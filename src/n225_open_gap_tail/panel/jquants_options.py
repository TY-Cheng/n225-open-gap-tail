# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

import n225_open_gap_tail.data_lake.cache_ops as cache_ops
from n225_open_gap_tail.config.runtime import datetime, Settings, _pipeline_log
from n225_open_gap_tail.features.n225_options import (
    build_n225_option_feature_records,
    write_jquants_options_silver_cache,
)
from n225_open_gap_tail.sources.jquants_options import normalize_jquants_nikkei225_option_rows


def prepare_n225_option_features(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    run_start_utc: datetime,
    downloaded_at_utc: datetime,
    force_refresh: bool = False,
) -> list[dict[str, object]]:
    _pipeline_log("J-Quants Nikkei 225 options bronze fetch/cache start")
    raw_rows = cache_ops._fetch_jquants_nikkei_option_rows(
        settings=settings,
        start=start,
        end=end,
        calendar_records=calendar_records,
        run_start_utc=run_start_utc,
        force_refresh=force_refresh,
    )
    _pipeline_log(f"J-Quants Nikkei 225 option rows available: {len(raw_rows)}")
    normalized = normalize_jquants_nikkei225_option_rows(
        raw_rows,
        downloaded_at_utc=downloaded_at_utc,
    )
    write_jquants_options_silver_cache(settings=settings, rows=normalized)
    features = build_n225_option_feature_records(normalized)
    _pipeline_log(f"N225 option feature dates built: {len(features)}")
    return features
