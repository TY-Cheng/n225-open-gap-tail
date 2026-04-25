from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import exchange_calendars as xcals  # type: ignore[import-untyped]
import polars as pl

from n225_open_gap_tail.config import Settings

MONTH_CODES = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}


@dataclass(frozen=True)
class ContractMetadataResult:
    metadata_path: Path
    contracts_path: Path
    selector_path: Path
    contracts: int
    selector_rows: int
    roll_window_rows: int


def build_nikkei_contract_records(
    *,
    start: str,
    end: str,
    jpx_exchange: str,
    contract_months: tuple[int, ...],
    roll_days_before_last_trade: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    calendar = xcals.get_calendar(jpx_exchange)
    session_end_date = min(date(end_date.year + 1, 12, 31), _calendar_last_session_date(calendar))
    session_dates = _session_dates(
        calendar,
        date(start_date.year - 1, 1, 1),
        session_end_date,
    )
    contract_records = _contract_records(
        years=range(start_date.year - 1, end_date.year + 3),
        contract_months=contract_months,
        jpx_sessions=session_dates,
        roll_days_before_last_trade=roll_days_before_last_trade,
    )
    selector_records = _central_contract_records(
        start_date=start_date,
        end_date=end_date,
        jpx_sessions=session_dates,
        contract_records=contract_records,
    )
    return contract_records, selector_records


def write_contract_metadata(
    *,
    settings: Settings,
    start: str,
    end: str,
) -> ContractMetadataResult:
    contract_records, selector_records = build_nikkei_contract_records(
        start=start,
        end=end,
        jpx_exchange=settings.calendar_jpx_exchange,
        contract_months=settings.nikkei_contract_month_list(),
        roll_days_before_last_trade=settings.nikkei_contract_roll_days_before_last_trade,
    )

    raw_dir = settings.raw_data_dir / "contracts"
    interim_dir = settings.interim_data_dir / "contracts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = raw_dir / f"nikkei_futures_contract_metadata_{start}_{end}.json"
    contracts_path = interim_dir / f"nikkei_futures_contracts_{start}_{end}.parquet"
    selector_path = interim_dir / f"nikkei_futures_central_contract_{start}_{end}.parquet"

    metadata = {
        "source": "rule_based_contract_metadata",
        "jpx_exchange_calendar": settings.calendar_jpx_exchange,
        "product": "OSE Nikkei 225 Futures large contract",
        "start": start,
        "end": end,
        "contract_months": list(settings.nikkei_contract_month_list()),
        "roll_days_before_last_trade": settings.nikkei_contract_roll_days_before_last_trade,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "note": (
            "This is deterministic research scaffolding based on quarterly contract months, "
            "second-Friday SQ dates, and JPX calendar-adjusted last trading days. "
            "It must be reconciled against J-Quants or JPX contract metadata before final results."
        ),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    pl.DataFrame(contract_records).write_parquet(contracts_path)
    pl.DataFrame(selector_records).write_parquet(selector_path)

    return ContractMetadataResult(
        metadata_path=metadata_path,
        contracts_path=contracts_path,
        selector_path=selector_path,
        contracts=len(contract_records),
        selector_rows=len(selector_records),
        roll_window_rows=sum(1 for row in selector_records if row["is_roll_window"] is True),
    )


def _contract_records(
    *,
    years: range,
    contract_months: tuple[int, ...],
    jpx_sessions: list[date],
    roll_days_before_last_trade: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for year in years:
        for month in contract_months:
            sq_date = _second_friday(year, month)
            if sq_date > jpx_sessions[-1]:
                continue
            last_trading_date = _previous_session(sq_date, jpx_sessions)
            roll_start_date = _roll_start_session(
                last_trading_date,
                jpx_sessions,
                roll_days_before_last_trade,
            )
            month_code = MONTH_CODES[month]
            records.append(
                {
                    "source": "rule_based_contract_metadata",
                    "product": "OSE_NIKKEI_225_FUTURES_LARGE",
                    "contract_id": f"N225F_{year}{month:02d}",
                    "contract_year": year,
                    "contract_month": month,
                    "month_code": month_code,
                    "year_month_code": f"{month_code}{str(year)[-2:]}",
                    "sq_date": sq_date.isoformat(),
                    "last_trading_date": last_trading_date.isoformat(),
                    "roll_start_date": roll_start_date.isoformat(),
                    "roll_days_before_last_trade": roll_days_before_last_trade,
                    "central_selection_rule": "front_contract_until_roll_start_else_next",
                    "needs_vendor_reconciliation": True,
                }
            )
    records.sort(key=lambda row: (str(row["last_trading_date"]), str(row["contract_id"])))
    return records


def _central_contract_records(
    *,
    start_date: date,
    end_date: date,
    jpx_sessions: list[date],
    contract_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    trading_dates = [session for session in jpx_sessions if start_date <= session <= end_date]

    for trading_date in trading_dates:
        live_contracts = [
            contract
            for contract in contract_records
            if date.fromisoformat(str(contract["last_trading_date"])) >= trading_date
        ]
        if not live_contracts:
            continue
        front_contract = live_contracts[0]
        front_roll_start = date.fromisoformat(str(front_contract["roll_start_date"]))
        in_roll_window = (
            front_roll_start
            <= trading_date
            <= date.fromisoformat(str(front_contract["last_trading_date"]))
        )
        central_contract = (
            live_contracts[1] if in_roll_window and len(live_contracts) > 1 else front_contract
        )
        records.append(
            {
                "source": "rule_based_contract_metadata",
                "session_date": trading_date.isoformat(),
                "front_contract_id": front_contract["contract_id"],
                "front_contract_month": front_contract["contract_month"],
                "front_last_trading_date": front_contract["last_trading_date"],
                "front_roll_start_date": front_contract["roll_start_date"],
                "central_contract_id": central_contract["contract_id"],
                "central_contract_month": central_contract["contract_month"],
                "central_last_trading_date": central_contract["last_trading_date"],
                "is_roll_window": in_roll_window,
                "days_to_front_last_trade": (
                    date.fromisoformat(str(front_contract["last_trading_date"])) - trading_date
                ).days,
                "needs_vendor_reconciliation": True,
            }
        )
    return records


def _session_dates(calendar: Any, start_date: date, end_date: date) -> list[date]:
    sessions = calendar.sessions_in_range(start_date.isoformat(), end_date.isoformat())
    return [session.date() for session in sessions]


def _calendar_last_session_date(calendar: Any) -> date:
    last_session = calendar.last_session
    last_session_date = last_session.date()
    if not isinstance(last_session_date, date):
        raise TypeError("Expected exchange calendar last_session to expose a date")
    return last_session_date


def _second_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    days_to_first_friday = (4 - first_day.weekday()) % 7
    return first_day + timedelta(days=days_to_first_friday + 7)


def _previous_session(target_date: date, sessions: list[date]) -> date:
    candidates = [session for session in sessions if session < target_date]
    if not candidates:
        raise ValueError(f"No JPX session before {target_date.isoformat()}")
    return candidates[-1]


def _roll_start_session(
    last_trading_date: date,
    sessions: list[date],
    roll_days_before_last_trade: int,
) -> date:
    if roll_days_before_last_trade < 1:
        raise ValueError("roll_days_before_last_trade must be positive")
    session_index = sessions.index(last_trading_date)
    roll_start_index = max(0, session_index - roll_days_before_last_trade + 1)
    return sessions[roll_start_index]
