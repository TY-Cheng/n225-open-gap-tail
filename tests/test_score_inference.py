from __future__ import annotations

import numpy as np
import pytest
from arch.bootstrap import MCS, CircularBlockBootstrap
from statsmodels.stats.multitest import multipletests  # type: ignore[import-untyped]

from n225_open_gap_tail.metrics.score_inference import build_score_inference


def test_paired_ql_uses_centered_two_sided_tests_and_basic_intervals() -> None:
    scores = np.random.default_rng(7).normal(size=(216, 2))
    scores[:, 0] -= 0.15
    flags = np.zeros_like(scores, dtype=bool)
    flags[:5, 0] = True
    result = build_score_inference(
        scores,
        model_names=["first", "second"],
        session_indices=list(range(216)),
        exception_flags=flags,
        score_name="quantile_loss",
        reps=199,
    )
    assert result["mcs"] == []
    assert {row["block_length"] for row in result["pairwise"]} == {5, 6, 12}
    observed = float(np.mean(scores[:, 0] - scores[:, 1]))
    for row in result["pairwise"]:
        assert row["model_i"] == "first"
        assert row["model_j"] == "second"
        assert row["mean_difference"] == pytest.approx(observed)
        assert row["status"] == "ok"
        assert row["reps_usable"] == 199
        assert row["n_exception_dates"] == 5
        bootstrap = CircularBlockBootstrap(int(str(row["block_length"])), scores, seed=225)
        means = np.array(
            [np.mean(data[0][0][:, 0] - data[0][0][:, 1]) for data in bootstrap.bootstrap(199)]
        )
        expected_p = (1 + np.count_nonzero(np.abs(means - observed) >= abs(observed))) / 200
        assert row["p_value_raw"] == expected_p
        assert row["p_value_holm"] == expected_p
        assert row["ci_lower"] == pytest.approx(2 * observed - np.quantile(means, 0.975))
        assert row["ci_upper"] == pytest.approx(2 * observed - np.quantile(means, 0.025))


def test_selected_oriented_pairs_share_draws_and_only_the_requested_holm_family() -> None:
    scores = np.random.default_rng(82).normal(size=(216, 9))
    scores += np.linspace(0, 0.5, 9)
    pairs = [(0, 8), (1, 0), (2, 1), (3, 2), (4, 8), (5, 4), (6, 5), (7, 6)]
    names = list("abcdefghi")
    sessions = [i + 1000 for i in range(240) if i % 10 != 4]
    result = build_score_inference(
        scores,
        model_names=names,
        session_indices=sessions,
        exception_flags=np.ones_like(scores, dtype=bool),
        score_name="fzg",
        reps=199,
        pairs=pairs,
    )
    assert result["mcs"] == []
    assert len(result["pairwise"]) == 24
    native_scores = np.full((240, 9), np.nan)
    native_scores[np.array(sessions) - 1000] = scores
    for length in (5, 6, 12):
        rows = [row for row in result["pairwise"] if row["block_length"] == length]
        bootstrap = CircularBlockBootstrap(length, native_scores, seed=225)
        means = np.array([np.nanmean(data[0][0], axis=0) for data in bootstrap.bootstrap(199)])
        raw = []
        for row, (i, j) in zip(rows, pairs, strict=True):
            observed = (scores[:, i] - scores[:, j]).mean()
            boot = means[:, i] - means[:, j]
            p = (1 + np.count_nonzero(np.abs(boot - observed) >= abs(observed))) / 200
            raw.append(p)
            assert (row["model_i"], row["model_j"]) == (names[i], names[j])
            assert row["mean_difference"] == pytest.approx(observed)
            assert row["p_value_raw"] == p
            assert row["ci_lower"] == pytest.approx(2 * observed - np.quantile(boot, 0.975))
        assert [row["p_value_holm"] for row in rows] == pytest.approx(
            multipletests(raw, method="holm")[1]
        )


@pytest.mark.parametrize("pairs", [[(0, 0)], [(0, 2)], [(0, 1), (1, 0)]])
def test_invalid_requested_pairs_fail(pairs: list[tuple[int, int]]) -> None:
    with pytest.raises(ValueError, match="pairs"):
        build_score_inference(
            np.ones((120, 2)),
            model_names=["a", "b"],
            session_indices=list(range(120)),
            exception_flags=np.ones((120, 2), dtype=bool),
            score_name="fzg",
            pairs=pairs,
        )


def test_joint_calendar_mask_is_preserved_and_holm_is_within_each_block() -> None:
    scores = np.random.default_rng(11).normal(size=(216, 3))
    scores[:, 0] -= 0.14
    scores[:, 2] += 0.05
    sessions = [i + 1000 for i in range(240) if i % 10 != 4]
    flags = np.zeros_like(scores, dtype=bool)
    flags[:5] = True
    result = build_score_inference(
        scores,
        model_names=["a", "b", "c"],
        session_indices=sessions,
        exception_flags=flags,
        score_name="quantile_loss",
        reps=199,
    )
    native_scores = np.full((240, 3), np.nan)
    native_scores[np.asarray(sessions) - 1000] = scores
    for length in (5, 6, 12):
        rows = [row for row in result["pairwise"] if row["block_length"] == length]
        assert len(rows) == 3
        assert all(row["calendar_span"] == 240 for row in rows)
        bootstrap = CircularBlockBootstrap(length, native_scores, seed=225)
        means = np.array([np.nanmean(data[0][0], axis=0) for data in bootstrap.bootstrap(199)])
        for row, (i, j) in zip(rows, [(0, 1), (0, 2), (1, 2)], strict=True):
            difference = float(np.mean(scores[:, i] - scores[:, j]))
            low, high = np.quantile(means[:, i] - means[:, j], [0.025, 0.975])
            assert row["ci_lower"] == pytest.approx(2 * difference - high)
            assert row["ci_upper"] == pytest.approx(2 * difference - low)
        expected_holm = multipletests([row["p_value_raw"] for row in rows], method="holm")[1]
        assert [row["p_value_holm"] for row in rows] == pytest.approx(expected_holm)


def test_fzg_mcs_matches_arch_r_with_identical_complete_series_draws() -> None:
    scores = np.random.default_rng(23).normal(size=(216, 4))
    scores += [0.0, 0.1, 0.4, 0.8]
    flags = np.zeros_like(scores, dtype=bool)
    flags[:5] = True
    names = ["alpha", "beta", "gamma", "delta"]
    result = build_score_inference(
        scores,
        model_names=names,
        session_indices=list(range(216)),
        exception_flags=flags,
        score_name="fzg",
        reps=199,
    )
    assert len(result["mcs"]) == 12
    for length in (5, 6, 12):
        expected = MCS(
            scores,
            size=0.05,
            reps=199,
            block_size=length,
            method="R",
            bootstrap="circular",
            seed=225,
        )
        expected.compute()
        rows = [row for row in result["mcs"] if row["block_length"] == length]
        assert [row["model_name"] for row in rows] == names
        for index, row in enumerate(rows):
            assert row["status"] == "ok"
            assert row["p_value_mcs"] == float(expected.pvalues.loc[index, "Pvalue"])
            assert row["survives_95"] == (index in expected.included)


@pytest.mark.parametrize(
    ("n", "events", "status"),
    [
        (119, 5, "unavailable_insufficient_common_rows"),
        (216, 4, "unavailable_insufficient_exception_dates"),
    ],
)
def test_inference_floors_do_not_evict_roster_members(n: int, events: int, status: str) -> None:
    scores = np.random.default_rng(31).normal(size=(n, 3))
    flags = np.zeros_like(scores, dtype=bool)
    flags[:events, :2] = True
    flags[:5, 2] = True
    result = build_score_inference(
        scores,
        model_names=["a", "b", "c"],
        session_indices=list(range(n)),
        exception_flags=flags,
        score_name="fzg",
        reps=99,
    )
    first_pairs = [row for row in result["pairwise"] if row["model_j"] == "b"]
    assert all(row["status"] == status for row in first_pairs)
    assert all(row["p_value_raw"] is None and row["ci_lower"] is None for row in first_pairs)
    assert {row["model_name"] for row in result["mcs"]} == {"a", "b", "c"}
    assert all(row["status"] == "unavailable_pairwise_requirements" for row in result["mcs"])
    assert all(row["survives_95"] is None for row in result["mcs"])


@pytest.mark.parametrize("constant_difference", [0.0, 2.0])
def test_degenerate_pairs_preserve_identities_without_inventing_significance(
    constant_difference: float,
) -> None:
    baseline = np.arange(216, dtype=float) % 13
    scores = np.column_stack([baseline, baseline + constant_difference])
    flags = np.ones_like(scores, dtype=bool)
    result = build_score_inference(
        scores,
        model_names=["original_a", "original_b"],
        session_indices=list(range(216)),
        exception_flags=flags,
        score_name="fzg",
        reps=99,
    )
    assert {row["model_name"] for row in result["mcs"]} == {"original_a", "original_b"}
    if constant_difference == 0:
        assert all(row["observational_tie"] is True for row in result["pairwise"])
        assert all(row["p_value_raw"] == 1.0 for row in result["pairwise"])
        assert all(row["ci_lower"] == row["ci_upper"] == 0.0 for row in result["pairwise"])
        assert all(row["p_value_mcs"] == 1.0 for row in result["mcs"])
        assert all(row["survives_95"] is True for row in result["mcs"])
    else:
        assert all(
            row["status"] == "unavailable_nonzero_constant_difference" for row in result["pairwise"]
        )
        assert all(row["p_value_raw"] is None for row in result["pairwise"])
        assert all(row["p_value_mcs"] is None for row in result["mcs"])


def test_zero_bootstrap_variance_is_not_replaced_by_a_variance_floor() -> None:
    scores = np.column_stack([np.tile(np.arange(5, dtype=float), 24), np.zeros(120)])
    result = build_score_inference(
        scores,
        model_names=["periodic", "zero"],
        session_indices=list(range(120)),
        exception_flags=np.ones_like(scores, dtype=bool),
        score_name="fzg",
        reps=99,
    )
    assert all(
        row["status"] == "unavailable_degenerate_bootstrap_variance" for row in result["pairwise"]
    )
    assert all(row["p_value_raw"] is None for row in result["pairwise"])
    assert all(row["survives_95"] is None for row in result["mcs"])


@pytest.mark.parametrize(("n", "k"), [(0, 0), (0, 2), (216, 1)])
def test_empty_panels_and_single_candidates_never_claim_superiority(n: int, k: int) -> None:
    scores = np.zeros((n, k))
    result = build_score_inference(
        scores,
        model_names=[f"model_{i}" for i in range(k)],
        session_indices=list(range(n)),
        exception_flags=np.ones_like(scores, dtype=bool),
        score_name="fzg",
        reps=19,
    )
    if k == 0:
        assert result == {"pairwise": [], "mcs": []}
    else:
        assert {row["model_index"] for row in result["mcs"]} == set(range(k))
        assert all(row["survives_95"] is None for row in result["mcs"])
        assert all(row["p_value_raw"] is None for row in result["pairwise"])
        if k == 1:
            assert all(row["status"] == "unavailable_single_candidate" for row in result["mcs"])


@pytest.mark.parametrize("fault", ["nonfinite", "calendar_order", "calendar_length", "names"])
def test_input_contract_rejects_invalid_joint_panels(fault: str) -> None:
    scores = np.ones((120, 2))
    sessions = list(range(120))
    names = ["a", "b"]
    if fault == "nonfinite":
        scores[0, 0] = np.nan
    elif fault == "calendar_order":
        sessions[1] = 0
    elif fault == "calendar_length":
        sessions = sessions[:-1]
    else:
        names = ["a", "a"]
    with pytest.raises(ValueError):
        build_score_inference(
            scores,
            model_names=names,
            session_indices=sessions,
            exception_flags=np.ones_like(scores, dtype=bool),
            score_name="fzg",
            reps=19,
        )
