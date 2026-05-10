# ruff: noqa: E501
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import polars as pl

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
    display_source_block_label,
    display_status_label,
)
from n225_open_gap_tail.config.runtime import ML_TAIL_MODEL_NAMES
from n225_open_gap_tail.diagnostics import snapshot_gallery as _snapshot_gallery
from n225_open_gap_tail.diagnostics.model_comparison import _all_model_comparison_table
from n225_open_gap_tail.diagnostics.results_discussion import (
    generate_results_discussion as _generate_results_discussion,
)
from n225_open_gap_tail.diagnostics.snapshot_formatting import (
    _bool_sum,
    _code,
    _count_value,
    _counts_table,
    _demote_markdown_headings,
    _fmt_float,
    _fmt_rate,
    _forecast_sample_bounds,
    _join_model_list,
    _markdown_table,
    _optional_float,
    _panel_bounds,
    _result_matrix_display_value,
    _unique_values,
)
from n225_open_gap_tail.diagnostics.snapshot_paths import (
    full_run_snapshot_paths as _full_run_snapshot_paths,
)
from n225_open_gap_tail.diagnostics.snapshot_qa import (
    advanced_benchmark_qa_text as _advanced_benchmark_qa_text,
)
from n225_open_gap_tail.diagnostics.snapshot_qa import discussion_qa_markdown as _discussion_qa
from n225_open_gap_tail.diagnostics.target_distribution import (
    opening_gap_scale_text as _opening_gap_scale_text,
)
from n225_open_gap_tail.diagnostics.target_distribution import (
    target_tail_diagnostics_markdown as _target_tail_diagnostics_markdown,
)
from n225_open_gap_tail.reporting.latex import _promoted_tail_model_rows


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
    discussion_path = Path("docs/discussion_qa.md")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    _snapshot_gallery.sync_snapshot_figure_assets(
        run_dir=run_dir,
        figure_manifest=_read_json_dict(paths["figure_manifest"]),
        docs_dir=docs_path.parent,
    )
    discussion_path.write_text(
        _full_run_discussion_qa_markdown(
            run_dir=run_dir,
            manifest=manifest,
            paths=paths,
        ),
        encoding="utf-8",
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
        if not _is_completed_full_run(run_dir):
            raise SnapshotError(f"Run is not a completed full tail-risk run: {run_dir}")
        return run_dir
    candidates = sorted(
        (
            path
            for path in runs_dir.glob("tailrisk_*")
            if (path / "manifest.json").exists() and _is_completed_full_run(path)
        ),
        key=lambda path: (path / "manifest.json").stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SnapshotError("No completed tail-risk run found under reports/runs")
    return candidates[0]


def _is_completed_full_run(run_dir: Path) -> bool:
    manifest = _read_json_dict(run_dir / "manifest.json")
    return bool(manifest.get("benchmark_eval_status") and manifest.get("ml_tail_eval_status"))


def _read_json_dict(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _read_parquet_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _filter_current_ml_tail_models(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty() or "model_name" not in frame.columns:
        return frame
    return frame.filter(pl.col("model_name").is_in(list(ML_TAIL_MODEL_NAMES)))


def _full_run_discussion_qa_markdown(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    paths: dict[str, Path],
) -> str:
    benchmark_status = _read_json_dict(paths["benchmark_status"])
    panel = _read_parquet_optional(paths["modeling_panel"])
    (
        advanced_implementation_text,
        advanced_implementation_bullet,
        advanced_bottom_line_bullet,
    ) = _advanced_benchmark_qa_text(
        int(_optional_float(benchmark_status.get("benchmark_advanced_forecast_rows")) or 0)
    )
    return _discussion_qa(
        advanced_implementation_text=advanced_implementation_text,
        advanced_implementation_bullet=advanced_implementation_bullet,
        advanced_bottom_line_bullet=advanced_bottom_line_bullet,
        claim_scope_table=_claim_scope_markdown_table(),
        opening_gap_scale_text=_opening_gap_scale_text(panel),
    )


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
    benchmark_metrics_per_model = _read_parquet_optional(paths["benchmark_metrics_per_model"])
    ml_tail_metrics = _read_parquet_optional(paths["ml_tail_metrics"])
    ml_tail_metrics_per_model = _filter_current_ml_tail_models(
        _read_parquet_optional(paths["ml_tail_metrics_per_model"])
    )
    result_matrix = _filter_current_ml_tail_models(
        _read_parquet_optional(paths["ml_tail_result_matrix"])
    )
    result_matrix_dm = _filter_current_ml_tail_models(
        _read_parquet_optional(paths["ml_tail_result_matrix_dm"])
    )
    result_matrix_mcs = _filter_current_ml_tail_models(
        _read_parquet_optional(paths["ml_tail_result_matrix_mcs"])
    )
    benchmark_stress = _read_parquet_optional(paths["benchmark_stress_windows"])
    ml_tail_stress = _read_parquet_optional(paths["ml_tail_stress_windows"])
    results_discussion = _demote_markdown_headings(
        _generate_results_discussion(
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
        ),
        levels=1,
    ).replace("### Results And Discussion", "### Results interpretation and claim boundaries")

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
    ml_primary_table = _metrics_table(ml_tail_metrics)
    ml_coverage_review = _coverage_review_sentence(ml_tail_metrics)
    result_matrix_table = _result_matrix_summary_table(result_matrix)
    metric_artifact_table = _metric_artifact_relationship_table(
        ml_tail_metrics=ml_tail_metrics,
        ml_tail_metrics_per_model=ml_tail_metrics_per_model,
        result_matrix=result_matrix,
    )
    all_model_comparison_table = _all_model_comparison_table(
        benchmark_metrics=benchmark_metrics,
        benchmark_metrics_per_model=benchmark_metrics_per_model,
        ml_tail_metrics_per_model=ml_tail_metrics_per_model,
    )
    promoted_tail_model_table = _promoted_tail_model_markdown_table(
        ml_tail_metrics_per_model,
        dm=result_matrix_dm,
        mcs=result_matrix_mcs,
    )
    benchmark_status_label = (
        manifest.get("benchmark_eval_status")
        or benchmark_status.get("status")
        or benchmark_status.get("common_sample_status")
        or "unknown"
    )
    ml_tail_components = _join_model_list(ML_TAIL_MODEL_NAMES)
    ml_tail_status_label = display_status_label(ml_tail_status.get("status"))
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
    evidence_map = _snapshot_gallery.evidence_map_mermaid()
    table_manifest_table = _snapshot_gallery.table_manifest_markdown(table_manifest)
    configuration_sensitivity = _configuration_sensitivity_markdown(run_dir)
    figure_gallery = _demote_markdown_headings(
        _snapshot_gallery.figure_gallery_markdown(
            figure_manifest=figure_manifest,
            run_id=run_id,
        ),
        levels=1,
    )
    target_tail_diagnostics = _demote_markdown_headings(
        _target_tail_diagnostics_markdown(
            panel=panel,
            figure_manifest=figure_manifest,
            run_id=run_id,
        ),
        levels=1,
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

## Introduction

The framing questions have moved to [Discussion Q&A](discussion_qa.md). This snapshot is organized as a paper-facing evidence map: data and target construction first, model and evaluation design second, results third, and paper-facing exports and artifact provenance at the end.

The main result tables are in the Results section. Full table and figure provenance is collected in the Appendix section, including source artifacts and claim scopes for paper-facing outputs.

### Evidence Map

```mermaid
{evidence_map}
```

- The left branch binds vendor and calendar inputs into a timestamp-audited gold panel.
- The middle branch compares baseline benchmarks, advanced econometric benchmarks, and ML-tail forecasts on registered loss units.
- The right branch separates primary ML nested information sets, diagnostic model-family comparisons, unconditional DM/MCS inference, CPA diagnostics, and supporting figures.

## Materials: Data And Target

### Run Metadata

{metadata_table}

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty` is recorded so dirty runs can be rejected before manuscript tables are frozen.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

{target_tail_diagnostics}

### Gold Panel Construction

{panel_table}

{target_table}

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

### Calendar And Timing Map

{calendar_table}

- The map covers EST/EDT, early closes, U.S./Japan holiday desynchronization, and normal trading alignments.
- Desync rows are not treated as normal forecast rows.
- The timing map is part of the leakage-bound gold artifact, not ad hoc evaluation logic.

### Feature Coverage

{feature_table}

- U.S. core, proxy ETFs, minute late-session features, CBOE VIX, FRED rates, FRED H.10 FX, and any audit-gated options-risk fields are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

### Leakage Audit

{leakage_table}

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Methods: Model Configuration And Evaluation

### Pipeline Structure

| Step | Layer | Purpose |
| --- | --- | --- |
| 1 | Vendor and calendar sources | Pull or read J-Quants, Massive, FRED, CBOE, and exchange-calendar inputs. |
| 2 | Bronze and silver cache | Preserve typed vendor/cache rows, then normalize point-in-time research features. |
| 3 | Gold modeling panel | Join targets, calendar map, feature coverage, and leakage-bound signatures. |
| 4 | Leakage and coverage gates | Enforce timestamp ordering and sample eligibility before evaluation. |
| 5 | Baseline benchmarks and ML-tail registry | Run target-history/econometric baseline benchmarks and LightGBM tail-model families. |
| 6 | Metrics, inference, diagnostics | Build loss matrices, DM/MCS/Murphy diagnostics, stress windows, and result matrix artifacts. |
| 7 | Results snapshot | Summarize run-specific evidence and claim boundaries for reader review. |

- Data-access and cache artifacts live under `data/bronze` and `data/silver`.
- Durable modeling evidence lives under `data/gold`; forecast/evaluation/reporting read from gold and reports.
- Run-specific forecasts, metrics, diagnostics, and LaTeX tables live under `reports/runs/<run_id>`.

### Model And Evaluation Protocol

- The registered risk level is `tail_level = 0.95`; the nominal VaR exception rate is 5%.
- A VaR exception is counted when `realized_loss > var_forecast`; this follows the
  standard exception-counting logic of VaR backtesting, but the snapshot does not
  apply Basel green/yellow/red traffic-light capital zones.
- Forecast evaluation is based on coverage diagnostics, Kupiec/Christoffersen
  tests where available, quantile loss, Fissler-Ziegel joint VaR-ES loss, and
  DM/MCS inference.
- Benchmarks use target-history information only. ML-tail models add predictors through fixed nested information sets.
- Most specifications use expanding pre-forecast training histories. The rolling-quantile benchmark is the designed exception and uses the most recent 1,000 clean observations.
- LightGBM hyperparameters are held fixed across information sets and refit dates; the snapshot reports model-family evidence rather than tuning-search evidence.
- DM/MCS inference is read on average across the unconditional evaluation sample. CPA is read as a conditional loss-difference diagnostic, not as a forecasting model.

## Results And Discussion

### Main result tables

#### Benchmark Suite

Status: `{benchmark_status_label}`; forecast rows: `{benchmark_status.get("forecast_rows")}`; metric rows: `{benchmark_status.get("metric_rows")}`; failures: `{benchmark_status.get("failures")}`.

{benchmark_layer_table}

{benchmark_table}

- Baseline benchmark rows set the target-history/econometric reference that ML models should be interpreted against.
- Advanced econometric benchmark families are nonblocking; rows with valid forecasts are empirical evidence subject to the same sample and inference gates, while unavailable rows remain diagnostics.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

#### Primary ML Specifications

Status: `{ml_tail_status_label}`; implemented models: {ml_tail_components}; forecast rows: `{ml_tail_status.get("forecast_rows")}`; failures: `{ml_tail_status.get("failures")}`.

{ml_primary_table}

- This primary ML table remains strict and reports only ML-tail rows that pass the registered common-sample and coverage gates.
- Location-scale empirical and plain POT-GPD are primary candidates only after their valid OOS coverage, standardized-loss, exceedance, and ES-validity gates pass.
- Differences across information blocks are candidate forecast evidence only after the common-sample, coverage, and inference diagnostics are reviewed.
- {ml_coverage_review}

#### Side-specific ML-tail Promotion Gate

{promoted_tail_model_table}

- This paper-facing bridge promotes side-specific ML-tail candidates only after the N/coverage gate and restricted common-sample inference are visible.
- In the current run the left-tail promoted row is median/IQR POT-GPD, while the right-tail promoted row is location-scale empirical.
- This is not a universal model-family ranking and does not replace the strict primary nested-information-set table above.

#### ML-tail artifact relationship

{metric_artifact_table}

- `ml_tail_metrics.parquet` is the primary nested-information-set artifact. It contains the ML-tail rows that survived the strict common-sample gate in this run.
- `ml_tail_metrics_per_model.parquet` reports each implemented ML-tail model on its own valid OOS rows; it is useful for debugging coverage but is not a cross-model comparison table.
- `ml_tail_result_matrix.parquet` creates restricted common samples for VaR-only and VaR-ES comparisons across model families and within-model information-set increments.

### Other result tables

#### All-model diagnostic scan

{all_model_comparison_table}

- This table joins `benchmark_metrics_per_model.parquet` and `ml_tail_metrics_per_model.parquet` so all benchmark and LGBM tail-model variants are visible in one place.
- Mean and standard deviation are computed across registered metric rows for the same suite/model/information-set configuration; for most rows this summarizes left- and right-tail metrics.
- It is a diagnostic scan, not the formal cross-model comparison table. Cross-model claims still require common-sample result-matrix, DM, and MCS evidence because valid dates and model gates can differ.

#### Restricted Common-Sample Result Matrix

{result_matrix_table}

- The result matrix is the right place to compare direct quantile, location-scale empirical, plain POT-GPD, and the robust plain POT-GPD routes on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the primary direct-quantile evidence.
- DM and MCS records are emitted only where registered row-count and exception-count gates pass; otherwise the result matrix remains descriptive.

#### Stress And Diagnostic Windows

{stress_table}

- Stress windows identify high-loss or high-volatility subsamples for two-sided risk diagnostics.
- These rows use reproducible full-sample classifiers in this first pass, so they should be described as diagnostics rather than a live stress classifier.
- They are useful for finding whether model behavior changes in difficult regimes before writing manuscript discussion.

{results_discussion}

## Appendix: Tables, Figures, And Run Artifacts

The appendix collects generated exports and provenance. The main Results section refers back to these files when a table or figure is suitable for manuscript use.

### Paper-Facing Table And Figure Gallery

#### Appendix Configuration Robustness

{configuration_sensitivity}

#### Table Manifest

{table_manifest_table}

- The table manifest records the generated LaTeX table files, their source artifacts, and their claim scopes.
- Tables are paper-facing exports; the Markdown tables above are snapshot summaries for browser review.

{figure_gallery}

### Artifact Index

{artifact_table}

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.

### Technical Infrastructure Note

- Runtime imports are explicit at the module boundary; no dynamic runtime namespace bridge is required to generate this snapshot. This infrastructure note is separate from empirical claim boundaries.
"""


def _configuration_sensitivity_markdown(run_dir: Path) -> str:
    status_path = run_dir / "sensitivity" / "metrics" / "sensitivity_status.json"
    metrics_root = run_dir / "sensitivity" / "metrics"
    if not status_path.exists():
        return (
            "Appendix configuration robustness has not been generated for this run. "
            "Run `just sensitivity latest` after the canonical full run, then rerun "
            "`just snapshot latest`."
        )
    status = _read_json_dict(status_path)
    rows = [
        (
            "LGBM capacity",
            _sensitivity_metric_summary(
                metrics_root / "lgbm_configuration_sensitivity_metrics.parquet"
            ),
        ),
        (
            "EWMA lambda",
            _sensitivity_metric_summary(
                metrics_root / "benchmark_configuration_sensitivity_metrics.parquet"
            ),
        ),
        (
            "POT threshold",
            _sensitivity_metric_summary(metrics_root / "evt_threshold_sensitivity_metrics.parquet"),
        ),
    ]
    return "\n\n".join(
        (
            _markdown_table(
                ("Field", "Value"),
                [
                    ("Source primary run", _code(status.get("source_primary_run_id"))),
                    ("Primary-claim allowed", _code(status.get("primary_claim_allowed"))),
                    ("Forecast rows", _code(status.get("forecast_rows"))),
                    ("Metric rows", _code(status.get("metric_rows"))),
                    ("Status", _code(status.get("status"))),
                ],
            ),
            _markdown_table(("Sensitivity family", "Rows / classifications"), rows),
            (
                "- The primary design compares pre-specified point-in-time forecast "
                "specifications. Configuration sensitivity is appendix robustness "
                "evidence and is not used to select primary selections.\n"
                "- LGBM rows vary only capacity settings; EWMA reports the primary "
                "lambda 0.94 plus 0.90 and 0.97; POT threshold rows use forecastable "
                "0.90/0.925 settings and mark 0.95 as a boundary diagnostic at the "
                "95% VaR level.\n"
                "- Robustness classes describe conclusion stability versus the "
                "registered primary specification. They do not feed DM/MCS gates, "
                "promoted-model logic, or selected-model figures."
            ),
        )
    )


def _sensitivity_metric_summary(path: Path) -> str:
    frame = _read_parquet_optional(path)
    if frame.is_empty():
        return "not generated"
    if "robustness_classification" not in frame.columns:
        return f"{frame.height} rows"
    grouped = (
        frame.group_by("robustness_classification")
        .agg(pl.len().alias("rows"))
        .sort("robustness_classification")
    )
    parts = [
        f"{row['robustness_classification']}={row['rows']}" for row in grouped.iter_rows(named=True)
    ]
    return f"{frame.height} rows ({', '.join(parts)})"


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
            display_source_block_label(row["source_family"]),
            display_source_block_label(row["source_block"]),
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
            display_model_label(row["model_name"]),
            display_information_set_label(row["information_set"]),
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


def _promoted_tail_model_markdown_table(
    metrics: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
    mcs: pl.DataFrame | None = None,
) -> str:
    rows = []
    for row in _promoted_tail_model_rows(metrics, dm=dm, mcs=mcs):
        rows.append(
            (
                row.get("promotion_role"),
                display_model_label(row.get("model_name")),
                display_information_set_label(row.get("information_set")),
                row.get("tail_side"),
                row.get("rows") or "missing",
                _fmt_rate(row.get("var_breach_rate")),
                _fmt_float(row.get("mean_quantile_loss")),
                _fmt_float(row.get("mean_fz_loss")),
                _snapshot_dm_cell(row.get("dm_quantile")),
                _snapshot_dm_cell(row.get("dm_fz")),
                _snapshot_mcs_pair_cell(row.get("mcs_quantile"), row.get("mcs_fz")),
                row.get("promotion_status"),
            )
        )
    return _markdown_table(
        (
            "Role",
            "Model",
            "Information set",
            "Tail side",
            "Rows",
            "Breach",
            "Q loss",
            "FZ loss",
            "DM q",
            "DM FZ",
            "MCS q/FZ",
            "Gate",
        ),
        rows or [("missing", "missing", "", "", "", "", "", "", "", "", "", "")],
    )


def _snapshot_dm_cell(row: object) -> str:
    if not isinstance(row, dict):
        return "n/a"
    diff = _optional_float(row.get("mean_loss_diff_candidate_minus_baseline"))
    pvalue = _optional_float(row.get("pvalue_one_sided"))
    reject = row.get("reject_10pct")
    if diff is None or pvalue is None:
        return str(row.get("inference_status") or "n/a")
    reject_text = "reject10" if reject is True else "no reject"
    return f"{_fmt_float(diff)}; p={_fmt_float(pvalue)}; {reject_text}"


def _snapshot_mcs_pair_cell(q_row: object, fz_row: object) -> str:
    return f"{_snapshot_mcs_cell(q_row)} / {_snapshot_mcs_cell(fz_row)}"


def _snapshot_mcs_cell(row: object) -> str:
    if not isinstance(row, dict):
        return "n/a"
    status = str(row.get("mcs_status") or "n/a")
    if row.get("included_in_mcs") is True:
        return "in"
    if row.get("included_in_mcs") is False and status == "ok":
        return "out"
    return status


def _benchmark_layer_table(status: dict[str, object]) -> str:
    advanced_rows = int(_optional_float(status.get("benchmark_advanced_forecast_rows")) or 0)
    advanced_note = (
        "Implemented nonblocking advanced econometric benchmark forecasts; review with common-sample gates."
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
                "baseline",
                _code(status.get("benchmark_baseline_status") or status.get("status") or "unknown"),
                _code(
                    status.get("benchmark_baseline_forecast_rows") or status.get("forecast_rows")
                ),
                _code(status.get("benchmark_baseline_metric_rows") or status.get("metric_rows")),
                _code(status.get("benchmark_baseline_failures") or 0),
                "Implemented evidence for target-history and econometric baseline benchmark models.",
            ),
            (
                "advanced econometric",
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


def _claim_scope_markdown_table() -> str:
    return _markdown_table(
        ("Evidence layer", "Can support primary claim?", "How to read it"),
        [
            (
                "Benchmark common-sample table",
                "Yes, after review",
                "External target-history/econometric baseline benchmark on a shared sample.",
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
                "No primary claim",
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
                "Primary ML nested-information-set comparison",
                "Eligible for primary discussion after author review.",
            ),
            (
                "`ml_tail_metrics_per_model.parquet`",
                str(ml_tail_metrics_per_model.height),
                "Per-model diagnostics on each model's own valid OOS rows",
                "Not a cross-model comparison and not a replacement primary ML table.",
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
            f"Coverage review: `{flagged}/{len(rows)}` primary ML rows differ from the "
            "expected breach rate by more than 2.5 percentage points, so quantile/FZ loss "
            "differences alone must not be read as forecast improvement."
        )
    return (
        "Coverage review: primary ML breach rates are within the 2.5 percentage-point "
        "snapshot review band, but final claims still require author review of inference "
        "and exception diagnostics."
    )


def _artifact_table(paths: dict[str, Path]) -> str:
    rows = [
        (name, f"`{path}`", "yes" if path.exists() else "missing") for name, path in paths.items()
    ]
    return _markdown_table(("Artifact", "Path", "Exists"), rows)
