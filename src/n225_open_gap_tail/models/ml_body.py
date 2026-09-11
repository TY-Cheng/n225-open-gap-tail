"""Accepted nine-body experiment; fits are shared before any tail calibration.

Fits use decimal losses before each recipe's target transform. Public outputs
use decimal returns and keep original calibration-row positions, including unavailable predictions.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_IQR_CONSISTENCY_FACTOR,
    ML_TAIL_MAD_CONSISTENCY_FACTOR,
    ML_TAIL_MIN_OOF_TRAIN_ROWS,
    ML_TAIL_OOF_SPLITS,
    ML_TAIL_ROBUST_SCALE_FLOOR,
    ML_TAIL_SCALE_FLOOR,
    PipelineRunError,
)
from n225_open_gap_tail.models.ml_tail_oof import (
    _blocked_expanding_oof_folds,
    _fit_lgb_regression_model,
    _ml_tail_seed,
    _positive_scale,
    _predict_lgb_rows,
    _rearrange_quantile_predictions,
)

BODY_RECIPES = {
    "mean_log_abs": ("regression_l2", "log_abs", "regression_l2"),
    "median_mad": ("quantile", "mad", "regression_l1"),
    "median_iqr": ("quantile", "iqr", "quantile"),
    "huber_log_abs": ("huber", "log_abs", "regression_l2"),
    "fair_log_abs": ("fair", "log_abs", "regression_l2"),
    "mean_rms_l2": ("regression_l2", "rms", "regression_l2"),
    "mean_rms_poisson": ("regression_l2", "rms", "poisson"),
    "mean_rms_gamma": ("regression_l2", "rms", "gamma"),
    "mean_rms_tweedie": ("regression_l2", "rms", "tweedie"),
}
TAIL_METHODS = ("empirical", "plain_mle", "unibm")
TRAINING_MULTIPLIER = 1.0
Array = NDArray[np.float64]


def body_model_name(recipe: str, tail: str) -> str:
    if recipe not in BODY_RECIPES or tail not in TAIL_METHODS:
        raise ValueError(f"Unknown body/tail recipe: {recipe}/{tail}")
    if recipe == "mean_log_abs":
        return (
            "lightgbm_location_scale_empirical"
            if tail == "empirical"
            else f"lightgbm_standardized_loss_pot_gpd_{tail}"
        )
    suffix = "empirical" if tail == "empirical" else f"pot_gpd_{tail}"
    return f"lightgbm_{recipe}_{suffix}"


EXPERIMENT_MODEL_NAMES = (
    "lightgbm_direct_quantile",
    *(body_model_name(recipe, tail) for recipe in BODY_RECIPES for tail in TAIL_METHODS),
)


def _fit_component(
    rows: list[dict[str, Any]],
    target: Array,
    *,
    candidate_features: list[str],
    objective: str,
    alpha: float | None,
    seed_key: tuple[object, ...],
    lgb: Any,
    lgbm_params: Mapping[str, object] | None,
    folds: list[tuple[list[int], list[int]]],
) -> dict[str, Any]:
    """The scale learner sees only earlier available OOF-center residuals."""
    oof = np.full(len(rows), np.nan)

    def fit(indices: list[int], label: object) -> tuple[Any, dict[str, Any], list[str]]:
        return _fit_lgb_regression_model(
            lgb=lgb,
            rows=[rows[i] for i in indices],
            target=target[indices],
            candidate_features=candidate_features,
            objective=objective,
            alpha=alpha,
            random_state=_ml_tail_seed(*seed_key, label),
            lgbm_params=lgbm_params,
        )

    for fold_index, (train, valid) in enumerate(folds):
        eligible = [i for i in train if np.isfinite(target[i])]
        if len(eligible) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
            continue
        model, _, active = fit(eligible, fold_index)
        oof[valid] = _predict_lgb_rows(model, [rows[i] for i in valid], active)
    eligible = np.flatnonzero(np.isfinite(target)).tolist()
    if len(eligible) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
        raise PipelineRunError("unavailable_oof_standardization_insufficient_sample")
    model, gate, active = fit(eligible, "final")
    return {"model": model, "gate": gate, "active_features": active, "oof": oof}


def rms_scale(raw_second_moment: Array) -> Array:
    """Decimal squared-return input; nonfinite values remain unavailable."""
    return np.sqrt(_positive_scale(raw_second_moment, floor=ML_TAIL_ROBUST_SCALE_FLOOR**2))


def spread_target(residual: Array, transform: str) -> Array:
    if transform == "log_abs":
        return np.log(np.maximum(np.abs(residual), ML_TAIL_SCALE_FLOOR * TRAINING_MULTIPLIER))
    if transform == "rms":
        return residual**2
    return np.abs(residual)


def fit_body_recipes(
    train_rows: list[dict[str, Any]],
    *,
    candidate_features: list[str],
    information_set: str,
    tail_level: float,
    lgb: Any,
    lgbm_params: Mapping[str, object] | None = None,
    components: Mapping[str, dict[str, Any]] | None = None,
    calibration_kind: Literal["oof", "in_sample"] = "oof",
) -> Iterator[tuple[str, dict[str, Any]]]:
    """One refit's nine bodies; the five mean recipes reuse the same center object.

    A failed recipe is retained as unavailable. The cache lives only within this
    historical refit, so it cannot mix dates, information sets or loss signs.
    """
    y = np.array([float(row["realized_loss"]) for row in train_rows]) * TRAINING_MULTIPLIER
    if not np.all(np.isfinite(y)):
        raise ValueError("Body training rows require finite observed losses")
    if calibration_kind == "in_sample" and components is None:
        raise ValueError("In-sample calibration requires full-history fitted components")
    prediction_key = "fitted" if calibration_kind == "in_sample" else "oof"
    folds = (
        []
        if calibration_kind == "in_sample"
        else _blocked_expanding_oof_folds(
            len(train_rows), n_splits=ML_TAIL_OOF_SPLITS, min_train_rows=ML_TAIL_MIN_OOF_TRAIN_ROWS
        )
    )
    center_warmup = folds[0][1][0] if folds else len(train_rows)
    spread_warmup = next(
        (
            valid[0]
            for train, valid in folds
            if len(train) - center_warmup >= ML_TAIL_MIN_OOF_TRAIN_ROWS
        ),
        len(train_rows),
    )
    if calibration_kind == "in_sample":
        center_warmup = spread_warmup = 0
    oof_dates = [str(row["forecast_date"]) for row in train_rows]
    centers: dict[tuple[str, float | None], dict[str, Any]] = {}
    failures: dict[tuple[str, float | None], str] = {}

    def component(target: Array, objective: str, alpha: float | None, role: str) -> dict[str, Any]:
        if components is not None:
            result = components[role]
            if result.get("failure_reason"):
                raise PipelineRunError(result["failure_reason"])
            return result
        return _fit_component(
            train_rows,
            target,
            candidate_features=candidate_features,
            objective=objective,
            alpha=alpha,
            seed_key=(information_set, tail_level, role),
            lgb=lgb,
            lgbm_params=lgbm_params,
            folds=folds,
        )

    def center(objective: str, alpha: float | None = None) -> dict[str, Any]:
        key = (objective, alpha)
        if key in failures:
            raise PipelineRunError(failures[key])
        if key not in centers:
            try:
                centers[key] = component(y, objective, alpha, f"center:{objective}:{alpha}")
            except Exception as exc:
                failures[key] = str(exc)
                raise
        return centers[key]

    for recipe, (objective, transform, spread_objective) in BODY_RECIPES.items():
        try:
            central = center(objective, 0.5 if objective == "quantile" else None)
            mu = central[prediction_key]
            target = spread_target(y - mu, transform)
            smearing = None
            q25 = q75 = spread = None
            crossing = None
            if transform == "iqr":
                q25, q75 = center("quantile", 0.25), center("quantile", 0.75)
                low, mu, high, crossing = _rearrange_quantile_predictions(
                    q25[prediction_key], mu, q75[prediction_key]
                )
                raw_scale = (high - low) / (ML_TAIL_IQR_CONSISTENCY_FACTOR * TRAINING_MULTIPLIER)
                scale = _positive_scale(raw_scale, floor=ML_TAIL_ROBUST_SCALE_FLOOR)
            else:
                spread = component(target, spread_objective, None, f"spread:{recipe}")
                raw = spread[prediction_key]
                if transform == "log_abs":
                    valid = np.isfinite(target) & np.isfinite(raw)
                    with np.errstate(over="ignore", invalid="ignore"):
                        exp_residual = np.exp(target[valid] - raw[valid])
                    finite = exp_residual[np.isfinite(exp_residual)]
                    smearing = float(np.mean(finite)) if finite.size else np.nan
                    if not np.isfinite(smearing) or smearing <= 0:
                        raise PipelineRunError("unavailable_invalid_smearing_factor")
                    with np.errstate(over="ignore", invalid="ignore"):
                        raw_scale = np.exp(raw) * smearing / TRAINING_MULTIPLIER
                    scale = np.where(np.isfinite(raw_scale) & (raw_scale > 0), raw_scale, np.nan)
                elif transform == "mad":
                    raw_scale = raw * ML_TAIL_MAD_CONSISTENCY_FACTOR / TRAINING_MULTIPLIER
                    scale = _positive_scale(raw_scale, floor=ML_TAIL_ROBUST_SCALE_FLOOR)
                else:
                    raw_scale = raw / TRAINING_MULTIPLIER**2
                    scale = rms_scale(raw_scale)
            with np.errstate(divide="ignore", invalid="ignore"):
                standardized = ((y - mu) / TRAINING_MULTIPLIER) / scale
            standardized[~np.isfinite(standardized)] = np.nan
            if np.count_nonzero(np.isfinite(standardized)) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
                raise PipelineRunError(
                    f"unavailable_{calibration_kind}_standardization_insufficient_sample"
                )
            floor = (
                ML_TAIL_ROBUST_SCALE_FLOOR**2 if transform == "rms" else ML_TAIL_ROBUST_SCALE_FLOOR
            )
            yield (
                recipe,
                {
                    "fit_status": "ok",
                    "calibration_kind": calibration_kind,
                    "recipe": recipe,
                    "center": central,
                    "spread": spread,
                    "q25": q25,
                    "q75": q75,
                    "smearing_factor": smearing,
                    "scale_transform": transform,
                    "training_multiplier": TRAINING_MULTIPLIER,
                    "center_objective": objective,
                    "spread_objective": spread_objective,
                    f"mu_{calibration_kind}": mu / TRAINING_MULTIPLIER,
                    f"scale_{calibration_kind}": scale,
                    f"raw_scale_{calibration_kind}": raw_scale,
                    f"scale_target_{calibration_kind}_training_units": None
                    if transform == "iqr"
                    else target,
                    "raw_scale_units": "decimal_return_squared"
                    if transform == "rms"
                    else "decimal_return",
                    "scale_floor": None if transform == "log_abs" else ML_TAIL_ROBUST_SCALE_FLOOR,
                    "log_abs_epsilon": ML_TAIL_SCALE_FLOOR if transform == "log_abs" else None,
                    "standardized_losses": standardized,
                    f"{calibration_kind}_warmup_rows": center_warmup
                    if transform == "iqr"
                    else spread_warmup,
                    f"{calibration_kind}_dates": oof_dates,
                    "quantile_crossing_rate": crossing,
                    "scale_nonpositive_count": int(
                        np.sum(np.isfinite(raw_scale) & (raw_scale <= 0))
                    ),
                    "scale_floor_count": int(np.sum(np.isfinite(raw_scale) & (raw_scale < floor)))
                    if transform != "log_abs"
                    else 0,
                    "train_n": len(train_rows),
                    "train_start": train_rows[0]["forecast_date"],
                    "train_end": train_rows[-1]["forecast_date"],
                },
            )
        except Exception as exc:
            if components is not None and not isinstance(exc, PipelineRunError):
                raise
            yield recipe, {"fit_status": "unavailable_body_fit", "failure_reason": str(exc)}


def predict_body(body: Mapping[str, Any], rows: list[dict[str, Any]]) -> dict[str, Array]:
    def predict(component: Mapping[str, Any]) -> Array:
        return _predict_lgb_rows(component["model"], rows, component["active_features"])

    mu = predict(body["center"])
    transform = body["scale_transform"]
    if transform == "iqr":
        low, mu, high, _ = _rearrange_quantile_predictions(
            predict(body["q25"]), mu, predict(body["q75"])
        )
        raw = (high - low) / (ML_TAIL_IQR_CONSISTENCY_FACTOR * TRAINING_MULTIPLIER)
        scale = _positive_scale(raw, floor=ML_TAIL_ROBUST_SCALE_FLOOR)
    else:
        raw = predict(body["spread"])
        if transform == "rms":
            raw = raw / TRAINING_MULTIPLIER**2
            scale = rms_scale(raw)
        elif transform == "mad":
            raw = raw * ML_TAIL_MAD_CONSISTENCY_FACTOR / TRAINING_MULTIPLIER
            scale = _positive_scale(raw, floor=ML_TAIL_ROBUST_SCALE_FLOOR)
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                raw = np.exp(raw) * body["smearing_factor"] / TRAINING_MULTIPLIER
            scale = np.where(np.isfinite(raw) & (raw > 0), raw, np.nan)
    floor = ML_TAIL_ROBUST_SCALE_FLOOR**2 if transform == "rms" else ML_TAIL_ROBUST_SCALE_FLOOR
    return {
        "location": mu / TRAINING_MULTIPLIER,
        "scale": scale,
        "raw_scale": raw,
        "scale_nonpositive": np.isfinite(raw) & (raw <= 0),
        "scale_floor_hit": np.isfinite(raw) & (raw < floor)
        if transform != "log_abs"
        else np.zeros(len(rows), dtype=bool),
    }
