# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def write_leakage_check(*, run_dir: Path) -> LeakageCheckResult:
    panel_path = _gold_artifact_path(
        run_dir, "modeling_panel", run_dir / "panel" / "modeling_panel.parquet"
    )
    if not panel_path.exists():
        raise PipelineRunError(f"Missing modeling panel: {panel_path}")
    panel_frame = pl.read_parquet(panel_path)
    rows = build_leakage_check_records(panel_frame.to_dicts())
    binding = _current_leakage_binding(run_dir, panel_frame=panel_frame)
    output_path = run_dir / "audits" / "leakage_check.parquet"
    summary_path = run_dir / "audits" / "leakage_check_summary.json"
    _write_parquet(output_path, rows)
    failures = sum(1 for row in rows if row.get("status") == "fail")
    warnings = sum(1 for row in rows if row.get("status") == "warn")
    summary = {
        "run_id": run_dir.name,
        "claims_level": CLAIMS_LEVEL,
        "config_hash": _read_manifest(run_dir).get("config_hash"),
        **binding,
        "rows": len(rows),
        "failures": failures,
        "warnings": warnings,
        "status": "fail" if failures else "pass_with_warnings" if warnings else "pass",
    }
    _write_json(summary_path, summary)
    manifest = _read_manifest(run_dir)
    gold_root_raw = manifest.get("gold_root")
    if isinstance(gold_root_raw, str):
        gold_summary_path = (
            Path(gold_root_raw)
            / "leakage_summary"
            / "schema_version=1"
            / f"run_id={run_dir.name}"
            / "summary.json"
        )
        _write_json(gold_summary_path, summary)
    _update_manifest(
        run_dir,
        {
            "leakage_check_rows": len(rows),
            "leakage_check_failures": failures,
            "leakage_check_warnings": warnings,
        },
    )
    return LeakageCheckResult(
        run_id=run_dir.name,
        output_path=output_path,
        rows=len(rows),
        failures=failures,
        warnings=warnings,
    )


def _current_leakage_binding(
    run_dir: Path,
    *,
    panel_frame: pl.DataFrame | None = None,
) -> dict[str, object]:
    panel = (
        panel_frame
        if panel_frame is not None
        else pl.read_parquet(
            _gold_artifact_path(
                run_dir, "modeling_panel", run_dir / "panel" / "modeling_panel.parquet"
            )
        )
    )
    calendar_path = _gold_artifact_path(
        run_dir, "calendar_map", run_dir / "panel" / "calendar_map.parquet"
    )
    calendar_hash = None
    if calendar_path.exists():
        calendar_hash = _deterministic_frame_signature(
            pl.read_parquet(calendar_path),
            columns=(
                "ose_trading_date",
                "us_session_date",
                "model_cutoff_ts_utc",
                "target_open_ts_utc",
                "mapping_status",
                "mapping_reason",
            ),
            sort_columns=("ose_trading_date",),
        )
    manifest = _read_manifest(run_dir)
    forecast_bounds = _column_bounds(panel, "forecast_date")
    target_bounds = _column_bounds(panel, "target_open_ts_utc")
    cutoff_bounds = _column_bounds(panel, "model_cutoff_ts_utc")
    return {
        "panel_signature": _deterministic_frame_signature(
            panel,
            columns=PANEL_SIGNATURE_COLUMNS,
            sort_columns=("forecast_date",),
        ),
        "panel_signature_columns": list(PANEL_SIGNATURE_COLUMNS),
        "panel_signature_hash_seed": PANEL_SIGNATURE_HASH_SEED,
        "panel_row_count": panel.height,
        "panel_forecast_date_min": forecast_bounds[0],
        "panel_forecast_date_max": forecast_bounds[1],
        "panel_target_open_ts_utc_min": target_bounds[0],
        "panel_target_open_ts_utc_max": target_bounds[1],
        "panel_model_cutoff_ts_utc_min": cutoff_bounds[0],
        "panel_model_cutoff_ts_utc_max": cutoff_bounds[1],
        "calendar_map_hash": calendar_hash,
        "bound_config_hash": manifest.get("config_hash"),
    }


def _deterministic_frame_signature(
    frame: pl.DataFrame,
    *,
    columns: tuple[str, ...],
    sort_columns: tuple[str, ...],
) -> str:
    working = frame
    missing = [column for column in columns if column not in working.columns]
    if missing:
        raise PipelineRunError(
            "Cannot sign leakage summary; panel signature columns missing: " + ", ".join(missing)
        )
    selected = working.select(
        [
            pl.col(column).cast(pl.Utf8, strict=False).fill_null("<NULL>").alias(column)
            for column in columns
        ]
    )
    available_sort = [column for column in sort_columns if column in selected.columns]
    if available_sort:
        selected = selected.sort(available_sort)
    row_hashes = [
        int(value) for value in selected.hash_rows(seed=PANEL_SIGNATURE_HASH_SEED).to_list()
    ]
    return stable_hash(
        {
            "columns": columns,
            "hash_seed": PANEL_SIGNATURE_HASH_SEED,
            "row_count": selected.height,
            "row_hashes": row_hashes,
        }
    )


def _column_bounds(frame: pl.DataFrame, column: str) -> tuple[str | None, str | None]:
    if column not in frame.columns or frame.height == 0:
        return None, None
    series = frame.get_column(column).drop_nulls()
    if series.is_empty():
        return None, None
    return _bound_value_to_string(series.min()), _bound_value_to_string(series.max())


def _bound_value_to_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def build_leakage_check_records(panel_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    warning_min_lag = PIPELINE_CONFIG.leakage_policy.leakage_warning_min_lag_minutes
    for row in panel_rows:
        cutoff = _coerce_datetime(row.get("model_cutoff_ts_utc"))
        target_open = _coerce_datetime(row.get("target_open_ts_utc"))
        for key, raw_available in sorted(row.items()):
            if not key.endswith("__available_ts_utc"):
                continue
            feature_name = key.removesuffix("__available_ts_utc")
            feature_value = row.get(feature_name)
            available = _coerce_datetime(raw_available)
            status = "pass"
            reason = None
            lag_minutes: float | None = None
            if available is None and feature_value is None:
                status = "warn"
                reason = "missing_feature_value_not_evaluable"
            elif available is None or cutoff is None or target_open is None:
                status = "fail"
                reason = "missing_timestamp_for_leakage_check"
            elif available > cutoff:
                status = "fail"
                reason = "feature_available_after_model_cutoff"
                lag_minutes = (cutoff - available).total_seconds() / 60.0
            elif cutoff >= target_open:
                status = "fail"
                reason = "model_cutoff_not_before_target_open"
                lag_minutes = (cutoff - available).total_seconds() / 60.0
            else:
                lag_minutes = (cutoff - available).total_seconds() / 60.0
                if lag_minutes < warning_min_lag:
                    status = "warn"
                    reason = "lag_below_conservative_warning_threshold"
            records.append(
                {
                    "forecast_date": row.get("forecast_date"),
                    "feature_name": feature_name,
                    "feature_available_ts_utc": available,
                    "model_cutoff_ts_utc": cutoff,
                    "target_open_ts_utc": target_open,
                    "lag_minutes": lag_minutes,
                    "feature_fill_method": row.get(f"{feature_name}__fill_method"),
                    "feature_source_date": row.get(f"{feature_name}__source_date"),
                    "status": status,
                    "reason": reason,
                }
            )
    return records
