# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    cast,
    CLAIMS_LEVEL,
    delayed,
    EvaluationResult as EvaluationResult,
    json,
    ML_TAIL_ANCHOR_INFORMATION_SET,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_MODEL_NAMES,
    ML_TAIL_POT_GPD_MODEL_NAMES,
    ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES,
    ML_TAIL_REFIT_FREQUENCY,
    Parallel,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
    pl,
    stable_hash,
    TAIL_LEVELS,
    TAIL_SIDE_BOTH,
    tail_side_values,
    validate_worker_payload,
    _bounded_workers,
    _evaluation_log,
    _set_nested_thread_limits,
)
from n225_open_gap_tail.forecasting._guards import _assert_leakage_gate
from n225_open_gap_tail.forecasting.artifacts import (
    _forecast_shard_id,
    _read_manifest,
    _update_manifest,
    _write_json,
    _write_parquet,
)
from n225_open_gap_tail.inference.core import build_common_sample_artifacts
from n225_open_gap_tail.metrics.information import (
    _assert_run_config_compatible,
    _gold_artifact_path,
    build_incremental_information_records,
)
from n225_open_gap_tail.metrics.result_matrix import build_ml_tail_result_matrix_artifacts
from n225_open_gap_tail.models.ml_tail_oof import (
    build_ml_tail_feature_unavailability_date_records,
    build_ml_tail_feature_unavailability_records,
)
from n225_open_gap_tail.panel.build import (
    ml_tail_feature_columns_for_information_set,
    registered_ml_tail_information_sets,
)
from n225_open_gap_tail.forecasting._ml_tail_shards import (
    _compute_and_write_ml_tail_shard_atomic,
    _expected_ml_tail_shard_manifest,
    _load_active_ml_tail_shards,
    _ml_tail_leakage_context,
    _partition_ml_tail_shard_jobs,
    _sort_ml_tail_rows,
    _warn_orphan_ml_tail_shards,
)


def evaluate_ml_tail_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
    tail_side: str = TAIL_SIDE_BOTH,
    resume: bool = True,
) -> EvaluationResult:
    panel_path = _gold_artifact_path(
        run_dir, "modeling_panel", run_dir / "panel" / "modeling_panel.parquet"
    )
    coverage_path = _gold_artifact_path(
        run_dir, "feature_coverage", run_dir / "panel" / "feature_coverage.parquet"
    )
    if not panel_path.exists():
        raise PipelineRunError(f"Missing modeling panel: {panel_path}")
    if not coverage_path.exists():
        raise PipelineRunError(f"Missing feature coverage: {coverage_path}")
    _assert_run_config_compatible(run_dir, force=force)
    _assert_leakage_gate(run_dir)
    _set_nested_thread_limits()
    _evaluation_log(f"start ML tail run_id={run_dir.name} workers={workers}")
    forecast_root = run_dir / "forecasts"
    metrics_root = run_dir / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    information_sets = registered_ml_tail_information_sets()
    coverage_rows = pl.read_parquet(coverage_path).to_dicts()
    manifest = _read_manifest(run_dir)
    leakage_context = _ml_tail_leakage_context(run_dir)
    jobs: list[dict[str, object]] = []
    active_tail_sides = tail_side_values(tail_side)
    for active_tail_side in active_tail_sides:
        for tail_level in TAIL_LEVELS:
            for model_name in ML_TAIL_MODEL_NAMES:
                for information_set in information_sets:
                    candidate_features = ml_tail_feature_columns_for_information_set(
                        coverage_rows,
                        information_set=information_set,
                    )
                    shard_id = _forecast_shard_id(
                        model_name,
                        tail_level,
                        information_set=information_set,
                        target_family=PIPELINE_CONFIG.target_policy.primary_target_family,
                        tail_side=active_tail_side,
                        refit_frequency=ML_TAIL_REFIT_FREQUENCY,
                    )
                    jobs.append(
                        {
                            "panel_path": str(panel_path),
                            "coverage_path": str(coverage_path),
                            "run_dir": str(run_dir),
                            "tail_side": active_tail_side,
                            "tail_level": tail_level,
                            "target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
                            "information_set": information_set,
                            "model_name": model_name,
                            "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                            "shard_id": shard_id,
                            "candidate_feature_hash": stable_hash(candidate_features),
                        }
                    )
    for payload in jobs:
        validate_worker_payload(payload)
        payload["expected_shard_manifest"] = _expected_ml_tail_shard_manifest(
            payload,
            manifest=manifest,
            leakage_context=leakage_context,
        )
    n_jobs = _bounded_workers(workers)
    _warn_orphan_ml_tail_shards(run_dir, active_shard_ids={str(job["shard_id"]) for job in jobs})
    if resume:
        cached_jobs, compute_jobs = _partition_ml_tail_shard_jobs(run_dir, jobs)
    else:
        cached_jobs, compute_jobs = [], jobs
    _evaluation_log(
        "ML tail shards queued="
        f"{len(jobs)} cached={len(cached_jobs)} compute={len(compute_jobs)} "
        f"resume={resume} n_jobs={n_jobs}"
    )
    if compute_jobs:
        if n_jobs == 1:
            for payload in compute_jobs:
                _compute_and_write_ml_tail_shard_atomic(payload)
        else:
            Parallel(n_jobs=n_jobs, backend=PIPELINE_CONFIG.model_policy.joblib_backend)(
                delayed(_compute_and_write_ml_tail_shard_atomic)(payload)
                for payload in compute_jobs
            )
    forecasts, diagnostics, failures = _load_active_ml_tail_shards(run_dir, jobs)
    forecasts = _sort_ml_tail_rows(forecasts)
    diagnostics = _sort_ml_tail_rows(diagnostics)
    failures = _sort_ml_tail_rows(failures)
    if not forecasts and not diagnostics and failures:
        _evaluation_log(
            "ML tail active shards contain failures only; downstream metrics may be empty"
        )
    forecast_path = forecast_root / "ml_tail_forecasts.parquet"
    diagnostics_path = forecast_root / "ml_tail_fit_diagnostics.parquet"
    failures_path = forecast_root / "ml_tail_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _evaluation_log(f"wrote ML tail forecasts: {forecast_path} rows={len(forecasts)}")
    _write_parquet(diagnostics_path, diagnostics)
    _evaluation_log(f"wrote ML tail diagnostics: {diagnostics_path} rows={len(diagnostics)}")
    _write_parquet(failures_path, failures)
    _evaluation_log(f"wrote ML tail failures: {failures_path} rows={len(failures)}")
    artifacts = build_common_sample_artifacts(
        forecasts,
        suite="ml_tail",
        anchor_model=ML_TAIL_DIRECT_QUANTILE_MODEL,
        anchor_information_set=ML_TAIL_ANCHOR_INFORMATION_SET,
    )
    primary_forecasts = cast(list[dict[str, object]], artifacts["primary_forecasts"])
    metrics = cast(list[dict[str, object]], artifacts["primary_metrics"])
    incremental = build_incremental_information_records(
        primary_forecasts,
        baseline_information_set=PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
    )
    feature_unavailability = build_ml_tail_feature_unavailability_records(forecasts)
    feature_unavailability_dates = build_ml_tail_feature_unavailability_date_records(forecasts)
    result_matrix_artifacts = build_ml_tail_result_matrix_artifacts(forecasts)
    evt_shape_stability = _evt_shape_stability_records(diagnostics)
    extremal_index_diagnostics = _extremal_index_records(diagnostics)
    evt_cap_sensitivity = _evt_cap_sensitivity_records(diagnostics)
    evt_threshold_sensitivity = _evt_threshold_sensitivity_records(diagnostics)
    evt_body_tail_diagnostics = _evt_body_tail_diagnostic_records(diagnostics)
    evt_route_gate_status = _evt_route_gate_status_records(diagnostics)
    evt_route_availability = _evt_route_availability_records(diagnostics)
    evt_diagnostic_variant_metrics = _evt_diagnostic_variant_metric_records(
        cast(list[dict[str, object]], artifacts["per_model_metrics"])
    )
    _write_parquet(metrics_root / "ml_tail_metrics.parquet", metrics)
    _write_parquet(
        metrics_root / "ml_tail_metrics_per_model.parquet",
        cast(list[dict[str, object]], artifacts["per_model_metrics"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_model_eviction.parquet",
        cast(list[dict[str, object]], artifacts["model_eviction"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_loss_matrix.parquet",
        cast(list[dict[str, object]], artifacts["loss_matrix"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_dm_inference.parquet",
        cast(list[dict[str, object]], artifacts["dm_inference"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_murphy.parquet",
        cast(list[dict[str, object]], artifacts["murphy"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_stress_windows.parquet",
        cast(list[dict[str, object]], artifacts["stress_windows"]),
    )
    _write_parquet(metrics_root / "ml_tail_incremental_information.parquet", incremental)
    _write_parquet(
        metrics_root / "ml_tail_feature_unavailability.parquet",
        feature_unavailability,
    )
    _write_parquet(
        metrics_root / "ml_tail_feature_unavailability_dates.parquet",
        feature_unavailability_dates,
    )
    _write_parquet(
        metrics_root / "ml_tail_result_matrix.parquet",
        cast(list[dict[str, object]], result_matrix_artifacts["matrix"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_result_matrix_sample_audit.parquet",
        cast(list[dict[str, object]], result_matrix_artifacts["sample_audit"]),
    )
    _write_parquet(
        metrics_root / "ml_tail_result_matrix_dm.parquet",
        cast(list[dict[str, object]], result_matrix_artifacts["dm"]),
    )
    _write_parquet(metrics_root / "evt_shape_stability.parquet", evt_shape_stability)
    _write_parquet(
        metrics_root / "extremal_index_diagnostics.parquet",
        extremal_index_diagnostics,
    )
    _write_parquet(metrics_root / "evt_cap_sensitivity.parquet", evt_cap_sensitivity)
    _write_parquet(metrics_root / "evt_threshold_sensitivity.parquet", evt_threshold_sensitivity)
    _write_parquet(metrics_root / "evt_body_tail_diagnostics.parquet", evt_body_tail_diagnostics)
    _write_parquet(metrics_root / "evt_route_gate_status.parquet", evt_route_gate_status)
    _write_parquet(metrics_root / "evt_route_availability.parquet", evt_route_availability)
    _write_parquet(
        metrics_root / "evt_diagnostic_variant_metrics.parquet", evt_diagnostic_variant_metrics
    )
    (metrics_root / "ml_tail_result_matrix_notes.md").write_text(
        cast(str, result_matrix_artifacts["notes"]),
        encoding="utf-8",
    )
    _write_json(
        metrics_root / "ml_tail_status.json",
        {
            "claims_level": CLAIMS_LEVEL,
            "claim_level": CLAIMS_LEVEL,
            "config_hash": PIPELINE_CONFIG.config_hash(),
            "suite": "ml_tail",
            "status": "completed_lightgbm_ml_tail_models",
            "model_name": "ml_tail_lightgbm_model_registry",
            "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
            "forecast_rows": len(forecasts),
            "metric_rows": len(metrics),
            "per_model_metric_rows": len(
                cast(list[dict[str, object]], artifacts["per_model_metrics"])
            ),
            "loss_matrix_rows": len(cast(list[dict[str, object]], artifacts["loss_matrix"])),
            "feature_unavailability_rows": len(feature_unavailability),
            "feature_unavailability_date_rows": len(feature_unavailability_dates),
            "result_matrix_rows": len(
                cast(list[dict[str, object]], result_matrix_artifacts["matrix"])
            ),
            "evt_shape_stability_rows": len(evt_shape_stability),
            "extremal_index_diagnostic_rows": len(extremal_index_diagnostics),
            "evt_cap_sensitivity_rows": len(evt_cap_sensitivity),
            "evt_threshold_sensitivity_rows": len(evt_threshold_sensitivity),
            "evt_body_tail_diagnostic_rows": len(evt_body_tail_diagnostics),
            "evt_route_gate_status_rows": len(evt_route_gate_status),
            "evt_route_availability_rows": len(evt_route_availability),
            "evt_diagnostic_variant_metric_rows": len(evt_diagnostic_variant_metrics),
            "tail_sides": list(active_tail_sides),
            "result_matrix_sample_audit_rows": len(
                cast(list[dict[str, object]], result_matrix_artifacts["sample_audit"])
            ),
            "common_sample_status": artifacts["common_sample_status"],
            "failures": len(failures),
            "registered_information_sets": _registered_information_set_payload(),
            "implemented_components": list(ML_TAIL_MODEL_NAMES),
            "unavailable_components": {},
        },
    )
    _update_manifest(
        run_dir,
        {
            "ml_tail_eval_status": "completed_lightgbm_ml_tail_models",
            "ml_tail_forecast_rows": len(forecasts),
            "ml_tail_metric_rows": len(metrics),
            "ml_tail_tail_sides": list(active_tail_sides),
            "evt_shape_stability_rows": len(evt_shape_stability),
            "extremal_index_diagnostic_rows": len(extremal_index_diagnostics),
            "evt_cap_sensitivity_rows": len(evt_cap_sensitivity),
            "evt_threshold_sensitivity_rows": len(evt_threshold_sensitivity),
            "evt_body_tail_diagnostic_rows": len(evt_body_tail_diagnostics),
            "evt_route_gate_status_rows": len(evt_route_gate_status),
            "evt_route_availability_rows": len(evt_route_availability),
        },
    )
    _evaluation_log(
        f"complete ML tail run_id={run_dir.name} forecast_rows={len(forecasts)} "
        f"metric_rows={len(metrics)} failures={len(failures)}"
    )
    return EvaluationResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed_lightgbm_ml_tail_models",
    )


def _registered_information_set_payload() -> dict[str, object]:
    return {
        "model_a": PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
        "model_b": PIPELINE_CONFIG.feature_sets.ml_tail_model_b_information_set,
        "model_c": PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,
        "model_d": PIPELINE_CONFIG.feature_sets.ml_tail_model_d_information_set,
        "japan_only_features": PIPELINE_CONFIG.feature_sets.japan_only_features,
    }


def _evt_shape_stability_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if row.get("evt_variant") in (None, "empirical_standardized_tail"):
            continue
        base = _evt_base_record(row)
        records.append(
            {
                **base,
                "evt_shape": row.get("evt_shape"),
                "evt_shape_bin": row.get("evt_shape_bin"),
                "evt_scale": row.get("evt_scale"),
                "evt_shape_mle": row.get("evt_shape_mle"),
                "evt_scale_mle": row.get("evt_scale_mle"),
                "evt_xi_evi_anchor": row.get("evt_xi_evi_anchor"),
                "evt_cap_policy": row.get("evt_cap_policy"),
                "evt_cap_hit": row.get("evt_cap_hit"),
                "evt_shape_method": row.get("evt_shape_method"),
                "evt_scale_refit_status": row.get("evt_scale_refit_status"),
                "evt_es_finite": row.get("evt_es_finite"),
                "evt_unibm_n_obs": row.get("evt_unibm_n_obs"),
                "evt_unibm_min_block_size": row.get("evt_unibm_min_block_size"),
                "evt_unibm_max_block_size": row.get("evt_unibm_max_block_size"),
                "evt_unibm_sliding_blocks": row.get("evt_unibm_sliding_blocks"),
                "evt_unibm_bootstrap_reps": row.get("evt_unibm_bootstrap_reps"),
                "evt_unibm_plateau_point_count": row.get("evt_unibm_plateau_point_count"),
                "evt_unibm_block_sizes_json": row.get("evt_unibm_block_sizes_json"),
                "evt_unibm_block_counts_json": row.get("evt_unibm_block_counts_json"),
                "evt_unibm_plateau_block_sizes_json": row.get("evt_unibm_plateau_block_sizes_json"),
                "evt_unibm_plateau_block_counts_json": row.get(
                    "evt_unibm_plateau_block_counts_json"
                ),
                "evt_cap_sensitivity_json": row.get("evt_cap_sensitivity_json"),
            }
        )
    return records


def _extremal_index_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if row.get("evt_variant") in (None, "empirical_standardized_tail"):
            continue
        diagnostics = _json_dict(row.get("evt_ei_diagnostics_json"))
        records.append(
            {
                **_evt_base_record(row),
                "evt_ei_status": row.get("evt_ei_status"),
                "evt_theta_hat": row.get("evt_theta_hat"),
                "evt_effective_exceedance_count": row.get("evt_effective_exceedance_count"),
                "evt_exceedance_count": row.get("evt_exceedance_count"),
                "ei_primary_estimator": diagnostics.get("primary_estimator"),
                "k_gaps_theta_hat": diagnostics.get("k_gaps_theta_hat"),
                "ei_diagnostics_json": row.get("evt_ei_diagnostics_json"),
            }
        )
    return records


def _evt_cap_sensitivity_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if row.get("evt_variant") in (None, "empirical_standardized_tail"):
            continue
        sensitivity = _json_list(row.get("evt_cap_sensitivity_json"))
        for item in sensitivity:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    **_evt_base_record(row),
                    "cap": json.dumps(item.get("cap"), separators=(",", ":")),
                    "shape": item.get("shape"),
                    "cap_hit": item.get("cap_hit"),
                    "es_available": item.get("es_available"),
                }
            )
    return records


def _evt_threshold_sensitivity_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if row.get("evt_variant") in (None, "empirical_standardized_tail"):
            continue
        sensitivity = _json_list(row.get("evt_threshold_sensitivity_json"))
        for item in sensitivity:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    **_evt_base_record(row),
                    "sensitivity_threshold_quantile": item.get("threshold_quantile"),
                    "sensitivity_status": item.get("status"),
                    "threshold_value": item.get("threshold_value"),
                    "evt_exceedance_count": item.get("evt_exceedance_count"),
                    "evt_shape": item.get("evt_shape"),
                    "evt_shape_bin": item.get("evt_shape_bin"),
                    "evt_scale": item.get("evt_scale"),
                    "evt_shape_mle": item.get("evt_shape_mle"),
                    "evt_scale_mle": item.get("evt_scale_mle"),
                    "evt_shape_method": item.get("evt_shape_method"),
                    "evt_cap_policy": item.get("evt_cap_policy"),
                    "evt_cap_hit": item.get("evt_cap_hit"),
                    "evt_xi_evi_anchor": item.get("evt_xi_evi_anchor"),
                    "evt_theta_hat": item.get("evt_theta_hat"),
                    "evt_effective_exceedance_count": item.get("evt_effective_exceedance_count"),
                    "evt_unibm_n_obs": item.get("evt_unibm_n_obs"),
                    "evt_unibm_min_block_size": item.get("evt_unibm_min_block_size"),
                    "evt_unibm_max_block_size": item.get("evt_unibm_max_block_size"),
                    "evt_unibm_sliding_blocks": item.get("evt_unibm_sliding_blocks"),
                    "evt_unibm_plateau_point_count": item.get("evt_unibm_plateau_point_count"),
                    "standardized_var": item.get("standardized_var"),
                    "standardized_es": item.get("standardized_es"),
                    "evt_es_finite": item.get("evt_es_finite"),
                }
            )
    return records


def _evt_body_tail_diagnostic_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if not row.get("body_filter_method") and row.get("evt_variant") in (
            None,
            "empirical_standardized_tail",
        ):
            continue
        records.append(
            {
                **_evt_base_record(row),
                "body_filter_method": row.get("body_filter_method"),
                "scale_method": row.get("scale_method"),
                "tail_estimator_method": row.get("tail_estimator_method"),
                "threshold_model_level": row.get("threshold_model_level"),
                "oof_standardized_loss_count": row.get("oof_standardized_loss_count"),
                "evt_exceedance_count": row.get("evt_exceedance_count"),
                "evt_shape": row.get("evt_shape"),
                "evt_shape_bin": row.get("evt_shape_bin"),
                "evt_scale": row.get("evt_scale"),
                "evt_es_finite": row.get("evt_es_finite"),
                "scale_floor": row.get("scale_floor"),
                "mad_consistency_factor": row.get("mad_consistency_factor"),
                "iqr_consistency_factor": row.get("iqr_consistency_factor"),
                "quantile_crossing_rate": row.get("quantile_crossing_rate"),
                "quantile_rearrangement_applied": row.get("quantile_rearrangement_applied"),
                "threshold_diagnostics_json": row.get("threshold_diagnostics_json"),
                "evt_evi_diagnostics_json": row.get("evt_evi_diagnostics_json"),
                "evt_ei_diagnostics_json": row.get("evt_ei_diagnostics_json"),
                "evt_unibm_n_obs": row.get("evt_unibm_n_obs"),
                "evt_unibm_min_block_size": row.get("evt_unibm_min_block_size"),
                "evt_unibm_max_block_size": row.get("evt_unibm_max_block_size"),
                "evt_unibm_sliding_blocks": row.get("evt_unibm_sliding_blocks"),
                "evt_unibm_bootstrap_reps": row.get("evt_unibm_bootstrap_reps"),
                "evt_unibm_plateau_point_count": row.get("evt_unibm_plateau_point_count"),
                "evt_unibm_block_sizes_json": row.get("evt_unibm_block_sizes_json"),
                "evt_unibm_block_counts_json": row.get("evt_unibm_block_counts_json"),
                "evt_unibm_plateau_block_sizes_json": row.get("evt_unibm_plateau_block_sizes_json"),
                "evt_unibm_plateau_block_counts_json": row.get(
                    "evt_unibm_plateau_block_counts_json"
                ),
                "diagnostic_scope": "evt_body_tail_diagnostic",
            }
        )
    return records


def _evt_route_gate_status_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if not row.get("body_filter_method") and not row.get("evt_route_gate_status"):
            continue
        records.append(
            {
                **_evt_base_record(row),
                "body_filter_method": row.get("body_filter_method"),
                "scale_method": row.get("scale_method"),
                "tail_estimator_method": row.get("tail_estimator_method"),
                "evt_route_gate_status": row.get("evt_route_gate_status"),
                "gpd_fit_status": row.get("gpd_fit_status"),
                "gpd_es_status": row.get("gpd_es_status"),
                "scale_floor": row.get("scale_floor"),
                "quantile_crossing_rate": row.get("quantile_crossing_rate"),
                "quantile_rearrangement_applied": row.get("quantile_rearrangement_applied"),
                "fit_status": row.get("fit_status"),
                "failure_reason": row.get("failure_reason"),
            }
        )
    return records


def _evt_route_availability_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        if not row.get("body_filter_method") and not row.get("evt_route_gate_status"):
            continue
        key = (
            row.get("target_family"),
            row.get("tail_side"),
            row.get("tail_level"),
            row.get("model_name"),
            row.get("information_set"),
            row.get("refit_frequency"),
        )
        bucket = grouped.setdefault(
            key,
            {
                "target_family": row.get("target_family"),
                "tail_side": row.get("tail_side"),
                "tail_level": row.get("tail_level"),
                "model_name": row.get("model_name"),
                "information_set": row.get("information_set"),
                "refit_frequency": row.get("refit_frequency"),
                "total_refits": 0,
                "available_refits": 0,
                "status_counts": {},
            },
        )
        bucket["total_refits"] = int(bucket["total_refits"]) + 1
        status = str(row.get("evt_route_gate_status") or row.get("fit_status") or "unknown")
        if status == "ok" and row.get("fit_status") != "unavailable_optimizer_failed":
            bucket["available_refits"] = int(bucket["available_refits"]) + 1
        counts = cast(dict[str, int], bucket["status_counts"])
        counts[status] = counts.get(status, 0) + 1
    records: list[dict[str, object]] = []
    for bucket in grouped.values():
        total = int(bucket["total_refits"])
        available = int(bucket["available_refits"])
        status_counts = cast(dict[str, int], bucket.pop("status_counts"))
        records.append(
            {
                **bucket,
                "unavailable_refits": total - available,
                "availability_rate": available / total if total else None,
                "status_counts_json": json.dumps(status_counts, sort_keys=True),
                "artifact_scope": "evt_route_availability",
            }
        )
    return sorted(
        records,
        key=lambda row: (
            str(row.get("model_name")),
            str(row.get("information_set")),
            str(row.get("tail_side")),
            str(row.get("tail_level")),
        ),
    )


def _evt_diagnostic_variant_metric_records(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {**row, "artifact_scope": "evt_diagnostic_variant_metric"}
        for row in rows
        if str(row.get("model_name") or "") in ML_TAIL_POT_GPD_MODEL_NAMES
        or str(row.get("model_name") or "") == "lightgbm_location_scale_empirical"
        or str(row.get("model_name") or "") in ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES
    ]


def _evt_base_record(row: dict[str, object]) -> dict[str, object]:
    return {
        "forecast_date": row.get("forecast_date"),
        "target_family": row.get("target_family"),
        "tail_side": row.get("tail_side"),
        "tail_level": row.get("tail_level"),
        "model_name": row.get("model_name"),
        "information_set": row.get("information_set"),
        "refit_frequency": row.get("refit_frequency"),
        "refit_month": row.get("refit_month"),
        "train_n": row.get("train_n"),
        "oof_standardized_loss_count": row.get("oof_standardized_loss_count"),
        "evt_variant": row.get("evt_variant"),
        "body_filter_method": row.get("body_filter_method"),
        "scale_method": row.get("scale_method"),
        "tail_estimator_method": row.get("tail_estimator_method"),
        "evt_route_gate_status": row.get("evt_route_gate_status"),
        "gpd_fit_status": row.get("gpd_fit_status"),
        "gpd_es_status": row.get("gpd_es_status"),
    }


def _json_dict(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_list(value: object) -> list[object]:
    if not isinstance(value, str) or not value:
        return []
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []
