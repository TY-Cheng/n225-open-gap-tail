from __future__ import annotations

from pathlib import Path

import pytest

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.research_config import (
    ASIA_PROXY_MASSIVE_TICKERS,
    CORE_FRED_SERIES,
    CORE_MASSIVE_TICKERS,
    JAPAN_PROXY_MASSIVE_TICKERS,
    ClaimLevel,
    FeatureSetVersion,
    default_paper_research_config,
)


def test_claim_level_enum_is_controlled_vocabulary() -> None:
    assert {level.value for level in ClaimLevel} == {
        "smoke_only",
        "preliminary_pipeline",
        "paper_candidate",
        "supplementary",
        "unavailable",
    }


def test_core_feature_sets_exclude_short_history_and_robustness_tickers() -> None:
    config = default_paper_research_config()

    assert config.feature_sets.version == FeatureSetVersion.CORE_FULL_HISTORY
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
    assert "C:USDJPY" in config.feature_sets.massive_core
    assert config.feature_sets.p2b_model_d_information_set.endswith("plus_asia_proxy")
    assert config.leakage_policy.fred_availability_lag_us_business_days == 1


def test_config_hash_is_stable_and_env_defaults_sync_with_core_lists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = default_paper_research_config()
    assert config.config_hash() == default_paper_research_config().config_hash()
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
