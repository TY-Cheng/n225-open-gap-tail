from __future__ import annotations

from n225_open_gap_tail.config.runtime import (
    ML_TAIL_HISTORY_FEATURES,
    PIPELINE_CONFIG,
    PipelineRunError,
)


def registered_ml_tail_information_sets() -> tuple[str, ...]:
    return (
        PIPELINE_CONFIG.feature_sets.ml_tail_model_a_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_b_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_c_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_d_information_set,
        PIPELINE_CONFIG.feature_sets.ml_tail_model_e_information_set,
    )


def ml_tail_feature_columns_for_information_set(
    coverage_rows: list[dict[str, object]],
    *,
    information_set: str,
) -> list[str]:
    """Return the pre-registered ML tail candidate features for an information set."""
    blocks: set[str]
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
    elif information_set == PIPELINE_CONFIG.feature_sets.ml_tail_model_e_information_set:
        blocks = {
            "us_core",
            "us_late_session",
            "fred_core",
            "fx_core",
            "japan_proxy",
            "asia_proxy",
            "options_risk",
        }
    else:
        raise PipelineRunError(f"Unknown ML tail information set: {information_set}")
    block_features = [
        str(row["feature"])
        for row in coverage_rows
        if str(row.get("source_block") or "") in blocks and row.get("feature")
    ]
    return list(dict.fromkeys((*ML_TAIL_HISTORY_FEATURES, *sorted(block_features))))
