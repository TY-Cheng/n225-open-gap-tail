# mypy: ignore-errors
# ruff: noqa: F401
from __future__ import annotations

from pathlib import Path
from typing import cast

from n225_open_gap_tail.config.runtime import (
    PipelineRunError,
    _bounded_workers,
    _evaluation_log,
    _set_nested_thread_limits,
    read_json,
    validate_worker_payload,
)
from n225_open_gap_tail.metrics.information import _gold_artifact_path
from n225_open_gap_tail.panel.leakage import _current_leakage_binding


def _assert_leakage_gate(run_dir: Path) -> None:
    summary_path = run_dir / "audits" / "leakage_check_summary.json"
    if not summary_path.exists():
        raise PipelineRunError(
            "Evaluation requires a leakage check artifact; run `just _leakage-check` first."
        )
    summary = read_json(summary_path)
    failures = int(cast(int | float | str, summary.get("failures") or 0))
    if failures:
        raise PipelineRunError(f"Paper evaluation blocked by leakage check failures: {failures}")
    expected = _current_leakage_binding(run_dir)
    keys = (
        "panel_signature",
        "panel_signature_hash_seed",
        "panel_row_count",
        "panel_forecast_date_min",
        "panel_forecast_date_max",
        "panel_target_open_ts_utc_min",
        "panel_target_open_ts_utc_max",
        "panel_model_cutoff_ts_utc_min",
        "panel_model_cutoff_ts_utc_max",
        "calendar_map_hash",
        "bound_config_hash",
    )
    mismatches = [key for key in keys if summary.get(key) != expected.get(key)]
    if mismatches:
        raise PipelineRunError(
            "Paper evaluation blocked by stale leakage check artifact; "
            f"mismatched fields: {', '.join(mismatches)}"
        )
