# V0 Bootstrap Init Agent

This doc is for M00_BOOTSTRAP.

## Required commands

Bootstrap must use uv.

Recommended command sequence:

```bash
uv init --package dmc
uv add pydantic pydantic-settings pyyaml typer rich
uv add --dev pytest ruff
# Add one MCP dependency only in M09, not during bootstrap unless module plan says otherwise.
mkdir -p src/dmc tests tests/golden .dmc/state .dmc/plans .dmc/memory .dmc/skills/tier0 .dmc/skills/tier1 .dmc/skills/tier2 .dmc/knowledge .dmc/artifacts/raw .dmc/proposals/pending .dmc/proposals/accepted .dmc/proposals/rejected reports/handoffs reports/acceptance reports/integration examples
```

If `uv init --package dmc` creates a different layout, adapt without changing the required final layout.

## Required generated files

```text
pyproject.toml
src/dmc/__init__.py
src/dmc/cli.py
README.md
AGENTS.md
.dmc/config.yaml
.dmc/state/project_state.yaml
.dmc/state/active_task.yaml
.dmc/memory/events.jsonl
.dmc/artifacts/index.jsonl
examples/sample_task.yaml
examples/sample_action.yaml
examples/sample_event.yaml
agent_state.json
```

## Initial CLI behavior

`uv run dmc --help` must work even before other modules are implemented.

It can show placeholder commands, but commands must fail with clear `NotImplementedError` or user-facing error until their module is complete.

## Acceptance

```bash
uv sync
uv run dmc --help
uv run pytest
uv run ruff check .
```

`uv run pytest` must pass with at least one smoke test.
