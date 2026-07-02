# Acceptance Report: G01_INTEGRATION_V0

- Module: `G01_INTEGRATION_V0`
- Attempt: `attempt_20260701073000`
- Agent: `integration-agent-G01`
- Date: `2026-07-01T07:30:00Z`

## Scope completed

Ran the whole V0 loop end-to-end through the public `dmc` CLI, from
`examples/sample_task.yaml` to the codex/copilot/opencode adapter bundles, and
verified every stage produced its artifact. Fixed only integration glue (JSON
`--out` emission); no module was redesigned.

## Files changed

- `src/dmc/cli.py` — `_emit_structured` now writes valid JSON when `--out` ends
  in `.json` (YAML otherwise, and for stdout). Integration glue so
  `precheck_result.json` is genuine JSON.
- `tests/test_cli.py` — added
  `test_precheck_json_out_is_valid_json`.
- `reports/integration/v0_integration_report.md` — the required integration
  report (new).
- `reports/integration/precheck_result.json`,
  `reports/integration/distill_sess_demo.json` — committed evidence artifacts.

## Public APIs implemented

None new. This is an integration gate over existing M00–M11 public APIs.

## Tests added or changed

`tests/test_cli.py::test_precheck_json_out_is_valid_json` (asserts a `.json`
`--out` is parseable JSON containing the precheck `decision`).

## Commands run

| Command | Result | Notes |
|---|---|---|
| `uv sync` | pass | |
| `uv run pytest` | pass | 286 passed |
| `uv run ruff check .` | pass | clean |
| `uv run dmc --help` | pass | exit 0 |
| `dmc plan … --out .dmc/plans/active/plan_graph.yaml` | pass | 8-node plan |
| `dmc graph … --format mermaid --out …plan_graph.mmd` | pass | `flowchart TD` |
| `dmc brief … --out .dmc/briefing.md` | pass | 6 sections |
| `dmc precheck … --out reports/integration/precheck_result.json` | pass | decision=warn, valid JSON |
| `dmc record examples/sample_event.yaml` | pass | events.jsonl +1 |
| `dmc distill --session sess_demo` | pass | episode+eval+failure+proposal |
| `dmc export-agent-bundle --target codex --out .dmc/adapters/codex` | pass | AGENTS.md |
| `dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot` | pass | .github/* |
| `dmc export-agent-bundle --target opencode --out .dmc/adapters/opencode` | pass | AGENTS.md + template |

## Acceptance checklist

```text
[x] All module commands passed.
[x] Tests include positive and negative cases.
[x] No forbidden V0 system was implemented.
[x] No dynamic facts were inserted into stable instruction files.
[x] Handoff report written.
[x] agent_state.json updated.
```

## Dependency changes

None. No new project dependencies; no schema changes.

## Known limitations

- Runtime `.dmc/` outputs are rebuildable and not committed (directories kept
  empty via `.gitkeep`); the integration report + `precheck_result.json` +
  `distill_sess_demo.json` are the committed evidence.

## Evidence links

- `reports/integration/v0_integration_report.md`
- `reports/integration/precheck_result.json`
- `reports/integration/distill_sess_demo.json`
