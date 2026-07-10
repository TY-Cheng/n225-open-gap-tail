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
from n225_open_gap_tail.metrics.admissibility import coverage_admissibility_summary_rows
from n225_open_gap_tail.metrics.cross_suite_dm import cross_suite_dm_records_from_run
from n225_open_gap_tail.reporting.figures import export_figures
from n225_open_gap_tail.reporting.latex import (
    _claim_scope_to_latex,
    _configuration_sensitivity_to_latex,
    _coverage_admissibility_to_latex,
    _cross_suite_dm_to_latex,
    _es_severity_to_latex,
    _full_per_model_metrics_to_latex,
    _model_inventory_to_latex,
    _metrics_to_latex,
    _predictor_block_coverage_to_latex,
    _result_matrix_summary_to_latex,
    _result_matrix_to_latex,
)


def export_tables(*, run_dir: Path) -> TableExportResult:
    from n225_open_gap_tail.forecasting.artifacts import (
        _read_manifest,
        _update_manifest,
        _write_json,
    )

    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_tail_table_names(latex_dir)
    tables = 0
    table_files: list[str] = []
    manifest = _read_manifest(run_dir)
    feature_coverage_path = run_dir / "panel" / "feature_coverage.parquet"
    if feature_coverage_path.exists():
        table_path = latex_dir / "tailrisk_predictor_block_coverage_table.tex"
        table_path.write_text(
            _predictor_block_coverage_to_latex(
                pl.read_parquet(feature_coverage_path),
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    for suite in ("benchmark", "ml_tail"):
        metrics_path = run_dir / "metrics" / f"{suite}_metrics.parquet"
        if not metrics_path.exists():
            continue
        metrics = _paper_metric_rows(pl.read_parquet(metrics_path))
        if metrics.is_empty():
            continue
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
    if not benchmark_per_model.is_empty() or not ml_tail_per_model.is_empty():
        table_path = latex_dir / "tailrisk_model_inventory_table.tex"
        table_path.write_text(_model_inventory_to_latex(manifest=manifest), encoding="utf-8")
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
        table_path = latex_dir / "tailrisk_lgbm_24check_table.tex"
        table_path.write_text(
            _coverage_admissibility_to_latex(
                coverage_admissibility_summary_rows(ml_tail_per_model),
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
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
    if severity_metrics.is_empty() is False:
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
        dm = pl.read_parquet(dm_path) if dm_path.exists() else None
        table_path = latex_dir / "ml_tail_result_matrix_summary_table.tex"
        table_path.write_text(
            _result_matrix_summary_to_latex(
                result_matrix,
                dm=dm,
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    cross_suite_dm = cross_suite_dm_records_from_run(run_dir)
    if cross_suite_dm:
        table_path = latex_dir / "tailrisk_cross_suite_fz_dm_table.tex"
        table_path.write_text(
            _cross_suite_dm_to_latex(cross_suite_dm, manifest=manifest),
            encoding="utf-8",
        )
        tables += 1
        table_files.append(table_path.name)
    sensitivity_files = _export_sensitivity_tables(run_dir=run_dir, manifest=manifest)
    tables += len(sensitivity_files)
    table_files.extend(sensitivity_files)
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


def export_sensitivity_tables(*, run_dir: Path) -> TableExportResult:  # pragma: no cover
    from n225_open_gap_tail.forecasting.artifacts import (
        _read_manifest,
        _write_json,
    )

    manifest = _read_manifest(run_dir)
    table_files = _export_sensitivity_tables(run_dir=run_dir, manifest=manifest)
    if not table_files:
        return TableExportResult(
            run_id=run_dir.name,
            latex_dir=run_dir / "sensitivity" / "latex" / "tables",
            tables=0,
        )
    manifest_path = run_dir / "latex" / "table_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_table_manifest(manifest_path)
    existing_table_rows = existing.get("tables", [])
    if not isinstance(existing_table_rows, list):
        existing_table_rows = []
    existing_tables = [
        row
        for row in existing_table_rows
        if isinstance(row, dict) and not str(row.get("path") or "").startswith("sensitivity/")
    ]
    table_entries = [*existing_tables, *_table_manifest_entries(table_files)]
    _write_json(
        manifest_path,
        {
            "claims_level": existing.get("claims_level", CLAIMS_LEVEL),
            "claim_level": existing.get("claim_level", manifest.get("claim_level", CLAIMS_LEVEL)),
            "run_id": run_dir.name,
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "tables": table_entries,
            "table_count": len(table_entries),
        },
    )
    return TableExportResult(
        run_id=run_dir.name,
        latex_dir=run_dir / "sensitivity" / "latex" / "tables",
        tables=len(table_files),
    )


def _remove_stale_tail_table_names(latex_dir: Path) -> None:
    for path in latex_dir.glob("*.tex"):
        path.unlink(missing_ok=True)


def _paper_metric_rows(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    if not {"sample_policy", "common_sample_status"}.issubset(frame.columns):
        return pl.DataFrame()
    filtered = frame
    filtered = filtered.filter(
        (pl.col("sample_policy") == "primary_common_sample")
        & (pl.col("common_sample_status") == "ok")
    )
    if "fit_status" in filtered.columns:
        filtered = filtered.filter(pl.col("fit_status") == "ok")
    if "is_valid_forecast" in filtered.columns:
        filtered = filtered.filter(pl.col("is_valid_forecast") == True)  # noqa: E712
    return filtered


def _read_existing_table_manifest(path: Path) -> dict[str, object]:  # pragma: no cover
    if not path.exists():
        return {"tables": []}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _table_manifest_entries(table_files: list[str]) -> list[dict[str, object]]:
    return [_table_manifest_entry(table_file) for table_file in table_files]


def _table_manifest_entry(table_file: str) -> dict[str, object]:
    specs: dict[str, tuple[str, list[str], str, str | None]] = {
        "tailrisk_predictor_block_coverage_table.tex": (
            "tailrisk_predictor_block_coverage",
            ["panel/feature_coverage.parquet"],
            "main_text_predictor_block_coverage_information_transparency",
            None,
        ),
        "tailrisk_model_inventory_table.tex": (
            "tailrisk_model_inventory",
            [
                "config/research_config.json",
                "metrics/benchmark_metrics_per_model.parquet",
                "metrics/ml_tail_metrics_per_model.parquet",
            ],
            "main_text_model_inventory_forecast_construction",
            None,
        ),
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
            "left_tail_ml_tail_primary_risk_table",
            TAIL_SIDE_LEFT,
        ),
        "ml_tail_right_tail_risk_table.tex": (
            "ml_tail_right_tail_risk",
            ["metrics/ml_tail_metrics.parquet"],
            "right_tail_ml_tail_primary_risk_table",
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
            ],
            "restricted_result_matrix_summary_table",
            None,
        ),
        "tailrisk_cross_suite_fz_dm_table.tex": (
            "tailrisk_cross_suite_fz_dm",
            [
                "forecasts/benchmark_forecasts.parquet",
                "forecasts/ml_tail_forecasts.parquet",
            ],
            "post_24check_cross_suite_fz_dm_table",
            None,
        ),
        "tailrisk_lgbm_24check_table.tex": (
            "tailrisk_lgbm_24check",
            ["metrics/ml_tail_metrics_per_model.parquet"],
            "coverage_admissibility_24check_table",
            None,
        ),
        "appendix_lgbm_configuration_sensitivity_table.tex": (
            "appendix_lgbm_configuration_sensitivity",
            ["sensitivity/metrics/lgbm_configuration_sensitivity_metrics.parquet"],
            "appendix_configuration_robustness_lgbm",
            None,
        ),
        "appendix_evt_threshold_sensitivity_table.tex": (
            "appendix_evt_threshold_sensitivity",
            ["sensitivity/metrics/evt_threshold_sensitivity_metrics.parquet"],
            "appendix_configuration_robustness_evt_threshold",
            None,
        ),
    }
    key = Path(table_file).name if table_file.startswith("sensitivity/") else table_file
    name, sources, claim_scope, tail_side = specs.get(
        key,
        (
            Path(key).stem,
            [],
            "table_artifact_unclassified",
            None,
        ),
    )
    return {
        "name": name,
        "path": table_file
        if table_file.startswith("sensitivity/")
        else f"latex/tables/{table_file}",
        "format": "tex",
        "source_artifacts": sources,
        "tail_side": tail_side,
        "caption": _table_caption(name),
        "claim_scope": claim_scope,
    }


def _table_caption(name: str) -> str:
    captions = {
        "tailrisk_predictor_block_coverage": (
            "Predictor-block feature count, examples, and coverage summary."
        ),
        "tailrisk_model_inventory": "Model-family inventory and VaR/ES construction table.",
        "benchmark_metrics": "Baseline benchmark common-sample metric table.",
        "benchmark_left_tail_risk": "Benchmark downside-risk metric table.",
        "benchmark_right_tail_risk": "Benchmark upside-risk metric table.",
        "ml_tail_metrics": "Primary ML nested-information-set table.",
        "ml_tail_left_tail_risk": "Primary ML downside-risk table.",
        "ml_tail_right_tail_risk": "Primary ML upside-risk table.",
        "tailrisk_es_severity": "Conditional-on-exception severity diagnostic table.",
        "appendix_benchmark_all_models": "Appendix table with all benchmark model results.",
        "appendix_lgbm_all_models": "Appendix table with all LightGBM model results.",
        "tailrisk_claim_scope": "Claim-boundary reference table for manuscript review.",
        "ml_tail_result_matrix": "Restricted common-sample model-family comparison table.",
        "ml_tail_result_matrix_summary": (
            "Restricted result-matrix inference and gate summary table."
        ),
        "tailrisk_cross_suite_fz_dm": (
            "Post-24-check cross-suite FZ DM comparisons on strict common samples."
        ),
        "tailrisk_lgbm_24check": ("Full LightGBM 24-check coverage-admissibility screen."),
        "appendix_lgbm_configuration_sensitivity": (
            "Appendix post-24-check LightGBM configuration sensitivity table."
        ),
        "appendix_evt_threshold_sensitivity": (
            "Appendix post-24-check POT threshold sensitivity table."
        ),
    }
    return captions.get(name, "Generated LaTeX table artifact.")


def _export_sensitivity_tables(
    *,
    run_dir: Path,
    manifest: dict[str, object],
) -> list[str]:  # pragma: no cover
    sensitivity_specs = (
        (
            "lgbm_configuration_sensitivity_metrics.parquet",
            "appendix_lgbm_configuration_sensitivity_table.tex",
            "appendix_configuration_robustness_lgbm",
        ),
        (
            "evt_threshold_sensitivity_metrics.parquet",
            "appendix_evt_threshold_sensitivity_table.tex",
            "appendix_configuration_robustness_evt_threshold",
        ),
    )
    metrics_root = run_dir / "sensitivity" / "metrics"
    latex_dir = run_dir / "sensitivity" / "latex" / "tables"
    table_files: list[str] = []
    for metrics_file, table_file, scope in sensitivity_specs:
        metrics_path = metrics_root / metrics_file
        if not metrics_path.exists():
            continue
        latex_dir.mkdir(parents=True, exist_ok=True)
        table_path = latex_dir / table_file
        table_path.write_text(
            _configuration_sensitivity_to_latex(
                pl.read_parquet(metrics_path),
                table_scope=scope,
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        table_files.append(f"sensitivity/latex/tables/{table_file}")
    return table_files


def _combined_severity_metrics(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "metrics" / "benchmark_metrics.parquet"
    if benchmark_path.exists():
        benchmark_metrics = _paper_metric_rows(pl.read_parquet(benchmark_path))
        if not benchmark_metrics.is_empty():
            frames.append(
                benchmark_metrics.with_columns(
                    pl.lit("benchmark").alias("suite"),
                    pl.lit("primary").alias("claim_scope"),
                )
            )
    ml_primary_path = run_dir / "metrics" / "ml_tail_metrics.parquet"
    if ml_primary_path.exists():
        ml_primary = _paper_metric_rows(pl.read_parquet(ml_primary_path))
        if not ml_primary.is_empty():
            frames.append(
                ml_primary.with_columns(
                    pl.lit("ml_tail").alias("suite"),
                    pl.lit("primary").alias("claim_scope"),
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
