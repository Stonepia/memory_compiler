# M04_RENDERER — Render PlanGraph and briefing to Markdown/Mermaid

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M03_PLAN_GRAPH

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v1/01_VISUALIZATION_OPTIONAL.md`
- `modules/M04_RENDERER.md`
- `reports/handoffs/M03_PLAN_GRAPH_<latest>.md`

## Scope

Implement pure rendering functions. V0 visualization is Mermaid text and Markdown only.

## Required public API / inputs / outputs

### Required public API

```python
def render_plan_mermaid(graph: PlanGraph) -> str: ...
def render_plan_markdown(graph: PlanGraph) -> str: ...
def render_briefing(request: TaskRequest, graph: PlanGraph, context: list[SearchResult] | None = None) -> str: ...
def write_rendered(text: str, path: Path) -> None: ...
```

### Inputs

```text
PlanGraph, TaskRequest, SearchResult list
```

### Outputs

```text
Mermaid flowchart text, Markdown briefing text
```

### Rendering requirements

```text
- Mermaid output starts with flowchart TD or flowchart LR.
- Node labels include node id and type.
- Human review gates are visible.
- Evidence gates are visible.
- Markdown briefing includes selected workflows, atoms, knowledge refs, pitfalls, open questions, next actions.
```

## Strong acceptance commands

- `uv run pytest tests/test_renderer.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not build HTML UI in V0.
- Do not import frontend frameworks.

## Required handoff

Write:

```text
reports/handoffs/M04_RENDERER_<attempt_id>.md
reports/acceptance/M04_RENDERER_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
