from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotToolExecution,
)


ToolExecutor = Callable[[str, dict[str, object], CopilotContextBundle], CopilotToolExecution]


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


@dataclass
class UnavailableCopilotProvider:
    message: str
    provider_name: str = "unconfigured"

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
