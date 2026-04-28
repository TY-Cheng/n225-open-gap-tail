from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from joblib import Parallel, delayed  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]

from n225_open_gap_tail.calendars import build_session_calendar_records
from n225_open_gap_tail.config import Settings
from n225_open_gap_tail.datalake import (
    AUDIT_SAMPLE_START,
    CACHE_TMP_GC_HOURS,
    CALENDAR_MAP_SCHEMA,
    CHUNK_HASH_ALGO,
    FRED_CACHE_SCHEMA,
    FRED_CACHE_TTL_DAYS,
    JQUANTS_BRONZE_SCHEMA,
    JQUANTS_SILVER_SCHEMA,
    MAIN_SAMPLE_START,
    SPY_MINUTE_FEATURE_SCHEMA,
    VendorErrorClass,
    atomic_write_parquet,
    cache_path,
    classify_vendor_error,
    cleanup_orphan_tmp_files,
    compute_combined_clean_start,
    is_fred_cache_fresh_at_run_start,
    read_json,
    write_json_atomic,
)
from n225_open_gap_tail.fred import FredClient, normalize_fred_rows
from n225_open_gap_tail.jquants import JQuantsV2Client
from n225_open_gap_tail.massive import MassiveClient, normalize_aggregate_bars
from n225_open_gap_tail.research_config import (
    ClaimLevel,
    FeatureSetVersion,
    default_paper_research_config,
    stable_hash,
)
from n225_open_gap_tail.schemas import JoinMissReason, MappingStatus
from n225_open_gap_tail.snapshot import (
    build_jquants_schema_probe,
    build_target_audit_records,
    build_time_alignment_records,
    normalize_jquants_futures_rows,
)

PAPER_CONFIG = default_paper_research_config()
PAPER_CLAIMS_LEVEL = ClaimLevel.PAPER_CANDIDATE.value
PAPER_CORE_MASSIVE_TICKERS = PAPER_CONFIG.feature_sets.massive_core
PAPER_CORE_FRED_SERIES = PAPER_CONFIG.feature_sets.fred_core
PAPER_TAIL_LEVELS = PAPER_CONFIG.model_policy.tail_levels
EWMA_MAIN_LAMBDA = PAPER_CONFIG.model_policy.ewma_lambda
EWMA_SENSITIVITY_LAMBDAS = PAPER_CONFIG.model_policy.ewma_sensitivity_lambdas
DEFAULT_MIN_TRAIN_ROWS = PAPER_CONFIG.model_policy.min_train_rows
DEFAULT_MIN_TRAIN_EXCEEDANCES = PAPER_CONFIG.model_policy.min_train_exceedances
DEFAULT_EARLIEST_OOS_START = PAPER_CONFIG.model_policy.earliest_oos_start
LOW_VARIANCE_THRESHOLD = PAPER_CONFIG.model_policy.low_variance_threshold
NEAR_ZERO_VARIANCE_THRESHOLD = PAPER_CONFIG.model_policy.near_zero_variance_threshold
SHARD_SIZE_FORECAST_DATES = PAPER_CONFIG.model_policy.shard_size_forecast_dates
EVT_THRESHOLD_QUANTILE = PAPER_CONFIG.model_policy.evt_threshold_quantile
EVT_THRESHOLD_GRID = PAPER_CONFIG.model_policy.evt_threshold_grid


@dataclass(frozen=True)
class PaperPanelResult:
    run_id: str
    run_dir: Path
    panel_path: Path
    rows: int
    clean_rows: int


@dataclass(frozen=True)
class PaperEvalResult:
    run_id: str
    run_dir: Path
    forecast_rows: int
    metric_rows: int
    status: str


@dataclass(frozen=True)
class PaperLatexResult:
    run_id: str
    latex_dir: Path
    tables: int


@dataclass(frozen=True)
class PaperLeakageCheckResult:
    run_id: str
    output_path: Path
    rows: int
    failures: int
    warnings: int


class PaperRunError(RuntimeError):
    """Raised when a paper-grade run cannot satisfy an execution gate."""


def build_paper_run_id(
    *,
    start: str,
    end: str,
    run_ts_utc: datetime,
    git_commit: str,
    stage: str = "p2a",
) -> str:
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    compact_ts = run_ts_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stage}_{clean_start}_{clean_end}_{compact_ts}_commit_{git_commit[:8]}"


def validate_worker_payload(payload: dict[str, object]) -> None:
    """Reject large frame-like objects before dispatching joblib work."""
    for key, value in payload.items():
        if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
            raise PaperRunError(f"Worker payload {key!r} must be a path/config, not a Polars frame")
        module = type(value).__module__
        name = type(value).__name__
        if module.startswith("pandas") or name in {"DataFrame", "Series"}:
            raise PaperRunError(f"Worker payload {key!r} must not be a pandas object")


def find_oos_start_date(
    rows: list[dict[str, object]],
    *,
    earliest_oos_start: str | None = None,
    min_train_rows: int | None = None,
    min_train_exceedances: int | None = None,
    tail_level: float = 0.95,
) -> str | None:
    earliest_oos_start = earliest_oos_start or DEFAULT_EARLIEST_OOS_START
    min_train_rows = min_train_rows if min_train_rows is not None else DEFAULT_MIN_TRAIN_ROWS
    min_train_exceedances = (
        min_train_exceedances
        if min_train_exceedances is not None
        else DEFAULT_MIN_TRAIN_EXCEEDANCES
    )
    clean = _clean_loss_rows(rows)
    earliest = date.fromisoformat(earliest_oos_start)
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < earliest:
            continue
        train_losses: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        if train_losses.size < min_train_rows:
            continue
        threshold = float(np.quantile(train_losses, tail_level))
        exceedances = int(np.sum(train_losses > threshold))
        if exceedances >= min_train_exceedances:
            return forecast_date.isoformat()
    return None


def validate_forecast_values(var_forecast: float, es_forecast: float) -> tuple[bool, str | None]:
    if not math.isfinite(var_forecast) or not math.isfinite(es_forecast):
        return False, "invalid_nonfinite_forecast"
    if es_forecast < var_forecast:
        return False, "invalid_es_below_var"
    return True, None


def static_empirical_es(train_losses: np.ndarray, var_forecast: float) -> float:
    exceedances = train_losses[train_losses > var_forecast]
    if exceedances.size == 0:
        return float(var_forecast)
    return float(max(var_forecast, np.mean(exceedances)))


def empirical_excess_es_companion(
    *,
    train_losses: np.ndarray,
    train_var_forecasts: np.ndarray,
    forecast_var: float,
) -> float:
    exceedance_excess = (
        train_losses[train_losses > train_var_forecasts]
        - train_var_forecasts[train_losses > train_var_forecasts]
    )
    if exceedance_excess.size == 0:
        return float(forecast_var)
    return float(max(forecast_var, forecast_var + np.mean(exceedance_excess)))


def filtered_historical_es(
    *,
    location_forecast: float,
    scale_forecast: float,
    standardized_train_losses: np.ndarray,
    standardized_var: float,
) -> float:
    exceedances = standardized_train_losses[standardized_train_losses > standardized_var]
    standardized_es = standardized_var if exceedances.size == 0 else float(np.mean(exceedances))
    var_forecast = location_forecast + scale_forecast * standardized_var
    es_forecast = location_forecast + scale_forecast * standardized_es
    return float(max(var_forecast, es_forecast))


def drop_low_variance_features(
    frame: pl.DataFrame,
    feature_columns: list[str],
    *,
    threshold: float = LOW_VARIANCE_THRESHOLD,
) -> tuple[list[str], list[str]]:
    active: list[str] = []
    dropped: list[str] = []
    for column in feature_columns:
        if column not in frame.columns:
            dropped.append(column)
            continue
        std_value = frame.select(pl.col(column).std()).item()
        if std_value is None or not math.isfinite(float(std_value)) or float(std_value) < threshold:
            dropped.append(column)
        else:
            active.append(column)
    return active, dropped


def build_feature_matrix_gate_records(
    frame: pl.DataFrame,
    feature_columns: list[str],
    *,
    threshold: float = NEAR_ZERO_VARIANCE_THRESHOLD,
) -> dict[str, object]:
    """Prefit feature gate shared by P2B/P2C model families.

    The helper records candidate, active, and dropped feature sets using only the
    supplied training frame. It deliberately avoids any test-window information.
    """
    candidate_features = list(dict.fromkeys(feature_columns))
    active_features: list[str] = []
    dropped: list[dict[str, object]] = []
    training_missingness: dict[str, float | None] = {}
    training_variance: dict[str, float | None] = {}
    numeric_columns: dict[str, list[float | None]] = {}
    row_count = frame.height
    for column in candidate_features:
        if column not in frame.columns:
            dropped.append({"feature": column, "drop_reason": "missing_column"})
            training_missingness[column] = None
            training_variance[column] = None
            continue
        raw_values = frame.get_column(column).to_list()
        finite_values = [_optional_float(value) for value in raw_values]
        valid_values = [value for value in finite_values if value is not None]
        training_missingness[column] = (
            None if row_count == 0 else 1.0 - len(valid_values) / row_count
        )
        if len(valid_values) < 2:
            reason = "all_null_or_nonfinite" if row_count else "empty_training_window"
            dropped.append({"feature": column, "drop_reason": reason})
            training_variance[column] = None
            continue
        variance = float(np.var(valid_values, ddof=1))
        training_variance[column] = variance
        numeric_columns[column] = finite_values

    if numeric_columns:
        numeric_frame = pl.DataFrame(numeric_columns)
        active_after_variance, low_variance = drop_low_variance_features(
            numeric_frame,
            list(numeric_columns),
            threshold=threshold,
        )
        active_features.extend(active_after_variance)
        for column in low_variance:
            dropped_variance = training_variance.get(column)
            dropped.append(
                {
                    "feature": column,
                    "drop_reason": "zero_or_low_variance",
                    "variance": dropped_variance,
                    "threshold": threshold,
                }
            )

    active_features = [feature for feature in candidate_features if feature in set(active_features)]
    dropped_features = [str(row["feature"]) for row in dropped]
    return {
        "candidate_features": candidate_features,
        "active_features": active_features,
        "dropped_features": dropped_features,
        "candidate_feature_hash": stable_hash(candidate_features),
        "active_feature_hash": stable_hash(active_features),
        "dropped_features_json": json.dumps(dropped, sort_keys=True, default=str),
        "training_missingness_json": json.dumps(training_missingness, sort_keys=True, default=str),
        "training_variance_json": json.dumps(training_variance, sort_keys=True, default=str),
    }


def global_oos_intersection(
    rows: list[dict[str, object]],
    *,
    model_names: tuple[str, ...],
) -> list[str]:
    by_model: dict[str, set[str]] = {model: set() for model in model_names}
    for row in rows:
        model = str(row.get("model_name"))
        if model in by_model and row.get("fit_status") == "ok":
            by_model[model].add(str(row["forecast_date"]))
    if not by_model:
        return []
    common = set.intersection(*(dates for dates in by_model.values()))
    return sorted(common)


def pairwise_oos_intersection(
    rows: list[dict[str, object]],
    *,
    left_model: str,
    right_model: str,
) -> list[str]:
    return global_oos_intersection(rows, model_names=(left_model, right_model))


def common_sample_status(dates: list[str], *, min_rows: int | None = None) -> str:
    required = (
        min_rows if min_rows is not None else PAPER_CONFIG.evaluation_policy.min_common_oos_rows
    )
    if len(dates) < required:
        return "unavailable_insufficient_common_oos"
    return "ok"


def _paper_cache_key(
    *,
    git_commit: str,
    start: str,
    end: str,
    data_vintage: Mapping[str, object] | None = None,
) -> str:
    return stable_hash(
        {
            "git_commit": git_commit,
            "config_hash": PAPER_CONFIG.config_hash(),
            "feature_set_config": PAPER_CONFIG.feature_sets,
            "target_policy": PAPER_CONFIG.target_policy,
            "leakage_policy": PAPER_CONFIG.leakage_policy,
            "evaluation_policy": PAPER_CONFIG.evaluation_policy,
            "sample_window": [start, end],
            "data_vintage_manifest": data_vintage or {},
        }
    )


def write_paper_panel(
    *,
    settings: Settings,
    start: str = MAIN_SAMPLE_START,
    end: str | None = None,
) -> PaperPanelResult:
    run_ts = datetime.now(UTC)
    end_date = end or date.today().isoformat()
    removed_tmp_files = cleanup_orphan_tmp_files(
        settings.data_dir,
        older_than_hours=CACHE_TMP_GC_HOURS,
        now=run_ts,
    )
    git_commit = _git_commit()
    run_id = build_paper_run_id(
        start=start,
        end=end_date,
        run_ts_utc=run_ts,
        git_commit=git_commit,
        stage="p2a",
    )
    run_dir = settings.reports_dir / "paper_runs" / run_id
    panel_dir = run_dir / "panel"
    config_dir = run_dir / "config"
    panel_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    calendar_records = build_session_calendar_records(
        start=(date.fromisoformat(start) - timedelta(days=10)).isoformat(),
        end=end_date,
        us_exchange=settings.calendar_us_exchange,
        jpx_exchange=settings.calendar_jpx_exchange,
        us_timezone=settings.project_timezone_us,
        jpx_timezone=settings.project_timezone_jp,
    )
    jquants_pull_ts = datetime.now(UTC)
    raw_jquants = _fetch_jquants_futures_rows(
        settings=settings,
        start=start,
        end=end_date,
        calendar_records=calendar_records,
        run_start_utc=run_ts,
    )
    schema_probe = build_jquants_schema_probe(raw_jquants)
    if schema_probe["fail_closed"] is True:
        raise PaperRunError(
            f"J-Quants schema missing required fields: {schema_probe['missing_required_fields']}"
        )
    normalized = add_jquants_silver_flags(
        normalize_jquants_futures_rows(raw_jquants, downloaded_at_utc=jquants_pull_ts)
    )
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

    predictor_start = (date.fromisoformat(start) - timedelta(days=14)).isoformat()
    massive_pull_ts = datetime.now(UTC)
    massive_daily, spy_minutes = _fetch_massive_paper_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=massive_pull_ts,
        calendar_records=calendar_records,
    )
    fred_pull_ts = datetime.now(UTC)
    fred_rows = _fetch_fred_paper_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=fred_pull_ts,
        run_start_utc=run_ts,
    )
    alignment = build_time_alignment_records(
        target_rows=targets,
        calendar_records=calendar_records,
        spy_minute_records=spy_minutes,
        vendor_lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
    )
    calendar_map = build_calendar_map_records(
        target_rows=targets,
        calendar_records=calendar_records,
        alignment_records=alignment,
    )
    panel = build_modeling_panel_records(
        target_rows=targets,
        alignment_records=alignment,
        massive_daily_records=massive_daily,
        spy_minute_records=spy_minutes,
        fred_records=fred_rows,
    )
    feature_coverage = build_feature_coverage_records(panel)
    effective_predictor_start = build_effective_predictor_start(feature_coverage)
    combined_clean_start = compute_combined_clean_start(
        jquants_required_field_coverage_start=jquants_required_start,
        massive_daily_entitlement_start=effective_predictor_start.get("massive_daily"),
        fred_required_series_coverage_start=effective_predictor_start.get("fred_core"),
    )

    target_audit_path = panel_dir / "target_audit.parquet"
    panel_path = panel_dir / "modeling_panel.parquet"
    coverage_path = panel_dir / "feature_coverage.parquet"
    fields_coverage_path = panel_dir / "fields_coverage_audit.parquet"
    calendar_map_path = panel_dir / "calendar_map.parquet"
    schema_path = panel_dir / "jquants_schema_probe.json"
    vintage_path = run_dir / "data_vintage.json"
    manifest_path = run_dir / "manifest.json"
    feature_dictionary_path = panel_dir / "feature_dictionary.json"
    research_config_path = config_dir / "research_config.json"
    config_hash = PAPER_CONFIG.config_hash()
    data_vintage_payload: dict[str, object] = {
        "jquants_pull_ts_utc": jquants_pull_ts.isoformat(),
        "massive_pull_ts_utc": massive_pull_ts.isoformat(),
        "fred_pull_ts_utc": fred_pull_ts.isoformat(),
        "window": [start, end_date],
        "predictor_window": [predictor_start, end_date],
        "claims_level": PAPER_CLAIMS_LEVEL,
        "fred_vintage_policy": PAPER_CONFIG.leakage_policy.fred_vintage_policy,
        "fred_vintage_safe": False,
        "fred_ttl_days": FRED_CACHE_TTL_DAYS,
        "fred_ttl_decision_ts_utc": run_ts.isoformat(),
    }

    _write_parquet(target_audit_path, targets)
    _write_parquet(panel_path, panel)
    _write_parquet(coverage_path, feature_coverage)
    _write_parquet(fields_coverage_path, fields_coverage)
    _write_parquet(calendar_map_path, calendar_map, schema=CALENDAR_MAP_SCHEMA)
    _write_json(schema_path, schema_probe)
    _write_json(vintage_path, data_vintage_payload)
    _write_json(feature_dictionary_path, build_feature_dictionary(panel))
    _write_json(
        research_config_path,
        {
            "config_hash": config_hash,
            "research_config": PAPER_CONFIG.to_jsonable(),
        },
    )
    _write_json(
        config_dir / "model_config.json",
        {
            "stage": "p2a",
            "config_hash": config_hash,
            "tail_levels": PAPER_TAIL_LEVELS,
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
            "cache_key": _paper_cache_key(
                git_commit=git_commit,
                start=start,
                end=end_date,
                data_vintage=data_vintage_payload,
            ),
            "claims_level": PAPER_CLAIMS_LEVEL,
            "claim_level": PAPER_CLAIMS_LEVEL,
            "stage": "p2a_panel",
            "window": [start, end_date],
            "sample_policy": "clean_predictor_entitlement_sample",
            "main_sample_start_requested": start,
            "audit_sample_start": AUDIT_SAMPLE_START,
            "main_sample_rationale": (
                "Main paper panel starts no earlier than J-Quants futures required "
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
            "massive_symbols": PAPER_CORE_MASSIVE_TICKERS,
            "fred_series": PAPER_CORE_FRED_SERIES,
            "fred_vintage_policy": PAPER_CONFIG.leakage_policy.fred_vintage_policy,
            "target_policy": {
                "primary_target_family": PAPER_CONFIG.target_policy.primary_target_family,
                "residual_usclosemark_enabled": (
                    PAPER_CONFIG.target_policy.residual_usclosemark_enabled
                ),
                "residual_usclosemark_status": (
                    PAPER_CONFIG.target_policy.residual_usclosemark_status
                ),
            },
            "leakage_policy": {
                "fred_availability_lag_us_business_days": (
                    PAPER_CONFIG.leakage_policy.fred_availability_lag_us_business_days
                ),
                "max_forward_fill_us_close_days": (
                    PAPER_CONFIG.leakage_policy.max_forward_fill_us_close_days
                ),
                "leakage_warning_min_lag_minutes": (
                    PAPER_CONFIG.leakage_policy.leakage_warning_min_lag_minutes
                ),
            },
            "evaluation_policy": {
                "primary_common_sample": PAPER_CONFIG.evaluation_policy.primary_common_sample,
                "pairwise_inference_sample": (
                    PAPER_CONFIG.evaluation_policy.pairwise_inference_sample
                ),
                "global_headline_sample": PAPER_CONFIG.evaluation_policy.global_headline_sample,
            },
            "residual_usclosemark_status": PAPER_CONFIG.target_policy.residual_usclosemark_status,
            "residual_usclosemark_enabled": PAPER_CONFIG.target_policy.residual_usclosemark_enabled,
            "artifact_paths": {
                "modeling_panel": str(panel_path),
                "target_audit": str(target_audit_path),
                "feature_coverage": str(coverage_path),
                "fields_coverage_audit": str(fields_coverage_path),
                "calendar_map": str(calendar_map_path),
                "feature_dictionary": str(feature_dictionary_path),
                "schema_probe": str(schema_path),
                "data_vintage": str(vintage_path),
                "research_config": str(research_config_path),
            },
        },
    )
    clean_rows = sum(1 for row in panel if row.get("clean_sample") is True)
    return PaperPanelResult(
        run_id=run_id,
        run_dir=run_dir,
        panel_path=panel_path,
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
) -> list[dict[str, object]]:
    alignment_by_target = {str(row["trading_date"]): row for row in alignment_records}
    massive_features = _massive_daily_feature_map(massive_daily_records)
    fred_features = _fred_feature_map(fred_records)
    spy_features = _spy_minute_feature_map(spy_minute_records)
    panel: list[dict[str, object]] = []
    for target in target_rows:
        trading_date = str(target["trading_date"])
        alignment = alignment_by_target.get(trading_date, {})
        us_date = str(alignment.get("us_calendar_date") or "")
        join_miss_reason = _panel_join_miss_reason(alignment, us_date)
        record: dict[str, object] = {
            "forecast_date": trading_date,
            "target_family": "full_gap_settle_to_open",
            "forecast_origin_name": "US_CASH_CLOSE",
            "information_set": "core_full_history",
            "contract_code": target.get("contract_code"),
            "contract_month": target.get("contract_month"),
            "clean_sample": target.get("clean_sample"),
            "same_contract_flag": target.get("same_contract_only"),
            "roll_window_flag": target.get("is_roll_sq_window"),
            "sq_window_flag": target.get("is_roll_sq_window"),
            "missing_reason": target.get("missing_reason"),
            "target_open_ts_utc": target.get("target_open_ts_utc"),
            "model_cutoff_ts_utc": alignment.get("model_cutoff_ts_utc"),
            "dst_regime": alignment.get("dst_regime"),
            "absorption_regime": alignment.get("absorption_regime"),
            "us_calendar_date": us_date or None,
            "join_miss_reason": join_miss_reason,
            "mapping_status": alignment.get("mapping_status"),
            "gap_t": target.get("full_gap_settle_to_open"),
            "realized_loss": target.get("loss_settle_to_open"),
            "full_gap_close_to_open": target.get("full_gap_close_to_open"),
            "residual_nightclose_to_day_open": target.get("residual_nightclose_to_day_open"),
            "residual_usclosemark_to_open": None,
            "residual_usclosemark_status": PAPER_CONFIG.target_policy.residual_usclosemark_status,
            "volume": target.get("volume"),
            "open_interest": target.get("open_interest"),
            "volume_oi_anomaly": target.get("volume_oi_anomaly"),
        }
        record.update(
            _features_asof(
                massive_features,
                us_date,
                fill_method="forward_fill_us_holiday",
            )
        )
        record.update(
            _features_asof(
                fred_features,
                us_date,
                fill_method="forward_fill_us_holiday",
            )
        )
        record.update(
            _features_asof(
                spy_features,
                us_date,
                fill_method="forward_fill_us_holiday",
            )
        )
        panel.append(record)
    panel.sort(key=lambda row: str(row["forecast_date"]))
    return panel


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
        "gap_t",
        "realized_loss",
        "full_gap_close_to_open",
        "residual_nightclose_to_day_open",
        "residual_usclosemark_to_open",
        "residual_usclosemark_status",
        "volume",
        "open_interest",
        "volume_oi_anomaly",
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
    grouped: dict[str, list[str]] = {"massive_daily": [], "fred_core": [], "spy_minute": []}
    for row in coverage_rows:
        first_valid = row.get("first_valid_date")
        if not isinstance(first_valid, str) or not first_valid:
            continue
        family = str(row.get("source_family") or "")
        if family in grouped:
            grouped[family].append(first_valid)
    return {family: max(values) if values else None for family, values in grouped.items()}


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
            or field.startswith("fred_")
            or field.startswith("spy_late_")
            or field.startswith("spy_final_")
        )
    }


def _feature_source_family(field: str) -> str:
    if field.startswith("fred_"):
        return "fred_core"
    if field.startswith("spy_late_") or field.startswith("spy_final_"):
        return "spy_minute"
    if field.endswith("_return") or field.endswith("_range"):
        return "massive_daily"
    return "unknown"


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


def evaluate_p2a_run(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
) -> PaperEvalResult:
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    if not panel_path.exists():
        raise PaperRunError(f"Missing modeling panel: {panel_path}")
    _assert_run_config_compatible(run_dir, force=force)
    _set_nested_thread_limits()
    forecast_root = run_dir / "forecasts"
    metrics_root = run_dir / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    jobs: list[dict[str, object]] = []
    for tail_level in PAPER_TAIL_LEVELS:
        for model_name in (
            "historical_quantile",
            "rolling_quantile",
            "ewma_vol_scaled",
            "garch_t",
            "gjr_garch_t",
            "gjr_garch_evt",
        ):
            jobs.append(
                {
                    "panel_path": str(panel_path),
                    "run_dir": str(run_dir),
                    "tail_level": tail_level,
                    "models": (model_name,),
                    "shard_id": _forecast_shard_id(model_name, tail_level),
                }
            )
    for payload in jobs:
        validate_worker_payload(payload)
    n_jobs = _bounded_workers(workers)
    if n_jobs == 1:
        outputs = [_evaluate_p2a_shard(payload) for payload in jobs]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend=PAPER_CONFIG.model_policy.joblib_backend)(
            delayed(_evaluate_p2a_shard)(payload) for payload in jobs
        )
    forecasts = [row for output in outputs for row in output["forecasts"]]
    diagnostics = [row for output in outputs for row in output["diagnostics"]]
    failures = [row for output in outputs for row in output["failures"]]
    forecast_path = forecast_root / "p2a_forecasts.parquet"
    diagnostics_path = forecast_root / "p2a_fit_diagnostics.parquet"
    failures_path = forecast_root / "p2a_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _write_parquet(diagnostics_path, diagnostics)
    _write_parquet(failures_path, failures)
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    metrics = build_metric_records(forecasts)
    _write_parquet(metrics_root / "p2a_metrics.parquet", metrics)
    _write_json(
        metrics_root / "p2a_status.json",
        {
            "claims_level": PAPER_CLAIMS_LEVEL,
            "claim_level": PAPER_CLAIMS_LEVEL,
            "config_hash": PAPER_CONFIG.config_hash(),
            "stage": "p2a",
            "forecast_rows": len(forecasts),
            "metric_rows": len(metrics),
            "failures": len(failures),
        },
    )
    _update_manifest(run_dir, {"p2a_eval_status": "completed", "p2a_forecast_rows": len(forecasts)})
    return PaperEvalResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed",
    )


def evaluate_paper_run(
    *,
    run_dir: Path,
    workers: int = 1,
    stage: str = "p2a",
    force: bool = False,
) -> PaperEvalResult:
    normalized_stage = stage.lower()
    if normalized_stage == "p2a":
        return evaluate_p2a_run(run_dir=run_dir, workers=workers, force=force)
    if normalized_stage in {"p2b", "p2c"}:
        _assert_run_config_compatible(run_dir, force=force)
        _set_nested_thread_limits()
        status = (
            "unavailable_stage_not_implemented_nonblocking"
            if normalized_stage == "p2b"
            else "unavailable_supplementary_stage_not_implemented_nonblocking"
        )
        payload = {
            "claims_level": ClaimLevel.UNAVAILABLE.value
            if normalized_stage == "p2b"
            else ClaimLevel.SUPPLEMENTARY.value,
            "claim_level": ClaimLevel.UNAVAILABLE.value
            if normalized_stage == "p2b"
            else ClaimLevel.SUPPLEMENTARY.value,
            "config_hash": PAPER_CONFIG.config_hash(),
            "stage": normalized_stage,
            "status": status,
            "forecast_rows": 0,
            "metric_rows": 0,
            "nonblocking": True,
            "registered_information_sets": {
                "model_a": PAPER_CONFIG.feature_sets.p2b_model_a_information_set,
                "model_b": PAPER_CONFIG.feature_sets.p2b_model_b_information_set,
                "model_c": PAPER_CONFIG.feature_sets.p2b_model_c_information_set,
                "japan_only_features": PAPER_CONFIG.feature_sets.japan_only_features,
            },
            "message": (
                "P2B/P2C interface is wired, but this stage requires the registered "
                "feature-matrix/model implementation before producing evidence."
            ),
        }
        _write_json(run_dir / "metrics" / f"{normalized_stage}_status.json", payload)
        _update_manifest(run_dir, {f"{normalized_stage}_eval_status": status})
        return PaperEvalResult(
            run_id=run_dir.name,
            run_dir=run_dir,
            forecast_rows=0,
            metric_rows=0,
            status=status,
        )
    raise PaperRunError(f"Unknown paper evaluation stage: {stage}")


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
    current_hash = PAPER_CONFIG.config_hash()
    locked = _run_has_locked_outputs(run_dir)
    if locked and stored_hash != current_hash:
        if not force:
            raise PaperRunError(
                "Paper run config is locked and differs from current research config; "
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


def build_metric_records(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float], list[dict[str, object]]] = {}
    for row in forecasts:
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True:
            grouped.setdefault(
                (str(row["model_name"]), _required_float(row["tail_level"])),
                [],
            ).append(row)
    records: list[dict[str, object]] = []
    for (model, tail_level), rows in sorted(grouped.items()):
        losses: Any = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var: Any = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        es: Any = np.array([_required_float(row["es_forecast"]) for row in rows], dtype=float)
        breaches = losses > var
        alpha = 1.0 - tail_level
        kupiec = kupiec_pof_test(breaches=breaches, expected_probability=alpha)
        christoffersen = christoffersen_independence_test(breaches=breaches)
        exceedance_count = int(np.sum(breaches))
        records.append(
            {
                "model_name": model,
                "tail_level": tail_level,
                "rows": len(rows),
                "var_breach_rate": float(np.mean(breaches)) if rows else None,
                "expected_breach_rate": alpha,
                "exceedance_count": exceedance_count,
                "low_exceedance_warning": (
                    exceedance_count < PAPER_CONFIG.evaluation_policy.one_percent_min_exceedances
                    if tail_level >= 0.99
                    else False
                ),
                "kupiec_lr_uc": kupiec.get("lr_stat"),
                "kupiec_pvalue": kupiec.get("pvalue"),
                "christoffersen_lr_ind": christoffersen.get("lr_stat"),
                "christoffersen_pvalue": christoffersen.get("pvalue"),
                "dq_status": "unavailable_not_implemented",
                "mcs_status": "unavailable_requires_loss_matrix",
                "mean_quantile_loss": _safe_mean(
                    np.array(
                        [
                            quantile_loss(loss, forecast, tail_level)
                            for loss, forecast in zip(losses, var, strict=True)
                        ]
                    )
                ),
                "mean_fz_loss": _safe_mean(
                    np.array(
                        [
                            fz_loss(loss, var_value, es_value, tail_level)
                            for loss, var_value, es_value in zip(
                                losses,
                                var,
                                es,
                                strict=True,
                            )
                        ]
                    )
                ),
                "mean_exceedance_severity": float(np.mean(losses[breaches] - var[breaches]))
                if np.any(breaches)
                else None,
            }
        )
    return records


def kupiec_pof_test(*, breaches: np.ndarray, expected_probability: float) -> dict[str, object]:
    n = int(breaches.size)
    x = int(np.sum(breaches))
    if n == 0 or expected_probability <= 0.0 or expected_probability >= 1.0:
        return {"status": "unavailable_invalid_input", "lr_stat": None, "pvalue": None}
    observed = x / n
    if observed in {0.0, 1.0}:
        return {
            "status": "unavailable_boundary_exceedance_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    log_likelihood_null = x * math.log(expected_probability) + (n - x) * math.log(
        1.0 - expected_probability
    )
    log_likelihood_alt = x * math.log(observed) + (n - x) * math.log(1.0 - observed)
    lr_stat = -2.0 * (log_likelihood_null - log_likelihood_alt)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
    }


def christoffersen_independence_test(*, breaches: np.ndarray) -> dict[str, object]:
    values = [bool(value) for value in breaches.tolist()]
    if len(values) < 2:
        return {"status": "unavailable_insufficient_oos", "lr_stat": None, "pvalue": None}
    n00 = n01 = n10 = n11 = 0
    for previous, current in zip(values[:-1], values[1:], strict=True):
        if not previous and not current:
            n00 += 1
        elif not previous and current:
            n01 += 1
        elif previous and not current:
            n10 += 1
        else:
            n11 += 1
    if min(n00 + n01, n10 + n11, n00 + n10, n01 + n11) == 0:
        return {
            "status": "unavailable_boundary_transition_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    if any(value in {0.0, 1.0} for value in (pi01, pi11, pi)):
        return {
            "status": "unavailable_boundary_transition_rate",
            "lr_stat": None,
            "pvalue": None,
        }
    unrestricted = (
        n00 * math.log(1.0 - pi01)
        + n01 * math.log(pi01)
        + n10 * math.log(1.0 - pi11)
        + n11 * math.log(pi11)
    )
    restricted = (n00 + n10) * math.log(1.0 - pi) + (n01 + n11) * math.log(pi)
    lr_stat = -2.0 * (restricted - unrestricted)
    return {
        "status": "ok",
        "lr_stat": float(lr_stat),
        "pvalue": float(1.0 - stats.chi2.cdf(lr_stat, 1)),
    }


def quantile_loss(loss: float, var_forecast: float, tail_level: float) -> float:
    alpha = 1.0 - tail_level
    indicator = 1.0 if loss > var_forecast else 0.0
    return float((indicator - alpha) * (loss - var_forecast))


def fz_loss(loss: float, var_forecast: float, es_forecast: float, tail_level: float) -> float:
    valid, _ = validate_forecast_values(var_forecast, es_forecast)
    if not valid or es_forecast <= 0:
        return math.nan
    alpha = 1.0 - tail_level
    x = -loss
    var_return = -var_forecast
    es_return = -es_forecast
    indicator = 1.0 if x <= var_return else 0.0
    return float(
        (1.0 / (alpha * es_return)) * indicator * (x - var_return)
        + var_return / es_return
        + math.log(-es_return)
        - 1.0
    )


def write_paper_latex_tables(*, run_dir: Path) -> PaperLatexResult:
    metrics_path = run_dir / "metrics" / "p2a_metrics.parquet"
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    tables = 0
    manifest = _read_manifest(run_dir)
    if metrics_path.exists():
        metrics = pl.read_parquet(metrics_path)
        tex = _metrics_to_latex(metrics, manifest=manifest)
        (latex_dir / "p2a_metrics_table.tex").write_text(tex, encoding="utf-8")
        tables += 1
    _write_json(
        run_dir / "latex" / "figure_manifest.json",
        {
            "claims_level": PAPER_CLAIMS_LEVEL,
            "claim_level": manifest.get("claim_level", PAPER_CLAIMS_LEVEL),
            "run_id": run_dir.name,
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "tables": tables,
            "figures": [],
        },
    )
    _update_manifest(run_dir, {"latex_tables": tables})
    return PaperLatexResult(run_id=run_dir.name, latex_dir=latex_dir, tables=tables)


def write_paper_leakage_check(*, run_dir: Path) -> PaperLeakageCheckResult:
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    if not panel_path.exists():
        raise PaperRunError(f"Missing modeling panel: {panel_path}")
    rows = build_leakage_check_records(pl.read_parquet(panel_path).to_dicts())
    output_path = run_dir / "audits" / "leakage_check.parquet"
    summary_path = run_dir / "audits" / "leakage_check_summary.json"
    _write_parquet(output_path, rows)
    failures = sum(1 for row in rows if row.get("status") == "fail")
    warnings = sum(1 for row in rows if row.get("status") == "warn")
    _write_json(
        summary_path,
        {
            "run_id": run_dir.name,
            "claims_level": PAPER_CLAIMS_LEVEL,
            "config_hash": _read_manifest(run_dir).get("config_hash"),
            "rows": len(rows),
            "failures": failures,
            "warnings": warnings,
            "status": "fail" if failures else "pass_with_warnings" if warnings else "pass",
        },
    )
    _update_manifest(
        run_dir,
        {
            "leakage_check_rows": len(rows),
            "leakage_check_failures": failures,
            "leakage_check_warnings": warnings,
        },
    )
    return PaperLeakageCheckResult(
        run_id=run_dir.name,
        output_path=output_path,
        rows=len(rows),
        failures=failures,
        warnings=warnings,
    )


def build_leakage_check_records(panel_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    warning_min_lag = PAPER_CONFIG.leakage_policy.leakage_warning_min_lag_minutes
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


def resolve_paper_run_dir(settings: Settings, run_id: str) -> Path:
    runs_dir = settings.reports_dir / "paper_runs"
    if run_id:
        run_dir = runs_dir / run_id
    else:
        candidates = [path for path in runs_dir.glob("p2a_*") if path.is_dir()]
        if not candidates:
            raise PaperRunError("No paper run found; run paper-panel first or pass run_id")
        run_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    if not run_dir.exists():
        raise PaperRunError(f"Paper run does not exist: {run_dir}")
    return run_dir


def _evaluate_p2a_shard(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
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
    oos_start = find_oos_start_date(rows, tail_level=tail_level)
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(model_name, tail_level),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                    "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                }
                for model_name in models
            ],
            "failures": [],
        }
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for model_name in models:
        model_rows, model_diag, model_failures = _forecast_model_sequence(
            rows=rows,
            model_name=model_name,
            tail_level=tail_level,
            oos_start=oos_start,
        )
        forecasts.extend(model_rows)
        diagnostics.extend(model_diag)
        failures.extend(model_failures)
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _forecast_model_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    tail_level: float,
    oos_start: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    clean = _clean_loss_rows(rows)
    start_date = date.fromisoformat(oos_start)
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        if train.size < DEFAULT_MIN_TRAIN_ROWS:
            continue
        try:
            forecast = _forecast_one(train=train, model_name=model_name, tail_level=tail_level)
            realized_loss = _required_float(row["realized_loss"])
            var_forecast = _required_float(forecast["var_forecast"])
            es_forecast = _required_float(forecast["es_forecast"])
            valid, invalid_reason = validate_forecast_values(
                var_forecast,
                es_forecast,
            )
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": "full_gap_settle_to_open",
                    "model_name": model_name,
                    "information_set": "target_history_only",
                    "tail_level": tail_level,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": forecast["es_companion_type"],
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": valid,
                    "invalid_reason": invalid_reason,
                    "train_start": clean[0]["forecast_date"],
                    "train_end": clean[index - 1]["forecast_date"],
                    "train_n": int(train.size),
                    "fit_status": "ok" if valid else "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "runtime_seconds": None,
                }
            )
            diagnostics.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "train_n": int(train.size),
                    "optimizer_status": forecast.get("optimizer_status"),
                    "convergence_code": forecast.get("convergence_code"),
                    "candidate_feature_hash": stable_hash([]),
                    "active_feature_hash": stable_hash([]),
                    "dropped_features_json": "[]",
                    "drop_reason": None,
                    "training_missingness": "{}",
                    "training_variance": "{}",
                    "threshold_quantile": forecast.get("threshold_quantile"),
                    "threshold_value": forecast.get("threshold_value"),
                    "evt_exceedance_count": forecast.get("evt_exceedance_count"),
                    "threshold_diagnostics_json": forecast.get("threshold_diagnostics_json"),
                    "threshold_policy": forecast.get("threshold_policy"),
                    "threshold_smoothing": forecast.get("threshold_smoothing"),
                    "threshold_selection": forecast.get("threshold_selection"),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised via synthetic failure tests
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_optimizer_failed",
                    "failure_reason": str(exc),
                }
            )
    return forecasts, diagnostics, failures


def _forecast_one(
    *,
    train: np.ndarray,
    model_name: str,
    tail_level: float,
) -> dict[str, object]:
    if model_name == "historical_quantile":
        var_forecast = float(np.quantile(train, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(train, var_forecast),
            "es_companion_type": "raw_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "rolling_quantile":
        window = train[-min(DEFAULT_MIN_TRAIN_ROWS, train.size) :]
        var_forecast = float(np.quantile(window, tail_level))
        return {
            "var_forecast": var_forecast,
            "es_forecast": static_empirical_es(window, var_forecast),
            "es_companion_type": "rolling_empirical_es",
            "optimizer_status": "closed_form",
            "convergence_code": 0,
        }
    if model_name == "ewma_vol_scaled":
        return _ewma_forecast(train=train, tail_level=tail_level, lambda_=EWMA_MAIN_LAMBDA)
    if model_name in {"garch_t", "gjr_garch_t", "gjr_garch_evt"}:
        return _arch_forecast(train=train, tail_level=tail_level, model_name=model_name)
    raise PaperRunError(f"Unknown P2A model: {model_name}")


def _ewma_forecast(*, train: np.ndarray, tail_level: float, lambda_: float) -> dict[str, object]:
    mean = float(np.mean(train))
    variance = float(np.var(train, ddof=1))
    for value in train:
        variance = lambda_ * variance + (1.0 - lambda_) * float((value - mean) ** 2)
    scale = math.sqrt(max(variance, 1e-12))
    z = stats.norm.ppf(tail_level)
    var_forecast = mean + scale * z
    alpha = 1.0 - tail_level
    es_forecast = mean + scale * stats.norm.pdf(z) / alpha
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_normal_es",
        "optimizer_status": "closed_form",
        "convergence_code": 0,
    }


def _arch_forecast(  # pragma: no cover - numeric optimizer exercised in real P2A runs
    *,
    train: np.ndarray,
    tail_level: float,
    model_name: str,
) -> dict[str, object]:
    try:
        from arch import arch_model
    except Exception as exc:  # pragma: no cover - dependency/environment
        raise PaperRunError(f"arch import failed: {exc}") from exc
    scaled_train = -train * 100.0
    p = 1
    o = 1 if model_name in {"gjr_garch_t", "gjr_garch_evt"} else 0
    model = arch_model(
        scaled_train,
        mean="Constant",
        vol="GARCH",
        p=p,
        o=o,
        q=1,
        dist="studentst",
        rescale=False,
    )
    result = model.fit(disp="off", show_warning=False)
    forecast = result.forecast(horizon=1, reindex=False)
    mean_return_forecast = float(forecast.mean.iloc[-1, 0]) / 100.0
    variance_forecast = float(forecast.variance.iloc[-1, 0]) / (100.0**2)
    scale_forecast = math.sqrt(max(variance_forecast, 1e-12))
    nu = float(result.params.get("nu", 8.0))
    var_forecast, es_forecast = _standardized_student_t_loss_var_es(
        mean_return_forecast=mean_return_forecast,
        scale_forecast=scale_forecast,
        nu=nu,
        tail_level=tail_level,
    )
    if model_name == "gjr_garch_evt":
        standardized_losses = _standardized_arch_losses(
            train=train,
            fitted_result=result,
        )
        evt_tail = _pot_gpd_standardized_tail(
            standardized_losses=standardized_losses,
            tail_level=tail_level,
        )
        var_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_var"]
        )
        es_forecast = -mean_return_forecast + scale_forecast * _required_float(
            evt_tail["standardized_es"]
        )
    else:
        evt_tail = {}
    return {
        "var_forecast": float(var_forecast),
        "es_forecast": float(max(es_forecast, var_forecast)),
        "es_companion_type": "analytical_student_t_es"
        if model_name != "gjr_garch_evt"
        else str(evt_tail.get("tail_method", "pot_gpd_filtered_es")),
        "optimizer_status": "converged"
        if getattr(result, "convergence_flag", 1) == 0
        else "warning",
        "convergence_code": int(getattr(result, "convergence_flag", -1)),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
        "threshold_diagnostics_json": evt_tail.get("threshold_diagnostics_json"),
        "threshold_policy": evt_tail.get("threshold_policy"),
        "threshold_smoothing": evt_tail.get("threshold_smoothing"),
        "threshold_selection": evt_tail.get("threshold_selection"),
    }


def _standardized_student_t_loss_var_es(
    *,
    mean_return_forecast: float,
    scale_forecast: float,
    nu: float,
    tail_level: float,
) -> tuple[float, float]:
    alpha = 1.0 - tail_level
    raw_quantile = float(stats.t.ppf(alpha, df=nu))
    variance_scale = math.sqrt((nu - 2.0) / nu) if nu > 2.0 else 1.0
    standardized_lower_quantile = variance_scale * raw_quantile
    var_forecast = -(mean_return_forecast + scale_forecast * standardized_lower_quantile)
    raw_pdf = float(stats.t.pdf(raw_quantile, df=nu))
    if nu > 1.0:
        standardized_upper_es = (
            variance_scale * ((nu + raw_quantile**2) / (nu - 1.0)) * raw_pdf / alpha
        )
    else:
        standardized_upper_es = -standardized_lower_quantile
    es_forecast = -mean_return_forecast + scale_forecast * standardized_upper_es
    return float(var_forecast), float(max(var_forecast, es_forecast))


def _standardized_arch_losses(train: np.ndarray, fitted_result: object) -> np.ndarray:
    std_resid = getattr(fitted_result, "std_resid", None)
    if std_resid is not None:
        values = np.asarray(std_resid, dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            return cast(np.ndarray, -values)
    fallback = (train - np.mean(train)) / max(float(np.std(train, ddof=1)), 1e-12)
    return cast(np.ndarray, fallback)


def _pot_gpd_standardized_tail(
    *,
    standardized_losses: np.ndarray,
    tail_level: float,
    threshold_quantile: float = EVT_THRESHOLD_QUANTILE,
) -> dict[str, object]:
    values = standardized_losses[np.isfinite(standardized_losses)]
    if values.size < DEFAULT_MIN_TRAIN_ROWS:
        raise PaperRunError("EVT calibration has insufficient standardized losses")
    diagnostics = _evt_threshold_diagnostics(values)
    threshold = float(np.quantile(values, threshold_quantile))
    excesses = values[values > threshold] - threshold
    if excesses.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
        raise PaperRunError(f"EVT calibration has insufficient exceedances: {excesses.size}")
    if tail_level <= threshold_quantile:
        var_z = float(np.quantile(values, tail_level))
        es_z = static_empirical_es(values, var_z)
        tail_method = "empirical_filtered_es"
    else:
        shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
        shape = float(shape)
        scale = float(max(scale, 1e-12))
        exceedance_probability = excesses.size / values.size
        target_tail_probability = max(1.0 - tail_level, 1e-12)
        ratio = max(exceedance_probability / target_tail_probability, 1.0)
        if abs(shape) < 1e-8:
            var_z = threshold + scale * math.log(ratio)
        else:
            var_z = threshold + scale * (ratio**shape - 1.0) / shape
        if shape < 1.0:
            es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
        else:
            es_z = static_empirical_es(values, var_z)
        tail_method = "pot_gpd_filtered_es"
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "threshold_diagnostics_json": json.dumps(diagnostics, sort_keys=True),
        "threshold_policy": PAPER_CONFIG.model_policy.evt_threshold_refresh,
        "threshold_smoothing": PAPER_CONFIG.model_policy.evt_threshold_smoothing,
        "threshold_selection": "pre_registered_fixed_empirical_quantile",
        "tail_method": tail_method,
    }


def _features_asof(
    features_by_date: dict[str, dict[str, object]],
    date_key: str,
    *,
    fill_method: str,
) -> dict[str, object]:
    if not date_key:
        return {}
    if date_key in features_by_date:
        return dict(features_by_date[date_key])
    try:
        target_date = date.fromisoformat(date_key)
    except ValueError:
        return {}
    prior_keys = [key for key in features_by_date if key <= date_key]
    if not prior_keys:
        return {}
    selected_key = max(prior_keys)
    try:
        selected_date = date.fromisoformat(selected_key)
    except ValueError:
        return {}
    if (
        target_date - selected_date
    ).days > PAPER_CONFIG.leakage_policy.max_forward_fill_us_close_days:
        return {}
    output = dict(features_by_date[selected_key])
    for feature_name in _feature_value_names(output):
        output[f"{feature_name}__fill_method"] = fill_method
        output[f"{feature_name}__source_date"] = selected_key
    return output


def _feature_value_names(record: Mapping[str, object]) -> list[str]:
    return sorted(
        key
        for key in record
        if "__" not in key
        and (
            key.endswith("_return")
            or key.endswith("_range")
            or key.endswith("_diff")
            or key.endswith("_level")
            or key.startswith("spy_late_")
            or key.startswith("spy_final_")
        )
    )


def _stamp_feature_metadata(
    output: dict[str, object],
    *,
    feature_name: str,
    available_ts_utc: datetime | None,
    source_date: str,
    fill_method: str = "direct",
) -> None:
    output[f"{feature_name}__available_ts_utc"] = available_ts_utc
    output[f"{feature_name}__source_date"] = source_date
    output[f"{feature_name}__fill_method"] = fill_method


def _feature_available_ts(row: Mapping[str, object], *, lag_minutes: int = 0) -> datetime | None:
    raw = row.get("vendor_available_ts_utc") or row.get("bar_end_ts_utc")
    ts = _coerce_datetime(raw)
    if ts is None:
        return None
    return ts + timedelta(minutes=lag_minutes)


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _evt_threshold_diagnostics(values: np.ndarray) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    previous_shape: float | None = None
    previous_scale: float | None = None
    for quantile in EVT_THRESHOLD_GRID:
        threshold = float(np.quantile(values, quantile))
        excesses = values[values > threshold] - threshold
        row: dict[str, object] = {
            "threshold_quantile": quantile,
            "threshold_value": threshold,
            "exceedance_count": int(excesses.size),
            "mean_excess": float(np.mean(excesses)) if excesses.size else None,
        }
        if excesses.size >= 10:
            shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
            shape = float(shape)
            scale = float(scale)
            row["shape"] = shape
            row["scale"] = scale
            row["shape_delta_from_previous"] = (
                None if previous_shape is None else shape - previous_shape
            )
            row["scale_delta_from_previous"] = (
                None if previous_scale is None else scale - previous_scale
            )
            previous_shape = shape
            previous_scale = scale
        else:
            row["shape"] = None
            row["scale"] = None
            row["shape_delta_from_previous"] = None
            row["scale_delta_from_previous"] = None
        row["selected_threshold"] = quantile == EVT_THRESHOLD_QUANTILE
        row["selection_rationale"] = (
            "primary_pre_registered_threshold"
            if quantile == EVT_THRESHOLD_QUANTILE
            else "sensitivity_grid"
        )
        diagnostics.append(row)
    return diagnostics


def _massive_daily_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_ticker.setdefault(str(row["ticker"]), []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: str(row["bar_date_et"]))
        previous_close: float | None = None
        safe = _safe_name(ticker)
        for row in rows:
            date_key = str(row["bar_date_et"])
            close = _optional_float(row.get("close"))
            high = _optional_float(row.get("high"))
            low = _optional_float(row.get("low"))
            output = features_by_date.setdefault(date_key, {})
            available_ts = _feature_available_ts(
                row,
                lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
            )
            return_name = f"{safe}_return"
            range_name = f"{safe}_range"
            if close is not None and previous_close and previous_close > 0:
                output[return_name] = math.log(close) - math.log(previous_close)
            else:
                output[return_name] = None
            if high is not None and low is not None and high > 0 and low > 0:
                output[range_name] = math.log(high) - math.log(low)
            else:
                output[range_name] = None
            _stamp_feature_metadata(
                output,
                feature_name=return_name,
                available_ts_utc=available_ts,
                source_date=date_key,
            )
            _stamp_feature_metadata(
                output,
                feature_name=range_name,
                available_ts_utc=available_ts,
                source_date=date_key,
            )
            if close is not None:
                previous_close = close
    return features_by_date


def _fred_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_series: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_series.setdefault(str(row["series_id"]), []).append(row)
    features_by_date: dict[str, dict[str, object]] = {}
    for series, rows in by_series.items():
        rows.sort(key=lambda row: str(row["observation_date"]))
        previous: float | None = None
        safe = _safe_name(series)
        for row in rows:
            date_key = str(row.get("vendor_available_date_et") or row["observation_date"])
            value = _optional_float(row.get("value"))
            output = features_by_date.setdefault(date_key, {})
            available_ts = _feature_available_ts(row)
            level_name = f"fred_{safe}_level"
            diff_name = f"fred_{safe}_diff"
            output[level_name] = value
            output[diff_name] = None if value is None or previous is None else value - previous
            _stamp_feature_metadata(
                output,
                feature_name=level_name,
                available_ts_utc=available_ts,
                source_date=str(row["observation_date"]),
            )
            _stamp_feature_metadata(
                output,
                feature_name=diff_name,
                available_ts_utc=available_ts,
                source_date=str(row["observation_date"]),
            )
            if value is not None:
                previous = value
    return features_by_date


def _spy_minute_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    if any("spy_late_30m_return" in row for row in records):
        derived_features: dict[str, dict[str, object]] = {}
        for row in records:
            date_key = str(row.get("bar_date_et") or "")
            if not date_key:
                continue
            derived_features[date_key] = {
                "spy_late_30m_return": _optional_float(row.get("spy_late_30m_return")),
                "spy_late_60m_return": _optional_float(row.get("spy_late_60m_return")),
                "spy_late_session_range": _optional_float(row.get("spy_late_session_range")),
                "spy_late_volume_surge": _optional_float(row.get("spy_late_volume_surge")),
                "spy_final_window_momentum": _optional_float(row.get("spy_final_window_momentum")),
            }
            available_ts = _coerce_datetime(row.get("feature_available_ts_utc"))
            for feature_name in _feature_value_names(derived_features[date_key]):
                _stamp_feature_metadata(
                    derived_features[date_key],
                    feature_name=feature_name,
                    available_ts_utc=available_ts,
                    source_date=date_key,
                )
        return derived_features
    by_date: dict[str, list[dict[str, object]]] = {}
    for row in records:
        if row.get("is_us_regular_session") is True:
            by_date.setdefault(str(row["bar_date_et"]), []).append(row)
    features: dict[str, dict[str, object]] = {}
    rolling_session_volume: list[float] = []
    for date_key in sorted(by_date):
        rows = sorted(by_date[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
        closes = [_optional_float(row.get("close")) for row in rows]
        highs = [_optional_float(row.get("high")) for row in rows]
        lows = [_optional_float(row.get("low")) for row in rows]
        volumes = [_optional_float(row.get("volume")) or 0.0 for row in rows]
        valid_closes = [value for value in closes if value is not None and value > 0]
        session_volume = float(sum(volumes))
        rolling_mean_volume = (
            float(np.mean(rolling_session_volume[-20:])) if rolling_session_volume else None
        )
        volume_surge = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else session_volume / rolling_mean_volume
        )
        last_available_ts = _feature_available_ts(
            rows[-1],
            lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
        )
        features[date_key] = {
            "spy_late_30m_return": _window_return(valid_closes, 30),
            "spy_late_60m_return": _window_return(valid_closes, 60),
            "spy_late_session_range": _window_range(highs[-60:], lows[-60:]),
            "spy_late_volume_surge": volume_surge,
            "spy_final_window_momentum": _window_return(valid_closes, 15),
        }
        for feature_name in _feature_value_names(features[date_key]):
            _stamp_feature_metadata(
                features[date_key],
                feature_name=feature_name,
                available_ts_utc=last_available_ts,
                source_date=date_key,
            )
        rolling_session_volume.append(session_volume)
    return features


def add_jquants_silver_flags(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flagged: list[dict[str, object]] = []
    for row in rows:
        output = dict(row)
        for source_name, flag_name in (
            ("day_session_open", "invalid_day_session_open"),
            ("day_session_close", "invalid_day_session_close"),
            ("night_session_close", "invalid_night_session_close"),
            ("settlement_price", "invalid_settlement_price"),
        ):
            value = _optional_float(row.get(source_name))
            output[flag_name] = value is None or value <= 0
        output["day_session_ohlc_violation"] = False
        output["night_session_ohlc_violation"] = False
        output["night_session_close_ts_utc"] = row.get("night_close_ts_utc")
        flagged.append(output)
    return flagged


def _write_jquants_silver_cache(*, settings: Settings, rows: list[dict[str, object]]) -> None:
    root = settings.data_dir / "silver"
    by_month: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in rows:
        trading_date = str(row.get("trading_date") or "")
        if not trading_date:
            continue
        parsed = date.fromisoformat(trading_date)
        by_month.setdefault((parsed.year, parsed.month), []).append(row)
    for (year, month), chunk_rows in sorted(by_month.items()):
        path = cache_path(
            root,
            dataset="jquants_nk225f_daily",
            schema_version=JQUANTS_SILVER_SCHEMA.version,
            year=year,
            month=month,
        )
        atomic_write_parquet(
            path,
            chunk_rows,
            schema=JQUANTS_SILVER_SCHEMA,
            metadata={
                "source": "jquants",
                "layer": "silver",
                "product_category": "NK225F",
                "year": year,
                "month": month,
            },
        )


def build_spy_late_session_feature_records(
    minute_records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]],
    vendor_lag_minutes: int,
) -> list[dict[str, object]]:
    close_by_date = {
        str(row["calendar_date"]): _coerce_datetime(row.get("us_close_ts_utc"))
        for row in calendar_records
        if row.get("us_close_ts_utc") is not None
    }
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in minute_records:
        if row.get("is_us_regular_session") is True:
            grouped.setdefault(str(row["bar_date_et"]), []).append(row)
    records: list[dict[str, object]] = []
    rolling_session_volume: list[float] = []
    for date_key in sorted(grouped):
        rows = sorted(grouped[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
        official_close = close_by_date.get(date_key) or _coerce_datetime(
            rows[-1].get("bar_end_ts_utc")
        )
        if official_close is None:
            continue
        eligible = [
            row
            for row in rows
            if (_coerce_datetime(row.get("bar_end_ts_utc")) or datetime.max.replace(tzinfo=UTC))
            <= official_close
        ]
        if not eligible:
            continue
        selected_close = eligible[-1]
        selected_close_ts = _coerce_datetime(selected_close.get("bar_end_ts_utc"))
        selected_close_value = _optional_float(selected_close.get("close"))
        hour_rows = _window_rows(eligible, official_close=official_close, minutes=60)
        half_hour_rows = _window_rows(eligible, official_close=official_close, minutes=30)
        final_rows = _window_rows(eligible, official_close=official_close, minutes=15)
        session_volume = float(sum(_optional_float(row.get("volume")) or 0.0 for row in eligible))
        rolling_mean_volume = (
            float(np.mean(rolling_session_volume[-20:])) if rolling_session_volume else None
        )
        volume_surge = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else session_volume / rolling_mean_volume
        )
        feature_available = official_close + timedelta(minutes=vendor_lag_minutes)
        records.append(
            {
                "bar_date_et": date_key,
                "bar_end_ts_utc": selected_close_ts,
                "close": selected_close_value,
                "is_us_regular_session": True,
                "spy_late_30m_return": _rows_return(half_hour_rows),
                "spy_late_60m_return": _rows_return(hour_rows),
                "spy_late_session_range": _rows_range(hour_rows),
                "spy_late_volume_surge": volume_surge,
                "spy_final_window_momentum": _rows_return(final_rows),
                "feature_available_ts_utc": feature_available,
                "official_close_ts_utc": official_close,
                "selected_close_bar_end_ts_utc": selected_close_ts,
                "vendor_lag_seconds": vendor_lag_minutes * 60,
            }
        )
        rolling_session_volume.append(session_volume)
    return records


def _window_rows(
    rows: list[dict[str, object]],
    *,
    official_close: datetime,
    minutes: int,
) -> list[dict[str, object]]:
    start = official_close - timedelta(minutes=minutes)
    return [
        row
        for row in rows
        if (ts := _coerce_datetime(row.get("bar_end_ts_utc"))) is not None
        and start <= ts <= official_close
    ]


def _rows_return(rows: list[dict[str, object]]) -> float | None:
    closes = [
        _optional_float(row.get("close"))
        for row in rows
        if _optional_float(row.get("close")) is not None
    ]
    if len(closes) < 2:
        return None
    start = closes[0]
    end = closes[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _rows_range(rows: list[dict[str, object]]) -> float | None:
    highs = [_optional_float(row.get("high")) for row in rows]
    lows = [_optional_float(row.get("low")) for row in rows]
    return _window_range(highs, lows)


def _jquants_bronze_row(
    row: Mapping[str, object],
    *,
    requested_date: str,
    source_endpoint: str,
    downloaded_at_utc: datetime,
) -> dict[str, object]:
    output: dict[str, object] = {
        "Date": _optional_text(row.get("Date")) or requested_date,
        "ProdCat": _optional_text(row.get("ProdCat")),
        "Code": _optional_text(row.get("Code")),
        "CM": _optional_text(row.get("CM")),
        "CCMFlag": _optional_text(row.get("CCMFlag")),
        "LTD": _optional_text(row.get("LTD")),
        "SQD": _optional_text(row.get("SQD")),
        "source_endpoint": source_endpoint,
        "requested_date": requested_date,
        "research_download_ts_utc": downloaded_at_utc,
    }
    for field in ("AO", "AH", "AL", "AC", "EO", "EH", "EL", "EC", "Settle", "Vo", "OI"):
        output[field] = _optional_float(row.get(field))
    return output


def _payload_results(payload: Mapping[str, object]) -> list[dict[str, Any]]:
    raw = payload.get("results", [])
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], item) for item in raw if isinstance(item, dict)]


def _read_parquet_records(path: Path) -> list[dict[str, Any]]:
    return pl.read_parquet(path).to_dicts()


def _cache_covers_dates(path: Path, required_dates: list[str]) -> bool:
    metadata = read_json(path.with_suffix(path.suffix + ".metadata.json"))
    raw_dates = metadata.get("requested_dates")
    if not isinstance(raw_dates, list):
        return False
    available = {str(value) for value in raw_dates}
    return set(required_dates).issubset(available)


def _cache_covers_range(path: Path, start: str, end: str) -> bool:
    metadata = read_json(path.with_suffix(path.suffix + ".metadata.json"))
    return _metadata_covers_range(metadata, start, end)


def _metadata_covers_range(metadata: Mapping[str, object], start: str, end: str) -> bool:
    raw_range = metadata.get("requested_range")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        return False
    cached_start, cached_end = str(raw_range[0]), str(raw_range[1])
    return cached_start <= start and cached_end >= end


def _write_unavailable_marker(
    path: Path,
    *,
    source: str,
    error_class: VendorErrorClass,
    http_status: int | None,
    requested_range: list[str],
) -> None:
    write_json_atomic(
        path,
        {
            "source": source,
            "error_class": error_class.value,
            "http_status": http_status,
            "requested_range": requested_range,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "persistent_until_force_or_entitlement_refresh": error_class
            is VendorErrorClass.UNAVAILABLE_ENTITLEMENT,
        },
    )


def _fetch_jquants_futures_rows(
    *,
    settings: Settings,
    start: str,
    end: str,
    calendar_records: list[dict[str, object]],
    run_start_utc: datetime | None = None,
) -> list[dict[str, Any]]:  # pragma: no cover - vendor path
    rows: list[dict[str, Any]] = []
    jpx_dates = [
        str(row["calendar_date"])
        for row in calendar_records
        if start <= str(row["calendar_date"]) <= end and row.get("is_jpx_trading_day") is True
    ]
    dates_by_month: dict[tuple[int, int], list[str]] = {}
    for trading_date in jpx_dates:
        parsed = date.fromisoformat(trading_date)
        dates_by_month.setdefault((parsed.year, parsed.month), []).append(trading_date)
    bronze_root = settings.data_dir / "bronze"
    with JQuantsV2Client(
        api_key=settings.jquants_api_key,
        base_url=settings.jquants_api_base_url,
        timeout_seconds=settings.jquants_request_timeout_seconds,
    ) as client:
        for (year, month), trading_dates in sorted(dates_by_month.items()):
            path = cache_path(
                bronze_root,
                dataset="jquants_futures_daily",
                schema_version=JQUANTS_BRONZE_SCHEMA.version,
                year=year,
                month=month,
            )
            if path.exists() and _cache_covers_dates(path, trading_dates):
                rows.extend(_read_parquet_records(path))
                print(f"[paper-panel] J-Quants bronze cache hit {year}-{month:02d}", flush=True)
                continue
            chunk_rows: list[dict[str, object]] = []
            pull_started = datetime.now(UTC)
            for trading_date in trading_dates:
                raw_rows = client.get_futures_daily_bars(trading_date=trading_date)
                chunk_rows.extend(
                    _jquants_bronze_row(
                        row,
                        requested_date=trading_date,
                        source_endpoint="/derivatives/bars/daily/futures",
                        downloaded_at_utc=run_start_utc or pull_started,
                    )
                    for row in raw_rows
                )
            result = atomic_write_parquet(
                path,
                chunk_rows,
                schema=JQUANTS_BRONZE_SCHEMA,
                metadata={
                    "source": "jquants",
                    "endpoint": "/derivatives/bars/daily/futures",
                    "requested_dates": trading_dates,
                    "pull_started_at_utc": pull_started.isoformat(),
                    "pull_completed_at_utc": datetime.now(UTC).isoformat(),
                },
            )
            print(
                f"[paper-panel] J-Quants bronze wrote {year}-{month:02d}: {result.rows} rows",
                flush=True,
            )
            rows.extend(_read_parquet_records(path))
    return rows


def _fetch_massive_paper_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
    calendar_records: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:  # pragma: no cover - vendor path
    daily_records: list[dict[str, object]] = []
    spy_feature_records: list[dict[str, object]] = []
    bronze_root = settings.data_dir / "bronze"
    silver_root = settings.data_dir / "silver"
    with MassiveClient(
        api_key=settings.massive_api_key,
        base_url=settings.massive_base_url,
        timeout_seconds=settings.massive_request_timeout_seconds,
    ) as client:
        for ticker in PAPER_CORE_MASSIVE_TICKERS:
            safe_ticker = _safe_name(ticker)
            for chunk_start, chunk_end in _month_chunks(start=start, end=end):
                chunk_date = date.fromisoformat(chunk_start)
                path = cache_path(
                    bronze_root,
                    dataset="massive_daily",
                    schema_version=1,
                    year=chunk_date.year,
                    month=chunk_date.month,
                    extra_partitions={"ticker": safe_ticker},
                )
                unavailable_path = path.with_suffix(".unavailable.json")
                if path.exists() and _cache_covers_range(path, chunk_start, chunk_end):
                    daily_records.extend(_read_parquet_records(path))
                    continue
                if unavailable_path.exists():
                    continue
                payload = client.fetch_aggregate_bars(
                    name=f"{ticker}_day",
                    ticker=ticker,
                    multiplier=1,
                    timespan="day",
                    start=chunk_start,
                    end=chunk_end,
                    raise_for_status=False,
                )
                error_class = classify_vendor_error(
                    status_code=payload.http_status,
                    message=str(
                        payload.payload.get("message") or payload.payload.get("error") or ""
                    ),
                    row_count=payload.row_count,
                )
                if error_class is not VendorErrorClass.OK:
                    _write_unavailable_marker(
                        unavailable_path,
                        source="massive",
                        error_class=error_class,
                        http_status=payload.http_status,
                        requested_range=[chunk_start, chunk_end],
                    )
                    continue
                normalized = normalize_aggregate_bars(
                    ticker=ticker,
                    rows=_payload_results(payload.payload),
                    multiplier=1,
                    timespan="day",
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    regular_session_start_et=settings.massive_regular_session_start_et,
                    regular_session_end_et=settings.massive_regular_session_end_et,
                )
                atomic_write_parquet(
                    path,
                    normalized,
                    metadata={
                        "source": "massive",
                        "ticker": ticker,
                        "timespan": "day",
                        "requested_range": [chunk_start, chunk_end],
                        "http_status": payload.http_status,
                    },
                )
                daily_records.extend(normalized)
        for chunk_start, chunk_end in _month_chunks(start=start, end=end):
            chunk_date = date.fromisoformat(chunk_start)
            feature_path = cache_path(
                silver_root,
                dataset="massive_spy_minute_features",
                schema_version=SPY_MINUTE_FEATURE_SCHEMA.version,
                year=chunk_date.year,
                month=chunk_date.month,
                extra_partitions={"ticker": _safe_name(settings.massive_minute_ticker)},
            )
            unavailable_path = feature_path.with_suffix(".unavailable.json")
            if feature_path.exists() and _cache_covers_range(feature_path, chunk_start, chunk_end):
                spy_feature_records.extend(_read_parquet_records(feature_path))
                continue
            if unavailable_path.exists():
                continue
            payload = client.fetch_aggregate_bars(
                name=f"{settings.massive_minute_ticker}_minute",
                ticker=settings.massive_minute_ticker,
                multiplier=1,
                timespan="minute",
                start=chunk_start,
                end=chunk_end,
                raise_for_status=False,
            )
            error_class = classify_vendor_error(
                status_code=payload.http_status,
                message=str(payload.payload.get("message") or payload.payload.get("error") or ""),
                row_count=payload.row_count,
            )
            if error_class is not VendorErrorClass.OK:
                _write_unavailable_marker(
                    unavailable_path,
                    source="massive",
                    error_class=error_class,
                    http_status=payload.http_status,
                    requested_range=[chunk_start, chunk_end],
                )
                continue
            minute_records = normalize_aggregate_bars(
                ticker=settings.massive_minute_ticker,
                rows=_payload_results(payload.payload),
                multiplier=1,
                timespan="minute",
                research_download_ts_utc=downloaded_at_utc,
                us_timezone=settings.project_timezone_us,
                regular_session_start_et=settings.massive_regular_session_start_et,
                regular_session_end_et=settings.massive_regular_session_end_et,
            )
            features = build_spy_late_session_feature_records(
                minute_records,
                calendar_records=calendar_records or [],
                vendor_lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
            )
            atomic_write_parquet(
                feature_path,
                features,
                schema=SPY_MINUTE_FEATURE_SCHEMA,
                metadata={
                    "source": "massive",
                    "ticker": settings.massive_minute_ticker,
                    "timespan": "minute_derived",
                    "requested_range": [chunk_start, chunk_end],
                    "http_status": payload.http_status,
                },
            )
            spy_feature_records.extend(features)
    return daily_records, spy_feature_records


def _fetch_fred_paper_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
    run_start_utc: datetime | None = None,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    records: list[dict[str, object]] = []
    cache_root = settings.data_dir / "bronze"
    ttl_decision_ts = run_start_utc or downloaded_at_utc
    with FredClient(
        base_url=settings.fred_base_url,
        timeout_seconds=settings.fred_request_timeout_seconds,
    ) as client:
        for series_id in PAPER_CORE_FRED_SERIES:
            path = cache_path(
                cache_root,
                dataset="fred_daily",
                schema_version=FRED_CACHE_SCHEMA.version,
                extra_partitions={"series": _safe_name(series_id)},
            )
            metadata = read_json(path.with_suffix(path.suffix + ".metadata.json"))
            if (
                path.exists()
                and is_fred_cache_fresh_at_run_start(
                    metadata,
                    run_start_utc=ttl_decision_ts,
                    ttl_days=FRED_CACHE_TTL_DAYS,
                )
                and _metadata_covers_range(metadata, start, end)
            ):
                records.extend(_read_parquet_records(path))
                continue
            payload = client.fetch_series_csv(series_id)
            normalized = [
                {**row, "vintage_safe": False}
                for row in normalize_fred_rows(
                    series_id=series_id,
                    rows=payload.rows,
                    start=start,
                    end=end,
                    research_download_ts_utc=downloaded_at_utc,
                    us_timezone=settings.project_timezone_us,
                    availability_lag_us_business_days=(
                        PAPER_CONFIG.leakage_policy.fred_availability_lag_us_business_days
                    ),
                )
            ]
            atomic_write_parquet(
                path,
                normalized,
                schema=FRED_CACHE_SCHEMA,
                metadata={
                    "source": "fred",
                    "series_id": series_id,
                    "requested_range": [start, end],
                    "pull_completed_at_utc": downloaded_at_utc.isoformat(),
                    "ttl_decision_ts_utc": ttl_decision_ts.isoformat(),
                    "ttl_days": FRED_CACHE_TTL_DAYS,
                    "ttl_status": "refreshed_at_run_start",
                    "vintage_safe": False,
                    "revision_risk_label": "current_historical_revisions",
                },
            )
            records.extend(normalized)
    return records


def _clean_loss_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    clean: list[dict[str, object]] = []
    for row in rows:
        value = _optional_float(row.get("realized_loss"))
        if value is not None and math.isfinite(value):
            clean.append({**row, "realized_loss": value})
    clean.sort(key=lambda row: str(row["forecast_date"]))
    return clean


def _bounded_workers(workers: int) -> int:
    if workers > 0:
        return workers
    cpu_count = os.cpu_count() or 2
    return max(1, min(cpu_count - 2, 6))


def _set_nested_thread_limits() -> None:
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"


def _metrics_to_latex(
    metrics: pl.DataFrame, *, manifest: Mapping[str, object] | None = None
) -> str:
    headers = ("model", "tail", "rows", "breach", "q_loss", "fz_loss")
    manifest = manifest or {}
    lines = [
        f"% run_id: {manifest.get('run_id', '')}",
        f"% git_commit: {manifest.get('git_commit', '')}",
        f"% config_hash: {manifest.get('config_hash', '')}",
        f"% claim_level: {manifest.get('claim_level', manifest.get('claims_level', ''))}",
        "% loss convention: loss_t = -gap_t; lower FZ loss is better",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        " & ".join(headers) + r" \\",
        "\\midrule",
    ]
    for row in metrics.iter_rows(named=True):
        lines.append(
            f"{row['model_name']} & {float(row['tail_level']):.3f} & "
            f"{int(row['rows'])} & {_fmt(row['var_breach_rate'])} & "
            f"{_fmt(row['mean_quantile_loss'])} & {_fmt(row['mean_fz_loss'])} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


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


def _write_forecast_shards(
    forecast_root: Path,
    forecasts: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
    failures: list[dict[str, object]],
) -> None:
    shard_root = forecast_root / "shards"
    keys = {
        (str(row["model_name"]), _required_float(row["tail_level"]))
        for row in [*forecasts, *diagnostics, *failures]
        if "model_name" in row and "tail_level" in row
    }
    for model_name, tail_level in sorted(keys):
        shard_dir = shard_root / _forecast_shard_id(model_name, tail_level)
        _write_parquet(
            shard_dir / "forecasts.parquet",
            [
                row
                for row in forecasts
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_parquet(
            shard_dir / "fit_diagnostics.parquet",
            [
                row
                for row in diagnostics
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_parquet(
            shard_dir / "failures.parquet",
            [
                row
                for row in failures
                if row.get("model_name") == model_name
                and _required_float(row["tail_level"]) == tail_level
            ],
        )
        _write_json(
            shard_dir / "status.json",
            {
                "claims_level": PAPER_CLAIMS_LEVEL,
                "claim_level": PAPER_CLAIMS_LEVEL,
                "config_hash": PAPER_CONFIG.config_hash(),
                "completion_state": "complete",
                "model_name": model_name,
                "tail_level": tail_level,
                "shard_id": _forecast_shard_id(model_name, tail_level),
            },
        )


def _forecast_shard_id(model_name: str, tail_level: float) -> str:
    return (
        f"model={_safe_name(model_name)}/target=full_gap_settle_to_open/"
        f"info=target_history_only/tail={tail_level:.3f}".replace(".", "_")
    )


def _write_parquet(
    path: Path,
    rows: list[dict[str, object]],
    *,
    schema: object | None = None,
) -> None:
    atomic_write_parquet(path, rows, schema=cast(Any, schema))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    write_json_atomic(path, payload)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _required_float(value: object) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise PaperRunError(f"Expected finite numeric value, got {value!r}")
    return parsed


def _safe_name(value: str) -> str:
    return value.replace(":", "_").replace(".", "_").replace("-", "_").replace("/", "_").lower()


def _feature_description(field: str) -> str:
    if field.endswith("_return"):
        return "close-to-close log return frozen at U.S. close information set"
    if field.endswith("_range"):
        return "log high-low range over the source bar window"
    if field.endswith("_diff"):
        return "first difference of daily source value"
    if field.endswith("_level"):
        return "daily source level with conservative research availability semantics"
    if field.startswith("spy_late_"):
        return "SPY regular-session late-window minute-bar feature"
    return "paper-grade predictor candidate"


def _window_return(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    start = closes[-window - 1]
    end = closes[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end) - math.log(start)


def _window_range(highs: list[float | None], lows: list[float | None]) -> float | None:
    valid_highs = [value for value in highs if value is not None and value > 0]
    valid_lows = [value for value in lows if value is not None and value > 0]
    if not valid_highs or not valid_lows:
        return None
    return math.log(max(valid_highs)) - math.log(min(valid_lows))


def _month_chunks(*, start: str, end: str) -> list[tuple[str, str]]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    current = start_date
    while current <= end_date:
        next_month = current.replace(day=28) + timedelta(days=4)
        month_end = min(next_month.replace(day=1) - timedelta(days=1), end_date)
        chunks.append((current.isoformat(), month_end.isoformat()))
        current = month_end + timedelta(days=1)
    return chunks


def _safe_mean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.mean(finite))


def _fmt(value: object) -> str:
    parsed = _optional_float(value)
    return "" if parsed is None else f"{parsed:.6f}"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())
