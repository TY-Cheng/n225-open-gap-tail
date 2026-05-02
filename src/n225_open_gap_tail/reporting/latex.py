# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    Mapping,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    pl,
    PRIMARY_TAIL_SIDE,
    _optional_float,
)
from n225_open_gap_tail.metrics.stat_utils import _fmt


def _metrics_to_latex(
    metrics: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    headers = ("model", "side", "tail", "rows", "breach", "q_loss", "fz_loss")
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
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in metrics.iter_rows(named=True):
        lines.append(
            f"{row['model_name']} & {_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{float(row['tail_level']):.3f} & "
            f"{int(row['rows'])} & {_fmt(row['var_breach_rate'])} & "
            f"{_fmt(row['mean_quantile_loss'])} & {_fmt(row['mean_fz_loss'])} \\\\"
        )
    note = (
        "Visible notes: candidate artifact; lower FZ loss is better; "
        "inference artifacts use block-bootstrap DM and HLN Tmax MCS; "
        "common-sample status is recorded in metrics metadata."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{7}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
        "% claim_scope: restricted_model_comparison_not_headline unless stated otherwise",
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
        label = row.get("information_set") or row.get("model_name") or ""
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
        "these rows do not replace the headline ML tail table."
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
            f"{_latex_escape(row.get('model_name'))} & "
            f"{_latex_escape(row.get('tail_side') or PRIMARY_TAIL_SIDE)} & "
            f"{_latex_escape(row.get('information_set'))} & "
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
            f"{_latex_escape(row.get('model_name'))} & "
            f"{_latex_escape(row.get('information_set'))} & "
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
            f"{_latex_escape(row.get('model_name'))} & "
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
        "Restricted samples are not headline evidence. DM/MCS counts show how many "
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
            "headline benchmark floor",
            "yes after clean-run author review",
        ),
        (
            "ml_tail_metrics.parquet",
            "headline ML-tail nested information sets",
            "yes; current headline comparison is direct quantile",
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
            "no forecasting-model or headline-superiority claim",
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
        "artifacts may support discussion, but they do not replace headline common-sample "
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
    if sample_policy == "headline_common_sample":
        return "headline"
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
        if group.is_empty():
            continue
        key_values = key if isinstance(key, tuple) else (key,)
        row_key = dict(zip(group_columns, key_values, strict=False))
        threshold = group.select(pl.col("var_forecast").quantile(0.75)).item()
        if threshold is None:
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
    mcs_counts = _inference_status_counts(mcs, "mcs_status", "ok_hln_tmax_mcs")
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


def _inference_status_counts(
    frame: pl.DataFrame | None,
    status_column: str,
    ok_prefix: str,
) -> dict[tuple[str, str, str, str], dict[str, int]]:
    if frame is None or frame.is_empty() or status_column not in frame.columns:
        return {}
    output: dict[tuple[str, str, str, str], dict[str, int]] = {}
    for row in frame.iter_rows(named=True):
        key = _result_summary_key(row)
        bucket = output.setdefault(key, {"ok": 0, "total": 0})
        bucket["total"] += 1
        if str(row.get(status_column) or "").startswith(ok_prefix):
            bucket["ok"] += 1
    return output


def _result_summary_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("comparison_family") or ""),
        str(row.get("comparison_axis") or ""),
        str(row.get("sample_policy") or ""),
        str(row.get("loss_family") or ""),
        str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
    )


def _range_label(low: object, high: object) -> str:
    low_value = _optional_float(low)
    high_value = _optional_float(high)
    if low_value is None or high_value is None:
        return "n/a"
    if int(low_value) == int(high_value):
        return str(int(low_value))
    return f"{int(low_value)}--{int(high_value)}"


def _latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for raw, escaped in replacements.items():
        text = text.replace(raw, escaped)
    return text
