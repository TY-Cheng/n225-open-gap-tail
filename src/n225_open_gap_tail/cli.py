import os
from pathlib import Path

import typer

from n225_open_gap_tail.calendars import write_calendar_table
from n225_open_gap_tail.config import load_settings, split_csv
from n225_open_gap_tail.contracts import write_contract_metadata
from n225_open_gap_tail.datalake import MAIN_SAMPLE_START
from n225_open_gap_tail.fred import write_fred_smoke_sample
from n225_open_gap_tail.jquants import write_jquants_smoke_sample
from n225_open_gap_tail.massive import write_massive_smoke_sample
from n225_open_gap_tail.paper import (
    evaluate_paper_run,
    resolve_paper_run_dir,
    write_paper_latex_tables,
    write_paper_leakage_check,
    write_paper_panel,
)
from n225_open_gap_tail.snapshot import write_full_smoke_snapshot

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Command-line helpers for the research project."""


@app.command()
def status() -> None:
    """Print a local project status summary without exposing secrets."""
    settings = load_settings()
    uv_env = os.environ.get("UV_PROJECT_ENVIRONMENT", "")
    expanded_uv_env = os.path.expandvars(uv_env)

    typer.echo(f"project: {settings.project_name}")
    typer.echo(f"uv environment: {uv_env or '<unset>'}")
    typer.echo(f"uv environment resolved: {expanded_uv_env or '<unset>'}")
    typer.echo(f"python cwd: {Path.cwd()}")
    typer.echo(f"japan timezone: {settings.project_timezone_jp}")
    typer.echo(f"us timezone: {settings.project_timezone_us}")
    typer.echo("directories:")
    for directory in settings.required_directories():
        typer.echo(f"  - {directory}: {'ok' if directory.exists() else 'missing'}")
    typer.echo(f"massive api key configured: {bool(settings.massive_api_key)}")
    typer.echo(f"massive api base url: {settings.massive_base_url}")
    typer.echo(f"massive daily ticker count: {len(settings.massive_daily_ticker_list())}")
    typer.echo(f"massive minute ticker: {settings.massive_minute_ticker}")
    typer.echo(f"massive probe ticker count: {len(settings.massive_probe_ticker_list())}")
    typer.echo(f"fred base url: {settings.fred_base_url}")
    typer.echo(f"fred series count: {len(settings.fred_series_list())}")
    typer.echo(f"calendar us exchange: {settings.calendar_us_exchange}")
    typer.echo(f"calendar jpx exchange: {settings.calendar_jpx_exchange}")
    typer.echo(
        "nikkei contract roll days before last trade: "
        f"{settings.nikkei_contract_roll_days_before_last_trade}"
    )
    typer.echo(f"j-quants api version: {settings.jquants_api_version}")
    typer.echo(f"j-quants api base url: {settings.jquants_api_base_url}")
    typer.echo(f"j-quants api key configured: {bool(settings.jquants_api_key)}")
    typer.echo(f"j-quants api plan: {settings.jquants_api_plan}")
    typer.echo(f"j-quants equity master enabled: {settings.jquants_equity_master_enabled}")
    typer.echo(f"j-quants equity daily enabled: {settings.jquants_equity_daily_enabled}")
    typer.echo(f"j-quants derivatives daily enabled: {settings.jquants_derivatives_daily_enabled}")
    typer.echo(
        f"j-quants derivatives intraday enabled: {settings.jquants_derivatives_intraday_enabled}"
    )
    typer.echo(f"jpx datacube email configured: {bool(settings.jpx_datacube_email)}")


@app.command("jquants-smoke")
def jquants_smoke(
    code: str = typer.Option("72030", help="J-Quants 5-digit issue code."),
    start: str = typer.Option("2025-12-01", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("2025-12-05", help="End date in YYYY-MM-DD."),
    futures_date: str = typer.Option("2025-12-01", help="Futures probe date in YYYY-MM-DD."),
) -> None:
    """Download a small J-Quants V2 smoke sample into ignored raw data."""
    settings = load_settings()
    result = write_jquants_smoke_sample(
        settings=settings,
        code=code,
        start=start,
        end=end,
        futures_date=futures_date,
    )

    typer.echo(f"wrote: {result.output_path}")
    typer.echo(f"equity master rows: {result.equity_master_rows}")
    typer.echo(f"equity daily rows: {result.equity_daily_rows}")
    typer.echo(f"futures probe status: {result.futures_probe_status}")
    typer.echo(f"futures probe rows: {result.futures_probe_rows}")


@app.command("massive-smoke")
def massive_smoke(
    tickers: str = typer.Option(
        "",
        help="Comma-separated Massive tickers. Defaults to MASSIVE_DAILY_TICKERS.",
    ),
    start: str = typer.Option("2026-01-05", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("2026-01-09", help="End date in YYYY-MM-DD."),
    minute_ticker: str = typer.Option(
        "",
        help="Ticker for a one-day minute aggregate smoke pull.",
    ),
    minute_date: str = typer.Option("2026-01-05", help="Minute aggregate date in YYYY-MM-DD."),
    probe_tickers: str = typer.Option(
        "",
        help="Comma-separated optional tickers to probe without failing on 403.",
    ),
) -> None:
    """Download a small Massive.com predictor sample into ignored data folders."""
    settings = load_settings()
    ticker_list = split_csv(tickers) or settings.massive_daily_ticker_list()
    probe_ticker_list = split_csv(probe_tickers) or settings.massive_probe_ticker_list()
    result = write_massive_smoke_sample(
        settings=settings,
        tickers=ticker_list,
        start=start,
        end=end,
        minute_ticker=minute_ticker or settings.massive_minute_ticker,
        minute_date=minute_date,
        probe_tickers=probe_ticker_list,
    )

    typer.echo(f"bronze payload wrote: {result.bronze_payload_path}")
    typer.echo(f"daily parquet wrote: {result.daily_parquet_path}")
    typer.echo(f"minute parquet wrote: {result.minute_parquet_path}")
    typer.echo(f"daily rows: {result.daily_rows}")
    typer.echo(f"minute rows: {result.minute_rows}")
    typer.echo(f"minute regular-session rows: {result.minute_regular_session_rows}")
    typer.echo(f"daily statuses: {_format_statuses(result.daily_statuses)}")
    typer.echo(f"minute status: {result.minute_status}")
    typer.echo(f"probe statuses: {_format_statuses(result.probe_statuses)}")


@app.command("fred-smoke")
def fred_smoke(
    series: str = typer.Option(
        "",
        help="Comma-separated FRED series. Defaults to FRED_SERIES.",
    ),
    start: str = typer.Option("2026-01-05", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("2026-01-09", help="End date in YYYY-MM-DD."),
) -> None:
    """Download historical VIX/rates predictors from FRED into ignored data folders."""
    settings = load_settings()
    series_ids = split_csv(series) or settings.fred_series_list()
    result = write_fred_smoke_sample(
        settings=settings,
        series_ids=series_ids,
        start=start,
        end=end,
    )

    typer.echo(f"bronze payload wrote: {result.bronze_payload_path}")
    typer.echo(f"parquet wrote: {result.parquet_path}")
    typer.echo(f"rows: {result.rows}")
    typer.echo(f"series statuses: {_format_statuses(result.series_statuses)}")
    typer.echo(f"series rows: {_format_statuses(result.series_rows)}")


@app.command("calendar-build")
def calendar_build(
    start: str = typer.Option("2026-01-01", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("2026-01-31", help="End date in YYYY-MM-DD."),
) -> None:
    """Build U.S./JPX session, early-close, holiday, and DST alignment table."""
    settings = load_settings()
    result = write_calendar_table(settings=settings, start=start, end=end)

    typer.echo(f"metadata wrote: {result.metadata_path}")
    typer.echo(f"parquet wrote: {result.parquet_path}")
    typer.echo(f"rows: {result.rows}")
    typer.echo(f"us trading days: {result.us_trading_days}")
    typer.echo(f"jpx trading days: {result.jpx_trading_days}")
    typer.echo(f"us early closes: {result.us_early_closes}")


@app.command("contracts-build")
def contracts_build(
    start: str = typer.Option("2026-01-01", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("2026-12-31", help="End date in YYYY-MM-DD."),
) -> None:
    """Build rule-based Nikkei 225 futures contract metadata and central selector."""
    settings = load_settings()
    result = write_contract_metadata(settings=settings, start=start, end=end)

    typer.echo(f"metadata wrote: {result.metadata_path}")
    typer.echo(f"contracts parquet wrote: {result.contracts_path}")
    typer.echo(f"selector parquet wrote: {result.selector_path}")
    typer.echo(f"contracts: {result.contracts}")
    typer.echo(f"selector rows: {result.selector_rows}")
    typer.echo(f"roll-window rows: {result.roll_window_rows}")


@app.command("snapshot")
def snapshot(
    start: str = typer.Option("2022-01-01", help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("", help="End date in YYYY-MM-DD. Defaults to today."),
) -> None:
    """Run the 2022-present full-smoke results snapshot."""
    settings = load_settings()
    result = write_full_smoke_snapshot(
        settings=settings,
        start=start,
        end=end or None,
    )

    typer.echo(f"snapshot id: {result.snapshot_id}")
    typer.echo(f"snapshot dir: {result.snapshot_dir}")
    typer.echo(f"docs results snapshot: {result.docs_results_path}")
    typer.echo(f"target rows: {result.target_rows}")
    typer.echo(f"model status: {result.model_status}")


@app.command("paper-panel")
def paper_panel(
    start: str = typer.Option(MAIN_SAMPLE_START, help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("", help="End date in YYYY-MM-DD. Defaults to today."),
) -> None:
    """Build the paper-grade full-history modeling panel."""
    settings = load_settings()
    result = write_paper_panel(settings=settings, start=start, end=end or None)

    typer.echo(f"run id: {result.run_id}")
    typer.echo(f"run dir: {result.run_dir}")
    typer.echo(f"panel parquet: {result.panel_path}")
    typer.echo(f"rows: {result.rows}")
    typer.echo(f"clean rows: {result.clean_rows}")


@app.command("paper-eval")
def paper_eval(
    run_id: str = typer.Option("", help="Paper run id. Defaults to the latest P2A run."),
    workers: int = typer.Option(0, help="Joblib workers. Defaults to bounded local workers."),
    stage: str = typer.Option("p2a", help="Evaluation stage: p2a, p2b, or p2c."),
    force: bool = typer.Option(False, help="Clear locked outputs when config hash changed."),
) -> None:
    """Run paper-grade evaluation for a paper run."""
    settings = load_settings()
    run_dir = resolve_paper_run_dir(settings, run_id)
    result = evaluate_paper_run(run_dir=run_dir, workers=workers, stage=stage, force=force)

    typer.echo(f"run id: {result.run_id}")
    typer.echo(f"run dir: {result.run_dir}")
    typer.echo(f"forecast rows: {result.forecast_rows}")
    typer.echo(f"metric rows: {result.metric_rows}")
    typer.echo(f"status: {result.status}")


@app.command("paper-grade")
def paper_grade(
    start: str = typer.Option(MAIN_SAMPLE_START, help="Start date in YYYY-MM-DD."),
    end: str = typer.Option("", help="End date in YYYY-MM-DD. Defaults to today."),
    workers: int = typer.Option(0, help="Joblib workers. Defaults to bounded local workers."),
    stage: str = typer.Option("p2a", help="Evaluation stage: p2a, p2b, p2c, or all."),
    force: bool = typer.Option(False, help="Clear locked outputs when config hash changed."),
) -> None:
    """Build the paper panel, run requested evaluation stages, and export LaTeX tables."""
    settings = load_settings()
    panel = write_paper_panel(settings=settings, start=start, end=end or None)
    stages = ("p2a", "p2b", "p2c") if stage == "all" else (stage,)
    evaluation = None
    for active_stage in stages:
        if active_stage == "p2b":
            write_paper_leakage_check(run_dir=panel.run_dir)
        evaluation = evaluate_paper_run(
            run_dir=panel.run_dir,
            workers=workers,
            stage=active_stage,
            force=force,
        )
    latex = write_paper_latex_tables(run_dir=panel.run_dir)

    typer.echo(f"run id: {panel.run_id}")
    typer.echo(f"run dir: {panel.run_dir}")
    typer.echo(f"panel rows: {panel.rows}")
    typer.echo(f"forecast rows: {evaluation.forecast_rows if evaluation else 0}")
    typer.echo(f"metric rows: {evaluation.metric_rows if evaluation else 0}")
    typer.echo(f"eval status: {evaluation.status if evaluation else '<none>'}")
    typer.echo(f"latex tables: {latex.tables}")


@app.command("paper-latex-tables")
def paper_latex_tables(
    run_id: str = typer.Option("", help="Paper run id. Defaults to the latest P2A run."),
) -> None:
    """Export paper-run metrics to LaTeX table fragments."""
    settings = load_settings()
    run_dir = resolve_paper_run_dir(settings, run_id)
    result = write_paper_latex_tables(run_dir=run_dir)

    typer.echo(f"run id: {result.run_id}")
    typer.echo(f"latex dir: {result.latex_dir}")
    typer.echo(f"tables: {result.tables}")


@app.command("paper-leakage-check")
def paper_leakage_check(
    run_id: str = typer.Argument("", help="Paper run id. Defaults to the latest P2A run."),
) -> None:
    """Audit feature timestamp availability against model cutoff and target open."""
    settings = load_settings()
    run_dir = resolve_paper_run_dir(settings, run_id)
    result = write_paper_leakage_check(run_dir=run_dir)

    typer.echo(f"run id: {result.run_id}")
    typer.echo(f"leakage parquet: {result.output_path}")
    typer.echo(f"rows: {result.rows}")
    typer.echo(f"failures: {result.failures}")
    typer.echo(f"warnings: {result.warnings}")


def _format_statuses(statuses: dict[str, int]) -> str:
    if not statuses:
        return "<none>"
    return ", ".join(f"{ticker}={status}" for ticker, status in statuses.items())
