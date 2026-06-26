# M09_MCP_SERVER — Expose DMC through MCP tools/resources/prompts

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE
- M03_PLAN_GRAPH
- M04_RENDERER
- M05_RETRIEVER
- M06_PRECHECK
- M07_RECORDER
- M08_DISTILLER_EVALS

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/TOOL_POLICY.md`
- `docs/v0/02_ARCHITECTURE.md`
- `modules/M09_MCP_SERVER.md`
- `reports/handoffs/M01_SCHEMAS_<latest>.md`
- `reports/handoffs/M08_DISTILLER_EVALS_<latest>.md`

## Scope

Implement a thin MCP server over existing DMC core functions. Use MCP Python SDK or FastMCP. Keep business logic in core modules, not in MCP handlers.

## Required public API / inputs / outputs

### Required MCP tools

```text
dmc_plan_task
dmc_render_graph
dmc_get_briefing
dmc_search
dmc_precheck
dmc_record_event
dmc_commit_state
dmc_distill_session
dmc_propose_skill_update
dmc_export_agent_bundle
```

> **Implementation note for `dmc_export_agent_bundle`**: Adapter bundle generation
> is owned by M10_ADAPTERS. M09 must expose this as a thin lazy wrapper only:
>
> ```python
> try:
>     from dmc.adapters import export_agent_bundle
>     result = export_agent_bundle(...)
> except ImportError:
>     return {"ok": False, "errors": ["M10_ADAPTERS not yet implemented"], "data": None}
> ```
>
> No M10 adapter logic should be duplicated inside M09.

### Required MCP resources

```text
dmc://project_state/current
dmc://briefing/latest
dmc://skill/tier1/{id}
dmc://skill/tier2/{id}
dmc://artifact/{id}
dmc://proposal/pending
```

### Required MCP prompts

```text
dmc:start-task
dmc:checkpoint
dmc:end-session-distill
dmc:review-skill-proposals
```

### Inputs/outputs

Each MCP tool must accept JSON-compatible input matching the Pydantic schema and return JSON-compatible output with `ok`, `data`, and `errors` fields.

## Strong acceptance commands

- `uv run pytest tests/test_mcp_server.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not duplicate core logic in handlers.
- Do not assume a specific agent client.
- Do not hardcode user paths.

## Required handoff

Write:

```text
reports/handoffs/M09_MCP_SERVER_<attempt_id>.md
reports/acceptance/M09_MCP_SERVER_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
