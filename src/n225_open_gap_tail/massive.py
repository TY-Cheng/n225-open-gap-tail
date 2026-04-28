from __future__ import annotations

import time as time_module
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.datalake import atomic_write_parquet, write_json_atomic


class MassiveApiError(RuntimeError):
    """Raised when a Massive.com request fails unexpectedly."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MassiveEndpointPayload:
    name: str
    ticker: str
    path: str
    params: dict[str, str]
    http_status: int
    ok: bool
    row_count: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class MassiveSmokeResult:
    bronze_payload_path: Path
    daily_parquet_path: Path
    minute_parquet_path: Path
    daily_rows: int
    minute_rows: int
    minute_regular_session_rows: int
    daily_statuses: dict[str, int]
    minute_status: int
    probe_statuses: dict[str, int]


class MassiveClient:
    """Small Massive.com REST client for early U.S. predictor data engineering."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.massive.com",
        timeout_seconds: int = 30,
        min_request_interval_seconds: float = 0.0,
        max_retries: int = 2,
        rate_limit_backoff_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise MassiveApiError("MASSIVE_API_KEY is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._min_request_interval_seconds = max(0.0, min_request_interval_seconds)
        self._max_retries = max(0, max_retries)
        self._rate_limit_backoff_seconds = max(0.0, rate_limit_backoff_seconds)
        self._last_request_monotonic: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MassiveClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def request_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        raise_for_status: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        query = dict(params or {})
        query["apiKey"] = self._api_key
        attempt = 0
        while True:
            self._throttle()
            response = self._client.get(f"{self._base_url}{path}", params=query)
            if response.status_code != 429 and response.status_code < 500:
                break
            if attempt >= self._max_retries:
                break
            attempt += 1
            backoff = (
                self._rate_limit_backoff_seconds
                if response.status_code == 429
                else min(5.0, attempt)
            )
            if backoff > 0:
                time_module.sleep(backoff)
        payload = self._decode_payload(response)
        if raise_for_status and response.status_code >= 400:
            message = (
                payload.get("error")
                or payload.get("message")
                or payload.get("status")
                or "Massive.com request failed"
            )
            raise MassiveApiError(str(message), status_code=response.status_code)
        return response.status_code, payload

    def _throttle(self) -> None:
        if self._min_request_interval_seconds <= 0:
            return
        now = time_module.monotonic()
        if self._last_request_monotonic is not None:
            elapsed = now - self._last_request_monotonic
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                time_module.sleep(remaining)
        self._last_request_monotonic = time_module.monotonic()

    def get_aggregate_bars(
        self,
        *,
        ticker: str,
        multiplier: int,
        timespan: str,
        start: str,
        end: str,
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 50_000,
    ) -> list[dict[str, Any]]:
        endpoint = self.fetch_aggregate_bars(
            name=f"{ticker}_{timespan}",
            ticker=ticker,
            multiplier=multiplier,
            timespan=timespan,
            start=start,
            end=end,
            adjusted=adjusted,
            sort=sort,
            limit=limit,
            raise_for_status=True,
        )
        return _extract_results(endpoint.payload)

    def fetch_aggregate_bars(
        self,
        *,
        name: str,
        ticker: str,
        multiplier: int,
        timespan: str,
        start: str,
        end: str,
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 50_000,
        raise_for_status: bool = False,
    ) -> MassiveEndpointPayload:
        path = (
            f"/v2/aggs/ticker/{quote(ticker, safe=':')}/range/{multiplier}/{timespan}/{start}/{end}"
        )
        params = {
            "adjusted": str(adjusted).lower(),
            "sort": sort,
            "limit": str(limit),
        }
        status_code, payload = self.request_json(
            path,
            params,
            raise_for_status=raise_for_status,
        )
        rows = payload.get("results", [])
        row_count = len(rows) if isinstance(rows, list) else 0
        return MassiveEndpointPayload(
            name=name,
            ticker=ticker,
            path=path,
            params=params,
            http_status=status_code,
            ok=200 <= status_code < 300,
            row_count=row_count,
            payload=payload,
        )

    @staticmethod
    def _decode_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MassiveApiError(
                "Massive.com response was not JSON",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise MassiveApiError(
                "Massive.com response JSON was not an object",
                status_code=response.status_code,
            )
        return payload


def normalize_aggregate_bars(
    *,
    ticker: str,
    rows: list[dict[str, Any]],
    multiplier: int,
    timespan: str,
    research_download_ts_utc: datetime,
    us_timezone: str = "America/New_York",
    regular_session_start_et: str = "09:30",
    regular_session_end_et: str = "16:00",
) -> list[dict[str, object]]:
    """Normalize Massive aggregate bars into a timestamp-auditable row schema."""
    et_zone = ZoneInfo(us_timezone)
    regular_start = _parse_clock(regular_session_start_et)
    regular_end = _parse_clock(regular_session_end_et)
    records: list[dict[str, object]] = []

    for row in rows:
        start_ts_utc = _timestamp_from_millis(row.get("t"))
        start_ts_et = start_ts_utc.astimezone(et_zone)
        end_ts_utc = _bar_end_ts_utc(
            start_ts_utc=start_ts_utc,
            start_ts_et=start_ts_et,
            multiplier=multiplier,
            timespan=timespan,
            et_zone=et_zone,
        )
        records.append(
            {
                "source": "massive",
                "ticker": ticker,
                "multiplier": multiplier,
                "timespan": timespan,
                "bar_date_et": start_ts_et.date().isoformat(),
                "bar_start_ts_utc": start_ts_utc,
                "bar_start_ts_et": start_ts_et,
                "bar_end_ts_utc": end_ts_utc,
                "model_cutoff_ts_utc": end_ts_utc,
                "vendor_available_ts_utc": None,
                "research_download_ts_utc": research_download_ts_utc,
                "is_us_regular_session": _is_us_regular_session_bar(
                    start_ts_et,
                    timespan,
                    regular_start=regular_start,
                    regular_end=regular_end,
                ),
                "open": _optional_float(row.get("o")),
                "high": _optional_float(row.get("h")),
                "low": _optional_float(row.get("l")),
                "close": _optional_float(row.get("c")),
                "volume": _optional_float(row.get("v")),
                "vwap": _optional_float(row.get("vw")),
                "transactions": _optional_int(row.get("n")),
                "raw_t": _optional_int(row.get("t")),
            }
        )

    return records


def write_massive_smoke_sample(
    *,
    settings: Settings,
    tickers: tuple[str, ...],
    start: str,
    end: str,
    minute_ticker: str,
    minute_date: str,
    probe_tickers: tuple[str, ...],
    client: MassiveClient | None = None,
) -> MassiveSmokeResult:
    should_close = client is None
    active_client = client or MassiveClient(
        api_key=settings.massive_api_key,
        base_url=settings.massive_base_url,
        timeout_seconds=settings.massive_request_timeout_seconds,
        min_request_interval_seconds=settings.massive_min_request_interval_seconds,
        max_retries=settings.massive_max_retries,
        rate_limit_backoff_seconds=settings.massive_rate_limit_backoff_seconds,
    )
    downloaded_at = datetime.now(UTC)

    try:
        daily_requests = [
            active_client.fetch_aggregate_bars(
                name=f"daily_{ticker}",
                ticker=ticker,
                multiplier=1,
                timespan="day",
                start=start,
                end=end,
            )
            for ticker in tickers
        ]
        minute_request = active_client.fetch_aggregate_bars(
            name=f"minute_{minute_ticker}",
            ticker=minute_ticker,
            multiplier=1,
            timespan="minute",
            start=minute_date,
            end=minute_date,
        )
        probe_requests = [
            active_client.fetch_aggregate_bars(
                name=f"probe_{ticker}",
                ticker=ticker,
                multiplier=1,
                timespan="day",
                start=start,
                end=end,
            )
            for ticker in probe_tickers
        ]
    finally:
        if should_close:
            active_client.close()

    daily_records: list[dict[str, object]] = []
    for request in daily_requests:
        if request.ok:
            daily_records.extend(
                normalize_aggregate_bars(
                    ticker=request.ticker,
                    rows=_extract_results(request.payload),
                    multiplier=1,
                    timespan="day",
                    research_download_ts_utc=downloaded_at,
                    us_timezone=settings.project_timezone_us,
                    regular_session_start_et=settings.massive_regular_session_start_et,
                    regular_session_end_et=settings.massive_regular_session_end_et,
                )
            )

    minute_records: list[dict[str, object]] = []
    if minute_request.ok:
        minute_records = normalize_aggregate_bars(
            ticker=minute_request.ticker,
            rows=_extract_results(minute_request.payload),
            multiplier=1,
            timespan="minute",
            research_download_ts_utc=downloaded_at,
            us_timezone=settings.project_timezone_us,
            regular_session_start_et=settings.massive_regular_session_start_et,
            regular_session_end_et=settings.massive_regular_session_end_et,
        )

    bronze_dir = (
        settings.bronze_data_dir
        / "massive_smoke"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    silver_dir = (
        settings.silver_data_dir
        / "massive_smoke"
        / "schema_version=1"
        / f"start={start}"
        / f"end={end}"
    )
    bronze_payload_path = bronze_dir / "payload.json"
    daily_parquet_path = silver_dir / "daily_aggs.parquet"
    minute_parquet_path = silver_dir / f"minute_aggs_{minute_ticker}_{minute_date}.parquet"

    document = {
        "metadata": {
            "source": "massive",
            "api_base_url": settings.massive_base_url,
            "downloaded_at_utc": downloaded_at.isoformat(),
            "note": "API key is intentionally excluded from this raw smoke artifact.",
        },
        "daily_requests": [_endpoint_to_document(request) for request in daily_requests],
        "minute_request": _endpoint_to_document(minute_request),
        "probe_requests": [_endpoint_to_document(request) for request in probe_requests],
    }
    write_json_atomic(bronze_payload_path, document)
    atomic_write_parquet(daily_parquet_path, daily_records)
    atomic_write_parquet(minute_parquet_path, minute_records)

    regular_session_rows = sum(
        1 for record in minute_records if record["is_us_regular_session"] is True
    )
    return MassiveSmokeResult(
        bronze_payload_path=bronze_payload_path,
        daily_parquet_path=daily_parquet_path,
        minute_parquet_path=minute_parquet_path,
        daily_rows=len(daily_records),
        minute_rows=len(minute_records),
        minute_regular_session_rows=regular_session_rows,
        daily_statuses={request.ticker: request.http_status for request in daily_requests},
        minute_status=minute_request.http_status,
        probe_statuses={request.ticker: request.http_status for request in probe_requests},
    )


def _endpoint_to_document(endpoint: MassiveEndpointPayload) -> dict[str, object]:
    return {
        "name": endpoint.name,
        "ticker": endpoint.ticker,
        "path": endpoint.path,
        "params": endpoint.params,
        "http_status": endpoint.http_status,
        "ok": endpoint.ok,
        "row_count": endpoint.row_count,
        "payload": endpoint.payload,
    }


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise MassiveApiError("Expected list payload at 'results'")

    rows: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            raise MassiveApiError("Massive.com aggregate row was not an object")
        rows.append(row)
    return rows


def _timestamp_from_millis(value: object) -> datetime:
    if not isinstance(value, int | float):
        raise MassiveApiError("Massive.com aggregate row is missing numeric 't'")
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def _bar_end_ts_utc(
    *,
    start_ts_utc: datetime,
    start_ts_et: datetime,
    multiplier: int,
    timespan: str,
    et_zone: ZoneInfo,
) -> datetime:
    if timespan == "minute":
        return start_ts_utc + timedelta(minutes=multiplier)
    if timespan == "hour":
        return start_ts_utc + timedelta(hours=multiplier)
    if timespan == "day":
        close_ts_et = datetime.combine(start_ts_et.date(), time(16, 0), tzinfo=et_zone)
        return close_ts_et.astimezone(UTC)
    return start_ts_utc


def _is_us_regular_session_bar(
    start_ts_et: datetime,
    timespan: str,
    *,
    regular_start: time,
    regular_end: time,
) -> bool | None:
    if timespan != "minute":
        return None
    start_clock = start_ts_et.time()
    return regular_start <= start_clock < regular_end


def _parse_clock(value: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M")  # noqa: DTZ007
    except ValueError as exc:
        raise MassiveApiError("Clock values must use HH:MM format") from exc
    return parsed.time()


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise MassiveApiError("Boolean value is not a valid numeric aggregate field")
    if isinstance(value, int | float | str):
        return float(value)
    raise MassiveApiError("Aggregate field could not be converted to float")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise MassiveApiError("Boolean value is not a valid integer aggregate field")
    if isinstance(value, int | float | str):
        return int(value)
    raise MassiveApiError("Aggregate field could not be converted to int")
