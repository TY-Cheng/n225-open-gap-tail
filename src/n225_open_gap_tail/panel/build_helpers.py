from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.config.runtime import PipelineRunError
from n225_open_gap_tail.data_lake.schemas import (
    ForecastExclusionReason,
    JoinMissReason,
    MappingStatus,
)
from n225_open_gap_tail.market.calendars import build_session_calendar_records


def resolve_default_end_date(today: date | None = None) -> str:
    """Return the most recent completed Friday before the run date."""
    run_date = today or date.today()
    days_since_friday = (run_date.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7
    return (run_date - timedelta(days=days_since_friday)).isoformat()


def target_audit_calendar_records(
    *,
    settings: Settings,
    base_calendar_records: list[dict[str, object]],
    normalized_rows: list[dict[str, object]],
    start: str,
    end: str,
) -> list[dict[str, object]]:
    horizon = _target_audit_calendar_horizon(normalized_rows, fallback=end)
    if horizon <= end:
        return base_calendar_records
    return build_session_calendar_records(
        start=(date.fromisoformat(start) - timedelta(days=10)).isoformat(),
        end=horizon,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )


def _target_audit_calendar_horizon(
    normalized_rows: list[dict[str, object]],
    *,
    fallback: str,
) -> str:
    dates = [date.fromisoformat(fallback)]
    for row in normalized_rows:
        for field in ("last_trading_day", "special_quotation_day"):
            value = row.get(field)
            if isinstance(value, str) and value:
                try:
                    dates.append(date.fromisoformat(value[:10]))
                except ValueError:
                    continue
    return max(dates).isoformat()


def _assert_unique_record_keys(
    rows: list[dict[str, object]],
    *,
    key_field: str,
    context: str,
) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        key = str(row.get(key_field) or "")
        if not key:
            continue
        if key in seen:
            duplicates.append(key)
        else:
            seen.add(key)
    if duplicates:
        preview = ", ".join(duplicates[:5])
        raise PipelineRunError(f"Duplicate {context} for {key_field}: {preview}")


def _max_date_strings(*values: str | None) -> str | None:
    valid = [value for value in values if isinstance(value, str) and value]
    return max(valid) if valid else None


def _panel_join_miss_reason(alignment: Mapping[str, object], us_date: str) -> str | None:
    if not alignment:
        return JoinMissReason.CALENDAR_DESYNC.value
    if alignment.get("alignment_status") == "missing_us_close":
        return JoinMissReason.US_MARKET_CLOSED.value
    if not us_date:
        return JoinMissReason.CALENDAR_DESYNC.value
    if alignment.get("alignment_pass") is False:
        return JoinMissReason.US_EARLY_CLOSE_BEYOND_VENDOR_LAG.value
    return None


def _forecast_sample_exclusion_reason(
    *,
    target_clean: bool,
    mapping_status: str,
    join_miss_reason: str | None,
    cutoff: datetime | None,
    target_open: datetime | None,
) -> str | None:
    if not target_clean:
        return ForecastExclusionReason.TARGET_NOT_CLEAN.value
    if mapping_status != MappingStatus.NORMAL_TRADING.value:
        return ForecastExclusionReason.MAPPING_NOT_NORMAL.value
    if join_miss_reason:
        return ForecastExclusionReason.JOIN_MISS.value
    if cutoff is None or target_open is None:
        return ForecastExclusionReason.MISSING_CUTOFF_OR_TARGET_OPEN.value
    if cutoff >= target_open:
        return ForecastExclusionReason.CUTOFF_AFTER_TARGET_OPEN.value
    return None
