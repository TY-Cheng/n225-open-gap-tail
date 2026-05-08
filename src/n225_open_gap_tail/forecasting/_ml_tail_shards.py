# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

import os
import shutil
import uuid
from datetime import UTC, datetime

from n225_open_gap_tail.config.runtime import (
    cast,
    DEFAULT_MIN_TRAIN_EXCEEDANCES,
    DEFAULT_MIN_TRAIN_ROWS,
    EVT_MIN_EXCEEDANCES_95,
    EVT_MIN_STANDARDIZED_LOSSES_95,
    EVT_THRESHOLD_QUANTILE,
    json,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_IQR_CONSISTENCY_FACTOR,
    ML_TAIL_MAD_CONSISTENCY_FACTOR,
    ML_TAIL_MEDIAN_IQR_POT_GPD_MODEL_NAMES,
    ML_TAIL_MEDIAN_MAD_POT_GPD_MODEL_NAMES,
    ML_TAIL_MIN_OOF_TRAIN_ROWS,
    ML_TAIL_OOF_SPLITS,
    ML_TAIL_ROBUST_SCALE_FLOOR,
    ML_TAIL_SCALE_FLOOR,
    Path,
    PIPELINE_CONFIG,
    PipelineRunError,
    pl,
    stable_hash,
    _evaluation_log,
)
from n225_open_gap_tail.forecasting.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.models.ml_tail import (
    _evaluate_ml_tail_shard,
    _evt_variant_for_ml_tail_model,
)


ML_TAIL_SHARD_SEED_POLICY_VERSION = "ml_tail_seed_v1"
ML_TAIL_SHARD_COMPLETION_STATES = {"complete", "failed", "incomplete"}
ML_TAIL_SHARD_FORECAST_FIELDS = (
    "forecast_date",
    "target_family",
    "tail_side",
    "model_name",
    "information_set",
    "tail_level",
    "refit_frequency",
)
ML_TAIL_SHARD_DIAGNOSTIC_FIELDS = (
    "forecast_date",
    "target_family",
    "tail_side",
    "model_name",
    "information_set",
    "tail_level",
    "refit_frequency",
    "fit_status",
)
ML_TAIL_SHARD_FAILURE_FIELDS = (
    "forecast_date",
    "model_name",
    "information_set",
    "tail_side",
    "tail_level",
    "fit_status",
    "failure_reason",
)
ML_TAIL_SHARD_STATUS_FIELDS = (
    "shard_schema_hash",
    "completion_state",
    "model_name",
    "target_family",
    "tail_side",
    "tail_level",
    "information_set",
    "refit_frequency",
    "pipeline_config_hash",
    "ml_tail_payload_hash",
    "leakage_binding_hash",
    "panel_signature",
    "candidate_feature_hash",
    "seed_policy_version",
    "created_utc",
)
ML_TAIL_SHARD_SCHEMA_HASH = stable_hash(
    {
        "forecast_fields": ML_TAIL_SHARD_FORECAST_FIELDS,
        "diagnostic_fields": ML_TAIL_SHARD_DIAGNOSTIC_FIELDS,
        "failure_fields": ML_TAIL_SHARD_FAILURE_FIELDS,
        "status_fields": ML_TAIL_SHARD_STATUS_FIELDS,
    }
)


def _ml_tail_leakage_context(run_dir: Path) -> dict[str, object]:
    summary_path = run_dir / "audits" / "leakage_check_summary.json"
    summary = cast(dict[str, object], json.loads(summary_path.read_text(encoding="utf-8")))
    binding_keys = (
        "panel_signature",
        "panel_signature_hash_seed",
        "panel_row_count",
        "panel_forecast_date_min",
        "panel_forecast_date_max",
        "panel_target_open_ts_utc_min",
        "panel_target_open_ts_utc_max",
        "panel_model_cutoff_ts_utc_min",
        "panel_model_cutoff_ts_utc_max",
        "calendar_map_hash",
        "bound_config_hash",
    )
    binding = {key: summary.get(key) for key in binding_keys}
    return {
        "panel_signature": summary.get("panel_signature"),
        "leakage_binding_hash": stable_hash(binding),
    }


def _expected_ml_tail_shard_manifest(
    payload: dict[str, object],
    *,
    manifest: dict[str, object],
    leakage_context: dict[str, object],
) -> dict[str, object]:
    model_name = str(payload["model_name"])
    candidate_feature_hash = str(payload["candidate_feature_hash"])
    return {
        "shard_schema_hash": ML_TAIL_SHARD_SCHEMA_HASH,
        "model_name": model_name,
        "target_family": str(payload["target_family"]),
        "tail_side": str(payload["tail_side"]),
        "tail_level": float(payload["tail_level"]),
        "information_set": str(payload["information_set"]),
        "refit_frequency": str(payload.get("refit_frequency") or ""),
        "pipeline_config_hash": str(manifest.get("config_hash") or PIPELINE_CONFIG.config_hash()),
        "ml_tail_payload_hash": _ml_tail_payload_hash(
            model_name=model_name,
            target_family=str(payload["target_family"]),
            tail_side=str(payload["tail_side"]),
            tail_level=float(payload["tail_level"]),
            information_set=str(payload["information_set"]),
            refit_frequency=str(payload.get("refit_frequency") or ""),
            candidate_feature_hash=candidate_feature_hash,
        ),
        "leakage_binding_hash": leakage_context["leakage_binding_hash"],
        "panel_signature": leakage_context["panel_signature"],
        "candidate_feature_hash": candidate_feature_hash,
        "seed_policy_version": ML_TAIL_SHARD_SEED_POLICY_VERSION,
    }


def _ml_tail_payload_hash(
    *,
    model_name: str,
    target_family: str,
    tail_side: str,
    tail_level: float,
    information_set: str,
    refit_frequency: str,
    candidate_feature_hash: str,
) -> str:
    return stable_hash(
        {
            "model_name": model_name,
            "target_family": target_family,
            "tail_side": tail_side,
            "tail_level": tail_level,
            "information_set": information_set,
            "refit_frequency": refit_frequency,
            "candidate_feature_hash": candidate_feature_hash,
            "body_route": _ml_tail_body_route(model_name),
            "evt_variant": _ml_tail_evt_variant(model_name),
            "seed_policy_version": ML_TAIL_SHARD_SEED_POLICY_VERSION,
            "model_policy": {
                "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                "ml_tail_oof_splits": ML_TAIL_OOF_SPLITS,
                "ml_tail_min_oof_train_rows": ML_TAIL_MIN_OOF_TRAIN_ROWS,
                "evt_threshold_quantile": EVT_THRESHOLD_QUANTILE,
                "evt_min_standardized_losses_95": EVT_MIN_STANDARDIZED_LOSSES_95,
                "evt_min_exceedances_95": EVT_MIN_EXCEEDANCES_95,
                "ml_tail_scale_floor": ML_TAIL_SCALE_FLOOR,
                "ml_tail_robust_scale_floor": ML_TAIL_ROBUST_SCALE_FLOOR,
                "ml_tail_mad_consistency_factor": ML_TAIL_MAD_CONSISTENCY_FACTOR,
                "ml_tail_iqr_consistency_factor": ML_TAIL_IQR_CONSISTENCY_FACTOR,
            },
        }
    )


def _ml_tail_body_route(model_name: str) -> str:
    if model_name == ML_TAIL_DIRECT_QUANTILE_MODEL:
        return "direct_quantile"
    if model_name in ML_TAIL_MEDIAN_MAD_POT_GPD_MODEL_NAMES:
        return "median_mad"
    if model_name in ML_TAIL_MEDIAN_IQR_POT_GPD_MODEL_NAMES:
        return "median_iqr"
    return "mean_log_scale"


def _ml_tail_evt_variant(model_name: str) -> str:
    try:
        return _evt_variant_for_ml_tail_model(model_name)
    except PipelineRunError:
        return "none"


def _partition_ml_tail_shard_jobs(
    run_dir: Path,
    jobs: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cached: list[dict[str, object]] = []
    compute: list[dict[str, object]] = []
    for payload in jobs:
        state = _validate_ml_tail_cached_shard(run_dir, payload)
        if state == "cached":
            cached.append(payload)
        else:
            compute.append(payload)
    return cached, compute


def _validate_ml_tail_cached_shard(run_dir: Path, payload: dict[str, object]) -> str:
    shard_dir = _ml_tail_shard_dir(run_dir, payload)
    status_path = shard_dir / "status.json"
    if not status_path.exists():
        return "compute"
    status = _read_shard_status(status_path)
    completion = str(status.get("completion_state") or "incomplete")
    if completion not in {"complete", "failed"}:
        return "compute"
    for name in ("f.pq", "d.pq", "x.pq"):
        if not (shard_dir / name).exists():
            return "compute"
    expected = cast(dict[str, object], payload["expected_shard_manifest"])
    mismatches = [
        key for key, expected_value in expected.items() if status.get(key) != expected_value
    ]
    if mismatches:
        shard_id = str(payload["shard_id"])
        details = ", ".join(mismatches)
        raise PipelineRunError(
            f"Stale ML-tail shard {shard_id}; mismatched fields: {details}. "
            "Use --force to clear run outputs or --no-resume to recompute ML-tail shards."
        )
    return "cached"


def _warn_orphan_ml_tail_shards(run_dir: Path, *, active_shard_ids: set[str]) -> None:
    shard_root = run_dir / "s"
    if not shard_root.exists():
        return
    for status_path in sorted(shard_root.glob("*/status.json")):
        shard_id = status_path.parent.name
        if shard_id in active_shard_ids:
            continue
        status = _read_shard_status(status_path)
        model_name = status.get("model_name") or "<unknown>"
        _evaluation_log(f"orphan ML-tail shard skipped shard_id={shard_id} model_name={model_name}")


def _compute_and_write_ml_tail_shard_atomic(payload: dict[str, object]) -> None:
    try:
        output = _evaluate_ml_tail_shard(payload)
        completion_state = "complete"
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        completion_state = "failed"
        output = {
            "forecasts": [],
            "diagnostics": [],
            "failures": [
                {
                    "forecast_date": None,
                    "model_name": payload.get("model_name"),
                    "information_set": payload.get("information_set"),
                    "tail_side": payload.get("tail_side"),
                    "tail_level": payload.get("tail_level"),
                    "fit_status": "unavailable_shard_exception",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                    "shard_id": payload.get("shard_id"),
                }
            ],
        }
    _write_ml_tail_shard_atomic(payload, output, completion_state=completion_state)


def _write_ml_tail_shard_atomic(
    payload: dict[str, object],
    output: dict[str, list[dict[str, object]]],
    *,
    completion_state: str,
) -> None:
    run_dir = Path(str(payload["run_dir"]))
    shard_dir = _ml_tail_shard_dir(run_dir, payload)
    parent = shard_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = parent / f".{shard_dir.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    backup_dir = parent / f".{shard_dir.name}.bak.{os.getpid()}.{uuid.uuid4().hex}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        _write_parquet(tmp_dir / "f.pq", _with_shard_id(output.get("forecasts", []), payload))
        _write_parquet(tmp_dir / "d.pq", _with_shard_id(output.get("diagnostics", []), payload))
        _write_parquet(tmp_dir / "x.pq", _with_shard_id(output.get("failures", []), payload))
        manifest = {
            **cast(dict[str, object], payload["expected_shard_manifest"]),
            "completion_state": completion_state,
            "created_utc": datetime.now(UTC).isoformat(),
        }
        _write_json(tmp_dir / "status.json", manifest)
        if shard_dir.exists():
            os.replace(shard_dir, backup_dir)
        os.replace(tmp_dir, shard_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        if backup_dir.exists() and not shard_dir.exists():
            os.replace(backup_dir, shard_dir)
        raise
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)


def _load_active_ml_tail_shards(
    run_dir: Path,
    jobs: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for payload in jobs:
        _validate_ml_tail_cached_shard(run_dir, payload)
        shard_dir = _ml_tail_shard_dir(run_dir, payload)
        forecasts.extend(_read_shard_parquet(shard_dir / "f.pq"))
        diagnostics.extend(_read_shard_parquet(shard_dir / "d.pq"))
        failures.extend(_read_shard_parquet(shard_dir / "x.pq"))
    return forecasts, diagnostics, failures


def _read_shard_parquet(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise PipelineRunError(f"Missing ML-tail shard parquet: {path}")
    return pl.read_parquet(path).to_dicts()


def _read_shard_status(path: Path) -> dict[str, object]:
    try:
        return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {"completion_state": "incomplete"}


def _ml_tail_shard_dir(run_dir: Path, payload: dict[str, object]) -> Path:
    return run_dir / "s" / str(payload["shard_id"])


def _with_shard_id(
    rows: list[dict[str, object]],
    payload: dict[str, object],
) -> list[dict[str, object]]:
    shard_id = str(payload["shard_id"])
    return [{**row, "shard_id": row.get("shard_id") or shard_id} for row in rows]


def _sort_ml_tail_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("shard_id") or ""),
            str(row.get("forecast_date") or ""),
            str(row.get("model_name") or ""),
            str(row.get("information_set") or ""),
            str(row.get("tail_side") or ""),
            str(row.get("tail_level") or ""),
            str(row.get("refit_frequency") or ""),
            str(row.get("fit_status") or ""),
        ),
    )
