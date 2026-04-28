from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl
import pytest

import n225_open_gap_tail.paper as paper_module
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.paper import (
    build_feature_coverage_records,
    build_modeling_panel_records,
    build_paper_run_id,
    drop_low_variance_features,
    empirical_excess_es_companion,
    evaluate_p2a_run,
    filtered_historical_es,
    find_oos_start_date,
    global_oos_intersection,
    quantile_loss,
    static_empirical_es,
    validate_forecast_values,
    validate_worker_payload,
    write_paper_latex_tables,
    write_paper_panel,
)


def test_build_paper_run_id_binds_stage_window_timestamp_and_commit() -> None:
    run_id = build_paper_run_id(
        start="2008-05-07",
        end="2026-04-28",
        run_ts_utc=datetime(2026, 4, 28, 12, 30, tzinfo=UTC),
        git_commit="abcdef123456",
        stage="p2a",
    )

    assert run_id == "p2a_20080507_20260428_20260428T123000Z_commit_abcdef12"


def test_forecast_validity_distinguishes_var_breach_from_invalid_forecast() -> None:
    assert validate_forecast_values(2.0, 2.5) == (True, None)
    assert validate_forecast_values(2.0, 1.9) == (False, "invalid_es_below_var")
    assert validate_forecast_values(math.nan, 2.5) == (False, "invalid_nonfinite_forecast")


def test_es_companion_rules_cover_static_dynamic_and_filtered_history() -> None:
    train_losses = np.array([1.0, 2.0, 3.0, 10.0])
    assert static_empirical_es(train_losses, 2.5) == 6.5

    train_var = np.array([1.5, 1.5, 2.5, 8.0])
    companion = empirical_excess_es_companion(
        train_losses=train_losses,
        train_var_forecasts=train_var,
        forecast_var=4.0,
    )
    assert companion > 4.0

    filtered = filtered_historical_es(
        location_forecast=0.1,
        scale_forecast=2.0,
        standardized_train_losses=np.array([0.1, 1.0, 2.0, 3.0]),
        standardized_var=1.5,
    )
    assert filtered >= 0.1 + 2.0 * 1.5


def test_find_oos_start_requires_min_rows_and_tail_exceedances() -> None:
    start = datetime(2015, 1, 1, tzinfo=UTC)
    rows = [
        {
            "forecast_date": (start + timedelta(days=day)).date().isoformat(),
            "realized_loss": float(day % 20),
        }
        for day in range(140)
    ]

    oos = find_oos_start_date(
        rows,
        earliest_oos_start="2015-01-01",
        min_train_rows=100,
        min_train_exceedances=5,
        tail_level=0.95,
    )

    assert oos is not None
    assert oos >= "2015-04-11"
    assert (
        find_oos_start_date(
            rows,
            earliest_oos_start="2015-01-01",
            min_train_rows=200,
            min_train_exceedances=5,
        )
        is None
    )


def test_drop_low_variance_features_filters_dynamic_training_window() -> None:
    frame = pl.DataFrame(
        {
            "constant": [1.0, 1.0, 1.0],
            "moving": [1.0, 2.0, 3.0],
            "near_zero": [1e-12, 2e-12, 3e-12],
        }
    )

    active, dropped = drop_low_variance_features(
        frame,
        ["constant", "moving", "near_zero", "missing"],
    )

    assert active == ["moving"]
    assert dropped == ["constant", "near_zero", "missing"]


def test_global_oos_intersection_requires_complete_loss_matrix() -> None:
    forecasts: list[dict[str, object]] = [
        {"model_name": "a", "forecast_date": "2026-01-01", "fit_status": "ok"},
        {"model_name": "a", "forecast_date": "2026-01-02", "fit_status": "ok"},
        {"model_name": "b", "forecast_date": "2026-01-02", "fit_status": "ok"},
        {"model_name": "b", "forecast_date": "2026-01-03", "fit_status": "ok"},
    ]

    assert global_oos_intersection(forecasts, model_names=("a", "b")) == ["2026-01-02"]
    assert global_oos_intersection([], model_names=()) == []


def test_worker_payload_rejects_dataframe_objects() -> None:
    validate_worker_payload({"panel_path": "/tmp/panel.parquet", "tail_level": 0.95})
    with pytest.raises(paper_module.PaperRunError, match="Polars frame"):
        validate_worker_payload({"frame": pl.DataFrame({"x": [1]})})


def test_build_modeling_panel_records_and_feature_coverage() -> None:
    panel = build_modeling_panel_records(
        target_rows=[
            {
                "trading_date": "2026-01-05",
                "contract_code": "161030018",
                "contract_month": "2026-03",
                "clean_sample": True,
                "same_contract_only": True,
                "is_roll_sq_window": False,
                "missing_reason": None,
                "target_open_ts_utc": datetime(2026, 1, 4, 23, 45, tzinfo=UTC),
                "full_gap_settle_to_open": -0.01,
                "loss_settle_to_open": 0.01,
                "full_gap_close_to_open": -0.02,
                "residual_nightclose_to_day_open": -0.001,
                "volume": 100.0,
                "open_interest": 1000.0,
                "volume_oi_anomaly": None,
            }
        ],
        alignment_records=[
            {
                "trading_date": "2026-01-05",
                "us_calendar_date": "2026-01-02",
                "model_cutoff_ts_utc": datetime(2026, 1, 2, 21, 5, tzinfo=UTC),
                "dst_regime": "EST",
                "absorption_regime": "coincident_close",
            }
        ],
        massive_daily_records=[
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-01",
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
            },
            {
                "ticker": "SPY",
                "bar_date_et": "2026-01-02",
                "close": 101.0,
                "high": 102.0,
                "low": 100.0,
            },
        ],
        spy_minute_records=[],
        fred_records=[
            {"series_id": "VIXCLS", "observation_date": "2026-01-02", "value": 18.0}
        ],
    )
    coverage = build_feature_coverage_records(panel)

    assert panel[0]["forecast_date"] == "2026-01-05"
    assert panel[0]["spy_return"] is not None
    assert panel[0]["fred_vixcls_level"] == 18.0
    assert any(row["feature"] == "spy_return" for row in coverage)


def test_quantile_loss_and_fz_loss_are_finite_for_valid_forecasts() -> None:
    assert quantile_loss(2.0, 1.5, 0.95) > 0
    assert math.isfinite(paper_module.fz_loss(2.0, 1.5, 2.5, 0.95))
    assert math.isnan(paper_module.fz_loss(2.0, 1.5, 1.0, 0.95))


def test_closed_form_p2a_forecasts_and_unknown_model() -> None:
    train = np.arange(1.0, 80.0) / 100.0

    historical = paper_module._forecast_one(
        train=train,
        model_name="historical_quantile",
        tail_level=0.95,
    )
    rolling = paper_module._forecast_one(
        train=train,
        model_name="rolling_quantile",
        tail_level=0.95,
    )
    ewma = paper_module._forecast_one(
        train=train,
        model_name="ewma_vol_scaled",
        tail_level=0.95,
    )

    assert historical["es_companion_type"] == "raw_empirical_es"
    assert rolling["es_companion_type"] == "rolling_empirical_es"
    assert ewma["es_companion_type"] == "analytical_normal_es"
    assert isinstance(ewma["es_forecast"], float)
    assert isinstance(ewma["var_forecast"], float)
    assert ewma["es_forecast"] >= ewma["var_forecast"]
    with pytest.raises(paper_module.PaperRunError, match="Unknown P2A model"):
        paper_module._forecast_one(train=train, model_name="unknown", tail_level=0.95)


def test_evaluate_p2a_shard_records_unavailable_oos(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    pl.DataFrame(
        [
            {"forecast_date": "2026-01-01", "clean_sample": True, "realized_loss": 0.01},
            {"forecast_date": "2026-01-02", "clean_sample": True, "realized_loss": 0.02},
        ]
    ).write_parquet(panel_path)

    result = paper_module._evaluate_p2a_shard(
        {
            "panel_path": str(panel_path),
            "run_dir": str(tmp_path),
            "tail_level": 0.95,
            "models": ("historical_quantile",),
        }
    )

    assert result["forecasts"] == []
    assert result["diagnostics"][0]["fit_status"] == "unavailable_insufficient_oos_start"
    assert result["diagnostics"][0]["model_name"] == "historical_quantile"
    assert result["diagnostics"][0]["shard_id"] == (
        "model=historical_quantile/target=full_gap_settle_to_open/"
        "info=target_history_only/tail=0_950"
    )


def test_spy_minute_features_cover_late_window_and_volume_surge() -> None:
    rows: list[dict[str, object]] = []
    for day, base in (("2026-01-02", 100.0), ("2026-01-05", 110.0)):
        for minute in range(70):
            rows.append(
                {
                    "bar_date_et": day,
                    "bar_end_ts_utc": datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
                    + timedelta(minutes=minute),
                    "is_us_regular_session": True,
                    "close": base + minute / 100.0,
                    "high": base + minute / 100.0 + 0.1,
                    "low": base + minute / 100.0 - 0.1,
                    "volume": 1000.0 + minute,
                }
            )

    features = paper_module._spy_minute_feature_map(rows)

    assert features["2026-01-02"]["spy_late_30m_return"] is not None
    assert features["2026-01-05"]["spy_late_60m_return"] is not None
    assert features["2026-01-05"]["spy_late_volume_surge"] is not None


def test_evaluate_p2a_run_and_latex_export_with_synthetic_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "reports" / "paper_runs" / "p2a_synthetic"
    panel_dir = run_dir / "panel"
    panel_dir.mkdir(parents=True)
    rows = [
        {
            "forecast_date": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day))
            .date()
            .isoformat(),
            "clean_sample": True,
            "realized_loss": float(day) / 100.0,
        }
        for day in range(80)
    ]
    pl.DataFrame(rows).write_parquet(panel_dir / "modeling_panel.parquet")
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(paper_module, "DEFAULT_EARLIEST_OOS_START", "2026-01-01")
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_ROWS", 30)
    monkeypatch.setattr(paper_module, "DEFAULT_MIN_TRAIN_EXCEEDANCES", 1)

    def fake_forecast_one(
        *,
        train: np.ndarray,
        model_name: str,
        tail_level: float,
    ) -> dict[str, object]:
        var = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var,
            "es_forecast": var + 0.01,
            "es_companion_type": "synthetic",
            "optimizer_status": "ok",
            "convergence_code": 0,
        }

    monkeypatch.setattr(paper_module, "_forecast_one", fake_forecast_one)

    result = evaluate_p2a_run(run_dir=run_dir, workers=1)
    latex = write_paper_latex_tables(run_dir=run_dir)

    assert result.status == "completed"
    assert result.forecast_rows > 0
    assert (run_dir / "forecasts" / "p2a_forecasts.parquet").exists()
    assert (
        run_dir
        / "forecasts"
        / "shards"
        / "model=historical_quantile"
        / "target=full_gap_settle_to_open"
        / "info=target_history_only"
        / "tail=0_950"
        / "forecasts.parquet"
    ).exists()
    assert (run_dir / "metrics" / "p2a_metrics.parquet").exists()
    assert latex.tables == 1
    assert (latex.latex_dir / "p2a_metrics_table.tex").exists()


def test_write_paper_panel_with_synthetic_vendor_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_rows = [
        _raw_futures_row("2026-01-05", settle=50000, ac=50100),
        _raw_futures_row("2026-01-06", ao=50500, settle=50600, ac=50700),
    ]
    massive_daily = [
        {
            "ticker": "SPY",
            "bar_date_et": "2026-01-02",
            "close": 100.0,
            "high": 101.0,
            "low": 99.0,
        },
        {
            "ticker": "SPY",
            "bar_date_et": "2026-01-05",
            "close": 101.0,
            "high": 102.0,
            "low": 100.0,
        },
    ]
    fred_rows = [{"series_id": "VIXCLS", "observation_date": "2026-01-05", "value": 18.0}]

    monkeypatch.setattr(paper_module, "_git_commit", lambda: "abcdef123456")
    monkeypatch.setattr(paper_module, "_git_dirty", lambda: False)
    monkeypatch.setattr(
        paper_module,
        "_fetch_jquants_futures_rows",
        lambda **kwargs: raw_rows,
    )
    monkeypatch.setattr(
        paper_module,
        "_fetch_massive_paper_predictors",
        lambda **kwargs: (massive_daily, []),
    )
    monkeypatch.setattr(
        paper_module,
        "_fetch_fred_paper_predictors",
        lambda **kwargs: fred_rows,
    )

    settings = Settings(
        reports_dir=tmp_path / "reports",
        raw_data_dir=tmp_path / "data" / "raw",
        interim_data_dir=tmp_path / "data" / "interim",
        processed_data_dir=tmp_path / "data" / "processed",
    )
    result = write_paper_panel(settings=settings, start="2026-01-05", end="2026-01-06")
    panel = pl.read_parquet(result.panel_path)

    assert result.rows == 2
    assert result.clean_rows == 1
    assert result.run_id.startswith("p2a_20260105_20260106_")
    assert "spy_return" in panel.columns
    assert (result.run_dir / "panel" / "feature_coverage.parquet").exists()
    assert (result.run_dir / "manifest.json").exists()


def test_private_paper_helpers_cover_defensive_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert static_empirical_es(np.array([1.0, 2.0]), 3.0) == 3.0
    assert (
        empirical_excess_es_companion(
            train_losses=np.array([1.0, 2.0]),
            train_var_forecasts=np.array([3.0, 3.0]),
            forecast_var=4.0,
        )
        == 4.0
    )
    assert build_feature_coverage_records([]) == []
    assert paper_module._bounded_workers(2) == 2
    assert paper_module._bounded_workers(0) >= 1
    paper_module._set_nested_thread_limits()
    assert paper_module._month_chunks(start="2026-01-30", end="2026-03-02") == [
        ("2026-01-30", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-02"),
    ]
    assert paper_module._window_return([100.0, 101.0, 102.0], 2) == pytest.approx(
        math.log(102.0) - math.log(100.0)
    )
    assert paper_module._window_return([100.0], 2) is None
    assert paper_module._window_range([101.0, None], [99.0, None]) == pytest.approx(
        math.log(101.0) - math.log(99.0)
    )
    assert paper_module._safe_name("C:USDJPY") == "c_usdjpy"
    assert paper_module._feature_description("spy_late_30m_return").startswith("close-to-close")
    assert paper_module._feature_description("custom_feature") == "paper-grade predictor candidate"
    assert paper_module._safe_mean(np.array([math.nan])) is None
    with pytest.raises(paper_module.PaperRunError, match="Expected finite numeric"):
        paper_module._required_float(None)
    assert paper_module._fmt(None) == ""
    assert paper_module._fmt(1.2345678) == "1.234568"
    assert paper_module._optional_float(True) is None
    assert paper_module._optional_float("bad") is None
    assert paper_module._massive_daily_feature_map(
        [
            {"ticker": "SPY", "bar_date_et": "2026-01-02", "close": None},
            {"ticker": "SPY", "bar_date_et": "2026-01-05", "close": 100.0},
        ]
    )["2026-01-02"]["spy_range"] is None
    class Fitted:
        std_resid = np.array([0.1, 0.2, math.nan])

    assert paper_module._standardized_arch_losses(np.array([1.0, 2.0]), Fitted()).tolist() == [
        -0.1,
        -0.2,
    ]
    var_t, es_t = paper_module._standardized_student_t_loss_var_es(
        mean_return_forecast=0.0,
        scale_forecast=1.0,
        nu=8.0,
        tail_level=0.95,
    )
    assert es_t >= var_t
    assert var_t < 1.9
    standardized = paper_module._standardized_arch_losses(
        np.array([1.0, 2.0, 3.0]),
        object(),
    )
    assert standardized.mean() == pytest.approx(0.0)
    tail = paper_module._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, tail["standardized_es"]) >= cast(float, tail["standardized_var"])
    assert cast(int, tail["evt_exceedance_count"]) >= paper_module.DEFAULT_MIN_TRAIN_EXCEEDANCES
    assert tail["tail_method"] == "pot_gpd_filtered_es"
    assert tail["threshold_quantile"] == 0.90
    diagnostics = json.loads(str(tail["threshold_diagnostics_json"]))
    assert diagnostics
    assert any(row["selected_threshold"] for row in diagnostics)
    assert any("shape_delta_from_previous" in row for row in diagnostics)
    empirical_tail = paper_module._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.90,
    )
    assert cast(float, empirical_tail["standardized_es"]) >= cast(
        float,
        empirical_tail["standardized_var"],
    )
    assert empirical_tail["tail_method"] == "empirical_filtered_es"

    monkeypatch.setattr(
        "n225_open_gap_tail.paper.stats.genpareto.fit",
        lambda *args, **kwargs: (0.0, 0.0, 1.0),
    )
    exponential_tail = paper_module._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, exponential_tail["standardized_es"]) >= cast(
        float,
        exponential_tail["standardized_var"],
    )

    monkeypatch.setattr(
        "n225_open_gap_tail.paper.stats.genpareto.fit",
        lambda *args, **kwargs: (1.1, 0.0, 1.0),
    )
    heavy_tail = paper_module._pot_gpd_standardized_tail(
        standardized_losses=np.concatenate(
            [np.linspace(-2.0, 2.0, 1000), np.linspace(2.1, 6.0, 120)]
        ),
        tail_level=0.975,
    )
    assert cast(float, heavy_tail["standardized_es"]) >= cast(
        float,
        heavy_tail["standardized_var"],
    )
    with pytest.raises(paper_module.PaperRunError, match="insufficient standardized losses"):
        paper_module._pot_gpd_standardized_tail(
            standardized_losses=np.array([1.0, 2.0]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PaperRunError, match="insufficient exceedances"):
        paper_module._pot_gpd_standardized_tail(
            standardized_losses=np.concatenate([np.zeros(1060), np.arange(40.0)]),
            tail_level=0.975,
        )
    with pytest.raises(paper_module.PaperRunError, match="No paper run found"):
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "missing_reports"),
            "",
        )
    with pytest.raises(paper_module.PaperRunError, match="Paper run does not exist"):
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "missing_run",
        )
    with pytest.raises(paper_module.PaperRunError, match="Missing modeling panel"):
        evaluate_p2a_run(run_dir=tmp_path / "no_panel", workers=1)
    runs_dir = tmp_path / "reports" / "paper_runs"
    latest = runs_dir / "p2a_latest"
    older = runs_dir / "p2a_older"
    older.mkdir(parents=True)
    latest.mkdir(parents=True)
    assert paper_module.resolve_paper_run_dir(Settings(reports_dir=tmp_path / "reports"), "").name
    assert (
        paper_module.resolve_paper_run_dir(
            Settings(reports_dir=tmp_path / "reports"),
            "p2a_latest",
        )
        == latest
    )

    monkeypatch.setattr(
        "n225_open_gap_tail.paper.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no git")),
    )
    assert paper_module._git_commit() == "unknown"
    assert paper_module._git_dirty() is True


def _raw_futures_row(
    trading_date: str,
    *,
    ao: float = 50200,
    ac: float = 50300,
    ec: float = 50100,
    settle: float = 50000,
) -> dict[str, object]:
    return {
        "Date": trading_date,
        "ProdCat": "NK225F",
        "Code": "161030018",
        "CM": "2026-03",
        "CCMFlag": True,
        "AO": ao,
        "AC": ac,
        "EO": 50050,
        "EC": ec,
        "Settle": settle,
        "Vo": 100,
        "OI": 1000,
        "LTD": "2026-03-12",
        "SQD": "2026-03-13",
    }
