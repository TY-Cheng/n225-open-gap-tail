from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.datalake import atomic_write_parquet, write_json_atomic


class FredDataError(RuntimeError):
    """Raised when FRED data cannot be downloaded or parsed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FredSeriesPayload:
    series_id: str
    path: str
    params: dict[str, str]
    http_status: int
    rows: list[dict[str, str]]
    raw_csv: str


@dataclass(frozen=True)
class FredSmokeResult:
    bronze_payload_path: Path
    parquet_path: Path
    rows: int
    series_statuses: dict[str, int]
    series_rows: dict[str, int]


class FredClient:
    """Tiny FRED CSV client for historical VIX and rate predictors."""

    def __init__(
        self,
        *,
        base_url: str = "https://fred.stlouisfed.org",
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FredClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def fetch_series_csv(self, series_id: str) -> FredSeriesPayload:
        path = "/graph/fredgraph.csv"
        params = {"id": series_id}
        response = self._client.get(f"{self._base_url}{path}", params=params)
        if response.status_code >= 400:
            raise FredDataError(
                f"FRED request failed for {series_id}",
                status_code=response.status_code,
            )
        rows = _parse_fred_csv(response.text, series_id)
        return FredSeriesPayload(
            series_id=series_id,
            path=path,
            params=params,
            http_status=response.status_code,
            rows=rows,
            raw_csv=response.text,
        )


def normalize_fred_rows(
    *,
    series_id: str,
    rows: list[dict[str, str]],
    start: str,
    end: str,
    research_download_ts_utc: datetime,
    us_timezone: str = "America/New_York",
    availability_lag_us_business_days: int = 1,
) -> list[dict[str, object]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    us_zone = ZoneInfo(us_timezone)
    records: list[dict[str, object]] = []

    for row in rows:
        observation_date = date.fromisoformat(row["observation_date"])
        if not start_date <= observation_date <= end_date:
            continue

        observation_ts_utc = datetime.combine(
            observation_date,
            time(16, 0),
            tzinfo=us_zone,
        ).astimezone(UTC)
        available_date = _add_us_business_days(
            observation_date,
            availability_lag_us_business_days,
        )
        vendor_available_ts_utc = datetime.combine(
            available_date,
            time(16, 0),
            tzinfo=us_zone,
        ).astimezone(UTC)
        records.append(
            {
                "source": "fred",
                "series_id": series_id,
                "observation_date": observation_date.isoformat(),
                "observation_ts_utc": observation_ts_utc,
                "model_cutoff_ts_utc": vendor_available_ts_utc,
                "vendor_available_ts_utc": vendor_available_ts_utc,
                "vendor_available_date_et": available_date.isoformat(),
                "research_download_ts_utc": research_download_ts_utc,
                "availability_lag_us_business_days": availability_lag_us_business_days,
                "availability_note": (
                    "current_historical_value_with_conservative_lag_not_alfred_vintage_safe"
                ),
                "vintage_policy": "not_vintage_safe_without_alfred_realtime_parameters",
                "value": _parse_optional_float(row["value"]),
            }
        )

    return records


def write_fred_smoke_sample(
    *,
    settings: Settings,
    series_ids: tuple[str, ...],
    start: str,
    end: str,
    client: FredClient | None = None,
) -> FredSmokeResult:
    should_close = client is None
    active_client = client or FredClient(
        base_url=settings.fred_base_url,
        timeout_seconds=settings.fred_request_timeout_seconds,
    )
    downloaded_at = datetime.now(UTC)

    try:
        series_payloads = [active_client.fetch_series_csv(series_id) for series_id in series_ids]
    finally:
        if should_close:
            active_client.close()

    records: list[dict[str, object]] = []
    for payload in series_payloads:
        records.extend(
            normalize_fred_rows(
                series_id=payload.series_id,
                rows=payload.rows,
                start=start,
                end=end,
                research_download_ts_utc=downloaded_at,
                us_timezone=settings.project_timezone_us,
            )
        )

    bronze_dir = (
        settings.bronze_data_dir
        / "fred_smoke"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    silver_dir = (
        settings.silver_data_dir
        / "fred_smoke"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    bronze_payload_path = bronze_dir / "payload.json"
    parquet_path = silver_dir / "daily.parquet"
    document = {
        "metadata": {
            "source": "fred",
            "base_url": settings.fred_base_url,
            "downloaded_at_utc": downloaded_at.isoformat(),
            "note": (
                "FRED daily values are historical research predictors, "
                "not live availability claims."
            ),
        },
        "series": [_series_to_document(payload) for payload in series_payloads],
    }
    write_json_atomic(bronze_payload_path, document)
    atomic_write_parquet(parquet_path, records)

    return FredSmokeResult(
        bronze_payload_path=bronze_payload_path,
        parquet_path=parquet_path,
        rows=len(records),
        series_statuses={payload.series_id: payload.http_status for payload in series_payloads},
        series_rows={
            series_id: sum(1 for record in records if record["series_id"] == series_id)
            for series_id in series_ids
        },
    )


def _series_to_document(payload: FredSeriesPayload) -> dict[str, Any]:
    return {
        "series_id": payload.series_id,
        "path": payload.path,
        "params": payload.params,
        "http_status": payload.http_status,
        "row_count": len(payload.rows),
        "raw_csv": payload.raw_csv,
    }


def _parse_fred_csv(text: str, series_id: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text))
    expected_fields = {"observation_date", series_id}
    if not reader.fieldnames or not expected_fields.issubset(set(reader.fieldnames)):
        raise FredDataError(f"FRED CSV for {series_id} did not have expected columns")

    rows: list[dict[str, str]] = []
    for row in reader:
        observation_date = row.get("observation_date")
        value = row.get(series_id)
        if observation_date is None or value is None:
            raise FredDataError(f"FRED CSV for {series_id} had an incomplete row")
        rows.append({"observation_date": observation_date, "value": value})
    return rows


def _add_us_business_days(start_date: date, days: int) -> date:
    current = start_date
    remaining = days
    while remaining > 0:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _parse_optional_float(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)
