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
    CopilotMemo,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
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
    result: ResearchAnalyzeResponseModel | None = None


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
            warnings=list(row.warnings),
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
