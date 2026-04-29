from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

import n225_open_gap_tail.sources.cboe as cboe_module
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources.cboe import (
    CboeClient,
    CboeDataError,
    build_vix_consistency_records,
    normalize_cboe_vol_index_rows,
    write_cboe_smoke_sample,
)


def test_cboe_client_fetches_csv_and_preserves_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/VIX_History.csv")
        return httpx.Response(
            200,
            text="DATE,OPEN,HIGH,LOW,CLOSE\n2026-01-05,14,16,13,15\n",
            request=request,
        )

    with CboeClient(
        base_url="https://cboe.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        payload = client.fetch_vol_index_csv("vix")

    assert payload.symbol == "VIX"
    assert payload.raw_header == ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]
    assert payload.rows == [
        {"DATE": "2026-01-05", "OPEN": "14", "HIGH": "16", "LOW": "13", "CLOSE": "15"}
    ]


def test_cboe_client_and_parser_fail_closed_on_bad_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable", request=request)

    with (
        CboeClient(
            base_url="https://cboe.test",
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(CboeDataError, match="request failed"),
    ):
        client.fetch_vol_index_csv("VIX")

    with (
        CboeClient(
            base_url="https://cboe.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="", request=request)
            ),
        ) as client,
        pytest.raises(CboeDataError, match="header row"),
    ):
        client.fetch_vol_index_csv("VIX")
    with pytest.raises(CboeDataError, match="unsupported date format"):
        normalize_cboe_vol_index_rows(
            symbol="VIX",
            rows=[{"DATE": "bad-date", "CLOSE": "15"}],
            raw_header=["DATE", "CLOSE"],
            research_download_ts_utc=datetime(2026, 1, 6, tzinfo=UTC),
        )


def test_cboe_parser_accepts_legacy_header_styles() -> None:
    downloaded_at = datetime(2026, 1, 6, tzinfo=UTC)
    canonical = normalize_cboe_vol_index_rows(
        symbol="VIX",
        rows=[{"DATE": "2026-01-05", "OPEN": "14", "HIGH": "16", "LOW": "13", "CLOSE": "15"}],
        raw_header=["DATE", "OPEN", "HIGH", "LOW", "CLOSE"],
        research_download_ts_utc=downloaded_at,
    )
    legacy = normalize_cboe_vol_index_rows(
        symbol="VIX",
        rows=[
            {
                "Trade Date": "01/05/2026",
                "VIX Open": "14",
                "VIX High": "16",
                "VIX Low": "13",
                "VIX Close": "15",
            }
        ],
        raw_header=["Trade Date", "VIX Open", "VIX High", "VIX Low", "VIX Close"],
        research_download_ts_utc=downloaded_at,
    )

    assert canonical[0]["close"] == legacy[0]["close"] == 15.0
    assert canonical[0]["range"] == legacy[0]["range"] == 3.0
    blank_open = normalize_cboe_vol_index_rows(
        symbol="VIX",
        rows=[{"DATE": "2026-01-05", "OPEN": "", "CLOSE": "15"}],
        raw_header=["DATE", "OPEN", "CLOSE"],
        research_download_ts_utc=downloaded_at,
    )
    assert blank_open[0]["open"] is None
    assert canonical[0]["vendor_available_ts_utc"] == datetime(2026, 1, 5, 21, 15, tzinfo=UTC)


def test_cboe_parser_requires_close_field() -> None:
    with pytest.raises(CboeDataError, match="required field"):
        normalize_cboe_vol_index_rows(
            symbol="VIX",
            rows=[{"DATE": "2026-01-05", "VALUE": "15"}],
            raw_header=["DATE", "VALUE"],
            research_download_ts_utc=datetime(2026, 1, 6, tzinfo=UTC),
        )


def test_vix_consistency_records_warn_on_fred_cboe_diffs() -> None:
    warnings = build_vix_consistency_records(
        cboe_records=[
            {"symbol": "VIX", "observation_date": "2026-01-05", "close": 15.0},
            {"symbol": "VIX", "observation_date": "2026-01-06", "close": 15.5},
        ],
        fred_records=[
            {"series_id": "VIXCLS", "observation_date": "2026-01-05", "value": 15.0},
            {"series_id": "VIXCLS", "observation_date": "2026-01-06", "value": 15.0},
        ],
    )

    assert warnings == [
        {
            "observation_date": "2026-01-06",
            "cboe_vix_close": 15.5,
            "fred_vixcls": 15.0,
            "abs_diff": 0.5,
            "status": "warn",
        }
    ]


def test_write_cboe_smoke_sample_writes_bronze_silver_and_consistency(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=("DATE,OPEN,HIGH,LOW,CLOSE\n2026-01-02,14,16,13,15\n2026-01-05,15,17,14,16\n"),
            request=request,
        )

    settings = Settings(
        bronze_data_dir=tmp_path / "bronze",
        silver_data_dir=tmp_path / "silver",
        cboe_base_url="https://cboe.test",
    )
    client = CboeClient(base_url="https://cboe.test", transport=httpx.MockTransport(handler))
    result = write_cboe_smoke_sample(
        settings=settings,
        symbols=("VIX",),
        start="2026-01-05",
        end="2026-01-05",
        client=client,
        fred_records=[{"series_id": "VIXCLS", "observation_date": "2026-01-05", "value": 16.1}],
    )
    client.close()

    raw_payload = json.loads(result.bronze_payload_path.read_text(encoding="utf-8"))
    frame = pl.read_parquet(result.parquet_path)
    consistency = pl.read_parquet(result.consistency_path)

    assert raw_payload["symbols"][0]["raw_header"] == ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]
    assert result.rows == 1
    assert result.consistency_warnings == 1
    assert frame.select("observation_date").to_series().to_list() == ["2026-01-05"]
    assert consistency.select("status").to_series().to_list() == ["warn"]


def test_write_cboe_smoke_sample_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed = False

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def fetch_vol_index_csv(self, symbol: str) -> cboe_module.CboeVolIndexPayload:
            return cboe_module.CboeVolIndexPayload(
                symbol=symbol,
                path="/fake.csv",
                http_status=200,
                raw_csv="DATE,CLOSE\n2026-01-05,15\n",
                raw_header=["DATE", "CLOSE"],
                rows=[{"DATE": "2026-01-05", "CLOSE": "15"}],
            )

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(cboe_module, "CboeClient", FakeClient)
    result = write_cboe_smoke_sample(
        settings=Settings(bronze_data_dir=tmp_path / "bronze", silver_data_dir=tmp_path / "silver"),
        symbols=("VIX",),
        start="2026-01-05",
        end="2026-01-05",
    )

    assert closed is True
    assert result.rows == 1
