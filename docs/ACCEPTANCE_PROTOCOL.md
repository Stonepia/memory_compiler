# Acceptance Protocol

A module is complete only when implementation, tests, docs, state, and handoff are complete.

## Required report files

For each module attempt:

```text
reports/handoffs/<MODULE_ID>_<attempt_id>.md
reports/acceptance/<MODULE_ID>_<attempt_id>.md
```

Use templates:

```text
templates/handoff_report.template.md
templates/acceptance_report.template.md
```

## Minimum acceptance commands

Each module may add its own commands, but these must pass by G01 integration:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run dmc --help
```

## Module-level acceptance

A module acceptance report must include:

```text
- module id
- attempt id
- files changed
- public APIs implemented
- tests added/changed
- commands run
- command results
- known limitations
- dependency changes
- no-forbidden-work checklist
```

## No fake completion checklist

Before marking done, verify:

```text
[ ] No placeholder pass-through implementation.
[ ] No TODO used as substitute for required logic.
[ ] No test deleted merely to pass.
[ ] No acceptance command skipped.
[ ] No hidden network or local machine dependency.
[ ] No forbidden system implemented.
[ ] Public functions have deterministic behavior for tested inputs.
[ ] Schema validation fails on invalid examples.
[ ] Errors are explicit and actionable.
```

## Integration gates

Integration gates are separate modules:

```text
G01_INTEGRATION_V0
G02_DELIVERY_V0
```

No delivery is allowed before G01 passes.
