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
    estimated_tool_calls: int = 0
    estimated_provider_calls: int = 0
    estimated_latency_ms: int = 0


@dataclass(frozen=True)
class CopilotResearchPlanDomainDecision:
    domain: str
    used: bool
    reason: str


@dataclass(frozen=True)
class CopilotResearchPlan:
    intent: str
    target_entities: list[CopilotResearchPlanEntity] = field(default_factory=list)
    depth_profile: str = "standard"
    domain_plan: list[CopilotResearchPlanDomain] = field(default_factory=list)
    domain_decisions: list[CopilotResearchPlanDomainDecision] = field(default_factory=list)
    max_tool_calls: int = 0
    max_provider_calls: int = 0
    max_elapsed_ms: int = 0
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
    permission_policy: str = "automatic"
    provenance_behavior: str = "Returns Gamma source references and warnings where available."
    retry_policy: str = "retry_safe_if_read_only"
    can_call_external_providers: bool = False
    test_coverage_owner: str | None = None


@dataclass(frozen=True)
class CopilotOperatorPlanStep:
    step_id: str
    order: int
    title: str
    domain: str
    action_type: str
    tool_id: str | None = None
    status: str = "planned"
    permission_policy: str = "automatic"
    requires_confirmation: bool = False
    expected_artifacts: list[str] = field(default_factory=list)
    rationale: str | None = None
    stop_conditions: list[str] = field(default_factory=list)
    estimated_latency_ms: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotOperatorConfirmationCheckpoint:
    checkpoint_id: str
    after_step_id: str
    reason: str
    required_for_tool_ids: list[str] = field(default_factory=list)
    default_policy: str = "confirmation_required"


@dataclass(frozen=True)
class CopilotOperatorProgressEvent:
    run_id: str
    event_id: str
    sequence: int
    event_type: str
    timestamp: datetime = field(default_factory=now_utc)
    step_id: str | None = None
    tool_id: str | None = None
    title: str | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotOperatorPlan:
    intent: str
    target_entities: list[CopilotResearchPlanEntity] = field(default_factory=list)
    depth_profile: str = "standard"
    role: str = "research_operator"
    research_plan: CopilotResearchPlan | None = None
    steps: list[CopilotOperatorPlanStep] = field(default_factory=list)
    confirmation_checkpoints: list[CopilotOperatorConfirmationCheckpoint] = field(default_factory=list)
    max_tool_calls: int = 0
    max_provider_calls: int = 0
    max_elapsed_ms: int = 0
    requires_confirmation: bool = False
    expected_artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=now_utc)
    source_provider: str = "gamma_operator_planner"
    origin: str = "copilot_service.plan_research_operator"
    transformation_note: str | None = "Deterministic Research Operator plan; no tools were executed."


@dataclass(frozen=True)
class CopilotMutationDiffEntry:
    path: str
    label: str
    before: Any = None
    after: Any = None
    unit: str | None = None
    change_type: str = "update"


@dataclass(frozen=True)
class CopilotDraftMutation:
    mutation_id: str
    domain: str
    tool_id: str
    action_type: str
    target_id: str
    target_label: str
    status: str
    requires_confirmation: bool
    confirmation_token: str
    diff: list[CopilotMutationDiffEntry] = field(default_factory=list)
    rendered_diff: list[str] = field(default_factory=list)
    proposed_payload: dict[str, Any] = field(default_factory=dict)
    rationale: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    rollback_snapshot_id: str | None = None
    created_at: datetime = field(default_factory=now_utc)
    expires_at: datetime | None = None
    applied_at: datetime | None = None
    source_provider: str = "gamma_copilot"
    origin: str = "copilot_service.mutation"
    transformation_note: str | None = "Gamma draft mutation generated for explicit confirmation before local research-state changes are applied."


@dataclass(frozen=True)
class CopilotMutationApplyResult:
    mutation: CopilotDraftMutation
    artifact: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


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
    operator_events: list[CopilotOperatorProgressEvent] = field(default_factory=list)
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


@dataclass(frozen=True)
class CopilotReportToolTraceSummary:
    tool_name: str
    summary: str
    source_ids: list[str] = field(default_factory=list)
    status: str = "recorded"
    step_id: str | None = None
    event_type: str | None = None
    output_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotReportWarningProvenance:
    warning: str
    source_ids: list[str] = field(default_factory=list)
    tool_name: str | None = None
    step_id: str | None = None
    event_type: str | None = None
    event_id: str | None = None
    sequence: int | None = None


@dataclass(frozen=True)
class CopilotResearchReport:
    report_id: str
    session_id: str
    title: str
    source_turn_ids: list[str] = field(default_factory=list)
    source_memo_ids: list[str] = field(default_factory=list)
    source_backed_claims: list[ResearchClaim] = field(default_factory=list)
    inferred_claims: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    warning_provenance: list[CopilotReportWarningProvenance] = field(default_factory=list)
    tool_trace_summary: list[CopilotReportToolTraceSummary] = field(default_factory=list)
    sources: list[CopilotSourceRef] = field(default_factory=list)
    generated_at: datetime = field(default_factory=now_utc)
    source_provider: str = "gamma_copilot"
    origin: str = "copilot_report_service.generate_report"
    transformation_note: str | None = "Gamma research report generated from persisted read-only Copilot session traces."


def new_copilot_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
