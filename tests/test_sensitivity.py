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
    _build_evt_threshold_jobs,
    _build_lgbm_capacity_jobs,
    _cached_sensitivity_status_matches,
    _deterioration_ratio,
    _evt_boundary_metric_rows,
    _metric_rows_from_forecasts,
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
    with pytest.raises(PipelineRunError, match="Unknown LGBM sensitivity config label"):
        lgbm_sensitivity_config("wide")


def test_sensitivity_cache_key_rejects_retired_paper_scope_artifacts() -> None:
    current_status: dict[str, object] = {
        "scope": "paper",
        "lgbm_config_labels": list(PAPER_LGBM_CONFIGURATION_LABELS),
        "evt_threshold_labels": list(EVT_THRESHOLD_SPECS),
        "job_counts": {"lgbm_capacity": 8, "evt_threshold": 12, "evt_boundary_rows": 6},
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

    evt_jobs, boundary_rows = _build_evt_threshold_jobs(
        panel_path=Path("panel.parquet"),
        coverage_path=Path("coverage.parquet"),
        coverage_rows=[],
        information_sets=info_c,
        tail_sides=PASS_ALL_TAIL_SIDES,
        tail_level=0.95,
        pot_models=POST_24CHECK_LGBM_FAMILIES,
        benchmark_models=(PASS_ALL_BENCHMARK_MODEL,),
    )
    assert len(evt_jobs) == 12
    assert len(boundary_rows) == 6
    assert {job["evt_threshold_quantile"] for job in evt_jobs} == {0.875, 0.925}
    assert {row["evt_threshold_quantile"] for row in boundary_rows} == {0.95}


def test_primary_lgbm_params_remain_registered_current_spec() -> None:
    assert _lgbm_training_params() == lgbm_sensitivity_config("current")


def test_sensitivity_configs_do_not_enter_primary_model_registry() -> None:
    registry_text = " ".join(ML_TAIL_MODEL_NAMES)
    assert "near_low" not in registry_text
    assert "near_high" not in registry_text
    assert "sensitivity" not in registry_text


def test_evt_threshold_095_is_boundary_only_at_95pct_tail() -> None:
    rows = _evt_boundary_metric_rows(
        config_label="u_0_950_boundary",
        threshold=EVT_THRESHOLD_SPECS["u_0_950_boundary"],
        tail_sides=("left_tail",),
        tail_level=0.95,
        information_sets=("japan_only",),
        models=("lightgbm_standardized_loss_pot_gpd_plain_mle",),
    )
    assert rows[0]["sensitivity_status"] == "not_applicable_threshold_not_below_tail_level"
    assert rows[0]["rows"] == 0
    assert rows[0]["robustness_classification"] == "boundary_diagnostic"


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
