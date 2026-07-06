# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    PRIMARY_TAIL_SIDE,
    TAIL_SIDE_LEFT,
    TAIL_SIDE_RIGHT,
    _optional_float,
)
from n225_open_gap_tail.metrics.stat_utils import _fmt
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
    display_source_block_label,
)
from n225_open_gap_tail.reporting.latex_utils import _latex_escape


SELECTED_MODEL_MAX_PER_GROUP = 3
SELECTED_MODEL_MIN_ROWS = 450
SELECTED_MODEL_COVERAGE_TOLERANCE = 0.025
PROMOTED_TAIL_MODEL_SPECS = (
    {
        "tail_side": TAIL_SIDE_LEFT,
        "model_name": ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
        "information_set": "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy",
        "promotion_role": "left promoted",
    },
    {
        "tail_side": TAIL_SIDE_RIGHT,
        "model_name": ML_TAIL_LOCATION_SCALE_MODEL,
        "information_set": "japan_only_plus_us_close_core_plus_japan_proxy",
        "promotion_role": "right promoted",
    },
)


def _promoted_tail_model_rows(
    ml_tail_metrics: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spec in PROMOTED_TAIL_MODEL_SPECS:
        metric = _promoted_metric_row(ml_tail_metrics, spec)
        if metric is None:
            rows.append({**spec, "promotion_status": "missing_metric_row"})
            continue
        breach = _optional_float(metric.get("var_breach_rate"))
        expected = _optional_float(metric.get("expected_breach_rate")) or 0.05
        coverage_error = abs(breach - expected) if breach is not None else None
        gate_pass = (
            int(_optional_float(metric.get("rows")) or 0) >= SELECTED_MODEL_MIN_ROWS
            and coverage_error is not None
            and coverage_error <= SELECTED_MODEL_COVERAGE_TOLERANCE
            and _optional_float(metric.get("mean_quantile_loss")) is not None
            and _optional_float(metric.get("mean_fz_loss")) is not None
        )
        rows.append(
            {
                **metric,
                **spec,
                "coverage_abs_error": coverage_error,
                "promotion_status": "pass" if gate_pass else "diagnostic_only",
                "dm_quantile": _promoted_dm_row(dm, spec, "var_quantile_loss"),
                "dm_fz": _promoted_dm_row(dm, spec, "var_es_fz_loss"),
            }
        )
    return rows


def _promoted_metric_row(
    metrics: pl.DataFrame, spec: Mapping[str, object]
) -> dict[str, object] | None:
    required = {"model_name", "information_set", "tail_side"}
    if metrics.is_empty() or not required.issubset(metrics.columns):
        return None
    frame = metrics.filter(
        (pl.col("model_name") == spec["model_name"])
        & (pl.col("information_set") == spec["information_set"])
        & (pl.col("tail_side") == spec["tail_side"])
    )
    if frame.is_empty():
        return None
    return dict(frame.row(0, named=True))


def _promoted_dm_row(
    dm: pl.DataFrame | None,
    spec: Mapping[str, object],
    loss_family: str,
) -> dict[str, object] | None:
    if dm is None or dm.is_empty():
        return None
    required = {
        "tail_side",
        "information_set",
        "candidate_entity",
        "baseline_entity",
        "loss_family",
    }
    if not required.issubset(dm.columns):
        return None
    frame = dm.filter(
        (pl.col("tail_side") == spec["tail_side"])
        & (pl.col("information_set") == spec["information_set"])
        & (pl.col("candidate_entity") == spec["model_name"])
        & (pl.col("baseline_entity") == ML_TAIL_DIRECT_QUANTILE_MODEL)
        & (pl.col("loss_family") == loss_family)
    )
    if frame.is_empty():
        return None
    return dict(frame.row(0, named=True))


def _selected_model_performance_rows(
    benchmark_metrics: pl.DataFrame,
    ml_tail_metrics: pl.DataFrame,
    *,
    max_per_group: int = SELECTED_MODEL_MAX_PER_GROUP,
) -> list[dict[str, object]]:
    """Select compact Benchmark-vs-LGBM rows for paper-facing figures/tables.

    Selection is deterministic: per tail side and broad group, retain models with
    enough rows and VaR coverage within the registered tolerance, then rank by
    FZ loss and quantile loss. Full per-model tables remain the appendix record.
    """

    candidates: list[dict[str, object]] = []
    candidates.extend(_selection_candidates(benchmark_metrics, suite_group="Benchmark"))
    candidates.extend(_selection_candidates(ml_tail_metrics, suite_group="LGBM"))
    selected: list[dict[str, object]] = []
    tail_sides = [TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT]
    observed_sides = {str(row.get("tail_side") or PRIMARY_TAIL_SIDE) for row in candidates}
    tail_sides.extend(sorted(side for side in observed_sides if side not in tail_sides))
    for tail_side in tail_sides:
        for suite_group in ("Benchmark", "LGBM"):
            group = [
                row
                for row in candidates
                if row.get("suite_group") == suite_group and row.get("tail_side") == tail_side
            ]
            eligible = [
                row
                for row in group
                if int(_optional_float(row.get("rows")) or 0) >= SELECTED_MODEL_MIN_ROWS
                and (coverage_error := _optional_float(row.get("coverage_abs_error"))) is not None
                and coverage_error <= SELECTED_MODEL_COVERAGE_TOLERANCE
                and _optional_float(row.get("mean_fz_loss")) is not None
                and _optional_float(row.get("mean_quantile_loss")) is not None
            ]
            ranked = sorted(
                eligible,
                key=lambda row: (
                    _optional_float(row.get("mean_fz_loss")),
                    _optional_float(row.get("mean_quantile_loss")),
                    _optional_float(row.get("coverage_abs_error")),
                    str(row.get("model_name") or ""),
                    str(row.get("information_set") or ""),
                ),
            )
            for rank, row in enumerate(ranked[:max_per_group], start=1):
                selected.append({**row, "selection_rank": rank})
    return selected


def _selection_candidates(metrics: pl.DataFrame, *, suite_group: str) -> list[dict[str, object]]:
    required = {
        "model_name",
        "tail_side",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "mean_quantile_loss",
        "mean_fz_loss",
    }
    if metrics.is_empty() or not required.issubset(metrics.columns):
        return []
    rows: list[dict[str, object]] = []
    for row in metrics.iter_rows(named=True):
        breach = _optional_float(row.get("var_breach_rate"))
        expected = _optional_float(row.get("expected_breach_rate")) or 0.05
        if breach is None:
            continue
        rows.append(
            {
                **row,
                "suite_group": suite_group,
                "coverage_abs_error": abs(breach - expected),
                "selection_rule": (
                    f"rows>={SELECTED_MODEL_MIN_ROWS}; "
                    f"abs(breach-expected)<={SELECTED_MODEL_COVERAGE_TOLERANCE}; "
                    "rank_by=fz_loss_then_quantile_loss"
                ),
            }
        )
    return rows


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
            "econometric floor",
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
        "Performance belongs in selected-performance and result-matrix tables."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _dm_summary_to_latex(
    dm: pl.DataFrame | None,
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("comparison", "side", "loss", "diff", "DM p", "status")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: headline_dm_paired_inference_summary",
        "\\begin{tabular}{lllrrl}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _dm_summary_rows(dm):
        lines.append(
            f"{_latex_escape(row.get('comparison'))} & "
            f"{_latex_escape(row.get('tail_side'))} & "
            f"{_latex_escape(row.get('loss_family'))} & "
            f"{_fmt(row.get('mean_loss_diff_candidate_minus_baseline'))} & "
            f"{_fmt(row.get('pvalue_one_sided'))} & "
            f"{_latex_escape(row.get('status'))} \\\\"
        )
    note = (
        "Visible notes: negative loss differences favor the candidate. Benchmark-vs-ML "
        "cross-suite inference is reported as unavailable unless a registered "
        "cross-suite DM artifact exists."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _dm_summary_rows(
    dm: pl.DataFrame | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        rows.append(
            _dm_summary_row(
                dm,
                comparison="JP only -> +US close",
                tail_side=tail_side,
                family="information_set_ladder",
                axis="information_set_increment",
                baseline="japan_only",
                candidate="japan_only_plus_us_close_core",
                information_set=None,
            )
        )
        spec = next(
            (item for item in PROMOTED_TAIL_MODEL_SPECS if item["tail_side"] == tail_side),
            None,
        )
        if spec is not None:
            rows.append(
                _dm_summary_row(
                    dm,
                    comparison="Direct quantile -> promoted ML-tail",
                    tail_side=tail_side,
                    family="tail_model_family",
                    axis="model_family",
                    baseline=ML_TAIL_DIRECT_QUANTILE_MODEL,
                    candidate=str(spec["model_name"]),
                    information_set=str(spec["information_set"]),
                )
            )
        rows.append(
            {
                "comparison": "Benchmark suite -> promoted ML-tail",
                "tail_side": tail_side,
                "loss_family": "var_es_fz_loss",
                "mean_loss_diff_candidate_minus_baseline": None,
                "pvalue_one_sided": None,
                "status": "unavailable_no_registered_cross_suite_dm",
            }
        )
    return rows


def _dm_summary_row(
    dm: pl.DataFrame | None,
    *,
    comparison: str,
    tail_side: str,
    family: str,
    axis: str,
    baseline: str,
    candidate: str,
    information_set: str | None,
) -> dict[str, object]:
    if dm is None or dm.is_empty():
        return {
            "comparison": comparison,
            "tail_side": tail_side,
            "loss_family": "var_es_fz_loss",
            "mean_loss_diff_candidate_minus_baseline": None,
            "pvalue_one_sided": None,
            "status": "missing_dm_artifact",
        }
    for loss_family in ("var_es_fz_loss", "var_quantile_loss"):
        selected = dm.filter(
            (pl.col("tail_side") == tail_side)
            & (pl.col("comparison_family") == family)
            & (pl.col("comparison_axis") == axis)
            & (pl.col("baseline_entity") == baseline)
            & (pl.col("candidate_entity") == candidate)
            & (pl.col("loss_family") == loss_family)
        )
        if information_set is not None and "information_set" in selected.columns:
            selected = selected.filter(pl.col("information_set") == information_set)
        if selected.is_empty():
            continue
        row = dict(selected.row(0, named=True))
        return {
            "comparison": comparison,
            "tail_side": tail_side,
            "loss_family": loss_family,
            "mean_loss_diff_candidate_minus_baseline": row.get(
                "mean_loss_diff_candidate_minus_baseline"
            ),
            "pvalue_one_sided": row.get("pvalue_one_sided"),
            "status": row.get("inference_status"),
        }
    return {
        "comparison": comparison,
        "tail_side": tail_side,
        "loss_family": "var_es_fz_loss",
        "mean_loss_diff_candidate_minus_baseline": None,
        "pvalue_one_sided": None,
        "status": "missing_registered_pair",
    }


def _selected_model_performance_to_latex(
    benchmark_metrics: pl.DataFrame,
    ml_tail_metrics: pl.DataFrame,
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("group", "rank", "model", "info", "side", "N", "breach", "q_loss", "fz_loss")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: selected_benchmark_vs_lgbm_main_figure_rows",
        "\\begin{tabular}{ll ll lrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _selected_model_performance_rows(benchmark_metrics, ml_tail_metrics):
        lines.append(
            f"{_latex_escape(row.get('suite_group'))} & "
            f"{int(_optional_float(row.get('selection_rank')) or 0)} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{_fmt(row.get('var_breach_rate'))} & "
            f"{_fmt(row.get('mean_quantile_loss'))} & "
            f"{_fmt(row.get('mean_fz_loss'))} \\\\"
        )
    note = (
        "Visible notes: selected rows use the deterministic main-figure rule: "
        f"N >= {SELECTED_MODEL_MIN_ROWS}, absolute VaR coverage error <= "
        f"{SELECTED_MODEL_COVERAGE_TOLERANCE:.3f}, then rank by FZ loss and "
        "quantile loss within each broad group and tail side. Full per-model "
        "results are exported separately for appendix use."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _promoted_tail_models_to_latex(
    ml_tail_metrics: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = (
        "role",
        "model",
        "info",
        "side",
        "N",
        "breach",
        "q_loss",
        "fz_loss",
        "DM q",
        "DM FZ",
    )
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: side_specific_ml_tail_promotion_gate",
        "\\begin{tabular}{lll lrrrrll}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _promoted_tail_model_rows(ml_tail_metrics, dm=dm):
        lines.append(
            f"{_latex_escape(row.get('promotion_role'))} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{_fmt(row.get('var_breach_rate'))} & "
            f"{_fmt(row.get('mean_quantile_loss'))} & "
            f"{_fmt(row.get('mean_fz_loss'))} & "
            f"{_latex_escape(_dm_cell(row.get('dm_quantile')))} & "
            f"{_latex_escape(_dm_cell(row.get('dm_fz')))} \\\\"
        )
    note = (
        "Visible notes: side-specific promotion rows must pass N and VaR-coverage "
        "gates and are read with restricted common-sample DM evidence versus "
        "the direct-quantile anchor. Negative DM loss differences favor the "
        "promoted candidate. This is not a universal model-family ranking."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{10}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _dm_cell(row: object) -> str:
    if not isinstance(row, dict):
        return "n/a"
    diff = _optional_float(row.get("mean_loss_diff_candidate_minus_baseline"))
    pvalue = _optional_float(row.get("pvalue_one_sided"))
    status = str(row.get("inference_status") or "n/a")
    reject = row.get("reject_10pct")
    reject_mark = "rej10" if reject is True else "no-rej"
    if diff is None or pvalue is None:
        return status
    return f"{diff:.3g}; p={pvalue:.3g}; {reject_mark}"
