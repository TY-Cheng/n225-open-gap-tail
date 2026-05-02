from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

PRODUCT_CATEGORY = "NK225F"

PRICE_FIELDS = {
    "day_session_open": "AO",
    "day_session_high": "AH",
    "day_session_low": "AL",
    "day_session_close": "AC",
    "night_session_open": "EO",
    "night_session_high": "EH",
    "night_session_low": "EL",
    "night_session_close": "EC",
    "settlement_price": "Settle",
}
FIELD_MAPPING = {
    **PRICE_FIELDS,
    "volume": "Vo",
    "open_interest": "OI",
    "contract_month": "CM",
    "contract_code": "Code",
    "central_contract_month_flag": "CCMFlag",
    "last_trading_day": "LTD",
    "special_quotation_day": "SQD",
    "product_category": "ProdCat",
    "trading_date": "Date",
}
REQUIRED_SCHEMA_FIELDS = {
    "Date",
    "ProdCat",
    "Code",
    "AO",
    "AH",
    "AL",
    "AC",
    "EO",
    "EH",
    "EL",
    "EC",
    "Settle",
    "Vo",
    "OI",
    "CM",
    "CCMFlag",
    "LTD",
    "SQD",
}


class JQuantsFuturesError(ValueError):
    """Raised when a J-Quants futures row cannot be normalized safely."""


def normalize_jquants_futures_rows(
    rows: list[dict[str, Any]],
    *,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    jst = ZoneInfo("Asia/Tokyo")
    for row in rows:
        if str(row.get("ProdCat", "")) != PRODUCT_CATEGORY:
            continue
        trading_date = _parse_date(row.get("Date"))
        target_open_ts_jst = datetime.combine(trading_date, time(8, 45), tzinfo=jst)
        night_close_ts_jst = datetime.combine(trading_date, time(6, 0), tzinfo=jst)
        normalized.append(
            {
                "source": "jquants",
                "source_endpoint": "/derivatives/bars/daily/futures",
                "product_category": PRODUCT_CATEGORY,
                "trading_date": trading_date.isoformat(),
                "contract_code": _optional_str(row.get("Code")),
                "contract_month": _optional_str(row.get("CM")),
                "central_contract_month_flag": _optional_bool(row.get("CCMFlag")),
                "day_session_open": _price_or_none(row.get("AO")),
                "day_session_high": _price_or_none(row.get("AH")),
                "day_session_low": _price_or_none(row.get("AL")),
                "day_session_close": _price_or_none(row.get("AC")),
                "night_session_open": _price_or_none(row.get("EO")),
                "night_session_high": _price_or_none(row.get("EH")),
                "night_session_low": _price_or_none(row.get("EL")),
                "night_session_close": _price_or_none(row.get("EC")),
                "settlement_price": _price_or_none(row.get("Settle")),
                "volume": _optional_float(row.get("Vo")),
                "open_interest": _optional_float(row.get("OI")),
                "last_trading_day": _optional_date_iso(row.get("LTD")),
                "special_quotation_day": _optional_date_iso(row.get("SQD")),
                "target_open_ts_jst": target_open_ts_jst,
                "target_open_ts_utc": target_open_ts_jst.astimezone(UTC),
                "night_close_ts_jst": night_close_ts_jst,
                "night_close_ts_utc": night_close_ts_jst.astimezone(UTC),
                "vendor_available_ts_utc": datetime.combine(
                    trading_date + timedelta(days=1),
                    time(3, 0),
                    tzinfo=jst,
                ).astimezone(UTC),
                "research_download_ts_utc": downloaded_at_utc,
            }
        )
    normalized.sort(key=lambda item: (str(item["trading_date"]), str(item["contract_code"])))
    return normalized


def build_jquants_schema_probe(rows: list[dict[str, Any]]) -> dict[str, object]:
    fields = sorted({field for row in rows for field in row})
    missing_required = sorted(REQUIRED_SCHEMA_FIELDS.difference(fields))
    product_counts: dict[str, int] = {}
    coverage: dict[str, int] = {field: 0 for field in sorted(REQUIRED_SCHEMA_FIELDS)}
    zero_price_counts: dict[str, int] = {canonical: 0 for canonical in PRICE_FIELDS}
    for row in rows:
        product = str(row.get("ProdCat", "<missing>"))
        product_counts[product] = product_counts.get(product, 0) + 1
        for field in coverage:
            if row.get(field) not in (None, ""):
                coverage[field] += 1
        for canonical, raw_field in PRICE_FIELDS.items():
            value = row.get(raw_field)
            if value in (0, 0.0, "0"):
                zero_price_counts[canonical] += 1
    return {
        "source": "jquants",
        "endpoint": "/derivatives/bars/daily/futures",
        "field_mapping": FIELD_MAPPING,
        "observed_fields": fields,
        "missing_required_fields": missing_required,
        "product_counts": product_counts,
        "required_field_coverage": coverage,
        "zero_price_counts": zero_price_counts,
        "fail_closed": bool(missing_required),
    }


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise JQuantsFuturesError("J-Quants row is missing a date string")
    return date.fromisoformat(value)


def _optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _optional_date_iso(value: object) -> str | None:
    parsed = _optional_date(value)
    return parsed.isoformat() if parsed else None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | str):
        return int(value) == 1
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _price_or_none(value: object) -> float | None:
    parsed = _optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed
