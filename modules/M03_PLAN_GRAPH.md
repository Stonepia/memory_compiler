# M03_PLAN_GRAPH — PlanGraph creation, validation, and readiness

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M00_BOOTSTRAP
- M01_SCHEMAS
- M02_STORE

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v0/02_ARCHITECTURE.md`
- `docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md`
- `modules/M03_PLAN_GRAPH.md`
- `reports/handoffs/M01_SCHEMAS_<latest>.md`
- `reports/handoffs/M02_STORE_<latest>.md`

## Scope

Implement deterministic PlanGraph logic. V0 planning can be template/rule-based. No LLM required.

## Required public API / inputs / outputs

### Required public API

```python
def validate_plan_graph(graph: PlanGraph) -> ValidationReport: ...
def topological_nodes(graph: PlanGraph) -> list[PlanNode]: ...
def next_ready_nodes(graph: PlanGraph, completed_node_ids: set[str]) -> list[PlanNode]: ...
def plan_task(request: TaskRequest, store: DMCStore | None = None) -> PlanGraph: ...
def save_plan_graph(graph: PlanGraph, path: Path) -> None: ...
def load_plan_graph(path: Path) -> PlanGraph: ...
```

### Inputs

```text
TaskRequest, optional store/project state, PlanGraph YAML/JSON
```

### Outputs

```text
validated PlanGraph, ordered nodes, ready nodes, saved YAML/JSON
```

### Required node types

```text
brief, inspect, plan, edit, test, benchmark, profile, review, decide, distill
```

### Validation requirements

```text
- no duplicate node IDs
- all dependencies exist
- graph has no cycles
- required node fields are non-empty
- evidence gates are valid schema objects
- human_review is explicit true/false
```

## Strong acceptance commands

- `uv run pytest tests/test_plan_graph.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not call an LLM.
- Do not execute plan nodes.
- Do not build an orchestrator.

## Required handoff

Write:

```text
reports/handoffs/M03_PLAN_GRAPH_<attempt_id>.md
reports/acceptance/M03_PLAN_GRAPH_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
