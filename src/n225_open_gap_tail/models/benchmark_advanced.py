# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def benchmark_advanced_refit_dates(
    rows: list[dict[str, object]],
    *,
    oos_start: str,
) -> list[str]:
    """First valid panel forecast date in each calendar month after OOS start."""
    start_date = date.fromisoformat(oos_start)
    refits: dict[str, str] = {}
    for row in _clean_loss_rows(rows):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        month_key = forecast_date.strftime("%Y-%m")
        refits.setdefault(month_key, forecast_date.isoformat())
    return [refits[key] for key in sorted(refits)]


def _evaluate_benchmark_advanced_shard(
    payload: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    tail_level = _required_float(payload["tail_level"])
    models = cast(tuple[str, ...], payload["models"])
    frame = (
        pl.scan_parquet(panel_path)
        .filter(pl.col("clean_sample") == True)  # noqa: E712
        .select(["forecast_date", "realized_loss"])
        .drop_nulls()
        .sort("forecast_date")
        .collect()
    )
    rows = frame.to_dicts()
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                _advanced_benchmark_record(
                    {
                        "model_name": model_name,
                        "tail_level": tail_level,
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
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


def _forecast_stateful_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_level: float,
    oos_start: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Nonblocking scaffold for recursive advanced benchmark models.

    Concrete CAViaR/CARE/FZ/GAS implementations plug into this stateful path. Until
    then the benchmark suite records audited unavailability without blocking the
    benchmark floor.
    """
    refit_dates = benchmark_advanced_refit_dates(rows, oos_start=oos_start)
    return (
        [],
        [
            {
                "model_name": model_name,
                "tail_level": tail_level,
                "fit_status": "unavailable_advanced_model_not_implemented",
                "failure_reason": "advanced_stateful_model_scaffold_only",
                "refit_frequency": BENCHMARK_ADVANCED_REFIT_FREQUENCY,
                "refit_dates_json": json.dumps(refit_dates, separators=(",", ":")),
                "refit_calendar": "first_valid_panel_forecast_date_per_calendar_month",
                "state_update_policy": "valid_panel_dates_only_skip_calendar_gaps",
            }
        ],
        [],
    )


def _advanced_benchmark_record(
    row: dict[str, object],
    *,
    model_name: str,
) -> dict[str, object]:
    model_meta = _advanced_model_metadata(model_name)
    return {
        **row,
        "model_name": row.get("model_name") or model_name,
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "information_set": row.get("information_set") or "target_history_only",
        "benchmark_tier": "advanced",
        "model_family": row.get("model_family") or model_meta["model_family"],
        "model_variant": row.get("model_variant") or model_meta["model_variant"],
        "refit_frequency": row.get("refit_frequency") or BENCHMARK_ADVANCED_REFIT_FREQUENCY,
        "advanced_model_nonblocking": True,
    }


def _advanced_model_metadata(model_name: str) -> dict[str, str]:
    if model_name.startswith("caviar_"):
        return {"model_family": "caviar", "model_variant": model_name.removeprefix("caviar_")}
    if model_name.startswith("care_expectile_"):
        return {
            "model_family": "care_expectile",
            "model_variant": model_name.removeprefix("care_expectile_"),
        }
    if model_name.startswith("ald_taylor_"):
        return {
            "model_family": "ald_taylor_var_es",
            "model_variant": model_name.removeprefix("ald_taylor_"),
        }
    if model_name.startswith("direct_fz_loss_"):
        return {
            "model_family": "direct_fz_loss",
            "model_variant": model_name.removeprefix("direct_fz_loss_"),
        }
    if model_name.startswith("gas_t_"):
        return {"model_family": "gas_t", "model_variant": model_name.removeprefix("gas_t_")}
    return {"model_family": "advanced_benchmark", "model_variant": model_name}
