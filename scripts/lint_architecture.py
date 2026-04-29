#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "n225_open_gap_tail"

ALLOWED_ROOT_FILES = {"__init__.py", "cli.py"}
LINE_LIMIT = 1000
LINE_LIMIT_ALLOWLIST: dict[str, str] = {}

LAYER_ORDER = {
    "config": 0,
    "data_lake": 0,
    "sources": 0,
    "market": 1,
    "features": 1,
    "panel": 2,
    "models": 3,
    "metrics": 3,
    "inference": 4,
    "forecasting": 5,
    "reporting": 5,
    "diagnostics": 5,
}

DEPENDENCY_ALLOWLIST = {
    # Temporary no-logic extraction bridge: keeps the refactor behavior-identical while
    # function bodies are moved out of the former monolith. It is the only permitted
    # cross-layer import from the low-level config package.
    ("config/runtime.py", "market"),
    ("config/runtime.py", "sources"),
    ("config/runtime.py", "data_lake"),
    ("config/runtime.py", "diagnostics"),
}


def _rel(path: Path) -> str:
    return path.relative_to(PKG).as_posix()


def _subpackage(path: Path) -> str | None:
    rel = path.relative_to(PKG)
    if len(rel.parts) < 2:
        return None
    return rel.parts[0]


def _import_root(module: str) -> str | None:
    prefix = "n225_open_gap_tail."
    if not module.startswith(prefix):
        return None
    remainder = module[len(prefix) :]
    return remainder.split(".", 1)[0]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def main() -> int:
    errors: list[str] = []

    if (PKG / "pipeline").exists():
        errors.append("src/n225_open_gap_tail/pipeline/ must not exist")

    for path in PKG.glob("*.py"):
        if path.name not in ALLOWED_ROOT_FILES:
            errors.append(f"root business module is not allowed: {_rel(path)}")

    for path in PKG.rglob("*.py"):
        rel = _rel(path)
        text = path.read_text(encoding="utf-8")
        if "n225_open_gap_tail.pipeline" in text:
            errors.append(f"old pipeline import/reference remains: {rel}")

        line_count = text.count("\n") + 1
        if line_count > LINE_LIMIT and rel not in LINE_LIMIT_ALLOWLIST:
            errors.append(f"implementation file exceeds {LINE_LIMIT} lines: {rel} ({line_count})")

        source_layer = _subpackage(path)
        if source_layer is None or source_layer not in LAYER_ORDER:
            continue
        for module in _imports(path):
            target_layer = _import_root(module)
            if target_layer is None or target_layer not in LAYER_ORDER:
                continue
            if (rel, target_layer) in DEPENDENCY_ALLOWLIST:
                continue
            if LAYER_ORDER[target_layer] > LAYER_ORDER[source_layer]:
                errors.append(
                    f"reverse dependency: {rel} imports higher-layer {target_layer} via {module}"
                )

    if errors:
        for error in errors:
            print(f"architecture error: {error}", file=sys.stderr)
        return 1
    print("architecture lint ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
