from __future__ import annotations

import subprocess
from pathlib import Path


def _saved_source_matches_commit(run_dir: Path, stored_commit: str, current_commit: str) -> bool:
    """Recognize a dirty-run patch subsequently committed without source changes.

    Compare committed revisions, as the existing run guard does. Saved untracked
    source files are not represented by this diff and are conservatively rejected.
    """
    snapshot = run_dir / "source"
    patch = snapshot / "working-tree.patch"
    if not patch.is_file() or (snapshot / "src").exists():
        return False
    try:
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                stored_commit,
                current_commit,
                "--",
                "src",
                "pyproject.toml",
            ],
            check=True,
            capture_output=True,
        ).stdout
        lock_diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", stored_commit, current_commit, "--", "uv.lock"],
            check=True,
            capture_output=True,
        ).stdout
        return not lock_diff and diff == patch.read_bytes()
    except (OSError, subprocess.CalledProcessError):
        return False


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())


def _git_source_dirty() -> bool:
    """Uncommitted computation changes cannot safely reuse a HEAD-keyed cache."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "pyproject.toml", "uv.lock"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())
