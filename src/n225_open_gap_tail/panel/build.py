# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config.runtime import *
from n225_open_gap_tail.data_lake.cache_ops import (
    _fetch_cboe_predictors,
    _fetch_fred_predictors,
    _fetch_jquants_futures_rows,
    _fetch_massive_predictors,
)
from n225_open_gap_tail.config.git import _git_commit, _git_dirty
from n225_open_gap_tail.data_lake.artifacts import _write_json, _write_parquet
from n225_open_gap_tail.features.asof import (
    _canonical_fx_asof,
    _canonical_fx_context,
    _cboe_feature_map,
    _coerce_datetime,
    _features_asof,
    _fred_feature_map,
    _fred_features_asof,
    _massive_daily_feature_map,
    _spy_minute_feature_map,
)
from n225_open_gap_tail.features.descriptions import _feature_description, _safe_name
from n225_open_gap_tail.features.jquants_spy import (
    _write_jquants_silver_cache,
    add_jquants_silver_flags,
    build_spy_late_session_feature_records,
)
from n225_open_gap_tail.panel.target_audit import build_target_audit_records
from n225_open_gap_tail.panel.time_alignment import build_time_alignment_records
from n225_open_gap_tail.sources.jquants_futures import (
    build_jquants_schema_probe,
    normalize_jquants_futures_rows,
)


def build_panel(
    *,
    settings: Settings,
    start: str = MAIN_SAMPLE_START,
    end: str | None = None,
) -> PanelBuildResult:
    run_ts = datetime.now(UTC)
    end_date = end or date.today().isoformat()
    _pipeline_log(f"start window={start}..{end_date}")
    removed_tmp_files = cleanup_orphan_tmp_files(
        settings.data_dir,
        older_than_hours=CACHE_TMP_GC_HOURS,
        now=run_ts,
    )
    _pipeline_log(f"tmp gc removed {len(removed_tmp_files)} orphan temp files")
    removed_transient_markers = cleanup_transient_unavailable_markers(settings.data_dir)
    _pipeline_log(f"transient unavailable marker gc removed {len(removed_transient_markers)} files")
    git_commit = _git_commit()
    run_id = build_run_id(
        start=start,
        end=end_date,
        run_ts_utc=run_ts,
        git_commit=git_commit,
    )
    _pipeline_log(f"run id {run_id}")
    run_dir = settings.reports_dir / "runs" / run_id
    panel_dir = run_dir / "panel"
    config_dir = run_dir / "config"
    gold_run_dir = (
        settings.gold_data_dir / "tailrisk_panel" / "schema_version=1" / f"run_id={run_id}"
    )
    panel_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    gold_run_dir.mkdir(parents=True, exist_ok=True)

    calendar_records = build_session_calendar_records(
        start=(date.fromisoformat(start) - timedelta(days=10)).isoformat(),
        end=end_date,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )
    _pipeline_log(f"calendar records built: {len(calendar_records)}")
    jquants_pull_ts = datetime.now(UTC)
    _pipeline_log("J-Quants bronze fetch/cache start")
    raw_jquants = _fetch_jquants_futures_rows(
        settings=settings,
        start=start,
        end=end_date,
        calendar_records=calendar_records,
        run_start_utc=run_ts,
    )
    _pipeline_log(f"J-Quants bronze rows available: {len(raw_jquants)}")
    schema_probe = build_jquants_schema_probe(raw_jquants)
    if schema_probe["fail_closed"] is True:
        raise PipelineRunError(
            f"J-Quants schema missing required fields: {schema_probe['missing_required_fields']}"
        )
    normalized = add_jquants_silver_flags(
        normalize_jquants_futures_rows(raw_jquants, downloaded_at_utc=jquants_pull_ts)
    )
    _pipeline_log(f"J-Quants normalized NK225F rows: {len(normalized)}")
    _write_jquants_silver_cache(settings=settings, rows=normalized)
    fields_coverage = build_fields_coverage_audit_records(
        normalized,
        policy_start=MAIN_SAMPLE_START,
    )
    jquants_required_start = infer_jquants_required_field_coverage_start(
        fields_coverage,
        fallback=MAIN_SAMPLE_START,
    )
    targets = build_target_audit_records(
        normalized,
        calendar_records=calendar_records,
        roll_days_before_last_trade=settings.nikkei_contract_roll_days_before_last_trade,
    )
    clean_targets = sum(1 for row in targets if row.get("clean_sample") is True)
    _pipeline_log(f"target audit rows built: {len(targets)} rows, clean={clean_targets}")

    predictor_start = (date.fromisoformat(start) - timedelta(days=14)).isoformat()
    massive_pull_ts = datetime.now(UTC)
    _pipeline_log(f"Massive predictors fetch/cache start window={predictor_start}..{end_date}")
    massive_daily, spy_minutes = _fetch_massive_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=massive_pull_ts,
        calendar_records=calendar_records,
    )
    _pipeline_log(
        f"Massive predictors available: daily_rows={len(massive_daily)}, "
        f"spy_minute_feature_rows={len(spy_minutes)}"
    )
    fred_pull_ts = datetime.now(UTC)
    _pipeline_log(f"FRED predictors fetch/cache start window={predictor_start}..{end_date}")
    fred_rows = _fetch_fred_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=fred_pull_ts,
        run_start_utc=run_ts,
    )
    _pipeline_log(f"FRED predictor rows available: {len(fred_rows)}")
    cboe_pull_ts = datetime.now(UTC)
    _pipeline_log(
        f"Cboe volatility predictors fetch/cache start window={predictor_start}..{end_date}"
    )
    cboe_rows = _fetch_cboe_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=cboe_pull_ts,
    )
    vix_consistency = build_vix_consistency_records(
        cboe_records=cboe_rows,
        fred_records=fred_rows,
    )
    _pipeline_log(
        f"Cboe volatility rows available: {len(cboe_rows)}, "
        f"VIX consistency warnings={len(vix_consistency)}"
    )
    alignment = build_time_alignment_records(
        target_rows=targets,
        calendar_records=calendar_records,
        spy_minute_records=spy_minutes,
        vendor_lag_minutes=PIPELINE_CONFIG.leakage_policy.massive_vendor_lag_minutes,
    )
    _pipeline_log(f"time alignment rows built: {len(alignment)}")
    calendar_map = build_calendar_map_records(
        target_rows=targets,
        calendar_records=calendar_records,
        alignment_records=alignment,
    )
    _pipeline_log(f"calendar map rows built: {len(calendar_map)}")
    panel = build_modeling_panel_records(
        target_rows=targets,
        alignment_records=alignment,
        massive_daily_records=massive_daily,
        spy_minute_records=spy_minutes,
        fred_records=fred_rows,
        cboe_records=cboe_rows,
        calendar_records=calendar_records,
        calendar_map_records=calendar_map,
    )
    _pipeline_log(f"modeling panel rows built: {len(panel)}")
    initial_feature_coverage = build_feature_coverage_records(panel)
    effective_predictor_start = build_effective_predictor_start(initial_feature_coverage)
    fred_required_start = _max_date_strings(
        effective_predictor_start.get("fred_core"),
        effective_predictor_start.get("fx_core"),
    )
    combined_clean_start = compute_combined_clean_start(
        jquants_required_field_coverage_start=jquants_required_start,
        massive_daily_entitlement_start=effective_predictor_start.get("massive_daily"),
        fred_required_series_coverage_start=fred_required_start,
    )
    _pipeline_log(f"combined clean start: {combined_clean_start}")
    panel = apply_combined_clean_start(panel, combined_clean_start=combined_clean_start)
    feature_coverage = build_feature_coverage_records(panel)

    target_audit_path = panel_dir / "target_audit.parquet"
    panel_path = panel_dir / "modeling_panel.parquet"
    coverage_path = panel_dir / "feature_coverage.parquet"
    fields_coverage_path = panel_dir / "fields_coverage_audit.parquet"
    calendar_map_path = panel_dir / "calendar_map.parquet"
    vix_consistency_path = panel_dir / "vix_consistency_audit.parquet"
    schema_path = panel_dir / "jquants_schema_probe.json"
    vintage_path = run_dir / "data_vintage.json"
    manifest_path = run_dir / "manifest.json"
    feature_dictionary_path = panel_dir / "feature_dictionary.json"
    gold_target_audit_path = gold_run_dir / "target_audit.parquet"
    gold_panel_path = gold_run_dir / "modeling_panel.parquet"
    gold_coverage_path = gold_run_dir / "feature_coverage.parquet"
    gold_fields_coverage_path = gold_run_dir / "fields_coverage_audit.parquet"
    gold_calendar_map_path = gold_run_dir / "calendar_map.parquet"
    gold_feature_dictionary_path = gold_run_dir / "feature_dictionary.json"
    research_config_path = config_dir / "research_config.json"
    config_hash = PIPELINE_CONFIG.config_hash()
    data_vintage_payload: dict[str, object] = {
        "jquants_pull_ts_utc": jquants_pull_ts.isoformat(),
        "massive_pull_ts_utc": massive_pull_ts.isoformat(),
        "fred_pull_ts_utc": fred_pull_ts.isoformat(),
        "cboe_pull_ts_utc": cboe_pull_ts.isoformat(),
        "window": [start, end_date],
        "predictor_window": [predictor_start, end_date],
        "claims_level": CLAIMS_LEVEL,
        "fred_vintage_policy": PIPELINE_CONFIG.leakage_policy.fred_vintage_policy,
        "fred_vintage_safe": False,
        "fred_ttl_days": FRED_CACHE_TTL_DAYS,
        "fred_ttl_decision_ts_utc": run_ts.isoformat(),
    }

    _write_parquet(target_audit_path, targets)
    _pipeline_log(f"wrote target audit: {target_audit_path}")
    _write_parquet(panel_path, panel)
    _pipeline_log(f"wrote modeling panel: {panel_path}")
    _write_parquet(coverage_path, feature_coverage)
    _pipeline_log(f"wrote feature coverage: {coverage_path}")
    _write_parquet(fields_coverage_path, fields_coverage)
    _pipeline_log(f"wrote fields coverage audit: {fields_coverage_path}")
    _write_parquet(calendar_map_path, calendar_map, schema=CALENDAR_MAP_SCHEMA)
    _pipeline_log(f"wrote calendar map: {calendar_map_path}")
    _write_parquet(vix_consistency_path, vix_consistency)
    _pipeline_log(f"wrote VIX consistency audit: {vix_consistency_path}")
    _write_parquet(gold_target_audit_path, targets)
    _write_parquet(gold_panel_path, panel)
    _write_parquet(gold_coverage_path, feature_coverage)
    _write_parquet(gold_fields_coverage_path, fields_coverage)
    _write_parquet(gold_calendar_map_path, calendar_map, schema=CALENDAR_MAP_SCHEMA)
    _write_json(gold_feature_dictionary_path, build_feature_dictionary(panel))
    _pipeline_log(f"wrote durable gold panel artifacts: {gold_run_dir}")
    _write_json(schema_path, schema_probe)
    _write_json(vintage_path, data_vintage_payload)
    _write_json(feature_dictionary_path, build_feature_dictionary(panel))
    _write_json(
        research_config_path,
        {
            "config_hash": config_hash,
            "research_config": PIPELINE_CONFIG.to_jsonable(),
        },
    )
    _write_json(
        config_dir / "model_config.json",
        {
            "suite": "benchmark",
            "config_hash": config_hash,
            "tail_levels": TAIL_LEVELS,
            "ewma_lambda": EWMA_MAIN_LAMBDA,
            "ewma_sensitivity_lambdas": EWMA_SENSITIVITY_LAMBDAS,
            "oos_start_policy": {
                "earliest_oos_start": DEFAULT_EARLIEST_OOS_START,
                "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                "min_train_exceedances_5pct": DEFAULT_MIN_TRAIN_EXCEEDANCES,
            },
        },
    )
    _write_json(
        manifest_path,
        {
            "run_id": run_id,
            "created_at_utc": run_ts.isoformat(),
            "git_commit": git_commit,
            "git_dirty": _git_dirty(),
            "config_hash": config_hash,
            "cache_key": _run_cache_key(
                git_commit=git_commit,
                start=start,
                end=end_date,
                data_vintage=data_vintage_payload,
            ),
            "claims_level": CLAIMS_LEVEL,
            "claim_level": CLAIMS_LEVEL,
            "suite": "benchmark_panel",
            "gold_root": str(settings.gold_data_dir),
            "gold_artifacts": {
                "target_audit": str(gold_target_audit_path),
                "modeling_panel": str(gold_panel_path),
                "feature_coverage": str(gold_coverage_path),
                "fields_coverage_audit": str(gold_fields_coverage_path),
                "calendar_map": str(gold_calendar_map_path),
                "feature_dictionary": str(gold_feature_dictionary_path),
            },
            "window": [start, end_date],
            "sample_policy": "clean_predictor_entitlement_sample",
            "main_sample_start_requested": start,
            "audit_sample_start": AUDIT_SAMPLE_START,
            "main_sample_rationale": (
                "Main modeling panel starts no earlier than J-Quants futures required "
                "field coverage, Massive entitlement, and required FRED coverage."
            ),
            "combined_clean_start": combined_clean_start,
            "effective_predictor_start": effective_predictor_start,
            "jquants_required_field_coverage_start": jquants_required_start,
            "jquants_derivatives_intraday_available": False,
            "residual_usclosemark_reason": (
                "No licensed timestamped intraday OSE/CME/SGX Nikkei futures mark in this run."
            ),
            "cache_gc": {
                "tmp_gc_hours": CACHE_TMP_GC_HOURS,
                "removed_tmp_files": len(removed_tmp_files),
                "removed_transient_unavailable_markers": len(removed_transient_markers),
            },
            "cache_provenance": {
                "chunk_hash_algo": CHUNK_HASH_ALGO,
                "jquants_bronze_schema_hash": JQUANTS_BRONZE_SCHEMA.hash,
                "jquants_silver_schema_hash": JQUANTS_SILVER_SCHEMA.hash,
                "calendar_map_schema_hash": CALENDAR_MAP_SCHEMA.hash,
                "spy_minute_feature_schema_hash": SPY_MINUTE_FEATURE_SCHEMA.hash,
                "fred_cache_schema_hash": FRED_CACHE_SCHEMA.hash,
            },
            "feature_set_version": FeatureSetVersion.CORE_FULL_HISTORY.value,
            "massive_core_symbols": CORE_MASSIVE_TICKERS_FOR_PIPELINE,
            "massive_optional_symbols": OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE,
            "massive_japan_proxy_symbols": JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
            "massive_asia_proxy_symbols": ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
            "massive_fetched_symbols": FETCH_MASSIVE_TICKERS_FOR_PIPELINE,
            "massive_symbols": FETCH_MASSIVE_TICKERS_FOR_PIPELINE,
            "fred_core_series": CORE_FRED_SERIES_FOR_PIPELINE,
            "fred_fx_fallback_series": FX_FRED_SERIES_FOR_PIPELINE,
            "fred_credit_enriched_series": CREDIT_ENRICHED_FRED_SERIES_FOR_PIPELINE,
            "fred_series": FETCH_FRED_SERIES_FOR_PIPELINE,
            "fred_vintage_policy": PIPELINE_CONFIG.leakage_policy.fred_vintage_policy,
            "fx_policy": {
                "canonical_features": ["fx_usdjpy_level", "fx_usdjpy_return"],
                "source_precedence": ["fred_h10_latest_released", "null_unavailable"],
                "h10_release_age_cap_calendar_days": FRED_H10_RELEASE_AGE_CAP_DAYS,
            },
            "target_policy": {
                "primary_target_family": PIPELINE_CONFIG.target_policy.primary_target_family,
                "residual_usclosemark_enabled": (
                    PIPELINE_CONFIG.target_policy.residual_usclosemark_enabled
                ),
                "residual_usclosemark_status": (
                    PIPELINE_CONFIG.target_policy.residual_usclosemark_status
                ),
            },
            "leakage_policy": {
                "fred_availability_lag_us_business_days": (
                    PIPELINE_CONFIG.leakage_policy.fred_availability_lag_us_business_days
                ),
                "max_forward_fill_us_close_days": (
                    PIPELINE_CONFIG.leakage_policy.max_forward_fill_us_close_days
                ),
                "leakage_warning_min_lag_minutes": (
                    PIPELINE_CONFIG.leakage_policy.leakage_warning_min_lag_minutes
                ),
            },
            "evaluation_policy": {
                "primary_common_sample": PIPELINE_CONFIG.evaluation_policy.primary_common_sample,
                "pairwise_inference_sample": (
                    PIPELINE_CONFIG.evaluation_policy.pairwise_inference_sample
                ),
                "global_headline_sample": PIPELINE_CONFIG.evaluation_policy.global_headline_sample,
            },
            "residual_usclosemark_status": (
                PIPELINE_CONFIG.target_policy.residual_usclosemark_status
            ),
            "residual_usclosemark_enabled": (
                PIPELINE_CONFIG.target_policy.residual_usclosemark_enabled
            ),
            "artifact_paths": {
                "modeling_panel": str(panel_path),
                "target_audit": str(target_audit_path),
                "feature_coverage": str(coverage_path),
                "fields_coverage_audit": str(fields_coverage_path),
                "calendar_map": str(calendar_map_path),
                "vix_consistency_audit": str(vix_consistency_path),
                "feature_dictionary": str(feature_dictionary_path),
                "schema_probe": str(schema_path),
                "data_vintage": str(vintage_path),
                "research_config": str(research_config_path),
            },
        },
    )
    clean_rows = sum(1 for row in panel if row.get("clean_sample") is True)
    _pipeline_log(f"panel complete rows={len(panel)} clean_rows={clean_rows}")
    return PanelBuildResult(
        run_id=run_id,
        run_dir=run_dir,
        panel_path=gold_panel_path,
        rows=len(panel),
        clean_rows=clean_rows,
    )


def build_modeling_panel_records(
    *,
    target_rows: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
    massive_daily_records: list[dict[str, object]],
    spy_minute_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    cboe_records: list[dict[str, object]] | None = None,
    calendar_records: list[dict[str, object]] | None = None,
    calendar_map_records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    alignment_by_target = {str(row["trading_date"]): row for row in alignment_records}
    calendar_map_by_target = {
        str(row["ose_trading_date"]): row for row in (calendar_map_records or [])
    }
    massive_features = _massive_daily_feature_map(
        massive_daily_records,
        calendar_records=calendar_records or [],
    )
    fred_features = _fred_feature_map(fred_records)
    cboe_features = _cboe_feature_map(cboe_records or [])
    spy_features = _spy_minute_feature_map(spy_minute_records)
    fx_context = _canonical_fx_context(
        massive_daily_records=massive_daily_records,
        fred_records=fred_records,
        calendar_records=calendar_records or [],
    )
    panel: list[dict[str, object]] = []
    for target in target_rows:
        trading_date = str(target["trading_date"])
        alignment = alignment_by_target.get(trading_date, {})
        calendar_map = calendar_map_by_target.get(trading_date, {})
        us_date = str(alignment.get("us_calendar_date") or "")
        cutoff = _coerce_datetime(alignment.get("model_cutoff_ts_utc"))
        target_open = _coerce_datetime(
            alignment.get("target_open_ts_utc") or target.get("target_open_ts_utc")
        )
        join_miss_reason = _panel_join_miss_reason(alignment, us_date)
        mapping_status = str(calendar_map.get("mapping_status") or MappingStatus.UNMAPPED.value)
        forecast_sample_reason = _forecast_sample_exclusion_reason(
            target_clean=target.get("clean_sample") is True,
            mapping_status=mapping_status,
            join_miss_reason=join_miss_reason,
            cutoff=cutoff,
            target_open=target_open,
        )
        forecast_sample = forecast_sample_reason is None
        record: dict[str, object] = {
            "forecast_date": trading_date,
            "target_family": "full_gap_settle_to_open",
            "forecast_origin_name": "US_CASH_CLOSE",
            "information_set": "core_full_history",
            "contract_code": target.get("contract_code"),
            "contract_month": target.get("contract_month"),
            "clean_sample": forecast_sample,
            "target_clean_sample": target.get("clean_sample"),
            "forecast_sample": forecast_sample,
            "forecast_sample_reason": forecast_sample_reason,
            "same_contract_flag": target.get("same_contract_only"),
            "roll_window_flag": target.get("is_roll_sq_window"),
            "sq_window_flag": target.get("is_roll_sq_window"),
            "missing_reason": target.get("missing_reason"),
            "target_open_ts_utc": target_open,
            "model_cutoff_ts_utc": alignment.get("model_cutoff_ts_utc"),
            "dst_regime": alignment.get("dst_regime"),
            "absorption_regime": alignment.get("absorption_regime"),
            "us_calendar_date": us_date or None,
            "join_miss_reason": join_miss_reason,
            "mapping_status": mapping_status,
            "mapping_reason": calendar_map.get("mapping_reason"),
            "gap_t": target.get("full_gap_settle_to_open"),
            "realized_loss": target.get("loss_settle_to_open"),
            "full_gap_close_to_open": target.get("full_gap_close_to_open"),
            "residual_nightclose_to_day_open": target.get("residual_nightclose_to_day_open"),
            "residual_usclosemark_to_open": None,
            "residual_usclosemark_status": (
                PIPELINE_CONFIG.target_policy.residual_usclosemark_status
            ),
            "volume": target.get("volume"),
            "open_interest": target.get("open_interest"),
            "volume_oi_anomaly": target.get("volume_oi_anomaly"),
        }
        record.update(
            _features_asof(
                massive_features,
                us_date,
                cutoff=cutoff,
                fill_method="forward_fill_us_holiday",
            )
        )
        record.update(
            _fred_features_asof(
                fred_features,
                us_date,
                cutoff=cutoff,
            )
        )
        record.update(
            _features_asof(
                cboe_features,
                us_date,
                cutoff=cutoff,
                fill_method="forward_fill_us_holiday",
            )
        )
        record.update(
            _features_asof(
                spy_features,
                us_date,
                cutoff=cutoff,
                fill_method="forward_fill_us_holiday",
            )
        )
        record.update(_canonical_fx_asof(fx_context, us_date=us_date, cutoff=cutoff))
        panel.append(record)
    panel.sort(key=lambda row: str(row["forecast_date"]))
    return panel


def apply_combined_clean_start(
    panel: list[dict[str, object]],
    *,
    combined_clean_start: str,
) -> list[dict[str, object]]:
    """Apply the audited combined clean start as the forecast-sample lower bound."""
    try:
        threshold = date.fromisoformat(combined_clean_start)
    except ValueError:
        return panel
    output: list[dict[str, object]] = []
    for row in panel:
        forecast_date_raw = str(row.get("forecast_date") or "")
        try:
            forecast_date = date.fromisoformat(forecast_date_raw)
        except ValueError:
            output.append(row)
            continue
        if row.get("forecast_sample") is True and forecast_date < threshold:
            output.append(
                {
                    **row,
                    "clean_sample": False,
                    "forecast_sample": False,
                    "forecast_sample_reason": (
                        ForecastExclusionReason.BEFORE_COMBINED_CLEAN_START.value
                    ),
                    "combined_clean_start": combined_clean_start,
                }
            )
        else:
            output.append({**row, "combined_clean_start": combined_clean_start})
    return output


def build_feature_coverage_records(panel: list[dict[str, object]]) -> list[dict[str, object]]:
    if not panel:
        return []
    base_fields = {
        "forecast_date",
        "target_family",
        "forecast_origin_name",
        "information_set",
        "contract_code",
        "contract_month",
        "clean_sample",
        "target_clean_sample",
        "forecast_sample",
        "forecast_sample_reason",
        "combined_clean_start",
        "same_contract_flag",
        "roll_window_flag",
        "sq_window_flag",
        "missing_reason",
        "target_open_ts_utc",
        "model_cutoff_ts_utc",
        "dst_regime",
        "absorption_regime",
        "us_calendar_date",
        "join_miss_reason",
        "mapping_status",
        "mapping_reason",
        "gap_t",
        "realized_loss",
        "full_gap_close_to_open",
        "residual_nightclose_to_day_open",
        "residual_usclosemark_to_open",
        "residual_usclosemark_status",
        "volume",
        "open_interest",
        "volume_oi_anomaly",
        "fx_source",
        "fx_observation_date",
        "fx_available_ts_utc",
        "fx_staleness_days",
        "fx_is_stale",
        "fx_fallback_reason",
        "fred_dexjpus_available",
    }
    clean_rows = [row for row in panel if row.get("clean_sample") is True]
    records: list[dict[str, object]] = []
    feature_fields = [
        field
        for field in sorted(set().union(*(row.keys() for row in panel)).difference(base_fields))
        if "__" not in field
    ]
    for field in feature_fields:
        non_missing_rows = [row for row in clean_rows if row.get(field) is not None]
        source_dates = [
            str(row[f"{field}__source_date"])
            for row in non_missing_rows
            if row.get(f"{field}__source_date") is not None
        ]
        first_source_date = min(source_dates) if source_dates else None
        last_source_date = max(source_dates) if source_dates else None
        records.append(
            {
                "feature": field,
                "clean_rows": len(clean_rows),
                "non_missing_rows": len(non_missing_rows),
                "missingness_rate": 1.0 - len(non_missing_rows) / len(clean_rows)
                if clean_rows
                else None,
                "first_valid_date": first_source_date,
                "last_valid_date": last_source_date,
                "source_family": _feature_source_family(field),
                "source_block": _feature_source_block(field),
                "vintage_safe": not field.startswith("fred_"),
                "revision_risk_label": (
                    "current_historical_revisions" if field.startswith("fred_") else None
                ),
            }
        )
    return records


def build_effective_predictor_start(
    coverage_rows: list[dict[str, object]],
) -> dict[str, str | None]:
    grouped: dict[str, list[str]] = {
        "massive_daily": [],
        "fred_core": [],
        "fx_core": [],
        "spy_minute": [],
    }
    for row in coverage_rows:
        first_valid = row.get("first_valid_date")
        if not isinstance(first_valid, str) or not first_valid:
            continue
        family = str(row.get("source_family") or "")
        if family in grouped:
            grouped[family].append(first_valid)
    return {family: max(values) if values else None for family, values in grouped.items()}


def registered_ml_tail_information_sets() -> tuple[str, ...]:
    return (
        PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_b_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_d_information_set,
    )


def ml_tail_feature_columns_for_information_set(
    coverage_rows: list[dict[str, object]],
    *,
    information_set: str,
) -> list[str]:
    """Return the pre-registered ML tail candidate features for an information set."""
    blocks: set[str] = set()
    if information_set == PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set:
        blocks = set()
    elif information_set == PIPELINE_CONFIG.feature_sets.ml_tail_model_b_information_set:
        blocks = {"us_core", "us_late_session", "fred_core", "fx_core"}
    elif information_set == PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set:
        blocks = {"us_core", "us_late_session", "fred_core", "fx_core", "japan_proxy"}
    elif information_set == PIPELINE_CONFIG.feature_sets.ml_tail_model_d_information_set:
        blocks = {
            "us_core",
            "us_late_session",
            "fred_core",
            "fx_core",
            "japan_proxy",
            "asia_proxy",
        }
    else:
        raise PipelineRunError(f"Unknown ML tail information set: {information_set}")
    block_features = [
        str(row["feature"])
        for row in coverage_rows
        if str(row.get("source_block") or "") in blocks and row.get("feature")
    ]
    return list(dict.fromkeys((*ML_TAIL_HISTORY_FEATURES, *sorted(block_features))))


def _max_date_strings(*values: str | None) -> str | None:
    valid = [value for value in values if isinstance(value, str) and value]
    return max(valid) if valid else None


def build_fields_coverage_audit_records(
    rows: list[dict[str, object]],
    *,
    policy_start: str = MAIN_SAMPLE_START,
) -> list[dict[str, object]]:
    required_fields = (
        "settlement_price",
        "last_trading_day",
        "special_quotation_day",
        "central_contract_month_flag",
    )
    before = [row for row in rows if str(row.get("trading_date", "")) < policy_start]
    after = [row for row in rows if str(row.get("trading_date", "")) >= policy_start]
    records: list[dict[str, object]] = []
    for sample_name, sample in (("pre_policy_start", before), ("policy_start_forward", after)):
        for field in required_fields:
            non_missing = sum(1 for row in sample if row.get(field) is not None)
            records.append(
                {
                    "sample": sample_name,
                    "policy_start": policy_start,
                    "field": field,
                    "rows": len(sample),
                    "non_missing_rows": non_missing,
                    "missingness_rate": 1.0 - non_missing / len(sample) if sample else None,
                    "coverage_supports_policy_start": (
                        sample_name == "policy_start_forward"
                        and bool(sample)
                        and non_missing / len(sample) >= 0.95
                    ),
                }
            )
    return records


def infer_jquants_required_field_coverage_start(
    coverage_rows: list[dict[str, object]],
    *,
    fallback: str = MAIN_SAMPLE_START,
) -> str:
    after_rows = [row for row in coverage_rows if row.get("sample") == "policy_start_forward"]
    if after_rows and all(row.get("coverage_supports_policy_start") is True for row in after_rows):
        return fallback
    return fallback


def build_calendar_map_records(
    *,
    target_rows: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
    alignment_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    calendar_by_date = {str(row["calendar_date"]): row for row in calendar_records}
    alignment_by_target = {str(row["trading_date"]): row for row in alignment_records}
    records: list[dict[str, object]] = []
    for target in target_rows:
        ose_date = str(target["trading_date"])
        alignment = alignment_by_target.get(ose_date, {})
        us_session_date = str(alignment.get("us_calendar_date") or "")
        calendar_row = calendar_by_date.get(us_session_date) or calendar_by_date.get(ose_date) or {}
        mapping_status, mapping_reason = _calendar_mapping_status(
            target=target,
            alignment=alignment,
            calendar_row=calendar_row,
        )
        records.append(
            {
                "ose_trading_date": ose_date,
                "us_session_date": us_session_date or None,
                "us_official_close_ts_utc": _coerce_datetime(
                    alignment.get("us_official_close_ts_utc")
                    or alignment.get("model_cutoff_ts_utc")
                    or calendar_row.get("us_close_ts_utc")
                ),
                "us_early_close_flag": bool(calendar_row.get("is_us_early_close", False)),
                "dst_regime": alignment.get("dst_regime") or calendar_row.get("dst_regime"),
                "ose_day_open_ts_utc": _coerce_datetime(
                    alignment.get("target_open_ts_utc") or target.get("target_open_ts_utc")
                ),
                "ose_night_close_ts_utc": _coerce_datetime(
                    alignment.get("ose_night_close_ts_utc")
                    or calendar_row.get("ose_night_close_ts_utc")
                ),
                "us_close_to_ose_night_close_minutes": _optional_float(
                    alignment.get("us_close_to_ose_night_close_minutes")
                    or calendar_row.get("us_close_to_ose_night_close_minutes")
                ),
                "model_cutoff_ts_utc": _coerce_datetime(alignment.get("model_cutoff_ts_utc")),
                "target_open_ts_utc": _coerce_datetime(
                    alignment.get("target_open_ts_utc") or target.get("target_open_ts_utc")
                ),
                "mapping_status": mapping_status,
                "mapping_reason": mapping_reason,
            }
        )
    return records


def build_feature_dictionary(panel: list[dict[str, object]]) -> dict[str, str]:
    return {
        field: _feature_description(field)
        for field in sorted(set().union(*(row.keys() for row in panel)) if panel else set())
        if "__" not in field
        and (
            field.endswith("_return")
            or field.endswith("_range")
            or field.endswith("_diff")
            or field.endswith("_days")
            or field.startswith("fred_")
            or field.startswith("cboe_")
            or field.startswith("spy_late_")
            or field.startswith("spy_final_")
        )
    }


def _feature_source_family(field: str) -> str:
    if field.startswith("fx_usdjpy_"):
        return "fx_core"
    if field.startswith("fred_"):
        if field.startswith("fred_baml"):
            return "fred_credit_enriched"
        return "fred_core"
    if field.startswith("cboe_"):
        return "cboe_volatility"
    if field.startswith("spy_late_") or field.startswith("spy_final_"):
        return "spy_minute"
    if _feature_matches_tickers(field, OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE):
        return "massive_optional"
    if _feature_matches_tickers(field, JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "japan_proxy"
    if _feature_matches_tickers(field, ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "asia_proxy"
    if field.endswith("_return") or field.endswith("_range"):
        return "massive_daily"
    return "unknown"


def _feature_source_block(field: str) -> str:
    if field.startswith("fx_usdjpy_"):
        return "fx_core"
    if field.startswith("fred_"):
        if field.startswith("fred_baml"):
            return "fred_credit_enriched"
        return "fred_core"
    if field.startswith("cboe_"):
        # Cboe is the preferred VIX source, but it enters the same volatility block
        # as FRED VIX in the registered ML tail information-set ladder.
        return "fred_core"
    if field.startswith("spy_late_") or field.startswith("spy_final_"):
        return "us_late_session"
    if _feature_matches_tickers(field, OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE):
        return "massive_optional"
    if _feature_matches_tickers(field, JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "japan_proxy"
    if _feature_matches_tickers(field, ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE):
        return "asia_proxy"
    if _feature_matches_tickers(field, CORE_MASSIVE_TICKERS_FOR_PIPELINE):
        return "us_core"
    return "unknown"


def _feature_matches_tickers(field: str, tickers: tuple[str, ...]) -> bool:
    return any(field.startswith(f"{_safe_name(ticker)}_") for ticker in tickers)


def _panel_join_miss_reason(alignment: Mapping[str, object], us_date: str) -> str | None:
    if not alignment:
        return JoinMissReason.CALENDAR_DESYNC.value
    if alignment.get("alignment_status") == "missing_us_close":
        return JoinMissReason.US_MARKET_CLOSED.value
    if not us_date:
        return JoinMissReason.CALENDAR_DESYNC.value
    if alignment.get("alignment_pass") is False:
        return JoinMissReason.US_EARLY_CLOSE_BEYOND_VENDOR_LAG.value
    return None


def _forecast_sample_exclusion_reason(
    *,
    target_clean: bool,
    mapping_status: str,
    join_miss_reason: str | None,
    cutoff: datetime | None,
    target_open: datetime | None,
) -> str | None:
    if not target_clean:
        return ForecastExclusionReason.TARGET_NOT_CLEAN.value
    if mapping_status != MappingStatus.NORMAL_TRADING.value:
        return ForecastExclusionReason.MAPPING_NOT_NORMAL.value
    if join_miss_reason:
        return ForecastExclusionReason.JOIN_MISS.value
    if cutoff is None or target_open is None:
        return ForecastExclusionReason.MISSING_CUTOFF_OR_TARGET_OPEN.value
    if cutoff >= target_open:
        return ForecastExclusionReason.CUTOFF_AFTER_TARGET_OPEN.value
    return None


def _calendar_mapping_status(
    *,
    target: Mapping[str, object],
    alignment: Mapping[str, object],
    calendar_row: Mapping[str, object],
) -> tuple[str, str | None]:
    if not alignment:
        return MappingStatus.UNMAPPED.value, "missing_time_alignment"
    if alignment.get("alignment_status") == "missing_us_close":
        return MappingStatus.US_HOLIDAY.value, "no_us_close_before_target_open"
    if target.get("missing_reason") == "holiday_trading_no_day_open":
        return MappingStatus.OSE_HOLIDAY_TRADING.value, "ose_holiday_trading_no_day_open"
    if (
        calendar_row.get("is_us_trading_day") is False
        and calendar_row.get("is_jpx_trading_day") is True
    ):
        return MappingStatus.US_HOLIDAY.value, "us_closed_jpx_open"
    if (
        calendar_row.get("is_jpx_trading_day") is False
        and calendar_row.get("is_us_trading_day") is True
    ):
        return MappingStatus.US_JP_DESYNC.value, "us_open_jpx_closed"
    if alignment.get("alignment_pass") is False:
        return MappingStatus.US_JP_DESYNC.value, str(alignment.get("alignment_reason"))
    return MappingStatus.NORMAL_TRADING.value, None
