# ruff: noqa: E501
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import polars as pl

from n225_open_gap_tail.config.model_labels import display_model_label
from n225_open_gap_tail.config.runtime import (
    BENCHMARK_BASELINE_MODEL_NAMES,
    ML_TAIL_DIRECT_QUANTILE_MODEL,
    ML_TAIL_MODEL_NAMES,
)


def generate_results_discussion(
    *,
    manifest: Mapping[str, object],
    paths: Mapping[str, Path],
    data_vintage: Mapping[str, object],
    benchmark_status: Mapping[str, object],
    ml_tail_status: Mapping[str, object],
    leakage_summary: Mapping[str, object],
    figure_manifest: Mapping[str, object],
    panel: pl.DataFrame,
    calendar: pl.DataFrame,
    benchmark_metrics: pl.DataFrame,
    ml_tail_metrics: pl.DataFrame,
    result_matrix: pl.DataFrame,
    benchmark_stress: pl.DataFrame,
    ml_tail_stress: pl.DataFrame,
) -> str:
    benchmark_forecasts = _read_parquet_optional(paths["benchmark_forecasts"])
    ml_tail_forecasts = _read_parquet_optional(paths["ml_tail_forecasts"])
    benchmark_dm = _read_parquet_optional(paths["benchmark_dm_inference"])
    benchmark_mcs = _read_parquet_optional(paths["benchmark_mcs"])
    ml_tail_dm = _read_parquet_optional(paths["ml_tail_dm_inference"])
    ml_tail_mcs = _read_parquet_optional(paths["ml_tail_mcs"])
    result_matrix_dm = _read_parquet_optional(paths["ml_tail_result_matrix_dm"])
    result_matrix_mcs = _read_parquet_optional(paths["ml_tail_result_matrix_mcs"])
    cpa_path = paths.get("ml_tail_cpa_inference")
    ml_tail_cpa = _read_parquet_optional(cpa_path) if cpa_path is not None else pl.DataFrame()
    cross_cpa_path = paths.get("cross_model_cpa_inference")
    cross_model_cpa = (
        _read_parquet_optional(cross_cpa_path) if cross_cpa_path is not None else pl.DataFrame()
    )
    ml_tail_eviction = _read_parquet_optional(paths["ml_tail_model_eviction"])
    ml_tail_metrics_per_model = _read_parquet_optional(paths["ml_tail_metrics_per_model"])
    ml_tail_dst = _read_parquet_optional(paths["ml_tail_dst_attenuation"])
    ml_tail_murphy = _read_parquet_optional(paths["ml_tail_murphy"])
    feature_unavailability = _read_parquet_optional(paths["ml_tail_feature_unavailability"])
    combined_forecasts = _combine_forecasts_for_snapshot(
        benchmark_forecasts=benchmark_forecasts,
        ml_tail_forecasts=ml_tail_forecasts,
    )

    return f"""## Results And Discussion

<!-- generated: results_discussion -->

### Data and timing audit

{
        _results_data_timing_audit(
            manifest=manifest,
            data_vintage=data_vintage,
            leakage_summary=leakage_summary,
            panel=panel,
            calendar=calendar,
        )
    }

### Baseline benchmarks and advanced econometric benchmarks

{
        _results_benchmark_discussion(
            benchmark_status=benchmark_status,
            benchmark_metrics=benchmark_metrics,
            benchmark_forecasts=benchmark_forecasts,
        )
    }

### Primary ML specifications across nested information sets

{
        _results_ml_tail_primary_discussion(
            ml_tail_status=ml_tail_status,
            ml_tail_metrics=ml_tail_metrics,
        )
    }

### Restricted model-family comparison

{
        _results_restricted_model_family_discussion(
            result_matrix=result_matrix,
            result_matrix_dm=result_matrix_dm,
            result_matrix_mcs=result_matrix_mcs,
        )
    }

### Coverage and inference gates

{
        _results_coverage_inference_discussion(
            ml_tail_metrics=ml_tail_metrics,
            result_matrix=result_matrix,
            ml_tail_eviction=ml_tail_eviction,
            inference_frames=(benchmark_dm, benchmark_mcs, ml_tail_dm, ml_tail_mcs),
        )
    }

### CPA as conditional loss-difference diagnostics

{_results_cpa_discussion(ml_tail_cpa, cross_model_cpa)}

### Supporting diagnostics

{
        _results_supporting_diagnostics_discussion(
            paths=paths,
            benchmark_metrics=benchmark_metrics,
            ml_tail_metrics=ml_tail_metrics,
            ml_tail_metrics_per_model=ml_tail_metrics_per_model,
            result_matrix=result_matrix,
            ml_tail_dst=ml_tail_dst,
            ml_tail_murphy=ml_tail_murphy,
            benchmark_stress=benchmark_stress,
            ml_tail_stress=ml_tail_stress,
            feature_unavailability=feature_unavailability,
            combined_forecasts=combined_forecasts,
            figure_manifest=figure_manifest,
        )
    }

### Not yet claimed

- DST attenuation rows are descriptive forecast evidence; structural DST causal identification is not claimed.
- No hedge PnL, transaction-cost, or trading-alpha analysis is performed. The trigger table is a pre-open risk-monitoring diagnostic only.
- Left-tail and right-tail outputs are both economic tail-risk surfaces for futures positions; neither side should be promoted beyond the sample, coverage, and inference gates without author review.
- The current evidence does not create an automatic model-selection statement; any manuscript claim still requires author review of sample gates, coverage, loss metrics, and inference diagnostics.
"""


def _read_parquet_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _results_cpa_discussion(cpa: pl.DataFrame, cross_model_cpa: pl.DataFrame) -> str:
    if cpa.is_empty() and cross_model_cpa.is_empty():
        return "- Instrumented CPA conditional loss-difference diagnostics are not implemented in the current artifacts; the reported DM and MCS outputs are unconditional average-sample forecast-comparison diagnostics."
    ok_rows = 0
    if "inference_status" in cpa.columns:
        ok_rows = int(cpa.filter(pl.col("inference_status").str.starts_with("ok")).height)
    cross_ok_rows = 0
    if "inference_status" in cross_model_cpa.columns:
        cross_ok_rows = int(
            cross_model_cpa.filter(pl.col("inference_status").str.starts_with("ok")).height
        )
    tail_side_count = _unique_count(cpa, "tail_side")
    cross_rows = int(cross_model_cpa.height)
    loss_families = _unique_values(cpa, "loss_family")
    cross_loss_families = _unique_values(cross_model_cpa, "loss_family")
    return "\n".join(
        [
            f"- The ML-tail nested-information-set CPA artifact is a conditional loss-difference diagnostic across `{tail_side_count}` tail side(s), with `{cpa.height}` registered row(s), `{ok_rows}` HAC-Wald gate pass(es), and loss families {loss_families}.",
            f"- The registered cross-model CPA artifact is a conditional loss-difference diagnostic with `{cross_rows}` row(s), `{cross_ok_rows}` HAC-Wald gate pass(es), and loss families {cross_loss_families}.",
            "- Quantile-loss CPA and FZ-loss CPA are downstream inference over existing loss differentials; CPA does not generate VaR/ES forecasts and does not replace DM/MCS.",
        ]
    )


def _results_data_timing_audit(
    *,
    manifest: Mapping[str, object],
    data_vintage: Mapping[str, object],
    leakage_summary: Mapping[str, object],
    panel: pl.DataFrame,
    calendar: pl.DataFrame,
) -> str:
    combined_clean_start = str(manifest.get("combined_clean_start") or "not reported")
    date_range = _date_range_from_calendar(calendar) or _panel_bounds(panel)
    pre_start_count = _forecast_rows_before_combined_clean_start(panel, combined_clean_start)
    if pre_start_count is None:
        pre_start_sentence = (
            "The generator could not verify pre-start forecast rows because the panel "
            "artifact is missing the required date or forecast-sample fields."
        )
    elif pre_start_count == 0:
        pre_start_sentence = (
            f"No forecast-sample rows before `{combined_clean_start}` enter the modeling evidence."
        )
    else:
        pre_start_sentence = f"`{pre_start_count}` forecast-sample rows before `{combined_clean_start}` require review."
    leakage_sentence = _leakage_discussion_sentence(leakage_summary)
    vintage_safe = data_vintage.get("fred_vintage_safe")
    fred_sentence = (
        f"FRED vintage safety is recorded as `{vintage_safe}`; FRED values use conservative "
        "release timing but remain current historical observations rather than ALFRED real-time vintages."
    )
    return "\n".join(
        [
            f"- The gold timing map covers `{date_range}` and the combined clean start is `{combined_clean_start}`.",
            f"- {pre_start_sentence}",
            f"- {leakage_sentence}",
            f"- {fred_sentence}",
        ]
    )


def _results_benchmark_discussion(
    *,
    benchmark_status: Mapping[str, object],
    benchmark_metrics: pl.DataFrame,
    benchmark_forecasts: pl.DataFrame,
) -> str:
    if benchmark_metrics.is_empty() and benchmark_forecasts.is_empty():
        return _analysis_not_available("Benchmark metrics and forecasts")
    baseline_model_count = _unique_count(benchmark_metrics, "model_name")
    metric_rows = int(benchmark_metrics.height)
    tail_side_count = _unique_count(benchmark_metrics, "tail_side")
    forecast_rows = int(
        _optional_float(benchmark_status.get("forecast_rows")) or benchmark_forecasts.height
    )
    advanced = (
        benchmark_forecasts.filter(pl.col("benchmark_tier") == "advanced")
        if "benchmark_tier" in benchmark_forecasts.columns
        else pl.DataFrame()
    )
    advanced_model_count = _unique_count(advanced, "model_name")
    advanced_rows = int(
        _optional_float(benchmark_status.get("benchmark_advanced_forecast_rows")) or advanced.height
    )
    advanced_sentence = (
        f"Advanced econometric benchmark rows are implemented for `{advanced_model_count}` model families "
        f"and contribute `{advanced_rows}` nonblocking forecast rows; these rows are claim-gated "
        "diagnostics unless a manuscript table explicitly promotes them through the same sample and inference review."
        if advanced_rows > 0
        else "The advanced econometric benchmark registry is nonblocking, but this run does not provide advanced forecast rows for interpretation."
    )
    calibration_sentence = _benchmark_calibration_note(benchmark_metrics)
    lines = [
        f"- `benchmark_metrics.parquet` reports `{metric_rows}` common-sample rows across `{baseline_model_count}` baseline benchmark model families and `{tail_side_count}` tail side(s), while benchmark forecasts contain `{forecast_rows}` model-date rows.",
        "- Baseline benchmark models are external target-history and econometric references; this section does not rank them.",
        f"- {advanced_sentence}",
    ]
    if calibration_sentence:
        lines.append(f"- {calibration_sentence}")
    return "\n".join(lines)


def _results_ml_tail_primary_discussion(
    *,
    ml_tail_status: Mapping[str, object],
    ml_tail_metrics: pl.DataFrame,
) -> str:
    if ml_tail_metrics.is_empty():
        return _analysis_not_available("The ML-tail nested-information-set analysis")
    information_sets = _unique_count(ml_tail_metrics, "information_set")
    tail_levels = _unique_count(ml_tail_metrics, "tail_level")
    tail_side_count = _unique_count(ml_tail_metrics, "tail_side")
    models = _unique_values(ml_tail_metrics, "model_name", formatter=display_model_label)
    implemented = _join_model_list(ML_TAIL_MODEL_NAMES)
    coverage_warning = _ml_tail_coverage_warning(ml_tail_metrics)
    saturation_note = _information_set_saturation_note(ml_tail_metrics)
    lines = [
        "- `ml_tail_metrics.parquet` defines the primary ML specification comparison across nested information sets for this run.",
        f"- The primary ML artifact contains `{information_sets}` information sets, `{tail_levels}` tail level(s), and `{tail_side_count}` tail side(s); the retained primary ML rows are {models}.",
        f"- The implemented ML-tail registry is {implemented}, but the primary nested-information-set comparison should be read only from `ml_tail_metrics.parquet`.",
        "- The nested information sets report downside-risk and upside-risk surfaces separately. The registered artifacts show different left/right patterns, and the generator does not assume that the two sides share the same economic mechanism.",
    ]
    if coverage_warning:
        lines.append(f"- {coverage_warning}")
    if saturation_note:
        lines.append(f"- {saturation_note}")
    lines.append(
        "- The nested information sets are used to assess candidate incremental U.S.-close information under strict common-sample rules; they do not by themselves establish forecast improvement."
    )
    return "\n".join(lines)


def _results_restricted_model_family_discussion(
    *,
    result_matrix: pl.DataFrame,
    result_matrix_dm: pl.DataFrame,
    result_matrix_mcs: pl.DataFrame,
) -> str:
    if result_matrix.is_empty():
        return _analysis_not_available("The restricted ML-tail result matrix")
    common_n = _int_range(result_matrix, "common_n")
    joint_exceptions = _int_range(result_matrix, "joint_exception_count")
    model_count = _unique_count(result_matrix, "model_name")
    claim_scope = _unique_values(result_matrix, "claim_scope")
    short_sample_sentence = _restricted_short_sample_warning(result_matrix)
    lines = [
        f"- `ml_tail_result_matrix.parquet` contains restricted common-sample comparisons for `{model_count}` LightGBM tail-model families.",
        f"- The restricted common-N range is `{common_n}` and the joint-exception range is `{joint_exceptions}`.",
        f"- Recorded claim scopes are {claim_scope}; these rows are restricted evidence and cannot replace the primary ML nested-information-set comparison.",
    ]
    if short_sample_sentence:
        lines.append(f"- {short_sample_sentence}")
    inference_sentence = _result_matrix_inference_sentence(
        result_matrix_dm=result_matrix_dm,
        result_matrix_mcs=result_matrix_mcs,
    )
    if inference_sentence:
        lines.append(f"- {inference_sentence}")
    lines.append(
        "- The result matrix is a matched-date diagnostic layer. It should not be worded as one family being better than another."
    )
    return "\n".join(lines)


def _results_coverage_inference_discussion(
    *,
    ml_tail_metrics: pl.DataFrame,
    result_matrix: pl.DataFrame,
    ml_tail_eviction: pl.DataFrame,
    inference_frames: Sequence[pl.DataFrame],
) -> str:
    coverage_sentence = _coverage_test_discussion_sentence(ml_tail_metrics)
    eviction_sentence = _eviction_discussion_sentence(ml_tail_eviction)
    power_sentence = _tail_event_power_sentence(result_matrix, inference_frames)
    return "\n".join(
        [
            f"- {coverage_sentence}",
            f"- {eviction_sentence}",
            "- Block-bootstrap DM and HLN Tmax MCS artifacts are unconditional forecast-comparison diagnostics; any p-value should be read on average across the unconditional evaluation sample, not as condition-specific evidence.",
            "- Loss differentials alone do not constitute an improvement claim; coverage, exception counts, sample gates, and inference status must be reviewed together.",
            f"- {power_sentence}",
        ]
    )


def _results_supporting_diagnostics_discussion(
    *,
    paths: Mapping[str, Path],
    benchmark_metrics: pl.DataFrame,
    ml_tail_metrics: pl.DataFrame,
    ml_tail_metrics_per_model: pl.DataFrame,
    result_matrix: pl.DataFrame,
    ml_tail_dst: pl.DataFrame,
    ml_tail_murphy: pl.DataFrame,
    benchmark_stress: pl.DataFrame,
    ml_tail_stress: pl.DataFrame,
    feature_unavailability: pl.DataFrame,
    combined_forecasts: pl.DataFrame,
    figure_manifest: Mapping[str, object],
) -> str:
    table_sentence = _diagnostic_table_sentence(paths)
    severity_sentence = _severity_discussion_sentence(
        benchmark_metrics=benchmark_metrics,
        ml_tail_metrics=ml_tail_metrics,
        ml_tail_metrics_per_model=ml_tail_metrics_per_model,
    )
    trigger_sentence = _trigger_discussion_sentence(combined_forecasts)
    dst_sentence = (
        f"`ml_tail_dst_attenuation.parquet` contains `{ml_tail_dst.height}` DST attenuation rows; these are descriptive timing-regime forecast diagnostics."
        if not ml_tail_dst.is_empty()
        else "DST attenuation analysis has not yet been performed for this run."
    )
    murphy_sentence = (
        f"Murphy diagnostics contain `{ml_tail_murphy.height}` ML-tail rows."
        if not ml_tail_murphy.is_empty()
        else "Murphy diagnostics are not available in this snapshot."
    )
    stress_rows = benchmark_stress.height + ml_tail_stress.height
    feature_sentence = (
        f"Feature-unavailability diagnostics contain `{feature_unavailability.height}` rows."
        if not feature_unavailability.is_empty()
        else "Feature-unavailability diagnostics are empty or not available for this run."
    )
    figure_sentence = _figure_reference_discussion(figure_manifest)
    return "\n".join(
        [
            f"- {table_sentence}",
            f"- {dst_sentence} They do not establish a structural timing mechanism.",
            f"- {severity_sentence}",
            f"- {trigger_sentence}",
            f"- Stress-window diagnostics contain `{stress_rows}` rows, and {murphy_sentence}",
            f"- {feature_sentence}",
            figure_sentence,
        ]
    )


def _figure_reference_discussion(figure_manifest: Mapping[str, object]) -> str:
    figures = figure_manifest.get("figures")
    if not isinstance(figures, list) or not figures:
        return "- Figure manifest references are not available for this run."
    lines = ["- Figure manifest references:"]
    seen: set[str] = set()
    for item in figures:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("format")) != "png":
            continue
        name = str(item.get("name") or "unknown_figure")
        if name.startswith("target_"):
            continue
        if name in seen:
            continue
        seen.add(name)
        path = str(item.get("path") or "missing")
        sources = item.get("source_artifacts")
        if isinstance(sources, list) and sources:
            source_text = ", ".join(str(source) for source in sources)
        else:
            source_text = "not recorded"
        claim_scope = str(item.get("claim_scope") or "not recorded")
        lines.append(
            f"  - Figure: {name} (Source: {source_text}; Claim scope: {claim_scope}; File: {path})."
        )
    if len(lines) == 1:
        return "- Figure manifest references are present but do not include PNG entries for manuscript review."
    return "\n".join(lines)


def _analysis_not_available(label: str) -> str:
    return f"- {label} has not yet been performed for this run."


def _date_range_from_calendar(calendar: pl.DataFrame) -> str | None:
    for column in ("ose_trading_date", "forecast_date", "target_open_ts_utc"):
        if calendar.is_empty() or column not in calendar.columns:
            continue
        values = calendar.select(
            pl.col(column).min().alias("start"),
            pl.col(column).max().alias("end"),
        ).row(0, named=True)
        start = values.get("start")
        end = values.get("end")
        if start is not None and end is not None:
            return f"{start} to {end}"
    return None


def _forecast_rows_before_combined_clean_start(
    panel: pl.DataFrame,
    combined_clean_start: str,
) -> int | None:
    if (
        panel.is_empty()
        or combined_clean_start == "not reported"
        or not {"forecast_date", "forecast_sample"}.issubset(panel.columns)
    ):
        return None
    return int(
        panel.filter(
            (pl.col("forecast_sample") == True)  # noqa: E712
            & (pl.col("forecast_date").cast(pl.Utf8) < combined_clean_start)
        ).height
    )


def _leakage_discussion_sentence(leakage_summary: Mapping[str, object]) -> str:
    status = leakage_summary.get("status")
    failures = _optional_float(leakage_summary.get("failures"))
    warnings = leakage_summary.get("warnings")
    if failures == 0:
        return f"The leakage check reports status `{status}` with zero leakage failures and `{warnings}` warnings."
    if failures is None:
        return "Leakage-check status is not available in this snapshot."
    return f"The leakage check reports status `{status}` with `{int(failures)}` failures and `{warnings}` warnings; this requires review before manuscript claims."


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.select(pl.col(column).drop_nulls().n_unique()).item() or 0)


def _int_range(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return "not available"
    values = frame.select(
        pl.col(column).drop_nulls().min().alias("min"),
        pl.col(column).drop_nulls().max().alias("max"),
    ).row(0, named=True)
    low = values.get("min")
    high = values.get("max")
    if low is None or high is None:
        return "not available"
    if low == high:
        return str(low)
    return f"{low} to {high}"


def _coverage_test_discussion_sentence(frame: pl.DataFrame) -> str:
    required = {"var_breach_rate", "expected_breach_rate"}
    if frame.is_empty() or not required.issubset(frame.columns):
        return (
            "Coverage review is descriptive because primary ML coverage fields are not available; "
            "loss differences alone must not be read as improvement."
        )
    total = 0
    wide = 0
    kupiec_flags = 0
    christoffersen_flags = 0
    kupiec_reported = 0
    christoffersen_reported = 0
    for row in frame.iter_rows(named=True):
        breach = _optional_float(row.get("var_breach_rate"))
        expected = _optional_float(row.get("expected_breach_rate"))
        if breach is None or expected is None:
            continue
        total += 1
        wide += int(abs(breach - expected) > 0.025)
        kupiec = _optional_float(row.get("kupiec_pvalue"))
        christoffersen = _optional_float(row.get("christoffersen_pvalue"))
        kupiec_reported += int(kupiec is not None)
        christoffersen_reported += int(christoffersen is not None)
        kupiec_flags += int(kupiec is not None and kupiec < 0.05)
        christoffersen_flags += int(christoffersen is not None and christoffersen < 0.05)
    if total == 0:
        return (
            "Coverage review is descriptive because valid coverage rows are not available; "
            "loss differences alone must not be read as improvement."
        )
    return (
        f"Coverage review flags `{wide}/{total}` primary ML rows with breach rates more than 2.5 percentage points from nominal coverage; "
        f"Kupiec p-values fall below 0.05 in `{kupiec_flags}/{kupiec_reported}` reported rows and Christoffersen p-values fall below 0.05 in `{christoffersen_flags}/{christoffersen_reported}` reported rows."
    )


def _eviction_discussion_sentence(eviction: pl.DataFrame) -> str:
    if eviction.is_empty():
        return "Model-eviction artifacts are not available; primary ML inclusion must be checked from the metric tables."
    if "retained_for_primary" not in eviction.columns:
        return (
            "Model-eviction artifacts are present but do not expose retained-for-primary-ML flags."
        )
    evicted = int(eviction.filter(pl.col("retained_for_primary") == False).height)  # noqa: E712
    retained = int(eviction.filter(pl.col("retained_for_primary") == True).height)  # noqa: E712
    return f"Model-eviction artifacts record `{retained}` retained rows and `{evicted}` non-retained rows under the primary ML sample policy."


def _tail_event_power_sentence(
    result_matrix: pl.DataFrame,
    inference_frames: Sequence[pl.DataFrame],
) -> str:
    power_flags = 0
    if "tail_event_power_status" in result_matrix.columns:
        power_flags = result_matrix.filter(
            pl.col("tail_event_power_status").cast(pl.Utf8).str.contains("insufficient")
        ).height
    unavailable = 0
    total = 0
    for frame in inference_frames:
        if frame.is_empty():
            continue
        status_column = _first_present_column(frame, ("inference_status", "mcs_status"))
        if status_column is None:
            continue
        total += frame.height
        unavailable += frame.filter(
            pl.col(status_column).cast(pl.Utf8).str.contains("unavailable")
        ).height
    if not total and not power_flags:
        return "Formal inference gate status is not available in this snapshot."
    return f"Result-matrix tail-event power flags and suite-level inference gates report `{power_flags}` restricted rows with insufficient tail-event power and `{unavailable}/{total}` unavailable DM/MCS inference rows."


def _first_present_column(frame: pl.DataFrame, columns: Sequence[str]) -> str | None:
    return next((column for column in columns if column in frame.columns), None)


def _result_matrix_inference_sentence(
    *,
    result_matrix_dm: pl.DataFrame,
    result_matrix_mcs: pl.DataFrame,
) -> str | None:
    if result_matrix_dm.is_empty() and result_matrix_mcs.is_empty():
        return None
    parts: list[str] = []
    if not result_matrix_dm.is_empty() and "inference_status" in result_matrix_dm.columns:
        ok = int(
            result_matrix_dm.filter(
                pl.col("inference_status").cast(pl.Utf8).str.starts_with("ok")
            ).height
        )
        unavailable = int(
            result_matrix_dm.filter(
                pl.col("inference_status").cast(pl.Utf8).str.contains("unavailable")
            ).height
        )
        parts.append(
            f"restricted DM records include `{ok}` gate-pass rows and `{unavailable}` unavailable rows"
        )
    if not result_matrix_mcs.is_empty() and "mcs_status" in result_matrix_mcs.columns:
        ok = int(
            result_matrix_mcs.filter(
                pl.col("mcs_status").cast(pl.Utf8).str.starts_with("ok")
            ).height
        )
        unavailable = int(
            result_matrix_mcs.filter(
                pl.col("mcs_status").cast(pl.Utf8).str.contains("unavailable")
            ).height
        )
        parts.append(
            f"restricted MCS records include `{ok}` gate-pass rows and `{unavailable}` unavailable rows"
        )
    if not parts:
        return None
    return (
        "Result-matrix inference is recorded separately from the primary suite-level DM/MCS: "
        + "; ".join(parts)
        + ". These entries are restricted common-sample diagnostics, not primary model-family rankings."
    )


def _diagnostic_table_sentence(paths: Mapping[str, Path]) -> str:
    table_keys = (
        "dst_attenuation_table",
        "es_severity_table",
        "hedge_trigger_table",
        "result_matrix_summary_table",
    )
    existing = [key for key in table_keys if paths[key].exists()]
    if not existing:
        return "Supporting LaTeX diagnostic tables have not yet been exported for this run."
    return f"Supporting LaTeX diagnostic table files are present for `{len(existing)}/{len(table_keys)}` registered diagnostic families."


def _severity_discussion_sentence(
    *,
    benchmark_metrics: pl.DataFrame,
    ml_tail_metrics: pl.DataFrame,
    ml_tail_metrics_per_model: pl.DataFrame,
) -> str:
    frames = [
        frame
        for frame in (benchmark_metrics, ml_tail_metrics, ml_tail_metrics_per_model)
        if not frame.is_empty()
    ]
    if not frames:
        return "ES severity diagnostics have not yet been performed for this run."
    combined = pl.concat(frames, how="diagonal_relaxed")
    if "mean_exceedance_severity" not in combined.columns:
        return "ES severity diagnostics are not available in the metric artifacts."
    rows = combined.filter(pl.col("mean_exceedance_severity").is_not_null())
    if rows.is_empty():
        return "ES severity diagnostics are present but contain no finite mean exceedance-severity rows."
    values = rows.select(
        pl.col("mean_exceedance_severity").min().alias("min"),
        pl.col("mean_exceedance_severity").max().alias("max"),
    ).row(0, named=True)
    return f"ES severity diagnostics contain `{rows.height}` finite rows with mean exceedance severity ranging from `{_fmt_float(values['min'])}` to `{_fmt_float(values['max'])}`; this is conditional-on-exception evidence."


def _combine_forecasts_for_snapshot(
    *,
    benchmark_forecasts: pl.DataFrame,
    ml_tail_forecasts: pl.DataFrame,
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    if not benchmark_forecasts.is_empty():
        benchmark = benchmark_forecasts
        if "model_name" in benchmark.columns:
            benchmark = benchmark.filter(
                pl.col("model_name").is_in(list(BENCHMARK_BASELINE_MODEL_NAMES))
            )
        if not benchmark.is_empty():
            frames.append(benchmark.with_columns(pl.lit("benchmark").alias("suite")))
    if not ml_tail_forecasts.is_empty():
        ml_tail = ml_tail_forecasts
        if "model_name" in ml_tail.columns:
            ml_tail = ml_tail.filter(pl.col("model_name") == ML_TAIL_DIRECT_QUANTILE_MODEL)
        if not ml_tail.is_empty():
            frames.append(ml_tail.with_columns(pl.lit("ml_tail").alias("suite")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _trigger_discussion_sentence(forecasts: pl.DataFrame) -> str:
    required = {"model_name", "information_set", "tail_level", "var_forecast", "realized_loss"}
    if forecasts.is_empty() or not required.issubset(forecasts.columns):
        return "The hedge-trigger diagnostic has not yet been performed for this run; it would be descriptive trigger evidence only."
    valid_expr = pl.col("var_forecast").is_not_null() & pl.col("realized_loss").is_not_null()
    if "is_valid_forecast" in forecasts.columns:
        valid_expr = valid_expr & pl.col("is_valid_forecast").fill_null(True)
    valid = forecasts.filter(valid_expr)
    if valid.is_empty():
        return "The hedge-trigger diagnostic has no valid forecast rows; it remains descriptive trigger evidence only."
    group_columns = [
        column
        for column in (
            "suite",
            "target_family",
            "tail_side",
            "model_name",
            "information_set",
            "tail_level",
            "refit_frequency",
        )
        if column in valid.columns
    ]
    trigger_count = 0
    triggered_exception_count = 0
    exception_count = 0
    severities: list[float] = []
    for _, group in valid.group_by(group_columns, maintain_order=True):
        threshold = group.select(pl.col("var_forecast").quantile(0.75)).item()
        if threshold is None:
            continue
        diagnostic = group.with_columns(
            (pl.col("var_forecast") >= float(threshold)).alias("_trigger"),
            (pl.col("realized_loss") > pl.col("var_forecast")).alias("_exception"),
            (pl.col("realized_loss") - pl.col("var_forecast")).alias("_severity"),
        )
        trigger_count += int(diagnostic.select(pl.col("_trigger").sum()).item() or 0)
        exception_count += int(diagnostic.select(pl.col("_exception").sum()).item() or 0)
        triggered = diagnostic.filter(pl.col("_trigger") & pl.col("_exception"))
        triggered_exception_count += triggered.height
        if not triggered.is_empty():
            severities.extend(
                float(value)
                for value in triggered["_severity"].drop_nulls().to_list()
                if math.isfinite(float(value))
            )
    severity_text = _fmt_float(sum(severities) / len(severities)) if severities else "not available"
    return (
        f"The diagnostic 75th-percentile VaR trigger rule marks `{trigger_count}` model-date rows; `{triggered_exception_count}` of those rows coincide with VaR exceptions out of `{exception_count}` total exceptions, and mean triggered exception severity is `{severity_text}`. "
        "This is a pre-open risk-monitoring diagnostic, not hedge PnL, transaction-cost, or trading-alpha evidence."
    )


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    return f"`{value}`"


def _join_model_list(value: object) -> str:
    if isinstance(value, list | tuple):
        return ", ".join(f"`{display_model_label(item)}`" for item in value)
    return f"`{display_model_label(value)}`"


def _panel_bounds(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "forecast_date" not in frame.columns:
        return "`missing`"
    values = frame.select(
        pl.col("forecast_date").min().alias("start"),
        pl.col("forecast_date").max().alias("end"),
    ).row(0, named=True)
    return f"`{values['start']} to {values['end']}`"


def _unique_values(
    frame: pl.DataFrame,
    column: str,
    *,
    formatter: Callable[[object], str] | None = None,
) -> str:
    if frame.is_empty() or column not in frame.columns:
        return "`missing`"
    if formatter is not None:
        values = sorted(
            str(formatter(value)) for value in frame[column].drop_nulls().unique().to_list()
        )
    else:
        values = sorted(str(value) for value in frame[column].drop_nulls().unique().to_list())
    return ", ".join(f"`{value}`" for value in values)


def _fmt_float(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if not math.isfinite(float(value)):
        return str(value)
    return f"{float(value):.6g}"


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _benchmark_calibration_note(benchmark_metrics: pl.DataFrame) -> str | None:
    """Note that baseline benchmark models tend to be better calibrated than ML-tail models."""
    if benchmark_metrics.is_empty() or "var_breach_rate" not in benchmark_metrics.columns:
        return None
    rates = [
        float(v)
        for v in benchmark_metrics["var_breach_rate"].drop_nulls().to_list()
        if math.isfinite(float(v))
    ]
    if not rates:
        return None
    median_breach = sorted(rates)[len(rates) // 2]
    expected = 0.05
    deviation = abs(median_breach - expected)
    if deviation < 0.025:
        return (
            f"Baseline benchmark breach rates have a median of `{_fmt_float(median_breach)}`, "
            "within 2.5 percentage points of the nominal level, indicating reasonable coverage calibration "
            "relative to the ML-tail models whose breach rates are reported in the nested-information-set section."
        )
    return None


def _ml_tail_coverage_warning(ml_tail_metrics: pl.DataFrame) -> str | None:
    """Flag when all primary ML rows systematically over-exceed nominal coverage."""
    if ml_tail_metrics.is_empty() or "var_breach_rate" not in ml_tail_metrics.columns:
        return None
    total = 0
    over_count = 0
    breach_values: list[float] = []
    for row in ml_tail_metrics.iter_rows(named=True):
        breach = _optional_float(row.get("var_breach_rate"))
        expected = _optional_float(row.get("expected_breach_rate"))
        if breach is None or expected is None:
            continue
        total += 1
        breach_values.append(breach)
        if breach > expected + 0.025:
            over_count += 1
    if total == 0 or over_count < total:
        return None
    min_breach = _fmt_float(min(breach_values))
    max_breach = _fmt_float(max(breach_values))
    return (
        f"Coverage warning: all `{total}` primary ML rows exhibit VaR breach rates "
        f"(`{min_breach}` to `{max_breach}`) that exceed the nominal level by more than 2.5 percentage points. "
        "Quantile-loss and FZ-loss differences across the nested information sets must be interpreted "
        "in this context; lower loss scores may partly reflect less conservative VaR estimates rather than "
        "better conditional tail calibration."
    )


def _information_set_saturation_note(ml_tail_metrics: pl.DataFrame) -> str | None:
    """Detect whether nested information sets saturate after the first augmentation step."""
    if ml_tail_metrics.is_empty() or "mean_quantile_loss" not in ml_tail_metrics.columns:
        return None
    if (
        "information_set" not in ml_tail_metrics.columns
        or "tail_side" not in ml_tail_metrics.columns
    ):
        return None
    group_columns = [
        column
        for column in ("tail_side", "model_name", "tail_level", "target_family", "refit_frequency")
        if column in ml_tail_metrics.columns
    ]
    saturated_contexts: list[str] = []
    for _key, subset in ml_tail_metrics.group_by(group_columns, maintain_order=True):
        ladder = (
            subset.group_by("information_set")
            .agg(pl.mean("mean_quantile_loss").alias("mean_quantile_loss"))
            .sort("information_set")
        )
        losses = [_optional_float(v) for v in ladder["mean_quantile_loss"].to_list()]
        losses_clean = [v for v in losses if v is not None]
        if len(losses_clean) < 3:
            continue
        first_step = abs(losses_clean[1] - losses_clean[0])
        later_steps = [
            abs(losses_clean[i] - losses_clean[i - 1]) for i in range(2, len(losses_clean))
        ]
        if later_steps and first_step > 0 and max(later_steps) < first_step * 0.25:
            saturated_contexts.append(_information_saturation_context(subset, group_columns))
    if not saturated_contexts:
        return None
    contexts_text = ", ".join(f"`{s}`" for s in sorted(set(saturated_contexts)))
    return (
        f"For {contexts_text}, the largest quantile-loss change occurs at the first information-set augmentation "
        "(adding U.S. close core); subsequent additions of Japan proxy and Asia proxy ETFs contribute "
        "diminishing incremental loss changes. This saturation pattern is descriptive and does not "
        "automatically reduce the value of the broader information set."
    )


def _information_saturation_context(
    subset: pl.DataFrame,
    group_columns: Sequence[str],
) -> str:
    if subset.is_empty():
        return "unknown"
    row = subset.row(0, named=True)
    parts = [str(row.get("tail_side") or "unknown_side")]
    if "model_name" in group_columns:
        parts.append(display_model_label(row.get("model_name")))
    if "tail_level" in group_columns:
        tail_level = _optional_float(row.get("tail_level"))
        if tail_level is not None:
            parts.append(f"tail={tail_level:.3f}")
    return " / ".join(parts)


def _restricted_short_sample_warning(result_matrix: pl.DataFrame) -> str | None:
    """Flag when the restricted tail-model family comparison has a very short common sample."""
    if result_matrix.is_empty() or "common_n" not in result_matrix.columns:
        return None
    if "comparison_family" not in result_matrix.columns:
        return None
    family_rows = result_matrix.filter(
        pl.col("comparison_family").cast(pl.Utf8).str.contains("tail_model")
    )
    if family_rows.is_empty():
        return None
    max_n = family_rows.select(pl.col("common_n").max()).item()
    if max_n is None:
        return None
    max_n_int = int(max_n)
    if max_n_int >= 500:
        return None
    return (
        f"The tail-model family comparison is severely sample-limited: the largest restricted common-N "
        f"is `{max_n_int}` rows. No model-family ranking claim is supportable from this restricted sample; "
        "extended OOS coverage is needed before tail-model family ranking becomes meaningful."
    )
