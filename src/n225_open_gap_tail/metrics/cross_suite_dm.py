from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.config.runtime import (
    BOOTSTRAP_REPS,
    INFERENCE_RANDOM_SEED,
    ML_TAIL_MODEL_NAMES,
    ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
    ML_TAIL_POT_GPD_UNIBM_MODEL,
    RESULT_MATRIX_LOSS_FAMILIES,
    RESULT_MATRIX_MIN_DM_EXCEPTIONS,
    RESULT_MATRIX_MIN_DM_ROWS,
    _optional_float,
)
from n225_open_gap_tail.metrics.admissibility import (
    PASS_ALL_INFORMATION_SETS,
    pass_all_lgbm_model_names,
    select_external_references,
)
from n225_open_gap_tail.metrics.result_matrix_grouping import (
    _result_matrix_group_payload,
    _result_row_eligible,
)
from n225_open_gap_tail.metrics.result_matrix_scoring import (
    _build_result_matrix_dm_records,
    _build_result_matrix_group,
)
from n225_open_gap_tail.metrics.stat_utils import (
    forecast_eligible,
    fz_loss,
    index_forecast_sessions,
    moving_block_one_sided_pvalue,
)

C_INFORMATION_SET = "japan_only_plus_us_close_core_plus_japan_proxy"
LGBM_STANDARD_PLAIN_MLE_C_LABEL = f"{display_model_label(ML_TAIL_POT_GPD_PLAIN_MLE_MODEL)} (C)"
LGBM_STANDARD_UNIBM_C_LABEL = f"{display_model_label(ML_TAIL_POT_GPD_UNIBM_MODEL)} (C)"
CROSS_SUITE_DM_MODEL_SPECS = (
    ("GJR-GARCH-EVT", "benchmark", "gjr_garch_evt", "target_history_only"),
    (
        LGBM_STANDARD_PLAIN_MLE_C_LABEL,
        "ml_tail",
        ML_TAIL_POT_GPD_PLAIN_MLE_MODEL,
        C_INFORMATION_SET,
    ),
    (
        LGBM_STANDARD_UNIBM_C_LABEL,
        "ml_tail",
        ML_TAIL_POT_GPD_UNIBM_MODEL,
        C_INFORMATION_SET,
    ),
)


def build_screened_comparison_artifacts(
    forecasts: list[dict[str, object]],
    native_metrics: pl.DataFrame,
    *,
    ml_model_names: tuple[str, ...] = ML_TAIL_MODEL_NAMES,
) -> dict[str, list[dict[str, object]]]:
    """Current Q1--Q13 comparisons; fixed-C helpers below serve legacy exports only."""
    selection = select_external_references(forecasts, native_metrics)
    admitted = pass_all_lgbm_model_names(native_metrics, model_order=ml_model_names)
    scopes = {
        (str(row.get("target_family") or "full_gap_settle_to_open"), float(str(row["tail_level"])))
        for row in forecasts
    }
    if len(scopes) != 1:
        raise ValueError("Screened comparison input must contain one target family and tail level")
    target, level = next(iter(scopes))
    matrix: list[dict[str, object]] = []
    audit: list[dict[str, object]] = []
    dm: list[dict[str, object]] = []
    for stage, models in (("initial", ml_model_names), ("post_gate", admitted)):
        for reference in selection["references"]:
            side = str(reference["tail_side"])
            ref = reference["model_name"]
            for info in PASS_ALL_INFORMATION_SETS:
                for loss_family in RESULT_MATRIX_LOSS_FAMILIES:
                    if ref is None or not models:
                        audit.append(
                            {
                                "comparison_family": f"{stage}_cross_suite",
                                "tail_side": side,
                                "information_set": info,
                                "loss_family": loss_family,
                                "common_n": 0,
                                "status": "unavailable_external_reference"
                                if ref is None
                                else "unavailable_no_admissible_ml_models",
                            }
                        )
                        continue
                    entities = [str(ref), *models]
                    by_entity: dict[str, dict[str, dict[str, object]]] = {
                        model: {} for model in entities
                    }
                    for row in forecasts:
                        model = str(row["model_name"])
                        expected_info = "target_history_only" if model == ref else info
                        if (
                            model not in entities
                            or row.get("tail_side") != side
                            or row.get("information_set") != expected_info
                            or not _result_row_eligible(row, loss_family)
                        ):
                            continue
                        day = str(row["forecast_date"])
                        if day in by_entity[model]:
                            raise ValueError(f"Duplicate comparison forecast for {model} on {day}")
                        by_entity[model][day] = row
                    common = sorted(set.intersection(*(set(rows) for rows in by_entity.values())))
                    for day in common:
                        if (
                            len(
                                {
                                    float(str(rows[day]["realized_loss"]))
                                    for rows in by_entity.values()
                                }
                            )
                            != 1
                        ):
                            raise ValueError(f"Inconsistent comparison target on {day}")
                    group = _result_matrix_group_payload(
                        key=(target, side, info, level, ""),
                        entities=entities,
                        entity_field="model_name",
                        entity_rows=by_entity,
                        common_dates=common,
                    )
                    group["missing_entities"] = [
                        model for model, rows in by_entity.items() if not rows
                    ]
                    family = f"{stage}_cross_suite"
                    rows, sample = _build_result_matrix_group(
                        group=group,
                        loss_family=loss_family,
                        comparison_family=family,
                        comparison_axis="model_family",
                        claim_scope="exploratory_same_oos_selection",
                        primary_claim_allowed=False,
                    )
                    for row in rows:
                        row["external_reference"] = ref
                        row["source_information_set"] = (
                            "target_history_only" if row["model_name"] == ref else info
                        )
                    matrix.extend(rows)
                    audit.append(sample)
                    dm.extend(
                        _build_result_matrix_dm_records(
                            group=group,
                            loss_family=loss_family,
                            comparison_family=family,
                            comparison_axis="model_family",
                            baseline_entity=str(ref),
                            entity_field="model_name",
                        )
                    )
    return {**selection, "matrix": matrix, "sample_audit": audit, "dm": dm}


def cross_suite_dm_loss_rows(run_dir: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    panel_path = run_dir / "panel" / "modeling_panel.parquet"
    session_dates = (
        pl.read_parquet(panel_path, columns=["forecast_date"])["forecast_date"]
        .cast(pl.String)
        .to_list()
        if panel_path.exists()
        else None
    )
    forecast_specs = (
        (run_dir / "forecasts" / "benchmark_forecasts.parquet", "benchmark"),
        (run_dir / "forecasts" / "ml_tail_forecasts.parquet", "ml_tail"),
    )
    required = {
        "forecast_date",
        "tail_side",
        "model_name",
        "information_set",
        "tail_level",
        "realized_loss",
        "var_forecast",
        "es_forecast",
    }
    for path, suite in forecast_specs:
        frame = _read_optional_parquet(path)
        if frame.is_empty() or not required.issubset(frame.columns):
            continue
        frame = pl.from_dicts(
            index_forecast_sessions(frame.to_dicts(), session_dates=session_dates),
            infer_schema_length=None,
        )
        frame = _valid_forecast_rows(frame)
        rows: list[dict[str, object]] = []
        for label, spec_suite, model_name, information_set in CROSS_SUITE_DM_MODEL_SPECS:
            if spec_suite != suite:
                continue
            selected = frame.filter(
                (pl.col("model_name") == model_name)
                & (pl.col("information_set") == information_set)
            )
            for row in selected.iter_rows(named=True):
                loss = _optional_float(row.get("realized_loss"))
                var = _optional_float(row.get("var_forecast"))
                es = _optional_float(row.get("es_forecast"))
                tail_level = _optional_float(row.get("tail_level"))
                if loss is None or var is None or es is None or tail_level is None:
                    continue
                score = fz_loss(loss, var, es, tail_level)
                if not np.isfinite(score):
                    continue
                rows.append(
                    {
                        "plot_label": label,
                        "suite": suite,
                        "model_name": model_name,
                        "information_set": information_set,
                        "forecast_date": str(row["forecast_date"]),
                        "target_session_index": row.get("target_session_index"),
                        "target_family": row.get("target_family"),
                        "tail_side": row.get("tail_side"),
                        "tail_level": tail_level,
                        "realized_loss": loss,
                        "var_forecast": var,
                        "fz_loss": score,
                    }
                )
        if rows:
            frames.append(pl.from_dicts(rows, infer_schema_length=None))
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def cross_suite_dm_records(loss_rows: pl.DataFrame, tail_side: str) -> list[dict[str, object]]:
    if loss_rows.is_empty() or "tail_side" not in loss_rows.columns:
        return []
    loss_rows = pl.from_dicts(
        index_forecast_sessions(loss_rows.to_dicts()), infer_schema_length=None
    )
    tail_rows = loss_rows.filter(pl.col("tail_side") == tail_side)
    if tail_rows.is_empty():
        return []
    labels = [spec[0] for spec in CROSS_SUITE_DM_MODEL_SPECS]
    date_sets = [
        {
            str(value)
            for value in tail_rows.filter(pl.col("plot_label") == label)[
                "forecast_date"
            ].drop_nulls()
        }
        for label in labels
    ]
    common_dates = sorted(set.intersection(*date_sets)) if all(date_sets) else []
    row_by_label_date = {
        (str(row["plot_label"]), str(row["forecast_date"])): row
        for row in tail_rows.iter_rows(named=True)
    }
    return [
        _pair_record(
            candidate_label=candidate_label,
            anchor_label=anchor_label,
            common_dates=common_dates,
            row_by_label_date=row_by_label_date,
            tail_side=tail_side,
        )
        for candidate_label in labels
        for anchor_label in labels
        if candidate_label != anchor_label
    ]


def cross_suite_dm_records_from_run(run_dir: Path) -> list[dict[str, object]]:
    loss_rows = cross_suite_dm_loss_rows(run_dir)
    records: list[dict[str, object]] = []
    for tail_side in ("left_tail", "right_tail"):
        records.extend(cross_suite_dm_records(loss_rows, tail_side))
    return records


def cross_suite_dm_gate_status(*, common_n: int, joint_exception_count: int) -> str:
    if common_n == 0:
        return "unavailable_no_global_common_sample"
    if common_n < RESULT_MATRIX_MIN_DM_ROWS:
        return "unavailable_insufficient_common_rows_for_inference"
    if joint_exception_count < RESULT_MATRIX_MIN_DM_EXCEPTIONS:
        return "unavailable_insufficient_tail_events_for_inference"
    return "ok_block_bootstrap_dm"


def _pair_record(
    *,
    candidate_label: str,
    anchor_label: str,
    common_dates: list[str],
    row_by_label_date: dict[tuple[str, str], dict[str, object]],
    tail_side: str,
) -> dict[str, object]:
    diffs: list[float] = []
    session_indices: list[int | None] = []
    joint_exception_count = 0
    for forecast_date in common_dates:
        candidate = row_by_label_date.get((candidate_label, forecast_date))
        anchor = row_by_label_date.get((anchor_label, forecast_date))
        if candidate is None or anchor is None:
            continue
        candidate_fz = _optional_float(candidate.get("fz_loss"))
        anchor_fz = _optional_float(anchor.get("fz_loss"))
        if candidate_fz is not None and anchor_fz is not None:
            diffs.append(candidate_fz - anchor_fz)
            index = _optional_float(anchor.get("target_session_index"))
            session_indices.append(int(index) if index is not None else None)
        joint_exception_count += int(_breached(candidate) or _breached(anchor))
    diff_array = np.asarray(diffs, dtype=float)
    diff_array = diff_array[np.isfinite(diff_array)]
    paired_rows = int(diff_array.size)
    mean_diff = float(np.mean(diff_array)) if paired_rows else None
    block_length = max(5, round(paired_rows ** (1.0 / 3.0))) if paired_rows else None
    inference_status = cross_suite_dm_gate_status(
        common_n=len(common_dates), joint_exception_count=joint_exception_count
    )
    pvalue = (
        moving_block_one_sided_pvalue(
            diff_array,
            observed_mean=mean_diff,
            reps=BOOTSTRAP_REPS,
            block_length=int(block_length),
            rng=np.random.default_rng(INFERENCE_RANDOM_SEED),
            session_indices=session_indices,
        )
        if inference_status == "ok_block_bootstrap_dm"
        and mean_diff is not None
        and block_length is not None
        else None
    )
    if inference_status == "ok_block_bootstrap_dm" and pvalue is None:
        inference_status = "unavailable_bootstrap_time_axis_or_sample"
    return {
        "comparison_family": "pass_all_cross_suite_pairwise",
        "loss_family": "var_es_fz_loss",
        "tail_side": tail_side,
        "candidate_label": candidate_label,
        "anchor_label": anchor_label,
        "common_n": len(common_dates),
        "paired_rows": paired_rows,
        "joint_exception_count": joint_exception_count,
        "mean_fz_loss_diff_candidate_minus_anchor": mean_diff,
        "pvalue_one_sided": pvalue,
        "reject_10pct": pvalue is not None and pvalue < 0.10,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "bootstrap_seed": INFERENCE_RANDOM_SEED,
        "block_length": block_length,
        "alternative": "candidate_mean_fz_loss_less_than_anchor",
        "null_hypothesis": "E[FZ_candidate_minus_anchor] >= 0",
        "inference_status": inference_status,
    }


def _breached(row: dict[str, object]) -> bool:
    loss = _optional_float(row.get("realized_loss"))
    var = _optional_float(row.get("var_forecast"))
    return loss is not None and var is not None and loss > var


def _valid_forecast_rows(frame: pl.DataFrame) -> pl.DataFrame:
    return (
        frame.filter(pl.Series([forecast_eligible(row) for row in frame.iter_rows(named=True)]))
        if not frame.is_empty()
        else frame
    )


def _read_optional_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:
        return pl.DataFrame()
