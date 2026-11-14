"""Domain model for Workstream 12 - Ideas (checkpoint I1: the core object).

An Idea joins Gamma's tabs into one research workflow: a written thesis,
evidence pinned from any tab with its provenance frozen at capture, and an
append-only journal. Criteria, tracking, tests and reviews arrive in later
checkpoints (I2-I4); the lifecycle already reserves ``closed`` and
``closed_at`` for them, but nothing in this module evaluates, tracks or
fetches anything. Every record is a frozen dataclass that carries
``schema_version`` and validates itself on construction.

See ``docs/idea_workspace_spec.md``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Any

from src.models.handoff import CrossTabHandoffEnvelope, HandoffEntity
from src.models.provenance import FreshnessRecord, ProvenanceRecord, normalize_freshness_label
from src.utils.time import now_utc

IDEA_SCHEMA_VERSION = 1

IDEA_STANCES = ("long", "short", "relative", "event", "neutral")
# ``closed`` belongs to I3 (close requires a review); it is a valid stored state
# so later checkpoints need no migration, but no I1 transition reaches it.
IDEA_STATUSES = ("draft", "active", "closed", "archived")
IDEA_I1_STATUSES = ("draft", "active", "archived")
IDEA_ORIGIN_KINDS = ("manual", "sitrep_follow_up", "copilot", "handoff", "import")

EVIDENCE_KINDS = (
    "metric",
    "series",
    "table",
    "filing",
    "news",
    "prediction_contract",
    "research_card",
    "script_output",
    "backtest",
    "risk_result",
    "note",
)
EVIDENCE_STANCES = ("supports", "challenges", "context")

JOURNAL_USER_KINDS = ("note", "decision")
JOURNAL_SYSTEM_KINDS = (
    "created",
    "edited",
    "status_changed",
    "evidence_pinned",
    "evidence_unpinned",
)
JOURNAL_KINDS = JOURNAL_USER_KINDS + JOURNAL_SYSTEM_KINDS
JOURNAL_AUTHORS = ("user", "system")

# Size bounds. Ideas are local research notes, not a data warehouse: a pin
# keeps what the user saw, small enough that a board of ideas loads instantly.
IDEA_TITLE_MAX = 200
IDEA_THESIS_MAX = 1_000
IDEA_NOTES_MAX = 20_000
IDEA_TAG_MAX = 40
IDEA_TAGS_MAX = 12
IDEA_LEGS_MAX = 24
IDEA_LEG_WEIGHT_MAX = 100.0
IDEA_HOLDING_WINDOW_MAX = 80
IDEA_EVIDENCE_MAX = 200
IDEA_JOURNAL_MAX = 2_000
ORIGIN_LABEL_MAX = 300
ORIGIN_REF_MAX = 200
EVIDENCE_TITLE_MAX = 200
EVIDENCE_NOTE_MAX = 2_000
JOURNAL_BODY_MAX = 4_000
CAPTURED_VALUES_MAX_BYTES = 24 * 1024
CAPTURED_VALUES_MAX_DEPTH = 5
CAPTURED_VALUES_MAX_ITEMS = 500
CAPTURED_STRING_MAX = 2_000
CAPTURED_SERIES_MAX_POINTS = 260

SERIES_DOWNSAMPLING_METHOD = "uniform_stride_keep_endpoints"


class IdeaValidationError(ValueError):
    """Raised when an idea record breaks a domain rule; routes answer 422."""


class IdeaLifecycleError(IdeaValidationError):
    """Raised for a lifecycle transition the current status does not allow."""


# ---------------------------------------------------------------------------
# Frozen captured values
# ---------------------------------------------------------------------------


def downsample_series_points(points: Sequence[Any], max_points: int) -> tuple[list[Any], dict[str, Any] | None]:
    """Keep at most ``max_points`` points at a uniform stride, always keeping both ends.

    Returns the kept points and a note describing the method, or ``None`` when
    the series already fits. The note is stored beside the series so the pin
    says how it was reduced instead of implying full resolution.
    """
    items = list(points)
    count = len(items)
    if max_points < 2:
        raise IdeaValidationError("A downsampled series needs room for at least two points.")
    if count <= max_points:
        return items, None
    last_index = count - 1
    indexes = sorted({round(step * last_index / (max_points - 1)) for step in range(max_points)})
    kept = [items[index] for index in indexes]
    return kept, {
        "method": SERIES_DOWNSAMPLING_METHOD,
        "original_points": count,
        "kept_points": len(kept),
    }


def prepare_captured_values(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize a raw capture before freezing: downsample an oversized series.

    The convention the frontend writes is ``metrics`` (label/value rows),
    ``table`` (columns/rows), ``series`` (label/points) and ``text``; other keys
    are allowed as long as they stay within the bounds checked by
    :func:`freeze_captured_values`.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise IdeaValidationError("captured_values must be an object.")
    prepared = dict(raw)
    series = prepared.get("series")
    if isinstance(series, Mapping):
        points = series.get("points")
        if isinstance(points, Sequence) and not isinstance(points, (str, bytes)):
            kept, note = downsample_series_points(points, CAPTURED_SERIES_MAX_POINTS)
            if note is not None:
                prepared["series"] = {**dict(series), "points": kept, "downsampling": note}
    return prepared


def freeze_captured_values(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a deeply read-only copy of ``value`` after checking its bounds.

    Mappings become ``MappingProxyType`` over a private dict, sequences become
    tuples, and only JSON scalars are accepted. Non-finite numbers are refused
    so a capture always serializes as strict JSON.
    """
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise IdeaValidationError("captured_values must be an object.")
    frozen = _freeze(value, depth=0, path="captured_values")
    size = len(json.dumps(thaw_captured_values(frozen), allow_nan=False, separators=(",", ":")).encode("utf-8"))
    if size > CAPTURED_VALUES_MAX_BYTES:
        raise IdeaValidationError(
            f"captured_values is {size} bytes; the limit is {CAPTURED_VALUES_MAX_BYTES}. "
            "Pin fewer rows or a downsampled series."
        )
    return frozen


def thaw_captured_values(value: Any) -> Any:
    """Plain, JSON-ready copy of a frozen capture."""
    if isinstance(value, Mapping):
        return {str(key): thaw_captured_values(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_captured_values(item) for item in value]
    return value


def _freeze(value: Any, *, depth: int, path: str) -> Any:
    if depth > CAPTURED_VALUES_MAX_DEPTH:
        raise IdeaValidationError(f"{path} nests deeper than {CAPTURED_VALUES_MAX_DEPTH} levels.")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IdeaValidationError(f"{path} holds a non-finite number; store it as null with a label.")
        return value
    if isinstance(value, str):
        if len(value) > CAPTURED_STRING_MAX:
            raise IdeaValidationError(f"{path} holds a string longer than {CAPTURED_STRING_MAX} characters.")
        return value
    if isinstance(value, Mapping):
        if len(value) > CAPTURED_VALUES_MAX_ITEMS:
            raise IdeaValidationError(f"{path} has more than {CAPTURED_VALUES_MAX_ITEMS} keys.")
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if not key_text.strip():
                raise IdeaValidationError(f"{path} has an empty key.")
            frozen[key_text] = _freeze(item, depth=depth + 1, path=f"{path}.{key_text}")
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > CAPTURED_VALUES_MAX_ITEMS:
            raise IdeaValidationError(f"{path} has more than {CAPTURED_VALUES_MAX_ITEMS} items.")
        return tuple(_freeze(item, depth=depth + 1, path=f"{path}[{index}]") for index, item in enumerate(value))
    raise IdeaValidationError(f"{path} holds an unsupported value of type {type(value).__name__}.")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdeaLeg:
    """An instrument the idea is about, with an optional signed weight."""

    entity: HandoffEntity
    weight: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entity, HandoffEntity):
            raise IdeaValidationError("A leg needs an entity.")
        if self.weight is not None:
            weight = float(self.weight)
            if not math.isfinite(weight) or abs(weight) > IDEA_LEG_WEIGHT_MAX:
                raise IdeaValidationError(
                    f"Leg weight must be a finite number between -{IDEA_LEG_WEIGHT_MAX:g} and {IDEA_LEG_WEIGHT_MAX:g}."
                )
            object.__setattr__(self, "weight", weight)

    def to_dict(self) -> dict[str, Any]:
        return {"entity": self.entity.to_dict(), "weight": self.weight}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaLeg":
        entity = payload.get("entity")
        if not isinstance(entity, Mapping):
            raise IdeaValidationError("A leg needs an entity.")
        weight = payload.get("weight")
        return cls(entity=_entity_from_dict(entity), weight=None if weight is None else float(weight))


@dataclass(frozen=True)
class IdeaHorizon:
    """When to look again: a review date, a holding window, or both."""

    review_date: date | None = None
    holding_window: str | None = None

    def __post_init__(self) -> None:
        if self.holding_window is not None:
            window = str(self.holding_window).strip()
            _require_max(window, IDEA_HOLDING_WINDOW_MAX, "horizon.holding_window")
            object.__setattr__(self, "holding_window", window or None)

    @property
    def is_empty(self) -> bool:
        return self.review_date is None and self.holding_window is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_date": self.review_date.isoformat() if self.review_date else None,
            "holding_window": self.holding_window,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "IdeaHorizon":
        payload = payload or {}
        return cls(
            review_date=_parse_date(payload.get("review_date")),
            holding_window=_optional_text(payload.get("holding_window")),
        )


@dataclass(frozen=True)
class IdeaOrigin:
    """Where the idea came from, with a reference back to the source object."""

    kind: str = "manual"
    source_ref: str | None = None
    label: str | None = None
    handoff: CrossTabHandoffEnvelope | None = None

    def __post_init__(self) -> None:
        if self.kind not in IDEA_ORIGIN_KINDS:
            raise IdeaValidationError(f"origin.kind must be one of {IDEA_ORIGIN_KINDS}, got {self.kind!r}.")
        if self.source_ref is not None:
            _require_max(self.source_ref, ORIGIN_REF_MAX, "origin.source_ref")
        if self.label is not None:
            _require_max(self.label, ORIGIN_LABEL_MAX, "origin.label")
        if self.handoff is not None and not isinstance(self.handoff, CrossTabHandoffEnvelope):
            raise IdeaValidationError("origin.handoff must be a cross-tab handoff envelope.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_ref": self.source_ref,
            "label": self.label,
            "handoff": self.handoff.to_dict() if self.handoff else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "IdeaOrigin":
        payload = payload or {}
        handoff = payload.get("handoff")
        return cls(
            kind=str(payload.get("kind") or "manual").strip().lower(),
            source_ref=_optional_text(payload.get("source_ref")),
            label=_optional_text(payload.get("label")),
            handoff=envelope_from_dict(handoff) if isinstance(handoff, Mapping) else None,
        )


@dataclass(frozen=True)
class IdeaEvidence:
    """A pin: a frozen snapshot of what the user saw, with provenance at capture.

    It never live-updates. ``reopen`` is the handoff that returns to the source
    tab and mode on the same entity and lens.
    """

    evidence_id: str
    idea_id: str
    kind: str
    stance: str
    title: str
    captured_values: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    provenance: ProvenanceRecord | None = None
    freshness: FreshnessRecord | None = None
    reopen: CrossTabHandoffEnvelope | None = None
    captured_at: datetime = field(default_factory=now_utc)
    note: str = ""
    schema_version: int = IDEA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        _require_text(self.idea_id, "idea_id")
        if self.kind not in EVIDENCE_KINDS:
            raise IdeaValidationError(f"Evidence kind must be one of {EVIDENCE_KINDS}, got {self.kind!r}.")
        if self.stance not in EVIDENCE_STANCES:
            raise IdeaValidationError(
                f"Evidence stance is required and must be one of {EVIDENCE_STANCES}, got {self.stance!r}."
            )
        title = str(self.title or "").strip()
        _require_text(title, "evidence title")
        _require_max(title, EVIDENCE_TITLE_MAX, "evidence title")
        object.__setattr__(self, "title", title)
        note = str(self.note or "").strip()
        _require_max(note, EVIDENCE_NOTE_MAX, "evidence note")
        object.__setattr__(self, "note", note)
        # Always hold the read-only, bounds-checked form, whatever the caller passed.
        object.__setattr__(self, "captured_values", freeze_captured_values(self.captured_values))
        if self.provenance is not None and not isinstance(self.provenance, ProvenanceRecord):
            raise IdeaValidationError("evidence provenance must be a ProvenanceRecord.")
        if self.freshness is not None and not isinstance(self.freshness, FreshnessRecord):
            raise IdeaValidationError("evidence freshness must be a FreshnessRecord.")
        if self.reopen is not None and not isinstance(self.reopen, CrossTabHandoffEnvelope):
            raise IdeaValidationError("evidence reopen must be a cross-tab handoff envelope.")
        _check_schema_version(self.schema_version)

    @property
    def entity(self) -> HandoffEntity | None:
        return self.reopen.selected_entity if self.reopen else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "idea_id": self.idea_id,
            "kind": self.kind,
            "stance": self.stance,
            "title": self.title,
            "captured_values": thaw_captured_values(self.captured_values),
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "freshness": self.freshness.to_dict() if self.freshness else None,
            "reopen": self.reopen.to_dict() if self.reopen else None,
            "captured_at": self.captured_at.isoformat(),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaEvidence":
        provenance = payload.get("provenance")
        freshness = payload.get("freshness")
        reopen = payload.get("reopen")
        captured_values = payload.get("captured_values")
        return cls(
            schema_version=_schema_version(payload.get("schema_version")),
            evidence_id=str(payload.get("evidence_id") or ""),
            idea_id=str(payload.get("idea_id") or ""),
            kind=str(payload.get("kind") or "").strip().lower(),
            stance=str(payload.get("stance") or "").strip().lower(),
            title=str(payload.get("title") or ""),
            captured_values=freeze_captured_values(captured_values if isinstance(captured_values, Mapping) else {}),
            provenance=provenance_from_dict(provenance) if isinstance(provenance, Mapping) else None,
            freshness=freshness_from_dict(freshness) if isinstance(freshness, Mapping) else None,
            reopen=envelope_from_dict(reopen) if isinstance(reopen, Mapping) else None,
            captured_at=_parse_instant(payload.get("captured_at")) or now_utc(),
            note=str(payload.get("note") or ""),
        )


@dataclass(frozen=True)
class IdeaJournalEntry:
    """One append-only journal line. Corrections are new entries, never edits."""

    entry_id: str
    idea_id: str
    kind: str
    author: str
    body: str
    created_at: datetime = field(default_factory=now_utc)
    details: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = IDEA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.entry_id, "entry_id")
        _require_text(self.idea_id, "idea_id")
        if self.kind not in JOURNAL_KINDS:
            raise IdeaValidationError(f"Journal kind must be one of {JOURNAL_KINDS}, got {self.kind!r}.")
        if self.author not in JOURNAL_AUTHORS:
            raise IdeaValidationError(f"Journal author must be one of {JOURNAL_AUTHORS}, got {self.author!r}.")
        if self.author == "user" and self.kind not in JOURNAL_USER_KINDS:
            raise IdeaValidationError(f"A user journal entry must be one of {JOURNAL_USER_KINDS}.")
        if self.author == "system" and self.kind not in JOURNAL_SYSTEM_KINDS:
            raise IdeaValidationError(f"A system journal entry must be one of {JOURNAL_SYSTEM_KINDS}.")
        body = str(self.body or "").strip()
        _require_text(body, "journal body")
        _require_max(body, JOURNAL_BODY_MAX, "journal body")
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "details", freeze_captured_values(self.details))
        _check_schema_version(self.schema_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "idea_id": self.idea_id,
            "kind": self.kind,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
            "details": thaw_captured_values(self.details),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaJournalEntry":
        details = payload.get("details")
        return cls(
            schema_version=_schema_version(payload.get("schema_version")),
            entry_id=str(payload.get("entry_id") or ""),
            idea_id=str(payload.get("idea_id") or ""),
            kind=str(payload.get("kind") or "").strip().lower(),
            author=str(payload.get("author") or "").strip().lower(),
            body=str(payload.get("body") or ""),
            created_at=_parse_instant(payload.get("created_at")) or now_utc(),
            details=freeze_captured_values(details if isinstance(details, Mapping) else {}),
        )


@dataclass(frozen=True)
class Idea:
    """A thesis with its pinned evidence and journal (I1 scope)."""

    idea_id: str
    title: str
    thesis: str = ""
    notes: str = ""
    stance: str = "neutral"
    legs: tuple[IdeaLeg, ...] = ()
    horizon: IdeaHorizon = field(default_factory=IdeaHorizon)
    status: str = "draft"
    origin: IdeaOrigin = field(default_factory=IdeaOrigin)
    tags: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    closed_at: datetime | None = None
    evidence: tuple[IdeaEvidence, ...] = ()
    journal: tuple[IdeaJournalEntry, ...] = ()
    schema_version: int = IDEA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.idea_id, "idea_id")
        title = str(self.title or "").strip()
        _require_text(title, "title")
        _require_max(title, IDEA_TITLE_MAX, "title")
        object.__setattr__(self, "title", title)
        thesis = " ".join(str(self.thesis or "").split())
        _require_max(thesis, IDEA_THESIS_MAX, "thesis")
        object.__setattr__(self, "thesis", thesis)
        notes = str(self.notes or "").strip()
        _require_max(notes, IDEA_NOTES_MAX, "notes")
        object.__setattr__(self, "notes", notes)
        if self.stance not in IDEA_STANCES:
            raise IdeaValidationError(f"stance must be one of {IDEA_STANCES}, got {self.stance!r}.")
        if self.status not in IDEA_STATUSES:
            raise IdeaValidationError(f"status must be one of {IDEA_STATUSES}, got {self.status!r}.")
        legs = tuple(self.legs)
        if len(legs) > IDEA_LEGS_MAX:
            raise IdeaValidationError(f"An idea holds at most {IDEA_LEGS_MAX} legs.")
        if any(not isinstance(leg, IdeaLeg) for leg in legs):
            raise IdeaValidationError("legs must be IdeaLeg records.")
        object.__setattr__(self, "legs", legs)
        object.__setattr__(self, "tags", normalize_tags(self.tags))
        evidence = tuple(self.evidence)
        if len(evidence) > IDEA_EVIDENCE_MAX:
            raise IdeaValidationError(f"An idea holds at most {IDEA_EVIDENCE_MAX} evidence pins.")
        for item in evidence:
            if not isinstance(item, IdeaEvidence) or item.idea_id != self.idea_id:
                raise IdeaValidationError("Every evidence pin must belong to this idea.")
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise IdeaValidationError("Evidence ids must be unique within an idea.")
        object.__setattr__(self, "evidence", evidence)
        journal = tuple(self.journal)
        if len(journal) > IDEA_JOURNAL_MAX:
            raise IdeaValidationError(f"An idea journal holds at most {IDEA_JOURNAL_MAX} entries.")
        for entry in journal:
            if not isinstance(entry, IdeaJournalEntry) or entry.idea_id != self.idea_id:
                raise IdeaValidationError("Every journal entry must belong to this idea.")
        if len({entry.entry_id for entry in journal}) != len(journal):
            raise IdeaValidationError("Journal entry ids must be unique within an idea.")
        object.__setattr__(self, "journal", journal)
        if self.status == "closed" and self.closed_at is None:
            raise IdeaValidationError("A closed idea needs closed_at.")
        _check_schema_version(self.schema_version)

    # -- derived views -----------------------------------------------------

    def evidence_counts(self) -> dict[str, int]:
        counts = {stance: 0 for stance in EVIDENCE_STANCES}
        for item in self.evidence:
            counts[item.stance] += 1
        return counts

    @property
    def last_evidence_at(self) -> datetime | None:
        return max((item.captured_at for item in self.evidence), default=None)

    # -- immutable updates --------------------------------------------------

    def with_journal_entry(self, entry: IdeaJournalEntry, *, touched_at: datetime | None = None) -> "Idea":
        """Return a copy with ``entry`` appended. The journal never shrinks."""
        if entry.idea_id != self.idea_id:
            raise IdeaValidationError("A journal entry must belong to this idea.")
        return replace(self, journal=(*self.journal, entry), updated_at=touched_at or self.updated_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "idea_id": self.idea_id,
            "title": self.title,
            "thesis": self.thesis,
            "notes": self.notes,
            "stance": self.stance,
            "legs": [leg.to_dict() for leg in self.legs],
            "horizon": self.horizon.to_dict(),
            "status": self.status,
            "origin": self.origin.to_dict(),
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "evidence": [item.to_dict() for item in self.evidence],
            "journal": [entry.to_dict() for entry in self.journal],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Idea":
        return cls(
            schema_version=_schema_version(payload.get("schema_version")),
            idea_id=str(payload.get("idea_id") or ""),
            title=str(payload.get("title") or ""),
            thesis=str(payload.get("thesis") or ""),
            notes=str(payload.get("notes") or ""),
            stance=str(payload.get("stance") or "neutral").strip().lower(),
            legs=tuple(IdeaLeg.from_dict(item) for item in _list(payload.get("legs"), "legs")),
            horizon=IdeaHorizon.from_dict(payload.get("horizon") if isinstance(payload.get("horizon"), Mapping) else None),
            status=str(payload.get("status") or "draft").strip().lower(),
            origin=IdeaOrigin.from_dict(payload.get("origin") if isinstance(payload.get("origin"), Mapping) else None),
            tags=tuple(str(item) for item in _list(payload.get("tags"), "tags")),
            created_at=_parse_instant(payload.get("created_at")) or now_utc(),
            updated_at=_parse_instant(payload.get("updated_at")) or now_utc(),
            closed_at=_parse_instant(payload.get("closed_at")),
            evidence=tuple(IdeaEvidence.from_dict(item) for item in _list(payload.get("evidence"), "evidence")),
            journal=tuple(IdeaJournalEntry.from_dict(item) for item in _list(payload.get("journal"), "journal")),
        )


# ---------------------------------------------------------------------------
# Rules shared by the store and the service
# ---------------------------------------------------------------------------


def assert_journal_append_only(previous: Sequence[IdeaJournalEntry], current: Sequence[IdeaJournalEntry]) -> None:
    """Refuse any change to an idea that edits, reorders or drops journal entries."""
    if len(current) < len(previous):
        raise IdeaValidationError("The idea journal is append-only; entries cannot be removed.")
    for index, entry in enumerate(previous):
        if current[index].to_dict() != entry.to_dict():
            raise IdeaValidationError("The idea journal is append-only; existing entries cannot be edited.")


def normalize_tags(tags: Sequence[str] | None) -> tuple[str, ...]:
    """Lower-case, trimmed, de-duplicated tags in their given order."""
    result: list[str] = []
    for raw in tags or ():
        tag = " ".join(str(raw or "").split()).lower()
        if not tag:
            continue
        _require_max(tag, IDEA_TAG_MAX, "tag")
        if tag not in result:
            result.append(tag)
    if len(result) > IDEA_TAGS_MAX:
        raise IdeaValidationError(f"An idea holds at most {IDEA_TAGS_MAX} tags.")
    return tuple(result)


def provenance_from_dict(payload: Mapping[str, Any]) -> ProvenanceRecord:
    retrieved_at = _parse_instant(payload.get("retrieved_at"))
    if retrieved_at is None:
        raise IdeaValidationError("provenance.retrieved_at is required.")
    try:
        return ProvenanceRecord(
            source_provider=str(payload.get("source_provider") or "").strip(),
            retrieved_at=retrieved_at,
            origin=str(payload.get("origin") or "").strip(),
            transformation_note=_optional_text(payload.get("transformation_note")),
        )
    except ValueError as exc:
        raise IdeaValidationError(f"provenance: {exc}") from exc


def freshness_from_dict(payload: Mapping[str, Any]) -> FreshnessRecord:
    age = payload.get("age_seconds")
    ttl = payload.get("ttl_seconds")
    return FreshnessRecord(
        label=normalize_freshness_label(payload.get("label")),
        retrieved_at=_parse_instant(payload.get("retrieved_at")),
        source_timestamp=_parse_instant(payload.get("source_timestamp")),
        evaluated_at=_parse_instant(payload.get("evaluated_at")),
        age_seconds=_finite_or_none(age),
        ttl_seconds=_finite_or_none(ttl),
        is_stale=bool(payload.get("is_stale")),
        warnings=[str(item) for item in _list(payload.get("warnings"), "freshness.warnings") if str(item or "").strip()][:20],
    )


def envelope_from_dict(payload: Mapping[str, Any]) -> CrossTabHandoffEnvelope:
    """Parse a handoff envelope, normalizing every instant to naive UTC first."""
    normalized = dict(payload)
    for key in ("timestamp",):
        normalized[key] = _iso_or_none(normalized.get(key))
    source = normalized.get("source")
    if isinstance(source, Mapping):
        normalized["source"] = {**dict(source), "retrieved_at": _iso_or_none(source.get("retrieved_at"))}
        if not normalized["source"].get("retrieved_at"):
            normalized["source"] = None
    timeframe = normalized.get("selected_timeframe")
    if isinstance(timeframe, Mapping):
        normalized["selected_timeframe"] = {
            **dict(timeframe),
            "start": _iso_or_none(timeframe.get("start")),
            "end": _iso_or_none(timeframe.get("end")),
        }
    entity = normalized.get("selected_entity")
    if isinstance(entity, Mapping):
        normalized["selected_entity"] = _entity_from_dict(entity).to_dict()
    try:
        envelope = CrossTabHandoffEnvelope.from_dict(normalized)
    except ValueError as exc:
        raise IdeaValidationError(f"handoff: {exc}") from exc
    # The envelope's own JSON must stay small and strict; reuse the capture bounds.
    freeze_captured_values(envelope.to_dict())
    return envelope


def _entity_from_dict(payload: Mapping[str, Any]) -> HandoffEntity:
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise IdeaValidationError("entity.metadata must be an object.")
    try:
        entity = HandoffEntity.from_dict(dict(payload))
    except ValueError as exc:
        raise IdeaValidationError(f"entity: {exc}") from exc
    freeze_captured_values(entity.to_dict())
    return entity


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _parse_instant(value: Any) -> datetime | None:
    """Parse an ISO instant and return naive UTC, the convention of Gamma's API."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise IdeaValidationError(f"Invalid timestamp {value!r}.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _iso_or_none(value: Any) -> str | None:
    parsed = _parse_instant(value)
    return parsed.isoformat() if parsed else None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise IdeaValidationError(f"Invalid date {value!r}; use YYYY-MM-DD.") from exc


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _list(value: Any, name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    raise IdeaValidationError(f"{name} must be a list.")


def _schema_version(value: Any) -> int:
    if value is None or value == "":
        return IDEA_SCHEMA_VERSION
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise IdeaValidationError(f"Invalid schema_version {value!r}.") from exc


def _check_schema_version(value: int) -> None:
    if value != IDEA_SCHEMA_VERSION:
        raise IdeaValidationError(
            f"Idea records must be migrated to schema version {IDEA_SCHEMA_VERSION} before use (got {value})."
        )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _require_text(value: Any, name: str) -> None:
    if not str(value or "").strip():
        raise IdeaValidationError(f"{name} is required.")


def _require_max(value: str, limit: int, name: str) -> None:
    if len(str(value)) > limit:
        raise IdeaValidationError(f"{name} is longer than {limit} characters.")
