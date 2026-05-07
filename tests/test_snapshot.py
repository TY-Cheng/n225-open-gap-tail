from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl
import pytest

import n225_open_gap_tail.diagnostics.model_comparison as model_comparison_module
import n225_open_gap_tail.diagnostics.results_discussion as results_discussion_module
import n225_open_gap_tail.diagnostics.snapshot as snapshot_module
import n225_open_gap_tail.diagnostics.snapshot_gallery as snapshot_gallery
import n225_open_gap_tail.diagnostics.target_distribution as target_distribution_module
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.diagnostics.snapshot import (
    build_snapshot_id,
)
from n225_open_gap_tail.market.calendars import build_session_calendar_records
from n225_open_gap_tail.panel.target_audit import build_target_audit_records
from n225_open_gap_tail.panel.time_alignment import build_time_alignment_records
from n225_open_gap_tail.sources.jquants_futures import (
    build_jquants_schema_probe,
    normalize_jquants_futures_rows,
)


def test_build_snapshot_id_binds_window_timestamp_and_commit() -> None:
    snapshot_id = build_snapshot_id(
        start="2022-01-01",
        end="2026-04-28",
        run_ts_utc=datetime(2026, 4, 28, 6, 30, tzinfo=UTC),
        git_commit="abcdef123456",
    )

    assert snapshot_id == "20220101_20260428_20260428T063000Z_commit_abcdef12"


def test_latest_snapshot_ignores_panel_only_runs(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    incomplete = reports_dir / "runs" / "tailrisk_incomplete"
    complete = reports_dir / "runs" / "tailrisk_complete"
    incomplete.mkdir(parents=True)
    complete.mkdir(parents=True)
    (incomplete / "manifest.json").write_text(
        json.dumps({"run_id": "tailrisk_incomplete", "suite": "benchmark_panel"}),
        encoding="utf-8",
    )
    (complete / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "tailrisk_complete",
                "benchmark_eval_status": "completed",
                "ml_tail_eval_status": "completed_lightgbm_ml_tail_models",
            }
        ),
        encoding="utf-8",
    )

    resolved = snapshot_module._resolve_snapshot_run_dir(
        settings=Settings(reports_dir=reports_dir),
        run_id="latest",
    )

    assert resolved == complete


def test_schema_probe_maps_jquants_short_fields_and_counts_zero_prices() -> None:
    rows = [
        _raw_row("2026-01-05", "2026-03", "161030018"),
        _raw_row("2026-01-05", "2026-06", "161060018", ao=0),
    ]

    probe = build_jquants_schema_probe(rows)

    assert probe["fail_closed"] is False
    assert probe["product_counts"] == {"NK225F": 2}
    assert probe["zero_price_counts"] == {
        "day_session_open": 1,
        "day_session_high": 0,
        "day_session_low": 0,
        "day_session_close": 0,
        "night_session_open": 0,
        "night_session_high": 0,
        "night_session_low": 0,
        "night_session_close": 0,
        "settlement_price": 0,
    }


def test_normalize_jquants_rows_localizes_jst_and_invalidates_zero_prices() -> None:
    rows = [
        _raw_row("2026-03-09", "2026-03", "161030018", ao=51800, ec=54020),
        {**_raw_row("2026-03-09", "2026-03", "ignored"), "ProdCat": "NK225MF"},
        _raw_row("2026-03-10", "2026-03", "161030018", ec=0),
    ]

    records = normalize_jquants_futures_rows(
        rows,
        downloaded_at_utc=datetime(2026, 3, 11, tzinfo=UTC),
    )

    assert len(records) == 2
    assert records[0]["target_open_ts_jst"] == datetime(
        2026,
        3,
        9,
        8,
        45,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert records[0]["target_open_ts_utc"] == datetime(2026, 3, 8, 23, 45, tzinfo=UTC)
    assert records[1]["night_session_close"] is None


def test_target_audit_keeps_full_gap_when_night_close_missing_and_excludes_roll() -> None:
    downloaded = datetime(2026, 3, 11, tzinfo=UTC)
    raw_rows = [
        _raw_row("2026-03-04", "2026-03", "161030018", settle=50000, ac=50100),
        _raw_row("2026-03-05", "2026-03", "161030018", ao=50500, settle=50600, ac=50700),
        _raw_row("2026-03-06", "2026-03", "161030018", ao=50800, ec=0),
        _raw_row("2026-03-09", "2026-03", "161030018", ao=51000),
        _raw_row("2026-03-10", "2026-06", "161060018", ao=51100),
    ]
    normalized = normalize_jquants_futures_rows(raw_rows, downloaded_at_utc=downloaded)
    calendars = build_session_calendar_records(
        start="2026-03-01",
        end="2026-03-15",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )

    targets = build_target_audit_records(
        normalized,
        calendar_records=calendars,
        roll_days_before_last_trade=5,
    )
    by_date = {str(row["trading_date"]): row for row in targets}
    settle_gap = cast(float, by_date["2026-03-05"]["full_gap_settle_to_open"])

    assert math.isclose(
        settle_gap,
        math.log(50500) - math.log(50000),
    )
    assert by_date["2026-03-06"]["residual_nightclose_to_day_open"] is None
    assert by_date["2026-03-06"]["full_gap_settle_to_open"] is not None
    assert by_date["2026-03-06"]["is_roll_sq_window"] is True
    assert by_date["2026-03-06"]["clean_sample"] is False
    assert "roll_sq_excluded" in str(by_date["2026-03-06"]["missing_reason"])
    assert by_date["2026-03-10"]["same_contract_only"] is False
    assert "cross_contract_excluded" in str(by_date["2026-03-10"]["missing_reason"])


def test_time_alignment_selects_reference_minute_bar_and_checks_dst_regime() -> None:
    target_rows = [
        {
            "trading_date": "2026-01-05",
            "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
            "target_open_ts_jst": datetime(2026, 1, 5, 8, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
        },
        {
            "trading_date": "2026-07-01",
            "target_open_ts_utc": datetime(2026, 6, 30, 23, 45, tzinfo=UTC),
            "target_open_ts_jst": datetime(2026, 7, 1, 8, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
        },
    ]
    calendars = build_session_calendar_records(
        start="2026-01-01",
        end="2026-07-01",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )
    minute_features = [
        _spy_minute("2026-01-02", datetime(2026, 1, 2, 20, 59, tzinfo=UTC), 100.0),
        _spy_minute("2026-01-02", datetime(2026, 1, 2, 21, 0, tzinfo=UTC), 101.0),
        _spy_minute("2026-06-30", datetime(2026, 6, 30, 19, 59, tzinfo=UTC), 200.0),
        _spy_minute("2026-06-30", datetime(2026, 6, 30, 20, 0, tzinfo=UTC), 201.0),
    ]

    alignment = build_time_alignment_records(
        target_rows=target_rows,
        calendar_records=calendars,
        minute_feature_records=minute_features,
    )
    by_target = {str(row["trading_date"]): row for row in alignment}

    assert by_target["2026-01-05"]["dst_regime"] == "EST"
    assert by_target["2026-01-05"]["us_close_to_ose_night_close_minutes"] == 0
    assert by_target["2026-01-05"]["alignment_pass"] is True
    assert by_target["2026-07-01"]["dst_regime"] == "EDT"
    assert by_target["2026-07-01"]["us_close_to_ose_night_close_minutes"] == 60
    assert by_target["2026-07-01"]["alignment_pass"] is True
    assert by_target["2026-07-01"]["minute_reference_ticker"] == "SPY"
    assert by_target["2026-07-01"]["reference_minute_close"] == 201.0
    assert by_target["2026-07-01"]["cutoff_invariant_pass"] is True


def test_time_alignment_reports_missing_us_close_and_reference_bar() -> None:
    target_rows = [
        {
            "trading_date": "2026-01-01",
            "target_open_ts_utc": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            "target_open_ts_jst": datetime(2026, 1, 1, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        },
        {
            "trading_date": "2026-01-05",
            "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
            "target_open_ts_jst": datetime(2026, 1, 5, 8, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
        },
    ]
    calendars = build_session_calendar_records(
        start="2026-01-01",
        end="2026-01-05",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )

    alignment = build_time_alignment_records(
        target_rows=target_rows,
        calendar_records=calendars,
        minute_feature_records=[],
    )

    assert alignment[0]["alignment_status"] == "missing_us_close"
    assert alignment[1]["minute_reference_ticker"] == "SPY"
    assert alignment[1]["reference_bar_selection_reason"] == "missing_regular_session_close_bar"
    assert alignment[1]["selected_reference_bar_end_ts_utc"] is None


def test_time_alignment_treats_us_early_close_as_expected_regime() -> None:
    target_rows = [
        {
            "trading_date": "2026-11-30",
            "target_open_ts_utc": datetime(2026, 11, 29, 23, 45, tzinfo=UTC),
            "target_open_ts_jst": datetime(2026, 11, 30, 8, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
        }
    ]
    calendars = build_session_calendar_records(
        start="2026-11-25",
        end="2026-11-30",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )

    alignment = build_time_alignment_records(
        target_rows=target_rows,
        calendar_records=calendars,
        minute_feature_records=[],
    )

    assert alignment[0]["is_us_early_close"] is True
    assert alignment[0]["us_close_to_ose_night_close_minutes"] == 180
    assert alignment[0]["alignment_pass"] is True
    assert alignment[0]["alignment_reason"] == "est_early_close_expected_180_plus_minus_5"


def test_target_audit_missing_open_and_oi_anomaly_are_reported() -> None:
    downloaded = datetime(2026, 1, 7, tzinfo=UTC)
    raw_rows = [
        _raw_row("2026-01-05", "2026-03", "161030018", settle=50000),
        _raw_row("2026-01-06", "2026-03", "161030018", ao=0),
        {**_raw_row("2026-01-07", "2026-03", "161030018"), "OI": 0, "LTD": "", "SQD": ""},
    ]
    normalized = normalize_jquants_futures_rows(raw_rows, downloaded_at_utc=downloaded)
    calendars = build_session_calendar_records(
        start="2026-01-01",
        end="2026-01-10",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )

    targets = build_target_audit_records(
        normalized,
        calendar_records=calendars,
        roll_days_before_last_trade=5,
    )
    by_date = {str(row["trading_date"]): row for row in targets}

    assert "holiday_trading_no_day_open" in str(by_date["2026-01-06"]["missing_reason"])
    assert by_date["2026-01-07"]["volume_oi_anomaly"] == "open_interest_zero"


def test_parquet_round_trip_preserves_timezone_datetimes(tmp_path: Path) -> None:
    records = normalize_jquants_futures_rows(
        [_raw_row("2026-01-05", "2026-03", "161030018")],
        downloaded_at_utc=datetime(2026, 1, 6, tzinfo=UTC),
    )
    path = tmp_path / "target_audit.parquet"
    pl.DataFrame(records).write_parquet(path)

    frame = pl.read_parquet(path)

    assert "UTC" in str(frame.schema["target_open_ts_utc"])
    assert frame.select("day_session_open").item() == 50800.0


def test_snapshot_summary_can_be_written_from_generated_artifact_text(tmp_path: Path) -> None:
    path = tmp_path / "probe.json"
    path.write_text(
        json.dumps(build_jquants_schema_probe([_raw_row("2026-01-05", "2026-03", "161030018")])),
        encoding="utf-8",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fail_closed"] is False


def test_results_snapshot_uses_full_run_gold_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = "tailrisk_test"
    reports_dir = tmp_path / "reports"
    gold_dir = tmp_path / "data" / "gold"
    run_dir = reports_dir / "runs" / run_id
    panel_dir = gold_dir / "tp" / run_id
    leakage_dir = gold_dir / "ls" / run_id
    metrics_dir = run_dir / "metrics"
    panel_dir.mkdir(parents=True)
    leakage_dir.mkdir(parents=True)
    metrics_dir.mkdir(parents=True)

    panel_path = panel_dir / "modeling_panel.parquet"
    target_path = panel_dir / "target_audit.parquet"
    calendar_path = panel_dir / "calendar_map.parquet"
    feature_path = panel_dir / "feature_coverage.parquet"
    pl.DataFrame(
        [
            {
                "forecast_date": "2018-06-20",
                "forecast_sample": True,
                "target_clean_sample": True,
                "forecast_sample_reason": None,
                "mapping_status": "normal_trading",
            },
            {
                "forecast_date": "2018-06-21",
                "forecast_sample": False,
                "target_clean_sample": False,
                "forecast_sample_reason": "target_not_clean",
                "mapping_status": "normal_trading",
            },
        ]
    ).write_parquet(panel_path)
    pl.DataFrame(
        [
            {"clean_sample": True, "missing_reason": None},
            {"clean_sample": False, "missing_reason": "roll_sq_excluded"},
        ]
    ).write_parquet(target_path)
    pl.DataFrame(
        [
            {
                "mapping_status": "normal_trading",
                "dst_regime": "EDT",
                "us_early_close_flag": False,
            }
        ]
    ).write_parquet(calendar_path)
    pl.DataFrame(
        [
            {
                "source_family": "massive_daily",
                "source_block": "us_core",
                "missingness_rate": 0.0,
            }
        ]
    ).write_parquet(feature_path)
    metric_row = {
        "model_name": "lightgbm_direct_quantile",
        "information_set": "japan_only",
        "rows": 1,
        "var_breach_rate": 0.0,
        "expected_breach_rate": 0.05,
        "exceedance_count": 0,
        "mean_quantile_loss": 0.1,
        "mean_fz_loss": -1.0,
    }
    pl.DataFrame([metric_row]).write_parquet(metrics_dir / "benchmark_metrics.parquet")
    pl.DataFrame([metric_row]).write_parquet(metrics_dir / "ml_tail_metrics.parquet")
    pl.DataFrame([metric_row]).write_parquet(metrics_dir / "ml_tail_metrics_per_model.parquet")
    pl.DataFrame(
        [
            {
                "comparison_family": "tail_model_family",
                "comparison_axis": "model_family",
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": "var_quantile_loss",
                "common_n": 154,
                "date_start": "2025-08-01",
                "date_end": "2026-04-28",
                "joint_exception_count": 17,
            }
        ]
    ).write_parquet(metrics_dir / "ml_tail_result_matrix.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "claim_level": "research_candidate",
                "window": ["2016-07-19", "2026-04-29"],
                "combined_clean_start": "2018-06-20",
                "git_commit": "abcdef123",
                "git_dirty": False,
                "benchmark_eval_status": "completed",
                "ml_tail_eval_status": "completed_lightgbm_ml_tail_models",
                "gold_artifacts": {
                    "modeling_panel": str(panel_path),
                    "target_audit": str(target_path),
                    "calendar_map": str(calendar_path),
                    "feature_coverage": str(feature_path),
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "data_vintage.json").write_text(
        json.dumps({"fred_vintage_safe": False}),
        encoding="utf-8",
    )
    (metrics_dir / "benchmark_status.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "forecast_rows": 1,
                "metric_rows": 1,
                "failures": 0,
                "benchmark_floor_status": "completed",
                "benchmark_floor_forecast_rows": 1,
                "benchmark_floor_metric_rows": 1,
                "benchmark_floor_failures": 0,
                "benchmark_advanced_status": "completed_nonblocking",
                "benchmark_advanced_forecast_rows": 0,
                "benchmark_advanced_diagnostic_rows": 2,
                "benchmark_advanced_failures": 0,
            }
        ),
        encoding="utf-8",
    )
    (metrics_dir / "ml_tail_status.json").write_text(
        json.dumps(
            {
                "status": "completed_lightgbm_ml_tail_models",
                "implemented_components": ["lightgbm_direct_quantile"],
                "forecast_rows": 1,
                "failures": 0,
            }
        ),
        encoding="utf-8",
    )
    (leakage_dir / "summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "rows": 10,
                "failures": 0,
                "warnings": 0,
                "panel_row_count": 2,
                "panel_signature_hash_seed": 42,
                "panel_signature": "abc",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "latex").mkdir(parents=True)
    (run_dir / "latex" / "table_manifest.json").write_text(
        json.dumps(
            {
                "table_count": 1,
                "tables": [
                    {
                        "name": "ml_tail_metrics",
                        "path": "latex/tables/ml_tail_metrics_table.tex",
                        "format": "tex",
                        "source_artifacts": ["metrics/ml_tail_metrics.parquet"],
                        "tail_side": None,
                        "caption": "ML-tail headline nested-information-set table.",
                        "claim_scope": "ml_tail_nested_information_set_table",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "latex" / "figure_manifest.json").write_text(
        json.dumps(
            {
                "figures": [
                    {
                        "name": "dst_attenuation_left_tail",
                        "path": "latex/figures/dst_attenuation_left_tail.png",
                        "format": "png",
                        "source_artifacts": ["metrics/ml_tail_dst_attenuation.parquet"],
                        "tail_side": "left_tail",
                        "caption": (
                            "DST attenuation diagnostic for left_tail; bars report registered "
                            "forecast-loss gain summaries by timing regime. This is descriptive "
                            "forecast evidence, not structural causal identification."
                        ),
                        "claim_scope": (
                            "descriptive_dst_attenuation_not_structural_causal_identification"
                        ),
                    },
                    {
                        "name": "dst_attenuation_left_tail",
                        "path": "latex/figures/dst_attenuation_left_tail.pdf",
                        "format": "pdf",
                        "source_artifacts": ["metrics/ml_tail_dst_attenuation.parquet"],
                        "tail_side": "left_tail",
                        "caption": (
                            "DST attenuation diagnostic for left_tail; bars report registered "
                            "forecast-loss gain summaries by timing regime. This is descriptive "
                            "forecast evidence, not structural causal identification."
                        ),
                        "claim_scope": (
                            "descriptive_dst_attenuation_not_structural_causal_identification"
                        ),
                    },
                    {
                        "name": "trigger_diagnostics_right_tail",
                        "path": "latex/figures/trigger_diagnostics_right_tail.png",
                        "format": "png",
                        "source_artifacts": ["forecasts/benchmark_forecasts.parquet"],
                        "tail_side": "right_tail",
                        "caption": (
                            "VaR trigger diagnostic for right_tail; this is not hedge PnL, "
                            "not transaction-cost evidence, and not trading-alpha evidence."
                        ),
                        "claim_scope": "trigger_diagnostic_not_pnl_cost_or_alpha",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = snapshot_module.write_results_snapshot_from_run(
        settings=Settings(
            data_dir=tmp_path / "data",
            bronze_data_dir=tmp_path / "data" / "bronze",
            silver_data_dir=tmp_path / "data" / "silver",
            gold_data_dir=gold_dir,
            reports_dir=reports_dir,
        ),
        run_id="latest",
    )

    rendered = Path("docs/results_snapshot.md").read_text(encoding="utf-8")
    discussion_rendered = Path("docs/discussion_qa.md").read_text(encoding="utf-8")
    assert result.snapshot_id == run_id
    assert "Discussion Q&A](discussion_qa.md)" in rendered
    assert "### What is the empirical question?" not in rendered
    assert "# Discussion Q&A" in discussion_rendered
    _assert_discussion_qa_headings_in_order(discussion_rendered)
    assert "## Introduction" in rendered
    assert "## Materials: Data And Target" in rendered
    assert "## Methods: Model Configuration And Evaluation" in rendered
    assert "### Target Distribution And Tail Diagnostics" in rendered
    assert "Target-distribution diagnostics are unavailable" in rendered
    assert "## Results And Discussion" in rendered
    assert "<!-- generated: results_discussion -->" in rendered
    _assert_results_discussion_subsections_in_order(rendered)
    assert "#### CPA as conditional loss-difference diagnostics" in rendered
    assert "Figure: dst_attenuation_left_tail" in rendered
    assert "Source: metrics/ml_tail_dst_attenuation.parquet" in rendered
    assert (
        "Claim scope: descriptive_dst_attenuation_not_structural_causal_identification" in rendered
    )
    assert "File: latex/figures/dst_attenuation_left_tail.png" in rendered
    assert "Gold modeling rows" in rendered
    assert "JP only" in rendered
    assert "### Run Metadata" in rendered
    assert "### Evidence Map" in rendered
    assert "## Appendix: Tables, Figures, And Run Artifacts" in rendered
    assert "### Paper-Facing Table And Figure Gallery" in rendered
    assert "#### Table Manifest" in rendered
    assert "ml_tail_nested_information_set_table" in rendered
    assert "![dst_attenuation_left_tail]" in rendered
    assert "figures/tailrisk_test/dst_attenuation_left_tail.png" in rendered
    assert "older" in rendered
    assert "bounded access-check snapshot" in rendered
    assert "Coverage review:" in rendered
    assert "must not be read as forecast improvement" in rendered
    assert "on average across the unconditional evaluation sample" in rendered


def test_target_tail_diagnostics_markdown_reports_raw_target_boundary() -> None:
    rows = []
    for idx in range(220):
        base = 0.006 * math.sin(idx / 7)
        if idx % 53 == 0:
            base -= 0.035
        if idx % 67 == 0:
            base += 0.042
        rows.append(
            {
                "forecast_date": f"2025-01-{(idx % 28) + 1:02d}",
                "clean_sample": True,
                "forecast_sample": True,
                "gap_t": base,
                "residual_nightclose_to_day_open": base / 2,
            }
        )
    panel = pl.DataFrame(rows)
    manifest: dict[str, object] = {
        "figures": [
            {
                "name": "target_gap_histogram_density",
                "path": "latex/figures/target_gap_histogram_density.png",
                "format": "png",
                "source_artifacts": ["panel/modeling_panel.parquet"],
                "tail_side": "target_distribution",
                "claim_scope": "target_distribution_motivation_not_forecast_validation",
            }
        ]
    }

    rendered = target_distribution_module.target_tail_diagnostics_markdown(
        panel=panel,
        figure_manifest=manifest,
        run_id="tailrisk_test",
    )

    assert "## Target Distribution And Tail Diagnostics" in rendered
    assert "Clean forecast observations" in rendered
    assert "Excess kurtosis" in rendered
    assert "GPD xi" in rendered
    assert "Hill xi" in rendered
    assert "target_gap_histogram_density" in rendered
    assert "panel/modeling_panel.parquet" in rendered
    assert "not validate LightGBM+EVT forecasts" in rendered
    assert "not a finite-sample proof of Frechet" in rendered
    scale_text = target_distribution_module.opening_gap_scale_text(panel)
    assert "largest absolute clean settle-to-open gap" in scale_text
    assert "night-close-to-open residual" in scale_text
    assert "modeling panel is missing `gap_t`" in target_distribution_module.opening_gap_scale_text(
        pl.DataFrame()
    )


def test_target_tail_diagnostics_markdown_handles_empty_inputs() -> None:
    empty_rendered = target_distribution_module.target_tail_diagnostics_markdown(
        panel=pl.DataFrame({"other": [1.0]}),
        figure_manifest={"figures": []},
        run_id="tailrisk_test",
    )
    assert "Target-distribution diagnostics are unavailable" in empty_rendered
    assert "does not change any forecast-evaluation claim" in empty_rendered

    no_clean = pl.DataFrame({"gap_t": [None], "clean_sample": [True]})
    assert "no clean target rows" in target_distribution_module.opening_gap_scale_text(no_clean)


def test_target_distribution_helpers_report_manifest_fallbacks() -> None:
    assert "not available" in target_distribution_module._target_distribution_figure_table(
        figure_manifest={"figures": "not-a-list"},
        run_id="tailrisk_test",
    )
    assert "not available" in target_distribution_module._target_distribution_figure_table(
        figure_manifest={"figures": [{"name": "coverage_breach_rates_left_tail"}]},
        run_id="tailrisk_test",
    )
    rendered = target_distribution_module._target_distribution_figure_table(
        figure_manifest={
            "figures": [
                "bad-row",
                {
                    "name": "target_custom",
                    "path": "latex/figures/target_custom.png",
                    "tail_side": "target_distribution",
                    "claim_scope": "diagnostic|with_pipe",
                },
                {
                    "name": "target_custom",
                    "path": "latex/figures/target_custom.pdf",
                    "tail_side": "target_distribution",
                    "source_artifacts": ["panel/modeling_panel.parquet"],
                },
            ]
        },
        run_id="tailrisk_test",
    )
    assert "target_custom" in rendered
    assert "`missing`" in rendered
    assert "diagnostic\\|with_pipe" in rendered
    assert "figures/tailrisk_test/target_custom.png" in rendered

    assert target_distribution_module._fmt_log_return("not-a-number") == "missing"
    assert target_distribution_module._fmt_float(True) == "True"
    assert target_distribution_module._optional_float(float("nan")) is None


def _assert_discussion_qa_headings_in_order(rendered: str) -> None:
    headings = [
        "## What is the paper asking?",
        "## What is the target?",
        "## Why is the OSE open worth studying?",
        "## What data enter the forecasts?",
        "## What models are compared?",
        "## How do the LightGBM+EVT variants work?",
        "## How are forecasts judged?",
        "## What do the current results say?",
        "## What can the paper claim?",
    ]
    positions = [rendered.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "conditional loss-difference diagnostic" in rendered
    assert "The final VaR/ES level is 95%" in rendered
    assert "it is not the reported VaR level" in rendered
    assert "advanced benchmark layer is registered as nonblocking" in rendered
    assert "should be read as unavailable diagnostics" in rendered
    assert "Smoke-only artifact" not in rendered
    assert ("Giacomini" + "-White") not in rendered
    assert ("G" + "W") not in rendered
    _assert_no_forbidden_promotional_terms(rendered)


def test_results_discussion_coverage_sentence_uses_test_fields() -> None:
    frame = pl.DataFrame(
        [
            {
                "var_breach_rate": 0.08,
                "expected_breach_rate": 0.05,
                "kupiec_pvalue": 0.01,
                "christoffersen_pvalue": 0.20,
            },
            {
                "var_breach_rate": 0.051,
                "expected_breach_rate": 0.05,
                "kupiec_pvalue": 0.50,
                "christoffersen_pvalue": 0.03,
            },
        ]
    )

    sentence = results_discussion_module._coverage_test_discussion_sentence(frame)
    missing = results_discussion_module._coverage_test_discussion_sentence(pl.DataFrame())

    assert "Coverage review flags `1/2`" in sentence
    assert "Kupiec p-values fall below 0.05 in `1/2`" in sentence
    assert "Christoffersen p-values fall below 0.05 in `1/2`" in sentence
    assert "Coverage review is descriptive" in missing


def test_results_discussion_private_helpers_cover_fallbacks(tmp_path: Path) -> None:
    panel = pl.DataFrame(
        [
            {"forecast_date": "2018-01-01", "forecast_sample": True},
            {"forecast_date": "2018-06-20", "forecast_sample": True},
        ]
    )
    audit = results_discussion_module._results_data_timing_audit(
        manifest={"combined_clean_start": "2018-06-20"},
        data_vintage={"fred_vintage_safe": False},
        leakage_summary={"status": "fail", "failures": 2, "warnings": 1},
        panel=panel,
        calendar=pl.DataFrame([{"target_open_ts_utc": datetime(2020, 1, 1, tzinfo=UTC)}]),
    )
    assert "require review" in audit
    assert "2` failures" in audit
    assert results_discussion_module._date_range_from_calendar(pl.DataFrame()) is None
    assert (
        results_discussion_module._forecast_rows_before_combined_clean_start(
            pl.DataFrame(),
            "2018-06-20",
        )
        is None
    )
    assert "not available" in results_discussion_module._leakage_discussion_sentence({})

    assert "not yet been performed" in results_discussion_module._results_benchmark_discussion(
        benchmark_status={},
        benchmark_metrics=pl.DataFrame(),
        benchmark_forecasts=pl.DataFrame(),
    )
    no_advanced = results_discussion_module._results_benchmark_discussion(
        benchmark_status={"forecast_rows": 2},
        benchmark_metrics=pl.DataFrame([{"model_name": "hist"}]),
        benchmark_forecasts=pl.DataFrame([{"benchmark_tier": "floor", "model_name": "hist"}]),
    )
    assert "does not provide advanced forecast rows" in no_advanced
    assert (
        "not yet been performed"
        in results_discussion_module._results_ml_tail_headline_discussion(
            ml_tail_status={},
            ml_tail_metrics=pl.DataFrame(),
        )
    )
    assert (
        "not yet been performed"
        in results_discussion_module._results_restricted_model_family_discussion(
            result_matrix=pl.DataFrame(),
            result_matrix_dm=pl.DataFrame(),
            result_matrix_mcs=pl.DataFrame(),
        )
    )
    assert results_discussion_module._int_range(pl.DataFrame(), "common_n") == "not available"
    assert (
        results_discussion_module._int_range(pl.DataFrame([{"common_n": None}]), "common_n")
        == "not available"
    )
    assert (
        results_discussion_module._int_range(pl.DataFrame([{"common_n": 154}]), "common_n") == "154"
    )

    assert (
        "valid coverage rows are not available"
        in results_discussion_module._coverage_test_discussion_sentence(
            pl.DataFrame([{"var_breach_rate": None, "expected_breach_rate": None}])
        )
    )
    assert "not available" in results_discussion_module._eviction_discussion_sentence(
        pl.DataFrame()
    )
    assert "do not expose" in results_discussion_module._eviction_discussion_sentence(
        pl.DataFrame([{"model_name": "m"}])
    )
    assert "1` retained" in results_discussion_module._eviction_discussion_sentence(
        pl.DataFrame(
            [
                {"retained_for_headline": True},
                {"retained_for_headline": False},
            ]
        )
    )
    assert "not available" in results_discussion_module._tail_event_power_sentence(
        pl.DataFrame(),
        (),
    )
    gate_sentence = results_discussion_module._tail_event_power_sentence(
        pl.DataFrame([{"tail_event_power_status": "insufficient_tail_events_for_inference"}]),
        (pl.DataFrame([{"inference_status": "unavailable_insufficient_tail_events"}]),),
    )
    assert "1` restricted rows" in gate_sentence
    assert "1/1` unavailable" in gate_sentence
    result_matrix_inference = results_discussion_module._result_matrix_inference_sentence(
        result_matrix_dm=pl.DataFrame(
            [
                {"inference_status": "ok_block_bootstrap_dm"},
                {"inference_status": "unavailable_descriptive_coverage_metric"},
            ]
        ),
        result_matrix_mcs=pl.DataFrame([{"mcs_status": "unavailable_insufficient_common_rows"}]),
    )
    assert result_matrix_inference is not None
    assert (
        "restricted DM records include `1` gate-pass rows and `1` unavailable rows"
        in result_matrix_inference
    )
    assert (
        "restricted MCS records include `0` gate-pass rows and `1` unavailable rows"
        in result_matrix_inference
    )

    paths = {
        "dst_attenuation_table": tmp_path / "dst.tex",
        "es_severity_table": tmp_path / "severity.tex",
        "hedge_trigger_table": tmp_path / "trigger.tex",
        "result_matrix_summary_table": tmp_path / "summary.tex",
    }
    assert "not yet been exported" in results_discussion_module._diagnostic_table_sentence(paths)
    paths["dst_attenuation_table"].write_text("x", encoding="utf-8")
    assert "1/4" in results_discussion_module._diagnostic_table_sentence(paths)

    assert "not yet been performed" in results_discussion_module._severity_discussion_sentence(
        benchmark_metrics=pl.DataFrame(),
        ml_tail_metrics=pl.DataFrame(),
        ml_tail_metrics_per_model=pl.DataFrame(),
    )
    assert "not available" in results_discussion_module._severity_discussion_sentence(
        benchmark_metrics=pl.DataFrame([{"model_name": "m"}]),
        ml_tail_metrics=pl.DataFrame(),
        ml_tail_metrics_per_model=pl.DataFrame(),
    )
    assert "no finite" in results_discussion_module._severity_discussion_sentence(
        benchmark_metrics=pl.DataFrame([{"mean_exceedance_severity": None}]),
        ml_tail_metrics=pl.DataFrame(),
        ml_tail_metrics_per_model=pl.DataFrame(),
    )

    combined = results_discussion_module._combine_forecasts_for_snapshot(
        benchmark_forecasts=pl.DataFrame([{"model_name": "hist"}]),
        ml_tail_forecasts=pl.DataFrame([{"model_name": "lgbm"}]),
    )
    assert combined.height == 2
    assert set(combined["suite"].to_list()) == {"benchmark", "ml_tail"}
    assert results_discussion_module._combine_forecasts_for_snapshot(
        benchmark_forecasts=pl.DataFrame(),
        ml_tail_forecasts=pl.DataFrame(),
    ).is_empty()

    assert "not yet been performed" in results_discussion_module._trigger_discussion_sentence(
        pl.DataFrame()
    )
    assert "no valid forecast rows" in results_discussion_module._trigger_discussion_sentence(
        pl.DataFrame(
            [
                {
                    "model_name": "m",
                    "information_set": "i",
                    "tail_level": 0.95,
                    "var_forecast": None,
                    "realized_loss": None,
                    "is_valid_forecast": True,
                }
            ]
        )
    )
    trigger_text = results_discussion_module._trigger_discussion_sentence(
        pl.DataFrame(
            [
                {
                    "suite": "ml_tail",
                    "model_name": "m",
                    "information_set": "i",
                    "tail_level": 0.95,
                    "var_forecast": 1.0,
                    "realized_loss": 0.8,
                    "is_valid_forecast": True,
                },
                {
                    "suite": "ml_tail",
                    "model_name": "m",
                    "information_set": "i",
                    "tail_level": 0.95,
                    "var_forecast": 2.0,
                    "realized_loss": 2.5,
                    "is_valid_forecast": True,
                },
            ]
        )
    )
    assert "marks `1` model-date rows" in trigger_text
    assert "mean triggered exception severity is `0.5`" in trigger_text


def test_snapshot_private_helpers_cover_defensive_edges() -> None:
    assert snapshot_module._optional_float(True) is None
    assert snapshot_module._optional_float("1.5") == 1.5
    assert snapshot_module._markdown_cell("a|b\nc") == "a\\|b c"
    all_model_table = model_comparison_module._all_model_comparison_table(
        benchmark_metrics=pl.DataFrame(
            [
                {
                    "model_name": "historical_quantile",
                    "information_set": "target_history_only",
                    "rows": 100,
                    "var_breach_rate": 0.05,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.001,
                    "mean_fz_loss": -3.0,
                    "mean_exceedance_severity": 0.01,
                    "tail_side": "left_tail",
                }
            ]
        ),
        benchmark_metrics_per_model=pl.DataFrame(),
        ml_tail_metrics_per_model=pl.DataFrame(
            [
                {
                    "model_name": "lightgbm_standardized_loss_pot_gpd_plain_mle",
                    "information_set": "japan_only",
                    "rows": 80,
                    "var_breach_rate": 0.075,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.0009,
                    "mean_fz_loss": -3.2,
                    "mean_exceedance_severity": 0.02,
                    "tail_side": "right_tail",
                }
            ]
        ),
    )
    assert "benchmark_floor" in all_model_table
    assert "LGBM POT-GPD plain MLE" in all_model_table
    assert "JP only" in all_model_table
    assert "japan_only" not in all_model_table
    assert "Breach mean+-sd" in all_model_table
    assert results_discussion_module._optional_float("bad") is None
    assert results_discussion_module._fmt_float(float("inf")) == "inf"


def test_results_discussion_manuscript_audit_helpers_cover_branches(tmp_path: Path) -> None:
    cpa_text = results_discussion_module._results_cpa_discussion(
        pl.DataFrame(
            [
                {
                    "tail_side": "left_tail",
                    "loss_family": "var_quantile_loss",
                    "inference_status": "ok_newey_west_hac_wald_cpa",
                }
            ]
        ),
        pl.DataFrame(
            [
                {
                    "loss_family": "var_es_fz_loss",
                    "inference_status": "ok_newey_west_hac_wald_cpa",
                }
            ]
        ),
    )
    assert "conditional loss-difference diagnostic" in cpa_text
    assert "1` HAC-Wald gate pass" in cpa_text

    missing_panel_audit = results_discussion_module._results_data_timing_audit(
        manifest={"combined_clean_start": "2018-06-20"},
        data_vintage={"fred_vintage_safe": False},
        leakage_summary={"status": "pass", "failures": 0, "warnings": 0},
        panel=pl.DataFrame([{"forecast_date": "2018-06-20"}]),
        calendar=pl.DataFrame(),
    )
    assert "could not verify pre-start forecast rows" in missing_panel_audit

    calibrated = results_discussion_module._results_benchmark_discussion(
        benchmark_status={"forecast_rows": 2, "benchmark_advanced_forecast_rows": 1},
        benchmark_metrics=pl.DataFrame(
            [
                {"model_name": "a", "tail_side": "left_tail", "var_breach_rate": 0.05},
                {"model_name": "b", "tail_side": "right_tail", "var_breach_rate": 0.06},
            ]
        ),
        benchmark_forecasts=pl.DataFrame(
            [
                {"benchmark_tier": "floor", "model_name": "a"},
                {"benchmark_tier": "advanced", "model_name": "c"},
            ]
        ),
    )
    assert "reasonable coverage calibration" in calibrated

    headline = results_discussion_module._results_ml_tail_headline_discussion(
        ml_tail_status={"implemented_components": ["lightgbm_direct_quantile"]},
        ml_tail_metrics=pl.DataFrame(
            [
                {
                    "model_name": "lightgbm_direct_quantile",
                    "information_set": "japan_only",
                    "tail_side": "left_tail",
                    "tail_level": 0.95,
                    "var_breach_rate": 0.095,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.0020,
                },
                {
                    "model_name": "lightgbm_direct_quantile",
                    "information_set": "japan_only_plus_us_close_core",
                    "tail_side": "left_tail",
                    "tail_level": 0.95,
                    "var_breach_rate": 0.10,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.0010,
                },
                {
                    "model_name": "lightgbm_direct_quantile",
                    "information_set": "japan_only_plus_us_close_core_plus_japan_proxy",
                    "tail_side": "left_tail",
                    "tail_level": 0.95,
                    "var_breach_rate": 0.11,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.0009,
                },
                {
                    "model_name": "lightgbm_direct_quantile",
                    "information_set": (
                        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy"
                    ),
                    "tail_side": "left_tail",
                    "tail_level": 0.95,
                    "var_breach_rate": 0.12,
                    "expected_breach_rate": 0.05,
                    "mean_quantile_loss": 0.00085,
                },
            ]
        ),
    )
    assert "Coverage warning" in headline
    assert "largest quantile-loss change" in headline

    restricted = results_discussion_module._results_restricted_model_family_discussion(
        result_matrix=pl.DataFrame(
            [
                {
                    "comparison_family": "tail_model_family",
                    "model_name": "lightgbm_location_scale",
                    "common_n": 154,
                    "joint_exception_count": 17,
                    "claim_scope": "restricted_model_comparison_not_headline",
                }
            ]
        ),
        result_matrix_dm=pl.DataFrame([{"inference_status": "ok_block_bootstrap_dm"}]),
        result_matrix_mcs=pl.DataFrame([{"mcs_status": "unavailable_insufficient_common_rows"}]),
    )
    assert "severely sample-limited" in restricted
    assert "restricted DM records include `1` gate-pass rows" in restricted

    assert (
        results_discussion_module._result_matrix_inference_sentence(
            result_matrix_dm=pl.DataFrame([{"status": "missing_owner_column"}]),
            result_matrix_mcs=pl.DataFrame(),
        )
        is None
    )
    assert "do not include PNG" in results_discussion_module._figure_reference_discussion(
        {"figures": [{"name": "x", "format": "pdf"}]}
    )
    assert "not recorded" in results_discussion_module._figure_reference_discussion(
        {"figures": ["bad", {"name": "x", "format": "png", "path": "x.png"}]}
    )
    assert "not available" in results_discussion_module._tail_event_power_sentence(
        pl.DataFrame(),
        (pl.DataFrame([{"status": "no_status_column"}]),),
    )

    severity = results_discussion_module._severity_discussion_sentence(
        benchmark_metrics=pl.DataFrame([{"mean_exceedance_severity": 0.01}]),
        ml_tail_metrics=pl.DataFrame([{"mean_exceedance_severity": 0.02}]),
        ml_tail_metrics_per_model=pl.DataFrame([{"mean_exceedance_severity": 0.03}]),
    )
    assert "3` finite rows" in severity

    trigger = results_discussion_module._trigger_discussion_sentence(
        pl.DataFrame(
            [
                {
                    "suite": "ml_tail",
                    "tail_side": "left_tail",
                    "model_name": "m",
                    "information_set": "i",
                    "tail_level": 0.95,
                    "var_forecast": 1.0,
                    "realized_loss": 0.9,
                    "is_valid_forecast": True,
                },
                {
                    "suite": "ml_tail",
                    "tail_side": "right_tail",
                    "model_name": "m",
                    "information_set": "i",
                    "tail_level": 0.95,
                    "var_forecast": 1.0,
                    "realized_loss": 1.2,
                    "is_valid_forecast": True,
                },
            ]
        )
    )
    assert "marks `2` model-date rows" in trigger

    assert results_discussion_module._benchmark_calibration_note(pl.DataFrame()) is None
    assert (
        results_discussion_module._benchmark_calibration_note(
            pl.DataFrame([{"var_breach_rate": 0.20}])
        )
        is None
    )
    assert (
        results_discussion_module._ml_tail_coverage_warning(
            pl.DataFrame([{"var_breach_rate": 0.05, "expected_breach_rate": 0.05}])
        )
        is None
    )
    assert (
        results_discussion_module._information_set_saturation_note(
            pl.DataFrame([{"mean_quantile_loss": 1.0}])
        )
        is None
    )
    assert results_discussion_module._restricted_short_sample_warning(pl.DataFrame()) is None
    assert (
        results_discussion_module._restricted_short_sample_warning(
            pl.DataFrame([{"comparison_family": "information_set_ladder", "common_n": 660}])
        )
        is None
    )
    assert (
        results_discussion_module._restricted_short_sample_warning(
            pl.DataFrame([{"comparison_family": "tail_model_family", "common_n": 660}])
        )
        is None
    )
    assert results_discussion_module._read_parquet_optional(tmp_path / "missing.parquet").is_empty()


def test_snapshot_gallery_helpers_cover_manifest_edges(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "tailrisk_gallery"
    figure_dir = run_dir / "latex" / "figures"
    figure_dir.mkdir(parents=True)
    target_source = figure_dir / "target_gap_histogram_density.png"
    target_source.write_bytes(b"png")
    source = figure_dir / "coverage_breach_rates_left_tail.png"
    source.write_bytes(b"png")
    stale_docs = tmp_path / "docs" / "figures" / run_dir.name / "stale.png"
    stale_docs.parent.mkdir(parents=True)
    stale_docs.write_bytes(b"old")
    manifest: dict[str, object] = {
        "figures": [
            "bad",
            {"name": "no_path", "format": "png"},
            {
                "name": "target_gap_histogram_density",
                "path": "latex/figures/target_gap_histogram_density.png",
                "format": "png",
                "source_artifacts": ["panel/modeling_panel.parquet"],
                "tail_side": "target_distribution",
                "claim_scope": "target_distribution_motivation_not_forecast_validation",
            },
            {
                "name": "coverage_breach_rates_left_tail",
                "path": "latex/figures/coverage_breach_rates_left_tail.png",
                "format": "png",
                "source_artifacts": ["metrics/ml_tail_metrics.parquet"],
                "tail_side": "left_tail",
                "claim_scope": "coverage_diagnostic_not_headline_claim",
            },
            {
                "name": "coverage_breach_rates_left_tail",
                "path": "latex/figures/coverage_breach_rates_left_tail.pdf",
                "format": "pdf",
                "source_artifacts": ["metrics/ml_tail_metrics.parquet"],
                "tail_side": "left_tail",
                "claim_scope": "coverage_diagnostic_not_headline_claim",
            },
            {
                "name": "unknown_plot_left_tail",
                "path": "latex/figures/missing.png",
                "format": "png",
                "source_artifacts": [],
                "tail_side": "left_tail",
                "claim_scope": None,
            },
        ]
    }

    snapshot_gallery.sync_snapshot_figure_assets(
        run_dir=run_dir,
        figure_manifest={},
        docs_dir=tmp_path / "docs",
    )
    snapshot_gallery.sync_snapshot_figure_assets(
        run_dir=run_dir,
        figure_manifest=manifest,
        docs_dir=tmp_path / "docs",
    )

    copied = tmp_path / "docs" / "figures" / run_dir.name / source.name
    assert copied.exists()
    assert not stale_docs.exists()
    assert "flowchart LR" in snapshot_gallery.evidence_map_mermaid()
    assert "table_manifest_not_available" in snapshot_gallery.table_manifest_markdown({})
    assert "table_manifest_not_available" in snapshot_gallery.table_manifest_markdown(
        {"tables": ["bad"]}
    )
    assert "ml_tail_metrics.parquet" in snapshot_gallery.table_manifest_markdown(
        {
            "tables": [
                {
                    "name": "ml_tail_metrics",
                    "source_artifacts": ["metrics/ml_tail_metrics.parquet"],
                    "claim_scope": "ml_tail_nested_information_set_table",
                    "tail_side": None,
                    "path": "latex/tables/ml_tail_metrics_table.tex",
                }
            ]
        }
    )
    gallery = snapshot_gallery.figure_gallery_markdown(
        figure_manifest=manifest,
        run_id=run_dir.name,
    )
    assert "Figure 1. Target Distribution And Tail Diagnostics" in gallery
    assert "Figure 2. Coverage Breach-Rate Diagnostics" in gallery
    assert "target_gap_histogram_density.png" in gallery
    assert "coverage_breach_rates_left_tail.png" in gallery
    assert "Figure artifacts are not available" in snapshot_gallery.figure_gallery_markdown(
        figure_manifest={},
        run_id=run_dir.name,
    )
    assert snapshot_gallery._figure_family("target_gap_histogram_density") == "target_distribution"
    assert snapshot_gallery._figure_family("benchmark_murphy_left_tail") == "benchmark_murphy"
    assert snapshot_gallery._figure_family("ml_tail_murphy_left_tail") == "ml_tail_murphy"
    assert snapshot_gallery._figure_family("dst_attenuation_left_tail") == "dst"
    assert snapshot_gallery._figure_family("es_severity_left_tail") == "severity"
    assert snapshot_gallery._figure_family("trigger_diagnostics_left_tail") == "trigger"
    assert snapshot_gallery._figure_family("unknown") == "other"
    assert "generated diagnostic figure" in " ".join(snapshot_gallery._figure_key_readings("x"))
    assert "LightGBM+EVT forecasts" in " ".join(
        snapshot_gallery._figure_key_readings("target_distribution")
    )
    assert snapshot_gallery._source_artifacts_text([]) == "`missing`"
    assert snapshot_gallery._markdown_cell("a|b\nc") == "a\\|b c"


def _assert_results_discussion_subsections_in_order(rendered: str) -> None:
    headings = [
        "#### Data and timing audit",
        "#### Benchmark floor and advanced benchmarks",
        "#### Left/right ML-tail nested information sets",
        "#### Restricted model-family comparison",
        "#### Coverage and inference gates",
        "#### CPA as conditional loss-difference diagnostics",
        "#### Supporting diagnostics",
        "#### Not yet claimed",
    ]
    positions = [rendered.index(heading) for heading in headings]
    assert positions == sorted(positions)


def _assert_no_unsupported_affirmative_claims(rendered: str) -> None:
    _assert_no_forbidden_promotional_terms(rendered)

    restricted_disclaimer_terms = (
        "hedge PnL",
        "transaction-cost",
        "trading-alpha",
        "causal identification",
        "causal mechanism",
        "trading signal",
    )
    not_claimed_start = rendered.index("#### Not yet claimed")
    not_claimed_end = rendered.find("\n## ", not_claimed_start + 1)
    not_claimed = (
        rendered[not_claimed_start:]
        if not_claimed_end == -1
        else rendered[not_claimed_start:not_claimed_end]
    )
    approved_disclaimers = (
        "This is a pre-open risk-monitoring diagnostic, not hedge PnL, "
        "transaction-cost, or trading-alpha evidence.",
    )
    allowed_lines = set(not_claimed.splitlines()) | set(approved_disclaimers)
    for line in rendered.splitlines():
        for phrase in restricted_disclaimer_terms:
            if phrase.lower() in line.lower():
                assert line in allowed_lines, line


def _assert_no_forbidden_promotional_terms(rendered: str) -> None:
    forbidden_anywhere = (
        "best",
        "dominates",
        "winner",
        "superior",
        "significantly outperforms",
    )
    for phrase in forbidden_anywhere:
        assert phrase.lower() not in rendered.lower()

    assert re.search(
        r"DM|MCS|unconditional evaluation sample",
        rendered,
        flags=re.IGNORECASE,
    )


def _raw_row(
    trading_date: str,
    contract_month: str,
    code: str,
    *,
    ao: float = 50800,
    ah: float = 51900,
    al: float = 50700,
    ac: float = 51820,
    eo: float = 50450,
    eh: float = 50700,
    el: float = 50300,
    ec: float = 50620,
    settle: float = 51820,
) -> dict[str, object]:
    return {
        "Date": trading_date,
        "ProdCat": "NK225F",
        "Code": code,
        "CM": contract_month,
        "CCMFlag": 1,
        "AO": ao,
        "AH": ah,
        "AL": al,
        "AC": ac,
        "EO": eo,
        "EH": eh,
        "EL": el,
        "EC": ec,
        "Settle": settle,
        "Vo": 47001,
        "OI": 140121,
        "LTD": "2026-03-12",
        "SQD": "2026-03-13",
    }


def _spy_minute(date_et: str, end_ts_utc: datetime, close: float) -> dict[str, object]:
    return {
        "bar_date_et": date_et,
        "bar_end_ts_utc": end_ts_utc,
        "bar_end_ts_et": end_ts_utc.astimezone(ZoneInfo("America/New_York")),
        "is_us_regular_session": True,
        "close": close,
    }
