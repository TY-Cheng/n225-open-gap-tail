from __future__ import annotations

from pathlib import Path

from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.data_lake.artifacts import (
    _gold_leakage_dir,
    _gold_panel_dir,
)


def full_run_snapshot_paths(
    *,
    settings: Settings,
    run_dir: Path,
    manifest: dict[str, object],
) -> dict[str, Path]:
    run_id = str(manifest.get("run_id") or run_dir.name)
    gold_artifacts = _dict_value(manifest.get("gold_artifacts"))
    gold_panel_root = _gold_panel_dir(settings.gold_data_dir, run_id)
    leakage_root = _gold_leakage_dir(settings.gold_data_dir, run_id)
    leakage_summary = Path(
        str(gold_artifacts.get("leakage_summary", leakage_root / "summary.json"))
    )
    return {
        "manifest": run_dir / "manifest.json",
        "data_vintage": run_dir / "data_vintage.json",
        "modeling_panel": Path(
            str(gold_artifacts.get("modeling_panel", gold_panel_root / "modeling_panel.parquet"))
        ),
        "target_audit": Path(
            str(gold_artifacts.get("target_audit", gold_panel_root / "target_audit.parquet"))
        ),
        "calendar_map": Path(
            str(gold_artifacts.get("calendar_map", gold_panel_root / "calendar_map.parquet"))
        ),
        "feature_coverage": Path(
            str(
                gold_artifacts.get("feature_coverage", gold_panel_root / "feature_coverage.parquet")
            )
        ),
        "leakage_summary": leakage_summary,
        "benchmark_status": run_dir / "metrics" / "benchmark_status.json",
        "benchmark_metrics": run_dir / "metrics" / "benchmark_metrics.parquet",
        "benchmark_metrics_per_model": run_dir / "metrics" / "benchmark_metrics_per_model.parquet",
        "benchmark_forecasts": run_dir / "forecasts" / "benchmark_forecasts.parquet",
        "benchmark_dm_inference": run_dir / "metrics" / "benchmark_dm_inference.parquet",
        "benchmark_mcs": run_dir / "metrics" / "benchmark_mcs.parquet",
        "ml_tail_status": run_dir / "metrics" / "ml_tail_status.json",
        "ml_tail_metrics": run_dir / "metrics" / "ml_tail_metrics.parquet",
        "ml_tail_metrics_per_model": run_dir / "metrics" / "ml_tail_metrics_per_model.parquet",
        "ml_tail_forecasts": run_dir / "forecasts" / "ml_tail_forecasts.parquet",
        "ml_tail_result_matrix": run_dir / "metrics" / "ml_tail_result_matrix.parquet",
        "ml_tail_result_matrix_dm": run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet",
        "ml_tail_result_matrix_mcs": run_dir / "metrics" / "ml_tail_result_matrix_mcs.parquet",
        "ml_tail_dm_inference": run_dir / "metrics" / "ml_tail_dm_inference.parquet",
        "ml_tail_mcs": run_dir / "metrics" / "ml_tail_mcs.parquet",
        "ml_tail_cpa_inference": run_dir / "metrics" / "ml_tail_cpa_inference.parquet",
        "cross_model_cpa_inference": run_dir / "metrics" / "cross_model_cpa_inference.parquet",
        "ml_tail_model_eviction": run_dir / "metrics" / "ml_tail_model_eviction.parquet",
        "ml_tail_dst_attenuation": run_dir / "metrics" / "ml_tail_dst_attenuation.parquet",
        "ml_tail_murphy": run_dir / "metrics" / "ml_tail_murphy.parquet",
        "ml_tail_feature_unavailability": run_dir
        / "metrics"
        / "ml_tail_feature_unavailability.parquet",
        "benchmark_stress_windows": run_dir / "metrics" / "benchmark_stress_windows.parquet",
        "ml_tail_stress_windows": run_dir / "metrics" / "ml_tail_stress_windows.parquet",
        "figure_manifest": run_dir / "latex" / "figure_manifest.json",
        "table_manifest": run_dir / "latex" / "table_manifest.json",
        "latex_dir": run_dir / "latex" / "tables",
        "claim_scope_table": run_dir / "latex" / "tables" / "tailrisk_claim_scope_table.tex",
        "es_severity_table": run_dir / "latex" / "tables" / "tailrisk_es_severity_table.tex",
        "hedge_trigger_table": run_dir
        / "latex"
        / "tables"
        / "tailrisk_hedge_trigger_diagnostics_table.tex",
        "dst_attenuation_table": run_dir / "latex" / "tables" / "ml_tail_dst_attenuation_table.tex",
        "result_matrix_summary_table": run_dir
        / "latex"
        / "tables"
        / "ml_tail_result_matrix_summary_table.tex",
    }


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
