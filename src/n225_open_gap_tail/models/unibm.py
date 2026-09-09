"""Public strict-FGLS adapter for the new experiment, never an OLS fallback."""

from __future__ import annotations

import importlib
from dataclasses import replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from n225_open_gap_tail.models.benchmark import (
    UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT,
    UNIBM_EVI_MIN_FINITE_VALUES,
    UNIBM_EVI_MIN_PLATEAU_POINTS,
)


def estimate_public_unibm(sample: NDArray[np.float64], *, warmup_rows: int = 0) -> dict[str, Any]:
    """Omit only declared structural warm-up, retaining every later position.

    Unavailable bootstrap covariance is reported, not repaired by dropping
    observations, changing the estimator or perturbing the sample. The caller
    derives warmup_rows from the OOF schedule, not from the first finite value.
    """
    values = np.asarray(sample, dtype=float)
    if values.ndim != 1:
        raise ValueError("UniBM input must be a one-dimensional residual timeline")
    if (
        isinstance(warmup_rows, bool)
        or not isinstance(warmup_rows, int)
        or not 0 <= warmup_rows <= len(values)
    ):
        raise ValueError("warmup_rows must be an integer within the supplied timeline")
    if not np.isnan(values[:warmup_rows]).all():
        raise ValueError("Structural warm-up may contain only undefined (NaN) OOF residuals")
    input_n_obs = len(values)
    values = values[warmup_rows:]
    finite = np.isfinite(values)
    base: dict[str, Any] = {
        "primary_estimator": "public_unibm_quantile_strict_fgls",
        "regression_policy": "FGLS",
        "n_obs": len(values),
        "input_n_obs": input_n_obs,
        "structural_warmup_rows": warmup_rows,
        "finite_observations": int(finite.sum()),
        "missing_observations": int((~finite).sum()),
        "first_finite_position": warmup_rows + int(np.flatnonzero(finite)[0])
        if finite.any()
        else None,
        "last_finite_position": warmup_rows + int(np.flatnonzero(finite)[-1])
        if finite.any()
        else None,
        "position_policy": "omit_declared_warmup_preserve_remaining_positions",
        "quantile": 0.5,
        "sliding": True,
        "covariance_shrinkage": 0.37,
        "bootstrap_reps_policy": "adaptive",
        "random_state": 0,
    }
    try:
        public = importlib.import_module("unibm.evi")
        base["source_path"] = public.__file__
        if finite.sum() < UNIBM_EVI_MIN_FINITE_VALUES:
            raise ValueError("insufficient finite residuals")
        grid = public.generate_block_sizes(len(values))
        curve = public.block_summary_curve(
            values, grid, target="quantile", quantile=0.5, sliding=True
        )
        # Retain the existing minimum of 20 maxima per plateau point.
        curve = replace(
            curve,
            positive_mask=curve.positive_mask
            & (curve.counts >= UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT),
        )
        base.update(
            block_sizes=curve.block_sizes.tolist(),
            block_counts=curve.counts.tolist(),
            min_block_size=int(curve.block_sizes[0]),
            max_block_size=int(curve.block_sizes[-1]),
        )
        if curve.positive_mask.sum() < UNIBM_EVI_MIN_PLATEAU_POINTS:
            raise ValueError("insufficient eligible block-summary points")
        fit = public.estimate_evi_quantile(
            values,
            regression="FGLS",
            quantile=0.5,
            sliding=True,
            curve=curve,
            block_sizes=curve.block_sizes,
            plateau_points=UNIBM_EVI_MIN_PLATEAU_POINTS,
            trim_fraction=0.15,
            curvature_penalty=2.0,
            covariance_shrinkage=0.37,
            bootstrap_reps="adaptive",
            super_block_size=None,
            random_state=0,
        )
        if fit.regression != "FGLS" or not np.isfinite(fit.slope):
            raise ValueError("strict FGLS did not produce a finite slope")
        return {
            **base,
            "status": "ok",
            "xi_evi_anchor": float(fit.slope),
            "standard_error": fit.standard_error,
            "confidence_interval": fit.confidence_interval,
            "regression": fit.regression,
            "ci_variant": fit.ci_variant,
            "plateau_point_count": int(fit.plateau_mask.sum()),
            "plateau_block_sizes": fit.plateau_block_sizes.tolist(),
            "plateau_block_counts": fit.counts[fit.plateau_mask].tolist(),
            "bootstrap_reps": fit.bootstrap_reps_used,
            **{
                name: getattr(fit, name)
                for name in (
                    "bootstrap_reps_requested",
                    "bootstrap_reps_used",
                    "bootstrap_reps_policy",
                    "bootstrap_precision_met",
                    "bootstrap_mcse",
                    "bootstrap_mcse_max_ratio",
                    "bootstrap_mcse_targets",
                    "bootstrap_block_length_policy",
                    "bootstrap_block_length",
                    "covariance_shrinkage_policy",
                    "covariance_condition_number_raw",
                    "covariance_condition_number_regularized",
                )
            },
        }
    except Exception as exc:
        return {
            **base,
            "status": "unavailable_public_unibm",
            "xi_evi_anchor": None,
            "failure_reason": f"{type(exc).__name__}: {exc}",
        }
