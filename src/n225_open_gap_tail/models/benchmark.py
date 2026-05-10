# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    cast,
    date,
    DEFAULT_MIN_TRAIN_EXCEEDANCES,
    DEFAULT_MIN_TRAIN_ROWS,
    EVT_THRESHOLD_QUANTILE,
    EWMA_MAIN_LAMBDA,
    find_oos_start_diagnostics,
    json,
    math,
    normalize_tail_side,
    np,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
    pl,
    realized_loss_for_tail_side,
    Settings,
    stable_hash,
    static_empirical_es,
    stats,
    validate_forecast_values,
    validate_worker_payload,
    _clean_loss_rows,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.data_lake.artifacts import _forecast_shard_id
from n225_open_gap_tail.features.asof import _evt_threshold_diagnostics

UNIBM_EVI_MIN_FINITE_VALUES = 32
UNIBM_EVI_MIN_POSITIVE_BLOCK_SUMMARIES = 5
UNIBM_EVI_MIN_PLATEAU_POINTS = 5
UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT = 20
UNIBM_EVI_QUANTILE = 0.5
UNIBM_EVI_SLIDING_BLOCKS = True


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
    ewma_lambda = _optional_float(payload.get("ewma_lambda"))
    evt_threshold_quantile = _optional_float(payload.get("evt_threshold_quantile"))
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
                    "benchmark_tier": "baseline",
                    "model_family": _baseline_model_family(model_name),
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
            ewma_lambda=ewma_lambda,
            evt_threshold_quantile=evt_threshold_quantile,
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
    ewma_lambda: float | None = None,
    evt_threshold_quantile: float | None = None,
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
            if ewma_lambda is None and evt_threshold_quantile is None:
                forecast = _forecast_one(train=train, model_name=model_name, tail_level=tail_level)
            else:
                forecast = _forecast_one(
                    train=train,
                    model_name=model_name,
                    tail_level=tail_level,
                    ewma_lambda=ewma_lambda,
                    evt_threshold_quantile=evt_threshold_quantile,
                )
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
                    "benchmark_tier": "baseline",
                    "model_family": _baseline_model_family(model_name),
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
                    "benchmark_tier": "baseline",
                    "model_family": _baseline_model_family(model_name),
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
                    "benchmark_tier": "baseline",
                    "model_family": _baseline_model_family(model_name),
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


def _baseline_model_family(model_name: str) -> str:
    if model_name in {"historical_quantile", "rolling_quantile"}:
        return "empirical_quantile"
    if model_name == "ewma_vol_scaled":
        return "volatility_scaled"
    if model_name in {"garch_t", "gjr_garch_t"}:
        return "arch"
    if model_name == "gjr_garch_evt":
        return "arch_evt"
    return "benchmark_baseline"


def _forecast_one(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
    ewma_lambda: float | None = None,
    evt_threshold_quantile: float | None = None,
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
        return _ewma_forecast(
            train=train,
            tail_level=tail_level,
            lambda_=EWMA_MAIN_LAMBDA if ewma_lambda is None else float(ewma_lambda),
        )
    if model_name in {"garch_t", "gjr_garch_t", "gjr_garch_evt"}:
        return _arch_forecast(
            train=train,
            tail_level=tail_level,
            model_name=model_name,
            evt_threshold_quantile=evt_threshold_quantile,
        )
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
    evt_threshold_quantile: float | None = None,
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
            threshold_quantile=EVT_THRESHOLD_QUANTILE
            if evt_threshold_quantile is None
            else float(evt_threshold_quantile),
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
    min_standardized_losses: int | None = None,
    min_exceedances: int | None = None,
    evt_variant: str = "plain_mle",
    shape_cap: tuple[float, float] | None = None,
    shape_shrinkage_k: float | None = None,
) -> dict[str, object]:
    values = standardized_losses[np.isfinite(standardized_losses)]
    min_standardized_losses = (
        DEFAULT_MIN_TRAIN_ROWS if min_standardized_losses is None else int(min_standardized_losses)
    )
    min_exceedances = (
        DEFAULT_MIN_TRAIN_EXCEEDANCES if min_exceedances is None else int(min_exceedances)
    )
    if values.size < min_standardized_losses:
        raise PipelineRunError("EVT calibration has insufficient standardized losses")
    diagnostics = _evt_threshold_diagnostics(values)
    threshold = float(np.quantile(values, threshold_quantile))
    excesses = values[values > threshold] - threshold
    exceedance_indices = np.flatnonzero(values > threshold)
    if excesses.size < min_exceedances:
        raise PipelineRunError(f"EVT calibration has insufficient exceedances: {excesses.size}")
    shape: float | None = None
    scale: float | None = None
    shape_mle: float | None = None
    scale_mle: float | None = None
    shape_method = "empirical"
    cap_policy = "none"
    cap_hit = False
    evi = _unavailable_evi_anchor("not_used")
    ei = _unavailable_extremal_index("not_used", theta=1.0)
    scale_refit_status = "not_applicable"
    if tail_level <= threshold_quantile:
        var_z = float(np.quantile(values, tail_level))
        es_z = static_empirical_es(values, var_z)
        tail_method = "empirical_filtered_es"
    else:
        shape_mle, _, scale_mle = stats.genpareto.fit(excesses, floc=0.0)
        shape_mle = float(shape_mle)
        scale_mle = float(max(scale_mle, 1e-12))
        if not math.isfinite(scale_mle) or scale_mle <= 0.0:
            raise PipelineRunError("EVT calibration has invalid GPD scale")
        shape, scale = _select_evt_shape_and_scale(
            excesses=excesses,
            exceedance_indices=exceedance_indices,
            evi_sample=values,
            shape_mle=shape_mle,
            scale_mle=scale_mle,
            evt_variant=evt_variant,
            shape_cap=shape_cap,
            shape_shrinkage_k=shape_shrinkage_k,
        )
        shape_method = str(shape["shape_method"])
        cap_policy = str(shape["cap_policy"])
        cap_hit = bool(shape["cap_hit"])
        evi = cast(dict[str, object], shape["evi"])
        ei = cast(dict[str, object], shape["ei"])
        scale_refit_status = str(scale["scale_refit_status"])
        shape = _required_float(shape["shape_final"])
        scale = _required_float(scale["scale_final"])
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
    cap_sensitivity = _evt_cap_sensitivity(
        shape_mle=shape_mle,
        caps=(
            PIPELINE_CONFIG.model_policy.evt_shape_cap_conservative,
            PIPELINE_CONFIG.model_policy.evt_shape_cap_baseline,
            PIPELINE_CONFIG.model_policy.evt_shape_cap_loose,
        ),
    )
    threshold_sensitivity = _evt_threshold_sensitivity(
        values=values,
        tail_level=tail_level,
        threshold_grid=PIPELINE_CONFIG.model_policy.evt_threshold_grid,
        min_exceedances=min_exceedances,
        evt_variant=evt_variant,
        shape_cap=shape_cap,
        shape_shrinkage_k=shape_shrinkage_k,
    )
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "evt_shape": shape if tail_level > threshold_quantile else None,
        "evt_shape_bin": _evt_shape_bin(shape if tail_level > threshold_quantile else None),
        "evt_scale": scale if tail_level > threshold_quantile else None,
        "evt_variant": evt_variant,
        "evt_shape_method": shape_method,
        "evt_cap_policy": cap_policy,
        "evt_cap_hit": cap_hit,
        "evt_shape_mle": shape_mle,
        "evt_scale_mle": scale_mle,
        "evt_evi_status": evi.get("status"),
        "evt_ei_status": ei.get("status"),
        "evt_xi_evi_anchor": evi.get("xi_evi_anchor"),
        "evt_theta_hat": ei.get("theta_hat"),
        "evt_effective_exceedance_count": ei.get("effective_exceedance_count"),
        "evt_unibm_n_obs": evi.get("n_obs"),
        "evt_unibm_min_block_size": evi.get("min_block_size"),
        "evt_unibm_max_block_size": evi.get("max_block_size"),
        "evt_unibm_sliding_blocks": evi.get("sliding"),
        "evt_unibm_bootstrap_reps": evi.get("bootstrap_reps"),
        "evt_unibm_plateau_point_count": evi.get("plateau_point_count"),
        "evt_unibm_block_sizes_json": json.dumps(evi.get("block_sizes"), sort_keys=True),
        "evt_unibm_block_counts_json": json.dumps(evi.get("block_counts"), sort_keys=True),
        "evt_unibm_plateau_block_sizes_json": json.dumps(
            evi.get("plateau_block_sizes"), sort_keys=True
        ),
        "evt_unibm_plateau_block_counts_json": json.dumps(
            evi.get("plateau_block_counts"), sort_keys=True
        ),
        "evt_scale_refit_status": scale_refit_status,
        "evt_es_finite": bool(math.isfinite(float(max(var_z, es_z)))),
        "evt_evi_diagnostics_json": json.dumps(evi, sort_keys=True, default=str),
        "evt_ei_diagnostics_json": json.dumps(ei, sort_keys=True, default=str),
        "evt_cap_sensitivity_json": json.dumps(cap_sensitivity, sort_keys=True),
        "evt_threshold_sensitivity_json": json.dumps(
            threshold_sensitivity, sort_keys=True, default=str
        ),
        "threshold_diagnostics_json": json.dumps(diagnostics, sort_keys=True),
        "threshold_policy": PIPELINE_CONFIG.model_policy.evt_threshold_refresh,
        "threshold_smoothing": PIPELINE_CONFIG.model_policy.evt_threshold_smoothing,
        "threshold_selection": "pre_registered_fixed_empirical_quantile",
        "tail_method": tail_method,
    }


def _select_evt_shape_and_scale(
    *,
    excesses: np.ndarray,
    exceedance_indices: np.ndarray,
    evi_sample: np.ndarray,
    shape_mle: float,
    scale_mle: float,
    evt_variant: str,
    shape_cap: tuple[float, float] | None,
    shape_shrinkage_k: float | None,
) -> tuple[dict[str, object], dict[str, object]]:
    variant = evt_variant.strip().lower()
    evi = _unavailable_evi_anchor("not_used")
    ei = _unavailable_extremal_index("not_used", theta=1.0)
    shape_method = "fixed_loc_mle"
    if variant == "plain_mle":
        cap_policy = "none"
        cap_hit = False
        return (
            {
                "shape_final": float(shape_mle),
                "shape_method": shape_method,
                "cap_policy": cap_policy,
                "cap_hit": cap_hit,
                "evi": evi,
                "ei": ei,
            },
            {"scale_final": float(scale_mle), "scale_refit_status": "original_fixed_loc_mle"},
        )
    if variant == "unibm":
        evi = _estimate_unibm_evi_anchor(evi_sample)
        shape = _optional_float(evi.get("xi_evi_anchor"))
        if evi.get("status") != "ok" or shape is None:
            raise PipelineRunError(f"unavailable_evt_unibm: {evi.get('status')}")
        if not math.isfinite(shape):
            raise PipelineRunError("unavailable_evt_unibm: nonfinite_xi")
        scale = _refit_gpd_scale_fixed_shape(excesses, shape)
        return (
            {
                "shape_final": float(shape),
                "shape_method": "unibm_block_maxima_xi_fixed_shape_scale_refit",
                "cap_policy": "none",
                "cap_hit": False,
                "evi": evi,
                "ei": ei,
            },
            scale,
        )
    else:
        raise PipelineRunError(f"Unknown EVT variant: {evt_variant}")


def _evt_shape_bin(shape: object) -> str | None:
    value = _optional_float(shape)
    if value is None or not math.isfinite(value):
        return None
    if value <= -0.5:
        return "(-inf,-0.5]"
    if value <= -0.25:
        return "(-0.5,-0.25]"
    if value < 0.0:
        return "(-0.25,0)"
    if value < 0.75:
        return "[0,0.75)"
    if value < 1.0:
        return "[0.75,1)"
    if value < 1.5:
        return "[1,1.5)"
    return "[1.5,inf)"


def _estimate_unibm_evi_anchor(sample: np.ndarray) -> dict[str, object]:
    """Estimate GPD shape xi with the UniBM block-quantile scaling law."""
    try:
        values = np.asarray(sample, dtype=float).reshape(-1)
        values = values[np.isfinite(values)]
        n_obs = int(values.size)
        if n_obs < UNIBM_EVI_MIN_FINITE_VALUES:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_finite_values"),
                "n_obs": n_obs,
                "min_finite_values": UNIBM_EVI_MIN_FINITE_VALUES,
                "sliding": UNIBM_EVI_SLIDING_BLOCKS,
            }
        block_sizes = _unibm_block_sizes(values.size)
        if block_sizes.size < 5:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_block_grid"),
                "n_obs": n_obs,
                "min_block_size": None,
                "max_block_size": None,
                "block_sizes": [int(value) for value in block_sizes],
                "sliding": UNIBM_EVI_SLIDING_BLOCKS,
            }
        summaries: list[float] = []
        counts: list[int] = []
        for block_size in block_sizes:
            maxima = _sliding_block_maxima(values, int(block_size))
            counts.append(int(maxima.size))
            summary = (
                float(np.quantile(maxima, UNIBM_EVI_QUANTILE, method="median_unbiased"))
                if maxima.size
                else math.nan
            )
            summaries.append(summary)
        summary_array = np.asarray(summaries, dtype=float)
        count_array = np.asarray(counts, dtype=int)
        positive_mask = np.isfinite(summary_array) & (summary_array > 0.0) & (count_array > 0)
        eligible_mask = positive_mask & (
            count_array >= UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT
        )
        base_payload = {
            "n_obs": n_obs,
            "min_block_size": int(block_sizes[0]),
            "max_block_size": int(block_sizes[-1]),
            "block_sizes": [int(value) for value in block_sizes],
            "block_counts": [int(value) for value in count_array],
            "block_summary_values": [
                None if not math.isfinite(value) else float(value) for value in summary_array
            ],
            "positive_block_sizes": [int(value) for value in block_sizes[positive_mask]],
            "eligible_block_sizes": [int(value) for value in block_sizes[eligible_mask]],
            "min_block_maxima_per_plateau_point": UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT,
            "sliding": UNIBM_EVI_SLIDING_BLOCKS,
            "bootstrap_reps": 0,
        }
        if int(np.sum(positive_mask)) < UNIBM_EVI_MIN_POSITIVE_BLOCK_SUMMARIES:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_positive_summaries"),
                **base_payload,
            }
        if int(np.sum(eligible_mask)) < UNIBM_EVI_MIN_PLATEAU_POINTS:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_eligible_block_counts"),
                **base_payload,
            }
        x = np.log(block_sizes[eligible_mask].astype(float))
        y = np.log(summary_array[eligible_mask])
        selected = _unibm_select_plateau_window(x, y, min_points=UNIBM_EVI_MIN_PLATEAU_POINTS)
        x_window = x[selected["start"] : selected["stop"]]
        y_window = y[selected["start"] : selected["stop"]]
        eligible_sizes = block_sizes[eligible_mask]
        eligible_counts = count_array[eligible_mask]
        plateau_counts = eligible_counts[selected["start"] : selected["stop"]]
        if plateau_counts.size < UNIBM_EVI_MIN_PLATEAU_POINTS:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_plateau_points"),
                **base_payload,
            }
        if int(np.min(plateau_counts)) < UNIBM_EVI_MIN_BLOCK_MAXIMA_PER_PLATEAU_POINT:
            return {
                **_unavailable_evi_anchor("unavailable_unibm_insufficient_plateau_block_counts"),
                **base_payload,
            }
        fit = _unibm_fit_linear_model(x_window, y_window)
        slope = _optional_float(fit.get("slope"))
        if slope is None or not math.isfinite(slope):
            return {
                **_unavailable_evi_anchor("unavailable_unibm_nonfinite_slope"),
                **base_payload,
            }
        se = _optional_float(fit.get("standard_error"))
        ci = (
            [float(slope - 1.96 * se), float(slope + 1.96 * se)]
            if se is not None and math.isfinite(se)
            else [None, None]
        )
        return {
            **base_payload,
            "status": "ok",
            "primary_estimator": "unibm_block_quantile_scaling",
            "xi_evi_anchor": float(slope),
            "quantile": UNIBM_EVI_QUANTILE,
            "plateau_block_sizes": [
                int(value) for value in eligible_sizes[selected["start"] : selected["stop"]]
            ],
            "plateau_block_counts": [int(value) for value in plateau_counts],
            "plateau_point_count": int(plateau_counts.size),
            "plateau_score": float(selected["score"]),
            "intercept": _optional_float(fit.get("intercept")),
            "slope": float(slope),
            "standard_error": se,
            "confidence_interval": ci,
            "method_note": (
                "POT-GPD with UniBM block-maxima-derived shape: sliding block-maxima "
                "median-quantile log-log scaling; the selected-plateau slope is GPD "
                "shape xi, not reciprocal Pareto alpha."
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return _unavailable_evi_anchor(f"unavailable_unibm_exception:{type(exc).__name__}")


def _unibm_block_sizes(n_obs: int) -> np.ndarray:
    if n_obs < UNIBM_EVI_MIN_FINITE_VALUES:
        return np.asarray([], dtype=int)
    min_block_size = max(5, int(math.ceil(n_obs**0.2)))
    exponent_cap = int(math.floor(n_obs**0.55))
    disjoint_cap = int(math.floor(n_obs / 15))
    max_block_size = min(n_obs, max(min_block_size + 4, min(exponent_cap, disjoint_cap)))
    num_step = min(32, max(10, max_block_size - min_block_size + 1))
    grid = np.geomspace(min_block_size, max_block_size, num=num_step)
    block_sizes = np.unique(np.clip(np.rint(grid).astype(int), min_block_size, max_block_size))
    return block_sizes[(block_sizes > 1) & (block_sizes <= n_obs)]


def _sliding_block_maxima(values: np.ndarray, block_size: int) -> np.ndarray:
    if block_size < 2 or values.size < block_size:
        return np.asarray([], dtype=float)
    windows = np.lib.stride_tricks.sliding_window_view(values, block_size)
    finite = np.all(np.isfinite(windows), axis=1)
    if not np.any(finite):
        return np.asarray([], dtype=float)
    return np.max(windows[finite], axis=1)


def _unibm_select_plateau_window(
    log_block_sizes: np.ndarray,
    log_values: np.ndarray,
    *,
    min_points: int = 5,
    trim_fraction: float = 0.15,
    curvature_penalty: float = 2.0,
) -> dict[str, object]:
    n = int(log_block_sizes.size)
    if n < min_points:
        raise PipelineRunError("UniBM EVI has insufficient positive block summaries")
    lo = int(math.floor(n * trim_fraction))
    hi = n - lo
    lo = min(lo, max(n - min_points, 0))
    if hi - lo < min_points:
        lo = 0
        hi = n
    slopes = np.diff(log_values) / np.diff(log_block_sizes)
    best: tuple[float, int, int] | None = None
    for start in range(lo, hi - min_points + 1):
        for stop in range(start + min_points, hi + 1):
            x_window = log_block_sizes[start:stop]
            y_window = log_values[start:stop]
            fit = _unibm_fit_linear_model(x_window, y_window)
            fitted = _required_float(fit["intercept"]) + _required_float(fit["slope"]) * x_window
            mse = float(np.mean((y_window - fitted) ** 2))
            if stop - start > 2:
                curvature = float(np.mean(np.abs(np.diff(slopes[start : stop - 1]))))
            else:
                curvature = 0.0
            score = (mse + curvature_penalty * curvature) / math.sqrt(float(stop - start))
            if best is None or score < best[0]:
                best = (score, start, stop)
    if best is None:
        raise PipelineRunError("UniBM EVI plateau selection failed")
    return {"score": float(best[0]), "start": int(best[1]), "stop": int(best[2])}


def _unibm_fit_linear_model(x: np.ndarray, y: np.ndarray) -> dict[str, object]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x_design = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(x_design, y, rcond=None)
    fitted = x_design @ beta
    resid = y - fitted
    normal_inv = np.linalg.pinv(x_design.T @ x_design)
    meat = x_design.T @ np.diag(resid**2) @ x_design
    cov_beta = normal_inv @ meat @ normal_inv
    return {
        "intercept": float(beta[0]),
        "slope": float(beta[1]),
        "standard_error": float(math.sqrt(max(float(cov_beta[1, 1]), 0.0))),
    }


def _refit_gpd_scale_fixed_shape(excesses: np.ndarray, shape: float) -> dict[str, object]:
    try:
        _, _, scale = stats.genpareto.fit(excesses, f0=float(shape), floc=0.0)
        scale = float(max(scale, 1e-12))
    except Exception as exc:
        raise PipelineRunError("EVT fixed-shape GPD scale refit failed") from exc
    if shape < 0 and np.max(excesses) >= -scale / shape:
        raise PipelineRunError("EVT fixed-shape GPD support violation")
    return {"scale_final": scale, "scale_refit_status": "fixed_shape_mle_completed"}


def _estimate_evi_anchor(excesses: np.ndarray) -> dict[str, object]:
    try:
        ordered = np.sort(excesses[np.isfinite(excesses) & (excesses > 0)])[::-1]
        if ordered.size < 8:
            return _unavailable_evi_anchor("unavailable_insufficient_positive_excesses")
        k_values = _candidate_tail_counts(ordered.size)
        dedh = _evi_path_result("dedh_moment", k_values, _dedh_moment_path(ordered, k_values))
        hill = _evi_path_result("hill", k_values, _hill_path(ordered, k_values))
        pickands = _evi_path_result("pickands", k_values, _pickands_path(ordered, k_values))
        anchor = _optional_float(dedh.get("xi_hat"))
        if anchor is None:
            return _unavailable_evi_anchor("unavailable_dedh_no_finite_path")
        cross_checks = [
            value
            for value in (
                _optional_float(hill.get("xi_hat")),
                _optional_float(pickands.get("xi_hat")),
            )
            if value is not None
        ]
        if cross_checks and max(abs(anchor - value) for value in cross_checks) > 0.75:
            return {
                **_unavailable_evi_anchor("unavailable_anchor_path_disagreement"),
                "dedh": dedh,
                "hill": hill,
                "pickands": pickands,
            }
        return {
            "status": "ok",
            "primary_estimator": "dedh_moment",
            "xi_evi_anchor": float(anchor),
            "dedh": dedh,
            "hill": hill,
            "pickands": pickands,
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return _unavailable_evi_anchor(f"unavailable_exception:{type(exc).__name__}")


def _estimate_extremal_index(indices: np.ndarray, excess_count: int) -> dict[str, object]:
    try:
        times = np.diff(np.asarray(indices, dtype=int)).astype(float)
        if times.size < 2:
            return _unavailable_extremal_index("unavailable_insufficient_interexceedance_times")
        theta = _ferro_segers_theta(times)
        k_gaps = _k_gaps_theta(
            times,
            exceedance_rate=max(excess_count, 1) / max(indices[-1] + 1, 1),
        )
        return {
            "status": "ok",
            "primary_estimator": "ferro_segers",
            "theta_hat": theta,
            "effective_exceedance_count": float(max(theta * float(excess_count), 1.0)),
            "k_gaps_theta_hat": k_gaps,
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return _unavailable_extremal_index(f"unavailable_exception:{type(exc).__name__}")


def _unavailable_evi_anchor(status: str) -> dict[str, object]:
    return {
        "status": status,
        "primary_estimator": PIPELINE_CONFIG.model_policy.evt_evi_primary_estimator,
        "xi_evi_anchor": None,
    }


def _unavailable_extremal_index(status: str, *, theta: float = 1.0) -> dict[str, object]:
    return {
        "status": status,
        "primary_estimator": PIPELINE_CONFIG.model_policy.evt_ei_primary_estimator,
        "theta_hat": float(theta),
        "effective_exceedance_count": None,
    }


def _candidate_tail_counts(n_obs: int) -> np.ndarray:
    upper = int(min(max(10, int(np.floor(0.25 * n_obs))), n_obs - 3))
    lower = int(min(8, upper))
    if upper <= lower:
        return np.array([lower], dtype=int)
    grid = np.unique(np.round(np.geomspace(lower, upper, num=24)).astype(int))
    return grid[(grid >= lower) & (grid <= upper)]


def _evi_path_result(method: str, k_values: np.ndarray, path: np.ndarray) -> dict[str, object]:
    mask = np.isfinite(path)
    if not np.any(mask):
        return {"method": method, "status": "unavailable_no_finite_path", "xi_hat": None}
    levels = k_values[mask]
    values = path[mask]
    chosen_k, window = _select_stable_window(levels, values)
    chosen_idx = int(np.argmin(np.abs(levels - chosen_k)))
    return {
        "method": method,
        "status": "ok",
        "xi_hat": float(values[chosen_idx]),
        "selected_k": int(levels[chosen_idx]),
        "stable_window": [int(window[0]), int(window[1])],
        "path_k": [int(value) for value in levels],
        "path_xi": [float(value) for value in values],
    }


def _select_stable_window(levels: np.ndarray, values: np.ndarray) -> tuple[int, tuple[int, int]]:
    min_window = min(4, int(levels.size))
    if levels.size <= min_window:
        return int(np.median(levels)), (int(levels[0]), int(levels[-1]))
    best_score = math.inf
    best_slice = slice(0, min_window)
    for start in range(0, levels.size - min_window + 1):
        stop = start + min_window
        window_values = values[start:stop]
        local_var = float(np.mean((window_values - np.mean(window_values)) ** 2))
        curvature = (
            float(np.mean(np.abs(np.diff(window_values, n=2)))) if window_values.size >= 3 else 0.0
        )
        score = local_var + 0.5 * curvature
        if score < best_score:
            best_score = score
            best_slice = slice(start, stop)
    selected = levels[best_slice]
    return int(np.round(np.median(selected))), (int(selected[0]), int(selected[-1]))


def _hill_path(ordered: np.ndarray, k_values: np.ndarray) -> np.ndarray:
    log_ordered = np.log(ordered)
    estimates = []
    for k in k_values:
        threshold = log_ordered[k]
        estimates.append(float(np.mean(log_ordered[:k] - threshold)))
    return np.asarray(estimates, dtype=float)


def _pickands_path(ordered: np.ndarray, k_values: np.ndarray) -> np.ndarray:
    estimates = []
    for k in k_values:
        if 4 * k > ordered.size:
            estimates.append(np.nan)
            continue
        a = ordered[k - 1] - ordered[2 * k - 1]
        b = ordered[2 * k - 1] - ordered[4 * k - 1]
        estimates.append(float(np.log(a / b) / np.log(2.0)) if a > 0 and b > 0 else np.nan)
    return np.asarray(estimates, dtype=float)


def _dedh_moment_path(ordered: np.ndarray, k_values: np.ndarray) -> np.ndarray:
    log_ordered = np.log(ordered)
    estimates = []
    for k in k_values:
        threshold = log_ordered[k]
        log_excess = log_ordered[:k] - threshold
        m1 = float(np.mean(log_excess))
        m2 = float(np.mean(log_excess**2))
        denom = 1.0 - (m1 * m1) / m2 if m2 > 0 else math.nan
        estimates.append(float(m1 + 1.0 - 0.5 / denom) if abs(denom) > 1e-10 else np.nan)
    return np.asarray(estimates, dtype=float)


def _ferro_segers_theta(times: np.ndarray) -> float:
    t = times[np.isfinite(times) & (times > 0)]
    if t.size < 2:
        raise PipelineRunError("Ferro-Segers requires at least two inter-exceedance times")
    if np.max(t) <= 2.0:
        numerator = 2.0 * float(np.mean(t)) ** 2
        denominator = float(np.mean(t**2))
    else:
        numerator = 2.0 * float(np.mean(t - 1.0)) ** 2
        denominator = float(np.mean((t - 1.0) * (t - 2.0)))
    return float(np.clip(numerator / max(denominator, 1e-12), 1e-12, 1.0))


def _k_gaps_theta(times: np.ndarray, *, exceedance_rate: float) -> float | None:
    best_theta: float | None = None
    best_ll = -math.inf
    for run_k in (1, 2):
        gaps = np.maximum(times - float(run_k), 0.0) * float(exceedance_rate)
        gaps = gaps[np.isfinite(gaps)]
        if gaps.size < 2:
            continue
        zero_count = int(np.sum(gaps <= 0))
        positive = gaps[gaps > 0]
        for theta in np.linspace(0.01, 0.99, 99):
            ll = zero_count * math.log(max(1.0 - theta, 1e-12))
            if positive.size:
                ll += positive.size * 2.0 * math.log(theta) - theta * float(np.sum(positive))
            if ll > best_ll:
                best_ll = ll
                best_theta = float(theta)
    return best_theta


def _clip_with_flag(value: float, cap: tuple[float, float]) -> tuple[float, bool]:
    clipped = float(np.clip(value, cap[0], cap[1]))
    return clipped, bool(abs(clipped - value) > 1e-12)


def _cap_policy_name(cap: tuple[float, float]) -> str:
    return f"clip_{cap[0]:.2f}_{cap[1]:.2f}"


def _evt_cap_sensitivity(
    *,
    shape_mle: float | None,
    caps: tuple[tuple[float, float], ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cap in caps:
        if shape_mle is None:
            rows.append({"cap": list(cap), "shape": None, "cap_hit": None, "es_available": None})
            continue
        shape, cap_hit = _clip_with_flag(float(shape_mle), cap)
        rows.append(
            {
                "cap": list(cap),
                "shape": shape,
                "cap_hit": cap_hit,
                "es_available": shape < 1.0,
            }
        )
    return rows


def _evt_threshold_sensitivity(
    *,
    values: np.ndarray,
    tail_level: float,
    threshold_grid: tuple[float, ...],
    min_exceedances: int,
    evt_variant: str,
    shape_cap: tuple[float, float] | None,
    shape_shrinkage_k: float | None,
) -> list[dict[str, object]]:
    finite = values[np.isfinite(values)]
    rows: list[dict[str, object]] = []
    for threshold_quantile in threshold_grid:
        q = float(threshold_quantile)
        base: dict[str, object] = {
            "threshold_quantile": q,
            "tail_level": float(tail_level),
            "evt_variant": evt_variant,
        }
        if finite.size == 0:
            rows.append({**base, "status": "unavailable_no_finite_standardized_losses"})
            continue
        threshold = float(np.quantile(finite, q))
        if tail_level <= q:
            rows.append(
                {
                    **base,
                    "status": "not_applicable_threshold_not_below_tail_level",
                    "threshold_value": threshold,
                    "evt_exceedance_count": int(np.sum(finite > threshold)),
                }
            )
            continue
        try:
            excesses = finite[finite > threshold] - threshold
            exceedance_indices = np.flatnonzero(finite > threshold)
            if excesses.size < min_exceedances:
                rows.append(
                    {
                        **base,
                        "status": "unavailable_insufficient_exceedances",
                        "threshold_value": threshold,
                        "evt_exceedance_count": int(excesses.size),
                        "evt_min_exceedances": int(min_exceedances),
                    }
                )
                continue
            shape_mle, _, scale_mle = stats.genpareto.fit(excesses, floc=0.0)
            shape_mle = float(shape_mle)
            scale_mle = float(max(scale_mle, 1e-12))
            selected_shape, selected_scale = _select_evt_shape_and_scale(
                excesses=excesses,
                exceedance_indices=exceedance_indices,
                evi_sample=finite,
                shape_mle=shape_mle,
                scale_mle=scale_mle,
                evt_variant=evt_variant,
                shape_cap=shape_cap,
                shape_shrinkage_k=shape_shrinkage_k,
            )
            shape = _required_float(selected_shape["shape_final"])
            scale = _required_float(selected_scale["scale_final"])
            exceedance_probability = excesses.size / finite.size
            target_tail_probability = max(1.0 - tail_level, 1e-12)
            ratio = max(exceedance_probability / target_tail_probability, 1.0)
            if abs(shape) < 1e-8:
                var_z = threshold + scale * math.log(ratio)
            else:
                var_z = threshold + scale * (ratio**shape - 1.0) / shape
            es_z: float | None = None
            status = "ok"
            if shape < 1.0:
                es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
            else:
                status = "unavailable_infinite_es"
            evi = cast(dict[str, object], selected_shape.get("evi") or {})
            ei = cast(dict[str, object], selected_shape.get("ei") or {})
            rows.append(
                {
                    **base,
                    "status": status,
                    "threshold_value": threshold,
                    "evt_exceedance_count": int(excesses.size),
                    "evt_shape": shape,
                    "evt_shape_bin": _evt_shape_bin(shape),
                    "evt_scale": scale,
                    "evt_shape_mle": shape_mle,
                    "evt_scale_mle": scale_mle,
                    "evt_shape_method": selected_shape.get("shape_method"),
                    "evt_cap_policy": selected_shape.get("cap_policy"),
                    "evt_cap_hit": selected_shape.get("cap_hit"),
                    "evt_xi_evi_anchor": evi.get("xi_evi_anchor"),
                    "evt_theta_hat": ei.get("theta_hat"),
                    "evt_effective_exceedance_count": ei.get("effective_exceedance_count"),
                    "evt_unibm_n_obs": evi.get("n_obs"),
                    "evt_unibm_min_block_size": evi.get("min_block_size"),
                    "evt_unibm_max_block_size": evi.get("max_block_size"),
                    "evt_unibm_sliding_blocks": evi.get("sliding"),
                    "evt_unibm_plateau_point_count": evi.get("plateau_point_count"),
                    "standardized_var": float(var_z),
                    "standardized_es": None if es_z is None else float(max(var_z, es_z)),
                    "evt_es_finite": es_z is not None and math.isfinite(es_z),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive diagnostic path
            rows.append(
                {
                    **base,
                    "status": f"unavailable_exception:{type(exc).__name__}",
                    "threshold_value": threshold,
                }
            )
    return rows
