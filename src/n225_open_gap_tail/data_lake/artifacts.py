# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import *


def _artifact_safe_name(value: object) -> str:
    text = str(value).strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "value"


def _read_manifest(run_dir: Path) -> dict[str, object]:
    path = run_dir / "manifest.json"
    if not path.exists():
        return {}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _update_manifest(run_dir: Path, updates: dict[str, object]) -> None:
    path = run_dir / "manifest.json"
    manifest = _read_manifest(run_dir)
    manifest.update(updates)
    _write_json(path, manifest)


def _gold_artifact_path(run_dir: Path, key: str, fallback: Path) -> Path:
    manifest = _read_manifest(run_dir)
    gold_artifacts = manifest.get("gold_artifacts")
    if isinstance(gold_artifacts, Mapping):
        raw_path = gold_artifacts.get(key)
        if isinstance(raw_path, str) and raw_path:
            return Path(raw_path)
    return fallback


def _write_forecast_shards(
    forecast_root: Path,
    forecasts: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
    failures: list[dict[str, object]],
) -> None:
    shard_root = forecast_root / "shards"
    keys = {
        (
            str(row["model_name"]),
            str(row.get("target_family") or "full_gap_settle_to_open"),
            str(row.get("tail_side") or PRIMARY_TAIL_SIDE),
            str(row.get("information_set") or "target_history_only"),
            _required_float(row["tail_level"]),
            str(row.get("refit_frequency") or ""),
        )
        for row in [*forecasts, *diagnostics, *failures]
        if "model_name" in row and "tail_level" in row
    }
    for (
        model_name,
        target_family,
        tail_side,
        information_set,
        tail_level,
        refit_frequency,
    ) in sorted(keys):
        shard_dir = shard_root / _forecast_shard_id(
            model_name,
            tail_level,
            target_family=target_family,
            tail_side=tail_side,
            information_set=information_set,
            refit_frequency=refit_frequency or None,
        )
        _write_parquet(
            shard_dir / "forecasts.parquet",
            [
                row
                for row in forecasts
                if row.get("model_name") == model_name
                and str(row.get("target_family") or "full_gap_settle_to_open") == target_family
                and str(row.get("tail_side") or PRIMARY_TAIL_SIDE) == tail_side
                and str(row.get("information_set") or "target_history_only") == information_set
                and _required_float(row["tail_level"]) == tail_level
                and str(row.get("refit_frequency") or "") == refit_frequency
            ],
        )
        _write_parquet(
            shard_dir / "fit_diagnostics.parquet",
            [
                row
                for row in diagnostics
                if row.get("model_name") == model_name
                and str(row.get("target_family") or "full_gap_settle_to_open") == target_family
                and str(row.get("tail_side") or PRIMARY_TAIL_SIDE) == tail_side
                and str(row.get("information_set") or "target_history_only") == information_set
                and _required_float(row["tail_level"]) == tail_level
                and str(row.get("refit_frequency") or "") == refit_frequency
            ],
        )
        _write_parquet(
            shard_dir / "failures.parquet",
            [
                row
                for row in failures
                if row.get("model_name") == model_name
                and str(row.get("target_family") or "full_gap_settle_to_open") == target_family
                and str(row.get("tail_side") or PRIMARY_TAIL_SIDE) == tail_side
                and str(row.get("information_set") or "target_history_only") == information_set
                and _required_float(row["tail_level"]) == tail_level
                and str(row.get("refit_frequency") or "") == refit_frequency
            ],
        )
        _write_json(
            shard_dir / "status.json",
            {
                "claims_level": CLAIMS_LEVEL,
                "claim_level": CLAIMS_LEVEL,
                "config_hash": PIPELINE_CONFIG.config_hash(),
                "completion_state": "complete",
                "model_name": model_name,
                "target_family": target_family,
                "tail_side": tail_side,
                "information_set": information_set,
                "tail_level": tail_level,
                "refit_frequency": refit_frequency or None,
                "shard_id": _forecast_shard_id(
                    model_name,
                    tail_level,
                    target_family=target_family,
                    tail_side=tail_side,
                    information_set=information_set,
                    refit_frequency=refit_frequency or None,
                ),
            },
        )


def _forecast_shard_id(
    model_name: str,
    tail_level: float,
    *,
    target_family: str = "full_gap_settle_to_open",
    tail_side: str = PRIMARY_TAIL_SIDE,
    information_set: str = "target_history_only",
    refit_frequency: str | None = None,
) -> str:
    parts = [
        f"model={_artifact_safe_name(model_name)}",
        f"target={_artifact_safe_name(target_family)}",
        f"side={_artifact_safe_name(tail_side)}",
        f"info={_artifact_safe_name(information_set)}",
        f"tail={tail_level:.3f}".replace(".", "_"),
    ]
    if refit_frequency:
        parts.append(f"refit={_artifact_safe_name(refit_frequency)}")
    return "/".join(parts)


def _write_parquet(
    path: Path,
    rows: list[dict[str, object]],
    *,
    schema: object | None = None,
) -> None:
    atomic_write_parquet(path, rows, schema=cast(Any, schema))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    write_json_atomic(path, payload)
