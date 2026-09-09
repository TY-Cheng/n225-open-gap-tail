from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MODEL_NAMES,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    RESULT_MATRIX_MIN_METRIC_ROWS,
    TAIL_SIDE_LEFT,
    TAIL_SIDE_RIGHT,
    _optional_float,
    _required_float,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, fz_loss

PASS_ALL_INFORMATION_SETS = (
    "japan_only",
    "japan_only_plus_us_close_core",
    "japan_only_plus_us_close_core_plus_japan_proxy",
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy",
)
PASS_ALL_TAIL_SIDES = (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)
PASS_ALL_LGBM_MODEL_ORDER = (
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
)
PASS_ALL_BENCHMARK_MODEL = "gjr_garch_evt"
PASS_ALL_BENCHMARK_INFORMATION_SET = "target_history_only"
PASS_ALL_MIN_ROWS = 450
PASS_ALL_COVERAGE_TOLERANCE = 0.025
PASS_ALL_TEST_ALPHA = 0.05


def coverage_admissibility_summary_rows(
    frame: pl.DataFrame,
    *,
    model_order: tuple[str, ...] = ML_TAIL_MODEL_NAMES,
    information_sets: tuple[str, ...] = PASS_ALL_INFORMATION_SETS,
    tail_sides: tuple[str, ...] = PASS_ALL_TAIL_SIDES,
) -> list[dict[str, object]]:
    required = {
        "model_name",
        "tail_side",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "kupiec_pvalue",
        "christoffersen_pvalue",
    }
    if frame.is_empty() or not required.issubset(frame.columns):
        return []
    expected_scenarios = {
        (tail_side, information_set)
        for tail_side in tail_sides
        for information_set in information_sets
    }
    rows_by_model: dict[str, dict[tuple[str, str], Mapping[str, object]]] = {}
    for row in frame.iter_rows(named=True):
        model_name = str(row.get("model_name") or "")
        scenario = (str(row.get("tail_side") or ""), str(row.get("information_set") or ""))
        if model_name in model_order and scenario in expected_scenarios:
            rows_by_model.setdefault(model_name, {})[scenario] = row
    output = []
    for model_name in model_order:
        model_rows = rows_by_model.get(model_name, {})
        eligible = {
            scenario
            for scenario, row in model_rows.items()
            if int(_optional_float(row.get("rows")) or 0) >= PASS_ALL_MIN_ROWS
        }
        breach = {scenario for scenario in eligible if _breach_band_passes(model_rows[scenario])}
        kupiec = {
            scenario
            for scenario in eligible
            if (_optional_float(model_rows[scenario].get("kupiec_pvalue")) or -1.0)
            >= PASS_ALL_TEST_ALPHA
        }
        christoffersen = {
            scenario
            for scenario in eligible
            if (_optional_float(model_rows[scenario].get("christoffersen_pvalue")) or -1.0)
            >= PASS_ALL_TEST_ALPHA
        }
        severities = [
            severity
            for scenario in eligible
            if (severity := _optional_float(model_rows[scenario].get("mean_exceedance_severity")))
            is not None
        ]
        output.append(
            {
                "model_name": model_name,
                "eligible_scenarios": len(eligible),
                "breach_passes": len(breach),
                "kupiec_passes": len(kupiec),
                "christoffersen_independence_passes": len(christoffersen),
                "mean_exceedance_severity_min": min(severities) if severities else None,
                "mean_exceedance_severity_max": max(severities) if severities else None,
                "coverage_admissible": (
                    eligible == expected_scenarios
                    and breach == expected_scenarios
                    and kupiec == expected_scenarios
                    and christoffersen == expected_scenarios
                ),
            }
        )
    return output


def pass_all_row_passes(
    row: Mapping[str, object],
    *,
    min_rows: int = PASS_ALL_MIN_ROWS,
    tolerance: float = PASS_ALL_COVERAGE_TOLERANCE,
    test_alpha: float = PASS_ALL_TEST_ALPHA,
) -> bool:
    rows = int(_optional_float(row.get("rows")) or 0)
    breach = _optional_float(row.get("var_breach_rate"))
    expected = _optional_float(row.get("expected_breach_rate"))
    kupiec = _optional_float(row.get("kupiec_pvalue"))
    christoffersen = _optional_float(row.get("christoffersen_pvalue"))
    if breach is None or kupiec is None or christoffersen is None:
        return False
    expected = 0.05 if expected is None else expected
    return (
        rows >= min_rows
        and abs(breach - expected) <= tolerance
        and kupiec >= test_alpha
        and christoffersen >= test_alpha
    )


def _breach_band_passes(row: Mapping[str, object]) -> bool:
    breach = _optional_float(row.get("var_breach_rate"))
    expected = _optional_float(row.get("expected_breach_rate"))
    if breach is None:
        return False
    expected = 0.05 if expected is None else expected
    return abs(breach - expected) <= PASS_ALL_COVERAGE_TOLERANCE


def pass_all_lgbm_model_names(
    frame: pl.DataFrame,
    *,
    tail_sides: tuple[str, ...] = PASS_ALL_TAIL_SIDES,
    information_sets: tuple[str, ...] = PASS_ALL_INFORMATION_SETS,
    model_order: tuple[str, ...] = PASS_ALL_LGBM_MODEL_ORDER,
) -> tuple[str, ...]:
    required = {
        "model_name",
        "tail_side",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "kupiec_pvalue",
        "christoffersen_pvalue",
    }
    if frame.is_empty() or not required.issubset(frame.columns):
        return ()
    expected_scenarios = {
        (tail_side, information_set)
        for tail_side in tail_sides
        for information_set in information_sets
    }
    allowed_models = set(model_order)
    passed_by_model: dict[str, set[tuple[str, str]]] = {}
    for row in frame.iter_rows(named=True):
        model = str(row.get("model_name") or "")
        if model not in allowed_models:
            continue
        scenario = (str(row.get("tail_side") or ""), str(row.get("information_set") or ""))
        if scenario not in expected_scenarios:
            continue
        if pass_all_row_passes(row):
            passed_by_model.setdefault(model, set()).add(scenario)
    return tuple(model for model in model_order if passed_by_model.get(model) == expected_scenarios)


def benchmark_model_passes(
    frame: pl.DataFrame,
    *,
    model_name: str = PASS_ALL_BENCHMARK_MODEL,
    information_set: str = PASS_ALL_BENCHMARK_INFORMATION_SET,
    tail_sides: tuple[str, ...] = PASS_ALL_TAIL_SIDES,
) -> bool:
    required = {
        "model_name",
        "tail_side",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "kupiec_pvalue",
        "christoffersen_pvalue",
    }
    if frame.is_empty() or not required.issubset(frame.columns):
        return False
    expected_sides = set(tail_sides)
    passed_sides: set[str] = set()
    for row in frame.iter_rows(named=True):
        if str(row.get("model_name") or "") != model_name:
            continue
        row_information_set = str(row.get("information_set") or information_set)
        if row_information_set != information_set:
            continue
        tail_side = str(row.get("tail_side") or "")
        if tail_side in expected_sides and pass_all_row_passes(row):
            passed_sides.add(tail_side)
    return passed_sides == expected_sides


def select_external_references(
    forecasts: list[dict[str, object]],
    native_metrics: pl.DataFrame,
) -> dict[str, list[dict[str, object]]]:
    """Q8--Q13: both-tail native gates, then external-only shared FZ0 dates."""
    pool = BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES
    admitted = [model for model in pool if benchmark_model_passes(native_metrics, model_name=model)]
    ledger: list[dict[str, object]] = []
    references: list[dict[str, object]] = []
    for side in PASS_ALL_TAIL_SIDES:
        by_model: dict[str, dict[str, dict[str, object]]] = {model: {} for model in pool}
        for row in forecasts:
            model = str(row.get("model_name"))
            if (
                model not in pool
                or row.get("tail_side") != side
                or row.get("information_set") != PASS_ALL_BENCHMARK_INFORMATION_SET
                or not forecast_eligible(row, score="fz0")
            ):
                continue
            day = str(row["forecast_date"])
            if day in by_model[model]:
                raise ValueError(
                    "External reference selection requires one target/level/refit per model"
                )
            by_model[model][day] = row
        common = (
            sorted(set.intersection(*(set(by_model[model]) for model in admitted)))
            if admitted
            else []
        )
        scores: dict[str, float] = {}
        for day in common:
            if (
                len({_required_float(by_model[model][day]["realized_loss"]) for model in admitted})
                != 1
            ):
                raise ValueError(f"Inconsistent external comparison target on {day}")
        for model in pool:
            if model in admitted and common:
                scores[model] = sum(
                    fz_loss(
                        _required_float(by_model[model][day]["realized_loss"]),
                        _required_float(by_model[model][day]["var_forecast"]),
                        _required_float(by_model[model][day]["es_forecast"]),
                        _required_float(by_model[model][day]["tail_level"]),
                    )
                    for day in common
                ) / len(common)
            ledger.append(
                {
                    "model_name": model,
                    "tail_side": side,
                    "both_tail_coverage_admissible": model in admitted,
                    "native_fz0_rows": len(by_model[model]),
                    "selection_common_n": len(common),
                    "mean_fz_loss": scores.get(model),
                    "eligibility_status": (
                        "coverage_failed_or_unavailable"
                        if model not in admitted
                        else "no_fz0_forecasts"
                        if not by_model[model]
                        else "coverage_admissible"
                    ),
                }
            )
        selected = (
            min(scores, key=lambda model: (scores[model], pool.index(model)))
            if (scores and len(common) >= RESULT_MATRIX_MIN_METRIC_ROWS)
            else None
        )
        references.append(
            {
                "tail_side": side,
                "model_name": selected,
                "selection_common_n": len(common),
                "date_start": common[0] if common else None,
                "date_end": common[-1] if common else None,
                "mean_fz_loss": scores.get(selected) if selected else None,
                "selection_status": "ok"
                if selected
                else "unavailable_no_admissible_common_score_sample",
                "selection_sample_policy": "external_only_post_gate_common_fz0_dates",
                "minimum_score_rows": RESULT_MATRIX_MIN_METRIC_ROWS,
            }
        )
    return {"eligibility": ledger, "references": references}
