from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

import n225_open_gap_tail.models.benchmark as benchmark
import n225_open_gap_tail.models.unibm as adapter
from n225_open_gap_tail.config.runtime import PipelineRunError


@dataclass
class Curve:
    block_sizes: NDArray[np.int64]
    counts: NDArray[np.int64]
    positive_mask: NDArray[np.bool_]


def test_public_adapter_keeps_positions_and_strict_fgls_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = np.r_[np.nan, np.linspace(-2, 3, 60)]
    observed: dict[str, Any] = {}

    def estimate(values: NDArray[np.float64], **kwargs: Any) -> SimpleNamespace:
        np.testing.assert_equal(values, sample)
        observed.update(kwargs)
        metadata = dict.fromkeys(
            (
                "bootstrap_reps_requested",
                "bootstrap_reps_used",
                "bootstrap_reps_policy",
                "bootstrap_precision_met",
                "bootstrap_mcse",
                "bootstrap_mcse_max_ratio",
                "bootstrap_mcse_targets",
                "bootstrap_block_length_policy",
                "bootstrap_block_length",
                "covariance_shrinkage_policy",
                "covariance_condition_number_raw",
                "covariance_condition_number_regularized",
            )
        )
        metadata.update(bootstrap_reps_used=1024, bootstrap_precision_met=False)
        return SimpleNamespace(
            slope=0.2,
            standard_error=0.03,
            confidence_interval=(0.14, 0.26),
            regression="FGLS",
            ci_variant="bootstrap_cov",
            plateau_mask=np.ones(5, dtype=bool),
            plateau_block_sizes=np.arange(5, 10),
            counts=np.full(5, 30),
            **metadata,
        )

    public = SimpleNamespace(
        __file__="public_unibm/evi/__init__.py",
        generate_block_sizes=lambda n: np.arange(5, 11),
        block_summary_curve=lambda *args, **kwargs: Curve(
            np.arange(5, 11), np.array([30, 30, 30, 30, 30, 19]), np.ones(6, dtype=bool)
        ),
        estimate_evi_quantile=estimate,
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: public)
    result = adapter.estimate_public_unibm(sample)
    assert result["status"] == "ok"
    assert result["regression"] == "FGLS"
    assert result["first_finite_position"] == 1
    assert result["n_obs"] == 61
    assert result["bootstrap_precision_met"] is False  # diagnostic, not a new gate
    assert observed["bootstrap_reps"] == "adaptive"
    assert observed["covariance_shrinkage"] == 0.37
    assert observed["regression"] == "FGLS"
    np.testing.assert_equal(observed["curve"].positive_mask, [True] * 5 + [False])

    # Structural warm-up is explicit; an internal/trailing missing position survives.
    expanded = np.r_[np.full(5, np.nan), sample]
    result = adapter.estimate_public_unibm(expanded, warmup_rows=5)
    assert result["status"] == "ok"
    assert result["input_n_obs"] == 66 and result["n_obs"] == 61
    assert result["first_finite_position"] == 6
    assert result["missing_observations"] == 1
    assert result["structural_warmup_rows"] == 5
    with pytest.raises(ValueError, match="only undefined"):
        adapter.estimate_public_unibm(sample, warmup_rows=2)
    for invalid in (-1, 62, True):
        with pytest.raises(ValueError, match="integer within"):
            adapter.estimate_public_unibm(sample, warmup_rows=invalid)


def test_public_adapter_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> Any:
        raise ModuleNotFoundError("unibm is not installed")

    monkeypatch.setattr(importlib, "import_module", missing)
    result = adapter.estimate_public_unibm(np.linspace(-1, 2, 70))
    assert result["status"] == "unavailable_public_unibm"
    assert "ModuleNotFoundError" in result["failure_reason"]
    assert result["xi_evi_anchor"] is None
    with pytest.raises(ValueError, match="one-dimensional"):
        adapter.estimate_public_unibm(np.zeros((3, 4)))
    monkeypatch.setattr(importlib, "import_module", lambda name: SimpleNamespace(__file__="test"))
    result = adapter.estimate_public_unibm(np.zeros(3))
    assert "insufficient finite" in result["failure_reason"]


def test_same_public_anchor_is_reused_across_threshold_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def legacy_forbidden(*args: Any) -> Any:
        raise AssertionError("New experiment must not call copied OLS anchor")

    monkeypatch.setattr(benchmark, "_estimate_unibm_evi_anchor", legacy_forbidden)
    anchor = {"status": "ok", "xi_evi_anchor": 0.1, "regression": "FGLS", "n_obs": 300}
    result = benchmark._pot_gpd_standardized_tail(
        standardized_losses=np.linspace(-2, 6, 300),
        tail_level=0.95,
        min_standardized_losses=100,
        min_exceedances=5,
        evt_variant="unibm",
        require_finite_gpd_es=True,
        unibm_anchor=anchor,
    )
    assert result["evt_shape"] == 0.1
    assert json.loads(str(result["evt_evi_diagnostics_json"]))["regression"] == "FGLS"
    diagnostics = json.loads(str(result["evt_threshold_sensitivity_json"]))
    assert all(
        row["status"]
        == (
            "ok"
            if row["threshold_quantile"] < 0.95
            else "not_applicable_threshold_not_below_tail_level"
        )
        for row in diagnostics
    )
    with pytest.raises(PipelineRunError, match="unavailable_evt_unibm"):
        benchmark._pot_gpd_standardized_tail(
            standardized_losses=np.linspace(-2, 6, 300),
            tail_level=0.95,
            min_standardized_losses=100,
            min_exceedances=5,
            evt_variant="unibm",
            unibm_anchor={"status": "unavailable_public_unibm"},
        )
