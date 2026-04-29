# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    atomic_write_parquet,
    cache_path,
    cast,
    CboeClient,
    classify_vendor_error,
    cleanup_transient_unavailable_markers,
    date,
    datetime,
    FETCH_FRED_SERIES_FOR_PIPELINE,
    FETCH_MASSIVE_TICKERS_FOR_PIPELINE,
    FRED_CACHE_SCHEMA,
    FRED_CACHE_TTL_DAYS,
    FredClient,
    is_fred_cache_fresh_at_run_start,
    JQUANTS_BRONZE_SCHEMA,
    JQuantsV2Client,
    Mapping,
    MassiveClient,
    math,
    normalize_aggregate_bars,
    normalize_cboe_vol_index_rows,
    normalize_fred_rows,
    np,
    Path,
    PERSISTENT_UNAVAILABLE_ERRORS,
    PIPELINE_CONFIG,
    pl,
    read_json,
    read_verified_parquet_metadata,
    Settings,
    SPY_MINUTE_FEATURE_SCHEMA,
    timedelta,
    UTC,
    VendorErrorClass,
    write_json_atomic,
    _add_stat,
    _log_year_stats,
    _new_progress_stats,
    _optional_float,
    _pipeline_log,
)


def _safe_name(value: str) -> str:  # pragma: no cover - vendor cache path
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _optional_text(value: object) -> str | None:  # pragma: no cover - vendor cache path
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:  # pragma: no cover
    current = date.fromisoformat(start).replace(day=1)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    while current <= end_date:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        chunk_start = max(date.fromisoformat(start), current)
        chunk_end = min(end_date, next_month - timedelta(days=1))
        chunks.append((chunk_start.isoformat(), chunk_end.isoformat()))
        current = next_month
    return chunks


def _coerce_datetime(value: object) -> datetime | None:  # pragma: no cover - vendor cache path
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _window_return(values: list[float], window: int) -> float | None:  # pragma: no cover
    if len(values) < window or len(values) < 2:
        return None
    start = values[-window]
    end = values[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _window_range(  # pragma: no cover - vendor cache path
    highs: list[float | None], lows: list[float | None]
) -> float | None:
    valid_highs = [value for value in highs if value is not None and value > 0]
    valid_lows = [value for value in lows if value is not None and value > 0]
    if not valid_highs or not valid_lows:
        return None
    high = max(valid_highs)
    low = min(valid_lows)
    if low <= 0:
        return None
    return math.log(high) - math.log(low)


def _jquants_bronze_row(
    row: Mapping[str, object],
    *,
    requested_date: str,
    source_endpoint: str,
    downloaded_at_utc: datetime,
) -> dict[str, object]:  # pragma: no cover - vendor cache path
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


def build_spy_late_session_feature_records(
    minute_records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    vendor_lag_minutes: int,
) -> list[dict[str, object]]:  # pragma: no cover - vendor cache path
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
) -> list[dict[str, object]]:  # pragma: no cover - vendor cache path
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
) -> list[dict[str, object]]:  # pragma: no cover - vendor cache path
    start = official_close - timedelta(minutes=minutes)
    return [
        row
        for row in rows
        if (ts := _coerce_datetime(row.get("bar_end_ts_utc"))) is not None
        and start <= ts <= official_close
    ]


def _rows_return(rows: list[dict[str, object]]) -> float | None:  # pragma: no cover
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


def _rows_range(rows: list[dict[str, object]]) -> float | None:  # pragma: no cover
    highs = [_optional_float(row.get("high")) for row in rows]
    lows = [_optional_float(row.get("low")) for row in rows]
    return _window_range(highs, lows)


def _payload_results(payload: Mapping[str, object]) -> list[dict[str, Any]]:
    raw = payload.get("results", [])
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], item) for item in raw if isinstance(item, dict)]


def _read_parquet_records(path: Path) -> list[dict[str, Any]]:
    return pl.read_parquet(path).to_dicts()


def _cache_covers_dates(path: Path, required_dates: list[str]) -> bool:
    metadata = read_verified_parquet_metadata(path)
    raw_dates = metadata.get("requested_dates")
    if not isinstance(raw_dates, list):
        return False
    available = {str(value) for value in raw_dates}
    return set(required_dates).issubset(available)


def _cache_covers_range(path: Path, start: str, end: str) -> bool:
    metadata = read_verified_parquet_metadata(path)
    return _metadata_covers_range(metadata, start, end)


def _metadata_covers_range(metadata: Mapping[str, object], start: str, end: str) -> bool:
    raw_range = metadata.get("requested_range")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        return False
    cached_start, cached_end = str(raw_range[0]), str(raw_range[1])
    return cached_start <= start and cached_end >= end


def _filter_records_by_range(
    records: list[dict[str, object]],
    *,
    start: str,
    end: str,
    date_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for row in records:
        date_value = _first_row_date_value(row, date_fields)
        if date_value is not None and start <= date_value <= end:
            filtered.append(row)
    return filtered


def _filter_records_by_dates(
    records: list[dict[str, object]],
    *,
    allowed_dates: list[str],
    date_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    allowed = set(allowed_dates)
    return [
        row
        for row in records
        if (date_value := _first_row_date_value(row, date_fields)) is not None
        and date_value in allowed
    ]


def _first_row_date_value(row: Mapping[str, object], date_fields: tuple[str, ...]) -> str | None:
    for field in date_fields:
        raw = row.get(field)
        if raw is not None:
            return str(raw)[:10]
    return None


def _unavailable_marker_covers(path: Path, start: str, end: str) -> bool:
    return path.exists() and _metadata_covers_range(read_json(path), start, end)


def _write_unavailable_marker(
    path: Path,
    *,
    source: str,
    error_class: VendorErrorClass,
    http_status: int | None,
    requested_range: list[str],
) -> None:
    if error_class.value not in PERSISTENT_UNAVAILABLE_ERRORS:
        return
    write_json_atomic(
        path,
        {
            "source": source,
            "error_class": error_class.value,
            "http_status": http_status,
            "requested_range": requested_range,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "persistent_until_force_or_entitlement_refresh": error_class
            is VendorErrorClass.UNAVAILABLE_ENTITLEMENT,
        },
    )


def _fetch_jquants_futures_rows(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    run_start_utc: datetime | None = None,
) -> list[dict[str, Any]]:  # pragma: no cover - vendor path
    rows: list[dict[str, Any]] = []
    jpx_dates = [
        str(row["calendar_date"])
        for row in calendar_records
        if start <= str(row["calendar_date"]) <= end and row.get("is_jpx_trading_day") is True
    ]
    dates_by_month: dict[tuple[int, int], list[str]] = {}
    for trading_date in jpx_dates:
        parsed = date.fromisoformat(trading_date)
        dates_by_month.setdefault((parsed.year, parsed.month), []).append(trading_date)
    bronze_root = settings.data_dir / "bronze"
    with JQuantsV2Client(
        api_key=settings.jquants_api_key,
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    ) as client:
        current_year: int | None = None
        year_stats = _new_progress_stats()
        for (year, month), trading_dates in sorted(dates_by_month.items()):
            if current_year is not None and year != current_year:
                _log_year_stats("J-Quants bronze", current_year, year_stats)
                year_stats = _new_progress_stats()
            current_year = year
            _add_stat(year_stats, "months")
            _add_stat(year_stats, "trading_days", len(trading_dates))
            path = cache_path(
                bronze_root,
                dataset="jquants_futures_daily",
                schema_version=JQUANTS_BRONZE_SCHEMA.version,
                year=year,
                month=month,
            )
            if path.exists() and _cache_covers_dates(path, trading_dates):
                cached_records = _filter_records_by_dates(
                    _read_parquet_records(path),
                    allowed_dates=trading_dates,
                    date_fields=("requested_date", "Date"),
                )
                rows.extend(cached_records)
                _add_stat(year_stats, "cache_hits")
                _add_stat(year_stats, "rows", len(cached_records))
                continue
            chunk_rows: list[dict[str, object]] = []
            pull_started = datetime.now(UTC)
            for trading_date in trading_dates:
                raw_rows = client.get_futures_daily_bars(trading_date=trading_date)
                chunk_rows.extend(
                    _jquants_bronze_row(
                        row,
                        requested_date=trading_date,
                        source_endpoint="/derivatives/bars/daily/futures",
                        downloaded_at_utc=run_start_utc or pull_started,
                    )
                    for row in raw_rows
                )
            result = atomic_write_parquet(
                path,
                chunk_rows,
                schema=JQUANTS_BRONZE_SCHEMA,
                metadata={
                    "source": "jquants",
                    "endpoint": "/derivatives/bars/daily/futures",
                    "requested_dates": trading_dates,
                    "pull_started_at_utc": pull_started.isoformat(),
                    "pull_completed_at_utc": datetime.now(UTC).isoformat(),
                },
            )
            _add_stat(year_stats, "fetched")
            _add_stat(year_stats, "rows", result.rows)
            rows.extend(_read_parquet_records(path))
        if current_year is not None:
            _log_year_stats("J-Quants bronze", current_year, year_stats)
    return rows


def _fetch_massive_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
    calendar_records: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:  # pragma: no cover - vendor path
    daily_records: list[dict[str, object]] = []
    spy_feature_records: list[dict[str, object]] = []
    bronze_root = settings.data_dir / "bronze"
    silver_root = settings.data_dir / "silver"
    with MassiveClient(
        api_key=settings.massive_api_key,
        base_url=settings.massive_base_url,
        timeout_seconds=settings.massive_request_timeout_seconds,
        min_request_interval_seconds=settings.massive_min_request_interval_seconds,
        max_retries=settings.massive_max_retries,
        rate_limit_backoff_seconds=settings.massive_rate_limit_backoff_seconds,
    ) as client:
        chunks_by_year: dict[int, list[tuple[str, str]]] = {}
        for chunk_start, chunk_end in _month_chunks(start=start, end=end):
            chunks_by_year.setdefault(date.fromisoformat(chunk_start).year, []).append(
                (chunk_start, chunk_end)
            )

        for year, year_chunks in sorted(chunks_by_year.items()):
            year_stats = _new_progress_stats()
            for ticker in FETCH_MASSIVE_TICKERS_FOR_PIPELINE:
                safe_ticker = _safe_name(ticker)
                for chunk_start, chunk_end in year_chunks:
                    chunk_date = date.fromisoformat(chunk_start)
                    _add_stat(year_stats, "months")
                    path = cache_path(
                        bronze_root,
                        dataset="massive_daily",
                        schema_version=1,
                        year=chunk_date.year,
                        month=chunk_date.month,
                        extra_partitions={"ticker": safe_ticker},
                    )
                    unavailable_path = path.with_suffix(".unavailable.json")
                    if path.exists() and _cache_covers_range(path, chunk_start, chunk_end):
                        cached_records = _filter_records_by_range(
                            _read_parquet_records(path),
                            start=chunk_start,
                            end=chunk_end,
                            date_fields=("bar_date_et", "observation_date"),
                        )
                        daily_records.extend(cached_records)
                        _add_stat(year_stats, "cache_hits")
                        _add_stat(year_stats, "rows", len(cached_records))
                        continue
                    if _unavailable_marker_covers(unavailable_path, chunk_start, chunk_end):
                        _add_stat(year_stats, "unavailable")
                        continue
                    payload = client.fetch_aggregate_bars(
                        name=f"{ticker}_day",
                        ticker=ticker,
                        multiplier=1,
                        timespan="day",
                        start=chunk_start,
                        end=chunk_end,
                        raise_for_status=False,
                    )
                    error_class = classify_vendor_error(
                        status_code=payload.http_status,
                        message=str(
                            payload.payload.get("message") or payload.payload.get("error") or ""
                        ),
                        row_count=payload.row_count,
                    )
                    if error_class is not VendorErrorClass.OK:
                        _write_unavailable_marker(
                            unavailable_path,
                            source="massive",
                            error_class=error_class,
                            http_status=payload.http_status,
                            requested_range=[chunk_start, chunk_end],
                        )
                        _add_stat(year_stats, "unavailable")
                        continue
                    normalized = normalize_aggregate_bars(
                        ticker=ticker,
                        rows=_payload_results(payload.payload),
                        multiplier=1,
                        timespan="day",
                        research_download_ts_utc=downloaded_at_utc,
                        us_timezone=settings.project_timezone_us,
                        regular_session_start_et=settings.massive_regular_session_start_et,
                        regular_session_end_et=settings.massive_regular_session_end_et,
                    )
                    result = atomic_write_parquet(
                        path,
                        normalized,
                        metadata={
                            "source": "massive",
                            "ticker": ticker,
                            "timespan": "day",
                            "requested_range": [chunk_start, chunk_end],
                            "http_status": payload.http_status,
                        },
                    )
                    _add_stat(year_stats, "fetched")
                    _add_stat(year_stats, "rows", result.rows)
                    daily_records.extend(normalized)
            _log_year_stats("Massive daily", year, year_stats)

        for year, year_chunks in sorted(chunks_by_year.items()):
            year_stats = _new_progress_stats()
            for chunk_start, chunk_end in year_chunks:
                chunk_date = date.fromisoformat(chunk_start)
                _add_stat(year_stats, "months")
                feature_path = cache_path(
                    silver_root,
                    dataset="massive_spy_minute_features",
                    schema_version=SPY_MINUTE_FEATURE_SCHEMA.version,
                    year=chunk_date.year,
                    month=chunk_date.month,
                    extra_partitions={"ticker": _safe_name(settings.massive_minute_ticker)},
                )
                unavailable_path = feature_path.with_suffix(".unavailable.json")
                if feature_path.exists() and _cache_covers_range(
                    feature_path, chunk_start, chunk_end
                ):
                    cached_records = _filter_records_by_range(
                        _read_parquet_records(feature_path),
                        start=chunk_start,
                        end=chunk_end,
                        date_fields=("bar_date_et", "observation_date"),
                    )
                    spy_feature_records.extend(cached_records)
                    _add_stat(year_stats, "cache_hits")
                    _add_stat(year_stats, "rows", len(cached_records))
                    continue
                if _unavailable_marker_covers(unavailable_path, chunk_start, chunk_end):
                    _add_stat(year_stats, "unavailable")
                    continue
                payload = client.fetch_aggregate_bars(
                    name=f"{settings.massive_minute_ticker}_minute",
                    ticker=settings.massive_minute_ticker,
                    multiplier=1,
                    timespan="minute",
                    start=chunk_start,
                    end=chunk_end,
                    raise_for_status=False,
                )
                error_class = classify_vendor_error(
                    status_code=payload.http_status,
                    message=str(
                        payload.payload.get("message") or payload.payload.get("error") or ""
                    ),
                    row_count=payload.row_count,
                )
                if error_class is not VendorErrorClass.OK:
                    _write_unavailable_marker(
                        unavailable_path,
                        source="massive",
                        error_class=error_class,
                        http_status=payload.http_status,
                        requested_range=[chunk_start, chunk_end],
                    )
                    _add_stat(year_stats, "unavailable")
                    continue
                minute_records = normalize_aggregate_bars(
                    ticker=settings.massive_minute_ticker,
                    rows=_payload_results(payload.payload),
                    multiplier=1,
                    timespan="minute",
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    regular_session_start_et=settings.massive_regular_session_start_et,
                    regular_session_end_et=settings.massive_regular_session_end_et,
                )
                features = build_spy_late_session_feature_records(
                    minute_records,
                    calendar_records=calendar_records or [],
                    vendor_lag_minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes,
                )
                result = atomic_write_parquet(
                    feature_path,
                    features,
                    schema=SPY_MINUTE_FEATURE_SCHEMA,
                    metadata={
                        "source": "massive",
                        "ticker": settings.massive_minute_ticker,
                        "timespan": "minute_derived",
                        "requested_range": [chunk_start, chunk_end],
                        "http_status": payload.http_status,
                    },
                )
                _add_stat(year_stats, "fetched")
                _add_stat(year_stats, "rows", result.rows)
                spy_feature_records.extend(features)
            _log_year_stats("SPY minute-derived", year, year_stats)
    return daily_records, spy_feature_records


def _fetch_cboe_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    symbols = settings.cboe_vol_index_symbol_list()
    if not symbols:
        return []
    safe_symbols = "_".join(_safe_name(symbol) for symbol in symbols)
    bronze_path = (
        settings.data_dir
        / "bronze"
        / "cboe_vol_indices"
        / "schema_version=1"
        / f"symbols={safe_symbols}"
        / "payload.json"
    )
    silver_path = (
        settings.data_dir
        / "silver"
        / "cboe_vol_indices"
        / "schema_version=1"
        / f"symbols={safe_symbols}"
        / "daily.parquet"
    )
    if silver_path.exists() and _cache_covers_range(silver_path, start, end):
        _pipeline_log(f"Cboe volatility cache hit symbols={','.join(symbols)}")
        return _filter_records_by_range(
            _read_parquet_records(silver_path),
            start=start,
            end=end,
            date_fields=("observation_date",),
        )

    with CboeClient(
        base_url=settings.cboe_base_url,
        timeout_seconds=settings.cboe_request_timeout_seconds,
    ) as client:
        payloads = [client.fetch_vol_index_csv(symbol) for symbol in symbols]

    records: list[dict[str, object]] = []
    for payload in payloads:
        records.extend(
            row
            for row in normalize_cboe_vol_index_rows(
                symbol=payload.symbol,
                rows=payload.rows,
                raw_header=payload.raw_header,
                research_download_ts_utc=downloaded_at_utc,
                us_timezone=settings.project_timezone_us,
            )
            if start <= str(row["observation_date"]) <= end
        )
    write_json_atomic(
        bronze_path,
        {
            "source": "cboe",
            "base_url": settings.cboe_base_url,
            "downloaded_at_utc": downloaded_at_utc.isoformat(),
            "requested_range": [start, end],
            "symbols": [
                {
                    "symbol": payload.symbol,
                    "path": payload.path,
                    "http_status": payload.http_status,
                    "raw_header": payload.raw_header,
                    "row_count": len(payload.rows),
                    "raw_csv": payload.raw_csv,
                }
                for payload in payloads
            ],
            "note": "Raw headers are retained because Cboe historical CSV headers drift.",
        },
    )
    atomic_write_parquet(
        silver_path,
        records,
        metadata={
            "source": "cboe",
            "symbols": list(symbols),
            "requested_range": [start, end],
            "raw_headers": [payload.raw_header for payload in payloads],
        },
    )
    _pipeline_log(f"Cboe volatility fetched symbols={','.join(symbols)} rows={len(records)}")
    return records


def _fetch_fred_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
    run_start_utc: datetime | None = None,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    records: list[dict[str, object]] = []
    cache_root = settings.data_dir / "bronze"
    ttl_decision_ts = run_start_utc or downloaded_at_utc
    with FredClient(
        base_url=settings.fred_base_url,
        timeout_seconds=settings.fred_request_timeout_seconds,
    ) as client:
        for series_id in FETCH_FRED_SERIES_FOR_PIPELINE:
            _pipeline_log(f"FRED series start: {series_id}")
            path = cache_path(
                cache_root,
                dataset="fred_daily",
                schema_version=FRED_CACHE_SCHEMA.version,
                extra_partitions={"series": _safe_name(series_id)},
            )
            metadata = read_verified_parquet_metadata(path)
            if (
                path.exists()
                and is_fred_cache_fresh_at_run_start(
                    metadata,
                    run_start_utc=ttl_decision_ts,
                    ttl_days=FRED_CACHE_TTL_DAYS,
                )
                and _metadata_covers_range(metadata, start, end)
            ):
                records.extend(
                    _filter_records_by_range(
                        _read_parquet_records(path),
                        start=start,
                        end=end,
                        date_fields=("observation_date",),
                    )
                )
                _pipeline_log(f"FRED cache hit {series_id}")
                continue
            ttl_status = "missing"
            if path.exists():
                ttl_status = (
                    "stale_at_run_start"
                    if not is_fred_cache_fresh_at_run_start(
                        metadata,
                        run_start_utc=ttl_decision_ts,
                        ttl_days=FRED_CACHE_TTL_DAYS,
                    )
                    else "range_miss"
                )
            _pipeline_log(f"FRED fetching {series_id}: {ttl_status}")
            payload = client.fetch_series_csv(series_id)
            normalized = [
                {**row, "vintage_safe": False}
                for row in normalize_fred_rows(
                    series_id=series_id,
                    rows=payload.rows,
                    start=start,
                    end=end,
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    availability_lag_us_business_days=(
                        PIPELINE_CONFIG.leakage_policy.fred_availability_lag_us_business_days
                    ),
                )
            ]
            result = atomic_write_parquet(
                path,
                normalized,
                schema=FRED_CACHE_SCHEMA,
                metadata={
                    "source": "fred",
                    "series_id": series_id,
                    "requested_range": [start, end],
                    "pull_completed_at_utc": downloaded_at_utc.isoformat(),
                    "ttl_decision_ts_utc": ttl_decision_ts.isoformat(),
                    "ttl_days": FRED_CACHE_TTL_DAYS,
                    "ttl_status": "refreshed_at_run_start",
                    "vintage_safe": False,
                    "revision_risk_label": "current_historical_revisions",
                },
            )
            _pipeline_log(f"FRED wrote {series_id}: {result.rows} rows")
            records.extend(normalized)
    return records
