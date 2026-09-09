"""Evaluate frozen forecasts without fitting models or changing the source run."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import polars as pl

from n225_open_gap_tail.config.git import _git_commit, _git_dirty
from n225_open_gap_tail.config.runtime import (
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
    ML_TAIL_MODEL_NAMES,
    _optional_float,
    _required_float,
    find_oos_start_date,
)
from n225_open_gap_tail.data_lake.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.inference.core import build_common_sample_artifacts
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
    coverage_admissibility_summary_rows,
    pass_all_row_passes,
)
from n225_open_gap_tail.metrics.cross_suite_dm import build_screened_comparison_artifacts
from n225_open_gap_tail.metrics.grem import build_grem_artifacts
from n225_open_gap_tail.metrics.result_matrix import (
    build_metric_records,
    build_ml_tail_result_matrix_artifacts,
)
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, index_forecast_sessions
from n225_open_gap_tail.models.ml_body import EXPERIMENT_MODEL_NAMES


def reevaluate_frozen_run(run_dir: Path, *, output_dir: Path | None = None) -> Path:
    run_dir = run_dir.resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = (output_dir or run_dir.parent / f"reevaluation_{run_dir.name}_{stamp}").resolve()
    if output_dir == run_dir or run_dir in output_dir.parents:
        raise ValueError("Frozen re-evaluation output must be outside the source run")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite re-evaluation output: {output_dir}")
    source_manifest = json.loads((run_dir / "manifest.json").read_text())
    body_experiment = source_manifest.get("kind") == "shared_body_rolling_forecast"
    ml_model_names = EXPERIMENT_MODEL_NAMES if body_experiment else ML_TAIL_MODEL_NAMES
    if body_experiment and source_manifest.get("model_names") != list(ml_model_names):
        raise ValueError("Body experiment manifest does not contain the registered 28-model roster")
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    panel_columns = pl.read_parquet_schema(panel_path)
    columns: list[str] = [
        name
        for name in (
            "forecast_date",
            "clean_sample",
            "realized_loss",
            "target_clean_sample",
            "forecast_sample_reason",
            "missing_reason",
            "mapping_status",
        )
        if name in panel_columns
    ]
    panel = pl.read_parquet(panel_path, columns=columns).sort("forecast_date")
    if panel["forecast_date"].n_unique() != panel.height:
        raise ValueError("Frozen panel contains duplicate target dates")
    policy = source_manifest["model_policy"]
    levels = policy["tail_levels"]
    if len(levels) != 1:
        raise ValueError("Frozen replay currently requires one tail level per source run")
    level = float(levels[0])
    start = find_oos_start_date(
        panel.select("forecast_date", "clean_sample", "realized_loss").to_dicts(),
        earliest_oos_start=policy["earliest_oos_start"],
        min_train_rows=policy["min_train_rows"],
        min_train_exceedances=policy["min_train_exceedances"],
        tail_level=level,
    )
    if start is None:
        raise ValueError("Original frozen training policy has no scheduled OOS dates")
    panel_rows = {str(row["forecast_date"]): row for row in panel.iter_rows(named=True)}
    scheduled = {
        day: row for day, row in panel_rows.items() if day >= start and row["clean_sample"] is True
    }
    target = str(source_manifest["target_policy"]["primary_target_family"])
    forecasts: list[dict[str, object]] = []
    source_failures: list[dict[str, object]] = []
    fit_diagnostics: list[dict[str, object]] = []
    source_files = [run_dir / "manifest.json", panel_path]
    for suite, filename in (
        ("benchmark", "benchmark_forecasts.parquet"),
        ("ml_tail", "ml_tail_forecasts.parquet"),
    ):
        path = run_dir / "forecasts" / filename
        source_files.append(path)
        forecasts.extend(
            {**row, "suite": suite} for row in pl.read_parquet(path).iter_rows(named=True)
        )
        failure_path = path.with_name(filename.replace("forecasts", "failures"))
        if failure_path.exists():
            source_files.append(failure_path)
            source_failures.extend(
                {**row, "suite": suite}
                for row in pl.read_parquet(failure_path).iter_rows(named=True)
            )
        diagnostic_path = path.with_name(filename.replace("forecasts", "fit_diagnostics"))
        if diagnostic_path.exists():
            source_files.append(diagnostic_path)
            fit_diagnostics.extend(pl.read_parquet(diagnostic_path).to_dicts())
    forecasts = index_forecast_sessions(forecasts, session_dates=list(panel_rows))
    ledger, availability = _availability_records(
        forecasts, scheduled, target=target, level=level, ml_model_names=ml_model_names
    )
    native = build_metric_records(forecasts)
    for row in native:
        row["coverage_gate_pass"] = pass_all_row_passes(row)
    native_frame = pl.from_dicts(native, infer_schema_length=None)
    screens = coverage_admissibility_summary_rows(native_frame, model_order=ml_model_names)
    screens.extend(
        coverage_admissibility_summary_rows(
            native_frame,
            model_order=BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES,
            information_sets=("target_history_only",),
        )
    )
    screened = build_screened_comparison_artifacts(
        forecasts, native_frame, ml_model_names=ml_model_names
    )
    ml_rows = [row for row in forecasts if row["suite"] == "ml_tail"]
    ml = build_ml_tail_result_matrix_artifacts(ml_rows, model_names=ml_model_names)
    outputs: dict[str, list[dict[str, object]]] = {
        "native_metrics": native,
        "coverage_admissibility": screens,
        "availability": availability,
        "availability_by_date": ledger,
        "source_failure_records": source_failures,
        "target_schedule": [
            {
                "forecast_date": day,
                "scheduled_for_frozen_run": day in scheduled,
                "target_clean_sample": row.get("target_clean_sample"),
                "forecast_sample_reason": row.get("forecast_sample_reason"),
                "missing_reason": row.get("missing_reason"),
            }
            for day, row in panel_rows.items()
            if day >= start
        ],
        **{f"screened_{key}": rows for key, rows in screened.items()},
        **{
            f"ml_{key}": cast(list[dict[str, object]], ml[key])
            for key in ("matrix", "sample_audit", "dm")
        },
    }
    for tier, models in (
        ("baseline", BENCHMARK_BASELINE_MODEL_NAMES),
        ("advanced", BENCHMARK_ADVANCED_MODEL_NAMES),
    ):
        comparison = build_common_sample_artifacts(
            [row for row in forecasts if row["model_name"] in models],
            suite=f"benchmark_{tier}",
            anchor_model=models[0],
            anchor_information_set="target_history_only",
            model_names=models,
        )
        for key in ("primary_metrics", "model_eviction", "dm_inference"):
            outputs[f"benchmark_{tier}_{key}"] = cast(list[dict[str, object]], comparison[key])
    # Selection is already fixed above. Sequential diagnostics never feed back into it.
    outputs.update(
        build_grem_artifacts(
            forecasts,
            roster=availability,
            panel_rows=panel_rows,
            start=start,
            target=target,
            tail_level=level,
            unavailable_records=source_failures + fit_diagnostics,
        )
    )
    manifest: dict[str, object] = {
        "kind": "frozen_forecast_reevaluation",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_run_id": source_manifest.get("run_id", run_dir.name),
        "source_run_dir": str(run_dir),
        "source_git_commit": source_manifest.get("git_commit"),
        "source_git_dirty": source_manifest.get("git_dirty"),
        "source_config_hash": source_manifest.get("config_hash"),
        "source_run_kind": source_manifest.get("kind"),
        "ml_model_names": list(ml_model_names),
        "evaluator_git_commit": _git_commit(),
        "evaluator_git_dirty": _git_dirty(),
        "source_files": [str(path) for path in source_files],
        "forecast_rows": len(forecasts),
        "native_scenarios": len(native),
        "scheduled_start": start,
        "scheduled_end": max(scheduled),
        "scheduled_rows_per_scenario": len(scheduled),
        "target_axis": "full_frozen_panel_dates_before_sample_or_forecast_filters",
        "target_axis_oos_rows": sum(day >= start for day in panel_rows),
        "source_model_policy": policy,
        "evaluation_policy": {
            "native_gates": (
                "own_valid_var_sample_n450_breach_band_0.025_kupiec_and_independence_p0.05"
            ),
            "ml_admission": "all_four_information_sets_and_both_tails",
            "external_admission": "both_tails_then_external_only_shared_fz0_dates",
            "comparisons": "fixed_roster_by_question_separate_var_and_fz0_common_dates",
            "missing_members": "explicit_unavailable_never_silently_drop",
            "bootstrap": "circular_target_session_blocks_with_missing_mask_reps999_seed225",
        },
        "forecast_retrained": False,
        "grem_policy": {
            "method": "equal_capital_GREE_GREL_mixture_Taylor_approximation_gamma0.5",
            "windows": [500, 250],
            "population": "all_registered_candidates_before_coverage_screening",
            "history": "past_eligible_observations_only_short_initial_history_zero_first_bet",
            "monitoring": "native_full_target_axis_no_capital_resets",
            "missingness": "audited_cutoff_no_bets_otherwise_explicit_unavailable_suffix",
            "domain": "finite_loss_var_es_and_es_strictly_greater_than_var_not_FZ0_domain",
            "null": "correct_conditional_VaR_and_ES_not_underreported",
            "reference_level": 20,
            "error_scope": "single_sequence_5pct_anytime_not_familywise_or_post_selection",
            "used_for_selection": False,
            "source": "https://arxiv.org/html/2209.00991v6",
        },
        "calendar_features_regenerated": False,
        "claim_scope": "exploratory_same_inspected_oos_not_fresh_holdout",
        "source_limitations": {
            "fred_vintage_policy": source_manifest.get("fred_vintage_policy"),
            "sample_policy": source_manifest.get("sample_policy"),
            "estimator": "shared_nine_body_public_unibm_strict_fgls"
            if body_experiment
            else "original_frozen_methods_not_updated_UniBM_or_nine_body_design",
            "training_multiplier": source_manifest.get("training_multiplier")
            if body_experiment
            else None,
            "public_unibm": source_manifest.get("public_unibm") if body_experiment else None,
        },
        "output_rows": {name: len(rows) for name, rows in outputs.items()},
    }
    output_dir.mkdir(parents=True)
    for name, rows in outputs.items():
        _write_parquet(output_dir / f"{name}.parquet", rows)
    # A directory without this last-written manifest is an incomplete evaluation.
    _write_json(output_dir / "manifest.json", manifest)
    return output_dir


def _availability_records(
    forecasts: list[dict[str, object]],
    scheduled: dict[str, dict[str, Any]],
    *,
    target: str,
    level: float,
    ml_model_names: tuple[str, ...] = ML_TAIL_MODEL_NAMES,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Reconcile recorded failures and absent rows against the frozen schedule."""
    roster = [
        (model, side, info)
        for models, infos in (
            (
                BENCHMARK_BASELINE_MODEL_NAMES + BENCHMARK_ADVANCED_MODEL_NAMES,
                ("target_history_only",),
            ),
            (ml_model_names, PASS_ALL_INFORMATION_SETS),
        )
        for model in models
        for side in PASS_ALL_TAIL_SIDES
        for info in infos
    ]
    by_scenario: dict[tuple[str, str, str], dict[str, dict[str, object]]] = {
        key: {} for key in roster
    }
    for row in forecasts:
        key = (str(row["model_name"]), str(row["tail_side"]), str(row["information_set"]))
        day = str(row["forecast_date"])
        if (
            key not in by_scenario
            or day not in scheduled
            or row.get("target_family") != target
            or row.get("tail_level") != level
        ):
            raise ValueError(f"Forecast outside registered frozen target/schedule: {key}, {day}")
        if day in by_scenario[key]:
            raise ValueError(f"Duplicate forecast scenario/date: {key}, {day}")
        loss = _optional_float(row.get("realized_loss"))
        expected_loss = _required_float(scheduled[day]["realized_loss"]) * (
            1 if key[1] == "left_tail" else -1
        )
        if loss is not None and not math.isclose(loss, expected_loss, rel_tol=1e-12, abs_tol=1e-14):
            raise ValueError(f"Forecast loss disagrees with frozen panel: {key}, {day}")
        by_scenario[key][day] = row
    ledger: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for (model, side, info), by_date in by_scenario.items():
        scenario_rows = []
        for day in scheduled:
            row = by_date.get(day, {})
            var_ok = forecast_eligible(row)
            joint_ok = forecast_eligible(row, score="joint")
            fz_ok = forecast_eligible(row, score="fz0")
            reason = (
                "not_recorded"
                if not row
                else str(
                    row.get("failure_reason") or row.get("invalid_reason") or "invalid_var_or_loss"
                )
                if not var_ok
                else "invalid_or_unavailable_joint_pair"
                if not joint_ok
                else "outside_fz0_domain"
                if not fz_ok
                else "available"
            )
            record = {
                "model_name": model,
                "tail_side": side,
                "information_set": info,
                "forecast_date": day,
                "recorded": bool(row),
                "var_eligible": var_ok,
                "joint_eligible": joint_ok,
                "fz0_eligible": fz_ok,
                "original_fit_status": row.get("fit_status"),
                "original_is_valid_forecast": row.get("is_valid_forecast"),
                "original_failure_reason": row.get("failure_reason"),
                "original_invalid_reason": row.get("invalid_reason"),
                "availability_reason": reason,
                "recovered_var_from_legacy_es_filter": var_ok
                and row.get("is_valid_forecast") is False,
            }
            scenario_rows.append(record)
        counts = Counter(str(row["availability_reason"]) for row in scenario_rows)
        summary.append(
            {
                "model_name": model,
                "tail_side": side,
                "information_set": info,
                "scheduled_rows": len(scheduled),
                "recorded_rows": len(by_date),
                "missing_rows": len(scheduled) - len(by_date),
                **{
                    f"{metric}_rows": sum(bool(row[f"{metric}_eligible"]) for row in scenario_rows)
                    for metric in ("var", "joint", "fz0")
                },
                "recovered_var_rows": sum(
                    bool(row["recovered_var_from_legacy_es_filter"]) for row in scenario_rows
                ),
                "reason_counts_json": json.dumps(counts, sort_keys=True),
            }
        )
        ledger.extend(scenario_rows)
    return ledger, summary
