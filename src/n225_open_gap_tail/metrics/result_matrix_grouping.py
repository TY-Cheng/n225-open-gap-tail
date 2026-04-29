# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import *
from n225_open_gap_tail.panel.build import registered_ml_tail_information_sets


def _result_matrix_tail_model_groups(
    forecasts: list[dict[str, object]], *, loss_family: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, float, str], dict[str, dict[str, dict[str, object]]]] = {}
    for row in forecasts:
        if not _result_row_eligible(row, loss_family):
            continue
        key = _result_matrix_group_key(row)
        model_name = str(row["model_name"])
        if model_name not in ML_TAIL_MODEL_NAMES:
            continue
        grouped.setdefault(key, {}).setdefault(model_name, {})[str(row["forecast_date"])] = row
    result: list[dict[str, object]] = []
    for key, entity_rows in sorted(grouped.items()):
        if not all(model_name in entity_rows for model_name in ML_TAIL_MODEL_NAMES):
            continue
        common_dates = sorted(
            set.intersection(*(set(entity_rows[model]) for model in ML_TAIL_MODEL_NAMES))
        )
        result.append(
            _result_matrix_group_payload(
                key=key,
                entities=list(ML_TAIL_MODEL_NAMES),
                entity_field="model_name",
                entity_rows=entity_rows,
                common_dates=common_dates,
            )
        )
    return result


def _result_matrix_information_increment_groups(
    forecasts: list[dict[str, object]], *, loss_family: str
) -> list[dict[str, object]]:
    information_sets = registered_ml_tail_information_sets()
    grouped: dict[
        tuple[str, str, str, float, str, str], dict[str, dict[str, dict[str, object]]]
    ] = {}
    for row in forecasts:
        if not _result_row_eligible(row, loss_family):
            continue
        model_name = str(row["model_name"])
        if model_name not in ML_TAIL_MODEL_NAMES:
            continue
        target_family, tail_side, _, tail_level, refit_frequency = _result_matrix_group_key(row)
        key = (target_family, tail_side, model_name, tail_level, refit_frequency, loss_family)
        information_set = str(row.get("information_set") or "target_history_only")
        grouped.setdefault(key, {}).setdefault(information_set, {})[str(row["forecast_date"])] = row
    result: list[dict[str, object]] = []
    for key, entity_rows in sorted(grouped.items()):
        available_sets = [info for info in information_sets if info in entity_rows]
        if len(available_sets) < 2:
            continue
        common_dates = sorted(
            set.intersection(*(set(entity_rows[info]) for info in available_sets))
        )
        target_family, tail_side, model_name, tail_level, refit_frequency, _ = key
        result.append(
            {
                **_result_matrix_group_payload(
                    key=(target_family, tail_side, model_name, tail_level, refit_frequency),
                    entities=available_sets,
                    entity_field="information_set",
                    entity_rows=entity_rows,
                    common_dates=common_dates,
                ),
                "fixed_model_name": model_name,
            }
        )
    return result


def _result_matrix_group_key(row: Mapping[str, object]) -> tuple[str, str, str, float, str]:
    return (
        str(row.get("target_family") or "full_gap_settle_to_open"),
        str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
        str(row.get("information_set") or "target_history_only"),
        _required_float(row["tail_level"]),
        str(row.get("refit_frequency") or ""),
    )


def _result_matrix_group_payload(
    *,
    key: tuple[str, str, str, float, str],
    entities: list[str],
    entity_field: str,
    entity_rows: dict[str, dict[str, dict[str, object]]],
    common_dates: list[str],
) -> dict[str, object]:
    target_family, tail_side, information_or_model, tail_level, refit_frequency = key
    return {
        "target_family": target_family,
        "tail_side": tail_side,
        "information_set": information_or_model if entity_field == "model_name" else None,
        "fixed_model_name": information_or_model if entity_field == "information_set" else None,
        "tail_level": tail_level,
        "refit_frequency": refit_frequency or None,
        "entities": entities,
        "entity_field": entity_field,
        "entity_rows": entity_rows,
        "common_dates": common_dates,
    }


def _result_row_eligible(row: Mapping[str, object], loss_family: str) -> bool:
    if row.get("fit_status") != "ok" or row.get("is_valid_forecast") is not True:
        return False
    try:
        _required_float(row["realized_loss"])
        _required_float(row["var_forecast"])
        if loss_family == "var_es_fz_loss":
            _required_float(row["es_forecast"])
    except (KeyError, TypeError, ValueError, PipelineRunError):
        return False
    return loss_family in RESULT_MATRIX_LOSS_FAMILIES
