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
from n225_open_gap_tail.metrics.cross_suite_dm import (
    LGBM_STANDARD_PLAIN_MLE_C_LABEL,
    LGBM_STANDARD_UNIBM_C_LABEL,
    cross_suite_dm_records_from_run,
)

_DISPLAYED_DM_PAIRS = (
    (LGBM_STANDARD_PLAIN_MLE_C_LABEL, "GJR-GARCH-EVT"),
    (LGBM_STANDARD_UNIBM_C_LABEL, "GJR-GARCH-EVT"),
    (LGBM_STANDARD_PLAIN_MLE_C_LABEL, LGBM_STANDARD_UNIBM_C_LABEL),
)


def coverage_admissibility_markdown(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return (
            "Coverage-screen evidence is unavailable because the required per-model "
            "metrics are absent."
        )
    table = _markdown_table(
        (
            "LightGBM specification",
            "Eligible / 8",
            "Breach band / 8",
            "Kupiec UC / 8",
            "Christoffersen independence / 8",
            "Mean exception severity range",
            "Coverage-admissible",
        ),
        [
            (
                display_model_label(row.get("model_name")),
                f"{row.get('eligible_scenarios', 0)}/8",
                f"{row.get('breach_passes', 0)}/8",
                f"{row.get('kupiec_passes', 0)}/8",
                f"{row.get('christoffersen_independence_passes', 0)}/8",
                _severity_range(row),
                "yes" if row.get("coverage_admissible") else "no",
            )
            for row in rows
        ],
    )
    note = (
        "The eight-scenario VaR coverage screen spans two exposures and four information sets. "
        "Each scenario applies three criteria: "
        "the +/-2.5 percentage-point breach-rate band, Kupiec unconditional coverage, and "
        "Christoffersen independence. N >= 450 is an eligibility precondition, "
        "not an additional test. The severity range is descriptive and does not enter "
        "the screen."
    )
    return f"{table}\n\n{note}"


def _severity_range(row: Mapping[str, object]) -> str:
    lower = _optional_float(row.get("mean_exceedance_severity_min"))
    upper = _optional_float(row.get("mean_exceedance_severity_max"))
    if lower is None or upper is None:
        return "n/a"
    return f"{lower:.6f}--{upper:.6f}"


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
            "Post-screen FZ DM evidence is unavailable because the three-model "
            "common sample could not be formed."
        )
    table = _markdown_table(
        ("Tail", "Candidate", "Anchor", "Common N", "Mean FZ diff.", "One-sided p", "Status"),
        [
            (
                {"left_tail": "Downside", "right_tail": "Upside"}.get(
                    str(row.get("tail_side") or ""),
                    str(row.get("tail_side") or "").replace("_", " "),
                ),
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
        "exposure. Negative values mean that the candidate has lower FZ loss and better joint "
        "VaR-ES forecasts. P-values are one-sided circular-block-bootstrap DM p-values."
    )
    return f"{table}\n\n{note}"


def comparison_evidence_markdown(*, metrics: pl.DataFrame, run_dir: Path) -> str:
    coverage = coverage_admissibility_markdown(coverage_admissibility_rows(metrics))
    dm = cross_suite_dm_markdown(cross_suite_dm_records_from_run(run_dir))
    return f"""### 4.5 Eight-scenario VaR coverage screen and post-screen FZ DM evidence

{coverage}

The loss comparison below is deliberately conditional on the eight-scenario VaR coverage screen.
It compares the fixed coverage-admissible set rather than ranking every
implemented model.

{dm}
"""


def _format_float(value: object, *, digits: int) -> str:
    parsed = _optional_float(value)
    return "n/a" if parsed is None else f"{parsed:.{digits}f}"
