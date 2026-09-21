from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from arch.bootstrap import CircularBlockBootstrap
from typer.testing import CliRunner

from n225_open_gap_tail.cli import app
from n225_open_gap_tail.diagnostics.information_contrasts import (
    build_information_contrasts,
    build_information_mean_intervals,
    information_contrast_figure,
    run_information_contrasts,
)
from n225_open_gap_tail.forecasting.reevaluation import _file_sha256
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
)
from n225_open_gap_tail.metrics.stat_utils import fzg_loss, quantile_loss


def inputs() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    records: list[dict[str, object]] = []
    common: list[dict[str, object]] = []
    for t in range(160):
        day = (date(2024, 1, 1) + timedelta(days=t)).isoformat()
        common.append(
            {
                "scope": "main",
                "forecast_date": day,
                "target_session_index": t,
                "in_common": t % 10 != 4,
            }
        )
        for m, model in enumerate(("ml1", "ml2", "gjr_garch_evt")):
            infos = ("target_history_only",) if m == 2 else PASS_ALL_INFORMATION_SETS
            for j, info in enumerate(infos):
                for side in PASS_ALL_TAIL_SIDES:
                    loss = 0.03 * math.sin(t) * (1 if side == "left_tail" else -1)
                    var = 0.014 + 0.002 * math.cos(t / 3) + 0.001 * j * math.sin(t / 4) + m * 0.001
                    es = var + 0.01
                    if t == 0:
                        var, es = -0.02, -0.01  # coherent signed ES is retained
                    records.append(
                        {
                            "model_name": model,
                            "information_set": info,
                            "tail_side": side,
                            "forecast_date": day,
                            "target_session_index": t,
                            "target_family": "full_gap_settle_to_open",
                            "tail_level": 0.95,
                            "realized_loss": loss,
                            "var_forecast": var,
                            "es_forecast": es,
                            "fit_status": "ok",
                        }
                    )
    return records, common


def test_information_scores_use_two_tails_fixed_dates_and_eight_oriented_contrasts() -> None:
    records, common = inputs()
    before = deepcopy(records)
    out = build_information_contrasts(
        records, common, ml_models=("ml1", "ml2"), reference="gjr_garch_evt", reps=99
    )
    assert records == before
    assert len(out["daily_scores"]) == 144 * 9
    assert len(out["scores"]) == 18
    assert len(out["pairwise"]) == 32  # N=144: b=5 and half-b coincide; only 5/10 are distinct.
    assert all(
        row["holm_family_size"] == 8 and row["calendar_span"] == 160 for row in out["pairwise"]
    )
    for daily in out["daily_scores"]:
        source = [
            row
            for row in records
            if all(row[k] == daily[k] for k in ("model_name", "information_set", "forecast_date"))
        ]
        assert len(source) == 2
        for score in ("fzg", "quantile_loss"):
            values = [
                fzg_loss(
                    float(str(r["realized_loss"])),
                    float(str(r["var_forecast"])),
                    float(str(r["es_forecast"])),
                    0.95,
                )
                if score == "fzg"
                else quantile_loss(
                    100 * float(str(r["realized_loss"])), 100 * float(str(r["var_forecast"])), 0.95
                )
                for r in source
            ]
            assert daily[score] == pytest.approx(sum(values) / 2)
    means = {
        (row["model_name"], row["information_label"], row["score_name"]): float(
            str(row["mean_score"])
        )
        for row in out["scores"]
    }
    for row in out["pairwise"]:
        current, previous = str(row["contrast"]).split("-")
        m, s = row["recipe"], row["score_name"]
        baseline_model = "gjr_garch_evt" if previous == "reference" else m
        expected = means[(m, current, s)] - means[(baseline_model, previous, s)]
        assert row["mean_difference"] == pytest.approx(expected)
    for model in ("ml1", "ml2"):
        rows = [
            r
            for r in out["pairwise"]
            if r["recipe"] == model and r["configuration"] == "main" and r["score_name"] == "fzg"
        ]
        assert sum(float(str(r["mean_difference"])) for r in rows) == pytest.approx(
            means[(model, "D", "fzg")] - means[("gjr_garch_evt", "reference", "fzg")]
        )


def test_figure_preserves_paired_intervals_and_marks_holm_not_raw_significance() -> None:
    records, common = inputs()
    out = build_information_contrasts(
        records, common, ml_models=("ml1", "ml2"), reference="gjr_garch_evt", reps=9
    )
    rows = [
        row
        for row in out["pairwise"]
        if row["score_name"] == "fzg" and row["configuration"] == "main"
    ]
    for i, row in enumerate(rows):
        row.update(
            mean_difference=-0.02,
            ci_lower=-0.05,
            ci_upper=-0.03,
            p_value_raw=0.01,
            p_value_holm=0.01 if i == 0 else 0.08,
            reject_holm_05=i == 0,
            status="ok",
        )
    before = deepcopy(out)
    figure = information_contrast_figure(out, reference="gjr_garch_evt")
    assert out == before
    assert len(figure.axes) == 2
    assert len(figure.axes[0].collections) == 16  # Eight ML intervals, with endpoint caps.
    assert len(figure.axes[0].patches) == 1  # One reference band, not four estimates.
    paired = figure.axes[1]
    points = [line for line in paired.lines if line.get_marker() in ("o", "s")]
    assert len(points) == 8
    for i, point in enumerate(points):
        assert np.asarray(point.get_xdata())[0] == -0.02
        assert (point.get_markerfacecolor() == "white") is (i != 0)
    # Preserve even a basic interval that does not contain its point estimate.
    intervals = [
        np.asarray(collection.get_paths()[0].vertices)[:, 0]
        for collection in paired.collections[::2]
    ]
    assert len(intervals) == 8
    assert all(list(interval) == [-0.05, -0.03] for interval in intervals)
    assert [text.get_text() for text in paired.texts[:8]] == ["0.0100"] + ["0.0800"] * 7


def test_mean_intervals_reproduce_masked_calendar_bootstrap_including_reference() -> None:
    records, common = inputs()
    out = build_information_contrasts(
        records, common, ml_models=("ml1", "ml2"), reference="gjr_garch_evt", reps=99
    )
    means = [row for row in out["scores"] if row["score_name"] == "fzg"]
    native = np.full((160, 9), np.nan)
    for j, mean in enumerate(means):
        for row in out["daily_scores"]:
            if (row["model_name"], row["information_label"]) == (
                mean["model_name"],
                mean["information_label"],
            ):
                native[int(str(row["target_session_index"])), j] = float(str(row["fzg"]))
    bootstrap = CircularBlockBootstrap(5, native, seed=225)
    draws = np.array([np.nanmean(data[0][0], axis=0) for data in bootstrap.bootstrap(99)])
    assert len(out["mean_intervals"]) == 9
    for j, row in enumerate(out["mean_intervals"]):
        sample_mean = float(str(means[j]["mean_score"]))
        low, high = np.quantile(draws[:, j], [0.025, 0.975])
        assert row["mean_score"] == sample_mean
        assert row["ci_lower"] == pytest.approx(2 * sample_mean - high)
        assert row["ci_upper"] == pytest.approx(2 * sample_mean - low)
        assert row["calendar_span"] == 160 and row["reps_usable"] == 99
    out["daily_scores"].pop()
    with pytest.raises(ValueError, match="same frozen dates"):
        build_information_mean_intervals(out)


@pytest.mark.parametrize("change", ["missing", "invalid", "calendar", "duplicate_date", "empty"])
def test_information_contrasts_fail_closed_without_changing_common_dates(change: str) -> None:
    records, common = inputs()
    if change == "missing":
        records.pop(0)
    elif change == "invalid":
        records[0]["es_forecast"] = None
    elif change == "calendar":
        common[0]["target_session_index"] = 99
    elif change == "duplicate_date":
        common.append(dict(common[0]))
    else:
        common = []
    with pytest.raises(ValueError):
        build_information_contrasts(
            records, common, ml_models=("ml1", "ml2"), reference="gjr_garch_evt", reps=9
        )


def frozen_evaluation(tmp_path: Path) -> tuple[Path, Path]:
    records, common = inputs()
    source, evaluation = tmp_path / "source", tmp_path / "evaluation"
    (source / "panel").mkdir(parents=True)
    (source / "forecasts").mkdir()
    evaluation.mkdir()
    pl.DataFrame(common).select("forecast_date").write_parquet(
        source / "panel/modeling_panel.parquet"
    )
    frame = pl.DataFrame(records)
    for filename, external in (("benchmark_forecasts", True), ("ml_tail_forecasts", False)):
        frame.filter((pl.col("model_name") == "gjr_garch_evt") == external).write_parquet(
            source / f"forecasts/{filename}.parquet"
        )
    pl.DataFrame(common).write_parquet(evaluation / "common_sample.parquet")
    pl.DataFrame(
        [{"model_name": model, "suite": "ml_tail", "admitted": True} for model in ("ml1", "ml2")]
    ).write_parquet(evaluation / "admissibility.parquet")
    pl.DataFrame([{"model_name": "gjr_garch_evt", "selection_status": "ok"}]).write_parquet(
        evaluation / "references.parquet"
    )
    pl.DataFrame([{"model_roster": ["ml1", "ml2", "gjr_garch_evt"]}]).write_parquet(
        evaluation / "comparison_status.parquet"
    )
    daily = []
    for day in common:
        if not day["in_common"]:
            continue
        for model in ("ml1", "ml2", "gjr_garch_evt"):
            rows = [
                r
                for r in records
                if r["model_name"] == model and r["forecast_date"] == day["forecast_date"]
            ]
            fzg, ql, events = [], [], []
            for r in rows:
                loss, var, es = (
                    float(str(r[k])) for k in ("realized_loss", "var_forecast", "es_forecast")
                )
                fzg.append(fzg_loss(loss, var, es, 0.95))
                ql.append(quantile_loss(100 * loss, 100 * var, 0.95))
                events.append(loss > var)
            daily.append(
                {
                    "model_name": model,
                    "forecast_date": day["forecast_date"],
                    "target_session_index": day["target_session_index"],
                    "fzg": math.fsum(fzg) / len(fzg),
                    "quantile_loss": math.fsum(ql) / len(ql),
                    "exception": any(events),
                }
            )
    pl.DataFrame(daily).write_parquet(evaluation / "daily_scores.parquet")
    (evaluation / "manifest.json").write_text(
        json.dumps(
            {
                "evaluation_protocol_version": "fzg_grem_global_20260921",
                "source_run_dir": str(source),
                "source_sha256": {str(p): _file_sha256(p) for p in source.rglob("*.parquet")},
            }
        )
    )
    return source, evaluation


def test_information_cli_preserves_sources_and_writes_report_and_figure(tmp_path: Path) -> None:
    source, evaluation = frozen_evaluation(tmp_path)
    before = {
        str(p): _file_sha256(p)
        for root in (source, evaluation)
        for p in root.rglob("*")
        if p.is_file()
    }
    output = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["information-contrasts", "--evaluation-dir", str(evaluation), "--output-dir", str(output)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["common_n"] == 144
    assert manifest["global_scores_reconstructed"] is True
    assert manifest["forecast_retrained"] is manifest["mcs_computed"] is False
    assert manifest["output_rows"] == {
        "daily_scores": 1296,
        "scores": 18,
        "pairwise": 32,
        "mean_intervals": 9,
    }
    assert "quantile_loss: main block" in (output / "report.md").read_text()
    assert (output / "information_scores.png").stat().st_size > 1000
    assert (output / "information_scores.pdf").stat().st_size > 1000
    assert all(_file_sha256(Path(p)) == digest for p, digest in before.items())
    with pytest.raises(FileExistsError):
        run_information_contrasts(evaluation, output_dir=output)
    with pytest.raises(ValueError, match="outside"):
        run_information_contrasts(evaluation, output_dir=source / "nested")


@pytest.mark.parametrize("change", ["hash", "reference", "roster", "scores", "unbound", "protocol"])
def test_incompatible_frozen_inputs_are_rejected(tmp_path: Path, change: str) -> None:
    source, evaluation = frozen_evaluation(tmp_path)
    if change == "hash":
        (source / "forecasts/ml_tail_forecasts.parquet").write_bytes(b"changed")
    elif change == "reference":
        pl.DataFrame(
            [{"model_name": "gjr_garch_evt", "selection_status": "unavailable"}]
        ).write_parquet(evaluation / "references.parquet")
    elif change == "roster":
        pl.DataFrame([{"model_roster": ["ml1", "gjr_garch_evt"]}]).write_parquet(
            evaluation / "comparison_status.parquet"
        )
    elif change == "scores":
        p = evaluation / "daily_scores.parquet"
        pl.read_parquet(p).with_columns((pl.col("fzg") + 1).alias("fzg")).write_parquet(p)
    else:
        p = evaluation / "manifest.json"
        manifest = json.loads(p.read_text())
        if change == "unbound":
            manifest["source_sha256"].pop(str(source / "panel/modeling_panel.parquet"))
        else:
            manifest["evaluation_protocol_version"] = "old"
        p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run_information_contrasts(evaluation, output_dir=tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
