# Agent State Protocol

Every agent is stateless except for repository files. The state file is the coordination mechanism.

## Required state file

Path:

```text
agent_state.json
```

If missing, create it from:

```text
templates/agent_state.initial.json
```

Then validate against:

```text
templates/agent_state.schema.json
```

## Claiming work

To claim a module:

1. Read `agent_state.json`.
2. Find a module with `status` equal to `ready` or `needs_revision`.
3. Confirm all dependencies have status `done`.
4. Confirm `blockers` is empty.
5. Set:

```json
{
  "status": "in_progress",
  "active_agent": "<agent_label>",
  "attempt_id": "attempt_<timestamp_or_short_uuid>",
  "started_at": "<ISO-8601 timestamp>"
}
```

6. Write atomically.

If another agent already claimed the module, pick another ready module or stop with a blocker report.

## Updating work

When acceptance passes:

```json
{
  "status": "done",
  "completed_at": "<ISO-8601 timestamp>",
  "acceptance_report": "reports/acceptance/<MODULE_ID>_<attempt_id>.md",
  "handoff_report": "reports/handoffs/<MODULE_ID>_<attempt_id>.md"
}
```

When acceptance fails:

```json
{
  "status": "needs_revision",
  "last_failure": {
    "summary": "exact failure",
    "commands": ["uv run pytest ..."],
    "logs": ["reports/handoffs/..."]
  }
}
```

When blocked:

```json
{
  "status": "blocked",
  "blockers": [
    {
      "summary": "missing dependency or ambiguous requirement",
      "required_action": "what a later agent or human must do",
      "evidence": ["file path", "command output", "test name"]
    }
  ]
}
```

## Context selection

Agents must read exactly these classes of files before editing:

```text
1. START_HERE.md
2. docs/PROJECT_INDEX.md
3. docs/AGENT_STATE_PROTOCOL.md
4. docs/TOOL_POLICY.md
5. the active phase doc
6. the module card
7. any module-specific context files listed under "Must-read context"
8. dependency handoff reports if the module depends on completed modules
```

The module card may list source files that do not exist yet. Missing source files are expected for implementation modules. Missing docs/templates are blockers.

## Loop termination

A single agent may keep looping only if the caller explicitly wants a full local run. Otherwise, complete one module and stop with a clean handoff.

For full-run mode:

```text
After finishing a module, re-read agent_state.json and choose the next ready module.
Never continue if an integration gate fails.
Never skip review gates.
```
