set dotenv-load := true
set shell := ["zsh", "-cu"]

default:
    @just --list

_check-env:
    @python3 -c 'import os, sys; raw = os.environ.get("UV_PROJECT_ENVIRONMENT", ""); expanded = os.path.expandvars(raw); expected = os.path.join(os.environ["HOME"], ".venvs", "n225-open-gap-tail"); print(f"UV_PROJECT_ENVIRONMENT={raw}"); sys.exit(0 if expanded == expected else 1)'

setup: _check-env
    uv sync --all-extras --dev

status:
    uv run n225-open-gap-tail status

fmt:
    uv run ruff format .
    uv run ruff check --fix .

lint:
    uv run ruff check .
    uv run mypy src tests

test:
    uv run pytest

docs:
    uv run mkdocs serve -a 127.0.0.1:8000

docs-build:
    uv run mkdocs build --strict

kernel:
    uv run python -m ipykernel install --user --name n225-open-gap-tail --display-name "Python (n225-open-gap-tail)"
