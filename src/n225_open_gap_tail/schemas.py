from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum


class SchemaContractError(ValueError):
    """Raised when a row violates the research schema contract."""


class ForecastOrigin(StrEnum):
    """Forecast origins used throughout the project."""

    US_CASH_CLOSE = "US_CASH_CLOSE"
    OSE_NIGHT_CLOSE = "OSE_NIGHT_CLOSE"
    PREV_OSE_DAY_CLOSE = "PREV_OSE_DAY_CLOSE"


class TargetFamily(StrEnum):
    """Target families used for OSE Nikkei 225 futures opening-gap research."""

    FULL_GAP_SETTLE_TO_OPEN = "full_gap_settle_to_open"
    FULL_GAP_CLOSE_TO_OPEN = "full_gap_close_to_open"
    RESIDUAL_USCLOSEMARK_TO_OPEN = "residual_usclosemark_to_open"
    RESIDUAL_NIGHTCLOSE_TO_DAY_OPEN = "residual_nightclose_to_day_open"


REQUIRED_TIMESTAMP_FIELDS = (
    "observation_ts_utc",
    "bar_start_ts_utc",
    "bar_end_ts_utc",
    "vendor_available_ts_utc",
    "research_download_ts_utc",
    "model_cutoff_ts_utc",
    "target_open_ts_utc",
    "reference_price_ts_utc",
)

REQUIRED_TARGET_FIELDS = (
    "target_family",
    "forecast_origin_name",
    "reference_price",
    "reference_price_source",
    "model_cutoff_ts_utc",
    "target_open_ts_utc",
)

REQUIRED_MARKET_STRUCTURE_FLAGS = (
    "is_roll_window",
    "is_sq_window",
    "is_japan_holiday_adjacent",
    "is_us_holiday_adjacent",
    "is_us_early_close",
    "is_ose_holiday_trading",
)

JQUANTS_FUTURES_FIELD_USES = {
    "DaySessionOpen": "target_open",
    "DaySessionClose": "full_gap_close_reference",
    "NightSessionClose": "nightclose_residual_reference",
    "SettlementPrice": "full_gap_settlement_reference",
    "Volume": "liquidity_proxy",
    "OpenInterest": "liquidity_and_roll_proxy",
    "LastTradingDay": "roll_window_flag",
    "SpecialQuotationDay": "sq_window_flag",
    "CentralContractMonthFlag": "central_contract_selection",
}

MODEL_READY_LOSS_FIELDS = (
    "gap_t",
    "loss_t",
    "baseline_residual_loss_t",
    "lgbm_predicted_location_t",
    "lgbm_predicted_scale_t",
    "standardized_loss_t",
    "evt_threshold_u",
    "exceedance_indicator_t",
    "exceedance_severity_t",
    "tail_probability_alpha",
    "var_forecast",
    "es_forecast",
)


def require_fields(
    row: Mapping[str, object],
    required_fields: Iterable[str],
    *,
    schema_name: str = "row",
) -> None:
    """Require that a mapping carries all fields in a schema contract."""
    missing = tuple(field for field in required_fields if field not in row)
    if missing:
        joined = ", ".join(missing)
        raise SchemaContractError(f"{schema_name} is missing required fields: {joined}")


def parse_forecast_origin(value: object) -> ForecastOrigin:
    """Parse and validate a forecast origin value."""
    if isinstance(value, ForecastOrigin):
        return value
    if isinstance(value, str):
        try:
            return ForecastOrigin(value)
        except ValueError as exc:
            raise SchemaContractError(f"Unknown forecast origin: {value}") from exc
    raise SchemaContractError("Forecast origin must be a string or ForecastOrigin")


def parse_target_family(value: object) -> TargetFamily:
    """Parse and validate a target-family value."""
    if isinstance(value, TargetFamily):
        return value
    if isinstance(value, str):
        try:
            return TargetFamily(value)
        except ValueError as exc:
            raise SchemaContractError(f"Unknown target family: {value}") from exc
    raise SchemaContractError("Target family must be a string or TargetFamily")


def validate_model_timing(
    row: Mapping[str, object],
    *,
    residual_usclosemark_enabled: bool = False,
    schema_name: str = "model row",
) -> None:
    """Validate model-row timing and target-family availability invariants."""
    require_fields(
        row,
        ("forecast_origin_name", "target_family", "model_cutoff_ts_utc", "target_open_ts_utc"),
        schema_name=schema_name,
    )
    parse_forecast_origin(row["forecast_origin_name"])
    target_family = parse_target_family(row["target_family"])
    validate_target_timing(row, schema_name=schema_name)

    if target_family in {
        TargetFamily.RESIDUAL_NIGHTCLOSE_TO_DAY_OPEN,
        TargetFamily.RESIDUAL_USCLOSEMARK_TO_OPEN,
    }:
        validate_residual_reference_timing(row, schema_name=schema_name)

    if (
        target_family is TargetFamily.RESIDUAL_USCLOSEMARK_TO_OPEN
        and not residual_usclosemark_enabled
    ):
        raise SchemaContractError(
            "residual_usclosemark_to_open requires a licensed timestamped intraday mark"
        )


def validate_target_timing(row: Mapping[str, object], *, schema_name: str = "target row") -> None:
    """Require target opens to occur after the model cutoff."""
    require_fields(row, ("model_cutoff_ts_utc", "target_open_ts_utc"), schema_name=schema_name)
    model_cutoff = _aware_datetime(row, "model_cutoff_ts_utc", schema_name=schema_name)
    target_open = _aware_datetime(row, "target_open_ts_utc", schema_name=schema_name)
    if target_open <= model_cutoff:
        raise SchemaContractError(
            f"{schema_name} target_open_ts_utc must be after model_cutoff_ts_utc"
        )


def validate_residual_reference_timing(
    row: Mapping[str, object],
    *,
    schema_name: str = "residual target row",
) -> None:
    """Require residual reference prices to be known no later than model cutoff."""
    require_fields(row, ("reference_price_ts_utc", "model_cutoff_ts_utc"), schema_name=schema_name)
    reference_ts = _aware_datetime(row, "reference_price_ts_utc", schema_name=schema_name)
    model_cutoff = _aware_datetime(row, "model_cutoff_ts_utc", schema_name=schema_name)
    if reference_ts > model_cutoff:
        raise SchemaContractError(
            f"{schema_name} reference_price_ts_utc must be no later than model_cutoff_ts_utc"
        )


def validate_feature_availability(
    row: Mapping[str, object],
    *,
    allow_unknown_vendor_availability: bool = False,
    schema_name: str = "feature row",
) -> None:
    """Require feature availability timestamps to be no later than model cutoff."""
    require_fields(row, ("vendor_available_ts_utc", "model_cutoff_ts_utc"), schema_name=schema_name)
    model_cutoff = _aware_datetime(row, "model_cutoff_ts_utc", schema_name=schema_name)
    vendor_available = row["vendor_available_ts_utc"]

    if vendor_available is None:
        if allow_unknown_vendor_availability:
            return
        raise SchemaContractError(f"{schema_name} vendor_available_ts_utc is required")

    if not isinstance(vendor_available, datetime):
        raise SchemaContractError(f"{schema_name} vendor_available_ts_utc must be a datetime")
    if _is_naive(vendor_available):
        raise SchemaContractError(f"{schema_name} vendor_available_ts_utc must be timezone-aware")
    if vendor_available > model_cutoff:
        raise SchemaContractError(
            f"{schema_name} vendor_available_ts_utc must be no later than model_cutoff_ts_utc"
        )


def _aware_datetime(
    row: Mapping[str, object],
    field: str,
    *,
    schema_name: str,
) -> datetime:
    value = row[field]
    if not isinstance(value, datetime):
        raise SchemaContractError(f"{schema_name} {field} must be a datetime")
    if _is_naive(value):
        raise SchemaContractError(f"{schema_name} {field} must be timezone-aware")
    return value


def _is_naive(value: datetime) -> bool:
    return value.tzinfo is None or value.utcoffset() is None
