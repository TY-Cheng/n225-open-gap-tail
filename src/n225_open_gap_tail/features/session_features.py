# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    atomic_write_parquet,
    cache_path,
    date,
    datetime,
    JQUANTS_SILVER_SCHEMA,
    Mapping,
    math,
    np,
    PIPELINE_CONFIG,
    Settings,
    timedelta,
    UTC,
    _add_stat,
    _log_year_stats,
    _new_progress_stats,
    _optional_float,
)
from n225_open_gap_tail.features.asof import _coerce_datetime
from n225_open_gap_tail.features.descriptions import (
    _optional_text,
    _safe_name,
    _window_range,
    _window_return,
)


def add_jquants_silver_flags(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flagged: list[dict[str, object]] = []
    for row in rows:
        output = dict(row)
        for source_name, flag_name in (
            ("day_session_open", "invalid_day_session_open"),
            ("day_session_high", "invalid_day_session_high"),
            ("day_session_low", "invalid_day_session_low"),
            ("day_session_close", "invalid_day_session_close"),
            ("night_session_open", "invalid_night_session_open"),
            ("night_session_high", "invalid_night_session_high"),
            ("night_session_low", "invalid_night_session_low"),
            ("night_session_close", "invalid_night_session_close"),
            ("settlement_price", "invalid_settlement_price"),
        ):
            value = _optional_float(row.get(source_name))
            output[flag_name] = value is None or value <= 0
        output["day_session_ohlc_violation"] = _ohlc_violation(
            open_value=row.get("day_session_open"),
            high_value=row.get("day_session_high"),
            low_value=row.get("day_session_low"),
            close_value=row.get("day_session_close"),
        )
        output["night_session_ohlc_violation"] = _ohlc_violation(
            open_value=row.get("night_session_open"),
            high_value=row.get("night_session_high"),
            low_value=row.get("night_session_low"),
            close_value=row.get("night_session_close"),
        )
        output["night_session_close_ts_utc"] = row.get("night_close_ts_utc")
        flagged.append(output)
    return flagged


def _ohlc_violation(
    *,
    open_value: object,
    high_value: object,
    low_value: object,
    close_value: object,
) -> bool:
    open_price = _optional_float(open_value)
    high_price = _optional_float(high_value)
    low_price = _optional_float(low_value)
    close_price = _optional_float(close_value)
    if high_price is None or low_price is None:
        return False
    if high_price <= 0 or low_price <= 0 or high_price < low_price:
        return True
    for value in (open_price, close_price):
        if value is not None and (value < low_price or value > high_price):
            return True
    return False


def _write_jquants_silver_cache(*, settings: Settings, rows: list[dict[str, object]]) -> None:
    root = settings.data_dir / "silver"
    by_month: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in rows:
        trading_date = str(row.get("trading_date") or "")
        if not trading_date:
            continue
        parsed = date.fromisoformat(trading_date)
        by_month.setdefault((parsed.year, parsed.month), []).append(row)
    year_stats_by_year: dict[int, dict[str, int]] = {}
    for (year, month), chunk_rows in sorted(by_month.items()):
        path = cache_path(
            root,
            dataset="jquants_nk225f_daily",
            schema_version=JQUANTS_SILVER_SCHEMA.version,
            year=year,
            month=month,
        )
        result = atomic_write_parquet(
            path,
            chunk_rows,
            schema=JQUANTS_SILVER_SCHEMA,
            metadata={
                "source": "jquants",
                "layer": "silver",
                "product_category": "NK225F",
                "year": year,
                "month": month,
            },
        )
        stats = year_stats_by_year.setdefault(year, _new_progress_stats())
        _add_stat(stats, "months")
        _add_stat(stats, "fetched")
        _add_stat(stats, "rows", result.rows)
    for year, stats in sorted(year_stats_by_year.items()):
        _log_year_stats("J-Quants silver", year, stats)


def build_spy_compat_late_session_feature_records(
    minute_records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    vendor_lag_minutes: int,
) -> list[dict[str, object]]:  # pragma: no cover - vendor-derived silver cache path
    """Project generic SPY minute records into the stable canonical spy_* columns."""
    generic = build_massive_late_session_feature_records(
        minute_records,
        calendar_records=calendar_records,
        vendor_lag_minutes=vendor_lag_minutes,
        ticker="SPY",
    )
    records = []
    for row in generic:
        records.append(
            {
                "bar_date_et": row.get("bar_date_et"),
                "bar_end_ts_utc": row.get("bar_end_ts_utc"),
                "close": row.get("close"),
                "is_us_regular_session": row.get("is_us_regular_session"),
                "spy_late_30m_return": row.get("late_30m_return"),
                "spy_late_60m_return": row.get("late_60m_return"),
                "spy_late_session_range": row.get("late_session_range"),
                "spy_late_volume_surge": row.get("late_volume_surge"),
                "spy_final_window_momentum": row.get("final_window_momentum"),
                "late_60m_volume_for_surge": row.get("late_60m_volume_for_surge"),
                "regular_session_volume_for_surge": row.get("regular_session_volume_for_surge"),
                "feature_available_ts_utc": row.get("feature_available_ts_utc"),
                "official_close_ts_utc": row.get("official_close_ts_utc"),
                "selected_close_bar_end_ts_utc": row.get("selected_close_bar_end_ts_utc"),
                "vendor_lag_seconds": row.get("vendor_lag_seconds"),
            }
        )
    return records


def build_massive_late_session_feature_records(
    minute_records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    vendor_lag_minutes: int,
    ticker: str | None = None,
) -> list[dict[str, object]]:  # pragma: no cover - vendor-derived silver cache path
    close_by_date = {
        str(row["calendar_date"]): _coerce_datetime(row.get("us_close_ts_utc"))
        for row in calendar_records
        if row.get("us_close_ts_utc") is not None
    }
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in minute_records:
        if row.get("is_us_regular_session") is True:
            row_ticker = str(ticker or row.get("ticker") or "SPY").upper()
            grouped.setdefault((row_ticker, str(row["bar_date_et"])), []).append(row)
    records: list[dict[str, object]] = []
    for ticker_key, date_key in sorted(grouped):
        rows = sorted(grouped[(ticker_key, date_key)], key=lambda row: str(row["bar_end_ts_utc"]))
        official_close = close_by_date.get(date_key) or _coerce_datetime(
            rows[-1].get("bar_end_ts_utc")
        )
        if official_close is None:
            continue
        eligible = [
            row
            for row in rows
            if (_coerce_datetime(row.get("bar_end_ts_utc")) or datetime.max.replace(tzinfo=UTC))
            <= official_close
        ]
        if not eligible:
            continue
        selected_close = eligible[-1]
        selected_close_ts = _coerce_datetime(selected_close.get("bar_end_ts_utc"))
        selected_close_value = _optional_float(selected_close.get("close"))
        hour_rows = _window_rows(eligible, official_close=official_close, minutes=60)
        half_hour_rows = _window_rows(eligible, official_close=official_close, minutes=30)
        final_rows = _window_rows(eligible, official_close=official_close, minutes=15)
        session_volume = float(sum(_optional_float(row.get("volume")) or 0.0 for row in eligible))
        late_volume = float(sum(_optional_float(row.get("volume")) or 0.0 for row in hour_rows))
        feature_available = official_close + timedelta(minutes=vendor_lag_minutes)
        late_returns = _rows_log_returns(hour_rows)
        records.append(
            {
                "ticker": ticker_key,
                "safe_ticker": _safe_name(ticker_key),
                "bar_date_et": date_key,
                "bar_end_ts_utc": selected_close_ts,
                "close": selected_close_value,
                "is_us_regular_session": True,
                "late_30m_return": _rows_return(half_hour_rows),
                "late_60m_return": _rows_return(hour_rows),
                "late_60m_realized_var": _realized_var(late_returns),
                "late_60m_up_semivar": _semivar(late_returns, positive=True),
                "late_60m_down_semivar": _semivar(late_returns, positive=False),
                "late_60m_skew": _sample_skew(late_returns),
                "late_60m_excess_kurtosis": _sample_excess_kurtosis(late_returns),
                "late_session_range": _rows_range(hour_rows),
                "late_volume_surge": None,
                "late_volume_zscore_20": None,
                "late_volume_percentile_20": None,
                "final_window_momentum": _rows_return(final_rows),
                "late_60m_volume_for_surge": late_volume,
                "regular_session_volume_for_surge": session_volume,
                "feature_available_ts_utc": feature_available,
                "official_close_ts_utc": official_close,
                "selected_close_bar_end_ts_utc": selected_close_ts,
                "vendor_lag_seconds": vendor_lag_minutes * 60,
            }
        )
    return _records_with_recomputed_minute_volume_features(records)


def _records_with_recomputed_spy_compat_late_volume_surge(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Recompute canonical SPY compat volume surge over the full date sequence.

    The silver cache is partitioned monthly, but the 20-session baseline is a
    time-series feature. Recomputing after all cache chunks are loaded prevents
    each month boundary from manufacturing a missing first-day surge value.
    """
    rolling_late_volume: list[float] = []
    output: list[dict[str, object]] = []
    for row in sorted(records, key=lambda item: str(item.get("bar_date_et") or "")):
        enriched = dict(row)
        late_volume = _optional_float(enriched.get("late_60m_volume_for_surge"))
        if late_volume is None:
            output.append(enriched)
            continue
        rolling_mean_volume = (
            float(np.mean(rolling_late_volume[-20:])) if rolling_late_volume else None
        )
        enriched["spy_late_volume_surge"] = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else late_volume / rolling_mean_volume
        )
        rolling_late_volume.append(late_volume)
        output.append(enriched)
    return output


def _records_with_recomputed_minute_volume_features(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Recompute volume features per ticker over the full supplied date sequence."""
    baseline_window = PIPELINE_CONFIG.feature_engineering.massive_minute_volume_baseline_window
    by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_ticker.setdefault(str(row.get("ticker") or "SPY").upper(), []).append(row)
    output: list[dict[str, object]] = []
    for ticker, rows in sorted(by_ticker.items()):
        rolling_late_volume: list[float] = []
        for row in sorted(rows, key=lambda item: str(item.get("bar_date_et") or "")):
            enriched = dict(row)
            enriched["ticker"] = ticker
            enriched["safe_ticker"] = _safe_name(ticker)
            late_volume = _optional_float(enriched.get("late_60m_volume_for_surge"))
            if late_volume is None:
                output.append(enriched)
                continue
            baseline = rolling_late_volume[-baseline_window:]
            if baseline:
                rolling_mean = float(np.mean(baseline))
                rolling_std = float(np.std(baseline, ddof=1)) if len(baseline) >= 2 else None
                enriched["late_volume_surge"] = (
                    None if rolling_mean == 0.0 else late_volume / rolling_mean
                )
                enriched["late_volume_zscore_20"] = (
                    None
                    if rolling_std is None or rolling_std == 0.0
                    else (late_volume - rolling_mean) / rolling_std
                )
                enriched["late_volume_percentile_20"] = float(
                    sum(value <= late_volume for value in baseline) / len(baseline)
                )
            rolling_late_volume.append(late_volume)
            output.append(enriched)
    return sorted(
        output, key=lambda item: (str(item.get("bar_date_et") or ""), str(item.get("ticker") or ""))
    )


def _window_rows(
    rows: list[dict[str, object]],
    *,
    official_close: datetime,
    minutes: int,
) -> list[dict[str, object]]:
    start = official_close - timedelta(minutes=minutes)
    return [
        row
        for row in rows
        if (ts := _coerce_datetime(row.get("bar_end_ts_utc"))) is not None
        and start <= ts <= official_close
    ]


def _rows_return(rows: list[dict[str, object]]) -> float | None:
    closes = [
        _optional_float(row.get("close"))
        for row in rows
        if _optional_float(row.get("close")) is not None
    ]
    if len(closes) < 2:
        return None
    start = closes[0]
    end = closes[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _rows_range(rows: list[dict[str, object]]) -> float | None:
    highs = [_optional_float(row.get("high")) for row in rows]
    lows = [_optional_float(row.get("low")) for row in rows]
    return _window_range(highs, lows)


def _rows_log_returns(rows: list[dict[str, object]]) -> list[float]:
    closes = [
        value
        for row in rows
        if (value := _optional_float(row.get("close"))) is not None and value > 0
    ]
    output: list[float] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        output.append(math.log(current) - math.log(previous))
    return output


def _realized_var(returns: list[float]) -> float | None:
    if not returns:
        return None
    return float(sum(value * value for value in returns))


def _semivar(returns: list[float], *, positive: bool) -> float | None:
    if not returns:
        return None
    selected = (
        [value for value in returns if value > 0]
        if positive
        else [value for value in returns if value < 0]
    )
    if not selected:
        return 0.0
    return float(sum(value * value for value in selected))


def _sample_skew(returns: list[float]) -> float | None:
    min_periods = PIPELINE_CONFIG.feature_engineering.massive_minute_moment_min_periods
    if len(returns) < min_periods:
        return None
    values = np.asarray(returns, dtype=float)
    std = float(np.std(values, ddof=1))
    if std == 0.0:
        return None
    centered = values - float(np.mean(values))
    return float(np.mean((centered / std) ** 3))


def _sample_excess_kurtosis(returns: list[float]) -> float | None:
    min_periods = PIPELINE_CONFIG.feature_engineering.massive_minute_moment_min_periods
    if len(returns) < min_periods:
        return None
    values = np.asarray(returns, dtype=float)
    std = float(np.std(values, ddof=1))
    if std == 0.0:
        return None
    centered = values - float(np.mean(values))
    return float(np.mean((centered / std) ** 4) - 3.0)


def _jquants_bronze_row(
    row: Mapping[str, object],
    *,
    requested_date: str,
    source_endpoint: str,
    downloaded_at_utc: datetime,
) -> dict[str, object]:
    output: dict[str, object] = {
        "Date": _optional_text(row.get("Date")) or requested_date,
        "ProdCat": _optional_text(row.get("ProdCat")),
        "Code": _optional_text(row.get("Code")),
        "CM": _optional_text(row.get("CM")),
        "CCMFlag": _optional_text(row.get("CCMFlag")),
        "LTD": _optional_text(row.get("LTD")),
        "SQD": _optional_text(row.get("SQD")),
        "EmMrgnTrgDiv": _optional_text(row.get("EmMrgnTrgDiv")),
        "source_endpoint": source_endpoint,
        "requested_date": requested_date,
        "research_download_ts_utc": downloaded_at_utc,
    }
    for field in ("AO", "AH", "AL", "AC", "EO", "EH", "EL", "EC", "Settle", "Vo", "OI"):
        output[field] = _optional_float(row.get(field))
    return output
