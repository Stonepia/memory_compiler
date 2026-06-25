"""Tests for src/dmc/precheck.py (M06_PRECHECK).

Deterministic precheck behaviour over a real :class:`DMCStore` (no LLM, no
network). Positive and negative cases for each built-in rule.
"""

from __future__ import annotations

from pathlib import Path

from dmc.precheck import (
    BUILTIN_RULES,
    RULE_BENCHMARK,
    RULE_EDIT_NO_TASK,
    RULE_FAILURE_MODE,
    RULE_MEMORY_NO_EVIDENCE,
    RULE_SKILL_MUTATION,
    load_precheck_rules,
    match_failure_modes,
    precheck,
)
from dmc.schemas import FailureMode, PrecheckRequest
from dmc.store import DMCStore


def _store(tmp_path: Path) -> DMCStore:
    store = DMCStore(tmp_path)
    store.initialize()
    return store


def _seed_failure_mode(store: DMCStore) -> None:
    mode = FailureMode(
        id="inductor-lowering-no-tests",
        trigger="edit inductor lowering without rerunning tests",
        description="Modifying the inductor lowering pass breaks tests silently.",
        symptom="tests pass locally but CI fails",
        avoidance="rerun the inductor test suite after lowering edits",
        provenance=[{"source": "dmc://episode/ep1"}],
    )
    store.write_object("failure_modes", mode.id, mode)


# ---------------------------------------------------------------------------
# Rule 1: resembles a stored failure mode
# ---------------------------------------------------------------------------


def test_failure_mode_resemblance_warns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_failure_mode(store)
    request = PrecheckRequest(
        action="edit",
        files=["torch/_inductor/lowering.py"],
        intent="modify the inductor lowering pass",
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert result.decision == "warn"
    assert RULE_FAILURE_MODE in result.matched_rules

    matched = match_failure_modes(request, store)
    assert [m.id for m in matched] == ["inductor-lowering-no-tests"]


def test_no_failure_mode_match_when_unrelated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_failure_mode(store)
    request = PrecheckRequest(
        action="read",
        files=["README.md"],
        intent="read project documentation",
        task_context={"task_id": "task-1"},
    )
    assert match_failure_modes(request, store) == []
    assert RULE_FAILURE_MODE not in precheck(request, store).matched_rules


# ---------------------------------------------------------------------------
# Rule 2: benchmark/perf claim without artifact
# ---------------------------------------------------------------------------


def test_benchmark_claim_without_artifact_warns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="report",
        intent="this change delivers a 2x speedup on the kernel",
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert result.decision == "warn"
    assert RULE_BENCHMARK in result.matched_rules
    assert result.required_evidence_before_commit


def test_benchmark_claim_with_artifact_does_not_warn(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="report",
        intent="this change delivers a 2x speedup on the kernel",
        task_context={
            "task_id": "task-1",
            "benchmark_artifact": "dmc://artifact/bench-001",
        },
    )
    result = precheck(request, store)
    assert RULE_BENCHMARK not in result.matched_rules


# ---------------------------------------------------------------------------
# Rule 3: file edit without task/plan reference
# ---------------------------------------------------------------------------


def test_edit_without_task_ref_warns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(action="edit", files=["src/foo.py"], task_context={})
    result = precheck(request, store)
    assert result.decision == "warn"
    assert RULE_EDIT_NO_TASK in result.matched_rules


def test_edit_with_task_ref_no_warn(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="edit",
        files=["src/foo.py"],
        task_context={"task_id": "task-42"},
    )
    result = precheck(request, store)
    assert RULE_EDIT_NO_TASK not in result.matched_rules


# ---------------------------------------------------------------------------
# Rule 4: direct mutation of an accepted skill (BLOCK)
# ---------------------------------------------------------------------------


def test_direct_skill_mutation_blocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="edit",
        files=[".dmc/skills/tier1/my_workflow.yaml"],
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert result.decision == "block"
    assert RULE_SKILL_MUTATION in result.matched_rules
    assert result.required_evidence_before_commit
    assert any("proposal" in item.lower() for item in result.required_evidence_before_commit)


def test_skill_change_via_proposal_path_not_blocked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="propose_skill_update",
        files=[".dmc/proposals/pending/p1.yaml"],
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert RULE_SKILL_MUTATION not in result.matched_rules


# ---------------------------------------------------------------------------
# Rule 5: memory write without evidence (never silently allowed)
# ---------------------------------------------------------------------------


def test_memory_write_without_evidence_warns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="record_event",
        files=[".dmc/memory/episodes/ep9.yaml"],
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert RULE_MEMORY_NO_EVIDENCE in result.matched_rules
    assert result.required_evidence_before_commit


def test_memory_write_with_evidence_no_warn(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="record_event",
        files=[".dmc/memory/episodes/ep9.yaml"],
        task_context={"task_id": "task-1", "provenance": ["dmc://event/e1"]},
    )
    result = precheck(request, store)
    assert RULE_MEMORY_NO_EVIDENCE not in result.matched_rules


# ---------------------------------------------------------------------------
# Clean allow + load_precheck_rules + determinism
# ---------------------------------------------------------------------------


def test_clean_low_risk_request_allows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="read",
        files=["README.md"],
        intent="read the project documentation",
        risk_level="low",
        task_context={"task_id": "task-1"},
    )
    result = precheck(request, store)
    assert result.decision == "allow"
    assert result.warnings == []
    assert result.matched_rules == []
    assert result.required_evidence_before_commit == []


def test_load_precheck_rules_covers_required_behaviors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rules = load_precheck_rules(store)
    by_id = {rule.id: rule for rule in rules}
    # The four required built-in rules must be represented.
    assert RULE_FAILURE_MODE in by_id
    assert RULE_BENCHMARK in by_id
    assert RULE_EDIT_NO_TASK in by_id
    assert RULE_SKILL_MUTATION in by_id
    # The skill-mutation rule must be a hard block.
    assert by_id[RULE_SKILL_MUTATION].decision == "block"
    # Built-ins are always returned.
    assert {r.id for r in BUILTIN_RULES} <= set(by_id)


def test_precheck_is_deterministic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_failure_mode(store)
    request = PrecheckRequest(
        action="edit",
        files=["torch/_inductor/lowering.py"],
        intent="modify the inductor lowering pass for a speedup",
        task_context={},
    )
    first = precheck(request, store)
    second = precheck(request, store)
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# Decision precedence: block > warn > allow
# ---------------------------------------------------------------------------


def test_block_takes_precedence_over_warn(tmp_path: Path) -> None:
    # A single request that fires BOTH a warn rule (edit without task ref) and
    # the block rule (direct mutation of an accepted skill). Block must win,
    # while the warn rule is still evaluated and reported in matched_rules.
    store = _store(tmp_path)
    request = PrecheckRequest(
        action="edit",
        files=[".dmc/skills/tier1/my_workflow.yaml"],
        task_context={},  # no task/plan ref -> edit-without-task-ref warn fires
    )
    result = precheck(request, store)
    # Sanity: both rules genuinely fired (warn rule was not short-circuited).
    assert RULE_EDIT_NO_TASK in result.matched_rules
    assert RULE_SKILL_MUTATION in result.matched_rules
    # Block beats the co-firing warn rule.
    assert result.decision == "block"


def test_warn_takes_precedence_over_allow(tmp_path: Path) -> None:
    # Exactly one warn rule fires and no block rule fires -> decision is warn,
    # never allow.
    store = _store(tmp_path)
    request = PrecheckRequest(action="edit", files=["src/foo.py"], task_context={})
    result = precheck(request, store)
    assert result.matched_rules == [RULE_EDIT_NO_TASK]
    assert RULE_SKILL_MUTATION not in result.matched_rules
    assert result.decision == "warn"
