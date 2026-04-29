# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,PLR0912,PLR0913,PLR0915,UP035
from __future__ import annotations

from scipy import optimize  # type: ignore[import-untyped]

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def _recursive_var_path(
    *,
    train: np.ndarray,
    params: np.ndarray,
    variant: str,
    has_gap: bool,
) -> tuple[np.ndarray, float]:
    finite = train[np.isfinite(train)]
    if finite.size == 0:
        raise PipelineRunError("recursive advanced model has no finite training losses")
    q = max(float(np.quantile(finite, 0.95)), 1e-12)
    forecasts: list[float] = []
    for y in finite:
        forecasts.append(float(q))
        q = _recursive_next_var(q=q, y=float(y), params=params, variant=variant, has_gap=has_gap)
    return np.asarray(forecasts, dtype=float), float(q)


def _recursive_next_var(
    *,
    q: float,
    y: float,
    params: np.ndarray,
    variant: str,
    has_gap: bool,
) -> float:
    core = params[:-1] if has_gap else params
    if variant == "asymmetric_slope":
        beta0, beta1, beta2, beta3 = [float(value) for value in core[:4]]
        next_q = beta0 + beta1 * q + beta2 * max(y, 0.0) + beta3 * max(-y, 0.0)
    else:
        beta0, beta1, beta2 = [float(value) for value in core[:3]]
        next_q = beta0 + beta1 * q + beta2 * abs(y)
    return float(max(next_q, 1e-12))


def _recursive_params_valid(params: np.ndarray, *, variant: str, has_gap: bool) -> bool:
    if not np.all(np.isfinite(params)):
        return False
    core = params[:-1] if has_gap else params
    expected = 4 if variant == "asymmetric_slope" else 3
    if core.size != expected:
        return False
    beta0 = float(core[0])
    beta1 = float(core[1])
    shocks = core[2:]
    if beta0 < 0.0 or not 0.0 <= beta1 < 0.999:
        return False
    if np.any(shocks < 0.0) or np.any(shocks > 5.0):
        return False
    return not (has_gap and not math.isfinite(float(params[-1])))


def _recursive_initial_params(
    *,
    train: np.ndarray,
    model_name: str,
    variant: str,
    tail_level: float,
    previous_params: np.ndarray | None,
) -> tuple[np.ndarray, str]:
    if previous_params is not None and np.all(np.isfinite(previous_params)):
        return previous_params.astype(float, copy=True), "previous_month_warm_start"
    finite = train[np.isfinite(train)]
    base_var = max(float(np.quantile(finite, tail_level)), 1e-6)
    candidates: list[np.ndarray] = []
    for persistence in (0.70, 0.90, 0.95):
        for shock in (0.02, 0.05, 0.10, 0.20):
            intercept = max((1.0 - persistence - shock) * base_var, 1e-8)
            if variant == "asymmetric_slope":
                core = np.asarray([intercept, persistence, shock, shock * 0.25], dtype=float)
            else:
                core = np.asarray([intercept, persistence, shock], dtype=float)
            if _uses_positive_gap(model_name):
                gap = max(static_empirical_es(finite, base_var) - base_var, 1e-5)
                core = np.append(core, math.log(gap))
            candidates.append(core)
    objective_kind = _objective_kind(model_name)
    best = min(
        candidates,
        key=lambda params: _coarse_initialization_score(
            train=finite,
            params=params,
            model_name=model_name,
            variant=variant,
            tail_level=tail_level,
            objective_kind=objective_kind,
        ),
    )
    return best, "coarse_economic_grid"


def _coarse_initialization_score(
    *,
    train: np.ndarray,
    params: np.ndarray,
    model_name: str,
    variant: str,
    tail_level: float,
    objective_kind: str,
) -> float:
    var_path, _ = _recursive_var_path(
        train=train,
        params=params,
        variant=variant,
        has_gap=_uses_positive_gap(model_name),
    )
    if objective_kind in {"fz", "ald"}:
        return _fz_objective(
            train,
            var_path,
            var_path + _positive_gap_from_params(params),
            tail_level,
        )
    if objective_kind == "expectile":
        return float(np.mean((train - var_path) ** 2))
    return _quantile_objective(train, var_path, tail_level)


def _run_derivative_free_optimizer(
    *,
    objective: object,
    x0: np.ndarray,
    model_name: str,
    tail_level: float,
    forecast_date: str,
) -> dict[str, object]:
    best_params = np.asarray(x0, dtype=float)
    best_value = float(cast(Any, objective)(best_params))
    best_result: object | None = None
    rng = np.random.default_rng(_stable_optimizer_seed(model_name, tail_level, forecast_date))
    restart_count = 0
    retry_count = 0
    methods = ("Nelder-Mead", "Powell")
    starts = [best_params]
    for _ in range(ADVANCED_OPTIMIZER_MAX_RESTARTS):
        scale = ADVANCED_OPTIMIZER_JITTER_FRACTION * np.abs(best_params)
        scale = scale + ADVANCED_OPTIMIZER_JITTER_FLOOR
        starts.append(best_params + rng.normal(0.0, scale, size=best_params.shape))
    for start_index, start in enumerate(starts):
        if start_index:
            restart_count += 1
        for method in methods:
            retry_count += int(method != methods[0] or start_index > 0)
            try:
                options = {"maxiter": 80, "disp": False}
                if method == "Nelder-Mead":
                    options.update({"xatol": 1e-6, "fatol": 1e-7})
                elif method == "Powell":
                    options.update({"xtol": 1e-6, "ftol": 1e-7})
                result = optimize.minimize(
                    cast(Any, objective),
                    np.asarray(start, dtype=float),
                    method=method,
                    options=options,
                )
            except Exception:
                continue
            value = float(result.fun) if math.isfinite(float(result.fun)) else 1e12
            if value + 1e-10 < best_value:
                best_value = value
                best_params = np.asarray(result.x, dtype=float)
                best_result = result
        if best_result is not None and start_index == 0:
            break
    convergence_code = int(getattr(best_result, "status", 0 if math.isfinite(best_value) else 1))
    return {
        "params": best_params,
        "optimizer_method": str(getattr(best_result, "method", "derivative_free")),
        "optimizer_status": "converged"
        if best_result is None or bool(getattr(best_result, "success", True))
        else "warning",
        "convergence_code": convergence_code,
        "objective_value": best_value,
        "retry_count": retry_count,
        "restart_count": restart_count,
    }


def _empirical_es_multiplier(
    *,
    train_losses: np.ndarray,
    train_var_forecasts: np.ndarray,
) -> dict[str, object]:
    valid_var = np.isfinite(train_var_forecasts) & (train_var_forecasts > 1e-12)
    mask = np.isfinite(train_losses) & valid_var & (train_losses > train_var_forecasts)
    if int(mask.sum()) < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        return {
            "status": "unavailable_empirical_es_companion_insufficient_exceedances",
            "es_multiplier": None,
            "es_multiplier_exceedance_count": int(mask.sum()),
            "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
        }
    ratios = train_losses[mask] / train_var_forecasts[mask]
    finite = ratios[np.isfinite(ratios)]
    if finite.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        return {
            "status": "unavailable_empirical_es_companion_invalid_multiplier",
            "es_multiplier": None,
            "es_multiplier_exceedance_count": int(finite.size),
            "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
        }
    multiplier = float(max(1.0, np.mean(finite)))
    return {
        "status": "ok",
        "es_multiplier": multiplier,
        "es_multiplier_exceedance_count": int(finite.size),
        "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
    }


def _gas_initial_params(
    train: np.ndarray,
    *,
    previous_params: np.ndarray | None,
) -> tuple[np.ndarray, str]:
    if previous_params is not None and np.all(np.isfinite(previous_params)):
        return previous_params.astype(float, copy=True), "previous_month_warm_start"
    finite = train[np.isfinite(train)]
    mu = float(np.mean(finite))
    sigma = max(float(np.std(finite, ddof=1)), 1e-6)
    persistence = 0.90
    return (
        np.asarray([(1.0 - persistence) * math.log(sigma), 0.10, persistence, mu], dtype=float),
        "coarse_economic_grid",
    )


def _gas_params_valid(params: np.ndarray) -> bool:
    if params.size != 4 or not np.all(np.isfinite(params)):
        return False
    _, score_coef, persistence, _ = [float(value) for value in params]
    return -2.0 <= score_coef <= 2.0 and 0.0 <= persistence < 0.999


def _gas_filter_path(
    *,
    train: np.ndarray,
    params: np.ndarray,
    nu: float,
) -> dict[str, object] | None:
    finite = train[np.isfinite(train)]
    if finite.size == 0:
        return None
    log_sigma = math.log(max(float(np.std(finite, ddof=1)), 1e-6))
    log_sigmas: list[float] = []
    for y in finite:
        if not math.isfinite(log_sigma) or abs(log_sigma) > 25.0:
            return None
        log_sigmas.append(float(log_sigma))
        log_sigma = _gas_next_log_sigma(y=float(y), log_sigma=log_sigma, params=params, nu=nu)
    return {"log_sigmas": np.asarray(log_sigmas, dtype=float), "next_log_sigma": log_sigma}


def _gas_next_log_sigma(
    *,
    y: float,
    log_sigma: float,
    params: np.ndarray,
    nu: float,
) -> float:
    omega, score_coef, persistence, mu = [float(value) for value in params]
    sigma = math.exp(log_sigma)
    if not math.isfinite(sigma) or sigma <= 0.0 or not math.isfinite(nu) or nu <= 2.0:
        raise PipelineRunError("invalid GAS scale or nu")
    z = (y - mu) / sigma
    score = ((nu + 1.0) * z * z / (nu + z * z)) - 1.0
    next_state = omega + score_coef * score + persistence * log_sigma
    if not math.isfinite(next_state) or abs(next_state) > 25.0:
        raise PipelineRunError("nonfinite_unit_scaled_score")
    return float(next_state)


def _profile_gas_nu(train: np.ndarray) -> float:
    finite = train[np.isfinite(train)]
    if finite.size < 5:
        return float(GAS_NU_GRID[0])
    mu = float(np.mean(finite))
    scale = max(float(np.std(finite, ddof=1)), 1e-6)
    best_nu = float(GAS_NU_GRID[0])
    best_ll = -math.inf
    for nu in GAS_NU_GRID:
        z = (finite - mu) / scale
        ll = stats.t.logpdf(z, df=float(nu)) - math.log(scale)
        value = float(np.sum(ll[np.isfinite(ll)]))
        if value > best_ll:
            best_ll = value
            best_nu = float(nu)
    return best_nu


def _student_t_standardized_var_es(*, nu: float, tail_level: float) -> tuple[float, float]:
    alpha = 1.0 - tail_level
    q = float(stats.t.ppf(tail_level, df=nu))
    pdf = float(stats.t.pdf(q, df=nu))
    if nu <= 1.0:
        return q, q
    es = ((nu + q * q) / (nu - 1.0)) * pdf / alpha
    return float(q), float(max(q, es))


def _advanced_pot_gpd_standardized_tail(
    *,
    standardized_losses: np.ndarray,
    tail_level: float,
    threshold_quantile: float = EVT_THRESHOLD_QUANTILE,
) -> dict[str, object]:
    values = standardized_losses[np.isfinite(standardized_losses)]
    if values.size < DEFAULT_MIN_TRAIN_ROWS:
        raise PipelineRunError("GAS-POT calibration has insufficient standardized losses")
    threshold = float(np.quantile(values, threshold_quantile))
    excesses = values[values > threshold] - threshold
    if excesses.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        raise PipelineRunError(f"GAS-POT has insufficient exceedances: {excesses.size}")
    shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
    shape = float(shape)
    scale = float(max(scale, 1e-12))
    try:
        _, loc_hat, _ = stats.genpareto.fit(excesses)
        loc_hat = float(loc_hat)
    except Exception:
        loc_hat = math.nan
    loc_status = (
        "gpd_fixed_loc_diagnostic_warning"
        if math.isfinite(loc_hat) and abs(loc_hat) > 0.25 * scale
        else "ok"
    )
    if shape >= 1.0:
        raise PipelineRunError(f"GAS-POT shape >= 1 has infinite ES: {shape}")
    exceedance_probability = excesses.size / values.size
    target_tail_probability = max(1.0 - tail_level, 1e-12)
    ratio = max(exceedance_probability / target_tail_probability, 1.0)
    if abs(shape) < 1e-8:
        var_z = threshold + scale * math.log(ratio)
    else:
        var_z = threshold + scale * (ratio**shape - 1.0) / shape
    es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "evt_shape": shape,
        "evt_scale": scale,
        "gpd_unconstrained_loc_hat": loc_hat,
        "gpd_fixed_loc_diagnostic_status": loc_status,
    }


def _quantile_objective(train: np.ndarray, var_path: np.ndarray, tail_level: float) -> float:
    alpha = 1.0 - tail_level
    indicator = (train > var_path).astype(float)
    return float(np.mean((indicator - alpha) * (train - var_path)))


def _expectile_objective(train: np.ndarray, var_path: np.ndarray, *, tau: float) -> float:
    diff = train - var_path
    weights = np.where(diff >= 0.0, tau, 1.0 - tau)
    return float(np.mean(weights * diff * diff))


def _fz_objective(
    train: np.ndarray,
    var_path: np.ndarray,
    es_path: np.ndarray,
    tail_level: float,
) -> float:
    losses = [
        _fz_loss_one(float(y), float(var), float(es), tail_level)
        for y, var, es in zip(train, var_path, es_path, strict=False)
    ]
    finite = np.asarray([value for value in losses if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return 1e12
    return float(np.mean(finite))


def _fz_loss_one(loss: float, var_forecast: float, es_forecast: float, tail_level: float) -> float:
    valid, _ = validate_forecast_values(var_forecast, es_forecast)
    if not valid or es_forecast <= 0.0:
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


def _positive_gap_from_params(params: np.ndarray) -> float:
    return float(max(math.exp(float(params[-1])), 1e-12))


def _objective_kind(model_name: str) -> str:
    if model_name.startswith("care_expectile_"):
        return "expectile"
    if model_name.startswith("ald_taylor_"):
        return "ald"
    if model_name.startswith("direct_fz_loss_"):
        return "fz"
    return "quantile"


def _uses_positive_gap(model_name: str) -> bool:
    return model_name.startswith("ald_taylor_") or model_name.startswith("direct_fz_loss_")


def _recursive_variant(model_name: str) -> str:
    return "asymmetric_slope" if model_name.endswith("asymmetric_slope") else "sav"


def _burn_in_rows(train_n: int, *, gas: bool) -> int:
    if gas:
        return int(min(ADVANCED_GAS_BURN_IN_ROWS, max(1, train_n // 3)))
    return int(min(ADVANCED_RECURSIVE_BURN_IN_ROWS, max(1, train_n // 4)))


def _parameter_payload(
    *,
    model_name: str,
    params: np.ndarray,
    refit_date: str,
    optimizer: dict[str, object],
    extra: dict[str, object],
) -> dict[str, object]:
    return {
        "model": model_name,
        "params": {f"theta_{index}": float(value) for index, value in enumerate(params)},
        "refit_date": refit_date,
        "optimizer": optimizer.get("optimizer_method"),
        "convergence_code": optimizer.get("convergence_code"),
        "objective_value": optimizer.get("objective_value"),
        **extra,
    }


def _stable_optimizer_seed(model_name: str, tail_level: float, forecast_date: str) -> int:
    digest = stable_hash({"model": model_name, "tail": tail_level, "date": forecast_date})
    return int(digest[:8], 16)


def _failure_status_for_model(model_name: str) -> str:
    if model_name.startswith("gas_t_"):
        return "unavailable_gas_filter_failed"
    if model_name.startswith("care_expectile_"):
        return "unavailable_care_expectile_calibration_failed"
    if model_name.startswith("direct_fz_loss_"):
        return "unavailable_direct_fz_optimizer_failed"
    return "unavailable_advanced_optimizer_failed"


__all__ = [
    "_advanced_pot_gpd_standardized_tail",
    "_burn_in_rows",
    "_empirical_es_multiplier",
    "_expectile_objective",
    "_failure_status_for_model",
    "_fz_objective",
    "_gas_filter_path",
    "_gas_initial_params",
    "_gas_next_log_sigma",
    "_gas_params_valid",
    "_objective_kind",
    "_parameter_payload",
    "_positive_gap_from_params",
    "_profile_gas_nu",
    "_quantile_objective",
    "_recursive_initial_params",
    "_recursive_next_var",
    "_recursive_params_valid",
    "_recursive_var_path",
    "_recursive_variant",
    "_run_derivative_free_optimizer",
    "_student_t_standardized_var_es",
    "_uses_positive_gap",
]
