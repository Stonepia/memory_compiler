"""Tests for action-level event and artifact recording (M07_RECORDER)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dmc.recorder import (
    ALLOWED_ACTION_KINDS,
    ALLOWED_PHASES,
    record_artifact,
    record_event,
    session_events,
    summarize_session_trace,
)
from dmc.schemas import ArtifactCard, TraceEvent
from dmc.store import DMCStore, DMCValidationError


# ---------------------------------------------------------------------------
# Builders
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


def make_artifact(artifact_id: str, summary: str = "a log") -> ArtifactCard:
    return ArtifactCard(
        id=artifact_id,
        uri=f"file:///tmp/{artifact_id}.log",
        kind="log",
        summary=summary,
        metrics={"duration_s": 1.5},
        provenance=[{"source": f"session://{artifact_id}"}],
    )


@pytest.fixture()
def store(tmp_path: Path) -> DMCStore:
    s = DMCStore(tmp_path)
    s.initialize()
    return s


# ---------------------------------------------------------------------------
# record_event / session_events
# ---------------------------------------------------------------------------


def test_record_event_then_session_events_returns_it(store: DMCStore) -> None:
    uri = record_event(make_event("e1", "sessA"), store)
    assert uri == "dmc://event/e1"
    events = session_events("sessA", store)
    assert len(events) == 1
    assert events[0].event_id == "e1"


def test_record_event_preserves_order_across_phases_and_kinds(store: DMCStore) -> None:
    seeded = [
        make_event("e1", "sessA", phase="localize", kind="file_read"),
        make_event("e2", "sessA", phase="edit", kind="file_edit"),
        make_event("e3", "sessA", phase="test", kind="test_run"),
        make_event("e4", "sessA", phase="benchmark", kind="benchmark_run"),
    ]
    for event in seeded:
        record_event(event, store)
    got = session_events("sessA", store)
    assert [e.event_id for e in got] == ["e1", "e2", "e3", "e4"]
    assert [e.phase for e in got] == ["localize", "edit", "test", "benchmark"]
    assert [e.action.kind for e in got] == [
        "file_read",
        "file_edit",
        "test_run",
        "benchmark_run",
    ]


def test_events_jsonl_is_append_only(store: DMCStore) -> None:
    record_event(make_event("e1", "sessA"), store)
    first = store.events_path.read_text(encoding="utf-8")
    record_event(make_event("e2", "sessA"), store)
    second = store.events_path.read_text(encoding="utf-8")
    # The original line is unchanged and still the prefix of the new content.
    assert second.startswith(first)
    assert second.count("\n") == 2


def test_all_required_phases_and_kinds_accepted(store: DMCStore) -> None:
    # Every required phase and action kind is accepted by record_event.
    phases = sorted(ALLOWED_PHASES)
    kinds = sorted(ALLOWED_ACTION_KINDS)
    for i, phase in enumerate(phases):
        record_event(make_event(f"p{i}", "sessP", phase=phase), store)
    for i, kind in enumerate(kinds):
        record_event(make_event(f"k{i}", "sessK", kind=kind), store)
    assert len(session_events("sessP", store)) == len(phases)
    assert len(session_events("sessK", store)) == len(kinds)


def test_record_event_rejects_non_event(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        record_event({"event_id": "e1"}, store)  # type: ignore[arg-type]


def test_record_event_rejects_disallowed_action_kind(store: DMCStore) -> None:
    # The schema allows any non-empty action.kind, so the recorder is the gate.
    bad = make_event("ebad", "sessA")
    bad.action.kind = "definitely_not_allowed"
    with pytest.raises(DMCValidationError):
        record_event(bad, store)
    # Nothing was written.
    assert session_events("sessA", store) == []


def test_record_event_rejects_disallowed_phase_at_construction() -> None:
    # The schema constrains phase to the allowed literal set, so building an
    # event with a disallowed phase fails before it can ever be recorded.
    with pytest.raises(ValidationError):
        make_event("ebad", "sessA", phase="deploy")


# ---------------------------------------------------------------------------
# record_artifact
# ---------------------------------------------------------------------------


def test_record_artifact_card_only(store: DMCStore) -> None:
    uri = record_artifact(make_artifact("art1"), store)
    assert uri == "dmc://artifact/art1"
    index = store.artifacts_index_path.read_text(encoding="utf-8")
    assert "art1" in index


def test_record_artifact_with_raw_path_registers_and_does_not_inline(
    store: DMCStore, tmp_path: Path
) -> None:
    raw_marker = "RAW_BYTES_THAT_MUST_NOT_BE_INLINED_0xDEADBEEF"
    raw_src = tmp_path / "profile.txt"
    raw_src.write_text(raw_marker, encoding="utf-8")

    uri = record_artifact(make_artifact("art2"), store, raw_path=raw_src)
    assert uri == "dmc://artifact/art2"

    # Raw file copied under the store raw area.
    registered = store.artifacts_dir / "raw" / "art2" / "profile.txt"
    assert registered.exists()
    assert registered.read_text(encoding="utf-8") == raw_marker

    # The card references the raw file by portable path/URI — never a
    # machine-absolute file:// path (docs/v0/review.md §10).
    card_data = store.read_object("dmc://artifact/art2")
    assert card_data["raw_artifact_path"] == ".dmc/artifacts/raw/art2/profile.txt"
    assert card_data["raw_artifact_uri"] == "dmc://artifact/raw/art2/profile.txt"

    # The append-only index JSONL never contains the raw bytes.
    index_text = store.artifacts_index_path.read_text(encoding="utf-8")
    assert raw_marker not in index_text
    # Neither does the events log or the card file itself.
    card_file = (store.artifacts_cards_dir / "art2.yaml").read_text(encoding="utf-8")
    assert raw_marker not in card_file


def test_record_artifact_uses_portable_dmc_uri(store: DMCStore, tmp_path: Path) -> None:
    """No absolute file:// URI is ever persisted in durable memory (§10)."""
    raw_src = tmp_path / "trace.log"
    raw_src.write_text("some raw bytes", encoding="utf-8")

    record_artifact(make_artifact("art9"), store, raw_path=raw_src)
    card_data = store.read_object("dmc://artifact/art9")

    assert card_data["raw_artifact_uri"] == "dmc://artifact/raw/art9/trace.log"
    assert not card_data["raw_artifact_uri"].startswith("file://")
    assert not Path(card_data["raw_artifact_path"]).is_absolute()

    # The raw artifact card file on disk must not contain an absolute path either.
    card_file = (store.artifacts_cards_dir / "art9.yaml").read_text(encoding="utf-8")
    assert "file://" not in card_file
    assert str(tmp_path) not in card_file


def test_record_artifact_rejects_missing_raw_path(store: DMCStore, tmp_path: Path) -> None:
    with pytest.raises(DMCValidationError):
        record_artifact(make_artifact("art3"), store, raw_path=tmp_path / "nope.txt")


def test_record_artifact_rejects_non_card(store: DMCStore) -> None:
    with pytest.raises(DMCValidationError):
        record_artifact({"id": "x"}, store)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# summarize_session_trace
# ---------------------------------------------------------------------------


def _seed_known_session(store: DMCStore) -> None:
    record_event(
        make_event(
            "e1",
            "sessS",
            phase="localize",
            kind="file_read",
            outcome="success",
            timestamp="2026-06-25T00:00:01Z",
            artifacts={"log": "dmc://artifact/run1"},
        ),
        store,
    )
    record_event(
        make_event(
            "e2",
            "sessS",
            phase="test",
            kind="test_run",
            outcome="failure",
            timestamp="2026-06-25T00:00:02Z",
        ),
        store,
    )
    record_event(
        make_event(
            "e3",
            "sessS",
            phase="test",
            kind="test_run",
            outcome="success",
            timestamp="2026-06-25T00:00:03Z",
            artifacts={"refs": ["dmc://artifact/run2", "dmc://artifact/run1"]},
        ),
        store,
    )


def test_summarize_session_trace_counts(store: DMCStore) -> None:
    _seed_known_session(store)
    summary = summarize_session_trace("sessS", store)
    assert summary["session_id"] == "sessS"
    assert summary["num_events"] == 3
    assert summary["counts_by_phase"] == {"localize": 1, "test": 2}
    assert summary["counts_by_action_kind"] == {"file_read": 1, "test_run": 2}
    assert summary["counts_by_outcome"] == {"failure": 1, "success": 2}
    assert summary["first_timestamp"] == "2026-06-25T00:00:01Z"
    assert summary["last_timestamp"] == "2026-06-25T00:00:03Z"
    assert summary["artifact_refs"] == [
        "dmc://artifact/run1",
        "dmc://artifact/run2",
    ]


def test_summarize_session_trace_is_deterministic(store: DMCStore) -> None:
    _seed_known_session(store)
    assert summarize_session_trace("sessS", store) == summarize_session_trace(
        "sessS", store
    )


def test_summarize_empty_session(store: DMCStore) -> None:
    summary = summarize_session_trace("nobody", store)
    assert summary["num_events"] == 0
    assert summary["counts_by_phase"] == {}
    assert summary["first_timestamp"] is None
    assert summary["last_timestamp"] is None
    assert summary["artifact_refs"] == []


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


def test_session_isolation(store: DMCStore) -> None:
    record_event(make_event("a1", "sessA"), store)
    record_event(make_event("b1", "sessB"), store)
    record_event(make_event("a2", "sessA"), store)
    a_events = session_events("sessA", store)
    b_events = session_events("sessB", store)
    assert [e.event_id for e in a_events] == ["a1", "a2"]
    assert [e.event_id for e in b_events] == ["b1"]
    assert summarize_session_trace("sessA", store)["num_events"] == 2
    assert summarize_session_trace("sessB", store)["num_events"] == 1
