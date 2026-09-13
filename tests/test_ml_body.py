from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import lightgbm as lgb
import numpy as np
import pytest

import n225_open_gap_tail.models.ml_body as body_models
from n225_open_gap_tail.config.runtime import PipelineRunError
from n225_open_gap_tail.models.ml_tail import _lgbm_training_params
from n225_open_gap_tail.models.ml_tail_oof import _fit_lgb_regression_model


def rows(n: int = 120) -> list[dict[str, Any]]:
    return [
        {
            "forecast_date": (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
            "realized_loss": 0.01 * np.sin(i) + 0.0001 * i,
            "feature_x": float(i),
        }
        for i in range(n)
    ]


def test_seven_bodies_share_mean_fits_and_preserve_oof_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(body_models, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    training = rows()
    bodies = dict(
        body_models.fit_body_recipes(
            training,
            candidate_features=["feature_x"],
            information_set="A",
            tail_level=0.95,
            lgb=lgb,
            lgbm_params={"n_estimators": 3, "min_child_samples": 3},
        )
    )
    assert len(body_models.EXPERIMENT_MODEL_NAMES) == 22
    assert len(set(body_models.EXPERIMENT_MODEL_NAMES)) == 22
    assert set(bodies) == {
        "mean_log_abs",
        "median_mad",
        "median_iqr",
        "huber_log_abs",
        "mean_rms_l2",
        "mean_rms_poisson",
        "mean_rms_gamma",
    }
    assert all(body["fit_status"] == "ok" for body in bodies.values()), bodies
    mean = bodies["mean_log_abs"]["center"]
    target = bodies["mean_rms_l2"]["scale_target_oof_training_units"]
    losses = np.array([row["realized_loss"] for row in training])
    for name, body in bodies.items():
        assert body["training_multiplier"] == 1
        assert body["standardized_losses"].shape == (len(training),)
        assert np.isnan(body["standardized_losses"][:10]).all()
        expected_warmup = 10 if name == "median_iqr" else 32
        assert body["oof_warmup_rows"] == expected_warmup
        assert body["oof_dates"] == [row["forecast_date"] for row in training]
        assert np.isnan(body["standardized_losses"][:expected_warmup]).all()
        prediction = body_models.predict_body(body, training[-3:])
        assert np.isfinite(prediction["location"]).all()
        assert (prediction["scale"] > 0).all()
        assert abs(prediction["location"]).max() < 0.1  # decimal, not percent units
        residuals = losses - body["mu_oof"]
        np.testing.assert_allclose(
            body["standardized_losses"], residuals / body["scale_oof"], equal_nan=True
        )
        if name.startswith("mean_rms"):
            assert body["center"] is mean
            np.testing.assert_equal(body["scale_target_oof_training_units"], target)
            np.testing.assert_allclose(target, residuals**2, equal_nan=True)
        elif body["scale_transform"] == "mad":
            np.testing.assert_allclose(
                body["scale_target_oof_training_units"], np.abs(residuals), equal_nan=True
            )
        elif body["scale_transform"] == "log_abs":
            np.testing.assert_allclose(
                body["scale_target_oof_training_units"],
                np.log(np.maximum(np.abs(residuals), 1e-6)),
                equal_nan=True,
            )
    assert bodies["huber_log_abs"]["center"] is not mean
    assert bodies["median_mad"]["center"] is bodies["median_iqr"]["center"]


def test_native_objective_domains_and_constants() -> None:
    assert _lgbm_training_params()["max_depth"] == 17
    assert _lgbm_training_params()["num_threads"] == 3
    training = rows(20)
    mixed_zero_target = np.arange(20, dtype=float) / 20
    for objective in ("gamma", "poisson", "huber"):
        model, _, _ = _fit_lgb_regression_model(
            lgb=lgb,
            rows=training,
            target=mixed_zero_target,
            candidate_features=["feature_x"],
            objective=objective,
            random_state=225,
            lgbm_params={"n_estimators": 2, "min_child_samples": 3},
        )
        params = model.get_params()
        assert params["max_depth"] == 17
        assert model.booster_.params["num_threads"] == 3
        if objective in {"gamma", "poisson"}:
            assert params["metric"] == "l2"
        if objective == "huber":
            assert params["alpha"] == 0.9
        if objective == "poisson":
            assert params["poisson_max_delta_step"] == 0.7
    for target in (np.zeros(20), np.full(20, -1.0), np.full(20, np.nan)):
        with pytest.raises(PipelineRunError, match="positive_link_target_domain"):
            _fit_lgb_regression_model(
                lgb=lgb,
                rows=training,
                target=target,
                candidate_features=["feature_x"],
                objective="gamma",
                random_state=225,
            )


def test_scale_floor_keeps_nonfinite_unavailable() -> None:
    raw = np.array([-1.0, 0.0, 1e-10, 4e-8, np.nan, np.inf])
    result = body_models.rms_scale(raw)
    np.testing.assert_allclose(result[:4], [1e-4, 1e-4, 1e-4, 2e-4])
    assert np.isnan(result[4:]).all()
    with pytest.raises(ValueError, match="Unknown body/tail"):
        body_models.body_model_name("unknown", "empirical")


def test_body_failure_is_reported_without_hiding_other_recipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(body_models, "ML_TAIL_MIN_OOF_TRAIN_ROWS", 10)
    original = body_models._fit_component

    def fail_huber(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["objective"] == "huber":
            raise PipelineRunError("huber failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(body_models, "_fit_component", fail_huber)
    result = dict(
        body_models.fit_body_recipes(
            rows(),
            candidate_features=["feature_x"],
            information_set="A",
            tail_level=0.95,
            lgb=lgb,
            lgbm_params={"n_estimators": 2},
        )
    )
    assert result["huber_log_abs"]["failure_reason"] == "huber failed"
    assert result["mean_log_abs"]["fit_status"] == "ok"
    assert len(result) == 7
    with pytest.raises(ValueError, match="finite observed losses"):
        list(
            body_models.fit_body_recipes(
                [{"realized_loss": np.nan}],
                candidate_features=["feature_x"],
                information_set="A",
                tail_level=0.95,
                lgb=lgb,
            )
        )
