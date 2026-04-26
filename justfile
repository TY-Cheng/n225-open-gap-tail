set dotenv-load := true
set shell := ["zsh", "-cu"]

default:
    @just --list

_require-external-uv-env:
    @python3 -c 'import os, sys; from pathlib import Path; raw = os.environ.get("UV_PROJECT_ENVIRONMENT", ""); repo = Path("{{justfile_directory()}}").resolve(); expanded = Path(os.path.expanduser(os.path.expandvars(raw))); missing = not raw; relative = bool(raw) and not expanded.is_absolute(); inside = False if missing or relative else expanded.resolve().is_relative_to(repo); reason = "is required" if missing else "must be an absolute path" if relative else "must be outside the repo" if inside else "ok"; print("UV_PROJECT_ENVIRONMENT=" + (raw or "<unset>")); sys.exit(0 if reason == "ok" else (print("error: UV_PROJECT_ENVIRONMENT " + reason, file=sys.stderr) or 1))'

setup: _require-external-uv-env
    uv sync --all-extras --dev

status: _require-external-uv-env
    uv run n225-open-gap-tail status

fmt: _require-external-uv-env
    uv run ruff format .
    uv run ruff check --fix .

lint: _require-external-uv-env
    uv run ruff check .
    uv run mypy src tests

test: _require-external-uv-env
    uv run pytest

docs: _require-external-uv-env
    uv run mkdocs serve -a 127.0.0.1:8000

docs-build: _require-external-uv-env
    uv run mkdocs build --strict

kernel: _require-external-uv-env
    uv run python -m ipykernel install --user --name n225-open-gap-tail --display-name "Python (n225-open-gap-tail)"
