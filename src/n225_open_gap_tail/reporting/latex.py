# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def _metrics_to_latex(
    metrics: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    headers = ("model", "tail", "rows", "breach", "q_loss", "fz_loss")
    manifest = manifest or {}
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        f"% claim_level: {manifest.get('claim_level', manifest.get('claims_level', ''))}",
        "% loss convention: loss_t = -gap_t; lower FZ loss is better",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in metrics.iter_rows(named=True):
        lines.append(
            f"{row['model_name']} & {float(row['tail_level']):.3f} & "
            f"{int(row['rows'])} & {_fmt(row['var_breach_rate'])} & "
            f"{_fmt(row['mean_quantile_loss'])} & {_fmt(row['mean_fz_loss'])} \\\\"
        )
    note = (
        "Visible notes: candidate artifact; lower FZ loss is better; "
        "inference artifacts use block-bootstrap DM and HLN Tmax MCS; "
        "common-sample status is recorded in metrics metadata."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def _result_matrix_to_latex(
    matrix: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    manifest = manifest or {}
    headers = ("family", "axis", "loss", "info/model", "tail", "N", "exc", "metric")
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        "% claim_scope: restricted_model_comparison_not_headline unless stated otherwise",
        "\\begin{tabular}{llllrrrr}",
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
    lines.extend(["\\midrule", f"\\multicolumn{{8}}{{l}}{{\\footnotesize {note}}} \\\\"])
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


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
