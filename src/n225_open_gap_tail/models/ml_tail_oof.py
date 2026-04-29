# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def _ml_tail_oof_location_scale(
    *,
    train_rows: list[dict[str, object]],
    candidate_features: list[str],
    information_set: str,
    tail_level: float,
    lgb: Any,
) -> dict[str, object]:
    row_count = len(train_rows)
    folds = _blocked_expanding_oof_folds(
        row_count,
        n_splits=ML_TAIL_OOF_SPLITS,
        min_train_rows=ML_TAIL_MIN_OOF_TRAIN_ROWS,
    )
    if not folds:
        raise PipelineRunError("unavailable_oof_standardization_insufficient_sample: no folds")
    y = np.array([_required_float(row["realized_loss"]) for row in train_rows], dtype=float)
    mu_oof = np.full(row_count, np.nan, dtype=float)
    log_abs_resid_oof = np.full(row_count, np.nan, dtype=float)
    log_sigma_oof = np.full(row_count, np.nan, dtype=float)
    for fold_index, (fold_train, fold_validation) in enumerate(folds):
        fold_rows = [train_rows[index] for index in fold_train]
        fold_target = y[fold_train]
        model, _, active_features = _fit_lgb_regression_model(
            lgb=lgb,
            rows=fold_rows,
            target=fold_target,
            candidate_features=candidate_features,
            objective="regression_l2",
            random_state=_ml_tail_seed(information_set, tail_level, "location_oof", fold_index),
        )
        validation_rows = [train_rows[index] for index in fold_validation]
        mu_oof[fold_validation] = _predict_lgb_rows(model, validation_rows, active_features)
    for index, value in enumerate(mu_oof):
        if math.isfinite(value):
            log_abs_resid_oof[index] = math.log(max(abs(y[index] - value), ML_TAIL_SCALE_FLOOR))
    for fold_index, (fold_train, fold_validation) in enumerate(folds):
        scale_train = [index for index in fold_train if math.isfinite(log_abs_resid_oof[index])]
        scale_validation = [
            index for index in fold_validation if math.isfinite(log_abs_resid_oof[index])
        ]
        if len(scale_train) < ML_TAIL_MIN_OOF_TRAIN_ROWS or not scale_validation:
            continue
        scale_rows = [train_rows[index] for index in scale_train]
        scale_target = log_abs_resid_oof[scale_train]
        model, _, active_features = _fit_lgb_regression_model(
            lgb=lgb,
            rows=scale_rows,
            target=scale_target,
            candidate_features=candidate_features,
            objective="regression_l2",
            random_state=_ml_tail_seed(information_set, tail_level, "scale_oof", fold_index),
        )
        validation_rows = [train_rows[index] for index in scale_validation]
        log_sigma_oof[scale_validation] = _predict_lgb_rows(
            model,
            validation_rows,
            active_features,
        )
    valid_smearing = np.isfinite(log_abs_resid_oof) & np.isfinite(log_sigma_oof)
    if int(np.sum(valid_smearing)) < ML_TAIL_MIN_OOF_TRAIN_ROWS:
        raise PipelineRunError(
            f"unavailable_oof_standardization_insufficient_sample: {int(np.sum(valid_smearing))}"
        )
    exp_resid = np.exp(log_abs_resid_oof[valid_smearing] - log_sigma_oof[valid_smearing])
    exp_resid = exp_resid[np.isfinite(exp_resid)]
    smearing_factor = float(np.mean(exp_resid)) if exp_resid.size else math.nan
    if not math.isfinite(smearing_factor) or smearing_factor <= 0:
        raise PipelineRunError("unavailable_invalid_smearing_factor")
    sigma_oof = np.exp(log_sigma_oof) * smearing_factor
    valid_z = (
        np.isfinite(mu_oof)
        & np.isfinite(sigma_oof)
        & (sigma_oof > 0)
        & np.isfinite(log_abs_resid_oof)
    )
    standardized = (y[valid_z] - mu_oof[valid_z]) / sigma_oof[valid_z]
    standardized = standardized[np.isfinite(standardized)]
    if standardized.size < ML_TAIL_MIN_OOF_TRAIN_ROWS:
        raise PipelineRunError(
            f"unavailable_oof_standardization_insufficient_sample: {standardized.size}"
        )
    return {
        "mu_oof": mu_oof,
        "log_abs_resid_oof": log_abs_resid_oof,
        "log_sigma_oof": log_sigma_oof,
        "smearing_factor": smearing_factor,
        "standardized_losses": standardized,
        "location_oof_count": int(np.sum(np.isfinite(mu_oof))),
        "scale_oof_count": int(np.sum(np.isfinite(log_sigma_oof))),
    }


def _fit_lgb_regression_model(
    *,
    lgb: Any,
    rows: list[dict[str, object]],
    target: np.ndarray,
    candidate_features: list[str],
    objective: str,
    random_state: int,
) -> tuple[Any, dict[str, object], list[str]]:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    gate = build_feature_matrix_gate_records(frame, candidate_features)
    active_features = cast(list[str], gate["active_features"])
    if not active_features:
        raise PipelineRunError("ML tail LightGBM has no active features after training gate")
    x_train = _feature_matrix(frame, active_features)
    model = lgb.LGBMRegressor(
        objective=objective,
        n_estimators=80,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=random_state,
        num_threads=1,
        verbosity=-1,
    )
    model.fit(x_train, target)
    return model, gate, active_features


def _predict_lgb_rows(
    model: Any, rows: list[dict[str, object]], active_features: list[str]
) -> np.ndarray:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    x_predict = _feature_matrix(frame, active_features)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names",
            category=UserWarning,
        )
        return np.asarray(model.predict(x_predict), dtype=float)


def _blocked_expanding_oof_folds(
    row_count: int,
    *,
    n_splits: int,
    min_train_rows: int,
) -> list[tuple[list[int], list[int]]]:
    if row_count <= min_train_rows:
        return []
    validation_count = row_count - min_train_rows
    block_size = max(1, math.ceil(validation_count / max(n_splits, 1)))
    folds: list[tuple[list[int], list[int]]] = []
    start = min_train_rows
    while start < row_count:
        end = min(row_count, start + block_size)
        folds.append((list(range(start)), list(range(start, end))))
        start = end
    return folds


def _predict_ml_tail_location_scale_forecast(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    bundle: Mapping[str, object],
) -> dict[str, object]:
    location_model = bundle["location_model"]
    scale_model = bundle["scale_model"]
    location_forecast = float(
        _predict_lgb_rows(
            location_model,
            [dict(row)],
            cast(list[str], bundle["active_features"]),
        )[0]
    )
    log_scale_forecast = float(
        _predict_lgb_rows(
            scale_model,
            [dict(row)],
            cast(list[str], bundle["scale_active_features"]),
        )[0]
    )
    smearing_factor = _required_float(bundle["smearing_factor"])
    try:
        scale_forecast = math.exp(log_scale_forecast) * smearing_factor
    except OverflowError as exc:
        raise PipelineRunError("unavailable_invalid_scale_forecast") from exc
    if not math.isfinite(scale_forecast) or scale_forecast <= 0:
        raise PipelineRunError("unavailable_invalid_scale_forecast")
    standardized_var = _required_float(bundle["standardized_var"])
    standardized_es = _required_float(bundle["standardized_es"])
    var_forecast = float(location_forecast + scale_forecast * standardized_var)
    es_forecast = float(location_forecast + scale_forecast * standardized_es)
    es_forecast = float(max(var_forecast, es_forecast))
    realized_loss = _required_float(row["realized_loss"])
    valid, invalid_reason = validate_forecast_values(var_forecast, es_forecast)
    evt_tail = cast(Mapping[str, object], bundle.get("evt_tail") or {})
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
        "var_forecast": var_forecast,
        "es_forecast": es_forecast,
        "es_companion_type": bundle["es_companion_type"],
        "realized_loss": realized_loss,
        "var_breach": realized_loss > var_forecast,
        "is_valid_forecast": valid,
        "invalid_reason": invalid_reason,
        "train_start": bundle["train_start"],
        "train_end": bundle["train_end"],
        "train_n": bundle["train_n"],
        "fit_status": "ok" if valid else "invalid_forecast",
        "failure_reason": invalid_reason,
        "runtime_seconds": None,
        "dst_regime": row.get("dst_regime"),
        "absorption_regime": row.get("absorption_regime"),
        "vix_level": row.get("vix_level"),
        "active_feature_hash": bundle.get("active_feature_hash"),
        "location_forecast": location_forecast,
        "scale_forecast": scale_forecast,
        "scale_smearing_factor": smearing_factor,
        "scale_floor": ML_TAIL_SCALE_FLOOR,
        "standardization_method": bundle.get("standardization_method"),
        "oof_standardized_loss_count": bundle.get("oof_standardized_loss_count"),
        "standardized_var": standardized_var,
        "standardized_es": standardized_es,
        "evt_shape": evt_tail.get("evt_shape"),
        "evt_scale": evt_tail.get("evt_scale"),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
    }


def _ml_tail_location_scale_diagnostic(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    refit_month: str,
    bundle: Mapping[str, object],
) -> dict[str, object]:
    evt_tail = cast(Mapping[str, object], bundle.get("evt_tail") or {})
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "train_n": bundle["train_n"],
        "train_start": bundle["train_start"],
        "train_end": bundle["train_end"],
        "optimizer_status": "lightgbm_location_scale_fit_completed",
        "convergence_code": 0,
        "candidate_feature_hash": bundle["candidate_feature_hash"],
        "active_feature_hash": bundle["active_feature_hash"],
        "dropped_features_json": bundle["dropped_features_json"],
        "scale_dropped_features_json": bundle["scale_dropped_features_json"],
        "drop_reason": None,
        "training_missingness": bundle["training_missingness_json"],
        "training_variance": bundle["training_variance_json"],
        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
        "refit_month": refit_month,
        "scale_smearing_factor": bundle["smearing_factor"],
        "scale_floor": ML_TAIL_SCALE_FLOOR,
        "standardization_method": bundle["standardization_method"],
        "oof_standardized_loss_count": bundle["oof_standardized_loss_count"],
        "oof_location_count": bundle["oof_location_count"],
        "oof_scale_count": bundle["oof_scale_count"],
        "standardized_var": bundle["standardized_var"],
        "standardized_es": bundle["standardized_es"],
        "evt_shape": evt_tail.get("evt_shape"),
        "evt_scale": evt_tail.get("evt_scale"),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
        "threshold_diagnostics_json": evt_tail.get("threshold_diagnostics_json"),
        "threshold_policy": evt_tail.get("threshold_policy"),
        "threshold_selection": evt_tail.get("threshold_selection"),
    }


def _ml_tail_unavailable_feature_forecast(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    bundle: Mapping[str, object],
    unavailable_features: list[str],
) -> dict[str, object]:
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
        "var_forecast": None,
        "es_forecast": None,
        "es_companion_type": bundle.get("es_companion_type"),
        "realized_loss": _required_float(row["realized_loss"]),
        "var_breach": None,
        "is_valid_forecast": False,
        "invalid_reason": "unavailable_feature_not_valid_at_cutoff",
        "train_start": bundle.get("train_start"),
        "train_end": bundle.get("train_end"),
        "train_n": bundle.get("train_n"),
        "fit_status": "unavailable_feature_not_valid_at_cutoff",
        "failure_reason": ",".join(unavailable_features),
        "runtime_seconds": None,
        "dst_regime": row.get("dst_regime"),
        "absorption_regime": row.get("absorption_regime"),
        "vix_level": row.get("vix_level"),
        "active_feature_hash": bundle.get("active_feature_hash"),
        **_ml_tail_extended_forecast_fields(),
    }


def _ml_tail_extended_forecast_fields() -> dict[str, object]:
    return {
        "location_forecast": None,
        "scale_forecast": None,
        "scale_smearing_factor": None,
        "scale_floor": None,
        "standardization_method": None,
        "oof_standardized_loss_count": None,
        "standardized_var": None,
        "standardized_es": None,
        "evt_shape": None,
        "evt_scale": None,
        "threshold_quantile": None,
        "threshold_value": None,
        "evt_exceedance_count": None,
    }


def _ml_tail_unavailable_status(exc: BaseException) -> str:
    message = str(exc)
    if message.startswith("unavailable_"):
        return message.split(":", 1)[0]
    return "unavailable_optimizer_failed"


def _ml_tail_seed(*values: object) -> int:
    return int(stable_hash(values)[:8], 16)


def _unavailable_active_features(
    row: Mapping[str, object],
    active_features: list[str],
) -> list[str]:
    unavailable: list[str] = []
    for feature in active_features:
        value = _optional_float(row.get(feature))
        if value is None or not math.isfinite(value):
            unavailable.append(feature)
    return unavailable


def build_ml_tail_feature_unavailability_date_records(
    forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in forecasts:
        if row.get("fit_status") != "unavailable_feature_not_valid_at_cutoff":
            continue
        for feature in _missing_feature_names(row.get("failure_reason")):
            records.append(
                {
                    "forecast_date": row.get("forecast_date"),
                    "target_family": row.get("target_family"),
                    "model_name": row.get("model_name"),
                    "information_set": row.get("information_set"),
                    "tail_level": row.get("tail_level"),
                    "feature": feature,
                    "source_family": _feature_source_family(feature),
                    "source_block": _feature_source_block(feature),
                    "fit_status": row.get("fit_status"),
                    "failure_reason": row.get("failure_reason"),
                    "dst_regime": row.get("dst_regime"),
                    "absorption_regime": row.get("absorption_regime"),
                    "active_feature_hash": row.get("active_feature_hash"),
                }
            )
    return sorted(
        records,
        key=lambda item: (
            str(item.get("information_set") or ""),
            _optional_float(item.get("tail_level")) or 0.0,
            str(item.get("feature") or ""),
            str(item.get("forecast_date") or ""),
        ),
    )


def build_ml_tail_feature_unavailability_records(
    forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    denominators: dict[tuple[str, str, float], int] = {}
    dates_by_key: dict[tuple[str, str, float, str], list[str]] = {}
    for row in forecasts:
        model_name = str(row.get("model_name") or "")
        information_set = str(row.get("information_set") or "")
        tail_level = _optional_float(row.get("tail_level"))
        if not model_name or not information_set or tail_level is None:
            continue
        denominator_key = (model_name, information_set, tail_level)
        denominators[denominator_key] = denominators.get(denominator_key, 0) + 1
        if row.get("fit_status") != "unavailable_feature_not_valid_at_cutoff":
            continue
        for feature in _missing_feature_names(row.get("failure_reason")):
            key = (*denominator_key, feature)
            dates_by_key.setdefault(key, []).append(str(row.get("forecast_date") or ""))
    records: list[dict[str, object]] = []
    for (model_name, information_set, tail_level, feature), dates in sorted(dates_by_key.items()):
        denominator = denominators.get((model_name, information_set, tail_level), 0)
        clean_dates = sorted(date_value for date_value in dates if date_value)
        records.append(
            {
                "model_name": model_name,
                "information_set": information_set,
                "tail_level": tail_level,
                "feature": feature,
                "source_family": _feature_source_family(feature),
                "source_block": _feature_source_block(feature),
                "missing_count": len(clean_dates),
                "forecast_rows": denominator,
                "missing_rate": len(clean_dates) / denominator if denominator else None,
                "first_missing_date": clean_dates[0] if clean_dates else None,
                "last_missing_date": clean_dates[-1] if clean_dates else None,
                "missing_dates_json": json.dumps(clean_dates, separators=(",", ":")),
                "fit_status": "unavailable_feature_not_valid_at_cutoff",
            }
        )
    return records


def _missing_feature_names(value: object) -> list[str]:
    if value is None:
        return []
    return [feature.strip() for feature in str(value).split(",") if feature.strip()]


def _feature_matrix(frame: pl.DataFrame, active_features: list[str]) -> np.ndarray:
    selected = frame.select(
        [
            pl.col(feature).cast(pl.Float64, strict=False).alias(feature)
            if feature in frame.columns
            else pl.lit(None, dtype=pl.Float64).alias(feature)
            for feature in active_features
        ]
    )
    return cast(np.ndarray, selected.to_numpy())
