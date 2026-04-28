from __future__ import annotations

from datetime import UTC, datetime

import pytest

from n225_open_gap_tail.schemas import (
    JQUANTS_FUTURES_FIELD_USES,
    MODEL_READY_LOSS_FIELDS,
    REQUIRED_MARKET_STRUCTURE_FLAGS,
    REQUIRED_TARGET_FIELDS,
    REQUIRED_TIMESTAMP_FIELDS,
    ForecastOrigin,
    JoinMissReason,
    MappingStatus,
    SchemaContractError,
    TargetFamily,
    parse_forecast_origin,
    parse_target_family,
    require_fields,
    validate_feature_availability,
    validate_model_timing,
    validate_residual_reference_timing,
    validate_target_timing,
)


def test_schema_constants_cover_research_contract_terms() -> None:
    assert ForecastOrigin.US_CASH_CLOSE.value == "US_CASH_CLOSE"
    assert ForecastOrigin.OSE_NIGHT_CLOSE.value == "OSE_NIGHT_CLOSE"
    assert ForecastOrigin.PREV_OSE_DAY_CLOSE.value == "PREV_OSE_DAY_CLOSE"
    assert TargetFamily.FULL_GAP_SETTLE_TO_OPEN.value == "full_gap_settle_to_open"
    assert TargetFamily.FULL_GAP_CLOSE_TO_OPEN.value == "full_gap_close_to_open"
    assert TargetFamily.RESIDUAL_USCLOSEMARK_TO_OPEN.value == "residual_usclosemark_to_open"
    assert TargetFamily.RESIDUAL_NIGHTCLOSE_TO_DAY_OPEN.value == ("residual_nightclose_to_day_open")
    assert "vendor_available_ts_utc" in REQUIRED_TIMESTAMP_FIELDS
    assert "forecast_origin_name" in REQUIRED_TARGET_FIELDS
    assert "is_sq_window" in REQUIRED_MARKET_STRUCTURE_FLAGS
    assert JQUANTS_FUTURES_FIELD_USES["DaySessionOpen"] == "target_open"
    assert "standardized_loss_t" in MODEL_READY_LOSS_FIELDS
    assert MappingStatus.US_JP_DESYNC.value == "us_jp_desync"
    assert JoinMissReason.FRED_VINTAGE_UNSAFE.value == "fred_vintage_not_realtime_safe"


def test_parse_forecast_origin_and_target_family_are_strict() -> None:
    assert parse_forecast_origin("US_CASH_CLOSE") is ForecastOrigin.US_CASH_CLOSE
    assert parse_forecast_origin(ForecastOrigin.OSE_NIGHT_CLOSE) is ForecastOrigin.OSE_NIGHT_CLOSE
    assert parse_target_family("full_gap_settle_to_open") is (TargetFamily.FULL_GAP_SETTLE_TO_OPEN)
    assert parse_target_family(TargetFamily.FULL_GAP_CLOSE_TO_OPEN) is (
        TargetFamily.FULL_GAP_CLOSE_TO_OPEN
    )

    with pytest.raises(SchemaContractError, match="Unknown forecast origin"):
        parse_forecast_origin("US_CLOSE")
    with pytest.raises(SchemaContractError, match="Unknown target family"):
        parse_target_family("overnight_return")
    with pytest.raises(SchemaContractError, match="must be a string"):
        parse_forecast_origin(1)
    with pytest.raises(SchemaContractError, match="must be a string"):
        parse_target_family(None)


def test_require_fields_reports_missing_fields() -> None:
    with pytest.raises(SchemaContractError, match="missing required fields: b, c"):
        require_fields({"a": 1}, ("a", "b", "c"), schema_name="synthetic row")


def test_validate_target_timing_accepts_strictly_future_target_open() -> None:
    row = {
        "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
        "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
    }

    validate_target_timing(row)


def test_validate_target_timing_rejects_leakage_and_naive_timestamps() -> None:
    with pytest.raises(SchemaContractError, match="must be after"):
        validate_target_timing(
            {
                "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
                "target_open_ts_utc": _ts(2026, 1, 5, 21),
            }
        )

    with pytest.raises(SchemaContractError, match="timezone-aware"):
        validate_target_timing(
            {
                "model_cutoff_ts_utc": datetime(2026, 1, 5, 21),
                "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
            }
        )

    with pytest.raises(SchemaContractError, match="must be a datetime"):
        validate_target_timing(
            {
                "model_cutoff_ts_utc": "2026-01-05T21:00:00Z",
                "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
            }
        )


def test_validate_residual_reference_timing_requires_reference_before_cutoff() -> None:
    row = {
        "reference_price_ts_utc": _ts(2026, 1, 5, 20, 59),
        "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
    }

    validate_residual_reference_timing(row)

    with pytest.raises(SchemaContractError, match="no later"):
        validate_residual_reference_timing(
            {
                "reference_price_ts_utc": _ts(2026, 1, 5, 21, 1),
                "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
            }
        )


def test_validate_model_timing_handles_full_gap_and_residual_targets() -> None:
    validate_model_timing(
        {
            "forecast_origin_name": "US_CASH_CLOSE",
            "target_family": "full_gap_settle_to_open",
            "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
            "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
        }
    )

    validate_model_timing(
        {
            "forecast_origin_name": ForecastOrigin.OSE_NIGHT_CLOSE,
            "target_family": TargetFamily.RESIDUAL_NIGHTCLOSE_TO_DAY_OPEN,
            "reference_price_ts_utc": _ts(2026, 1, 5, 21),
            "model_cutoff_ts_utc": _ts(2026, 1, 5, 21),
            "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
        }
    )


def test_validate_model_timing_blocks_usclosemark_residual_until_enabled() -> None:
    row = {
        "forecast_origin_name": "US_CASH_CLOSE",
        "target_family": "residual_usclosemark_to_open",
        "reference_price_ts_utc": _ts(2026, 1, 5, 21),
        "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
        "target_open_ts_utc": _ts(2026, 1, 5, 23, 45),
    }

    with pytest.raises(SchemaContractError, match="licensed timestamped intraday mark"):
        validate_model_timing(row)

    validate_model_timing(row, residual_usclosemark_enabled=True)


def test_validate_feature_availability_enforces_cutoff() -> None:
    row = {
        "vendor_available_ts_utc": _ts(2026, 1, 5, 21, 10),
        "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
    }

    validate_feature_availability(row)

    with pytest.raises(SchemaContractError, match="no later"):
        validate_feature_availability(
            {
                "vendor_available_ts_utc": _ts(2026, 1, 5, 21, 16),
                "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
            }
        )


def test_validate_feature_availability_handles_unknown_and_invalid_vendor_times() -> None:
    row = {
        "vendor_available_ts_utc": None,
        "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
    }

    with pytest.raises(SchemaContractError, match="is required"):
        validate_feature_availability(row)
    validate_feature_availability(row, allow_unknown_vendor_availability=True)

    with pytest.raises(SchemaContractError, match="must be a datetime"):
        validate_feature_availability(
            {
                "vendor_available_ts_utc": "2026-01-05T21:00:00Z",
                "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
            }
        )

    with pytest.raises(SchemaContractError, match="timezone-aware"):
        validate_feature_availability(
            {
                "vendor_available_ts_utc": datetime(2026, 1, 5, 21),
                "model_cutoff_ts_utc": _ts(2026, 1, 5, 21, 15),
            }
        )


def _ts(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)
