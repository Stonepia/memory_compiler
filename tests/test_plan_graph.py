"""Tests for src/dmc/planner.py (M03_PLAN_GRAPH).

Positive and negative coverage for plan graph validation, ordering, readiness,
template-based planning, and YAML/JSON round-trip persistence.

Deliberately-broken graphs are built with ``model_construct`` so they bypass
the strict ``PlanGraph``/``PlanNode`` constructors (which already reject some
invalid shapes) and reach ``validate_plan_graph`` directly.
"""

from __future__ import annotations

import pytest

from dmc.planner import (
    PLAN_NODE_TYPES,
    load_plan_graph,
    next_ready_nodes,
    plan_task,
    save_plan_graph,
    topological_nodes,
    validate_plan_graph,
)
from dmc.schemas import PlanGraph, PlanNode, TaskRequest
from dmc.store import DMCValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task() -> TaskRequest:
    return TaskRequest(id="task_demo", task="demo task")


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
        evidence_contract=evidence_contract if evidence_contract is not None else {},
        human_review={"required": human_review_required},
    )


def _graph(nodes: list[PlanNode]) -> PlanGraph:
    return PlanGraph(id="plan_demo", task=_task(), nodes=nodes)


def _unsafe_graph(nodes: list[PlanNode]) -> PlanGraph:
    """Build a graph bypassing graph-level validation (for negative tests)."""
    return PlanGraph.model_construct(id="plan_demo", task=_task(), nodes=nodes)


# ---------------------------------------------------------------------------
# validate_plan_graph — positive
# ---------------------------------------------------------------------------


def test_validate_accepts_well_formed_graph() -> None:
    graph = _graph(
        [
            _node("a", "brief"),
            _node("b", "edit", deps=["a"]),
            _node("c", "review", deps=["b"], human_review_required=True),
        ]
    )
    report = validate_plan_graph(graph)
    assert report.ok is True
    assert report.valid is True
    assert report.errors == []


def test_validate_accepts_plan_task_output() -> None:
    report = validate_plan_graph(plan_task(_task()))
    assert report.ok is True
    assert report.errors == []


def test_validate_requires_plangraph_instance() -> None:
    with pytest.raises(DMCValidationError):
        validate_plan_graph({"id": "x"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_plan_graph — negative
# ---------------------------------------------------------------------------


def test_validate_rejects_duplicate_node_ids() -> None:
    graph = _unsafe_graph([_node("a", "brief"), _node("a", "edit")])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("duplicate node id" in e for e in report.errors)


def test_validate_rejects_dangling_dependency() -> None:
    graph = _unsafe_graph([_node("a", "edit", deps=["ghost"])])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("unknown node" in e for e in report.errors)


def test_validate_rejects_cycle() -> None:
    # a -> b -> a : both deps reference existing nodes, no self-edge, so the
    # PlanGraph constructor accepts it, but it is a genuine cycle.
    graph = _graph(
        [
            _node("a", "edit", deps=["b"]),
            _node("b", "test", deps=["a"]),
        ]
    )
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("cycle" in e for e in report.errors)


def test_validate_rejects_self_dependency() -> None:
    node = _node("a", "edit")
    node.dependencies = ["a"]
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("depends on itself" in e for e in report.errors)


def test_validate_rejects_empty_goal() -> None:
    node = _node("a", "edit")
    node.goal = "   "
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("empty goal" in e for e in report.errors)


def test_validate_rejects_empty_success_criteria() -> None:
    node = _node("a", "edit")
    node.success_criteria = []
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("success_criteria must be non-empty" in e for e in report.errors)


def test_validate_rejects_invalid_node_type() -> None:
    node = _node("a", "edit")
    node.type = "frobnicate"  # bypasses Literal via attribute set
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("invalid type" in e for e in report.errors)


def test_validate_rejects_non_object_evidence_contract() -> None:
    node = _node("a", "edit")
    node.evidence_contract = ["not", "a", "mapping"]  # type: ignore[assignment]
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("evidence_contract must be an object" in e for e in report.errors)


def test_validate_rejects_missing_human_review() -> None:
    node = _node("a", "edit")
    node.human_review = {}
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("explicit boolean 'required'" in e for e in report.errors)


def test_validate_rejects_non_boolean_human_review() -> None:
    node = _node("a", "edit")
    node.human_review = {"required": "yes"}
    graph = _unsafe_graph([node])
    report = validate_plan_graph(graph)
    assert report.ok is False
    assert any("must be a boolean" in e for e in report.errors)


# ---------------------------------------------------------------------------
# topological_nodes
# ---------------------------------------------------------------------------


def test_topological_order_for_dag() -> None:
    graph = _graph(
        [
            _node("c", "review", deps=["b"]),
            _node("a", "brief"),
            _node("b", "edit", deps=["a"]),
        ]
    )
    order = [n.id for n in topological_nodes(graph)]
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_is_deterministic_for_independent_nodes() -> None:
    graph = _graph(
        [
            _node("first", "brief"),
            _node("second", "inspect"),
        ]
    )
    # Two independent roots: tie broken by original position -> stable order.
    assert [n.id for n in topological_nodes(graph)] == ["first", "second"]
    assert [n.id for n in topological_nodes(graph)] == ["first", "second"]


def test_topological_order_matches_dependencies() -> None:
    graph = plan_task(_task())
    order = [n.id for n in topological_nodes(graph)]
    by_index = {nid: i for i, nid in enumerate(order)}
    for node in graph.nodes:
        for dep in node.dependencies:
            assert by_index[dep] < by_index[node.id]


def test_topological_raises_on_cycle() -> None:
    graph = _graph(
        [
            _node("a", "edit", deps=["b"]),
            _node("b", "test", deps=["a"]),
        ]
    )
    with pytest.raises(DMCValidationError):
        topological_nodes(graph)


# ---------------------------------------------------------------------------
# next_ready_nodes
# ---------------------------------------------------------------------------


def test_next_ready_empty_completed_returns_roots() -> None:
    graph = _graph(
        [
            _node("a", "brief"),
            _node("b", "edit", deps=["a"]),
            _node("c", "test", deps=["b"]),
        ]
    )
    assert [n.id for n in next_ready_nodes(graph, set())] == ["a"]


def test_next_ready_partial_completed() -> None:
    graph = _graph(
        [
            _node("a", "brief"),
            _node("b", "edit", deps=["a"]),
            _node("c", "test", deps=["a"]),
        ]
    )
    ready = [n.id for n in next_ready_nodes(graph, {"a"})]
    assert ready == ["b", "c"]


def test_next_ready_excludes_completed() -> None:
    graph = _graph(
        [
            _node("a", "brief"),
            _node("b", "edit", deps=["a"]),
        ]
    )
    ready = [n.id for n in next_ready_nodes(graph, {"a", "b"})]
    assert ready == []


def test_next_ready_full_completed_is_empty() -> None:
    graph = plan_task(_task())
    all_ids = {n.id for n in graph.nodes}
    assert next_ready_nodes(graph, all_ids) == []


def test_next_ready_multiple_dependencies() -> None:
    graph = _graph(
        [
            _node("a", "brief"),
            _node("b", "inspect"),
            _node("c", "edit", deps=["a", "b"]),
        ]
    )
    assert [n.id for n in next_ready_nodes(graph, {"a"})] == ["b"]
    assert [n.id for n in next_ready_nodes(graph, {"a", "b"})] == ["c"]


# ---------------------------------------------------------------------------
# plan_task
# ---------------------------------------------------------------------------


def test_plan_task_is_valid_and_uses_allowed_types() -> None:
    graph = plan_task(_task())
    assert validate_plan_graph(graph).ok is True
    assert graph.id == "plan_task_demo"
    for node in graph.nodes:
        assert node.type in PLAN_NODE_TYPES
        assert node.goal.strip()
        assert node.success_criteria
        assert isinstance(node.human_review.get("required"), bool)


def test_plan_task_is_deterministic() -> None:
    a = plan_task(_task())
    b = plan_task(_task())
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_plan_task_has_linear_spine() -> None:
    graph = plan_task(_task())
    ids = [n.id for n in graph.nodes]
    assert ids == [
        "brief",
        "inspect",
        "plan",
        "edit",
        "test",
        "review",
        "decide",
        "distill",
    ]


def test_plan_task_rejects_non_task_request() -> None:
    with pytest.raises(DMCValidationError):
        plan_task({"id": "x", "task": "y"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# save_plan_graph / load_plan_graph round-trip
# ---------------------------------------------------------------------------


def test_yaml_round_trip(tmp_path) -> None:
    graph = plan_task(_task())
    path = tmp_path / "plan.yaml"
    save_plan_graph(graph, path)
    loaded = load_plan_graph(path)
    assert loaded.model_dump(mode="json") == graph.model_dump(mode="json")
    assert validate_plan_graph(loaded).ok is True


def test_json_round_trip(tmp_path) -> None:
    graph = plan_task(_task())
    path = tmp_path / "plan.json"
    save_plan_graph(graph, path)
    loaded = load_plan_graph(path)
    assert loaded.model_dump(mode="json") == graph.model_dump(mode="json")


def test_save_creates_parent_dirs(tmp_path) -> None:
    graph = plan_task(_task())
    path = tmp_path / "nested" / "dir" / "plan.yaml"
    save_plan_graph(graph, path)
    assert path.exists()


def test_load_missing_file_raises(tmp_path) -> None:
    with pytest.raises(DMCValidationError):
        load_plan_graph(tmp_path / "nope.yaml")


def test_load_non_mapping_raises(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(DMCValidationError):
        load_plan_graph(path)


def test_save_requires_plangraph() -> None:
    with pytest.raises(DMCValidationError):
        save_plan_graph({"id": "x"}, "out.yaml")  # type: ignore[arg-type]
