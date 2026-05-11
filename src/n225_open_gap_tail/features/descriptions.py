# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    cast,
    date,
    math,
    PipelineRunError,
    timedelta,
)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _required_float(value: object) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise PipelineRunError(f"Expected finite numeric value, got {value!r}")
    return parsed


def _safe_name(value: str) -> str:
    return value.replace(":", "_").replace(".", "_").replace("-", "_").replace("/", "_").lower()


def _feature_description(field: str) -> str:
    if field.startswith("n225_option_"):
        return (
            "lagged J-Quants Nikkei 225 option-state feature available before the forecast cutoff"
        )
    if field.startswith("event_"):
        return "scheduled macro or policy event calendar control with timestamp-safe availability"
    if field.startswith("xmarket_"):
        return "derived cross-market panel feature built from already timestamped source predictors"
    if field.startswith("n225_"):
        return "lagged Nikkei 225 futures history feature built only from prior clean rows"
    if field.startswith("option_"):
        return (
            "computed U.S. OPRA options ATM-IV proxy from Massive day aggregates, "
            "Black-Scholes, DGS2, and zero dividend"
        )
    if field.startswith("japan_adr_"):
        return "Japanese ADR spot aggregate from U.S.-listed ADR daily bars"
    if field.startswith("fx_usdjpy_"):
        return "canonical USDJPY FX control using timestamp-safe FRED H.10 availability"
    if "_late_60m_realized_var" in field:
        return "late-session realized variance from one-minute U.S.-listed instrument bars"
    if "_late_60m_up_semivar" in field or "_late_60m_down_semivar" in field:
        return "late-session realized semivariance from one-minute U.S.-listed instrument bars"
    if "_late_60m_skew" in field or "_late_60m_excess_kurtosis" in field:
        return "noisy late-session small-sample realized moment from one-minute bars"
    if "_late_volume_" in field or field.endswith("_volume_surge"):
        return "late-session volume feature normalized within ticker using prior history"
    if field.endswith("_days"):
        return "timestamp-safe source staleness or release-lag diagnostic used as a predictor"
    if "_late_" in field or field.endswith("_final_window_momentum"):
        return (
            "U.S.-listed instrument late-session minute-bar feature frozen at the U.S. close cutoff"
        )
    if field.endswith("_return"):
        return "close-to-close log return frozen at U.S. close information set"
    if field.endswith("_range"):
        return "log high-low range over the source bar window"
    if field.endswith("_diff"):
        return "first difference of daily source value"
    if field.endswith("_level"):
        return "daily source level with conservative research availability semantics"
    return "run predictor candidate"


def _window_return(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    start = closes[-window - 1]
    end = closes[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _window_range(highs: list[float | None], lows: list[float | None]) -> float | None:
    valid_highs = [value for value in highs if value is not None and value > 0]
    valid_lows = [value for value in lows if value is not None and value > 0]
    if not valid_highs or not valid_lows:
        return None
    return math.log(max(valid_highs)) - math.log(min(valid_lows))


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        next_month = current.replace(day=28) + timedelta(days=4)
        month_end = min(next_month.replace(day=1) - timedelta(days=1), end_date)
        chunks.append((current.isoformat(), month_end.isoformat()))
        current = month_end + timedelta(days=1)
    return chunks
