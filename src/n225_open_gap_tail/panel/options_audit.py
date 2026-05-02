from __future__ import annotations

from datetime import datetime

from n225_open_gap_tail.config.runtime import (
    MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE,
    PIPELINE_CONFIG,
)
from n225_open_gap_tail.config.settings import Settings


def build_options_source_audit_records(
    *,
    settings: Settings,
    run_ts: datetime,
) -> list[dict[str, object]]:
    historical_enabled = bool(settings.massive_options_historical_enabled)
    flat_files_enabled = bool(settings.massive_options_flat_files_enabled)
    contract_rest_enabled = bool(settings.massive_options_contract_rest_enabled)
    jquants_nikkei_enabled = bool(settings.jquants_nikkei225_options_enabled)
    source_status = (
        "enabled_pending_entitlement_smoke"
        if historical_enabled and (flat_files_enabled or contract_rest_enabled)
        else "disabled_pending_historical_options_entitlement_audit"
    )
    return [
        {
            "source_name": "massive_options_snapshot",
            "source_role": "live_snapshot_not_historical_backfill",
            "audit_status": "excluded_from_historical_backfill",
            "historical_iv_greeks_oi_available": False,
            "headline_promotion_allowed": False,
            "reason": "snapshot_endpoint_is_current_chain_state_not_a_historical_feature_source",
            "run_ts_utc": run_ts,
        },
        {
            "source_name": "massive_options_historical_flat_files",
            "source_role": "candidate_historical_options_source",
            "audit_status": source_status if flat_files_enabled else "disabled_by_runtime_config",
            "historical_iv_greeks_oi_available": None,
            "headline_promotion_allowed": False,
            "reason": (
                "requires_explicit_flat_file_header_and_entitlement_verification_before_panel_use"
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
            "headline_promotion_allowed": jquants_nikkei_enabled,
            "reason": (
                "used_only_as_prior_available_n225_large_option_aggregates; "
                "same_target_date_option_rows_are_not_used"
            ),
            "run_ts_utc": run_ts,
        },
    ]


def build_options_feature_coverage_records(*, settings: Settings) -> list[dict[str, object]]:
    configured = (
        settings.massive_options_underlying_list() or MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE
    )
    headline_feature_cap = PIPELINE_CONFIG.feature_engineering.options_headline_feature_cap
    return [
        {
            "source_block": "options_risk",
            "feature_family": "option_us_core",
            "underlyings": ",".join(MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
        {
            "source_block": "options_risk",
            "feature_family": "option_japan_etf",
            "underlyings": ",".join(MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
        {
            "source_block": "options_risk",
            "feature_family": "option_japan_adr_aggregate",
            "underlyings": ",".join(MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE),
            "configured_underlyings": ",".join(configured),
            "headline_feature_cap": headline_feature_cap,
            "feature_status": "disabled_until_historical_options_source_audit_passes",
            "first_valid_date": None,
            "missingness_rate": None,
        },
    ]


def build_options_liquidity_audit_records(*, settings: Settings) -> list[dict[str, object]]:
    configured = (
        settings.massive_options_underlying_list() or MASSIVE_OPTIONS_UNDERLYINGS_FOR_PIPELINE
    )
    feature_policy = PIPELINE_CONFIG.feature_engineering
    primary = {
        *MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
        *MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    }
    records: list[dict[str, object]] = []
    for underlying in configured:
        records.append(
            {
                "underlying": underlying,
                "source_block": "options_risk",
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
