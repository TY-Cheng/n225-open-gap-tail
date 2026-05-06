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
import n225_open_gap_tail.models.benchmark as benchmark_models
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
        "n225_open_gap_tail.metrics.cpa",
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
        model_name=paper_module.ML_TAIL_STANDARDIZED_POT_GPD_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["es_companion_type"] == "oof_standardized_loss_pot_gpd"
    assert ok[0]["evt_variant"] == "stabilized"
    assert ok[0]["evt_shape_method"]
    assert ok[0]["evt_shape"] == pytest.approx(0.1)
    assert ok[0]["evt_scale"] == pytest.approx(1.0)
    assert ok[0]["threshold_value"] is not None
    assert cast(float, ok[0]["es_forecast"]) >= cast(float, ok[0]["var_forecast"])


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


def test_conditional_q90_probability_uses_oof_breach_rate() -> None:
    assert paper_core._q90_excess_probability_for_tail_level(
        q90_oof_breach_rate=0.115,
        tail_level=0.95,
    ) == pytest.approx(1.0 - 0.05 / 0.115)
    assert paper_core._q90_excess_probability_for_tail_level(
        q90_oof_breach_rate=0.10,
        tail_level=0.95,
    ) == pytest.approx(0.5)
    with pytest.raises(
        paper_module.PipelineRunError,
        match="unavailable_q90_breach_rate_too_low_for_target_tail",
    ):
        paper_core._q90_excess_probability_for_tail_level(
            q90_oof_breach_rate=0.05,
            tail_level=0.95,
        )
    with pytest.raises(
        paper_module.PipelineRunError,
        match="unavailable_invalid_q90_excess_probability",
    ):
        paper_core._q90_excess_probability_for_tail_level(
            q90_oof_breach_rate=0.10,
            tail_level=1.10,
        )


def test_q90_gate_statuses_are_partitioned() -> None:
    assert paper_core._q90_gate_status(0.10) == "ok"
    assert paper_core._q90_gate_status(0.08) == "marginal_q90_calibration"
    assert paper_core._q90_gate_status(0.13) == "unavailable_q90_calibration_failed"


def test_conditional_q90_oof_rejects_failed_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HighThresholdModel:
        def predict(self, x_predict: object) -> np.ndarray:
            return np.full(len(x_predict), 1.0)

    def fake_fit(**kwargs: object) -> tuple[object, dict[str, object], list[str]]:
        return (
            HighThresholdModel(),
            {
                "candidate_feature_hash": "candidate",
                "active_feature_hash": "active",
                "active_features": ["feature_x"],
            },
            ["feature_x"],
        )

    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(
        "n225_open_gap_tail.models.ml_tail_oof._fit_lgb_regression_model",
        fake_fit,
    )

    with pytest.raises(paper_module.PipelineRunError, match="unavailable_q90_calibration_failed"):
        paper_core._ml_tail_oof_conditional_q90_threshold(
            train_rows=_synthetic_ml_tail_location_scale_rows(70),
            candidate_features=["feature_x"],
            information_set="japan_only",
            tail_level=0.95,
            lgb=object(),
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
    unknown = paper_core._ml_tail_route_failure_metadata("other", "unavailable")

    assert mad["evt_route_gate_status"] == "unavailable_invalid_scale"
    assert mad["gpd_fit_status"] is None
    assert mad["gpd_es_status"] is None
    assert iqr["scale_method"] == "conditional_iqr_q25_q75"
    assert unknown == {}


def test_pot_gpd_excess_tail_records_infinite_es_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (1.2, 0.0, 1.0),
    )
    tail = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
        evt_variant="plain_mle",
    )
    assert tail["gpd_fit_status"] == "ok"
    assert tail["gpd_es_status"] == "unavailable_shape_ge_1"
    assert tail["excess_es"] is None


def test_pot_gpd_excess_tail_records_fit_failure_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low_count = paper_core._pot_gpd_excess_tail(
        excesses=np.array([0.1, 0.2]),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert low_count["gpd_fit_status"] == "unavailable_insufficient_exceedances"

    bad_probability = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=1.5,
        min_exceedances=10,
    )
    assert bad_probability["gpd_fit_status"] == "unavailable_invalid_gpd_probability"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fit failed")),
    )
    optimizer_failed = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert optimizer_failed["gpd_fit_status"] == "unavailable_optimizer_failed"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (math.nan, 0.0, 1.0),
    )
    invalid_shape = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert invalid_shape["gpd_fit_status"] == "unavailable_invalid_shape"
    assert invalid_shape["gpd_es_status"] == "unavailable_gpd_fit_failed"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )
    original_select_evt_shape_and_scale = benchmark_models._select_evt_shape_and_scale
    monkeypatch.setattr(
        "n225_open_gap_tail.models.benchmark._select_evt_shape_and_scale",
        lambda **kwargs: (
            {
                "shape_final": 0.1,
                "shape_method": "test",
                "cap_policy": "none",
                "cap_hit": False,
                "evi": {},
                "ei": {},
            },
            {"scale_final": -1.0, "scale_refit_status": "test_negative_scale"},
        ),
    )
    negative_scale = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert negative_scale["gpd_fit_status"] == "unavailable_negative_scale"
    assert negative_scale["gpd_es_status"] == "unavailable_gpd_fit_failed"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )
    monkeypatch.setattr(
        "n225_open_gap_tail.models.benchmark._select_evt_shape_and_scale",
        original_select_evt_shape_and_scale,
    )
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.ppf",
        lambda *args, **kwargs: math.nan,
    )
    invalid_quantile = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert invalid_quantile["gpd_fit_status"] == "unavailable_invalid_quantile"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.ppf",
        lambda *args, **kwargs: 0.5,
    )
    unknown_variant = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
        evt_variant="not_registered",
    )
    assert unknown_variant["gpd_fit_status"] == "unavailable_optimizer_failed"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (-0.5, 0.0, 1.0),
    )
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.ppf",
        lambda *args, **kwargs: 3.0,
    )
    support = paper_core._pot_gpd_excess_tail(
        excesses=np.linspace(0.01, 1.0, 40),
        tail_level=0.95,
        gpd_probability=0.5,
        min_exceedances=10,
    )
    assert support["gpd_fit_status"] == "unavailable_support_violation"


def test_conditional_q90_oof_helper_uses_threshold_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        def predict(self, x_predict: object) -> np.ndarray:
            return np.full(len(x_predict), 0.05)

    def fake_fit(**kwargs: object) -> tuple[object, dict[str, object], list[str]]:
        return (
            FakeModel(),
            {
                "candidate_feature_hash": "candidate",
                "active_feature_hash": "active",
                "active_features": ["feature_x"],
            },
            ["feature_x"],
        )

    _patch_paper_module(monkeypatch, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(
        "n225_open_gap_tail.models.ml_tail_oof._fit_lgb_regression_model",
        fake_fit,
    )
    rows = _synthetic_ml_tail_location_scale_rows(70)
    for index, row in enumerate(rows):
        row["realized_loss"] = 0.10 if index % 10 == 0 else 0.01

    oof = paper_core._ml_tail_oof_conditional_q90_threshold(
        train_rows=rows,
        candidate_features=["feature_x"],
        information_set="japan_only",
        tail_level=0.95,
        lgb=object(),
    )

    assert oof["q90_gate_status"] == "ok"
    assert oof["q90_oof_breach_rate"] == pytest.approx(0.1)
    assert cast(np.ndarray, oof["exceedances"]).size > 0


def test_conditional_q90_route_writes_forecasts_and_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_oof(**kwargs: object) -> dict[str, object]:
        return {
            "threshold_oof": np.zeros(80),
            "exceedances": np.linspace(0.01, 1.0, 40),
            "exceedance_indices": np.arange(40),
            "q90_oof_breach_rate": 0.10,
            "q90_expected_breach_rate": 0.10,
            "q90_gate_status": "ok",
            "q90_oof_count": 80,
        }

    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_ROWS", 25)
    _patch_paper_module(monkeypatch, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    monkeypatch.setattr(
        "n225_open_gap_tail.models.ml_tail._ml_tail_oof_conditional_q90_threshold",
        fake_oof,
    )
    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.1, 0.0, 1.0),
    )

    result = paper_core._forecast_ml_tail_lightgbm_sequence(
        rows=_synthetic_ml_tail_location_scale_rows(80),
        model_name="lightgbm_conditional_q90_pot_gpd_plain_mle",
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x", "feature_cycle"],
        tail_level=0.95,
        oos_start="2026-02-10",
    )

    ok = [row for row in result["forecasts"] if row["fit_status"] == "ok"]
    assert ok
    assert ok[0]["body_filter_method"] == "conditional_q90_threshold"
    assert ok[0]["q90_excess_probability_for_tail_level"] == pytest.approx(0.5)
    assert ok[0]["gpd_fit_status"] == "ok"
    assert ok[0]["gpd_es_status"] == "ok"


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


def test_pot_gpd_evt_variants_and_diagnostics_are_deterministic() -> None:
    rng = np.random.default_rng(0)
    losses = np.concatenate(
        [
            rng.exponential(scale=0.5, size=420),
            2.0 + rng.pareto(a=2.0, size=160),
        ]
    )
    rng.shuffle(losses)

    variants = {
        "plain_mle": "fixed_loc_mle",
        "capped_mle": "capped_fixed_loc_mle",
        "evi_shrink": "mle_evi_anchor_shrinkage",
        "ei_weighted": "mle_evi_anchor_ei_weighted",
        "stabilized": "stabilized_mle_evi_anchor_ei_weighted",
    }
    for variant, expected_method in variants.items():
        tail = benchmark_models._pot_gpd_standardized_tail(
            standardized_losses=losses,
            tail_level=0.95,
            evt_variant=variant,
            min_standardized_losses=100,
            min_exceedances=10,
            shape_cap=(-0.25, 0.75),
            shape_shrinkage_k=50.0,
        )
        assert tail["evt_variant"] == variant
        assert tail["evt_shape_method"] == expected_method
        assert tail["evt_cap_policy"] in {"none", "clip_-0.25_0.75"}
        assert cast(float, tail["standardized_es"]) >= cast(float, tail["standardized_var"])

    threshold = float(np.quantile(losses, 0.90))
    exceedance_indices = np.flatnonzero(losses > threshold)
    excesses = losses[losses > threshold] - threshold
    evi = benchmark_models._estimate_evi_anchor(excesses)
    ei = benchmark_models._estimate_extremal_index(exceedance_indices, int(excesses.size))
    assert evi["status"] == "ok"
    assert evi["primary_estimator"] == "dedh_moment"
    assert ei["status"] == "ok"
    assert ei["primary_estimator"] == "ferro_segers"
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
        evt_variant="stabilized",
        shape_cap=(-0.25, 0.75),
        shape_shrinkage_k=50.0,
    )
    assert {row["threshold_quantile"] for row in threshold_sensitivity} == {0.90, 0.925, 0.95}
    assert any(row["status"] == "ok" for row in threshold_sensitivity)
    assert threshold_sensitivity[-1]["status"] == "not_applicable_threshold_not_below_tail_level"


def test_location_scale_evt_variants_share_final_backbone_seed(
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
    stabilized = paper_core._fit_ml_tail_location_scale_bundle(
        train_rows=rows,
        candidate_features=["feature_x", "feature_cycle"],
        model_name=paper_module.ML_TAIL_POT_GPD_STABILIZED_MODEL,
        information_set="japan_only_plus_us_close_core",
        tail_level=0.95,
        lgb=lgb,
    )

    assert empirical["location_scale_backbone_key"] == stabilized["location_scale_backbone_key"]
    assert empirical["location_scale_location_seed"] == stabilized["location_scale_location_seed"]
    assert empirical["location_scale_scale_seed"] == stabilized["location_scale_scale_seed"]
    assert empirical["active_feature_hash"] == stabilized["active_feature_hash"]


def test_evt_diagnostic_artifact_helpers_parse_json_rows() -> None:
    row = {
        "forecast_date": "2026-02-03",
        "target_family": "full_gap_settle_to_open",
        "tail_side": "left_tail",
        "tail_level": 0.95,
        "model_name": paper_module.ML_TAIL_POT_GPD_STABILIZED_MODEL,
        "information_set": "japan_only_plus_us_close_core",
        "refit_frequency": "monthly",
        "refit_month": "2026-02",
        "train_n": 1200,
        "oof_standardized_loss_count": 700,
        "evt_variant": "stabilized",
        "evt_shape": 0.2,
        "evt_scale": 1.1,
        "evt_shape_mle": 0.3,
        "evt_scale_mle": 1.0,
        "evt_xi_evi_anchor": 0.1,
        "evt_cap_policy": "clip_-0.25_0.75",
        "evt_cap_hit": False,
        "evt_shape_method": "stabilized_mle_evi_anchor_ei_weighted",
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
    ablation_rows = ml_tail_suite._evt_ablation_metric_records(
        [
            row,
            {"model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL},
            {"model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL},
        ]
    )

    assert shape_rows[0]["evt_shape_method"] == "stabilized_mle_evi_anchor_ei_weighted"
    assert ei_rows[0]["ei_primary_estimator"] == "ferro_segers"
    assert cap_rows[1]["es_available"] is False
    assert threshold_rows[0]["sensitivity_threshold_quantile"] == 0.9
    assert threshold_rows[1]["sensitivity_status"] == (
        "not_applicable_threshold_not_below_tail_level"
    )
    assert len(ablation_rows) == 2
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
        rows.append(
            _with_panel_signature_fields(
                {
                    "forecast_date": current.date().isoformat(),
                    "target_family": "full_gap_settle_to_open",
                    "clean_sample": True,
                    "realized_loss": float(day % 20) / 100.0,
                    "gap_t": -float(day % 20) / 100.0,
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
    assert (run_dir / "metrics" / "ml_tail_dst_attenuation.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_feature_unavailability.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_feature_unavailability_dates.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_cpa_inference.parquet").exists()
    assert (run_dir / "metrics" / "cross_model_cpa_inference.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_sample_audit.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_mcs.parquet").exists()
    assert (run_dir / "metrics" / "evt_shape_stability.parquet").exists()
    assert (run_dir / "metrics" / "extremal_index_diagnostics.parquet").exists()
    assert (run_dir / "metrics" / "evt_cap_sensitivity.parquet").exists()
    assert (run_dir / "metrics" / "evt_threshold_sensitivity.parquet").exists()
    assert (run_dir / "metrics" / "evt_body_tail_diagnostics.parquet").exists()
    assert (run_dir / "metrics" / "evt_route_gate_status.parquet").exists()
    assert (run_dir / "metrics" / "evt_ablation_metrics.parquet").exists()
    assert (run_dir / "metrics" / "ml_tail_result_matrix_notes.md").exists()
    result_matrix = pl.read_parquet(run_dir / "metrics" / "ml_tail_result_matrix.parquet")
    headline_metrics = pl.read_parquet(run_dir / "metrics" / "ml_tail_metrics.parquet")
    cpa = pl.read_parquet(run_dir / "metrics" / "ml_tail_cpa_inference.parquet")
    cross_cpa = pl.read_parquet(run_dir / "metrics" / "cross_model_cpa_inference.parquet")
    assert not set(paper_module.ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES).intersection(
        set(headline_metrics["model_name"].to_list())
    )
    assert set(cpa["tail_side"].to_list()) == {"left_tail", "right_tail"}
    assert "var_quantile_loss" in set(cpa["loss_family"].to_list())
    assert set(cross_cpa["inference_status"].to_list()) == {"skipped_missing_benchmark_forecasts"}
    assert {
        "var_quantile_loss",
        "var_coverage",
        "var_es_fz_loss",
    }.issubset(set(result_matrix["loss_family"].to_list()))
    incremental_text = json.dumps(
        pl.read_parquet(run_dir / "metrics" / "ml_tail_incremental_information.parquet").to_dicts()
    )
    dst_text = json.dumps(
        pl.read_parquet(run_dir / "metrics" / "ml_tail_dst_attenuation.parquet").to_dicts()
    )
    assert "conditional predictive ability" not in incremental_text
    assert "conditional predictive ability" not in dst_text
    status = json.loads((run_dir / "metrics" / "ml_tail_status.json").read_text(encoding="utf-8"))
    assert set(status["implemented_components"]) == set(paper_module.ML_TAIL_MODEL_NAMES)
    assert status["unavailable_components"] == {}
    registered_models = {
        key for key in status["registered_information_sets"] if str(key).startswith("model_")
    }
    assert registered_models == {"model_a", "model_b", "model_c", "model_d"}
    assert status["registered_information_sets"]["model_d"].endswith("plus_asia_proxy")
    assert status["cpa_inference_rows"] == cpa.height
    assert status["cross_model_cpa_inference_rows"] == cross_cpa.height
    assert status["cross_model_cpa_status"] == "skipped_missing_benchmark_forecasts"
    assert status["evt_body_tail_diagnostic_rows"] >= 0
    assert status["evt_route_gate_status_rows"] >= 0
