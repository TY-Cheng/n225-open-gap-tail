from __future__ import annotations

import math
from pathlib import Path

import polars as pl
import pytest

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MODEL_NAMES,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    PIPELINE_CONFIG,
    PipelineRunError,
)
from n225_open_gap_tail.forecasting.sensitivity import (
    EVT_THRESHOLD_SPECS,
    LGBM_CONFIGURATION_SPECS,
    PAPER_LGBM_CONFIGURATION_LABELS,
    POST_24CHECK_LGBM_FAMILIES,
    RETIRED_EWMA_SENSITIVITY_ARTIFACTS,
    _build_evt_threshold_jobs,
    _build_lgbm_capacity_jobs,
    _cached_sensitivity_status_matches,
    _deterioration_ratio,
    _metric_rows_from_forecasts,
    _remove_retired_ewma_sensitivity_artifacts,
    _sensitivity_config_hash,
    _sensitivity_selection,
    _tag_rows,
    breach_category,
    classify_sensitivity_comparison,
    lgbm_sensitivity_config,
)
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_BENCHMARK_MODEL,
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
    benchmark_model_passes,
    pass_all_lgbm_model_names,
)
from n225_open_gap_tail.models.ml_tail import _lgbm_training_params


def test_lgbm_sensitivity_config_labels_are_exact() -> None:
    assert lgbm_sensitivity_config("current") == {
        "n_estimators": 160,
        "learning_rate": 0.025,
        "max_depth": -1,
        "num_leaves": 20,
        "min_child_samples": 25,
        "subsample": 0.85,
        "subsample_freq": 1,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.1,
        "reg_lambda": 0.5,
        "num_threads": 1,
    }
    assert lgbm_sensitivity_config("near_low")["n_estimators"] == 128
    assert lgbm_sensitivity_config("near_low")["num_leaves"] == 16
    assert lgbm_sensitivity_config("near_low")["min_child_samples"] == 30
    assert lgbm_sensitivity_config("near_high")["n_estimators"] == 192
    assert lgbm_sensitivity_config("near_high")["num_leaves"] == 24
    assert lgbm_sensitivity_config("near_high")["min_child_samples"] == 20
    assert set(LGBM_CONFIGURATION_SPECS) == {"current", "near_low", "near_high"}
    with pytest.raises(PipelineRunError, match="Unknown LightGBM sensitivity config label"):
        lgbm_sensitivity_config("wide")


def test_sensitivity_cache_key_rejects_retired_paper_scope_artifacts() -> None:
    current_status: dict[str, object] = {
        "scope": "paper",
        "sensitivity_config_hash": _sensitivity_config_hash(),
        "lgbm_config_labels": list(PAPER_LGBM_CONFIGURATION_LABELS),
        "evt_threshold_labels": list(EVT_THRESHOLD_SPECS),
        "job_counts": {"lgbm_capacity": 8, "evt_threshold": 12},
    }
    assert _cached_sensitivity_status_matches(current_status)

    stale_status = {
        **current_status,
        "lgbm_config_labels": ["shallow", "deeper"],
        "evt_threshold_labels": ["u_0_900", "u_0_925", "u_0_950_boundary"],
        "ewma_config_labels": [],
        "job_counts": {
            "lgbm_capacity": 8,
            "ewma_lambda": 0,
            "evt_threshold": 12,
            "evt_boundary_rows": 6,
        },
    }
    assert not _cached_sensitivity_status_matches(stale_status)


def _passing_metric_row(
    *,
    model_name: str,
    tail_side: str,
    information_set: str,
) -> dict[str, object]:
    return {
        "model_name": model_name,
        "tail_side": tail_side,
        "information_set": information_set,
        "rows": 500,
        "var_breach_rate": 0.05,
        "expected_breach_rate": 0.05,
        "kupiec_pvalue": 0.50,
        "christoffersen_pvalue": 0.50,
    }


def _write_selection_metrics(
    run_dir: Path,
    *,
    lgbm_models: tuple[str, ...] = POST_24CHECK_LGBM_FAMILIES,
    benchmark_rows: list[dict[str, object]] | None = None,
) -> None:
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    ml_rows = [
        _passing_metric_row(model_name=model, tail_side=tail_side, information_set=info)
        for model in lgbm_models
        for tail_side in PASS_ALL_TAIL_SIDES
        for info in PASS_ALL_INFORMATION_SETS
    ]
    pl.DataFrame(ml_rows).write_parquet(metrics_dir / "ml_tail_metrics_per_model.parquet")
    if benchmark_rows is None:
        benchmark_rows = [
            _passing_metric_row(
                model_name=PASS_ALL_BENCHMARK_MODEL,
                tail_side=tail_side,
                information_set="target_history_only",
            )
            for tail_side in PASS_ALL_TAIL_SIDES
        ]
    pl.DataFrame(benchmark_rows).write_parquet(metrics_dir / "benchmark_metrics_per_model.parquet")


def test_pass_all_helpers_identify_admissible_lgbm_and_benchmark_models() -> None:
    ml_rows = [
        _passing_metric_row(model_name=model, tail_side=tail_side, information_set=info)
        for model in (
            ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
            ML_TAIL_POT_GPD_UNIBM_MODEL,
            ML_TAIL_DIRECT_QUANTILE_MODEL,
        )
        for tail_side in PASS_ALL_TAIL_SIDES
        for info in PASS_ALL_INFORMATION_SETS
    ]
    assert pass_all_lgbm_model_names(pl.DataFrame(ml_rows)) == POST_24CHECK_LGBM_FAMILIES

    benchmark_rows = [
        _passing_metric_row(
            model_name=PASS_ALL_BENCHMARK_MODEL,
            tail_side=tail_side,
            information_set="target_history_only",
        )
        for tail_side in PASS_ALL_TAIL_SIDES
    ]
    assert benchmark_model_passes(pl.DataFrame(benchmark_rows))


def test_sensitivity_selection_uses_post24check_c_only(tmp_path: Path) -> None:
    run_dir = tmp_path / "tailrisk_selection"
    _write_selection_metrics(
        run_dir,
        lgbm_models=(
            ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
            ML_TAIL_POT_GPD_UNIBM_MODEL,
            ML_TAIL_DIRECT_QUANTILE_MODEL,
        ),
    )

    selection = _sensitivity_selection(run_dir=run_dir)

    assert selection.lgbm_models == POST_24CHECK_LGBM_FAMILIES
    assert selection.evt_lgbm_models == POST_24CHECK_LGBM_FAMILIES
    assert selection.benchmark_models == (PASS_ALL_BENCHMARK_MODEL,)
    assert selection.evt_benchmark_models == (PASS_ALL_BENCHMARK_MODEL,)
    assert selection.information_sets == (
        PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,
    )
    assert selection.lgbm_config_labels == PAPER_LGBM_CONFIGURATION_LABELS


def test_sensitivity_selection_rejects_missing_pass_all_inputs(tmp_path: Path) -> None:
    missing_lgbm_run = tmp_path / "missing_lgbm"
    _write_selection_metrics(
        missing_lgbm_run,
        lgbm_models=(ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,),
    )
    with pytest.raises(PipelineRunError, match="did not pass all checks"):
        _sensitivity_selection(run_dir=missing_lgbm_run)

    failing_benchmark_run = tmp_path / "failing_benchmark"
    benchmark_rows = [
        _passing_metric_row(
            model_name=PASS_ALL_BENCHMARK_MODEL,
            tail_side=tail_side,
            information_set="target_history_only",
        )
        for tail_side in PASS_ALL_TAIL_SIDES
    ]
    benchmark_rows[0]["kupiec_pvalue"] = 0.01
    _write_selection_metrics(failing_benchmark_run, benchmark_rows=benchmark_rows)
    with pytest.raises(PipelineRunError, match=PASS_ALL_BENCHMARK_MODEL):
        _sensitivity_selection(run_dir=failing_benchmark_run)


def test_sensitivity_cache_key_rejects_specific_stale_shapes() -> None:
    current_status: dict[str, object] = {
        "scope": "paper",
        "sensitivity_config_hash": _sensitivity_config_hash(),
        "lgbm_config_labels": list(PAPER_LGBM_CONFIGURATION_LABELS),
        "evt_threshold_labels": list(EVT_THRESHOLD_SPECS),
        "job_counts": {"lgbm_capacity": 8, "evt_threshold": 12},
    }

    assert not _cached_sensitivity_status_matches({**current_status, "scope": "full"})
    assert not _cached_sensitivity_status_matches(
        {**current_status, "sensitivity_config_hash": "stale"}
    )
    assert not _cached_sensitivity_status_matches(
        {key: value for key, value in current_status.items() if key != "sensitivity_config_hash"}
    )
    assert not _cached_sensitivity_status_matches(
        {**current_status, "lgbm_config_labels": "near_low"}
    )
    assert not _cached_sensitivity_status_matches(
        {**current_status, "evt_threshold_labels": ["u_0_900"]}
    )
    assert not _cached_sensitivity_status_matches({**current_status, "ewma_config_labels": []})
    assert not _cached_sensitivity_status_matches(
        {**current_status, "job_counts": {"ewma_lambda": 0}}
    )


def test_retired_ewma_sensitivity_artifacts_are_removed(tmp_path: Path) -> None:
    sensitivity_root = tmp_path / "sensitivity"
    for relative_path in RETIRED_EWMA_SENSITIVITY_ARTIFACTS:
        artifact = sensitivity_root / relative_path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("stale", encoding="utf-8")

    _remove_retired_ewma_sensitivity_artifacts(sensitivity_root)

    assert not any(
        (sensitivity_root / path).exists() for path in RETIRED_EWMA_SENSITIVITY_ARTIFACTS
    )


def test_sensitivity_job_construction_keeps_only_post24check_c_models() -> None:
    info_c = (PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,)
    jobs = _build_lgbm_capacity_jobs(
        panel_path=Path("panel.parquet"),
        coverage_path=Path("coverage.parquet"),
        coverage_rows=[],
        information_sets=info_c,
        tail_sides=PASS_ALL_TAIL_SIDES,
        tail_level=0.95,
        models=POST_24CHECK_LGBM_FAMILIES,
        config_labels=PAPER_LGBM_CONFIGURATION_LABELS,
    )
    assert len(jobs) == 8
    assert {job["model_name"] for job in jobs} == set(POST_24CHECK_LGBM_FAMILIES)
    assert {job["information_set"] for job in jobs} == set(info_c)
    assert {job["config_label"] for job in jobs} == set(PAPER_LGBM_CONFIGURATION_LABELS)
    assert ML_TAIL_DIRECT_QUANTILE_MODEL not in {job["model_name"] for job in jobs}
    assert ML_TAIL_LOCATION_SCALE_MODEL not in {job["model_name"] for job in jobs}
    assert ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL not in {job["model_name"] for job in jobs}
    assert ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL not in {job["model_name"] for job in jobs}

    evt_jobs = _build_evt_threshold_jobs(
        panel_path=Path("panel.parquet"),
        coverage_path=Path("coverage.parquet"),
        coverage_rows=[],
        information_sets=info_c,
        tail_sides=PASS_ALL_TAIL_SIDES,
        tail_level=0.95,
        pot_models=POST_24CHECK_LGBM_FAMILIES,
        benchmark_models=(PASS_ALL_BENCHMARK_MODEL,),
    )
    assert EVT_THRESHOLD_SPECS == {"u_0_875": 0.875, "u_0_925": 0.925}
    assert len(evt_jobs) == 12
    assert {job["evt_threshold_quantile"] for job in evt_jobs} == {0.875, 0.925}


def test_primary_lgbm_params_remain_registered_current_spec() -> None:
    assert _lgbm_training_params() == lgbm_sensitivity_config("current")


def test_sensitivity_configs_do_not_enter_primary_model_registry() -> None:
    registry_text = " ".join(ML_TAIL_MODEL_NAMES)
    assert "near_low" not in registry_text
    assert "near_high" not in registry_text
    assert "sensitivity" not in registry_text


def test_breach_category_thresholds_are_registered() -> None:
    assert breach_category(None) == "missing"
    assert breach_category(0.05) == "near_nominal"
    assert breach_category(0.075) == "near_nominal"
    assert breach_category(0.0751) == "coverage_warning"
    assert breach_category(0.0249) == "coverage_warning"


def test_robustness_classification_uses_abs_negative_fz_denominator() -> None:
    fz_deterioration = _deterioration_ratio(-3.90, -4.00)
    assert fz_deterioration is not None
    assert math.isclose(fz_deterioration, 0.025)
    assert _deterioration_ratio(None, -4.00) is None
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.05,
            sensitivity_breach_rate=0.052,
            q_loss_deterioration=0.03,
            fz_loss_deterioration=fz_deterioration,
        )
        == "robust"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.05,
            sensitivity_breach_rate=0.08,
            q_loss_deterioration=0.00,
            fz_loss_deterioration=-0.01,
        )
        == "sensitive"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.04,
            sensitivity_breach_rate=0.04,
            q_loss_deterioration=0.06,
            fz_loss_deterioration=0.00,
        )
        == "mixed"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.01,
            sensitivity_breach_rate=0.05,
            q_loss_deterioration=0.00,
            fz_loss_deterioration=0.00,
        )
        == "mixed"
    )


def test_tag_rows_omits_none_metadata() -> None:
    assert _tag_rows([{"model_name": "m"}], source_run_id="run", optional=None) == [
        {"model_name": "m", "source_run_id": "run"}
    ]


def test_metric_rows_from_forecasts_registers_classification_and_primary_comparison() -> None:
    forecasts = [
        {
            "fit_status": "ok",
            "is_valid_forecast": True,
            "tail_level": 0.95,
            "model_name": "demo_model",
            "information_set": "demo_info",
            "tail_side": "left_tail",
            "sensitivity_family": "lgbm_capacity",
            "config_label": "near_high",
            "evt_threshold_quantile": 0.90,
            "realized_loss": 2.0,
            "var_forecast": 1.0,
            "es_forecast": 1.5,
        },
        {
            "fit_status": "ok",
            "is_valid_forecast": True,
            "tail_level": 0.95,
            "model_name": "demo_model",
            "information_set": "demo_info",
            "tail_side": "left_tail",
            "sensitivity_family": "lgbm_capacity",
            "config_label": "near_high",
            "evt_threshold_quantile": 0.90,
            "realized_loss": 0.5,
            "var_forecast": 1.0,
            "es_forecast": 1.5,
        },
        {
            "fit_status": "failed",
            "is_valid_forecast": False,
            "tail_level": 0.95,
            "model_name": "demo_model",
        },
    ]
    primary_metrics: dict[tuple[str, str, str, float], dict[str, object]] = {
        ("demo_model", "demo_info", "left_tail", 0.95): {
            "rows": 2,
            "var_breach_rate": 0.50,
            "mean_quantile_loss": 0.30,
            "mean_fz_loss": -0.50,
        }
    }

    rows = _metric_rows_from_forecasts(
        forecasts,
        primary_metrics=primary_metrics,
        source_run_id="tailrisk_demo",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["source_primary_run_id"] == "tailrisk_demo"
    assert row["primary_claim_allowed"] is False
    assert row["rows"] == 2
    assert row["exceedance_count"] == 1
    assert row["var_breach_rate"] == 0.50
    assert row["primary_rows"] == 2
    assert row["primary_breach_category"] == "coverage_warning"
    assert row["breach_category"] == "coverage_warning"
    assert row["robustness_classification"] in {"robust", "mixed", "sensitive"}

    skipped_rows = _metric_rows_from_forecasts(
        [
            {"fit_status": "ok", "is_valid_forecast": True, "tail_level": None},
            {
                "fit_status": "ok",
                "is_valid_forecast": True,
                "tail_level": 0.95,
                "model_name": "empty_model",
                "information_set": "empty_info",
                "tail_side": "left_tail",
                "sensitivity_family": "lgbm_capacity",
                "config_label": "near_high",
                "realized_loss": 2.0,
                "var_forecast": 1.0,
                "es_forecast": None,
            },
        ],
        primary_metrics={},
        source_run_id="tailrisk_demo",
    )
    assert skipped_rows == []
