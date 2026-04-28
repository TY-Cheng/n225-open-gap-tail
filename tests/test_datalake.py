from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from n225_open_gap_tail.datalake import (
    CACHE_TMP_GC_HOURS,
    CHUNK_HASH_ALGO,
    JQUANTS_BRONZE_SCHEMA,
    MAIN_SAMPLE_START,
    VendorErrorClass,
    _validate_frame_schema,
    atomic_write_parquet,
    cache_path,
    classify_vendor_error,
    cleanup_orphan_tmp_files,
    compute_combined_clean_start,
    is_fred_cache_fresh_at_run_start,
    read_json,
    scan_hive_parquet,
)


def test_atomic_parquet_write_validates_and_records_hash(tmp_path: Path) -> None:
    output = tmp_path / "bronze" / "jquants" / "data.parquet"
    result = atomic_write_parquet(
        output,
        [
            {
                "Date": "2026-01-05",
                "ProdCat": "NK225F",
                "Code": "code",
                "CM": "2026-03",
                "CCMFlag": "1",
                "LTD": "2026-03-12",
                "SQD": "2026-03-13",
                "AO": 100.0,
                "AH": 101.0,
                "AL": 99.0,
                "AC": 100.5,
                "EO": 98.0,
                "EH": 100.0,
                "EL": 97.0,
                "EC": 99.0,
                "Settle": 100.0,
                "Vo": 10.0,
                "OI": 20.0,
                "source_endpoint": "/derivatives/bars/daily/futures",
                "requested_date": "2026-01-05",
                "research_download_ts_utc": datetime(2026, 1, 6, tzinfo=UTC),
            }
        ],
        schema=JQUANTS_BRONZE_SCHEMA,
    )

    assert output.exists()
    assert result.chunk_hash_algo == CHUNK_HASH_ALGO
    assert result.schema_hash == JQUANTS_BRONZE_SCHEMA.hash
    assert result.metadata_path.exists()
    assert pl.read_parquet(output).height == 1


def test_cache_tmp_gc_removes_only_old_orphans(tmp_path: Path) -> None:
    old_tmp = tmp_path / f"data.parquet.tmp.{os.getpid()}.old"
    fresh_tmp = tmp_path / f"data.parquet.tmp.{os.getpid()}.fresh"
    old_tmp.write_text("old", encoding="utf-8")
    fresh_tmp.write_text("fresh", encoding="utf-8")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    old_time = (now - timedelta(hours=CACHE_TMP_GC_HOURS + 1)).timestamp()
    fresh_time = (now - timedelta(minutes=10)).timestamp()
    os.utime(old_tmp, (old_time, old_time))
    os.utime(fresh_tmp, (fresh_time, fresh_time))

    removed = cleanup_orphan_tmp_files(tmp_path, now=now)

    assert old_tmp in removed
    assert not old_tmp.exists()
    assert fresh_tmp.exists()


def test_hive_partition_scan_uses_numeric_partition_schema(tmp_path: Path) -> None:
    path = cache_path(tmp_path, dataset="demo", schema_version=1, year=2016, month=7)
    atomic_write_parquet(path, [{"value": 1.0}])

    frame = scan_hive_parquet(
        tmp_path / "demo" / "schema_version=1" / "year=*" / "month=*" / "*.parquet",
        hive_schema={"year": pl.Int32, "month": pl.Int8, "schema_version": pl.Int32},
    ).collect()

    assert frame.schema["year"] == pl.Int32
    assert frame.schema["month"] == pl.Int8
    assert frame.select(pl.col("year").min()).item() == 2016
    extra_path = cache_path(
        tmp_path,
        dataset="demo",
        schema_version=1,
        year=2017,
        month=8,
        extra_partitions={"ticker": "spy"},
    )
    assert "ticker=spy" in str(extra_path)


def test_atomic_parquet_write_infers_full_unspecified_schema(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics.parquet"
    rows = [{"threshold_quantile": 0, "model_name": "x"} for _ in range(120)]
    rows.append({"threshold_quantile": 0.9, "model_name": "x"})

    atomic_write_parquet(path, rows)

    frame = pl.read_parquet(path)
    assert frame.schema["threshold_quantile"] == pl.Float64
    assert frame.select(pl.col("threshold_quantile").max()).item() == 0.9


def test_vendor_error_and_ttl_policy_are_deterministic() -> None:
    assert classify_vendor_error(exception=TimeoutError()) == VendorErrorClass.NETWORK_ERROR
    assert classify_vendor_error(status_code=None) == VendorErrorClass.UNKNOWN_ERROR
    assert classify_vendor_error(status_code=403, message="plan limit") == (
        VendorErrorClass.UNAVAILABLE_ENTITLEMENT
    )
    assert classify_vendor_error(status_code=401, message="bad api key") == (
        VendorErrorClass.AUTH_FAILED
    )
    assert classify_vendor_error(status_code=429) == VendorErrorClass.RATE_LIMITED
    assert classify_vendor_error(status_code=503) == VendorErrorClass.VENDOR_5XX
    assert classify_vendor_error(status_code=404) == VendorErrorClass.NO_DATA
    assert classify_vendor_error(status_code=418) == VendorErrorClass.UNKNOWN_ERROR
    assert classify_vendor_error(status_code=200, row_count=0) == VendorErrorClass.NO_DATA

    run_start = datetime(2026, 4, 28, tzinfo=UTC)
    assert is_fred_cache_fresh_at_run_start(
        {"pull_completed_at_utc": (run_start - timedelta(days=29)).isoformat()},
        run_start_utc=run_start,
        ttl_days=30,
    )
    assert not is_fred_cache_fresh_at_run_start(
        {"pull_completed_at_utc": (run_start - timedelta(days=31)).isoformat()},
        run_start_utc=run_start,
        ttl_days=30,
    )
    assert not is_fred_cache_fresh_at_run_start(None, run_start_utc=run_start)
    assert not is_fred_cache_fresh_at_run_start(
        {"pull_completed_at_utc": 1}, run_start_utc=run_start
    )
    assert not is_fred_cache_fresh_at_run_start(
        {"pull_completed_at_utc": "not-a-date"},
        run_start_utc=run_start,
    )
    assert is_fred_cache_fresh_at_run_start(
        {"pull_completed_at_utc": "2026-04-27T00:00:00"},
        run_start_utc=run_start,
        ttl_days=30,
    )


def test_combined_clean_start_is_explicit_maximum() -> None:
    assert (
        compute_combined_clean_start(
            jquants_required_field_coverage_start=MAIN_SAMPLE_START,
            massive_daily_entitlement_start="2017-01-03",
            fred_required_series_coverage_start="2016-07-19",
        )
        == "2017-01-03"
    )


def test_read_json_and_validation_failures_are_explicit(tmp_path: Path) -> None:
    assert read_json(tmp_path / "missing.json") == {}
    path = tmp_path / "payload.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    assert read_json(path) == {"ok": True}
    with pytest.raises(ValueError, match="missing columns"):
        _validate_frame_schema(pl.DataFrame({"Date": ["2026-01-05"]}), JQUANTS_BRONZE_SCHEMA)
