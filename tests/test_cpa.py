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


def _cpa_loss_matrix_rows(
    *,
    count: int,
    tail_side: str = "left_tail",
    model_name: str | None = None,
    include_vix: bool = True,
    include_es: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    anchor_information_set = (
        pipeline_runtime.PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set
    )
    candidate_information_set = "japan_only_plus_us_close_core"
    model = model_name or paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL
    for index in range(count):
        forecast_date = (
            (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        )
        vix_value = 18.0 + float(index % 7) if include_vix else None
        regime = "EDT" if index % 2 else "EST"
        absorption = (
            "post_us_close_night_absorption" if index % 3 else "near_coincident_us_japan_close"
        )
        common = {
            "forecast_date": forecast_date,
            "target_family": "full_gap_settle_to_open",
            "tail_side": tail_side,
            "model_name": model,
            "tail_level": 0.95,
            "refit_frequency": paper_module.ML_TAIL_REFIT_FREQUENCY,
            "realized_loss": 1.0 if index % 17 == 0 else 0.1,
            "var_forecast": 0.5,
            "fit_status": "ok",
            "is_valid_forecast": True,
            "vix_level": vix_value,
            "dst_regime": regime,
            "absorption_regime": absorption,
        }
        if include_es:
            common["es_forecast"] = 0.9
            common["es_companion_type"] = "joint_var_es_model"
        anchor_loss = 0.22 + float(index % 5) / 1000.0
        candidate_loss = 0.20 + float(index % 11) / 1200.0
        rows.append(
            {
                **common,
                "information_set": anchor_information_set,
                "quantile_loss": anchor_loss,
                "es_forecast": 0.9 if include_es else None,
            }
        )
        rows.append(
            {
                **common,
                "information_set": candidate_information_set,
                "quantile_loss": candidate_loss,
                "es_forecast": 0.8 if include_es else None,
            }
        )
    return rows


def test_ml_tail_cpa_v1_runs_two_sided_direct_quantile_information_ladder() -> None:
    records = paper_module.build_ml_tail_cpa_inference_records(
        [
            *_cpa_loss_matrix_rows(count=150),
            *_cpa_loss_matrix_rows(count=150, tail_side="right_tail"),
            *_cpa_loss_matrix_rows(
                count=150,
                model_name=paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
                include_es=True,
            ),
        ]
    )

    core_record = next(
        row
        for row in records
        if row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )

    assert core_record["tail_side"] == "left_tail"
    assert core_record["model_name"] == paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL
    assert core_record["loss_family"] == "var_quantile_loss"
    assert core_record["claim_scope"] == "conditional_inference_diagnostic_not_headline"
    assert core_record["headline_claim_allowed"] is False
    assert core_record["inference_status"] == "ok_newey_west_hac_wald_cpa"
    assert core_record["common_n"] == 150
    assert core_record["effective_n"] == 149
    assert core_record["dropped_missing_instrument_rows"] == 1
    assert core_record["dropped_missing_loss_rows"] == 0
    assert core_record["hac_kernel"] == "bartlett"
    assert core_record["hac_lags"] == math.floor(4 * (149 / 100) ** (2 / 9))
    assert core_record["wald_pvalue"] is not None
    assert "lagged_loss_diff" in json.loads(str(core_record["instruments_json"]))
    assert {row["tail_side"] for row in records} == {"left_tail", "right_tail"}
    assert {row["loss_family"] for row in records} == {"var_quantile_loss", "var_es_fz_loss"}
    fz_record = next(
        row
        for row in records
        if row["model_name"] == paper_module.ML_TAIL_LOCATION_SCALE_MODEL
        and row["loss_family"] == "var_es_fz_loss"
        and row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )
    assert fz_record["inference_status"] == "ok_newey_west_hac_wald_cpa"
    assert fz_record["regression_formula"].startswith("candidate_minus_anchor_fz_loss")


def test_ml_tail_cpa_v1_gates_scope_and_instruments() -> None:
    right_records = paper_module.build_ml_tail_cpa_inference_records(
        _cpa_loss_matrix_rows(count=150, tail_side="right_tail")
    )
    assert {row["tail_side"] for row in right_records} == {"right_tail"}
    assert {row["loss_family"] for row in right_records} == {"var_quantile_loss"}

    assert (
        paper_module.build_ml_tail_cpa_inference_records(
            _cpa_loss_matrix_rows(count=150, model_name=paper_module.ML_TAIL_LOCATION_SCALE_MODEL)
        )
        == []
    )

    short_records = paper_module.build_ml_tail_cpa_inference_records(
        _cpa_loss_matrix_rows(count=30)
    )
    short_core = next(
        row
        for row in short_records
        if row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )
    assert short_core["inference_status"] == "unavailable_insufficient_effective_rows_for_cpa"
    assert short_core["wald_pvalue"] is None

    no_vix_records = paper_module.build_ml_tail_cpa_inference_records(
        _cpa_loss_matrix_rows(count=150, include_vix=False)
    )
    no_vix_core = next(
        row
        for row in no_vix_records
        if row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )
    dropped = json.loads(str(no_vix_core["dropped_instruments_json"]))
    assert {"instrument": "vix_level", "drop_reason": "nonfinite_or_missing"} in dropped
    assert no_vix_core["inference_status"] == "ok_newey_west_hac_wald_cpa"


def test_ml_tail_cpa_defensive_branches_and_forecast_quantile_fallback(tmp_path: Path) -> None:
    assert cpa_module._cpa_quantile_loss(
        {"realized_loss": 1.0, "var_forecast": 0.8, "tail_level": 0.95}
    ) == pytest.approx(quantile_loss(1.0, 0.8, 0.95))
    assert cpa_module._cpa_quantile_loss({"realized_loss": 1.0}) is None
    assert cpa_module._cpa_hac_lags(1) == 0

    anchor_only = [
        row
        for row in _cpa_loss_matrix_rows(count=3)
        if row["information_set"]
        == pipeline_runtime.PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set
    ]
    missing_candidate = paper_module.build_ml_tail_cpa_inference_records(anchor_only)
    assert {row["inference_status"] for row in missing_candidate} == {
        "unavailable_missing_anchor_or_candidate_sample"
    }

    constant_rows = []
    for row in _cpa_loss_matrix_rows(count=150):
        constant_rows.append(
            {
                **row,
                "quantile_loss": 0.1,
                "vix_level": 20.0,
                "dst_regime": "EST",
                "absorption_regime": "coincident_us_ose_night_close",
            }
        )
    no_instruments = paper_module.build_ml_tail_cpa_inference_records(constant_rows)
    no_instrument_core = next(
        row
        for row in no_instruments
        if row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )
    assert no_instrument_core["inference_status"] == "unavailable_no_nonconstant_instruments"

    stale = tmp_path / "benchmark_right_robustness_table.tex"
    stale.write_text("old", encoding="utf-8")
    reporting_tables._remove_stale_tail_table_names(tmp_path)
    assert not stale.exists()


def test_cross_model_cpa_registered_pairs_and_fz_gates() -> None:
    ml_tail_rows = [
        *_cpa_loss_matrix_rows(count=150),
        *_cpa_loss_matrix_rows(
            count=150,
            model_name=paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
            include_es=True,
        ),
    ]
    benchmark_rows: list[dict[str, object]] = []
    for row in _cpa_loss_matrix_rows(count=150, model_name="garch_t", include_es=True):
        if row["information_set"] == "japan_only_plus_us_close_core":
            continue
        benchmark_rows.append(
            {
                **row,
                "information_set": "target_history_only",
                "refit_frequency": "monthly",
                "es_companion_type": "analytical_student_t_es",
            }
        )
    for row in _cpa_loss_matrix_rows(count=150, model_name="caviar_sav", include_es=True):
        if row["information_set"] == "japan_only_plus_us_close_core":
            continue
        benchmark_rows.append(
            {
                **row,
                "information_set": "target_history_only",
                "refit_frequency": paper_module.BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                "es_source": "empirical_exceedance_companion",
                "fz_interpretation": "augmented_var_es_pair_not_jointly_estimated",
            }
        )

    records = cpa_module.build_cross_model_cpa_inference_records(
        ml_tail_forecasts=ml_tail_rows,
        benchmark_forecasts=benchmark_rows,
    )

    assert {row["comparison_axis"] for row in records} == {"cross_model_registered_pair"}
    assert any(row["loss_family"] == "var_quantile_loss" for row in records)
    fz_records = [row for row in records if row["loss_family"] == "var_es_fz_loss"]
    assert fz_records
    assert {row["anchor_model_name"] for row in fz_records} == {"garch_t"}
    fz_core = next(
        row
        for row in fz_records
        if row["candidate_information_set"] == "japan_only_plus_us_close_core"
    )
    assert fz_core["candidate_model_name"] == paper_module.ML_TAIL_LOCATION_SCALE_MODEL
    assert fz_core["anchor_refit_frequency"] == "monthly"
    assert fz_core["candidate_refit_frequency"] == paper_module.ML_TAIL_REFIT_FREQUENCY
    assert fz_core["effective_n"] == 149
    assert fz_core["inference_status"] == "ok_newey_west_hac_wald_cpa"

    skipped = cpa_module.build_cross_model_cpa_inference_records(
        ml_tail_forecasts=ml_tail_rows,
        benchmark_forecasts=[],
    )
    assert skipped[0]["inference_status"] == "skipped_missing_benchmark_forecasts"
