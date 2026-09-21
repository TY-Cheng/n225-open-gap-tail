# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Any,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_MODEL_NAMES,
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
    fzg_loss,
    forecast_eligible,
    index_forecast_sessions,
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
    for row in index_forecast_sessions(forecasts):
        if row.get("tail_level") is not None:
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
    ), scheduled_rows in sorted(grouped.items()):
        rows = sorted(
            valid_forecast_rows(scheduled_rows), key=lambda row: str(row["forecast_date"])
        )
        losses: Any = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var: Any = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        fz_rows = [row for row in rows if forecast_eligible(row, score="fz0")]
        fzg_rows = [row for row in rows if forecast_eligible(row, score="fzg")]
        breaches = losses > var
        alpha = 1.0 - tail_level
        kupiec = kupiec_pof_test(breaches=breaches, expected_probability=alpha)
        christoffersen = christoffersen_independence_test(
            breaches=breaches, session_indices=[row.get("target_session_index") for row in rows]
        )
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
                "recorded_rows": len(scheduled_rows),
                "joint_rows": sum(forecast_eligible(row, score="joint") for row in rows),
                "fz0_rows": len(fz_rows),
                "fzg_rows": len(fzg_rows),
                "fz0_excluded_rows": len(rows) - len(fz_rows),
                "date_start": str(rows[0]["forecast_date"]) if rows else None,
                "date_end": str(rows[-1]["forecast_date"]) if rows else None,
                "session_axis": rows[0].get("session_axis") if rows else None,
                "var_breach_rate": float(np.mean(breaches)) if rows else None,
                "expected_breach_rate": alpha,
                "exceedance_count": exceedance_count,
                "low_exceedance_warning": exceedance_count < 30,
                "kupiec_lr_uc": kupiec.get("lr_stat"),
                "kupiec_pvalue": kupiec.get("pvalue"),
                "christoffersen_lr_ind": christoffersen.get("lr_stat"),
                "christoffersen_pvalue": christoffersen.get("pvalue"),
                "christoffersen_status": christoffersen.get("status"),
                "christoffersen_transition_count": christoffersen.get("transition_count", 0),
                "christoffersen_skipped_transitions": christoffersen.get("skipped_transitions", 0),
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
                            fz_loss(
                                _required_float(row["realized_loss"]),
                                _required_float(row["var_forecast"]),
                                _required_float(row["es_forecast"]),
                                tail_level,
                            )
                            for row in fz_rows
                        ]
                    )
                ),
                "mean_fzg_loss": _safe_mean(
                    np.array(
                        [
                            fzg_loss(
                                _required_float(row["realized_loss"]),
                                _required_float(row["var_forecast"]),
                                _required_float(row["es_forecast"]),
                                tail_level,
                            )
                            for row in fzg_rows
                        ]
                    )
                ),
                "mean_quantile_loss_pct": _safe_mean(
                    np.array(
                        [
                            quantile_loss(100 * loss, 100 * forecast, tail_level)
                            for loss, forecast in zip(losses, var, strict=True)
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
    *,
    model_names: tuple[str, ...] = ML_TAIL_MODEL_NAMES,
) -> dict[str, object]:
    valid_rows = index_forecast_sessions(forecasts)
    matrix: list[dict[str, object]] = []
    sample_audit: list[dict[str, object]] = []
    dm_records: list[dict[str, object]] = []
    for loss_family in RESULT_MATRIX_LOSS_FAMILIES:
        for group in _result_matrix_tail_model_groups(
            valid_rows, loss_family=loss_family, model_names=model_names
        ):
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
            valid_rows, loss_family=loss_family, model_names=model_names
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
