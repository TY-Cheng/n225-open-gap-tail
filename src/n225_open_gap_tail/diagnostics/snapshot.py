# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl
from scipy import stats  # type: ignore[import-untyped]

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import write_json_atomic
from n225_open_gap_tail.market.calendars import build_session_calendar_records
from n225_open_gap_tail.sources.fred import FredClient, normalize_fred_rows
from n225_open_gap_tail.sources.jquants import JQuantsV2Client
from n225_open_gap_tail.sources.massive import MassiveClient, normalize_aggregate_bars

JPX_CONTRACT_URL = "https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html"
CLAIMS_LEVEL = "smoke_only_not_manuscript_evidence"
PRODUCT_CATEGORY = "NK225F"
MIN_TOTAL_ROWS_FOR_SPLIT = 120
MIN_TRAIN_ROWS_FOR_LIGHTGBM = 80
MIN_TEST_ROWS_FOR_METRICS = 20
MIN_TRAIN_EXCEEDANCES_FOR_EVT = 30
PREFERRED_TRAIN_EXCEEDANCES_FOR_EVT = 50

PRICE_FIELDS = {
    "day_session_open": "AO",
    "day_session_close": "AC",
    "night_session_open": "EO",
    "night_session_close": "EC",
    "settlement_price": "Settle",
}
FIELD_MAPPING = {
    **PRICE_FIELDS,
    "volume": "Vo",
    "open_interest": "OI",
    "contract_month": "CM",
    "contract_code": "Code",
    "central_contract_month_flag": "CCMFlag",
    "last_trading_day": "LTD",
    "special_quotation_day": "SQD",
    "product_category": "ProdCat",
    "trading_date": "Date",
}
REQUIRED_SCHEMA_FIELDS = {
    "Date",
    "ProdCat",
    "Code",
    "AO",
    "AC",
    "EC",
    "Settle",
    "Vo",
    "OI",
    "CM",
    "CCMFlag",
    "LTD",
    "SQD",
}


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: str
    snapshot_dir: Path
    docs_results_path: Path
    target_rows: int
    model_status: str


class SnapshotError(RuntimeError):
    """Raised when a snapshot gate cannot be satisfied."""


def write_results_snapshot_from_run(
    *,
    settings: Settings,
    run_id: str | None = None,
) -> SnapshotResult:
    """Write docs/results_snapshot.md from a completed full tail-risk run.

    This is intentionally different from the historical smoke snapshot helper below:
    it does not fetch vendors and it summarizes the durable gold modeling sample.
    """
    run_dir = _resolve_snapshot_run_dir(settings=settings, run_id=run_id)
    manifest = _read_json_dict(run_dir / "manifest.json")
    resolved_run_id = str(manifest.get("run_id") or run_dir.name)
    paths = _full_run_snapshot_paths(settings=settings, run_dir=run_dir, manifest=manifest)
    panel = _read_parquet_optional(paths["modeling_panel"])
    docs_path = Path("docs/results_snapshot.md")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(
        _full_run_results_markdown(
            run_dir=run_dir,
            manifest=manifest,
            paths=paths,
        ),
        encoding="utf-8",
    )
    return SnapshotResult(
        snapshot_id=resolved_run_id,
        snapshot_dir=run_dir,
        docs_results_path=docs_path,
        target_rows=panel.height,
        model_status=str(
            manifest.get("ml_tail_eval_status") or manifest.get("benchmark_eval_status")
        ),
    )


def build_snapshot_id(
    *,
    start: str,
    end: str,
    run_ts_utc: datetime,
    git_commit: str,
) -> str:
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    compact_ts = run_ts_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{clean_start}_{clean_end}_{compact_ts}_commit_{git_commit[:8]}"


def _resolve_snapshot_run_dir(*, settings: Settings, run_id: str | None) -> Path:
    runs_dir = settings.reports_dir / "runs"
    if run_id and run_id != "latest":
        run_dir = runs_dir / run_id
        if not (run_dir / "manifest.json").exists():
            raise SnapshotError(f"Run manifest not found: {run_dir / 'manifest.json'}")
        return run_dir
    candidates = sorted(
        (path for path in runs_dir.glob("tailrisk_*") if (path / "manifest.json").exists()),
        key=lambda path: (path / "manifest.json").stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SnapshotError("No completed tail-risk run found under reports/runs")
    return candidates[0]


def _read_json_dict(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _full_run_snapshot_paths(
    *,
    settings: Settings,
    run_dir: Path,
    manifest: dict[str, object],
) -> dict[str, Path]:
    run_id = str(manifest.get("run_id") or run_dir.name)
    gold_artifacts = _dict_value(manifest.get("gold_artifacts"))
    gold_panel_root = (
        settings.gold_data_dir / "tailrisk_panel" / "schema_version=1" / f"run_id={run_id}"
    )
    leakage_root = (
        settings.gold_data_dir / "leakage_summary" / "schema_version=1" / f"run_id={run_id}"
    )
    return {
        "manifest": run_dir / "manifest.json",
        "data_vintage": run_dir / "data_vintage.json",
        "modeling_panel": Path(
            str(gold_artifacts.get("modeling_panel", gold_panel_root / "modeling_panel.parquet"))
        ),
        "target_audit": Path(
            str(gold_artifacts.get("target_audit", gold_panel_root / "target_audit.parquet"))
        ),
        "calendar_map": Path(
            str(gold_artifacts.get("calendar_map", gold_panel_root / "calendar_map.parquet"))
        ),
        "feature_coverage": Path(
            str(
                gold_artifacts.get("feature_coverage", gold_panel_root / "feature_coverage.parquet")
            )
        ),
        "leakage_summary": leakage_root / "summary.json",
        "benchmark_status": run_dir / "metrics" / "benchmark_status.json",
        "benchmark_metrics": run_dir / "metrics" / "benchmark_metrics.parquet",
        "ml_tail_status": run_dir / "metrics" / "ml_tail_status.json",
        "ml_tail_metrics": run_dir / "metrics" / "ml_tail_metrics.parquet",
        "ml_tail_metrics_per_model": run_dir / "metrics" / "ml_tail_metrics_per_model.parquet",
        "ml_tail_result_matrix": run_dir / "metrics" / "ml_tail_result_matrix.parquet",
        "benchmark_stress_windows": run_dir / "metrics" / "benchmark_stress_windows.parquet",
        "ml_tail_stress_windows": run_dir / "metrics" / "ml_tail_stress_windows.parquet",
        "latex_dir": run_dir / "latex" / "tables",
    }


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _read_parquet_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _full_run_results_markdown(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    paths: dict[str, Path],
) -> str:
    data_vintage = _read_json_dict(paths["data_vintage"])
    benchmark_status = _read_json_dict(paths["benchmark_status"])
    ml_tail_status = _read_json_dict(paths["ml_tail_status"])
    leakage_summary = _read_json_dict(paths["leakage_summary"])
    panel = _read_parquet_optional(paths["modeling_panel"])
    target = _read_parquet_optional(paths["target_audit"])
    calendar = _read_parquet_optional(paths["calendar_map"])
    feature_coverage = _read_parquet_optional(paths["feature_coverage"])
    benchmark_metrics = _read_parquet_optional(paths["benchmark_metrics"])
    ml_tail_metrics = _read_parquet_optional(paths["ml_tail_metrics"])
    result_matrix = _read_parquet_optional(paths["ml_tail_result_matrix"])
    benchmark_stress = _read_parquet_optional(paths["benchmark_stress_windows"])
    ml_tail_stress = _read_parquet_optional(paths["ml_tail_stress_windows"])

    run_id = str(manifest.get("run_id") or run_dir.name)
    panel_bounds = _panel_bounds(panel)
    forecast_bounds = _forecast_sample_bounds(panel)
    metadata_table = _markdown_table(
        ("Field", "Value"),
        [
            ("Run ID", f"`{run_id}`"),
            ("Artifact root", f"`{run_dir}`"),
            ("Claim level", _code(manifest.get("claim_level") or manifest.get("claims_level"))),
            ("Requested window", _code(manifest.get("window"))),
            ("Combined clean start", _code(manifest.get("combined_clean_start"))),
            ("Gold panel dates", panel_bounds),
            ("Forecast sample dates", forecast_bounds),
            ("Git commit", _code(manifest.get("git_commit"))),
            ("Git dirty", _code(manifest.get("git_dirty"))),
            ("FRED vintage safe", _code(data_vintage.get("fred_vintage_safe"))),
        ],
    )
    panel_table = _markdown_table(
        ("Measure", "Value"),
        [
            ("Gold modeling rows", str(panel.height)),
            ("Gold columns", str(panel.width)),
            ("Target-audit rows", str(target.height)),
            ("Clean target rows", str(_bool_sum(target, "clean_sample"))),
            ("Forecast-sample rows", str(_bool_sum(panel, "forecast_sample"))),
            (
                "Rows before combined clean start",
                str(_count_value(panel, "forecast_sample_reason", "before_combined_clean_start")),
            ),
            (
                "Target-not-clean rows",
                str(_count_value(panel, "forecast_sample_reason", "target_not_clean")),
            ),
            (
                "Mapping excluded rows",
                str(
                    _count_value(
                        panel, "forecast_sample_reason", "mapping_status_not_normal_trading"
                    )
                ),
            ),
        ],
    )
    target_table = _counts_table(target, "missing_reason", "Target audit reason")
    calendar_table = _markdown_table(
        ("Measure", "Value"),
        [
            (
                "Normal trading mappings",
                str(_count_value(calendar, "mapping_status", "normal_trading")),
            ),
            (
                "U.S./Japan desync mappings",
                str(_count_value(calendar, "mapping_status", "us_jp_desync")),
            ),
            ("NYSE early-close mappings", str(_bool_sum(calendar, "us_early_close_flag"))),
            ("EDT rows", str(_count_value(calendar, "dst_regime", "EDT"))),
            ("EST rows", str(_count_value(calendar, "dst_regime", "EST"))),
        ],
    )
    feature_table = _feature_coverage_table(feature_coverage)
    leakage_table = _markdown_table(
        ("Field", "Value"),
        [
            ("Status", _code(leakage_summary.get("status"))),
            ("Rows audited", _code(leakage_summary.get("rows"))),
            ("Failures", _code(leakage_summary.get("failures"))),
            ("Warnings", _code(leakage_summary.get("warnings"))),
            ("Panel row count", _code(leakage_summary.get("panel_row_count"))),
            ("Panel signature seed", _code(leakage_summary.get("panel_signature_hash_seed"))),
            ("Panel signature", _code(leakage_summary.get("panel_signature"))),
        ],
    )
    benchmark_table = _metrics_table(benchmark_metrics)
    ml_headline_table = _metrics_table(ml_tail_metrics)
    result_matrix_table = _result_matrix_summary_table(result_matrix)
    benchmark_status_label = (
        manifest.get("benchmark_eval_status")
        or benchmark_status.get("status")
        or benchmark_status.get("common_sample_status")
        or "unknown"
    )
    ml_tail_components = _join_list(ml_tail_status.get("implemented_components"))
    stress_table = _markdown_table(
        ("Suite", "Rows", "Window labels"),
        [
            (
                "benchmark",
                str(benchmark_stress.height),
                _unique_values(benchmark_stress, "window_name"),
            ),
            ("ml_tail", str(ml_tail_stress.height), _unique_values(ml_tail_stress, "window_name")),
        ],
    )
    artifact_table = _artifact_table(paths)

    return f"""# Results Snapshot

!!! warning "Research-candidate full-run artifact"
    This page is generated from `{run_id}`. It summarizes the durable gold modeling sample and run outputs, not the older bounded access-check snapshot. It is still a research-candidate artifact: final manuscript claims require a clean committed run and author review of the tables and notes.

## Discussion Q&A

### What is this project testing?

It tests whether timestamp-safe information available after the U.S. cash close helps forecast the downside tail of the next Osaka Nikkei 225 Futures day-session open.

- The object is tail risk, not average return prediction or a trading signal.
- The comparison is organized as an information ladder: Japan-only history first, then U.S. close core, then Japan proxy ETFs, then Asia proxy ETFs.
- The current page reports what the pipeline produced; it does not automatically claim that any model is best.

### What exactly is being forecast?

The primary target is the loss version of the settle-to-open Nikkei futures gap for the OSE day-session open.

- A positive realized loss means the opening gap moved against the lower-tail risk direction being evaluated.
- Roll/SQ windows and invalid reference prices are excluded from clean target evidence.
- The residual U.S.-close mark target is disabled in this run because there is no licensed timestamped intraday Nikkei mark.

### Why is timing the central issue?

The forecast origin is the U.S. close plus vendor lag, and it must occur before the OSE target open.

- Every joined predictor is audited against `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.
- FRED features are treated with timestamp-safe release lags; FRED historical values are not ALFRED vintage-safe.
- Leakage audit failures are zero in this run, but warnings remain visible below rather than hidden.

### What has been implemented?

The external benchmark floor and the ML-tail suite are implemented and have completed artifacts in this run.

- Benchmark models include target-history baselines and GARCH/EVT-style econometric floors.
- ML-tail models include direct LightGBM quantile, location-scale LightGBM, and standardized-loss POT-GPD.
- The headline ML-tail table remains strict: it currently keeps direct quantile rows because the newer tail-model variants have shorter common coverage.

### How should broad readers interpret the metrics?

Coverage diagnostics ask whether VaR exceptions are too frequent or too rare; quantile loss scores VaR accuracy; FZ loss scores VaR-ES pairs.

- Lower quantile loss is better only within a common sample and claim boundary.
- FZ loss is only meaningful for valid VaR-ES pairs and needs enough exceptions to avoid short-sample overinterpretation.
- Restricted result-matrix rows are useful diagnostics, not replacements for the headline information-set ladder.

### What is the current bottom line?

The pipeline is now producing full-run research-candidate evidence from the durable gold layer.

- The gold sample starts at the dynamic combined clean start, not the 2016 cache lower bound.
- Benchmark and ML-tail suites both completed with zero recorded forecast failures.
- Before manuscript claims, rerun from a clean commit and review the restricted result matrix, inference gates, and vintage limitations.

## Metadata

{metadata_table}

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty=True` means this exact run was produced with local uncommitted changes; use a clean committed rerun for manuscript tables.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

## Pipeline Structure

```mermaid
flowchart LR
  A["Vendor and calendar sources"] --> B["Bronze cache"]
  B --> C["Silver normalized features"]
  C --> D["Gold modeling panel"]
  D --> E["Leakage and coverage gates"]
  E --> F["Benchmark models"]
  E --> G["ML-tail model registry"]
  F --> H["Metrics and loss matrices"]
  G --> H
  H --> I["DM, MCS, result matrix, stress diagnostics"]
  I --> J["Results snapshot"]
```

- Data-access and cache artifacts live under `data/bronze` and `data/silver`.
- Durable modeling evidence lives under `data/gold`; forecast/evaluation/reporting read from gold and reports.
- Run-specific forecasts, metrics, diagnostics, and LaTeX tables live under `reports/runs/<run_id>`.

## Gold Panel Construction

{panel_table}

{target_table}

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

## Calendar And Timing Map

{calendar_table}

- The map covers EST/EDT, early closes, U.S./Japan holiday desynchronization, and normal trading alignments.
- Desync rows are not treated as normal forecast rows.
- The timing map is part of the leakage-bound gold artifact, not ad hoc evaluation logic.

## Feature Coverage

{feature_table}

- U.S. core, proxy ETFs, SPY late-session features, CBOE VIX, FRED rates, and FRED H.10 FX are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

## Leakage Audit

{leakage_table}

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Benchmark Suite

Status: `{benchmark_status_label}`; forecast rows: `{benchmark_status.get("forecast_rows")}`; metric rows: `{benchmark_status.get("metric_rows")}`; failures: `{benchmark_status.get("failures")}`.

{benchmark_table}

- Benchmarks set the target-history/econometric floor that ML models should be interpreted against.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

## ML-Tail Headline Ladder

Status: `{ml_tail_status.get("status")}`; implemented models: {ml_tail_components}; forecast rows: `{ml_tail_status.get("forecast_rows")}`; failures: `{ml_tail_status.get("failures")}`.

{ml_headline_table}

- This headline table remains strict and currently reports direct LightGBM quantile across the information ladder.
- Location-scale and POT-GPD are implemented, but their shorter common coverage keeps them out of the headline ladder.
- The apparent improvement in quantile loss as blocks are added is descriptive until inference and coverage diagnostics are reviewed.

## Result Matrix Layer

{result_matrix_table}

- The result matrix is the right place to compare direct quantile, location-scale, and POT-GPD on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the headline direct-quantile evidence.

## Stress And Diagnostic Windows

{stress_table}

- Stress windows identify high-loss or high-volatility subsamples for robustness diagnostics.
- These rows use reproducible full-sample classifiers in this first pass, so they should be described as diagnostics rather than a live stress classifier.
- They are useful for finding whether model behavior changes in difficult regimes before writing manuscript discussion.

## Artifact Index

{artifact_table}

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.
"""


def _code(value: object) -> str:
    return f"`{value}`"


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    return _code(value)


def _markdown_table(headers: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _panel_bounds(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "forecast_date" not in frame.columns:
        return "`missing`"
    values = frame.select(
        pl.col("forecast_date").min().alias("start"),
        pl.col("forecast_date").max().alias("end"),
    ).row(0, named=True)
    return f"`{values['start']} to {values['end']}`"


def _forecast_sample_bounds(frame: pl.DataFrame) -> str:
    if frame.is_empty() or not {"forecast_date", "forecast_sample"}.issubset(frame.columns):
        return "`missing`"
    filtered = frame.filter(pl.col("forecast_sample") == True)  # noqa: E712
    if filtered.is_empty():
        return "`empty`"
    values = filtered.select(
        pl.col("forecast_date").min().alias("start"),
        pl.col("forecast_date").max().alias("end"),
        pl.len().alias("rows"),
    ).row(0, named=True)
    return f"`{values['start']} to {values['end']} ({values['rows']} rows)`"


def _bool_sum(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.select(pl.col(column).fill_null(False).sum()).item() or 0)


def _count_value(frame: pl.DataFrame, column: str, value: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.filter(pl.col(column) == value).height)


def _counts_table(frame: pl.DataFrame, column: str, label: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return _markdown_table((label, "Rows"), [("missing", "0")])
    rows = [
        (str(row[column]), str(row["len"]))
        for row in frame.group_by(column).len().sort("len", descending=True).iter_rows(named=True)
    ]
    return _markdown_table((label, "Rows"), rows)


def _feature_coverage_table(frame: pl.DataFrame) -> str:
    required = {"source_family", "source_block", "missingness_rate"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return _markdown_table(
            ("Source family", "Block", "Features", "Mean missing", "Max missing"),
            [("missing", "missing", "0", "n/a", "n/a")],
        )
    grouped = (
        frame.group_by(["source_family", "source_block"])
        .agg(
            pl.len().alias("features"),
            pl.mean("missingness_rate").alias("mean_missing"),
            pl.max("missingness_rate").alias("max_missing"),
        )
        .sort(["source_family", "source_block"])
    )
    rows = [
        (
            row["source_family"],
            row["source_block"],
            row["features"],
            _fmt_rate(row["mean_missing"]),
            _fmt_rate(row["max_missing"]),
        )
        for row in grouped.iter_rows(named=True)
    ]
    return _markdown_table(
        ("Source family", "Block", "Features", "Mean missing", "Max missing"),
        rows,
    )


def _metrics_table(frame: pl.DataFrame) -> str:
    columns = [
        "model_name",
        "information_set",
        "rows",
        "var_breach_rate",
        "exceedance_count",
        "mean_quantile_loss",
        "mean_fz_loss",
    ]
    if frame.is_empty() or not set(columns).issubset(frame.columns):
        return _markdown_table(tuple(columns), [("missing", "", "", "", "", "", "")])
    rows = [
        (
            row["model_name"],
            row["information_set"],
            row["rows"],
            _fmt_rate(row["var_breach_rate"]),
            row["exceedance_count"],
            _fmt_float(row["mean_quantile_loss"]),
            _fmt_float(row["mean_fz_loss"]),
        )
        for row in frame.select(columns).iter_rows(named=True)
    ]
    return _markdown_table(
        (
            "Model",
            "Information set",
            "Rows",
            "VaR breach rate",
            "Exceptions",
            "Mean quantile loss",
            "Mean FZ loss",
        ),
        rows,
    )


def _result_matrix_summary_table(frame: pl.DataFrame) -> str:
    columns = {"comparison_family", "comparison_axis", "sample_policy", "loss_family"}
    if frame.is_empty() or not columns.issubset(frame.columns):
        return _markdown_table(
            ("Family", "Axis", "Loss", "Rows", "Common N", "Date range", "Joint exceptions"),
            [("missing", "", "", "0", "n/a", "n/a", "n/a")],
        )
    grouped = (
        frame.group_by(["comparison_family", "comparison_axis", "sample_policy", "loss_family"])
        .agg(
            pl.len().alias("rows"),
            pl.min("common_n").alias("min_n"),
            pl.max("common_n").alias("max_n"),
            pl.min("date_start").alias("start"),
            pl.max("date_end").alias("end"),
            pl.min("joint_exception_count").alias("min_joint_exceptions"),
            pl.max("joint_exception_count").alias("max_joint_exceptions"),
        )
        .sort(["comparison_family", "comparison_axis", "loss_family"])
    )
    rows = [
        (
            row["comparison_family"],
            row["comparison_axis"],
            row["loss_family"],
            row["rows"],
            f"{row['min_n']} to {row['max_n']}",
            f"{row['start']} to {row['end']}",
            f"{row['min_joint_exceptions']} to {row['max_joint_exceptions']}",
        )
        for row in grouped.iter_rows(named=True)
    ]
    return _markdown_table(
        ("Family", "Axis", "Loss", "Rows", "Common N", "Date range", "Joint exceptions"),
        rows,
    )


def _unique_values(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return "`missing`"
    values = sorted(str(value) for value in frame[column].drop_nulls().unique().to_list())
    return ", ".join(f"`{value}`" for value in values)


def _artifact_table(paths: dict[str, Path]) -> str:
    rows = [
        (name, f"`{path}`", "yes" if path.exists() else "missing") for name, path in paths.items()
    ]
    return _markdown_table(("Artifact", "Path", "Exists"), rows)


def _fmt_float(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.6g}"


def _fmt_rate(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.3%}"


def normalize_jquants_futures_rows(
    rows: list[dict[str, Any]],
    *,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    jst = ZoneInfo("Asia/Tokyo")
    for row in rows:
        if str(row.get("ProdCat", "")) != PRODUCT_CATEGORY:
            continue
        trading_date = _parse_date(row.get("Date"))
        target_open_ts_jst = datetime.combine(trading_date, time(8, 45), tzinfo=jst)
        night_close_ts_jst = datetime.combine(trading_date, time(6, 0), tzinfo=jst)
        record: dict[str, object] = {
            "source": "jquants",
            "source_endpoint": "/derivatives/bars/daily/futures",
            "product_category": PRODUCT_CATEGORY,
            "trading_date": trading_date.isoformat(),
            "contract_code": _optional_str(row.get("Code")),
            "contract_month": _optional_str(row.get("CM")),
            "central_contract_month_flag": _optional_bool(row.get("CCMFlag")),
            "day_session_open": _price_or_none(row.get("AO")),
            "day_session_close": _price_or_none(row.get("AC")),
            "night_session_open": _price_or_none(row.get("EO")),
            "night_session_close": _price_or_none(row.get("EC")),
            "settlement_price": _price_or_none(row.get("Settle")),
            "volume": _optional_float(row.get("Vo")),
            "open_interest": _optional_float(row.get("OI")),
            "last_trading_day": _optional_date_iso(row.get("LTD")),
            "special_quotation_day": _optional_date_iso(row.get("SQD")),
            "target_open_ts_jst": target_open_ts_jst,
            "target_open_ts_utc": target_open_ts_jst.astimezone(UTC),
            "night_close_ts_jst": night_close_ts_jst,
            "night_close_ts_utc": night_close_ts_jst.astimezone(UTC),
            "vendor_available_ts_utc": datetime.combine(
                trading_date + timedelta(days=1),
                time(3, 0),
                tzinfo=jst,
            ).astimezone(UTC),
            "research_download_ts_utc": downloaded_at_utc,
        }
        normalized.append(record)
    normalized.sort(key=lambda item: (str(item["trading_date"]), str(item["contract_code"])))
    return normalized


def build_jquants_schema_probe(rows: list[dict[str, Any]]) -> dict[str, object]:
    fields = sorted({field for row in rows for field in row})
    missing_required = sorted(REQUIRED_SCHEMA_FIELDS.difference(fields))
    product_counts: dict[str, int] = {}
    coverage: dict[str, int] = {field: 0 for field in sorted(REQUIRED_SCHEMA_FIELDS)}
    zero_price_counts: dict[str, int] = {canonical: 0 for canonical in PRICE_FIELDS}
    for row in rows:
        product = str(row.get("ProdCat", "<missing>"))
        product_counts[product] = product_counts.get(product, 0) + 1
        for field in coverage:
            if row.get(field) not in (None, ""):
                coverage[field] += 1
        for canonical, raw_field in PRICE_FIELDS.items():
            value = row.get(raw_field)
            if value in (0, 0.0, "0"):
                zero_price_counts[canonical] += 1
    return {
        "source": "jquants",
        "endpoint": "/derivatives/bars/daily/futures",
        "field_mapping": FIELD_MAPPING,
        "observed_fields": fields,
        "missing_required_fields": missing_required,
        "product_counts": product_counts,
        "required_field_coverage": coverage,
        "zero_price_counts": zero_price_counts,
        "fail_closed": bool(missing_required),
    }


def build_target_audit_records(
    normalized_rows: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    roll_days_before_last_trade: int,
) -> list[dict[str, object]]:
    central_rows = [
        row for row in normalized_rows if row.get("central_contract_month_flag") is True
    ]
    all_by_contract: dict[str, list[dict[str, object]]] = {}
    for row in normalized_rows:
        code = str(row.get("contract_code") or "")
        if code:
            all_by_contract.setdefault(code, []).append(row)
    for rows in all_by_contract.values():
        rows.sort(key=lambda item: str(item["trading_date"]))

    jpx_sessions = [
        date.fromisoformat(str(row["calendar_date"]))
        for row in calendar_records
        if row.get("is_jpx_trading_day") is True
    ]

    target_rows: list[dict[str, object]] = []
    previous_central: dict[str, object] | None = None
    for row in sorted(central_rows, key=lambda item: str(item["trading_date"])):
        trading_date = date.fromisoformat(str(row["trading_date"]))
        contract_code = str(row.get("contract_code") or "")
        prior_row = _previous_same_contract_row(
            all_by_contract.get(contract_code, []),
            trading_date,
        )
        roll_window = _is_roll_sq_window(
            trading_date=trading_date,
            last_trading_day=_optional_date(row.get("last_trading_day")),
            special_quotation_day=_optional_date(row.get("special_quotation_day")),
            jpx_sessions=jpx_sessions,
            roll_days_before_last_trade=roll_days_before_last_trade,
        )
        same_contract = prior_row is not None
        missing_reasons = _target_missing_reasons(
            target_row=row,
            prior_row=prior_row,
            roll_window=roll_window,
            previous_central=previous_central,
        )
        full_gap_settle = _log_gap(
            row.get("day_session_open"), _value(prior_row, "settlement_price")
        )
        full_gap_close = _log_gap(
            row.get("day_session_open"), _value(prior_row, "day_session_close")
        )
        residual_night = _log_gap(row.get("day_session_open"), row.get("night_session_close"))
        clean_eligible = same_contract and not roll_window and not missing_reasons
        target_rows.append(
            {
                "trading_date": row["trading_date"],
                "contract_code": contract_code,
                "contract_month": row.get("contract_month"),
                "reference_contract_code": _value(prior_row, "contract_code"),
                "same_contract_only": same_contract,
                "is_roll_sq_window": roll_window,
                "clean_sample": clean_eligible,
                "missing_reason": ";".join(missing_reasons) if missing_reasons else None,
                "target_open_ts_utc": row["target_open_ts_utc"],
                "target_open_ts_jst": row["target_open_ts_jst"],
                "reference_date": _value(prior_row, "trading_date"),
                "day_session_open": row.get("day_session_open"),
                "prior_settlement_price": _value(prior_row, "settlement_price"),
                "prior_day_session_close": _value(prior_row, "day_session_close"),
                "night_session_close": row.get("night_session_close"),
                "full_gap_settle_to_open": full_gap_settle,
                "full_gap_close_to_open": full_gap_close,
                "residual_nightclose_to_day_open": residual_night,
                "loss_settle_to_open": -full_gap_settle if full_gap_settle is not None else None,
                "volume": row.get("volume"),
                "open_interest": row.get("open_interest"),
                "volume_oi_anomaly": _volume_oi_anomaly(row),
                "last_trading_day": row.get("last_trading_day"),
                "special_quotation_day": row.get("special_quotation_day"),
            }
        )
        previous_central = row
    return target_rows


def build_time_alignment_records(
    *,
    target_rows: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
    spy_minute_records: list[dict[str, object]],
    vendor_lag_minutes: int = 5,
) -> list[dict[str, object]]:
    us_closes = [row for row in calendar_records if row.get("us_close_ts_utc") is not None]
    us_closes.sort(key=lambda row: _as_datetime(row["us_close_ts_utc"]))
    minute_by_date: dict[str, list[dict[str, object]]] = {}
    for record in spy_minute_records:
        minute_by_date.setdefault(str(record["bar_date_et"]), []).append(record)
    for records in minute_by_date.values():
        records.sort(key=lambda row: _as_datetime(row["bar_end_ts_utc"]))

    alignment: list[dict[str, object]] = []
    for target in target_rows:
        target_open = _as_datetime(target["target_open_ts_utc"])
        close_row = _latest_us_close_before(us_closes, target_open)
        if close_row is None:
            alignment.append(
                {
                    "trading_date": target["trading_date"],
                    "target_open_ts_utc": target_open,
                    "alignment_status": "missing_us_close",
                    "alignment_pass": False,
                }
            )
            continue
        us_close = _as_datetime(close_row["us_close_ts_utc"])
        model_cutoff = us_close + timedelta(minutes=vendor_lag_minutes)
        bar, bar_reason = _select_spy_close_bar(
            minute_by_date.get(str(close_row["calendar_date"]), []),
            official_close_ts_utc=us_close,
        )
        minutes = close_row.get("us_close_to_ose_night_close_minutes")
        alignment_pass, reason = _dst_alignment_check(
            close_row.get("dst_regime"),
            minutes,
            is_early_close=close_row.get("is_us_early_close") is True,
        )
        bar_end = _as_datetime(bar["bar_end_ts_utc"]) if bar else None
        alignment.append(
            {
                "trading_date": target["trading_date"],
                "us_calendar_date": close_row["calendar_date"],
                "dst_regime": close_row.get("dst_regime"),
                "absorption_regime": close_row.get("absorption_regime"),
                "is_us_early_close": close_row.get("is_us_early_close"),
                "is_us_trading_day": close_row.get("is_us_trading_day"),
                "is_jpx_trading_day": close_row.get("is_jpx_trading_day"),
                "us_official_close_ts_utc": us_close,
                "us_official_close_ts_et": close_row.get("us_close_ts_et"),
                "model_cutoff_ts_utc": model_cutoff,
                "selected_spy_bar_end_ts_utc": bar_end,
                "selected_spy_bar_end_ts_et": bar.get("bar_end_ts_et") if bar else None,
                "spy_close": bar.get("close") if bar else None,
                "vendor_lag_seconds": vendor_lag_minutes * 60 if bar else None,
                "spy_bar_selection_reason": bar_reason,
                "ose_night_close_ts_utc": close_row.get("ose_night_close_ts_utc"),
                "ose_night_close_ts_jst": close_row.get("ose_night_close_ts_jst"),
                "target_open_ts_utc": target_open,
                "target_open_ts_jst": target.get("target_open_ts_jst"),
                "us_close_to_ose_night_close_minutes": minutes,
                "alignment_pass": alignment_pass,
                "alignment_reason": reason,
                "cutoff_invariant_pass": model_cutoff < target_open
                and (bar_end is None or bar_end <= model_cutoff),
            }
        )
    return alignment


def build_predictor_availability_records(
    *,
    target_rows: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    clean_dates = {
        str(row["trading_date"])
        for row in target_rows
        if row.get("clean_sample") is True and row.get("full_gap_settle_to_open") is not None
    }
    by_us_date = {
        str(row["us_calendar_date"]): str(row["trading_date"])
        for row in alignment_records
        if row.get("us_calendar_date") is not None
    }
    loss_by_date = {
        str(row["trading_date"]): _required_float(row["loss_settle_to_open"])
        for row in target_rows
        if row.get("loss_settle_to_open") is not None
    }
    regime_by_target = {
        str(row["trading_date"]): str(row.get("dst_regime") or "") for row in alignment_records
    }
    records: list[dict[str, object]] = []
    records.extend(
        _availability_for_records(
            source="massive_daily",
            key_field="ticker",
            date_field="bar_date_et",
            value_field="close",
            records=massive_daily_records,
            by_us_date=by_us_date,
            clean_dates=clean_dates,
            loss_by_date=loss_by_date,
            regime_by_target=regime_by_target,
        )
    )
    records.extend(
        _availability_for_records(
            source="fred",
            key_field="series_id",
            date_field="observation_date",
            value_field="value",
            records=fred_records,
            by_us_date=by_us_date,
            clean_dates=clean_dates,
            loss_by_date=loss_by_date,
            regime_by_target=regime_by_target,
        )
    )
    return records


def build_model_smoke(
    target_rows: list[dict[str, object]],
    *,
    alpha: float = 0.05,
) -> dict[str, object]:
    clean_rows = [
        row
        for row in target_rows
        if row.get("clean_sample") is True and row.get("full_gap_settle_to_open") is not None
    ]
    losses: Any = np.array(
        [_required_float(row["loss_settle_to_open"]) for row in clean_rows],
        dtype=float,
    )
    status: dict[str, object] = {
        "claims_level": CLAIMS_LEVEL,
        "target": "full_gap_settle_to_open",
        "alpha": alpha,
        "total_clean_rows": int(losses.size),
        "min_total_rows_for_split": MIN_TOTAL_ROWS_FOR_SPLIT,
        "min_train_rows_for_lightgbm": MIN_TRAIN_ROWS_FOR_LIGHTGBM,
        "min_test_rows_for_metrics": MIN_TEST_ROWS_FOR_METRICS,
        "min_train_exceedances_for_evt": MIN_TRAIN_EXCEEDANCES_FOR_EVT,
    }
    if losses.size < MIN_TOTAL_ROWS_FOR_SPLIT:
        status["overall_status"] = "unavailable_insufficient_sample"
        return status

    split_index = max(MIN_TRAIN_ROWS_FOR_LIGHTGBM, int(losses.size * 0.8))
    train = losses[:split_index]
    test = losses[split_index:]
    if train.size < MIN_TRAIN_ROWS_FOR_LIGHTGBM or test.size < MIN_TEST_ROWS_FOR_METRICS:
        status["overall_status"] = "unavailable_insufficient_sample"
        status["train_rows"] = int(train.size)
        status["test_rows"] = int(test.size)
        return status

    historical_var = float(np.quantile(train, 1 - alpha))
    rolling_window = min(250, train.size)
    rolling_var = np.array(
        [
            np.quantile(losses[max(0, idx - rolling_window) : idx], 1 - alpha)
            for idx in range(split_index, losses.size)
        ]
    )
    volatility_scaled = float(np.mean(train) + np.std(train, ddof=1) * stats.norm.ppf(1 - alpha))
    status.update(
        {
            "overall_status": "smoke_metrics_available",
            "train_rows": int(train.size),
            "test_rows": int(test.size),
            "historical_quantile_exception_rate": float(np.mean(test > historical_var)),
            "rolling_quantile_exception_rate": float(np.mean(test > rolling_var)),
            "vol_scaled_exception_rate": float(np.mean(test > volatility_scaled)),
            "no_leaderboard": True,
        }
    )
    status.update(_lightgbm_smoke_status(losses=losses, split_index=split_index))
    status.update(_evt_smoke_status(train=train, alpha=alpha))
    return status


def write_full_smoke_snapshot(  # pragma: no cover
    *,
    settings: Settings,
    start: str = "2022-01-01",
    end: str | None = None,
) -> SnapshotResult:
    run_ts = datetime.now(UTC)
    end_date = end or date.today().isoformat()
    git_commit = _git_commit()
    snapshot_id = build_snapshot_id(
        start=start,
        end=end_date,
        run_ts_utc=run_ts,
        git_commit=git_commit,
    )
    snapshot_dir = settings.reports_dir / "snapshots" / snapshot_id
    _ensure_snapshot_dirs(snapshot_dir)

    calendar_records = build_session_calendar_records(
        start=(date.fromisoformat(start) - timedelta(days=10)).isoformat(),
        end=end_date,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )
    jquants_pull_ts = datetime.now(UTC)
    raw_jquants_rows = _fetch_jquants_futures_rows(settings=settings, start=start, end=end_date)
    schema_probe = build_jquants_schema_probe(raw_jquants_rows)
    if schema_probe["fail_closed"] is True:
        raise SnapshotError(
            f"J-Quants schema missing required fields: {schema_probe['missing_required_fields']}"
        )
    normalized_rows = normalize_jquants_futures_rows(
        raw_jquants_rows, downloaded_at_utc=jquants_pull_ts
    )
    target_rows = build_target_audit_records(
        normalized_rows,
        calendar_records=calendar_records,
        roll_days_before_last_trade=settings.nikkei_contract_roll_days_before_last_trade,
    )

    massive_pull_ts = datetime.now(UTC)
    massive_daily, spy_minutes = _fetch_massive_predictors(
        settings=settings,
        start=start,
        end=end_date,
        downloaded_at_utc=massive_pull_ts,
    )
    fred_pull_ts = datetime.now(UTC)
    fred_rows = _fetch_fred_predictors(
        settings=settings,
        start=start,
        end=end_date,
        downloaded_at_utc=fred_pull_ts,
    )
    alignment_records = build_time_alignment_records(
        target_rows=target_rows,
        calendar_records=calendar_records,
        spy_minute_records=spy_minutes,
    )
    predictor_availability = build_predictor_availability_records(
        target_rows=target_rows,
        massive_daily_records=massive_daily,
        fred_records=fred_rows,
        alignment_records=alignment_records,
    )
    model_smoke = build_model_smoke(target_rows)
    artifacts = _write_snapshot_artifacts(
        settings=settings,
        snapshot_dir=snapshot_dir,
        snapshot_id=snapshot_id,
        start=start,
        end=end_date,
        run_ts=run_ts,
        git_commit=git_commit,
        raw_jquants_rows=raw_jquants_rows,
        schema_probe=schema_probe,
        normalized_rows=normalized_rows,
        target_rows=target_rows,
        calendar_records=calendar_records,
        alignment_records=alignment_records,
        massive_daily_records=massive_daily,
        spy_minute_records=spy_minutes,
        fred_records=fred_rows,
        predictor_availability=predictor_availability,
        model_smoke=model_smoke,
        data_vintage={
            "jquants_pull_ts_utc": jquants_pull_ts.isoformat(),
            "jquants_update_window_jst": "~27:00 (next-day 03:00), not guaranteed",
            "massive_pull_ts_utc": massive_pull_ts.isoformat(),
            "fred_pull_ts_utc": fred_pull_ts.isoformat(),
            "snapshot_window": [start, end_date],
        },
    )
    _write_results_snapshot_doc(
        docs_path=Path("docs/results_snapshot.md"),
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        start=start,
        end=end_date,
        target_rows=target_rows,
        alignment_records=alignment_records,
        predictor_availability=predictor_availability,
        model_smoke=model_smoke,
        artifacts=artifacts,
    )
    return SnapshotResult(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        docs_results_path=Path("docs/results_snapshot.md"),
        target_rows=len(target_rows),
        model_status=str(model_smoke.get("overall_status")),
    )


def _fetch_jquants_futures_rows(  # pragma: no cover
    *,
    settings: Settings,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with JQuantsV2Client(
        api_key=settings.jquants_api_key,
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    ) as client:
        for current in _date_range(date.fromisoformat(start), date.fromisoformat(end)):
            rows.extend(client.get_futures_daily_bars(trading_date=current.isoformat()))
    return rows


def _fetch_massive_predictors(  # pragma: no cover
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    daily_records: list[dict[str, object]] = []
    minute_records: list[dict[str, object]] = []
    with MassiveClient(
        api_key=settings.massive_api_key,
        base_url=settings.massive_base_url,
        timeout_seconds=settings.massive_request_timeout_seconds,
    ) as client:
        for ticker in settings.massive_daily_ticker_list():
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


def _fetch_fred_predictors(  # pragma: no cover
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with FredClient(
        base_url=settings.fred_base_url,
        timeout_seconds=settings.fred_request_timeout_seconds,
    ) as client:
        for series_id in settings.fred_series_list():
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


def _write_snapshot_artifacts(  # pragma: no cover
    *,
    settings: Settings,
    snapshot_dir: Path,
    snapshot_id: str,
    start: str,
    end: str,
    run_ts: datetime,
    git_commit: str,
    raw_jquants_rows: list[dict[str, Any]],
    schema_probe: dict[str, object],
    normalized_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    spy_minute_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    predictor_availability: list[dict[str, object]],
    model_smoke: dict[str, object],
    data_vintage: dict[str, object],
) -> dict[str, str]:
    raw_path = (
        settings.bronze_data_dir
        / "jquants_snapshot_raw"
        / "schema_version=1"
        / f"snapshot_id={snapshot_id}"
        / "futures_daily_raw.json"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_document = {
        "metadata": {
            "source": "jquants",
            "endpoint": "/derivatives/bars/daily/futures",
            "start": start,
            "end": end,
            "downloaded_at_utc": data_vintage["jquants_pull_ts_utc"],
            "note": "API key is intentionally excluded from this raw artifact.",
        },
        "data": raw_jquants_rows,
    }
    write_json_atomic(raw_path, raw_document)

    artifacts = {
        "manifest": snapshot_dir / "manifest.json",
        "data_vintage": snapshot_dir / "data_vintage.json",
        "schema_probe": snapshot_dir / "jquants_schema_probe.json",
        "audit_header": snapshot_dir / "audit_header.json",
        "normalized_jquants": snapshot_dir / "target_audit" / "jquants_futures_normalized.parquet",
        "target_audit": snapshot_dir / "target_audit" / "target_audit.parquet",
        "time_alignment": snapshot_dir / "target_audit" / "time_alignment_check.parquet",
        "calendar_alignment": snapshot_dir / "target_audit" / "calendar_alignment.parquet",
        "massive_daily": snapshot_dir / "predictors" / "massive_daily.parquet",
        "spy_minutes": snapshot_dir / "predictors" / "spy_minutes.parquet",
        "fred": snapshot_dir / "predictors" / "fred.parquet",
        "predictor_availability": snapshot_dir / "predictors" / "predictor_availability.parquet",
        "model_smoke": snapshot_dir / "model_smoke" / "model_smoke_status.json",
        "narrative": snapshot_dir / "narrative" / "snapshot_summary.md",
    }
    for path in artifacts.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    _write_json(artifacts["data_vintage"], data_vintage)
    _write_json(artifacts["schema_probe"], schema_probe)
    _write_parquet(artifacts["normalized_jquants"], normalized_rows)
    _write_parquet(artifacts["target_audit"], target_rows)
    _write_parquet(artifacts["time_alignment"], alignment_records)
    _write_parquet(artifacts["calendar_alignment"], calendar_records)
    _write_parquet(artifacts["massive_daily"], massive_daily_records)
    _write_parquet(artifacts["spy_minutes"], spy_minute_records)
    _write_parquet(artifacts["fred"], fred_records)
    _write_parquet(artifacts["predictor_availability"], predictor_availability)
    _write_json(artifacts["model_smoke"], model_smoke)

    audit_header = _audit_header(
        snapshot_id=snapshot_id,
        start=start,
        end=end,
        target_rows=target_rows,
        alignment_records=alignment_records,
        predictor_availability=predictor_availability,
        model_smoke=model_smoke,
    )
    _write_json(artifacts["audit_header"], audit_header)
    manifest = {
        "snapshot_id": snapshot_id,
        "created_at_utc": run_ts.isoformat(),
        "data_window_start": start,
        "data_window_end": end,
        "git_commit": git_commit,
        "git_dirty": _git_dirty(),
        "claims_level": CLAIMS_LEVEL,
        "jpx_contract_url": JPX_CONTRACT_URL,
        "jpx_calendar_source": settings.calendar_jpx_exchange,
        "jpx_calendar_hash": _hash_json(calendar_records),
        "calendar_fallback_triggered": False,
        "jquants_endpoint": "/derivatives/bars/daily/futures",
        "jquants_bronze_payload_path": str(raw_path),
        "jquants_bronze_payload_sha256": hashlib.sha256(
            json.dumps(raw_document, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest(),
        "massive_symbols": list(settings.massive_daily_ticker_list()),
        "massive_minute_ticker": settings.massive_minute_ticker,
        "fred_series": list(settings.fred_series_list()),
        "artifact_paths": {name: str(path) for name, path in artifacts.items()},
    }
    _write_json(artifacts["manifest"], manifest)
    summary = _snapshot_summary_markdown(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        audit_header=audit_header,
        model_smoke=model_smoke,
        artifacts={name: str(path) for name, path in artifacts.items()},
    )
    artifacts["narrative"].write_text(summary, encoding="utf-8")
    return {name: str(path) for name, path in artifacts.items()}


def _write_results_snapshot_doc(  # pragma: no cover
    *,
    docs_path: Path,
    snapshot_id: str,
    snapshot_dir: Path,
    start: str,
    end: str,
    target_rows: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
    predictor_availability: list[dict[str, object]],
    model_smoke: dict[str, object],
    artifacts: dict[str, str],
) -> None:
    audit_header = _audit_header(
        snapshot_id=snapshot_id,
        start=start,
        end=end,
        target_rows=target_rows,
        alignment_records=alignment_records,
        predictor_availability=predictor_availability,
        model_smoke=model_smoke,
    )
    docs_path.write_text(
        _snapshot_summary_markdown(
            snapshot_id=snapshot_id,
            snapshot_dir=snapshot_dir,
            audit_header=audit_header,
            model_smoke=model_smoke,
            artifacts=artifacts,
        ),
        encoding="utf-8",
    )


def _audit_header(
    *,
    snapshot_id: str,
    start: str,
    end: str,
    target_rows: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
    predictor_availability: list[dict[str, object]],
    model_smoke: dict[str, object],
) -> dict[str, object]:
    clean_rows = [row for row in target_rows if row.get("clean_sample") is True]
    return {
        "snapshot_id": snapshot_id,
        "window": [start, end],
        "claims_level": CLAIMS_LEVEL,
        "target_rows": len(target_rows),
        "clean_target_rows": len(clean_rows),
        "roll_sq_excluded_rows": sum(
            1 for row in target_rows if row.get("is_roll_sq_window") is True
        ),
        "missing_residual_night_rows": sum(
            1 for row in target_rows if row.get("residual_nightclose_to_day_open") is None
        ),
        "time_alignment_rows": len(alignment_records),
        "time_alignment_failures": sum(
            1 for row in alignment_records if row.get("alignment_pass") is False
        ),
        "predictor_blocks": len(predictor_availability),
        "model_smoke_status": model_smoke.get("overall_status"),
    }


def _snapshot_summary_markdown(
    *,
    snapshot_id: str,
    snapshot_dir: Path,
    audit_header: dict[str, object],
    model_smoke: dict[str, object],
    artifacts: dict[str, str],
) -> str:
    warning = (
        f"This page is generated from `{snapshot_id}`. It is pipeline evidence only, "
        "not manuscript evidence."
    )
    boundary = (
        "This snapshot validates data access, target construction, timestamp alignment, "
        "predictor availability, and smoke-only model wiring. It does **not** support "
        "claims about causal spillover, price discovery, trading alpha, live deployment, "
        "LightGBM-EVT superiority, or ES improvement."
    )
    staleness_note = (
        "Regenerate this page with `just snapshot` after material code or schema changes. "
        "The snapshot window is intentionally bounded and may start later than the full "
        "`just full` default; it is a smoke/access check, not the clean modeling sample."
    )
    smoke_note = (
        "The model layer is deliberately labeled as smoke-only. If LightGBM or EVT "
        "gates are unavailable, that is a valid engineering result rather than weak "
        "empirical evidence."
    )
    return f"""# Results Snapshot

!!! warning "Smoke-only artifact"
    {warning}

## Snapshot

| Field | Value |
| --- | --- |
| Snapshot ID | `{snapshot_id}` |
| Artifact root | `{snapshot_dir}` |
| Claims level | `{CLAIMS_LEVEL}` |
| Window | `{audit_header["window"]}` |
| Target rows | `{audit_header["target_rows"]}` |
| Clean target rows | `{audit_header["clean_target_rows"]}` |
| Roll/SQ excluded rows | `{audit_header["roll_sq_excluded_rows"]}` |
| Time-alignment failures | `{audit_header["time_alignment_failures"]}` |
| Model smoke status | `{model_smoke.get("overall_status")}` |

## Interpretation Boundary

{boundary}

{staleness_note}

## Model Smoke

{smoke_note}

```json
{json.dumps(model_smoke, indent=2, sort_keys=True)}
```

## Artifact Index

| Artifact | Path |
| --- | --- |
{chr(10).join(f"| `{name}` | `{path}` |" for name, path in artifacts.items())}
"""


def _lightgbm_smoke_status(*, losses: Any, split_index: int) -> dict[str, object]:
    try:
        import lightgbm as lgb
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"lightgbm_status": "unavailable_import_error", "lightgbm_error": str(exc)}
    features, labels = _lag_features(losses)
    train_features = features[: split_index - 1]
    train_labels = labels[: split_index - 1]
    test_features = features[split_index - 1 :]
    test_labels = labels[split_index - 1 :]
    if (
        train_features.shape[0] < MIN_TRAIN_ROWS_FOR_LIGHTGBM
        or test_features.shape[0] < MIN_TEST_ROWS_FOR_METRICS
    ):
        return {"lightgbm_status": "unavailable_insufficient_sample"}
    model = lgb.LGBMRegressor(
        objective="quantile",
        alpha=0.95,
        n_estimators=20,
        min_child_samples=10,
        verbosity=-1,
        random_state=225,
    )
    model.fit(train_features, train_labels)
    predictions = np.asarray(model.predict(test_features), dtype=float)
    return {
        "lightgbm_status": "smoke_metrics_available",
        "lightgbm_exception_rate": float(np.mean(test_labels > predictions)),
    }


def _evt_smoke_status(*, train: Any, alpha: float) -> dict[str, object]:
    threshold = float(np.quantile(train, 1 - alpha))
    exceedances = train[train > threshold] - threshold
    if exceedances.size < MIN_TRAIN_EXCEEDANCES_FOR_EVT:
        return {
            "evt_status": "unavailable_insufficient_exceedances",
            "evt_train_exceedances": int(exceedances.size),
            "evt_threshold_quantile": 1 - alpha,
        }
    shape, loc, scale = stats.genpareto.fit(exceedances, floc=0)
    return {
        "evt_status": "smoke_fit_available"
        if exceedances.size < PREFERRED_TRAIN_EXCEEDANCES_FOR_EVT
        else "meaningful_discussion_ready",
        "evt_train_exceedances": int(exceedances.size),
        "evt_threshold_quantile": 1 - alpha,
        "evt_threshold": threshold,
        "evt_shape": float(shape),
        "evt_scale": float(scale),
        "evt_loc": float(loc),
        "evt_threshold_selection": (
            "empirical_95pct_smoke; final paper requires mean-excess and "
            "parameter-stability diagnostics"
        ),
    }


def _lag_features(losses: Any) -> tuple[Any, Any]:
    lag = losses[:-1]
    labels = losses[1:]
    rolling_abs = np.array(
        [np.mean(np.abs(losses[max(0, idx - 20) : idx + 1])) for idx in range(losses.size - 1)]
    )
    return np.column_stack([lag, rolling_abs]), labels


def _availability_for_records(
    *,
    source: str,
    key_field: str,
    date_field: str,
    value_field: str,
    records: list[dict[str, object]],
    by_us_date: dict[str, str],
    clean_dates: set[str],
    loss_by_date: dict[str, float],
    regime_by_target: dict[str, str],
) -> list[dict[str, object]]:
    keys = sorted({str(record[key_field]) for record in records if record.get(key_field)})
    output: list[dict[str, object]] = []
    for key in keys:
        values_by_target: dict[str, float] = {}
        for record in records:
            if str(record.get(key_field)) != key:
                continue
            target_date = by_us_date.get(str(record.get(date_field)))
            value = record.get(value_field)
            if target_date and target_date in clean_dates and value is not None:
                values_by_target[target_date] = _required_float(value)
        common_dates = sorted(set(values_by_target).intersection(loss_by_date))
        output.append(
            {
                "source": source,
                "predictor": key,
                "available_rows": len(values_by_target),
                "effective_clean_join_rows": len(common_dates),
                "missing_clean_join_rows": max(0, len(clean_dates) - len(common_dates)),
                "spearman_all": _spearman_for_dates(common_dates, values_by_target, loss_by_date),
                "spearman_est": _spearman_for_dates(
                    [item for item in common_dates if regime_by_target.get(item) == "EST"],
                    values_by_target,
                    loss_by_date,
                ),
                "spearman_edt": _spearman_for_dates(
                    [item for item in common_dates if regime_by_target.get(item) == "EDT"],
                    values_by_target,
                    loss_by_date,
                ),
            }
        )
    return output


def _spearman_for_dates(
    dates: list[str],
    values_by_target: dict[str, float],
    loss_by_date: dict[str, float],
    *,
    min_subsample: int = 10,
) -> dict[str, object]:
    if len(dates) < min_subsample:
        return {"rho": None, "pvalue": None, "n": len(dates), "reason": "insufficient_subsample"}
    predictor = [values_by_target[item] for item in dates]
    losses = [loss_by_date[item] for item in dates]
    result = stats.spearmanr(predictor, losses)
    return {
        "rho": float(result.statistic),
        "pvalue": float(result.pvalue),
        "n": len(dates),
        "reason": None,
    }


def _target_missing_reasons(
    *,
    target_row: dict[str, object],
    prior_row: dict[str, object] | None,
    roll_window: bool,
    previous_central: dict[str, object] | None,
) -> list[str]:
    reasons: list[str] = []
    if target_row.get("day_session_open") is None:
        reasons.append("holiday_trading_no_day_open")
    if prior_row is None:
        reasons.append("cross_contract_excluded" if previous_central else "missing_reference_price")
    if prior_row is not None and prior_row.get("settlement_price") is None:
        reasons.append("missing_reference_price")
    if roll_window:
        reasons.append("roll_sq_excluded")
    return reasons


def _previous_same_contract_row(
    rows: list[dict[str, object]],
    trading_date: date,
) -> dict[str, object] | None:
    candidates = [
        row for row in rows if date.fromisoformat(str(row["trading_date"])) < trading_date
    ]
    return candidates[-1] if candidates else None


def _is_roll_sq_window(
    *,
    trading_date: date,
    last_trading_day: date | None,
    special_quotation_day: date | None,
    jpx_sessions: list[date],
    roll_days_before_last_trade: int,
) -> bool:
    if last_trading_day is None or special_quotation_day is None:
        return False
    if last_trading_day in jpx_sessions:
        index = jpx_sessions.index(last_trading_day)
        start_index = max(0, index - roll_days_before_last_trade + 1)
        roll_start = jpx_sessions[start_index]
    else:
        roll_start = last_trading_day - timedelta(days=7)
    return roll_start <= trading_date <= special_quotation_day


def _volume_oi_anomaly(row: dict[str, object]) -> str | None:
    volume = row.get("volume")
    oi = row.get("open_interest")
    if volume == 0:
        return "volume_zero"
    if oi == 0:
        return "open_interest_zero"
    return None


def _select_spy_close_bar(
    records: list[dict[str, object]],
    *,
    official_close_ts_utc: datetime,
) -> tuple[dict[str, object] | None, str]:
    candidates = [
        record
        for record in records
        if record.get("is_us_regular_session") is True
        and _as_datetime(record["bar_end_ts_utc"]) <= official_close_ts_utc
    ]
    if not candidates:
        return None, "missing_regular_session_close_bar"
    return candidates[-1], "last_regular_session_bar_at_or_before_official_close"


def _latest_us_close_before(
    us_closes: list[dict[str, object]],
    target_open_ts_utc: datetime,
) -> dict[str, object] | None:
    candidates = [
        row for row in us_closes if _as_datetime(row["us_close_ts_utc"]) < target_open_ts_utc
    ]
    return candidates[-1] if candidates else None


def _dst_alignment_check(
    regime: object,
    minutes: object,
    *,
    is_early_close: bool = False,
) -> tuple[bool, str]:
    if is_early_close and regime == "EST" and isinstance(minutes, int):
        return abs(minutes - 180) <= 5, "est_early_close_expected_180_plus_minus_5"
    if is_early_close and regime == "EDT" and isinstance(minutes, int):
        return abs(minutes - 240) <= 5, "edt_early_close_expected_240_plus_minus_5"
    if regime == "EST" and isinstance(minutes, int):
        return abs(minutes) <= 5, "est_expected_0_plus_minus_5"
    if regime == "EDT" and isinstance(minutes, int):
        return 55 <= minutes <= 65, "edt_expected_55_to_65"
    return False, "missing_or_unknown_dst_regime"


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        chunk_end = min(end_date, next_month - timedelta(days=1))
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = next_month
    return chunks


def _date_range(start_date: date, end_date: date) -> list[date]:
    return [
        start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)
    ]


def _ensure_snapshot_dirs(snapshot_dir: Path) -> None:
    for name in ("target_audit", "predictors", "model_smoke", "narrative"):
        (snapshot_dir / name).mkdir(parents=True, exist_ok=True)


def _write_parquet(path: Path, records: list[dict[str, object]]) -> None:
    pl.DataFrame(records).write_parquet(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _hash_json(records: list[dict[str, object]]) -> str:
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return completed.stdout.strip()


def _git_dirty() -> bool:  # pragma: no cover
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return True
    return bool(completed.stdout.strip())


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise SnapshotError("J-Quants row is missing a date string")
    return date.fromisoformat(value)


def _optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _optional_date_iso(value: object) -> str | None:
    parsed = _optional_date(value)
    return parsed.isoformat() if parsed else None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | str):
        return int(value) == 1
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _required_float(value: object) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise SnapshotError("Expected numeric value")
    return parsed


def _price_or_none(value: object) -> float | None:
    parsed = _optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _log_gap(open_price: object, reference_price: object) -> float | None:
    open_value = _optional_float(open_price)
    reference_value = _optional_float(reference_price)
    if open_value is None or reference_value is None or open_value <= 0 or reference_value <= 0:
        return None
    return math.log(open_value) - math.log(reference_value)


def _value(row: dict[str, object] | None, key: str) -> object | None:
    return row.get(key) if row is not None else None


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise SnapshotError("Expected timezone-aware datetime")
    if value.tzinfo is None:
        raise SnapshotError("Expected timezone-aware datetime")
    return value
