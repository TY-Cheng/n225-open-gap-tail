from __future__ import annotations

import gzip
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

import n225_open_gap_tail.sources.probe as source_probe
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources import massive_flatfiles
from n225_open_gap_tail.sources.massive_flatfiles import (
    MASSIVE_OPTIONS_DATASETS,
    MassiveFlatFileDatasetProbe,
    _classify_flatfile_status,
    _probe_options_dataset,
    parse_massive_flat_file_credentials,
    probe_massive_options_flat_files,
)
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


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _S3Client:
    def __init__(self, forbidden_keys: set[str] | None = None) -> None:
        self.forbidden_keys = forbidden_keys or set()

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        prefix = str(kwargs["Prefix"])
        dataset = prefix.strip("/").split("/")[-3]
        return {
            "Contents": [
                {
                    "Key": f"us_options_opra/{dataset}/2026/01/2026-01-05.csv.gz",
                    "Size": 100,
                }
            ]
        }

    def get_object(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs["Key"])
        if key in self.forbidden_keys:
            raise _S3Forbidden("forbidden")
        if "quotes_v1" in key:
            header = "ticker,bid_price,ask_price,bid_size,ask_size,participant_timestamp\n"
        else:
            header = "ticker,volume,open,close,high,low,window_start,transactions\n"
        return {"Body": _Body(gzip.compress(header.encode("utf-8")))}


class _S3MissingSampleClient(_S3Client):
    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        return {"Contents": []}


class _S3ListFailureClient(_S3Client):
    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        raise _S3Forbidden("forbidden")


class _S3Forbidden(Exception):
    response: Mapping[str, object] = {"ResponseMetadata": {"HTTPStatusCode": 403}}


class _FakeBoto3:
    def client(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {"args": args, **kwargs}


class _FakeBotocoreConfig:
    class Config:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs


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
    settings = Settings(
        jquants_api_key_file="",
        massive_api_key_file="",
        massive_flat_file_key_file="",
    )

    assert source_probe._probe_jquants(settings).status == "auth_failed"
    assert source_probe._probe_massive(settings).status == "auth_failed"
    assert source_probe._probe_massive_options_flatfiles(settings) == []


def test_source_probe_success_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jquants_key_file = tmp_path / "jquants.keyfile"
    massive_key_file = tmp_path / "massive.keyfile"
    jquants_key_file.write_text("jq\n", encoding="utf-8")
    massive_key_file.write_text("massive\n", encoding="utf-8")
    settings = Settings(
        jquants_api_key_file=str(jquants_key_file),
        massive_api_key_file=str(massive_key_file),
        massive_flat_file_key_file="",
    )
    monkeypatch.setattr(source_probe, "JQuantsV2Client", _JQuantsClient)
    monkeypatch.setattr(source_probe, "MassiveClient", _MassiveClient)
    monkeypatch.setattr(source_probe, "FredClient", _FredClient)
    monkeypatch.setattr(source_probe, "CboeClient", _CboeClient)

    results = source_probe.probe_sources(settings)

    assert [result.source for result in results] == ["jquants", "massive", "fred", "cboe"]
    assert {result.status for result in results} == {"ok"}


def test_massive_flat_file_credentials_parse_supported_shapes() -> None:
    assert parse_massive_flat_file_credentials("access\nsecret\n") == ("access", "secret")
    assert parse_massive_flat_file_credentials("access:secret") == ("access", "secret")
    assert parse_massive_flat_file_credentials("access,secret") == ("access", "secret")
    with pytest.raises(ValueError, match="access and secret"):
        parse_massive_flat_file_credentials("access-only")


def test_massive_options_flatfile_probe_reads_headers(tmp_path: Path) -> None:
    flat_file_key = tmp_path / "massive-flatfile.key"
    flat_file_key.write_text("access\nsecret\n", encoding="utf-8")
    settings = Settings(massive_flat_file_key_file=str(flat_file_key))

    results = probe_massive_options_flat_files(settings=settings, s3_client=_S3Client())

    assert [result.dataset for result in results] == list(MASSIVE_OPTIONS_DATASETS)
    assert {result.status for result in results} == {"ok"}
    assert all("direct_iv_greeks_oi=false" in result.detail for result in results)


def test_massive_options_flatfile_probe_records_get_entitlement_error(tmp_path: Path) -> None:
    flat_file_key = tmp_path / "massive-flatfile.key"
    flat_file_key.write_text("access\nsecret\n", encoding="utf-8")
    settings = Settings(massive_flat_file_key_file=str(flat_file_key))
    forbidden = {"us_options_opra/quotes_v1/2026/01/2026-01-05.csv.gz"}

    results = probe_massive_options_flat_files(
        settings=settings,
        s3_client=_S3Client(forbidden_keys=forbidden),
    )

    quote = next(result for result in results if result.dataset == "quotes_v1")
    assert quote.status == "entitlement_unavailable"
    assert quote.http_status == 403


def test_massive_options_flatfile_probe_auth_and_missing_sample_paths(tmp_path: Path) -> None:
    bad_key = tmp_path / "bad-flatfile.key"
    bad_key.write_text("access-only\n", encoding="utf-8")
    bad_settings = Settings(massive_flat_file_key_file=str(bad_key))

    auth_result = probe_massive_options_flat_files(settings=bad_settings)

    assert auth_result[0].status == "auth_failed"

    good_key = tmp_path / "good-flatfile.key"
    good_key.write_text("access\nsecret\n", encoding="utf-8")
    settings = Settings(massive_flat_file_key_file=str(good_key))

    missing = probe_massive_options_flat_files(
        settings=settings,
        s3_client=_S3MissingSampleClient(),
    )

    assert {result.status for result in missing} == {"sample_unavailable"}


def test_massive_options_flatfile_probe_list_error_and_status_classifier() -> None:
    result = _probe_options_dataset(
        client=_S3ListFailureClient(),
        dataset="day_aggs_v1",
        sample_date="2026-01-05",
    )

    assert result.status == "entitlement_unavailable"
    assert result.http_status == 403
    assert _classify_flatfile_status(404) == "sample_unavailable"
    assert _classify_flatfile_status(429) == "rate_limited"
    assert _classify_flatfile_status(503) == "vendor_5xx"
    assert _classify_flatfile_status(None) == "network_error"


def test_massive_options_flatfile_probe_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = MassiveFlatFileDatasetProbe(
        dataset="sample",
        status="ok",
        detail="",
        header_fields=("ticker", "implied_volatility"),
    )
    assert probe.has_direct_iv_greeks_oi is True

    def fake_import_module(name: str) -> object:
        if name == "boto3":
            return _FakeBoto3()
        if name == "botocore.config":
            return _FakeBotocoreConfig
        raise AssertionError(name)

    monkeypatch.setattr(
        "n225_open_gap_tail.sources.massive_flatfiles.importlib.import_module",
        fake_import_module,
    )
    client = massive_flatfiles._build_s3_client(access_key="access", secret_key="secret")

    assert client["endpoint_url"] == "https://files.massive.com"


def test_massive_options_flatfile_probe_status_is_optional_by_default() -> None:
    settings = Settings(
        massive_options_historical_enabled=False,
        massive_options_flat_files_enabled=False,
    )
    enabled = Settings(
        massive_options_historical_enabled=True,
        massive_options_flat_files_enabled=True,
    )

    assert (
        source_probe._flatfile_probe_status(
            settings=settings,
            status="entitlement_unavailable",
        )
        == "optional_entitlement_unavailable"
    )
    assert (
        source_probe._flatfile_probe_status(
            settings=enabled,
            status="entitlement_unavailable",
        )
        == "entitlement_unavailable"
    )


def test_csv_probe_handles_fetch_failure() -> None:
    def fail() -> int:
        raise RuntimeError("bad csv")

    result = source_probe._csv_probe("fred", fail)

    assert result.status == "network_error"
    assert result.detail == "bad csv"
