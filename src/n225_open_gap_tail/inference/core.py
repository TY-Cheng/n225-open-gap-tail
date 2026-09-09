# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    BOOTSTRAP_REPS,
    cast,
    COMMON_SAMPLE_MIN_ANCHOR_COVERAGE,
    common_sample_status,
    INFERENCE_RANDOM_SEED,
    Mapping,
    math,
    ML_TAIL_PRIMARY_MODEL_NAMES,
    MODEL_EVICTION_COVERAGE_THRESHOLD,
    np,
    PIPELINE_CONFIG,
    PRIMARY_TAIL_SIDE,
    RESULT_MATRIX_MIN_DM_EXCEPTIONS,
    RESULT_MATRIX_MIN_DM_ROWS,
    stats,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.config.runtime import (
    BENCHMARK_BASELINE_MODEL_NAMES,
    BENCHMARK_ADVANCED_MODEL_NAMES,
    ML_TAIL_MODEL_NAMES,
)
from n225_open_gap_tail.metrics.stat_utils import (
    _safe_mean,
    fz_loss,
    forecast_eligible,
    index_forecast_sessions,
    valid_forecast_rows,
    christoffersen_independence_test as _session_independence_test,
    moving_block_one_sided_pvalue as _session_block_pvalue,
)
from n225_open_gap_tail.metrics.result_matrix import build_metric_records


def build_common_sample_artifacts(
    forecasts: list[dict[str, object]],
    *,
    suite: str,
    anchor_model: str,
    anchor_information_set: str,
    model_names: tuple[str, ...] | None = None,
) -> dict[str, object]:
    forecasts = index_forecast_sessions(forecasts)
    per_model_metrics = build_metric_records(forecasts, sample_policy="per_model_oos")
    registered = model_names or (
        ML_TAIL_MODEL_NAMES
        if suite == "ml_tail"
        else BENCHMARK_BASELINE_MODEL_NAMES
        if suite == "benchmark_baseline"
        else BENCHMARK_ADVANCED_MODEL_NAMES
        if suite == "benchmark_advanced"
        else BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES
    )
    grouped = _group_forecasts_by_key(_valid_forecast_rows(forecasts))
    dimensions = sorted(
        {
            (
                str(row.get("target_family") or "full_gap_settle_to_open"),
                str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
                float(row["tail_level"]),
                str(row.get("information_set") or "target_history_only"),
            )
            for row in forecasts
        }
    )
    primary_forecasts = []
    primary_metrics = []
    evictions = []
    loss_matrix = []
    dm = []
    statuses = {}
    for target, side, level, information in dimensions:
        keys = []
        for model in registered:
            matches = [
                key
                for key in grouped
                if (key[0], key[1], key[2], key[3], key[5])
                == (target, model, information, level, side)
            ]
            if len(matches) > 1:
                raise ValueError("A comparison requires one refit specification per model")
            key = matches[0] if matches else (target, model, information, level, "", side)
            grouped.setdefault(key, {})
            keys.append(key)
        anchor_key = next((key for key in keys if key[1] == anchor_model), keys[0])
        anchor_dates = set(grouped[anchor_key])
        missing = [key[1] for key in keys if not grouped[key]]
        common_dates = sorted(set.intersection(*(set(grouped[key]) for key in keys)))
        status = (
            "unavailable_missing_registered_model"
            if missing
            else common_sample_status(common_dates)
        )
        statuses[(target, side, level, information)] = status
        for key in keys:
            overlap = len(set(grouped[key]) & anchor_dates)
            record = _model_eviction_record(
                suite=suite,
                key=key,
                anchor_key=anchor_key,
                anchor_rows=len(anchor_dates),
                overlap_rows=overlap,
                coverage_ratio=overlap / len(anchor_dates) if anchor_dates else 0.0,
                retained=not missing,
                eviction_reason=status if missing else None,
                common_rows=len(common_dates),
                common_anchor_coverage=len(common_dates) / len(anchor_dates)
                if anchor_dates
                else 0.0,
                common_sample_status_value=status,
            )
            record.update(
                eviction_threshold=None,
                common_sample_min_anchor_coverage=None,
                roster_policy="fixed_by_comparison_question",
                missing_entities=missing,
            )
            evictions.append(record)
        group_rows = [
            {**grouped[key][day], "comparison_refit_frequency": anchor_key[4] or None}
            for key in keys
            for day in common_dates
        ]
        primary_forecasts.extend(group_rows)
        metrics = build_metric_records(
            group_rows,
            sample_policy="comparison_specific_common_dates",
            common_sample_status_value=status,
        )
        # FZ0 has its own all-member common sample; never average unequal ES subsets.
        fz_dates = sorted(
            set.intersection(
                *(
                    {
                        day
                        for day, row in grouped[key].items()
                        if forecast_eligible(row, score="fz0")
                    }
                    for key in keys
                )
            )
        )
        fz_metrics = {
            row["model_name"]: row
            for row in build_metric_records([grouped[key][day] for key in keys for day in fz_dates])
        }
        for metric in metrics:
            fz_metric = fz_metrics.get(metric["model_name"], {})
            metric["mean_fz_loss"] = fz_metric.get("mean_fz_loss")
            metric["fz0_rows"] = len(fz_dates)
        primary_metrics.extend(metrics)
        group_loss = build_loss_matrix_records(group_rows, suite=suite)
        for row in group_loss:
            if str(row["forecast_date"]) not in fz_dates:
                row["fz_loss"] = None
        loss_matrix.extend(group_loss)
        dm.extend(
            build_block_bootstrap_dm_records(
                group_loss,
                suite=suite,
                anchor_model=anchor_model,
                anchor_information_set=information,
            )
        )
    return {
        "primary_forecasts": primary_forecasts,
        "primary_metrics": primary_metrics,
        "per_model_metrics": per_model_metrics,
        "model_eviction": evictions,
        "loss_matrix": loss_matrix,
        "dm_inference": dm,
        "murphy": build_murphy_records(primary_forecasts, suite=suite),
        "stress_windows": build_stress_window_records(primary_forecasts, suite=suite),
        "common_sample_status": _combined_common_sample_status(statuses),
    }


def build_loss_matrix_records(
    forecasts: list[dict[str, object]],
    *,
    suite: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in _valid_forecast_rows(forecasts):
        tail_level = _required_float(row["tail_level"])
        loss = _required_float(row["realized_loss"])
        var_forecast = _required_float(row["var_forecast"])
        es_forecast = _optional_float(row.get("es_forecast"))
        q_loss = quantile_loss(loss, var_forecast, tail_level)
        realized_fz_loss = (
            fz_loss(loss, var_forecast, es_forecast, tail_level)
            if forecast_eligible(row, score="fz0")
            else None
        )
        records.append(
            {
                "suite": suite,
                "forecast_date": row["forecast_date"],
                "target_session_index": row.get("target_session_index"),
                "target_family": row.get("target_family") or "full_gap_settle_to_open",
                "tail_side": row.get("tail_side") or PRIMARY_TAIL_SIDE,
                "model_name": row["model_name"],
                "information_set": row.get("information_set") or "target_history_only",
                "tail_level": tail_level,
                "refit_frequency": row.get(
                    "comparison_refit_frequency",
                    row.get("refit_frequency"),
                ),
                "realized_loss": loss,
                "var_forecast": var_forecast,
                "es_forecast": es_forecast,
                "quantile_loss": q_loss,
                "fz_loss": realized_fz_loss,
                "dst_regime": row.get("dst_regime"),
                "absorption_regime": row.get("absorption_regime"),
                "vix_level": row.get("vix_level"),
            }
        )
    return sorted(
        records,
        key=lambda item: (
            _required_float(item["tail_level"]),
            str(item.get("tail_side") or PRIMARY_TAIL_SIDE),
            str(item["model_name"]),
            str(item["information_set"]),
            str(item["forecast_date"]),
        ),
    )


def build_block_bootstrap_dm_records(
    loss_matrix: list[dict[str, object]],
    *,
    suite: str,
    anchor_model: str,
    anchor_information_set: str,
    reps: int = BOOTSTRAP_REPS,
    seed: int = INFERENCE_RANDOM_SEED,
) -> list[dict[str, object]]:
    grouped = _group_loss_matrix_by_key(loss_matrix)
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    for target_family, tail_side, tail_level, refit_frequency in sorted(
        {(key[0], key[5], key[3], key[4]) for key in grouped}
    ):
        anchor_key = (
            target_family,
            anchor_model,
            anchor_information_set,
            tail_level,
            refit_frequency,
            tail_side,
        )
        anchor_rows = grouped.get(anchor_key, {})
        for candidate_key in sorted(
            key
            for key in grouped
            if key[0] == target_family
            and key[5] == tail_side
            and key[3] == tail_level
            and key[4] == refit_frequency
        ):
            if candidate_key == anchor_key:
                continue
            candidate_rows = grouped[candidate_key]
            dates = sorted(
                day
                for day in set(anchor_rows).intersection(candidate_rows)
                if _optional_float(anchor_rows[day].get("fz_loss")) is not None
                and _optional_float(candidate_rows[day].get("fz_loss")) is not None
            )
            diffs = np.array(
                [
                    _required_float(candidate_rows[forecast_date]["fz_loss"])
                    - _required_float(anchor_rows[forecast_date]["fz_loss"])
                    for forecast_date in dates
                ],
                dtype=float,
            )
            diffs = diffs[np.isfinite(diffs)]
            block_length = max(5, round(len(diffs) ** (1.0 / 3.0))) if len(diffs) else None
            mean_diff = _safe_mean(diffs)
            joint_exception_count = _loss_matrix_joint_exception_count(
                grouped,
                [anchor_key, candidate_key],
                dates,
            )
            inference_status = _primary_dm_gate_status(len(dates), joint_exception_count)
            pvalue = (
                _moving_block_one_sided_pvalue(
                    diffs,
                    observed_mean=mean_diff,
                    reps=reps,
                    block_length=int(block_length),
                    rng=rng,
                    session_indices=[anchor_rows[day].get("target_session_index") for day in dates],
                )
                if inference_status == "ok_block_bootstrap_dm"
                and mean_diff is not None
                and block_length is not None
                else None
            )
            if inference_status == "ok_block_bootstrap_dm" and pvalue is None:
                inference_status = "unavailable_bootstrap_time_axis_or_sample"
            records.append(
                {
                    "suite": suite,
                    "target_family": target_family,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "refit_frequency": refit_frequency or None,
                    "baseline_model_name": anchor_model,
                    "baseline_information_set": anchor_information_set,
                    "candidate_model_name": candidate_key[1],
                    "candidate_information_set": candidate_key[2],
                    "paired_rows": int(diffs.size),
                    "common_n": len(dates),
                    "joint_exception_count": joint_exception_count,
                    "mean_fz_loss_diff_candidate_minus_baseline": mean_diff,
                    "alternative": "candidate_mean_diff_less_than_zero",
                    "null_hypothesis": "E[FZ_candidate_minus_baseline] >= 0",
                    "pvalue_one_sided": pvalue,
                    "reject_10pct": pvalue is not None and pvalue < 0.10,
                    "bootstrap_reps": reps,
                    "bootstrap_seed": seed,
                    "block_length": block_length,
                    "bootstrap_time_axis": "target_session_grid_with_missing_mask",
                    "method_note": PIPELINE_CONFIG.evaluation_policy.dm_method
                    if inference_status == "ok_block_bootstrap_dm"
                    else None,
                    "inference_status": inference_status,
                }
            )
    return records


def build_murphy_records(
    forecasts: list[dict[str, object]],
    *,
    suite: str,
    grid_size: int = 200,
) -> list[dict[str, object]]:
    valid_rows = _valid_forecast_rows(forecasts)
    losses = np.array([_required_float(row["realized_loss"]) for row in valid_rows], dtype=float)
    losses = losses[np.isfinite(losses)]
    if losses.size == 0:
        return []
    lower = float(np.quantile(losses, 0.01))
    upper = float(np.quantile(losses, 0.99))
    thresholds = np.linspace(lower, upper, grid_size)
    grouped = _group_forecasts_by_key(valid_rows)
    records: list[dict[str, object]] = []
    for key, rows_by_date in sorted(grouped.items()):
        rows = list(rows_by_date.values())
        row_losses = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var_values = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        alpha = 1.0 - key[3]
        for threshold_index, threshold in enumerate(thresholds):
            exceed = (row_losses > threshold).astype(float)
            elementary = (exceed - alpha) * (var_values - threshold)
            records.append(
                {
                    "suite": suite,
                    "target_family": key[0],
                    "tail_side": key[5],
                    "model_name": key[1],
                    "information_set": key[2],
                    "tail_level": key[3],
                    "refit_frequency": key[4] or None,
                    "threshold_index": threshold_index,
                    "threshold_value": float(threshold),
                    "threshold_grid_policy": "pooled_oos_loss_1pct_to_99pct_200_equal_points",
                    "rows": len(rows),
                    "mean_elementary_score": _safe_mean(elementary),
                }
            )
    return records


def build_stress_window_records(
    forecasts: list[dict[str, object]],
    *,
    suite: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    valid_rows = _valid_forecast_rows(forecasts)
    for tail_side in sorted({str(row.get("tail_side") or PRIMARY_TAIL_SIDE) for row in valid_rows}):
        loss_by_date: dict[str, float] = {}
        vix_by_date: dict[str, float] = {}
        for row in valid_rows:
            if str(row.get("tail_side") or PRIMARY_TAIL_SIDE) != tail_side:
                continue
            forecast_date = str(row["forecast_date"])
            loss = _optional_float(row.get("realized_loss"))
            if loss is not None and math.isfinite(loss):
                loss_by_date[forecast_date] = loss
            vix = _optional_float(row.get("vix_level"))
            if vix is not None and math.isfinite(vix):
                vix_by_date[forecast_date] = vix
        if loss_by_date:
            threshold = float(np.quantile(np.array(list(loss_by_date.values()), dtype=float), 0.90))
            records.extend(
                {
                    "suite": suite,
                    "tail_side": tail_side,
                    "window_name": "loss_top_decile",
                    "forecast_date": forecast_date,
                    "threshold_value": threshold,
                    "realized_loss": loss,
                    "vix_level": vix_by_date.get(forecast_date),
                    "classifier_policy": "full_sample_reproducible_decile",
                    "rolling_classifier_status": "future_work_not_used_in_first_round",
                }
                for forecast_date, loss in sorted(loss_by_date.items())
                if loss >= threshold
            )
        if vix_by_date:
            threshold = float(np.quantile(np.array(list(vix_by_date.values()), dtype=float), 0.90))
            records.extend(
                {
                    "suite": suite,
                    "tail_side": tail_side,
                    "window_name": "vix_top_decile",
                    "forecast_date": forecast_date,
                    "threshold_value": threshold,
                    "realized_loss": loss_by_date.get(forecast_date),
                    "vix_level": vix,
                    "classifier_policy": "full_sample_reproducible_decile",
                    "rolling_classifier_status": "future_work_not_used_in_first_round",
                }
                for forecast_date, vix in sorted(vix_by_date.items())
                if vix >= threshold
            )
    return records


def _valid_forecast_rows(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    return valid_forecast_rows(forecasts)


def _forecast_key(row: Mapping[str, object]) -> tuple[str, str, str, float, str, str]:
    return (
        str(row.get("target_family") or "full_gap_settle_to_open"),
        str(row["model_name"]),
        str(row.get("information_set") or "target_history_only"),
        _required_float(row["tail_level"]),
        str(row.get("refit_frequency") or ""),
        str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
    )


def _group_forecasts_by_key(
    forecasts: list[dict[str, object]],
) -> dict[tuple[str, str, str, float, str, str], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str, str, float, str, str], dict[str, dict[str, object]]] = {}
    for row in forecasts:
        date_rows = grouped.setdefault(_forecast_key(row), {})
        day = str(row["forecast_date"])
        if day in date_rows:
            raise ValueError(f"Duplicate forecast for {_forecast_key(row)} on {day}")
        date_rows[day] = row
    return grouped


def _group_loss_matrix_by_key(
    rows: list[dict[str, object]],
) -> dict[tuple[str, str, str, float, str, str], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str, str, float, str, str], dict[str, dict[str, object]]] = {}
    for row in rows:
        key = (
            str(row.get("target_family") or "full_gap_settle_to_open"),
            str(row["model_name"]),
            str(row.get("information_set") or "target_history_only"),
            _required_float(row["tail_level"]),
            str(row.get("refit_frequency") or ""),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
        )
        grouped.setdefault(key, {})[str(row["forecast_date"])] = row
    return grouped


def _loss_matrix_joint_exception_count(
    grouped: Mapping[tuple[str, str, str, float, str, str], Mapping[str, Mapping[str, object]]],
    keys: list[tuple[str, str, str, float, str, str]],
    common_dates: list[str],
) -> int:
    count = 0
    for forecast_date in common_dates:
        has_exception = False
        for key in keys:
            row = grouped.get(key, {}).get(forecast_date)
            if row is None:
                continue
            loss = _optional_float(row.get("realized_loss"))
            var = _optional_float(row.get("var_forecast"))
            if loss is not None and var is not None and loss > var:
                has_exception = True
                break
        count += int(has_exception)
    return count


def _primary_dm_gate_status(common_n: int, joint_exception_count: int) -> str:
    if common_n < RESULT_MATRIX_MIN_DM_ROWS:
        return "unavailable_insufficient_common_rows_for_inference"
    if joint_exception_count < RESULT_MATRIX_MIN_DM_EXCEPTIONS:
        return "unavailable_insufficient_tail_events_for_inference"
    return "ok_block_bootstrap_dm"


def _model_eviction_record(
    *,
    suite: str,
    key: tuple[str, str, str, float, str, str],
    anchor_key: tuple[str, str, str, float, str, str],
    anchor_rows: int,
    overlap_rows: int,
    coverage_ratio: float,
    retained: bool,
    eviction_reason: str | None,
    common_rows: int,
    common_anchor_coverage: float,
    common_sample_status_value: str,
) -> dict[str, object]:
    return {
        "suite": suite,
        "target_family": key[0],
        "tail_side": key[5],
        "model_name": key[1],
        "information_set": key[2],
        "tail_level": key[3],
        "refit_frequency": key[4] or None,
        "anchor_model_name": anchor_key[1],
        "anchor_information_set": anchor_key[2],
        "anchor_rows": anchor_rows,
        "overlap_rows": overlap_rows,
        "coverage_ratio": coverage_ratio,
        "eviction_threshold": MODEL_EVICTION_COVERAGE_THRESHOLD,
        "retained_for_primary": retained,
        "eviction_reason": eviction_reason,
        "common_rows": common_rows,
        "common_anchor_coverage": common_anchor_coverage,
        "common_sample_min_anchor_coverage": COMMON_SAMPLE_MIN_ANCHOR_COVERAGE,
        "common_sample_status": common_sample_status_value,
    }


def _combined_common_sample_status(status_by_tail: Mapping[object, str]) -> str:
    statuses = set(status_by_tail.values())
    if not statuses:
        return "unavailable_empty_forecasts"
    if "common_sample_unstable" in statuses:
        return "common_sample_unstable"
    if statuses == {"ok"}:
        return "ok"
    return ",".join(sorted(statuses))


def _moving_block_one_sided_pvalue(
    values: np.ndarray,
    *,
    observed_mean: float | None,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
    session_indices=None,
) -> float | None:
    return _session_block_pvalue(
        values,
        observed_mean=observed_mean,
        reps=reps,
        block_length=block_length,
        rng=rng,
        session_indices=session_indices,
    )


def _moving_block_greater_pvalue(
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
        if float(np.mean(np.array(sample, dtype=float))) >= observed_mean:
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


def christoffersen_independence_test(
    *, breaches: np.ndarray, session_indices=None
) -> dict[str, object]:
    return _session_independence_test(breaches=breaches, session_indices=session_indices)


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


def quantile_loss(loss: float, var_forecast: float, tail_level: float) -> float:
    alpha = 1.0 - tail_level
    indicator = 1.0 if loss > var_forecast else 0.0
    return float((indicator - alpha) * (loss - var_forecast))
