"""Tests for the DMC MCP server (M09_MCP_SERVER).

These tests call the tool/resource/prompt handler functions directly against a
temporary DMC root and a real :class:`DMCStore`. No network server is spun up.
"""

from __future__ import annotations

import pytest

from dmc import mcp_server as m
from dmc.recorder import record_event
from dmc.schemas import ArtifactCard, ProjectState, TraceEvent
from dmc.store import DMCStore


@pytest.fixture()
def store(tmp_path) -> DMCStore:
    s = DMCStore(tmp_path)
    s.initialize()
    return s


def _envelope_ok(result: dict) -> bool:
    assert set(result.keys()) == {"ok", "data", "errors"}
    assert isinstance(result["errors"], list)
    return result["ok"]


# ---------------------------------------------------------------------------
# Envelope/root helpers
# ---------------------------------------------------------------------------


def test_resolve_root_defaults_to_cwd(tmp_path):
    assert m.resolve_root(tmp_path) == tmp_path.resolve()
    assert m.resolve_root(None).is_absolute()


def test_envelope_shape():
    assert m.envelope(True, {"x": 1}) == {"ok": True, "data": {"x": 1}, "errors": []}
    assert m.envelope(False, None, ["bad"])["errors"] == ["bad"]


# ---------------------------------------------------------------------------
# Tools: happy paths
# ---------------------------------------------------------------------------


def test_plan_task_ok(store):
    r = m.dmc_plan_task({"id": "t1", "task": "do a thing"}, store)
    assert _envelope_ok(r)
    assert r["data"]["id"] == "plan_t1"
    assert len(r["data"]["nodes"]) == 8


def test_render_graph_ok(store):
    plan = m.dmc_plan_task({"id": "t1", "task": "x"}, store)["data"]
    merm = m.dmc_render_graph({"graph": plan, "format": "mermaid"}, store)
    assert _envelope_ok(merm)
    assert merm["data"]["text"].startswith("flowchart TD")
    md = m.dmc_render_graph({"graph": plan, "format": "markdown"}, store)
    assert _envelope_ok(md)
    assert md["data"]["text"].startswith("# Plan")


def test_get_briefing_ok(store):
    r = m.dmc_get_briefing({"id": "t1", "task": "fix bug"}, store)
    assert _envelope_ok(r)
    assert "# Briefing" in r["data"]["briefing"]


def test_search_ok(store):
    store.upsert_project_state(ProjectState(name="proj", status="active"))
    r = m.dmc_search({"query": "proj", "scopes": ["project_state"]}, store)
    assert _envelope_ok(r)
    assert isinstance(r["data"], list)


def test_precheck_ok(store):
    r = m.dmc_precheck({"action": "read file", "files": ["a.py"]}, store)
    assert _envelope_ok(r)
    assert r["data"]["decision"] in ("allow", "warn", "block")


def make_event(eid: str = "e1") -> dict:
    return {
        "event_id": eid,
        "session_id": "sess_demo",
        "phase": "test",
        "actor": "agent",
        "intent": "run tests",
        "action": {"kind": "test_run", "command": "pytest"},
        "observation": {"outcome": "success"},
        "timestamp": "2026-06-25T00:00:00Z",
        "provenance": [{"source": "session://sess_demo"}],
    }


def test_record_event_ok(store):
    r = m.dmc_record_event(make_event(), store)
    assert _envelope_ok(r)
    assert r["data"]["uri"] == "dmc://event/e1"


def test_commit_state_ok(store):
    r = m.dmc_commit_state({"name": "p", "status": "active"}, store)
    assert _envelope_ok(r)
    assert r["data"]["version"] == 1


def test_distill_session_ok(store):
    record_event(TraceEvent.model_validate(make_event()), store)
    r = m.dmc_distill_session({"session_id": "sess_demo"}, store)
    assert _envelope_ok(r)
    assert r["data"]["session_id"] == "sess_demo"
    assert r["data"]["episode_uri"]


def test_propose_skill_update_ok(store):
    r = m.dmc_propose_skill_update(
        {
            "id": "prop1",
            "target": "skill://tier1/x",
            "change_kind": "create",
            "rationale": "because",
            "provenance": [{"source": "session://s"}],
        },
        store,
    )
    assert _envelope_ok(r)
    assert r["data"]["uri"] == "dmc://proposal/prop1"


# ---------------------------------------------------------------------------
# Tools: lazy export + invalid input
# ---------------------------------------------------------------------------


def test_export_agent_bundle_lazy_fallback(store):
    r = m.dmc_export_agent_bundle({"target": "codex"}, store)
    assert set(r.keys()) == {"ok", "data", "errors"}
    if not r["ok"]:
        assert r["errors"] == ["M10_ADAPTERS not yet implemented"]
        assert r["data"] is None
    else:
        # M10 present: lazy fallback successfully delegated.
        assert r["data"] is not None


def test_invalid_input_returns_envelope_not_exception(store):
    r = m.dmc_plan_task({"task": "missing id"}, store)
    assert r["ok"] is False
    assert r["errors"]
    r2 = m.dmc_record_event({"bad": "event"}, store)
    assert r2["ok"] is False and r2["errors"]
    r3 = m.dmc_distill_session({}, store)
    assert r3["ok"] is False and r3["errors"]


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def test_resource_project_state(store):
    store.upsert_project_state(ProjectState(name="proj", status="active"))
    r = m.resource_project_state_current(store)
    assert _envelope_ok(r)
    assert r["data"]["name"] == "proj"


def test_resource_proposal_pending(store):
    m.dmc_propose_skill_update(
        {
            "id": "prop1",
            "target": "skill://tier1/x",
            "change_kind": "create",
            "rationale": "r",
            "provenance": [{"source": "session://s"}],
        },
        store,
    )
    r = m.resource_proposal_pending(store)
    assert _envelope_ok(r)
    assert any(item["id"] == "prop1" for item in r["data"])


def test_resource_artifact_missing_graceful(store):
    r = m.resource_artifact("nope", store)
    assert r["ok"] is False and r["errors"]


def test_resource_proposal_pending_surfaces_corrupt(store):
    m.dmc_propose_skill_update(
        {
            "id": "good1",
            "target": "skill://tier1/x",
            "change_kind": "create",
            "rationale": "r",
            "provenance": [{"source": "session://s"}],
        },
        store,
    )
    corrupt = store.dmc_dir / "proposals" / "pending" / "bad.yaml"
    corrupt.write_text("::: not: valid: yaml: [", encoding="utf-8")
    r = m.resource_proposal_pending(store)
    assert r["ok"] is False
    assert r["errors"] and any("bad.yaml" in e for e in r["errors"])
    assert any(item["id"] == "good1" for item in r["data"])


def test_resource_artifact_present(store):
    card = ArtifactCard(
        id="art1", uri="dmc://artifact/art1", kind="bench", summary="s",
        provenance=[{"source": "session://s"}],
    )
    store.save_artifact_card(card)
    r = m.resource_artifact("art1", store)
    assert _envelope_ok(r)


def test_resource_briefing_missing(store):
    assert m.resource_briefing_latest(store)["ok"] is False


# ---------------------------------------------------------------------------
# Prompts + server registration
# ---------------------------------------------------------------------------


def test_prompts_text():
    for fn in (
        m.prompt_start_task, m.prompt_checkpoint,
        m.prompt_end_session_distill, m.prompt_review_skill_proposals,
    ):
        assert isinstance(fn(), str) and fn()


def test_server_registration(tmp_path):
    import asyncio

    server = m.build_server(tmp_path)
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert set(m.TOOL_NAMES) <= tools
    prompts = {p.name for p in asyncio.run(server.list_prompts())}
    assert set(m.PROMPT_NAMES) <= prompts
    resources = asyncio.run(server.list_resources())
    templates = asyncio.run(server.list_resource_templates())
    assert resources or templates


# ---------------------------------------------------------------------------
# MCP-level: generated input schemas expose top-level fields (no nested wrapper)
# ---------------------------------------------------------------------------


def test_tool_input_schemas_are_flat_not_wrapped(tmp_path):
    import asyncio

    server = m.build_server(tmp_path)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    plan = tools["dmc_plan_task"].inputSchema
    assert "id" in plan["properties"] and "task" in plan["properties"]
    assert set(plan["required"]) == {"id", "task"}
    assert "task" not in plan["properties"].get("task", {}).get("properties", {})

    srch = tools["dmc_search"].inputSchema
    assert "query" in srch["properties"]
    assert srch["required"] == ["query"]
    assert "request" not in srch["properties"]

    ev = tools["dmc_record_event"].inputSchema
    for field in ("event_id", "session_id", "phase", "actor", "intent",
                  "action", "observation", "timestamp", "provenance"):
        assert field in ev["properties"], field
    assert "event" not in ev["properties"]


def test_read_resource_all_six(tmp_path):
    import asyncio

    store = DMCStore(tmp_path)
    store.initialize()
    store.upsert_project_state(ProjectState(name="proj", status="active"))
    store.save_artifact_card(
        ArtifactCard(id="art1", uri="dmc://artifact/art1", kind="bench",
                     summary="s", provenance=[{"source": "session://s"}])
    )
    server = m.build_server(tmp_path)
    for uri in (
        "dmc://project_state/current",
        "dmc://briefing/latest",
        "dmc://skill/tier1/x",
        "dmc://skill/tier2/y",
        "dmc://artifact/art1",
        "dmc://proposal/pending",
    ):
        contents = asyncio.run(server.read_resource(uri))
        assert contents is not None


def test_all_four_prompts_registered(tmp_path):
    import asyncio

    server = m.build_server(tmp_path)
    names = {p.name for p in asyncio.run(server.list_prompts())}
    assert set(m.PROMPT_NAMES) == names & set(m.PROMPT_NAMES)
    assert len(set(m.PROMPT_NAMES)) == 4
