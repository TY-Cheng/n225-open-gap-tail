# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    atomic_write_parquet,
    cache_path,
    date,
    datetime,
    JQUANTS_OPTIONS_SILVER_SCHEMA,
    math,
    np,
    PIPELINE_CONFIG,
    Settings,
    _optional_float,
)

N225_OPTION_FEATURES = (
    "n225_option_atm_iv_lag_1",
    "n225_option_atm_put_call_iv_skew_lag_1",
    "n225_option_base_volatility_lag_1",
    "n225_option_iv_oi_weighted_lag_1",
    "n225_option_put_call_oi_ratio_lag_1",
    "n225_option_put_call_volume_ratio_lag_1",
    "n225_option_total_open_interest_log1p_lag_1",
    "n225_option_total_volume_log1p_lag_1",
    "n225_option_valid_contract_count_lag_1",
    "n225_option_days_to_sq_lag_1",
)


def write_jquants_options_silver_cache(
    *,
    settings: Settings,
    rows: list[dict[str, object]],
) -> None:
    root = settings.data_dir / "silver"
    by_month: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in rows:
        trading_date = str(row.get("trading_date") or "")
        if not trading_date:
            continue
        parsed = date.fromisoformat(trading_date)
        by_month.setdefault((parsed.year, parsed.month), []).append(row)
    for (year, month), chunk_rows in sorted(by_month.items()):
        path = cache_path(
            root,
            dataset="jquants_nk225_options_daily",
            schema_version=JQUANTS_OPTIONS_SILVER_SCHEMA.version,
            year=year,
            month=month,
        )
        atomic_write_parquet(
            path,
            chunk_rows,
            schema=JQUANTS_OPTIONS_SILVER_SCHEMA,
            metadata={
                "source": "jquants",
                "layer": "silver",
                "product_category": "NK225E",
                "year": year,
                "month": month,
            },
        )


def build_n225_option_feature_records(
    option_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Aggregate J-Quants Nikkei 225 large options into daily option-state rows."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in option_rows:
        trading_date = str(row.get("trading_date") or "")
        if trading_date:
            grouped.setdefault(trading_date, []).append(row)
    output = [_daily_option_summary(date_key, rows) for date_key, rows in sorted(grouped.items())]
    return [row for row in output if row is not None]


def add_n225_option_features(
    panel_rows: list[dict[str, object]],
    option_feature_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Stamp lagged option-implied features using only prior available option rows."""
    option_summaries = sorted(
        option_feature_records,
        key=lambda row: str(row.get("trading_date") or ""),
    )
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    output: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        forecast_date = str(enriched.get("forecast_date") or "")
        cutoff = _coerce_datetime(enriched.get("model_cutoff_ts_utc"))
        candidates = [
            summary
            for summary in option_summaries
            if str(summary.get("trading_date") or "") < forecast_date
            and _available_by_cutoff(summary, cutoff)
        ]
        latest = candidates[-1] if candidates else None
        for feature in N225_OPTION_FEATURES:
            source = feature.removeprefix("n225_option_").removesuffix("_lag_1")
            enriched[feature] = None if latest is None else latest.get(source)
            enriched[f"{feature}__source_date"] = (
                None if latest is None else latest.get("trading_date")
            )
        output.append(enriched)
    return output


def _daily_option_summary(
    trading_date: str,
    rows: list[dict[str, object]],
) -> dict[str, object] | None:
    valid = [
        row
        for row in rows
        if _optional_float(row.get("strike_price")) is not None
        and _optional_float(row.get("underlying_price")) is not None
        and _optional_float(row.get("implied_volatility")) is not None
    ]
    if not valid:
        return None
    central = [row for row in valid if row.get("central_contract_month_flag") is True]
    dte_scoped = _configured_dte_scope(trading_date, central or valid)
    scoped = dte_scoped or central or valid
    atm_rows = _atm_rows(scoped)
    atm_iv = _safe_median([_optional_float(row.get("implied_volatility")) for row in atm_rows])
    put_atm = _safe_median(
        [
            _optional_float(row.get("implied_volatility"))
            for row in atm_rows
            if row.get("put_call") == "put"
        ]
    )
    call_atm = _safe_median(
        [
            _optional_float(row.get("implied_volatility"))
            for row in atm_rows
            if row.get("put_call") == "call"
        ]
    )
    total_oi = sum(_optional_float(row.get("open_interest")) or 0.0 for row in scoped)
    total_volume = sum(_optional_float(row.get("volume")) or 0.0 for row in scoped)
    put_oi = sum(
        _optional_float(row.get("open_interest")) or 0.0
        for row in scoped
        if row.get("put_call") == "put"
    )
    call_oi = sum(
        _optional_float(row.get("open_interest")) or 0.0
        for row in scoped
        if row.get("put_call") == "call"
    )
    put_volume = sum(
        _optional_float(row.get("volume")) or 0.0 for row in scoped if row.get("put_call") == "put"
    )
    call_volume = sum(
        _optional_float(row.get("volume")) or 0.0 for row in scoped if row.get("put_call") == "call"
    )
    return {
        "trading_date": trading_date,
        "vendor_available_ts_utc": _max_datetime(
            row.get("vendor_available_ts_utc") for row in scoped
        ),
        "atm_iv": atm_iv,
        "atm_put_call_iv_skew": None if put_atm is None or call_atm is None else put_atm - call_atm,
        "base_volatility": _safe_median(
            [_optional_float(row.get("base_volatility")) for row in scoped]
        ),
        "iv_oi_weighted": _weighted_mean(
            values=[_optional_float(row.get("implied_volatility")) for row in scoped],
            weights=[_optional_float(row.get("open_interest")) for row in scoped],
        ),
        "put_call_oi_ratio": put_oi / call_oi if call_oi > 0 else None,
        "put_call_volume_ratio": put_volume / call_volume if call_volume > 0 else None,
        "total_open_interest_log1p": math.log1p(total_oi) if total_oi >= 0 else None,
        "total_volume_log1p": math.log1p(total_volume) if total_volume >= 0 else None,
        "valid_contract_count": float(len(scoped)),
        "days_to_sq": _safe_median(_days_to_sq(trading_date, row) for row in scoped),
    }


def _atm_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    distances: list[tuple[float, dict[str, object]]] = []
    for row in rows:
        strike = _optional_float(row.get("strike_price"))
        underlying = _optional_float(row.get("underlying_price"))
        if strike is not None and underlying is not None:
            distances.append((abs(strike - underlying), row))
    if not distances:
        return []
    min_distance = min(distance for distance, _ in distances)
    return [row for distance, row in distances if distance == min_distance]


def _days_to_sq(trading_date: str, row: dict[str, object]) -> float | None:
    sq_raw = row.get("special_quotation_day")
    if sq_raw is None:
        return None
    try:
        return float((date.fromisoformat(str(sq_raw)) - date.fromisoformat(trading_date)).days)
    except ValueError:
        return None


def _configured_dte_scope(
    trading_date: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    policy = PIPELINE_CONFIG.feature_engineering
    min_dte = policy.options_dte_short_bucket[0]
    max_dte = policy.options_dte_medium_bucket[1]
    scoped: list[dict[str, object]] = []
    for row in rows:
        days_to_sq = _days_to_sq(trading_date, row)
        if days_to_sq is not None and min_dte <= days_to_sq <= max_dte:
            scoped.append(row)
    return scoped


def _available_by_cutoff(row: dict[str, object], cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    available = _coerce_datetime(row.get("vendor_available_ts_utc"))
    return available is not None and available <= cutoff


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _max_datetime(values: object) -> datetime | None:
    parsed = [value for value in values if isinstance(value, datetime)]
    return max(parsed) if parsed else None


def _safe_median(values: object) -> float | None:
    valid = [value for value in values if value is not None and math.isfinite(float(value))]
    if not valid:
        return None
    return float(np.median(valid))


def _weighted_mean(values: list[float | None], weights: list[float | None]) -> float | None:
    pairs = [
        (float(value), float(weight))
        for value, weight in zip(values, weights, strict=False)
        if value is not None and weight is not None and math.isfinite(value) and weight > 0
    ]
    if not pairs:
        return None
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total_weight
