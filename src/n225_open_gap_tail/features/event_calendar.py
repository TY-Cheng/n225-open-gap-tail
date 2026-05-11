from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from n225_open_gap_tail.config.runtime import PipelineRunError

EVENT_CALENDAR_FEATURES = (
    "event_fomc_same_us_session",
    "event_cpi_same_us_session",
    "event_nfp_same_us_session",
    "event_boj_same_ose_session",
    "event_major_count_next_3d",
    "event_days_to_next_major",
    "event_days_since_previous_major",
)

EVENT_TYPES = {"fomc", "cpi", "nfp", "boj"}
AFFECTS_SESSIONS = {"us", "ose"}
EVENT_RESOURCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "event_calendar.csv"


@dataclass(frozen=True)
class EventCalendarRecord:
    event_date: date
    event_type: str
    event_name: str
    affects_session: str
    release_ts_utc: datetime | None
    known_ts_utc: datetime | None
    source_note: str


def load_event_calendar(path: Path | None = None) -> list[EventCalendarRecord]:
    """Load the tracked static event calendar and fail closed on malformed rows."""
    csv_path = path or EVENT_RESOURCE_PATH
    if not csv_path.exists():
        return []
    rows: list[EventCalendarRecord] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = {
            "event_date",
            "event_type",
            "event_name",
            "affects_session",
            "release_ts_utc",
            "known_ts_utc",
            "source_note",
        }
        missing = expected.difference(reader.fieldnames or ())
        if missing:
            raise PipelineRunError(f"Event calendar missing columns: {sorted(missing)}")
        for index, row in enumerate(reader, start=2):
            rows.append(_parse_event_row(row, row_number=index, source_path=csv_path))
    return sorted(rows, key=lambda row: (row.event_date, row.event_type, row.event_name))


def add_event_calendar_features(
    panel_rows: list[dict[str, object]],
    event_records: list[EventCalendarRecord] | None = None,
) -> list[dict[str, object]]:
    """Add clean scheduled-event controls with timestamp-safe availability."""
    events = event_records if event_records is not None else load_event_calendar()
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    output: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        cutoff = _coerce_datetime(enriched.get("model_cutoff_ts_utc"))
        forecast_date = _parse_date(enriched.get("forecast_date"))
        us_date = _parse_date(enriched.get("us_calendar_date"))
        _stamp_same_us_session(enriched, events, cutoff=cutoff, us_date=us_date)
        _stamp_same_ose_session(enriched, events, cutoff=cutoff, forecast_date=forecast_date)
        _stamp_event_intensity(enriched, events, cutoff=cutoff, forecast_date=forecast_date)
        output.append(enriched)
    return output


def _parse_event_row(
    row: dict[str, str | None],
    *,
    row_number: int,
    source_path: Path,
) -> EventCalendarRecord:
    try:
        event_date = date.fromisoformat(str(row.get("event_date") or ""))
    except ValueError as exc:
        raise PipelineRunError(
            f"Malformed event_date in {source_path}:{row_number}: {row.get('event_date')!r}"
        ) from exc
    event_type = str(row.get("event_type") or "").strip().lower()
    if event_type not in EVENT_TYPES:
        raise PipelineRunError(
            f"Malformed event_type in {source_path}:{row_number}: {event_type!r}"
        )
    affects_session = str(row.get("affects_session") or "").strip().lower()
    if affects_session not in AFFECTS_SESSIONS:
        raise PipelineRunError(
            f"Malformed affects_session in {source_path}:{row_number}: {affects_session!r}"
        )
    return EventCalendarRecord(
        event_date=event_date,
        event_type=event_type,
        event_name=str(row.get("event_name") or "").strip(),
        affects_session=affects_session,
        release_ts_utc=_parse_datetime(row.get("release_ts_utc")),
        known_ts_utc=_parse_datetime(row.get("known_ts_utc")),
        source_note=str(row.get("source_note") or "").strip(),
    )


def _stamp_same_us_session(
    row: dict[str, object],
    events: list[EventCalendarRecord],
    *,
    cutoff: datetime | None,
    us_date: date | None,
) -> None:
    for event_type, feature_name in (
        ("fomc", "event_fomc_same_us_session"),
        ("cpi", "event_cpi_same_us_session"),
        ("nfp", "event_nfp_same_us_session"),
    ):
        matches = [
            event
            for event in events
            if event.event_type == event_type
            and event.affects_session == "us"
            and event.event_date == us_date
            and event.release_ts_utc is not None
            and cutoff is not None
            and event.release_ts_utc <= cutoff
        ]
        _stamp_event_feature(
            row,
            feature_name,
            1.0 if matches else 0.0,
            matches[:1],
            availability_field="release",
            fallback_available_ts=cutoff,
            fallback_source_date=None if us_date is None else us_date.isoformat(),
        )


def _stamp_same_ose_session(
    row: dict[str, object],
    events: list[EventCalendarRecord],
    *,
    cutoff: datetime | None,
    forecast_date: date | None,
) -> None:
    matches = [
        event
        for event in events
        if event.event_type == "boj"
        and event.affects_session == "ose"
        and event.event_date == forecast_date
        and _known_by_cutoff(event, cutoff)
    ]
    _stamp_event_feature(
        row,
        "event_boj_same_ose_session",
        1.0 if matches else 0.0,
        matches[:1],
        fallback_available_ts=cutoff,
        fallback_source_date=None if forecast_date is None else forecast_date.isoformat(),
    )


def _stamp_event_intensity(
    row: dict[str, object],
    events: list[EventCalendarRecord],
    *,
    cutoff: datetime | None,
    forecast_date: date | None,
) -> None:
    if forecast_date is None:
        for feature in (
            "event_major_count_next_3d",
            "event_days_to_next_major",
            "event_days_since_previous_major",
        ):
            _stamp_event_feature(row, feature, None, [])
        return
    known_events = [event for event in events if _known_by_cutoff(event, cutoff)]
    future_events = [
        event for event in known_events if 0 <= (event.event_date - forecast_date).days <= 3
    ]
    next_events = [event for event in known_events if (event.event_date - forecast_date).days >= 0]
    previous_events = [
        event for event in known_events if (forecast_date - event.event_date).days > 0
    ]
    next_event = min(next_events, key=lambda event: event.event_date, default=None)
    previous_event = max(previous_events, key=lambda event: event.event_date, default=None)
    _stamp_event_feature(
        row,
        "event_major_count_next_3d",
        float(len(future_events)),
        future_events,
        fallback_available_ts=cutoff,
        fallback_source_date=forecast_date.isoformat(),
    )
    _stamp_event_feature(
        row,
        "event_days_to_next_major",
        None
        if next_event is None
        else float(min((next_event.event_date - forecast_date).days, 30)),
        [] if next_event is None else [next_event],
    )
    _stamp_event_feature(
        row,
        "event_days_since_previous_major",
        None
        if previous_event is None
        else float(min((forecast_date - previous_event.event_date).days, 30)),
        [] if previous_event is None else [previous_event],
    )


def _stamp_event_feature(
    row: dict[str, object],
    feature_name: str,
    value: object,
    events: list[EventCalendarRecord],
    *,
    availability_field: str = "known",
    fallback_available_ts: datetime | None = None,
    fallback_source_date: str | None = None,
) -> None:
    row[feature_name] = value
    row[f"{feature_name}__fill_method"] = "static_event_calendar"
    available_values = [
        timestamp
        for event in events
        if (timestamp := _event_availability_ts(event, availability_field)) is not None
    ]
    if available_values:
        row[f"{feature_name}__available_ts_utc"] = max(available_values)
        row[f"{feature_name}__source_date"] = max(event.event_date.isoformat() for event in events)
    elif value is not None and fallback_available_ts is not None:
        row[f"{feature_name}__available_ts_utc"] = fallback_available_ts
        if fallback_source_date is not None:
            row[f"{feature_name}__source_date"] = fallback_source_date


def _event_availability_ts(event: EventCalendarRecord, availability_field: str) -> datetime | None:
    if availability_field == "release":
        return event.release_ts_utc
    return event.known_ts_utc or event.release_ts_utc


def _known_by_cutoff(event: EventCalendarRecord, cutoff: datetime | None) -> bool:
    return event.known_ts_utc is not None and cutoff is not None and event.known_ts_utc <= cutoff


def _parse_date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PipelineRunError(f"Malformed event timestamp: {text!r}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None
