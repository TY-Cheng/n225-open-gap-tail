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
import n225_open_gap_tail.forecasting._ml_tail_shards as ml_tail_shards
import n225_open_gap_tail.forecasting._ml_tail_suite as ml_tail_suite
import n225_open_gap_tail.inference as paper_inference
import n225_open_gap_tail.metrics.stat_utils as stat_utils
import n225_open_gap_tail.models.benchmark as benchmark_models
import n225_open_gap_tail.models.benchmark_advanced as benchmark_advanced
import n225_open_gap_tail.models.benchmark_advanced_math as advanced_math
import n225_open_gap_tail.models.ml_tail as ml_tail_models
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


def _synthetic_ml_tail_location_scale_rows(n: int = 90) -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(n):
        current = start + timedelta(days=index)
        seasonal = math.sin(index / 3.0)
        loss = 0.04 + 0.01 * seasonal + (0.09 if index % 17 == 0 else 0.0)
        rows.append(
            {
                "forecast_date": current.date().isoformat(),
                "target_family": "full_gap_settle_to_open",
                "clean_sample": True,
                "realized_loss": loss,
                "gap_t": -loss,
                "dst_regime": "EDT" if index % 2 else "EST",
                "absorption_regime": "post_us_close_night_absorption",
                "feature_x": float(index) / 10.0,
                "feature_cycle": float(index % 5),
            }
        )
    return rows


def test_ml_tail_marks_active_feature_missing_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 5)
    rows = []
    for day in range(1, 9):
        rows.append(
            {
                "forecast_date": f"2026-04-{day:02d}",
                "target_family": "full_gap_settle_to_open",
                "clean_sample": True,
                "realized_loss": 0.01 + day / 1000.0,
                "feature_x": None if day == 6 else float(day),
            }
        )

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=rows,
        model_name=paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x"],
        tail_level=0.95,
        oos_start="2026-04-06",
    )

    assert any(
        row["fit_status"] == "unavailable_feature_not_valid_at_cutoff"
        for row in result["forecasts"]
    )


def test_ml_tail_feature_unavailability_artifacts_aggregate_and_explode_dates() -> None:
    forecasts = [
        {
            "forecast_date": "2026-04-06",
            "target_family": "full_gap_settle_to_open",
            "model_name": "lightgbm_direct_quantile",
            "information_set": "japan_only_plus_us_close_core",
            "tail_level": 0.95,
            "fit_status": "unavailable_feature_not_valid_at_cutoff",
            "failure_reason": "spy_late_volume_surge,fred_dgs10_level",
            "dst_regime": "EDT",
            "absorption_regime": "post_us_close_night_absorption",
        },
        {
            "forecast_date": "2026-04-07",
            "target_family": "full_gap_settle_to_open",
            "model_name": "lightgbm_direct_quantile",
            "information_set": "japan_only_plus_us_close_core",
            "tail_level": 0.95,
            "fit_status": "ok",
            "failure_reason": None,
        },
    ]

    aggregate = paper_module.build_ml_tail_feature_unavailability_records(forecasts)
    exploded = paper_module.build_ml_tail_feature_unavailability_date_records(forecasts)

    by_feature = {row["feature"]: row for row in aggregate}
    assert by_feature["spy_late_volume_surge"]["missing_count"] == 1
    assert by_feature["spy_late_volume_surge"]["missing_rate"] == 0.5
    assert by_feature["fred_dgs10_level"]["source_block"] == "fred_core"
    assert {row["feature"] for row in exploded} == {
        "spy_late_volume_surge",
        "fred_dgs10_level",
    }
    assert all(row["forecast_date"] == "2026-04-06" for row in exploded)


def test_blocked_expanding_oof_folds_are_strictly_past_to_future() -> None:
    folds = paper_core._blocked_expanding_oof_folds(
        30,
        n_splits=4,
        min_train_rows=10,
    )

    assert folds
    for train_index, validation_index in folds:
        assert train_index
        assert validation_index
        assert max(train_index) < min(validation_index)
    assert folds[0][0] == list(range(10))


def test_ml_tail_oof_location_scale_smearing_is_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lightgbm as lgb

    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    oof = paper_core._ml_tail_oof_location_scale(
        train_rows=_synthetic_ml_tail_location_scale_rows(70),
        candidate_features=["feature_x", "feature_cycle"],
        information_set="japan_only_plus_us_close_core",
        tail_level=0.95,
        lgb=lgb,
    )

    assert cast(int, oof["location_oof_count"]) > 0
    assert cast(int, oof["scale_oof_count"]) > 0
    assert cast(float, oof["smearing_factor"]) > 0
    standardized = cast(np.ndarray, oof["standardized_losses"])
    assert standardized.size > 0
    assert np.isfinite(standardized).all()


def test_ml_tail_location_scale_sequence_outputs_valid_forecasts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(80),
        model_name=paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["es_companion_type"] == "oof_filtered_historical_standardized_es"
    assert cast(float, ok[0]["es_forecast"]) >= cast(float, ok[0]["var_forecast"])
    assert cast(float, ok[0]["scale_forecast"]) > 0
    assert cast(float, ok[0]["scale_smearing_factor"]) > 0
    assert ok[0]["standardization_method"] == "blocked_expanding_oof_location_scale_duan_smearing"


def test_ml_tail_standardized_pot_gpd_sequence_records_evt_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name=paper_module.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["es_companion_type"] == "oof_standardized_loss_pot_gpd"
    assert ok[0]["evt_variant"] == "plain_mle"
    assert ok[0]["evt_shape_method"]
    assert ok[0]["evt_shape"] == pytest.approx(0.1)
    assert ok[0]["evt_scale"] == pytest.approx(1.0)
    assert ok[0]["threshold_value"] is not None
    assert cast(float, ok[0]["es_forecast"]) >= cast(float, ok[0]["var_forecast"])


def test_ml_tail_unibm_pot_gpd_uses_unibm_slope_as_gpd_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)

    def fake_gpd_fit(*args: object, **kwargs: object) -> tuple[float, float, float]:
        fixed_shape = kwargs.get("f0")
        if fixed_shape is not None:
            return (float(fixed_shape), 0.0, 2.0)
        return (0.40, 0.0, 1.0)

    monkeypatch.setattr("n225_open_gap_tail.forecasting.stats.genpareto.fit", fake_gpd_fit)
    observed_sample_sizes: list[int] = []

    def fake_unibm(sample: np.ndarray) -> dict[str, object]:
        observed_sample_sizes.append(int(np.asarray(sample).size))
        return {
            "status": "ok",
            "primary_estimator": "unibm_block_quantile_scaling",
            "xi_evi_anchor": 0.25,
            "quantile": 0.5,
            "n_obs": int(np.asarray(sample).size),
            "min_block_size": 5,
            "max_block_size": 9,
            "sliding": True,
            "bootstrap_reps": 0,
            "plateau_block_sizes": [5, 6, 7, 8, 9],
            "plateau_block_counts": [85, 84, 83, 82, 81],
            "plateau_point_count": 5,
        }

    monkeypatch.setattr(benchmark_models, "_estimate_unibm_evi_anchor", fake_unibm)

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name=paper_module.ML_TAIL_POT_GPD_UNIBM_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert observed_sample_sizes
    assert observed_sample_sizes[0] > cast(int, ok[0]["evt_exceedance_count"])
    assert ok[0]["evt_variant"] == "unibm"
    assert ok[0]["evt_shape_method"] == "unibm_block_maxima_xi_fixed_shape_scale_refit"
    assert ok[0]["evt_shape_mle"] == pytest.approx(0.40)
    assert ok[0]["evt_shape"] == pytest.approx(0.25)
    assert ok[0]["evt_shape_bin"] == "[0,0.75)"
    assert ok[0]["evt_scale"] == pytest.approx(2.0)
    assert ok[0]["evt_evi_status"] == "ok"
    assert ok[0]["evt_ei_status"] == "not_used"
    assert ok[0]["evt_unibm_n_obs"] == observed_sample_sizes[0]
    assert ok[0]["evt_unibm_sliding_blocks"] is True


def test_ml_tail_standardized_pot_gpd_shape_above_one_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lightgbm as lgb

    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (1.2, 0.0, 1.0),
    )

    with pytest.raises(paper_module.PipelineRunError, match="unavailable_evt_shape_es_infinite"):
        paper_core._fit_ml_tail_location_scale_bundle(
            train_rows=_synthetic_ml_tail_location_scale_rows(80),
            candidate_features=["feature_x", "feature_cycle"],
            model_name=paper_module.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
            information_set="japan_only_plus_us_close_core",
            tail_level=0.95,
            lgb=lgb,
        )


def test_ml_tail_robust_pot_gpd_requires_tail_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lightgbm as lgb

    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)

    with pytest.raises(
        paper_module.PipelineRunError,
        match="unavailable_evt_tail_not_above_threshold",
    ):
        ml_tail_models._fit_ml_tail_robust_location_scale_bundle(
            train_rows=_synthetic_ml_tail_location_scale_rows(80),
            candidate_features=["feature_x", "feature_cycle"],
            model_name=paper_module.ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
            information_set="japan_only_plus_us_close_core",
            tail_level=0.95,
            lgb=lgb,
            evt_threshold_quantile=0.95,
        )


def test_median_iqr_quantile_crossing_is_rearranged() -> None:
    q25, q50, q75, crossing_rate = paper_core._rearrange_quantile_predictions(
        np.array([3.0, 1.0]),
        np.array([2.0, 2.0]),
        np.array([1.0, 3.0]),
    )
    assert crossing_rate == pytest.approx(0.5)
    assert q25[0] <= q50[0] <= q75[0]
    assert q25[1] <= q50[1] <= q75[1]


def test_route_failure_metadata_keeps_status_taxonomy_separate() -> None:
    mad = paper_core._ml_tail_route_failure_metadata(
        "lightgbm_median_mad_pot_gpd_plain_mle",
        "unavailable_invalid_scale",
    )
    iqr = paper_core._ml_tail_route_failure_metadata(
        "lightgbm_median_iqr_pot_gpd_plain_mle",
        "unavailable_iqr_crossing_failed",
    )
    iqr_unibm = paper_core._ml_tail_route_failure_metadata(
        "lightgbm_median_iqr_pot_gpd_unibm",
        "unavailable_evt_unibm",
    )
    unknown = paper_core._ml_tail_route_failure_metadata("other", "unavailable")

    assert mad["evt_route_gate_status"] == "unavailable_invalid_scale"
    assert mad["gpd_fit_status"] is None
    assert mad["gpd_es_status"] is None
    assert iqr["scale_method"] == "conditional_iqr_q25_q75"
    assert iqr_unibm["body_filter_method"] == "conditional_median_q50"
    assert iqr_unibm["scale_method"] == "conditional_iqr_q25_q75"
    assert iqr_unibm["evt_route_gate_status"] == "unavailable_evt_unibm"
    assert unknown == {}


def test_ml_tail_median_mad_pot_gpd_sequence_records_route_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name="lightgbm_median_mad_pot_gpd_plain_mle",
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["body_filter_method"] == "conditional_median_q50"
    assert ok[0]["scale_method"] == "conditional_median_abs_residual_l1"
    assert ok[0]["scale_floor"] == pytest.approx(1e-4)
    assert ok[0]["mad_consistency_factor"] == pytest.approx(1.4826)
    assert ok[0]["gpd_fit_status"] == "ok"
    assert ok[0]["gpd_es_status"] == "ok"


def test_ml_tail_median_iqr_pot_gpd_sequence_records_crossing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name="lightgbm_median_iqr_pot_gpd_plain_mle",
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["body_filter_method"] == "conditional_median_q50"
    assert ok[0]["scale_method"] == "conditional_iqr_q25_q75"
    assert ok[0]["iqr_consistency_factor"] == pytest.approx(1.349)
    assert ok[0]["quantile_rearrangement_applied"] in {True, False}


def test_ml_tail_median_iqr_unibm_uses_iqr_route_and_unibm_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)

    def fake_gpd_fit(*args: object, **kwargs: object) -> tuple[float, float, float]:
        fixed_shape = kwargs.get("f0")
        if fixed_shape is not None:
            return (float(fixed_shape), 0.0, 2.0)
        return (0.40, 0.0, 1.0)

    monkeypatch.setattr("n225_open_gap_tail.forecasting.stats.genpareto.fit", fake_gpd_fit)
    observed_sample_sizes: list[int] = []

    def fake_unibm(sample: np.ndarray) -> dict[str, object]:
        observed_sample_sizes.append(int(np.asarray(sample).size))
        return {
            "status": "ok",
            "primary_estimator": "unibm_block_quantile_scaling",
            "xi_evi_anchor": 0.25,
            "quantile": 0.5,
            "n_obs": int(np.asarray(sample).size),
            "min_block_size": 5,
            "max_block_size": 9,
            "sliding": True,
            "bootstrap_reps": 0,
            "plateau_block_sizes": [5, 6, 7, 8, 9],
            "plateau_block_counts": [85, 84, 83, 82, 81],
            "plateau_point_count": 5,
        }

    monkeypatch.setattr(benchmark_models, "_estimate_unibm_evi_anchor", fake_unibm)

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name=paper_module.ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert observed_sample_sizes
    assert observed_sample_sizes[0] > cast(int, ok[0]["evt_exceedance_count"])
    assert ok[0]["body_filter_method"] == "conditional_median_q50"
    assert ok[0]["scale_method"] == "conditional_iqr_q25_q75"
    assert ok[0]["iqr_consistency_factor"] == pytest.approx(1.349)
    assert ok[0]["evt_variant"] == "unibm"
    assert ok[0]["evt_shape_method"] == "unibm_block_maxima_xi_fixed_shape_scale_refit"
    assert ok[0]["evt_shape_mle"] == pytest.approx(0.40)
    assert ok[0]["evt_shape"] == pytest.approx(0.25)
    assert ok[0]["evt_scale"] == pytest.approx(2.0)
    assert ok[0]["evt_unibm_n_obs"] == observed_sample_sizes[0]
    assert ok[0]["evt_unibm_sliding_blocks"] is True
    assert ok[0]["quantile_rearrangement_applied"] in {True, False}


def test_ml_tail_median_mad_unibm_uses_mad_route_and_unibm_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)

    def fake_gpd_fit(*args: object, **kwargs: object) -> tuple[float, float, float]:
        fixed_shape = kwargs.get("f0")
        if fixed_shape is not None:
            return (float(fixed_shape), 0.0, 2.0)
        return (0.40, 0.0, 1.0)

    monkeypatch.setattr("n225_open_gap_tail.forecasting.stats.genpareto.fit", fake_gpd_fit)
    observed_sample_sizes: list[int] = []

    def fake_unibm(sample: np.ndarray) -> dict[str, object]:
        observed_sample_sizes.append(int(np.asarray(sample).size))
        return {
            "status": "ok",
            "primary_estimator": "unibm_block_quantile_scaling",
            "xi_evi_anchor": 0.25,
            "quantile": 0.5,
            "n_obs": int(np.asarray(sample).size),
            "min_block_size": 5,
            "max_block_size": 9,
            "sliding": True,
            "bootstrap_reps": 0,
            "plateau_block_sizes": [5, 6, 7, 8, 9],
            "plateau_block_counts": [85, 84, 83, 82, 81],
            "plateau_point_count": 5,
        }

    monkeypatch.setattr(benchmark_models, "_estimate_unibm_evi_anchor", fake_unibm)

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(90),
        model_name=paper_module.ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert observed_sample_sizes
    assert observed_sample_sizes[0] > cast(int, ok[0]["evt_exceedance_count"])
    assert ok[0]["body_filter_method"] == "conditional_median_q50"
    assert ok[0]["scale_method"] == "conditional_median_abs_residual_l1"
    assert ok[0]["mad_consistency_factor"] == pytest.approx(1.4826)
    assert ok[0]["evt_variant"] == "unibm"
    assert ok[0]["evt_shape_method"] == "unibm_block_maxima_xi_fixed_shape_scale_refit"
    assert ok[0]["evt_shape_mle"] == pytest.approx(0.40)
    assert ok[0]["evt_shape"] == pytest.approx(0.25)
    assert ok[0]["evt_scale"] == pytest.approx(2.0)
    assert ok[0]["evt_unibm_n_obs"] == observed_sample_sizes[0]
    assert ok[0]["evt_unibm_sliding_blocks"] is True


def test_plain_pot_gpd_and_evt_diagnostics_are_deterministic() -> None:
    rng = np.random.default_rng(0)
    losses = np.concatenate(
        [
            rng.exponential(scale=0.5, size=420),
            2.0 + rng.pareto(a=2.0, size=160),
        ]
    )
    rng.shuffle(losses)

    tail = benchmark_models._pot_gpd_standardized_tail(
        standardized_losses=losses,
        tail_level=0.95,
        evt_variant="plain_mle",
        min_standardized_losses=100,
        min_exceedances=10,
        shape_cap=(-0.25, 0.75),
        shape_shrinkage_k=50.0,
    )
    assert tail["evt_variant"] == "plain_mle"
    assert tail["evt_shape_method"] == "fixed_loc_mle"
    assert tail["evt_cap_policy"] == "none"
    assert cast(float, tail["standardized_es"]) >= cast(float, tail["standardized_var"])

    evi_tail = benchmark_models._pot_gpd_standardized_tail(
        standardized_losses=losses,
        tail_level=0.95,
        evt_variant="unibm",
        min_standardized_losses=100,
        min_exceedances=10,
        shape_cap=(-0.25, 0.75),
        shape_shrinkage_k=50.0,
    )
    assert evi_tail["evt_variant"] == "unibm"
    assert evi_tail["evt_shape_method"] == "unibm_block_maxima_xi_fixed_shape_scale_refit"
    assert evi_tail["evt_cap_policy"] == "none"
    assert evi_tail["evt_ei_status"] == "not_used"
    assert evi_tail["evt_xi_evi_anchor"] == evi_tail["evt_shape"]
    assert evi_tail["evt_unibm_n_obs"] == losses.size
    assert evi_tail["evt_unibm_sliding_blocks"] is True

    threshold = float(np.quantile(losses, 0.90))
    exceedance_indices = np.flatnonzero(losses > threshold)
    excesses = losses[losses > threshold] - threshold
    evi = benchmark_models._estimate_evi_anchor(excesses)
    ei = benchmark_models._estimate_extremal_index(exceedance_indices, int(excesses.size))
    assert evi["status"] == "ok"
    assert evi["primary_estimator"] == "dedh_moment"
    assert ei["status"] == "ok"
    assert ei["primary_estimator"] == "ferro_segers"


def test_unibm_registry_name_is_restricted_diagnostic_variant() -> None:
    assert (
        pipeline_runtime.ML_TAIL_POT_GPD_UNIBM_MODEL == "lightgbm_standardized_loss_pot_gpd_unibm"
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL
        == "lightgbm_median_iqr_pot_gpd_unibm"
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL
        == "lightgbm_median_mad_pot_gpd_unibm"
    )
    assert pipeline_runtime.ML_TAIL_POT_GPD_UNIBM_MODEL in pipeline_runtime.ML_TAIL_MODEL_NAMES
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL
        in pipeline_runtime.ML_TAIL_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL
        in pipeline_runtime.ML_TAIL_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_POT_GPD_UNIBM_MODEL
        not in pipeline_runtime.ML_TAIL_PRIMARY_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL
        not in pipeline_runtime.ML_TAIL_PRIMARY_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL
        not in pipeline_runtime.ML_TAIL_PRIMARY_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL
        in pipeline_runtime.ML_TAIL_DIAGNOSTIC_MODEL_NAMES
    )
    assert (
        pipeline_runtime.ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL
        in pipeline_runtime.ML_TAIL_DIAGNOSTIC_MODEL_NAMES
    )
    old_suffix = "unibm" + "_evi_shape"
    assert all(
        old_suffix not in str(model_name) for model_name in pipeline_runtime.ML_TAIL_MODEL_NAMES
    )


def test_ml_tail_resumable_shard_manifest_reuses_complete_and_failed(tmp_path: Path) -> None:
    payload = _minimal_ml_tail_shard_payload(tmp_path)
    output = {
        "forecasts": [
            {
                "forecast_date": "2026-01-05",
                "model_name": "lightgbm_direct_quantile",
                "information_set": "japan_only",
                "tail_side": "left_tail",
                "tail_level": 0.95,
                "refit_frequency": "monthly",
            }
        ],
        "diagnostics": [
            {
                "forecast_date": "2026-01-05",
                "model_name": "lightgbm_direct_quantile",
                "information_set": "japan_only",
                "tail_side": "left_tail",
                "tail_level": 0.95,
                "refit_frequency": "monthly",
                "fit_status": "ok",
            }
        ],
        "failures": [
            {
                "forecast_date": None,
                "model_name": "lightgbm_direct_quantile",
                "information_set": "japan_only",
                "tail_side": "left_tail",
                "tail_level": 0.95,
                "fit_status": "ok",
                "failure_reason": None,
            }
        ],
    }

    ml_tail_shards._write_ml_tail_shard_atomic(payload, output, completion_state="complete")
    cached, compute = ml_tail_shards._partition_ml_tail_shard_jobs(tmp_path, [payload])
    assert cached == [payload]
    assert compute == []
    forecasts, diagnostics, failures = ml_tail_shards._load_active_ml_tail_shards(
        tmp_path, [payload]
    )
    assert forecasts[0]["shard_id"] == "ml_tail_test_shard"
    assert diagnostics[0]["shard_id"] == "ml_tail_test_shard"
    assert failures[0]["shard_id"] == "ml_tail_test_shard"

    ml_tail_shards._write_ml_tail_shard_atomic(payload, output, completion_state="failed")
    cached, compute = ml_tail_shards._partition_ml_tail_shard_jobs(tmp_path, [payload])
    assert cached == [payload]
    assert compute == []

    (tmp_path / "s" / "ml_tail_test_shard" / "f.pq").unlink()
    cached, compute = ml_tail_shards._partition_ml_tail_shard_jobs(tmp_path, [payload])
    assert cached == []
    assert compute == [payload]


def test_ml_tail_resumable_shard_stale_manifest_errors(tmp_path: Path) -> None:
    payload = _minimal_ml_tail_shard_payload(tmp_path)
    output = {"forecasts": [], "diagnostics": [], "failures": []}
    ml_tail_shards._write_ml_tail_shard_atomic(payload, output, completion_state="complete")
    status_path = tmp_path / "s" / "ml_tail_test_shard" / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["ml_tail_payload_hash"] = "stale"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(paper_module.PipelineRunError, match="Stale ML-tail shard"):
        ml_tail_shards._partition_ml_tail_shard_jobs(tmp_path, [payload])


def _minimal_ml_tail_shard_payload(tmp_path: Path) -> dict[str, object]:
    expected = {
        "shard_schema_hash": ml_tail_shards.ML_TAIL_SHARD_SCHEMA_HASH,
        "model_name": "lightgbm_direct_quantile",
        "target_family": "full_gap_settle_to_open",
        "tail_side": "left_tail",
        "tail_level": 0.95,
        "information_set": "japan_only",
        "refit_frequency": "monthly",
        "pipeline_config_hash": "cfg",
        "ml_tail_payload_hash": "payload",
        "leakage_binding_hash": "leakage",
        "panel_signature": "panel",
        "candidate_feature_hash": "features",
        "seed_policy_version": ml_tail_shards.ML_TAIL_SHARD_SEED_POLICY_VERSION,
    }
    return {
        "run_dir": str(tmp_path),
        "shard_id": "ml_tail_test_shard",
        "expected_shard_manifest": expected,
    }


def test_unibm_block_grid_and_shape_bins_are_registered() -> None:
    block_sizes = benchmark_models._unibm_block_sizes(50)
    assert block_sizes.size >= 5
    assert int(np.max(block_sizes)) <= 50
    assert int(np.min(block_sizes)) >= 2
    assert benchmark_models._evt_shape_bin(-0.6) == "(-inf,-0.5]"
    assert benchmark_models._evt_shape_bin(-0.3) == "(-0.5,-0.25]"
    assert benchmark_models._evt_shape_bin(-0.1) == "(-0.25,0)"
    assert benchmark_models._evt_shape_bin(0.25) == "[0,0.75)"
    assert benchmark_models._evt_shape_bin(0.85) == "[0.75,1)"
    assert benchmark_models._evt_shape_bin(1.2) == "[1,1.5)"
    assert benchmark_models._evt_shape_bin(1.8) == "[1.5,inf)"


def test_unibm_block_count_gate_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_maxima(values: np.ndarray, block_size: int) -> np.ndarray:
        return np.linspace(1.0, 2.0, 19)

    monkeypatch.setattr(benchmark_models, "_sliding_block_maxima", fake_maxima)
    evi = benchmark_models._estimate_unibm_evi_anchor(np.linspace(1.0, 10.0, 200))
    assert evi["status"] == "unavailable_unibm_insufficient_eligible_block_counts"
    assert evi["n_obs"] == 200
    assert evi["min_block_maxima_per_plateau_point"] == 20


def test_unibm_failure_does_not_fallback_to_plain_mle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        benchmark_models,
        "_estimate_unibm_evi_anchor",
        lambda sample: {
            "status": "unavailable_unibm_insufficient_eligible_block_counts",
            "xi_evi_anchor": None,
        },
    )
    losses = np.concatenate([np.linspace(-1.0, 1.0, 300), np.linspace(1.1, 5.0, 80)])
    with pytest.raises(paper_module.PipelineRunError, match="unavailable_evt_unibm"):
        benchmark_models._pot_gpd_standardized_tail(
            standardized_losses=losses,
            tail_level=0.95,
            evt_variant="unibm",
            min_standardized_losses=100,
            min_exceedances=10,
        )


def test_evt_route_availability_records_unibm_fail_closed_refits() -> None:
    records = ml_tail_suite._evt_route_availability_records(
        [
            {
                "target_family": "full_gap_settle_to_open",
                "tail_side": "left_tail",
                "tail_level": 0.95,
                "model_name": pipeline_runtime.ML_TAIL_POT_GPD_UNIBM_MODEL,
                "information_set": "japan_only",
                "refit_frequency": "monthly",
                "body_filter_method": "conditional_mean_l2",
                "evt_route_gate_status": "ok",
                "fit_status": "ok",
            },
            {
                "target_family": "full_gap_settle_to_open",
                "tail_side": "left_tail",
                "tail_level": 0.95,
                "model_name": pipeline_runtime.ML_TAIL_POT_GPD_UNIBM_MODEL,
                "information_set": "japan_only",
                "refit_frequency": "monthly",
                "body_filter_method": "conditional_mean_l2",
                "evt_route_gate_status": "unavailable_evt_unibm",
                "fit_status": "unavailable_evt_unibm",
            },
        ]
    )
    assert len(records) == 1
    assert records[0]["available_refits"] == 1
    assert records[0]["unavailable_refits"] == 1
    assert records[0]["availability_rate"] == pytest.approx(0.5)
    assert "unavailable_evt_unibm" in str(records[0]["status_counts_json"])


def test_unibm_fixed_shape_scale_refit_enforces_negative_shape_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        benchmark_models.stats.genpareto,
        "fit",
        lambda *args, **kwargs: (-0.5, 0.0, 1.0),
    )
    with pytest.raises(paper_module.PipelineRunError, match="support violation"):
        benchmark_models._refit_gpd_scale_fixed_shape(np.array([0.5, 3.0]), -0.5)

    losses = np.concatenate(
        [
            np.random.default_rng(4).exponential(scale=0.5, size=420),
            2.0 + np.random.default_rng(5).pareto(a=2.0, size=160),
        ]
    )
    threshold = float(np.quantile(losses, 0.90))
    exceedance_indices = np.flatnonzero(losses > threshold)
    excesses = losses[losses > threshold] - threshold
    ei = benchmark_models._estimate_extremal_index(exceedance_indices, int(excesses.size))
    assert ei["k_gaps_theta_hat"] is not None

    k_values = benchmark_models._candidate_tail_counts(excesses.size)
    ordered = np.sort(excesses)[::-1]
    dedh_path = benchmark_models._dedh_moment_path(ordered, k_values)
    hill_path = benchmark_models._hill_path(ordered, k_values)
    pickands_path = benchmark_models._pickands_path(ordered, k_values)
    assert benchmark_models._evi_path_result("dedh_moment", k_values, dedh_path)["status"] == "ok"
    assert np.isfinite(hill_path).any()
    assert pickands_path.shape == k_values.shape

    levels = np.array([8, 10, 12, 14, 16])
    stable_k, stable_window = benchmark_models._select_stable_window(
        levels,
        np.array([0.21, 0.20, 0.205, 0.203, 0.40]),
    )
    assert int(levels[0]) <= stable_k <= int(levels[-1])
    assert stable_window[0] <= stable_window[1]

    assert benchmark_models._ferro_segers_theta(np.array([1.0, 1.0, 2.0])) > 0
    assert benchmark_models._k_gaps_theta(np.array([1.0, 4.0, 8.0]), exceedance_rate=0.1)
    clipped, cap_hit = benchmark_models._clip_with_flag(1.2, (-0.25, 0.75))
    assert clipped == pytest.approx(0.75)
    assert cap_hit is True
    assert benchmark_models._cap_policy_name((-0.25, 0.75)) == "clip_-0.25_0.75"
    sensitivity = benchmark_models._evt_cap_sensitivity(
        shape_mle=1.2,
        caps=((-0.1, 0.5), (-0.25, 0.75), (-0.5, 1.0)),
    )
    assert sensitivity[-1]["shape"] == pytest.approx(1.0)
    assert sensitivity[-1]["es_available"] is False
    threshold_sensitivity = benchmark_models._evt_threshold_sensitivity(
        values=losses,
        tail_level=0.95,
        threshold_grid=(0.90, 0.925, 0.95),
        min_exceedances=10,
        evt_variant="plain_mle",
        shape_cap=(-0.25, 0.75),
        shape_shrinkage_k=50.0,
    )
    assert {row["threshold_quantile"] for row in threshold_sensitivity} == {0.90, 0.925, 0.95}
    assert any(row["status"] == "ok" for row in threshold_sensitivity)
    assert threshold_sensitivity[-1]["status"] == "not_applicable_threshold_not_below_tail_level"


def test_location_scale_empirical_and_plain_pot_share_final_backbone_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lightgbm as lgb

    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 8)
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )

    rows = _synthetic_ml_tail_location_scale_rows(90)
    empirical = paper_core._fit_ml_tail_location_scale_bundle(
        train_rows=rows,
        candidate_features=["feature_x", "feature_cycle"],
        model_name=paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
        information_set="japan_only_plus_us_close_core",
        tail_level=0.95,
        lgb=lgb,
    )
    plain_pot = paper_core._fit_ml_tail_location_scale_bundle(
        train_rows=rows,
        candidate_features=["feature_x", "feature_cycle"],
        model_name=paper_module.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
        information_set="japan_only_plus_us_close_core",
        tail_level=0.95,
        lgb=lgb,
    )

    assert empirical["location_scale_backbone_key"] == plain_pot["location_scale_backbone_key"]
    assert empirical["location_scale_location_seed"] == plain_pot["location_scale_location_seed"]
    assert empirical["location_scale_scale_seed"] == plain_pot["location_scale_scale_seed"]
    assert empirical["active_feature_hash"] == plain_pot["active_feature_hash"]


def test_evt_diagnostic_artifact_helpers_parse_json_rows() -> None:
    row = {
        "forecast_date": "2026-02-03",
        "target_family": "full_gap_settle_to_open",
        "tail_side": "left_tail",
        "tail_level": 0.95,
        "model_name": paper_module.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
        "information_set": "japan_only_plus_us_close_core",
        "refit_frequency": "monthly",
        "refit_month": "2026-02",
        "train_n": 1200,
        "oof_standardized_loss_count": 700,
        "evt_variant": "plain_mle",
        "evt_shape": 0.2,
        "evt_scale": 1.1,
        "evt_shape_mle": 0.3,
        "evt_scale_mle": 1.0,
        "evt_xi_evi_anchor": 0.1,
        "evt_cap_policy": "clip_-0.25_0.75",
        "evt_cap_hit": False,
        "evt_shape_method": "fixed_loc_mle",
        "evt_scale_refit_status": "fixed_shape_mle_completed",
        "evt_es_finite": True,
        "evt_ei_status": "ok",
        "evt_theta_hat": 0.8,
        "evt_effective_exceedance_count": 40.0,
        "evt_exceedance_count": 50,
        "evt_ei_diagnostics_json": json.dumps(
            {"primary_estimator": "ferro_segers", "k_gaps_theta_hat": 0.7}
        ),
        "evt_cap_sensitivity_json": json.dumps(
            [
                {"cap": [-0.1, 0.5], "shape": 0.2, "cap_hit": False, "es_available": True},
                {"cap": [-0.5, 1.0], "shape": 1.0, "cap_hit": True, "es_available": False},
            ]
        ),
        "evt_threshold_sensitivity_json": json.dumps(
            [
                {
                    "threshold_quantile": 0.9,
                    "status": "ok",
                    "threshold_value": 1.2,
                    "evt_exceedance_count": 50,
                    "evt_shape": 0.2,
                    "evt_scale": 1.1,
                    "standardized_var": 2.0,
                    "standardized_es": 2.5,
                    "evt_es_finite": True,
                },
                {
                    "threshold_quantile": 0.95,
                    "status": "not_applicable_threshold_not_below_tail_level",
                    "threshold_value": 2.0,
                    "evt_exceedance_count": 25,
                },
            ]
        ),
    }

    shape_rows = ml_tail_suite._evt_shape_stability_records([row])
    ei_rows = ml_tail_suite._extremal_index_records([row])
    cap_rows = ml_tail_suite._evt_cap_sensitivity_records([row])
    threshold_rows = ml_tail_suite._evt_threshold_sensitivity_records([row])
    diagnostic_variant_rows = ml_tail_suite._evt_diagnostic_variant_metric_records(
        [
            row,
            {"model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL},
            {"model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL},
        ]
    )

    assert shape_rows[0]["evt_shape_method"] == "fixed_loc_mle"
    assert ei_rows[0]["ei_primary_estimator"] == "ferro_segers"
    assert cap_rows[1]["es_available"] is False
    assert threshold_rows[0]["sensitivity_threshold_quantile"] == 0.9
    assert threshold_rows[1]["sensitivity_status"] == (
        "not_applicable_threshold_not_below_tail_level"
    )
    assert len(diagnostic_variant_rows) == 2
    assert ml_tail_suite._json_dict("{") == {}
    assert ml_tail_suite._json_dict("[]") == {}
    assert ml_tail_suite._json_list("{") == []
    assert ml_tail_suite._json_list("{}") == []


def test_evaluate_ml_tail_suite_writes_lightgbm_ladder_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "runs" / "ml_tail_synthetic"
    panel_dir = run_dir / "panel"
    audits_dir = run_dir / "audits"
    panel_dir.mkdir(parents=True)
    audits_dir.mkdir(parents=True)
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(90):
        current = start + timedelta(days=day)
        loss_magnitude = float(day % 20) / 100.0
        signed_gap = -loss_magnitude if day % 2 else loss_magnitude
        rows.append(
            _with_panel_signature_fields(
                {
                    "forecast_date": current.date().isoformat(),
                    "target_family": "full_gap_settle_to_open",
                    "clean_sample": True,
                    "realized_loss": loss_magnitude,
                    "gap_t": signed_gap,
                    "dst_regime": "EDT" if day % 2 else "EST",
                    "absorption_regime": "post_us_close_night_absorption"
                    if day % 2
                    else "coincident_us_ose_night_close",
                    "spy_return": float(day) / 1000.0,
                    "ewj_return": float(day % 7) / 1000.0,
                    "ewh_return": float(day % 5) / 1000.0,
                }
            )
        )
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    pl.DataFrame(
        [
            {"feature": "spy_return", "source_block": "us_core"},
            {"feature": "ewj_return", "source_block": "japan_proxy"},
            {"feature": "ewh_return", "source_block": "asia_proxy"},
        ]
    ).write_parquet(panel_dir / "feature_coverage.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_leakage_check(run_dir=run_dir)
    _patch_paper_module(monkeypatch, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 30)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    _patch_paper_module(monkeypatch, "TAIL_LEVELS", (0.95,))

    result = evaluate_ml_tail_suite(run_dir=run_dir, workers=1)

    assert result.status == "completed_lightgbm_ml_tail_models"
    assert (run_dir / "forecasts" / "ml_tail_forecasts.parquet").exists()
    forecasts = pl.read_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    assert forecasts["information_set"].n_unique() == 4
    assert set(forecasts["tail_side"].to_list()) == {"left_tail", "right_tail"}
    assert (run_dir / "metrics" / "ml_tail_incremental_information.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_feature_unavailability.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_feature_unavailability_dates.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_sample_audit.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet").exists()
    assert (run_dir / "metrics" / "evt_shape_stability.parquet").exists()
    assert (run_dir / "metrics" / "extremal_index_diagnostics.parquet").exists()
    assert (run_dir / "metrics" / "evt_cap_sensitivity.parquet").exists()
    assert (run_dir / "metrics" / "evt_threshold_sensitivity.parquet").exists()
    assert (run_dir / "metrics" / "evt_body_tail_diagnostics.parquet").exists()
    assert (run_dir / "metrics" / "evt_route_gate_status.parquet").exists()
    assert (run_dir / "metrics" / "evt_diagnostic_variant_metrics.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_notes.md").exists()
    result_matrix = pl.read_parquet(run_dir / "metrics" / "ml_tail_result_matrix.parquet")
    primary_metrics = pl.read_parquet(run_dir / "metrics" / "ml_tail_metrics.parquet")
    assert not set(paper_module.ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES).intersection(
        set(primary_metrics["model_name"].to_list())
    )
    assert {
        "var_quantile_loss",
        "var_coverage",
        "var_es_fz_loss",
    }.issubset(set(result_matrix["loss_family"].to_list()))
    status = json.loads((run_dir / "metrics" / "ml_tail_status.json").read_text(encoding="utf-8"))
    assert set(status["implemented_components"]) == set(paper_module.ML_TAIL_MODEL_NAMES)
    assert status["unavailable_components"] == {}
    registered_models = {
        key for key in status["registered_information_sets"] if str(key).startswith("model_")
    }
    assert registered_models == {"model_a", "model_b", "model_c", "model_d"}
    assert status["registered_information_sets"]["model_d"].endswith("plus_asia_proxy")
    assert status["evt_body_tail_diagnostic_rows"] >= 0
    assert status["evt_route_gate_status_rows"] >= 0
