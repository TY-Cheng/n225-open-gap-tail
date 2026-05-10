from __future__ import annotations

import math

import pytest

from n225_open_gap_tail.config.runtime import (
    EWMA_MAIN_LAMBDA,
    ML_TAIL_MODEL_NAMES,
    PipelineRunError,
)
from n225_open_gap_tail.forecasting.sensitivity import (
    EVT_THRESHOLD_SPECS,
    EWMA_CONFIGURATION_SPECS,
    LGBM_CONFIGURATION_SPECS,
    _deterioration_ratio,
    _evt_boundary_metric_rows,
    _metric_rows_from_forecasts,
    _tag_rows,
    breach_category,
    classify_sensitivity_comparison,
    lgbm_sensitivity_config,
)
from n225_open_gap_tail.models.ml_tail import _lgbm_training_params


def test_lgbm_sensitivity_config_labels_are_exact() -> None:
    assert lgbm_sensitivity_config("current") == {
        "n_estimators": 80,
        "learning_rate": 0.05,
        "num_leaves": 15,
        "min_child_samples": 20,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
    }
    assert lgbm_sensitivity_config("shallow")["num_leaves"] == 10
    assert lgbm_sensitivity_config("deeper")["n_estimators"] == 160
    assert set(LGBM_CONFIGURATION_SPECS) == {"current", "shallow", "deeper"}
    with pytest.raises(PipelineRunError, match="Unknown LGBM sensitivity config label"):
        lgbm_sensitivity_config("wide")


def test_primary_lgbm_params_remain_registered_current_spec() -> None:
    assert _lgbm_training_params() == lgbm_sensitivity_config("current")


def test_sensitivity_configs_do_not_enter_primary_model_registry() -> None:
    registry_text = " ".join(ML_TAIL_MODEL_NAMES)
    assert "shallow" not in registry_text
    assert "deeper" not in registry_text
    assert "sensitivity" not in registry_text


def test_ewma_primary_lambda_label_is_not_a_sensitivity_lambda() -> None:
    assert EWMA_CONFIGURATION_SPECS["primary"] == EWMA_MAIN_LAMBDA == 0.94
    assert EWMA_CONFIGURATION_SPECS["lambda_0_90"] == 0.90
    assert EWMA_CONFIGURATION_SPECS["lambda_0_97"] == 0.97


def test_evt_threshold_095_is_boundary_only_at_95pct_tail() -> None:
    rows = _evt_boundary_metric_rows(
        config_label="u_0_950_boundary",
        threshold=EVT_THRESHOLD_SPECS["u_0_950_boundary"],
        tail_sides=("left_tail",),
        tail_level=0.95,
        information_sets=("japan_only",),
        models=("lightgbm_standardized_loss_pot_gpd_plain_mle",),
    )
    assert rows[0]["sensitivity_status"] == "not_applicable_threshold_not_below_tail_level"
    assert rows[0]["rows"] == 0
    assert rows[0]["robustness_classification"] == "boundary_diagnostic"


def test_breach_category_thresholds_are_registered() -> None:
    assert breach_category(None) == "missing"
    assert breach_category(0.05) == "near_nominal"
    assert breach_category(0.075) == "near_nominal"
    assert breach_category(0.0751) == "coverage_warning"
    assert breach_category(0.0249) == "coverage_warning"


def test_robustness_classification_uses_abs_negative_fz_denominator() -> None:
    fz_deterioration = _deterioration_ratio(-3.90, -4.00)
    assert fz_deterioration is not None
    assert math.isclose(fz_deterioration, 0.025)
    assert _deterioration_ratio(None, -4.00) is None
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.05,
            sensitivity_breach_rate=0.052,
            q_loss_deterioration=0.03,
            fz_loss_deterioration=fz_deterioration,
        )
        == "robust"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.05,
            sensitivity_breach_rate=0.08,
            q_loss_deterioration=0.00,
            fz_loss_deterioration=-0.01,
        )
        == "sensitive"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.04,
            sensitivity_breach_rate=0.04,
            q_loss_deterioration=0.06,
            fz_loss_deterioration=0.00,
        )
        == "mixed"
    )
    assert (
        classify_sensitivity_comparison(
            primary_breach_rate=0.01,
            sensitivity_breach_rate=0.05,
            q_loss_deterioration=0.00,
            fz_loss_deterioration=0.00,
        )
        == "mixed"
    )


def test_tag_rows_omits_none_metadata() -> None:
    assert _tag_rows([{"model_name": "m"}], source_run_id="run", optional=None) == [
        {"model_name": "m", "source_run_id": "run"}
    ]


def test_metric_rows_from_forecasts_registers_classification_and_primary_comparison() -> None:
    forecasts = [
        {
            "fit_status": "ok",
            "is_valid_forecast": True,
            "tail_level": 0.95,
            "model_name": "demo_model",
            "information_set": "demo_info",
            "tail_side": "left_tail",
            "sensitivity_family": "lgbm_capacity",
            "config_label": "deeper",
            "evt_threshold_quantile": 0.90,
            "realized_loss": 2.0,
            "var_forecast": 1.0,
            "es_forecast": 1.5,
        },
        {
            "fit_status": "ok",
            "is_valid_forecast": True,
            "tail_level": 0.95,
            "model_name": "demo_model",
            "information_set": "demo_info",
            "tail_side": "left_tail",
            "sensitivity_family": "lgbm_capacity",
            "config_label": "deeper",
            "evt_threshold_quantile": 0.90,
            "realized_loss": 0.5,
            "var_forecast": 1.0,
            "es_forecast": 1.5,
        },
        {
            "fit_status": "failed",
            "is_valid_forecast": False,
            "tail_level": 0.95,
            "model_name": "demo_model",
        },
    ]
    primary_metrics: dict[tuple[str, str, str, float], dict[str, object]] = {
        ("demo_model", "demo_info", "left_tail", 0.95): {
            "rows": 2,
            "var_breach_rate": 0.50,
            "mean_quantile_loss": 0.30,
            "mean_fz_loss": -0.50,
        }
    }

    rows = _metric_rows_from_forecasts(
        forecasts,
        primary_metrics=primary_metrics,
        source_run_id="tailrisk_demo",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["source_primary_run_id"] == "tailrisk_demo"
    assert row["primary_claim_allowed"] is False
    assert row["rows"] == 2
    assert row["exceedance_count"] == 1
    assert row["var_breach_rate"] == 0.50
    assert row["primary_rows"] == 2
    assert row["primary_breach_category"] == "coverage_warning"
    assert row["breach_category"] == "coverage_warning"
    assert row["robustness_classification"] in {"robust", "mixed", "sensitive"}

    skipped_rows = _metric_rows_from_forecasts(
        [
            {"fit_status": "ok", "is_valid_forecast": True, "tail_level": None},
            {
                "fit_status": "ok",
                "is_valid_forecast": True,
                "tail_level": 0.95,
                "model_name": "empty_model",
                "information_set": "empty_info",
                "tail_side": "left_tail",
                "sensitivity_family": "lgbm_capacity",
                "config_label": "deeper",
                "realized_loss": 2.0,
                "var_forecast": 1.0,
                "es_forecast": None,
            },
        ],
        primary_metrics={},
        source_run_id="tailrisk_demo",
    )
    assert skipped_rows == []
