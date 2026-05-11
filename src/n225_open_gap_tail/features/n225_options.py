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
    "n225_option_atm_iv_short_lag_1",
    "n225_option_atm_iv_medium_lag_1",
    "n225_option_iv_term_slope_lag_1",
    "n225_option_atm_put_call_iv_skew_lag_1",
    "n225_option_otm_put_iv_lag_1",
    "n225_option_otm_call_iv_lag_1",
    "n225_option_risk_reversal_lag_1",
    "n225_option_base_volatility_lag_1",
    "n225_option_base_iv_spread_lag_1",
    "n225_option_iv_oi_weighted_lag_1",
    "n225_option_put_call_oi_ratio_lag_1",
    "n225_option_put_call_volume_ratio_lag_1",
    "n225_option_put_oi_share_lag_1",
    "n225_option_put_volume_share_lag_1",
    "n225_option_total_open_interest_log1p_lag_1",
    "n225_option_total_volume_log1p_lag_1",
    "n225_option_oi_log_change_lag_1",
    "n225_option_volume_log_change_lag_1",
    "n225_option_valid_contract_count_lag_1",
    "n225_option_short_valid_contract_count_lag_1",
    "n225_option_medium_valid_contract_count_lag_1",
    "n225_option_days_to_sq_lag_1",
    "n225_option_atm_iv_zscore_20_lag_1",
    "n225_option_atm_iv_change_20_lag_1",
    "n225_option_atm_iv_percentile_60_lag_1",
    "n225_option_night_atm_close_lag_1",
    "n225_option_night_atm_return_lag_1",
    "n225_option_night_atm_range_lag_1",
    "n225_option_night_valid_contract_count_lag_1",
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
    summaries = [row for row in output if row is not None]
    _stamp_rolling_option_state(summaries)
    return summaries


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
            enriched[f"{feature}__fill_method"] = "prior_n225_option_state"
            if latest is not None and latest.get("vendor_available_ts_utc") is not None:
                enriched[f"{feature}__available_ts_utc"] = latest.get("vendor_available_ts_utc")
        output.append(enriched)
    return output


def _daily_option_summary(
    trading_date: str,
    rows: list[dict[str, object]],
) -> dict[str, object] | None:
    policy = PIPELINE_CONFIG.feature_engineering
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
    short_rows = _dte_bucket_rows(trading_date, valid, policy.options_dte_short_bucket)
    medium_rows = _dte_bucket_rows(trading_date, valid, policy.options_dte_medium_bucket)
    atm_rows = _atm_rows(scoped)
    short_atm_rows = _atm_rows(short_rows)
    medium_atm_rows = _atm_rows(medium_rows)
    atm_iv = _safe_median([_optional_float(row.get("implied_volatility")) for row in atm_rows])
    short_atm_iv = _safe_median(
        [_optional_float(row.get("implied_volatility")) for row in short_atm_rows]
    )
    medium_atm_iv = _safe_median(
        [_optional_float(row.get("implied_volatility")) for row in medium_atm_rows]
    )
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
    otm_put_iv = _safe_median(
        [
            _optional_float(row.get("implied_volatility"))
            for row in scoped
            if row.get("put_call") == "put"
            and _moneyness_in_band(row, policy.options_otm_put_moneyness_band)
        ]
    )
    otm_call_iv = _safe_median(
        [
            _optional_float(row.get("implied_volatility"))
            for row in scoped
            if row.get("put_call") == "call"
            and _moneyness_in_band(row, policy.options_otm_call_moneyness_band)
        ]
    )
    base_volatility = _safe_median([_optional_float(row.get("base_volatility")) for row in scoped])
    night_atm_rows = [row for row in atm_rows if _has_valid_night_ohlc(row)]
    night_atm_close = _safe_median(
        [_optional_float(row.get("night_session_close")) for row in night_atm_rows]
    )
    night_atm_return = _safe_median(
        [
            _safe_log_return(row.get("night_session_open"), row.get("night_session_close"))
            for row in night_atm_rows
        ]
    )
    night_atm_range = _safe_median(
        [
            _safe_log_range(row.get("night_session_high"), row.get("night_session_low"))
            for row in night_atm_rows
        ]
    )
    return {
        "trading_date": trading_date,
        "vendor_available_ts_utc": _max_datetime(
            row.get("vendor_available_ts_utc") for row in scoped
        ),
        "atm_iv": atm_iv,
        "atm_iv_short": short_atm_iv,
        "atm_iv_medium": medium_atm_iv,
        "iv_term_slope": None
        if short_atm_iv is None or medium_atm_iv is None
        else medium_atm_iv - short_atm_iv,
        "atm_put_call_iv_skew": None if put_atm is None or call_atm is None else put_atm - call_atm,
        "otm_put_iv": otm_put_iv,
        "otm_call_iv": otm_call_iv,
        "risk_reversal": None
        if otm_put_iv is None or otm_call_iv is None
        else otm_put_iv - otm_call_iv,
        "base_volatility": base_volatility,
        "base_iv_spread": None
        if base_volatility is None or atm_iv is None
        else base_volatility - atm_iv,
        "iv_oi_weighted": _weighted_mean(
            values=[_optional_float(row.get("implied_volatility")) for row in scoped],
            weights=[_optional_float(row.get("open_interest")) for row in scoped],
        ),
        "put_call_oi_ratio": put_oi / call_oi if call_oi > 0 else None,
        "put_call_volume_ratio": put_volume / call_volume if call_volume > 0 else None,
        "put_oi_share": put_oi / total_oi if total_oi > 0 else None,
        "put_volume_share": put_volume / total_volume if total_volume > 0 else None,
        "total_open_interest_log1p": math.log1p(total_oi) if total_oi >= 0 else None,
        "total_volume_log1p": math.log1p(total_volume) if total_volume >= 0 else None,
        "valid_contract_count": float(len(scoped)),
        "short_valid_contract_count": float(len(short_rows)),
        "medium_valid_contract_count": float(len(medium_rows)),
        "days_to_sq": _safe_median(_days_to_sq(trading_date, row) for row in scoped),
        "night_atm_close": night_atm_close,
        "night_atm_return": night_atm_return,
        "night_atm_range": night_atm_range,
        "night_valid_contract_count": float(len(night_atm_rows)),
    }


def _stamp_rolling_option_state(summaries: list[dict[str, object]]) -> None:
    policy = PIPELINE_CONFIG.feature_engineering
    prior: list[dict[str, object]] = []
    for row in summaries:
        atm_iv = _optional_float(row.get("atm_iv"))
        open_interest = _optional_float(row.get("total_open_interest_log1p"))
        volume = _optional_float(row.get("total_volume_log1p"))
        previous = prior[-1] if prior else None
        previous_open_interest = (
            None if previous is None else _optional_float(previous.get("total_open_interest_log1p"))
        )
        previous_volume = (
            None if previous is None else _optional_float(previous.get("total_volume_log1p"))
        )
        change_values = [
            _optional_float(item.get("atm_iv"))
            for item in prior[-policy.options_iv_change_window :]
        ]
        zscore_values = [
            _optional_float(item.get("atm_iv"))
            for item in prior[-policy.options_iv_zscore_window :]
        ]
        percentile_values = [
            _optional_float(item.get("atm_iv"))
            for item in prior[-policy.options_iv_percentile_window :]
        ]
        row["oi_log_change"] = (
            None
            if open_interest is None or previous_open_interest is None
            else open_interest - previous_open_interest
        )
        row["volume_log_change"] = (
            None if volume is None or previous_volume is None else volume - previous_volume
        )
        row["atm_iv_change_20"] = _level_minus_prior_mean(
            atm_iv,
            change_values,
            min_periods=policy.options_iv_rolling_min_periods,
        )
        row["atm_iv_zscore_20"] = _level_vs_prior_zscore(
            atm_iv,
            zscore_values,
            min_periods=policy.options_iv_rolling_min_periods,
        )
        row["atm_iv_percentile_60"] = _level_vs_prior_percentile(
            atm_iv,
            percentile_values,
            min_periods=policy.options_iv_rolling_min_periods,
        )
        prior.append(row)


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


def _dte_bucket_rows(
    trading_date: str,
    rows: list[dict[str, object]],
    bucket: tuple[int, int],
) -> list[dict[str, object]]:
    lower, upper = bucket
    return [
        row
        for row in rows
        if (days_to_sq := _days_to_sq(trading_date, row)) is not None
        and lower <= days_to_sq <= upper
    ]


def _moneyness_in_band(row: dict[str, object], band: tuple[float, float]) -> bool:
    strike = _optional_float(row.get("strike_price"))
    underlying = _optional_float(row.get("underlying_price"))
    if strike is None or underlying is None or underlying <= 0:
        return False
    lower, upper = band
    moneyness = strike / underlying
    return lower <= moneyness <= upper


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


def _has_valid_night_ohlc(row: dict[str, object]) -> bool:
    night_open = _optional_float(row.get("night_session_open"))
    night_high = _optional_float(row.get("night_session_high"))
    night_low = _optional_float(row.get("night_session_low"))
    night_close = _optional_float(row.get("night_session_close"))
    return (
        night_open is not None
        and night_high is not None
        and night_low is not None
        and night_close is not None
        and night_open > 0
        and night_high > 0
        and night_low > 0
        and night_close > 0
        and night_high >= night_low
    )


def _safe_log_return(open_value: object, close_value: object) -> float | None:
    open_price = _optional_float(open_value)
    close_price = _optional_float(close_value)
    if open_price is None or close_price is None or open_price <= 0 or close_price <= 0:
        return None
    return math.log(close_price / open_price)


def _safe_log_range(high_value: object, low_value: object) -> float | None:
    high_price = _optional_float(high_value)
    low_price = _optional_float(low_value)
    if high_price is None or low_price is None or high_price <= 0 or low_price <= 0:
        return None
    if high_price < low_price:
        return None
    return math.log(high_price / low_price)


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


def _finite_values(values: list[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and math.isfinite(value)]


def _level_minus_prior_mean(
    value: float | None,
    prior_values: list[float | None],
    *,
    min_periods: int,
) -> float | None:
    prior = _finite_values(prior_values)
    if value is None or len(prior) < min_periods:
        return None
    return value - float(np.mean(prior))


def _level_vs_prior_zscore(
    value: float | None,
    prior_values: list[float | None],
    *,
    min_periods: int,
) -> float | None:
    prior = _finite_values(prior_values)
    if value is None or len(prior) < min_periods:
        return None
    std = float(np.std(prior, ddof=1))
    if std == 0.0:
        return None
    return (value - float(np.mean(prior))) / std


def _level_vs_prior_percentile(
    value: float | None,
    prior_values: list[float | None],
    *,
    min_periods: int,
) -> float | None:
    prior = _finite_values(prior_values)
    if value is None or len(prior) < min_periods:
        return None
    return sum(1 for item in prior if item <= value) / len(prior)
