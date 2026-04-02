from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
    portfolio_state: dict[str, Any] | None = None
    research_state: dict[str, Any] | None = None
    risk_state: dict[str, Any] | None = None
    iv_state: dict[str, Any] | None = None


@dataclass(frozen=True)
class CopilotResearchCardRequest:
    domain: str
    prompt: str | None = None
    previous_response_id: str | None = None
    user_session_id: str | None = None
    context: CopilotRequestContext = field(default_factory=CopilotRequestContext)


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
