from __future__ import annotations

from pathlib import Path

import pytest

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.config.research import (
    ASIA_PROXY_MASSIVE_TICKERS,
    CORE_FRED_SERIES,
    CORE_MASSIVE_TICKERS,
    JAPAN_PROXY_MASSIVE_TICKERS,
    MASSIVE_MINUTE_ASIA_PROXY_TICKERS,
    MASSIVE_MINUTE_JAPAN_PROXY_TICKERS,
    MASSIVE_MINUTE_US_CORE_TICKERS,
    ClaimLevel,
    FeatureSetVersion,
    default_research_config,
)
from n225_open_gap_tail.panel.information_sets import registered_ml_tail_information_sets


def test_claim_level_enum_is_controlled_vocabulary() -> None:
    assert {level.value for level in ClaimLevel} == {
        "smoke_only",
        "preliminary_pipeline",
        "research_candidate",
        "supplementary",
        "unavailable",
    }


def test_core_feature_sets_exclude_short_history_and_robustness_tickers() -> None:
    config = default_research_config()

    assert config.feature_sets.version == FeatureSetVersion.OPTIONS_EVT_PRIMARY
    assert "SOFR" not in config.feature_sets.fred_core
    assert "EFFR" not in config.feature_sets.fred_core
    assert "SOFR" in config.feature_sets.fred_post_2018
    assert "EWJ" not in config.feature_sets.massive_core
    assert "DXJ" not in config.feature_sets.massive_core
    assert "EWH" not in config.feature_sets.massive_core
    assert config.feature_sets.massive_japan_proxy == JAPAN_PROXY_MASSIVE_TICKERS
    assert config.feature_sets.massive_asia_proxy == ASIA_PROXY_MASSIVE_TICKERS
    assert "EWH" in config.feature_sets.massive_asia_proxy
    assert config.feature_sets.massive_robustness == (
        JAPAN_PROXY_MASSIVE_TICKERS + ASIA_PROXY_MASSIVE_TICKERS
    )
    assert config.feature_sets.massive_minute_us_core == MASSIVE_MINUTE_US_CORE_TICKERS
    assert config.feature_sets.massive_minute_japan_proxy == MASSIVE_MINUTE_JAPAN_PROXY_TICKERS
    assert config.feature_sets.massive_minute_asia_proxy == MASSIVE_MINUTE_ASIA_PROXY_TICKERS
    assert "C:USDJPY" not in config.feature_sets.massive_core
    assert "C:USDJPY" not in config.feature_sets.massive_optional
    assert config.feature_sets.massive_optional == ("UUP",)
    assert "DEXJPUS" in config.feature_sets.fred_fallback
    assert "BAMLH0A0HYM2" in config.feature_sets.fred_credit_enriched
    assert config.feature_sets.ml_tail_model_d_information_set.endswith("plus_asia_proxy")
    assert len(registered_ml_tail_information_sets()) == 4
    assert config.model_policy.tail_levels == (0.95,)
    assert config.model_policy.evt_min_standardized_losses_95 == 500
    assert config.model_policy.evt_min_exceedances_95 == 35
    assert config.leakage_policy.fred_availability_lag_us_business_days == 1
    assert config.leakage_policy.max_forward_fill_us_close_days == 7
    assert config.leakage_policy.fred_h10_release_age_cap_calendar_days == 8
    assert config.feature_engineering.n225_higher_moment_window == 120
    assert config.feature_engineering.ml_feature_max_training_missingness == 0.20
    assert config.feature_engineering.ml_minute_feature_max_training_missingness == 0.05
    assert config.feature_engineering.winsorization_policy.startswith("none_raw")


def test_config_hash_is_stable_and_env_defaults_sync_with_core_lists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = default_research_config()
    assert config.config_hash() == default_research_config().config_hash()
    monkeypatch.setenv("MASSIVE_DAILY_TICKERS", ",".join(CORE_MASSIVE_TICKERS))
    monkeypatch.setenv("FRED_SERIES", ",".join(CORE_FRED_SERIES))

    settings = Settings(
        data_dir=tmp_path / "data",
        bronze_data_dir=tmp_path / "data" / "bronze",
        silver_data_dir=tmp_path / "data" / "silver",
        gold_data_dir=tmp_path / "data" / "gold",
        reports_dir=tmp_path / "reports",
    )

    assert settings.massive_daily_ticker_list() == CORE_MASSIVE_TICKERS
    assert settings.fred_series_list() == CORE_FRED_SERIES
