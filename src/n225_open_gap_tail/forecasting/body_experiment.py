"""Shared-body refits for the accepted 28-spec experiment, separate from frozen runs."""

from __future__ import annotations

import importlib
import json
import math
import resource
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, date, datetime
from itertools import groupby
from pathlib import Path
from typing import Any, Literal

import lightgbm as lgb
import numpy as np
import polars as pl

from n225_open_gap_tail.config.git import _git_commit, _git_dirty
from n225_open_gap_tail.config.runtime import (
    DEFAULT_MIN_TRAIN_EXCEEDANCES,
    DEFAULT_MIN_TRAIN_ROWS,
    EVT_MIN_EXCEEDANCES_95,
    EVT_MIN_STANDARDIZED_LOSSES_95,
    LOCATION_SCALE_MIN_ES_EXCEEDANCES_95,
    ML_TAIL_EVT_SHAPE_UPPER_BOUND,
    PIPELINE_CONFIG,
    TAIL_SIDES,
    PipelineRunError,
    _optional_float,
    empirical_excess_es_companion,
    find_oos_start_date,
    validate_forecast_values,
)
from n225_open_gap_tail.data_lake.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.data_lake.io import compute_combined_clean_start
from n225_open_gap_tail.forecasting._guards import _assert_leakage_gate
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, index_forecast_sessions
from n225_open_gap_tail.models.benchmark import _pot_gpd_standardized_tail
from n225_open_gap_tail.models.ml_body import (
    BODY_RECIPES,
    EXPERIMENT_MODEL_NAMES,
    TAIL_METHODS,
    TRAINING_MULTIPLIER,
    body_model_name,
    fit_body_recipes,
    predict_body,
)
from n225_open_gap_tail.models.ml_tail import build_ml_tail_modeling_rows
from n225_open_gap_tail.models.ml_tail_oof import (
    _fit_lgb_regression_model,
    _predict_lgb_rows,
)
from n225_open_gap_tail.models.unibm import estimate_public_unibm
from n225_open_gap_tail.panel.build import (
    apply_combined_clean_start,
    build_effective_predictor_start,
    build_feature_coverage_records,
)
from n225_open_gap_tail.panel.build_helpers import _max_date_strings
from n225_open_gap_tail.panel.information_sets import (
    ml_tail_feature_columns_for_information_set,
    registered_ml_tail_information_sets,
)
from n225_open_gap_tail.panel.leakage import write_leakage_check


def forecast_shared_body_refit(
    train_rows: list[dict[str, Any]],
    forecast_rows: list[dict[str, Any]],
    *,
    candidate_features: list[str],
    information_set: str,
    tail_side: str,
    tail_level: float = 0.95,
    lgbm_params: Mapping[str, object] | None = None,
    progress: Callable[[str], None] | None = None,
    components: Mapping[str, dict[str, Any]] | None = None,
    calibration_kind: Literal["oof", "in_sample"] = "oof",
) -> dict[str, Any]:
    """Fit one historical prefix; three tails reuse each body's fits and calibration sample.

    Forecast rows must be in one refit month and strictly after training. Failed
    models/dates remain in the roster. ES-only failure does not erase finite VaR.
    This is not a rolling evaluation or a model-selection operation.
    """
    train_dates = [str(row["forecast_date"]) for row in train_rows]
    days = [str(row["forecast_date"]) for row in forecast_rows]
    if (
        not train_dates
        or not days
        or train_dates != sorted(set(train_dates))
        or days != sorted(set(days))
        or train_dates[-1] >= days[0]
        or len({day[:7] for day in days}) != 1
    ):
        raise ValueError("Refit requires ordered unique dates, historical training and one month")
    if not 0.9 < tail_level < 1 or tail_side not in TAIL_SIDES:
        raise ValueError("Expected a left/right tail above the registered POT threshold")
    y = np.array([float(row["realized_loss"]) for row in train_rows]) * TRAINING_MULTIPLIER
    if not np.isfinite(y).all() or any(row.get("clean_sample") is False for row in train_rows):
        raise ValueError("Training prefix must contain only eligible finite observed losses")

    forecasts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    oof: list[dict[str, Any]] = []
    context = {
        "calibration_kind": calibration_kind,
        "information_set": information_set,
        "tail_side": tail_side,
        "tail_level": tail_level,
        "refit_date": days[0],
        "train_start": train_dates[0],
        "train_end": train_dates[-1],
        "train_n": len(train_rows),
        "training_multiplier": TRAINING_MULTIPLIER,
    }

    def emit(
        model: str,
        vars_: Any,
        es_: Any,
        *,
        failure: str | None = None,
        es_failure: str | None = None,
        companion: str,
        predictions: dict[str, Any] | None = None,
    ) -> None:
        for i, source in enumerate(forecast_rows):
            q, e = float(vars_[i]), float(es_[i])
            valid, reason = validate_forecast_values(q, e)
            row = {
                **context,
                "forecast_date": source["forecast_date"],
                "target_family": source.get("target_family", "full_gap_settle_to_open"),
                "model_name": model,
                "refit_frequency": "monthly",
                "var_forecast": _optional_float(q),
                "es_forecast": _optional_float(e),
                "realized_loss": source["realized_loss"],
                "var_breach": float(source["realized_loss"]) > q if math.isfinite(q) else None,
                "is_valid_forecast": valid and failure is None,
                "invalid_reason": reason,
                "fit_status": "unavailable_fit"
                if failure
                else "ok"
                if valid
                else "invalid_forecast",
                "failure_reason": failure,
                "es_failure_reason": es_failure,
                "es_companion_type": companion,
                **{
                    key: source.get(key) for key in ("dst_regime", "absorption_regime", "vix_level")
                },
            }
            if predictions is not None:
                row.update(
                    {
                        key: _optional_float(predictions[key][i])
                        for key in ("location", "scale", "raw_scale")
                    }
                )
                row.update(
                    {
                        key: bool(predictions[key][i])
                        for key in ("scale_nonpositive", "scale_floor_hit")
                    }
                )
            for score in ("var", "joint", "fz0"):
                row[f"{score}_eligible"] = forecast_eligible(row, score=score)
            forecasts.append(row)

    unavailable = np.full(len(days), np.nan)
    started = time.perf_counter()
    direct: dict[str, Any] = {**context, "model_name": "lightgbm_direct_quantile"}
    try:
        if components is None:
            model, gate, active = _fit_lgb_regression_model(
                lgb=lgb,
                rows=train_rows,
                target=y,
                candidate_features=candidate_features,
                objective="quantile",
                alpha=tail_level,
                random_state=int(tail_level * 10000) + len(information_set),
                lgbm_params=lgbm_params,
            )
        else:
            fitted = components["direct"]
            if fitted.get("failure_reason"):
                raise PipelineRunError(fitted["failure_reason"])
            model, gate, active = fitted["model"], fitted["gate"], fitted["active_features"]
        training_q = _predict_lgb_rows(model, train_rows, active)
        q = _predict_lgb_rows(model, forecast_rows, active)
        e = np.array(
            [
                empirical_excess_es_companion(
                    train_losses=y, train_var_forecasts=training_q, forecast_var=float(value)
                )
                if np.isfinite(training_q).all() and np.isfinite(value)
                else np.nan
                for value in q
            ]
        )
        emit(
            "lightgbm_direct_quantile",
            q / TRAINING_MULTIPLIER,
            e / TRAINING_MULTIPLIER,
            companion="training_in_sample_empirical_excess",
            es_failure=None if np.isfinite(training_q).all() else "nonfinite_training_quantile",
        )
        direct.update(fit_status="ok", feature_gate=gate, parameters=model.get_params())
    except Exception as exc:
        if components is not None and not isinstance(exc, PipelineRunError):
            raise
        direct.update(fit_status="unavailable_fit", failure_reason=f"{type(exc).__name__}: {exc}")
        emit(
            "lightgbm_direct_quantile",
            unavailable,
            unavailable,
            companion="training_in_sample_empirical_excess",
            failure=direct["failure_reason"],
        )
    direct["runtime_seconds"] = time.perf_counter() - started
    diagnostics.append(direct)
    if progress:
        progress(f"direct quantile: {direct['fit_status']}")

    bodies = fit_body_recipes(
        train_rows,
        candidate_features=candidate_features,
        information_set=information_set,
        tail_level=tail_level,
        lgb=lgb,
        lgbm_params=lgbm_params,
        components=components,
        calibration_kind=calibration_kind,
    )
    for expected_recipe in BODY_RECIPES:
        if progress:
            progress(f"fitting {expected_recipe}")
        started = time.perf_counter()
        recipe, body = next(bodies)
        detail: dict[str, Any] = {
            **context,
            "recipe": recipe,
            "body_fit_seconds": time.perf_counter() - started,
        }
        try:
            if body["fit_status"] != "ok":
                raise PipelineRunError(body["failure_reason"])
            pred = predict_body(body, forecast_rows)
        except Exception as exc:
            if components is not None and not isinstance(exc, PipelineRunError):
                raise
            failure = f"{type(exc).__name__}: {exc}"
            diagnostics.append(
                {**detail, "fit_status": "unavailable_body_fit", "failure_reason": failure}
            )
            for tail in TAIL_METHODS:
                emit(
                    body_model_name(recipe, tail),
                    unavailable,
                    unavailable,
                    failure=failure,
                    companion=tail,
                )
            if progress:
                progress(f"{recipe}: unavailable body")
            continue
        detail.update(
            fit_status="ok",
            body={
                key: value
                for key, value in body.items()
                if key
                not in {
                    "center",
                    "spread",
                    "q25",
                    "q75",
                    f"mu_{calibration_kind}",
                    f"scale_{calibration_kind}",
                    f"raw_scale_{calibration_kind}",
                    "standardized_losses",
                    f"{calibration_kind}_dates",
                    f"scale_target_{calibration_kind}_training_units",
                }
            },
            components={
                role: {
                    "feature_gate": body[role]["gate"],
                    "parameters": body[role]["model"].get_params(),
                }
                for role in ("center", "spread", "q25", "q75")
                if body[role] is not None
            },
            tails={},
        )
        z = body["standardized_losses"]
        finite = z[np.isfinite(z)]
        for i, day in enumerate(body[f"{calibration_kind}_dates"]):
            oof.append(
                {
                    **context,
                    "recipe": recipe,
                    "observation_date": day,
                    "position": i,
                    "structural_warmup": i < body[f"{calibration_kind}_warmup_rows"],
                    **{
                        key: _optional_float(body[key][i])
                        for key in (
                            f"mu_{calibration_kind}",
                            f"scale_{calibration_kind}",
                            f"raw_scale_{calibration_kind}",
                            "standardized_losses",
                        )
                    },
                }
            )
        for tail in TAIL_METHODS:
            tail_start = time.perf_counter()
            metadata: dict[str, Any] = {}
            try:
                if tail == "empirical":
                    qz = float(np.quantile(finite, tail_level))
                    exceedances = finite[finite > qz]
                    enough = len(exceedances) >= min(
                        LOCATION_SCALE_MIN_ES_EXCEEDANCES_95, DEFAULT_MIN_TRAIN_EXCEEDANCES
                    )
                    metadata = {
                        "standardized_var": qz,
                        "standardized_es": float(np.mean(exceedances)) if enough else None,
                        "evt_exceedance_count": len(exceedances),
                        "evt_es_failure_reason": None
                        if enough
                        else "insufficient_empirical_es_exceedances",
                    }
                else:
                    anchor = None
                    if tail == "unibm":
                        anchor = estimate_public_unibm(
                            z, warmup_rows=body[f"{calibration_kind}_warmup_rows"]
                        )
                        detail["public_unibm"] = {
                            key: value for key, value in anchor.items() if key != "xi_evi_anchor"
                        }
                        if anchor["status"] != "ok":
                            raise ValueError(anchor["failure_reason"])
                    metadata.update(
                        _pot_gpd_standardized_tail(
                            standardized_losses=z,
                            tail_level=tail_level,
                            evt_variant=tail,
                            shape_upper_bound=ML_TAIL_EVT_SHAPE_UPPER_BOUND,
                            unibm_anchor=anchor,
                            preserve_var_without_es=True,
                            min_standardized_losses=min(
                                EVT_MIN_STANDARDIZED_LOSSES_95, DEFAULT_MIN_TRAIN_ROWS
                            ),
                            min_exceedances=min(
                                EVT_MIN_EXCEEDANCES_95, DEFAULT_MIN_TRAIN_EXCEEDANCES
                            ),
                        )
                    )
                qz = float(metadata["standardized_var"])
                ez = metadata["standardized_es"]
                with np.errstate(over="ignore", invalid="ignore"):
                    q = pred["location"] + pred["scale"] * qz
                    e = pred["location"] + pred["scale"] * (float(ez) if ez is not None else np.nan)
                # No ES replacement/projection: eligibility reports the raw result.
                emit(
                    body_model_name(recipe, tail),
                    q,
                    e,
                    companion=tail,
                    es_failure=metadata.get("evt_es_failure_reason"),
                    predictions=pred,
                )
                metadata["fit_status"] = "ok"
            except Exception as exc:
                failure = f"{type(exc).__name__}: {exc}"
                metadata.update(fit_status="unavailable_tail_fit", failure_reason=failure)
                emit(
                    body_model_name(recipe, tail),
                    unavailable,
                    unavailable,
                    failure=failure,
                    companion=tail,
                    predictions=pred,
                )
            metadata["runtime_seconds"] = time.perf_counter() - tail_start
            detail["tails"][tail] = metadata
        diagnostics.append(detail)
        if progress:
            progress(f"{recipe}: body and three tail streams recorded")
    return {"forecasts": forecasts, "diagnostics": diagnostics, calibration_kind: oof}


def _prepare_body_run(
    source_run: Path, output_dir: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Reuse source data only; regenerate sample/coverage and record the actual estimator."""
    if output_dir == source_run or source_run in output_dir.parents:
        raise ValueError("Body output must be outside the frozen source run")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite body output: {output_dir}")
    source = json.loads((source_run / "manifest.json").read_text())
    lower_bound = max(
        source["main_sample_start_requested"], source["jquants_required_field_coverage_start"]
    )
    panel = pl.read_parquet(source_run / "panel/modeling_panel.parquet").sort("forecast_date")
    if panel["forecast_date"].n_unique() != panel.height:
        raise ValueError("Source panel has duplicate target dates")
    panel_rows = apply_combined_clean_start(panel.to_dicts(), combined_clean_start=lower_bound)
    effective_predictor_start = build_effective_predictor_start(
        build_feature_coverage_records(panel_rows)
    )
    lower_bound = max(
        lower_bound,
        compute_combined_clean_start(
            jquants_required_field_coverage_start=source["jquants_required_field_coverage_start"],
            massive_daily_entitlement_start=effective_predictor_start.get("massive_daily"),
            fred_required_series_coverage_start=_max_date_strings(
                effective_predictor_start.get("fred_core"), effective_predictor_start.get("fx_core")
            ),
        ),
    )
    panel_rows = apply_combined_clean_start(panel_rows, combined_clean_start=lower_bound)
    coverage = build_feature_coverage_records(panel_rows)
    levels = PIPELINE_CONFIG.model_policy.tail_levels
    if len(levels) != 1:
        raise ValueError("Body experiment requires the registered single tail level")
    public = importlib.import_module("unibm.evi")
    public_path = public.__file__
    if public_path is None:
        raise ValueError("Public UniBM module must have an auditable source path")
    public_dir = Path(public_path).resolve().parent
    public_git = {
        key: subprocess.run(
            ["git", "-C", str(public_dir), *command],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for key, command in (
            ("git_commit", ["rev-parse", "HEAD"]),
            ("git_status", ["status", "--short"]),
        )
    }
    manifest = {
        **PIPELINE_CONFIG.to_jsonable(),
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "source_run": str(source_run),
        "source_git_commit": source.get("git_commit"),
        "source_config_hash": source.get("config_hash"),
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "config_hash": PIPELINE_CONFIG.config_hash(),
        "sample_policy": "clean_predictor_entitlement_sample",
        "combined_clean_start": lower_bound,
        "effective_predictor_start": effective_predictor_start,
        "main_sample_start_requested": source["main_sample_start_requested"],
        "jquants_required_field_coverage_start": source["jquants_required_field_coverage_start"],
        "fred_vintage_policy": source.get("fred_vintage_policy"),
        "tail_level": levels[0],
        "model_names": list(EXPERIMENT_MODEL_NAMES),
        "body_recipes": BODY_RECIPES,
        "training_multiplier": TRAINING_MULTIPLIER,
        "public_unibm": {"source_path": public.__file__, **public_git},
        "python_version": sys.version,
        "lightgbm_version": lgb.__version__,
        "numpy_version": np.__version__,
        "polars_version": pl.__version__,
    }
    return manifest, panel_rows, coverage


def _write_body_panel(
    output_dir: Path,
    source_run: Path,
    panel_rows: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
) -> None:
    # New local paths and bindings; never inherit source gold_artifacts/gold_root.
    _write_parquet(output_dir / "panel/modeling_panel.parquet", panel_rows)
    _write_parquet(output_dir / "panel/feature_coverage.parquet", coverage)
    _write_parquet(
        output_dir / "panel/calendar_map.parquet",
        pl.read_parquet(source_run / "panel/calendar_map.parquet").to_dicts(),
    )
    write_leakage_check(run_dir=output_dir)
    _assert_leakage_gate(output_dir)


def monthly_body_refits(
    rows: list[dict[str, Any]], *, tail_level: float
) -> Iterator[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Monthly expanding prefixes, starting at the native OOS date (even mid-month)."""
    start = find_oos_start_date(rows, tail_level=tail_level)
    if start is None:
        raise ValueError("No scheduled OOS dates under the registered training policy")
    clean = [
        row
        for row in rows
        if row["clean_sample"] is True and _optional_float(row["realized_loss"]) is not None
    ]
    scheduled = ((i, row) for i, row in enumerate(clean) if str(row["forecast_date"]) >= start)
    for _, group in groupby(scheduled, key=lambda item: str(item[1]["forecast_date"])[:7]):
        month = list(group)
        yield clean[: month[0][0]], [row for _, row in month]


def run_body_pilot(
    source_run: Path,
    output_dir: Path,
    *,
    forecast_date: str,
    information_set: str,
    tail_side: str,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """One date, one info set, one exposure, 28 specs; never overwrite the source."""
    started = time.perf_counter()
    date.fromisoformat(forecast_date)
    source_run, output_dir = source_run.resolve(), output_dir.resolve()
    manifest, panel_rows, coverage = _prepare_body_run(source_run, output_dir)
    candidates = ml_tail_feature_columns_for_information_set(
        coverage, information_set=information_set
    )
    rows = build_ml_tail_modeling_rows(
        panel_rows, candidate_features=candidates, tail_side=tail_side
    )
    level = float(manifest["tail_level"])
    batch = next(
        (
            (train, future)
            for train, future in monthly_body_refits(rows, tail_level=level)
            if future[0]["forecast_date"] == forecast_date
        ),
        None,
    )
    if batch is None:
        raise ValueError("Pilot date must be the first eligible OOS session of its refit month")
    train, month = batch
    manifest.update(
        kind="shared_body_single_refit_pilot",
        information_set=information_set,
        tail_side=tail_side,
        forecast_date=forecast_date,
        oos_start=find_oos_start_date(rows, tail_level=level),
        train_n=len(train),
        candidate_feature_count=len(candidates),
        claims_boundary="runtime and numerical integration only; no performance inference",
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "manifest.json", manifest)
    try:
        _write_body_panel(output_dir, source_run, panel_rows, coverage)
        if progress:
            progress(
                f"pilot ready: {len(train)} training rows, {len(candidates)} candidate features"
            )
        result = forecast_shared_body_refit(
            train,
            [month[0]],
            candidate_features=candidates,
            information_set=information_set,
            tail_side=tail_side,
            tail_level=level,
            progress=progress,
        )
        forecasts = index_forecast_sessions(
            result["forecasts"], session_dates=[str(row["forecast_date"]) for row in panel_rows]
        )
        _write_parquet(output_dir / "forecasts/ml_tail_forecasts.parquet", forecasts)
        _write_parquet(output_dir / "diagnostics/oof_residuals.parquet", result["oof"])
        _write_json(output_dir / "diagnostics/refit.json", {"refits": result["diagnostics"]})
        # Keep leakage metadata added by the existing writer.
        manifest = json.loads((output_dir / "manifest.json").read_text())
        manifest.update(
            status="completed",
            forecast_rows=len(forecasts),
            eligibility_counts={
                score: sum(forecast_eligible(row, score=score) for row in forecasts)
                for score in ("var", "joint", "fz0")
            },
        )
    except Exception as exc:
        manifest.update(status="failed", failure_reason=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        manifest.update(
            ended_at_utc=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.perf_counter() - started,
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
        )
        _write_json(output_dir / "manifest.json", manifest)
    return output_dir


def run_body_rolling(
    source_run: Path,
    output_dir: Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Generate the fixed 28 x A--D x both-tail grid; no external fits or selection.

    Each refit's diagnostics and original-position OOF rows are written immediately.
    No legacy shards are loaded, and existing output directories are never reused.
    """
    started = time.perf_counter()
    source_run, output_dir = source_run.resolve(), output_dir.resolve()
    manifest, panel_rows, coverage = _prepare_body_run(source_run, output_dir)
    information_sets = registered_ml_tail_information_sets()
    manifest.update(
        kind="shared_body_rolling_forecast",
        information_sets=list(information_sets),
        tail_sides=list(TAIL_SIDES),
        refit_frequency="monthly",
        claims_boundary="exploratory_same_inspected_oos_not_fresh_holdout",
        completed_refits=0,
        forecast_rows=0,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "manifest.json", manifest)
    session_dates = [str(row["forecast_date"]) for row in panel_rows]
    forecasts: list[dict[str, Any]] = []
    level = float(manifest["tail_level"])
    try:
        _write_body_panel(output_dir, source_run, panel_rows, coverage)
        manifest = json.loads((output_dir / "manifest.json").read_text())
        # ponytail: serial scenario loop; use existing joblib only if full-run budgeting needs it.
        for side in TAIL_SIDES:
            for info in information_sets:
                candidates = ml_tail_feature_columns_for_information_set(
                    coverage, information_set=info
                )
                rows = build_ml_tail_modeling_rows(
                    panel_rows, candidate_features=candidates, tail_side=side
                )
                for train, future in monthly_body_refits(rows, tail_level=level):
                    refit_date = str(future[0]["forecast_date"])
                    if progress:
                        progress(f"refit {info}/{side}/{refit_date}: train_n={len(train)}")
                    result = forecast_shared_body_refit(
                        train,
                        future,
                        candidate_features=candidates,
                        information_set=info,
                        tail_side=side,
                        tail_level=level,
                        progress=progress,
                    )
                    records = index_forecast_sessions(
                        result["forecasts"], session_dates=session_dates
                    )
                    refit_dir = output_dir / "refits" / info / side / refit_date
                    _write_parquet(refit_dir / "forecasts.parquet", records)
                    _write_parquet(refit_dir / "oof_residuals.parquet", result["oof"])
                    _write_json(refit_dir / "diagnostics.json", {"refits": result["diagnostics"]})
                    forecasts.extend(records)
                    manifest.update(
                        completed_refits=manifest["completed_refits"] + 1,
                        forecast_rows=len(forecasts),
                        last_refit=f"{info}/{side}/{refit_date}",
                    )
                    _write_json(output_dir / "manifest.json", manifest)
        _write_parquet(output_dir / "forecasts/ml_tail_forecasts.parquet", forecasts)
        manifest.update(
            status="completed",
            eligibility_counts={
                score: sum(forecast_eligible(row, score=score) for row in forecasts)
                for score in ("var", "joint", "fz0")
            },
        )
    except Exception as exc:
        manifest.update(status="failed", failure_reason=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        manifest.update(
            ended_at_utc=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.perf_counter() - started,
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
        )
        _write_json(output_dir / "manifest.json", manifest)
    return output_dir
