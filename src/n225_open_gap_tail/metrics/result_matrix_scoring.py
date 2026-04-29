# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


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
        "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
        "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
        "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
                "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
                "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
            "tail_side": group.get("tail_side") or PRIMARY_TAIL_SIDE,
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
