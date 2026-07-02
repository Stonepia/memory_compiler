# R03_MEMORY_QUALITY — Executable precheck rules + reliable outcome status

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the
state file, claim this module, implement only this module, run acceptance, write
handoff, update state.

## Origin

V0 review (`docs/v0/review.md`), P1/P2 memory-integrity fixes:

- **§5 precheck rules**: `load_precheck_rules(store)` claims to merge extra rules
  from `.dmc/objects/precheck_rules/`, but `precheck()` never calls it and only
  runs five hardcoded predicates — false extensibility. Malformed failure-mode
  files are also silently skipped.
- **§7 trace status**: distiller classifies outcomes by substring
  (`fail`/`pass`/`ok`...), misclassifying `"not passed"`, `"not ok"`,
  `"0 failures"`, `"inconclusive"`, which poisons eval/failure memory.

## Dependencies

- (V0 complete)

## Must-read context

- `docs/v0/review.md` (sections 5, 7; §15 precheck)
- `src/dmc/precheck.py` (`precheck`, `load_precheck_rules`, `_rule_by_id`, `BUILTIN_RULES`, `_load_failure_modes`)
- `src/dmc/schemas.py` (`TraceObservation`), `src/dmc/distiller.py` (`is_failure_event`, `is_success_validation_event`), `src/dmc/recorder.py`
- `tests/test_precheck.py`, `tests/test_distiller.py`

## Scope

Guard durable-memory quality. Keep everything deterministic (no LLM).

## Required work

1. **Precheck rules.** Choose ONE and implement fully:
   - *Preferred:* a minimal declarative matcher (`when.action_contains_any`,
     `when.missing_context_any`, `decision`, `required_evidence`); `precheck()`
     runs built-ins then loaded rules, preserving block > warn > allow.
   - *Or:* delete the extra-rule loading and make `load_precheck_rules()` return
     built-in metadata only.
   Either way, surface malformed failure-mode/rule files as warnings instead of
   silent skips. Add an explicit `data_warnings: list[str]` field to
   `PrecheckResult` (schema + regenerated JSON schema) and thread it through the
   CLI/MCP output — do not rely on Pydantic `extra`.
2. **Outcome status (backward-compatible — do not break legacy events).** Add an
   explicit enum while keeping old events readable:
   ```python
   status: ObservationStatus | None = None   # None = legacy; NOT a validation error
   classification_source: Literal["explicit", "legacy_heuristic"] | None = None
   ```
   - Newly written events (recorder / CLI / MCP) MUST carry an explicit `status`;
     those write paths reject a missing status.
   - Legacy JSONL and sample events without `status` MUST still load — implement a
     before-validator / migration that leaves `status=None` (or derives it and sets
     `classification_source="legacy_heuristic"`). Do NOT make `status` a hard
     required field on `TraceObservation`, or old events and `examples/*.yaml` fail
     `model_validate` (and break R05's smoke test).
   - `is_failure_event` / `is_success_validation_event` read `status` first, falling
     back to the substring heuristic only when `status is None`.
   - Update `examples/sample_event.yaml` to include an explicit `status` and
     regenerate the affected generated schemas.

## Acceptance commands

- `uv run pytest tests/test_precheck.py tests/test_distiller.py tests/test_recorder.py tests/test_schemas.py`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Required tests (add)

- precheck: `test_precheck_extra_rule_actually_fires` (or, for removal, API returns builtins only); malformed file surfaces a `PrecheckResult.data_warnings` entry (asserted through CLI/MCP)
- distiller: `test_distiller_does_not_mark_not_passed_as_success`, `test_distiller_does_not_mark_not_ok_as_success`
- compat: a legacy event with no `status` still validates; a recorder/CLI/MCP write with no explicit `status` is rejected; `examples/sample_event.yaml` carries an explicit `status`

## Module-specific forbidden shortcuts

- No API that implies extensibility without behavior.
- No pure-substring classification as the primary path for new events.

## Required handoff

```text
reports/handoffs/R03_MEMORY_QUALITY_<attempt_id>.md
reports/acceptance/R03_MEMORY_QUALITY_<attempt_id>.md
```

Update `agent_state.json` (module status, reports, changed files, blockers).
