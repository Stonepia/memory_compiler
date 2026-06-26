"""DMC deterministic precheck (M06_PRECHECK).

Deterministic pre-action gates and warnings. This module contains **no LLM
calls** and no network access: every decision is a pure function of the
``PrecheckRequest`` and the contents of the local :class:`~dmc.store.DMCStore`.

Public API (see ``modules/M06_PRECHECK.md``)::

    precheck(request: PrecheckRequest, store: DMCStore) -> PrecheckResult
    load_precheck_rules(store: DMCStore) -> list[PrecheckRule]
    match_failure_modes(request: PrecheckRequest, store: DMCStore) -> list[FailureMode]

Built-in rules (all deterministic):

1. ``failure-mode-resemblance`` (warn) — the action resembles a stored
   :class:`~dmc.schemas.FailureMode`.
2. ``benchmark-claim-without-artifact`` (warn) — a perf/benchmark/speedup claim
   is made without referencing a benchmark artifact.
3. ``edit-without-task-ref`` (warn) — a file edit without a task/plan reference.
4. ``direct-skill-mutation`` (block) — a direct write to an accepted skill file
   instead of going through the proposal path.
5. ``memory-write-without-evidence`` (warn) — a durable memory/knowledge write
   without attached provenance/evidence (so missing evidence for memory writes
   is never *silently* allowed; see the module card's forbidden shortcuts).

Decision precedence: any ``block`` rule -> ``block``; else any ``warn`` rule ->
``warn``; else ``allow``.
"""

from __future__ import annotations

import re
from typing import Any

from dmc.schemas import (
    FailureMode,
    PrecheckRequest,
    PrecheckResult,
    PrecheckRule,
)
from dmc.store import DMCError, DMCStore

__all__ = [
    "BUILTIN_RULES",
    "PROPOSAL_PATH_HINT",
    "precheck",
    "load_precheck_rules",
    "match_failure_modes",
]


# ---------------------------------------------------------------------------
# Built-in rule definitions (durable contracts live in schemas.PrecheckRule)
# ---------------------------------------------------------------------------

#: Human-readable hint pointing direct skill edits at the proposal workflow.
PROPOSAL_PATH_HINT = (
    "Use the proposal path: write a SkillUpdateProposal under "
    ".dmc/proposals/pending/ instead of editing .dmc/skills/** directly."
)

RULE_FAILURE_MODE = "failure-mode-resemblance"
RULE_BENCHMARK = "benchmark-claim-without-artifact"
RULE_EDIT_NO_TASK = "edit-without-task-ref"
RULE_SKILL_MUTATION = "direct-skill-mutation"
RULE_MEMORY_NO_EVIDENCE = "memory-write-without-evidence"

#: The deterministic built-in rule set returned by :func:`load_precheck_rules`.
BUILTIN_RULES: tuple[PrecheckRule, ...] = (
    PrecheckRule(
        id=RULE_FAILURE_MODE,
        description="Warn when the action resembles a stored failure mode.",
        decision="warn",
        rationale="Repeating a recorded wrong turn wastes effort.",
    ),
    PrecheckRule(
        id=RULE_BENCHMARK,
        description=(
            "Warn when a benchmark/perf/speedup claim lacks a benchmark "
            "artifact reference."
        ),
        decision="warn",
        rationale="Performance claims require reproducible benchmark evidence.",
        required_evidence=["reference a benchmark artifact (dmc://artifact/...)"],
    ),
    PrecheckRule(
        id=RULE_EDIT_NO_TASK,
        description="Warn when editing files without a task/plan reference.",
        decision="warn",
        rationale="Edits should be traceable to a task or plan.",
        required_evidence=["reference the task/plan (task_id or plan ref)"],
    ),
    PrecheckRule(
        id=RULE_SKILL_MUTATION,
        description=(
            "Block direct mutation of an accepted skill; require the proposal "
            "path instead."
        ),
        decision="block",
        rationale="Accepted skills are immutable except via review.",
        required_evidence=[PROPOSAL_PATH_HINT],
    ),
    PrecheckRule(
        id=RULE_MEMORY_NO_EVIDENCE,
        description=(
            "Warn when a durable memory/knowledge write lacks provenance/"
            "evidence."
        ),
        decision="warn",
        rationale="Durable memory must carry provenance; never allow silently.",
        required_evidence=["attach provenance/evidence before the memory write"],
    ),
)


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

#: Common words ignored when measuring failure-mode resemblance.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "without",
        "this",
        "that",
        "from",
        "into",
        "your",
        "have",
        "when",
        "then",
        "than",
        "code",
        "file",
        "files",
        "edit",
        "edits",
        "test",
        "tests",
    }
)

_PERF_TERMS: tuple[str, ...] = (
    "benchmark",
    "perf",
    "performance",
    "speedup",
    "speed-up",
    "faster",
    "throughput",
    "latency",
    "optimiz",
    "optimis",
    "regression",
    "flops",
)

_EDIT_TERMS: tuple[str, ...] = (
    "edit",
    "write",
    "modify",
    "patch",
    "create",
    "refactor",
    "delete",
    "rewrite",
    "apply",
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) >= 4 and t not in _STOPWORDS}


def _flatten(value: Any) -> str:
    """Flatten an arbitrary JSON-ish value into a whitespace-joined string."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, sub in node.items():
                parts.append(str(key))
                walk(sub)
        elif isinstance(node, (list, tuple, set)):
            for sub in node:
                walk(sub)
        elif node is not None:
            parts.append(str(node))

    walk(value)
    return " ".join(parts)


def _request_blob(request: PrecheckRequest) -> str:
    """All free text in a request (action/command/intent/files/context)."""
    pieces = [
        request.action or "",
        request.command or "",
        request.intent or "",
        " ".join(request.files),
        _flatten(request.task_context),
    ]
    return " ".join(p for p in pieces if p)


# ---------------------------------------------------------------------------
# Failure-mode matching
# ---------------------------------------------------------------------------


def _load_failure_modes(store: DMCStore) -> list[FailureMode]:
    """Load every stored failure mode (deterministic, sorted by id).

    Failure modes are written by M08 distiller via
    ``store.write_object("failure_mode", id, FailureMode)`` to
    ``objects/failure_mode/``.  The canonical directory is ``failure_mode``
    (singular); ``failure_modes`` (plural) is a backward-compatible fallback
    for objects written before the singular convention was adopted.
    Malformed files are skipped rather than crashing the precheck.
    """
    canonical_dir = store.objects_dir / "failure_mode"
    compat_dir = store.objects_dir / "failure_modes"

    # Merge files from both directories; canonical singular wins on id collision.
    files: dict[str, tuple[str, object]] = {}  # stem -> (uri, path)
    for directory, uri_kind in ((compat_dir, "failure_modes"), (canonical_dir, "failure_mode")):
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower().lstrip(".") not in {"yaml", "yml", "json", "md", "markdown"}:
                continue
            files[path.stem] = (f"dmc://{uri_kind}/{path.stem}", path)

    modes: list[FailureMode] = []
    for stem in sorted(files):
        uri, _ = files[stem]
        try:
            data = store.read_object(uri)
            modes.append(FailureMode.model_validate(data))
        except (DMCError, ValueError):
            # Skip unreadable/invalid failure-mode files; never raise here.
            continue
    return modes


def _failure_mode_matches(request: PrecheckRequest, mode: FailureMode) -> bool:
    """Deterministic resemblance test between a request and a failure mode."""
    blob = _request_blob(request).lower()
    # Direct phrase match on the trigger is a strong signal.
    trigger = (mode.trigger or "").strip().lower()
    if trigger and trigger in blob:
        return True

    request_tokens = _significant_tokens(blob)
    mode_text = " ".join(
        part
        for part in (mode.trigger, mode.description, mode.symptom)
        if part
    )
    mode_tokens = _significant_tokens(mode_text)
    overlap = request_tokens & mode_tokens
    # Require at least two distinctive shared tokens to avoid false positives.
    return len(overlap) >= 2


def match_failure_modes(
    request: PrecheckRequest, store: DMCStore
) -> list[FailureMode]:
    """Return stored failure modes the request resembles (sorted by id).

    Deterministic: scans the local failure-mode objects and matches on trigger
    phrase containment or on >=2 distinctive shared tokens. No LLM, no network.
    """
    matched = [
        mode for mode in _load_failure_modes(store) if _failure_mode_matches(request, mode)
    ]
    return sorted(matched, key=lambda m: m.id)


# ---------------------------------------------------------------------------
# Individual rule predicates
# ---------------------------------------------------------------------------


def _is_edit_action(request: PrecheckRequest) -> bool:
    action = (request.action or "").lower()
    if any(term in action for term in _EDIT_TERMS):
        return True
    # A non-read action that names target files is treated as an edit.
    if request.files and "read" not in action and "search" not in action:
        return bool(action)
    return False


def _has_task_ref(request: PrecheckRequest) -> bool:
    ctx = request.task_context or {}
    if isinstance(ctx, dict):
        for key in ("task", "task_id", "task_ref", "plan", "plan_id", "plan_ref", "plan_graph"):
            if ctx.get(key):
                return True
    blob = _flatten(ctx).lower()
    return "plan://" in blob or "dmc://plan" in blob or "task" in blob


def _is_perf_claim(request: PrecheckRequest) -> bool:
    haystack = " ".join(
        [request.action or "", request.intent or "", request.command or ""]
    ).lower()
    return any(term in haystack for term in _PERF_TERMS)


def _has_benchmark_artifact(request: PrecheckRequest) -> bool:
    ctx = request.task_context or {}
    if isinstance(ctx, dict):
        for key in ("benchmark_artifact", "artifact", "artifacts", "benchmark", "evidence"):
            if ctx.get(key):
                return True
    blob = _flatten(ctx).lower()
    return "dmc://artifact" in blob


def _is_skill_path(path: str) -> bool:
    norm = path.replace("\\", "/").lower()
    return ".dmc/skills/" in norm or norm.startswith("skills/") or "/skills/tier" in norm


def _is_proposal_action(request: PrecheckRequest) -> bool:
    action = (request.action or "").lower()
    if "propos" in action:
        return True
    for path in request.files:
        norm = path.replace("\\", "/").lower()
        if ".dmc/proposals/" in norm:
            return True
    return False


def _is_direct_skill_mutation(request: PrecheckRequest) -> bool:
    if _is_proposal_action(request):
        return False
    if not _is_edit_action(request):
        return False
    if any(_is_skill_path(path) for path in request.files):
        return True
    action = (request.action or "").lower()
    return "skill" in action


def _is_memory_write(request: PrecheckRequest) -> bool:
    action = (request.action or "").lower()
    memory_actions = (
        "record",
        "distill",
        "commit_state",
        "write_memory",
        "save_memory",
        "save_episode",
        "save_failure",
        "save_knowledge",
        "write_knowledge",
    )
    if any(term in action for term in memory_actions):
        return True
    for path in request.files:
        norm = path.replace("\\", "/").lower()
        if ".dmc/memory/" in norm or ".dmc/knowledge/" in norm:
            return True
    return False


def _has_evidence(request: PrecheckRequest) -> bool:
    ctx = request.task_context or {}
    if isinstance(ctx, dict):
        for key in ("provenance", "evidence", "artifacts", "sources"):
            if ctx.get(key):
                return True
    blob = _flatten(ctx).lower()
    return "dmc://" in blob or "provenance" in blob


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_precheck_rules(store: DMCStore) -> list[PrecheckRule]:
    """Return the deterministic rule set used by :func:`precheck`.

    Always includes the required built-in rules. If the store holds extra rules
    under ``objects/precheck_rules/``, they are merged in (sorted by id) after
    the built-ins. No LLM is consulted.
    """
    rules: list[PrecheckRule] = list(BUILTIN_RULES)
    directory = store.objects_dir / "precheck_rules"
    if directory.exists():
        extra: list[PrecheckRule] = []
        builtin_ids = {rule.id for rule in rules}
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower().lstrip(".") not in {"yaml", "yml", "json", "md", "markdown"}:
                continue
            try:
                data = store.read_object(f"dmc://precheck_rules/{path.stem}")
                rule = PrecheckRule.model_validate(data)
            except (DMCError, ValueError):
                continue
            if rule.id not in builtin_ids:
                extra.append(rule)
        rules.extend(sorted(extra, key=lambda r: r.id))
    return rules


def precheck(request: PrecheckRequest, store: DMCStore) -> PrecheckResult:
    """Run all deterministic precheck rules and return a combined result.

    Decision precedence: any blocking rule -> ``block``; else any warning rule
    -> ``warn``; else ``allow``. ``matched_rules`` lists the ids of the rules
    that fired, ``warnings``/``reasons`` carry human-readable messages, and
    ``required_evidence_before_commit`` aggregates the evidence each fired rule
    requires. Fully deterministic: no LLM, no network.
    """
    if not isinstance(request, PrecheckRequest):
        raise TypeError("precheck requires a PrecheckRequest instance")

    matched_rules: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []
    required_evidence: list[str] = []
    has_block = False

    def fire(rule_id: str, message: str, *, evidence: list[str] | None = None) -> None:
        nonlocal has_block
        matched_rules.append(rule_id)
        reasons.append(message)
        rule = _rule_by_id(rule_id)
        if rule is not None and rule.decision == "block":
            has_block = True
        else:
            warnings.append(message)
        for item in evidence or (rule.required_evidence if rule else []):
            if item not in required_evidence:
                required_evidence.append(item)

    # Rule 1: resembles a stored failure mode.
    matches = match_failure_modes(request, store)
    if matches:
        names = ", ".join(mode.id for mode in matches)
        fire(
            RULE_FAILURE_MODE,
            f"Action resembles stored failure mode(s): {names}.",
        )

    # Rule 2: benchmark/perf claim without a benchmark artifact.
    if _is_perf_claim(request) and not _has_benchmark_artifact(request):
        fire(
            RULE_BENCHMARK,
            "Performance/benchmark claim lacks a benchmark artifact reference.",
        )

    # Rule 3: editing files without a task/plan reference.
    if _is_edit_action(request) and not _has_task_ref(request):
        fire(
            RULE_EDIT_NO_TASK,
            "Editing files without a task/plan reference.",
        )

    # Rule 4: direct mutation of an accepted skill (BLOCK).
    if _is_direct_skill_mutation(request):
        fire(
            RULE_SKILL_MUTATION,
            "Direct mutation of an accepted skill is not allowed; "
            "use the proposal path.",
        )

    # Rule 5: durable memory/knowledge write without evidence.
    if _is_memory_write(request) and not _has_evidence(request):
        fire(
            RULE_MEMORY_NO_EVIDENCE,
            "Memory/knowledge write without attached provenance/evidence.",
        )

    if has_block:
        decision = "block"
    elif matched_rules:
        decision = "warn"
    else:
        decision = "allow"

    return PrecheckResult(
        decision=decision,
        reasons=reasons,
        matched_rules=matched_rules,
        warnings=warnings,
        required_evidence_before_commit=required_evidence,
    )


def _rule_by_id(rule_id: str) -> PrecheckRule | None:
    for rule in BUILTIN_RULES:
        if rule.id == rule_id:
            return rule
    return None
