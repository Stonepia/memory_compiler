"""Tests for M05_RETRIEVER — local retrieval over DMC objects."""

from __future__ import annotations

import math

import pytest

from dmc.retriever import (
    CHARS_PER_TOKEN,
    build_context_pack,
    rank_results,
    search,
)
from dmc.schemas import KnowledgeRef, SearchRequest, SearchResult
from dmc.store import DMCStore


# ---------------------------------------------------------------------------
# Fixtures / seeding helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_store(tmp_path) -> DMCStore:
    """A real DMCStore seeded with objects across several scopes."""
    store = DMCStore(tmp_path)
    store.initialize()

    # Skill (tier-1 workflow shape).
    store.write_object(
        "skills",
        "bmg_occupancy_workflow",
        {
            "id": "bmg_occupancy_workflow",
            "tier": 1,
            "title": "Investigate low BMG occupancy",
            "summary": "Workflow for diagnosing low occupancy on BMG kernels",
            "tags": ["bmg", "occupancy", "perf"],
        },
    )

    # Knowledge ref WITH provenance.
    store.write_knowledge(
        KnowledgeRef(
            id="bmg_hw_spec",
            kind="hw",
            uri="https://example.com/bmg",
            summary="BMG hardware occupancy characteristics",
            tags=["bmg", "hardware"],
            provenance=[{"source": "https://example.com/bmg-spec"}],
        )
    )

    # Episode.
    store.write_object(
        "episodes",
        "ep_occupancy_fix",
        {
            "id": "ep_occupancy_fix",
            "summary": "Fixed occupancy regression by tiling the loop",
            "outcome": "success",
            "tags": ["occupancy"],
        },
    )

    # Failure mode.
    store.write_object(
        "failure_modes",
        "fm_oversized_tile",
        {
            "id": "fm_oversized_tile",
            "trigger": "oversized tile reduces occupancy",
            "description": "Choosing too large a tile drops BMG occupancy",
            "tags": ["occupancy", "tile"],
        },
    )

    return store


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_returns_hits_across_scopes(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=list())  # all scopes
    results = search(req, seeded_store)
    assert results, "expected at least one hit for 'occupancy'"
    assert all(isinstance(r, SearchResult) for r in results)
    kinds = {r.kind for r in results}
    # occupancy appears in several scopes.
    assert {"skills", "episodes", "failure_modes"} & kinds


def test_search_respects_scope_filter(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=["skills"])
    results = search(req, seeded_store)
    assert results
    assert all(r.kind == "skills" for r in results)
    # Other scopes must be excluded.
    uris = {r.uri for r in results}
    assert "dmc://episodes/ep_occupancy_fix" not in uris


def test_search_respects_limit(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=[], limit=1)
    results = search(req, seeded_store)
    assert len(results) <= 1


def test_search_preserves_provenance_when_present(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="bmg", scopes=["knowledge"])
    results = search(req, seeded_store)
    assert results
    hit = next(r for r in results if r.uri == "dmc://knowledge/bmg_hw_spec")
    prov = getattr(hit, "provenance", None)
    assert prov, "knowledge ref provenance should be attached"
    assert prov[0]["source"] == "https://example.com/bmg-spec"


def test_search_no_provenance_when_source_lacks_it(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=["episodes"])
    results = search(req, seeded_store)
    assert results
    hit = results[0]
    assert getattr(hit, "provenance", None) is None


def test_search_empty_query_returns_empty(seeded_store: DMCStore) -> None:
    assert search(SearchRequest(query="   ", scopes=["skills"]), seeded_store) == []


def test_search_unknown_scope_handled_gracefully(seeded_store: DMCStore) -> None:
    # Unknown scope only -> empty, no crash.
    assert search(SearchRequest(query="occupancy", scopes=["bogus"]), seeded_store) == []
    # Mixed: unknown scope ignored, known scope still works.
    mixed = search(
        SearchRequest(query="occupancy", scopes=["bogus", "skills"]), seeded_store
    )
    assert mixed and all(r.kind == "skills" for r in mixed)


def test_search_no_match_returns_empty(seeded_store: DMCStore) -> None:
    results = search(
        SearchRequest(query="nonexistentxyz", scopes=["skills"]), seeded_store
    )
    assert results == []


def test_search_with_filters_narrows(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=[])
    req.filters = {"kind": "failure_modes"}  # extra field (extra="allow")
    results = search(req, seeded_store)
    assert results
    assert all(r.kind == "failure_modes" for r in results)


# ---------------------------------------------------------------------------
# rank_results
# ---------------------------------------------------------------------------


def test_rank_exact_id_outranks_weak_text_match() -> None:
    exact = SearchResult(
        uri="dmc://skills/tiling", score=0.1, kind="skills", title="some title"
    )
    weak = SearchResult(
        uri="dmc://skills/other",
        score=5.0,
        kind="skills",
        snippet="mentions tiling once",
    )
    ranked = rank_results("tiling", [weak, exact])
    assert ranked[0].uri == "dmc://skills/tiling"
    assert ranked[0].reason and "exact id/path match" in ranked[0].reason


def test_rank_every_result_has_reason() -> None:
    candidates = [
        SearchResult(uri="dmc://skills/a", score=1.0, kind="skills", title="alpha"),
        SearchResult(uri="dmc://knowledge/b", score=2.0, kind="knowledge"),
    ]
    ranked = rank_results("alpha", candidates)
    assert all(r.reason for r in ranked)


def test_rank_scope_match_boosts() -> None:
    # Query mentions the kind "skills"; the skills result should outrank the
    # knowledge result that has no overlap at all.
    skill = SearchResult(uri="dmc://skills/x", score=0.0, kind="skills")
    knowledge = SearchResult(uri="dmc://knowledge/y", score=0.0, kind="knowledge")
    ranked = rank_results("skills", [knowledge, skill])
    assert ranked[0].uri == "dmc://skills/x"


def test_rank_deterministic_tie_break_on_uri() -> None:
    # Identical scoring signals -> deterministic order by uri ascending.
    a = SearchResult(uri="dmc://skills/zzz", score=1.0, kind="skills")
    b = SearchResult(uri="dmc://skills/aaa", score=1.0, kind="skills")
    ranked = rank_results("nomatchquery", [a, b])
    assert [r.uri for r in ranked] == ["dmc://skills/aaa", "dmc://skills/zzz"]
    # Stable across repeated calls.
    again = rank_results("nomatchquery", [a, b])
    assert [r.uri for r in again] == [r.uri for r in ranked]


def test_rank_preserves_provenance() -> None:
    prov = [{"source": "https://example.com/x"}]
    c = SearchResult(
        uri="dmc://knowledge/k", score=1.0, kind="knowledge", provenance=prov
    )
    ranked = rank_results("k", [c])
    assert getattr(ranked[0], "provenance", None) == prov


# ---------------------------------------------------------------------------
# build_context_pack
# ---------------------------------------------------------------------------


def _estimate(text: str) -> int:
    return 0 if not text else math.ceil(len(text) / CHARS_PER_TOKEN)


def test_context_pack_is_markdown_within_budget() -> None:
    results = [
        SearchResult(
            uri="dmc://skills/a",
            score=1.0,
            kind="skills",
            title="Alpha",
            reason="exact id/path match",
        )
    ]
    pack = build_context_pack(results, budget_tokens=200)
    assert pack.startswith("# Context Pack")
    assert "dmc://skills/a" in pack
    assert _estimate(pack) <= 200


def test_context_pack_truncates_and_flags_over_budget() -> None:
    results = [
        SearchResult(
            uri=f"dmc://skills/item_{i}",
            score=float(i),
            kind="skills",
            title=f"Item number {i} with a fairly long descriptive title",
            reason="text match: item",
            snippet="a reasonably long snippet of body text to consume budget",
        )
        for i in range(20)
    ]
    budget = 60
    pack = build_context_pack(results, budget_tokens=budget)
    assert _estimate(pack) <= budget
    assert "truncated" in pack.lower()
    # Not every item could fit.
    assert pack.count("## ") < len(results)


def test_context_pack_empty_results_placeholder() -> None:
    pack = build_context_pack([], budget_tokens=50)
    assert pack.startswith("# Context Pack")
    assert "No results" in pack
    assert _estimate(pack) <= 50


# ---------------------------------------------------------------------------
# Blocker 1: distilled objects searchable through plural scope names (Issue #1)
# ---------------------------------------------------------------------------


@pytest.fixture()
def distilled_store(tmp_path):
    """A store seeded with M08-distiller-style objects (singular kind)."""
    from dmc.distiller import distill_session
    from dmc.recorder import record_event
    from dmc.schemas import TraceAction, TraceEvent, TraceObservation

    store = DMCStore(tmp_path)
    store.initialize()

    session_id = "test-distilled-scope"
    for ev_id, phase, outcome, intent in [
        ("d1", "test", "success", "run unit tests"),
        ("d2", "validate", "passed", "validate fix"),
        ("d3", "benchmark", "regressed: oversized tile", "benchmark hot loop"),
    ]:
        record_event(
            TraceEvent(
                event_id=ev_id,
                session_id=session_id,
                phase=phase,
                actor="agent",
                intent=intent,
                action=TraceAction(kind="test_run"),
                observation=TraceObservation(outcome=outcome),
                timestamp="2026-06-25T00:00:00Z",
                provenance=[{"source": f"session://{session_id}"}],
            ),
            store,
        )
    distill_session(session_id, store)
    return store


def test_search_episodes_scope_finds_distilled_episode(distilled_store: DMCStore) -> None:
    req = SearchRequest(query="session", scopes=["episodes"])
    results = search(req, distilled_store)
    assert results, "search(scopes=['episodes']) must find M08-distilled episode objects"
    kinds = {r.kind for r in results}
    assert "episode" in kinds


def test_search_failure_modes_scope_finds_distilled_failure_mode(
    distilled_store: DMCStore,
) -> None:
    req = SearchRequest(query="oversized tile", scopes=["failure_modes"])
    results = search(req, distilled_store)
    assert results, "search(scopes=['failure_modes']) must find M08-distilled failure modes"
    kinds = {r.kind for r in results}
    assert "failure_mode" in kinds


def test_search_eval_cases_scope_finds_distilled_eval_case(
    distilled_store: DMCStore,
) -> None:
    req = SearchRequest(query="session", scopes=["eval_cases"])
    results = search(req, distilled_store)
    assert results, "search(scopes=['eval_cases']) must find M08-distilled eval cases"
    kinds = {r.kind for r in results}
    assert "eval_case" in kinds


# ---------------------------------------------------------------------------
# Blocker 3: SearchRequest schema fields (Issue #1)
# ---------------------------------------------------------------------------


def test_search_request_schema_has_filters_and_budget_tokens() -> None:
    schema = SearchRequest.model_json_schema()
    props = schema.get("properties", {})
    assert "filters" in props, "SearchRequest schema must include 'filters'"
    assert "budget_tokens" in props, "SearchRequest schema must include 'budget_tokens'"


def test_search_request_filters_first_class(seeded_store: DMCStore) -> None:
    """filters is now a first-class field, not just an extra field."""
    req = SearchRequest(query="occupancy", scopes=[], filters={"kind": "failure_modes"})
    results = search(req, seeded_store)
    assert results
    assert all(r.kind == "failure_modes" for r in results)


def test_search_request_budget_tokens_field(seeded_store: DMCStore) -> None:
    req = SearchRequest(query="occupancy", scopes=[], budget_tokens=500)
    # budget_tokens is accessible as a typed field
    assert req.budget_tokens == 500
    # search still works
    results = search(req, seeded_store)
    assert isinstance(results, list)


def test_context_pack_deterministic() -> None:
    results = [
        SearchResult(uri="dmc://skills/a", score=1.0, kind="skills", title="A"),
        SearchResult(uri="dmc://skills/b", score=2.0, kind="skills", title="B"),
    ]
    first = build_context_pack(results, budget_tokens=300)
    second = build_context_pack(results, budget_tokens=300)
    assert first == second


def test_context_pack_zero_budget_is_empty() -> None:
    results = [SearchResult(uri="dmc://skills/a", score=1.0, kind="skills")]
    assert build_context_pack(results, budget_tokens=0) == ""


def test_context_pack_includes_provenance() -> None:
    results = [
        SearchResult(
            uri="dmc://knowledge/k",
            score=1.0,
            kind="knowledge",
            title="Knowledge",
            reason="exact match",
            provenance=[{"source": "https://example.com/spec"}],
        )
    ]
    pack = build_context_pack(results, budget_tokens=300)
    assert "https://example.com/spec" in pack


# ---------------------------------------------------------------------------
# end-to-end
# ---------------------------------------------------------------------------


def test_search_then_build_context_pack(seeded_store: DMCStore) -> None:
    results = search(SearchRequest(query="occupancy", scopes=[]), seeded_store)
    pack = build_context_pack(results, budget_tokens=500)
    assert pack.startswith("# Context Pack")
    assert _estimate(pack) <= 500
    # Ranked results each explain themselves.
    assert all(r.reason for r in results)
