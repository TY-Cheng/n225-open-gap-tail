from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.fred import (
    FredClient,
    FredDataError,
    normalize_fred_rows,
    write_fred_smoke_sample,
)


def test_fred_client_fetches_csv_series() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            text="observation_date,VIXCLS\n2026-01-05,17.1\n",
            request=request,
        )

    with FredClient(
        base_url="https://fred.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        payload = client.fetch_series_csv("VIXCLS")

    assert payload.http_status == 200
    assert payload.rows == [{"observation_date": "2026-01-05", "value": "17.1"}]
    assert seen_urls == ["https://fred.test/graph/fredgraph.csv?id=VIXCLS"]


def test_fred_client_reports_bad_status_and_bad_csv() -> None:
    with (
        FredClient(
            base_url="https://fred.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text="error", request=request)
            ),
        ) as client,
        pytest.raises(FredDataError) as excinfo,
    ):
        client.fetch_series_csv("VIXCLS")
    assert excinfo.value.status_code == 500

    with (
        FredClient(
            base_url="https://fred.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="DATE,VALUE\n", request=request)
            ),
        ) as client,
        pytest.raises(FredDataError, match="expected columns"),
    ):
        client.fetch_series_csv("VIXCLS")


def test_normalize_fred_rows_filters_range_and_marks_missing_values() -> None:
    records = normalize_fred_rows(
        series_id="DGS10",
        rows=[
            {"observation_date": "2026-01-02", "value": "4.15"},
            {"observation_date": "2026-01-05", "value": "."},
            {"observation_date": "2026-01-06", "value": "4.20"},
        ],
        start="2026-01-05",
        end="2026-01-06",
        research_download_ts_utc=datetime(2026, 1, 7, tzinfo=UTC),
    )

    assert len(records) == 2
    assert records[0]["value"] is None
    assert records[1]["value"] == 4.20
    assert records[1]["observation_ts_utc"] == datetime(2026, 1, 6, 21, 0, tzinfo=UTC)
    assert records[1]["availability_note"] == "historical_daily_close_proxy_not_live_availability"


def test_write_fred_smoke_sample_writes_raw_and_parquet(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        series_id = request.url.params["id"]
        return httpx.Response(
            200,
            text=(
                f"observation_date,{series_id}\n2026-01-02,1.0\n2026-01-05,2.0\n2026-01-06,3.0\n"
            ),
            request=request,
        )

    settings = Settings(
        raw_data_dir=tmp_path / "raw",
        interim_data_dir=tmp_path / "interim",
        fred_base_url="https://fred.test",
    )
    client = FredClient(
        base_url="https://fred.test",
        transport=httpx.MockTransport(handler),
    )

    result = write_fred_smoke_sample(
        settings=settings,
        series_ids=("VIXCLS", "DGS2"),
        start="2026-01-05",
        end="2026-01-06",
        client=client,
    )
    client.close()

    raw_payload = json.loads(result.raw_output_path.read_text(encoding="utf-8"))
    frame = pl.read_parquet(result.parquet_path)

    assert raw_payload["metadata"]["source"] == "fred"
    assert result.rows == 4
    assert result.series_statuses == {"VIXCLS": 200, "DGS2": 200}
    assert result.series_rows == {"VIXCLS": 2, "DGS2": 2}
    assert frame.select("series_id").to_series().to_list() == [
        "VIXCLS",
        "VIXCLS",
        "DGS2",
        "DGS2",
    ]
