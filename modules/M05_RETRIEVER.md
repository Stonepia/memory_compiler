# M05_RETRIEVER — Local retrieval over DMC objects

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/TOOL_POLICY.md`
- `modules/M05_RETRIEVER.md`
- `reports/handoffs/M02_STORE_<latest>.md`

## Scope

Implement local retrieval over DMC-owned files and indexes. This is not repo search. Repo/code search belongs to Serena/GitHub/Sourcegraph/Basic Memory adapters and instructions.

## Required public API / inputs / outputs

### Required public API

```python
def search(request: SearchRequest, store: DMCStore) -> list[SearchResult]: ...
def rank_results(query: str, candidates: list[SearchResult]) -> list[SearchResult]: ...
def build_context_pack(results: list[SearchResult], budget_tokens: int) -> str: ...
```

### Inputs

```text
SearchRequest(query, scopes, filters, limit, budget_tokens)
```

### Outputs

```text
ranked SearchResult list, compact context pack Markdown
```

### Search scopes

```text
project_state, skills, knowledge, artifacts, episodes, failure_modes, eval_cases, proposals
```

### Ranking requirements

```text
- exact ID/path match ranks high
- scope/filter match ranks high
- text match uses SQLite FTS5 or simple fallback
- result explains why relevant
- result carries provenance if source has it
```

## Strong acceptance commands

- `uv run pytest tests/test_retriever.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not implement repo search.
- Do not add embeddings/vector DB.
- Do not index arbitrary source code in V0.

## Required handoff

Write:

```text
reports/handoffs/M05_RETRIEVER_<attempt_id>.md
reports/acceptance/M05_RETRIEVER_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
