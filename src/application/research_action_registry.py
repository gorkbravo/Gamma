from __future__ import annotations

from collections.abc import Iterable

from src.models.copilot import CopilotResearchActionDefinition


class ResearchActionRegistry:
    """Read-only index over Copilot operator action contracts."""

    def __init__(self, definitions: Iterable[CopilotResearchActionDefinition]) -> None:
        self._definitions = {definition.tool_id: definition for definition in definitions}

    def list_definitions(self) -> list[CopilotResearchActionDefinition]:
        return sorted(self._definitions.values(), key=lambda item: item.tool_id)

    def get(self, tool_id: str) -> CopilotResearchActionDefinition | None:
        return self._definitions.get(tool_id)

    def list_for_domain(self, domain: str) -> list[CopilotResearchActionDefinition]:
        return [
            definition
            for definition in self.list_definitions()
            if domain in definition.domains
        ]

    def requires_confirmation(self, tool_id: str) -> bool:
        definition = self.get(tool_id)
        return bool(definition and definition.requires_confirmation)

