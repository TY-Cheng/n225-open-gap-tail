# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    atomic_write_parquet,
    cache_path,
    cast,
    date,
    datetime,
    JQUANTS_OPTIONS_BRONZE_SCHEMA,
    JQuantsV2Client,
    Mapping,
    pl,
    Settings,
    UTC,
    _add_stat,
    _log_year_stats,
    _new_progress_stats,
    _optional_float,
    _pipeline_log,
    read_verified_parquet_metadata,
)


def _fetch_jquants_nikkei_option_rows(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    run_start_utc: datetime | None = None,
) -> list[dict[str, Any]]:  # pragma: no cover - vendor path
    if not settings.jquants_nikkei225_options_enabled:
        _pipeline_log("J-Quants Nikkei 225 options disabled by runtime config")
        return []
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
        api_key=settings.read_jquants_api_key(),
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    ) as client:
        current_year: int | None = None
        year_stats = _new_progress_stats()
        for (year, month), trading_dates in sorted(dates_by_month.items()):
            if current_year is not None and year != current_year:
                _log_year_stats("J-Quants Nikkei 225 options bronze", current_year, year_stats)
                year_stats = _new_progress_stats()
            current_year = year
            _add_stat(year_stats, "months")
            _add_stat(year_stats, "trading_days", len(trading_dates))
            path = cache_path(
                bronze_root,
                dataset="jquants_nikkei225_options_daily",
                schema_version=JQUANTS_OPTIONS_BRONZE_SCHEMA.version,
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
                raw_rows = client.get_nikkei225_options_daily_bars(
                    trading_date=trading_date,
                    category=settings.jquants_nikkei225_options_category,
                    contract_flag=settings.jquants_nikkei225_options_contract_flag,
                )
                chunk_rows.extend(
                    _jquants_option_bronze_row(
                        row,
                        requested_date=trading_date,
                        source_endpoint="/derivatives/bars/daily/options/225",
                        downloaded_at_utc=run_start_utc or pull_started,
                    )
                    for row in raw_rows
                )
            result = atomic_write_parquet(
                path,
                chunk_rows,
                schema=JQUANTS_OPTIONS_BRONZE_SCHEMA,
                metadata={
                    "source": "jquants",
                    "endpoint": "/derivatives/bars/daily/options/225",
                    "product_category": settings.jquants_nikkei225_options_category,
                    "contract_flag": settings.jquants_nikkei225_options_contract_flag,
                    "requested_dates": trading_dates,
                    "pull_started_at_utc": pull_started.isoformat(),
                    "pull_completed_at_utc": datetime.now(UTC).isoformat(),
                },
            )
            _add_stat(year_stats, "fetched")
            _add_stat(year_stats, "rows", result.rows)
            rows.extend(_read_parquet_records(path))
        if current_year is not None:
            _log_year_stats("J-Quants Nikkei 225 options bronze", current_year, year_stats)
    return rows


def _jquants_option_bronze_row(
    row: Mapping[str, object],
    *,
    requested_date: str,
    source_endpoint: str,
    downloaded_at_utc: datetime,
) -> dict[str, object]:  # pragma: no cover - vendor cache path
    output: dict[str, object] = {
        "Date": _optional_text(row.get("Date")) or requested_date,
        "Code": _optional_text(row.get("Code")),
        "CM": _optional_text(row.get("CM") or row.get("ContractMonth")),
        "EmMrgnTrgDiv": _optional_text(
            row.get("EmMrgnTrgDiv") or row.get("EmergencyMarginTriggerDivision")
        ),
        "PCDiv": _optional_text(row.get("PCDiv") or row.get("PutCallDivision")),
        "LTD": _optional_text(row.get("LTD") or row.get("LastTradingDay")),
        "SQD": _optional_text(row.get("SQD") or row.get("SpecialQuotationDay")),
        "source_endpoint": source_endpoint,
        "requested_date": requested_date,
        "research_download_ts_utc": downloaded_at_utc,
    }
    for field in (
        "O",
        "H",
        "L",
        "C",
        "EO",
        "EH",
        "EL",
        "EC",
        "AO",
        "AH",
        "AL",
        "AC",
        "Vo",
        "OI",
        "Va",
        "Strike",
        "VoOA",
        "Settle",
        "Theo",
        "BaseVol",
        "UnderPx",
        "IV",
        "IR",
    ):
        output[field] = _optional_float(row.get(field) or _jquants_option_long_field(row, field))
    return output


def _jquants_option_long_field(
    row: Mapping[str, object], compact_field: str
) -> object:  # pragma: no cover - vendor fallback
    return {
        "O": row.get("WholeDayOpen"),
        "H": row.get("WholeDayHigh"),
        "L": row.get("WholeDayLow"),
        "C": row.get("WholeDayClose"),
        "EO": row.get("NightSessionOpen"),
        "EH": row.get("NightSessionHigh"),
        "EL": row.get("NightSessionLow"),
        "EC": row.get("NightSessionClose"),
        "AO": row.get("DaySessionOpen"),
        "AH": row.get("DaySessionHigh"),
        "AL": row.get("DaySessionLow"),
        "AC": row.get("DaySessionClose"),
        "Vo": row.get("Volume"),
        "OI": row.get("OpenInterest"),
        "Va": row.get("TurnoverValue"),
        "Strike": row.get("StrikePrice"),
        "VoOA": row.get("Volume(OnlyAuction)"),
        "Settle": row.get("SettlementPrice"),
        "Theo": row.get("TheoreticalPrice"),
        "BaseVol": row.get("BaseVolatility"),
        "UnderPx": row.get("UnderlyingPrice"),
        "IV": row.get("ImpliedVolatility"),
        "IR": row.get("InterestRate"),
    }.get(compact_field)


def _optional_text(value: object) -> str | None:  # pragma: no cover - vendor cache path
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_parquet_records(path: object) -> list[dict[str, Any]]:  # pragma: no cover
    return pl.read_parquet(path).to_dicts()


def _cache_covers_dates(path: object, required_dates: list[str]) -> bool:  # pragma: no cover
    metadata = read_verified_parquet_metadata(path)
    raw_dates = metadata.get("requested_dates")
    if not isinstance(raw_dates, list):
        return False
    available = {str(value) for value in raw_dates}
    return set(required_dates).issubset(available)


def _filter_records_by_dates(
    records: list[dict[str, object]],
    *,
    allowed_dates: list[str],
    date_fields: tuple[str, ...],
) -> list[dict[str, object]]:  # pragma: no cover
    allowed = set(allowed_dates)
    return [
        row
        for row in records
        if (date_value := _first_row_date_value(row, date_fields)) is not None
        and date_value in allowed
    ]


def _first_row_date_value(
    row: Mapping[str, object], date_fields: tuple[str, ...]
) -> str | None:  # pragma: no cover - vendor cache path
    for field in date_fields:
        raw = row.get(field)
        if raw is not None:
            return str(raw)[:10]
    return None
