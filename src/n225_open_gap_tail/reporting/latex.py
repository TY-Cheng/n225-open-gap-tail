# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Mapping,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    pl,
    PRIMARY_TAIL_SIDE,
    TAIL_SIDE_LEFT,
    TAIL_SIDE_RIGHT,
    _optional_float,
)
from n225_open_gap_tail.metrics.stat_utils import _fmt
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
)
from n225_open_gap_tail.reporting.latex_utils import (
    _inference_status_counts,
    _latex_escape,
    _range_label,
    _result_summary_key,
)


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
    mcs: pl.DataFrame | None = None,
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
                "mcs_quantile": _promoted_mcs_row(mcs, spec, "var_quantile_loss"),
                "mcs_fz": _promoted_mcs_row(mcs, spec, "var_es_fz_loss"),
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


def _promoted_mcs_row(
    mcs: pl.DataFrame | None,
    spec: Mapping[str, object],
    loss_family: str,
) -> dict[str, object] | None:
    if mcs is None or mcs.is_empty():
        return None
    required = {"tail_side", "information_set", "model_name", "loss_family"}
    if not required.issubset(mcs.columns):
        return None
    frame = mcs.filter(
        (pl.col("tail_side") == spec["tail_side"])
        & (pl.col("information_set") == spec["information_set"])
        & (pl.col("model_name") == spec["model_name"])
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
        "inference artifacts use block-bootstrap DM and HLN Tmax MCS; "
        "common-sample status is recorded in metrics metadata."
    )
    lines.extend(
        ["\\midrule", f"\\multicolumn{{{len(headers)}}}{{l}}{{\\footnotesize {note}}} \\\\"]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


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
    lines.extend(["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _promoted_tail_models_to_latex(
    ml_tail_metrics: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
    mcs: pl.DataFrame | None = None,
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
        "MCS q/FZ",
    )
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: side_specific_ml_tail_promotion_gate",
        "\\begin{tabular}{lll lrrrrlll}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _promoted_tail_model_rows(ml_tail_metrics, dm=dm, mcs=mcs):
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
            f"{_latex_escape(_dm_cell(row.get('dm_fz')))} & "
            f"{_latex_escape(_mcs_pair_cell(row.get('mcs_quantile'), row.get('mcs_fz')))} \\\\"
        )
    note = (
        "Visible notes: side-specific promotion rows must pass N and VaR-coverage "
        "gates and are read with restricted common-sample DM/MCS evidence versus "
        "the direct-quantile anchor. Negative DM loss differences favor the "
        "promoted candidate. This is not a universal model-family ranking."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{11}}{{l}}{{\\footnotesize {note}}} \\\\"])
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


def _mcs_pair_cell(q_row: object, fz_row: object) -> str:
    return f"{_mcs_cell(q_row)}/{_mcs_cell(fz_row)}"


def _mcs_cell(row: object) -> str:
    if not isinstance(row, dict):
        return "n/a"
    status = str(row.get("mcs_status") or "n/a")
    included = row.get("included_in_mcs")
    if included is True:
        return "in"
    if included is False and status == "ok":
        return "out"
    return status


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
    lines.extend(["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
        "Visible notes: appendix-only configuration robustness diagnostics. "
        "Rows carry primary_claim_allowed=false and are not used to select "
        "primary selections, promoted rows, DM/MCS gates, or selected-model figures. "
        "Lower quantile/FZ loss is better; breach should be read against the 5% "
        "nominal exception rate. Boundary EVT rows at u=0.95 are diagnostics at "
        "the 95% VaR level, not alternative forecasts."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{10}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
        "\\begin{tabular}{lllllrrrr}",
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
        "and HLN Tmax MCS appear only when registered sample and exception gates pass; "
        "these rows do not replace the primary ML table."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
    lines.extend(["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _hedge_trigger_to_latex(
    forecasts: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    manifest = manifest or {}
    headers = ("suite", "model", "info", "side", "tail", "N", "trig", "false", "miss", "sev")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: diagnostic_var_trigger_not_hedge_pnl",
        "\\begin{tabular}{lllllrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in _hedge_trigger_rows(forecasts):
        lines.append(
            f"{_latex_escape(row.get('suite'))} & "
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_latex_escape(display_information_set_label(row.get('information_set')))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_fmt(row.get('tail_level'))} & "
            f"{int(_optional_float(row.get('rows')) or 0)} & "
            f"{int(_optional_float(row.get('trigger_count')) or 0)} & "
            f"{int(_optional_float(row.get('false_alarm_count')) or 0)} & "
            f"{int(_optional_float(row.get('missed_exception_count')) or 0)} & "
            f"{_fmt(row.get('mean_triggered_exception_severity'))} \\\\"
        )
    note = (
        "Visible notes: trigger is a within-model 75th-percentile VaR diagnostic "
        "computed on the evaluation sample. False alarms are triggers without a VaR "
        "exception; misses are exceptions without a trigger. This is not hedge PnL, "
        "not turnover, and not a trading-alpha result."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{10}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _dst_attenuation_to_latex(
    attenuation: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    manifest = manifest or {}
    headers = ("model", "tail", "regime", "pairs", "q_gain", "fz_gain", "p", "alpha")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% table_scope: descriptive_dst_attenuation",
        "\\begin{tabular}{lllrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    frame = attenuation
    if {"model_name", "tail_level", "dst_regime"}.issubset(frame.columns):
        frame = frame.sort(["model_name", "tail_level", "dst_regime"])
    for row in frame.iter_rows(named=True):
        lines.append(
            f"{_latex_escape(display_model_label(row.get('model_name')))} & "
            f"{_fmt(row.get('tail_level'))} & "
            f"{_latex_escape(row.get('dst_regime'))} & "
            f"{int(_optional_float(row.get('paired_rows')) or 0)} & "
            f"{_fmt(row.get('mean_quantile_gain'))} & "
            f"{_fmt(row.get('mean_fz_gain'))} & "
            f"{_fmt(row.get('dm_pvalue_one_sided'))} & "
            f"{_fmt(row.get('alpha_absorb'))} \\\\"
        )
    note = (
        "Visible notes: DST attenuation rows compare forecast gains by timing regime. "
        "They are descriptive forecast evidence, not a structural causal mechanism; "
        "ratio rows are diagnostics when direct block-bootstrap DM is not defined."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{8}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _result_matrix_summary_to_latex(
    matrix: pl.DataFrame,
    *,
    dm: pl.DataFrame | None = None,
    mcs: pl.DataFrame | None = None,
    manifest: Mapping[str, object] | None = None,
) -> str:
    manifest = manifest or {}
    headers = ("family", "axis", "loss", "side", "sample", "N", "joint exc", "DM", "MCS")
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
    for row in _result_matrix_summary_rows(matrix, dm=dm, mcs=mcs):
        lines.append(
            f"{_latex_escape(row.get('comparison_family'))} & "
            f"{_latex_escape(row.get('comparison_axis'))} & "
            f"{_latex_escape(row.get('loss_family'))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_latex_escape(row.get('sample_policy'))} & "
            f"{_latex_escape(row.get('common_n_range'))} & "
            f"{_latex_escape(row.get('joint_exception_range'))} & "
            f"{int(_optional_float(row.get('dm_ok')) or 0)}/"
            f"{int(_optional_float(row.get('dm_total')) or 0)} & "
            f"{int(_optional_float(row.get('mcs_ok')) or 0)}/"
            f"{int(_optional_float(row.get('mcs_total')) or 0)} \\\\"
        )
    note = (
        "Visible notes: VaR-only and VaR-ES loss families are separated. "
        "Restricted samples are not primary evidence. DM/MCS counts show how many "
        "registered inference records passed their sample and exception gates."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{9}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
            "yes; current primary comparison is direct quantile",
        ),
        (
            "ml_tail_metrics_per_model.parquet",
            "per-model OOS diagnostics",
            "no; not a cross-model common-sample table",
        ),
        (
            "ml_tail_result_matrix*.parquet",
            "restricted model-family and increment comparisons",
            "no; restricted sample evidence only",
        ),
        (
            "ml_tail_dst_attenuation.parquet",
            "DST attenuation diagnostics",
            "no structural causal claim",
        ),
        (
            "*_cpa_inference.parquet",
            "conditional loss-difference diagnostics",
            "no forecasting-model or primary-superiority claim",
        ),
        (
            "hedge-trigger table",
            "VaR trigger diagnostic",
            "no hedge PnL or trading-alpha claim",
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
    lines.extend(["\\midrule", f"\\multicolumn{{3}}{{l}}{{\\footnotesize {note}}} \\\\"])
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


def _hedge_trigger_rows(forecasts: pl.DataFrame) -> list[dict[str, object]]:
    required = {
        "suite",
        "model_name",
        "information_set",
        "tail_level",
        "var_forecast",
        "realized_loss",
    }
    if forecasts.is_empty() or not required.issubset(forecasts.columns):
        return []
    rows: list[dict[str, object]] = []
    group_columns = [
        column
        for column in (
            "suite",
            "target_family",
            "tail_side",
            "model_name",
            "information_set",
            "tail_level",
            "refit_frequency",
        )
        if column in forecasts.columns
    ]
    frame = forecasts.filter(
        pl.col("var_forecast").is_not_null()
        & pl.col("realized_loss").is_not_null()
        & pl.col("is_valid_forecast").fill_null(True)
    )
    for key, group in frame.group_by(group_columns, maintain_order=True):
        if group.is_empty():  # pragma: no cover
            continue
        key_values = key if isinstance(key, tuple) else (key,)
        row_key = dict(zip(group_columns, key_values, strict=False))
        threshold = group.select(pl.col("var_forecast").quantile(0.75)).item()
        if threshold is None:  # pragma: no cover
            continue
        diagnostic = group.with_columns(
            (pl.col("var_forecast") >= float(threshold)).alias("_trigger"),
            (pl.col("realized_loss") > pl.col("var_forecast")).alias("_exception"),
            (pl.col("realized_loss") - pl.col("var_forecast")).alias("_severity"),
        )
        trigger_count = int(diagnostic.select(pl.col("_trigger").sum()).item() or 0)
        exception_count = int(diagnostic.select(pl.col("_exception").sum()).item() or 0)
        false_alarm_count = int(
            diagnostic.filter(pl.col("_trigger") & ~pl.col("_exception")).height
        )
        missed_exception_count = int(
            diagnostic.filter(~pl.col("_trigger") & pl.col("_exception")).height
        )
        triggered_exceptions = diagnostic.filter(pl.col("_trigger") & pl.col("_exception"))
        rows.append(
            {
                **row_key,
                "rows": diagnostic.height,
                "trigger_threshold_quantile": 0.75,
                "trigger_threshold_var": float(threshold),
                "trigger_count": trigger_count,
                "trigger_rate": trigger_count / diagnostic.height if diagnostic.height else None,
                "exception_count": exception_count,
                "false_alarm_count": false_alarm_count,
                "false_alarm_rate": false_alarm_count / trigger_count if trigger_count else None,
                "missed_exception_count": missed_exception_count,
                "missed_exception_rate": missed_exception_count / exception_count
                if exception_count
                else None,
                "mean_triggered_exception_severity": _group_mean(triggered_exceptions, "_severity"),
                "trigger_rule": "within_model_var_forecast_q75_diagnostic",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("suite")),
            str(row.get("model_name")),
            str(row.get("information_set")),
            float(_optional_float(row.get("tail_level")) or 0.0),
        ),
    )


def _group_mean(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    value = frame.select(pl.col(column).mean()).item()
    return _optional_float(value)


def _result_matrix_summary_rows(
    matrix: pl.DataFrame,
    *,
    dm: pl.DataFrame | None,
    mcs: pl.DataFrame | None,
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
    mcs_counts = _inference_status_counts(mcs, "mcs_status", "ok")
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
                "mcs_ok": mcs_counts.get(key, {}).get("ok", 0),
                "mcs_total": mcs_counts.get(key, {}).get("total", 0),
            }
        )
    return rows
