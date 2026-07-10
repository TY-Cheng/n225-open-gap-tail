# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from n225_open_gap_tail.config.runtime import _optional_float
from n225_open_gap_tail.metrics.stat_utils import _fmt
from n225_open_gap_tail.config.model_labels import (
    display_source_block_label,
)
from n225_open_gap_tail.reporting.latex_utils import _latex_escape


def _predictor_block_coverage_to_latex(
    coverage: pl.DataFrame,
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("block", "source", "features", "examples", "mean miss", "max miss", "role")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: predictor_block_coverage_information_transparency",
        "\\begin{tabular}{llrllll}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _predictor_block_coverage_rows(coverage):
        lines.append(
            f"{_latex_escape(row.get('block'))} & "
            f"{_latex_escape(row.get('source_family'))} & "
            f"{int(_optional_float(row.get('features')) or 0)} & "
            f"{_latex_escape(row.get('examples'))} & "
            f"{_fmt(row.get('mean_missing'))} & "
            f"{_fmt(row.get('max_missing'))} & "
            f"{_latex_escape(row.get('role'))} \\\\"
        )
    note = (
        "Visible notes: predictor-block coverage is an information-transparency "
        "summary, not feature admissibility. Timestamp availability and "
        "feature-matrix gates are applied before each refit."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{7}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _predictor_block_coverage_rows(coverage: pl.DataFrame) -> list[dict[str, object]]:
    required = {"source_family", "source_block", "feature", "missingness_rate"}
    if coverage.is_empty() or not required.issubset(coverage.columns):
        return []
    rows: list[dict[str, object]] = []
    for key, group in coverage.group_by(["source_family", "source_block"], maintain_order=True):
        source_family, source_block = key if isinstance(key, tuple) else ("", key)
        examples = ", ".join(str(value) for value in group["feature"].head(3).to_list())
        rows.append(
            {
                "source_family": display_source_block_label(source_family),
                "block": display_source_block_label(source_block),
                "features": group.height,
                "examples": examples,
                "mean_missing": group.select(pl.col("missingness_rate").mean()).item(),
                "max_missing": group.select(pl.col("missingness_rate").max()).item(),
                "role": _source_block_role(str(source_block)),
            }
        )
    return sorted(rows, key=lambda row: (str(row["role"]), str(row["block"])))


def _source_block_role(source_block: str) -> str:
    if source_block in {"target_history", "target_history_only", "japan_history", "japan_only"}:
        return "Japan/history anchor"
    if source_block in {"us_core", "us_close_core", "fred_core"}:
        return "U.S. close core"
    if source_block == "us_late_session":
        return "U.S. late-session timing"
    if source_block == "japan_proxy":
        return "Japan proxy increment"
    if source_block == "asia_proxy":
        return "Asia proxy increment"
    if "option" in source_block or source_block == "options_risk":
        return "Options-risk diagnostic"
    if "fred" in source_block:
        return "Macro/credit enrichment"
    return "Supporting control"


def _model_inventory_to_latex(*, manifest: Mapping[str, object] | None = None) -> str:
    manifest = manifest or {}
    headers = ("family", "examples", "information", "VaR", "ES", "role")
    rows = [
        (
            "Historical",
            "historical quantile; rolling quantile",
            "target history",
            "empirical quantile",
            "empirical tail mean",
            "benchmark suite",
        ),
        (
            "GARCH/GJR",
            "GARCH-t; GJR-GARCH-t",
            "target history",
            "parametric t",
            "parametric t",
            "econometric benchmark",
        ),
        (
            "GARCH-EVT",
            "GJR-GARCH-EVT",
            "target history",
            "filtered POT-GPD",
            "GPD ES",
            "tail benchmark",
        ),
        (
            "Advanced econometric",
            "CAViaR; CARE; GAS",
            "target history",
            "recursive/score",
            "varies by family",
            "nonblocking benchmark",
        ),
        (
            "Direct LightGBM",
            "LGBM direct quantile",
            "nested information sets",
            "quantile regression",
            "empirical companion",
            "information ladder",
        ),
        (
            "LightGBM location-scale",
            "LGBM location-scale empirical",
            "nested information sets",
            "standardized empirical tail",
            "standardized empirical tail",
            "filtered candidate",
        ),
        (
            "LightGBM POT-GPD",
            "standardized, median/MAD, median/IQR POT-GPD",
            "nested information sets",
            "standardized POT-GPD",
            "GPD ES",
            "filtered EVT candidate",
        ),
    ]
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: model_inventory_forecast_construction",
        "\\begin{tabular}{llllll}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(_latex_escape(value) for value in row) + r" \\")
    note = (
        "Visible notes: inventory table explains forecast construction and paper role. "
        "Performance belongs in the coverage-admissibility, common-sample loss, and "
        "full-result tables."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)
