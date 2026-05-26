from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_EXTERNAL_DATA_PATHS = (
    "DATA_DIR",
    "BRONZE_DATA_DIR",
    "SILVER_DATA_DIR",
    "GOLD_DATA_DIR",
)


def _resolved_env_path(name: str) -> tuple[Path | None, str | None]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None, f"{name} is required"
    expanded = Path(os.path.expanduser(os.path.expandvars(raw)))
    if not expanded.is_absolute():
        return None, f"{name} must be an absolute path: {raw}"
    resolved = expanded.resolve(strict=False)
    if resolved.is_relative_to(ROOT):
        return None, f"{name} must be outside the repo: {resolved}"
    return resolved, None


def _repo_local_data_error(local_data: Path) -> str | None:
    if not local_data.exists() and not local_data.is_symlink():
        return None
    if not local_data.is_symlink():
        return f"repo-local data path must be an external symlink or absent: {local_data}"
    target = local_data.resolve(strict=False)
    if target.is_relative_to(ROOT):
        return f"repo-local data symlink must resolve outside the repo: {local_data} -> {target}"
    print(f"DATA_SYMLINK={local_data} -> {target}")
    return None


def main() -> int:
    errors: list[str] = []
    for name in REQUIRED_EXTERNAL_DATA_PATHS:
        path, error = _resolved_env_path(name)
        if error:
            errors.append(error)
            continue
        print(f"{name}={path}")

    local_data = ROOT / "data"
    if error := _repo_local_data_error(local_data):
        errors.append(error)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
