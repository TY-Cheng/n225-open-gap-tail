from __future__ import annotations

import math
from copy import deepcopy

import pytest

from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_INFORMATION_SETS,
    PASS_ALL_TAIL_SIDES,
    pass_all_row_passes,
)


def test_var_admission_does_not_use_the_descriptive_breach_band() -> None:
    assert pass_all_row_passes(
        {"rows": 450, "var_breach_rate": 0.2, "kupiec_pvalue": 0.2, "christoffersen_pvalue": 0.4}
    )


def native_rows(model: str, *, external: bool = False) -> list[dict[str, object]]:
    return [
        {
            "model_name": model,
            "information_set": info,
            "tail_side": side,
            "rows": 500,
            "var_breach_rate": 0.05,
            "kupiec_pvalue": 0.2,
            "christoffersen_pvalue": 0.4,
        }
        for info in (("target_history_only",) if external else PASS_ALL_INFORMATION_SETS)
        for side in PASS_ALL_TAIL_SIDES
    ]


def grem_rows(native: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            **row,
            "window": 500,
            "diagnostic_status": "ok",
            "processed_eligible_rows": 450,
            "input_eligible_rows": 450,
            "unavailable_rows": 0,
            "unavailable_since": None,
            "predictable_no_bet_rows": 50,
            "monitoring_axis_rows": 500,
            "valid_prefix_peak_log_grem": math.log(2),
            "final_log_grem": math.log(1),
            "first_crossing_20_date": None,
        }
        for row in native
    ]


def test_admission_uses_all_eight_native_scenarios_and_historical_w500_alarm() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("good") + native_rows("alarm") + native_rows("short")
    grem = grem_rows(native)
    grem.append({**grem[0], "window": 250, "valid_prefix_peak_log_grem": math.log(100)})
    grem[8]["first_crossing_20_date"] = "2024-01-02"
    grem[8]["valid_prefix_peak_log_grem"] = math.log(21)
    grem[-2]["processed_eligible_rows"] = 449
    result = build_robust_comparison_artifacts(
        [], native, grem, ml_model_names=("good", "alarm", "short")
    )
    status = {row["model_name"]: row for row in result["admissibility"]}
    assert status["good"]["admitted"] is True
    assert status["alarm"]["admission_status"] == "failed"
    assert status["short"]["admission_status"] == "unassessable"
    assert len(result["gate_scenarios"]) == 48  # Three recipes plus 12 two-tail externals.
    assert result["references"][0]["selection_status"] == "no_admitted_external"


def forecasts_for(
    model: str, *, external: bool = False, var: float = 0, es: float = 0
) -> list[dict[str, object]]:
    return [
        {
            "model_name": model,
            "information_set": info,
            "tail_side": side,
            "forecast_date": f"2024-01-0{day}",
            "target_session_index": day * 2,
            "target_family": "full_gap_settle_to_open",
            "tail_level": 0.95,
            "realized_loss": 0.01 if side == "left_tail" else -0.01,
            "var_forecast": var,
            "es_forecast": es,
            "fit_status": "ok",
        }
        for day in (2, 3)
        for info in (("target_history_only",) if external else PASS_ALL_INFORMATION_SETS)
        for side in PASS_ALL_TAIL_SIDES
    ]


def test_reference_uses_external_two_tail_dates_before_fixed_eight_scenario_panel() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml") + native_rows("garch_t", external=True)
    native += native_rows("gjr_garch_evt", external=True)
    forecasts = forecasts_for("ml") + forecasts_for("garch_t", external=True)
    forecasts += forecasts_for("gjr_garch_evt", external=True, var=0.02, es=0.02)
    forecasts.pop(0)  # ML missing one scenario: only day 3 is globally common.
    result = build_robust_comparison_artifacts(
        forecasts, native, grem_rows(native), ml_model_names=("ml",)
    )
    reference = result["references"][0]
    assert reference["model_name"] == "gjr_garch_evt"
    assert reference["common_n"] == 2
    assert reference["mean_fzg"] == pytest.approx(0.6662191695169728)
    assert {row["forecast_date"] for row in result["daily_scores"]} == {"2024-01-03"}
    daily = {row["model_name"]: row for row in result["daily_scores"]}
    assert daily["ml"]["fzg"] == pytest.approx(5.5)
    assert daily["ml"]["quantile_loss"] == pytest.approx(0.5)
    assert daily["ml"]["exception"] is True
    assert daily["ml"]["target_session_index"] == 6
    assert daily["gjr_garch_evt"]["quantile_loss"] == pytest.approx(0.1)
    assert len(result["scenario_scores"]) == 16
    excluded = [
        row
        for row in result["common_sample"]
        if row["scope"] == "main" and row["forecast_date"] == "2024-01-02"
    ][0]
    assert excluded["in_common"] is False
    missing_members = excluded["missing_members"]
    assert isinstance(missing_members, list)
    assert len(missing_members) == 1


def test_stale_native_or_grem_scope_cannot_be_used_to_admit_forecasts() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml")
    native[0]["tail_level"] = 0.99
    with pytest.raises(ValueError, match="one target family and one tail level"):
        build_robust_comparison_artifacts(
            forecasts_for("ml"), native, grem_rows(native), ml_model_names=("ml",)
        )


def test_signed_es_is_scored_without_a_reference_or_source_mutation() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml")
    forecasts = forecasts_for("ml", var=-0.02, es=-0.01)
    before = deepcopy(forecasts)
    result = build_robust_comparison_artifacts(
        forecasts, native, grem_rows(native), ml_model_names=("ml",)
    )
    assert forecasts == before
    assert result["comparison_status"][0]["status"] == "reference_unavailable"
    assert result["comparison_status"][0]["model_roster"] == ["ml"]
    assert result["references"][0]["model_name"] is None
    assert len(result["daily_scores"]) == 2
    for row in result["daily_scores"]:
        score = row["fzg"]
        assert isinstance(score, float)
        assert math.isfinite(score)


def test_global_reference_ties_use_registered_order_not_input_order() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("gjr_garch_evt", external=True) + native_rows("garch_t", external=True)
    forecasts = forecasts_for("gjr_garch_evt", external=True)
    forecasts += forecasts_for("garch_t", external=True)
    result = build_robust_comparison_artifacts(
        forecasts, native, grem_rows(native), ml_model_names=()
    )
    assert result["references"][0]["model_name"] == "garch_t"
    assert result["references"][0]["tied_best_models"] == ["garch_t", "gjr_garch_evt"]
    assert len(result["daily_scores"]) == 2  # Not four copies of the reference per date.
    assert result["comparison_status"][0]["candidate_count"] == 1
    assert (
        result["comparison_status"][0]["comparative_status"] == "insufficient_candidates_or_dates"
    )


@pytest.mark.parametrize("change", ["duplicate", "level", "target", "outcome", "session"])
def test_invalid_frozen_comparison_inputs_fail_instead_of_silent_overwrite(change: str) -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml")
    forecasts = forecasts_for("ml")
    if change == "duplicate":
        forecasts.append(dict(forecasts[0]))
    elif change == "level":
        forecasts[0]["tail_level"] = 0.99
    elif change == "target":
        forecasts[0]["target_family"] = "different_target"
    elif change == "outcome":
        forecasts[0]["realized_loss"] = 0.02
    else:
        forecasts[0]["target_session_index"] = 1
    with pytest.raises(ValueError):
        build_robust_comparison_artifacts(
            forecasts, native, grem_rows(native), ml_model_names=("ml",)
        )


@pytest.mark.parametrize(
    "change",
    [
        {"diagnostic_status": "unavailable_segment"},
        {"unavailable_rows": 1},
        {"unavailable_since": "2024-01-02"},
        {"valid_prefix_peak_log_grem": None},
        {"processed_eligible_rows": 449},
    ],
)
def test_missing_or_insufficient_grem_cannot_pass(change: dict[str, object]) -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml")
    grem = grem_rows(native)
    grem[0].update(change)
    result = build_robust_comparison_artifacts([], native, grem, ml_model_names=("ml",))
    assert result["admissibility"][0]["admission_status"] == "unassessable"
    assert result["admissibility"][0]["admitted"] is False


def test_a_missing_grem_record_and_missing_forecast_pairs_are_not_imputed() -> None:
    from n225_open_gap_tail.metrics.robust_comparison import build_robust_comparison_artifacts

    native = native_rows("ml") + native_rows("garch_t", external=True)
    grem = grem_rows(native)
    grem.pop(0)
    forecasts = forecasts_for("garch_t", external=True)
    for row in forecasts:
        row["es_forecast"] = None
    result = build_robust_comparison_artifacts(forecasts, native, grem, ml_model_names=("ml",))
    assert result["admissibility"][0]["admitted"] is False
    assert result["references"][0]["selection_status"] == "no_common_joint_dates"
    assert not result["daily_scores"]
    assert all(row["in_common"] is False for row in result["common_sample"])
