from __future__ import annotations

from collections.abc import Mapping

from n225_open_gap_tail.config.runtime import _optional_float
from n225_open_gap_tail.data_lake.schemas import MappingStatus
from n225_open_gap_tail.features.asof import _coerce_datetime


def build_calendar_map_records(
    *,
    target_rows: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    calendar_by_date = {str(row["calendar_date"]): row for row in calendar_records}
    alignment_by_target = {str(row["trading_date"]): row for row in alignment_records}
    records: list[dict[str, object]] = []
    for target in target_rows:
        ose_date = str(target["trading_date"])
        alignment = alignment_by_target.get(ose_date, {})
        us_session_date = str(alignment.get("us_calendar_date") or "")
        calendar_row = calendar_by_date.get(us_session_date) or calendar_by_date.get(ose_date) or {}
        mapping_status, mapping_reason = _calendar_mapping_status(
            target=target,
            alignment=alignment,
            calendar_row=calendar_row,
        )
        records.append(
            {
                "ose_trading_date": ose_date,
                "us_session_date": us_session_date or None,
                "us_official_close_ts_utc": _coerce_datetime(
                    alignment.get("us_official_close_ts_utc")
                    or alignment.get("model_cutoff_ts_utc")
                    or calendar_row.get("us_close_ts_utc")
                ),
                "us_early_close_flag": bool(calendar_row.get("is_us_early_close", False)),
                "dst_regime": alignment.get("dst_regime") or calendar_row.get("dst_regime"),
                "ose_day_open_ts_utc": _coerce_datetime(
                    alignment.get("target_open_ts_utc") or target.get("target_open_ts_utc")
                ),
                "ose_night_close_ts_utc": _coerce_datetime(
                    alignment.get("ose_night_close_ts_utc")
                    or calendar_row.get("ose_night_close_ts_utc")
                ),
                "us_close_to_ose_night_close_minutes": _optional_float(
                    alignment.get("us_close_to_ose_night_close_minutes")
                    or calendar_row.get("us_close_to_ose_night_close_minutes")
                ),
                "model_cutoff_ts_utc": _coerce_datetime(alignment.get("model_cutoff_ts_utc")),
                "target_open_ts_utc": _coerce_datetime(
                    alignment.get("target_open_ts_utc") or target.get("target_open_ts_utc")
                ),
                "mapping_status": mapping_status,
                "mapping_reason": mapping_reason,
            }
        )
    return records


def _calendar_mapping_status(
    *,
    target: Mapping[str, object],
    alignment: Mapping[str, object],
    calendar_row: Mapping[str, object],
) -> tuple[str, str | None]:
    if not alignment:
        return MappingStatus.UNMAPPED.value, "missing_time_alignment"
    if alignment.get("alignment_status") == "missing_us_close":
        return MappingStatus.US_HOLIDAY.value, "no_us_close_before_target_open"
    if target.get("missing_reason") == "holiday_trading_no_day_open":
        return MappingStatus.OSE_HOLIDAY_TRADING.value, "ose_holiday_trading_no_day_open"
    if (
        calendar_row.get("is_us_trading_day") is False
        and calendar_row.get("is_jpx_trading_day") is True
    ):
        return MappingStatus.US_HOLIDAY.value, "us_closed_jpx_open"
    if (
        calendar_row.get("is_jpx_trading_day") is False
        and calendar_row.get("is_us_trading_day") is True
    ):
        return MappingStatus.US_JP_DESYNC.value, "us_open_jpx_closed"
    if alignment.get("alignment_pass") is False:
        return MappingStatus.US_JP_DESYNC.value, str(alignment.get("alignment_reason"))
    return MappingStatus.NORMAL_TRADING.value, None


__all__ = [name for name in globals() if not name.startswith("_")]
