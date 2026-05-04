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
import n225_open_gap_tail.metrics.cpa as cpa_module
import n225_open_gap_tail.metrics.stat_utils as stat_utils
import n225_open_gap_tail.models.benchmark_advanced as benchmark_advanced
import n225_open_gap_tail.models.benchmark_advanced_math as advanced_math
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
    evaluate_benchmark_floor_suite,
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


def _patch_paper_module(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> None:
    for module in [
        paper_module,
        paper_core,
        paper_evaluation,
        paper_features,
        paper_leakage,
        paper_panel,
        paper_reporting,
        paper_inference,
        paper_cache,
        pipeline_runtime,
        artifact_utils,
        stat_utils,
        benchmark_suite,
        ml_tail_suite,
        reporting_tables,
        reporting_latex,
        reporting_figures,
        cpa_module,
        benchmark_advanced,
        advanced_math,
    ]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)

    owner_map = {
        "PANEL_DIR": artifact_utils,
        "REPORTS_DIR": artifact_utils,
        "PIPELINE_CONFIG": pipeline_runtime,
        "BOOTSTRAP_REPS": pipeline_runtime,
        "BOOTSTRAP_SEED": pipeline_runtime,
        "MCS_ALPHA": pipeline_runtime,
        "MCS_MAX_MODELS": pipeline_runtime,
        "MCS_MIN_MODELS": pipeline_runtime,
        "MCS_MIN_OBS": pipeline_runtime,
        "MCS_BLOCK_LENGTH": pipeline_runtime,
        "MCS_REPS": pipeline_runtime,
        "MIN_TAIL_EXCEPTIONS_FOR_INFERENCE": pipeline_runtime,
        "MIN_COMMON_ROWS_FOR_INFERENCE": pipeline_runtime,
        "MODEL_CONFIDENCE_LEVEL": pipeline_runtime,
    }
    owner = owner_map.get(name)
    if owner is not None:
        monkeypatch.setattr(owner, name, value)


def _ml_tail_result_matrix_forecasts(
    *,
    dates: list[str],
    information_sets: tuple[str, ...] = (
        "japan_only",
        "japan_only_plus_us_close_core",
    ),
    with_exceptions: bool = True,
    include_es: bool = True,
) -> list[dict[str, object]]:
    forecasts: list[dict[str, object]] = []
    for model_index, model_name in enumerate(paper_module.ML_TAIL_MODEL_NAMES):
        for info_index, information_set in enumerate(information_sets):
            for index, forecast_date in enumerate(dates):
                realized_loss = 1.0 if with_exceptions and index % 10 == 0 else 0.10
                var_forecast = 0.45 + model_index * 0.05 + info_index * 0.01
                row: dict[str, object] = {
                    "forecast_date": forecast_date,
                    "target_family": "full_gap_settle_to_open",
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": 0.95,
                    "refit_frequency": "monthly",
                    "realized_loss": realized_loss,
                    "var_forecast": var_forecast,
                    "es_forecast": var_forecast + 0.25 if include_es else None,
                    "fit_status": "ok",
                    "is_valid_forecast": True,
                }
                forecasts.append(row)
    return forecasts


def test_ml_tail_result_matrix_separates_var_and_var_es_layers() -> None:
    dates = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(130)
    ]
    artifacts = paper_module.build_ml_tail_result_matrix_artifacts(
        _ml_tail_result_matrix_forecasts(dates=dates)
    )

    matrix = cast(list[dict[str, object]], artifacts["matrix"])
    dm = cast(list[dict[str, object]], artifacts["dm"])
    mcs = cast(list[dict[str, object]], artifacts["mcs"])
    notes = cast(str, artifacts["notes"])

    tail_var_rows = [
        row
        for row in matrix
        if row["comparison_axis"] == "model_family"
        and row["loss_family"] == "var_quantile_loss"
        and row["information_set"] == "japan_only"
    ]
    assert {row["model_name"] for row in tail_var_rows} == set(paper_module.ML_TAIL_MODEL_NAMES)
    assert all(row["sample_policy"] == "restricted_tail_model_common_sample" for row in matrix)
    assert all(row["headline_claim_allowed"] is False for row in matrix)
    assert any(row["loss_family"] == "var_es_fz_loss" for row in matrix)
    assert any(row["loss_family"] == "var_coverage" for row in matrix)
    assert any(row["comparison_axis"] == "information_set_increment" for row in matrix)
    assert any(row["comparison_family"] == "information_set_ladder" for row in matrix)
    assert any(row["inference_status"] == "ok_block_bootstrap_dm" for row in dm)
    assert all(
        row["mcs_status"] == "unavailable_insufficient_common_rows_for_inference"
        for row in mcs
        if row["loss_family"] != "var_coverage"
    )
    assert all(
        row["mcs_status"] == "unavailable_descriptive_coverage_metric"
        for row in mcs
        if row["loss_family"] == "var_coverage"
    )
    assert "conditional predictive ability" not in notes
    assert "instrumented conditional predictive ability" not in notes
    assert "dominates" not in notes
    assert "significantly outperforms" not in notes
    assert "best" not in notes.lower()


def test_ml_tail_result_matrix_gates_sparse_tail_events_and_var_es_eligibility() -> None:
    dates = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(130)
    ]
    sparse = paper_module.build_ml_tail_result_matrix_artifacts(
        _ml_tail_result_matrix_forecasts(dates=dates, with_exceptions=False)
    )
    sparse_matrix = cast(list[dict[str, object]], sparse["matrix"])
    sparse_dm = cast(list[dict[str, object]], sparse["dm"])

    assert any(row["zero_exception_flag"] is True for row in sparse_matrix)
    assert any(
        row["inference_status"] == "unavailable_insufficient_tail_events_for_inference"
        for row in sparse_dm
    )

    no_es = paper_module.build_ml_tail_result_matrix_artifacts(
        _ml_tail_result_matrix_forecasts(dates=dates, include_es=False)
    )
    no_es_matrix = cast(list[dict[str, object]], no_es["matrix"])

    assert {row["loss_family"] for row in no_es_matrix} == {
        "var_quantile_loss",
        "var_coverage",
    }


def test_ml_tail_result_matrix_marks_short_common_samples_unavailable() -> None:
    dates = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(20)
    ]
    forecasts = _ml_tail_result_matrix_forecasts(dates=dates, information_sets=("japan_only",))
    forecasts.append(
        {
            **forecasts[0],
            "model_name": "unregistered_lightgbm_variant",
            "forecast_date": dates[0],
        }
    )

    artifacts = paper_module.build_ml_tail_result_matrix_artifacts(forecasts)
    matrix = cast(list[dict[str, object]], artifacts["matrix"])
    audit = cast(list[dict[str, object]], artifacts["sample_audit"])

    assert matrix
    assert all(
        row["metric_status"] == "unavailable_insufficient_common_rows_for_metrics" for row in matrix
    )
    assert all(row["model_name"] != "unregistered_lightgbm_variant" for row in matrix)
    assert all(row["comparison_axis"] == "model_family" for row in matrix)
    assert all(
        row["dm_gate_status"] == "unavailable_insufficient_common_rows_for_inference"
        for row in audit
        if row["loss_family"] != "var_coverage"
    )


def test_ml_tail_result_matrix_runs_registered_mcs_when_gates_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(260)
    ]
    _patch_paper_module(monkeypatch, "BOOTSTRAP_REPS", 19)
    artifacts = paper_module.build_ml_tail_result_matrix_artifacts(
        _ml_tail_result_matrix_forecasts(dates=dates, information_sets=("japan_only",))
    )
    mcs = cast(list[dict[str, object]], artifacts["mcs"])

    assert any(row["mcs_status"] == "ok" for row in mcs)
    assert any(row["method_note"] == "hln_tmax_moving_block_bootstrap" for row in mcs)
    assert any(row["included_in_mcs"] is True for row in mcs)
    assert any(
        row["mcs_status"] == "unavailable_descriptive_coverage_metric"
        for row in mcs
        if row["loss_family"] == "var_coverage"
    )
