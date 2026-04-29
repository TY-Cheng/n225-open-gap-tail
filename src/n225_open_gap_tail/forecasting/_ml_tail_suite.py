# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime
from n225_open_gap_tail.forecasting._guards import _assert_leakage_gate

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def evaluate_ml_tail_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
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
    jobs: list[dict[str, object]] = []
    for tail_level in TAIL_LEVELS:
        for model_name in ML_TAIL_MODEL_NAMES:
            for information_set in information_sets:
                jobs.append(
                    {
                        "panel_path": str(panel_path),
                        "coverage_path": str(coverage_path),
                        "run_dir": str(run_dir),
                        "tail_level": tail_level,
                        "target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
                        "information_set": information_set,
                        "model_name": model_name,
                        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
                            information_set=information_set,
                            target_family=PIPELINE_CONFIG.target_policy.primary_target_family,
                            refit_frequency=ML_TAIL_REFIT_FREQUENCY,
                        ),
                    }
                )
    for payload in jobs:
        validate_worker_payload(payload)
    n_jobs = _bounded_workers(workers)
    _evaluation_log(f"ML tail shards queued={len(jobs)} n_jobs={n_jobs}")
    if n_jobs == 1:
        outputs = [_evaluate_ml_tail_shard(payload) for payload in jobs]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend=PIPELINE_CONFIG.model_policy.joblib_backend)(
            delayed(_evaluate_ml_tail_shard)(payload) for payload in jobs
        )
    forecasts = [row for output in outputs for row in output["forecasts"]]
    diagnostics = [row for output in outputs for row in output["diagnostics"]]
    failures = [row for output in outputs for row in output["failures"]]
    forecast_path = forecast_root / "ml_tail_forecasts.parquet"
    diagnostics_path = forecast_root / "ml_tail_fit_diagnostics.parquet"
    failures_path = forecast_root / "ml_tail_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _evaluation_log(f"wrote ML tail forecasts: {forecast_path} rows={len(forecasts)}")
    _write_parquet(diagnostics_path, diagnostics)
    _evaluation_log(f"wrote ML tail diagnostics: {diagnostics_path} rows={len(diagnostics)}")
    _write_parquet(failures_path, failures)
    _evaluation_log(f"wrote ML tail failures: {failures_path} rows={len(failures)}")
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    artifacts = build_common_sample_artifacts(
        forecasts,
        suite="ml_tail",
        anchor_model=ML_TAIL_DIRECT_QUANTILE_MODEL,
        anchor_information_set=ML_TAIL_ANCHOR_INFORMATION_SET,
    )
    headline_forecasts = cast(list[dict[str, object]], artifacts["headline_forecasts"])
    metrics = cast(list[dict[str, object]], artifacts["headline_metrics"])
    incremental = build_incremental_information_records(
        headline_forecasts,
        baseline_information_set=PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
    )
    dst_attenuation = build_dst_attenuation_records(
        headline_forecasts,
        baseline_information_set=PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
        expanded_information_set=PIPELINE_CONFIG.feature_sets.ml_tail_model_b_information_set,
    )
    feature_unavailability = build_ml_tail_feature_unavailability_records(forecasts)
    feature_unavailability_dates = build_ml_tail_feature_unavailability_date_records(forecasts)
    result_matrix_artifacts = build_ml_tail_result_matrix_artifacts(forecasts)
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
        metrics_root / "ml_tail_mcs.parquet",
        cast(list[dict[str, object]], artifacts["mcs"]),
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
    _write_parquet(metrics_root / "ml_tail_dst_attenuation.parquet", dst_attenuation)
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
    _write_parquet(
        metrics_root / "ml_tail_result_matrix_mcs.parquet",
        cast(list[dict[str, object]], result_matrix_artifacts["mcs"]),
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
