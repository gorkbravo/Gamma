from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.models.provenance import ProvenanceRecord
from src.utils.time import now_utc


@dataclass(frozen=True)
class HandoffEntity:
    entity_type: str
    label: str
    normalized_id: str
    provider_id: str | None = None
    native_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.entity_type, "entity_type")
        _require_text(self.label, "label")
        _require_text(self.normalized_id, "normalized_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "label": self.label,
            "normalized_id": self.normalized_id,
            "provider_id": self.provider_id,
            "native_id": self.native_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HandoffEntity":
        return cls(
            entity_type=str(payload.get("entity_type") or ""),
            label=str(payload.get("label") or ""),
            normalized_id=str(payload.get("normalized_id") or ""),
            provider_id=_optional_text(payload.get("provider_id")),
            native_id=_optional_text(payload.get("native_id")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class HandoffTimeframe:
    label: str
    start: datetime | None = None
    end: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.label, "label")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("handoff timeframe start cannot be after end.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HandoffTimeframe":
        return cls(
            label=str(payload.get("label") or ""),
            start=_parse_datetime(payload.get("start")),
            end=_parse_datetime(payload.get("end")),
        )


@dataclass(frozen=True)
class CrossTabHandoffEnvelope:
    source_tab: str
    intended_target_tab: str
    source_mode: str | None = None
    intended_target_mode: str | None = None
    selected_entity: HandoffEntity | None = None
    selected_timeframe: HandoffTimeframe | None = None
    provider: str | None = None
    source: ProvenanceRecord | None = None
    warnings: list[str] = field(default_factory=list)
    normalized_ids: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=now_utc)

    def __post_init__(self) -> None:
        _require_text(self.source_tab, "source_tab")
        _require_text(self.intended_target_tab, "intended_target_tab")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_tab": self.source_tab,
            "source_mode": self.source_mode,
            "selected_entity": self.selected_entity.to_dict() if self.selected_entity else None,
            "selected_timeframe": self.selected_timeframe.to_dict() if self.selected_timeframe else None,
            "provider": self.provider,
            "source": self.source.to_dict() if self.source else None,
            "warnings": list(self.warnings),
            "normalized_ids": dict(self.normalized_ids),
            "timestamp": self.timestamp.isoformat(),
            "intended_target_tab": self.intended_target_tab,
            "intended_target_mode": self.intended_target_mode,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CrossTabHandoffEnvelope":
        entity_payload = payload.get("selected_entity")
        timeframe_payload = payload.get("selected_timeframe")
        source_payload = payload.get("source")
        return cls(
            source_tab=str(payload.get("source_tab") or ""),
            source_mode=_optional_text(payload.get("source_mode")),
            selected_entity=HandoffEntity.from_dict(entity_payload) if isinstance(entity_payload, dict) else None,
            selected_timeframe=(
                HandoffTimeframe.from_dict(timeframe_payload) if isinstance(timeframe_payload, dict) else None
            ),
            provider=_optional_text(payload.get("provider")),
            source=_provenance_from_dict(source_payload) if isinstance(source_payload, dict) else None,
            warnings=[str(item) for item in payload.get("warnings", []) if str(item or "").strip()],
            normalized_ids={
                str(key): str(value)
                for key, value in dict(payload.get("normalized_ids") or {}).items()
                if str(key or "").strip() and str(value or "").strip()
            },
            timestamp=_parse_datetime(payload.get("timestamp")) or now_utc(),
            intended_target_tab=str(payload.get("intended_target_tab") or ""),
            intended_target_mode=_optional_text(payload.get("intended_target_mode")),
        )


def _provenance_from_dict(payload: dict[str, Any]) -> ProvenanceRecord:
    retrieved_at = _parse_datetime(payload.get("retrieved_at"))
    if retrieved_at is None:
        raise ValueError("source.retrieved_at is required.")
    return ProvenanceRecord(
        source_provider=str(payload.get("source_provider") or ""),
        retrieved_at=retrieved_at,
        origin=str(payload.get("origin") or ""),
        transformation_note=_optional_text(payload.get("transformation_note")),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _require_text(value: Any, field_name: str) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field_name} is required.")

