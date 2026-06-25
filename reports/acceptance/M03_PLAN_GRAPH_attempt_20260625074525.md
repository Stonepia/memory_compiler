# Acceptance Report: M03_PLAN_GRAPH

- Module: `M03_PLAN_GRAPH`
- Attempt: `attempt_20260625074525`
- Agent: `module-impl-agent-M03`
- Date: `2026-06-25T07:45:25Z`

## Scope completed

Deterministic, rule/template-based PlanGraph logic in `src/dmc/planner.py`:
creation (`plan_task`), validation (`validate_plan_graph`), readiness
(`topological_nodes`, `next_ready_nodes`), and persistence
(`save_plan_graph`/`load_plan_graph`). No LLM, no node execution, no
orchestrator.

## Files changed

- `src/dmc/planner.py` — new module (public API + helpers).
- `src/dmc/schemas.py` — added `ValidationReport` model (to `__all__` and
  `EXPORTED_MODELS`).
- `tests/test_plan_graph.py` — new test file (32 tests).
- `agent_state.json` — claim + completion state transitions; unblocked M04.
- `reports/handoffs/M03_PLAN_GRAPH_attempt_20260625074525.md` — handoff.

## Public APIs implemented

- `validate_plan_graph(graph: PlanGraph) -> ValidationReport`
- `topological_nodes(graph: PlanGraph) -> list[PlanNode]`
- `next_ready_nodes(graph: PlanGraph, completed_node_ids: set[str]) -> list[PlanNode]`
- `plan_task(request: TaskRequest, store: DMCStore | None = None) -> PlanGraph`
- `save_plan_graph(graph: PlanGraph, path: Path) -> None`
- `load_plan_graph(path: Path) -> PlanGraph`

## Tests added or changed

Added `tests/test_plan_graph.py` (32 tests), positive AND negative:
- validate: accepts well-formed graph and `plan_task` output; rejects duplicate
  ids, dangling deps, cycles, self-dep, empty goal, empty success_criteria,
  invalid node type, non-object evidence_contract, missing/non-boolean
  human_review; rejects non-`PlanGraph` arg.
- topological_nodes: correct order for a DAG, deterministic for independent
  nodes, respects dependencies, raises on a cycle.
- next_ready_nodes: empty / partial / full completed sets, multi-dependency.
- plan_task: valid + allowed types, deterministic, linear spine, rejects
  non-TaskRequest.
- save/load: YAML and JSON round-trip (semantic equality), parent-dir creation,
  missing-file and non-mapping errors, non-PlanGraph save error.

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv run pytest tests/test_plan_graph.py` | pass | 32 passed in 0.23s |
| `uv run pytest` | pass | 116 passed in 0.33s (incl. M01/M02 suites) |
| `uv run ruff check .` | pass | All checks passed! |
| `uv run dmc --help` | pass | exit code 0 |
| `uv sync` | pass | Resolved 22 packages; no dependency changes |

## Acceptance checklist

```text
[x] All module commands passed.
[x] Tests include positive and negative cases.
[x] No forbidden V0 system was implemented.
[x] No dynamic facts were inserted into stable instruction files.
[x] Handoff report written.
[x] agent_state.json updated.
```

## No-forbidden-work checklist

```text
[x] No LLM call.
[x] No plan-node execution.
[x] No orchestrator / scheduler / runtime loop.
[x] No vector DB, graph DB, web UI, custom repo indexer, or agent harness.
[x] No new external dependency added.
[x] No placeholder / no-op pass-through; behavior is deterministic and tested.
[x] No test deleted or weakened.
```

## Dependency changes

- No external dependency changes.
- Contract change: added `ValidationReport` to `src/dmc/schemas.py` (single
  source of data shapes) so planner and downstream modules share one validation
  result type instead of duplicating it. Pre-existing M01 tests remain green
  (the schema-export count test uses `len(EXPORTED_MODELS)`).

## Known limitations

- `plan_task` uses a single fixed linear template; it does not branch on task
  mode/hardware and does not consult `store`/project state to shape the plan
  (accepted as optional in the module card; reserved for later versions).
- `benchmark`/`profile` node types are supported by the validator and schema
  but are not emitted by the default template.

## Evidence links

- `src/dmc/planner.py`
- `tests/test_plan_graph.py`
- `reports/handoffs/M03_PLAN_GRAPH_attempt_20260625074525.md`
