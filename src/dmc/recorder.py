"""DMC action-level event and artifact recording (M07_RECORDER).

DMC records *what happened* as structured :class:`TraceEvent` objects and
:class:`ArtifactCard` summaries. A natural-language transcript is never the
primary or only memory object — every meaningful action is a typed event.

Responsibilities (see ``modules/M07_RECORDER.md``):

* ``record_event`` — validate and append a :class:`TraceEvent` to the
  append-only ``events.jsonl`` log via :meth:`DMCStore.append_event`. The
  event ``phase`` and ``action.kind`` must come from the allowed sets; an
  invalid value raises an explicit error rather than being silently accepted.
* ``record_artifact`` — persist an :class:`ArtifactCard` via
  :meth:`DMCStore.save_artifact_card`. When a ``raw_path`` is given the raw
  bytes are copied into the store's raw artifact area
  (``.dmc/artifacts/raw/...``) and referenced by path/URI only — raw bytes are
  never inlined into JSONL.
* ``session_events`` — return all events for a session in recorded order.
* ``summarize_session_trace`` — a deterministic dict summary of a session's
  events.

Shapes are imported from ``src/dmc/schemas.py``; none are redefined here.
"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Any, get_args

from dmc.schemas import ArtifactCard, TraceEvent, TracePhase
from dmc.store import DMCStore, DMCValidationError

__all__ = [
    "ALLOWED_PHASES",
    "ALLOWED_ACTION_KINDS",
    "record_event",
    "record_artifact",
    "session_events",
    "summarize_session_trace",
]


#: The phases an event may use. Derived from the schema ``TracePhase`` literal
#: so the recorder and schema can never silently diverge. Matches the required
#: set in ``modules/M07_RECORDER.md`` (line 51).
ALLOWED_PHASES: frozenset[str] = frozenset(get_args(TracePhase))

#: The action kinds an event may use (``modules/M07_RECORDER.md`` line 57).
#: ``schemas.TraceAction.kind`` is an open non-empty string, so the recorder is
#: the authoritative gate for the allowed-kind contract.
ALLOWED_ACTION_KINDS: frozenset[str] = frozenset(
    {
        "command",
        "file_read",
        "file_edit",
        "test_run",
        "benchmark_run",
        "profiler_run",
        "asm_dump",
        "tool_call",
        "human_note",
    }
)


def record_event(event: TraceEvent, store: DMCStore) -> str:
    """Validate and record a structured :class:`TraceEvent`; return its URI.

    The event is appended to the append-only ``events.jsonl`` log via
    :meth:`DMCStore.append_event`. The event ``phase`` and ``action.kind`` must
    be members of :data:`ALLOWED_PHASES` and :data:`ALLOWED_ACTION_KINDS`
    respectively; an out-of-set value raises :class:`DMCValidationError` (the
    recorder never silently accepts an unknown phase/kind).

    Parameters
    ----------
    event:
        A fully-formed :class:`TraceEvent`. Its core fields (``session_id``,
        ``event_id``, ``phase``, ``action.kind``, ``observation.outcome``,
        ``provenance``) are already enforced by the schema at construction.
    store:
        The :class:`DMCStore` to append to.

    Returns
    -------
    str
        The ``dmc://event/<event_id>`` URI of the recorded event.
    """
    if not isinstance(event, TraceEvent):
        raise DMCValidationError("record_event requires a TraceEvent instance")
    if event.phase not in ALLOWED_PHASES:
        raise DMCValidationError(
            f"invalid event phase {event.phase!r}: "
            f"allowed phases are {sorted(ALLOWED_PHASES)}"
        )
    if event.action.kind not in ALLOWED_ACTION_KINDS:
        raise DMCValidationError(
            f"invalid action.kind {event.action.kind!r}: "
            f"allowed kinds are {sorted(ALLOWED_ACTION_KINDS)}"
        )
    return store.append_event(event)


def record_artifact(
    card: ArtifactCard, store: DMCStore, raw_path: Path | None = None
) -> str:
    """Persist an :class:`ArtifactCard`; return its ``dmc://artifact/<id>`` URI.

    The card is written via :meth:`DMCStore.save_artifact_card`, which appends a
    metadata line to the append-only ``artifacts/index.jsonl`` index.

    When ``raw_path`` is provided the raw file is copied into the store's raw
    artifact area (``.dmc/artifacts/raw/<id>/<filename>``) and referenced on the
    card by path/URI (the ``raw_artifact_path`` and ``raw_artifact_uri`` extra
    fields). Raw bytes are **never** inlined into JSONL — only the path/URI is
    stored.

    Parameters
    ----------
    card:
        The :class:`ArtifactCard` to persist.
    store:
        The :class:`DMCStore` to persist into.
    raw_path:
        Optional path to the raw artifact file to register. When ``None``, only
        the card metadata is stored.

    Returns
    -------
    str
        The ``dmc://artifact/<id>`` storage URI returned by the store.
    """
    if not isinstance(card, ArtifactCard):
        raise DMCValidationError("record_artifact requires an ArtifactCard instance")

    if raw_path is not None:
        src = Path(raw_path)
        if not src.exists() or not src.is_file():
            raise DMCValidationError(
                f"raw_path {str(src)!r} does not exist or is not a file"
            )
        raw_root = store.artifacts_dir / "raw"
        dest_dir = raw_root / card.id
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise DMCValidationError(
                f"failed to register raw artifact {str(src)!r}: {exc}"
            ) from exc

        # Reference the raw file by path/URI only (no inlined bytes). Use a
        # store-relative path when possible so the reference is portable.
        try:
            rel = dest.relative_to(store.root).as_posix()
        except ValueError:
            rel = str(dest)
        data = card.model_dump(mode="json")
        data["raw_artifact_path"] = rel
        data["raw_artifact_uri"] = dest.resolve().as_uri()
        card = ArtifactCard.model_validate(data)

    return store.save_artifact_card(card)


def session_events(session_id: str, store: DMCStore) -> list[TraceEvent]:
    """Return all :class:`TraceEvent` objects for ``session_id`` in recorded order.

    Delegates to :meth:`DMCStore.list_events`, which reads ``events.jsonl`` in
    append (file) order, so the returned list preserves recording order.
    """
    if not session_id or not isinstance(session_id, str):
        raise DMCValidationError("session_events requires a non-empty session_id")
    return store.list_events(session_id)


def _collect_artifact_refs(events: list[TraceEvent]) -> list[str]:
    """Collect unique URI-like artifact references from events, sorted.

    Walks each event's ``artifacts`` mapping and gathers any string value that
    looks like a URI (contains ``://``). Deterministic: sorted and de-duped.
    """
    refs: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for sub in value.values():
                walk(sub)
        elif isinstance(value, (list, tuple)):
            for sub in value:
                walk(sub)
        elif isinstance(value, str) and "://" in value:
            refs.add(value)

    for event in events:
        walk(event.artifacts)
    return sorted(refs)


def summarize_session_trace(session_id: str, store: DMCStore) -> dict:
    """Return a deterministic summary dict for a session's recorded events.

    The returned dict has the following shape::

        {
            "session_id": str,            # the queried session id
            "num_events": int,            # total events for the session
            "counts_by_phase": dict[str, int],        # events per phase (sorted keys)
            "counts_by_action_kind": dict[str, int],  # events per action.kind (sorted)
            "counts_by_outcome": dict[str, int],      # events per observation.outcome
            "first_timestamp": str | None,            # timestamp of first recorded event
            "last_timestamp": str | None,             # timestamp of last recorded event
            "artifact_refs": list[str],   # unique URI-like artifact refs, sorted
        }

    Counts use sorted keys and ``artifact_refs`` is sorted+de-duped, so the
    result is deterministic: calling this twice on the same store yields an
    equal dict. ``first_timestamp``/``last_timestamp`` reflect the first and
    last events in recorded (append) order; both are ``None`` for an empty
    session.
    """
    events = session_events(session_id, store)

    phase_counts = Counter(event.phase for event in events)
    kind_counts = Counter(event.action.kind for event in events)
    outcome_counts = Counter(event.observation.outcome for event in events)

    return {
        "session_id": session_id,
        "num_events": len(events),
        "counts_by_phase": dict(sorted(phase_counts.items())),
        "counts_by_action_kind": dict(sorted(kind_counts.items())),
        "counts_by_outcome": dict(sorted(outcome_counts.items())),
        "first_timestamp": events[0].timestamp if events else None,
        "last_timestamp": events[-1].timestamp if events else None,
        "artifact_refs": _collect_artifact_refs(events),
    }
