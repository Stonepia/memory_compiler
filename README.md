# Dev Memory Compiler (DMC)

DMC is a local-first memory/context sidecar for coding agents (Codex, Copilot,
OpenCode, Claude, Cursor). It preserves development experience — codebase
context, hardware specs, tests, profiler/benchmark artifacts, debugging
trajectories, wrong turns, and project state — so future agents can plan,
inspect, execute, record, distill, and reuse that experience across sessions.

DMC is a **sidecar, not a harness**. It does not solve tasks autonomously and
does not replace the execution agent.

## Status

**V0 delivered.** The full local loop works end-to-end: schemas, the local
store (SQLite/FTS5), PlanGraph, rendering, retrieval, precheck, recording,
distillation, the MCP server, agent adapters, and the `dmc` CLI are all
implemented and covered by tests. See `CHANGELOG.md` and
`reports/integration/v0_delivery_report.md`.

## Quick start

Install and verify:

```bash
uv sync
uv run dmc --help
uv run pytest
uv run ruff check .
```

Run the whole V0 loop from a sample task to agent bundles:

```bash
# Plan a task into a PlanGraph, then render it.
uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml
uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd

# Build a briefing, precheck an action, record an event.
uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md
uv run dmc precheck examples/sample_action.yaml --out precheck_result.json
uv run dmc record examples/sample_event.yaml

# Distill a session into reusable memory (episode/eval/failure/proposal).
uv run dmc distill --session sess_demo

# Export instructions for your agent (codex | copilot | opencode).
uv run dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot

# Serve the MCP tools over stdio.
uv run dmc serve --root .
```

Every subcommand reads/writes the local `.dmc/` tree and fails with a clear,
non-zero error when inputs are missing or invalid.

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
