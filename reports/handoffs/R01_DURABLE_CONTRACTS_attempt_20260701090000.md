# Handoff Report: R01_DURABLE_CONTRACTS

- Module: `R01_DURABLE_CONTRACTS`
- Attempt: `attempt_20260701090000`
- Agent: `module-impl-agent-R01`
- Status: `done`
- Date: `2026-07-01T09:00:00Z`

## Summary

Fixed the three store-layer contract bugs from the V0 review (§2, §6, §10):
`.dmc/skills` / `.dmc/knowledge` are now the canonical, single-source-of-truth
layout for skill and knowledge objects (with dedicated APIs and MCP resource
resolution), all caller-provided path segments (kind/object_id/knowledge id)
are contained against traversal, and artifact raw-file references are fully
portable `dmc://` URIs — no absolute `file://` path is ever persisted.

## What changed

See `reports/acceptance/R01_DURABLE_CONTRACTS_attempt_20260701090000.md` for
the full file list. Core additions: `DMCStore.write_skill/read_skill/list_skills`,
`write_knowledge/read_knowledge/list_knowledge`, `_safe_child()` containment
helper, `KnowledgePath` schema type, and `ArtifactCard.raw_artifact_path` /
`raw_artifact_uri`. `write_object`/`read_object` now refuse the reserved kinds
`"skill"`/`"knowledge"`. `rebuild_index()` scans `.dmc/skills` and
`.dmc/knowledge`. `record_artifact` normalizes both `raw_artifact_uri` and the
card's own `uri` to the portable form once a raw file is registered.

## Important implementation notes

- This module's diff was already ~90% written when I picked it up (branch
  `r01-durable-contracts` had uncommitted changes to `store.py`/`schemas.py`/
  `recorder.py`/tests). I diagnosed and fixed the two remaining test failures
  rather than rewriting: (1) `record_artifact` was leaving the card's original
  `uri` as a machine-absolute `file://` even after registering a portable
  `raw_artifact_uri` — fixed by normalizing `uri` too; (2)
  `test_rebuild_index_includes_skills_and_nested_knowledge` used a 3-term FTS5
  query (`"cite compare bmg"`) expecting OR semantics across three different
  rows, but SQLite FTS5 bareword terms are implicit AND within one row — fixed
  by asserting each term against its own row.
- `tests/test_retriever.py`'s `seeded_store` fixture called
  `store.write_object("knowledge", ...)`, which is now a reserved kind — updated
  to call `store.write_knowledge(KnowledgeRef(...))` instead.
- Regenerated `.dmc/generated_schemas/*` via `dmc schemas-export` (picked up
  the new `ArtifactCard` fields; `search_request.schema.json` also shifted key
  order, harmless, pre-existing drift unrelated to this module).

## How to verify

```bash
uv run pytest tests/test_store.py tests/test_recorder.py tests/test_mcp_server.py
uv run pytest
uv run ruff check .
uv run dmc --help
```

All green: 314 tests pass, ruff clean, CLI exits 0.

## Downstream impact

- `R02_STATE_AND_BRIEFING` depends on this module and is now unblocked.
- No other module's public API changed in a breaking way; `write_object`
  callers using `"knowledge"`/`"skill"` as `kind` must switch to
  `write_knowledge`/`write_skill` (only `tests/test_retriever.py` did this in
  this repo).

## Blockers or risks

None.

## Suggested next module

`R02_STATE_AND_BRIEFING` (dependency `R01_DURABLE_CONTRACTS` now satisfied).
`R03_MEMORY_QUALITY` and `R04_RETRIEVAL_AND_ADAPTERS` were already `ready`
(no dependency on R01) and remain claimable independently.
