# Acceptance Report: M09_MCP_SERVER

- Module: `M09_MCP_SERVER`
- Attempt: `attempt_20260629053105`
- Agent: `module-impl-agent-M09`
- Date: `2026-06-29T05:31:17Z`

## Scope completed

Thin MCP server over DMC core: 10 tools, 6 resources, 4 prompts, plus a
programmatic `build_server(root)` and stdio `main()` entry, wired to a new
`dmc serve` CLI command. All handlers delegate to core modules.

## Files changed

- `src/dmc/mcp_server.py` (new)
- `tests/test_mcp_server.py` (new)
- `tests/test_store.py` (added pending-proposal enumeration tests)
- `src/dmc/store.py` (added `list_pending_proposals`)
- `src/dmc/cli.py` (added `serve`)
- `pyproject.toml`, `uv.lock` (added `mcp>=1.28.1`)
- `.gitignore` (ignore `*.sqlite3` / `.dmc/index.sqlite3`; untracked the cache)
- `agent_state.json`

## Public APIs implemented

- Tools: `dmc_plan_task`, `dmc_render_graph`, `dmc_get_briefing`, `dmc_search`,
  `dmc_precheck`, `dmc_record_event`, `dmc_commit_state`, `dmc_distill_session`,
  `dmc_propose_skill_update`, `dmc_export_agent_bundle` (lazy M10 wrapper).
  Tools register with explicit top-level fields mirroring the DMC Pydantic
  schemas so FastMCP input schemas are flat (no nested `{"task":{...}}` wrapper).
- Resources: `dmc://project_state/current`, `dmc://briefing/latest`,
  `dmc://skill/tier1/{id}`, `dmc://skill/tier2/{id}`, `dmc://artifact/{id}`,
  `dmc://proposal/pending`.
- Prompts: `dmc:start-task`, `dmc:checkpoint`, `dmc:end-session-distill`,
  `dmc:review-skill-proposals`.
- `build_server(root)`, `main(root)`, `resolve_root`, `envelope`.
- Core: `DMCStore.list_pending_proposals() -> (entries, errors)`.

## Tests added or changed

`tests/test_mcp_server.py` — 27 tests: each tool envelope/happy path, lazy
export fallback, invalid-input -> ok=False, resources resolve + missing-id
graceful, prompt text, server registration; plus MCP-level
`test_tool_input_schemas_are_flat_not_wrapped`, `test_read_resource_all_six`,
`test_all_four_prompts_registered`, `test_resource_proposal_pending_surfaces_corrupt`.
`tests/test_store.py` — `test_list_pending_proposals_empty`,
`_returns_entries`, `_surfaces_corrupt`. No network.

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv run dmc serve --help` | pass | exit 0 |
| `uv run pytest tests/test_mcp_server.py` | pass | 27 passed |
| `uv run pytest` | pass | 239 passed |
| `uv run ruff check .` | pass | All checks passed |
| `uv run dmc --help` | pass | exit 0 |
| `uv sync` | pass | 45 packages resolved |

## Acceptance checklist

```text
[x] All module commands passed.
[x] Tests include positive and negative cases.
[x] No forbidden V0 system was implemented.
[x] No dynamic facts were inserted into stable instruction files.
[x] Handoff report written.
[x] agent_state.json updated.
```

## Known limitations

- `dmc_export_agent_bundle` returns ok=False until M10 lands; a genuine broken
  import from inside `dmc.adapters` is reported distinctly (not masked).
- `dmc://briefing/latest` reads `.dmc/briefing.md` if present (none until CLI).

## Dependency changes

Added `mcp>=1.28.1` (MCP Python SDK incl. FastMCP) via `uv add mcp`; `uv lock`
resolves the latest available (1.28.1). `mcp` chosen over `fastmcp`; installed
cleanly. Transitive `jsonschema` pulled in by `mcp` but NOT added to
`pyproject.toml`.

## No-forbidden-work checklist

No vector/graph DB, web UI, agent harness, sandbox, or custom indexer. Server
is thin; logic remains in core modules.

## Evidence links

- `reports/handoffs/M09_MCP_SERVER_attempt_20260629053105.md`
