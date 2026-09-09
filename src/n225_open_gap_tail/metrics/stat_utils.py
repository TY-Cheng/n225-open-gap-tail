from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

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
    if not valid or es_forecast <= 0 or not math.isfinite(loss) or not 0 < tail_level < 1:
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


def forecast_eligible(row: Mapping[str, object], *, score: str = "var") -> bool:
    """Numerical eligibility, including recoverable ES-only legacy failures."""
    status = row.get("fit_status")
    reason = row.get("invalid_reason") or row.get("failure_reason")
    es_only_failure = reason in {
        "invalid_nonpositive_es",
        "invalid_es_below_var",
        "invalid_nonfinite_forecast",
    }
    if status != "ok" and not (status == "invalid_forecast" and es_only_failure):
        return False
    if row.get("is_valid_forecast") is False and not es_only_failure:
        return False
    loss = _optional_float(row.get("realized_loss"))
    var = _optional_float(row.get("var_forecast"))
    level = _optional_float(row.get("tail_level"))
    if loss is None or var is None or level is None or not 0 < level < 1:
        return False
    if not math.isfinite(loss) or not math.isfinite(var):
        return False
    if score == "var":
        return True
    es = _optional_float(row.get("es_forecast"))
    if es is None or not validate_forecast_values(var, es)[0]:
        return False
    if score == "joint":
        return True
    return score == "fz0" and math.isfinite(fz_loss(loss, var, es, level))


def valid_forecast_rows(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in forecasts if forecast_eligible(row)]


def index_forecast_sessions(
    forecasts: list[dict[str, object]],
    *,
    session_dates: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Attach the unfiltered target axis before selecting valid forecasts."""
    dates = sorted(
        set(
            session_dates
            if session_dates is not None
            else (
                str(row["forecast_date"])
                for row in forecasts
                if row.get("forecast_date") is not None
            )
        )
    )
    positions = {day: index for index, day in enumerate(dates)}
    basis = "target_panel_sessions" if session_dates is not None else "forecast_record_date_union"
    return [
        {
            **row,
            "target_session_index": (
                positions.get(str(row.get("forecast_date")))
                if session_dates is not None
                else row.get("target_session_index", positions.get(str(row.get("forecast_date"))))
            ),
            "session_axis": basis if session_dates is not None else row.get("session_axis", basis),
        }
        for row in forecasts
    ]


def moving_block_one_sided_pvalue(
    values: np.ndarray,
    *,
    observed_mean: float | None,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
    session_indices: Sequence[int | None] | None = None,
) -> float | None:
    if observed_mean is None or values.size < 2 or not np.all(np.isfinite(values)):
        return None
    centered = values - float(np.mean(values))
    n = int(centered.size)
    if block_length < 1 or reps < 1:
        raise ValueError("Positive block length and replication count required")
    weights = np.ones(n, dtype=int)
    if session_indices is not None:
        if len(session_indices) != n or any(value is None for value in session_indices):
            return None
        indices = np.asarray(session_indices, dtype=int)
        if np.any(np.diff(indices) <= 0):
            return None
        offsets = indices - indices[0]
        n = int(offsets[-1]) + 1
        grid = np.zeros(n)
        weights = np.zeros(n, dtype=int)
        grid[offsets] = centered
        weights[offsets] = 1
        centered = grid
    # Circular blocks on the full target axis resample (mask * centered loss, mask).
    # Missing scores carry zero weight, not an imputed loss; isolated observations
    # remain eligible. The ratio targets the observed-date mean, not missing outcomes.
    chosen = rng.choice(np.arange(n), size=(reps, math.ceil(n / block_length)))
    positions = (chosen[:, :, None] + np.arange(block_length)) % n
    positions = positions.reshape(reps, -1)[:, :n]
    counts = np.sum(weights[positions], axis=1)
    usable = counts > 0
    if not np.any(usable):
        return None
    means = np.sum(centered[positions[usable]], axis=1) / counts[usable]
    count = int(np.sum(means <= observed_mean))
    return float((count + 1) / (int(np.sum(usable)) + 1))


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


def christoffersen_independence_test(
    *,
    breaches: np.ndarray,
    session_indices: Sequence[int | None] | None = None,
) -> dict[str, object]:
    values = [bool(value) for value in breaches.tolist()]
    if session_indices is not None and (
        len(session_indices) != len(values) or any(value is None for value in session_indices)
    ):
        return {"status": "unavailable_session_index", "lr_stat": None, "pvalue": None}
    if len(values) < 2:
        return {"status": "unavailable_insufficient_oos", "lr_stat": None, "pvalue": None}
    n00 = n01 = n10 = n11 = 0
    skipped = 0
    indices = np.asarray(session_indices, dtype=int) if session_indices is not None else None
    for index, (previous, current) in enumerate(zip(values[:-1], values[1:], strict=True)):
        if indices is not None and indices[index + 1] != indices[index] + 1:
            skipped += 1
            continue
        if not previous and not current:
            n00 += 1
        elif not previous and current:
            n01 += 1
        elif previous and not current:
            n10 += 1
        else:
            n11 += 1
    counts = {
        "n00": n00,
        "n01": n01,
        "n10": n10,
        "n11": n11,
        "transition_count": n00 + n01 + n10 + n11,
        "skipped_transitions": skipped,
    }
    if counts["transition_count"] == 0:
        return {
            "status": "unavailable_no_adjacent_sessions",
            "lr_stat": None,
            "pvalue": None,
            **counts,
        }
    unrestricted = _bernoulli_log_likelihood(n01, n00) + _bernoulli_log_likelihood(n11, n10)
    restricted = _bernoulli_log_likelihood(n01 + n11, n00 + n10)
    lr_stat = -2.0 * (restricted - unrestricted)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
        **counts,
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
