from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.models.copilot_context import default_copilot_read_only_safety
from src.utils.time import now_utc


@dataclass(frozen=True)
class MacroCopilotContext:
    mode: str = "snapshot"
    region: str = "US"
    timeframe: str = "3M"
    theme: str = "all"
    comparison_region: str | None = None


@dataclass(frozen=True)
class CopilotRequestContext:
    current_tab: str = "portfolio"
    workspace_mode: str | None = None
    macro: MacroCopilotContext | None = None
    prediction_market_id: str | None = None
    crypto_token_id: str | None = None
    fundamentals_ticker: str | None = None
    fundamentals_state: dict[str, Any] | None = None
    commodities_state: dict[str, Any] | None = None
    portfolio_state: dict[str, Any] | None = None
    research_state: dict[str, Any] | None = None
    strategy_lab_state: dict[str, Any] | None = None
    risk_state: dict[str, Any] | None = None
    iv_state: dict[str, Any] | None = None


@dataclass(frozen=True)
class CopilotSynthesisScope:
    domain: str
    label: str | None = None
    context_fingerprint: str | None = None
    context: CopilotRequestContext = field(default_factory=CopilotRequestContext)


@dataclass(frozen=True)
class CopilotSynthesisRequest:
    active_tab: str | None = None
    included_scopes: list[CopilotSynthesisScope] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotResearchCardRequest:
    domain: str
    prompt: str | None = None
    previous_response_id: str | None = None
    user_session_id: str | None = None
    context_fingerprint: str | None = None
    session_title: str | None = None
    context: CopilotRequestContext = field(default_factory=CopilotRequestContext)
    synthesis: CopilotSynthesisRequest | None = None


@dataclass(frozen=True)
class CopilotResearchPlanEntity:
    kind: str
    id: str
    label: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class CopilotResearchPlanDomain:
    domain: str
    depth: str
    reason: str
    action_type: str = "read_context"
    planned_tools: list[str] = field(default_factory=list)
    required_context: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotResearchPlan:
    intent: str
    target_entities: list[CopilotResearchPlanEntity] = field(default_factory=list)
    depth_profile: str = "standard"
    domain_plan: list[CopilotResearchPlanDomain] = field(default_factory=list)
    requires_confirmation: bool = False
    expected_artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=now_utc)
    source_provider: str = "gamma_planner"
    origin: str = "copilot_service.plan_research"
    transformation_note: str | None = "Deterministic planner-only Copilot V2 prototype; no tools were executed."


@dataclass(frozen=True)
class CopilotResearchActionDefinition:
    tool_id: str
    domains: list[str]
    action_type: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    mutates_local_state: bool = False
    requires_confirmation: bool = False
    external_provider: str | None = None
    timeout_seconds: float = 30.0
    request_limit: int = 1
    failure_modes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotSourceRef:
    source_id: str
    label: str
    kind: str
    provider: str
    origin: str
    description: str | None = None
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class CopilotToolTrace:
    tool_name: str
    summary: str
    arguments: dict[str, Any] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchClaim:
    claim: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchCard:
    title: str
    hypothesis: str
    rationale: str
    required_data: list[str] = field(default_factory=list)
    proposed_test: str = ""
    confounders: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    source_backed_claims: list[ResearchClaim] = field(default_factory=list)
    inferred_claims: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotContextBundle:
    domain: str
    current_tab: str
    summary_data: dict[str, Any]
    tool_state: dict[str, Any] = field(default_factory=dict)
    sources: list[CopilotSourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    read_only_safety: dict[str, Any] = field(default_factory=default_copilot_read_only_safety)


@dataclass(frozen=True)
class CopilotToolExecution:
    output: dict[str, Any] | list[Any] | str
    trace: CopilotToolTrace
    sources: list[CopilotSourceRef] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotResearchCardResult:
    domain: str
    current_tab: str
    status: str
    provider: str
    model: str | None = None
    response_id: str | None = None
    message: str | None = None
    card: ResearchCard | None = None
    sources: list[CopilotSourceRef] = field(default_factory=list)
    tool_traces: list[CopilotToolTrace] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotContextSnapshot:
    snapshot_id: str
    domain: str
    context_fingerprint: str | None
    current_tab: str
    workspace_mode: str | None
    summary: dict[str, Any] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now_utc)
    read_only_safety: dict[str, Any] = field(default_factory=default_copilot_read_only_safety)


@dataclass(frozen=True)
class CopilotTurn:
    turn_id: str
    session_id: str
    turn_index: int
    domain: str
    prompt: str
    context_snapshot_id: str
    result: CopilotResearchCardResult
    created_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class CopilotSession:
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    active_domain: str | None = None
    active_context_fingerprint: str | None = None
    turn_count: int = 0
    memo_count: int = 0
    warnings: list[str] = field(default_factory=list)
    archived_at: datetime | None = None


@dataclass(frozen=True)
class CopilotMemo:
    memo_id: str
    session_id: str
    title: str
    body: str
    source_turn_ids: list[str] = field(default_factory=list)
    source_snapshot_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = "gamma_copilot"
    origin: str = "copilot_store.memo"
    transformation_note: str | None = "Gamma memo generated from persisted read-only Copilot turns."


def new_copilot_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
