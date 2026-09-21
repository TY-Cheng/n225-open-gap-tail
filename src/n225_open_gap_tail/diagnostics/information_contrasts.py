"""Matched information contrasts for an already frozen admitted-model roster."""

from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from n225_open_gap_tail.config.git import _git_commit, _git_dirty
from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.config.runtime import _required_float
from n225_open_gap_tail.data_lake.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.forecasting.reevaluation import _file_sha256
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_BENCHMARK_INFORMATION_SET,
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
)
from n225_open_gap_tail.metrics.robust_comparison import _index_forecasts, _scores
from n225_open_gap_tail.metrics.score_inference import _joint_mean_draws, build_score_inference
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, index_forecast_sessions

type Row = dict[str, object]


def build_information_contrasts(
    forecasts: list[Row],
    common_sample: list[Row],
    *,
    ml_models: tuple[str, ...],
    reference: str,
    reps: int = 9999,
) -> dict[str, list[Row]]:
    """Keep the inherited joint dates; never reselect models or shrink the sample."""
    if not ml_models or len(set(ml_models)) != len(ml_models) or reference in ml_models:
        raise ValueError("Require distinct admitted ML recipes and an external reference")
    panel = sorted(
        (row for row in common_sample if row["scope"] == "main" and row["in_common"] is True),
        key=lambda row: str(row["forecast_date"]),
    )
    dates = [str(row["forecast_date"]) for row in panel]
    if not dates or len(set(dates)) != len(dates):
        raise ValueError("Require nonempty unique frozen common dates")
    indices = [int(_required_float(row["target_session_index"])) for row in panel]
    selected = [row for row in forecasts if row["model_name"] in (*ml_models, reference)]
    indexed, sessions = _index_forecasts(selected, ml_models)
    members = [(model, info) for model in ml_models for info in PASS_ALL_INFORMATION_SETS]
    members.append((reference, PASS_ALL_BENCHMARK_INFORMATION_SET))
    labels = [f"{model}:{'ABCD'[i % 4]}" for i, (model, _) in enumerate(members[:-1])]
    labels.append(reference)
    daily: list[Row] = []
    for day, position in zip(dates, indices, strict=True):
        if sessions.get(day) != position:
            raise ValueError(f"Frozen common calendar disagrees with forecasts: {day}")
        for column, (model, info) in enumerate(members):
            records = [
                indexed.get((model, info, side), {}).get(day, {}) for side in PASS_ALL_TAIL_SIDES
            ]
            if not all(forecast_eligible(row, score="fzg") for row in records):
                raise ValueError(
                    f"Missing/ineligible frozen common forecast: {model}, {info}, {day}"
                )
            scores = [_scores(row) for row in records]
            daily.append(
                {
                    "model_name": model,
                    "information_set": info,
                    "information_label": "reference" if model == reference else "ABCD"[column % 4],
                    "forecast_date": day,
                    "target_session_index": position,
                    "fzg": math.fsum(score[0] for score in scores) / 2,
                    "quantile_loss": math.fsum(score[1] for score in scores) / 2,
                    "exception": any(score[2] for score in scores),
                }
            )
    pairs = [
        (base + step, len(members) - 1 if step == 0 else base + step - 1)
        for base in range(0, 4 * len(ml_models), 4)
        for step in range(4)
    ]
    definitions = {
        (labels[i], labels[j]): (members[i][0], ("A-reference", "B-A", "C-B", "D-C")[i % 4])
        for i, j in pairs
    }
    flags = np.array([row["exception"] for row in daily], dtype=bool).reshape(len(dates), -1)
    output: dict[str, list[Row]] = {"daily_scores": daily, "scores": [], "pairwise": []}
    for score in ("fzg", "quantile_loss"):
        values = np.array([_required_float(row[score]) for row in daily]).reshape(len(dates), -1)
        for column, (model, info) in enumerate(members):
            output["scores"].append(
                {
                    "model_name": model,
                    "information_set": info,
                    "information_label": daily[column]["information_label"],
                    "score_name": score,
                    "mean_score": float(values[:, column].mean()),
                    "n_common": len(dates),
                    "date_start": dates[0],
                    "date_end": dates[-1],
                    "score_units": "percentage_points",
                    "tail_weights": "equal_two",
                }
            )
        inference = build_score_inference(
            values,
            model_names=labels,
            session_indices=indices,
            exception_flags=flags,
            score_name=score,
            reps=reps,
            pairs=pairs,
        )
        for row in inference["pairwise"]:
            model, contrast = definitions[(str(row["model_i"]), str(row["model_j"]))]
            output["pairwise"].append(
                {
                    **row,
                    "recipe": model,
                    "contrast": contrast,
                    "holm_family_size": len(pairs),
                    "holm_family": "information_contrasts_not_global_pairs",
                }
            )
    output["mean_intervals"] = build_information_mean_intervals(output)
    return output


def build_information_mean_intervals(outputs: dict[str, list[Row]]) -> list[Row]:
    """Pointwise FZG-level intervals using the existing main-block calendar-mask design."""
    means = [row for row in outputs["scores"] if row["score_name"] == "fzg"]
    main = next(
        row
        for row in outputs["pairwise"]
        if row["score_name"] == "fzg" and row["configuration"] == "main"
    )
    daily = pl.DataFrame(outputs["daily_scores"])
    columns = [
        daily.filter(
            (pl.col("model_name") == row["model_name"])
            & (pl.col("information_label") == row["information_label"])
        ).sort("forecast_date")
        for row in means
    ]
    dates = columns[0].select("forecast_date", "target_session_index")
    if any(not column.select(dates.columns).equals(dates) for column in columns):
        raise ValueError("Mean intervals require the same frozen dates for every configuration")
    values = np.column_stack([column["fzg"].to_numpy() for column in columns])
    draws = _joint_mean_draws(
        values,
        dates["target_session_index"].to_list(),
        int(_required_float(main["block_length"])),
        int(_required_float(main["reps_requested"])),
        int(_required_float(main["seed"])),
    )
    bounds = np.quantile(draws, [0.025, 0.975], axis=0) if len(draws) else None
    return [
        {
            **row,
            **{
                key: main[key]
                for key in ("block_length", "calendar_span", "reps_requested", "seed", "scope")
            },
            "reps_usable": len(draws),
            "confidence_level": 0.95,
            "ci_kind": "pointwise_basic",
            "ci_lower": None
            if bounds is None
            else 2 * _required_float(row["mean_score"]) - float(bounds[1, i]),
            "ci_upper": None
            if bounds is None
            else 2 * _required_float(row["mean_score"]) - float(bounds[0, i]),
            "status": "ok" if bounds is not None else "unavailable_mean_bootstrap",
        }
        for i, row in enumerate(means)
    ]


def run_information_contrasts(evaluation_dir: Path, *, output_dir: Path) -> Path:
    """Read the frozen selection and forecasts, write only a new diagnostic directory."""
    started = time.perf_counter()
    evaluation_dir, output_dir = evaluation_dir.resolve(), output_dir.resolve()
    manifest_path = evaluation_dir / "manifest.json"
    parent = json.loads(manifest_path.read_text())
    if parent.get("evaluation_protocol_version") != "fzg_grem_global_20260921":
        raise ValueError("Require the frozen FZG/GREM global evaluation protocol")
    source = Path(parent["source_run_dir"]).resolve()
    if any(output_dir == path or path in output_dir.parents for path in (source, evaluation_dir)):
        raise ValueError("Information-contrast output must be outside frozen input directories")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite information-contrast output: {output_dir}")
    hashes = dict(parent["source_sha256"])
    filenames = (
        "admissibility",
        "references",
        "comparison_status",
        "common_sample",
        "daily_scores",
    )
    input_paths = [manifest_path, *(evaluation_dir / f"{name}.parquet" for name in filenames)]
    hashes.update({str(path): _file_sha256(path) for path in input_paths})
    for path, digest in hashes.items():
        if _file_sha256(Path(path)) != digest:
            raise ValueError(f"Frozen input hash mismatch: {path}")
    tables = {name: pl.read_parquet(evaluation_dir / f"{name}.parquet") for name in filenames}
    ml_models = tuple(
        str(row["model_name"])
        for row in tables["admissibility"].to_dicts()
        if row["suite"] == "ml_tail" and row["admitted"] is True
    )
    refs = tables["references"].to_dicts()
    if len(refs) != 1 or refs[0]["selection_status"] != "ok":
        raise ValueError("Frozen evaluation has no selected external reference")
    reference = str(refs[0]["model_name"])
    status = tables["comparison_status"].to_dicts()
    if len(status) != 1 or status[0]["model_roster"] != [*ml_models, reference]:
        raise ValueError("Frozen comparison roster disagrees with admission/reference")
    panel_path = source / "panel/modeling_panel.parquet"
    paths = [
        source / "forecasts" / name
        for name in ("ml_tail_forecasts.parquet", "benchmark_forecasts.parquet")
    ]
    if any(str(path) not in hashes for path in (panel_path, *paths)):
        raise ValueError("Frozen manifest does not bind the panel and forecast inputs")
    forecasts = [
        row
        for path in paths
        for row in pl.read_parquet(path).to_dicts()
        if row["model_name"] in (*ml_models, reference)
    ]
    forecasts = index_forecast_sessions(
        forecasts,
        session_dates=pl.read_parquet(panel_path, columns=["forecast_date"])
        .sort("forecast_date")["forecast_date"]
        .to_list(),
    )
    outputs = build_information_contrasts(
        forecasts,
        tables["common_sample"].to_dicts(),
        ml_models=ml_models,
        reference=reference,
    )
    # Re-aggregating the information-level scores must recover the old global panel.
    reconstructed = (
        pl.DataFrame(outputs["daily_scores"])
        .group_by("model_name", "forecast_date")
        .agg(
            pl.col("fzg", "quantile_loss").mean(),
            pl.col("exception").any(),
            pl.col("target_session_index").first(),
        )
        .sort("model_name", "forecast_date")
    )
    frozen = tables["daily_scores"].sort("model_name", "forecast_date")
    keys = ["model_name", "forecast_date", "target_session_index", "exception"]
    if not reconstructed.select(keys).equals(frozen.select(keys)) or not np.allclose(
        reconstructed.select("fzg", "quantile_loss").to_numpy(),
        frozen.select("fzg", "quantile_loss").to_numpy(),
        rtol=1e-12,
        atol=1e-14,
    ):
        raise ValueError("Information scores do not reconstruct the frozen global scores")
    if any(_file_sha256(Path(path)) != digest for path, digest in hashes.items()):
        raise RuntimeError("Frozen inputs changed during information-contrast evaluation")
    output_dir.mkdir(parents=True)
    for name, rows in outputs.items():
        _write_parquet(output_dir / f"{name}.parquet", rows)
    pl.DataFrame(outputs["pairwise"]).write_csv(output_dir / "pairwise.csv")
    write_information_report(outputs, output_dir=output_dir, reference=reference)
    package = Path(__file__).resolve().parents[1]
    _write_json(
        output_dir / "manifest.json",
        {
            "kind": "frozen_information_contrasts",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "evaluation_dir": str(evaluation_dir),
            "source_run_dir": str(source),
            "source_sha256": hashes,
            "source_hashes_verified_after_evaluation": True,
            "global_scores_reconstructed": True,
            "forecast_retrained": False,
            "gates_recomputed": False,
            "reference_reselected": False,
            "mcs_computed": False,
            "ml_models": list(ml_models),
            "reference": reference,
            "common_n": reconstructed["forecast_date"].n_unique(),
            "policy": {
                "contrasts": ["A-reference", "B-A", "C-B", "D-C"],
                "tail_weights": "equal_two",
                "date_weights": "equal",
                "scores": ["fzg", "quantile_loss"],
                "score_units": "percentage_points",
                "holm": "all_contrasts_by_score_and_block_separate_from_global_pairs",
                "inference": "two_sided_centered_CBB_pointwise_basic95_reps9999_seed225",
                "mean_intervals": "fzg_pointwise_basic95_main_block_same_joint_calendar_mask",
                "blocks": "max(5,round(N**(1/3)))_half_and_double",
                "floors": "N120_and_five_exception_dates_union_of_the_compared_two_tail_series",
                "scope": "post_screen_exploratory_no_causal_or_current_OSE_path_increment",
            },
            "output_rows": {name: len(rows) for name, rows in outputs.items()},
            "elapsed_seconds": time.perf_counter() - started,
            "evaluator_git_commit": _git_commit(),
            "evaluator_git_dirty": _git_dirty(),
            "evaluation_source_sha256": {
                str(path.relative_to(package)): _file_sha256(path)
                for path in sorted(package.rglob("*.py"))
            },
        },
    )
    return output_dir


def information_contrast_figure(outputs: dict[str, list[Row]], *, reference: str) -> Figure:
    """Show descriptive levels alongside the stored paired inference, without refitting."""
    means = pl.DataFrame(outputs["scores"])
    figure = Figure(figsize=(13.5, 6.4), layout="constrained")
    FigureCanvasAgg(figure)
    ax, paired = figure.subplots(1, 2, width_ratios=[1, 1.25])
    fzg = means.filter(pl.col("score_name") == "fzg")
    models = [m for m in fzg["model_name"].unique(maintain_order=True).to_list() if m != reference]
    styles = {
        model: (("#1f77b4", "#d97706")[i % 2], ("o", "s")[i % 2]) for i, model in enumerate(models)
    }
    labels = {
        "lightgbm_median_iqr_pot_gpd_unibm": "Median–IQR–UniBM",
        "lightgbm_mean_rms_gamma_pot_gpd_plain_mle": "Mean–RMS-Gamma–MLE",
    }
    for model in [*models, reference]:
        model_scores = fzg.filter(pl.col("model_name") == model).sort("information_label")
        intervals = [row for row in outputs["mean_intervals"] if row["model_name"] == model]
        label = labels.get(model, display_model_label(model))
        if model == reference:
            if intervals[0]["status"] == "ok":
                ax.axhspan(
                    _required_float(intervals[0]["ci_lower"]),
                    _required_float(intervals[0]["ci_upper"]),
                    color="#555555",
                    alpha=0.10,
                )
            ax.axhline(model_scores["mean_score"][0], linestyle="--", color="#555555", label=label)
        else:
            color, marker = styles[model]
            offset = (models.index(model) - (len(models) - 1) / 2) * 0.10
            for row in intervals:
                if row["status"] == "ok":
                    x = "ABCD".index(str(row["information_label"])) + offset
                    lower, upper = (_required_float(row[key]) for key in ("ci_lower", "ci_upper"))
                    ax.vlines(x, lower, upper, color=color, linewidth=1.3, alpha=0.8)
                    ax.hlines([lower, upper], x - 0.045, x + 0.045, color=color, linewidth=1.3)
            ax.plot(
                np.arange(4) + offset,
                model_scores["mean_score"].to_list(),
                marker=marker,
                color=color,
                linewidth=2,
                label=label,
            )
    ax.set_xticks(
        range(4),
        [
            "A\nJapan\nhistory",
            "B\n+ U.S.-close\nbundle",
            "C\n+ Japan\nproxies",
            "D\n+ Asia\nproxies",
        ],
    )
    ax.set_ylabel("Mean FZG (lower is better)")
    ax.set_title("(a) Mean FZG: pointwise 95% CI", fontsize=12, pad=16)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(fontsize=9, loc="lower left", frameon=False)

    rows = [
        row
        for row in outputs["pairwise"]
        if row["score_name"] == "fzg" and row["configuration"] == "main"
    ]
    contrasts = ("A-reference", "B-A", "C-B", "D-C")
    paired.axvline(0, color="#555555", linestyle="--", linewidth=1)
    for row in rows:
        model = str(row["recipe"])
        color, marker = styles[model]
        y = (
            contrasts.index(str(row["contrast"]))
            + (models.index(model) - (len(models) - 1) / 2) * 0.32
        )
        if row["status"] == "ok":
            lower, upper = (_required_float(row[key]) for key in ("ci_lower", "ci_upper"))
            # Basic intervals need not contain the estimate; draw their endpoints unchanged.
            paired.hlines(y, lower, upper, color=color, linewidth=1.8)
            paired.vlines([lower, upper], y - 0.055, y + 0.055, color=color, linewidth=1.3)
            paired.plot(
                _required_float(row["mean_difference"]),
                y,
                marker=marker,
                linestyle="none",
                markersize=7,
                markeredgecolor=color,
                markeredgewidth=1.5,
                markerfacecolor=color if row["reject_holm_05"] is True else "white",
            )
        p_label = (
            "n/a" if row["p_value_holm"] is None else f"{_required_float(row['p_value_holm']):.4f}"
        )
        paired.text(
            1.03, y, p_label, transform=paired.get_yaxis_transform(), va="center", color=color
        )
    paired.text(1.03, 1.02, "Holm p", transform=paired.transAxes, fontsize=10)
    paired.set_yticks(
        range(4), [f"A − {display_model_label(reference)}", "B − A", "C − B", "D − C"]
    )
    paired.set_ylim(3.55, -0.65)
    paired.set_xlabel("Mean FZG difference (first − second)\nNegative favors the first member")
    paired.set_title("(b) Paired differences: pointwise 95% CI", fontsize=12, pad=16)
    paired.grid(axis="x", alpha=0.2)
    for axis in (ax, paired):
        axis.spines[["top", "right"]].set_visible(False)
    first = outputs["scores"][0]
    figure.suptitle(
        "Information sets and paired FZG contrasts\n"
        f"{first['n_common']} common dates · {first['date_start']} to {first['date_end']}"
        " · equal left/right weights",
        fontsize=13,
    )
    figure.supxlabel(
        f"Both panels: {int(_required_float(rows[0]['reps_requested'])):,} circular-block draws; "
        f"b={rows[0]['block_length']}. Pointwise 95% CIs (not simultaneous); gray band: GJR.\n"
        f"Panel (b) filled: Holm p ≤ 0.05 across {len(rows)} FZG contrasts; open: not rejected. "
        "Post-screen exploratory inference.",
        fontsize=10,
    )
    return figure


def write_information_report(
    outputs: dict[str, list[Row]], *, output_dir: Path, reference: str
) -> None:
    """One two-panel FZG figure and compact tables; no new model-selection exercise."""
    figure = information_contrast_figure(outputs, reference=reference)
    for extension in ("png", "pdf"):
        figure.savefig(output_dir / f"information_scores.{extension}", dpi=180)
    first = outputs["scores"][0]
    lines = [
        "# Frozen information contrasts",
        "",
        f"N={first['n_common']}; {first['date_start']}–{first['date_end']}. "
        "Same frozen roster/dates; equal tail weights; no training, gates or reference changes.",
        "",
        "![A–D mean FZG and paired differences with pointwise 95% intervals]"
        "(information_scores.png)",
        "",
        "Left: sample means with pointwise 95% basic CIs; the gray band is the single GJR CI. "
        "ML marks are slightly offset horizontally for readability only. "
        "The main-block bootstrap jointly resamples scores and the native-calendar mask; "
        "point estimates remain the original sample means, not bootstrap bias-corrected means. "
        "Right: stored paired differences and intervals; "
        "negative favors the first member. Filled symbols indicate Holm p ≤ 0.05, "
        "not merely an interval excluding zero. Two-sided centered CBB; "
        "pointwise 95% basic intervals, not simultaneous. Holm is within this table's "
        "contrasts for each score/block, separate from the existing global comparisons.",
        "",
    ]

    def number(value: object, digits: int = 6) -> str:
        return "n/a" if value is None else f"{_required_float(value):.{digits}f}"

    lines.extend(
        [
            "## fzg: pointwise mean intervals",
            "",
            "| Recipe | Information set | Sample mean | 95% basic CI | Status |",
            "|---|---|---:|---|---|",
        ]
    )
    for row in outputs["mean_intervals"]:
        lines.append(
            f"| {display_model_label(row['model_name'])} | {row['information_label']} | "
            f"{number(row['mean_score'])} | [{number(row['ci_lower'])}, "
            f"{number(row['ci_upper'])}] | {row['status']} |"
        )
    lines.append("")

    for score in ("fzg", "quantile_loss"):
        lines.extend(
            [
                f"## {score}: main block",
                "",
                "| Recipe | Contrast | Difference | 95% CI | Raw p | Holm p | Status |",
                "|---|---|---:|---|---:|---:|---|",
            ]
        )
        rows = [row for row in outputs["pairwise"] if row["score_name"] == score]
        for row in rows:
            if row["configuration"] == "main":
                lines.append(
                    f"| {display_model_label(row['recipe'])} | {row['contrast']} | "
                    f"{number(row['mean_difference'])} | [{number(row['ci_lower'])}, "
                    f"{number(row['ci_upper'])}] | {number(row['p_value_raw'], 4)} | "
                    f"{number(row['p_value_holm'], 4)} | {row['status']} |"
                )
        lengths = sorted({int(_required_float(row["block_length"])) for row in rows})
        lines.extend(
            [
                "",
                "### Block-length sensitivity: Holm p",
                "",
                "| Recipe | Contrast | " + " | ".join(f"b={b}" for b in lengths) + " |",
                "|---|---|" + "---:|" * len(lengths),
            ]
        )
        for row in rows:
            if row["configuration"] == "main":
                matches = [
                    r
                    for r in rows
                    if r["recipe"] == row["recipe"] and r["contrast"] == row["contrast"]
                ]
                ordered = sorted(matches, key=lambda r: _required_float(r["block_length"]))
                lines.append(
                    f"| {display_model_label(row['recipe'])} | {row['contrast']} | "
                    + " | ".join(number(r["p_value_holm"], 4) for r in ordered)
                    + " |"
                )
        lines.append("")
    lines.extend(
        [
            "B−A adds a U.S.-close information bundle, not solely U.S. equity returns. "
            "A−reference changes both model and inputs. No causal interpretation, "
            "no claim beyond contemporaneous OSE night-session prices, and no correction "
            "for prior gate/reference selection or repeated OOS inspection.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines))
