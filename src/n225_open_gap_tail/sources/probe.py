from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.sources.cboe import CboeClient
from n225_open_gap_tail.sources.fred import FredClient
from n225_open_gap_tail.sources.jquants import JQuantsApiError, JQuantsV2Client
from n225_open_gap_tail.sources.massive import MassiveApiError, MassiveClient


@dataclass(frozen=True)
class SourceProbeResult:
    source: str
    status: str
    detail: str
    http_status: int | None = None


def probe_sources(settings: Settings) -> list[SourceProbeResult]:
    """Check source reachability without downloading the full research history."""
    return [
        _probe_jquants(settings),
        _probe_massive(settings),
        _probe_fred(settings),
        _probe_cboe(settings),
    ]


def _classify_http_status(status_code: int | None) -> str:
    if status_code == 429:
        return "rate_limited"
    if status_code is not None and status_code >= 500:
        return "vendor_5xx"
    if status_code in {401, 403}:
        return "entitlement_unavailable"
    if status_code is not None and 200 <= status_code < 300:
        return "ok"
    return "network_error"


def _exception_result(source: str, exc: BaseException) -> SourceProbeResult:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return SourceProbeResult(
            source=source,
            status=_classify_http_status(status_code),
            detail=str(exc),
            http_status=status_code,
        )
    return SourceProbeResult(source=source, status="network_error", detail=str(exc))


def _probe_jquants(settings: Settings) -> SourceProbeResult:
    try:
        api_key = settings.read_jquants_api_key()
        with JQuantsV2Client(
            api_key=api_key,
            base_url=settings.jquants_api_base_url,
            timeout_seconds=settings.jquants_request_timeout_seconds,
        ) as client:
            payload = client.probe_endpoint(
                name="futures_daily_probe",
                path="/derivatives/bars/daily/futures",
                params={"date": "2026-01-05"},
            )
        return SourceProbeResult(
            "jquants",
            _classify_http_status(payload.http_status),
            f"futures_daily_probe rows={payload.row_count}",
            payload.http_status,
        )
    except ValueError as exc:
        return SourceProbeResult("jquants", "auth_failed", str(exc))
    except JQuantsApiError as exc:
        return _exception_result("jquants", exc)
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return _exception_result("jquants", exc)


def _probe_massive(settings: Settings) -> SourceProbeResult:
    try:
        api_key = settings.read_massive_api_key()
        with MassiveClient(
            api_key=api_key,
            base_url=settings.massive_base_url,
            timeout_seconds=settings.massive_request_timeout_seconds,
            min_request_interval_seconds=settings.massive_min_request_interval_seconds,
            max_retries=0,
            rate_limit_backoff_seconds=0.0,
        ) as client:
            payload = client.fetch_aggregate_bars(
                name="spy_daily_probe",
                ticker="SPY",
                multiplier=1,
                timespan="day",
                start="2026-01-05",
                end="2026-01-05",
                raise_for_status=False,
            )
        return SourceProbeResult(
            "massive",
            _classify_http_status(payload.http_status),
            f"SPY day rows={payload.row_count}",
            payload.http_status,
        )
    except ValueError as exc:
        return SourceProbeResult("massive", "auth_failed", str(exc))
    except MassiveApiError as exc:
        return _exception_result("massive", exc)
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return _exception_result("massive", exc)


def _csv_probe(
    source: str,
    fetch: Callable[[], int],
) -> SourceProbeResult:
    try:
        rows = fetch()
        return SourceProbeResult(source, "ok", f"csv rows={rows}", 200)
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return _exception_result(source, exc)


def _probe_fred(settings: Settings) -> SourceProbeResult:
    def fetch() -> int:
        with FredClient(
            base_url=settings.fred_base_url,
            timeout_seconds=settings.fred_request_timeout_seconds,
        ) as client:
            payload = client.fetch_series_csv("VIXCLS")
        return len(payload.rows)

    return _csv_probe("fred", fetch)


def _probe_cboe(settings: Settings) -> SourceProbeResult:
    def fetch() -> int:
        with CboeClient(
            base_url=settings.cboe_base_url,
            timeout_seconds=settings.cboe_request_timeout_seconds,
        ) as client:
            payload = client.fetch_vol_index_csv("VIX")
        return len(payload.rows)

    return _csv_probe("cboe", fetch)
