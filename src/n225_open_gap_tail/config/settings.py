from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from n225_open_gap_tail.config.research import CORE_FRED_SERIES, CORE_MASSIVE_TICKERS


def _read_secret_file(path_value: str, *, env_name: str) -> str:
    if not path_value.strip():
        raise ValueError(f"{env_name} is not configured")
    path = Path(os.path.expanduser(os.path.expandvars(path_value))).resolve()
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"{env_name} points to an unreadable file: {path}") from exc
    if not secret:
        raise ValueError(f"{env_name} points to an empty file: {path}")
    return secret


def split_csv(value: str) -> tuple[str, ...]:
    """Split comma-separated environment values into non-empty tokens."""
    return tuple(token.strip() for token in value.split(",") if token.strip())


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "n225-open-gap-tail"
    project_timezone_jp: str = "Asia/Tokyo"
    project_timezone_us: str = "America/New_York"
    log_level: str = "INFO"

    data_dir: Path = Field(default=Path("data"))
    bronze_data_dir: Path = Field(default=Path("data/bronze"))
    silver_data_dir: Path = Field(default=Path("data/silver"))
    gold_data_dir: Path = Field(default=Path("data/gold"))
    reports_dir: Path = Field(default=Path("reports"))

    massive_api_key_file: str = ""
    massive_flat_file_key_file: str = ""
    massive_base_url: str = "https://api.massive.com"
    massive_request_timeout_seconds: int = 30
    massive_min_request_interval_seconds: float = 0.0
    massive_max_retries: int = 2
    massive_rate_limit_backoff_seconds: float = 60.0
    massive_daily_tickers: str = ",".join(CORE_MASSIVE_TICKERS)
    massive_minute_ticker: str = "SPY"
    massive_probe_tickers: str = "I:VIX"
    massive_regular_session_start_et: str = "09:30"
    massive_regular_session_end_et: str = "16:00"

    fred_base_url: str = "https://fred.stlouisfed.org"
    fred_request_timeout_seconds: int = 30
    fred_series: str = ",".join(CORE_FRED_SERIES)

    cboe_base_url: str = "https://cdn.cboe.com"
    cboe_vol_index_symbols: str = "VIX"
    cboe_request_timeout_seconds: int = 30

    calendar_us_exchange: str = "XNYS"
    calendar_jpx_exchange: str = "JPX"

    nikkei_contract_roll_days_before_last_trade: int = 5
    nikkei_contract_months: str = "3,6,9,12"

    jquants_api_key_file: str = ""
    jquants_api_base_url: str = "https://api.jquants.com/v2"
    jquants_equity_master_enabled: bool = True
    jquants_equity_daily_enabled: bool = True
    jquants_derivatives_daily_enabled: bool = False
    jquants_derivatives_intraday_enabled: bool = False
    jquants_request_timeout_seconds: int = 30

    jpx_datacube_email: str = ""
    jpx_datacube_password: str = ""
    jpx_datacube_base_url: str = "https://dc.jpx-jquants.com"

    def read_massive_api_key(self) -> str:
        return _read_secret_file(self.massive_api_key_file, env_name="MASSIVE_API_KEY_FILE")

    def read_massive_flat_file_key(self) -> str:
        return _read_secret_file(
            self.massive_flat_file_key_file,
            env_name="MASSIVE_FLAT_FILE_KEY_FILE",
        )

    def read_jquants_api_key(self) -> str:
        return _read_secret_file(self.jquants_api_key_file, env_name="JQUANTS_API_KEY_FILE")

    def required_directories(self) -> tuple[Path, ...]:
        return (
            self.data_dir,
            self.bronze_data_dir,
            self.silver_data_dir,
            self.gold_data_dir,
            self.reports_dir,
        )

    def massive_daily_ticker_list(self) -> tuple[str, ...]:
        return split_csv(self.massive_daily_tickers)

    def massive_probe_ticker_list(self) -> tuple[str, ...]:
        return split_csv(self.massive_probe_tickers)

    def fred_series_list(self) -> tuple[str, ...]:
        return split_csv(self.fred_series)

    def cboe_vol_index_symbol_list(self) -> tuple[str, ...]:
        return split_csv(self.cboe_vol_index_symbols)

    def nikkei_contract_month_list(self) -> tuple[int, ...]:
        return tuple(int(month) for month in split_csv(self.nikkei_contract_months))


def load_settings() -> Settings:
    return Settings()
