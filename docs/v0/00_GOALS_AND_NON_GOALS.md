# V0 Goals and Non-goals

## Mission

Build a local-first Dev Memory Compiler sidecar that lets coding agents:

```text
start task -> plan task -> get briefing -> inspect context -> execute -> record events -> precheck risky actions -> commit project state -> distill session -> produce eval cases and skill proposals -> recall next time
```

## V0 goals

```text
1. Define durable schemas for state, skills, artifacts, trace events, PlanGraph, eval cases, and proposals.
2. Store all data locally using plain files plus SQLite/FTS5.
3. Generate deterministic task plans and briefings without requiring an LLM.
4. Render PlanGraph to Mermaid and Markdown.
5. Support local search over state, skills, memory, and artifacts.
6. Warn/block repeated bad actions using deterministic precheck rules.
7. Record action-level trace events and artifacts.
8. Distill sessions into episode/eval/proposal stubs with provenance.
9. Expose a minimal CLI.
10. Generate adapter bundles for Codex/Copilot/OpenCode.
```

## Non-goals

```text
- Solve tasks autonomously.
- Replace Codex/Copilot/OpenCode.
- Parse every benchmark/profiler format.
- Build a repo graph or code indexer.
- Build a vector search platform.
- Build a web UI.
- Train or fine-tune models.
- Store private credentials.
```

## Success definition

V0 succeeds if a fresh agent can run:

```bash
uv run dmc plan examples/sample_task.yaml --out .dmc/plans/active/plan_graph.yaml
uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd
uv run dmc brief examples/sample_task.yaml --out .dmc/briefing.md
uv run dmc record examples/sample_event.yaml
uv run dmc distill --session sess_demo
uv run dmc export-agent-bundle --target codex --out .dmc/adapters/codex
uv run pytest
```

and the outputs contain provenance, readable IDs, and no hardcoded absolute paths.
