# Acceptance Report: M00_BOOTSTRAP

- Module: `M00_BOOTSTRAP`
- Attempt: `attempt_20260625054019`
- Agent: `module-impl-agent-M00`
- Date: `2026-06-25T05:40:19Z`

## Scope completed

Created the project skeleton with `uv`: package layout (`src/dmc`), tests
layout (`tests`, `tests/golden`), the full `.dmc/` data tree, examples (kept as
provided), seed state files, `README.md`, `AGENTS.md`, `agent_state.json`, and a
smoke-testable Typer CLI entry point (`dmc = "dmc.cli:main"`). No deep module
logic; later-module commands are explicit error-raising stubs.

## Files changed

Created:

- `pyproject.toml`, `uv.lock`
- `src/dmc/__init__.py`, `src/dmc/cli.py`
- `tests/test_cli.py`, `tests/golden/.gitkeep`
- `README.md`, `AGENTS.md`
- `agent_state.json`
- `.dmc/config.yaml`, `.dmc/state/project_state.yaml`, `.dmc/state/active_task.yaml`
- `.dmc/memory/events.jsonl`, `.dmc/artifacts/index.jsonl`
- `.dmc/` subtree dirs (plans/active, memory/{sessions,episodes,failure_modes,eval_cases},
  skills/tier{0,1,2}, knowledge/{repo,tests,perf,hw,specs}, artifacts/raw,
  proposals/{pending,accepted,rejected}, adapters/{codex,copilot,opencode}) with `.gitkeep`
- `reports/{handoffs,acceptance,integration}/.gitkeep`

Unchanged: `examples/*.yaml`, `docs/`, `modules/`, `templates/`, `prompts/`, `scripts/`.

## Public APIs implemented

- `dmc.__version__: str`
- `dmc.cli.app` — `typer.Typer` application.
- `dmc.cli.main() -> None` — console-script entrypoint.
- Placeholder CLI commands (each fails with a clear non-zero error):
  `state`, `plan`, `graph`, `brief`, `search`, `precheck`, `record`, `distill`,
  `export-agent-bundle`.

## Tests added or changed

- `tests/test_cli.py`:
  - `test_package_imports_and_has_version` (positive: import + version).
  - `test_cli_help_works` (positive: `--help` exit 0, help text present).
  - `test_placeholder_command_fails_clearly` (negative: unimplemented command
    exits non-zero).

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv sync` | pass | Resolved 22 packages; built/installed `dmc==0.1.0`; CPython 3.14.3 venv. No MCP dep. |
| `uv run dmc --help` | pass | Prints usage + 9 placeholder commands; exit 0. |
| `uv run pytest` | pass | 3 passed in 0.19s. |
| `uv run ruff check .` | pass | All checks passed. |

Additional verification: `uv run dmc plan examples/sample_task.yaml` exits 1 with
`NotImplementedError: ... owned by module M03_PLAN_GRAPH`.

## Acceptance checklist

```text
[x] All module commands passed.
[x] Tests include positive and negative cases.
[x] No forbidden V0 system was implemented.
[x] No dynamic facts were inserted into stable instruction files.
[x] Handoff report written.
[x] agent_state.json updated.
```

## No-forbidden-work checklist

```text
[x] No custom repo graph.
[x] No custom symbol/code indexer.
[x] No vector database.
[x] No graph database.
[x] No web UI / dashboard.
[x] No agent harness.
[x] No sandbox runner.
[x] No MCP dependency added during bootstrap.
[x] Only stubs for later-module logic.
```

## Known limitations

- All `dmc` subcommands are placeholders that intentionally fail until their
  owning modules (M03–M11) are implemented.
- The local store (SQLite/FTS5) is not created yet; `.dmc/config.yaml` only
  references its future path. Owned by M02_STORE.

## Evidence links

- Handoff: `reports/handoffs/M00_BOOTSTRAP_attempt_20260625054019.md`
- State: `agent_state.json` (validated against `templates/agent_state.schema.json`)
