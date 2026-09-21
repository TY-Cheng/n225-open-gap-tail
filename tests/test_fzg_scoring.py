from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import quad  # type: ignore[import-untyped]

from n225_open_gap_tail.metrics.result_matrix import build_metric_records
from n225_open_gap_tail.metrics.stat_utils import forecast_eligible, fzg_loss


def test_fzg_signed_domain_units_and_exact_boundary_examples() -> None:
    # Published lower-tail FZG reflected into upper losses, in percentage points.
    assert fzg_loss(0.0, 0.0, 0.0, 0.95) == 0.0
    assert fzg_loss(0.01, 0.0, 0.0, 0.95) == pytest.approx(11.0)
    assert fzg_loss(-0.01, -0.01, 0.0, 0.95) == pytest.approx(-0.55)
    assert fzg_loss(-0.02, -0.02, -0.01, 0.95) == pytest.approx(
        -0.1 - math.e / (1 + math.e) - math.log1p(math.e) + math.log(2)
    )
    row = {
        "realized_loss": -0.02,
        "var_forecast": -0.02,
        "es_forecast": -0.01,
        "tail_level": 0.95,
        "fit_status": "ok",
    }
    assert forecast_eligible(row, score="fzg")
    assert not forecast_eligible(row, score="fz0")
    native = build_metric_records([{**row, "model_name": "signed", "forecast_date": "2024-01-02"}])[
        0
    ]
    assert native["fz0_rows"] == 0
    assert native["fzg_rows"] == 1
    assert native["mean_fzg_loss"] == fzg_loss(-0.02, -0.02, -0.01, 0.95)


def test_fzg_expected_score_is_minimized_at_known_uniform_tail_pair() -> None:
    # Deterministic integration of Uniform[-1,1] percentage points: q=.9, ES=.95.
    def expected(q: float, e: float) -> float:
        return float(
            quad(
                lambda y: fzg_loss(y / 100, q / 100, e / 100, 0.95),
                -1,
                1,
                points=[q] if -1 < q < 1 else None,
            )[0]
            / 2
        )

    correct = expected(0.9, 0.95)
    for q, e in [(0.8, 0.95), (0.94, 0.95), (0.9, 0.91), (0.9, 1.1)]:
        assert correct < expected(q, e)


@pytest.mark.parametrize(
    "y,q,e,p",
    [
        (0.0, 1.0, 0.0, 0.95),
        (0.0, 0.0, math.inf, 0.95),
        (math.nan, 0.0, 1.0, 0.95),
        (0.0, 0.0, 1.0, 1.0),
    ],
)
def test_fzg_rejects_incoherent_or_nonfinite_inputs(y: float, q: float, e: float, p: float) -> None:
    assert math.isnan(fzg_loss(y, q, e, p))


def test_fzg_logistic_and_softplus_do_not_overflow_at_extreme_signed_values() -> None:
    for y, q, e in [(2.0, 1.0, 100.0), (-100.0, -100.0, -99.0)]:
        assert np.isfinite(fzg_loss(y, q, e, 0.95))
