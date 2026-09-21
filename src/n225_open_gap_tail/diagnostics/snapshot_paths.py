from __future__ import annotations

from pathlib import Path


def full_run_snapshot_paths(*, run_dir: Path) -> dict[str, Path]:
    return {
        "manifest": run_dir / "manifest.json",
        "data_vintage": run_dir / "data_vintage.json",
        "modeling_panel": run_dir / "panel" / "modeling_panel.parquet",
        "target_audit": run_dir / "panel" / "target_audit.parquet",
        "calendar_map": run_dir / "panel" / "calendar_map.parquet",
        "feature_coverage": run_dir / "panel" / "feature_coverage.parquet",
        "leakage_summary": run_dir / "audits" / "leakage_check_summary.json",
        "benchmark_status": run_dir / "metrics" / "benchmark_status.json",
        "benchmark_metrics": run_dir / "metrics" / "benchmark_metrics.parquet",
        "benchmark_metrics_per_model": run_dir / "metrics" / "benchmark_metrics_per_model.parquet",
        "benchmark_forecasts": run_dir / "forecasts" / "benchmark_forecasts.parquet",
        "benchmark_dm_inference": run_dir / "metrics" / "benchmark_dm_inference.parquet",
        "ml_tail_status": run_dir / "metrics" / "ml_tail_status.json",
        "ml_tail_metrics": run_dir / "metrics" / "ml_tail_metrics.parquet",
        "ml_tail_metrics_per_model": run_dir / "metrics" / "ml_tail_metrics_per_model.parquet",
        "ml_tail_forecasts": run_dir / "forecasts" / "ml_tail_forecasts.parquet",
        "ml_tail_result_matrix": run_dir / "metrics" / "ml_tail_result_matrix.parquet",
        "ml_tail_result_matrix_dm": run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet",
        "ml_tail_dm_inference": run_dir / "metrics" / "ml_tail_dm_inference.parquet",
        "ml_tail_model_eviction": run_dir / "metrics" / "ml_tail_model_eviction.parquet",
        "lgbm_24check_murphy": run_dir / "metrics" / "lgbm_24check_murphy.parquet",
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
        "result_matrix_summary_table": run_dir
        / "latex"
        / "tables"
        / "ml_tail_result_matrix_summary_table.tex",
    }
