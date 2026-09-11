"""Bounded three-fold random CV shared by A--D and both exposures.

Only component validation losses select parameters. Tail outcomes and evaluation
gates are not inputs. Final full-history in-sample residuals calibrate the tails.
"""

from __future__ import annotations

import multiprocessing as mp
import resource
import sys
import time
from collections.abc import Callable, Mapping
from multiprocessing.pool import Pool
from typing import Any

import lightgbm as lgb
import numpy as np
from sklearn.model_selection import KFold  # type: ignore[import-untyped]

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_MIN_OOF_TRAIN_ROWS,
    PipelineRunError,
)
from n225_open_gap_tail.models.ml_body import (
    BODY_RECIPES,
    TRAINING_MULTIPLIER,
    Array,
    spread_target,
)
from n225_open_gap_tail.models.ml_tail_oof import (
    _fit_lgb_regression_model,
    _ml_tail_seed,
    _predict_lgb_rows,
)

CV_SPLITS = 3
CV_SEED = 0
Fold = dict[str, tuple[list[int], list[int]]]
ROUND_CAPS = (79, 139, 199)
CANDIDATES: tuple[tuple[str, dict[str, object]], ...] = (
    ("current", {}),
    ("no_l1", {"reg_alpha": 0.0}),
    ("no_l1_l2", {"reg_alpha": 0.0, "reg_lambda": 0.0}),
    ("lower_capacity", {"reg_alpha": 0.0, "num_leaves": 7, "min_child_samples": 50}),
    ("higher_capacity", {"reg_alpha": 0.0, "num_leaves": 31}),
    ("faster_learning", {"reg_alpha": 0.0, "learning_rate": 0.05}),
)


class PilotDeadline(BaseException):
    """Stop the workflow, including legacy per-model exception handlers."""


class FitTimeout(TimeoutError):
    """Expected bounded fit/search failure; never a reason to retry that fit."""


def _native_fit(params: dict[str, Any], x: Array, y: Array) -> tuple[Any, int]:
    model = lgb.LGBMRegressor(**params)
    model.fit(x, y)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return model, int(rss * (1 if sys.platform == "darwin" else 1024))


class BoundedFit:
    """One reusable spawn worker: a native C fit can be terminated at its deadline."""

    def __init__(self, *, total_seconds: float | None = None, fit_seconds: float = 300) -> None:
        self.global_deadline = None if total_seconds is None else time.monotonic() + total_seconds
        self.fit_seconds = fit_seconds
        self.selection_deadline: float | None = None
        self.pool: Pool | None = None
        self.fits = 0
        self.timeouts = 0
        self.worker_peak_rss_bytes = 0

    def check(self) -> None:
        if self.global_deadline is not None and time.monotonic() >= self.global_deadline:
            raise PilotDeadline("Pilot whole-workflow deadline reached")

    def close(self) -> None:
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()
            self.pool = None

    def __call__(self, params: dict[str, object], x: Array, y: Array) -> Any:
        self.check()
        started = time.monotonic()
        deadline = min(
            started + self.fit_seconds,
            self.selection_deadline or float("inf"),
            self.global_deadline or float("inf"),
        )
        if deadline <= started:
            raise FitTimeout("joint_selection_timeout")
        if self.pool is None:
            self.pool = mp.get_context("spawn").Pool(1)
        self.fits += 1
        pending = self.pool.apply_async(_native_fit, (params, x, y))
        try:
            model, rss = pending.get(timeout=max(0.0, deadline - time.monotonic()))
        except mp.TimeoutError as exc:
            self.timeouts += 1
            self.close()
            self.check()
            raise FitTimeout("lightgbm_fit_or_selection_timeout") from exc
        self.worker_peak_rss_bytes = max(self.worker_peak_rss_bytes, rss)
        self.check()
        return model


def validation_loss(target: Array, predicted: Array, objective: str, alpha: float | None) -> float:
    """Q41 losses, in each component's own target units (never across components)."""
    if not len(target) or not np.isfinite(target).all() or not np.isfinite(predicted).all():
        return float("nan")
    error = target - predicted
    absolute = np.abs(error)
    if objective == "quantile":
        assert alpha is not None
        loss = np.maximum(alpha * error, (alpha - 1) * error)
    elif objective == "regression_l1":
        loss = absolute
    elif objective == "huber":
        loss = np.where(absolute <= 0.9, 0.5 * error**2, 0.9 * (absolute - 0.45))
    elif objective == "fair":
        loss = absolute - np.log1p(absolute)  # fixed fair_c=1
    else:
        loss = error**2  # also the common residual-square metric for all RMS objectives
    return float(np.mean(loss))


def _eligible(case: Mapping[str, Any], target: Array, cutoff: str) -> list[int]:
    return [
        i
        for i, row in enumerate(case["train"])
        if str(row["forecast_date"]) < cutoff and np.isfinite(target[i])
    ]


def _fit(
    case: Mapping[str, Any],
    target: Array,
    indices: list[int],
    *,
    role: str,
    objective: str,
    alpha: float | None,
    label: object,
    params: Mapping[str, object],
    runtime: BoundedFit,
) -> tuple[Any, dict[str, Any], list[str]]:
    seed = (
        int(case["tail_level"] * 10000) + len(case["information_set"])
        if role == "direct"
        else _ml_tail_seed(case["information_set"], case["tail_level"], role, label)
    )
    return _fit_lgb_regression_model(
        lgb=lgb,
        rows=[case["train"][i] for i in indices],
        target=target[indices],
        candidate_features=case["features"],
        objective=objective,
        alpha=alpha,
        random_state=seed,
        lgbm_params=params,
        fit_executor=runtime,
    )


def date_folds(cases: Mapping[str, dict[str, Any]], cutoff: str) -> list[Fold]:
    """Partition common dates once; retain each scenario's extra native training dates."""
    maps = {
        key: {
            str(row["forecast_date"]): i
            for i, row in enumerate(case["train"])
            if str(row["forecast_date"]) < cutoff
        }
        for key, case in cases.items()
    }
    if len(maps) != 8:
        return []
    common = sorted(set.intersection(*(set(mapping) for mapping in maps.values())))
    if len(common) < CV_SPLITS:
        return []
    result = []
    for _, valid in KFold(CV_SPLITS, shuffle=True, random_state=CV_SEED).split(common):
        heldout = [common[i] for i in valid]
        heldout_set = set(heldout)
        result.append(
            {
                key: (
                    [i for day, i in mapping.items() if day not in heldout_set],
                    [mapping[day] for day in heldout],
                )
                for key, mapping in maps.items()
            }
        )
    return result


def _center_fold_residuals(
    cases: Mapping[str, dict[str, Any]],
    folds: list[Fold],
    centers: Mapping[str, dict[str, Any]],
    runtime: BoundedFit,
) -> list[dict[str, Array]]:
    """One selected-center reconstruction per fold, reused by its spread recipes."""
    result = []
    for fold, split in enumerate(folds):
        residuals = {}
        for key, case in cases.items():
            center = centers[key]
            y = (
                np.array([float(row["realized_loss"]) for row in case["train"]])
                * TRAINING_MULTIPLIER
            )
            train, _ = split[key]
            model, _, active = _fit(
                case,
                y,
                train,
                role=center["role"],
                objective=center["objective"],
                alpha=center["alpha"],
                label=f"cv:{fold}",
                params=center["parameters"],
                runtime=runtime,
            )
            # T predictions are in-sample; V predictions use only this fold's T fit.
            residuals[key] = y - _predict_lgb_rows(model, case["train"], active)
        result.append(residuals)
    return result


def select_parameters(
    cases: Mapping[str, dict[str, Any]],
    targets: Mapping[str, Array],
    *,
    role: str,
    objective: str,
    alpha: float | None,
    cutoff: str,
    runtime: BoundedFit,
    selection_seconds: float = 1800,
    folds: list[Fold] | None = None,
    center_cv: dict[str, Any] | None = None,
    transform: str | None = None,
) -> tuple[dict[str, object], dict[str, Any]]:
    """Rank only complete 3 x 8 scores: pooled dates within case, then equal cases."""
    runtime.check()
    started = time.monotonic()
    folds = date_folds(cases, cutoff) if folds is None else folds
    record: dict[str, Any] = {
        "role": role,
        "cutoff": cutoff,
        "objective": objective,
        "alpha": alpha,
        "cv_splits": CV_SPLITS,
        "cv_seed": CV_SEED,
        "status": "fixed_short_history",
        "folds": [],
        "candidates": [],
        "selected_name": "current",
        "parameters": {"n_estimators": 160},
    }
    for fold, split in enumerate(folds):
        record["folds"].append(
            {
                "fold": fold,
                "validation_dates": [
                    str(cases[next(iter(cases))]["train"][i]["forecast_date"])
                    for i in split[next(iter(cases))][1]
                ],
                "training": {
                    key: {
                        "n": len(train),
                        "start": str(cases[key]["train"][train[0]]["forecast_date"])
                        if train
                        else None,
                        "end": str(cases[key]["train"][train[-1]]["forecast_date"])
                        if train
                        else None,
                    }
                    for key, (train, _) in split.items()
                },
            }
        )
    if (
        len(cases) != 8
        or len(folds) != CV_SPLITS
        or any(
            len(train) < ML_TAIL_MIN_OOF_TRAIN_ROWS
            for split in folds
            for train, _ in split.values()
        )
    ):
        record["failure_reason"] = "eight_case_common_validation_or_training_history_unavailable"
        record["elapsed_seconds"] = time.monotonic() - started
        return dict(record["parameters"]), record

    best: tuple[float, int, int] | None = None
    incomplete = False
    runtime.selection_deadline = started + selection_seconds
    try:
        fold_targets: list[Mapping[str, Array]] = [targets] * len(folds)
        if center_cv is not None:
            assert transform is not None
            if "failure_reason" in center_cv:
                raise PipelineRunError(center_cv["failure_reason"])
            if "residuals" not in center_cv:
                try:
                    center_cv["residuals"] = _center_fold_residuals(
                        cases, folds, center_cv["components"], runtime
                    )
                except (FitTimeout, PipelineRunError) as exc:
                    center_cv["failure_reason"] = str(exc)
                    raise
            fold_targets = [
                {key: spread_target(residual, transform) for key, residual in residuals.items()}
                for residuals in center_cv["residuals"]
            ]
        for index, (name, overrides) in enumerate(CANDIDATES):
            runtime.check()
            if time.monotonic() >= runtime.selection_deadline:
                incomplete = True
                break
            scores: dict[int, dict[str, list[tuple[int, float]]]] = {
                rounds: {key: [] for key in cases} for rounds in ROUND_CAPS
            }
            detail: dict[str, Any] = {"name": name, "actual_trees": {}, "status": "complete"}
            try:
                for fold, split in enumerate(folds):
                    for key, case in cases.items():
                        train, valid = split[key]
                        target = fold_targets[fold][key]
                        eligible = [i for i in train if np.isfinite(target[i])]
                        if (
                            len(eligible) < ML_TAIL_MIN_OOF_TRAIN_ROWS
                            or not np.isfinite(target[valid]).all()
                        ):
                            raise PipelineRunError("nonfinite_cv_target_or_insufficient_training")
                        model, _, active = _fit(
                            case,
                            target,
                            eligible,
                            role=role,
                            objective=objective,
                            alpha=alpha,
                            label=f"cv:{fold}",
                            params={**overrides, "n_estimators": max(ROUND_CAPS)},
                            runtime=runtime,
                        )
                        detail["actual_trees"][f"{fold}/{key}"] = int(model.n_estimators_)
                        for rounds in ROUND_CAPS:
                            runtime.check()
                            if time.monotonic() >= runtime.selection_deadline:
                                raise FitTimeout("joint_selection_timeout")
                            prediction = _predict_lgb_rows(
                                model,
                                [case["train"][i] for i in valid],
                                active,
                                num_iteration=rounds,
                            )
                            scores[rounds][key].append(
                                (
                                    len(valid),
                                    validation_loss(target[valid], prediction, objective, alpha),
                                )
                            )
            except (FitTimeout, PipelineRunError) as exc:
                incomplete = True
                detail.update(status="incomplete", failure_reason=str(exc))
            detail["rounds"] = []
            for rounds, per_case in scores.items():
                complete = all(
                    len(values) == CV_SPLITS and all(np.isfinite(loss) for _, loss in values)
                    for values in per_case.values()
                )
                pooled = {
                    key: float(sum(n * loss for n, loss in values) / sum(n for n, _ in values))
                    if len(values) == CV_SPLITS and all(np.isfinite(loss) for _, loss in values)
                    else None
                    for key, values in per_case.items()
                }
                mean = float(np.mean(list(pooled.values()))) if complete else None
                detail["rounds"].append(
                    {
                        "n_estimators": rounds,
                        "complete": complete,
                        "fold_losses": {
                            key: [
                                {"n": n, "loss": loss if np.isfinite(loss) else None}
                                for n, loss in values
                            ]
                            for key, values in per_case.items()
                        },
                        "per_case_loss": pooled,
                        "mean_loss": mean,
                    }
                )
                if not complete:
                    incomplete = True
                elif mean is not None:
                    rank = (mean, rounds, index)
                    if best is None or rank < best:
                        best = rank
                        record.update(
                            selected_name=name, parameters={**overrides, "n_estimators": rounds}
                        )
            record["candidates"].append(detail)
    except (FitTimeout, PipelineRunError) as exc:
        incomplete = True
        record["failure_reason"] = str(exc)
    finally:
        runtime.selection_deadline = None
    record["status"] = (
        "fixed_no_complete_candidate"
        if best is None
        else "search_incomplete"
        if incomplete
        else "selected"
    )
    record["elapsed_seconds"] = time.monotonic() - started
    return dict(record["parameters"]), record


def fit_joint_component(
    cases: Mapping[str, dict[str, Any]],
    targets: Mapping[str, Array],
    *,
    role: str,
    objective: str,
    alpha: float | None,
    runtime: BoundedFit,
    receipt: Callable[[dict[str, Any]], None],
    folds: list[Fold] | None = None,
    center_cv: dict[str, Any] | None = None,
    transform: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Select once on D; refit each scenario's full D and retain fitted values."""
    cutoff = min(str(case["future"][0]["forecast_date"]) for case in cases.values())
    params, record = select_parameters(
        cases,
        targets,
        role=role,
        objective=objective,
        alpha=alpha,
        cutoff=cutoff,
        runtime=runtime,
        folds=folds,
        center_cv=center_cv,
        transform=transform,
    )
    results: dict[str, dict[str, Any]] = {}
    record["fits"] = []
    for key, case in cases.items():
        runtime.check()
        started = time.monotonic()
        indices = _eligible(case, targets[key], cutoff)
        result: dict[str, Any] = {
            "fitted": np.full(len(case["train"]), np.nan),
            "role": role,
            "objective": objective,
            "alpha": alpha,
            "parameters": params,
        }
        detail: dict[str, Any] = {
            "case": key,
            "label": "final",
            "n": len(indices),
            "status": "ok",
            "train_end": str(case["train"][indices[-1]]["forecast_date"]) if indices else None,
        }
        try:
            if len(indices) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
                raise PipelineRunError("unavailable_in_sample_standardization_insufficient_sample")
            model, gate, active = _fit(
                case,
                targets[key],
                indices,
                role=role,
                objective=objective,
                alpha=alpha,
                label="final",
                params=params,
                runtime=runtime,
            )
            detail["actual_trees"] = int(model.n_estimators_)
            result.update(
                model=model,
                gate=gate,
                active_features=active,
                fitted=_predict_lgb_rows(model, case["train"], active),
            )
        except (FitTimeout, PipelineRunError) as exc:
            detail.update(status="unavailable", failure_reason=str(exc))
            result["failure_reason"] = str(exc)
        detail["elapsed_seconds"] = time.monotonic() - started
        record["fits"].append(detail)
        results[key] = result
    receipt(record)
    return results


def fit_joint_bodies(
    cases: Mapping[str, dict[str, Any]],
    *,
    runtime: BoundedFit,
    receipt: Callable[[dict[str, Any]], None],
    progress: Callable[[str], None] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    components: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in cases}
    center_caches: dict[str, dict[str, Any]] = {}
    cutoff = min(str(case["future"][0]["forecast_date"]) for case in cases.values())
    folds = date_folds(cases, cutoff)
    y = {
        key: np.array([float(r["realized_loss"]) for r in case["train"]]) * TRAINING_MULTIPLIER
        for key, case in cases.items()
    }

    def fit(
        role: str,
        targets: Mapping[str, Array],
        objective: str,
        alpha: float | None,
        *,
        center_cv: dict[str, Any] | None = None,
        transform: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        if progress:
            progress(f"joint component {role}")
        fitted = fit_joint_component(
            cases,
            targets,
            role=role,
            objective=objective,
            alpha=alpha,
            runtime=runtime,
            receipt=receipt,
            folds=folds,
            center_cv=center_cv,
            transform=transform,
        )
        for key in cases:
            components[key][role] = fitted[key]
        return fitted

    for objective, alpha in (
        ("regression_l2", None),
        ("quantile", 0.5),
        ("huber", None),
        ("fair", None),
        ("quantile", 0.25),
        ("quantile", 0.75),
    ):
        role = f"center:{objective}:{alpha}"
        center_caches[role] = {"components": fit(role, y, objective, alpha)}
    for recipe, (objective, transform, spread_objective) in BODY_RECIPES.items():
        if transform == "iqr":
            continue
        center_role = f"center:{objective}:{0.5 if objective == 'quantile' else None}"
        targets = {
            key: spread_target(y[key] - components[key][center_role]["fitted"], transform)
            for key in cases
        }
        fit(
            f"spread:{recipe}",
            targets,
            spread_objective,
            None,
            center_cv=center_caches[center_role],
            transform=transform,
        )
    fit("direct", y, "quantile", next(iter(cases.values()))["tail_level"])
    return components
