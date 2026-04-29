# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


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
    _write_json(
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
