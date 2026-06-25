# Handoff Report: M05_RETRIEVER

- Module: `M05_RETRIEVER`
- Attempt: `attempt_20260625080439`
- Agent: `module-impl-agent-M05`
- Status: `done`
- Date: `2026-06-25T08:04:39Z`

## Summary

Implemented `src/dmc/retriever.py` — local retrieval over DMC-owned objects and
the SQLite/FTS5 index only (not repo/code search). Provides the three required
public functions: `search`, `rank_results`, and `build_context_pack`. Backed by
`DMCStore.search_text` (FTS5); adds deterministic scope/filter narrowing,
relevance ranking with per-result explanations, provenance preservation, and a
token-budgeted Markdown context pack. Added `tests/test_retriever.py` (21 tests,
positive + negative) using `tmp_path` and a real `DMCStore`. All acceptance
commands pass (163 tests total, ruff clean, `dmc --help` exit 0). No new
dependencies.

## What changed

Created:
- `src/dmc/retriever.py` — `search`, `rank_results`, `build_context_pack`, plus
  module constants (`SUPPORTED_SCOPES`, `SCOPE_TO_STORE_SCOPE`,
  `CHARS_PER_TOKEN`) and private helpers.
- `tests/test_retriever.py` — retriever unit tests.

Modified:
- `src/dmc/schemas.py` — added one optional field `reason: str | None = None`
  to `SearchResult`. No relevance-explanation field existed; per the module
  card this is the minimal optional addition needed so `rank_results` can
  explain *why* each result is relevant. Optional with a `None` default, so all
  M01 tests and existing constructions stay valid (verified green).
- `.dmc/generated_schemas/search_result.schema.json` — regenerated via
  `export_json_schemas` to reflect the new optional `reason` field (only this
  generated file changed).
- `agent_state.json` — claimed M05 (ready -> in_progress -> done), recorded the
  attempt + report paths, and unblocked M06_PRECHECK (deps M01,M02,M05 now all
  done) by flipping it to `ready` and clearing its satisfied blocker.

## Important implementation notes

- Imports `SearchRequest`/`SearchResult` from `src/dmc/schemas.py` and
  `DMCStore`/`DMCError` from `src/dmc/store.py`; no shapes redefined.
- `SearchRequest` formally defines `query`, `scopes`, `limit`. The card also
  names `filters` and `budget_tokens`; these are read via `getattr` (the model
  is `extra="allow"`, so they round-trip as extra fields). `filters` supports
  `kind`/`uri`/`id`/`tags` narrowing; `budget_tokens` is consumed by
  `build_context_pack`.
- Scope mapping: DMC search scopes map 1:1 to the store's FTS `scope` column
  except `project_state` -> `state` (the store indexes project state under the
  `state` scope). Unknown scopes are ignored; if no recognised scope remains,
  `search` returns `[]` (never crashes). Empty/whitespace query -> `[]`.
- Ranking is deterministic (card lines 54-60): exact id/path match (+1000),
  partial path (+200), id-token overlap (+100), scope/kind match (+80), title
  match (+30), snippet/body match (+10), plus the store's bm25-derived score as
  a fine tiebreaker; ties break on `uri` ascending. Every result gets a
  non-empty `reason`; provenance carried by a candidate is preserved through
  ranking.
- Provenance attach: `search` calls `store.read_object(uri)` and attaches the
  source object's `provenance` (when present) as an extra field on the result;
  missing objects/provenance are handled gracefully.
- Token budget: deterministic ~4-chars/token estimate
  (`ceil(len(text) / 4)`, `CHARS_PER_TOKEN = 4`). `build_context_pack` includes
  results in ranked order until the next would breach the budget, then appends a
  truncation notice; a final hard cap guarantees the estimate never exceeds the
  budget. Empty results -> small placeholder pack; zero/negative budget -> empty
  string.

## How to verify

```bash
uv run pytest tests/test_retriever.py
uv run pytest
uv run ruff check .
uv run dmc --help
```

## Downstream impact

- `M06_PRECHECK` (deps M01,M02,M05 — all done) -> `ready` (blocker cleared).

## Blockers or risks

None. No new external dependencies. No repo search, embeddings/vector DB,
arbitrary source-code indexing, or LLM use (forbidden by the card).

## Suggested next module

`M06_PRECHECK` (now ready).
