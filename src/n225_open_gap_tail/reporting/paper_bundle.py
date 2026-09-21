"""Export a paper-facing bundle from frozen evaluation artifacts, without inference."""

from __future__ import annotations

import csv
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.config.runtime import _required_float
from n225_open_gap_tail.data_lake.io import read_verified_parquet_metadata
from n225_open_gap_tail.forecasting.reevaluation import _file_sha256
from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.reporting.latex_utils import _latex_escape
from n225_open_gap_tail.reporting.paper_bundle_diagnostics import render_diagnostics

type Row = dict[str, object]

_TABLES = (
    "availability",
    "availability_by_date",
    "gate_scenarios",
    "admissibility",
    "global_scores",
    "pairwise",
    "mcs",
    "grem_summary",
    "grem_curves",
    "common_sample",
    "comparison_status",
    "references",
    "external_selection",
)
_COLORS = ("#1f77b4", "#d97706", "#555555", "#8a528f")


def export_paper_bundle(*, evaluation_dir: Path, information_dir: Path, output_dir: Path) -> Path:
    """Render stored results into a new directory; refuse changed or mismatched inputs."""
    evaluation_dir, information_dir, output_dir = (
        path.resolve() for path in (evaluation_dir, information_dir, output_dir)
    )
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite paper bundle: {output_dir}")
    evaluation = json.loads((evaluation_dir / "manifest.json").read_text())
    information = json.loads((information_dir / "manifest.json").read_text())
    supplement = json.loads((information_dir / "mean_intervals_manifest.json").read_text())
    source = Path(evaluation["source_run_dir"]).resolve()
    if evaluation.get("evaluation_protocol_version") != "fzg_grem_global_20260921":
        raise ValueError("Require the frozen FZG/GREM evaluation protocol")
    if (
        Path(information["evaluation_dir"]).resolve() != evaluation_dir
        or Path(information["source_run_dir"]).resolve() != source
    ):
        raise ValueError("Information/evaluation source identities disagree")
    if any(
        output_dir == p or p in output_dir.parents
        for p in (source, evaluation_dir, information_dir)
    ):
        raise ValueError("Paper bundle must be outside its frozen input directories")
    hashes: dict[str, str] = {}
    for manifest in (evaluation, information, supplement):
        for field in ("source_sha256", "output_sha256"):
            for name, digest in manifest.get(field, {}).items():
                path = Path(name)
                if not path.is_absolute():
                    path = information_dir.parent.parent / path
                path = path.resolve()
                if _file_sha256(path) != digest:
                    raise ValueError(f"Frozen input hash mismatch: {path}")
                hashes[str(path)] = digest
    paths = [evaluation_dir / f"{name}.parquet" for name in _TABLES]
    paths += [
        source / "panel/modeling_panel.parquet",
        source / "panel/calendar_map.parquet",
        source / "forecasts/ml_tail_forecasts.parquet",
        source / "forecasts/benchmark_forecasts.parquet",
        source / "manifest.json",
        evaluation_dir / "manifest.json",
        information_dir / "manifest.json",
        information_dir / "mean_intervals_manifest.json",
    ]
    paths += [
        information_dir / name
        for name in (
            "information_scores.png",
            "information_scores.pdf",
            "scores.parquet",
            "pairwise.parquet",
            "mean_intervals.parquet",
        )
    ]
    for path in paths:
        hashes[str(path)] = _file_sha256(path)
        if path.suffix == ".parquet":
            if not read_verified_parquet_metadata(path):
                raise ValueError(f"Missing or mismatched parquet metadata: {path}")
            sidecar = path.with_suffix(".parquet.metadata.json")
            hashes[str(sidecar)] = _file_sha256(sidecar)
    required_bound = [
        source / "panel/modeling_panel.parquet",
        source / "manifest.json",
        source / "forecasts/ml_tail_forecasts.parquet",
        source / "forecasts/benchmark_forecasts.parquet",
    ]
    if any(str(path) not in evaluation["source_sha256"] for path in required_bound):
        raise ValueError("Evaluation does not bind the source panel, forecasts and run manifest")
    tables = {name: pl.read_parquet(evaluation_dir / f"{name}.parquet") for name in _TABLES}
    status = tables["comparison_status"].to_dicts()
    roster = [*information["ml_models"], information["reference"]]
    if len(status) != 1 or status[0]["status"] != "ok" or status[0]["model_roster"] != roster:
        raise ValueError("Frozen model rosters disagree or comparison is unavailable")
    panel = pl.read_parquet(source / "panel/modeling_panel.parquet")
    calendar = pl.read_parquet(source / "panel/calendar_map.parquet")
    forecast_columns = [
        "model_name",
        "information_set",
        "tail_side",
        "tail_level",
        "forecast_date",
        "var_forecast",
        "realized_loss",
    ]
    forecasts = pl.concat(
        [
            pl.read_parquet(source / f"forecasts/{name}.parquet").select(forecast_columns)
            for name in ("ml_tail_forecasts", "benchmark_forecasts")
        ]
    )
    run = json.loads((source / "manifest.json").read_text())
    output_dir.mkdir(parents=True)
    captions = {
        "sample": _sample_figure(tables, panel, output_dir),
        "timeline": _timeline_figure(calendar, tables["common_sample"], output_dir),
        "gates": _gate_figure(tables, output_dir),
        "global_comparison": _global_figure(tables, roster, output_dir),
        "information_scores": (
            "Copied unchanged from the frozen information-contrast supplement. Left: FZG means "
            "and pointwise 95% basic CBB intervals, including GJR. Right: eight paired contrasts; "
            "intervals are pointwise, filled markers indicate Holm p <= 0.05 within eight FZG "
            "comparisons. Not simultaneous or post-selection-adjusted confidence intervals."
        ),
        "grem": _grem_figure(tables, roster, output_dir),
    }
    captions.update(
        render_diagnostics(
            panel=panel,
            calendar=calendar,
            common=tables["common_sample"],
            forecasts=forecasts,
            roster=roster,
            output=output_dir,
        )
    )
    for extension in ("png", "pdf"):
        shutil.copyfile(
            information_dir / f"information_scores.{extension}",
            output_dir / f"information_scores.{extension}",
        )
    for name in _TABLES:
        if name not in {"grem_curves", "availability_by_date", "comparison_status"}:
            _csv(tables[name], output_dir / f"{name}.csv")
    for name in ("scores", "pairwise", "mean_intervals"):
        _csv(
            pl.read_parquet(information_dir / f"{name}.parquet"),
            output_dir / f"information_{name}.csv",
        )
    _latex_tables(tables, roster, output_dir)
    notes = [
        "# Frozen paper figure/table bundle",
        "",
        "Rendering and descriptive aggregation only: no retraining, rescoring, new bootstrap, "
        "MCS, gate decision or reference selection. Manuscript is not modified.",
        "",
        f"- Evaluation: `{evaluation_dir}`",
        f"- Forecast source: `{source}`",
        f"- Information contrasts: `{information_dir}`",
        f"- Source predictor-clean start: `{run.get('combined_clean_start', 'not recorded')}`.",
        "- CSVs retain machine identifiers and all candidates; JSON-encoded cells retain lists.",
        "- `paper_tables.tex` contains compact tabular fragments (requires booktabs).",
        "",
        "All score inference is approximate/exploratory, conditional on screened models and "
        "the retained common dates. Equal A-D and left/right weights are not an application "
        "frequency estimate. Gate non-rejection is not proof of calibration. GREM is not an "
        "accuracy score or recipe-level familywise 5% guarantee.",
        "",
    ]
    for name, caption in captions.items():
        notes += [f"## {name}", "", f"![{name}]({name}.png)", "", caption, ""]
    (output_dir / "README.md").write_text("\n".join(notes))
    if any(_file_sha256(Path(path)) != digest for path, digest in hashes.items()):
        raise ValueError("Frozen inputs changed during export; bundle is incomplete")
    manifest = {
        "kind": "frozen_paper_bundle",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "evaluation_dir": str(evaluation_dir),
        "information_dir": str(information_dir),
        "source_run_dir": str(source),
        "model_roster": roster,
        "source_sha256": hashes,
        "source_hashes_verified_after_export": True,
        "exporter_sha256": _file_sha256(Path(__file__)),
        "exporter_source_sha256": {
            name: _file_sha256(Path(__file__).with_name(name))
            for name in ("paper_bundle.py", "paper_bundle_diagnostics.py", "figures.py")
        },
        "inference_recomputed": False,
        "forecasts_retrained": False,
        "captions": captions,
        "output_sha256": {p.name: _file_sha256(p) for p in sorted(output_dir.iterdir())},
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return output_dir


def _figure(width: float, height: float) -> Figure:
    figure = Figure(figsize=(width, height), layout="constrained")
    FigureCanvasAgg(figure)
    return figure


def _save(figure: Figure, output: Path, name: str) -> None:
    for extension in ("png", "pdf"):
        figure.savefig(output / f"{name}.{extension}", dpi=180)


def _label(model: object) -> str:
    text = str(model)
    if "median_iqr_pot_gpd_unibm" in text:
        return "Median-IQR-UniBM"
    if "mean_rms_gamma_pot_gpd_plain_mle" in text:
        return "Mean-RMS-Gamma-MLE"
    label = display_model_label(model)
    return label.replace("LightGBM ", "").replace("lightgbm_", "").replace("_", " ")


def _dates(values: list[str]) -> list[datetime]:
    return [datetime.fromisoformat(value) for value in values]


def _sample_figure(tables: dict[str, pl.DataFrame], panel: pl.DataFrame, output: Path) -> str:
    figure = _figure(11, 6.5)
    upper, lower = figure.subplots(2, 1)
    panel = panel.sort("forecast_date")
    upper.plot(
        _dates(panel["forecast_date"].to_list()),
        100 * panel["gap_t"].to_numpy(),
        color="#555555",
        linewidth=0.7,
    )
    common = tables["common_sample"].filter((pl.col("scope") == "main") & pl.col("in_common"))
    upper.axvspan(
        datetime.fromisoformat(str(common["forecast_date"].min())),
        datetime.fromisoformat(str(common["forecast_date"].max())),
        color=_COLORS[0],
        alpha=0.1,
    )
    upper.set(title="(a) Stored opening-gap history", ylabel="Opening gap (%)")
    admissions = tables["admissibility"].select("model_name", "suite")
    availability = tables["availability_by_date"].join(admissions, on="model_name")
    for color, suite in zip(_COLORS, ("ml_tail", "benchmark"), strict=False):
        rows = (
            availability.filter(pl.col("suite") == suite)
            .group_by("forecast_date")
            .agg(pl.col("var_eligible").mean(), pl.col("fzg_eligible").mean())
            .sort("forecast_date")
        )
        dates = _dates(rows["forecast_date"].to_list())
        lower.plot(dates, rows["var_eligible"], color=color, label=f"{suite}: VaR", linewidth=1)
        lower.plot(
            dates,
            rows["fzg_eligible"],
            color=color,
            linestyle="--",
            label=f"{suite}: FZG",
            linewidth=1,
        )
    lower.scatter(
        _dates(common["forecast_date"].to_list()),
        [-0.05] * len(common),
        marker="|",
        color="#333333",
        s=15,
        label="Main common dates",
    )
    lower.set(
        title="(b) Fraction of scheduled candidate/scenarios with eligible forecasts",
        ylabel="Eligible fraction",
        ylim=(-0.1, 1.06),
        xlabel="Forecast date",
    )
    lower.legend(fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 0.25), ncol=3)
    for ax in (upper, lower):
        ax.grid(axis="y", alpha=0.2)
    _save(figure, output, "sample")
    sample_rows = [
        {
            "sample": "stored_panel",
            "rows": len(panel),
            "start": panel["forecast_date"].min(),
            "end": panel["forecast_date"].max(),
        },
    ]
    for scope in ("main", "external_selection"):
        for common_only in (False, True):
            selected = tables["common_sample"].filter(pl.col("scope") == scope)
            if common_only:
                selected = selected.filter(pl.col("in_common"))
            sample_rows.append(
                {
                    "sample": f"{scope}_{'common' if common_only else 'scheduled'}",
                    "rows": len(selected),
                    "start": selected["forecast_date"].min(),
                    "end": selected["forecast_date"].max(),
                }
            )
    _csv(pl.DataFrame(sample_rows), output / "sample.csv")
    return (
        "Upper: stored gap_t, expressed in percent, with the comparison date span shaded; "
        "shading does not imply every date is retained. Lower: per-date availability across "
        "all registered candidate/scenarios, not only winners; native VaR and joint FZG "
        f"eligibility differ. Black ticks are the {len(common)} fixed common dates. "
        "sample.csv distinguishes the scheduled axis, external-selection common dates and "
        "main-comparison common dates. Native eligible counts vary by model/scenario; full "
        "availability counts and common-date exclusions are retained in CSVs."
    )


def _timeline_figure(calendar: pl.DataFrame, common: pl.DataFrame, output: Path) -> str:
    common_dates = common.filter(pl.col("scope") == "main")["forecast_date"].to_list()
    rows = calendar.filter(pl.col("ose_trading_date").is_in(common_dates))
    if rows.is_empty():
        raise ValueError("No calendar rows cover the evaluated period")
    timing = rows.select(
        "ose_trading_date",
        "dst_regime",
        "us_early_close_flag",
        "us_official_close_ts_utc",
        "model_cutoff_ts_utc",
        "target_open_ts_utc",
        "ose_night_close_ts_utc",
    )
    _csv(timing, output / "timing.csv")
    jst = ZoneInfo("Asia/Tokyo")
    events: dict[str, list[str]] = {}
    night_times: set[str] = set()
    lags: set[int] = set()
    for regime in ("EDT", "EST"):
        regular = rows.filter((pl.col("dst_regime") == regime) & ~pl.col("us_early_close_flag"))
        if regular.is_empty():
            continue
        row = regular.row(0, named=True)
        lags.add(
            int((row["model_cutoff_ts_utc"] - row["us_official_close_ts_utc"]).total_seconds() / 60)
        )
        for key, label in (
            ("us_official_close_ts_utc", f"NYSE close ({regime})"),
            ("model_cutoff_ts_utc", f"Cutoff ({regime})"),
            ("ose_night_close_ts_utc", "OSE night closes"),
            ("target_open_ts_utc", "OSE day open"),
        ):
            clock = row[key].astimezone(jst).strftime("%H:%M")
            labels = events.setdefault(clock, [])
            if label not in labels:
                labels.append(label)
            if key == "ose_night_close_ts_utc":
                night_times.add(clock)
    labels = [
        "T-1\n15:45\nOSE day close /\nsettlement ref.",
        "T-1\n17:00\nOSE night\nopens",
    ]
    clocks = sorted(events)
    labels += ["\n".join(["T", clock, *events[clock]]) for clock in clocks]
    figure = _figure(12, 1.75)
    ax = figure.subplots()
    ax.set(xlim=(-0.5, len(labels) - 0.5), ylim=(-0.7, 0.8))
    ax.axis("off")
    for x, label in enumerate(labels):
        color = "#fff1db" if "Cutoff" in label else "#edf2fc" if "OSE" in label else "#f5f5f5"
        ax.text(
            x,
            0.25,
            label,
            ha="center",
            va="center",
            fontsize=10,
            bbox={"boxstyle": "square,pad=0.5", "facecolor": color, "edgecolor": "#a4a4a4"},
        )
        if x:
            ax.annotate(
                "",
                xy=(x - 0.39, 0.25),
                xytext=(x - 0.61, 0.25),
                arrowprops={"arrowstyle": "->", "color": "#9ca3af", "linewidth": 1.2},
            )
    for clock in night_times:
        end = 2 + clocks.index(clock)
        ax.plot([1, 1, end, end], [-0.18, -0.45, -0.45, -0.18], color=_COLORS[0], linewidth=1)
        ax.text(
            (1 + end) / 2,
            -0.5,
            "OSE night session",
            ha="center",
            va="top",
            color=_COLORS[0],
            fontsize=10,
        )
    lag_label = "/".join(str(lag) for lag in sorted(lags))
    _save(figure, output, "timeline")
    return (
        "Current-hours schematic in JST, not to scale: T-1 marks the preceding calendar "
        "day and T the day-session opening date in an ordinary adjacent-weekday example, "
        "not exchange trading-day labels. OSE day close (15:45) and night opening (17:00) "
        "use the schedule effective 5 November 2024, not all historical sample hours. "
        "The target is anchored to the preceding trading day's official settlement; "
        "15:45 denotes day-session close, not settlement publication time. Morning nodes "
        "use stored regular-session EDT/EST examples. The two NYSE-close and "
        "cutoff pairs are seasonal alternatives, not successive events on one date. "
        f"Cutoff = matched NYSE close + {lag_label} min. "
        "Early-close and holiday-matched sessions follow their actual official close, not these "
        "clock labels; timing.csv retains every evaluated mapping unchanged. "
        "The diagram does not add a residual-risk forecast or "
        "contemporaneous OSE night-path predictors."
    )


def _gate_figure(tables: dict[str, pl.DataFrame], output: Path) -> str:
    figure = _figure(15, 10)
    axes = figure.subplots(1, 2, width_ratios=[1.65, 1])
    rows = tables["gate_scenarios"].to_dicts()
    for ax, suite in zip(axes, ("ml_tail", "benchmark"), strict=True):
        models = tables["admissibility"].filter(pl.col("suite") == suite)["model_name"].to_list()
        infos = PASS_ALL_INFORMATION_SETS if suite == "ml_tail" else ("target_history_only",)
        keys = [(info, side) for info in infos for side in ("left_tail", "right_tail")]
        lookup = {(r["model_name"], r["information_set"], r["tail_side"]): r for r in rows}
        matrix = [
            [
                {"failed": 0, "passed": 1, "unassessable": 2}[
                    str(lookup[(model, *key)]["gate_status"])
                ]
                for key in keys
            ]
            for model in models
        ]
        ax.imshow(
            matrix,
            cmap=ListedColormap(["#f4d6b0", "#8bb9d8", "#dddddd"]),
            vmin=0,
            vmax=2,
            aspect="auto",
        )
        for i, values in enumerate(matrix):
            for j, value in enumerate(values):
                ax.text(j, i, ("F", "P", "U")[value], ha="center", va="center", fontsize=9)
        ax.set_yticks(range(len(models)), [_label(m) for m in models], fontsize=9)
        labels = [f"{'ABCD'[i // 2]}-{('L', 'R')[i % 2]}" for i in range(len(keys))]
        ax.set_xticks(range(len(keys)), labels if suite == "ml_tail" else ["Left", "Right"])
        ax.set_title(f"{len(models)} {'ML recipes' if suite == 'ml_tail' else 'external models'}")
    figure.suptitle("All-candidate native-sample gates: Kupiec + independence + GREM", fontsize=14)
    figure.supxlabel(
        "P = all scenario gates pass; F = failed; U = unassessable (not a rejection). "
        "Each model/scenario uses its own eligible dates.",
        fontsize=10,
    )
    _save(figure, output, "gates")
    return (
        "Every registered candidate is shown: ML must pass all A-D x left/right scenarios; "
        "external models must pass both tails. Unassessable is distinct from failed. The "
        "stored scenario decision combines native VaR gates and native W=500 GREM; W=250 "
        "is sensitivity only. Breach rates remain descriptive, not an extra gate. Detailed "
        "sample counts, p-values, historical GREM crossings and failure reasons are in CSV."
    )


def _global_figure(tables: dict[str, pl.DataFrame], roster: list[str], output: Path) -> str:
    figure = _figure(15, 8)
    axes = figure.subplots(2, 3, width_ratios=[1, 1.45, 0.9])
    for row_index, score in enumerate(("fzg", "quantile_loss")):
        ax, paired = axes[row_index, :2]
        values = {
            r["model_name"]: r["mean_score"]
            for r in tables["global_scores"].to_dicts()
            if r["score_name"] == score
        }
        for i, model in enumerate(roster):
            ax.plot(values[model], i, "o", color=_COLORS[i], markersize=8)
            ax.annotate(
                f"{values[model]:.4f}",
                (values[model], i),
                xytext=(0, 9),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
        ax.set_yticks(range(len(roster)), [_label(m) for m in roster], fontsize=9)
        ax.set(
            ylim=(len(roster) - 0.5, -0.5),
            title=f"Mean {'FZG' if score == 'fzg' else 'QL'} (descriptive)",
            xlabel="Lower is better",
        )
        ax.margins(x=0.2)
        rows = (
            tables["pairwise"]
            .filter((pl.col("score_name") == score) & (pl.col("configuration") == "main"))
            .to_dicts()
        )
        paired.axvline(0, color="#777777", linestyle="--", linewidth=1)
        labels = []
        for i, row in enumerate(rows):
            labels.append(f"{_label(row['model_i'])}\n- {_label(row['model_j'])}")
            if row["status"] == "ok":
                paired.hlines(
                    i,
                    _required_float(row["ci_lower"]),
                    _required_float(row["ci_upper"]),
                    color=_COLORS[0],
                    linewidth=2,
                )
                paired.plot(
                    row["mean_difference"],
                    i,
                    "o",
                    markeredgecolor=_COLORS[0],
                    markerfacecolor=_COLORS[0] if row["reject_holm_05"] else "white",
                )
                paired.text(
                    1.02,
                    i,
                    f"{row['p_value_holm']:.4f}",
                    transform=paired.get_yaxis_transform(),
                    fontsize=9,
                    va="center",
                )
            else:
                paired.text(
                    0.5,
                    i,
                    "Unavailable",
                    transform=paired.get_yaxis_transform(),
                    ha="center",
                    va="center",
                    fontsize=9,
                )
        paired.set_yticks(range(len(rows)), labels, fontsize=8)
        paired.set(
            ylim=(len(rows) - 0.5, -0.5),
            title="Paired difference: 95% pointwise CI",
            xlabel="First - second; negative favors first",
        )
        paired.text(1.02, 1.03, "Holm p", transform=paired.transAxes, fontsize=9)
    mcs = axes[0, 2]
    rows = tables["mcs"].to_dicts()
    blocks = sorted({int(_required_float(r["block_length"])) for r in rows})
    for i, model in enumerate(roster):
        for j, block in enumerate(blocks):
            result = next(
                r for r in rows if r["model_name"] == model and r["block_length"] == block
            )
            available = result["status"] == "ok"
            mcs.text(
                j,
                i,
                ("Keep" if result["survives_95"] else "Out") if available else "N/A",
                ha="center",
                va="center",
                color=_COLORS[0] if available and result["survives_95"] else "#555555",
            )
    mcs.set(xlim=(-0.5, len(blocks) - 0.5), ylim=(len(roster) - 0.5, -0.5), title="FZG 95% MCS")
    mcs.set_xticks(range(len(blocks)), [f"b={b}" for b in blocks])
    mcs.set_yticks(range(len(roster)), [_label(m) for m in roster], fontsize=8)
    axes[1, 2].axis("off")
    axes[1, 2].text(
        0,
        0.8,
        "Stored results only\n\nFilled: Holm p <= 0.05\nOpen: not rejected\n\n"
        "Pointwise CIs are not\nsimultaneous intervals.\n\nMCS is approximate,\n"
        "post-screen exploratory.",
        va="top",
        fontsize=10,
    )
    figure.suptitle("Three-model comparison on one frozen common-date panel", fontsize=14)
    _save(figure, output, "global_comparison")
    return (
        "Descriptive global FZG and quantile-loss means average A-D and both tails equally "
        "for each ML recipe; the same target-history-only reference is used across scenarios. "
        "No new mean intervals are computed. Paired intervals and Holm decisions are copied "
        "from stored main-block tests (three comparisons per score); MCS membership uses "
        "stored FZG results for all block lengths. These are screened-panel exploratory "
        "results, not proof of a unique best model or fresh-holdout performance."
    )


def _grem_figure(tables: dict[str, pl.DataFrame], roster: list[str], output: Path) -> str:
    figure = _figure(12, 8.8)
    axes = figure.subplots(len(roster), 2, sharex=True, sharey=True, squeeze=False)
    curves = tables["grem_curves"]
    dates = curves["forecast_date"].unique().sort().to_list()
    ticks = _dates([dates[i] for i in sorted({round(j * (len(dates) - 1) / 5) for j in range(6)})])
    for i, model in enumerate(roster):
        for j, side in enumerate(("left_tail", "right_tail")):
            ax = axes[i, j]
            selected = curves.filter(
                (pl.col("model_name") == model) & (pl.col("tail_side") == side)
            )
            infos = selected["information_set"].unique().sort().to_list()
            for k, info in enumerate(infos):
                label = "GJR" if len(infos) == 1 else "ABCD"[PASS_ALL_INFORMATION_SETS.index(info)]
                for window, style in ((500, "-"), (250, "--")):
                    rows = selected.filter(
                        (pl.col("information_set") == info) & (pl.col("window") == window)
                    ).sort("forecast_date")
                    ax.plot(
                        _dates(rows["forecast_date"].to_list()),
                        rows["log_grem"].to_numpy(),
                        color=_COLORS[2] if len(infos) == 1 else _COLORS[k],
                        linestyle=style,
                        linewidth=1,
                        label=f"{label}, W={window}",
                    )
            ax.axhline(math.log(20), color="black", linestyle=":", linewidth=1.2)
            ax.set_title(f"{_label(model)} | {side.replace('_', ' ')}", fontsize=10)
            ax.grid(alpha=0.15)
            if j == 0:
                ax.set_ylabel("log GREM capital")
            if j == 1:
                ax.legend(fontsize=7, ncol=2, loc="upper left")
            ax.set_xticks(ticks, [day.strftime("%Y-%m") for day in ticks])
    figure.suptitle("Native GREM monitoring: W=500 solid; W=250 dashed", fontsize=14)
    figure.supxlabel(
        "Dotted threshold = log(20). Native paths, no resets, no pooling, "
        "no accuracy ranking; W=250 is not a gate.",
        fontsize=10,
    )
    _save(figure, output, "grem")
    return (
        "Each curve is its own native monitoring process, not restricted to common-score dates. "
        "Cutoff-audited no-bet dates retain capital, and unavailable suffixes remain unavailable. "
        "W=500 solid curves underpin the stored gate; W=250 dashed curves are sensitivity only. "
        "The threshold is scenario-level 20, not a recipe-level familywise 5% guarantee. "
        "Lower capital does not mean more accurate forecasts; curves are not averaged. "
        "grem_summary.csv includes all candidates, including unavailable diagnostics."
    )


def _csv(frame: pl.DataFrame, path: Path) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=frame.columns)
        writer.writeheader()
        for row in frame.to_dicts():
            writer.writerow(
                {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()}
            )


def _latex_tables(tables: dict[str, pl.DataFrame], roster: list[str], output: Path) -> None:
    lines = ["% Frozen stored results; requires booktabs. Not inserted into the manuscript."]
    for title, headers, rows in (
        (
            "All-candidate admission",
            ["Model", "Pass / required", "Unavailable", "Admitted"],
            [
                [
                    _label(r["model_name"]),
                    f"{r['passed_scenarios']} / {r['required_scenarios']}",
                    str(r["unassessable_scenarios"]),
                    "Yes" if r["admitted"] else "No",
                ]
                for r in tables["admissibility"].to_dicts()
            ],
        ),
        (
            "Three-model descriptive scores",
            ["Model", "Score", "Mean", "N"],
            [
                [
                    _label(r["model_name"]),
                    str(r["score_name"]),
                    f"{r['mean_score']:.6f}",
                    str(r["n_common"]),
                ]
                for r in tables["global_scores"].to_dicts()
                if r["model_name"] in roster
            ],
        ),
        (
            "FZG MCS (approximate, post-screen)",
            ["Model", "Block", "MCS p", "Retained"],
            [
                [
                    _label(r["model_name"]),
                    str(r["block_length"]),
                    f"{r['p_value_mcs']:.4f}" if r["status"] == "ok" else "N/A",
                    ("Yes" if r["survives_95"] else "No") if r["status"] == "ok" else "N/A",
                ]
                for r in tables["mcs"].to_dicts()
            ],
        ),
    ):
        lines += [
            f"\n% {title}",
            r"\begin{tabular}{lrrr}",
            r"\toprule",
            " & ".join(_latex_escape(h) for h in headers) + r" \\",
            r"\midrule",
        ]
        lines += [" & ".join(_latex_escape(v) for v in row) + r" \\" for row in rows]
        lines += [r"\bottomrule", r"\end{tabular}"]
    (output / "paper_tables.tex").write_text("\n".join(lines) + "\n")
