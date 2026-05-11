# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
    CORE_MASSIVE_TICKERS_FOR_PIPELINE,
    JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
    MASSIVE_MINUTE_ASIA_PROXY_TICKERS_FOR_PIPELINE,
    MASSIVE_MINUTE_JAPAN_PROXY_TICKERS_FOR_PIPELINE,
    MASSIVE_MINUTE_US_CORE_TICKERS_FOR_PIPELINE,
    OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE,
)
from n225_open_gap_tail.features.descriptions import _safe_name


def _feature_dictionary_includes(field: str) -> bool:
    if "__" in field:
        return False
    return (
        field.startswith("n225_")
        or field.startswith("event_")
        or field.startswith("xmarket_")
        or field.startswith("option_")
        or field.endswith("_return")
        or field.endswith("_range")
        or field.endswith("_diff")
        or field.endswith("_days")
        or field.endswith("_var")
        or field.endswith("_semivar")
        or field.endswith("_skew")
        or field.endswith("_kurtosis")
        or field.endswith("_volume_surge")
        or field.endswith("_window_momentum")
        or field.endswith("_count")
        or "_zscore_" in field
        or "_percentile_" in field
        or field.startswith("fred_")
        or field.startswith("cboe_")
    )


def _feature_source_family(field: str) -> str:
    if field.startswith("event_"):
        return "event_calendar"
    if field.startswith("xmarket_"):
        return "cross_market_derived"
    if field.startswith("n225_option_"):
        return "jquants_nikkei_options"
    if field.startswith("n225_"):
        return "japan_history"
    if field.startswith("option_us_core_") or field.startswith("option_us_sector_"):
        return "us_core_options"
    if field.startswith("option_japan_etf_") or field.startswith("option_japan_adr_"):
        return "japan_proxy_options"
    if field.startswith("option_asia_proxy_"):
        return "asia_proxy_options"
    if field.startswith("japan_adr_"):
        return "japan_proxy"
    if field.startswith("fx_usdjpy_"):
        return "fx_core"
    if field.startswith("fred_"):
        if field.startswith("fred_baml"):
            return "fred_credit_enriched"
        return "fred_core"
    if field.startswith("cboe_"):
        return "cboe_volatility"
    minute_block = _minute_feature_source_block(field)
    if minute_block is not None:
        return "massive_minute"
    if _feature_matches_tickers(field, OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE):
        return "massive_optional"
    if _feature_matches_tickers(field, JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "japan_proxy"
    if _feature_matches_tickers(field, ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "asia_proxy"
    if field.endswith("_return") or field.endswith("_range"):
        return "massive_daily"
    return "unknown"


def _feature_source_block(field: str) -> str:
    if field.startswith("event_"):
        return "calendar_controls"
    if field.startswith("xmarket_us_"):
        return "us_core"
    if field.startswith("xmarket_vix_"):
        return "fred_core"
    if field.startswith("xmarket_japan_proxy_"):
        return "japan_proxy"
    if field.startswith("xmarket_asia_proxy_"):
        return "asia_proxy"
    if field.startswith("n225_option_"):
        return "japan_only"
    if field.startswith("n225_"):
        return "japan_only"
    if field.startswith("option_us_core_") or field.startswith("option_us_sector_"):
        return "us_core"
    if field.startswith("option_japan_etf_") or field.startswith("option_japan_adr_"):
        return "japan_proxy"
    if field.startswith("option_asia_proxy_"):
        return "asia_proxy"
    if field.startswith("japan_adr_"):
        return "japan_proxy"
    if field.startswith("fx_usdjpy_"):
        return "fx_core"
    if field.startswith("fred_"):
        if field.startswith("fred_baml"):
            return "fred_credit_enriched"
        return "fred_core"
    if field.startswith("cboe_"):
        return "fred_core"
    minute_block = _minute_feature_source_block(field)
    if minute_block is not None:
        return minute_block
    if _feature_matches_tickers(field, OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE):
        return "massive_optional"
    if _feature_matches_tickers(field, JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "japan_proxy"
    if _feature_matches_tickers(field, ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "asia_proxy"
    if _feature_matches_tickers(field, CORE_MASSIVE_TICKERS_FOR_PIPELINE):
        return "us_core"
    return "unknown"


def _feature_matches_tickers(field: str, tickers: tuple[str, ...]) -> bool:
    return any(field.startswith(f"{_safe_name(ticker)}_") for ticker in tickers)


def _minute_feature_source_block(field: str) -> str | None:
    if not _looks_like_minute_feature(field):
        return None
    if _feature_matches_tickers(field, MASSIVE_MINUTE_US_CORE_TICKERS_FOR_PIPELINE):
        return "us_late_session"
    if _feature_matches_tickers(field, MASSIVE_MINUTE_JAPAN_PROXY_TICKERS_FOR_PIPELINE):
        return "japan_proxy"
    if _feature_matches_tickers(field, MASSIVE_MINUTE_ASIA_PROXY_TICKERS_FOR_PIPELINE):
        return "asia_proxy"
    return None


def _looks_like_minute_feature(field: str) -> bool:
    return (
        "_late_" in field
        or field.endswith("_late_session_range")
        or field.endswith("_late_volume_surge")
        or field.endswith("_final_window_momentum")
    )
