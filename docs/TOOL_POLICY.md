# Tool Policy — Reuse First, Minimal Code Only

DMC must minimize maintenance burden. It should be a thin local sidecar with stable schemas and contracts.

## Required stack

Use these unless impossible:

```text
Python: 3.11 or 3.12
Project/package manager: uv
Schemas: Pydantic
CLI: Typer + Rich
YAML: PyYAML
Storage: SQLite from stdlib + SQLite FTS5 + filesystem
Event log: JSONL append-only files
Tests: pytest
Lint: ruff
MCP: MCP Python SDK or FastMCP
Graph rendering: Mermaid text output
```

## Recommended external tools, not reimplemented by DMC

```text
Serena MCP       -> repo symbols, references, file/code structure
GitHub MCP       -> issues, PRs, commits, repo metadata
Sourcegraph MCP  -> large repo / multi-repo / cross-repo search, optional
Basic Memory MCP -> Markdown notes/spec/project knowledge, optional
Codex skills     -> task-specific Codex workflows, optional
Copilot skills   -> task-specific Copilot workflows, optional
OpenCode skills  -> SKILL.md-based reusable OpenCode workflows, optional
```

## Forbidden in V0

Do not implement:

```text
custom repo graph
custom symbol indexer
custom call graph
custom vector database
graph database
RAG platform
web dashboard
full UI debugger
full agent harness
sandbox runner
multi-agent orchestrator
automatic profiler parser framework
cloud sync
training pipeline
```

## Allowed later, not V0

```text
embedding retrieval
interactive HTML graph viewer
Sourcegraph-specific adapter helpers
Basic Memory sync helper
ProjectMem import/export helper
LLM-assisted distillation
agent-specific plugins beyond file bundle generation
```

## Dependency discipline

Before adding a dependency:

1. Check whether stdlib is sufficient.
2. Check whether an existing listed dependency already covers it.
3. Add only if it removes more code than it adds.
4. Record the reason in the module handoff.

Do not add heavy frameworks for a single helper function.
