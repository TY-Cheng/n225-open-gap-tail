from __future__ import annotations

_MODEL_DISPLAY_LABELS = {
    "historical_quantile": "Historical quantile",
    "rolling_quantile": "Rolling quantile",
    "ewma_vol_scaled": "EWMA volatility scaling",
    "garch_t": "GARCH-t",
    "gjr_garch_t": "GJR-GARCH-t",
    "gjr_garch_evt": "GJR-GARCH-EVT",
    "caviar_sav": "CAViaR SAV",
    "caviar_asymmetric_slope": "CAViaR asymmetric slope",
    "care_expectile_sav": "CARE expectile SAV",
    "care_expectile_asymmetric_slope": "CARE expectile asymmetric slope",
    "gas_t_location_scale": "GAS-t location-scale",
    "gas_t_pot_gpd": "GAS-t POT-GPD",
    "lightgbm_direct_quantile": "LightGBM direct quantile",
    "lightgbm_location_scale_empirical": "LightGBM empirical location-scale",
    "lightgbm_standardized_loss_pot_gpd_plain_mle": "LightGBM mean/scale POT-GPD MLE",
    "lightgbm_standardized_loss_pot_gpd_unibm": "LightGBM mean/scale POT-GPD UniBM",
    "lightgbm_median_mad_pot_gpd_plain_mle": "LightGBM median/MAD POT-GPD MLE",
    "lightgbm_median_mad_pot_gpd_unibm": "LightGBM median/MAD POT-GPD UniBM",
    "lightgbm_median_iqr_pot_gpd_plain_mle": "LightGBM median/IQR POT-GPD MLE",
    "lightgbm_median_iqr_pot_gpd_unibm": "LightGBM median/IQR POT-GPD UniBM",
}

_STATUS_DISPLAY_LABELS = {
    "completed_lightgbm_ml_tail_models": "completed LightGBM forecasts",
}

_INFORMATION_SET_DISPLAY_LABELS = {
    "target_history_only": "Lagged opening-gap losses",
    "japan_only": "A: Japan only",
    "japan_only_plus_us_close_core": "B: +U.S.-close core",
    "japan_only_plus_us_close_core_plus_japan_proxy": "C: +Japan proxy",
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy": ("D: +Asia proxy"),
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy_plus_options_risk": (
        "E: +U.S.-listed options"
    ),
}

_TAIL_SIDE_DISPLAY_LABELS = {
    "left_tail": "Downside",
    "right_tail": "Upside",
}

_SUITE_GROUP_DISPLAY_LABELS = {
    "benchmark": "Benchmark",
    "benchmark_baseline": "Baseline benchmark",
    "benchmark_advanced": "Advanced econometric benchmark",
    "ml_tail": "LightGBM",
    "ml_tail_primary": "LightGBM direct-quantile forecast",
    "ml_tail_restricted_family": "LightGBM filtered-tail family",
}

_SOURCE_BLOCK_DISPLAY_LABELS = {
    "target_history": "Lagged opening-gap losses",
    "target_history_only": "Lagged opening-gap losses",
    "japan_history": "Japan history",
    "japan_only": "Japan only",
    "japan_proxy": "Japan proxy",
    "japan_proxy_options": "Japan proxy options",
    "jquants_nikkei_options": "J-Quants Nikkei 225 options",
    "us_close_core": "U.S.-close core",
    "us_core": "U.S. core",
    "us_late_session": "U.S. late session",
    "us_core_options": "U.S. core options",
    "asia_proxy": "Asia proxy",
    "asia_proxy_options": "Asia proxy options",
    "fred_credit_enriched": "FRED credit enriched",
    "options_risk": "Options risk",
    "massive_daily": "Massive daily",
    "massive_minute": "Massive intraday",
    "massive_optional": "Massive cross-asset ETF",
    "cross_market_derived": "Derived cross-market",
    "calendar_controls": "Calendar controls",
    "event_calendar": "Event calendar",
    "fx_core": "Foreign exchange",
    "cboe_volatility": "Cboe volatility",
    "fred_core": "FRED",
}


def display_model_label(value: object) -> str:
    """Return paper-facing model labels while preserving raw artifact keys elsewhere."""
    text = "" if value is None else str(value)
    return _MODEL_DISPLAY_LABELS.get(text, text)


def display_status_label(value: object) -> str:
    text = "" if value is None else str(value)
    return _STATUS_DISPLAY_LABELS.get(text, text)


def display_information_set_label(value: object) -> str:
    """Return compact paper-facing information-set labels."""
    text = "" if value is None else str(value)
    return _INFORMATION_SET_DISPLAY_LABELS.get(text, text)


def display_tail_side_label(value: object) -> str:
    """Return the economic exposure label for an internal tail-side key."""
    text = "" if value is None else str(value)
    return _TAIL_SIDE_DISPLAY_LABELS.get(text, text.replace("_", " "))


def display_suite_group_label(value: object) -> str:
    """Return paper-facing labels for report-suite group keys."""
    text = "" if value is None else str(value)
    return _SUITE_GROUP_DISPLAY_LABELS.get(text, text.replace("_", " "))


def display_source_block_label(value: object) -> str:
    """Return compact paper-facing source-block labels."""
    text = "" if value is None else str(value)
    return _SOURCE_BLOCK_DISPLAY_LABELS.get(text, text)
