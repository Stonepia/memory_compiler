# M11_CLI — Typer CLI for local use and integration tests

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M02_STORE
- M03_PLAN_GRAPH
- M04_RENDERER
- M05_RETRIEVER
- M06_PRECHECK
- M07_RECORDER
- M08_DISTILLER_EVALS
- M10_ADAPTERS

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/v0/04_INTEGRATION_AND_DELIVERY.md`
- `modules/M11_CLI.md`
- `reports/handoffs/M10_ADAPTERS_<latest>.md`

## Scope

Implement complete local CLI. The CLI is the user-facing shell for V0 and the stable interface for integration tests.

## Required public API / inputs / outputs

### Required commands

```bash
dmc state show
dmc state commit <patch-file>
dmc plan <task-file> --out <path>
dmc graph <plan-file> --format mermaid|markdown --out <path>
dmc brief <task-file> --out <path>
dmc search <query> --scope <scope>...
dmc precheck <action-file> --out <path optional>
dmc record <event-file>
dmc distill --session <session_id>
dmc export-agent-bundle --target codex|copilot|opencode --out <dir>
```

### Required behavior

```text
- All commands return non-zero on validation failure.
- All commands print clear error messages.
- All file outputs create parent directories.
- Default DMC root is ./.dmc but can be overridden by --dmc-root.
```

## Strong acceptance commands

- `uv run dmc --help`
- `uv run dmc state show`
- `uv run pytest tests/test_cli.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not put business logic in CLI command bodies. Call core functions.

## Required handoff

Write:

```text
reports/handoffs/M11_CLI_<attempt_id>.md
reports/acceptance/M11_CLI_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
