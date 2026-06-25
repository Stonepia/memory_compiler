# START HERE — Dev Memory Compiler Agent Bootstrap Plan

You are a fresh coding agent. You have no trusted memory from previous chat turns. Your only reliable inputs are the files in this bootstrap pack and the repository files you inspect yourself.

Your job is to build **Dev Memory Compiler (DMC)** as a thin local memory/context sidecar for coding agents. DMC must help future agents plan, inspect, execute, record, distill, and reuse development experience across sessions.

DMC is **not** a generic chat memory product. DMC exists to preserve development experience from codebases, hardware specs, tests, profiler/benchmark artifacts, debugging trajectories, wrong turns, and project state.

---

## 0. Non-negotiable rules

1. **State-first execution**: before doing any work, read `agent_state.json`. If it does not exist, create it from `templates/agent_state.initial.json`.
2. **Every task assumes a fresh agent**: never rely on conversation history. Read the module card and the listed context files.
3. **One claimable unit at a time**: claim one module or integration gate, complete it, validate it, write a handoff, update state.
4. **No wheel reinvention**: use uv, Pydantic, Typer, Rich, PyYAML, SQLite/FTS5, pytest, ruff, and MCP Python SDK/FastMCP. Do not implement repo graph, vector DB, graph DB, web UI, agent harness, sandbox, custom code indexer, or profiler parsers in v0.
5. **DMC is a sidecar, not a harness**: Codex/Copilot/OpenCode/Claude/Cursor remain the execution agents. DMC provides schemas, local store, PlanGraph, briefing, precheck, event logging, distillation, eval cases, and adapter files.
6. **No fake completion**: a module cannot be marked `done` unless all acceptance commands pass and an acceptance report is written.
7. **No silent test weakening**: do not remove or weaken tests to pass. If a test is wrong, explain why in the handoff and add a replacement test.
8. **No dynamic facts inside stable rules**: `AGENTS.md`, Copilot instructions, and OpenCode skills contain protocol only. Project state lives under `.dmc/state/project_state.yaml`.
9. **Evidence over prose**: every state update, skill proposal, eval case, failure mode, and benchmark claim must carry provenance fields.
10. **User maintenance cost matters**: prefer fewer modules, fewer moving parts, plain files, and local-first behavior.

---

## 1. First action for any agent

Run this exact checklist:

```text
1. Read this file: START_HERE.md.
2. Read docs/PROJECT_INDEX.md.
3. Read agent_state.json if present; otherwise create it from templates/agent_state.initial.json.
4. Determine the next claimable unit:
   - status == "ready"
   - dependencies are done
   - no unresolved blocker
5. Read the module card listed in agent_state.modules[MODULE_ID].module_doc.
6. Read every file listed under that module card's "Must-read context".
7. Implement only the required scope.
8. Run the module's acceptance commands.
9. Write reports/handoffs/<MODULE_ID>_<attempt_id>.md.
10. Update agent_state.json.
```

If there are multiple ready modules, pick the lowest module ID unless `agent_state.json` explicitly prioritizes another module.

---

## 2. Agent loop

This is the full local loop. A human should be able to give only this `START_HERE.md` to a coding agent, and the agent should know how to continue.

```pseudo
while project not delivered:
    read agent_state.json
    validate agent_state against templates/agent_state.schema.json

    if agent_state.project_status == "uninitialized":
        claim M00_BOOTSTRAP
    else:
        claim first module where:
            status in ["ready", "needs_revision"]
            dependencies are done
            blockers is empty

    if no module is claimable:
        if integration gate is ready:
            claim next integration gate
        else:
            write a blocker report and stop

    read module_doc and all must-read context files
    implement scope exactly
    run acceptance commands exactly

    if acceptance passes:
        write acceptance report
        mark module done
        unblock dependents
    else:
        write failure report
        mark module needs_revision or blocked with exact reason

    update agent_state.json atomically
```

State updates must be atomic: write to `agent_state.json.tmp`, validate it, then replace `agent_state.json`.

---

## 3. Project phases

### P0 — Documentation and scaffold

Goal: create the repo skeleton, uv environment, state files, package structure, test harness, and generated docs.

Must deliver:

```text
pyproject.toml
uv.lock
src/dmc/
tests/
.dmc/
agent_state.json
AGENTS.md
README.md
```

### V0 — Local core

Goal: make DMC usable locally without any LLM, vector DB, UI, external MCP dependency, or agent harness.

Must deliver:

```text
schemas
local store
PlanGraph validator
Mermaid/Markdown renderer
local retriever
precheck engine
event recorder
distiller/eval-case stub compiler
Typer CLI
pytest coverage for each module
```

### V0.5 — MCP and adapters

Goal: expose DMC to Codex/Copilot/OpenCode/Claude-compatible surfaces through a thin MCP server and generated adapter bundles.

Must deliver:

```text
DMC MCP server with tools/resources/prompts
Codex AGENTS.md and .codex/config.toml.template
Copilot instructions and skill folder template
OpenCode AGENTS.md, opencode.jsonc.template, agents/skills templates
```

### V1 — PlanGraph loop and learning loop

Goal: support editable execution graphs, session-to-eval compilation, failure mode/precheck compilation, and visual review.

Must deliver:

```text
PlanGraph execution readiness states
Mermaid graph renderer
session -> episode -> eval_case -> failure_mode -> skill_update_proposal
integration tests across two fake sessions
```

---

## 4. Required project architecture

```text
Codex / Copilot / OpenCode / Claude / Cursor
        |
        | MCP + AGENTS.md / skills / instructions
        v
DMC Adapter Layer
        |
        v
DMC Core
  - plan_task
  - get_briefing
  - search
  - precheck
  - record_event
  - commit_state
  - distill_session
  - propose_skill_update
        |
        v
Local Store
  - SQLite + FTS5
  - YAML/Markdown human-editable objects
  - JSONL append-only trace
  - filesystem artifacts
        |
        v
External existing tools, not reimplemented by DMC
  - Serena MCP for repo symbols/code navigation
  - GitHub MCP for issues/PRs/commits
  - Sourcegraph MCP for large/cross-repo search, optional
  - Basic Memory MCP for Markdown notes/specs, optional
```

---

## 5. Required repo layout after bootstrap

```text
.
├── START_HERE.md
├── README.md
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── agent_state.json
├── src/
│   └── dmc/
│       ├── __init__.py
│       ├── cli.py
│       ├── schemas.py
│       ├── store.py
│       ├── planner.py
│       ├── renderer.py
│       ├── retriever.py
│       ├── precheck.py
│       ├── recorder.py
│       ├── distiller.py
│       ├── evals.py
│       ├── mcp_server.py
│       └── adapters.py
├── tests/
│   ├── test_schemas.py
│   ├── test_store.py
│   ├── test_plan_graph.py
│   ├── test_renderer.py
│   ├── test_retriever.py
│   ├── test_precheck.py
│   ├── test_recorder.py
│   ├── test_distiller.py
│   ├── test_cli.py
│   └── golden/
├── .dmc/
│   ├── config.yaml
│   ├── state/
│   │   ├── project_state.yaml
│   │   └── active_task.yaml
│   ├── plans/
│   ├── memory/
│   │   ├── events.jsonl
│   │   ├── sessions/
│   │   ├── episodes/
│   │   ├── failure_modes/
│   │   └── eval_cases/
│   ├── skills/
│   │   ├── tier0/
│   │   ├── tier1/
│   │   └── tier2/
│   ├── knowledge/
│   │   ├── repo/
│   │   ├── tests/
│   │   ├── perf/
│   │   ├── hw/
│   │   └── specs/
│   ├── artifacts/
│   │   ├── index.jsonl
│   │   └── raw/
│   ├── proposals/
│   │   ├── pending/
│   │   ├── accepted/
│   │   └── rejected/
│   └── adapters/
│       ├── codex/
│       ├── copilot/
│       └── opencode/
└── reports/
    ├── handoffs/
    ├── acceptance/
    └── integration/
```

---

## 6. Implementation order

Implement modules in this order unless `agent_state.json` says otherwise:

```text
M00_BOOTSTRAP
M01_SCHEMAS
M02_STORE
M03_PLAN_GRAPH
M04_RENDERER
M05_RETRIEVER
M06_PRECHECK
M07_RECORDER
M08_DISTILLER_EVALS
M09_MCP_SERVER
M10_ADAPTERS
M11_CLI
G01_INTEGRATION_V0
G02_DELIVERY_V0
```

---

## 7. Minimal command set

After bootstrap, these commands must exist:

```bash
uv run dmc --help
uv run dmc state show
uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml
uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd
uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md
uv run dmc search "BMG occupancy low" --scope skills --scope memory
uv run dmc precheck examples/sample_action.yaml
uv run dmc record examples/sample_event.yaml
uv run dmc distill --session sess_demo
uv run dmc export-agent-bundle --target codex --out .dmc/adapters/codex
uv run pytest
uv run ruff check .
```

---

## 8. v0 quality bar

A module is not done until all are true:

```text
[ ] All inputs and outputs match its module card.
[ ] All public functions have typed signatures.
[ ] All schemas reject invalid examples.
[ ] Tests include positive and negative cases.
[ ] Acceptance commands pass from a clean checkout after `uv sync`.
[ ] No hidden network requirement except dependency installation.
[ ] No vector DB, graph DB, UI, custom repo indexer, or autonomous agent harness.
[ ] Handoff report exists and links changed files/tests.
[ ] agent_state.json updated.
```

---

## 9. Strong stop conditions

Stop and write a blocker report instead of guessing when:

```text
- Required context file is missing.
- agent_state.json is invalid and cannot be repaired from template.
- A dependency module is not done.
- A required open-source dependency is unavailable.
- Tests fail for reasons outside the module's scope.
- The requested work would require building a forbidden system in v0.
```

Do not ask the user to clarify unless the repo state truly prevents execution. Prefer writing a precise blocker report that a later agent can act on.
