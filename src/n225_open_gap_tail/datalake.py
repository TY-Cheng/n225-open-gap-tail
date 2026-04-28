from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import polars as pl
import xxhash

CHUNK_HASH_ALGO = "xxhash64"
DEFAULT_SCHEMA_VERSION = 1
CACHE_TMP_GC_HOURS = 2
FRED_CACHE_TTL_DAYS = 30
MAIN_SAMPLE_START = "2016-07-19"
AUDIT_SAMPLE_START = "2008-05-07"
TMP_MARKER = ".tmp."


class VendorErrorClass(StrEnum):
    OK = "ok"
    UNAVAILABLE_ENTITLEMENT = "unavailable_entitlement"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    VENDOR_5XX = "vendor_5xx"
    NO_DATA = "no_data"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class ParquetSchema:
    name: str
    version: int
    columns: tuple[tuple[str, Any], ...]

    @property
    def polars_schema(self) -> dict[str, Any]:
        return dict(self.columns)

    @property
    def hash(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "version": self.version,
                "columns": [(name, str(dtype)) for name, dtype in self.columns],
            },
            sort_keys=True,
        )
        return xxhash.xxh64_hexdigest(payload.encode("utf-8"))


@dataclass(frozen=True)
class AtomicWriteResult:
    path: Path
    rows: int
    schema_name: str | None
    schema_version: int | None
    schema_hash: str | None
    chunk_hash_algo: str
    chunk_hash: str
    metadata_path: Path


JQUANTS_BRONZE_SCHEMA = ParquetSchema(
    name="jquants_futures_daily_bronze",
    version=DEFAULT_SCHEMA_VERSION,
    columns=(
        ("Date", pl.Utf8),
        ("ProdCat", pl.Utf8),
        ("Code", pl.Utf8),
        ("CM", pl.Utf8),
        ("CCMFlag", pl.Utf8),
        ("LTD", pl.Utf8),
        ("SQD", pl.Utf8),
        ("AO", pl.Float64),
        ("AH", pl.Float64),
        ("AL", pl.Float64),
        ("AC", pl.Float64),
        ("EO", pl.Float64),
        ("EH", pl.Float64),
        ("EL", pl.Float64),
        ("EC", pl.Float64),
        ("Settle", pl.Float64),
        ("Vo", pl.Float64),
        ("OI", pl.Float64),
        ("source_endpoint", pl.Utf8),
        ("requested_date", pl.Utf8),
        ("research_download_ts_utc", pl.Datetime("us", "UTC")),
    ),
)

JQUANTS_SILVER_SCHEMA = ParquetSchema(
    name="jquants_nk225f_daily_silver",
    version=DEFAULT_SCHEMA_VERSION,
    columns=(
        ("trading_date", pl.Utf8),
        ("product_category", pl.Utf8),
        ("contract_code", pl.Utf8),
        ("contract_month", pl.Utf8),
        ("central_contract_month_flag", pl.Boolean),
        ("last_trading_day", pl.Utf8),
        ("special_quotation_day", pl.Utf8),
        ("day_session_open", pl.Float64),
        ("day_session_close", pl.Float64),
        ("night_session_open", pl.Float64),
        ("night_session_close", pl.Float64),
        ("settlement_price", pl.Float64),
        ("volume", pl.Float64),
        ("open_interest", pl.Float64),
        ("target_open_ts_utc", pl.Datetime("us", "UTC")),
        ("night_session_close_ts_utc", pl.Datetime("us", "UTC")),
        ("vendor_available_ts_utc", pl.Datetime("us", "UTC")),
        ("research_download_ts_utc", pl.Datetime("us", "UTC")),
        ("invalid_day_session_open", pl.Boolean),
        ("invalid_day_session_close", pl.Boolean),
        ("invalid_night_session_close", pl.Boolean),
        ("invalid_settlement_price", pl.Boolean),
        ("day_session_ohlc_violation", pl.Boolean),
        ("night_session_ohlc_violation", pl.Boolean),
    ),
)

CALENDAR_MAP_SCHEMA = ParquetSchema(
    name="calendar_map",
    version=DEFAULT_SCHEMA_VERSION,
    columns=(
        ("ose_trading_date", pl.Utf8),
        ("us_session_date", pl.Utf8),
        ("us_official_close_ts_utc", pl.Datetime("us", "UTC")),
        ("us_early_close_flag", pl.Boolean),
        ("dst_regime", pl.Utf8),
        ("ose_day_open_ts_utc", pl.Datetime("us", "UTC")),
        ("ose_night_close_ts_utc", pl.Datetime("us", "UTC")),
        ("us_close_to_ose_night_close_minutes", pl.Float64),
        ("model_cutoff_ts_utc", pl.Datetime("us", "UTC")),
        ("target_open_ts_utc", pl.Datetime("us", "UTC")),
        ("mapping_status", pl.Utf8),
        ("mapping_reason", pl.Utf8),
    ),
)

SPY_MINUTE_FEATURE_SCHEMA = ParquetSchema(
    name="spy_minute_derived_features",
    version=DEFAULT_SCHEMA_VERSION,
    columns=(
        ("bar_date_et", pl.Utf8),
        ("bar_end_ts_utc", pl.Datetime("us", "UTC")),
        ("close", pl.Float64),
        ("is_us_regular_session", pl.Boolean),
        ("spy_late_30m_return", pl.Float64),
        ("spy_late_60m_return", pl.Float64),
        ("spy_late_session_range", pl.Float64),
        ("spy_late_volume_surge", pl.Float64),
        ("spy_final_window_momentum", pl.Float64),
        ("feature_available_ts_utc", pl.Datetime("us", "UTC")),
        ("official_close_ts_utc", pl.Datetime("us", "UTC")),
        ("selected_close_bar_end_ts_utc", pl.Datetime("us", "UTC")),
        ("vendor_lag_seconds", pl.Int64),
    ),
)

FRED_CACHE_SCHEMA = ParquetSchema(
    name="fred_series_cache",
    version=DEFAULT_SCHEMA_VERSION,
    columns=(
        ("series_id", pl.Utf8),
        ("observation_date", pl.Utf8),
        ("value", pl.Float64),
        ("vendor_available_date_et", pl.Utf8),
        ("vendor_available_ts_utc", pl.Datetime("us", "UTC")),
        ("research_download_ts_utc", pl.Datetime("us", "UTC")),
        ("vintage_policy", pl.Utf8),
        ("vintage_safe", pl.Boolean),
    ),
)


def cache_path(
    root: Path,
    *,
    dataset: str,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
    year: int | None = None,
    month: int | None = None,
    extra_partitions: Mapping[str, str] | None = None,
) -> Path:
    path = root / dataset / f"schema_version={schema_version}"
    for key, value in (extra_partitions or {}).items():
        path /= f"{key}={value}"
    if year is not None:
        path /= f"year={year:04d}"
    if month is not None:
        path /= f"month={month:02d}"
    return path / "data.parquet"


def scan_hive_parquet(path: str | Path, *, hive_schema: Mapping[str, Any]) -> pl.LazyFrame:
    return pl.scan_parquet(path, hive_schema=dict(hive_schema), hive_partitioning=True)


def atomic_write_parquet(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    *,
    schema: ParquetSchema | None = None,
    compression: str = "zstd",
    metadata: Mapping[str, object] | None = None,
) -> AtomicWriteResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}{TMP_MARKER}{os.getpid()}.{uuid.uuid4().hex}")
    row_list = [dict(row) for row in rows]
    try:
        frame = (
            pl.DataFrame(row_list, schema=schema.polars_schema, orient="row")
            if schema is not None
            else pl.DataFrame(row_list, infer_schema_length=None)
        )
        if schema is not None:
            frame = frame.select(
                [
                    pl.col(name).cast(dtype, strict=False).alias(name)
                    for name, dtype in schema.columns
                ]
            )
        frame.write_parquet(tmp_path, compression=cast(Any, compression))
        validated = pl.read_parquet(tmp_path)
        if schema is not None:
            _validate_frame_schema(validated, schema)
        if validated.height != len(row_list):
            raise ValueError(
                f"Parquet row-count validation failed for {path}: "
                f"{validated.height} != {len(row_list)}"
            )
        chunk_hash = file_xxhash64(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    result = AtomicWriteResult(
        path=path,
        rows=len(row_list),
        schema_name=schema.name if schema else None,
        schema_version=schema.version if schema else None,
        schema_hash=schema.hash if schema else None,
        chunk_hash_algo=CHUNK_HASH_ALGO,
        chunk_hash=chunk_hash,
        metadata_path=metadata_path,
    )
    write_json_atomic(
        metadata_path,
        {
            "path": str(path),
            "rows": result.rows,
            "schema_name": result.schema_name,
            "schema_version": result.schema_version,
            "schema_hash": result.schema_hash,
            "chunk_hash_algo": result.chunk_hash_algo,
            "chunk_hash": result.chunk_hash,
            "compression": compression,
            "created_at_utc": datetime.now(UTC).isoformat(),
            **dict(metadata or {}),
        },
    )
    return result


def write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}{TMP_MARKER}{os.getpid()}.{uuid.uuid4().hex}")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def file_xxhash64(path: Path) -> str:
    digest = xxhash.xxh64()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_orphan_tmp_files(
    root: Path,
    *,
    older_than_hours: int = CACHE_TMP_GC_HOURS,
    now: datetime | None = None,
) -> list[Path]:
    if not root.exists():
        return []
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=older_than_hours)
    removed: list[Path] = []
    for path in root.rglob(f"*{TMP_MARKER}*"):
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified <= cutoff:
            path.unlink()
            removed.append(path)
    return removed


def classify_vendor_error(
    *,
    status_code: int | None = None,
    message: str = "",
    exception: BaseException | None = None,
    row_count: int | None = None,
) -> VendorErrorClass:
    if exception is not None:
        return VendorErrorClass.NETWORK_ERROR
    if status_code is None:
        return VendorErrorClass.UNKNOWN_ERROR
    if 200 <= status_code < 300:
        if row_count == 0:
            return VendorErrorClass.NO_DATA
        return VendorErrorClass.OK
    if status_code in {401, 403}:
        lowered = message.lower()
        if "auth" in lowered or "api key" in lowered or status_code == 401:
            return VendorErrorClass.AUTH_FAILED
        return VendorErrorClass.UNAVAILABLE_ENTITLEMENT
    if status_code == 429:
        return VendorErrorClass.RATE_LIMITED
    if 500 <= status_code < 600:
        return VendorErrorClass.VENDOR_5XX
    if status_code == 404:
        return VendorErrorClass.NO_DATA
    return VendorErrorClass.UNKNOWN_ERROR


def is_fred_cache_fresh_at_run_start(
    metadata: Mapping[str, object] | None,
    *,
    run_start_utc: datetime,
    ttl_days: int = FRED_CACHE_TTL_DAYS,
) -> bool:
    if not metadata:
        return False
    raw = metadata.get("pull_completed_at_utc") or metadata.get("created_at_utc")
    if not isinstance(raw, str):
        return False
    try:
        pulled_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if pulled_at.tzinfo is None:
        pulled_at = pulled_at.replace(tzinfo=UTC)
    return run_start_utc.astimezone(UTC) - pulled_at.astimezone(UTC) <= timedelta(days=ttl_days)


def compute_combined_clean_start(
    *,
    jquants_required_field_coverage_start: str,
    massive_daily_entitlement_start: str | None,
    fred_required_series_coverage_start: str | None,
) -> str:
    candidates = [
        jquants_required_field_coverage_start,
        massive_daily_entitlement_start or jquants_required_field_coverage_start,
        fred_required_series_coverage_start or jquants_required_field_coverage_start,
    ]
    return max(candidates)


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _validate_frame_schema(frame: pl.DataFrame, schema: ParquetSchema) -> None:
    expected = schema.polars_schema
    actual = frame.schema
    missing = [name for name in expected if name not in actual]
    if missing:
        raise ValueError(f"{schema.name} missing columns after write: {missing}")
    mismatched = [
        (name, actual[name], expected[name]) for name in expected if actual[name] != expected[name]
    ]
    if mismatched:
        raise ValueError(f"{schema.name} schema mismatch after write: {mismatched}")
