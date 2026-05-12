# ruff: noqa: E501
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def sync_snapshot_figure_assets(
    *,
    run_dir: Path,
    figure_manifest: dict[str, object],
    docs_dir: Path,
) -> None:
    entries = _png_figure_entries(figure_manifest)
    if not entries:
        return
    target_dir = docs_dir / "figures" / run_dir.name
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in target_dir.glob("*.png"):
        stale.unlink(missing_ok=True)
    for entry in entries:
        raw_path = str(entry.get("path") or "")
        if not raw_path:
            continue
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = run_dir / source_path
        if not source_path.exists():
            raise FileNotFoundError(f"Figure manifest references missing PNG: {source_path}")
        shutil.copy2(source_path, target_dir / source_path.name)


def evidence_map_mermaid() -> str:
    return "\n".join(
        [
            "flowchart LR",
            '  A["Vendor and calendar inputs"] --> B["Bronze / silver caches"]',
            '  B --> C["Gold panel and timing map"]',
            '  C --> D["Leakage and sample gates"]',
            '  D --> E["Baseline benchmarks and advanced econometric benchmarks"]',
            '  D --> F["Primary ML nested information sets"]',
            '  E --> G["Metrics, DM/MCS, Murphy diagnostics"]',
            "  F --> G",
            '  F --> H["CPA conditional loss-difference diagnostics"]',
            '  G --> I["Tables and figures"]',
            "  H --> I",
            '  I --> J["Generated results snapshot"]',
        ]
    )


def table_manifest_markdown(table_manifest: dict[str, object]) -> str:
    raw_tables = table_manifest.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        return _markdown_table(
            ("Table", "Source artifacts", "Claim scope", "Tail side", "File"),
            [("missing", "missing", "table_manifest_not_available", "", "")],
        )
    rows = []
    for item in raw_tables:
        if not isinstance(item, dict):
            continue
        rows.append(
            (
                str(item.get("name") or "unnamed_table"),
                _source_artifacts_text(item.get("source_artifacts")),
                _code(item.get("claim_scope")),
                _code(item.get("tail_side")),
                _code(item.get("path")),
            )
        )
    if not rows:
        rows = [("missing", "missing", "table_manifest_not_available", "", "")]
    return _markdown_table(("Table", "Source artifacts", "Claim scope", "Tail side", "File"), rows)


def figure_gallery_markdown(*, figure_manifest: dict[str, object], run_id: str) -> str:
    entries = _png_figure_entries(figure_manifest)
    if not entries:
        return "### Figures\n\n- Figure artifacts are not available for this run."
    by_family: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        by_family.setdefault(_figure_family(str(entry.get("name") or "")), []).append(entry)
    sections: list[str] = []
    order = [
        ("target_distribution", "Figure 1. Target Distribution And Tail Diagnostics"),
        ("coverage", "Figure 2. Coverage Breach-Rate Diagnostics"),
        ("selected_performance", "Figure 3. Selected Benchmark-vs-LGBM Performance"),
        ("benchmark_murphy", "Figure 4. Benchmark Murphy Diagnostics"),
        ("ml_tail_murphy", "Figure 5. ML-Tail Murphy Diagnostics"),
        ("severity", "Figure 6. ES Severity Diagnostics"),
        ("trigger", "Figure 7. Selected Trigger Diagnostics"),
        ("evt_standardized", "Figure 8. EVT Standardized-Residual Diagnostics"),
        ("dst", "Appendix Figure A. DST Attenuation Diagnostics"),
    ]
    for family, title in order:
        family_entries = by_family.get(family, [])
        if not family_entries:
            continue
        family_entries = sorted(family_entries, key=lambda item: _figure_sort_key(family, item))
        parts = [f"### {title}", "", *_figure_key_readings(family)]
        for entry in family_entries:
            name = str(entry.get("name") or "figure")
            path = str(entry.get("path") or "")
            file_name = Path(path).name
            docs_path = f"figures/{run_id}/{file_name}"
            source = _source_artifacts_text(entry.get("source_artifacts"))
            claim_scope = _code(entry.get("claim_scope"))
            tail_side = _code(entry.get("tail_side"))
            parts.extend(
                [
                    "",
                    f"![{name}]({docs_path})",
                    "",
                    (
                        f"_Figure: `{name}`. Source: {source}. Claim scope: "
                        f"{claim_scope}. Tail side: {tail_side}. Run file: `{path}`._"
                    ),
                ]
            )
        sections.append("\n".join(parts))
    if not sections:
        return (
            "### Figures\n\n"
            "- Figure manifest entries are present, but none match the registered paper figure families."
        )
    return "\n\n".join(sections)


def _png_figure_entries(figure_manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_figures = figure_manifest.get("figures")
    if not isinstance(raw_figures, list):
        return []
    entries = [item for item in raw_figures if isinstance(item, dict)]
    return [entry for entry in entries if str(entry.get("format") or "").lower() == "png"]


def _figure_family(name: str) -> str:
    if name.startswith("target_"):
        return "target_distribution"
    if name.startswith("coverage_breach_rates"):
        return "coverage"
    if name.startswith("selected_model_performance"):
        return "selected_performance"
    if name.startswith("benchmark_murphy"):
        return "benchmark_murphy"
    if name.startswith("ml_tail_murphy"):
        return "ml_tail_murphy"
    if name.startswith("dst_attenuation"):
        return "dst"
    if name.startswith("es_severity"):
        return "severity"
    if name.startswith("trigger_diagnostics"):
        return "trigger"
    if name.startswith("evt_standardized"):
        return "evt_standardized"
    return "other"


def _figure_sort_key(family: str, item: dict[str, object]) -> tuple[object, ...]:
    name = str(item.get("name") or "")
    if family == "target_distribution":
        target_order = {
            "target_gap_histogram_density": 0,
            "target_loss_qq_left_tail": 1,
            "target_loss_qq_right_tail": 2,
            "target_log_survival": 3,
            "target_mean_excess": 4,
            "target_hill_plot": 5,
        }
        return (target_order.get(name, 99), name)
    return (str(item.get("tail_side") or ""), name)


def _figure_key_readings(family: str) -> list[str]:
    readings = {
        "target_distribution": [
            "- Key readings: these figures describe the raw settlement-to-open gap and the left/right loss tails.",
            "- They motivate VaR/ES and POT-GPD modeling, but they do not validate LightGBM+EVT forecasts.",
        ],
        "coverage": [
            "- Key readings: bars report realized VaR exception rates against the nominal line.",
            "- Read this first: exception-rate deviations set the boundary for any loss-based interpretation.",
        ],
        "selected_performance": [
            "- Key readings: compact main-figure rows split models into two broad groups, Benchmark and LGBM.",
            "- Within each tail and group, rows are selected by sufficient sample size, VaR coverage near 5%, then lower FZ loss and quantile loss.",
            "- Full benchmark and LGBM per-model results are exported in appendix tables, so this figure is a readable summary rather than the full result set.",
        ],
        "benchmark_murphy": [
            "- Key readings: curves report benchmark elementary-score diagnostics on a common grid.",
            "- The plot is a scoring-family diagnostic, not a pairwise ranking statement.",
        ],
        "ml_tail_murphy": [
            "- Key readings: curves report the ML-tail nested information sets on a common grid.",
            "- Interpret curve separation together with the primary ML coverage warning and unconditional inference gates.",
        ],
        "dst": [
            "- Appendix-only diagnostic: the left/right timing-regime patterns are not stable enough for a main-text claim.",
            "- Key readings: bars report loss gains from adding `JP + US close core` to `JP only`, split by EST/EDT timing regime.",
            "- A positive gain means the expanded information set has lower average loss; a negative gain means it performs worse on that loss metric.",
            "- This diagnostic is computed for the current primary nested-information-set anchor, `LGBM direct quantile`; it is not an average across all LightGBM/EVT variants or a model-selection exercise.",
            "- Treat this as descriptive timing evidence; left/right patterns should not be assigned a shared structural mechanism.",
        ],
        "severity": [
            "- Key readings: bars report conditional-on-exception severity diagnostics.",
            "- Severity is reported for risk interpretation but is not a standalone model-selection claim.",
        ],
        "trigger": [
            "- Key readings: bars report pre-open VaR-trigger diagnostics for the same selected Benchmark-vs-LGBM candidates used in the compact performance figures.",
            "- The trigger rule is within-model: `trigger = VaR forecast above that model's 75th-percentile VaR forecast` on the evaluation sample.",
            "- This top-quartile rule is separate from the 95% VaR forecast target: VaR calibration is evaluated by breach rates, coverage tests, quantile loss, and FZ loss.",
            "- Lower false-alarm and missed-exception rates are better; the trigger-rate bar is omitted because it is expected to be near 25% by construction.",
            "- The trigger output is a monitoring diagnostic, not hedge PnL, not transaction-cost evidence, and not an execution-performance result.",
        ],
        "evt_standardized": [
            "- Key readings: figures show EVT diagnostics for LightGBM location-scale standardized residuals.",
            "- QQ, log-survival, mean-excess, Hill, and threshold-stability diagnostics validate the POT-GPD tail assumption.",
            "- These are assumption-validation diagnostics, not forecast-performance claims.",
        ],
    }
    return readings.get(family, ["- Key readings: generated diagnostic figure."])


def _source_artifacts_text(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "`missing`"
    return ", ".join(f"`{item}`" for item in value)


def _code(value: object) -> str:
    return f"`{value}`"


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
