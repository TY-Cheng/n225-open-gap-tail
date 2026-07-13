from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import polars as pl  # noqa: E402

from n225_open_gap_tail.config import load_settings  # noqa: E402
from n225_open_gap_tail.config.model_labels import (  # noqa: E402
    display_information_set_label,
    display_model_label,
)
from n225_open_gap_tail.config.runtime import (  # noqa: E402
    BENCHMARK_ADVANCED_MODEL_NAMES,
    BENCHMARK_BASELINE_MODEL_NAMES,
    ML_TAIL_MODEL_NAMES,
)
from n225_open_gap_tail.metrics.admissibility import (  # noqa: E402
    PASS_ALL_COVERAGE_TOLERANCE,
    PASS_ALL_MIN_ROWS,
)

CSV_NAME = "model_metrics_full_rows.csv"
AUDIT_NAME = "model_metrics_breach_audit.md"
METRIC_COLUMNS = (
    "group",
    "tail",
    "info",
    "model",
    "N",
    "breach",
    "breach_pass",
    "gate_pass",
    "q_loss",
    "fz_loss",
    "severity",
)
TAIL_ORDER = {"Downside": 0, "Upside": 1}
INFO_ORDER = {
    "Lagged opening-gap losses": 0,
    "A: Japan only": 1,
    "B: +U.S.-close core": 2,
    "C: +Japan proxy": 3,
    "D: +Asia proxy": 4,
    "E: +U.S.-listed options": 5,
}


class AuditExportError(RuntimeError):
    """Raised when a slide audit export cannot be created from a run."""


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    reports_dir = _resolve_reports_dir()
    run_dir = _resolve_run_dir(reports_dir=reports_dir, run_id=args.run_id)
    run_id = run_dir.name
    output_dir = args.output_dir or (ROOT / "docs" / "tables" / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_metrics = _read_metric_frame(
        run_dir=run_dir,
        name="benchmark_metrics_per_model",
        active_models=(*BENCHMARK_BASELINE_MODEL_NAMES, *BENCHMARK_ADVANCED_MODEL_NAMES),
    )
    ml_tail_metrics = _read_metric_frame(
        run_dir=run_dir,
        name="ml_tail_metrics_per_model",
        active_models=ML_TAIL_MODEL_NAMES,
    )
    if benchmark_metrics.is_empty() and ml_tail_metrics.is_empty():
        raise AuditExportError(f"No per-model metrics available under {run_dir / 'metrics'}")

    rows = [
        *_metric_rows(benchmark_metrics, group="Benchmark"),
        *_metric_rows(ml_tail_metrics, group="LightGBM"),
    ]
    if not rows:
        raise AuditExportError("No active model metric rows remained after filtering")

    csv_path = output_dir / CSV_NAME
    full_metrics = pl.DataFrame(rows).select(METRIC_COLUMNS)
    full_metrics = full_metrics.with_columns(
        pl.col("group").replace({"Benchmark": 0, "LightGBM": 1}).alias("_group_order"),
        pl.col("tail").replace(TAIL_ORDER).alias("_tail_order"),
        pl.col("info").replace(INFO_ORDER).fill_null(99).alias("_info_order"),
        pl.col("model").str.to_lowercase().alias("_model_order"),
    ).sort(["_group_order", "_tail_order", "_model_order", "_info_order"])
    csv_metrics = full_metrics.select(METRIC_COLUMNS).with_columns(
        *[
            pl.when(pl.col(column)).then(pl.lit("True")).otherwise(pl.lit("False")).alias(column)
            for column in ("breach_pass", "gate_pass")
        ]
    )
    csv_metrics.write_csv(csv_path)

    audit_path = output_dir / AUDIT_NAME
    audit_path.write_text(
        _audit_markdown(run_id=run_id, full_metrics=full_metrics.select(METRIC_COLUMNS)),
        encoding="utf-8",
    )
    print(f"wrote {csv_path}")
    print(f"wrote {audit_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export slide-facing model metrics and VaR breach-pass audit tables "
            "from a completed tail-risk run."
        )
    )
    parser.add_argument(
        "--run-id",
        default="latest",
        help="Run id under reports/runs, or 'latest' for the latest completed full run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to docs/tables/<run_id>.",
    )
    return parser.parse_args(argv)


def _resolve_reports_dir() -> Path:
    settings = load_settings()
    reports_dir = settings.reports_dir
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir
    return reports_dir.resolve(strict=False)


def _resolve_run_dir(*, reports_dir: Path, run_id: str) -> Path:
    runs_dir = reports_dir / "runs"
    if run_id != "latest":
        run_dir = runs_dir / run_id
        if not (run_dir / "manifest.json").exists():
            raise AuditExportError(f"Run manifest not found: {run_dir / 'manifest.json'}")
        return run_dir
    candidates = sorted(
        (
            path
            for path in runs_dir.glob("tailrisk_*")
            if (path / "manifest.json").exists() and _is_completed_full_run(path)
        ),
        key=lambda path: (path / "manifest.json").stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise AuditExportError(f"No completed full tail-risk runs found under {runs_dir}")
    return candidates[0]


def _is_completed_full_run(run_dir: Path) -> bool:
    manifest = _read_json(run_dir / "manifest.json")
    benchmark_status = str(manifest.get("benchmark_eval_status") or "")
    ml_tail_status = str(manifest.get("ml_tail_eval_status") or "")
    return benchmark_status == "completed" and ml_tail_status.startswith("completed")


def _read_json(path: Path) -> dict[str, object]:
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {}


def _read_metric_frame(
    *,
    run_dir: Path,
    name: str,
    active_models: Iterable[str],
) -> pl.DataFrame:
    path = run_dir / "metrics" / f"{name}.parquet"
    if not path.exists():
        raise AuditExportError(f"Required metric parquet not found: {path}")
    frame = pl.read_parquet(path)
    if frame.is_empty() or "model_name" not in frame.columns:
        return pl.DataFrame()
    return frame.filter(pl.col("model_name").is_in(list(active_models)))


def _metric_rows(frame: pl.DataFrame, *, group: str) -> list[dict[str, object]]:
    required = {
        "model_name",
        "tail_side",
        "information_set",
        "rows",
        "var_breach_rate",
        "expected_breach_rate",
        "mean_quantile_loss",
        "mean_fz_loss",
        "mean_exceedance_severity",
    }
    if frame.is_empty() or not required.issubset(frame.columns):
        return []
    rows: list[dict[str, object]] = []
    for metric in frame.iter_rows(named=True):
        rows.append(_metric_row(metric, group=group))
    return rows


def _metric_row(metric: Mapping[str, object], *, group: str) -> dict[str, object]:
    breach = _optional_float(metric.get("var_breach_rate"))
    expected = _optional_float(metric.get("expected_breach_rate")) or 0.05
    coverage_error = abs(breach - expected) if breach is not None else None
    breach_pass = coverage_error is not None and coverage_error <= PASS_ALL_COVERAGE_TOLERANCE
    n_rows = int(_optional_float(metric.get("rows")) or 0)
    return {
        "group": group,
        "tail": _tail_label(metric.get("tail_side")),
        "info": display_information_set_label(metric.get("information_set")),
        "model": display_model_label(metric.get("model_name")),
        "N": n_rows,
        "breach": _round_float(breach),
        "breach_pass": breach_pass,
        "gate_pass": breach_pass and n_rows >= PASS_ALL_MIN_ROWS,
        "q_loss": _round_float(metric.get("mean_quantile_loss")),
        "fz_loss": _round_float(metric.get("mean_fz_loss")),
        "severity": _round_float(metric.get("mean_exceedance_severity")),
    }


def _audit_markdown(*, run_id: str, full_metrics: pl.DataFrame) -> str:
    benchmark = full_metrics.filter(pl.col("group") == "Benchmark")
    lgbm = full_metrics.filter(pl.col("group") == "LightGBM")
    sections = [
        "# Model Metrics, Breach-Neighborhood, and Sample-Eligibility Audit",
        "",
        f"Run: `{run_id}`",
        "",
        (
            f"Generated by `scripts/export_model_metrics_breach_audit.py`. "
            f"Breach pass criterion: `abs(breach - 0.05) <= "
            f"{PASS_ALL_COVERAGE_TOLERANCE}`; gate pass additionally requires "
            f"`N >= {PASS_ALL_MIN_ROWS}`."
        ),
        (
            "This companion audit reports only the exception-rate tolerance and sample-size "
            "gates. The Results Snapshot reports the Kupiec and Christoffersen independence "
            "tests that complete the eight-scenario VaR coverage screen."
        ),
        "",
        "## LightGBM-EVT Breach-Pass Counts Across 8 Scenarios",
        "",
        _lgbm_count_table(lgbm),
        "",
        "## Benchmark Breach-Pass Counts",
        "",
        _benchmark_count_table(benchmark),
        "",
        "## Best LightGBM-EVT Model in Each Scenario",
        "",
        (
            "Best-by-FZ is selected among gate-pass rows only. QL-best is shown "
            "separately because it sometimes disagrees with FZ-best."
        ),
        "",
        _best_lgbm_table(lgbm),
        "",
        "## Best Benchmark Models",
        "",
        _best_benchmark_table(benchmark),
        "",
        "## Full Benchmark Metrics",
        "",
        _full_metrics_table(benchmark, include_info=False),
        "",
        "## Full LightGBM-EVT Metrics",
        "",
        _full_metrics_table(lgbm, include_info=True),
        "",
    ]
    return "\n".join(sections)


def _lgbm_count_table(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return _markdown_table(
            ("Model", "Breach-pass scenarios / 8", "Gate-pass scenarios / 8"), []
        )
    grouped = (
        frame.group_by("model")
        .agg(
            pl.len().alias("total"),
            pl.sum("breach_pass").alias("breach_pass"),
            pl.sum("gate_pass").alias("gate_pass"),
        )
        .sort("model")
    )
    return _markdown_table(
        ("Model", "Breach-pass scenarios / 8", "Gate-pass scenarios / 8"),
        [
            (
                row["model"],
                f"{int(row['breach_pass'])}/{int(row['total'])}",
                f"{int(row['gate_pass'])}/{int(row['total'])}",
            )
            for row in grouped.iter_rows(named=True)
        ],
    )


def _benchmark_count_table(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return _markdown_table(
            ("Tail", "Breach-pass models", "Gate-pass models", "Total models"), []
        )
    rows: list[tuple[object, ...]] = []
    total_breach = total_gate = total_models = 0
    for tail in ("Downside", "Upside"):
        side = frame.filter(pl.col("tail") == tail)
        breach = _bool_sum(side, "breach_pass")
        gate = _bool_sum(side, "gate_pass")
        count = side.height
        total_breach += breach
        total_gate += gate
        total_models += count
        rows.append((tail, breach, gate, count))
    rows.append(("Total", total_breach, total_gate, total_models))
    return _markdown_table(
        ("Tail", "Breach-pass models", "Gate-pass models", "Total models"),
        rows,
    )


def _best_lgbm_table(frame: pl.DataFrame) -> str:
    rows: list[tuple[object, ...]] = []
    for tail in ("Downside", "Upside"):
        side = frame.filter(pl.col("tail") == tail)
        for info in _ordered_values(side.get_column("info").to_list()):
            group = side.filter(pl.col("info") == info)
            gate = group.filter(pl.col("gate_pass"))
            if gate.is_empty():
                rows.append((tail, info, 0, "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"))
                continue
            fz_best = _best_row(gate, "fz_loss")
            q_best = _best_row(gate, "q_loss")
            rows.append(
                (
                    tail,
                    info,
                    gate.height,
                    fz_best["model"],
                    _fmt_rate(fz_best["breach"]),
                    _fmt_float(fz_best["q_loss"]),
                    _fmt_float(fz_best["fz_loss"]),
                    _fmt_float(fz_best["severity"]),
                    q_best["model"],
                    _fmt_float(q_best["q_loss"]),
                )
            )
    return _markdown_table(
        (
            "Tail",
            "Info set",
            "Gate-pass rows",
            "Best by FZ",
            "Breach",
            "QL",
            "FZ",
            "Severity",
            "Best by QL",
            "QL",
        ),
        rows,
    )


def _best_benchmark_table(frame: pl.DataFrame) -> str:
    rows: list[tuple[object, ...]] = []
    for tail in ("Downside", "Upside"):
        gate = frame.filter((pl.col("tail") == tail) & pl.col("gate_pass"))
        if gate.is_empty():
            rows.append((tail, 0, "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"))
            continue
        fz_best = _best_row(gate, "fz_loss")
        q_best = _best_row(gate, "q_loss")
        rows.append(
            (
                tail,
                gate.height,
                fz_best["model"],
                _fmt_rate(fz_best["breach"]),
                _fmt_float(fz_best["q_loss"]),
                _fmt_float(fz_best["fz_loss"]),
                q_best["model"],
                _fmt_float(q_best["q_loss"]),
            )
        )
    return _markdown_table(
        ("Tail", "Gate-pass rows", "Best by FZ", "Breach", "QL", "FZ", "Best by QL", "QL"),
        rows,
    )


def _full_metrics_table(frame: pl.DataFrame, *, include_info: bool) -> str:
    sort_cols = ["_tail_order"]
    if include_info:
        sort_cols.append("_info_order")
    sorted_frame = frame.with_columns(
        pl.col("tail").replace(TAIL_ORDER).alias("_tail_order"),
        pl.col("info").replace(INFO_ORDER).fill_null(99).alias("_info_order"),
        pl.col("gate_pass").cast(pl.Int8).alias("_gate_order"),
    ).sort(
        [*sort_cols, "_gate_order", "fz_loss", "q_loss"],
        descending=[False] * len(sort_cols) + [True, False, False],
    )
    headers = (
        ("Tail", "Info set", "Model", "N", "Breach", "Pass", "QL", "FZ", "Severity")
        if include_info
        else ("Tail", "Model", "N", "Breach", "Pass", "QL", "FZ", "Severity")
    )
    rows: list[tuple[object, ...]] = []
    for row in sorted_frame.iter_rows(named=True):
        common = (
            int(row["N"]),
            _fmt_rate(row["breach"]),
            "Y" if bool(row["gate_pass"]) else "N",
            _fmt_float(row["q_loss"]),
            _fmt_float(row["fz_loss"]),
            _fmt_float(row["severity"]),
        )
        if include_info:
            rows.append((row["tail"], row["info"], row["model"], *common))
        else:
            rows.append((row["tail"], row["model"], *common))
    return _markdown_table(headers, rows)


def _best_row(frame: pl.DataFrame, metric: str) -> dict[str, object]:
    ranked = frame.sort([metric, "q_loss", "model"])
    return dict(ranked.row(0, named=True))


def _ordered_values(values: Iterable[object]) -> list[str]:
    return sorted({str(value) for value in values}, key=lambda value: INFO_ORDER.get(value, 99))


def _tail_label(value: object) -> str:
    text = "" if value is None else str(value)
    return {"left_tail": "Downside", "right_tail": "Upside"}.get(text, text)


def _bool_sum(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.select(pl.sum(column)).item() or 0)


def _round_float(value: object) -> float | None:
    numeric = _optional_float(value)
    return None if numeric is None else round(numeric, 6)


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and abs(numeric) != float("inf") else None


def _fmt_rate(value: object) -> str:
    numeric = _optional_float(value)
    return "n/a" if numeric is None else f"{numeric:.1%}"


def _fmt_float(value: object) -> str:
    numeric = _optional_float(value)
    return "n/a" if numeric is None else f"{numeric:.6f}"


def _markdown_table(headers: tuple[str, ...], rows: Iterable[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    right_aligned = {
        "N",
        "Breach",
        "Pass",
        "QL",
        "FZ",
        "Severity",
        "Gate-pass rows",
        "Breach-pass models",
        "Gate-pass models",
        "Total models",
        "Breach-pass scenarios / 8",
        "Gate-pass scenarios / 8",
    }
    divider = (
        "| " + " | ".join("---:" if item in right_aligned else "---" for item in headers) + " |"
    )
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
