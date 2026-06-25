# G02_DELIVERY_V0 — Final V0 delivery packaging

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- G01_INTEGRATION_V0

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/ACCEPTANCE_PROTOCOL.md`
- `docs/v0/04_INTEGRATION_AND_DELIVERY.md`
- `reports/integration/v0_integration_report.md`

## Scope

Prepare final delivery docs and sanity checks. This module does not add features.

## Required public API / inputs / outputs

### Required outputs

```text
README.md with quickstart
CHANGELOG.md with V0 summary
reports/integration/v0_delivery_report.md
agent_state.json project_status = delivered_v0
```

### Delivery report must include

```text
- commands run
- artifact list
- known limitations
- next phase recommendations
- confirmation that forbidden V0 systems were not implemented
```

## Strong acceptance commands

- `uv sync`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Module-specific forbidden shortcuts

- Do not add new capabilities during delivery.
- Do not hide known limitations.

## Required handoff

Write:

```text
reports/handoffs/G02_DELIVERY_V0_<attempt_id>.md
reports/acceptance/G02_DELIVERY_V0_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
