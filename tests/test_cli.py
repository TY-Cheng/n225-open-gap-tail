from pathlib import Path

import pytest
from typer.testing import CliRunner

import n225_open_gap_tail.cli as cli
from n225_open_gap_tail.calendars import CalendarBuildResult
from n225_open_gap_tail.cli import app
from n225_open_gap_tail.contracts import ContractMetadataResult
from n225_open_gap_tail.fred import FredSmokeResult
from n225_open_gap_tail.jquants import JQuantsSmokeResult
from n225_open_gap_tail.massive import MassiveSmokeResult


def test_status_reports_environment_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    interim_dir = data_dir / "interim"
    processed_dir = data_dir / "processed"
    reports_dir = tmp_path / "reports"
    for directory in (data_dir, raw_dir, interim_dir, processed_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "${HOME}/.venvs/n225-open-gap-tail")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))
    monkeypatch.setenv("INTERIM_DATA_DIR", str(interim_dir))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(processed_dir))
    monkeypatch.setenv("REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("MASSIVE_API_KEY", "massive-secret")
    monkeypatch.setenv("JQUANTS_API_KEY", "jquants-secret")
    monkeypatch.setenv("JQUANTS_API_PLAN", "free")
    monkeypatch.setenv("JPX_DATACUBE_EMAIL", "researcher@example.com")

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "project: n225-open-gap-tail" in result.output
    assert "uv environment: ${HOME}/.venvs/n225-open-gap-tail" in result.output
    assert f"  - {data_dir}: ok" in result.output
    assert "massive api key configured: True" in result.output
    assert "massive api base url: https://api.massive.com" in result.output
    assert "massive daily ticker count: 10" in result.output
    assert "massive minute ticker: SPY" in result.output
    assert "massive probe ticker count: 1" in result.output
    assert "fred base url: https://fred.stlouisfed.org" in result.output
    assert "fred series count: 3" in result.output
    assert "calendar us exchange: XNYS" in result.output
    assert "calendar jpx exchange: JPX" in result.output
    assert "nikkei contract roll days before last trade: 5" in result.output
    assert "j-quants api version: v2" in result.output
    assert "j-quants api base url: https://api.jquants.com/v2" in result.output
    assert "j-quants api key configured: True" in result.output
    assert "j-quants api plan: free" in result.output
    assert "j-quants equity master enabled: True" in result.output
    assert "j-quants equity daily enabled: True" in result.output
    assert "j-quants derivatives daily enabled: False" in result.output
    assert "j-quants derivatives intraday enabled: False" in result.output
    assert "jpx datacube email configured: True" in result.output
    assert "massive-secret" not in result.output
    assert "jquants-secret" not in result.output
    assert "researcher@example.com" not in result.output


def test_jquants_smoke_command_reports_non_secret_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "jquants_smoke.json"

    def fake_write_jquants_smoke_sample(**kwargs: object) -> JQuantsSmokeResult:
        return JQuantsSmokeResult(
            output_path=output_path,
            equity_master_rows=1,
            equity_daily_rows=5,
            futures_probe_status=403,
            futures_probe_rows=0,
        )

    monkeypatch.setattr(cli, "write_jquants_smoke_sample", fake_write_jquants_smoke_sample)

    result = CliRunner().invoke(
        app,
        [
            "jquants-smoke",
            "--code",
            "72030",
            "--start",
            "2025-12-01",
            "--end",
            "2025-12-05",
        ],
    )

    assert result.exit_code == 0
    assert f"wrote: {output_path}" in result.output
    assert "equity master rows: 1" in result.output
    assert "equity daily rows: 5" in result.output
    assert "futures probe status: 403" in result.output
    assert "futures probe rows: 0" in result.output


def test_massive_smoke_command_reports_non_secret_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "massive_smoke.json"
    daily_path = tmp_path / "massive_daily.parquet"
    minute_path = tmp_path / "massive_minute.parquet"

    def fake_write_massive_smoke_sample(**kwargs: object) -> MassiveSmokeResult:
        assert kwargs["tickers"] == ("SPY", "QQQ")
        assert kwargs["probe_tickers"] == ("I:VIX",)
        return MassiveSmokeResult(
            raw_output_path=raw_path,
            daily_parquet_path=daily_path,
            minute_parquet_path=minute_path,
            daily_rows=10,
            minute_rows=921,
            minute_regular_session_rows=390,
            daily_statuses={"SPY": 200, "QQQ": 200},
            minute_status=200,
            probe_statuses={"I:VIX": 403},
        )

    monkeypatch.setattr(cli, "write_massive_smoke_sample", fake_write_massive_smoke_sample)

    result = CliRunner().invoke(
        app,
        [
            "massive-smoke",
            "--tickers",
            "SPY,QQQ",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-09",
            "--probe-tickers",
            "I:VIX",
        ],
    )

    assert result.exit_code == 0
    assert f"raw wrote: {raw_path}" in result.output
    assert f"daily parquet wrote: {daily_path}" in result.output
    assert f"minute parquet wrote: {minute_path}" in result.output
    assert "daily rows: 10" in result.output
    assert "minute rows: 921" in result.output
    assert "minute regular-session rows: 390" in result.output
    assert "daily statuses: SPY=200, QQQ=200" in result.output
    assert "minute status: 200" in result.output
    assert "probe statuses: I:VIX=403" in result.output


def test_fred_smoke_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "fred_smoke.json"
    parquet_path = tmp_path / "fred.parquet"

    def fake_write_fred_smoke_sample(**kwargs: object) -> FredSmokeResult:
        assert kwargs["series_ids"] == ("VIXCLS", "DGS10")
        return FredSmokeResult(
            raw_output_path=raw_path,
            parquet_path=parquet_path,
            rows=4,
            series_statuses={"VIXCLS": 200, "DGS10": 200},
            series_rows={"VIXCLS": 2, "DGS10": 2},
        )

    monkeypatch.setattr(cli, "write_fred_smoke_sample", fake_write_fred_smoke_sample)

    result = CliRunner().invoke(
        app,
        [
            "fred-smoke",
            "--series",
            "VIXCLS,DGS10",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
        ],
    )

    assert result.exit_code == 0
    assert f"raw wrote: {raw_path}" in result.output
    assert f"parquet wrote: {parquet_path}" in result.output
    assert "rows: 4" in result.output
    assert "series statuses: VIXCLS=200, DGS10=200" in result.output
    assert "series rows: VIXCLS=2, DGS10=2" in result.output


def test_calendar_build_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "calendar.json"
    parquet_path = tmp_path / "calendar.parquet"

    def fake_write_calendar_table(**kwargs: object) -> CalendarBuildResult:
        assert kwargs["start"] == "2026-01-01"
        assert kwargs["end"] == "2026-01-31"
        return CalendarBuildResult(
            metadata_path=metadata_path,
            parquet_path=parquet_path,
            rows=31,
            us_trading_days=20,
            jpx_trading_days=19,
            us_early_closes=0,
        )

    monkeypatch.setattr(cli, "write_calendar_table", fake_write_calendar_table)

    result = CliRunner().invoke(
        app,
        [
            "calendar-build",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-31",
        ],
    )

    assert result.exit_code == 0
    assert f"metadata wrote: {metadata_path}" in result.output
    assert f"parquet wrote: {parquet_path}" in result.output
    assert "rows: 31" in result.output
    assert "us trading days: 20" in result.output
    assert "jpx trading days: 19" in result.output
    assert "us early closes: 0" in result.output


def test_contracts_build_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "contracts.json"
    contracts_path = tmp_path / "contracts.parquet"
    selector_path = tmp_path / "selector.parquet"

    def fake_write_contract_metadata(**kwargs: object) -> ContractMetadataResult:
        assert kwargs["start"] == "2026-01-01"
        assert kwargs["end"] == "2026-12-31"
        return ContractMetadataResult(
            metadata_path=metadata_path,
            contracts_path=contracts_path,
            selector_path=selector_path,
            contracts=16,
            selector_rows=245,
            roll_window_rows=20,
        )

    monkeypatch.setattr(cli, "write_contract_metadata", fake_write_contract_metadata)

    result = CliRunner().invoke(
        app,
        [
            "contracts-build",
            "--start",
            "2026-01-01",
            "--end",
            "2026-12-31",
        ],
    )

    assert result.exit_code == 0
    assert f"metadata wrote: {metadata_path}" in result.output
    assert f"contracts parquet wrote: {contracts_path}" in result.output
    assert f"selector parquet wrote: {selector_path}" in result.output
    assert "contracts: 16" in result.output
    assert "selector rows: 245" in result.output
    assert "roll-window rows: 20" in result.output
