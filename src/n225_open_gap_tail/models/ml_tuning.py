"""Bounded expanding-fold CV shared by A--D and both exposures.

Only component validation losses select parameters. Tail outcomes and evaluation
gates are not inputs. Selected-parameter OOF residuals calibrate the tails;
selection uses all outer training folds, not a historical hyperparameter replay.
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

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_MIN_OOF_TRAIN_ROWS,
    ML_TAIL_OOF_SPLITS,
    PipelineRunError,
)
from n225_open_gap_tail.models.ml_body import (
    BODY_RECIPES,
    TRAINING_MULTIPLIER,
    Array,
    spread_target,
)
from n225_open_gap_tail.models.ml_tail_oof import (
    _blocked_expanding_oof_folds,
    _fit_lgb_regression_model,
    _ml_tail_seed,
    _predict_lgb_rows,
)

CV_SPLITS = ML_TAIL_OOF_SPLITS
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
    """Five chronological validation blocks; each fit retains its native past only."""
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
    result = []
    for _, valid in _blocked_expanding_oof_folds(
        len(common), n_splits=CV_SPLITS, min_train_rows=ML_TAIL_MIN_OOF_TRAIN_ROWS
    ):
        heldout = [common[i] for i in valid]
        result.append(
            {
                key: (
                    [i for day, i in mapping.items() if day < heldout[0]],
                    [mapping[day] for day in heldout],
                )
                for key, mapping in maps.items()
            }
        )
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
) -> tuple[dict[str, object], dict[str, Any], dict[str, Array]]:
    """One search over all eligible folds; retain the winner's actual OOF predictions."""
    runtime.check()
    started = time.monotonic()
    folds = date_folds(cases, cutoff) if folds is None else folds
    record: dict[str, Any] = {
        "role": role,
        "cutoff": cutoff,
        "objective": objective,
        "alpha": alpha,
        "cv_splits": CV_SPLITS,
        "cv_kind": "blocked_expanding",
        "scored_fold_count": len(folds),
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
        or not folds
        or any(
            len(train) < ML_TAIL_MIN_OOF_TRAIN_ROWS
            for split in folds
            for train, _ in split.values()
        )
    ):
        record["failure_reason"] = "eight_case_common_validation_or_training_history_unavailable"
        record["elapsed_seconds"] = time.monotonic() - started
        return dict(record["parameters"]), record, {}

    best: tuple[float, int, int] | None = None
    best_oof: dict[str, Array] = {}
    incomplete = False
    runtime.selection_deadline = started + selection_seconds
    try:
        for index, (name, overrides) in enumerate(CANDIDATES):
            runtime.check()
            if time.monotonic() >= runtime.selection_deadline:
                incomplete = True
                break
            scores: dict[int, dict[str, list[tuple[int, float]]]] = {
                rounds: {key: [] for key in cases} for rounds in ROUND_CAPS
            }
            predictions = {
                rounds: {key: np.full(len(case["train"]), np.nan) for key, case in cases.items()}
                for rounds in ROUND_CAPS
            }
            detail: dict[str, Any] = {"name": name, "actual_trees": {}, "status": "complete"}
            try:
                for fold, split in enumerate(folds):
                    for key, case in cases.items():
                        train, valid = split[key]
                        target = targets[key]
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
                            predictions[rounds][key][valid] = prediction
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
                    len(values) == len(folds) and all(np.isfinite(loss) for _, loss in values)
                    for values in per_case.values()
                )
                pooled = {
                    key: float(sum(n * loss for n, loss in values) / sum(n for n, _ in values))
                    if len(values) == len(folds) and all(np.isfinite(loss) for _, loss in values)
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
                        best_oof = predictions[rounds]
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
    return dict(record["parameters"]), record, best_oof


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
) -> dict[str, dict[str, Any]]:
    """Select once on D; keep OOF predictions and refit on all finite target history."""
    cutoff = min(str(case["future"][0]["forecast_date"]) for case in cases.values())
    folds = date_folds(cases, cutoff) if folds is None else folds
    params, record, oof = select_parameters(
        cases,
        targets,
        role=role,
        objective=objective,
        alpha=alpha,
        cutoff=cutoff,
        runtime=runtime,
        folds=folds,
    )
    results: dict[str, dict[str, Any]] = {}
    record["fits"] = []
    for key, case in cases.items():
        runtime.check()
        started = time.monotonic()
        indices = _eligible(case, targets[key], cutoff)
        result: dict[str, Any] = {
            "fitted": np.full(len(case["train"]), np.nan),
            "oof": oof.get(key, np.full(len(case["train"]), np.nan)),
            "oof_warmup_rows": folds[0][key][1][0] if folds else len(case["train"]),
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
                raise PipelineRunError("unavailable_oof_standardization_insufficient_sample")
            if key not in oof:
                # Existing fixed-parameter fallback still needs genuine held-out predictions.
                for fold, split in enumerate(folds):
                    train, valid = split[key]
                    eligible = [i for i in train if np.isfinite(targets[key][i])]
                    if len(eligible) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
                        raise PipelineRunError(
                            "unavailable_oof_standardization_insufficient_sample"
                        )
                    fold_model, _, active = _fit(
                        case,
                        targets[key],
                        eligible,
                        role=role,
                        objective=objective,
                        alpha=alpha,
                        label=f"cv:{fold}",
                        params=params,
                        runtime=runtime,
                    )
                    result["oof"][valid] = _predict_lgb_rows(
                        fold_model, [case["train"][i] for i in valid], active
                    )
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
        score_folds: list[Fold] | None = None,
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
            folds=folds if score_folds is None else score_folds,
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
        fit(role, y, objective, alpha)
    for recipe, (objective, transform, spread_objective) in BODY_RECIPES.items():
        if transform == "iqr":
            continue
        center_role = f"center:{objective}:{0.5 if objective == 'quantile' else None}"
        targets = {
            key: spread_target(y[key] - components[key][center_role]["oof"], transform)
            for key in cases
        }
        # Structural warm-up alone fixes the scoring roster, never candidate performance.
        spread_folds = [
            split
            for split in folds
            if all(
                sum(i >= components[key][center_role]["oof_warmup_rows"] for i in train)
                >= ML_TAIL_MIN_OOF_TRAIN_ROWS
                for key, (train, _) in split.items()
            )
        ]
        fit(
            f"spread:{recipe}",
            targets,
            spread_objective,
            None,
            score_folds=spread_folds,
        )
    fit("direct", y, "quantile", next(iter(cases.values()))["tail_level"])
    return components
