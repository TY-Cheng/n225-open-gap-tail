from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from typing import cast

import polars as pl
import pytest

import n225_open_gap_tail.data_lake.cache_ops as cache_ops
import n225_open_gap_tail.panel.us_options as panel_us_options
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.config.runtime import build_feature_matrix_gate_records
from n225_open_gap_tail.data_lake.massive_options_cache import (
    massive_options_primary_underlyings,
)
from n225_open_gap_tail.features.asof import (
    _features_asof,
    _massive_daily_feature_map,
    _options_feature_map,
)
from n225_open_gap_tail.features.us_options import (
    black_scholes_price,
    build_us_options_atm_iv_feature_records,
    implied_volatility_from_price,
    normalize_massive_options_day_agg_rows,
    parse_opra_option_ticker,
)
from n225_open_gap_tail.panel.calendar_map import _calendar_mapping_status
from n225_open_gap_tail.panel.options_audit import (
    build_options_feature_coverage_records,
    build_options_liquidity_audit_records,
    build_options_source_audit_records,
)
from n225_open_gap_tail.sources.massive_flatfiles import (
    download_massive_options_day_aggs_file,
    massive_options_day_aggs_key,
)


def test_opra_ticker_parser_accepts_configured_underlyings_and_rejects_adjusted() -> None:
    underlyings = ("SPY", "EWJ", "SONY")

    spy = parse_opra_option_ticker("O:SPY260116C00100000", underlyings=underlyings)
    ewj = parse_opra_option_ticker("O:EWJ260116P00081840", underlyings=underlyings)
    sony = parse_opra_option_ticker("O:SONY260116C00025000", underlyings=underlyings)

    assert spy is not None
    assert spy.underlying == "SPY"
    assert spy.expiration_date == "2026-01-16"
    assert spy.option_type == "C"
    assert spy.strike == pytest.approx(100.0)
    assert ewj is not None and ewj.option_type == "P"
    assert sony is not None and sony.underlying == "SONY"
    assert parse_opra_option_ticker("O:CYU260116C00100000", underlyings=underlyings) is None
    assert parse_opra_option_ticker("O:SPY261332C00100000", underlyings=underlyings) is None


def test_black_scholes_implied_vol_solver_recovers_known_sigma() -> None:
    price = black_scholes_price(
        spot=100.0,
        strike=100.0,
        rate=0.04,
        time_to_expiry=30 / 365.25,
        sigma=0.25,
        option_type="C",
    )
    assert price is not None

    iv = implied_volatility_from_price(
        option_price=price,
        spot=100.0,
        strike=100.0,
        rate=0.04,
        time_to_expiry=30 / 365.25,
        option_type="C",
    )

    assert iv == pytest.approx(0.25, abs=1e-6)
    assert (
        implied_volatility_from_price(
            option_price=10_000.0,
            spot=100.0,
            strike=100.0,
            rate=0.04,
            time_to_expiry=30 / 365.25,
            option_type="C",
        )
        is None
    )
    assert (
        black_scholes_price(
            spot=100.0,
            strike=100.0,
            rate=0.04,
            time_to_expiry=30 / 365.25,
            sigma=0.25,
            option_type="X",
        )
        is None
    )
    assert (
        implied_volatility_from_price(
            option_price=1.0,
            spot=100.0,
            strike=100.0,
            rate=0.04,
            time_to_expiry=30 / 365.25,
            option_type="C",
            sigma_bounds=(-1.0, 5.0),
        )
        is None
    )


def test_us_options_feature_builder_computes_atm_iv_and_adr_aggregate() -> None:
    date_key = "2026-01-05"
    close_ts = datetime(2026, 1, 5, 21, tzinfo=UTC)
    downloaded = datetime(2026, 1, 5, 22, tzinfo=UTC)
    raw_rows = []
    for underlying, spot in (
        ("SPY", 100.0),
        ("XLK", 120.0),
        ("EEM", 50.0),
        ("EWJ", 80.0),
        ("TM", 200.0),
    ):
        for expiry, dte in (("260116", 11), ("260220", 46)):
            for option_type in ("C", "P"):
                price = black_scholes_price(
                    spot=spot,
                    strike=spot,
                    rate=0.04,
                    time_to_expiry=dte / 365.25,
                    sigma=0.20,
                    option_type=option_type,
                )
                raw_rows.append(
                    {
                        "ticker": f"O:{underlying}{expiry}{option_type}{int(spot * 1000):08d}",
                        "volume": "10",
                        "open": price,
                        "close": price,
                        "high": price,
                        "low": price,
                        "window_start": "0",
                        "transactions": "2",
                    }
                )
    option_rows = normalize_massive_options_day_agg_rows(
        raw_rows,
        bar_date_et=date_key,
        underlyings=("SPY", "XLK", "EEM", "EWJ", "TM"),
        downloaded_at_utc=downloaded,
    )

    result = build_us_options_atm_iv_feature_records(
        option_rows=option_rows,
        massive_daily_records=[
            {"ticker": "SPY", "bar_date_et": date_key, "close": 100.0},
            {"ticker": "XLK", "bar_date_et": date_key, "close": 120.0},
            {"ticker": "EEM", "bar_date_et": date_key, "close": 50.0},
            {"ticker": "EWJ", "bar_date_et": date_key, "close": 80.0},
            {"ticker": "TM", "bar_date_et": date_key, "close": 200.0},
        ],
        fred_records=[
            {
                "series_id": "DGS2",
                "observation_date": date_key,
                "value": 4.0,
                "vendor_available_date_et": date_key,
                "vendor_available_ts_utc": close_ts,
            }
        ],
        calendar_records=[{"calendar_date": date_key, "us_close_ts_utc": close_ts}],
    )

    row = result.feature_records[0]
    assert row["option_us_core_spy_atm_iv_short"] == pytest.approx(0.20, abs=1e-6)
    assert row["option_us_sector_median_atm_iv_short"] == pytest.approx(0.20, abs=1e-6)
    assert row["option_japan_etf_ewj_atm_iv_medium"] == pytest.approx(0.20, abs=1e-6)
    assert row["option_japan_adr_median_atm_iv_short"] == pytest.approx(0.20, abs=1e-6)
    assert row["option_asia_proxy_median_atm_iv_short"] == pytest.approx(0.20, abs=1e-6)
    assert row["option_asia_proxy_valid_underlying_count_short"] == pytest.approx(1.0)
    assert row["option_japan_adr_valid_underlying_count_short"] == pytest.approx(1.0)
    assert row["feature_available_ts_utc"] == close_ts + timedelta(minutes=30)
    assert len(result.liquidity_records) >= 6


def test_us_options_feature_builder_handles_missing_calendar_and_risk_free() -> None:
    downloaded = datetime(2026, 1, 5, 22, tzinfo=UTC)
    price = black_scholes_price(
        spot=100.0,
        strike=100.0,
        rate=0.04,
        time_to_expiry=11 / 365.25,
        sigma=0.20,
        option_type="C",
    )
    option_rows = normalize_massive_options_day_agg_rows(
        [
            {
                "ticker": "O:SPY260116C00100000",
                "volume": "10",
                "close": price,
                "transactions": "2",
            }
        ],
        bar_date_et="2026-01-05",
        underlyings=("SPY",),
        downloaded_at_utc=downloaded,
    )

    no_calendar = build_us_options_atm_iv_feature_records(
        option_rows=option_rows,
        massive_daily_records=[{"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0}],
        fred_records=[],
        calendar_records=[],
    )
    assert no_calendar.feature_records == []

    no_fred = build_us_options_atm_iv_feature_records(
        option_rows=option_rows,
        massive_daily_records=[{"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0}],
        fred_records=[],
        calendar_records=[
            {"calendar_date": "2026-01-05", "us_close_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC)}
        ],
    )
    assert no_fred.feature_records[0]["option_us_core_spy_atm_iv_short"] is None
    assert no_fred.feature_records[0]["option_japan_adr_median_atm_iv_short"] is None
    assert no_fred.liquidity_records[0]["risk_free_available"] is False


def test_options_asof_respects_cutoff_metadata() -> None:
    records = [
        {
            "bar_date_et": "2026-01-05",
            "feature_available_ts_utc": datetime(2026, 1, 5, 21, 15, tzinfo=UTC),
            "option_us_core_spy_atm_iv_short": 0.2,
        }
    ]
    mapped = _options_feature_map(records)

    assert (
        _features_asof(
            mapped,
            "2026-01-05",
            cutoff=datetime(2026, 1, 5, 21, 10, tzinfo=UTC),
            fill_method="forward_fill_us_holiday",
        )
        == {}
    )
    selected = _features_asof(
        mapped,
        "2026-01-05",
        cutoff=datetime(2026, 1, 5, 21, 20, tzinfo=UTC),
        fill_method="forward_fill_us_holiday",
    )
    assert selected["option_us_core_spy_atm_iv_short"] == pytest.approx(0.2)
    assert selected["option_us_core_spy_atm_iv_short__fill_method"] == "direct"

    null_exact = _options_feature_map(
        [
            {
                "bar_date_et": "2026-01-02",
                "feature_available_ts_utc": datetime(2026, 1, 2, 21, 20, tzinfo=UTC),
                "option_us_core_spy_atm_iv_short": 0.19,
            },
            {
                "bar_date_et": "2026-01-05",
                "feature_available_ts_utc": datetime(2026, 1, 5, 21, 20, tzinfo=UTC),
                "option_us_core_spy_atm_iv_short": None,
            },
        ]
    )
    selected_null = _features_asof(
        null_exact,
        "2026-01-05",
        cutoff=datetime(2026, 1, 5, 21, 30, tzinfo=UTC),
        fill_method="forward_fill_us_holiday",
    )
    assert selected_null["option_us_core_spy_atm_iv_short"] is None
    assert selected_null["option_us_core_spy_atm_iv_short__fill_method"] == "direct"


def test_options_missingness_gate_is_separate_from_core_features() -> None:
    frame = pl.DataFrame(
        {
            "option_us_core_spy_atm_iv_short": [0.2, None, 0.21, 0.22],
            "spy_return": [0.01, None, 0.02, 0.03],
        }
    )

    gate = build_feature_matrix_gate_records(
        frame,
        ["option_us_core_spy_atm_iv_short", "spy_return"],
    )

    active_features = cast(list[str], gate["active_features"])
    assert "option_us_core_spy_atm_iv_short" in active_features
    dropped = json.loads(str(gate["dropped_features_json"]))
    spy_drop = next(item for item in dropped if item["feature"] == "spy_return")
    assert spy_drop["drop_reason"] == "high_training_missingness"
    assert spy_drop["max_missingness"] == pytest.approx(0.20)


def test_options_underlying_helpers_are_gated_and_deduplicated() -> None:
    disabled = cache_ops._massive_daily_tickers_for_fetch(
        Settings(
            massive_options_historical_enabled=False,
            massive_options_flat_files_enabled=False,
            massive_options_underlyings="",
        )
    )
    enabled = cache_ops._massive_daily_tickers_for_fetch(
        Settings(
            massive_options_historical_enabled=True,
            massive_options_flat_files_enabled=True,
            massive_options_underlyings="spy,tm,SPY",
        )
    )

    assert "TM" in disabled
    assert "TM" in enabled
    assert "XLK" in cache_ops._massive_daily_tickers_for_fetch(
        Settings(
            massive_options_historical_enabled=True,
            massive_options_flat_files_enabled=True,
            massive_options_underlyings="",
        )
    )
    assert massive_options_primary_underlyings(
        Settings(massive_options_underlyings="spy,tm,SPY")
    ) == ("SPY", "TM")


def test_japanese_adr_spot_aggregate_routes_without_single_name_features() -> None:
    features = _massive_daily_feature_map(
        [
            {
                "ticker": "TM",
                "bar_date_et": "2026-01-02",
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
            },
            {
                "ticker": "SONY",
                "bar_date_et": "2026-01-02",
                "close": 50.0,
                "high": 51.0,
                "low": 49.0,
            },
            {
                "ticker": "TM",
                "bar_date_et": "2026-01-05",
                "close": 110.0,
                "high": 112.0,
                "low": 108.0,
            },
            {
                "ticker": "SONY",
                "bar_date_et": "2026-01-05",
                "close": 55.0,
                "high": 56.0,
                "low": 54.0,
            },
        ],
        calendar_records=[
            {"calendar_date": "2026-01-05", "us_close_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC)}
        ],
    )

    row = features["2026-01-05"]
    assert row["japan_adr_median_return"] == pytest.approx(0.0953101798)
    assert row["japan_adr_trimmed_mean_return"] == pytest.approx(0.0953101798)
    assert row["japan_adr_valid_underlying_count"] == pytest.approx(2.0)
    assert "tm_return" not in row


def test_calendar_mapping_status_edges_for_options_features() -> None:
    assert _calendar_mapping_status(
        target={},
        alignment={},
        us_calendar_row={},
        jpx_calendar_row={},
    ) == (
        "unmapped",
        "missing_time_alignment",
    )
    assert _calendar_mapping_status(
        target={},
        alignment={"alignment_status": "missing_us_close"},
        us_calendar_row={},
        jpx_calendar_row={},
    ) == ("us_holiday", "no_us_close_before_target_open")
    assert _calendar_mapping_status(
        target={"missing_reason": "holiday_trading_no_day_open"},
        alignment={"alignment_status": "ok"},
        us_calendar_row={},
        jpx_calendar_row={},
    ) == ("ose_holiday_trading", "ose_holiday_trading_no_day_open")
    assert _calendar_mapping_status(
        target={},
        alignment={"alignment_status": "ok"},
        us_calendar_row={"is_us_trading_day": True},
        jpx_calendar_row={"is_jpx_trading_day": False},
    ) == ("us_jp_desync", "us_open_jpx_closed")
    assert _calendar_mapping_status(
        target={},
        alignment={"alignment_status": "ok", "alignment_pass": False, "alignment_reason": "lag"},
        us_calendar_row={},
        jpx_calendar_row={},
    ) == ("us_jp_desync", "lag")


def test_options_audit_records_computed_iv_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(data_dir=tmp_path / "data")
    feature_records = [
        {
            "bar_date_et": "2026-01-05",
            "option_us_core_spy_atm_iv_short": 0.2,
            "option_us_core_spy_atm_iv_medium": None,
        }
    ]
    liquidity_records = [
        {
            "bar_date_et": "2026-01-05",
            "underlying": "SPY",
            "dte_bucket": "short",
            "valid_contract_count": 2,
            "iv_count": 2,
            "total_volume": 20,
        }
    ]

    source = build_options_source_audit_records(
        settings=Settings(
            massive_options_historical_enabled=True,
            massive_options_flat_files_enabled=True,
        ),
        run_ts=datetime(2026, 1, 5, tzinfo=UTC),
        option_feature_records=feature_records,
    )
    coverage = build_options_feature_coverage_records(
        settings=settings,
        option_feature_records=feature_records,
    )
    liquidity = build_options_liquidity_audit_records(
        settings=settings,
        liquidity_records=liquidity_records,
    )

    flatfile = next(
        row for row in source if row["source_name"] == "massive_options_historical_flat_files"
    )
    assert flatfile["computed_iv_proxy_available"] is True
    assert any(row["feature"] == "option_us_core_spy_atm_iv_short" for row in coverage)
    assert liquidity[0]["liquidity_status"] == "computed_iv_available"


class _FlatFileBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _FlatFileClient:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def get_object(self, **kwargs: object) -> dict[str, object]:
        self.keys.append(str(kwargs["Key"]))
        payload = gzip.compress(b"ticker,volume,open,close,high,low,window_start,transactions\n")
        return {"Body": _FlatFileBody(payload)}


def test_massive_options_day_aggs_download_uses_expected_key_and_cache(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _FlatFileClient()
    destination = tmp_path / "2026-01-05.csv.gz"

    assert massive_options_day_aggs_key("2026-01-05").endswith(
        "day_aggs_v1/2026/01/2026-01-05.csv.gz"
    )
    download_massive_options_day_aggs_file(
        client=client,
        destination=destination,
        day="2026-01-05",
    )
    download_massive_options_day_aggs_file(
        client=client,
        destination=destination,
        day="2026-01-05",
    )

    assert destination.exists()
    assert client.keys == ["us_options_opra/day_aggs_v1/2026/01/2026-01-05.csv.gz"]


def test_prepare_us_options_atm_iv_features_calls_flatfile_fetcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloaded = datetime(2026, 1, 5, 22, tzinfo=UTC)

    def _fake_fetch(**kwargs: object) -> list[dict[str, object]]:
        assert kwargs["start"] == "2026-01-05"
        return normalize_massive_options_day_agg_rows(
            [
                {
                    "ticker": "O:SPY260116C00100000",
                    "volume": "10",
                    "close": black_scholes_price(
                        spot=100.0,
                        strike=100.0,
                        rate=0.04,
                        time_to_expiry=11 / 365.25,
                        sigma=0.20,
                        option_type="C",
                    ),
                    "transactions": "2",
                }
            ],
            bar_date_et="2026-01-05",
            underlyings=("SPY",),
            downloaded_at_utc=downloaded,
        )

    monkeypatch.setattr(panel_us_options, "fetch_massive_options_day_agg_rows", _fake_fetch)
    result = panel_us_options.prepare_us_options_atm_iv_features(
        settings=Settings(),
        start="2026-01-05",
        end="2026-01-05",
        calendar_records=[
            {"calendar_date": "2026-01-05", "us_close_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC)}
        ],
        massive_daily_records=[{"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0}],
        fred_records=[
            {
                "series_id": "DGS2",
                "observation_date": "2026-01-05",
                "value": 4.0,
                "vendor_available_date_et": "2026-01-05",
                "vendor_available_ts_utc": datetime(2026, 1, 5, 21, tzinfo=UTC),
            }
        ],
        downloaded_at_utc=downloaded,
    )

    assert result.feature_records[0]["option_us_core_spy_atm_iv_short"] == pytest.approx(0.20)
