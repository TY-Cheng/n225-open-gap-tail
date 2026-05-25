#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = (ROOT / "src", ROOT / "tests")
MYPY_IGNORE_ALLOWLIST = {
    "src/n225_open_gap_tail/data_lake/artifacts.py",
    "src/n225_open_gap_tail/data_lake/cache_ops.py",
    "src/n225_open_gap_tail/data_lake/jquants_options_cache.py",
    "src/n225_open_gap_tail/features/asof.py",
    "src/n225_open_gap_tail/features/descriptions.py",
    "src/n225_open_gap_tail/features/n225_history.py",
    "src/n225_open_gap_tail/features/n225_options.py",
    "src/n225_open_gap_tail/features/registry.py",
    "src/n225_open_gap_tail/features/session_features.py",
    "src/n225_open_gap_tail/forecasting/_benchmark_suite.py",
    "src/n225_open_gap_tail/forecasting/_ml_tail_shards.py",
    "src/n225_open_gap_tail/forecasting/_ml_tail_suite.py",
    "src/n225_open_gap_tail/forecasting/sensitivity.py",
    "src/n225_open_gap_tail/inference/core.py",
    "src/n225_open_gap_tail/metrics/information.py",
    "src/n225_open_gap_tail/metrics/result_matrix.py",
    "src/n225_open_gap_tail/metrics/result_matrix_grouping.py",
    "src/n225_open_gap_tail/metrics/result_matrix_scoring.py",
    "src/n225_open_gap_tail/models/benchmark.py",
    "src/n225_open_gap_tail/models/benchmark_advanced.py",
    "src/n225_open_gap_tail/models/benchmark_advanced_math.py",
    "src/n225_open_gap_tail/models/benchmark_advanced_stateful.py",
    "src/n225_open_gap_tail/models/ml_tail.py",
    "src/n225_open_gap_tail/models/ml_tail_oof.py",
    "src/n225_open_gap_tail/panel/build.py",
    "src/n225_open_gap_tail/panel/jquants_options.py",
    "src/n225_open_gap_tail/panel/leakage.py",
    "src/n225_open_gap_tail/reporting/figures.py",
    "src/n225_open_gap_tail/reporting/latex.py",
    "src/n225_open_gap_tail/reporting/tables.py",
    "src/n225_open_gap_tail/sources/jquants_options.py",
    "tests/test_benchmark_advanced.py",
    "tests/test_ml_tail.py",
    "tests/test_pipeline.py",
    "tests/test_result_matrix.py",
}


def _repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _current_mypy_ignores() -> set[str]:
    ignores: set[str] = set()
    for root in SEARCH_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "# mypy: ignore-errors" in text:
                ignores.add(_repo_rel(path))
    return ignores


def main() -> int:
    current = _current_mypy_ignores()
    unexpected = sorted(current - MYPY_IGNORE_ALLOWLIST)
    stale = sorted(MYPY_IGNORE_ALLOWLIST - current)
    if unexpected or stale:
        for path in unexpected:
            print(f"mypy ignore debt error: unregistered ignore-errors file: {path}", file=sys.stderr)
        for path in stale:
            print(f"mypy ignore debt error: stale allowlist entry: {path}", file=sys.stderr)
        return 1
    print(f"mypy ignore debt ok ({len(current)} allowlisted files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
