from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta


def _safe_name(value: str) -> str:  # pragma: no cover - vendor cache path
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _optional_text(value: object) -> str | None:  # pragma: no cover - vendor cache path
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:  # pragma: no cover
    current = date.fromisoformat(start).replace(day=1)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    while current <= end_date:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        chunk_start = max(date.fromisoformat(start), current)
        chunk_end = min(end_date, next_month - timedelta(days=1))
        chunks.append((chunk_start.isoformat(), chunk_end.isoformat()))
        current = next_month
    return chunks


def _coerce_datetime(value: object) -> datetime | None:  # pragma: no cover - vendor cache path
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _window_return(values: list[float], window: int) -> float | None:  # pragma: no cover
    if len(values) < window or len(values) < 2:
        return None
    start = values[-window]
    end = values[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _window_range(  # pragma: no cover - vendor cache path
    highs: list[float | None], lows: list[float | None]
) -> float | None:
    valid_highs = [value for value in highs if value is not None and value > 0]
    valid_lows = [value for value in lows if value is not None and value > 0]
    if not valid_highs or not valid_lows:
        return None
    high = max(valid_highs)
    low = min(valid_lows)
    if low <= 0:
        return None
    return math.log(high) - math.log(low)
