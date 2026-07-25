from __future__ import annotations

from collections.abc import Iterable

from src.models.copilot import CopilotResearchActionDefinition


class ResearchActionRegistryError(ValueError):
    pass


class ResearchActionPermissionError(ResearchActionRegistryError):
    pass


class ResearchActionRegistry:
    """Authoritative index and permission policy for Copilot research actions."""

    AUTOMATIC_ACTION_TYPES = {"read_context", "run_analysis", "fetch_external_context"}
    PROHIBITED_ACTION_TERMS = {
        "account",
        "arbitrary_code",
        "execute_code",
        "order",
        "rebalance",
        "trade",
        "wallet",
    }

    def __init__(self, definitions: Iterable[CopilotResearchActionDefinition]) -> None:
        rows = list(definitions)
        duplicate_ids = sorted(
            tool_id
            for tool_id in {definition.tool_id for definition in rows}
            if sum(definition.tool_id == tool_id for definition in rows) > 1
        )
        if duplicate_ids:
            raise ResearchActionRegistryError(
                f"Duplicate Research Action Registry ids: {', '.join(duplicate_ids)}"
            )
        for definition in rows:
            self._validate_definition(definition)
        self._definitions = {definition.tool_id: definition for definition in rows}

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

    def authorize_automatic(self, tool_id: str) -> CopilotResearchActionDefinition:
        definition = self.require(tool_id)
        if (
            definition.action_type not in self.AUTOMATIC_ACTION_TYPES
            or not definition.read_only
            or definition.mutates_local_state
            or definition.requires_confirmation
            or definition.permission_policy not in {"automatic", "automatic_read_only"}
        ):
            raise ResearchActionPermissionError(
                f"Action is not automatic read-only work: {tool_id}"
            )
        return definition

    def authorize_draft(self, tool_id: str) -> CopilotResearchActionDefinition:
        definition = self.require(tool_id)
        if (
            definition.action_type != "draft_change"
            or definition.mutates_local_state
            or definition.requires_confirmation
            or definition.permission_policy != "automatic_draft"
        ):
            raise ResearchActionPermissionError(
                f"Action is not an automatic draft action: {tool_id}"
            )
        return definition

    def authorize_confirmed_mutation(self, tool_id: str) -> CopilotResearchActionDefinition:
        definition = self.require(tool_id)
        if (
            definition.action_type != "apply_change"
            or definition.read_only
            or not definition.mutates_local_state
            or not definition.requires_confirmation
            or definition.permission_policy != "confirmation_required"
        ):
            raise ResearchActionPermissionError(
                f"Action is not a confirmation-gated local mutation: {tool_id}"
            )
        return definition

    def require(self, tool_id: str) -> CopilotResearchActionDefinition:
        definition = self.get(tool_id)
        if definition is None:
            raise ResearchActionPermissionError(
                f"Unsupported Research Action Registry tool: {tool_id}"
            )
        return definition

    @classmethod
    def _validate_definition(cls, definition: CopilotResearchActionDefinition) -> None:
        normalized_id = str(definition.tool_id or "").strip().lower()
        if not normalized_id:
            raise ResearchActionRegistryError("Research action tool_id is required.")
        tokens = set(normalized_id.replace("-", "_").replace(".", "_").split("_"))
        prohibited = sorted(tokens.intersection(cls.PROHIBITED_ACTION_TERMS))
        if prohibited:
            raise ResearchActionRegistryError(
                f"Execution-capable action family is prohibited in Gamma: {definition.tool_id}"
            )
        if definition.mutates_local_state and (
            not definition.requires_confirmation
            or definition.permission_policy != "confirmation_required"
        ):
            raise ResearchActionRegistryError(
                f"Local mutation must require confirmation: {definition.tool_id}"
            )
        if definition.read_only and definition.mutates_local_state:
            raise ResearchActionRegistryError(
                f"Action cannot be read-only and mutating: {definition.tool_id}"
            )
