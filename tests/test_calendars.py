from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from n225_open_gap_tail.calendars import build_session_calendar_records, write_calendar_table
from n225_open_gap_tail.config import Settings


def test_build_session_calendar_records_marks_holidays_and_dst() -> None:
    records = build_session_calendar_records(
        start="2026-01-01",
        end="2026-01-06",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )
    by_date = {str(record["calendar_date"]): record for record in records}

    assert by_date["2026-01-01"]["is_us_weekday_holiday"] is True
    assert by_date["2026-01-02"]["is_us_trading_day"] is True
    assert by_date["2026-01-02"]["is_jpx_trading_day"] is False
    assert by_date["2026-01-05"]["is_jpx_trading_day"] is True
    assert by_date["2026-01-05"]["us_close_ts_utc"] is not None
    assert by_date["2026-01-05"]["us_close_ts_jst"] is not None
    assert by_date["2026-01-05"]["is_us_dst"] is False
    assert by_date["2026-01-05"]["dst_regime"] == "EST"
    assert by_date["2026-01-05"]["us_close_to_ose_night_close_minutes"] == 0
    assert by_date["2026-01-05"]["absorption_regime"] == "coincident_us_ose_night_close"

    summer = build_session_calendar_records(
        start="2026-07-01",
        end="2026-07-01",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )
    assert summer[0]["is_us_dst"] is True
    assert summer[0]["dst_regime"] == "EDT"
    assert summer[0]["us_close_to_ose_night_close_minutes"] == 60
    assert summer[0]["absorption_regime"] == "post_us_close_night_absorption"


def test_build_session_calendar_records_marks_us_early_close() -> None:
    records = build_session_calendar_records(
        start="2026-11-25",
        end="2026-11-28",
        us_exchange="XNYS",
        jpx_exchange="JPX",
    )
    by_date = {str(record["calendar_date"]): record for record in records}

    assert by_date["2026-11-26"]["is_us_weekday_holiday"] is True
    assert by_date["2026-11-27"]["is_us_trading_day"] is True
    assert by_date["2026-11-27"]["is_us_early_close"] is True
    assert by_date["2026-11-27"]["us_close_to_ose_night_close_minutes"] == 180
    assert by_date["2026-11-27"]["absorption_regime"] == "post_us_close_night_absorption"


def test_write_calendar_table_writes_metadata_and_parquet(tmp_path: Path) -> None:
    settings = Settings(
        bronze_data_dir=tmp_path / "bronze",
        silver_data_dir=tmp_path / "silver",
    )

    result = write_calendar_table(settings=settings, start="2026-01-01", end="2026-01-10")
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    frame = pl.read_parquet(result.parquet_path)

    assert "bronze/calendar_sessions" in result.metadata_path.as_posix()
    assert "silver/calendar_sessions" in result.parquet_path.as_posix()
    assert metadata["source"] == "exchange_calendars"
    assert result.rows == 10
    assert result.us_trading_days == 6
    assert result.jpx_trading_days == 5
    assert frame.height == 10
    assert "is_us_early_close" in frame.columns
    assert "us_close_to_ose_night_close_minutes" in frame.columns
    assert "absorption_regime" in frame.columns
