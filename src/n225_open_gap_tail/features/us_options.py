from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from n225_open_gap_tail.config.runtime import (
    MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
    PIPELINE_CONFIG,
    _optional_float,
)
from n225_open_gap_tail.features.asof import (
    _coerce_datetime,
    _fred_feature_candidate_asof,
    _fred_feature_map,
)
from n225_open_gap_tail.features.descriptions import _safe_name
from n225_open_gap_tail.sources.massive_flatfiles import (
    ParsedOpraOptionTicker as ParsedOpraOptionTicker,
)
from n225_open_gap_tail.sources.massive_flatfiles import (
    normalize_massive_options_day_agg_rows as normalize_massive_options_day_agg_rows,
)
from n225_open_gap_tail.sources.massive_flatfiles import (
    parse_opra_option_ticker as parse_opra_option_ticker,
)

US_OPTIONS_IV_METHOD = "black_scholes_european_dgs2_zero_dividend_from_day_aggs_close"
US_OPTIONS_RISK_FREE_SOURCE = "fred_dgs2_latest_timestamp_safe"
US_OPTIONS_HEADLINE_FEATURES: tuple[str, ...] = (
    "option_us_core_spy_atm_iv_short",
    "option_us_core_spy_atm_iv_medium",
    "option_us_core_spy_atm_iv_term_slope",
    "option_us_core_qqq_atm_iv_short",
    "option_us_core_qqq_atm_iv_medium",
    "option_us_core_qqq_atm_iv_term_slope",
    "option_us_core_dia_atm_iv_short",
    "option_us_core_dia_atm_iv_medium",
    "option_us_core_dia_atm_iv_term_slope",
    "option_us_core_iwm_atm_iv_short",
    "option_us_core_iwm_atm_iv_medium",
    "option_us_core_iwm_atm_iv_term_slope",
    "option_us_sector_median_atm_iv_short",
    "option_us_sector_median_atm_iv_medium",
    "option_us_sector_atm_iv_term_slope",
    "option_us_sector_atm_iv_dispersion_short",
    "option_us_sector_atm_iv_dispersion_medium",
    "option_us_sector_max_atm_iv_short",
    "option_us_sector_max_atm_iv_medium",
    "option_us_sector_valid_underlying_count_short",
    "option_us_sector_valid_underlying_count_medium",
    "option_japan_etf_ewj_atm_iv_short",
    "option_japan_etf_ewj_atm_iv_medium",
    "option_japan_etf_ewj_atm_iv_term_slope",
    "option_japan_etf_dxj_atm_iv_short",
    "option_japan_etf_dxj_atm_iv_medium",
    "option_japan_etf_dxj_atm_iv_term_slope",
    "option_japan_adr_median_atm_iv_short",
    "option_japan_adr_median_atm_iv_medium",
    "option_japan_adr_trimmed_mean_atm_iv_short",
    "option_japan_adr_trimmed_mean_atm_iv_medium",
    "option_japan_adr_atm_iv_term_slope",
    "option_japan_adr_valid_underlying_count_short",
    "option_japan_adr_valid_underlying_count_medium",
    "option_asia_proxy_median_atm_iv_short",
    "option_asia_proxy_median_atm_iv_medium",
    "option_asia_proxy_atm_iv_term_slope",
    "option_asia_proxy_max_atm_iv_short",
    "option_asia_proxy_max_atm_iv_medium",
    "option_asia_proxy_valid_underlying_count_short",
    "option_asia_proxy_valid_underlying_count_medium",
)


@dataclass(frozen=True)
class UsOptionsAtmIvBuildResult:
    feature_records: list[dict[str, object]]
    liquidity_records: list[dict[str, object]]


def build_us_options_atm_iv_feature_records(
    *,
    option_rows: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
) -> UsOptionsAtmIvBuildResult:
    official_close_by_date = {
        str(row["calendar_date"]): _coerce_datetime(row.get("us_close_ts_utc"))
        for row in calendar_records
        if row.get("us_close_ts_utc") is not None
    }
    spot_by_ticker_date = _spot_close_by_ticker_date(massive_daily_records)
    fred_features = _fred_feature_map(fred_records)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in option_rows:
        grouped.setdefault((str(row["bar_date_et"]), str(row["underlying"]).upper()), []).append(
            row
        )

    feature_records: list[dict[str, object]] = []
    liquidity_records: list[dict[str, object]] = []
    for date_key in sorted({date_key for date_key, _ in grouped}):
        official_close = official_close_by_date.get(date_key)
        if official_close is None:
            continue
        available_ts = official_close + timedelta(
            minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes
        )
        risk_free_rate = _risk_free_rate_for_date(
            fred_features,
            date_key=date_key,
            cutoff=available_ts,
        )
        output: dict[str, object] = {
            "bar_date_et": date_key,
            "feature_available_ts_utc": available_ts,
            "iv_method": US_OPTIONS_IV_METHOD,
            "risk_free_source": US_OPTIONS_RISK_FREE_SOURCE,
        }
        per_underlying_iv: dict[str, dict[str, float | None]] = {}
        for underlying in _headline_underlyings():
            spot = spot_by_ticker_date.get((underlying, date_key))
            iv_by_bucket, audit_rows = _underlying_bucket_ivs(
                rows=grouped.get((date_key, underlying), []),
                underlying=underlying,
                spot=spot,
                risk_free_rate=risk_free_rate,
                date_key=date_key,
                available_ts=available_ts,
            )
            per_underlying_iv[underlying] = iv_by_bucket
            liquidity_records.extend(audit_rows)
            _stamp_underlying_features(output, underlying=underlying, iv_by_bucket=iv_by_bucket)
        _stamp_iv_aggregate_features(
            output,
            per_underlying_iv=per_underlying_iv,
            underlyings=MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
            prefix="option_us_sector",
            include_dispersion=True,
        )
        _stamp_adr_aggregate_features(output, per_underlying_iv)
        _stamp_iv_aggregate_features(
            output,
            per_underlying_iv=per_underlying_iv,
            underlyings=MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
            prefix="option_asia_proxy",
            include_dispersion=False,
        )
        for feature in US_OPTIONS_HEADLINE_FEATURES:
            output.setdefault(feature, None)
        feature_records.append(output)
    return UsOptionsAtmIvBuildResult(
        feature_records=feature_records,
        liquidity_records=liquidity_records,
    )


def black_scholes_price(
    *,
    spot: float,
    strike: float,
    rate: float,
    time_to_expiry: float,
    sigma: float,
    option_type: str,
) -> float | None:
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or sigma <= 0:
        return None
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * time_to_expiry) / (
        sigma * sqrt_t
    )
    d2 = d1 - sigma * sqrt_t
    discount = math.exp(-rate * time_to_expiry)
    if option_type.upper() == "C":
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    if option_type.upper() == "P":
        return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return None


def implied_volatility_from_price(
    *,
    option_price: float,
    spot: float,
    strike: float,
    rate: float,
    time_to_expiry: float,
    option_type: str,
    sigma_bounds: tuple[float, float] = (1e-4, 5.0),
) -> float | None:
    if option_price <= 0 or spot <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None
    low, high = sigma_bounds
    low_price = black_scholes_price(
        spot=spot,
        strike=strike,
        rate=rate,
        time_to_expiry=time_to_expiry,
        sigma=low,
        option_type=option_type,
    )
    high_price = black_scholes_price(
        spot=spot,
        strike=strike,
        rate=rate,
        time_to_expiry=time_to_expiry,
        sigma=high,
        option_type=option_type,
    )
    if low_price is None or high_price is None:
        return None
    tolerance = 1e-10
    if option_price < low_price - tolerance or option_price > high_price + tolerance:
        return None
    left, right = low, high
    for _ in range(100):
        midpoint = 0.5 * (left + right)
        midpoint_price = black_scholes_price(
            spot=spot,
            strike=strike,
            rate=rate,
            time_to_expiry=time_to_expiry,
            sigma=midpoint,
            option_type=option_type,
        )
        if midpoint_price is None:
            return None
        if abs(midpoint_price - option_price) <= 1e-8:
            return midpoint
        if midpoint_price < option_price:
            left = midpoint
        else:
            right = midpoint
    return 0.5 * (left + right)


def _underlying_bucket_ivs(
    *,
    rows: list[dict[str, object]],
    underlying: str,
    spot: float | None,
    risk_free_rate: float | None,
    date_key: str,
    available_ts: datetime,
) -> tuple[dict[str, float | None], list[dict[str, object]]]:
    buckets = {
        "short": PIPELINE_CONFIG.feature_engineering.options_dte_short_bucket,
        "medium": PIPELINE_CONFIG.feature_engineering.options_dte_medium_bucket,
    }
    iv_by_bucket: dict[str, float | None] = {"short": None, "medium": None}
    audit_rows: list[dict[str, object]] = []
    for bucket_name, (lower, upper) in buckets.items():
        candidates = [
            row
            for row in rows
            if (dte := _optional_int(row.get("dte"))) is not None
            and lower <= dte <= upper
            and _optional_float(row.get("volume")) is not None
            and (_optional_float(row.get("volume")) or 0.0) > 0
            and _optional_float(row.get("transactions")) is not None
            and (_optional_float(row.get("transactions")) or 0.0) > 0
            and _optional_float(row.get("close")) is not None
        ]
        selected_ivs: list[float] = []
        selected_rows: list[dict[str, object]] = []
        if spot is not None and spot > 0 and risk_free_rate is not None:
            for option_type in ("C", "P"):
                selected = _nearest_atm_candidate(
                    [
                        row
                        for row in candidates
                        if str(row.get("option_type") or "").upper() == option_type
                    ],
                    spot=spot,
                )
                if selected is None:
                    continue
                iv = implied_volatility_from_price(
                    option_price=float(_optional_float(selected.get("close")) or 0.0),
                    spot=spot,
                    strike=float(_optional_float(selected.get("strike")) or 0.0),
                    rate=risk_free_rate,
                    time_to_expiry=max(1, _optional_int(selected.get("dte")) or 0) / 365.25,
                    option_type=option_type,
                )
                if iv is not None:
                    selected_ivs.append(iv)
                    selected_rows.append(selected)
        iv_by_bucket[bucket_name] = _median(selected_ivs)
        audit_rows.append(
            {
                "bar_date_et": date_key,
                "underlying": underlying,
                "source_block": _underlying_source_block(underlying),
                "dte_bucket": bucket_name,
                "feature_available_ts_utc": available_ts,
                "valid_contract_count": len(candidates),
                "selected_contract_count": len(selected_rows),
                "iv_count": len(selected_ivs),
                "total_volume": _safe_sum(row.get("volume") for row in candidates),
                "total_transactions": _safe_sum(row.get("transactions") for row in candidates),
                "spot_available": spot is not None,
                "risk_free_available": risk_free_rate is not None,
                "liquidity_status": "ok" if selected_ivs else "no_valid_atm_iv",
                "headline_promotion_allowed": bool(selected_ivs),
            }
        )
    return iv_by_bucket, audit_rows


def _nearest_atm_candidate(
    rows: list[dict[str, object]],
    *,
    spot: float,
) -> dict[str, object] | None:
    candidates: list[tuple[float, dict[str, object]]] = []
    for row in rows:
        strike = _optional_float(row.get("strike"))
        if strike is None or strike <= 0:
            continue
        candidates.append((abs(math.log(strike / spot)), row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], abs(_optional_int(item[1].get("dte")) or 10_000)))
    return candidates[0][1]


def _stamp_underlying_features(
    output: dict[str, object],
    *,
    underlying: str,
    iv_by_bucket: Mapping[str, float | None],
) -> None:
    safe = _safe_name(underlying)
    if underlying in MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE:
        prefix = f"option_us_core_{safe}"
    elif underlying in MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE:
        prefix = f"option_japan_etf_{safe}"
    else:
        return
    short_iv = iv_by_bucket.get("short")
    medium_iv = iv_by_bucket.get("medium")
    output[f"{prefix}_atm_iv_short"] = short_iv
    output[f"{prefix}_atm_iv_medium"] = medium_iv
    output[f"{prefix}_atm_iv_term_slope"] = (
        None if short_iv is None or medium_iv is None else medium_iv - short_iv
    )


def _underlying_source_block(underlying: str) -> str:
    ticker = underlying.upper()
    if (
        ticker in MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE
        or ticker in MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE
    ):
        return "us_core"
    if (
        ticker in MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE
        or ticker in MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE
    ):
        return "japan_proxy"
    if ticker in MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE:
        return "asia_proxy"
    return "options_unregistered"


def _stamp_adr_aggregate_features(
    output: dict[str, object],
    per_underlying_iv: Mapping[str, Mapping[str, float | None]],
) -> None:
    short_values = [
        value
        for underlying in MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE
        if (value := per_underlying_iv.get(underlying, {}).get("short")) is not None
    ]
    medium_values = [
        value
        for underlying in MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE
        if (value := per_underlying_iv.get(underlying, {}).get("medium")) is not None
    ]
    short_median = _median(short_values)
    medium_median = _median(medium_values)
    output["option_japan_adr_median_atm_iv_short"] = short_median
    output["option_japan_adr_median_atm_iv_medium"] = medium_median
    output["option_japan_adr_trimmed_mean_atm_iv_short"] = _trimmed_mean(short_values)
    output["option_japan_adr_trimmed_mean_atm_iv_medium"] = _trimmed_mean(medium_values)
    output["option_japan_adr_atm_iv_term_slope"] = (
        None if short_median is None or medium_median is None else medium_median - short_median
    )
    output["option_japan_adr_valid_underlying_count_short"] = float(len(short_values))
    output["option_japan_adr_valid_underlying_count_medium"] = float(len(medium_values))


def _stamp_iv_aggregate_features(
    output: dict[str, object],
    *,
    per_underlying_iv: Mapping[str, Mapping[str, float | None]],
    underlyings: tuple[str, ...],
    prefix: str,
    include_dispersion: bool,
) -> None:
    short_values = _bucket_values(per_underlying_iv, underlyings=underlyings, bucket="short")
    medium_values = _bucket_values(per_underlying_iv, underlyings=underlyings, bucket="medium")
    short_median = _median(short_values)
    medium_median = _median(medium_values)
    output[f"{prefix}_median_atm_iv_short"] = short_median
    output[f"{prefix}_median_atm_iv_medium"] = medium_median
    output[f"{prefix}_atm_iv_term_slope"] = (
        None if short_median is None or medium_median is None else medium_median - short_median
    )
    output[f"{prefix}_max_atm_iv_short"] = _max_or_none(short_values)
    output[f"{prefix}_max_atm_iv_medium"] = _max_or_none(medium_values)
    output[f"{prefix}_valid_underlying_count_short"] = float(len(short_values))
    output[f"{prefix}_valid_underlying_count_medium"] = float(len(medium_values))
    if include_dispersion:
        output[f"{prefix}_atm_iv_dispersion_short"] = _std_or_none(short_values)
        output[f"{prefix}_atm_iv_dispersion_medium"] = _std_or_none(medium_values)


def _bucket_values(
    per_underlying_iv: Mapping[str, Mapping[str, float | None]],
    *,
    underlyings: tuple[str, ...],
    bucket: str,
) -> list[float]:
    return [
        value
        for underlying in underlyings
        if (value := per_underlying_iv.get(underlying, {}).get(bucket)) is not None
    ]


def _spot_close_by_ticker_date(records: list[dict[str, object]]) -> dict[tuple[str, str], float]:
    output: dict[tuple[str, str], float] = {}
    for row in records:
        ticker = str(row.get("ticker") or "").upper()
        date_key = str(row.get("bar_date_et") or "")
        close = _optional_float(row.get("close"))
        if ticker and date_key and close is not None and close > 0:
            output[(ticker, date_key)] = close
    return output


def _risk_free_rate_for_date(
    fred_features: dict[str, dict[str, object]],
    *,
    date_key: str,
    cutoff: datetime,
) -> float | None:
    selected = _fred_feature_candidate_asof(
        fred_features,
        date_key=date_key,
        feature_name="fred_dgs2_level",
        cutoff=cutoff,
    )
    if selected is None:
        return None
    value = _optional_float(selected.get("value"))
    return None if value is None else value / 100.0


def _headline_underlyings() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
            )
        )
    )


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _optional_int(value: object) -> int | None:
    parsed = _optional_float(value)
    return None if parsed is None else int(parsed)


def _median(values: list[float]) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return None if not finite else float(np.median(finite))


def _trimmed_mean(values: list[float]) -> float | None:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return None
    trim = int(len(finite) * 0.2)
    trimmed = finite[trim : len(finite) - trim] if len(finite) - 2 * trim > 0 else finite
    return float(np.mean(trimmed))


def _max_or_none(values: list[float]) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return None if not finite else max(finite)


def _std_or_none(values: list[float]) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if len(finite) < 2:
        return None
    return float(np.std(finite, ddof=0))


def _safe_sum(values: Iterable[object]) -> float:
    total = 0.0
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            total += parsed
    return total


__all__ = [name for name in globals() if not name.startswith("_")]
