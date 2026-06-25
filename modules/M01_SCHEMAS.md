# M01_SCHEMAS — Define all durable Pydantic schemas

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M00_BOOTSTRAP

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/AGENT_STATE_PROTOCOL.md`
- `docs/v0/02_ARCHITECTURE.md`
- `templates/plan_graph.schema.json`
- `templates/trace_event.schema.json`
- `templates/eval_case.schema.json`
- `modules/M01_SCHEMAS.md`

## Scope

Implement `src/dmc/schemas.py`. This is the contract module. Other modules must import these schemas rather than defining their own data shapes.

Export JSON schemas under `.dmc/generated_schemas/` or `schemas/` via a CLI/helper if simple.

## Required public API / inputs / outputs

### Required models

```python
class Provenance(BaseModel): ...
class EvidenceRef(BaseModel): ...
class TaskRequest(BaseModel): ...
class ProjectState(BaseModel): ...
class SkillCard(BaseModel): ...
class Tier0Policy(BaseModel): ...
class Tier1Workflow(BaseModel): ...
class Tier2Atom(BaseModel): ...
class KnowledgeRef(BaseModel): ...
class ArtifactCard(BaseModel): ...
class TraceEvent(BaseModel): ...
class PlanNode(BaseModel): ...
class PlanGraph(BaseModel): ...
class SearchRequest(BaseModel): ...
class SearchResult(BaseModel): ...
class PrecheckRequest(BaseModel): ...
class PrecheckResult(BaseModel): ...
class EpisodeCard(BaseModel): ...
class FailureMode(BaseModel): ...
class SkillUpdateProposal(BaseModel): ...
class EvalCase(BaseModel): ...
class AgentState(BaseModel): ...
```

### Required validation rules

```text
- IDs are non-empty slug-like strings.
- URIs use known prefixes where applicable.
- PlanNode dependencies reference existing nodes.
- TraceEvent has session_id, event_id, phase, action.kind, and outcome.
- Evidence-bearing objects require provenance list; empty provenance is invalid for final memory objects.
- EvalCase must include task, plan refs, outcome, labels, and provenance.
```

### Outputs

```text
- src/dmc/schemas.py
- tests/test_schemas.py
- generated schema files or tests validating model_json_schema()
```

## Strong acceptance commands

- `uv run pytest tests/test_schemas.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not define duplicate dataclasses in other files.
- Do not silently coerce invalid objects into valid objects.

## Required handoff

Write:

```text
reports/handoffs/M01_SCHEMAS_<attempt_id>.md
reports/acceptance/M01_SCHEMAS_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
