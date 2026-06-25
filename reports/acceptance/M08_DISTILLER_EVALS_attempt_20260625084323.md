# Acceptance Report: M08_DISTILLER_EVALS

- Module: `M08_DISTILLER_EVALS`
- Attempt: `attempt_20260625084323`
- Agent: `module-impl-agent-M08`
- Date: `2026-06-25T08:43:23Z`

## Scope completed

Deterministic, rule-based session distillation (no LLM, no network) per
`modules/M08_DISTILLER_EVALS.md`. Converts a session's `TraceEvent` stream into
an `EpisodeCard`, an `EvalCase`, `FailureMode` candidates, and *pending*
`SkillUpdateProposal` candidates, persists them, and returns a `DistillResult`.
Required rules enforced: failed/regressed events -> `wrong_turn` labels +
failure modes; successful validation events -> `useful_memory` labels;
proposals are pending only (never mutate skills); every durable output links
back to session/event/artifact provenance (non-empty).

## Files changed

- `src/dmc/distiller.py` (new) — 5 public functions + deterministic helpers.
- `tests/test_distiller.py` (new) — 9 tests (positive + negative).
- `src/dmc/schemas.py` (modified) — added `DistillResult` model + `__all__` /
  `EXPORTED_MODELS` entries. No existing model altered.
- `.dmc/generated_schemas/distill_result.schema.json` (new) — regenerated.
- `agent_state.json` (modified) — claim/complete M08; flip M09 to ready.

## Public APIs implemented

```python
def distill_session(session_id: str, store: DMCStore) -> DistillResult: ...
def build_episode_card(session_id: str, events: list[TraceEvent]) -> EpisodeCard: ...
def build_eval_case(session_id: str, events: list[TraceEvent]) -> EvalCase: ...
def propose_failure_modes(session_id: str, events: list[TraceEvent]) -> list[FailureMode]: ...
def propose_skill_updates(session_id: str, events: list[TraceEvent]) -> list[SkillUpdateProposal]: ...
```

Plus deterministic helpers: `is_failure_event`, `is_success_validation_event`,
and the marker/phase constants used for classification.

## Tests added or changed

`tests/test_distiller.py` (9 tests), using `tmp_path` + a real `DMCStore` and
the recorder to seed sessions:

- `test_failure_and_success_classification` — classification helpers.
- `test_build_episode_card_has_provenance_and_labels` — non-empty provenance to
  the session; `useful_memory`/`wrong_turn` labels present.
- `test_build_eval_case_is_schema_valid` — construction does not raise; task,
  `initial_plan_graph` plan ref, outcome, labels, non-empty provenance.
- `test_propose_failure_modes_from_failed_event` — failure mode for the
  regressed event with `wrong_turn` label + non-empty provenance/evidence.
- `test_propose_failure_modes_empty_for_clean_session` — empty list (negative).
- `test_propose_skill_updates_are_pending_with_provenance` — pending proposals,
  provenance, `useful_memory` + `wrong_turn` labels.
- `test_propose_skill_updates_does_not_write_skills` — nothing under `.dmc/skills`.
- `test_distill_session_persists_and_is_deterministic` — persisted objects exist
  and round-trip; proposals only under `proposals/pending`; nothing under
  skills; provenance non-empty; re-run deterministic.
- `test_distill_session_clean_session_has_no_failures` — negative/edge: clean
  session -> no failure modes, still valid episode/eval case with provenance.

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv run pytest tests/test_distiller.py` | pass | 9 passed |
| `uv run pytest` | pass | 202 passed |
| `uv run ruff check .` | pass | All checks passed! |
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

- Classification is intentionally rule/marker-based (no LLM in V0); outcome
  semantics rely on substring markers (`fail`/`regress`/`error`/`pass`/...).
- A session without an explicit plan graph gets a deterministic synthesized
  `plan://<session_id>/initial` ref (documented) so the `EvalCase` is
  schema-valid and provenance-backed; it is tied to the real session, not
  fabricated content.
- Proposals are written to `.dmc/proposals/pending` directly because the store
  exposes no proposal-specific API; durable objects use `store.write_object`.

## Dependency changes

No new project dependencies were added to `pyproject.toml`. `jsonschema` was
NOT added (state validated only via uv's ephemeral `--with jsonschema` layer per
AGENTS.md). One new schema model `DistillResult` was added to `src/dmc/schemas.py`
(the single contract module) and the generated schema export was regenerated
(`.dmc/generated_schemas/distill_result.schema.json`); no existing schema model
was changed, so all M01 schema tests stay green.

## No-forbidden-work checklist

```text
[x] No online LLM API / network requirement (deterministic rule-based only).
[x] No direct mutation of accepted skills (proposals -> proposals/pending only).
[x] No evidence-free lessons (every durable output carries non-empty provenance).
[x] No custom repo graph, vector DB, graph DB, web UI, agent harness, sandbox,
    or custom code indexer.
[x] No placeholder/TODO pass-through; functions are deterministic for tested inputs.
```

## Evidence links

- Handoff: `reports/handoffs/M08_DISTILLER_EVALS_attempt_20260625084323.md`
- Implementation: `src/dmc/distiller.py`
- Tests: `tests/test_distiller.py`
- Schema: `src/dmc/schemas.py` (`DistillResult`),
  `.dmc/generated_schemas/distill_result.schema.json`
