from __future__ import annotations

import json
import math
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from joblib import Parallel, delayed  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]

from n225_open_gap_tail.calendars import build_session_calendar_records
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.fred import FredClient, normalize_fred_rows
from n225_open_gap_tail.jquants import JQuantsV2Client
from n225_open_gap_tail.massive import MassiveClient, normalize_aggregate_bars
from n225_open_gap_tail.snapshot import (
    build_jquants_schema_probe,
    build_target_audit_records,
    build_time_alignment_records,
    normalize_jquants_futures_rows,
)

PAPER_CLAIMS_LEVEL = "paper_grade_candidate_not_final_manuscript"
PAPER_CORE_MASSIVE_TICKERS = (
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "TLT",
    "GLD",
    "USO",
    "EEM",
    "FXI",
    "SMH",
    "C:USDJPY",
)
PAPER_CORE_FRED_SERIES = (
    "VIXCLS",
    "DGS2",
    "DGS10",
    "T10Y2Y",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "SOFR",
    "EFFR",
)
PAPER_TAIL_LEVELS = (0.95, 0.975)
EWMA_MAIN_LAMBDA = 0.94
EWMA_SENSITIVITY_LAMBDAS = (0.90, 0.97)
DEFAULT_MIN_TRAIN_ROWS = 1000
DEFAULT_MIN_TRAIN_EXCEEDANCES = 50
DEFAULT_EARLIEST_OOS_START = "2016-01-01"
LOW_VARIANCE_THRESHOLD = 1e-8
SHARD_SIZE_FORECAST_DATES = 50
EVT_THRESHOLD_QUANTILE = 0.90
EVT_THRESHOLD_GRID = (0.90, 0.925, 0.95)


@dataclass(frozen=True)
class PaperPanelResult:
    run_id: str
    run_dir: Path
    panel_path: Path
    rows: int
    clean_rows: int


@dataclass(frozen=True)
class PaperEvalResult:
    run_id: str
    run_dir: Path
    forecast_rows: int
    metric_rows: int
    status: str


@dataclass(frozen=True)
class PaperLatexResult:
    run_id: str
    latex_dir: Path
    tables: int


class PaperRunError(RuntimeError):
    """Raised when a paper-grade run cannot satisfy an execution gate."""


def build_paper_run_id(
    *,
    start: str,
    end: str,
    run_ts_utc: datetime,
    git_commit: str,
    stage: str = "p2a",
) -> str:
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    compact_ts = run_ts_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stage}_{clean_start}_{clean_end}_{compact_ts}_commit_{git_commit[:8]}"


def validate_worker_payload(payload: dict[str, object]) -> None:
    """Reject large frame-like objects before dispatching joblib work."""
    for key, value in payload.items():
        if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
            raise PaperRunError(f"Worker payload {key!r} must be a path/config, not a Polars frame")
        module = type(value).__module__
        name = type(value).__name__
        if module.startswith("pandas") or name in {"DataFrame", "Series"}:
            raise PaperRunError(f"Worker payload {key!r} must not be a pandas object")


def find_oos_start_date(
    rows: list[dict[str, object]],
    *,
    earliest_oos_start: str | None = None,
    min_train_rows: int | None = None,
    min_train_exceedances: int | None = None,
    tail_level: float = 0.95,
) -> str | None:
    earliest_oos_start = earliest_oos_start or DEFAULT_EARLIEST_OOS_START
    min_train_rows = min_train_rows if min_train_rows is not None else DEFAULT_MIN_TRAIN_ROWS
    min_train_exceedances = (
        min_train_exceedances
        if min_train_exceedances is not None
        else DEFAULT_MIN_TRAIN_EXCEEDANCES
    )
    clean = _clean_loss_rows(rows)
    earliest = date.fromisoformat(earliest_oos_start)
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < earliest:
            continue
        train_losses: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        if train_losses.size < min_train_rows:
            continue
        threshold = float(np.quantile(train_losses, tail_level))
        exceedances = int(np.sum(train_losses > threshold))
        if exceedances >= min_train_exceedances:
            return forecast_date.isoformat()
    return None


def validate_forecast_values(var_forecast: float, es_forecast: float) -> tuple[bool, str | None]:
    if not math.isfinite(var_forecast) or not math.isfinite(es_forecast):
        return False, "invalid_nonfinite_forecast"
    if es_forecast < var_forecast:
        return False, "invalid_es_below_var"
    return True, None


def static_empirical_es(train_losses: np.ndarray, var_forecast: float) -> float:
    exceedances = train_losses[train_losses > var_forecast]
    if exceedances.size == 0:
        return float(var_forecast)
    return float(max(var_forecast, np.mean(exceedances)))


def empirical_excess_es_companion(
    *,
    train_losses: np.ndarray,
    train_var_forecasts: np.ndarray,
    forecast_var: float,
) -> float:
    exceedance_excess = train_losses[train_losses > train_var_forecasts] - train_var_forecasts[
        train_losses > train_var_forecasts
    ]
    if exceedance_excess.size == 0:
        return float(forecast_var)
    return float(max(forecast_var, forecast_var + np.mean(exceedance_excess)))


def filtered_historical_es(
    *,
    location_forecast: float,
    scale_forecast: float,
    standardized_train_losses: np.ndarray,
    standardized_var: float,
) -> float:
    exceedances = standardized_train_losses[standardized_train_losses > standardized_var]
    standardized_es = standardized_var if exceedances.size == 0 else float(np.mean(exceedances))
    var_forecast = location_forecast + scale_forecast * standardized_var
    es_forecast = location_forecast + scale_forecast * standardized_es
    return float(max(var_forecast, es_forecast))


def drop_low_variance_features(
    frame: pl.DataFrame,
    feature_columns: list[str],
    *,
    threshold: float = LOW_VARIANCE_THRESHOLD,
) -> tuple[list[str], list[str]]:
    active: list[str] = []
    dropped: list[str] = []
    for column in feature_columns:
        if column not in frame.columns:
            dropped.append(column)
            continue
        std_value = frame.select(pl.col(column).std()).item()
        if std_value is None or not math.isfinite(float(std_value)) or float(std_value) < threshold:
            dropped.append(column)
        else:
            active.append(column)
    return active, dropped


def global_oos_intersection(
    rows: list[dict[str, object]],
    *,
    model_names: tuple[str, ...],
) -> list[str]:
    by_model: dict[str, set[str]] = {model: set() for model in model_names}
    for row in rows:
        model = str(row.get("model_name"))
        if model in by_model and row.get("fit_status") == "ok":
            by_model[model].add(str(row["forecast_date"]))
    if not by_model:
        return []
    common = set.intersection(*(dates for dates in by_model.values()))
    return sorted(common)


def write_paper_panel(
    *,
    settings: Settings,
    start: str = "2008-05-07",
    end: str | None = None,
) -> PaperPanelResult:
    run_ts = datetime.now(UTC)
    end_date = end or date.today().isoformat()
    git_commit = _git_commit()
    run_id = build_paper_run_id(
        start=start,
        end=end_date,
        run_ts_utc=run_ts,
        git_commit=git_commit,
        stage="p2a",
    )
    run_dir = settings.reports_dir / "paper_runs" / run_id
    panel_dir = run_dir / "panel"
    config_dir = run_dir / "config"
    panel_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    calendar_records = build_session_calendar_records(
        start=(date.fromisoformat(start) - timedelta(days=10)).isoformat(),
        end=end_date,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )
    jquants_pull_ts = datetime.now(UTC)
    raw_jquants = _fetch_jquants_futures_rows(
        settings=settings,
        start=start,
        end=end_date,
        calendar_records=calendar_records,
    )
    schema_probe = build_jquants_schema_probe(raw_jquants)
    if schema_probe["fail_closed"] is True:
        raise PaperRunError(
            f"J-Quants schema missing required fields: {schema_probe['missing_required_fields']}"
        )
    normalized = normalize_jquants_futures_rows(raw_jquants, downloaded_at_utc=jquants_pull_ts)
    targets = build_target_audit_records(
        normalized,
        calendar_records=calendar_records,
        roll_days_before_last_trade=settings.nikkei_contract_roll_days_before_last_trade,
    )

    massive_pull_ts = datetime.now(UTC)
    massive_daily, spy_minutes = _fetch_massive_paper_predictors(
        settings=settings,
        start=start,
        end=end_date,
        downloaded_at_utc=massive_pull_ts,
    )
    fred_pull_ts = datetime.now(UTC)
    fred_rows = _fetch_fred_paper_predictors(
        settings=settings,
        start=start,
        end=end_date,
        downloaded_at_utc=fred_pull_ts,
    )
    alignment = build_time_alignment_records(
        target_rows=targets,
        calendar_records=calendar_records,
        spy_minute_records=spy_minutes,
    )
    panel = build_modeling_panel_records(
        target_rows=targets,
        alignment_records=alignment,
        massive_daily_records=massive_daily,
        spy_minute_records=spy_minutes,
        fred_records=fred_rows,
    )
    feature_coverage = build_feature_coverage_records(panel)

    target_audit_path = panel_dir / "target_audit.parquet"
    panel_path = panel_dir / "modeling_panel.parquet"
    coverage_path = panel_dir / "feature_coverage.parquet"
    schema_path = panel_dir / "jquants_schema_probe.json"
    vintage_path = run_dir / "data_vintage.json"
    manifest_path = run_dir / "manifest.json"
    feature_dictionary_path = panel_dir / "feature_dictionary.json"

    _write_parquet(target_audit_path, targets)
    _write_parquet(panel_path, panel)
    _write_parquet(coverage_path, feature_coverage)
    _write_json(schema_path, schema_probe)
    _write_json(
        vintage_path,
        {
            "jquants_pull_ts_utc": jquants_pull_ts.isoformat(),
            "massive_pull_ts_utc": massive_pull_ts.isoformat(),
            "fred_pull_ts_utc": fred_pull_ts.isoformat(),
            "window": [start, end_date],
            "claims_level": PAPER_CLAIMS_LEVEL,
        },
    )
    _write_json(feature_dictionary_path, build_feature_dictionary(panel))
    _write_json(
        config_dir / "model_config.json",
        {
            "stage": "p2a",
            "tail_levels": PAPER_TAIL_LEVELS,
            "ewma_lambda": EWMA_MAIN_LAMBDA,
            "ewma_sensitivity_lambdas": EWMA_SENSITIVITY_LAMBDAS,
            "oos_start_policy": {
                "earliest_oos_start": DEFAULT_EARLIEST_OOS_START,
                "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                "min_train_exceedances_5pct": DEFAULT_MIN_TRAIN_EXCEEDANCES,
            },
        },
    )
    _write_json(
        manifest_path,
        {
            "run_id": run_id,
            "created_at_utc": run_ts.isoformat(),
            "git_commit": git_commit,
            "git_dirty": _git_dirty(),
            "claims_level": PAPER_CLAIMS_LEVEL,
            "stage": "p2a_panel",
            "window": [start, end_date],
            "feature_set_version": "core_full_history",
            "massive_symbols": PAPER_CORE_MASSIVE_TICKERS,
            "fred_series": PAPER_CORE_FRED_SERIES,
            "artifact_paths": {
                "modeling_panel": str(panel_path),
                "target_audit": str(target_audit_path),
                "feature_coverage": str(coverage_path),
                "feature_dictionary": str(feature_dictionary_path),
                "schema_probe": str(schema_path),
                "data_vintage": str(vintage_path),
            },
        },
    )
    clean_rows = sum(1 for row in panel if row.get("clean_sample") is True)
    return PaperPanelResult(
        run_id=run_id,
        run_dir=run_dir,
        panel_path=panel_path,
        rows=len(panel),
        clean_rows=clean_rows,
    )


def build_modeling_panel_records(
    *,
    target_rows: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    spy_minute_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    alignment_by_target = {str(row["trading_date"]): row for row in alignment_records}
    massive_features = _massive_daily_feature_map(massive_daily_records)
    fred_features = _fred_feature_map(fred_records)
    spy_features = _spy_minute_feature_map(spy_minute_records)
    panel: list[dict[str, object]] = []
    for target in target_rows:
        trading_date = str(target["trading_date"])
        alignment = alignment_by_target.get(trading_date, {})
        us_date = str(alignment.get("us_calendar_date") or "")
        record: dict[str, object] = {
            "forecast_date": trading_date,
            "target_family": "full_gap_settle_to_open",
            "forecast_origin_name": "US_CASH_CLOSE",
            "information_set": "core_full_history",
            "contract_code": target.get("contract_code"),
            "contract_month": target.get("contract_month"),
            "clean_sample": target.get("clean_sample"),
            "same_contract_flag": target.get("same_contract_only"),
            "roll_window_flag": target.get("is_roll_sq_window"),
            "sq_window_flag": target.get("is_roll_sq_window"),
            "missing_reason": target.get("missing_reason"),
            "target_open_ts_utc": target.get("target_open_ts_utc"),
            "model_cutoff_ts_utc": alignment.get("model_cutoff_ts_utc"),
            "dst_regime": alignment.get("dst_regime"),
            "absorption_regime": alignment.get("absorption_regime"),
            "us_calendar_date": us_date or None,
            "gap_t": target.get("full_gap_settle_to_open"),
            "realized_loss": target.get("loss_settle_to_open"),
            "full_gap_close_to_open": target.get("full_gap_close_to_open"),
            "residual_nightclose_to_day_open": target.get("residual_nightclose_to_day_open"),
            "volume": target.get("volume"),
            "open_interest": target.get("open_interest"),
            "volume_oi_anomaly": target.get("volume_oi_anomaly"),
        }
        record.update(massive_features.get(us_date, {}))
        record.update(fred_features.get(us_date, {}))
        record.update(spy_features.get(us_date, {}))
        panel.append(record)
    panel.sort(key=lambda row: str(row["forecast_date"]))
    return panel


def build_feature_coverage_records(panel: list[dict[str, object]]) -> list[dict[str, object]]:
    if not panel:
        return []
    base_fields = {
        "forecast_date",
        "target_family",
        "forecast_origin_name",
        "information_set",
        "contract_code",
        "contract_month",
        "clean_sample",
        "same_contract_flag",
        "roll_window_flag",
        "sq_window_flag",
        "missing_reason",
        "target_open_ts_utc",
        "model_cutoff_ts_utc",
        "dst_regime",
        "absorption_regime",
        "us_calendar_date",
        "gap_t",
        "realized_loss",
        "full_gap_close_to_open",
        "residual_nightclose_to_day_open",
        "volume",
        "open_interest",
        "volume_oi_anomaly",
    }
    clean_rows = [row for row in panel if row.get("clean_sample") is True]
    records: list[dict[str, object]] = []
    for field in sorted(set().union(*(row.keys() for row in panel)).difference(base_fields)):
        non_missing = sum(1 for row in clean_rows if row.get(field) is not None)
        records.append(
            {
                "feature": field,
                "clean_rows": len(clean_rows),
                "non_missing_rows": non_missing,
                "missingness_rate": 1.0 - non_missing / len(clean_rows) if clean_rows else None,
            }
        )
    return records


def build_feature_dictionary(panel: list[dict[str, object]]) -> dict[str, str]:
    return {
        field: _feature_description(field)
        for field in sorted(set().union(*(row.keys() for row in panel)) if panel else set())
        if field.endswith("_return")
        or field.endswith("_range")
        or field.endswith("_diff")
        or field.startswith("fred_")
        or field.startswith("spy_late_")
        or field.startswith("spy_final_")
    }


def evaluate_p2a_run(
    *,
    run_dir: Path,
    workers: int = 1,
) -> PaperEvalResult:
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    if not panel_path.exists():
        raise PaperRunError(f"Missing modeling panel: {panel_path}")
    _set_nested_thread_limits()
    forecast_root = run_dir / "forecasts"
    metrics_root = run_dir / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    jobs: list[dict[str, object]] = []
    for tail_level in PAPER_TAIL_LEVELS:
        for model_name in (
            "historical_quantile",
            "rolling_quantile",
            "ewma_vol_scaled",
            "garch_t",
            "gjr_garch_t",
            "gjr_garch_evt",
        ):
            jobs.append(
                {
                    "panel_path": str(panel_path),
                    "run_dir": str(run_dir),
                    "tail_level": tail_level,
                    "models": (model_name,),
                    "shard_id": _forecast_shard_id(model_name, tail_level),
                }
            )
    for payload in jobs:
        validate_worker_payload(payload)
    n_jobs = _bounded_workers(workers)
    if n_jobs == 1:
        outputs = [_evaluate_p2a_shard(payload) for payload in jobs]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend="loky")(
            delayed(_evaluate_p2a_shard)(payload) for payload in jobs
        )
    forecasts = [row for output in outputs for row in output["forecasts"]]
    diagnostics = [row for output in outputs for row in output["diagnostics"]]
    failures = [row for output in outputs for row in output["failures"]]
    forecast_path = forecast_root / "p2a_forecasts.parquet"
    diagnostics_path = forecast_root / "p2a_fit_diagnostics.parquet"
    failures_path = forecast_root / "p2a_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _write_parquet(diagnostics_path, diagnostics)
    _write_parquet(failures_path, failures)
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    metrics = build_metric_records(forecasts)
    _write_parquet(metrics_root / "p2a_metrics.parquet", metrics)
    _write_json(
        metrics_root / "p2a_status.json",
        {
            "claims_level": PAPER_CLAIMS_LEVEL,
            "stage": "p2a",
            "forecast_rows": len(forecasts),
            "metric_rows": len(metrics),
            "failures": len(failures),
        },
    )
    _update_manifest(run_dir, {"p2a_eval_status": "completed", "p2a_forecast_rows": len(forecasts)})
    return PaperEvalResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed",
    )


def build_metric_records(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float], list[dict[str, object]]] = {}
    for row in forecasts:
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True:
            grouped.setdefault(
                (str(row["model_name"]), _required_float(row["tail_level"])),
                [],
            ).append(row)
    records: list[dict[str, object]] = []
    for (model, tail_level), rows in sorted(grouped.items()):
        losses: Any = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var: Any = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        es: Any = np.array([_required_float(row["es_forecast"]) for row in rows], dtype=float)
        breaches = losses > var
        records.append(
            {
                "model_name": model,
                "tail_level": tail_level,
                "rows": len(rows),
                "var_breach_rate": float(np.mean(breaches)) if rows else None,
                "expected_breach_rate": 1.0 - tail_level,
                "mean_quantile_loss": _safe_mean(
                    np.array(
                        [
                            quantile_loss(loss, forecast, tail_level)
                            for loss, forecast in zip(losses, var, strict=True)
                        ]
                    )
                ),
                "mean_fz_loss": _safe_mean(
                    np.array(
                        [
                            fz_loss(loss, var_value, es_value, tail_level)
                            for loss, var_value, es_value in zip(
                                losses,
                                var,
                                es,
                                strict=True,
                            )
                        ]
                    )
                ),
                "mean_exceedance_severity": float(np.mean(losses[breaches] - var[breaches]))
                if np.any(breaches)
                else None,
            }
        )
    return records


def quantile_loss(loss: float, var_forecast: float, tail_level: float) -> float:
    alpha = 1.0 - tail_level
    indicator = 1.0 if loss > var_forecast else 0.0
    return float((indicator - alpha) * (loss - var_forecast))


def fz_loss(loss: float, var_forecast: float, es_forecast: float, tail_level: float) -> float:
    valid, _ = validate_forecast_values(var_forecast, es_forecast)
    if not valid or es_forecast <= 0:
        return math.nan
    alpha = 1.0 - tail_level
    x = -loss
    var_return = -var_forecast
    es_return = -es_forecast
    indicator = 1.0 if x <= var_return else 0.0
    return float(
        (1.0 / (alpha * es_return)) * indicator * (x - var_return)
        + var_return / es_return
        + math.log(-es_return)
        - 1.0
    )


def write_paper_latex_tables(*, run_dir: Path) -> PaperLatexResult:
    metrics_path = run_dir / "metrics" / "p2a_metrics.parquet"
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    tables = 0
    if metrics_path.exists():
        metrics = pl.read_parquet(metrics_path)
        tex = _metrics_to_latex(metrics)
        (latex_dir / "p2a_metrics_table.tex").write_text(tex, encoding="utf-8")
        tables += 1
    _write_json(
        run_dir / "latex" / "figure_manifest.json",
        {"claims_level": PAPER_CLAIMS_LEVEL, "tables": tables, "figures": []},
    )
    _update_manifest(run_dir, {"latex_tables": tables})
    return PaperLatexResult(run_id=run_dir.name, latex_dir=latex_dir, tables=tables)


def resolve_paper_run_dir(settings: Settings, run_id: str) -> Path:
    runs_dir = settings.reports_dir / "paper_runs"
    if run_id:
        run_dir = runs_dir / run_id
    else:
        candidates = [path for path in runs_dir.glob("p2a_*") if path.is_dir()]
        if not candidates:
            raise PaperRunError("No paper run found; run paper-panel first or pass run_id")
        run_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    if not run_dir.exists():
        raise PaperRunError(f"Paper run does not exist: {run_dir}")
    return run_dir


def _evaluate_p2a_shard(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    tail_level = _required_float(payload["tail_level"])
    models = cast(tuple[str, ...], payload["models"])
    frame = (
        pl.scan_parquet(panel_path)
        .filter(pl.col("clean_sample") == True)  # noqa: E712
        .select(["forecast_date", "realized_loss"])
        .drop_nulls()
        .sort("forecast_date")
        .collect()
    )
    rows = frame.to_dicts()
    oos_start = find_oos_start_date(rows, tail_level=tail_level)
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(model_name, tail_level),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                    "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                }
                for model_name in models
            ],
            "failures": [],
        }
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for model_name in models:
        model_rows, model_diag, model_failures = _forecast_model_sequence(
            rows=rows,
            model_name=model_name,
            tail_level=tail_level,
            oos_start=oos_start,
        )
        forecasts.extend(model_rows)
        diagnostics.extend(model_diag)
        failures.extend(model_failures)
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _forecast_model_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_level: float,
    oos_start: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    clean = _clean_loss_rows(rows)
    start_date = date.fromisoformat(oos_start)
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        if train.size < DEFAULT_MIN_TRAIN_ROWS:
            continue
        try:
            forecast = _forecast_one(train=train, model_name=model_name, tail_level=tail_level)
            realized_loss = _required_float(row["realized_loss"])
            var_forecast = _required_float(forecast["var_forecast"])
            es_forecast = _required_float(forecast["es_forecast"])
            valid, invalid_reason = validate_forecast_values(
                var_forecast,
                es_forecast,
            )
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": "full_gap_settle_to_open",
                    "model_name": model_name,
                    "information_set": "target_history_only",
                    "tail_level": tail_level,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": forecast["es_companion_type"],
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": valid,
                    "invalid_reason": invalid_reason,
                    "train_start": clean[0]["forecast_date"],
                    "train_end": clean[index - 1]["forecast_date"],
                    "train_n": int(train.size),
                    "fit_status": "ok" if valid else "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "runtime_seconds": None,
                }
            )
            diagnostics.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "train_n": int(train.size),
                    "optimizer_status": forecast.get("optimizer_status"),
                    "convergence_code": forecast.get("convergence_code"),
                    "dropped_features_json": "[]",
                    "threshold_quantile": forecast.get("threshold_quantile"),
                    "threshold_value": forecast.get("threshold_value"),
                    "evt_exceedance_count": forecast.get("evt_exceedance_count"),
                    "threshold_diagnostics_json": forecast.get("threshold_diagnostics_json"),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised via synthetic failure tests
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_optimizer_failed",
                    "failure_reason": str(exc),
                }
            )
    return forecasts, diagnostics, failures


def _forecast_one(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
) -> dict[str, object]:
    if model_name == "historical_quantile":
        var_forecast = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(train, var_forecast),
            "es_companion_type": "raw_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "rolling_quantile":
        window = train[-min(DEFAULT_MIN_TRAIN_ROWS, train.size) :]
        var_forecast = float(np.quantile(window, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(window, var_forecast),
            "es_companion_type": "rolling_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "ewma_vol_scaled":
        return _ewma_forecast(train=train, tail_level=tail_level, lambda_=EWMA_MAIN_LAMBDA)
    if model_name in {"garch_t", "gjr_garch_t", "gjr_garch_evt"}:
        return _arch_forecast(train=train, tail_level=tail_level, model_name=model_name)
    raise PaperRunError(f"Unknown P2A model: {model_name}")


def _ewma_forecast(*, train: np.ndarray, tail_level: float, lambda_: float) -> dict[str, object]:
    mean = float(np.mean(train))
    variance = float(np.var(train, ddof=1))
    for value in train:
        variance = lambda_ * variance + (1.0 - lambda_) * float((value - mean) ** 2)
    scale = math.sqrt(max(variance, 1e-12))
    z = stats.norm.ppf(tail_level)
    var_forecast = mean + scale * z
    alpha = 1.0 - tail_level
    es_forecast = mean + scale * stats.norm.pdf(z) / alpha
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_normal_es",
        "optimizer_status": "closed_form",
        "convergence_code": 0,
    }


def _arch_forecast(  # pragma: no cover - numeric optimizer exercised in real P2A runs
    *,
    train: np.ndarray,
    tail_level: float,
    model_name: str,
) -> dict[str, object]:
    try:
        from arch import arch_model
    except Exception as exc:  # pragma: no cover - dependency/environment
        raise PaperRunError(f"arch import failed: {exc}") from exc
    scaled_train = -train * 100.0
    p = 1
    o = 1 if model_name in {"gjr_garch_t", "gjr_garch_evt"} else 0
    model = arch_model(
        scaled_train,
        mean="Constant",
        vol="GARCH",
        p=p,
        o=o,
        q=1,
        dist="studentst",
        rescale=False,
    )
    result = model.fit(disp="off", show_warning=False)
    forecast = result.forecast(horizon=1, reindex=False)
    mean_return_forecast = float(forecast.mean.iloc[-1, 0]) / 100.0
    variance_forecast = float(forecast.variance.iloc[-1, 0]) / (100.0**2)
    scale_forecast = math.sqrt(max(variance_forecast, 1e-12))
    nu = float(result.params.get("nu", 8.0))
    var_forecast, es_forecast = _standardized_student_t_loss_var_es(
        mean_return_forecast=mean_return_forecast,
        scale_forecast=scale_forecast,
        nu=nu,
        tail_level=tail_level,
    )
    if model_name == "gjr_garch_evt":
        standardized_losses = _standardized_arch_losses(
            train=train,
            fitted_result=result,
        )
        evt_tail = _pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=tail_level,
        )
        var_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_var"]
        )
        es_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_es"]
        )
    else:
        evt_tail = {}
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_student_t_es"
        if model_name != "gjr_garch_evt"
        else str(evt_tail.get("tail_method", "pot_gpd_filtered_es")),
        "optimizer_status": "converged"
        if getattr(result, "convergence_flag", 1) == 0
        else "warning",
        "convergence_code": int(getattr(result, "convergence_flag", -1)),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
        "threshold_diagnostics_json": evt_tail.get("threshold_diagnostics_json"),
    }


def _standardized_student_t_loss_var_es(
    *,
    mean_return_forecast: float,
    scale_forecast: float,
    nu: float,
    tail_level: float,
) -> tuple[float, float]:
    alpha = 1.0 - tail_level
    raw_quantile = float(stats.t.ppf(alpha, df=nu))
    variance_scale = math.sqrt((nu - 2.0) / nu) if nu > 2.0 else 1.0
    standardized_lower_quantile = variance_scale * raw_quantile
    var_forecast = -(mean_return_forecast + scale_forecast * standardized_lower_quantile)
    raw_pdf = float(stats.t.pdf(raw_quantile, df=nu))
    if nu > 1.0:
        standardized_upper_es = (
            variance_scale
            * ((nu + raw_quantile**2) / (nu - 1.0))
            * raw_pdf
            / alpha
        )
    else:
        standardized_upper_es = -standardized_lower_quantile
    es_forecast = -mean_return_forecast + scale_forecast * standardized_upper_es
    return float(var_forecast), float(max(var_forecast, es_forecast))


def _standardized_arch_losses(train: np.ndarray, fitted_result: object) -> np.ndarray:
    std_resid = getattr(fitted_result, "std_resid", None)
    if std_resid is not None:
        values = np.asarray(std_resid, dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            return cast(np.ndarray, -values)
    fallback = (train - np.mean(train)) / max(float(np.std(train, ddof=1)), 1e-12)
    return cast(np.ndarray, fallback)


def _pot_gpd_standardized_tail(
    *,
    standardized_losses: np.ndarray,
    tail_level: float,
    threshold_quantile: float = EVT_THRESHOLD_QUANTILE,
) -> dict[str, object]:
    values = standardized_losses[np.isfinite(standardized_losses)]
    if values.size < DEFAULT_MIN_TRAIN_ROWS:
        raise PaperRunError("EVT calibration has insufficient standardized losses")
    diagnostics = _evt_threshold_diagnostics(values)
    threshold = float(np.quantile(values, threshold_quantile))
    excesses = values[values > threshold] - threshold
    if excesses.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        raise PaperRunError(
            f"EVT calibration has insufficient exceedances: {excesses.size}"
        )
    if tail_level <= threshold_quantile:
        var_z = float(np.quantile(values, tail_level))
        es_z = static_empirical_es(values, var_z)
        tail_method = "empirical_filtered_es"
    else:
        shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
        shape = float(shape)
        scale = float(max(scale, 1e-12))
        exceedance_probability = excesses.size / values.size
        target_tail_probability = max(1.0 - tail_level, 1e-12)
        ratio = max(exceedance_probability / target_tail_probability, 1.0)
        if abs(shape) < 1e-8:
            var_z = threshold + scale * math.log(ratio)
        else:
            var_z = threshold + scale * (ratio**shape - 1.0) / shape
        if shape < 1.0:
            es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
        else:
            es_z = static_empirical_es(values, var_z)
        tail_method = "pot_gpd_filtered_es"
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "threshold_diagnostics_json": json.dumps(diagnostics, sort_keys=True),
        "tail_method": tail_method,
    }


def _evt_threshold_diagnostics(values: np.ndarray) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    previous_shape: float | None = None
    previous_scale: float | None = None
    for quantile in EVT_THRESHOLD_GRID:
        threshold = float(np.quantile(values, quantile))
        excesses = values[values > threshold] - threshold
        row: dict[str, object] = {
            "threshold_quantile": quantile,
            "threshold_value": threshold,
            "exceedance_count": int(excesses.size),
            "mean_excess": float(np.mean(excesses)) if excesses.size else None,
        }
        if excesses.size >= 10:
            shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
            shape = float(shape)
            scale = float(scale)
            row["shape"] = shape
            row["scale"] = scale
            row["shape_delta_from_previous"] = (
                None if previous_shape is None else shape - previous_shape
            )
            row["scale_delta_from_previous"] = (
                None if previous_scale is None else scale - previous_scale
            )
            previous_shape = shape
            previous_scale = scale
        else:
            row["shape"] = None
            row["scale"] = None
            row["shape_delta_from_previous"] = None
            row["scale_delta_from_previous"] = None
        row["selected_threshold"] = quantile == EVT_THRESHOLD_QUANTILE
        row["selection_rationale"] = (
            "primary_pre_registered_threshold"
            if quantile == EVT_THRESHOLD_QUANTILE
            else "sensitivity_grid"
        )
        diagnostics.append(row)
    return diagnostics


def _massive_daily_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_ticker.setdefault(str(row["ticker"]), []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: str(row["bar_date_et"]))
        previous_close: float | None = None
        safe = _safe_name(ticker)
        for row in rows:
            date_key = str(row["bar_date_et"])
            close = _optional_float(row.get("close"))
            high = _optional_float(row.get("high"))
            low = _optional_float(row.get("low"))
            output = features_by_date.setdefault(date_key, {})
            if close is not None and previous_close and previous_close > 0:
                output[f"{safe}_return"] = math.log(close) - math.log(previous_close)
            else:
                output[f"{safe}_return"] = None
            if high is not None and low is not None and high > 0 and low > 0:
                output[f"{safe}_range"] = math.log(high) - math.log(low)
            else:
                output[f"{safe}_range"] = None
            if close is not None:
                previous_close = close
    return features_by_date


def _fred_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_series: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_series.setdefault(str(row["series_id"]), []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for series, rows in by_series.items():
        rows.sort(key=lambda row: str(row["observation_date"]))
        previous: float | None = None
        safe = _safe_name(series)
        for row in rows:
            date_key = str(row["observation_date"])
            value = _optional_float(row.get("value"))
            output = features_by_date.setdefault(date_key, {})
            output[f"fred_{safe}_level"] = value
            output[f"fred_{safe}_diff"] = (
                None if value is None or previous is None else value - previous
            )
            if value is not None:
                previous = value
    return features_by_date


def _spy_minute_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_date: dict[str, list[dict[str, object]]] = {}
    for row in records:
        if row.get("is_us_regular_session") is True:
            by_date.setdefault(str(row["bar_date_et"]), []).append(row)
    features: dict[str, dict[str, object]] = {}
    rolling_session_volume: list[float] = []
    for date_key in sorted(by_date):
        rows = sorted(by_date[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
        closes = [_optional_float(row.get("close")) for row in rows]
        highs = [_optional_float(row.get("high")) for row in rows]
        lows = [_optional_float(row.get("low")) for row in rows]
        volumes = [_optional_float(row.get("volume")) or 0.0 for row in rows]
        valid_closes = [value for value in closes if value is not None and value > 0]
        session_volume = float(sum(volumes))
        rolling_mean_volume = (
            float(np.mean(rolling_session_volume[-20:])) if rolling_session_volume else None
        )
        volume_surge = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else session_volume / rolling_mean_volume
        )
        features[date_key] = {
            "spy_late_30m_return": _window_return(valid_closes, 30),
            "spy_late_60m_return": _window_return(valid_closes, 60),
            "spy_late_session_range": _window_range(highs[-60:], lows[-60:]),
            "spy_late_volume_surge": volume_surge,
            "spy_final_window_momentum": _window_return(valid_closes, 15),
        }
        rolling_session_volume.append(session_volume)
    return features


def _fetch_jquants_futures_rows(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
) -> list[dict[str, Any]]:  # pragma: no cover - vendor path
    rows: list[dict[str, Any]] = []
    jpx_dates = [
        str(row["calendar_date"])
        for row in calendar_records
        if start <= str(row["calendar_date"]) <= end and row.get("is_jpx_trading_day") is True
    ]
    with JQuantsV2Client(
        api_key=settings.jquants_api_key,
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    ) as client:
        for trading_date in jpx_dates:
            rows.extend(client.get_futures_daily_bars(trading_date=trading_date))
    return rows


def _fetch_massive_paper_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:  # pragma: no cover - vendor path
    daily_records: list[dict[str, object]] = []
    minute_records: list[dict[str, object]] = []
    with MassiveClient(
        api_key=settings.massive_api_key,
        base_url=settings.massive_base_url,
        timeout_seconds=settings.massive_request_timeout_seconds,
    ) as client:
        for ticker in PAPER_CORE_MASSIVE_TICKERS:
            daily_records.extend(
                normalize_aggregate_bars(
                    ticker=ticker,
                    rows=client.get_aggregate_bars(
                        ticker=ticker,
                        multiplier=1,
                        timespan="day",
                        start=start,
                        end=end,
                    ),
                    multiplier=1,
                    timespan="day",
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    regular_session_start_et=settings.massive_regular_session_start_et,
                    regular_session_end_et=settings.massive_regular_session_end_et,
                )
            )
        for chunk_start, chunk_end in _month_chunks(start=start, end=end):
            minute_records.extend(
                normalize_aggregate_bars(
                    ticker=settings.massive_minute_ticker,
                    rows=client.get_aggregate_bars(
                        ticker=settings.massive_minute_ticker,
                        multiplier=1,
                        timespan="minute",
                        start=chunk_start,
                        end=chunk_end,
                    ),
                    multiplier=1,
                    timespan="minute",
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    regular_session_start_et=settings.massive_regular_session_start_et,
                    regular_session_end_et=settings.massive_regular_session_end_et,
                )
            )
    return daily_records, minute_records


def _fetch_fred_paper_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    records: list[dict[str, object]] = []
    with FredClient(
        base_url=settings.fred_base_url,
        timeout_seconds=settings.fred_request_timeout_seconds,
    ) as client:
        for series_id in PAPER_CORE_FRED_SERIES:
            payload = client.fetch_series_csv(series_id)
            records.extend(
                normalize_fred_rows(
                    series_id=series_id,
                    rows=payload.rows,
                    start=start,
                    end=end,
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                )
            )
    return records


def _clean_loss_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    clean: list[dict[str, object]] = []
    for row in rows:
        value = _optional_float(row.get("realized_loss"))
        if value is not None and math.isfinite(value):
            clean.append({**row, "realized_loss": value})
    clean.sort(key=lambda row: str(row["forecast_date"]))
    return clean


def _bounded_workers(workers: int) -> int:
    if workers > 0:
        return workers
    cpu_count = os.cpu_count() or 2
    return max(1, min(cpu_count - 2, 6))


def _set_nested_thread_limits() -> None:
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"


def _metrics_to_latex(metrics: pl.DataFrame) -> str:
    headers = ("model", "tail", "rows", "breach", "q_loss", "fz_loss")
    lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in metrics.iter_rows(named=True):
        lines.append(
            f"{row['model_name']} & {float(row['tail_level']):.3f} & "
            f"{int(row['rows'])} & {_fmt(row['var_breach_rate'])} & "
            f"{_fmt(row['mean_quantile_loss'])} & {_fmt(row['mean_fz_loss'])} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _update_manifest(run_dir: Path, updates: dict[str, object]) -> None:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest.update(updates)
    _write_json(path, manifest)


def _write_forecast_shards(
    forecast_root: Path,
    forecasts: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
    failures: list[dict[str, object]],
) -> None:
    shard_root = forecast_root / "shards"
    keys = {
        (str(row["model_name"]), _required_float(row["tail_level"]))
        for row in [*forecasts, *diagnostics, *failures]
        if "model_name" in row and "tail_level" in row
    }
    for model_name, tail_level in sorted(keys):
        shard_dir = shard_root / _forecast_shard_id(model_name, tail_level)
        _write_parquet(
            shard_dir / "forecasts.parquet",
            [
                row
                for row in forecasts
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_parquet(
            shard_dir / "fit_diagnostics.parquet",
            [
                row
                for row in diagnostics
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_parquet(
            shard_dir / "failures.parquet",
            [
                row
                for row in failures
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_json(
            shard_dir / "status.json",
            {
                "claims_level": PAPER_CLAIMS_LEVEL,
                "model_name": model_name,
                "tail_level": tail_level,
                "shard_id": _forecast_shard_id(model_name, tail_level),
            },
        )


def _forecast_shard_id(model_name: str, tail_level: float) -> str:
    return (
        f"model={_safe_name(model_name)}/target=full_gap_settle_to_open/"
        f"info=target_history_only/tail={tail_level:.3f}".replace(".", "_")
    )


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows).write_parquet(path)
    else:
        pl.DataFrame().write_parquet(path)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _required_float(value: object) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise PaperRunError(f"Expected finite numeric value, got {value!r}")
    return parsed


def _safe_name(value: str) -> str:
    return (
        value.replace(":", "_")
        .replace(".", "_")
        .replace("-", "_")
        .replace("/", "_")
        .lower()
    )


def _feature_description(field: str) -> str:
    if field.endswith("_return"):
        return "close-to-close log return frozen at U.S. close information set"
    if field.endswith("_range"):
        return "log high-low range over the source bar window"
    if field.endswith("_diff"):
        return "first difference of daily source value"
    if field.endswith("_level"):
        return "daily source level with conservative research availability semantics"
    if field.startswith("spy_late_"):
        return "SPY regular-session late-window minute-bar feature"
    return "paper-grade predictor candidate"


def _window_return(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    start = closes[-window - 1]
    end = closes[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _window_range(highs: list[float | None], lows: list[float | None]) -> float | None:
    valid_highs = [value for value in highs if value is not None and value > 0]
    valid_lows = [value for value in lows if value is not None and value > 0]
    if not valid_highs or not valid_lows:
        return None
    return math.log(max(valid_highs)) - math.log(min(valid_lows))


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        next_month = current.replace(day=28) + timedelta(days=4)
        month_end = min(next_month.replace(day=1) - timedelta(days=1), end_date)
        chunks.append((current.isoformat(), month_end.isoformat()))
        current = month_end + timedelta(days=1)
    return chunks


def _safe_mean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.mean(finite))


def _fmt(value: object) -> str:
    parsed = _optional_float(value)
    return "" if parsed is None else f"{parsed:.6f}"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())
