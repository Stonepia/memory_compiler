# M00_BOOTSTRAP — Initialize repo, uv environment, skeleton, and DMC directories

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- none

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/AGENT_STATE_PROTOCOL.md`
- `docs/TOOL_POLICY.md`
- `docs/ACCEPTANCE_PROTOCOL.md`
- `docs/v0/00_GOALS_AND_NON_GOALS.md`
- `docs/v0/01_BOOTSTRAP_INIT.md`
- `templates/pyproject.toml.template`
- `templates/agent_state.initial.json`

## Scope

Create the project skeleton. Use uv. Create package layout, tests layout, `.dmc` layout, examples, initial state files, `README.md`, `AGENTS.md`, and a smoke-testable Typer CLI entry point.

Do not implement deep module logic. Only create stubs with explicit errors where later modules own the logic.

## Required public API / inputs / outputs

### Inputs

```text
- bootstrap pack files
- current working directory
```

### Outputs

```text
- initialized uv project
- pyproject.toml with dmc console script
- src/dmc package
- tests smoke test
- .dmc directory tree
- examples/sample_task.yaml
- examples/sample_action.yaml
- examples/sample_event.yaml
- agent_state.json
```

### Required CLI surface

```python
# src/dmc/cli.py
app = typer.Typer()
def main() -> None: ...
```

`uv run dmc --help` must not crash.

## Strong acceptance commands

- `uv sync`
- `uv run dmc --help`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not add MCP dependency yet unless absolutely required by generated CLI smoke test.
- Do not implement schema/store/planner logic beyond stubs.

## Required handoff

Write:

```text
reports/handoffs/M00_BOOTSTRAP_<attempt_id>.md
reports/acceptance/M00_BOOTSTRAP_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
