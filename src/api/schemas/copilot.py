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
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSynthesisRequest,
    CopilotSynthesisScope,
    CopilotSourceRef,
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
    context: CopilotRequestContextModel = Field(default_factory=CopilotRequestContextModel)
    synthesis: CopilotSynthesisRequestModel | None = None

    def to_domain(self) -> CopilotResearchCardRequest:
        return CopilotResearchCardRequest(
            domain=self.domain,
            prompt=self.prompt,
            previous_response_id=self.previous_response_id,
            user_session_id=self.user_session_id,
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
