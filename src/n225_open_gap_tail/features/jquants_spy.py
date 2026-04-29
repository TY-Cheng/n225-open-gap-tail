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
            ("day_session_close", "invalid_day_session_close"),
            ("night_session_close", "invalid_night_session_close"),
            ("settlement_price", "invalid_settlement_price"),
        ):
            value = _optional_float(row.get(source_name))
            output[flag_name] = value is None or value <= 0
        output["day_session_ohlc_violation"] = False
        output["night_session_ohlc_violation"] = False
        output["night_session_close_ts_utc"] = row.get("night_close_ts_utc")
        flagged.append(output)
    return flagged


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


def build_spy_late_session_feature_records(
    minute_records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    vendor_lag_minutes: int,
) -> list[dict[str, object]]:  # pragma: no cover - vendor-derived silver cache path
    close_by_date = {
        str(row["calendar_date"]): _coerce_datetime(row.get("us_close_ts_utc"))
        for row in calendar_records
        if row.get("us_close_ts_utc") is not None
    }
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in minute_records:
        if row.get("is_us_regular_session") is True:
            grouped.setdefault(str(row["bar_date_et"]), []).append(row)
    records: list[dict[str, object]] = []
    for date_key in sorted(grouped):
        rows = sorted(grouped[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
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
        records.append(
            {
                "bar_date_et": date_key,
                "bar_end_ts_utc": selected_close_ts,
                "close": selected_close_value,
                "is_us_regular_session": True,
                "spy_late_30m_return": _rows_return(half_hour_rows),
                "spy_late_60m_return": _rows_return(hour_rows),
                "spy_late_session_range": _rows_range(hour_rows),
                "spy_late_volume_surge": None,
                "spy_final_window_momentum": _rows_return(final_rows),
                "late_60m_volume_for_surge": late_volume,
                "regular_session_volume_for_surge": session_volume,
                "feature_available_ts_utc": feature_available,
                "official_close_ts_utc": official_close,
                "selected_close_bar_end_ts_utc": selected_close_ts,
                "vendor_lag_seconds": vendor_lag_minutes * 60,
            }
        )
    return _records_with_recomputed_spy_late_volume_surge(records)


def _records_with_recomputed_spy_late_volume_surge(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Recompute SPY volume surge over the full supplied date sequence.

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
        "source_endpoint": source_endpoint,
        "requested_date": requested_date,
        "research_download_ts_utc": downloaded_at_utc,
    }
    for field in ("AO", "AH", "AL", "AC", "EO", "EH", "EL", "EC", "Settle", "Vo", "OI"):
        output[field] = _optional_float(row.get(field))
    return output
