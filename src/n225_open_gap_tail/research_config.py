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
    PAPER_CANDIDATE = "paper_candidate"
    SUPPLEMENTARY = "supplementary"
    UNAVAILABLE = "unavailable"


class FeatureSetVersion(StrEnum):
    """Pre-registered paper feature-set versions."""

    CORE_FULL_HISTORY = "core_full_history"
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
    "C:USDJPY",
)
OPTIONAL_MASSIVE_TICKERS: tuple[str, ...] = ("UUP",)
JAPAN_PROXY_MASSIVE_TICKERS: tuple[str, ...] = ("EWJ", "DXJ")
ASIA_PROXY_MASSIVE_TICKERS: tuple[str, ...] = ("EWY", "EWT", "EWH")
ROBUSTNESS_MASSIVE_TICKERS: tuple[str, ...] = (
    JAPAN_PROXY_MASSIVE_TICKERS + ASIA_PROXY_MASSIVE_TICKERS
)

CORE_FRED_SERIES: tuple[str, ...] = (
    "VIXCLS",
    "DGS2",
    "DGS10",
    "T10Y2Y",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
)
FRED_FALLBACK_SERIES: tuple[str, ...] = ("DEXJPUS",)
POST_2018_FRED_SERIES: tuple[str, ...] = ("SOFR", "EFFR")
ROBUSTNESS_FRED_SERIES: tuple[str, ...] = ("NFCI", "ANFCI", "STLFSI4")


@dataclass(frozen=True)
class FeatureSetConfig:
    version: FeatureSetVersion = FeatureSetVersion.CORE_FULL_HISTORY
    massive_core: tuple[str, ...] = CORE_MASSIVE_TICKERS
    massive_optional: tuple[str, ...] = OPTIONAL_MASSIVE_TICKERS
    massive_japan_proxy: tuple[str, ...] = JAPAN_PROXY_MASSIVE_TICKERS
    massive_asia_proxy: tuple[str, ...] = ASIA_PROXY_MASSIVE_TICKERS
    massive_robustness: tuple[str, ...] = ROBUSTNESS_MASSIVE_TICKERS
    fred_core: tuple[str, ...] = CORE_FRED_SERIES
    fred_fallback: tuple[str, ...] = FRED_FALLBACK_SERIES
    fred_post_2018: tuple[str, ...] = POST_2018_FRED_SERIES
    fred_robustness: tuple[str, ...] = ROBUSTNESS_FRED_SERIES
    japan_only_features: tuple[str, ...] = (
        "lagged_target_history",
        "prior_settlement_close_returns",
        "lagged_day_night_returns",
        "rolling_volatility",
        "volume_open_interest_changes",
        "roll_sq_flags",
        "holiday_early_close_dst_flags",
    )
    p2b_model_a_information_set: str = "japan_only"
    p2b_model_b_information_set: str = "japan_only_plus_us_close_core"
    p2b_model_c_information_set: str = "japan_only_plus_us_close_core_plus_japan_proxy"
    p2b_model_d_information_set: str = (
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy"
    )


@dataclass(frozen=True)
class LeakagePolicy:
    fred_availability_lag_us_business_days: int = 1
    massive_vendor_lag_minutes: int = 15
    leakage_warning_min_lag_minutes: int = 30
    max_forward_fill_us_close_days: int = 7
    fred_vintage_policy: str = (
        "current_historical_values_with_conservative_lag_not_alfred_vintage_safe"
    )


@dataclass(frozen=True)
class ModelPolicy:
    tail_levels: tuple[float, ...] = (0.95, 0.975)
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
    joblib_backend: str = "loky"


@dataclass(frozen=True)
class EvaluationPolicy:
    primary_common_sample: str = "table_specific_intersection"
    pairwise_inference_sample: str = "pairwise_oos_intersection"
    global_headline_sample: str = "headline_only_report_retained_n"
    min_common_oos_rows: int = 120
    one_percent_min_exceedances: int = 10
    mcs_method: str = "block_bootstrap_fz_loss_matrix"


@dataclass(frozen=True)
class TargetPolicy:
    primary_target_family: str = "full_gap_settle_to_open"
    residual_usclosemark_enabled: bool = False
    residual_usclosemark_status: str = "disabled_requires_licensed_intraday_mark"


@dataclass(frozen=True)
class PaperResearchConfig:
    claim_level: ClaimLevel = ClaimLevel.PAPER_CANDIDATE
    feature_sets: FeatureSetConfig = field(default_factory=FeatureSetConfig)
    leakage_policy: LeakagePolicy = field(default_factory=LeakagePolicy)
    model_policy: ModelPolicy = field(default_factory=ModelPolicy)
    evaluation_policy: EvaluationPolicy = field(default_factory=EvaluationPolicy)
    target_policy: TargetPolicy = field(default_factory=TargetPolicy)

    def to_jsonable(self) -> dict[str, Any]:
        return cast(dict[str, Any], _enum_to_value(asdict(self)))

    def config_hash(self) -> str:
        encoded = json.dumps(self.to_jsonable(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def default_paper_research_config() -> PaperResearchConfig:
    return PaperResearchConfig()


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
