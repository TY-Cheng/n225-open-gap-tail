from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals  # type: ignore[import-untyped]

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import atomic_write_parquet, write_json_atomic


@dataclass(frozen=True)
class CalendarBuildResult:
    metadata_path: Path
    parquet_path: Path
    rows: int
    us_trading_days: int
    jpx_trading_days: int
    us_early_closes: int


def build_session_calendar_records(
    *,
    start: str,
    end: str,
    us_exchange: str,
    jpx_exchange: str,
    us_timezone: str = "America/New_York",
    jpx_timezone: str = "Asia/Tokyo",
) -> list[dict[str, object]]:
    us_calendar = xcals.get_calendar(us_exchange)
    jpx_calendar = xcals.get_calendar(jpx_exchange)
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    us_sessions = _session_date_set(us_calendar, start, end)
    jpx_sessions = _session_date_set(jpx_calendar, start, end)
    us_early_closes = _early_close_date_set(us_calendar, start_date, end_date)
    jpx_early_closes = _early_close_date_set(jpx_calendar, start_date, end_date)
    us_holidays = _weekday_holiday_set(start_date, end_date, us_sessions)
    jpx_holidays = _weekday_holiday_set(start_date, end_date, jpx_sessions)
    us_zone = ZoneInfo(us_timezone)
    jpx_zone = ZoneInfo(jpx_timezone)

    records: list[dict[str, object]] = []
    for current_date in _date_range(start_date, end_date):
        date_key = current_date.isoformat()
        us_open, us_close = _session_open_close(us_calendar, current_date, us_sessions)
        jpx_open, jpx_close = _session_open_close(jpx_calendar, current_date, jpx_sessions)
        us_close_jst = us_close.astimezone(jpx_zone) if us_close is not None else None
        ose_night_close = _ose_night_close_for_us_close(us_close_jst, jpx_zone)
        ose_night_close_utc = ose_night_close.astimezone(UTC) if ose_night_close else None
        minutes_to_night_close = _minutes_between(us_close, ose_night_close_utc)

        records.append(
            {
                "source": "exchange_calendars",
                "calendar_date": date_key,
                "weekday": current_date.weekday(),
                "us_exchange": us_exchange,
                "jpx_exchange": jpx_exchange,
                "is_us_trading_day": date_key in us_sessions,
                "is_jpx_trading_day": date_key in jpx_sessions,
                "is_us_weekday_holiday": current_date in us_holidays,
                "is_jpx_weekday_holiday": current_date in jpx_holidays,
                "is_us_holiday_adjacent": _is_adjacent_to(current_date, us_holidays),
                "is_jpx_holiday_adjacent": _is_adjacent_to(current_date, jpx_holidays),
                "is_us_early_close": current_date in us_early_closes,
                "is_jpx_early_close": current_date in jpx_early_closes,
                "is_us_dst": _is_dst(current_date, us_zone),
                "dst_regime": _dst_regime(current_date, us_zone)
                if date_key in us_sessions
                else None,
                "us_open_ts_utc": us_open,
                "us_close_ts_utc": us_close,
                "us_close_ts_et": us_close.astimezone(us_zone) if us_close is not None else None,
                "us_close_ts_jst": us_close_jst,
                "ose_night_close_ts_utc": ose_night_close_utc,
                "ose_night_close_ts_jst": ose_night_close,
                "us_close_to_ose_night_close_minutes": minutes_to_night_close,
                "absorption_regime": _absorption_regime(minutes_to_night_close),
                "jpx_open_ts_utc": jpx_open,
                "jpx_close_ts_utc": jpx_close,
                "jpx_open_ts_jst": jpx_open.astimezone(jpx_zone) if jpx_open is not None else None,
                "jpx_close_ts_jst": jpx_close.astimezone(jpx_zone)
                if jpx_close is not None
                else None,
            }
        )
    return records


def write_calendar_table(
    *,
    settings: Settings,
    start: str,
    end: str,
) -> CalendarBuildResult:
    records = build_session_calendar_records(
        start=start,
        end=end,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )

    bronze_dir = (
        settings.bronze_data_dir
        / "calendar_sessions"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    silver_dir = (
        settings.silver_data_dir
        / "calendar_sessions"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    metadata_path = bronze_dir / "metadata.json"
    parquet_path = silver_dir / "data.parquet"

    metadata = {
        "source": "exchange_calendars",
        "us_exchange": settings.calendar_us_exchange,
        "jpx_exchange": settings.calendar_jpx_exchange,
        "start": start,
        "end": end,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "note": (
            "Calendar rows are historical alignment scaffolding for research. "
            "OSE derivatives-specific holiday trading should be audited when futures "
            "data is licensed."
        ),
    }
    write_json_atomic(metadata_path, metadata)
    atomic_write_parquet(parquet_path, records)

    return CalendarBuildResult(
        metadata_path=metadata_path,
        parquet_path=parquet_path,
        rows=len(records),
        us_trading_days=sum(1 for record in records if record["is_us_trading_day"] is True),
        jpx_trading_days=sum(1 for record in records if record["is_jpx_trading_day"] is True),
        us_early_closes=sum(1 for record in records if record["is_us_early_close"] is True),
    )


def _session_date_set(calendar: Any, start: str, end: str) -> set[str]:
    sessions = calendar.sessions_in_range(start, end)
    return {session.date().isoformat() for session in sessions}


def _early_close_date_set(calendar: Any, start_date: date, end_date: date) -> set[date]:
    dates: set[date] = set()
    for session in calendar.early_closes:
        session_date = session.date()
        if start_date <= session_date <= end_date:
            dates.add(session_date)
    return dates


def _weekday_holiday_set(start_date: date, end_date: date, sessions: set[str]) -> set[date]:
    return {
        current_date
        for current_date in _date_range(start_date, end_date)
        if current_date.weekday() < 5 and current_date.isoformat() not in sessions
    }


def _session_open_close(
    calendar: Any,
    session_date: date,
    sessions: set[str],
) -> tuple[datetime | None, datetime | None]:
    if session_date.isoformat() not in sessions:
        return None, None
    open_ts = calendar.session_open(session_date.isoformat())
    close_ts = calendar.session_close(session_date.isoformat())
    return _to_utc_datetime(open_ts), _to_utc_datetime(close_ts)


def _to_utc_datetime(value: Any) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise TypeError("Expected datetime-like calendar timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_adjacent_to(current_date: date, holiday_dates: set[date]) -> bool:
    return (
        current_date - timedelta(days=1) in holiday_dates
        or current_date + timedelta(days=1) in holiday_dates
    )


def _is_dst(current_date: date, timezone: ZoneInfo) -> bool:
    noon = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone).replace(hour=12)
    dst_offset = noon.dst()
    return bool(dst_offset and dst_offset != timedelta(0))


def _dst_regime(current_date: date, timezone: ZoneInfo) -> str:
    return "EDT" if _is_dst(current_date, timezone) else "EST"


def _ose_night_close_for_us_close(
    us_close_jst: datetime | None,
    jpx_timezone: ZoneInfo,
) -> datetime | None:
    if us_close_jst is None:
        return None
    return datetime.combine(us_close_jst.date(), time(6, 0), tzinfo=jpx_timezone)


def _minutes_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() // 60)


def _absorption_regime(minutes_to_night_close: int | None) -> str | None:
    if minutes_to_night_close is None:
        return None
    if minutes_to_night_close == 0:
        return "coincident_us_ose_night_close"
    if minutes_to_night_close > 0:
        return "post_us_close_night_absorption"
    return "us_close_after_ose_night_close"


def _date_range(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    if days < 0:
        raise ValueError("start date must be on or before end date")
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]
