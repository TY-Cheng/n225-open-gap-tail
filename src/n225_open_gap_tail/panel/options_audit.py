from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from n225_open_gap_tail.config.runtime import (
    MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE,
    PIPELINE_CONFIG,
    _optional_float,
)
from n225_open_gap_tail.config.settings import Settings
from n225_open_gap_tail.features.us_options import US_OPTIONS_HEADLINE_FEATURES


def build_options_source_audit_records(
    *,
    settings: Settings,
    run_ts: datetime,
    option_feature_records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    historical_enabled = bool(settings.massive_options_historical_enabled)
    flat_files_enabled = bool(settings.massive_options_flat_files_enabled)
    contract_rest_enabled = bool(settings.massive_options_contract_rest_enabled)
    jquants_nikkei_enabled = bool(settings.jquants_nikkei225_options_enabled)
    source_status = (
        "enabled_computed_iv_proxy_available"
        if historical_enabled and flat_files_enabled and option_feature_records
        else "enabled_pending_entitlement_smoke"
        if historical_enabled and (flat_files_enabled or contract_rest_enabled)
        else "disabled_pending_historical_options_entitlement_audit"
    )
    feature_rows = len(option_feature_records or [])
    return [
        {
            "source_name": "massive_options_snapshot",
            "source_role": "live_snapshot_not_historical_backfill",
            "audit_status": "excluded_from_historical_backfill",
            "historical_iv_greeks_oi_available": False,
            "computed_iv_proxy_available": False,
            "panel_feature_rows": 0,
            "headline_promotion_allowed": False,
            "reason": "snapshot_endpoint_is_current_chain_state_not_a_historical_feature_source",
            "run_ts_utc": run_ts,
        },
        {
            "source_name": "massive_options_historical_flat_files",
            "source_role": "historical_day_agg_source_for_computed_atm_iv",
            "audit_status": source_status if flat_files_enabled else "disabled_by_runtime_config",
            "historical_iv_greeks_oi_available": False,
            "computed_iv_proxy_available": bool(feature_rows),
            "panel_feature_rows": feature_rows,
            "headline_promotion_allowed": False,
            "reason": (
                "day_aggs_have_prices_and_volume_but_no_direct_iv_greeks_oi; "
                "ATM IV is computed with Black-Scholes, DGS2, and zero dividend"
            ),
            "run_ts_utc": run_ts,
        },
        {
            "source_name": "massive_options_contract_rest",
            "source_role": "candidate_contract_level_trades_quotes_aggs_source",
            "audit_status": (
                source_status if contract_rest_enabled else "disabled_by_runtime_config"
            ),
            "historical_iv_greeks_oi_available": False,
            "computed_iv_proxy_available": False,
            "panel_feature_rows": 0,
            "headline_promotion_allowed": False,
            "reason": (
                "contract_level_history_can_support_computed_iv_only_after_small_scope_smoke"
            ),
            "run_ts_utc": run_ts,
        },
        {
            "source_name": "jquants_nikkei_options",
            "source_role": "lagged_domestic_option_implied_state",
            "audit_status": "enabled_lagged_japan_only_features"
            if jquants_nikkei_enabled
            else "disabled_by_runtime_config",
            "historical_iv_greeks_oi_available": True if jquants_nikkei_enabled else None,
            "computed_iv_proxy_available": None,
            "panel_feature_rows": None,
            "headline_promotion_allowed": jquants_nikkei_enabled,
            "reason": (
                "used_only_as_prior_available_n225_large_option_aggregates; "
                "same_target_date_option_rows_are_not_used"
            ),
            "run_ts_utc": run_ts,
        },
    ]


def build_options_feature_coverage_records(
    *,
    settings: Settings,
    option_feature_records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    configured = (
        settings.massive_options_underlying_list() or MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE
    )
    headline_feature_cap = PIPELINE_CONFIG.feature_engineering.options_headline_feature_cap
    if option_feature_records:
        records: list[dict[str, object]] = []
        total = len(option_feature_records)
        for feature in US_OPTIONS_HEADLINE_FEATURES:
            values = [
                _optional_float(row.get(feature))
                for row in option_feature_records
                if _optional_float(row.get(feature)) is not None
            ]
            source_dates = [
                str(row.get("bar_date_et"))
                for row in option_feature_records
                if _optional_float(row.get(feature)) is not None
            ]
            records.append(
                {
                    "source_block": _options_feature_source_block(feature),
                    "feature_family": _options_feature_family(feature),
                    "feature": feature,
                    "underlyings": ",".join(_options_feature_underlyings(feature)),
                    "configured_underlyings": ",".join(configured),
                    "headline_feature_cap": headline_feature_cap,
                    "feature_status": "computed_iv_proxy_available",
                    "valid_count": len(values),
                    "total_rows": total,
                    "first_valid_date": min(source_dates) if source_dates else None,
                    "last_valid_date": max(source_dates) if source_dates else None,
                    "missingness_rate": 1.0 - len(values) / total if total else None,
                }
            )
        return records
    return [
        {
            "source_block": "us_core",
            "feature_family": "option_us_sector_aggregate",
            "underlyings": ",".join(MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_pending_historical_options_source",
            "missingness_rate": None,
        },
        {
            "source_block": "us_core",
            "feature_family": "option_us_core",
            "underlyings": ",".join(MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
        {
            "source_block": "japan_proxy",
            "feature_family": "option_japan_etf",
            "underlyings": ",".join(MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
        {
            "source_block": "japan_proxy",
            "feature_family": "option_japan_adr_aggregate",
            "underlyings": ",".join(MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
        {
            "source_block": "asia_proxy",
            "feature_family": "option_asia_proxy_aggregate",
            "underlyings": ",".join(MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_pending_historical_options_source",
            "missingness_rate": None,
        },
    ]


def build_options_liquidity_audit_records(
    *,
    settings: Settings,
    liquidity_records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    configured = (
        settings.massive_options_underlying_list() or MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE
    )
    feature_policy = PIPELINE_CONFIG.feature_engineering
    primary = {
        *MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    }
    records: list[dict[str, object]] = []
    if liquidity_records:
        grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in liquidity_records:
            grouped.setdefault(
                (str(row.get("underlying") or ""), str(row.get("dte_bucket") or "")),
                [],
            ).append(row)
        for (underlying, bucket), rows in sorted(grouped.items()):
            valid_counts = _finite_values(row.get("valid_contract_count") for row in rows)
            iv_counts = _finite_values(row.get("iv_count") for row in rows)
            volume = _finite_values(row.get("total_volume") for row in rows)
            records.append(
                {
                    "underlying": underlying,
                    "source_block": _underlying_source_block(underlying),
                    "candidate_role": (
                        "headline_candidate" if underlying in primary else "diagnostic"
                    ),
                    "dte_bucket": bucket,
                    "liquidity_status": (
                        "computed_iv_available"
                        if any((value or 0.0) > 0 for value in iv_counts)
                        else "no_valid_atm_iv"
                    ),
                    "dte_short_bucket": list(feature_policy.options_dte_short_bucket),
                    "dte_medium_bucket": list(feature_policy.options_dte_medium_bucket),
                    "atm_policy": feature_policy.options_atm_policy,
                    "aggregation_policy": feature_policy.options_adr_aggregation_policy,
                    "valid_contract_count": max(valid_counts) if valid_counts else None,
                    "median_relative_spread": None,
                    "rolling_volume": sum(volume) if volume else None,
                    "iv_observation_count": sum(iv_counts) if iv_counts else 0.0,
                    "headline_promotion_allowed": any((value or 0.0) > 0 for value in iv_counts),
                }
            )
        return records
    for underlying in configured:
        records.append(
            {
                "underlying": underlying,
                "source_block": _underlying_source_block(underlying),
                "candidate_role": "headline_candidate" if underlying in primary else "diagnostic",
                "liquidity_status": "not_evaluated_no_historical_options_source",
                "dte_short_bucket": list(feature_policy.options_dte_short_bucket),
                "dte_medium_bucket": list(feature_policy.options_dte_medium_bucket),
                "atm_policy": feature_policy.options_atm_policy,
                "aggregation_policy": feature_policy.options_adr_aggregation_policy,
                "valid_contract_count": None,
                "median_relative_spread": None,
                "rolling_volume": None,
                "headline_promotion_allowed": False,
            }
        )
    return records


def _finite_values(values: Iterable[object]) -> list[float]:
    output: list[float] = []
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            output.append(parsed)
    return output


def _options_feature_family(feature: str) -> str:
    if feature.startswith("option_us_core_"):
        return "option_us_core"
    if feature.startswith("option_us_sector_"):
        return "option_us_sector_aggregate"
    if feature.startswith("option_japan_etf_"):
        return "option_japan_etf"
    if feature.startswith("option_asia_proxy_"):
        return "option_asia_proxy_aggregate"
    return "option_japan_adr_aggregate"


def _options_feature_source_block(feature: str) -> str:
    if feature.startswith("option_us_core_") or feature.startswith("option_us_sector_"):
        return "us_core"
    if feature.startswith("option_japan_etf_") or feature.startswith("option_japan_adr_"):
        return "japan_proxy"
    if feature.startswith("option_asia_proxy_"):
        return "asia_proxy"
    return "options_unregistered"


def _options_feature_underlyings(feature: str) -> tuple[str, ...]:
    if feature.startswith("option_us_core_"):
        return MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE
    if feature.startswith("option_us_sector_"):
        return MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE
    if feature.startswith("option_japan_etf_"):
        return MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE
    if feature.startswith("option_asia_proxy_"):
        return MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE
    return MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE


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
