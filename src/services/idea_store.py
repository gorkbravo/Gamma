"""Local JSON persistence for Ideas (Workstream 12, checkpoint I1).

Layout under ``data/ideas/``::

    index.json                 derived summaries, one row per idea
    items/<idea_id>.json       the authoritative record of one idea
    quarantine/                corrupt, invalid or unsupported files, preserved
    trash/                     deleted ideas, preserved until the user clears them

It follows the existing local stores (``saved_research_store``,
``sitrep_follow_up_store``, ``copilot_store``): every write is an atomic
replace through a temporary file, a record is validated by the domain model
before it is served, a file that cannot be read is moved to quarantine with a
storage warning instead of failing the board, and older records are migrated
by ``schema_version``. The index is never trusted over the item files: it is
reused at start only when it matches every item file's size and mtime, and is
rebuilt otherwise.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.ideas import (
    CRITERION_STATES,
    EVIDENCE_STANCES,
    IDEA_SCHEMA_VERSION,
    Idea,
    IdeaValidationError,
    TRACKING_LABEL,
    assert_journal_append_only,
    assert_reviews_append_only,
    migrate_idea_v1_to_v2,
    migrate_idea_v2_to_v3,
    migrate_idea_v3_to_v4,
    migrate_idea_v4_to_v5,
)
from src.utils.time import now_utc

# Version 2 (I2) added the criteria columns to each board row; version 3 (I3a) the
# tracking headline ("forward return since activation"); version 4 (I3b) the review.
IDEA_INDEX_SCHEMA_VERSION = 4
IdeaMigration = Callable[[dict[str, Any]], dict[str, Any]]

# from_version -> function returning the payload at from_version + 1.
DEFAULT_IDEA_MIGRATIONS: dict[int, IdeaMigration] = {
    1: migrate_idea_v1_to_v2,
    2: migrate_idea_v2_to_v3,
    3: migrate_idea_v3_to_v4,
    4: migrate_idea_v4_to_v5,
}


class IdeaStoreError(RuntimeError):
    pass


class IdeaNotFoundError(IdeaStoreError):
    pass


class IdeaConflictError(IdeaStoreError):
    pass


@dataclass(frozen=True)
class IdeaStorageWarning:
    action: str
    file_name: str
    message: str
    created_at: datetime = field(default_factory=now_utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "file_name": self.file_name,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class IdeaLegSummary:
    label: str
    entity_type: str
    normalized_id: str
    weight: float | None = None


@dataclass(frozen=True)
class IdeaSummary:
    """One board row, served from the index without opening the item file."""

    idea_id: str
    title: str
    thesis: str
    stance: str
    status: str
    tags: tuple[str, ...]
    legs: tuple[IdeaLegSummary, ...]
    evidence_counts: Mapping[str, int]
    evidence_total: int
    last_evidence_at: datetime | None
    journal_count: int
    origin_kind: str
    origin_ref: str | None
    review_date: str | None
    created_at: datetime
    updated_at: datetime
    criteria_counts: Mapping[str, int] = field(default_factory=dict)
    criteria_total: int = 0
    unacknowledged_triggers: int = 0
    # Titular del seguimiento hipotético (I3a): último snapshot calculado, con su sesión ``as_of``.
    tracking: Mapping[str, Any] | None = None
    # I3b: la revisión del cierre vigente (cerrada, o archivada tras cerrar), para el modo Review.
    review: Mapping[str, Any] | None = None
    schema_version: int = IDEA_SCHEMA_VERSION

    @classmethod
    def from_idea(cls, idea: Idea) -> "IdeaSummary":
        counts = idea.evidence_counts()
        return cls(
            idea_id=idea.idea_id,
            title=idea.title,
            thesis=idea.thesis,
            stance=idea.stance,
            status=idea.status,
            tags=idea.tags,
            legs=tuple(
                IdeaLegSummary(
                    label=leg.entity.label,
                    entity_type=leg.entity.entity_type,
                    normalized_id=leg.entity.normalized_id,
                    weight=leg.weight,
                )
                for leg in idea.legs
            ),
            evidence_counts=counts,
            evidence_total=sum(counts.values()),
            last_evidence_at=idea.last_evidence_at,
            journal_count=len(idea.journal),
            origin_kind=idea.origin.kind,
            origin_ref=idea.origin.source_ref,
            review_date=idea.horizon.review_date.isoformat() if idea.horizon.review_date else None,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
            criteria_counts=idea.criteria_counts(),
            criteria_total=len(idea.criteria),
            unacknowledged_triggers=idea.unacknowledged_triggers,
            tracking=_tracking_headline(idea),
            review=_review_headline(idea),
            schema_version=idea.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "title": self.title,
            "thesis": self.thesis,
            "stance": self.stance,
            "status": self.status,
            "tags": list(self.tags),
            "legs": [
                {
                    "label": leg.label,
                    "entity_type": leg.entity_type,
                    "normalized_id": leg.normalized_id,
                    "weight": leg.weight,
                }
                for leg in self.legs
            ],
            "evidence_counts": dict(self.evidence_counts),
            "evidence_total": self.evidence_total,
            "last_evidence_at": self.last_evidence_at.isoformat() if self.last_evidence_at else None,
            "journal_count": self.journal_count,
            "origin_kind": self.origin_kind,
            "origin_ref": self.origin_ref,
            "review_date": self.review_date,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "criteria_counts": {state: int(self.criteria_counts.get(state, 0)) for state in CRITERION_STATES},
            "criteria_total": self.criteria_total,
            "unacknowledged_triggers": self.unacknowledged_triggers,
            "tracking": dict(self.tracking) if self.tracking else None,
            "review": dict(self.review) if self.review else None,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaSummary":
        counts = dict(payload.get("evidence_counts") or {})
        criteria_counts = dict(payload.get("criteria_counts") or {})
        return cls(
            idea_id=str(payload["idea_id"]),
            title=str(payload["title"]),
            thesis=str(payload.get("thesis") or ""),
            stance=str(payload["stance"]),
            status=str(payload["status"]),
            tags=tuple(str(tag) for tag in payload.get("tags") or ()),
            legs=tuple(
                IdeaLegSummary(
                    label=str(leg["label"]),
                    entity_type=str(leg["entity_type"]),
                    normalized_id=str(leg["normalized_id"]),
                    weight=None if leg.get("weight") is None else float(leg["weight"]),
                )
                for leg in payload.get("legs") or ()
            ),
            evidence_counts={stance: int(counts.get(stance) or 0) for stance in EVIDENCE_STANCES},
            evidence_total=int(payload.get("evidence_total") or 0),
            last_evidence_at=_parse_datetime(payload.get("last_evidence_at")),
            journal_count=int(payload.get("journal_count") or 0),
            origin_kind=str(payload.get("origin_kind") or "manual"),
            origin_ref=payload.get("origin_ref"),
            review_date=payload.get("review_date"),
            created_at=_parse_datetime(payload["created_at"]) or now_utc(),
            updated_at=_parse_datetime(payload["updated_at"]) or now_utc(),
            criteria_counts={state: int(criteria_counts.get(state) or 0) for state in CRITERION_STATES},
            criteria_total=int(payload.get("criteria_total") or 0),
            unacknowledged_triggers=int(payload.get("unacknowledged_triggers") or 0),
            tracking=dict(payload["tracking"]) if isinstance(payload.get("tracking"), Mapping) else None,
            review=dict(payload["review"]) if isinstance(payload.get("review"), Mapping) else None,
            schema_version=int(payload.get("schema_version") or IDEA_SCHEMA_VERSION),
        )


class IdeaStore:
    def __init__(
        self,
        base_dir: str | Path = "data/ideas",
        *,
        migrations: Mapping[int, IdeaMigration] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.items_dir = self.base_dir / "items"
        self.quarantine_dir = self.base_dir / "quarantine"
        self.trash_dir = self.base_dir / "trash"
        self.index_path = self.base_dir / "index.json"
        for directory in (self.items_dir, self.quarantine_dir, self.trash_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._migrations: dict[int, IdeaMigration] = dict(
            DEFAULT_IDEA_MIGRATIONS if migrations is None else migrations
        )
        self._lock = threading.RLock()
        self._warnings: list[IdeaStorageWarning] = []
        self._index: dict[str, IdeaSummary] = {}
        self._file_stats: dict[str, tuple[int, int]] = {}
        self.index_rebuilt = False
        with self._lock:
            self._recover_interrupted_writes_unlocked()
            if not self._load_index_unlocked():
                self._rebuild_index_unlocked()

    # -- reads ---------------------------------------------------------------

    def list_summaries(self) -> list[IdeaSummary]:
        with self._lock:
            items = list(self._index.values())
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def get(self, idea_id: str) -> Idea | None:
        safe_id = _safe_id(idea_id)
        if not safe_id:
            return None
        with self._lock:
            return self._load_item_unlocked(self.items_dir / f"{safe_id}.json")

    def require(self, idea_id: str) -> Idea:
        idea = self.get(idea_id)
        if idea is None:
            raise IdeaNotFoundError(f"Idea {idea_id} was not found.")
        return idea

    def storage_warnings(self) -> list[IdeaStorageWarning]:
        with self._lock:
            return list(self._warnings)

    # -- writes --------------------------------------------------------------

    def create(self, idea: Idea) -> Idea:
        safe_id = _safe_id(idea.idea_id)
        if safe_id != idea.idea_id:
            raise IdeaValidationError("Idea ids may only contain letters, digits, '-' and '_'.")
        with self._lock:
            path = self.items_dir / f"{safe_id}.json"
            if path.exists():
                raise IdeaConflictError(f"Idea {idea.idea_id} already exists.")
            self._write_item_unlocked(idea)
        return idea

    def update(self, idea_id: str, mutate: Callable[[Idea], Idea]) -> Idea:
        """Read, change and write one idea under the store lock.

        ``mutate`` receives the stored idea and returns its replacement. The
        replacement must keep the id and may only append to the journal.
        """
        with self._lock:
            current = self.require(idea_id)
            updated = mutate(current)
            if updated.idea_id != current.idea_id:
                raise IdeaValidationError("An update cannot change the idea id.")
            assert_journal_append_only(current.journal, updated.journal)
            assert_reviews_append_only(current.reviews, updated.reviews)
            self._write_item_unlocked(updated)
            return updated

    def delete(self, idea_id: str) -> bool:
        """Move the idea file to ``trash/``; the board stops listing it at once."""
        safe_id = _safe_id(idea_id)
        if not safe_id:
            return False
        with self._lock:
            path = self.items_dir / f"{safe_id}.json"
            # Se carga antes de mover: confirma que el fichero es exactamente esta idea
            # (un id con otra capitalización no debe borrar la real y dejar una fila fantasma).
            if self._load_item_unlocked(path) is None:
                return False
            stamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
            os.replace(path, self.trash_dir / f"{safe_id}.{stamp}.json")
            self._index.pop(safe_id, None)
            self._file_stats.pop(safe_id, None)
            self._write_index_unlocked()
        return True

    # -- internals -----------------------------------------------------------

    def _write_item_unlocked(self, idea: Idea) -> None:
        path = self.items_dir / f"{_safe_id(idea.idea_id)}.json"
        self._write_json_atomic(path, idea.to_dict())
        self._index[idea.idea_id] = IdeaSummary.from_idea(idea)
        self._file_stats[idea.idea_id] = _file_stat(path)
        self._write_index_unlocked()

    def _load_item_unlocked(self, path: Path) -> Idea | None:
        if not path.exists():
            return None
        payload = self._read_payload_unlocked(path)
        if payload is None:
            self._forget_unlocked(path.stem)
            return None
        try:
            idea = Idea.from_dict(payload)
        except Exception as exc:  # noqa: BLE001 - cualquier JSON mal formado (p. ej. AttributeError) va a cuarentena, nunca impide arrancar
            self._quarantine_unlocked(path, reason="invalid", message=f"failed validation ({exc.__class__.__name__}: {exc})")
            self._forget_unlocked(path.stem)
            return None
        if idea.idea_id != path.stem and idea.idea_id.casefold() == path.stem.casefold():
            # Sistema de ficheros sin distinción de mayúsculas (NTFS): se pidió el id con otra
            # capitalización. El fichero es válido; no se toca y se responde como no encontrado.
            return None
        if idea.idea_id != path.stem:
            self._quarantine_unlocked(path, reason="id-mismatch", message="names a different idea id than its file")
            self._forget_unlocked(path.stem)
            return None
        return idea

    def _read_payload_unlocked(self, path: Path) -> dict[str, Any] | None:
        """Parse, version-check and migrate one item file; quarantine what cannot be served."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._quarantine_unlocked(path, reason="malformed", message="is not valid JSON")
            return None
        if not isinstance(payload, dict):
            self._quarantine_unlocked(path, reason="non-object", message="is not a JSON object")
            return None
        try:
            version = int(payload.get("schema_version") or 0)
        except (TypeError, ValueError):
            version = -1
        if version > IDEA_SCHEMA_VERSION:
            # A newer Gamma wrote it: leave the file untouched and say so.
            self._warn_unlocked(
                "skipped_future_version",
                path.name,
                f"Skipped idea file {path.name}: schema version {version} is newer than this build supports "
                f"({IDEA_SCHEMA_VERSION}). The file was not changed.",
            )
            return None
        if version < IDEA_SCHEMA_VERSION:
            migrated = self._migrate_unlocked(payload, version)
            if migrated is None:
                self._quarantine_unlocked(
                    path,
                    reason=f"unsupported-v{version}",
                    message=f"uses schema version {version}, which has no migration path",
                )
                return None
            payload = migrated
            self._write_json_atomic(path, payload)
            self._warn_unlocked(
                "migrated",
                path.name,
                f"Migrated idea file {path.name} from schema version {version} to {IDEA_SCHEMA_VERSION}.",
            )
        return payload

    def _migrate_unlocked(self, payload: dict[str, Any], version: int) -> dict[str, Any] | None:
        current = dict(payload)
        while version < IDEA_SCHEMA_VERSION:
            step = self._migrations.get(version)
            if step is None:
                return None
            current = dict(step(dict(current)))
            version += 1
            current["schema_version"] = version
        return current

    def _rebuild_index_unlocked(self) -> None:
        self._index.clear()
        self._file_stats.clear()
        for path in sorted(self.items_dir.glob("*.json")):
            idea = self._load_item_unlocked(path)
            if idea is None:
                continue
            self._index[idea.idea_id] = IdeaSummary.from_idea(idea)
            self._file_stats[idea.idea_id] = _file_stat(path)
        self.index_rebuilt = True
        self._write_index_unlocked()

    def _load_index_unlocked(self) -> bool:
        """Reuse ``index.json`` only when it describes every item file exactly."""
        if not self.index_path.exists():
            return False
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            if int(payload.get("schema_version") or 0) != IDEA_INDEX_SCHEMA_VERSION:
                return False
            rows = payload.get("items")
            if not isinstance(rows, list):
                return False
            index: dict[str, IdeaSummary] = {}
            stats: dict[str, tuple[int, int]] = {}
            for row in rows:
                summary = IdeaSummary.from_dict(row["summary"])
                if summary.schema_version != IDEA_SCHEMA_VERSION:
                    return False
                index[summary.idea_id] = summary
                stats[summary.idea_id] = (int(row["file_size"]), int(row["file_mtime_ns"]))
        except Exception:
            self._warn_unlocked("index_rebuilt", self.index_path.name, "The idea index was unreadable and was rebuilt.")
            return False
        on_disk = {path.stem: _file_stat(path) for path in self.items_dir.glob("*.json")}
        if on_disk != stats:
            return False
        self._index = index
        self._file_stats = stats
        return True

    def _write_index_unlocked(self) -> None:
        rows = [
            {
                "summary": summary.to_dict(),
                "file_size": self._file_stats.get(idea_id, (0, 0))[0],
                "file_mtime_ns": self._file_stats.get(idea_id, (0, 0))[1],
            }
            for idea_id, summary in sorted(self._index.items())
        ]
        self._write_json_atomic(
            self.index_path,
            {"schema_version": IDEA_INDEX_SCHEMA_VERSION, "generated_at": now_utc().isoformat(), "items": rows},
        )

    def _forget_unlocked(self, idea_id: str) -> None:
        if self._index.pop(idea_id, None) is not None:
            self._file_stats.pop(idea_id, None)
            self._write_index_unlocked()

    def _recover_interrupted_writes_unlocked(self) -> None:
        for temp_path in sorted(self.items_dir.glob("*.tmp")):
            target = self.items_dir / f"{temp_path.name.split('.', 1)[0]}.json"
            if target.exists():
                self._quarantine_unlocked(
                    temp_path,
                    reason="interrupted-stale-temp",
                    message="was an interrupted write; the idea file itself was intact",
                )
                continue
            try:
                payload = json.loads(temp_path.read_text(encoding="utf-8"))
                Idea.from_dict(payload)
            except Exception:
                self._quarantine_unlocked(
                    temp_path,
                    reason="interrupted-invalid-temp",
                    message="was an interrupted write that could not be read",
                )
                continue
            os.replace(temp_path, target)
            self._warn_unlocked("recovered_interrupted_write", target.name, f"Recovered an interrupted write of {target.name}.")

    def _quarantine_unlocked(self, path: Path, *, reason: str, message: str) -> None:
        if not path.exists():
            return
        stamp = now_utc().strftime("%Y%m%dT%H%M%S%f")
        target = self.quarantine_dir / f"{path.name}.{reason}.{stamp}.{uuid4().hex[:8]}.preserved"
        os.replace(path, target)
        self._warn_unlocked(
            "quarantined",
            path.name,
            f"Idea file {path.name} {message}; it was moved to quarantine/{target.name} for inspection.",
        )

    def _warn_unlocked(self, action: str, file_name: str, message: str) -> None:
        self._warnings.append(IdeaStorageWarning(action=action, file_name=file_name, message=message))
        del self._warnings[:-50]

    @staticmethod
    def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
        content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{path.stem}.", suffix=".json.tmp")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _tracking_headline(idea: Idea) -> dict[str, Any] | None:
    """Board figure: the last computed snapshot plus the segment count, or ``None``."""
    tracking = idea.tracking
    if tracking is None or not tracking.segments:
        return None
    snapshot = tracking.snapshot.to_dict() if tracking.snapshot else None
    return {
        "label": TRACKING_LABEL,
        "segments": len(tracking.segments),
        "open": tracking.open_segment is not None,
        "started_at": tracking.segments[0].started_at.isoformat(),
        "snapshot": snapshot,
    }


def _clip(text: str, limit: int = 240) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _review_headline(idea: Idea) -> dict[str, Any] | None:
    """Review mode row: the review of the current close, or ``None``."""
    review = idea.current_review
    if review is None:
        return None
    first_invalidation = review.first_invalidation_at
    return {
        "review_id": review.review_id,
        "outcome": review.outcome,
        "opened_at": review.opened_at.isoformat(),
        "closed_at": review.closed_at.isoformat(),
        "holding_days": round(review.holding_days, 4),
        "expected": _clip(review.expected),
        "lesson": _clip(review.lesson),
        "invalidation_criteria": review.invalidation_criteria,
        "first_invalidation_at": first_invalidation.isoformat() if first_invalidation else None,
        "evidence_verdicts": review.verdict_counts(),
        "realized_at_close": review.realized.to_dict() if review.realized else None,
    }


def _file_stat(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return (int(stat.st_size), int(stat.st_mtime_ns))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_id(value: str | None) -> str:
    """Devuelve el id solo si ya es seguro tal cual; si no, cadena vacía.

    No elimina caracteres: ``"a/b"`` no debe convertirse en ``"ab"`` y abrir otra idea.
    """
    text = str(value or "")
    if not text or len(text) > 128:
        return ""
    if all((ch.isascii() and ch.isalnum()) or ch in {"_", "-"} for ch in text):
        return text
    return ""
