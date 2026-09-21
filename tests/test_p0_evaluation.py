from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl
import pytest

from n225_open_gap_tail.config import load_settings
from n225_open_gap_tail.config.runtime import (
    BENCHMARK_BASELINE_MODEL_NAMES,
    ML_TAIL_MODEL_NAMES,
    PipelineRunError,
    validate_forecast_values,
)
from n225_open_gap_tail.forecasting.reevaluation import (
    _availability_records,
    _global_inference,
    reevaluate_frozen_run,
)
from n225_open_gap_tail.market.calendars import _ose_night_close_for_us_close
from n225_open_gap_tail.metrics.admissibility import select_external_references
from n225_open_gap_tail.metrics.cross_suite_dm import build_screened_comparison_artifacts
from n225_open_gap_tail.metrics.result_matrix import (
    build_metric_records,
    build_ml_tail_result_matrix_artifacts,
)
from n225_open_gap_tail.metrics.result_matrix_grouping import (
    _result_matrix_information_increment_groups,
)
from n225_open_gap_tail.metrics.stat_utils import (
    christoffersen_independence_test,
    forecast_eligible,
    fz_loss,
    index_forecast_sessions,
    moving_block_one_sided_pvalue,
)
from n225_open_gap_tail.models.benchmark import resolve_run_dir
from n225_open_gap_tail.models.ml_body import EXPERIMENT_MODEL_NAMES
from n225_open_gap_tail.panel.information_sets import registered_ml_tail_information_sets


def forecast(day: str, *, var: float = 1.0, es: float | None = 2.0) -> dict[str, object]:
    return {
        "forecast_date": day,
        "model_name": ML_TAIL_MODEL_NAMES[0],
        "tail_side": "left_tail",
        "information_set": registered_ml_tail_information_sets()[0],
        "tail_level": 0.95,
        "realized_loss": 0.5,
        "var_forecast": var,
        "es_forecast": es,
        "fit_status": "ok",
        "is_valid_forecast": True,
    }


def test_var_joint_and_fz0_have_separate_domains() -> None:
    row = {
        **forecast("2024-01-02", var=-2.0, es=-1.0),
        "fit_status": "invalid_forecast",
        "is_valid_forecast": False,
        "invalid_reason": "invalid_nonpositive_es",
    }
    assert validate_forecast_values(-2.0, -1.0) == (True, None)
    assert forecast_eligible(row) and forecast_eligible(row, score="joint")
    assert not forecast_eligible(row, score="fz0")
    assert np.isnan(fz_loss(0.5, -2.0, -1.0, 0.95))
    assert forecast_eligible(forecast("2024-01-03", es=None))
    assert not forecast_eligible(forecast("2024-01-03", var=float("nan")))
    metrics = build_metric_records([row, forecast("2024-01-03", es=None), forecast("2024-01-04")])
    assert metrics[0]["rows"] == 3
    assert metrics[0]["joint_rows"] == 2
    assert metrics[0]["fz0_rows"] == 1


def test_frozen_availability_keeps_signed_es_in_primary_score_domain() -> None:
    row = {
        **forecast("2024-01-02", var=-0.02, es=-0.01),
        "target_family": "test_target",
    }
    ledger, summary = _availability_records(
        [row],
        {"2024-01-02": {"realized_loss": 0.5}},
        target="test_target",
        level=0.95,
    )
    recorded = next(item for item in ledger if item["recorded"])
    assert recorded["availability_reason"] == "available"
    assert recorded["fzg_eligible"] is True
    assert recorded["fz0_eligible"] is False
    native = next(item for item in summary if item["recorded_rows"])
    assert native["fzg_rows"] == 1 and native["fz0_rows"] == 0


def test_frozen_global_inference_preserves_daily_panel_and_fzg_only_mcs() -> None:
    rows = [
        {
            "model_name": model,
            "forecast_date": (datetime(2024, 1, 1) + timedelta(days=day)).date().isoformat(),
            "target_session_index": 2 * day,
            "fzg": 1.0 + np.sin(day + offset),
            "quantile_loss": (1.0 + np.sin(day + offset)) / 10,
            "exception": day % 10 == 0,
        }
        for model, offset in (("first", 0), ("second", 1))
        for day in range(125)
    ]
    result = _global_inference(rows)
    assert len(result["global_scores"]) == 4
    assert all(row["n_common"] == 125 for row in result["global_scores"])
    assert len(result["pairwise"]) == 4  # two scores x distinct block lengths 5, 10
    assert all(row["calendar_span"] == 249 for row in result["pairwise"])
    assert len(result["mcs"]) == 4
    assert {row["score_name"] for row in result["mcs"]} == {"fzg"}
    with pytest.raises(ValueError, match="complete unique date/model"):
        _global_inference(rows[:-1])


def test_independence_counts_only_adjacent_target_sessions_and_sorts_rows() -> None:
    test = christoffersen_independence_test(
        breaches=np.array([False, True, False, True]), session_indices=[0, 2, 3, 4]
    )
    assert test["transition_count"] == 2
    assert test["skipped_transitions"] == 1
    assert test["n01"] == 1 and test["n10"] == 1
    rows = index_forecast_sessions(
        [forecast("2024-01-05"), forecast("2024-01-02"), forecast("2024-01-04")],
        session_dates=["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    )
    metric = build_metric_records(rows)[0]
    assert metric["christoffersen_transition_count"] == 1
    assert metric["christoffersen_skipped_transitions"] == 1
    assert metric["session_axis"] == "target_panel_sessions"


def test_bootstrap_preserves_missing_mask_and_keeps_isolated_observations() -> None:
    values = np.array([1.0, -1.0, 2.0])
    indices = [0, 2, 4]
    reps, seed, block = 99, 225, 2
    # Independent, deliberately simple reconstruction on the five-session axis.
    rng = np.random.default_rng(seed)
    starts = rng.choice(np.arange(5), size=(reps, 3))
    means = []
    centered = dict(zip(indices, values - values.mean(), strict=True))
    for replicate in starts:
        positions = [(int(start) + offset) % 5 for start in replicate for offset in range(block)][
            :5
        ]
        observed = [centered[pos] for pos in positions if pos in centered]
        if observed:
            means.append(sum(observed) / len(observed))
    expected = (1 + sum(value <= 0.5 for value in means)) / (1 + len(means))
    actual = moving_block_one_sided_pvalue(
        values,
        observed_mean=0.5,
        reps=reps,
        block_length=block,
        rng=np.random.default_rng(seed),
        session_indices=indices,
    )
    assert actual == expected
    assert actual is not None
    assert moving_block_one_sided_pvalue(
        values, rng=np.random.default_rng(seed), observed_mean=0.5, reps=reps, block_length=block
    ) == (
        moving_block_one_sided_pvalue(
            values,
            rng=np.random.default_rng(seed),
            session_indices=[10, 11, 12],
            observed_mean=0.5,
            reps=reps,
            block_length=block,
        )
    )


def test_information_comparison_does_not_silently_drop_missing_d() -> None:
    infos = registered_ml_tail_information_sets()
    rows = [{**forecast("2024-01-02"), "information_set": info} for info in infos[:3]]
    groups = _result_matrix_information_increment_groups(rows, loss_family="var_quantile_loss")
    assert groups[0]["entities"] == list(infos)
    assert groups[0]["missing_entities"] == [infos[3]]
    assert groups[0]["common_dates"] == []


def test_historical_night_close_and_migration_boundary() -> None:
    zone = ZoneInfo("Asia/Tokyo")
    for day, expected in [("2021-09-17", (5, 30)), ("2021-09-22", (6, 0)), ("2022-01-05", (6, 0))]:
        close = _ose_night_close_for_us_close(
            datetime.fromisoformat(day).replace(tzinfo=zone), zone
        )
        assert close is not None and (close.hour, close.minute) == expected
    assert _ose_night_close_for_us_close(datetime(2021, 9, 18, 5, tzinfo=zone), zone) is None


def test_external_reference_requires_both_tails_and_ignores_ml_availability() -> None:
    models = BENCHMARK_BASELINE_MODEL_NAMES[:3]
    metrics, forecasts = [], []
    for model_index, model in enumerate(models):
        for side in ("left_tail", "right_tail"):
            metrics.append(
                {
                    "model_name": model,
                    "tail_side": side,
                    "information_set": "target_history_only",
                    "rows": 500,
                    "var_breach_rate": 0.05,
                    "expected_breach_rate": 0.05,
                    "kupiec_pvalue": 0.5,
                    "christoffersen_pvalue": 0.01
                    if model_index == 2 and side == "right_tail"
                    else 0.5,
                }
            )
            for index in range(60):
                day = (datetime(2024, 1, 1) + timedelta(days=index)).date().isoformat()
                good = model_index == (0 if side == "left_tail" else 1)
                forecasts.append(
                    {
                        **forecast(day, var=0, es=1 if good else 2),
                        "model_name": model,
                        "information_set": "target_history_only",
                        "tail_side": side,
                        "realized_loss": 0.0,
                    }
                )
    selection = select_external_references(forecasts, pl.DataFrame(metrics))
    assert [row["model_name"] for row in selection["references"]] == list(models[:2])
    assert all(row["selection_common_n"] == 60 for row in selection["references"])
    assert not any(
        row["both_tail_coverage_admissible"]
        for row in selection["eligibility"]
        if row["model_name"] == models[2]
    )
    assert (
        select_external_references(forecasts + [forecast("2024-01-01")], pl.DataFrame(metrics))
        == selection
    )
    assert len(selection["eligibility"]) == 24


def test_source_guard_cannot_force_overwrite_old_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import n225_open_gap_tail.metrics.information as information

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"git_commit": "old", "config_hash": "old"}))
    sentinel = tmp_path / "forecasts" / "untouched.txt"
    sentinel.parent.mkdir()
    sentinel.write_text("original")
    monkeypatch.setattr(information, "_git_commit", lambda: "new")
    with pytest.raises(PipelineRunError, match="source revision"):
        information._assert_run_config_compatible(tmp_path, force=True)
    assert sentinel.read_text() == "original"
    assert json.loads(manifest.read_text())["git_commit"] == "old"


@pytest.mark.parametrize("new_roster", [False, True])
def test_post_gate_comparisons_use_fixed_reference_and_all_information_sets(
    new_roster: bool,
) -> None:
    roster = EXPERIMENT_MODEL_NAMES if new_roster else ML_TAIL_MODEL_NAMES
    models = EXPERIMENT_MODEL_NAMES[-2:] if new_roster else ML_TAIL_MODEL_NAMES[2:4]
    external = BENCHMARK_BASELINE_MODEL_NAMES[0]
    infos = registered_ml_tail_information_sets()
    rows = []
    for index in range(500):
        day = (datetime(2024, 1, 1) + timedelta(days=index)).date().isoformat()
        left_loss = 2.0 if index % 20 == 0 else -2.0 if index % 20 == 10 else 0.0
        for side in ("left_tail", "right_tail"):
            for model, info in [
                (external, "target_history_only"),
                *[(model, info) for model in models for info in infos],
            ]:
                if model in models and info == infos[1] and index == 150:
                    continue
                rows.append(
                    {
                        **forecast(day),
                        "model_name": model,
                        "information_set": info,
                        "tail_side": side,
                        "realized_loss": left_loss if side == "left_tail" else -left_loss,
                        "target_family": "full_gap_settle_to_open",
                        "target_session_index": index,
                    }
                )
    native = pl.from_dicts(build_metric_records(rows), infer_schema_length=None)
    result = build_screened_comparison_artifacts(rows, native, ml_model_names=roster)
    assert all(row["model_name"] == external for row in result["references"])
    assert all(row["selection_common_n"] == 500 for row in result["references"])
    post = [row for row in result["matrix"] if row["comparison_family"] == "post_gate_cross_suite"]
    assert {row["model_name"] for row in post} == {external, *models}
    assert {row["information_set"] for row in post} == set(infos)
    assert all(
        row["common_n"] == (499 if row["information_set"] == infos[1] else 500) for row in post
    )
    assert all(
        row["source_information_set"] == "target_history_only"
        for row in post
        if row["model_name"] == external
    )
    assert any(row["inference_status"] == "ok_block_bootstrap_dm" for row in result["dm"])


@pytest.mark.parametrize(
    ("new_roster", "training_multiplier"),
    [(False, None), (True, None), (True, 100.0), (True, 1.0)],
)
def test_frozen_replay_preserves_source_and_reports_missing_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    new_roster: bool,
    training_multiplier: float | None,
) -> None:
    import n225_open_gap_tail.forecasting._benchmark_suite as benchmark
    import n225_open_gap_tail.forecasting._ml_tail_suite as ml

    def no_training(**kwargs: object) -> None:
        pytest.fail("Frozen replay must not train")

    monkeypatch.setattr(benchmark, "evaluate_benchmark_suite", no_training)
    monkeypatch.setattr(ml, "evaluate_ml_tail_suite", no_training)
    source = tmp_path / "artifacts" / "tailrisk_frozen"
    roster = EXPERIMENT_MODEL_NAMES if new_roster else ML_TAIL_MODEL_NAMES
    (source / "panel").mkdir(parents=True)
    (source / "forecasts").mkdir()
    days = [(datetime(2024, 1, 1) + timedelta(days=index)).date().isoformat() for index in range(6)]
    panel = [
        {"forecast_date": day, "clean_sample": index != 3, "realized_loss": 0.5}
        for index, day in enumerate(days)
    ]
    pl.DataFrame(panel).write_parquet(source / "panel" / "modeling_panel.parquet")
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "git_commit": "original-code",
                "git_dirty": False,
                "config_hash": "original-config",
                **(
                    {"training_multiplier": training_multiplier}
                    if training_multiplier is not None
                    else {}
                ),
                **(
                    {"kind": "shared_body_rolling_forecast", "model_names": list(roster)}
                    if new_roster
                    else {}
                ),
                "model_policy": {
                    "tail_levels": [0.95],
                    "earliest_oos_start": days[0],
                    "min_train_rows": 2,
                    "min_train_exceedances": 0,
                },
                "target_policy": {"primary_target_family": "full_gap_settle_to_open"},
            }
        )
    )
    for filename, model, info in (
        ("benchmark_forecasts.parquet", BENCHMARK_BASELINE_MODEL_NAMES[0], "target_history_only"),
        (
            "ml_tail_forecasts.parquet",
            roster[-1],
            registered_ml_tail_information_sets()[0],
        ),
    ):
        rows = [
            {
                **forecast(day),
                "model_name": model,
                "information_set": info,
                "target_family": "full_gap_settle_to_open",
            }
            for day in (days[2], days[4])
        ]
        pl.DataFrame(rows).write_parquet(source / "forecasts" / filename)
    before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    from typer.testing import CliRunner

    import n225_open_gap_tail.cli as cli

    monkeypatch.setenv("ARTIFACTS_DIR", str(source.parent))
    result = tmp_path / "replay"
    args = ["reevaluate", "--run-id", source.name]
    if not new_roster:
        args.extend(["--output-dir", str(result)])
    command = CliRunner().invoke(cli.app, args)
    assert command.exit_code == 0, command.output
    if new_roster:
        outputs = [path for path in source.parent.iterdir() if path != source]
        assert len(outputs) == 1
        result = outputs[0]
        assert resolve_run_dir(load_settings(), "") == source
    assert all(path.read_bytes() == value for path, value in before.items())
    manifest = json.loads((result / "manifest.json").read_text())
    assert manifest["source_git_commit"] == "original-code"
    assert manifest["forecast_retrained"] is False
    assert manifest["source_limitations"]["training_multiplier"] == training_multiplier
    if new_roster:
        assert manifest["source_limitations"]["estimator"] == "shared_body_public_unibm_strict_fgls"
    availability = pl.read_parquet(result / "availability.parquet")
    assert availability.height == 24 + 8 * len(roster)
    assert manifest["ml_model_names"] == list(roster)
    screens = pl.read_parquet(result / "admissibility.parquet")
    assert set(roster).issubset(screens["model_name"])
    assert (result / "comparison_status.parquet").exists()
    assert (result / "pairwise.parquet").exists()
    assert (result / "mcs.parquet").exists()
    assert availability["scheduled_rows"].unique().to_list() == [3]
    native = pl.read_parquet(result / "native_metrics.parquet")
    assert native["christoffersen_transition_count"].to_list() == [0, 0]
    assert native["rows"].to_list() == [2, 2]
    grem = pl.read_parquet(result / "grem_summary.parquet")
    assert grem.height == 2 * (24 + 8 * len(roster))
    assert set(grem["window"]) == {250, 500}
    assert set(roster).issubset(grem["model_name"])
    assert manifest["grem_policy"]["used_for_selection"] is True
    assert manifest["grem_policy"]["selection_window"] == 500
    assert manifest["grem_policy"]["sensitivity_window_not_a_gate"] == 250
    assert manifest["source_hashes_verified_after_evaluation"] is True
    assert manifest["evaluation_policy"]["mcs"] == "FZG_only_TR_nominal95_approximate_exploratory"
    assert not (result / "joint_murphy_samples.parquet").exists()
    # These candidates fail N>=450, but GREM must still retain their input timelines.
    assert not any(native["var_gate_pass"])
    curves = pl.read_parquet(result / "grem_curves.parquet")
    assert curves["forecast_date"].n_unique() == 4
    assert set(curves["window"]) == {250, 500}
    with pytest.raises(FileExistsError):
        reevaluate_frozen_run(source, output_dir=result)
    with pytest.raises(ValueError, match="outside"):
        reevaluate_frozen_run(source, output_dir=source / "replay")
    if new_roster:
        bad_manifest = json.loads((source / "manifest.json").read_text())
        bad_manifest["model_names"] = list(roster[:-1])
        (source / "manifest.json").write_text(json.dumps(bad_manifest))
        with pytest.raises(ValueError, match="22-model roster"):
            reevaluate_frozen_run(source, output_dir=tmp_path / "bad_roster")


def test_new_roster_common_dates_keep_all_22_and_separate_es_eligibility() -> None:
    infos = registered_ml_tail_information_sets()
    rows = [
        {
            **forecast(day),
            "model_name": model,
            "information_set": info,
            "es_forecast": None
            if model == EXPERIMENT_MODEL_NAMES[-1] and day.endswith("03")
            else 2.0,
        }
        for day in ("2024-01-01", "2024-01-02", "2024-01-03")
        for model in EXPERIMENT_MODEL_NAMES
        for info in infos
        # A missing model in D must not shrink that model-comparison roster.
        if not (model == EXPERIMENT_MODEL_NAMES[-2] and info == infos[-1])
    ]
    result = build_ml_tail_result_matrix_artifacts(rows, model_names=EXPERIMENT_MODEL_NAMES)
    matrix = pl.from_dicts(
        cast(list[dict[str, object]], result["matrix"]), infer_schema_length=None
    )
    model_rows = matrix.filter(pl.col("comparison_axis") == "model_family")
    assert set(model_rows["model_name"]) == set(EXPERIMENT_MODEL_NAMES)
    a = model_rows.filter(pl.col("information_set") == infos[0])
    assert a.filter(pl.col("loss_family") == "var_quantile_loss")[
        "common_n"
    ].unique().to_list() == [3]
    assert a.filter(pl.col("loss_family") == "var_es_fz_loss")["common_n"].unique().to_list() == [2]
    d = model_rows.filter(pl.col("information_set") == infos[-1])
    assert d["common_n"].unique().to_list() == [0]
    assert set(d["model_name"]) == set(EXPERIMENT_MODEL_NAMES)


def test_replay_rejects_duplicate_or_mismatched_frozen_targets() -> None:
    day = "2024-01-02"
    target = "full_gap_settle_to_open"
    row = {**forecast(day), "target_family": target}
    scheduled = {day: {"realized_loss": 0.5}}
    with pytest.raises(ValueError, match="Duplicate"):
        _availability_records([row, row], scheduled, target=target, level=0.95)
    with pytest.raises(ValueError, match="disagrees"):
        _availability_records([{**row, "realized_loss": 0.1}], scheduled, target=target, level=0.95)
    with pytest.raises(ValueError, match="outside"):
        _availability_records(
            [{**row, "forecast_date": "2024-01-03"}], scheduled, target=target, level=0.95
        )


def test_unknown_git_state_cannot_reuse_computation_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import n225_open_gap_tail.config.git as git

    def unavailable(*args: object, **kwargs: object) -> None:
        raise OSError("git unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert git._git_source_dirty() is True
