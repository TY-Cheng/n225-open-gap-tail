from pathlib import Path

import pytest

from n225_open_gap_tail.config import Settings, split_csv
from n225_open_gap_tail.config.research import CORE_FRED_SERIES, CORE_MASSIVE_TICKERS


def test_default_settings_have_project_name() -> None:
    settings = Settings(
        jquants_derivatives_daily_enabled=False,
        jquants_derivatives_intraday_enabled=False,
        fred_series=",".join(CORE_FRED_SERIES),
        massive_daily_tickers=",".join(CORE_MASSIVE_TICKERS),
    )

    assert settings.project_name == "n225-open-gap-tail"
    assert settings.project_timezone_jp == "Asia/Tokyo"
    assert settings.project_timezone_us == "America/New_York"
    assert settings.jquants_api_base_url.endswith("/v2")
    assert settings.jquants_equity_master_enabled is True
    assert settings.jquants_equity_daily_enabled is True
    assert settings.jquants_derivatives_daily_enabled is False
    assert settings.massive_request_timeout_seconds == 30
    assert settings.fred_series_list() == (
        "VIXCLS",
        "DGS2",
        "DGS10",
        "T10Y2Y",
    )
    assert settings.calendar_us_exchange == "XNYS"
    assert settings.calendar_jpx_exchange == "JPX"
    assert settings.nikkei_contract_roll_days_before_last_trade == 5
    assert settings.nikkei_contract_month_list() == (3, 6, 9, 12)
    assert settings.massive_daily_ticker_list() == (
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
        "SMH",
        "HYG",
        "LQD",
    )
    assert settings.massive_probe_ticker_list() == ("I:VIX",)


def test_required_directories_preserve_configured_paths(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        bronze_data_dir=tmp_path / "data/bronze",
        silver_data_dir=tmp_path / "data/silver",
        gold_data_dir=tmp_path / "data/gold",
        reports_dir=tmp_path / "reports",
    )

    assert settings.required_directories() == (
        tmp_path / "data",
        tmp_path / "data/bronze",
        tmp_path / "data/silver",
        tmp_path / "data/gold",
        tmp_path / "reports",
    )


def test_api_keys_resolve_from_secret_files(tmp_path: Path) -> None:
    massive_key_file = tmp_path / "massive.keyfile"
    massive_flat_file_key_file = tmp_path / "massive-flat-file.keyfile"
    jquants_key_file = tmp_path / "jquants.keyfile"
    massive_key_file.write_text("massive-secret\n", encoding="utf-8")
    massive_flat_file_key_file.write_text("massive-flat-file-secret\n", encoding="utf-8")
    jquants_key_file.write_text("jquants-secret\n", encoding="utf-8")

    settings = Settings(
        massive_api_key_file=str(massive_key_file),
        massive_flat_file_key_file=str(massive_flat_file_key_file),
        jquants_api_key_file=str(jquants_key_file),
    )

    assert settings.read_massive_api_key() == "massive-secret"
    assert settings.read_massive_flat_file_key() == "massive-flat-file-secret"
    assert settings.read_jquants_api_key() == "jquants-secret"


def test_direct_api_key_environment_variables_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MASSIVE_API_KEY", "inline-massive-secret")
    monkeypatch.setenv("MASSIVE_FLAT_FILE_KEY", "inline-flat-file-secret")
    monkeypatch.setenv("JQUANTS_API_KEY", "inline-jquants-secret")

    settings = Settings(
        massive_api_key_file="",
        massive_flat_file_key_file="",
        jquants_api_key_file="",
    )

    with pytest.raises(ValueError, match="MASSIVE_API_KEY_FILE is not configured"):
        settings.read_massive_api_key()
    with pytest.raises(ValueError, match="MASSIVE_FLAT_FILE_KEY_FILE is not configured"):
        settings.read_massive_flat_file_key()
    with pytest.raises(ValueError, match="JQUANTS_API_KEY_FILE is not configured"):
        settings.read_jquants_api_key()


def test_split_csv_removes_empty_tokens() -> None:
    assert split_csv(" SPY, ,QQQ,C:USDJPY ") == ("SPY", "QQQ", "C:USDJPY")
