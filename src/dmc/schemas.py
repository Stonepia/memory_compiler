"""DMC durable Pydantic schemas — the single contract module.

This module (M01_SCHEMAS) defines every durable data shape used by the Dev
Memory Compiler. All other modules MUST import these models rather than
redefining their own shapes.

Design rules enforced here (see ``modules/M01_SCHEMAS.md``):

* IDs are non-empty, slug-like strings (``Slug``).
* URIs use known scheme prefixes where applicable (``Uri``).
* ``PlanNode`` dependencies must reference existing nodes in the same
  ``PlanGraph`` (validated at the graph level).
* ``TraceEvent`` must carry ``session_id``, ``event_id``, ``phase``,
  ``action.kind`` and an ``observation.outcome``.
* Final/durable memory objects require a non-empty ``provenance`` list. An
  empty provenance list is invalid for those objects.
* ``EvalCase`` must include task, plan refs, outcome, labels and provenance.

Field shapes are aligned with the three target JSON schemas:
``templates/plan_graph.schema.json``, ``templates/trace_event.schema.json`` and
``templates/eval_case.schema.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

__all__ = [
    "SLUG_RE",
    "KNOWN_URI_SCHEMES",
    "Slug",
    "Uri",
    "Provenance",
    "EvidenceRef",
    "TaskRequest",
    "ProjectState",
    "SkillCard",
    "Tier0Policy",
    "Tier1Workflow",
    "Tier2Atom",
    "KnowledgeRef",
    "ArtifactCard",
    "TraceAction",
    "TraceObservation",
    "TraceEvent",
    "PlanNode",
    "PlanGraph",
    "ValidationReport",
    "SearchRequest",
    "SearchResult",
    "PrecheckRequest",
    "PrecheckRule",
    "PrecheckResult",
    "EpisodeCard",
    "FailureMode",
    "SkillUpdateProposal",
    "EvalCase",
    "DistillResult",
    "AgentState",
    "EXPORTED_MODELS",
    "export_json_schemas",
]


# ---------------------------------------------------------------------------
# Primitive validated types
# ---------------------------------------------------------------------------

#: A slug-like identifier: starts with an alphanumeric, then alphanumerics plus
#: ``-``, ``_`` and ``.``. No whitespace, no slashes, never empty.
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: URI schemes DMC recognises. ``URI`` values must use one of these prefixes.
KNOWN_URI_SCHEMES: frozenset[str] = frozenset(
    {
        "dmc",
        "plan",
        "session",
        "event",
        "artifact",
        "episode",
        "failure_mode",
        "proposal",
        "eval_case",
        "knowledge",
        "skill",
        "file",
        "git",
        "http",
        "https",
    }
)

_URI_RE = re.compile(r"^(?P<scheme>[a-z][a-z0-9_]*)://(?P<rest>.+)$")


def _validate_slug(value: str) -> str:
    """Reject empty or non slug-like identifiers."""
    if not isinstance(value, str):
        raise ValueError("id must be a string")
    if not value:
        raise ValueError("id must be a non-empty slug-like string")
    if not SLUG_RE.match(value):
        raise ValueError(
            f"invalid id {value!r}: must be slug-like "
            "(alphanumeric start; only letters, digits, '.', '-', '_')"
        )
    return value


def _validate_uri(value: str) -> str:
    """Reject URIs that do not use a known scheme prefix."""
    if not isinstance(value, str) or not value:
        raise ValueError("uri must be a non-empty string")
    match = _URI_RE.match(value)
    if not match:
        raise ValueError(
            f"invalid uri {value!r}: expected '<scheme>://<path>' form"
        )
    scheme = match.group("scheme")
    if scheme not in KNOWN_URI_SCHEMES:
        raise ValueError(
            f"unknown uri scheme {scheme!r} in {value!r}: "
            f"known schemes are {sorted(KNOWN_URI_SCHEMES)}"
        )
    return value


Slug = Annotated[str, AfterValidator(_validate_slug)]
Uri = Annotated[str, AfterValidator(_validate_uri)]


# ---------------------------------------------------------------------------
# Provenance / evidence
# ---------------------------------------------------------------------------


class Provenance(BaseModel):
    """Where a piece of memory came from.

    Accepts either a structured mapping or a bare URI string (which is coerced
    into ``{"source": <uri>}``). ``source`` must be a known-scheme URI.
    """

    model_config = ConfigDict(extra="allow")

    source: Uri
    kind: str | None = None
    detail: str | None = None
    timestamp: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"source": value}
        return value


class EvidenceRef(BaseModel):
    """A pointer to supporting evidence (artifact, file, event, ...)."""

    model_config = ConfigDict(extra="allow")

    uri: Uri
    description: str | None = None
    kind: str | None = None


#: Reusable type for durable memory objects: provenance list must be non-empty.
NonEmptyProvenance = Annotated[list[Provenance], Field(min_length=1)]


# ---------------------------------------------------------------------------
# Task and project state
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """A request to work on a task. Aligned with ``examples/sample_task.yaml``."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    task: str
    repo: str | None = None
    mode: str | None = None
    hardware: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    current_phase: str | None = None
    budget_tokens: int | None = None
    constraints: list[str] = Field(default_factory=list)


class ProjectState(BaseModel):
    """Where the project is now."""

    model_config = ConfigDict(extra="allow")

    name: str
    status: str
    current_phase: str | None = None
    summary: str | None = None
    active_task: Slug | None = None
    open_questions: list[str] = Field(default_factory=list)
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Skills (tiered)
# ---------------------------------------------------------------------------


class SkillCard(BaseModel):
    """Base skill card shared by all tiers."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    tier: Literal[0, 1, 2]
    title: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)


class Tier0Policy(SkillCard):
    """Always-on evidence/reproducibility policy."""

    tier: Literal[0] = 0
    policy: str
    always_on: bool = True


class Tier1Workflow(SkillCard):
    """A stable, reusable task workflow."""

    tier: Literal[1] = 1
    steps: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)


class Tier2Atom(SkillCard):
    """An executable atomic action / tool pattern."""

    tier: Literal[2] = 2
    pattern: str
    command: str | None = None
    tools: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Knowledge and artifacts (durable, evidence-bearing)
# ---------------------------------------------------------------------------


class KnowledgeRef(BaseModel):
    """A fact/spec/doc/code reference with provenance."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    kind: str
    uri: Uri
    summary: str
    tags: list[str] = Field(default_factory=list)
    provenance: NonEmptyProvenance


class ArtifactCard(BaseModel):
    """A raw artifact summary and its URI."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    uri: Uri
    kind: str
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    provenance: NonEmptyProvenance


# ---------------------------------------------------------------------------
# Trace events (aligned with templates/trace_event.schema.json)
# ---------------------------------------------------------------------------

TracePhase = Literal[
    "localize",
    "inspect",
    "plan",
    "edit",
    "test",
    "benchmark",
    "profile",
    "analyze",
    "validate",
    "review",
    "distill",
]

TraceActor = Literal["agent", "human", "tool", "system"]


class TraceAction(BaseModel):
    """The action taken in an event. ``kind`` is required."""

    model_config = ConfigDict(extra="allow")

    kind: str
    command: str | None = None
    files: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kind_non_empty(self) -> "TraceAction":
        if not self.kind:
            raise ValueError("action.kind must be a non-empty string")
        return self


class TraceObservation(BaseModel):
    """The observed result of an action. ``outcome`` is required."""

    model_config = ConfigDict(extra="allow")

    outcome: str
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _outcome_non_empty(self) -> "TraceObservation":
        if not self.outcome:
            raise ValueError("observation.outcome must be a non-empty string")
        return self


class TraceEvent(BaseModel):
    """An action-level event from a session.

    Must carry ``session_id``, ``event_id``, ``phase``, ``action.kind`` and
    ``observation.outcome`` and a non-empty provenance list.
    """

    model_config = ConfigDict(extra="allow")

    event_id: Slug
    session_id: Slug
    phase: TracePhase
    actor: TraceActor
    intent: str
    action: TraceAction
    observation: TraceObservation
    timestamp: str
    run_id: str | None = None
    step_id: int | None = None
    repo_state: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: dict[str, Any] = Field(default_factory=dict)
    memory_hooks: dict[str, Any] = Field(default_factory=dict)
    provenance: NonEmptyProvenance


# ---------------------------------------------------------------------------
# Plan graph (aligned with templates/plan_graph.schema.json)
# ---------------------------------------------------------------------------

PlanNodeType = Literal[
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
]


class PlanNode(BaseModel):
    """A single node in an executable plan graph."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    type: PlanNodeType
    goal: str
    # Required per templates/plan_graph.schema.json: the fields must be present.
    # They may be empty lists, but they are not optional.
    dependencies: list[Slug]
    success_criteria: list[str]
    agent: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_contract: dict[str, Any] = Field(default_factory=dict)
    human_review: dict[str, Any] = Field(default_factory=dict)


class PlanGraph(BaseModel):
    """An editable execution graph over plan nodes."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    task: TaskRequest
    # Required per templates/plan_graph.schema.json (top-level `nodes`).
    nodes: list[PlanNode]

    @model_validator(mode="after")
    def _validate_dependency_refs(self) -> "PlanGraph":
        node_ids = [node.id for node in self.nodes]
        seen: set[str] = set()
        for node_id in node_ids:
            if node_id in seen:
                raise ValueError(f"duplicate plan node id: {node_id!r}")
            seen.add(node_id)
        for node in self.nodes:
            for dep in node.dependencies:
                if dep not in seen:
                    raise ValueError(
                        f"plan node {node.id!r} depends on unknown node {dep!r}"
                    )
                if dep == node.id:
                    raise ValueError(
                        f"plan node {node.id!r} cannot depend on itself"
                    )
        return self


class ValidationReport(BaseModel):
    """Result of validating a :class:`PlanGraph` (or similar object).

    Validation does not raise for an invalid graph; instead it collects every
    problem so callers can report all of them at once. ``ok`` is ``True`` only
    when ``errors`` is empty. ``ok`` is kept in sync with ``errors`` by a
    validator so a report cannot claim success while carrying errors.
    """

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_ok(self) -> "ValidationReport":
        # ``ok`` is authoritative-by-derivation: a report with errors is never ok.
        self.ok = not self.errors
        return self

    @property
    def valid(self) -> bool:
        """Alias for :attr:`ok` (a graph is valid when there are no errors)."""
        return self.ok


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """A local search request over DMC objects."""

    model_config = ConfigDict(extra="allow")

    query: str
    scopes: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 10
    budget_tokens: int | None = None


class SearchResult(BaseModel):
    """A single local search hit.

    ``reason`` is an optional, human-readable explanation of *why* this result
    is relevant to the query (populated by the retriever's ranking step). It is
    optional with a ``None`` default so existing callers/constructions stay
    valid. Provenance, when the backing object carries it, is attached as an
    extra field (``model_config`` allows extras).
    """

    model_config = ConfigDict(extra="allow")

    uri: Uri
    score: float
    kind: str
    snippet: str | None = None
    title: str | None = None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Precheck (request aligned with examples/sample_action.yaml)
# ---------------------------------------------------------------------------


class PrecheckRequest(BaseModel):
    """A proposed action to validate before execution."""

    model_config = ConfigDict(extra="allow")

    action: str
    files: list[str] = Field(default_factory=list)
    command: str | None = None
    intent: str | None = None
    risk_level: str | None = None
    task_context: dict[str, Any] = Field(default_factory=dict)


class PrecheckRule(BaseModel):
    """A deterministic precheck warning/block rule.

    Rules are evaluated by ``src/dmc/precheck.py`` (no LLM). Each rule carries a
    stable ``id`` (slug), a human-readable ``description``, and the ``decision``
    it contributes when it fires (``warn`` or ``block``). ``required_evidence``
    lists evidence/paths the agent must supply before committing when the rule
    fires (e.g. the proposal path for a blocked direct skill mutation).
    """

    model_config = ConfigDict(extra="allow")

    id: Slug
    description: str
    decision: Literal["warn", "block"]
    rationale: str | None = None
    required_evidence: list[str] = Field(default_factory=list)


class PrecheckResult(BaseModel):
    """The deterministic precheck decision for an action."""

    model_config = ConfigDict(extra="allow")

    decision: Literal["allow", "warn", "block"]
    reasons: list[str] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_evidence_before_commit: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Distilled / durable memory objects (require non-empty provenance)
# ---------------------------------------------------------------------------


class EpisodeCard(BaseModel):
    """What happened in a session."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    session_id: Slug
    summary: str
    outcome: str
    task: Slug | None = None
    highlights: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    provenance: NonEmptyProvenance


class FailureMode(BaseModel):
    """A repeatable wrong turn and its trigger."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    trigger: str
    description: str
    symptom: str | None = None
    avoidance: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    provenance: NonEmptyProvenance


class SkillUpdateProposal(BaseModel):
    """A pending change to a workflow/atom/knowledge object."""

    model_config = ConfigDict(extra="allow")

    id: Slug
    target: Uri
    change_kind: Literal["create", "update", "deprecate"]
    rationale: str
    diff_summary: str | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"
    evidence: list[EvidenceRef] = Field(default_factory=list)
    provenance: NonEmptyProvenance


class EvalCase(BaseModel):
    """A test-set-like record produced from a session.

    Aligned with ``templates/eval_case.schema.json``. Must include task, plan
    refs, outcome, labels and a non-empty provenance list.
    """

    model_config = ConfigDict(extra="allow")

    id: Slug
    source_session: Slug
    task: TaskRequest
    outcome: dict[str, Any]
    labels: dict[str, Any]
    # Plan refs are required per modules/M01_SCHEMAS.md (task, plan refs,
    # outcome, labels, provenance). `initial_plan_graph` is the mandatory plan
    # reference; the others remain optional and align with
    # templates/eval_case.schema.json property names.
    initial_plan_graph: Uri
    final_plan_graph: Uri | None = None
    execution_trace: Uri | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    future_assertions: list[str] = Field(default_factory=list)
    provenance: NonEmptyProvenance


# ---------------------------------------------------------------------------
# Distillation result (M08_DISTILLER_EVALS aggregate output)
# ---------------------------------------------------------------------------


class DistillResult(BaseModel):
    """Aggregate output of :func:`dmc.distiller.distill_session`.

    Carries the durable objects derived from a session plus the storage refs
    of what was persisted. ``episode`` and ``eval_case`` are always produced;
    ``failure_modes`` and ``skill_proposals`` may be empty when the session had
    no triggering events. Skill proposals are persisted to the pending area
    (``.dmc/proposals/pending``) only — they never mutate accepted skills.
    """

    model_config = ConfigDict(extra="allow")

    session_id: Slug
    episode: EpisodeCard
    eval_case: EvalCase
    failure_modes: list[FailureMode] = Field(default_factory=list)
    skill_proposals: list[SkillUpdateProposal] = Field(default_factory=list)
    episode_uri: Uri
    eval_case_uri: Uri
    failure_mode_uris: list[Uri] = Field(default_factory=list)
    proposal_uris: list[Uri] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent state (permissive mirror of agent_state.json)
# ---------------------------------------------------------------------------


class AgentState(BaseModel):
    """A permissive model of ``agent_state.json``.

    Kept intentionally loose: it is the coordination file, owned by the state
    protocol, not by any single module. Unknown keys are preserved.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str
    project: dict[str, Any]
    current_phase: str
    modules: dict[str, Any]
    quality_gates: dict[str, Any]
    current_gate: str | None = None
    global_rules: dict[str, Any] = Field(default_factory=dict)
    handoffs: list[Any] = Field(default_factory=list)
    decisions: list[Any] = Field(default_factory=list)
    blockers: list[Any] = Field(default_factory=list)
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Schema export helper
# ---------------------------------------------------------------------------

#: Models exported to JSON schema files. Keyed by file stem.
EXPORTED_MODELS: dict[str, type[BaseModel]] = {
    "provenance": Provenance,
    "evidence_ref": EvidenceRef,
    "task_request": TaskRequest,
    "project_state": ProjectState,
    "skill_card": SkillCard,
    "tier0_policy": Tier0Policy,
    "tier1_workflow": Tier1Workflow,
    "tier2_atom": Tier2Atom,
    "knowledge_ref": KnowledgeRef,
    "artifact_card": ArtifactCard,
    "trace_event": TraceEvent,
    "plan_node": PlanNode,
    "plan_graph": PlanGraph,
    "validation_report": ValidationReport,
    "search_request": SearchRequest,
    "search_result": SearchResult,
    "precheck_request": PrecheckRequest,
    "precheck_rule": PrecheckRule,
    "precheck_result": PrecheckResult,
    "episode_card": EpisodeCard,
    "failure_mode": FailureMode,
    "skill_update_proposal": SkillUpdateProposal,
    "eval_case": EvalCase,
    "distill_result": DistillResult,
    "agent_state": AgentState,
}


def export_json_schemas(out_dir: str | Path = ".dmc/generated_schemas") -> list[Path]:
    """Write ``model_json_schema()`` for every exported model under ``out_dir``.

    Returns the list of written file paths. Deterministic output (sorted keys,
    trailing newline) so generated files are diff-friendly.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stem, model in EXPORTED_MODELS.items():
        target = out_path / f"{stem}.schema.json"
        schema = model.model_json_schema()
        target.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(target)
    return written
