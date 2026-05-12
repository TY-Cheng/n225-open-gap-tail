# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

NIKKEI225_OPTIONS_CATEGORY = "NK225E"


def normalize_jquants_nikkei225_option_rows(
    rows: list[dict[str, Any]],
    *,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:
    """Normalize J-Quants Nikkei 225 large-option daily rows.

    These rows are used only as lagged option-implied state. Same trading-date
    option rows are not considered available for that date's opening forecast.
    """
    normalized: list[dict[str, object]] = []
    jst = ZoneInfo("Asia/Tokyo")
    for row in rows:
        trading_date = _optional_date(row.get("Date"))
        if trading_date is None:
            continue
        normalized.append(
            {
                "source": "jquants",
                "source_endpoint": "/derivatives/bars/daily/options/225",
                "product_category": NIKKEI225_OPTIONS_CATEGORY,
                "trading_date": trading_date.isoformat(),
                "option_code": _optional_str(row.get("Code")),
                "contract_month": _optional_str(row.get("CM") or row.get("ContractMonth")),
                "central_contract_month_flag": _optional_bool(
                    row.get("CCMFlag") or row.get("CentralContractMonthFlag")
                ),
                "strike_price": _positive_float(row.get("Strike") or row.get("StrikePrice")),
                "put_call": _put_call(row.get("PCDiv") or row.get("PutCallDivision")),
                "night_session_open": _price_or_none(row.get("EO") or row.get("NightSessionOpen")),
                "night_session_high": _price_or_none(row.get("EH") or row.get("NightSessionHigh")),
                "night_session_low": _price_or_none(row.get("EL") or row.get("NightSessionLow")),
                "night_session_close": _price_or_none(
                    row.get("EC") or row.get("NightSessionClose")
                ),
                "volume": _optional_float(row.get("Vo") or row.get("Volume")),
                "open_interest": _optional_float(row.get("OI") or row.get("OpenInterest")),
                "settlement_price": _price_or_none(row.get("Settle") or row.get("SettlementPrice")),
                "theoretical_price": _price_or_none(row.get("Theo") or row.get("TheoreticalPrice")),
                "base_volatility": _rate_fraction(row.get("BaseVol") or row.get("BaseVolatility")),
                "underlying_price": _positive_float(
                    row.get("UnderPx") or row.get("UnderlyingPrice")
                ),
                "implied_volatility": _rate_fraction(row.get("IV") or row.get("ImpliedVolatility")),
                "interest_rate": _interest_rate_fraction(row.get("IR") or row.get("InterestRate")),
                "last_trading_day": _optional_date_iso(row.get("LTD") or row.get("LastTradingDay")),
                "special_quotation_day": _optional_date_iso(
                    row.get("SQD") or row.get("SpecialQuotationDay")
                ),
                "emergency_margin_trigger_division": _optional_str(
                    row.get("EmMrgnTrgDiv") or row.get("EmergencyMarginTriggerDivision")
                ),
                "vendor_available_ts_utc": datetime.combine(
                    trading_date + timedelta(days=1),
                    time(3, 0),
                    tzinfo=jst,
                ).astimezone(UTC),
                "research_download_ts_utc": downloaded_at_utc,
            }
        )
    # Do not globally sort here. Full-history NK225E pulls contain millions of
    # option-chain rows, and downstream aggregation groups by trading date
    # explicitly. Per-artifact writers can impose narrower ordering if needed.
    return normalized


def _optional_date(value: object) -> date | None:
    text = _optional_str(value)
    if text is None:
        return None
    compact = text.replace("-", "")
    try:
        if len(compact) == 8 and compact.isdigit():
            return date.fromisoformat(f"{compact[:4]}-{compact[4:6]}-{compact[6:]}")
        return date.fromisoformat(text)
    except ValueError:
        return None


def _optional_date_iso(value: object) -> str | None:
    parsed = _optional_date(value)
    return parsed.isoformat() if parsed is not None else None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    text = _optional_str(value)
    if text is None:
        return None
    if text in {"1", "true", "True", "TRUE"}:
        return True
    if text in {"0", "false", "False", "FALSE"}:
        return False
    return None


def _positive_float(value: object) -> float | None:
    parsed = _optional_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _price_or_none(value: object) -> float | None:
    parsed = _optional_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _rate_fraction(value: object) -> float | None:
    parsed = _positive_float(value)
    if parsed is None:
        return None
    return parsed / 100.0 if parsed > 1.0 else parsed


def _interest_rate_fraction(value: object) -> float | None:
    parsed = _positive_float(value)
    return None if parsed is None else parsed / 100.0


def _put_call(value: object) -> str | None:
    text = _optional_str(value)
    if text == "1":
        return "put"
    if text == "2":
        return "call"
    return None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
