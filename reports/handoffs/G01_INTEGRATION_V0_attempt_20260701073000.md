# Handoff Report: G01_INTEGRATION_V0

- Module: `G01_INTEGRATION_V0`
- Attempt: `attempt_20260701073000`
- Agent: `integration-agent-G01`
- Status: `done`
- Date: `2026-07-01T07:30:00Z`

## Summary

The V0 end-to-end integration gate passes. The full loop
(task → plan → graph → briefing → precheck → event → distill → 3 adapter
bundles) runs cleanly through the `dmc` CLI. Acceptance is green: 286 tests
pass, ruff clean, `dmc --help` exit 0.

## What changed

- `src/dmc/cli.py`: `_emit_structured` writes JSON for `.json --out` paths
  (integration glue) so `precheck_result.json` is valid JSON; YAML elsewhere.
- `tests/test_cli.py`: added `test_precheck_json_out_is_valid_json`.
- `reports/integration/v0_integration_report.md`: required report (new).
- `reports/integration/precheck_result.json`,
  `reports/integration/distill_sess_demo.json`: committed evidence.

## Important implementation notes

- No module was redesigned; the card's "fix only integration glue" constraint
  was honored. The single glue change is JSON output for `.json` targets.
- All three adapter bundles are generated. Copilot's files live under `.github/`
  (dotfiles); `ls` without `-a` hides them.
- Distilled objects are stored under `.dmc/objects/<kind>/`; the pending
  proposal is under `.dmc/proposals/pending/`.

## How to verify

```bash
uv sync
uv run pytest
uv run ruff check .
uv run dmc --help
uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml
uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd
uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md
uv run dmc precheck examples/sample_action.yaml --out reports/integration/precheck_result.json
uv run dmc record examples/sample_event.yaml
uv run dmc distill --session sess_demo
uv run dmc export-agent-bundle --target codex --out .dmc/adapters/codex
uv run dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot
uv run dmc export-agent-bundle --target opencode --out .dmc/adapters/opencode
```

## Downstream impact

- `G02_DELIVERY_V0` depends only on G01, which is now `done`, so G02 becomes
  ready.

## Blockers or risks

- None.

## Suggested next module

`G02_DELIVERY_V0`.
