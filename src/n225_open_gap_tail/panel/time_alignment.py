from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class TimeAlignmentError(ValueError):
    """Raised when timestamp alignment input rows are malformed."""


def build_time_alignment_records(
    *,
    target_rows: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
    minute_feature_records: list[dict[str, object]],
    vendor_lag_minutes: int = 5,
    us_timezone: str = "America/New_York",
) -> list[dict[str, object]]:
    reference_ticker = "SPY"
    us_tz = ZoneInfo(us_timezone)
    us_closes = [row for row in calendar_records if row.get("us_close_ts_utc") is not None]
    us_closes.sort(key=lambda row: _as_datetime(row["us_close_ts_utc"]))
    minute_by_date: dict[str, list[dict[str, object]]] = {}
    for record in minute_feature_records:
        if str(record.get("ticker") or reference_ticker).upper() != reference_ticker:
            continue
        minute_by_date.setdefault(str(record["bar_date_et"]), []).append(record)
    for records in minute_by_date.values():
        records.sort(key=lambda row: _as_datetime(row["bar_end_ts_utc"]))

    alignment: list[dict[str, object]] = []
    for target in target_rows:
        target_open = _as_datetime(target["target_open_ts_utc"])
        target_us_calendar_date = target_open.astimezone(us_tz).date().isoformat()
        close_row = _latest_us_close_before(us_closes, target_open)
        if close_row is None:
            alignment.append(
                {
                    "trading_date": target["trading_date"],
                    "target_open_ts_utc": target_open,
                    "target_us_calendar_date": target_us_calendar_date,
                    "minute_reference_ticker": reference_ticker,
                    "alignment_status": "missing_us_close",
                    "alignment_pass": False,
                }
            )
            continue
        us_close = _as_datetime(close_row["us_close_ts_utc"])
        model_cutoff = us_close + timedelta(minutes=vendor_lag_minutes)
        bar, bar_reason = _select_reference_close_bar(
            minute_by_date.get(str(close_row["calendar_date"]), []),
            official_close_ts_utc=us_close,
        )
        minutes = close_row.get("us_close_to_ose_night_close_minutes")
        alignment_pass, reason = _dst_alignment_check(
            close_row.get("dst_regime"),
            minutes,
            is_early_close=close_row.get("is_us_early_close") is True,
        )
        bar_end = _as_datetime(bar["bar_end_ts_utc"]) if bar else None
        alignment.append(
            {
                "trading_date": target["trading_date"],
                "us_calendar_date": close_row["calendar_date"],
                "target_us_calendar_date": target_us_calendar_date,
                "dst_regime": close_row.get("dst_regime"),
                "absorption_regime": close_row.get("absorption_regime"),
                "is_us_early_close": close_row.get("is_us_early_close"),
                "is_us_trading_day": close_row.get("is_us_trading_day"),
                "is_jpx_trading_day": close_row.get("is_jpx_trading_day"),
                "us_official_close_ts_utc": us_close,
                "us_official_close_ts_et": close_row.get("us_close_ts_et"),
                "model_cutoff_ts_utc": model_cutoff,
                "minute_reference_ticker": reference_ticker,
                "selected_reference_bar_end_ts_utc": bar_end,
                "selected_reference_bar_end_ts_et": bar.get("bar_end_ts_et") if bar else None,
                "reference_minute_close": bar.get("close") if bar else None,
                "vendor_lag_seconds": vendor_lag_minutes * 60 if bar else None,
                "reference_bar_selection_reason": bar_reason,
                "ose_night_close_ts_utc": close_row.get("ose_night_close_ts_utc"),
                "ose_night_close_ts_jst": close_row.get("ose_night_close_ts_jst"),
                "target_open_ts_utc": target_open,
                "target_open_ts_jst": target.get("target_open_ts_jst"),
                "us_close_to_ose_night_close_minutes": minutes,
                "alignment_pass": alignment_pass,
                "alignment_reason": reason,
                "cutoff_invariant_pass": model_cutoff < target_open
                and (bar_end is None or bar_end <= model_cutoff),
            }
        )
    return alignment


def _select_reference_close_bar(
    records: list[dict[str, object]],
    *,
    official_close_ts_utc: datetime,
) -> tuple[dict[str, object] | None, str]:
    candidates = [
        record
        for record in records
        if record.get("is_us_regular_session") is True
        and _as_datetime(record["bar_end_ts_utc"]) <= official_close_ts_utc
    ]
    if not candidates:
        return None, "missing_regular_session_close_bar"
    return candidates[-1], "last_regular_session_bar_at_or_before_official_close"


def _latest_us_close_before(
    us_closes: list[dict[str, object]],
    target_open_ts_utc: datetime,
) -> dict[str, object] | None:
    candidates = [
        row for row in us_closes if _as_datetime(row["us_close_ts_utc"]) < target_open_ts_utc
    ]
    return candidates[-1] if candidates else None


def _dst_alignment_check(
    regime: object,
    minutes: object,
    *,
    is_early_close: bool = False,
) -> tuple[bool, str]:
    if is_early_close and regime == "EST" and isinstance(minutes, int):
        return abs(minutes - 180) <= 5, "est_early_close_expected_180_plus_minus_5"
    if is_early_close and regime == "EDT" and isinstance(minutes, int):
        return abs(minutes - 240) <= 5, "edt_early_close_expected_240_plus_minus_5"
    if regime == "EST" and isinstance(minutes, int):
        return abs(minutes) <= 5, "est_expected_0_plus_minus_5"
    if regime == "EDT" and isinstance(minutes, int):
        return 55 <= minutes <= 65, "edt_expected_55_to_65"
    return False, "missing_or_unknown_dst_regime"


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TimeAlignmentError("Expected timezone-aware datetime")
    return value
