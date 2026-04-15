from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.models.handoff import HandoffEntity, HandoffTimeframe
from src.models.provenance import ProvenanceSummary
from src.utils.time import now_utc


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

