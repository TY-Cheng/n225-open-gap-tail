# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from zoneinfo import ZoneInfo

from n225_open_gap_tail.config.runtime import *
from n225_open_gap_tail.features.descriptions import _safe_name, _window_range, _window_return


def _features_asof(
    features_by_date: dict[str, dict[str, object]],
    date_key: str,
    *,
    cutoff: datetime | None = None,
    fill_method: str,
) -> dict[str, object]:
    if not date_key:
        return {}
    try:
        target_date = date.fromisoformat(date_key)
    except ValueError:
        return {}
    prior_keys = [key for key in features_by_date if key <= date_key]
    if not prior_keys:
        return {}
    for selected_key in sorted(prior_keys, reverse=True):
        try:
            selected_date = date.fromisoformat(selected_key)
        except ValueError:
            continue
        if (
            target_date - selected_date
        ).days > PIPELINE_CONFIG.leakage_policy.max_forward_fill_us_close_days:
            continue
        output = dict(features_by_date[selected_key])
        if cutoff is not None and not _feature_record_available_by_cutoff(output, cutoff):
            continue
        selected_fill_method = "direct" if selected_key == date_key else fill_method
        for feature_name in _feature_value_names(output):
            output[f"{feature_name}__fill_method"] = selected_fill_method
            output[f"{feature_name}__source_date"] = selected_key
        return output
    return {}


def _fred_features_asof(
    features_by_date: dict[str, dict[str, object]],
    date_key: str,
    *,
    cutoff: datetime | None = None,
) -> dict[str, object]:
    """Select FRED predictors feature-by-feature using timestamp-safe as-of logic."""
    if not date_key or cutoff is None:
        return {}
    try:
        date.fromisoformat(date_key)
    except ValueError:
        return {}
    feature_names = sorted(
        {
            feature
            for record in features_by_date.values()
            for feature in _feature_value_names(record)
            if feature.startswith("fred_")
        }
    )
    output: dict[str, object] = {}
    rate_source_ages: list[int] = []
    rate_available_ts: list[datetime] = []
    rate_source_dates: list[str] = []
    for feature_name in feature_names:
        selected = _fred_feature_candidate_asof(
            features_by_date,
            date_key=date_key,
            feature_name=feature_name,
            cutoff=cutoff,
        )
        if selected is None:
            continue
        is_forward_fill = selected["date_key"] != date_key
        is_filled_diff = bool(is_forward_fill and feature_name.endswith("_diff"))
        output[feature_name] = 0.0 if is_filled_diff else selected["value"]
        _stamp_feature_metadata(
            output,
            feature_name=feature_name,
            available_ts_utc=cast(datetime | None, selected["available_ts_utc"]),
            source_date=str(selected["source_date"]),
            fill_method="forward_fill_fred_release_lag" if is_forward_fill else "direct",
        )
        output[f"{feature_name}__forward_fill_fred_release_lag"] = is_forward_fill
        output[f"{feature_name}__fill_source_obs_date"] = selected["source_date"]
        output[f"{feature_name}__fill_feature_available_ts_utc"] = selected["available_ts_utc"]
        output[f"{feature_name}__is_filled_diff"] = is_filled_diff
        output[f"{feature_name}__fred_release_lag_days"] = selected["release_lag_days"]
        output[f"{feature_name}__fred_source_age_days"] = selected["source_age_days"]
        if (
            feature_name in FRED_RATE_STALENESS_LEVEL_FEATURES
            and selected["source_age_days"] is not None
        ):
            rate_source_ages.append(int(cast(int, selected["source_age_days"])))
            if selected["available_ts_utc"] is not None:
                rate_available_ts.append(cast(datetime, selected["available_ts_utc"]))
            if selected["source_date"]:
                rate_source_dates.append(str(selected["source_date"]))
    _synthesize_forward_filled_fred_diffs(output, feature_names)
    if rate_source_ages:
        output[FRED_RATE_STALENESS_FEATURE] = float(max(rate_source_ages))
        latest_rate_available = max(rate_available_ts) if rate_available_ts else None
        latest_source_date = max(rate_source_dates) if rate_source_dates else date_key
        _stamp_feature_metadata(
            output,
            feature_name=FRED_RATE_STALENESS_FEATURE,
            available_ts_utc=latest_rate_available,
            source_date=latest_source_date,
            fill_method="fred_rates_staleness",
        )
    return output


def _synthesize_forward_filled_fred_diffs(
    output: dict[str, object],
    feature_names: list[str],
) -> None:
    for level_feature in [
        key for key in output if key.startswith("fred_") and key.endswith("_level")
    ]:
        diff_feature = f"{level_feature.removesuffix('_level')}_diff"
        if diff_feature not in feature_names or diff_feature in output:
            continue
        if output.get(f"{level_feature}__fill_method") != "forward_fill_fred_release_lag":
            continue
        available_ts = _coerce_datetime(output.get(f"{level_feature}__available_ts_utc"))
        source_date = str(output.get(f"{level_feature}__source_date") or "")
        output[diff_feature] = 0.0
        _stamp_feature_metadata(
            output,
            feature_name=diff_feature,
            available_ts_utc=available_ts,
            source_date=source_date,
            fill_method="forward_fill_fred_release_lag",
        )
        for suffix in (
            "forward_fill_fred_release_lag",
            "fill_source_obs_date",
            "fill_feature_available_ts_utc",
            "fred_release_lag_days",
            "fred_source_age_days",
        ):
            output[f"{diff_feature}__{suffix}"] = output.get(f"{level_feature}__{suffix}")
        output[f"{diff_feature}__is_filled_diff"] = True


def _fred_feature_candidate_asof(
    features_by_date: dict[str, dict[str, object]],
    *,
    date_key: str,
    feature_name: str,
    cutoff: datetime,
) -> dict[str, object] | None:
    try:
        target_date = date.fromisoformat(date_key)
    except ValueError:
        return None
    prior_keys = [key for key in features_by_date if key <= date_key]
    for selected_key in sorted(prior_keys, reverse=True):
        try:
            selected_date = date.fromisoformat(selected_key)
        except ValueError:
            continue
        release_lag_days = (target_date - selected_date).days
        if release_lag_days > PIPELINE_CONFIG.leakage_policy.max_forward_fill_us_close_days:
            continue
        record = features_by_date[selected_key]
        value = _optional_float(record.get(feature_name))
        if value is None:
            continue
        available_ts = _coerce_datetime(record.get(f"{feature_name}__available_ts_utc"))
        if available_ts is None or available_ts > cutoff:
            continue
        source_date_text = str(record.get(f"{feature_name}__source_date") or selected_key)
        try:
            source_date = date.fromisoformat(source_date_text)
        except ValueError:
            source_date = selected_date
            source_date_text = selected_key
        source_age_days = max(0, (target_date - source_date).days)
        return {
            "date_key": selected_key,
            "value": value,
            "available_ts_utc": available_ts,
            "source_date": source_date_text,
            "release_lag_days": release_lag_days,
            "source_age_days": source_age_days,
        }
    return None


def _feature_record_available_by_cutoff(
    record: Mapping[str, object],
    cutoff: datetime,
) -> bool:
    value_names = _feature_value_names(record)
    if not value_names:
        return True
    evaluable = False
    for feature_name in value_names:
        if record.get(feature_name) is None:
            continue
        available_ts = _coerce_datetime(record.get(f"{feature_name}__available_ts_utc"))
        if available_ts is None or available_ts > cutoff:
            return False
        evaluable = True
    return evaluable


def _feature_value_names(record: Mapping[str, object]) -> list[str]:
    return sorted(
        key
        for key in record
        if "__" not in key
        and (
            key.endswith("_return")
            or key.endswith("_range")
            or key.endswith("_diff")
            or key.endswith("_level")
            or key.endswith("_days")
            or key.startswith("spy_late_")
            or key.startswith("spy_final_")
        )
    )


def _stamp_feature_metadata(
    output: dict[str, object],
    *,
    feature_name: str,
    available_ts_utc: datetime | None,
    source_date: str,
    fill_method: str = "direct",
) -> None:
    output[f"{feature_name}__available_ts_utc"] = available_ts_utc
    output[f"{feature_name}__source_date"] = source_date
    output[f"{feature_name}__fill_method"] = fill_method


def _feature_available_ts(row: Mapping[str, object], *, lag_minutes: int = 0) -> datetime | None:
    raw = row.get("vendor_available_ts_utc") or row.get("bar_end_ts_utc")
    ts = _coerce_datetime(raw)
    if ts is None:
        return None
    return ts + timedelta(minutes=lag_minutes)


def _official_us_close_by_date(
    calendar_records: list[dict[str, object]],
) -> dict[str, datetime]:
    closes: dict[str, datetime] = {}
    for row in calendar_records:
        date_key = str(row.get("calendar_date") or "")
        close_ts = _coerce_datetime(row.get("us_close_ts_utc"))
        if date_key and close_ts is not None:
            closes[date_key] = close_ts
    return closes


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _evt_threshold_diagnostics(values: np.ndarray) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    previous_shape: float | None = None
    previous_scale: float | None = None
    for quantile in EVT_THRESHOLD_GRID:
        threshold = float(np.quantile(values, quantile))
        excesses = values[values > threshold] - threshold
        row: dict[str, object] = {
            "threshold_quantile": quantile,
            "threshold_value": threshold,
            "exceedance_count": int(excesses.size),
            "mean_excess": float(np.mean(excesses)) if excesses.size else None,
        }
        if excesses.size >= 10:
            shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
            shape = float(shape)
            scale = float(scale)
            row["shape"] = shape
            row["scale"] = scale
            row["shape_delta_from_previous"] = (
                None if previous_shape is None else shape - previous_shape
            )
            row["scale_delta_from_previous"] = (
                None if previous_scale is None else scale - previous_scale
            )
            previous_shape = shape
            previous_scale = scale
        else:
            row["shape"] = None
            row["scale"] = None
            row["shape_delta_from_previous"] = None
            row["scale_delta_from_previous"] = None
        row["selected_threshold"] = quantile == EVT_THRESHOLD_QUANTILE
        row["selection_rationale"] = (
            "primary_pre_registered_threshold"
            if quantile == EVT_THRESHOLD_QUANTILE
            else "sensitivity_grid"
        )
        diagnostics.append(row)
    return diagnostics


def _massive_daily_feature_map(
    records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]] | None = None,
) -> dict[str, dict[str, object]]:
    official_close_by_date = _official_us_close_by_date(calendar_records or [])
    by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_ticker.setdefault(str(row["ticker"]), []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: str(row["bar_date_et"]))
        previous_close: float | None = None
        safe = _safe_name(ticker)
        for row in rows:
            date_key = str(row["bar_date_et"])
            close = _optional_float(row.get("close"))
            high = _optional_float(row.get("high"))
            low = _optional_float(row.get("low"))
            output = features_by_date.setdefault(date_key, {})
            official_close = official_close_by_date.get(date_key)
            available_ts = (
                official_close
                + timedelta(minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes)
                if official_close is not None
                else _feature_available_ts(
                    row,
                    lag_minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes,
                )
            )
            return_name = f"{safe}_return"
            range_name = f"{safe}_range"
            if close is not None and previous_close and previous_close > 0:
                output[return_name] = math.log(close) - math.log(previous_close)
            else:
                output[return_name] = None
            if high is not None and low is not None and high > 0 and low > 0:
                output[range_name] = math.log(high) - math.log(low)
            else:
                output[range_name] = None
            _stamp_feature_metadata(
                output,
                feature_name=return_name,
                available_ts_utc=available_ts,
                source_date=date_key,
            )
            _stamp_feature_metadata(
                output,
                feature_name=range_name,
                available_ts_utc=available_ts,
                source_date=date_key,
            )
            if close is not None:
                previous_close = close
    return features_by_date


def _fred_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_series: dict[str, list[dict[str, object]]] = {}
    for row in records:
        series_id = str(row["series_id"])
        if series_id.upper() in FX_FRED_SERIES_FOR_PIPELINE:
            continue
        by_series.setdefault(series_id, []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for series, rows in by_series.items():
        rows.sort(key=lambda row: str(row["observation_date"]))
        previous: float | None = None
        safe = _safe_name(series)
        for row in rows:
            date_key = str(row.get("vendor_available_date_et") or row["observation_date"])
            value = _optional_float(row.get("value"))
            output = features_by_date.setdefault(date_key, {})
            available_ts = _feature_available_ts(row)
            level_name = f"fred_{safe}_level"
            diff_name = f"fred_{safe}_diff"
            output[level_name] = value
            output[diff_name] = None if value is None or previous is None else value - previous
            _stamp_feature_metadata(
                output,
                feature_name=level_name,
                available_ts_utc=available_ts,
                source_date=str(row["observation_date"]),
            )
            _stamp_feature_metadata(
                output,
                feature_name=diff_name,
                available_ts_utc=available_ts,
                source_date=str(row["observation_date"]),
            )
            if value is not None:
                previous = value
    return features_by_date


def _cboe_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    features_by_date: dict[str, dict[str, object]] = {}
    for row in sorted(records, key=lambda item: str(item.get("observation_date") or "")):
        if str(row.get("symbol", "")).upper() != "VIX":
            continue
        date_key = str(row["observation_date"])
        output = features_by_date.setdefault(date_key, {})
        close = _optional_float(row.get("close"))
        range_value = _optional_float(row.get("range"))
        available_ts = _coerce_datetime(row.get("vendor_available_ts_utc"))
        output["cboe_vix_close"] = close
        output["cboe_vix_range"] = range_value
        _stamp_feature_metadata(
            output,
            feature_name="cboe_vix_close",
            available_ts_utc=available_ts,
            source_date=date_key,
        )
        _stamp_feature_metadata(
            output,
            feature_name="cboe_vix_range",
            available_ts_utc=available_ts,
            source_date=date_key,
        )
    return features_by_date


def _canonical_fx_context(
    *,
    massive_daily_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
) -> dict[str, object]:
    _ = massive_daily_records, calendar_records
    return {"fred": _fred_fx_records(fred_records)}


def _fred_fx_records(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    rows = [
        row
        for row in records
        if str(row.get("series_id", "")).upper() in FX_FRED_SERIES_FOR_PIPELINE
    ]
    rows.sort(key=lambda row: str(row.get("observation_date") or ""))
    output: dict[str, dict[str, object]] = {}
    previous_value: float | None = None
    for row in rows:
        observation_date = str(row.get("observation_date") or "")
        if not observation_date:
            continue
        value = _optional_float(row.get("value"))
        fx_return = (
            math.log(value) - math.log(previous_value)
            if value is not None and previous_value is not None and value > 0 and previous_value > 0
            else None
        )
        output[observation_date] = {
            "observation_date": observation_date,
            "value": value,
            "return": fx_return,
            "available_ts": _coerce_datetime(row.get("vendor_available_ts_utc")),
            "source": "fred_h10",
        }
        if value is not None and value > 0:
            previous_value = value
    return output


def _canonical_fx_asof(
    context: Mapping[str, object],
    *,
    us_date: str,
    cutoff: datetime | None,
) -> dict[str, object]:
    if not us_date or cutoff is None:
        return {}
    try:
        target_date = date.fromisoformat(us_date)
    except ValueError:
        return {}
    fred_rows = cast(dict[str, dict[str, object]], context.get("fred") or {})
    exact_fred = fred_rows.get(us_date)
    latest_fred = _latest_usable_fx_candidate(
        fred_rows,
        target_date=target_date,
        cutoff=cutoff,
        max_release_age_days=FRED_H10_RELEASE_AGE_CAP_DAYS,
    )
    if latest_fred is not None:
        return _fx_output(
            latest_fred,
            target_date=target_date,
            cutoff=cutoff,
            source="fred_h10_latest_released",
            reason="fred_h10_latest_released",
            fred_available=True,
        )

    return {
        "fx_usdjpy_level": None,
        "fx_usdjpy_return": None,
        "fx_source": "null_unavailable",
        "fx_observation_date": None,
        "fx_available_ts_utc": None,
        "fx_staleness_days": None,
        "fx_observation_age_days": None,
        "fx_release_age_days": None,
        "fx_is_stale": None,
        "fx_fallback_reason": _fred_fx_unavailable_reason(
            exact_fred,
            fred_rows=fred_rows,
            target_date=target_date,
            cutoff=cutoff,
        ),
        "fred_dexjpus_available": False,
    }


def _latest_usable_fx_candidate(
    rows: dict[str, dict[str, object]],
    *,
    target_date: date,
    cutoff: datetime,
    max_release_age_days: int,
) -> dict[str, object] | None:
    candidates = []
    for row in rows.values():
        if not _fx_candidate_is_usable(
            row,
            cutoff=cutoff,
            target_date=target_date,
            max_release_age_days=max_release_age_days,
        ):
            continue
        candidates.append(row)
    if not candidates:
        return None
    return max(candidates, key=lambda row: str(row["observation_date"]))


def _fx_candidate_is_usable(
    row: Mapping[str, object],
    *,
    cutoff: datetime,
    target_date: date,
    max_release_age_days: int,
) -> bool:
    value = _optional_float(row.get("value"))
    available_ts = _coerce_datetime(row.get("available_ts"))
    observation_date = _fx_observation_date(row)
    if value is None or not math.isfinite(value) or value <= 0:
        return False
    if available_ts is None or available_ts > cutoff:
        return False
    if observation_date is None:
        return False
    if observation_date > target_date:
        return False
    release_age_days = _fred_h10_release_age_days(cutoff=cutoff, available_ts=available_ts)
    return release_age_days <= max_release_age_days


def _fx_output(
    row: Mapping[str, object],
    *,
    target_date: date,
    cutoff: datetime,
    source: str,
    reason: str,
    fred_available: bool,
) -> dict[str, object]:
    observation_date = _fx_observation_date(row)
    available_ts = _coerce_datetime(row.get("available_ts"))
    observation_age_days = (
        None if observation_date is None else (target_date - observation_date).days
    )
    release_age_days = (
        None
        if available_ts is None
        else _fred_h10_release_age_days(cutoff=cutoff, available_ts=available_ts)
    )
    source_date = observation_date.isoformat() if observation_date else None
    output: dict[str, object] = {
        "fx_usdjpy_level": _optional_float(row.get("value")),
        "fx_usdjpy_return": _optional_float(row.get("return")),
        "fx_source": source,
        "fx_observation_date": source_date,
        "fx_available_ts_utc": available_ts,
        "fx_staleness_days": observation_age_days,
        "fx_observation_age_days": observation_age_days,
        "fx_release_age_days": release_age_days,
        "fx_is_stale": observation_age_days is not None and observation_age_days > 0,
        "fx_fallback_reason": reason,
        "fred_dexjpus_available": fred_available,
    }
    for feature_name in ("fx_usdjpy_level", "fx_usdjpy_return"):
        _stamp_feature_metadata(
            output,
            feature_name=feature_name,
            available_ts_utc=available_ts,
            source_date=source_date or "",
            fill_method=source,
        )
    return output


def _fred_h10_release_age_days(*, cutoff: datetime, available_ts: datetime) -> int:
    """Calendar days since the expected H.10 release in the U.S. release calendar."""
    release_zone = ZoneInfo("America/New_York")
    cutoff_release_date = cutoff.astimezone(release_zone).date()
    available_release_date = available_ts.astimezone(release_zone).date()
    return max(0, (cutoff_release_date - available_release_date).days)


def _fx_observation_date(row: Mapping[str, object]) -> date | None:
    raw = row.get("observation_date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _fred_fx_unavailable_reason(
    exact_fred: Mapping[str, object] | None,
    *,
    fred_rows: Mapping[str, Mapping[str, object]],
    target_date: date,
    cutoff: datetime,
) -> str:
    if exact_fred is None:
        pass
    else:
        value = _optional_float(exact_fred.get("value"))
        available = _coerce_datetime(exact_fred.get("available_ts"))
        if value is None or not math.isfinite(value):
            return JoinMissReason.FRED_FX_NULL_OBSERVATION.value
        if available is None or available > cutoff:
            return JoinMissReason.FRED_H10_RELEASE_DELAY.value
    released_values = [
        row
        for row in fred_rows.values()
        if (value := _optional_float(row.get("value"))) is not None
        and math.isfinite(value)
        and (available := _coerce_datetime(row.get("available_ts"))) is not None
        and available <= cutoff
        and (observation_date := _fx_observation_date(row)) is not None
        and observation_date <= target_date
    ]
    if released_values:
        return JoinMissReason.FRED_FX_STALE_BEYOND_FILL_WINDOW.value
    return JoinMissReason.FRED_H10_RELEASE_DELAY.value


def _spy_minute_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    if any("spy_late_30m_return" in row for row in records):
        from n225_open_gap_tail.features.jquants_spy import (
            _records_with_recomputed_spy_late_volume_surge,
        )

        records = _records_with_recomputed_spy_late_volume_surge(records)
        derived_features: dict[str, dict[str, object]] = {}
        for row in records:
            date_key = str(row.get("bar_date_et") or "")
            if not date_key:
                continue
            derived_features[date_key] = {
                "spy_late_30m_return": _optional_float(row.get("spy_late_30m_return")),
                "spy_late_60m_return": _optional_float(row.get("spy_late_60m_return")),
                "spy_late_session_range": _optional_float(row.get("spy_late_session_range")),
                "spy_late_volume_surge": _optional_float(row.get("spy_late_volume_surge")),
                "spy_final_window_momentum": _optional_float(row.get("spy_final_window_momentum")),
            }
            available_ts = _coerce_datetime(row.get("feature_available_ts_utc"))
            for feature_name in _feature_value_names(derived_features[date_key]):
                _stamp_feature_metadata(
                    derived_features[date_key],
                    feature_name=feature_name,
                    available_ts_utc=available_ts,
                    source_date=date_key,
                )
        return derived_features
    by_date: dict[str, list[dict[str, object]]] = {}
    for row in records:
        if row.get("is_us_regular_session") is True:
            by_date.setdefault(str(row["bar_date_et"]), []).append(row)
    features: dict[str, dict[str, object]] = {}
    rolling_late_volume: list[float] = []
    for date_key in sorted(by_date):
        rows = sorted(by_date[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
        closes = [_optional_float(row.get("close")) for row in rows]
        highs = [_optional_float(row.get("high")) for row in rows]
        lows = [_optional_float(row.get("low")) for row in rows]
        volumes = [_optional_float(row.get("volume")) or 0.0 for row in rows]
        valid_closes = [value for value in closes if value is not None and value > 0]
        late_volume = float(sum(volumes[-60:]))
        rolling_mean_volume = (
            float(np.mean(rolling_late_volume[-20:])) if rolling_late_volume else None
        )
        volume_surge = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else late_volume / rolling_mean_volume
        )
        last_available_ts = _feature_available_ts(
            rows[-1],
            lag_minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes,
        )
        features[date_key] = {
            "spy_late_30m_return": _window_return(valid_closes, 30),
            "spy_late_60m_return": _window_return(valid_closes, 60),
            "spy_late_session_range": _window_range(highs[-60:], lows[-60:]),
            "spy_late_volume_surge": volume_surge,
            "spy_final_window_momentum": _window_return(valid_closes, 15),
        }
        for feature_name in _feature_value_names(features[date_key]):
            _stamp_feature_metadata(
                features[date_key],
                feature_name=feature_name,
                available_ts_utc=last_available_ts,
                source_date=date_key,
            )
        rolling_late_volume.append(late_volume)
    return features
