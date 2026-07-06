from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import polars as pl


def _with_leakage_warning_counts(
    run_dir: Path,
    leakage_summary: dict[str, object],
) -> dict[str, object]:
    if isinstance(leakage_summary.get("warning_reason_counts"), Mapping):
        return leakage_summary
    leakage = _read_parquet_optional(run_dir / "audits" / "leakage_check.parquet")
    if leakage.is_empty() or not {"status", "reason"}.issubset(leakage.columns):
        return leakage_summary
    return {
        **leakage_summary,
        "status_counts": _series_counts(leakage, "status"),
        "warning_reason_counts": _series_counts(
            leakage.filter(pl.col("status") == "warn"),
            "reason",
        ),
    }


def _format_count_mapping(value: object) -> str:
    if not isinstance(value, Mapping) or not value:
        return "not available"
    pairs = sorted(value.items(), key=lambda item: int(item[1]), reverse=True)
    return "<br>".join(f"`{key}`: `{count}`" for key, count in pairs)


def _read_parquet_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _series_counts(frame: pl.DataFrame, column: str) -> dict[str, int]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    counts = frame.group_by(column).len().sort("len", descending=True)
    return {str(row[column] or "missing"): int(row["len"]) for row in counts.iter_rows(named=True)}
