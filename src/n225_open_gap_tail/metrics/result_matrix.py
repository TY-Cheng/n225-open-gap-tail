# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def build_metric_records(
    forecasts: list[dict[str, object]],
    *,
    sample_policy: str = "per_model_oos",
    common_sample_status_value: str | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, float, str | None], list[dict[str, object]]] = {}
    for row in forecasts:
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True:
            grouped.setdefault(
                (
                    str(row["model_name"]),
                    str(row.get("target_family") or "full_gap_settle_to_open"),
                    str(row.get("information_set") or "target_history_only"),
                    _required_float(row["tail_level"]),
                    str(row["refit_frequency"]) if row.get("refit_frequency") else None,
                ),
                [],
            ).append(row)
    records: list[dict[str, object]] = []
    for (model, target_family, information_set, tail_level, refit_frequency), rows in sorted(
        grouped.items()
    ):
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
                "mcs_status": "available_in_loss_matrix_artifact",
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
    valid_rows = _valid_forecast_rows(forecasts)
    matrix: list[dict[str, object]] = []
    sample_audit: list[dict[str, object]] = []
    dm_records: list[dict[str, object]] = []
    mcs_records: list[dict[str, object]] = []
    for loss_family in RESULT_MATRIX_LOSS_FAMILIES:
        for group in _result_matrix_tail_model_groups(valid_rows, loss_family=loss_family):
            group_rows, audit = _build_result_matrix_group(
                group=group,
                loss_family=loss_family,
                comparison_family="tail_model_family",
                comparison_axis="model_family",
                claim_scope="restricted_model_comparison_not_headline",
                headline_claim_allowed=False,
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
            mcs_records.extend(
                _build_result_matrix_mcs_records(
                    group=group,
                    loss_family=loss_family,
                    comparison_family="tail_model_family",
                    comparison_axis="model_family",
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
                claim_scope="restricted_model_comparison_not_headline",
                headline_claim_allowed=False,
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
        "mcs": mcs_records,
        "notes": _result_matrix_notes(matrix, sample_audit, dm_records, mcs_records),
    }


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
    grouped: dict[tuple[str, str, float, str, str], dict[str, dict[str, dict[str, object]]]] = {}
    for row in forecasts:
        if not _result_row_eligible(row, loss_family):
            continue
        model_name = str(row["model_name"])
        if model_name not in ML_TAIL_MODEL_NAMES:
            continue
        target_family, _, tail_level, refit_frequency = _result_matrix_group_key(row)
        key = (target_family, model_name, tail_level, refit_frequency, loss_family)
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
        target_family, model_name, tail_level, refit_frequency, _ = key
        result.append(
            {
                **_result_matrix_group_payload(
                    key=(target_family, model_name, tail_level, refit_frequency),
                    entities=available_sets,
                    entity_field="information_set",
                    entity_rows=entity_rows,
                    common_dates=common_dates,
                ),
                "fixed_model_name": model_name,
            }
        )
    return result


def _result_matrix_group_key(row: Mapping[str, object]) -> tuple[str, str, float, str]:
    return (
        str(row.get("target_family") or "full_gap_settle_to_open"),
        str(row.get("information_set") or "target_history_only"),
        _required_float(row["tail_level"]),
        str(row.get("refit_frequency") or ""),
    )


def _result_matrix_group_payload(
    *,
    key: tuple[str, str, float, str],
    entities: list[str],
    entity_field: str,
    entity_rows: dict[str, dict[str, dict[str, object]]],
    common_dates: list[str],
) -> dict[str, object]:
    target_family, information_or_model, tail_level, refit_frequency = key
    return {
        "target_family": target_family,
        "information_set": information_or_model if entity_field == "model_name" else None,
        "fixed_model_name": information_or_model if entity_field == "information_set" else None,
        "tail_level": tail_level,
        "refit_frequency": refit_frequency or None,
        "entities": entities,
        "entity_field": entity_field,
        "entity_rows": entity_rows,
        "common_dates": common_dates,
    }


def _build_result_matrix_group(
    *,
    group: Mapping[str, object],
    loss_family: str,
    comparison_family: str,
    comparison_axis: str,
    claim_scope: str,
    headline_claim_allowed: bool,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    common_dates = cast(list[str], group["common_dates"])
    entities = cast(list[str], group["entities"])
    entity_field = str(group["entity_field"])
    entity_rows = cast(dict[str, dict[str, dict[str, object]]], group["entity_rows"])
    common_n = len(common_dates)
    joint_exception_count = _joint_exception_count(entity_rows, entities, common_dates)
    audit = _result_matrix_sample_audit_record(
        group=group,
        comparison_family=comparison_family,
        comparison_axis=comparison_axis,
        loss_family=loss_family,
        common_n=common_n,
        joint_exception_count=joint_exception_count,
    )
    records: list[dict[str, object]] = []
    if common_n < RESULT_MATRIX_MIN_METRIC_ROWS:
        for entity in entities:
            records.append(
                _result_matrix_unavailable_row(
                    group=group,
                    entity=entity,
                    entity_field=entity_field,
                    comparison_family=comparison_family,
                    comparison_axis=comparison_axis,
                    loss_family=loss_family,
                    common_n=common_n,
                    joint_exception_count=joint_exception_count,
                    status="unavailable_insufficient_common_rows_for_metrics",
                    claim_scope=claim_scope,
                    headline_claim_allowed=headline_claim_allowed,
                )
            )
        return records, audit
    for entity in entities:
        rows = [entity_rows[entity][forecast_date] for forecast_date in common_dates]
        records.append(
            _result_matrix_metric_row(
                rows=rows,
                group=group,
                entity=entity,
                entity_field=entity_field,
                comparison_family=comparison_family,
                comparison_axis=comparison_axis,
                loss_family=loss_family,
                common_n=common_n,
                joint_exception_count=joint_exception_count,
                claim_scope=claim_scope,
                headline_claim_allowed=headline_claim_allowed,
            )
        )
    return records, audit


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


def _result_matrix_sample_audit_record(
    *,
    group: Mapping[str, object],
    comparison_family: str,
    comparison_axis: str,
    loss_family: str,
    common_n: int,
    joint_exception_count: int,
) -> dict[str, object]:
    common_dates = cast(list[str], group["common_dates"])
    tail_level = _required_float(group["tail_level"])
    return {
        "comparison_family": comparison_family,
        "comparison_axis": comparison_axis,
        "sample_policy": "restricted_tail_model_common_sample",
        "loss_family": loss_family,
        "claim_scope": "restricted_model_comparison_not_headline",
        "headline_claim_allowed": False,
        "target_family": group.get("target_family"),
        "information_set": group.get("information_set"),
        "model_name": group.get("fixed_model_name"),
        "tail_level": tail_level,
        "refit_frequency": group.get("refit_frequency"),
        "entities_json": json.dumps(cast(list[str], group["entities"]), sort_keys=True),
        "common_n": common_n,
        "date_start": common_dates[0] if common_dates else None,
        "date_end": common_dates[-1] if common_dates else None,
        "joint_exception_count": joint_exception_count,
        "joint_exception_rate": joint_exception_count / common_n if common_n else None,
        "metric_status": "ok"
        if common_n >= RESULT_MATRIX_MIN_METRIC_ROWS
        else "unavailable_insufficient_common_rows_for_metrics",
        "dm_gate_status": _result_matrix_dm_gate_status(
            loss_family, common_n, joint_exception_count
        ),
        "mcs_gate_status": _result_matrix_mcs_gate_status(
            loss_family, common_n, joint_exception_count
        ),
        "minimum_common_rows_for_metrics": RESULT_MATRIX_MIN_METRIC_ROWS,
        "minimum_common_rows_for_dm": RESULT_MATRIX_MIN_DM_ROWS,
        "minimum_joint_exceptions_for_dm": RESULT_MATRIX_MIN_DM_EXCEPTIONS,
        "minimum_common_rows_for_mcs": RESULT_MATRIX_MIN_MCS_ROWS,
        "minimum_joint_exceptions_for_mcs": RESULT_MATRIX_MIN_MCS_EXCEPTIONS,
    }


def _result_matrix_metric_row(
    *,
    rows: list[dict[str, object]],
    group: Mapping[str, object],
    entity: str,
    entity_field: str,
    comparison_family: str,
    comparison_axis: str,
    loss_family: str,
    common_n: int,
    joint_exception_count: int,
    claim_scope: str,
    headline_claim_allowed: bool,
) -> dict[str, object]:
    losses = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
    var = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
    tail_level = _required_float(group["tail_level"])
    breaches = losses > var
    exception_count = int(np.sum(breaches))
    exception_rate = float(np.mean(breaches)) if common_n else None
    expected_rate = 1.0 - tail_level
    kupiec = kupiec_pof_test(breaches=breaches, expected_probability=expected_rate)
    christoffersen = christoffersen_independence_test(breaches=breaches)
    quantile_losses = np.array(
        [
            quantile_loss(loss, forecast, tail_level)
            for loss, forecast in zip(losses, var, strict=True)
        ],
        dtype=float,
    )
    if loss_family == "var_es_fz_loss":
        es = np.array([_required_float(row["es_forecast"]) for row in rows], dtype=float)
        fz_losses = np.array(
            [
                fz_loss(loss, var_value, es_value, tail_level)
                for loss, var_value, es_value in zip(losses, var, es, strict=True)
            ],
            dtype=float,
        )
        fz_losses = fz_losses[np.isfinite(fz_losses)]
    else:
        fz_losses = np.array([], dtype=float)
    mean_quantile_loss = _safe_mean(quantile_losses)
    mean_fz_loss = _safe_mean(fz_losses)
    absolute_coverage_error = (
        abs(float(exception_rate) - expected_rate) if exception_rate is not None else None
    )
    metric_value = {
        "var_quantile_loss": mean_quantile_loss,
        "var_coverage": absolute_coverage_error,
        "var_es_fz_loss": mean_fz_loss,
    }[loss_family]
    row = {
        "comparison_family": comparison_family,
        "comparison_axis": comparison_axis,
        "sample_policy": "restricted_tail_model_common_sample",
        "loss_family": loss_family,
        "claim_scope": claim_scope,
        "headline_claim_allowed": headline_claim_allowed,
        "target_family": group.get("target_family"),
        "information_set": entity
        if entity_field == "information_set"
        else group.get("information_set"),
        "model_name": entity if entity_field == "model_name" else group.get("fixed_model_name"),
        "tail_level": tail_level,
        "refit_frequency": group.get("refit_frequency"),
        "common_n": common_n,
        "date_start": str(rows[0]["forecast_date"]) if rows else None,
        "date_end": str(rows[-1]["forecast_date"]) if rows else None,
        "exception_count": exception_count,
        "exception_rate": exception_rate,
        "expected_exception_rate": expected_rate,
        "absolute_coverage_error": absolute_coverage_error,
        "zero_exception_flag": exception_count == 0,
        "tail_event_power_status": _tail_event_power_status(joint_exception_count),
        "kupiec_lr_uc": kupiec.get("lr_stat"),
        "kupiec_pvalue": kupiec.get("pvalue"),
        "christoffersen_lr_ind": christoffersen.get("lr_stat"),
        "christoffersen_pvalue": christoffersen.get("pvalue"),
        "mean_quantile_loss": mean_quantile_loss,
        "mean_fz_loss": mean_fz_loss,
        "metric_value": metric_value,
        "metric_status": "ok",
        "joint_exception_count": joint_exception_count,
        "fz_interpretation_status": _fz_interpretation_status(
            loss_family, exception_count, joint_exception_count
        ),
        "deng_qiu_reference_role": "scoring_function_context_not_exact_test",
    }
    return row


def _result_matrix_unavailable_row(
    *,
    group: Mapping[str, object],
    entity: str,
    entity_field: str,
    comparison_family: str,
    comparison_axis: str,
    loss_family: str,
    common_n: int,
    joint_exception_count: int,
    status: str,
    claim_scope: str,
    headline_claim_allowed: bool,
) -> dict[str, object]:
    return {
        "comparison_family": comparison_family,
        "comparison_axis": comparison_axis,
        "sample_policy": "restricted_tail_model_common_sample",
        "loss_family": loss_family,
        "claim_scope": claim_scope,
        "headline_claim_allowed": headline_claim_allowed,
        "target_family": group.get("target_family"),
        "information_set": entity
        if entity_field == "information_set"
        else group.get("information_set"),
        "model_name": entity if entity_field == "model_name" else group.get("fixed_model_name"),
        "tail_level": group.get("tail_level"),
        "refit_frequency": group.get("refit_frequency"),
        "common_n": common_n,
        "date_start": None,
        "date_end": None,
        "exception_count": None,
        "exception_rate": None,
        "expected_exception_rate": None,
        "absolute_coverage_error": None,
        "zero_exception_flag": None,
        "tail_event_power_status": _tail_event_power_status(joint_exception_count),
        "kupiec_lr_uc": None,
        "kupiec_pvalue": None,
        "christoffersen_lr_ind": None,
        "christoffersen_pvalue": None,
        "mean_quantile_loss": None,
        "mean_fz_loss": None,
        "metric_value": None,
        "metric_status": status,
        "joint_exception_count": joint_exception_count,
        "fz_interpretation_status": "unavailable_insufficient_common_rows",
        "deng_qiu_reference_role": "scoring_function_context_not_exact_test",
    }


def _build_result_matrix_dm_records(
    *,
    group: Mapping[str, object],
    loss_family: str,
    comparison_family: str,
    comparison_axis: str,
    baseline_entity: str,
    entity_field: str,
) -> list[dict[str, object]]:
    entities = cast(list[str], group["entities"])
    common_dates = cast(list[str], group["common_dates"])
    entity_rows = cast(dict[str, dict[str, dict[str, object]]], group["entity_rows"])
    if baseline_entity not in entities:
        return []
    records: list[dict[str, object]] = []
    for candidate in entities:
        if candidate == baseline_entity:
            continue
        common_n = len(common_dates)
        joint_exception_count = _joint_exception_count(
            entity_rows,
            [baseline_entity, candidate],
            common_dates,
        )
        gate_status = _result_matrix_dm_gate_status(loss_family, common_n, joint_exception_count)
        baseline_losses = _result_matrix_loss_values(
            [entity_rows[baseline_entity][forecast_date] for forecast_date in common_dates],
            loss_family=loss_family,
        )
        candidate_losses = _result_matrix_loss_values(
            [entity_rows[candidate][forecast_date] for forecast_date in common_dates],
            loss_family=loss_family,
        )
        diffs = candidate_losses - baseline_losses
        diffs = diffs[np.isfinite(diffs)]
        mean_diff = _safe_mean(diffs)
        block_length = max(5, round(len(diffs) ** (1.0 / 3.0))) if len(diffs) else None
        pvalue = (
            _moving_block_one_sided_pvalue(
                diffs,
                observed_mean=mean_diff,
                reps=BOOTSTRAP_REPS,
                block_length=int(block_length),
                rng=np.random.default_rng(INFERENCE_RANDOM_SEED),
            )
            if gate_status == "ok_block_bootstrap_dm"
            and mean_diff is not None
            and block_length is not None
            else None
        )
        records.append(
            {
                "comparison_family": comparison_family,
                "comparison_axis": comparison_axis,
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": loss_family,
                "claim_scope": "restricted_model_comparison_not_headline",
                "headline_claim_allowed": False,
                "target_family": group.get("target_family"),
                "information_set": group.get("information_set")
                if entity_field == "model_name"
                else baseline_entity,
                "model_name": group.get("fixed_model_name")
                if entity_field == "information_set"
                else baseline_entity,
                "tail_level": group.get("tail_level"),
                "refit_frequency": group.get("refit_frequency"),
                "baseline_entity": baseline_entity,
                "candidate_entity": candidate,
                "paired_rows": int(diffs.size),
                "common_n": common_n,
                "joint_exception_count": joint_exception_count,
                "mean_loss_diff_candidate_minus_baseline": mean_diff,
                "alternative": "candidate_mean_loss_less_than_baseline",
                "null_hypothesis": "E[loss_candidate_minus_baseline] >= 0",
                "pvalue_one_sided": pvalue,
                "reject_10pct": pvalue is not None and pvalue < 0.10,
                "bootstrap_reps": BOOTSTRAP_REPS,
                "bootstrap_seed": INFERENCE_RANDOM_SEED,
                "block_length": block_length,
                "method_note": PIPELINE_CONFIG.evaluation_policy.dm_method
                if gate_status == "ok_block_bootstrap_dm"
                else None,
                "inference_status": gate_status,
            }
        )
    return records


def _build_result_matrix_mcs_records(
    *,
    group: Mapping[str, object],
    loss_family: str,
    comparison_family: str,
    comparison_axis: str,
) -> list[dict[str, object]]:
    entities = cast(list[str], group["entities"])
    common_dates = cast(list[str], group["common_dates"])
    entity_rows = cast(dict[str, dict[str, dict[str, object]]], group["entity_rows"])
    common_n = len(common_dates)
    joint_exception_count = _joint_exception_count(entity_rows, entities, common_dates)
    gate_status = _result_matrix_mcs_gate_status(loss_family, common_n, joint_exception_count)
    if gate_status != "ok_hln_tmax_mcs":
        return [
            {
                "comparison_family": comparison_family,
                "comparison_axis": comparison_axis,
                "sample_policy": "restricted_tail_model_common_sample",
                "loss_family": loss_family,
                "claim_scope": "restricted_model_comparison_not_headline",
                "headline_claim_allowed": False,
                "target_family": group.get("target_family"),
                "information_set": group.get("information_set"),
                "model_name": entity,
                "tail_level": group.get("tail_level"),
                "refit_frequency": group.get("refit_frequency"),
                "rows": common_n,
                "joint_exception_count": joint_exception_count,
                "mean_loss": None,
                "included_in_mcs": False,
                "mcs_status": gate_status,
                "method_note": None,
                "block_length": None,
                "bootstrap_reps": BOOTSTRAP_REPS,
                "bootstrap_seed": INFERENCE_RANDOM_SEED,
            }
            for entity in entities
        ]
    block_length = max(5, round(common_n ** (1.0 / 3.0)))
    losses_by_entity = {
        entity: _result_matrix_loss_values(
            [entity_rows[entity][forecast_date] for forecast_date in common_dates],
            loss_family=loss_family,
        )
        for entity in entities
    }
    active = set(entities)
    mean_losses = {entity: _safe_mean(values) for entity, values in losses_by_entity.items()}
    rng = np.random.default_rng(INFERENCE_RANDOM_SEED)
    eliminated: set[str] = set()
    while len(active) > 1:
        ordered = sorted(active)
        matrix = np.column_stack([losses_by_entity[entity] for entity in ordered])
        result = _hln_tmax_mcs_step(
            matrix,
            reps=BOOTSTRAP_REPS,
            block_length=block_length,
            rng=rng,
        )
        pvalue = _optional_float(result["pvalue"])
        if pvalue is None or pvalue > MCS_ALPHA:
            break
        worst = max(active, key=lambda entity: (cast(float, mean_losses[entity]), entity))
        active.remove(worst)
        eliminated.add(worst)
    return [
        {
            "comparison_family": comparison_family,
            "comparison_axis": comparison_axis,
            "sample_policy": "restricted_tail_model_common_sample",
            "loss_family": loss_family,
            "claim_scope": "restricted_model_comparison_not_headline",
            "headline_claim_allowed": False,
            "target_family": group.get("target_family"),
            "information_set": group.get("information_set"),
            "model_name": entity,
            "tail_level": group.get("tail_level"),
            "refit_frequency": group.get("refit_frequency"),
            "rows": common_n,
            "joint_exception_count": joint_exception_count,
            "mean_loss": mean_losses[entity],
            "included_in_mcs": entity in active,
            "mcs_status": "ok",
            "method_note": PIPELINE_CONFIG.evaluation_policy.mcs_method,
            "block_length": block_length,
            "bootstrap_reps": BOOTSTRAP_REPS,
            "bootstrap_seed": INFERENCE_RANDOM_SEED,
            "eliminated_in_restricted_mcs": entity in eliminated,
        }
        for entity in entities
    ]


def _result_matrix_loss_values(rows: list[dict[str, object]], *, loss_family: str) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        loss = _required_float(row["realized_loss"])
        var = _required_float(row["var_forecast"])
        if loss_family == "var_quantile_loss":
            values.append(quantile_loss(loss, var, _required_float(row["tail_level"])))
        elif loss_family == "var_es_fz_loss":
            values.append(
                fz_loss(
                    loss,
                    var,
                    _required_float(row["es_forecast"]),
                    _required_float(row["tail_level"]),
                )
            )
        elif loss_family == "var_coverage":
            values.append(float(loss > var))
    return np.array(values, dtype=float)


def _joint_exception_count(
    entity_rows: Mapping[str, Mapping[str, Mapping[str, object]]],
    entities: list[str],
    common_dates: list[str],
) -> int:
    count = 0
    for forecast_date in common_dates:
        if any(
            _required_float(entity_rows[entity][forecast_date]["realized_loss"])
            > _required_float(entity_rows[entity][forecast_date]["var_forecast"])
            for entity in entities
        ):
            count += 1
    return count


def _result_matrix_dm_gate_status(
    loss_family: str,
    common_n: int,
    joint_exception_count: int,
) -> str:
    if loss_family == "var_coverage":
        return "unavailable_descriptive_coverage_metric"
    if common_n < RESULT_MATRIX_MIN_DM_ROWS:
        return "unavailable_insufficient_common_rows_for_inference"
    if joint_exception_count < RESULT_MATRIX_MIN_DM_EXCEPTIONS:
        return "unavailable_insufficient_tail_events_for_inference"
    return "ok_block_bootstrap_dm"


def _result_matrix_mcs_gate_status(
    loss_family: str,
    common_n: int,
    joint_exception_count: int,
) -> str:
    if loss_family == "var_coverage":
        return "unavailable_descriptive_coverage_metric"
    if common_n < RESULT_MATRIX_MIN_MCS_ROWS:
        return "unavailable_insufficient_common_rows_for_inference"
    if joint_exception_count < RESULT_MATRIX_MIN_MCS_EXCEPTIONS:
        return "unavailable_insufficient_tail_events_for_inference"
    return "ok_hln_tmax_mcs"


def _tail_event_power_status(joint_exception_count: int) -> str:
    if joint_exception_count <= 0:
        return "zero_joint_exceptions"
    if joint_exception_count < RESULT_MATRIX_MIN_DM_EXCEPTIONS:
        return "insufficient_tail_events_for_inference"
    if joint_exception_count < RESULT_MATRIX_MIN_MCS_EXCEPTIONS:
        return "limited_tail_events_dm_only"
    return "tail_events_sufficient_for_registered_inference"


def _fz_interpretation_status(
    loss_family: str,
    exception_count: int,
    joint_exception_count: int,
) -> str:
    if loss_family != "var_es_fz_loss":
        return "not_fz_loss"
    if exception_count == 0:
        return "zero_exception_degenerate"
    if joint_exception_count < RESULT_MATRIX_MIN_DM_EXCEPTIONS:
        return "insufficient_tail_events_for_inference"
    return "ok"


def _result_matrix_notes(
    matrix: list[dict[str, object]],
    sample_audit: list[dict[str, object]],
    dm_records: list[dict[str, object]],
    mcs_records: list[dict[str, object]],
) -> str:
    tail_model_rows = [
        row
        for row in sample_audit
        if row.get("comparison_axis") == "model_family"
        and row.get("loss_family") == "var_quantile_loss"
    ]
    max_common_n = max(
        (
            int(common_n)
            for row in tail_model_rows
            if (common_n := _optional_float(row.get("common_n"))) is not None
        ),
        default=0,
    )
    min_joint_exceptions = min(
        (
            int(joint_exception_count)
            for row in tail_model_rows
            if (joint_exception_count := _optional_float(row.get("joint_exception_count")))
            is not None
        ),
        default=0,
    )
    dm_unavailable = sum(
        1 for row in dm_records if str(row.get("inference_status") or "").startswith("unavailable")
    )
    mcs_unavailable = sum(
        1 for row in mcs_records if str(row.get("mcs_status") or "").startswith("unavailable")
    )
    zero_exception_rows = sum(1 for row in matrix if row.get("zero_exception_flag") is True)
    lines = [
        "# ML tail Result Matrix Notes",
        "",
        "This note is an artifact-level guide, not an automatic Results or Discussion draft.",
        "",
        "## Artifact taxonomy",
        "",
        "- `ml_tail_metrics.parquet` remains the headline ML tail information-set ladder.",
        "- `ml_tail_metrics_per_model.parquet` is diagnostic, not a cross-model comparison table.",
        "- `ml_tail_result_matrix.parquet` provides restricted VaR-only and VaR-ES "
        "comparisons on explicit common samples.",
        "",
        "## Claim boundary",
        "",
        "- Restricted direct-quantile rows are included only to compare against "
        "location-scale and POT-GPD on the same dates.",
        "- Restricted rows do not replace the headline direct-quantile evidence.",
        "- `headline_claim_allowed=false` marks restricted and diagnostic rows.",
        "",
        "## Short-sample and ES interpretation",
        "",
        f"- Largest restricted tail-model common sample observed: `{max_common_n}` rows.",
        "- Minimum joint exception count across VaR-only tail-model audits: "
        f"`{min_joint_exceptions}`.",
        f"- Rows with zero model-specific exceptions: `{zero_exception_rows}`.",
        f"- DM records unavailable by registered gates: `{dm_unavailable}`.",
        f"- MCS records unavailable by registered gates: `{mcs_unavailable}`.",
        "- Deng and Qiu (2021) motivate scoring-function comparison and caution "
        "with short ES backtests; this pipeline does not implement their exact test.",
        "- When exceptions are zero or sparse, FZ-loss rows are retained as "
        "diagnostics but must not be read as ES superiority evidence.",
        "",
        "## Safe interpretation",
        "",
        "- VaR-only rows compare quantile loss, coverage error, and exception diagnostics.",
        "- VaR-ES rows compare FZ scores only where valid VaR and ES forecasts exist.",
        "- No automatic ranking, dominance, or significance claim is generated by this note.",
        "",
    ]
    return "\n".join(lines)
