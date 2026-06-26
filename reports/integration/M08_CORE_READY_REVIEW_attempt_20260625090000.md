# M08_CORE_READY Review Report

**Attempt ID:** attempt_20260625090000  
**Date:** 2026-06-25  
**Issue:** [#1 — Milestone blocker: align M05–M08 core contracts before M09](https://github.com/Stonepia/memory_compiler/issues/1)

---

## Verdict

```
M08_CORE_READY: GO
```

All 5 blockers from Issue #1 are resolved. Full test suite passes (210 tests).
M09 can remain a thin MCP wrapper — no core logic changes needed at M09.

---

## Summary of Contract Fixes

### Blocker 1 — Singular/plural URI conventions (M05 / M06 / M08)

**Root cause:** M08 distiller wrote objects with singular kinds
(`episode`, `eval_case`, `failure_mode`) but M05 retriever mapped plural
user-facing scopes to plural store scopes (`episodes → episodes`), and M06
precheck loaded failure modes from `objects/failure_modes/` (plural).  This
broke the `record → distill → precheck` loop.

**Fix — `src/dmc/retriever.py`:**
- Changed `SCOPE_TO_STORE_SCOPE` type from `dict[str, str]` to `dict[str, list[str]]`.
- Plural user-facing scopes now expand to **both** singular and plural store
  scopes (e.g. `"episodes" → ["episode", "episodes"]`) so both M08-distilled
  objects and legacy objects seeded with plural kind are always reachable.
- Updated `search()` to iterate over the list of mapped store scopes.

**Fix — `src/dmc/precheck.py` (`_load_failure_modes`):**
- Primary scan directory changed to `objects/failure_mode/` (singular canonical).
- Backward-compatible fallback added for `objects/failure_modes/` (legacy plural).
- Generates correct `dmc://failure_mode/<id>` URIs for canonical objects.
- Stem-keyed merge ensures canonical singular wins on ID collision.

---

### Blocker 2 — Pending proposals bypass DMCStore indexing (M08)

**Root cause:** `distiller._write_pending_proposal` wrote directly to
`.dmc/proposals/pending/` with no FTS index row, so
`search(scopes=["proposals"])` could not find them.

**Fix — `src/dmc/store.py`:**
- Added `DMCStore.save_pending_proposal(proposal: SkillUpdateProposal) -> str`.
  Writes to `.dmc/proposals/pending/<id>.yaml` **and** calls `_index_row` with
  `scope="proposal"`, `kind="proposal"`, `uri="dmc://proposal/<id>"`.
- Added `_KIND_PROPOSAL = "proposal"` constant.
- Updated `read_object` to handle `kind == "proposal"` by looking in
  `.dmc/proposals/pending/` (so URIs are DMC-readable).

**Fix — `src/dmc/distiller.py`:**
- Removed `_write_pending_proposal` helper and its direct YAML write.
- `distill_session` now calls `store.save_pending_proposal(proposal)`.
- Removed unused `Path` and `yaml` imports from distiller.
- Proposal URIs changed from `proposal://pending/<id>` → `dmc://proposal/<id>`.

---

### Blocker 3 — `SearchRequest` missing `filters` and `budget_tokens` (M01)

**Fix — `src/dmc/schemas.py`:**
- Added `filters: dict[str, Any] = Field(default_factory=dict)`.
- Added `budget_tokens: int | None = None`.
- Regenerated `.dmc/generated_schemas/search_request.schema.json`.

`SearchRequest.model_json_schema()` now includes both fields; M09 MCP tool
input will match the Pydantic schema.

---

### Blocker 4 — Stale dynamic state and config mismatch (Blocker 4)

**Fix — `.dmc/config.yaml`:**
- `store.sqlite_path` corrected from `.dmc/dmc.sqlite3` → `.dmc/index.sqlite3`
  (matches `DMCStore.db_path`).

**Fix — `.dmc/state/project_state.yaml`:**
- `current_phase` updated `P0` → `V0`.
- `last_completed_module` updated `M00_BOOTSTRAP` → `M08_DISTILLER_EVALS`.
- `current_gate` set to `M09_MCP_SERVER`.
- Notes updated to reflect Issue #1 fixes.

---

### Blocker 5 — M09/M10 `export-agent-bundle` ownership ambiguity

**Fix — `modules/M09_MCP_SERVER.md`:**
- Added implementation note specifying that `dmc_export_agent_bundle` must be
  a thin lazy wrapper that imports from `dmc.adapters` (M10) and returns
  `{"ok": False, "errors": ["M10_ADAPTERS not yet implemented"]}` until M10 is done.
- No M10 adapter logic to be duplicated in M09.

---

## Files Changed

| File | Change |
|------|--------|
| `src/dmc/schemas.py` | Add `filters`, `budget_tokens` to `SearchRequest` |
| `src/dmc/retriever.py` | `SCOPE_TO_STORE_SCOPE` → `dict[str, list[str]]`; expand multi-scope in `search()`; use `request.filters` not `getattr` |
| `src/dmc/precheck.py` | `_load_failure_modes`: singular dir first, plural fallback, correct URI |
| `src/dmc/store.py` | Add `save_pending_proposal`; add `_KIND_PROPOSAL`; handle `kind=="proposal"` in `read_object` |
| `src/dmc/distiller.py` | Remove `_write_pending_proposal`; use `store.save_pending_proposal`; remove unused imports |
| `.dmc/config.yaml` | Fix `sqlite_path` |
| `.dmc/state/project_state.yaml` | Update to V0 / M08 done / M09 gate |
| `.dmc/generated_schemas/search_request.schema.json` | Regenerated with new fields |
| `modules/M09_MCP_SERVER.md` | Lazy-wrapper note for `dmc_export_agent_bundle` |
| `tests/test_distiller.py` | Update `proposal://` → `dmc://`; add proposal-search + end-to-end loop test |
| `tests/test_retriever.py` | Add distilled-scope tests + SearchRequest schema field tests |

---

## Tests Added

**`tests/test_distiller.py`:**
- `test_distill_session_proposal_is_searchable_via_store` — verifies
  `search(scopes=["proposals"])` finds distilled proposals and `read_object` resolves them.
- `test_record_distill_precheck_loop_fires_failure_mode_rule` — integration:
  `record_event(regressed) → distill_session → precheck(similar) → RULE_FAILURE_MODE matched`.

**`tests/test_retriever.py`:**
- `test_search_episodes_scope_finds_distilled_episode`
- `test_search_failure_modes_scope_finds_distilled_failure_mode`
- `test_search_eval_cases_scope_finds_distilled_eval_case`
- `test_search_request_schema_has_filters_and_budget_tokens`
- `test_search_request_filters_first_class`
- `test_search_request_budget_tokens_field`

---

## Acceptance Commands Run

```
uv run pytest tests/test_retriever.py tests/test_precheck.py tests/test_distiller.py
# → 53 passed

uv run pytest
# → 210 passed

uv run ruff check .
# → All checks passed!

uv run dmc --help
# → exit 0

uv run --with jsonschema python -c "import json, jsonschema; jsonschema.validate(...)"
# → agent_state.json validates OK
```

---

## Forbidden V0 Systems Check

- No repo graph, custom code indexer, vector DB, graph DB, RAG, web UI, agent harness,
  sandbox runner, profiler parser framework, cloud sync, or training pipelines added. ✓
- No new project dependencies added. ✓
- No tests weakened or removed. ✓

---

## M09 Readiness Confirmation

M09 can be implemented as a thin MCP wrapper over the now-aligned core:

- `dmc_search` → `dmc.retriever.search(SearchRequest(...), store)` — fully typed, indexed
- `dmc_precheck` → `dmc.precheck.precheck(PrecheckRequest(...), store)` — loads from canonical `objects/failure_mode/`
- `dmc_record_event` → `dmc.recorder.record_event(event, store)`
- `dmc_distill_session` → `dmc.distiller.distill_session(session_id, store)` — proposals indexed
- `dmc_export_agent_bundle` → thin lazy wrapper importing from `dmc.adapters` (M10)

The `record → distill → search/precheck` loop is end-to-end validated.

```
M08_CORE_READY: GO
M09_MCP_SERVER: ready to implement
```
