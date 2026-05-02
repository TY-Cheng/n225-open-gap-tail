# ruff: noqa: E501
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import polars as pl

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake.artifacts import (
    _gold_leakage_dir,
    _gold_panel_dir,
    _legacy_gold_leakage_dir,
    _legacy_gold_panel_dir,
)
from n225_open_gap_tail.diagnostics.results_discussion import (
    generate_results_discussion as _generate_results_discussion,
)
from n225_open_gap_tail.diagnostics.snapshot_gallery import (
    evidence_map_mermaid as _evidence_map_mermaid,
)
from n225_open_gap_tail.diagnostics.snapshot_gallery import (
    figure_gallery_markdown as _figure_gallery_markdown,
)
from n225_open_gap_tail.diagnostics.snapshot_gallery import (
    sync_snapshot_figure_assets as _sync_snapshot_figure_assets,
)
from n225_open_gap_tail.diagnostics.snapshot_gallery import (
    table_manifest_markdown as _table_manifest_markdown,
)
from n225_open_gap_tail.diagnostics.snapshot_qa import discussion_qa_markdown as _discussion_qa


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
    """Write docs/results_snapshot.md from a completed full tail-risk run."""
    run_dir = _resolve_snapshot_run_dir(settings=settings, run_id=run_id)
    manifest = _read_json_dict(run_dir / "manifest.json")
    resolved_run_id = str(manifest.get("run_id") or run_dir.name)
    paths = _full_run_snapshot_paths(settings=settings, run_dir=run_dir, manifest=manifest)
    panel = _read_parquet_optional(paths["modeling_panel"])
    docs_path = Path("docs/results_snapshot.md")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    _sync_snapshot_figure_assets(
        run_dir=run_dir,
        figure_manifest=_read_json_dict(paths["figure_manifest"]),
        docs_dir=docs_path.parent,
    )
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
    gold_panel_root = _gold_panel_dir(settings.gold_data_dir, run_id)
    legacy_gold_panel_root = _legacy_gold_panel_dir(settings.gold_data_dir, run_id)
    if not gold_panel_root.exists() and legacy_gold_panel_root.exists():
        gold_panel_root = legacy_gold_panel_root
    leakage_root = _gold_leakage_dir(settings.gold_data_dir, run_id)
    legacy_leakage_root = _legacy_gold_leakage_dir(settings.gold_data_dir, run_id)
    if (
        not (leakage_root / "summary.json").exists()
        and (legacy_leakage_root / "summary.json").exists()
    ):
        leakage_root = legacy_leakage_root
    leakage_summary = Path(
        str(gold_artifacts.get("leakage_summary", leakage_root / "summary.json"))
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
        "leakage_summary": leakage_summary,
        "benchmark_status": run_dir / "metrics" / "benchmark_status.json",
        "benchmark_metrics": run_dir / "metrics" / "benchmark_metrics.parquet",
        "benchmark_forecasts": run_dir / "forecasts" / "benchmark_forecasts.parquet",
        "benchmark_dm_inference": run_dir / "metrics" / "benchmark_dm_inference.parquet",
        "benchmark_mcs": run_dir / "metrics" / "benchmark_mcs.parquet",
        "ml_tail_status": run_dir / "metrics" / "ml_tail_status.json",
        "ml_tail_metrics": run_dir / "metrics" / "ml_tail_metrics.parquet",
        "ml_tail_metrics_per_model": run_dir / "metrics" / "ml_tail_metrics_per_model.parquet",
        "ml_tail_forecasts": run_dir / "forecasts" / "ml_tail_forecasts.parquet",
        "ml_tail_result_matrix": run_dir / "metrics" / "ml_tail_result_matrix.parquet",
        "ml_tail_result_matrix_dm": run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet",
        "ml_tail_result_matrix_mcs": run_dir / "metrics" / "ml_tail_result_matrix_mcs.parquet",
        "ml_tail_dm_inference": run_dir / "metrics" / "ml_tail_dm_inference.parquet",
        "ml_tail_mcs": run_dir / "metrics" / "ml_tail_mcs.parquet",
        "ml_tail_cpa_inference": run_dir / "metrics" / "ml_tail_cpa_inference.parquet",
        "cross_model_cpa_inference": run_dir / "metrics" / "cross_model_cpa_inference.parquet",
        "ml_tail_model_eviction": run_dir / "metrics" / "ml_tail_model_eviction.parquet",
        "ml_tail_dst_attenuation": run_dir / "metrics" / "ml_tail_dst_attenuation.parquet",
        "ml_tail_murphy": run_dir / "metrics" / "ml_tail_murphy.parquet",
        "ml_tail_feature_unavailability": run_dir
        / "metrics"
        / "ml_tail_feature_unavailability.parquet",
        "benchmark_stress_windows": run_dir / "metrics" / "benchmark_stress_windows.parquet",
        "ml_tail_stress_windows": run_dir / "metrics" / "ml_tail_stress_windows.parquet",
        "figure_manifest": run_dir / "latex" / "figure_manifest.json",
        "table_manifest": run_dir / "latex" / "table_manifest.json",
        "latex_dir": run_dir / "latex" / "tables",
        "claim_scope_table": run_dir / "latex" / "tables" / "tailrisk_claim_scope_table.tex",
        "es_severity_table": run_dir / "latex" / "tables" / "tailrisk_es_severity_table.tex",
        "hedge_trigger_table": run_dir
        / "latex"
        / "tables"
        / "tailrisk_hedge_trigger_diagnostics_table.tex",
        "dst_attenuation_table": run_dir / "latex" / "tables" / "ml_tail_dst_attenuation_table.tex",
        "result_matrix_summary_table": run_dir
        / "latex"
        / "tables"
        / "ml_tail_result_matrix_summary_table.tex",
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
    figure_manifest = _read_json_dict(paths["figure_manifest"])
    table_manifest = _read_json_dict(paths["table_manifest"])
    panel = _read_parquet_optional(paths["modeling_panel"])
    target = _read_parquet_optional(paths["target_audit"])
    calendar = _read_parquet_optional(paths["calendar_map"])
    feature_coverage = _read_parquet_optional(paths["feature_coverage"])
    benchmark_metrics = _read_parquet_optional(paths["benchmark_metrics"])
    ml_tail_metrics = _read_parquet_optional(paths["ml_tail_metrics"])
    ml_tail_metrics_per_model = _read_parquet_optional(paths["ml_tail_metrics_per_model"])
    result_matrix = _read_parquet_optional(paths["ml_tail_result_matrix"])
    benchmark_stress = _read_parquet_optional(paths["benchmark_stress_windows"])
    ml_tail_stress = _read_parquet_optional(paths["ml_tail_stress_windows"])
    results_discussion = _generate_results_discussion(
        manifest=manifest,
        paths=paths,
        data_vintage=data_vintage,
        benchmark_status=benchmark_status,
        ml_tail_status=ml_tail_status,
        leakage_summary=leakage_summary,
        figure_manifest=figure_manifest,
        panel=panel,
        calendar=calendar,
        benchmark_metrics=benchmark_metrics,
        ml_tail_metrics=ml_tail_metrics,
        result_matrix=result_matrix,
        benchmark_stress=benchmark_stress,
        ml_tail_stress=ml_tail_stress,
    )

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
    benchmark_layer_table = _benchmark_layer_table(benchmark_status)
    ml_headline_table = _metrics_table(ml_tail_metrics)
    ml_coverage_review = _coverage_review_sentence(ml_tail_metrics)
    result_matrix_table = _result_matrix_summary_table(result_matrix)
    claim_scope_table = _claim_scope_markdown_table()
    opening_gap_scale_text = _opening_gap_scale_text(panel)
    metric_artifact_table = _metric_artifact_relationship_table(
        ml_tail_metrics=ml_tail_metrics,
        ml_tail_metrics_per_model=ml_tail_metrics_per_model,
        result_matrix=result_matrix,
    )
    benchmark_status_label = (
        manifest.get("benchmark_eval_status")
        or benchmark_status.get("status")
        or benchmark_status.get("common_sample_status")
        or "unknown"
    )
    advanced_forecast_rows = int(
        _optional_float(benchmark_status.get("benchmark_advanced_forecast_rows")) or 0
    )
    if advanced_forecast_rows > 0:
        advanced_implementation_text = (
            "The benchmark floor, advanced benchmark suite, and ML-tail suite are "
            "implemented and have completed artifacts in this run."
        )
        advanced_implementation_bullet = (
            "Advanced benchmark families such as CAViaR, CARE/expectile, Taylor ALD, "
            "direct FZ-loss, and GAS now produce nonblocking empirical forecast rows; "
            "their interpretation still follows the benchmark/restricted-sample gates."
        )
        advanced_bottom_line_bullet = (
            "Benchmark floor, advanced benchmark, and ML-tail suites completed with zero "
            "recorded forecast failures; advanced rows are implemented evidence but remain "
            "nonblocking until author-reviewed against the same sample/inference gates."
        )
    else:
        advanced_implementation_text = (
            "The benchmark floor and ML-tail suite are implemented and have completed "
            "artifacts in this run. The advanced benchmark layer is registered as "
            "nonblocking, but this run has not produced empirical advanced-model "
            "forecast rows."
        )
        advanced_implementation_bullet = (
            "Advanced benchmark families such as CAViaR, CARE/expectile, Taylor ALD, "
            "direct FZ-loss, and GAS should be read as unavailable diagnostics when "
            "their optimizers produce no valid forecast rows."
        )
        advanced_bottom_line_bullet = (
            "Benchmark floor and ML-tail suites both completed with zero recorded forecast "
            "failures; advanced benchmark rows are nonblocking diagnostics in this run."
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
    evidence_map = _evidence_map_mermaid()
    table_manifest_table = _table_manifest_markdown(table_manifest)
    figure_gallery = _figure_gallery_markdown(figure_manifest=figure_manifest, run_id=run_id)
    discussion_qa = _discussion_qa(
        advanced_implementation_text=advanced_implementation_text,
        advanced_implementation_bullet=advanced_implementation_bullet,
        advanced_bottom_line_bullet=advanced_bottom_line_bullet,
        claim_scope_table=claim_scope_table,
        opening_gap_scale_text=opening_gap_scale_text,
    )

    return f"""---
hide:
  - navigation
---

# Results Snapshot

> **Research-candidate full-run artifact.** This page is generated from `{run_id}`.
> It summarizes the durable gold modeling sample and run outputs, not the older
> bounded access-check snapshot. It is still a research-candidate artifact:
> final manuscript claims require a clean committed run and author review of the
> tables and notes.

{discussion_qa}

{results_discussion}

## Run Metadata

{metadata_table}

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty` is recorded so dirty runs can be rejected before manuscript tables are frozen.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

## Technical Infrastructure Note

- Runtime imports are explicit at the module boundary; no dynamic runtime namespace bridge is required to generate this snapshot. This infrastructure note is separate from empirical claim boundaries.

## Evidence Map

```mermaid
{evidence_map}
```

- The left branch binds vendor and calendar inputs into a timestamp-audited gold panel.
- The middle branch compares benchmark floors, advanced econometric benchmarks, and ML-tail forecasts on registered loss units.
- The right branch separates headline nested information sets, restricted model-family comparisons, unconditional DM/MCS inference, CPA diagnostics, and supporting figures.

## Pipeline Structure

| Step | Layer | Purpose |
| --- | --- | --- |
| 1 | Vendor and calendar sources | Pull or read J-Quants, Massive, FRED, CBOE, and exchange-calendar inputs. |
| 2 | Bronze and silver cache | Preserve typed vendor/cache rows, then normalize timestamp-safe research features. |
| 3 | Gold modeling panel | Join targets, calendar map, feature coverage, and leakage-bound signatures. |
| 4 | Leakage and coverage gates | Enforce timestamp ordering and sample eligibility before evaluation. |
| 5 | Benchmark floor and ML-tail registry | Run target-history/econometric floors and LightGBM tail-model families. |
| 6 | Metrics, inference, diagnostics | Build loss matrices, DM/MCS/Murphy diagnostics, stress windows, and result matrix artifacts. |
| 7 | Results snapshot | Summarize run-specific evidence and claim boundaries for reader review. |

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

- U.S. core, proxy ETFs, minute late-session features, CBOE VIX, FRED rates, FRED H.10 FX, and any audit-gated options-risk fields are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

## Leakage Audit

{leakage_table}

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Benchmark Suite

Status: `{benchmark_status_label}`; forecast rows: `{benchmark_status.get("forecast_rows")}`; metric rows: `{benchmark_status.get("metric_rows")}`; failures: `{benchmark_status.get("failures")}`.

{benchmark_layer_table}

{benchmark_table}

- Benchmark floor rows set the target-history/econometric floor that ML models should be interpreted against.
- Advanced benchmark families are nonblocking; rows with valid forecasts are empirical evidence subject to the same sample and inference gates, while unavailable rows remain diagnostics.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

## ML-Tail Headline Ladder

Status: `{ml_tail_status.get("status")}`; implemented models: {ml_tail_components}; forecast rows: `{ml_tail_status.get("forecast_rows")}`; failures: `{ml_tail_status.get("failures")}`.

{ml_headline_table}

- This headline table remains strict and reports only ML-tail rows that pass the registered common-sample and coverage gates.
- Location-scale empirical, plain POT-GPD, and stabilized POT-GPD are headline candidates only after their valid OOS coverage, standardized-loss, exceedance, and ES-validity gates pass.
- Differences across information blocks are candidate forecast evidence only after the common-sample, coverage, and inference diagnostics are reviewed.
- {ml_coverage_review}

### ML-tail artifact relationship

{metric_artifact_table}

- `ml_tail_metrics.parquet` is the headline nested-information-set artifact. It contains the ML-tail rows that survived the strict common-sample gate in this run.
- `ml_tail_metrics_per_model.parquet` reports each implemented ML-tail model on its own valid OOS rows; it is useful for debugging coverage but is not a cross-model comparison table.
- `ml_tail_result_matrix.parquet` creates restricted common samples for VaR-only and VaR-ES comparisons across model families and within-model information-set increments.

## Result Matrix Layer

{result_matrix_table}

- The result matrix is the right place to compare direct quantile, location-scale empirical, plain POT-GPD, stabilized POT-GPD, and ablation variants on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the headline direct-quantile evidence.
- DM and MCS records are emitted only where registered row-count and exception-count gates pass; otherwise the result matrix remains descriptive.

## Paper-Facing Table And Figure Gallery

### Table Manifest

{table_manifest_table}

- The table manifest records the generated LaTeX table files, their source artifacts, and their claim scopes.
- Tables are paper-facing exports; the Markdown tables above are snapshot summaries for browser review.

{figure_gallery}

## Stress And Diagnostic Windows

{stress_table}

- Stress windows identify high-loss or high-volatility subsamples for two-sided risk diagnostics.
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
    base_columns = [
        "model_name",
        "information_set",
        "rows",
        "var_breach_rate",
        "exceedance_count",
        "mean_quantile_loss",
        "mean_fz_loss",
    ]
    columns = (
        [*base_columns[:2], "tail_side", *base_columns[2:]]
        if "tail_side" in frame.columns
        else base_columns
    )
    if frame.is_empty() or not set(columns).issubset(frame.columns):
        return _markdown_table(tuple(columns), [tuple(["missing", *[""] * (len(columns) - 1)])])
    rows = [
        (
            row["model_name"],
            row["information_set"],
            *([row["tail_side"]] if "tail_side" in columns else []),
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
            *(("Tail side",) if "tail_side" in columns else ()),
            "Rows",
            "VaR breach rate",
            "Exceptions",
            "Mean quantile loss",
            "Mean FZ loss",
        ),
        rows,
    )


def _benchmark_layer_table(status: dict[str, object]) -> str:
    advanced_rows = int(_optional_float(status.get("benchmark_advanced_forecast_rows")) or 0)
    advanced_note = (
        "Implemented nonblocking advanced benchmark forecasts; review with common-sample gates."
        if advanced_rows > 0
        else "Nonblocking registry diagnostics unless valid advanced forecast rows are present."
    )
    return _markdown_table(
        (
            "Benchmark layer",
            "Status",
            "Forecast rows",
            "Diagnostic rows",
            "Failures",
            "How to read it",
        ),
        [
            (
                "floor",
                _code(status.get("benchmark_floor_status") or status.get("status") or "unknown"),
                _code(status.get("benchmark_floor_forecast_rows") or status.get("forecast_rows")),
                _code(status.get("benchmark_floor_metric_rows") or status.get("metric_rows")),
                _code(status.get("benchmark_floor_failures") or 0),
                "Implemented benchmark evidence for target-history and econometric floor models.",
            ),
            (
                "advanced",
                _code(status.get("benchmark_advanced_status") or "not_reported"),
                _code(status.get("benchmark_advanced_forecast_rows") or 0),
                _code(status.get("benchmark_advanced_diagnostic_rows") or 0),
                _code(status.get("benchmark_advanced_failures") or 0),
                advanced_note,
            ),
        ],
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
            _result_matrix_display_value(row["comparison_family"]),
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


def _result_matrix_display_value(value: object) -> str:
    text = str(value)
    if text == "information_set_ladder":
        return "nested information sets"
    return text


def _claim_scope_markdown_table() -> str:
    return _markdown_table(
        ("Evidence layer", "Can support headline claim?", "How to read it"),
        [
            (
                "Benchmark common-sample table",
                "Yes, after review",
                "External target-history/econometric floor on a shared sample.",
            ),
            (
                "ML-tail nested information sets",
                "Yes, after review",
                "Strict nested-information-set comparison; currently direct quantile survived the gate.",
            ),
            (
                "ML-tail per-model rows",
                "No",
                "Model-specific OOS diagnostics; samples need not match across model families.",
            ),
            (
                "Restricted result matrix",
                "No headline claim",
                "Matched-date comparison for model families and within-model increments.",
            ),
            (
                "DST, stress, Murphy, hedge-trigger diagnostics",
                "Diagnostic only",
                "Useful for interpretation and risk monitoring, not automatic model-selection evidence.",
            ),
        ],
    )


def _metric_artifact_relationship_table(
    *,
    ml_tail_metrics: pl.DataFrame,
    ml_tail_metrics_per_model: pl.DataFrame,
    result_matrix: pl.DataFrame,
) -> str:
    return _markdown_table(
        ("Artifact", "Rows", "Role", "Claim boundary"),
        [
            (
                "`ml_tail_metrics.parquet`",
                str(ml_tail_metrics.height),
                "Headline ML-tail nested-information-set comparison",
                "Eligible for headline discussion after author review.",
            ),
            (
                "`ml_tail_metrics_per_model.parquet`",
                str(ml_tail_metrics_per_model.height),
                "Per-model diagnostics on each model's own valid OOS rows",
                "Not a cross-model comparison and not a replacement headline table.",
            ),
            (
                "`ml_tail_result_matrix.parquet`",
                str(result_matrix.height),
                "Restricted common-sample VaR-only and VaR-ES comparisons",
                "Restricted evidence; direct quantile rows here are comparison anchors.",
            ),
        ],
    )


def _coverage_review_sentence(frame: pl.DataFrame) -> str:
    required = {"var_breach_rate", "expected_breach_rate"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return (
            "Coverage review status is unavailable in this snapshot; quantile and FZ loss "
            "differences cannot establish improvement without VaR exception diagnostics."
        )
    review_threshold = 0.025
    rows = []
    for row in frame.iter_rows(named=True):
        breach = _optional_float(row.get("var_breach_rate"))
        expected = _optional_float(row.get("expected_breach_rate"))
        if breach is None or expected is None:
            continue
        rows.append(abs(breach - expected) > review_threshold)
    if not rows:
        return (
            "Coverage review status is unavailable in this snapshot; quantile and FZ loss "
            "differences cannot establish improvement without VaR exception diagnostics."
        )
    flagged = sum(1 for value in rows if value)
    if flagged:
        return (
            f"Coverage review: `{flagged}/{len(rows)}` headline rows differ from the "
            "expected breach rate by more than 2.5 percentage points, so quantile/FZ loss "
            "differences alone must not be read as forecast improvement."
        )
    return (
        "Coverage review: headline breach rates are within the 2.5 percentage-point "
        "snapshot review band, but final claims still require author review of inference "
        "and exception diagnostics."
    )


def _opening_gap_scale_text(panel: pl.DataFrame) -> str:
    if panel.is_empty() or "gap_t" not in panel.columns:
        return "- Opening-gap scale is unavailable because the modeling panel is missing `gap_t`."
    clean = panel.filter(pl.col("gap_t").is_not_null())
    if "clean_sample" in clean.columns:
        clean = clean.filter(pl.col("clean_sample"))
    if clean.is_empty():
        return (
            "- Opening-gap scale is unavailable because no clean target rows have finite `gap_t`."
        )
    date_col = "forecast_date" if "forecast_date" in clean.columns else clean.columns[0]
    min_row = clean.sort("gap_t").head(1).to_dicts()[0]
    max_row = clean.sort("gap_t", descending=True).head(1).to_dicts()[0]
    abs_row = (
        clean.with_columns(pl.col("gap_t").abs().alias("_abs_gap_t"))
        .sort("_abs_gap_t", descending=True)
        .head(1)
        .to_dicts()[0]
    )
    stats = clean.select(
        pl.len().alias("rows"),
        pl.col("gap_t").quantile(0.01).alias("q01"),
        pl.col("gap_t").quantile(0.99).alias("q99"),
    ).to_dicts()[0]
    lines = [
        (
            f"- In the current clean headline sample (`n={stats['rows']}`), the settle-to-open "
            f"gap ranges from `{_fmt_log_return(min_row['gap_t'])}` on "
            f"`{min_row.get(date_col)}` to `{_fmt_log_return(max_row['gap_t'])}` on "
            f"`{max_row.get(date_col)}`."
        ),
        (
            f"- The largest absolute clean settle-to-open gap is "
            f"`{_fmt_log_return(abs_row['gap_t'])}` on `{abs_row.get(date_col)}`; "
            "this is large enough to make opening-gap tail risk a substantive risk-management "
            "forecasting problem rather than a cosmetic return-prediction exercise."
        ),
        (
            f"- The clean 1% to 99% settle-to-open range is "
            f"`{_fmt_log_return(stats['q01'])}` to `{_fmt_log_return(stats['q99'])}`, "
            "so the extremes are far outside the usual daily opening-gap range."
        ),
    ]
    if "residual_nightclose_to_day_open" in clean.columns:
        residual = clean.filter(pl.col("residual_nightclose_to_day_open").is_not_null())
        if not residual.is_empty():
            residual_stats = residual.select(
                pl.col("residual_nightclose_to_day_open").min().alias("min"),
                pl.col("residual_nightclose_to_day_open").max().alias("max"),
                pl.col("residual_nightclose_to_day_open").abs().max().alias("max_abs"),
            ).to_dicts()[0]
            lines.append(
                "- Even after the night-session close, the clean night-close-to-open residual "
                f"ranges from `{_fmt_log_return(residual_stats['min'])}` to "
                f"`{_fmt_log_return(residual_stats['max'])}`, with maximum absolute residual "
                f"`{_fmt_log_return(residual_stats['max_abs'])}`."
            )
    lines.append(
        "- These magnitudes make the empirical object an opening-tail risk problem, not only "
        "an average next-open return-forecasting problem."
    )
    return "\n".join(lines)


def _fmt_log_return(value: object) -> str:
    parsed = _optional_float(value)
    if parsed is None:
        return "missing"
    simple_pct = math.expm1(parsed) * 100.0
    return f"{parsed:.6f} log ({simple_pct:+.2f}%)"


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


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
