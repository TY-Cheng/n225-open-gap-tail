from __future__ import annotations

import math
from datetime import date, timedelta


def build_target_audit_records(
    normalized_rows: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    roll_days_before_last_trade: int,
) -> list[dict[str, object]]:
    central_rows = [
        row for row in normalized_rows if row.get("central_contract_month_flag") is True
    ]
    all_by_contract: dict[str, list[dict[str, object]]] = {}
    for row in normalized_rows:
        code = str(row.get("contract_code") or "")
        if code:
            all_by_contract.setdefault(code, []).append(row)
    for rows in all_by_contract.values():
        rows.sort(key=lambda item: str(item["trading_date"]))

    jpx_sessions = [
        date.fromisoformat(str(row["calendar_date"]))
        for row in calendar_records
        if row.get("is_jpx_trading_day") is True
    ]

    target_rows: list[dict[str, object]] = []
    previous_central: dict[str, object] | None = None
    for row in sorted(central_rows, key=lambda item: str(item["trading_date"])):
        trading_date = date.fromisoformat(str(row["trading_date"]))
        contract_code = str(row.get("contract_code") or "")
        prior_row = _previous_same_contract_row(
            all_by_contract.get(contract_code, []),
            trading_date,
        )
        roll_window = _is_roll_sq_window(
            trading_date=trading_date,
            last_trading_day=_optional_date(row.get("last_trading_day")),
            special_quotation_day=_optional_date(row.get("special_quotation_day")),
            jpx_sessions=jpx_sessions,
            roll_days_before_last_trade=roll_days_before_last_trade,
        )
        same_contract = prior_row is not None
        missing_reasons = _target_missing_reasons(
            target_row=row,
            prior_row=prior_row,
            roll_window=roll_window,
            previous_central=previous_central,
        )
        full_gap_settle = _log_gap(
            row.get("day_session_open"), _value(prior_row, "settlement_price")
        )
        full_gap_close = _log_gap(
            row.get("day_session_open"), _value(prior_row, "day_session_close")
        )
        residual_night = _log_gap(row.get("day_session_open"), row.get("night_session_close"))
        clean_eligible = same_contract and not roll_window and not missing_reasons
        target_rows.append(
            {
                "trading_date": row["trading_date"],
                "contract_code": contract_code,
                "contract_month": row.get("contract_month"),
                "reference_contract_code": _value(prior_row, "contract_code"),
                "same_contract_only": same_contract,
                "is_roll_sq_window": roll_window,
                "clean_sample": clean_eligible,
                "missing_reason": ";".join(missing_reasons) if missing_reasons else None,
                "target_open_ts_utc": row["target_open_ts_utc"],
                "target_open_ts_jst": row["target_open_ts_jst"],
                "jquants_vendor_available_ts_utc": row.get("vendor_available_ts_utc"),
                "reference_date": _value(prior_row, "trading_date"),
                "day_session_open": row.get("day_session_open"),
                "day_session_high": row.get("day_session_high"),
                "day_session_low": row.get("day_session_low"),
                "day_session_close": row.get("day_session_close"),
                "night_session_open": row.get("night_session_open"),
                "night_session_high": row.get("night_session_high"),
                "night_session_low": row.get("night_session_low"),
                "prior_settlement_price": _value(prior_row, "settlement_price"),
                "prior_day_session_close": _value(prior_row, "day_session_close"),
                "night_session_close": row.get("night_session_close"),
                "full_gap_settle_to_open": full_gap_settle,
                "full_gap_close_to_open": full_gap_close,
                "residual_nightclose_to_day_open": residual_night,
                "loss_settle_to_open": -full_gap_settle if full_gap_settle is not None else None,
                "volume": row.get("volume"),
                "open_interest": row.get("open_interest"),
                "volume_oi_anomaly": _volume_oi_anomaly(row),
                "last_trading_day": row.get("last_trading_day"),
                "special_quotation_day": row.get("special_quotation_day"),
            }
        )
        previous_central = row
    return target_rows


def _target_missing_reasons(
    *,
    target_row: dict[str, object],
    prior_row: dict[str, object] | None,
    roll_window: bool,
    previous_central: dict[str, object] | None,
) -> list[str]:
    reasons: list[str] = []
    if target_row.get("day_session_open") is None:
        reasons.append("holiday_trading_no_day_open")
    if prior_row is None:
        reasons.append("cross_contract_excluded" if previous_central else "missing_reference_price")
    if prior_row is not None and prior_row.get("settlement_price") is None:
        reasons.append("missing_reference_price")
    if roll_window:
        reasons.append("roll_sq_excluded")
    return reasons


def _previous_same_contract_row(
    rows: list[dict[str, object]],
    trading_date: date,
) -> dict[str, object] | None:
    candidates = [
        row for row in rows if date.fromisoformat(str(row["trading_date"])) < trading_date
    ]
    return candidates[-1] if candidates else None


def _is_roll_sq_window(
    *,
    trading_date: date,
    last_trading_day: date | None,
    special_quotation_day: date | None,
    jpx_sessions: list[date],
    roll_days_before_last_trade: int,
) -> bool:
    if last_trading_day is None or special_quotation_day is None:
        return False
    if last_trading_day in jpx_sessions:
        index = jpx_sessions.index(last_trading_day)
        start_index = max(0, index - roll_days_before_last_trade + 1)
        roll_start = jpx_sessions[start_index]
    else:
        roll_start = last_trading_day - timedelta(days=7)
    return roll_start <= trading_date <= special_quotation_day


def _volume_oi_anomaly(row: dict[str, object]) -> str | None:
    volume = row.get("volume")
    oi = row.get("open_interest")
    if volume == 0:
        return "volume_zero"
    if oi == 0:
        return "open_interest_zero"
    return None


def _optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _log_gap(open_price: object, reference_price: object) -> float | None:
    open_value = _optional_float(open_price)
    reference_value = _optional_float(reference_price)
    if open_value is None or reference_value is None or open_value <= 0 or reference_value <= 0:
        return None
    return math.log(open_value) - math.log(reference_value)


def _value(row: dict[str, object] | None, key: str) -> object | None:
    return row.get(key) if row is not None else None
