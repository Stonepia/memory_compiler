# Project Index — Dev Memory Compiler Bootstrap Pack

This is the index every agent must read after `START_HERE.md`.

## Core docs

| Path | Purpose | Read when |
|---|---|---|
| `START_HERE.md` | Root execution protocol | Always first |
| `docs/PROJECT_INDEX.md` | Project index and doc routing | Always second |
| `docs/AGENT_STATE_PROTOCOL.md` | State-driven agent loop | Before any implementation |
| `docs/TOOL_POLICY.md` | What to reuse and what not to build | Before any implementation |
| `docs/ACCEPTANCE_PROTOCOL.md` | Acceptance, handoff, and delivery rules | Before marking anything done |

## Phase docs

| Path | Phase | Purpose |
|---|---|---|
| `docs/v0/00_GOALS_AND_NON_GOALS.md` | V0 | Scope, success criteria, and forbidden work |
| `docs/v0/01_BOOTSTRAP_INIT.md` | P0/V0 | Init agent instructions and uv environment |
| `docs/v0/02_ARCHITECTURE.md` | V0 | Architecture and package layout |
| `docs/v0/03_MODULE_SEQUENCE.md` | V0 | Module dependency order |
| `docs/v0/04_INTEGRATION_AND_DELIVERY.md` | V0 | How modules are integrated and delivered |
| `docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md` | V1 | Editable graph, eval set, and learning loop |
| `docs/v1/01_VISUALIZATION_OPTIONAL.md` | V1 | Optional graph visualization path |

## Module cards

Each module card is a contract for a separate fresh agent.

| Module | Path | Depends on |
|---|---|---|
| M00_BOOTSTRAP | `modules/M00_BOOTSTRAP.md` | none |
| M01_SCHEMAS | `modules/M01_SCHEMAS.md` | M00 |
| M02_STORE | `modules/M02_STORE.md` | M01 |
| M03_PLAN_GRAPH | `modules/M03_PLAN_GRAPH.md` | M01, M02 |
| M04_RENDERER | `modules/M04_RENDERER.md` | M01, M03 |
| M05_RETRIEVER | `modules/M05_RETRIEVER.md` | M01, M02 |
| M06_PRECHECK | `modules/M06_PRECHECK.md` | M01, M02, M05 |
| M07_RECORDER | `modules/M07_RECORDER.md` | M01, M02 |
| M08_DISTILLER_EVALS | `modules/M08_DISTILLER_EVALS.md` | M01, M02, M07 |
| M09_MCP_SERVER | `modules/M09_MCP_SERVER.md` | M01-M08 |
| M10_ADAPTERS | `modules/M10_ADAPTERS.md` | M01, M03, M04, M09 |
| M11_CLI | `modules/M11_CLI.md` | M01-M08, M10 |
| G01_INTEGRATION_V0 | `modules/G01_INTEGRATION_V0.md` | M00-M11 |
| G02_DELIVERY_V0 | `modules/G02_DELIVERY_V0.md` | G01 |

## Templates and schemas

| Path | Purpose |
|---|---|
| `templates/agent_state.initial.json` | Initial state file |
| `templates/agent_state.schema.json` | State schema |
| `templates/plan_graph.schema.json` | PlanGraph JSON schema target |
| `templates/trace_event.schema.json` | TraceEvent schema target |
| `templates/eval_case.schema.json` | EvalCase schema target |
| `templates/acceptance_report.template.md` | Required module acceptance report |
| `templates/handoff_report.template.md` | Required module handoff report |
| `templates/pyproject.toml.template` | Bootstrap pyproject reference |

## Prompts

| Path | Purpose |
|---|---|
| `prompts/MODULE_AGENT_CONTRACT.md` | Copyable prompt for a module implementation agent |
| `prompts/REVIEWER_AGENT_CONTRACT.md` | Copyable prompt for a review agent |
| `prompts/DELIVERY_AGENT_CONTRACT.md` | Copyable prompt for final delivery |

## The final generated repo must preserve this rule

The root `START_HERE.md` remains the only entrypoint. Other docs are context selected by `agent_state.json` and module cards.
