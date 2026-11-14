"""Pydantic contracts for ``/ideas`` (Workstream 12, checkpoint I1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.application.idea_service import (
    IdeaCreateRequest,
    IdeaEvidenceCreateRequest,
    IdeaListResult,
    IdeaPatchRequest,
)
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    EVIDENCE_NOTE_MAX,
    EVIDENCE_TITLE_MAX,
    IDEA_HOLDING_WINDOW_MAX,
    IDEA_LEGS_MAX,
    IDEA_NOTES_MAX,
    IDEA_TAGS_MAX,
    IDEA_THESIS_MAX,
    IDEA_TITLE_MAX,
    JOURNAL_BODY_MAX,
    ORIGIN_LABEL_MAX,
    ORIGIN_REF_MAX,
    Idea,
    IdeaEvidence,
    IdeaHorizon,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaOrigin,
    envelope_from_dict,
    freshness_from_dict,
    provenance_from_dict,
    thaw_captured_values,
)
from src.services.idea_store import IdeaStorageWarning, IdeaSummary

IdeaStanceLiteral = Literal["long", "short", "relative", "event", "neutral"]
IdeaStatusLiteral = Literal["draft", "active", "closed", "archived"]
EvidenceStanceLiteral = Literal["supports", "challenges", "context"]
EvidenceKindLiteral = Literal[
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
]
OriginKindLiteral = Literal["manual", "sitrep_follow_up", "copilot", "handoff", "import"]


# ---------------------------------------------------------------------------
# Shared parts
# ---------------------------------------------------------------------------


class IdeaEntityModel(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    normalized_id: str = Field(min_length=1, max_length=200)
    provider_id: str | None = Field(default=None, max_length=200)
    native_id: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_domain(self) -> HandoffEntity:
        return HandoffEntity(
            entity_type=self.entity_type.strip(),
            label=self.label.strip(),
            normalized_id=self.normalized_id.strip(),
            provider_id=self.provider_id,
            native_id=self.native_id,
            metadata=dict(self.metadata),
        )

    @classmethod
    def from_domain(cls, entity: HandoffEntity) -> "IdeaEntityModel":
        return cls(**entity.to_dict())


class IdeaLegModel(BaseModel):
    entity: IdeaEntityModel
    weight: float | None = None

    def to_domain(self) -> IdeaLeg:
        return IdeaLeg(entity=self.entity.to_domain(), weight=self.weight)

    @classmethod
    def from_domain(cls, leg: IdeaLeg) -> "IdeaLegModel":
        return cls(entity=IdeaEntityModel.from_domain(leg.entity), weight=leg.weight)


class IdeaHorizonModel(BaseModel):
    review_date: date | None = None
    holding_window: str | None = Field(default=None, max_length=IDEA_HOLDING_WINDOW_MAX)

    def to_domain(self) -> IdeaHorizon:
        return IdeaHorizon(review_date=self.review_date, holding_window=self.holding_window)

    @classmethod
    def from_domain(cls, horizon: IdeaHorizon) -> "IdeaHorizonModel":
        return cls(review_date=horizon.review_date, holding_window=horizon.holding_window)


class IdeaOriginModel(BaseModel):
    kind: OriginKindLiteral = "manual"
    source_ref: str | None = Field(default=None, max_length=ORIGIN_REF_MAX)
    label: str | None = Field(default=None, max_length=ORIGIN_LABEL_MAX)
    handoff: dict[str, Any] | None = None

    def to_domain(self) -> IdeaOrigin:
        return IdeaOrigin(
            kind=self.kind,
            source_ref=(self.source_ref or "").strip() or None,
            label=(self.label or "").strip() or None,
            handoff=envelope_from_dict(self.handoff) if self.handoff else None,
        )

    @classmethod
    def from_domain(cls, origin: IdeaOrigin) -> "IdeaOriginModel":
        return cls(
            kind=origin.kind,  # type: ignore[arg-type]
            source_ref=origin.source_ref,
            label=origin.label,
            handoff=origin.handoff.to_dict() if origin.handoff else None,
        )


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class IdeaCreateRequestModel(BaseModel):
    title: str = Field(min_length=1, max_length=IDEA_TITLE_MAX)
    thesis: str = Field(default="", max_length=IDEA_THESIS_MAX)
    notes: str = Field(default="", max_length=IDEA_NOTES_MAX)
    stance: IdeaStanceLiteral = "neutral"
    legs: list[IdeaLegModel] = Field(default_factory=list, max_length=IDEA_LEGS_MAX)
    horizon: IdeaHorizonModel | None = None
    tags: list[str] = Field(default_factory=list, max_length=IDEA_TAGS_MAX)
    origin: IdeaOriginModel | None = None

    def to_domain(self) -> IdeaCreateRequest:
        return IdeaCreateRequest(
            title=self.title,
            thesis=self.thesis,
            notes=self.notes,
            stance=self.stance,
            legs=tuple(leg.to_domain() for leg in self.legs),
            horizon=self.horizon.to_domain() if self.horizon else IdeaHorizon(),
            tags=tuple(self.tags),
            origin=self.origin.to_domain() if self.origin else IdeaOrigin(),
        )


class IdeaPatchRequestModel(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=IDEA_TITLE_MAX)
    thesis: str | None = Field(default=None, max_length=IDEA_THESIS_MAX)
    notes: str | None = Field(default=None, max_length=IDEA_NOTES_MAX)
    stance: IdeaStanceLiteral | None = None
    legs: list[IdeaLegModel] | None = Field(default=None, max_length=IDEA_LEGS_MAX)
    horizon: IdeaHorizonModel | None = None
    tags: list[str] | None = Field(default=None, max_length=IDEA_TAGS_MAX)

    def to_domain(self) -> IdeaPatchRequest:
        return IdeaPatchRequest(
            title=self.title,
            thesis=self.thesis,
            notes=self.notes,
            stance=self.stance,
            legs=None if self.legs is None else tuple(leg.to_domain() for leg in self.legs),
            horizon=None if self.horizon is None else self.horizon.to_domain(),
            tags=None if self.tags is None else tuple(self.tags),
        )


class IdeaEvidenceCreateRequestModel(BaseModel):
    kind: EvidenceKindLiteral
    # Required on purpose: disconfirming evidence is first-class, never a default.
    stance: EvidenceStanceLiteral
    title: str = Field(min_length=1, max_length=EVIDENCE_TITLE_MAX)
    captured_values: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    reopen: dict[str, Any] | None = None
    note: str = Field(default="", max_length=EVIDENCE_NOTE_MAX)

    def to_domain(self) -> IdeaEvidenceCreateRequest:
        return IdeaEvidenceCreateRequest(
            kind=self.kind,
            stance=self.stance,
            title=self.title,
            captured_values=dict(self.captured_values),
            provenance=provenance_from_dict(self.provenance) if self.provenance else None,
            freshness=freshness_from_dict(self.freshness) if self.freshness else None,
            reopen=envelope_from_dict(self.reopen) if self.reopen else None,
            note=self.note,
        )


class IdeaJournalCreateRequestModel(BaseModel):
    kind: Literal["note", "decision"] = "note"
    body: str = Field(min_length=1, max_length=JOURNAL_BODY_MAX)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class IdeaEvidenceModel(BaseModel):
    schema_version: int
    evidence_id: str
    idea_id: str
    kind: str
    stance: str
    title: str
    captured_values: dict[str, Any]
    provenance: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    reopen: dict[str, Any] | None = None
    captured_at: datetime
    note: str = ""

    @classmethod
    def from_domain(cls, item: IdeaEvidence) -> "IdeaEvidenceModel":
        return cls(
            schema_version=item.schema_version,
            evidence_id=item.evidence_id,
            idea_id=item.idea_id,
            kind=item.kind,
            stance=item.stance,
            title=item.title,
            captured_values=thaw_captured_values(item.captured_values),
            provenance=item.provenance.to_dict() if item.provenance else None,
            freshness=item.freshness.to_dict() if item.freshness else None,
            reopen=item.reopen.to_dict() if item.reopen else None,
            captured_at=item.captured_at,
            note=item.note,
        )


class IdeaJournalEntryModel(BaseModel):
    schema_version: int
    entry_id: str
    idea_id: str
    kind: str
    author: str
    body: str
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, entry: IdeaJournalEntry) -> "IdeaJournalEntryModel":
        return cls(
            schema_version=entry.schema_version,
            entry_id=entry.entry_id,
            idea_id=entry.idea_id,
            kind=entry.kind,
            author=entry.author,
            body=entry.body,
            created_at=entry.created_at,
            details=thaw_captured_values(entry.details),
        )


class IdeaModel(BaseModel):
    schema_version: int
    idea_id: str
    title: str
    thesis: str
    notes: str
    stance: str
    legs: list[IdeaLegModel]
    horizon: IdeaHorizonModel
    status: str
    origin: IdeaOriginModel
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    evidence: list[IdeaEvidenceModel]
    journal: list[IdeaJournalEntryModel]
    evidence_counts: dict[str, int]
    # ``origin`` above is the idea's domain origin, so the record's own
    # provenance travels as one nested object instead of top-level fields.
    provenance: dict[str, Any]

    @classmethod
    def from_domain(cls, idea: Idea, *, retrieved_at: datetime) -> "IdeaModel":
        return cls(
            schema_version=idea.schema_version,
            idea_id=idea.idea_id,
            title=idea.title,
            thesis=idea.thesis,
            notes=idea.notes,
            stance=idea.stance,
            legs=[IdeaLegModel.from_domain(leg) for leg in idea.legs],
            horizon=IdeaHorizonModel.from_domain(idea.horizon),
            status=idea.status,
            origin=IdeaOriginModel.from_domain(idea.origin),
            tags=list(idea.tags),
            created_at=idea.created_at,
            updated_at=idea.updated_at,
            closed_at=idea.closed_at,
            evidence=[IdeaEvidenceModel.from_domain(item) for item in idea.evidence],
            journal=[IdeaJournalEntryModel.from_domain(entry) for entry in idea.journal],
            evidence_counts=idea.evidence_counts(),
            provenance={
                "source_provider": "gamma_ideas",
                "retrieved_at": retrieved_at.isoformat(),
                "origin": "idea_store",
                "transformation_note": None,
            },
        )


class IdeaLegSummaryModel(BaseModel):
    label: str
    entity_type: str
    normalized_id: str
    weight: float | None = None


class IdeaSummaryModel(BaseModel):
    idea_id: str
    title: str
    thesis: str
    stance: str
    status: str
    tags: list[str]
    legs: list[IdeaLegSummaryModel]
    evidence_counts: dict[str, int]
    evidence_total: int
    last_evidence_at: datetime | None = None
    journal_count: int
    origin_kind: str
    origin_ref: str | None = None
    review_date: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, summary: IdeaSummary) -> "IdeaSummaryModel":
        payload = summary.to_dict()
        payload.pop("schema_version", None)
        return cls(**payload)


class IdeaStorageWarningModel(BaseModel):
    action: str
    file_name: str
    message: str
    created_at: datetime

    @classmethod
    def from_domain(cls, warning: IdeaStorageWarning) -> "IdeaStorageWarningModel":
        return cls(
            action=warning.action,
            file_name=warning.file_name,
            message=warning.message,
            created_at=warning.created_at,
        )


class IdeaListResponseModel(BaseModel):
    items: list[IdeaSummaryModel] = Field(default_factory=list)
    total: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    storage_warnings: list[IdeaStorageWarningModel] = Field(default_factory=list)
    source_provider: str = "gamma_ideas"
    retrieved_at: datetime
    origin: str = "idea_service.list_ideas"
    transformation_note: str | None = "Board rows come from the local idea index."

    @classmethod
    def from_domain(cls, result: IdeaListResult) -> "IdeaListResponseModel":
        return cls(
            items=[IdeaSummaryModel.from_domain(item) for item in result.items],
            total=result.total,
            status_counts=result.status_counts,
            tags=result.tags,
            storage_warnings=[IdeaStorageWarningModel.from_domain(item) for item in result.storage_warnings],
            retrieved_at=result.retrieved_at,
        )


class IdeaPinResponseModel(BaseModel):
    idea: IdeaModel
    evidence: IdeaEvidenceModel


class IdeaDeleteResponseModel(BaseModel):
    success: bool
    recoverable: bool = True

