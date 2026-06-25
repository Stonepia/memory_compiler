# Handoff Report: M03_PLAN_GRAPH

- Module: `M03_PLAN_GRAPH`
- Attempt: `attempt_20260625074525`
- Agent: `module-impl-agent-M03`
- Status: `done`
- Date: `2026-06-25T07:45:25Z`

## Summary

Implemented `src/dmc/planner.py` — deterministic, rule/template-based PlanGraph
logic. No LLM, no node execution, no orchestrator. Added the six required public
functions (`validate_plan_graph`, `topological_nodes`, `next_ready_nodes`,
`plan_task`, `save_plan_graph`, `load_plan_graph`) plus a `PLAN_NODE_TYPES`
constant. Added a minimal `ValidationReport` model to `src/dmc/schemas.py` (the
single contract module) and `tests/test_plan_graph.py` (32 tests, positive +
negative). All acceptance commands pass (116 tests total, ruff clean, `dmc
--help` exit 0). No new external dependencies.

## What changed

Created:
- `src/dmc/planner.py` — PlanGraph creation/validation/readiness/persistence.
- `tests/test_plan_graph.py` — positive + negative unit tests.

Modified:
- `src/dmc/schemas.py` — added `ValidationReport` (ok/errors/warnings, `valid`
  alias) to `__all__` and `EXPORTED_MODELS`. No other model behavior changed.
- `agent_state.json` — claimed M03 (in_progress -> done), recorded attempt and
  reports, flipped `M04_RENDERER` to `ready` and cleared its blocker.

## Important implementation notes

- Imports all shapes from `src/dmc/schemas.py` (`PlanGraph`, `PlanNode`,
  `TaskRequest`, `ValidationReport`); no shapes redefined in planner.
- `validate_plan_graph` collects errors and never raises for an invalid graph
  (it only raises `DMCValidationError` on API misuse — a non-`PlanGraph` arg).
  Enforces: no duplicate ids; deps exist + no self-dep; no cycles (DFS); node
  `type` in `PLAN_NODE_TYPES`; non-empty `id`/`type`/`goal`/`success_criteria`;
  `evidence_contract` is a mapping; `human_review.required` is an explicit bool.
- `ValidationReport.ok` is derived from `errors` via a model validator, so a
  report can never claim success while carrying errors.
- `topological_nodes` uses Kahn-style selection with original-position tie-break
  for full determinism; raises `DMCValidationError` on a cycle.
- `next_ready_nodes` returns non-completed nodes whose deps are all completed,
  in original order; handles empty and full completed-sets.
- `plan_task` emits a fixed linear spine
  `brief -> inspect -> plan -> edit -> test -> review -> decide -> distill`,
  each node with non-empty goal/criteria, an `evidence_contract` object, and an
  explicit `human_review.required` bool (true for review/decide). Output always
  passes `validate_plan_graph` (asserted internally and in tests). The optional
  `store` is accepted for API compatibility and validated but does not change
  the plan.
- `save_plan_graph`/`load_plan_graph` round-trip via YAML (default) or JSON (by
  `.json` extension), aligned with `templates/plan_graph.schema.json` field
  names; `load` reconstructs and validates the model.
- Negative tests build deliberately-broken graphs with `model_construct` to
  bypass the strict constructors (which already reject duplicates/dangling/self
  deps) and exercise `validate_plan_graph` directly.

## How to verify

```bash
uv run pytest tests/test_plan_graph.py
uv run pytest
uv run ruff check .
uv run dmc --help
```

## Downstream impact

- `M04_RENDERER` (deps M01, M03 — now both `done`) flipped to `ready`; blocker
  cleared.
- `M05_RETRIEVER` and `M07_RECORDER` remain `ready` (independent of M03).
- `M09`/`M10`/`M11` remain `blocked` (need M05/M06/M08 and beyond).

## Blockers or risks

None. No new external dependencies (pydantic, pyyaml already present). Added one
contract model (`ValidationReport`) to schemas.py; all pre-existing M01/M02
tests stay green (the schema-count test uses `len(EXPORTED_MODELS)` and is
unaffected).

## Suggested next module

`M04_RENDERER` (newly-ready, depends on the now-complete M03).
