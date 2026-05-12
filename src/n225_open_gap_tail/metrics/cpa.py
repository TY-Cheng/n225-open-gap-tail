# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    json,
    Mapping,
    math,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_POT_GPD_MODEL_NAMES,
    ML_TAIL_REFIT_FREQUENCY,
    ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES,
    np,
    PIPELINE_CONFIG,
    PipelineRunError,
    PRIMARY_TAIL_SIDE,
    stats,
    TAIL_SIDES,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.metrics.stat_utils import fz_loss, quantile_loss
from n225_open_gap_tail.panel.build import registered_ml_tail_information_sets

CPA_QUANTILE_LOSS_FAMILY = "var_quantile_loss"
CPA_FZ_LOSS_FAMILY = "var_es_fz_loss"
CPA_LOSS_FAMILIES = (CPA_QUANTILE_LOSS_FAMILY, CPA_FZ_LOSS_FAMILY)
CPA_CLAIM_SCOPE = "conditional_inference_diagnostic_not_primary"
CPA_HAC_KERNEL = "bartlett"
CPA_INSTRUMENT_CANDIDATES = (
    "lagged_loss_diff",
    "vix_level",
    "dst_edt",
    "absorption_post_us_close",
)
CPA_FZ_ML_TAIL_MODELS = (
    ML_TAIL_LOCATION_SCALE_MODEL,
    *ML_TAIL_POT_GPD_MODEL_NAMES,
    *ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES,
)


def build_ml_tail_cpa_inference_records(
    forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build information-set CPA records for registered ML-tail models.

    Direct quantile remains VaR-only and therefore uses quantile loss. Location-scale
    and standardized-loss POT-GPD are true VaR-ES forecast pairs and enter FZ-CPA.
    """

    records: list[dict[str, object]] = []
    records.extend(
        _build_information_set_cpa_records(
            forecasts,
            model_name=ML_TAIL_DIRECT_QUANTILE_MODEL,
            loss_family=CPA_QUANTILE_LOSS_FAMILY,
        )
    )
    for model_name in CPA_FZ_ML_TAIL_MODELS:
        records.extend(
            _build_information_set_cpa_records(
                forecasts,
                model_name=model_name,
                loss_family=CPA_FZ_LOSS_FAMILY,
            )
        )
    return records


def build_cross_model_cpa_inference_records(
    *,
    ml_tail_forecasts: list[dict[str, object]],
    benchmark_forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build registered cross-model CPA records.

    Candidate models are ML-tail forecasts. Anchors are benchmark-family forecasts.
    The function emits a stable skipped status when benchmark forecasts are absent.
    """

    if not benchmark_forecasts:
        return [_cross_model_skipped_record("skipped_missing_benchmark_forecasts")]
    records: list[dict[str, object]] = []
    records.extend(
        _build_cross_model_cpa_records(
            ml_tail_forecasts=ml_tail_forecasts,
            benchmark_forecasts=benchmark_forecasts,
            candidate_models=(ML_TAIL_DIRECT_QUANTILE_MODEL,),
            loss_family=CPA_QUANTILE_LOSS_FAMILY,
        )
    )
    records.extend(
        _build_cross_model_cpa_records(
            ml_tail_forecasts=ml_tail_forecasts,
            benchmark_forecasts=benchmark_forecasts,
            candidate_models=CPA_FZ_ML_TAIL_MODELS,
            loss_family=CPA_FZ_LOSS_FAMILY,
        )
    )
    return records or [_cross_model_skipped_record("skipped_no_registered_pairs")]


def _build_information_set_cpa_records(
    forecasts: list[dict[str, object]],
    *,
    model_name: str,
    loss_family: str,
) -> list[dict[str, object]]:
    information_sets = registered_ml_tail_information_sets()
    anchor_information_set = PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set
    candidate_sets = [item for item in information_sets if item != anchor_information_set]
    model_rows = [
        row
        for row in forecasts
        if str(row.get("model_name") or "") == model_name
        and str(row.get("tail_side") or PRIMARY_TAIL_SIDE) in TAIL_SIDES
        and _cpa_forecast_row_eligible(row)
        and _cpa_row_loss(row, loss_family) is not None
    ]
    grouped: dict[tuple[str, str, float, str], dict[str, dict[str, dict[str, object]]]] = {}
    for row in model_rows:
        key = (
            str(row.get("target_family") or PIPELINE_CONFIG.target_policy.primary_target_family),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
            _required_float(row["tail_level"]),
            str(row.get("refit_frequency") or ML_TAIL_REFIT_FREQUENCY),
        )
        information_set = str(row.get("information_set") or "")
        grouped.setdefault(key, {}).setdefault(information_set, {})[str(row["forecast_date"])] = row
    records: list[dict[str, object]] = []
    for (target_family, tail_side, tail_level, refit_frequency), rows_by_info in sorted(
        grouped.items()
    ):
        anchor_rows = rows_by_info.get(anchor_information_set, {})
        for candidate_information_set in candidate_sets:
            candidate_rows = rows_by_info.get(candidate_information_set, {})
            records.append(
                _cpa_record_for_pair(
                    suite="ml_tail",
                    comparison_axis="information_set_increment",
                    target_family=target_family,
                    tail_side=tail_side,
                    tail_level=tail_level,
                    loss_family=loss_family,
                    model_name=model_name,
                    anchor_model_name=model_name,
                    candidate_model_name=model_name,
                    anchor_refit_frequency=refit_frequency,
                    candidate_refit_frequency=refit_frequency,
                    anchor_information_set=anchor_information_set,
                    candidate_information_set=candidate_information_set,
                    anchor_rows=anchor_rows,
                    candidate_rows=candidate_rows,
                )
            )
    return records


def _build_cross_model_cpa_records(
    *,
    ml_tail_forecasts: list[dict[str, object]],
    benchmark_forecasts: list[dict[str, object]],
    candidate_models: tuple[str, ...],
    loss_family: str,
) -> list[dict[str, object]]:
    ml_groups = _cpa_group_rows(
        [
            row
            for row in ml_tail_forecasts
            if str(row.get("model_name") or "") in candidate_models
            and _cpa_forecast_row_eligible(row)
            and _cpa_row_loss(row, loss_family) is not None
        ],
        include_information_set=True,
    )
    benchmark_groups = _cpa_group_rows(
        [
            row
            for row in benchmark_forecasts
            if _cpa_forecast_row_eligible(row)
            and _cpa_row_loss(row, loss_family, require_primary_fz_pair=True) is not None
        ],
        include_information_set=False,
    )
    records: list[dict[str, object]] = []
    for candidate_key, candidate_rows in sorted(ml_groups.items()):
        (
            target_family,
            tail_side,
            tail_level,
            candidate_model_name,
            candidate_information_set,
            candidate_refit_frequency,
        ) = candidate_key
        for anchor_key, anchor_rows in sorted(benchmark_groups.items()):
            (
                anchor_target_family,
                anchor_tail_side,
                anchor_tail_level,
                anchor_model_name,
                anchor_information_set,
                anchor_refit_frequency,
            ) = anchor_key
            if (
                anchor_target_family != target_family
                or anchor_tail_side != tail_side
                or anchor_tail_level != tail_level
            ):
                continue
            records.append(
                _cpa_record_for_pair(
                    suite="cross_model",
                    comparison_axis="cross_model_registered_pair",
                    target_family=target_family,
                    tail_side=tail_side,
                    tail_level=tail_level,
                    loss_family=loss_family,
                    model_name=candidate_model_name,
                    anchor_model_name=anchor_model_name,
                    candidate_model_name=candidate_model_name,
                    anchor_refit_frequency=anchor_refit_frequency,
                    candidate_refit_frequency=candidate_refit_frequency,
                    anchor_information_set=anchor_information_set,
                    candidate_information_set=candidate_information_set,
                    anchor_rows=anchor_rows,
                    candidate_rows=candidate_rows,
                )
            )
    return records


def _cpa_group_rows(
    rows: list[dict[str, object]],
    *,
    include_information_set: bool,
) -> dict[tuple[str, str, float, str, str, str], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str, float, str, str, str], dict[str, dict[str, object]]] = {}
    for row in rows:
        information_set = str(row.get("information_set") or "target_history_only")
        if not include_information_set:
            information_set = "target_history_only"
        key = (
            str(row.get("target_family") or PIPELINE_CONFIG.target_policy.primary_target_family),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
            _required_float(row["tail_level"]),
            str(row.get("model_name") or ""),
            information_set,
            str(row.get("refit_frequency") or ""),
        )
        grouped.setdefault(key, {})[str(row["forecast_date"])] = row
    return grouped


def _cpa_record_for_pair(
    *,
    suite: str,
    comparison_axis: str,
    target_family: str,
    tail_side: str,
    tail_level: float,
    loss_family: str,
    model_name: str,
    anchor_model_name: str,
    candidate_model_name: str,
    anchor_refit_frequency: str,
    candidate_refit_frequency: str,
    anchor_information_set: str,
    candidate_information_set: str,
    anchor_rows: Mapping[str, Mapping[str, object]],
    candidate_rows: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    common_dates = sorted(set(anchor_rows).intersection(candidate_rows))
    paired = [
        _cpa_paired_observation(
            forecast_date=forecast_date,
            anchor=anchor_rows[forecast_date],
            candidate=candidate_rows[forecast_date],
            loss_family=loss_family,
        )
        for forecast_date in common_dates
    ]
    for index in range(1, len(paired)):
        paired[index]["lagged_loss_diff"] = paired[index - 1]["loss_diff"]
    loss_available = [row for row in paired if _finite_optional(row.get("loss_diff"))]
    active, dropped = _active_cpa_instruments(loss_available)
    complete = [row for row in loss_available if _cpa_complete_instrument_row(row, active)]
    effective_n = len(complete)
    instrument_count = len(active)
    min_effective_n = max(120, 20 * instrument_count) if instrument_count else 120
    base = {
        "suite": suite,
        "target_family": target_family,
        "tail_side": tail_side,
        "tail_level": tail_level,
        "model_name": model_name,
        "anchor_model_name": anchor_model_name,
        "candidate_model_name": candidate_model_name,
        "refit_frequency": candidate_refit_frequency or None,
        "anchor_refit_frequency": anchor_refit_frequency or None,
        "candidate_refit_frequency": candidate_refit_frequency or None,
        "loss_family": loss_family,
        "comparison_axis": comparison_axis,
        "claim_scope": CPA_CLAIM_SCOPE,
        "primary_claim_allowed": False,
        "anchor_information_set": anchor_information_set,
        "candidate_information_set": candidate_information_set,
        "common_n": len(common_dates),
        "complete_case_n": len(complete),
        "effective_n": effective_n,
        "instrument_count": instrument_count,
        "minimum_effective_n": min_effective_n,
        "instruments_json": json.dumps(active, separators=(",", ":")),
        "dropped_instruments_json": json.dumps(dropped, sort_keys=True, separators=(",", ":")),
        "dropped_missing_instrument_rows": len(loss_available) - len(complete),
        "dropped_missing_loss_rows": len(paired) - len(loss_available),
        "hac_kernel": CPA_HAC_KERNEL,
        "hac_lags": _cpa_hac_lags(effective_n) if effective_n else None,
        "method_note": "newey_west_hac_wald_conditional_loss_differential_regression",
        "regression_formula": _cpa_regression_formula(loss_family, comparison_axis),
    }
    if not common_dates:
        return _cpa_unavailable(base, "unavailable_missing_anchor_or_candidate_sample")
    if instrument_count <= 1:
        return _cpa_unavailable(base, "unavailable_no_nonconstant_instruments")
    if effective_n < min_effective_n:
        return _cpa_unavailable(base, "unavailable_insufficient_effective_rows_for_cpa")
    result = _fit_cpa_hac_regression(complete, active)
    if result is None:
        return _cpa_unavailable(base, "unavailable_singular_instrument_matrix")
    return {
        **base,
        **result,
        "inference_status": "ok_newey_west_hac_wald_cpa",
    }


def _cpa_paired_observation(
    *,
    forecast_date: str,
    anchor: Mapping[str, object],
    candidate: Mapping[str, object],
    loss_family: str,
) -> dict[str, object]:
    candidate_loss = _cpa_row_loss(candidate, loss_family)
    anchor_loss = _cpa_row_loss(anchor, loss_family)
    diff = (
        candidate_loss - anchor_loss
        if candidate_loss is not None and anchor_loss is not None
        else None
    )
    return {
        "forecast_date": forecast_date,
        "loss_diff": diff,
        "lagged_loss_diff": None,
        "vix_level": _optional_float(candidate.get("vix_level"))
        if _optional_float(candidate.get("vix_level")) is not None
        else _optional_float(anchor.get("vix_level")),
        "dst_edt": 1.0
        if str(candidate.get("dst_regime") or anchor.get("dst_regime")) == "EDT"
        else 0.0,
        "absorption_post_us_close": 1.0
        if str(candidate.get("absorption_regime") or anchor.get("absorption_regime"))
        == "post_us_close_night_absorption"
        else 0.0,
    }


def _cpa_row_loss(
    row: Mapping[str, object],
    loss_family: str,
    *,
    require_primary_fz_pair: bool = False,
) -> float | None:
    if loss_family == CPA_QUANTILE_LOSS_FAMILY:
        return _cpa_quantile_loss(row)
    if loss_family == CPA_FZ_LOSS_FAMILY:
        if require_primary_fz_pair and not _primary_fz_pair_allowed(row):
            return None
        return _cpa_fz_loss(row)
    return None


def _cpa_forecast_row_eligible(row: Mapping[str, object]) -> bool:
    return row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True


def _cpa_quantile_loss(row: Mapping[str, object]) -> float | None:
    recorded = _optional_float(row.get("quantile_loss"))
    if recorded is not None:
        return recorded
    try:
        loss = _required_float(row["realized_loss"])
        var_forecast = _required_float(row["var_forecast"])
        tail_level = _required_float(row["tail_level"])
    except (KeyError, TypeError, ValueError, PipelineRunError):
        return None
    return quantile_loss(loss, var_forecast, tail_level)


def _cpa_fz_loss(row: Mapping[str, object]) -> float | None:
    recorded = _optional_float(row.get("fz_loss"))
    if recorded is not None:
        return recorded
    try:
        loss = _required_float(row["realized_loss"])
        var_forecast = _required_float(row["var_forecast"])
        es_forecast = _required_float(row["es_forecast"])
        tail_level = _required_float(row["tail_level"])
    except (KeyError, TypeError, ValueError, PipelineRunError):
        return None
    value = fz_loss(loss, var_forecast, es_forecast, tail_level)
    return value if math.isfinite(value) else None


def _primary_fz_pair_allowed(row: Mapping[str, object]) -> bool:
    if _cpa_fz_loss(row) is None:
        return False
    interpretation = str(row.get("fz_interpretation") or "")
    es_source = str(row.get("es_source") or "")
    companion = str(row.get("es_companion_type") or "")
    blocked = {
        "augmented_var_es_pair_not_jointly_estimated",
        "empirical_exceedance_companion",
        "raw_empirical_es",
        "rolling_empirical_es",
    }
    values = {interpretation, es_source, companion}
    return values.isdisjoint(blocked)


def _cpa_complete_instrument_row(row: Mapping[str, object], instruments: list[str]) -> bool:
    for field in ("loss_diff", *[item for item in instruments if item != "constant"]):
        if not _finite_optional(row.get(field)):
            return False
    return True


def _active_cpa_instruments(
    rows: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]]]:
    if not rows:
        return ["constant"], [
            {"instrument": name, "drop_reason": "no_complete_rows"}
            for name in CPA_INSTRUMENT_CANDIDATES
        ]
    active = ["constant"]
    dropped: list[dict[str, object]] = []
    for name in CPA_INSTRUMENT_CANDIDATES:
        finite_values = [
            value
            for row in rows
            if (value := _optional_float(row.get(name))) is not None and math.isfinite(value)
        ]
        values = np.array(finite_values, dtype=float)
        if values.size < 2 or float(np.nanstd(values)) <= 1e-12:
            reason = "nonfinite_or_missing" if values.size < 2 else "zero_or_low_variance"
            dropped.append({"instrument": name, "drop_reason": reason})
        else:
            active.append(name)
    return active, dropped


def _finite_optional(value: object) -> bool:
    parsed = _optional_float(value)
    return parsed is not None and math.isfinite(parsed)


def _fit_cpa_hac_regression(
    rows: list[dict[str, object]],
    instruments: list[str],
) -> dict[str, object] | None:
    y = np.array([_required_float(row["loss_diff"]) for row in rows], dtype=float)
    columns = []
    for name in instruments:
        if name == "constant":
            columns.append(np.ones(y.size, dtype=float))
        else:
            columns.append(np.array([_required_float(row[name]) for row in rows], dtype=float))
    x = np.column_stack(columns)
    if np.linalg.matrix_rank(x) < x.shape[1]:
        return None
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    hac_lags = _cpa_hac_lags(y.size)
    meat = _newey_west_meat(x, resid, hac_lags)
    cov = xtx_inv @ meat @ xtx_inv
    if not np.all(np.isfinite(cov)):
        return None
    if np.linalg.matrix_rank(cov) < len(instruments):
        return None
    cov_inv = np.linalg.pinv(cov)
    wald_stat = float(beta.T @ cov_inv @ beta)
    pvalue = float(1.0 - stats.chi2.cdf(wald_stat, len(instruments)))
    se = np.sqrt(np.clip(np.diag(cov), 0.0, np.inf))
    tstat = np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)
    return {
        "mean_loss_diff_candidate_minus_anchor": float(np.mean(y)),
        "wald_stat": wald_stat,
        "wald_df": len(instruments),
        "wald_pvalue": pvalue,
        "reject_10pct": pvalue < 0.10,
        "coef_json": _named_float_json(instruments, beta),
        "stderr_json": _named_float_json(instruments, se),
        "tstat_json": _named_float_json(instruments, tstat),
    }


def _newey_west_meat(x: np.ndarray, resid: np.ndarray, lags: int) -> np.ndarray:
    xu = x * resid[:, None]
    meat = xu.T @ xu
    n = x.shape[0]
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        gamma = xu[lag:].T @ xu[:-lag]
        meat += weight * (gamma + gamma.T)
    return meat


def _cpa_hac_lags(n: int) -> int:
    if n <= 1:
        return 0
    return int(max(1, math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def _named_float_json(names: list[str], values: np.ndarray) -> str:
    return json.dumps(
        {
            name: (float(value) if math.isfinite(float(value)) else None)
            for name, value in zip(names, values, strict=True)
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _cpa_unavailable(base: Mapping[str, object], status: str) -> dict[str, object]:
    return {
        **base,
        "mean_loss_diff_candidate_minus_anchor": None,
        "wald_stat": None,
        "wald_df": None,
        "wald_pvalue": None,
        "reject_10pct": False,
        "coef_json": None,
        "stderr_json": None,
        "tstat_json": None,
        "inference_status": status,
    }


def _cross_model_skipped_record(status: str) -> dict[str, object]:
    return _cpa_unavailable(
        {
            "suite": "cross_model",
            "target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
            "tail_side": None,
            "tail_level": None,
            "model_name": None,
            "anchor_model_name": None,
            "candidate_model_name": None,
            "refit_frequency": None,
            "anchor_refit_frequency": None,
            "candidate_refit_frequency": None,
            "loss_family": None,
            "comparison_axis": "cross_model_registered_pair",
            "claim_scope": CPA_CLAIM_SCOPE,
            "primary_claim_allowed": False,
            "anchor_information_set": None,
            "candidate_information_set": None,
            "common_n": 0,
            "complete_case_n": 0,
            "effective_n": 0,
            "instrument_count": 0,
            "minimum_effective_n": 120,
            "instruments_json": "[]",
            "dropped_instruments_json": "[]",
            "dropped_missing_instrument_rows": 0,
            "dropped_missing_loss_rows": 0,
            "hac_kernel": CPA_HAC_KERNEL,
            "hac_lags": None,
            "method_note": "newey_west_hac_wald_conditional_loss_differential_regression",
            "regression_formula": None,
        },
        status,
    )


def _cpa_regression_formula(loss_family: str, comparison_axis: str) -> str:
    loss_label = "fz_loss" if loss_family == CPA_FZ_LOSS_FAMILY else "quantile_loss"
    return f"candidate_minus_anchor_{loss_label}_on_preregistered_instruments_{comparison_axis}"
