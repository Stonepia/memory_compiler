"""DMC deterministic session distillation and eval-case generation (M08).

This module turns a session's recorded :class:`~dmc.schemas.TraceEvent` stream
into durable, evidence-bearing memory objects:

* :class:`~dmc.schemas.EpisodeCard` — what happened in the session.
* :class:`~dmc.schemas.EvalCase` — a test-set-like record derived from the
  session (task, plan refs, outcome, labels, provenance).
* :class:`~dmc.schemas.FailureMode` candidates — repeatable wrong turns derived
  from failed/regressed events.
* :class:`~dmc.schemas.SkillUpdateProposal` candidates — *pending* proposals
  only; this module never mutates accepted skills under ``.dmc/skills``.

Design rules (see ``modules/M08_DISTILLER_EVALS.md`` and
``docs/v1/00_PLAN_GRAPH_AND_LEARNING_LOOP.md``):

* **Deterministic / rule-based, no LLM, no network.** Running the builders or
  :func:`distill_session` twice over the same store yields equal objects (and
  re-writes the same files).
* **Failed/regressed events** produce ``wrong_turn`` labels and failure modes.
* **Successful validation events** (``test``/``validate``/``benchmark`` phases
  with a passing outcome) produce ``useful_memory`` labels.
* **Proposals are pending only.** They are persisted under
  ``.dmc/proposals/pending`` and never written under ``.dmc/skills``.
* **Every durable output carries non-empty provenance** linking back to the
  session and the events/artifacts it was derived from. No evidence-free
  lessons are ever created.

Shapes are imported from ``src/dmc/schemas.py``; none are redefined here.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from dmc.schemas import (
    DistillResult,
    EpisodeCard,
    EvalCase,
    EvidenceRef,
    FailureMode,
    Provenance,
    SkillUpdateProposal,
    TaskRequest,
    TraceEvent,
)
from dmc.store import DMCStore, DMCValidationError

__all__ = [
    "FAILURE_OUTCOME_MARKERS",
    "SUCCESS_OUTCOME_MARKERS",
    "VALIDATION_PHASES",
    "is_failure_event",
    "is_success_validation_event",
    "distill_session",
    "build_episode_card",
    "build_eval_case",
    "propose_failure_modes",
    "propose_skill_updates",
]


# ---------------------------------------------------------------------------
# Deterministic event classification
# ---------------------------------------------------------------------------

#: Substrings (matched case-insensitively against ``observation.outcome``) that
#: mark an event as a failed/regressed/wrong-turn event.
FAILURE_OUTCOME_MARKERS: tuple[str, ...] = (
    "fail",
    "regress",
    "error",
    "blocked",
    "broke",
)

#: Substrings marking a *successful* outcome.
SUCCESS_OUTCOME_MARKERS: tuple[str, ...] = (
    "success",
    "passed",
    "pass",
    "ok",
    "green",
)

#: Phases whose successful outcomes count as a *validation* (useful_memory).
VALIDATION_PHASES: frozenset[str] = frozenset({"test", "validate", "benchmark"})


def is_failure_event(event: TraceEvent) -> bool:
    """Return ``True`` when an event's outcome marks a failure/regression."""
    outcome = event.observation.outcome.lower()
    return any(marker in outcome for marker in FAILURE_OUTCOME_MARKERS)


def is_success_validation_event(event: TraceEvent) -> bool:
    """Return ``True`` for a successful validation/test/benchmark event."""
    if event.phase not in VALIDATION_PHASES:
        return False
    outcome = event.observation.outcome.lower()
    if any(marker in outcome for marker in FAILURE_OUTCOME_MARKERS):
        return False
    return any(marker in outcome for marker in SUCCESS_OUTCOME_MARKERS)


# ---------------------------------------------------------------------------
# Provenance / evidence helpers (every durable object must carry these)
# ---------------------------------------------------------------------------


def _session_provenance(session_id: str, events: list[TraceEvent]) -> list[Provenance]:
    """Build a non-empty provenance chain: the session plus each event.

    The first entry always references the session, so the returned list is
    non-empty even for an empty event list (no evidence-free objects).
    """
    prov: list[Provenance] = [Provenance(source=f"session://{session_id}")]
    for event in events:
        prov.append(Provenance(source=f"event://{event.event_id}"))
    return prov


def _event_provenance(session_id: str, event: TraceEvent) -> list[Provenance]:
    """Provenance tying a single-event-derived object to session + event."""
    return [
        Provenance(source=f"session://{session_id}"),
        Provenance(source=f"event://{event.event_id}"),
    ]


def _event_evidence(events: list[TraceEvent]) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            uri=f"event://{event.event_id}",
            kind="trace_event",
            description=f"{event.phase}/{event.action.kind}: {event.observation.outcome}",
        )
        for event in events
    ]


def _initial_plan_graph_uri(session_id: str) -> str:
    """Deterministic plan-graph URI synthesized from the session id.

    A V0 session may carry no explicit plan-graph reference. To keep the
    derived :class:`EvalCase` schema-valid *and* provenance-backed, we reference
    a deterministic ``plan://<session_id>/initial`` URI tied to the actual
    session rather than fabricating evidence-free plan content.
    """
    return f"plan://{session_id}/initial"


def _overall_outcome(events: list[TraceEvent]) -> str:
    """Derive a deterministic session-level outcome string from events."""
    if not events:
        return "empty"
    if any(is_failure_event(event) for event in events):
        return "failed"
    if any(is_success_validation_event(event) for event in events):
        return "success"
    return "completed"


def _labels(session_id: str, events: list[TraceEvent]) -> dict[str, list[str]]:
    """Deterministic label map: wrong_turn + useful_memory event ids."""
    wrong_turn = [e.event_id for e in events if is_failure_event(e)]
    useful_memory = [e.event_id for e in events if is_success_validation_event(e)]
    return {"wrong_turn": wrong_turn, "useful_memory": useful_memory}


# ---------------------------------------------------------------------------
# Builders (deterministic; take events directly, no store dependency)
# ---------------------------------------------------------------------------


def build_episode_card(session_id: str, events: list[TraceEvent]) -> EpisodeCard:
    """Summarize a session's events into an :class:`EpisodeCard`.

    The summary mirrors :func:`dmc.recorder.summarize_session_trace` (counts by
    phase/action/outcome) but is computed directly from ``events`` so the
    builder stays store-independent. The card always carries non-empty
    provenance referencing the session and its events.
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("build_episode_card requires a non-empty session_id")

    phase_counts = dict(sorted(Counter(e.phase for e in events).items()))
    outcome = _overall_outcome(events)
    labels = _labels(session_id, events)

    highlights: list[str] = []
    for event in events:
        if is_failure_event(event):
            highlights.append(
                f"wrong_turn[{event.event_id}]: {event.phase}/{event.action.kind} "
                f"-> {event.observation.outcome}"
            )
        elif is_success_validation_event(event):
            highlights.append(
                f"useful_memory[{event.event_id}]: {event.phase}/{event.action.kind} "
                f"-> {event.observation.outcome}"
            )

    summary = (
        f"Session {session_id}: {len(events)} event(s), "
        f"outcome={outcome}, phases={phase_counts}"
    )

    return EpisodeCard(
        id=f"episode-{session_id}",
        session_id=session_id,
        summary=summary,
        outcome=outcome,
        highlights=highlights,
        evidence=_event_evidence(events),
        provenance=_session_provenance(session_id, events),
        labels=labels,
    )


def build_eval_case(session_id: str, events: list[TraceEvent]) -> EvalCase:
    """Build a schema-valid :class:`EvalCase` from a session's events.

    Includes a task, a plan ref (``initial_plan_graph``), an outcome dict,
    a labels dict and non-empty provenance. The plan ref is a deterministic
    ``plan://<session_id>/initial`` URI synthesized from the session (see
    :func:`_initial_plan_graph_uri`).
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("build_eval_case requires a non-empty session_id")

    outcome = _overall_outcome(events)
    labels = _labels(session_id, events)

    intents = [e.intent for e in events if e.intent]
    task_text = (
        f"Session {session_id}: {intents[0]}" if intents else f"Session {session_id}"
    )

    task = TaskRequest(id=session_id, task=task_text)

    outcome_dict = {
        "status": outcome,
        "num_events": len(events),
        "num_failures": len(labels["wrong_turn"]),
        "num_success_validations": len(labels["useful_memory"]),
        "counts_by_outcome": dict(
            sorted(Counter(e.observation.outcome for e in events).items())
        ),
    }

    return EvalCase(
        id=f"evalcase-{session_id}",
        source_session=session_id,
        task=task,
        outcome=outcome_dict,
        labels=labels,
        initial_plan_graph=_initial_plan_graph_uri(session_id),
        execution_trace=f"session://{session_id}",
        provenance=_session_provenance(session_id, events),
    )


def propose_failure_modes(session_id: str, events: list[TraceEvent]) -> list[FailureMode]:
    """Derive :class:`FailureMode` candidates from failed/regressed events.

    Returns one failure mode per failure event, each tagged ``wrong_turn`` and
    carrying non-empty provenance (session + the triggering event). Returns an
    empty list when no failure/regression events exist.
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("propose_failure_modes requires a non-empty session_id")

    failure_modes: list[FailureMode] = []
    for event in events:
        if not is_failure_event(event):
            continue
        command = event.action.command or event.action.kind
        failure_modes.append(
            FailureMode(
                id=f"fm-{session_id}-{event.event_id}",
                trigger=f"{event.phase}/{event.action.kind}",
                description=(
                    f"During '{event.intent}' the {event.action.kind} action "
                    f"({command!r}) resulted in outcome "
                    f"{event.observation.outcome!r}."
                ),
                symptom=event.observation.outcome,
                avoidance=(
                    f"Before repeating {event.action.kind} in phase "
                    f"'{event.phase}', verify the prior failure "
                    f"({event.observation.outcome}) is addressed."
                ),
                evidence=_event_evidence([event]),
                provenance=_event_provenance(session_id, event),
                labels={"wrong_turn": [event.event_id]},
            )
        )
    return failure_modes


def propose_skill_updates(
    session_id: str, events: list[TraceEvent]
) -> list[SkillUpdateProposal]:
    """Derive *pending* :class:`SkillUpdateProposal` candidates from events.

    * Each failed/regressed event yields a proposal to create a pitfall/atom
      skill that helps future agents avoid the wrong turn (``wrong_turn``).
    * Each successful validation event yields a proposal capturing it as a
      reusable, ``useful_memory`` workflow signal.

    Proposals are always ``status="pending"`` and carry non-empty provenance.
    This function never mutates accepted skills; persistence (when invoked via
    :func:`distill_session`) targets ``.dmc/proposals/pending`` only. Returns an
    empty list when no triggering events exist.
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("propose_skill_updates requires a non-empty session_id")

    proposals: list[SkillUpdateProposal] = []
    for event in events:
        if is_failure_event(event):
            proposals.append(
                SkillUpdateProposal(
                    id=f"prop-avoid-{session_id}-{event.event_id}",
                    target=f"skill://tier1/avoid-{event.phase}-{event.action.kind}",
                    change_kind="create",
                    rationale=(
                        f"Session {session_id} hit a wrong turn at event "
                        f"{event.event_id} ({event.observation.outcome}); propose a "
                        f"pitfall-avoidance skill for {event.phase}/{event.action.kind}."
                    ),
                    diff_summary=(
                        f"create pitfall skill for {event.phase}/{event.action.kind}"
                    ),
                    evidence=_event_evidence([event]),
                    provenance=_event_provenance(session_id, event),
                    labels={"wrong_turn": [event.event_id]},
                )
            )
        elif is_success_validation_event(event):
            proposals.append(
                SkillUpdateProposal(
                    id=f"prop-useful-{session_id}-{event.event_id}",
                    target=f"skill://tier2/{event.phase}-{event.action.kind}",
                    change_kind="update",
                    rationale=(
                        f"Session {session_id} produced a useful validation at event "
                        f"{event.event_id} ({event.observation.outcome}); reinforce "
                        f"the {event.phase}/{event.action.kind} atom."
                    ),
                    diff_summary=(
                        f"reinforce atom for {event.phase}/{event.action.kind}"
                    ),
                    evidence=_event_evidence([event]),
                    provenance=_event_provenance(session_id, event),
                    labels={"useful_memory": [event.event_id]},
                )
            )
    return proposals


# ---------------------------------------------------------------------------
# Persistence (uses store write APIs; proposals -> pending only)
# ---------------------------------------------------------------------------


def _pending_proposals_dir(store: DMCStore) -> Path:
    return store.dmc_dir / "proposals" / "pending"


def _write_pending_proposal(store: DMCStore, proposal: SkillUpdateProposal) -> str:
    """Persist a proposal to ``.dmc/proposals/pending`` and return its URI.

    The store exposes no proposal-specific API, so the proposal is written to
    the canonical pending area documented in the repo layout. It is never
    written under ``.dmc/skills`` (accepted skills are not mutated here).
    """
    pending_dir = _pending_proposals_dir(store)
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
        target = pending_dir / f"{proposal.id}.yaml"
        payload = proposal.model_dump(mode="json")
        target.write_text(
            yaml.safe_dump(payload, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise DMCValidationError(
            f"failed to write pending proposal {proposal.id!r}: {exc}"
        ) from exc
    return f"proposal://pending/{proposal.id}"


def distill_session(session_id: str, store: DMCStore) -> DistillResult:
    """Distill a session into durable memory objects and persist them.

    Loads the session's events from ``store``, runs the deterministic builders,
    persists the outputs, and returns a :class:`DistillResult` with the storage
    refs. Episodes, eval cases and failure modes are written via the store's
    object API (``dmc://<kind>/<id>``); skill proposals are written to
    ``.dmc/proposals/pending`` only. Re-running is deterministic.
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("distill_session requires a non-empty session_id")

    events = store.list_events(session_id)

    episode = build_episode_card(session_id, events)
    eval_case = build_eval_case(session_id, events)
    failure_modes = propose_failure_modes(session_id, events)
    skill_proposals = propose_skill_updates(session_id, events)

    episode_uri = store.write_object("episode", episode.id, episode)
    eval_case_uri = store.write_object("eval_case", eval_case.id, eval_case)
    failure_mode_uris = [
        store.write_object("failure_mode", fm.id, fm) for fm in failure_modes
    ]
    proposal_uris = [
        _write_pending_proposal(store, proposal) for proposal in skill_proposals
    ]

    return DistillResult(
        session_id=session_id,
        episode=episode,
        eval_case=eval_case,
        failure_modes=failure_modes,
        skill_proposals=skill_proposals,
        episode_uri=episode_uri,
        eval_case_uri=eval_case_uri,
        failure_mode_uris=failure_mode_uris,
        proposal_uris=proposal_uris,
    )
