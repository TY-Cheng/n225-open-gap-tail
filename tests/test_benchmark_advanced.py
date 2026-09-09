# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

import ast
import importlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import polars as pl
import pytest

import n225_open_gap_tail.config.runtime as pipeline_runtime
import n225_open_gap_tail.data_lake.artifacts as artifact_utils
import n225_open_gap_tail.data_lake.cache_ops as paper_cache
import n225_open_gap_tail.features as paper_features
import n225_open_gap_tail.forecasting as paper_core
import n225_open_gap_tail.forecasting as paper_evaluation
import n225_open_gap_tail.forecasting as paper_module
import n225_open_gap_tail.forecasting._benchmark_suite as benchmark_suite
import n225_open_gap_tail.forecasting._ml_tail_suite as ml_tail_suite
import n225_open_gap_tail.inference as paper_inference
import n225_open_gap_tail.metrics.stat_utils as stat_utils
import n225_open_gap_tail.models.benchmark as benchmark
import n225_open_gap_tail.models.benchmark_advanced as benchmark_advanced
import n225_open_gap_tail.models.benchmark_advanced_math as advanced_math
import n225_open_gap_tail.models.benchmark_advanced_stateful as advanced_stateful
import n225_open_gap_tail.panel as paper_leakage
import n225_open_gap_tail.panel as paper_panel
import n225_open_gap_tail.reporting as paper_reporting
import n225_open_gap_tail.reporting.figures as reporting_figures
import n225_open_gap_tail.reporting.latex as reporting_latex
import n225_open_gap_tail.reporting.tables as reporting_tables
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import VendorErrorClass
from n225_open_gap_tail.forecasting import (
    build_feature_coverage_records,
    build_feature_matrix_gate_records,
    build_fields_coverage_audit_records,
    build_leakage_check_records,
    build_ml_tail_modeling_rows,
    build_modeling_panel_records,
    build_panel,
    build_run_id,
    build_spy_compat_late_session_feature_records,
    drop_low_variance_features,
    empirical_excess_es_companion,
    evaluate_benchmark_baseline_suite,
    evaluate_benchmark_suite,
    evaluate_ml_tail_suite,
    evaluate_suite,
    export_tables,
    filtered_historical_es,
    find_oos_start_date,
    global_oos_intersection,
    kupiec_pof_test,
    ml_tail_feature_columns_for_information_set,
    pairwise_oos_intersection,
    quantile_loss,
    static_empirical_es,
    validate_forecast_values,
    validate_worker_payload,
    write_leakage_check,
)


def _patch_paper_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: object,
) -> None:
    """Patch copied globals across the functional modules used by this test suite."""
    module_names = (
        "n225_open_gap_tail.config.runtime",
        "n225_open_gap_tail.forecasting",
        "n225_open_gap_tail.panel.build",
        "n225_open_gap_tail.panel.leakage",
        "n225_open_gap_tail.models.benchmark",
        "n225_open_gap_tail.models.benchmark_advanced",
        "n225_open_gap_tail.models.ml_tail",
        "n225_open_gap_tail.models.ml_tail_oof",
        "n225_open_gap_tail.metrics.information",
        "n225_open_gap_tail.metrics.result_matrix",
        "n225_open_gap_tail.inference.core",
        "n225_open_gap_tail.features.asof",
        "n225_open_gap_tail.features.session_features",
        "n225_open_gap_tail.data_lake.cache_ops",
        "n225_open_gap_tail.reporting.tables",
        "n225_open_gap_tail.reporting.latex",
        "n225_open_gap_tail.reporting.figures",
        "n225_open_gap_tail.forecasting._guards",
        "n225_open_gap_tail.forecasting._benchmark_suite",
        "n225_open_gap_tail.forecasting._ml_tail_suite",
        "n225_open_gap_tail.forecasting.evaluation",
        "n225_open_gap_tail.forecasting.artifacts",
        "n225_open_gap_tail.models.benchmark_advanced_math",
        "n225_open_gap_tail.models.benchmark_advanced_stateful",
        "n225_open_gap_tail.metrics.result_matrix_grouping",
        "n225_open_gap_tail.metrics.result_matrix_scoring",
        "n225_open_gap_tail.metrics.result_matrix_notes",
        "n225_open_gap_tail.metrics.stat_utils",
        "n225_open_gap_tail.diagnostics.git",
    )
    for module_name in dict.fromkeys(module_names):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            monkeypatch.setattr(module, name, value)


def _with_panel_signature_fields(row: dict[str, object]) -> dict[str, object]:
    forecast_date = str(row["forecast_date"])
    current = datetime.fromisoformat(forecast_date)
    realized_loss = float(row.get("realized_loss") or 0.0)
    return {
        **row,
        "target_open_ts_utc": row.get("target_open_ts_utc")
        or datetime(current.year, current.month, current.day, 23, 45, tzinfo=UTC),
        "model_cutoff_ts_utc": row.get("model_cutoff_ts_utc")
        or datetime(current.year, current.month, current.day, 21, 0, tzinfo=UTC),
        "gap_t": row.get("gap_t", -realized_loss),
        "forecast_sample": row.get("forecast_sample", True),
        "forecast_sample_reason": row.get("forecast_sample_reason"),
        "target_clean_sample": row.get("target_clean_sample", True),
        "join_miss_reason": row.get("join_miss_reason"),
        "mapping_status": row.get("mapping_status", "normal_trading"),
    }


def test_advanced_benchmark_monthly_refit_uses_first_valid_panel_date() -> None:
    rows = [
        {"forecast_date": "2026-01-30", "clean_sample": True, "realized_loss": 0.01},
        {"forecast_date": "2026-02-03", "clean_sample": True, "realized_loss": 0.02},
        {"forecast_date": "2026-02-04", "clean_sample": True, "realized_loss": 0.03},
        {"forecast_date": "2026-03-02", "clean_sample": True, "realized_loss": 0.04},
        {"forecast_date": "2026-03-03", "clean_sample": False, "realized_loss": 0.05},
    ]

    assert benchmark_advanced.benchmark_advanced_refit_dates(
        rows,
        oos_start="2026-02-01",
    ) == ["2026-02-03", "2026-03-02"]


def test_advanced_gas_contract_records_raw_score_scaling_and_failure_status() -> None:
    _, diagnostics, _ = benchmark_advanced._forecast_stateful_sequence(
        rows=[
            {"forecast_date": "2026-01-02", "clean_sample": True, "realized_loss": 0.01},
            {"forecast_date": "2026-01-03", "clean_sample": True, "realized_loss": 0.02},
        ],
        model_name="gas_t_location_scale",
        tail_level=0.95,
        oos_start="2026-01-03",
    )

    diagnostic = diagnostics[0]
    assert diagnostic["score_scaling"] == "raw_student_t_log_scale_score"
    assert diagnostic["state_variable"] == "log_sigma"
    assert diagnostic["invalid_state_status"] == "unavailable_gas_filter_failed"

    failure = benchmark_advanced._gas_filter_failure_record(
        model_name="gas_t_location_scale",
        tail_level=0.95,
        failure_reason="nonfinite_raw_student_t_log_scale_score",
    )
    assert failure["fit_status"] == "unavailable_gas_filter_failed"
    assert failure["score_scaling"] == "raw_student_t_log_scale_score"
    assert failure["state_variable"] == "log_sigma"


def test_derivative_free_optimizer_runs_bounded_restarts_on_flat_objective() -> None:
    result = advanced_math._run_derivative_free_optimizer(
        objective=lambda params: 1.0,
        x0=np.array([1.0, 0.5]),
        model_name="caviar_sav",
        tail_level=0.95,
        forecast_date="2026-01-05",
    )

    assert result["restart_count"] == paper_module.ADVANCED_OPTIMIZER_MAX_RESTARTS
    assert result["restart_reason"] == "no_optimizer_improvement"
    assert result["initial_objective_value"] == 1.0


def test_care_expectile_calibration_uses_training_window_only() -> None:
    oos_start = "2026-04-16"
    base_date = datetime(2023, 1, 1, tzinfo=UTC)
    training_rows = [
        {
            "forecast_date": (base_date + timedelta(days=day)).date().isoformat(),
            "clean_sample": True,
            "realized_loss": float(day % 37) / 1000.0,
        }
        for day in range(1100)
    ]
    post_oos_rows = [
        {
            "forecast_date": (datetime(2026, 4, 16, tzinfo=UTC) + timedelta(days=day))
            .date()
            .isoformat(),
            "clean_sample": True,
            "realized_loss": 100.0 + day,
        }
        for day in range(5)
    ]
    _, diagnostics, _ = benchmark_advanced._forecast_stateful_sequence(
        rows=[*training_rows, *post_oos_rows],
        model_name="care_expectile_sav",
        tail_level=0.95,
        oos_start=oos_start,
    )
    _, mutated_diagnostics, _ = benchmark_advanced._forecast_stateful_sequence(
        rows=[
            *training_rows,
            *[{**row, "realized_loss": -999.0} for row in post_oos_rows],
        ],
        model_name="care_expectile_sav",
        tail_level=0.95,
        oos_start=oos_start,
    )

    diagnostic = diagnostics[0]
    mutated = mutated_diagnostics[0]
    assert diagnostic["care_model_definition"] == "conditional_autoregressive_expectile"
    assert diagnostic["expectile_calibration_method"] == (
        paper_module.CARE_EXPECTILE_CALIBRATION_METHOD
    )
    assert diagnostic["expectile_calibration_source"] == "training_window_before_oos_start"
    assert diagnostic["expectile_calibration_status"] == "ok"
    assert diagnostic["expectile_tau"] in paper_module.CARE_EXPECTILE_GRID
    assert diagnostic["expectile_tau"] == mutated["expectile_tau"]
    assert (
        diagnostic["expectile_calibration_breach_rate"]
        == (mutated["expectile_calibration_breach_rate"])
    )


def test_care_expectile_calibration_failure_is_unavailable_not_forecast() -> None:
    calibration = benchmark_advanced._calibrate_care_expectile_tau(
        np.array([0.01, 0.02]),
        tail_level=0.95,
    )

    assert calibration["expectile_tau"] is None
    assert calibration["expectile_calibration_status"] == (
        "unavailable_care_expectile_insufficient_training_rows"
    )


def test_caviar_stateful_sequence_produces_audited_forecasts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    base_date = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "forecast_date": (base_date + timedelta(days=day)).date().isoformat(),
            "clean_sample": True,
            "realized_loss": 0.01 + (0.08 if day % 17 == 0 else float(day % 11) / 1000.0),
        }
        for day in range(80)
    ]

    forecasts, diagnostics, failures = benchmark_advanced._forecast_stateful_sequence(
        rows=rows,
        model_name="caviar_sav",
        tail_level=0.95,
        oos_start=rows[40]["forecast_date"],
    )

    assert failures == []
    assert forecasts
    assert diagnostics[0]["fit_status"] == "ok"
    assert diagnostics[0]["burn_in_rows"] == min(
        paper_module.ADVANCED_RECURSIVE_BURN_IN_ROWS,
        diagnostics[0]["train_n"] // 4,
    )
    assert diagnostics[0]["initialization_source"] in {
        "coarse_economic_grid",
        "previous_month_warm_start",
    }
    assert forecasts[0]["es_source"] == "empirical_exceedance_companion"
    assert forecasts[0]["fz_interpretation"] == "augmented_var_es_pair_not_jointly_estimated"
    assert forecasts[0]["es_forecast"] >= forecasts[0]["var_forecast"]


def test_stateful_forecast_t_does_not_use_realized_loss_t(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    base_date = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "forecast_date": (base_date + timedelta(days=day)).date().isoformat(),
            "clean_sample": True,
            "realized_loss": 0.01 + (0.12 if day % 13 == 0 else float(day % 7) / 1000.0),
        }
        for day in range(70)
    ]
    oos_start = rows[40]["forecast_date"]
    mutated = [dict(row) for row in rows]
    mutated[40]["realized_loss"] = 999.0

    forecasts, _, _ = benchmark_advanced._forecast_stateful_sequence(
        rows=rows,
        model_name="caviar_asymmetric_slope",
        tail_level=0.95,
        oos_start=oos_start,
    )
    mutated_forecasts, _, _ = benchmark_advanced._forecast_stateful_sequence(
        rows=mutated,
        model_name="caviar_asymmetric_slope",
        tail_level=0.95,
        oos_start=oos_start,
    )

    assert forecasts[0]["forecast_date"] == oos_start
    assert mutated_forecasts[0]["forecast_date"] == oos_start
    assert forecasts[0]["var_forecast"] == pytest.approx(mutated_forecasts[0]["var_forecast"])
    assert forecasts[0]["es_forecast"] == pytest.approx(mutated_forecasts[0]["es_forecast"])


@pytest.mark.parametrize(
    ("var", "es", "joint"),
    [
        (1.0, None, False),
        (1.0, math.nan, False),
        (1.0, math.inf, False),
        (1.0, 0.5, False),
        (1.0, 1.2, True),
        (math.nan, 1.2, False),
    ],
)
def test_baseline_retains_var_independently_of_es(monkeypatch, var, es, joint) -> None:
    monkeypatch.setattr(benchmark, "DEFAULT_MIN_TRAIN_ROWS", 3)
    monkeypatch.setattr(
        benchmark,
        "_forecast_one",
        lambda **kw: {"var_forecast": var, "es_forecast": es, "es_companion_type": "test"},
    )
    rows = [
        {"forecast_date": f"2026-01-{day:02d}", "realized_loss": day / 100.0} for day in range(1, 8)
    ]
    forecasts, _, failures = benchmark._forecast_model_sequence(
        rows=rows,
        model_name="historical_quantile",
        tail_side="left_tail",
        tail_level=0.95,
        oos_start="2026-01-04",
    )
    if not math.isfinite(var):
        assert not forecasts and len(failures) == 4
        return
    assert not failures and len(forecasts) == 4
    for row in forecasts:
        assert stat_utils.forecast_eligible(row)
        assert stat_utils.forecast_eligible(row, score="joint") is joint
        assert stat_utils.forecast_eligible(row, score="fz0") is joint
        assert row["es_forecast"] == (es if es is not None and math.isfinite(es) else None)


@pytest.mark.parametrize("model_name", pipeline_runtime.BENCHMARK_ADVANCED_MODEL_NAMES[:4])
def test_recursive_es_unavailable_preserves_var_and_monthly_state(monkeypatch, model_name) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 10)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1000)
    refits = []
    params = np.array([0.01, 0.5, 0.2, 0.1] if model_name.endswith("slope") else [0.01, 0.5, 0.2])

    def optimizer(**kwargs):
        refits.append(kwargs["forecast_date"])
        return {"params": params}

    monkeypatch.setattr(advanced_stateful, "_run_derivative_free_optimizer", optimizer)
    monkeypatch.setattr(
        advanced_stateful,
        "_calibrate_care_expectile_tau",
        lambda *a, **k: {"expectile_calibration_status": "ok", "expectile_tau": 0.975},
    )
    rows = [
        {
            "forecast_date": (datetime(2026, 1, 1) + timedelta(days=day)).date().isoformat(),
            "realized_loss": 0.01 * (day % 7 + 1),
        }
        for day in range(35)
    ]
    forecasts, diagnostics, failures = advanced_stateful._forecast_stateful_sequence(
        rows=rows,
        model_name=model_name,
        tail_level=0.95,
        oos_start="2026-01-28",
    )
    assert refits == ["2026-01-28", "2026-02-01"]  # No ES-driven daily retries.
    assert len(forecasts) == len(failures) == 8
    assert all(row["fit_status"] == "ok" and row["parameter_json"] for row in diagnostics)
    assert all(row["es_multiplier_exceedance_count"] is not None for row in diagnostics)
    for row in forecasts:
        assert row["es_forecast"] is None
        assert (
            row["es_failure_reason"]
            == "unavailable_empirical_es_companion_insufficient_exceedances"
        )
        assert stat_utils.forecast_eligible(row)
        assert not stat_utils.forecast_eligible(row, score="joint")
        assert not stat_utils.forecast_eligible(row, score="fz0")
    expected_next_var = advanced_math._recursive_next_var(
        q=forecasts[0]["var_forecast"],
        y=forecasts[0]["realized_loss"],
        params=params,
        variant="asymmetric_slope" if model_name.endswith("slope") else "sav",
        has_gap=False,
    )
    assert forecasts[1]["var_forecast"] == pytest.approx(expected_next_var)


@pytest.mark.parametrize("model_name", ["caviar_sav", "gas_t_location_scale"])
@pytest.mark.parametrize("es", [None, math.nan, 0.5, 1.2])
def test_advanced_sequence_preserves_raw_es_without_clipping(monkeypatch, model_name, es) -> None:
    monkeypatch.setattr(advanced_stateful, "DEFAULT_MIN_TRAIN_ROWS", 3)
    monkeypatch.setattr(
        advanced_stateful,
        "_fit_advanced_model",
        lambda **k: {
            "fit_status": "ok",
            "model_name": model_name,
            "params": np.array([]),
            "state": {
                "var": 1.0,
                "log_sigma": 0.0,
                "location": 0.0,
                "standardized_var": 1.0,
                "standardized_es": es,
            },
            "es_multiplier": es,
            "es_companion_type": "test",
        },
    )
    monkeypatch.setattr(advanced_stateful, "_update_advanced_fit_state", lambda *a: None)
    forecasts, diagnostics, failures = advanced_stateful._forecast_stateful_sequence(
        rows=[
            {"forecast_date": f"2026-01-{day:02d}", "realized_loss": 0.01} for day in range(1, 8)
        ],
        model_name=model_name,
        tail_level=0.95,
        oos_start="2026-01-04",
    )
    joint = es is not None and math.isfinite(es) and es >= 1.0
    assert len(diagnostics) == 1 and len(forecasts) == 4
    assert len(failures) == (0 if joint else 4)
    for row in forecasts:
        assert row["es_forecast"] == (es if es is not None and math.isfinite(es) else None)
        assert stat_utils.forecast_eligible(row)
        assert stat_utils.forecast_eligible(row, score="joint") is joint
        assert stat_utils.forecast_eligible(row, score="fz0") is joint


def test_advanced_nonfinite_var_does_not_erase_prior_forecasts(monkeypatch) -> None:
    monkeypatch.setattr(advanced_stateful, "DEFAULT_MIN_TRAIN_ROWS", 3)
    monkeypatch.setattr(
        advanced_stateful,
        "_fit_advanced_model",
        lambda **k: {
            "fit_status": "ok",
            "model_name": "caviar_sav",
            "params": np.array([]),
            "state": {"var": 1.0},
            "es_multiplier": 1.2,
            "es_companion_type": "test",
        },
    )
    monkeypatch.setattr(
        advanced_stateful,
        "_update_advanced_fit_state",
        lambda fit, loss: fit["state"].update(var=math.nan),
    )
    forecasts, diagnostics, failures = advanced_stateful._forecast_stateful_sequence(
        rows=[
            {"forecast_date": f"2026-01-{day:02d}", "realized_loss": 0.01} for day in range(1, 7)
        ],
        model_name="caviar_sav",
        tail_level=0.95,
        oos_start="2026-01-04",
    )
    assert [row["forecast_date"] for row in forecasts] == ["2026-01-04", "2026-01-06"]
    assert len(diagnostics) == 2
    assert failures[0]["fit_status"] == "unavailable_forecast_failed"
    assert failures[0]["forecast_date"] == "2026-01-05"


@pytest.mark.parametrize("shape", [0.2, 1.0, 1.2])
def test_external_pot_preserves_var_when_es_is_infinite(monkeypatch, shape) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 10)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 2)
    monkeypatch.setattr("scipy.stats.genpareto.fit", lambda *a, **k: (shape, 0.0, 1.0))
    train = np.linspace(-2.0, 5.0, 100)
    arch_result = SimpleNamespace(
        params={"nu": 5.0},
        convergence_flag=0,
        std_resid=-train,
        forecast=lambda **k: SimpleNamespace(
            mean=SimpleNamespace(iloc=np.array([[10.0]])),
            variance=SimpleNamespace(iloc=np.array([[10000.0]])),
        ),
    )
    monkeypatch.setattr(
        "arch.arch_model",
        lambda *a, **k: SimpleNamespace(fit=lambda **kw: arch_result),
    )
    arch_forecast = benchmark._arch_forecast(
        train=train, tail_level=0.95, model_name="gjr_garch_evt"
    )
    monkeypatch.setattr(advanced_stateful, "_profile_gas_nu", lambda train: 5.0)
    monkeypatch.setattr(
        advanced_stateful,
        "_run_derivative_free_optimizer",
        lambda **k: {"params": np.array([0.0, 0.05, 0.9, 0.0])},
    )
    monkeypatch.setattr(
        advanced_stateful,
        "_gas_filter_path",
        lambda **k: {"log_sigmas": np.zeros(len(k["train"])), "next_log_sigma": 0.0},
    )
    fit = advanced_stateful._fit_advanced_model(
        train=train,
        model_name="gas_t_pot_gpd",
        tail_level=0.95,
        forecast_date="2026-01-04",
        previous_params=None,
        gas_nu_by_year={},
    )
    assert fit["fit_status"] == "ok"
    gas_forecast = advanced_stateful._forecast_from_advanced_fit(fit)
    for row in [arch_forecast, {**gas_forecast, "es_failure_reason": fit.get("es_failure_reason")}]:
        assert math.isfinite(row["var_forecast"])
        if shape >= 1.0:
            assert row["es_forecast"] is None
            assert row["es_failure_reason"] == "unavailable_gpd_es_shape_ge_one"
        else:
            assert row["es_forecast"] > row["var_forecast"]
            assert row["es_failure_reason"] is None
    # Genuine tail-calibration failure must not fall back to Student-t or a finite ES.
    with pytest.raises(paper_module.PipelineRunError, match="insufficient"):
        benchmark._arch_forecast(
            train=train[:2],
            tail_level=0.95,
            model_name="gjr_garch_evt",
            evt_threshold_quantile=0.999,
        )
    failed_fit = advanced_stateful._fit_advanced_model(
        train=train[:2],
        model_name="gas_t_pot_gpd",
        tail_level=0.95,
        forecast_date="2026-01-04",
        previous_params=None,
        gas_nu_by_year={},
    )
    assert failed_fit["fit_status"] != "ok" and "state" not in failed_fit


def test_gas_pot_validity_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 3)

    tail = benchmark_advanced._advanced_pot_gpd_standardized_tail(
        standardized_losses=np.r_[np.linspace(-1.0, 2.0, 50), np.linspace(2.5, 5.0, 12)],
        tail_level=0.95,
        threshold_quantile=0.80,
    )
    assert tail["evt_exceedance_count"] >= 3
    assert tail["evt_scale"] > 0
    assert "gpd_unconstrained_loc_hat" in tail


def test_advanced_registry_contains_only_supported_families() -> None:
    advanced_models = tuple(pipeline_runtime.BENCHMARK_ADVANCED_MODEL_NAMES)
    assert advanced_models == (
        "caviar_sav",
        "caviar_asymmetric_slope",
        "care_expectile_sav",
        "care_expectile_asymmetric_slope",
        "gas_t_location_scale",
        "gas_t_pot_gpd",
    )


def test_advanced_helper_failure_branches_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 3)

    forecasts, diagnostics, failures = benchmark_advanced._forecast_stateful_sequence(
        rows=[],
        model_name="caviar_sav",
        tail_level=0.95,
        oos_start="2026-01-01",
    )
    assert forecasts == []
    assert failures == []
    assert diagnostics[0]["fit_status"] == "unavailable_no_clean_rows"

    with pytest.raises(paper_module.PipelineRunError):
        benchmark_advanced._recursive_var_path(
            train=np.array([]),
            params=np.array([0.01, 0.9, 0.05]),
            variant="sav",
            has_gap=False,
        )
    assert not benchmark_advanced._recursive_params_valid(
        np.array([0.01, 1.1, 0.05]),
        variant="sav",
        has_gap=False,
    )
    assert (
        benchmark_advanced._empirical_es_multiplier(
            train_losses=np.array([1.0, 2.0]),
            train_var_forecasts=np.array([10.0, 10.0]),
        )["status"]
        == "unavailable_empirical_es_companion_insufficient_exceedances"
    )
    assert (
        benchmark_advanced._gas_filter_path(
            train=np.array([]),
            params=np.array([0.0, 0.1, 0.9, 0.0]),
            nu=5.0,
        )
        is None
    )
    assert not benchmark_advanced._gas_params_valid(np.array([0.0, 5.0, 0.9, 0.0]))
    with pytest.raises(paper_module.PipelineRunError):
        benchmark_advanced._gas_next_log_sigma(
            y=1.0,
            log_sigma=0.0,
            params=np.array([0.0, 0.1, 0.9, 0.0]),
            nu=1.5,
        )
    with pytest.raises(paper_module.PipelineRunError):
        benchmark_advanced._advanced_pot_gpd_standardized_tail(
            standardized_losses=np.array([0.1, 0.2]),
            tail_level=0.95,
        )


@pytest.mark.parametrize("missing_es", [False, True])
def test_benchmark_advanced_wiring_is_nonblocking_and_sharded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing_es: bool,
) -> None:
    run_dir = tmp_path / "artifacts" / "benchmark_advanced_synthetic"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = [
        _with_panel_signature_fields(
            {
                "forecast_date": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day))
                .date()
                .isoformat(),
                "clean_sample": True,
                "realized_loss": float(day) / 100.0,
            }
        )
        for day in range(70)
    ]
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_leakage_check(run_dir=run_dir)

    _patch_paper_module(monkeypatch, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "TAIL_LEVELS", (0.95,))
    _patch_paper_module(monkeypatch, "BENCHMARK_ADVANCED_MODEL_NAMES", ("caviar_sav",))

    def fake_forecast_one(
        *,
        train: np.ndarray,
        model_name: str,
        tail_level: float,
    ) -> dict[str, object]:
        var = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var,
            "es_forecast": None if missing_es else var + 0.01,
            "es_companion_type": "synthetic_baseline",
            "optimizer_status": "ok",
            "convergence_code": 0,
        }

    def fake_stateful_sequence(
        *,
        rows: list[dict[str, object]],
        model_name: str,
        tail_level: float,
        oos_start: str,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
        clean = paper_module._clean_loss_rows(rows)
        forecasts = []
        for index, row in enumerate(clean):
            if index < 30 or str(row["forecast_date"]) < oos_start:
                continue
            realized = float(row["realized_loss"])
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "var_forecast": realized + 1.0,
                    "es_forecast": None if missing_es else realized + 1.1,
                    "es_companion_type": "synthetic_advanced",
                    "realized_loss": realized,
                    "var_breach": False,
                    "is_valid_forecast": not missing_es,
                    "invalid_reason": "invalid_nonfinite_forecast" if missing_es else None,
                    "train_n": index,
                    "fit_status": "invalid_forecast" if missing_es else "ok",
                }
            )
        return (
            forecasts,
            [
                {
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "fit_status": "ok",
                    "refit_dates_json": json.dumps(
                        benchmark_advanced.benchmark_advanced_refit_dates(
                            clean,
                            oos_start=oos_start,
                        )
                    ),
                }
            ],
            [],
        )

    _patch_paper_module(monkeypatch, "_forecast_one", fake_forecast_one)
    _patch_paper_module(monkeypatch, "_forecast_stateful_sequence", fake_stateful_sequence)

    result = evaluate_benchmark_suite(run_dir=run_dir, workers=1, tail_side="left_tail")

    assert result.status == "completed"
    forecasts = pl.read_parquet(run_dir / "forecasts" / "benchmark_forecasts.parquet")
    advanced = forecasts.filter(pl.col("benchmark_tier") == "advanced")
    assert advanced.height > 0
    assert set(advanced["refit_frequency"].to_list()) == {
        paper_module.BENCHMARK_ADVANCED_REFIT_FREQUENCY
    }
    assert (run_dir / "s" / "caviar_sav__sto__L__hist__q0950__m_state" / "f.pq").exists()
    assert (run_dir / "metrics" / "benchmark_baseline_metrics.parquet").exists()
    status = json.loads((run_dir / "metrics" / "benchmark_status.json").read_text())
    assert status["benchmark_baseline_status"] == "completed"
    assert status["benchmark_advanced_status"] == "completed_nonblocking"
    assert status["benchmark_advanced_forecast_rows"] == advanced.height
    assert status["benchmark_advanced_failures"] == 0
    metrics = pl.read_parquet(run_dir / "metrics" / "benchmark_metrics_per_model.parquet")
    assert all(count == advanced.height for count in metrics["rows"])
    if missing_es:
        assert forecasts["es_forecast"].null_count() == forecasts.height
        assert all(count == 0 for count in metrics["joint_rows"])
        assert all(count == 0 for count in metrics["fz0_rows"])


def test_benchmark_tagged_dispatch_preserves_serial_baseline_then_advanced_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts" / "benchmark_dispatch_order"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = [
        _with_panel_signature_fields(
            {
                "forecast_date": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day))
                .date()
                .isoformat(),
                "clean_sample": True,
                "realized_loss": float(day) / 100.0,
            }
        )
        for day in range(70)
    ]
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_leakage_check(run_dir=run_dir)
    _patch_paper_module(monkeypatch, "TAIL_LEVELS", (0.95,))
    _patch_paper_module(monkeypatch, "BENCHMARK_BASELINE_MODEL_NAMES", ("historical_quantile",))
    _patch_paper_module(monkeypatch, "BENCHMARK_ADVANCED_MODEL_NAMES", ("caviar_sav",))
    calls: list[str] = []

    def fake_output(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
        model_name = str(cast(tuple[str], payload["models"])[0])
        kind = str(payload["shard_kind"])
        calls.append(kind)
        forecasts = [
            {
                "forecast_date": (datetime(2026, 2, 1, tzinfo=UTC) + timedelta(days=day))
                .date()
                .isoformat(),
                "model_name": model_name,
                "target_family": "full_gap_settle_to_open",
                "tail_side": payload.get("tail_side"),
                "information_set": "target_history_only",
                "tail_level": 0.95,
                "refit_frequency": None
                if kind == "baseline"
                else paper_module.BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                "benchmark_tier": kind,
                "var_forecast": 1.0,
                "es_forecast": 1.1,
                "realized_loss": float(day) / 100.0,
                "var_breach": False,
                "is_valid_forecast": True,
                "invalid_reason": None,
                "fit_status": "ok",
            }
            for day in range(30)
        ]
        return {"forecasts": forecasts, "diagnostics": [], "failures": []}

    monkeypatch.setattr(benchmark_suite, "_evaluate_benchmark_shard", fake_output)
    monkeypatch.setattr(benchmark_suite, "_evaluate_benchmark_advanced_shard", fake_output)

    evaluate_benchmark_suite(run_dir=run_dir, workers=1)

    assert calls == ["baseline", "baseline", "advanced", "advanced"]
    status = json.loads((run_dir / "metrics" / "benchmark_status.json").read_text())
    assert status["benchmark_baseline_forecast_rows"] == 60
    assert status["benchmark_advanced_forecast_rows"] == 60


def test_benchmark_baseline_suite_skips_advanced_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts" / "benchmark_baseline_only"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = [
        _with_panel_signature_fields(
            {
                "forecast_date": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day))
                .date()
                .isoformat(),
                "clean_sample": True,
                "realized_loss": float(day) / 100.0,
            }
        )
        for day in range(70)
    ]
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_leakage_check(run_dir=run_dir)

    _patch_paper_module(monkeypatch, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "TAIL_LEVELS", (0.95,))

    def fake_forecast_one(
        *,
        train: np.ndarray,
        model_name: str,
        tail_level: float,
    ) -> dict[str, object]:
        var = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var,
            "es_forecast": var + 0.01,
            "es_companion_type": "synthetic_baseline",
            "optimizer_status": "ok",
            "convergence_code": 0,
        }

    _patch_paper_module(monkeypatch, "_forecast_one", fake_forecast_one)

    result = evaluate_suite(run_dir=run_dir, workers=1, suite="benchmark-baseline")

    assert result.status == "completed"
    forecasts = pl.read_parquet(run_dir / "forecasts" / "benchmark_forecasts.parquet")
    assert set(forecasts["benchmark_tier"].to_list()) == {"baseline"}
    status = json.loads((run_dir / "metrics" / "benchmark_status.json").read_text())
    assert status["benchmark_advanced_status"] == "skipped_benchmark_baseline_suite"
    assert status["benchmark_advanced_model_count"] == 0
