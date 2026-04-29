from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from io import StringIO
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import httpx

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import atomic_write_parquet, write_json_atomic


class CboeDataError(RuntimeError):
    """Raised when Cboe volatility-index data cannot be downloaded or parsed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CboeVolIndexPayload:
    symbol: str
    path: str
    http_status: int
    raw_csv: str
    raw_header: list[str]
    rows: list[dict[str, str]]


@dataclass(frozen=True)
class CboeSmokeResult:
    bronze_payload_path: Path
    parquet_path: Path
    consistency_path: Path
    rows: int
    symbols_statuses: dict[str, int]
    symbols_rows: dict[str, int]
    consistency_warnings: int


class CboeClient:
    """Small Cboe historical volatility-index CSV client."""

    def __init__(
        self,
        *,
        base_url: str = "https://cdn.cboe.com",
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CboeClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def fetch_vol_index_csv(self, symbol: str) -> CboeVolIndexPayload:
        clean_symbol = symbol.strip().upper()
        path = f"/api/global/us_indices/daily_prices/{clean_symbol}_History.csv"
        response = self._client.get(f"{self._base_url}{path}")
        if response.status_code >= 400:
            raise CboeDataError(
                f"Cboe volatility index CSV request failed for {clean_symbol}",
                status_code=response.status_code,
            )
        raw_header, rows = _parse_cboe_csv(response.text)
        return CboeVolIndexPayload(
            symbol=clean_symbol,
            path=path,
            http_status=response.status_code,
            raw_csv=response.text,
            raw_header=raw_header,
            rows=rows,
        )


def normalize_cboe_vol_index_rows(
    *,
    symbol: str,
    rows: list[dict[str, str]],
    raw_header: list[str],
    research_download_ts_utc: datetime,
    us_timezone: str = "America/New_York",
) -> list[dict[str, object]]:
    normalized_header = {_normalize_header(name): name for name in raw_header}
    date_field = _required_field(normalized_header, ("date", "trade_date"))
    close_field = _required_field(
        normalized_header,
        ("close", "vix_close", "vix_close_price", "close_price", "vix"),
    )
    open_field = _optional_field(normalized_header, ("open", "vix_open", "open_price"))
    high_field = _optional_field(normalized_header, ("high", "vix_high", "high_price"))
    low_field = _optional_field(normalized_header, ("low", "vix_low", "low_price"))
    us_zone = ZoneInfo(us_timezone)
    records: list[dict[str, object]] = []
    for row in rows:
        observation_date = _parse_cboe_date(row[date_field])
        observation_ts_utc = datetime.combine(observation_date, time(16, 0), tzinfo=us_zone)
        vendor_available_ts_utc = datetime.combine(observation_date, time(16, 15), tzinfo=us_zone)
        open_value = _parse_optional_float(row.get(open_field, "")) if open_field else None
        high_value = _parse_optional_float(row.get(high_field, "")) if high_field else None
        low_value = _parse_optional_float(row.get(low_field, "")) if low_field else None
        close_value = _parse_optional_float(row.get(close_field, ""))
        records.append(
            {
                "source": "cboe",
                "symbol": symbol.strip().upper(),
                "observation_date": observation_date.isoformat(),
                "observation_ts_utc": observation_ts_utc.astimezone(UTC),
                "vendor_available_ts_utc": vendor_available_ts_utc.astimezone(UTC),
                "research_download_ts_utc": research_download_ts_utc,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "range": high_value - low_value
                if high_value is not None and low_value is not None
                else None,
                "raw_header_json": list(raw_header),
            }
        )
    return records


def build_vix_consistency_records(
    *,
    cboe_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    tolerance: float = 1e-6,
) -> list[dict[str, object]]:
    cboe_by_date = {
        str(row["observation_date"]): row
        for row in cboe_records
        if str(row.get("symbol", "")).upper() == "VIX" and row.get("close") is not None
    }
    fred_by_date = {
        str(row["observation_date"]): row
        for row in fred_records
        if str(row.get("series_id", "")).upper() == "VIXCLS" and row.get("value") is not None
    }
    records: list[dict[str, object]] = []
    for observation_date in sorted(set(cboe_by_date).intersection(fred_by_date)):
        cboe_close = float(cast(str | int | float, cboe_by_date[observation_date]["close"]))
        fred_close = float(cast(str | int | float, fred_by_date[observation_date]["value"]))
        diff = cboe_close - fred_close
        if abs(diff) > tolerance:
            records.append(
                {
                    "observation_date": observation_date,
                    "cboe_vix_close": cboe_close,
                    "fred_vixcls": fred_close,
                    "abs_diff": abs(diff),
                    "status": "warn",
                }
            )
    return records


def write_cboe_smoke_sample(
    *,
    settings: Settings,
    symbols: tuple[str, ...],
    start: str,
    end: str,
    client: CboeClient | None = None,
    fred_records: list[dict[str, object]] | None = None,
) -> CboeSmokeResult:
    should_close = client is None
    active_client = client or CboeClient(
        base_url=settings.cboe_base_url,
        timeout_seconds=settings.cboe_request_timeout_seconds,
    )
    downloaded_at = datetime.now(UTC)
    try:
        payloads = [active_client.fetch_vol_index_csv(symbol) for symbol in symbols]
    finally:
        if should_close:
            active_client.close()
    records: list[dict[str, object]] = []
    for payload in payloads:
        records.extend(
            row
            for row in normalize_cboe_vol_index_rows(
                symbol=payload.symbol,
                rows=payload.rows,
                raw_header=payload.raw_header,
                research_download_ts_utc=downloaded_at,
                us_timezone=settings.project_timezone_us,
            )
            if start <= str(row["observation_date"]) <= end
        )
    consistency_records = build_vix_consistency_records(
        cboe_records=records,
        fred_records=fred_records or [],
    )
    bronze_dir = settings.bronze_data_dir / "cboe_vol_indices" / "schema_version=1" / f"end={end}"
    silver_dir = (
        settings.silver_data_dir
        / "cboe_vol_indices"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    bronze_payload_path = bronze_dir / "payload.json"
    parquet_path = silver_dir / "daily.parquet"
    consistency_path = silver_dir / "vix_consistency.parquet"
    write_json_atomic(
        bronze_payload_path,
        {
            "metadata": {
                "source": "cboe",
                "base_url": settings.cboe_base_url,
                "downloaded_at_utc": downloaded_at.isoformat(),
                "note": "Raw headers are preserved because Cboe historical CSV headers vary.",
            },
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
            "vix_consistency_warnings": len(consistency_records),
        },
    )
    atomic_write_parquet(parquet_path, records)
    atomic_write_parquet(consistency_path, consistency_records)
    return CboeSmokeResult(
        bronze_payload_path=bronze_payload_path,
        parquet_path=parquet_path,
        consistency_path=consistency_path,
        rows=len(records),
        symbols_statuses={payload.symbol: payload.http_status for payload in payloads},
        symbols_rows={payload.symbol: len(payload.rows) for payload in payloads},
        consistency_warnings=len(consistency_records),
    )


def _parse_cboe_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise CboeDataError("Cboe CSV did not have a header row")
    rows = [dict(row) for row in reader]
    return list(reader.fieldnames), rows


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _required_field(normalized_header: dict[str, str], aliases: tuple[str, ...]) -> str:
    field = _optional_field(normalized_header, aliases)
    if field is None:
        raise CboeDataError(f"Cboe CSV missing required field aliases: {aliases}")
    return field


def _optional_field(normalized_header: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if alias in normalized_header:
            return normalized_header[alias]
    return None


def _parse_optional_float(value: str) -> float | None:
    if value.strip() in {"", "."}:
        return None
    return float(value)


def _parse_cboe_date(value: str) -> date:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CboeDataError(f"Cboe CSV has unsupported date format: {value!r}")
