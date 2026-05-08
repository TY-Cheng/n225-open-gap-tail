# ruff: noqa: E501
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

import polars as pl

from n225_open_gap_tail.config.model_labels import display_model_label


def _code(value: object) -> str:
    return f"`{value}`"


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    return _code(value)


def _join_model_list(value: object) -> str:
    if isinstance(value, list | tuple):
        return ", ".join(f"`{display_model_label(item)}`" for item in value)
    return _code(display_model_label(value))


def _markdown_table(headers: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _demote_markdown_headings(markdown: str, *, levels: int) -> str:
    prefix = "#" * levels
    lines = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            lines.append(f"{prefix}{line}")
        else:
            lines.append(line)
    return "\n".join(lines)


def _markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _panel_bounds(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "forecast_date" not in frame.columns:
        return "`missing`"
    values = frame.select(
        pl.col("forecast_date").min().alias("start"),
        pl.col("forecast_date").max().alias("end"),
    ).row(0, named=True)
    return f"`{values['start']} to {values['end']}`"


def _forecast_sample_bounds(frame: pl.DataFrame) -> str:
    if frame.is_empty() or not {"forecast_date", "forecast_sample"}.issubset(frame.columns):
        return "`missing`"
    filtered = frame.filter(pl.col("forecast_sample") == True)  # noqa: E712
    if filtered.is_empty():
        return "`empty`"
    values = filtered.select(
        pl.col("forecast_date").min().alias("start"),
        pl.col("forecast_date").max().alias("end"),
        pl.len().alias("rows"),
    ).row(0, named=True)
    return f"`{values['start']} to {values['end']} ({values['rows']} rows)`"


def _bool_sum(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.select(pl.col(column).fill_null(False).sum()).item() or 0)


def _count_value(frame: pl.DataFrame, column: str, value: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.filter(pl.col(column) == value).height)


def _counts_table(frame: pl.DataFrame, column: str, label: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return _markdown_table((label, "Rows"), [("missing", "0")])
    rows = [
        (str(row[column]), str(row["len"]))
        for row in frame.group_by(column).len().sort("len", descending=True).iter_rows(named=True)
    ]
    return _markdown_table((label, "Rows"), rows)


def _result_matrix_display_value(value: object) -> str:
    text = str(value)
    if text == "information_set_ladder":
        return "nested information sets"
    return text


def _unique_values(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return "`missing`"
    values = sorted(str(value) for value in frame[column].drop_nulls().unique().to_list())
    return ", ".join(f"`{value}`" for value in values)


def _fmt_float(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.6g}"


def _fmt_rate(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.3%}"


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
