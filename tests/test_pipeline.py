# mypy: ignore-errors
from __future__ import annotations

import ast
import importlib
import json
import math
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
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
import n225_open_gap_tail.forecasting.evaluation as evaluation_dispatch
import n225_open_gap_tail.metrics.information as metrics_information
import n225_open_gap_tail.metrics.stat_utils as stat_utils
import n225_open_gap_tail.models.benchmark_advanced as benchmark_advanced
import n225_open_gap_tail.panel as paper_leakage
import n225_open_gap_tail.panel as paper_panel
import n225_open_gap_tail.panel.build_helpers as panel_build_helpers
import n225_open_gap_tail.reporting as paper_reporting
import n225_open_gap_tail.reporting.figures as reporting_figures
import n225_open_gap_tail.reporting.latex as reporting_latex
import n225_open_gap_tail.reporting.tables as reporting_tables
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import VendorErrorClass
from n225_open_gap_tail.diagnostics.feature_audit import write_feature_audit
from n225_open_gap_tail.features.cross_market import add_cross_market_features
from n225_open_gap_tail.features.descriptions import (
    _optional_float as _description_optional_float,
)
from n225_open_gap_tail.features.descriptions import (
    _optional_text,
)
from n225_open_gap_tail.features.descriptions import (
    _required_float as _description_required_float,
)
from n225_open_gap_tail.features.event_calendar import (
    EventCalendarRecord,
    add_event_calendar_features,
    load_event_calendar,
)
from n225_open_gap_tail.features.n225_history import (
    _contract_month_number,
    _is_finite_or_none,
    _parse_date,
    add_n225_history_features,
)
from n225_open_gap_tail.features.n225_history import (
    _log_return as _n225_log_return,
)
from n225_open_gap_tail.features.n225_history import (
    _sample_excess_kurtosis as _n225_sample_excess_kurtosis,
)
from n225_open_gap_tail.features.n225_history import (
    _sample_skew as _n225_sample_skew,
)
from n225_open_gap_tail.features.n225_history import (
    _semivar_if_enough as _n225_semivar_if_enough,
)
from n225_open_gap_tail.features.session_features import (
    _realized_var as _minute_realized_var,
)
from n225_open_gap_tail.features.session_features import (
    _sample_excess_kurtosis as _minute_sample_excess_kurtosis,
)
from n225_open_gap_tail.features.session_features import (
    _sample_skew as _minute_sample_skew,
)
from n225_open_gap_tail.features.session_features import (
    _semivar as _minute_semivar,
)
from n225_open_gap_tail.features.session_features import (
    build_massive_late_session_feature_records as build_feature_minute_records,
)
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
from n225_open_gap_tail.sources.jquants import JQuantsV2Client


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


def test_build_run_id_binds_window_timestamp_and_commit() -> None:
    run_id = build_run_id(
        start="2008-05-07",
        end="2026-04-28",
        run_ts_utc=datetime(2026, 4, 28, 12, 30, tzinfo=UTC),
        git_commit="abcdef123456",
    )

    assert run_id == "tailrisk_20080507_20260428_20260428T123000Z_commit_abcdef12"


def test_paper_package_split_preserves_import_compatibility() -> None:
    assert paper_panel.build_panel is build_panel
    assert paper_cache.cleanup_transient_unavailable_markers is (
        paper_module.cleanup_transient_unavailable_markers
    )
    assert paper_evaluation.evaluate_suite is evaluate_suite
    assert paper_features.drop_low_variance_features is drop_low_variance_features
    assert paper_leakage.write_leakage_check is write_leakage_check
    assert paper_reporting.export_tables is export_tables
    assert paper_reporting.export_figures is reporting_figures.export_figures
    assert paper_evaluation.evaluate_benchmark_baseline_suite is evaluate_benchmark_baseline_suite
    assert paper_evaluation.evaluate_ml_tail_suite is ml_tail_suite.evaluate_ml_tail_suite
    assert paper_evaluation.evaluate_benchmark_suite is benchmark_suite.evaluate_benchmark_suite
    assert paper_evaluation._evaluate_benchmark_advanced_shard is (
        benchmark_advanced._evaluate_benchmark_advanced_shard
    )
    assert not hasattr(pipeline_runtime, "_IMPLEMENTATION_MODULES")
    assert not hasattr(pipeline_runtime, "wire_runtime_namespace")


def test_runtime_bridge_removed_from_source_modules() -> None:
    source_root = Path("src/n225_open_gap_tail")
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if (
            "globals().update" in text
            or "wire_runtime_namespace" in text
            or "from n225_open_gap_tail.config.runtime import *" in text
        ):
            offenders.append(str(path))
    assert offenders == []


def test_benchmark_tagged_dispatch_routes_by_shard_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_baseline(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
        calls.append(f"baseline:{payload['shard_id']}")
        return {"forecasts": [{"model_name": "baseline"}], "diagnostics": [], "failures": []}

    def fake_advanced(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
        calls.append(f"advanced:{payload['shard_id']}")
        return {"forecasts": [{"model_name": "advanced"}], "diagnostics": [], "failures": []}

    monkeypatch.setattr(benchmark_suite, "_evaluate_benchmark_shard", fake_baseline)
    monkeypatch.setattr(
        benchmark_suite,
        "_evaluate_benchmark_advanced_shard",
        fake_advanced,
    )

    baseline = benchmark_suite._dispatch_benchmark_shard(
        {"shard_kind": "baseline", "shard_id": "a"}
    )
    advanced = benchmark_suite._dispatch_benchmark_shard(
        {"shard_kind": "advanced", "shard_id": "b"}
    )

    assert calls == ["baseline:a", "advanced:b"]
    assert baseline["shard_kind"] == "baseline"
    assert advanced["shard_kind"] == "advanced"


def test_paper_root_is_compatibility_surface() -> None:
    root = Path(paper_module.__file__).read_text(encoding="utf-8")
    module = ast.parse(root)
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in module.body)
    required_public = {
        "PanelBuildResult",
        "EvaluationResult",
        "TableExportResult",
        "LeakageCheckResult",
        "PipelineRunError",
        "build_panel",
        "evaluate_suite",
        "evaluate_benchmark_baseline_suite",
        "evaluate_benchmark_suite",
        "evaluate_ml_tail_suite",
        "export_tables",
        "write_leakage_check",
        "build_run_id",
        "find_oos_start_date",
        "cleanup_transient_unavailable_markers",
        "build_ml_tail_result_matrix_artifacts",
    }
    paper_all = cast("list[str]", paper_module.__dict__["__all__"])
    assert required_public.issubset(set(paper_all))


def test_functional_modules_do_not_import_removed_pipeline_package() -> None:
    src_dir = Path("src/n225_open_gap_tail")
    for path in src_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "n225_open_gap_tail.pipeline" not in text


@pytest.mark.parametrize(
    "module_name",
    [
        "n225_open_gap_tail.config",
        "n225_open_gap_tail.data_lake",
        "n225_open_gap_tail.sources",
        "n225_open_gap_tail.market",
        "n225_open_gap_tail.features",
        "n225_open_gap_tail.panel",
        "n225_open_gap_tail.forecasting",
        "n225_open_gap_tail.models",
        "n225_open_gap_tail.metrics",
        "n225_open_gap_tail.inference",
        "n225_open_gap_tail.reporting",
        "n225_open_gap_tail.diagnostics",
        "n225_open_gap_tail.data_lake.cache_ops",
        "n225_open_gap_tail.panel.build",
        "n225_open_gap_tail.panel.target_audit",
        "n225_open_gap_tail.panel.time_alignment",
        "n225_open_gap_tail.models.ml_tail",
        "n225_open_gap_tail.models.benchmark_advanced",
        "n225_open_gap_tail.models.benchmark_advanced_stateful",
        "n225_open_gap_tail.metrics.result_matrix",
        "n225_open_gap_tail.metrics.result_matrix_grouping",
        "n225_open_gap_tail.metrics.result_matrix_scoring",
        "n225_open_gap_tail.metrics.result_matrix_notes",
        "n225_open_gap_tail.sources.jquants_futures",
    ],
)
def test_pipeline_submodule_surfaces_import(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module is not None


def test_forecast_validity_distinguishes_var_breach_from_invalid_forecast() -> None:
    assert validate_forecast_values(2.0, 2.5) == (True, None)
    assert validate_forecast_values(2.0, 1.9) == (False, "invalid_es_below_var")
    assert validate_forecast_values(-2.0, -1.0) == (False, "invalid_nonpositive_es")
    assert validate_forecast_values(math.nan, 2.5) == (False, "invalid_nonfinite_forecast")


def test_es_companion_rules_cover_static_dynamic_and_filtered_history() -> None:
    train_losses = np.array([1.0, 2.0, 3.0, 10.0])
    assert static_empirical_es(train_losses, 2.5) == 6.5

    train_var = np.array([1.5, 1.5, 2.5, 8.0])
    companion = empirical_excess_es_companion(
        train_losses=train_losses,
        train_var_forecasts=train_var,
        forecast_var=4.0,
    )
    assert companion > 4.0

    filtered = filtered_historical_es(
        location_forecast=0.1,
        scale_forecast=2.0,
        standardized_train_losses=np.array([0.1, 1.0, 2.0, 3.0]),
        standardized_var=1.5,
    )
    assert filtered >= 0.1 + 2.0 * 1.5


def test_find_oos_start_requires_min_rows_and_tail_exceedances() -> None:
    start = datetime(2015, 1, 1, tzinfo=UTC)
    rows = [
        {
            "forecast_date": (start + timedelta(days=day)).date().isoformat(),
            "realized_loss": float(day % 20),
        }
        for day in range(140)
    ]

    oos = find_oos_start_date(
        rows,
        earliest_oos_start="2015-01-01",
        min_train_rows=100,
        min_train_exceedances=5,
        tail_level=0.95,
    )

    assert oos is not None
    assert oos >= "2015-04-11"
    assert (
        find_oos_start_date(
            rows,
            earliest_oos_start="2015-01-01",
            min_train_rows=200,
            min_train_exceedances=5,
        )
        is None
    )


def test_combined_clean_start_excludes_pre_start_forecast_rows() -> None:
    panel = paper_module.apply_combined_clean_start(
        [
            {
                "forecast_date": "2018-06-20",
                "clean_sample": True,
                "forecast_sample": True,
                "forecast_sample_reason": None,
            },
            {
                "forecast_date": "2018-06-22",
                "clean_sample": True,
                "forecast_sample": True,
                "forecast_sample_reason": None,
            },
        ],
        combined_clean_start="2018-06-21",
    )

    assert panel[0]["clean_sample"] is False
    assert panel[0]["forecast_sample"] is False
    assert panel[0]["forecast_sample_reason"] == "before_combined_clean_start"
    assert panel[0]["combined_clean_start"] == "2018-06-21"
    assert panel[1]["clean_sample"] is True
    bad_threshold_rows = [{"forecast_date": "2018-06-20", "forecast_sample": True}]
    assert (
        paper_module.apply_combined_clean_start(
            bad_threshold_rows,
            combined_clean_start="not-a-date",
        )
        is bad_threshold_rows
    )
    bad_date = paper_module.apply_combined_clean_start(
        [{"forecast_date": "not-a-date", "forecast_sample": True}],
        combined_clean_start="2018-06-21",
    )
    assert bad_date == [{"forecast_date": "not-a-date", "forecast_sample": True}]


def test_oos_gate_reason_ordering_after_clean_sample_filter() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = [
        {
            "forecast_date": (start + timedelta(days=day)).date().isoformat(),
            "clean_sample": day >= 2,
            "forecast_sample_reason": "before_combined_clean_start" if day < 2 else None,
            "realized_loss": float(day % 10),
        }
        for day in range(8)
    ]

    train_rows_diag = paper_module.find_oos_start_diagnostics(
        rows,
        earliest_oos_start="2026-01-01",
        min_train_rows=10,
        min_train_exceedances=1,
    )
    exceedance_diag = paper_module.find_oos_start_diagnostics(
        rows,
        earliest_oos_start="2026-01-01",
        min_train_rows=3,
        min_train_exceedances=5,
    )

    assert train_rows_diag["failure_reason"] == "train_n_below_1000"
    assert train_rows_diag["train_n"] == 5
    assert exceedance_diag["failure_reason"] == "train_exceedances_below_50"


def test_drop_low_variance_features_filters_dynamic_training_window() -> None:
    frame = pl.DataFrame(
        {
            "constant": [1.0, 1.0, 1.0],
            "moving": [1.0, 2.0, 3.0],
            "near_zero": [1e-12, 2e-12, 3e-12],
        }
    )

    active, dropped = drop_low_variance_features(
        frame,
        ["constant", "moving", "near_zero", "missing"],
    )

    assert active == ["moving"]
    assert dropped == ["constant", "near_zero", "missing"]


def test_global_oos_intersection_requires_complete_loss_matrix() -> None:
    forecasts: list[dict[str, object]] = [
        {"model_name": "a", "forecast_date": "2026-01-01", "fit_status": "ok"},
        {"model_name": "a", "forecast_date": "2026-01-02", "fit_status": "ok"},
        {"model_name": "b", "forecast_date": "2026-01-02", "fit_status": "ok"},
        {"model_name": "b", "forecast_date": "2026-01-03", "fit_status": "ok"},
    ]

    assert global_oos_intersection(forecasts, model_names=("a", "b")) == ["2026-01-02"]
    assert pairwise_oos_intersection(
        forecasts,
        left_model="a",
        right_model="b",
    ) == ["2026-01-02"]
    assert paper_module.common_sample_status(["2026-01-02"], min_rows=2) == (
        "unavailable_insufficient_common_oos"
    )
    assert global_oos_intersection([], model_names=()) == []


def test_tail_side_loss_units_are_explicit_and_symmetric() -> None:
    rows = [
        {"forecast_date": "2026-01-01", "gap_t": -0.04, "realized_loss": 999.0},
        {"forecast_date": "2026-01-02", "gap_t": 0.03, "realized_loss": 999.0},
    ]

    left = pipeline_runtime.rows_for_tail_side(rows, tail_side="left-tail")
    right = pipeline_runtime.rows_for_tail_side(rows, tail_side="right_tail")

    assert [row["realized_loss"] for row in left] == pytest.approx([0.04, -0.03])
    assert [row["realized_loss"] for row in right] == pytest.approx([-0.04, 0.03])
    assert {row["tail_side"] for row in left} == {"left_tail"}
    assert {row["tail_side"] for row in right} == {"right_tail"}
    assert pipeline_runtime.tail_side_values("both") == ("left_tail", "right_tail")
    assert pipeline_runtime.TAIL_LEVELS == (0.95,)
    with pytest.raises(paper_module.PipelineRunError, match="Unknown tail_side"):
        pipeline_runtime.normalize_tail_side("center_tail")


def test_feature_matrix_gate_records_candidate_active_and_dropped_sets() -> None:
    frame = pl.DataFrame(
        {
            "good": [1.0, 2.0, 3.0],
            "constant": [1.0, 1.0, 1.0],
            "nonfinite": [1.0, math.inf, math.nan],
        }
    )

    gate = build_feature_matrix_gate_records(
        frame,
        ["good", "constant", "nonfinite", "missing"],
    )

    assert gate["active_features"] == ["good"]
    dropped_features = cast(list[str], gate["dropped_features"])
    assert "constant" in dropped_features
    assert "missing" in dropped_features
    assert isinstance(gate["candidate_feature_hash"], str)
    assert json.loads(str(gate["dropped_features_json"]))


def test_filled_fred_zero_diffs_are_low_variance_dropped_not_model_breaking() -> None:
    frame = pl.DataFrame(
        {
            "fred_dgs10_diff": [0.0, 0.0, 0.0, 0.0],
            "fred_rates_staleness_days": [0.0, 1.0, 2.0, 3.0],
        }
    )

    gate = build_feature_matrix_gate_records(
        frame,
        ["fred_dgs10_diff", "fred_rates_staleness_days"],
    )

    assert gate["active_features"] == ["fred_rates_staleness_days"]
    assert "fred_dgs10_diff" in cast(list[str], gate["dropped_features"])


def test_feature_matrix_gate_drops_sparse_minute_features_before_prediction() -> None:
    frame = pl.DataFrame(
        {
            "dense": [float(index) for index in range(10)],
            "sparse_minute_late_60m_return": [
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
                6.0,
                None,
                None,
                None,
                None,
            ],
            "tolerated_history_feature": [
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
                6.0,
                7.0,
                8.0,
                None,
                None,
            ],
        }
    )

    gate = build_feature_matrix_gate_records(
        frame,
        ["dense", "sparse_minute_late_60m_return", "tolerated_history_feature"],
    )

    assert gate["active_features"] == ["dense", "tolerated_history_feature"]
    assert "sparse_minute_late_60m_return" in cast(list[str], gate["dropped_features"])
    dropped = json.loads(str(gate["dropped_features_json"]))
    sparse_drop = next(
        item for item in dropped if item["feature"] == "sparse_minute_late_60m_return"
    )
    assert sparse_drop["drop_reason"] == "high_training_missingness"
    assert sparse_drop["max_missingness"] == pytest.approx(0.05)


def test_ml_tail_information_sets_select_nested_feature_blocks() -> None:
    coverage_rows: list[dict[str, object]] = [
        {"feature": "spy_return", "source_block": "us_core"},
        {"feature": "spy_late_30m_return", "source_block": "us_late_session"},
        {"feature": "qqq_late_30m_return", "source_block": "us_late_session"},
        {"feature": "ewj_late_30m_return", "source_block": "japan_proxy"},
        {"feature": "ewh_late_30m_return", "source_block": "asia_proxy"},
        {"feature": "n225_day_range_lag_1", "source_block": "japan_only"},
        {"feature": "fred_vixcls_level", "source_block": "fred_core"},
        {"feature": "fred_rates_staleness_days", "source_block": "fred_core"},
        {"feature": "fx_usdjpy_level", "source_block": "fx_core"},
        {"feature": "fx_release_age_days", "source_block": "fx_core"},
        {"feature": "uup_return", "source_block": "massive_optional"},
        {"feature": "event_nfp_same_us_session", "source_block": "calendar_controls"},
        {"feature": "event_major_count_next_3d", "source_block": "calendar_controls"},
        {"feature": "ewj_return", "source_block": "japan_proxy"},
        {"feature": "ewh_return", "source_block": "asia_proxy"},
        {"feature": "option_us_core_spy_atm_iv_short", "source_block": "us_core"},
        {"feature": "option_us_sector_median_atm_iv_short", "source_block": "us_core"},
        {"feature": "xmarket_us_core_return_mean_1d", "source_block": "us_core"},
        {"feature": "xmarket_vix_shock_20d", "source_block": "fred_core"},
        {"feature": "option_japan_etf_ewj_atm_iv_short", "source_block": "japan_proxy"},
        {"feature": "option_japan_adr_median_atm_iv_short", "source_block": "japan_proxy"},
        {"feature": "japan_adr_median_return", "source_block": "japan_proxy"},
        {"feature": "xmarket_japan_proxy_ewj_spy_spread_1d", "source_block": "japan_proxy"},
        {"feature": "option_asia_proxy_median_atm_iv_short", "source_block": "asia_proxy"},
        {"feature": "xmarket_asia_proxy_return_dispersion_1d", "source_block": "asia_proxy"},
        {"feature": "fred_bamlh0a0hym2_level", "source_block": "fred_credit_enriched"},
    ]

    japan_only = ml_tail_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only",
    )
    us_core = ml_tail_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core",
    )
    japan_proxy = ml_tail_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core_plus_japan_proxy",
    )
    asia_proxy = ml_tail_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy",
    )
    assert "loss_lag_1" in japan_only
    assert "n225_day_range_lag_1" in japan_only
    assert "event_boj_same_ose_session" in japan_only
    assert "event_nfp_same_us_session" not in japan_only
    assert "event_major_count_next_3d" not in japan_only
    assert "xmarket_us_core_return_mean_1d" not in japan_only
    assert "spy_return" not in japan_only
    assert "spy_late_30m_return" in us_core
    assert "qqq_late_30m_return" in us_core
    assert "option_us_core_spy_atm_iv_short" in us_core
    assert "option_us_sector_median_atm_iv_short" in us_core
    assert "xmarket_us_core_return_mean_1d" in us_core
    assert "xmarket_vix_shock_20d" in us_core
    assert "xmarket_japan_proxy_ewj_spy_spread_1d" not in us_core
    assert "option_japan_etf_ewj_atm_iv_short" not in us_core
    assert "option_asia_proxy_median_atm_iv_short" not in us_core
    assert "ewj_late_30m_return" not in us_core
    assert "ewh_late_30m_return" not in us_core
    assert "fx_usdjpy_level" in us_core
    assert "fred_rates_staleness_days" in us_core
    assert "fred_bamlh0a0hym2_level" in us_core
    assert "event_nfp_same_us_session" in us_core
    assert "event_major_count_next_3d" in us_core
    assert "uup_return" in us_core
    assert "ewj_return" in japan_proxy
    assert "ewj_late_30m_return" in japan_proxy
    assert "option_japan_etf_ewj_atm_iv_short" in japan_proxy
    assert "option_japan_adr_median_atm_iv_short" in japan_proxy
    assert "japan_adr_median_return" in japan_proxy
    assert "xmarket_japan_proxy_ewj_spy_spread_1d" in japan_proxy
    assert "xmarket_asia_proxy_return_dispersion_1d" not in japan_proxy
    assert "option_asia_proxy_median_atm_iv_short" not in japan_proxy
    assert "ewh_return" in asia_proxy
    assert "ewh_late_30m_return" in asia_proxy
    assert "option_us_core_spy_atm_iv_short" in asia_proxy
    assert "option_japan_adr_median_atm_iv_short" in asia_proxy
    assert "option_asia_proxy_median_atm_iv_short" in asia_proxy
    assert "xmarket_asia_proxy_return_dispersion_1d" in asia_proxy
    assert paper_core._feature_source_block("ewj_late_30m_return") == "japan_proxy"
    assert paper_core._feature_source_block("ewh_late_30m_return") == "asia_proxy"
    assert paper_core._feature_source_block("spy_late_30m_return") == "us_late_session"
    assert paper_core._feature_source_block("option_us_core_spy_atm_iv_short") == "us_core"
    assert paper_core._feature_source_block("option_japan_etf_ewj_atm_iv_short") == "japan_proxy"
    assert paper_core._feature_source_block("option_japan_adr_median_atm_iv_short") == (
        "japan_proxy"
    )
    assert paper_core._feature_source_block("japan_adr_median_return") == "japan_proxy"
    assert paper_core._feature_source_block("fx_release_age_days") == "fx_core"
    assert paper_core._feature_source_block("option_asia_proxy_median_atm_iv_short") == (
        "asia_proxy"
    )
    assert paper_core._feature_source_block("event_nfp_same_us_session") == "calendar_controls"
    assert paper_core._feature_source_block("xmarket_us_core_return_mean_1d") == "us_core"
    assert paper_core._feature_source_block("xmarket_vix_shock_20d") == "fred_core"
    assert (
        paper_core._feature_source_block("xmarket_japan_proxy_ewj_spy_spread_1d") == "japan_proxy"
    )
    assert (
        paper_core._feature_source_block("xmarket_asia_proxy_return_dispersion_1d") == "asia_proxy"
    )
    with pytest.raises(paper_module.PipelineRunError):
        ml_tail_feature_columns_for_information_set(
            coverage_rows,
            information_set="unknown_information_set",
        )


def test_options_audit_artifacts_are_disabled_until_historical_source_is_verified(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        bronze_data_dir=tmp_path / "data" / "bronze",
        silver_data_dir=tmp_path / "data" / "silver",
        gold_data_dir=tmp_path / "data" / "gold",
        reports_dir=tmp_path / "reports",
    )

    source_audit = paper_core.build_options_source_audit_records(
        settings=settings,
        run_ts=datetime(2026, 1, 1, tzinfo=UTC),
    )
    feature_coverage = paper_core.build_options_feature_coverage_records(settings=settings)
    liquidity = paper_core.build_options_liquidity_audit_records(settings=settings)

    assert any(row["source_name"] == "massive_options_snapshot" for row in source_audit)
    assert all(
        row["primary_promotion_allowed"] is False
        for row in source_audit
        if str(row["source_name"]).startswith("massive_options")
    )
    assert any(
        row["source_name"] == "jquants_nikkei_options" and row["primary_promotion_allowed"] is True
        for row in source_audit
    )
    assert {row["source_block"] for row in feature_coverage} == {
        "us_core",
        "japan_proxy",
        "asia_proxy",
    }
    assert all(str(row["feature_status"]).startswith("disabled") for row in feature_coverage)
    assert any(row["underlying"] == "SPY" for row in liquidity)


def test_n225_option_features_use_prior_available_option_state() -> None:
    option_rows = paper_core.normalize_jquants_nikkei225_option_rows(
        [
            {
                "Date": "2026-01-05",
                "Code": "OPT-P",
                "ContractMonth": "2026-03",
                "StrikePrice": 39000.0,
                "PutCallDivision": "1",
                "OpenInterest": 100.0,
                "Volume": 10.0,
                "NightSessionOpen": 100.0,
                "NightSessionHigh": 112.0,
                "NightSessionLow": 98.0,
                "NightSessionClose": 110.0,
                "SettlementPrice": 250.0,
                "TheoreticalPrice": 255.0,
                "BaseVolatility": 0.22,
                "UnderlyingPrice": 39010.0,
                "ImpliedVolatility": 0.24,
                "SpecialQuotationDay": "2026-03-13",
                "CentralContractMonthFlag": "1",
            },
            {
                "Date": "2026-01-05",
                "Code": "OPT-C",
                "ContractMonth": "2026-03",
                "StrikePrice": 39000.0,
                "PutCallDivision": "2",
                "OpenInterest": 200.0,
                "Volume": 20.0,
                "NightSessionOpen": 200.0,
                "NightSessionHigh": 225.0,
                "NightSessionLow": 195.0,
                "NightSessionClose": 220.0,
                "SettlementPrice": 260.0,
                "TheoreticalPrice": 265.0,
                "BaseVolatility": 0.20,
                "UnderlyingPrice": 39010.0,
                "ImpliedVolatility": 0.21,
                "SpecialQuotationDay": "2026-03-13",
                "CentralContractMonthFlag": "1",
            },
        ],
        downloaded_at_utc=datetime(2026, 1, 5, 12, tzinfo=UTC),
    )
    option_features = paper_core.build_n225_option_feature_records(option_rows)
    panel = paper_core.add_n225_option_features(
        [
            {
                "forecast_date": "2026-01-06",
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC),
            }
        ],
        option_features,
    )

    assert panel[0]["n225_option_atm_iv_lag_1"] == pytest.approx(0.225)
    assert panel[0]["n225_option_atm_put_call_iv_skew_lag_1"] == pytest.approx(0.03)
    assert panel[0]["n225_option_put_call_oi_ratio_lag_1"] == pytest.approx(0.5)
    assert panel[0]["n225_option_valid_contract_count_lag_1"] == pytest.approx(2.0)
    assert panel[0]["n225_option_night_atm_close_lag_1"] == pytest.approx(165.0)
    assert panel[0]["n225_option_night_atm_return_lag_1"] == pytest.approx(math.log(1.1))
    assert panel[0]["n225_option_night_atm_range_lag_1"] == pytest.approx(
        np.median([math.log(112.0 / 98.0), math.log(225.0 / 195.0)])
    )
    assert panel[0]["n225_option_night_valid_contract_count_lag_1"] == pytest.approx(2.0)


def test_n225_option_features_normalize_compact_v2_fields_and_write_silver(
    tmp_path: Path,
) -> None:
    downloaded_at = datetime(2026, 1, 5, 12, tzinfo=UTC)
    option_rows = paper_core.normalize_jquants_nikkei225_option_rows(
        [
            {
                "Date": "20260105",
                "Code": "P-ATM",
                "CM": "2026-02",
                "CCMFlag": "1",
                "Strike": 52000.0,
                "PCDiv": "1",
                "OI": 300.0,
                "Vo": 30.0,
                "EO": 100.0,
                "EH": 115.0,
                "EL": 95.0,
                "EC": 105.0,
                "Settle": 210.0,
                "Theo": 215.0,
                "BaseVol": 20.0,
                "UnderPx": 51990.0,
                "IV": 24.0,
                "IR": 0.5,
                "SQD": "20260213",
            },
            {
                "Date": "20260105",
                "Code": "C-ATM",
                "CM": "2026-02",
                "CCMFlag": "1",
                "Strike": 52000.0,
                "PCDiv": "2",
                "OI": 100.0,
                "Vo": 10.0,
                "EO": 200.0,
                "EH": 220.0,
                "EL": 190.0,
                "EC": 210.0,
                "Settle": 220.0,
                "Theo": 225.0,
                "BaseVol": 18.0,
                "UnderPx": 51990.0,
                "IV": 21.0,
                "IR": 0.5,
                "SQD": "20260213",
            },
            {
                "Date": "20260105",
                "Code": "BAD",
                "CM": "2026-02",
                "Strike": 0.0,
                "PCDiv": "2",
                "UnderPx": 51990.0,
                "IV": 19.0,
                "SQD": "20260213",
            },
        ],
        downloaded_at_utc=downloaded_at,
    )
    features = paper_core.build_n225_option_feature_records(option_rows)

    settings = Settings(
        data_dir=tmp_path / "data",
        bronze_data_dir=tmp_path / "data" / "bronze",
        silver_data_dir=tmp_path / "data" / "silver",
        gold_data_dir=tmp_path / "data" / "gold",
        reports_dir=tmp_path / "reports",
    )
    paper_core.write_jquants_options_silver_cache(settings=settings, rows=option_rows)
    silver_path = (
        settings.data_dir
        / "silver"
        / "jquants_nk225_options_daily"
        / f"schema_version={pipeline_runtime.JQUANTS_OPTIONS_SILVER_SCHEMA.version}"
        / "year=2026"
        / "month=01"
        / "data.parquet"
    )
    option_by_code = {str(row["option_code"]): row for row in option_rows}
    too_early_panel = paper_core.add_n225_option_features(
        [
            {
                "forecast_date": "2026-01-06",
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 17, tzinfo=UTC),
            }
        ],
        features,
    )
    same_date_panel = paper_core.add_n225_option_features(
        [
            {
                "forecast_date": "2026-01-05",
                "model_cutoff_ts_utc": datetime(2026, 1, 6, 20, tzinfo=UTC),
            }
        ],
        features,
    )

    assert silver_path.exists()
    assert option_by_code["P-ATM"]["implied_volatility"] == pytest.approx(0.24)
    assert option_by_code["P-ATM"]["central_contract_month_flag"] is True
    assert option_by_code["P-ATM"]["interest_rate"] == pytest.approx(0.005)
    assert option_by_code["P-ATM"]["night_session_open"] == pytest.approx(100.0)
    assert option_by_code["P-ATM"]["night_session_close"] == pytest.approx(105.0)
    assert features[0]["atm_iv"] == pytest.approx(0.225)
    assert features[0]["atm_put_call_iv_skew"] == pytest.approx(0.03)
    assert features[0]["put_call_oi_ratio"] == pytest.approx(3.0)
    assert features[0]["days_to_sq"] == pytest.approx(39.0)
    assert features[0]["night_atm_close"] == pytest.approx(157.5)
    assert features[0]["night_atm_return"] == pytest.approx(
        np.median([math.log(105.0 / 100.0), math.log(210.0 / 200.0)])
    )
    assert features[0]["night_atm_range"] == pytest.approx(
        np.median([math.log(115.0 / 95.0), math.log(220.0 / 190.0)])
    )
    assert features[0]["night_valid_contract_count"] == pytest.approx(2.0)
    assert too_early_panel[0]["n225_option_atm_iv_lag_1"] is None
    assert too_early_panel[0]["n225_option_night_atm_return_lag_1"] is None
    assert same_date_panel[0]["n225_option_atm_iv_lag_1"] is None
    assert same_date_panel[0]["n225_option_night_atm_return_lag_1"] is None


def test_jquants_nikkei225_options_client_uses_date_only_endpoint_params() -> None:
    seen_query: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_query.append(request.url.query.decode())
        return httpx.Response(200, json={"data": []})

    with JQuantsV2Client(api_key="test", transport=httpx.MockTransport(handler)) as client:
        client.get_nikkei225_options_daily_bars(
            trading_date="2026-01-05",
            category="NK225E",
            contract_flag="1",
        )

    assert seen_query == ["date=2026-01-05"]


def test_n225_option_surface_buckets_risk_reversal_and_metadata() -> None:
    available = datetime(2026, 1, 6, 3, tzinfo=UTC)
    option_rows = [
        {
            "trading_date": "2026-01-05",
            "strike_price": strike,
            "underlying_price": 100.0,
            "implied_volatility": iv,
            "base_volatility": base_vol,
            "open_interest": oi,
            "volume": volume,
            "put_call": put_call,
            "central_contract_month_flag": False,
            "special_quotation_day": sq,
            "vendor_available_ts_utc": available,
        }
        for strike, iv, base_vol, oi, volume, put_call, sq in (
            (100.0, 0.20, 0.24, 100.0, 10.0, "call", "2026-01-20"),
            (100.0, 0.22, 0.24, 300.0, 30.0, "put", "2026-01-20"),
            (100.0, 0.30, 0.34, 200.0, 20.0, "call", "2026-03-01"),
            (100.0, 0.32, 0.34, 200.0, 20.0, "put", "2026-03-01"),
            (95.0, 0.36, 0.34, 50.0, 5.0, "put", "2026-03-01"),
            (105.0, 0.25, 0.34, 50.0, 5.0, "call", "2026-03-01"),
        )
    ]
    features = paper_core.build_n225_option_feature_records(option_rows)
    panel = paper_core.add_n225_option_features(
        [
            {
                "forecast_date": "2026-01-07",
                "model_cutoff_ts_utc": datetime(2026, 1, 6, 21, tzinfo=UTC),
            }
        ],
        features,
    )
    row = panel[0]

    assert features[0]["atm_iv_short"] == pytest.approx(0.21)
    assert features[0]["atm_iv_medium"] == pytest.approx(0.31)
    assert row["n225_option_iv_term_slope_lag_1"] == pytest.approx(0.10)
    assert row["n225_option_risk_reversal_lag_1"] == pytest.approx(0.11)
    assert row["n225_option_put_oi_share_lag_1"] == pytest.approx(550.0 / 900.0)
    assert row["n225_option_short_valid_contract_count_lag_1"] == pytest.approx(2.0)
    assert row["n225_option_medium_valid_contract_count_lag_1"] == pytest.approx(4.0)
    assert row["n225_option_atm_iv_lag_1__source_date"] == "2026-01-05"
    assert row["n225_option_atm_iv_lag_1__available_ts_utc"] == available


def test_n225_option_medium_only_bucket_leaves_term_slope_null() -> None:
    features = paper_core.build_n225_option_feature_records(
        [
            {
                "trading_date": "2026-01-05",
                "strike_price": 100.0,
                "underlying_price": 100.0,
                "implied_volatility": 0.30,
                "open_interest": 1.0,
                "volume": 1.0,
                "put_call": "call",
                "central_contract_month_flag": True,
                "special_quotation_day": "2026-03-01",
                "vendor_available_ts_utc": datetime(2026, 1, 6, 3, tzinfo=UTC),
            }
        ]
    )

    assert features[0]["atm_iv_short"] is None
    assert features[0]["atm_iv_medium"] == pytest.approx(0.30)
    assert features[0]["iv_term_slope"] is None


def test_n225_option_features_fail_closed_on_cutoff_and_dte_scope() -> None:
    features = paper_core.build_n225_option_feature_records(
        [
            {
                "trading_date": "2026-01-05",
                "option_code": "OUTSIDE-DTE",
                "emergency_margin_trigger_division": "0",
                "strike_price": 100.0,
                "underlying_price": 100.0,
                "implied_volatility": 0.30,
                "open_interest": 1.0,
                "volume": 1.0,
                "put_call": "call",
                "central_contract_month_flag": True,
                "special_quotation_day": "2026-06-01",
                "vendor_available_ts_utc": "2026-01-06T03:00:00Z",
            },
            {
                "trading_date": "2026-01-05",
                "option_code": "OUTSIDE-DTE",
                "emergency_margin_trigger_division": "0",
                "strike_price": 100.0,
                "underlying_price": 100.0,
                "implied_volatility": 0.30,
                "open_interest": 1.0,
                "volume": 1.0,
                "put_call": "call",
                "central_contract_month_flag": True,
                "special_quotation_day": "2026-06-01",
                "vendor_available_ts_utc": "2026-01-06T03:00:00Z",
            },
        ]
    )
    no_cutoff_panel = paper_core.add_n225_option_features(
        [{"forecast_date": "2026-01-06", "model_cutoff_ts_utc": None}],
        features,
    )
    stale_panel = paper_core.add_n225_option_features(
        [
            {
                "forecast_date": "2026-01-20",
                "model_cutoff_ts_utc": datetime(2026, 1, 19, 21, tzinfo=UTC),
            }
        ],
        features,
    )

    assert features[0]["atm_iv"] is None
    assert features[0]["valid_contract_count"] == pytest.approx(0.0)
    assert features[0]["vendor_available_ts_utc"] == datetime(2026, 1, 6, 3, tzinfo=UTC)
    assert no_cutoff_panel[0]["n225_option_atm_iv_lag_1"] is None
    assert stale_panel[0]["n225_option_atm_iv_lag_1"] is None


def test_n225_option_normalization_handles_invalid_optional_fields() -> None:
    rows = paper_core.normalize_jquants_nikkei225_option_rows(
        [
            {"Date": "not-a-date", "Code": "SKIP"},
            {
                "Date": "2026-01-05",
                "Code": "INVALID-OPTIONAL",
                "CentralContractMonthFlag": "0",
                "StrikePrice": "not-a-number",
                "PutCallDivision": "9",
                "SettlementPrice": 0.0,
                "TheoreticalPrice": -1.0,
                "BaseVolatility": False,
                "UnderlyingPrice": "bad",
                "ImpliedVolatility": "bad",
                "InterestRate": "bad",
                "SpecialQuotationDay": "bad-date",
            },
        ],
        downloaded_at_utc=datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    assert len(rows) == 1
    assert rows[0]["central_contract_month_flag"] is False
    assert rows[0]["strike_price"] is None
    assert rows[0]["put_call"] is None
    assert rows[0]["settlement_price"] is None
    assert rows[0]["theoretical_price"] is None
    assert rows[0]["base_volatility"] is None
    assert rows[0]["underlying_price"] is None
    assert rows[0]["implied_volatility"] is None
    assert rows[0]["interest_rate"] is None
    assert rows[0]["special_quotation_day"] is None


def test_build_ml_tail_modeling_rows_uses_only_lagged_loss_history() -> None:
    panel_rows = [
        {
            "forecast_date": "2026-01-01",
            "clean_sample": True,
            "realized_loss": 1.0,
            "gap_t": -1.0,
            "dst_regime": "EST",
            "absorption_regime": "coincident_us_ose_night_close",
            "spy_return": 0.01,
        },
        {
            "forecast_date": "2026-01-02",
            "clean_sample": True,
            "realized_loss": 2.0,
            "gap_t": -2.0,
            "dst_regime": "EDT",
            "absorption_regime": "post_us_close_night_absorption",
            "spy_return": 0.02,
        },
    ]

    rows = build_ml_tail_modeling_rows(panel_rows, ["loss_lag_1", "spy_return"])

    assert rows[0]["loss_lag_1"] is None
    assert rows[1]["loss_lag_1"] == 1.0
    assert rows[1]["calendar_dst_edt"] == 1.0
    assert rows[1]["calendar_absorption_post_us_close"] == 1.0
    assert rows[1]["spy_return"] == 0.02


def test_n225_history_features_use_prior_clean_rows_and_insufficient_history() -> None:
    base_rows = [
        {
            "forecast_date": f"2026-01-{day:02d}",
            "clean_sample": True,
            "contract_month": "2026-03",
            "last_trading_day": "2026-03-12",
            "special_quotation_day": "2026-03-13",
            "day_session_open": 100.0 + day,
            "day_session_high": 102.0 + day,
            "day_session_low": 99.0 + day,
            "day_session_close": 101.0 + day,
            "night_session_open": 99.0 + day,
            "night_session_high": 101.0 + day,
            "night_session_low": 98.0 + day,
            "night_session_close": 100.0 + day,
            "volume": 100.0 + day,
            "open_interest": 1000.0 + day,
            "model_cutoff_ts_utc": datetime(2026, 1, day, 21, tzinfo=UTC),
            "jquants_vendor_available_ts_utc": datetime(2026, 1, day, 18, tzinfo=UTC),
        }
        for day in range(1, 4)
    ]

    enriched = add_n225_history_features(base_rows)
    mutated = [dict(row) for row in base_rows]
    mutated[1]["day_session_high"] = 999.0
    mutated_enriched = add_n225_history_features(mutated)

    assert enriched[0]["n225_day_return_lag_1"] is None
    assert enriched[1]["n225_day_return_lag_1"] == pytest.approx(math.log(102.0 / 101.0))
    assert enriched[1]["n225_day_range_lag_1"] == pytest.approx(math.log(103.0 / 100.0))
    assert enriched[1]["n225_volume_log1p_lag_1"] == pytest.approx(math.log1p(101.0))
    assert enriched[1]["n225_days_to_last_trade"] == float(
        (date(2026, 3, 12) - date(2026, 1, 2)).days
    )
    assert enriched[1]["n225_contract_month_sin"] == pytest.approx(math.sin(math.pi / 3.0))
    assert enriched[1]["n225_session_skew_120"] is None
    assert enriched[2]["n225_volume_zscore_60"] is None
    assert mutated_enriched[1]["n225_day_range_lag_1"] == enriched[1]["n225_day_range_lag_1"]
    assert mutated_enriched[2]["n225_day_range_lag_1"] != enriched[2]["n225_day_range_lag_1"]


def test_n225_history_features_compute_rolling_moments_and_controls() -> None:
    base_rows = []
    for index in range(123):
        forecast_date = date(2025, 1, 2) + timedelta(days=index)
        open_price = 100.0 + index * 0.2
        day_move = ((-1) ** index) * (0.001 + (index % 7) * 0.0002)
        night_move = ((-1) ** (index + 1)) * (0.0008 + (index % 5) * 0.0002)
        base_rows.append(
            {
                "forecast_date": forecast_date.isoformat(),
                "clean_sample": index != 60,
                "contract_month": "2025-03",
                "last_trading_day": "2025-03-12",
                "special_quotation_day": "2025-03-13",
                "day_session_open": open_price,
                "day_session_high": open_price * 1.01,
                "day_session_low": open_price * 0.99,
                "day_session_close": open_price * (1.0 + day_move),
                "night_session_open": open_price * 0.995,
                "night_session_high": open_price * 1.004,
                "night_session_low": open_price * 0.986,
                "night_session_close": open_price * 0.995 * (1.0 + night_move),
                "volume": 1000.0 + index * 3.0,
                "open_interest": 5000.0 + index * 2.0,
                "model_cutoff_ts_utc": datetime.combine(
                    forecast_date,
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                + timedelta(hours=21),
                "jquants_vendor_available_ts_utc": datetime(2025, 1, 2, 18, tzinfo=UTC)
                + timedelta(days=index),
            }
        )

    enriched = add_n225_history_features(base_rows)
    target = enriched[-1]

    assert target["n225_session_range_mean_20"] is not None
    assert target["n225_session_range_mean_5"] is not None
    assert target["n225_session_range_mean_10"] is not None
    assert target["n225_session_range_mean_60"] is not None
    assert target["n225_session_parkinson_var_mean_20"] is not None
    assert target["n225_session_parkinson_var_mean_60"] is not None
    assert target["n225_session_up_semivar_5"] is not None
    assert target["n225_session_up_semivar_20"] is not None
    assert target["n225_session_up_semivar_60"] is not None
    assert target["n225_session_down_semivar_20"] is not None
    assert target["n225_session_down_semivar_60"] is not None
    assert target["n225_session_skew_120"] is not None
    assert target["n225_session_excess_kurtosis_120"] is not None
    assert target["n225_volume_zscore_60"] is not None
    assert target["n225_open_interest_zscore_60"] is not None
    assert target["n225_volume_log_change_lag_1"] is not None
    assert target["n225_open_interest_log_change_lag_1"] is not None
    assert target["n225_volume_oi_ratio_lag_1"] is not None
    assert target["n225_days_to_sq"] == float((date(2025, 3, 13) - date(2025, 5, 4)).days)


def test_n225_history_tail_hit_counts_use_prior_rolling_threshold() -> None:
    rows = []
    start = date(2025, 1, 1)
    for index in range(253):
        current = start + timedelta(days=index)
        rows.append(
            {
                "forecast_date": current.isoformat(),
                "clean_sample": True,
                "realized_loss": float(index),
                "gap_t": float(index),
                "model_cutoff_ts_utc": datetime.combine(
                    current,
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                + timedelta(hours=21),
                "jquants_vendor_available_ts_utc": datetime.combine(
                    current,
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                + timedelta(hours=18),
            }
        )

    enriched = add_n225_history_features(rows)
    target = enriched[-1]

    assert enriched[251]["n225_left_tail_hit_count_20"] is None
    assert target["n225_left_tail_hit_count_20"] == pytest.approx(13.0)
    assert target["n225_left_tail_hit_count_60"] == pytest.approx(13.0)
    assert target["n225_right_tail_hit_count_20"] == pytest.approx(13.0)
    assert target["n225_right_tail_hit_count_60"] == pytest.approx(13.0)


def test_n225_history_features_null_invalid_ohlc_and_bad_dates() -> None:
    rows = [
        {
            "forecast_date": "2025-01-02",
            "clean_sample": True,
            "contract_month": "bad",
            "last_trading_day": "bad-date",
            "special_quotation_day": None,
            "day_session_open": 100.0,
            "day_session_high": 99.0,
            "day_session_low": 101.0,
            "day_session_close": 100.5,
            "night_session_open": 100.0,
            "night_session_high": 101.0,
            "night_session_low": 99.0,
            "night_session_close": 100.2,
            "volume": -1.0,
            "open_interest": 0.0,
            "model_cutoff_ts_utc": datetime(2025, 1, 2, 21, tzinfo=UTC),
            "jquants_vendor_available_ts_utc": datetime(2025, 1, 2, 18, tzinfo=UTC),
        },
        {
            "forecast_date": "2025-01-03",
            "clean_sample": True,
            "contract_month": "bad",
            "last_trading_day": "bad-date",
            "special_quotation_day": None,
            "day_session_open": 100.0,
            "day_session_high": 101.0,
            "day_session_low": 99.0,
            "day_session_close": 100.5,
            "night_session_open": 100.0,
            "night_session_high": 101.0,
            "night_session_low": 99.0,
            "night_session_close": 100.2,
            "volume": 1.0,
            "open_interest": 0.0,
            "model_cutoff_ts_utc": datetime(2025, 1, 3, 21, tzinfo=UTC),
        },
    ]

    enriched = add_n225_history_features(rows)

    assert enriched[1]["n225_day_range_lag_1"] is None
    assert enriched[1]["n225_day_parkinson_var_lag_1"] is None
    assert enriched[1]["n225_volume_log1p_lag_1"] is None
    assert enriched[1]["n225_volume_oi_ratio_lag_1"] is None
    assert enriched[1]["n225_days_to_last_trade"] is None
    assert enriched[1]["n225_contract_month_sin"] is None


def test_n225_history_features_respect_current_model_cutoff() -> None:
    rows = []
    for index, forecast_date in enumerate(("2025-01-06", "2025-01-07", "2025-01-08")):
        rows.append(
            {
                "forecast_date": forecast_date,
                "model_cutoff_ts_utc": datetime(2025, 1, 7, 21, tzinfo=UTC),
                "clean_sample": True,
                "contract_month": "2025-03",
                "last_trading_day": "2025-03-12",
                "special_quotation_day": "2025-03-13",
                "day_session_open": 100.0 + index,
                "day_session_high": 102.0 + index,
                "day_session_low": 99.0 + index,
                "day_session_close": 101.0 + index,
                "night_session_open": 100.0 + index,
                "night_session_high": 101.0 + index,
                "night_session_low": 99.0 + index,
                "night_session_close": 100.5 + index,
                "volume": 1000.0 + index,
                "open_interest": 5000.0 + index,
                "jquants_vendor_available_ts_utc": datetime(
                    2025,
                    1,
                    6 + index,
                    18 if index != 1 else 22,
                    tzinfo=UTC,
                ),
            }
        )

    enriched = add_n225_history_features(rows)

    assert enriched[2]["n225_day_return_lag_1__source_date"] == "2025-01-06"
    assert enriched[2]["n225_day_return_lag_1__available_ts_utc"] == datetime(
        2025, 1, 6, 18, tzinfo=UTC
    )
    assert enriched[2]["n225_day_return_lag_1"] == pytest.approx(math.log(101.0 / 100.0))


def test_n225_history_features_fail_closed_without_model_cutoff() -> None:
    rows = [
        {
            "forecast_date": "2025-01-06",
            "clean_sample": True,
            "contract_month": "2025-03",
            "last_trading_day": "2025-03-12",
            "special_quotation_day": "2025-03-13",
            "day_session_open": 100.0,
            "day_session_high": 102.0,
            "day_session_low": 99.0,
            "day_session_close": 101.0,
            "night_session_open": 100.0,
            "night_session_high": 101.0,
            "night_session_low": 99.0,
            "night_session_close": 100.5,
            "jquants_vendor_available_ts_utc": datetime(2025, 1, 6, 18, tzinfo=UTC),
        },
        {
            "forecast_date": "2025-01-07",
            "clean_sample": True,
            "contract_month": "2025-03",
            "last_trading_day": "2025-03-12",
            "special_quotation_day": "2025-03-13",
        },
    ]

    enriched = add_n225_history_features(rows)

    assert enriched[1]["n225_day_return_lag_1"] is None
    assert "n225_days_to_sq__available_ts_utc" not in enriched[1]


def test_event_calendar_features_respect_known_and_release_timestamps() -> None:
    records = [
        EventCalendarRecord(
            event_date=date(2026, 1, 2),
            event_type="nfp",
            event_name="NFP",
            affects_session="us",
            release_ts_utc=datetime(2026, 1, 2, 13, 30, tzinfo=UTC),
            known_ts_utc=datetime(2025, 12, 1, tzinfo=UTC),
            source_note="test",
        ),
        EventCalendarRecord(
            event_date=date(2026, 1, 3),
            event_type="cpi",
            event_name="CPI",
            affects_session="us",
            release_ts_utc=datetime(2026, 1, 3, 13, 30, tzinfo=UTC),
            known_ts_utc=datetime(2026, 1, 2, 22, tzinfo=UTC),
            source_note="test",
        ),
        EventCalendarRecord(
            event_date=date(2026, 1, 5),
            event_type="boj",
            event_name="BOJ",
            affects_session="ose",
            release_ts_utc=datetime(2026, 1, 5, 3, tzinfo=UTC),
            known_ts_utc=datetime(2025, 12, 1, tzinfo=UTC),
            source_note="test",
        ),
    ]
    panel = [
        {
            "forecast_date": "2026-01-02",
            "us_calendar_date": "2026-01-02",
            "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, tzinfo=UTC),
        },
        {
            "forecast_date": "2026-01-05",
            "us_calendar_date": "2026-01-02",
            "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC),
        },
    ]

    enriched = add_event_calendar_features(panel, event_records=records)

    assert enriched[0]["event_nfp_same_us_session"] == 1
    assert enriched[0]["event_cpi_same_us_session"] == 0
    assert enriched[0]["event_cpi_same_us_session__available_ts_utc"] == datetime(
        2026, 1, 2, 21, tzinfo=UTC
    )
    assert enriched[0]["event_major_count_next_3d"] == 2
    assert enriched[0]["event_days_to_next_major"] == 0
    assert enriched[0]["event_nfp_same_us_session__available_ts_utc"] == datetime(
        2026, 1, 2, 13, 30, tzinfo=UTC
    )
    assert enriched[1]["event_boj_same_ose_session"] == 1
    assert enriched[1]["event_days_since_previous_major"] == 2


def test_event_calendar_loader_validation_and_missing_dates(tmp_path: Path) -> None:
    assert load_event_calendar(tmp_path / "missing.csv") == []
    good_path = tmp_path / "events.csv"
    good_path.write_text(
        "\n".join(
            [
                "event_date,event_type,event_name,affects_session,release_ts_utc,known_ts_utc,source_note",
                "2026-01-02,nfp,NFP,us,2026-01-02T13:30:00,2025-12-31T00:00:00,manual",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_event_calendar(good_path)
    assert loaded[0].known_ts_utc == datetime(2025, 12, 31, tzinfo=UTC)

    missing_column_path = tmp_path / "missing_column.csv"
    missing_column_path.write_text("event_date,event_type\n2026-01-02,nfp\n", encoding="utf-8")
    with pytest.raises(paper_module.PipelineRunError, match="missing columns"):
        load_event_calendar(missing_column_path)

    bad_rows = {
        "bad_date": (
            "bad-date,nfp,NFP,us,2026-01-02T13:30:00+00:00,2025-12-31T00:00:00+00:00,manual"
        ),
        "bad_type": (
            "2026-01-02,bad,NFP,us,2026-01-02T13:30:00+00:00,2025-12-31T00:00:00+00:00,manual"
        ),
        "bad_session": (
            "2026-01-02,nfp,NFP,bad,2026-01-02T13:30:00+00:00,2025-12-31T00:00:00+00:00,manual"
        ),
        "bad_timestamp": "2026-01-02,nfp,NFP,us,not-a-time,2025-12-31T00:00:00+00:00,manual",
    }
    for name, row_text in bad_rows.items():
        bad_path = tmp_path / f"{name}.csv"
        bad_path.write_text(
            "event_date,event_type,event_name,affects_session,release_ts_utc,known_ts_utc,source_note\n"
            f"{row_text}\n",
            encoding="utf-8",
        )
        with pytest.raises(paper_module.PipelineRunError):
            load_event_calendar(bad_path)

    enriched = add_event_calendar_features(
        [
            {
                "forecast_date": "bad-date",
                "us_calendar_date": date(2026, 1, 2),
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21),
            }
        ],
        event_records=loaded,
    )
    assert enriched[0]["event_major_count_next_3d"] is None
    assert enriched[0]["event_days_to_next_major"] is None
    assert enriched[0]["event_nfp_same_us_session"] == 1


def test_cross_market_features_use_partial_aggregation_and_metadata() -> None:
    enough_components = {
        "forecast_date": "2026-01-05",
        "clean_sample": True,
        "spy_return": 0.01,
        "qqq_return": 0.02,
        "dia_return": 0.00,
        "iwm_return": None,
        "xlk_return": 0.01,
        "xlf_return": 0.02,
        "xle_return": 0.03,
        "xlv_return": 0.04,
        "xli_return": 0.05,
        "xly_return": 0.06,
        "xlp_return": None,
        "xlb_return": None,
        "xlu_return": None,
        "xlc_return": None,
        "ewj_return": 0.015,
        "dxj_return": 0.004,
        "eem_return": 0.01,
        "fxi_return": -0.01,
        "ewy_return": 0.02,
        "ewt_return": None,
        "ewh_return": None,
        "cboe_vix_close": 20.0,
        "spy_return__available_ts_utc": datetime(2026, 1, 2, 21, tzinfo=UTC),
        "qqq_return__available_ts_utc": datetime(2026, 1, 2, 21, 5, tzinfo=UTC),
        "dia_return__available_ts_utc": datetime(2026, 1, 2, 21, 10, tzinfo=UTC),
        "spy_return__source_date": "2026-01-02",
        "qqq_return__source_date": "2026-01-02",
        "dia_return__source_date": "2026-01-02",
    }
    insufficient_components = {
        **enough_components,
        "forecast_date": "2026-01-06",
        "spy_return": 0.01,
        "qqq_return": None,
        "dia_return": None,
        "iwm_return": None,
        "xle_return": None,
        "xlv_return": None,
        "xli_return": None,
        "xly_return": None,
        "eem_return": 0.01,
        "fxi_return": None,
        "ewy_return": None,
    }

    enriched = add_cross_market_features([enough_components, insufficient_components])

    assert enriched[0]["xmarket_us_core_return_mean_1d"] == pytest.approx(0.01)
    assert enriched[0]["xmarket_us_sector_return_dispersion_1d"] is not None
    assert enriched[0]["xmarket_japan_proxy_ewj_spy_spread_1d"] == pytest.approx(0.005)
    assert enriched[0]["xmarket_asia_proxy_return_dispersion_1d"] is not None
    assert enriched[0]["xmarket_us_core_return_mean_1d__fill_method"] == ("derived_panel_aggregate")
    assert enriched[0]["xmarket_us_core_return_mean_1d__available_ts_utc"] == datetime(
        2026, 1, 2, 21, 10, tzinfo=UTC
    )
    assert enriched[1]["xmarket_us_core_return_mean_1d"] is None
    assert enriched[1]["xmarket_asia_proxy_return_dispersion_1d"] is None


def test_feature_audit_reports_coverage_gate_and_baseline_delta(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "tailrisk_current"
    baseline_dir = tmp_path / "reports" / "runs" / "tailrisk_baseline"
    (run_dir / "panel").mkdir(parents=True)
    (run_dir / "forecasts").mkdir(parents=True)
    (baseline_dir / "panel").mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "feature": "event_nfp_same_us_session",
                "source_family": "event_calendar",
                "source_block": "calendar_controls",
                "missingness_rate": 0.0,
                "non_missing_rows": 10,
            },
            {
                "feature": "xmarket_us_core_return_mean_1d",
                "source_family": "cross_market_derived",
                "source_block": "us_core",
                "missingness_rate": 0.2,
                "non_missing_rows": 8,
            },
        ]
    ).write_parquet(run_dir / "panel" / "feature_coverage.parquet")
    pl.DataFrame(
        [
            {
                "information_set": "japan_only",
                "candidate_feature_hash": "candidate-a",
                "active_feature_hash": "active-a",
                "dropped_features_json": json.dumps(
                    [
                        {
                            "feature": "xmarket_us_core_return_mean_1d",
                            "drop_reason": "high_training_missingness",
                        }
                    ]
                ),
                "scale_dropped_features_json": json.dumps(
                    [
                        {
                            "feature": "xmarket_us_core_return_mean_1d",
                            "drop_reason": "high_training_missingness",
                        },
                        {
                            "feature": "None",
                            "drop_reason": "malformed_optional_row",
                        },
                    ]
                ),
            }
        ]
    ).write_parquet(run_dir / "forecasts" / "ml_tail_fit_diagnostics.parquet")
    pl.DataFrame(
        [
            {
                "feature": "n225_day_range_lag_1",
                "source_family": "japan_history",
                "source_block": "japan_only",
                "missingness_rate": 0.0,
                "non_missing_rows": 10,
            }
        ]
    ).write_parquet(baseline_dir / "panel" / "feature_coverage.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"window": ["2026-01-01", "2026-01-31"]}),
        encoding="utf-8",
    )
    (baseline_dir / "manifest.json").write_text(
        json.dumps({"window": ["2025-01-01", "2025-01-31"]}),
        encoding="utf-8",
    )

    result = write_feature_audit(run_dir=run_dir, baseline_run_dir=baseline_dir)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.feature_count == 2
    assert result.block_count == 2
    assert result.warning_count == 1
    assert "date range mismatch" in payload["warnings"][0]
    assert payload["feature_delta_summary"]["added_features"] == [
        "event_nfp_same_us_session",
        "xmarket_us_core_return_mean_1d",
    ]
    assert payload["ml_tail_gate_summary"]["dropped_feature_count"] == 1


def test_feature_audit_fails_clearly_when_coverage_is_missing(tmp_path: Path) -> None:
    with pytest.raises(paper_module.PipelineRunError, match="Missing feature coverage artifact"):
        write_feature_audit(run_dir=tmp_path / "empty_run")


def test_feature_audit_handles_empty_coverage_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "tailrisk_empty"
    (run_dir / "panel").mkdir(parents=True)
    (run_dir / "forecasts").mkdir(parents=True)
    pl.DataFrame(schema={"feature": pl.String}).write_parquet(
        run_dir / "panel" / "feature_coverage.parquet"
    )
    pl.DataFrame(
        schema={
            "information_set": pl.String,
            "candidate_feature_hash": pl.String,
            "active_feature_hash": pl.String,
            "dropped_features_json": pl.String,
        }
    ).write_parquet(run_dir / "forecasts" / "ml_tail_fit_diagnostics.parquet")

    result = write_feature_audit(run_dir=run_dir)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.feature_count == 0
    assert result.block_count == 0
    assert payload["block_summary"] == []


def test_feature_audit_handles_bad_optional_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "tailrisk_current"
    baseline_dir = tmp_path / "reports" / "runs" / "tailrisk_baseline"
    (run_dir / "panel").mkdir(parents=True)
    (run_dir / "forecasts").mkdir(parents=True)
    (baseline_dir / "panel").mkdir(parents=True)
    coverage = pl.DataFrame(
        [
            {
                "feature": "event_nfp_same_us_session",
                "source_family": "event_calendar",
                "source_block": "calendar_controls",
                "missingness_rate": 0.0,
                "non_missing_rows": 10,
            }
        ]
    )
    coverage.write_parquet(run_dir / "panel" / "feature_coverage.parquet")
    coverage.write_parquet(baseline_dir / "panel" / "feature_coverage.parquet")
    pl.DataFrame(
        [
            {
                "information_set": "japan_only",
                "candidate_feature_hash": "candidate-a",
                "active_feature_hash": "active-a",
                "dropped_features_json": "not-json",
            },
            {
                "information_set": "japan_only",
                "candidate_feature_hash": "candidate-a",
                "active_feature_hash": "active-a",
                "dropped_features_json": json.dumps({"not": "a-list"}),
            },
            {
                "information_set": "japan_only",
                "candidate_feature_hash": "candidate-a",
                "active_feature_hash": "active-a",
                "dropped_features_json": json.dumps([{"feature": "ok"}, "bad"]),
            },
        ]
    ).write_parquet(run_dir / "forecasts" / "ml_tail_fit_diagnostics.parquet")
    (run_dir / "manifest.json").write_text("{bad-json", encoding="utf-8")
    (baseline_dir / "manifest.json").write_text(json.dumps({"window": "bad"}), encoding="utf-8")

    result = write_feature_audit(run_dir=run_dir, baseline_run_dir=baseline_dir)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.warning_count == 0
    assert payload["ml_tail_gate_summary"]["dropped_feature_count"] == 1
    assert payload["feature_delta_summary"]["available"] is True

    missing_baseline = tmp_path / "reports" / "runs" / "tailrisk_missing_baseline"
    result = write_feature_audit(run_dir=run_dir, baseline_run_dir=missing_baseline)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert result.warning_count == 1
    assert payload["feature_delta_summary"]["reason"] == "missing_baseline_feature_coverage"


def test_worker_payload_rejects_dataframe_objects() -> None:
    validate_worker_payload({"panel_path": "/tmp/panel.parquet", "tail_level": 0.95})
    with pytest.raises(paper_module.PipelineRunError, match="Polars frame"):
        validate_worker_payload({"frame": pl.DataFrame({"x": [1]})})


def test_build_modeling_panel_records_and_feature_coverage() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-05",
                "contract_code": "161030018",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
                "full_gap_close_to_open": -0.02,
                "residual_nightclose_to_day_open": -0.001,
                "volume": 100.0,
                "open_interest": 1000.0,
                "volume_oi_anomaly": None,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-05",
                "us_calendar_date": "2026-01-02",
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 30, tzinfo=UTC),
                "dst_regime": "EST",
                "absorption_regime": "coincident_close",
            }
        ],
        massive_daily_records=[
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-01",
                "bar_end_ts_utc": datetime(2026, 1, 1, 21, 0, tzinfo=UTC),
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
            },
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-02",
                "bar_end_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "close": 101.0,
                "high": 102.0,
                "low": 100.0,
            },
            {
                "ticker": "EWJ",
                "bar_date_et": "2026-01-01",
                "bar_end_ts_utc": datetime(2026, 1, 1, 21, 0, tzinfo=UTC),
                "close": 70.0,
                "high": 71.0,
                "low": 69.0,
            },
            {
                "ticker": "EWJ",
                "bar_date_et": "2026-01-02",
                "bar_end_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "close": 71.0,
                "high": 72.0,
                "low": 70.0,
            },
            {
                "ticker": "EWH",
                "bar_date_et": "2026-01-01",
                "bar_end_ts_utc": datetime(2026, 1, 1, 21, 0, tzinfo=UTC),
                "close": 20.0,
                "high": 20.5,
                "low": 19.5,
            },
            {
                "ticker": "EWH",
                "bar_date_et": "2026-01-02",
                "bar_end_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "close": 20.2,
                "high": 20.4,
                "low": 19.9,
            },
        ],
        minute_feature_records=[],
        fred_records=[
            {
                "series_id": "VIXCLS",
                "observation_date": "2026-01-02",
                "vendor_available_date_et": "2026-01-02",
                "vendor_available_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "value": 18.0,
            }
        ],
    )
    coverage = build_feature_coverage_records(panel)

    assert panel[0]["forecast_date"] == "2026-01-05"
    assert panel[0]["spy_return"] is not None
    assert panel[0]["spy_return__fill_method"] == "direct"
    assert panel[0]["fred_vixcls_level"] == 18.0
    assert panel[0]["residual_usclosemark_to_open"] is None
    assert panel[0]["residual_usclosemark_status"] == ("disabled_requires_licensed_intraday_mark")
    assert any(row["feature"] == "spy_return" for row in coverage)
    spy_coverage = next(row for row in coverage if row["feature"] == "spy_return")
    assert spy_coverage["source_family"] == "massive_daily"
    assert spy_coverage["source_block"] == "us_core"
    assert spy_coverage["vintage_safe"] is True
    ewj_coverage = next(row for row in coverage if row["feature"] == "ewj_return")
    assert ewj_coverage["source_family"] == "japan_proxy"
    assert ewj_coverage["source_block"] == "japan_proxy"
    ewh_coverage = next(row for row in coverage if row["feature"] == "ewh_return")
    assert ewh_coverage["source_family"] == "asia_proxy"
    assert ewh_coverage["source_block"] == "asia_proxy"


def test_fred_asof_fill_skips_null_ghost_row_and_records_metadata() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-06",
                "contract_code": "161030018",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-06",
                "us_calendar_date": "2026-01-05",
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, 30, tzinfo=UTC),
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "dst_regime": "EST",
                "absorption_regime": "coincident_close",
            }
        ],
        massive_daily_records=[],
        minute_feature_records=[],
        fred_records=[
            {
                "series_id": "DGS10",
                "observation_date": "2026-01-02",
                "vendor_available_date_et": "2026-01-02",
                "vendor_available_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "value": 4.0,
            },
            {
                "series_id": "DGS10",
                "observation_date": "2026-01-05",
                "vendor_available_date_et": "2026-01-05",
                "vendor_available_ts_utc": datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
                "value": None,
            },
        ],
    )

    row = panel[0]
    assert row["fred_dgs10_level"] == 4.0
    assert row["fred_dgs10_diff"] == 0.0
    assert row["fred_dgs10_level__fill_method"] == "forward_fill_fred_release_lag"
    assert row["fred_dgs10_level__fill_source_obs_date"] == "2026-01-02"
    assert row["fred_dgs10_level__fill_feature_available_ts_utc"] == datetime(
        2026,
        1,
        2,
        21,
        0,
        tzinfo=UTC,
    )
    assert row["fred_dgs10_diff__is_filled_diff"] is True
    assert row["fred_rates_staleness_days"] == 3.0


def test_fred_asof_fill_enforces_cutoff_and_fill_cap() -> None:
    features = paper_core._fred_feature_map(
        [
            {
                "series_id": "DGS2",
                "observation_date": "2026-01-02",
                "vendor_available_date_et": "2026-01-02",
                "vendor_available_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "value": 3.0,
            },
            {
                "series_id": "DGS2",
                "observation_date": "2026-01-09",
                "vendor_available_date_et": "2026-01-09",
                "vendor_available_ts_utc": datetime(2026, 1, 9, 22, 0, tzinfo=UTC),
                "value": 3.1,
            },
        ]
    )

    assert (
        paper_core._fred_features_asof(features, "", cutoff=datetime(2026, 1, 9, tzinfo=UTC)) == {}
    )
    assert (
        paper_core._fred_features_asof(
            features, "bad-date", cutoff=datetime(2026, 1, 9, tzinfo=UTC)
        )
        == {}
    )
    assert paper_core._fred_features_asof(features, "2026-01-09", cutoff=None) == {}
    cutoff_before_new_release = datetime(2026, 1, 9, 21, 30, tzinfo=UTC)
    filled = paper_core._fred_features_asof(
        features,
        "2026-01-09",
        cutoff=cutoff_before_new_release,
    )
    assert filled is not None
    assert filled["fred_dgs2_level"] == 3.0
    assert filled["fred_dgs2_level__fill_method"] == "forward_fill_fred_release_lag"
    assert (
        paper_core._fred_features_asof(
            features,
            "2026-01-10",
            cutoff=datetime(2026, 1, 10, 21, 30, tzinfo=UTC),
        )["fred_dgs2_level"]
        == 3.1
    )
    assert (
        paper_core._fred_features_asof(
            features,
            "2026-01-20",
            cutoff=datetime(2026, 1, 20, 21, 30, tzinfo=UTC),
        )
        == {}
    )


def test_fields_coverage_audit_supports_clean_jquants_start() -> None:
    rows = [
        {
            "trading_date": "2016-07-19",
            "settlement_price": 100.0,
            "last_trading_day": "2016-09-08",
            "special_quotation_day": "2016-09-09",
            "central_contract_month_flag": True,
        }
        for _ in range(20)
    ]

    audit = build_fields_coverage_audit_records(rows, policy_start="2016-07-19")

    assert audit
    assert all(
        row["coverage_supports_policy_start"] is True
        for row in audit
        if row["sample"] == "policy_start_forward"
    )


def test_target_audit_requires_immediate_previous_jpx_session() -> None:
    rows = [
        _normalized_target_row("2026-01-05", day_open=100.0, settle=100.0),
        _normalized_target_row("2026-01-07", day_open=102.0, settle=102.0),
    ]
    calendar = _jpx_calendar_records(
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-03-10",
        "2026-03-11",
        "2026-03-12",
        "2026-03-13",
    )

    targets = paper_core.build_target_audit_records(
        rows,
        calendar_records=calendar,
        roll_days_before_last_trade=3,
    )

    assert targets[1]["reference_date"] is None
    assert targets[1]["full_gap_settle_to_open"] is None
    assert targets[1]["clean_sample"] is False
    assert targets[1]["missing_reason"] == "missing_previous_jpx_session"


def test_target_audit_fails_closed_when_roll_calendar_is_truncated() -> None:
    rows = [
        _normalized_target_row("2026-01-05", day_open=100.0, settle=100.0),
        _normalized_target_row("2026-01-06", day_open=101.0, settle=101.0),
    ]

    targets = paper_core.build_target_audit_records(
        rows,
        calendar_records=_jpx_calendar_records("2026-01-05", "2026-01-06"),
        roll_days_before_last_trade=3,
    )

    assert targets[1]["is_roll_sq_window"] is True
    assert targets[1]["clean_sample"] is False
    assert "roll_sq_excluded" in str(targets[1]["missing_reason"])


def test_target_audit_rejects_duplicate_target_keys() -> None:
    rows = [
        _normalized_target_row("2026-01-05", day_open=100.0, settle=100.0),
        _normalized_target_row("2026-01-05", day_open=101.0, settle=101.0),
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        paper_core.build_target_audit_records(
            rows,
            calendar_records=_jpx_calendar_records("2026-01-05", "2026-03-13"),
            roll_days_before_last_trade=3,
        )


def test_target_audit_calendar_horizon_ignores_far_noncentral_contracts() -> None:
    base_calendar = _jpx_calendar_records("2026-05-08")
    rows = [
        {
            **_normalized_target_row("2026-05-08", day_open=100.0, settle=99.0),
            "last_trading_day": "2026-05-08",
            "special_quotation_day": "2026-05-08",
        },
        {
            **_normalized_target_row(
                "2026-05-08",
                day_open=100.0,
                settle=99.0,
                contract_code="far-contract",
            ),
            "central_contract_month_flag": False,
            "last_trading_day": "2033-12-08",
            "special_quotation_day": "2033-12-09",
        },
    ]

    calendar = panel_build_helpers.target_audit_calendar_records(
        settings=Settings(),
        base_calendar_records=base_calendar,
        normalized_rows=rows,
        start="2026-05-08",
        end="2026-05-08",
    )

    assert calendar == base_calendar


def test_spy_minute_features_use_official_early_close_and_exclude_after_hours() -> None:
    official_close = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    records = []
    for minute in range(90):
        end_ts = official_close - timedelta(minutes=89 - minute)
        records.append(
            {
                "bar_date_et": "2026-11-27",
                "bar_end_ts_utc": end_ts,
                "is_us_regular_session": True,
                "close": 100.0 + minute,
                "high": 101.0 + minute,
                "low": 99.0 + minute,
                "volume": 1000.0,
            }
        )
    records.append(
        {
            "bar_date_et": "2026-11-27",
            "bar_end_ts_utc": official_close + timedelta(hours=3),
            "is_us_regular_session": False,
            "close": 999.0,
            "high": 999.0,
            "low": 999.0,
            "volume": 1.0,
        }
    )

    features = build_spy_compat_late_session_feature_records(
        records,
        calendar_records=[
            {
                "calendar_date": "2026-11-27",
                "us_close_ts_utc": official_close,
            }
        ],
        vendor_lag_minutes=5,
    )

    assert len(features) == 1
    assert features[0]["selected_close_bar_end_ts_utc"] == official_close
    assert features[0]["feature_available_ts_utc"] == official_close + timedelta(minutes=5)
    assert features[0]["close"] != 999.0
    assert features[0]["spy_late_30m_return"] is not None


def test_generic_minute_builder_computes_moments_and_per_ticker_volume_features() -> None:
    minute_records = []
    for day_index, day in enumerate(("2026-01-02", "2026-01-05", "2026-01-06")):
        day_date = date.fromisoformat(day)
        official_close = datetime(day_date.year, day_date.month, day_date.day, 21, 0, tzinfo=UTC)
        volume = 10.0 * (day_index + 1)
        for minute in range(61):
            close = 100.0 + day_index + minute * 0.02 + ((-1) ** minute) * 0.1
            minute_records.append(
                {
                    "ticker": "QQQ",
                    "bar_date_et": day,
                    "bar_end_ts_utc": official_close - timedelta(minutes=60 - minute),
                    "is_us_regular_session": True,
                    "close": close,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "volume": volume,
                }
            )
        minute_records.append(
            {
                "ticker": "QQQ",
                "bar_date_et": day,
                "bar_end_ts_utc": official_close + timedelta(hours=1),
                "is_us_regular_session": False,
                "close": 999.0,
                "high": 999.0,
                "low": 999.0,
                "volume": 999.0,
            }
        )

    features = build_feature_minute_records(
        minute_records,
        calendar_records=[
            {
                "calendar_date": day,
                "us_close_ts_utc": datetime(
                    date.fromisoformat(day).year,
                    date.fromisoformat(day).month,
                    date.fromisoformat(day).day,
                    21,
                    0,
                    tzinfo=UTC,
                ),
            }
            for day in ("2026-01-02", "2026-01-05", "2026-01-06")
        ],
        vendor_lag_minutes=15,
        ticker="QQQ",
    )

    assert len(features) == 3
    assert features[-1]["safe_ticker"] == "qqq"
    assert features[-1]["selected_close_bar_end_ts_utc"] == datetime(2026, 1, 6, 21, 0, tzinfo=UTC)
    assert features[-1]["feature_available_ts_utc"] == datetime(2026, 1, 6, 21, 15, tzinfo=UTC)
    assert features[-1]["close"] != 999.0
    assert features[-1]["late_60m_realized_var"] is not None
    assert features[-1]["late_60m_up_semivar"] > 0.0
    assert features[-1]["late_60m_down_semivar"] > 0.0
    assert features[-1]["late_60m_skew"] is not None
    assert features[-1]["late_60m_excess_kurtosis"] is not None
    assert features[-1]["late_volume_surge"] == pytest.approx(2.0)
    assert features[-1]["late_volume_zscore_20"] is not None
    assert features[-1]["late_volume_percentile_20"] == pytest.approx(1.0)


def test_massive_daily_features_use_official_early_close_availability() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-11-30",
                "contract_code": "c1",
                "contract_month": "2026-12",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 11, 29, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-11-30",
                "us_calendar_date": "2026-11-27",
                "model_cutoff_ts_utc": datetime(2026, 11, 27, 18, 15, tzinfo=UTC),
            }
        ],
        massive_daily_records=[
            {
                "ticker": "SPY",
                "bar_date_et": "2026-11-25",
                "bar_end_ts_utc": datetime(2026, 11, 25, 21, 0, tzinfo=UTC),
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
            },
            {
                "ticker": "SPY",
                "bar_date_et": "2026-11-27",
                "bar_end_ts_utc": datetime(2026, 11, 27, 21, 0, tzinfo=UTC),
                "close": 101.0,
                "high": 102.0,
                "low": 100.0,
            },
        ],
        minute_feature_records=[],
        fred_records=[],
        calendar_records=[
            {
                "calendar_date": "2026-11-27",
                "us_close_ts_utc": datetime(2026, 11, 27, 18, 0, tzinfo=UTC),
            }
        ],
    )

    assert panel[0]["spy_return"] is not None
    assert panel[0]["spy_return__available_ts_utc"] == datetime(
        2026,
        11,
        27,
        18,
        15,
        tzinfo=UTC,
    )
    assert not [row for row in build_leakage_check_records(panel) if row["status"] == "fail"]


def test_modeling_panel_forward_fills_us_holiday_features_and_leakage_gate() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-06",
                "contract_code": "161030018",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-06",
                "us_calendar_date": "2026-01-05",
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, 30, tzinfo=UTC),
                "dst_regime": "EST",
                "absorption_regime": "coincident_close",
            }
        ],
        massive_daily_records=[
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-02",
                "bar_end_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
            },
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-03",
                "bar_end_ts_utc": datetime(2026, 1, 3, 21, 0, tzinfo=UTC),
                "close": 101.0,
                "high": 102.0,
                "low": 100.0,
            },
        ],
        minute_feature_records=[],
        fred_records=[],
    )

    assert panel[0]["spy_return__fill_method"] == "forward_fill_us_holiday"
    leakage_rows = build_leakage_check_records(panel)
    assert leakage_rows
    assert {row["status"] for row in leakage_rows} <= {"pass", "warn"}


def test_leakage_check_warns_when_missing_feature_has_no_timestamp() -> None:
    rows = build_leakage_check_records(
        [
            {
                "forecast_date": "2026-01-05",
                "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 15, tzinfo=UTC),
                "x_return": None,
                "x_return__available_ts_utc": None,
            }
        ]
    )

    assert rows[0]["status"] == "warn"
    assert rows[0]["reason"] == "missing_feature_value_not_evaluable"


def test_leakage_check_reports_positive_lead_after_cutoff() -> None:
    rows = build_leakage_check_records(
        [
            {
                "forecast_date": "2026-01-05",
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, 15, tzinfo=UTC),
                "x_return": 0.01,
                "x_return__available_ts_utc": datetime(2026, 1, 5, 21, 20, tzinfo=UTC),
            }
        ]
    )

    assert rows[0]["status"] == "fail"
    assert rows[0]["reason"] == "feature_available_after_model_cutoff"
    assert rows[0]["lag_minutes"] == pytest.approx(5.0)


def test_leakage_check_reports_row_cutoff_without_feature_timestamps() -> None:
    rows = build_leakage_check_records(
        [
            {
                "forecast_date": "2026-01-05",
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "model_cutoff_ts_utc": datetime(2026, 1, 6, 0, 0, tzinfo=UTC),
                "x_return": 0.01,
            }
        ]
    )

    assert rows[0]["feature_name"] == "__row_cutoff_invariant__"
    assert rows[0]["status"] == "fail"
    assert rows[0]["reason"] == "model_cutoff_not_before_target_open"


def test_modeling_panel_records_calendar_join_miss_reason() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-06",
                "contract_code": "c1",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
            }
        ],
        alignment_records=[],
        massive_daily_records=[],
        minute_feature_records=[],
        fred_records=[],
    )

    assert panel[0]["join_miss_reason"] == "calendar_desync"


def test_modeling_panel_records_reject_duplicate_target_dates() -> None:
    target = {
        "trading_date": "2026-01-06",
        "contract_code": "c1",
        "contract_month": "2026-03",
        "clean_sample": True,
        "same_contract_only": True,
        "is_roll_sq_window": False,
        "missing_reason": None,
        "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
        "full_gap_settle_to_open": -0.01,
        "loss_settle_to_open": 0.01,
    }

    with pytest.raises(paper_module.PipelineRunError, match="Duplicate target rows"):
        build_modeling_panel_records(
            target_rows=[target, dict(target)],
            alignment_records=[],
            massive_daily_records=[],
            minute_feature_records=[],
            fred_records=[],
        )


def test_forecast_sample_reason_priority_and_calendar_map_propagation() -> None:
    target_open = datetime(2026, 1, 5, 23, 45, tzinfo=UTC)
    cutoff = datetime(2026, 1, 2, 21, 30, tzinfo=UTC)

    assert (
        paper_core._forecast_sample_exclusion_reason(
            target_clean=False,
            mapping_status="us_holiday",
            join_miss_reason="calendar_desync",
            cutoff=None,
            target_open=None,
        )
        == "target_not_clean"
    )
    assert (
        paper_core._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="us_holiday",
            join_miss_reason="calendar_desync",
            cutoff=cutoff,
            target_open=target_open,
        )
        == "mapping_status_not_normal_trading"
    )
    assert (
        paper_core._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="normal_trading",
            join_miss_reason="calendar_desync",
            cutoff=cutoff,
            target_open=target_open,
        )
        == "has_join_miss_reason"
    )
    assert (
        paper_core._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="normal_trading",
            join_miss_reason=None,
            cutoff=None,
            target_open=target_open,
        )
        == "missing_cutoff_or_target_open"
    )
    assert (
        paper_core._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="normal_trading",
            join_miss_reason=None,
            cutoff=target_open,
            target_open=target_open,
        )
        == "cutoff_after_target_open"
    )

    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-06",
                "contract_code": "c1",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": target_open,
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-06",
                "us_calendar_date": "2026-01-02",
                "model_cutoff_ts_utc": cutoff,
            }
        ],
        calendar_map_records=[
            {
                "ose_trading_date": "2026-01-06",
                "mapping_status": "us_holiday",
                "mapping_reason": "us_closed_jpx_open",
            }
        ],
        massive_daily_records=[],
        minute_feature_records=[],
        fred_records=[],
    )

    assert panel[0]["mapping_status"] == "us_holiday"
    assert panel[0]["mapping_reason"] == "us_closed_jpx_open"
    assert panel[0]["forecast_sample"] is False
    assert panel[0]["forecast_sample_reason"] == "mapping_status_not_normal_trading"


def test_canonical_fx_uses_fred_h10_latest_released_and_ignores_massive_fx() -> None:
    context = paper_core._canonical_fx_context(
        massive_daily_records=[
            {
                "ticker": "C:USDJPY",
                "bar_date_et": "2026-01-12",
                "close": 161.0,
                "bar_end_ts_utc": datetime(2026, 1, 12, 21, tzinfo=UTC),
            }
        ],
        fred_records=[
            {
                "series_id": "DEXJPUS",
                "observation_date": "2026-01-09",
                "vendor_available_ts_utc": datetime(2026, 1, 12, 21, 15, tzinfo=UTC),
                "value": 160.0,
            }
        ],
        calendar_records=[
            {
                "calendar_date": "2026-01-12",
                "us_close_ts_utc": datetime(2026, 1, 12, 21, tzinfo=UTC),
            }
        ],
    )

    fx = paper_core._canonical_fx_asof(
        context,
        us_date="2026-01-12",
        cutoff=datetime(2026, 1, 12, 21, 30, tzinfo=UTC),
    )

    assert fx["fx_source"] == "fred_h10_latest_released"
    assert fx["fx_usdjpy_level"] == 160.0
    assert fx["fx_staleness_days"] == 3
    assert fx["fx_release_age_days"] == 0


def test_canonical_fx_uses_latest_released_fred_when_same_day_row_unreleased() -> None:
    fred_rows = [
        {
            "series_id": "DEXJPUS",
            "observation_date": "2026-01-09",
            "vendor_available_ts_utc": datetime(2026, 1, 12, 21, 15, tzinfo=UTC),
            "value": 160.0,
        },
        {
            "series_id": "DEXJPUS",
            "observation_date": "2026-01-12",
            "vendor_available_ts_utc": datetime(2026, 1, 19, 21, 15, tzinfo=UTC),
            "value": None,
        },
    ]
    calendar_records = [
        {
            "calendar_date": "2026-01-12",
            "us_close_ts_utc": datetime(2026, 1, 12, 21, tzinfo=UTC),
        }
    ]
    context = paper_core._canonical_fx_context(
        massive_daily_records=[
            {
                "ticker": "C:USDJPY",
                "bar_date_et": "2026-01-09",
                "close": 160.0,
                "bar_end_ts_utc": datetime(2026, 1, 9, 21, tzinfo=UTC),
            },
            {
                "ticker": "C:USDJPY",
                "bar_date_et": "2026-01-12",
                "close": 161.0,
                "bar_end_ts_utc": datetime(2026, 1, 12, 21, tzinfo=UTC),
            },
        ],
        fred_records=fred_rows,
        calendar_records=calendar_records,
    )
    fx = paper_core._canonical_fx_asof(
        context,
        us_date="2026-01-12",
        cutoff=datetime(2026, 1, 12, 21, 30, tzinfo=UTC),
    )

    assert fx["fx_source"] == "fred_h10_latest_released"
    assert fx["fx_usdjpy_level"] == 160.0
    assert fx["fx_staleness_days"] == 3


def test_canonical_fx_nulls_beyond_stale_fallback_window() -> None:
    context = paper_core._canonical_fx_context(
        massive_daily_records=[],
        fred_records=[
            {
                "series_id": "DEXJPUS",
                "observation_date": "2026-01-09",
                "vendor_available_ts_utc": datetime(2026, 1, 12, 21, 15, tzinfo=UTC),
                "value": 160.0,
            }
        ],
        calendar_records=[],
    )

    fx = paper_core._canonical_fx_asof(
        context,
        us_date="2026-01-22",
        cutoff=datetime(2026, 1, 22, 21, 30, tzinfo=UTC),
    )

    assert fx["fx_source"] == "null_unavailable"
    assert fx["fx_fallback_reason"] == "fred_fx_stale_beyond_fill_window"


def test_fred_h10_release_age_uses_us_release_calendar_not_utc_date() -> None:
    context = paper_core._canonical_fx_context(
        massive_daily_records=[],
        fred_records=[
            {
                "series_id": "DEXJPUS",
                "observation_date": "2026-01-09",
                "vendor_available_ts_utc": datetime(2026, 1, 12, 21, 15, tzinfo=UTC),
                "value": 160.0,
            }
        ],
        calendar_records=[],
    )

    fx = paper_core._canonical_fx_asof(
        context,
        us_date="2026-01-12",
        cutoff=datetime(2026, 1, 13, 1, 0, tzinfo=UTC),
    )

    assert fx["fx_source"] == "fred_h10_latest_released"
    assert fx["fx_release_age_days"] == 0


def test_calendar_map_statuses_cover_desync_and_holiday_trading() -> None:
    records = paper_module.build_calendar_map_records(
        target_rows=[
            {
                "trading_date": "2026-01-12",
                "target_open_ts_utc": datetime(2026, 1, 11, 23, 45, tzinfo=UTC),
                "missing_reason": "holiday_trading_no_day_open",
            },
            {
                "trading_date": "2026-01-13",
                "target_open_ts_utc": datetime(2026, 1, 12, 23, 45, tzinfo=UTC),
                "missing_reason": None,
            },
        ],
        calendar_records=[
            {
                "calendar_date": "2026-01-09",
                "is_us_trading_day": True,
                "is_jpx_trading_day": False,
                "us_close_ts_utc": datetime(2026, 1, 9, 21, tzinfo=UTC),
                "ose_night_close_ts_utc": datetime(2026, 1, 9, 21, tzinfo=UTC),
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-12",
                "us_calendar_date": "2026-01-09",
                "alignment_pass": True,
                "model_cutoff_ts_utc": datetime(2026, 1, 9, 21, 5, tzinfo=UTC),
            },
            {
                "trading_date": "2026-01-13",
                "us_calendar_date": "2026-01-09",
                "alignment_pass": False,
                "alignment_reason": "outside_dst_tolerance",
                "model_cutoff_ts_utc": datetime(2026, 1, 9, 21, 5, tzinfo=UTC),
            },
        ],
    )

    assert records[0]["mapping_status"] == "ose_holiday_trading"
    assert records[1]["mapping_status"] == "us_jp_desync"


def test_calendar_map_uses_target_us_date_for_holiday_status() -> None:
    records = paper_module.build_calendar_map_records(
        target_rows=[
            {
                "trading_date": "2026-01-20",
                "target_open_ts_utc": datetime(2026, 1, 19, 23, 45, tzinfo=UTC),
                "missing_reason": None,
            },
            {
                "trading_date": "2026-01-13",
                "target_open_ts_utc": datetime(2026, 1, 12, 23, 45, tzinfo=UTC),
                "missing_reason": None,
            },
            {
                "trading_date": "2026-01-26",
                "target_open_ts_utc": datetime(2026, 1, 25, 23, 45, tzinfo=UTC),
                "missing_reason": None,
            },
        ],
        calendar_records=[
            {
                "calendar_date": "2026-01-16",
                "is_us_trading_day": True,
                "is_jpx_trading_day": True,
                "us_close_ts_utc": datetime(2026, 1, 16, 21, tzinfo=UTC),
            },
            {
                "calendar_date": "2026-01-19",
                "is_us_trading_day": False,
                "is_jpx_trading_day": True,
            },
            {
                "calendar_date": "2026-01-20",
                "is_us_trading_day": True,
                "is_jpx_trading_day": True,
            },
            {
                "calendar_date": "2026-01-23",
                "is_us_trading_day": True,
                "is_jpx_trading_day": True,
                "us_close_ts_utc": datetime(2026, 1, 23, 21, tzinfo=UTC),
            },
            {
                "calendar_date": "2026-01-25",
                "weekday": 6,
                "is_us_trading_day": False,
                "is_jpx_trading_day": False,
            },
            {
                "calendar_date": "2026-01-26",
                "is_us_trading_day": True,
                "is_jpx_trading_day": True,
            },
            {
                "calendar_date": "2026-01-12",
                "is_us_trading_day": True,
                "is_jpx_trading_day": False,
                "us_close_ts_utc": datetime(2026, 1, 12, 21, tzinfo=UTC),
            },
            {
                "calendar_date": "2026-01-13",
                "is_us_trading_day": True,
                "is_jpx_trading_day": True,
            },
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-20",
                "us_calendar_date": "2026-01-16",
                "target_us_calendar_date": "2026-01-19",
                "alignment_pass": True,
                "model_cutoff_ts_utc": datetime(2026, 1, 16, 21, 5, tzinfo=UTC),
            },
            {
                "trading_date": "2026-01-13",
                "us_calendar_date": "2026-01-12",
                "target_us_calendar_date": "2026-01-12",
                "alignment_pass": True,
                "model_cutoff_ts_utc": datetime(2026, 1, 12, 21, 5, tzinfo=UTC),
            },
            {
                "trading_date": "2026-01-26",
                "us_calendar_date": "2026-01-23",
                "target_us_calendar_date": "2026-01-25",
                "alignment_pass": True,
                "model_cutoff_ts_utc": datetime(2026, 1, 23, 21, 5, tzinfo=UTC),
            },
        ],
    )

    assert records[0]["mapping_status"] == "us_holiday"
    assert records[0]["mapping_reason"] == "us_closed_jpx_open"
    assert records[1]["mapping_status"] == "normal_trading"
    assert records[2]["mapping_status"] == "normal_trading"


def test_jquants_silver_flags_and_cache_writer(tmp_path: Path) -> None:
    row = {
        "trading_date": "2026-01-05",
        "product_category": "NK225F",
        "contract_code": "c1",
        "contract_month": "2026-03",
        "central_contract_month_flag": True,
        "last_trading_day": "2026-03-12",
        "special_quotation_day": "2026-03-13",
        "day_session_open": None,
        "day_session_high": 101.0,
        "day_session_low": 99.0,
        "day_session_close": 100.0,
        "night_session_open": 99.0,
        "night_session_high": 101.0,
        "night_session_low": 98.0,
        "night_session_close": 100.0,
        "settlement_price": 100.0,
        "volume": 1.0,
        "open_interest": 2.0,
        "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
        "night_close_ts_utc": datetime(2026, 1, 4, 21, tzinfo=UTC),
        "vendor_available_ts_utc": datetime(2026, 1, 5, 18, tzinfo=UTC),
        "research_download_ts_utc": datetime(2026, 1, 5, 19, tzinfo=UTC),
    }
    flagged = paper_module.add_jquants_silver_flags([row])

    assert flagged[0]["invalid_day_session_open"] is True
    assert flagged[0]["invalid_day_session_high"] is False
    assert flagged[0]["day_session_ohlc_violation"] is False
    assert flagged[0]["invalid_settlement_price"] is False
    bad_hilo = paper_module.add_jquants_silver_flags(
        [{**row, "day_session_open": 100.0, "day_session_high": 98.0, "day_session_low": 101.0}]
    )
    assert bad_hilo[0]["day_session_ohlc_violation"] is True

    settings = Settings(data_dir=tmp_path / "data")
    paper_core._write_jquants_silver_cache(settings=settings, rows=flagged)
    assert (
        tmp_path
        / "data/silver/jquants_nk225f_daily/schema_version=2/year=2026/month=01/data.parquet"
    ).exists()


def test_derived_spy_records_flow_into_feature_map_and_alignment() -> None:
    available = datetime(2026, 1, 2, 21, 5, tzinfo=UTC)
    features = paper_core._minute_feature_map(
        [
            {
                "bar_date_et": "2026-01-02",
                "feature_available_ts_utc": available,
                "spy_late_30m_return": 0.01,
                "spy_late_60m_return": 0.02,
                "spy_late_session_range": 0.03,
                "spy_late_volume_surge": 1.2,
                "spy_final_window_momentum": -0.01,
            }
        ]
    )

    assert features["2026-01-02"]["spy_late_30m_return"] == 0.01
    assert features["2026-01-02"]["spy_late_30m_return__available_ts_utc"] == available


def test_derived_spy_volume_surge_recomputes_across_cache_partitions() -> None:
    features = paper_core._minute_feature_map(
        [
            {
                "bar_date_et": "2026-01-30",
                "feature_available_ts_utc": datetime(2026, 1, 30, 21, 15, tzinfo=UTC),
                "spy_late_30m_return": 0.01,
                "spy_late_60m_return": 0.02,
                "spy_late_session_range": 0.03,
                "spy_late_volume_surge": None,
                "spy_final_window_momentum": -0.01,
                "late_60m_volume_for_surge": 100.0,
                "regular_session_volume_for_surge": 1000.0,
            },
            {
                "bar_date_et": "2026-02-02",
                "feature_available_ts_utc": datetime(2026, 2, 2, 21, 15, tzinfo=UTC),
                "spy_late_30m_return": 0.02,
                "spy_late_60m_return": 0.03,
                "spy_late_session_range": 0.04,
                "spy_late_volume_surge": None,
                "spy_final_window_momentum": -0.02,
                "late_60m_volume_for_surge": 150.0,
                "regular_session_volume_for_surge": 1000.0,
            },
        ]
    )

    assert features["2026-01-30"]["spy_late_volume_surge"] is None
    assert features["2026-02-02"]["spy_late_volume_surge"] == pytest.approx(1.5)


def test_generic_minute_features_are_prefixed_and_volume_normalized_by_ticker() -> None:
    rows = [
        {
            "ticker": ticker,
            "safe_ticker": ticker.lower(),
            "bar_date_et": day,
            "feature_available_ts_utc": datetime(2026, 1, 2, 21, 15, tzinfo=UTC),
            "late_30m_return": 0.01,
            "late_60m_return": 0.02,
            "late_60m_realized_var": 0.0001,
            "late_60m_up_semivar": 0.00007,
            "late_60m_down_semivar": 0.00003,
            "late_60m_skew": None,
            "late_60m_excess_kurtosis": None,
            "late_session_range": 0.03,
            "late_volume_surge": None,
            "late_volume_zscore_20": None,
            "late_volume_percentile_20": None,
            "final_window_momentum": -0.01,
            "late_60m_volume_for_surge": volume,
        }
        for ticker, values in {"QQQ": (100.0, 200.0), "EWJ": (1000.0, 500.0)}.items()
        for day, volume in zip(("2026-01-02", "2026-01-05"), values, strict=True)
    ]

    features = paper_core._minute_feature_map(rows)

    assert features["2026-01-05"]["qqq_late_volume_surge"] == pytest.approx(2.0)
    assert features["2026-01-05"]["ewj_late_volume_surge"] == pytest.approx(0.5)
    assert features["2026-01-05"]["qqq_late_60m_realized_var"] == pytest.approx(0.0001)
    assert features["2026-01-05"]["ewj_late_30m_return"] == pytest.approx(0.01)
    assert features["2026-01-05"]["ewj_late_30m_return__available_ts_utc"] == datetime(
        2026, 1, 2, 21, 15, tzinfo=UTC
    )


def test_vendor_payload_helpers_and_marker(tmp_path: Path) -> None:
    assert paper_core._payload_results({"results": "bad"}) == []
    assert paper_core._payload_results({"results": [{"x": 1}, 2]}) == [{"x": 1}]

    marker = tmp_path / "data.unavailable.json"
    paper_core._write_unavailable_marker(
        marker,
        source="massive",
        error_class=VendorErrorClass.UNAVAILABLE_ENTITLEMENT,
        http_status=403,
        requested_range=["2026-01-01", "2026-01-31"],
    )
    assert json.loads(marker.read_text(encoding="utf-8"))["error_class"] == (
        "unavailable_entitlement"
    )
    assert paper_core._unavailable_marker_covers(marker, "2026-01-05", "2026-01-10")
    assert not paper_core._unavailable_marker_covers(marker, "2026-01-01", "2026-02-01")
    transient = tmp_path / "transient.unavailable.json"
    paper_core._write_unavailable_marker(
        transient,
        source="massive",
        error_class=VendorErrorClass.RATE_LIMITED,
        http_status=429,
        requested_range=["2026-01-01", "2026-01-31"],
    )
    assert not transient.exists()
    old_transient = tmp_path / "old.unavailable.json"
    old_transient.write_text('{"error_class": "rate_limited"}', encoding="utf-8")
    removed = paper_module.cleanup_transient_unavailable_markers(tmp_path)
    assert removed == [old_transient]
    assert not old_transient.exists()


def test_cache_coverage_guards_prevent_partial_month_reuse(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    paper_core.atomic_write_parquet(
        parquet_path,
        [{"requested_date": "2026-01-05", "value": 1.0}],
        metadata={
            "requested_dates": ["2026-01-05", "2026-01-06"],
            "completed_dates": ["2026-01-05"],
            "requested_range": ["2026-01-05", "2026-01-09"],
        },
    )

    assert paper_core._cache_covers_dates(parquet_path, ["2026-01-05"])
    assert not paper_core._cache_covers_dates(
        parquet_path,
        ["2026-01-05", "2026-01-06"],
    )
    legacy_massive_options_path = tmp_path / "legacy_massive_options.parquet"
    paper_core.atomic_write_parquet(
        legacy_massive_options_path,
        [{"bar_date_et": "2026-01-05", "value": 1.0}],
        metadata={
            "dataset": "us_options_opra/day_aggs_v1",
            "requested_dates": ["2026-01-05"],
        },
    )
    assert not paper_core._cache_covers_dates(
        legacy_massive_options_path,
        ["2026-01-05"],
    )
    assert paper_core._cache_covers_range(parquet_path, "2026-01-06", "2026-01-08")
    assert not paper_core._cache_covers_range(parquet_path, "2026-01-01", "2026-01-08")
    assert not paper_core._metadata_covers_range({}, "2026-01-01", "2026-01-08")
    rows = [
        {"requested_date": "2026-01-01", "value": 1},
        {"requested_date": "2026-01-05", "value": 5},
        {"bar_date_et": "2026-01-06", "value": 6},
        {"observation_date": "2026-02-01", "value": 20},
    ]
    filtered = paper_core._filter_records_by_range(
        rows,
        start="2026-01-05",
        end="2026-01-06",
        date_fields=("requested_date", "bar_date_et", "observation_date"),
    )
    assert [row["value"] for row in filtered] == [5, 6]
    assert paper_core._filter_records_by_dates(
        rows,
        allowed_dates=["2026-01-06"],
        date_fields=("requested_date", "bar_date_et", "observation_date"),
    ) == [{"bar_date_et": "2026-01-06", "value": 6}]


def test_low_level_feature_and_bronze_helpers_cover_edge_cases() -> None:
    assert paper_core._feature_description("other") == "run predictor candidate"
    assert "Nikkei 225 futures history" in paper_core._feature_description("n225_day_return_lag_1")
    assert "USDJPY FX control" in paper_core._feature_description("fx_usdjpy_level")
    assert "realized variance" in paper_core._feature_description("qqq_late_60m_realized_var")
    assert "realized semivariance" in paper_core._feature_description("qqq_late_60m_up_semivar")
    assert "small-sample realized moment" in paper_core._feature_description("qqq_late_60m_skew")
    assert "late-session volume" in paper_core._feature_description("spy_late_volume_surge")
    assert "normalized within ticker" in paper_core._feature_description(
        "qqq_late_volume_zscore_20"
    )
    assert "staleness" in paper_core._feature_description("fred_rates_staleness_days")
    assert "close-to-close" in paper_core._feature_description("spy_return")
    assert "high-low" in paper_core._feature_description("spy_range")
    assert "first difference" in paper_core._feature_description("fred_rate_diff")
    assert "daily source level" in paper_core._feature_description("fred_rate_level")
    assert "U.S.-listed instrument" in paper_core._feature_description("spy_late_30m_return")
    assert "U.S.-listed instrument" in paper_core._feature_description("qqq_final_window_momentum")
    assert _optional_text(None) is None
    assert _optional_text(" ") is None
    assert _description_optional_float(True) is None
    assert _description_optional_float("bad") is None
    with pytest.raises(paper_module.PipelineRunError):
        _description_required_float("bad")
    assert _minute_realized_var([]) is None
    assert _minute_semivar([], positive=True) is None
    assert _minute_semivar([-0.1, -0.2], positive=True) == 0.0
    assert _minute_sample_skew([0.1]) is None
    assert _minute_sample_skew([0.0] * 30) is None
    assert _minute_sample_excess_kurtosis([0.1]) is None
    assert _minute_sample_excess_kurtosis([0.0] * 30) is None
    assert _n225_log_return(0.0, 1.0) is None
    assert _n225_semivar_if_enough([0.1, 0.2], min_periods=2, positive=False) == 0.0
    assert _n225_sample_skew([1.0, 1.0], min_periods=2) is None
    assert _n225_sample_excess_kurtosis([1.0, 1.0], min_periods=2) is None
    assert not _is_finite_or_none(float("inf"))
    assert _parse_date(date(2026, 1, 1)) == date(2026, 1, 1)
    assert _contract_month_number("") is None
    assert paper_core._feature_source_family("unknown") == "unknown"
    assert "EWH" in paper_module.FETCH_MASSIVE_TICKERS_FOR_PIPELINE
    assert "EWH" not in paper_module.CORE_MASSIVE_TICKERS_FOR_PIPELINE
    assert "EEM" in paper_module.ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE
    assert "FXI" in paper_module.ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE
    assert "EEM" not in paper_module.CORE_MASSIVE_TICKERS_FOR_PIPELINE
    assert "FXI" not in paper_module.CORE_MASSIVE_TICKERS_FOR_PIPELINE
    assert "TM" in paper_module.FETCH_MASSIVE_TICKERS_FOR_PIPELINE
    assert "SONY" in paper_module.FETCH_MASSIVE_TICKERS_FOR_PIPELINE
    assert "C:USDJPY" not in paper_module.FETCH_MASSIVE_TICKERS_FOR_PIPELINE
    assert "C:USDJPY" not in paper_module.CORE_MASSIVE_TICKERS_FOR_PIPELINE
    assert "DEXJPUS" in paper_module.FETCH_FRED_SERIES_FOR_PIPELINE
    assert paper_core._feature_source_family("ewj_return") == "japan_proxy"
    assert paper_core._feature_source_family("ewh_return") == "asia_proxy"
    assert paper_core._feature_source_family("fx_usdjpy_level") == "fx_core"
    assert paper_core._feature_source_family("fx_release_age_days") == "fx_core"
    assert paper_core._feature_source_family("fred_bamlh0a0hym2_level") == ("fred_credit_enriched")
    assert paper_core._feature_source_family("cboe_vix_close") == "cboe_volatility"
    assert paper_core._feature_source_family("uup_return") == "massive_optional"
    assert paper_core._feature_source_family("c_usdjpy_return") == "massive_daily"
    assert paper_core._feature_source_family("n225_session_skew_120") == "japan_history"
    assert paper_core._feature_source_family("event_fomc_same_us_session") == "event_calendar"
    assert paper_core._feature_source_family("xmarket_vix_shock_20d") == "cross_market_derived"
    assert paper_core._feature_source_family("qqq_late_60m_realized_var") == "massive_minute"
    assert paper_core._feature_source_family("option_us_core_spy_atm_iv_short") == (
        "us_core_options"
    )
    assert paper_core._feature_source_family("option_japan_etf_ewj_atm_iv_short") == (
        "japan_proxy_options"
    )
    assert paper_core._feature_source_family("option_japan_adr_median_atm_iv_short") == (
        "japan_proxy_options"
    )
    assert paper_core._feature_source_family("option_us_sector_median_atm_iv_short") == (
        "us_core_options"
    )
    assert paper_core._feature_source_family("option_asia_proxy_median_atm_iv_short") == (
        "asia_proxy_options"
    )
    assert paper_core._feature_source_family("japan_adr_median_return") == "japan_proxy"
    assert paper_core._feature_source_block("fred_bamlh0a0hym2_level") == ("fred_credit_enriched")
    assert paper_core._feature_source_block("cboe_vix_close") == "fred_core"
    assert paper_core._feature_source_block("uup_return") == "massive_optional"
    assert paper_core._feature_source_block("fx_observation_age_days") == "fx_core"
    assert paper_core._feature_source_block("qqq_return") == "us_core"
    assert paper_core._feature_source_block("qqq_late_60m_realized_var") == "us_late_session"
    assert paper_core._feature_source_block("dxj_late_30m_return") == "japan_proxy"
    assert paper_core._feature_source_block("ewy_late_30m_return") == "asia_proxy"
    assert paper_core._feature_source_block("eem_return") == "asia_proxy"
    assert paper_core._feature_source_block("fxi_return") == "asia_proxy"
    assert paper_core._feature_source_block("option_us_core_spy_atm_iv_short") == "us_core"
    assert paper_core._feature_source_block("option_japan_etf_ewj_atm_iv_short") == "japan_proxy"
    assert paper_core._feature_source_block("option_japan_adr_median_atm_iv_short") == (
        "japan_proxy"
    )
    assert paper_core._feature_source_block("option_us_sector_median_atm_iv_short") == "us_core"
    assert paper_core._feature_source_block("option_asia_proxy_median_atm_iv_short") == (
        "asia_proxy"
    )
    assert paper_core._feature_source_block("n225_session_skew_120") == "japan_only"
    assert paper_core._feature_source_block("event_fomc_same_us_session") == "calendar_controls"
    assert paper_core._feature_source_block("xmarket_us_core_return_mean_1d") == "us_core"
    assert paper_core._feature_source_block("xmarket_vix_shock_20d") == "fred_core"
    assert paper_core._feature_source_block("xmarket_japan_proxy_dxj_spy_spread_1d") == (
        "japan_proxy"
    )
    assert paper_core._feature_source_block("xmarket_asia_proxy_return_dispersion_1d") == (
        "asia_proxy"
    )
    assert paper_core._panel_join_miss_reason({}, "") == "calendar_desync"
    assert (
        paper_core._panel_join_miss_reason(
            {"alignment_status": "missing_us_close"},
            "2026-01-02",
        )
        == "us_market_closed"
    )
    assert paper_core._panel_join_miss_reason({"alignment_pass": False}, "2026-01-02") == (
        "us_early_close_beyond_vendor_lag"
    )
    assert paper_core._rows_return([]) is None
    assert paper_core._rows_return([{"close": 0.0}, {"close": 1.0}]) is None

    row = paper_core._jquants_bronze_row(
        {
            "Date": "",
            "ProdCat": "NK225F",
            "EmMrgnTrgDiv": "002",
            "AO": "bad",
            "Settle": "100",
        },
        requested_date="2026-01-05",
        source_endpoint="/endpoint",
        downloaded_at_utc=datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert row["Date"] == "2026-01-05"
    assert row["EmMrgnTrgDiv"] == "002"
    assert row["AO"] is None
    assert row["Settle"] == 100.0


def test_quantile_loss_and_fz_loss_are_finite_for_valid_forecasts() -> None:
    assert quantile_loss(2.0, 1.5, 0.95) > 0
    assert math.isfinite(paper_module.fz_loss(2.0, 1.5, 2.5, 0.95))
    assert math.isnan(paper_module.fz_loss(2.0, 1.5, 1.0, 0.95))
    kupiec = kupiec_pof_test(
        breaches=np.array([False, False, True, False, False, True]),
        expected_probability=0.25,
    )
    assert kupiec["status"] == "ok"
    assert cast(float, kupiec["pvalue"]) <= 1.0


def _synthetic_forecasts(
    *,
    model_name: str,
    information_set: str,
    dates: list[str],
    var_shift: float = 0.0,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, forecast_date in enumerate(dates):
        loss = 0.01 + (index % 5) * 0.002
        var_forecast = 0.018 + var_shift
        es_forecast = max(var_forecast + 0.01, 0.03)
        rows.append(
            {
                "forecast_date": forecast_date,
                "target_family": "full_gap_settle_to_open",
                "model_name": model_name,
                "information_set": information_set,
                "tail_level": 0.95,
                "var_forecast": var_forecast,
                "es_forecast": es_forecast,
                "realized_loss": loss,
                "is_valid_forecast": True,
                "fit_status": "ok",
                "vix_level": 15.0 + index,
            }
        )
    return rows


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


def test_common_sample_eviction_and_primary_artifacts() -> None:
    dates = [f"2026-01-{day:02d}" for day in range(1, 21)]
    forecasts = [
        *_synthetic_forecasts(
            model_name="historical_quantile",
            information_set="target_history_only",
            dates=dates,
            var_shift=0.0,
        ),
        *_synthetic_forecasts(
            model_name="rolling_quantile",
            information_set="target_history_only",
            dates=dates,
            var_shift=0.002,
        ),
        *_synthetic_forecasts(
            model_name="fragile_model",
            information_set="target_history_only",
            dates=dates[:18],
            var_shift=-0.004,
        ),
    ]

    artifacts = paper_module.build_common_sample_artifacts(
        forecasts,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    evictions = cast(list[dict[str, object]], artifacts["model_eviction"])
    fragile = next(row for row in evictions if row["model_name"] == "fragile_model")
    assert fragile["retained_for_primary"] is False
    assert fragile["eviction_reason"] == "coverage_below_model_eviction_threshold"
    primary_models = {
        row["model_name"] for row in cast(list[dict[str, object]], artifacts["primary_metrics"])
    }
    per_model_models = {
        row["model_name"] for row in cast(list[dict[str, object]], artifacts["per_model_metrics"])
    }
    assert "fragile_model" not in primary_models
    assert "fragile_model" in per_model_models
    assert cast(list[dict[str, object]], artifacts["loss_matrix"])
    assert cast(list[dict[str, object]], artifacts["dm_inference"])[0]["alternative"] == (
        "candidate_mean_diff_less_than_zero"
    )
    murphy = cast(list[dict[str, object]], artifacts["murphy"])
    first_model_grid = [row for row in murphy if row["model_name"] == "historical_quantile"]
    assert len(first_model_grid) == 200
    assert cast(float, first_model_grid[0]["threshold_value"]) <= cast(
        float, first_model_grid[-1]["threshold_value"]
    )
    stress = cast(list[dict[str, object]], artifacts["stress_windows"])
    assert {row["window_name"] for row in stress} == {"loss_top_decile", "vix_top_decile"}


def test_common_sample_compares_benchmark_models_across_refit_metadata() -> None:
    dates = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(130)
    ]
    forecasts = [
        *_synthetic_forecasts(
            model_name="historical_quantile",
            information_set="target_history_only",
            dates=dates,
            var_shift=0.0,
        ),
        *[
            {
                **row,
                "model_name": "caviar_sav",
                "refit_frequency": paper_module.BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                "var_forecast": cast(float, row["var_forecast"]) + 0.01,
                "es_forecast": cast(float, row["es_forecast"]) + 0.01,
            }
            for row in _synthetic_forecasts(
                model_name="placeholder",
                information_set="target_history_only",
                dates=dates,
                var_shift=0.002,
            )
        ],
    ]

    artifacts = paper_module.build_common_sample_artifacts(
        forecasts,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    assert artifacts["common_sample_status"] == "ok"
    primary_models = {
        row["model_name"] for row in cast(list[dict[str, object]], artifacts["primary_metrics"])
    }
    assert {"historical_quantile", "caviar_sav"}.issubset(primary_models)
    dm = cast(list[dict[str, object]], artifacts["dm_inference"])
    assert any(row["candidate_model_name"] == "caviar_sav" for row in dm)


def test_primary_dm_gate_on_common_rows_and_tail_events() -> None:
    loss_matrix: list[dict[str, object]] = []
    for index in range(130):
        forecast_date = (datetime(2026, 2, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for model_name, fz in (("historical_quantile", 0.20), ("candidate", 0.18)):
            loss_matrix.append(
                {
                    "forecast_date": forecast_date.isoformat(),
                    "target_family": "full_gap_settle_to_open",
                    "model_name": model_name,
                    "information_set": "target_history_only",
                    "tail_level": 0.95,
                    "refit_frequency": "monthly",
                    "realized_loss": 1.0 if index % 25 == 0 else 0.1,
                    "var_forecast": 0.5,
                    "fz_loss": fz,
                }
            )

    dm = paper_module.build_block_bootstrap_dm_records(
        loss_matrix,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
        reps=19,
    )

    assert dm[0]["inference_status"] == "ok_block_bootstrap_dm"
    assert dm[0]["target_family"] == "full_gap_settle_to_open"
    assert dm[0]["refit_frequency"] == "monthly"
    assert dm[0]["joint_exception_count"] >= 5


def test_loss_matrix_grouping_keeps_target_and_refit_frequency_separate() -> None:
    loss_matrix: list[dict[str, object]] = []
    for target_family, refit_frequency in (
        ("full_gap_settle_to_open", "monthly"),
        ("residual_usclosemark_to_open", "daily"),
    ):
        for tail_side in ("left_tail", "right_tail"):
            for index in range(130):
                forecast_date = (datetime(2026, 6, 1, tzinfo=UTC) + timedelta(days=index)).date()
                for model_name, fz in (("historical_quantile", 0.20), ("candidate", 0.19)):
                    loss_matrix.append(
                        {
                            "forecast_date": forecast_date.isoformat(),
                            "target_family": target_family,
                            "tail_side": tail_side,
                            "model_name": model_name,
                            "information_set": "target_history_only",
                            "tail_level": 0.95,
                            "refit_frequency": refit_frequency,
                            "realized_loss": 1.0 if index % 20 == 0 else 0.1,
                            "var_forecast": 0.5,
                            "fz_loss": fz,
                        }
                    )

    dm = paper_module.build_block_bootstrap_dm_records(
        loss_matrix,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
        reps=19,
    )

    assert {
        (
            row["target_family"],
            row["tail_side"],
            row["refit_frequency"],
            row["candidate_model_name"],
        )
        for row in dm
    } == {
        ("full_gap_settle_to_open", "left_tail", "monthly", "candidate"),
        ("full_gap_settle_to_open", "right_tail", "monthly", "candidate"),
        ("residual_usclosemark_to_open", "left_tail", "daily", "candidate"),
        ("residual_usclosemark_to_open", "right_tail", "daily", "candidate"),
    }


def test_incremental_information_artifacts_use_block_bootstrap_dm_labels() -> None:
    dates = [
        (datetime(2026, 3, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
        for index in range(130)
    ]
    forecasts: list[dict[str, object]] = []
    for index, forecast_date in enumerate(dates):
        regime = "EDT" if index % 2 else "EST"
        forecasts.extend(
            [
                {
                    "forecast_date": forecast_date,
                    "target_family": "full_gap_settle_to_open",
                    "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                    "information_set": "japan_only",
                    "tail_level": 0.95,
                    "realized_loss": 1.0,
                    "var_forecast": 1.2,
                    "es_forecast": 1.4,
                    "fit_status": "ok",
                    "is_valid_forecast": True,
                    "dst_regime": regime,
                },
                {
                    "forecast_date": forecast_date,
                    "target_family": "full_gap_settle_to_open",
                    "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                    "information_set": "japan_only_plus_us_close_core",
                    "tail_level": 0.95,
                    "realized_loss": 1.0,
                    "var_forecast": 1.1,
                    "es_forecast": 1.3,
                    "fit_status": "ok",
                    "is_valid_forecast": True,
                    "dst_regime": regime,
                },
            ]
        )

    incremental = paper_module.build_incremental_information_records(
        forecasts,
        baseline_information_set="japan_only",
    )
    assert any(row["dm_method"] == "moving_block_bootstrap_unconditional_dm" for row in incremental)
    assert any(row["inference_status"] == "ok_block_bootstrap_dm" for row in incremental)


def test_common_sample_unstable_status_after_eviction_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = [f"2026-02-{day:02d}" for day in range(1, 11)]
    forecasts = [
        *_synthetic_forecasts(
            model_name="historical_quantile",
            information_set="target_history_only",
            dates=dates,
        ),
        *_synthetic_forecasts(
            model_name="candidate",
            information_set="target_history_only",
            dates=dates[:8],
        ),
    ]
    _patch_paper_module(monkeypatch, "MODEL_EVICTION_COVERAGE_THRESHOLD", 0.50)
    _patch_paper_module(monkeypatch, "COMMON_SAMPLE_MIN_ANCHOR_COVERAGE", 0.90)

    artifacts = paper_module.build_common_sample_artifacts(
        forecasts,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    assert artifacts["common_sample_status"] == "common_sample_unstable"
    assert all(
        row["common_sample_status"] == "common_sample_unstable"
        for row in cast(list[dict[str, object]], artifacts["model_eviction"])
    )


def test_common_sample_missing_anchor_and_empty_artifacts() -> None:
    forecasts = _synthetic_forecasts(
        model_name="candidate",
        information_set="target_history_only",
        dates=["2026-03-01", "2026-03-02"],
    )

    artifacts = paper_module.build_common_sample_artifacts(
        forecasts,
        suite="benchmark",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    assert artifacts["common_sample_status"] == "unavailable_missing_anchor"
    eviction = cast(list[dict[str, object]], artifacts["model_eviction"])[0]
    assert eviction["eviction_reason"] == "missing_anchor_sample"
    assert paper_module.build_murphy_records([], suite="benchmark") == []
    bad_matrix = paper_module.build_loss_matrix_records(
        [
            {
                **forecasts[0],
                "es_forecast": -1.0,
            }
        ],
        suite="benchmark",
    )
    assert bad_matrix == []


def test_coverage_tests_return_unavailable_for_degenerate_inputs() -> None:
    assert kupiec_pof_test(breaches=np.array([]), expected_probability=0.05)["status"] == (
        "unavailable_invalid_input"
    )
    assert (
        kupiec_pof_test(
            breaches=np.array([False, False]),
            expected_probability=0.05,
        )["status"]
        == "ok"
    )

    assert (
        paper_module.christoffersen_independence_test(breaches=np.array([True]))["status"]
        == "unavailable_insufficient_oos"
    )
    assert (
        paper_module.christoffersen_independence_test(
            breaches=np.array([False, False, False]),
        )["status"]
        == "ok"
    )
    ok = paper_module.christoffersen_independence_test(
        breaches=np.array([False, True, False, False, True, True, False]),
    )
    assert ok["status"] == "ok"


def test_force_clear_preserves_audits_for_leakage_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    for name in ("forecasts", "metrics", "latex", "audits"):
        directory = run_dir / name
        directory.mkdir(parents=True)
        (directory / "sentinel.txt").write_text("x", encoding="utf-8")

    metrics_information._clear_run_outputs_for_force(run_dir)

    assert not (run_dir / "forecasts").exists()
    assert not (run_dir / "metrics").exists()
    assert not (run_dir / "latex").exists()
    assert (run_dir / "audits" / "sentinel.txt").read_text(encoding="utf-8") == "x"


def test_force_config_compatibility_preserves_audits_and_updates_manifest(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "forecasts").mkdir(parents=True)
    (run_dir / "forecasts" / "sentinel.txt").write_text("x", encoding="utf-8")
    (run_dir / "audits").mkdir()
    (run_dir / "audits" / "leakage_summary.parquet").write_text("x", encoding="utf-8")
    (run_dir / "manifest.json").write_text('{"config_hash": "stale"}', encoding="utf-8")

    metrics_information._assert_run_config_compatible(run_dir, force=True)

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_hash"] == metrics_information.PIPELINE_CONFIG.config_hash()
    assert manifest["config_lock_status"] == "locked_after_forecasts_or_metrics"
    assert not (run_dir / "forecasts").exists()
    assert (run_dir / "audits" / "leakage_summary.parquet").exists()


def test_gold_artifact_path_uses_existing_manifest_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    gold = tmp_path / "gold.parquet"
    fallback = tmp_path / "fallback.parquet"
    gold.write_text("x", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"gold_artifacts": {"benchmark_metrics": str(gold)}}),
        encoding="utf-8",
    )

    assert metrics_information._gold_artifact_path(run_dir, "benchmark_metrics", fallback) == gold


def test_closed_form_benchmark_forecasts_and_unknown_model() -> None:
    train = np.arange(1.0, 80.0) / 100.0

    historical = paper_core._forecast_one(
        train=train,
        model_name="historical_quantile",
        tail_level=0.95,
    )
    rolling = paper_core._forecast_one(
        train=train,
        model_name="rolling_quantile",
        tail_level=0.95,
    )
    ewma = paper_core._forecast_one(
        train=train,
        model_name="ewma_vol_scaled",
        tail_level=0.95,
    )

    assert historical["es_companion_type"] == "raw_empirical_es"
    assert rolling["es_companion_type"] == "rolling_empirical_es"
    assert ewma["es_companion_type"] == "analytical_normal_es"
    assert isinstance(ewma["es_forecast"], float)
    assert isinstance(ewma["var_forecast"], float)
    assert ewma["es_forecast"] >= ewma["var_forecast"]
    with pytest.raises(paper_module.PipelineRunError, match="Unknown Benchmark model"):
        paper_core._forecast_one(train=train, model_name="unknown", tail_level=0.95)


def test_evaluate_benchmark_shard_records_unavailable_oos(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    pl.DataFrame(
        [
            {"forecast_date": "2026-01-01", "clean_sample": True, "realized_loss": 0.01},
            {"forecast_date": "2026-01-02", "clean_sample": True, "realized_loss": 0.02},
        ]
    ).write_parquet(panel_path)

    result = paper_core._evaluate_benchmark_shard(
        {
            "panel_path": str(panel_path),
            "run_dir": str(tmp_path),
            "tail_level": 0.95,
            "models": ("historical_quantile",),
        }
    )

    assert result["forecasts"] == []
    assert result["diagnostics"][0]["fit_status"] == "unavailable_insufficient_oos_start"
    assert result["diagnostics"][0]["model_name"] == "historical_quantile"
    assert result["diagnostics"][0]["shard_id"] == "hist_q__sto__L__hist__q0950"


def test_spy_minute_features_cover_late_window_and_volume_surge() -> None:
    rows: list[dict[str, object]] = []
    for day, base in (("2026-01-02", 100.0), ("2026-01-05", 110.0)):
        for minute in range(70):
            rows.append(
                {
                    "bar_date_et": day,
                    "bar_end_ts_utc": datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
                    + timedelta(minutes=minute),
                    "is_us_regular_session": True,
                    "close": base + minute / 100.0,
                    "high": base + minute / 100.0 + 0.1,
                    "low": base + minute / 100.0 - 0.1,
                    "volume": 1000.0 + minute,
                }
            )

    features = paper_core._minute_feature_map(rows)

    assert features["2026-01-02"]["spy_late_30m_return"] is not None
    assert features["2026-01-05"]["spy_late_60m_return"] is not None
    assert features["2026-01-05"]["spy_late_volume_surge"] is not None


def test_evaluate_benchmark_suite_and_latex_export_with_synthetic_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "runs" / "benchmark_synthetic"
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
        for day in range(80)
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
            "es_companion_type": "synthetic",
            "optimizer_status": "ok",
            "convergence_code": 0,
        }

    _patch_paper_module(monkeypatch, "_forecast_one", fake_forecast_one)

    result = evaluate_benchmark_suite(run_dir=run_dir, workers=1, tail_side="left_tail")
    latex = export_tables(run_dir=run_dir)

    assert result.status == "completed"
    assert result.forecast_rows > 0
    assert (run_dir / "forecasts" / "benchmark_forecasts.parquet").exists()
    assert (run_dir / "s" / "hist_q__sto__L__hist__q0950" / "f.pq").exists()
    assert (run_dir / "metrics" / "benchmark_metrics.parquet").exists()
    assert latex.tables >= 2
    assert not (latex.latex_dir / "benchmark_metrics_table.tex").exists()
    assert not (latex.latex_dir / "tailrisk_es_severity_table.tex").exists()
    assert not (latex.latex_dir / "tailrisk_claim_scope_table.tex").exists()
    latex_text = (latex.latex_dir / "appendix_benchmark_all_models_table.tex").read_text(
        encoding="utf-8"
    )
    assert "% config_hash:" in latex_text


def test_result_matrix_latex_export_has_restricted_notes(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "ml_tail_result_matrix_latex"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "ml_tail_result_matrix_latex",
                "git_commit": "abc123",
                "config_hash": paper_module.PIPELINE_CONFIG.config_hash(),
            }
        ),
        encoding="utf-8",
    )
    pl.DataFrame(
        [
            {
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": "var_quantile_loss",
                "claim_scope": "restricted_model_comparison_not_primary",
                "primary_claim_allowed": False,
                "target_family": "full_gap_settle_to_open",
                "information_set": "japan_only",
                "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "tail_level": 0.95,
                "refit_frequency": "monthly",
                "common_n": 130,
                "exception_count": 7,
                "metric_value": 0.0123,
                "metric_status": "ok",
            }
        ]
    ).write_parquet(metrics_dir / "ml_tail_result_matrix.parquet")

    latex = export_tables(run_dir=run_dir)
    latex_text = (latex.latex_dir / "ml_tail_result_matrix_table.tex").read_text(encoding="utf-8")
    summary_text = (latex.latex_dir / "ml_tail_result_matrix_summary_table.tex").read_text(
        encoding="utf-8"
    )

    assert latex.tables == 2
    assert "restricted result matrix" in latex_text
    assert "LGBM direct quantile" in latex_text
    assert "primary ML table" in latex_text
    assert "block-bootstrap DM" in latex_text
    assert "VaR-only and VaR-ES" in summary_text
    assert "Restricted samples are not primary evidence" in summary_text


def test_export_tables_clears_stale_tables_when_primary_gate_fails(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "stale_table_gate"
    metrics_dir = run_dir / "metrics"
    latex_dir = run_dir / "latex" / "tables"
    metrics_dir.mkdir(parents=True)
    latex_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "stale_table_gate"}),
        encoding="utf-8",
    )
    stale_table = latex_dir / "benchmark_metrics_table.tex"
    stale_table.write_text("old table", encoding="utf-8")
    pl.DataFrame(
        [
            {
                "model_name": "historical_quantile",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "tail_level": 0.95,
                "sample_policy": "primary_common_sample",
                "common_sample_status": "unavailable_missing_anchor",
                "rows": 500,
                "var_breach_rate": 0.05,
                "mean_quantile_loss": 0.01,
                "mean_fz_loss": -1.0,
            }
        ]
    ).write_parquet(metrics_dir / "benchmark_metrics.parquet")

    result = export_tables(run_dir=run_dir)
    manifest = json.loads((run_dir / "latex" / "table_manifest.json").read_text())

    assert result.tables == 0
    assert manifest["table_count"] == 0
    assert not stale_table.exists()


def test_market_timing_design_labels_jst_cutoff_and_schedule_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "reports" / "runs" / "timing_design"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_save_figure(fig: object, **kwargs: object) -> list[dict[str, object]]:
        texts: list[str] = []
        for ax in fig.axes:
            texts.append(ax.get_title())
            texts.extend(text.get_text() for text in ax.texts)
        captured["text"] = "\n".join(texts)
        captured["kwargs"] = kwargs
        reporting_figures.plt.close(fig)
        return [
            {
                "name": kwargs["name"],
                "path": "latex/figures/market_timing_design.png",
                "format": "png",
                "source_artifacts": kwargs["source_artifacts"],
                "tail_side": kwargs["tail_side"],
                "caption": kwargs["caption"],
                "claim_scope": kwargs["claim_scope"],
            }
        ]

    monkeypatch.setattr(reporting_figures, "_save_figure", fake_save_figure)

    entries = reporting_figures._market_timing_design_figures(
        run_dir=run_dir, figure_dir=run_dir / "latex" / "figures"
    )

    text = str(captured["text"])
    kwargs = cast(dict[str, object], captured["kwargs"])
    assert entries
    assert kwargs["claim_scope"] == "design_forecast_origin_not_causal_price_discovery"
    assert "JST timing for the settlement-to-open forecast design" in text
    assert "if EDT" in text
    assert "if EST" in text
    assert "matched\nU.S. close\n+ data lag\ncutoff" in text
    caption = str(kwargs["caption"])
    assert "05:00 JST" in caption
    assert "06:00 JST" in caption
    assert "pre-2024-11-05 hours" in caption
    assert "day close 15:45 JST" in caption
    assert "night session 17:00-06:00 JST" in caption
    assert "OSE night close is timing context, not the forecast origin" in caption
    assert "not a structural market-transmission diagram" in caption


def test_export_tables_generates_paper_figures_and_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "figure_export"
    metrics_dir = run_dir / "metrics"
    forecasts_dir = run_dir / "forecasts"
    panel_dir = run_dir / "panel"
    metrics_dir.mkdir(parents=True)
    forecasts_dir.mkdir(parents=True)
    panel_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "figure_export",
                "git_commit": "abc123",
                "config_hash": paper_module.PIPELINE_CONFIG.config_hash(),
            }
        ),
        encoding="utf-8",
    )
    panel_rows = []
    for idx in range(120):
        gap = 0.004 * math.sin(idx / 6.0)
        if idx % 37 == 0:
            gap += 0.045
        if idx % 41 == 0:
            gap -= 0.038
        panel_rows.append(
            {
                "forecast_date": f"2025-01-{(idx % 28) + 1:02d}",
                "forecast_sample": True,
                "gap_t": gap,
            }
        )
    pl.DataFrame(panel_rows).write_parquet(panel_dir / "modeling_panel.parquet")
    pl.DataFrame(
        [
            {
                "feature": "spy_return",
                "clean_rows": 500,
                "non_missing_rows": 500,
                "missingness_rate": 0.0,
                "first_valid_date": "2023-01-01",
                "last_valid_date": "2026-01-08",
                "source_family": "massive_daily",
                "source_block": "us_core",
                "vintage_safe": True,
                "revision_risk_label": None,
            },
            {
                "feature": "ewj_return",
                "clean_rows": 500,
                "non_missing_rows": 480,
                "missingness_rate": 0.04,
                "first_valid_date": "2023-01-05",
                "last_valid_date": "2026-01-08",
                "source_family": "japan_proxy",
                "source_block": "japan_proxy",
                "vintage_safe": True,
                "revision_risk_label": None,
            },
        ]
    ).write_parquet(panel_dir / "feature_coverage.parquet")
    metric_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for model_name, breach in (
            ("historical_quantile", 0.05),
            ("gjr_garch_evt", 0.05),
            ("garch_t", 0.07),
        ):
            metric_rows.append(
                {
                    "model_name": model_name,
                    "target_family": "full_gap_settle_to_open",
                    "tail_side": tail_side,
                    "information_set": "target_history_only",
                    "tail_level": 0.95,
                    "refit_frequency": "daily",
                    "sample_policy": "primary_common_sample",
                    "common_sample_status": "ok",
                    "rows": 500,
                    "var_breach_rate": breach,
                    "expected_breach_rate": 0.05,
                    "exceedance_count": 1,
                    "mean_quantile_loss": 0.001,
                    "mean_fz_loss": -3.1,
                    "mean_exceedance_severity": 0.01,
                }
            )
    benchmark_metrics = pl.DataFrame(metric_rows)
    benchmark_metrics.write_parquet(metrics_dir / "benchmark_metrics.parquet")
    advanced = benchmark_metrics.with_columns(
        pl.lit("caviar_sav").alias("model_name"),
        pl.lit("monthly_parameter_refit_daily_filter").alias("refit_frequency"),
    )
    pl.concat([benchmark_metrics, advanced], how="diagonal_relaxed").write_parquet(
        metrics_dir / "benchmark_metrics_per_model.parquet"
    )
    ml_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for information_set, breach in (
            ("japan_only", 0.06),
            ("japan_only_plus_us_close_core", 0.08),
        ):
            base = {
                "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "target_family": "full_gap_settle_to_open",
                "tail_side": tail_side,
                "information_set": information_set,
                "tail_level": 0.95,
                "refit_frequency": "monthly",
                "sample_policy": "primary_common_sample",
                "common_sample_status": "ok",
                "rows": 500,
                "var_breach_rate": breach,
                "expected_breach_rate": 0.05,
                "exceedance_count": 2,
                "mean_quantile_loss": 0.001,
                "mean_fz_loss": -3.2,
                "mean_exceedance_severity": 0.009,
            }
            ml_rows.append(base)
            ml_rows.append({**base, "model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL})
        promoted_spec = next(
            item
            for item in reporting_latex.PROMOTED_TAIL_MODEL_SPECS
            if item["tail_side"] == tail_side
        )
        ml_rows.append(
            {
                **base,
                "model_name": promoted_spec["model_name"],
                "information_set": promoted_spec["information_set"],
                "var_breach_rate": 0.052,
                "exceedance_count": 26,
                "mean_quantile_loss": 0.0008,
                "mean_fz_loss": -3.4,
            }
        )
    ml_metrics = pl.DataFrame(ml_rows)
    ml_metrics.filter(
        pl.col("model_name") == paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL
    ).write_parquet(metrics_dir / "ml_tail_metrics.parquet")
    ml_metrics.write_parquet(metrics_dir / "ml_tail_metrics_per_model.parquet")
    murphy_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for threshold_index, threshold_value in enumerate((-0.01, 0.0, 0.01)):
            for model_name in ("historical_quantile", "garch_t"):
                murphy_rows.append(
                    {
                        "suite": "benchmark",
                        "target_family": "full_gap_settle_to_open",
                        "tail_side": tail_side,
                        "model_name": model_name,
                        "information_set": "target_history_only",
                        "tail_level": 0.95,
                        "refit_frequency": "daily",
                        "threshold_index": threshold_index,
                        "threshold_value": threshold_value,
                        "threshold_grid_policy": "synthetic_common_grid",
                        "rows": 20,
                        "mean_elementary_score": 0.02 + threshold_index * 0.001,
                    }
                )
    pl.DataFrame(murphy_rows).write_parquet(metrics_dir / "benchmark_murphy.parquet")
    ml_murphy_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for threshold_index, threshold_value in enumerate((-0.01, 0.0, 0.01)):
            for information_set in ("japan_only", "japan_only_plus_us_close_core"):
                ml_murphy_rows.append(
                    {
                        "suite": "ml_tail",
                        "target_family": "full_gap_settle_to_open",
                        "tail_side": tail_side,
                        "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                        "information_set": information_set,
                        "tail_level": 0.95,
                        "refit_frequency": "monthly",
                        "threshold_index": threshold_index,
                        "threshold_value": threshold_value,
                        "threshold_grid_policy": "synthetic_common_grid",
                        "rows": 20,
                        "mean_elementary_score": 0.015 + threshold_index * 0.001,
                    }
                )
    pl.DataFrame(ml_murphy_rows).write_parquet(metrics_dir / "ml_tail_murphy.parquet")
    dm_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        promoted_spec = next(
            item
            for item in reporting_latex.PROMOTED_TAIL_MODEL_SPECS
            if item["tail_side"] == tail_side
        )
        dm_rows.extend(
            [
                {
                    "comparison_family": "information_set_ladder",
                    "comparison_axis": "information_set_increment",
                    "sample_policy": "restricted_tail_model_common_sample",
                    "loss_family": "var_es_fz_loss",
                    "tail_side": tail_side,
                    "information_set": "japan_only_plus_us_close_core",
                    "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                    "baseline_entity": "japan_only",
                    "candidate_entity": "japan_only_plus_us_close_core",
                    "paired_rows": 100,
                    "common_n": 100,
                    "joint_exception_count": 8,
                    "mean_loss_diff_candidate_minus_baseline": -0.10,
                    "pvalue_one_sided": 0.04,
                    "inference_status": "ok_block_bootstrap_dm",
                },
                {
                    "comparison_family": "tail_model_family",
                    "comparison_axis": "model_family",
                    "sample_policy": "restricted_tail_model_common_sample",
                    "loss_family": "var_es_fz_loss",
                    "tail_side": tail_side,
                    "information_set": promoted_spec["information_set"],
                    "model_name": promoted_spec["model_name"],
                    "baseline_entity": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                    "candidate_entity": promoted_spec["model_name"],
                    "paired_rows": 100,
                    "common_n": 100,
                    "joint_exception_count": 8,
                    "mean_loss_diff_candidate_minus_baseline": -0.08,
                    "pvalue_one_sided": 0.06,
                    "inference_status": "ok_block_bootstrap_dm",
                },
            ]
        )
    pl.DataFrame(dm_rows).write_parquet(metrics_dir / "ml_tail_result_matrix_dm.parquet")
    forecast_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for day in range(8):
            forecast_rows.append(
                {
                    "forecast_date": f"2026-01-{day + 1:02d}",
                    "target_family": "full_gap_settle_to_open",
                    "tail_side": tail_side,
                    "model_name": "historical_quantile",
                    "information_set": "target_history_only",
                    "tail_level": 0.95,
                    "refit_frequency": "daily",
                    "var_forecast": 0.01 + day * 0.001,
                    "es_forecast": 0.015 + day * 0.001,
                    "realized_loss": 0.02 if day % 3 == 0 else 0.005,
                    "var_breach": day % 3 == 0,
                    "is_valid_forecast": True,
                    "fit_status": "ok",
                }
            )
            forecast_rows.append(
                {
                    **forecast_rows[-1],
                    "model_name": "gjr_garch_evt",
                    "var_forecast": 0.012 + day * 0.001,
                    "es_forecast": 0.017 + day * 0.001,
                    "var_breach": day % 4 == 0,
                }
            )
            forecast_rows.append(
                {
                    **forecast_rows[-1],
                    "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                    "information_set": "japan_only",
                    "refit_frequency": "monthly",
                    "var_forecast": 0.011 + day * 0.001,
                    "es_forecast": 0.016 + day * 0.001,
                }
            )
            forecast_rows.append(
                {
                    **forecast_rows[-1],
                    "information_set": "japan_only_plus_us_close_core",
                    "var_forecast": 0.0105 + day * 0.001,
                    "es_forecast": 0.0155 + day * 0.001,
                }
            )
            promoted_spec = next(
                item
                for item in reporting_latex.PROMOTED_TAIL_MODEL_SPECS
                if item["tail_side"] == tail_side
            )
            forecast_rows.append(
                {
                    **forecast_rows[-1],
                    "model_name": promoted_spec["model_name"],
                    "information_set": promoted_spec["information_set"],
                    "var_forecast": 0.0102 + day * 0.001,
                    "es_forecast": 0.0152 + day * 0.001,
                }
            )
            for model_offset, model_name in enumerate(
                reporting_figures.LGBM_24CHECK_CUMULATIVE_MODELS
            ):
                for information_offset, information_set in enumerate(
                    reporting_figures.INFORMATION_LADDER_ORDER
                ):
                    forecast_rows.append(
                        {
                            "forecast_date": f"2026-01-{day + 1:02d}",
                            "target_family": "full_gap_settle_to_open",
                            "tail_side": tail_side,
                            "model_name": model_name,
                            "information_set": information_set,
                            "tail_level": 0.95,
                            "refit_frequency": "monthly",
                            "var_forecast": (
                                0.0103
                                + day * 0.001
                                - information_offset * 0.0001
                                + model_offset * 0.00005
                            ),
                            "es_forecast": (
                                0.0153
                                + day * 0.001
                                - information_offset * 0.0001
                                + model_offset * 0.00005
                            ),
                            "realized_loss": 0.02 if day % 3 == 0 else 0.005,
                            "var_breach": day % 3 == 0,
                            "is_valid_forecast": True,
                            "fit_status": "ok",
                        }
                    )
    forecast_frame = pl.DataFrame(forecast_rows)
    forecast_frame.filter(
        pl.col("model_name").is_in(["historical_quantile", "gjr_garch_evt"])
    ).write_parquet(forecasts_dir / "benchmark_forecasts.parquet")
    forecast_frame.filter(
        ~pl.col("model_name").is_in(["historical_quantile", "gjr_garch_evt"])
    ).write_parquet(forecasts_dir / "ml_tail_forecasts.parquet")

    latex = export_tables(run_dir=run_dir)
    manifest = json.loads((run_dir / "latex" / "figure_manifest.json").read_text())
    table_manifest = json.loads((run_dir / "latex" / "table_manifest.json").read_text())
    entries = manifest["figures"]

    assert latex.tables >= 7
    assert table_manifest["table_count"] == latex.tables
    assert len(table_manifest["tables"]) == latex.tables
    assert any(table["name"] == "benchmark_metrics" for table in table_manifest["tables"])
    assert all(table["source_artifacts"] for table in table_manifest["tables"])
    assert all((run_dir / table["path"]).exists() for table in table_manifest["tables"])
    assert entries
    assert {entry["format"] for entry in entries} == {"png", "pdf"}
    assert {paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT}.issubset(
        {entry["tail_side"] for entry in entries}
    )
    assert any(entry["name"] == "market_timing_design" for entry in entries)
    assert any(
        table["name"] == "tailrisk_predictor_block_coverage" for table in table_manifest["tables"]
    )
    assert any(table["name"] == "tailrisk_model_inventory" for table in table_manifest["tables"])
    assert any(entry["name"] == "cumulative_lgbm_a_anchor_fz_gain" for entry in entries)
    assert any(entry["name"] == "full_sample_var_overlay_left_tail" for entry in entries)
    assert any(str(entry["name"]).startswith("var_es_stress_overlay_") for entry in entries)
    assert any(entry["name"] == "dm_heatmap_left_tail" for entry in entries)
    dm_entries = [
        entry
        for entry in entries
        if entry["format"] == "png" and str(entry["name"]).startswith("dm_heatmap_")
    ]
    assert {entry["name"] for entry in dm_entries} == {
        "dm_heatmap_left_tail",
        "dm_heatmap_right_tail",
    }
    for entry in dm_entries:
        assert entry["source_artifacts"] == [
            "forecasts/benchmark_forecasts.parquet",
            "forecasts/ml_tail_forecasts.parquet",
        ]
        assert entry["claim_scope"] == "post_24check_cross_suite_fz_dm_diagnostic"
        assert "strict global common sample (N=8)" in entry["caption"]
        assert "Fissler-Ziegel joint VaR-ES loss" in entry["caption"]
    assert any(entry["name"] == "coverage_breach_rates_left_tail" for entry in entries)
    assert any(entry["name"] == "benchmark_murphy_right_tail" for entry in entries)
    assert any("does not report hedge PnL" in entry["caption"] for entry in entries)
    assert all((run_dir / entry["path"]).exists() for entry in entries)
    dm_loss_rows = reporting_figures._cross_suite_dm_loss_rows(run_dir)
    assert set(dm_loss_rows["plot_label"].unique().to_list()) == {
        "GJR-GARCH-EVT",
        "LGBM plain MLE C",
        "LGBM UniBM C",
    }
    assert paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL not in set(
        dm_loss_rows["model_name"].unique().to_list()
    )
    left_dm_records = reporting_figures._cross_suite_dm_records(
        dm_loss_rows,
        paper_module.TAIL_SIDE_LEFT,
    )
    assert len(left_dm_records) == 6
    assert {record["common_n"] for record in left_dm_records} == {8}
    assert {record["loss_family"] for record in left_dm_records} == {"var_es_fz_loss"}
    assert {record["candidate_label"] for record in left_dm_records} == {
        "GJR-GARCH-EVT",
        "LGBM plain MLE C",
        "LGBM UniBM C",
    }
    missing_unibm = dm_loss_rows.filter(pl.col("plot_label") != "LGBM UniBM C")
    missing_records = reporting_figures._cross_suite_dm_records(
        missing_unibm,
        paper_module.TAIL_SIDE_LEFT,
    )
    assert {record["common_n"] for record in missing_records} == {0}
    assert all(
        record["inference_status"] == "unavailable_no_global_common_sample"
        for record in missing_records
    )
    full_overlay = reporting_figures._full_sample_var_overlay_forecasts(run_dir)
    assert "JP-only direct" not in set(full_overlay["plot_group"].to_list())
    assert {"Benchmark comparator", "Promoted ML-tail"}.issubset(
        set(full_overlay["plot_group"].to_list())
    )
    stress_overlay = reporting_figures._stress_overlay_forecasts(run_dir)
    stress_groups = set(stress_overlay["plot_group"].to_list())
    assert "JP-only direct" not in stress_groups
    assert {
        "GJR-GARCH-EVT",
        "LGBM POT-GPD plain MLE (C)",
        "LGBM POT-GPD UniBM (C)",
    }.issubset(stress_groups)


def test_export_figures_skips_missing_optional_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "empty_figures"
    run_dir.mkdir(parents=True)
    stale = run_dir / "latex" / "figures" / "stale.png"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")

    result = reporting_figures.export_figures(run_dir=run_dir, manifest={"run_id": "empty_figures"})

    assert result.figure_entries == []
    assert result.figure_dir.exists()
    assert not stale.exists()
    assert reporting_figures._available_tail_sides(pl.DataFrame()) == []
    assert reporting_figures._first_float(pl.DataFrame(), "x") is None
    assert reporting_figures._optional_float(None) is None
    assert reporting_figures._optional_float("bad") is None
    assert reporting_figures._optional_float(float("nan")) is None
    assert reporting_figures._series_percent(pl.DataFrame({"x": [0.1]}), "missing") == [0.0]
    assert (
        reporting_figures._limit_rows_for_plot(
            pl.DataFrame({"x": list(range(20))}), max_rows=3
        ).height
        == 3
    )


def test_export_figures_renders_target_distribution_diagnostics(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "target_figures"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = []
    for idx in range(240):
        gap = 0.006 * math.sin(idx / 8)
        if idx % 59 == 0:
            gap -= 0.04
        if idx % 71 == 0:
            gap += 0.05
        rows.append(
            {
                "forecast_date": f"2025-02-{(idx % 28) + 1:02d}",
                "forecast_sample": True,
                "gap_t": gap,
            }
        )
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")

    result = reporting_figures.export_figures(
        run_dir=run_dir,
        manifest={"run_id": "target_figures"},
    )
    target_names = {
        "target_tail_motivation",
    }
    entries = [
        entry for entry in result.figure_entries if str(entry.get("name", "")).startswith("target_")
    ]

    assert {entry["name"] for entry in entries if entry["format"] == "png"} == target_names
    assert {entry["name"] for entry in entries if entry["format"] == "pdf"} == target_names
    assert all(entry["source_artifacts"] == ["panel/modeling_panel.parquet"] for entry in entries)
    assert all(
        entry["claim_scope"] == "target_distribution_motivation_not_forecast_validation"
        for entry in entries
    )
    assert all((run_dir / entry["path"]).exists() for entry in entries)


def test_reporting_new_figure_helpers_lock_selection_order_and_loss_sign(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "runs" / "reporting_new_helpers"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "model_name": "garch_t",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "information_set": "target_history_only",
                "rows": 500,
                "var_breach_rate": 0.04,
                "expected_breach_rate": 0.05,
                "exceedance_count": 20,
                "mean_quantile_loss": 0.002,
                "mean_fz_loss": -5.0,
            },
            {
                "model_name": "gjr_garch_evt",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "information_set": "target_history_only",
                "rows": 500,
                "var_breach_rate": 0.06,
                "expected_breach_rate": 0.05,
                "exceedance_count": 30,
                "mean_quantile_loss": 0.003,
                "mean_fz_loss": -4.0,
            },
        ]
    ).write_parquet(metrics_dir / "benchmark_metrics_per_model.parquet")
    robust_metric_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for idx, information_set in enumerate(reporting_figures.INFORMATION_LADDER_ORDER):
            robust_metric_rows.append(
                {
                    "model_name": reporting_figures.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
                    "tail_side": tail_side,
                    "information_set": information_set,
                    "rows": 500,
                    "var_breach_rate": 0.05,
                    "expected_breach_rate": 0.05,
                    "exceedance_count": 25,
                    "kupiec_pvalue": 0.50,
                    "christoffersen_pvalue": 0.50,
                    "mean_quantile_loss": 0.001,
                    "mean_fz_loss": -3.0 - idx,
                }
            )
    robust_metric_rows.append(
        {
            "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
            "tail_side": paper_module.TAIL_SIDE_LEFT,
            "information_set": "japan_only",
            "rows": 500,
            "var_breach_rate": 0.10,
            "expected_breach_rate": 0.05,
            "exceedance_count": 50,
            "kupiec_pvalue": 0.01,
            "christoffersen_pvalue": 0.50,
            "mean_quantile_loss": 0.001,
            "mean_fz_loss": -3.0,
        }
    )
    pl.DataFrame(robust_metric_rows).write_parquet(
        metrics_dir / "ml_tail_metrics_per_model.parquet"
    )
    forecast_dir = run_dir / "forecasts"
    forecast_dir.mkdir(parents=True)
    forecast_rows = []
    for tail_side in (paper_module.TAIL_SIDE_LEFT, paper_module.TAIL_SIDE_RIGHT):
        for information_set in reporting_figures.INFORMATION_LADDER_ORDER:
            for day in range(12):
                forecast_rows.append(
                    {
                        "forecast_date": f"2026-01-{day + 1:02d}",
                        "target_family": "full_gap_settle_to_open",
                        "tail_side": tail_side,
                        "model_name": reporting_figures.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
                        "information_set": information_set,
                        "tail_level": 0.95,
                        "refit_frequency": "monthly",
                        "realized_loss": 0.01 + 0.001 * day,
                        "var_forecast": 0.012 + 0.0005 * day,
                        "is_valid_forecast": True,
                        "fit_status": "ok",
                    }
                )
    forecast_rows.append(
        {
            "forecast_date": "2026-01-01",
            "target_family": "full_gap_settle_to_open",
            "tail_side": paper_module.TAIL_SIDE_LEFT,
            "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
            "information_set": "japan_only",
            "tail_level": 0.95,
            "refit_frequency": "monthly",
            "realized_loss": 0.011,
            "var_forecast": 0.012,
            "is_valid_forecast": True,
            "fit_status": "ok",
        }
    )
    pl.DataFrame(forecast_rows).write_parquet(forecast_dir / "ml_tail_forecasts.parquet")
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-01",
                "target_family": "full_gap_settle_to_open",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "model_name": "garch_t",
                "information_set": "target_history_only",
                "tail_level": 0.95,
                "refit_frequency": "monthly",
                "realized_loss": 0.011,
                "var_forecast": 0.013,
                "is_valid_forecast": True,
                "fit_status": "ok",
            }
        ]
    ).write_parquet(forecast_dir / "benchmark_forecasts.parquet")

    robust_models = reporting_figures._coverage_robust_model_names(
        pl.read_parquet(metrics_dir / "ml_tail_metrics_per_model.parquet")
    )

    assert robust_models == (reporting_figures.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,)
    figure_dir = run_dir / "latex" / "figures"
    figure_dir.mkdir(parents=True)
    murphy_entries = reporting_figures._lgbm_24check_murphy_figures(
        run_dir=run_dir,
        figure_dir=figure_dir,
    )
    assert {entry["name"] for entry in murphy_entries if entry["format"] == "png"} == {
        "lgbm_24check_murphy_left_tail",
        "lgbm_24check_murphy_right_tail",
    }
    assert (metrics_dir / "lgbm_24check_murphy.parquet").exists()
    combined_forecasts = reporting_figures._combined_forecasts(run_dir)
    assert set(combined_forecasts["suite"].to_list()) == {
        "benchmark_baseline",
        "ml_tail_primary",
    }
    japan_only_order = reporting_figures._information_order("japan_only")
    us_core_order = reporting_figures._information_order("japan_only_plus_us_close_core")
    assert japan_only_order < us_core_order

    loss_frame = pl.DataFrame(
        [
            {
                "suite": "ml_tail",
                "forecast_date": "2026-01-01",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "model_name": "anchor",
                "information_set": "a",
                "fz_loss": 2.0,
            },
            {
                "suite": "ml_tail",
                "forecast_date": "2026-01-01",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "model_name": "candidate",
                "information_set": "b",
                "fz_loss": 1.0,
            },
            {
                "suite": "ml_tail",
                "forecast_date": "2026-01-02",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "model_name": "anchor",
                "information_set": "a",
                "fz_loss": 2.0,
            },
            {
                "suite": "ml_tail",
                "forecast_date": "2026-01-02",
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "model_name": "candidate",
                "information_set": "b",
                "fz_loss": 3.0,
            },
        ]
    )
    paired = reporting_figures._paired_cumulative_loss(
        loss_frame,
        tail_side=paper_module.TAIL_SIDE_LEFT,
        anchor={"suite": "ml_tail", "model_name": "anchor", "information_set": "a"},
        candidate={"suite": "ml_tail", "model_name": "candidate", "information_set": "b"},
    )

    assert paired["gain"].to_list() == [1.0, -1.0]
    assert paired["cumulative_gain"].to_list() == [1.0, 0.0]
    assert reporting_figures._plot_date_values(["2026-01-02", date(2026, 4, 1)]) == [
        date(2026, 1, 2),
        date(2026, 4, 1),
    ]
    fig, ax = reporting_figures.plt.subplots()
    reporting_figures._set_monthly_date_ticks(ax)
    assert isinstance(ax.xaxis.get_major_locator(), reporting_figures.mdates.MonthLocator)
    assert isinstance(ax.xaxis.get_major_formatter(), reporting_figures.mdates.DateFormatter)
    reporting_figures.plt.close(fig)


def test_reporting_dm_heatmap_helpers_cover_edge_cases() -> None:
    assert (
        reporting_figures._cross_suite_dm_gate_status(common_n=0, joint_exception_count=0)
        == "unavailable_no_global_common_sample"
    )
    assert (
        reporting_figures._cross_suite_dm_gate_status(
            common_n=reporting_figures.RESULT_MATRIX_MIN_DM_ROWS - 1,
            joint_exception_count=reporting_figures.RESULT_MATRIX_MIN_DM_EXCEPTIONS,
        )
        == "unavailable_insufficient_common_rows_for_inference"
    )
    assert (
        reporting_figures._cross_suite_dm_gate_status(
            common_n=reporting_figures.RESULT_MATRIX_MIN_DM_ROWS,
            joint_exception_count=reporting_figures.RESULT_MATRIX_MIN_DM_EXCEPTIONS - 1,
        )
        == "unavailable_insufficient_tail_events_for_inference"
    )
    assert (
        reporting_figures._cross_suite_dm_gate_status(
            common_n=reporting_figures.RESULT_MATRIX_MIN_DM_ROWS,
            joint_exception_count=reporting_figures.RESULT_MATRIX_MIN_DM_EXCEPTIONS,
        )
        == "ok_block_bootstrap_dm"
    )
    assert reporting_figures._dm_heatmap_annotation(None) == "n/a"
    assert (
        reporting_figures._dm_heatmap_annotation(
            {"mean_fz_loss_diff_candidate_minus_anchor": None, "common_n": 12}
        )
        == "n/a\nN=12"
    )
    assert "***" in reporting_figures._dm_heatmap_annotation(
        {"mean_fz_loss_diff_candidate_minus_anchor": -0.004, "pvalue_one_sided": 0.009}
    )
    assert reporting_figures._pvalue_stars(0.04) == "**"
    assert reporting_figures._pvalue_stars(0.08) == "*"
    assert reporting_figures._pvalue_stars(0.20) == ""
    assert reporting_figures._tail_threshold([float("nan"), -1.0, 0.0]) == 0.0
    assert (
        reporting_figures._information_order("unknown_set")
        == len(reporting_figures.INFORMATION_LADDER_ORDER) + 1
    )
    assert reporting_figures._ordered_unique(["a", "b", "a", 2]) == ["a", "b", "2"]
    assert reporting_figures._entity_label("japan_only") == "JP only"


def test_reporting_model_selection_helpers_cover_missing_and_promoted_cases() -> None:
    assert (
        reporting_figures._metric_row_for_model(
            pl.DataFrame(), tail_side=paper_module.TAIL_SIDE_LEFT, model_names=("m",)
        )
        is None
    )
    assert (
        reporting_figures._metric_row_for_model(
            pl.DataFrame({"model_name": ["m"]}),
            tail_side=paper_module.TAIL_SIDE_LEFT,
            model_names=("m",),
        )
        is None
    )
    frame = pl.DataFrame(
        [
            {"tail_side": paper_module.TAIL_SIDE_LEFT, "model_name": "fallback", "value": 1},
            {"tail_side": paper_module.TAIL_SIDE_LEFT, "model_name": "preferred", "value": 2},
        ]
    )
    assert (
        reporting_figures._metric_row_for_model(
            frame,
            tail_side=paper_module.TAIL_SIDE_LEFT,
            model_names=("missing", "preferred", "fallback"),
        )
        or {}
    )["value"] == 2
    assert (
        reporting_figures._metric_row_for_model(
            frame, tail_side=paper_module.TAIL_SIDE_RIGHT, model_names=("preferred",)
        )
        is None
    )

    assert (
        reporting_figures._promoted_metric_for_tail(pl.DataFrame(), paper_module.TAIL_SIDE_LEFT)
        is None
    )
    promoted_spec = reporting_figures.PROMOTED_TAIL_MODEL_SPECS[0]
    promoted_frame = pl.DataFrame(
        [
            {
                "tail_side": promoted_spec["tail_side"],
                "model_name": promoted_spec["model_name"],
                "information_set": promoted_spec["information_set"],
                "value": 3,
            }
        ]
    )
    assert (
        reporting_figures._promoted_metric_for_tail(promoted_frame, str(promoted_spec["tail_side"]))
        or {}
    )["value"] == 3
    assert (
        reporting_figures._promoted_metric_for_tail(promoted_frame, paper_module.TAIL_SIDE_RIGHT)
        is None
    )


def test_compact_dm_rows_selects_ladder_and_promoted_family_records() -> None:
    promoted_spec = reporting_figures.PROMOTED_TAIL_MODEL_SPECS[0]
    tail_side = str(promoted_spec["tail_side"])
    dm = pl.DataFrame(
        [
            {
                "tail_side": tail_side,
                "comparison_family": "information_set_ladder",
                "comparison_axis": "information_set_increment",
                "baseline_entity": "japan_only",
                "candidate_entity": "japan_only_plus_us_close_core",
                "loss_family": "var_es_fz_loss",
                "row_id": "ladder_fz",
            },
            {
                "tail_side": tail_side,
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "baseline_entity": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "candidate_entity": promoted_spec["model_name"],
                "information_set": promoted_spec["information_set"],
                "loss_family": "var_quantile_loss",
                "row_id": "promoted_quantile_fallback",
            },
        ]
    )

    compact = reporting_figures._compact_dm_rows(dm, tail_side)

    assert compact["row_id"].to_list() == ["ladder_fz", "promoted_quantile_fallback"]
    empty_dm = pl.DataFrame(
        schema={
            "tail_side": pl.String,
            "comparison_family": pl.String,
            "comparison_axis": pl.String,
            "baseline_entity": pl.String,
            "candidate_entity": pl.String,
            "loss_family": pl.String,
        }
    )
    assert reporting_figures._compact_dm_rows(empty_dm, tail_side).is_empty()


def test_reporting_claim_scope_helpers_cover_restricted_edges(tmp_path: Path) -> None:
    metrics = pl.DataFrame(
        [
            {
                "suite": "ml_tail",
                "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "information_set": "japan_only",
                "tail_level": 0.95,
                "sample_policy": "primary_common_sample",
                "common_sample_status": "ok",
                "rows": 20,
                "var_breach_rate": 0.05,
                "exceedance_count": 1,
                "mean_quantile_loss": 0.01,
                "mean_fz_loss": -1.0,
                "mean_exceedance_severity": 0.02,
            },
            {
                "suite": "ml_tail",
                "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "information_set": "japan_only_plus_us_close_core",
                "tail_level": 0.95,
                "sample_policy": "primary_common_sample",
                "common_sample_status": "ok",
                "rows": 20,
                "var_breach_rate": 0.05,
                "exceedance_count": 1,
                "mean_quantile_loss": 0.009,
                "mean_fz_loss": -1.1,
                "mean_exceedance_severity": 0.01,
            },
            {
                "suite": "ml_tail_per_model",
                "model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
                "information_set": "japan_only",
                "tail_level": 0.95,
                "rows": 20,
                "var_breach_rate": 0.0,
                "exceedance_count": 0,
                "mean_quantile_loss": 0.02,
                "mean_fz_loss": -0.8,
                "mean_exceedance_severity": None,
            },
            {
                "suite": "ml_tail_per_model",
                "model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
                "information_set": "japan_only_plus_us_close_core",
                "tail_level": 0.95,
                "rows": 20,
                "var_breach_rate": 0.05,
                "exceedance_count": 1,
                "mean_quantile_loss": 0.018,
                "mean_fz_loss": -0.9,
                "mean_exceedance_severity": 0.03,
            },
        ]
    )
    severity_text = reporting_latex._es_severity_to_latex(metrics)
    assert "primary" in severity_text
    assert "LGBM direct quantile" in severity_text
    assert "JP only" in severity_text
    assert "japan\\_only" not in severity_text
    assert paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL not in severity_text
    assert "0.010000" in severity_text
    metric_text = reporting_latex._metrics_to_latex(
        metrics.filter(pl.col("model_name") == paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL)
    )
    assert "LGBM direct quantile" in metric_text
    assert paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL not in metric_text
    assert reporting_latex._severity_rows(pl.DataFrame()) == []
    assert reporting_latex._range_label(None, 1) == "n/a"
    assert reporting_latex._range_label(5, 5) == "5"
    assert reporting_latex._range_label(5, 7) == "5--7"
    coverage = pl.DataFrame(
        [
            {
                "source_family": "jquants",
                "source_block": "japan_history",
                "feature": "n225_day_return_lag1",
                "missingness_rate": 0.0,
            },
            {
                "source_family": "massive",
                "source_block": "us_core",
                "feature": "spy_return",
                "missingness_rate": 0.1,
            },
            {
                "source_family": "massive",
                "source_block": "us_late_session",
                "feature": "spy_late_30m_return",
                "missingness_rate": 0.2,
            },
            {
                "source_family": "massive",
                "source_block": "japan_proxy",
                "feature": "ewj_return",
                "missingness_rate": 0.3,
            },
            {
                "source_family": "massive",
                "source_block": "asia_proxy",
                "feature": "ewy_return",
                "missingness_rate": 0.4,
            },
            {
                "source_family": "jquants",
                "source_block": "options_risk",
                "feature": "option_iv",
                "missingness_rate": 0.5,
            },
            {
                "source_family": "fred",
                "source_block": "fred_credit_enriched",
                "feature": "baa_spread",
                "missingness_rate": 0.6,
            },
        ]
    )
    coverage_rows = reporting_latex._predictor_block_coverage_rows(coverage)
    assert {row["role"] for row in coverage_rows} >= {
        "Japan/history anchor",
        "U.S. close core",
        "U.S. late-session timing",
        "Japan proxy increment",
        "Asia proxy increment",
        "Options-risk diagnostic",
        "Macro/credit enrichment",
    }
    coverage_text = reporting_latex._predictor_block_coverage_to_latex(coverage)
    assert "feature-matrix gates" in coverage_text
    assert reporting_latex._source_block_role("other_controls") == "Supporting control"
    promoted_spec = reporting_latex.PROMOTED_TAIL_MODEL_SPECS[0]
    promoted_metric = pl.DataFrame(
        [
            {
                "model_name": promoted_spec["model_name"],
                "information_set": promoted_spec["information_set"],
                "tail_side": promoted_spec["tail_side"],
                "rows": 550,
                "var_breach_rate": 0.047,
                "expected_breach_rate": 0.05,
                "mean_quantile_loss": 0.001,
                "mean_fz_loss": -4.0,
                "mean_exceedance_severity": 0.01,
            }
        ]
    )
    promoted_dm = pl.DataFrame(
        [
            {
                "tail_side": promoted_spec["tail_side"],
                "information_set": promoted_spec["information_set"],
                "candidate_entity": promoted_spec["model_name"],
                "baseline_entity": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "loss_family": "var_quantile_loss",
                "mean_loss_diff_candidate_minus_baseline": -0.1,
                "pvalue_one_sided": 0.04,
                "reject_10pct": True,
                "inference_status": "ok_block_bootstrap_dm",
            },
            {
                "tail_side": promoted_spec["tail_side"],
                "information_set": promoted_spec["information_set"],
                "candidate_entity": promoted_spec["model_name"],
                "baseline_entity": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "loss_family": "var_es_fz_loss",
                "mean_loss_diff_candidate_minus_baseline": None,
                "pvalue_one_sided": None,
                "reject_10pct": False,
                "inference_status": "unavailable",
            },
        ]
    )
    summary_dm = pl.DataFrame(
        [
            {
                "tail_side": paper_module.TAIL_SIDE_LEFT,
                "comparison_family": "information_set_ladder",
                "comparison_axis": "information_set_increment",
                "information_set": "japan_only_plus_us_close_core",
                "candidate_entity": "japan_only_plus_us_close_core",
                "baseline_entity": "japan_only",
                "loss_family": "var_es_fz_loss",
                "mean_loss_diff_candidate_minus_baseline": -0.01,
                "pvalue_one_sided": 0.03,
                "inference_status": "ok_block_bootstrap_dm",
            },
            {
                "tail_side": promoted_spec["tail_side"],
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "information_set": promoted_spec["information_set"],
                "candidate_entity": promoted_spec["model_name"],
                "baseline_entity": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "loss_family": "var_es_fz_loss",
                "mean_loss_diff_candidate_minus_baseline": -0.02,
                "pvalue_one_sided": 0.02,
                "inference_status": "ok_block_bootstrap_dm",
            },
        ]
    )
    dm_summary_text = reporting_latex._dm_summary_to_latex(summary_dm)
    assert "negative loss differences favor the candidate" in dm_summary_text
    assert "JP only -> +US close" in dm_summary_text
    assert "Direct quantile -> promoted ML-tail" in dm_summary_text
    assert "Benchmark suite -> promoted ML-tail" in dm_summary_text
    assert "ok\\_block\\_bootstrap\\_dm" in dm_summary_text
    assert "missing\\_dm\\_artifact" in reporting_latex._dm_summary_to_latex(None)
    promoted_rows = reporting_latex._promoted_tail_model_rows(promoted_metric, dm=promoted_dm)
    assert promoted_rows[0]["promotion_status"] == "pass"
    assert promoted_rows[0]["dm_quantile"]["reject_10pct"] is True
    assert (
        reporting_latex._promoted_tail_model_rows(pl.DataFrame())[0]["promotion_status"]
        == "missing_metric_row"
    )
    assert reporting_latex._promoted_dm_row(None, promoted_spec, "var_quantile_loss") is None
    assert reporting_latex._promoted_dm_row(pl.DataFrame({"x": [1]}), promoted_spec, "x") is None
    assert (
        reporting_latex._promoted_dm_row(
            pl.DataFrame(
                {
                    "tail_side": ["other_tail"],
                    "information_set": [promoted_spec["information_set"]],
                    "candidate_entity": [promoted_spec["model_name"]],
                    "baseline_entity": [paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL],
                    "loss_family": ["var_quantile_loss"],
                }
            ),
            promoted_spec,
            "var_quantile_loss",
        )
        is None
    )
    assert (
        reporting_latex._selection_candidates(
            pl.DataFrame(
                {
                    "model_name": ["m"],
                    "tail_side": ["left_tail"],
                    "rows": [100],
                    "var_breach_rate": [None],
                    "expected_breach_rate": [0.05],
                    "mean_quantile_loss": [0.1],
                    "mean_fz_loss": [-0.5],
                }
            ),
            suite_group="demo",
        )
        == []
    )
    assert (
        reporting_latex._selected_model_performance_rows(
            pl.DataFrame(
                {
                    "model_name": ["historical_quantile"],
                    "tail_side": [paper_module.TAIL_SIDE_LEFT],
                    "rows": [100],
                    "var_breach_rate": [0.05],
                    "expected_breach_rate": [0.05],
                    "mean_quantile_loss": [0.1],
                    "mean_fz_loss": [-0.5],
                }
            ),
            pl.DataFrame(),
        )
        == []
    )
    assert "rej10" in reporting_latex._dm_cell(promoted_rows[0]["dm_quantile"])
    assert reporting_latex._dm_cell(promoted_rows[0]["dm_fz"]) == "unavailable"
    assert reporting_latex._dm_cell(None) == "n/a"
    assert (
        reporting_latex._severity_claim_scope(
            {
                "suite": "ml_tail_per_model",
                "model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
            }
        )
        == "restricted_diagnostic"
    )
    assert reporting_latex._severity_claim_scope({"sample_policy": "primary_common_sample"}) == (
        "primary"
    )
    assert reporting_latex._severity_claim_scope({}) == "diagnostic"
    assert reporting_tables._paper_metric_rows(pl.DataFrame()).is_empty()
    assert reporting_tables._paper_metric_rows(pl.DataFrame({"rows": [1]})).is_empty()
    filtered_metrics = reporting_tables._paper_metric_rows(
        pl.DataFrame(
            [
                {
                    "sample_policy": "primary_common_sample",
                    "common_sample_status": "ok",
                    "fit_status": "ok",
                    "is_valid_forecast": True,
                    "rows": 10,
                },
                {
                    "sample_policy": "primary_common_sample",
                    "common_sample_status": "ok",
                    "fit_status": "failed",
                    "is_valid_forecast": True,
                    "rows": 11,
                },
                {
                    "sample_policy": "primary_common_sample",
                    "common_sample_status": "ok",
                    "fit_status": "ok",
                    "is_valid_forecast": False,
                    "rows": 12,
                },
            ]
        )
    )
    assert filtered_metrics["rows"].to_list() == [10]

    matrix = pl.DataFrame(
        [
            {
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": "var_quantile_loss",
                "model_name": paper_module.ML_TAIL_LOCATION_SCALE_MODEL,
                "tail_level": 0.95,
                "common_n": 121,
                "joint_exception_count": 6,
                "metric_status": "skipped",
                "metric_value": 0.1,
            }
        ]
    )
    dm = pl.DataFrame(
        [
            {
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": "var_quantile_loss",
                "inference_status": "ok_block_bootstrap_dm",
            },
            {
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": "var_quantile_loss",
                "inference_status": "unavailable_insufficient_tail_events_for_inference",
            },
        ]
    )
    result_text = reporting_latex._result_matrix_to_latex(matrix)
    summary_text = reporting_latex._result_matrix_summary_to_latex(matrix, dm=dm)
    assert paper_module.ML_TAIL_LOCATION_SCALE_MODEL not in result_text
    assert "1/2" in summary_text
    assert reporting_latex._result_matrix_summary_rows(pl.DataFrame(), dm=None) == []
    assert reporting_latex._inference_status_counts(None, "status", "ok") == {}

    run_dir = tmp_path / "reports" / "runs" / "ml_tail_reporting"
    (run_dir / "metrics").mkdir(parents=True)
    (run_dir / "forecasts").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    metrics.drop("suite").write_parquet(run_dir / "metrics" / "ml_tail_metrics.parquet")
    metrics.drop("suite").write_parquet(run_dir / "metrics" / "ml_tail_metrics_per_model.parquet")
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-01",
                "target_family": "full_gap_settle_to_open",
                "model_name": paper_module.ML_TAIL_DIRECT_QUANTILE_MODEL,
                "information_set": "japan_only",
                "tail_level": 0.95,
                "refit_frequency": "monthly",
                "var_forecast": 0.01,
                "realized_loss": 0.02,
                "is_valid_forecast": True,
            }
        ]
    ).write_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")

    latex = export_tables(run_dir=run_dir)
    severity_export = (latex.latex_dir / "tailrisk_es_severity_table.tex").read_text(
        encoding="utf-8"
    )
    assert latex.tables == 6
    assert (latex.latex_dir / "ml_tail_promoted_tail_models_table.tex").exists()
    assert (latex.latex_dir / "appendix_lgbm_all_models_table.tex").exists()
    assert "ml\\_tail\\_per\\_model" in severity_export


def test_locked_run_refuses_config_mismatch_without_force(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "benchmark_locked"
    panel_dir = run_dir / "panel"
    metrics_dir = run_dir / "metrics"
    panel_dir.mkdir(parents=True)
    metrics_dir.mkdir(parents=True)
    pl.DataFrame(
        [{"forecast_date": "2026-01-01", "clean_sample": True, "realized_loss": 0.01}]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    (metrics_dir / "benchmark_status.json").write_text("{}", encoding="utf-8")
    (run_dir / "manifest.json").write_text('{"config_hash": "stale"}', encoding="utf-8")

    with pytest.raises(paper_module.PipelineRunError, match="config is locked"):
        evaluate_benchmark_suite(run_dir=run_dir, workers=1)

    with pytest.raises(paper_module.PipelineRunError, match="Unknown evaluation suite"):
        evaluate_suite(run_dir=run_dir, workers=1, suite="advanced", force=True)


def test_evaluate_suite_dispatches_registered_suite_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_dispatch(name: str) -> object:
        def _dispatch(**kwargs: object) -> paper_module.EvaluationResult:
            calls.append((name, kwargs))
            return paper_module.EvaluationResult(
                run_id=name,
                run_dir=cast(Path, kwargs["run_dir"]),
                forecast_rows=1,
                metric_rows=1,
                status=name,
            )

        return _dispatch

    monkeypatch.setattr(evaluation_dispatch, "evaluate_benchmark_suite", fake_dispatch("benchmark"))
    monkeypatch.setattr(evaluation_dispatch, "evaluate_ml_tail_suite", fake_dispatch("ml_tail"))
    monkeypatch.setattr(
        evaluation_dispatch, "evaluate_sensitivity_suite", fake_dispatch("sensitivity")
    )

    assert (
        evaluation_dispatch.evaluate_suite(run_dir=tmp_path, suite="benchmark").status
        == "benchmark"
    )
    assert evaluation_dispatch.evaluate_suite(run_dir=tmp_path, suite="ml-tail").status == "ml_tail"
    assert (
        evaluation_dispatch.evaluate_suite(run_dir=tmp_path, suite="sensitivity").status
        == "sensitivity"
    )
    assert [name for name, _ in calls] == ["benchmark", "ml_tail", "sensitivity"]


def test_benchmark_and_ml_tail_require_current_leakage_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "leakage_required"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-01",
                "clean_sample": True,
                "realized_loss": 0.01,
                "gap_t": -0.01,
                "target_open_ts_utc": datetime(2026, 1, 1, 23, 45, tzinfo=UTC),
                "model_cutoff_ts_utc": datetime(2025, 12, 31, 21, 0, tzinfo=UTC),
                "forecast_sample": True,
                "forecast_sample_reason": None,
                "target_clean_sample": True,
                "join_miss_reason": None,
                "mapping_status": "normal_trading",
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    pl.DataFrame([]).write_parquet(panel_dir / "feature_coverage.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )

    with pytest.raises(paper_module.PipelineRunError, match="leakage check artifact"):
        evaluate_benchmark_suite(run_dir=run_dir, workers=1)
    with pytest.raises(paper_module.PipelineRunError, match="leakage check artifact"):
        evaluate_ml_tail_suite(run_dir=run_dir, workers=1)

    write_leakage_check(run_dir=run_dir)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-02",
                "clean_sample": True,
                "realized_loss": 0.02,
                "gap_t": -0.02,
                "target_open_ts_utc": datetime(2026, 1, 2, 23, 45, tzinfo=UTC),
                "model_cutoff_ts_utc": datetime(2026, 1, 1, 21, 0, tzinfo=UTC),
                "forecast_sample": True,
                "forecast_sample_reason": None,
                "target_clean_sample": True,
                "join_miss_reason": None,
                "mapping_status": "normal_trading",
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    with pytest.raises(paper_module.PipelineRunError, match="stale leakage check artifact"):
        evaluate_benchmark_suite(run_dir=run_dir, workers=1)


def test_write_leakage_check_outputs_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "benchmark_leakage"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-05",
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 30, tzinfo=UTC),
                "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
                "gap_t": -0.02,
                "realized_loss": 0.02,
                "forecast_sample": True,
                "forecast_sample_reason": None,
                "target_clean_sample": True,
                "join_miss_reason": None,
                "mapping_status": "normal_trading",
                "spy_return": 0.01,
                "spy_return__available_ts_utc": datetime(2026, 1, 2, 21, 15, tzinfo=UTC),
                "spy_return__fill_method": "direct",
                "spy_return__source_date": "2026-01-02",
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )

    result = write_leakage_check(run_dir=run_dir)

    assert result.rows == 1
    assert result.failures == 0
    assert result.warnings == 1
    assert result.output_path.exists()
    summary = json.loads((run_dir / "audits" / "leakage_check_summary.json").read_text())
    assert summary["status_counts"] == {"warn": 1}
    assert summary["warning_reason_counts"] == {"lag_below_conservative_warning_threshold": 1}


def test_leakage_binding_uses_deterministic_panel_signature(tmp_path: Path) -> None:
    rows = [
        {
            "forecast_date": "2026-01-06",
            "target_open_ts_utc": datetime(2026, 1, 5, 23, 45, tzinfo=UTC),
            "model_cutoff_ts_utc": datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
            "gap_t": -0.02,
            "realized_loss": 0.02,
            "forecast_sample": True,
            "forecast_sample_reason": None,
            "target_clean_sample": True,
            "join_miss_reason": None,
            "mapping_status": "normal_trading",
        },
        {
            "forecast_date": "2026-01-05",
            "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
            "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 0, tzinfo=UTC),
            "gap_t": -0.01,
            "realized_loss": 0.01,
            "forecast_sample": True,
            "forecast_sample_reason": None,
            "target_clean_sample": True,
            "join_miss_reason": None,
            "mapping_status": "normal_trading",
        },
    ]
    frame = pl.DataFrame(rows)
    reversed_frame = pl.DataFrame(list(reversed(rows)))
    signature = paper_core._deterministic_frame_signature(
        frame,
        columns=paper_module.PANEL_SIGNATURE_COLUMNS,
        sort_columns=("forecast_date",),
    )

    assert signature == paper_core._deterministic_frame_signature(
        reversed_frame,
        columns=paper_module.PANEL_SIGNATURE_COLUMNS,
        sort_columns=("forecast_date",),
    )

    run_dir = tmp_path / "reports" / "runs" / "leakage_bound"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    frame.write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PIPELINE_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_leakage_check(run_dir=run_dir)
    paper_core._assert_leakage_gate(run_dir)
    frame.with_columns(pl.lit(0.99).alias("realized_loss")).write_parquet(
        panel_dir / "modeling_panel.parquet"
    )
    with pytest.raises(paper_module.PipelineRunError, match="stale leakage check artifact"):
        paper_core._assert_leakage_gate(run_dir)


def test_leakage_signature_fails_closed_on_missing_signature_column() -> None:
    frame = pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-05",
                "target_open_ts_utc": datetime(2026, 1, 5, tzinfo=UTC),
            }
        ]
    )

    with pytest.raises(paper_module.PipelineRunError, match="panel signature columns missing"):
        paper_core._deterministic_frame_signature(
            frame,
            columns=paper_module.PANEL_SIGNATURE_COLUMNS,
            sort_columns=("forecast_date",),
        )


def test_build_panel_with_synthetic_vendor_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_rows = [
        _raw_futures_row("2026-01-05", settle=50000, ac=50100),
        _raw_futures_row("2026-01-06", ao=50500, settle=50600, ac=50700),
    ]
    massive_daily = [
        {
            "ticker": "SPY",
            "bar_date_et": "2026-01-02",
            "close": 100.0,
            "high": 101.0,
            "low": 99.0,
        },
        {
            "ticker": "SPY",
            "bar_date_et": "2026-01-05",
            "close": 101.0,
            "high": 102.0,
            "low": 100.0,
        },
    ]
    fred_rows = [{"series_id": "VIXCLS", "observation_date": "2026-01-05", "value": 18.0}]

    _patch_paper_module(monkeypatch, "_git_commit", lambda: "abcdef123456")
    _patch_paper_module(monkeypatch, "_git_dirty", lambda: False)
    _patch_paper_module(
        monkeypatch,
        "_fetch_jquants_futures_rows",
        lambda **kwargs: raw_rows,
    )
    _patch_paper_module(
        monkeypatch,
        "_fetch_jquants_nikkei_option_rows",
        lambda **kwargs: [],
    )
    _patch_paper_module(
        monkeypatch,
        "_fetch_massive_predictors",
        lambda **kwargs: (massive_daily, []),
    )
    _patch_paper_module(
        monkeypatch,
        "_fetch_fred_predictors",
        lambda **kwargs: fred_rows,
    )
    _patch_paper_module(
        monkeypatch,
        "_fetch_cboe_predictors",
        lambda **kwargs: [],
    )

    settings = Settings(
        reports_dir=tmp_path / "reports",
        bronze_data_dir=tmp_path / "data" / "bronze",
        silver_data_dir=tmp_path / "data" / "silver",
        gold_data_dir=tmp_path / "data" / "gold",
    )
    result = build_panel(settings=settings, start="2026-01-05", end="2026-01-06")
    panel = pl.read_parquet(result.panel_path)

    assert result.rows == 2
    assert result.clean_rows == 1
    assert result.run_id.startswith("tailrisk_20260105_20260106_")
    assert "spy_return" in panel.columns
    assert (result.run_dir / "panel" / "feature_coverage.parquet").exists()
    assert (result.run_dir / "manifest.json").exists()
    gold_panel_dir = artifact_utils._gold_panel_dir(settings.gold_data_dir, result.run_id)
    gold_panel = gold_panel_dir / "modeling_panel.parquet"
    gold_calendar = gold_panel.with_name("calendar_map.parquet")
    assert gold_panel.exists()
    assert gold_calendar.exists()
    assert result.panel_path == gold_panel


def test_default_end_date_resolves_to_most_recent_completed_friday() -> None:
    assert paper_core.resolve_default_end_date(date(2026, 5, 9)) == "2026-05-08"
    assert paper_core.resolve_default_end_date(date(2026, 5, 10)) == "2026-05-08"
    assert paper_core.resolve_default_end_date(date(2026, 5, 11)) == "2026-05-08"
    assert paper_core.resolve_default_end_date(date(2026, 5, 14)) == "2026-05-08"
    assert paper_core.resolve_default_end_date(date(2026, 5, 15)) == "2026-05-08"


def test_private_pipeline_helpers_cover_defensive_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert static_empirical_es(np.array([1.0, 2.0]), 3.0) == 3.0
    assert (
        empirical_excess_es_companion(
            train_losses=np.array([1.0, 2.0]),
            train_var_forecasts=np.array([3.0, 3.0]),
            forecast_var=4.0,
        )
        == 4.0
    )
    assert build_feature_coverage_records([]) == []
    assert paper_core._bounded_workers(2) == 2
    assert paper_core._bounded_workers(0) >= 1
    paper_core._set_nested_thread_limits()
    assert paper_core._month_chunks(start="2026-01-30", end="2026-03-02") == [
        ("2026-01-30", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-02"),
    ]
    assert paper_core._window_return([100.0, 101.0, 102.0], 2) == pytest.approx(
        math.log(102.0) - math.log(100.0)
    )
    assert paper_core._window_return([100.0], 2) is None
    assert paper_core._window_range([101.0, None], [99.0, None]) == pytest.approx(
        math.log(101.0) - math.log(99.0)
    )
    assert paper_core._window_range([None], [None]) is None
    assert paper_core._safe_name("C:USDJPY") == "c_usdjpy"
    long_shard_id = paper_core._forecast_shard_id(
        paper_module.ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
        0.95,
        target_family="full_gap_settle_to_open",
        tail_side="right_tail",
        information_set=("japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy"),
        refit_frequency="monthly",
    )
    assert long_shard_id == "lgbm_pot_plain__sto__R__D__q0950__m"
    assert len(long_shard_id) < 48
    assert paper_core._feature_description("fx_usdjpy_level").startswith("canonical USDJPY")
    assert paper_core._feature_description("spy_late_30m_return").startswith(
        "U.S.-listed instrument"
    )
    assert paper_core._feature_description("fred_vixcls_diff").startswith("first difference")
    assert paper_core._feature_description("fred_vixcls_level").startswith("daily source level")
    assert paper_core._feature_description("spy_late_volume_surge").startswith(
        "late-session volume"
    )
    assert paper_core._feature_description("custom_feature") == "run predictor candidate"
    assert paper_core._safe_mean(np.array([math.nan])) is None
    with pytest.raises(paper_module.PipelineRunError, match="Expected finite numeric"):
        paper_core._required_float(None)
    assert paper_core._fmt(None) == ""
    assert paper_core._fmt(1.2345678) == "1.234568"
    assert paper_core._optional_float(True) is None
    artifact_run_dir = tmp_path / "artifact_run"
    artifact_run_dir.mkdir()
    artifact_target = tmp_path / "gold_panel.parquet"
    (artifact_run_dir / "manifest.json").write_text(
        json.dumps({"gold_artifacts": {"modeling_panel": str(artifact_target)}}),
        encoding="utf-8",
    )
    assert (
        artifact_utils._gold_artifact_path(
            artifact_run_dir,
            "modeling_panel",
            tmp_path / "fallback.parquet",
        )
        == artifact_target
    )
    cache_rows_path = tmp_path / "cache_rows.parquet"
    pl.DataFrame([{"requested_date": "2026-01-05", "value": 1.0}]).write_parquet(cache_rows_path)
    assert paper_cache._read_parquet_records(cache_rows_path)[0]["requested_date"] == "2026-01-05"
    assert paper_cache._cache_covers_dates(cache_rows_path, ["2026-01-05"]) is False
    assert paper_cache._first_row_date_value({}, ("requested_date", "Date")) is None
    assert (
        stat_utils.moving_block_one_sided_pvalue(
            np.array([1.0]),
            observed_mean=None,
            reps=2,
            block_length=1,
            rng=np.random.default_rng(1),
        )
        is None
    )
    assert (
        stat_utils.kupiec_pof_test(
            breaches=np.array([]),
            expected_probability=0.05,
        )["status"]
        == "unavailable_invalid_input"
    )
    assert (
        stat_utils.kupiec_pof_test(
            breaches=np.array([False, False]),
            expected_probability=0.05,
        )["status"]
        == "ok"
    )
    assert (
        stat_utils.christoffersen_independence_test(
            breaches=np.array([False]),
        )["status"]
        == "unavailable_insufficient_oos"
    )
    assert (
        stat_utils.christoffersen_independence_test(
            breaches=np.array([False, False, False]),
        )["status"]
        == "ok"
    )
    assert paper_core._optional_float("bad") is None
    assert (
        paper_core._massive_daily_feature_map(
            [
                {"ticker": "SPY", "bar_date_et": "2026-01-02", "close": None},
                {"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0},
            ]
        )["2026-01-02"]["spy_range"]
        is None
    )

    class Fitted:
        std_resid = np.array([0.1, 0.2, math.nan])

    assert paper_core._standardized_arch_losses(np.array([1.0, 2.0]), Fitted()).tolist() == [
        -0.1,
        -0.2,
    ]
    var_t, es_t = paper_core._standardized_student_t_loss_var_es(
        mean_return_forecast=0.0,
        scale_forecast=1.0,
        nu=8.0,
        tail_level=0.95,
    )
    assert es_t >= var_t
    assert var_t == pytest.approx(1.6104158400592559)
    assert es_t == pytest.approx(2.1770604941459104)
    var_ref, es_ref = paper_core._standardized_student_t_loss_var_es(
        mean_return_forecast=0.001,
        scale_forecast=0.02,
        nu=7.0,
        tail_level=0.975,
    )
    assert var_ref == pytest.approx(0.03896944494135751)
    assert es_ref == pytest.approx(0.0511784232197246)
    standardized = paper_core._standardized_arch_losses(
        np.array([1.0, 2.0, 3.0]),
        object(),
    )
    assert standardized.mean() == pytest.approx(0.0)
    tail = paper_core._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, tail["standardized_es"]) >= cast(float, tail["standardized_var"])
    assert cast(int, tail["evt_exceedance_count"]) >= paper_module.DEFAULT_MIN_TRAIN_EXCEEDANCES
    assert tail["tail_method"] == "pot_gpd_filtered_es"
    assert tail["threshold_quantile"] == 0.90
    diagnostics = json.loads(str(tail["threshold_diagnostics_json"]))
    assert diagnostics
    assert any(row["selected_threshold"] for row in diagnostics)
    assert any("shape_delta_from_previous" in row for row in diagnostics)
    empirical_tail = paper_core._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.90,
    )
    assert cast(float, empirical_tail["standardized_es"]) >= cast(
        float,
        empirical_tail["standardized_var"],
    )
    assert empirical_tail["tail_method"] == "empirical_filtered_es"

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (0.0, 0.0, 1.0),
    )
    exponential_tail = paper_core._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, exponential_tail["standardized_es"]) >= cast(
        float,
        exponential_tail["standardized_var"],
    )

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.stats.genpareto.fit",
        lambda *args, **kwargs: (1.1, 0.0, 1.0),
    )
    heavy_tail = paper_core._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, heavy_tail["standardized_es"]) >= cast(
        float,
        heavy_tail["standardized_var"],
    )
    with pytest.raises(paper_module.PipelineRunError, match="insufficient standardized losses"):
        paper_core._pot_gpd_standardized_tail(
            standardized_losses=np.array([1.0, 2.0]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PipelineRunError, match="insufficient exceedances"):
        paper_core._pot_gpd_standardized_tail(
            standardized_losses=np.concatenate([np.zeros(1060), np.arange(40.0)]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PipelineRunError, match="No run found"):
        paper_module.resolve_run_dir(
            Settings(reports_dir=tmp_path / "missing_reports"),
            "",
        )
    with pytest.raises(paper_module.PipelineRunError, match="Run does not exist"):
        paper_module.resolve_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "missing_run",
        )
    with pytest.raises(paper_module.PipelineRunError, match="Missing modeling panel"):
        evaluate_benchmark_suite(run_dir=tmp_path / "no_panel", workers=1)
    runs_dir = tmp_path / "reports" / "runs"
    latest = runs_dir / "tailrisk_latest"
    older = runs_dir / "tailrisk_older"
    older.mkdir(parents=True)
    latest.mkdir(parents=True)
    assert paper_module.resolve_run_dir(Settings(reports_dir=tmp_path / "reports"), "").name
    assert (
        paper_module.resolve_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "tailrisk_latest",
        )
        == latest
    )

    monkeypatch.setattr(
        "n225_open_gap_tail.forecasting.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no git")),
    )
    assert paper_core._git_commit() == "unknown"
    assert paper_core._git_dirty() is True


def test_feature_asof_and_source_maps_cover_edge_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoff = datetime(2026, 1, 10, 21, 0, tzinfo=UTC)
    assert paper_core._features_asof({}, "", cutoff=cutoff, fill_method="ffill") == {}
    assert (
        paper_core._features_asof(
            {"bad-date": {"spy_return": 0.1}},
            "bad-date",
            cutoff=cutoff,
            fill_method="ffill",
        )
        == {}
    )
    assert (
        paper_core._features_asof(
            {"2025-12-01": {"spy_return": 0.1}},
            "2026-01-10",
            cutoff=cutoff,
            fill_method="ffill",
        )
        == {}
    )
    assert (
        paper_core._features_asof(
            {
                "bad-date": {"spy_return": 0.1},
                "2026-01-09": {
                    "spy_return": 0.1,
                    "spy_return__available_ts_utc": datetime(2026, 1, 11, tzinfo=UTC),
                },
            },
            "2026-01-10",
            cutoff=cutoff,
            fill_method="ffill",
        )
        == {}
    )
    selected = paper_core._features_asof(
        {
            "2026-01-09": {
                "spy_return": 0.1,
                "spy_return__available_ts_utc": datetime(2026, 1, 9, 21, tzinfo=UTC),
            }
        },
        "2026-01-10",
        cutoff=cutoff,
        fill_method="ffill",
    )
    assert selected["spy_return__fill_method"] == "ffill"

    assert paper_core._fred_features_asof({}, "", cutoff=cutoff) == {}
    assert paper_core._fred_features_asof({}, "not-a-date", cutoff=cutoff) == {}
    assert (
        paper_core._fred_feature_candidate_asof(
            {"bad-date": {"fred_dgs2_level": 1.0}},
            date_key="2026-01-10",
            feature_name="fred_dgs2_level",
            cutoff=cutoff,
        )
        is None
    )
    fred_selected = paper_core._fred_features_asof(
        {
            "2026-01-08": {
                "fred_dgs2_level": 4.0,
                "fred_dgs2_diff": None,
                "fred_dgs2_level__available_ts_utc": datetime(2026, 1, 8, 21, tzinfo=UTC),
                "fred_dgs2_level__source_date": "bad-date",
            }
        },
        "2026-01-10",
        cutoff=cutoff,
    )
    assert fred_selected["fred_dgs2_level__fill_method"] == "forward_fill_fred_release_lag"
    assert fred_selected["fred_dgs2_diff"] == 0.0
    assert fred_selected["fred_dgs2_diff__is_filled_diff"] is True

    assert paper_core._feature_record_available_by_cutoff({}, cutoff)
    assert not paper_core._feature_record_available_by_cutoff(
        {"spy_return": 0.1, "spy_return__available_ts_utc": None},
        cutoff,
    )
    assert paper_core._coerce_datetime("bad") is None
    assert paper_core._coerce_datetime("2026-01-10T21:00:00").tzinfo is not None

    diagnostics = paper_core._evt_threshold_diagnostics(np.linspace(-1.0, 3.0, 200))
    assert diagnostics
    assert any(row["shape"] is not None for row in diagnostics)

    massive_features = paper_core._massive_daily_feature_map(
        [
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-08",
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
                "bar_end_ts_utc": datetime(2026, 1, 8, 21, tzinfo=UTC),
            },
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-09",
                "close": 101.0,
                "high": None,
                "low": None,
                "bar_end_ts_utc": datetime(2026, 1, 9, 21, tzinfo=UTC),
            },
        ],
        calendar_records=[
            {
                "calendar_date": "2026-01-09",
                "us_close_ts_utc": datetime(2026, 1, 9, 18, tzinfo=UTC),
            }
        ],
    )
    assert massive_features["2026-01-09"]["spy_return"] is not None
    assert massive_features["2026-01-09"]["spy_range"] is None

    cboe_features = paper_core._cboe_feature_map(
        [
            {
                "symbol": "VVIX",
                "observation_date": "2026-01-08",
                "close": 100.0,
            },
            {
                "symbol": "VIX",
                "observation_date": "2026-01-09",
                "close": 18.0,
                "range": 1.2,
                "vendor_available_ts_utc": "2026-01-09T21:15:00Z",
            },
        ]
    )
    assert cboe_features["2026-01-09"]["cboe_vix_close"] == 18.0
    cboe_features["2026-01-09"]["cboe_vix_range"] = None
    cboe_asof = paper_core._features_asof(
        cboe_features,
        "2026-01-09",
        cutoff=datetime(2026, 1, 9, 21, 30, tzinfo=UTC),
        fill_method="forward_fill_us_holiday",
    )
    assert cboe_asof["cboe_vix_close"] == pytest.approx(18.0)
    assert cboe_asof["cboe_vix_range"] is None
    assert cboe_asof["cboe_vix_close__source_date"] == "2026-01-09"

    fx_context = paper_core._canonical_fx_context(
        massive_daily_records=[],
        fred_records=[
            {
                "series_id": "DEXJPUS",
                "observation_date": "",
                "vendor_available_ts_utc": cutoff,
                "value": 150.0,
            },
            {
                "series_id": "DEXJPUS",
                "observation_date": "2026-01-08",
                "vendor_available_ts_utc": datetime(2026, 1, 8, 21, 15, tzinfo=UTC),
                "value": 150.0,
            },
        ],
        calendar_records=[],
    )
    assert paper_core._canonical_fx_asof(fx_context, us_date="", cutoff=cutoff) == {}
    assert paper_core._canonical_fx_asof(fx_context, us_date="bad-date", cutoff=cutoff) == {}
    fx = paper_core._canonical_fx_asof(fx_context, us_date="2026-01-10", cutoff=cutoff)
    assert fx["fx_source"] == "fred_h10_latest_released"

    monkeypatch.setattr("n225_open_gap_tail.forecasting.subprocess.run", _fake_completed_process)
    assert paper_core._git_commit() == "abc123"
    assert paper_core._git_dirty() is False


def _fake_completed_process(*args: object, **kwargs: object) -> object:
    command = args[0] if args else []
    stdout = "abc123\n" if "rev-parse" in command else ""
    return type("Completed", (), {"stdout": stdout})()


def _normalized_target_row(
    trading_date: str,
    *,
    day_open: float,
    settle: float,
    contract_code: str = "161030018",
) -> dict[str, object]:
    return {
        "trading_date": trading_date,
        "product_category": "NK225F",
        "contract_code": contract_code,
        "contract_month": "2026-03",
        "central_contract_month_flag": True,
        "last_trading_day": "2026-03-12",
        "special_quotation_day": "2026-03-13",
        "day_session_open": day_open,
        "day_session_high": day_open + 1.0,
        "day_session_low": day_open - 1.0,
        "day_session_close": day_open,
        "night_session_open": settle,
        "night_session_high": settle + 1.0,
        "night_session_low": settle - 1.0,
        "night_session_close": settle,
        "settlement_price": settle,
        "volume": 100.0,
        "open_interest": 1000.0,
        "target_open_ts_utc": datetime.fromisoformat(f"{trading_date}T00:00:00+00:00"),
        "target_open_ts_jst": f"{trading_date}T09:00:00+09:00",
        "vendor_available_ts_utc": datetime.fromisoformat(f"{trading_date}T18:00:00+00:00"),
    }


def _jpx_calendar_records(*dates: str) -> list[dict[str, object]]:
    return [
        {
            "calendar_date": value,
            "is_jpx_trading_day": True,
            "is_us_trading_day": True,
        }
        for value in dates
    ]


def _raw_futures_row(
    trading_date: str,
    *,
    ao: float = 50200,
    ah: float = 50400,
    al: float = 50100,
    ac: float = 50300,
    eo: float = 50050,
    eh: float = 50200,
    el: float = 50000,
    ec: float = 50100,
    settle: float = 50000,
) -> dict[str, object]:
    return {
        "Date": trading_date,
        "ProdCat": "NK225F",
        "Code": "161030018",
        "CM": "2026-03",
        "CCMFlag": True,
        "EmMrgnTrgDiv": "002",
        "AO": ao,
        "AH": ah,
        "AL": al,
        "AC": ac,
        "EO": eo,
        "EH": eh,
        "EL": el,
        "EC": ec,
        "Settle": settle,
        "Vo": 100,
        "OI": 1000,
        "LTD": "2026-03-12",
        "SQD": "2026-03-13",
    }
