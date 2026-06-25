"""Tests for src/dmc/renderer.py (M04_RENDERER).

Positive and negative coverage for Mermaid rendering, Markdown plan rendering,
Markdown briefing rendering, file output, and determinism. Plan graphs are
built with the deterministic planner (``plan_task``) and with hand-built
``PlanGraph`` objects to exercise specific gate visibility.
"""

from __future__ import annotations

import pytest

from dmc.planner import next_ready_nodes, plan_task
from dmc.renderer import (
    render_briefing,
    render_plan_markdown,
    render_plan_mermaid,
    write_rendered,
)
from dmc.schemas import PlanGraph, PlanNode, SearchResult, TaskRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task() -> TaskRequest:
    return TaskRequest(
        id="task_demo",
        task="make the widget fast",
        repo="dmc",
        current_phase="edit",
        hardware=["gpu_a"],
        constraints=["no network"],
    )


def _node(
    node_id: str,
    type_: str = "edit",
    deps: list[str] | None = None,
    *,
    goal: str = "do the thing",
    success_criteria: list[str] | None = None,
    human_review_required: bool = False,
    evidence_contract: dict | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        type=type_,
        goal=goal,
        dependencies=deps or [],
        success_criteria=success_criteria or ["done"],
        evidence_contract=(
            evidence_contract
            if evidence_contract is not None
            else {"required": True, "kinds": ["note"]}
        ),
        human_review={"required": human_review_required},
    )


def _graph(nodes: list[PlanNode]) -> PlanGraph:
    return PlanGraph(id="plan_demo", task=_task(), nodes=nodes)


# ---------------------------------------------------------------------------
# render_plan_mermaid
# ---------------------------------------------------------------------------


def test_mermaid_starts_with_flowchart_td():
    graph = plan_task(_task())
    out = render_plan_mermaid(graph)
    assert out.startswith("flowchart TD")


def test_mermaid_starts_with_valid_direction():
    graph = plan_task(_task())
    first = render_plan_mermaid(graph).splitlines()[0].strip()
    assert first in {"flowchart TD", "flowchart LR"}


def test_mermaid_contains_every_node_id_and_type():
    graph = plan_task(_task())
    out = render_plan_mermaid(graph)
    for node in graph.nodes:
        assert node.id in out
        # The label carries "<id> (<type>)".
        assert f"{node.id} ({node.type})" in out


def test_mermaid_has_one_edge_per_dependency():
    graph = plan_task(_task())
    out = render_plan_mermaid(graph)
    expected_edges = [
        f"{dep} --> {node.id}"
        for node in graph.nodes
        for dep in node.dependencies
    ]
    assert expected_edges  # the linear spine has dependencies
    for edge in expected_edges:
        assert edge in out
    # Exactly one edge line per dependency.
    edge_lines = [ln for ln in out.splitlines() if "-->" in ln]
    assert len(edge_lines) == len(expected_edges)


def test_mermaid_human_review_gate_visible():
    graph = _graph(
        [
            _node("a", "edit", human_review_required=False),
            _node("b", "review", deps=["a"], human_review_required=True),
        ]
    )
    out = render_plan_mermaid(graph)
    assert "human_review" in out


def test_mermaid_evidence_gate_visible():
    graph = _graph(
        [
            _node(
                "a",
                "edit",
                evidence_contract={"required": True, "kinds": ["note"]},
            )
        ]
    )
    out = render_plan_mermaid(graph)
    assert "evidence" in out


def test_mermaid_rejects_non_graph():
    with pytest.raises(TypeError):
        render_plan_mermaid("not a graph")  # type: ignore[arg-type]


def test_mermaid_label_sanitizes_brackets():
    graph = _graph([_node("a", "edit", goal="fix [array] bounds")])
    out = render_plan_mermaid(graph)
    # The raw "[array]" must not survive inside the label (would break Mermaid).
    assert "[array]" not in out
    assert "(array)" in out


# ---------------------------------------------------------------------------
# render_plan_markdown
# ---------------------------------------------------------------------------


def test_markdown_contains_each_node():
    graph = plan_task(_task())
    out = render_plan_markdown(graph)
    for node in graph.nodes:
        assert f"### {node.id} ({node.type})" in out
        assert node.goal in out


def test_markdown_shows_review_and_evidence_gates():
    graph = _graph(
        [
            _node(
                "a",
                "edit",
                human_review_required=False,
                evidence_contract={},
            ),
            _node(
                "b",
                "review",
                deps=["a"],
                human_review_required=True,
                evidence_contract={"required": True},
            ),
        ]
    )
    out = render_plan_markdown(graph)
    assert "Human review gate: yes" in out
    assert "Human review gate: no" in out
    assert "Evidence gate: yes" in out
    assert "Evidence gate: no" in out


def test_markdown_lists_success_criteria():
    graph = _graph(
        [_node("a", "test", success_criteria=["tests pass", "no regressions"])]
    )
    out = render_plan_markdown(graph)
    assert "tests pass" in out
    assert "no regressions" in out


def test_markdown_rejects_non_graph():
    with pytest.raises(TypeError):
        render_plan_markdown(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# render_briefing
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = (
    "## Selected workflows",
    "## Atoms",
    "## Knowledge refs",
    "## Pitfalls",
    "## Open questions",
    "## Next actions",
)


def test_briefing_has_all_six_sections_without_context():
    task = _task()
    graph = plan_task(task)
    out = render_briefing(task, graph)
    for section in _REQUIRED_SECTIONS:
        assert section in out


def test_briefing_has_all_six_sections_with_context():
    task = _task()
    graph = plan_task(task)
    context = [
        SearchResult(
            uri="knowledge://repo/widget",
            score=0.9,
            kind="knowledge",
            title="Widget overview",
        ),
        SearchResult(
            uri="failure_mode://slow-loop",
            score=0.8,
            kind="failure_mode",
            title="Slow inner loop pitfall",
        ),
    ]
    out = render_briefing(task, graph, context)
    for section in _REQUIRED_SECTIONS:
        assert section in out
    # Knowledge ref routed to knowledge section.
    assert "knowledge://repo/widget" in out
    # Failure-mode routed to pitfalls section.
    assert "failure_mode://slow-loop" in out


def test_briefing_empty_sections_have_placeholders():
    task = _task()
    graph = plan_task(task)
    out = render_briefing(task, graph, context=[])
    assert "(no knowledge refs)" in out
    assert "(no known pitfalls)" in out


def test_briefing_pitfall_classified_by_snippet_hint():
    task = _task()
    graph = plan_task(task)
    context = [
        SearchResult(
            uri="knowledge://note/x",
            score=0.5,
            kind="knowledge",
            snippet="A known pitfall to avoid when editing",
        )
    ]
    out = render_briefing(task, graph, context)
    pitfalls_part = out.split("## Pitfalls", 1)[1].split("## Open questions", 1)[0]
    assert "knowledge://note/x" in pitfalls_part


def test_briefing_next_actions_reflect_plan_graph():
    task = _task()
    graph = plan_task(task)
    out = render_briefing(task, graph)
    ready = next_ready_nodes(graph, set())
    assert ready  # the spine has a first node
    next_part = out.split("## Next actions", 1)[1]
    for node in ready:
        assert node.id in next_part


def test_briefing_open_questions_rendered():
    task = TaskRequest(
        id="task_q",
        task="investigate",
        open_questions=["is the cache coherent?"],
    )
    graph = plan_task(task)
    out = render_briefing(task, graph)
    assert "is the cache coherent?" in out


def test_briefing_rejects_non_task():
    graph = plan_task(_task())
    with pytest.raises(TypeError):
        render_briefing("nope", graph)  # type: ignore[arg-type]


def test_briefing_rejects_non_graph():
    with pytest.raises(TypeError):
        render_briefing(_task(), "nope")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# write_rendered
# ---------------------------------------------------------------------------


def test_write_rendered_writes_exact_content(tmp_path):
    target = tmp_path / "out.md"
    text = "# Title\n\nbody line\n"
    write_rendered(text, target)
    assert target.read_text(encoding="utf-8") == text


def test_write_rendered_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "graph.mmd"
    text = "flowchart TD\n    a[\"a (edit)\"]\n"
    write_rendered(text, target)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == text


def test_write_rendered_overwrites(tmp_path):
    target = tmp_path / "out.txt"
    write_rendered("first", target)
    write_rendered("second", target)
    assert target.read_text(encoding="utf-8") == "second"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_mermaid_is_deterministic():
    graph = plan_task(_task())
    assert render_plan_mermaid(graph) == render_plan_mermaid(graph)


def test_markdown_is_deterministic():
    graph = plan_task(_task())
    assert render_plan_markdown(graph) == render_plan_markdown(graph)


def test_briefing_is_deterministic():
    task = _task()
    graph = plan_task(task)
    context = [
        SearchResult(uri="knowledge://a", score=0.1, kind="knowledge"),
        SearchResult(uri="failure_mode://b", score=0.2, kind="failure_mode"),
    ]
    assert render_briefing(task, graph, context) == render_briefing(
        task, graph, context
    )
