# Optional Visualization Path

Do not build an interactive UI in V0.

## V0 visualization

Generate Mermaid text:

```bash
uv run dmc graph .dmc/plans/active/plan_graph.yaml --format mermaid --out .dmc/plans/active/plan_graph.mmd
```

## V1 visualization

Optional static HTML can be added later using:

```text
Mermaid embedded HTML
no frontend framework
no server required
```

## V1.5 visualization

Only after the core loop proves useful:

```text
click node -> show context refs
edit node -> update PlanGraph YAML
show evidence gates
show session trace timeline
```

This must remain optional. The source of truth is always PlanGraph YAML/JSON, not the UI.
