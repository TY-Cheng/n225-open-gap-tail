from pathlib import Path

import pytest
from typer.testing import CliRunner

import n225_open_gap_tail.cli as cli
from n225_open_gap_tail.cli import app
from n225_open_gap_tail.config.research import CORE_FRED_SERIES, CORE_MASSIVE_TICKERS
from n225_open_gap_tail.diagnostics.snapshot import SnapshotResult
from n225_open_gap_tail.forecasting import (
    EvaluationResult,
    LeakageCheckResult,
    PanelBuildResult,
    TableExportResult,
)
from n225_open_gap_tail.market.calendars import CalendarBuildResult
from n225_open_gap_tail.market.contracts import ContractMetadataResult
from n225_open_gap_tail.sources.cboe import CboeSmokeResult
from n225_open_gap_tail.sources.fred import FredSmokeResult
from n225_open_gap_tail.sources.jquants import JQuantsSmokeResult
from n225_open_gap_tail.sources.massive import MassiveSmokeResult
from n225_open_gap_tail.sources.probe import SourceProbeResult


def test_format_statuses_empty_mapping() -> None:
    assert cli._format_statuses({}) == "<none>"


def test_pipeline_commands_expose_help() -> None:
    runner = CliRunner()
    for command in (
        "build-panel",
        "evaluate",
        "export-tables",
        "leakage-check",
        "sensitivity",
        "source-probe",
    ):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert command in result.output


def test_source_probe_command_reports_provider_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "probe_sources",
        lambda settings: [
            SourceProbeResult("jquants", "ok", "futures_daily_probe rows=1", 200),
            SourceProbeResult("massive", "rate_limited", "too many requests", 429),
        ],
    )

    result = CliRunner().invoke(app, ["source-probe"])

    assert result.exit_code == 1
    assert "jquants: ok http=200 futures_daily_probe rows=1" in result.output
    assert "massive: rate_limited http=429 too many requests" in result.output


def test_source_probe_command_treats_optional_flatfile_probe_as_nonblocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "probe_sources",
        lambda settings: [
            SourceProbeResult("jquants", "ok", "futures_daily_probe rows=1", 200),
            SourceProbeResult(
                "massive_flatfiles:quotes_v1",
                "optional_entitlement_unavailable",
                "quotes unavailable",
                403,
            ),
        ],
    )

    result = CliRunner().invoke(app, ["source-probe"])

    assert result.exit_code == 0
    assert "massive_flatfiles:quotes_v1: optional_entitlement_unavailable" in result.output


def test_status_reports_environment_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    bronze_dir = data_dir / "bronze"
    silver_dir = data_dir / "silver"
    gold_dir = data_dir / "gold"
    reports_dir = tmp_path / "reports"
    massive_key_file = tmp_path / "massive.keyfile"
    massive_flat_file_key_file = tmp_path / "massive-flat-file.keyfile"
    jquants_key_file = tmp_path / "jquants.keyfile"
    massive_key_file.write_text("massive-secret\n", encoding="utf-8")
    massive_flat_file_key_file.write_text("massive-flat-file-secret\n", encoding="utf-8")
    jquants_key_file.write_text("jquants-secret\n", encoding="utf-8")
    for directory in (data_dir, bronze_dir, silver_dir, gold_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "${HOME}/.venvs/n225-open-gap-tail")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BRONZE_DATA_DIR", str(bronze_dir))
    monkeypatch.setenv("SILVER_DATA_DIR", str(silver_dir))
    monkeypatch.setenv("GOLD_DATA_DIR", str(gold_dir))
    monkeypatch.setenv("REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("MASSIVE_DAILY_TICKERS", ",".join(CORE_MASSIVE_TICKERS))
    monkeypatch.setenv("FRED_SERIES", ",".join(CORE_FRED_SERIES))
    monkeypatch.setenv("MASSIVE_API_KEY", "ignored-direct-massive-secret")
    monkeypatch.setenv("MASSIVE_API_KEY_FILE", str(massive_key_file))
    monkeypatch.setenv("MASSIVE_FLAT_FILE_KEY", "ignored-direct-flat-file-secret")
    monkeypatch.setenv("MASSIVE_FLAT_FILE_KEY_FILE", str(massive_flat_file_key_file))
    monkeypatch.setenv("JQUANTS_API_KEY", "ignored-direct-jquants-secret")
    monkeypatch.setenv("JQUANTS_API_KEY_FILE", str(jquants_key_file))
    monkeypatch.setenv("JQUANTS_DERIVATIVES_DAILY_ENABLED", "false")
    monkeypatch.setenv("JQUANTS_DERIVATIVES_INTRADAY_ENABLED", "false")
    monkeypatch.setenv("JPX_DATACUBE_EMAIL", "researcher@example.com")

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "project: n225-open-gap-tail" in result.output
    assert "uv environment: ${HOME}/.venvs/n225-open-gap-tail" in result.output
    assert f"  - {data_dir}: ok" in result.output
    assert f"  - {bronze_dir}: ok" in result.output
    assert f"  - {silver_dir}: ok" in result.output
    assert f"  - {gold_dir}: ok" in result.output
    assert "data/raw" not in result.output
    assert "data/interim" not in result.output
    assert "data/processed" not in result.output
    assert "massive api key file configured: True" in result.output
    assert "massive flat-file key file configured: True" in result.output
    assert "massive api base url: https://api.massive.com" in result.output
    assert "massive daily ticker count: 20" in result.output
    assert "massive minute ticker: SPY" in result.output
    assert "massive probe ticker count: 1" in result.output
    assert "fred base url: https://fred.stlouisfed.org" in result.output
    assert "fred series count: 4" in result.output
    assert "calendar us exchange: XNYS" in result.output
    assert "calendar jpx exchange: JPX" in result.output
    assert "nikkei contract roll days before last trade: 5" in result.output
    assert "j-quants api base url: https://api.jquants.com/v2" in result.output
    assert "j-quants api key file configured: True" in result.output
    assert "j-quants required plan: premium" in result.output
    assert "j-quants equity master enabled: True" in result.output
    assert "j-quants equity daily enabled: True" in result.output
    assert "j-quants derivatives daily enabled: False" in result.output
    assert "j-quants derivatives intraday enabled: False" in result.output
    assert "jpx datacube email configured: True" in result.output
    assert "massive-secret" not in result.output
    assert "massive-flat-file-secret" not in result.output
    assert "jquants-secret" not in result.output
    assert "ignored-direct" not in result.output
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
    bronze_path = tmp_path / "massive_smoke.json"
    daily_path = tmp_path / "massive_daily.parquet"
    minute_path = tmp_path / "massive_minute.parquet"

    def fake_write_massive_smoke_sample(**kwargs: object) -> MassiveSmokeResult:
        assert kwargs["tickers"] == ("SPY", "QQQ")
        assert kwargs["probe_tickers"] == ("I:VIX",)
        return MassiveSmokeResult(
            bronze_payload_path=bronze_path,
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
    assert f"bronze payload wrote: {bronze_path}" in result.output
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
    bronze_path = tmp_path / "fred_smoke.json"
    parquet_path = tmp_path / "fred.parquet"

    def fake_write_fred_smoke_sample(**kwargs: object) -> FredSmokeResult:
        assert kwargs["series_ids"] == ("VIXCLS", "DGS10")
        return FredSmokeResult(
            bronze_payload_path=bronze_path,
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
    assert f"bronze payload wrote: {bronze_path}" in result.output
    assert f"parquet wrote: {parquet_path}" in result.output
    assert "rows: 4" in result.output
    assert "series statuses: VIXCLS=200, DGS10=200" in result.output
    assert "series rows: VIXCLS=2, DGS10=2" in result.output


def test_cboe_smoke_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bronze_path = tmp_path / "cboe_smoke.json"
    parquet_path = tmp_path / "cboe.parquet"
    consistency_path = tmp_path / "cboe_consistency.parquet"

    def fake_write_cboe_smoke_sample(**kwargs: object) -> CboeSmokeResult:
        assert kwargs["symbols"] == ("VIX", "VIX9D")
        return CboeSmokeResult(
            bronze_payload_path=bronze_path,
            parquet_path=parquet_path,
            consistency_path=consistency_path,
            rows=4,
            symbols_statuses={"VIX": 200, "VIX9D": 200},
            symbols_rows={"VIX": 2, "VIX9D": 2},
            consistency_warnings=1,
        )

    monkeypatch.setattr(cli, "write_cboe_smoke_sample", fake_write_cboe_smoke_sample)

    result = CliRunner().invoke(
        app,
        [
            "cboe-smoke",
            "--symbols",
            "VIX,VIX9D",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
        ],
    )

    assert result.exit_code == 0
    assert f"bronze payload wrote: {bronze_path}" in result.output
    assert f"parquet wrote: {parquet_path}" in result.output
    assert f"consistency parquet wrote: {consistency_path}" in result.output
    assert "rows: 4" in result.output
    assert "symbol statuses: VIX=200, VIX9D=200" in result.output
    assert "symbol rows: VIX=2, VIX9D=2" in result.output
    assert "vix consistency warnings: 1" in result.output


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


def test_snapshot_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "tailrisk_run"
    docs_results = tmp_path / "docs" / "results_snapshot.md"

    def fake_write_results_snapshot_from_run(**kwargs: object) -> SnapshotResult:
        assert kwargs["run_id"] == "latest"
        return SnapshotResult(
            snapshot_id="tailrisk_latest",
            snapshot_dir=snapshot_dir,
            docs_results_path=docs_results,
            target_rows=250,
            model_status="completed_lightgbm_ml_tail_models",
        )

    monkeypatch.setattr(
        cli,
        "write_results_snapshot_from_run",
        fake_write_results_snapshot_from_run,
    )

    result = CliRunner().invoke(app, ["snapshot"])

    assert result.exit_code == 0
    assert "run id: tailrisk_latest" in result.output
    assert f"run dir: {snapshot_dir}" in result.output
    assert f"docs results snapshot: {docs_results}" in result.output
    assert "gold panel rows: 250" in result.output
    assert "model status: completed_lightgbm_ml_tail_models" in result.output


def test_build_panel_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"
    panel_path = run_dir / "panel" / "modeling_panel.parquet"

    def fake_build_panel(**kwargs: object) -> PanelBuildResult:
        assert kwargs["start"] == "2016-07-19"
        assert kwargs["end"] is None
        return PanelBuildResult(
            run_id="tailrisk_test",
            run_dir=run_dir,
            panel_path=panel_path,
            rows=100,
            clean_rows=90,
        )

    monkeypatch.setattr(cli, "build_panel", fake_build_panel)

    result = CliRunner().invoke(app, ["build-panel"])

    assert result.exit_code == 0
    assert "run id: tailrisk_test" in result.output
    assert f"run dir: {run_dir}" in result.output
    assert "rows: 100" in result.output
    assert "clean rows: 90" in result.output


def test_evaluate_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"

    def fake_resolve_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == "tailrisk_test"
        return run_dir

    def fake_evaluate_suite(**kwargs: object) -> EvaluationResult:
        assert kwargs["run_dir"] == run_dir
        assert kwargs["workers"] == 2
        assert kwargs["suite"] == "benchmark"
        assert kwargs["force"] is False
        return EvaluationResult(
            run_id="tailrisk_test",
            run_dir=run_dir,
            forecast_rows=50,
            metric_rows=6,
            status="completed",
        )

    monkeypatch.setattr(cli, "resolve_run_dir", fake_resolve_run_dir)
    monkeypatch.setattr(cli, "evaluate_suite", fake_evaluate_suite)

    result = CliRunner().invoke(
        app,
        ["evaluate", "--run-id", "tailrisk_test", "--workers", "2"],
    )

    assert result.exit_code == 0
    assert "forecast rows: 50" in result.output
    assert "metric rows: 6" in result.output
    assert "status: completed" in result.output


def test_sensitivity_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"

    def fake_resolve_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == "tailrisk_test"
        return run_dir

    def fake_evaluate_suite(**kwargs: object) -> EvaluationResult:
        assert kwargs["run_dir"] == run_dir
        assert kwargs["workers"] == 3
        assert kwargs["suite"] == "sensitivity"
        assert kwargs["force"] is False
        return EvaluationResult(
            run_id="tailrisk_test",
            run_dir=run_dir,
            forecast_rows=123,
            metric_rows=45,
            status="ok",
        )

    monkeypatch.setattr(cli, "resolve_run_dir", fake_resolve_run_dir)
    monkeypatch.setattr(cli, "evaluate_suite", fake_evaluate_suite)

    result = CliRunner().invoke(
        app,
        ["sensitivity", "--run-id", "tailrisk_test", "--workers", "3"],
    )

    assert result.exit_code == 0
    assert "sensitivity forecast rows: 123" in result.output
    assert "sensitivity metric rows: 45" in result.output
    assert "status: ok" in result.output


def test_run_command_runs_panel_eval_and_latex(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"

    def fake_build_panel(**kwargs: object) -> PanelBuildResult:
        return PanelBuildResult(
            run_id="tailrisk_test",
            run_dir=run_dir,
            panel_path=run_dir / "panel" / "modeling_panel.parquet",
            rows=100,
            clean_rows=90,
        )

    def fake_evaluate_suite(**kwargs: object) -> EvaluationResult:
        assert kwargs["suite"] == "benchmark"
        return EvaluationResult(
            run_id="tailrisk_test",
            run_dir=run_dir,
            forecast_rows=50,
            metric_rows=6,
            status="completed",
        )

    def fake_export_tables(**kwargs: object) -> TableExportResult:
        return TableExportResult(
            run_id="tailrisk_test",
            latex_dir=run_dir / "latex" / "tables",
            tables=1,
        )

    def fake_write_leakage_check(**kwargs: object) -> LeakageCheckResult:
        assert kwargs["run_dir"] == run_dir
        return LeakageCheckResult(
            run_id="tailrisk_test",
            output_path=run_dir / "audits" / "leakage_check.parquet",
            rows=100,
            failures=0,
            warnings=0,
        )

    monkeypatch.setattr(cli, "build_panel", fake_build_panel)
    monkeypatch.setattr(cli, "write_leakage_check", fake_write_leakage_check)
    monkeypatch.setattr(cli, "evaluate_suite", fake_evaluate_suite)
    monkeypatch.setattr(cli, "export_tables", fake_export_tables)

    result = CliRunner().invoke(app, ["run", "--workers", "1", "--suite", "benchmark"])

    assert result.exit_code == 0
    assert "panel rows: 100" in result.output
    assert "forecast rows: 50" in result.output
    assert "eval status: completed" in result.output
    assert "latex tables: 1" in result.output


def test_export_tables_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"

    def fake_resolve_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == ""
        return run_dir

    def fake_export_tables(**kwargs: object) -> TableExportResult:
        assert kwargs["run_dir"] == run_dir
        return TableExportResult(
            run_id="tailrisk_latest",
            latex_dir=run_dir / "latex" / "tables",
            tables=1,
        )

    monkeypatch.setattr(cli, "resolve_run_dir", fake_resolve_run_dir)
    monkeypatch.setattr(cli, "export_tables", fake_export_tables)

    result = CliRunner().invoke(app, ["export-tables"])

    assert result.exit_code == 0
    assert "run id: tailrisk_latest" in result.output
    assert "tables: 1" in result.output


def test_leakage_check_command_reports_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "tailrisk_run"
    output_path = run_dir / "audits" / "leakage_check.parquet"

    def fake_resolve_run_dir(settings: object, run_id: str) -> Path:
        assert run_id == "tailrisk_test"
        return run_dir

    def fake_write_leakage_check(**kwargs: object) -> LeakageCheckResult:
        assert kwargs["run_dir"] == run_dir
        return LeakageCheckResult(
            run_id="tailrisk_test",
            output_path=output_path,
            rows=10,
            failures=0,
            warnings=2,
        )

    monkeypatch.setattr(cli, "resolve_run_dir", fake_resolve_run_dir)
    monkeypatch.setattr(cli, "write_leakage_check", fake_write_leakage_check)

    result = CliRunner().invoke(app, ["leakage-check", "tailrisk_test"])

    assert result.exit_code == 0
    assert "run id: tailrisk_test" in result.output
    assert "rows: 10" in result.output
    assert "warnings: 2" in result.output
