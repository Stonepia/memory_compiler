# M07_RECORDER — Trace event and artifact recording

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v0/02_ARCHITECTURE.md`
- `docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md`
- `modules/M07_RECORDER.md`
- `reports/handoffs/M02_STORE_<latest>.md`

## Scope

Implement action-level event recording. DMC records what happened; it does not store raw transcript as the primary memory object.

## Required public API / inputs / outputs

### Required public API

```python
def record_event(event: TraceEvent, store: DMCStore) -> str: ...
def record_artifact(card: ArtifactCard, store: DMCStore, raw_path: Path | None = None) -> str: ...
def session_events(session_id: str, store: DMCStore) -> list[TraceEvent]: ...
def summarize_session_trace(session_id: str, store: DMCStore) -> dict: ...
```

### Inputs

```text
TraceEvent, ArtifactCard, optional raw artifact path
```

### Outputs

```text
event URI, artifact URI, session trace summary
```

### Required event phases

```text
localize, inspect, plan, edit, test, benchmark, profile, analyze, validate, review, distill
```

### Required action kinds

```text
command, file_read, file_edit, test_run, benchmark_run, profiler_run, asm_dump, tool_call, human_note
```

## Strong acceptance commands

- `uv run pytest tests/test_recorder.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not store large raw artifacts inside JSONL. Store URI/path only.
- Do not treat natural language transcript as the only event representation.

## Required handoff

Write:

```text
reports/handoffs/M07_RECORDER_<attempt_id>.md
reports/acceptance/M07_RECORDER_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
