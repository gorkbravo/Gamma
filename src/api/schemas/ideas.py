"""Pydantic contracts for ``/ideas`` (Workstream 12, checkpoints I1, I2, I3a, I3b and I3c)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.application.idea_service import (
    IdeaCreateRequest,
    IdeaCriterionRequest,
    IdeaEvidenceCreateRequest,
    IdeaCloseRequest,
    IdeaListResult,
    IdeaPatchRequest,
    IdeaReviewStatistics,
    IdeaTrackingSettingsRequest,
)
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    CRITERION_LABEL_MAX,
    EVIDENCE_NOTE_MAX,
    EVIDENCE_TITLE_MAX,
    IDEA_HOLDING_WINDOW_MAX,
    IDEA_LEGS_MAX,
    IDEA_NOTES_MAX,
    IDEA_TAGS_MAX,
    IDEA_THESIS_MAX,
    IDEA_TITLE_MAX,
    JOURNAL_BODY_MAX,
    OBSERVABLE_ID_MAX,
    OBSERVABLE_LABEL_MAX,
    OBSERVABLE_PARAM_VALUE_MAX,
    OBSERVABLE_PARAMS_MAX,
    ORIGIN_LABEL_MAX,
    ORIGIN_REF_MAX,
    REVIEW_TEXT_MAX,
    TRACKING_BENCHMARK_MAX,
    TRACKING_COST_BP_MAX,
    TRACKING_LABEL,
    CriterionEvaluation,
    Idea,
    IdeaCriterion,
    IdeaEvidence,
    IdeaHorizon,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaOrigin,
    IdeaReview,
    IdeaRiskSnapshot,
    IdeaTestSnapshot,
    IdeaTracking,
    ObservableRef,
    envelope_from_dict,
    freshness_from_dict,
    provenance_from_dict,
    snapshot_staleness,
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
CriterionKindLiteral = Literal["invalidate", "confirm", "review"]
CriterionConditionLiteral = Literal[
    "above",
    "below",
    "crosses_above",
    "crosses_below",
    "change_over_window",
    "date_reached",
    "event_occurs",
]
CriterionCadenceLiteral = Literal["on_open", "daily_close", "intraday"]
CriterionWindowLiteral = Literal["1d", "5d", "1m", "3m", "6m", "1y"]


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


class ObservableRefModel(BaseModel):
    observable_id: str = Field(min_length=1, max_length=OBSERVABLE_ID_MAX)
    params: dict[str, str] = Field(default_factory=dict, max_length=OBSERVABLE_PARAMS_MAX)
    label: str = Field(default="", max_length=OBSERVABLE_LABEL_MAX)

    def to_domain(self) -> ObservableRef:
        for value in self.params.values():
            if len(value) > OBSERVABLE_PARAM_VALUE_MAX:
                raise ValueError(f"observable params are limited to {OBSERVABLE_PARAM_VALUE_MAX} characters.")
        return ObservableRef(observable_id=self.observable_id, params=dict(self.params), label=self.label)

    @classmethod
    def from_domain(cls, ref: ObservableRef) -> "ObservableRefModel":
        return cls(**ref.to_dict())


class IdeaCriterionRequestModel(BaseModel):
    kind: CriterionKindLiteral
    observable: ObservableRefModel
    condition: CriterionConditionLiteral
    threshold: float | None = None
    window: CriterionWindowLiteral | None = None
    cadence: CriterionCadenceLiteral = "daily_close"
    # Blank means "generate it from the rule"; the user may edit it.
    label: str | None = Field(default=None, max_length=CRITERION_LABEL_MAX)

    def to_domain(self) -> IdeaCriterionRequest:
        return IdeaCriterionRequest(
            kind=self.kind,
            observable=self.observable.to_domain(),
            condition=self.condition,
            threshold=self.threshold,
            window=self.window,
            cadence=self.cadence,
            label=self.label,
        )


class ObservablePreviewRequestModel(BaseModel):
    observable: ObservableRefModel


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


class CriterionEvaluationModel(BaseModel):
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
    effective_cadence: str
    cadence_note: str | None = None
    provenance: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    known_at_arming: bool = False

    @classmethod
    def from_domain(cls, evaluation: CriterionEvaluation) -> "CriterionEvaluationModel":
        return cls(**evaluation.to_dict())


class IdeaCriterionModel(BaseModel):
    schema_version: int
    criterion_id: str
    idea_id: str
    kind: str
    label: str
    observable: ObservableRefModel
    condition: str
    threshold: float | None = None
    window: str | None = None
    cadence: str
    state: str
    last_evaluation: CriterionEvaluationModel | None = None
    trigger_evaluation: CriterionEvaluationModel | None = None
    triggered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    armed_at: datetime
    created_at: datetime
    baseline_as_of: datetime | None = None
    baseline_for: datetime | None = None

    @classmethod
    def from_domain(cls, criterion: IdeaCriterion) -> "IdeaCriterionModel":
        return cls(
            schema_version=criterion.schema_version,
            criterion_id=criterion.criterion_id,
            idea_id=criterion.idea_id,
            kind=criterion.kind,
            label=criterion.label,
            observable=ObservableRefModel.from_domain(criterion.observable),
            condition=criterion.condition,
            threshold=criterion.threshold,
            window=criterion.window,
            cadence=criterion.cadence,
            state=criterion.state,
            last_evaluation=(
                CriterionEvaluationModel.from_domain(criterion.last_evaluation) if criterion.last_evaluation else None
            ),
            trigger_evaluation=(
                CriterionEvaluationModel.from_domain(criterion.trigger_evaluation)
                if criterion.trigger_evaluation
                else None
            ),
            triggered_at=criterion.triggered_at,
            acknowledged_at=criterion.acknowledged_at,
            armed_at=criterion.armed_at,
            created_at=criterion.created_at,
            baseline_as_of=criterion.baseline_as_of,
            baseline_for=criterion.baseline_for,
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
    criteria: list[IdeaCriterionModel] = Field(default_factory=list)
    journal: list[IdeaJournalEntryModel]
    evidence_counts: dict[str, int]
    criteria_counts: dict[str, int] = Field(default_factory=dict)
    # I3a: segmentos, supuestos de coste y último titular; la serie se pide a /tracking.
    tracking: "IdeaTrackingRecordModel | None" = None
    # I3b: revisiones escritas al cerrar (la última es la del cierre vigente si la idea está cerrada).
    reviews: list["IdeaReviewModel"] = Field(default_factory=list)
    # I3c: snapshots de test y riesgo (del más antiguo al más reciente), con su motivo de obsolescencia.
    tests: list["IdeaTestSnapshotModel"] = Field(default_factory=list)
    risks: list["IdeaRiskSnapshotModel"] = Field(default_factory=list)
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
            criteria=[IdeaCriterionModel.from_domain(item) for item in idea.criteria],
            journal=[IdeaJournalEntryModel.from_domain(entry) for entry in idea.journal],
            evidence_counts=idea.evidence_counts(),
            criteria_counts=idea.criteria_counts(),
            tracking=IdeaTrackingRecordModel.from_domain(idea.tracking) if idea.tracking else None,
            reviews=[IdeaReviewModel.from_domain(item) for item in idea.reviews],
            tests=[IdeaTestSnapshotModel.from_domain(item, idea, retrieved_at) for item in idea.tests],
            risks=[IdeaRiskSnapshotModel.from_domain(item, idea, retrieved_at) for item in idea.risks],
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
    criteria_counts: dict[str, int] = Field(default_factory=dict)
    criteria_total: int = 0
    unacknowledged_triggers: int = 0
    tracking: "IdeaTrackingHeadlineModel | None" = None
    review: "IdeaReviewHeadlineModel | None" = None

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



class IdeaCriterionResponseModel(BaseModel):
    idea: IdeaModel
    criterion: IdeaCriterionModel


class IdeaNotificationModel(BaseModel):
    notification_id: str
    kind: Literal["criterion_triggered", "review_due"]
    idea_id: str
    idea_title: str
    created_at: datetime
    criterion_id: str | None = None
    criterion_kind: str | None = None
    label: str = ""
    value_display: str | None = None
    first_met_at: datetime | None = None
    review_date: date | None = None
    days_overdue: int | None = None
    provenance: dict[str, Any] | None = None


class IdeaNotificationsResponseModel(BaseModel):
    items: list[IdeaNotificationModel] = Field(default_factory=list)
    triggered: int = 0
    reviews_due: int = 0
    evaluation_running: bool = False
    last_pass: dict[str, Any] | None = None
    limitation: str = (
        "Criteria are evaluated only while Gamma runs: at start, when an idea is opened, "
        "after each US close and, with Trader Workstation connected, intraday."
    )
    source_provider: str = "gamma_ideas"
    retrieved_at: datetime
    origin: str = "idea_evaluation.notifications"


class EvaluationPassModel(BaseModel):
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    ideas_evaluated: int = 0
    criteria_evaluated: int = 0
    readings_taken: int = 0
    new_triggers: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ObservableParamModel(BaseModel):
    name: str
    label: str
    kind: str
    required: bool = True
    placeholder: str | None = None
    options: list[dict[str, str | None]] = Field(default_factory=list)


class ObservableDefinitionModel(BaseModel):
    observable_id: str
    label: str
    group: str
    source: str
    params: list[ObservableParamModel]
    conditions: list[str]
    cadences: list[str]
    change_unit: str
    value_unit: str
    needs_tws: bool
    needs_keys: list[str] = Field(default_factory=list)
    intraday_capable: bool = False
    available: bool
    unavailable_reason: str | None = None
    dependency_label: str | None = None
    order: int


class ObservableRegistryResponseModel(BaseModel):
    items: list[ObservableDefinitionModel] = Field(default_factory=list)
    tws_connected: bool = False
    source_provider: str = "gamma_ideas"
    retrieved_at: datetime
    origin: str = "idea_observables.registry"


class ObservablePreviewResponseModel(BaseModel):
    observable: ObservableRefModel
    available: bool
    value: float | None = None
    value_display: str | None = None
    as_of: datetime | None = None
    reason: str | None = None
    stale_reason: str | None = None
    history_points: int = 0
    event_time: datetime | None = None
    event_released: bool | None = None
    provenance: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    retrieved_at: datetime


class IdeaExplanationModel(BaseModel):
    key: str
    title: str
    measures: str
    why: dict[str, str]
    computed: str
    source: str | None = None


class IdeaExplanationsResponseModel(BaseModel):
    items: list[IdeaExplanationModel] = Field(default_factory=list)
    retrieved_at: datetime
    source_provider: str = "gamma_ideas"
    origin: str = "idea_explanations.registry"


# ---------------------------------------------------------------------------
# Forward tracking (I3a)
# ---------------------------------------------------------------------------


class IdeaTrackedLegModel(BaseModel):
    entity: IdeaEntityModel
    stated_weight: float | None = None
    weight: float | None = None
    weight_source: str
    asset_class: str
    market: str
    key: str


class IdeaTrackingSegmentRecordModel(BaseModel):
    segment_id: str
    number: int
    started_at: datetime
    start_reason: str
    start_note: str = ""
    stance: str
    legs: list[IdeaTrackedLegModel]
    ended_at: datetime | None = None
    end_reason: str | None = None
    end_note: str = ""
    untracked_reason: str | None = None


class IdeaTrackingSnapshotModel(BaseModel):
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
    final: bool = False
    stale_since: date | None = None


class IdeaCostModelRecordModel(BaseModel):
    per_side_bp: dict[str, float]
    leg_classes: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime | None = None


class IdeaTrackingRecordModel(BaseModel):
    label: str = TRACKING_LABEL
    benchmark: str
    cost_model: IdeaCostModelRecordModel
    segments: list[IdeaTrackingSegmentRecordModel] = Field(default_factory=list)
    snapshot: IdeaTrackingSnapshotModel | None = None

    @classmethod
    def from_domain(cls, tracking: IdeaTracking) -> "IdeaTrackingRecordModel":
        payload = tracking.to_dict()
        for segment, record in zip(payload["segments"], tracking.segments):
            for leg_payload, leg in zip(segment["legs"], record.legs):
                leg_payload["key"] = leg.key
        return cls(**payload)


class IdeaTrackingHeadlineModel(BaseModel):
    label: str = TRACKING_LABEL
    segments: int
    open: bool
    started_at: datetime
    snapshot: IdeaTrackingSnapshotModel | None = None


class IdeaTrackingSettingsRequestModel(BaseModel):
    per_side_bp: dict[str, float] | None = None
    leg_classes: dict[str, str | None] | None = None
    benchmark: str | None = Field(default=None, min_length=1, max_length=TRACKING_BENCHMARK_MAX)

    def to_domain(self) -> IdeaTrackingSettingsRequest:
        if self.per_side_bp is not None:
            for name, value in self.per_side_bp.items():
                if not (0 <= float(value) <= TRACKING_COST_BP_MAX):
                    raise ValueError(f"The {name} cost must be between 0 and {TRACKING_COST_BP_MAX:g} bp per side.")
        return IdeaTrackingSettingsRequest(
            per_side_bp=None if self.per_side_bp is None else dict(self.per_side_bp),
            leg_classes=None if self.leg_classes is None else dict(self.leg_classes),
            benchmark=self.benchmark,
        )


class TrackingSummaryModel(BaseModel):
    net_return: float | None = None
    gross_return: float | None = None
    cost_drag: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_drawdown: float | None = None
    sessions: int = 0
    gaps: int = 0
    partial: bool = False
    final: bool = False
    stale_since: date | None = None
    first_session: date | None = None
    as_of: date | None = None


class TrackingBenchmarkModel(BaseModel):
    symbol: str
    available: bool
    reason: str | None = None


class TrackingCostClassModel(BaseModel):
    asset_class: str
    label: str
    basis: str
    per_side_bp: float | None = None
    default_bp: float | None = None
    editable: bool
    source: Literal["stated", "quote", "none"]
    edited: bool = False


class TrackingCostModelViewModel(BaseModel):
    classes: list[TrackingCostClassModel]
    leg_classes: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime | None = None
    edited: bool = False


class TrackingSegmentLegModel(BaseModel):
    key: str
    label: str
    entity_type: str
    normalized_id: str
    stated_weight: float | None = None
    weight: float | None = None
    weight_source: str
    asset_class: str
    detected_class: str
    cost_bp: float | None = None
    market: str
    entry_price: float | None = None
    last_price: float | None = None


class TrackingSegmentModel(BaseModel):
    segment_id: str
    number: int
    status: Literal["untracked", "unavailable", "waiting", "never_entered", "tracking", "exiting", "closed"]
    reason: str | None = None
    started_at: datetime
    start_reason: str
    start_note: str = ""
    ended_at: datetime | None = None
    end_reason: str | None = None
    stance: str
    entry_session: date | None = None
    exit_session: date | None = None
    last_session: date | None = None
    sessions: int = 0
    gaps: int = 0
    gross_return: float | None = None
    net_return: float | None = None
    entry_cost: float | None = None
    exit_cost: float | None = None
    cost: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_drawdown: float | None = None
    legs: list[TrackingSegmentLegModel] = Field(default_factory=list)


class TrackingPointModel(BaseModel):
    session: date
    segment: int
    net_return: float | None = None
    gross_return: float | None = None
    benchmark_return: float | None = None
    drawdown: float | None = None
    gap: bool = False
    missing: list[str] = Field(default_factory=list)


class TrackingProvenanceModel(BaseModel):
    key: str
    label: str
    role: Literal["leg", "benchmark"]
    source_provider: str | None = None
    retrieved_at: datetime | None = None
    origin: str | None = None
    transformation_note: str | None = None
    available: bool = True


class IdeaTrackingResponseModel(BaseModel):
    idea_id: str
    label: str = TRACKING_LABEL
    status: Literal["not_started", "waiting", "tracking", "stopped", "unavailable"]
    status_reason: str | None = None
    methodology: str
    summary: TrackingSummaryModel
    benchmark: TrackingBenchmarkModel
    cost_model: TrackingCostModelViewModel
    segments: list[TrackingSegmentModel] = Field(default_factory=list)
    points: list[TrackingPointModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: list[TrackingProvenanceModel] = Field(default_factory=list)
    computed_at: datetime
    source_provider: str = "gamma_ideas"
    origin: str = "idea_tracking.compute"
    transformation_note: str | None = None


# ---------------------------------------------------------------------------
# Close and review (I3b)
# ---------------------------------------------------------------------------

ReviewOutcomeLiteral = Literal["confirmed", "invalidated", "abandoned", "expired"]
EvidenceVerdictLiteral = Literal["held", "failed", "unclear"]


class IdeaCloseRequestModel(BaseModel):
    outcome: ReviewOutcomeLiteral
    lesson: str = Field(min_length=1, max_length=REVIEW_TEXT_MAX)
    expected: str | None = Field(default=None, max_length=REVIEW_TEXT_MAX)
    realized_note: str = Field(default="", max_length=REVIEW_TEXT_MAX)
    evidence_verdicts: dict[str, EvidenceVerdictLiteral] = Field(default_factory=dict)

    def to_domain(self) -> IdeaCloseRequest:
        return IdeaCloseRequest(
            outcome=self.outcome,
            lesson=self.lesson,
            expected=self.expected,
            realized_note=self.realized_note,
            evidence_verdicts=dict(self.evidence_verdicts),
        )


class IdeaEvidenceVerdictModel(BaseModel):
    evidence_id: str
    verdict: str
    title: str
    stance: str


class IdeaCriterionAtCloseModel(BaseModel):
    criterion_id: str
    kind: str
    label: str
    state: str
    triggered_at: datetime | None = None
    first_met_at: datetime | None = None


class IdeaReviewModel(BaseModel):
    review_id: str
    outcome: str
    lesson: str
    expected: str = ""
    realized_note: str = ""
    opened_at: datetime
    closed_at: datetime
    holding_days: float
    evidence_verdicts: list[IdeaEvidenceVerdictModel] = Field(default_factory=list)
    criteria_at_close: list[IdeaCriterionAtCloseModel] = Field(default_factory=list)
    realized: IdeaTrackingSnapshotModel | None = None
    first_invalidation_at: datetime | None = None

    @classmethod
    def from_domain(cls, review: IdeaReview) -> "IdeaReviewModel":
        payload = review.to_dict()
        payload.pop("schema_version", None)
        payload.pop("idea_id", None)
        return cls(**payload, holding_days=review.holding_days, first_invalidation_at=review.first_invalidation_at)


class IdeaReviewHeadlineModel(BaseModel):
    review_id: str
    outcome: str
    opened_at: datetime
    closed_at: datetime
    holding_days: float
    expected: str = ""
    lesson: str = ""
    invalidation_criteria: int = 0
    first_invalidation_at: datetime | None = None
    evidence_verdicts: dict[str, int] = Field(default_factory=dict)
    realized_at_close: IdeaTrackingSnapshotModel | None = None


class IdeaReviewRowModel(BaseModel):
    idea_id: str
    title: str
    stance: str
    status: str
    tags: list[str] = Field(default_factory=list)
    outcome: str
    opened_at: datetime
    closed_at: datetime
    holding_days: float
    expected: str = ""
    lesson: str = ""
    net_return: float | None = None
    benchmark: str | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    realized_final: bool = False
    realized_as_of: date | None = None
    tracked: bool = False
    invalidation_criteria: int = 0
    first_invalidation_at: datetime | None = None
    evidence_verdicts: dict[str, int] = Field(default_factory=dict)


class IdeaReviewStatsResponseModel(BaseModel):
    rows: list[IdeaReviewRowModel] = Field(default_factory=list)
    outcomes: dict[str, int] = Field(default_factory=dict)
    holding_days: dict[str, Any] = Field(default_factory=dict)
    realized: dict[str, Any] = Field(default_factory=dict)
    invalidation: dict[str, Any] = Field(default_factory=dict)
    label: str = TRACKING_LABEL
    source_provider: str = "gamma_ideas"
    retrieved_at: datetime
    origin: str = "idea_service.review_statistics"
    transformation_note: str | None = (
        "Your own closed ideas only: the review of each current close, with the hypothetical tracking record. No score."
    )

    @classmethod
    def from_domain(cls, result: IdeaReviewStatistics) -> "IdeaReviewStatsResponseModel":
        return cls(
            rows=[IdeaReviewRowModel(**row) for row in result.rows],
            outcomes=result.outcomes,
            holding_days=result.holding_days,
            realized=result.realized,
            invalidation=result.invalidation,
            retrieved_at=result.retrieved_at,
        )


# ---------------------------------------------------------------------------
# Test and risk snapshots (I3c)
# ---------------------------------------------------------------------------


class IdeaSnapshotModelBase(BaseModel):
    snapshot_id: str
    created_at: datetime
    legs: list[IdeaTrackedLegModel]
    benchmark: str
    lookback_days: int
    window_start: date | None = None
    window_end: date | None = None
    observations: int = 0
    source: str = "idea_legs"
    source_ids: dict[str, str] = Field(default_factory=dict)
    provenance: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    stale_reason: str | None = None

    @staticmethod
    def _payload(snapshot: IdeaTestSnapshot | IdeaRiskSnapshot, idea: Idea, now: datetime) -> dict[str, Any]:
        payload = snapshot.to_dict()
        payload.pop("schema_version", None)
        payload.pop("idea_id", None)
        for leg_payload, leg in zip(payload["legs"], snapshot.legs):
            leg_payload["key"] = leg.key
        payload["stale_reason"] = snapshot_staleness(snapshot, idea, now)
        return payload


class IdeaTestSnapshotModel(IdeaSnapshotModelBase):
    metrics: dict[str, float | None] = Field(default_factory=dict)
    leg_contributions: dict[str, float | None] = Field(default_factory=dict)
    equity_curve: list[tuple[date, float]] = Field(default_factory=list)
    benchmark_curve: list[tuple[date, float]] = Field(default_factory=list)
    costs_included: bool = False
    sample: str = "in_sample"

    @classmethod
    def from_domain(cls, snapshot: IdeaTestSnapshot, idea: Idea, now: datetime) -> "IdeaTestSnapshotModel":
        return cls(**cls._payload(snapshot, idea, now))


class IdeaRiskEpisodeModel(BaseModel):
    episode_id: str
    label: str
    start: date
    end: date
    status: str
    book_return: float | None = None
    benchmark_return: float | None = None
    max_drawdown: float | None = None


class IdeaRiskSnapshotModel(IdeaSnapshotModelBase):
    alpha: float
    horizon_days: int = 1
    metrics: dict[str, float | None] = Field(default_factory=dict)
    episodes: list[IdeaRiskEpisodeModel] = Field(default_factory=list)
    worst_episode_id: str | None = None

    @classmethod
    def from_domain(cls, snapshot: IdeaRiskSnapshot, idea: Idea, now: datetime) -> "IdeaRiskSnapshotModel":
        return cls(**cls._payload(snapshot, idea, now))


IdeaModel.model_rebuild()
IdeaSummaryModel.model_rebuild()
