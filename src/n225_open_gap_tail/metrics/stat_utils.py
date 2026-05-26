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


def kupiec_pof_test(*, breaches: np.ndarray, expected_probability: float) -> dict[str, object]:
    n = int(breaches.size)
    x = int(np.sum(breaches))
    if n == 0 or expected_probability <= 0.0 or expected_probability >= 1.0:
        return {"status": "unavailable_invalid_input", "lr_stat": None, "pvalue": None}
    log_likelihood_null = x * math.log(expected_probability) + (n - x) * math.log(
        1.0 - expected_probability
    )
    log_likelihood_alt = _bernoulli_log_likelihood(x, n - x)
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
    unrestricted = _bernoulli_log_likelihood(n01, n00) + _bernoulli_log_likelihood(n11, n10)
    restricted = _bernoulli_log_likelihood(n01 + n11, n00 + n10)
    lr_stat = -2.0 * (restricted - unrestricted)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
    }


def _bernoulli_log_likelihood(successes: int, failures: int) -> float:
    total = successes + failures
    if total == 0:
        return 0.0
    probability = successes / total
    value = 0.0
    if successes:
        value += successes * math.log(probability)
    if failures:
        value += failures * math.log(1.0 - probability)
    return float(value)
