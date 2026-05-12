from __future__ import annotations

from datetime import datetime

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake.massive_options_cache import fetch_massive_options_day_agg_rows
from n225_open_gap_tail.features.us_options import (
    UsOptionsAtmIvBuildResult,
    build_us_options_atm_iv_feature_records,
)


def prepare_us_options_atm_iv_features(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    downloaded_at_utc: datetime,
    force_refresh: bool = False,
) -> UsOptionsAtmIvBuildResult:
    option_rows = fetch_massive_options_day_agg_rows(
        settings=settings,
        start=start,
        end=end,
        calendar_records=calendar_records,
        downloaded_at_utc=downloaded_at_utc,
        force_refresh=force_refresh,
    )
    return build_us_options_atm_iv_feature_records(
        option_rows=option_rows,
        massive_daily_records=massive_daily_records,
        fred_records=fred_records,
        calendar_records=calendar_records,
    )


__all__ = [name for name in globals() if not name.startswith("_")]
