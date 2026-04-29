# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


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
