from __future__ import annotations

import importlib
import json
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import polars as pl
import pytest
from typer.testing import CliRunner

import n225_open_gap_tail.forecasting.body_experiment as experiment
import n225_open_gap_tail.models.benchmark as benchmark
import n225_open_gap_tail.models.ml_body as bodies
from n225_open_gap_tail.cli import app
from n225_open_gap_tail.config.runtime import PANEL_SIGNATURE_COLUMNS, PipelineRunError
from n225_open_gap_tail.forecasting._guards import _assert_leakage_gate
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible
from n225_open_gap_tail.models.benchmark import _pot_gpd_standardized_tail
from n225_open_gap_tail.models.ml_tail_oof import _fit_lgb_regression_model
from n225_open_gap_tail.panel.information_sets import registered_ml_tail_information_sets


def sample_rows(n: int = 120) -> list[dict[str, Any]]:
    return [
        {
            "forecast_date": (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
            "realized_loss": 0.01 * np.sin(i) + 0.0001 * i,
            "clean_sample": True,
            "feature_x": float(i),
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("tail_side", ["left_tail", "right_tail"])
def test_shared_refit_native_bodies_units_and_anchor_reuse(
    monkeypatch: pytest.MonkeyPatch, tail_side: str
) -> None:
    monkeypatch.setattr(bodies, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(experiment, "EVT_MIN_STANDARDIZED_LOSSES_95", 50)
    monkeypatch.setattr(experiment, "EVT_MIN_EXCEEDANCES_95", 3)
    monkeypatch.setattr(experiment, "LOCATION_SCALE_MIN_ES_EXCEEDANCES_95", 3)
    anchors: list[tuple[np.ndarray, int]] = []
    calls: list[dict[str, Any]] = []
    targets: list[np.ndarray] = []
    native_fit = _fit_lgb_regression_model
    native_tail = _pot_gpd_standardized_tail

    def fit(**kwargs: Any) -> Any:
        targets.append(kwargs["target"])
        return native_fit(**kwargs)

    def anchor(values: np.ndarray, *, warmup_rows: int) -> dict[str, Any]:
        assert np.isnan(values[:warmup_rows]).all()
        anchors.append((values, warmup_rows))
        return {"status": "ok", "xi_evi_anchor": 0.2}

    def tail(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return native_tail(**kwargs)

    monkeypatch.setattr(experiment, "_fit_lgb_regression_model", fit)
    monkeypatch.setattr(experiment, "estimate_public_unibm", anchor)
    monkeypatch.setattr(experiment, "_pot_gpd_standardized_tail", tail)
    train = sample_rows()
    if tail_side == "right_tail":
        train = [{**row, "realized_loss": -row["realized_loss"]} for row in train]
    future = [{**train[-1], "forecast_date": f"2020-05-0{i}"} for i in (1, 2)]
    progress: list[str] = []
    result = experiment.forecast_shared_body_refit(
        train,
        future,
        candidate_features=["feature_x"],
        information_set="A",
        tail_side=tail_side,
        lgbm_params={"n_estimators": 3, "min_child_samples": 3},
        progress=progress.append,
    )
    assert len(result["forecasts"]) == 56
    assert {row["model_name"] for row in result["forecasts"]} == set(bodies.EXPERIMENT_MODEL_NAMES)
    assert len(result["diagnostics"]) == 10 and len(result["oof"]) == 9 * len(train)
    assert len(anchors) == 9 and len(calls) == 18
    assert all(call["shape_upper_bound"] == 0.99 for call in calls)
    for i, (values, _) in enumerate(anchors):
        assert calls[2 * i]["standardized_losses"] is values
        assert calls[2 * i + 1]["standardized_losses"] is values
        assert calls[2 * i + 1]["preserve_var_without_es"] is True
        assert calls[2 * i + 1]["unibm_anchor"]["status"] == "ok"
    np.testing.assert_allclose(targets[0], [row["realized_loss"] for row in train])
    for records in (result["forecasts"], result["diagnostics"], result["oof"]):
        assert all(row["training_multiplier"] == 1 for row in records)
    first = result["forecasts"][0]
    assert first["es_companion_type"] == "training_in_sample_empirical_excess"
    assert 0 < abs(first["var_forecast"]) < 0.1
    assert first["train_end"] < first["forecast_date"]
    assert all(row["var_eligible"] for row in result["forecasts"]), result["diagnostics"]
    for detail in result["diagnostics"][1:]:
        assert "xi_evi_anchor" not in detail["public_unibm"]
        for method, fitted_tail in detail["tails"].items():
            assert "evt_cap_hit" not in fitted_tail and "evt_shape_mle" not in fitted_tail
            name = bodies.body_model_name(detail["recipe"], method)
            for row in result["forecasts"]:
                if row["model_name"] != name:
                    continue
                assert row["var_forecast"] == pytest.approx(
                    row["location"] + row["scale"] * fitted_tail["standardized_var"]
                )
                if fitted_tail["standardized_es"] is None:
                    assert row["es_forecast"] is None
                else:
                    assert row["es_forecast"] == pytest.approx(
                        row["location"] + row["scale"] * fitted_tail["standardized_es"]
                    )
    assert len(progress) == 19


def test_refit_preserves_partial_es_and_all_unavailable_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train = sample_rows()
    future = [{**train[-1], "forecast_date": "2020-05-01"}]
    monkeypatch.setattr(bodies, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(
        experiment,
        "estimate_public_unibm",
        lambda *a, **k: {"status": "unavailable", "failure_reason": "strict FGLS failed"},
    )
    monkeypatch.setattr(
        experiment,
        "_pot_gpd_standardized_tail",
        lambda **k: {
            "standardized_var": 2.0,
            "standardized_es": None,
            "evt_es_failure_reason": "unavailable_gpd_es_shape_ge_one",
        },
    )

    def fail(**kwargs: Any) -> Any:
        raise PipelineRunError("deliberate failed fit")

    monkeypatch.setattr(experiment, "_fit_lgb_regression_model", fail)
    result = experiment.forecast_shared_body_refit(
        train,
        future,
        candidate_features=["feature_x"],
        information_set="A",
        tail_side="right_tail",
        lgbm_params={"n_estimators": 2, "min_child_samples": 3},
    )
    assert len(result["forecasts"]) == 28
    partial = [row for row in result["forecasts"] if row["model_name"].endswith("plain_mle")]
    assert len(partial) == 9
    assert all(
        row["var_eligible"] and not row["joint_eligible"] and not row["fz0_eligible"]
        for row in partial
    )
    assert all(row["es_forecast"] is None for row in partial)
    assert sum(row["fit_status"] == "unavailable_fit" for row in result["forecasts"]) == 10
    assert all(
        row["es_failure_reason"] == "insufficient_empirical_es_exceedances"
        for row in result["forecasts"]
        if row["model_name"].endswith("empirical")
    )

    monkeypatch.setattr(
        experiment,
        "fit_body_recipes",
        lambda *a, **k: iter(
            (recipe, {"fit_status": "unavailable_body_fit", "failure_reason": "missing OOF"})
            for recipe in bodies.BODY_RECIPES
        ),
    )
    result = experiment.forecast_shared_body_refit(
        train,
        future,
        candidate_features=["feature_x"],
        information_set="A",
        tail_side="left_tail",
        progress=lambda message: None,
    )
    assert len(result["forecasts"]) == 28 and not result["oof"]
    assert all(row["fit_status"] == "unavailable_fit" for row in result["forecasts"])


def test_pot_retains_finite_var_without_empirical_es_or_clip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = np.linspace(-2, 5, 600)
    monkeypatch.setattr("scipy.stats.genpareto.fit", lambda *a, **k: (1.2, 0.0, 1.0))
    result = benchmark._pot_gpd_standardized_tail(
        standardized_losses=values,
        tail_level=0.95,
        min_standardized_losses=100,
        min_exceedances=20,
        preserve_var_without_es=True,
    )
    assert isinstance(result["standardized_var"], float) and np.isfinite(result["standardized_var"])
    assert result["standardized_es"] is None and not result["evt_es_finite"]
    assert result["evt_es_failure_reason"] == "unavailable_gpd_es_shape_ge_one"
    row = {
        "fit_status": "invalid_forecast",
        "invalid_reason": "invalid_nonfinite_forecast",
        "var_forecast": result["standardized_var"],
        "es_forecast": None,
        "realized_loss": 2.0,
        "tail_level": 0.95,
    }
    assert forecast_eligible(row) and not forecast_eligible(row, score="joint")
    with pytest.raises(ValueError, match="both retain"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=values,
            tail_level=0.95,
            preserve_var_without_es=True,
            require_finite_gpd_es=True,
        )
    with pytest.raises(PipelineRunError, match="infinite ES"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=values,
            tail_level=0.95,
            min_standardized_losses=100,
            min_exceedances=20,
            require_finite_gpd_es=True,
        )


@pytest.mark.parametrize("variant", ["plain_mle", "unibm"])
@pytest.mark.parametrize("shape", [-0.2, 0.0, 0.2, 0.99, 1.2])
def test_ml_shape_bound_refits_scale_and_reports_only_final_shape(
    monkeypatch: pytest.MonkeyPatch, variant: str, shape: float
) -> None:
    fixed_shapes: list[float] = []

    def fit(*args: Any, **kwargs: Any) -> tuple[float, float, float]:
        if "f0" in kwargs:
            fixed_shapes.append(kwargs["f0"])
            return kwargs["f0"], 0.0, 3.0
        return shape, 0.0, 2.0

    monkeypatch.setattr("scipy.stats.genpareto.fit", fit)
    anchor = {"status": "ok", "xi_evi_anchor": shape, "bootstrap_precision_met": False}
    values = np.linspace(-2, 5, 600)
    result = benchmark._pot_gpd_standardized_tail(
        standardized_losses=values,
        tail_level=0.95,
        min_standardized_losses=100,
        min_exceedances=20,
        evt_variant=variant,
        unibm_anchor=anchor,
        shape_upper_bound=0.99,
        preserve_var_without_es=True,
    )
    final_shape = min(shape, 0.99)
    refit = variant == "unibm" or shape > 0.99
    scale = 3.0 if refit else 2.0
    assert fixed_shapes == ([final_shape] if refit else [])
    assert result["evt_shape"] == final_shape and result["evt_scale"] == scale
    threshold = np.quantile(values, 0.9)
    q = threshold + scale * (
        np.expm1(final_shape * np.log(2)) / final_shape if final_shape else np.log(2)
    )
    es = q + (scale + final_shape * (q - threshold)) / (1 - final_shape)
    assert result["standardized_var"] == pytest.approx(q)
    assert result["standardized_es"] == pytest.approx(es)
    assert result["evt_es_failure_reason"] is None
    for key in ("evt_cap_hit", "evt_shape_mle", "evt_scale_mle", "evt_xi_evi_anchor"):
        assert key not in result
    assert "evt_threshold_sensitivity_json" not in result
    assert anchor["xi_evi_anchor"] == shape  # never mutate the supplied fit
    if variant == "unibm":
        diagnostics = json.loads(str(result["evt_evi_diagnostics_json"]))
        assert "xi_evi_anchor" not in diagnostics
        assert diagnostics["bootstrap_precision_met"] is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_shape_bound_never_repairs_nonfinite_estimates(
    monkeypatch: pytest.MonkeyPatch, value: float
) -> None:
    monkeypatch.setattr("scipy.stats.genpareto.fit", lambda *a, **k: (value, 0.0, 1.0))
    standardized_losses = np.linspace(-2, 5, 600)
    with pytest.raises(ValueError, match="upper bound"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=0.95,
            min_standardized_losses=100,
            min_exceedances=20,
            shape_upper_bound=value,
        )
    with pytest.raises(PipelineRunError, match="nonfinite GPD shape"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=0.95,
            min_standardized_losses=100,
            min_exceedances=20,
            shape_upper_bound=0.99,
        )
    with pytest.raises(ValueError, match="upper bound"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=0.95,
            min_standardized_losses=100,
            min_exceedances=20,
            shape_upper_bound=1.0,
        )


@pytest.mark.parametrize(
    "case", ["empty", "future", "duplicate", "month", "side", "nan", "excluded"]
)
def test_refit_input_boundary(case: str) -> None:
    train, future = sample_rows(), [{**sample_rows(1)[0], "forecast_date": "2020-05-01"}]
    side = "left_tail"
    if case == "empty":
        train = []
    if case == "future":
        future[0]["forecast_date"] = "2019-01-01"
    if case == "duplicate":
        train.append(train[-1])
    if case == "month":
        future.append({**future[0], "forecast_date": "2020-06-01"})
    if case == "side":
        side = "both"
    if case == "nan":
        train[0]["realized_loss"] = np.nan
    if case == "excluded":
        train[0]["clean_sample"] = False
    with pytest.raises(ValueError):
        experiment.forecast_shared_body_refit(
            train, future, candidate_features=["feature_x"], information_set="A", tail_side=side
        )


def test_pilot_artifacts_isolation_binding_and_no_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    (source / "panel").mkdir(parents=True)
    original = {
        "main_sample_start_requested": "2020-01-01",
        "jquants_required_field_coverage_start": "2020-01-01",
        "training_multiplier": 100.0,
        "gold_root": "/do/not/write",
        "gold_artifacts": {"modeling_panel": "/do/not/read"},
    }
    (source / "manifest.json").write_text(json.dumps(original))
    rows = [
        {
            **dict.fromkeys(PANEL_SIGNATURE_COLUMNS),
            **row,
            "target_clean_sample": True,
            "forecast_sample": True,
            "model_cutoff_ts_utc": datetime(2020, 1, 1),
            "target_open_ts_utc": datetime(2020, 1, 1, 1),
            "gap_t": -row["realized_loss"],
            "mapping_status": "normal_trading",
        }
        for row in sample_rows(10)
    ]
    pl.from_dicts(rows).write_parquet(source / "panel/modeling_panel.parquet")
    pl.DataFrame(
        {
            "ose_trading_date": ["2020-01-01"],
            "us_session_date": ["2019-12-31"],
            "model_cutoff_ts_utc": [datetime(2020, 1, 1)],
            "target_open_ts_utc": [datetime(2020, 1, 1, 1)],
            "mapping_status": ["normal_trading"],
            "mapping_reason": [None],
        }
    ).write_parquet(source / "panel/calendar_map.parquet")
    monkeypatch.setattr(experiment, "find_oos_start_date", lambda *a, **k: "2020-01-01")
    # A prior month is required for a historical prefix; shift the final test date.
    rows[-1]["forecast_date"] = "2020-02-01"
    pl.from_dicts(rows).write_parquet(source / "panel/modeling_panel.parquet")
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: SimpleNamespace(__file__=str(source / "evi.py")),
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="test-revision"))
    observed: list[dict[str, Any]] = []

    def refit(train: Any, future: Any, **kwargs: Any) -> dict[str, Any]:
        observed.append(kwargs)
        assert len(train) == 9 and future[0]["forecast_date"] == "2020-02-01"
        return {
            "forecasts": [
                {
                    **future[0],
                    "information_set": kwargs["information_set"],
                    "model_name": name,
                    "tail_level": 0.95,
                    "fit_status": "ok",
                    "var_forecast": 0.01,
                    "es_forecast": 0.02,
                }
                for name in bodies.EXPERIMENT_MODEL_NAMES
            ],
            "diagnostics": [{"fit_status": "ok"}],
            kwargs.get("calibration_kind", "oof"): [{"position": 0, "standardized_losses": None}],
        }

    monkeypatch.setattr(experiment, "forecast_shared_body_refit", refit)
    output = tmp_path / "pilot"
    result = experiment.run_body_pilot(
        source,
        output,
        forecast_date="2020-02-01",
        information_set="japan_only",
        tail_side="left_tail",
        progress=lambda message: None,
    )
    assert result == output and len(observed) == 1
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "completed" and manifest["forecast_rows"] == 28
    assert manifest["training_multiplier"] == 1
    assert manifest["sample_policy"] == "clean_predictor_entitlement_sample"
    assert "gold_root" not in manifest and "gold_artifacts" not in manifest
    assert manifest["leakage_check_failures"] == 0 and manifest["elapsed_seconds"] > 0
    assert (output / "audits/leakage_check_summary.json").exists()
    _assert_leakage_gate(output)
    assert json.loads((source / "manifest.json").read_text()) == original
    # The body entry point must reapply predictor bounds, even to an expanded source panel.
    later_rows = [{**row, "xlc_return": None, "xlc_return__source_date": None} for row in rows]
    later_rows[-1].update(xlc_return=0.01, xlc_return__source_date="2020-01-05")
    pl.from_dicts(later_rows).write_parquet(source / "panel/modeling_panel.parquet")
    bounded, bounded_rows, _ = experiment._prepare_body_run(source, tmp_path / "bounded")
    assert bounded["combined_clean_start"] == "2020-01-05"
    assert sum(row["clean_sample"] is True for row in bounded_rows) == 6
    pl.from_dicts(rows).write_parquet(source / "panel/modeling_panel.parquet")
    with pytest.raises(FileExistsError):
        experiment.run_body_pilot(
            source,
            output,
            forecast_date="2020-02-01",
            information_set="japan_only",
            tail_side="left_tail",
        )
    with pytest.raises(ValueError, match="outside"):
        experiment.run_body_pilot(
            source,
            source / "bad",
            forecast_date="2020-02-01",
            information_set="japan_only",
            tail_side="left_tail",
        )
    with pytest.raises(ValueError, match="first eligible"):
        experiment.run_body_pilot(
            source,
            tmp_path / "wrongdate",
            forecast_date="2020-02-02",
            information_set="japan_only",
            tail_side="left_tail",
        )

    monkeypatch.setattr(experiment, "find_oos_start_date", lambda *a, **k: "2020-02-01")
    observed.clear()
    rolling = tmp_path / "rolling"
    experiment.run_body_rolling(source, rolling, progress=lambda message: None)
    rolling_manifest = json.loads((rolling / "manifest.json").read_text())
    assert rolling_manifest["status"] == "completed"
    assert rolling_manifest["kind"] == "shared_body_rolling_forecast"
    assert rolling_manifest["training_multiplier"] == 1
    assert rolling_manifest["completed_refits"] == len(observed) == 8
    assert rolling_manifest["forecast_rows"] == 224
    assert len(list((rolling / "refits").rglob("diagnostics.json"))) == 8
    assert len(list((rolling / "refits").rglob("oof_residuals.parquet"))) == 8
    assert rolling_manifest["leakage_check_failures"] == 0
    rolling_forecasts = pl.read_parquet(rolling / "forecasts/ml_tail_forecasts.parquet")
    assert rolling_forecasts["information_set"].n_unique() == 4
    assert rolling_forecasts["tail_side"].n_unique() == 2
    assert rolling_forecasts["target_session_index"].unique().to_list() == [9]
    assert rolling_forecasts.filter(pl.col("tail_side") == "right_tail")[
        "realized_loss"
    ].unique().to_list() == [-rows[-1]["realized_loss"]]
    assert not (rolling / "forecasts/benchmark_forecasts.parquet").exists()
    assert not (rolling / "metrics").exists()
    _assert_leakage_gate(rolling)
    with pytest.raises(FileExistsError):
        experiment.run_body_rolling(source, rolling)

    from n225_open_gap_tail.forecasting import tuned_body

    monkeypatch.setattr(tuned_body, "_save_working_source", lambda path: None)
    monkeypatch.setattr(tuned_body, "forecast_shared_body_refit", refit)

    def joint(cases: Any, **kw: Any) -> Any:
        assert len(cases) == 8
        kw["receipt"](
            {
                "role": "direct",
                "cutoff": "2020-02-01",
                "status": "selected",
                "selected_name": "current",
                "parameters": {"n_estimators": 160},
            }
        )
        return {key: {"direct": {"test": True}} for key in cases}

    monkeypatch.setattr(tuned_body, "fit_joint_bodies", joint)
    for pilot_date, workers in (("2020-02-01", 1), (None, 1), (None, None), (None, 3)):
        destination = tmp_path / f"tuned_{pilot_date}_{workers}"
        observed.clear()
        tuned_body.run_tuned_body(
            source,
            destination,
            forecast_date=pilot_date,
            progress=lambda message: None,
            **({} if workers is None else {"workers": workers}),
        )
        tuned_manifest = json.loads((destination / "manifest.json").read_text())
        assert tuned_manifest["status"] == "completed" and len(observed) == 8
        assert tuned_manifest["month_workers"] == (2 if workers is None else workers)
        assert tuned_manifest["completed_refits"] == 8 and tuned_manifest["forecast_rows"] == 224
        assert all(c["components"]["direct"]["test"] for c in observed)
        assert all(c["calibration_kind"] == "oof" for c in observed)
        assert tuned_manifest["tuning"]["cv_splits"] == 5
        assert tuned_manifest["tuning"]["cv_shuffle"] is False
        assert (
            tuned_manifest["calibration_warmup_policy"] == "per_refit_component_structural_warmup"
        )
        assert len(list((destination / "refits").rglob("oof_residuals.parquet"))) == 8
        assert not list((destination / "refits").rglob("in_sample_residuals.parquet"))
        assert (
            tuned_manifest["tail_calibration"]
            == "selected_parameter_expanding_oof_standardized_residuals"
        )
        assert (destination / "selection/2020-02.json").exists()
    with pytest.raises(ValueError, match="first eligible"):
        tuned_body.run_tuned_body(
            source, tmp_path / "tuned_bad_date", forecast_date="2020-02-02", workers=1
        )
    for workers in (0, 4):
        with pytest.raises(ValueError, match="month workers"):
            tuned_body.run_tuned_body(source, tmp_path / "invalid_workers", workers=workers)
    with pytest.raises(ValueError, match="pilot requires"):
        tuned_body.run_tuned_body(source, tmp_path / "parallel_pilot", forecast_date="2020-02-01")

    monkeypatch.setattr(tuned_body, "registered_ml_tail_information_sets", lambda: ["japan_only"])
    with pytest.raises(ValueError, match="eight scenario"):
        tuned_body.run_tuned_body(source, tmp_path / "tuned_missing_group")
    monkeypatch.setattr(
        tuned_body,
        "registered_ml_tail_information_sets",
        registered_ml_tail_information_sets,
    )

    def joint_crash(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("no hidden retry")

    monkeypatch.setattr(tuned_body, "fit_joint_bodies", joint_crash)
    with pytest.raises(RuntimeError, match="no hidden retry"):
        tuned_body.run_tuned_body(source, tmp_path / "tuned_crash", workers=1)
    assert json.loads((tmp_path / "tuned_crash/manifest.json").read_text())["status"] == "failed"
    with pytest.raises(RuntimeError, match="no hidden retry"):
        tuned_body.run_tuned_body(source, tmp_path / "tuned_parallel_crash", workers=2)

    def crash(*a: Any, **k: Any) -> Any:
        raise RuntimeError("do not retry")

    monkeypatch.setattr(experiment, "forecast_shared_body_refit", crash)
    failed = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="do not retry"):
        experiment.run_body_pilot(
            source,
            failed,
            forecast_date="2020-02-01",
            information_set="japan_only",
            tail_side="left_tail",
        )
    assert json.loads((failed / "manifest.json").read_text())["status"] == "failed"
    failed_rolling = tmp_path / "failed_rolling"
    with pytest.raises(RuntimeError, match="do not retry"):
        experiment.run_body_rolling(source, failed_rolling)
    failed_manifest = json.loads((failed_rolling / "manifest.json").read_text())
    assert failed_manifest["status"] == "failed" and failed_manifest["completed_refits"] == 0


def test_body_pilot_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def run(source: Path, output: Path, **kwargs: Any) -> Path:
        calls.append(kwargs)
        return output

    monkeypatch.setattr(experiment, "run_body_pilot", run)
    from n225_open_gap_tail.forecasting import tuned_body

    monkeypatch.setattr(tuned_body, "run_tuned_body", run)
    tuned_result = CliRunner().invoke(
        app,
        [
            "body-tuned",
            "--source-run",
            str(tmp_path / "source"),
            "--output-dir",
            str(tmp_path / "tuned"),
            "--forecast-date",
            "2026-05-01",
            "--workers",
            "1",
        ],
    )
    assert tuned_result.exit_code == 0
    pilot_call = calls.pop()
    assert pilot_call["forecast_date"] == "2026-05-01" and pilot_call["workers"] == 1
    tuned_result = CliRunner().invoke(
        app,
        ["body-tuned", "--source-run", str(tmp_path), "--output-dir", str(tmp_path / "full")],
    )
    assert tuned_result.exit_code == 0 and calls.pop()["workers"] == 2
    result = CliRunner().invoke(
        app,
        [
            "body-pilot",
            "--source-run",
            str(tmp_path / "source"),
            "--output-dir",
            str(tmp_path / "pilot"),
            "--forecast-date",
            "2026-05-01",
            "--information-set",
            "A",
            "--tail-side",
            "left_tail",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["forecast_date"] == "2026-05-01" and "body pilot:" in result.output
    monkeypatch.setattr(experiment, "run_body_rolling", run)
    result = CliRunner().invoke(
        app,
        ["body-rolling", "--source-run", str(tmp_path), "--output-dir", str(tmp_path / "rolling")],
    )
    assert result.exit_code == 0 and "body rolling forecasts:" in result.output


def test_monthly_prefixes_preserve_maximal_history_and_mid_month_oos_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = sample_rows(120)
    rows[50]["clean_sample"] = False
    rows[65]["realized_loss"] = None
    monkeypatch.setattr(experiment, "find_oos_start_date", lambda *a, **k: "2020-02-15")
    batches = list(experiment.monthly_body_refits(rows, tail_level=0.95))
    assert [future[0]["forecast_date"] for _, future in batches] == [
        "2020-02-15",
        "2020-03-01",
        "2020-04-01",
    ]
    for train, future in batches:
        first = future[0]["forecast_date"]
        assert train == [
            row
            for row in rows
            if row["forecast_date"] < first
            and row["clean_sample"]
            and row["realized_loss"] is not None
        ]
        assert len({row["forecast_date"][:7] for row in future}) == 1
        assert all(row["clean_sample"] and row["realized_loss"] is not None for row in future)
    expected = [
        row
        for row in rows
        if row["forecast_date"] >= "2020-02-15"
        and row["clean_sample"]
        and row["realized_loss"] is not None
    ]
    assert [row for _, future in batches for row in future] == expected
    monkeypatch.setattr(experiment, "find_oos_start_date", lambda *a, **k: None)
    with pytest.raises(ValueError, match="No scheduled OOS"):
        list(experiment.monthly_body_refits(rows, tail_level=0.95))
