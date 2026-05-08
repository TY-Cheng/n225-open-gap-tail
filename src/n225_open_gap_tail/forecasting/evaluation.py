# ruff: noqa: F401,I001,UP035
from __future__ import annotations

from pathlib import Path

from n225_open_gap_tail.config.runtime import (
    EvaluationResult as EvaluationResult,
    PipelineRunError,
    TAIL_SIDE_BOTH,
)
from n225_open_gap_tail.forecasting._benchmark_suite import (
    evaluate_benchmark_baseline_suite,
    evaluate_benchmark_suite,
)
from n225_open_gap_tail.forecasting._ml_tail_suite import evaluate_ml_tail_suite


def evaluate_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    suite: str = "benchmark",
    force: bool = False,
    tail_side: str = TAIL_SIDE_BOTH,
    resume: bool = True,
) -> EvaluationResult:
    normalized_suite = suite.lower().replace("-", "_")
    if normalized_suite == "benchmark":
        return evaluate_benchmark_suite(
            run_dir=run_dir, workers=workers, force=force, tail_side=tail_side
        )
    if normalized_suite == "benchmark_baseline":
        return evaluate_benchmark_baseline_suite(
            run_dir=run_dir, workers=workers, force=force, tail_side=tail_side
        )
    if normalized_suite == "ml_tail":
        return evaluate_ml_tail_suite(
            run_dir=run_dir,
            workers=workers,
            force=force,
            tail_side=tail_side,
            resume=resume,
        )
    raise PipelineRunError(f"Unknown evaluation suite: {suite}")
