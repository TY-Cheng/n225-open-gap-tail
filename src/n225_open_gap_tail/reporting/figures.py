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
from scipy.stats import genpareto

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
)
from n225_open_gap_tail.inference.core import build_murphy_records
from n225_open_gap_tail.reporting.latex import (
    PROMOTED_TAIL_MODEL_SPECS,
    _selected_model_performance_rows,
    _severity_rows,
)
from n225_open_gap_tail.metrics.stat_utils import fz_loss, quantile_loss


INFORMATION_LADDER_ORDER = (
    "japan_only",
    "japan_only_plus_us_close_core",
    "japan_only_plus_us_close_core_plus_japan_proxy",
    "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy",
)
COVERAGE_GATE_ROBUST_MODEL_ORDER = (
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_IQR_POT_GPD_UNIBM_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_MEDIAN_MAD_POT_GPD_UNIBM_MODEL,
)
COVERAGE_GATE_MIN_ROWS = 450
COVERAGE_GATE_TOLERANCE = 0.025
COVERAGE_GATE_TEST_ALPHA = 0.05
BENCHMARK_STRESS_PRIMARY_MODEL = "gjr_garch_evt"
BENCHMARK_STRESS_FALLBACK_MODEL = "gjr_garch_t"


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
    entries.extend(_target_distribution_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_coverage_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_cumulative_loss_difference_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_selected_model_performance_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_full_sample_var_overlay_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_murphy_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_lgbm_24check_murphy_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_severity_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_stress_overlay_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_dm_heatmap_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_evt_standardized_residual_figures(run_dir=run_dir, figure_dir=figure_dir))
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
        (4.70, "T\n05:00\nU.S. close\nif EDT", "#fef2f2", 0.84),
        (7.05, "T\n05:30\nOSE night\ncloses", "#eef2ff", 0.84),
        (9.40, "T\n06:00\nU.S. close\nif EST", "#fef2f2", 0.84),
        (11.75, "T\nmatched\nU.S. close\n+ data lag\ncutoff", "#fdf2f8", 1.02),
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
        "JST timing for the settlement-to-open forecast design",
        fontsize=12.5,
    )
    caption = (
        "Session-aligned forecast-origin and target-timing diagram. The U.S. cash "
        "close appears at 05:00 JST during U.S. daylight-saving time and at 06:00 "
        "JST during U.S. standard time. OSE labels show the pre-2024-11-05 hours: "
        "day close 15:15 JST, night session 16:30-05:30 JST, and next day open "
        "08:45 JST. From 2024-11-05, JPX hours are day close 15:45 JST and night "
        "session 17:00-06:00 JST; the next day open remains 08:45 JST. The model "
        "cutoff is the matched U.S. cash close plus the pre-specified data-availability "
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


def _target_tail_motivation_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _target_gap_frame(run_dir)
    if frame.is_empty():
        return []
    gap = _finite_array(frame, "gap_t")
    if gap.size < 50:
        return []
    left_loss = -gap
    right_loss = gap
    left_threshold = _tail_threshold(left_loss)
    right_threshold = _tail_threshold(right_loss)
    fig, axes = plt.subplots(1, 3, figsize=(15.2, 4.8))
    axes[0].hist(gap, bins=50, density=True, color="#64748b", alpha=0.62, label="empirical")
    _plot_normal_density(axes[0], gap)
    axes[0].axvline(0.0, color="#111827", linewidth=1.0)
    axes[0].set_title("A. Opening-gap density")
    axes[0].set_xlabel("gap_t, log return")
    axes[0].set_ylabel("Density")
    axes[0].legend(frameon=False, fontsize=7)
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
    ):
        x, survival = _survival_curve(values)
        if x.size:
            mask = survival > 0
            axes[1].semilogy(x[mask], survival[mask], label=label, color=color, linewidth=1.5)
    axes[1].set_title("B. Tail log survival")
    axes[1].set_xlabel("Positive loss magnitude")
    axes[1].set_ylabel("Empirical survival, log scale")
    axes[1].legend(frameon=False, fontsize=7)
    for label, values, threshold, color in (
        ("left loss", left_loss, left_threshold, "#dc2626"),
        ("right loss", right_loss, right_threshold, "#2563eb"),
    ):
        thresholds, mean_excess = _mean_excess_curve(values)
        if thresholds.size:
            axes[2].plot(thresholds, mean_excess, label=label, color=color, linewidth=1.5)
            axes[2].axvline(threshold, color=color, linewidth=1.0, linestyle="--")
            axes[2].text(
                threshold,
                float(np.nanmax(mean_excess)) if mean_excess.size else 0.0,
                f"u={threshold:.3f}",
                rotation=90,
                ha="right",
                va="top",
                fontsize=7,
                color=color,
            )
    axes[2].set_title("C. Mean excess")
    axes[2].set_xlabel("Threshold u")
    axes[2].set_ylabel("Mean excess over u")
    axes[2].legend(frameon=False, fontsize=7)
    for ax in axes:
        _style_axes(ax)
    fig.suptitle("Opening-gap distribution and raw-tail diagnostics", fontsize=12)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name="target_tail_motivation",
        source_artifacts=["panel/modeling_panel.parquet"],
        tail_side="left_right_target_distribution",
        caption=(
            "Composite raw-target motivation figure: density versus a Gaussian "
            "reference, left/right log-survival curves, and mean-excess curves with "
            "90th-percentile positive-loss thresholds. This is raw target motivation, "
            "not forecast validation."
        ),
        claim_scope="target_distribution_motivation_not_forecast_validation",
    )


def _target_distribution_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _target_gap_frame(run_dir)
    if frame.is_empty():
        return []
    gap = _finite_array(frame, "gap_t")
    if gap.size < 50:
        return []
    left_loss = -gap
    right_loss = gap
    abs_gap = np.abs(gap)
    source_artifacts = ["panel/modeling_panel.parquet"]
    claim_scope = "target_distribution_motivation_not_forecast_validation"
    entries: list[dict[str, object]] = []

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.hist(gap, bins=55, density=True, color="#475569", alpha=0.62, label="empirical density")
    _plot_normal_density(ax, gap)
    quantile_lines = (
        (0.01, "#dc2626"),
        (0.05, "#f97316"),
        (0.95, "#2563eb"),
        (0.99, "#7c3aed"),
    )
    for probability, color in quantile_lines:
        ax.axvline(float(np.quantile(gap, probability)), color=color, linewidth=1.0, linestyle="--")
    ax.axvline(0.0, color="#111827", linewidth=1.0)
    ax.set_title("Settlement-to-open gap distribution")
    ax.set_xlabel("gap_t, log return")
    ax.set_ylabel("Density")
    ax.legend(frameon=False, fontsize=8)
    _style_axes(ax)
    entries.extend(
        _save_figure(
            fig,
            run_dir=run_dir,
            figure_dir=figure_dir,
            name="target_gap_histogram_density",
            source_artifacts=source_artifacts,
            tail_side="target_distribution",
            caption=(
                "Raw settlement-to-open gap distribution for the clean modeling sample. "
                "This target-distribution diagnostic motivates tail-risk modeling; it "
                "does not validate any LightGBM+EVT forecast."
            ),
            claim_scope=claim_scope,
        )
    )

    for tail_side, values in ((TAIL_SIDE_LEFT, left_loss), (TAIL_SIDE_RIGHT, right_loss)):
        qq = _gpd_qq_values(values, threshold_probability=0.90)
        if qq is None:
            continue
        empirical, fitted, threshold = qq
        fig, ax = plt.subplots(figsize=(6.2, 5.6))
        ax.scatter(fitted, empirical, s=18, color="#2563eb", alpha=0.78)
        max_value = max(float(np.max(empirical)), float(np.max(fitted)))
        ax.plot([0.0, max_value], [0.0, max_value], color="#111827", linewidth=1.1, linestyle="--")
        ax.set_title(f"GPD Q-Q diagnostic ({_label_tail_side(tail_side)})")
        ax.set_xlabel("Fitted GPD excess quantile")
        ax.set_ylabel("Empirical excess quantile")
        ax.text(
            0.02,
            0.96,
            f"threshold = {threshold:.4f}",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
            color="#374151",
        )
        _style_axes(ax)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"target_loss_qq_{tail_side}",
                source_artifacts=source_artifacts,
                tail_side=tail_side,
                caption=(
                    f"Raw {tail_side} loss Q-Q diagnostic for excesses above the 90th "
                    "percentile threshold. This is evidence on the target loss tail, not "
                    "forecast validation for LightGBM+EVT."
                ),
                claim_scope=claim_scope,
            )
        )

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    plotted = False
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        x, survival = _survival_curve(values)
        if x.size:
            ax.semilogy(x, survival, label=label, color=color, linewidth=1.5)
            plotted = True
    if plotted:
        ax.set_title("Log survival diagnostics")
        ax.set_xlabel("Loss magnitude")
        ax.set_ylabel("Empirical survival probability, log scale")
        ax.legend(frameon=False, fontsize=8)
        _style_axes(ax)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name="target_log_survival",
                source_artifacts=source_artifacts,
                tail_side="left_right_target_distribution",
                caption=(
                    "Empirical log survival curves for raw left loss, right loss, and absolute "
                    "settlement-to-open gap. This motivates tail-risk evaluation and is not a "
                    "forecast-performance claim."
                ),
                claim_scope=claim_scope,
            )
        )
    else:
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    plotted = False
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        thresholds, mean_excess = _mean_excess_curve(values)
        if thresholds.size:
            ax.plot(thresholds, mean_excess, label=label, color=color, linewidth=1.6)
            plotted = True
    if plotted:
        ax.set_title("Mean excess diagnostics")
        ax.set_xlabel("Threshold")
        ax.set_ylabel("Mean excess over threshold")
        ax.legend(frameon=False, fontsize=8)
        _style_axes(ax)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name="target_mean_excess",
                source_artifacts=source_artifacts,
                tail_side="left_right_target_distribution",
                caption=(
                    "Mean excess curves for raw target losses. Near-linear upper-tail patterns "
                    "are tail-shape motivation only; standardized residual-loss EVT diagnostics "
                    "remain required for LightGBM+EVT forecasts."
                ),
                claim_scope=claim_scope,
            )
        )
    else:
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    plotted = False
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        ks, xi = _hill_curve(values)
        if ks.size:
            ax.plot(ks, xi, label=label, color=color, linewidth=1.5)
            plotted = True
    if plotted:
        ax.set_title("Hill tail-index diagnostics")
        ax.set_xlabel("Number of upper order statistics, k")
        ax.set_ylabel("Hill estimate of GPD shape xi")
        ax.legend(frameon=False, fontsize=8)
        _style_axes(ax)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name="target_hill_plot",
                source_artifacts=source_artifacts,
                tail_side="left_right_target_distribution",
                caption=(
                    "Hill estimates by k for raw left loss, right loss, and absolute gap. "
                    "The plot is a raw-target tail diagnostic, not a model-comparison result."
                ),
                claim_scope=claim_scope,
            )
        )
    else:
        plt.close(fig)
    return entries


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


def _gpd_qq_values(
    values: object,
    *,
    threshold_probability: float,
) -> tuple[object, object, float] | None:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 50:
        return None
    threshold = float(np.quantile(finite, threshold_probability))
    excess = np.sort(finite[finite > threshold] - threshold)
    if excess.size < 15 or float(np.max(excess)) <= 0.0:
        return None
    try:
        shape, _, scale = genpareto.fit(excess, floc=0.0)
    except (ValueError, RuntimeError, FloatingPointError):
        return None
    if not np.isfinite(shape) or not np.isfinite(scale) or scale <= 0.0:
        return None
    probabilities = (np.arange(1, excess.size + 1) - 0.5) / excess.size
    fitted = genpareto.ppf(probabilities, c=shape, loc=0.0, scale=scale)
    return excess, fitted, threshold


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
    required = {
        "model_name",
        "tail_side",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "kupiec_pvalue",
        "christoffersen_pvalue",
    }
    if frame.is_empty() or not required.issubset(frame.columns):
        return ()
    expected_scenarios = {
        (tail_side, information_set)
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT)
        for information_set in INFORMATION_LADDER_ORDER
    }
    passed_by_model: dict[str, set[tuple[str, str]]] = {}
    for row in frame.iter_rows(named=True):
        model = str(row.get("model_name") or "")
        if model == ML_TAIL_DIRECT_QUANTILE_MODEL:
            continue
        scenario = (str(row.get("tail_side") or ""), str(row.get("information_set") or ""))
        if scenario not in expected_scenarios:
            continue
        if not _coverage_robust_row_passes(row):
            continue
        passed_by_model.setdefault(model, set()).add(scenario)
    return tuple(
        sorted(
            (
                model
                for model, scenarios in passed_by_model.items()
                if scenarios == expected_scenarios
            ),
            key=_coverage_robust_model_order,
        )
    )


def _coverage_robust_row_passes(row: Mapping[str, object]) -> bool:
    rows = int(_optional_float(row.get("rows")) or 0)
    breach = _optional_float(row.get("var_breach_rate"))
    expected = _optional_float(row.get("expected_breach_rate")) or 0.05
    kupiec = _optional_float(row.get("kupiec_pvalue"))
    christoffersen = _optional_float(row.get("christoffersen_pvalue"))
    if breach is None or kupiec is None or christoffersen is None:
        return False
    return (
        rows >= COVERAGE_GATE_MIN_ROWS
        and abs(breach - expected) <= COVERAGE_GATE_TOLERANCE
        and kupiec >= COVERAGE_GATE_TEST_ALPHA
        and christoffersen >= COVERAGE_GATE_TEST_ALPHA
    )


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
            f"{row['suite_group']} | {row['model_label']}"
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
                    pl.col("model_name").alias("model_label"),
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
                        pl.col("model_name").alias("model_label"),
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
    entries: list[dict[str, object]] = []
    loss_frame = _all_loss_rows(run_dir)
    if loss_frame.is_empty():
        return []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        series = _cumulative_loss_pairs(loss_frame, tail_side)
        if not series:
            continue
        fig, ax = plt.subplots(figsize=(10.5, 5.4))
        for label, frame in series:
            if frame.is_empty():
                continue
            forecast_dates = _plot_date_values(frame["forecast_date"].to_list())
            ax.plot(
                forecast_dates,
                frame["cumulative_gain"].to_list(),
                linewidth=1.45,
                label=label,
            )
        ax.axhline(0.0, color="#111827", linewidth=0.9, linestyle="--")
        ax.set_title(f"Cumulative loss difference ({_label_tail_side(tail_side)})")
        ax.set_xlabel("Forecast date")
        ax.set_ylabel("Cumulative anchor loss - candidate loss")
        ax.legend(frameon=False, fontsize=8)
        _set_monthly_date_ticks(ax)
        _style_axes(ax)
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"cumulative_loss_difference_{tail_side}",
                source_artifacts=[
                    "metrics/benchmark_loss_matrix.parquet",
                    "metrics/ml_tail_loss_matrix.parquet",
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=(
                    f"Cumulative loss-difference diagnostic for {tail_side}. Positive "
                    "slope means the candidate has lower cumulative FZ loss than the "
                    "anchor under the fixed sign convention anchor loss minus candidate loss."
                ),
                claim_scope="headline_cumulative_loss_difference_sign_fixed",
            )
        )
    return entries


def _selected_model_performance_figures(
    *, run_dir: Path, figure_dir: Path
) -> list[dict[str, object]]:
    frame = _selected_performance_frame(run_dir)
    if frame.is_empty() or "tail_side" not in frame.columns:
        return []
    entries: list[dict[str, object]] = []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        side = side.sort(["suite_order", "selection_rank", "model_label"])
        labels = [
            f"{row.get('suite_group')} | {row.get('model_label')}"
            for row in side.iter_rows(named=True)
        ]
        colors = [_suite_color(str(row.get("suite_key"))) for row in side.iter_rows(named=True)]
        breach = _series_percent(side, "var_breach_rate")
        fz_loss = [float(_optional_float(value) or 0.0) for value in side["mean_fz_loss"].to_list()]
        fig, axes = plt.subplots(1, 2, figsize=(13.2, max(5.0, len(labels) * 0.42)))
        y = np.arange(len(labels))
        axes[0].barh(y, breach, color=colors, alpha=0.88)
        expected = _first_float(side, "expected_breach_rate") or 0.05
        axes[0].axvline(expected * 100.0, color="#111827", linestyle="--", linewidth=1.25)
        axes[0].set_xlabel("VaR breach rate (%)")
        axes[0].set_title("Coverage")
        axes[0].set_yticks(y, [_short_label(label, max_len=44) for label in labels])
        axes[1].barh(y, fz_loss, color=colors, alpha=0.88)
        axes[1].set_xlabel("Mean FZ loss (lower is better)")
        axes[1].set_title("VaR-ES scoring")
        axes[1].set_yticks(y, [""] * len(labels))
        fig.suptitle(f"Selected Benchmark-vs-LGBM performance ({_label_tail_side(tail_side)})")
        for ax in axes:
            _style_axes(ax)
        caption = (
            f"Selected Benchmark-vs-LGBM performance for {tail_side}. Rows are selected "
            "within each broad group by a deterministic rule: sufficient rows, VaR "
            "coverage within the tolerance band, then lower FZ loss and quantile loss. "
            "Full per-model results remain in appendix tables."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"selected_model_performance_{tail_side}",
                source_artifacts=[
                    "metrics/benchmark_metrics_per_model.parquet",
                    "metrics/ml_tail_metrics_per_model.parquet",
                ],
                tail_side=tail_side,
                caption=caption,
                claim_scope="selected_benchmark_vs_lgbm_main_figure_not_full_result_set",
            )
        )
    return entries


def _selected_performance_frame(run_dir: Path) -> pl.DataFrame:
    benchmark = _read_optional_parquet(run_dir / "metrics" / "benchmark_metrics_per_model.parquet")
    ml_tail = _read_optional_parquet(run_dir / "metrics" / "ml_tail_metrics_per_model.parquet")
    rows = _selected_model_performance_rows(benchmark, ml_tail)
    if not rows:
        return pl.DataFrame()
    frame = pl.DataFrame(rows)
    return frame.with_columns(
        pl.when(pl.col("suite_group") == "Benchmark")
        .then(pl.lit(0))
        .otherwise(pl.lit(1))
        .alias("suite_order"),
        pl.when(pl.col("suite_group") == "Benchmark")
        .then(pl.lit("benchmark"))
        .otherwise(pl.lit("lgbm"))
        .alias("suite_key"),
        (
            _model_label_expr()
            + pl.when(pl.col("suite_group") == "LGBM")
            .then(pl.lit(" / ") + _information_set_label_expr())
            .otherwise(pl.lit(""))
        ).alias("model_label"),
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
            "Benchmark target-history Murphy diagnostics",
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
                f"Benchmark Murphy diagnostic curves for {tail_side} on the artifact's "
                "common threshold grid and target-history baseline sample. The curves "
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
        ax.set_title(f"24-check robust LGBM Murphy diagnostics ({_label_tail_side(tail_side)})")
        ax.set_xlabel("Elementary-score threshold")
        ax.set_ylabel("Mean elementary score")
        ax.legend(fontsize=6.5, frameon=False, ncol=1)
        _style_axes(ax)
        caption = (
            f"Murphy diagnostic curves for {tail_side} restricted to LGBM families that "
            "pass the full tail-by-information-set calibration screen. Each curve is a "
            "model-by-information-set pair on the shared 24-check robust sample grid; "
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
            f"{row.get('suite')} | "
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
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        side = forecasts.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        windows = _stress_overlay_windows(side)
        fig, axes = plt.subplots(len(windows), 1, figsize=(11.2, 4.1 * len(windows)), sharey=True)
        if len(windows) == 1:
            axes = [axes]
        for ax, window in zip(axes, windows, strict=False):
            window_rows = _filter_date_window(side, window["start"], window["end"])
            _plot_stress_overlay_panel(ax, window_rows, tail_side, window)
        fig.suptitle(f"VaR/ES stress-window overlays ({_label_tail_side(tail_side)})")
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"var_es_stress_overlay_{tail_side}",
                source_artifacts=[
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=(
                    f"Stress-window VaR/ES overlay for {tail_side}. The figure is an "
                    "illustration of threshold behavior around fixed stress windows; it "
                    "does not report hedge PnL, transaction costs, or trading performance."
                ),
                claim_scope="appendix_stress_overlay_illustration_not_validation",
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
                    f"Full-sample VaR overlay for {tail_side}. The benchmark comparator "
                    "is fixed as GJR-GARCH-EVT with GJR-GARCH-t fallback; the ML-tail "
                    "line is the locked side-specific promoted candidate. The figure is "
                    "a visual diagnostic and not a post-hoc best-model selection."
                ),
                claim_scope="full_sample_var_overlay_fixed_selection_visual_diagnostic",
            )
        )
    return entries


def _dm_heatmap_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    dm = _read_optional_parquet(run_dir / "metrics" / "ml_tail_result_matrix_dm.parquet")
    required = {
        "tail_side",
        "baseline_entity",
        "candidate_entity",
        "loss_family",
        "pvalue_one_sided",
        "mean_loss_diff_candidate_minus_baseline",
    }
    if dm.is_empty() or not required.issubset(dm.columns):
        return []
    entries: list[dict[str, object]] = []
    for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
        rows = _compact_dm_rows(dm, tail_side)
        if rows.is_empty():
            continue
        baselines = _ordered_unique(rows["baseline_entity"].to_list())
        candidates = _ordered_unique(rows["candidate_entity"].to_list())
        pvalues = np.full((len(baselines), len(candidates)), np.nan)
        diffs = np.full_like(pvalues, np.nan, dtype=float)
        for row in rows.iter_rows(named=True):
            i = baselines.index(str(row["baseline_entity"]))
            j = candidates.index(str(row["candidate_entity"]))
            pvalues[i, j] = _optional_float(row.get("pvalue_one_sided")) or np.nan
            diffs[i, j] = (
                _optional_float(row.get("mean_loss_diff_candidate_minus_baseline")) or np.nan
            )
        fig, ax = plt.subplots(
            figsize=(max(7.0, len(candidates) * 1.15), max(4.8, len(baselines) * 0.8))
        )
        image = ax.imshow(pvalues, cmap="viridis_r", vmin=0.0, vmax=0.25, aspect="auto")
        cbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.03)
        cbar.set_label("One-sided DM p-value")
        ax.set_xticks(
            np.arange(len(candidates)),
            [_short_label(_entity_label(value), max_len=24) for value in candidates],
            rotation=35,
            ha="right",
        )
        ax.set_yticks(
            np.arange(len(baselines)),
            [_short_label(_entity_label(value), max_len=28) for value in baselines],
        )
        for i in range(len(baselines)):
            for j in range(len(candidates)):
                if not np.isfinite(pvalues[i, j]):
                    continue
                diff = diffs[i, j]
                ax.text(
                    j,
                    i,
                    f"p={pvalues[i, j]:.3f}\nΔ={diff:.2g}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="#111827",
                )
        ax.set_title(f"Compact DM heatmap ({_label_tail_side(tail_side)})")
        ax.set_xlabel("Candidate")
        ax.set_ylabel("Anchor")
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"dm_heatmap_{tail_side}",
                source_artifacts=["metrics/ml_tail_result_matrix_dm.parquet"],
                tail_side=tail_side,
                caption=(
                    f"Compact appendix DM heatmap for {tail_side}. Cells report "
                    "one-sided DM p-values and candidate-minus-anchor mean loss "
                    "differences; negative differences favor the candidate."
                ),
                claim_scope="appendix_dm_visual_diagnostic",
            )
        )
    return entries


def _evt_standardized_residual_figures(
    *, run_dir: Path, figure_dir: Path
) -> list[dict[str, object]]:
    """EVT diagnostics for LightGBM location-scale standardized residuals.

    Reconstructs z_t = (realized_loss - location_forecast) / scale_forecast
    from the saved forecast file and produces QQ, log-survival, mean-excess,
    Hill, and threshold-stability figures per tail side.
    """
    frame = _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    if frame.is_empty():
        return []
    required = {
        "model_name",
        "tail_side",
        "location_forecast",
        "scale_forecast",
        "realized_loss",
        "is_valid_forecast",
    }
    if not required.issubset(frame.columns):
        return []
    source_artifacts = ["forecasts/ml_tail_forecasts.parquet"]
    claim_scope = "evt_standardized_residual_diagnostic_not_forecast_claim"
    entries: list[dict[str, object]] = []
    location_scale_names = set()
    for row in frame.iter_rows(named=True):
        mn = str(row.get("model_name") or "")
        if mn.startswith("lightgbm_") and mn != ML_TAIL_DIRECT_QUANTILE_MODEL:
            location_scale_names.add(mn)
    anchor_model = "lightgbm_location_scale_empirical"
    if anchor_model not in location_scale_names:
        if location_scale_names:
            anchor_model = sorted(location_scale_names)[0]
        else:
            return []
    for tail_side in _available_tail_sides(frame):
        z_values = _reconstruct_standardized_residuals(frame, tail_side, anchor_model)
        if z_values.size < 80:
            continue
        entries.extend(
            _evt_qq_figure(
                z_values,
                tail_side=tail_side,
                model_name=anchor_model,
                run_dir=run_dir,
                figure_dir=figure_dir,
                source_artifacts=source_artifacts,
                claim_scope=claim_scope,
            )
        )
        entries.extend(
            _evt_log_survival_figure(
                z_values,
                tail_side=tail_side,
                model_name=anchor_model,
                run_dir=run_dir,
                figure_dir=figure_dir,
                source_artifacts=source_artifacts,
                claim_scope=claim_scope,
            )
        )
        entries.extend(
            _evt_mean_excess_figure(
                z_values,
                tail_side=tail_side,
                model_name=anchor_model,
                run_dir=run_dir,
                figure_dir=figure_dir,
                source_artifacts=source_artifacts,
                claim_scope=claim_scope,
            )
        )
        entries.extend(
            _evt_hill_figure(
                z_values,
                tail_side=tail_side,
                model_name=anchor_model,
                run_dir=run_dir,
                figure_dir=figure_dir,
                source_artifacts=source_artifacts,
                claim_scope=claim_scope,
            )
        )
        entries.extend(
            _evt_threshold_stability_figure(
                z_values,
                tail_side=tail_side,
                model_name=anchor_model,
                run_dir=run_dir,
                figure_dir=figure_dir,
                source_artifacts=source_artifacts,
                claim_scope=claim_scope,
            )
        )
    return entries


def _reconstruct_standardized_residuals(
    frame: pl.DataFrame, tail_side: str, model_name: str
) -> np.ndarray:
    """Reconstruct z_t from saved forecast rows."""
    filtered = frame.filter(
        (pl.col("tail_side") == tail_side)
        & (pl.col("model_name") == model_name)
        & (pl.col("is_valid_forecast") == True)  # noqa: E712
        & pl.col("location_forecast").is_not_null()
        & pl.col("scale_forecast").is_not_null()
        & pl.col("realized_loss").is_not_null()
    )
    if filtered.is_empty():
        return np.asarray([], dtype=float)
    location = np.asarray(filtered["location_forecast"].to_list(), dtype=float)
    scale = np.asarray(filtered["scale_forecast"].to_list(), dtype=float)
    realized = np.asarray(filtered["realized_loss"].to_list(), dtype=float)
    mask = np.isfinite(location) & np.isfinite(scale) & (scale > 0) & np.isfinite(realized)
    z = (realized[mask] - location[mask]) / scale[mask]
    return z[np.isfinite(z)]


def _evt_qq_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
    model_name: str,
    run_dir: Path,
    figure_dir: Path,
    source_artifacts: list[str],
    claim_scope: str,
) -> list[dict[str, object]]:
    """GPD Q-Q plot for standardized residuals."""
    qq = _gpd_qq_values(z_values, threshold_probability=0.90)
    if qq is None:
        return []
    empirical, fitted, threshold = qq
    fig, ax = plt.subplots(figsize=(6.2, 5.6))
    ax.scatter(fitted, empirical, s=18, color="#059669", alpha=0.78)
    max_value = max(float(np.max(empirical)), float(np.max(fitted)))
    ax.plot([0.0, max_value], [0.0, max_value], color="#111827", linewidth=1.1, linestyle="--")
    ax.set_title(f"Standardized residual GPD Q-Q ({_label_tail_side(tail_side)})")
    ax.set_xlabel("Fitted GPD excess quantile")
    ax.set_ylabel("Empirical excess quantile")
    ax.text(
        0.02,
        0.96,
        f"threshold = {threshold:.3f}  |  n_excess = {int(np.sum(z_values > threshold))}",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
        color="#374151",
    )
    _style_axes(ax)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name=f"evt_standardized_qq_{tail_side}",
        source_artifacts=source_artifacts,
        tail_side=tail_side,
        caption=(
            "GPD Q-Q diagnostic for "
            f"{display_model_label(model_name)} standardized residuals ({tail_side}). "
            "Excesses above the plotted evaluation-sample 90th percentile threshold are "
            "compared with fitted GPD quantiles. Residuals are pooled across available "
            "information sets and tail levels for this diagnostic; this is not a "
            "forecast-performance claim."
        ),
        claim_scope=claim_scope,
    )


def _evt_log_survival_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
    model_name: str,
    run_dir: Path,
    figure_dir: Path,
    source_artifacts: list[str],
    claim_scope: str,
) -> list[dict[str, object]]:
    """Log survival plot for standardized residuals."""
    x, survival = _survival_curve(z_values)
    if x.size < 10:
        return []
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    ax.semilogy(x, survival, color="#059669", linewidth=1.5, label="standardized residuals")
    # overlay normal reference
    x_norm = np.linspace(float(np.min(x)), float(np.max(x)), 200)
    from scipy.stats import norm  # type: ignore[import-untyped]

    survival_norm = 1.0 - norm.cdf(
        x_norm, loc=float(np.mean(z_values)), scale=float(np.std(z_values, ddof=1))
    )
    survival_norm = np.maximum(survival_norm, 1e-12)
    ax.semilogy(
        x_norm,
        survival_norm,
        color="#94a3b8",
        linewidth=1.0,
        linestyle="--",
        label="normal reference",
    )
    ax.set_title(f"Standardized residual log survival ({_label_tail_side(tail_side)})")
    ax.set_xlabel("Standardized loss z")
    ax.set_ylabel("Empirical survival probability, log scale")
    ax.legend(frameon=False, fontsize=8)
    _style_axes(ax)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name=f"evt_standardized_log_survival_{tail_side}",
        source_artifacts=source_artifacts,
        tail_side=tail_side,
        caption=(
            f"Log survival curve for {display_model_label(model_name)} standardized "
            f"residuals ({tail_side}) compared with a normal reference. Residuals are "
            "pooled across available information sets and tail levels for this diagnostic."
        ),
        claim_scope=claim_scope,
    )


def _evt_mean_excess_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
    model_name: str,
    run_dir: Path,
    figure_dir: Path,
    source_artifacts: list[str],
    claim_scope: str,
) -> list[dict[str, object]]:
    """Mean excess plot for standardized residuals."""
    thresholds, mean_excess = _mean_excess_curve(z_values)
    if thresholds.size < 5:
        return []
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    ax.plot(thresholds, mean_excess, color="#059669", linewidth=1.6, marker="o", markersize=3)
    ax.set_title(f"Standardized residual mean excess ({_label_tail_side(tail_side)})")
    ax.set_xlabel("Threshold z")
    ax.set_ylabel("Mean excess E[Z - z | Z > z]")
    ax.text(
        0.02,
        0.96,
        "Linear pattern → GPD appropriate",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
        color="#374151",
        style="italic",
    )
    _style_axes(ax)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name=f"evt_standardized_mean_excess_{tail_side}",
        source_artifacts=source_artifacts,
        tail_side=tail_side,
        caption=(
            f"Mean excess function for {display_model_label(model_name)} standardized "
            f"residuals ({tail_side}). A near-linear upper-tail pattern supports GPD "
            "modeling for this pooled residual diagnostic; it is not a forecast-validation claim."
        ),
        claim_scope=claim_scope,
    )


def _evt_hill_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
    model_name: str,
    run_dir: Path,
    figure_dir: Path,
    source_artifacts: list[str],
    claim_scope: str,
) -> list[dict[str, object]]:
    """Hill plot for standardized residuals."""
    ks, xi = _hill_curve(z_values)
    if ks.size < 5:
        return []
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    ax.plot(ks, xi, color="#059669", linewidth=1.5)
    ax.axhline(0.0, color="#94a3b8", linewidth=0.8, linestyle=":")
    ax.set_title(f"Standardized residual Hill plot ({_label_tail_side(tail_side)})")
    ax.set_xlabel("Number of upper order statistics k")
    ax.set_ylabel("Hill estimate of tail index ξ")
    # annotate stable region
    if ks.size > 10:
        mid = len(ks) // 2
        xi_window = xi[max(0, mid - 5) : mid + 5]
        if len(xi_window) > 0:
            ax.axhspan(
                float(np.min(xi_window)),
                float(np.max(xi_window)),
                alpha=0.08,
                color="#059669",
                label=f"mid-range ξ ≈ {float(np.mean(xi_window)):.3f}",
            )
            ax.legend(frameon=False, fontsize=8)
    _style_axes(ax)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name=f"evt_standardized_hill_{tail_side}",
        source_artifacts=source_artifacts,
        tail_side=tail_side,
        caption=(
            f"Hill tail-index estimates for {display_model_label(model_name)} standardized "
            f"residuals ({tail_side}) "
            "as a function of the number of upper order statistics k. A stable plateau "
            "indicates consistent tail behavior. This is a tail-assumption diagnostic."
        ),
        claim_scope=claim_scope,
    )


def _evt_threshold_stability_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
    model_name: str,
    run_dir: Path,
    figure_dir: Path,
    source_artifacts: list[str],
    claim_scope: str,
) -> list[dict[str, object]]:
    """Threshold stability plot for GPD shape and modified scale."""
    grid = np.array([0.80, 0.85, 0.875, 0.90, 0.925, 0.95, 0.975])
    shapes: list[float] = []
    mod_scales: list[float] = []
    kept_grid: list[float] = []
    for probability in grid:
        threshold = float(np.quantile(z_values, probability))
        excess = z_values[z_values > threshold] - threshold
        if excess.size < 15:
            continue
        try:
            shape, _, scale = genpareto.fit(excess, floc=0.0)
        except (ValueError, RuntimeError, FloatingPointError):
            continue
        if not np.isfinite(shape) or not np.isfinite(scale) or scale <= 0.0:
            continue
        kept_grid.append(probability)
        shapes.append(float(shape))
        mod_scales.append(float(scale - shape * threshold))
    if len(kept_grid) < 3:
        return []
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 7.0), sharex=True)
    axes[0].plot(kept_grid, shapes, color="#059669", linewidth=1.6, marker="o", markersize=4)
    axes[0].axhline(0.0, color="#94a3b8", linewidth=0.8, linestyle=":")
    axes[0].set_ylabel("GPD shape ξ̂")
    axes[0].set_title(f"GPD threshold stability ({_label_tail_side(tail_side)})")
    axes[1].plot(kept_grid, mod_scales, color="#2563eb", linewidth=1.6, marker="s", markersize=4)
    axes[1].set_ylabel("Modified scale σ̂* = σ̂ − ξ̂·u")
    axes[1].set_xlabel("Threshold quantile")
    for ax in axes:
        _style_axes(ax)
    return _save_figure(
        fig,
        run_dir=run_dir,
        figure_dir=figure_dir,
        name=f"evt_standardized_threshold_stability_{tail_side}",
        source_artifacts=source_artifacts,
        tail_side=tail_side,
        caption=(
            f"GPD parameter stability across threshold quantiles for "
            f"{display_model_label(model_name)} standardized residuals ({tail_side}). "
            "Stable shape and modified scale across thresholds "
            "support the POT-GPD specification. This diagnostic validates the threshold "
            "choice, not forecast accuracy."
        ),
        claim_scope=claim_scope,
    )


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


def _metric_row_for_model(
    frame: pl.DataFrame,
    *,
    tail_side: str,
    model_names: tuple[str, ...],
) -> dict[str, object] | None:
    required = {"tail_side", "model_name"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return None
    for model_name in model_names:
        selected = frame.filter(
            (pl.col("tail_side") == tail_side) & (pl.col("model_name") == model_name)
        )
        if not selected.is_empty():
            return dict(selected.row(0, named=True))
    return None


def _promoted_metric_for_tail(frame: pl.DataFrame, tail_side: str) -> dict[str, object] | None:
    required = {"tail_side", "model_name", "information_set"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return None
    for spec in PROMOTED_TAIL_MODEL_SPECS:
        if spec.get("tail_side") != tail_side:
            continue
        selected = frame.filter(
            (pl.col("tail_side") == spec["tail_side"])
            & (pl.col("model_name") == spec["model_name"])
            & (pl.col("information_set") == spec["information_set"])
        )
        if not selected.is_empty():
            return dict(selected.row(0, named=True))
    return None


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


def _cumulative_loss_pairs(
    loss_frame: pl.DataFrame, tail_side: str
) -> list[tuple[str, pl.DataFrame]]:
    pairs: list[tuple[str, pl.DataFrame]] = []
    direct_anchor = _loss_identity(
        suite="ml_tail",
        model_name=ML_TAIL_DIRECT_QUANTILE_MODEL,
        information_set="japan_only",
    )
    direct_candidate = _loss_identity(
        suite="ml_tail",
        model_name=ML_TAIL_DIRECT_QUANTILE_MODEL,
        information_set="japan_only_plus_us_close_core",
    )
    direct_pair = _paired_cumulative_loss(
        loss_frame,
        tail_side=tail_side,
        anchor=direct_anchor,
        candidate=direct_candidate,
    )
    if not direct_pair.is_empty():
        pairs.append(("JP only direct → +US close direct", direct_pair))
    promoted = _promoted_spec_for_tail(tail_side)
    if promoted is not None:
        benchmark_pair = _paired_cumulative_loss(
            loss_frame,
            tail_side=tail_side,
            anchor=_loss_identity(
                suite="benchmark",
                model_name=BENCHMARK_STRESS_PRIMARY_MODEL,
                information_set="target_history_only",
            ),
            candidate=_loss_identity(
                suite="ml_tail",
                model_name=str(promoted["model_name"]),
                information_set=str(promoted["information_set"]),
            ),
        )
        if benchmark_pair.is_empty():
            benchmark_pair = _paired_cumulative_loss(
                loss_frame,
                tail_side=tail_side,
                anchor=_loss_identity(
                    suite="benchmark",
                    model_name=BENCHMARK_STRESS_FALLBACK_MODEL,
                    information_set="target_history_only",
                ),
                candidate=_loss_identity(
                    suite="ml_tail",
                    model_name=str(promoted["model_name"]),
                    information_set=str(promoted["information_set"]),
                ),
            )
        if not benchmark_pair.is_empty():
            pairs.append(("benchmark floor → promoted ML-tail", benchmark_pair))
    return pairs


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


def _promoted_spec_for_tail(tail_side: str) -> Mapping[str, object] | None:
    for spec in PROMOTED_TAIL_MODEL_SPECS:
        if spec.get("tail_side") == tail_side:
            return spec
    return None


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
                        pl.lit("Benchmark floor").alias("plot_group"),
                        pl.lit(0).alias("plot_order"),
                    )
                )
        frames.extend(rows)
    ml_tail = _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    if not ml_tail.is_empty():
        rows = []
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            direct = _metric_forecast_for_identity(
                ml_tail,
                tail_side=tail_side,
                model_name=ML_TAIL_DIRECT_QUANTILE_MODEL,
                information_set="japan_only",
            )
            if not direct.is_empty():
                rows.append(
                    direct.with_columns(
                        pl.lit("JP-only direct").alias("plot_group"),
                        pl.lit(1).alias("plot_order"),
                    )
                )
            promoted = _promoted_spec_for_tail(tail_side)
            if promoted is not None:
                promoted_rows = _metric_forecast_for_identity(
                    ml_tail,
                    tail_side=tail_side,
                    model_name=str(promoted["model_name"]),
                    information_set=str(promoted["information_set"]),
                )
                if not promoted_rows.is_empty():
                    rows.append(
                        promoted_rows.with_columns(
                            pl.lit("Promoted ML-tail").alias("plot_group"),
                            pl.lit(2).alias("plot_order"),
                        )
                    )
        frames.extend(rows)
    if not frames:
        return pl.DataFrame()
    return pl.concat([_valid_forecast_rows(frame) for frame in frames], how="diagonal_relaxed")


def _full_sample_var_overlay_forecasts(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark = _read_optional_parquet(run_dir / "forecasts" / "benchmark_forecasts.parquet")
    if not benchmark.is_empty():
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            selected = _metric_forecast_for_model(
                benchmark,
                tail_side=tail_side,
                model_names=(BENCHMARK_STRESS_PRIMARY_MODEL, BENCHMARK_STRESS_FALLBACK_MODEL),
            )
            if not selected.is_empty():
                frames.append(
                    selected.with_columns(
                        pl.lit("Benchmark comparator").alias("plot_group"),
                        pl.lit(0).alias("plot_order"),
                    )
                )
    ml_tail = _read_optional_parquet(run_dir / "forecasts" / "ml_tail_forecasts.parquet")
    if not ml_tail.is_empty():
        for tail_side in (TAIL_SIDE_LEFT, TAIL_SIDE_RIGHT):
            promoted = _promoted_spec_for_tail(tail_side)
            if promoted is None:
                continue
            selected = _metric_forecast_for_identity(
                ml_tail,
                tail_side=tail_side,
                model_name=str(promoted["model_name"]),
                information_set=str(promoted["information_set"]),
            )
            if not selected.is_empty():
                frames.append(
                    selected.with_columns(
                        pl.lit("Promoted ML-tail").alias("plot_group"),
                        pl.lit(1).alias("plot_order"),
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
    windows = [
        {
            "name": "COVID fixed window",
            "start": date(2020, 2, 15),
            "end": date(2020, 4, 30),
            "allow_empty": True,
        }
    ]
    max_date = _max_loss_date(side)
    if max_date is not None:
        windows.append(
            {
                "name": f"Max-loss window centered on {max_date.isoformat()}",
                "start": max_date - timedelta(days=30),
                "end": max_date + timedelta(days=30),
                "allow_empty": False,
            }
        )
    return windows


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
) -> None:
    ax.set_title(str(window["name"]))
    if frame.is_empty():
        ax.text(
            0.5,
            0.5,
            "Window outside available OOS forecast sample",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="#6b7280",
        )
        _style_axes(ax)
        return
    realized = frame.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
    dates = realized["forecast_date"].to_list()
    ax.plot(
        dates,
        realized["realized_loss"].to_list(),
        color="#111827",
        linewidth=1.1,
        label="realized loss",
    )
    colors = {
        "Benchmark floor": "#475569",
        "JP-only direct": "#2563eb",
        "Promoted ML-tail": "#7c3aed",
    }
    for group, group_frame in frame.group_by("plot_group", maintain_order=True):
        label = str(group[0] if isinstance(group, tuple) else group)
        series = group_frame.sort("forecast_date")
        color = colors.get(label, "#64748b")
        ax.plot(
            series["forecast_date"].to_list(),
            series["var_forecast"].to_list(),
            color=color,
            linewidth=1.3,
            label=f"{label} VaR",
        )
        if "es_forecast" in series.columns and series["es_forecast"].drop_nulls().len() > 0:
            ax.plot(
                series["forecast_date"].to_list(),
                series["es_forecast"].to_list(),
                color=color,
                linewidth=1.0,
                linestyle="--",
                alpha=0.8,
                label=f"{label} ES",
            )
    breaches = (
        frame.filter(pl.col("var_breach").fill_null(False))
        if "var_breach" in frame.columns
        else pl.DataFrame()
    )
    if not breaches.is_empty():
        breach_dates = (
            breaches.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
        )
        ax.scatter(
            breach_dates["forecast_date"].to_list(),
            breach_dates["realized_loss"].to_list(),
            s=26,
            color="#dc2626",
            label="VaR breach",
            zorder=5,
        )
    ax.set_ylabel("Positive loss")
    ax.set_xlabel("Forecast date")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    _style_axes(ax)


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
    colors = {
        "Benchmark comparator": "#475569",
        "Promoted ML-tail": "#7c3aed",
    }
    for group, group_frame in frame.sort("plot_order").group_by("plot_group", maintain_order=True):
        label = str(group[0] if isinstance(group, tuple) else group)
        series = (
            group_frame.sort("forecast_date")
            .unique(subset=["forecast_date"], keep="first")
            .sort("forecast_date")
        )
        ax.plot(
            _plot_date_values(series["forecast_date"].to_list()),
            series["var_forecast"].to_list(),
            color=colors.get(label, "#64748b"),
            linewidth=1.35,
            label=f"{label} VaR",
        )
    promoted = frame.filter(pl.col("plot_group") == "Promoted ML-tail")
    if "var_breach" in promoted.columns:
        breaches = promoted.filter(pl.col("var_breach").fill_null(False))
        if not breaches.is_empty():
            breach_points = (
                breaches.select(["forecast_date", "realized_loss"]).unique().sort("forecast_date")
            )
            ax.scatter(
                _plot_date_values(breach_points["forecast_date"].to_list()),
                breach_points["realized_loss"].to_list(),
                s=18,
                color="#dc2626",
                label="promoted VaR breach",
                zorder=5,
            )
    ax.axhline(0.0, color="#111827", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.set_title(f"Full-sample VaR overlay ({_label_tail_side(tail_side)})")
    ax.set_ylabel("Realized loss and VaR")
    ax.set_xlabel("Forecast date")
    _set_monthly_date_ticks(ax)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    _style_axes(ax)


def _compact_dm_rows(dm: pl.DataFrame, tail_side: str) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    candidates = [
        (
            "information_set_ladder",
            "information_set_increment",
            "japan_only",
            "japan_only_plus_us_close_core",
            None,
        ),
    ]
    promoted = _promoted_spec_for_tail(tail_side)
    if promoted is not None:
        candidates.append(
            (
                "tail_model_family",
                "model_family",
                ML_TAIL_DIRECT_QUANTILE_MODEL,
                str(promoted["model_name"]),
                str(promoted["information_set"]),
            )
        )
    for family, axis, baseline, candidate, information_set in candidates:
        for loss_family in ("var_es_fz_loss", "var_quantile_loss"):
            selected = dm.filter(
                (pl.col("tail_side") == tail_side)
                & (pl.col("comparison_family") == family)
                & (pl.col("comparison_axis") == axis)
                & (pl.col("baseline_entity") == baseline)
                & (pl.col("candidate_entity") == candidate)
                & (pl.col("loss_family") == loss_family)
            )
            if information_set is not None and "information_set" in selected.columns:
                selected = selected.filter(pl.col("information_set") == information_set)
            if not selected.is_empty():
                rows.append(dict(selected.row(0, named=True)))
                break
    return pl.DataFrame(rows) if rows else pl.DataFrame()


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
) -> list[dict[str, object]]:
    fig.tight_layout()
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
    return tail_side.replace("_", " ")


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
