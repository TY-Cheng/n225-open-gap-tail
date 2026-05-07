# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import genpareto

from n225_open_gap_tail.config.runtime import (
    BENCHMARK_FLOOR_MODEL_NAMES,
    Mapping,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
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
from n225_open_gap_tail.reporting.latex import (
    _hedge_trigger_rows,
    _selected_model_performance_rows,
    _severity_rows,
)


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
    entries.extend(_target_distribution_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_coverage_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_selected_model_performance_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_murphy_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_dst_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_severity_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_trigger_figures(run_dir=run_dir, figure_dir=figure_dir))
    entries.extend(_evt_standardized_residual_figures(run_dir=run_dir, figure_dir=figure_dir))
    _ = manifest
    return FigureExportResult(figure_dir=figure_dir, figure_entries=entries)


def _remove_stale_figures(figure_dir: Path) -> None:
    for pattern in ("*.png", "*.pdf"):
        for path in figure_dir.glob(pattern):
            path.unlink(missing_ok=True)


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
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        x, survival = _survival_curve(values)
        if x.size:
            ax.semilogy(x, survival, label=label, color=color, linewidth=1.5)
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

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        thresholds, mean_excess = _mean_excess_curve(values)
        if thresholds.size:
            ax.plot(thresholds, mean_excess, label=label, color=color, linewidth=1.6)
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

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    for label, values, color in (
        ("left loss", left_loss, "#dc2626"),
        ("right loss", right_loss, "#2563eb"),
        ("absolute gap", abs_gap, "#4b5563"),
    ):
        ks, xi = _hill_curve(values)
        if ks.size:
            ax.plot(ks, xi, label=label, color=color, linewidth=1.5)
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
    return entries


def _target_gap_frame(run_dir: Path) -> pl.DataFrame:
    frame = _read_optional_parquet(run_dir / "panel" / "modeling_panel.parquet")
    if frame.is_empty() or "gap_t" not in frame.columns:
        return pl.DataFrame()
    clean = frame.filter(pl.col("gap_t").is_not_null())
    if "clean_sample" in clean.columns:
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
    except Exception:
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
    survival = np.asarray([float(np.mean(finite > value)) for value in positive])
    return positive, survival


def _mean_excess_curve(values: object) -> tuple[object, object]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
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
    finite = np.sort(finite[np.isfinite(finite)])
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
                claim_scope="coverage_diagnostic_not_headline_claim",
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
                    pl.lit("benchmark_floor").alias("suite_group"),
                    pl.lit(0).alias("suite_order"),
                    pl.col("model_name").alias("model_label"),
                )
            )
    benchmark_per_model = _read_optional_parquet(
        run_dir / "metrics" / "benchmark_metrics_per_model.parquet"
    )
    if not benchmark_per_model.is_empty() and "model_name" in benchmark_per_model.columns:
        advanced = benchmark_per_model.filter(
            ~pl.col("model_name").is_in(list(BENCHMARK_FLOOR_MODEL_NAMES))
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
                    pl.lit("ml_tail_headline").alias("suite_group"),
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
            "Benchmark floor Murphy diagnostics",
            "model_name",
            "metrics/benchmark_murphy.parquet",
            "murphy_diagnostic_benchmark_floor_common_grid",
        ),
        (
            "ml_tail_murphy",
            run_dir / "metrics" / "ml_tail_murphy.parquet",
            "ML-tail nested-information-set Murphy diagnostics",
            "information_set",
            "metrics/ml_tail_murphy.parquet",
            "murphy_diagnostic_ml_tail_nested_information_sets_common_grid",
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
                f"Murphy diagnostic curves for {tail_side} on the artifact's common "
                "threshold grid and recorded sample policy. The curves are descriptive "
                "forecast-evaluation diagnostics and are not pairwise dominance claims."
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


def _dst_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    frame = _read_optional_parquet(run_dir / "metrics" / "ml_tail_dst_attenuation.parquet")
    required = {"tail_side", "dst_regime", "mean_quantile_gain", "mean_fz_gain"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return []
    entries: list[dict[str, object]] = []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        rows = [
            row
            for row in side.iter_rows(named=True)
            if row.get("dst_regime") != "absorption_coefficient"
            and _optional_float(row.get("mean_quantile_gain")) is not None
        ]
        if not rows:
            continue
        labels = [
            f"{row.get('dst_regime')} / {float(row.get('tail_level') or 0.0):.3f}" for row in rows
        ]
        q_gain = [float(row["mean_quantile_gain"]) for row in rows]
        fz_gain = [
            float(row["mean_fz_gain"])
            if _optional_float(row.get("mean_fz_gain")) is not None
            else 0.0
            for row in rows
        ]
        x = np.arange(len(labels))
        fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
        axes[0].bar(x, q_gain, color="#2563eb", alpha=0.85)
        axes[0].axhline(0.0, color="#1f2937", linewidth=1.0)
        axes[0].set_ylabel("Quantile-loss gain")
        axes[1].bar(x, fz_gain, color="#059669", alpha=0.85)
        axes[1].axhline(0.0, color="#1f2937", linewidth=1.0)
        axes[1].set_ylabel("FZ-loss gain")
        axes[1].set_xticks(x, labels, rotation=35, ha="right")
        fig.suptitle(f"DST attenuation diagnostics ({_label_tail_side(tail_side)})")
        for ax in axes:
            _style_axes(ax)
        caption = (
            f"DST attenuation diagnostic for {tail_side}; bars report registered "
            "forecast-loss gain summaries by timing regime. This is descriptive "
            "forecast evidence, not structural causal identification."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"dst_attenuation_{tail_side}",
                source_artifacts=["metrics/ml_tail_dst_attenuation.parquet"],
                tail_side=tail_side,
                caption=caption,
                claim_scope="descriptive_dst_attenuation_not_structural_causal_identification",
            )
        )
    return entries


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


def _trigger_figures(*, run_dir: Path, figure_dir: Path) -> list[dict[str, object]]:
    rows = _selected_trigger_rows(run_dir)
    if not rows:
        return []
    frame = pl.DataFrame(rows)
    if "tail_side" not in frame.columns:
        frame = frame.with_columns(pl.lit(PRIMARY_TAIL_SIDE).alias("tail_side"))
    entries: list[dict[str, object]] = []
    for tail_side in _available_tail_sides(frame):
        side = frame.filter(pl.col("tail_side") == tail_side)
        if side.is_empty():
            continue
        selected = _trigger_plot_rows(side)
        if selected.is_empty():
            continue
        labels = [
            f"{row.get('suite')} | "
            f"{display_model_label(row.get('model_name'))} | "
            f"{display_information_set_label(row.get('information_set'))}"
            for row in selected.iter_rows(named=True)
        ]
        x = np.arange(len(labels))
        false_alarm_rate = _series_percent(selected, "false_alarm_rate")
        missed_rate = _series_percent(selected, "missed_exception_rate")
        fig, ax = plt.subplots(figsize=(12, 6.5))
        width = 0.34
        ax.bar(
            x - width / 2,
            false_alarm_rate,
            width,
            label="false alarm / trigger",
            color="#dc2626",
            alpha=0.75,
        )
        ax.bar(
            x + width / 2,
            missed_rate,
            width,
            label="missed exception / exception",
            color="#f59e0b",
            alpha=0.8,
        )
        ax.set_ylabel("Rate (%)")
        ax.set_title(f"VaR trigger diagnostics ({_label_tail_side(tail_side)})")
        ax.set_xticks(
            x, [_short_label(label, max_len=34) for label in labels], rotation=35, ha="right"
        )
        ax.legend(frameon=False, fontsize=8)
        _style_axes(ax)
        caption = (
            f"VaR trigger diagnostic for selected Benchmark-vs-LGBM candidates in "
            f"{tail_side}. Trigger is the within-model 75th-percentile VaR rule; "
            "the trigger rate is therefore near 25% by construction and is omitted "
            "from the compact plot. This is not hedge PnL, not transaction-cost "
            "evidence, and not trading-alpha evidence."
        )
        entries.extend(
            _save_figure(
                fig,
                run_dir=run_dir,
                figure_dir=figure_dir,
                name=f"trigger_diagnostics_{tail_side}",
                source_artifacts=[
                    "forecasts/benchmark_forecasts.parquet",
                    "forecasts/ml_tail_forecasts.parquet",
                ],
                tail_side=tail_side,
                caption=caption,
                claim_scope="trigger_diagnostic_not_pnl_cost_or_alpha",
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
            f"GPD Q-Q diagnostic for LightGBM location-scale standardized residuals "
            f"({tail_side}). Excesses above the OOF 90th percentile threshold are "
            "compared with fitted GPD quantiles. This diagnostic validates the EVT tail "
            "assumption for the filtered residuals, not a forecast-performance claim."
        ),
        claim_scope=claim_scope,
    )


def _evt_log_survival_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
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
            f"Log survival curve for LightGBM standardized residuals ({tail_side}) "
            "compared with a normal reference. Departures above the normal curve "
            "indicate heavier-than-normal tails in the filtered residuals."
        ),
        claim_scope=claim_scope,
    )


def _evt_mean_excess_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
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
            f"Mean excess function for LightGBM standardized residuals ({tail_side}). "
            "A near-linear pattern above the threshold supports GPD modeling. This is "
            "a tail-assumption diagnostic, not a forecast-validation claim."
        ),
        claim_scope=claim_scope,
    )


def _evt_hill_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
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
            f"Hill tail-index estimates for LightGBM standardized residuals ({tail_side}) "
            "as a function of the number of upper order statistics k. A stable plateau "
            "indicates consistent tail behavior. This is a tail-assumption diagnostic."
        ),
        claim_scope=claim_scope,
    )


def _evt_threshold_stability_figure(
    z_values: np.ndarray,
    *,
    tail_side: str,
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
        except Exception:
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
            f"GPD parameter stability across threshold quantiles for LightGBM standardized "
            f"residuals ({tail_side}). Stable shape and modified scale across thresholds "
            "support the POT-GPD specification. This diagnostic validates the threshold "
            "choice, not forecast accuracy."
        ),
        claim_scope=claim_scope,
    )


def _combined_severity_metrics(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "metrics" / "benchmark_metrics.parquet"
    if benchmark_path.exists():
        frames.append(
            pl.read_parquet(benchmark_path).with_columns(
                pl.lit("benchmark_floor").alias("suite"),
                pl.lit("headline_benchmark_floor").alias("claim_scope"),
            )
        )
    ml_headline_path = run_dir / "metrics" / "ml_tail_metrics.parquet"
    if ml_headline_path.exists():
        frames.append(
            pl.read_parquet(ml_headline_path).with_columns(
                pl.lit("ml_tail_headline").alias("suite"),
                pl.lit("headline_nested_information_sets").alias("claim_scope"),
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
                pl.col("model_name").is_in(list(BENCHMARK_FLOOR_MODEL_NAMES))
            )
        if not benchmark.is_empty():
            frames.append(benchmark.with_columns(pl.lit("benchmark_floor").alias("suite")))
    ml_tail_path = run_dir / "forecasts" / "ml_tail_forecasts.parquet"
    if ml_tail_path.exists():
        ml_tail = pl.read_parquet(ml_tail_path)
        if "model_name" in ml_tail.columns:
            ml_tail = ml_tail.filter(pl.col("model_name") == ML_TAIL_DIRECT_QUANTILE_MODEL)
        if not ml_tail.is_empty():
            frames.append(ml_tail.with_columns(pl.lit("ml_tail_headline").alias("suite")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _all_forecasts_for_trigger(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    benchmark_path = run_dir / "forecasts" / "benchmark_forecasts.parquet"
    if benchmark_path.exists():
        benchmark = pl.read_parquet(benchmark_path)
        if not benchmark.is_empty():
            frames.append(benchmark.with_columns(pl.lit("Benchmark").alias("suite")))
    ml_tail_path = run_dir / "forecasts" / "ml_tail_forecasts.parquet"
    if ml_tail_path.exists():
        ml_tail = pl.read_parquet(ml_tail_path)
        if not ml_tail.is_empty():
            frames.append(ml_tail.with_columns(pl.lit("LGBM").alias("suite")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _selected_trigger_rows(run_dir: Path) -> list[dict[str, object]]:
    selected = _selected_performance_frame(run_dir)
    forecasts = _all_forecasts_for_trigger(run_dir)
    if selected.is_empty() or forecasts.is_empty():
        return []
    selected_keys = {
        (
            str(row.get("suite_group") or ""),
            str(row.get("model_name") or ""),
            str(row.get("information_set") or ""),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
        )
        for row in selected.iter_rows(named=True)
    }
    rows = _hedge_trigger_rows(forecasts)
    return [
        row
        for row in rows
        if (
            str(row.get("suite") or ""),
            str(row.get("model_name") or ""),
            str(row.get("information_set") or ""),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
        )
        in selected_keys
    ]


def _trigger_plot_rows(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    selected = frame
    if "tail_level" in selected.columns:
        selected = selected.filter(
            pl.col("tail_level") == selected.select(pl.col("tail_level").min()).item()
        )
    return _limit_rows_for_plot(
        selected.sort(["suite", "model_name", "information_set"]),
        max_rows=18,
    )


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
        "benchmark_floor": "#475569",
        "benchmark_advanced": "#0f766e",
        "ml_tail_headline": "#2563eb",
        "ml_tail_restricted_family": "#7c3aed",
    }.get(suite_group, "#64748b")


def _style_axes(ax: object) -> None:
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=8)
