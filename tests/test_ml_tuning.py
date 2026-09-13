from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import lightgbm as lgb
import numpy as np
import pytest

from n225_open_gap_tail.config.runtime import PipelineRunError
from n225_open_gap_tail.models import ml_body as body
from n225_open_gap_tail.models import ml_tuning as tuning
from n225_open_gap_tail.models.ml_tail_oof import _fit_lgb_regression_model, _predict_lgb_rows


def cases(n: int = 40) -> dict[str, dict[str, Any]]:
    return {
        f"{info}/{side}": {
            "information_set": info,
            "tail_side": side,
            "tail_level": 0.95,
            "features": ["feature_x"],
            "train": [
                {
                    "forecast_date": (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
                    "realized_loss": (1 if side == "left_tail" else -1) * (0.01 * np.sin(i)),
                    "feature_x": float(i),
                    "clean_sample": True,
                }
                for i in range(n)
            ],
            "future": [{"forecast_date": (date(2020, 1, 1) + timedelta(days=n)).isoformat()}],
        }
        for info in "ABCD"
        for side in ("left_tail", "right_tail")
    }


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tuning, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(tuning, "ROUND_CAPS", (2, 3))
    monkeypatch.setattr(tuning, "CANDIDATES", (("current", {}), ("no_l1", {"reg_alpha": 0.0})))


def selection_args(grid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": grid,
        "targets": {key: np.zeros(len(case["train"])) for key, case in grid.items()},
        "role": "center:regression_l2:None",
        "objective": "regression_l2",
        "alpha": None,
        "cutoff": "2020-02-10",
        "runtime": tuning.BoundedFit(),
    }


def test_selection_is_eight_way_mean_and_uses_common_validation_not_common_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    round_caps = tuning.ROUND_CAPS
    assert round_caps == (79, 139, 199)
    configure(monkeypatch)
    monkeypatch.setattr(tuning, "ROUND_CAPS", round_caps)
    grid = cases()
    grid["D/right_tail"]["train"] = grid["D/right_tail"]["train"][3:]
    calls: list[tuple[str, list[int], dict[str, object]]] = []
    prefixes: list[int] = []

    def fit(case: Any, target: Any, indices: Any, **kwargs: Any) -> Any:
        calls.append((case["information_set"], indices, kwargs["params"]))
        current = "reg_alpha" not in kwargs["params"]
        # Seven cases prefer no_l1, but the eighth makes its *mean* worse.
        prediction = 1.0 if current else 4.0 if case is grid["D/right_tail"] else 0.0

        def predict(x: Any, *, num_iteration: int) -> Any:
            prefixes.append(num_iteration)
            return np.full(len(x), prediction + abs(num_iteration - 139) / 60)

        return (
            SimpleNamespace(n_estimators_=199, predict=predict),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "_fit", fit)
    params, receipt, oof = tuning.select_parameters(**selection_args(grid))
    assert params == {"n_estimators": 139}  # shared winner, not per-case winners or last prefix
    assert receipt["status"] == "selected"
    assert len(receipt["folds"]) == 5
    assert sum(len(f["validation_dates"]) for f in receipt["folds"]) == 27
    for fold in receipt["folds"]:
        assert fold["training"]["A/left_tail"]["n"] - fold["training"]["D/right_tail"]["n"] == 3
    assert len(calls) == 80  # 2 candidates x 5 folds x 8 cases; not 240
    assert all(params["n_estimators"] == 199 for _, _, params in calls)
    assert prefixes == list(round_caps) * len(calls)
    for candidate in receipt["candidates"]:
        assert len(candidate["rounds"]) == 3
        assert all(len(round_["per_case_loss"]) == 8 for round_ in candidate["rounds"])
    folds = tuning.date_folds(grid, "2020-02-10")
    assert folds == tuning.date_folds(grid, "2020-02-10")
    for fold in folds:
        heldout_dates = []
        for key, (train, valid) in fold.items():
            assert not set(train) & set(valid)
            assert max(grid[key]["train"][i]["forecast_date"] for i in train) < min(
                grid[key]["train"][i]["forecast_date"] for i in valid
            )
            np.testing.assert_equal(oof[key][valid], np.ones(len(valid)))
            heldout_dates.append([grid[key]["train"][i]["forecast_date"] for i in valid])
        assert all(days == heldout_dates[0] for days in heldout_dates)
        assert {0, 1, 2}.issubset(fold["A/left_tail"][0])


@pytest.mark.parametrize("failure", ["missing", "short", "no_finite", "timeout", "partial", "nan"])
def test_selection_missing_groups_and_timeout_never_rank_seven_cases(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    configure(monkeypatch)
    grid = cases()
    args = selection_args(grid)
    if failure == "missing":
        grid.pop("D/right_tail")
    if failure == "short":
        args["cutoff"] = "2020-01-10"
    if failure == "no_finite":
        args["targets"]["D/right_tail"][:] = np.nan
    calls = 0

    def fit(*a: Any, **kw: Any) -> Any:
        nonlocal calls
        calls += 1
        if failure == "timeout" or (failure == "partial" and calls == 80):
            raise tuning.FitTimeout("deadline")
        prediction = np.nan if failure == "nan" and calls in (40, 80) else 0.0
        return (
            SimpleNamespace(n_estimators_=3, predict=lambda x, **k: np.full(len(x), prediction)),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "_fit", fit)
    params, receipt, _ = tuning.select_parameters(**args)
    if failure == "partial":
        assert receipt["status"] == "search_incomplete" and params["n_estimators"] == 2
    else:
        assert params == {"n_estimators": 160}
        assert receipt["status"].startswith("fixed_")
    assert args["runtime"].selection_deadline is None


def test_deadline_and_unexpected_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    args = selection_args(cases())
    params, record, _ = tuning.select_parameters(**args, selection_seconds=0)
    assert params == {"n_estimators": 160} and record["status"] == "fixed_no_complete_candidate"

    def crash(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("unexpected implementation failure")

    monkeypatch.setattr(tuning, "_fit", crash)
    with pytest.raises(RuntimeError, match="unexpected"):
        tuning.select_parameters(**args)
    assert args["runtime"].selection_deadline is None
    args["runtime"].global_deadline = 0
    with pytest.raises(tuning.PilotDeadline):
        tuning.select_parameters(**args)


def test_selects_once_then_native_full_refits(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    grid = cases()
    args = selection_args(grid)
    observed: list[dict[str, Any]] = []

    def select(cases: Any, targets: Any, **kw: Any) -> Any:
        cutoff = kw["cutoff"]
        return (
            {"n_estimators": int(cutoff[-2:])},
            {"cutoff": cutoff},
            {
                key: np.r_[np.full(10, np.nan), np.ones(len(target) - 10)]
                for key, target in targets.items()
            },
        )

    def fit(case: Any, target: Any, indices: Any, **kw: Any) -> Any:
        assert case["train"][indices[-1]]["forecast_date"] < (
            case["future"][0]["forecast_date"]
            if kw["label"] == "final"
            else case["train"][indices[-1] + 1]["forecast_date"]
        )
        observed.append(kw)
        return (
            SimpleNamespace(n_estimators_=1, predict=lambda x, **k: np.zeros(len(x))),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "select_parameters", select)
    monkeypatch.setattr(tuning, "_fit", fit)
    records: list[dict[str, Any]] = []
    result = tuning.fit_joint_component(
        grid,
        args["targets"],
        role=args["role"],
        objective="regression_l2",
        alpha=None,
        runtime=args["runtime"],
        receipt=records.append,
    )
    assert len(records) == 1 and len(observed) == 8
    assert all(o["label"] == "final" for o in observed)
    for record in records:
        assert len(record["fits"]) == 8
        assert all(f["train_end"] < record["cutoff"] for f in record["fits"])
    for component in result.values():
        assert component["oof_warmup_rows"] == 10
        assert np.isnan(component["oof"][:10]).all()
        assert np.all(component["oof"][10:] == 1)
        assert len(component["fitted"]) == 40
        assert np.isfinite(component["fitted"]).all()


def test_component_expected_failures_preserve_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    grid = cases()
    args = selection_args(grid)
    args["targets"]["D/right_tail"][:] = np.nan
    monkeypatch.setattr(tuning, "select_parameters", lambda *a, **k: ({}, {}, {}))

    def unavailable(*a: Any, **kw: Any) -> Any:
        raise PipelineRunError("expected domain failure")

    monkeypatch.setattr(tuning, "_fit", unavailable)
    fitted = tuning.fit_joint_component(
        grid,
        args["targets"],
        role="direct",
        objective="quantile",
        alpha=0.95,
        runtime=args["runtime"],
        receipt=lambda record: None,
    )
    assert all(np.isnan(v["fitted"]).all() and v["failure_reason"] for v in fitted.values())


def test_native_prefix_predictions_and_worker_timeout() -> None:
    case = cases(80)["A/left_tail"]
    y = np.array([r["realized_loss"] for r in case["train"]])
    runtime = tuning.BoundedFit(fit_seconds=30)
    options = dict(
        lgb=lgb,
        rows=case["train"],
        target=y,
        candidate_features=["feature_x"],
        objective="regression_l2",
        random_state=225,
    )
    try:
        long, _, active = _fit_lgb_regression_model(
            **options,
            lgbm_params={"n_estimators": 8, "reg_alpha": 0, "min_child_samples": 3},
            fit_executor=runtime,
        )
        short, _, _ = _fit_lgb_regression_model(
            **options,
            lgbm_params={"n_estimators": 3, "reg_alpha": 0, "min_child_samples": 3},
        )
        assert long.booster_.params["num_threads"] == short.booster_.params["num_threads"] == 3
        np.testing.assert_allclose(
            _predict_lgb_rows(long, case["train"], active, num_iteration=3),
            _predict_lgb_rows(short, case["train"], active),
            rtol=0,
            atol=1e-15,
        )
        assert runtime.fits == 1 and runtime.worker_peak_rss_bytes > 0
        runtime.selection_deadline = time.monotonic() - 1
        with pytest.raises(tuning.FitTimeout, match="joint_selection"):
            runtime({}, np.ones((2, 1)), np.ones(2))
    finally:
        runtime.close()
    runtime = tuning.BoundedFit(fit_seconds=0.001)
    try:
        with pytest.raises(tuning.FitTimeout):
            runtime({"n_estimators": 1000}, np.ones((100, 1)), np.ones(100))
        assert runtime.timeouts == 1 and runtime.pool is None
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "objective,alpha",
    [
        ("regression_l2", None),
        ("regression_l1", None),
        ("quantile", 0.95),
        ("huber", None),
        ("gamma", None),
    ],
)
def test_losses_are_native_component_metrics(objective: str, alpha: float | None) -> None:
    y, prediction = np.array([-2.0, 1.0]), np.zeros(2)
    loss = tuning.validation_loss(y, prediction, objective, alpha)
    expected = {
        "regression_l2": 2.5,
        "gamma": 2.5,
        "regression_l1": 1.5,
        "quantile": 0.525,
        "huber": 0.945,
    }[objective]
    assert loss == pytest.approx(expected)
    assert np.isnan(tuning.validation_loss(y, np.array([np.nan, 0]), objective, alpha))


def test_joint_body_targets_reuse_selected_oof_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch)
    grid = cases(40)
    captured: dict[str, Any] = {}

    def fit(cases: Any, targets: Any, **kw: Any) -> Any:
        captured[kw["role"]] = targets
        return {
            key: {
                "fitted": np.full(len(y), 99.0),
                "oof": np.r_[np.full(10, np.nan), np.zeros(len(y) - 10)],
                "oof_warmup_rows": 10,
                "model": SimpleNamespace(predict=lambda x: np.zeros(len(x))),
                "active_features": ["feature_x"],
                "gate": {},
            }
            for key, y in targets.items()
        }

    monkeypatch.setattr(tuning, "fit_joint_component", fit)
    fitted = tuning.fit_joint_bodies(
        grid, runtime=tuning.BoundedFit(), receipt=lambda r: None, progress=lambda message: None
    )
    assert len(captured) == 12
    assert not any("fair" in role or "tweedie" in role for role in captured)
    key = "A/left_tail"
    y = captured["center:regression_l2:None"][key]
    squared = captured["spread:mean_rms_l2"][key]
    for objective in ("poisson", "gamma"):
        np.testing.assert_equal(squared, captured[f"spread:mean_rms_{objective}"][key])
    np.testing.assert_allclose(squared[10:], y[10:] ** 2)
    assert np.isnan(squared[:10]).all()
    np.testing.assert_allclose(captured["spread:median_mad"][key][10:], np.abs(y[10:]))
    monkeypatch.setattr(body, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    bodies = dict(
        body.fit_body_recipes(
            grid[key]["train"],
            candidate_features=["feature_x"],
            information_set="A",
            tail_level=0.95,
            lgb=lgb,
            components=fitted[key],
            calibration_kind="oof",
        )
    )
    assert bodies["mean_log_abs"]["center"] is bodies["mean_rms_l2"]["center"]
    fitted[key]["center:regression_l2:None"]["failure_reason"] = "expected unavailable"
    unavailable = dict(
        body.fit_body_recipes(
            grid[key]["train"],
            candidate_features=["feature_x"],
            information_set="A",
            tail_level=0.95,
            lgb=lgb,
            components=fitted[key],
            calibration_kind="oof",
        )
    )
    assert unavailable["mean_log_abs"]["fit_status"] == "unavailable_body_fit"


def test_native_joint_components_and_direct_forecast_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    from n225_open_gap_tail.forecasting import body_experiment as experiment

    configure(monkeypatch)
    # The public estimator has separate tests; this check concerns body-fit reuse.
    monkeypatch.setattr(
        experiment,
        "estimate_public_unibm",
        lambda *a, **k: {
            "status": "unavailable_public_unibm",
            "failure_reason": "small integration sample",
        },
    )
    monkeypatch.setattr(body, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    monkeypatch.setattr(
        tuning, "CANDIDATES", (("small", {"reg_alpha": 0.0, "min_child_samples": 3}),)
    )
    monkeypatch.setattr(tuning, "ROUND_CAPS", (2,))

    def local_fit(self: Any, params: Any, x: Any, y: Any) -> Any:
        return tuning._native_fit(params, x, y)[0]

    monkeypatch.setattr(tuning.BoundedFit, "__call__", local_fit)
    grid = cases(120)
    fitted = tuning.fit_joint_bodies(grid, runtime=tuning.BoundedFit(), receipt=lambda row: None)
    key = "A/left_tail"
    for role in fitted[key]:
        configs = [
            {
                k: v
                for k, v in fitted[case][role]["model"].get_params().items()
                if k != "random_state"
            }
            for case in grid
        ]
        assert all(config == configs[0] for config in configs)
    expected = dict(
        body.fit_body_recipes(
            grid[key]["train"],
            candidate_features=["feature_x"],
            information_set="A",
            tail_level=0.95,
            lgb=lgb,
            components=fitted[key],
            calibration_kind="oof",
        )
    )
    assert all(v["fit_status"] == "ok" for v in expected.values())
    for recipe in expected.values():
        assert recipe["oof_warmup_rows"] > 0
        assert len(recipe["standardized_losses"]) == len(grid[key]["train"])
        y = np.array([row["realized_loss"] for row in grid[key]["train"]])
        np.testing.assert_allclose(
            recipe["standardized_losses"],
            (y - recipe["mu_oof"]) / recipe["scale_oof"],
            equal_nan=True,
        )

    # Native fitting finished: this forecast path must consume the actual supplied fits.
    def forbid(*a: Any, **kw: Any) -> Any:
        raise AssertionError("unexpected refit")

    monkeypatch.setattr(experiment, "_fit_lgb_regression_model", forbid)
    future = [{**grid[key]["train"][-1], "forecast_date": "2020-05-01"}]
    result = experiment.forecast_shared_body_refit(
        grid[key]["train"],
        future,
        candidate_features=["feature_x"],
        information_set="A",
        tail_side="left_tail",
        components=fitted[key],
        calibration_kind="oof",
    )
    assert len(result["forecasts"]) == 22 and result["diagnostics"][0]["fit_status"] == "ok"
    assert "in_sample" not in result
    assert len(result["oof"]) == 7 * 120
    assert any(row["structural_warmup"] for row in result["oof"])
    fitted[key]["direct"]["failure_reason"] = "bounded fit failure"
    result = experiment.forecast_shared_body_refit(
        grid[key]["train"],
        future,
        candidate_features=["feature_x"],
        information_set="A",
        tail_side="left_tail",
        components=fitted[key],
        calibration_kind="oof",
    )
    assert result["forecasts"][0]["var_forecast"] is None
    with pytest.raises(KeyError):
        experiment.forecast_shared_body_refit(
            grid[key]["train"],
            future,
            candidate_features=["feature_x"],
            information_set="A",
            tail_side="left_tail",
            components={},
        )


def test_spread_search_uses_only_prior_oof_targets_and_fixed_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(tuning, "CANDIDATES", (("current", {}),))
    grid = cases()
    args = selection_args(grid)
    folds = tuning.date_folds(grid, args["cutoff"])
    # Center warm-up is ten rows; the first two blocks cannot yet train spread.
    folds = [
        split for split in folds if all(sum(i >= 10 for i in t) >= 10 for t, _ in split.values())
    ]
    targets = {key: np.r_[np.full(10, np.nan), np.arange(30.0)] for key in grid}
    spread_calls = 0

    def fit(case: Any, target: Any, indices: Any, **kw: Any) -> Any:
        nonlocal spread_calls
        key = f"{case['information_set']}/{case['tail_side']}"
        fold = int(kw["label"].split(":")[-1])
        train, valid = folds[fold][key]
        assert indices == [i for i in train if i >= 10]
        assert max(indices) < min(valid)
        assert args["runtime"].selection_deadline is not None
        assert kw["role"].startswith("spread:")
        spread_calls += 1
        np.testing.assert_equal(target, targets[key])
        return (
            SimpleNamespace(n_estimators_=3, predict=lambda x, **k: np.zeros(len(x))),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "_fit", fit)
    args.update(role="spread:mean_rms_l2", targets=targets, folds=folds)
    _, record, oof = tuning.select_parameters(**args)
    assert record["status"] == "selected" and spread_calls == 24
    assert record["scored_fold_count"] == 3
    assert np.isnan(oof["A/left_tail"][:22]).all()
    assert np.isfinite(oof["A/left_tail"][22:]).all()
    # Missing validation after warm-up must fail, not change the folds/denominator.
    targets["D/right_tail"][22] = np.nan
    _, failed, _ = tuning.select_parameters(**args)
    assert failed["status"] == "fixed_no_complete_candidate"
    assert failed["folds"] == record["folds"]


def test_cv_pools_dates_not_fold_means_and_does_not_drop_bad_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(tuning, "CANDIDATES", (("current", {}),))
    grid = cases(41)
    args = selection_args(grid)
    args["cutoff"] = "2020-02-11"

    def fit(case: Any, target: Any, indices: Any, **kw: Any) -> Any:
        value = float(kw["label"].split(":")[-1])
        return (
            SimpleNamespace(n_estimators_=3, predict=lambda x, **k: np.full(len(x), value)),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "_fit", fit)
    _, record, _ = tuning.select_parameters(**args)
    assert record["parameters"]["n_estimators"] == 2  # tied losses prefer fewer rounds
    assert record["candidates"][0]["rounds"][0]["mean_loss"] == pytest.approx(
        (7 * 0 + 7 * 1 + 7 * 4 + 7 * 9 + 3 * 16) / 31
    )
    args["targets"]["D/right_tail"][10] = np.nan
    _, failed, _ = tuning.select_parameters(**args)
    assert failed["status"] == "fixed_no_complete_candidate"
    assert failed["folds"] == record["folds"]  # validity never changes the date partition


def test_fixed_fallback_produces_oof_not_fitted_residuals(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    args = selection_args(cases())
    monkeypatch.setattr(
        tuning, "select_parameters", lambda *a, **k: ({"n_estimators": 160}, {}, {})
    )
    calls = []

    def fit(case: Any, target: Any, indices: Any, **kw: Any) -> Any:
        calls.append(kw["label"])
        assert kw["params"] == {"n_estimators": 160}
        return (
            SimpleNamespace(
                n_estimators_=160, predict=lambda x, **k: np.full(len(x), len(indices))
            ),
            {},
            ["feature_x"],
        )

    monkeypatch.setattr(tuning, "_fit", fit)
    result = tuning.fit_joint_component(
        **{k: v for k, v in args.items() if k != "cutoff"}, receipt=lambda r: None
    )
    assert len(calls) == 8 * 6
    for c in result.values():
        assert np.isnan(c["oof"][:10]).all()
        assert np.all(c["oof"][10:] < c["fitted"][10:])


@pytest.mark.parametrize("workers", [2, 3])
def test_spawn_fit_from_independent_month_threads(workers: int) -> None:
    def fit(seed: int) -> Any:
        runtime = tuning.BoundedFit(fit_seconds=30)
        try:
            model = runtime(
                {"n_estimators": 2, "num_threads": 3, "verbosity": -1, "random_state": seed},
                np.arange(30.0).reshape(-1, 1),
                np.arange(30.0),
            )
            return model.predict(np.array([[2.0]]))
        finally:
            runtime.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        values = list(executor.map(fit, range(workers)))
    assert all(np.isfinite(v).all() for v in values)
