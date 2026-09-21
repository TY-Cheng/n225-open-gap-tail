from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from matplotlib.figure import Figure
from matplotlib.image import imread

from n225_open_gap_tail.data_lake.io import atomic_write_parquet
from n225_open_gap_tail.forecasting.reevaluation import _file_sha256
from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.reporting import paper_bundle
from n225_open_gap_tail.reporting.paper_bundle import export_paper_bundle


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    evaluation, information, source = [root / "artifacts" / n for n in ("eval", "info", "source")]
    for path in (evaluation, information, source):
        path.mkdir(parents=True)
    models = ["lightgbm_median_iqr_pot_gpd_unibm", "lightgbm_mean_rms_gamma_pot_gpd_plain_mle"]
    roster = [*models, "gjr_garch_evt"]
    candidates = [*roster, "historical_quantile", "gas_t_pot_gpd"]
    dates = ["2024-01-02", "2024-07-02", "2024-07-03"]
    common = [
        {"scope": scope, "forecast_date": day, "in_common": i != 1}
        for scope in ("main", "external_selection")
        for i, day in enumerate(dates)
    ]
    admission = [
        {
            "model_name": m,
            "suite": "ml_tail" if m in models else "benchmark",
            "required_scenarios": 8 if m in models else 2,
            "passed_scenarios": (8 if m in models else 2) if m in roster else 0,
            "unassessable_scenarios": 2 if m == "gas_t_pot_gpd" else 0,
            "admitted": m in roster,
        }
        for m in candidates
    ]
    gates, availability, curves = [], [], []
    for m in candidates:
        infos = PASS_ALL_INFORMATION_SETS if m in models else ("target_history_only",)
        for info in infos:
            for side in ("left_tail", "right_tail"):
                gates.append(
                    {
                        "model_name": m,
                        "information_set": info,
                        "tail_side": side,
                        "gate_status": "passed"
                        if m in roster
                        else "unassessable"
                        if m == "gas_t_pot_gpd"
                        else "failed",
                        "gate_reasons": ["synthetic_test"],
                    }
                )
                for day in dates:
                    availability.append(
                        {
                            "model_name": m,
                            "information_set": info,
                            "tail_side": side,
                            "forecast_date": day,
                            "var_eligible": True,
                            "fzg_eligible": day != dates[1],
                        }
                    )
                    for window in (250, 500):
                        curves.append(
                            {
                                "model_name": m,
                                "information_set": info,
                                "tail_side": side,
                                "window": window,
                                "forecast_date": day,
                                "log_grem": 0.2,
                            }
                        )
    scores = [
        {"model_name": m, "score_name": score, "mean_score": 0.5 + i / 10, "n_common": 2}
        for score in ("fzg", "quantile_loss")
        for i, m in enumerate(roster)
    ]
    pairs = [
        {
            "score_name": score,
            "configuration": "main",
            "model_i": a,
            "model_j": b,
            "status": "ok",
            "mean_difference": -0.1,
            "ci_lower": -0.2,
            "ci_upper": 0.02,
            "p_value_holm": 0.04 if j == 0 else 0.8,
            "reject_holm_05": j == 0,
        }
        for score in ("fzg", "quantile_loss")
        for j, (a, b) in enumerate(
            ((roster[0], roster[1]), (roster[0], roster[2]), (roster[1], roster[2]))
        )
    ]
    mcs = [
        {
            "model_name": m,
            "block_length": b,
            "status": "ok",
            "p_value_mcs": 0.8 if m in models else 0.01,
            "survives_95": m in models,
        }
        for b in (5, 9, 18)
        for m in roster
    ]
    data = {
        "availability": admission,
        "availability_by_date": availability,
        "gate_scenarios": gates,
        "admissibility": admission,
        "global_scores": scores,
        "pairwise": pairs,
        "mcs": mcs,
        "grem_curves": curves,
        "grem_summary": curves,
        "common_sample": common,
        "comparison_status": [{"status": "ok", "model_roster": roster}],
        "references": [{"model_name": roster[-1]}],
        "external_selection": admission,
    }
    for name, rows in data.items():
        assert isinstance(rows, list)
        atomic_write_parquet(evaluation / f"{name}.parquet", rows)
    atomic_write_parquet(
        source / "panel/modeling_panel.parquet",
        [
            {"forecast_date": d, "gap_t": (i - 1) / 100, "target_clean_sample": True}
            for i, d in enumerate(dates)
        ],
    )
    for name, selected in (("ml_tail_forecasts", models), ("benchmark_forecasts", [roster[-1]])):
        atomic_write_parquet(
            source / f"forecasts/{name}.parquet",
            [
                {
                    "model_name": model,
                    "information_set": PASS_ALL_INFORMATION_SETS[-1]
                    if model in models
                    else "target_history_only",
                    "tail_side": side,
                    "tail_level": 0.95,
                    "forecast_date": day,
                    "var_forecast": 0.02,
                    "realized_loss": (i - 1) / 100 * (-1 if side == "left_tail" else 1),
                }
                for model in selected
                for side in ("left_tail", "right_tail")
                for i, day in enumerate(dates)
            ],
        )
    calendar = []
    for i, day in enumerate(dates):
        close = datetime.fromisoformat(day).replace(hour=21 if i == 0 else 20, tzinfo=UTC)
        calendar.append(
            {
                "ose_trading_date": day,
                "dst_regime": "EST" if i == 0 else "EDT",
                "us_early_close_flag": False,
                "us_official_close_ts_utc": close,
                "model_cutoff_ts_utc": close + timedelta(minutes=15),
                "target_open_ts_utc": close.replace(hour=23, minute=45),
                "ose_night_close_ts_utc": close.replace(hour=21),
            }
        )
    atomic_write_parquet(source / "panel/calendar_map.parquet", calendar)
    (source / "manifest.json").write_text('{"combined_clean_start": "2020-01-01"}')
    hashes = {
        str(source / p): _file_sha256(source / p)
        for p in (
            "panel/modeling_panel.parquet",
            "manifest.json",
            "forecasts/ml_tail_forecasts.parquet",
            "forecasts/benchmark_forecasts.parquet",
        )
    }
    (evaluation / "manifest.json").write_text(
        json.dumps(
            {
                "evaluation_protocol_version": "fzg_grem_global_20260921",
                "source_run_dir": str(source),
                "source_sha256": hashes,
            }
        )
    )
    (information / "manifest.json").write_text(
        json.dumps(
            {
                "evaluation_dir": str(evaluation),
                "source_run_dir": str(source),
                "ml_models": models,
                "reference": roster[-1],
                "source_sha256": hashes,
            }
        )
    )
    for name in ("scores", "pairwise", "mean_intervals"):
        atomic_write_parquet(information / f"{name}.parquet", scores)
    for extension in ("png", "pdf"):
        (information / f"information_scores.{extension}").write_bytes(b"synthetic unchanged bytes")
    (information / "mean_intervals_manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": {
                    "artifacts/info/scores.parquet": _file_sha256(information / "scores.parquet")
                }
            }
        )
    )
    return evaluation, information, source


def test_paper_bundle_frozen_public_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    save = paper_bundle._save

    def check_and_save(figure: Figure, output: Path, name: str) -> None:
        if name == "timeline":
            ax = figure.axes[0]
            labels = [text.get_text() for text in ax.texts if text.get_text()]
            assert labels == [
                "T-1\n15:45\nOSE day close /\nsettlement ref.",
                "T-1\n17:00\nOSE night\nopens",
                "T\n05:00\nNYSE close (EDT)",
                "T\n05:15\nCutoff (EDT)",
                "T\n06:00\nOSE night closes\nNYSE close (EST)",
                "T\n06:15\nCutoff (EST)",
                "T\n08:45\nOSE day open",
                "OSE night session",
            ]
            assert ax.get_title() == ""
            assert not figure.texts
        save(figure, output, name)

    monkeypatch.setattr(paper_bundle, "_save", check_and_save)
    evaluation, information, source = _fixture(tmp_path)
    paths = [
        p for root in (evaluation, information, source) for p in root.rglob("*") if p.is_file()
    ]
    before = {str(p): _file_sha256(p) for p in paths}
    output = export_paper_bundle(
        evaluation_dir=evaluation, information_dir=information, output_dir=tmp_path / "bundle"
    )
    assert {str(p): _file_sha256(p) for p in paths} == before
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["inference_recomputed"] is False
    assert manifest["source_hashes_verified_after_export"] is True
    assert len(list(output.glob("*.png"))) == len(list(output.glob("*.pdf"))) == 9
    timeline = imread(output / "timeline.png")
    assert timeline.shape[0] / timeline.shape[1] < 0.25
    assert "seasonal alternatives, not successive events" in manifest["captions"]["timeline"]
    assert "schedule effective 5 November 2024" in manifest["captions"]["timeline"]
    assert pl.read_csv(output / "timing.csv").height == 3
    for name in ("var_paths_left_tail", "var_paths_right_tail", "target_tail_motivation"):
        assert name in manifest["captions"]
    assert (output / "var_paths.csv").is_file()
    assert (output / "target_tail_summary.csv").is_file()
    assert any("ml_tail_forecasts.parquet" in name for name in manifest["source_sha256"])
    for name, digest in manifest["output_sha256"].items():
        assert _file_sha256(output / name) == digest
    assert (output / "information_scores.png").read_bytes() == b"synthetic unchanged bytes"
    assert pl.read_csv(output / "gate_scenarios.csv")["gate_status"].n_unique() == 3
    assert "post-screen" in (output / "paper_tables.tex").read_text()
    assert "not an accuracy" in (output / "README.md").read_text()
    assert any(name.endswith(".parquet.metadata.json") for name in manifest["source_sha256"])
    with pytest.raises(FileExistsError, match="overwrite"):
        export_paper_bundle(
            evaluation_dir=evaluation, information_dir=information, output_dir=output
        )


@pytest.mark.parametrize(
    "failure", ["protocol", "identity", "hash", "sidecar", "unbound", "roster", "missing", "inside"]
)
def test_paper_bundle_rejects_untrusted_sources(tmp_path: Path, failure: str) -> None:
    evaluation, information, source = _fixture(tmp_path)
    path = evaluation / "manifest.json"
    manifest = json.loads(path.read_text())
    if failure == "protocol":
        manifest["evaluation_protocol_version"] = "old_fz0"
        path.write_text(json.dumps(manifest))
    elif failure == "identity":
        path = information / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["evaluation_dir"] = str(tmp_path)
        path.write_text(json.dumps(manifest))
    elif failure == "hash":
        (source / "manifest.json").write_text("{}")
    elif failure == "sidecar":
        (evaluation / "global_scores.parquet.metadata.json").unlink()
    elif failure == "unbound":
        manifest["source_sha256"] = {}
        path.write_text(json.dumps(manifest))
    elif failure == "roster":
        atomic_write_parquet(
            evaluation / "comparison_status.parquet", [{"status": "ok", "model_roster": ["wrong"]}]
        )
    elif failure == "missing":
        (evaluation / "mcs.parquet").unlink()
    output = source / "forbidden" if failure == "inside" else tmp_path / "bundle"
    with pytest.raises((ValueError, FileNotFoundError)):
        export_paper_bundle(
            evaluation_dir=evaluation, information_dir=information, output_dir=output
        )
    assert not output.exists()


def test_paper_bundle_marks_unavailable_inference(tmp_path: Path) -> None:
    evaluation, information, source = _fixture(tmp_path)
    for name in ("mcs", "pairwise"):
        path = evaluation / f"{name}.parquet"
        rows = pl.read_parquet(path).to_dicts()
        rows[0]["status"] = "unavailable_test_fixture"
        for key in ("p_value_mcs", "ci_lower", "ci_upper", "p_value_holm"):
            if key in rows[0]:
                rows[0][key] = None
        atomic_write_parquet(path, rows)
    path = source / "panel/calendar_map.parquet"
    rows = pl.read_parquet(path).with_columns(pl.lit("EDT").alias("dst_regime")).to_dicts()
    atomic_write_parquet(path, rows)
    output = export_paper_bundle(
        evaluation_dir=evaluation, information_dir=information, output_dir=tmp_path / "bundle"
    )
    assert "N/A & N/A" in (output / "paper_tables.tex").read_text()
    assert "unavailable_test_fixture" in (output / "mcs.csv").read_text()
