# R05_DOCS_AND_CI — Resolve doc/code drift and add CI + smoke tests

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the
state file, claim this module, implement only this module, run acceptance, write
handoff, update state.

## Origin

V0 review (`docs/v0/review.md`), P2/limitations cleanup:

- **§11 doc drift**: `docs/v0/02_ARCHITECTURE.md` lists `src/dmc/evals.py` as owning
  eval cases, but eval-case generation lives in `src/dmc/distiller.py`. Also §12/
  §15 note the briefing "workflows/atoms" labels are plan-derived placeholders and
  planner memory-awareness is overstated.
- **§14 CI**: `CHANGELOG` lists "no CI workflow yet" as a known limitation. NOTE:
  the original review priority list marked CI as V0.2-acceptable; this plan
  deliberately pulls CI into V0.1 as the closing verification step AFTER the
  contract fixes (R01–R04), so a green run reflects the remediated surface. This is
  an intentional upgrade, not a conflict with the review.

## Dependencies

- R01_DURABLE_CONTRACTS, R02_STATE_AND_BRIEFING, R03_MEMORY_QUALITY, R04_RETRIEVAL_AND_ADAPTERS
  (docs and smoke tests should reflect the finished remediation surface)

## Must-read context

- `docs/v0/review.md` (sections 11, 12, 14; §15 renderer/planner)
- `docs/v0/02_ARCHITECTURE.md`, `README.md`, `CHANGELOG.md`
- `src/dmc/distiller.py`, `src/dmc/renderer.py`, `src/dmc/planner.py`
- `AGENTS.md` (uv-only execution), `examples/*.yaml`

## Scope

Documentation alignment plus CI and a CLI smoke test. uv-only; no bare python.
This is the closing V0.1 remediation step — confirm the full loop is green.

## Required work

1. **Docs.** Update `02_ARCHITECTURE.md` so eval-case generation is attributed to
   `distiller.py` (`build_eval_case()`); no dangling `evals.py` reference. Clarify
   briefing "workflows/atoms" are plan spine/checks until real skill selection
   lands, and note planner determinism (`memory_context_used: false`). Refresh
   README/CHANGELOG for the V0.1 remediation surface.
2. **CI.** Add `.github/workflows/ci.yml` running:
   ```bash
   uv sync --all-extras --dev
   uv run pytest
   uv run ruff check .
   ```
3. **Smoke test.** A pytest/script exercising the delivered CLI loop on samples:
   `dmc plan`/`brief`/`precheck`/`record`/`distill` over `examples/*.yaml`.
   Drop the "no CI" limitation from `CHANGELOG` once green.

## Acceptance commands

- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Required checks

- No reference implies a `src/dmc/evals.py` that does not exist.
- CI workflow is well-formed and uv-only; smoke test passes on sample inputs.

## Module-specific forbidden shortcuts

- No runtime behavior changes hidden in this docs/CI step.
- uv-only. Never invoke bare `python`/`python3` or the system interpreter.

## Required handoff

```text
reports/handoffs/R05_DOCS_AND_CI_<attempt_id>.md
reports/acceptance/R05_DOCS_AND_CI_<attempt_id>.md
```

Update `agent_state.json` (module status, reports, changed files, blockers).
