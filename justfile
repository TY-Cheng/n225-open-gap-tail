set dotenv-load
set shell := ["zsh", "-cu"]
cli := "PYTHONPATH=src uv run python -m n225_open_gap_tail.cli"

default:
    @just --list

_require-external-uv-env:
    @python3 -c 'import os, sys; from pathlib import Path; raw = os.environ.get("UV_PROJECT_ENVIRONMENT", ""); repo = Path("{{ justfile_directory() }}").resolve(); expanded = Path(os.path.expanduser(os.path.expandvars(raw))); missing = not raw; relative = bool(raw) and not expanded.is_absolute(); inside = False if missing or relative else expanded.resolve().is_relative_to(repo); reason = "is required" if missing else "must be an absolute path" if relative else "must be outside the repo" if inside else "ok"; print("UV_PROJECT_ENVIRONMENT=" + (raw or "<unset>")); sys.exit(0 if reason == "ok" else (print("error: UV_PROJECT_ENVIRONMENT " + reason, file=sys.stderr) or 1))'

status: _require-external-uv-env
    {{cli}} status

check: _require-external-uv-env
    uv sync --all-extras --dev
    uv run ruff format --check src tests
    uv run ruff check src tests
    uv run mypy src tests
    uv run python scripts/lint_mypy_ignore_debt.py
    uv run pytest -m "not vendor and not realdata"
    uv run mkdocs build --strict
    just lint-legacy-names
    just lint-architecture

fix: _require-external-uv-env
    uv sync --all-extras --dev
    uv run ruff format src tests
    uv run ruff check --fix src tests

full start="2016-07-19" end="" workers="6" force="false" options="true":
    @[[ "{{ options }}" == "true" || "{{ options }}" == "false" ]] || (echo 'error: options must be "true" or "false"' >&2; exit 1)
    just check
    MASSIVE_OPTIONS_HISTORICAL_ENABLED="{{ options }}" MASSIVE_OPTIONS_FLAT_FILES_ENABLED="{{ options }}" MASSIVE_OPTIONS_UNDERLYINGS="${MASSIVE_OPTIONS_UNDERLYINGS:-SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,SMH,EWJ,DXJ,EEM,FXI,EWY,EWT,EWH,TM,SONY,MUFG,SMFG,MFG}" just _run "{{ start }}" "{{ end }}" "{{ workers }}" all "{{ force }}"

source-probe: _require-external-uv-env
    {{cli}} source-probe

lint-legacy-names:
    python3 scripts/lint_legacy_names.py

lint-architecture:
    python3 scripts/lint_architecture.py

docs port="8000": _require-external-uv-env
    uv run mkdocs build --strict
    @port=$(python3 -c 'import socket, sys; host = "127.0.0.1"; start = int(sys.argv[1]); print(next(p for p in range(start, start + 100) if socket.socket().connect_ex((host, p))))' "{{ port }}"); echo "Serving docs at http://127.0.0.1:${port}"; uv run mkdocs serve -a 127.0.0.1:${port}

snapshot run_id="latest": _require-external-uv-env
    {{cli}} snapshot --run-id "{{ run_id }}"

sensitivity run_id="latest" workers="6": _require-external-uv-env
    {{cli}} sensitivity --run-id "{{ run_id }}" --workers "{{ workers }}"

_build-panel start="2016-07-19" end="": _require-external-uv-env
    {{cli}} build-panel --start "{{ start }}" {{ if end == "" { "" } else { "--end \"" + end + "\"" } }}

_evaluate run_id="" workers="" suite="benchmark" force="false" tail_side="both" no_resume="false": _require-external-uv-env
    {{cli}} evaluate {{ if run_id == "" { "" } else { "--run-id \"" + run_id + "\"" } }} {{ if workers == "" { "" } else { "--workers " + workers } }} --suite "{{ suite }}" --tail-side "{{ tail_side }}" {{ if force == "true" { "--force" } else { "" } }} {{ if no_resume == "true" { "--no-resume" } else { "" } }}

_run start="2016-07-19" end="" workers="" suite="all" force="false" tail_side="both" no_resume="false": _require-external-uv-env
    {{cli}} run --start "{{ start }}" {{ if end == "" { "" } else { "--end \"" + end + "\"" } }} {{ if workers == "" { "" } else { "--workers " + workers } }} --suite "{{ suite }}" --tail-side "{{ tail_side }}" {{ if force == "true" { "--force" } else { "" } }} {{ if no_resume == "true" { "--no-resume" } else { "" } }}

_export-tables run_id="": _require-external-uv-env
    {{cli}} export-tables {{ if run_id == "" { "" } else { "--run-id \"" + run_id + "\"" } }}

_leakage-check run_id="": _require-external-uv-env
    {{cli}} leakage-check {{ run_id }}

_kernel: _require-external-uv-env
    uv run python -m ipykernel install --user --name n225-open-gap-tail --display-name "Python (n225-open-gap-tail)"

agent *args:
    @runner="{{ justfile_directory() }}/../agent-runner"; if [[ ! -d "$runner" ]]; then echo "error: agent-runner not found at $runner" >&2; exit 1; fi; cd "$runner"; env -u UV_PROJECT_ENVIRONMENT just {{ args }}
