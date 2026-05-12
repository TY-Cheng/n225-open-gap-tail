# mypy: ignore-errors
# ruff: noqa: F401,I001,PLR0912,PLR0913,PLR0915,UP035
from __future__ import annotations

import time

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_PARALLELISM_UNIT,
    BENCHMARK_ADVANCED_REFIT_FREQUENCY,
    BENCHMARK_ADVANCED_RUNTIME_BUDGET_SINGLE_THREADED,
    CARE_EXPECTILE_CALIBRATION_METHOD,
    CARE_EXPECTILE_GRID,
    cast,
    date,
    DEFAULT_MIN_TRAIN_EXCEEDANCES,
    DEFAULT_MIN_TRAIN_ROWS,
    GAS_NU_GRID,
    GAS_SCORE_SCALING,
    GAS_STATE_VARIABLE,
    json,
    math,
    normalize_tail_side,
    np,
    PRIMARY_TAIL_SIDE,
    stable_hash,
    stats,
    validate_forecast_values,
    _clean_loss_rows,
    _required_float,
)
from n225_open_gap_tail.models.benchmark_advanced_math import (
    _advanced_pot_gpd_standardized_tail,
    _burn_in_rows,
    _empirical_es_multiplier,
    _expectile_objective,
    _failure_status_for_model,
    _fz_objective,
    _gas_filter_path,
    _gas_initial_params,
    _gas_next_log_sigma,
    _gas_params_valid,
    _objective_kind,
    _parameter_payload,
    _positive_gap_from_params,
    _profile_gas_nu,
    _quantile_objective,
    _recursive_initial_params,
    _recursive_next_var,
    _recursive_params_valid,
    _recursive_var_path,
    _recursive_variant,
    _run_derivative_free_optimizer,
    _student_t_standardized_var_es,
    _uses_positive_gap,
)


def benchmark_advanced_refit_dates(
    rows: list[dict[str, object]],
    *,
    oos_start: str,
) -> list[str]:
    """First valid panel forecast date in each calendar month after OOS start."""
    start_date = date.fromisoformat(oos_start)
    refits: dict[str, str] = {}
    for row in _clean_loss_rows(rows):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        month_key = forecast_date.strftime("%Y-%m")
        refits.setdefault(month_key, forecast_date.isoformat())
    return [refits[key] for key in sorted(refits)]


def _forecast_stateful_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_level: float,
    oos_start: str,
    tail_side: str | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    tail_side = normalize_tail_side(tail_side or (rows[0].get("tail_side") if rows else None))
    clean = _clean_loss_rows(rows)
    if not clean:
        return (
            [],
            [
                _unavailable_diagnostic(
                    model_name,
                    tail_level,
                    "unavailable_no_clean_rows",
                    tail_side=tail_side,
                )
            ],
            [],
        )
    start_date = date.fromisoformat(oos_start)
    forecast_date_strings = [str(row["forecast_date"]) for row in clean]
    forecast_dates = [date.fromisoformat(item) for item in forecast_date_strings]
    losses = np.asarray([_required_float(row["realized_loss"]) for row in clean], dtype=float)
    refit_dates = set(benchmark_advanced_refit_dates(clean, oos_start=oos_start))
    sorted_refit_dates = sorted(refit_dates)
    train_start = forecast_date_strings[0]
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    current_fit: dict[str, object] | None = None
    previous_params: np.ndarray | None = None
    gas_nu_by_year: dict[int, float] = {}
    for index, row in enumerate(clean):
        forecast_date = forecast_dates[index]
        if forecast_date < start_date:
            continue
        train = losses[:index]
        if train.size < DEFAULT_MIN_TRAIN_ROWS:
            continue
        forecast_date_str = forecast_date_strings[index]
        train_end = forecast_date_strings[index - 1]
        needs_refit = current_fit is None or forecast_date_str in refit_dates
        if needs_refit:
            fit = _fit_advanced_model(
                train=train,
                model_name=model_name,
                tail_level=tail_level,
                forecast_date=forecast_date_str,
                previous_params=previous_params,
                gas_nu_by_year=gas_nu_by_year,
            )
            diagnostics.append(
                _fit_diagnostic_row(
                    fit=fit,
                    model_name=model_name,
                    tail_side=tail_side,
                    tail_level=tail_level,
                    forecast_date=forecast_date_str,
                    train=train,
                    train_start=train_start,
                    train_end=train_end,
                    refit_dates=sorted_refit_dates,
                )
            )
            if fit["fit_status"] != "ok":
                current_fit = None
                continue
            current_fit = fit
            previous_params = cast(np.ndarray, fit["params"])
        if current_fit is None:
            continue
        forecast = _forecast_from_advanced_fit(current_fit)
        realized_loss = float(losses[index])
        var_forecast = _required_float(forecast["var_forecast"])
        es_forecast = _required_float(forecast["es_forecast"])
        valid, invalid_reason = validate_forecast_values(var_forecast, es_forecast)
        if valid:
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": "full_gap_settle_to_open",
                    "tail_side": tail_side,
                    "model_name": model_name,
                    "information_set": "target_history_only",
                    "tail_level": tail_level,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": forecast["es_companion_type"],
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": True,
                    "invalid_reason": None,
                    "train_start": train_start,
                    "train_end": train_end,
                    "train_n": int(train.size),
                    "fit_status": "ok",
                    "failure_reason": None,
                    "runtime_seconds": current_fit.get("runtime_seconds"),
                    "refit_date": current_fit.get("refit_date"),
                    "burn_in_rows": current_fit.get("burn_in_rows"),
                    "parameter_json": current_fit.get("parameter_json"),
                    "optimizer_status": current_fit.get("optimizer_status"),
                    "convergence_code": current_fit.get("convergence_code"),
                    "objective_value": current_fit.get("objective_value"),
                    "objective_kind": current_fit.get("objective_kind"),
                    "retry_count": current_fit.get("retry_count"),
                    "restart_count": current_fit.get("restart_count"),
                    "initialization_source": current_fit.get("initialization_source"),
                    "es_source": current_fit.get("es_source"),
                    "fz_interpretation": current_fit.get("fz_interpretation"),
                    "expectile_tau": current_fit.get("expectile_tau"),
                    "score_scaling": current_fit.get("score_scaling"),
                    "state_variable": current_fit.get("state_variable"),
                    "nu": current_fit.get("nu"),
                    "nu_profile_method": current_fit.get("nu_profile_method"),
                    "threshold_quantile": current_fit.get("threshold_quantile"),
                    "threshold_value": current_fit.get("threshold_value"),
                    "evt_exceedance_count": current_fit.get("evt_exceedance_count"),
                    "evt_shape": current_fit.get("evt_shape"),
                    "evt_scale": current_fit.get("evt_scale"),
                    "gpd_unconstrained_loc_hat": current_fit.get("gpd_unconstrained_loc_hat"),
                    "gpd_fixed_loc_diagnostic_status": current_fit.get(
                        "gpd_fixed_loc_diagnostic_status"
                    ),
                }
            )
        else:
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                }
            )
        try:
            _update_advanced_fit_state(current_fit, realized_loss)
        except Exception as exc:  # pragma: no cover - defensive state filter guard
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_state_update_failed",
                    "failure_reason": str(exc),
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                }
            )
            current_fit = None
    if not forecasts and not diagnostics:
        diagnostics.append(
            _unavailable_diagnostic(
                model_name,
                tail_level,
                "unavailable_advanced_model_no_forecasts",
                tail_side=tail_side,
            )
        )
    return forecasts, diagnostics, failures


def _fit_advanced_model(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
    forecast_date: str,
    previous_params: np.ndarray | None,
    gas_nu_by_year: dict[int, float],
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        if model_name.startswith("gas_t_"):
            fit = _fit_gas_model(
                train=train,
                model_name=model_name,
                tail_level=tail_level,
                forecast_date=forecast_date,
                previous_params=previous_params,
                gas_nu_by_year=gas_nu_by_year,
            )
        else:
            fit = _fit_recursive_var_model(
                train=train,
                model_name=model_name,
                tail_level=tail_level,
                forecast_date=forecast_date,
                previous_params=previous_params,
            )
    except Exception as exc:
        return {
            "fit_status": _failure_status_for_model(model_name),
            "failure_reason": str(exc),
            "runtime_seconds": time.perf_counter() - started,
            "refit_date": forecast_date,
        }
    fit["runtime_seconds"] = time.perf_counter() - started
    fit["refit_date"] = forecast_date
    return fit


def _fit_recursive_var_model(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
    forecast_date: str,
    previous_params: np.ndarray | None,
) -> dict[str, object]:
    variant = _recursive_variant(model_name)
    burn_in_rows = _burn_in_rows(train.size, gas=False)
    initial_params, initialization_source = _recursive_initial_params(
        train=train,
        model_name=model_name,
        variant=variant,
        tail_level=tail_level,
        previous_params=previous_params,
    )
    objective_kind = _objective_kind(model_name)
    expectile_tau = None
    care_calibration: dict[str, object] = {}
    if objective_kind == "expectile":
        care_calibration = _calibrate_care_expectile_tau(train, tail_level=tail_level)
        if care_calibration["expectile_calibration_status"] != "ok":
            return {
                "fit_status": "unavailable_care_expectile_calibration_failed",
                "failure_reason": care_calibration["expectile_calibration_status"],
                "burn_in_rows": burn_in_rows,
                **care_calibration,
            }
        expectile_tau = float(care_calibration["expectile_tau"])

    def objective(params: np.ndarray) -> float:
        if not _recursive_params_valid(
            params,
            variant=variant,
            has_gap=_uses_positive_gap(model_name),
        ):
            return 1e12
        var_path, _ = _recursive_var_path(
            train=train,
            params=params,
            variant=variant,
            has_gap=_uses_positive_gap(model_name),
            tail_level=tail_level,
        )
        objective_train = train[burn_in_rows:]
        objective_var_path = var_path[burn_in_rows:]
        if objective_kind == "expectile":
            return _expectile_objective(
                objective_train,
                objective_var_path,
                tau=_required_float(expectile_tau),
            )
        if objective_kind == "ald_fz0":
            gap = _positive_gap_from_params(params)
            return _fz_objective(
                objective_train,
                objective_var_path,
                objective_var_path + gap,
                tail_level,
            )
        return _quantile_objective(objective_train, objective_var_path, tail_level)

    opt = _run_derivative_free_optimizer(
        objective=objective,
        x0=initial_params,
        model_name=model_name,
        tail_level=tail_level,
        forecast_date=forecast_date,
    )
    params = cast(np.ndarray, opt["params"])
    var_path, next_var = _recursive_var_path(
        train=train,
        params=params,
        variant=variant,
        has_gap=_uses_positive_gap(model_name),
        tail_level=tail_level,
    )
    if _uses_positive_gap(model_name):
        gap = _positive_gap_from_params(params)
        es_multiplier = None
        es_source = "positive_gap_joint_var_es"
        fz_interpretation = "joint_var_es_optimized"
    else:
        es_multiplier_info = _empirical_es_multiplier(
            train_losses=train[burn_in_rows:],
            train_var_forecasts=var_path[burn_in_rows:],
        )
        if es_multiplier_info["status"] != "ok":
            return {
                "fit_status": "unavailable_empirical_es_companion_insufficient_exceedances",
                "failure_reason": es_multiplier_info["status"],
                "burn_in_rows": burn_in_rows,
                **opt,
                **care_calibration,
                **es_multiplier_info,
            }
        gap = None
        es_multiplier = _required_float(es_multiplier_info["es_multiplier"])
        es_source = "empirical_exceedance_companion"
        fz_interpretation = "augmented_var_es_pair_not_jointly_estimated"
    parameter_payload = _parameter_payload(
        model_name=model_name,
        params=params,
        refit_date=forecast_date,
        optimizer=opt,
        extra={
            "variant": variant,
            "objective_kind": objective_kind,
            "expectile_tau": expectile_tau,
            "es_multiplier": es_multiplier,
            "positive_es_gap": gap,
        },
    )
    return {
        "fit_status": "ok",
        "model_name": model_name,
        "tail_level": tail_level,
        "params": params,
        "variant": variant,
        "objective_kind": objective_kind,
        "state": {"var": float(next_var)},
        "positive_gap": gap,
        "es_multiplier": es_multiplier,
        "es_source": es_source,
        "fz_interpretation": fz_interpretation,
        "es_companion_type": es_source,
        "burn_in_rows": burn_in_rows,
        "parameter_json": json.dumps(parameter_payload, sort_keys=True, separators=(",", ":")),
        "initialization_source": initialization_source,
        **opt,
        **care_calibration,
    }


def _fit_gas_model(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
    forecast_date: str,
    previous_params: np.ndarray | None,
    gas_nu_by_year: dict[int, float],
) -> dict[str, object]:
    burn_in_rows = _burn_in_rows(train.size, gas=True)
    year = date.fromisoformat(forecast_date).year
    if year not in gas_nu_by_year:
        gas_nu_by_year[year] = _profile_gas_nu(train)
    nu = gas_nu_by_year[year]
    x0, initialization_source = _gas_initial_params(train, previous_params=previous_params)

    def objective(params: np.ndarray) -> float:
        if not _gas_params_valid(params):
            return 1e12
        path = _gas_filter_path(train=train, params=params, nu=nu)
        if path is None:
            return 1e12
        log_sigmas = path["log_sigmas"]
        mu = float(params[3])
        sigma = np.exp(log_sigmas)
        z = (train - mu) / sigma
        ll = (stats.t.logpdf(z, df=nu) - np.log(sigma))[burn_in_rows:]
        finite = ll[np.isfinite(ll)]
        if finite.size == 0:
            return 1e12
        return float(-np.mean(finite))

    opt = _run_derivative_free_optimizer(
        objective=objective,
        x0=x0,
        model_name=model_name,
        tail_level=tail_level,
        forecast_date=forecast_date,
    )
    params = cast(np.ndarray, opt["params"])
    path = _gas_filter_path(train=train, params=params, nu=nu)
    if path is None:
        return {
            "fit_status": "unavailable_gas_filter_failed",
            "failure_reason": "nonfinite_raw_student_t_log_scale_score",
            "burn_in_rows": burn_in_rows,
            **opt,
        }
    location = float(params[3])
    standardized_losses = (train - location) / np.exp(cast(np.ndarray, path["log_sigmas"]))
    standardized_losses = standardized_losses[burn_in_rows:]
    tail_info: dict[str, object] = {}
    standardized_var = standardized_es = None
    if model_name == "gas_t_pot_gpd":
        tail_info = _advanced_pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=tail_level,
        )
        standardized_var = _required_float(tail_info["standardized_var"])
        standardized_es = _required_float(tail_info["standardized_es"])
        es_companion_type = "gas_standardized_loss_pot_gpd"
    else:
        standardized_var, standardized_es = _student_t_standardized_var_es(
            nu=nu,
            tail_level=tail_level,
        )
        es_companion_type = "gas_student_t_analytical_es"
    state = {
        "log_sigma": float(path["next_log_sigma"]),
        "location": location,
        "nu": nu,
        "standardized_var": float(standardized_var),
        "standardized_es": float(standardized_es),
    }
    parameter_payload = _parameter_payload(
        model_name=model_name,
        params=params,
        refit_date=forecast_date,
        optimizer=opt,
        extra={
            "nu": nu,
            "nu_profile_method": "annual_profile_grid",
            "nu_grid": list(GAS_NU_GRID),
            "score_scaling": GAS_SCORE_SCALING,
        },
    )
    return {
        "fit_status": "ok",
        "model_name": model_name,
        "tail_level": tail_level,
        "params": params,
        "state": state,
        "es_companion_type": es_companion_type,
        "burn_in_rows": burn_in_rows,
        "parameter_json": json.dumps(parameter_payload, sort_keys=True, separators=(",", ":")),
        "initialization_source": initialization_source,
        "score_scaling": GAS_SCORE_SCALING,
        "state_variable": GAS_STATE_VARIABLE,
        "nu": nu,
        "nu_profile_method": "annual_profile_grid",
        "nu_profile_grid_json": json.dumps(GAS_NU_GRID, separators=(",", ":")),
        "nu_profile_window_start": None,
        "nu_profile_window_end": None,
        **opt,
        **tail_info,
    }


def _forecast_from_advanced_fit(fit: dict[str, object]) -> dict[str, object]:
    model_name = str(fit["model_name"])
    if model_name.startswith("gas_t_"):
        state = cast(dict[str, object], fit["state"])
        sigma = math.exp(_required_float(state["log_sigma"]))
        location = _required_float(state["location"])
        var = location + sigma * _required_float(state["standardized_var"])
        es = location + sigma * _required_float(state["standardized_es"])
        return {
            "var_forecast": float(var),
            "es_forecast": float(max(var, es)),
            "es_companion_type": fit["es_companion_type"],
        }
    state = cast(dict[str, object], fit["state"])
    var = max(_required_float(state["var"]), 1e-12)
    if fit.get("positive_gap") is not None:
        es = var + _required_float(fit["positive_gap"])
    else:
        es = var * _required_float(fit["es_multiplier"])
    return {
        "var_forecast": float(var),
        "es_forecast": float(max(var, es)),
        "es_companion_type": fit["es_companion_type"],
    }


def _update_advanced_fit_state(fit: dict[str, object], realized_loss: float) -> None:
    model_name = str(fit["model_name"])
    if model_name.startswith("gas_t_"):
        state = cast(dict[str, object], fit["state"])
        params = cast(np.ndarray, fit["params"])
        state["log_sigma"] = _gas_next_log_sigma(
            y=realized_loss,
            log_sigma=_required_float(state["log_sigma"]),
            params=params,
            nu=_required_float(state["nu"]),
        )
        return
    state = cast(dict[str, object], fit["state"])
    params = cast(np.ndarray, fit["params"])
    state["var"] = _recursive_next_var(
        q=_required_float(state["var"]),
        y=realized_loss,
        params=params,
        variant=str(fit["variant"]),
        has_gap=_uses_positive_gap(model_name),
    )


def _fit_diagnostic_row(
    *,
    fit: dict[str, object],
    model_name: str,
    tail_side: str,
    tail_level: float,
    forecast_date: str,
    train: np.ndarray,
    train_start: str,
    train_end: str,
    refit_dates: list[str],
) -> dict[str, object]:
    return {
        "forecast_date": forecast_date,
        "model_name": model_name,
        "tail_side": tail_side,
        "tail_level": tail_level,
        "fit_status": fit.get("fit_status"),
        "failure_reason": fit.get("failure_reason"),
        "train_n": int(train.size),
        "train_start": train_start,
        "train_end": train_end,
        "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
        "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
        "refit_date": fit.get("refit_date") or forecast_date,
        "refit_dates_json": json.dumps(refit_dates, separators=(",", ":")),
        "refit_calendar": "first_valid_panel_forecast_date_per_calendar_month",
        "state_update_policy": "valid_panel_dates_only_skip_calendar_gaps",
        "burn_in_rows": fit.get("burn_in_rows"),
        "parameter_json": fit.get("parameter_json"),
        "optimizer_method": fit.get("optimizer_method"),
        "optimizer_status": fit.get("optimizer_status"),
        "convergence_code": fit.get("convergence_code"),
        "objective_value": fit.get("objective_value"),
        "objective_kind": fit.get("objective_kind"),
        "retry_count": fit.get("retry_count"),
        "restart_count": fit.get("restart_count"),
        "initialization_source": fit.get("initialization_source"),
        "runtime_seconds": fit.get("runtime_seconds"),
        "advanced_runtime_budget_single_threaded": (
            BENCHMARK_ADVANCED_RUNTIME_BUDGET_SINGLE_THREADED
        ),
        "advanced_parallelism_unit": BENCHMARK_ADVANCED_PARALLELISM_UNIT,
        "candidate_feature_hash": stable_hash([]),
        "active_feature_hash": stable_hash([]),
        "dropped_features_json": "[]",
        "drop_reason": None,
        "training_missingness": "{}",
        "training_variance": "{}",
        "es_source": fit.get("es_source"),
        "fz_interpretation": fit.get("fz_interpretation"),
        "es_multiplier": fit.get("es_multiplier"),
        "es_multiplier_exceedance_count": fit.get("es_multiplier_exceedance_count"),
        "care_model_definition": "conditional_autoregressive_expectile"
        if model_name.startswith("care_expectile_")
        else None,
        "care_var_es_mapping": "training_window_expectile_level_calibrated_to_var_coverage"
        if model_name.startswith("care_expectile_")
        else None,
        "expectile_grid_json": json.dumps(CARE_EXPECTILE_GRID, separators=(",", ":"))
        if model_name.startswith("care_expectile_")
        else None,
        "expectile_tau": fit.get("expectile_tau"),
        "expectile_calibration_breach_rate": fit.get("expectile_calibration_breach_rate"),
        "expectile_calibration_objective": fit.get("expectile_calibration_objective"),
        "expectile_calibration_status": fit.get("expectile_calibration_status"),
        "expectile_calibration_method": fit.get("expectile_calibration_method"),
        "expectile_calibration_source": fit.get("expectile_calibration_source"),
        "score_scaling": fit.get("score_scaling"),
        "state_variable": fit.get("state_variable"),
        "invalid_state_status": "unavailable_gas_filter_failed"
        if model_name.startswith("gas_t_")
        else None,
        "nu": fit.get("nu"),
        "nu_profile_method": fit.get("nu_profile_method"),
        "nu_profile_grid_json": fit.get("nu_profile_grid_json"),
        "threshold_quantile": fit.get("threshold_quantile"),
        "threshold_value": fit.get("threshold_value"),
        "evt_exceedance_count": fit.get("evt_exceedance_count"),
        "evt_shape": fit.get("evt_shape"),
        "evt_scale": fit.get("evt_scale"),
        "gpd_unconstrained_loc_hat": fit.get("gpd_unconstrained_loc_hat"),
        "gpd_fixed_loc_diagnostic_status": fit.get("gpd_fixed_loc_diagnostic_status"),
    }


def _unavailable_diagnostic(
    model_name: str,
    tail_level: float,
    reason: str,
    *,
    tail_side: str = PRIMARY_TAIL_SIDE,
) -> dict[str, object]:
    return {
        "model_name": model_name,
        "tail_side": tail_side,
        "tail_level": tail_level,
        "fit_status": reason,
        "failure_reason": reason,
        "refit_frequency": BENCHMARK_ADVANCED_REFIT_FREQUENCY,
        "advanced_runtime_budget_single_threaded": (
            BENCHMARK_ADVANCED_RUNTIME_BUDGET_SINGLE_THREADED
        ),
        "advanced_parallelism_unit": BENCHMARK_ADVANCED_PARALLELISM_UNIT,
        "refit_calendar": "first_valid_panel_forecast_date_per_calendar_month",
        "state_update_policy": "valid_panel_dates_only_skip_calendar_gaps",
        **_advanced_model_calibration_metadata(
            rows=[],
            model_name=model_name,
            tail_level=tail_level,
            oos_start="9999-12-31",
        ),
    }


def _advanced_model_calibration_metadata(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_level: float,
    oos_start: str,
) -> dict[str, object]:
    if model_name.startswith("gas_t_"):
        return {
            "score_scaling": GAS_SCORE_SCALING,
            "state_variable": GAS_STATE_VARIABLE,
            "invalid_state_status": "unavailable_gas_filter_failed",
            "nu_profile_method": "annual_profile_grid",
            "nu_profile_grid_json": json.dumps(GAS_NU_GRID, separators=(",", ":")),
        }
    if model_name.startswith("care_expectile_"):
        calibration = _calibrate_care_expectile_tau(
            _training_losses_before_oos(rows, oos_start=oos_start),
            tail_level=tail_level,
        )
        return {
            "care_model_definition": "conditional_autoregressive_expectile",
            "care_var_es_mapping": "training_window_expectile_level_calibrated_to_var_coverage",
            "expectile_grid_json": json.dumps(CARE_EXPECTILE_GRID, separators=(",", ":")),
            **calibration,
        }
    return {}


def _training_losses_before_oos(
    rows: list[dict[str, object]],
    *,
    oos_start: str,
) -> np.ndarray:
    start_date = date.fromisoformat(oos_start)
    values = [
        _required_float(row["realized_loss"])
        for row in _clean_loss_rows(rows)
        if date.fromisoformat(str(row["forecast_date"])) < start_date
    ]
    return np.asarray(values, dtype=float)


def _calibrate_care_expectile_tau(
    training_losses: np.ndarray,
    *,
    tail_level: float,
) -> dict[str, object]:
    values = training_losses[np.isfinite(training_losses)]
    if values.size < DEFAULT_MIN_TRAIN_ROWS:
        return {
            "expectile_tau": None,
            "expectile_calibration_breach_rate": None,
            "expectile_calibration_objective": None,
            "expectile_calibration_status": "unavailable_care_expectile_insufficient_training_rows",
            "expectile_calibration_method": CARE_EXPECTILE_CALIBRATION_METHOD,
            "expectile_calibration_source": "training_window_before_oos_start",
        }
    target_breach_rate = 1.0 - tail_level
    candidates: list[dict[str, object]] = []
    for tau in CARE_EXPECTILE_GRID:
        threshold = _sample_expectile(values, tau=float(tau))
        if threshold is None:
            continue
        breach_rate = float(np.mean(values > threshold))
        candidates.append(
            {
                "tau": float(tau),
                "threshold": float(threshold),
                "breach_rate": breach_rate,
                "objective": abs(breach_rate - target_breach_rate),
            }
        )
    if not candidates:
        return {
            "expectile_tau": None,
            "expectile_calibration_breach_rate": None,
            "expectile_calibration_objective": None,
            "expectile_calibration_status": "unavailable_care_expectile_calibration_failed",
            "expectile_calibration_method": CARE_EXPECTILE_CALIBRATION_METHOD,
            "expectile_calibration_source": "training_window_before_oos_start",
        }
    best = min(candidates, key=lambda row: (row["objective"], -row["tau"]))
    return {
        "expectile_tau": best["tau"],
        "expectile_calibration_threshold": best["threshold"],
        "expectile_calibration_breach_rate": best["breach_rate"],
        "expectile_calibration_objective": best["objective"],
        "expectile_calibration_status": "ok",
        "expectile_calibration_method": CARE_EXPECTILE_CALIBRATION_METHOD,
        "expectile_calibration_source": "training_window_before_oos_start",
    }


def _sample_expectile(values: np.ndarray, *, tau: float) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0 or not 0.0 < tau < 1.0:
        return None
    lower = float(np.min(finite))
    upper = float(np.max(finite))
    if math.isclose(lower, upper):
        return lower
    for _ in range(80):
        midpoint = (lower + upper) / 2.0
        above = np.maximum(finite - midpoint, 0.0).sum()
        below = np.maximum(midpoint - finite, 0.0).sum()
        score = tau * above - (1.0 - tau) * below
        if score > 0:
            lower = midpoint
        else:
            upper = midpoint
    return float((lower + upper) / 2.0)


def _gas_filter_failure_record(
    *,
    model_name: str,
    tail_side: str = PRIMARY_TAIL_SIDE,
    tail_level: float,
    failure_reason: str,
) -> dict[str, object]:
    return _advanced_benchmark_record(
        {
            "model_name": model_name,
            "tail_side": tail_side,
            "tail_level": tail_level,
            "fit_status": "unavailable_gas_filter_failed",
            "failure_reason": failure_reason,
            "score_scaling": GAS_SCORE_SCALING,
            "state_variable": GAS_STATE_VARIABLE,
            "invalid_state_status": "unavailable_gas_filter_failed",
        },
        model_name=model_name,
    )


def _advanced_benchmark_record(
    row: dict[str, object],
    *,
    model_name: str,
) -> dict[str, object]:
    model_meta = _advanced_model_metadata(model_name)
    return {
        **row,
        "model_name": row.get("model_name") or model_name,
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "tail_side": row.get("tail_side") or PRIMARY_TAIL_SIDE,
        "information_set": row.get("information_set") or "target_history_only",
        "benchmark_tier": "advanced",
        "model_family": row.get("model_family") or model_meta["model_family"],
        "model_variant": row.get("model_variant") or model_meta["model_variant"],
        "refit_frequency": row.get("refit_frequency") or BENCHMARK_ADVANCED_REFIT_FREQUENCY,
        "advanced_model_nonblocking": True,
    }


def _advanced_model_metadata(model_name: str) -> dict[str, str]:
    if model_name.startswith("caviar_"):
        return {"model_family": "caviar", "model_variant": model_name.removeprefix("caviar_")}
    if model_name.startswith("care_expectile_"):
        return {
            "model_family": "care_expectile",
            "model_variant": model_name.removeprefix("care_expectile_"),
        }
    if model_name.startswith("ald_taylor_"):
        return {
            "model_family": "ald_taylor_var_es",
            "model_variant": model_name.removeprefix("ald_taylor_"),
        }
    if model_name.startswith("gas_t_"):
        return {"model_family": "gas_t", "model_variant": model_name.removeprefix("gas_t_")}
    return {"model_family": "advanced_benchmark", "model_variant": model_name}
