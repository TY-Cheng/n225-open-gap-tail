from __future__ import annotations

import csv
import gzip
from datetime import date, datetime

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.config.runtime import (
    MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
    MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
    _pipeline_log,
)
from n225_open_gap_tail.data_lake.cache_metadata import _cache_covers_dates
from n225_open_gap_tail.data_lake.cache_ops import (
    _filter_records_by_dates,
    _read_parquet_records,
    _safe_name,
)
from n225_open_gap_tail.data_lake.io import (
    MASSIVE_OPTIONS_DAY_AGGS_FILTERED_SCHEMA,
    atomic_write_parquet,
    cache_path,
)
from n225_open_gap_tail.sources.massive_flatfiles import (
    build_massive_flatfiles_s3_client,
    download_massive_options_day_aggs_file,
    normalize_massive_options_day_agg_rows,
)


def fetch_massive_options_day_agg_rows(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    downloaded_at_utc: datetime,
    force_refresh: bool = False,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    if not (
        settings.massive_options_historical_enabled
        and settings.massive_options_flat_files_enabled
        and settings.massive_flat_file_key_file
    ):
        return []

    underlyings = massive_options_primary_underlyings(settings)
    us_dates = [
        str(row["calendar_date"])
        for row in calendar_records
        if start <= str(row["calendar_date"]) <= end and row.get("is_us_trading_day") is True
    ]
    if not us_dates:
        return []
    client = build_massive_flatfiles_s3_client(settings=settings)
    safe_underlyings = "_".join(_safe_name(underlying) for underlying in underlyings)
    bronze_root = settings.bronze_data_dir / "massive_options_day_aggs" / "schema_version=1"
    rows: list[dict[str, object]] = []
    dates_by_month: dict[tuple[int, int], list[str]] = {}
    for day in us_dates:
        parsed = date.fromisoformat(day)
        dates_by_month.setdefault((parsed.year, parsed.month), []).append(day)

    for (year, month), month_dates in sorted(dates_by_month.items()):
        path = cache_path(
            settings.silver_data_dir,
            dataset="massive_options_day_aggs_filtered",
            schema_version=MASSIVE_OPTIONS_DAY_AGGS_FILTERED_SCHEMA.version,
            year=year,
            month=month,
            extra_partitions={"underlyings": safe_underlyings},
        )
        if not force_refresh and path.exists() and _cache_covers_dates(path, month_dates):
            cached = _filter_records_by_dates(
                _read_parquet_records(path),
                allowed_dates=month_dates,
                date_fields=("bar_date_et",),
            )
            rows.extend(cached)
            _pipeline_log(
                f"Massive options day-aggs cache hit {year}-{month:02d} rows={len(cached)}"
            )
            continue

        month_rows: list[dict[str, object]] = []
        completed_dates: list[str] = []
        failed_dates: list[str] = []
        for day in month_dates:
            gz_path = bronze_root / f"year={year:04d}" / f"month={month:02d}" / f"{day}.csv.gz"
            try:
                download_massive_options_day_aggs_file(
                    client=client,
                    destination=gz_path,
                    day=day,
                )
            except Exception as exc:
                _pipeline_log(
                    "Massive options day-aggs unavailable "
                    f"date={day} error={type(exc).__name__}: {str(exc)[:160]}"
                )
                failed_dates.append(day)
                continue
            with gzip.open(gz_path, mode="rt", encoding="utf-8", newline="") as handle:
                raw_rows = list(csv.DictReader(handle))
            month_rows.extend(
                normalize_massive_options_day_agg_rows(
                    raw_rows,
                    bar_date_et=day,
                    underlyings=underlyings,
                    downloaded_at_utc=downloaded_at_utc,
                )
            )
            completed_dates.append(day)
        result = atomic_write_parquet(
            path,
            month_rows,
            schema=MASSIVE_OPTIONS_DAY_AGGS_FILTERED_SCHEMA,
            metadata={
                "source": "massive_flatfiles",
                "dataset": "us_options_opra/day_aggs_v1",
                "requested_dates": month_dates,
                "completed_dates": completed_dates,
                "failed_dates": failed_dates,
                "underlyings": list(underlyings),
                "iv_greeks_oi_source": "not_direct_fields_day_aggs_price_volume_only",
            },
        )
        _pipeline_log(f"Massive options day-aggs filtered {year}-{month:02d} rows={result.rows}")
        rows.extend(month_rows)
    return rows


def massive_options_primary_underlyings(settings: Settings) -> tuple[str, ...]:
    configured = settings.massive_options_underlying_list()
    if configured:
        return tuple(dict.fromkeys(underlying.upper() for underlying in configured))
    return tuple(
        dict.fromkeys(
            (
                *MASSIVE_OPTIONS_CORE_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_SECTOR_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_JAPAN_ETF_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_ASIA_PROXY_UNDERLYINGS_FOR_PIPELINE,
                *MASSIVE_OPTIONS_ADR_PRIMARY_UNDERLYINGS_FOR_PIPELINE,
            )
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
