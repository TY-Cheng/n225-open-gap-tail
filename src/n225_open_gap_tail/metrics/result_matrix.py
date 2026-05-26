# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    np,
    PIPELINE_CONFIG,
    PRIMARY_TAIL_SIDE,
    RESULT_MATRIX_LOSS_FAMILIES,
    _required_float,
)
from n225_open_gap_tail.metrics.stat_utils import (
    _safe_mean,
    christoffersen_independence_test,
    fz_loss,
    kupiec_pof_test,
    quantile_loss,
    valid_forecast_rows,
)
from n225_open_gap_tail.metrics.result_matrix_grouping import (
    _result_matrix_information_increment_groups,
    _result_matrix_tail_model_groups,
)
from n225_open_gap_tail.metrics.result_matrix_notes import _result_matrix_notes
from n225_open_gap_tail.metrics.result_matrix_scoring import (
    _build_result_matrix_dm_records,
    _build_result_matrix_group,
)


def build_metric_records(
    forecasts: list[dict[str, object]],
    *,
    sample_policy: str = "per_model_oos",
    common_sample_status_value: str | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, float, str | None], list[dict[str, object]]] = {}
    for row in forecasts:
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True:
            grouped.setdefault(
                (
                    str(row["model_name"]),
                    str(row.get("target_family") or "full_gap_settle_to_open"),
                    str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
                    str(row.get("information_set") or "target_history_only"),
                    _required_float(row["tail_level"]),
                    str(row["refit_frequency"]) if row.get("refit_frequency") else None,
                ),
                [],
            ).append(row)
    records: list[dict[str, object]] = []
    for (
        model,
        target_family,
        tail_side,
        information_set,
        tail_level,
        refit_frequency,
    ), rows in sorted(grouped.items()):
        losses: Any = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var: Any = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        es: Any = np.array([_required_float(row["es_forecast"]) for row in rows], dtype=float)
        breaches = losses > var
        alpha = 1.0 - tail_level
        kupiec = kupiec_pof_test(breaches=breaches, expected_probability=alpha)
        christoffersen = christoffersen_independence_test(breaches=breaches)
        exceedance_count = int(np.sum(breaches))
        records.append(
            {
                "model_name": model,
                "target_family": target_family,
                "tail_side": tail_side,
                "information_set": information_set,
                "tail_level": tail_level,
                "refit_frequency": refit_frequency,
                "sample_policy": sample_policy,
                "common_sample_status": common_sample_status_value,
                "rows": len(rows),
                "var_breach_rate": float(np.mean(breaches)) if rows else None,
                "expected_breach_rate": alpha,
                "exceedance_count": exceedance_count,
                "low_exceedance_warning": exceedance_count < 30,
                "kupiec_lr_uc": kupiec.get("lr_stat"),
                "kupiec_pvalue": kupiec.get("pvalue"),
                "christoffersen_lr_ind": christoffersen.get("lr_stat"),
                "christoffersen_pvalue": christoffersen.get("pvalue"),
                "dq_status": "unavailable_not_implemented",
                "mean_quantile_loss": _safe_mean(
                    np.array(
                        [
                            quantile_loss(loss, forecast, tail_level)
                            for loss, forecast in zip(losses, var, strict=True)
                        ]
                    )
                ),
                "mean_fz_loss": _safe_mean(
                    np.array(
                        [
                            fz_loss(loss, var_value, es_value, tail_level)
                            for loss, var_value, es_value in zip(
                                losses,
                                var,
                                es,
                                strict=True,
                            )
                        ]
                    )
                ),
                "mean_exceedance_severity": float(np.mean(losses[breaches] - var[breaches]))
                if np.any(breaches)
                else None,
            }
        )
    return records


def build_ml_tail_result_matrix_artifacts(
    forecasts: list[dict[str, object]],
) -> dict[str, object]:
    valid_rows = valid_forecast_rows(forecasts)
    matrix: list[dict[str, object]] = []
    sample_audit: list[dict[str, object]] = []
    dm_records: list[dict[str, object]] = []
    for loss_family in RESULT_MATRIX_LOSS_FAMILIES:
        for group in _result_matrix_tail_model_groups(valid_rows, loss_family=loss_family):
            group_rows, audit = _build_result_matrix_group(
                group=group,
                loss_family=loss_family,
                comparison_family="tail_model_family",
                comparison_axis="model_family",
                claim_scope="restricted_model_comparison_not_primary",
                primary_claim_allowed=False,
            )
            matrix.extend(group_rows)
            sample_audit.append(audit)
            dm_records.extend(
                _build_result_matrix_dm_records(
                    group=group,
                    loss_family=loss_family,
                    comparison_family="tail_model_family",
                    comparison_axis="model_family",
                    baseline_entity=ML_TAIL_DIRECT_QUANTILE_MODEL,
                    entity_field="model_name",
                )
            )
        for group in _result_matrix_information_increment_groups(
            valid_rows, loss_family=loss_family
        ):
            group_rows, audit = _build_result_matrix_group(
                group=group,
                loss_family=loss_family,
                comparison_family="information_set_ladder",
                comparison_axis="information_set_increment",
                claim_scope="restricted_model_comparison_not_primary",
                primary_claim_allowed=False,
            )
            matrix.extend(group_rows)
            sample_audit.append(audit)
            dm_records.extend(
                _build_result_matrix_dm_records(
                    group=group,
                    loss_family=loss_family,
                    comparison_family="information_set_ladder",
                    comparison_axis="information_set_increment",
                    baseline_entity=PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
                    entity_field="information_set",
                )
            )
    return {
        "matrix": matrix,
        "sample_audit": sample_audit,
        "dm": dm_records,
        "notes": _result_matrix_notes(matrix, sample_audit, dm_records),
    }
