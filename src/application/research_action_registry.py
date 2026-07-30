from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from src.models.copilot import CopilotResearchActionDefinition


class ResearchActionRegistryError(ValueError):
    pass


class ResearchActionPermissionError(ResearchActionRegistryError):
    pass


class ResearchActionArgumentError(ResearchActionRegistryError):
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

    def validate_arguments(
        self,
        tool_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate model-produced arguments at Gamma's execution boundary.

        Provider-side strict schemas improve tool-call quality, but the server
        registry remains authoritative. This validator intentionally covers the
        bounded JSON-schema subset used by Gamma's registered research tools.
        It never fills hidden defaults or coerces unrelated values.
        """

        definition = self.require(tool_id)
        if not isinstance(arguments, dict):
            raise ResearchActionArgumentError(
                f"Invalid arguments for `{tool_id}` at `$`: expected object."
            )
        self._validate_schema_value(
            definition.input_schema,
            arguments,
            path="$",
            tool_id=tool_id,
        )
        return dict(arguments)

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

    @classmethod
    def _validate_schema_value(
        cls,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
        tool_id: str,
    ) -> None:
        if not isinstance(schema, dict):
            return

        for keyword in ("oneOf", "anyOf"):
            variants = schema.get(keyword)
            if isinstance(variants, list) and variants:
                failures: list[str] = []
                for variant in variants:
                    try:
                        cls._validate_schema_value(
                            variant,
                            value,
                            path=path,
                            tool_id=tool_id,
                        )
                        return
                    except ResearchActionArgumentError as exc:
                        failures.append(str(exc))
                raise ResearchActionArgumentError(
                    f"Invalid arguments for `{tool_id}` at `{path}`: value did not "
                    f"match any allowed {keyword} schema."
                )

        raw_types = schema.get("type")
        allowed_types = (
            list(raw_types)
            if isinstance(raw_types, list)
            else [raw_types]
            if isinstance(raw_types, str)
            else []
        )
        if allowed_types and not any(
            cls._matches_json_type(value, expected)
            for expected in allowed_types
        ):
            expected = " or ".join(str(item) for item in allowed_types)
            raise ResearchActionArgumentError(
                f"Invalid arguments for `{tool_id}` at `{path}`: expected {expected}, "
                f"received {cls._json_type_name(value)}."
            )

        if "enum" in schema and value not in list(schema.get("enum") or []):
            raise ResearchActionArgumentError(
                f"Invalid arguments for `{tool_id}` at `{path}`: value is not in "
                f"the allowed enum."
            )

        if value is None:
            return

        if isinstance(value, dict):
            properties = schema.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            required = {
                str(item)
                for item in list(schema.get("required") or [])
            }
            missing = sorted(required.difference(value))
            if missing:
                raise ResearchActionArgumentError(
                    f"Invalid arguments for `{tool_id}` at `{path}`: missing required "
                    f"field(s): {', '.join(missing)}."
                )
            if schema.get("additionalProperties") is False:
                extras = sorted(str(key) for key in value if key not in properties)
                if extras:
                    raise ResearchActionArgumentError(
                        f"Invalid arguments for `{tool_id}` at `{path}`: unexpected "
                        f"field(s): {', '.join(extras)}."
                    )
            for key, nested in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    cls._validate_schema_value(
                        child_schema,
                        nested,
                        path=f"{path}.{key}",
                        tool_id=tool_id,
                    )
            return

        if isinstance(value, list):
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    cls._validate_schema_value(
                        item_schema,
                        item,
                        path=f"{path}[{index}]",
                        tool_id=tool_id,
                    )
            return

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                raise ResearchActionArgumentError(
                    f"Invalid arguments for `{tool_id}` at `{path}`: value is below "
                    f"the minimum {minimum}."
                )
            if maximum is not None and value > maximum:
                raise ResearchActionArgumentError(
                    f"Invalid arguments for `{tool_id}` at `{path}`: value is above "
                    f"the maximum {maximum}."
                )

        if isinstance(value, str) and schema.get("pattern"):
            pattern = str(schema["pattern"])
            if re.search(pattern, value) is None:
                raise ResearchActionArgumentError(
                    f"Invalid arguments for `{tool_id}` at `{path}`: value does not "
                    "match the required pattern."
                )

    @staticmethod
    def _matches_json_type(value: Any, expected: str) -> bool:
        return {
            "null": value is None,
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        }.get(str(expected), True)

    @staticmethod
    def _json_type_name(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        if isinstance(value, str):
            return "string"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        return type(value).__name__
