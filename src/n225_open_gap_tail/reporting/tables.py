# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def export_tables(*, run_dir: Path) -> TableExportResult:
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    tables = 0
    manifest = _read_manifest(run_dir)
    for suite in ("benchmark", "ml_tail"):
        metrics_path = run_dir / "metrics" / f"{suite}_metrics.parquet"
        if not metrics_path.exists():
            continue
        metrics = pl.read_parquet(metrics_path)
        tex = _metrics_to_latex(metrics, manifest=manifest)
        (latex_dir / f"{suite}_metrics_table.tex").write_text(tex, encoding="utf-8")
        tables += 1
    result_matrix_path = run_dir / "metrics" / "ml_tail_result_matrix.parquet"
    if result_matrix_path.exists():
        result_matrix = pl.read_parquet(result_matrix_path)
        tex = _result_matrix_to_latex(result_matrix, manifest=manifest)
        (latex_dir / "ml_tail_result_matrix_table.tex").write_text(tex, encoding="utf-8")
        tables += 1
    _write_json(
        run_dir / "latex" / "figure_manifest.json",
        {
            "claims_level": CLAIMS_LEVEL,
            "claim_level": manifest.get("claim_level", CLAIMS_LEVEL),
            "run_id": run_dir.name,
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "tables": tables,
            "figures": [],
        },
    )
    _update_manifest(run_dir, {"latex_tables": tables})
    return TableExportResult(run_id=run_dir.name, latex_dir=latex_dir, tables=tables)
