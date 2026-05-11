from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

from n225_open_gap_tail.config.runtime import _optional_float

XMARKET_FEATURES = (
    "xmarket_us_core_return_mean_1d",
    "xmarket_us_sector_return_dispersion_1d",
    "xmarket_vix_shock_20d",
    "xmarket_vix_shock_zscore_60d",
    "xmarket_japan_proxy_ewj_spy_spread_1d",
    "xmarket_japan_proxy_dxj_spy_spread_1d",
    "xmarket_asia_proxy_return_dispersion_1d",
)

US_CORE_RETURN_FEATURES = ("spy_return", "qqq_return", "dia_return", "iwm_return")
US_SECTOR_RETURN_FEATURES = (
    "xlk_return",
    "xlf_return",
    "xle_return",
    "xlv_return",
    "xli_return",
    "xly_return",
    "xlp_return",
    "xlb_return",
    "xlu_return",
    "xlc_return",
)
ASIA_PROXY_RETURN_FEATURES = (
    "eem_return",
    "fxi_return",
    "ewy_return",
    "ewt_return",
    "ewh_return",
)


def add_cross_market_features(panel_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Add deterministic cross-market features from already timestamped panel inputs."""
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    output: list[dict[str, object]] = []
    prior_vix_closes: list[dict[str, object]] = []
    prior_vix_diffs: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        current_vix = _optional_float(enriched.get("cboe_vix_close"))
        previous_vix = (
            _optional_float(prior_vix_closes[-1].get("value")) if prior_vix_closes else None
        )
        current_vix_diff = (
            None if current_vix is None or previous_vix is None else current_vix - previous_vix
        )

        _stamp_aggregate_feature(
            enriched,
            "xmarket_us_core_return_mean_1d",
            _mean_components(enriched, US_CORE_RETURN_FEATURES, min_components=3),
            US_CORE_RETURN_FEATURES,
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_us_sector_return_dispersion_1d",
            _sample_std_components(enriched, US_SECTOR_RETURN_FEATURES, min_components=6),
            US_SECTOR_RETURN_FEATURES,
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_vix_shock_20d",
            _current_minus_prior_mean(
                current_vix,
                [item.get("value") for item in prior_vix_closes[-20:]],
                min_periods=20,
            ),
            ("cboe_vix_close",),
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_vix_shock_zscore_60d",
            _current_minus_prior_zscore(
                current_vix_diff,
                [item.get("value") for item in prior_vix_diffs[-60:]],
                min_periods=20,
            ),
            ("cboe_vix_close",),
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_japan_proxy_ewj_spy_spread_1d",
            _difference(enriched.get("ewj_return"), enriched.get("spy_return")),
            ("ewj_return", "spy_return"),
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_japan_proxy_dxj_spy_spread_1d",
            _difference(enriched.get("dxj_return"), enriched.get("spy_return")),
            ("dxj_return", "spy_return"),
        )
        _stamp_aggregate_feature(
            enriched,
            "xmarket_asia_proxy_return_dispersion_1d",
            _sample_std_components(enriched, ASIA_PROXY_RETURN_FEATURES, min_components=3),
            ASIA_PROXY_RETURN_FEATURES,
        )

        output.append(enriched)
        if enriched.get("clean_sample") is True and current_vix is not None:
            prior_vix_closes.append(
                {
                    "value": current_vix,
                    "source_date": enriched.get("cboe_vix_close__source_date"),
                    "available_ts_utc": _coerce_datetime(
                        enriched.get("cboe_vix_close__available_ts_utc")
                    ),
                }
            )
            if current_vix_diff is not None:
                prior_vix_diffs.append(
                    {
                        "value": current_vix_diff,
                        "source_date": enriched.get("cboe_vix_close__source_date"),
                        "available_ts_utc": _coerce_datetime(
                            enriched.get("cboe_vix_close__available_ts_utc")
                        ),
                    }
                )
    return output


def _mean_components(
    row: dict[str, object],
    component_features: tuple[str, ...],
    *,
    min_components: int,
) -> float | None:
    values = _finite_component_values(row, component_features)
    if len(values) < min_components:
        return None
    return float(np.mean(values))


def _sample_std_components(
    row: dict[str, object],
    component_features: tuple[str, ...],
    *,
    min_components: int,
) -> float | None:
    values = _finite_component_values(row, component_features)
    if len(values) < min_components:
        return None
    return float(np.std(values, ddof=1))


def _current_minus_prior_mean(
    value: float | None,
    prior_values: list[object],
    *,
    min_periods: int,
) -> float | None:
    prior = _finite_values(prior_values)
    if value is None or len(prior) < min_periods:
        return None
    return value - float(np.mean(prior))


def _current_minus_prior_zscore(
    value: float | None,
    prior_values: list[object],
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


def _difference(first: object, second: object) -> float | None:
    first_value = _optional_float(first)
    second_value = _optional_float(second)
    if first_value is None or second_value is None:
        return None
    return first_value - second_value


def _finite_component_values(
    row: dict[str, object],
    component_features: tuple[str, ...],
) -> list[float]:
    return _finite_values([row.get(feature) for feature in component_features])


def _finite_values(values: list[object]) -> list[float]:
    parsed = [_optional_float(value) for value in values]
    return [float(value) for value in parsed if value is not None and math.isfinite(value)]


def _stamp_aggregate_feature(
    row: dict[str, object],
    feature_name: str,
    value: object,
    component_features: tuple[str, ...],
) -> None:
    row[feature_name] = value if _is_finite_or_none(value) else None
    row[f"{feature_name}__fill_method"] = "derived_panel_aggregate"
    available_values = [
        available_ts
        for feature in component_features
        if row.get(feature) is not None
        if (available_ts := _coerce_datetime(row.get(f"{feature}__available_ts_utc"))) is not None
    ]
    source_dates = [
        str(row.get(f"{feature}__source_date"))
        for feature in component_features
        if row.get(feature) is not None and row.get(f"{feature}__source_date") is not None
    ]
    if available_values:
        row[f"{feature_name}__available_ts_utc"] = max(available_values)
    if source_dates:
        row[f"{feature_name}__source_date"] = max(source_dates)


def _is_finite_or_none(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, int | float):
        return math.isfinite(value)
    return False


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None
