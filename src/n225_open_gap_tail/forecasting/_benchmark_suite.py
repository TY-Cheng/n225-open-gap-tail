# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_ADVANCED_REFIT_FREQUENCY,
    BENCHMARK_ANCHOR_MODEL,
    BENCHMARK_BASELINE_MODEL_NAMES,
    cast,
    CLAIMS_LEVEL,
    delayed,
    EvaluationResult as EvaluationResult,
    Parallel,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
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
    _update_manifest,
    _write_forecast_shards,
    _write_json,
    _write_parquet,
)
from n225_open_gap_tail.inference.core import build_common_sample_artifacts
from n225_open_gap_tail.metrics.information import (
    _assert_run_config_compatible,
    _gold_artifact_path,
)
from n225_open_gap_tail.models.benchmark import _evaluate_benchmark_shard
from n225_open_gap_tail.models.benchmark_advanced import _evaluate_benchmark_advanced_shard


def evaluate_benchmark_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
    include_advanced: bool = True,
    tail_side: str = TAIL_SIDE_BOTH,
) -> EvaluationResult:
    panel_path = _gold_artifact_path(
        run_dir, "modeling_panel", run_dir / "panel" / "modeling_panel.parquet"
    )
    if not panel_path.exists():
        raise PipelineRunError(f"Missing modeling panel: {panel_path}")
    _assert_run_config_compatible(run_dir, force=force)
    _assert_leakage_gate(run_dir)
    _set_nested_thread_limits()
    _evaluation_log(f"start run_id={run_dir.name} workers={workers}")
    forecast_root = run_dir / "forecasts"
    metrics_root = run_dir / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    baseline_jobs: list[dict[str, object]] = []
    active_tail_sides = tail_side_values(tail_side)
    for active_tail_side in active_tail_sides:
        for tail_level in TAIL_LEVELS:
            for model_name in BENCHMARK_BASELINE_MODEL_NAMES:
                baseline_jobs.append(
                    {
                        "panel_path": str(panel_path),
                        "run_dir": str(run_dir),
                        "tail_side": active_tail_side,
                        "tail_level": tail_level,
                        "models": (model_name,),
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
                            tail_side=active_tail_side,
                        ),
                        "shard_kind": "baseline",
                    }
                )
    advanced_jobs: list[dict[str, object]] = []
    if include_advanced:
        for active_tail_side in active_tail_sides:
            for tail_level in TAIL_LEVELS:
                for model_name in BENCHMARK_ADVANCED_MODEL_NAMES:
                    advanced_jobs.append(
                        {
                            "panel_path": str(panel_path),
                            "run_dir": str(run_dir),
                            "tail_side": active_tail_side,
                            "tail_level": tail_level,
                            "models": (model_name,),
                            "shard_id": _forecast_shard_id(
                                model_name,
                                tail_level,
                                tail_side=active_tail_side,
                                refit_frequency=BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                            ),
                            "shard_kind": "advanced",
                        }
                    )
    jobs = [*baseline_jobs, *advanced_jobs]
    for payload in jobs:
        validate_worker_payload(payload)
    n_jobs = _bounded_workers(workers)
    _evaluation_log(
        f"Benchmark shards queued={len(jobs)} baseline={len(baseline_jobs)} "
        f"advanced={len(advanced_jobs)} n_jobs={n_jobs}"
    )
    if n_jobs == 1:
        outputs = [_dispatch_benchmark_shard(payload) for payload in jobs]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend=PIPELINE_CONFIG.model_policy.joblib_backend)(
            delayed(_dispatch_benchmark_shard)(payload) for payload in jobs
        )
    baseline_outputs = [output for output in outputs if output.get("shard_kind") == "baseline"]
    advanced_outputs = [output for output in outputs if output.get("shard_kind") == "advanced"]
    forecasts = [row for output in outputs for row in output["forecasts"]]
    diagnostics = [row for output in outputs for row in output["diagnostics"]]
    failures = [row for output in outputs for row in output["failures"]]
    baseline_forecasts = [row for output in baseline_outputs for row in output["forecasts"]]
    baseline_failures = [row for output in baseline_outputs for row in output["failures"]]
    advanced_forecasts = [row for output in advanced_outputs for row in output["forecasts"]]
    advanced_diagnostics = [row for output in advanced_outputs for row in output["diagnostics"]]
    advanced_failures = [row for output in advanced_outputs for row in output["failures"]]
    forecast_path = forecast_root / "benchmark_forecasts.parquet"
    diagnostics_path = forecast_root / "benchmark_fit_diagnostics.parquet"
    failures_path = forecast_root / "benchmark_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _evaluation_log(f"wrote forecasts: {forecast_path} rows={len(forecasts)}")
    _write_parquet(diagnostics_path, diagnostics)
    _evaluation_log(f"wrote diagnostics: {diagnostics_path} rows={len(diagnostics)}")
    _write_parquet(failures_path, failures)
    _evaluation_log(f"wrote failures: {failures_path} rows={len(failures)}")
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    _evaluation_log("wrote forecast shards")
    artifacts = build_common_sample_artifacts(
        forecasts,
        suite="benchmark",
        anchor_model=BENCHMARK_ANCHOR_MODEL,
        anchor_information_set="target_history_only",
    )
    baseline_artifacts = build_common_sample_artifacts(
        baseline_forecasts,
        suite="benchmark_baseline",
        anchor_model=BENCHMARK_ANCHOR_MODEL,
        anchor_information_set="target_history_only",
    )
    metrics = cast(list[dict[str, object]], artifacts["primary_metrics"])
    _write_parquet(metrics_root / "benchmark_metrics.parquet", metrics)
    _write_parquet(
        metrics_root / "benchmark_baseline_metrics.parquet",
        cast(list[dict[str, object]], baseline_artifacts["primary_metrics"]),
    )
    _write_parquet(
        metrics_root / "benchmark_metrics_per_model.parquet",
        cast(list[dict[str, object]], artifacts["per_model_metrics"]),
    )
    _write_parquet(
        metrics_root / "benchmark_model_eviction.parquet",
        cast(list[dict[str, object]], artifacts["model_eviction"]),
    )
    _write_parquet(
        metrics_root / "benchmark_loss_matrix.parquet",
        cast(list[dict[str, object]], artifacts["loss_matrix"]),
    )
    _write_parquet(
        metrics_root / "benchmark_dm_inference.parquet",
        cast(list[dict[str, object]], artifacts["dm_inference"]),
    )
    _write_parquet(
        metrics_root / "benchmark_murphy.parquet",
        cast(list[dict[str, object]], artifacts["murphy"]),
    )
    _write_parquet(
        metrics_root / "benchmark_stress_windows.parquet",
        cast(list[dict[str, object]], artifacts["stress_windows"]),
    )
    _evaluation_log(f"wrote primary metrics rows={len(metrics)}")
    advanced_status = (
        "completed_nonblocking" if include_advanced else "skipped_benchmark_baseline_suite"
    )
    _write_json(
        metrics_root / "benchmark_status.json",
        {
            "claims_level": CLAIMS_LEVEL,
            "claim_level": CLAIMS_LEVEL,
            "config_hash": PIPELINE_CONFIG.config_hash(),
            "suite": "benchmark",
            "benchmark_baseline_status": "completed",
            "benchmark_advanced_status": advanced_status,
            "benchmark_baseline_model_count": len(BENCHMARK_BASELINE_MODEL_NAMES),
            "benchmark_advanced_model_count": len(BENCHMARK_ADVANCED_MODEL_NAMES)
            if include_advanced
            else 0,
            "tail_sides": list(active_tail_sides),
            "forecast_rows": len(forecasts),
            "benchmark_baseline_forecast_rows": len(baseline_forecasts),
            "benchmark_advanced_forecast_rows": len(advanced_forecasts),
            "benchmark_advanced_diagnostic_rows": len(advanced_diagnostics),
            "benchmark_advanced_unavailable_diagnostic_rows": sum(
                1 for row in advanced_diagnostics if row.get("fit_status") != "ok"
            ),
            "metric_rows": len(metrics),
            "benchmark_baseline_metric_rows": len(
                cast(list[dict[str, object]], baseline_artifacts["primary_metrics"])
            ),
            "per_model_metric_rows": len(
                cast(list[dict[str, object]], artifacts["per_model_metrics"])
            ),
            "loss_matrix_rows": len(cast(list[dict[str, object]], artifacts["loss_matrix"])),
            "common_sample_status": artifacts["common_sample_status"],
            "failures": len(failures),
            "benchmark_baseline_failures": len(baseline_failures),
            "benchmark_advanced_failures": len(advanced_failures),
        },
    )
    _update_manifest(
        run_dir,
        {
            "benchmark_eval_status": "completed",
            "benchmark_baseline_status": "completed",
            "benchmark_advanced_status": advanced_status,
            "benchmark_forecast_rows": len(forecasts),
            "benchmark_tail_sides": list(active_tail_sides),
        },
    )
    _evaluation_log(
        f"complete run_id={run_dir.name} forecast_rows={len(forecasts)} "
        f"metric_rows={len(metrics)} failures={len(failures)}"
    )
    return EvaluationResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed",
    )


def evaluate_benchmark_baseline_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
    tail_side: str = TAIL_SIDE_BOTH,
) -> EvaluationResult:
    return evaluate_benchmark_suite(
        run_dir=run_dir,
        workers=workers,
        force=force,
        include_advanced=False,
        tail_side=tail_side,
    )


def _dispatch_benchmark_shard(payload: dict[str, object]) -> dict[str, object]:
    shard_kind = str(payload.get("shard_kind") or "baseline")
    if shard_kind == "advanced":
        output = _evaluate_benchmark_advanced_shard(payload)
    else:
        output = _evaluate_benchmark_shard(payload)
        shard_kind = "baseline"
    return {
        "shard_kind": shard_kind,
        "forecasts": output["forecasts"],
        "diagnostics": output["diagnostics"],
        "failures": output["failures"],
    }
