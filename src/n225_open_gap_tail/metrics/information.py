# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def build_incremental_information_records(
    forecasts: list[dict[str, object]],
    *,
    baseline_information_set: str,
) -> list[dict[str, object]]:
    information_sets = registered_ml_tail_information_sets()
    model_names = sorted(
        {str(row.get("model_name") or "") for row in forecasts if row.get("model_name")}
    )
    comparisons = [
        (information_sets[index], information_sets[index + 1])
        for index in range(len(information_sets) - 1)
    ]
    if information_sets:
        comparisons.insert(0, (baseline_information_set, information_sets[-1]))
    records: list[dict[str, object]] = []
    for model_name in model_names:
        for tail_level in TAIL_LEVELS:
            for base_info, expanded_info in comparisons:
                paired = _paired_forecast_rows(
                    forecasts,
                    model_name=model_name,
                    tail_level=tail_level,
                    base_information_set=base_info,
                    expanded_information_set=expanded_info,
                )
                records.append(
                    _incremental_record_from_pairs(
                        paired,
                        model_name=model_name,
                        tail_level=tail_level,
                        base_information_set=base_info,
                        expanded_information_set=expanded_info,
                        dst_regime=None,
                    )
                )
    return records


def build_dst_attenuation_records(
    forecasts: list[dict[str, object]],
    *,
    baseline_information_set: str,
    expanded_information_set: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    model_names = sorted(
        {str(row.get("model_name") or "") for row in forecasts if row.get("model_name")}
    )
    for model_name in model_names:
        for tail_level in TAIL_LEVELS:
            regime_records: dict[str, dict[str, object]] = {}
            for regime in ("EST", "EDT"):
                paired = _paired_forecast_rows(
                    forecasts,
                    model_name=model_name,
                    tail_level=tail_level,
                    base_information_set=baseline_information_set,
                    expanded_information_set=expanded_information_set,
                    dst_regime=regime,
                )
                row = _incremental_record_from_pairs(
                    paired,
                    model_name=model_name,
                    tail_level=tail_level,
                    base_information_set=baseline_information_set,
                    expanded_information_set=expanded_information_set,
                    dst_regime=regime,
                )
                regime_records[regime] = row
                records.append(row)
            est_gain = _optional_float(regime_records.get("EST", {}).get("mean_fz_gain"))
            edt_gain = _optional_float(regime_records.get("EDT", {}).get("mean_fz_gain"))
            stable = est_gain is not None and est_gain > 0 and edt_gain is not None
            alpha_absorb: float | None = None
            if est_gain is not None and est_gain > 0 and edt_gain is not None:
                alpha_absorb = float(1.0 - edt_gain / est_gain)
            records.append(
                {
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "base_information_set": baseline_information_set,
                    "expanded_information_set": expanded_information_set,
                    "dst_regime": "absorption_coefficient",
                    "paired_rows": None,
                    "mean_quantile_gain": None,
                    "mean_fz_gain": None,
                    "alpha_absorb": alpha_absorb,
                    "alpha_absorb_status": "ok" if stable else "unavailable_unstable_est_gain",
                    "inference_status": "diagnostic_ratio_no_direct_dm_test",
                    "dm_method": None,
                    "dm_pvalue_one_sided": None,
                    "dm_block_length": None,
                    "dm_reps": None,
                    "dm_seed": None,
                }
            )
    return records


def _paired_forecast_rows(
    forecasts: list[dict[str, object]],
    *,
    model_name: str,
    tail_level: float,
    base_information_set: str,
    expanded_information_set: str,
    dst_regime: str | None = None,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    base: dict[str, dict[str, object]] = {}
    expanded: dict[str, dict[str, object]] = {}
    for row in forecasts:
        if row.get("fit_status") != "ok" or row.get("is_valid_forecast") is not True:
            continue
        if str(row.get("model_name") or "") != model_name:
            continue
        if _required_float(row["tail_level"]) != tail_level:
            continue
        if dst_regime is not None and str(row.get("dst_regime") or "") != dst_regime:
            continue
        key = str(row["forecast_date"])
        info = str(row.get("information_set") or "")
        if info == base_information_set:
            base[key] = row
        elif info == expanded_information_set:
            expanded[key] = row
    return [(base[key], expanded[key]) for key in sorted(set(base).intersection(expanded))]


def _incremental_record_from_pairs(
    paired: list[tuple[dict[str, object], dict[str, object]]],
    *,
    model_name: str,
    tail_level: float,
    base_information_set: str,
    expanded_information_set: str,
    dst_regime: str | None,
) -> dict[str, object]:
    q_gains: list[float] = []
    fz_gains: list[float] = []
    for base, expanded in paired:
        loss = _required_float(base["realized_loss"])
        base_var = _required_float(base["var_forecast"])
        expanded_var = _required_float(expanded["var_forecast"])
        base_es = _required_float(base["es_forecast"])
        expanded_es = _required_float(expanded["es_forecast"])
        q_gains.append(
            quantile_loss(loss, base_var, tail_level)
            - quantile_loss(loss, expanded_var, tail_level)
        )
        fz_gains.append(
            fz_loss(loss, base_var, base_es, tail_level)
            - fz_loss(loss, expanded_var, expanded_es, tail_level)
        )
    fz_gain_array = np.array(fz_gains, dtype=float)
    candidate_minus_base = -fz_gain_array
    paired_rows = int(candidate_minus_base[np.isfinite(candidate_minus_base)].size)
    block_length = max(5, round(paired_rows ** (1.0 / 3.0))) if paired_rows else None
    mean_candidate_minus_base = _safe_mean(candidate_minus_base)
    dm_pvalue = (
        _moving_block_one_sided_pvalue(
            candidate_minus_base[np.isfinite(candidate_minus_base)],
            observed_mean=mean_candidate_minus_base,
            reps=BOOTSTRAP_REPS,
            block_length=int(block_length),
            rng=np.random.default_rng(INFERENCE_RANDOM_SEED),
        )
        if mean_candidate_minus_base is not None
        and block_length is not None
        and paired_rows >= PIPELINE_CONFIG.evaluation_policy.min_common_oos_rows
        else None
    )
    inference_status = (
        "ok_block_bootstrap_dm"
        if dm_pvalue is not None
        else "unavailable_block_bootstrap_dm_insufficient_pairs"
    )
    return {
        "model_name": model_name,
        "tail_level": tail_level,
        "base_information_set": base_information_set,
        "expanded_information_set": expanded_information_set,
        "dst_regime": dst_regime,
        "paired_rows": len(paired),
        "common_sample_status": common_sample_status([str(i) for i in range(len(paired))]),
        "mean_quantile_gain": _safe_mean(np.array(q_gains, dtype=float)),
        "mean_fz_gain": _safe_mean(fz_gain_array),
        "dm_method": PIPELINE_CONFIG.evaluation_policy.dm_method,
        "dm_alternative": "expanded_mean_fz_loss_less_than_base",
        "dm_pvalue_one_sided": dm_pvalue,
        "dm_block_length": block_length,
        "dm_reps": BOOTSTRAP_REPS,
        "dm_seed": INFERENCE_RANDOM_SEED,
        "inference_status": inference_status,
    }


def _run_has_locked_outputs(run_dir: Path) -> bool:
    locked_roots = (run_dir / "forecasts", run_dir / "metrics")
    for root in locked_roots:
        if root.exists() and any(path.is_file() for path in root.rglob("*")):
            return True
    return False


def _clear_run_outputs_for_force(run_dir: Path) -> None:
    for name in ("forecasts", "metrics", "latex", "audits"):
        path = run_dir / name
        if path.exists():
            shutil.rmtree(path)


def _assert_run_config_compatible(run_dir: Path, *, force: bool = False) -> None:
    manifest = _read_manifest(run_dir)
    stored_hash = manifest.get("config_hash")
    current_hash = PIPELINE_CONFIG.config_hash()
    locked = _run_has_locked_outputs(run_dir)
    if locked and stored_hash != current_hash:
        if not force:
            raise PipelineRunError(
                "Run config is locked and differs from current research config; "
                "use a new run_id or pass --force to clear run outputs."
            )
        _clear_run_outputs_for_force(run_dir)
    if stored_hash != current_hash:
        _update_manifest(
            run_dir,
            {
                "config_hash": current_hash,
                "config_lock_status": "locked_after_forecasts_or_metrics",
            },
        )


def _gold_artifact_path(run_dir: Path, key: str, fallback: Path) -> Path:
    manifest = _read_manifest(run_dir)
    artifacts = manifest.get("gold_artifacts")
    if isinstance(artifacts, Mapping):
        candidate = artifacts.get(key)
        if isinstance(candidate, str):
            path = Path(candidate)
            if path.exists():
                return path
    return fallback
