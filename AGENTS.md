# AGENTS.md — DMC Agent Protocol

This file contains **protocol only**. It must never contain dynamic project
state. Dynamic facts (status, phase, completed modules, project knowledge) live
in `.dmc/state/project_state.yaml` and `agent_state.json`.

## Single entrypoint

`START_HERE.md` is the only entrypoint. Read it first, then
`docs/PROJECT_INDEX.md`, then `agent_state.json`.

## Non-negotiable rules

1. **State-first execution.** Read `agent_state.json` before any work. If it is
   missing, create it from `templates/agent_state.initial.json` and validate it
   against `templates/agent_state.schema.json`.
2. **Every task assumes a fresh agent.** Never rely on conversation history.
   Read the module card and its listed context files.
3. **One claimable unit at a time.** Claim one module or integration gate,
   complete it, validate it, write a handoff, update state.
4. **No wheel reinvention.** Use uv, Pydantic, Typer, Rich, PyYAML,
   SQLite/FTS5, pytest, ruff, and (later) the MCP Python SDK/FastMCP.
5. **DMC is a sidecar, not a harness.** The execution agent remains in control.
6. **No fake completion.** A module is `done` only when all acceptance commands
   pass and an acceptance report is written.
7. **No silent test weakening.** Do not remove or weaken tests to pass.
8. **No dynamic facts in stable rules.** Keep this file and other instruction
   files protocol-only; put dynamic state under `.dmc/state/`.
9. **Evidence over prose.** State updates, proposals, eval cases, failure
   modes, and benchmark claims carry provenance.
10. **User maintenance cost matters.** Prefer fewer modules, plain files, and
    local-first behavior.
11. **uv-only execution. Never the system interpreter.** Run all Python through
    `uv run` (or `uv run --with <pkg>` for tooling not in project deps). Never
    invoke bare `python`/`python3`, a python shebang, or any globally-installed
    package. Relying on the system interpreter is a forbidden hidden
    local-machine dependency and breaks reproducibility on a clean checkout.

## Forbidden in v0

Do not implement: custom repo graph, custom symbol/code indexer, custom call
graph, vector database, graph database, RAG platform, web UI/dashboard, full
agent harness, sandbox runner, multi-agent orchestrator, automatic profiler
parser framework, cloud sync, or training pipelines. See `docs/TOOL_POLICY.md`.

## Agent loop (summary)

1. Read `START_HERE.md` and `docs/PROJECT_INDEX.md`.
2. Read and validate `agent_state.json`.
3. Pick the next claimable module: `status` in `ready`/`needs_revision`, all
   dependencies `done`, no blockers. Lowest module id wins unless state says
   otherwise.
4. Read the module card and its must-read context.
5. Implement only that module's scope.
6. Run the module acceptance commands.
7. Write `reports/handoffs/<MODULE_ID>_<attempt_id>.md` and
   `reports/acceptance/<MODULE_ID>_<attempt_id>.md`.
8. Update `agent_state.json` atomically (write `.tmp`, validate, replace).

## Minimum acceptance commands

```bash
uv sync
uv run pytest
uv run ruff check .
uv run dmc --help
```

## State update discipline

State writes are atomic: write `agent_state.json.tmp`, validate it against
`templates/agent_state.schema.json`, then replace `agent_state.json`. Never
mark a module `done` without passing acceptance and a written report.

## State-schema validation path

`jsonschema` is intentionally **not** a project dependency, so it is absent
from the uv venv. Validating `agent_state.json` against
`templates/agent_state.schema.json` must therefore use uv's ephemeral layer —
never the system interpreter (which may or may not have `jsonschema` installed):

```bash
uv run --with jsonschema python -c "import json, jsonschema; jsonschema.validate(json.load(open('agent_state.json')), json.load(open('templates/agent_state.schema.json')))"
```

Do not add `jsonschema` to `pyproject.toml`. Do not fall back to `python3`.
