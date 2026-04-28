from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import polars as pl

from n225_open_gap_tail.config import Settings


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
    raw_output_path: Path
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
        records.append(
            {
                "source": "fred",
                "series_id": series_id,
                "observation_date": observation_date.isoformat(),
                "observation_ts_utc": observation_ts_utc,
                "model_cutoff_ts_utc": observation_ts_utc,
                "vendor_available_ts_utc": None,
                "research_download_ts_utc": research_download_ts_utc,
                "availability_note": "historical_daily_close_proxy_not_live_availability",
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

    raw_dir = settings.raw_data_dir / "fred" / "smoke"
    interim_dir = settings.interim_data_dir / "fred" / "smoke"
    raw_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)

    raw_output_path = raw_dir / f"fred_smoke_{start}_{end}.json"
    parquet_path = interim_dir / f"fred_daily_{start}_{end}.parquet"
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
    raw_output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    pl.DataFrame(records).write_parquet(parquet_path)

    return FredSmokeResult(
        raw_output_path=raw_output_path,
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


def _parse_optional_float(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)
