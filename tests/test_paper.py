from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl
import pytest

import n225_open_gap_tail.paper as paper_module
import n225_open_gap_tail.paper.cache as paper_cache
import n225_open_gap_tail.paper.evaluation as paper_evaluation
import n225_open_gap_tail.paper.features as paper_features
import n225_open_gap_tail.paper.inference as paper_inference
import n225_open_gap_tail.paper.leakage as paper_leakage
import n225_open_gap_tail.paper.panel as paper_panel
import n225_open_gap_tail.paper.reporting as paper_reporting
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.datalake import VendorErrorClass
from n225_open_gap_tail.paper import (
    build_feature_coverage_records,
    build_feature_matrix_gate_records,
    build_fields_coverage_audit_records,
    build_leakage_check_records,
    build_modeling_panel_records,
    build_p2b_modeling_rows,
    build_paper_run_id,
    build_spy_late_session_feature_records,
    drop_low_variance_features,
    empirical_excess_es_companion,
    evaluate_p2a_run,
    evaluate_p2b_run,
    evaluate_paper_run,
    filtered_historical_es,
    find_oos_start_date,
    global_oos_intersection,
    kupiec_pof_test,
    p2b_feature_columns_for_information_set,
    pairwise_oos_intersection,
    quantile_loss,
    static_empirical_es,
    validate_forecast_values,
    validate_worker_payload,
    write_paper_latex_tables,
    write_paper_leakage_check,
    write_paper_panel,
)


def test_build_paper_run_id_binds_stage_window_timestamp_and_commit() -> None:
    run_id = build_paper_run_id(
        start="2008-05-07",
        end="2026-04-28",
        run_ts_utc=datetime(2026, 4, 28, 12, 30, tzinfo=UTC),
        git_commit="abcdef123456",
        stage="p2a",
    )

    assert run_id == "p2a_20080507_20260428_20260428T123000Z_commit_abcdef12"


def test_paper_package_split_preserves_import_compatibility() -> None:
    assert paper_panel.write_paper_panel is write_paper_panel
    assert paper_inference.build_mcs_records is paper_module.build_mcs_records
    assert paper_cache.cleanup_transient_unavailable_markers is (
        paper_module.cleanup_transient_unavailable_markers
    )
    assert paper_evaluation.evaluate_paper_run is evaluate_paper_run
    assert paper_features.drop_low_variance_features is drop_low_variance_features
    assert paper_leakage.write_paper_leakage_check is write_paper_leakage_check
    assert paper_reporting.write_paper_latex_tables is write_paper_latex_tables


def test_forecast_validity_distinguishes_var_breach_from_invalid_forecast() -> None:
    assert validate_forecast_values(2.0, 2.5) == (True, None)
    assert validate_forecast_values(2.0, 1.9) == (False, "invalid_es_below_var")
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


def test_p2b_information_sets_select_nested_feature_blocks() -> None:
    coverage_rows: list[dict[str, object]] = [
        {"feature": "spy_return", "source_block": "us_core"},
        {"feature": "spy_late_30m_return", "source_block": "us_late_session"},
        {"feature": "fred_vixcls_level", "source_block": "fred_core"},
        {"feature": "fred_rates_staleness_days", "source_block": "fred_core"},
        {"feature": "fx_usdjpy_level", "source_block": "fx_core"},
        {"feature": "ewj_return", "source_block": "japan_proxy"},
        {"feature": "ewh_return", "source_block": "asia_proxy"},
        {"feature": "fred_bamlh0a0hym2_level", "source_block": "fred_credit_enriched"},
    ]

    japan_only = p2b_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only",
    )
    us_core = p2b_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core",
    )
    japan_proxy = p2b_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core_plus_japan_proxy",
    )
    asia_proxy = p2b_feature_columns_for_information_set(
        coverage_rows,
        information_set="japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy",
    )

    assert "loss_lag_1" in japan_only
    assert "spy_return" not in japan_only
    assert "fx_usdjpy_level" in us_core
    assert "fred_rates_staleness_days" in us_core
    assert "fred_bamlh0a0hym2_level" not in us_core
    assert "ewj_return" in japan_proxy
    assert "ewh_return" in asia_proxy


def test_build_p2b_modeling_rows_uses_only_lagged_loss_history() -> None:
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

    rows = build_p2b_modeling_rows(panel_rows, ["loss_lag_1", "spy_return"])

    assert rows[0]["loss_lag_1"] is None
    assert rows[1]["loss_lag_1"] == 1.0
    assert rows[1]["calendar_dst_edt"] == 1.0
    assert rows[1]["calendar_absorption_post_us_close"] == 1.0
    assert rows[1]["spy_return"] == 0.02


def test_worker_payload_rejects_dataframe_objects() -> None:
    validate_worker_payload({"panel_path": "/tmp/panel.parquet", "tail_level": 0.95})
    with pytest.raises(paper_module.PaperRunError, match="Polars frame"):
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
        spy_minute_records=[],
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
        spy_minute_records=[],
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
    features = paper_module._fred_feature_map(
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
        paper_module._fred_features_asof(features, "", cutoff=datetime(2026, 1, 9, tzinfo=UTC))
        == {}
    )
    assert (
        paper_module._fred_features_asof(
            features, "bad-date", cutoff=datetime(2026, 1, 9, tzinfo=UTC)
        )
        == {}
    )
    assert paper_module._fred_features_asof(features, "2026-01-09", cutoff=None) == {}
    cutoff_before_new_release = datetime(2026, 1, 9, 21, 30, tzinfo=UTC)
    filled = paper_module._fred_features_asof(
        features,
        "2026-01-09",
        cutoff=cutoff_before_new_release,
    )
    assert filled is not None
    assert filled["fred_dgs2_level"] == 3.0
    assert filled["fred_dgs2_level__fill_method"] == "forward_fill_fred_release_lag"
    assert (
        paper_module._fred_features_asof(
            features,
            "2026-01-10",
            cutoff=datetime(2026, 1, 10, 21, 30, tzinfo=UTC),
        )["fred_dgs2_level"]
        == 3.1
    )
    assert (
        paper_module._fred_features_asof(
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

    features = build_spy_late_session_feature_records(
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
        spy_minute_records=[],
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
        spy_minute_records=[],
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
        spy_minute_records=[],
        fred_records=[],
    )

    assert panel[0]["join_miss_reason"] == "calendar_desync"


def test_forecast_sample_reason_priority_and_calendar_map_propagation() -> None:
    target_open = datetime(2026, 1, 5, 23, 45, tzinfo=UTC)
    cutoff = datetime(2026, 1, 2, 21, 30, tzinfo=UTC)

    assert (
        paper_module._forecast_sample_exclusion_reason(
            target_clean=False,
            mapping_status="us_holiday",
            join_miss_reason="calendar_desync",
            cutoff=None,
            target_open=None,
        )
        == "target_not_clean"
    )
    assert (
        paper_module._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="us_holiday",
            join_miss_reason="calendar_desync",
            cutoff=cutoff,
            target_open=target_open,
        )
        == "mapping_status_not_normal_trading"
    )
    assert (
        paper_module._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="normal_trading",
            join_miss_reason="calendar_desync",
            cutoff=cutoff,
            target_open=target_open,
        )
        == "has_join_miss_reason"
    )
    assert (
        paper_module._forecast_sample_exclusion_reason(
            target_clean=True,
            mapping_status="normal_trading",
            join_miss_reason=None,
            cutoff=None,
            target_open=target_open,
        )
        == "missing_cutoff_or_target_open"
    )
    assert (
        paper_module._forecast_sample_exclusion_reason(
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
        spy_minute_records=[],
        fred_records=[],
    )

    assert panel[0]["mapping_status"] == "us_holiday"
    assert panel[0]["mapping_reason"] == "us_closed_jpx_open"
    assert panel[0]["forecast_sample"] is False
    assert panel[0]["forecast_sample_reason"] == "mapping_status_not_normal_trading"


def test_canonical_fx_uses_fred_h10_latest_released_and_ignores_massive_fx() -> None:
    context = paper_module._canonical_fx_context(
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

    fx = paper_module._canonical_fx_asof(
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
    context = paper_module._canonical_fx_context(
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
    fx = paper_module._canonical_fx_asof(
        context,
        us_date="2026-01-12",
        cutoff=datetime(2026, 1, 12, 21, 30, tzinfo=UTC),
    )

    assert fx["fx_source"] == "fred_h10_latest_released"
    assert fx["fx_usdjpy_level"] == 160.0
    assert fx["fx_staleness_days"] == 3


def test_canonical_fx_nulls_beyond_stale_fallback_window() -> None:
    context = paper_module._canonical_fx_context(
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

    fx = paper_module._canonical_fx_asof(
        context,
        us_date="2026-01-22",
        cutoff=datetime(2026, 1, 22, 21, 30, tzinfo=UTC),
    )

    assert fx["fx_source"] == "null_unavailable"
    assert fx["fx_fallback_reason"] == "fred_fx_stale_beyond_fill_window"


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
        "day_session_close": 100.0,
        "night_session_open": 99.0,
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
    assert flagged[0]["invalid_settlement_price"] is False

    settings = Settings(data_dir=tmp_path / "data")
    paper_module._write_jquants_silver_cache(settings=settings, rows=flagged)
    assert (
        tmp_path
        / "data/silver/jquants_nk225f_daily/schema_version=1/year=2026/month=01/data.parquet"
    ).exists()


def test_derived_spy_records_flow_into_feature_map_and_alignment() -> None:
    available = datetime(2026, 1, 2, 21, 5, tzinfo=UTC)
    features = paper_module._spy_minute_feature_map(
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
    features = paper_module._spy_minute_feature_map(
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


def test_vendor_payload_helpers_and_marker(tmp_path: Path) -> None:
    assert paper_module._payload_results({"results": "bad"}) == []
    assert paper_module._payload_results({"results": [{"x": 1}, 2]}) == [{"x": 1}]

    marker = tmp_path / "data.unavailable.json"
    paper_module._write_unavailable_marker(
        marker,
        source="massive",
        error_class=VendorErrorClass.UNAVAILABLE_ENTITLEMENT,
        http_status=403,
        requested_range=["2026-01-01", "2026-01-31"],
    )
    assert json.loads(marker.read_text(encoding="utf-8"))["error_class"] == (
        "unavailable_entitlement"
    )
    assert paper_module._unavailable_marker_covers(marker, "2026-01-05", "2026-01-10")
    assert not paper_module._unavailable_marker_covers(marker, "2026-01-01", "2026-02-01")
    transient = tmp_path / "transient.unavailable.json"
    paper_module._write_unavailable_marker(
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
    metadata_path = parquet_path.with_suffix(parquet_path.suffix + ".metadata.json")
    metadata_path.write_text(
        json.dumps(
            {
                "requested_dates": ["2026-01-05", "2026-01-06"],
                "requested_range": ["2026-01-05", "2026-01-09"],
            }
        ),
        encoding="utf-8",
    )

    assert paper_module._cache_covers_dates(parquet_path, ["2026-01-05"])
    assert not paper_module._cache_covers_dates(
        parquet_path,
        ["2026-01-05", "2026-01-31"],
    )
    assert paper_module._cache_covers_range(parquet_path, "2026-01-06", "2026-01-08")
    assert not paper_module._cache_covers_range(parquet_path, "2026-01-01", "2026-01-08")
    assert not paper_module._metadata_covers_range({}, "2026-01-01", "2026-01-08")
    rows = [
        {"requested_date": "2026-01-01", "value": 1},
        {"requested_date": "2026-01-05", "value": 5},
        {"bar_date_et": "2026-01-06", "value": 6},
        {"observation_date": "2026-02-01", "value": 20},
    ]
    filtered = paper_module._filter_records_by_range(
        rows,
        start="2026-01-05",
        end="2026-01-06",
        date_fields=("requested_date", "bar_date_et", "observation_date"),
    )
    assert [row["value"] for row in filtered] == [5, 6]
    assert paper_module._filter_records_by_dates(
        rows,
        allowed_dates=["2026-01-06"],
        date_fields=("requested_date", "bar_date_et", "observation_date"),
    ) == [{"bar_date_et": "2026-01-06", "value": 6}]


def test_low_level_feature_and_bronze_helpers_cover_edge_cases() -> None:
    assert paper_module._feature_description("other") == "paper-grade predictor candidate"
    assert paper_module._feature_source_family("unknown") == "unknown"
    assert "EWH" in paper_module.PAPER_FETCH_MASSIVE_TICKERS
    assert "EWH" not in paper_module.PAPER_CORE_MASSIVE_TICKERS
    assert "C:USDJPY" not in paper_module.PAPER_FETCH_MASSIVE_TICKERS
    assert "C:USDJPY" not in paper_module.PAPER_CORE_MASSIVE_TICKERS
    assert "DEXJPUS" in paper_module.PAPER_FETCH_FRED_SERIES
    assert paper_module._feature_source_family("ewj_return") == "japan_proxy"
    assert paper_module._feature_source_family("ewh_return") == "asia_proxy"
    assert paper_module._feature_source_family("fx_usdjpy_level") == "fx_core"
    assert paper_module._feature_source_family("c_usdjpy_return") == "massive_daily"
    assert paper_module._feature_source_block("qqq_return") == "us_core"
    assert paper_module._panel_join_miss_reason({}, "") == "calendar_desync"
    assert (
        paper_module._panel_join_miss_reason(
            {"alignment_status": "missing_us_close"},
            "2026-01-02",
        )
        == "us_market_closed"
    )
    assert paper_module._panel_join_miss_reason({"alignment_pass": False}, "2026-01-02") == (
        "us_early_close_beyond_vendor_lag"
    )
    assert paper_module._rows_return([]) is None
    assert paper_module._rows_return([{"close": 0.0}, {"close": 1.0}]) is None

    row = paper_module._jquants_bronze_row(
        {"Date": "", "ProdCat": "NK225F", "AO": "bad", "Settle": "100"},
        requested_date="2026-01-05",
        source_endpoint="/endpoint",
        downloaded_at_utc=datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert row["Date"] == "2026-01-05"
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


def test_common_sample_eviction_and_headline_artifacts() -> None:
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
        stage="p2a",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    evictions = cast(list[dict[str, object]], artifacts["model_eviction"])
    fragile = next(row for row in evictions if row["model_name"] == "fragile_model")
    assert fragile["retained_for_headline"] is False
    assert fragile["eviction_reason"] == "coverage_below_model_eviction_threshold"
    headline_models = {
        row["model_name"] for row in cast(list[dict[str, object]], artifacts["headline_metrics"])
    }
    per_model_models = {
        row["model_name"] for row in cast(list[dict[str, object]], artifacts["per_model_metrics"])
    }
    assert "fragile_model" not in headline_models
    assert "fragile_model" in per_model_models
    assert cast(list[dict[str, object]], artifacts["loss_matrix"])
    assert cast(list[dict[str, object]], artifacts["dm_inference"])[0]["alternative"] == (
        "candidate_mean_diff_less_than_zero"
    )
    mcs = cast(list[dict[str, object]], artifacts["mcs"])
    assert any(row["included_in_mcs"] is False for row in mcs)
    murphy = cast(list[dict[str, object]], artifacts["murphy"])
    first_model_grid = [row for row in murphy if row["model_name"] == "historical_quantile"]
    assert len(first_model_grid) == 200
    assert cast(float, first_model_grid[0]["threshold_value"]) <= cast(
        float, first_model_grid[-1]["threshold_value"]
    )
    stress = cast(list[dict[str, object]], artifacts["stress_windows"])
    assert {row["window_name"] for row in stress} == {"loss_top_decile", "vix_top_decile"}


def test_hln_tmax_mcs_eliminates_worst_model_on_balanced_loss_matrix() -> None:
    loss_matrix: list[dict[str, object]] = []
    for index in range(160):
        forecast_date = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for model_name, base_loss in (
            ("best", 0.10),
            ("middle", 0.12),
            ("worst", 0.30),
        ):
            loss_matrix.append(
                {
                    "forecast_date": forecast_date.isoformat(),
                    "model_name": model_name,
                    "information_set": "set_a",
                    "tail_level": 0.95,
                    "fz_loss": base_loss + float(index % 7) / 1000.0,
                }
            )

    records = paper_module.build_mcs_records(loss_matrix, stage="p2b", reps=99)
    by_model = {str(row["model_name"]): row for row in records}

    assert by_model["best"]["included_in_mcs"] is True
    assert by_model["worst"]["included_in_mcs"] is False
    assert by_model["worst"]["elimination_step"] == 1
    assert by_model["worst"]["block_length"] == max(5, round(160 ** (1 / 3)))
    assert by_model["worst"]["method_note"] == "hln_tmax_moving_block_bootstrap"
    assert by_model["worst"]["tmax_stat"] is not None
    assert by_model["worst"]["active_model_set"] is not None


def test_incremental_and_dst_artifacts_use_block_bootstrap_dm_labels() -> None:
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
                    "model_name": paper_module.P2B_DIRECT_QUANTILE_MODEL,
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
                    "model_name": paper_module.P2B_DIRECT_QUANTILE_MODEL,
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
    dst = paper_module.build_dst_attenuation_records(
        forecasts,
        baseline_information_set="japan_only",
        expanded_information_set="japan_only_plus_us_close_core",
    )
    payload = json.dumps([*incremental, *dst])

    assert "GW" not in payload
    assert "Giacomini-White" not in payload
    assert any(row["dm_method"] == "moving_block_bootstrap_unconditional_dm" for row in incremental)
    assert any(row["inference_status"] == "ok_block_bootstrap_dm" for row in incremental)
    assert any(
        row["inference_status"] == "diagnostic_ratio_no_direct_dm_test"
        for row in dst
        if row["dst_regime"] == "absorption_coefficient"
    )


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
    monkeypatch.setattr(paper_module, "MODEL_EVICTION_COVERAGE_THRESHOLD", 0.50)
    monkeypatch.setattr(paper_module, "COMMON_SAMPLE_MIN_ANCHOR_COVERAGE", 0.90)

    artifacts = paper_module.build_common_sample_artifacts(
        forecasts,
        stage="p2a",
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
        stage="p2a",
        anchor_model="historical_quantile",
        anchor_information_set="target_history_only",
    )

    assert artifacts["common_sample_status"] == "unavailable_missing_anchor"
    eviction = cast(list[dict[str, object]], artifacts["model_eviction"])[0]
    assert eviction["eviction_reason"] == "missing_anchor_sample"
    assert paper_module.build_murphy_records([], stage="p2a") == []
    bad_matrix = paper_module.build_loss_matrix_records(
        [
            {
                **forecasts[0],
                "es_forecast": -1.0,
            }
        ],
        stage="p2a",
    )
    assert bad_matrix == []


def test_p2b_marks_active_feature_missing_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_ROWS", 5)
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

    result = paper_module._forecast_p2b_lightgbm_sequence(
        rows=rows,
        model_name=paper_module.P2B_DIRECT_QUANTILE_MODEL,
        information_set="japan_only_plus_us_close_core",
        candidate_features=["feature_x"],
        tail_level=0.95,
        oos_start="2026-04-06",
    )

    assert any(
        row["fit_status"] == "unavailable_feature_not_valid_at_cutoff"
        for row in result["forecasts"]
    )


def test_p2b_feature_unavailability_artifacts_aggregate_and_explode_dates() -> None:
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

    aggregate = paper_module.build_p2b_feature_unavailability_records(forecasts)
    exploded = paper_module.build_p2b_feature_unavailability_date_records(forecasts)

    by_feature = {row["feature"]: row for row in aggregate}
    assert by_feature["spy_late_volume_surge"]["missing_count"] == 1
    assert by_feature["spy_late_volume_surge"]["missing_rate"] == 0.5
    assert by_feature["fred_dgs10_level"]["source_block"] == "fred_core"
    assert {row["feature"] for row in exploded} == {
        "spy_late_volume_surge",
        "fred_dgs10_level",
    }
    assert all(row["forecast_date"] == "2026-04-06" for row in exploded)


def test_coverage_tests_return_unavailable_for_degenerate_inputs() -> None:
    assert kupiec_pof_test(breaches=np.array([]), expected_probability=0.05)["status"] == (
        "unavailable_invalid_input"
    )
    assert (
        kupiec_pof_test(
            breaches=np.array([False, False]),
            expected_probability=0.05,
        )["status"]
        == "unavailable_boundary_exceedance_rate"
    )

    assert (
        paper_module.christoffersen_independence_test(breaches=np.array([True]))["status"]
        == "unavailable_insufficient_oos"
    )
    assert (
        paper_module.christoffersen_independence_test(
            breaches=np.array([False, False, False]),
        )["status"]
        == "unavailable_boundary_transition_rate"
    )
    ok = paper_module.christoffersen_independence_test(
        breaches=np.array([False, True, False, False, True, True, False]),
    )
    assert ok["status"] == "ok"


def test_closed_form_p2a_forecasts_and_unknown_model() -> None:
    train = np.arange(1.0, 80.0) / 100.0

    historical = paper_module._forecast_one(
        train=train,
        model_name="historical_quantile",
        tail_level=0.95,
    )
    rolling = paper_module._forecast_one(
        train=train,
        model_name="rolling_quantile",
        tail_level=0.95,
    )
    ewma = paper_module._forecast_one(
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
    with pytest.raises(paper_module.PaperRunError, match="Unknown P2A model"):
        paper_module._forecast_one(train=train, model_name="unknown", tail_level=0.95)


def test_evaluate_p2a_shard_records_unavailable_oos(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    pl.DataFrame(
        [
            {"forecast_date": "2026-01-01", "clean_sample": True, "realized_loss": 0.01},
            {"forecast_date": "2026-01-02", "clean_sample": True, "realized_loss": 0.02},
        ]
    ).write_parquet(panel_path)

    result = paper_module._evaluate_p2a_shard(
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
    assert result["diagnostics"][0]["shard_id"] == (
        "model=historical_quantile/target=full_gap_settle_to_open/"
        "info=target_history_only/tail=0_950"
    )


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

    features = paper_module._spy_minute_feature_map(rows)

    assert features["2026-01-02"]["spy_late_30m_return"] is not None
    assert features["2026-01-05"]["spy_late_60m_return"] is not None
    assert features["2026-01-05"]["spy_late_volume_surge"] is not None


def test_evaluate_p2a_run_and_latex_export_with_synthetic_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "p2a_synthetic"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = [
        {
            "forecast_date": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day))
            .date()
            .isoformat(),
            "clean_sample": True,
            "realized_loss": float(day) / 100.0,
        }
        for day in range(80)
    ]
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PAPER_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_paper_leakage_check(run_dir=run_dir)

    monkeypatch.setattr(paper_module, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_ROWS", 30)
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)

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

    monkeypatch.setattr(paper_module, "_forecast_one", fake_forecast_one)

    result = evaluate_p2a_run(run_dir=run_dir, workers=1)
    latex = write_paper_latex_tables(run_dir=run_dir)

    assert result.status == "completed"
    assert result.forecast_rows > 0
    assert (run_dir / "forecasts" / "p2a_forecasts.parquet").exists()
    assert (
        run_dir
        / "forecasts"
        / "shards"
        / "model=historical_quantile"
        / "target=full_gap_settle_to_open"
        / "info=target_history_only"
        / "tail=0_950"
        / "forecasts.parquet"
    ).exists()
    assert (run_dir / "metrics" / "p2a_metrics.parquet").exists()
    assert latex.tables == 1
    assert (latex.latex_dir / "p2a_metrics_table.tex").exists()
    latex_text = (latex.latex_dir / "p2a_metrics_table.tex").read_text(encoding="utf-8")
    assert "% config_hash:" in latex_text
    assert "block-bootstrap DM" in latex_text
    assert "GW" not in latex_text
    assert "Giacomini-White" not in latex_text


def test_evaluate_p2b_run_writes_lightgbm_ladder_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "p2b_synthetic"
    panel_dir = run_dir / "panel"
    audits_dir = run_dir / "audits"
    panel_dir.mkdir(parents=True)
    audits_dir.mkdir(parents=True)
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(90):
        current = start + timedelta(days=day)
        rows.append(
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
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    pl.DataFrame(
        [
            {"feature": "spy_return", "source_block": "us_core"},
            {"feature": "ewj_return", "source_block": "japan_proxy"},
            {"feature": "ewh_return", "source_block": "asia_proxy"},
        ]
    ).write_parquet(panel_dir / "feature_coverage.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PAPER_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_paper_leakage_check(run_dir=run_dir)
    monkeypatch.setattr(paper_module, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_ROWS", 30)
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)
    monkeypatch.setattr(paper_module, "PAPER_TAIL_LEVELS", (0.95,))

    result = evaluate_p2b_run(run_dir=run_dir, workers=1)

    assert result.status == "completed_lightgbm_direct_quantile"
    assert (run_dir / "forecasts" / "p2b_forecasts.parquet").exists()
    forecasts = pl.read_parquet(run_dir / "forecasts" / "p2b_forecasts.parquet")
    assert forecasts["information_set"].n_unique() == 4
    assert (run_dir / "metrics" / "p2b_incremental_information.parquet").exists()
    assert (run_dir / "metrics" / "p2b_dst_attenuation.parquet").exists()
    assert (run_dir / "metrics" / "p2b_feature_unavailability.parquet").exists()
    assert (run_dir / "metrics" / "p2b_feature_unavailability_dates.parquet").exists()
    incremental_text = json.dumps(
        pl.read_parquet(run_dir / "metrics" / "p2b_incremental_information.parquet").to_dicts()
    )
    dst_text = json.dumps(
        pl.read_parquet(run_dir / "metrics" / "p2b_dst_attenuation.parquet").to_dicts()
    )
    assert "GW" not in incremental_text
    assert "GW" not in dst_text
    status = json.loads((run_dir / "metrics" / "p2b_status.json").read_text(encoding="utf-8"))
    assert status["unavailable_components"]["lightgbm_standardized_loss_pot_gpd"]
    assert status["registered_information_sets"]["model_d"].endswith("plus_asia_proxy")


def test_locked_run_refuses_config_mismatch_without_force(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "p2a_locked"
    panel_dir = run_dir / "panel"
    metrics_dir = run_dir / "metrics"
    panel_dir.mkdir(parents=True)
    metrics_dir.mkdir(parents=True)
    pl.DataFrame(
        [{"forecast_date": "2026-01-01", "clean_sample": True, "realized_loss": 0.01}]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    (metrics_dir / "p2a_status.json").write_text("{}", encoding="utf-8")
    (run_dir / "manifest.json").write_text('{"config_hash": "stale"}', encoding="utf-8")

    with pytest.raises(paper_module.PaperRunError, match="config is locked"):
        evaluate_p2a_run(run_dir=run_dir, workers=1)

    result = evaluate_paper_run(run_dir=run_dir, workers=1, stage="p2c", force=True)

    assert result.status == "unavailable_supplementary_stage_not_implemented_nonblocking"
    assert not (metrics_dir / "p2a_status.json").exists()
    p2c_status_path = run_dir / "metrics" / "p2c_status.json"
    assert p2c_status_path.exists()
    registered = json.loads(p2c_status_path.read_text(encoding="utf-8"))[
        "registered_information_sets"
    ]
    assert registered["model_c"] == "japan_only_plus_us_close_core_plus_japan_proxy"
    assert registered["model_d"] == (
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy"
    )


def test_p2a_and_p2b_require_current_leakage_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "leakage_required"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-01",
                "clean_sample": True,
                "realized_loss": 0.01,
                "gap_t": -0.01,
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    pl.DataFrame([]).write_parquet(panel_dir / "feature_coverage.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PAPER_CONFIG.config_hash()}),
        encoding="utf-8",
    )

    with pytest.raises(paper_module.PaperRunError, match="leakage check artifact"):
        evaluate_p2a_run(run_dir=run_dir, workers=1)
    with pytest.raises(paper_module.PaperRunError, match="leakage check artifact"):
        evaluate_p2b_run(run_dir=run_dir, workers=1)

    write_paper_leakage_check(run_dir=run_dir)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-02",
                "clean_sample": True,
                "realized_loss": 0.02,
                "gap_t": -0.02,
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    with pytest.raises(paper_module.PaperRunError, match="stale leakage check artifact"):
        evaluate_p2a_run(run_dir=run_dir, workers=1)


def test_write_paper_leakage_check_outputs_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "p2a_leakage"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "forecast_date": "2026-01-05",
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 30, tzinfo=UTC),
                "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
                "spy_return": 0.01,
                "spy_return__available_ts_utc": datetime(2026, 1, 2, 21, 15, tzinfo=UTC),
                "spy_return__fill_method": "direct",
                "spy_return__source_date": "2026-01-02",
            }
        ]
    ).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PAPER_CONFIG.config_hash()}),
        encoding="utf-8",
    )

    result = write_paper_leakage_check(run_dir=run_dir)

    assert result.rows == 1
    assert result.failures == 0
    assert result.warnings == 1
    assert result.output_path.exists()


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
    signature = paper_module._deterministic_frame_signature(
        frame,
        columns=paper_module.PANEL_SIGNATURE_COLUMNS,
        sort_columns=("forecast_date",),
    )

    assert signature == paper_module._deterministic_frame_signature(
        reversed_frame,
        columns=paper_module.PANEL_SIGNATURE_COLUMNS,
        sort_columns=("forecast_date",),
    )

    run_dir = tmp_path / "reports" / "paper_runs" / "leakage_bound"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    frame.write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps({"config_hash": paper_module.PAPER_CONFIG.config_hash()}),
        encoding="utf-8",
    )
    write_paper_leakage_check(run_dir=run_dir)
    paper_module._assert_leakage_gate(run_dir)
    frame.with_columns(pl.lit(0.99).alias("realized_loss")).write_parquet(
        panel_dir / "modeling_panel.parquet"
    )
    with pytest.raises(paper_module.PaperRunError, match="stale leakage check artifact"):
        paper_module._assert_leakage_gate(run_dir)


def test_write_paper_panel_with_synthetic_vendor_rows(
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

    monkeypatch.setattr(paper_module, "_git_commit", lambda: "abcdef123456")
    monkeypatch.setattr(paper_module, "_git_dirty", lambda: False)
    monkeypatch.setattr(
        paper_module,
        "_fetch_jquants_futures_rows",
        lambda **kwargs: raw_rows,
    )
    monkeypatch.setattr(
        paper_module,
        "_fetch_massive_paper_predictors",
        lambda **kwargs: (massive_daily, []),
    )
    monkeypatch.setattr(
        paper_module,
        "_fetch_fred_paper_predictors",
        lambda **kwargs: fred_rows,
    )
    monkeypatch.setattr(
        paper_module,
        "_fetch_cboe_paper_predictors",
        lambda **kwargs: [],
    )

    settings = Settings(
        reports_dir=tmp_path / "reports",
        bronze_data_dir=tmp_path / "data" / "bronze",
        silver_data_dir=tmp_path / "data" / "silver",
        gold_data_dir=tmp_path / "data" / "gold",
    )
    result = write_paper_panel(settings=settings, start="2026-01-05", end="2026-01-06")
    panel = pl.read_parquet(result.panel_path)

    assert result.rows == 2
    assert result.clean_rows == 1
    assert result.run_id.startswith("p2a_20260105_20260106_")
    assert "spy_return" in panel.columns
    assert (result.run_dir / "panel" / "feature_coverage.parquet").exists()
    assert (result.run_dir / "manifest.json").exists()


def test_private_paper_helpers_cover_defensive_edges(
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
    assert paper_module._bounded_workers(2) == 2
    assert paper_module._bounded_workers(0) >= 1
    paper_module._set_nested_thread_limits()
    assert paper_module._month_chunks(start="2026-01-30", end="2026-03-02") == [
        ("2026-01-30", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-02"),
    ]
    assert paper_module._window_return([100.0, 101.0, 102.0], 2) == pytest.approx(
        math.log(102.0) - math.log(100.0)
    )
    assert paper_module._window_return([100.0], 2) is None
    assert paper_module._window_range([101.0, None], [99.0, None]) == pytest.approx(
        math.log(101.0) - math.log(99.0)
    )
    assert paper_module._window_range([None], [None]) is None
    assert paper_module._safe_name("C:USDJPY") == "c_usdjpy"
    assert paper_module._feature_description("fx_usdjpy_level").startswith("canonical USDJPY")
    assert paper_module._feature_description("spy_late_30m_return").startswith("close-to-close")
    assert paper_module._feature_description("fred_vixcls_diff").startswith("first difference")
    assert paper_module._feature_description("fred_vixcls_level").startswith("daily source level")
    assert paper_module._feature_description("spy_late_volume_surge").startswith("SPY late-session")
    assert paper_module._feature_description("custom_feature") == "paper-grade predictor candidate"
    assert paper_module._safe_mean(np.array([math.nan])) is None
    with pytest.raises(paper_module.PaperRunError, match="Expected finite numeric"):
        paper_module._required_float(None)
    assert paper_module._fmt(None) == ""
    assert paper_module._fmt(1.2345678) == "1.234568"
    assert paper_module._optional_float(True) is None
    assert paper_module._optional_float("bad") is None
    assert (
        paper_module._massive_daily_feature_map(
            [
                {"ticker": "SPY", "bar_date_et": "2026-01-02", "close": None},
                {"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0},
            ]
        )["2026-01-02"]["spy_range"]
        is None
    )

    class Fitted:
        std_resid = np.array([0.1, 0.2, math.nan])

    assert paper_module._standardized_arch_losses(np.array([1.0, 2.0]), Fitted()).tolist() == [
        -0.1,
        -0.2,
    ]
    var_t, es_t = paper_module._standardized_student_t_loss_var_es(
        mean_return_forecast=0.0,
        scale_forecast=1.0,
        nu=8.0,
        tail_level=0.95,
    )
    assert es_t >= var_t
    assert var_t == pytest.approx(1.6104158400592559)
    assert es_t == pytest.approx(2.1770604941459104)
    var_ref, es_ref = paper_module._standardized_student_t_loss_var_es(
        mean_return_forecast=0.001,
        scale_forecast=0.02,
        nu=7.0,
        tail_level=0.975,
    )
    assert var_ref == pytest.approx(0.03896944494135751)
    assert es_ref == pytest.approx(0.0511784232197246)
    standardized = paper_module._standardized_arch_losses(
        np.array([1.0, 2.0, 3.0]),
        object(),
    )
    assert standardized.mean() == pytest.approx(0.0)
    tail = paper_module._pot_gpd_standardized_tail(
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
    empirical_tail = paper_module._pot_gpd_standardized_tail(
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
        "n225_open_gap_tail.paper.stats.genpareto.fit",
        lambda *args, **kwargs: (0.0, 0.0, 1.0),
    )
    exponential_tail = paper_module._pot_gpd_standardized_tail(
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
        "n225_open_gap_tail.paper.stats.genpareto.fit",
        lambda *args, **kwargs: (1.1, 0.0, 1.0),
    )
    heavy_tail = paper_module._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, heavy_tail["standardized_es"]) >= cast(
        float,
        heavy_tail["standardized_var"],
    )
    with pytest.raises(paper_module.PaperRunError, match="insufficient standardized losses"):
        paper_module._pot_gpd_standardized_tail(
            standardized_losses=np.array([1.0, 2.0]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PaperRunError, match="insufficient exceedances"):
        paper_module._pot_gpd_standardized_tail(
            standardized_losses=np.concatenate([np.zeros(1060), np.arange(40.0)]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PaperRunError, match="No paper run found"):
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "missing_reports"),
            "",
        )
    with pytest.raises(paper_module.PaperRunError, match="Paper run does not exist"):
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "missing_run",
        )
    with pytest.raises(paper_module.PaperRunError, match="Missing modeling panel"):
        evaluate_p2a_run(run_dir=tmp_path / "no_panel", workers=1)
    runs_dir = tmp_path / "reports" / "paper_runs"
    latest = runs_dir / "p2a_latest"
    older = runs_dir / "p2a_older"
    older.mkdir(parents=True)
    latest.mkdir(parents=True)
    assert paper_module.resolve_paper_run_dir(Settings(reports_dir=tmp_path / "reports"), "").name
    assert (
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "p2a_latest",
        )
        == latest
    )

    monkeypatch.setattr(
        "n225_open_gap_tail.paper.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no git")),
    )
    assert paper_module._git_commit() == "unknown"
    assert paper_module._git_dirty() is True


def _raw_futures_row(
    trading_date: str,
    *,
    ao: float = 50200,
    ac: float = 50300,
    ec: float = 50100,
    settle: float = 50000,
) -> dict[str, object]:
    return {
        "Date": trading_date,
        "ProdCat": "NK225F",
        "Code": "161030018",
        "CM": "2026-03",
        "CCMFlag": True,
        "AO": ao,
        "AC": ac,
        "EO": 50050,
        "EC": ec,
        "Settle": settle,
        "Vo": 100,
        "OI": 1000,
        "LTD": "2026-03-12",
        "SQD": "2026-03-13",
    }
