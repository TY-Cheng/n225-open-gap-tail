# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def export_tables(*, run_dir: Path) -> TableExportResult:
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
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
            "figures": [],
        },
    )
    _update_manifest(run_dir, {"latex_tables": tables})
    return TableExportResult(run_id=run_dir.name, latex_dir=latex_dir, tables=tables)


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
