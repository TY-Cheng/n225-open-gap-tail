"""Descriptive plots of frozen forecasts and the target; no training or score inference."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from numpy.typing import NDArray

from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.reporting.figures import (
    _hill_curve,
    _mean_excess_curve,
    _survival_curve,
)

_COLORS = ("#1f77b4", "#d97706", "#555555")
_STYLES = ("-", "--", "-.")


def _date_expr(frame: pl.DataFrame, column: str) -> pl.Expr:
    expr = pl.col(column)
    return expr.str.to_date("%Y-%m-%d") if frame.schema[column] == pl.String else expr.cast(pl.Date)


def render_diagnostics(
    *,
    panel: pl.DataFrame,
    calendar: pl.DataFrame,
    common: pl.DataFrame,
    forecasts: pl.DataFrame,
    roster: list[str],
    output: Path,
) -> dict[str, str]:
    """Render three figures, validating selected predictions before creating outputs."""
    paths = _var_path_frame(panel, calendar, common, forecasts, roster)
    target = _target_frame(panel)
    paths.write_csv(output / "var_paths.csv")
    captions = _var_figures(paths, roster, output)
    captions["target_tail_motivation"] = _target_figure(target, output)
    return captions


def _var_path_frame(
    panel: pl.DataFrame,
    calendar: pl.DataFrame,
    common: pl.DataFrame,
    forecasts: pl.DataFrame,
    roster: list[str],
) -> pl.DataFrame:
    dates = common.filter((pl.col("scope") == "main") & pl.col("in_common")).select(
        _date_expr(common, "forecast_date")
    )
    if dates.is_empty() or dates["forecast_date"].n_unique() != dates.height:
        raise ValueError("Require nonempty, unique main common dates")
    native = calendar.select(_date_expr(calendar, "ose_trading_date").alias("forecast_date"))
    native = native.filter(
        pl.col("forecast_date").is_between(
            dates["forecast_date"].min(), dates["forecast_date"].max()
        )
    ).sort("forecast_date")
    if (
        native["forecast_date"].n_unique() != native.height
        or not dates.join(native, on="forecast_date", how="anti").is_empty()
    ):
        raise ValueError("Native calendar must uniquely contain every common date")
    targets = panel.select(_date_expr(panel, "forecast_date"), "gap_t").join(
        dates, on="forecast_date", how="semi"
    )
    if (
        targets.height != dates.height
        or targets["forecast_date"].n_unique() != dates.height
        or targets.filter(pl.col("gap_t").is_null() | ~pl.col("gap_t").is_finite()).height
    ):
        raise ValueError("Require one finite target per common date")
    if len(roster) != 3 or len(set(roster)) != 3:
        raise ValueError("Require two ML models followed by one reference")
    forecasts = forecasts.with_columns(_date_expr(forecasts, "forecast_date"))
    axis = native.with_columns(
        pl.col("forecast_date").is_in(dates["forecast_date"].implode()).alias("in_common")
    )
    pieces = []
    for side, sign in (("left_tail", -1), ("right_tail", 1)):
        for index, model in enumerate(roster):
            info = PASS_ALL_INFORMATION_SETS[-1] if index < 2 else "target_history_only"
            selected = forecasts.filter(
                (pl.col("model_name") == model)
                & (pl.col("information_set") == info)
                & (pl.col("tail_side") == side)
                & ((pl.col("tail_level") - 0.95).abs() < 1e-12)
            ).join(dates, on="forecast_date", how="semi")
            if (
                selected.height != dates.height
                or selected["forecast_date"].n_unique() != dates.height
            ):
                raise ValueError(f"Missing or duplicate common forecasts: {model}/{side}/{info}")
            if selected.filter(
                pl.any_horizontal(
                    pl.col("var_forecast", "realized_loss").is_null()
                    | ~pl.col("var_forecast", "realized_loss").is_finite()
                )
            ).height:
                raise ValueError(f"Nonfinite common forecast or realized loss: {model}/{side}")
            matched = selected.join(targets, on="forecast_date")
            if not np.allclose(
                matched["realized_loss"].to_numpy(),
                sign * matched["gap_t"].to_numpy(),
                rtol=1e-10,
                atol=1e-12,
            ):
                raise ValueError(f"Forecast target/sign disagrees with panel: {model}/{side}")
            pieces.append(
                axis.join(
                    selected.select("forecast_date", "var_forecast", "realized_loss"),
                    on="forecast_date",
                    how="left",
                    maintain_order="left",
                ).with_columns(
                    pl.lit(model).alias("model_name"),
                    pl.lit(info).alias("information_set"),
                    pl.lit(side).alias("tail_side"),
                    (100 * pl.col("var_forecast")).alias("var_pct"),
                    (100 * pl.col("realized_loss")).alias("loss_pct"),
                    (pl.col("realized_loss") > pl.col("var_forecast")).alias("breach"),
                )
            )
    return pl.concat(pieces)


def _target_frame(panel: pl.DataFrame) -> pl.DataFrame:
    target = (
        panel.filter(
            pl.col("target_clean_sample")
            & pl.col("gap_t").is_not_null()
            & pl.col("gap_t").is_finite()
        )
        .select(_date_expr(panel, "forecast_date"), "gap_t")
        .sort("forecast_date")
    )
    if target.height < 2 or target["forecast_date"].n_unique() != target.height:
        raise ValueError("Require at least two unique finite target-clean observations")
    return target


def _save(figure: Figure, output: Path, name: str) -> None:
    FigureCanvasAgg(figure)
    for extension in ("png", "pdf"):
        figure.savefig(output / f"{name}.{extension}", dpi=180)


def _var_figures(paths: pl.DataFrame, roster: list[str], output: Path) -> dict[str, str]:
    captions = {}
    bounds = np.concatenate([paths[c].drop_nulls().to_numpy() for c in ("loss_pct", "var_pct")])
    pad = max(float(np.ptp(bounds)) * 0.05, 0.01)
    for side, symbol in (("left_tail", "-g"), ("right_tail", "+g")):
        figure = Figure(figsize=(12, 5.4), layout="constrained")
        ax = figure.subplots()
        subset = paths.filter(pl.col("tail_side") == side)
        realized = subset.filter(pl.col("model_name") == roster[0])
        dates = [date.fromisoformat(str(value)) for value in realized["forecast_date"]]
        plot_dates = np.asarray(dates, dtype="datetime64[D]")
        n_common = realized.filter(pl.col("in_common")).height
        ax.plot(
            plot_dates,
            realized["loss_pct"].to_numpy(),
            color="#343434",
            alpha=0.45,
            linewidth=0.6,
            marker=".",
            markersize=2,
            label=f"Realized loss ({symbol})",
            zorder=1,
        )
        for index, model in enumerate(roster):
            series = subset.filter(pl.col("model_name") == model)
            label = display_model_label(model).replace("LightGBM ", "")
            label += " | D" if index < 2 else " | target history"
            ax.plot(
                plot_dates,
                series["var_pct"].to_numpy(),
                color=_COLORS[index],
                linestyle=_STYLES[index],
                linewidth=1.1,
                marker=".",
                markersize=2,
                label=f"{label} VaR",
                zorder=2,
            )
            breaches = series.filter(pl.col("breach"))
            ax.scatter(
                breaches["forecast_date"].to_numpy(),
                breaches["loss_pct"].to_numpy(),
                s=36 + 18 * index,
                marker=("s", "^", "o")[index],
                facecolors="none",
                edgecolors=_COLORS[index],
                linewidths=1.1,
                label=f"{label} breach (n={breaches.height})",
                zorder=3,
            )
        ax.axhline(0, color="#888888", linewidth=0.6)
        ax.set(
            title=f"95% VaR paths | {side.replace('_', ' ')} | {n_common} common dates",
            ylabel="Signed loss / VaR (%)",
            xlabel="OSE trading date",
            ylim=(float(bounds.min()) - pad, float(bounds.max()) + pad),
            xlim=(dates[0], dates[-1]),
        )
        ticks = sorted({dates[0] + (dates[-1] - dates[0]) * (i / 5) for i in range(6)})
        ax.set_xticks(np.asarray(ticks, dtype="datetime64[D]"), [str(value) for value in ticks])
        ax.grid(axis="y", alpha=0.18)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(
            loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, frameon=False, fontsize=8
        )
        figure.suptitle("Frozen forecasts; Set D for both ML recipes", fontsize=13)
        name = f"var_paths_{side}"
        _save(figure, output, name)
        captions[name] = (
            f"95% VaR and signed realized loss ({symbol}) on {n_common} fixed main common dates, "
            f"{dates[0]} to {dates[-1]}. Loss and VaR are multiplied by 100; no absolute-value "
            "or sign truncation is applied. The native OSE calendar is retained and noncommon "
            "dates are left blank, without interpolation or filling. Hollow squares (IQR), "
            "triangles (Gamma) and circles (GJR) mark realized losses strictly above each "
            "model's VaR; equality is not a breach. Legend counts use these common dates, "
            "not the native gate samples. Both ML recipes use Set D, "
            "selected by their lowest equal-left/right mean FZG for descriptive illustration; "
            "the reference uses target history only. This post-selection path display does not "
            "establish a superior information set and does not alter the all-scenario inference."
        )
    return captions


def _target_figure(target: pl.DataFrame, output: Path) -> str:
    gap = 100 * target["gap_t"].to_numpy()
    mean, std = float(np.mean(gap)), float(np.std(gap, ddof=1))
    start, end = str(target["forecast_date"].min()), str(target["forecast_date"].max())
    pl.DataFrame(
        [
            {
                "n_target": len(gap),
                "date_start": start,
                "date_end": end,
                "n_downside_positive": int(np.sum(gap < 0)),
                "n_upside_positive": int(np.sum(gap > 0)),
                "n_zero": int(np.sum(gap == 0)),
                "gap_mean_pct": mean,
                "gap_std_pct_ddof1": std,
            }
        ]
    ).write_csv(output / "target_tail_summary.csv")
    figure = Figure(figsize=(11.8, 8.6), layout="constrained")
    density, survival, excess, hill = figure.subplots(2, 2).ravel()
    heights, edges, _ = density.hist(
        gap, bins=50, density=True, color="#64748b", alpha=0.65, label="Empirical"
    )
    coordinates: list[dict[str, str | float]] = []

    def record(
        name: str, series: str, x: NDArray[np.float64], y: NDArray[np.float64], xu: str, yu: str
    ) -> None:
        coordinates.extend(
            {
                "diagnostic": name,
                "series": series,
                "x": float(a),
                "y": float(b),
                "x_unit": xu,
                "y_unit": yu,
            }
            for a, b in zip(x, y, strict=True)
        )

    record(
        "density",
        "empirical",
        (edges[:-1] + edges[1:]) / 2,
        heights,
        "percent",
        "density_per_percent",
    )
    if std > 0:
        x = np.linspace(float(gap.min()), float(gap.max()), 240)
        normal = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
        density.plot(x, normal, color="#222222", linestyle="--", label="Fitted normal")
        record("density", "fitted_normal", x, normal, "percent", "density_per_percent")
    density.set(title="(a) Opening-gap density", xlabel="Opening gap (%)", ylabel="Density")
    for index, (label, values) in enumerate(
        (("Downside", -gap), ("Upside", gap), ("Absolute gap", np.abs(gap)))
    ):
        color, style = _COLORS[index], _STYLES[index]
        if index < 2:
            x_raw, y_raw = _survival_curve(values)
            x, y = cast(NDArray[np.float64], x_raw), cast(NDArray[np.float64], y_raw)
            if x.size:
                survival.semilogy(x[y > 0], y[y > 0], color=color, linestyle=style, label=label)
                record("conditional_survival", label, x, y, "percent", "probability_given_positive")
            x_raw, y_raw = _mean_excess_curve(values)
            x, y = cast(NDArray[np.float64], x_raw), cast(NDArray[np.float64], y_raw)
            if x.size:
                excess.plot(x, y, color=color, linestyle=style, label=label)
                record("mean_excess", label, x, y, "threshold_percent", "excess_percent")
        x_raw, y_raw = _hill_curve(values)
        x, y = cast(NDArray[np.float64], x_raw), cast(NDArray[np.float64], y_raw)
        if x.size:
            hill.plot(x, y, color=color, linestyle=style, label=label)
            record("hill", label, x, y, "upper_order_count", "dimensionless")
    survival.set(
        title="(b) Positive-tail conditional survival",
        xlabel="Positive loss magnitude (%)",
        ylabel=r"$P(L>x\mid L>0)$ (log scale)",
    )
    excess.set(title="(c) Mean excess", xlabel="Threshold u (%)", ylabel="Mean excess above u (%)")
    hill.set(
        title="(d) Descriptive Hill paths",
        xlabel="Upper order statistics k",
        ylabel="Hill estimator (dimensionless)",
    )
    hill.axhline(0, color="#777777", linestyle=":", linewidth=0.7)
    for ax in (density, survival, excess, hill):
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend(frameon=False, fontsize=9)
        else:
            ax.text(0.5, 0.5, "Too few positive observations", transform=ax.transAxes, ha="center")
        ax.grid(alpha=0.18)
        ax.spines[["top", "right"]].set_visible(False)
    figure.suptitle(f"Opening-gap tail diagnostics | {len(gap):,} valid targets | {start} to {end}")
    _save(figure, output, "target_tail_motivation")
    pl.DataFrame(coordinates).write_csv(output / "target_tail_coordinates.csv")
    return (
        f"Descriptive opening-gap diagnostics from {len(gap):,} finite target-clean observations, "
        f"{start} to {end}; no predictor-start or forecast-availability filter. "
        "Values are multiplied by 100. The normal reference uses this sample's mean and "
        "sample standard deviation. "
        "Survival is P(L > x | L > 0), using only strictly positive values of -gap (downside) or "
        "+gap (upside) in its denominator; zero empirical survival is omitted from the log plot. "
        "Mean-excess thresholds use 24 quantiles from 0.80 to 0.99 of positive losses, retaining "
        "at least eight strict exceedances (at least 50 positive observations). Hill paths use "
        "k = 20, 25, ... up to min(220, floor(n_positive/3)), requiring 80 positive observations. "
        "These exploratory diagnostics describe empirical tail behavior; they do not prove "
        "regular variation, identify a GPD shape, establish EVT-model superiority, or validate "
        "forecast calibration. No new inferential tests are performed."
    )
