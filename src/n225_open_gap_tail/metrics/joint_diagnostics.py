"""Q14 descriptive joint calibration and score sensitivity; never selection inputs."""

from __future__ import annotations

import json
from typing import cast

import numpy as np

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
    BOOTSTRAP_REPS,
    INFERENCE_RANDOM_SEED,
    _required_float,
)
from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.metrics.result_matrix_grouping import (
    _result_matrix_information_increment_groups,
    _result_matrix_tail_model_groups,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, moving_block_mean_draws


def joint_identification(
    loss: np.ndarray, var: np.ndarray, es: np.ndarray, tail_level: float
) -> tuple[np.ndarray, np.ndarray]:
    """Negative of Nolde & Ziegel (2017), eq. 2.7, in upper-loss convention.

    Zero conditional means identify a joint VaR/ES forecast under the paper's
    integrability, unique quantile and continuity at that quantile. A pooled
    mean is weaker; the diagnostics also report observed forecast ties.
    """
    alpha = 1.0 - tail_level
    return (loss > var).astype(float) - alpha, es - var - np.maximum(loss - var, 0) / alpha


def joint_elementary_score(
    loss: np.ndarray, var: np.ndarray, es: np.ndarray, tail_level: float, threshold: float
) -> np.ndarray:
    """Ziegel et al. (2017), Prop. 2.1 S_v2, with (x1,x2,y,v2)=(-q,-e,-L,-eta)."""
    return np.asarray(
        (es <= threshold) * (np.maximum(loss - var, 0) / (1.0 - tail_level) + var - threshold)
        + np.maximum(threshold - loss, 0)
    )


def _arrays(rows: list[dict[str, object]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    loss, var, es = (
        np.array([_required_float(row[column]) for row in rows])
        for column in ("realized_loss", "var_forecast", "es_forecast")
    )
    return loss, var, es


def build_joint_diagnostic_artifacts(
    forecasts: list[dict[str, object]],
    *,
    roster: list[dict[str, object]],
    ml_model_names: tuple[str, ...],
    references: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    by_scenario: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for row in forecasts:
        key = tuple(str(row[field]) for field in ("model_name", "tail_side", "information_set"))
        by_scenario.setdefault(cast(tuple[str, str, str], key), []).append(row)
    calibration: list[dict[str, object]] = []
    for scenario in roster:
        key = tuple(
            str(scenario[field]) for field in ("model_name", "tail_side", "information_set")
        )
        recorded = by_scenario.get(cast(tuple[str, str, str], key), [])
        rows = sorted(
            [row for row in recorded if forecast_eligible(row, score="joint")],
            key=lambda row: str(row["forecast_date"]),
        )
        record: dict[str, object] = {
            "model_name": key[0],
            "tail_side": key[1],
            "information_set": key[2],
            "joint_rows": len(rows),
            "recorded_rows": len(recorded),
            "scheduled_rows": scenario.get("scheduled_rows"),
            "date_start": rows[0]["forecast_date"] if rows else None,
            "date_end": rows[-1]["forecast_date"] if rows else None,
            "status": "ok" if rows else "unavailable_no_joint_rows",
            "sample_policy": "native_joint_eligible",
            "interval_scope": "pointwise_basic_block_bootstrap_not_joint_or_conditional_test",
        }
        if rows:
            loss, var, es = _arrays(rows)
            level = _required_float(rows[0]["tail_level"])
            moments = joint_identification(loss, var, es, level)
            block = max(5, round(len(rows) ** (1 / 3)))
            record.update(
                tail_level=level,
                tie_rate=float(np.mean(loss == var)),
                exceedance_count=int(np.sum(loss > var)),
                block_length=block,
                bootstrap_reps=BOOTSTRAP_REPS,
                low_exceedance_warning=int(np.sum(loss > var)) < 30,
            )
            for name, values in zip(("var_moment", "joint_es_moment"), moments, strict=True):
                mean = float(np.mean(values))
                # Same seed means paired resampling across the two components.
                draws = moving_block_mean_draws(
                    values,
                    reps=BOOTSTRAP_REPS,
                    block_length=block,
                    rng=np.random.default_rng(INFERENCE_RANDOM_SEED),
                    session_indices=cast(
                        list[int | None], [r.get("target_session_index") for r in rows]
                    ),
                )
                interval = 2 * mean - np.quantile(draws, [0.975, 0.025]) if draws.size else None
                record.update(
                    {
                        name: mean,
                        f"{name}_ci_lower": float(interval[0]) if interval is not None else None,
                        f"{name}_ci_upper": float(interval[1]) if interval is not None else None,
                        f"{name}_bootstrap_usable_reps": int(draws.size),
                    }
                )
        calibration.append(record)

    groups: list[tuple[str, dict[str, object]]] = []
    external = BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES
    for family, names in (("ml_models", ml_model_names), ("external_models", external)):
        # Refit schedules belong to the models, not to the comparison question.
        comparison = [
            {**row, "refit_frequency": "model_native_schedules"}
            for row in forecasts
            if row["model_name"] in names
        ]
        groups.extend(
            (family, group)
            for group in _result_matrix_tail_model_groups(
                comparison,
                loss_family="var_es_elementary",
                model_names=names,
            )
        )
    groups.extend(
        ("information_increment", group)
        for group in _result_matrix_information_increment_groups(
            forecasts,
            loss_family="var_es_elementary",
            model_names=ml_model_names,
        )
    )
    for reference in references:
        if reference.get("model_name") is None:
            continue
        ref, side = str(reference["model_name"]), str(reference["tail_side"])
        for info in PASS_ALL_INFORMATION_SETS:
            comparison = [
                {**row, "information_set": info, "refit_frequency": "model_native_schedules"}
                for row in forecasts
                if row["tail_side"] == side
                and (
                    (row["model_name"] in ml_model_names and row["information_set"] == info)
                    or (
                        row["model_name"] == ref and row["information_set"] == "target_history_only"
                    )
                )
            ]
            groups.extend(
                ("initial_cross_suite", {**group, "external_reference": ref})
                for group in _result_matrix_tail_model_groups(
                    comparison,
                    loss_family="var_es_elementary",
                    model_names=(ref, *ml_model_names),
                )
            )

    curves: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    for family, group in groups:
        curve, sample = _murphy_group(family, group)
        curves.extend(curve)
        samples.append(sample)
    return {
        "joint_calibration": calibration,
        "joint_murphy": curves,
        "joint_murphy_samples": samples,
    }


def _murphy_group(
    family: str, group: dict[str, object]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    dates = cast(list[str], group["common_dates"])
    entities = cast(list[str], group["entities"])
    by_entity = cast(dict[str, dict[str, dict[str, object]]], group["entity_rows"])
    context = {
        key: group.get(key)
        for key in (
            "target_family",
            "tail_side",
            "information_set",
            "fixed_model_name",
            "tail_level",
            "refit_frequency",
            "external_reference",
        )
    }
    context.update(comparison_family=family, common_n=len(dates))
    sample = {
        **context,
        "entities": json.dumps(entities),
        "common_dates": json.dumps(dates),
        "missing_entities": json.dumps(group.get("missing_entities") or []),
        "status": "ok" if dates else "unavailable_no_fixed_roster_common_dates",
        "threshold_grid_policy": (
            "101_quantiles_pooled_common_ES_and_realized_loss_including_bounds"
        ),
    }
    if not dates:
        return [], sample
    arrays = {entity: _arrays([by_entity[entity][day] for day in dates]) for entity in entities}
    loss = arrays[entities[0]][0]
    if any(not np.array_equal(item[0], loss) for item in arrays.values()):
        raise ValueError("Joint Murphy comparison targets disagree on shared dates")
    # ponytail: finite grid is descriptive, not an all-threshold dominance test.
    grid = np.unique(
        np.quantile(
            np.concatenate([loss, *(item[2] for item in arrays.values())]), np.linspace(0, 1, 101)
        )
    )
    curves = []
    for entity, (loss, var, es) in arrays.items():
        for index, threshold in enumerate(grid):
            scores = joint_elementary_score(
                loss, var, es, _required_float(group["tail_level"]), float(threshold)
            )
            curves.append(
                {
                    **context,
                    "entity": entity,
                    "entity_field": group["entity_field"],
                    "threshold_index": index,
                    "threshold_value": float(threshold),
                    "mean_elementary_score": float(np.mean(scores)),
                }
            )
    return curves, sample
