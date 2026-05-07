from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

import polars as pl

from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
)
from n225_open_gap_tail.config.runtime import ML_TAIL_MODEL_NAMES


def _all_model_comparison_table(
    *,
    benchmark_metrics: pl.DataFrame,
    benchmark_metrics_per_model: pl.DataFrame,
    ml_tail_metrics_per_model: pl.DataFrame,
) -> str:
    required = {
        "model_name",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "mean_quantile_loss",
        "mean_fz_loss",
        "mean_exceedance_severity",
    }
    metric_columns = [
        "model_name",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "mean_quantile_loss",
        "mean_fz_loss",
        "mean_exceedance_severity",
        "tail_side",
    ]
    floor_models = (
        set(str(value) for value in benchmark_metrics["model_name"].drop_nulls().unique().to_list())
        if not benchmark_metrics.is_empty() and "model_name" in benchmark_metrics.columns
        else set()
    )
    records: list[dict[str, object]] = []
    benchmark_source = (
        benchmark_metrics_per_model
        if not benchmark_metrics_per_model.is_empty()
        else benchmark_metrics
    )
    if not benchmark_source.is_empty() and required.issubset(benchmark_source.columns):
        columns = [column for column in metric_columns if column in benchmark_source.columns]
        for row in benchmark_source.select(columns).iter_rows(named=True):
            model_name = str(row["model_name"])
            records.append(
                {
                    **row,
                    "suite": (
                        "benchmark_floor"
                        if not floor_models or model_name in floor_models
                        else "benchmark_advanced"
                    ),
                    "model_label": display_model_label(model_name),
                    "information_set_label": display_information_set_label(
                        row.get("information_set")
                    ),
                    "information_set_order": _information_set_order(row.get("information_set")),
                    "abs_coverage_error": _abs_coverage_error(row),
                }
            )
    if not ml_tail_metrics_per_model.is_empty() and required.issubset(
        ml_tail_metrics_per_model.columns
    ):
        columns = [
            column for column in metric_columns if column in ml_tail_metrics_per_model.columns
        ]
        active_ml_models = set(ML_TAIL_MODEL_NAMES)
        for row in ml_tail_metrics_per_model.select(columns).iter_rows(named=True):
            if str(row["model_name"]) not in active_ml_models:
                continue
            records.append(
                {
                    **row,
                    "suite": "ml_tail",
                    "model_label": display_model_label(row["model_name"]),
                    "information_set_label": display_information_set_label(
                        row.get("information_set")
                    ),
                    "information_set_order": _information_set_order(row.get("information_set")),
                    "abs_coverage_error": _abs_coverage_error(row),
                }
            )
    if not records:
        return _markdown_table(
            (
                "Suite",
                "Model",
                "Information set",
                "Metric rows",
                "OOS N",
                "Breach",
                "Abs cov err",
                "Q loss",
                "FZ loss",
                "ES severity",
            ),
            [("missing", "missing", "missing", "0", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a")],
        )
    frame = pl.DataFrame(records)
    grouped = (
        frame.group_by(["suite", "model_label", "information_set_label"])
        .agg(
            pl.min("information_set_order").alias("information_set_order"),
            pl.len().alias("metric_rows"),
            pl.mean("rows").alias("rows_mean"),
            pl.std("rows").alias("rows_std"),
            pl.mean("var_breach_rate").alias("breach_mean"),
            pl.std("var_breach_rate").alias("breach_std"),
            pl.mean("abs_coverage_error").alias("abs_cov_err_mean"),
            pl.std("abs_coverage_error").alias("abs_cov_err_std"),
            pl.mean("mean_quantile_loss").alias("q_loss_mean"),
            pl.std("mean_quantile_loss").alias("q_loss_std"),
            pl.mean("mean_fz_loss").alias("fz_loss_mean"),
            pl.std("mean_fz_loss").alias("fz_loss_std"),
            pl.mean("mean_exceedance_severity").alias("severity_mean"),
            pl.std("mean_exceedance_severity").alias("severity_std"),
        )
        .sort(["suite", "model_label", "information_set_order", "information_set_label"])
    )
    rows = [
        (
            row["suite"],
            row["model_label"],
            row["information_set_label"],
            row["metric_rows"],
            _fmt_mean_std(row["rows_mean"], row["rows_std"]),
            _fmt_mean_std(row["breach_mean"], row["breach_std"], rate=True),
            _fmt_mean_std(row["abs_cov_err_mean"], row["abs_cov_err_std"], rate=True),
            _fmt_mean_std(row["q_loss_mean"], row["q_loss_std"]),
            _fmt_mean_std(row["fz_loss_mean"], row["fz_loss_std"]),
            _fmt_mean_std(row["severity_mean"], row["severity_std"]),
        )
        for row in grouped.iter_rows(named=True)
    ]
    return _markdown_table(
        (
            "Suite",
            "Model",
            "Information set",
            "Metric rows",
            "OOS N mean+-sd",
            "Breach mean+-sd",
            "Abs cov err mean+-sd",
            "Q loss mean+-sd",
            "FZ loss mean+-sd",
            "ES severity mean+-sd",
        ),
        rows,
    )


def _abs_coverage_error(row: dict[str, object]) -> float | None:
    breach = _optional_float(row.get("var_breach_rate"))
    expected = _optional_float(row.get("expected_breach_rate"))
    if breach is None or expected is None:
        return None
    return abs(breach - expected)


def _information_set_order(value: object) -> int:
    text = "" if value is None else str(value)
    order = {
        "target_history_only": 0,
        "japan_only": 1,
        "japan_only_plus_us_close_core": 2,
        "japan_only_plus_us_close_core_plus_japan_proxy": 3,
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy": 4,
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy_plus_options_risk": 5,
    }
    return order.get(text, 99)


def _fmt_mean_std(mean: object, std: object, *, rate: bool = False) -> str:
    mean_value = _optional_float(mean)
    if mean_value is None:
        return "n/a"
    std_value = _optional_float(std)
    if std_value is None:
        std_value = 0.0
    if rate:
        return f"{_fmt_rate(mean_value)} +/- {_fmt_rate(std_value)}"
    return f"{_fmt_float(mean_value)} +/- {_fmt_float(std_value)}"


def _fmt_rate(value: object) -> str:
    numeric = _optional_float(value)
    return "n/a" if numeric is None else f"{numeric:.3%}"


def _fmt_float(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.6g}"


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _markdown_table(headers: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
