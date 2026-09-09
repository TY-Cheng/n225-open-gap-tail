"""Deterministic implementation checks, not a simulation study."""

import math
from datetime import date, timedelta

import pytest

from n225_open_gap_tail.metrics.grem import build_grem_artifacts, grem_sequence


def observation(day: int, loss: float, var: float = 0, es: float = 2) -> dict[str, object]:
    return {
        "forecast_date": f"2024-01-{day:02d}",
        "realized_loss": loss,
        "var_forecast": var,
        "es_forecast": es,
        "availability_known_at_cutoff": True,
    }


def test_grem_uses_past_only_taylor_bets_and_mixes_capitals() -> None:
    rows = [observation(1, 4), observation(2, 2, var=2, es=4), observation(3, 3)]
    curve = grem_sequence(rows, tail_level=0.5, window=500)
    assert [row["lambda_gree"] for row in curve] == pytest.approx([0, 1 / 3, 1 / 5])
    assert [row["lambda_grel"] for row in curve] == pytest.approx([0, 1 / 2, 2 / 5])
    assert [math.exp(row["log_grem"]) for row in curve] == pytest.approx([1, 7 / 12, 11 / 12])
    changed = grem_sequence([*rows[:2], observation(3, 300)], tail_level=0.5, window=500)
    assert changed[:2] == curve[:2]
    assert changed[2]["lambda_gree"] == curve[2]["lambda_gree"]
    assert changed[2]["lambda_grel"] == curve[2]["lambda_grel"]


def test_native_no_bet_dates_do_not_reset_capital_or_consume_betting_history() -> None:
    rows = [observation(1, 4), {**observation(2, 1000), "es_forecast": None}, observation(3, 4)]
    curve = grem_sequence(rows, tail_level=0.5, window=250)
    assert [row["input_status"] for row in curve] == ["eligible", "predictable_no_bet", "eligible"]
    assert [row["history_n"] for row in curve] == [0, 1, 1]
    assert [math.exp(row["log_grem"]) for row in curve] == pytest.approx([1, 1, 2])
    assert curve[1]["lambda_gree"] == curve[1]["lambda_grel"] == 0
    assert curve == grem_sequence(rows, tail_level=0.5, window=500)


@pytest.mark.parametrize(
    "missing",
    [
        {"realized_loss": None},
        {"availability_known_at_cutoff": False},
    ],
)
def test_unverified_missingness_leaves_an_explicit_unavailable_suffix(
    missing: dict[str, object],
) -> None:
    rows = [observation(1, 4), {**observation(2, 4), **missing}, observation(3, 4)]
    curve = grem_sequence(rows, tail_level=0.5, window=500)
    assert curve[0]["log_grem"] == 0
    assert [row["diagnostic_status"] for row in curve] == ["ok", "unavailable", "unavailable"]
    assert curve[1]["log_grem"] is None and curve[2]["log_grem"] is None
    assert curve[2]["unavailable_since"] == "2024-01-02"


def test_windows_limit_bet_history_not_cumulative_evidence_and_allow_nonpositive_es() -> None:
    rows = [
        {
            **observation(1, 0, var=-2, es=0),
            "forecast_date": str(date(2020, 1, 1) + timedelta(days=i)),
        }
        for i in range(2000)
    ]
    curve = grem_sequence(rows, tail_level=0.5, window=250)
    assert curve[-1]["history_n"] == 250
    assert curve[-1]["log_grem"] == pytest.approx(1999 * math.log(1.5))
    assert curve[-1]["running_max_log_grem"] == curve[-1]["log_grem"]
    assert (
        grem_sequence([observation(1, 1), observation(2, 1)], tail_level=0.5, window=1)[1][
            "lambda_gree"
        ]
        == 0
    )


@pytest.mark.parametrize("level,window", [(0, 500), (1, 500), (float("nan"), 500), (0.95, 0)])
def test_invalid_monitoring_parameters_are_rejected(level: float, window: int) -> None:
    with pytest.raises(ValueError):
        grem_sequence([observation(1, 1)], tail_level=level, window=window)


def test_native_dates_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError, match="dates"):
        grem_sequence([observation(2, 1), observation(1, 1)], tail_level=0.95, window=500)
    with pytest.raises(ValueError, match="dates"):
        grem_sequence([observation(1, 1), observation(1, 1)], tail_level=0.95, window=500)


@pytest.mark.parametrize("loss,var,es", [(1e308, -1e308, 0), (1, 0, 5e-324)])
def test_unrepresentable_e_statistics_are_unavailable_not_successful_no_bets(
    loss: float, var: float, es: float
) -> None:
    curve = grem_sequence(
        [observation(1, loss, var=var, es=es), observation(2, 4)],
        tail_level=0.95,
        window=500,
    )
    assert curve[0]["availability_reason"] == "nonfinite_derived_e_statistic"
    assert all(row["diagnostic_status"] == "unavailable" for row in curve)
    assert all(row["log_grem"] is None for row in curve)


def test_artifacts_keep_pre_screen_roster_and_audit_calendar_and_failure_timing() -> None:
    roster: list[dict[str, object]] = [
        {"model_name": model, "tail_side": "left_tail", "information_set": "target_history_only"}
        for model in ("known", "unknown", "empty")
    ]
    panel = {
        f"2024-01-{day:02d}": {
            "clean_sample": day != 2,
            "realized_loss": 0,
            "mapping_status": "us_holiday" if day == 2 else "normal_trading",
        }
        for day in range(1, 5)
    }
    forecasts = [
        {
            **candidate,
            **observation(day, 0, var=-2, es=-1),
            "tail_level": 0.95,
            "fit_status": "ok",
            "train_end": "2023-12-31",
            "coverage_gate_pass": False,
        }
        for candidate in roster[:2]
        for day in (1, 4)
    ]
    failures: list[dict[str, object]] = [
        {**roster[0], "forecast_date": "2024-01-03", "fit_status": "unavailable_optimizer_failed"},
        {
            **roster[1],
            "forecast_date": "2024-01-03",
            "fit_status": "unavailable_state_update_failed",
        },
    ]
    result = build_grem_artifacts(
        forecasts,
        roster=roster,
        panel_rows=panel,
        start="2024-01-01",
        target="full_gap_settle_to_open",
        tail_level=0.95,
        unavailable_records=failures,
    )
    summary = [row for row in result["grem_summary"] if row["window"] == 500]
    assert [row["model_name"] for row in summary] == ["known", "unknown", "empty"]
    assert summary[0]["input_eligible_rows"] == 2  # ES<0 is allowed, irrespective of FZ0/gates.
    assert summary[0]["predictable_no_bet_rows"] == 2
    assert summary[0]["diagnostic_status"] == "ok"
    assert summary[1]["unavailable_since"] == "2024-01-03"
    assert summary[1]["final_log_grem"] is None
    assert summary[2]["input_eligible_rows"] == 0
    assert len(result["grem_curves"]) == 3 * 4 * 2


def test_first_crossing_is_per_sequence_and_does_not_reset_evidence() -> None:
    candidate: dict[str, object] = {
        "model_name": "test",
        "tail_side": "left_tail",
        "information_set": "target_history_only",
    }
    forecasts = [
        {
            **candidate,
            **observation(day, 4),
            "fit_status": "ok",
            "tail_level": 0.5,
            "train_end": "2023-12-31",
        }
        for day in range(1, 9)
    ]
    panel = {
        str(row["forecast_date"]): {"clean_sample": True, "realized_loss": 4} for row in forecasts
    }
    result = build_grem_artifacts(
        forecasts,
        roster=[candidate],
        panel_rows=panel,
        start="2024-01-01",
        target="full_gap_settle_to_open",
        tail_level=0.5,
        unavailable_records=[],
    )
    assert all(row["first_crossing_20_date"] == "2024-01-06" for row in result["grem_summary"])
    assert all(
        row["final_log_grem"] == pytest.approx(math.log(128)) for row in result["grem_summary"]
    )
