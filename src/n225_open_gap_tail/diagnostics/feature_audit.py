from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from n225_open_gap_tail.config.runtime import PipelineRunError
from n225_open_gap_tail.data_lake import write_json_atomic


@dataclass(frozen=True)
class FeatureAuditResult:
    run_id: str
    run_dir: Path
    output_path: Path
    feature_count: int
    block_count: int
    warning_count: int


def write_feature_audit(
    *,
    run_dir: Path,
    baseline_run_dir: Path | None = None,
) -> FeatureAuditResult:
    """Write a compact feature audit from completed run artifacts."""
    coverage_path = run_dir / "panel" / "feature_coverage.parquet"
    if not coverage_path.exists():
        raise PipelineRunError(f"Missing feature coverage artifact: {coverage_path}")
    coverage = pl.read_parquet(coverage_path)
    if coverage.is_empty():
        block_summary: list[dict[str, object]] = []
    else:
        block_summary = (
            coverage.group_by("source_block")
            .agg(
                pl.len().alias("feature_count"),
                pl.median("missingness_rate").alias("median_missingness_rate"),
                pl.max("missingness_rate").alias("max_missingness_rate"),
                pl.sum("non_missing_rows").alias("non_missing_rows_total"),
            )
            .sort("source_block")
            .to_dicts()
        )
    diagnostics_summary = _ml_tail_gate_summary(run_dir)
    delta_summary, warnings = _feature_delta_summary(run_dir, coverage, baseline_run_dir)
    payload = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "feature_count": coverage.height,
        "block_summary": block_summary,
        "ml_tail_gate_summary": diagnostics_summary,
        "feature_delta_summary": delta_summary,
        "warnings": warnings,
    }
    output_path = run_dir / "audits" / "feature_audit.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, payload)
    return FeatureAuditResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        output_path=output_path,
        feature_count=coverage.height,
        block_count=len(block_summary),
        warning_count=len(warnings),
    )


def _ml_tail_gate_summary(run_dir: Path) -> dict[str, object]:
    diagnostics_path = run_dir / "forecasts" / "ml_tail_fit_diagnostics.parquet"
    if not diagnostics_path.exists():
        return {
            "available": False,
            "reason": f"missing artifact: {diagnostics_path}",
            "candidate_hashes": [],
            "dropped_feature_count": 0,
            "dropped_features_by_reason": [],
        }
    diagnostics = pl.read_parquet(diagnostics_path)
    if diagnostics.is_empty():
        return {
            "available": True,
            "candidate_hashes": [],
            "dropped_feature_count": 0,
            "dropped_features_by_reason": [],
        }
    candidate_hashes = (
        diagnostics.select(["information_set", "candidate_feature_hash", "active_feature_hash"])
        .unique()
        .sort(["information_set", "candidate_feature_hash"])
        .to_dicts()
    )
    dropped_rows: list[dict[str, object]] = []
    if "dropped_features_json" in diagnostics.columns:
        for raw in diagnostics.get_column("dropped_features_json").unique().to_list():
            dropped_rows.extend(_parse_dropped_features(raw))
    dropped_by_reason: dict[str, set[str]] = {}
    for row in dropped_rows:
        feature = str(row.get("feature") or "")
        reason = str(row.get("drop_reason") or "unknown")
        if feature:
            dropped_by_reason.setdefault(reason, set()).add(feature)
    return {
        "available": True,
        "candidate_hashes": candidate_hashes,
        "dropped_feature_count": len({str(row.get("feature")) for row in dropped_rows}),
        "dropped_features_by_reason": [
            {
                "drop_reason": reason,
                "feature_count": len(features),
                "features": sorted(features),
            }
            for reason, features in sorted(dropped_by_reason.items())
        ],
    }


def _feature_delta_summary(
    run_dir: Path,
    coverage: pl.DataFrame,
    baseline_run_dir: Path | None,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    if baseline_run_dir is None:
        return {"available": False, "reason": "baseline_run_id_not_provided"}, warnings
    baseline_coverage_path = baseline_run_dir / "panel" / "feature_coverage.parquet"
    if not baseline_coverage_path.exists():
        warnings.append(f"missing baseline feature coverage: {baseline_coverage_path}")
        return {"available": False, "reason": "missing_baseline_feature_coverage"}, warnings
    baseline_coverage = pl.read_parquet(baseline_coverage_path)
    current_features = (
        set(coverage.get_column("feature").to_list()) if "feature" in coverage else set()
    )
    baseline_features = (
        set(baseline_coverage.get_column("feature").to_list())
        if "feature" in baseline_coverage
        else set()
    )
    current_window = _run_window(run_dir)
    baseline_window = _run_window(baseline_run_dir)
    if current_window != baseline_window:
        warnings.append(
            f"date range mismatch: current={current_window or '<unknown>'} "
            f"baseline={baseline_window or '<unknown>'}"
        )
    return (
        {
            "available": True,
            "baseline_run_id": baseline_run_dir.name,
            "added_features": sorted(current_features.difference(baseline_features)),
            "removed_features": sorted(baseline_features.difference(current_features)),
            "current_feature_count": len(current_features),
            "baseline_feature_count": len(baseline_features),
        },
        warnings,
    )


def _parse_dropped_features(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _run_window(run_dir: Path) -> tuple[object, object] | None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    window = manifest.get("window")
    if not isinstance(window, list) or len(window) != 2:
        return None
    return (window[0], window[1])
