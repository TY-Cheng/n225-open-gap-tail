# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_BASELINE_MODEL_NAMES,
    Mapping,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    np,
    pl,
    PRIMARY_TAIL_SIDE,
    TAIL_SIDE_LEFT,
    TAIL_SIDE_RIGHT,
)
from n225_open_gap_tail.config.model_labels import (
    display_information_set_label,
    display_model_label,
    display_suite_group_label,
    display_tail_side_label,
)
from n225_open_gap_tail.inference.core import build_murphy_records
from n225_open_gap_tail.metrics.cross_suite_dm import (
    CROSS_SUITE_DM_MODEL_SPECS,
    LGBM_STANDARD_PLAIN_MLE_C_LABEL,
    LGBM_STANDARD_UNIBM_C_LABEL,
    cross_suite_dm_gate_status as _cross_suite_dm_gate_status,
    cross_suite_dm_loss_rows as _cross_suite_dm_loss_rows,
    cross_suite_dm_records as _cross_suite_dm_records,
)
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_COVERAGE_TOLERANCE,
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_LGBM_MODEL_ORDER,
    PASS_ALL_MIN_ROWS,
    PASS_ALL_TEST_ALPHA,
    pass_all_lgbm_model_names,
    pass_all_row_passes,
)
from n225_open_gap_tail.reporting.latex import _severity_rows
from n225_open_gap_tail.metrics.stat_utils import (
    fz_loss,
    quantile_loss,
)

matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42


INFORMATION_LADDER_ORDER = PASS_ALL_INFORMATION_SETS
COVERAGE_GATE_ROBUST_MODEL_ORDER = PASS_ALL_LGBM_MODEL_ORDER
COVERAGE_GATE_MIN_ROWS = PASS_ALL_MIN_ROWS
COVERAGE_GATE_TOLERANCE = PASS_ALL_COVERAGE_TOLERANCE
COVERAGE_GATE_TEST_ALPHA = PASS_ALL_TEST_ALPHA
BENCHMARK_STRESS_PRIMARY_MODEL = "gjr_garch_evt"
BENCHMARK_STRESS_FALLBACK_MODEL = "gjr_garch_t"
LGBM_24CHECK_CUMULATIVE_MODELS = (
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
)
INFORMATION_INCREMENT_ANCHOR_SET = "japan_only"
INFORMATION_INCREMENT_CANDIDATE_SETS = INFORMATION_LADDER_ORDER[1:]
STRESS_OVERLAY_INFORMATION_SET = INFORMATION_LADDER_ORDER[2]
STRESS_OVERLAY_WINDOW_HALF_WIDTH_DAYS = 30
STRESS_OVERLAY_MAX_WINDOWS = 2
STRESS_OVERLAY_EPISODE_CLUSTER_DAYS = 90
STRESS_OVERLAY_REALIZED_COLOR = "#111827"
STRESS_OVERLAY_COLORS = {
    "GJR-GARCH-EVT": "#2563eb",
    "GJR-GARCH-t fallback": "#2563eb",
    LGBM_STANDARD_PLAIN_MLE_C_LABEL: "#10b981",
    LGBM_STANDARD_UNIBM_C_LABEL: "#f97316",
}
STRESS_OVERLAY_MARKERS = {
    "GJR-GARCH-EVT": "o",
    "GJR-GARCH-t fallback": "o",
    LGBM_STANDARD_PLAIN_MLE_C_LABEL: "s",
    LGBM_STANDARD_UNIBM_C_LABEL: "^",
}
FULL_SAMPLE_OVERLAY_COLORS = {
    "GJR-GARCH-EVT": "#2563eb",
    LGBM_STANDARD_PLAIN_MLE_C_LABEL: "#10b981",
    LGBM_STANDARD_UNIBM_C_LABEL: "#f97316",
}
FULL_SAMPLE_OVERLAY_MARKERS = {
    "GJR-GARCH-EVT": "o",
    LGBM_STANDARD_PLAIN_MLE_C_LABEL: "s",
    LGBM_STANDARD_UNIBM_C_LABEL: "^",
}


@dataclass(frozen=True)
class FigureExportResult:
    figure_dir: Path
    figure_entries: list[dict[str, object]]


def export_figures(*, run_dir: Path, manifest: Mapping[str, object]) -> FigureExportResult:
    """Render paper-facing diagnostic figures from existing run artifacts."""
    figure_dir = run_dir / "latex" / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_figures(figure_dir)
    entries: list[dict[str, object]] = []
    entries.extend(_market_timing_design_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_target_tail_motivation_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_coverage_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_cumulative_loss_difference_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_full_sample_var_overlay_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_murphy_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_lgbm_24check_murphy_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_severity_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_stress_overlay_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_dm_heatmap_figures(run_dir=run_dir, figure_dir=figure_dir))
    _ = manifest
    return FigureExportResult(figure_dir=figure_dir, figure_entries=entries)


def _remove_stale_figures(figure_dir: Path) -> None:
    for pattern in ("*.png", "*.pdf"):
        for path in figure_dir.glob(pattern):
            path.unlink(missing_ok=True)


def _market_timing_design_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    if not (run_dir / "manifest.json").exists():
        return []
    fig, ax = plt.subplots(figsize=(12.8, 3.05))
    ax.set_xlim(-0.6, 14.8)
    ax.set_ylim(-1.42, 1.25)
    ax.axis("off")

    events = [
        (0.0, "T-1\n15:15\nOSE close /\nsettlement", "#eef2ff", 0.84),
        (2.35, "T-1\n16:30\nOSE night\nopens", "#eef2ff", 0.84),
        (4.70, "T\n05:00\nNYSE close\nif EDT", "#fef2f2", 0.84),
        (7.05, "T\n05:30\nOSE night\ncloses", "#eef2ff", 0.84),
        (9.40, "T\n06:00\nNYSE close\nif EST", "#fef2f2", 0.84),
        (11.75, "T\nmatched\nNYSE close\n+ data lag\ncutoff", "#fdf2f8", 1.02),
        (14.10, "T\n08:45\nOSE day\nopen", "#f0fdf4", 0.84),
    ]
    for (x0, _label0, _face0, half_width0), (x1, _label1, _face1, half_width1) in zip(
        events[:-1], events[1:], strict=True
    ):
        ax.annotate(
            "",
            xy=(x1 - half_width1, 0.0),
            xytext=(x0 + half_width0, 0.0),
            arrowprops={"arrowstyle": "->", "linewidth": 1.2, "color": "#9ca3af"},
        )
    for x, label, facecolor, _half_width in events:
        ax.text(
            x,
            0.0,
            label,
            ha="center",
            va="center",
            fontsize=9.2,
            color="#111827",
            linespacing=1.0,
            bbox={
                "boxstyle": "round,pad=0.36,rounding_size=0.08",
                "facecolor": facecolor,
                "edgecolor": "#a3a3a3",
                "linewidth": 0.8,
            },
        )
    ax.plot(
        [2.35, 2.35, 7.05, 7.05],
        [-0.58, -1.02, -1.02, -0.58],
        color="#818cf8",
        linewidth=1.3,
    )
    ax.text(
        4.70,
        -1.20,
        "OSE night session",
        ha="center",
        va="center",
        fontsize=8.7,
        color="#1d4ed8",
    )
    ax.set_title(
        "Japan Standard Time (JST) timing for the settlement-to-open forecast design",
        fontsize=12.5,
    )
    caption = (
        "Session-aligned forecast-origin and target-timing diagram. The U.S. cash "
        "close appears at 05:00 JST during U.S. daylight-saving time and at 06:00 "
        "JST during U.S. standard time. OSE labels show the pre-2024-11-05 hours: "
        "day close 15:15 JST, night session 16:30-05:30 JST, and next day open "
        "08:45 JST. From 2024-11-05, JPX hours are day close 15:45 JST and night "
        "session 17:00-06:00 JST; the next day open remains 08:45 JST. The model "
        "cutoff is the matched U.S. equity-market close plus the pre-specified "
        "data-availability "
        "lag; the OSE night close is timing context, not the forecast origin. The "
        "figure is a forecast-origin and target-timing diagram, not a structural "
        "market-transmission diagram."
    )
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name="market_timing_design",
        source_artifacts=[
            "manifest.json",
            "config/research_config.json",
            "panel/calendar_map.parquet",
        ],
        tail_side="design",
        caption=caption,
        claim_scope="design_forecast_origin_not_causal_price_discovery",
    )


def _legend_if_labeled(ax: object, **kwargs: object) -> None:
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(**kwargs)


def _target_tail_motivation_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _target_gap_frame(run_dir)
    if frame.is_empty():
        return []
    gap = _finite_array(frame, "gap_t")
    if gap.size < 50:
        return []
    left_loss = -gap
    right_loss = gap
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 8.6))
    ax_density, ax_survival, ax_excess, ax_hill = axes.ravel()
    ax_density.hist(gap, bins=50, density=True, color="#64748b", alpha=0.62, label="empirical")
    _plot_normal_density(ax_density, gap)
    ax_density.axvline(0.0, color="#111827", linewidth=1.0)
    ax_density.set_title("A. Opening-gap density")
    ax_density.set_xlabel(r"$g_t$ (log return)")
    ax_density.set_ylabel("Density")
    _legend_if_labeled(ax_density, frameon=False, fontsize=7)

    for label, values, color in (
        ("Downside loss", left_loss, "#dc2626"),
        ("Upside loss", right_loss, "#2563eb"),
    ):
        x, survival = _survival_curve(values)
        if x.size:
            mask = survival > 0
            ax_survival.semilogy(
                x[mask],
                survival[mask],
                label=label,
                color=color,
                linewidth=1.5,
            )
    ax_survival.set_title("B. Tail log survival")
    ax_survival.set_xlabel("Positive loss magnitude")
    ax_survival.set_ylabel("Empirical survival, log scale")
    _legend_if_labeled(ax_survival, frameon=False, fontsize=7)

    for label, values, color in (
        ("Downside loss", left_loss, "#dc2626"),
        ("Upside loss", right_loss, "#2563eb"),
    ):
        thresholds, mean_excess = _mean_excess_curve(values)
        if thresholds.size:
            ax_excess.plot(thresholds, mean_excess, label=label, color=color, linewidth=1.5)
            threshold = _tail_threshold(values)
            ax_excess.axvline(threshold, color=color, linewidth=1.0, linestyle="--")
    ax_excess.set_title("C. Mean excess")
    ax_excess.set_xlabel("Threshold u")
    ax_excess.set_ylabel("Mean excess over u")
    _legend_if_labeled(ax_excess, frameon=False, fontsize=7)

    for label, values, color in (
        ("Downside loss", left_loss, "#dc2626"),
        ("Upside loss", right_loss, "#2563eb"),
        ("Absolute opening gap", np.abs(gap), "#4b5563"),
    ):
        ks, xi = _hill_curve(values)
        if ks.size:
            ax_hill.plot(ks, xi, label=label, color=color, linewidth=1.5)
    ax_hill.axhline(0.0, color="#111827", linewidth=0.9, linestyle=":")
    ax_hill.set_title("D. Hill tail-index path")
    ax_hill.set_xlabel("Upper order statistics k")
    ax_hill.set_ylabel(r"Hill estimate of GPD shape $\xi$")
    _legend_if_labeled(ax_hill, frameon=False, fontsize=7)

    for ax in axes.ravel():
        _style_axes(ax)
    fig.suptitle("Opening-gap distribution and tail diagnostics", fontsize=12)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name="target_tail_motivation",
        source_artifacts=["panel/modeling_panel.parquet"],
        tail_side="left_right_target_distribution",
        caption=(
            "Composite raw-target motivation figure: density versus a Gaussian "
            "reference, left/right log-survival curves, mean-excess curves, and "
            "Hill tail-index paths. This is raw target motivation, "
            "not forecast validation."
        ),
        claim_scope="target_distribution_motivation_not_forecast_validation",
    )


def _target_gap_frame(run_dir: Path) -> pl.DataFrame:
    frame = _read_optional_parquet(run_dir / "panel" / "modeling_panel.parquet")
    if frame.is_empty() or "gap_t" not in frame.columns:
        return pl.DataFrame()
    clean = frame.filter(pl.col("gap_t").is_not_null() & pl.col("gap_t").is_finite())
    if "forecast_sample" in clean.columns:
        clean = clean.filter(pl.col("forecast_sample") == True)  # noqa: E712
    elif "clean_sample" in clean.columns:
        clean = clean.filter(pl.col("clean_sample") == True)  # noqa: E712
    if {"forecast_date", "combined_clean_start"}.issubset(clean.columns):
        clean = clean.filter(pl.col("forecast_date") >= pl.col("combined_clean_start"))
    return clean


def _finite_array(frame: pl.DataFrame, column: str) -> object:
    values = np.asarray(frame[column].to_list(), dtype=float)
    return values[np.isfinite(values)]


def _plot_normal_density(ax: object, values: object) -> None:
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    if not np.isfinite(std) or std <= 0.0:
        return
    x = np.linspace(float(np.min(values)), float(np.max(values)), 240)
    density = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2.0 * np.pi))
    ax.plot(x, density, color="#111827", linewidth=1.2, label="normal reference")


def _survival_curve(values: object) -> tuple[object, object]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.asarray([]), np.asarray([])
    positive = np.sort(finite[finite > 0.0])
    if positive.size == 0:
        return np.asarray([]), np.asarray([])
    survival = np.asarray([float(np.mean(positive > value)) for value in positive])
    return positive, survival


def _mean_excess_curve(values: object) -> tuple[object, object]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    finite = finite[finite > 0.0]
    if finite.size < 50:
        return np.asarray([]), np.asarray([])
    thresholds = np.quantile(finite, np.linspace(0.80, 0.99, 24))
    mean_excess = []
    kept_thresholds = []
    for threshold in thresholds:
        excess = finite[finite > threshold] - threshold
        if excess.size >= 8:
            kept_thresholds.append(float(threshold))
            mean_excess.append(float(np.mean(excess)))
    return np.asarray(kept_thresholds), np.asarray(mean_excess)


def _hill_curve(values: object) -> tuple[object, object]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    finite = np.sort(finite[finite > 0.0])
    n = finite.size
    if n < 80:
        return np.asarray([]), np.asarray([])
    upper = finite[::-1]
    max_k = min(220, n // 3)
    ks = np.arange(20, max_k + 1, 5)
    xi: list[float] = []
    kept: list[int] = []
    for k in ks:
        boundary = upper[k]
        if boundary <= 0.0:
            continue
        estimate = float(np.mean(np.log(upper[:k]) - np.log(boundary)))
        if np.isfinite(estimate):
            kept.append(int(k))
            xi.append(estimate)
    return np.asarray(kept), np.asarray(xi)


def _coverage_robust_model_names(frame: pl.DataFrame) -> tuple[str, ...]:
    return pass_all_lgbm_model_names(frame)


def _coverage_robust_row_passes(row: Mapping[str, object]) -> bool:
    return pass_all_row_passes(row)


def _coverage_robust_model_order(value: object) -> int:
    text = str(value or "")
    try:
        return COVERAGE_GATE_ROBUST_MODEL_ORDER.index(text)
    except ValueError:
        return len(COVERAGE_GATE_ROBUST_MODEL_ORDER) + 1


def _coverage_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _coverage_frame(run_dir)
    if frame.is_empty() or "tail_side" not in frame.columns:
        return []
    entries: list[dict[str, object]] = []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        fig, ax = plt.subplots(figsize=(11, max(5, side.height * 0.32)))
        labels = [
            f"{display_suite_group_label(row['suite_group'])} | {row['model_label']}"
            for row in side.sort(["suite_order", "model_label"]).iter_rows(named=True)
        ]
        values = [
            float(row["var_breach_rate"]) * 100.0
            for row in side.sort(["suite_order", "model_label"]).iter_rows(named=True)
        ]
        colors = [
            _suite_color(str(row["suite_group"]))
            for row in side.sort(["suite_order", "model_label"]).iter_rows(named=True)
        ]
        ax.barh(labels, values, color=colors, alpha=0.88)
        expected = _first_float(side, "expected_breach_rate") or 0.05
        ax.axvline(expected * 100.0, color="#1f2937", linestyle="--", linewidth=1.4)
        ax.set_xlabel("VaR breach rate (%)")
        ax.set_title(f"Coverage diagnostics ({_label_tail_side(tail_side)})")
        ax.text(
            expected * 100.0,
            -0.75,
            f"nominal {expected * 100.0:.1f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#1f2937",
        )
        _style_axes(ax)
        caption = (
            f"Coverage breach-rate diagnostic for {tail_side}; bars show realized VaR "
            "exception rates against the nominal reference line. This figure is a "
            "coverage diagnostic and does not rank models or make a selection claim."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"coverage_breach_rates_{tail_side}",
                source_artifacts=[
                    "metrics/benchmark_metrics.parquet",
                    "metrics/benchmark_metrics_per_model.parquet",
                    "metrics/ml_tail_metrics.parquet",
                    "metrics/ml_tail_metrics_per_model.parquet",
                ],
                tail_side=tail_side,
                caption=caption,
                claim_scope="coverage_diagnostic_not_primary_claim",
            )
        )
    return entries


def _coverage_frame(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_metrics = _read_optional_parquet(run_dir / "metrics" / "benchmark_metrics.parquet")
    if not benchmark_metrics.is_empty():
        selected = _coverage_select(benchmark_metrics)
        if not selected.is_empty():
            frames.append(
                selected.with_columns(
                    pl.lit("benchmark_baseline").alias("suite_group"),
                    pl.lit(0).alias("suite_order"),
                    _model_label_expr().alias("model_label"),
                )
            )
    benchmark_per_model = _read_optional_parquet(
        run_dir / "metrics" / "benchmark_metrics_per_model.parquet"
    )
    if not benchmark_per_model.is_empty() and "model_name" in benchmark_per_model.columns:
        advanced = benchmark_per_model.filter(
            ~pl.col("model_name").is_in(list(BENCHMARK_BASELINE_MODEL_NAMES))
        )
        if not advanced.is_empty():
            selected = _coverage_select(advanced)
            if not selected.is_empty():
                frames.append(
                    selected.with_columns(
                        pl.lit("benchmark_advanced").alias("suite_group"),
                        pl.lit(1).alias("suite_order"),
                        _model_label_expr().alias("model_label"),
                    )
                )
    ml_tail_metrics = _read_optional_parquet(run_dir / "metrics" / "ml_tail_metrics.parquet")
    if not ml_tail_metrics.is_empty():
        selected = _coverage_select(ml_tail_metrics)
        if not selected.is_empty():
            frames.append(
                selected.with_columns(
                    pl.lit("ml_tail_primary").alias("suite_group"),
                    pl.lit(2).alias("suite_order"),
                    (_model_label_expr() + pl.lit(" / ") + _information_set_label_expr()).alias(
                        "model_label"
                    ),
                )
            )
    ml_tail_per_model = _read_optional_parquet(
        run_dir / "metrics" / "ml_tail_metrics_per_model.parquet"
    )
    if not ml_tail_per_model.is_empty() and "model_name" in ml_tail_per_model.columns:
        restricted = ml_tail_per_model.filter(pl.col("model_name") != ML_TAIL_DIRECT_QUANTILE_MODEL)
        if not restricted.is_empty():
            selected = _coverage_select(restricted)
            if not selected.is_empty():
                frames.append(
                    selected.with_columns(
                        pl.lit("ml_tail_restricted_family").alias("suite_group"),
                        pl.lit(3).alias("suite_order"),
                        (_model_label_expr() + pl.lit(" / ") + _information_set_label_expr()).alias(
                            "model_label"
                        ),
                    )
                )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _cumulative_loss_difference_figures(
    *, run_dir: Path, figure_dir: Path
) -> list[dict[str, object]]:
    loss_frame = _all_loss_rows(run_dir)
    if loss_frame.is_empty():
        return []
    panel_specs = [
        (tail_side, model_name)
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)
        for model_name in LGBM_24CHECK_CUMULATIVE_MODELS
    ]
    panel_series = [
        (
            tail_side,
            model_name,
            _lgbm_a_anchor_cumulative_loss_pairs(loss_frame, tail_side, model_name),
        )
        for tail_side, model_name in panel_specs
    ]
    if not any(rows for _, _, rows in panel_series):
        return []

    fig, axes = plt.subplots(
        len((TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)),
        len(LGBM_24CHECK_CUMULATIVE_MODELS),
        figsize=(13.6, 8.1),
        sharex=True,
        sharey=True,
    )
    axes_array = np.asarray(axes)
    for row_index, tail_side in enumerate((TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)):
        for column_index, model_name in enumerate(LGBM_24CHECK_CUMULATIVE_MODELS):
            ax = axes_array[row_index, column_index]
            series = next(
                rows
                for series_tail, series_model, rows in panel_series
                if series_tail == tail_side and series_model == model_name
            )
            for style_index, (label, frame) in enumerate(series):
                if frame.is_empty():
                    continue
                forecast_dates = _plot_date_values(frame["forecast_date"].to_list())
                ax.plot(
                    forecast_dates,
                    frame["cumulative_gain"].to_list(),
                    linewidth=1.45,
                    linestyle=("-", "--", ":", "-.")[style_index % 4],
                    label=label,
                )
            ax.axhline(0.0, color="#111827", linewidth=0.9, linestyle="--")
            ax.set_title(
                f"{_label_tail_side(tail_side)} | {display_model_label(model_name)}",
                fontsize=10,
            )
            if row_index == axes_array.shape[0] - 1:
                ax.set_xlabel("Forecast date")
            if column_index == 0:
                ax.set_ylabel("Cumulative FZ gain relative to A")
            if row_index == 0 and column_index == 0:
                ax.legend(frameon=False, fontsize=7)
            _set_monthly_date_ticks(ax)
            _style_axes(ax)
    fig.suptitle(
        "Cumulative FZ gains relative to the corresponding Japan-only LightGBM-EVT baseline",
        fontsize=13,
    )
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name="cumulative_lgbm_a_anchor_fz_gain",
        source_artifacts=[
            "metrics/benchmark_loss_matrix.parquet",
            "metrics/ml_tail_loss_matrix.parquet",
            "forecasts/benchmark_forecasts.parquet",
            "forecasts/ml_tail_forecasts.parquet",
        ],
        tail_side="left_right",
        caption=(
            "Cumulative FZ-gain diagnostic relative to the corresponding Japan-only "
            "LightGBM-EVT baseline. Each panel fixes a tail side and one of the two "
            "mean/scale LightGBM-EVT specifications that satisfy the coverage screen. "
            "At each date, a path is the cumulative sum over pair-specific common dates "
            "of FZ(A) minus FZ(candidate), where A is the corresponding Japan-only "
            "LightGBM-EVT forecast. Positive movement favors the candidate."
        ),
        claim_scope="headline_lgbm_a_anchor_gjr_evt_and_information_increment_fz_gain",
    )


def _coverage_select(frame: pl.DataFrame) -> pl.DataFrame:
    required = {"model_name", "tail_side", "var_breach_rate", "expected_breach_rate"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return pl.DataFrame()
    columns = [
        column
        for column in (
            "model_name",
            "information_set",
            "tail_side",
            "tail_level",
            "var_breach_rate",
            "expected_breach_rate",
        )
        if column in frame.columns
    ]
    return frame.select(columns).filter(pl.col("var_breach_rate").is_not_null())


def _model_label_expr() -> pl.Expr:
    return pl.col("model_name").map_elements(display_model_label, return_dtype=pl.Utf8)


def _information_set_label_expr() -> pl.Expr:
    return pl.col("information_set").map_elements(
        display_information_set_label,
        return_dtype=pl.Utf8,
    )


def _murphy_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    specs = [
        (
            "benchmark_murphy",
            run_dir / "metrics" / "benchmark_murphy.parquet",
            "Murphy diagnostics for the benchmark suite",
            "model_name",
            "metrics/benchmark_murphy.parquet",
            "murphy_diagnostic_benchmark_baseline_common_grid",
        ),
    ]
    for prefix, path, title, label_column, source, claim_scope in specs:
        frame = _read_optional_parquet(path)
        required = {"tail_side", "threshold_value", "mean_elementary_score", label_column}
        if frame.is_empty() or not required.issubset(frame.columns):
            continue
        for tail_side in _available_tail_sides(frame):
            side = frame.filter(pl.col("tail_side") == tail_side)
            if side.is_empty():
                continue
            fig, ax = plt.subplots(figsize=(8.5, 5.5))
            for key, group in side.group_by(label_column, maintain_order=True):
                label = str(key[0] if isinstance(key, tuple) else key)
                if label_column == "information_set":
                    label = display_information_set_label(label)
                elif label_column == "model_name":
                    label = display_model_label(label)
                curve = group.sort("threshold_value")
                ax.plot(
                    curve["threshold_value"].to_list(),
                    curve["mean_elementary_score"].to_list(),
                    linewidth=1.5,
                    label=_short_label(label),
                )
            ax.set_title(f"{title} ({_label_tail_side(tail_side)})")
            ax.set_xlabel("Elementary-score threshold")
            ax.set_ylabel("Mean elementary score")
            ax.legend(fontsize=7, frameon=False)
            _style_axes(ax)
            caption = (
                f"Murphy diagnostic curves for the benchmark suite ({tail_side}) use "
                "the artifact's common threshold grid and common sample. The curves "
                "are descriptive forecast-evaluation diagnostics and are not pairwise "
                "dominance claims."
            )
            entries.extend(
                _save_figure(
                    fig,
                    run_dir=run_dir,
                    figure_dir=figure_dir,
                    name=f"{prefix}_{tail_side}",
                    source_artifacts=[source],
                    tail_side=tail_side,
                    caption=caption,
                    claim_scope=claim_scope,
                )
            )
    return entries


def _lgbm_24check_murphy_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _lgbm_24check_murphy_frame(run_dir)
    if frame.is_empty():
        return []
    artifact_path = run_dir / "metrics" / "lgbm_24check_murphy.parquet"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(artifact_path)
    entries: list[dict[str, object]] = []
    required = {"tail_side", "threshold_value", "mean_elementary_score", "curve_label"}
    if not required.issubset(frame.columns):
        return []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        fig, ax = plt.subplots(figsize=(10.4, 6.2))
        for key, group in side.group_by("curve_label", maintain_order=True):
            label = str(key[0] if isinstance(key, tuple) else key)
            curve = group.sort("threshold_value")
            ax.plot(
                curve["threshold_value"].to_list(),
                curve["mean_elementary_score"].to_list(),
                linewidth=1.35,
                label=_short_label(label, max_len=48),
            )
        ax.set_title(
            f"LightGBM Murphy diagnostics after coverage screening ({_label_tail_side(tail_side)})"
        )
        ax.set_xlabel("Elementary-score threshold")
        ax.set_ylabel("Mean elementary score")
        ax.legend(fontsize=6.5, frameon=False, ncol=1)
        _style_axes(ax)
        caption = (
            f"Murphy diagnostic curves for {tail_side} restricted to LightGBM specifications "
            "that pass the full eight-scenario VaR coverage screen. Each curve is a "
            "model-by-information-set pair on the shared screen-qualified sample grid; "
            "the diagnostic is descriptive and not a pairwise dominance claim."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"lgbm_24check_murphy_{tail_side}",
                source_artifacts=[
                    "metrics/lgbm_24check_murphy.parquet",
                    "metrics/ml_tail_metrics_per_model.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=caption,
                claim_scope="murphy_diagnostic_lgbm_24check_robust_ladder",
            )
        )
    return entries


def _lgbm_24check_murphy_frame(run_dir: Path) -> pl.DataFrame:
    metrics = _read_optional_parquet(run_dir / "metrics" / "ml_tail_metrics_per_model.parquet")
    forecasts = _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    robust_models = _coverage_robust_model_names(metrics)
    required = {"model_name", "information_set", "tail_side"}
    if forecasts.is_empty() or not robust_models or not required.issubset(forecasts.columns):
        return pl.DataFrame()
    filtered = forecasts.filter(
        pl.col("model_name").is_in(list(robust_models))
        & pl.col("information_set").is_in(list(INFORMATION_LADDER_ORDER))
    )
    if filtered.is_empty():
        return pl.DataFrame()
    rows = build_murphy_records(filtered.to_dicts(), suite="lgbm_24check")
    if not rows:
        return pl.DataFrame()
    frame = pl.DataFrame(rows).with_columns(
        (
            pl.col("model_name").map_elements(display_model_label, return_dtype=pl.Utf8)
            + pl.lit(" / ")
            + pl.col("information_set").map_elements(
                display_information_set_label,
                return_dtype=pl.Utf8,
            )
        ).alias("curve_label"),
        pl.col("model_name")
        .map_elements(lambda value: _coverage_robust_model_order(value), return_dtype=pl.Int64)
        .alias("_model_order"),
        pl.col("information_set")
        .map_elements(lambda value: _information_order(value), return_dtype=pl.Int64)
        .alias("_information_order"),
    )
    return frame.sort(["tail_side", "_model_order", "_information_order", "threshold_index"]).drop(
        ["_model_order", "_information_order"]
    )


def _severity_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    metrics = _combined_severity_metrics(run_dir)
    rows = _severity_rows(metrics) if not metrics.is_empty() else []
    if not rows:
        return []
    frame = pl.DataFrame(rows)
    if "tail_side" not in frame.columns:
        frame = frame.with_columns(pl.lit(PRIMARY_TAIL_SIDE).alias("tail_side"))
    entries: list[dict[str, object]] = []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        if side.is_empty() or "mean_exceedance_severity" not in side.columns:
            continue
        side = _limit_rows_for_plot(
            side.sort(["suite", "model_name", "information_set"]),
            max_rows=28,
        )
        labels = [
            f"{display_suite_group_label(row.get('suite'))} | "
            f"{display_model_label(row.get('model_name'))} | "
            f"{display_information_set_label(row.get('information_set'))}"
            for row in side.iter_rows(named=True)
        ]
        values = [
            float(row["mean_exceedance_severity"])
            if _optional_float(row.get("mean_exceedance_severity")) is not None
            else 0.0
            for row in side.iter_rows(named=True)
        ]
        fig, ax = plt.subplots(figsize=(11, max(5, len(labels) * 0.34)))
        ax.barh(labels, values, color="#7c3aed", alpha=0.84)
        ax.set_xlabel("Mean exceedance severity")
        ax.set_title(f"ES severity diagnostics ({_label_tail_side(tail_side)})")
        _style_axes(ax)
        caption = (
            f"Expected-shortfall severity diagnostic for {tail_side}; values are "
            "conditional on VaR exceptions. This is a severity diagnostic, not a "
            "model-win claim."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"es_severity_{tail_side}",
                source_artifacts=[
                    "metrics/benchmark_metrics.parquet",
                    "metrics/ml_tail_metrics.parquet",
                    "metrics/ml_tail_metrics_per_model.parquet",
                ],
                tail_side=tail_side,
                caption=caption,
                claim_scope="es_severity_diagnostic_not_model_selection_claim",
            )
        )
    return entries


def _stress_overlay_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    forecasts = _stress_overlay_forecasts(run_dir)
    if forecasts.is_empty():
        return []
    entries: list[dict[str, object]] = []
    windows = _stress_overlay_windows(forecasts)
    for window in windows:
        fig, axes = plt.subplots(2, 1, figsize=(11.2, 7.8), sharex=True, sharey=True)
        for index, tail_side in enumerate((TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)):
            ax = axes[index]
            side = forecasts.filter(pl.col("tail_side") == tail_side)
            window_rows = _filter_date_window(side, window["start"], window["end"])
            _plot_stress_overlay_panel(
                ax,
                window_rows,
                tail_side,
                window,
                show_x_label=index == 1,
            )
        fig.suptitle(f"VaR and ES paths during the {window['title']}")
        _add_stress_overlay_shared_legend(fig)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"var_es_stress_overlay_{window['slug']}",
                source_artifacts=[
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side="left_right_tail",
                caption=(
                    "Stress-episode VaR and ES paths for downside and upside exposure on "
                    "a shared date axis. The LightGBM lines use information set C "
                    "(Japan + U.S.-close core + Japan proxy), matching the best FZ rows within "
                    "the two mean/scale LightGBM-EVT specifications that satisfy the "
                    "coverage screen. The figure is illustrative and "
                    "does not report hedge PnL, transaction costs, or trading performance."
                ),
                claim_scope="appendix_stress_overlay_illustration_not_validation",
                tight_layout_rect=(0.0, 0.11, 1.0, 0.95),
            )
        )
    return entries


def _full_sample_var_overlay_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    forecasts = _full_sample_var_overlay_forecasts(run_dir)
    if forecasts.is_empty():
        return []
    entries: list[dict[str, object]] = []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        side = forecasts.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        fig, ax = plt.subplots(figsize=(12.4, 5.2))
        _plot_full_sample_var_overlay_panel(ax, side, tail_side)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"full_sample_var_overlay_{tail_side}",
                source_artifacts=[
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=(
                    f"Out-of-sample VaR paths for {_label_tail_side(tail_side)}. "
                    "The fixed post-screen "
                    "comparison set contains GJR-GARCH-EVT and the two standard-filter "
                    "LightGBM-EVT specifications under information set C. After each LightGBM "
                    "model's first valid forecast, a missing display value is the mean of "
                    "its previous displayed VaR and the same-day GJR-GARCH-EVT VaR. "
                    "Open markers on the realized-loss path identify exceedances of the "
                    "displayed threshold. Carried values and their visual exceedances do not "
                    "enter formal coverage, loss, or DM calculations. The figure "
                    "is a visual diagnostic; formal comparison uses the strict common-sample "
                    "FZ DM analysis."
                ),
                claim_scope="full_sample_var_overlay_coverage_admissible_set_diagnostic",
            )
        )
    return entries


def _dm_heatmap_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    loss_rows = _cross_suite_dm_loss_rows(run_dir)
    if loss_rows.is_empty():
        return []
    entries: list[dict[str, object]] = []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        records = _cross_suite_dm_records(loss_rows, tail_side)
        if not records:
            continue
        labels = [spec[0] for spec in CROSS_SUITE_DM_MODEL_SPECS]
        common_n = int(records[0].get("common_n") or 0)
        values = np.full((len(labels), len(labels)), np.nan)
        for record in records:
            i = labels.index(str(record["candidate_label"]))
            j = labels.index(str(record["anchor_label"]))
            value = _optional_float(record.get("mean_fz_loss_diff_candidate_minus_anchor"))
            values[i, j] = value if value is not None else np.nan
        finite_values = values[np.isfinite(values)]
        scale = float(np.nanmax(np.abs(finite_values))) if finite_values.size else 1.0
        scale = max(scale, 1e-9)
        cmap = plt.get_cmap("RdBu_r").copy()
        cmap.set_bad("#f3f4f6")
        norm = matplotlib.colors.TwoSlopeNorm(vmin=-scale, vcenter=0.0, vmax=scale)
        fig, ax = plt.subplots(figsize=(8.4, 6.4))
        image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="equal")
        cbar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.035)
        cbar.set_label("Mean FZ difference (candidate - anchor)")
        ax.set_xticks(np.arange(len(labels)), labels, rotation=25, ha="right")
        ax.set_yticks(np.arange(len(labels)), labels)
        ax.set_xticks(np.arange(-0.5, len(labels), 1.0), minor=True)
        ax.set_yticks(np.arange(-0.5, len(labels), 1.0), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.8)
        ax.tick_params(which="minor", bottom=False, left=False)
        record_by_pair = {
            (str(record["candidate_label"]), str(record["anchor_label"])): record
            for record in records
        }
        for i, candidate_label in enumerate(labels):
            for j, anchor_label in enumerate(labels):
                if i == j:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=13, color="#6b7280")
                    continue
                record = record_by_pair.get((candidate_label, anchor_label))
                text = _dm_heatmap_annotation(record)
                value = values[i, j]
                color = "white" if np.isfinite(value) and abs(value) > 0.55 * scale else "#111827"
                ax.text(j, i, text, ha="center", va="center", fontsize=7.6, color=color)
        ax.set_title(
            f"Pairwise FZ DM heatmap ({_label_tail_side(tail_side)})\n"
            f"Strict global common sample N={common_n}",
            fontsize=11.2,
            pad=14,
        )
        ax.set_xlabel("Anchor model")
        ax.set_ylabel("Candidate model")
        for spine in ax.spines.values():
            spine.set_visible(False)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"dm_heatmap_{tail_side}",
                source_artifacts=[
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=(
                    f"Post-screen pairwise FZ DM heatmap for {_label_tail_side(tail_side)}. "
                    "Rows are candidate models and columns are anchors. All cells use "
                    f"the same strict global common sample (N={common_n}) formed by "
                    "intersecting valid forecast dates for GJR-GARCH-EVT and the two "
                    "mean/scale LightGBM-EVT specifications under information set C. "
                    "Mean differences are in units of the "
                    "Fissler-Ziegel joint VaR-ES loss; FZ scores may be negative under "
                    "this scoring convention, and lower values mean better joint "
                    "VaR-ES forecasts. Negative candidate-minus-anchor values favor "
                    "the row model."
                ),
                claim_scope="post_24check_cross_suite_fz_dm_diagnostic",
            )
        )
    return entries


def _dm_heatmap_annotation(record: dict[str, object] | None) -> str:
    if record is None:
        return "n/a"
    diff = _optional_float(record.get("mean_fz_loss_diff_candidate_minus_anchor"))
    pvalue = _optional_float(record.get("pvalue_one_sided"))
    if diff is None:
        return f"n/a\nN={int(record.get('common_n') or 0)}"
    pvalue_text = "p=n/a" if pvalue is None else f"p={pvalue:.3f}{_pvalue_stars(pvalue)}"
    return f"ΔFZ={_format_dm_diff(diff)}\n{pvalue_text}"


def _format_dm_diff(value: float) -> str:
    return f"{value:.4f}" if abs(value) < 0.01 else f"{value:.3f}"


def _pvalue_stars(pvalue: float) -> str:
    if pvalue < 0.01:
        return "***"
    if pvalue < 0.05:
        return "**"
    if pvalue < 0.10:
        return "*"
    return ""


def _tail_threshold(values: object, probability: float = 0.90) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    finite = finite[finite > 0.0]
    if finite.size == 0:
        return 0.0
    return float(np.quantile(finite, probability))


def _information_order(value: object) -> int:
    text = "" if value is None else str(value)
    try:
        return INFORMATION_LADDER_ORDER.index(text)
    except ValueError:
        return len(INFORMATION_LADDER_ORDER) + 1


def _all_loss_rows(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for path in (
        run_dir / "metrics" / "benchmark_loss_matrix.parquet",
        run_dir / "metrics" / "ml_tail_loss_matrix.parquet",
    ):
        frame = _read_optional_parquet(path)
        if not frame.is_empty():
            frames.append(frame)
    forecast_losses = _loss_rows_from_forecasts(run_dir)
    if not forecast_losses.is_empty():
        frames.append(forecast_losses)
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def _loss_rows_from_forecasts(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    specs = (
        (run_dir / "forecasts" / "benchmark_forecasts.parquet", "benchmark"),
        (run_dir / "forecasts" / "ml_tail_forecasts.parquet", "ml_tail"),
    )
    required = {
        "forecast_date",
        "tail_side",
        "model_name",
        "realized_loss",
        "var_forecast",
        "tail_level",
    }
    for path, suite in specs:
        frame = _read_optional_parquet(path)
        if frame.is_empty() or not required.issubset(frame.columns):
            continue
        frame = _valid_forecast_rows(frame)
        rows = []
        for row in frame.iter_rows(named=True):
            loss = _optional_float(row.get("realized_loss"))
            var = _optional_float(row.get("var_forecast"))
            tail_level = _optional_float(row.get("tail_level"))
            if loss is None or var is None or tail_level is None:
                continue
            es = _optional_float(row.get("es_forecast"))
            rows.append(
                {
                    **row,
                    "suite": suite,
                    "quantile_loss": quantile_loss(loss, var, tail_level),
                    "fz_loss": fz_loss(loss, var, es, tail_level) if es is not None else None,
                }
            )
        if rows:
            frames.append(pl.from_dicts(rows, infer_schema_length=None))
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def _valid_forecast_rows(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    filtered = frame
    if "fit_status" in filtered.columns:
        filtered = filtered.filter(pl.col("fit_status") == "ok")
    if "is_valid_forecast" in filtered.columns:
        filtered = filtered.filter(pl.col("is_valid_forecast") == True)  # noqa: E712
    return filtered


def _lgbm_a_anchor_cumulative_loss_pairs(
    loss_frame: pl.DataFrame, tail_side: str, model_name: str
) -> list[tuple[str, pl.DataFrame]]:
    pairs: list[tuple[str, pl.DataFrame]] = []
    anchor = _loss_identity(
        suite="ml_tail",
        model_name=model_name,
        information_set=INFORMATION_INCREMENT_ANCHOR_SET,
    )
    benchmark_pair = _paired_cumulative_loss(
        loss_frame,
        tail_side=tail_side,
        anchor=anchor,
        candidate=_loss_identity(
            suite="benchmark",
            model_name=BENCHMARK_STRESS_PRIMARY_MODEL,
            information_set="target_history_only",
        ),
    )
    if not benchmark_pair.is_empty():
        pairs.append(("GJR-GARCH-EVT vs A", benchmark_pair))
    for information_set in INFORMATION_INCREMENT_CANDIDATE_SETS:
        pair = _paired_cumulative_loss(
            loss_frame,
            tail_side=tail_side,
            anchor=anchor,
            candidate=_loss_identity(
                suite="ml_tail",
                model_name=model_name,
                information_set=information_set,
            ),
        )
        if not pair.is_empty():
            pairs.append((f"{_information_set_stage_label(information_set)} vs A", pair))
    return pairs


def _information_set_stage_label(value: object) -> str:
    text = "" if value is None else str(value)
    labels = {
        "japan_only": "Set A",
        "japan_only_plus_us_close_core": "Set B",
        "japan_only_plus_us_close_core_plus_japan_proxy": "Set C",
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy": "Set D",
    }
    return labels.get(text, display_information_set_label(text))


def _loss_identity(*, suite: str, model_name: str, information_set: str) -> dict[str, str]:
    return {"suite": suite, "model_name": model_name, "information_set": information_set}


def _paired_cumulative_loss(
    frame: pl.DataFrame,
    *,
    tail_side: str,
    anchor: Mapping[str, str],
    candidate: Mapping[str, str],
) -> pl.DataFrame:
    required = {"forecast_date", "suite", "tail_side", "model_name", "information_set", "fz_loss"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return pl.DataFrame()
    anchor_rows = _select_loss_identity(frame, tail_side=tail_side, identity=anchor).select(
        ["forecast_date", "fz_loss"]
    )
    candidate_rows = _select_loss_identity(frame, tail_side=tail_side, identity=candidate).select(
        ["forecast_date", "fz_loss"]
    )
    if anchor_rows.is_empty() or candidate_rows.is_empty():
        return pl.DataFrame()
    joined = anchor_rows.join(candidate_rows, on="forecast_date", how="inner", suffix="_candidate")
    if joined.is_empty():
        return pl.DataFrame()
    joined = joined.rename({"fz_loss": "anchor_loss", "fz_loss_candidate": "candidate_loss"})
    joined = joined.filter(
        pl.col("anchor_loss").is_not_null() & pl.col("candidate_loss").is_not_null()
    )
    if joined.is_empty():
        return pl.DataFrame()
    return (
        joined.with_columns((pl.col("anchor_loss") - pl.col("candidate_loss")).alias("gain"))
        .sort("forecast_date")
        .with_columns(pl.col("gain").cum_sum().alias("cumulative_gain"))
    )


def _plot_date_values(values: list[object]) -> list[date]:
    dates: list[date] = []
    for value in values:
        if isinstance(value, date):
            dates.append(value)
        else:
            dates.append(date.fromisoformat(str(value)[:10]))
    return dates


def _set_monthly_date_ticks(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=60, labelsize=6)


def _select_loss_identity(
    frame: pl.DataFrame,
    *,
    tail_side: str,
    identity: Mapping[str, str],
) -> pl.DataFrame:
    selected = frame.filter(
        (pl.col("tail_side") == tail_side)
        & (pl.col("suite") == identity["suite"])
        & (pl.col("model_name") == identity["model_name"])
    )
    if "information_set" in selected.columns:
        selected = selected.filter(pl.col("information_set") == identity["information_set"])
    if "forecast_date" in selected.columns:
        selected = selected.unique(subset=["forecast_date"], keep="first")
    return selected


def _stress_overlay_forecasts(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark = _read_optional_parquet(run_dir / "forecasts" / "benchmark_forecasts.parquet")
    if not benchmark.is_empty():
        rows = []
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            selected = _metric_forecast_for_model(
                benchmark,
                tail_side=tail_side,
                model_names=(BENCHMARK_STRESS_PRIMARY_MODEL, BENCHMARK_STRESS_FALLBACK_MODEL),
            )
            if not selected.is_empty():
                rows.append(
                    selected.with_columns(
                        pl.lit(_stress_benchmark_label(selected)).alias("plot_group"),
                        pl.lit(0).alias("plot_order"),
                    )
                )
        frames.extend(rows)
    ml_tail = _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    if not ml_tail.is_empty():
        rows = []
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            for order, model_name in enumerate(LGBM_24CHECK_CUMULATIVE_MODELS, start=1):
                model_rows = _metric_forecast_for_identity(
                    ml_tail,
                    tail_side=tail_side,
                    model_name=model_name,
                    information_set=STRESS_OVERLAY_INFORMATION_SET,
                )
                if not model_rows.is_empty():
                    rows.append(
                        model_rows.with_columns(
                            pl.lit(_stress_lgbm_label(model_name)).alias("plot_group"),
                            pl.lit(order).alias("plot_order"),
                        )
                    )
        frames.extend(rows)
    if not frames:
        return pl.DataFrame()
    return pl.concat([_valid_forecast_rows(frame) for frame in frames], how="diagonal_relaxed")


def _stress_benchmark_label(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "model_name" not in frame.columns:
        return "Benchmark comparator"
    model_name = str(frame["model_name"][0])
    if model_name == BENCHMARK_STRESS_PRIMARY_MODEL:
        return "GJR-GARCH-EVT"
    if model_name == BENCHMARK_STRESS_FALLBACK_MODEL:
        return "GJR-GARCH-t fallback"
    return display_model_label(model_name)


def _stress_lgbm_label(model_name: str) -> str:
    labels = {
        ML_TAIL_POT_GPD_PLAIN_MLE_MODEL: LGBM_STANDARD_PLAIN_MLE_C_LABEL,
        ML_TAIL_POT_GPD_UNIBM_MODEL: LGBM_STANDARD_UNIBM_C_LABEL,
    }
    return labels.get(model_name, f"{display_model_label(model_name)} (C)")


def _full_sample_var_overlay_forecasts(run_dir: Path) -> pl.DataFrame:
    sources = {
        "benchmark": _read_optional_parquet(run_dir / "forecasts" / "benchmark_forecasts.parquet"),
        "ml_tail": _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet"),
    }
    frames: list[pl.DataFrame] = []
    for order, (label, suite, model_name, information_set) in enumerate(CROSS_SUITE_DM_MODEL_SPECS):
        source = sources[suite]
        if source.is_empty():
            continue
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            selected = _metric_forecast_for_identity(
                source,
                tail_side=tail_side,
                model_name=model_name,
                information_set=information_set,
            )
            if not selected.is_empty():
                frames.append(
                    selected.with_columns(
                        pl.lit(label).alias("plot_group"),
                        pl.lit(order).alias("plot_order"),
                    )
                )
    if not frames:
        return pl.DataFrame()
    return pl.concat([_valid_forecast_rows(frame) for frame in frames], how="diagonal_relaxed")


def _metric_forecast_for_model(
    frame: pl.DataFrame,
    *,
    tail_side: str,
    model_names: tuple[str, ...],
) -> pl.DataFrame:
    for model_name in model_names:
        selected = frame.filter(
            (pl.col("tail_side") == tail_side) & (pl.col("model_name") == model_name)
        )
        if not selected.is_empty():
            return selected
    return pl.DataFrame()


def _metric_forecast_for_identity(
    frame: pl.DataFrame,
    *,
    tail_side: str,
    model_name: str,
    information_set: str,
) -> pl.DataFrame:
    required = {"tail_side", "model_name", "information_set"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return pl.DataFrame()
    return frame.filter(
        (pl.col("tail_side") == tail_side)
        & (pl.col("model_name") == model_name)
        & (pl.col("information_set") == information_set)
    )


def _stress_overlay_windows(side: pl.DataFrame) -> list[dict[str, object]]:
    candidate_dates: list[date] = []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        tail_frame = side.filter(pl.col("tail_side") == tail_side)
        candidate_dates.extend(
            _top_non_overlapping_loss_dates(
                tail_frame,
                max_windows=STRESS_OVERLAY_MAX_WINDOWS,
                half_width_days=STRESS_OVERLAY_WINDOW_HALF_WIDTH_DAYS,
            )
        )
    return _stress_episode_windows(candidate_dates)


def _stress_episode_windows(candidate_dates: list[date]) -> list[dict[str, object]]:
    if not candidate_dates:
        return []
    clusters: list[list[date]] = []
    for candidate in sorted(set(candidate_dates)):
        if (
            not clusters
            or (candidate - clusters[-1][-1]).days > STRESS_OVERLAY_EPISODE_CLUSTER_DAYS
        ):
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)
    windows: list[dict[str, object]] = []
    for cluster in clusters:
        start = min(cluster) - timedelta(days=STRESS_OVERLAY_WINDOW_HALF_WIDTH_DAYS)
        end = max(cluster) + timedelta(days=STRESS_OVERLAY_WINDOW_HALF_WIDTH_DAYS)
        year = min(cluster).year if len({item.year for item in cluster}) == 1 else start.year
        windows.append(
            {
                "slug": f"{year}_stress_episode",
                "title": f"{year} out-of-sample stress episode",
                "start": start,
                "end": end,
                "centers": tuple(cluster),
            }
        )
    return windows[:STRESS_OVERLAY_MAX_WINDOWS]


def _max_loss_date(frame: pl.DataFrame) -> date | None:
    if (
        frame.is_empty()
        or "realized_loss" not in frame.columns
        or "forecast_date" not in frame.columns
    ):
        return None
    unique = frame.select(["forecast_date", "realized_loss"]).unique()
    if unique.is_empty():
        return None
    row = unique.sort("realized_loss", descending=True).row(0, named=True)
    return _date_from_iso(row.get("forecast_date"))


def _top_non_overlapping_loss_dates(
    frame: pl.DataFrame,
    *,
    max_windows: int,
    half_width_days: int,
) -> list[date]:
    if (
        frame.is_empty()
        or "realized_loss" not in frame.columns
        or "forecast_date" not in frame.columns
    ):
        return []
    unique = (
        frame.select(["forecast_date", "realized_loss"])
        .unique()
        .sort("realized_loss", descending=True)
    )
    selected: list[date] = []
    min_gap_days = half_width_days * 2
    for row in unique.iter_rows(named=True):
        candidate = _date_from_iso(row.get("forecast_date"))
        if candidate is None:
            continue
        if any(abs((candidate - existing).days) <= min_gap_days for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_windows:
            break
    return selected


def _filter_date_window(frame: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    if frame.is_empty() or "forecast_date" not in frame.columns:
        return pl.DataFrame()
    return frame.filter(
        (pl.col("forecast_date") >= start.isoformat())
        & (pl.col("forecast_date") <= end.isoformat())
    )


def _plot_stress_overlay_panel(
    ax: object,
    frame: pl.DataFrame,
    tail_side: str,
    window: Mapping[str, object],
    *,
    show_x_label: bool,
) -> None:
    ax.set_title(_label_tail_side(tail_side))
    if frame.is_empty():
        ax.text(
            0.5,
            0.5,
            "Window outside the available out-of-sample forecast period",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="#6b7280",
        )
        _style_axes(ax)
        return
    realized = frame.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
    dates = _plot_date_values(realized["forecast_date"].to_list())
    ax.plot(
        dates,
        realized["realized_loss"].to_list(),
        color=STRESS_OVERLAY_REALIZED_COLOR,
        linewidth=1.2,
        label="realized loss",
    )
    for group, group_frame in frame.group_by("plot_group", maintain_order=True):
        label = str(group[0] if isinstance(group, tuple) else group)
        series = group_frame.sort("forecast_date")
        color = STRESS_OVERLAY_COLORS.get(label, "#64748b")
        series_dates = _plot_date_values(series["forecast_date"].to_list())
        ax.plot(
            series_dates,
            series["var_forecast"].to_list(),
            color=color,
            linewidth=1.7,
            label=f"{label} VaR",
        )
        if "es_forecast" in series.columns and series["es_forecast"].drop_nulls().len() > 0:
            ax.plot(
                series_dates,
                series["es_forecast"].to_list(),
                color=color,
                linewidth=1.4,
                linestyle="--",
                alpha=0.86,
                label=f"{label} ES",
            )
        breaches = (
            series.filter(pl.col("var_breach").fill_null(False))
            if "var_breach" in series.columns
            else pl.DataFrame()
        )
        if not breaches.is_empty():
            breach_points = (
                breaches.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
            )
            ax.scatter(
                _plot_date_values(breach_points["forecast_date"].to_list()),
                breach_points["realized_loss"].to_list(),
                s=42,
                marker=STRESS_OVERLAY_MARKERS.get(label, "o"),
                color=color,
                edgecolors="white",
                linewidths=0.8,
                label=f"{label} breach",
                zorder=5,
            )
    ax.axhline(0.0, color="#9ca3af", linewidth=0.8, linestyle=":")
    ax.set_ylabel("Realized loss\n(positive = adverse)")
    ax.set_xlabel("Forecast date" if show_x_label else "")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.tick_params(axis="x", rotation=0)
    _style_axes(ax)


def _add_stress_overlay_shared_legend(fig: object) -> None:
    handles = [
        Line2D(
            [0],
            [0],
            color=STRESS_OVERLAY_REALIZED_COLOR,
            linewidth=1.4,
            label="realized loss",
        ),
        Line2D(
            [0],
            [0],
            color=STRESS_OVERLAY_COLORS["GJR-GARCH-EVT"],
            linewidth=2.0,
            label="GJR-GARCH-EVT",
        ),
        Line2D(
            [0],
            [0],
            color=STRESS_OVERLAY_COLORS[LGBM_STANDARD_PLAIN_MLE_C_LABEL],
            linewidth=2.0,
            label=LGBM_STANDARD_PLAIN_MLE_C_LABEL,
        ),
        Line2D(
            [0],
            [0],
            color=STRESS_OVERLAY_COLORS[LGBM_STANDARD_UNIBM_C_LABEL],
            linewidth=2.0,
            label=LGBM_STANDARD_UNIBM_C_LABEL,
        ),
        Line2D([0], [0], color="#374151", linewidth=1.5, label="solid = VaR"),
        Line2D(
            [0],
            [0],
            color="#374151",
            linewidth=1.5,
            linestyle="--",
            label="dashed = ES",
        ),
        Line2D(
            [0],
            [0],
            color="#374151",
            marker="o",
            linestyle="None",
            markerfacecolor="#374151",
            markeredgecolor="white",
            markersize=6,
            label="marker = VaR breach",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
        ncol=4,
        frameon=False,
        fontsize=7.5,
        handlelength=2.2,
        columnspacing=1.3,
    )


def _plot_full_sample_var_overlay_panel(
    ax: object,
    frame: pl.DataFrame,
    tail_side: str,
) -> None:
    realized = frame.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
    realized_dates = _plot_date_values(realized["forecast_date"].to_list())
    ax.plot(
        realized_dates,
        realized["realized_loss"].to_list(),
        color="#111827",
        linewidth=0.95,
        alpha=0.78,
        label="realized loss",
    )
    gjr_values = (
        realized.join(
            frame.filter(pl.col("plot_group") == "GJR-GARCH-EVT")
            .select(["forecast_date", "var_forecast"])
            .sort("forecast_date")
            .unique(subset=["forecast_date"], keep="first"),
            on="forecast_date",
            how="left",
        )
        .sort("forecast_date")["var_forecast"]
        .fill_null(strategy="forward")
        .to_list()
    )
    for marker_order, (group, group_frame) in enumerate(
        frame.sort("plot_order").group_by("plot_group", maintain_order=True)
    ):
        label = str(group[0] if isinstance(group, tuple) else group)
        series = realized.join(
            group_frame.select(["forecast_date", "var_forecast"])
            .sort("forecast_date")
            .unique(subset=["forecast_date"], keep="first"),
            on="forecast_date",
            how="left",
        ).sort("forecast_date")
        display_values = (
            series["var_forecast"].fill_null(strategy="forward").to_list()
            if label == "GJR-GARCH-EVT"
            else _lgbm_overlay_var_values(series["var_forecast"].to_list(), gjr_values)
        )
        series = series.with_columns(pl.Series("var_forecast", display_values)).filter(
            pl.col("var_forecast").is_not_null()
        )
        ax.plot(
            _plot_date_values(series["forecast_date"].to_list()),
            series["var_forecast"].to_list(),
            color=FULL_SAMPLE_OVERLAY_COLORS.get(label, "#64748b"),
            linewidth=1.35,
            label=f"{label} VaR",
        )
        breaches = series.filter(pl.col("realized_loss") > pl.col("var_forecast"))
        if not breaches.is_empty():
            breach_points = (
                breaches.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
            )
            ax.scatter(
                _plot_date_values(breach_points["forecast_date"].to_list()),
                breach_points["realized_loss"].to_list(),
                s=30 + 12 * marker_order,
                facecolors="none",
                edgecolors=FULL_SAMPLE_OVERLAY_COLORS.get(label, "#64748b"),
                marker=FULL_SAMPLE_OVERLAY_MARKERS.get(label, "o"),
                linewidths=1.15,
                label=f"{label} breach",
                zorder=5,
            )
    ax.axhline(0.0, color="#111827", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.set_title(f"Out-of-sample VaR paths ({_label_tail_side(tail_side)})")
    ax.set_ylabel("Realized loss and VaR")
    ax.set_xlabel("Forecast date")
    _set_monthly_date_ticks(ax)
    ax.legend(frameon=False, fontsize=7, ncol=3)
    _style_axes(ax)


def _lgbm_overlay_var_values(
    raw_values: list[object],
    gjr_values: list[object],
) -> list[float | None]:
    displayed: list[float | None] = []
    previous: float | None = None
    for raw_value, gjr_value in zip(raw_values, gjr_values, strict=True):
        value = _optional_float(raw_value)
        if value is None and previous is not None:
            gjr_var = _optional_float(gjr_value)
            value = (previous + gjr_var) / 2.0 if gjr_var is not None else previous
        displayed.append(value)
        if value is not None:
            previous = value
    return displayed


def _ordered_unique(values: list[object]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text not in output:
            output.append(text)
    return output


def _entity_label(value: object) -> str:
    text = str(value)
    if text in INFORMATION_LADDER_ORDER:
        return display_information_set_label(text)
    return display_model_label(text)


def _date_from_iso(value: object) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _combined_severity_metrics(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "metrics" / "benchmark_metrics.parquet"
    if benchmark_path.exists():
        frames.append(
            pl.read_parquet(benchmark_path).with_columns(
                pl.lit("benchmark_baseline").alias("suite"),
                pl.lit("primary_benchmark_baseline").alias("claim_scope"),
            )
        )
    ml_primary_path = run_dir / "metrics" / "ml_tail_metrics.parquet"
    if ml_primary_path.exists():
        frames.append(
            pl.read_parquet(ml_primary_path).with_columns(
                pl.lit("ml_tail_primary").alias("suite"),
                pl.lit("primary_nested_information_sets").alias("claim_scope"),
            )
        )
    ml_per_model_path = run_dir / "metrics" / "ml_tail_metrics_per_model.parquet"
    if ml_per_model_path.exists():
        per_model = pl.read_parquet(ml_per_model_path)
        if "model_name" in per_model.columns:
            per_model = per_model.filter(pl.col("model_name") != ML_TAIL_DIRECT_QUANTILE_MODEL)
        if not per_model.is_empty():
            frames.append(
                per_model.with_columns(
                    pl.lit("ml_tail_restricted_family").alias("suite"),
                    pl.lit("restricted_diagnostic").alias("claim_scope"),
                )
            )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _combined_forecasts(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "forecasts" / "benchmark_forecasts.parquet"
    if benchmark_path.exists():
        benchmark = pl.read_parquet(benchmark_path)
        if "model_name" in benchmark.columns:
            benchmark = benchmark.filter(
                pl.col("model_name").is_in(list(BENCHMARK_BASELINE_MODEL_NAMES))
            )
        if not benchmark.is_empty():
            frames.append(benchmark.with_columns(pl.lit("benchmark_baseline").alias("suite")))
    ml_tail_path = run_dir / "forecasts" / "ml_tail_forecasts.parquet"
    if ml_tail_path.exists():
        ml_tail = pl.read_parquet(ml_tail_path)
        if "model_name" in ml_tail.columns:
            ml_tail = ml_tail.filter(pl.col("model_name") == ML_TAIL_DIRECT_QUANTILE_MODEL)
        if not ml_tail.is_empty():
            frames.append(ml_tail.with_columns(pl.lit("ml_tail_primary").alias("suite")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _limit_rows_for_plot(frame: pl.DataFrame, *, max_rows: int) -> pl.DataFrame:
    if frame.height <= max_rows:
        return frame
    return frame.head(max_rows)


def _save_figure(
    fig: object,
    *,
    run_dir: Path,
    figure_dir: Path,
    name: str,
    source_artifacts: list[str],
    tail_side: str,
    caption: str,
    claim_scope: str,
    tight_layout_rect: tuple[float, float, float, float] | None = None,
) -> list[dict[str, object]]:
    fig.tight_layout(rect=tight_layout_rect)
    entries: list[dict[str, object]] = []
    for fmt in ("png", "pdf"):
        output = figure_dir / f"{name}.{fmt}"
        save_kwargs = {"bbox_inches": "tight"}
        if fmt == "png":
            save_kwargs["dpi"] = 200
        fig.savefig(output, **save_kwargs)
        entries.append(
            {
                "name": name,
                "path": output.relative_to(run_dir).as_posix(),
                "format": fmt,
                "source_artifacts": source_artifacts,
                "tail_side": tail_side,
                "caption": caption,
                "claim_scope": claim_scope,
            }
        )
    plt.close(fig)
    return entries


def _read_optional_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:
        return pl.DataFrame()


def _available_tail_sides(frame: pl.DataFrame) -> list[str]:
    if frame.is_empty() or "tail_side" not in frame.columns:
        return []
    sides = [str(item) for item in frame["tail_side"].drop_nulls().unique().to_list()]
    ordered = [side for side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT) if side in sides]
    return ordered + sorted(side for side in sides if side not in ordered)


def _first_float(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    for value in frame[column].to_list():
        output = _optional_float(value)
        if output is not None:
            return output
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(output):
        return None
    return output


def _series_percent(frame: pl.DataFrame, column: str) -> list[float]:
    if column not in frame.columns:
        return [0.0] * frame.height
    return [float(_optional_float(value) or 0.0) * 100.0 for value in frame[column].to_list()]


def _label_tail_side(tail_side: str) -> str:
    label = display_tail_side_label(tail_side)
    return f"{label.lower()} exposure" if label in {"Downside", "Upside"} else label


def _short_label(value: object, *, max_len: int = 42) -> str:
    text = str(value).replace("_", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _suite_color(suite_group: str) -> str:
    return {
        "benchmark": "#475569",
        "lgbm": "#2563eb",
        "benchmark_baseline": "#475569",
        "benchmark_advanced": "#0f766e",
        "ml_tail_primary": "#2563eb",
        "ml_tail_restricted_family": "#7c3aed",
    }.get(suite_group, "#64748b")


def _style_axes(ax: object) -> None:
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=8)
