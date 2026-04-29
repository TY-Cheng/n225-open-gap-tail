# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,PLR0912,PLR0913,PLR0915,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import *
from n225_open_gap_tail.data_lake.artifacts import _forecast_shard_id
from n225_open_gap_tail.models.benchmark_advanced_math import (
    _advanced_pot_gpd_standardized_tail,
    _empirical_es_multiplier,
    _gas_filter_path,
    _gas_next_log_sigma,
    _gas_params_valid,
    _recursive_params_valid,
    _recursive_var_path,
)
from n225_open_gap_tail.models.benchmark_advanced_stateful import (
    _advanced_benchmark_record,
    _calibrate_care_expectile_tau,
    _fit_advanced_model,
    _forecast_from_advanced_fit,
    _forecast_stateful_sequence,
    _gas_filter_failure_record,
    benchmark_advanced_refit_dates,
)


def _evaluate_benchmark_advanced_shard(
    payload: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    tail_side = normalize_tail_side(payload.get("tail_side"))
    tail_level = _required_float(payload["tail_level"])
    models = cast(tuple[str, ...], payload["models"])
    panel_columns = pl.scan_parquet(panel_path).collect_schema().names()
    selected_columns = ["forecast_date", "realized_loss"]
    if "gap_t" in panel_columns:
        selected_columns.append("gap_t")
    frame = (
        pl.scan_parquet(panel_path)
        .filter(pl.col("clean_sample") == True)  # noqa: E712
        .select(selected_columns)
        .drop_nulls()
        .sort("forecast_date")
        .collect()
    )
    rows = rows_for_tail_side(frame.to_dicts(), tail_side=tail_side)
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                _advanced_benchmark_record(
                    {
                        "model_name": model_name,
                        "tail_side": tail_side,
                        "tail_level": tail_level,
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
                            tail_side=tail_side,
                            refit_frequency=BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                        ),
                        "fit_status": "unavailable_insufficient_oos_start",
                        "oos_failure_reason": oos_diagnostics["failure_reason"],
                        "train_n": oos_diagnostics["train_n"],
                        "train_exceedances": oos_diagnostics["train_exceedances"],
                        "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                        "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                    },
                    model_name=model_name,
                )
                for model_name in models
            ],
            "failures": [],
        }
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for model_name in models:
        try:
            model_rows, model_diag, model_failures = _forecast_stateful_sequence(
                rows=rows,
                model_name=model_name,
                tail_level=tail_level,
                oos_start=oos_start,
            )
        except Exception as exc:  # pragma: no cover - defensive optimizer boundary
            model_rows = []
            model_diag = []
            model_failures = [
                {
                    "model_name": model_name,
                    "tail_side": tail_side,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_advanced_optimizer_failed",
                    "failure_reason": str(exc),
                }
            ]
        forecasts.extend(
            _advanced_benchmark_record(row, model_name=model_name) for row in model_rows
        )
        diagnostics.extend(
            _advanced_benchmark_record(row, model_name=model_name) for row in model_diag
        )
        failures.extend(
            _advanced_benchmark_record(row, model_name=model_name) for row in model_failures
        )
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}
