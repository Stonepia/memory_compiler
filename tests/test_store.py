"""Tests for the DMC local-first store (M02_STORE)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dmc.schemas import (
    ArtifactCard,
    KnowledgeRef,
    ProjectState,
    SearchResult,
    Tier0Policy,
    Tier1Workflow,
    TraceEvent,
)
from dmc.store import (
    DMCNotFoundError,
    DMCStore,
    DMCValidationError,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def make_event(
    event_id: str,
    session_id: str,
    *,
    intent: str = "run unit tests",
    outcome: str = "passed",
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        session_id=session_id,
        phase="test",
        actor="agent",
        intent=intent,
        action={"kind": "run", "command": "pytest"},
        observation={"outcome": outcome},
        timestamp="2026-06-25T00:00:00Z",
        provenance=[{"source": f"session://{session_id}"}],
    )


def make_artifact(artifact_id: str, summary: str) -> ArtifactCard:
    return ArtifactCard(
        id=artifact_id,
        uri=f"file:///tmp/{artifact_id}.log",
        kind="log",
        summary=summary,
        metrics={"duration_s": 1.5},
        provenance=[{"source": f"session://{artifact_id}"}],
    )


def make_state(name: str = "dmc", status: str = "active") -> ProjectState:
    return ProjectState(
        name=name,
        status=status,
        current_phase="V0",
        summary="building the local store",
    )


def make_knowledge(knowledge_id: str, summary: str, **extra: object) -> KnowledgeRef:
    return KnowledgeRef(
        id=knowledge_id,
        kind="doc",
        uri=f"file:///tmp/{knowledge_id.replace('/', '_')}.md",
        summary=summary,
        provenance=[{"source": f"session://{knowledge_id.replace('/', '_')}"}],
        **extra,
    )


@pytest.fixture()
def store(tmp_path: Path) -> DMCStore:
    s = DMCStore(tmp_path)
    s.initialize()
    return s


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


def test_initialize_creates_layout_and_db(tmp_path: Path) -> None:
    s = DMCStore(tmp_path)
    s.initialize()
    assert (tmp_path / ".dmc").is_dir()
    assert s.memory_dir.is_dir()
    assert s.events_path.exists()
    assert s.artifacts_index_path.exists()
    assert s.objects_dir.is_dir()
    assert s.db_path.exists()


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    s = DMCStore(tmp_path)
    s.initialize()
    s.append_event(make_event("e1", "sess1"))
    # Calling again must not wipe data or error.
    s.initialize()
    s.initialize()
    assert len(s.list_events()) == 1
    assert s.events_path.exists()


# ---------------------------------------------------------------------------
# events: append-only + listing/filtering
# ---------------------------------------------------------------------------


def test_append_event_returns_uri(store: DMCStore) -> None:
    uri = store.append_event(make_event("e1", "sess1"))
    assert uri == "dmc://event/e1"


def test_list_events_all_and_filtered(store: DMCStore) -> None:
    store.append_event(make_event("e1", "sess1"))
    store.append_event(make_event("e2", "sess2"))
    store.append_event(make_event("e3", "sess1"))

    all_events = store.list_events()
    assert [e.event_id for e in all_events] == ["e1", "e2", "e3"]

    sess1 = store.list_events(session_id="sess1")
    assert [e.event_id for e in sess1] == ["e1", "e3"]
    assert all(isinstance(e, TraceEvent) for e in sess1)

    assert store.list_events(session_id="nope") == []


def test_events_jsonl_is_append_only(store: DMCStore) -> None:
    store.append_event(make_event("e1", "sess1"))
    first_lines = store.events_path.read_text(encoding="utf-8").splitlines()
    assert len(first_lines) == 1

    store.append_event(make_event("e2", "sess1"))
    second_lines = store.events_path.read_text(encoding="utf-8").splitlines()
    assert len(second_lines) == 2
    # The original first line is preserved byte-for-byte.
    assert second_lines[0] == first_lines[0]
    assert json.loads(second_lines[0])["event_id"] == "e1"


def test_append_event_rejects_non_event(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.append_event({"event_id": "e1"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# write_object / read_object round-trips
# ---------------------------------------------------------------------------


def test_write_read_object_yaml_roundtrip(store: DMCStore) -> None:
    data = {"id": "k1", "title": "BMG occupancy notes", "value": 42}
    uri = store.write_object("notes", "k1", data, ext="yaml")
    assert uri == "dmc://notes/k1"
    out = store.read_object(uri)
    assert out == data


def test_write_read_object_json_roundtrip(store: DMCStore) -> None:
    data = {"id": "k2", "title": "json object", "nested": {"a": [1, 2, 3]}}
    uri = store.write_object("notes", "k2", data, ext="json")
    out = store.read_object(uri)
    assert out == data


def test_write_object_accepts_basemodel(store: DMCStore) -> None:
    state = make_state(name="proj-x")
    uri = store.write_object("snapshots", "snap1", state, ext="yaml")
    out = store.read_object(uri)
    assert out["name"] == "proj-x"
    assert out["status"] == "active"


def test_write_object_rejects_bad_ext(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.write_object("notes", "k3", {"a": 1}, ext="exe")


def test_write_object_rejects_reserved_kind(store: DMCStore) -> None:
    # "skill" and "knowledge" have dedicated canonical APIs; write_object must
    # refuse them so .dmc/skills and .dmc/knowledge stay the single source of
    # truth (no dual write paths).
    with pytest.raises(DMCValidationError):
        store.write_object("knowledge", "k3", {"a": 1}, ext="yaml")
    with pytest.raises(DMCValidationError):
        store.write_object("skill", "s1", {"a": 1}, ext="yaml")


def test_read_object_invalid_uri_raises(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.read_object("not-a-uri")


def test_read_object_unknown_object_raises(store: DMCStore) -> None:
    with pytest.raises(DMCNotFoundError):
        store.read_object("dmc://notes/does_not_exist")
    with pytest.raises(DMCNotFoundError):
        store.read_object("dmc://knowledge/does_not_exist")


# ---------------------------------------------------------------------------
# path-traversal containment (write_object / read_object)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_kind", ["../escape", "a/b", "..", "", "a\\b"])
def test_write_object_rejects_path_traversal_kind(store: DMCStore, bad_kind: str) -> None:
    with pytest.raises(DMCValidationError):
        store.write_object(bad_kind, "obj1", {"a": 1}, ext="yaml")


@pytest.mark.parametrize("bad_id", ["../escape", "a/b", "..", "", "a\\b"])
def test_write_object_rejects_path_traversal_object_id(store: DMCStore, bad_id: str) -> None:
    with pytest.raises(DMCValidationError):
        store.write_object("notes", bad_id, {"a": 1}, ext="yaml")


def test_write_object_traversal_cannot_escape_objects_dir(store: DMCStore) -> None:
    # Even if a validation gap were reopened, _safe_child must still refuse to
    # write outside objects_dir. Escape sentinel must never be created.
    sentinel = store.dmc_dir / "escaped.yaml"
    with pytest.raises(DMCValidationError):
        store.write_object("notes", "..", {"a": 1}, ext="yaml")
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "bad_uri",
    [
        "dmc://notes/../escape",
        "dmc://../escape/x",
    ],
)
def test_read_object_rejects_path_traversal(store: DMCStore, bad_uri: str) -> None:
    with pytest.raises((DMCValidationError, DMCNotFoundError)):
        store.read_object(bad_uri)


# ---------------------------------------------------------------------------
# skills (canonical: .dmc/skills/tier{0,1,2}/<id>.yaml)
# ---------------------------------------------------------------------------


def test_write_read_skill_tier0_roundtrip(store: DMCStore) -> None:
    policy = Tier0Policy(id="always-cite", title="Always cite evidence", policy="cite")
    uri = store.write_skill(0, policy)
    assert uri == "dmc://skill/tier0/always-cite"
    assert (store.skills_dir / "tier0" / "always-cite.yaml").exists()
    assert not (store.objects_dir / "skill").exists()

    out = store.read_skill(0, "always-cite")
    assert out["id"] == "always-cite"
    assert out["tier"] == 0


def test_skill_resource_reads_dmc_skills_tier0(store: DMCStore) -> None:
    # dmc://skill/tier0/<id> must resolve through .dmc/skills, not .dmc/objects.
    store.write_skill(0, Tier0Policy(id="p1", title="Policy one", policy="always cite"))
    out = store.read_object("dmc://skill/tier0/p1")
    assert out["id"] == "p1"
    assert out["policy"] == "always cite"


def test_skill_resource_reads_dmc_skills_tier1(store: DMCStore) -> None:
    store.write_skill(
        1, Tier1Workflow(id="w1", title="Workflow one", steps=["a", "b"])
    )
    out = store.read_object("dmc://skill/tier1/w1")
    assert out["id"] == "w1"
    assert out["steps"] == ["a", "b"]


def test_list_skills_filters_by_tier(store: DMCStore) -> None:
    store.write_skill(0, Tier0Policy(id="p1", title="Policy one", policy="cite"))
    store.write_skill(1, Tier1Workflow(id="w1", title="Workflow one"))
    store.write_skill(1, Tier1Workflow(id="w2", title="Workflow two"))

    all_skills = store.list_skills()
    assert {s["id"] for s in all_skills} == {"p1", "w1", "w2"}

    tier1_only = store.list_skills(tier=1)
    assert {s["id"] for s in tier1_only} == {"w1", "w2"}


def test_write_skill_rejects_tier_mismatch(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.write_skill(1, Tier0Policy(id="p1", title="Policy one", policy="cite"))


def test_read_skill_missing_raises(store: DMCStore) -> None:
    with pytest.raises(DMCNotFoundError):
        store.read_skill(1, "does_not_exist")


# ---------------------------------------------------------------------------
# knowledge (canonical: .dmc/knowledge/<id>.yaml, id may be nested)
# ---------------------------------------------------------------------------


def test_write_read_knowledge_roundtrip(store: DMCStore) -> None:
    ref = make_knowledge("k1", "occupancy report")
    uri = store.write_knowledge(ref)
    assert uri == "dmc://knowledge/k1"
    assert (store.knowledge_dir / "k1.yaml").exists()

    out = store.read_knowledge("k1")
    assert out["id"] == "k1"
    assert out["summary"] == "occupancy report"


def test_write_read_nested_knowledge_roundtrip(store: DMCStore) -> None:
    ref = make_knowledge("hw/by-platform/bmg", "BMG platform notes")
    uri = store.write_knowledge(ref)
    assert uri == "dmc://knowledge/hw/by-platform/bmg"
    assert (store.knowledge_dir / "hw" / "by-platform" / "bmg.yaml").exists()

    out = store.read_knowledge("hw/by-platform/bmg")
    assert out["summary"] == "BMG platform notes"
    via_read_object = store.read_object(uri)
    assert via_read_object["summary"] == "BMG platform notes"


def test_knowledge_id_rejects_traversal_segment() -> None:
    with pytest.raises(ValueError):
        make_knowledge("hw/../etc", "bad")


def test_read_knowledge_rejects_traversal_segment(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.read_knowledge("hw/../etc")


def test_list_knowledge_includes_nested(store: DMCStore) -> None:
    store.write_knowledge(make_knowledge("k1", "flat"))
    store.write_knowledge(make_knowledge("hw/by-platform/bmg", "nested"))
    ids = {item["id"] for item in store.list_knowledge()}
    assert ids == {"k1", "hw/by-platform/bmg"}


# ---------------------------------------------------------------------------
# project state
# ---------------------------------------------------------------------------


def test_upsert_and_get_project_state_roundtrip(store: DMCStore) -> None:
    v1 = store.upsert_project_state(make_state(name="alpha", status="active"))
    assert v1 == 1
    got = store.get_project_state()
    assert isinstance(got, ProjectState)
    assert got.name == "alpha"
    assert got.status == "active"

    v2 = store.upsert_project_state(make_state(name="alpha", status="paused"))
    assert v2 == 2
    assert store.get_project_state().status == "paused"


def test_get_project_state_missing_raises(store: DMCStore) -> None:
    with pytest.raises(DMCNotFoundError):
        store.get_project_state()


def test_get_project_state_seeded_repo_root_is_valid() -> None:
    """The seeded .dmc/state/project_state.yaml must be ProjectState-valid.

    DMCStore.get_project_state() validates the file with ProjectState.model_validate().
    M09 exposes dmc://project_state/current and M11 uses 'dmc state show', so
    the seeded file must carry the required 'name' and 'status' fields.
    """
    import pathlib

    # Locate the repo root relative to this test file (tests/ -> repo root).
    repo_root = pathlib.Path(__file__).parent.parent
    seeded_state_path = repo_root / ".dmc" / "state" / "project_state.yaml"
    assert seeded_state_path.exists(), f"Seeded project_state.yaml not found at {seeded_state_path}"

    repo_store = DMCStore(repo_root)
    # Must not raise DMCStorageError / ValidationError.
    state = repo_store.get_project_state()
    assert isinstance(state, ProjectState)
    assert state.name, "ProjectState.name must be non-empty"
    assert state.status, "ProjectState.status must be non-empty"


def test_read_object_project_state_uri(store: DMCStore) -> None:
    store.upsert_project_state(make_state(name="beta"))
    out = store.read_object("dmc://project_state/current")
    assert out["name"] == "beta"


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------


def test_save_artifact_card_writes_file_and_appends_index(store: DMCStore) -> None:
    uri = store.save_artifact_card(make_artifact("a1", "first artifact"))
    assert uri == "dmc://artifact/a1"
    assert (store.artifacts_cards_dir / "a1.yaml").exists()

    store.save_artifact_card(make_artifact("a2", "second artifact"))
    index_lines = store.artifacts_index_path.read_text(encoding="utf-8").splitlines()
    assert len(index_lines) == 2
    ids = [json.loads(line)["id"] for line in index_lines]
    assert ids == ["a1", "a2"]
    # Index is append-only: first line untouched after the second append.
    assert json.loads(index_lines[0])["id"] == "a1"

    out = store.read_object(uri)
    assert out["summary"] == "first artifact"


# ---------------------------------------------------------------------------
# search_text
# ---------------------------------------------------------------------------


def test_search_text_returns_hits(store: DMCStore) -> None:
    store.write_knowledge(make_knowledge("k1", "BMG occupancy low: warp stalls"))
    store.write_knowledge(make_knowledge("k2", "unrelated: nothing here"))
    results = store.search_text("occupancy", scopes=["knowledge"])
    assert results
    assert all(isinstance(r, SearchResult) for r in results)
    assert results[0].uri == "dmc://knowledge/k1"


def test_search_text_respects_scopes(store: DMCStore) -> None:
    store.write_knowledge(make_knowledge("k1", "occupancy report"))
    store.append_event(make_event("e1", "sess1", intent="occupancy probe"))

    # Restrict to memory scope: only the event should match.
    mem = store.search_text("occupancy", scopes=["memory"])
    assert [r.kind for r in mem] == ["event"]

    know = store.search_text("occupancy", scopes=["knowledge"])
    assert [r.kind for r in know] == ["knowledge"]

    both = store.search_text("occupancy", scopes=["memory", "knowledge"])
    assert {r.kind for r in both} == {"event", "knowledge"}


def test_search_text_respects_limit(store: DMCStore) -> None:
    for i in range(5):
        store.write_knowledge(make_knowledge(f"k{i}", f"occupancy item {i}"))
    results = store.search_text("occupancy", scopes=["knowledge"], limit=2)
    assert len(results) == 2


def test_knowledge_scope_reads_dmc_knowledge(store: DMCStore) -> None:
    # .dmc/knowledge is the single source of truth for the "knowledge" scope —
    # not .dmc/objects/knowledge.
    store.write_knowledge(make_knowledge("k1", "occupancy report"))
    assert (store.knowledge_dir / "k1.yaml").exists()
    assert not (store.objects_dir / "knowledge").exists()
    hits = store.search_text("occupancy", scopes=["knowledge"])
    assert [r.uri for r in hits] == ["dmc://knowledge/k1"]


def test_search_text_empty_query_raises(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.search_text("   ", scopes=["knowledge"])


def test_search_text_requires_scope(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        store.search_text("occupancy", scopes=[])


# ---------------------------------------------------------------------------
# rebuild from files (SQLite is a rebuildable cache, not source of truth)
# ---------------------------------------------------------------------------


def test_rebuild_index_from_files(store: DMCStore) -> None:
    store.write_knowledge(make_knowledge("k1", "occupancy low"))
    store.append_event(make_event("e1", "sess1", intent="occupancy probe"))
    store.save_artifact_card(make_artifact("a1", "occupancy artifact"))
    store.upsert_project_state(make_state(name="occupancy-proj"))

    # Destroy the SQLite cache entirely; files remain the source of truth.
    store.close()
    store.db_path.unlink()
    assert not store.db_path.exists()

    rebuilt = DMCStore(store.root)
    rebuilt.initialize()
    count = rebuilt.rebuild_index()
    assert count >= 4

    # Search works again after a pure-from-files rebuild.
    hits = rebuilt.search_text(
        "occupancy", scopes=["knowledge", "memory", "artifacts", "state"]
    )
    uris = {r.uri for r in hits}
    assert "dmc://knowledge/k1" in uris
    assert "dmc://event/e1" in uris
    assert "dmc://artifact/a1" in uris

    # And the file-backed objects still read back correctly.
    assert rebuilt.get_project_state().name == "occupancy-proj"
    assert rebuilt.read_object("dmc://knowledge/k1")["summary"] == "occupancy low"


def test_rebuild_index_includes_skills_and_nested_knowledge(store: DMCStore) -> None:
    store.write_skill(
        0, Tier0Policy(id="always-cite", title="Always cite evidence", policy="cite")
    )
    store.write_skill(
        1,
        Tier1Workflow(
            id="bench-flow", title="Benchmark workflow", steps=["run", "compare"]
        ),
    )
    store.write_knowledge(make_knowledge("hw/by-platform/bmg", "BMG platform notes"))

    store.close()
    store.db_path.unlink()
    rebuilt = DMCStore(store.root)
    rebuilt.initialize()
    rebuilt.rebuild_index()

    # FTS5 MATCH uses implicit AND between bareword terms, so each term is
    # queried separately against the row it uniquely appears in.
    tier0_hits = {r.uri for r in rebuilt.search_text("cite", scopes=["skills"])}
    tier1_hits = {r.uri for r in rebuilt.search_text("compare", scopes=["skills"])}
    knowledge_hits = {r.uri for r in rebuilt.search_text("bmg", scopes=["knowledge"])}
    assert "dmc://skill/tier0/always-cite" in tier0_hits
    assert "dmc://skill/tier1/bench-flow" in tier1_hits
    assert "dmc://knowledge/hw/by-platform/bmg" in knowledge_hits


def test_rebuild_index_includes_pending_proposals(tmp_path: Path) -> None:
    """Pending proposals must survive a full index-delete + rebuild cycle."""
    from dmc.distiller import distill_session
    from dmc.recorder import record_event
    from dmc.retriever import search
    from dmc.schemas import SearchRequest, TraceAction, TraceEvent, TraceObservation

    store = DMCStore(tmp_path)
    store.initialize()

    session_id = "rebuild-prop-sess"
    record_event(
        TraceEvent(
            event_id="rp1",
            session_id=session_id,
            phase="benchmark",
            actor="agent",
            intent="benchmark kernel",
            action=TraceAction(kind="benchmark_run"),
            observation=TraceObservation(outcome="regressed: tile too large"),
            timestamp="2026-06-25T00:00:00Z",
            provenance=[{"source": f"session://{session_id}"}],
        ),
        store,
    )
    result = distill_session(session_id, store)
    assert result.proposal_uris, "distill_session must produce at least one proposal"

    # Destroy SQLite — plain files remain source of truth.
    store.close()
    store.db_path.unlink()
    assert not store.db_path.exists()

    rebuilt = DMCStore(tmp_path)
    rebuilt.initialize()
    rebuilt.rebuild_index()

    # Pending proposals must be searchable after a cold rebuild.
    hits = search(SearchRequest(query="tile", scopes=["proposals"]), rebuilt)
    uris = {r.uri for r in hits}
    proposal_id = result.proposal_uris[0].split("dmc://proposal/", 1)[-1]
    assert f"dmc://proposal/{proposal_id}" in uris, (
        f"Expected dmc://proposal/{proposal_id} in rebuilt index, got {uris}"
    )
    # URI must be DMC-readable (read_object resolves to the pending file).
    data = rebuilt.read_object(f"dmc://proposal/{proposal_id}")
    assert data.get("status") == "pending"


def test_list_pending_proposals_empty(tmp_path: Path) -> None:
    """No pending dir -> empty entries, no errors."""
    store = DMCStore(tmp_path)
    store.initialize()
    entries, errors = store.list_pending_proposals()
    assert entries == [] and errors == []


def test_list_pending_proposals_returns_entries(tmp_path: Path) -> None:
    from dmc.schemas import SkillUpdateProposal

    store = DMCStore(tmp_path)
    store.initialize()
    store.save_pending_proposal(
        SkillUpdateProposal(
            id="p1", target="skill://tier1/x", change_kind="create",
            rationale="r", provenance=[{"source": "session://s"}],
        )
    )
    entries, errors = store.list_pending_proposals()
    assert errors == []
    assert [e["id"] for e in entries] == ["p1"]


def test_list_pending_proposals_surfaces_corrupt(tmp_path: Path) -> None:
    """Corrupt files are reported in errors, never silently dropped."""
    from dmc.schemas import SkillUpdateProposal

    store = DMCStore(tmp_path)
    store.initialize()
    store.save_pending_proposal(
        SkillUpdateProposal(
            id="good", target="skill://tier1/x", change_kind="create",
            rationale="r", provenance=[{"source": "session://s"}],
        )
    )
    bad = store.dmc_dir / "proposals" / "pending" / "bad.yaml"
    bad.write_text("::: not: valid: [", encoding="utf-8")
    entries, errors = store.list_pending_proposals()
    assert [e["id"] for e in entries] == ["good"]
    assert errors and any("bad.yaml" in e for e in errors)
