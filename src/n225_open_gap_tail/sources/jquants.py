from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake import write_json_atomic

JQUANTS_REQUIRED_PLAN = "premium"


class JQuantsApiError(RuntimeError):
    """Raised when a J-Quants request fails unexpectedly."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EndpointPayload:
    name: str
    path: str
    params: dict[str, str]
    http_status: int
    ok: bool
    row_count: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class JQuantsSmokeResult:
    output_path: Path
    equity_master_rows: int
    equity_daily_rows: int
    futures_probe_status: int
    futures_probe_rows: int


class JQuantsV2Client:
    """Small V2 client for smoke tests and early data engineering."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.jquants.com/v2",
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise JQuantsApiError("J-Quants API key is required")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._headers = {
            "x-api-key": api_key,
            "User-Agent": "n225-open-gap-tail-jquants-v2",
        }

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JQuantsV2Client:
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
        response = self._client.get(
            f"{self._base_url}{path}",
            params=params or {},
            headers=self._headers,
        )
        payload = self._decode_payload(response)
        if raise_for_status and response.status_code >= 400:
            message = payload.get("message", "J-Quants request failed")
            raise JQuantsApiError(str(message), status_code=response.status_code)
        return response.status_code, payload

    def get_paginated(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        data_key: str = "data",
    ) -> list[dict[str, Any]]:
        query = dict(params or {})
        rows: list[dict[str, Any]] = []

        while True:
            _, payload = self.request_json(path, query)
            batch = payload.get(data_key, [])
            if not isinstance(batch, list):
                raise JQuantsApiError(f"Expected list payload at {data_key!r}")
            rows.extend(_ensure_record_list(batch))

            pagination_key = payload.get("pagination_key")
            if not pagination_key:
                break
            query["pagination_key"] = str(pagination_key)

        return rows

    def get_equity_master(self, *, code: str = "") -> list[dict[str, Any]]:
        params = {"code": code} if code else {}
        return self.get_paginated("/equities/master", params)

    def get_equity_daily_bars(
        self,
        *,
        code: str = "",
        start: str = "",
        end: str = "",
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if code:
            params["code"] = code
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        return self.get_paginated("/equities/bars/daily", params)

    def get_futures_daily_bars(self, *, trading_date: str) -> list[dict[str, Any]]:
        """Fetch daily derivatives futures bars for one exchange trading date."""
        return self.get_paginated(
            "/derivatives/bars/daily/futures",
            {"date": trading_date},
        )

    def get_nikkei225_options_daily_bars(
        self,
        *,
        trading_date: str,
        category: str = "NK225E",
        contract_flag: str = "1",
    ) -> list[dict[str, Any]]:
        """Fetch daily Nikkei 225 large-option bars for one exchange trading date."""
        params = {"date": trading_date}
        if category:
            params["category"] = category
        if contract_flag:
            params["contract_flag"] = contract_flag
        return self.get_paginated("/derivatives/bars/daily/options/225", params)

    def probe_endpoint(
        self,
        *,
        name: str,
        path: str,
        params: dict[str, str],
    ) -> EndpointPayload:
        status_code, payload = self.request_json(path, params, raise_for_status=False)
        data = payload.get("data", [])
        row_count = len(data) if isinstance(data, list) else 0
        return EndpointPayload(
            name=name,
            path=path,
            params=dict(params),
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
            raise JQuantsApiError(
                "J-Quants response was not JSON",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise JQuantsApiError(
                "J-Quants response JSON was not an object",
                status_code=response.status_code,
            )
        return payload


def write_jquants_smoke_sample(
    *,
    settings: Settings,
    code: str,
    start: str,
    end: str,
    futures_date: str,
    client: JQuantsV2Client | None = None,
) -> JQuantsSmokeResult:
    should_close = client is None
    active_client = client or JQuantsV2Client(
        api_key=settings.read_jquants_api_key(),
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    )

    try:
        equity_master = active_client.get_equity_master(code=code)
        equity_daily = active_client.get_equity_daily_bars(code=code, start=start, end=end)
        futures_probe = active_client.probe_endpoint(
            name="futures_daily_probe",
            path="/derivatives/bars/daily/futures",
            params={"date": futures_date},
        )
    finally:
        if should_close:
            active_client.close()

    output_path = (
        settings.bronze_data_dir
        / "jquants_smoke"
        / "schema_version=1"
        / f"code={code}"
        / f"start={start}"
        / f"end={end}"
        / "payload.json"
    )

    document = {
        "metadata": {
            "source": "jquants",
            "api_base_url": settings.jquants_api_base_url,
            "required_plan": JQUANTS_REQUIRED_PLAN,
            "downloaded_at_utc": datetime.now(UTC).isoformat(),
            "note": "API key is intentionally excluded from this raw smoke artifact.",
        },
        "requests": [
            {
                "name": "equity_master",
                "path": "/equities/master",
                "params": {"code": code},
                "http_status": 200,
                "ok": True,
                "row_count": len(equity_master),
                "data": equity_master,
            },
            {
                "name": "equity_daily_bars",
                "path": "/equities/bars/daily",
                "params": {"code": code, "from": start, "to": end},
                "http_status": 200,
                "ok": True,
                "row_count": len(equity_daily),
                "data": equity_daily,
            },
            {
                "name": futures_probe.name,
                "path": futures_probe.path,
                "params": futures_probe.params,
                "http_status": futures_probe.http_status,
                "ok": futures_probe.ok,
                "row_count": futures_probe.row_count,
                "payload": futures_probe.payload,
            },
        ],
    }
    write_json_atomic(output_path, document)

    return JQuantsSmokeResult(
        output_path=output_path,
        equity_master_rows=len(equity_master),
        equity_daily_rows=len(equity_daily),
        futures_probe_status=futures_probe.http_status,
        futures_probe_rows=futures_probe.row_count,
    )


def _ensure_record_list(batch: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in batch:
        if not isinstance(row, dict):
            raise JQuantsApiError("J-Quants data row was not an object")
        records.append(row)
    return records
