from __future__ import annotations

import importlib
import math
import os
import re
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from n225_open_gap_tail.config import Settings

MASSIVE_FLATFILES_ENDPOINT = "https://files.massive.com"
MASSIVE_FLATFILES_BUCKET = "flatfiles"
MASSIVE_OPTIONS_DATASETS: tuple[str, ...] = (
    "day_aggs_v1",
    "minute_aggs_v1",
    "trades_v1",
    "quotes_v1",
)
MASSIVE_OPTIONS_PREFIX = "us_options_opra"
MASSIVE_OPTIONS_SAMPLE_DATE = "2026-01-05"
_DIRECT_OPTION_STATE_FIELDS = {
    "implied_volatility",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "open_interest",
}
_OPRA_RE = re.compile(r"^(?P<expiry>\d{6})(?P<option_type>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True)
class ParsedOpraOptionTicker:
    ticker: str
    underlying: str
    expiration_date: str
    option_type: str
    strike: float


@dataclass(frozen=True)
class MassiveFlatFileDatasetProbe:
    dataset: str
    status: str
    detail: str
    http_status: int | None = None
    sample_key: str | None = None
    header_fields: tuple[str, ...] = ()

    @property
    def has_direct_iv_greeks_oi(self) -> bool:
        return bool(_DIRECT_OPTION_STATE_FIELDS.intersection(self.header_fields))


def parse_opra_option_ticker(
    ticker: str,
    *,
    underlyings: tuple[str, ...],
) -> ParsedOpraOptionTicker | None:
    """Parse a standard Massive OPRA ticker for a configured underlying."""

    text = ticker.removeprefix("O:").upper()
    for underlying in sorted({item.upper() for item in underlyings}, key=len, reverse=True):
        if not text.startswith(underlying):
            continue
        match = _OPRA_RE.fullmatch(text[len(underlying) :])
        if match is None:
            continue
        expiry_raw = match.group("expiry")
        expiry_year = 2000 + int(expiry_raw[:2])
        try:
            expiry = date(expiry_year, int(expiry_raw[2:4]), int(expiry_raw[4:6]))
        except ValueError:
            return None
        strike = int(match.group("strike")) / 1000.0
        return ParsedOpraOptionTicker(
            ticker=f"O:{text}",
            underlying=underlying,
            expiration_date=expiry.isoformat(),
            option_type=match.group("option_type"),
            strike=strike,
        )
    return None


def normalize_massive_options_day_agg_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    bar_date_et: str,
    underlyings: tuple[str, ...],
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    bar_date = date.fromisoformat(bar_date_et)
    for row in rows:
        parsed = parse_opra_option_ticker(str(row.get("ticker") or ""), underlyings=underlyings)
        if parsed is None:
            continue
        expiry = date.fromisoformat(parsed.expiration_date)
        dte = (expiry - bar_date).days
        output.append(
            {
                "bar_date_et": bar_date_et,
                "ticker": parsed.ticker,
                "underlying": parsed.underlying,
                "expiration_date": parsed.expiration_date,
                "option_type": parsed.option_type,
                "strike": parsed.strike,
                "dte": dte,
                "volume": _optional_float(row.get("volume")),
                "open": _optional_float(row.get("open")),
                "close": _optional_float(row.get("close")),
                "high": _optional_float(row.get("high")),
                "low": _optional_float(row.get("low")),
                "transactions": _optional_float(row.get("transactions")),
                "window_start": (
                    None if row.get("window_start") is None else str(row["window_start"])
                ),
                "research_download_ts_utc": downloaded_at_utc,
            }
        )
    return output


def parse_massive_flat_file_credentials(raw_secret: str) -> tuple[str, str]:
    """Parse Massive S3 flat-file credentials from the key-file payload."""

    lines = tuple(line.strip() for line in raw_secret.splitlines() if line.strip())
    if len(lines) >= 2:
        return lines[0], lines[1]

    compact = raw_secret.strip()
    for delimiter in (":", ","):
        if delimiter in compact:
            access_key, secret_key = (part.strip() for part in compact.split(delimiter, 1))
            if access_key and secret_key:
                return access_key, secret_key

    raise ValueError(
        "MASSIVE_FLAT_FILE_KEY_FILE must contain S3 access and secret keys "
        "as two lines, access:secret, or access,secret"
    )


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def probe_massive_options_flat_files(
    *,
    settings: Settings,
    sample_date: str = MASSIVE_OPTIONS_SAMPLE_DATE,
    s3_client: Any | None = None,
) -> list[MassiveFlatFileDatasetProbe]:
    """Probe Massive options flat-file availability without downloading full files."""

    if not settings.massive_flat_file_key_file:
        return []

    try:
        access_key, secret_key = parse_massive_flat_file_credentials(
            settings.read_massive_flat_file_key()
        )
    except ValueError as exc:
        return [
            MassiveFlatFileDatasetProbe(
                dataset="options_flatfiles",
                status="auth_failed",
                detail=str(exc),
            )
        ]

    client = s3_client or _build_s3_client(access_key=access_key, secret_key=secret_key)
    return [
        _probe_options_dataset(client=client, dataset=dataset, sample_date=sample_date)
        for dataset in MASSIVE_OPTIONS_DATASETS
    ]


def _build_s3_client(*, access_key: str, secret_key: str) -> Any:
    boto3 = importlib.import_module("boto3")
    botocore_config = importlib.import_module("botocore.config")
    return boto3.client(
        "s3",
        endpoint_url=MASSIVE_FLATFILES_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=botocore_config.Config(signature_version="s3v4"),
    )


def build_massive_flatfiles_s3_client(*, settings: Settings) -> Any:
    """Build an S3-compatible Massive flat-file client from key-file credentials."""

    access_key, secret_key = parse_massive_flat_file_credentials(
        settings.read_massive_flat_file_key()
    )
    return _build_s3_client(access_key=access_key, secret_key=secret_key)


def massive_options_day_aggs_key(day: str) -> str:
    year, month, _ = day.split("-")
    return f"{MASSIVE_OPTIONS_PREFIX}/day_aggs_v1/{year}/{month}/{day}.csv.gz"


def download_massive_options_day_aggs_file(
    *,
    client: Any,
    destination: Path,
    day: str,
) -> Path:
    """Download a Massive OPRA day-aggs flat file if it is not already cached."""

    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(f"{destination.name}.tmp.{os.getpid()}")
    try:
        response = client.get_object(
            Bucket=MASSIVE_FLATFILES_BUCKET,
            Key=massive_options_day_aggs_key(day),
        )
        tmp_path.write_bytes(response["Body"].read())
        os.replace(tmp_path, destination)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return destination


def _probe_options_dataset(
    *,
    client: Any,
    dataset: str,
    sample_date: str,
) -> MassiveFlatFileDatasetProbe:
    year, month, _day = sample_date.split("-")
    prefix = f"{MASSIVE_OPTIONS_PREFIX}/{dataset}/{year}/{month}/"
    sample_key = f"{prefix}{sample_date}.csv.gz"
    try:
        response = client.list_objects_v2(
            Bucket=MASSIVE_FLATFILES_BUCKET,
            Prefix=prefix,
            MaxKeys=100,
        )
    except Exception as exc:
        return _probe_error(dataset=dataset, exc=exc, stage="list_prefix")

    keys = tuple(
        obj.get("Key")
        for obj in response.get("Contents", [])
        if isinstance(obj, Mapping) and isinstance(obj.get("Key"), str)
    )
    if sample_key not in keys:
        return MassiveFlatFileDatasetProbe(
            dataset=dataset,
            status="sample_unavailable",
            detail=f"prefix_listed={prefix} sample_key_missing={sample_key}",
            sample_key=sample_key,
        )

    try:
        header_fields = _read_gzip_csv_header(client=client, key=sample_key)
    except Exception as exc:
        return _probe_error(dataset=dataset, exc=exc, stage="read_header", sample_key=sample_key)

    direct_fields = sorted(_DIRECT_OPTION_STATE_FIELDS.intersection(header_fields))
    direct_status = "true" if direct_fields else "false"
    return MassiveFlatFileDatasetProbe(
        dataset=dataset,
        status="ok",
        detail=(
            f"sample_key={sample_key} header={','.join(header_fields)} "
            f"direct_iv_greeks_oi={direct_status}"
        ),
        http_status=200,
        sample_key=sample_key,
        header_fields=header_fields,
    )


def _read_gzip_csv_header(*, client: Any, key: str) -> tuple[str, ...]:
    response = client.get_object(
        Bucket=MASSIVE_FLATFILES_BUCKET,
        Key=key,
        Range="bytes=0-1048575",
    )
    compressed = response["Body"].read()
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    text = decompressor.decompress(compressed).decode("utf-8", errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    return tuple(field.strip() for field in first_line.split(",") if field.strip())


def _probe_error(
    *,
    dataset: str,
    exc: Exception,
    stage: str,
    sample_key: str | None = None,
) -> MassiveFlatFileDatasetProbe:
    status_code = _exception_http_status(exc)
    status = _classify_flatfile_status(status_code)
    key_detail = f" sample_key={sample_key}" if sample_key else ""
    return MassiveFlatFileDatasetProbe(
        dataset=dataset,
        status=status,
        detail=f"{stage}{key_detail}: {type(exc).__name__}: {str(exc)[:240]}",
        http_status=status_code,
        sample_key=sample_key,
    )


def _exception_http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        metadata = response.get("ResponseMetadata")
        if isinstance(metadata, Mapping):
            status_code = metadata.get("HTTPStatusCode")
            if isinstance(status_code, int):
                return status_code
    return None


def _classify_flatfile_status(status_code: int | None) -> str:
    if status_code in {401, 403}:
        return "entitlement_unavailable"
    if status_code == 404:
        return "sample_unavailable"
    if status_code == 429:
        return "rate_limited"
    if status_code is not None and status_code >= 500:
        return "vendor_5xx"
    return "network_error"
