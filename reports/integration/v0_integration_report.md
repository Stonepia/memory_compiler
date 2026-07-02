# V0 Integration Report — G01_INTEGRATION_V0

- Gate: `G01_INTEGRATION_V0`
- Attempt: `attempt_20260701073000`
- Agent: `integration-agent-G01`
- Date: `2026-07-01T07:30:00Z`
- Result: **GO** — the full V0 loop runs end-to-end from a sample task to the
  three adapter bundles.

## Scenario

The required V0 chain was executed through the public `dmc` CLI only (the CLI is
the stable integration surface delivered by M11):

```text
sample_task.yaml
  -> plan_graph.yaml        (dmc plan)
  -> plan_graph.mmd         (dmc graph --format mermaid)
  -> briefing.md            (dmc brief)
  -> precheck_result.json   (dmc precheck)
  -> events.jsonl (+1)      (dmc record)
  -> episode/eval/failure/proposal   (dmc distill)
  -> codex/copilot/opencode bundles  (dmc export-agent-bundle)
```

## Commands run and results

| # | Command | Result |
|---|---|---|
| 1 | `uv sync` | pass |
| 2 | `uv run pytest` | pass (286 passed) |
| 3 | `uv run ruff check .` | pass (clean) |
| 4 | `uv run dmc --help` | pass (exit 0) |
| 5 | `uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml` | pass |
| 6 | `uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd` | pass |
| 7 | `uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md` | pass |
| 8 | `uv run dmc precheck examples/sample_action.yaml --out reports/integration/precheck_result.json` | pass (decision=warn) |
| 9 | `uv run dmc record examples/sample_event.yaml` | pass (event recorded to events.jsonl) |
| 10 | `uv run dmc distill --session sess_demo` | pass (episode + eval_case + failure_mode + proposal) |
| 11 | `uv run dmc export-agent-bundle --target codex --out .dmc/adapters/codex` | pass |
| 12 | `uv run dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot` | pass |
| 13 | `uv run dmc export-agent-bundle --target opencode --out .dmc/adapters/opencode` | pass |

## Artifact verification

Every stage produced its artifact:

- **Plan**: `.dmc/plans/active/plan_graph.yaml` (valid PlanGraph, id
  `plan_task_demo_bmg_perf`, 8 nodes: brief→inspect→plan→edit→test→review→
  decide→distill).
- **Graph**: `.dmc/plans/active/plan_graph.mmd` begins with `flowchart TD`;
  every node label carries its id, type, and gate markers.
- **Briefing**: `.dmc/briefing.md` begins with `# Briefing: task_demo_bmg_perf`
  and includes the six required sections.
- **Precheck**: `reports/integration/precheck_result.json` is valid JSON with
  `decision: "warn"` and rule `edit-without-task-ref` (the CLI emits JSON for a
  `.json --out`).
- **Event**: `.dmc/memory/events.jsonl` gained the `event_demo_001`
  (`session_id: sess_demo`) record.
- **Distill**: wrote `dmc://episode/episode-sess_demo`,
  `dmc://eval_case/evalcase-sess_demo`,
  `dmc://failure_mode/fm-sess_demo-event_demo_001` (stored under
  `.dmc/objects/<kind>/`) and the pending proposal
  `.dmc/proposals/pending/prop-avoid-sess_demo-event_demo_001.yaml`.
- **Adapter bundles** (all three present):
  - codex: `.dmc/adapters/codex/AGENTS.md`
  - copilot: `.dmc/adapters/copilot/.github/copilot-instructions.md` and
    `.github/skills/dmc-start-task/SKILL.md` (Copilot's `.github` layout)
  - opencode: `.dmc/adapters/opencode/AGENTS.md` and
    `.dmc/adapters/opencode/opencode.jsonc.template`

## Integration glue changed

One small, in-scope glue change was made in the CLI so a `--out` path ending in
`.json` is written as valid JSON instead of YAML (previously all structured
`--out` writes were YAML). This makes the required
`reports/integration/precheck_result.json` genuinely JSON. Stdout and non-`.json`
outputs remain human-friendly YAML. Covered by
`tests/test_cli.py::test_precheck_json_out_is_valid_json`. No module was
redesigned; no schemas changed; no new dependencies.

## Dependency changes

None. No new project dependencies. No schema changes.

## No-forbidden-work checklist

```text
[x] No module tests were skipped (full `uv run pytest` = 286 passed).
[x] Integration is not marked passed with any adapter bundle missing (all 3 present).
[x] No forbidden V0 system was implemented (no repo graph, vector/graph DB, web
    UI, agent harness, sandbox, or custom code indexer).
[x] No dynamic facts were written into stable instruction files.
```

## Notes / limitations

- Runtime artifacts written under `.dmc/` during this run (plan, graph,
  briefing, distilled objects, adapter bundles) are rebuildable outputs; the
  repo keeps those directories empty via `.gitkeep`, so they are not committed.
  The committed evidence for this gate is this report plus
  `reports/integration/precheck_result.json` and
  `reports/integration/distill_sess_demo.json`.
- The Copilot bundle writes to Copilot's `.github/` locations (dotfiles), so a
  plain `ls` hides them; use `ls -a`/`find` to see them.

## Suggested next gate

`G02_DELIVERY_V0` (its only dependency, G01, is now satisfied).
