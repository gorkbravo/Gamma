from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from src.models.copilot import (
    CopilotContextBundle,
    CopilotOperatorPlan,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotToolExecution,
)


ToolExecutor = Callable[[str, dict[str, object], CopilotContextBundle], CopilotToolExecution]
OperatorToolExecutor = Callable[[str, dict[str, object]], CopilotToolExecution]

# Streaming providers call this with (event_type, data) for each semantic
# provider event: text deltas, tool activity, warnings, refusals, usage.
RunEventEmitter = Callable[[str, dict[str, object]], None]

# Returns True when the active run should stop (user cancel or run timeout).
CancelCheck = Callable[[], bool]


class CopilotRunCancelled(Exception):
    """Raised inside a streaming provider when the run is cancelled or times out."""

    def __init__(self, reason: str = "cancelled") -> None:
        super().__init__(reason)
        self.reason = reason


class CopilotProvider(Protocol):
    provider_name: str

    def generate_research_card(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        tool_specs: list[dict[str, object]],
        execute_tool: ToolExecutor,
    ) -> CopilotResearchCardResult:
        ...


class CopilotOperatorLoopProvider(Protocol):
    provider_name: str

    def stream_research_operator(
        self,
        *,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        tool_specs: list[dict[str, object]],
        execute_tool: OperatorToolExecutor,
        emit: RunEventEmitter,
        should_cancel: CancelCheck,
    ) -> CopilotResearchCardResult:
        ...


@dataclass
class UnavailableCopilotProvider:
    message: str
    provider_name: str = "unconfigured"
    provider_id: str = "unavailable_copilot"

    def generate_research_card(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        tool_specs: list[dict[str, object]],
        execute_tool: ToolExecutor,
    ) -> CopilotResearchCardResult:
        del tool_specs
        del execute_tool
        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="unavailable",
            provider=self.provider_name,
            message=self.message,
            sources=list(context.sources),
            warnings=list(context.warnings),
        )
