from __future__ import annotations

import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from n225_open_gap_tail.metrics.admissibility import PASS_ALL_INFORMATION_SETS
from n225_open_gap_tail.reporting.paper_bundle_diagnostics import (
    _target_figure,
    _target_frame,
    _var_path_frame,
    render_diagnostics,
)

ROSTER = [
    "lightgbm_median_iqr_pot_gpd_unibm",
    "lightgbm_mean_rms_gamma_pot_gpd_plain_mle",
    "gjr_garch_evt",
]


def _inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(8)]
    gaps = [-0.03, -0.02, 0, 0.01, 0.02, float("nan"), 0.8, 0.015]
    panel = pl.DataFrame(
        {
            "forecast_date": days,
            "gap_t": gaps,
            "target_clean_sample": [True] * 6 + [False, True],
            "forecast_sample": [False] * 8,
            "clean_sample": [False] * 8,
            "combined_clean_start": [days[-1]] * 8,
        }
    )
    calendar = pl.DataFrame({"ose_trading_date": days[1:5]})
    common = pl.DataFrame(
        {
            "forecast_date": days[1:5],
            "scope": ["main"] * 4,
            "in_common": [True, False, False, True],
        }
    )
    rows = []
    for index, model in enumerate(ROSTER):
        for side, sign in (("left_tail", -1), ("right_tail", 1)):
            infos = (
                (PASS_ALL_INFORMATION_SETS[0], PASS_ALL_INFORMATION_SETS[-1])
                if index < 2
                else ("target_history_only",)
            )
            for info in infos:
                for i in (1, 4):
                    rows.append(
                        {
                            "model_name": model,
                            "information_set": info,
                            "tail_side": side,
                            "tail_level": 0.95,
                            "forecast_date": days[i],
                            "var_forecast": 999.0 if info == PASS_ALL_INFORMATION_SETS[0] else 0.03,
                            "realized_loss": sign * gaps[i],
                        }
                    )
    return panel, calendar, common, pl.DataFrame(rows)


def test_string_dates_match_typed_dates_without_deprecation() -> None:
    inputs = _inputs()
    expected_paths = _var_path_frame(*inputs, ROSTER)
    expected_target = _target_frame(inputs[0])
    panel, calendar, common, forecasts = [
        frame.with_columns(pl.col(pl.Date).dt.to_string("%Y-%m-%d")) for frame in inputs
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert _var_path_frame(panel, calendar, common, forecasts, ROSTER).equals(expected_paths)
        assert _target_frame(panel).equals(expected_target)


def test_render_diagnostics_d_only_signed_loss_and_calendar_holes(tmp_path: Path) -> None:
    panel, calendar, common, forecasts = _inputs()
    captions = render_diagnostics(
        panel=panel,
        calendar=calendar,
        common=common,
        forecasts=forecasts,
        roster=ROSTER,
        output=tmp_path,
    )
    assert set(captions) == {
        "var_paths_left_tail",
        "var_paths_right_tail",
        "target_tail_motivation",
    }
    assert len(list(tmp_path.glob("*.png"))) == len(list(tmp_path.glob("*.pdf"))) == 3
    paths = pl.read_csv(tmp_path / "var_paths.csv", try_parse_dates=True)
    assert paths.height == 4 * 3 * 2
    assert set(paths["information_set"]) == {PASS_ALL_INFORMATION_SETS[-1], "target_history_only"}
    holes = paths.filter(~pl.col("in_common"))
    assert holes.height == 2 * 3 * 2
    assert all(
        holes[c].null_count() == holes.height
        for c in ("var_forecast", "realized_loss", "var_pct", "loss_pct", "breach")
    )
    left = paths.filter(
        (pl.col("tail_side") == "left_tail")
        & (pl.col("model_name") == ROSTER[0])
        & pl.col("in_common")
    )
    right = paths.filter(
        (pl.col("tail_side") == "right_tail")
        & (pl.col("model_name") == ROSTER[0])
        & pl.col("in_common")
    )
    assert left["loss_pct"].to_list() == [2, -2]
    assert right["loss_pct"].to_list() == [-2, 2]
    assert left["var_pct"].to_list() == [3, 3]
    assert "without interpolation or filling" in captions["var_paths_left_tail"]
    assert "lowest equal-left/right mean FZG" in captions["var_paths_right_tail"]
    assert "equality is not a breach" in captions["var_paths_left_tail"]
    summary = pl.read_csv(tmp_path / "target_tail_summary.csv").row(0, named=True)
    assert summary["n_target"] == 6
    assert summary["date_start"] == "2024-01-01"
    assert summary["date_end"] == "2024-01-08"
    coords = pl.read_csv(tmp_path / "target_tail_coordinates.csv")
    downside = coords.filter(
        (pl.col("diagnostic") == "conditional_survival") & (pl.col("series") == "Downside")
    )
    assert downside["x"].to_list() == [2, 3]
    assert downside["y"].to_list() == [0.5, 0]
    assert "do not prove regular variation" in captions["target_tail_motivation"]


def test_var_breaches_use_each_model_signed_loss_and_strict_threshold() -> None:
    panel, calendar, common, forecasts = _inputs()
    forecasts = forecasts.with_columns(
        pl.when(pl.col("model_name") == ROSTER[0])
        .then(0.01)
        .when(pl.col("model_name") == ROSTER[1])
        .then(pl.col("realized_loss"))
        .otherwise(pl.col("var_forecast"))
        .alias("var_forecast")
    )
    paths = _var_path_frame(panel, calendar, common, forecasts, ROSTER)
    valid = paths.filter(pl.col("in_common"))
    iqr = valid.filter(pl.col("model_name") == ROSTER[0])
    assert iqr.filter(pl.col("tail_side") == "left_tail")["breach"].to_list() == [True, False]
    assert iqr.filter(pl.col("tail_side") == "right_tail")["breach"].to_list() == [False, True]
    assert not valid.filter(pl.col("model_name") != ROSTER[0])["breach"].any()
    assert paths.filter(~pl.col("in_common"))["breach"].null_count() == 12


@pytest.mark.parametrize("problem", ["missing", "duplicate", "nonfinite", "sign", "tail_level"])
def test_var_paths_reject_invalid_common_forecasts(problem: str) -> None:
    panel, calendar, common, forecasts = _inputs()
    chosen = (
        (pl.col("model_name") == ROSTER[0])
        & (pl.col("information_set") == PASS_ALL_INFORMATION_SETS[-1])
        & (pl.col("tail_side") == "left_tail")
    )
    row = forecasts.filter(chosen).head(1)
    if problem == "missing":
        forecasts = forecasts.filter(~chosen)
    elif problem == "duplicate":
        forecasts = pl.concat([forecasts, row])
    else:
        column = {"nonfinite": "var_forecast", "sign": "realized_loss", "tail_level": "tail_level"}[
            problem
        ]
        value = {"nonfinite": float("nan"), "sign": 4.0, "tail_level": 0.99}[problem]
        forecasts = forecasts.with_columns(
            pl.when(chosen).then(value).otherwise(pl.col(column)).alias(column)
        )
    with pytest.raises(ValueError, match="Missing or duplicate|Nonfinite|target/sign"):
        _var_path_frame(panel, calendar, common, forecasts, ROSTER)


@pytest.mark.parametrize(
    "problem", ["empty_common", "duplicate_common", "calendar", "target", "roster"]
)
def test_var_paths_reject_incompatible_dates_and_targets(problem: str) -> None:
    panel, calendar, common, forecasts = _inputs()
    roster = ROSTER
    if problem == "empty_common":
        common = common.with_columns(pl.lit(False).alias("in_common"))
    elif problem == "duplicate_common":
        common = pl.concat([common, common.head(1)])
    elif problem == "calendar":
        calendar = calendar.tail(1)
    elif problem == "target":
        panel = panel.with_columns(pl.lit(None, dtype=pl.Float64).alias("gap_t"))
    else:
        roster = ROSTER[:2]
    with pytest.raises(ValueError):
        _var_path_frame(panel, calendar, common, forecasts, roster)


def test_target_tail_coordinates_match_empirical_math(tmp_path: Path) -> None:
    positive = np.linspace(0.1, 12, 180)
    gap_pct = np.concatenate([-positive, positive, [0]])
    target = pl.DataFrame(
        {
            "forecast_date": [date(2023, 1, 1) + timedelta(days=i) for i in range(len(gap_pct))],
            "gap_t": gap_pct / 100,
        }
    )
    _target_figure(target, tmp_path)
    rows = pl.read_csv(tmp_path / "target_tail_coordinates.csv")
    assert set(rows["diagnostic"]) == {"density", "conditional_survival", "mean_excess", "hill"}
    for kind in ("conditional_survival", "mean_excess", "hill"):
        sample = rows.filter((pl.col("diagnostic") == kind) & (pl.col("series") == "Upside")).row(
            0, named=True
        )
        x = sample["x"]
        if kind == "conditional_survival":
            expected = np.mean(positive > x)
        elif kind == "mean_excess":
            expected = np.mean(positive[positive > x] - x)
        else:
            k = int(x)
            upper = np.sort(positive)[::-1]
            expected = np.mean(np.log(upper[:k]) - np.log(upper[k]))
        assert sample["y"] == pytest.approx(expected)


def test_target_requires_at_least_two_unique_clean_values(tmp_path: Path) -> None:
    panel, _, _, _ = _inputs()
    with pytest.raises(ValueError, match="at least two"):
        _target_frame(panel.head(1))
    target = _target_frame(panel).with_columns(pl.lit(0.0).alias("gap_t"))
    _target_figure(target, tmp_path)
    rows = pl.read_csv(tmp_path / "target_tail_coordinates.csv")
    assert set(rows["series"]) == {"empirical"}
