# M02_STORE — Local file + SQLite/FTS5 store

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M00_BOOTSTRAP
- M01_SCHEMAS

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/TOOL_POLICY.md`
- `docs/v0/02_ARCHITECTURE.md`
- `modules/M02_STORE.md`
- `reports/handoffs/M01_SCHEMAS_<latest>.md if present`

## Scope

Implement a local-first store. It must use plain files as source of truth for human-editable objects and SQLite/FTS5 as an index/cache. It must work in temporary directories for tests.

## Required public API / inputs / outputs

### Required public API

```python
class DMCStore:
    def __init__(self, root: Path) -> None: ...
    def initialize(self) -> None: ...
    def append_event(self, event: TraceEvent) -> str: ...
    def list_events(self, session_id: str | None = None) -> list[TraceEvent]: ...
    def write_object(self, kind: str, object_id: str, data: BaseModel | dict, *, ext: str = "yaml") -> str: ...
    def read_object(self, uri: str) -> dict: ...
    def upsert_project_state(self, state: ProjectState) -> int: ...
    def get_project_state(self) -> ProjectState: ...
    def save_artifact_card(self, card: ArtifactCard) -> str: ...
    def search_text(self, query: str, scopes: list[str], limit: int = 10) -> list[SearchResult]: ...
```

### Inputs

```text
root path, typed schema objects, text query
```

### Outputs

```text
local URI strings, typed objects, search results, SQLite index rows
```

### Storage requirements

```text
.dmc/memory/events.jsonl is append-only.
.dmc/artifacts/index.jsonl is append-only.
YAML/Markdown object files remain human-readable.
SQLite can be rebuilt from files.
```

## Strong acceptance commands

- `uv run pytest tests/test_store.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not make SQLite the only source of truth.
- Do not add external DB dependencies.
- Do not add vector DB.

## Required handoff

Write:

```text
reports/handoffs/M02_STORE_<attempt_id>.md
reports/acceptance/M02_STORE_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
