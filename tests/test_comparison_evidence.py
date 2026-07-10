from __future__ import annotations

import polars as pl

from n225_open_gap_tail.diagnostics.snapshot_comparisons import (
    coverage_admissibility_markdown,
    cross_suite_dm_markdown,
)
from n225_open_gap_tail.metrics.admissibility import (
    coverage_admissibility_summary_rows as coverage_admissibility_rows,
)
from n225_open_gap_tail.metrics.cross_suite_dm import cross_suite_dm_records


def test_coverage_admissibility_counts_all_three_checks_across_eight_scenarios() -> None:
    rows: list[dict[str, object]] = []
    information_sets = ("A", "B", "C", "D")
    for model_name in ("pass_model", "kupiec_failure"):
        for tail_side in ("left_tail", "right_tail"):
            for information_set in information_sets:
                rows.append(
                    {
                        "model_name": model_name,
                        "tail_side": tail_side,
                        "information_set": information_set,
                        "rows": 500,
                        "var_breach_rate": 0.05,
                        "expected_breach_rate": 0.05,
                        "kupiec_pvalue": (
                            0.01
                            if model_name == "kupiec_failure"
                            and tail_side == "right_tail"
                            and information_set == "D"
                            else 0.50
                        ),
                        "christoffersen_pvalue": 0.40,
                    }
                )

    summary = coverage_admissibility_rows(
        pl.DataFrame(rows),
        model_order=("pass_model", "kupiec_failure"),
        information_sets=information_sets,
    )

    assert summary == [
        {
            "model_name": "pass_model",
            "eligible_scenarios": 8,
            "breach_passes": 8,
            "kupiec_passes": 8,
            "christoffersen_independence_passes": 8,
            "coverage_admissible": True,
        },
        {
            "model_name": "kupiec_failure",
            "eligible_scenarios": 8,
            "breach_passes": 8,
            "kupiec_passes": 7,
            "christoffersen_independence_passes": 8,
            "coverage_admissible": False,
        },
    ]
    rendered = coverage_admissibility_markdown(summary)
    assert "24-check" in rendered
    assert "Christoffersen independence" in rendered
    assert "Christoffersen conditional coverage" not in rendered
    assert "8/8" in rendered


def test_cross_suite_dm_uses_one_global_common_sample_and_formats_exact_evidence() -> None:
    loss_rows: list[dict[str, object]] = []
    labels = ("GJR-GARCH-EVT", "LGBM plain MLE C", "LGBM UniBM C")
    for label_index, label in enumerate(labels):
        dates = range(1, 6) if label != "LGBM UniBM C" else range(2, 6)
        for day in dates:
            loss_rows.append(
                {
                    "plot_label": label,
                    "forecast_date": f"2026-01-{day:02d}",
                    "tail_side": "left_tail",
                    "realized_loss": 0.02,
                    "var_forecast": 0.01,
                    "fz_loss": -3.0 - label_index * 0.1 - day * 0.001,
                }
            )

    records = cross_suite_dm_records(pl.DataFrame(loss_rows), "left_tail")

    assert len(records) == 6
    assert {record["common_n"] for record in records} == {4}
    assert {record["paired_rows"] for record in records} == {4}
    rendered = cross_suite_dm_markdown(records)
    assert "Candidate" in rendered
    assert "Anchor" in rendered
    assert "Common N" in rendered
    assert "candidate - anchor" in rendered
    assert "lower FZ loss" in rendered
