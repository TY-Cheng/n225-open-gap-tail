"""Exploratory joint-date score inference on frozen forecast panels.

Calendar blocks carry the common observation mask with them. Each replicate
averages only selected eligible observations (a ratio), rather than interpreting
unavailable dates as zero losses. This does not establish a missingness or
stationarity assumption; all inference is conditional, approximate/exploratory.
"""

from __future__ import annotations

from itertools import combinations
from typing import cast

import numpy as np
from arch.bootstrap import CircularBlockBootstrap
from numpy.typing import NDArray

type FloatArray = NDArray[np.float64]
type Row = dict[str, object]


def _joint_mean_draws(
    scores: FloatArray, session_indices: list[int], block_length: int, reps: int, seed: int
) -> FloatArray:
    if len(scores) < 120 or scores.shape[1] < 2:
        return np.empty((0, scores.shape[1]), dtype=np.float64)
    offsets = np.asarray(session_indices, dtype=np.int64) - session_indices[0]
    calendar_to_row = np.full(int(offsets[-1]) + 1, -1, dtype=np.int64)
    calendar_to_row[offsets] = np.arange(len(scores))
    bootstrap = CircularBlockBootstrap(block_length, np.arange(len(calendar_to_row)), seed=seed)
    draws: list[FloatArray] = []
    for data, _ in bootstrap.bootstrap(reps):
        selected = calendar_to_row[np.asarray(data[0], dtype=np.int64)]
        available = selected[selected >= 0]
        if available.size:
            draws.append(np.asarray(scores[available].mean(axis=0), dtype=np.float64))
    return np.asarray(draws, dtype=np.float64).reshape(-1, scores.shape[1])


def _mcs_rows(
    scores: FloatArray,
    draws: FloatArray,
    model_names: list[str],
    metadata: Row,
    pairwise_rows: list[Row],
) -> list[Row]:
    """Hansen--Lunde--Nason T_R elimination, using arch's finite-B convention.

    Only the resampled means differ from ``arch.bootstrap.MCS``: they retain
    native-calendar holes. Step p-values use strict empirical exceedances,
    then a cumulative maximum in elimination order, as in arch's R method.
    """
    unavailable = (
        "unavailable_single_candidate"
        if len(model_names) < 2
        else "unavailable_pairwise_requirements"
        if any(row["status"] != "ok" for row in pairwise_rows)
        else None
    )
    if unavailable:
        return [
            {
                **metadata,
                "model_name": name,
                "model_index": index,
                "status": unavailable,
                "p_value_step": None,
                "p_value_mcs": None,
                "survives_95": None,
                "elimination_order": None,
                "statistic_at_elimination": None,
                "method": "T_R",
                "confidence_level": 0.95,
                "p_value_convention": "strict_empirical_arch_R",
            }
            for index, name in enumerate(model_names)
        ]
    # Collapse identical columns only for arithmetic; every original identity
    # is restored below with the same group survival and elimination record.
    representatives: list[int] = []
    groups: list[int] = []
    for index in range(len(model_names)):
        matching = next(
            (
                group
                for group, representative in enumerate(representatives)
                if np.array_equal(scores[:, index], scores[:, representative])
            ),
            None,
        )
        if matching is None:
            matching = len(representatives)
            representatives.append(index)
        groups.append(matching)
    means = scores[:, representatives].mean(axis=0)
    draws = draws[:, representatives]
    differences = means[:, None] - means[None, :]
    centered = draws[:, :, None] - draws[:, None, :] - differences
    variance = np.mean(centered**2, axis=0) + np.eye(len(representatives))
    standard = np.sqrt(variance)
    observed = differences / standard
    simulated = centered / standard
    active = list(range(len(representatives)))
    records: dict[int, Row] = {}
    previous_p = 0.0
    while len(active) > 1:
        observed_subset = observed[np.ix_(active, active)]
        statistic = float(np.max(observed_subset))
        simulated_statistics = simulated[:, active, :][:, :, active].max(axis=(1, 2))
        p_value = float(np.mean(simulated_statistics > statistic))
        previous_p = max(previous_p, p_value)
        worst_local = int(np.unravel_index(np.argmax(observed_subset), observed_subset.shape)[0])
        worst = active.pop(worst_local)
        records[worst] = {
            "p_value_step": p_value,
            "p_value_mcs": previous_p,
            "survives_95": previous_p > 0.05,
            "elimination_order": len(records) + 1,
            "statistic_at_elimination": statistic,
        }
    records[active[0]] = {
        "p_value_step": 1.0,
        "p_value_mcs": 1.0,
        "survives_95": True,
        "elimination_order": None,
        "statistic_at_elimination": None,
    }
    return [
        {
            **metadata,
            "model_name": name,
            "model_index": index,
            "status": "ok",
            "method": "T_R",
            "confidence_level": 0.95,
            "p_value_convention": "strict_empirical_arch_R",
            "tied_model_names": [
                other_name
                for other_index, other_name in enumerate(model_names)
                if groups[other_index] == groups[index]
            ],
            **records[groups[index]],
        }
        for index, name in enumerate(model_names)
    ]


def build_score_inference(
    scores: FloatArray,
    *,
    model_names: list[str],
    session_indices: list[int],
    exception_flags: NDArray[np.bool_],
    score_name: str,
    reps: int = 9999,
    seed: int = 225,
    pairs: list[tuple[int, int]] | None = None,
) -> dict[str, list[Row]]:
    """Compare date-level, equally aggregated scores on one fixed joint panel.

    Negative ``mean_difference`` favors ``model_i``. Paired confidence intervals
    are pointwise basic intervals, not simultaneous multiplicity-adjusted ones.
    ``exception_flags`` is the per-date any-scenario breach indicator per model.
    Explicit oriented ``pairs`` define one Holm family and disable MCS; omitted
    pairs preserve the original all-pairs/global-MCS comparison.
    """
    scores = np.asarray(scores, dtype=np.float64)
    if scores.ndim != 2 or not np.all(np.isfinite(scores)):
        raise ValueError("scores must be a finite N-by-K joint panel")
    n, k = scores.shape
    if len(model_names) != k or len(set(model_names)) != k:
        raise ValueError("model_names must uniquely identify every score column")
    if exception_flags.shape != scores.shape or exception_flags.dtype != np.bool_:
        raise ValueError("exception_flags must be an N-by-K boolean array")
    if len(session_indices) != n or any(
        not isinstance(index, (int, np.integer)) or isinstance(index, bool)
        for index in session_indices
    ):
        raise ValueError("session_indices must contain one integer per joint date")
    if any(
        right <= left for left, right in zip(session_indices[:-1], session_indices[1:], strict=True)
    ):
        raise ValueError("session_indices must be strictly increasing")
    if not isinstance(reps, (int, np.integer)) or isinstance(reps, bool) or reps < 1:
        raise ValueError("reps must be a positive integer")
    selected_pairs = list(combinations(range(k), 2)) if pairs is None else pairs
    if any(i == j or not (0 <= i < k and 0 <= j < k) for i, j in selected_pairs) or len(
        {frozenset(pair) for pair in selected_pairs}
    ) != len(selected_pairs):
        raise ValueError("pairs must be distinct non-self score-column comparisons")
    base = max(5, round(n ** (1 / 3)))
    output: dict[str, list[Row]] = {"pairwise": [], "mcs": []}
    if not k:
        return output
    for block_length in dict.fromkeys((base, max(5, round(base / 2)), 2 * base)):
        draws = _joint_mean_draws(scores, session_indices, block_length, reps, seed)
        metadata: Row = {
            "score_name": score_name,
            "block_length": block_length,
            "configuration": "main" if block_length == base else "sensitivity",
            "n_common": n,
            "calendar_span": session_indices[-1] - session_indices[0] + 1 if n else 0,
            "reps_requested": reps,
            "reps_usable": len(draws),
            "seed": seed,
            "scope": "approximate_exploratory_conditional_on_screened_common_panel",
        }
        block_rows: list[Row] = []
        for i, j in selected_pairs:
            difference_series = scores[:, i] - scores[:, j]
            difference = float(np.mean(difference_series)) if n else None
            observational_tie = bool(np.array_equal(scores[:, i], scores[:, j]))
            n_events = int(np.count_nonzero(exception_flags[:, i] | exception_flags[:, j]))
            row: Row = {
                **metadata,
                "model_i": model_names[i],
                "model_j": model_names[j],
                "mean_difference": difference,
                "n_exception_dates": n_events,
                "observational_tie": observational_tie,
                "p_value_raw": None,
                "p_value_holm": None,
                "reject_holm_05": None,
                "ci_lower": None,
                "ci_upper": None,
                "confidence_level": 0.95,
                "ci_kind": "pointwise_basic",
                "status": "ok",
            }
            if n < 120:
                row["status"] = "unavailable_insufficient_common_rows"
            elif n_events < 5:
                row["status"] = "unavailable_insufficient_exception_dates"
            elif not len(draws):
                row["status"] = "unavailable_empty_bootstrap_mask"
            elif not observational_tie and np.all(difference_series == difference_series[0]):
                row["status"] = "unavailable_nonzero_constant_difference"
            if row["status"] != "ok":
                block_rows.append(row)
                continue
            assert difference is not None
            boot_difference = draws[:, i] - draws[:, j]
            if not observational_tie and np.mean((boot_difference - difference) ** 2) <= 0:
                row["status"] = "unavailable_degenerate_bootstrap_variance"
                block_rows.append(row)
                continue
            p_value = float(
                (1 + np.count_nonzero(np.abs(boot_difference - difference) >= abs(difference)))
                / (len(draws) + 1)
            )
            lower, upper = np.quantile(boot_difference, [0.025, 0.975])
            row.update(
                {
                    "p_value_raw": p_value,
                    "p_value_holm": p_value,
                    "ci_lower": float(2 * difference - upper),
                    "ci_upper": float(2 * difference - lower),
                }
            )
            block_rows.append(row)
        ordered = sorted(
            (row for row in block_rows if row["p_value_raw"] is not None),
            key=lambda row: cast(float, row["p_value_raw"]),
        )
        previous = 0.0
        for rank, row in enumerate(ordered):
            previous = min(
                1.0, max(previous, (len(block_rows) - rank) * cast(float, row["p_value_raw"]))
            )
            row["p_value_holm"] = previous
            row["reject_holm_05"] = previous <= 0.05
        output["pairwise"].extend(block_rows)
        if score_name == "fzg" and pairs is None:
            output["mcs"].extend(_mcs_rows(scores, draws, model_names, metadata, block_rows))
    return output
