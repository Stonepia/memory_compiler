# V0 Architecture

## Layers

```text
src/dmc/schemas.py      -> typed contracts
src/dmc/store.py        -> local files + SQLite/FTS5
src/dmc/planner.py      -> PlanGraph creation/validation/readiness
src/dmc/renderer.py     -> Markdown and Mermaid rendering
src/dmc/retriever.py    -> local search over DMC objects
src/dmc/precheck.py     -> deterministic gates/warnings
src/dmc/recorder.py     -> action-level event and artifact recording
src/dmc/distiller.py    -> session -> episode/failure/proposal/eval stubs
src/dmc/evals.py        -> eval-case helpers and metrics
src/dmc/mcp_server.py   -> MCP tools/resources/prompts
src/dmc/adapters.py     -> Codex/Copilot/OpenCode bundle generation
src/dmc/cli.py          -> Typer CLI
```

## Data object boundaries

```text
ProjectState: where the project is now.
Tier0Policy: always-on evidence/reproducibility rules.
Tier1Workflow: stable task workflow.
Tier2Atom: executable atomic action/tool pattern.
KnowledgeRef: fact/spec/doc/code reference.
TraceEvent: action-level event from a session.
ArtifactCard: raw artifact summary and URI.
EpisodeCard: what happened in a session.
FailureMode: repeatable wrong turn and trigger.
PrecheckRule: deterministic warning/block rule.
SkillUpdateProposal: pending change to workflow/atom/knowledge.
EvalCase: test-set-like record produced from a session.
PlanGraph: editable execution graph.
```

## URI convention

Use readable local URIs:

```text
dmc://project_state/current
dmc://skill/tier1/<id>
dmc://skill/tier2/<id>
dmc://knowledge/<path>
dmc://event/<id>
dmc://artifact/<id>
dmc://episode/<id>
dmc://failure_mode/<id>
dmc://proposal/<id>
dmc://eval_case/<id>
plan://<id>
session://<id>
```

## Error handling

All public functions should return typed results or raise explicit DMC exceptions:

```text
DMCValidationError
DMCNotFoundError
DMCBlockedError
DMCStorageError
```

No bare `Exception` for expected failures.
