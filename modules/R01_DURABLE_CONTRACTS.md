# R01_DURABLE_CONTRACTS — Fix the `.dmc` durable store contract

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the
state file, claim this module, implement only this module, run acceptance, write
handoff, update state.

## Origin

V0 review (`docs/v0/review.md`), P1/P2 store-layer contract fixes. This module
bundles three tightly related `store.py`/`recorder.py` fixes:

- **§2 durable layout**: `.dmc/skills` / `.dmc/knowledge` are treated as source of
  truth by config, precheck, and MCP resources, but the store writes generic
  objects to `.dmc/objects/<kind>/...` and `dmc://skill/tier1/{id}` resolves to
  `.dmc/objects/skill/...`. Three places disagree.
- **§6 path safety**: `write_object` / `read_object` build paths from
  caller-provided `kind`/`object_id` with no containment check (`..` can escape).
- **§10 artifact URI**: `record_artifact` stores `raw_artifact_uri =
  dest.resolve().as_uri()` — a machine-absolute `file://` path in durable memory.

## Dependencies

- (V0 complete)

## Must-read context

- `docs/v0/review.md` (sections 2, 6, 10, and §15 store)
- `docs/v0/02_ARCHITECTURE.md` (object boundaries)
- `src/dmc/store.py` (`write_object`, `read_object`, `_find_object_file`, `rebuild_index`)
- `src/dmc/recorder.py` (`record_artifact`)
- `src/dmc/mcp_server.py` (skill/knowledge/artifact resources)
- `tests/test_store.py`, `tests/test_recorder.py`

## Scope

Make `.dmc` durable paths canonical, contained, and portable. No embeddings /
vector DB / code indexer (forbidden in V0).

## Required work

1. **Canonical skill/knowledge store.** Add first-class APIs and fixed layout for
   all tiers (Tier-0 policy is a durable skill — see decision below):
   ```python
   store.write_skill(tier, card); store.read_skill(tier, id); store.list_skills(tier=None)
   store.write_knowledge(ref);    store.read_knowledge(id);  store.list_knowledge()
   ```
   ```text
   .dmc/skills/tier0/<id>.yaml   .dmc/skills/tier1/<id>.yaml
   .dmc/skills/tier2/<id>.yaml   .dmc/knowledge/<id>.yaml
   ```
   Map `dmc://skill/tier0/<id>`, `dmc://skill/tier1/<id>`, `dmc://skill/tier2/<id>`,
   `dmc://knowledge/<id>` to those paths; scan them in `rebuild_index()`.
   `.dmc/objects` stays only for generic objects. Align precheck's `.dmc/skills/**`
   protection with the store.

   **Decision — Tier-0 policy (Option A, chosen):** Tier-0 policies ARE durable
   skills. `SkillCard.tier` is already `Literal[0, 1, 2]` and `Tier0Policy` exists
   in schema, so `write_skill(0, Tier0Policy)` and `dmc://skill/tier0/<id>` must be
   supported here — do not leave `Tier0Policy` a schema orphan or scatter always-on
   policy only in `global_rules`. (Option B — defer Tier-0 to config-only — is
   explicitly NOT chosen.)
2. **Path containment (two id policies — do not conflate).** Add a
   `_safe_child(base, *parts)` helper that resolves and rejects escapes, applied in
   both write and read paths:
   - **Generic `kind` / `object_id`:** must each be a single `Slug` (no `/`, `..`,
     empty, absolute, backslash).
   - **Knowledge ids:** MAY be nested (e.g. `dmc://knowledge/hw/by-platform/bmg`),
     but EVERY segment must independently be a `Slug`; reject empty segments, `.`,
     `..`, absolute paths, backslashes, and any symlink escape. "Path safety" must
     NOT forbid hierarchical knowledge refs, and hierarchical refs must NOT reopen
     traversal. Update `KnowledgeRef.id` (currently flat `Slug`) or add a
     `KnowledgePath` type accordingly, and reflect it in the generated schemas.
3. **Portable artifact URI.** Persist `raw_artifact_path:
   .dmc/artifacts/raw/<id>/<filename>` and `raw_artifact_uri:
   dmc://artifact/raw/<id>/<filename>`; resolve to a real `Path` only at runtime.

## Acceptance commands

- `uv run pytest tests/test_store.py tests/test_recorder.py tests/test_mcp_server.py`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Required tests (add)

- `test_skill_resource_reads_dmc_skills_tier0` / `tier1`, `test_knowledge_scope_reads_dmc_knowledge`
- nested knowledge path (`dmc://knowledge/hw/by-platform/bmg`) round-trips; a
  segment containing `..` or empty is rejected
- `test_write_object_rejects_path_traversal`, `test_read_object_rejects_path_traversal`
- `test_record_artifact_uses_portable_dmc_uri` (no `file://` absolute URI in card)

## Module-specific forbidden shortcuts

- No dual write paths; `.dmc/skills` / `.dmc/knowledge` is the single source of truth.
- Do not persist machine-absolute paths in durable memory.

## Required handoff

```text
reports/handoffs/R01_DURABLE_CONTRACTS_<attempt_id>.md
reports/acceptance/R01_DURABLE_CONTRACTS_<attempt_id>.md
```

Update `agent_state.json` (module status, reports, changed files, blockers).
