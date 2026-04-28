from __future__ import annotations

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

from n225_open_gap_tail.calendars import build_session_calendar_records
from n225_open_gap_tail.cboe import (
    CboeClient,
    build_vix_consistency_records,
    normalize_cboe_vol_index_rows,
)
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
from n225_open_gap_tail.schemas import ForecastExclusionReason, JoinMissReason, MappingStatus
from n225_open_gap_tail.snapshot import (
    build_jquants_schema_probe,
    build_target_audit_records,
    build_time_alignment_records,
    normalize_jquants_futures_rows,
)

PAPER_CONFIG = default_paper_research_config()
PAPER_CLAIMS_LEVEL = ClaimLevel.PAPER_CANDIDATE.value
PAPER_REMOVED_MASSIVE_FX_TICKERS = ("C:USDJPY",)
PAPER_CORE_MASSIVE_TICKERS = PAPER_CONFIG.feature_sets.massive_core
PAPER_OPTIONAL_MASSIVE_TICKERS = tuple(
    ticker
    for ticker in PAPER_CONFIG.feature_sets.massive_optional
    if ticker not in PAPER_REMOVED_MASSIVE_FX_TICKERS
)
PAPER_JAPAN_PROXY_MASSIVE_TICKERS = PAPER_CONFIG.feature_sets.massive_japan_proxy
PAPER_ASIA_PROXY_MASSIVE_TICKERS = PAPER_CONFIG.feature_sets.massive_asia_proxy
PAPER_FETCH_MASSIVE_TICKERS = tuple(
    dict.fromkeys(
        (
            *PAPER_CORE_MASSIVE_TICKERS,
            *PAPER_OPTIONAL_MASSIVE_TICKERS,
            *PAPER_JAPAN_PROXY_MASSIVE_TICKERS,
            *PAPER_ASIA_PROXY_MASSIVE_TICKERS,
        )
    )
)
PAPER_CORE_FRED_SERIES = PAPER_CONFIG.feature_sets.fred_core
PAPER_FX_FRED_SERIES = PAPER_CONFIG.feature_sets.fred_fallback
PAPER_CREDIT_ENRICHED_FRED_SERIES = PAPER_CONFIG.feature_sets.fred_credit_enriched
PAPER_FETCH_FRED_SERIES = tuple(
    dict.fromkeys(
        (
            *PAPER_CORE_FRED_SERIES,
            *PAPER_FX_FRED_SERIES,
            *PAPER_CREDIT_ENRICHED_FRED_SERIES,
        )
    )
)
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
FRED_H10_RELEASE_AGE_CAP_DAYS = PAPER_CONFIG.leakage_policy.fred_h10_release_age_cap_calendar_days
P2B_DIRECT_QUANTILE_MODEL = "lightgbm_direct_quantile"
P2B_LOCATION_SCALE_MODEL = "lightgbm_location_scale"
P2B_STANDARDIZED_POT_GPD_MODEL = "lightgbm_standardized_loss_pot_gpd"
P2B_MODEL_NAMES = (
    P2B_DIRECT_QUANTILE_MODEL,
    P2B_LOCATION_SCALE_MODEL,
    P2B_STANDARDIZED_POT_GPD_MODEL,
)
P2B_REFIT_FREQUENCY = "monthly"
P2B_SCALE_FLOOR = 1e-6
P2B_OOF_SPLITS = 5
P2B_MIN_OOF_TRAIN_ROWS = 250
P2A_ANCHOR_MODEL = "historical_quantile"
P2B_ANCHOR_INFORMATION_SET = PAPER_CONFIG.feature_sets.p2b_model_a_information_set
MODEL_EVICTION_COVERAGE_THRESHOLD = 0.95
COMMON_SAMPLE_MIN_ANCHOR_COVERAGE = 0.90
BOOTSTRAP_REPS = PAPER_CONFIG.evaluation_policy.bootstrap_reps
INFERENCE_RANDOM_SEED = PAPER_CONFIG.evaluation_policy.inference_random_seed
MCS_ALPHA = PAPER_CONFIG.evaluation_policy.mcs_alpha
PANEL_SIGNATURE_HASH_SEED = PAPER_CONFIG.evaluation_policy.panel_signature_hash_seed
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
P2B_HISTORY_FEATURES = (
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


def _paper_log(message: str) -> None:
    print(f"[paper-panel {_log_ts_utc()}] {message}", flush=True)


def _paper_eval_log(message: str) -> None:
    print(f"[paper-eval {_log_ts_utc()}] {message}", flush=True)


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
    _paper_log(f"{label} {year}: {' '.join(parts)}")


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
    _paper_log(f"start window={start}..{end_date}")
    removed_tmp_files = cleanup_orphan_tmp_files(
        settings.data_dir,
        older_than_hours=CACHE_TMP_GC_HOURS,
        now=run_ts,
    )
    _paper_log(f"tmp gc removed {len(removed_tmp_files)} orphan temp files")
    removed_transient_markers = cleanup_transient_unavailable_markers(settings.data_dir)
    _paper_log(f"transient unavailable marker gc removed {len(removed_transient_markers)} files")
    git_commit = _git_commit()
    run_id = build_paper_run_id(
        start=start,
        end=end_date,
        run_ts_utc=run_ts,
        git_commit=git_commit,
        stage="p2a",
    )
    _paper_log(f"run id {run_id}")
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
    _paper_log(f"calendar records built: {len(calendar_records)}")
    jquants_pull_ts = datetime.now(UTC)
    _paper_log("J-Quants bronze fetch/cache start")
    raw_jquants = _fetch_jquants_futures_rows(
        settings=settings,
        start=start,
        end=end_date,
        calendar_records=calendar_records,
        run_start_utc=run_ts,
    )
    _paper_log(f"J-Quants bronze rows available: {len(raw_jquants)}")
    schema_probe = build_jquants_schema_probe(raw_jquants)
    if schema_probe["fail_closed"] is True:
        raise PaperRunError(
            f"J-Quants schema missing required fields: {schema_probe['missing_required_fields']}"
        )
    normalized = add_jquants_silver_flags(
        normalize_jquants_futures_rows(raw_jquants, downloaded_at_utc=jquants_pull_ts)
    )
    _paper_log(f"J-Quants normalized NK225F rows: {len(normalized)}")
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
    _paper_log(f"target audit rows built: {len(targets)} rows, clean={clean_targets}")

    predictor_start = (date.fromisoformat(start) - timedelta(days=14)).isoformat()
    massive_pull_ts = datetime.now(UTC)
    _paper_log(f"Massive predictors fetch/cache start window={predictor_start}..{end_date}")
    massive_daily, spy_minutes = _fetch_massive_paper_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=massive_pull_ts,
        calendar_records=calendar_records,
    )
    _paper_log(
        f"Massive predictors available: daily_rows={len(massive_daily)}, "
        f"spy_minute_feature_rows={len(spy_minutes)}"
    )
    fred_pull_ts = datetime.now(UTC)
    _paper_log(f"FRED predictors fetch/cache start window={predictor_start}..{end_date}")
    fred_rows = _fetch_fred_paper_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=fred_pull_ts,
        run_start_utc=run_ts,
    )
    _paper_log(f"FRED predictor rows available: {len(fred_rows)}")
    cboe_pull_ts = datetime.now(UTC)
    _paper_log(f"Cboe volatility predictors fetch/cache start window={predictor_start}..{end_date}")
    cboe_rows = _fetch_cboe_paper_predictors(
        settings=settings,
        start=predictor_start,
        end=end_date,
        downloaded_at_utc=cboe_pull_ts,
    )
    vix_consistency = build_vix_consistency_records(
        cboe_records=cboe_rows,
        fred_records=fred_rows,
    )
    _paper_log(
        f"Cboe volatility rows available: {len(cboe_rows)}, "
        f"VIX consistency warnings={len(vix_consistency)}"
    )
    alignment = build_time_alignment_records(
        target_rows=targets,
        calendar_records=calendar_records,
        spy_minute_records=spy_minutes,
        vendor_lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
    )
    _paper_log(f"time alignment rows built: {len(alignment)}")
    calendar_map = build_calendar_map_records(
        target_rows=targets,
        calendar_records=calendar_records,
        alignment_records=alignment,
    )
    _paper_log(f"calendar map rows built: {len(calendar_map)}")
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
    _paper_log(f"modeling panel rows built: {len(panel)}")
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
    _paper_log(f"combined clean start: {combined_clean_start}")
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
    research_config_path = config_dir / "research_config.json"
    config_hash = PAPER_CONFIG.config_hash()
    data_vintage_payload: dict[str, object] = {
        "jquants_pull_ts_utc": jquants_pull_ts.isoformat(),
        "massive_pull_ts_utc": massive_pull_ts.isoformat(),
        "fred_pull_ts_utc": fred_pull_ts.isoformat(),
        "cboe_pull_ts_utc": cboe_pull_ts.isoformat(),
        "window": [start, end_date],
        "predictor_window": [predictor_start, end_date],
        "claims_level": PAPER_CLAIMS_LEVEL,
        "fred_vintage_policy": PAPER_CONFIG.leakage_policy.fred_vintage_policy,
        "fred_vintage_safe": False,
        "fred_ttl_days": FRED_CACHE_TTL_DAYS,
        "fred_ttl_decision_ts_utc": run_ts.isoformat(),
    }

    _write_parquet(target_audit_path, targets)
    _paper_log(f"wrote target audit: {target_audit_path}")
    _write_parquet(panel_path, panel)
    _paper_log(f"wrote modeling panel: {panel_path}")
    _write_parquet(coverage_path, feature_coverage)
    _paper_log(f"wrote feature coverage: {coverage_path}")
    _write_parquet(fields_coverage_path, fields_coverage)
    _paper_log(f"wrote fields coverage audit: {fields_coverage_path}")
    _write_parquet(calendar_map_path, calendar_map, schema=CALENDAR_MAP_SCHEMA)
    _paper_log(f"wrote calendar map: {calendar_map_path}")
    _write_parquet(vix_consistency_path, vix_consistency)
    _paper_log(f"wrote VIX consistency audit: {vix_consistency_path}")
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
            "massive_core_symbols": PAPER_CORE_MASSIVE_TICKERS,
            "massive_optional_symbols": PAPER_OPTIONAL_MASSIVE_TICKERS,
            "massive_japan_proxy_symbols": PAPER_JAPAN_PROXY_MASSIVE_TICKERS,
            "massive_asia_proxy_symbols": PAPER_ASIA_PROXY_MASSIVE_TICKERS,
            "massive_fetched_symbols": PAPER_FETCH_MASSIVE_TICKERS,
            "massive_symbols": PAPER_FETCH_MASSIVE_TICKERS,
            "fred_core_series": PAPER_CORE_FRED_SERIES,
            "fred_fx_fallback_series": PAPER_FX_FRED_SERIES,
            "fred_credit_enriched_series": PAPER_CREDIT_ENRICHED_FRED_SERIES,
            "fred_series": PAPER_FETCH_FRED_SERIES,
            "fred_vintage_policy": PAPER_CONFIG.leakage_policy.fred_vintage_policy,
            "fx_policy": {
                "canonical_features": ["fx_usdjpy_level", "fx_usdjpy_return"],
                "source_precedence": ["fred_h10_latest_released", "null_unavailable"],
                "h10_release_age_cap_calendar_days": FRED_H10_RELEASE_AGE_CAP_DAYS,
            },
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
                "vix_consistency_audit": str(vix_consistency_path),
                "feature_dictionary": str(feature_dictionary_path),
                "schema_probe": str(schema_path),
                "data_vintage": str(vintage_path),
                "research_config": str(research_config_path),
            },
        },
    )
    clean_rows = sum(1 for row in panel if row.get("clean_sample") is True)
    _paper_log(f"panel complete rows={len(panel)} clean_rows={clean_rows}")
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
            "residual_usclosemark_status": PAPER_CONFIG.target_policy.residual_usclosemark_status,
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


def registered_p2b_information_sets() -> tuple[str, ...]:
    return (
        PAPER_CONFIG.feature_sets.p2b_model_a_information_set,
        PAPER_CONFIG.feature_sets.p2b_model_b_information_set,
        PAPER_CONFIG.feature_sets.p2b_model_c_information_set,
        PAPER_CONFIG.feature_sets.p2b_model_d_information_set,
    )


def p2b_feature_columns_for_information_set(
    coverage_rows: list[dict[str, object]],
    *,
    information_set: str,
) -> list[str]:
    """Return the pre-registered P2B candidate features for an information set."""
    blocks: set[str] = set()
    if information_set == PAPER_CONFIG.feature_sets.p2b_model_a_information_set:
        blocks = set()
    elif information_set == PAPER_CONFIG.feature_sets.p2b_model_b_information_set:
        blocks = {"us_core", "us_late_session", "fred_core", "fx_core"}
    elif information_set == PAPER_CONFIG.feature_sets.p2b_model_c_information_set:
        blocks = {"us_core", "us_late_session", "fred_core", "fx_core", "japan_proxy"}
    elif information_set == PAPER_CONFIG.feature_sets.p2b_model_d_information_set:
        blocks = {
            "us_core",
            "us_late_session",
            "fred_core",
            "fx_core",
            "japan_proxy",
            "asia_proxy",
        }
    else:
        raise PaperRunError(f"Unknown P2B information set: {information_set}")
    block_features = [
        str(row["feature"])
        for row in coverage_rows
        if str(row.get("source_block") or "") in blocks and row.get("feature")
    ]
    return list(dict.fromkeys((*P2B_HISTORY_FEATURES, *sorted(block_features))))


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
    if _feature_matches_tickers(field, PAPER_OPTIONAL_MASSIVE_TICKERS):
        return "massive_optional"
    if _feature_matches_tickers(field, PAPER_JAPAN_PROXY_MASSIVE_TICKERS):
        return "japan_proxy"
    if _feature_matches_tickers(field, PAPER_ASIA_PROXY_MASSIVE_TICKERS):
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
        # as FRED VIX in the registered P2B information-set ladder.
        return "fred_core"
    if field.startswith("spy_late_") or field.startswith("spy_final_"):
        return "us_late_session"
    if _feature_matches_tickers(field, PAPER_OPTIONAL_MASSIVE_TICKERS):
        return "massive_optional"
    if _feature_matches_tickers(field, PAPER_JAPAN_PROXY_MASSIVE_TICKERS):
        return "japan_proxy"
    if _feature_matches_tickers(field, PAPER_ASIA_PROXY_MASSIVE_TICKERS):
        return "asia_proxy"
    if _feature_matches_tickers(field, PAPER_CORE_MASSIVE_TICKERS):
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
    _assert_leakage_gate(run_dir)
    _set_nested_thread_limits()
    _paper_eval_log(f"start run_id={run_dir.name} workers={workers}")
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
    _paper_eval_log(f"P2A shards queued={len(jobs)} n_jobs={n_jobs}")
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
    _paper_eval_log(f"wrote forecasts: {forecast_path} rows={len(forecasts)}")
    _write_parquet(diagnostics_path, diagnostics)
    _paper_eval_log(f"wrote diagnostics: {diagnostics_path} rows={len(diagnostics)}")
    _write_parquet(failures_path, failures)
    _paper_eval_log(f"wrote failures: {failures_path} rows={len(failures)}")
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    _paper_eval_log("wrote forecast shards")
    artifacts = build_common_sample_artifacts(
        forecasts,
        stage="p2a",
        anchor_model=P2A_ANCHOR_MODEL,
        anchor_information_set="target_history_only",
    )
    metrics = cast(list[dict[str, object]], artifacts["headline_metrics"])
    _write_parquet(metrics_root / "p2a_metrics.parquet", metrics)
    _write_parquet(
        metrics_root / "p2a_metrics_per_model.parquet",
        cast(list[dict[str, object]], artifacts["per_model_metrics"]),
    )
    _write_parquet(
        metrics_root / "p2a_model_eviction.parquet",
        cast(list[dict[str, object]], artifacts["model_eviction"]),
    )
    _write_parquet(
        metrics_root / "p2a_loss_matrix.parquet",
        cast(list[dict[str, object]], artifacts["loss_matrix"]),
    )
    _write_parquet(
        metrics_root / "p2a_dm_inference.parquet",
        cast(list[dict[str, object]], artifacts["dm_inference"]),
    )
    _write_parquet(
        metrics_root / "p2a_mcs.parquet",
        cast(list[dict[str, object]], artifacts["mcs"]),
    )
    _write_parquet(
        metrics_root / "p2a_murphy.parquet",
        cast(list[dict[str, object]], artifacts["murphy"]),
    )
    _write_parquet(
        metrics_root / "p2a_stress_windows.parquet",
        cast(list[dict[str, object]], artifacts["stress_windows"]),
    )
    _paper_eval_log(f"wrote headline metrics rows={len(metrics)}")
    _write_json(
        metrics_root / "p2a_status.json",
        {
            "claims_level": PAPER_CLAIMS_LEVEL,
            "claim_level": PAPER_CLAIMS_LEVEL,
            "config_hash": PAPER_CONFIG.config_hash(),
            "stage": "p2a",
            "forecast_rows": len(forecasts),
            "metric_rows": len(metrics),
            "per_model_metric_rows": len(
                cast(list[dict[str, object]], artifacts["per_model_metrics"])
            ),
            "loss_matrix_rows": len(cast(list[dict[str, object]], artifacts["loss_matrix"])),
            "common_sample_status": artifacts["common_sample_status"],
            "failures": len(failures),
        },
    )
    _update_manifest(run_dir, {"p2a_eval_status": "completed", "p2a_forecast_rows": len(forecasts)})
    _paper_eval_log(
        f"complete run_id={run_dir.name} forecast_rows={len(forecasts)} "
        f"metric_rows={len(metrics)} failures={len(failures)}"
    )
    return PaperEvalResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed",
    )


def evaluate_p2b_run(
    *,
    run_dir: Path,
    workers: int = 1,
    force: bool = False,
) -> PaperEvalResult:
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    coverage_path = run_dir / "panel" / "feature_coverage.parquet"
    if not panel_path.exists():
        raise PaperRunError(f"Missing modeling panel: {panel_path}")
    if not coverage_path.exists():
        raise PaperRunError(f"Missing feature coverage: {coverage_path}")
    _assert_run_config_compatible(run_dir, force=force)
    _assert_leakage_gate(run_dir)
    _set_nested_thread_limits()
    _paper_eval_log(f"start P2B run_id={run_dir.name} workers={workers}")
    forecast_root = run_dir / "forecasts"
    metrics_root = run_dir / "metrics"
    forecast_root.mkdir(parents=True, exist_ok=True)
    metrics_root.mkdir(parents=True, exist_ok=True)
    information_sets = registered_p2b_information_sets()
    jobs: list[dict[str, object]] = []
    for tail_level in PAPER_TAIL_LEVELS:
        for model_name in P2B_MODEL_NAMES:
            for information_set in information_sets:
                jobs.append(
                    {
                        "panel_path": str(panel_path),
                        "coverage_path": str(coverage_path),
                        "run_dir": str(run_dir),
                        "tail_level": tail_level,
                        "target_family": PAPER_CONFIG.target_policy.primary_target_family,
                        "information_set": information_set,
                        "model_name": model_name,
                        "refit_frequency": P2B_REFIT_FREQUENCY,
                        "shard_id": _forecast_shard_id(
                            model_name,
                            tail_level,
                            information_set=information_set,
                            target_family=PAPER_CONFIG.target_policy.primary_target_family,
                            refit_frequency=P2B_REFIT_FREQUENCY,
                        ),
                    }
                )
    for payload in jobs:
        validate_worker_payload(payload)
    n_jobs = _bounded_workers(workers)
    _paper_eval_log(f"P2B shards queued={len(jobs)} n_jobs={n_jobs}")
    if n_jobs == 1:
        outputs = [_evaluate_p2b_shard(payload) for payload in jobs]
    else:
        outputs = Parallel(n_jobs=n_jobs, backend=PAPER_CONFIG.model_policy.joblib_backend)(
            delayed(_evaluate_p2b_shard)(payload) for payload in jobs
        )
    forecasts = [row for output in outputs for row in output["forecasts"]]
    diagnostics = [row for output in outputs for row in output["diagnostics"]]
    failures = [row for output in outputs for row in output["failures"]]
    forecast_path = forecast_root / "p2b_forecasts.parquet"
    diagnostics_path = forecast_root / "p2b_fit_diagnostics.parquet"
    failures_path = forecast_root / "p2b_failures.parquet"
    _write_parquet(forecast_path, forecasts)
    _paper_eval_log(f"wrote P2B forecasts: {forecast_path} rows={len(forecasts)}")
    _write_parquet(diagnostics_path, diagnostics)
    _paper_eval_log(f"wrote P2B diagnostics: {diagnostics_path} rows={len(diagnostics)}")
    _write_parquet(failures_path, failures)
    _paper_eval_log(f"wrote P2B failures: {failures_path} rows={len(failures)}")
    _write_forecast_shards(forecast_root, forecasts, diagnostics, failures)
    artifacts = build_common_sample_artifacts(
        forecasts,
        stage="p2b",
        anchor_model=P2B_DIRECT_QUANTILE_MODEL,
        anchor_information_set=P2B_ANCHOR_INFORMATION_SET,
    )
    headline_forecasts = cast(list[dict[str, object]], artifacts["headline_forecasts"])
    metrics = cast(list[dict[str, object]], artifacts["headline_metrics"])
    incremental = build_incremental_information_records(
        headline_forecasts,
        baseline_information_set=PAPER_CONFIG.feature_sets.p2b_model_a_information_set,
    )
    dst_attenuation = build_dst_attenuation_records(
        headline_forecasts,
        baseline_information_set=PAPER_CONFIG.feature_sets.p2b_model_a_information_set,
        expanded_information_set=PAPER_CONFIG.feature_sets.p2b_model_b_information_set,
    )
    feature_unavailability = build_p2b_feature_unavailability_records(forecasts)
    feature_unavailability_dates = build_p2b_feature_unavailability_date_records(forecasts)
    _write_parquet(metrics_root / "p2b_metrics.parquet", metrics)
    _write_parquet(
        metrics_root / "p2b_metrics_per_model.parquet",
        cast(list[dict[str, object]], artifacts["per_model_metrics"]),
    )
    _write_parquet(
        metrics_root / "p2b_model_eviction.parquet",
        cast(list[dict[str, object]], artifacts["model_eviction"]),
    )
    _write_parquet(
        metrics_root / "p2b_loss_matrix.parquet",
        cast(list[dict[str, object]], artifacts["loss_matrix"]),
    )
    _write_parquet(
        metrics_root / "p2b_dm_inference.parquet",
        cast(list[dict[str, object]], artifacts["dm_inference"]),
    )
    _write_parquet(
        metrics_root / "p2b_mcs.parquet",
        cast(list[dict[str, object]], artifacts["mcs"]),
    )
    _write_parquet(
        metrics_root / "p2b_murphy.parquet",
        cast(list[dict[str, object]], artifacts["murphy"]),
    )
    _write_parquet(
        metrics_root / "p2b_stress_windows.parquet",
        cast(list[dict[str, object]], artifacts["stress_windows"]),
    )
    _write_parquet(metrics_root / "p2b_incremental_information.parquet", incremental)
    _write_parquet(metrics_root / "p2b_dst_attenuation.parquet", dst_attenuation)
    _write_parquet(
        metrics_root / "p2b_feature_unavailability.parquet",
        feature_unavailability,
    )
    _write_parquet(
        metrics_root / "p2b_feature_unavailability_dates.parquet",
        feature_unavailability_dates,
    )
    _write_json(
        metrics_root / "p2b_status.json",
        {
            "claims_level": PAPER_CLAIMS_LEVEL,
            "claim_level": PAPER_CLAIMS_LEVEL,
            "config_hash": PAPER_CONFIG.config_hash(),
            "stage": "p2b",
            "status": "completed_lightgbm_p2b_models",
            "model_name": "p2b_lightgbm_model_registry",
            "refit_frequency": P2B_REFIT_FREQUENCY,
            "forecast_rows": len(forecasts),
            "metric_rows": len(metrics),
            "per_model_metric_rows": len(
                cast(list[dict[str, object]], artifacts["per_model_metrics"])
            ),
            "loss_matrix_rows": len(cast(list[dict[str, object]], artifacts["loss_matrix"])),
            "feature_unavailability_rows": len(feature_unavailability),
            "feature_unavailability_date_rows": len(feature_unavailability_dates),
            "common_sample_status": artifacts["common_sample_status"],
            "failures": len(failures),
            "registered_information_sets": _registered_information_set_payload(),
            "implemented_components": list(P2B_MODEL_NAMES),
            "unavailable_components": {},
        },
    )
    _update_manifest(
        run_dir,
        {
            "p2b_eval_status": "completed_lightgbm_p2b_models",
            "p2b_forecast_rows": len(forecasts),
            "p2b_metric_rows": len(metrics),
        },
    )
    _paper_eval_log(
        f"complete P2B run_id={run_dir.name} forecast_rows={len(forecasts)} "
        f"metric_rows={len(metrics)} failures={len(failures)}"
    )
    return PaperEvalResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        forecast_rows=len(forecasts),
        metric_rows=len(metrics),
        status="completed_lightgbm_p2b_models",
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
    if normalized_stage == "p2b":
        return evaluate_p2b_run(run_dir=run_dir, workers=workers, force=force)
    if normalized_stage == "p2c":
        _assert_run_config_compatible(run_dir, force=force)
        _set_nested_thread_limits()
        status = "unavailable_supplementary_stage_not_implemented_nonblocking"
        payload = {
            "claims_level": ClaimLevel.SUPPLEMENTARY.value,
            "claim_level": ClaimLevel.SUPPLEMENTARY.value,
            "config_hash": PAPER_CONFIG.config_hash(),
            "stage": normalized_stage,
            "status": status,
            "forecast_rows": 0,
            "metric_rows": 0,
            "nonblocking": True,
            "registered_information_sets": _registered_information_set_payload(),
            "message": (
                "P2C interface is wired, but advanced econometric and formal inference "
                "models remain unavailable until their registered implementations complete."
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


def _registered_information_set_payload() -> dict[str, object]:
    return {
        "model_a": PAPER_CONFIG.feature_sets.p2b_model_a_information_set,
        "model_b": PAPER_CONFIG.feature_sets.p2b_model_b_information_set,
        "model_c": PAPER_CONFIG.feature_sets.p2b_model_c_information_set,
        "model_d": PAPER_CONFIG.feature_sets.p2b_model_d_information_set,
        "japan_only_features": PAPER_CONFIG.feature_sets.japan_only_features,
    }


def _assert_leakage_gate(run_dir: Path) -> None:
    summary_path = run_dir / "audits" / "leakage_check_summary.json"
    if not summary_path.exists():
        raise PaperRunError(
            "Paper evaluation requires a leakage check artifact; "
            "run `just _paper-leakage-check` first."
        )
    summary = read_json(summary_path)
    failures = int(cast(int | float | str, summary.get("failures") or 0))
    if failures:
        raise PaperRunError(f"Paper evaluation blocked by leakage check failures: {failures}")
    expected = _current_leakage_binding(run_dir)
    keys = (
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
    mismatches = [key for key in keys if summary.get(key) != expected.get(key)]
    if mismatches:
        raise PaperRunError(
            "Paper evaluation blocked by stale leakage check artifact; "
            f"mismatched fields: {', '.join(mismatches)}"
        )


def _evaluate_p2b_shard(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    validate_worker_payload(payload)
    panel_path = Path(str(payload["panel_path"]))
    coverage_path = Path(str(payload["coverage_path"]))
    tail_level = _required_float(payload["tail_level"])
    target_family = str(
        payload.get("target_family") or PAPER_CONFIG.target_policy.primary_target_family
    )
    information_set = str(payload["information_set"])
    model_name = str(payload["model_name"])
    refit_frequency = str(payload.get("refit_frequency") or P2B_REFIT_FREQUENCY)
    coverage_rows = pl.read_parquet(coverage_path).to_dicts()
    candidate_features = p2b_feature_columns_for_information_set(
        coverage_rows,
        information_set=information_set,
    )
    panel_rows = pl.read_parquet(panel_path).to_dicts()
    rows = build_p2b_modeling_rows(panel_rows, candidate_features)
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(
                        model_name,
                        tail_level,
                        target_family=target_family,
                        information_set=information_set,
                        refit_frequency=refit_frequency,
                    ),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "oos_failure_reason": oos_diagnostics["failure_reason"],
                    "train_n": oos_diagnostics["train_n"],
                    "train_exceedances": oos_diagnostics["train_exceedances"],
                    "min_train_rows": DEFAULT_MIN_TRAIN_ROWS,
                    "min_train_exceedances": DEFAULT_MIN_TRAIN_EXCEEDANCES,
                    "target_family": target_family,
                    "refit_frequency": refit_frequency,
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
            ],
            "failures": [],
        }
    return _forecast_p2b_lightgbm_sequence(
        rows=rows,
        model_name=model_name,
        information_set=information_set,
        candidate_features=candidate_features,
        tail_level=tail_level,
        oos_start=oos_start,
    )


def build_p2b_modeling_rows(
    panel_rows: list[dict[str, object]],
    candidate_features: list[str],
) -> list[dict[str, object]]:
    rows = sorted(panel_rows, key=lambda row: str(row.get("forecast_date") or ""))
    losses: list[float] = []
    gaps: list[float] = []
    output: list[dict[str, object]] = []
    for row in rows:
        forecast_date = str(row.get("forecast_date") or "")
        if not forecast_date:
            continue
        try:
            parsed_date = date.fromisoformat(forecast_date)
        except ValueError:
            continue
        loss = _optional_float(row.get("realized_loss"))
        gap = _optional_float(row.get("gap_t"))
        record: dict[str, object] = {
            "forecast_date": forecast_date,
            "target_family": row.get("target_family") or "full_gap_settle_to_open",
            "clean_sample": row.get("clean_sample"),
            "realized_loss": loss,
            "gap_t": gap,
            "dst_regime": row.get("dst_regime"),
            "absorption_regime": row.get("absorption_regime"),
            "vix_level": _optional_float(row.get("fred_vixcls_level"))
            if _optional_float(row.get("fred_vixcls_level")) is not None
            else _optional_float(row.get("cboe_vix_close")),
        }
        record.update(_history_feature_values(losses=losses, gaps=gaps, forecast_date=parsed_date))
        record["calendar_dst_edt"] = 1.0 if row.get("dst_regime") == "EDT" else 0.0
        record["calendar_absorption_post_us_close"] = (
            1.0 if row.get("absorption_regime") == "post_us_close_night_absorption" else 0.0
        )
        for feature in candidate_features:
            if feature in record:
                continue
            record[feature] = _optional_float(row.get(feature))
        output.append(record)
        if row.get("clean_sample") is True and loss is not None and math.isfinite(loss):
            losses.append(loss)
            if gap is not None and math.isfinite(gap):
                gaps.append(gap)
    return output


def _history_feature_values(
    *,
    losses: list[float],
    gaps: list[float],
    forecast_date: date,
) -> dict[str, object]:
    month_angle = 2.0 * math.pi * (forecast_date.month - 1) / 12.0
    values: dict[str, object] = {
        "loss_lag_1": losses[-1] if len(losses) >= 1 else None,
        "loss_lag_2": losses[-2] if len(losses) >= 2 else None,
        "loss_lag_5": losses[-5] if len(losses) >= 5 else None,
        "gap_lag_1": gaps[-1] if len(gaps) >= 1 else None,
        "calendar_month_sin": math.sin(month_angle),
        "calendar_month_cos": math.cos(month_angle),
    }
    for window in (5, 20):
        slice_ = losses[-window:]
        values[f"loss_roll_mean_{window}"] = float(np.mean(slice_)) if slice_ else None
    for window in (20, 60):
        slice_ = losses[-window:]
        values[f"loss_roll_std_{window}"] = (
            float(np.std(slice_, ddof=1)) if len(slice_) >= 2 else None
        )
    tail_window = losses[-252:]
    values["loss_roll_q95_252"] = float(np.quantile(tail_window, 0.95)) if tail_window else None
    return values


def _forecast_p2b_lightgbm_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    information_set: str,
    candidate_features: list[str],
    tail_level: float,
    oos_start: str,
) -> dict[str, list[dict[str, object]]]:
    try:
        import lightgbm as lgb
    except Exception as exc:  # pragma: no cover - dependency/environment
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_import_error",
                    "failure_reason": str(exc),
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
            ],
            "failures": [],
        }
    if model_name != P2B_DIRECT_QUANTILE_MODEL:
        return _forecast_p2b_location_scale_sequence(
            rows=rows,
            model_name=model_name,
            information_set=information_set,
            candidate_features=candidate_features,
            tail_level=tail_level,
            oos_start=oos_start,
            lgb=lgb,
        )
    clean = [
        row
        for row in rows
        if row.get("clean_sample") is True
        and (loss := _optional_float(row.get("realized_loss"))) is not None
        and math.isfinite(loss)
    ]
    clean.sort(key=lambda row: str(row["forecast_date"]))
    start_date = date.fromisoformat(oos_start)
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    cached_model: Any | None = None
    cached_refit_month: str | None = None
    cached_active_features: list[str] = []
    cached_gate: dict[str, object] = {}
    cached_train_n = 0
    cached_train_start: object = None
    cached_train_end: object = None
    cached_excess_mean = 0.0
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train_rows = clean[:index]
        if len(train_rows) < DEFAULT_MIN_TRAIN_ROWS:
            continue
        refit_month = forecast_date.strftime("%Y-%m")
        if cached_model is None or cached_refit_month != refit_month:
            try:
                train_frame = pl.DataFrame(train_rows, infer_schema_length=None)
                gate = build_feature_matrix_gate_records(train_frame, candidate_features)
                active_features = cast(list[str], gate["active_features"])
                if not active_features:
                    raise PaperRunError("P2B LightGBM has no active features after training gate")
                x_train = _feature_matrix(train_frame, active_features)
                y_train: Any = np.array(
                    [_required_float(item["realized_loss"]) for item in train_rows],
                    dtype=float,
                )
                model = lgb.LGBMRegressor(
                    objective="quantile",
                    alpha=tail_level,
                    n_estimators=80,
                    learning_rate=0.05,
                    num_leaves=15,
                    min_child_samples=20,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    random_state=int(tail_level * 10_000) + len(information_set),
                    num_threads=1,
                    verbosity=-1,
                )
                model.fit(x_train, y_train)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="X does not have valid feature names",
                        category=UserWarning,
                    )
                    train_var: Any = np.asarray(model.predict(x_train), dtype=float)
                exceedance_excess = y_train[y_train > train_var] - train_var[y_train > train_var]
                cached_excess_mean = (
                    float(np.mean(exceedance_excess)) if exceedance_excess.size else 0.0
                )
                cached_model = model
                cached_refit_month = refit_month
                cached_active_features = active_features
                cached_gate = gate
                cached_train_n = int(y_train.size)
                cached_train_start = train_rows[0]["forecast_date"]
                cached_train_end = train_rows[-1]["forecast_date"]
                diagnostics.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_level": tail_level,
                        "train_n": cached_train_n,
                        "optimizer_status": "lightgbm_fit_completed",
                        "convergence_code": 0,
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "candidate_feature_hash": gate["candidate_feature_hash"],
                        "active_feature_hash": gate["active_feature_hash"],
                        "dropped_features_json": gate["dropped_features_json"],
                        "drop_reason": None,
                        "training_missingness": gate["training_missingness_json"],
                        "training_variance": gate["training_variance_json"],
                        "refit_frequency": P2B_REFIT_FREQUENCY,
                        "refit_month": refit_month,
                    }
                )
            except Exception as exc:  # pragma: no cover - synthetic tests cover status path
                failures.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_level": tail_level,
                        "fit_status": "unavailable_optimizer_failed",
                        "failure_reason": str(exc),
                    }
                )
                cached_model = None
                cached_refit_month = None
                continue
        if cached_model is None:
            continue
        try:
            unavailable_features = _unavailable_active_features(row, cached_active_features)
            if unavailable_features:
                realized_loss = _required_float(row["realized_loss"])
                forecasts.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_level": tail_level,
                        "refit_frequency": P2B_REFIT_FREQUENCY,
                        "var_forecast": None,
                        "es_forecast": None,
                        "es_companion_type": "empirical_excess_es_companion",
                        "realized_loss": realized_loss,
                        "var_breach": None,
                        "is_valid_forecast": False,
                        "invalid_reason": "unavailable_feature_not_valid_at_cutoff",
                        "train_start": cached_train_start,
                        "train_end": cached_train_end,
                        "train_n": cached_train_n,
                        "fit_status": "unavailable_feature_not_valid_at_cutoff",
                        "failure_reason": ",".join(unavailable_features),
                        "runtime_seconds": None,
                        "dst_regime": row.get("dst_regime"),
                        "absorption_regime": row.get("absorption_regime"),
                        "vix_level": row.get("vix_level"),
                        "active_feature_hash": cached_gate.get("active_feature_hash"),
                        **_p2b_extended_forecast_fields(),
                    }
                )
                continue
            predict_frame = pl.DataFrame([row], infer_schema_length=None)
            x_predict = _feature_matrix(predict_frame, cached_active_features)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="X does not have valid feature names",
                    category=UserWarning,
                )
                var_forecast = float(np.asarray(cached_model.predict(x_predict), dtype=float)[0])
            es_forecast = float(max(var_forecast, var_forecast + cached_excess_mean))
            realized_loss = _required_float(row["realized_loss"])
            valid, invalid_reason = validate_forecast_values(var_forecast, es_forecast)
            forecasts.append(
                {
                    "forecast_date": row["forecast_date"],
                    "target_family": row.get("target_family") or "full_gap_settle_to_open",
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "refit_frequency": P2B_REFIT_FREQUENCY,
                    "var_forecast": var_forecast,
                    "es_forecast": es_forecast,
                    "es_companion_type": "empirical_excess_es_companion",
                    "realized_loss": realized_loss,
                    "var_breach": realized_loss > var_forecast,
                    "is_valid_forecast": valid,
                    "invalid_reason": invalid_reason,
                    "train_start": cached_train_start,
                    "train_end": cached_train_end,
                    "train_n": cached_train_n,
                    "fit_status": "ok" if valid else "invalid_forecast",
                    "failure_reason": invalid_reason,
                    "runtime_seconds": None,
                    "dst_regime": row.get("dst_regime"),
                    "absorption_regime": row.get("absorption_regime"),
                    "vix_level": row.get("vix_level"),
                    "active_feature_hash": cached_gate.get("active_feature_hash"),
                    **_p2b_extended_forecast_fields(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive failure log
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "fit_status": "unavailable_prediction_failed",
                    "failure_reason": str(exc),
                }
            )
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _forecast_p2b_location_scale_sequence(
    *,
    rows: list[dict[str, object]],
    model_name: str,
    information_set: str,
    candidate_features: list[str],
    tail_level: float,
    oos_start: str,
    lgb: Any,
) -> dict[str, list[dict[str, object]]]:
    clean = [
        row
        for row in rows
        if row.get("clean_sample") is True
        and (loss := _optional_float(row.get("realized_loss"))) is not None
        and math.isfinite(loss)
    ]
    clean.sort(key=lambda row: str(row["forecast_date"]))
    start_date = date.fromisoformat(oos_start)
    forecasts: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    cached_bundle: dict[str, object] | None = None
    cached_refit_month: str | None = None
    for index, row in enumerate(clean):
        forecast_date = date.fromisoformat(str(row["forecast_date"]))
        if forecast_date < start_date:
            continue
        train_rows = clean[:index]
        if len(train_rows) < DEFAULT_MIN_TRAIN_ROWS:
            continue
        refit_month = forecast_date.strftime("%Y-%m")
        if cached_bundle is None or cached_refit_month != refit_month:
            cached_refit_month = refit_month
            try:
                cached_bundle = _fit_p2b_location_scale_bundle(
                    train_rows=train_rows,
                    candidate_features=candidate_features,
                    model_name=model_name,
                    information_set=information_set,
                    tail_level=tail_level,
                    lgb=lgb,
                )
                diagnostics.append(
                    _p2b_location_scale_diagnostic(
                        row=row,
                        model_name=model_name,
                        information_set=information_set,
                        tail_level=tail_level,
                        refit_month=refit_month,
                        bundle=cached_bundle,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive path covered by statuses
                status = _p2b_unavailable_status(exc)
                cached_bundle = {
                    "fit_status": status,
                    "failure_reason": str(exc),
                    "refit_month": refit_month,
                    "train_n": len(train_rows),
                    "train_start": train_rows[0]["forecast_date"],
                    "train_end": train_rows[-1]["forecast_date"],
                    "candidate_feature_hash": stable_hash(candidate_features),
                    "active_feature_hash": stable_hash([]),
                }
                diagnostics.append(
                    {
                        "forecast_date": row["forecast_date"],
                        "target_family": row.get("target_family") or "full_gap_settle_to_open",
                        "model_name": model_name,
                        "information_set": information_set,
                        "tail_level": tail_level,
                        "fit_status": status,
                        "failure_reason": str(exc),
                        "train_n": len(train_rows),
                        "train_start": train_rows[0]["forecast_date"],
                        "train_end": train_rows[-1]["forecast_date"],
                        "candidate_feature_hash": stable_hash(candidate_features),
                        "active_feature_hash": stable_hash([]),
                        "refit_frequency": P2B_REFIT_FREQUENCY,
                        "refit_month": refit_month,
                    }
                )
        if cached_bundle is None or cached_bundle.get("fit_status") != "ok":
            continue
        try:
            active_features = cast(list[str], cached_bundle["active_features"])
            scale_active_features = cast(list[str], cached_bundle["scale_active_features"])
            unavailable_features = _unavailable_active_features(
                row,
                list(dict.fromkeys((*active_features, *scale_active_features))),
            )
            if unavailable_features:
                forecasts.append(
                    _p2b_unavailable_feature_forecast(
                        row=row,
                        model_name=model_name,
                        information_set=information_set,
                        tail_level=tail_level,
                        bundle=cached_bundle,
                        unavailable_features=unavailable_features,
                    )
                )
                continue
            forecast = _predict_p2b_location_scale_forecast(
                row=row,
                model_name=model_name,
                information_set=information_set,
                tail_level=tail_level,
                bundle=cached_bundle,
            )
            forecasts.append(forecast)
        except Exception as exc:  # pragma: no cover - defensive failure log
            failures.append(
                {
                    "forecast_date": row["forecast_date"],
                    "model_name": model_name,
                    "information_set": information_set,
                    "tail_level": tail_level,
                    "fit_status": _p2b_unavailable_status(exc),
                    "failure_reason": str(exc),
                }
            )
    return {"forecasts": forecasts, "diagnostics": diagnostics, "failures": failures}


def _fit_p2b_location_scale_bundle(
    *,
    train_rows: list[dict[str, object]],
    candidate_features: list[str],
    model_name: str,
    information_set: str,
    tail_level: float,
    lgb: Any,
) -> dict[str, object]:
    oof = _p2b_oof_location_scale(
        train_rows=train_rows,
        candidate_features=candidate_features,
        information_set=information_set,
        tail_level=tail_level,
        lgb=lgb,
    )
    z_oof = cast(np.ndarray, oof["standardized_losses"])
    z_oof = z_oof[np.isfinite(z_oof)]
    if z_oof.size < P2B_MIN_OOF_TRAIN_ROWS:
        raise PaperRunError(f"unavailable_oof_standardization_insufficient_sample: {z_oof.size}")
    standardized_var: float | None = None
    standardized_es: float | None = None
    evt_tail: dict[str, object] = {}
    if model_name == P2B_LOCATION_SCALE_MODEL:
        standardized_var = float(np.quantile(z_oof, tail_level))
        exceedances = z_oof[z_oof > standardized_var]
        if exceedances.size < DEFAULT_MIN_TRAIN_EXCEEDANCES:
            raise PaperRunError(
                f"unavailable_oof_standardized_es_insufficient_exceedances: {exceedances.size}"
            )
        standardized_es = float(max(standardized_var, np.mean(exceedances)))
        es_companion_type = "oof_filtered_historical_standardized_es"
    elif model_name == P2B_STANDARDIZED_POT_GPD_MODEL:
        if tail_level <= EVT_THRESHOLD_QUANTILE:
            raise PaperRunError("unavailable_evt_tail_not_above_threshold")
        try:
            evt_tail = _pot_gpd_standardized_tail(
                standardized_losses=z_oof,
                tail_level=tail_level,
                require_finite_gpd_es=True,
            )
        except PaperRunError as exc:
            message = str(exc)
            if "insufficient exceedances" in message:
                raise PaperRunError(f"unavailable_evt_insufficient_exceedances: {message}") from exc
            if "shape" in message:
                raise PaperRunError(f"unavailable_evt_shape_es_infinite: {message}") from exc
            raise PaperRunError(f"unavailable_evt_calibration_failed: {message}") from exc
        standardized_var = _required_float(evt_tail["standardized_var"])
        standardized_es = _required_float(evt_tail["standardized_es"])
        es_companion_type = "oof_standardized_loss_pot_gpd"
    else:
        raise PaperRunError(f"Unknown P2B model: {model_name}")

    y_train = np.array([_required_float(row["realized_loss"]) for row in train_rows], dtype=float)
    location_model, gate, active_features = _fit_lgb_regression_model(
        lgb=lgb,
        rows=train_rows,
        target=y_train,
        candidate_features=candidate_features,
        objective="regression_l2",
        random_state=_p2b_seed(model_name, information_set, tail_level, "location_final"),
    )
    log_abs_resid_oof = cast(np.ndarray, oof["log_abs_resid_oof"])
    scale_indices = [index for index, value in enumerate(log_abs_resid_oof) if math.isfinite(value)]
    if len(scale_indices) < P2B_MIN_OOF_TRAIN_ROWS:
        raise PaperRunError(
            f"unavailable_oof_standardization_insufficient_sample: {len(scale_indices)}"
        )
    scale_rows = [train_rows[index] for index in scale_indices]
    scale_target = np.array([log_abs_resid_oof[index] for index in scale_indices], dtype=float)
    scale_model, scale_gate, scale_active_features = _fit_lgb_regression_model(
        lgb=lgb,
        rows=scale_rows,
        target=scale_target,
        candidate_features=candidate_features,
        objective="regression_l2",
        random_state=_p2b_seed(model_name, information_set, tail_level, "scale_final"),
    )
    return {
        "fit_status": "ok",
        "location_model": location_model,
        "scale_model": scale_model,
        "active_features": active_features,
        "scale_active_features": scale_active_features,
        "gate": gate,
        "scale_gate": scale_gate,
        "train_n": len(train_rows),
        "train_start": train_rows[0]["forecast_date"],
        "train_end": train_rows[-1]["forecast_date"],
        "smearing_factor": oof["smearing_factor"],
        "scale_floor": P2B_SCALE_FLOOR,
        "standardized_losses": z_oof,
        "standardized_var": standardized_var,
        "standardized_es": standardized_es,
        "es_companion_type": es_companion_type,
        "oof_standardized_loss_count": int(z_oof.size),
        "oof_location_count": oof["location_oof_count"],
        "oof_scale_count": oof["scale_oof_count"],
        "standardization_method": "blocked_expanding_oof_location_scale_duan_smearing",
        "evt_tail": evt_tail,
        "candidate_feature_hash": gate["candidate_feature_hash"],
        "active_feature_hash": stable_hash(
            {
                "location": active_features,
                "scale": scale_active_features,
            }
        ),
        "dropped_features_json": gate["dropped_features_json"],
        "scale_dropped_features_json": scale_gate["dropped_features_json"],
        "training_missingness_json": gate["training_missingness_json"],
        "training_variance_json": gate["training_variance_json"],
    }


def _p2b_oof_location_scale(
    *,
    train_rows: list[dict[str, object]],
    candidate_features: list[str],
    information_set: str,
    tail_level: float,
    lgb: Any,
) -> dict[str, object]:
    row_count = len(train_rows)
    folds = _blocked_expanding_oof_folds(
        row_count,
        n_splits=P2B_OOF_SPLITS,
        min_train_rows=P2B_MIN_OOF_TRAIN_ROWS,
    )
    if not folds:
        raise PaperRunError("unavailable_oof_standardization_insufficient_sample: no folds")
    y = np.array([_required_float(row["realized_loss"]) for row in train_rows], dtype=float)
    mu_oof = np.full(row_count, np.nan, dtype=float)
    log_abs_resid_oof = np.full(row_count, np.nan, dtype=float)
    log_sigma_oof = np.full(row_count, np.nan, dtype=float)
    for fold_index, (fold_train, fold_validation) in enumerate(folds):
        fold_rows = [train_rows[index] for index in fold_train]
        fold_target = y[fold_train]
        model, _, active_features = _fit_lgb_regression_model(
            lgb=lgb,
            rows=fold_rows,
            target=fold_target,
            candidate_features=candidate_features,
            objective="regression_l2",
            random_state=_p2b_seed(information_set, tail_level, "location_oof", fold_index),
        )
        validation_rows = [train_rows[index] for index in fold_validation]
        mu_oof[fold_validation] = _predict_lgb_rows(model, validation_rows, active_features)
    for index, value in enumerate(mu_oof):
        if math.isfinite(value):
            log_abs_resid_oof[index] = math.log(max(abs(y[index] - value), P2B_SCALE_FLOOR))
    for fold_index, (fold_train, fold_validation) in enumerate(folds):
        scale_train = [index for index in fold_train if math.isfinite(log_abs_resid_oof[index])]
        scale_validation = [
            index for index in fold_validation if math.isfinite(log_abs_resid_oof[index])
        ]
        if len(scale_train) < P2B_MIN_OOF_TRAIN_ROWS or not scale_validation:
            continue
        scale_rows = [train_rows[index] for index in scale_train]
        scale_target = log_abs_resid_oof[scale_train]
        model, _, active_features = _fit_lgb_regression_model(
            lgb=lgb,
            rows=scale_rows,
            target=scale_target,
            candidate_features=candidate_features,
            objective="regression_l2",
            random_state=_p2b_seed(information_set, tail_level, "scale_oof", fold_index),
        )
        validation_rows = [train_rows[index] for index in scale_validation]
        log_sigma_oof[scale_validation] = _predict_lgb_rows(
            model,
            validation_rows,
            active_features,
        )
    valid_smearing = np.isfinite(log_abs_resid_oof) & np.isfinite(log_sigma_oof)
    if int(np.sum(valid_smearing)) < P2B_MIN_OOF_TRAIN_ROWS:
        raise PaperRunError(
            f"unavailable_oof_standardization_insufficient_sample: {int(np.sum(valid_smearing))}"
        )
    exp_resid = np.exp(log_abs_resid_oof[valid_smearing] - log_sigma_oof[valid_smearing])
    exp_resid = exp_resid[np.isfinite(exp_resid)]
    smearing_factor = float(np.mean(exp_resid)) if exp_resid.size else math.nan
    if not math.isfinite(smearing_factor) or smearing_factor <= 0:
        raise PaperRunError("unavailable_invalid_smearing_factor")
    sigma_oof = np.exp(log_sigma_oof) * smearing_factor
    valid_z = (
        np.isfinite(mu_oof)
        & np.isfinite(sigma_oof)
        & (sigma_oof > 0)
        & np.isfinite(log_abs_resid_oof)
    )
    standardized = (y[valid_z] - mu_oof[valid_z]) / sigma_oof[valid_z]
    standardized = standardized[np.isfinite(standardized)]
    if standardized.size < P2B_MIN_OOF_TRAIN_ROWS:
        raise PaperRunError(
            f"unavailable_oof_standardization_insufficient_sample: {standardized.size}"
        )
    return {
        "mu_oof": mu_oof,
        "log_abs_resid_oof": log_abs_resid_oof,
        "log_sigma_oof": log_sigma_oof,
        "smearing_factor": smearing_factor,
        "standardized_losses": standardized,
        "location_oof_count": int(np.sum(np.isfinite(mu_oof))),
        "scale_oof_count": int(np.sum(np.isfinite(log_sigma_oof))),
    }


def _fit_lgb_regression_model(
    *,
    lgb: Any,
    rows: list[dict[str, object]],
    target: np.ndarray,
    candidate_features: list[str],
    objective: str,
    random_state: int,
) -> tuple[Any, dict[str, object], list[str]]:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    gate = build_feature_matrix_gate_records(frame, candidate_features)
    active_features = cast(list[str], gate["active_features"])
    if not active_features:
        raise PaperRunError("P2B LightGBM has no active features after training gate")
    x_train = _feature_matrix(frame, active_features)
    model = lgb.LGBMRegressor(
        objective=objective,
        n_estimators=80,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=random_state,
        num_threads=1,
        verbosity=-1,
    )
    model.fit(x_train, target)
    return model, gate, active_features


def _predict_lgb_rows(
    model: Any, rows: list[dict[str, object]], active_features: list[str]
) -> np.ndarray:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    x_predict = _feature_matrix(frame, active_features)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names",
            category=UserWarning,
        )
        return np.asarray(model.predict(x_predict), dtype=float)


def _blocked_expanding_oof_folds(
    row_count: int,
    *,
    n_splits: int,
    min_train_rows: int,
) -> list[tuple[list[int], list[int]]]:
    if row_count <= min_train_rows:
        return []
    validation_count = row_count - min_train_rows
    block_size = max(1, math.ceil(validation_count / max(n_splits, 1)))
    folds: list[tuple[list[int], list[int]]] = []
    start = min_train_rows
    while start < row_count:
        end = min(row_count, start + block_size)
        folds.append((list(range(start)), list(range(start, end))))
        start = end
    return folds


def _predict_p2b_location_scale_forecast(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    bundle: Mapping[str, object],
) -> dict[str, object]:
    location_model = bundle["location_model"]
    scale_model = bundle["scale_model"]
    location_forecast = float(
        _predict_lgb_rows(
            location_model,
            [dict(row)],
            cast(list[str], bundle["active_features"]),
        )[0]
    )
    log_scale_forecast = float(
        _predict_lgb_rows(
            scale_model,
            [dict(row)],
            cast(list[str], bundle["scale_active_features"]),
        )[0]
    )
    smearing_factor = _required_float(bundle["smearing_factor"])
    try:
        scale_forecast = math.exp(log_scale_forecast) * smearing_factor
    except OverflowError as exc:
        raise PaperRunError("unavailable_invalid_scale_forecast") from exc
    if not math.isfinite(scale_forecast) or scale_forecast <= 0:
        raise PaperRunError("unavailable_invalid_scale_forecast")
    standardized_var = _required_float(bundle["standardized_var"])
    standardized_es = _required_float(bundle["standardized_es"])
    var_forecast = float(location_forecast + scale_forecast * standardized_var)
    es_forecast = float(location_forecast + scale_forecast * standardized_es)
    es_forecast = float(max(var_forecast, es_forecast))
    realized_loss = _required_float(row["realized_loss"])
    valid, invalid_reason = validate_forecast_values(var_forecast, es_forecast)
    evt_tail = cast(Mapping[str, object], bundle.get("evt_tail") or {})
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "refit_frequency": P2B_REFIT_FREQUENCY,
        "var_forecast": var_forecast,
        "es_forecast": es_forecast,
        "es_companion_type": bundle["es_companion_type"],
        "realized_loss": realized_loss,
        "var_breach": realized_loss > var_forecast,
        "is_valid_forecast": valid,
        "invalid_reason": invalid_reason,
        "train_start": bundle["train_start"],
        "train_end": bundle["train_end"],
        "train_n": bundle["train_n"],
        "fit_status": "ok" if valid else "invalid_forecast",
        "failure_reason": invalid_reason,
        "runtime_seconds": None,
        "dst_regime": row.get("dst_regime"),
        "absorption_regime": row.get("absorption_regime"),
        "vix_level": row.get("vix_level"),
        "active_feature_hash": bundle.get("active_feature_hash"),
        "location_forecast": location_forecast,
        "scale_forecast": scale_forecast,
        "scale_smearing_factor": smearing_factor,
        "scale_floor": P2B_SCALE_FLOOR,
        "standardization_method": bundle.get("standardization_method"),
        "oof_standardized_loss_count": bundle.get("oof_standardized_loss_count"),
        "standardized_var": standardized_var,
        "standardized_es": standardized_es,
        "evt_shape": evt_tail.get("evt_shape"),
        "evt_scale": evt_tail.get("evt_scale"),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
    }


def _p2b_location_scale_diagnostic(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    refit_month: str,
    bundle: Mapping[str, object],
) -> dict[str, object]:
    evt_tail = cast(Mapping[str, object], bundle.get("evt_tail") or {})
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "train_n": bundle["train_n"],
        "train_start": bundle["train_start"],
        "train_end": bundle["train_end"],
        "optimizer_status": "lightgbm_location_scale_fit_completed",
        "convergence_code": 0,
        "candidate_feature_hash": bundle["candidate_feature_hash"],
        "active_feature_hash": bundle["active_feature_hash"],
        "dropped_features_json": bundle["dropped_features_json"],
        "scale_dropped_features_json": bundle["scale_dropped_features_json"],
        "drop_reason": None,
        "training_missingness": bundle["training_missingness_json"],
        "training_variance": bundle["training_variance_json"],
        "refit_frequency": P2B_REFIT_FREQUENCY,
        "refit_month": refit_month,
        "scale_smearing_factor": bundle["smearing_factor"],
        "scale_floor": P2B_SCALE_FLOOR,
        "standardization_method": bundle["standardization_method"],
        "oof_standardized_loss_count": bundle["oof_standardized_loss_count"],
        "oof_location_count": bundle["oof_location_count"],
        "oof_scale_count": bundle["oof_scale_count"],
        "standardized_var": bundle["standardized_var"],
        "standardized_es": bundle["standardized_es"],
        "evt_shape": evt_tail.get("evt_shape"),
        "evt_scale": evt_tail.get("evt_scale"),
        "threshold_quantile": evt_tail.get("threshold_quantile"),
        "threshold_value": evt_tail.get("threshold_value"),
        "evt_exceedance_count": evt_tail.get("evt_exceedance_count"),
        "threshold_diagnostics_json": evt_tail.get("threshold_diagnostics_json"),
        "threshold_policy": evt_tail.get("threshold_policy"),
        "threshold_selection": evt_tail.get("threshold_selection"),
    }


def _p2b_unavailable_feature_forecast(
    *,
    row: Mapping[str, object],
    model_name: str,
    information_set: str,
    tail_level: float,
    bundle: Mapping[str, object],
    unavailable_features: list[str],
) -> dict[str, object]:
    return {
        "forecast_date": row["forecast_date"],
        "target_family": row.get("target_family") or "full_gap_settle_to_open",
        "model_name": model_name,
        "information_set": information_set,
        "tail_level": tail_level,
        "refit_frequency": P2B_REFIT_FREQUENCY,
        "var_forecast": None,
        "es_forecast": None,
        "es_companion_type": bundle.get("es_companion_type"),
        "realized_loss": _required_float(row["realized_loss"]),
        "var_breach": None,
        "is_valid_forecast": False,
        "invalid_reason": "unavailable_feature_not_valid_at_cutoff",
        "train_start": bundle.get("train_start"),
        "train_end": bundle.get("train_end"),
        "train_n": bundle.get("train_n"),
        "fit_status": "unavailable_feature_not_valid_at_cutoff",
        "failure_reason": ",".join(unavailable_features),
        "runtime_seconds": None,
        "dst_regime": row.get("dst_regime"),
        "absorption_regime": row.get("absorption_regime"),
        "vix_level": row.get("vix_level"),
        "active_feature_hash": bundle.get("active_feature_hash"),
        **_p2b_extended_forecast_fields(),
    }


def _p2b_extended_forecast_fields() -> dict[str, object]:
    return {
        "location_forecast": None,
        "scale_forecast": None,
        "scale_smearing_factor": None,
        "scale_floor": None,
        "standardization_method": None,
        "oof_standardized_loss_count": None,
        "standardized_var": None,
        "standardized_es": None,
        "evt_shape": None,
        "evt_scale": None,
        "threshold_quantile": None,
        "threshold_value": None,
        "evt_exceedance_count": None,
    }


def _p2b_unavailable_status(exc: BaseException) -> str:
    message = str(exc)
    if message.startswith("unavailable_"):
        return message.split(":", 1)[0]
    return "unavailable_optimizer_failed"


def _p2b_seed(*values: object) -> int:
    return int(stable_hash(values)[:8], 16)


def _unavailable_active_features(
    row: Mapping[str, object],
    active_features: list[str],
) -> list[str]:
    unavailable: list[str] = []
    for feature in active_features:
        value = _optional_float(row.get(feature))
        if value is None or not math.isfinite(value):
            unavailable.append(feature)
    return unavailable


def build_p2b_feature_unavailability_date_records(
    forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in forecasts:
        if row.get("fit_status") != "unavailable_feature_not_valid_at_cutoff":
            continue
        for feature in _missing_feature_names(row.get("failure_reason")):
            records.append(
                {
                    "forecast_date": row.get("forecast_date"),
                    "target_family": row.get("target_family"),
                    "model_name": row.get("model_name"),
                    "information_set": row.get("information_set"),
                    "tail_level": row.get("tail_level"),
                    "feature": feature,
                    "source_family": _feature_source_family(feature),
                    "source_block": _feature_source_block(feature),
                    "fit_status": row.get("fit_status"),
                    "failure_reason": row.get("failure_reason"),
                    "dst_regime": row.get("dst_regime"),
                    "absorption_regime": row.get("absorption_regime"),
                    "active_feature_hash": row.get("active_feature_hash"),
                }
            )
    return sorted(
        records,
        key=lambda item: (
            str(item.get("information_set") or ""),
            _optional_float(item.get("tail_level")) or 0.0,
            str(item.get("feature") or ""),
            str(item.get("forecast_date") or ""),
        ),
    )


def build_p2b_feature_unavailability_records(
    forecasts: list[dict[str, object]],
) -> list[dict[str, object]]:
    denominators: dict[tuple[str, str, float], int] = {}
    dates_by_key: dict[tuple[str, str, float, str], list[str]] = {}
    for row in forecasts:
        model_name = str(row.get("model_name") or "")
        information_set = str(row.get("information_set") or "")
        tail_level = _optional_float(row.get("tail_level"))
        if not model_name or not information_set or tail_level is None:
            continue
        denominator_key = (model_name, information_set, tail_level)
        denominators[denominator_key] = denominators.get(denominator_key, 0) + 1
        if row.get("fit_status") != "unavailable_feature_not_valid_at_cutoff":
            continue
        for feature in _missing_feature_names(row.get("failure_reason")):
            key = (*denominator_key, feature)
            dates_by_key.setdefault(key, []).append(str(row.get("forecast_date") or ""))
    records: list[dict[str, object]] = []
    for (model_name, information_set, tail_level, feature), dates in sorted(dates_by_key.items()):
        denominator = denominators.get((model_name, information_set, tail_level), 0)
        clean_dates = sorted(date_value for date_value in dates if date_value)
        records.append(
            {
                "model_name": model_name,
                "information_set": information_set,
                "tail_level": tail_level,
                "feature": feature,
                "source_family": _feature_source_family(feature),
                "source_block": _feature_source_block(feature),
                "missing_count": len(clean_dates),
                "forecast_rows": denominator,
                "missing_rate": len(clean_dates) / denominator if denominator else None,
                "first_missing_date": clean_dates[0] if clean_dates else None,
                "last_missing_date": clean_dates[-1] if clean_dates else None,
                "missing_dates_json": json.dumps(clean_dates, separators=(",", ":")),
                "fit_status": "unavailable_feature_not_valid_at_cutoff",
            }
        )
    return records


def _missing_feature_names(value: object) -> list[str]:
    if value is None:
        return []
    return [feature.strip() for feature in str(value).split(",") if feature.strip()]


def _feature_matrix(frame: pl.DataFrame, active_features: list[str]) -> np.ndarray:
    selected = frame.select(
        [
            pl.col(feature).cast(pl.Float64, strict=False).alias(feature)
            if feature in frame.columns
            else pl.lit(None, dtype=pl.Float64).alias(feature)
            for feature in active_features
        ]
    )
    return cast(np.ndarray, selected.to_numpy())


def build_incremental_information_records(
    forecasts: list[dict[str, object]],
    *,
    baseline_information_set: str,
) -> list[dict[str, object]]:
    information_sets = registered_p2b_information_sets()
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
        for tail_level in PAPER_TAIL_LEVELS:
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
        for tail_level in PAPER_TAIL_LEVELS:
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
        and paired_rows >= PAPER_CONFIG.evaluation_policy.min_common_oos_rows
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
        "dm_method": PAPER_CONFIG.evaluation_policy.dm_method,
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


def build_metric_records(
    forecasts: list[dict[str, object]],
    *,
    sample_policy: str = "per_model_oos",
    common_sample_status_value: str | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, float, str | None], list[dict[str, object]]] = {}
    for row in forecasts:
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True:
            grouped.setdefault(
                (
                    str(row["model_name"]),
                    str(row.get("target_family") or "full_gap_settle_to_open"),
                    str(row.get("information_set") or "target_history_only"),
                    _required_float(row["tail_level"]),
                    str(row["refit_frequency"]) if row.get("refit_frequency") else None,
                ),
                [],
            ).append(row)
    records: list[dict[str, object]] = []
    for (model, target_family, information_set, tail_level, refit_frequency), rows in sorted(
        grouped.items()
    ):
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
                "target_family": target_family,
                "information_set": information_set,
                "tail_level": tail_level,
                "refit_frequency": refit_frequency,
                "sample_policy": sample_policy,
                "common_sample_status": common_sample_status_value,
                "rows": len(rows),
                "var_breach_rate": float(np.mean(breaches)) if rows else None,
                "expected_breach_rate": alpha,
                "exceedance_count": exceedance_count,
                "low_exceedance_warning": exceedance_count < 30,
                "kupiec_lr_uc": kupiec.get("lr_stat"),
                "kupiec_pvalue": kupiec.get("pvalue"),
                "christoffersen_lr_ind": christoffersen.get("lr_stat"),
                "christoffersen_pvalue": christoffersen.get("pvalue"),
                "dq_status": "unavailable_not_implemented",
                "mcs_status": "available_in_loss_matrix_artifact",
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


def build_common_sample_artifacts(
    forecasts: list[dict[str, object]],
    *,
    stage: str,
    anchor_model: str,
    anchor_information_set: str,
) -> dict[str, object]:
    valid_rows = _valid_forecast_rows(forecasts)
    per_model_metrics = build_metric_records(
        valid_rows,
        sample_policy="per_model_oos",
        common_sample_status_value=None,
    )
    grouped = _group_forecasts_by_key(valid_rows)
    evictions: list[dict[str, object]] = []
    headline_forecasts: list[dict[str, object]] = []
    status_by_tail: dict[float, str] = {}
    for tail_level in sorted({key[2] for key in grouped}):
        keys = sorted(key for key in grouped if key[2] == tail_level)
        anchor_key = (anchor_model, anchor_information_set, tail_level)
        anchor_dates = set(grouped.get(anchor_key, {}))
        if not anchor_dates:
            status_by_tail[tail_level] = "unavailable_missing_anchor"
            for key in keys:
                evictions.append(
                    _model_eviction_record(
                        stage=stage,
                        key=key,
                        anchor_key=anchor_key,
                        anchor_rows=0,
                        overlap_rows=0,
                        coverage_ratio=0.0,
                        retained=False,
                        eviction_reason="missing_anchor_sample",
                        common_rows=0,
                        common_anchor_coverage=0.0,
                        common_sample_status_value="unavailable_missing_anchor",
                    )
                )
            continue

        retained_keys: list[tuple[str, str, float]] = []
        pending_rows: list[dict[str, object]] = []
        for key in keys:
            overlap_rows = len(set(grouped[key]).intersection(anchor_dates))
            coverage_ratio = overlap_rows / len(anchor_dates)
            retained = key == anchor_key or coverage_ratio >= MODEL_EVICTION_COVERAGE_THRESHOLD
            if retained:
                retained_keys.append(key)
            pending_rows.append(
                _model_eviction_record(
                    stage=stage,
                    key=key,
                    anchor_key=anchor_key,
                    anchor_rows=len(anchor_dates),
                    overlap_rows=overlap_rows,
                    coverage_ratio=coverage_ratio,
                    retained=retained,
                    eviction_reason=None if retained else "coverage_below_model_eviction_threshold",
                    common_rows=0,
                    common_anchor_coverage=0.0,
                    common_sample_status_value="pending",
                )
            )
        common_dates = (
            sorted(set.intersection(*(set(grouped[key]) for key in retained_keys)))
            if retained_keys
            else []
        )
        common_anchor_coverage = len(common_dates) / len(anchor_dates)
        if common_anchor_coverage < COMMON_SAMPLE_MIN_ANCHOR_COVERAGE:
            tail_status = "common_sample_unstable"
        else:
            tail_status = common_sample_status(common_dates)
        status_by_tail[tail_level] = tail_status
        for row in pending_rows:
            row["common_rows"] = len(common_dates)
            row["common_anchor_coverage"] = common_anchor_coverage
            row["common_sample_status"] = tail_status
            evictions.append(row)
        for key in retained_keys:
            date_map = grouped[key]
            headline_forecasts.extend(date_map[forecast_date] for forecast_date in common_dates)

    headline_metrics = build_metric_records(
        headline_forecasts,
        sample_policy="headline_common_sample",
        common_sample_status_value=_combined_common_sample_status(status_by_tail),
    )
    loss_matrix = build_loss_matrix_records(headline_forecasts, stage=stage)
    return {
        "headline_forecasts": headline_forecasts,
        "headline_metrics": headline_metrics,
        "per_model_metrics": per_model_metrics,
        "model_eviction": evictions,
        "loss_matrix": loss_matrix,
        "dm_inference": build_block_bootstrap_dm_records(
            loss_matrix,
            stage=stage,
            anchor_model=anchor_model,
            anchor_information_set=anchor_information_set,
        ),
        "mcs": build_mcs_records(loss_matrix, stage=stage),
        "murphy": build_murphy_records(headline_forecasts, stage=stage),
        "stress_windows": build_stress_window_records(headline_forecasts, stage=stage),
        "common_sample_status": _combined_common_sample_status(status_by_tail),
    }


def build_loss_matrix_records(
    forecasts: list[dict[str, object]],
    *,
    stage: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in _valid_forecast_rows(forecasts):
        tail_level = _required_float(row["tail_level"])
        loss = _required_float(row["realized_loss"])
        var_forecast = _required_float(row["var_forecast"])
        es_forecast = _required_float(row["es_forecast"])
        q_loss = quantile_loss(loss, var_forecast, tail_level)
        realized_fz_loss = fz_loss(loss, var_forecast, es_forecast, tail_level)
        if not math.isfinite(realized_fz_loss):
            continue
        records.append(
            {
                "stage": stage,
                "forecast_date": row["forecast_date"],
                "target_family": row.get("target_family") or "full_gap_settle_to_open",
                "model_name": row["model_name"],
                "information_set": row.get("information_set") or "target_history_only",
                "tail_level": tail_level,
                "realized_loss": loss,
                "var_forecast": var_forecast,
                "es_forecast": es_forecast,
                "quantile_loss": q_loss,
                "fz_loss": realized_fz_loss,
                "dst_regime": row.get("dst_regime"),
                "absorption_regime": row.get("absorption_regime"),
                "vix_level": row.get("vix_level"),
            }
        )
    return sorted(
        records,
        key=lambda item: (
            _required_float(item["tail_level"]),
            str(item["model_name"]),
            str(item["information_set"]),
            str(item["forecast_date"]),
        ),
    )


def build_block_bootstrap_dm_records(
    loss_matrix: list[dict[str, object]],
    *,
    stage: str,
    anchor_model: str,
    anchor_information_set: str,
    reps: int = BOOTSTRAP_REPS,
    seed: int = INFERENCE_RANDOM_SEED,
) -> list[dict[str, object]]:
    grouped = _group_loss_matrix_by_key(loss_matrix)
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    for tail_level in sorted({key[2] for key in grouped}):
        anchor_key = (anchor_model, anchor_information_set, tail_level)
        anchor_rows = grouped.get(anchor_key, {})
        for candidate_key in sorted(key for key in grouped if key[2] == tail_level):
            if candidate_key == anchor_key:
                continue
            candidate_rows = grouped[candidate_key]
            dates = sorted(set(anchor_rows).intersection(candidate_rows))
            diffs = np.array(
                [
                    _required_float(candidate_rows[forecast_date]["fz_loss"])
                    - _required_float(anchor_rows[forecast_date]["fz_loss"])
                    for forecast_date in dates
                ],
                dtype=float,
            )
            diffs = diffs[np.isfinite(diffs)]
            block_length = max(5, round(len(diffs) ** (1.0 / 3.0))) if len(diffs) else None
            mean_diff = _safe_mean(diffs)
            pvalue = (
                _moving_block_one_sided_pvalue(
                    diffs,
                    observed_mean=mean_diff,
                    reps=reps,
                    block_length=int(block_length),
                    rng=rng,
                )
                if mean_diff is not None and block_length is not None and len(diffs) >= 2
                else None
            )
            records.append(
                {
                    "stage": stage,
                    "tail_level": tail_level,
                    "baseline_model_name": anchor_model,
                    "baseline_information_set": anchor_information_set,
                    "candidate_model_name": candidate_key[0],
                    "candidate_information_set": candidate_key[1],
                    "paired_rows": int(diffs.size),
                    "mean_fz_loss_diff_candidate_minus_baseline": mean_diff,
                    "alternative": "candidate_mean_diff_less_than_zero",
                    "null_hypothesis": "E[FZ_candidate_minus_baseline] >= 0",
                    "pvalue_one_sided": pvalue,
                    "reject_10pct": pvalue is not None and pvalue < 0.10,
                    "bootstrap_reps": reps,
                    "bootstrap_seed": seed,
                    "block_length": block_length,
                    "method_note": PAPER_CONFIG.evaluation_policy.dm_method,
                    "inference_status": "ok"
                    if pvalue is not None
                    else "unavailable_block_bootstrap_dm_insufficient_pairs",
                }
            )
    return records


def build_mcs_records(
    loss_matrix: list[dict[str, object]],
    *,
    stage: str,
    seed: int = INFERENCE_RANDOM_SEED,
    alpha: float = MCS_ALPHA,
    reps: int = BOOTSTRAP_REPS,
) -> list[dict[str, object]]:
    grouped = _group_loss_matrix_by_key(loss_matrix)
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    for tail_level in sorted({key[2] for key in grouped}):
        keys = sorted(key for key in grouped if key[2] == tail_level)
        if not keys:
            continue
        common_dates = sorted(set.intersection(*(set(grouped[key]) for key in keys)))
        if len(common_dates) < PAPER_CONFIG.evaluation_policy.min_common_oos_rows:
            for key in keys:
                records.append(
                    _mcs_record(
                        stage=stage,
                        key=key,
                        rows=len(common_dates),
                        mean_fz_loss=None,
                        included=False,
                        alpha=alpha,
                        reps=reps,
                        seed=seed,
                        block_length=None,
                        status="unavailable_insufficient_global_common_oos",
                        method_note=PAPER_CONFIG.evaluation_policy.mcs_method,
                    )
                )
            continue
        losses_by_key = {
            key: np.array(
                [
                    _required_float(grouped[key][forecast_date]["fz_loss"])
                    for forecast_date in common_dates
                ],
                dtype=float,
            )
            for key in keys
        }
        mean_losses = {key: _safe_mean(values) for key, values in losses_by_key.items()}
        active = {key for key, value in mean_losses.items() if value is not None}
        eliminated_step: dict[tuple[str, str, float], int] = {}
        elimination_pvalue: dict[tuple[str, str, float], float | None] = {}
        elimination_tmax: dict[tuple[str, str, float], float | None] = {}
        elimination_active_set: dict[tuple[str, str, float], str | None] = {}
        model_tmax_component: dict[tuple[str, str, float], float | None] = {}
        final_tmax_stat: float | None = None
        final_pvalue: float | None = None
        block_length = max(5, round(len(common_dates) ** (1.0 / 3.0)))
        step = 0
        while len(active) > 1:
            worst_key = max(active, key=lambda key: (cast(float, mean_losses[key]), key[0], key[1]))
            ordered_active = sorted(active)
            active_loss_matrix = np.column_stack([losses_by_key[key] for key in ordered_active])
            result = _hln_tmax_mcs_step(
                active_loss_matrix,
                reps=reps,
                block_length=block_length,
                rng=rng,
            )
            t_values = cast(np.ndarray, result["t_values"])
            for key, t_value in zip(ordered_active, t_values, strict=True):
                model_tmax_component[key] = (
                    float(t_value) if math.isfinite(float(t_value)) else None
                )
            pvalue = _optional_float(result["pvalue"])
            final_tmax_stat = _optional_float(result["tmax_stat"])
            final_pvalue = pvalue
            if pvalue is None or pvalue > alpha:
                break
            step += 1
            eliminated_step[worst_key] = step
            elimination_pvalue[worst_key] = pvalue
            elimination_tmax[worst_key] = _optional_float(result["tmax_stat"])
            elimination_active_set[worst_key] = _mcs_key_set_json(ordered_active)
            active.remove(worst_key)
        final_active_set = _mcs_key_set_json(sorted(active))
        for key in keys:
            records.append(
                _mcs_record(
                    stage=stage,
                    key=key,
                    rows=len(common_dates),
                    mean_fz_loss=mean_losses[key],
                    included=key in active,
                    alpha=alpha,
                    reps=reps,
                    seed=seed,
                    block_length=block_length,
                    status="ok" if active else "unavailable_empty_loss_matrix",
                    method_note=PAPER_CONFIG.evaluation_policy.mcs_method,
                    elimination_step=eliminated_step.get(key),
                    elimination_pvalue=elimination_pvalue.get(key),
                    tmax_stat=elimination_tmax.get(key)
                    if key in eliminated_step
                    else final_tmax_stat,
                    final_pvalue=final_pvalue,
                    model_t_stat=model_tmax_component.get(key),
                    active_model_set=elimination_active_set.get(key)
                    if key in eliminated_step
                    else final_active_set,
                )
            )
    return records


def _mcs_record(
    *,
    stage: str,
    key: tuple[str, str, float],
    rows: int,
    mean_fz_loss: float | None,
    included: bool,
    alpha: float,
    reps: int,
    seed: int,
    block_length: int | None,
    status: str,
    method_note: str,
    elimination_step: int | None = None,
    elimination_pvalue: float | None = None,
    tmax_stat: float | None = None,
    final_pvalue: float | None = None,
    model_t_stat: float | None = None,
    active_model_set: str | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "tail_level": key[2],
        "model_name": key[0],
        "information_set": key[1],
        "rows": rows,
        "mean_fz_loss": mean_fz_loss,
        "included_in_mcs": included,
        "elimination_step": elimination_step,
        "elimination_pvalue": elimination_pvalue,
        "model_t_stat": model_t_stat,
        "tmax_stat": tmax_stat,
        "final_pvalue": final_pvalue,
        "active_model_set": active_model_set,
        "mcs_alpha": alpha,
        "bootstrap_reps": reps,
        "bootstrap_seed": seed,
        "block_length": block_length,
        "mcs_status": status,
        "method_note": method_note,
    }


def _hln_tmax_mcs_step(
    losses: np.ndarray,
    *,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    if losses.ndim != 2 or min(losses.shape) < 2:
        return {"tmax_stat": None, "pvalue": None, "t_values": np.array([])}
    centered_against_cross_section = losses - np.mean(losses, axis=1, keepdims=True)
    dbar = np.mean(centered_against_cross_section, axis=0)
    null_centered = centered_against_cross_section - dbar
    bootstrap_means = _moving_block_bootstrap_mean_matrix(
        null_centered,
        reps=reps,
        block_length=block_length,
        rng=rng,
    )
    se = np.std(bootstrap_means, axis=0, ddof=1)
    tiny_se = se <= 1e-12
    t_values = np.divide(dbar, se, out=np.zeros_like(dbar), where=~tiny_se)
    t_values = np.where(tiny_se & (dbar > 1e-12), 1e12, t_values)
    t_values = np.where(tiny_se & (dbar < -1e-12), -1e12, t_values)
    if np.all(np.isnan(t_values)):
        return {"tmax_stat": None, "pvalue": None, "t_values": t_values}
    tmax_stat = float(np.nanmax(t_values))
    bootstrap_scaled = np.divide(
        bootstrap_means,
        se,
        out=np.zeros_like(bootstrap_means),
        where=~tiny_se,
    )
    bootstrap_tmax = np.nanmax(bootstrap_scaled, axis=1)
    bootstrap_tmax = bootstrap_tmax[np.isfinite(bootstrap_tmax)]
    if bootstrap_tmax.size == 0:
        return {"tmax_stat": tmax_stat, "pvalue": None, "t_values": t_values}
    pvalue = float((np.sum(bootstrap_tmax >= tmax_stat) + 1) / (bootstrap_tmax.size + 1))
    return {"tmax_stat": tmax_stat, "pvalue": pvalue, "t_values": t_values}


def _mcs_key_set_json(keys: list[tuple[str, str, float]]) -> str:
    return json.dumps(
        [
            {
                "model_name": key[0],
                "information_set": key[1],
                "tail_level": key[2],
            }
            for key in keys
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _moving_block_bootstrap_mean_matrix(
    matrix: np.ndarray,
    *,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    n, m = matrix.shape
    starts = np.arange(n)
    output = np.empty((reps, m), dtype=float)
    for rep in range(reps):
        indices: list[int] = []
        while len(indices) < n:
            start = int(rng.choice(starts))
            for offset in range(block_length):
                indices.append((start + offset) % n)
                if len(indices) == n:
                    break
        output[rep, :] = np.mean(matrix[indices, :], axis=0)
    return output


def build_murphy_records(
    forecasts: list[dict[str, object]],
    *,
    stage: str,
    grid_size: int = 200,
) -> list[dict[str, object]]:
    valid_rows = _valid_forecast_rows(forecasts)
    losses = np.array([_required_float(row["realized_loss"]) for row in valid_rows], dtype=float)
    losses = losses[np.isfinite(losses)]
    if losses.size == 0:
        return []
    lower = float(np.quantile(losses, 0.01))
    upper = float(np.quantile(losses, 0.99))
    thresholds = np.linspace(lower, upper, grid_size)
    grouped = _group_forecasts_by_key(valid_rows)
    records: list[dict[str, object]] = []
    for key, rows_by_date in sorted(grouped.items()):
        rows = list(rows_by_date.values())
        row_losses = np.array([_required_float(row["realized_loss"]) for row in rows], dtype=float)
        var_values = np.array([_required_float(row["var_forecast"]) for row in rows], dtype=float)
        alpha = 1.0 - key[2]
        for threshold_index, threshold in enumerate(thresholds):
            exceed = (row_losses > threshold).astype(float)
            elementary = (exceed - alpha) * (var_values - threshold)
            records.append(
                {
                    "stage": stage,
                    "model_name": key[0],
                    "information_set": key[1],
                    "tail_level": key[2],
                    "threshold_index": threshold_index,
                    "threshold_value": float(threshold),
                    "threshold_grid_policy": "pooled_oos_loss_1pct_to_99pct_200_equal_points",
                    "rows": len(rows),
                    "mean_elementary_score": _safe_mean(elementary),
                }
            )
    return records


def build_stress_window_records(
    forecasts: list[dict[str, object]],
    *,
    stage: str,
) -> list[dict[str, object]]:
    loss_by_date: dict[str, float] = {}
    vix_by_date: dict[str, float] = {}
    for row in _valid_forecast_rows(forecasts):
        forecast_date = str(row["forecast_date"])
        loss = _optional_float(row.get("realized_loss"))
        if loss is not None and math.isfinite(loss):
            loss_by_date[forecast_date] = loss
        vix = _optional_float(row.get("vix_level"))
        if vix is not None and math.isfinite(vix):
            vix_by_date[forecast_date] = vix
    records: list[dict[str, object]] = []
    if loss_by_date:
        threshold = float(np.quantile(np.array(list(loss_by_date.values()), dtype=float), 0.90))
        records.extend(
            {
                "stage": stage,
                "window_name": "loss_top_decile",
                "forecast_date": forecast_date,
                "threshold_value": threshold,
                "realized_loss": loss,
                "vix_level": vix_by_date.get(forecast_date),
                "classifier_policy": "full_sample_reproducible_decile",
                "rolling_classifier_status": "future_work_not_used_in_first_round",
            }
            for forecast_date, loss in sorted(loss_by_date.items())
            if loss >= threshold
        )
    if vix_by_date:
        threshold = float(np.quantile(np.array(list(vix_by_date.values()), dtype=float), 0.90))
        records.extend(
            {
                "stage": stage,
                "window_name": "vix_top_decile",
                "forecast_date": forecast_date,
                "threshold_value": threshold,
                "realized_loss": loss_by_date.get(forecast_date),
                "vix_level": vix,
                "classifier_policy": "full_sample_reproducible_decile",
                "rolling_classifier_status": "future_work_not_used_in_first_round",
            }
            for forecast_date, vix in sorted(vix_by_date.items())
            if vix >= threshold
        )
    return records


def _valid_forecast_rows(forecasts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in forecasts
        if row.get("fit_status") == "ok" and row.get("is_valid_forecast") is True
    ]


def _forecast_key(row: Mapping[str, object]) -> tuple[str, str, float]:
    return (
        str(row["model_name"]),
        str(row.get("information_set") or "target_history_only"),
        _required_float(row["tail_level"]),
    )


def _group_forecasts_by_key(
    forecasts: list[dict[str, object]],
) -> dict[tuple[str, str, float], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str, float], dict[str, dict[str, object]]] = {}
    for row in forecasts:
        grouped.setdefault(_forecast_key(row), {})[str(row["forecast_date"])] = row
    return grouped


def _group_loss_matrix_by_key(
    rows: list[dict[str, object]],
) -> dict[tuple[str, str, float], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str, float], dict[str, dict[str, object]]] = {}
    for row in rows:
        key = (
            str(row["model_name"]),
            str(row.get("information_set") or "target_history_only"),
            _required_float(row["tail_level"]),
        )
        grouped.setdefault(key, {})[str(row["forecast_date"])] = row
    return grouped


def _model_eviction_record(
    *,
    stage: str,
    key: tuple[str, str, float],
    anchor_key: tuple[str, str, float],
    anchor_rows: int,
    overlap_rows: int,
    coverage_ratio: float,
    retained: bool,
    eviction_reason: str | None,
    common_rows: int,
    common_anchor_coverage: float,
    common_sample_status_value: str,
) -> dict[str, object]:
    return {
        "stage": stage,
        "model_name": key[0],
        "information_set": key[1],
        "tail_level": key[2],
        "anchor_model_name": anchor_key[0],
        "anchor_information_set": anchor_key[1],
        "anchor_rows": anchor_rows,
        "overlap_rows": overlap_rows,
        "coverage_ratio": coverage_ratio,
        "eviction_threshold": MODEL_EVICTION_COVERAGE_THRESHOLD,
        "retained_for_headline": retained,
        "eviction_reason": eviction_reason,
        "common_rows": common_rows,
        "common_anchor_coverage": common_anchor_coverage,
        "common_sample_min_anchor_coverage": COMMON_SAMPLE_MIN_ANCHOR_COVERAGE,
        "common_sample_status": common_sample_status_value,
    }


def _combined_common_sample_status(status_by_tail: Mapping[float, str]) -> str:
    statuses = set(status_by_tail.values())
    if not statuses:
        return "unavailable_empty_forecasts"
    if "common_sample_unstable" in statuses:
        return "common_sample_unstable"
    if statuses == {"ok"}:
        return "ok"
    return ",".join(sorted(statuses))


def _moving_block_one_sided_pvalue(
    values: np.ndarray,
    *,
    observed_mean: float | None,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> float | None:
    if observed_mean is None or values.size < 2:
        return None
    centered = values - float(np.mean(values))
    n = int(centered.size)
    starts = np.arange(n)
    count = 0
    for _ in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            start = int(rng.choice(starts))
            for offset in range(block_length):
                sample.append(float(centered[(start + offset) % n]))
                if len(sample) == n:
                    break
        if float(np.mean(np.array(sample, dtype=float))) <= observed_mean:
            count += 1
    return float((count + 1) / (reps + 1))


def _moving_block_greater_pvalue(
    values: np.ndarray,
    *,
    observed_mean: float | None,
    reps: int,
    block_length: int,
    rng: np.random.Generator,
) -> float | None:
    if observed_mean is None or values.size < 2:
        return None
    centered = values - float(np.mean(values))
    n = int(centered.size)
    starts = np.arange(n)
    count = 0
    for _ in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            start = int(rng.choice(starts))
            for offset in range(block_length):
                sample.append(float(centered[(start + offset) % n]))
                if len(sample) == n:
                    break
        if float(np.mean(np.array(sample, dtype=float))) >= observed_mean:
            count += 1
    return float((count + 1) / (reps + 1))


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
    latex_dir = run_dir / "latex" / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    tables = 0
    manifest = _read_manifest(run_dir)
    for stage in ("p2a", "p2b"):
        metrics_path = run_dir / "metrics" / f"{stage}_metrics.parquet"
        if not metrics_path.exists():
            continue
        metrics = pl.read_parquet(metrics_path)
        tex = _metrics_to_latex(metrics, manifest=manifest)
        (latex_dir / f"{stage}_metrics_table.tex").write_text(tex, encoding="utf-8")
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
    panel_frame = pl.read_parquet(panel_path)
    rows = build_leakage_check_records(panel_frame.to_dicts())
    binding = _current_leakage_binding(run_dir, panel_frame=panel_frame)
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
            **binding,
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


def _current_leakage_binding(
    run_dir: Path,
    *,
    panel_frame: pl.DataFrame | None = None,
) -> dict[str, object]:
    panel = (
        panel_frame
        if panel_frame is not None
        else pl.read_parquet(run_dir / "panel" / "modeling_panel.parquet")
    )
    calendar_path = run_dir / "panel" / "calendar_map.parquet"
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
    for column in columns:
        if column not in working.columns:
            working = working.with_columns(pl.lit(None).alias(column))
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
    oos_diagnostics = find_oos_start_diagnostics(rows, tail_level=tail_level)
    oos_start = cast(str | None, oos_diagnostics["oos_start"])
    if oos_start is None:
        return {
            "forecasts": [],
            "diagnostics": [
                {
                    "model_name": model_name,
                    "tail_level": tail_level,
                    "shard_id": _forecast_shard_id(model_name, tail_level),
                    "fit_status": "unavailable_insufficient_oos_start",
                    "oos_failure_reason": oos_diagnostics["failure_reason"],
                    "train_n": oos_diagnostics["train_n"],
                    "train_exceedances": oos_diagnostics["train_exceedances"],
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
    """Convert return-space Student-t forecasts into loss-space VaR and ES.

    The ARCH model is fit on negative returns for numerical convenience, but this
    helper receives the forecast mean in return units. Let return R = mu + sigma Z
    and loss L = -R. For a right-tail loss level tau, alpha = 1 - tau and the
    return cutoff is the lower alpha quantile q_alpha of the standardized
    Student-t innovation. Therefore VaR_tau(L) = -(mu + sigma q_alpha).

    For Student-t innovations standardized to unit variance, q_alpha is
    sqrt((nu - 2) / nu) * t_nu^{-1}(alpha). The left-tail return ES is the
    negative of the symmetric right-tail standardized ES,
    sqrt((nu - 2) / nu) * f_nu(t_nu^{-1}(alpha)) / alpha
    * (nu + t_nu^{-1}(alpha)^2) / (nu - 1), so loss ES is
    -mu + sigma * standardized_upper_es.
    """
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
    require_finite_gpd_es: bool = False,
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
        if not math.isfinite(scale) or scale <= 0.0:
            raise PaperRunError("EVT calibration has invalid GPD scale")
        exceedance_probability = excesses.size / values.size
        target_tail_probability = max(1.0 - tail_level, 1e-12)
        ratio = max(exceedance_probability / target_tail_probability, 1.0)
        if abs(shape) < 1e-8:
            var_z = threshold + scale * math.log(ratio)
        else:
            var_z = threshold + scale * (ratio**shape - 1.0) / shape
        if shape < 1.0:
            es_z = var_z + (scale + shape * (var_z - threshold)) / (1.0 - shape)
        elif require_finite_gpd_es:
            raise PaperRunError(f"EVT calibration shape >= 1 has infinite ES: {shape}")
        else:
            es_z = static_empirical_es(values, var_z)
        tail_method = "pot_gpd_filtered_es"
    return {
        "standardized_var": float(var_z),
        "standardized_es": float(max(var_z, es_z)),
        "threshold_quantile": threshold_quantile,
        "threshold_value": threshold,
        "evt_exceedance_count": int(excesses.size),
        "evt_shape": shape if tail_level > threshold_quantile else None,
        "evt_scale": scale if tail_level > threshold_quantile else None,
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
    cutoff: datetime | None = None,
    fill_method: str,
) -> dict[str, object]:
    if not date_key:
        return {}
    try:
        target_date = date.fromisoformat(date_key)
    except ValueError:
        return {}
    prior_keys = [key for key in features_by_date if key <= date_key]
    if not prior_keys:
        return {}
    for selected_key in sorted(prior_keys, reverse=True):
        try:
            selected_date = date.fromisoformat(selected_key)
        except ValueError:
            continue
        if (
            target_date - selected_date
        ).days > PAPER_CONFIG.leakage_policy.max_forward_fill_us_close_days:
            continue
        output = dict(features_by_date[selected_key])
        if cutoff is not None and not _feature_record_available_by_cutoff(output, cutoff):
            continue
        selected_fill_method = "direct" if selected_key == date_key else fill_method
        for feature_name in _feature_value_names(output):
            output[f"{feature_name}__fill_method"] = selected_fill_method
            output[f"{feature_name}__source_date"] = selected_key
        return output
    return {}


def _fred_features_asof(
    features_by_date: dict[str, dict[str, object]],
    date_key: str,
    *,
    cutoff: datetime | None = None,
) -> dict[str, object]:
    """Select FRED predictors feature-by-feature using timestamp-safe as-of logic."""
    if not date_key or cutoff is None:
        return {}
    try:
        date.fromisoformat(date_key)
    except ValueError:
        return {}
    feature_names = sorted(
        {
            feature
            for record in features_by_date.values()
            for feature in _feature_value_names(record)
            if feature.startswith("fred_")
        }
    )
    output: dict[str, object] = {}
    rate_source_ages: list[int] = []
    rate_available_ts: list[datetime] = []
    rate_source_dates: list[str] = []
    for feature_name in feature_names:
        selected = _fred_feature_candidate_asof(
            features_by_date,
            date_key=date_key,
            feature_name=feature_name,
            cutoff=cutoff,
        )
        if selected is None:
            continue
        is_forward_fill = selected["date_key"] != date_key
        is_filled_diff = bool(is_forward_fill and feature_name.endswith("_diff"))
        output[feature_name] = 0.0 if is_filled_diff else selected["value"]
        _stamp_feature_metadata(
            output,
            feature_name=feature_name,
            available_ts_utc=cast(datetime | None, selected["available_ts_utc"]),
            source_date=str(selected["source_date"]),
            fill_method="forward_fill_fred_release_lag" if is_forward_fill else "direct",
        )
        output[f"{feature_name}__forward_fill_fred_release_lag"] = is_forward_fill
        output[f"{feature_name}__fill_source_obs_date"] = selected["source_date"]
        output[f"{feature_name}__fill_feature_available_ts_utc"] = selected["available_ts_utc"]
        output[f"{feature_name}__is_filled_diff"] = is_filled_diff
        output[f"{feature_name}__fred_release_lag_days"] = selected["release_lag_days"]
        output[f"{feature_name}__fred_source_age_days"] = selected["source_age_days"]
        if (
            feature_name in FRED_RATE_STALENESS_LEVEL_FEATURES
            and selected["source_age_days"] is not None
        ):
            rate_source_ages.append(int(cast(int, selected["source_age_days"])))
            if selected["available_ts_utc"] is not None:
                rate_available_ts.append(cast(datetime, selected["available_ts_utc"]))
            if selected["source_date"]:
                rate_source_dates.append(str(selected["source_date"]))
    _synthesize_forward_filled_fred_diffs(output, feature_names)
    if rate_source_ages:
        output[FRED_RATE_STALENESS_FEATURE] = float(max(rate_source_ages))
        latest_rate_available = max(rate_available_ts) if rate_available_ts else None
        latest_source_date = max(rate_source_dates) if rate_source_dates else date_key
        _stamp_feature_metadata(
            output,
            feature_name=FRED_RATE_STALENESS_FEATURE,
            available_ts_utc=latest_rate_available,
            source_date=latest_source_date,
            fill_method="fred_rates_staleness",
        )
    return output


def _synthesize_forward_filled_fred_diffs(
    output: dict[str, object],
    feature_names: list[str],
) -> None:
    for level_feature in [
        key for key in output if key.startswith("fred_") and key.endswith("_level")
    ]:
        diff_feature = f"{level_feature.removesuffix('_level')}_diff"
        if diff_feature not in feature_names or diff_feature in output:
            continue
        if output.get(f"{level_feature}__fill_method") != "forward_fill_fred_release_lag":
            continue
        available_ts = _coerce_datetime(output.get(f"{level_feature}__available_ts_utc"))
        source_date = str(output.get(f"{level_feature}__source_date") or "")
        output[diff_feature] = 0.0
        _stamp_feature_metadata(
            output,
            feature_name=diff_feature,
            available_ts_utc=available_ts,
            source_date=source_date,
            fill_method="forward_fill_fred_release_lag",
        )
        for suffix in (
            "forward_fill_fred_release_lag",
            "fill_source_obs_date",
            "fill_feature_available_ts_utc",
            "fred_release_lag_days",
            "fred_source_age_days",
        ):
            output[f"{diff_feature}__{suffix}"] = output.get(f"{level_feature}__{suffix}")
        output[f"{diff_feature}__is_filled_diff"] = True


def _fred_feature_candidate_asof(
    features_by_date: dict[str, dict[str, object]],
    *,
    date_key: str,
    feature_name: str,
    cutoff: datetime,
) -> dict[str, object] | None:
    try:
        target_date = date.fromisoformat(date_key)
    except ValueError:
        return None
    prior_keys = [key for key in features_by_date if key <= date_key]
    for selected_key in sorted(prior_keys, reverse=True):
        try:
            selected_date = date.fromisoformat(selected_key)
        except ValueError:
            continue
        release_lag_days = (target_date - selected_date).days
        if release_lag_days > PAPER_CONFIG.leakage_policy.max_forward_fill_us_close_days:
            continue
        record = features_by_date[selected_key]
        value = _optional_float(record.get(feature_name))
        if value is None:
            continue
        available_ts = _coerce_datetime(record.get(f"{feature_name}__available_ts_utc"))
        if available_ts is None or available_ts > cutoff:
            continue
        source_date_text = str(record.get(f"{feature_name}__source_date") or selected_key)
        try:
            source_date = date.fromisoformat(source_date_text)
        except ValueError:
            source_date = selected_date
            source_date_text = selected_key
        source_age_days = max(0, (target_date - source_date).days)
        return {
            "date_key": selected_key,
            "value": value,
            "available_ts_utc": available_ts,
            "source_date": source_date_text,
            "release_lag_days": release_lag_days,
            "source_age_days": source_age_days,
        }
    return None


def _feature_record_available_by_cutoff(
    record: Mapping[str, object],
    cutoff: datetime,
) -> bool:
    value_names = _feature_value_names(record)
    if not value_names:
        return True
    evaluable = False
    for feature_name in value_names:
        if record.get(feature_name) is None:
            continue
        available_ts = _coerce_datetime(record.get(f"{feature_name}__available_ts_utc"))
        if available_ts is None or available_ts > cutoff:
            return False
        evaluable = True
    return evaluable


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
            or key.endswith("_days")
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


def _official_us_close_by_date(
    calendar_records: list[dict[str, object]],
) -> dict[str, datetime]:
    closes: dict[str, datetime] = {}
    for row in calendar_records:
        date_key = str(row.get("calendar_date") or "")
        close_ts = _coerce_datetime(row.get("us_close_ts_utc"))
        if date_key and close_ts is not None:
            closes[date_key] = close_ts
    return closes


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


def _massive_daily_feature_map(
    records: list[dict[str, object]],
    *,
    calendar_records: list[dict[str, object]] | None = None,
) -> dict[str, dict[str, object]]:
    official_close_by_date = _official_us_close_by_date(calendar_records or [])
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
            official_close = official_close_by_date.get(date_key)
            available_ts = (
                official_close
                + timedelta(minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes)
                if official_close is not None
                else _feature_available_ts(
                    row,
                    lag_minutes=PAPER_CONFIG.leakage_policy.massive_vendor_lag_minutes,
                )
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
        series_id = str(row["series_id"])
        if series_id.upper() in PAPER_FX_FRED_SERIES:
            continue
        by_series.setdefault(series_id, []).append(row)
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


def _cboe_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    features_by_date: dict[str, dict[str, object]] = {}
    for row in sorted(records, key=lambda item: str(item.get("observation_date") or "")):
        if str(row.get("symbol", "")).upper() != "VIX":
            continue
        date_key = str(row["observation_date"])
        output = features_by_date.setdefault(date_key, {})
        close = _optional_float(row.get("close"))
        range_value = _optional_float(row.get("range"))
        available_ts = _coerce_datetime(row.get("vendor_available_ts_utc"))
        output["cboe_vix_close"] = close
        output["cboe_vix_range"] = range_value
        _stamp_feature_metadata(
            output,
            feature_name="cboe_vix_close",
            available_ts_utc=available_ts,
            source_date=date_key,
        )
        _stamp_feature_metadata(
            output,
            feature_name="cboe_vix_range",
            available_ts_utc=available_ts,
            source_date=date_key,
        )
    return features_by_date


def _canonical_fx_context(
    *,
    massive_daily_records: list[dict[str, object]],
    fred_records: list[dict[str, object]],
    calendar_records: list[dict[str, object]],
) -> dict[str, object]:
    _ = massive_daily_records, calendar_records
    return {"fred": _fred_fx_records(fred_records)}


def _fred_fx_records(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    rows = [row for row in records if str(row.get("series_id", "")).upper() in PAPER_FX_FRED_SERIES]
    rows.sort(key=lambda row: str(row.get("observation_date") or ""))
    output: dict[str, dict[str, object]] = {}
    previous_value: float | None = None
    for row in rows:
        observation_date = str(row.get("observation_date") or "")
        if not observation_date:
            continue
        value = _optional_float(row.get("value"))
        fx_return = (
            math.log(value) - math.log(previous_value)
            if value is not None and previous_value is not None and value > 0 and previous_value > 0
            else None
        )
        output[observation_date] = {
            "observation_date": observation_date,
            "value": value,
            "return": fx_return,
            "available_ts": _coerce_datetime(row.get("vendor_available_ts_utc")),
            "source": "fred_h10",
        }
        if value is not None and value > 0:
            previous_value = value
    return output


def _canonical_fx_asof(
    context: Mapping[str, object],
    *,
    us_date: str,
    cutoff: datetime | None,
) -> dict[str, object]:
    if not us_date or cutoff is None:
        return {}
    try:
        target_date = date.fromisoformat(us_date)
    except ValueError:
        return {}
    fred_rows = cast(dict[str, dict[str, object]], context.get("fred") or {})
    exact_fred = fred_rows.get(us_date)
    latest_fred = _latest_usable_fx_candidate(
        fred_rows,
        target_date=target_date,
        cutoff=cutoff,
        max_release_age_days=FRED_H10_RELEASE_AGE_CAP_DAYS,
    )
    if latest_fred is not None:
        return _fx_output(
            latest_fred,
            target_date=target_date,
            cutoff=cutoff,
            source="fred_h10_latest_released",
            reason="fred_h10_latest_released",
            fred_available=True,
        )

    return {
        "fx_usdjpy_level": None,
        "fx_usdjpy_return": None,
        "fx_source": "null_unavailable",
        "fx_observation_date": None,
        "fx_available_ts_utc": None,
        "fx_staleness_days": None,
        "fx_observation_age_days": None,
        "fx_release_age_days": None,
        "fx_is_stale": None,
        "fx_fallback_reason": _fred_fx_unavailable_reason(
            exact_fred,
            fred_rows=fred_rows,
            target_date=target_date,
            cutoff=cutoff,
        ),
        "fred_dexjpus_available": False,
    }


def _latest_usable_fx_candidate(
    rows: dict[str, dict[str, object]],
    *,
    target_date: date,
    cutoff: datetime,
    max_release_age_days: int,
) -> dict[str, object] | None:
    candidates = []
    for row in rows.values():
        if not _fx_candidate_is_usable(
            row,
            cutoff=cutoff,
            target_date=target_date,
            max_release_age_days=max_release_age_days,
        ):
            continue
        candidates.append(row)
    if not candidates:
        return None
    return max(candidates, key=lambda row: str(row["observation_date"]))


def _fx_candidate_is_usable(
    row: Mapping[str, object],
    *,
    cutoff: datetime,
    target_date: date,
    max_release_age_days: int,
) -> bool:
    value = _optional_float(row.get("value"))
    available_ts = _coerce_datetime(row.get("available_ts"))
    observation_date = _fx_observation_date(row)
    if value is None or not math.isfinite(value) or value <= 0:
        return False
    if available_ts is None or available_ts > cutoff:
        return False
    if observation_date is None:
        return False
    if observation_date > target_date:
        return False
    release_age_days = max(0, (cutoff.date() - available_ts.date()).days)
    return release_age_days <= max_release_age_days


def _fx_output(
    row: Mapping[str, object],
    *,
    target_date: date,
    cutoff: datetime,
    source: str,
    reason: str,
    fred_available: bool,
) -> dict[str, object]:
    observation_date = _fx_observation_date(row)
    available_ts = _coerce_datetime(row.get("available_ts"))
    observation_age_days = (
        None if observation_date is None else (target_date - observation_date).days
    )
    release_age_days = (
        None if available_ts is None else max(0, (cutoff.date() - available_ts.date()).days)
    )
    source_date = observation_date.isoformat() if observation_date else None
    output: dict[str, object] = {
        "fx_usdjpy_level": _optional_float(row.get("value")),
        "fx_usdjpy_return": _optional_float(row.get("return")),
        "fx_source": source,
        "fx_observation_date": source_date,
        "fx_available_ts_utc": available_ts,
        "fx_staleness_days": observation_age_days,
        "fx_observation_age_days": observation_age_days,
        "fx_release_age_days": release_age_days,
        "fx_is_stale": observation_age_days is not None and observation_age_days > 0,
        "fx_fallback_reason": reason,
        "fred_dexjpus_available": fred_available,
    }
    for feature_name in ("fx_usdjpy_level", "fx_usdjpy_return"):
        _stamp_feature_metadata(
            output,
            feature_name=feature_name,
            available_ts_utc=available_ts,
            source_date=source_date or "",
            fill_method=source,
        )
    return output


def _fx_observation_date(row: Mapping[str, object]) -> date | None:
    raw = row.get("observation_date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _fred_fx_unavailable_reason(
    exact_fred: Mapping[str, object] | None,
    *,
    fred_rows: Mapping[str, Mapping[str, object]],
    target_date: date,
    cutoff: datetime,
) -> str:
    if exact_fred is None:
        pass
    else:
        value = _optional_float(exact_fred.get("value"))
        available = _coerce_datetime(exact_fred.get("available_ts"))
        if value is None or not math.isfinite(value):
            return JoinMissReason.FRED_FX_NULL_OBSERVATION.value
        if available is None or available > cutoff:
            return JoinMissReason.FRED_H10_RELEASE_DELAY.value
    released_values = [
        row
        for row in fred_rows.values()
        if (value := _optional_float(row.get("value"))) is not None
        and math.isfinite(value)
        and (available := _coerce_datetime(row.get("available_ts"))) is not None
        and available <= cutoff
        and (observation_date := _fx_observation_date(row)) is not None
        and observation_date <= target_date
    ]
    if released_values:
        return JoinMissReason.FRED_FX_STALE_BEYOND_FILL_WINDOW.value
    return JoinMissReason.FRED_H10_RELEASE_DELAY.value


def _spy_minute_feature_map(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    if any("spy_late_30m_return" in row for row in records):
        records = _records_with_recomputed_spy_late_volume_surge(records)
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
    rolling_late_volume: list[float] = []
    for date_key in sorted(by_date):
        rows = sorted(by_date[date_key], key=lambda row: str(row["bar_end_ts_utc"]))
        closes = [_optional_float(row.get("close")) for row in rows]
        highs = [_optional_float(row.get("high")) for row in rows]
        lows = [_optional_float(row.get("low")) for row in rows]
        volumes = [_optional_float(row.get("volume")) or 0.0 for row in rows]
        valid_closes = [value for value in closes if value is not None and value > 0]
        late_volume = float(sum(volumes[-60:]))
        rolling_mean_volume = (
            float(np.mean(rolling_late_volume[-20:])) if rolling_late_volume else None
        )
        volume_surge = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else late_volume / rolling_mean_volume
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
        rolling_late_volume.append(late_volume)
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
    year_stats_by_year: dict[int, dict[str, int]] = {}
    for (year, month), chunk_rows in sorted(by_month.items()):
        path = cache_path(
            root,
            dataset="jquants_nk225f_daily",
            schema_version=JQUANTS_SILVER_SCHEMA.version,
            year=year,
            month=month,
        )
        result = atomic_write_parquet(
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
        stats = year_stats_by_year.setdefault(year, _new_progress_stats())
        _add_stat(stats, "months")
        _add_stat(stats, "fetched")
        _add_stat(stats, "rows", result.rows)
    for year, stats in sorted(year_stats_by_year.items()):
        _log_year_stats("J-Quants silver", year, stats)


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
        late_volume = float(sum(_optional_float(row.get("volume")) or 0.0 for row in hour_rows))
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
                "spy_late_volume_surge": None,
                "spy_final_window_momentum": _rows_return(final_rows),
                "late_60m_volume_for_surge": late_volume,
                "regular_session_volume_for_surge": session_volume,
                "feature_available_ts_utc": feature_available,
                "official_close_ts_utc": official_close,
                "selected_close_bar_end_ts_utc": selected_close_ts,
                "vendor_lag_seconds": vendor_lag_minutes * 60,
            }
        )
    return _records_with_recomputed_spy_late_volume_surge(records)


def _records_with_recomputed_spy_late_volume_surge(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Recompute SPY volume surge over the full supplied date sequence.

    The silver cache is partitioned monthly, but the 20-session baseline is a
    time-series feature. Recomputing after all cache chunks are loaded prevents
    each month boundary from manufacturing a missing first-day surge value.
    """
    rolling_late_volume: list[float] = []
    output: list[dict[str, object]] = []
    for row in sorted(records, key=lambda item: str(item.get("bar_date_et") or "")):
        enriched = dict(row)
        late_volume = _optional_float(enriched.get("late_60m_volume_for_surge"))
        if late_volume is None:
            output.append(enriched)
            continue
        rolling_mean_volume = (
            float(np.mean(rolling_late_volume[-20:])) if rolling_late_volume else None
        )
        enriched["spy_late_volume_surge"] = (
            None
            if rolling_mean_volume is None or rolling_mean_volume == 0.0
            else late_volume / rolling_mean_volume
        )
        rolling_late_volume.append(late_volume)
        output.append(enriched)
    return output


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


def _filter_records_by_range(
    records: list[dict[str, object]],
    *,
    start: str,
    end: str,
    date_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for row in records:
        date_value = _first_row_date_value(row, date_fields)
        if date_value is not None and start <= date_value <= end:
            filtered.append(row)
    return filtered


def _filter_records_by_dates(
    records: list[dict[str, object]],
    *,
    allowed_dates: list[str],
    date_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    allowed = set(allowed_dates)
    return [
        row
        for row in records
        if (date_value := _first_row_date_value(row, date_fields)) is not None
        and date_value in allowed
    ]


def _first_row_date_value(row: Mapping[str, object], date_fields: tuple[str, ...]) -> str | None:
    for field in date_fields:
        raw = row.get(field)
        if raw is not None:
            return str(raw)[:10]
    return None


def _unavailable_marker_covers(path: Path, start: str, end: str) -> bool:
    return path.exists() and _metadata_covers_range(read_json(path), start, end)


def _write_unavailable_marker(
    path: Path,
    *,
    source: str,
    error_class: VendorErrorClass,
    http_status: int | None,
    requested_range: list[str],
) -> None:
    if error_class.value not in PERSISTENT_UNAVAILABLE_ERRORS:
        return
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
        current_year: int | None = None
        year_stats = _new_progress_stats()
        for (year, month), trading_dates in sorted(dates_by_month.items()):
            if current_year is not None and year != current_year:
                _log_year_stats("J-Quants bronze", current_year, year_stats)
                year_stats = _new_progress_stats()
            current_year = year
            _add_stat(year_stats, "months")
            _add_stat(year_stats, "trading_days", len(trading_dates))
            path = cache_path(
                bronze_root,
                dataset="jquants_futures_daily",
                schema_version=JQUANTS_BRONZE_SCHEMA.version,
                year=year,
                month=month,
            )
            if path.exists() and _cache_covers_dates(path, trading_dates):
                cached_records = _filter_records_by_dates(
                    _read_parquet_records(path),
                    allowed_dates=trading_dates,
                    date_fields=("requested_date", "Date"),
                )
                rows.extend(cached_records)
                _add_stat(year_stats, "cache_hits")
                _add_stat(year_stats, "rows", len(cached_records))
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
            _add_stat(year_stats, "fetched")
            _add_stat(year_stats, "rows", result.rows)
            rows.extend(_read_parquet_records(path))
        if current_year is not None:
            _log_year_stats("J-Quants bronze", current_year, year_stats)
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
        min_request_interval_seconds=settings.massive_min_request_interval_seconds,
        max_retries=settings.massive_max_retries,
        rate_limit_backoff_seconds=settings.massive_rate_limit_backoff_seconds,
    ) as client:
        chunks_by_year: dict[int, list[tuple[str, str]]] = {}
        for chunk_start, chunk_end in _month_chunks(start=start, end=end):
            chunks_by_year.setdefault(date.fromisoformat(chunk_start).year, []).append(
                (chunk_start, chunk_end)
            )

        for year, year_chunks in sorted(chunks_by_year.items()):
            year_stats = _new_progress_stats()
            for ticker in PAPER_FETCH_MASSIVE_TICKERS:
                safe_ticker = _safe_name(ticker)
                for chunk_start, chunk_end in year_chunks:
                    chunk_date = date.fromisoformat(chunk_start)
                    _add_stat(year_stats, "months")
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
                        cached_records = _filter_records_by_range(
                            _read_parquet_records(path),
                            start=chunk_start,
                            end=chunk_end,
                            date_fields=("bar_date_et", "observation_date"),
                        )
                        daily_records.extend(cached_records)
                        _add_stat(year_stats, "cache_hits")
                        _add_stat(year_stats, "rows", len(cached_records))
                        continue
                    if _unavailable_marker_covers(unavailable_path, chunk_start, chunk_end):
                        _add_stat(year_stats, "unavailable")
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
                        _add_stat(year_stats, "unavailable")
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
                    result = atomic_write_parquet(
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
                    _add_stat(year_stats, "fetched")
                    _add_stat(year_stats, "rows", result.rows)
                    daily_records.extend(normalized)
            _log_year_stats("Massive daily", year, year_stats)

        for year, year_chunks in sorted(chunks_by_year.items()):
            year_stats = _new_progress_stats()
            for chunk_start, chunk_end in year_chunks:
                chunk_date = date.fromisoformat(chunk_start)
                _add_stat(year_stats, "months")
                feature_path = cache_path(
                    silver_root,
                    dataset="massive_spy_minute_features",
                    schema_version=SPY_MINUTE_FEATURE_SCHEMA.version,
                    year=chunk_date.year,
                    month=chunk_date.month,
                    extra_partitions={"ticker": _safe_name(settings.massive_minute_ticker)},
                )
                unavailable_path = feature_path.with_suffix(".unavailable.json")
                if feature_path.exists() and _cache_covers_range(
                    feature_path, chunk_start, chunk_end
                ):
                    cached_records = _filter_records_by_range(
                        _read_parquet_records(feature_path),
                        start=chunk_start,
                        end=chunk_end,
                        date_fields=("bar_date_et", "observation_date"),
                    )
                    spy_feature_records.extend(cached_records)
                    _add_stat(year_stats, "cache_hits")
                    _add_stat(year_stats, "rows", len(cached_records))
                    continue
                if _unavailable_marker_covers(unavailable_path, chunk_start, chunk_end):
                    _add_stat(year_stats, "unavailable")
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
                    _add_stat(year_stats, "unavailable")
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
                result = atomic_write_parquet(
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
                _add_stat(year_stats, "fetched")
                _add_stat(year_stats, "rows", result.rows)
                spy_feature_records.extend(features)
            _log_year_stats("SPY minute-derived", year, year_stats)
    return daily_records, spy_feature_records


def _fetch_cboe_paper_predictors(
    *,
    settings: Settings,
    start: str,
    end: str,
    downloaded_at_utc: datetime,
) -> list[dict[str, object]]:  # pragma: no cover - vendor path
    symbols = settings.cboe_vol_index_symbol_list()
    if not symbols:
        return []
    safe_symbols = "_".join(_safe_name(symbol) for symbol in symbols)
    bronze_path = (
        settings.data_dir
        / "bronze"
        / "cboe_vol_indices"
        / "schema_version=1"
        / f"symbols={safe_symbols}"
        / "payload.json"
    )
    silver_path = (
        settings.data_dir
        / "silver"
        / "cboe_vol_indices"
        / "schema_version=1"
        / f"symbols={safe_symbols}"
        / "daily.parquet"
    )
    if silver_path.exists() and _cache_covers_range(silver_path, start, end):
        _paper_log(f"Cboe volatility cache hit symbols={','.join(symbols)}")
        return _filter_records_by_range(
            _read_parquet_records(silver_path),
            start=start,
            end=end,
            date_fields=("observation_date",),
        )

    with CboeClient(
        base_url=settings.cboe_base_url,
        timeout_seconds=settings.cboe_request_timeout_seconds,
    ) as client:
        payloads = [client.fetch_vol_index_csv(symbol) for symbol in symbols]

    records: list[dict[str, object]] = []
    for payload in payloads:
        records.extend(
            row
            for row in normalize_cboe_vol_index_rows(
                symbol=payload.symbol,
                rows=payload.rows,
                raw_header=payload.raw_header,
                research_download_ts_utc=downloaded_at_utc,
                us_timezone=settings.project_timezone_us,
            )
            if start <= str(row["observation_date"]) <= end
        )
    _write_json(
        bronze_path,
        {
            "source": "cboe",
            "base_url": settings.cboe_base_url,
            "downloaded_at_utc": downloaded_at_utc.isoformat(),
            "requested_range": [start, end],
            "symbols": [
                {
                    "symbol": payload.symbol,
                    "path": payload.path,
                    "http_status": payload.http_status,
                    "raw_header": payload.raw_header,
                    "row_count": len(payload.rows),
                    "raw_csv": payload.raw_csv,
                }
                for payload in payloads
            ],
            "note": "Raw headers are retained because Cboe historical CSV headers drift.",
        },
    )
    atomic_write_parquet(
        silver_path,
        records,
        metadata={
            "source": "cboe",
            "symbols": list(symbols),
            "requested_range": [start, end],
            "raw_headers": [payload.raw_header for payload in payloads],
        },
    )
    _paper_log(f"Cboe volatility fetched symbols={','.join(symbols)} rows={len(records)}")
    return records


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
        for series_id in PAPER_FETCH_FRED_SERIES:
            _paper_log(f"FRED series start: {series_id}")
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
                records.extend(
                    _filter_records_by_range(
                        _read_parquet_records(path),
                        start=start,
                        end=end,
                        date_fields=("observation_date",),
                    )
                )
                _paper_log(f"FRED cache hit {series_id}")
                continue
            ttl_status = "missing"
            if path.exists():
                ttl_status = (
                    "stale_at_run_start"
                    if not is_fred_cache_fresh_at_run_start(
                        metadata,
                        run_start_utc=ttl_decision_ts,
                        ttl_days=FRED_CACHE_TTL_DAYS,
                    )
                    else "range_miss"
                )
            _paper_log(f"FRED fetching {series_id}: {ttl_status}")
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
            result = atomic_write_parquet(
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
            _paper_log(f"FRED wrote {series_id}: {result.rows} rows")
            records.extend(normalized)
    return records


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
    note = (
        "Visible notes: paper-candidate artifact; lower FZ loss is better; "
        "inference artifacts use block-bootstrap DM and HLN Tmax MCS; "
        "common-sample status is recorded in metrics metadata."
    )
    lines.extend(["\\midrule", f"\\multicolumn{{6}}{{l}}{{\\footnotesize {note}}} \\\\"])
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
        (
            str(row["model_name"]),
            str(row.get("target_family") or "full_gap_settle_to_open"),
            str(row.get("information_set") or "target_history_only"),
            _required_float(row["tail_level"]),
            str(row.get("refit_frequency") or ""),
        )
        for row in [*forecasts, *diagnostics, *failures]
        if "model_name" in row and "tail_level" in row
    }
    for model_name, target_family, information_set, tail_level, refit_frequency in sorted(keys):
        shard_dir = shard_root / _forecast_shard_id(
            model_name,
            tail_level,
            target_family=target_family,
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
                and str(row.get("information_set") or "target_history_only") == information_set
                and _required_float(row["tail_level"]) == tail_level
                and str(row.get("refit_frequency") or "") == refit_frequency
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
                "target_family": target_family,
                "information_set": information_set,
                "tail_level": tail_level,
                "refit_frequency": refit_frequency or None,
                "shard_id": _forecast_shard_id(
                    model_name,
                    tail_level,
                    target_family=target_family,
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
    information_set: str = "target_history_only",
    refit_frequency: str | None = None,
) -> str:
    parts = [
        f"model={_safe_name(model_name)}",
        f"target={_safe_name(target_family)}",
        f"info={_safe_name(information_set)}",
        f"tail={tail_level:.3f}".replace(".", "_"),
    ]
    if refit_frequency:
        parts.append(f"refit={_safe_name(refit_frequency)}")
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
    if field.startswith("fx_usdjpy_"):
        return "canonical USDJPY FX control using timestamp-safe FRED H.10 availability"
    if field.endswith("_days"):
        return "timestamp-safe source staleness or release-lag diagnostic used as a predictor"
    if field.endswith("_return"):
        return "close-to-close log return frozen at U.S. close information set"
    if field.endswith("_range"):
        return "log high-low range over the source bar window"
    if field.endswith("_diff"):
        return "first difference of daily source value"
    if field.endswith("_level"):
        return "daily source level with conservative research availability semantics"
    if field.startswith("spy_late_"):
        return "SPY late-session minute-bar feature frozen at the U.S. close cutoff"
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
