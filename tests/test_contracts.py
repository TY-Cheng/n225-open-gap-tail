from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.contracts import build_nikkei_contract_records, write_contract_metadata


def test_build_nikkei_contract_records_selects_central_contract_around_roll() -> None:
    contracts, selector = build_nikkei_contract_records(
        start="2026-03-02",
        end="2026-03-13",
        jpx_exchange="JPX",
        contract_months=(3, 6, 9, 12),
        roll_days_before_last_trade=5,
    )
    march_contract = next(row for row in contracts if row["contract_id"] == "N225F_202603")
    by_date = {str(row["session_date"]): row for row in selector}

    assert march_contract["sq_date"] == "2026-03-13"
    assert march_contract["last_trading_date"] == "2026-03-12"
    assert march_contract["roll_start_date"] == "2026-03-06"
    assert by_date["2026-03-05"]["central_contract_id"] == "N225F_202603"
    assert by_date["2026-03-06"]["central_contract_id"] == "N225F_202606"
    assert by_date["2026-03-06"]["is_roll_window"] is True
    assert by_date["2026-03-13"]["front_contract_id"] == "N225F_202606"


def test_write_contract_metadata_writes_contract_and_selector_tables(tmp_path: Path) -> None:
    settings = Settings(
        raw_data_dir=tmp_path / "raw",
        interim_data_dir=tmp_path / "interim",
        nikkei_contract_roll_days_before_last_trade=5,
    )

    result = write_contract_metadata(settings=settings, start="2026-01-01", end="2026-12-31")
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    contracts = pl.read_parquet(result.contracts_path)
    selector = pl.read_parquet(result.selector_path)

    assert metadata["source"] == "rule_based_contract_metadata"
    assert result.contracts >= 9
    assert result.selector_rows > 200
    assert result.roll_window_rows > 0
    assert contracts.filter(pl.col("contract_id") == "N225F_202603").height == 1
    assert selector.select("central_contract_id").null_count().item() == 0
