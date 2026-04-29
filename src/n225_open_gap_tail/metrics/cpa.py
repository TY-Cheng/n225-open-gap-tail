# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


CPA_LOSS_FAMILY = "var_quantile_loss"
CPA_CLAIM_SCOPE = "conditional_inference_diagnostic_not_headline"
CPA_HAC_KERNEL = "bartlett"
CPA_INSTRUMENT_CANDIDATES = (
    "lagged_loss_diff",
    "vix_level",
    "dst_edt",
    "absorption_post_us_close",
)


def build_ml_tail_cpa_inference_records(
    loss_matrix: list[dict[str, object]],
) -> list[dict[str, object]]:
    information_sets = registered_ml_tail_information_sets()
    anchor_information_set = PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set
    candidate_sets = [item for item in information_sets if item != anchor_information_set]
    direct_rows = [
        row
        for row in loss_matrix
        if str(row.get("model_name") or "") == ML_TAIL_DIRECT_QUANTILE_MODEL
        and str(row.get("tail_side") or PRIMARY_TAIL_SIDE) in TAIL_SIDES
    ]
    grouped: dict[tuple[str, str, float, str], dict[str, dict[str, dict[str, object]]]] = {}
    for row in direct_rows:
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
                    target_family=target_family,
                    tail_side=tail_side,
                    tail_level=tail_level,
                    refit_frequency=refit_frequency,
                    anchor_information_set=anchor_information_set,
                    candidate_information_set=candidate_information_set,
                    anchor_rows=anchor_rows,
                    candidate_rows=candidate_rows,
                )
            )
    return records


def _cpa_record_for_pair(
    *,
    target_family: str,
    tail_side: str,
    tail_level: float,
    refit_frequency: str,
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
        "suite": "ml_tail",
        "target_family": target_family,
        "tail_side": tail_side,
        "tail_level": tail_level,
        "model_name": ML_TAIL_DIRECT_QUANTILE_MODEL,
        "refit_frequency": refit_frequency or None,
        "loss_family": CPA_LOSS_FAMILY,
        "comparison_axis": "information_set_increment",
        "claim_scope": CPA_CLAIM_SCOPE,
        "headline_claim_allowed": False,
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
        "regression_formula": "candidate_minus_anchor_quantile_loss_on_preregistered_instruments",
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
) -> dict[str, object]:
    candidate_loss = _cpa_quantile_loss(candidate)
    anchor_loss = _cpa_quantile_loss(anchor)
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


def _cpa_quantile_loss(row: Mapping[str, object]) -> float | None:
    recorded = _optional_float(row.get("quantile_loss"))
    if recorded is not None:
        return recorded
    try:
        loss = _required_float(row["realized_loss"])
        var_forecast = _required_float(row["var_forecast"])
        tail_level = _required_float(row["tail_level"])
    except (KeyError, TypeError, ValueError):
        return None
    return quantile_loss(loss, var_forecast, tail_level)


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
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    hac_lags = _cpa_hac_lags(y.size)
    meat = _newey_west_meat(x, resid, hac_lags)
    cov = xtx_inv @ meat @ xtx_inv
    if not np.all(np.isfinite(cov)):
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
