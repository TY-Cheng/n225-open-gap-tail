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
from n225_open_gap_tail.paper import (
    PaperEvalResult,
    PaperLatexResult,
    PaperLeakageCheckResult,
    PaperPanelResult,
)
from n225_open_gap_tail.research_config import CORE_FRED_SERIES, CORE_MASSIVE_TICKERS


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
    monkeypatch.setenv("MASSIVE_DAILY_TICKERS", ",".join(CORE_MASSIVE_TICKERS))
    monkeypatch.setenv("FRED_SERIES", ",".join(CORE_FRED_SERIES))
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
    assert "massive daily ticker count: 23" in result.output
    assert "massive minute ticker: SPY" in result.output
    assert "massive probe ticker count: 1" in result.output
    assert "fred base url: https://fred.stlouisfed.org" in result.output
    assert "fred series count: 6" in result.output
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


def test_paper_panel_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "paper_run"
    panel_path = run_dir / "panel" / "modeling_panel.parquet"

    def fake_write_paper_panel(**kwargs: object) -> PaperPanelResult:
        assert kwargs["start"] == "2008-05-07"
        assert kwargs["end"] is None
        return PaperPanelResult(
            run_id="p2a_test",
            run_dir=run_dir,
            panel_path=panel_path,
            rows=100,
            clean_rows=90,
        )

    monkeypatch.setattr(cli, "write_paper_panel", fake_write_paper_panel)

    result = CliRunner().invoke(app, ["paper-panel"])

    assert result.exit_code == 0
    assert "run id: p2a_test" in result.output
    assert f"run dir: {run_dir}" in result.output
    assert "rows: 100" in result.output
    assert "clean rows: 90" in result.output


def test_paper_eval_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "paper_run"

    def fake_resolve_paper_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == "p2a_test"
        return run_dir

    def fake_evaluate_paper_run(**kwargs: object) -> PaperEvalResult:
        assert kwargs["run_dir"] == run_dir
        assert kwargs["workers"] == 2
        assert kwargs["stage"] == "p2a"
        assert kwargs["force"] is False
        return PaperEvalResult(
            run_id="p2a_test",
            run_dir=run_dir,
            forecast_rows=50,
            metric_rows=6,
            status="completed",
        )

    monkeypatch.setattr(cli, "resolve_paper_run_dir", fake_resolve_paper_run_dir)
    monkeypatch.setattr(cli, "evaluate_paper_run", fake_evaluate_paper_run)

    result = CliRunner().invoke(
        app,
        ["paper-eval", "--run-id", "p2a_test", "--workers", "2"],
    )

    assert result.exit_code == 0
    assert "forecast rows: 50" in result.output
    assert "metric rows: 6" in result.output
    assert "status: completed" in result.output


def test_paper_grade_command_runs_panel_eval_and_latex(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "paper_run"

    def fake_write_paper_panel(**kwargs: object) -> PaperPanelResult:
        return PaperPanelResult(
            run_id="p2a_test",
            run_dir=run_dir,
            panel_path=run_dir / "panel" / "modeling_panel.parquet",
            rows=100,
            clean_rows=90,
        )

    def fake_evaluate_paper_run(**kwargs: object) -> PaperEvalResult:
        assert kwargs["stage"] == "p2a"
        return PaperEvalResult(
            run_id="p2a_test",
            run_dir=run_dir,
            forecast_rows=50,
            metric_rows=6,
            status="completed",
        )

    def fake_write_paper_latex_tables(**kwargs: object) -> PaperLatexResult:
        return PaperLatexResult(
            run_id="p2a_test",
            latex_dir=run_dir / "latex" / "tables",
            tables=1,
        )

    monkeypatch.setattr(cli, "write_paper_panel", fake_write_paper_panel)
    monkeypatch.setattr(cli, "evaluate_paper_run", fake_evaluate_paper_run)
    monkeypatch.setattr(cli, "write_paper_latex_tables", fake_write_paper_latex_tables)

    result = CliRunner().invoke(app, ["paper-grade", "--workers", "1"])

    assert result.exit_code == 0
    assert "panel rows: 100" in result.output
    assert "forecast rows: 50" in result.output
    assert "eval status: completed" in result.output
    assert "latex tables: 1" in result.output


def test_paper_latex_tables_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "paper_run"

    def fake_resolve_paper_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == ""
        return run_dir

    def fake_write_paper_latex_tables(**kwargs: object) -> PaperLatexResult:
        assert kwargs["run_dir"] == run_dir
        return PaperLatexResult(
            run_id="p2a_latest",
            latex_dir=run_dir / "latex" / "tables",
            tables=1,
        )

    monkeypatch.setattr(cli, "resolve_paper_run_dir", fake_resolve_paper_run_dir)
    monkeypatch.setattr(cli, "write_paper_latex_tables", fake_write_paper_latex_tables)

    result = CliRunner().invoke(app, ["paper-latex-tables"])

    assert result.exit_code == 0
    assert "run id: p2a_latest" in result.output
    assert "tables: 1" in result.output


def test_paper_leakage_check_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "paper_run"
    output_path = run_dir / "audits" / "leakage_check.parquet"

    def fake_resolve_paper_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == "p2a_test"
        return run_dir

    def fake_write_paper_leakage_check(**kwargs: object) -> PaperLeakageCheckResult:
        assert kwargs["run_dir"] == run_dir
        return PaperLeakageCheckResult(
            run_id="p2a_test",
            output_path=output_path,
            rows=10,
            failures=0,
            warnings=2,
        )

    monkeypatch.setattr(cli, "resolve_paper_run_dir", fake_resolve_paper_run_dir)
    monkeypatch.setattr(cli, "write_paper_leakage_check", fake_write_paper_leakage_check)

    result = CliRunner().invoke(app, ["paper-leakage-check", "p2a_test"])

    assert result.exit_code == 0
    assert "run id: p2a_test" in result.output
    assert "rows: 10" in result.output
    assert "warnings: 2" in result.output
