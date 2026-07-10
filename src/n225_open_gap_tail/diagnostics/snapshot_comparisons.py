from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import polars as pl

from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.config.runtime import _optional_float
from n225_open_gap_tail.diagnostics.snapshot_formatting import _markdown_table
from n225_open_gap_tail.metrics.admissibility import (
    coverage_admissibility_summary_rows as coverage_admissibility_rows,
)
from n225_open_gap_tail.metrics.cross_suite_dm import cross_suite_dm_records_from_run

_DISPLAYED_DM_PAIRS = (
    ("LGBM plain MLE C", "GJR-GARCH-EVT"),
    ("LGBM UniBM C", "GJR-GARCH-EVT"),
    ("LGBM plain MLE C", "LGBM UniBM C"),
)


def coverage_admissibility_markdown(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "24-check evidence is unavailable because the required per-model metrics are absent."
    table = _markdown_table(
        (
            "LGBM family",
            "Eligible / 8",
            "Breach band / 8",
            "Kupiec UC / 8",
            "Christoffersen independence / 8",
            "Coverage-admissible",
        ),
        [
            (
                display_model_label(row.get("model_name")),
                f"{row.get('eligible_scenarios', 0)}/8",
                f"{row.get('breach_passes', 0)}/8",
                f"{row.get('kupiec_passes', 0)}/8",
                f"{row.get('christoffersen_independence_passes', 0)}/8",
                "yes" if row.get("coverage_admissible") else "no",
            )
            for row in rows
        ],
    )
    note = (
        "The 24-check screen is 2 tail sides x 4 information sets x 3 calibration checks: "
        "the +/-2.5 percentage-point breach-rate band, Kupiec unconditional coverage, and "
        "Christoffersen independence. N >= 450 is an eligibility precondition, "
        "not a twenty-fifth check."
    )
    return f"{table}\n\n{note}"


def cross_suite_dm_markdown(records: Sequence[Mapping[str, object]]) -> str:
    selected = [
        row
        for tail_side in ("left_tail", "right_tail")
        for candidate, anchor in _DISPLAYED_DM_PAIRS
        for row in records
        if row.get("tail_side") == tail_side
        and row.get("candidate_label") == candidate
        and row.get("anchor_label") == anchor
    ]
    if not selected:
        return (
            "Cross-suite FZ DM evidence is unavailable because the three-model "
            "common sample could not be formed."
        )
    table = _markdown_table(
        ("Tail", "Candidate", "Anchor", "Common N", "Mean FZ diff.", "One-sided p", "Status"),
        [
            (
                str(row.get("tail_side") or "").replace("_", " "),
                row.get("candidate_label"),
                row.get("anchor_label"),
                row.get("common_n"),
                _format_float(row.get("mean_fz_loss_diff_candidate_minus_anchor"), digits=6),
                _format_float(row.get("pvalue_one_sided"), digits=3),
                row.get("inference_status"),
            )
            for row in selected
        ],
    )
    note = (
        "Mean differences are FZ(candidate - anchor) on one strict global common sample per "
        "tail. Negative values mean that the candidate has lower FZ loss and better joint "
        "VaR-ES forecasts. P-values are one-sided moving-block-bootstrap DM p-values."
    )
    return f"{table}\n\n{note}"


def comparison_evidence_markdown(*, metrics: pl.DataFrame, run_dir: Path) -> str:
    coverage = coverage_admissibility_markdown(coverage_admissibility_rows(metrics))
    dm = cross_suite_dm_markdown(cross_suite_dm_records_from_run(run_dir))
    return f"""### 4.5 Coverage-admissibility screen and cross-suite FZ DM evidence

{coverage}

The loss comparison below is deliberately conditional on the 24-check screen.
It compares the fixed coverage-admissible set rather than ranking every
implemented model.

{dm}
"""


def _format_float(value: object, *, digits: int) -> str:
    parsed = _optional_float(value)
    return "n/a" if parsed is None else f"{parsed:.{digits}f}"
