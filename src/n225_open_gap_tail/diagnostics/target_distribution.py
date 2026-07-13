# ruff: noqa: E501
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from scipy.stats import genpareto, jarque_bera  # type: ignore[import-untyped]


def opening_gap_scale_text(panel: pl.DataFrame) -> str:
    if panel.is_empty() or "gap_t" not in panel.columns:
        return "- Opening-gap scale is unavailable because the modeling panel is missing `gap_t`."
    clean = _target_clean_frame(panel)
    if clean.is_empty():
        return (
            "- Opening-gap scale is unavailable because no clean target rows have finite `gap_t`."
        )
    date_col = "forecast_date" if "forecast_date" in clean.columns else clean.columns[0]
    min_row = clean.sort("gap_t").head(1).to_dicts()[0]
    max_row = clean.sort("gap_t", descending=True).head(1).to_dicts()[0]
    abs_row = (
        clean.with_columns(pl.col("gap_t").abs().alias("_abs_gap_t"))
        .sort("_abs_gap_t", descending=True)
        .head(1)
        .to_dicts()[0]
    )
    stats = clean.select(
        pl.len().alias("rows"),
        pl.col("gap_t").quantile(0.01).alias("q01"),
        pl.col("gap_t").quantile(0.99).alias("q99"),
    ).to_dicts()[0]
    lines = [
        (
            f"- In the current clean primary sample (`n={stats['rows']}`), the settle-to-open "
            f"gap ranges from `{_fmt_log_return(min_row['gap_t'])}` on "
            f"`{min_row.get(date_col)}` to `{_fmt_log_return(max_row['gap_t'])}` on "
            f"`{max_row.get(date_col)}`."
        ),
        (
            f"- The largest absolute clean settle-to-open gap is "
            f"`{_fmt_log_return(abs_row['gap_t'])}` on `{abs_row.get(date_col)}`; "
            "this is large enough to make opening-gap tail risk a substantive risk-management "
            "forecasting problem rather than a cosmetic return-prediction exercise."
        ),
        (
            f"- The clean 1% to 99% settle-to-open range is "
            f"`{_fmt_log_return(stats['q01'])}` to `{_fmt_log_return(stats['q99'])}`, "
            "so the extremes are far outside the usual daily opening-gap range."
        ),
    ]
    if "residual_nightclose_to_day_open" in clean.columns:
        residual = clean.filter(
            pl.col("residual_nightclose_to_day_open").is_not_null()
            & pl.col("residual_nightclose_to_day_open").is_finite()
        )
        if not residual.is_empty():
            residual_stats = residual.select(
                pl.col("residual_nightclose_to_day_open").min().alias("min"),
                pl.col("residual_nightclose_to_day_open").max().alias("max"),
                pl.col("residual_nightclose_to_day_open").abs().max().alias("max_abs"),
            ).to_dicts()[0]
            lines.append(
                "- Even after the night-session close, the clean night-close-to-open residual "
                f"ranges from `{_fmt_log_return(residual_stats['min'])}` to "
                f"`{_fmt_log_return(residual_stats['max'])}`, with maximum absolute residual "
                f"`{_fmt_log_return(residual_stats['max_abs'])}`."
            )
    lines.append(
        "- These magnitudes make the empirical object an opening-tail risk problem, not only "
        "an average next-open return-forecasting problem."
    )
    return "\n".join(lines)


def target_tail_diagnostics_markdown(
    *,
    panel: pl.DataFrame,
    figure_manifest: dict[str, object],
    run_id: str,
) -> str:
    clean = _target_clean_frame(panel)
    if clean.is_empty():
        return """## Target Distribution And Tail Diagnostics

- Target-distribution diagnostics are unavailable because the snapshot cannot find finite clean `gap_t` observations.
- This placeholder is neutral: it does not change any forecast-evaluation claim.
"""
    gap = _target_array(clean, "gap_t")
    left_loss = -gap
    right_loss = gap
    abs_gap = np.abs(gap)
    summary_table = _target_summary_table(clean=clean, gap=gap)
    stability_table = _target_gpd_stability_table(
        series_by_side={
            "left_tail_loss": left_loss,
            "right_tail_loss": right_loss,
            "absolute_gap": abs_gap,
        }
    )
    figure_table = _target_distribution_figure_table(
        figure_manifest=figure_manifest,
        run_id=run_id,
    )
    return f"""## Target Distribution And Tail Diagnostics

- These diagnostics are computed from the raw clean settlement-to-open target `gap_t`; left loss is `-gap_t`, and right loss is `gap_t`.
- The purpose is to show why the dependent variable is a tail-risk object before comparing VaR/ES forecasts.
- Positive tail-shape estimates, heavy empirical tails, and upward mean-excess patterns are empirical support for using heavy-tail approximations such as POT-GPD; they are not a finite-sample proof of Frechet max-domain attraction.
- Raw target diagnostics motivate VaR/ES and EVT modeling. They do not validate LightGBM-EVT forecasts; forecast validity must be read from out-of-sample VaR/ES backtests and loss comparisons.

### Target Summary

{summary_table}

### Raw-Tail EVT Diagnostics

{stability_table}

- The GPD threshold table is computed on raw left loss, raw right loss, and the absolute gap; it should not be read as a forecast-model diagnostic.
- The Hill and GPD shape estimates are deliberately reported over multiple thresholds because tail-index estimates are sensitive in samples of this length.

### Target Distribution Figures

{figure_table}
"""


def _target_clean_frame(panel: pl.DataFrame) -> pl.DataFrame:
    if panel.is_empty() or "gap_t" not in panel.columns:
        return pl.DataFrame()
    clean = panel.filter(pl.col("gap_t").is_not_null() & pl.col("gap_t").is_finite())
    if "forecast_sample" in clean.columns:
        clean = clean.filter(pl.col("forecast_sample") == True)  # noqa: E712
    elif "clean_sample" in clean.columns:
        clean = clean.filter(pl.col("clean_sample") == True)  # noqa: E712
    if {"forecast_date", "combined_clean_start"}.issubset(clean.columns):
        clean = clean.filter(pl.col("forecast_date") >= pl.col("combined_clean_start"))
    return clean


def _target_array(frame: pl.DataFrame, column: str) -> np.ndarray:
    values = np.asarray(frame[column].to_list(), dtype=float)
    return cast(np.ndarray, values[np.isfinite(values)])


def _target_summary_table(*, clean: pl.DataFrame, gap: np.ndarray) -> str:
    if gap.size == 0:
        return _markdown_table(("Measure", "Value"), [("Clean observations", "0")])
    date_col = "forecast_date" if "forecast_date" in clean.columns else clean.columns[0]
    min_row = clean.sort("gap_t").head(1).to_dicts()[0]
    max_row = clean.sort("gap_t", descending=True).head(1).to_dicts()[0]
    std = float(np.std(gap, ddof=1)) if gap.size > 1 else float("nan")
    centered = gap - float(np.mean(gap))
    if std > 0.0 and np.isfinite(std):
        skewness = float(np.mean((centered / std) ** 3))
        excess_kurtosis = float(np.mean((centered / std) ** 4) - 3.0)
    else:
        skewness = float("nan")
        excess_kurtosis = float("nan")
    jb_stat, jb_pvalue = jarque_bera(gap)
    rows = [
        ("Clean forecast observations", f"`{gap.size}`"),
        ("Date range", _target_date_range(clean, date_col)),
        ("Mean gap", _fmt_log_return(float(np.mean(gap)))),
        ("Standard deviation", _fmt_log_return(std)),
        ("Skewness", _fmt_float(skewness)),
        ("Excess kurtosis", _fmt_float(excess_kurtosis)),
        ("1% quantile", _fmt_log_return(float(np.quantile(gap, 0.01)))),
        ("5% quantile", _fmt_log_return(float(np.quantile(gap, 0.05)))),
        ("Median", _fmt_log_return(float(np.quantile(gap, 0.50)))),
        ("95% quantile", _fmt_log_return(float(np.quantile(gap, 0.95)))),
        ("99% quantile", _fmt_log_return(float(np.quantile(gap, 0.99)))),
        (
            "Max drawdown gap",
            f"{_fmt_log_return(min_row['gap_t'])} on `{min_row.get(date_col)}`",
        ),
        (
            "Max upside gap",
            f"{_fmt_log_return(max_row['gap_t'])} on `{max_row.get(date_col)}`",
        ),
        ("Jarque-Bera p-value", _fmt_float(float(jb_pvalue))),
        ("Jarque-Bera statistic", _fmt_float(float(jb_stat))),
    ]
    return _markdown_table(("Measure", "Value"), rows)


def _target_date_range(frame: pl.DataFrame, date_col: str) -> str:
    bounds = frame.select(
        pl.col(date_col).min().alias("start"),
        pl.col(date_col).max().alias("end"),
    ).row(0, named=True)
    return f"`{bounds['start']} to {bounds['end']}`"


def _target_gpd_stability_table(*, series_by_side: dict[str, np.ndarray]) -> str:
    rows: list[tuple[object, ...]] = []
    for side, values in series_by_side.items():
        finite = values[np.isfinite(values)]
        finite = finite[finite > 0.0]
        if finite.size < 80:
            continue
        for probability in (0.90, 0.925, 0.95, 0.975, 0.99):
            threshold = float(np.quantile(finite, probability))
            excess = finite[finite > threshold] - threshold
            if excess.size < 8:
                continue
            shape, scale = _fit_gpd_excess(excess)
            hill_xi = _hill_xi(finite, int(excess.size))
            rows.append(
                (
                    side,
                    f"{probability:.3f}",
                    _fmt_float(threshold),
                    str(int(excess.size)),
                    _fmt_float(float(np.mean(excess))),
                    _fmt_float(shape),
                    _fmt_float(scale),
                    _fmt_float(hill_xi),
                )
            )
    if not rows:
        rows = [("missing", "", "", "0", "", "", "", "")]
    return _markdown_table(
        (
            "Tail",
            "Threshold probability",
            "Threshold",
            "Exceedances",
            "Mean excess",
            "GPD xi",
            "GPD scale",
            "Hill xi",
        ),
        rows,
    )


def _fit_gpd_excess(excess: np.ndarray) -> tuple[float, float]:
    try:
        shape, _, scale = genpareto.fit(excess, floc=0.0)
    except (ValueError, RuntimeError, FloatingPointError):
        return float("nan"), float("nan")
    return float(shape), float(scale)


def _hill_xi(values: np.ndarray, k: int) -> float:
    finite = values[np.isfinite(values)]
    finite = np.sort(finite[finite > 0.0])
    if finite.size <= k or k < 2:
        return float("nan")
    upper = finite[::-1]
    boundary = upper[k]
    if boundary <= 0.0:
        return float("nan")
    estimate = float(np.mean(np.log(upper[:k]) - np.log(boundary)))
    return estimate if math.isfinite(estimate) else float("nan")


def _target_distribution_figure_table(
    *,
    figure_manifest: dict[str, object],
    run_id: str,
) -> str:
    raw_figures = figure_manifest.get("figures")
    if not isinstance(raw_figures, list):
        return (
            "- Target-distribution figures are not available in the figure manifest for this run."
        )
    rows: list[tuple[object, ...]] = []
    seen: set[str] = set()
    for item in raw_figures:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        if not name.startswith("target_") or not path.endswith(".png") or name in seen:
            continue
        seen.add(name)
        rows.append(
            (
                f"`{name}`",
                _code(item.get("tail_side")),
                _source_artifacts_text(item.get("source_artifacts")),
                _code(item.get("claim_scope")),
                f"`figures/{run_id}/{Path(path).name}`",
            )
        )
    if not rows:
        return (
            "- Target-distribution figures are not available in the figure manifest for this run."
        )
    return _markdown_table(("Figure", "Tail side", "Source", "Claim scope", "Docs file"), rows)


def _markdown_table(headers: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _code(value: object) -> str:
    return f"`{value}`"


def _source_artifacts_text(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "`missing`"
    return ", ".join(f"`{item}`" for item in value)


def _fmt_log_return(value: object) -> str:
    parsed = _optional_float(value)
    if parsed is None:
        return "missing"
    simple_pct = math.expm1(parsed) * 100.0
    return f"{parsed:.6f} log ({simple_pct:+.2f}%)"


def _fmt_float(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.6g}"


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
