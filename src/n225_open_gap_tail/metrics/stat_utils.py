from __future__ import annotations

import math

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from n225_open_gap_tail.config.runtime import (
    _optional_float,
    validate_forecast_values,
)


def _safe_mean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.mean(finite))


def _fmt(value: object) -> str:
    parsed = _optional_float(value)
    return "" if parsed is None else f"{parsed:.6f}"


def quantile_loss(loss: float, var_forecast: float, tail_level: float) -> float:
    alpha = 1.0 - tail_level
    indicator = 1.0 if loss > var_forecast else 0.0
    return float((indicator - alpha) * (loss - var_forecast))


def fz_loss(loss: float, var_forecast: float, es_forecast: float, tail_level: float) -> float:
    valid, _ = validate_forecast_values(var_forecast, es_forecast)
    if not valid or es_forecast <= 0:
        return math.nan
    alpha = 1.0 - tail_level
    x = -loss
    var_return = -var_forecast
    es_return = -es_forecast
    indicator = 1.0 if x <= var_return else 0.0
    return float(
        (1.0 / (alpha * es_return)) * indicator * (x - var_return)
        + var_return / es_return
        + math.log(-es_return)
        - 1.0
    )


def valid_forecast_rows(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in forecasts
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True
    ]


def moving_block_one_sided_pvalue(
    values: np.ndarray,
    *,
    observed_mean: float | None,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> float | None:
    if observed_mean is None or values.size < 2:
        return None
    centered = values - float(np.mean(values))
    n = int(centered.size)
    starts = np.arange(n)
    count = 0
    for _ in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            start = int(rng.choice(starts))
            for offset in range(block_length):
                sample.append(float(centered[(start + offset) % n]))
                if len(sample) == n:
                    break
        if float(np.mean(np.array(sample, dtype=float))) <= observed_mean:
            count += 1
    return float((count + 1) / (reps + 1))


def moving_block_bootstrap_mean_matrix(
    matrix: np.ndarray,
    *,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    n, m = matrix.shape
    starts = np.arange(n)
    output = np.empty((reps, m), dtype=float)
    for rep in range(reps):
        indices: list[int] = []
        while len(indices) < n:
            start = int(rng.choice(starts))
            for offset in range(block_length):
                indices.append((start + offset) % n)
                if len(indices) == n:
                    break
        output[rep, :] = np.mean(matrix[indices, :], axis=0)
    return output


def hln_tmax_mcs_step(
    losses: np.ndarray,
    *,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    if losses.ndim != 2 or min(losses.shape) < 2:
        return {"tmax_stat": None, "pvalue": None, "t_values": np.array([])}
    centered_against_cross_section = losses - np.mean(losses, axis=1, keepdims=True)
    dbar = np.mean(centered_against_cross_section, axis=0)
    null_centered = centered_against_cross_section - dbar
    bootstrap_means = moving_block_bootstrap_mean_matrix(
        null_centered,
        reps=reps,
        block_length=block_length,
        rng=rng,
    )
    se = np.std(bootstrap_means, axis=0, ddof=1)
    tiny_se = se <= 1e-12
    t_values = np.divide(dbar, se, out=np.zeros_like(dbar), where=~tiny_se)
    t_values = np.where(tiny_se & (dbar > 1e-12), 1e12, t_values)
    t_values = np.where(tiny_se & (dbar < -1e-12), -1e12, t_values)
    if np.all(np.isnan(t_values)):
        return {"tmax_stat": None, "pvalue": None, "t_values": t_values}
    tmax_stat = float(np.nanmax(t_values))
    bootstrap_scaled = np.divide(
        bootstrap_means,
        se,
        out=np.zeros_like(bootstrap_means),
        where=~tiny_se,
    )
    bootstrap_tmax = np.nanmax(bootstrap_scaled, axis=1)
    bootstrap_tmax = bootstrap_tmax[np.isfinite(bootstrap_tmax)]
    if bootstrap_tmax.size == 0:
        return {"tmax_stat": tmax_stat, "pvalue": None, "t_values": t_values}
    pvalue = float((np.sum(bootstrap_tmax >= tmax_stat) + 1) / (bootstrap_tmax.size + 1))
    return {"tmax_stat": tmax_stat, "pvalue": pvalue, "t_values": t_values}


def kupiec_pof_test(*, breaches: np.ndarray, expected_probability: float) -> dict[str, object]:
    n = int(breaches.size)
    x = int(np.sum(breaches))
    if n == 0 or expected_probability <= 0.0 or expected_probability >= 1.0:
        return {"status": "unavailable_invalid_input", "lr_stat": None, "pvalue": None}
    observed = x / n
    if observed in {0.0, 1.0}:
        return {
            "status": "unavailable_boundary_exceedance_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    log_likelihood_null = x * math.log(expected_probability) + (n - x) * math.log(
        1.0 - expected_probability
    )
    log_likelihood_alt = x * math.log(observed) + (n - x) * math.log(1.0 - observed)
    lr_stat = -2.0 * (log_likelihood_null - log_likelihood_alt)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
    }


def christoffersen_independence_test(*, breaches: np.ndarray) -> dict[str, object]:
    values = [bool(value) for value in breaches.tolist()]
    if len(values) < 2:
        return {"status": "unavailable_insufficient_oos", "lr_stat": None, "pvalue": None}
    n00 = n01 = n10 = n11 = 0
    for previous, current in zip(values[:-1], values[1:], strict=True):
        if not previous and not current:
            n00 += 1
        elif not previous and current:
            n01 += 1
        elif previous and not current:
            n10 += 1
        else:
            n11 += 1
    if min(n00 + n01, n10 + n11, n00 + n10, n01 + n11) == 0:
        return {
            "status": "unavailable_boundary_transition_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    if any(value in {0.0, 1.0} for value in (pi01, pi11, pi)):
        return {
            "status": "unavailable_boundary_transition_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    unrestricted = (
        n00 * math.log(1.0 - pi01)
        + n01 * math.log(pi01)
        + n10 * math.log(1.0 - pi11)
        + n11 * math.log(pi11)
    )
    restricted = (n00 + n10) * math.log(1.0 - pi) + (n01 + n11) * math.log(pi)
    lr_stat = -2.0 * (restricted - unrestricted)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
    }
