"""Evaluate frozen forecasts without fitting models or changing the source run."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
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
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
    pass_all_row_passes,
)
from n225_open_gap_tail.metrics.grem import build_grem_artifacts
from n225_open_gap_tail.metrics.result_matrix import build_metric_records
from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts
from n225_open_gap_tail.metrics.score_inference import build_score_inference
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, index_forecast_sessions
from n225_open_gap_tail.models.ml_body import EXPERIMENT_MODEL_NAMES


def reevaluate_frozen_run(run_dir: Path, *, output_dir: Path | None = None) -> Path:
    started = time.perf_counter()
    run_dir = run_dir.resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = (output_dir or run_dir.parent / f"reevaluation_{run_dir.name}_{stamp}").resolve()
    if output_dir == run_dir or run_dir in output_dir.parents:
        raise ValueError("Frozen re-evaluation output must be outside the source run")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite re-evaluation output: {output_dir}")
    source_manifest_path = run_dir / "manifest.json"
    source_hashes = {str(source_manifest_path): _file_sha256(source_manifest_path)}
    source_manifest = json.loads(source_manifest_path.read_text())
    body_experiment = source_manifest.get("kind") == "shared_body_rolling_forecast"
    ml_model_names = EXPERIMENT_MODEL_NAMES if body_experiment else ML_TAIL_MODEL_NAMES
    if body_experiment and source_manifest.get("model_names") != list(ml_model_names):
        raise ValueError("Body experiment manifest does not contain the registered 22-model roster")
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    source_hashes[str(panel_path)] = _file_sha256(panel_path)
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
        source_hashes[str(path)] = _file_sha256(path)
        forecasts.extend(
            {**row, "suite": suite} for row in pl.read_parquet(path).iter_rows(named=True)
        )
        failure_path = path.with_name(filename.replace("forecasts", "failures"))
        if failure_path.exists():
            source_files.append(failure_path)
            source_hashes[str(failure_path)] = _file_sha256(failure_path)
            source_failures.extend(
                {**row, "suite": suite}
                for row in pl.read_parquet(failure_path).iter_rows(named=True)
            )
        diagnostic_path = path.with_name(filename.replace("forecasts", "fit_diagnostics"))
        if diagnostic_path.exists():
            source_files.append(diagnostic_path)
            source_hashes[str(diagnostic_path)] = _file_sha256(diagnostic_path)
            fit_diagnostics.extend(pl.read_parquet(diagnostic_path).to_dicts())
    forecasts = index_forecast_sessions(forecasts, session_dates=list(panel_rows))
    ledger, availability = _availability_records(
        forecasts, scheduled, target=target, level=level, ml_model_names=ml_model_names
    )
    native = build_metric_records(forecasts)
    for row in native:
        row["var_gate_pass"] = pass_all_row_passes(row)
    grem = build_grem_artifacts(
        forecasts,
        roster=availability,
        panel_rows=panel_rows,
        start=start,
        target=target,
        tail_level=level,
        unavailable_records=source_failures + fit_diagnostics,
    )
    comparison = build_robust_comparison_artifacts(
        forecasts, native, grem["grem_summary"], ml_model_names=ml_model_names
    )
    outputs: dict[str, list[dict[str, object]]] = {
        "native_metrics": native,
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
        **grem,
        **comparison,
        **_global_inference(comparison["daily_scores"]),
    }
    if any(_file_sha256(path) != source_hashes[str(path)] for path in source_files):
        raise RuntimeError("Source files changed during frozen reevaluation")
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
        "source_sha256": source_hashes,
        "source_hashes_verified_after_evaluation": True,
        "evaluation_elapsed_seconds": time.perf_counter() - started,
        "evaluation_protocol_version": "fzg_grem_global_20260921",
        "evaluation_source_sha256": {
            str(path.relative_to(Path(__file__).resolve().parents[1])): _file_sha256(path)
            for path in sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
        },
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
                "own_valid_var_n450_kupiec_independence_p0.05_"
                "plus_native_ES_GREM_W500_n450_complete_running_max_below20"
            ),
            "ml_admission": "all_four_information_sets_and_both_tails",
            "external_admission": "both_tails_then_external_only_shared_joint_dates",
            "reference": "one_global_minimum_equal_two_tail_FZG",
            "comparisons": "all_admitted_ML_plus_fixed_reference_single_joint_common_panel",
            "aggregation": "equal_eight_scenarios_per_date_then_equal_dates",
            "primary_score": "logistic_FZG_G1_identity_G2_sigmoid_primitive_softplus_log2",
            "score_units": "percentage_points_evaluation_only_training_unchanged",
            "secondary_score": "quantile_loss",
            "score_domain": "finite_coherent_signed_ES_no_positive_ES_restriction",
            "missing_members": "explicit_unavailable_never_silently_drop",
            "bootstrap": "joint_circular_target_session_blocks_mask_ratio_reps9999_seed225",
            "block_length": "max(5,round(N_common**(1/3)))_half_and_double_sensitivity",
            "paired_tests": "all_pairs_two_sided_centered_bootstrap_plus_one_Holm_by_score",
            "intervals": "pointwise_95pct_basic_not_simultaneous",
            "inference_floor": "n_common120_pairwise_five_distinct_exception_dates_union8",
            "mcs": "FZG_only_TR_nominal95_approximate_exploratory",
            "mcs_floor": "all_pairs_meet_inference_floor_or_whole_set_unavailable",
            "legacy_native_columns": "mean_fz_loss_is_FZ0_mean_quantile_loss_is_decimal",
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
            "used_for_selection": True,
            "selection_window": 500,
            "sensitivity_window_not_a_gate": 250,
            "minimum_input_eligible_rows": 450,
            "source": "https://arxiv.org/html/2209.00991v6",
        },
        "calendar_features_regenerated": False,
        "claim_scope": "exploratory_same_inspected_oos_not_fresh_holdout",
        "source_limitations": {
            "fred_vintage_policy": source_manifest.get("fred_vintage_policy"),
            "sample_policy": source_manifest.get("sample_policy"),
            "estimator": "shared_body_public_unibm_strict_fgls"
            if body_experiment
            else "original_frozen_methods_not_updated_UniBM_or_shared_body_design",
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


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _global_inference(daily: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {"global_scores": [], "pairwise": [], "mcs": []}
    if not daily:
        return result
    models = list(dict.fromkeys(str(row["model_name"]) for row in daily))
    dates = sorted({str(row["forecast_date"]) for row in daily})
    lookup = {(str(row["forecast_date"]), str(row["model_name"])): row for row in daily}
    if len(lookup) != len(daily) or len(lookup) != len(dates) * len(models):
        raise ValueError("Global inference requires a complete unique date/model score panel")
    indices = [
        int(_required_float(lookup[(day, models[0])]["target_session_index"])) for day in dates
    ]
    exceptions = np.array(
        [[bool(lookup[(day, model)]["exception"]) for model in models] for day in dates]
    )
    for score in ("fzg", "quantile_loss"):
        values = np.array(
            [[_required_float(lookup[(day, model)][score]) for model in models] for day in dates]
        )
        for model, mean in zip(models, np.mean(values, axis=0), strict=True):
            result["global_scores"].append(
                {
                    "model_name": model,
                    "score_name": score,
                    "mean_score": float(mean),
                    "n_common": len(dates),
                    "date_start": dates[0],
                    "date_end": dates[-1],
                    "scenario_weights": "equal_eight",
                    "date_weights": "equal",
                    "score_units": "percentage_points",
                    "scope": "exploratory_common_dates",
                }
            )
        inference = build_score_inference(
            values,
            model_names=models,
            session_indices=indices,
            exception_flags=exceptions,
            score_name=score,
        )
        result["pairwise"].extend(inference["pairwise"])
        result["mcs"].extend(inference["mcs"])
    return result


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
            fzg_ok = forecast_eligible(row, score="fzg")
            reason = (
                "not_recorded"
                if not row
                else str(
                    row.get("failure_reason") or row.get("invalid_reason") or "invalid_var_or_loss"
                )
                if not var_ok
                else "invalid_or_unavailable_joint_pair"
                if not joint_ok
                else "nonfinite_fzg_score"
                if not fzg_ok
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
                "fzg_eligible": fzg_ok,
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
                    for metric in ("var", "joint", "fz0", "fzg")
                },
                "recovered_var_rows": sum(
                    bool(row["recovered_var_from_legacy_es_filter"]) for row in scenario_rows
                ),
                "reason_counts_json": json.dumps(counts, sort_keys=True),
            }
        )
        ledger.extend(scenario_rows)
    return ledger, summary
