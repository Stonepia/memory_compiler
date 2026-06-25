# G01_INTEGRATION_V0 — End-to-end V0 integration gate

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M00_BOOTSTRAP
- M01_SCHEMAS
- M02_STORE
- M03_PLAN_GRAPH
- M04_RENDERER
- M05_RETRIEVER
- M06_PRECHECK
- M07_RECORDER
- M08_DISTILLER_EVALS
- M09_MCP_SERVER
- M10_ADAPTERS
- M11_CLI

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/ACCEPTANCE_PROTOCOL.md`
- `docs/v0/04_INTEGRATION_AND_DELIVERY.md`
- `all reports/handoffs/*.md`
- `all reports/acceptance/*.md`

## Scope

Run the whole V0 loop from sample task to adapter bundle. Fix only integration glue; do not redesign modules unless a blocker report requires revision.

## Required public API / inputs / outputs

### Required integration scenario

```text
sample_task.yaml -> plan_graph.yaml -> plan_graph.mmd -> briefing.md -> precheck_result.json -> events.jsonl -> eval_case -> proposal -> codex/copilot/opencode bundles
```

### Required report

```text
reports/integration/v0_integration_report.md
```

## Strong acceptance commands

- `uv sync`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`
- `uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml`
- `uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd`
- `uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md`
- `uv run dmc precheck examples/sample_action.yaml --out reports/integration/precheck_result.json`
- `uv run dmc record examples/sample_event.yaml`
- `uv run dmc distill --session sess_demo`
- `uv run dmc export-agent-bundle --target codex --out .dmc/adapters/codex`
- `uv run dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot`
- `uv run dmc export-agent-bundle --target opencode --out .dmc/adapters/opencode`

## Module-specific forbidden shortcuts

- Do not skip any module tests.
- Do not mark integration passed if adapter bundles are missing.

## Required handoff

Write:

```text
reports/handoffs/G01_INTEGRATION_V0_<attempt_id>.md
reports/acceptance/G01_INTEGRATION_V0_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
