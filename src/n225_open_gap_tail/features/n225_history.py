# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    date,
    datetime,
    math,
    np,
    PIPELINE_CONFIG,
    UTC,
    _optional_float,
)

N225_HISTORY_FEATURES = (
    "n225_day_return_lag_1",
    "n225_night_return_lag_1",
    "n225_day_range_lag_1",
    "n225_night_range_lag_1",
    "n225_day_parkinson_var_lag_1",
    "n225_night_parkinson_var_lag_1",
    "n225_session_range_mean_20",
    "n225_session_parkinson_var_mean_20",
    "n225_session_up_semivar_20",
    "n225_session_down_semivar_20",
    "n225_session_skew_120",
    "n225_session_excess_kurtosis_120",
    "n225_volume_log1p_lag_1",
    "n225_open_interest_log1p_lag_1",
    "n225_volume_log_change_lag_1",
    "n225_open_interest_log_change_lag_1",
    "n225_volume_zscore_60",
    "n225_open_interest_zscore_60",
    "n225_volume_oi_ratio_lag_1",
    "n225_days_to_last_trade",
    "n225_days_to_sq",
    "n225_contract_month_sin",
    "n225_contract_month_cos",
)


def add_n225_history_features(panel_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Add timestamp-safe N225 futures history features using prior clean rows only."""
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    prior_summaries: list[dict[str, object]] = []
    output: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        forecast_date = _parse_date(enriched.get("forecast_date"))
        model_cutoff = _coerce_datetime(enriched.get("model_cutoff_ts_utc"))
        usable_summaries = _summaries_available_by_cutoff(prior_summaries, model_cutoff)
        latest_prior = usable_summaries[-1] if usable_summaries else None
        _stamp_lag_features(enriched, latest_prior)
        _stamp_rolling_session_features(
            enriched,
            prior_session_returns=_session_values(usable_summaries, "day_return", "night_return"),
            prior_session_ranges=_session_values(usable_summaries, "day_range", "night_range"),
            prior_session_parkinson_vars=_session_values(
                usable_summaries,
                "day_parkinson_var",
                "night_parkinson_var",
            ),
            latest_prior=latest_prior,
        )
        _stamp_volume_oi_features(enriched, usable_summaries)
        _stamp_contract_calendar_features(enriched, forecast_date)
        output.append(enriched)
        if enriched.get("clean_sample") is True:
            prior_summaries.append(_row_summary(enriched))
    return output


def _summaries_available_by_cutoff(
    summaries: list[dict[str, object]],
    model_cutoff: datetime | None,
) -> list[dict[str, object]]:
    if model_cutoff is None:
        return summaries
    return [
        summary
        for summary in summaries
        if (available_ts := _coerce_datetime(summary.get("vendor_available_ts_utc"))) is not None
        and available_ts <= model_cutoff
    ]


def _session_values(
    summaries: list[dict[str, object]],
    first_key: str,
    second_key: str,
) -> list[float]:
    values: list[float] = []
    for summary in summaries:
        for key in (first_key, second_key):
            value = summary.get(key)
            if isinstance(value, float) and math.isfinite(value):
                values.append(value)
    return values


def _stamp_lag_features(
    row: dict[str, object],
    latest_prior: dict[str, object] | None,
) -> None:
    mapping = {
        "n225_day_return_lag_1": "day_return",
        "n225_night_return_lag_1": "night_return",
        "n225_day_range_lag_1": "day_range",
        "n225_night_range_lag_1": "night_range",
        "n225_day_parkinson_var_lag_1": "day_parkinson_var",
        "n225_night_parkinson_var_lag_1": "night_parkinson_var",
        "n225_volume_log1p_lag_1": "volume_log1p",
        "n225_open_interest_log1p_lag_1": "open_interest_log1p",
        "n225_volume_oi_ratio_lag_1": "volume_oi_ratio",
    }
    for feature, source in mapping.items():
        _stamp_feature(
            row,
            feature,
            None if latest_prior is None else latest_prior.get(source),
            source_date=None if latest_prior is None else str(latest_prior.get("forecast_date")),
            available_ts=None
            if latest_prior is None
            else latest_prior.get("vendor_available_ts_utc"),
        )


def _stamp_rolling_session_features(
    row: dict[str, object],
    *,
    prior_session_returns: list[float],
    prior_session_ranges: list[float],
    prior_session_parkinson_vars: list[float],
    latest_prior: dict[str, object] | None,
) -> None:
    policy = PIPELINE_CONFIG.feature_engineering
    range_values = prior_session_ranges[-policy.n225_range_window :]
    parkinson_values = prior_session_parkinson_vars[-policy.n225_range_window :]
    semivar_values = prior_session_returns[-policy.n225_semivariance_window :]
    moment_values = prior_session_returns[-policy.n225_higher_moment_window :]
    source_date = None if latest_prior is None else str(latest_prior.get("forecast_date"))
    available_ts = None if latest_prior is None else latest_prior.get("vendor_available_ts_utc")
    _stamp_feature(
        row,
        "n225_session_range_mean_20",
        _mean_if_enough(range_values, policy.n225_range_min_periods),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_session_parkinson_var_mean_20",
        _mean_if_enough(parkinson_values, policy.n225_range_min_periods),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_session_up_semivar_20",
        _semivar_if_enough(
            semivar_values,
            min_periods=policy.n225_semivariance_min_periods,
            positive=True,
        ),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_session_down_semivar_20",
        _semivar_if_enough(
            semivar_values,
            min_periods=policy.n225_semivariance_min_periods,
            positive=False,
        ),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_session_skew_120",
        _sample_skew(moment_values, min_periods=policy.n225_higher_moment_min_periods),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_session_excess_kurtosis_120",
        _sample_excess_kurtosis(
            moment_values,
            min_periods=policy.n225_higher_moment_min_periods,
        ),
        source_date=source_date,
        available_ts=available_ts,
    )


def _stamp_volume_oi_features(
    row: dict[str, object],
    prior_summaries: list[dict[str, object]],
) -> None:
    policy = PIPELINE_CONFIG.feature_engineering
    latest_prior = prior_summaries[-1] if prior_summaries else None
    previous_prior = prior_summaries[-2] if len(prior_summaries) >= 2 else None
    source_date = None if latest_prior is None else str(latest_prior.get("forecast_date"))
    available_ts = None if latest_prior is None else latest_prior.get("vendor_available_ts_utc")
    _stamp_feature(
        row,
        "n225_volume_log_change_lag_1",
        _difference(latest_prior, previous_prior, "volume_log1p"),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_open_interest_log_change_lag_1",
        _difference(latest_prior, previous_prior, "open_interest_log1p"),
        source_date=source_date,
        available_ts=available_ts,
    )
    window = prior_summaries[-policy.n225_volume_oi_zscore_window :]
    _stamp_feature(
        row,
        "n225_volume_zscore_60",
        _zscore_latest(
            [item.get("volume_log1p") for item in window],
            min_periods=policy.n225_volume_oi_zscore_min_periods,
        ),
        source_date=source_date,
        available_ts=available_ts,
    )
    _stamp_feature(
        row,
        "n225_open_interest_zscore_60",
        _zscore_latest(
            [item.get("open_interest_log1p") for item in window],
            min_periods=policy.n225_volume_oi_zscore_min_periods,
        ),
        source_date=source_date,
        available_ts=available_ts,
    )


def _stamp_contract_calendar_features(
    row: dict[str, object],
    forecast_date: date | None,
) -> None:
    last_trade = _parse_date(row.get("last_trading_day"))
    sq = _parse_date(row.get("special_quotation_day"))
    _stamp_feature(
        row,
        "n225_days_to_last_trade",
        None
        if forecast_date is None or last_trade is None
        else float((last_trade - forecast_date).days),
        source_date=None if forecast_date is None else forecast_date.isoformat(),
        available_ts=None,
    )
    _stamp_feature(
        row,
        "n225_days_to_sq",
        None if forecast_date is None or sq is None else float((sq - forecast_date).days),
        source_date=None if forecast_date is None else forecast_date.isoformat(),
        available_ts=None,
    )
    month = _contract_month_number(row.get("contract_month"))
    angle = None if month is None else 2.0 * math.pi * (month - 1) / 12.0
    _stamp_feature(
        row,
        "n225_contract_month_sin",
        None if angle is None else math.sin(angle),
        source_date=None if forecast_date is None else forecast_date.isoformat(),
        available_ts=None,
    )
    _stamp_feature(
        row,
        "n225_contract_month_cos",
        None if angle is None else math.cos(angle),
        source_date=None if forecast_date is None else forecast_date.isoformat(),
        available_ts=None,
    )


def _row_summary(row: dict[str, object]) -> dict[str, object]:
    volume = _optional_float(row.get("volume"))
    open_interest = _optional_float(row.get("open_interest"))
    return {
        "forecast_date": row.get("forecast_date"),
        "vendor_available_ts_utc": _coerce_datetime(row.get("jquants_vendor_available_ts_utc")),
        "day_return": _log_return(row.get("day_session_open"), row.get("day_session_close")),
        "night_return": _log_return(row.get("night_session_open"), row.get("night_session_close")),
        "day_range": _log_range(row, prefix="day_session"),
        "night_range": _log_range(row, prefix="night_session"),
        "day_parkinson_var": _parkinson_var(row, prefix="day_session"),
        "night_parkinson_var": _parkinson_var(row, prefix="night_session"),
        "volume_log1p": None if volume is None or volume < 0 else math.log1p(volume),
        "open_interest_log1p": None
        if open_interest is None or open_interest < 0
        else math.log1p(open_interest),
        "volume_oi_ratio": None
        if volume is None or open_interest is None or open_interest <= 0
        else volume / open_interest,
    }


def _log_return(start_value: object, end_value: object) -> float | None:
    start = _optional_float(start_value)
    end = _optional_float(end_value)
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _log_range(row: dict[str, object], *, prefix: str) -> float | None:
    high = _optional_float(row.get(f"{prefix}_high"))
    low = _optional_float(row.get(f"{prefix}_low"))
    if high is None or low is None or high <= 0 or low <= 0 or high < low:
        return None
    return math.log(high) - math.log(low)


def _parkinson_var(row: dict[str, object], *, prefix: str) -> float | None:
    range_value = _log_range(row, prefix=prefix)
    if range_value is None:
        return None
    return (range_value * range_value) / (4.0 * math.log(2.0))


def _mean_if_enough(values: list[float], min_periods: int) -> float | None:
    valid = [value for value in values if math.isfinite(value)]
    if len(valid) < min_periods:
        return None
    return float(np.mean(valid))


def _semivar_if_enough(
    values: list[float],
    *,
    min_periods: int,
    positive: bool,
) -> float | None:
    valid = [value for value in values if math.isfinite(value)]
    if len(valid) < min_periods:
        return None
    selected = (
        [value for value in valid if value > 0]
        if positive
        else [value for value in valid if value < 0]
    )
    if not selected:
        return 0.0
    return float(np.mean([value * value for value in selected]))


def _sample_skew(values: list[float], *, min_periods: int) -> float | None:
    valid = [value for value in values if math.isfinite(value)]
    if len(valid) < min_periods:
        return None
    array = np.asarray(valid, dtype=float)
    std = float(np.std(array, ddof=1))
    if std == 0.0:
        return None
    centered = array - float(np.mean(array))
    return float(np.mean((centered / std) ** 3))


def _sample_excess_kurtosis(values: list[float], *, min_periods: int) -> float | None:
    valid = [value for value in values if math.isfinite(value)]
    if len(valid) < min_periods:
        return None
    array = np.asarray(valid, dtype=float)
    std = float(np.std(array, ddof=1))
    if std == 0.0:
        return None
    centered = array - float(np.mean(array))
    return float(np.mean((centered / std) ** 4) - 3.0)


def _zscore_latest(values: list[object], *, min_periods: int) -> float | None:
    valid = [
        float(value) for value in values if isinstance(value, int | float) and math.isfinite(value)
    ]
    if len(valid) < min_periods:
        return None
    latest = valid[-1]
    mean = float(np.mean(valid))
    std = float(np.std(valid, ddof=1))
    if std == 0.0:
        return None
    return (latest - mean) / std


def _difference(
    latest_prior: dict[str, object] | None,
    previous_prior: dict[str, object] | None,
    key: str,
) -> float | None:
    latest = None if latest_prior is None else _optional_float(latest_prior.get(key))
    previous = None if previous_prior is None else _optional_float(previous_prior.get(key))
    if latest is None or previous is None:
        return None
    return latest - previous


def _stamp_feature(
    row: dict[str, object],
    feature_name: str,
    value: object,
    *,
    source_date: str | None,
    available_ts: object | None,
) -> None:
    row[feature_name] = value if _is_finite_or_none(value) else None
    row[f"{feature_name}__source_date"] = source_date
    row[f"{feature_name}__fill_method"] = "prior_clean_history"
    if available_ts is not None:
        row[f"{feature_name}__available_ts_utc"] = _coerce_datetime(available_ts)


def _is_finite_or_none(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, int | float):
        return math.isfinite(value)
    return False


def _parse_date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _contract_month_number(value: object) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(value.split("-")[-1])
    except ValueError:
        return None


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None
