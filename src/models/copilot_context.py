from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.models.handoff import HandoffEntity, HandoffTimeframe
from src.models.provenance import ProvenanceSummary
from src.utils.time import now_utc


COPILOT_CONTEXT_CONTRACT_VERSION = "copilot.context.v2"


@dataclass(frozen=True)
class CopilotHeadlineMetric:
    metric_id: str
    label: str
    value: Any = None
    display_value: str | None = None
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "label": self.label,
            "value": self.value,
            "display_value": self.display_value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class CopilotDrilldownTool:
    tool_id: str
    label: str
    description: str
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "label": self.label,
            "description": self.description,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class CopilotReadOnlySafety:
    read_only: bool = True
    mutation_allowed: bool = False
    execution_allowed: bool = False
    notes: list[str] = field(default_factory=lambda: list(DEFAULT_COPILOT_READ_ONLY_NOTES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "read_only": self.read_only,
            "mutation_allowed": self.mutation_allowed,
            "execution_allowed": self.execution_allowed,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CopilotContextBudget:
    """Explicit serialized-size guard for one selectable Copilot scope."""

    scope_budget_bytes: int
    total_budget_bytes: int
    original_bytes: int
    final_bytes: int
    within_scope_budget: bool
    within_total_budget: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_budget_bytes": self.scope_budget_bytes,
            "total_budget_bytes": self.total_budget_bytes,
            "original_bytes": self.original_bytes,
            "final_bytes": self.final_bytes,
            "within_scope_budget": self.within_scope_budget,
            "within_total_budget": self.within_total_budget,
        }


@dataclass(frozen=True)
class CopilotContextFreshness:
    """Freshness/invalidation state derived from normalized source metadata."""

    status: str
    valid: bool
    latest_retrieved_at: datetime | None = None
    source_retrievals: dict[str, str | None] = field(default_factory=dict)
    stale_reasons: list[str] = field(default_factory=list)
    supplied_fingerprint: str | None = None
    invalidated_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "valid": self.valid,
            "latest_retrieved_at": self.latest_retrieved_at.isoformat() if self.latest_retrieved_at else None,
            "source_retrievals": dict(self.source_retrievals),
            "stale_reasons": list(self.stale_reasons),
            "supplied_fingerprint": self.supplied_fingerprint,
            "invalidated_fingerprint": self.invalidated_fingerprint,
        }


@dataclass(frozen=True)
class CopilotContextCompaction:
    """Deterministic disclosure of any context reduction."""

    applied: bool = False
    strategy: str = "none"
    omitted_sections: list[dict[str, Any]] = field(default_factory=list)
    preserved_fields: list[str] = field(default_factory=list)
    omitted_domains: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "strategy": self.strategy,
            "omitted_sections": list(self.omitted_sections),
            "preserved_fields": list(self.preserved_fields),
            "omitted_domains": list(self.omitted_domains),
        }


@dataclass(frozen=True)
class CopilotScopeContextContract:
    """Versioned replay-safe contract attached to every selectable scope.

    The contract stores canonical selectors, content/source digests, size
    accounting, compaction disclosure, and freshness. Provider payloads and
    credentials are deliberately excluded.
    """

    scope: str
    current_tab: str
    context_fingerprint: str
    selectors: dict[str, Any]
    content_digest: str
    source_versions: list[dict[str, Any]]
    budget: CopilotContextBudget
    freshness: CopilotContextFreshness
    compaction: CopilotContextCompaction
    contract_version: str = COPILOT_CONTEXT_CONTRACT_VERSION
    generated_at: datetime = field(default_factory=now_utc)
    origin: str = "gamma.copilot.context_contract.v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "scope": self.scope,
            "current_tab": self.current_tab,
            "context_fingerprint": self.context_fingerprint,
            "selectors": dict(self.selectors),
            "content_digest": self.content_digest,
            "source_versions": list(self.source_versions),
            "budget": self.budget.to_dict(),
            "freshness": self.freshness.to_dict(),
            "compaction": self.compaction.to_dict(),
            "generated_at": self.generated_at.isoformat(),
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CopilotScopeContextContract":
        budget = dict(payload.get("budget") or {})
        freshness = dict(payload.get("freshness") or {})
        compaction = dict(payload.get("compaction") or {})

        def parse_datetime(value: Any) -> datetime | None:
            if isinstance(value, datetime):
                return value
            if not isinstance(value, str) or not value.strip():
                return None
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        return cls(
            scope=str(payload.get("scope") or "unknown"),
            current_tab=str(payload.get("current_tab") or "copilot"),
            context_fingerprint=str(payload.get("context_fingerprint") or ""),
            selectors=dict(payload.get("selectors") or {}),
            content_digest=str(payload.get("content_digest") or ""),
            source_versions=[
                dict(item)
                for item in list(payload.get("source_versions") or [])
                if isinstance(item, dict)
            ],
            budget=CopilotContextBudget(
                scope_budget_bytes=int(budget.get("scope_budget_bytes") or 0),
                total_budget_bytes=int(budget.get("total_budget_bytes") or 0),
                original_bytes=int(budget.get("original_bytes") or 0),
                final_bytes=int(budget.get("final_bytes") or 0),
                within_scope_budget=bool(budget.get("within_scope_budget")),
                within_total_budget=bool(budget.get("within_total_budget")),
            ),
            freshness=CopilotContextFreshness(
                status=str(freshness.get("status") or "unknown"),
                valid=bool(freshness.get("valid")),
                latest_retrieved_at=parse_datetime(freshness.get("latest_retrieved_at")),
                source_retrievals={
                    str(key): str(value) if value is not None else None
                    for key, value in dict(freshness.get("source_retrievals") or {}).items()
                },
                stale_reasons=[str(item) for item in list(freshness.get("stale_reasons") or [])],
                supplied_fingerprint=(
                    str(freshness["supplied_fingerprint"])
                    if freshness.get("supplied_fingerprint") is not None
                    else None
                ),
                invalidated_fingerprint=(
                    str(freshness["invalidated_fingerprint"])
                    if freshness.get("invalidated_fingerprint") is not None
                    else None
                ),
            ),
            compaction=CopilotContextCompaction(
                applied=bool(compaction.get("applied")),
                strategy=str(compaction.get("strategy") or "none"),
                omitted_sections=[
                    dict(item)
                    for item in list(compaction.get("omitted_sections") or [])
                    if isinstance(item, dict)
                ],
                preserved_fields=[
                    str(item) for item in list(compaction.get("preserved_fields") or [])
                ],
                omitted_domains=[
                    {str(key): str(value) for key, value in item.items()}
                    for item in list(compaction.get("omitted_domains") or [])
                    if isinstance(item, dict)
                ],
            ),
            contract_version=str(
                payload.get("contract_version") or COPILOT_CONTEXT_CONTRACT_VERSION
            ),
            generated_at=parse_datetime(payload.get("generated_at")) or now_utc(),
            origin=str(payload.get("origin") or "gamma.copilot.context_contract.v2"),
        )


@dataclass(frozen=True)
class CopilotContextContract:
    tab_id: str
    active_mode: str
    selected_entity: HandoffEntity | None = None
    selected_timeframe: HandoffTimeframe | None = None
    headline_metrics: list[CopilotHeadlineMetric] = field(default_factory=list)
    provenance_summaries: list[ProvenanceSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    available_drilldown_tools: list[CopilotDrilldownTool] = field(default_factory=list)
    read_only_safety: CopilotReadOnlySafety = field(default_factory=CopilotReadOnlySafety)
    generated_at: datetime = field(default_factory=now_utc)
    source_provider: str = "gamma"
    origin: str = "gamma.copilot.context_contract"

    def __post_init__(self) -> None:
        if not str(self.tab_id or "").strip():
            raise ValueError("tab_id is required.")
        if not str(self.active_mode or "").strip():
            raise ValueError("active_mode is required.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "active_mode": self.active_mode,
            "selected_entity": self.selected_entity.to_dict() if self.selected_entity else None,
            "selected_timeframe": self.selected_timeframe.to_dict() if self.selected_timeframe else None,
            "headline_metrics": [metric.to_dict() for metric in self.headline_metrics],
            "provenance_summaries": [summary.to_dict() for summary in self.provenance_summaries],
            "warnings": list(self.warnings),
            "available_drilldown_tools": [tool.to_dict() for tool in self.available_drilldown_tools],
            "read_only_safety": self.read_only_safety.to_dict(),
            "generated_at": self.generated_at.isoformat(),
            "source_provider": self.source_provider,
            "origin": self.origin,
        }


DEFAULT_COPILOT_READ_ONLY_NOTES: tuple[str, ...] = (
    "Copilot context is grounded in loaded Gamma state and read-only internal tools.",
    "Copilot context must not expose order placement, account modification, wallet signing, or transaction submission.",
)


def default_copilot_read_only_safety() -> dict[str, Any]:
    return CopilotReadOnlySafety().to_dict()
