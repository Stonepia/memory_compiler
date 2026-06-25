"""Pure rendering of PlanGraph and briefing to Mermaid/Markdown (M04_RENDERER).

This module turns durable DMC data shapes into human-readable text. It is
deliberately *pure*: every function is a deterministic transformation of its
inputs into a string, with the single exception of :func:`write_rendered`,
which writes a finished string to disk.

Design rules (see ``modules/M04_RENDERER.md`` and
``docs/v1/01_VISUALIZATION_OPTIONAL.md``):

* V0 visualization is **Mermaid text and Markdown only** — no HTML UI, no
  frontend framework, no server, no LLM, and no node execution.
* All data shapes are imported from :mod:`dmc.schemas`; nothing is redefined.
* Rendering is deterministic: the same graph renders to identical text every
  time (node order follows ``graph.nodes``).

Public API
----------

``render_plan_mermaid(graph) -> str``
    Mermaid ``flowchart`` text. Starts with ``flowchart TD``. Each node label
    carries the node id and type; dependency edges are drawn; human-review and
    evidence gates are made visible on the relevant nodes.
``render_plan_markdown(graph) -> str``
    Markdown view of the plan: per-node goal, success criteria, and explicit
    human-review / evidence-gate visibility.
``render_briefing(request, graph, context=None) -> str``
    Markdown briefing with the six required sections (workflows, atoms,
    knowledge refs, pitfalls, open questions, next actions). Uses the optional
    ``context`` search results to populate knowledge refs / pitfalls.
``write_rendered(text, path) -> None``
    Write rendered text to ``path``, creating parent directories as needed.
"""

from __future__ import annotations

from pathlib import Path

from dmc.planner import next_ready_nodes
from dmc.schemas import PlanGraph, PlanNode, SearchResult, TaskRequest

__all__ = [
    "render_plan_mermaid",
    "render_plan_markdown",
    "render_briefing",
    "write_rendered",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_review_required(node: PlanNode) -> bool:
    """True when a node carries an explicit ``human_review.required == True``."""
    hr = node.human_review
    return isinstance(hr, dict) and bool(hr.get("required", False))


def _evidence_required(node: PlanNode) -> bool:
    """True when a node carries an evidence contract requiring evidence."""
    ec = node.evidence_contract
    if not isinstance(ec, dict) or not ec:
        return False
    # An evidence contract that is present and non-empty is treated as an
    # active gate. If it sets an explicit ``required`` flag, honour it.
    if "required" in ec:
        return bool(ec.get("required"))
    return True


def _gate_markers(node: PlanNode) -> list[str]:
    """Short, human-visible markers for the gates active on a node."""
    markers: list[str] = []
    if _human_review_required(node):
        markers.append("human_review")
    if _evidence_required(node):
        markers.append("evidence")
    return markers


def _sanitize_label(text: str) -> str:
    """Make text safe to embed inside a Mermaid bracket label.

    Mermaid node labels are delimited by ``[`` and ``]`` and break on quotes
    and newlines. We strip the structural characters and collapse whitespace
    so the label stays on one line and the flowchart remains parseable.
    """
    cleaned = text.replace("[", "(").replace("]", ")")
    cleaned = cleaned.replace('"', "'").replace("\n", " ").replace("\r", " ")
    return " ".join(cleaned.split())


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------


def render_plan_mermaid(graph: PlanGraph) -> str:
    """Render ``graph`` as Mermaid ``flowchart TD`` text.

    Guarantees (see ``modules/M04_RENDERER.md`` lines 49-53):

    * Output starts with ``flowchart TD``.
    * Every node's label contains its id **and** its type.
    * Human-review gates are visible (a ``human_review`` marker on the node).
    * Evidence gates are visible (an ``evidence`` marker on the node).
    * One edge per dependency (``dep --> node``).

    Output is deterministic: nodes and edges follow ``graph.nodes`` order.
    """
    if not isinstance(graph, PlanGraph):  # defensive: API misuse
        raise TypeError("render_plan_mermaid requires a PlanGraph instance")

    lines: list[str] = ["flowchart TD"]

    # Node declarations: id["<id> (<type>) [gate markers]"]
    for node in graph.nodes:
        markers = _gate_markers(node)
        label_parts = [f"{node.id} ({node.type})"]
        if node.goal and node.goal.strip():
            label_parts.append(_sanitize_label(node.goal))
        if markers:
            label_parts.append("gates: " + ", ".join(markers))
        label = " | ".join(label_parts)
        lines.append(f'    {node.id}["{label}"]')

    # Edges: one per dependency, in node then dependency order.
    for node in graph.nodes:
        for dep in node.dependencies:
            lines.append(f"    {dep} --> {node.id}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Markdown plan
# ---------------------------------------------------------------------------


def render_plan_markdown(graph: PlanGraph) -> str:
    """Render ``graph`` as a Markdown plan document.

    Includes a header, the task, and a section per node containing the node's
    id, type, goal, dependencies, success criteria, and explicit visibility of
    its human-review and evidence gates.
    """
    if not isinstance(graph, PlanGraph):  # defensive: API misuse
        raise TypeError("render_plan_markdown requires a PlanGraph instance")

    lines: list[str] = [
        f"# Plan: {graph.id}",
        "",
        f"- Task: {graph.task.task}",
        f"- Task id: {graph.task.id}",
        f"- Nodes: {len(graph.nodes)}",
        "",
        "## Nodes",
        "",
    ]

    if not graph.nodes:
        lines.append("_(no nodes)_")
        lines.append("")

    for node in graph.nodes:
        human_review = "yes" if _human_review_required(node) else "no"
        evidence = "yes" if _evidence_required(node) else "no"
        deps = ", ".join(node.dependencies) if node.dependencies else "(none)"
        lines.append(f"### {node.id} ({node.type})")
        lines.append("")
        lines.append(f"- Goal: {node.goal}")
        lines.append(f"- Dependencies: {deps}")
        lines.append(f"- Human review gate: {human_review}")
        lines.append(f"- Evidence gate: {evidence}")
        if node.success_criteria:
            lines.append("- Success criteria:")
            for crit in node.success_criteria:
                lines.append(f"    - {crit}")
        else:
            lines.append("- Success criteria: (none)")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------

#: Keywords used to classify a search result as a pitfall/failure-mode hit
#: rather than a generic knowledge reference.
_PITFALL_KINDS = frozenset(
    {"failure_mode", "failure", "pitfall", "pitfalls", "wrong_turn"}
)
_PITFALL_HINTS = ("pitfall", "failure", "wrong turn", "regression", "avoid")


def _looks_like_pitfall(result: SearchResult) -> bool:
    """Classify a search hit as a pitfall vs a generic knowledge reference."""
    kind = (result.kind or "").lower()
    if kind in _PITFALL_KINDS:
        return True
    haystack = " ".join(
        part.lower()
        for part in (result.kind, result.title, result.snippet, result.uri)
        if part
    )
    return any(hint in haystack for hint in _PITFALL_HINTS)


def _result_line(result: SearchResult) -> str:
    """A single Markdown bullet describing a search result."""
    title = result.title or result.snippet or result.uri
    title = " ".join(str(title).split())
    return f"- {title} ({result.uri})"


def render_briefing(
    request: TaskRequest,
    graph: PlanGraph,
    context: list[SearchResult] | None = None,
) -> str:
    """Render a Markdown task briefing.

    The briefing always contains the six required sections, in order:

    1. Selected workflows
    2. Atoms
    3. Knowledge refs
    4. Pitfalls
    5. Open questions
    6. Next actions

    ``next actions`` are derived from the plan graph's *ready* / first nodes
    (the nodes with no incomplete dependencies). The optional ``context``
    (a list of :class:`SearchResult`) is used to populate knowledge refs and
    pitfalls: results that look like failure modes/pitfalls go to the pitfalls
    section, the rest become knowledge references.

    Every section is always rendered; a section with no data emits an explicit
    placeholder line rather than being omitted.
    """
    if not isinstance(request, TaskRequest):  # defensive: API misuse
        raise TypeError("render_briefing requires a TaskRequest instance")
    if not isinstance(graph, PlanGraph):  # defensive: API misuse
        raise TypeError("render_briefing requires a PlanGraph instance")

    results = list(context or [])
    pitfalls = [r for r in results if _looks_like_pitfall(r)]
    knowledge = [r for r in results if not _looks_like_pitfall(r)]

    lines: list[str] = [
        f"# Briefing: {request.id}",
        "",
        f"- Task: {request.task}",
    ]
    if request.repo:
        lines.append(f"- Repo: {request.repo}")
    if request.current_phase:
        lines.append(f"- Phase: {request.current_phase}")
    if request.hardware:
        lines.append(f"- Hardware: {', '.join(request.hardware)}")
    if request.constraints:
        lines.append(f"- Constraints: {', '.join(request.constraints)}")
    lines.append("")

    # 1. Selected workflows — derived from the plan node types (the workflow
    #    spine). Always non-empty when the graph has nodes.
    lines.append("## Selected workflows")
    lines.append("")
    if graph.nodes:
        for node in graph.nodes:
            lines.append(f"- {node.type}: {node.goal} ({node.id})")
    else:
        lines.append("- (no workflows selected)")
    lines.append("")

    # 2. Atoms — concrete success criteria are the atomic checks for this plan.
    lines.append("## Atoms")
    lines.append("")
    atoms = [
        (node.id, crit)
        for node in graph.nodes
        for crit in node.success_criteria
    ]
    if atoms:
        for node_id, crit in atoms:
            lines.append(f"- [{node_id}] {crit}")
    else:
        lines.append("- (no atoms)")
    lines.append("")

    # 3. Knowledge refs — from the provided context.
    lines.append("## Knowledge refs")
    lines.append("")
    if knowledge:
        for result in knowledge:
            lines.append(_result_line(result))
    else:
        lines.append("- (no knowledge refs)")
    lines.append("")

    # 4. Pitfalls — failure-mode/pitfall-like hits from the context.
    lines.append("## Pitfalls")
    lines.append("")
    if pitfalls:
        for result in pitfalls:
            lines.append(_result_line(result))
    else:
        lines.append("- (no known pitfalls)")
    lines.append("")

    # 5. Open questions — from the task request where present.
    lines.append("## Open questions")
    lines.append("")
    open_questions = list(getattr(request, "open_questions", []) or [])
    if open_questions:
        for question in open_questions:
            lines.append(f"- {question}")
    else:
        lines.append("- (no open questions)")
    lines.append("")

    # 6. Next actions — derived from the plan graph's ready / first nodes.
    lines.append("## Next actions")
    lines.append("")
    ready = next_ready_nodes(graph, set())
    if ready:
        for node in ready:
            markers = _gate_markers(node)
            suffix = f" [gates: {', '.join(markers)}]" if markers else ""
            lines.append(f"- {node.id} ({node.type}): {node.goal}{suffix}")
    else:
        lines.append("- (no next actions)")
    lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_rendered(text: str, path: Path) -> None:
    """Write ``text`` to ``path``, creating parent directories as needed.

    This is the only side-effecting function in the module. The text is written
    verbatim (UTF-8), so the caller controls the exact file content.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
