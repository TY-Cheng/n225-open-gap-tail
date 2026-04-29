# mypy: ignore-errors
# ruff: noqa: F401,F403,F405,F821,I001,UP035
from __future__ import annotations

from n225_open_gap_tail.config import runtime as _runtime
from n225_open_gap_tail.forecasting._benchmark_suite import (
    evaluate_benchmark_floor_suite,
    evaluate_benchmark_suite,
)
from n225_open_gap_tail.forecasting._ml_tail_suite import evaluate_ml_tail_suite

globals().update({k: v for k, v in vars(_runtime).items() if not k.startswith("__")})


def evaluate_suite(
    *,
    run_dir: Path,
    workers: int = 1,
    suite: str = "benchmark",
    force: bool = False,
    tail_side: str = TAIL_SIDE_BOTH,
) -> EvaluationResult:
    normalized_suite = suite.lower().replace("-", "_")
    if normalized_suite == "benchmark":
        return evaluate_benchmark_suite(
            run_dir=run_dir, workers=workers, force=force, tail_side=tail_side
        )
    if normalized_suite == "benchmark_floor":
        return evaluate_benchmark_floor_suite(
            run_dir=run_dir, workers=workers, force=force, tail_side=tail_side
        )
    if normalized_suite == "ml_tail":
        return evaluate_ml_tail_suite(
            run_dir=run_dir, workers=workers, force=force, tail_side=tail_side
        )
    raise PipelineRunError(f"Unknown evaluation suite: {suite}")
