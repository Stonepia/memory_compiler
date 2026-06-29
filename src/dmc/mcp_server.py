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


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` entries so unset optional tool args fall back to defaults."""
    return {k: v for k, v in values.items() if v is not None}


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

    Adapter generation is owned by M10_ADAPTERS. While that module is genuinely
    absent (``dmc.adapters`` missing, or no ``export_agent_bundle`` symbol) we
    return a clean ``ok=False`` envelope. A *real* ImportError raised from
    inside ``dmc.adapters`` (a broken dependency once M10 exists) is reported
    distinctly rather than masked as "not yet implemented".
    """
    try:
        import dmc.adapters as adapters_mod
    except ModuleNotFoundError as exc:
        if exc.name in ("dmc.adapters", "adapters"):
            return envelope(False, None, ["M10_ADAPTERS not yet implemented"])
        # A dependency *inside* adapters is missing — surface it distinctly.
        return envelope(False, None, [f"dmc.adapters import error: {exc}"])
    except ImportError as exc:  # pragma: no cover - needs broken M10
        return envelope(False, None, [f"dmc.adapters import error: {exc}"])

    export_agent_bundle = getattr(adapters_mod, "export_agent_bundle", None)
    if export_agent_bundle is None:
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
    """Resolve ``dmc://proposal/pending`` — list all pending proposals.

    Delegates enumeration to :meth:`DMCStore.list_pending_proposals`. Any
    read/parse errors are surfaced in the envelope ``errors`` field (never
    silently dropped); ``ok`` is ``False`` when corrupt entries were found.
    """
    items, errors = store.list_pending_proposals()
    return envelope(not errors, items, errors)


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

    # Tools register with explicit top-level fields mirroring the DMC Pydantic
    # schemas so FastMCP generates input schemas whose required fields are the
    # schema's own top-level fields (no nested `{"task": {...}}` wrapper).

    @server.tool(name="dmc_plan_task")
    def _plan_task(
        id: str,
        task: str,
        repo: str | None = None,
        mode: str | None = None,
        hardware: list[str] | None = None,
        changed_files: list[str] | None = None,
        current_phase: str | None = None,
        budget_tokens: int | None = None,
        constraints: list[str] | None = None,
    ) -> dict:
        return dmc_plan_task(_clean(locals()), store)

    @server.tool(name="dmc_render_graph")
    def _render_graph(graph: dict, format: str = "mermaid") -> dict:
        return dmc_render_graph({"graph": graph, "format": format}, store)

    @server.tool(name="dmc_get_briefing")
    def _get_briefing(
        id: str,
        task: str,
        repo: str | None = None,
        mode: str | None = None,
        hardware: list[str] | None = None,
        changed_files: list[str] | None = None,
        current_phase: str | None = None,
        budget_tokens: int | None = None,
        constraints: list[str] | None = None,
    ) -> dict:
        return dmc_get_briefing(_clean(locals()), store)

    @server.tool(name="dmc_search")
    def _search(
        query: str,
        scopes: list[str] | None = None,
        filters: dict | None = None,
        limit: int = 10,
        budget_tokens: int | None = None,
    ) -> dict:
        return dmc_search(_clean(locals()), store)

    @server.tool(name="dmc_precheck")
    def _precheck(
        action: str,
        files: list[str] | None = None,
        command: str | None = None,
        intent: str | None = None,
        risk_level: str | None = None,
        task_context: dict | None = None,
    ) -> dict:
        return dmc_precheck(_clean(locals()), store)

    @server.tool(name="dmc_record_event")
    def _record_event(
        event_id: str,
        session_id: str,
        phase: str,
        actor: str,
        intent: str,
        action: dict,
        observation: dict,
        timestamp: str,
        provenance: list[dict],
        run_id: str | None = None,
        step_id: int | None = None,
        repo_state: dict | None = None,
        artifacts: dict | None = None,
        reasoning_summary: dict | None = None,
        memory_hooks: dict | None = None,
    ) -> dict:
        return dmc_record_event(_clean(locals()), store)

    @server.tool(name="dmc_commit_state")
    def _commit_state(
        name: str,
        status: str,
        current_phase: str | None = None,
        summary: str | None = None,
        active_task: str | None = None,
        open_questions: list[str] | None = None,
        updated_at: str | None = None,
    ) -> dict:
        return dmc_commit_state(_clean(locals()), store)

    @server.tool(name="dmc_distill_session")
    def _distill_session(session_id: str) -> dict:
        return dmc_distill_session({"session_id": session_id}, store)

    @server.tool(name="dmc_propose_skill_update")
    def _propose_skill_update(
        id: str,
        target: str,
        change_kind: str,
        rationale: str,
        provenance: list[dict],
        diff_summary: str | None = None,
        status: str = "pending",
        evidence: list[dict] | None = None,
    ) -> dict:
        return dmc_propose_skill_update(_clean(locals()), store)

    @server.tool(name="dmc_export_agent_bundle")
    def _export_agent_bundle(target: str, out: str | None = None) -> dict:
        return dmc_export_agent_bundle({"target": target, "out": out}, store)

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
