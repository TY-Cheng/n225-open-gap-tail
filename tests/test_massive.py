from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources.massive import (
    MassiveApiError,
    MassiveClient,
    normalize_aggregate_bars,
    write_massive_smoke_sample,
)


def test_massive_client_fetches_aggregate_bars_without_exposing_key() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "ticker": "SPY",
                "results": [_bar("2026-01-05T14:30:00+00:00", close=101.0)],
            },
            request=request,
        )

    with MassiveClient(
        api_key="massive-secret",
        base_url="https://api.massive.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        rows = client.get_aggregate_bars(
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )
        endpoint = client.fetch_aggregate_bars(
            name="probe_vix",
            ticker="I:VIX",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )

    assert rows[0]["c"] == 101.0
    assert endpoint.path == "/v2/aggs/ticker/I:VIX/range/1/day/2026-01-05/2026-01-05"
    assert endpoint.params == {"adjusted": "true", "sort": "asc", "limit": "50000"}
    assert all("apiKey=massive-secret" in url for url in seen_urls)
    assert "massive-secret" not in json.dumps(endpoint.params)


def test_massive_client_reports_http_and_payload_errors() -> None:
    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"status": "NOT_AUTHORIZED", "message": "not subscribed"},
            request=request,
        )

    with (
        MassiveClient(
            api_key="secret",
            base_url="https://api.massive.test",
            transport=httpx.MockTransport(forbidden_handler),
        ) as client,
        pytest.raises(MassiveApiError) as excinfo,
    ):
        client.get_aggregate_bars(
            ticker="I:VIX",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )

    assert excinfo.value.status_code == 403
    assert "secret" not in str(excinfo.value)

    def invalid_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", request=request)

    with (
        MassiveClient(
            api_key="secret",
            base_url="https://api.massive.test",
            transport=httpx.MockTransport(invalid_json_handler),
        ) as client,
        pytest.raises(MassiveApiError, match="not JSON"),
    ):
        client.get_aggregate_bars(
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )


def test_massive_client_retries_rate_limits_and_throttles(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = [429, 200]
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        payload = {"status": "OK", "results": [_bar("2026-01-05T05:00:00+00:00", close=101.0)]}
        return httpx.Response(status, json=payload, request=request)

    monkeypatch.setattr("n225_open_gap_tail.sources.massive.time_module.sleep", sleeps.append)
    with MassiveClient(
        api_key="secret",
        base_url="https://api.massive.test",
        min_request_interval_seconds=0.1,
        max_retries=1,
        rate_limit_backoff_seconds=2.0,
        transport=httpx.MockTransport(handler),
    ) as client:
        endpoint = client.fetch_aggregate_bars(
            name="daily_SPY",
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )

    assert endpoint.http_status == 200
    assert 2.0 in sleeps


def test_massive_client_retries_network_timeouts_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("simulated timeout", request=request)
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [_bar("2026-01-05T05:00:00+00:00", close=101.0)],
            },
            request=request,
        )

    monkeypatch.setattr("n225_open_gap_tail.sources.massive.time_module.sleep", sleeps.append)
    with MassiveClient(
        api_key="massive-secret",
        base_url="https://api.massive.test",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    ) as client:
        endpoint = client.fetch_aggregate_bars(
            name="daily_SPY",
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )

    assert endpoint.http_status == 200
    assert attempts == 2
    assert sleeps == [1.0]


def test_massive_client_reports_exhausted_network_timeout_as_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with MassiveClient(
        api_key="massive-secret",
        base_url="https://api.massive.test",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        endpoint = client.fetch_aggregate_bars(
            name="daily_SPY",
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )

    assert endpoint.http_status == 0
    assert endpoint.ok is False
    assert endpoint.row_count == 0
    assert endpoint.payload["error_class"] == "network_error"
    assert "massive-secret" not in str(endpoint.payload)


def test_normalize_aggregate_bars_adds_timestamp_audit_fields() -> None:
    rows = [
        _bar("2026-01-05T14:30:00+00:00", close=100.0),
        _bar("2026-01-05T21:00:00+00:00", close=101.0),
    ]

    records = normalize_aggregate_bars(
        ticker="SPY",
        rows=rows,
        multiplier=1,
        timespan="minute",
        research_download_ts_utc=datetime(2026, 1, 6, tzinfo=UTC),
    )

    assert records[0]["bar_date_et"] == "2026-01-05"
    assert records[0]["is_us_regular_session"] is True
    assert records[1]["is_us_regular_session"] is False
    assert records[0]["model_cutoff_ts_utc"] == datetime(2026, 1, 5, 14, 31, tzinfo=UTC)
    assert records[0]["vendor_available_ts_utc"] is None


def test_write_massive_smoke_sample_writes_bronze_json_and_silver_parquet(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "I:VIX" in path:
            return httpx.Response(
                403,
                json={"status": "NOT_AUTHORIZED", "message": "not subscribed"},
                request=request,
            )
        if "/minute/" in path:
            payload = {
                "status": "OK",
                "ticker": "SPY",
                "results": [
                    _bar("2026-01-05T14:29:00+00:00", close=99.0),
                    _bar("2026-01-05T14:30:00+00:00", close=100.0),
                    _bar("2026-01-05T21:00:00+00:00", close=101.0),
                ],
            }
            return httpx.Response(200, json=payload, request=request)
        ticker = "SPY" if "SPY" in path else "QQQ"
        payload = {
            "status": "OK",
            "ticker": ticker,
            "results": [_bar("2026-01-05T05:00:00+00:00", close=400.0)],
        }
        return httpx.Response(200, json=payload, request=request)

    settings = Settings(
        bronze_data_dir=tmp_path / "bronze",
        silver_data_dir=tmp_path / "silver",
        massive_base_url="https://api.massive.test",
    )
    client = MassiveClient(
        api_key="massive-secret",
        base_url="https://api.massive.test",
        transport=httpx.MockTransport(handler),
    )

    result = write_massive_smoke_sample(
        settings=settings,
        tickers=("SPY", "QQQ"),
        start="2026-01-05",
        end="2026-01-09",
        minute_ticker="SPY",
        minute_date="2026-01-05",
        probe_tickers=("I:VIX",),
        client=client,
    )
    client.close()

    raw_text = result.bronze_payload_path.read_text(encoding="utf-8")
    raw_payload = json.loads(raw_text)
    daily_df = pl.read_parquet(result.daily_parquet_path)
    minute_df = pl.read_parquet(result.minute_parquet_path)

    assert "bronze/massive_smoke" in result.bronze_payload_path.as_posix()
    assert "silver/massive_smoke" in result.daily_parquet_path.as_posix()
    assert "massive-secret" not in raw_text
    assert raw_payload["metadata"]["source"] == "massive"
    assert raw_payload["daily_requests"][0]["params"]["adjusted"] == "true"
    assert result.daily_rows == 2
    assert result.minute_rows == 3
    assert result.minute_regular_session_rows == 1
    assert result.daily_statuses == {"SPY": 200, "QQQ": 200}
    assert result.minute_status == 200
    assert result.probe_statuses == {"I:VIX": 403}
    assert daily_df.select("ticker").to_series().to_list() == ["SPY", "QQQ"]
    assert minute_df.select("is_us_regular_session").to_series().to_list() == [
        False,
        True,
        False,
    ]


def test_massive_validation_errors_are_explicit() -> None:
    with pytest.raises(MassiveApiError, match="Massive API key"):
        MassiveClient(api_key="")

    with pytest.raises(MassiveApiError, match="missing numeric"):
        normalize_aggregate_bars(
            ticker="SPY",
            rows=[{"o": 1.0}],
            multiplier=1,
            timespan="day",
            research_download_ts_utc=datetime(2026, 1, 6, tzinfo=UTC),
        )

    with (
        pytest.raises(MassiveApiError, match="not an object"),
        MassiveClient(
            api_key="secret",
            base_url="https://api.massive.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"results": [1]},
                    request=request,
                )
            ),
        ) as client,
    ):
        client.get_aggregate_bars(
            ticker="SPY",
            multiplier=1,
            timespan="day",
            start="2026-01-05",
            end="2026-01-05",
        )


def _bar(timestamp: str, *, close: float) -> dict[str, float | int]:
    ts = datetime.fromisoformat(timestamp).timestamp()
    return {
        "t": int(ts * 1000),
        "o": close - 1.0,
        "h": close + 1.0,
        "l": close - 2.0,
        "c": close,
        "v": 1000.0,
        "vw": close - 0.25,
        "n": 10,
    }
