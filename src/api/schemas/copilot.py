from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.api.schemas.iv import IVSessionStatusResponseModel, IVSurfaceResponseModel
from src.api.schemas.portfolio import (
    PortfolioHistoryResponseModel,
    PortfolioPerformanceResponseModel,
    PortfolioSnapshotModel,
)
from src.api.schemas.research import ResearchAnalyzeResponseModel
from src.api.schemas.risk import RiskComputeResponseModel
from src.models.copilot import (
    CopilotDraftMutation,
    CopilotMemo,
    CopilotMutationApplyResult,
    CopilotMutationDiffEntry,
    CopilotOperatorConfirmationCheckpoint,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotResearchActionDefinition,
    CopilotResearchPlan,
    CopilotResearchPlanDomainDecision,
    CopilotResearchPlanDomain,
    CopilotResearchPlanEntity,
    CopilotResearchReport,
    CopilotReportWarningProvenance,
    CopilotReportToolTraceSummary,
    CopilotSession,
    CopilotSynthesisRequest,
    CopilotSynthesisScope,
    CopilotSourceRef,
    CopilotTurn,
    CopilotToolTrace,
    MacroCopilotContext,
    ResearchCard,
    ResearchClaim,
)


class MacroCopilotContextModel(BaseModel):
    mode: str = "snapshot"
    region: str = "US"
    timeframe: str = "3M"
    theme: str = "all"
    comparison_region: str | None = None

    def to_domain(self) -> MacroCopilotContext:
        return MacroCopilotContext(
            mode=self.mode,
            region=self.region,
            timeframe=self.timeframe,
            theme=self.theme,
            comparison_region=self.comparison_region,
        )


class CopilotPortfolioStateModel(BaseModel):
    snapshot: PortfolioSnapshotModel | None = None
    history: PortfolioHistoryResponseModel | None = None
    performance: PortfolioPerformanceResponseModel | None = None


class CopilotResearchStateModel(BaseModel):
    overview: dict[str, object] | None = None
    result: ResearchAnalyzeResponseModel | None = None
    strategy_result: dict[str, object] | None = None
    strategy_composition: dict[str, object] | None = None


class CopilotRiskStateModel(BaseModel):
    snapshot: PortfolioSnapshotModel | None = None
    result: RiskComputeResponseModel | None = None


class CopilotIvStateModel(BaseModel):
    surface: IVSurfaceResponseModel | None = None
    session: IVSessionStatusResponseModel | None = None


class CopilotRequestContextModel(BaseModel):
    current_tab: str = "portfolio"
    workspace_mode: str | None = None
    macro: MacroCopilotContextModel | None = None
    prediction_market_id: str | None = None
    crypto_token_id: str | None = None
    fundamentals_ticker: str | None = None
    fundamentals_state: dict[str, object] | None = None
    commodities_state: dict[str, object] | None = None
    portfolio_state: CopilotPortfolioStateModel | None = None
    research_state: CopilotResearchStateModel | None = None
    strategy_lab_state: dict[str, object] | None = None
    risk_state: CopilotRiskStateModel | None = None
    iv_state: CopilotIvStateModel | None = None

    def to_domain(self) -> CopilotRequestContext:
        return CopilotRequestContext(
            current_tab=self.current_tab,
            workspace_mode=self.workspace_mode,
            macro=self.macro.to_domain() if self.macro is not None else None,
            prediction_market_id=self.prediction_market_id,
            crypto_token_id=self.crypto_token_id,
            fundamentals_ticker=self.fundamentals_ticker,
            fundamentals_state=self.fundamentals_state,
            commodities_state=self.commodities_state,
            portfolio_state=self.portfolio_state.model_dump(mode="python") if self.portfolio_state is not None else None,
            research_state=self.research_state.model_dump(mode="python") if self.research_state is not None else None,
            strategy_lab_state=self.strategy_lab_state,
            risk_state=self.risk_state.model_dump(mode="python") if self.risk_state is not None else None,
            iv_state=self.iv_state.model_dump(mode="python") if self.iv_state is not None else None,
        )


class CopilotSynthesisScopeModel(BaseModel):
    domain: str
    label: str | None = None
    context_fingerprint: str | None = None
    context: CopilotRequestContextModel = Field(default_factory=CopilotRequestContextModel)

    def to_domain(self) -> CopilotSynthesisScope:
        return CopilotSynthesisScope(
            domain=self.domain,
            label=self.label,
            context_fingerprint=self.context_fingerprint,
            context=self.context.to_domain(),
        )


class CopilotSynthesisRequestModel(BaseModel):
    active_tab: str | None = None
    included_scopes: list[CopilotSynthesisScopeModel] = Field(default_factory=list)

    def to_domain(self) -> CopilotSynthesisRequest:
        return CopilotSynthesisRequest(
            active_tab=self.active_tab,
            included_scopes=[item.to_domain() for item in self.included_scopes],
        )


class CopilotResearchCardRequestModel(BaseModel):
    domain: str
    prompt: str | None = None
    previous_response_id: str | None = None
    user_session_id: str | None = None
    context_fingerprint: str | None = None
    session_title: str | None = None
    context: CopilotRequestContextModel = Field(default_factory=CopilotRequestContextModel)
    synthesis: CopilotSynthesisRequestModel | None = None

    def to_domain(self) -> CopilotResearchCardRequest:
        return CopilotResearchCardRequest(
            domain=self.domain,
            prompt=self.prompt,
            previous_response_id=self.previous_response_id,
            user_session_id=self.user_session_id,
            context_fingerprint=self.context_fingerprint,
            session_title=self.session_title,
            context=self.context.to_domain(),
            synthesis=self.synthesis.to_domain() if self.synthesis is not None else None,
        )


class CopilotSourceRefModel(BaseModel):
    source_id: str
    label: str
    kind: str
    provider: str
    origin: str
    description: str | None = None
    retrieved_at: datetime | None = None

    @classmethod
    def from_domain(cls, row: CopilotSourceRef) -> "CopilotSourceRefModel":
        return cls(**row.__dict__)


class CopilotToolTraceModel(BaseModel):
    tool_name: str
    summary: str
    arguments: dict[str, object] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotToolTrace) -> "CopilotToolTraceModel":
        return cls(**row.__dict__)


class CopilotOperatorProgressEventModel(BaseModel):
    run_id: str
    event_id: str
    sequence: int
    event_type: str
    timestamp: datetime
    step_id: str | None = None
    tool_id: str | None = None
    title: str | None = None
    message: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotOperatorProgressEvent) -> "CopilotOperatorProgressEventModel":
        return cls(
            run_id=row.run_id,
            event_id=row.event_id,
            sequence=row.sequence,
            event_type=row.event_type,
            timestamp=row.timestamp,
            step_id=row.step_id,
            tool_id=row.tool_id,
            title=row.title,
            message=row.message,
            payload=dict(row.payload),
            source_ids=list(row.source_ids),
            warnings=list(row.warnings),
        )


class ResearchClaimModel(BaseModel):
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchClaim) -> "ResearchClaimModel":
        return cls(**row.__dict__)


class ResearchCardModel(BaseModel):
    title: str
    hypothesis: str
    rationale: str
    required_data: list[str] = Field(default_factory=list)
    proposed_test: str
    confounders: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_backed_claims: list[ResearchClaimModel] = Field(default_factory=list)
    inferred_claims: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchCard) -> "ResearchCardModel":
        return cls(
            title=row.title,
            hypothesis=row.hypothesis,
            rationale=row.rationale,
            required_data=list(row.required_data),
            proposed_test=row.proposed_test,
            confounders=list(row.confounders),
            next_steps=list(row.next_steps),
            caveats=list(row.caveats),
            source_backed_claims=[ResearchClaimModel.from_domain(item) for item in row.source_backed_claims],
            inferred_claims=list(row.inferred_claims),
        )


class CopilotResearchCardResponseModel(BaseModel):
    domain: str
    current_tab: str
    status: str
    provider: str
    model: str | None = None
    response_id: str | None = None
    message: str | None = None
    card: ResearchCardModel | None = None
    sources: list[CopilotSourceRefModel] = Field(default_factory=list)
    tool_traces: list[CopilotToolTraceModel] = Field(default_factory=list)
    operator_events: list[CopilotOperatorProgressEventModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotResearchCardResult) -> "CopilotResearchCardResponseModel":
        return cls(
            domain=row.domain,
            current_tab=row.current_tab,
            status=row.status,
            provider=row.provider,
            model=row.model,
            response_id=row.response_id,
            message=row.message,
            card=ResearchCardModel.from_domain(row.card) if row.card is not None else None,
            sources=[CopilotSourceRefModel.from_domain(item) for item in row.sources],
            tool_traces=[CopilotToolTraceModel.from_domain(item) for item in row.tool_traces],
            operator_events=[CopilotOperatorProgressEventModel.from_domain(item) for item in row.operator_events],
            warnings=list(row.warnings),
        )


class CopilotResearchPlanEntityModel(BaseModel):
    kind: str
    id: str
    label: str | None = None
    confidence: float | None = None

    @classmethod
    def from_domain(cls, row: CopilotResearchPlanEntity) -> "CopilotResearchPlanEntityModel":
        return cls(**row.__dict__)


class CopilotResearchPlanDomainModel(BaseModel):
    domain: str
    depth: str
    reason: str
    action_type: str
    planned_tools: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    estimated_tool_calls: int = 0
    estimated_provider_calls: int = 0
    estimated_latency_ms: int = 0

    @classmethod
    def from_domain(cls, row: CopilotResearchPlanDomain) -> "CopilotResearchPlanDomainModel":
        return cls(
            domain=row.domain,
            depth=row.depth,
            reason=row.reason,
            action_type=row.action_type,
            planned_tools=list(row.planned_tools),
            required_context=list(row.required_context),
            estimated_tool_calls=row.estimated_tool_calls,
            estimated_provider_calls=row.estimated_provider_calls,
            estimated_latency_ms=row.estimated_latency_ms,
        )


class CopilotResearchPlanDomainDecisionModel(BaseModel):
    domain: str
    used: bool
    reason: str

    @classmethod
    def from_domain(cls, row: CopilotResearchPlanDomainDecision) -> "CopilotResearchPlanDomainDecisionModel":
        return cls(**row.__dict__)


class CopilotResearchPlanModel(BaseModel):
    intent: str
    target_entities: list[CopilotResearchPlanEntityModel] = Field(default_factory=list)
    depth_profile: str
    domain_plan: list[CopilotResearchPlanDomainModel] = Field(default_factory=list)
    domain_decisions: list[CopilotResearchPlanDomainDecisionModel] = Field(default_factory=list)
    max_tool_calls: int = 0
    max_provider_calls: int = 0
    max_elapsed_ms: int = 0
    requires_confirmation: bool
    expected_artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime
    source_provider: str
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotResearchPlan) -> "CopilotResearchPlanModel":
        return cls(
            intent=row.intent,
            target_entities=[CopilotResearchPlanEntityModel.from_domain(item) for item in row.target_entities],
            depth_profile=row.depth_profile,
            domain_plan=[CopilotResearchPlanDomainModel.from_domain(item) for item in row.domain_plan],
            domain_decisions=[CopilotResearchPlanDomainDecisionModel.from_domain(item) for item in row.domain_decisions],
            max_tool_calls=row.max_tool_calls,
            max_provider_calls=row.max_provider_calls,
            max_elapsed_ms=row.max_elapsed_ms,
            requires_confirmation=row.requires_confirmation,
            expected_artifacts=list(row.expected_artifacts),
            warnings=list(row.warnings),
            generated_at=row.generated_at,
            source_provider=row.source_provider,
            origin=row.origin,
            transformation_note=row.transformation_note,
        )


class CopilotResearchActionDefinitionModel(BaseModel):
    tool_id: str
    domains: list[str] = Field(default_factory=list)
    action_type: str
    description: str
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    read_only: bool = True
    mutates_local_state: bool = False
    requires_confirmation: bool = False
    external_provider: str | None = None
    timeout_seconds: float = 30.0
    request_limit: int = 1
    failure_modes: list[str] = Field(default_factory=list)
    permission_policy: str = "automatic"
    provenance_behavior: str
    retry_policy: str
    can_call_external_providers: bool = False
    test_coverage_owner: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotResearchActionDefinition) -> "CopilotResearchActionDefinitionModel":
        return cls(
            tool_id=row.tool_id,
            domains=list(row.domains),
            action_type=row.action_type,
            description=row.description,
            input_schema=dict(row.input_schema),
            output_schema=dict(row.output_schema),
            read_only=row.read_only,
            mutates_local_state=row.mutates_local_state,
            requires_confirmation=row.requires_confirmation,
            external_provider=row.external_provider,
            timeout_seconds=row.timeout_seconds,
            request_limit=row.request_limit,
            failure_modes=list(row.failure_modes),
            permission_policy=row.permission_policy,
            provenance_behavior=row.provenance_behavior,
            retry_policy=row.retry_policy,
            can_call_external_providers=row.can_call_external_providers,
            test_coverage_owner=row.test_coverage_owner,
        )


class CopilotOperatorPlanStepModel(BaseModel):
    step_id: str
    order: int
    title: str
    domain: str
    action_type: str
    tool_id: str | None = None
    status: str = "planned"
    permission_policy: str = "automatic"
    requires_confirmation: bool = False
    expected_artifacts: list[str] = Field(default_factory=list)
    rationale: str | None = None
    stop_conditions: list[str] = Field(default_factory=list)
    estimated_latency_ms: int = 0
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotOperatorPlanStep) -> "CopilotOperatorPlanStepModel":
        return cls(
            step_id=row.step_id,
            order=row.order,
            title=row.title,
            domain=row.domain,
            action_type=row.action_type,
            tool_id=row.tool_id,
            status=row.status,
            permission_policy=row.permission_policy,
            requires_confirmation=row.requires_confirmation,
            expected_artifacts=list(row.expected_artifacts),
            rationale=row.rationale,
            stop_conditions=list(row.stop_conditions),
            estimated_latency_ms=row.estimated_latency_ms,
            warnings=list(row.warnings),
        )


class CopilotOperatorConfirmationCheckpointModel(BaseModel):
    checkpoint_id: str
    after_step_id: str
    reason: str
    required_for_tool_ids: list[str] = Field(default_factory=list)
    default_policy: str = "confirmation_required"

    @classmethod
    def from_domain(
        cls,
        row: CopilotOperatorConfirmationCheckpoint,
    ) -> "CopilotOperatorConfirmationCheckpointModel":
        return cls(
            checkpoint_id=row.checkpoint_id,
            after_step_id=row.after_step_id,
            reason=row.reason,
            required_for_tool_ids=list(row.required_for_tool_ids),
            default_policy=row.default_policy,
        )


class CopilotOperatorPlanModel(BaseModel):
    intent: str
    target_entities: list[CopilotResearchPlanEntityModel] = Field(default_factory=list)
    depth_profile: str
    role: str = "research_operator"
    research_plan: CopilotResearchPlanModel | None = None
    steps: list[CopilotOperatorPlanStepModel] = Field(default_factory=list)
    confirmation_checkpoints: list[CopilotOperatorConfirmationCheckpointModel] = Field(default_factory=list)
    max_tool_calls: int = 0
    max_provider_calls: int = 0
    max_elapsed_ms: int = 0
    requires_confirmation: bool = False
    expected_artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime
    source_provider: str
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotOperatorPlan) -> "CopilotOperatorPlanModel":
        return cls(
            intent=row.intent,
            target_entities=[CopilotResearchPlanEntityModel.from_domain(item) for item in row.target_entities],
            depth_profile=row.depth_profile,
            role=row.role,
            research_plan=CopilotResearchPlanModel.from_domain(row.research_plan) if row.research_plan else None,
            steps=[CopilotOperatorPlanStepModel.from_domain(item) for item in row.steps],
            confirmation_checkpoints=[
                CopilotOperatorConfirmationCheckpointModel.from_domain(item)
                for item in row.confirmation_checkpoints
            ],
            max_tool_calls=row.max_tool_calls,
            max_provider_calls=row.max_provider_calls,
            max_elapsed_ms=row.max_elapsed_ms,
            requires_confirmation=row.requires_confirmation,
            expected_artifacts=list(row.expected_artifacts),
            warnings=list(row.warnings),
            generated_at=row.generated_at,
            source_provider=row.source_provider,
            origin=row.origin,
            transformation_note=row.transformation_note,
        )


class CopilotSessionModel(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    active_domain: str | None = None
    active_context_fingerprint: str | None = None
    turn_count: int = 0
    memo_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    archived_at: datetime | None = None

    @classmethod
    def from_domain(cls, row: CopilotSession) -> "CopilotSessionModel":
        return cls(**row.__dict__)


class CopilotTurnModel(BaseModel):
    turn_id: str
    session_id: str
    turn_index: int
    domain: str
    prompt: str
    context_snapshot_id: str
    result: CopilotResearchCardResponseModel
    created_at: datetime

    @classmethod
    def from_domain(cls, row: CopilotTurn) -> "CopilotTurnModel":
        return cls(
            turn_id=row.turn_id,
            session_id=row.session_id,
            turn_index=row.turn_index,
            domain=row.domain,
            prompt=row.prompt,
            context_snapshot_id=row.context_snapshot_id,
            result=CopilotResearchCardResponseModel.from_domain(row.result),
            created_at=row.created_at,
        )


class CopilotSessionDetailModel(BaseModel):
    session: CopilotSessionModel
    turns: list[CopilotTurnModel] = Field(default_factory=list)
    memos: list["CopilotMemoModel"] = Field(default_factory=list)


class CopilotMemoModel(BaseModel):
    memo_id: str
    session_id: str
    title: str
    body: str
    source_turn_ids: list[str] = Field(default_factory=list)
    source_snapshot_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotMemo) -> "CopilotMemoModel":
        return cls(**row.__dict__)


class CopilotMemoCreateRequestModel(BaseModel):
    session_id: str
    title: str | None = None
    notes: str | None = None
    source_turn_ids: list[str] = Field(default_factory=list)


class CopilotMemoUpdateRequestModel(BaseModel):
    title: str | None = None
    body: str | None = None


class CopilotReportToolTraceSummaryModel(BaseModel):
    tool_name: str
    summary: str
    source_ids: list[str] = Field(default_factory=list)
    status: str = "recorded"
    step_id: str | None = None
    event_type: str | None = None
    output_summary: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotReportToolTraceSummary) -> "CopilotReportToolTraceSummaryModel":
        return cls(**row.__dict__)


class CopilotReportWarningProvenanceModel(BaseModel):
    warning: str
    source_ids: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    step_id: str | None = None
    event_type: str | None = None
    event_id: str | None = None
    sequence: int | None = None

    @classmethod
    def from_domain(cls, row: CopilotReportWarningProvenance) -> "CopilotReportWarningProvenanceModel":
        return cls(**row.__dict__)


class CopilotResearchReportModel(BaseModel):
    report_id: str
    session_id: str
    title: str
    source_turn_ids: list[str] = Field(default_factory=list)
    source_memo_ids: list[str] = Field(default_factory=list)
    source_backed_claims: list[ResearchClaimModel] = Field(default_factory=list)
    inferred_claims: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    warning_provenance: list[CopilotReportWarningProvenanceModel] = Field(default_factory=list)
    tool_trace_summary: list[CopilotReportToolTraceSummaryModel] = Field(default_factory=list)
    sources: list[CopilotSourceRefModel] = Field(default_factory=list)
    generated_at: datetime
    source_provider: str
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotResearchReport) -> "CopilotResearchReportModel":
        return cls(
            report_id=row.report_id,
            session_id=row.session_id,
            title=row.title,
            source_turn_ids=list(row.source_turn_ids),
            source_memo_ids=list(row.source_memo_ids),
            source_backed_claims=[ResearchClaimModel.from_domain(item) for item in row.source_backed_claims],
            inferred_claims=list(row.inferred_claims),
            assumptions=list(row.assumptions),
            missing_data=list(row.missing_data),
            warnings=list(row.warnings),
            warning_provenance=[
                CopilotReportWarningProvenanceModel.from_domain(item)
                for item in row.warning_provenance
            ],
            tool_trace_summary=[CopilotReportToolTraceSummaryModel.from_domain(item) for item in row.tool_trace_summary],
            sources=[CopilotSourceRefModel.from_domain(item) for item in row.sources],
            generated_at=row.generated_at,
            source_provider=row.source_provider,
            origin=row.origin,
            transformation_note=row.transformation_note,
        )


class CopilotResearchReportRequestModel(BaseModel):
    title: str | None = None
    notes: str | None = None
    source_turn_ids: list[str] = Field(default_factory=list)
    source_memo_ids: list[str] = Field(default_factory=list)


class CopilotMutationDiffEntryModel(BaseModel):
    path: str
    label: str
    before: object | None = None
    after: object | None = None
    unit: str | None = None
    change_type: str = "update"

    @classmethod
    def from_domain(cls, row: CopilotMutationDiffEntry) -> "CopilotMutationDiffEntryModel":
        return cls(**row.__dict__)


class CopilotDraftMutationModel(BaseModel):
    mutation_id: str
    domain: str
    tool_id: str
    action_type: str
    target_id: str
    target_label: str
    status: str
    requires_confirmation: bool
    confirmation_token: str
    diff: list[CopilotMutationDiffEntryModel] = Field(default_factory=list)
    rendered_diff: list[str] = Field(default_factory=list)
    proposed_payload: dict[str, object] = Field(default_factory=dict)
    rationale: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    rollback_snapshot_id: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    applied_at: datetime | None = None
    source_provider: str
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CopilotDraftMutation) -> "CopilotDraftMutationModel":
        return cls(
            mutation_id=row.mutation_id,
            domain=row.domain,
            tool_id=row.tool_id,
            action_type=row.action_type,
            target_id=row.target_id,
            target_label=row.target_label,
            status=row.status,
            requires_confirmation=row.requires_confirmation,
            confirmation_token=row.confirmation_token,
            diff=[CopilotMutationDiffEntryModel.from_domain(item) for item in row.diff],
            rendered_diff=list(row.rendered_diff),
            proposed_payload=dict(row.proposed_payload),
            rationale=row.rationale,
            warnings=list(row.warnings),
            source_ids=list(row.source_ids),
            rollback_snapshot_id=row.rollback_snapshot_id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            applied_at=row.applied_at,
            source_provider=row.source_provider,
            origin=row.origin,
            transformation_note=row.transformation_note,
        )


class CopilotFundamentalsDcfMutationScenarioModel(BaseModel):
    assumptions: dict[str, object] = Field(default_factory=dict)
    overrides: dict[str, list[float | None]] = Field(default_factory=dict)


class CopilotFundamentalsDcfMutationRequestModel(BaseModel):
    ticker: str
    scenario_id: str = "base"
    active_scenario_id: str | None = None
    assumptions: dict[str, object] = Field(default_factory=dict)
    overrides: dict[str, list[float | None]] = Field(default_factory=dict)
    rationale: str | None = None


class CopilotMutationApplyRequestModel(BaseModel):
    confirmation_token: str


class CopilotMutationApplyResultModel(BaseModel):
    mutation: CopilotDraftMutationModel
    artifact: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CopilotMutationApplyResult) -> "CopilotMutationApplyResultModel":
        return cls(
            mutation=CopilotDraftMutationModel.from_domain(row.mutation),
            artifact=dict(row.artifact),
            warnings=list(row.warnings),
        )
