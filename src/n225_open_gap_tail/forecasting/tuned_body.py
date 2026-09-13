"""Jointly tuned shared-body execution, retaining the established tail/output path."""

from __future__ import annotations

import json
import resource
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from n225_open_gap_tail.config.runtime import TAIL_SIDES, _set_nested_thread_limits
from n225_open_gap_tail.data_lake.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.forecasting.body_experiment import (
    _prepare_body_run,
    _write_body_panel,
    forecast_shared_body_refit,
    monthly_body_refits,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, index_forecast_sessions
from n225_open_gap_tail.models.ml_tail import build_ml_tail_modeling_rows
from n225_open_gap_tail.models.ml_tuning import (
    CANDIDATES,
    CV_SPLITS,
    ROUND_CAPS,
    BoundedFit,
    fit_joint_bodies,
)
from n225_open_gap_tail.panel.information_sets import (
    ml_tail_feature_columns_for_information_set,
    registered_ml_tail_information_sets,
)


def _save_working_source(output_dir: Path) -> None:
    """Git HEAD plus tracked diff and new source files reproduce uncommitted execution."""
    patch = subprocess.run(
        ["git", "diff", "HEAD", "--", "src", "pyproject.toml"], check=True, capture_output=True
    ).stdout
    directory = output_dir / "source"
    directory.mkdir(parents=True)
    (directory / "working-tree.patch").write_bytes(patch)
    new = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "src"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for name in new:
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(name, destination)


def _run_month(
    month: str,
    cases: dict[str, dict[str, Any]],
    *,
    output_dir: Path,
    session_dates: list[str],
    runtime: BoundedFit,
    progress: Callable[[str], None] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Independent months may run concurrently; selection within a month stays eight-way."""
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    def receipt(record: dict[str, Any]) -> None:
        receipts.append(record)
        _write_json(output_dir / "selection" / f"{month}.json", {"selections": receipts})
        if progress:
            progress(
                f"{month} {record['role']} cutoff={record['cutoff']} {record['status']}: "
                f"{record['selected_name']}/{record['parameters']['n_estimators']}"
            )

    try:
        runtime.check()
        if progress:
            progress(
                f"joint refit {month}: eight scenarios, "
                f"native n={[len(c['train']) for c in cases.values()]}"
            )
        fitted = fit_joint_bodies(cases, runtime=runtime, receipt=receipt, progress=progress)
        for key, case in cases.items():
            runtime.check()
            if progress:
                progress(f"tail calibration {month}/{key}")
            result = forecast_shared_body_refit(
                case["train"],
                case["future"],
                candidate_features=case["features"],
                information_set=case["information_set"],
                tail_side=case["tail_side"],
                tail_level=case["tail_level"],
                components=fitted[key],
                calibration_kind="oof",
                progress=progress,
            )
            current = index_forecast_sessions(result["forecasts"], session_dates=session_dates)
            refit = str(case["future"][0]["forecast_date"])
            refit_dir = output_dir / "refits" / key / refit
            _write_parquet(refit_dir / "forecasts.parquet", current)
            _write_parquet(refit_dir / "oof_residuals.parquet", result["oof"])
            _write_json(refit_dir / "diagnostics.json", {"refits": result["diagnostics"]})
            records.extend(current)
        runtime.check()
        stats = {
            "month": month,
            "elapsed_seconds": time.monotonic() - started,
            "native_fit_count": runtime.fits,
            "native_fit_timeouts": runtime.timeouts,
            "worker_peak_rss_bytes": runtime.worker_peak_rss_bytes,
            "forecast_rows": len(records),
        }
        _write_json(output_dir / "selection" / f"{month}_runtime.json", stats)
        return records, stats
    finally:
        runtime.close()


def run_tuned_body(
    source_run: Path,
    output_dir: Path,
    *,
    forecast_date: str | None = None,
    progress: Callable[[str], None] | None = None,
    workers: int = 2,
) -> Path:
    """All eight scenarios, all 22 specs; optional one-date pilot capped at 60min.

    Full runs retain monthly shards and receipts as they finish. Outputs are new;
    no old forecasts or fitted trees are reused and no model is dropped by gates.
    """
    started = time.monotonic()
    if forecast_date is not None:
        date.fromisoformat(forecast_date)
    if workers < 1 or workers > 3 or (forecast_date is not None and workers != 1):
        raise ValueError("Use 1--3 independent month workers; the bounded pilot requires workers=1")
    _set_nested_thread_limits()
    source_run, output_dir = source_run.resolve(), output_dir.resolve()
    manifest, panel, coverage = _prepare_body_run(source_run, output_dir)
    level = float(manifest["tail_level"])
    info_sets = registered_ml_tail_information_sets()
    schedule: dict[str, dict[str, dict[str, Any]]] = {}
    for info in info_sets:
        features = ml_tail_feature_columns_for_information_set(coverage, information_set=info)
        for side in TAIL_SIDES:
            rows = build_ml_tail_modeling_rows(panel, candidate_features=features, tail_side=side)
            for train, future in monthly_body_refits(rows, tail_level=level):
                if forecast_date and str(future[0]["forecast_date"]) != forecast_date:
                    continue
                month = str(future[0]["forecast_date"])[:7]
                schedule.setdefault(month, {})[f"{info}/{side}"] = {
                    "train": train,
                    "future": [future[0]] if forecast_date else future,
                    "features": features,
                    "information_set": info,
                    "tail_side": side,
                    "tail_level": level,
                }
    if not schedule:
        raise ValueError("Pilot date must be the first eligible OOS session of its refit month")
    if any(len(cases) != 8 for cases in schedule.values()):
        raise ValueError("Joint experiment requires all eight scenario schedules in each month")
    manifest.update(
        kind="shared_body_joint_tuning_pilot" if forecast_date else "shared_body_rolling_forecast",
        information_sets=list(info_sets),
        tail_sides=list(TAIL_SIDES),
        refit_frequency="monthly",
        claims_boundary="exploratory_same_inspected_oos_not_fresh_holdout",
        body_parameter_policy="expanding_cv_eight_scenario_component_validation",
        tail_calibration="selected_parameter_expanding_oof_standardized_residuals",
        calibration_warmup_policy="per_refit_component_structural_warmup",
        tuning={
            "candidates": dict(CANDIDATES),
            "round_caps": list(ROUND_CAPS),
            "cv_splits": CV_SPLITS,
            "cv_shuffle": False,
            "block_size": "ceil((common_training_rows-250)/5)",
            "parameter_selection_boundary": "full_outer_training_history_not_historical_replay",
            "validation_aggregation": "pooled_dates_within_case_then_equal_eight_cases",
            "min_prior_training_rows": 250,
            "single_fit_seconds": 300,
            "joint_selection_seconds": 1800,
            "pilot_seconds": 3600 if forecast_date else None,
            "tie_break": "mean_loss_then_fewer_rounds_then_candidate_order",
        },
        completed_refits=0,
        forecast_rows=0,
        planned_months=len(schedule),
        month_workers=workers,
        native_fit_count=0,
        native_fit_timeouts=0,
        worker_peak_rss_bytes=0,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "manifest.json", manifest)
    forecasts: list[dict[str, Any]] = []
    session_dates = [str(row["forecast_date"]) for row in panel]
    try:
        _save_working_source(output_dir)
        _write_body_panel(output_dir, source_run, panel, coverage)
        manifest = json.loads((output_dir / "manifest.json").read_text())

        def run(month: str, cases: dict[str, dict[str, Any]]) -> Any:
            remaining = max(0, 3600 - (time.monotonic() - started)) if forecast_date else None
            return _run_month(
                month,
                cases,
                output_dir=output_dir,
                session_dates=session_dates,
                runtime=BoundedFit(total_seconds=remaining),
                progress=progress,
            )

        def collect(result: tuple[list[dict[str, Any]], dict[str, Any]]) -> None:
            records, stats = result
            forecasts.extend(records)
            manifest.update(
                completed_refits=manifest["completed_refits"] + 8,
                forecast_rows=len(forecasts),
                last_completed_month=stats["month"],
                native_fit_count=manifest["native_fit_count"] + stats["native_fit_count"],
                native_fit_timeouts=manifest["native_fit_timeouts"] + stats["native_fit_timeouts"],
                worker_peak_rss_bytes=max(
                    manifest["worker_peak_rss_bytes"], stats["worker_peak_rss_bytes"]
                ),
            )
            _write_json(output_dir / "manifest.json", manifest)

        if workers == 1:
            for month, cases in sorted(schedule.items()):
                collect(run(month, cases))
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                pending = [
                    executor.submit(run, month, cases) for month, cases in sorted(schedule.items())
                ]
                try:
                    for job in as_completed(pending):
                        collect(job.result())
                except BaseException:
                    for job in pending:
                        job.cancel()
                    raise
        forecasts.sort(
            key=lambda row: (
                row["tail_side"],
                row["information_set"],
                row["model_name"],
                row["forecast_date"],
            )
        )
        _write_parquet(output_dir / "forecasts/ml_tail_forecasts.parquet", forecasts)
        manifest.update(
            status="completed",
            eligibility_counts={
                score: sum(forecast_eligible(row, score=score) for row in forecasts)
                for score in ("var", "joint", "fz0")
            },
        )
    except BaseException as exc:
        manifest.update(status="failed", failure_reason=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        manifest.update(
            ended_at_utc=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.monotonic() - started,
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
        )
        _write_json(output_dir / "manifest.json", manifest)
    return output_dir
