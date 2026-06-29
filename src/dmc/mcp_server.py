"""DMC MCP server (M09_MCP_SERVER) — a thin MCP surface over DMC core.

This module exposes existing DMC core functionality (schemas, store, planner,
renderer, retriever, precheck, recorder, distiller) through the Model Context
Protocol using the official MCP Python SDK's ``FastMCP``. It is deliberately a
*thin* adapter: every tool/resource/prompt handler is a small wrapper that
validates JSON-compatible input against the M01 Pydantic schemas and delegates
to a core function. No business logic is duplicated here.

Design rules (see ``modules/M09_MCP_SERVER.md`` and ``docs/TOOL_POLICY.md``):

* All durable shapes are imported from :mod:`dmc.schemas`; nothing is redefined.
* Tools return a JSON-compatible envelope ``{"ok", "data", "errors"}``.
* The DMC root is resolved from config/cwd, never hardcoded.
* No specific agent client is assumed; the server speaks plain MCP over stdio.
* ``dmc_export_agent_bundle`` is a lazy wrapper around M10's adapter; while M10
  is absent it returns a clean ``ok=False`` envelope instead of raising.

The tool/resource/prompt handlers are also exposed as plain functions so they
can be unit-tested directly against a temp DMC root + real :class:`DMCStore`
without spinning up a network server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dmc import distiller, planner, precheck, recorder, renderer, retriever
from dmc.schemas import (
    PlanGraph,
    PrecheckRequest,
    ProjectState,
    SearchRequest,
    SkillUpdateProposal,
    TaskRequest,
    TraceEvent,
)
from dmc.store import DMCError, DMCStore

__all__ = [
    "TOOL_NAMES",
    "RESOURCE_URIS",
    "PROMPT_NAMES",
    "envelope",
    "resolve_root",
    "dmc_plan_task",
    "dmc_render_graph",
    "dmc_get_briefing",
    "dmc_search",
    "dmc_precheck",
    "dmc_record_event",
    "dmc_commit_state",
    "dmc_distill_session",
    "dmc_propose_skill_update",
    "dmc_export_agent_bundle",
    "resource_project_state_current",
    "resource_briefing_latest",
    "resource_skill_tier1",
    "resource_skill_tier2",
    "resource_artifact",
    "resource_proposal_pending",
    "prompt_start_task",
    "prompt_checkpoint",
    "prompt_end_session_distill",
    "prompt_review_skill_proposals",
    "build_server",
    "main",
]

#: The 10 required tools (card lines 36-46).
TOOL_NAMES: tuple[str, ...] = (
    "dmc_plan_task",
    "dmc_render_graph",
    "dmc_get_briefing",
    "dmc_search",
    "dmc_precheck",
    "dmc_record_event",
    "dmc_commit_state",
    "dmc_distill_session",
    "dmc_propose_skill_update",
    "dmc_export_agent_bundle",
)

#: The 6 required resource URIs/templates (card lines 64-71).
RESOURCE_URIS: tuple[str, ...] = (
    "dmc://project_state/current",
    "dmc://briefing/latest",
    "dmc://skill/tier1/{id}",
    "dmc://skill/tier2/{id}",
    "dmc://artifact/{id}",
    "dmc://proposal/pending",
)

#: The 4 required prompts (card lines 75-80).
PROMPT_NAMES: tuple[str, ...] = (
    "dmc:start-task",
    "dmc:checkpoint",
    "dmc:end-session-distill",
    "dmc:review-skill-proposals",
)


# ---------------------------------------------------------------------------
# Envelope + root resolution helpers
# ---------------------------------------------------------------------------


def envelope(
    ok: bool, data: Any = None, errors: list[str] | None = None
) -> dict[str, Any]:
    """Build the JSON-compatible tool response envelope.

    Every tool returns ``{"ok": bool, "data": <json|None>, "errors": [str,...]}``.
    """
    return {"ok": ok, "data": data, "errors": errors or []}


def resolve_root(root: str | Path | None = None) -> Path:
    """Resolve the DMC project root without hardcoding any user path.

    Resolution order: explicit ``root`` argument, then the current working
    directory. The root need not exist yet; the store creates ``.dmc`` on init.
    """
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _get_store(root: str | Path | None = None) -> DMCStore:
    """Return an initialized :class:`DMCStore` rooted at ``resolve_root(root)``."""
    store = DMCStore(resolve_root(root))
    store.initialize()
    return store


# ---------------------------------------------------------------------------
# Tools (thin wrappers; all logic stays in core modules)
# ---------------------------------------------------------------------------


def dmc_plan_task(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Build a deterministic PlanGraph from a task request."""
    try:
        request = TaskRequest.model_validate(payload)
        graph = planner.plan_task(request, store)
        return envelope(True, graph.model_dump(mode="json"))
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_render_graph(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Render a PlanGraph to Mermaid or Markdown text."""
    try:
        graph = PlanGraph.model_validate(payload.get("graph", payload))
        fmt = str(payload.get("format", "mermaid")).lower()
        if fmt == "mermaid":
            text = renderer.render_plan_mermaid(graph)
        elif fmt in ("markdown", "md"):
            text = renderer.render_plan_markdown(graph)
        else:
            return envelope(False, None, [f"unknown format {fmt!r}"])
        return envelope(True, {"format": fmt, "text": text})
    except (ValidationError, DMCError, ValueError, TypeError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_get_briefing(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Produce a Markdown task briefing for a task request."""
    try:
        request = TaskRequest.model_validate(payload)
        graph = planner.plan_task(request, store)
        context = search_request_results(request, store)
        text = renderer.render_briefing(request, graph, context)
        return envelope(True, {"briefing": text})
    except (ValidationError, DMCError, ValueError, TypeError) as exc:
        return envelope(False, None, [str(exc)])


def search_request_results(request: TaskRequest, store: DMCStore):
    """Best-effort local context search for a briefing (never raises)."""
    try:
        return retriever.search(SearchRequest(query=request.task), store)
    except (DMCError, ValueError):
        return []


def dmc_search(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Search local DMC objects and return ranked results."""
    try:
        request = SearchRequest.model_validate(payload)
        results = retriever.search(request, store)
        return envelope(True, [r.model_dump(mode="json") for r in results])
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_precheck(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Run deterministic precheck rules over a proposed action."""
    try:
        request = PrecheckRequest.model_validate(payload)
        result = precheck.precheck(request, store)
        return envelope(True, result.model_dump(mode="json"))
    except (ValidationError, DMCError, ValueError, TypeError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_record_event(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Record a structured trace event to the append-only log."""
    try:
        event = TraceEvent.model_validate(payload)
        uri = recorder.record_event(event, store)
        return envelope(True, {"uri": uri})
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_commit_state(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Commit (upsert) the project state, returning the new version."""
    try:
        state = ProjectState.model_validate(payload)
        version = store.upsert_project_state(state)
        return envelope(True, {"version": version})
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_distill_session(payload: dict[str, Any], store: DMCStore) -> dict[str, Any]:
    """Distill a session into episode/eval/failure/proposal objects."""
    try:
        session_id = payload.get("session_id") or payload.get("session")
        if not session_id:
            return envelope(False, None, ["session_id is required"])
        result = distiller.distill_session(session_id, store)
        return envelope(True, result.model_dump(mode="json"))
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_propose_skill_update(
    payload: dict[str, Any], store: DMCStore
) -> dict[str, Any]:
    """Persist a pending skill-update proposal (never mutates skills)."""
    try:
        proposal = SkillUpdateProposal.model_validate(payload)
        uri = store.save_pending_proposal(proposal)
        return envelope(True, {"uri": uri})
    except (ValidationError, DMCError, ValueError) as exc:
        return envelope(False, None, [str(exc)])


def dmc_export_agent_bundle(
    payload: dict[str, Any], store: DMCStore
) -> dict[str, Any]:
    """Thin lazy wrapper over M10's adapter bundle export.

    Adapter generation is owned by M10_ADAPTERS. While that module is absent,
    return a clean ``ok=False`` envelope rather than failing.
    """
    try:
        from dmc.adapters import export_agent_bundle
    except ImportError:
        return envelope(False, None, ["M10_ADAPTERS not yet implemented"])
    try:
        result = export_agent_bundle(
            target=payload.get("target"),
            out=payload.get("out"),
            store=store,
        )
        data = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return envelope(True, data)
    except (DMCError, ValueError, TypeError) as exc:  # pragma: no cover - needs M10
        return envelope(False, None, [str(exc)])


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def resource_project_state_current(store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://project_state/current``."""
    try:
        return envelope(True, store.get_project_state().model_dump(mode="json"))
    except DMCError as exc:
        return envelope(False, None, [str(exc)])


def resource_briefing_latest(store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://briefing/latest`` from the latest written briefing."""
    path = store.dmc_dir / "briefing.md"
    if not path.exists():
        return envelope(False, None, ["no briefing has been written yet"])
    return envelope(True, {"briefing": path.read_text(encoding="utf-8")})


def resource_skill_tier1(skill_id: str, store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://skill/tier1/{id}``."""
    return _read_object_envelope(f"dmc://skill/tier1/{skill_id}", store)


def resource_skill_tier2(skill_id: str, store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://skill/tier2/{id}``."""
    return _read_object_envelope(f"dmc://skill/tier2/{skill_id}", store)


def resource_artifact(artifact_id: str, store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://artifact/{id}``; missing ids handled gracefully."""
    return _read_object_envelope(f"dmc://artifact/{artifact_id}", store)


def resource_proposal_pending(store: DMCStore) -> dict[str, Any]:
    """Resolve ``dmc://proposal/pending`` — list all pending proposals."""
    pending_dir = store.dmc_dir / "proposals" / "pending"
    items: list[dict[str, Any]] = []
    if pending_dir.exists():
        for path in sorted(pending_dir.glob("*.yaml")):
            try:
                items.append(store.read_object(f"dmc://proposal/{path.stem}"))
            except DMCError:
                continue
    return envelope(True, items)


def _read_object_envelope(uri: str, store: DMCStore) -> dict[str, Any]:
    try:
        return envelope(True, store.read_object(uri))
    except DMCError as exc:
        return envelope(False, None, [str(exc)])


# ---------------------------------------------------------------------------
# Prompts (plain text guidance; no client assumptions)
# ---------------------------------------------------------------------------


def prompt_start_task() -> str:
    """Prompt: bootstrap a new task with a plan and briefing."""
    return (
        "Start a DMC task: call dmc_plan_task with the task request, then "
        "dmc_get_briefing, and review the project_state/current resource before "
        "editing. Record each action with dmc_record_event."
    )


def prompt_checkpoint() -> str:
    """Prompt: checkpoint progress and commit state."""
    return (
        "Checkpoint: run dmc_precheck on the next action, record events with "
        "dmc_record_event, and commit progress with dmc_commit_state."
    )


def prompt_end_session_distill() -> str:
    """Prompt: end the session and distill memory."""
    return (
        "End session: call dmc_distill_session with the session_id to compile an "
        "episode, eval case, failure modes, and pending skill proposals."
    )


def prompt_review_skill_proposals() -> str:
    """Prompt: review pending skill proposals."""
    return (
        "Review skill proposals: read the proposal/pending resource and accept, "
        "revise, or reject each pending SkillUpdateProposal via the review path."
    )


# ---------------------------------------------------------------------------
# Server assembly
# ---------------------------------------------------------------------------


def build_server(root: str | Path | None = None):
    """Build and return a FastMCP server bound to the DMC root.

    Handlers are thin wrappers that delegate to the plain tool functions above,
    each operating against a single :class:`DMCStore` resolved from ``root``.
    """
    from mcp.server.fastmcp import FastMCP

    store = _get_store(root)
    server = FastMCP("dmc")

    @server.tool(name="dmc_plan_task")
    def _plan_task(task: dict) -> dict:
        return dmc_plan_task(task, store)

    @server.tool(name="dmc_render_graph")
    def _render_graph(payload: dict) -> dict:
        return dmc_render_graph(payload, store)

    @server.tool(name="dmc_get_briefing")
    def _get_briefing(task: dict) -> dict:
        return dmc_get_briefing(task, store)

    @server.tool(name="dmc_search")
    def _search(request: dict) -> dict:
        return dmc_search(request, store)

    @server.tool(name="dmc_precheck")
    def _precheck(action: dict) -> dict:
        return dmc_precheck(action, store)

    @server.tool(name="dmc_record_event")
    def _record_event(event: dict) -> dict:
        return dmc_record_event(event, store)

    @server.tool(name="dmc_commit_state")
    def _commit_state(state: dict) -> dict:
        return dmc_commit_state(state, store)

    @server.tool(name="dmc_distill_session")
    def _distill_session(payload: dict) -> dict:
        return dmc_distill_session(payload, store)

    @server.tool(name="dmc_propose_skill_update")
    def _propose_skill_update(proposal: dict) -> dict:
        return dmc_propose_skill_update(proposal, store)

    @server.tool(name="dmc_export_agent_bundle")
    def _export_agent_bundle(payload: dict) -> dict:
        return dmc_export_agent_bundle(payload, store)

    @server.resource("dmc://project_state/current")
    def _project_state() -> dict:
        return resource_project_state_current(store)

    @server.resource("dmc://briefing/latest")
    def _briefing_latest() -> dict:
        return resource_briefing_latest(store)

    @server.resource("dmc://skill/tier1/{id}")
    def _skill_tier1(id: str) -> dict:
        return resource_skill_tier1(id, store)

    @server.resource("dmc://skill/tier2/{id}")
    def _skill_tier2(id: str) -> dict:
        return resource_skill_tier2(id, store)

    @server.resource("dmc://artifact/{id}")
    def _artifact(id: str) -> dict:
        return resource_artifact(id, store)

    @server.resource("dmc://proposal/pending")
    def _proposal_pending() -> dict:
        return resource_proposal_pending(store)

    server.prompt(name="dmc:start-task")(prompt_start_task)
    server.prompt(name="dmc:checkpoint")(prompt_checkpoint)
    server.prompt(name="dmc:end-session-distill")(prompt_end_session_distill)
    server.prompt(name="dmc:review-skill-proposals")(prompt_review_skill_proposals)

    return server


def main(root: str | Path | None = None) -> None:
    """Run the DMC MCP server over stdio."""
    build_server(root).run()


if __name__ == "__main__":  # pragma: no cover
    main()
