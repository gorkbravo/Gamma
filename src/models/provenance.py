from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FreshnessLabel(str, Enum):
    LIVE = "live"
    DELAYED = "delayed"
    STALE = "stale"
    HISTORICAL = "historical"
    MOCKED = "mocked"
    DERIVED = "derived"
    MODEL_GENERATED = "model_generated"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


_FRESHNESS_ALIASES = {
    "fresh": FreshnessLabel.LIVE,
    "current": FreshnessLabel.LIVE,
    "current_public_api": FreshnessLabel.LIVE,
    "realtime": FreshnessLabel.LIVE,
    "real_time": FreshnessLabel.LIVE,
    "mock": FreshnessLabel.MOCKED,
    "sample": FreshnessLabel.MOCKED,
    "synthetic": FreshnessLabel.MOCKED,
    "model": FreshnessLabel.MODEL_GENERATED,
    "model_generated": FreshnessLabel.MODEL_GENERATED,
    "ai_generated": FreshnessLabel.MODEL_GENERATED,
    "not_available": FreshnessLabel.UNAVAILABLE,
    "n/a": FreshnessLabel.UNAVAILABLE,
}


@dataclass(frozen=True)
class ProvenanceRecord:
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None

    def __post_init__(self) -> None:
        if not str(self.source_provider or "").strip():
            raise ValueError("source_provider is required.")
        if not str(self.origin or "").strip():
            raise ValueError("origin is required.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_provider": self.source_provider,
            "retrieved_at": self.retrieved_at.isoformat(),
            "origin": self.origin,
            "transformation_note": self.transformation_note,
        }


@dataclass(frozen=True)
class FreshnessRecord:
    label: FreshnessLabel
    retrieved_at: datetime | None = None
    source_timestamp: datetime | None = None
    evaluated_at: datetime | None = None
    age_seconds: float | None = None
    ttl_seconds: float | None = None
    is_stale: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label.value,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "source_timestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "age_seconds": self.age_seconds,
            "ttl_seconds": self.ttl_seconds,
            "is_stale": self.is_stale,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ProvenanceSummary:
    source_provider: str
    origin: str
    retrieved_at: datetime | None = None
    transformation_note: str | None = None
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_record(
        cls,
        provenance: ProvenanceRecord,
        *,
        freshness_label: str | FreshnessLabel | None = None,
        warnings: list[str] | None = None,
    ) -> "ProvenanceSummary":
        return cls(
            source_provider=provenance.source_provider,
            origin=provenance.origin,
            retrieved_at=provenance.retrieved_at,
            transformation_note=provenance.transformation_note,
            freshness_label=normalize_freshness_label(freshness_label),
            warnings=list(warnings or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_provider": self.source_provider,
            "origin": self.origin,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "transformation_note": self.transformation_note,
            "freshness_label": self.freshness_label.value,
            "warnings": list(self.warnings),
        }


def normalize_freshness_label(value: str | FreshnessLabel | None) -> FreshnessLabel:
    if isinstance(value, FreshnessLabel):
        return value
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return FreshnessLabel.UNKNOWN
    if normalized in _FRESHNESS_ALIASES:
        return _FRESHNESS_ALIASES[normalized]
    try:
        return FreshnessLabel(normalized)
    except ValueError:
        return FreshnessLabel.UNKNOWN


def requires_transformation_note(label: str | FreshnessLabel | None) -> bool:
    return normalize_freshness_label(label) in {
        FreshnessLabel.DERIVED,
        FreshnessLabel.MODEL_GENERATED,
    }

