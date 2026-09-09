"""Taylor-approximate GREM for ES, independent of coverage/FZ0 selection.

Wang, Wang and Ziegel, E-backtesting, Sections 4--5 and Appendix A:
https://arxiv.org/html/2209.00991v6
The basic null includes correct conditional VaR and non-underreported ES.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import pairwise
from typing import Any

import numpy as np

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_ADVANCED_REFIT_FREQUENCY,
    ML_TAIL_REFIT_FREQUENCY,
    _optional_float,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible


def _taylor_bet(statistics: np.ndarray) -> float:
    centered = statistics - 1.0
    scale = float(np.max(np.abs(centered))) if centered.size else 0.0
    if scale == 0:
        return 0.0
    scaled = centered / scale
    return float(np.clip(scaled.sum() / np.dot(scaled, scaled) / scale, 0.0, 0.5))


def grem_sequence(
    rows: list[dict[str, object]], *, tail_level: float, window: int
) -> list[dict[str, Any]]:
    """Accumulate an equal capital mixture; W limits past bet-learning only.

    Availability must be explicitly audited as known at the cutoff. Known
    unavailable forecasts get zero bets. Unknown timing or a missing realized
    loss makes the suffix unavailable: never delete the observation or reset.
    """
    if not 0 < tail_level < 1 or window < 1:
        raise ValueError("GREM requires a level in (0, 1) and a positive betting window")
    dates = [str(row["forecast_date"]) for row in rows]
    if any(previous >= current for previous, current in pairwise(dates)):
        raise ValueError("GREM dates must be strictly increasing on the native axis")
    statistics: list[float] = []
    losses: list[float] = []
    log_gree = log_grel = peak = 0.0
    unavailable_since: str | None = None
    curve: list[dict[str, Any]] = []
    for row in rows:
        loss, var, es = (
            _optional_float(row.get(name))
            for name in ("realized_loss", "var_forecast", "es_forecast")
        )
        reason = row.get("no_bet_reason")
        input_status = "eligible"
        if row.get("availability_known_at_cutoff") is not True:
            input_status, reason = "unavailable", "unverified_availability_at_cutoff"
        elif loss is None or not math.isfinite(loss):
            input_status, reason = "unavailable", "missing_realized_loss"
        elif (
            reason
            or var is None
            or es is None
            or not math.isfinite(var)
            or not math.isfinite(es)
            or es <= var
        ):
            input_status = "predictable_no_bet"
            reason = reason or "invalid_or_unavailable_es_pair"
        if input_status == "unavailable" and unavailable_since is None:
            unavailable_since = str(row["forecast_date"])
        history_n = min(len(losses), window)
        current = None
        bet_e = bet_l = 0.0
        if input_status == "eligible" and unavailable_since is None:
            assert loss is not None and var is not None and es is not None
            denominator = (1.0 - tail_level) * (es - var)
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                past_current_forecast = (
                    np.maximum(np.asarray(losses[-window:]) - var, 0) / denominator
                )
                current = max(loss - var, 0.0) / denominator if denominator > 0 else math.nan
            if (
                not math.isfinite(denominator)
                or not math.isfinite(current)
                or not np.isfinite(past_current_forecast).all()
            ):
                # A failure depending on today's loss must not become a valid no-bet.
                input_status, reason = "unavailable", "nonfinite_derived_e_statistic"
                unavailable_since, current = str(row["forecast_date"]), None
            else:
                bet_e = _taylor_bet(np.asarray(statistics[-window:]))
                bet_l = _taylor_bet(past_current_forecast)
                log_gree += math.log1p(bet_e * (current - 1.0))
                log_grel += math.log1p(bet_l * (current - 1.0))
                statistics.append(current)
                losses.append(loss)
        log_grem = float(np.logaddexp(log_gree, log_grel) - math.log(2.0))
        peak = max(peak, log_grem)
        curve.append(
            {
                "forecast_date": row["forecast_date"],
                "input_status": input_status,
                "availability_reason": reason,
                "diagnostic_status": "unavailable" if unavailable_since else "ok",
                "unavailable_since": unavailable_since,
                "history_n": history_n,
                "e_statistic": current,
                "lambda_gree": bet_e if unavailable_since is None else None,
                "lambda_grel": bet_l if unavailable_since is None else None,
                "log_gree": log_gree if unavailable_since is None else None,
                "log_grel": log_grel if unavailable_since is None else None,
                "log_grem": log_grem if unavailable_since is None else None,
                "running_max_log_grem": peak if unavailable_since is None else None,
            }
        )
    return curve


def build_grem_artifacts(
    forecasts: list[dict[str, object]],
    *,
    roster: list[dict[str, object]],
    panel_rows: dict[str, dict[str, Any]],
    start: str,
    target: str,
    tail_level: float,
    unavailable_records: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Use the full native target axis and the pre-screen roster, never gate winners.

    Cutoff audit of the current generators: body/baseline fits use historical
    rows; advanced forecasts precede the current-loss state update. A recorded
    train_end must precede the forecast. Calendar exclusions are limited to
    roll/SQ and US holidays; absent records need dated pre-forecast fit-failure
    evidence. Unknown exclusions/absence cannot become retrospective no-bets.
    """
    grouped: dict[tuple[str, str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in forecasts:
        key = (str(row["model_name"]), str(row["tail_side"]), str(row["information_set"]))
        grouped[key][str(row["forecast_date"])] = row
    known_failures: set[tuple[str, str, str, str]] = set()
    for row in unavailable_records:
        day = str(row.get("forecast_date") or "")
        status = str(row.get("fit_status") or "")
        # A same-day post-loss filter failure does not justify skipping that day.
        pre_forecast_failure = status in {
            "unavailable_optimizer_failed",
            "unavailable_forecast_failed",
        } or (
            status
            in {
                "unavailable_gas_filter_failed",
                "unavailable_care_expectile_calibration_failed",
                "unavailable_advanced_optimizer_failed",
            }
            and bool(row.get("train_end"))
            and str(row["train_end"]) < day
        )
        if day and pre_forecast_failure:
            known_failures.add(
                (
                    str(row["model_name"]),
                    str(row["tail_side"]),
                    str(row.get("information_set") or "target_history_only"),
                    day,
                )
            )
    curves: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for candidate in roster:
        model, side, info = (
            str(candidate[name]) for name in ("model_name", "tail_side", "information_set")
        )
        by_date = grouped[(model, side, info)]
        frequencies = {row.get("refit_frequency") for row in by_date.values()}
        if len(frequencies) > 1:
            raise ValueError(
                f"GREM candidate contains multiple refit frequencies: {model}, {info}, {side}"
            )
        frequency = (
            next(iter(frequencies))
            if frequencies
            else (
                BENCHMARK_ADVANCED_REFIT_FREQUENCY
                if model in BENCHMARK_ADVANCED_MODEL_NAMES
                else None
                if info == "target_history_only"
                else ML_TAIL_REFIT_FREQUENCY
            )
        )
        metadata = {
            "suite": "benchmark" if info == "target_history_only" else "ml_tail",
            "target_family": target,
            "model_name": model,
            "information_set": info,
            "tail_side": side,
            "tail_level": tail_level,
            "refit_frequency": frequency,
        }
        inputs: list[dict[str, object]] = []
        for index, (day, panel) in enumerate(sorted(panel_rows.items())):
            if day < start:
                continue
            forecast_row = by_date.get(day)
            known = False
            no_bet_reason: object = None
            if panel["clean_sample"] is not True:
                missing = set(str(panel.get("missing_reason") or "").split(";")) - {""}
                roll = missing == {"roll_sq_excluded"}
                holiday = not missing and panel.get("mapping_status") == "us_holiday"
                known = roll or holiday
                no_bet_reason = (
                    "calendar_roll_sq" if roll else "calendar_us_holiday" if holiday else None
                )
            elif forecast_row is not None:
                known = bool(forecast_row.get("train_end")) and str(forecast_row["train_end"]) < day
                # The score-domain decision here deliberately does not use today's loss.
                if not forecast_eligible({**forecast_row, "realized_loss": 0.0}, score="joint"):
                    no_bet_reason = (
                        forecast_row.get("failure_reason")
                        or forecast_row.get("invalid_reason")
                        or "unavailable_forecast_pair"
                    )
            elif (model, side, info, day) in known_failures:
                known, no_bet_reason = True, "dated_pre_forecast_fit_failure"
            loss = _optional_float(panel.get("realized_loss"))
            inputs.append(
                {
                    "forecast_date": day,
                    "target_session_index": index,
                    "realized_loss": loss * (1 if side == "left_tail" else -1)
                    if loss is not None
                    else None,
                    "var_forecast": forecast_row.get("var_forecast") if forecast_row else None,
                    "es_forecast": forecast_row.get("es_forecast") if forecast_row else None,
                    "availability_known_at_cutoff": known,
                    "no_bet_reason": no_bet_reason,
                }
            )
        for window in (500, 250):
            curve = grem_sequence(inputs, tail_level=tail_level, window=window)
            full_curve = [
                {
                    **metadata,
                    "window": window,
                    "target_session_index": source["target_session_index"],
                    **row,
                }
                for source, row in zip(inputs, curve, strict=True)
            ]
            curves.extend(full_curve)
            eligible = [row for row in curve if row["input_status"] == "eligible"]
            valid = [row for row in curve if row["diagnostic_status"] == "ok"]
            alarms = [row for row in valid if row["log_grem"] >= math.log(20.0)]
            unavailable_since = next(
                (row["unavailable_since"] for row in curve if row["unavailable_since"]), None
            )
            summaries.append(
                {
                    **metadata,
                    "window": window,
                    "diagnostic_status": "unavailable_segment"
                    if unavailable_since
                    else "ok"
                    if eligible
                    else "no_eligible_inputs",
                    "monitoring_axis_rows": len(curve),
                    "input_eligible_rows": len(eligible),
                    "processed_eligible_rows": sum(
                        row["input_status"] == "eligible" for row in valid
                    ),
                    "predictable_no_bet_rows": sum(
                        row["input_status"] == "predictable_no_bet" for row in curve
                    ),
                    "unavailable_rows": len(curve) - len(valid),
                    "first_input_eligible_date": eligible[0]["forecast_date"] if eligible else None,
                    "last_valid_date": valid[-1]["forecast_date"] if valid else None,
                    "unavailable_since": unavailable_since,
                    "final_log_grem": curve[-1]["log_grem"] if curve and eligible else None,
                    "valid_prefix_peak_log_grem": valid[-1]["running_max_log_grem"]
                    if valid and eligible
                    else None,
                    "first_crossing_20_date": alarms[0]["forecast_date"] if alarms else None,
                }
            )
    return {"grem_curves": curves, "grem_summary": summaries}
