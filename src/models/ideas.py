"""Domain model for Workstream 12 - Ideas (checkpoints I1, I2, I3a and I3b).

An Idea joins Gamma's tabs into one research workflow: a written thesis,
evidence pinned from any tab with its provenance frozen at capture, criteria
stated before the outcome is known, and an append-only journal. Tracking,
tests and reviews arrive in later checkpoints (I3-I4); the lifecycle already
reserves ``closed`` and ``closed_at`` for them. Nothing in this module fetches
anything: a criterion stores the rule and the last evaluation it was given by
the evaluation service. Every record is a frozen dataclass that carries
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

# Version 2 (I2) added ``criteria``; version 1 files migrate on load
# (``migrate_idea_v1_to_v2``), so an older build skips them instead of dropping criteria.
# Version 3 (I3a) added ``tracking`` (``migrate_idea_v2_to_v3``).
# Version 4 (I3b) added ``reviews`` (``migrate_idea_v3_to_v4``).
IDEA_SCHEMA_VERSION = 4

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
    "criterion_added",
    "criterion_edited",
    "criterion_removed",
    "criterion_triggered",
    "criterion_acknowledged",
    # I3a: apertura y cierre de segmentos de seguimiento, y cambios de supuestos (costes, benchmark).
    "tracking_segment",
    "tracking_settings",
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

# Criteria (I2). A criterion is a rule stated before the outcome is known.
CRITERION_KINDS = ("invalidate", "confirm", "review")
CRITERION_CONDITIONS = (
    "above",
    "below",
    "crosses_above",
    "crosses_below",
    "change_over_window",
    "date_reached",
    "event_occurs",
)
CRITERION_THRESHOLD_CONDITIONS = ("above", "below", "crosses_above", "crosses_below", "change_over_window")
CRITERION_CADENCES = ("on_open", "daily_close", "intraday")
# ``pending`` means never evaluated (or edited since); evaluation outcomes are the other four.
CRITERION_STATES = ("pending", "holding", "triggered", "unavailable", "stale")
CRITERION_EVALUATION_STATES = ("holding", "triggered", "unavailable", "stale")
# Look-back windows for ``change_over_window``, in calendar days.
CRITERION_WINDOWS = {"1d": 1, "5d": 5, "1m": 30, "3m": 91, "6m": 182, "1y": 365}
IDEA_CRITERIA_MAX = 12
CRITERION_LABEL_MAX = 200
CRITERION_REASON_MAX = 500
CRITERION_DISPLAY_MAX = 80
OBSERVABLE_ID_MAX = 60
OBSERVABLE_PARAMS_MAX = 8
OBSERVABLE_PARAM_KEY_MAX = 40
OBSERVABLE_PARAM_VALUE_MAX = 200
OBSERVABLE_LABEL_MAX = 160
CRITERION_WARNINGS_MAX = 10

# Forward tracking (I3a). The record is a hypothetical book: nothing here is an order.
TRACKING_LABEL = "Hypothetical, not executed"
# Leg types this slice can price from provider closes (research market data and CoinGecko).
TRACKED_ENTITY_TYPES = ("equity", "etf", "crypto")
TRACKING_ASSET_CLASSES = (
    "us_equity_liquid",
    "equity_other",
    "futures",
    "options",
    "crypto_spot",
    "prediction_contract",
    "non_tradable",
)
# Classes whose cost is a stated number of basis points per side (editable). Options and
# prediction contracts take half the quoted spread from a live quote; non-tradable has none.
TRACKING_BP_CLASSES = ("us_equity_liquid", "equity_other", "futures", "crypto_spot")
# Per-side defaults (decision 5). Assumptions checked against official fee schedules on
# 2026-11-21; see docs/idea_workspace_spec.md (Default cost model). The spec's starting
# values were 10 bp for other equities and 25 bp for crypto: the official schedules put
# IBKR's European commission alone at 5 bp (minimum EUR 3) and entry-tier crypto taker
# fees at 50-90 bp (Coinbase Advanced, Kraken Pro), so both were raised.
DEFAULT_TRACKING_COST_BP: dict[str, float] = {
    "us_equity_liquid": 5.0,
    "equity_other": 15.0,
    "futures": 3.0,
    "crypto_spot": 50.0,
}
TRACKING_COST_BP_MAX = 500.0
TRACKING_START_REASONS = ("activated", "legs_edited", "legs_added", "restored", "reopened", "migrated")
TRACKING_END_REASONS = ("legs_edited", "legs_removed", "archived", "closed")
TRACKING_STATUSES = ("not_started", "waiting", "tracking", "stopped", "unavailable")
TRACKING_WEIGHT_SOURCES = ("stated", "stance")
TRACKING_SEGMENTS_MAX = 200
TRACKING_NOTE_MAX = 500
TRACKING_BENCHMARK_MAX = 24
DEFAULT_TRACKING_BENCHMARK = "SPY"

# Close and review (I3b). Closing requires a review; reviews only grow.
REVIEW_OUTCOMES = ("confirmed", "invalidated", "abandoned", "expired")
EVIDENCE_VERDICTS = ("held", "failed", "unclear")
REVIEW_TEXT_MAX = 4_000
REVIEW_LESSON_MIN = 3
IDEA_REVIEWS_MAX = 50

# Exchange suffixes (Yahoo style) with the local closing time Gamma uses for each market.
# Times are at or before the official close: a session whose close might precede the
# activation is skipped rather than used, so a price known before activation never enters.
# A suffix not listed here falls back to the conservative ``unknown`` market (see
# ``application/idea_tracking.py``); one letter after a dot is a US share class (BRK.B).
TRACKING_EXCHANGES: dict[str, tuple[str, str, int, int]] = {
    # suffijo: (mercado, zona horaria, hora, minuto) del cierre local
    "L": ("lse", "Europe/London", 16, 30),
    "IL": ("lse", "Europe/London", 16, 30),
    "DE": ("xetra", "Europe/Berlin", 17, 30),
    "PA": ("euronext_paris", "Europe/Paris", 17, 30),
    "AS": ("euronext_amsterdam", "Europe/Amsterdam", 17, 30),
    "BR": ("euronext_brussels", "Europe/Brussels", 17, 30),
    "LS": ("euronext_lisbon", "Europe/Lisbon", 16, 30),
    "MI": ("borsa_italiana", "Europe/Rome", 17, 30),
    "MC": ("bme", "Europe/Madrid", 17, 30),
    "SW": ("six", "Europe/Zurich", 17, 20),
    "ST": ("nasdaq_stockholm", "Europe/Stockholm", 17, 25),
    "CO": ("nasdaq_copenhagen", "Europe/Copenhagen", 16, 55),
    "HE": ("nasdaq_helsinki", "Europe/Helsinki", 18, 25),
    "OL": ("oslo", "Europe/Oslo", 16, 20),
    "TO": ("tsx", "America/Toronto", 16, 0),
    "V": ("tsxv", "America/Toronto", 16, 0),
    "T": ("tse", "Asia/Tokyo", 15, 25),
    "HK": ("hkex", "Asia/Hong_Kong", 16, 0),
    "AX": ("asx", "Australia/Sydney", 16, 0),
}


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
class ObservableRef:
    """A reference into the observable registry: which observable, on what.

    ``params`` are short strings the registry validates (a ticker, a series id,
    a venue and contract id, a date). ``label`` is the display name the user saw
    when the criterion was written, e.g. "XOM close".
    """

    observable_id: str
    params: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    label: str = ""

    def __post_init__(self) -> None:
        observable_id = str(self.observable_id or "").strip().lower()
        _require_text(observable_id, "observable id")
        _require_max(observable_id, OBSERVABLE_ID_MAX, "observable id")
        object.__setattr__(self, "observable_id", observable_id)
        raw = self.params or {}
        if not isinstance(raw, Mapping):
            raise IdeaValidationError("observable params must be an object.")
        if len(raw) > OBSERVABLE_PARAMS_MAX:
            raise IdeaValidationError(f"An observable takes at most {OBSERVABLE_PARAMS_MAX} params.")
        params: dict[str, str] = {}
        for key, value in raw.items():
            key_text = str(key or "").strip()
            _require_text(key_text, "observable param name")
            _require_max(key_text, OBSERVABLE_PARAM_KEY_MAX, "observable param name")
            if value is None:
                continue
            value_text = str(value).strip()
            _require_max(value_text, OBSERVABLE_PARAM_VALUE_MAX, f"observable param {key_text}")
            if value_text:
                params[key_text] = value_text
        object.__setattr__(self, "params", MappingProxyType(dict(sorted(params.items()))))
        label = " ".join(str(self.label or "").split())
        _require_max(label, OBSERVABLE_LABEL_MAX, "observable label")
        object.__setattr__(self, "label", label or observable_id)

    @property
    def key(self) -> str:
        """Stable identity of the reading, so one pass reads each observable once."""
        return self.observable_id + "|" + json.dumps(dict(self.params), sort_keys=True, separators=(",", ":"))

    def to_dict(self) -> dict[str, Any]:
        return {"observable_id": self.observable_id, "params": dict(self.params), "label": self.label}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservableRef":
        params = payload.get("params")
        if params is not None and not isinstance(params, Mapping):
            raise IdeaValidationError("observable params must be an object.")
        return cls(
            observable_id=str(payload.get("observable_id") or ""),
            params=dict(params or {}),
            label=str(payload.get("label") or ""),
        )


@dataclass(frozen=True)
class CriterionEvaluation:
    """The outcome of one evaluation, kept on the criterion until the next one.

    ``state`` is never ``pending``. ``unavailable`` carries ``reason`` and never
    a condition result: missing data is not evidence that the thesis holds.
    ``first_met_at`` is when the condition was first met, from the observable's
    history when it has one (the "while you were away" time), otherwise the
    time of the evaluation that found it. ``value`` is the latest observation;
    ``met_value`` is the observation that met the condition, which can be an
    earlier close than the latest one.
    """

    state: str
    evaluated_at: datetime
    value: float | None = None
    value_display: str | None = None
    as_of: datetime | None = None
    met_value: float | None = None
    met_display: str | None = None
    reference_value: float | None = None
    change: float | None = None
    first_met_at: datetime | None = None
    reason: str | None = None
    effective_cadence: str = "on_open"
    cadence_note: str | None = None
    provenance: ProvenanceRecord | None = None
    warnings: tuple[str, ...] = ()
    # Solo ``event_occurs``: el evento ya estaba resuelto en la primera lectura tras armar
    # la regla, así que no es una observación nueva y la regla no puede dispararse.
    known_at_arming: bool = False

    def __post_init__(self) -> None:
        if self.state not in CRITERION_EVALUATION_STATES:
            raise IdeaValidationError(
                f"An evaluation state must be one of {CRITERION_EVALUATION_STATES}, got {self.state!r}."
            )
        if self.effective_cadence not in CRITERION_CADENCES:
            raise IdeaValidationError(f"effective_cadence must be one of {CRITERION_CADENCES}.")
        for name in ("value", "reference_value", "change", "met_value"):
            number = getattr(self, name)
            if number is not None:
                finite = _finite_or_none(number)
                if finite is None:
                    raise IdeaValidationError(f"evaluation {name} must be a finite number.")
                object.__setattr__(self, name, finite)
        if self.state == "unavailable" and not str(self.reason or "").strip():
            raise IdeaValidationError("An unavailable evaluation needs the reason.")
        for name, limit in (
            ("reason", CRITERION_REASON_MAX),
            ("cadence_note", CRITERION_REASON_MAX),
            ("value_display", CRITERION_DISPLAY_MAX),
            ("met_display", CRITERION_DISPLAY_MAX),
        ):
            text = _optional_text(getattr(self, name))
            if text is not None:
                text = text[:limit]
            object.__setattr__(self, name, text)
        if self.provenance is not None and not isinstance(self.provenance, ProvenanceRecord):
            raise IdeaValidationError("evaluation provenance must be a ProvenanceRecord.")
        warnings = tuple(str(item).strip()[:CRITERION_REASON_MAX] for item in self.warnings if str(item or "").strip())
        object.__setattr__(self, "warnings", warnings[:CRITERION_WARNINGS_MAX])

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "evaluated_at": self.evaluated_at.isoformat(),
            "value": self.value,
            "value_display": self.value_display,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "met_value": self.met_value,
            "met_display": self.met_display,
            "reference_value": self.reference_value,
            "change": self.change,
            "first_met_at": self.first_met_at.isoformat() if self.first_met_at else None,
            "reason": self.reason,
            "effective_cadence": self.effective_cadence,
            "cadence_note": self.cadence_note,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "warnings": list(self.warnings),
            "known_at_arming": self.known_at_arming,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CriterionEvaluation":
        provenance = payload.get("provenance")
        return cls(
            state=str(payload.get("state") or "").strip().lower(),
            evaluated_at=_parse_instant(payload.get("evaluated_at")) or now_utc(),
            value=_finite_or_none(payload.get("value")),
            value_display=_optional_text(payload.get("value_display")),
            as_of=_parse_instant(payload.get("as_of")),
            met_value=_finite_or_none(payload.get("met_value")),
            met_display=_optional_text(payload.get("met_display")),
            reference_value=_finite_or_none(payload.get("reference_value")),
            change=_finite_or_none(payload.get("change")),
            first_met_at=_parse_instant(payload.get("first_met_at")),
            reason=_optional_text(payload.get("reason")),
            effective_cadence=str(payload.get("effective_cadence") or "on_open").strip().lower(),
            cadence_note=_optional_text(payload.get("cadence_note")),
            provenance=provenance_from_dict(provenance) if isinstance(provenance, Mapping) else None,
            warnings=tuple(str(item) for item in _list(payload.get("warnings"), "evaluation.warnings")),
            # Ausente en ficheros anteriores al 2026-11-21: equivale a False.
            known_at_arming=payload.get("known_at_arming") is True,
        )


@dataclass(frozen=True)
class IdeaCriterion:
    """A rule stated before the outcome is known (I2).

    ``armed_at`` is when the rule was last set (created or edited); evaluation
    only counts observations from then on, and from the idea's activation.
    ``baseline_as_of`` is the newest observation already known at the first
    evaluation after that moment (``baseline_for``): later observations count
    even when they are dated earlier, because lagging series (FRED daily
    yields, monthly prints dated by their reference period) publish after the
    date they carry. A trigger latches: ``triggered_at`` (when Gamma detected it) and
    ``trigger_evaluation`` (the reading that met the condition, with the date it
    was first met and its provenance) stay until the rule is edited, even if the
    condition later stops holding, because the trigger is a fact about the
    thesis. ``acknowledged_at`` only clears the notification.
    """

    criterion_id: str
    idea_id: str
    kind: str
    label: str
    observable: ObservableRef
    condition: str
    threshold: float | None = None
    window: str | None = None
    cadence: str = "daily_close"
    last_evaluation: CriterionEvaluation | None = None
    trigger_evaluation: CriterionEvaluation | None = None
    triggered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    armed_at: datetime = field(default_factory=now_utc)
    created_at: datetime = field(default_factory=now_utc)
    baseline_as_of: datetime | None = None
    baseline_for: datetime | None = None
    schema_version: int = IDEA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "criterion_id")
        if (self.baseline_as_of is None) != (self.baseline_for is None):
            raise IdeaValidationError("A criterion baseline needs both baseline_as_of and baseline_for.")
        _require_text(self.idea_id, "idea_id")
        if self.kind not in CRITERION_KINDS:
            raise IdeaValidationError(f"Criterion kind must be one of {CRITERION_KINDS}, got {self.kind!r}.")
        label = " ".join(str(self.label or "").split())
        _require_text(label, "criterion label")
        _require_max(label, CRITERION_LABEL_MAX, "criterion label")
        object.__setattr__(self, "label", label)
        if not isinstance(self.observable, ObservableRef):
            raise IdeaValidationError("A criterion needs an observable.")
        if self.condition not in CRITERION_CONDITIONS:
            raise IdeaValidationError(f"condition must be one of {CRITERION_CONDITIONS}, got {self.condition!r}.")
        if self.condition in CRITERION_THRESHOLD_CONDITIONS:
            threshold = _finite_or_none(self.threshold)
            if threshold is None:
                raise IdeaValidationError(f"The {self.condition} condition needs a finite threshold.")
            if self.condition == "change_over_window" and threshold == 0:
                raise IdeaValidationError("A change threshold cannot be zero; use a signed rise or fall.")
            object.__setattr__(self, "threshold", threshold)
        elif self.threshold is not None:
            raise IdeaValidationError(f"The {self.condition} condition takes no threshold.")
        if self.condition == "change_over_window":
            if self.window not in CRITERION_WINDOWS:
                raise IdeaValidationError(f"change_over_window needs a window in {tuple(CRITERION_WINDOWS)}.")
        elif self.window is not None:
            raise IdeaValidationError(f"The {self.condition} condition takes no window.")
        if self.cadence not in CRITERION_CADENCES:
            raise IdeaValidationError(f"cadence must be one of {CRITERION_CADENCES}, got {self.cadence!r}.")
        if self.last_evaluation is not None and not isinstance(self.last_evaluation, CriterionEvaluation):
            raise IdeaValidationError("last_evaluation must be a CriterionEvaluation.")
        if self.trigger_evaluation is not None:
            if not isinstance(self.trigger_evaluation, CriterionEvaluation) or self.trigger_evaluation.state != "triggered":
                raise IdeaValidationError("trigger_evaluation must be the triggering evaluation.")
            if self.triggered_at is None:
                raise IdeaValidationError("A trigger evaluation needs triggered_at.")
        if self.acknowledged_at is not None and self.triggered_at is None:
            raise IdeaValidationError("Only a triggered criterion can be acknowledged.")
        _check_schema_version(self.schema_version)

    @property
    def state(self) -> str:
        """Latched trigger first, then the last evaluation, else ``pending``."""
        if self.triggered_at is not None:
            return "triggered"
        if self.last_evaluation is None:
            return "pending"
        return self.last_evaluation.state

    @property
    def needs_acknowledgement(self) -> bool:
        return self.triggered_at is not None and self.acknowledged_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "criterion_id": self.criterion_id,
            "idea_id": self.idea_id,
            "kind": self.kind,
            "label": self.label,
            "observable": self.observable.to_dict(),
            "condition": self.condition,
            "threshold": self.threshold,
            "window": self.window,
            "cadence": self.cadence,
            "state": self.state,
            "last_evaluation": self.last_evaluation.to_dict() if self.last_evaluation else None,
            "trigger_evaluation": self.trigger_evaluation.to_dict() if self.trigger_evaluation else None,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "armed_at": self.armed_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "baseline_as_of": self.baseline_as_of.isoformat() if self.baseline_as_of else None,
            "baseline_for": self.baseline_for.isoformat() if self.baseline_for else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaCriterion":
        observable = payload.get("observable")
        if not isinstance(observable, Mapping):
            raise IdeaValidationError("A criterion needs an observable.")
        last_evaluation = payload.get("last_evaluation")
        trigger_evaluation = payload.get("trigger_evaluation")
        window = payload.get("window")
        created_at = _parse_instant(payload.get("created_at")) or now_utc()
        return cls(
            schema_version=_schema_version(payload.get("schema_version")),
            criterion_id=str(payload.get("criterion_id") or ""),
            idea_id=str(payload.get("idea_id") or ""),
            kind=str(payload.get("kind") or "").strip().lower(),
            label=str(payload.get("label") or ""),
            observable=ObservableRef.from_dict(observable),
            condition=str(payload.get("condition") or "").strip().lower(),
            threshold=None if payload.get("threshold") is None else _finite_or_none(payload.get("threshold")),
            window=None if window in (None, "") else str(window).strip().lower(),
            cadence=str(payload.get("cadence") or "daily_close").strip().lower(),
            last_evaluation=CriterionEvaluation.from_dict(last_evaluation) if isinstance(last_evaluation, Mapping) else None,
            trigger_evaluation=(
                CriterionEvaluation.from_dict(trigger_evaluation) if isinstance(trigger_evaluation, Mapping) else None
            ),
            triggered_at=_parse_instant(payload.get("triggered_at")),
            acknowledged_at=_parse_instant(payload.get("acknowledged_at")),
            armed_at=_parse_instant(payload.get("armed_at")) or created_at,
            created_at=created_at,
            baseline_as_of=_parse_instant(payload.get("baseline_as_of")),
            baseline_for=_parse_instant(payload.get("baseline_for")),
        )


# ---------------------------------------------------------------------------
# Forward tracking (I3a)
# ---------------------------------------------------------------------------


def tracking_leg_key(entity: HandoffEntity) -> str:
    """Stable identity of a leg for the cost model: type and id, case-insensitive."""
    return f"{str(entity.entity_type).strip().lower()}:{str(entity.normalized_id).strip().upper()}"


def tracking_market(entity: HandoffEntity) -> str:
    """The market whose calendar and closing time price this leg.

    ``crypto`` trades every day; ``us`` is the default for a listing without an
    exchange suffix (or with a one-letter share class such as BRK.B); a known
    suffix maps to its exchange; any other suffix is ``unknown``.
    """
    entity_type = str(entity.entity_type).strip().lower()
    if entity_type == "crypto":
        return "crypto"
    symbol = str(entity.normalized_id).strip().upper()
    if "." not in symbol:
        return "us"
    suffix = symbol.rsplit(".", 1)[1]
    if suffix in TRACKING_EXCHANGES:
        return TRACKING_EXCHANGES[suffix][0]
    if len(suffix) == 1 and suffix.isalpha():
        return "us"
    return "unknown"


def default_tracking_asset_class(entity: HandoffEntity) -> str:
    """Asset class for the default cost: a guess the user can override per leg."""
    entity_type = str(entity.entity_type).strip().lower()
    if entity_type in {"equity", "etf"}:
        return "us_equity_liquid" if tracking_market(entity) == "us" else "equity_other"
    if entity_type == "crypto":
        return "crypto_spot"
    if entity_type == "commodity":
        return "futures"
    if entity_type == "prediction_market":
        return "prediction_contract"
    return "non_tradable"


@dataclass(frozen=True)
class IdeaTrackedLeg:
    """A leg as frozen when its tracking segment opened.

    ``weight`` is the signed share of gross exposure (the absolute weights of a
    segment add up to 1); ``None`` when the segment cannot be tracked.
    ``stated_weight`` is what the user wrote; ``weight_source`` says whether the
    weight came from it or from the stance (an equal-weight long or short book).
    """

    entity: HandoffEntity
    stated_weight: float | None = None
    weight: float | None = None
    weight_source: str = "stated"
    asset_class: str = "non_tradable"
    market: str = "us"

    def __post_init__(self) -> None:
        if not isinstance(self.entity, HandoffEntity):
            raise IdeaValidationError("A tracked leg needs an entity.")
        for name in ("stated_weight", "weight"):
            value = getattr(self, name)
            if value is not None:
                number = _finite_or_none(value)
                if number is None:
                    raise IdeaValidationError(f"tracked leg {name} must be a finite number.")
                object.__setattr__(self, name, number)
        if self.weight is not None and abs(self.weight) > 1.0 + 1e-9:
            raise IdeaValidationError("A tracked leg weight is a share of gross exposure, between -1 and 1.")
        if self.weight_source not in TRACKING_WEIGHT_SOURCES:
            raise IdeaValidationError(f"weight_source must be one of {TRACKING_WEIGHT_SOURCES}.")
        if self.asset_class not in TRACKING_ASSET_CLASSES:
            raise IdeaValidationError(f"asset_class must be one of {TRACKING_ASSET_CLASSES}.")
        market = str(self.market or "").strip().lower()
        _require_text(market, "tracked leg market")
        object.__setattr__(self, "market", market)

    @property
    def key(self) -> str:
        return tracking_leg_key(self.entity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity.to_dict(),
            "stated_weight": self.stated_weight,
            "weight": self.weight,
            "weight_source": self.weight_source,
            "asset_class": self.asset_class,
            "market": self.market,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaTrackedLeg":
        entity = payload.get("entity")
        if not isinstance(entity, Mapping):
            raise IdeaValidationError("A tracked leg needs an entity.")
        return cls(
            entity=_entity_from_dict(entity),
            stated_weight=_finite_or_none(payload.get("stated_weight")),
            weight=_finite_or_none(payload.get("weight")),
            weight_source=str(payload.get("weight_source") or "stated").strip().lower(),
            asset_class=str(payload.get("asset_class") or "non_tradable").strip().lower(),
            market=str(payload.get("market") or "us"),
        )


@dataclass(frozen=True)
class IdeaTrackingSegment:
    """One stretch of the hypothetical book with fixed legs and weights.

    A segment opens when the legs are frozen (activation, a leg edit, a restore)
    and closes when they change again or the idea stops being active. Its book
    enters at the first close after ``started_at`` and, once ended, exits at the
    first close after ``ended_at``; nothing before ``started_at`` is ever used.
    ``untracked_reason`` says why the segment has no book (a leg type this slice
    cannot price, or weights that do not define one); the period stays visible.
    """

    segment_id: str
    number: int
    started_at: datetime
    start_reason: str
    legs: tuple[IdeaTrackedLeg, ...] = ()
    stance: str = "neutral"
    start_note: str = ""
    ended_at: datetime | None = None
    end_reason: str | None = None
    end_note: str = ""
    untracked_reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.segment_id, "segment_id")
        if int(self.number) < 1:
            raise IdeaValidationError("Tracking segments are numbered from 1.")
        object.__setattr__(self, "number", int(self.number))
        if self.start_reason not in TRACKING_START_REASONS:
            raise IdeaValidationError(f"start_reason must be one of {TRACKING_START_REASONS}, got {self.start_reason!r}.")
        if self.stance not in IDEA_STANCES:
            raise IdeaValidationError(f"segment stance must be one of {IDEA_STANCES}.")
        legs = tuple(self.legs)
        if not legs:
            raise IdeaValidationError("A tracking segment needs at least one leg.")
        if len(legs) > IDEA_LEGS_MAX:
            raise IdeaValidationError(f"A tracking segment holds at most {IDEA_LEGS_MAX} legs.")
        if any(not isinstance(leg, IdeaTrackedLeg) for leg in legs):
            raise IdeaValidationError("Segment legs must be IdeaTrackedLeg records.")
        object.__setattr__(self, "legs", legs)
        if (self.ended_at is None) != (self.end_reason is None):
            raise IdeaValidationError("An ended segment needs both ended_at and end_reason.")
        if self.end_reason is not None and self.end_reason not in TRACKING_END_REASONS:
            raise IdeaValidationError(f"end_reason must be one of {TRACKING_END_REASONS}, got {self.end_reason!r}.")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise IdeaValidationError("A segment cannot end before it starts.")
        for name in ("start_note", "end_note"):
            text = " ".join(str(getattr(self, name) or "").split())
            object.__setattr__(self, name, text[:TRACKING_NOTE_MAX])
        reason = _optional_text(self.untracked_reason)
        object.__setattr__(self, "untracked_reason", reason[:TRACKING_NOTE_MAX] if reason else None)
        if reason is None and any(leg.weight is None for leg in legs):
            raise IdeaValidationError("A tracked segment needs a weight on every leg.")

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    def closed(self, at: datetime, reason: str, note: str = "") -> "IdeaTrackingSegment":
        return replace(self, ended_at=at, end_reason=reason, end_note=note)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "number": self.number,
            "started_at": self.started_at.isoformat(),
            "start_reason": self.start_reason,
            "start_note": self.start_note,
            "stance": self.stance,
            "legs": [leg.to_dict() for leg in self.legs],
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "end_reason": self.end_reason,
            "end_note": self.end_note,
            "untracked_reason": self.untracked_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaTrackingSegment":
        started_at = _parse_instant(payload.get("started_at"))
        if started_at is None:
            raise IdeaValidationError("A tracking segment needs started_at.")
        return cls(
            segment_id=str(payload.get("segment_id") or ""),
            number=int(payload.get("number") or 0),
            started_at=started_at,
            start_reason=str(payload.get("start_reason") or "").strip().lower(),
            start_note=str(payload.get("start_note") or ""),
            stance=str(payload.get("stance") or "neutral").strip().lower(),
            legs=tuple(IdeaTrackedLeg.from_dict(item) for item in _list(payload.get("legs"), "segment.legs")),
            ended_at=_parse_instant(payload.get("ended_at")),
            end_reason=_optional_text(payload.get("end_reason")),
            end_note=str(payload.get("end_note") or ""),
            untracked_reason=_optional_text(payload.get("untracked_reason")),
        )


@dataclass(frozen=True)
class IdeaCostModel:
    """Per-side cost assumptions by asset class, plus per-leg class overrides.

    The gross record never depends on it; the net record is the gross record
    minus these costs, so changing an assumption is visible and journaled but
    cannot rewrite what the prices did.
    """

    per_side_bp: Mapping[str, float] = field(default_factory=lambda: MappingProxyType(dict(DEFAULT_TRACKING_COST_BP)))
    leg_classes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        raw = dict(self.per_side_bp or {})
        unknown = sorted(set(raw) - set(TRACKING_BP_CLASSES))
        if unknown:
            raise IdeaValidationError(f"Costs take basis points for {TRACKING_BP_CLASSES}; not {', '.join(unknown)}.")
        values: dict[str, float] = {}
        for asset_class in TRACKING_BP_CLASSES:
            number = _finite_or_none(raw.get(asset_class, DEFAULT_TRACKING_COST_BP[asset_class]))
            if number is None or number < 0 or number > TRACKING_COST_BP_MAX:
                raise IdeaValidationError(
                    f"The {asset_class} cost must be between 0 and {TRACKING_COST_BP_MAX:g} bp per side."
                )
            values[asset_class] = number
        object.__setattr__(self, "per_side_bp", MappingProxyType(values))
        overrides: dict[str, str] = {}
        raw_overrides = dict(self.leg_classes or {})
        if len(raw_overrides) > IDEA_LEGS_MAX * 4:
            raise IdeaValidationError("Too many per-leg cost classes.")
        for key, value in raw_overrides.items():
            key_text = str(key or "").strip()
            _require_text(key_text, "leg class key")
            _require_max(key_text, OBSERVABLE_PARAM_VALUE_MAX, "leg class key")
            asset_class = str(value or "").strip().lower()
            if asset_class not in TRACKING_ASSET_CLASSES:
                raise IdeaValidationError(f"A leg class must be one of {TRACKING_ASSET_CLASSES}, got {value!r}.")
            overrides[key_text] = asset_class
        object.__setattr__(self, "leg_classes", MappingProxyType(dict(sorted(overrides.items()))))

    def class_for(self, leg: IdeaTrackedLeg) -> str:
        return self.leg_classes.get(leg.key, leg.asset_class)

    def bp_for(self, asset_class: str) -> float | None:
        """Per-side basis points; ``None`` where the cost comes from a live quote."""
        if asset_class in self.per_side_bp:
            return float(self.per_side_bp[asset_class])
        if asset_class == "non_tradable":
            return 0.0
        return None

    @property
    def edited(self) -> bool:
        return dict(self.per_side_bp) != DEFAULT_TRACKING_COST_BP or bool(self.leg_classes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_side_bp": dict(self.per_side_bp),
            "leg_classes": dict(self.leg_classes),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "IdeaCostModel":
        payload = payload or {}
        per_side = payload.get("per_side_bp")
        leg_classes = payload.get("leg_classes")
        return cls(
            per_side_bp=dict(per_side) if isinstance(per_side, Mapping) else dict(DEFAULT_TRACKING_COST_BP),
            leg_classes=dict(leg_classes) if isinstance(leg_classes, Mapping) else {},
            updated_at=_parse_instant(payload.get("updated_at")),
        )


@dataclass(frozen=True)
class IdeaTrackingSnapshot:
    """The last computed headline of the canonical series, kept for the Board.

    It is derived data, refreshed whenever the series is rebuilt; the Board
    shows it with its ``as_of`` session so a stale figure is never mistaken for
    today's.
    """

    status: str
    computed_at: datetime
    as_of: date | None = None
    net_return: float | None = None
    gross_return: float | None = None
    benchmark_return: float | None = None
    benchmark: str | None = None
    sessions: int = 0
    gaps: int = 0
    partial: bool = False
    # I3b: no hay segmento abierto ni salida pendiente; la cifra ya no cambiará.
    final: bool = False

    def __post_init__(self) -> None:
        if self.status not in TRACKING_STATUSES:
            raise IdeaValidationError(f"tracking status must be one of {TRACKING_STATUSES}, got {self.status!r}.")
        for name in ("net_return", "gross_return", "benchmark_return"):
            value = getattr(self, name)
            if value is not None:
                number = _finite_or_none(value)
                if number is None:
                    raise IdeaValidationError(f"snapshot {name} must be a finite number.")
                object.__setattr__(self, name, number)
        object.__setattr__(self, "sessions", max(0, int(self.sessions)))
        object.__setattr__(self, "gaps", max(0, int(self.gaps)))

    def same_figures(self, other: "IdeaTrackingSnapshot | None") -> bool:
        """Equal apart from ``computed_at``: no need to rewrite the idea file."""
        if other is None:
            return False
        mine = self.to_dict()
        theirs = other.to_dict()
        mine.pop("computed_at")
        theirs.pop("computed_at")
        return mine == theirs

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "computed_at": self.computed_at.isoformat(),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "net_return": self.net_return,
            "gross_return": self.gross_return,
            "benchmark_return": self.benchmark_return,
            "benchmark": self.benchmark,
            "sessions": self.sessions,
            "gaps": self.gaps,
            "partial": self.partial,
            "final": self.final,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaTrackingSnapshot":
        return cls(
            status=str(payload.get("status") or "not_started").strip().lower(),
            computed_at=_parse_instant(payload.get("computed_at")) or now_utc(),
            as_of=_parse_date(payload.get("as_of")),
            net_return=_finite_or_none(payload.get("net_return")),
            gross_return=_finite_or_none(payload.get("gross_return")),
            benchmark_return=_finite_or_none(payload.get("benchmark_return")),
            benchmark=_optional_text(payload.get("benchmark")),
            sessions=int(payload.get("sessions") or 0),
            gaps=int(payload.get("gaps") or 0),
            partial=payload.get("partial") is True,
            final=payload.get("final") is True,
        )


@dataclass(frozen=True)
class IdeaTracking:
    """The hypothetical forward record of an idea with legs (I3a).

    ``segments`` only grow: a closed segment is never edited or removed, and at
    most the last one is open. The canonical daily series is not stored; it is
    rebuilt from provider closes (``application/idea_tracking.py``), so it has
    no holes when Gamma was closed. ``snapshot`` keeps the last headline for the
    Board.
    """

    benchmark: str = DEFAULT_TRACKING_BENCHMARK
    cost_model: IdeaCostModel = field(default_factory=IdeaCostModel)
    segments: tuple[IdeaTrackingSegment, ...] = ()
    snapshot: IdeaTrackingSnapshot | None = None

    def __post_init__(self) -> None:
        benchmark = str(self.benchmark or "").strip().upper()
        _require_text(benchmark, "benchmark")
        _require_max(benchmark, TRACKING_BENCHMARK_MAX, "benchmark")
        if any(char.isspace() for char in benchmark):
            raise IdeaValidationError("Use a ticker such as SPY for the benchmark.")
        object.__setattr__(self, "benchmark", benchmark)
        if not isinstance(self.cost_model, IdeaCostModel):
            raise IdeaValidationError("tracking cost_model must be an IdeaCostModel.")
        segments = tuple(self.segments)
        if len(segments) > TRACKING_SEGMENTS_MAX:
            raise IdeaValidationError(f"A tracking record holds at most {TRACKING_SEGMENTS_MAX} segments.")
        for index, segment in enumerate(segments):
            if not isinstance(segment, IdeaTrackingSegment):
                raise IdeaValidationError("Tracking segments must be IdeaTrackingSegment records.")
            if segment.number != index + 1:
                raise IdeaValidationError("Tracking segments are numbered 1, 2, 3… in order.")
            if segment.is_open and index != len(segments) - 1:
                raise IdeaValidationError("Only the last tracking segment can be open.")
            if index and segment.started_at < (segments[index - 1].ended_at or segments[index - 1].started_at):
                raise IdeaValidationError("A tracking segment cannot start before the previous one ended.")
        if len({segment.segment_id for segment in segments}) != len(segments):
            raise IdeaValidationError("Tracking segment ids must be unique.")
        object.__setattr__(self, "segments", segments)
        if self.snapshot is not None and not isinstance(self.snapshot, IdeaTrackingSnapshot):
            raise IdeaValidationError("tracking snapshot must be an IdeaTrackingSnapshot.")

    @property
    def open_segment(self) -> IdeaTrackingSegment | None:
        if self.segments and self.segments[-1].is_open:
            return self.segments[-1]
        return None

    def with_open_segment(
        self, *, legs: Sequence[IdeaLeg], stance: str, at: datetime, reason: str, note: str = ""
    ) -> "IdeaTracking":
        """Append a new open segment with ``legs`` frozen at ``at``. The last one must be closed."""
        if self.open_segment is not None:
            raise IdeaValidationError("Close the open tracking segment before opening another.")
        frozen, untracked = freeze_tracking_legs(legs, stance)
        number = len(self.segments) + 1
        segment = IdeaTrackingSegment(
            segment_id=f"seg-{number}",
            number=number,
            started_at=at,
            start_reason=reason,
            start_note=note,
            stance=stance,
            legs=frozen,
            untracked_reason=untracked,
        )
        return replace(self, segments=(*self.segments, segment))

    def with_open_segment_closed(self, *, at: datetime, reason: str, note: str = "") -> "IdeaTracking":
        current = self.open_segment
        if current is None:
            return self
        return replace(self, segments=(*self.segments[:-1], current.closed(at, reason, note)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": TRACKING_LABEL,
            "benchmark": self.benchmark,
            "cost_model": self.cost_model.to_dict(),
            "segments": [segment.to_dict() for segment in self.segments],
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaTracking":
        snapshot = payload.get("snapshot")
        cost_model = payload.get("cost_model")
        return cls(
            benchmark=str(payload.get("benchmark") or DEFAULT_TRACKING_BENCHMARK),
            cost_model=IdeaCostModel.from_dict(cost_model if isinstance(cost_model, Mapping) else None),
            segments=tuple(IdeaTrackingSegment.from_dict(item) for item in _list(payload.get("segments"), "tracking.segments")),
            snapshot=IdeaTrackingSnapshot.from_dict(snapshot) if isinstance(snapshot, Mapping) else None,
        )


def freeze_tracking_legs(legs: Sequence[IdeaLeg], stance: str) -> tuple[tuple[IdeaTrackedLeg, ...], str | None]:
    """Freeze ``legs`` for a segment and say why the book cannot be tracked, if it cannot.

    Weights become signed shares of gross exposure. Without any stated weight, a
    ``long`` or ``short`` idea is an equal-weight book with that sign; a
    relative, event or neutral idea needs a signed weight on every leg, because
    only the user knows which leg is short. Mixing stated and missing weights is
    refused rather than guessed.
    """
    items = tuple(legs)
    if not items:
        raise IdeaValidationError("A tracking segment needs at least one leg.")
    reasons: list[str] = []
    untracked_types = sorted(
        {
            str(leg.entity.entity_type).strip().lower()
            for leg in items
            if str(leg.entity.entity_type).strip().lower() not in TRACKED_ENTITY_TYPES
        }
    )
    if untracked_types:
        names = ", ".join(item.replace("_", " ") for item in untracked_types)
        reasons.append(
            f"Tracking prices equity, ETF and crypto legs from provider closes; {names} legs have no price source in this build."
        )
    stated = [leg.weight for leg in items]
    weights: list[float] | None
    source = "stated"
    if all(value is None for value in stated):
        if stance in {"long", "short"}:
            sign = 1.0 if stance == "long" else -1.0
            weights = [sign for _ in items]
            source = "stance"
        else:
            weights = None
            reasons.append("Give each leg a signed weight: a relative, event or neutral idea must say which legs are short.")
    elif any(value is None for value in stated):
        weights = None
        reasons.append("Give every leg a signed weight, or none for an equal-weight long or short book.")
    else:
        weights = [float(value) for value in stated if value is not None]
    gross = sum(abs(value) for value in weights) if weights is not None else 0.0
    if weights is not None and gross <= 0:
        weights = None
        reasons.append("The weights add up to no exposure; give at least one leg a non-zero weight.")
    untracked = " ".join(reasons) or None
    frozen = tuple(
        IdeaTrackedLeg(
            entity=leg.entity,
            stated_weight=leg.weight,
            weight=None if untracked or weights is None else weights[index] / gross,
            weight_source=source,
            asset_class=default_tracking_asset_class(leg.entity),
            market=tracking_market(leg.entity),
        )
        for index, leg in enumerate(items)
    )
    return frozen, untracked


def tracking_positions(legs: Sequence[IdeaLeg], stance: str) -> tuple[Any, ...]:
    """What a segment holds, for deciding whether an edit opens a new one.

    Labels and metadata are not positions: renaming a leg keeps the segment;
    a new instrument, a different weight share or a stance change that alters
    a default weight opens a new one.
    """
    if not legs:
        return ()
    frozen, untracked = freeze_tracking_legs(legs, stance)
    # Pesos (1, -1) y (2, -2) son el mismo libro: se compara la proporción, no el número escrito.
    positions = sorted((leg.key, leg.weight is None, round(leg.weight or 0.0, 10)) for leg in frozen)
    return (tuple(positions), untracked)


# ---------------------------------------------------------------------------
# Close and review (I3b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdeaEvidenceVerdict:
    """Whether a pin held up, as the user judged it at close; title and stance frozen then."""

    evidence_id: str
    verdict: str
    title: str
    stance: str

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        if self.verdict not in EVIDENCE_VERDICTS:
            raise IdeaValidationError(f"An evidence verdict must be one of {EVIDENCE_VERDICTS}, got {self.verdict!r}.")
        if self.stance not in EVIDENCE_STANCES:
            raise IdeaValidationError(f"An evidence stance must be one of {EVIDENCE_STANCES}.")
        title = str(self.title or "").strip()
        _require_text(title, "evidence title")
        object.__setattr__(self, "title", title[:EVIDENCE_TITLE_MAX])

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "verdict": self.verdict, "title": self.title, "stance": self.stance}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaEvidenceVerdict":
        return cls(
            evidence_id=str(payload.get("evidence_id") or ""),
            verdict=str(payload.get("verdict") or "").strip().lower(),
            title=str(payload.get("title") or ""),
            stance=str(payload.get("stance") or "").strip().lower(),
        )


@dataclass(frozen=True)
class IdeaCriterionAtClose:
    """A criterion's state when the idea was closed, kept for the review statistics."""

    criterion_id: str
    kind: str
    label: str
    state: str
    triggered_at: datetime | None = None
    first_met_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "criterion_id")
        if self.kind not in CRITERION_KINDS:
            raise IdeaValidationError(f"Criterion kind must be one of {CRITERION_KINDS}.")
        if self.state not in CRITERION_STATES:
            raise IdeaValidationError(f"Criterion state must be one of {CRITERION_STATES}.")
        label = " ".join(str(self.label or "").split())
        _require_text(label, "criterion label")
        object.__setattr__(self, "label", label[:CRITERION_LABEL_MAX])

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "kind": self.kind,
            "label": self.label,
            "state": self.state,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "first_met_at": self.first_met_at.isoformat() if self.first_met_at else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaCriterionAtClose":
        return cls(
            criterion_id=str(payload.get("criterion_id") or ""),
            kind=str(payload.get("kind") or "").strip().lower(),
            label=str(payload.get("label") or ""),
            state=str(payload.get("state") or "").strip().lower(),
            triggered_at=_parse_instant(payload.get("triggered_at")),
            first_met_at=_parse_instant(payload.get("first_met_at")),
        )


@dataclass(frozen=True)
class IdeaReview:
    """Written at close (I3b): what was expected against what happened, and the lesson.

    ``realized`` is the hypothetical tracking headline as it stood when the
    idea was closed (its exit close may still be pending); the live record
    stays on ``Idea.tracking``. ``opened_at`` is when this episode began (the
    activation, or the reopen after an earlier close). Reviews only grow: a
    reopened idea keeps the review of its earlier close.
    """

    review_id: str
    idea_id: str
    outcome: str
    lesson: str
    opened_at: datetime
    closed_at: datetime
    expected: str = ""
    realized_note: str = ""
    evidence_verdicts: tuple[IdeaEvidenceVerdict, ...] = ()
    criteria_at_close: tuple[IdeaCriterionAtClose, ...] = ()
    realized: IdeaTrackingSnapshot | None = None
    schema_version: int = IDEA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.review_id, "review_id")
        _require_text(self.idea_id, "idea_id")
        if self.outcome not in REVIEW_OUTCOMES:
            raise IdeaValidationError(f"A review outcome must be one of {REVIEW_OUTCOMES}, got {self.outcome!r}.")
        lesson = str(self.lesson or "").strip()
        if len(lesson) < REVIEW_LESSON_MIN:
            raise IdeaValidationError("Closing an idea needs a review: write the lesson.")
        for name, value in (("lesson", lesson), ("expected", self.expected), ("realized_note", self.realized_note)):
            _require_max(str(value or "").strip(), REVIEW_TEXT_MAX, f"review {name}")
        object.__setattr__(self, "lesson", lesson)
        object.__setattr__(self, "expected", str(self.expected or "").strip())
        object.__setattr__(self, "realized_note", str(self.realized_note or "").strip())
        if self.closed_at < self.opened_at:
            raise IdeaValidationError("A review cannot close before its episode opened.")
        verdicts = tuple(self.evidence_verdicts)
        if any(not isinstance(item, IdeaEvidenceVerdict) for item in verdicts):
            raise IdeaValidationError("evidence_verdicts must be IdeaEvidenceVerdict records.")
        if len({item.evidence_id for item in verdicts}) != len(verdicts):
            raise IdeaValidationError("Each pin takes at most one verdict.")
        object.__setattr__(self, "evidence_verdicts", verdicts[:IDEA_EVIDENCE_MAX])
        criteria = tuple(self.criteria_at_close)
        if any(not isinstance(item, IdeaCriterionAtClose) for item in criteria):
            raise IdeaValidationError("criteria_at_close must be IdeaCriterionAtClose records.")
        object.__setattr__(self, "criteria_at_close", criteria[:IDEA_CRITERIA_MAX])
        if self.realized is not None and not isinstance(self.realized, IdeaTrackingSnapshot):
            raise IdeaValidationError("review realized must be a tracking snapshot.")
        _check_schema_version(self.schema_version)

    @property
    def holding_days(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds() / 86_400

    @property
    def invalidation_criteria(self) -> int:
        return sum(1 for item in self.criteria_at_close if item.kind == "invalidate")

    @property
    def first_invalidation_at(self) -> datetime | None:
        """The earliest invalidation trigger before the close, if any fired."""
        moments = [
            item.first_met_at or item.triggered_at
            for item in self.criteria_at_close
            if item.kind == "invalidate" and item.triggered_at is not None and item.triggered_at <= self.closed_at
        ]
        return min((moment for moment in moments if moment is not None), default=None)

    def verdict_counts(self) -> dict[str, int]:
        counts = {verdict: 0 for verdict in EVIDENCE_VERDICTS}
        for item in self.evidence_verdicts:
            counts[item.verdict] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "review_id": self.review_id,
            "idea_id": self.idea_id,
            "outcome": self.outcome,
            "lesson": self.lesson,
            "expected": self.expected,
            "realized_note": self.realized_note,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat(),
            "evidence_verdicts": [item.to_dict() for item in self.evidence_verdicts],
            "criteria_at_close": [item.to_dict() for item in self.criteria_at_close],
            "realized": self.realized.to_dict() if self.realized else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdeaReview":
        opened_at = _parse_instant(payload.get("opened_at"))
        closed_at = _parse_instant(payload.get("closed_at"))
        if opened_at is None or closed_at is None:
            raise IdeaValidationError("A review needs opened_at and closed_at.")
        realized = payload.get("realized")
        return cls(
            schema_version=_schema_version(payload.get("schema_version")),
            review_id=str(payload.get("review_id") or ""),
            idea_id=str(payload.get("idea_id") or ""),
            outcome=str(payload.get("outcome") or "").strip().lower(),
            lesson=str(payload.get("lesson") or ""),
            expected=str(payload.get("expected") or ""),
            realized_note=str(payload.get("realized_note") or ""),
            opened_at=opened_at,
            closed_at=closed_at,
            evidence_verdicts=tuple(
                IdeaEvidenceVerdict.from_dict(item) for item in _list(payload.get("evidence_verdicts"), "evidence_verdicts")
            ),
            criteria_at_close=tuple(
                IdeaCriterionAtClose.from_dict(item) for item in _list(payload.get("criteria_at_close"), "criteria_at_close")
            ),
            realized=IdeaTrackingSnapshot.from_dict(realized) if isinstance(realized, Mapping) else None,
        )


@dataclass(frozen=True)
class Idea:
    """A thesis with its pinned evidence, criteria and journal."""

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
    criteria: tuple[IdeaCriterion, ...] = ()
    journal: tuple[IdeaJournalEntry, ...] = ()
    # I3a: registro hipotético de seguimiento; None mientras la idea nunca estuvo activa con patas.
    tracking: IdeaTracking | None = None
    # I3b: revisiones escritas al cerrar; solo crecen (reabrir conserva la anterior).
    reviews: tuple[IdeaReview, ...] = ()
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
        criteria = tuple(self.criteria)
        if len(criteria) > IDEA_CRITERIA_MAX:
            raise IdeaValidationError(f"An idea holds at most {IDEA_CRITERIA_MAX} criteria.")
        for item in criteria:
            if not isinstance(item, IdeaCriterion) or item.idea_id != self.idea_id:
                raise IdeaValidationError("Every criterion must belong to this idea.")
        if len({item.criterion_id for item in criteria}) != len(criteria):
            raise IdeaValidationError("Criterion ids must be unique within an idea.")
        object.__setattr__(self, "criteria", criteria)
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
        if self.tracking is not None and not isinstance(self.tracking, IdeaTracking):
            raise IdeaValidationError("tracking must be an IdeaTracking record.")
        reviews = tuple(self.reviews)
        if len(reviews) > IDEA_REVIEWS_MAX:
            raise IdeaValidationError(f"An idea holds at most {IDEA_REVIEWS_MAX} reviews.")
        for review in reviews:
            if not isinstance(review, IdeaReview) or review.idea_id != self.idea_id:
                raise IdeaValidationError("Every review must belong to this idea.")
        if len({review.review_id for review in reviews}) != len(reviews):
            raise IdeaValidationError("Review ids must be unique within an idea.")
        object.__setattr__(self, "reviews", reviews)
        # Cerrar exige una revisión: la última corresponde a este cierre.
        if self.status == "closed" and (not reviews or reviews[-1].closed_at != self.closed_at):
            raise IdeaValidationError("A closed idea needs the review written at its close.")
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

    def criteria_counts(self) -> dict[str, int]:
        counts = {state: 0 for state in CRITERION_STATES}
        for item in self.criteria:
            counts[item.state] += 1
        return counts

    @property
    def unacknowledged_triggers(self) -> int:
        return sum(1 for item in self.criteria if item.needs_acknowledgement)

    @property
    def latest_review(self) -> IdeaReview | None:
        return self.reviews[-1] if self.reviews else None

    @property
    def current_review(self) -> IdeaReview | None:
        """The review of the idea's current close (closed, or archived after closing)."""
        review = self.latest_review
        if review is None or self.closed_at is None or review.closed_at != self.closed_at:
            return None
        return review

    @property
    def activated_at(self) -> datetime | None:
        """When the idea last became active, from the journal; ``None`` if it never did."""
        for entry in reversed(self.journal):
            if entry.kind == "status_changed" and entry.details.get("to") == "active":
                return entry.created_at
        return None

    def criterion(self, criterion_id: str) -> IdeaCriterion | None:
        return next((item for item in self.criteria if item.criterion_id == criterion_id), None)

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
            "criteria": [item.to_dict() for item in self.criteria],
            "journal": [entry.to_dict() for entry in self.journal],
            "tracking": self.tracking.to_dict() if self.tracking else None,
            "reviews": [review.to_dict() for review in self.reviews],
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
            criteria=tuple(IdeaCriterion.from_dict(item) for item in _list(payload.get("criteria"), "criteria")),
            journal=tuple(IdeaJournalEntry.from_dict(item) for item in _list(payload.get("journal"), "journal")),
            tracking=IdeaTracking.from_dict(payload["tracking"]) if isinstance(payload.get("tracking"), Mapping) else None,
            reviews=tuple(IdeaReview.from_dict(item) for item in _list(payload.get("reviews"), "reviews")),
        )


# ---------------------------------------------------------------------------
# Rules shared by the store and the service
# ---------------------------------------------------------------------------


def migrate_idea_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Version 2 adds ``criteria``. Nested records carry the idea's version too."""
    migrated = dict(payload)
    migrated["criteria"] = list(migrated.get("criteria") or [])
    for key in ("evidence", "journal", "criteria"):
        items = migrated.get(key)
        if isinstance(items, list):
            migrated[key] = [dict(item, schema_version=2) if isinstance(item, Mapping) else item for item in items]
    return migrated


def migrate_idea_v2_to_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """Version 3 adds ``tracking``. Nested records carry the idea's version too.

    An idea that is active with legs gets one open segment, frozen at the last
    moment its legs and status were set: the later of its last activation (or
    restore) and its last leg edit, both read from the journal. Its legs have
    not changed since that instant, so the record starts at the next close
    after it and nothing earlier is added. Earlier active periods are not
    reconstructed, because version 2 journals describe old legs only as text.
    """
    migrated = dict(payload)
    for key in ("evidence", "journal", "criteria"):
        items = migrated.get(key)
        if isinstance(items, list):
            migrated[key] = [dict(item, schema_version=3) if isinstance(item, Mapping) else item for item in items]
    migrated["tracking"] = None
    if str(migrated.get("status") or "").strip().lower() != "active" or not migrated.get("legs"):
        return migrated
    activated_at: datetime | None = None
    legs_edited_at: datetime | None = None
    for entry in migrated.get("journal") or []:
        if not isinstance(entry, Mapping):
            continue
        created_at = _parse_instant(entry.get("created_at"))
        details = entry.get("details") if isinstance(entry.get("details"), Mapping) else {}
        if created_at is None:
            continue
        if entry.get("kind") == "status_changed" and details.get("to") == "active":
            activated_at = created_at
        changes = details.get("changes") if entry.get("kind") == "edited" else None
        if isinstance(changes, list) and any(isinstance(item, Mapping) and item.get("field") == "legs" for item in changes):
            legs_edited_at = created_at
    if activated_at is None:
        return migrated
    frozen_at = max(activated_at, legs_edited_at) if legs_edited_at else activated_at
    legs = tuple(IdeaLeg.from_dict(item) for item in _list(migrated.get("legs"), "legs"))
    stance = str(migrated.get("stance") or "neutral").strip().lower()
    note = (
        f"Tracking began in a later build. The legs have not changed since {frozen_at.strftime('%Y-%m-%d %H:%M')} UTC, "
        "so the record starts at the next close after that; nothing earlier is added."
    )
    tracking = IdeaTracking().with_open_segment(legs=legs, stance=stance, at=frozen_at, reason="migrated", note=note)
    migrated["tracking"] = tracking.to_dict()
    return migrated


def migrate_idea_v3_to_v4(payload: dict[str, Any]) -> dict[str, Any]:
    """Version 4 adds ``reviews``. No version 3 idea can be closed, so none needs one."""
    migrated = dict(payload)
    migrated["reviews"] = list(migrated.get("reviews") or [])
    for key in ("evidence", "journal", "criteria", "reviews"):
        items = migrated.get(key)
        if isinstance(items, list):
            migrated[key] = [dict(item, schema_version=4) if isinstance(item, Mapping) else item for item in items]
    return migrated


def assert_reviews_append_only(previous: Sequence[IdeaReview], current: Sequence[IdeaReview]) -> None:
    """Refuse any change that edits or drops a review written at an earlier close."""
    if len(current) < len(previous):
        raise IdeaValidationError("Idea reviews are kept; a review cannot be removed.")
    for index, review in enumerate(previous):
        if current[index].to_dict() != review.to_dict():
            raise IdeaValidationError("Idea reviews are kept as written; an earlier review cannot be edited.")


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
