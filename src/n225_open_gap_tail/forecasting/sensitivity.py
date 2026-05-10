# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from n225_open_gap_tail.config.runtime import (
    cast,
    delayed,
    EvaluationResult,
    EWMA_MAIN_LAMBDA,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MODEL_NAMES,
    ML_TAIL_POT_GPD_MODEL_NAMES,
    ML_TAIL_REFIT_FREQUENCY,
    ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES,
    Parallel,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
    pl,
    stable_hash,
    TAIL_LEVELS,
    TAIL_SIDE_BOTH,
    tail_side_values,
    _bounded_workers,
    _evaluation_log,
    _optional_float,
    _set_nested_thread_limits,
)
from n225_open_gap_tail.forecasting._guards import _assert_leakage_gate
from n225_open_gap_tail.forecasting.artifacts import (
    _forecast_shard_id,
    _gold_artifact_path,
    _read_manifest,
    _write_json,
    _write_parquet,
)
from n225_open_gap_tail.metrics.stat_utils import (
    christoffersen_independence_test,
    fz_loss,
    kupiec_pof_test,
    quantile_loss,
)
from n225_open_gap_tail.models.benchmark import _evaluate_benchmark_shard
from n225_open_gap_tail.models.ml_tail import _evaluate_ml_tail_shard
from n225_open_gap_tail.panel.build import (
    ml_tail_feature_columns_for_information_set,
    registered_ml_tail_information_sets,
)
from n225_open_gap_tail.reporting.tables import export_sensitivity_tables

LGBM_CONFIGURATION_SENSITIVITY_MODELS = (
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    "lightgbm_standardized_loss_pot_gpd_plain_mle",
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
)
LGBM_TARGETED_MEDIAN_MAD_MODEL = ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL
LGBM_CONFIGURATION_SPECS: dict[str, dict[str, object]] = {
    "current": {
        "n_estimators": 80,
        "learning_rate": 0.05,
        "num_leaves": 15,
        "min_child_samples": 20,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
    },
    "shallow": {
        "n_estimators": 50,
        "learning_rate": 0.05,
        "num_leaves": 10,
        "min_child_samples": 30,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
    },
    "deeper": {
        "n_estimators": 160,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 10,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
    },
}
EWMA_CONFIGURATION_SPECS: dict[str, float] = {
    "primary": EWMA_MAIN_LAMBDA,
    "lambda_0_90": 0.90,
    "lambda_0_97": 0.97,
}
EVT_THRESHOLD_SPECS: dict[str, float] = {
    "u_0_900": 0.900,
    "u_0_925": 0.925,
    "u_0_950_boundary": 0.950,
}


def lgbm_sensitivity_config(label: str) -> dict[str, object]:
    if label not in LGBM_CONFIGURATION_SPECS:
        raise PipelineRunError(f"Unknown LGBM sensitivity config label: {label}")
    return dict(LGBM_CONFIGURATION_SPECS[label])


def breach_category(breach_rate: object) -> str:
    value = _optional_float(breach_rate)
    if value is None:
        return "missing"
    return "near_nominal" if abs(value - 0.05) <= 0.025 else "coverage_warning"


def classify_sensitivity_comparison(
    *,
    primary_breach_rate: object,
    sensitivity_breach_rate: object,
    q_loss_deterioration: object,
    fz_loss_deterioration: object,
    material_conclusion_change: bool = False,
) -> str:
    primary_category = breach_category(primary_breach_rate)
    sensitivity_category = breach_category(sensitivity_breach_rate)
    q_det = _optional_float(q_loss_deterioration)
    fz_det = _optional_float(fz_loss_deterioration)
    q_bad = q_det is not None and q_det > 0.05
    fz_bad = fz_det is not None and fz_det > 0.05
    breach_worsens = (
        primary_category == "near_nominal" and sensitivity_category == "coverage_warning"
    )
    if material_conclusion_change or breach_worsens or (q_bad and fz_bad):
        return "sensitive"
    if q_bad or fz_bad:
        return "mixed"
    if primary_category == sensitivity_category:
        return "robust"
    return "mixed"


def evaluate_sensitivity_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
    tail_side: str = TAIL_SIDE_BOTH,
) -> EvaluationResult:  # pragma: no cover
    sensitivity_root = run_dir / "sensitivity"
    status_path = sensitivity_root / "metrics" / "sensitivity_status.json"
    if status_path.exists() and not force:
        export_sensitivity_tables(run_dir=run_dir)
        status = cast(dict[str, object], _read_json(status_path))
        return EvaluationResult(
            run_id=run_dir.name,
            run_dir=run_dir,
            forecast_rows=int(status.get("forecast_rows") or 0),
            metric_rows=int(status.get("metric_rows") or 0),
            status=str(status.get("status") or "cached"),
        )
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
    _assert_leakage_gate(run_dir)
    _set_nested_thread_limits()
    manifest = _read_manifest(run_dir)
    coverage_rows = pl.read_parquet(coverage_path).to_dicts()
    active_tail_sides = tail_side_values(tail_side)
    tail_levels = tuple(float(level) for level in TAIL_LEVELS)
    if len(tail_levels) != 1 or not tail_levels:
        raise PipelineRunError("Configuration sensitivity expects the registered 0.95 tail level")
    tail_level = tail_levels[0]
    information_sets = registered_ml_tail_information_sets()
    lgbm_jobs = _build_lgbm_capacity_jobs(
        panel_path=panel_path,
        coverage_path=coverage_path,
        coverage_rows=coverage_rows,
        information_sets=information_sets,
        tail_sides=active_tail_sides,
        tail_level=tail_level,
    )
    ewma_jobs = _build_ewma_jobs(
        panel_path=panel_path,
        tail_sides=active_tail_sides,
        tail_level=tail_level,
    )
    evt_jobs, evt_boundary_rows = _build_evt_threshold_jobs(
        panel_path=panel_path,
        coverage_path=coverage_path,
        coverage_rows=coverage_rows,
        information_sets=information_sets,
        tail_sides=active_tail_sides,
        tail_level=tail_level,
    )
    n_jobs = _bounded_workers(workers)
    _evaluation_log(
        "configuration sensitivity queued="
        f"lgbm={len(lgbm_jobs)} ewma={len(ewma_jobs)} evt={len(evt_jobs)} n_jobs={n_jobs}"
    )
    lgbm_result = _run_jobs(lgbm_jobs, _evaluate_ml_tail_shard, n_jobs=n_jobs)
    ewma_result = _run_jobs(ewma_jobs, _evaluate_benchmark_shard, n_jobs=n_jobs)
    evt_result = _run_jobs(evt_jobs, _sensitivity_worker, n_jobs=n_jobs)
    lgbm_forecasts = _tag_rows(
        lgbm_result["forecasts"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    ewma_forecasts = _tag_rows(
        ewma_result["forecasts"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    evt_forecasts = _tag_rows(
        evt_result["forecasts"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    lgbm_diagnostics = _tag_rows(
        lgbm_result["diagnostics"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    ewma_diagnostics = _tag_rows(
        ewma_result["diagnostics"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    evt_diagnostics = _tag_rows(
        evt_result["diagnostics"], source_run_id=run_dir.name, primary_claim_allowed=False
    )
    lgbm_metrics = _metric_rows_from_forecasts(
        lgbm_forecasts,
        primary_metrics=_read_primary_ml_metrics(run_dir),
        source_run_id=run_dir.name,
    )
    ewma_metrics = _metric_rows_from_forecasts(
        ewma_forecasts,
        primary_metrics=_read_primary_benchmark_metrics(run_dir),
        source_run_id=run_dir.name,
    )
    evt_metrics = _metric_rows_from_forecasts(
        evt_forecasts,
        primary_metrics=_read_primary_evt_metrics(run_dir),
        source_run_id=run_dir.name,
    )
    evt_metrics.extend(
        _tag_rows(
            evt_boundary_rows, source_primary_run_id=run_dir.name, primary_claim_allowed=False
        )
    )
    forecast_root = sensitivity_root / "forecasts"
    metrics_root = sensitivity_root / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    _write_parquet(
        forecast_root / "lgbm_configuration_sensitivity_forecasts.parquet", lgbm_forecasts
    )
    _write_parquet(
        forecast_root / "benchmark_configuration_sensitivity_forecasts.parquet", ewma_forecasts
    )
    _write_parquet(forecast_root / "evt_threshold_sensitivity_forecasts.parquet", evt_forecasts)
    _write_parquet(
        forecast_root / "lgbm_configuration_sensitivity_diagnostics.parquet", lgbm_diagnostics
    )
    _write_parquet(
        forecast_root / "benchmark_configuration_sensitivity_diagnostics.parquet", ewma_diagnostics
    )
    _write_parquet(forecast_root / "evt_threshold_sensitivity_diagnostics.parquet", evt_diagnostics)
    _write_parquet(metrics_root / "lgbm_configuration_sensitivity_metrics.parquet", lgbm_metrics)
    _write_parquet(
        metrics_root / "benchmark_configuration_sensitivity_metrics.parquet", ewma_metrics
    )
    _write_parquet(metrics_root / "evt_threshold_sensitivity_metrics.parquet", evt_metrics)
    forecast_rows = len(lgbm_forecasts) + len(ewma_forecasts) + len(evt_forecasts)
    metric_rows = len(lgbm_metrics) + len(ewma_metrics) + len(evt_metrics)
    _write_json(
        status_path,
        {
            "status": "ok",
            "source_primary_run_id": run_dir.name,
            "primary_claim_allowed": False,
            "forecast_rows": forecast_rows,
            "metric_rows": metric_rows,
            "created_utc": datetime.now(UTC).isoformat(),
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "lgbm_config_labels": sorted(LGBM_CONFIGURATION_SPECS),
            "ewma_config_labels": sorted(EWMA_CONFIGURATION_SPECS),
            "evt_threshold_labels": sorted(EVT_THRESHOLD_SPECS),
        },
    )
    export_sensitivity_tables(run_dir=run_dir)
    return EvaluationResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=forecast_rows,
        metric_rows=metric_rows,
        status="ok",
    )


def _build_lgbm_capacity_jobs(
    *,
    panel_path: Path,
    coverage_path: Path,
    coverage_rows: list[dict[str, object]],
    information_sets: tuple[str, ...],
    tail_sides: tuple[str, ...],
    tail_level: float,
) -> list[dict[str, object]]:  # pragma: no cover
    jobs: list[dict[str, object]] = []
    targeted_infos = tuple(
        dict.fromkeys(
            (
                PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
                PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,
                PIPELINE_CONFIG.feature_sets.ml_tail_model_d_information_set,
            )
        )
    )
    specs: list[tuple[str, str, tuple[str, ...]]] = []
    for model_name in LGBM_CONFIGURATION_SENSITIVITY_MODELS:
        for config_label in ("current", "shallow", "deeper"):
            specs.append((model_name, config_label, information_sets))
    for config_label in ("current", "deeper"):
        specs.append((LGBM_TARGETED_MEDIAN_MAD_MODEL, config_label, targeted_infos))
    for model_name, config_label, active_infos in specs:
        for tail_side in tail_sides:
            for information_set in active_infos:
                candidate_features = ml_tail_feature_columns_for_information_set(
                    coverage_rows,
                    information_set=information_set,
                )
                jobs.append(
                    {
                        "panel_path": str(panel_path),
                        "coverage_path": str(coverage_path),
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
                        "information_set": information_set,
                        "model_name": model_name,
                        "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
                            target_family=PIPELINE_CONFIG.target_policy.primary_target_family,
                            tail_side=tail_side,
                            information_set=f"{information_set}__{config_label}",
                            refit_frequency=ML_TAIL_REFIT_FREQUENCY,
                        ),
                        "candidate_feature_hash": stable_hash(candidate_features),
                        "lgbm_params": lgbm_sensitivity_config(config_label),
                        "sensitivity_family": "lgbm_capacity",
                        "config_label": config_label,
                        "primary_claim_allowed": False,
                    }
                )
    return jobs


def _build_ewma_jobs(
    *,
    panel_path: Path,
    tail_sides: tuple[str, ...],
    tail_level: float,
) -> list[dict[str, object]]:  # pragma: no cover
    jobs: list[dict[str, object]] = []
    for config_label, lambda_value in EWMA_CONFIGURATION_SPECS.items():
        for tail_side in tail_sides:
            jobs.append(
                {
                    "panel_path": str(panel_path),
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "models": ("ewma_vol_scaled",),
                    "ewma_lambda": lambda_value,
                    "sensitivity_family": "ewma_lambda",
                    "config_label": config_label,
                    "primary_claim_allowed": False,
                }
            )
    return jobs


def _build_evt_threshold_jobs(
    *,
    panel_path: Path,
    coverage_path: Path,
    coverage_rows: list[dict[str, object]],
    information_sets: tuple[str, ...],
    tail_sides: tuple[str, ...],
    tail_level: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:  # pragma: no cover
    jobs: list[dict[str, object]] = []
    boundary_rows: list[dict[str, object]] = []
    pot_models = (*ML_TAIL_POT_GPD_MODEL_NAMES, *ML_TAIL_ROBUST_POT_GPD_MODEL_NAMES)
    for config_label, threshold in EVT_THRESHOLD_SPECS.items():
        if tail_level <= threshold:
            boundary_rows.extend(
                _evt_boundary_metric_rows(
                    config_label=config_label,
                    threshold=threshold,
                    tail_sides=tail_sides,
                    tail_level=tail_level,
                    information_sets=information_sets,
                    models=pot_models,
                )
            )
            boundary_rows.extend(
                _evt_boundary_metric_rows(
                    config_label=config_label,
                    threshold=threshold,
                    tail_sides=tail_sides,
                    tail_level=tail_level,
                    information_sets=("target_history_only",),
                    models=("gjr_garch_evt",),
                )
            )
            continue
        for tail_side in tail_sides:
            jobs.append(
                {
                    "panel_path": str(panel_path),
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "models": ("gjr_garch_evt",),
                    "evt_threshold_quantile": threshold,
                    "sensitivity_family": "evt_threshold",
                    "config_label": config_label,
                    "primary_claim_allowed": False,
                }
            )
            for model_name in pot_models:
                for information_set in information_sets:
                    candidate_features = ml_tail_feature_columns_for_information_set(
                        coverage_rows,
                        information_set=information_set,
                    )
                    jobs.append(
                        {
                            "panel_path": str(panel_path),
                            "coverage_path": str(coverage_path),
                            "tail_side": tail_side,
                            "tail_level": tail_level,
                            "target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
                            "information_set": information_set,
                            "model_name": model_name,
                            "refit_frequency": ML_TAIL_REFIT_FREQUENCY,
                            "candidate_feature_hash": stable_hash(candidate_features),
                            "evt_threshold_quantile": threshold,
                            "sensitivity_family": "evt_threshold",
                            "config_label": config_label,
                            "primary_claim_allowed": False,
                        }
                    )
    return jobs, boundary_rows


def _evt_boundary_metric_rows(
    *,
    config_label: str,
    threshold: float,
    tail_sides: tuple[str, ...],
    tail_level: float,
    information_sets: tuple[str, ...],
    models: tuple[str, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tail_side in tail_sides:
        for model_name in models:
            for information_set in information_sets:
                rows.append(
                    {
                        "source_primary_run_id": None,
                        "primary_claim_allowed": False,
                        "sensitivity_family": "evt_threshold",
                        "config_label": config_label,
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "evt_threshold_quantile": threshold,
                        "sensitivity_status": "not_applicable_threshold_not_below_tail_level",
                        "rows": 0,
                        "var_breach_rate": None,
                        "expected_breach_rate": 1.0 - tail_level,
                        "exceedance_count": 0,
                        "mean_quantile_loss": None,
                        "mean_fz_loss": None,
                        "mean_exceedance_severity": None,
                        "breach_category": "missing",
                        "robustness_classification": "boundary_diagnostic",
                    }
                )
    return rows


def _sensitivity_worker(
    payload: dict[str, object],
) -> dict[str, list[dict[str, object]]]:  # pragma: no cover
    # The worker is exercised by the real sensitivity workflow, not unit tests.
    if "models" in payload:
        return _evaluate_benchmark_shard(payload)
    return _evaluate_ml_tail_shard(payload)


def _run_jobs(
    jobs: list[dict[str, object]],
    worker: object,
    *,
    n_jobs: int,
) -> dict[str, list[dict[str, object]]]:  # pragma: no cover
    if not jobs:
        return {"forecasts": [], "diagnostics": [], "failures": []}
    if n_jobs == 1:
        outputs = [worker(job) for job in jobs]  # type: ignore[misc]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend=PIPELINE_CONFIG.model_policy.joblib_backend)(
            delayed(worker)(job)
            for job in jobs  # type: ignore[misc]
        )
    result = {"forecasts": [], "diagnostics": [], "failures": []}
    for payload, output in zip(jobs, outputs, strict=True):
        for key in tuple(result):
            result[key].extend(
                _tag_rows(
                    output.get(key, []),
                    sensitivity_family=str(payload.get("sensitivity_family") or ""),
                    config_label=str(payload.get("config_label") or ""),
                    primary_claim_allowed=False,
                    evt_threshold_quantile=payload.get("evt_threshold_quantile"),
                    lgbm_config_json=stable_hash(payload.get("lgbm_params") or {}),
                )
            )
    return result


def _tag_rows(rows: list[dict[str, object]], **metadata: object) -> list[dict[str, object]]:
    return [
        {**row, **{key: value for key, value in metadata.items() if value is not None}}
        for row in rows
    ]


def _metric_rows_from_forecasts(
    forecasts: list[dict[str, object]],
    *,
    primary_metrics: dict[tuple[str, str, str, float], dict[str, object]],
    source_run_id: str,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, float, str, str], list[dict[str, object]]] = defaultdict(
        list
    )
    for row in forecasts:
        if row.get("fit_status") != "ok" or row.get("is_valid_forecast") is not True:
            continue
        tail_level = _optional_float(row.get("tail_level"))
        if tail_level is None:
            continue
        key = (
            str(row.get("model_name") or ""),
            str(row.get("information_set") or "target_history_only"),
            str(row.get("tail_side") or ""),
            float(tail_level),
            str(row.get("sensitivity_family") or ""),
            str(row.get("config_label") or ""),
        )
        grouped[key].append(row)
    metrics: list[dict[str, object]] = []
    for (
        model_name,
        information_set,
        tail_side,
        tail_level,
        sensitivity_family,
        config_label,
    ), rows in sorted(grouped.items()):
        losses: list[float] = []
        vars_: list[float] = []
        esses: list[float] = []
        breaches: list[bool] = []
        q_losses: list[float] = []
        fz_losses: list[float] = []
        severities: list[float] = []
        for row in rows:
            loss = _optional_float(row.get("realized_loss"))
            var = _optional_float(row.get("var_forecast"))
            es = _optional_float(row.get("es_forecast"))
            if loss is None or var is None or es is None:
                continue
            loss = float(loss)
            var = float(var)
            es = float(es)
            breach = loss > var
            losses.append(loss)
            vars_.append(var)
            esses.append(es)
            breaches.append(breach)
            q_losses.append(quantile_loss(loss, var, tail_level))
            loss_fz = fz_loss(loss, var, es, tail_level)
            if loss_fz == loss_fz:
                fz_losses.append(loss_fz)
            if breach:
                severities.append(loss - var)
        n = len(losses)
        if n == 0:
            continue
        breach_rate = sum(breaches) / n
        primary = primary_metrics.get((model_name, information_set, tail_side, tail_level), {})
        mean_q = sum(q_losses) / len(q_losses) if q_losses else None
        mean_fz = sum(fz_losses) / len(fz_losses) if fz_losses else None
        primary_q = _optional_float(primary.get("mean_quantile_loss"))
        primary_fz = _optional_float(primary.get("mean_fz_loss"))
        primary_breach = _optional_float(primary.get("var_breach_rate"))
        q_det = _deterioration_ratio(mean_q, primary_q)
        fz_det = _deterioration_ratio(mean_fz, primary_fz)
        metrics.append(
            {
                "source_primary_run_id": source_run_id,
                "primary_claim_allowed": False,
                "sensitivity_family": sensitivity_family,
                "config_label": config_label,
                "model_name": model_name,
                "information_set": information_set,
                "tail_side": tail_side,
                "tail_level": tail_level,
                "evt_threshold_quantile": rows[0].get("evt_threshold_quantile"),
                "sensitivity_status": "ok",
                "rows": n,
                "var_breach_rate": breach_rate,
                "expected_breach_rate": 1.0 - tail_level,
                "exceedance_count": int(sum(breaches)),
                "kupiec_pvalue": kupiec_pof_test(
                    breaches=pl.Series(breaches).to_numpy(),
                    expected_probability=1.0 - tail_level,
                ).get("pvalue"),
                "christoffersen_pvalue": christoffersen_independence_test(
                    breaches=pl.Series(breaches).to_numpy(),
                ).get("pvalue"),
                "mean_quantile_loss": mean_q,
                "mean_fz_loss": mean_fz,
                "mean_exceedance_severity": sum(severities) / len(severities)
                if severities
                else None,
                "primary_rows": primary.get("rows"),
                "primary_var_breach_rate": primary_breach,
                "primary_mean_quantile_loss": primary_q,
                "primary_mean_fz_loss": primary_fz,
                "q_loss_deterioration_ratio": q_det,
                "fz_loss_deterioration_ratio": fz_det,
                "primary_breach_category": breach_category(primary_breach),
                "breach_category": breach_category(breach_rate),
                "robustness_classification": classify_sensitivity_comparison(
                    primary_breach_rate=primary_breach,
                    sensitivity_breach_rate=breach_rate,
                    q_loss_deterioration=q_det,
                    fz_loss_deterioration=fz_det,
                ),
            }
        )
    return metrics


def _deterioration_ratio(value: object, primary: object) -> float | None:
    observed = _optional_float(value)
    baseline = _optional_float(primary)
    if observed is None or baseline is None:
        return None
    denominator = max(abs(baseline), 1e-12)
    return float((observed - baseline) / denominator)


def _read_primary_ml_metrics(
    run_dir: Path,
) -> dict[tuple[str, str, str, float], dict[str, object]]:  # pragma: no cover
    return _metric_lookup(run_dir / "metrics" / "ml_tail_metrics_per_model.parquet")


def _read_primary_benchmark_metrics(
    run_dir: Path,
) -> dict[tuple[str, str, str, float], dict[str, object]]:  # pragma: no cover
    return _metric_lookup(run_dir / "metrics" / "benchmark_metrics_per_model.parquet")


def _read_primary_evt_metrics(
    run_dir: Path,
) -> dict[tuple[str, str, str, float], dict[str, object]]:  # pragma: no cover
    lookup = _read_primary_ml_metrics(run_dir)
    lookup.update(_read_primary_benchmark_metrics(run_dir))
    return lookup


def _metric_lookup(
    path: Path,
) -> dict[tuple[str, str, str, float], dict[str, object]]:  # pragma: no cover
    if not path.exists():
        return {}
    frame = pl.read_parquet(path)
    output: dict[tuple[str, str, str, float], dict[str, object]] = {}
    required = {"model_name", "information_set", "tail_side", "tail_level"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return output
    for row in frame.iter_rows(named=True):
        tail_level = _optional_float(row.get("tail_level"))
        if tail_level is None:
            continue
        output[
            (
                str(row.get("model_name") or ""),
                str(row.get("information_set") or "target_history_only"),
                str(row.get("tail_side") or ""),
                float(tail_level),
            )
        ] = row
    return output


def _read_json(path: Path) -> dict[str, object]:  # pragma: no cover
    import json

    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
