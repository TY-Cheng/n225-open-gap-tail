# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path

import polars as pl

from n225_open_gap_tail.diagnostics.snapshot_formatting import (
    _code,
    _markdown_table,
    _optional_float,
    _result_matrix_display_value,
)


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
