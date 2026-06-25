# M10_ADAPTERS — Generate Codex/Copilot/OpenCode adapter bundles

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the state file, claim this module, implement only this module, run acceptance, write handoff, update state.

## Dependencies

- M01_SCHEMAS
- M03_PLAN_GRAPH
- M04_RENDERER
- M09_MCP_SERVER

## Must-read context

- `START_HERE.md`
- `docs/PROJECT_INDEX.md`
- `docs/TOOL_POLICY.md`
- `modules/M10_ADAPTERS.md`
- `reports/handoffs/M09_MCP_SERVER_<latest>.md`

## Scope

Implement adapter bundle generation. The output is files/instructions/config templates, not a custom integration runtime.

## Required public API / inputs / outputs

### Required public API

```python
def export_agent_bundle(target: Literal["codex", "copilot", "opencode"], out_dir: Path, *, project_root: Path) -> list[Path]: ...
def render_codex_bundle(project_root: Path) -> dict[str, str]: ...
def render_copilot_bundle(project_root: Path) -> dict[str, str]: ...
def render_opencode_bundle(project_root: Path) -> dict[str, str]: ...
```

### Codex outputs

```text
AGENTS.md
.codex/config.toml.template
.dmc/adapters/codex/README.md
```

### Copilot outputs

```text
.github/copilot-instructions.md
.github/skills/dmc-start-task/SKILL.md or equivalent skill folder
.dmc/adapters/copilot/README.md
```

### OpenCode outputs

```text
AGENTS.md
opencode.jsonc.template
.dmc/adapters/opencode/agents/*.md
.dmc/adapters/opencode/skills/*/SKILL.md
```

### Adapter protocol content

Each adapter must instruct the agent to:

```text
- call dmc_plan_task / dmc_get_briefing at task start
- use Serena/GitHub/Sourcegraph/Basic Memory for repo/spec context if configured
- call dmc_precheck before risky edit/test/benchmark
- call dmc_record_event after meaningful action/failure/result
- call dmc_commit_state at checkpoint
- call dmc_distill_session at end
- never directly mutate accepted skills
```

## Strong acceptance commands

- `uv run pytest tests/test_adapters.py`
- `uv run pytest`
- `uv run ruff check .`

## Module-specific forbidden shortcuts

- Do not write dynamic project facts into AGENTS.md.
- Do not auto-install external MCP servers. Generate templates only.

## Required handoff

Write:

```text
reports/handoffs/M10_ADAPTERS_<attempt_id>.md
reports/acceptance/M10_ADAPTERS_<attempt_id>.md
```

Update `agent_state.json` with status, reports, changed files, and blockers if any.
