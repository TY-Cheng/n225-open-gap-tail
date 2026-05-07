# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    CLAIMS_LEVEL,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    Path,
    pl,
    TableExportResult as TableExportResult,
    TAIL_SIDE_LEFT,
    TAIL_SIDE_RIGHT,
)
from n225_open_gap_tail.forecasting.artifacts import _read_manifest, _update_manifest, _write_json
from n225_open_gap_tail.reporting.figures import export_figures
from n225_open_gap_tail.reporting.latex import (
    _claim_scope_to_latex,
    _dst_attenuation_to_latex,
    _es_severity_to_latex,
    _full_per_model_metrics_to_latex,
    _hedge_trigger_to_latex,
    _metrics_to_latex,
    _result_matrix_summary_to_latex,
    _result_matrix_to_latex,
    _selected_model_performance_to_latex,
)


def export_tables(*, run_dir: Path) -> TableExportResult:
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_tail_table_names(latex_dir)
    tables = 0
    table_files: list[str] = []
    manifest = _read_manifest(run_dir)
    for suite in ("benchmark", "ml_tail"):
        metrics_path = run_dir / "metrics" / f"{suite}_metrics.parquet"
        if not metrics_path.exists():
            continue
        metrics = pl.read_parquet(metrics_path)
        tex = _metrics_to_latex(metrics, manifest=manifest)
        table_path = latex_dir / f"{suite}_metrics_table.tex"
        table_path.write_text(tex, encoding="utf-8")
        tables += 1
        table_files.append(table_path.name)
        for active_tail_side, suffix in (
            (TAIL_SIDE_LEFT, "left_tail_risk"),
            (TAIL_SIDE_RIGHT, "right_tail_risk"),
        ):
            if "tail_side" not in metrics.columns:
                continue
            side_metrics = metrics.filter(pl.col("tail_side") == active_tail_side)
            if side_metrics.is_empty():
                continue
            side_path = latex_dir / f"{suite}_{suffix}_table.tex"
            side_path.write_text(
                _metrics_to_latex(side_metrics, manifest=manifest), encoding="utf-8"
            )
            tables += 1
            table_files.append(side_path.name)
    benchmark_per_model_path = run_dir / "metrics" / "benchmark_metrics_per_model.parquet"
    ml_tail_per_model_path = run_dir / "metrics" / "ml_tail_metrics_per_model.parquet"
    benchmark_per_model = (
        pl.read_parquet(benchmark_per_model_path)
        if benchmark_per_model_path.exists()
        else pl.DataFrame()
    )
    ml_tail_per_model = (
        pl.read_parquet(ml_tail_per_model_path)
        if ml_tail_per_model_path.exists()
        else pl.DataFrame()
    )
    if not benchmark_per_model.is_empty() and not ml_tail_per_model.is_empty():
        table_path = latex_dir / "tailrisk_selected_model_performance_table.tex"
        table_path.write_text(
            _selected_model_performance_to_latex(
                benchmark_per_model,
                ml_tail_per_model,
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    if not benchmark_per_model.is_empty():
        table_path = latex_dir / "appendix_benchmark_all_models_table.tex"
        table_path.write_text(
            _full_per_model_metrics_to_latex(
                benchmark_per_model,
                suite_group="Benchmark",
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    if not ml_tail_per_model.is_empty():
        table_path = latex_dir / "appendix_lgbm_all_models_table.tex"
        table_path.write_text(
            _full_per_model_metrics_to_latex(
                ml_tail_per_model,
                suite_group="LGBM",
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    severity_metrics = _combined_severity_metrics(run_dir)
    if not severity_metrics.is_empty():
        table_path = latex_dir / "tailrisk_es_severity_table.tex"
        table_path.write_text(
            _es_severity_to_latex(severity_metrics, manifest=manifest),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    trigger_forecasts = _combined_forecasts(run_dir)
    if not trigger_forecasts.is_empty():
        table_path = latex_dir / "tailrisk_hedge_trigger_diagnostics_table.tex"
        table_path.write_text(
            _hedge_trigger_to_latex(trigger_forecasts, manifest=manifest),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    if severity_metrics.is_empty() is False or trigger_forecasts.is_empty() is False:
        table_path = latex_dir / "tailrisk_claim_scope_table.tex"
        table_path.write_text(_claim_scope_to_latex(manifest=manifest), encoding="utf-8")
        tables += 1
        table_files.append(table_path.name)
    result_matrix_path = run_dir / "metrics" / "ml_tail_result_matrix.parquet"
    if result_matrix_path.exists():
        result_matrix = pl.read_parquet(result_matrix_path)
        tex = _result_matrix_to_latex(result_matrix, manifest=manifest)
        table_path = latex_dir / "ml_tail_result_matrix_table.tex"
        table_path.write_text(tex, encoding="utf-8")
        tables += 1
        table_files.append(table_path.name)
        dm_path = run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet"
        mcs_path = run_dir / "metrics" / "ml_tail_result_matrix_mcs.parquet"
        dm = pl.read_parquet(dm_path) if dm_path.exists() else None
        mcs = pl.read_parquet(mcs_path) if mcs_path.exists() else None
        table_path = latex_dir / "ml_tail_result_matrix_summary_table.tex"
        table_path.write_text(
            _result_matrix_summary_to_latex(
                result_matrix,
                dm=dm,
                mcs=mcs,
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    dst_path = run_dir / "metrics" / "ml_tail_dst_attenuation.parquet"
    if dst_path.exists():
        dst_attenuation = pl.read_parquet(dst_path)
        table_path = latex_dir / "ml_tail_dst_attenuation_table.tex"
        table_path.write_text(
            _dst_attenuation_to_latex(dst_attenuation, manifest=manifest),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    figure_result = export_figures(run_dir=run_dir, manifest=manifest)
    table_entries = _table_manifest_entries(table_files)
    _write_json(
        run_dir / "latex" / "table_manifest.json",
        {
            "claims_level": CLAIMS_LEVEL,
            "claim_level": manifest.get("claim_level", CLAIMS_LEVEL),
            "run_id": run_dir.name,
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "tables": table_entries,
            "table_count": len(table_entries),
        },
    )
    _write_json(
        run_dir / "latex" / "figure_manifest.json",
        {
            "claims_level": CLAIMS_LEVEL,
            "claim_level": manifest.get("claim_level", CLAIMS_LEVEL),
            "run_id": run_dir.name,
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "tables": tables,
            "table_files": table_files,
            "figures": figure_result.figure_entries,
        },
    )
    _update_manifest(
        run_dir,
        {
            "latex_tables": tables,
            "latex_figures": len(figure_result.figure_entries),
        },
    )
    return TableExportResult(run_id=run_dir.name, latex_dir=latex_dir, tables=tables)


def _remove_stale_tail_table_names(latex_dir: Path) -> None:
    for pattern in ("*_left_headline_table.tex", "*_right_robustness_table.tex"):
        for path in latex_dir.glob(pattern):
            path.unlink(missing_ok=True)


def _table_manifest_entries(table_files: list[str]) -> list[dict[str, object]]:
    return [_table_manifest_entry(table_file) for table_file in table_files]


def _table_manifest_entry(table_file: str) -> dict[str, object]:
    specs: dict[str, tuple[str, list[str], str, str | None]] = {
        "benchmark_metrics_table.tex": (
            "benchmark_metrics",
            ["metrics/benchmark_metrics.parquet"],
            "benchmark_common_sample_metric_table",
            None,
        ),
        "benchmark_left_tail_risk_table.tex": (
            "benchmark_left_tail_risk",
            ["metrics/benchmark_metrics.parquet"],
            "left_tail_benchmark_risk_table",
            TAIL_SIDE_LEFT,
        ),
        "benchmark_right_tail_risk_table.tex": (
            "benchmark_right_tail_risk",
            ["metrics/benchmark_metrics.parquet"],
            "right_tail_benchmark_risk_table",
            TAIL_SIDE_RIGHT,
        ),
        "ml_tail_metrics_table.tex": (
            "ml_tail_metrics",
            ["metrics/ml_tail_metrics.parquet"],
            "ml_tail_nested_information_set_table",
            None,
        ),
        "ml_tail_left_tail_risk_table.tex": (
            "ml_tail_left_tail_risk",
            ["metrics/ml_tail_metrics.parquet"],
            "left_tail_ml_tail_headline_risk_table",
            TAIL_SIDE_LEFT,
        ),
        "ml_tail_right_tail_risk_table.tex": (
            "ml_tail_right_tail_risk",
            ["metrics/ml_tail_metrics.parquet"],
            "right_tail_ml_tail_headline_risk_table",
            TAIL_SIDE_RIGHT,
        ),
        "tailrisk_es_severity_table.tex": (
            "tailrisk_es_severity",
            [
                "metrics/benchmark_metrics.parquet",
                "metrics/ml_tail_metrics.parquet",
                "metrics/ml_tail_metrics_per_model.parquet",
            ],
            "es_severity_diagnostic_table",
            None,
        ),
        "tailrisk_selected_model_performance_table.tex": (
            "tailrisk_selected_model_performance",
            [
                "metrics/benchmark_metrics_per_model.parquet",
                "metrics/ml_tail_metrics_per_model.parquet",
            ],
            "selected_benchmark_vs_lgbm_main_figure_rows",
            None,
        ),
        "appendix_benchmark_all_models_table.tex": (
            "appendix_benchmark_all_models",
            ["metrics/benchmark_metrics_per_model.parquet"],
            "appendix_full_benchmark_results",
            None,
        ),
        "appendix_lgbm_all_models_table.tex": (
            "appendix_lgbm_all_models",
            ["metrics/ml_tail_metrics_per_model.parquet"],
            "appendix_full_lgbm_results",
            None,
        ),
        "tailrisk_hedge_trigger_diagnostics_table.tex": (
            "tailrisk_trigger_diagnostics",
            ["forecasts/benchmark_forecasts.parquet", "forecasts/ml_tail_forecasts.parquet"],
            "trigger_diagnostic_table",
            None,
        ),
        "tailrisk_claim_scope_table.tex": (
            "tailrisk_claim_scope",
            ["manifest.json", "config/research_config.json"],
            "claim_boundary_reference_table",
            None,
        ),
        "ml_tail_result_matrix_table.tex": (
            "ml_tail_result_matrix",
            ["metrics/ml_tail_result_matrix.parquet"],
            "restricted_model_comparison_table",
            None,
        ),
        "ml_tail_result_matrix_summary_table.tex": (
            "ml_tail_result_matrix_summary",
            [
                "metrics/ml_tail_result_matrix.parquet",
                "metrics/ml_tail_result_matrix_dm.parquet",
                "metrics/ml_tail_result_matrix_mcs.parquet",
            ],
            "restricted_result_matrix_summary_table",
            None,
        ),
        "ml_tail_dst_attenuation_table.tex": (
            "ml_tail_dst_attenuation",
            ["metrics/ml_tail_dst_attenuation.parquet"],
            "descriptive_dst_attenuation_table",
            None,
        ),
    }
    name, sources, claim_scope, tail_side = specs.get(
        table_file,
        (
            Path(table_file).stem,
            [],
            "table_artifact_unclassified",
            None,
        ),
    )
    return {
        "name": name,
        "path": f"latex/tables/{table_file}",
        "format": "tex",
        "source_artifacts": sources,
        "tail_side": tail_side,
        "caption": _table_caption(name),
        "claim_scope": claim_scope,
    }


def _table_caption(name: str) -> str:
    captions = {
        "benchmark_metrics": (
            "Benchmark common-sample metric table for target-history and econometric floors."
        ),
        "benchmark_left_tail_risk": "Benchmark downside-risk metric table.",
        "benchmark_right_tail_risk": "Benchmark upside-risk metric table.",
        "ml_tail_metrics": "ML-tail headline nested-information-set table.",
        "ml_tail_left_tail_risk": "ML-tail downside-risk headline table.",
        "ml_tail_right_tail_risk": "ML-tail upside-risk headline table.",
        "tailrisk_es_severity": "Conditional-on-exception severity diagnostic table.",
        "tailrisk_selected_model_performance": (
            "Selected Benchmark-vs-LGBM rows used for compact main performance figures."
        ),
        "appendix_benchmark_all_models": "Appendix table with all benchmark model results.",
        "appendix_lgbm_all_models": "Appendix table with all LightGBM model results.",
        "tailrisk_trigger_diagnostics": "Pre-open risk-trigger diagnostic table.",
        "tailrisk_claim_scope": "Claim-boundary reference table for manuscript review.",
        "ml_tail_result_matrix": "Restricted common-sample model-family comparison table.",
        "ml_tail_result_matrix_summary": (
            "Restricted result-matrix inference and gate summary table."
        ),
        "ml_tail_dst_attenuation": "Descriptive DST timing-regime diagnostic table.",
    }
    return captions.get(name, "Generated LaTeX table artifact.")


def _combined_severity_metrics(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "metrics" / "benchmark_metrics.parquet"
    if benchmark_path.exists():
        frames.append(
            pl.read_parquet(benchmark_path).with_columns(
                pl.lit("benchmark").alias("suite"),
                pl.lit("headline").alias("claim_scope"),
            )
        )
    ml_headline_path = run_dir / "metrics" / "ml_tail_metrics.parquet"
    if ml_headline_path.exists():
        frames.append(
            pl.read_parquet(ml_headline_path).with_columns(
                pl.lit("ml_tail").alias("suite"),
                pl.lit("headline").alias("claim_scope"),
            )
        )
    ml_per_model_path = run_dir / "metrics" / "ml_tail_metrics_per_model.parquet"
    if ml_per_model_path.exists():
        per_model = pl.read_parquet(ml_per_model_path)
        if "model_name" in per_model.columns:
            per_model = per_model.filter(pl.col("model_name") != ML_TAIL_DIRECT_QUANTILE_MODEL)
        frames.append(
            per_model.with_columns(
                pl.lit("ml_tail_per_model").alias("suite"),
                pl.lit("restricted_diagnostic").alias("claim_scope"),
            )
        )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _combined_forecasts(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "forecasts" / "benchmark_forecasts.parquet"
    if benchmark_path.exists():
        frames.append(
            pl.read_parquet(benchmark_path).with_columns(pl.lit("benchmark").alias("suite"))
        )
    ml_tail_path = run_dir / "forecasts" / "ml_tail_forecasts.parquet"
    if ml_tail_path.exists():
        frames.append(pl.read_parquet(ml_tail_path).with_columns(pl.lit("ml_tail").alias("suite")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")
