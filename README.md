# Dev Memory Compiler (DMC)

DMC is a local-first memory/context sidecar for coding agents (Codex, Copilot,
OpenCode, Claude, Cursor). It preserves development experience — codebase
context, hardware specs, tests, profiler/benchmark artifacts, debugging
trajectories, wrong turns, and project state — so future agents can plan,
inspect, execute, record, distill, and reuse that experience across sessions.

DMC is a **sidecar, not a harness**. It does not solve tasks autonomously and
does not replace the execution agent.

## Status

This repository is built module-by-module. Bootstrap (`M00_BOOTSTRAP`) creates
the repo skeleton, the `uv` environment, the `.dmc/` data tree, and a
smoke-testable CLI. Later modules implement schemas, the local store,
PlanGraph, rendering, retrieval, precheck, recording, distillation, the MCP
server, adapters, and the full CLI.

## Quick start

```bash
uv sync
uv run dmc --help
uv run pytest
uv run ruff check .
```

At bootstrap, `dmc` subcommands are placeholders that fail with a clear error
until their owning module is implemented.

## Layout

- `src/dmc/` — Python package (`dmc`), console script `dmc = "dmc.cli:main"`.
- `tests/` — pytest suite, including `tests/golden/` fixtures.
- `.dmc/` — local data tree: config, state, plans, memory, skills, knowledge,
  artifacts, proposals, adapters.
- `reports/` — handoff, acceptance, and integration reports.
- `examples/` — sample task/action/event inputs.

## Where to start

`START_HERE.md` is the single entrypoint and execution protocol. Agents read it
first, then `docs/PROJECT_INDEX.md`, then `agent_state.json`.

## Tech stack

Python 3.11+, uv, Pydantic, Typer + Rich, PyYAML, SQLite/FTS5 (stdlib), pytest,
ruff. See `docs/TOOL_POLICY.md` for what to reuse and what not to build in v0.
