# Changelog

All notable changes to the Dev Memory Compiler (DMC) are documented here.
This project adheres to a module-by-module delivery protocol; each release
corresponds to a completed phase gate.

## [0.1.0] — 2026-07-01 — V0 (delivered)

First end-to-end release of the local-first memory/context sidecar. DMC is a
**sidecar, not a harness**: it preserves and replays development experience but
never solves tasks autonomously.

### Added

- **Schemas (`M01`)** — Pydantic contracts for tasks, project state, plan
  graphs, trace events, search/precheck requests and results, and distillation
  outputs (episodes, eval cases, failure modes, proposals). Single contract
  module `src/dmc/schemas.py`.
- **Local store (`M02`)** — File + SQLite/FTS5 store rooted at `<root>/.dmc`
  (`DMCStore`): project state, object read/write, full-text search, event log,
  and pending proposals. Uses only the Python stdlib `sqlite3`.
- **PlanGraph (`M03`)** — Deterministic 8-node task plan
  (brief → inspect → plan → edit → test → review → decide → distill) with
  validation, topological ordering, and ready-node computation.
- **Renderer (`M04`)** — Mermaid (`flowchart TD`) and Markdown plan renderers
  plus a six-section task briefing renderer.
- **Retriever (`M05`)** — Scoped FTS retrieval over project state, skills,
  knowledge, artifacts, episodes, failure modes, eval cases, and proposals.
- **Precheck (`M06`)** — Rule-based action gate returning `allow` / `warn` /
  `block` before an agent edits or runs commands.
- **Recorder (`M07`)** — Append-only trace event recording to
  `.dmc/memory/events.jsonl`.
- **Distiller + evals (`M08`)** — Turns a recorded session into reusable
  memory: an episode, an eval case, failure modes, and a pending improvement
  proposal.
- **MCP server (`M09`)** — FastMCP server (`dmc serve`) exposing the core as
  MCP tools over stdio.
- **Adapters (`M10`)** — Agent bundle generation for **Codex**, **Copilot**
  (under `.github/`), and **OpenCode**. Output directory is always explicit;
  no silent overwrite of repo root files.
- **CLI (`M11`)** — The `dmc` Typer CLI: `plan`, `graph`, `brief`, `search`,
  `precheck`, `record`, `distill`, `state show/commit`, `schemas-export`,
  `serve`, and `export-agent-bundle`. Commands are thin adapters over the core;
  `--dmc-root` overrides the data tree; a `--out` path ending in `.json` is
  written as valid JSON (YAML otherwise and for stdout); failures exit non-zero
  with clear errors.

### Integration (`G01`)

The full V0 loop was verified end-to-end through the CLI:
`sample task → plan graph → graph render → briefing → precheck → record event →
distill session → eval case → adapter bundle` (all three bundles generated).

### Tooling

- Python 3.11+, `uv`, Pydantic, Typer + Rich, PyYAML, SQLite/FTS5 (stdlib),
  pytest, ruff. All Python runs through `uv run`.
- Test suite: **286 tests passing**; `ruff check .` clean.

### Known limitations

- Planning is a fixed deterministic 8-node template; there is no adaptive or
  learned plan graph yet (that is V1 scope).
- Retrieval is lexical (SQLite FTS5) only — no semantic/vector search.
- Distillation heuristics are rule-based and produce **pending** proposals for
  human review; nothing is auto-promoted into skills/knowledge.
- The MCP server targets stdio transport for local single-user use.
- No CI is wired in this repo yet; acceptance is run locally via the commands
  above.

### Deliberately not built in V0

Per `docs/TOOL_POLICY.md`: no custom repo graph, custom symbol/code indexer,
custom call graph, vector database, graph database, RAG platform, web
UI/dashboard, full agent harness, sandbox runner, multi-agent orchestrator,
cloud sync, or training pipelines.

### Next phase

See `docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md` and
`docs/v1/01_VISUALIZATION_OPTIONAL.md` for the V1 direction: an adaptive plan
graph and a learning loop that promotes reviewed proposals into durable memory.
