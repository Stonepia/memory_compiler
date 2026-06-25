# V0 Integration and Delivery

## G01 Integration goals

The integration agent must verify the whole loop:

```text
sample task -> plan graph -> graph render -> briefing -> precheck -> record event -> distill session -> eval case -> adapter bundle
```

## Required integration commands

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

## Required integration artifacts

```text
reports/integration/v0_integration_report.md
.dmc/plans/active/plan_graph.yaml
.dmc/plans/active/plan_graph.mmd
.dmc/briefing.md
.dmc/memory/events.jsonl
.dmc/memory/eval_cases/*.yaml or *.json
.dmc/proposals/pending/*
.dmc/adapters/codex/*
.dmc/adapters/copilot/*
.dmc/adapters/opencode/*
```

## G02 delivery goals

The delivery agent must package the repo state and write:

```text
reports/integration/v0_delivery_report.md
README.md updated with quickstart
CHANGELOG.md with V0 notes
```

No delivery if G01 has unresolved failures.
