"""Tests for deterministic session distillation (M08_DISTILLER_EVALS)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dmc.distiller import (
    build_episode_card,
    build_eval_case,
    distill_session,
    is_failure_event,
    is_success_validation_event,
    propose_failure_modes,
    propose_skill_updates,
)
from dmc.recorder import record_event, session_events
from dmc.schemas import (
    DistillResult,
    EpisodeCard,
    EvalCase,
    FailureMode,
    SkillUpdateProposal,
    TraceEvent,
)
from dmc.store import DMCStore


# ---------------------------------------------------------------------------
# Builders / fixtures
# ---------------------------------------------------------------------------


def make_event(
    event_id: str,
    session_id: str,
    *,
    phase: str = "test",
    kind: str = "test_run",
    outcome: str = "success",
    intent: str = "run unit tests",
    timestamp: str = "2026-06-25T00:00:00Z",
    artifacts: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        session_id=session_id,
        phase=phase,
        actor="agent",
        intent=intent,
        action={"kind": kind, "command": "pytest"},
        observation={"outcome": outcome},
        timestamp=timestamp,
        artifacts=artifacts or {},
        provenance=[{"source": f"session://{session_id}"}],
    )


@pytest.fixture()
def store(tmp_path: Path) -> DMCStore:
    s = DMCStore(tmp_path)
    s.initialize()
    return s


def seed_mixed_session(store: DMCStore, session_id: str = "sessMix") -> str:
    """A session with successful validation events and a failed/regressed one."""
    record_event(
        make_event("e1", session_id, phase="test", kind="test_run", outcome="success"),
        store,
    )
    record_event(
        make_event(
            "e2",
            session_id,
            phase="validate",
            kind="test_run",
            outcome="passed",
            intent="validate fix",
        ),
        store,
    )
    record_event(
        make_event(
            "e3",
            session_id,
            phase="benchmark",
            kind="benchmark_run",
            outcome="regressed",
            intent="benchmark hot loop",
        ),
        store,
    )
    return session_id


def seed_clean_session(store: DMCStore, session_id: str = "sessClean") -> str:
    """A session with only clean successful events (no failures)."""
    record_event(
        make_event("c1", session_id, phase="test", kind="test_run", outcome="success"),
        store,
    )
    record_event(
        make_event(
            "c2",
            session_id,
            phase="validate",
            kind="test_run",
            outcome="passed",
            intent="validate",
        ),
        store,
    )
    return session_id


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_failure_and_success_classification() -> None:
    fail = make_event("x", "s", phase="benchmark", outcome="regressed")
    ok = make_event("y", "s", phase="test", outcome="success")
    edit = make_event("z", "s", phase="edit", kind="file_edit", outcome="success")
    assert is_failure_event(fail) is True
    assert is_failure_event(ok) is False
    assert is_success_validation_event(ok) is True
    # A successful edit is not a *validation* phase, so not useful_memory.
    assert is_success_validation_event(edit) is False


# ---------------------------------------------------------------------------
# build_episode_card
# ---------------------------------------------------------------------------


def test_build_episode_card_has_provenance_and_labels(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    events = session_events(session_id, store)
    card = build_episode_card(session_id, events)

    assert isinstance(card, EpisodeCard)
    assert card.session_id == session_id
    # non-empty provenance referencing the session
    assert len(card.provenance) >= 1
    sources = [p.source for p in card.provenance]
    assert f"session://{session_id}" in sources
    # useful_memory label appears for successful validation events
    assert "e1" in card.labels["useful_memory"]
    assert "e2" in card.labels["useful_memory"]
    # wrong_turn label appears for the regressed event
    assert "e3" in card.labels["wrong_turn"]
    assert card.outcome == "failed"


# ---------------------------------------------------------------------------
# build_eval_case
# ---------------------------------------------------------------------------


def test_build_eval_case_is_schema_valid(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    events = session_events(session_id, store)
    # Constructing the eval case must NOT raise.
    case = build_eval_case(session_id, events)

    assert isinstance(case, EvalCase)
    assert case.source_session == session_id
    assert case.task.id == session_id
    # mandatory plan ref synthesized deterministically from the session
    assert case.initial_plan_graph == f"plan://{session_id}/initial"
    assert case.outcome["status"] == "failed"
    assert case.labels["useful_memory"] == ["e1", "e2"]
    assert case.labels["wrong_turn"] == ["e3"]
    assert len(case.provenance) >= 1
    assert f"session://{session_id}" in [p.source for p in case.provenance]


# ---------------------------------------------------------------------------
# propose_failure_modes
# ---------------------------------------------------------------------------


def test_propose_failure_modes_from_failed_event(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    events = session_events(session_id, store)
    modes = propose_failure_modes(session_id, events)

    assert len(modes) == 1
    mode = modes[0]
    assert isinstance(mode, FailureMode)
    # wrong_turn label present where required
    assert mode.labels["wrong_turn"] == ["e3"]
    # non-empty provenance referencing session + the triggering event
    sources = [p.source for p in mode.provenance]
    assert f"session://{session_id}" in sources
    assert "event://e3" in sources
    assert mode.evidence and mode.evidence[0].uri == "event://e3"


def test_propose_failure_modes_empty_for_clean_session(store: DMCStore) -> None:
    session_id = seed_clean_session(store)
    events = session_events(session_id, store)
    assert propose_failure_modes(session_id, events) == []


# ---------------------------------------------------------------------------
# propose_skill_updates
# ---------------------------------------------------------------------------


def test_propose_skill_updates_are_pending_with_provenance(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    events = session_events(session_id, store)
    proposals = propose_skill_updates(session_id, events)

    assert proposals
    for proposal in proposals:
        assert isinstance(proposal, SkillUpdateProposal)
        # proposals are pending candidates
        assert proposal.status == "pending"
        # non-empty provenance
        assert len(proposal.provenance) >= 1
        # never targets accepted skills directory (skill:// scheme, not a path)
        assert proposal.target.startswith("skill://")
    # useful_memory proposals exist for the successful validations
    labels_union: set[str] = set()
    for proposal in proposals:
        labels_union.update(getattr(proposal, "labels", {}).keys())
    assert "useful_memory" in labels_union
    assert "wrong_turn" in labels_union


def test_propose_skill_updates_does_not_write_skills(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    events = session_events(session_id, store)
    propose_skill_updates(session_id, events)
    # pure builder: nothing under .dmc/skills should have been created
    skills_dir = store.dmc_dir / "skills"
    skill_files = [p for p in skills_dir.rglob("*") if p.is_file()]
    assert skill_files == []


# ---------------------------------------------------------------------------
# distill_session (persistence + determinism)
# ---------------------------------------------------------------------------


def test_distill_session_persists_and_is_deterministic(store: DMCStore) -> None:
    session_id = seed_mixed_session(store)
    result = distill_session(session_id, store)

    assert isinstance(result, DistillResult)
    assert result.session_id == session_id

    # persisted durable objects exist in the store and round-trip back
    assert result.episode_uri == "dmc://episode/episode-sessMix"
    assert result.eval_case_uri == "dmc://eval_case/evalcase-sessMix"
    assert store.read_object(result.episode_uri)["session_id"] == session_id
    assert store.read_object(result.eval_case_uri)["source_session"] == session_id
    assert len(result.failure_mode_uris) == 1
    assert store.read_object(result.failure_mode_uris[0])["trigger"]

    # skill proposals go to .dmc/proposals/pending ONLY and are indexed
    pending_dir = store.dmc_dir / "proposals" / "pending"
    pending_files = sorted(p.name for p in pending_dir.glob("*.yaml"))
    assert pending_files
    assert all(uri.startswith("dmc://proposal/") for uri in result.proposal_uris)
    # nothing written under .dmc/skills
    skill_files = [p for p in (store.dmc_dir / "skills").rglob("*") if p.is_file()]
    assert skill_files == []

    # every durable output carries non-empty provenance
    assert result.episode.provenance
    assert result.eval_case.provenance
    for fm in result.failure_modes:
        assert fm.provenance
    for proposal in result.skill_proposals:
        assert proposal.provenance

    # re-running is deterministic (same refs, same persisted content)
    pending_before = {
        p.name: p.read_text() for p in pending_dir.glob("*.yaml")
    }
    episode_before = store.read_object(result.episode_uri)
    result2 = distill_session(session_id, store)
    assert result2.episode_uri == result.episode_uri
    assert result2.eval_case_uri == result.eval_case_uri
    assert result2.failure_mode_uris == result.failure_mode_uris
    assert result2.proposal_uris == result.proposal_uris
    assert store.read_object(result.episode_uri) == episode_before
    pending_after = {p.name: p.read_text() for p in pending_dir.glob("*.yaml")}
    assert pending_after == pending_before


def test_distill_session_clean_session_has_no_failures(store: DMCStore) -> None:
    session_id = seed_clean_session(store)
    result = distill_session(session_id, store)

    # still a valid episode + eval case with non-empty provenance
    assert isinstance(result.episode, EpisodeCard)
    assert isinstance(result.eval_case, EvalCase)
    assert result.episode.provenance
    assert result.eval_case.provenance
    # no failure modes for a clean session
    assert result.failure_modes == []
    assert result.failure_mode_uris == []
    # useful_memory still captured on the eval case labels
    assert result.eval_case.labels["useful_memory"] == ["c1", "c2"]
    assert result.eval_case.labels["wrong_turn"] == []


# ---------------------------------------------------------------------------
# Blocker 2: pending proposals are indexed and searchable (Issue #1)
# ---------------------------------------------------------------------------


def test_distill_session_proposal_is_searchable_via_store(store: DMCStore) -> None:
    """Proposals written by distill_session must be findable via search."""
    from dmc.retriever import search
    from dmc.schemas import SearchRequest

    session_id = seed_mixed_session(store)
    result = distill_session(session_id, store)

    # Proposals must use dmc:// URIs (indexed in FTS)
    assert result.proposal_uris
    assert all(uri.startswith("dmc://proposal/") for uri in result.proposal_uris)

    # Each proposal must be readable via read_object
    for uri in result.proposal_uris:
        data = store.read_object(uri)
        assert data.get("status") == "pending"

    # search(scopes=["proposals"]) must find at least one distilled proposal
    req = SearchRequest(query="wrong turn", scopes=["proposals"])
    hits = search(req, store)
    assert hits, "distilled proposals must be findable via search(scopes=['proposals'])"
    hit_uris = {h.uri for h in hits}
    assert hit_uris & set(result.proposal_uris), (
        "at least one proposal URI from distill_session must appear in search results"
    )

    # No files written under .dmc/skills
    skill_files = [p for p in (store.dmc_dir / "skills").rglob("*") if p.is_file()]
    assert skill_files == []


# ---------------------------------------------------------------------------
# Blocker 1: end-to-end record → distill → precheck loop (Issue #1)
# ---------------------------------------------------------------------------


def test_record_distill_precheck_loop_fires_failure_mode_rule(
    store: DMCStore,
) -> None:
    """Core loop: record a regression, distill, then precheck a similar action.

    After distill_session writes failure_mode objects under objects/failure_mode/,
    precheck must load them and fire RULE_FAILURE_MODE (failure-mode-resemblance)
    when the proposed action matches the stored failure mode's trigger.
    """
    from dmc.precheck import RULE_FAILURE_MODE, precheck
    from dmc.schemas import PrecheckRequest

    session_id = "sess-loop-test"

    # 1. Record a failure event with a distinctive trigger phrase
    record_event(
        make_event(
            "loop-e1",
            session_id,
            phase="benchmark",
            kind="benchmark_run",
            outcome="regressed: tiling_factor too large",
            intent="benchmark loop with large tile",
        ),
        store,
    )

    # 2. Distill the session — writes objects/failure_mode/<id>.yaml
    result = distill_session(session_id, store)
    assert result.failure_modes, "session with a regression must produce failure modes"
    failure_mode_dir = store.objects_dir / "failure_mode"
    assert failure_mode_dir.exists(), "distiller must write to objects/failure_mode/"

    # 3. Run precheck on an action that resembles the stored failure mode
    trigger_text = result.failure_modes[0].trigger
    req = PrecheckRequest(
        action=f"benchmark_run with {trigger_text}",
        intent=f"repeat benchmark: {trigger_text}",
    )
    check = precheck(req, store)

    assert RULE_FAILURE_MODE in check.matched_rules, (
        "precheck must fire failure-mode-resemblance after distill wrote "
        "the failure mode to objects/failure_mode/"
    )
