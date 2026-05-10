from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from n225_open_gap_tail.config.runtime import PRIMARY_TAIL_SIDE, _optional_float


def _inference_status_counts(
    frame: pl.DataFrame | None,
    status_column: str,
    ok_prefix: str,
) -> dict[tuple[str, str, str, str, str], dict[str, int]]:
    if frame is None or frame.is_empty() or status_column not in frame.columns:
        return {}
    output: dict[tuple[str, str, str, str, str], dict[str, int]] = {}
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
