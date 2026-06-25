"""DMC local-first store (M02_STORE).

Plain files are the *source of truth* for human-editable objects; SQLite/FTS5
is an index/cache that can be fully rebuilt from those files.

Layout under ``<root>/.dmc``::

    memory/events.jsonl        append-only trace event log (JSONL)
    memory/{sessions,episodes,failure_modes,eval_cases}/
    artifacts/index.jsonl      append-only artifact index (JSONL)
    artifacts/cards/<id>.yaml   artifact card files
    artifacts/raw/
    objects/<kind>/<id>.<ext>   generic human-editable objects
    state/project_state.yaml    project state (source of truth)
    index.sqlite3              FTS5 search index (rebuildable cache)

Design rules (see ``modules/M02_STORE.md`` and ``docs/v0/02_ARCHITECTURE.md``):

* ``events.jsonl`` and ``artifacts/index.jsonl`` are append-only — prior lines
  are never rewritten.
* SQLite is never the only source of truth; deleting ``index.sqlite3`` and
  calling :meth:`DMCStore.rebuild_index` reconstructs the index from files.
* URIs use known schemes accepted by ``src/dmc/schemas.py`` (here: ``dmc://``).
* Errors are explicit DMC exceptions, never bare ``Exception`` or silent
  ``None`` for expected failures.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from dmc.schemas import (
    ArtifactCard,
    ProjectState,
    SearchResult,
    TraceEvent,
)

__all__ = [
    "DMCError",
    "DMCValidationError",
    "DMCNotFoundError",
    "DMCStorageError",
    "DMCStore",
]


# ---------------------------------------------------------------------------
# Exceptions (per docs/v0/02_ARCHITECTURE.md error handling)
# ---------------------------------------------------------------------------


class DMCError(Exception):
    """Base class for all explicit DMC store errors."""


class DMCValidationError(DMCError):
    """Raised when input is malformed (bad URI, invalid object, bad ext)."""


class DMCNotFoundError(DMCError):
    """Raised when a requested object/URI cannot be resolved to a file."""


class DMCStorageError(DMCError):
    """Raised when the underlying filesystem/SQLite store is unusable."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Supported serialization extensions for :meth:`DMCStore.write_object`.
_YAML_EXTS = frozenset({"yaml", "yml"})
_JSON_EXTS = frozenset({"json"})
_MD_EXTS = frozenset({"md", "markdown"})
_SUPPORTED_EXTS = _YAML_EXTS | _JSON_EXTS | _MD_EXTS

#: ``dmc://<kind>/<id>`` — kind is a slug-ish token, id may contain extra path
#: segments (joined back together for objects that use nested ids).
_URI_RE = re.compile(r"^dmc://(?P<kind>[A-Za-z0-9._-]+)/(?P<id>.+)$")

_KIND_PROJECT_STATE = "project_state"
_KIND_ARTIFACT = "artifact"
_KIND_EVENT = "event"


class DMCStore:
    """Local-first file + SQLite/FTS5 store.

    Parameters
    ----------
    root:
        The project root. All DMC data lives under ``<root>/.dmc``. The root
        need not exist yet; :meth:`initialize` creates the layout.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.dmc_dir = self.root / ".dmc"
        self.memory_dir = self.dmc_dir / "memory"
        self.events_path = self.memory_dir / "events.jsonl"
        self.artifacts_dir = self.dmc_dir / "artifacts"
        self.artifacts_cards_dir = self.artifacts_dir / "cards"
        self.artifacts_index_path = self.artifacts_dir / "index.jsonl"
        self.objects_dir = self.dmc_dir / "objects"
        self.state_dir = self.dmc_dir / "state"
        self.project_state_path = self.state_dir / "project_state.yaml"
        self.db_path = self.dmc_dir / "index.sqlite3"
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the ``.dmc`` layout and the SQLite/FTS5 index (idempotent)."""
        dirs = [
            self.memory_dir,
            self.memory_dir / "sessions",
            self.memory_dir / "episodes",
            self.memory_dir / "failure_modes",
            self.memory_dir / "eval_cases",
            self.artifacts_dir,
            self.artifacts_cards_dir,
            self.artifacts_dir / "raw",
            self.objects_dir,
            self.state_dir,
        ]
        try:
            for directory in dirs:
                directory.mkdir(parents=True, exist_ok=True)
            # Append-only files exist from the start (touch, never truncate).
            for path in (self.events_path, self.artifacts_index_path):
                if not path.exists():
                    path.touch()
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise DMCStorageError(f"failed to create .dmc layout: {exc}") from exc
        self._ensure_schema(self._connect())

    def close(self) -> None:
        """Close the SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            try:
                self.dmc_dir.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.db_path)
            except sqlite3.Error as exc:  # pragma: no cover
                raise DMCStorageError(f"cannot open sqlite db: {exc}") from exc
            conn.row_factory = sqlite3.Row
            self._conn = conn
            self._ensure_schema(conn)
        return self._conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5("
                "uri UNINDEXED, kind UNINDEXED, scope UNINDEXED, "
                "title, body)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS project_state_meta ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
            )
            conn.commit()
        except sqlite3.Error as exc:  # pragma: no cover
            raise DMCStorageError(f"cannot create sqlite schema: {exc}") from exc

    def _index_row(
        self,
        conn: sqlite3.Connection,
        *,
        uri: str,
        kind: str,
        scope: str,
        title: str,
        body: str,
        commit: bool = True,
    ) -> None:
        # Replace any prior row for this uri so re-writes stay consistent.
        conn.execute("DELETE FROM search_index WHERE uri = ?", (uri,))
        conn.execute(
            "INSERT INTO search_index (uri, kind, scope, title, body) "
            "VALUES (?, ?, ?, ?, ?)",
            (uri, kind, scope, title, body),
        )
        if commit:
            conn.commit()

    @staticmethod
    def _searchable_body(data: dict) -> str:
        """Flatten a dict into a whitespace-joined string for FTS indexing."""
        parts: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, sub in value.items():
                    parts.append(str(key))
                    walk(sub)
            elif isinstance(value, (list, tuple)):
                for sub in value:
                    walk(sub)
            elif value is not None:
                parts.append(str(value))

        walk(data)
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Events (append-only JSONL)
    # ------------------------------------------------------------------

    def append_event(self, event: TraceEvent) -> str:
        """Append a :class:`TraceEvent` as one JSON line; return its URI.

        ``events.jsonl`` is append-only: existing lines are never rewritten.
        """
        if not isinstance(event, TraceEvent):
            raise DMCValidationError("append_event requires a TraceEvent instance")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        payload = event.model_dump(mode="json")
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:  # pragma: no cover
            raise DMCStorageError(f"failed to append event: {exc}") from exc

        uri = f"dmc://{_KIND_EVENT}/{event.event_id}"
        conn = self._connect()
        title = f"{event.phase}: {event.intent}"
        self._index_row(
            conn,
            uri=uri,
            kind=_KIND_EVENT,
            scope="memory",
            title=title,
            body=self._searchable_body(payload),
        )
        return uri

    def list_events(self, session_id: str | None = None) -> list[TraceEvent]:
        """Return all events, optionally filtered by ``session_id`` (file order)."""
        if not self.events_path.exists():
            return []
        events: list[TraceEvent] = []
        try:
            with self.events_path.open("r", encoding="utf-8") as handle:
                for lineno, raw in enumerate(handle, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise DMCStorageError(
                            f"corrupt event line {lineno} in {self.events_path}: {exc}"
                        ) from exc
                    try:
                        event = TraceEvent.model_validate(obj)
                    except ValidationError as exc:
                        raise DMCStorageError(
                            f"invalid event at line {lineno}: {exc}"
                        ) from exc
                    if session_id is None or event.session_id == session_id:
                        events.append(event)
        except OSError as exc:  # pragma: no cover
            raise DMCStorageError(f"failed to read events: {exc}") from exc
        return events

    # ------------------------------------------------------------------
    # Generic objects (human-editable files)
    # ------------------------------------------------------------------

    def write_object(
        self,
        kind: str,
        object_id: str,
        data: BaseModel | dict,
        *,
        ext: str = "yaml",
    ) -> str:
        """Write a human-editable object file and index it; return its URI.

        ``data`` may be a Pydantic model or a plain dict. Supported ``ext``:
        ``yaml``/``yml``, ``json``, ``md``/``markdown``.
        """
        if not kind or not isinstance(kind, str):
            raise DMCValidationError("write_object requires a non-empty kind")
        if not object_id or not isinstance(object_id, str):
            raise DMCValidationError("write_object requires a non-empty object_id")
        norm_ext = ext.lower().lstrip(".")
        if norm_ext not in _SUPPORTED_EXTS:
            raise DMCValidationError(
                f"unsupported ext {ext!r}: supported are {sorted(_SUPPORTED_EXTS)}"
            )

        if isinstance(data, BaseModel):
            payload = data.model_dump(mode="json")
        elif isinstance(data, dict):
            payload = data
        else:
            raise DMCValidationError("data must be a pydantic model or a dict")

        target = self.objects_dir / kind / f"{object_id}.{norm_ext}"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._serialize(payload, norm_ext), encoding="utf-8")
        except OSError as exc:  # pragma: no cover
            raise DMCStorageError(f"failed to write object: {exc}") from exc

        uri = f"dmc://{kind}/{object_id}"
        conn = self._connect()
        title = str(payload.get("title") or payload.get("summary") or object_id)
        self._index_row(
            conn,
            uri=uri,
            kind=kind,
            scope=kind,
            title=title,
            body=self._searchable_body(payload),
        )
        return uri

    @staticmethod
    def _serialize(payload: dict, ext: str) -> str:
        if ext in _YAML_EXTS:
            return yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
        if ext in _JSON_EXTS:
            return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        # Markdown: YAML front matter so the file stays human-readable and the
        # object round-trips back to a dict via read_object.
        front = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
        return f"---\n{front}---\n"

    def read_object(self, uri: str) -> dict:
        """Resolve a ``dmc://`` URI to its file and return its parsed dict.

        Raises :class:`DMCValidationError` for malformed URIs and
        :class:`DMCNotFoundError` when no backing file exists.
        """
        if not uri or not isinstance(uri, str):
            raise DMCValidationError("read_object requires a non-empty uri string")
        match = _URI_RE.match(uri)
        if not match:
            raise DMCValidationError(
                f"invalid object uri {uri!r}: expected 'dmc://<kind>/<id>'"
            )
        kind = match.group("kind")
        obj_id = match.group("id")

        if kind == _KIND_PROJECT_STATE:
            return self._read_project_state_dict()
        if kind == _KIND_EVENT:
            return self._read_event_dict(obj_id)

        if kind == _KIND_ARTIFACT:
            candidate_dir = self.artifacts_cards_dir
        else:
            candidate_dir = self.objects_dir / kind

        path = self._find_object_file(candidate_dir, obj_id)
        if path is None:
            raise DMCNotFoundError(f"no object file found for uri {uri!r}")
        return self._deserialize(path)

    @staticmethod
    def _find_object_file(directory: Path, obj_id: str) -> Path | None:
        if not directory.exists():
            return None
        for ext in ("yaml", "yml", "json", "md", "markdown"):
            candidate = directory / f"{obj_id}.{ext}"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _deserialize(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower().lstrip(".")
        try:
            if suffix in _JSON_EXTS:
                data = json.loads(text)
            elif suffix in _MD_EXTS:
                data = DMCStore._parse_markdown_front_matter(text)
            else:
                data = yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise DMCStorageError(f"failed to parse object file {path}: {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise DMCStorageError(
                f"object file {path} did not contain a mapping (got {type(data).__name__})"
            )
        return data

    @staticmethod
    def _parse_markdown_front_matter(text: str) -> dict:
        stripped = text.lstrip()
        if stripped.startswith("---"):
            body = stripped[3:]
            end = body.find("\n---")
            if end != -1:
                front = body[:end]
                return yaml.safe_load(front) or {}
        return {"text": text}

    def _read_event_dict(self, event_id: str) -> dict:
        for event in self.list_events():
            if event.event_id == event_id:
                return event.model_dump(mode="json")
        raise DMCNotFoundError(f"no event with id {event_id!r}")

    # ------------------------------------------------------------------
    # Project state
    # ------------------------------------------------------------------

    def upsert_project_state(self, state: ProjectState) -> int:
        """Write project state (source of truth) and bump its version.

        Returns the new monotonically increasing version number.
        """
        if not isinstance(state, ProjectState):
            raise DMCValidationError("upsert_project_state requires a ProjectState")
        payload = state.model_dump(mode="json")
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.project_state_path.write_text(
                yaml.safe_dump(payload, sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover
            raise DMCStorageError(f"failed to write project state: {exc}") from exc

        conn = self._connect()
        row = conn.execute(
            "SELECT version FROM project_state_meta WHERE id = 1"
        ).fetchone()
        version = (row["version"] + 1) if row else 1
        conn.execute(
            "INSERT INTO project_state_meta (id, version) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version",
            (version,),
        )
        uri = f"dmc://{_KIND_PROJECT_STATE}/current"
        self._index_row(
            conn,
            uri=uri,
            kind=_KIND_PROJECT_STATE,
            scope="state",
            title=str(payload.get("name") or "project_state"),
            body=self._searchable_body(payload),
            commit=False,
        )
        conn.commit()
        return version

    def get_project_state(self) -> ProjectState:
        """Read project state from its source-of-truth file."""
        return ProjectState.model_validate(self._read_project_state_dict())

    def _read_project_state_dict(self) -> dict:
        if not self.project_state_path.exists():
            raise DMCNotFoundError(
                f"no project state at {self.project_state_path}"
            )
        try:
            data = yaml.safe_load(
                self.project_state_path.read_text(encoding="utf-8")
            )
        except yaml.YAMLError as exc:
            raise DMCStorageError(f"corrupt project state file: {exc}") from exc
        if not isinstance(data, dict):
            raise DMCStorageError("project state file is not a mapping")
        return data

    # ------------------------------------------------------------------
    # Artifacts (card files + append-only index)
    # ------------------------------------------------------------------

    def save_artifact_card(self, card: ArtifactCard) -> str:
        """Persist an :class:`ArtifactCard` and append to the artifact index.

        Returns the card's ``dmc://artifact/<id>`` storage URI.
        """
        if not isinstance(card, ArtifactCard):
            raise DMCValidationError("save_artifact_card requires an ArtifactCard")
        payload = card.model_dump(mode="json")
        try:
            self.artifacts_cards_dir.mkdir(parents=True, exist_ok=True)
            card_path = self.artifacts_cards_dir / f"{card.id}.yaml"
            card_path.write_text(
                yaml.safe_dump(payload, sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
            # Append-only index line.
            with self.artifacts_index_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "id": card.id,
                            "uri": card.uri,
                            "kind": card.kind,
                            "summary": card.summary,
                            "card_path": str(card_path.relative_to(self.root))
                            if self._is_relative(card_path)
                            else str(card_path),
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError as exc:  # pragma: no cover
            raise DMCStorageError(f"failed to save artifact card: {exc}") from exc

        uri = f"dmc://{_KIND_ARTIFACT}/{card.id}"
        conn = self._connect()
        self._index_row(
            conn,
            uri=uri,
            kind=_KIND_ARTIFACT,
            scope="artifacts",
            title=str(payload.get("summary") or card.id),
            body=self._searchable_body(payload),
        )
        return uri

    def _is_relative(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_text(
        self, query: str, scopes: list[str], limit: int = 10
    ) -> list[SearchResult]:
        """Full-text search (FTS5) over indexed objects/events, scoped.

        Only rows whose ``scope`` is in ``scopes`` are returned. ``limit`` caps
        the number of hits. Higher ``score`` means a better match.
        """
        if not isinstance(query, str) or not query.strip():
            raise DMCValidationError("search_text requires a non-empty query")
        if not scopes:
            raise DMCValidationError("search_text requires at least one scope")
        if limit <= 0:
            raise DMCValidationError("search_text limit must be positive")

        conn = self._connect()
        placeholders = ",".join("?" for _ in scopes)
        sql = (
            "SELECT uri, kind, scope, title, "
            "snippet(search_index, 4, '[', ']', '...', 12) AS snip, "
            "bm25(search_index) AS rank "
            "FROM search_index "
            f"WHERE search_index MATCH ? AND scope IN ({placeholders}) "
            "ORDER BY rank ASC LIMIT ?"
        )
        params: list[Any] = [self._fts_query(query), *scopes, limit]
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise DMCValidationError(f"invalid search query {query!r}: {exc}") from exc

        results: list[SearchResult] = []
        for row in rows:
            results.append(
                SearchResult(
                    uri=row["uri"],
                    score=-float(row["rank"]),
                    kind=row["kind"],
                    snippet=row["snip"],
                    title=row["title"],
                )
            )
        return results

    @staticmethod
    def _fts_query(query: str) -> str:
        """Build a safe FTS5 MATCH string by quoting each bare term."""
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        if not tokens:
            # Fall back to a quoted phrase to avoid FTS syntax errors.
            return '"' + query.replace('"', "") + '"'
        return " ".join(f'"{tok}"' for tok in tokens)

    # ------------------------------------------------------------------
    # Rebuild (SQLite is a cache; files are the source of truth)
    # ------------------------------------------------------------------

    def rebuild_index(self) -> int:
        """Rebuild the SQLite/FTS5 index entirely from files.

        Safe to call after deleting ``index.sqlite3``. Returns the number of
        indexed rows.
        """
        self.close()
        conn = self._connect()
        conn.execute("DELETE FROM search_index")
        conn.commit()
        count = 0

        # Events.
        for event in self.list_events():
            payload = event.model_dump(mode="json")
            self._index_row(
                conn,
                uri=f"dmc://{_KIND_EVENT}/{event.event_id}",
                kind=_KIND_EVENT,
                scope="memory",
                title=f"{event.phase}: {event.intent}",
                body=self._searchable_body(payload),
                commit=False,
            )
            count += 1

        # Artifact cards.
        if self.artifacts_cards_dir.exists():
            for path in sorted(self.artifacts_cards_dir.glob("*.yaml")):
                data = self._deserialize(path)
                self._index_row(
                    conn,
                    uri=f"dmc://{_KIND_ARTIFACT}/{path.stem}",
                    kind=_KIND_ARTIFACT,
                    scope="artifacts",
                    title=str(data.get("summary") or path.stem),
                    body=self._searchable_body(data),
                    commit=False,
                )
                count += 1

        # Generic objects.
        if self.objects_dir.exists():
            for path in sorted(self.objects_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower().lstrip(".") not in _SUPPORTED_EXTS:
                    continue
                kind = path.parent.relative_to(self.objects_dir).as_posix() or "object"
                data = self._deserialize(path)
                self._index_row(
                    conn,
                    uri=f"dmc://{kind}/{path.stem}",
                    kind=kind,
                    scope=kind,
                    title=str(data.get("title") or data.get("summary") or path.stem),
                    body=self._searchable_body(data),
                    commit=False,
                )
                count += 1

        # Project state.
        if self.project_state_path.exists():
            data = self._read_project_state_dict()
            self._index_row(
                conn,
                uri=f"dmc://{_KIND_PROJECT_STATE}/current",
                kind=_KIND_PROJECT_STATE,
                scope="state",
                title=str(data.get("name") or "project_state"),
                body=self._searchable_body(data),
                commit=False,
            )
            count += 1

        conn.commit()
        return count
