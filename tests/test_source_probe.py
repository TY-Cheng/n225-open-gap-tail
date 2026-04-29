from __future__ import annotations

from dataclasses import dataclass

import pytest

import n225_open_gap_tail.sources.probe as source_probe
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources.probe import SourceProbeResult


@dataclass
class _Payload:
    http_status: int
    row_count: int


class _StatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _JQuantsClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> _JQuantsClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def probe_endpoint(self, **kwargs: object) -> _Payload:
        assert kwargs["path"] == "/derivatives/bars/daily/futures"
        return _Payload(http_status=200, row_count=1)


class _MassiveClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> _MassiveClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def fetch_aggregate_bars(self, **kwargs: object) -> _Payload:
        assert kwargs["ticker"] == "SPY"
        assert kwargs["raise_for_status"] is False
        return _Payload(http_status=200, row_count=1)


class _FredPayload:
    rows = [{"DATE": "2026-01-05", "VIXCLS": "18.0"}]


class _FredClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> _FredClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def fetch_series_csv(self, series_id: str) -> _FredPayload:
        assert series_id == "VIXCLS"
        return _FredPayload()


class _CboePayload:
    rows = [{"DATE": "2026-01-05", "CLOSE": "18.0"}]


class _CboeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> _CboeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def fetch_vol_index_csv(self, symbol: str) -> _CboePayload:
        assert symbol == "VIX"
        return _CboePayload()


def test_source_probe_classifies_http_and_exceptions() -> None:
    assert source_probe._classify_http_status(200) == "ok"
    assert source_probe._classify_http_status(429) == "rate_limited"
    assert source_probe._classify_http_status(503) == "vendor_5xx"
    assert source_probe._classify_http_status(403) == "entitlement_unavailable"
    assert source_probe._classify_http_status(None) == "network_error"

    status = source_probe._exception_result("massive", _StatusError("limited", 429))
    assert status == SourceProbeResult("massive", "rate_limited", "limited", 429)
    network = source_probe._exception_result("fred", RuntimeError("socket closed"))
    assert network.status == "network_error"


def test_source_probe_reports_missing_auth() -> None:
    settings = Settings(jquants_api_key="", massive_api_key="")

    assert source_probe._probe_jquants(settings).status == "auth_failed"
    assert source_probe._probe_massive(settings).status == "auth_failed"


def test_source_probe_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(jquants_api_key="jq", massive_api_key="massive")
    monkeypatch.setattr(source_probe, "JQuantsV2Client", _JQuantsClient)
    monkeypatch.setattr(source_probe, "MassiveClient", _MassiveClient)
    monkeypatch.setattr(source_probe, "FredClient", _FredClient)
    monkeypatch.setattr(source_probe, "CboeClient", _CboeClient)

    results = source_probe.probe_sources(settings)

    assert [result.source for result in results] == ["jquants", "massive", "fred", "cboe"]
    assert {result.status for result in results} == {"ok"}


def test_csv_probe_handles_fetch_failure() -> None:
    def fail() -> int:
        raise RuntimeError("bad csv")

    result = source_probe._csv_probe("fred", fail)

    assert result.status == "network_error"
    assert result.detail == "bad csv"
