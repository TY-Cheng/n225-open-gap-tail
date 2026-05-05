from __future__ import annotations

_MODEL_DISPLAY_LABELS = {
    "lightgbm_direct_quantile": "LGBM direct quantile",
    "lightgbm_location_scale": "LGBM location-scale",
    "lightgbm_location_scale_empirical": "LGBM location-scale empirical",
    "lightgbm_standardized_loss_pot_gpd": "LGBM POT-GPD",
    "lightgbm_standardized_loss_pot_gpd_plain_mle": "LGBM POT-GPD plain MLE",
    "lightgbm_standardized_loss_pot_gpd_capped_mle": "LGBM POT-GPD capped MLE",
    "lightgbm_standardized_loss_pot_gpd_evi_shrink": "LGBM POT-GPD EVI shrink",
    "lightgbm_standardized_loss_pot_gpd_ei_weighted": "LGBM POT-GPD EI-weighted",
    "lightgbm_standardized_loss_pot_gpd_stabilized": "LGBM POT-GPD stabilized",
    "lightgbm_conditional_q90_pot_gpd_plain_mle": "LGBM conditional q90 POT-GPD plain MLE",
    "lightgbm_conditional_q90_pot_gpd_stabilized": "LGBM conditional q90 POT-GPD stabilized",
    "lightgbm_median_mad_pot_gpd_plain_mle": "LGBM median/MAD POT-GPD plain MLE",
    "lightgbm_median_mad_pot_gpd_stabilized": "LGBM median/MAD POT-GPD stabilized",
    "lightgbm_median_iqr_pot_gpd_plain_mle": "LGBM median/IQR POT-GPD plain MLE",
}

_STATUS_DISPLAY_LABELS = {
    "completed_lightgbm_ml_tail_models": "completed LGBM ML-tail models",
}

_INFORMATION_SET_DISPLAY_LABELS = {
    "target_history_only": "Target history",
    "japan_only": "JP only",
    "japan_only_plus_us_close_core": "JP + US close core",
    "japan_only_plus_us_close_core_plus_japan_proxy": "JP + US close core + JP proxy",
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy": (
        "JP + US close core + JP proxy + Asia proxy"
    ),
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy_plus_options_risk": (
        "JP + US close core + JP proxy + Asia proxy + options"
    ),
}

_SOURCE_BLOCK_DISPLAY_LABELS = {
    "target_history": "Target history",
    "target_history_only": "Target history",
    "japan_history": "JP history",
    "japan_only": "JP only",
    "japan_proxy": "JP proxy",
    "japan_proxy_options": "JP proxy options",
    "jquants_nikkei_options": "J-Quants N225 options",
    "us_close_core": "US close core",
    "us_core": "US core",
    "us_late_session": "US late session",
    "us_core_options": "US core options",
    "asia_proxy": "Asia proxy",
    "asia_proxy_options": "Asia proxy options",
    "fred_credit_enriched": "FRED credit enriched",
    "options_risk": "Options risk",
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


def display_source_block_label(value: object) -> str:
    """Return compact paper-facing source-block labels."""
    text = "" if value is None else str(value)
    return _SOURCE_BLOCK_DISPLAY_LABELS.get(text, text)
