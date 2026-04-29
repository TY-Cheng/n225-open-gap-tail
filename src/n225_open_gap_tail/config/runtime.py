# ruff: noqa: F401,F811,I001
from __future__ import annotations

import importlib
import sys
import json
import math
import os
import shutil
import subprocess
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from joblib import Parallel, delayed  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]

from n225_open_gap_tail.market.calendars import build_session_calendar_records
from n225_open_gap_tail.sources.cboe import (
    CboeClient,
    build_vix_consistency_records,
    normalize_cboe_vol_index_rows,
)
from n225_open_gap_tail.config.settings import Settings
from n225_open_gap_tail.data_lake.io import (
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
    read_verified_parquet_metadata,
    write_json_atomic,
)
from n225_open_gap_tail.sources.fred import FredClient, normalize_fred_rows
from n225_open_gap_tail.sources.jquants import JQuantsV2Client
from n225_open_gap_tail.sources.massive import MassiveClient, normalize_aggregate_bars
from n225_open_gap_tail.config.research import (
    ClaimLevel,
    FeatureSetVersion,
    default_research_config,
    stable_hash,
)
from n225_open_gap_tail.data_lake.schemas import (
    ForecastExclusionReason,
    JoinMissReason,
    MappingStatus,
)
from n225_open_gap_tail.sources.jquants_futures import (
    build_jquants_schema_probe,
    normalize_jquants_futures_rows,
)

PIPELINE_CONFIG = default_research_config()
CLAIMS_LEVEL = ClaimLevel.RESEARCH_CANDIDATE.value
REMOVED_MASSIVE_FX_TICKERS = ("C:USDJPY",)
CORE_MASSIVE_TICKERS_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.massive_core
OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE = tuple(
    ticker
    for ticker in PIPELINE_CONFIG.feature_sets.massive_optional
    if ticker not in REMOVED_MASSIVE_FX_TICKERS
)
JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.massive_japan_proxy
ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.massive_asia_proxy
FETCH_MASSIVE_TICKERS_FOR_PIPELINE = tuple(
    dict.fromkeys(
        (
            *CORE_MASSIVE_TICKERS_FOR_PIPELINE,
            *OPTIONAL_MASSIVE_TICKERS_FOR_PIPELINE,
            *JAPAN_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
            *ASIA_PROXY_MASSIVE_TICKERS_FOR_PIPELINE,
        )
    )
)
CORE_FRED_SERIES_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.fred_core
FX_FRED_SERIES_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.fred_fallback
CREDIT_ENRICHED_FRED_SERIES_FOR_PIPELINE = PIPELINE_CONFIG.feature_sets.fred_credit_enriched
FETCH_FRED_SERIES_FOR_PIPELINE = tuple(
    dict.fromkeys(
        (
            *CORE_FRED_SERIES_FOR_PIPELINE,
            *FX_FRED_SERIES_FOR_PIPELINE,
            *CREDIT_ENRICHED_FRED_SERIES_FOR_PIPELINE,
        )
    )
)
TAIL_LEVELS = PIPELINE_CONFIG.model_policy.tail_levels
TAIL_SIDES = PIPELINE_CONFIG.model_policy.tail_sides
PRIMARY_TAIL_SIDE = PIPELINE_CONFIG.model_policy.primary_tail_side
TAIL_SIDE_LEFT = "left_tail"
TAIL_SIDE_RIGHT = "right_tail"
TAIL_SIDE_BOTH = "both"
EWMA_MAIN_LAMBDA = PIPELINE_CONFIG.model_policy.ewma_lambda
EWMA_SENSITIVITY_LAMBDAS = PIPELINE_CONFIG.model_policy.ewma_sensitivity_lambdas
DEFAULT_MIN_TRAIN_ROWS = PIPELINE_CONFIG.model_policy.min_train_rows
DEFAULT_MIN_TRAIN_EXCEEDANCES = PIPELINE_CONFIG.model_policy.min_train_exceedances
DEFAULT_EARLIEST_OOS_START = PIPELINE_CONFIG.model_policy.earliest_oos_start
LOW_VARIANCE_THRESHOLD = PIPELINE_CONFIG.model_policy.low_variance_threshold
NEAR_ZERO_VARIANCE_THRESHOLD = PIPELINE_CONFIG.model_policy.near_zero_variance_threshold
SHARD_SIZE_FORECAST_DATES = PIPELINE_CONFIG.model_policy.shard_size_forecast_dates
EVT_THRESHOLD_QUANTILE = PIPELINE_CONFIG.model_policy.evt_threshold_quantile
EVT_THRESHOLD_GRID = PIPELINE_CONFIG.model_policy.evt_threshold_grid
TRANSIENT_VENDOR_ERRORS = {
    VendorErrorClass.RATE_LIMITED.value,
    VendorErrorClass.VENDOR_5XX.value,
    VendorErrorClass.NETWORK_ERROR.value,
    VendorErrorClass.UNKNOWN_ERROR.value,
}
PERSISTENT_UNAVAILABLE_ERRORS = {
    VendorErrorClass.UNAVAILABLE_ENTITLEMENT.value,
    VendorErrorClass.NO_DATA.value,
}
FRED_H10_RELEASE_AGE_CAP_DAYS = (
    PIPELINE_CONFIG.leakage_policy.fred_h10_release_age_cap_calendar_days
)
ML_TAIL_DIRECT_QUANTILE_MODEL = "lightgbm_direct_quantile"
ML_TAIL_LOCATION_SCALE_MODEL = "lightgbm_location_scale"
ML_TAIL_STANDARDIZED_POT_GPD_MODEL = "lightgbm_standardized_loss_pot_gpd"
ML_TAIL_MODEL_NAMES = (
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_LOCATION_SCALE_MODEL,
    ML_TAIL_STANDARDIZED_POT_GPD_MODEL,
)
ML_TAIL_REFIT_FREQUENCY = "monthly"
ML_TAIL_SCALE_FLOOR = 1e-6
ML_TAIL_OOF_SPLITS = 5
ML_TAIL_MIN_OOF_TRAIN_ROWS = 250
RESULT_MATRIX_MIN_METRIC_ROWS = 50
RESULT_MATRIX_MIN_DM_ROWS = 120
RESULT_MATRIX_MIN_DM_EXCEPTIONS = 5
RESULT_MATRIX_MIN_MCS_ROWS = 250
RESULT_MATRIX_MIN_MCS_EXCEPTIONS = 10
RESULT_MATRIX_LOSS_FAMILIES = ("var_quantile_loss", "var_coverage", "var_es_fz_loss")
BENCHMARK_ANCHOR_MODEL = "historical_quantile"
BENCHMARK_FLOOR_MODEL_NAMES = (
    "historical_quantile",
    "rolling_quantile",
    "ewma_vol_scaled",
    "garch_t",
    "gjr_garch_t",
    "gjr_garch_evt",
)
BENCHMARK_ADVANCED_MODEL_NAMES = (
    "caviar_sav",
    "caviar_asymmetric_slope",
    "care_expectile_sav",
    "care_expectile_asymmetric_slope",
    "ald_taylor_var_es_sav",
    "ald_taylor_var_es_asymmetric_slope",
    "direct_fz_loss_sav",
    "direct_fz_loss_asymmetric_slope",
    "gas_t_location_scale",
    "gas_t_pot_gpd",
)
BENCHMARK_ADVANCED_REFIT_FREQUENCY = "monthly_parameter_refit_daily_filter"
BENCHMARK_ADVANCED_RUNTIME_BUDGET_SINGLE_THREADED = (
    PIPELINE_CONFIG.model_policy.advanced_runtime_budget_single_threaded
)
BENCHMARK_ADVANCED_PARALLELISM_UNIT = PIPELINE_CONFIG.model_policy.advanced_parallelism_unit
ADVANCED_RECURSIVE_BURN_IN_ROWS = PIPELINE_CONFIG.model_policy.advanced_recursive_burn_in_rows
ADVANCED_GAS_BURN_IN_ROWS = PIPELINE_CONFIG.model_policy.advanced_gas_burn_in_rows
ADVANCED_OPTIMIZER_MAX_RESTARTS = PIPELINE_CONFIG.model_policy.advanced_optimizer_max_restarts
ADVANCED_OPTIMIZER_JITTER_FRACTION = PIPELINE_CONFIG.model_policy.advanced_optimizer_jitter_fraction
ADVANCED_OPTIMIZER_JITTER_FLOOR = PIPELINE_CONFIG.model_policy.advanced_optimizer_jitter_floor
GAS_SCORE_SCALING = PIPELINE_CONFIG.model_policy.gas_score_scaling
GAS_STATE_VARIABLE = PIPELINE_CONFIG.model_policy.gas_state_variable
GAS_NU_GRID = PIPELINE_CONFIG.model_policy.gas_nu_grid
CARE_EXPECTILE_GRID = PIPELINE_CONFIG.model_policy.care_expectile_grid
CARE_EXPECTILE_CALIBRATION_METHOD = PIPELINE_CONFIG.model_policy.care_expectile_calibration_method
ML_TAIL_ANCHOR_INFORMATION_SET = PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set
MODEL_EVICTION_COVERAGE_THRESHOLD = 0.95
COMMON_SAMPLE_MIN_ANCHOR_COVERAGE = 0.90
BOOTSTRAP_REPS = PIPELINE_CONFIG.evaluation_policy.bootstrap_reps
INFERENCE_RANDOM_SEED = PIPELINE_CONFIG.evaluation_policy.inference_random_seed
MCS_ALPHA = PIPELINE_CONFIG.evaluation_policy.mcs_alpha
PANEL_SIGNATURE_HASH_SEED = PIPELINE_CONFIG.evaluation_policy.panel_signature_hash_seed
PANEL_SIGNATURE_COLUMNS = (
    "forecast_date",
    "target_open_ts_utc",
    "model_cutoff_ts_utc",
    "gap_t",
    "realized_loss",
    "forecast_sample",
    "forecast_sample_reason",
    "target_clean_sample",
    "join_miss_reason",
    "mapping_status",
)


def normalize_tail_side(value: object | None) -> str:
    tail_side = str(value or PRIMARY_TAIL_SIDE).strip().lower().replace("-", "_")
    if tail_side not in {*TAIL_SIDES, TAIL_SIDE_BOTH}:
        expected = ", ".join((*TAIL_SIDES, TAIL_SIDE_BOTH))
        raise PipelineRunError(f"Unknown tail_side {value!r}; expected one of {expected}")
    return tail_side


def tail_side_values(value: object | None) -> tuple[str, ...]:
    tail_side = normalize_tail_side(value)
    return TAIL_SIDES if tail_side == TAIL_SIDE_BOTH else (tail_side,)


def realized_loss_for_tail_side(row: Mapping[str, object], tail_side: str) -> float | None:
    normalized = normalize_tail_side(tail_side)
    if normalized == TAIL_SIDE_LEFT:
        gap = _optional_float(row.get("gap_t"))
        if gap is not None:
            return -gap
        existing = _optional_float(row.get("realized_loss"))
        if existing is not None:
            return existing
        return None
    if normalized == TAIL_SIDE_RIGHT:
        return _optional_float(row.get("gap_t"))
    return None


def rows_for_tail_side(rows: list[dict[str, object]], *, tail_side: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        loss = realized_loss_for_tail_side(row, tail_side)
        if loss is None:
            continue
        output.append({**row, "tail_side": normalize_tail_side(tail_side), "realized_loss": loss})
    return output


ML_TAIL_HISTORY_FEATURES = (
    "loss_lag_1",
    "loss_lag_2",
    "loss_lag_5",
    "loss_roll_mean_5",
    "loss_roll_mean_20",
    "loss_roll_std_20",
    "loss_roll_std_60",
    "loss_roll_q95_252",
    "gap_lag_1",
    "calendar_month_sin",
    "calendar_month_cos",
    "calendar_dst_edt",
    "calendar_absorption_post_us_close",
)
FRED_RATE_STALENESS_FEATURE = "fred_rates_staleness_days"
FRED_RATE_STALENESS_SERIES = ("DGS2", "DGS10", "T10Y2Y")
FRED_RATE_STALENESS_LEVEL_FEATURES = tuple(
    f"fred_{series.lower()}_level" for series in FRED_RATE_STALENESS_SERIES
)


@dataclass(frozen=True)
class PanelBuildResult:
    run_id: str
    run_dir: Path
    panel_path: Path
    rows: int
    clean_rows: int


@dataclass(frozen=True)
class EvaluationResult:
    run_id: str
    run_dir: Path
    forecast_rows: int
    metric_rows: int
    status: str


@dataclass(frozen=True)
class TableExportResult:
    run_id: str
    latex_dir: Path
    tables: int


@dataclass(frozen=True)
class LeakageCheckResult:
    run_id: str
    output_path: Path
    rows: int
    failures: int
    warnings: int


class PipelineRunError(RuntimeError):
    """Raised when a run cannot satisfy an execution gate."""


def _pipeline_log(message: str) -> None:
    print(f"[build-panel {_log_ts_utc()}] {message}", flush=True)


def _evaluation_log(message: str) -> None:
    print(f"[evaluate {_log_ts_utc()}] {message}", flush=True)


def _log_ts_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_progress_stats() -> dict[str, int]:
    return {
        "months": 0,
        "trading_days": 0,
        "cache_hits": 0,
        "fetched": 0,
        "unavailable": 0,
        "rows": 0,
    }


def _add_stat(stats: dict[str, int], key: str, amount: int = 1) -> None:
    stats[key] = stats.get(key, 0) + amount


def _log_year_stats(label: str, year: int, stats: Mapping[str, int]) -> None:
    parts = [f"chunks={stats.get('months', 0)}"]
    for key in ("trading_days", "cache_hits", "fetched", "unavailable", "rows"):
        value = stats.get(key, 0)
        if value:
            parts.append(f"{key}={value}")
    _pipeline_log(f"{label} {year}: {' '.join(parts)}")


def build_run_id(
    *,
    start: str,
    end: str,
    run_ts_utc: datetime,
    git_commit: str,
) -> str:
    clean_start = start.replace("-", "")
    clean_end = end.replace("-", "")
    compact_ts = run_ts_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"tailrisk_{clean_start}_{clean_end}_{compact_ts}_commit_{git_commit[:8]}"


def validate_worker_payload(payload: dict[str, object]) -> None:
    """Reject large frame-like objects before dispatching joblib work."""
    for key, value in payload.items():
        if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
            raise PipelineRunError(
                f"Worker payload {key!r} must be a path/config, not a Polars frame"
            )
        module = type(value).__module__
        name = type(value).__name__
        if module.startswith("pandas") or name in {"DataFrame", "Series"}:
            raise PipelineRunError(f"Worker payload {key!r} must not be a pandas object")


def cleanup_transient_unavailable_markers(root: Path) -> list[Path]:
    """Remove stale retryable vendor-error markers from prior interrupted runs."""
    removed: list[Path] = []
    if not root.exists():
        return removed
    for marker in root.rglob("*.unavailable.json"):
        payload = read_json(marker)
        error_class = str(payload.get("error_class") or "")
        if error_class not in TRANSIENT_VENDOR_ERRORS:
            continue
        marker.unlink(missing_ok=True)
        removed.append(marker)
    return removed


def find_oos_start_date(
    rows: list[dict[str, object]],
    *,
    earliest_oos_start: str | None = None,
    min_train_rows: int | None = None,
    min_train_exceedances: int | None = None,
    tail_level: float = 0.95,
) -> str | None:
    return cast(
        str | None,
        find_oos_start_diagnostics(
            rows,
            earliest_oos_start=earliest_oos_start,
            min_train_rows=min_train_rows,
            min_train_exceedances=min_train_exceedances,
            tail_level=tail_level,
        )["oos_start"],
    )


def find_oos_start_diagnostics(
    rows: list[dict[str, object]],
    *,
    earliest_oos_start: str | None = None,
    min_train_rows: int | None = None,
    min_train_exceedances: int | None = None,
    tail_level: float = 0.95,
) -> dict[str, object]:
    earliest_oos_start = earliest_oos_start or DEFAULT_EARLIEST_OOS_START
    min_train_rows = min_train_rows if min_train_rows is not None else DEFAULT_MIN_TRAIN_ROWS
    min_train_exceedances = (
        min_train_exceedances
        if min_train_exceedances is not None
        else DEFAULT_MIN_TRAIN_EXCEEDANCES
    )
    clean = _clean_loss_rows(rows)
    earliest = date.fromisoformat(earliest_oos_start)
    last_train_n = 0
    last_exceedances = 0
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < earliest:
            continue
        train_losses: Any = np.array(
            [_required_float(item["realized_loss"]) for item in clean[:index]],
            dtype=float,
        )
        last_train_n = int(train_losses.size)
        if train_losses.size < min_train_rows:
            continue
        threshold = float(np.quantile(train_losses, tail_level))
        exceedances = int(np.sum(train_losses > threshold))
        last_exceedances = exceedances
        if exceedances >= min_train_exceedances:
            return {
                "oos_start": forecast_date.isoformat(),
                "failure_reason": None,
                "train_n": last_train_n,
                "train_exceedances": last_exceedances,
                "min_train_rows": min_train_rows,
                "min_train_exceedances": min_train_exceedances,
            }
    failure_reason = (
        "train_n_below_1000" if last_train_n < min_train_rows else "train_exceedances_below_50"
    )
    return {
        "oos_start": None,
        "failure_reason": failure_reason,
        "train_n": last_train_n,
        "train_exceedances": last_exceedances,
        "min_train_rows": min_train_rows,
        "min_train_exceedances": min_train_exceedances,
    }


def validate_forecast_values(var_forecast: float, es_forecast: float) -> tuple[bool, str | None]:
    if not math.isfinite(var_forecast) or not math.isfinite(es_forecast):
        return False, "invalid_nonfinite_forecast"
    if es_forecast < var_forecast:
        return False, "invalid_es_below_var"
    return True, None


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
        raise PipelineRunError(f"Expected finite numeric value, got {value!r}")
    return parsed


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


def _clean_loss_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    clean: list[dict[str, object]] = []
    for row in rows:
        if "clean_sample" in row and row.get("clean_sample") is not True:
            continue
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
    """Prefit feature gate shared by ML tail/Advanced model families.

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
        min_rows if min_rows is not None else PIPELINE_CONFIG.evaluation_policy.min_common_oos_rows
    )
    if len(dates) < required:
        return "unavailable_insufficient_common_oos"
    return "ok"


def _run_cache_key(
    *,
    git_commit: str,
    start: str,
    end: str,
    data_vintage: Mapping[str, object] | None = None,
) -> str:
    return stable_hash(
        {
            "git_commit": git_commit,
            "config_hash": PIPELINE_CONFIG.config_hash(),
            "feature_set_config": PIPELINE_CONFIG.feature_sets,
            "target_policy": PIPELINE_CONFIG.target_policy,
            "leakage_policy": PIPELINE_CONFIG.leakage_policy,
            "evaluation_policy": PIPELINE_CONFIG.evaluation_policy,
            "sample_window": [start, end],
            "data_vintage_manifest": data_vintage or {},
        }
    )


__all__ = [name for name in globals() if not name.startswith("__")]
