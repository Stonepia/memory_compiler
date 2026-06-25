"""Deterministic PlanGraph logic (M03_PLAN_GRAPH).

This module creates, validates, orders, and persists :class:`PlanGraph`
objects. Everything here is deterministic, rule/template-based, and offline:

* **No LLM.** Planning is a fixed template over a :class:`TaskRequest`.
* **No execution.** Plan nodes are never run; this module only reasons about
  the graph (validity, topological order, readiness).
* **No orchestrator.** There is no scheduler, runtime, or side-effecting loop.

Data shapes are owned by ``src/dmc/schemas.py`` (the single contract module).
This module imports :class:`PlanGraph`, :class:`PlanNode`,
:class:`TaskRequest`, and :class:`ValidationReport`; it does not redefine them.

Public API
----------

``validate_plan_graph(graph) -> ValidationReport``
    Collect (never raise) every structural problem in a graph.
``topological_nodes(graph) -> list[PlanNode]``
    Deterministic dependency order for an acyclic graph (raises on a cycle).
``next_ready_nodes(graph, completed_node_ids) -> list[PlanNode]``
    Nodes whose dependencies are all completed and which are not themselves
    completed, in deterministic order.
``plan_task(request, store=None) -> PlanGraph``
    Build a deterministic, always-valid PlanGraph from a task request.
``save_plan_graph(graph, path) -> None`` / ``load_plan_graph(path) -> PlanGraph``
    YAML/JSON round-trip persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from dmc.schemas import (
    PlanGraph,
    PlanNode,
    TaskRequest,
    ValidationReport,
)
from dmc.store import DMCStore, DMCValidationError

__all__ = [
    "PLAN_NODE_TYPES",
    "validate_plan_graph",
    "topological_nodes",
    "next_ready_nodes",
    "plan_task",
    "save_plan_graph",
    "load_plan_graph",
]

#: The exact set of node types a PlanGraph may use (card lines 52-56). Mirrors
#: ``PlanNodeType`` in ``schemas.py`` and ``templates/plan_graph.schema.json``.
PLAN_NODE_TYPES: frozenset[str] = frozenset(
    {
        "brief",
        "inspect",
        "plan",
        "edit",
        "test",
        "benchmark",
        "profile",
        "review",
        "decide",
        "distill",
    }
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_plan_graph(graph: PlanGraph) -> ValidationReport:
    """Validate a :class:`PlanGraph`, collecting every problem (never raising).

    Enforces (see ``modules/M03_PLAN_GRAPH.md`` lines 60-67):

    * no duplicate node IDs
    * all dependencies reference existing nodes (and no self-dependency)
    * the graph has no cycles
    * required node fields are non-empty (``id``, ``type``, ``goal``,
      ``success_criteria``)
    * node ``type`` is one of :data:`PLAN_NODE_TYPES`
    * ``evidence_contract`` is a valid schema object (a mapping)
    * ``human_review`` is explicit: a mapping carrying a boolean ``required``

    The returned :class:`ValidationReport` has ``ok == False`` whenever any
    error was collected. ``warnings`` is reserved for non-fatal observations.
    """
    if not isinstance(graph, PlanGraph):  # defensive: API misuse
        raise DMCValidationError("validate_plan_graph requires a PlanGraph instance")

    errors: list[str] = []
    warnings: list[str] = []

    nodes = list(graph.nodes)

    # --- duplicate node IDs -------------------------------------------------
    seen: set[str] = set()
    duplicates: set[str] = set()
    for node in nodes:
        if node.id in seen:
            duplicates.add(node.id)
        seen.add(node.id)
    for dup in sorted(duplicates):
        errors.append(f"duplicate node id: {dup!r}")

    known_ids = set(seen)

    # --- per-node field + reference checks ---------------------------------
    for node in nodes:
        loc = f"node {node.id!r}"

        if not node.id:
            errors.append("a node has an empty id")
        if not node.type:
            errors.append(f"{loc}: empty type")
        elif node.type not in PLAN_NODE_TYPES:
            errors.append(
                f"{loc}: invalid type {node.type!r}; "
                f"allowed types are {sorted(PLAN_NODE_TYPES)}"
            )
        if not (node.goal and node.goal.strip()):
            errors.append(f"{loc}: empty goal")
        if not node.success_criteria:
            errors.append(f"{loc}: success_criteria must be non-empty")
        elif any(not (c and str(c).strip()) for c in node.success_criteria):
            errors.append(f"{loc}: success_criteria contains an empty entry")

        # dependencies must exist and may not be self-referential
        for dep in node.dependencies:
            if dep == node.id:
                errors.append(f"{loc}: node depends on itself")
            elif dep not in known_ids:
                errors.append(f"{loc}: depends on unknown node {dep!r}")

        # evidence gates must be valid schema objects (mappings)
        if not isinstance(node.evidence_contract, dict):
            errors.append(
                f"{loc}: evidence_contract must be an object/mapping, "
                f"got {type(node.evidence_contract).__name__}"
            )

        # human_review must be explicit true/false
        hr = node.human_review
        if not isinstance(hr, dict):
            errors.append(
                f"{loc}: human_review must be an object carrying an explicit "
                f"boolean 'required', got {type(hr).__name__}"
            )
        elif "required" not in hr:
            errors.append(
                f"{loc}: human_review must set an explicit boolean 'required'"
            )
        elif not isinstance(hr["required"], bool):
            errors.append(
                f"{loc}: human_review.required must be a boolean true/false, "
                f"got {type(hr['required']).__name__}"
            )

    # --- cycles -------------------------------------------------------------
    # Only meaningful when dependency references are otherwise sane; restrict
    # the adjacency to known ids so a dangling dep is reported once (above) and
    # does not also masquerade as a cycle.
    if _has_cycle(nodes, known_ids):
        errors.append("graph has a cycle (dependencies are not acyclic)")

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)


def _has_cycle(nodes: list[PlanNode], known_ids: set[str]) -> bool:
    """Return True if the dependency graph over ``nodes`` contains a cycle."""
    adjacency: dict[str, list[str]] = {}
    for node in nodes:
        # Keep only real, non-self edges to existing nodes.
        adjacency.setdefault(node.id, [])
        for dep in node.dependencies:
            if dep in known_ids and dep != node.id:
                adjacency[node.id].append(dep)

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in done:
            return False
        if node_id in visiting:
            return True
        visiting.add(node_id)
        for dep in adjacency.get(node_id, ()):
            if visit(dep):
                return True
        visiting.discard(node_id)
        done.add(node_id)
        return False

    return any(visit(node_id) for node_id in adjacency)


# ---------------------------------------------------------------------------
# Ordering and readiness
# ---------------------------------------------------------------------------


def topological_nodes(graph: PlanGraph) -> list[PlanNode]:
    """Return the graph's nodes in deterministic dependency order.

    Uses Kahn's algorithm. Ties (nodes that become ready at the same time) are
    broken by the node's original position in ``graph.nodes`` so the result is
    fully deterministic. Assumes the graph is acyclic; raises
    :class:`DMCValidationError` if a cycle is present (consistent with the
    ``ValidationReport`` produced by :func:`validate_plan_graph`).
    """
    nodes = list(graph.nodes)
    order_index = {node.id: i for i, node in enumerate(nodes)}
    by_id = {node.id: node for node in nodes}

    # Real dependency edges only (existing targets, no self-edges).
    deps_of: dict[str, set[str]] = {
        node.id: {
            d for d in node.dependencies if d in by_id and d != node.id
        }
        for node in nodes
    }

    resolved: set[str] = set()
    result: list[PlanNode] = []

    while len(result) < len(nodes):
        # Nodes whose dependencies are all resolved, in original order.
        ready = [
            node
            for node in nodes
            if node.id not in resolved
            and deps_of[node.id] <= resolved
        ]
        if not ready:
            unresolved = sorted(set(by_id) - resolved)
            raise DMCValidationError(
                "cannot compute topological order: graph has a cycle involving "
                f"nodes {unresolved}"
            )
        # Deterministic: take the lowest original-position ready node.
        ready.sort(key=lambda node: order_index[node.id])
        chosen = ready[0]
        result.append(chosen)
        resolved.add(chosen.id)

    return result


def next_ready_nodes(
    graph: PlanGraph, completed_node_ids: set[str]
) -> list[PlanNode]:
    """Return nodes ready to run given a set of completed node ids.

    A node is *ready* when it is not itself completed and every one of its
    (existing, non-self) dependencies is in ``completed_node_ids``. Results are
    ordered by the node's original position in ``graph.nodes`` for determinism.
    """
    completed = set(completed_node_ids or set())
    by_id = {node.id: node for node in graph.nodes}
    ready: list[PlanNode] = []
    for node in graph.nodes:
        if node.id in completed:
            continue
        deps = [d for d in node.dependencies if d in by_id and d != node.id]
        if all(d in completed for d in deps):
            ready.append(node)
    return ready


# ---------------------------------------------------------------------------
# Planning (deterministic template)
# ---------------------------------------------------------------------------

#: The fixed v0 plan template: ordered (type, id, goal, success_criteria,
#: human_review_required) tuples. Dependencies are the immediately preceding
#: node, forming a linear, acyclic spine that always validates.
_PLAN_TEMPLATE: tuple[tuple[str, str, str, list[str], bool], ...] = (
    (
        "brief",
        "brief",
        "Assemble a task briefing: goal, constraints, hardware, prior memory.",
        ["briefing names the goal, constraints, and relevant prior memory"],
        False,
    ),
    (
        "inspect",
        "inspect",
        "Inspect the repository and gather the context needed to plan.",
        ["relevant files, symbols, and tests are identified with evidence"],
        False,
    ),
    (
        "plan",
        "plan",
        "Produce a concrete, ordered plan of edits and checks.",
        ["a concrete ordered plan exists with success criteria per step"],
        False,
    ),
    (
        "edit",
        "edit",
        "Apply the planned code changes.",
        ["changes implement the plan and the project still imports/builds"],
        False,
    ),
    (
        "test",
        "test",
        "Run the relevant tests and capture their results as evidence.",
        ["tests run and their pass/fail outcome is recorded as evidence"],
        False,
    ),
    (
        "review",
        "review",
        "Review the diff and evidence for correctness and regressions.",
        ["a reviewer confirms the change is correct and complete"],
        True,
    ),
    (
        "decide",
        "decide",
        "Decide whether to accept, revise, or roll back the change.",
        ["an explicit accept/revise/rollback decision is recorded"],
        True,
    ),
    (
        "distill",
        "distill",
        "Distill the session into reusable memory (episode, pitfalls, evals).",
        ["durable memory objects are written with provenance"],
        False,
    ),
)


def plan_task(request: TaskRequest, store: DMCStore | None = None) -> PlanGraph:
    """Build a deterministic :class:`PlanGraph` from a :class:`TaskRequest`.

    The plan is a fixed, rule-based template (no LLM): a linear
    ``brief -> inspect -> plan -> edit -> test -> review -> decide -> distill``
    spine. Each node carries a non-empty goal, non-empty ``success_criteria``,
    an ``evidence_contract`` object, and an explicit ``human_review.required``
    boolean. The result is guaranteed to pass :func:`validate_plan_graph`.

    ``store`` is accepted for API compatibility and may be used by later
    versions to enrich planning with project state; it is optional and the
    plan is identical whether or not it is provided.
    """
    if not isinstance(request, TaskRequest):  # defensive: API misuse
        raise DMCValidationError("plan_task requires a TaskRequest instance")
    if store is not None and not isinstance(store, DMCStore):
        raise DMCValidationError("plan_task store must be a DMCStore or None")

    nodes: list[PlanNode] = []
    previous_id: str | None = None
    for node_type, node_id, goal, criteria, review_required in _PLAN_TEMPLATE:
        dependencies = [previous_id] if previous_id is not None else []
        nodes.append(
            PlanNode(
                id=node_id,
                type=node_type,
                goal=goal,
                dependencies=dependencies,
                success_criteria=list(criteria),
                agent={"role": "execution_agent"},
                context_refs=[],
                tools=[],
                inputs={},
                outputs={},
                evidence_contract={
                    "required": True,
                    "kinds": ["note"],
                },
                human_review={"required": review_required},
            )
        )
        previous_id = node_id

    graph = PlanGraph(id=f"plan_{request.id}", task=request, nodes=nodes)

    # A planner must never emit an invalid graph.
    report = validate_plan_graph(graph)
    if not report.ok:  # pragma: no cover - guards against template regressions
        raise DMCValidationError(
            "internal error: plan_task produced an invalid graph: "
            + "; ".join(report.errors)
        )
    return graph


# ---------------------------------------------------------------------------
# Persistence (YAML / JSON round-trip)
# ---------------------------------------------------------------------------


def save_plan_graph(graph: PlanGraph, path: Path) -> None:
    """Serialize a :class:`PlanGraph` to ``path`` as YAML (or JSON).

    The format is chosen from the file extension: ``.json`` writes JSON, every
    other extension (``.yaml``/``.yml`` and anything else) writes YAML. Field
    names align with ``templates/plan_graph.schema.json``.
    """
    if not isinstance(graph, PlanGraph):
        raise DMCValidationError("save_plan_graph requires a PlanGraph instance")
    path = Path(path)
    payload = graph.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    else:
        text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
    path.write_text(text, encoding="utf-8")


def load_plan_graph(path: Path) -> PlanGraph:
    """Load a :class:`PlanGraph` from a YAML or JSON file.

    Reconstructs and validates the model (Pydantic graph-level validation plus
    schema field validation). Raises :class:`DMCValidationError` if the file is
    missing, unparseable, or does not contain a mapping.
    """
    path = Path(path)
    if not path.exists():
        raise DMCValidationError(f"no plan graph file at {path}")
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise DMCValidationError(f"failed to parse plan graph {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DMCValidationError(
            f"plan graph file {path} did not contain a mapping "
            f"(got {type(data).__name__})"
        )
    return PlanGraph.model_validate(data)
