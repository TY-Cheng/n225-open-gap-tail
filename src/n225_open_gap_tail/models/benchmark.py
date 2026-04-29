# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def resolve_run_dir(settings: Settings, run_id: str) -> Path:
    runs_dir = settings.reports_dir / "runs"
    if run_id:
        run_dir = runs_dir / run_id
    else:
        candidates = [path for path in runs_dir.glob("tailrisk_*") if path.is_dir()]
        if not candidates:
            raise PipelineRunError("No run found; run build-panel first or pass run_id")
        run_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    if not run_dir.exists():
        raise PipelineRunError(f"Run does not exist: {run_dir}")
    return run_dir


def _evaluate_benchmark_shard(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    tail_side = normalize_tail_side(payload.get("tail_side"))
    tail_level = _required_float(payload["tail_level"])
    models = cast(tuple[str, ...], payload["models"])
    panel_columns = pl.scan_parquet(panel_path).collect_schema().names()
    selected_columns = ["forecast_date", "realized_loss"]
    if "gap_t" in panel_columns:
        selected_columns.append("gap_t")
    frame = (
        pl.scan_parquet(panel_path)
        .filter(pl.col("clean_sample") == True)  # noqa: E712
        .select(selected_columns)
        .drop_nulls()
        .sort("forecast_date")
        .collect()
    )
    rows = _rows_for_tail_side(frame.to_dicts(), tail_side=tail_side)
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "benchmark_tier": "floor",
                    "model_family": _floor_model_family(model_name),
                    "model_variant": model_name,
                    "refit_frequency": None,
                    "advanced_model_nonblocking": False,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(
                        model_name,
                        tail_level,
                        tail_side=tail_side,
                    ),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "oos_failure_reason": oos_diagnostics["failure_reason"],
                    "train_n": oos_diagnostics["train_n"],
                    "train_exceedances": oos_diagnostics["train_exceedances"],
                    "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                    "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                    "refit_dates_json": None,
                    "refit_calendar": None,
                    "state_update_policy": None,
                }
                for model_name in models
            ],
            "failures": [],
        }
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for model_name in models:
        model_rows, model_diag, model_failures = _forecast_model_sequence(
            rows=rows,
            model_name=model_name,
            tail_side=tail_side,
            tail_level=tail_level,
            oos_start=oos_start,
        )
        forecasts.extend(model_rows)
        diagnostics.extend(model_diag)
        failures.extend(model_failures)
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _forecast_model_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_side: str,
    tail_level: float,
    oos_start: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    clean = _clean_loss_rows(rows)
    start_date = date.fromisoformat(oos_start)
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        if train.size < DEFAULT_MIN_TRAIN_ROWS:
            continue
        try:
            forecast = _forecast_one(train=train, model_name=model_name, tail_level=tail_level)
            realized_loss = _required_float(row["realized_loss"])
            var_forecast = _required_float(forecast["var_forecast"])
            es_forecast = _required_float(forecast["es_forecast"])
            valid, invalid_reason = validate_forecast_values(
                var_forecast,
                es_forecast,
            )
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": "full_gap_settle_to_open",
                    "tail_side": tail_side,
                    "model_name": model_name,
                    "benchmark_tier": "floor",
                    "model_family": _floor_model_family(model_name),
                    "model_variant": model_name,
                    "refit_frequency": None,
                    "advanced_model_nonblocking": False,
                    "information_set": "target_history_only",
                    "tail_level": tail_level,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": forecast["es_companion_type"],
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": valid,
                    "invalid_reason": invalid_reason,
                    "train_start": clean[0]["forecast_date"],
                    "train_end": clean[index - 1]["forecast_date"],
                    "train_n": int(train.size),
                    "fit_status": "ok" if valid else "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "runtime_seconds": None,
                }
            )
            diagnostics.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "benchmark_tier": "floor",
                    "model_family": _floor_model_family(model_name),
                    "model_variant": model_name,
                    "refit_frequency": None,
                    "advanced_model_nonblocking": False,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "train_n": int(train.size),
                    "optimizer_status": forecast.get("optimizer_status"),
                    "convergence_code": forecast.get("convergence_code"),
                    "candidate_feature_hash": stable_hash([]),
                    "active_feature_hash": stable_hash([]),
                    "dropped_features_json": "[]",
                    "drop_reason": None,
                    "training_missingness": "{}",
                    "training_variance": "{}",
                    "threshold_quantile": forecast.get("threshold_quantile"),
                    "threshold_value": forecast.get("threshold_value"),
                    "evt_exceedance_count": forecast.get("evt_exceedance_count"),
                    "threshold_diagnostics_json": forecast.get("threshold_diagnostics_json"),
                    "threshold_policy": forecast.get("threshold_policy"),
                    "threshold_smoothing": forecast.get("threshold_smoothing"),
                    "threshold_selection": forecast.get("threshold_selection"),
                    "refit_dates_json": None,
                    "refit_calendar": None,
                    "state_update_policy": None,
                }
            )
        except Exception as exc:  # pragma: no cover - exercised via synthetic failure tests
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "benchmark_tier": "floor",
                    "model_family": _floor_model_family(model_name),
                    "model_variant": model_name,
                    "refit_frequency": None,
                    "advanced_model_nonblocking": False,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_optimizer_failed",
                    "failure_reason": str(exc),
                    "refit_dates_json": None,
                    "refit_calendar": None,
                    "state_update_policy": None,
                }
            )
    return forecasts, diagnostics, failures


def _rows_for_tail_side(
    rows: list[dict[str, object]], *, tail_side: str
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        loss = realized_loss_for_tail_side(row, tail_side)
        if loss is None:
            continue
        output.append({**row, "tail_side": tail_side, "realized_loss": loss})
    return output


def _floor_model_family(model_name: str) -> str:
    if model_name in {"historical_quantile", "rolling_quantile"}:
        return "empirical_quantile"
    if model_name == "ewma_vol_scaled":
        return "volatility_scaled"
    if model_name in {"garch_t", "gjr_garch_t"}:
        return "arch"
    if model_name == "gjr_garch_evt":
        return "arch_evt"
    return "benchmark_floor"


def _forecast_one(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
) -> dict[str, object]:
    if model_name == "historical_quantile":
        var_forecast = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(train, var_forecast),
            "es_companion_type": "raw_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "rolling_quantile":
        window = train[-min(DEFAULT_MIN_TRAIN_ROWS, train.size) :]
        var_forecast = float(np.quantile(window, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(window, var_forecast),
            "es_companion_type": "rolling_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "ewma_vol_scaled":
        return _ewma_forecast(train=train, tail_level=tail_level, lambda_=EWMA_MAIN_LAMBDA)
    if model_name in {"garch_t", "gjr_garch_t", "gjr_garch_evt"}:
        return _arch_forecast(train=train, tail_level=tail_level, model_name=model_name)
    raise PipelineRunError(f"Unknown Benchmark model: {model_name}")


def _ewma_forecast(*, train: np.ndarray, tail_level: float, lambda_: float) -> dict[str, object]:
    mean = float(np.mean(train))
    variance = float(np.var(train, ddof=1))
    for value in train:
        variance = lambda_ * variance + (1.0 - lambda_) * float((value - mean) ** 2)
    scale = math.sqrt(max(variance, 1e-12))
    z = stats.norm.ppf(tail_level)
    var_forecast = mean + scale * z
    alpha = 1.0 - tail_level
    es_forecast = mean + scale * stats.norm.pdf(z) / alpha
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_normal_es",
        "optimizer_status": "closed_form",
        "convergence_code": 0,
    }


def _arch_forecast(  # pragma: no cover - numeric optimizer exercised in real Benchmark runs
    *,
    train: np.ndarray,
    tail_level: float,
    model_name: str,
) -> dict[str, object]:
    try:
        from arch import arch_model
    except Exception as exc:  # pragma: no cover - dependency/environment
        raise PipelineRunError(f"arch import failed: {exc}") from exc
    scaled_train = -train * 100.0
    p = 1
    o = 1 if model_name in {"gjr_garch_t", "gjr_garch_evt"} else 0
    model = arch_model(
        scaled_train,
        mean="Constant",
        vol="GARCH",
        p=p,
        o=o,
        q=1,
        dist="studentst",
        rescale=False,
    )
    result = model.fit(disp="off", show_warning=False)
    forecast = result.forecast(horizon=1, reindex=False)
    mean_return_forecast = float(forecast.mean.iloc[-1, 0]) / 100.0
    variance_forecast = float(forecast.variance.iloc[-1, 0]) / (100.0**2)
    scale_forecast = math.sqrt(max(variance_forecast, 1e-12))
    nu = float(result.params.get("nu", 8.0))
    var_forecast, es_forecast = _standardized_student_t_loss_var_es(
        mean_return_forecast=mean_return_forecast,
        scale_forecast=scale_forecast,
        nu=nu,
        tail_level=tail_level,
    )
    if model_name == "gjr_garch_evt":
        standardized_losses = _standardized_arch_losses(
            train=train,
            fitted_result=result,
        )
        evt_tail = _pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=tail_level,
        )
        var_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_var"]
        )
        es_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_es"]
        )
    else:
        evt_tail = {}
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_student_t_es"
        if model_name != "gjr_garch_evt"
        else str(evt_tail.get("tail_method", "pot_gpd_filtered_es")),
        "optimizer_status": "converged"
        if getattr(result, "convergence_flag", 1) == 0
        else "warning",
        "convergence_code": int(getattr(result, "convergence_flag", -1)),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
        "threshold_diagnostics_json": evt_tail.get("threshold_diagnostics_json"),
        "threshold_policy": evt_tail.get("threshold_policy"),
        "threshold_smoothing": evt_tail.get("threshold_smoothing"),
        "threshold_selection": evt_tail.get("threshold_selection"),
    }


def _standardized_student_t_loss_var_es(
    *,
    mean_return_forecast: float,
    scale_forecast: float,
    nu: float,
    tail_level: float,
) -> tuple[float, float]:
    """Convert return-space Student-t forecasts into loss-space VaR and ES.

    The ARCH model is fit on negative returns for numerical convenience, but this
    helper receives the forecast mean in return units. Let return R = mu + sigma Z
    and loss L = -R. For a right-tail loss level tau, alpha = 1 - tau and the
    return cutoff is the lower alpha quantile q_alpha of the standardized
    Student-t innovation. Therefore VaR_tau(L) = -(mu + sigma q_alpha).

    For Student-t innovations standardized to unit variance, q_alpha is
    sqrt((nu - 2) / nu) * t_nu^{-1}(alpha). The left-tail return ES is the
    negative of the symmetric right-tail standardized ES,
    sqrt((nu - 2) / nu) * f_nu(t_nu^{-1}(alpha)) / alpha
    * (nu + t_nu^{-1}(alpha)^2) / (nu - 1), so loss ES is
    -mu + sigma * standardized_upper_es.
    """
    alpha = 1.0 - tail_level
    raw_quantile = float(stats.t.ppf(alpha, df=nu))
    variance_scale = math.sqrt((nu - 2.0) / nu) if nu > 2.0 else 1.0
    standardized_lower_quantile = variance_scale * raw_quantile
    var_forecast = -(mean_return_forecast + scale_forecast * standardized_lower_quantile)
    raw_pdf = float(stats.t.pdf(raw_quantile, df=nu))
    if nu > 1.0:
        standardized_upper_es = (
            variance_scale * ((nu + raw_quantile**2) / (nu - 1.0)) * raw_pdf / alpha
        )
    else:
        standardized_upper_es = -standardized_lower_quantile
    es_forecast = -mean_return_forecast + scale_forecast * standardized_upper_es
    return float(var_forecast), float(max(var_forecast, es_forecast))


def _standardized_arch_losses(train: np.ndarray, fitted_result: object) -> np.ndarray:
    std_resid = getattr(fitted_result, "std_resid", None)
    if std_resid is not None:
        values = np.asarray(std_resid, dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            return cast(np.ndarray, -values)
    fallback = (train - np.mean(train)) / max(float(np.std(train, ddof=1)), 1e-12)
    return cast(np.ndarray, fallback)


def _pot_gpd_standardized_tail(
    *,
    standardized_losses: np.ndarray,
    tail_level: float,
    threshold_quantile: float = EVT_THRESHOLD_QUANTILE,
    require_finite_gpd_es: bool = False,
) -> dict[str, object]:
    values = standardized_losses[np.isfinite(standardized_losses)]
    if values.size < DEFAULT_MIN_TRAIN_ROWS:
        raise PipelineRunError("EVT calibration has insufficient standardized losses")
    diagnostics = _evt_threshold_diagnostics(values)
    threshold = float(np.quantile(values, threshold_quantile))
    excesses = values[values > threshold] - threshold
    if excesses.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        raise PipelineRunError(f"EVT calibration has insufficient exceedances: {excesses.size}")
    if tail_level <= threshold_quantile:
        var_z = float(np.quantile(values, tail_level))
        es_z = static_empirical_es(values, var_z)
        tail_method = "empirical_filtered_es"
    else:
        shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
        shape = float(shape)
        scale = float(max(scale, 1e-12))
        if not math.isfinite(scale) or scale <= 0.0:
            raise PipelineRunError("EVT calibration has invalid GPD scale")
        exceedance_probability = excesses.size / values.size
        target_tail_probability = max(1.0 - tail_level, 1e-12)
        ratio = max(exceedance_probability / target_tail_probability, 1.0)
        if abs(shape) < 1e-8:
            var_z = threshold + scale * math.log(ratio)
        else:
            var_z = threshold + scale * (ratio**shape - 1.0) / shape
        if shape < 1.0:
            es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
        elif require_finite_gpd_es:
            raise PipelineRunError(f"EVT calibration shape >= 1 has infinite ES: {shape}")
        else:
            es_z = static_empirical_es(values, var_z)
        tail_method = "pot_gpd_filtered_es"
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "evt_shape": shape if tail_level > threshold_quantile else None,
        "evt_scale": scale if tail_level > threshold_quantile else None,
        "threshold_diagnostics_json": json.dumps(diagnostics, sort_keys=True),
        "threshold_policy": PIPELINE_CONFIG.model_policy.evt_threshold_refresh,
        "threshold_smoothing": PIPELINE_CONFIG.model_policy.evt_threshold_smoothing,
        "threshold_selection": "pre_registered_fixed_empirical_quantile",
        "tail_method": tail_method,
    }
