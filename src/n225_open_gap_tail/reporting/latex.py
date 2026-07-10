# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from collections.abc import Sequence

from n225_open_gap_tail.config.runtime import (
    Mapping,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    pl,
    PRIMARY_TAIL_SIDE,
    _optional_float,
)
from n225_open_gap_tail.metrics.stat_utils import _fmt
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
    display_source_block_label,
)
from n225_open_gap_tail.reporting.latex_utils import (
    _inference_status_counts,
    _latex_escape,
    _range_label,
    _result_summary_key,
)


from n225_open_gap_tail.reporting.latex_headline import (
    _model_inventory_to_latex as _model_inventory_to_latex,
    _predictor_block_coverage_rows as _predictor_block_coverage_rows,
    _predictor_block_coverage_to_latex as _predictor_block_coverage_to_latex,
    _source_block_role as _source_block_role,
)


def _metrics_to_latex(
    metrics: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    has_information_set = "information_set" in metrics.columns
    headers = (
        ("model", "info", "side", "tail", "rows", "breach", "q_loss", "fz_loss")
        if has_information_set
        else ("model", "side", "tail", "rows", "breach", "q_loss", "fz_loss")
    )
    manifest = manifest or {}
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        f"% claim_level: {manifest.get('claim_level', manifest.get('claims_level', ''))}",
        (
            "% loss convention: realized_loss is positive loss for selected tail_side; "
            "lower FZ loss is better"
        ),
        "\\begin{tabular}{lllrrrrr}" if has_information_set else "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in metrics.iter_rows(named=True):
        info_cell = (
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            if has_information_set
            else ""
        )
        lines.append(
            f"{_latex_escape(display_model_label(row['model_name']))} & "
            f"{info_cell}"
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{float(row['tail_level']):.3f} & "
            f"{int(row['rows'])} & {_fmt(row['var_breach_rate'])} & "
            f"{_fmt(row['mean_quantile_loss'])} & {_fmt(row['mean_fz_loss'])} \\\\"
        )
    note = (
        "Visible notes: candidate artifact; lower FZ loss is better; "
        "inference artifacts use block-bootstrap DM; "
        "common-sample status is recorded in metrics metadata."
    )
    lines.extend(
        [
            "\\midrule",
            f"\\multicolumn{{{len(headers)}}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\",
        ]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _cross_suite_dm_to_latex(
    records: Sequence[Mapping[str, object]],
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    displayed_pairs = {
        ("LGBM plain MLE C", "GJR-GARCH-EVT"),
        ("LGBM UniBM C", "GJR-GARCH-EVT"),
        ("LGBM plain MLE C", "LGBM UniBM C"),
    }
    selected = [
        row
        for row in records
        if (str(row.get("candidate_label")), str(row.get("anchor_label"))) in displayed_pairs
    ]
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: post_24check_cross_suite_fz_dm_table",
        "\\begin{tabular}{llllrrl}",
        "\\toprule",
        "tail & candidate & anchor & common N & mean FZ diff. & one-sided p & status \\\\",
        "\\midrule",
    ]
    for row in selected:
        pvalue = _optional_float(row.get("pvalue_one_sided"))
        pvalue_text = "n/a" if pvalue is None else f"{pvalue:.3f}{_dm_significance_stars(pvalue)}"
        lines.append(
            f"{_latex_escape(str(row.get('tail_side') or '').replace('_', ' '))} & "
            f"{_latex_escape(row.get('candidate_label'))} & "
            f"{_latex_escape(row.get('anchor_label'))} & "
            f"{int(_optional_float(row.get('common_n')) or 0)} & "
            f"{_fmt(row.get('mean_fz_loss_diff_candidate_minus_anchor'))} & "
            f"{_latex_escape(pvalue_text)} & "
            f"{_latex_escape(row.get('inference_status'))} \\\\"
        )
    note = (
        "Mean differences are FZ(candidate - anchor) on one strict global common sample "
        "per tail. Negative values favor the candidate because lower Fissler-Ziegel joint "
        "VaR-ES loss is better. P-values are one-sided moving-block-bootstrap DM p-values."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{7}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _coverage_admissibility_to_latex(
    rows: Sequence[Mapping[str, object]],
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: coverage_admissibility_24check_table",
        "\\begin{tabular}{lrrrrl}",
        "\\toprule",
        (
            "LGBM family & eligible/8 & breach/8 & Kupiec/8 & "
            "Christoffersen independence/8 & admissible \\\\"
        ),
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{int(_optional_float(row.get('eligible_scenarios')) or 0)}/8 & "
            f"{int(_optional_float(row.get('breach_passes')) or 0)}/8 & "
            f"{int(_optional_float(row.get('kupiec_passes')) or 0)}/8 & "
            f"{int(_optional_float(row.get('christoffersen_independence_passes')) or 0)}/8 & "
            f"{'yes' if row.get('coverage_admissible') else 'no'} \\\\"
        )
    note = (
        "The 24-check screen is two tail sides times four information sets times "
        "the breach-rate band, Kupiec unconditional coverage, and Christoffersen "
        "independence. N >= 450 is an eligibility precondition."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _dm_significance_stars(pvalue: float) -> str:
    if pvalue < 0.01:
        return "***"
    if pvalue < 0.05:
        return "**"
    if pvalue < 0.10:
        return "*"
    return ""


def _full_per_model_metrics_to_latex(
    metrics: pl.DataFrame,
    *,
    suite_group: str,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("group", "model", "info", "side", "N", "breach", "q_loss", "fz_loss", "severity")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: full_per_model_appendix",
        "\\begin{tabular}{lll lrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    sort_columns = [
        column
        for column in ("tail_side", "model_name", "information_set", "tail_level")
        if column in metrics.columns
    ]
    frame = metrics.sort(sort_columns) if sort_columns else metrics
    for row in frame.iter_rows(named=True):
        lines.append(
            f"{_latex_escape(suite_group)} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{_fmt(row.get('var_breach_rate'))} & "
            f"{_fmt(row.get('mean_quantile_loss'))} & "
            f"{_fmt(row.get('mean_fz_loss'))} & "
            f"{_fmt(row.get('mean_exceedance_severity'))} \\\\"
        )
    note = (
        "Visible notes: appendix table; lower quantile/FZ loss and lower "
        "exceedance severity are better, while VaR breach should be read relative "
        "to the nominal 5% exception rate."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _configuration_sensitivity_to_latex(
    metrics: pl.DataFrame,
    *,
    table_scope: str,
    manifest: Mapping[str, object] | None = None,
) -> str:  # pragma: no cover
    manifest = manifest or {}
    headers = (
        "family",
        "config",
        "model",
        "info",
        "side",
        "N",
        "breach",
        "q_loss",
        "fz_loss",
        "class",
    )
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        f"% table_scope: {table_scope}",
        "% primary_claim_allowed: false",
        "\\begin{tabular}{lll l lrrrrl}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    sort_columns = [
        column
        for column in (
            "sensitivity_family",
            "config_label",
            "tail_side",
            "model_name",
            "information_set",
        )
        if column in metrics.columns
    ]
    frame = metrics.sort(sort_columns) if sort_columns else metrics
    for row in frame.iter_rows(named=True):
        class_label = row.get("robustness_classification") or row.get("sensitivity_status")
        lines.append(
            f"{_latex_escape(row.get('sensitivity_family'))} & "
            f"{_latex_escape(row.get('config_label'))} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{_fmt(row.get('var_breach_rate'))} & "
            f"{_fmt(row.get('mean_quantile_loss'))} & "
            f"{_fmt(row.get('mean_fz_loss'))} & "
            f"{_latex_escape(class_label)} \\\\"
        )
    note = (
        "Visible notes: appendix-only post-24-check configuration robustness diagnostics. "
        "Rows carry primary_claim_allowed=false and do not alter coverage admissibility, "
        "the canonical forecasts, or the cross-suite FZ DM heatmap. "
        "Lower quantile/FZ loss is better; breach should be read against the 5% "
        "nominal exception rate. Boundary EVT rows at u=0.95 are diagnostics at "
        "the 95% VaR level, not alternative forecasts."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{10}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _result_matrix_to_latex(
    matrix: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    manifest = manifest or {}
    headers = ("family", "axis", "loss", "info/model", "side", "tail", "N", "exc", "metric")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% claim_scope: restricted_model_comparison_not_primary unless stated otherwise",
        "\\begin{tabular}{lllllrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    sort_columns = [
        column
        for column in (
            "comparison_family",
            "comparison_axis",
            "loss_family",
            "tail_level",
            "information_set",
            "model_name",
        )
        if column in matrix.columns
    ]
    frame = matrix.sort(sort_columns) if sort_columns else matrix
    for row in frame.iter_rows(named=True):
        if row.get("metric_status") != "ok":
            continue
        if row.get("comparison_axis") == "information_set_increment" and row.get("information_set"):
            label = display_information_set_label(row.get("information_set"))
        else:
            label = display_model_label(row.get("model_name") or row.get("information_set") or "")
        lines.append(
            f"{_latex_escape(row.get('comparison_family'))} & "
            f"{_latex_escape(row.get('comparison_axis'))} & "
            f"{_latex_escape(row.get('loss_family'))} & "
            f"{_latex_escape(label)} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_fmt(row.get('tail_level'))} & "
            f"{int(_optional_float(row.get('common_n')) or 0)} & "
            f"{int(_optional_float(row.get('exception_count')) or 0)} & "
            f"{_fmt(row.get('metric_value'))} \\\\"
        )
    note = (
        "Visible notes: restricted result matrix; lower metric is better for "
        "quantile loss, FZ loss, and absolute coverage error; block-bootstrap DM "
        "appears only when registered sample and exception gates pass; "
        "these rows do not replace the primary ML table."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _es_severity_to_latex(
    metrics: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    manifest = manifest or {}
    headers = ("suite", "scope", "model", "side", "info", "N", "exc", "severity", "delta")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: exceedance_severity_diagnostic",
        "\\begin{tabular}{lllllrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _severity_rows(metrics):
        lines.append(
            f"{_latex_escape(row.get('suite'))} & "
            f"{_latex_escape(row.get('claim_scope'))} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{int(_optional_float(row.get('exceedance_count')) or 0)} & "
            f"{_fmt(row.get('mean_exceedance_severity'))} & "
            f"{_fmt(row.get('severity_delta_vs_anchor'))} \\\\"
        )
    note = (
        "Visible notes: severity is conditional on VaR exceptions; positive delta "
        "means lower mean exceedance severity than the same-model anchor information "
        "set. This is an ES severity diagnostic, not a model-win claim."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _result_matrix_summary_to_latex(
    matrix: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("family", "axis", "loss", "side", "sample", "N", "joint exc", "DM")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: result_matrix_sample_and_inference_gate_summary",
        "\\begin{tabular}{lllllrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _result_matrix_summary_rows(matrix, dm=dm):
        lines.append(
            f"{_latex_escape(row.get('comparison_family'))} & "
            f"{_latex_escape(row.get('comparison_axis'))} & "
            f"{_latex_escape(row.get('loss_family'))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_latex_escape(row.get('sample_policy'))} & "
            f"{_latex_escape(row.get('common_n_range'))} & "
            f"{_latex_escape(row.get('joint_exception_range'))} & "
            f"{int(_optional_float(row.get('dm_ok')) or 0)}/"
            f"{int(_optional_float(row.get('dm_total')) or 0)} \\\\"
        )
    note = (
        "Visible notes: VaR-only and VaR-ES loss families are separated. "
        "Restricted samples are not primary evidence. DM counts show how many "
        "registered inference records passed their sample and exception gates."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{8}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _claim_scope_to_latex(*, manifest: Mapping[str, object] | None = None) -> str:
    manifest = manifest or {}
    rows = [
        (
            "benchmark_metrics.parquet",
            "baseline benchmarks",
            "yes after clean-run author review",
        ),
        (
            "ml_tail_metrics.parquet",
            "primary ML nested information sets",
            "yes; direct quantile is the information-set comparator, not the coverage gate",
        ),
        (
            "ml_tail_metrics_per_model.parquet",
            "per-model OOS diagnostics",
            "24-check inputs only; raw rows are not a cross-model comparison",
        ),
        (
            "ml_tail_result_matrix*.parquet",
            "restricted model-family and increment comparisons",
            "no; restricted sample evidence only",
        ),
        (
            "canonical forecasts + 24-check table",
            "coverage-admissible cross-suite FZ DM",
            "yes; conditional on the screen and strict common dates",
        ),
    ]
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: claim_governance_map",
        "\\begin{tabular}{lll}",
        "\\toprule",
        "artifact & role & allowed claim \\\\",
        "\\midrule",
    ]
    for artifact, role, claim in rows:
        lines.append(
            f"{_latex_escape(artifact)} & {_latex_escape(role)} & {_latex_escape(claim)} \\\\"
        )
    note = (
        "Visible notes: this map governs table placement. Restricted and diagnostic "
        "artifacts may support discussion, but they do not replace primary common-sample "
        "evidence."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{3}}{{l}}{{\\footnotesize {_latex_escape(note)}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _severity_rows(metrics: pl.DataFrame) -> list[dict[str, object]]:
    required = {"model_name", "information_set", "tail_level", "mean_exceedance_severity"}
    if metrics.is_empty() or not required.issubset(metrics.columns):
        return []
    sort_columns = [
        column
        for column in ("suite", "model_name", "tail_side", "tail_level", "information_set")
        if column in metrics.columns
    ]
    frame = metrics.sort(sort_columns) if sort_columns else metrics
    rows = frame.iter_rows(named=True)
    anchors: dict[tuple[str, str, float], float] = {}
    staged = []
    for row in rows:
        severity = _optional_float(row.get("mean_exceedance_severity"))
        if severity is None:
            continue
        suite = str(row.get("suite") or "unknown")
        model_name = str(row.get("model_name") or "")
        tail_level = float(_optional_float(row.get("tail_level")) or 0.0)
        tail_side = str(row.get("tail_side") or PRIMARY_TAIL_SIDE)
        key = (suite, model_name, tail_side, tail_level)
        if key not in anchors:
            anchors[key] = severity
        claim_scope = str(row.get("claim_scope") or "")
        staged.append(
            {
                **row,
                "tail_side": tail_side,
                "suite": suite,
                "claim_scope": claim_scope or _severity_claim_scope(row),
                "severity_delta_vs_anchor": anchors[key] - severity,
            }
        )
    return staged


def _severity_claim_scope(row: Mapping[str, object]) -> str:
    sample_policy = str(row.get("sample_policy") or "")
    model_name = str(row.get("model_name") or "")
    suite = str(row.get("suite") or "")
    if suite == "ml_tail_per_model" and model_name != ML_TAIL_DIRECT_QUANTILE_MODEL:
        return "restricted_diagnostic"
    if sample_policy == "primary_common_sample":
        return "primary"
    return "diagnostic"


def _result_matrix_summary_rows(
    matrix: pl.DataFrame,
    *,
    dm: pl.DataFrame | None,
) -> list[dict[str, object]]:
    required = {"comparison_family", "comparison_axis", "sample_policy", "loss_family"}
    if matrix.is_empty() or not required.issubset(matrix.columns):
        return []
    rows = []
    frame = matrix
    if "tail_side" not in frame.columns:
        frame = frame.with_columns(pl.lit(PRIMARY_TAIL_SIDE).alias("tail_side"))
    for column in ("common_n", "joint_exception_count"):
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).alias(column))
    grouped = (
        frame.group_by(
            [
                "comparison_family",
                "comparison_axis",
                "sample_policy",
                "loss_family",
                "tail_side",
            ]
        )
        .agg(
            pl.min("common_n").alias("min_common_n"),
            pl.max("common_n").alias("max_common_n"),
            pl.min("joint_exception_count").alias("min_joint_exception_count"),
            pl.max("joint_exception_count").alias("max_joint_exception_count"),
            pl.len().alias("matrix_rows"),
        )
        .sort(["comparison_family", "comparison_axis", "loss_family"])
    )
    dm_counts = _inference_status_counts(dm, "inference_status", "ok_block_bootstrap_dm")
    for row in grouped.iter_rows(named=True):
        key = _result_summary_key(row)
        rows.append(
            {
                **row,
                "common_n_range": _range_label(row["min_common_n"], row["max_common_n"]),
                "joint_exception_range": _range_label(
                    row["min_joint_exception_count"],
                    row["max_joint_exception_count"],
                ),
                "dm_ok": dm_counts.get(key, {}).get("ok", 0),
                "dm_total": dm_counts.get(key, {}).get("total", 0),
            }
        )
    return rows
