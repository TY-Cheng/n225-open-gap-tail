import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources.jquants import (
    JQuantsApiError,
    JQuantsV2Client,
    write_jquants_smoke_sample,
)


def test_jquants_client_paginates_and_sends_api_key() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        assert request.headers["x-api-key"] == "secret"
        if "pagination_key=next-page" in str(request.url):
            return httpx.Response(200, json={"data": [{"Code": "72030", "Date": "2025-12-02"}]})
        return httpx.Response(
            200,
            json={
                "data": [{"Code": "72030", "Date": "2025-12-01"}],
                "pagination_key": "next-page",
            },
        )

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(handler),
    )

    rows = client.get_equity_daily_bars(code="72030", start="2025-12-01", end="2025-12-02")

    assert rows == [
        {"Code": "72030", "Date": "2025-12-01"},
        {"Code": "72030", "Date": "2025-12-02"},
    ]
    assert len(seen_requests) == 2
    assert seen_requests[0].url.params["code"] == "72030"
    assert seen_requests[0].url.params["from"] == "2025-12-01"
    assert seen_requests[0].url.params["to"] == "2025-12-02"
    assert seen_requests[1].url.params["pagination_key"] == "next-page"


def test_jquants_client_requires_api_key() -> None:
    with pytest.raises(JQuantsApiError, match="JQUANTS_API_KEY is required"):
        JQuantsV2Client(api_key="")


def test_jquants_client_raises_for_required_endpoint_without_leaking_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "secret"
        return httpx.Response(403, json={"message": "not entitled"})

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(JQuantsApiError) as exc_info:
        client.get_equity_master(code="72030")

    assert exc_info.value.status_code == 403
    assert "not entitled" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_jquants_client_context_manager_closes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_equity_master() == []


def test_jquants_client_rejects_malformed_payloads() -> None:
    def non_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(non_json_handler),
    )
    with pytest.raises(JQuantsApiError, match="not JSON") as non_json_error:
        client.get_equity_master()
    assert non_json_error.value.status_code == 200

    def non_object_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not-object"])

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(non_object_handler),
    )
    with pytest.raises(JQuantsApiError, match="not an object"):
        client.get_equity_master()

    def non_list_data_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"not": "a-list"}})

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(non_list_data_handler),
    )
    with pytest.raises(JQuantsApiError, match="Expected list payload"):
        client.get_equity_master()

    def non_object_row_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": ["not-object-row"]})

    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(non_object_row_handler),
    )
    with pytest.raises(JQuantsApiError, match="data row was not an object"):
        client.get_equity_master()


def test_write_jquants_smoke_sample_writes_bronze_artifact(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/equities/master":
            return httpx.Response(200, json={"data": [{"Code": "72030", "CoNameEn": "TOYOTA"}]})
        if path == "/v2/equities/bars/daily":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"Code": "72030", "Date": "2025-12-01", "O": 1.0, "C": 2.0},
                        {"Code": "72030", "Date": "2025-12-02", "O": 2.0, "C": 3.0},
                    ]
                },
            )
        if path == "/v2/derivatives/bars/daily/futures":
            return httpx.Response(403, json={"message": "subscription unavailable"})
        return httpx.Response(404, json={"message": "unexpected path"})

    settings = Settings(
        bronze_data_dir=tmp_path / "bronze",
        jquants_api_key="secret",
        jquants_api_base_url="https://example.test/v2",
        jquants_api_plan="free",
    )
    client = JQuantsV2Client(
        api_key="secret",
        base_url="https://example.test/v2",
        transport=httpx.MockTransport(handler),
    )

    result = write_jquants_smoke_sample(
        settings=settings,
        code="72030",
        start="2025-12-01",
        end="2025-12-02",
        futures_date="2025-12-01",
        client=client,
    )

    assert result.equity_master_rows == 1
    assert result.equity_daily_rows == 2
    assert result.futures_probe_status == 403
    assert result.futures_probe_rows == 0
    assert "bronze/jquants_smoke" in result.output_path.as_posix()
    document: dict[str, Any] = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert document["metadata"]["api_plan"] == "free"
    assert "secret" not in result.output_path.read_text(encoding="utf-8")
    assert document["requests"][2]["payload"]["message"] == "subscription unavailable"
