from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from n225_open_gap_tail.data_lake.io import read_verified_parquet_metadata


def _cache_covers_dates(path: Path, required_dates: list[str]) -> bool:
    metadata = read_verified_parquet_metadata(path)
    raw_dates = metadata.get("completed_dates")
    if raw_dates is None:
        if metadata.get("dataset") == "us_options_opra/day_aggs_v1":
            return False
        raw_dates = metadata.get("requested_dates")
    if not isinstance(raw_dates, list):
        return False
    available = {str(value) for value in raw_dates}
    return set(required_dates).issubset(available)


def _cache_covers_range(path: Path, start: str, end: str) -> bool:
    metadata = read_verified_parquet_metadata(path)
    return _metadata_covers_range(metadata, start, end)


def _metadata_covers_range(metadata: Mapping[str, object], start: str, end: str) -> bool:
    raw_range = metadata.get("requested_range")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        return False
    cached_start, cached_end = str(raw_range[0]), str(raw_range[1])
    return cached_start <= start and cached_end >= end
