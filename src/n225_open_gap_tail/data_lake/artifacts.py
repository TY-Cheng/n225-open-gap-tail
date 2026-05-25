# mypy: ignore-errors
# ruff: noqa: F401,I001,UP035
from __future__ import annotations

import hashlib

from n225_open_gap_tail.config.runtime import (
    Any,
    atomic_write_parquet,
    cast,
    CLAIMS_LEVEL,
    json,
    Mapping,
    Path,
    PIPELINE_CONFIG,
    PRIMARY_TAIL_SIDE,
    write_json_atomic,
    _required_float,
)


def _artifact_safe_name(value: object) -> str:
    text = str(value).strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "value"


_SHARD_ALIASES: dict[str, dict[str, str]] = {
    "model": {
        "historical_quantile": "hist_q",
        "rolling_quantile": "roll_q",
        "ewma": "ewma",
        "garch_student_t": "garch_t",
        "gjr_garch_student_t": "gjr_t",
        "gjr_garch_evt": "gjr_evt",
        "caviar_sav": "caviar_sav",
        "caviar_as": "caviar_as",
        "caviar_asymmetric_slope": "caviar_asym",
        "care_sav": "care_sav",
        "care_as": "care_as",
        "care_expectile_sav": "care_sav",
        "care_expectile_asymmetric_slope": "care_asym",
        "gas_t_location_scale": "gas_t_ls",
        "gas_t_pot_gpd": "gas_t_pot",
        "lightgbm_direct_quantile": "lgbm_q",
        "lightgbm_location_scale_empirical": "lgbm_ls_emp",
        "lightgbm_standardized_loss_pot_gpd_plain_mle": "lgbm_pot_plain",
        "lightgbm_standardized_loss_pot_gpd_unibm": "lgbm_pot_unibm",
        "lightgbm_median_mad_pot_gpd_plain_mle": "lgbm_mad_pot_plain",
        "lightgbm_median_mad_pot_gpd_unibm": "lgbm_mad_pot_unibm",
        "lightgbm_median_iqr_pot_gpd_plain_mle": "lgbm_iqr_pot_plain",
        "lightgbm_median_iqr_pot_gpd_unibm": "lgbm_iqr_pot_unibm",
    },
    "target": {
        "full_gap_settle_to_open": "sto",
        "full_gap_close_to_open": "cto",
        "residual_nightclose_to_day_open": "nco",
        "residual_usclosemark_to_open": "uco",
    },
    "side": {
        "left_tail": "L",
        "right_tail": "R",
    },
    "info": {
        "target_history_only": "hist",
        "japan_only": "A",
        "japan_only_plus_us_close_core": "B",
        "japan_only_plus_us_close_core_plus_japan_proxy": "C",
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy": "D",
        "japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy_plus_options_risk": "E",
    },
    "refit": {
        "monthly": "m",
        "monthly_parameter_refit_daily_filter": "m_state",
    },
}


def _artifact_compact_name(kind: str, value: object) -> str:
    safe = _artifact_safe_name(value)
    alias = _SHARD_ALIASES.get(kind, {}).get(safe)
    if alias:
        return alias
    if len(safe) <= 28:
        return safe
    digest = hashlib.blake2s(safe.encode("utf-8"), digest_size=5).hexdigest()
    return f"{safe[:20]}_{digest}"


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


def _gold_panel_dir(gold_root: Path, run_id: str) -> Path:
    return gold_root / "tp" / run_id


def _gold_leakage_dir(gold_root: Path, run_id: str) -> Path:
    return gold_root / "ls" / run_id


def _write_forecast_shards(
    forecast_root: Path,
    forecasts: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
    failures: list[dict[str, object]],
) -> None:
    shard_root = forecast_root.parent / "s"
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
            shard_dir / "f.pq",
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
            shard_dir / "d.pq",
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
            shard_dir / "x.pq",
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
                "shard_path_schema": "compact",
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
        _artifact_compact_name("model", model_name),
        _artifact_compact_name("target", target_family),
        _artifact_compact_name("side", tail_side),
        _artifact_compact_name("info", information_set),
        f"q{tail_level:.3f}".replace(".", ""),
    ]
    if refit_frequency:
        parts.append(_artifact_compact_name("refit", refit_frequency))
    return "__".join(parts)


def _write_parquet(
    path: Path,
    rows: list[dict[str, object]],
    *,
    schema: object | None = None,
) -> None:
    atomic_write_parquet(path, rows, schema=cast(Any, schema))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    write_json_atomic(path, payload)
