from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any, cast


class ClaimLevel(StrEnum):
    """Controlled vocabulary for artifact claim status."""

    SMOKE_ONLY = "smoke_only"
    PRELIMINARY_PIPELINE = "preliminary_pipeline"
    RESEARCH_CANDIDATE = "research_candidate"
    SUPPLEMENTARY = "supplementary"
    UNAVAILABLE = "unavailable"


class FeatureSetVersion(StrEnum):
    """Pre-registered paper feature-set versions."""

    CORE_FULL_HISTORY = "core_full_history"
    OPTIONS_EVT_HEADLINE = "options_evt_headline"
    POST_2018_ENRICHED = "post_2018_enriched"
    ROBUSTNESS_CANDIDATE = "robustness_candidate"


CORE_MASSIVE_TICKERS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLY",
    "XLP",
    "XLB",
    "XLU",
    "XLC",
    "TLT",
    "GLD",
    "USO",
    "EEM",
    "FXI",
    "SMH",
    "HYG",
    "LQD",
)
OPTIONAL_MASSIVE_TICKERS: tuple[str, ...] = ("UUP",)
JAPAN_PROXY_MASSIVE_TICKERS: tuple[str, ...] = ("EWJ", "DXJ")
ASIA_PROXY_MASSIVE_TICKERS: tuple[str, ...] = ("EWY", "EWT", "EWH")
ROBUSTNESS_MASSIVE_TICKERS: tuple[str, ...] = (
    JAPAN_PROXY_MASSIVE_TICKERS + ASIA_PROXY_MASSIVE_TICKERS
)
MASSIVE_MINUTE_US_CORE_TICKERS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "TLT",
    "HYG",
    "GLD",
)
MASSIVE_MINUTE_JAPAN_PROXY_TICKERS: tuple[str, ...] = ("EWJ", "DXJ")
MASSIVE_MINUTE_ASIA_PROXY_TICKERS: tuple[str, ...] = ("EEM", "FXI", "EWY", "EWT", "EWH")
MASSIVE_MINUTE_TICKERS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *MASSIVE_MINUTE_US_CORE_TICKERS,
            *MASSIVE_MINUTE_JAPAN_PROXY_TICKERS,
            *MASSIVE_MINUTE_ASIA_PROXY_TICKERS,
        )
    )
)
MASSIVE_OPTIONS_CORE_UNDERLYINGS: tuple[str, ...] = ("SPY", "QQQ", "IWM")
MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS: tuple[str, ...] = ("EWJ", "DXJ")
MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS: tuple[str, ...] = (
    "TM",
    "SONY",
    "MUFG",
    "SMFG",
    "MFG",
)
MASSIVE_OPTIONS_ADR_DIAGNOSTIC_UNDERLYINGS: tuple[str, ...] = ("HMC", "NMR", "IX", "TAK")

CORE_FRED_SERIES: tuple[str, ...] = (
    "VIXCLS",
    "DGS2",
    "DGS10",
    "T10Y2Y",
)
FRED_FALLBACK_SERIES: tuple[str, ...] = ("DEXJPUS",)
FRED_CREDIT_ENRICHED_SERIES: tuple[str, ...] = ("BAMLH0A0HYM2", "BAMLC0A0CM")
POST_2018_FRED_SERIES: tuple[str, ...] = ("SOFR", "EFFR")
ROBUSTNESS_FRED_SERIES: tuple[str, ...] = ("NFCI", "ANFCI", "STLFSI4")


@dataclass(frozen=True)
class FeatureSetConfig:
    version: FeatureSetVersion = FeatureSetVersion.OPTIONS_EVT_HEADLINE
    massive_core: tuple[str, ...] = CORE_MASSIVE_TICKERS
    massive_optional: tuple[str, ...] = OPTIONAL_MASSIVE_TICKERS
    massive_japan_proxy: tuple[str, ...] = JAPAN_PROXY_MASSIVE_TICKERS
    massive_asia_proxy: tuple[str, ...] = ASIA_PROXY_MASSIVE_TICKERS
    massive_robustness: tuple[str, ...] = ROBUSTNESS_MASSIVE_TICKERS
    massive_minute_us_core: tuple[str, ...] = MASSIVE_MINUTE_US_CORE_TICKERS
    massive_minute_japan_proxy: tuple[str, ...] = MASSIVE_MINUTE_JAPAN_PROXY_TICKERS
    massive_minute_asia_proxy: tuple[str, ...] = MASSIVE_MINUTE_ASIA_PROXY_TICKERS
    massive_options_core_underlyings: tuple[str, ...] = MASSIVE_OPTIONS_CORE_UNDERLYINGS
    massive_options_japan_etf_underlyings: tuple[str, ...] = MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS
    massive_options_adr_primary_underlyings: tuple[str, ...] = (
        MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS
    )
    massive_options_adr_diagnostic_underlyings: tuple[str, ...] = (
        MASSIVE_OPTIONS_ADR_DIAGNOSTIC_UNDERLYINGS
    )
    fred_core: tuple[str, ...] = CORE_FRED_SERIES
    fred_fallback: tuple[str, ...] = FRED_FALLBACK_SERIES
    fred_credit_enriched: tuple[str, ...] = FRED_CREDIT_ENRICHED_SERIES
    fred_post_2018: tuple[str, ...] = POST_2018_FRED_SERIES
    fred_robustness: tuple[str, ...] = ROBUSTNESS_FRED_SERIES
    japan_only_features: tuple[str, ...] = (
        "lagged_target_history",
        "prior_settlement_close_returns",
        "lagged_day_night_returns",
        "rolling_volatility",
        "volume_open_interest_changes",
        "volume_oi_z_scores",
        "session_range_variance",
        "session_semivariance",
        "session_higher_moments",
        "lagged_nikkei225_option_implied_state",
        "contract_calendar_controls",
        "roll_sq_flags",
        "holiday_early_close_dst_flags",
    )
    ml_tail_model_a_information_set: str = "japan_only"
    ml_tail_model_b_information_set: str = "japan_only_plus_us_close_core"
    ml_tail_model_c_information_set: str = "japan_only_plus_us_close_core_plus_japan_proxy"
    ml_tail_model_d_information_set: str = (
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy"
    )
    ml_tail_model_e_information_set: str = (
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy_plus_options_risk"
    )


@dataclass(frozen=True)
class FeatureEngineeringPolicy:
    """Controls deterministic headline feature engineering."""

    n225_range_window: int = 20
    n225_range_min_periods: int = 20
    n225_semivariance_window: int = 20
    n225_semivariance_min_periods: int = 20
    n225_higher_moment_window: int = 120
    n225_higher_moment_min_periods: int = 120
    n225_volume_oi_zscore_window: int = 60
    n225_volume_oi_zscore_min_periods: int = 20
    massive_minute_late_window: int = 60
    massive_minute_moment_min_periods: int = 30
    massive_minute_volume_baseline_window: int = 20
    options_dte_short_bucket: tuple[int, int] = (7, 30)
    options_dte_medium_bucket: tuple[int, int] = (31, 90)
    options_headline_feature_cap: int = 30
    options_atm_policy: str = "delta_neutral_preferred_else_closest_to_spot_or_forward"
    options_adr_aggregation_policy: str = "median_and_20pct_trimmed_mean_primary"
    options_historical_source_policy: str = (
        "disabled_until_historical_iv_greeks_oi_entitlement_verified"
    )
    winsorization_policy: str = "none_raw_estimators_no_full_sample_winsorization"


@dataclass(frozen=True)
class LeakagePolicy:
    fred_availability_lag_us_business_days: int = 1
    massive_vendor_lag_minutes: int = 15
    leakage_warning_min_lag_minutes: int = 30
    max_forward_fill_us_close_days: int = 7
    fred_h10_release_age_cap_calendar_days: int = 8
    fred_vintage_policy: str = (
        "current_historical_values_with_conservative_lag_not_alfred_vintage_safe"
    )


@dataclass(frozen=True)
class ModelPolicy:
    tail_levels: tuple[float, ...] = (0.95,)
    tail_sides: tuple[str, ...] = ("left_tail", "right_tail")
    primary_tail_side: str = "left_tail"
    tail_side_policy: str = "positive_loss_units_left_minus_gap_right_gap_shared_tail_levels"
    ewma_lambda: float = 0.94
    ewma_sensitivity_lambdas: tuple[float, ...] = (0.90, 0.97)
    min_train_rows: int = 1000
    min_train_exceedances: int = 50
    earliest_oos_start: str = "2016-01-01"
    low_variance_threshold: float = 1e-8
    near_zero_variance_threshold: float = 1e-6
    shard_size_forecast_dates: int = 50
    evt_threshold_quantile: float = 0.90
    evt_threshold_grid: tuple[float, ...] = (0.90, 0.925, 0.95)
    evt_threshold_refresh: str = "monthly_locked"
    evt_threshold_smoothing: str = "rolling_median_optional"
    evt_min_standardized_losses_95: int = 500
    evt_min_exceedances_95: int = 35
    location_scale_min_es_exceedances_95: int = 25
    evt_shape_cap_baseline: tuple[float, float] = (-0.25, 0.75)
    evt_shape_cap_conservative: tuple[float, float] = (-0.10, 0.50)
    evt_shape_cap_loose: tuple[float, float] = (-0.50, 1.00)
    evt_shape_shrinkage_k: float = 50.0
    evt_evi_primary_estimator: str = "dedh_moment"
    evt_ei_primary_estimator: str = "ferro_segers"
    evt_ei_robustness_estimator: str = "k_gaps"
    joblib_backend: str = "loky"
    advanced_runtime_budget_single_threaded: str = "4_to_8_hours_full_suite_estimate"
    advanced_parallelism_unit: str = "model_name_x_tail_level_shards"
    advanced_recursive_burn_in_rows: int = 252
    advanced_gas_burn_in_rows: int = 500
    advanced_optimizer_max_restarts: int = 3
    advanced_optimizer_jitter_fraction: float = 0.05
    advanced_optimizer_jitter_floor: float = 1e-4
    gas_score_scaling: str = "raw_student_t_log_scale_score"
    gas_state_variable: str = "log_sigma"
    gas_nu_grid: tuple[float, ...] = (4.1, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0)
    care_expectile_grid: tuple[float, ...] = (0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)
    care_expectile_calibration_method: str = (
        "training_window_grid_search_match_target_var_exception_rate"
    )


@dataclass(frozen=True)
class EvaluationPolicy:
    primary_common_sample: str = "table_specific_intersection"
    pairwise_inference_sample: str = "pairwise_oos_intersection"
    global_headline_sample: str = "headline_only_report_retained_n"
    min_common_oos_rows: int = 120
    one_percent_min_exceedances: int = 10
    bootstrap_reps: int = 999
    inference_random_seed: int = 225
    mcs_alpha: float = 0.10
    mcs_method: str = "hln_tmax_moving_block_bootstrap"
    dm_method: str = "moving_block_bootstrap_unconditional_dm"
    panel_signature_hash_seed: int = 42


@dataclass(frozen=True)
class TargetPolicy:
    primary_target_family: str = "full_gap_settle_to_open"
    residual_usclosemark_enabled: bool = False
    residual_usclosemark_status: str = "disabled_requires_licensed_intraday_mark"


@dataclass(frozen=True)
class ResearchConfig:
    claim_level: ClaimLevel = ClaimLevel.RESEARCH_CANDIDATE
    feature_sets: FeatureSetConfig = field(default_factory=FeatureSetConfig)
    feature_engineering: FeatureEngineeringPolicy = field(default_factory=FeatureEngineeringPolicy)
    leakage_policy: LeakagePolicy = field(default_factory=LeakagePolicy)
    model_policy: ModelPolicy = field(default_factory=ModelPolicy)
    evaluation_policy: EvaluationPolicy = field(default_factory=EvaluationPolicy)
    target_policy: TargetPolicy = field(default_factory=TargetPolicy)

    def to_jsonable(self) -> dict[str, Any]:
        return cast(dict[str, Any], _enum_to_value(asdict(self)))

    def config_hash(self) -> str:
        encoded = json.dumps(self.to_jsonable(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def default_research_config() -> ResearchConfig:
    return ResearchConfig()


def stable_hash(payload: object) -> str:
    encoded = json.dumps(
        _enum_to_value(payload), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _enum_to_value(value: object) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _enum_to_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _enum_to_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_enum_to_value(item) for item in value]
    return value
