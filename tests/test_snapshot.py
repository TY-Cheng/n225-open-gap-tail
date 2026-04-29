from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl
import pytest

import n225_open_gap_tail.diagnostics.snapshot as snapshot_module
from n225_open_gap_tail.diagnostics.snapshot import (
    build_jquants_schema_probe,
    build_model_smoke,
    build_predictor_availability_records,
    build_snapshot_id,
    build_target_audit_records,
    build_time_alignment_records,
    normalize_jquants_futures_rows,
)
from n225_open_gap_tail.market.calendars import build_session_calendar_records


def test_build_snapshot_id_binds_window_timestamp_and_commit() -> None:
    snapshot_id = build_snapshot_id(
        start="2022-01-01",
        end="2026-04-28",
        run_ts_utc=datetime(2026, 4, 28, 6, 30, tzinfo=UTC),
        git_commit="abcdef123456",
    )

    assert snapshot_id == "20220101_20260428_20260428T063000Z_commit_abcdef12"


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
        "day_session_close": 0,
        "night_session_open": 0,
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


def test_time_alignment_selects_spy_bar_and_checks_dst_regime() -> None:
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
    spy_minutes = [
        _spy_minute("2026-01-02", datetime(2026, 1, 2, 20, 59, tzinfo=UTC), 100.0),
        _spy_minute("2026-01-02", datetime(2026, 1, 2, 21, 0, tzinfo=UTC), 101.0),
        _spy_minute("2026-06-30", datetime(2026, 6, 30, 19, 59, tzinfo=UTC), 200.0),
        _spy_minute("2026-06-30", datetime(2026, 6, 30, 20, 0, tzinfo=UTC), 201.0),
    ]

    alignment = build_time_alignment_records(
        target_rows=target_rows,
        calendar_records=calendars,
        spy_minute_records=spy_minutes,
    )
    by_target = {str(row["trading_date"]): row for row in alignment}

    assert by_target["2026-01-05"]["dst_regime"] == "EST"
    assert by_target["2026-01-05"]["us_close_to_ose_night_close_minutes"] == 0
    assert by_target["2026-01-05"]["alignment_pass"] is True
    assert by_target["2026-07-01"]["dst_regime"] == "EDT"
    assert by_target["2026-07-01"]["us_close_to_ose_night_close_minutes"] == 60
    assert by_target["2026-07-01"]["alignment_pass"] is True
    assert by_target["2026-07-01"]["spy_close"] == 201.0
    assert by_target["2026-07-01"]["cutoff_invariant_pass"] is True


def test_time_alignment_reports_missing_us_close_and_spy_bar() -> None:
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
        spy_minute_records=[],
    )

    assert alignment[0]["alignment_status"] == "missing_us_close"
    assert alignment[1]["spy_bar_selection_reason"] == "missing_regular_session_close_bar"
    assert alignment[1]["selected_spy_bar_end_ts_utc"] is None


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
        spy_minute_records=[],
    )

    assert alignment[0]["is_us_early_close"] is True
    assert alignment[0]["us_close_to_ose_night_close_minutes"] == 180
    assert alignment[0]["alignment_pass"] is True
    assert alignment[0]["alignment_reason"] == "est_early_close_expected_180_plus_minus_5"


def test_predictor_availability_reports_spearman_and_subsample_guard() -> None:
    targets = [
        {
            "trading_date": f"2026-01-{day:02d}",
            "clean_sample": True,
            "full_gap_settle_to_open": -day / 1000,
            "loss_settle_to_open": day / 1000,
        }
        for day in range(1, 13)
    ]
    alignment = [
        {
            "trading_date": row["trading_date"],
            "us_calendar_date": row["trading_date"],
            "dst_regime": "EST",
        }
        for row in targets
    ]
    massive = [
        {"ticker": "SPY", "bar_date_et": row["trading_date"], "close": 100 + index}
        for index, row in enumerate(targets)
    ]
    massive.append({"ticker": "QQQ", "bar_date_et": "2026-02-01", "close": 1.0})

    records = build_predictor_availability_records(
        target_rows=targets,
        massive_daily_records=massive,
        fred_records=[],
        alignment_records=alignment,
    )
    by_predictor = {str(row["predictor"]): row for row in records}

    assert by_predictor["SPY"]["source"] == "massive_daily"
    assert by_predictor["SPY"]["effective_clean_join_rows"] == 12
    spearman_all = cast(dict[str, object], by_predictor["SPY"]["spearman_all"])
    spearman_edt = cast(dict[str, object], by_predictor["SPY"]["spearman_edt"])
    assert spearman_all["n"] == 12
    assert spearman_edt["reason"] == "insufficient_subsample"
    assert by_predictor["QQQ"]["effective_clean_join_rows"] == 0


def test_model_smoke_gates_evt_by_training_exceedances() -> None:
    small_rows: list[dict[str, object]] = [
        {
            "clean_sample": True,
            "full_gap_settle_to_open": -0.001,
            "loss_settle_to_open": 0.001,
        }
        for _ in range(10)
    ]
    assert build_model_smoke(small_rows)["overall_status"] == "unavailable_insufficient_sample"

    large_rows: list[dict[str, object]] = [
        {
            "clean_sample": True,
            "full_gap_settle_to_open": -value,
            "loss_settle_to_open": value,
        }
        for value in np.linspace(0.001, 0.2, 180)
    ]
    status = build_model_smoke(large_rows)

    assert status["overall_status"] == "smoke_metrics_available"
    assert status["evt_status"] == "unavailable_insufficient_exceedances"
    assert status["lightgbm_status"] in {
        "smoke_metrics_available",
        "unavailable_import_error",
    }


def test_model_smoke_records_train_test_gate_and_evt_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, object]] = [
        {
            "clean_sample": True,
            "full_gap_settle_to_open": -0.001,
            "loss_settle_to_open": 0.001,
        }
        for _ in range(130)
    ]
    monkeypatch.setattr(snapshot_module, "MIN_TEST_ROWS_FOR_METRICS", 40)
    gated = build_model_smoke(rows)
    assert gated["overall_status"] == "unavailable_insufficient_sample"
    assert cast(int, gated["test_rows"]) < 40

    evt_rows: list[dict[str, object]] = [
        {
            "clean_sample": True,
            "full_gap_settle_to_open": -value,
            "loss_settle_to_open": value,
        }
        for value in np.linspace(0.001, 1.0, 900)
    ]
    monkeypatch.setattr(snapshot_module, "MIN_TEST_ROWS_FOR_METRICS", 20)
    fitted = build_model_smoke(evt_rows)
    assert cast(int, fitted["evt_train_exceedances"]) >= 30
    assert fitted["evt_status"] in {"smoke_fit_available", "meaningful_discussion_ready"}


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


def test_private_snapshot_helpers_cover_defensive_edges(tmp_path: Path) -> None:
    assert snapshot_module._month_chunks(start="2026-01-30", end="2026-03-02") == [
        ("2026-01-30", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-02"),
    ]
    assert snapshot_module._date_range(
        datetime(2026, 1, 1).date(),
        datetime(2026, 1, 3).date(),
    ) == [
        datetime(2026, 1, 1).date(),
        datetime(2026, 1, 2).date(),
        datetime(2026, 1, 3).date(),
    ]
    assert snapshot_module._optional_date(None) is None
    parsed_date = snapshot_module._optional_date(datetime(2026, 1, 1).date())
    assert parsed_date is not None
    assert parsed_date.isoformat() == "2026-01-01"
    assert snapshot_module._optional_str("") is None
    assert snapshot_module._optional_bool(True) is True
    assert snapshot_module._optional_bool("1") is True
    assert snapshot_module._optional_float(True) is None
    assert snapshot_module._optional_float("1.5") == 1.5
    assert snapshot_module._price_or_none(0) is None
    assert snapshot_module._log_gap(0, 1) is None
    with pytest.raises(snapshot_module.SnapshotError):
        snapshot_module._parse_date(1)
    with pytest.raises(snapshot_module.SnapshotError):
        snapshot_module._as_datetime("not-a-datetime")
    with pytest.raises(snapshot_module.SnapshotError):
        snapshot_module._as_datetime(datetime(2026, 1, 1))

    snapshot_module._ensure_snapshot_dirs(tmp_path)
    assert (tmp_path / "target_audit").exists()
    json_path = tmp_path / "payload.json"
    snapshot_module._write_json(json_path, {"created_at": datetime(2026, 1, 1, tzinfo=UTC)})
    assert "2026-01-01" in json_path.read_text(encoding="utf-8")
    parquet_path = tmp_path / "payload.parquet"
    snapshot_module._write_parquet(parquet_path, [{"x": 1}])
    assert pl.read_parquet(parquet_path).select("x").item() == 1
    assert snapshot_module._hash_json([{"x": 1}])


def _raw_row(
    trading_date: str,
    contract_month: str,
    code: str,
    *,
    ao: float = 50800,
    ac: float = 51820,
    eo: float = 50450,
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
        "AC": ac,
        "EO": eo,
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
