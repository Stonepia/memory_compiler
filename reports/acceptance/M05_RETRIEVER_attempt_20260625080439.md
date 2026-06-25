# Acceptance Report: M05_RETRIEVER

- Module: `M05_RETRIEVER`
- Attempt: `attempt_20260625080439`
- Agent: `module-impl-agent-M05`
- Date: `2026-06-25T08:04:39Z`

## Scope completed

Local retrieval over DMC-owned objects and the SQLite/FTS5 index only (not
repo/code search). Implemented the three required public functions with
deterministic scope/filter narrowing, ranking with per-result explanations,
provenance preservation, and a token-budgeted Markdown context pack.

## Files changed

- `src/dmc/retriever.py` (new) — `search`, `rank_results`, `build_context_pack`.
- `tests/test_retriever.py` (new) — 21 tests (positive + negative).
- `src/dmc/schemas.py` (modified) — added one optional field
  `SearchResult.reason: str | None = None`. Reason: no relevance-explanation
  field existed; the card requires each result to explain *why* it is relevant.
  Optional/defaulted so M01 tests stay green (verified).
- `.dmc/generated_schemas/search_result.schema.json` (regenerated) — reflects
  the new optional `reason` field; only this generated file changed.
- `agent_state.json` (modified) — claim/complete M05; unblock M06_PRECHECK.

## Public APIs implemented

```python
def search(request: SearchRequest, store: DMCStore) -> list[SearchResult]: ...
def rank_results(query: str, candidates: list[SearchResult]) -> list[SearchResult]: ...
def build_context_pack(results: list[SearchResult], budget_tokens: int) -> str: ...
```

Supported search scopes: `project_state, skills, knowledge, artifacts,
episodes, failure_modes, eval_cases, proposals`.

## Tests added or changed

`tests/test_retriever.py` (21 tests), incl.:
- search returns hits across scopes; respects scope filter and `limit`.
- provenance preserved when source has it; absent when it does not.
- empty/whitespace query -> empty; unknown scope handled gracefully (alone ->
  empty; mixed with a valid scope -> valid scope still works); no-match -> empty.
- `filters` narrowing (by kind).
- rank: exact id/path outranks weak text match; scope/kind match boosts;
  deterministic tie-break on uri (stable across calls); every result has a
  non-empty `reason`; provenance preserved through ranking.
- context pack: Markdown, within budget; over-budget input truncated + flagged;
  empty results -> placeholder; deterministic; zero budget -> empty; provenance
  rendered.
- end-to-end search -> build_context_pack within budget.

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv run pytest tests/test_retriever.py` | pass | 21 passed in 0.25s |
| `uv run pytest` | pass | 163 passed in 0.46s |
| `uv run ruff check .` | pass | All checks passed! |
| `uv run dmc --help` | pass | exit 0; command group renders |

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

- Ranking is lexical/heuristic over the FTS index (deterministic, no
  embeddings) — by design for V0.
- `filters` and `budget_tokens` are consumed as `SearchRequest` extra fields
  (the model is `extra="allow"`); they are not yet formal schema fields. A
  later M01 revision could promote them if desired.
- Token counting is a coarse ~4-chars/token estimate, not a real tokenizer.

## Dependency changes

- No new project dependencies were added. `pyproject.toml` and `uv.lock` are
  unchanged; the retriever relies only on the existing stack (Pydantic, stdlib
  `re`/`math`, and the already-present `DMCStore` FTS5 backend).
- `jsonschema` was used only via uv's ephemeral layer
  (`uv run --with jsonschema ...`) to validate `agent_state.json`; it was **not**
  added to project dependencies (per AGENTS.md).
- Schema surface change (not a dependency change): `src/dmc/schemas.py` gained
  one optional field `SearchResult.reason: str | None = None`, and
  `.dmc/generated_schemas/search_result.schema.json` was regenerated to match.
  No other schemas changed.

## No-forbidden-work checklist

```text
[x] No repo/code search implemented.
[x] No embeddings / vector DB.
[x] No arbitrary source-code indexing.
[x] No LLM use.
[x] No new dependencies added.
```

## Evidence links

- `reports/handoffs/M05_RETRIEVER_attempt_20260625080439.md`
- `src/dmc/retriever.py`
- `tests/test_retriever.py`


## Reviewer note

Reviewer found a documentation-contract deviation on 2026-06-25: this acceptance report lacked the required **Dependency changes** section from `docs/ACCEPTANCE_PROTOCOL.md` (lines 34-47), so M05_RETRIEVER was returned for revision even though the re-run code/test commands passed. Resolved 2026-06-25: the `## Dependency changes` section was added above and all required sections are now present; code and tests were unchanged.
