# M06_PRECHECK — Deterministic pre-action gates and warnings

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE
- M05_RETRIEVER

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v0/02_ARCHITECTURE.md`
- `modules/M06_PRECHECK.md`
- `reports/handoffs/M05_RETRIEVER_<latest>.md`

## Scope

Implement deterministic precheck logic. It warns or blocks before repeated bad actions, risky edits, or missing evidence.

## Required public API / inputs / outputs

### Required public API

```python
def precheck(request: PrecheckRequest, store: DMCStore) -> PrecheckResult: ...
def load_precheck_rules(store: DMCStore) -> list[PrecheckRule]: ...
def match_failure_modes(request: PrecheckRequest, store: DMCStore) -> list[FailureMode]: ...
```

### Inputs

```text
PrecheckRequest(action, files, command, intent, risk_level, task_context)
```

### Outputs

```text
PrecheckResult(decision: allow|warn|block, warnings, required_evidence_before_commit, matched_rules)
```

### Required built-in rules

```text
- warn if action resembles a stored failure mode
- warn if benchmark/perf claim lacks benchmark artifact
- warn if editing files without a task/plan reference
- block if request tries to mutate accepted skills directly instead of proposal path
```

## Strong acceptance commands

- `uv run pytest tests/test_precheck.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not call LLM.
- Do not silently allow missing evidence for memory writes.

## Required handoff

Write:

```text
reports/handoffs/M06_PRECHECK_<attempt_id>.md
reports/acceptance/M06_PRECHECK_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
