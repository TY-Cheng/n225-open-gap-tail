from __future__ import annotations

import json

import numpy as np
import pytest

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
)
from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.metrics.joint_diagnostics import (
    _murphy_group,
    build_joint_diagnostic_artifacts,
    joint_elementary_score,
    joint_identification,
)
from n225_open_gap_tail.metrics.result_matrix_grouping import _result_matrix_tail_model_groups
from n225_open_gap_tail.metrics.stat_utils import moving_block_mean_draws


def test_upper_loss_formulas_match_return_convention_and_identification() -> None:
    loss = np.array([-2.0, 0, 1.0, 2.0, 4.0])
    var = np.full(5, 1.0)
    es = np.full(5, 2.0)
    alpha = 0.05
    for eta in (-3.0, 1.0, 2.0, 5.0):
        x1, x2, y, threshold = -var, -es, -loss, -eta
        published = (threshold <= x2) * ((y <= x1) * (x1 - y) / alpha - (x1 - threshold)) + (
            threshold <= y
        ) * (y - threshold)
        actual = joint_elementary_score(loss, var, es, 0.95, eta)
        np.testing.assert_allclose(actual, published)
        assert np.all(actual >= -1e-14)
        np.testing.assert_allclose(joint_elementary_score(var, var, var, 0.95, eta), 0)
    v1, v2 = joint_identification(loss, var, es, 0.95)
    np.testing.assert_allclose(v1, (loss > var) - alpha)
    np.testing.assert_allclose(v2, es - var - (loss > var) * (loss - var) / alpha)
    # Exact midpoint integration of Uniform(0,1) at q=.95, e=.975, not an empirical study.
    uniform = (np.arange(1000) + 0.5) / 1000
    moment = joint_identification(uniform, np.full(1000, 0.95), np.full(1000, 0.975), 0.95)
    np.testing.assert_allclose([np.mean(value) for value in moment], 0, atol=1e-15)


def test_block_mean_draws_retain_native_missing_mask() -> None:
    values = np.array([1.0, -1.0, 2.0])
    indices = [0, 2, 4]
    seed, reps, block = 225, 31, 2
    rng = np.random.default_rng(seed)
    starts = rng.choice(np.arange(5), size=(reps, 3))
    expected = []
    lookup = dict(zip(indices, values, strict=True))
    for row in starts:
        chosen = [(int(start) + k) % 5 for start in row for k in range(block)][:5]
        observed = [lookup[index] for index in chosen if index in lookup]
        if observed:
            expected.append(np.mean(observed))
    actual = moving_block_mean_draws(
        values,
        reps=reps,
        block_length=block,
        rng=np.random.default_rng(seed),
        session_indices=indices,
    )
    np.testing.assert_allclose(actual, expected)


def test_diagnostics_use_joint_domain_fixed_rosters_and_shared_dates() -> None:
    infos = PASS_ALL_INFORMATION_SETS
    rows: list[dict[str, object]] = [
        {
            "model_name": model,
            "tail_side": "left_tail",
            "information_set": info,
            "forecast_date": f"2024-01-0{day}",
            "target_session_index": day - 1,
            "realized_loss": -1.5,
            "var_forecast": -2.0,
            "es_forecast": -1.0,
            "tail_level": 0.95,
            "fit_status": "ok",
            "is_valid_forecast": True,
            "refit_frequency": "monthly",
        }
        for model in ("a", "b")
        for info in infos
        for day in (1, 2, 3)
        if not (model == "b" and day == 2)
    ]
    roster: list[dict[str, object]] = [
        {
            "model_name": model,
            "tail_side": "left_tail",
            "information_set": info,
            "scheduled_rows": 3,
        }
        for model in ("a", "b", "missing")
        for info in infos
    ]
    output = build_joint_diagnostic_artifacts(
        rows, roster=roster, ml_model_names=("a", "b"), references=[]
    )
    calibration = output["joint_calibration"]
    assert len(calibration) == 12
    a = next(row for row in calibration if row["model_name"] == "a")
    assert a["joint_rows"] == 3
    assert a["var_moment"] == pytest.approx(0.95)
    assert a["joint_es_moment"] == pytest.approx(-9.0)
    assert a["var_moment_ci_lower"] == pytest.approx(0.95)
    assert a["var_moment_bootstrap_usable_reps"] == 999
    assert any(row["status"] == "unavailable_no_joint_rows" for row in calibration)
    samples = [
        row for row in output["joint_murphy_samples"] if row["comparison_family"] == "ml_models"
    ]
    assert len(samples) == 4
    assert all(row["common_n"] == 2 for row in samples)
    assert json.loads(str(samples[0]["common_dates"])) == ["2024-01-01", "2024-01-03"]
    curves = [row for row in output["joint_murphy"] if row["comparison_family"] == "ml_models"]
    assert {row["entity"] for row in curves} == {"a", "b"}
    assert all(row["common_n"] == 2 for row in curves)
    missing = build_joint_diagnostic_artifacts(
        rows, roster=roster, ml_model_names=("a", "b", "missing"), references=[]
    )
    samples = [
        row for row in missing["joint_murphy_samples"] if row["comparison_family"] == "ml_models"
    ]
    assert all(row["common_n"] == 0 for row in samples)
    assert all(json.loads(str(row["missing_entities"])) == ["missing"] for row in samples)
    assert not any(row["comparison_family"] == "ml_models" for row in missing["joint_murphy"])
    benchmark: list[dict[str, object]] = [
        {
            **row,
            "model_name": "reference",
            "information_set": "target_history_only",
            "refit_frequency": "daily",
        }
        for row in rows
        if row["model_name"] == "b" and row["information_set"] == infos[0]
    ]
    cross = build_joint_diagnostic_artifacts(
        rows + benchmark,
        roster=roster,
        ml_model_names=("a", "b"),
        references=[
            {"model_name": "reference", "tail_side": "left_tail"},
            {"model_name": None, "tail_side": "right_tail"},
        ],
    )
    samples = [
        row
        for row in cross["joint_murphy_samples"]
        if row["comparison_family"] == "initial_cross_suite"
    ]
    assert len(samples) == 4
    assert all(row["common_n"] == 2 for row in samples)
    assert all(json.loads(str(row["entities"])) == ["reference", "a", "b"] for row in samples)
    assert all(row["information_set"] == "target_history_only" for row in benchmark)
    external: list[dict[str, object]] = [
        {**row, "model_name": model, "refit_frequency": None if index % 2 else "daily"}
        for index, model in enumerate(
            BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES
        )
        for row in benchmark
    ]
    compared = build_joint_diagnostic_artifacts(
        rows + external,
        roster=roster,
        ml_model_names=("a", "b"),
        references=[],
    )
    samples = [
        row
        for row in compared["joint_murphy_samples"]
        if row["comparison_family"] == "external_models"
    ]
    assert len(samples) == 1 and samples[0]["common_n"] == 2
    rows[0]["realized_loss"] = -3.0
    group = _result_matrix_tail_model_groups(
        rows, loss_family="var_es_elementary", model_names=("a", "b")
    )[0]
    with pytest.raises(ValueError, match="targets disagree"):
        _murphy_group("ml_models", group)
