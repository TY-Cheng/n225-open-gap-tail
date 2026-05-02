# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    build_feature_matrix_gate_records,
    cast,
    date,
    DEFAULT_MIN_TRAIN_EXCEEDANCES,
    DEFAULT_MIN_TRAIN_ROWS,
    EVT_MIN_EXCEEDANCES_95,
    EVT_MIN_STANDARDIZED_LOSSES_95,
    EVT_SHAPE_CAP_BASELINE,
    EVT_SHAPE_SHRINKAGE_K,
    EVT_THRESHOLD_QUANTILE,
    find_oos_start_diagnostics,
    LOCATION_SCALE_MIN_ES_EXCEEDANCES_95,
    math,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MIN_OOF_TRAIN_ROWS,
    ML_TAIL_POT_GPD_CAPPED_MLE_MODEL,
    ML_TAIL_POT_GPD_EI_WEIGHTED_MODEL,
    ML_TAIL_POT_GPD_EVI_SHRINK_MODEL,
    ML_TAIL_POT_GPD_MODEL_NAMES,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_STABILIZED_MODEL,
    ML_TAIL_REFIT_FREQUENCY,
    ML_TAIL_SCALE_FLOOR,
    normalize_tail_side,
    np,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
    pl,
    PRIMARY_TAIL_SIDE,
    realized_loss_for_tail_side,
    stable_hash,
    validate_forecast_values,
    validate_worker_payload,
    warnings,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.data_lake.artifacts import _forecast_shard_id
from n225_open_gap_tail.models.benchmark import _pot_gpd_standardized_tail
from n225_open_gap_tail.models.ml_tail_oof import (
    _feature_matrix,
    _fit_lgb_regression_model,
    _ml_tail_extended_forecast_fields,
    _ml_tail_location_scale_diagnostic,
    _ml_tail_oof_location_scale,
    _ml_tail_seed,
    _ml_tail_unavailable_feature_forecast,
    _ml_tail_unavailable_status,
    _predict_ml_tail_location_scale_forecast,
    _unavailable_active_features,
)
from n225_open_gap_tail.panel.build import ml_tail_feature_columns_for_information_set


def _evaluate_ml_tail_shard(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    coverage_path = Path(str(payload["coverage_path"]))
    tail_side = normalize_tail_side(payload.get("tail_side"))
    tail_level = _required_float(payload["tail_level"])
    target_family = str(
        payload.get("target_family") or PIPELINE_CONFIG.target_policy.primary_target_family
    )
    information_set = str(payload["information_set"])
    model_name = str(payload["model_name"])
    refit_frequency = str(payload.get("refit_frequency") or ML_TAIL_REFIT_FREQUENCY)
    coverage_rows = pl.read_parquet(coverage_path).to_dicts()
    candidate_features = ml_tail_feature_columns_for_information_set(
        coverage_rows,
        information_set=information_set,
    )
    panel_rows = pl.read_parquet(panel_path).to_dicts()
    rows = build_ml_tail_modeling_rows(panel_rows, candidate_features, tail_side=tail_side)
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(
                        model_name,
                        tail_level,
                        target_family=target_family,
                        tail_side=tail_side,
                        information_set=information_set,
                        refit_frequency=refit_frequency,
                    ),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "oos_failure_reason": oos_diagnostics["failure_reason"],
                    "train_n": oos_diagnostics["train_n"],
                    "train_exceedances": oos_diagnostics["train_exceedances"],
                    "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                    "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                    "target_family": target_family,
                    "refit_frequency": refit_frequency,
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
            ],
            "failures": [],
        }
    return _forecast_ml_tail_lightgbm_sequence(
        rows=rows,
        model_name=model_name,
        information_set=information_set,
        candidate_features=candidate_features,
        tail_side=tail_side,
        tail_level=tail_level,
        oos_start=oos_start,
    )


def build_ml_tail_modeling_rows(
    panel_rows: list[dict[str, object]],
    candidate_features: list[str],
    *,
    tail_side: str = PRIMARY_TAIL_SIDE,
) -> list[dict[str, object]]:
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    losses: list[float] = []
    gaps: list[float] = []
    output: list[dict[str, object]] = []
    for row in rows:
        forecast_date = str(row.get("forecast_date") or "")
        if not forecast_date:
            continue
        try:
            parsed_date = date.fromisoformat(forecast_date)
        except ValueError:
            continue
        loss = realized_loss_for_tail_side(row, tail_side)
        gap = _optional_float(row.get("gap_t"))
        record: dict[str, object] = {
            "forecast_date": forecast_date,
            "target_family": row.get("target_family") or "full_gap_settle_to_open",
            "tail_side": tail_side,
            "clean_sample": row.get("clean_sample"),
            "realized_loss": loss,
            "gap_t": gap,
            "dst_regime": row.get("dst_regime"),
            "absorption_regime": row.get("absorption_regime"),
            "vix_level": _optional_float(row.get("fred_vixcls_level"))
            if _optional_float(row.get("fred_vixcls_level")) is not None
            else _optional_float(row.get("cboe_vix_close")),
        }
        record.update(_history_feature_values(losses=losses, gaps=gaps, forecast_date=parsed_date))
        record["calendar_dst_edt"] = 1.0 if row.get("dst_regime") == "EDT" else 0.0
        record["calendar_absorption_post_us_close"] = (
            1.0 if row.get("absorption_regime") == "post_us_close_night_absorption" else 0.0
        )
        for feature in candidate_features:
            if feature in record:
                continue
            record[feature] = _optional_float(row.get(feature))
        output.append(record)
        if row.get("clean_sample") is True and loss is not None and math.isfinite(loss):
            losses.append(loss)
            if gap is not None and math.isfinite(gap):
                gaps.append(gap)
    return output


def _history_feature_values(
    *,
    losses: list[float],
    gaps: list[float],
    forecast_date: date,
) -> dict[str, object]:
    month_angle = 2.0 * math.pi * (forecast_date.month - 1) / 12.0
    values: dict[str, object] = {
        "loss_lag_1": losses[-1] if len(losses) >= 1 else None,
        "loss_lag_2": losses[-2] if len(losses) >= 2 else None,
        "loss_lag_5": losses[-5] if len(losses) >= 5 else None,
        "gap_lag_1": gaps[-1] if len(gaps) >= 1 else None,
        "calendar_month_sin": math.sin(month_angle),
        "calendar_month_cos": math.cos(month_angle),
    }
    for window in (5, 20):
        slice_ = losses[-window:]
        values[f"loss_roll_mean_{window}"] = float(np.mean(slice_)) if slice_ else None
    for window in (20, 60):
        slice_ = losses[-window:]
        values[f"loss_roll_std_{window}"] = (
            float(np.std(slice_, ddof=1)) if len(slice_) >= 2 else None
        )
    tail_window = losses[-252:]
    values["loss_roll_q95_252"] = float(np.quantile(tail_window, 0.95)) if tail_window else None
    return values


def _forecast_ml_tail_lightgbm_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    information_set: str,
    candidate_features: list[str],
    tail_level: float,
    oos_start: str,
    tail_side: str = PRIMARY_TAIL_SIDE,
) -> dict[str, list[dict[str, object]]]:
    try:
        import lightgbm as lgb
    except Exception as exc:  # pragma: no cover - dependency/environment
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_import_error",
                    "failure_reason": str(exc),
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
            ],
            "failures": [],
        }
    if model_name != ML_TAIL_DIRECT_QUANTILE_MODEL:
        return _forecast_ml_tail_location_scale_sequence(
            rows=rows,
            model_name=model_name,
            information_set=information_set,
            candidate_features=candidate_features,
            tail_level=tail_level,
            tail_side=tail_side,
            oos_start=oos_start,
            lgb=lgb,
        )
    clean = [
        row
        for row in rows
        if row.get("clean_sample") is True
        and (loss := _optional_float(row.get("realized_loss"))) is not None
        and math.isfinite(loss)
    ]
    clean.sort(key=lambda row: str(row["forecast_date"]))
    start_date = date.fromisoformat(oos_start)
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    cached_model: Any | None = None
    cached_refit_month: str | None = None
    cached_active_features: list[str] = []
    cached_gate: dict[str, object] = {}
    cached_train_n = 0
    cached_train_start: object = None
    cached_train_end: object = None
    cached_excess_mean = 0.0
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train_rows = clean[:index]
        if len(train_rows) < DEFAULT_MIN_TRAIN_ROWS:
            continue
        refit_month = forecast_date.strftime("%Y-%m")
        if cached_model is None or cached_refit_month != refit_month:
            try:
                train_frame = pl.DataFrame(train_rows, infer_schema_length=None)
                gate = build_feature_matrix_gate_records(train_frame, candidate_features)
                active_features = cast(list[str], gate["active_features"])
                if not active_features:
                    raise PipelineRunError(
                        "ML tail LightGBM has no active features after training gate"
                    )
                x_train = _feature_matrix(train_frame, active_features)
                y_train: Any = np.array(
                    [_required_float(item["realized_loss"]) for item in train_rows],
                    dtype=float,
                )
                model = lgb.LGBMRegressor(
                    objective="quantile",
                    alpha=tail_level,
                    n_estimators=80,
                    learning_rate=0.05,
                    num_leaves=15,
                    min_child_samples=20,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    random_state=int(tail_level * 10_000) + len(information_set),
                    num_threads=1,
                    verbosity=-1,
                )
                model.fit(x_train, y_train)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="X does not have valid feature names",
                        category=UserWarning,
                    )
                    train_var: Any = np.asarray(model.predict(x_train), dtype=float)
                exceedance_excess = y_train[y_train > train_var] - train_var[y_train > train_var]
                cached_excess_mean = (
                    float(np.mean(exceedance_excess)) if exceedance_excess.size else 0.0
                )
                cached_model = model
                cached_refit_month = refit_month
                cached_active_features = active_features
                cached_gate = gate
                cached_train_n = int(y_train.size)
                cached_train_start = train_rows[0]["forecast_date"]
                cached_train_end = train_rows[-1]["forecast_date"]
                diagnostics.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "train_n": cached_train_n,
                        "optimizer_status": "lightgbm_fit_completed",
                        "convergence_code": 0,
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "candidate_feature_hash": gate["candidate_feature_hash"],
                        "active_feature_hash": gate["active_feature_hash"],
                        "dropped_features_json": gate["dropped_features_json"],
                        "drop_reason": None,
                        "training_missingness": gate["training_missingness_json"],
                        "training_variance": gate["training_variance_json"],
                        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                        "refit_month": refit_month,
                    }
                )
            except Exception as exc:  # pragma: no cover - synthetic tests cover status path
                failures.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "fit_status": "unavailable_optimizer_failed",
                        "failure_reason": str(exc),
                    }
                )
                cached_model = None
                cached_refit_month = None
                continue
        if cached_model is None:
            continue
        try:
            unavailable_features = _unavailable_active_features(row, cached_active_features)
            if unavailable_features:
                realized_loss = _required_float(row["realized_loss"])
                forecasts.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "tail_side": tail_side,
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_level": tail_level,
                        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                        "var_forecast": None,
                        "es_forecast": None,
                        "es_companion_type": "empirical_excess_es_companion",
                        "realized_loss": realized_loss,
                        "var_breach": None,
                        "is_valid_forecast": False,
                        "invalid_reason": "unavailable_feature_not_valid_at_cutoff",
                        "train_start": cached_train_start,
                        "train_end": cached_train_end,
                        "train_n": cached_train_n,
                        "fit_status": "unavailable_feature_not_valid_at_cutoff",
                        "failure_reason": ",".join(unavailable_features),
                        "runtime_seconds": None,
                        "dst_regime": row.get("dst_regime"),
                        "absorption_regime": row.get("absorption_regime"),
                        "vix_level": row.get("vix_level"),
                        "active_feature_hash": cached_gate.get("active_feature_hash"),
                        **_ml_tail_extended_forecast_fields(),
                    }
                )
                continue
            predict_frame = pl.DataFrame([row], infer_schema_length=None)
            x_predict = _feature_matrix(predict_frame, cached_active_features)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="X does not have valid feature names",
                    category=UserWarning,
                )
                var_forecast = float(np.asarray(cached_model.predict(x_predict), dtype=float)[0])
            es_forecast = float(max(var_forecast, var_forecast + cached_excess_mean))
            realized_loss = _required_float(row["realized_loss"])
            valid, invalid_reason = validate_forecast_values(var_forecast, es_forecast)
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": row.get("target_family") or "full_gap_settle_to_open",
                    "tail_side": tail_side,
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": "empirical_excess_es_companion",
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": valid,
                    "invalid_reason": invalid_reason,
                    "train_start": cached_train_start,
                    "train_end": cached_train_end,
                    "train_n": cached_train_n,
                    "fit_status": "ok" if valid else "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "runtime_seconds": None,
                    "dst_regime": row.get("dst_regime"),
                    "absorption_regime": row.get("absorption_regime"),
                    "vix_level": row.get("vix_level"),
                    "active_feature_hash": cached_gate.get("active_feature_hash"),
                    **_ml_tail_extended_forecast_fields(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive failure log
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_prediction_failed",
                    "failure_reason": str(exc),
                }
            )
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _forecast_ml_tail_location_scale_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    information_set: str,
    candidate_features: list[str],
    tail_level: float,
    oos_start: str,
    lgb: Any,
    tail_side: str = PRIMARY_TAIL_SIDE,
) -> dict[str, list[dict[str, object]]]:
    clean = [
        row
        for row in rows
        if row.get("clean_sample") is True
        and (loss := _optional_float(row.get("realized_loss"))) is not None
        and math.isfinite(loss)
    ]
    clean.sort(key=lambda row: str(row["forecast_date"]))
    start_date = date.fromisoformat(oos_start)
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    cached_bundle: dict[str, object] | None = None
    cached_refit_month: str | None = None
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train_rows = clean[:index]
        if len(train_rows) < DEFAULT_MIN_TRAIN_ROWS:
            continue
        refit_month = forecast_date.strftime("%Y-%m")
        if cached_bundle is None or cached_refit_month != refit_month:
            cached_refit_month = refit_month
            try:
                cached_bundle = _fit_ml_tail_location_scale_bundle(
                    train_rows=train_rows,
                    candidate_features=candidate_features,
                    model_name=model_name,
                    information_set=information_set,
                    tail_level=tail_level,
                    lgb=lgb,
                )
                diagnostics.append(
                    _ml_tail_location_scale_diagnostic(
                        row=row,
                        model_name=model_name,
                        information_set=information_set,
                        tail_side=tail_side,
                        tail_level=tail_level,
                        refit_month=refit_month,
                        bundle=cached_bundle,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive path covered by statuses
                status = _ml_tail_unavailable_status(exc)
                cached_bundle = {
                    "fit_status": status,
                    "failure_reason": str(exc),
                    "refit_month": refit_month,
                    "train_n": len(train_rows),
                    "train_start": train_rows[0]["forecast_date"],
                    "train_end": train_rows[-1]["forecast_date"],
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
                diagnostics.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "fit_status": status,
                        "failure_reason": str(exc),
                        "train_n": len(train_rows),
                        "train_start": train_rows[0]["forecast_date"],
                        "train_end": train_rows[-1]["forecast_date"],
                        "candidate_feature_hash": stable_hash(candidate_features),
                        "active_feature_hash": stable_hash([]),
                        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                        "refit_month": refit_month,
                    }
                )
        if cached_bundle is None or cached_bundle.get("fit_status") != "ok":
            continue
        try:
            active_features = cast(list[str], cached_bundle["active_features"])
            scale_active_features = cast(list[str], cached_bundle["scale_active_features"])
            unavailable_features = _unavailable_active_features(
                row,
                list(dict.fromkeys((*active_features, *scale_active_features))),
            )
            if unavailable_features:
                forecasts.append(
                    _ml_tail_unavailable_feature_forecast(
                        row=row,
                        model_name=model_name,
                        information_set=information_set,
                        tail_side=tail_side,
                        tail_level=tail_level,
                        bundle=cached_bundle,
                        unavailable_features=unavailable_features,
                    )
                )
                continue
            forecast = _predict_ml_tail_location_scale_forecast(
                row=row,
                model_name=model_name,
                information_set=information_set,
                tail_side=tail_side,
                tail_level=tail_level,
                bundle=cached_bundle,
            )
            forecasts.append(forecast)
        except Exception as exc:  # pragma: no cover - defensive failure log
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": _ml_tail_unavailable_status(exc),
                    "failure_reason": str(exc),
                }
            )
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _fit_ml_tail_location_scale_bundle(
    *,
    train_rows: list[dict[str, object]],
    candidate_features: list[str],
    model_name: str,
    information_set: str,
    tail_level: float,
    lgb: Any,
) -> dict[str, object]:
    oof = _ml_tail_oof_location_scale(
        train_rows=train_rows,
        candidate_features=candidate_features,
        information_set=information_set,
        tail_level=tail_level,
        lgb=lgb,
    )
    z_oof = cast(np.ndarray, oof["standardized_losses"])
    z_oof = z_oof[np.isfinite(z_oof)]
    if z_oof.size < ML_TAIL_MIN_OOF_TRAIN_ROWS:
        raise PipelineRunError(f"unavailable_oof_standardization_insufficient_sample: {z_oof.size}")
    standardized_var: float | None = None
    standardized_es: float | None = None
    evt_tail: dict[str, object] = {}
    if model_name == ML_TAIL_LOCATION_SCALE_MODEL:
        standardized_var = float(np.quantile(z_oof, tail_level))
        exceedances = z_oof[z_oof > standardized_var]
        min_es_exceedances = min(
            LOCATION_SCALE_MIN_ES_EXCEEDANCES_95,
            DEFAULT_MIN_TRAIN_EXCEEDANCES,
        )
        if exceedances.size < min_es_exceedances:
            raise PipelineRunError(
                f"unavailable_oof_standardized_es_insufficient_exceedances: {exceedances.size}"
            )
        standardized_es = float(max(standardized_var, np.mean(exceedances)))
        es_companion_type = "oof_filtered_historical_standardized_es"
        evt_tail = _location_scale_empirical_evt_metadata(
            exceedance_count=int(exceedances.size),
            min_exceedances=min_es_exceedances,
        )
    elif model_name in ML_TAIL_POT_GPD_MODEL_NAMES:
        if tail_level <= EVT_THRESHOLD_QUANTILE:
            raise PipelineRunError("unavailable_evt_tail_not_above_threshold")
        try:
            evt_tail = _pot_gpd_standardized_tail(
                standardized_losses=z_oof,
                tail_level=tail_level,
                require_finite_gpd_es=True,
                min_standardized_losses=min(EVT_MIN_STANDARDIZED_LOSSES_95, DEFAULT_MIN_TRAIN_ROWS),
                min_exceedances=min(EVT_MIN_EXCEEDANCES_95, DEFAULT_MIN_TRAIN_EXCEEDANCES),
                evt_variant=_evt_variant_for_ml_tail_model(model_name),
                shape_cap=EVT_SHAPE_CAP_BASELINE,
                shape_shrinkage_k=EVT_SHAPE_SHRINKAGE_K,
            )
        except PipelineRunError as exc:
            message = str(exc)
            if "insufficient exceedances" in message:
                raise PipelineRunError(
                    f"unavailable_evt_insufficient_exceedances: {message}"
                ) from exc
            if "shape" in message:
                raise PipelineRunError(f"unavailable_evt_shape_es_infinite: {message}") from exc
            raise PipelineRunError(f"unavailable_evt_calibration_failed: {message}") from exc
        standardized_var = _required_float(evt_tail["standardized_var"])
        standardized_es = _required_float(evt_tail["standardized_es"])
        es_companion_type = "oof_standardized_loss_pot_gpd"
    else:
        raise PipelineRunError(f"Unknown ML tail model: {model_name}")

    y_train = np.array([_required_float(row["realized_loss"]) for row in train_rows], dtype=float)
    location_model, gate, active_features = _fit_lgb_regression_model(
        lgb=lgb,
        rows=train_rows,
        target=y_train,
        candidate_features=candidate_features,
        objective="regression_l2",
        random_state=_ml_tail_seed(model_name, information_set, tail_level, "location_final"),
    )
    log_abs_resid_oof = cast(np.ndarray, oof["log_abs_resid_oof"])
    scale_indices = [index for index, value in enumerate(log_abs_resid_oof) if math.isfinite(value)]
    if len(scale_indices) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
        raise PipelineRunError(
            f"unavailable_oof_standardization_insufficient_sample: {len(scale_indices)}"
        )
    scale_rows = [train_rows[index] for index in scale_indices]
    scale_target = np.array([log_abs_resid_oof[index] for index in scale_indices], dtype=float)
    scale_model, scale_gate, scale_active_features = _fit_lgb_regression_model(
        lgb=lgb,
        rows=scale_rows,
        target=scale_target,
        candidate_features=candidate_features,
        objective="regression_l2",
        random_state=_ml_tail_seed(model_name, information_set, tail_level, "scale_final"),
    )
    return {
        "fit_status": "ok",
        "location_model": location_model,
        "scale_model": scale_model,
        "active_features": active_features,
        "scale_active_features": scale_active_features,
        "gate": gate,
        "scale_gate": scale_gate,
        "train_n": len(train_rows),
        "train_start": train_rows[0]["forecast_date"],
        "train_end": train_rows[-1]["forecast_date"],
        "smearing_factor": oof["smearing_factor"],
        "scale_floor": ML_TAIL_SCALE_FLOOR,
        "standardized_losses": z_oof,
        "standardized_var": standardized_var,
        "standardized_es": standardized_es,
        "es_companion_type": es_companion_type,
        "oof_standardized_loss_count": int(z_oof.size),
        "oof_location_count": oof["location_oof_count"],
        "oof_scale_count": oof["scale_oof_count"],
        "standardization_method": "blocked_expanding_oof_location_scale_duan_smearing",
        "evt_tail": evt_tail,
        "candidate_feature_hash": gate["candidate_feature_hash"],
        "active_feature_hash": stable_hash(
            {
                "location": active_features,
                "scale": scale_active_features,
            }
        ),
        "dropped_features_json": gate["dropped_features_json"],
        "scale_dropped_features_json": scale_gate["dropped_features_json"],
        "training_missingness_json": gate["training_missingness_json"],
        "training_variance_json": gate["training_variance_json"],
    }


def _evt_variant_for_ml_tail_model(model_name: str) -> str:
    if model_name == ML_TAIL_POT_GPD_PLAIN_MLE_MODEL:
        return "plain_mle"
    if model_name == ML_TAIL_POT_GPD_CAPPED_MLE_MODEL:
        return "capped_mle"
    if model_name == ML_TAIL_POT_GPD_EVI_SHRINK_MODEL:
        return "evi_shrink"
    if model_name == ML_TAIL_POT_GPD_EI_WEIGHTED_MODEL:
        return "ei_weighted"
    if model_name == ML_TAIL_POT_GPD_STABILIZED_MODEL:
        return "stabilized"
    raise PipelineRunError(f"Unknown ML tail POT-GPD model variant: {model_name}")


def _location_scale_empirical_evt_metadata(
    *,
    exceedance_count: int,
    min_exceedances: int,
) -> dict[str, object]:
    return {
        "evt_variant": "empirical_standardized_tail",
        "evt_shape_method": "not_applicable_empirical_standardized_tail",
        "evt_cap_policy": "not_applicable",
        "evt_cap_hit": False,
        "evt_evi_status": "not_used",
        "evt_ei_status": "not_used",
        "evt_exceedance_count": exceedance_count,
        "evt_min_exceedances": min_exceedances,
        "tail_method": "oof_filtered_historical_standardized_es",
    }
