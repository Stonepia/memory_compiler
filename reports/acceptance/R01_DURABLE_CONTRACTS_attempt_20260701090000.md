# Acceptance Report: R01_DURABLE_CONTRACTS

- Module: `R01_DURABLE_CONTRACTS`
- Attempt: `attempt_20260701090000`
- Agent: `module-impl-agent-R01`
- Date: `2026-07-01T09:00:00Z`

## Scope completed

All three required fixes from `docs/v0/review.md` §2, §6, §10:

1. **Canonical skill/knowledge store.** Added `DMCStore.write_skill/read_skill/
   list_skills` (`.dmc/skills/tier{0,1,2}/<id>.yaml`) and
   `write_knowledge/read_knowledge/list_knowledge` (`.dmc/knowledge/<id>.yaml`,
   nested ids allowed). `dmc://skill/tier{0,1,2}/<id>` and
   `dmc://knowledge/<id>` now resolve through `read_object` to these canonical
   paths, not `.dmc/objects`. `rebuild_index()` scans both directories.
   `write_object`/`read_object` now reject the reserved kinds `skill` and
   `knowledge` so there is only one write path. Tier-0 policies are supported
   as durable skills (Option A per the module card).
2. **Path containment.** Added `_safe_child()` plus `_validate_slug_segment()`
   (flat `kind`/`object_id`) and `_validate_knowledge_segments()` /
   `KnowledgePath` (nested knowledge ids — every segment independently
   validated; hierarchical refs allowed, traversal is not). Applied in both
   write and read paths for objects, skills, and knowledge.
3. **Portable artifact URI.** `record_artifact` now persists
   `raw_artifact_path: .dmc/artifacts/raw/<id>/<filename>` and
   `raw_artifact_uri: dmc://artifact/raw/<id>/<filename>`, and also normalizes
   the card's own `uri` field to the portable URI once a raw file is
   registered (previously the card retained the caller's original, possibly
   machine-absolute, `uri`). No `file://` URI is persisted in durable memory.

## Files changed

- `src/dmc/store.py` — canonical skill/knowledge APIs, `_safe_child`, segment
  validators, reserved-kind check in `write_object`, `rebuild_index` scans for
  skills/knowledge.
- `src/dmc/schemas.py` — `KnowledgePath` type (`KnowledgeRef.id`), `ArtifactCard
  .raw_artifact_path`/`raw_artifact_uri` fields.
- `src/dmc/recorder.py` — `record_artifact` writes the portable
  `raw_artifact_uri` and normalizes `card.uri` to it when a raw file is
  registered.
- `tests/test_store.py` — path-traversal, canonical-skill, canonical-knowledge,
  nested-knowledge, reserved-kind, and rebuild-index coverage.
- `tests/test_recorder.py` — `test_record_artifact_uses_portable_dmc_uri`.
- `tests/test_retriever.py` — fixture updated to use `write_knowledge()`
  instead of the now-reserved `write_object("knowledge", ...)`.
- `.dmc/generated_schemas/artifact_card.schema.json`,
  `.dmc/generated_schemas/search_request.schema.json` — regenerated via
  `dmc schemas-export` (new `ArtifactCard` fields; `search_request` diff is
  key-order only).

## Public APIs implemented

```python
store.write_skill(tier, card) -> str
store.read_skill(tier, skill_id) -> dict
store.list_skills(tier=None) -> list[dict]
store.write_knowledge(ref) -> str
store.read_knowledge(knowledge_id) -> dict
store.list_knowledge() -> list[dict]
```

## Tests added or changed

- `test_write_read_skill_tier0_roundtrip`, `test_skill_resource_reads_dmc_skills_tier0/tier1`,
  `test_list_skills_filters_by_tier`, `test_write_skill_rejects_tier_mismatch`,
  `test_read_skill_missing_raises`
- `test_write_read_knowledge_roundtrip`, `test_write_read_nested_knowledge_roundtrip`,
  `test_knowledge_id_rejects_traversal_segment`, `test_read_knowledge_rejects_traversal_segment`,
  `test_list_knowledge_includes_nested`, `test_knowledge_scope_reads_dmc_knowledge`
- `test_write_object_rejects_reserved_kind`,
  `test_write_object_rejects_path_traversal_kind/object_id`,
  `test_write_object_traversal_cannot_escape_objects_dir`,
  `test_read_object_rejects_path_traversal`
- `test_rebuild_index_includes_skills_and_nested_knowledge`
- `test_record_artifact_uses_portable_dmc_uri`

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv run pytest tests/test_store.py tests/test_recorder.py tests/test_mcp_server.py` | pass | 94 passed |
| `uv run pytest` | pass | 314 passed |
| `uv run ruff check .` | pass | All checks passed |
| `uv run dmc --help` | pass | exit 0 |

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

- `search_request.schema.json` also picked up a key-ordering diff from the
  `dmc schemas-export` regeneration; functionally identical, unrelated to this
  module's scope, left as-is rather than hand-reverting.

## Dependency changes

- No new project dependencies added or removed.

## Evidence links

- `docs/v0/review.md` sections 2, 6, 10, 15 (store)
- `modules/R01_DURABLE_CONTRACTS.md`
