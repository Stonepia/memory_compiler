# R02_STATE_AND_BRIEFING — Honest state mutation + closed briefing loop

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the
state file, claim this module, implement only this module, run acceptance, write
handoff, update state.

## Origin

V0 review (`docs/v0/review.md`), P1 MCP/CLI contract closure:

- **§4 state semantics**: `dmc_commit_state` / CLI `state commit <patch-file>` are
  named like a patch but validate a full `ProjectState` and full-replace it.
- **§3 briefing loop**: `dmc_get_briefing()` returns `{"briefing": text}` but never
  writes `.dmc/briefing.md`, while `resource_briefing_latest()` reads that file —
  the tool never maintains the resource the MCP surface exposes.

## Dependencies

- R01_DURABLE_CONTRACTS (consistent `.dmc` durable layout)

## Must-read context

- `docs/v0/review.md` (sections 3, 4; §15 schemas)
- `src/dmc/mcp_server.py` (`dmc_commit_state`, `dmc_get_briefing`, `resource_briefing_latest`)
- `src/dmc/cli.py` (`state commit`, `brief`)
- `src/dmc/store.py` (`upsert_project_state`), `src/dmc/schemas.py` (`ProjectState`)
- `src/dmc/renderer.py` (`render_briefing`)

## Scope

Make state mutation honest and close the briefing latest-resource loop. A fully
structured briefing JSON envelope is deferred V0.2 backlog — not required here.

## Required work

1. **Enrich `ProjectState` first (decision: fields become first-class, not
   `extra`).** The V0 review flagged `ProjectState` as too thin. Before patching,
   promote the fields the patch touches into the schema so state is not a bag of
   dynamic `extra` keys:
   ```python
   class ProjectDecision(BaseModel):
       id: Slug | None = None
       claim: str
       evidence: list[EvidenceRef] = Field(default_factory=list)
       confidence: Literal["low", "medium", "high"] | None = None

   class ProjectState(BaseModel):
       ...  # existing: name, status, current_phase, summary, active_task,
            #           open_questions, updated_at
       next_actions: list[str] = Field(default_factory=list)
       decisions: list[ProjectDecision] = Field(default_factory=list)
       evidence: list[EvidenceRef] = Field(default_factory=list)
   ```
   Add schema tests and regenerate the generated JSON schema. **Fallback:** if this
   proves too large for one context, restrict the V0.1 patch to the CURRENT explicit
   fields only and defer `next_actions/decisions/evidence` patch ops to V0.2 — but
   never write them into `extra`.
2. **State patch vs replace.** Add `ProjectStatePatch` (partial: phase/summary/
   active_task set, open_questions add/remove, next_actions set, decisions/
   evidence append) and `store.patch_project_state(patch) -> (version, diff)`.
   Expose unambiguous surfaces:
   ```text
   MCP: dmc_patch_state (partial)      CLI: dmc state patch <patch-file>
   MCP: dmc_replace_state (full upsert) CLI: dmc state replace <state-file>
   ```
   The default `state commit` naming must no longer imply patch while replacing.
3. **Briefing loop.** On success, `dmc_get_briefing()` writes `.dmc/briefing.md`
   (and `.dmc/briefings/<task-or-timestamp>.md`) and returns
   `{"briefing": ..., "uri": "dmc://briefing/latest", "path": ".dmc/briefing.md"}`.
   `resource_briefing_latest()` round-trips with it.

## Acceptance commands

- `uv run pytest tests/test_cli.py tests/test_mcp_server.py tests/test_store.py`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Required tests (add)

- `test_state_commit_patch_does_not_replace_whole_state` (patch preserves fields)
- appending a `decision` / `next_action` via patch persists as the typed field
  (not an `extra` key); enriched `ProjectState` round-trips + generated schema updated
- `state replace` performs full upsert
- `test_mcp_get_briefing_writes_latest_resource` (tool output == resource content)

## Module-specific forbidden shortcuts

- No command named `patch` that silently full-replaces.
- No `latest` resource the tool never updates.

## Required handoff

```text
reports/handoffs/R02_STATE_AND_BRIEFING_<attempt_id>.md
reports/acceptance/R02_STATE_AND_BRIEFING_<attempt_id>.md
```

Update `agent_state.json` (module status, reports, changed files, blockers).
