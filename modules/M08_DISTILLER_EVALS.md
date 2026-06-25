# M08_DISTILLER_EVALS — Session distillation and eval-case generation

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE
- M07_RECORDER

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md`
- `modules/M08_DISTILLER_EVALS.md`
- `reports/handoffs/M07_RECORDER_<latest>.md`

## Scope

Implement deterministic/stub distillation. V0 does not require LLM calls. It should convert trace events into structured episode cards, failure mode candidates, skill update proposals, and eval cases.

## Required public API / inputs / outputs

### Required public API

```python
def distill_session(session_id: str, store: DMCStore) -> DistillResult: ...
def build_episode_card(session_id: str, events: list[TraceEvent]) -> EpisodeCard: ...
def build_eval_case(session_id: str, events: list[TraceEvent]) -> EvalCase: ...
def propose_failure_modes(session_id: str, events: list[TraceEvent]) -> list[FailureMode]: ...
def propose_skill_updates(session_id: str, events: list[TraceEvent]) -> list[SkillUpdateProposal]: ...
```

### Inputs

```text
session_id, TraceEvent list, ArtifactCard refs
```

### Outputs

```text
EpisodeCard, EvalCase, FailureMode candidates, SkillUpdateProposal candidates
```

### Required rules

```text
- failed/regressed events can produce wrong_turn labels
- successful validation events can produce useful_memory labels
- proposals are pending only; never directly mutate skills
- every output links back to event/artifact/session provenance
```

## Strong acceptance commands

- `uv run pytest tests/test_distiller.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not require online LLM APIs.
- Do not directly edit accepted skills.
- Do not create evidence-free lessons.

## Required handoff

Write:

```text
reports/handoffs/M08_DISTILLER_EVALS_<attempt_id>.md
reports/acceptance/M08_DISTILLER_EVALS_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
