"""Frozen-forecast admission and one cross-scenario FZG comparison panel."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import chain

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_BENCHMARK_INFORMATION_SET,
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_MIN_ROWS,
    PASS_ALL_TAIL_SIDES,
    PASS_ALL_TEST_ALPHA,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, fzg_loss, quantile_loss

EXTERNAL_MODELS = BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES
Scenario = tuple[str, str, str]


def _scenario(row: Mapping[str, object]) -> Scenario:
    return str(row["model_name"]), str(row["information_set"]), str(row["tail_side"])


def _finite(value: object) -> float | None:
    number = _optional_float(value)
    return number if number is not None and math.isfinite(number) else None


def _scenario_index(rows: list[dict[str, object]], label: str) -> dict[Scenario, dict[str, object]]:
    result: dict[Scenario, dict[str, object]] = {}
    for row in rows:
        key = _scenario(row)
        if key in result:
            raise ValueError(f"Duplicate {label} scenario: {key}")
        result[key] = row
    return result


def _gate(
    key: Scenario, native: Mapping[str, object], grem: Mapping[str, object]
) -> dict[str, object]:
    n = _finite(native.get("rows"))
    kupiec = _finite(native.get("kupiec_pvalue"))
    independence = _finite(native.get("christoffersen_pvalue"))
    eligible = _finite(grem.get("processed_eligible_rows"))
    peak = _finite(grem.get("valid_prefix_peak_log_grem"))
    reasons: list[str] = []
    if n is None or n < PASS_ALL_MIN_ROWS:
        reasons.append("insufficient_native_var_rows")
    if kupiec is None or independence is None:
        reasons.append("unavailable_var_pvalues")
    if eligible is None or eligible < PASS_ALL_MIN_ROWS:
        reasons.append("insufficient_grem_eligible_rows")
    if (
        grem.get("diagnostic_status") != "ok"
        or _finite(grem.get("unavailable_rows")) != 0
        or grem.get("unavailable_since") is not None
        or peak is None
        or _finite(grem.get("final_log_grem")) is None
    ):
        reasons.append("unavailable_grem_sequence")
    assessable = not reasons
    var_pass = (
        n is not None
        and n >= PASS_ALL_MIN_ROWS
        and kupiec is not None
        and kupiec >= PASS_ALL_TEST_ALPHA
        and independence is not None
        and independence >= PASS_ALL_TEST_ALPHA
    )
    alarm = (peak is not None and peak >= math.log(20)) or bool(grem.get("first_crossing_20_date"))
    if kupiec is not None and kupiec < PASS_ALL_TEST_ALPHA:
        reasons.append("kupiec_rejection")
    if independence is not None and independence < PASS_ALL_TEST_ALPHA:
        reasons.append("independence_rejection")
    if alarm:
        reasons.append("grem_historical_crossing")
    passed = assessable and var_pass and not alarm
    return {
        "model_name": key[0],
        "information_set": key[1],
        "tail_side": key[2],
        "native_var_rows": n,
        "var_breach_rate": native.get("var_breach_rate"),
        "kupiec_pvalue": kupiec,
        "christoffersen_pvalue": independence,
        "var_gate_pass": var_pass,
        "grem_window": 500,
        "grem_eligible_rows": eligible,
        "grem_input_eligible_rows": grem.get("input_eligible_rows"),
        "grem_monitoring_axis_rows": grem.get("monitoring_axis_rows"),
        "grem_no_bet_rows": grem.get("predictable_no_bet_rows"),
        "grem_status": grem.get("diagnostic_status"),
        "grem_peak_log": peak,
        "grem_final_log": grem.get("final_log_grem"),
        "grem_first_crossing_date": grem.get("first_crossing_20_date"),
        "gate_pass": passed,
        "gate_status": "passed" if passed else "failed" if assessable else "unassessable",
        "gate_reasons": reasons,
    }


def _index_forecasts(
    forecasts: list[dict[str, object]], ml_model_names: tuple[str, ...]
) -> tuple[dict[Scenario, dict[str, dict[str, object]]], dict[str, int]]:
    indexed: dict[Scenario, dict[str, dict[str, object]]] = {}
    sessions: dict[str, int] = {}
    dates_by_session: dict[int, str] = {}
    outcomes: dict[tuple[str, str], float] = {}
    scope: set[tuple[str, float]] = set()
    for row in forecasts:
        key = _scenario(row)
        if key[0] not in (*ml_model_names, *EXTERNAL_MODELS):
            continue
        infos = (
            PASS_ALL_INFORMATION_SETS
            if key[0] in ml_model_names
            else (PASS_ALL_BENCHMARK_INFORMATION_SET,)
        )
        if key[1] not in infos or key[2] not in PASS_ALL_TAIL_SIDES:
            raise ValueError(f"Unexpected forecast scenario: {key}")
        day = str(row["forecast_date"])
        if day in indexed.setdefault(key, {}):
            raise ValueError(f"Duplicate forecast record: {key}, {day}")
        target, level = row.get("target_family"), _finite(row.get("tail_level"))
        if not target or level is None or not 0 < level < 1:
            raise ValueError("Forecasts require a target family and valid tail level")
        scope.add((str(target), level))
        position = _finite(row.get("target_session_index"))
        if position is None or position < 0 or not position.is_integer():
            raise ValueError("Forecasts require original integer target-session indices")
        index = int(position)
        if (day in sessions and sessions[day] != index) or (
            index in dates_by_session and dates_by_session[index] != day
        ):
            raise ValueError(f"Inconsistent target-session index on {day}")
        sessions[day], dates_by_session[index] = index, day
        loss = _finite(row.get("realized_loss"))
        outcome_key = (day, key[2])
        if loss is not None:
            if outcome_key in outcomes and outcomes[outcome_key] != loss:
                raise ValueError(f"Inconsistent realized outcome on {day}, {key[2]}")
            outcomes[outcome_key] = loss
        indexed[key][day] = row
    if len(scope) > 1:
        raise ValueError("Comparison requires one target family and one tail level")
    ordered_indices = [sessions[day] for day in sorted(sessions)]
    if ordered_indices != sorted(ordered_indices):
        raise ValueError("Target-session indices must preserve forecast-date chronology")
    return indexed, sessions


def _source_key(key: Scenario) -> Scenario:
    return (
        (key[0], PASS_ALL_BENCHMARK_INFORMATION_SET, key[2]) if key[0] in EXTERNAL_MODELS else key
    )


def _scores(row: Mapping[str, object]) -> tuple[float, float, bool]:
    loss, var, es, level = (
        _required_float(row[name])
        for name in ("realized_loss", "var_forecast", "es_forecast", "tail_level")
    )
    return fzg_loss(loss, var, es, level), quantile_loss(100 * loss, 100 * var, level), loss > var


def _common_dates(
    members: list[Scenario],
    indexed: dict[Scenario, dict[str, dict[str, object]]],
    sessions: dict[str, int],
    *,
    scope: str,
) -> tuple[list[str], list[dict[str, object]]]:
    dates = sorted({day for member in members for day in indexed.get(_source_key(member), {})})
    common: list[str] = []
    ledger: list[dict[str, object]] = []
    for day in dates:
        missing: list[str] = []
        reasons: list[str] = []
        for member in members:
            row = indexed.get(_source_key(member), {}).get(day)
            reason = None
            if row is None:
                reason = "missing_forecast_record"
            elif not forecast_eligible(row, score="joint"):
                reason = str(
                    row.get("failure_reason") or row.get("invalid_reason") or "invalid_joint_pair"
                )
            elif not all(math.isfinite(score) for score in _scores(row)[:2]):
                reason = "nonfinite_evaluation_score"
            if reason:
                label = "/".join(member)
                missing.append(label)
                reasons.append(f"{label}:{reason}")
        if not missing:
            common.append(day)
        ledger.append(
            {
                "scope": scope,
                "forecast_date": day,
                "target_session_index": sessions[day],
                "required_members": len(members),
                "eligible_members": len(members) - len(missing),
                "in_common": not missing,
                "missing_members": missing,
                "missing_reasons": reasons,
            }
        )
    return common, ledger


def build_robust_comparison_artifacts(
    forecasts: list[dict[str, object]],
    native_metrics: list[dict[str, object]],
    grem_summary: list[dict[str, object]],
    *,
    ml_model_names: tuple[str, ...],
) -> dict[str, list[dict[str, object]]]:
    """Apply native gates before constructing any shared-date comparison."""
    if len(set(ml_model_names)) != len(ml_model_names) or set(ml_model_names) & set(
        EXTERNAL_MODELS
    ):
        raise ValueError("ML roster must be unique and disjoint from external candidates")
    targets: set[str] = set()
    levels: set[float] = set()
    for row in chain(forecasts, native_metrics, grem_summary):
        if row.get("target_family") is not None:
            targets.add(str(row["target_family"]))
        if row.get("tail_level") is not None:
            level = _finite(row["tail_level"])
            if level is None or not 0 < level < 1:
                raise ValueError("Comparison requires a valid tail level")
            levels.add(level)
    if len(targets) > 1 or len(levels) > 1:
        raise ValueError("Comparison requires one target family and one tail level")
    indexed, sessions = _index_forecasts(forecasts, ml_model_names)
    native = _scenario_index(native_metrics, "native metrics")
    grem = _scenario_index([row for row in grem_summary if row.get("window") == 500], "W500 GREM")
    gate_rows: list[dict[str, object]] = []
    admission: list[dict[str, object]] = []
    for model in (*ml_model_names, *EXTERNAL_MODELS):
        information_sets = (
            PASS_ALL_INFORMATION_SETS
            if model in ml_model_names
            else (PASS_ALL_BENCHMARK_INFORMATION_SET,)
        )
        model_gates = [
            _gate(key, native.get(key, {}), grem.get(key, {}))
            for info in information_sets
            for side in PASS_ALL_TAIL_SIDES
            for key in [(model, info, side)]
        ]
        gate_rows.extend(model_gates)
        passed = all(row["gate_pass"] is True for row in model_gates)
        admission.append(
            {
                "model_name": model,
                "suite": "ml_tail" if model in ml_model_names else "benchmark",
                "required_scenarios": len(model_gates),
                "passed_scenarios": sum(row["gate_pass"] is True for row in model_gates),
                "unassessable_scenarios": sum(
                    row["gate_status"] == "unassessable" for row in model_gates
                ),
                "admitted": passed,
                "admission_status": "admitted"
                if passed
                else "unassessable"
                if any(row["gate_status"] == "unassessable" for row in model_gates)
                else "failed",
            }
        )
    admitted_ml = [
        str(row["model_name"])
        for row in admission
        if row["admitted"] is True and row["suite"] == "ml_tail"
    ]
    admitted_external = [
        str(row["model_name"])
        for row in admission
        if row["admitted"] is True and row["suite"] == "benchmark"
    ]
    external_members = [
        (model, PASS_ALL_BENCHMARK_INFORMATION_SET, side)
        for model in admitted_external
        for side in PASS_ALL_TAIL_SIDES
    ]
    external_dates, external_ledger = _common_dates(
        external_members, indexed, sessions, scope="external_selection"
    )
    external_means = {
        model: math.fsum(
            _scores(indexed[(model, PASS_ALL_BENCHMARK_INFORMATION_SET, side)][day])[0]
            for day in external_dates
            for side in PASS_ALL_TAIL_SIDES
        )
        / (2 * len(external_dates))
        for model in admitted_external
        if external_dates
    }
    reference = (
        min(external_means, key=lambda model: external_means[model]) if external_means else None
    )
    tied = [
        model
        for model, score in external_means.items()
        if reference is not None and score == external_means[reference]
    ]
    selection_status = (
        "ok"
        if reference is not None
        else "no_common_joint_dates"
        if admitted_external
        else "no_admitted_external"
    )
    selection: list[dict[str, object]] = [
        {
            "model_name": model,
            "admitted": model in admitted_external,
            "selected": model == reference,
            "mean_fzg": external_means.get(model),
            "common_n": len(external_dates),
            "date_start": external_dates[0] if external_dates else None,
            "date_end": external_dates[-1] if external_dates else None,
            "selection_status": selection_status if model in admitted_external else "not_admitted",
            "tied_best": model in tied,
            "external_roster": admitted_external,
        }
        for model in EXTERNAL_MODELS
    ]
    references: list[dict[str, object]] = [
        {
            "model_name": reference,
            "selection_status": selection_status,
            "common_n": len(external_dates),
            "date_start": external_dates[0] if external_dates else None,
            "date_end": external_dates[-1] if external_dates else None,
            "mean_fzg": external_means.get(reference) if reference is not None else None,
            "external_roster": admitted_external,
            "tied_best_models": tied,
            "tie_break": "registered_external_roster_order" if len(tied) > 1 else None,
        }
    ]
    roster = admitted_ml + ([reference] if reference is not None else [])
    members = [
        (model, info, side)
        for model in roster
        for info in PASS_ALL_INFORMATION_SETS
        for side in PASS_ALL_TAIL_SIDES
    ]
    common, main_ledger = _common_dates(members, indexed, sessions, scope="main")
    scenario_scores: list[dict[str, object]] = []
    daily_scores: list[dict[str, object]] = []
    for model in roster:
        for day in common:
            scores = [
                _scores(indexed[_source_key((model, info, side))][day])
                for info in PASS_ALL_INFORMATION_SETS
                for side in PASS_ALL_TAIL_SIDES
            ]
            daily_scores.append(
                {
                    "model_name": model,
                    "forecast_date": day,
                    "target_session_index": sessions[day],
                    "fzg": math.fsum(score[0] for score in scores) / 8,
                    "quantile_loss": math.fsum(score[1] for score in scores) / 8,
                    "exception": any(score[2] for score in scores),
                }
            )
    for member in members:
        scores = [_scores(indexed[_source_key(member)][day]) for day in common]
        scenario_scores.append(
            {
                "model_name": member[0],
                "information_set": member[1],
                "tail_side": member[2],
                "common_n": len(common),
                "mean_fzg": math.fsum(score[0] for score in scores) / len(scores)
                if scores
                else None,
                "mean_quantile_loss": math.fsum(score[1] for score in scores) / len(scores)
                if scores
                else None,
                "exception_dates": sum(score[2] for score in scores),
                "date_start": common[0] if common else None,
                "date_end": common[-1] if common else None,
                "reference_reused_across_information_sets": member[0] == reference,
            }
        )
    return {
        "gate_scenarios": gate_rows,
        "admissibility": admission,
        "external_selection": selection,
        "references": references,
        "scenario_scores": scenario_scores,
        "daily_scores": daily_scores,
        "common_sample": external_ledger + main_ledger,
        "comparison_status": [
            {
                "status": "no_admitted_candidates"
                if not roster
                else "no_common_joint_dates"
                if not common
                else "reference_unavailable"
                if reference is None
                else "ok",
                "reference_status": selection_status,
                "reference_model": reference,
                "model_roster": roster,
                "candidate_count": len(roster),
                "common_n": len(common),
                "date_start": common[0] if common else None,
                "date_end": common[-1] if common else None,
                "comparative_status": "available"
                if len(roster) >= 2 and common
                else "insufficient_candidates_or_dates",
            }
        ],
    }
