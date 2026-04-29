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
            continue
        shutil.copy2(source_path, target_dir / source_path.name)


def evidence_map_mermaid() -> str:
    return "\n".join(
        [
            "flowchart LR",
            '  A["Vendor and calendar inputs"] --> B["Bronze / silver caches"]',
            '  B --> C["Gold panel and timing map"]',
            '  C --> D["Leakage and sample gates"]',
            '  D --> E["Benchmark floor and advanced benchmarks"]',
            '  D --> F["ML-tail information ladder"]',
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
        ("coverage", "Figure 1. Coverage Breach-Rate Diagnostics"),
        ("benchmark_murphy", "Figure 2. Benchmark Murphy Diagnostics"),
        ("ml_tail_murphy", "Figure 3. ML-Tail Murphy Diagnostics"),
        ("dst", "Figure 4. DST Attenuation Diagnostics"),
        ("severity", "Figure 5. ES Severity Diagnostics"),
        ("trigger", "Figure 6. Trigger Diagnostics"),
    ]
    for family, title in order:
        family_entries = by_family.get(family, [])
        if not family_entries:
            continue
        family_entries = sorted(family_entries, key=lambda item: str(item.get("tail_side") or ""))
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
    return "\n\n".join(sections)


def _png_figure_entries(figure_manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_figures = figure_manifest.get("figures")
    if not isinstance(raw_figures, list):
        return []
    entries = [item for item in raw_figures if isinstance(item, dict)]
    return [entry for entry in entries if str(entry.get("format") or "").lower() == "png"]


def _figure_family(name: str) -> str:
    if name.startswith("coverage_breach_rates"):
        return "coverage"
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
    return "other"


def _figure_key_readings(family: str) -> list[str]:
    readings = {
        "coverage": [
            "- Key readings: bars report realized VaR exception rates against the nominal line.",
            "- Read this with Kupiec/Christoffersen fields, exception counts, and sample gates.",
        ],
        "benchmark_murphy": [
            "- Key readings: curves report benchmark elementary-score diagnostics on a common grid.",
            "- The plot is a scoring-family diagnostic, not a pairwise ranking statement.",
        ],
        "ml_tail_murphy": [
            "- Key readings: curves report the ML-tail headline information ladder on a common grid.",
            "- Interpret curve separation together with coverage and unconditional inference gates.",
        ],
        "dst": [
            "- Key readings: bars summarize timing-regime forecast diagnostics.",
            "- Treat this as descriptive timing evidence, not structural identification.",
        ],
        "severity": [
            "- Key readings: bars report conditional-on-exception severity diagnostics.",
            "- Severity is useful for risk interpretation but is not a standalone model claim.",
        ],
        "trigger": [
            "- Key readings: bars report pre-open risk-trigger diagnostics by model family.",
            "- The trigger output is a monitoring diagnostic, not an execution-performance result.",
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
