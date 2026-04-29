from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"\b(?:p2a|p2b|p2c)\b|paper-panel|paper-eval|paper-grade|"
    r"paper-leakage-check|paper-latex-tables|\bGW\b|Giacomini-White",
    re.IGNORECASE,
)

ROOTS = ("src", "tests", "docs")
EXTRA_FILES = (
    "README.md",
    "justfile",
    "mkdocs.yml",
    "pyproject.toml",
)
SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "reports",
    "site",
}
ALLOWLIST = {
    Path("scripts/lint_legacy_names.py"),
}


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root_name in ROOTS:
        root = Path(root_name)
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*") if path.is_file())
    files.extend(Path(name) for name in EXTRA_FILES if Path(name).exists())
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in _iter_files():
        if path in ALLOWLIST or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                failures.append(f"{path}:{line_number}: {line.strip()}")
    if failures:
        print("Legacy names remain:", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("No legacy names found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
