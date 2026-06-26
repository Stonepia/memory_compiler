"""DMC local retrieval (M05_RETRIEVER).

Local retrieval over DMC-owned objects and indexes only. This is **not** repo
or source-code search — repo/code navigation belongs to external adapters
(Serena / GitHub / Sourcegraph / Basic Memory). No embeddings, no vector DB, no
arbitrary source-code indexing, no LLM.

Public API (see ``modules/M05_RETRIEVER.md``)::

    search(request: SearchRequest, store: DMCStore) -> list[SearchResult]
    rank_results(query: str, candidates: list[SearchResult]) -> list[SearchResult]
    build_context_pack(results: list[SearchResult], budget_tokens: int) -> str

Backend: :meth:`DMCStore.search_text` (SQLite FTS5) over indexed DMC objects,
then deterministic scope/filter narrowing and ranking on top.

Token budgeting uses a deterministic ~4-characters-per-token estimate
(``ceil(len(text) / 4)``); see :func:`_estimate_tokens`. ``build_context_pack``
never emits Markdown whose estimate exceeds ``budget_tokens``.
"""

from __future__ import annotations

import math
import re
from typing import Any

from dmc.schemas import SearchRequest, SearchResult
from dmc.store import DMCError, DMCStore

__all__ = [
    "SUPPORTED_SCOPES",
    "SCOPE_TO_STORE_SCOPE",
    "CHARS_PER_TOKEN",
    "search",
    "rank_results",
    "build_context_pack",
]

#: DMC search scopes accepted in a :class:`SearchRequest` (card line 49).
SUPPORTED_SCOPES: tuple[str, ...] = (
    "project_state",
    "skills",
    "knowledge",
    "artifacts",
    "episodes",
    "failure_modes",
    "eval_cases",
    "proposals",
)

#: Map a user-facing DMC search scope to the ``scope`` column(s) used by the
#: store's FTS index. ``project_state`` is indexed under ``"state"``.
#: Plural user-facing scopes (``episodes``, ``failure_modes``, ``eval_cases``,
#: ``proposals``) map to BOTH the canonical singular kind (written by M08
#: distiller) AND the legacy plural form (for backward compat with objects
#: written directly via ``write_object("episodes", ...)`` etc.).
SCOPE_TO_STORE_SCOPE: dict[str, list[str]] = {
    "project_state": ["state"],
    "skills": ["skills"],
    "knowledge": ["knowledge"],
    "artifacts": ["artifacts"],
    "episodes": ["episode", "episodes"],
    "failure_modes": ["failure_mode", "failure_modes"],
    "eval_cases": ["eval_case", "eval_cases"],
    "proposals": ["proposal", "proposals"],
}

#: Deterministic token-estimate divisor (~4 chars per token).
CHARS_PER_TOKEN = 4

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def search(request: SearchRequest, store: DMCStore) -> list[SearchResult]:
    """Search DMC objects for ``request.query`` within the requested scopes.

    Uses :meth:`DMCStore.search_text` (FTS5) as the backend, attaches
    provenance when the backing object carries it, applies optional ``filters``,
    ranks deterministically via :func:`rank_results`, and respects
    ``request.limit``.

    Unknown scopes are ignored gracefully. An empty/whitespace query or a
    request with no recognised scope yields an empty list (never an error).
    """
    query = request.query or ""
    if not query.strip():
        return []

    requested = list(request.scopes) if request.scopes else list(SUPPORTED_SCOPES)
    valid_scopes = [s for s in requested if s in SCOPE_TO_STORE_SCOPE]
    if not valid_scopes:
        # Every requested scope was unknown — clear, non-crashing behaviour.
        return []

    # Translate to store scopes (dedup, preserve order). Each user scope may
    # expand to multiple store scopes (e.g. "episodes" -> ["episode", "episodes"]).
    store_scopes: list[str] = []
    for scope in valid_scopes:
        for mapped in SCOPE_TO_STORE_SCOPE[scope]:
            if mapped not in store_scopes:
                store_scopes.append(mapped)

    limit = request.limit if request.limit and request.limit > 0 else 10
    filters = request.filters if request.filters else None

    # Fetch a few extra rows so ranking/filtering can reorder beyond the raw
    # bm25 top-N before we trim to the caller's limit.
    fetch_limit = max(limit * 4, limit, 20)
    try:
        raw = store.search_text(query, store_scopes, limit=fetch_limit)
    except DMCError:
        # Backend rejected the query/scopes — treat as no local hits.
        return []

    enriched = [_attach_provenance(result, store) for result in raw]
    filtered = [r for r in enriched if _passes_filters(r, filters)]
    ranked = rank_results(query, filtered)
    return ranked[:limit]


def _attach_provenance(result: SearchResult, store: DMCStore) -> SearchResult:
    """Return a copy of ``result`` carrying its source's provenance if any."""
    try:
        obj = store.read_object(result.uri)
    except DMCError:
        return result
    provenance = obj.get("provenance") if isinstance(obj, dict) else None
    if not provenance:
        return result
    data = result.model_dump()
    data["provenance"] = provenance
    return SearchResult(**data)


def _passes_filters(result: SearchResult, filters: Any) -> bool:
    """Deterministic narrowing by an optional ``filters`` mapping.

    Supported keys (all optional): ``kind`` (exact, case-insensitive),
    ``uri`` (substring), ``id`` (substring of the uri's final segment),
    ``tags`` (every listed tag must appear in the indexed body/snippet/title).
    Unknown filter keys are ignored. A non-mapping ``filters`` means no filter.
    """
    if not filters or not isinstance(filters, dict):
        return True

    want_kind = filters.get("kind")
    if want_kind and (result.kind or "").lower() != str(want_kind).lower():
        return False

    want_uri = filters.get("uri")
    if want_uri and str(want_uri).lower() not in result.uri.lower():
        return False

    want_id = filters.get("id")
    if want_id:
        obj_id = result.uri.rsplit("/", 1)[-1].lower()
        if str(want_id).lower() not in obj_id:
            return False

    want_tags = filters.get("tags")
    if want_tags:
        haystack = " ".join(
            part.lower()
            for part in (result.title, result.snippet, result.uri)
            if part
        )
        for tag in want_tags:
            if str(tag).lower() not in haystack:
                return False

    return True


# ---------------------------------------------------------------------------
# rank_results
# ---------------------------------------------------------------------------


def rank_results(query: str, candidates: list[SearchResult]) -> list[SearchResult]:
    """Deterministically rank ``candidates`` for ``query``.

    Ranking signals (card lines 54-60), strongest first:

    * exact ID/path match (query equals the uri or its final segment),
    * partial path / ID-token overlap,
    * scope/kind match (query mentions the result's ``kind``),
    * title text match,
    * snippet/body text match,
    * the backend FTS (bm25-derived) ``score`` as a fine tiebreaker.

    Every returned result gets a non-empty ``reason`` explaining the match, and
    any provenance carried by a candidate is preserved. Ties break on ``uri``
    ascending for stable, deterministic ordering.
    """
    scored: list[tuple[float, str, SearchResult]] = []
    for candidate in candidates:
        score, reason = _score_candidate(query, candidate)
        data = candidate.model_dump()
        data["reason"] = reason
        scored.append((score, candidate.uri, SearchResult(**data)))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [result for _, _, result in scored]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _score_candidate(query: str, candidate: SearchResult) -> tuple[float, str]:
    q = (query or "").strip().lower()
    q_tokens = _tokens(q)
    uri = candidate.uri.lower()
    obj_id = uri.rsplit("/", 1)[-1]
    kind = (candidate.kind or "").lower()
    title = (candidate.title or "").lower()
    snippet = (candidate.snippet or "").lower()

    score = 0.0
    reasons: list[str] = []

    if q and (q == obj_id or q == uri):
        score += 1000.0
        reasons.append(f"exact id/path match on {obj_id!r}")
    elif q and q in uri:
        score += 200.0
        reasons.append(f"path contains query {q!r}")

    id_overlap = q_tokens & _tokens(obj_id)
    if id_overlap:
        score += 100.0
        reasons.append("id token overlap: " + ", ".join(sorted(id_overlap)))

    if kind and (q == kind or kind in q_tokens):
        score += 80.0
        reasons.append(f"scope/kind match {kind!r}")

    title_overlap = q_tokens & _tokens(title)
    if title_overlap:
        score += 30.0
        reasons.append("title match: " + ", ".join(sorted(title_overlap)))

    snippet_overlap = q_tokens & _tokens(snippet)
    if snippet_overlap:
        score += 10.0
        reasons.append("text match: " + ", ".join(sorted(snippet_overlap)))

    # bm25-derived score from the store (higher = better) as a fine tiebreaker.
    score += float(candidate.score or 0.0)

    if not reasons:
        reasons.append(f"FTS index match for query {query!r}")

    return score, "; ".join(reasons)


# ---------------------------------------------------------------------------
# build_context_pack
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Deterministic ~4-chars/token estimate (``ceil(len(text) / 4)``)."""
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def build_context_pack(results: list[SearchResult], budget_tokens: int) -> str:
    """Render ranked ``results`` as compact Markdown within ``budget_tokens``.

    The output's estimated token count (see :func:`_estimate_tokens`) never
    exceeds ``budget_tokens``. Results are included in order until the next one
    would breach the budget; remaining results are dropped and a truncation
    notice is appended. Empty input yields a small placeholder pack. Output is
    deterministic for identical inputs.
    """
    budget = budget_tokens if budget_tokens and budget_tokens > 0 else 0

    header = "# Context Pack\n"
    if not results:
        pack = f"{header}\n_No results._\n"
        return _enforce_budget(pack, budget)

    truncation_note = "\n_…context pack truncated to fit token budget._\n"

    blocks: list[str] = [header]
    current = header
    included = 0

    for index, result in enumerate(results):
        block = _render_result_block(result, index + 1)
        candidate_text = current + block
        # Reserve room for a truncation note if more results remain.
        remaining_after = len(results) - (included + 1)
        reserve = truncation_note if remaining_after > 0 else ""
        if _estimate_tokens(candidate_text + reserve) > budget:
            break
        blocks.append(block)
        current = candidate_text
        included += 1

    if included < len(results):
        blocks.append(truncation_note)

    pack = "".join(blocks)
    return _enforce_budget(pack, budget)


def _render_result_block(result: SearchResult, position: int) -> str:
    title = result.title or result.uri
    lines = [f"\n## {position}. {title}\n"]
    lines.append(f"- uri: `{result.uri}`\n")
    lines.append(f"- kind: {result.kind}\n")
    lines.append(f"- score: {result.score:.4f}\n")
    if result.reason:
        lines.append(f"- why: {result.reason}\n")
    if result.snippet:
        lines.append(f"- snippet: {result.snippet}\n")
    provenance = getattr(result, "provenance", None)
    if provenance:
        lines.append(f"- provenance: {_format_provenance(provenance)}\n")
    return "".join(lines)


def _format_provenance(provenance: Any) -> str:
    sources: list[str] = []
    if isinstance(provenance, list):
        for entry in provenance:
            if isinstance(entry, dict):
                source = entry.get("source")
                if source:
                    sources.append(str(source))
            elif entry:
                sources.append(str(entry))
    elif isinstance(provenance, dict):
        source = provenance.get("source")
        if source:
            sources.append(str(source))
    elif provenance:
        sources.append(str(provenance))
    return ", ".join(sources) if sources else str(provenance)


def _enforce_budget(text: str, budget: int) -> str:
    """Hard guarantee the estimate never exceeds ``budget`` tokens."""
    if budget <= 0:
        return ""
    if _estimate_tokens(text) <= budget:
        return text
    # Deterministic safety net: cut to the byte budget the estimate allows.
    max_chars = budget * CHARS_PER_TOKEN
    return text[:max_chars]
