"""Términos prohibidos compuestos en el registro de acciones del Copilot (2026-11-27).

`arbitrary_code` y `execute_code` no coincidían nunca porque el id se troceaba por «_» y se
comparaba palabra a palabra.
"""

from __future__ import annotations

import pytest

from src.application.research_action_registry import ResearchActionRegistry, ResearchActionRegistryError
from src.models.copilot import CopilotResearchActionDefinition


def _definition(tool_id: str) -> CopilotResearchActionDefinition:
    return CopilotResearchActionDefinition(
        tool_id=tool_id,
        domains=["strategy_lab"],
        action_type="read_context",
        description="Test action.",
        input_schema={},
        read_only=True,
        mutates_local_state=False,
        requires_confirmation=False,
        permission_policy="automatic",
    )


@pytest.mark.parametrize(
    "tool_id",
    ["strategy_lab.execute_code", "sandbox.arbitrary_code_runner", "run-execute-code", "portfolio.execute_trade", "wallet.read"],
)
def test_registry_rejects_single_and_compound_prohibited_terms(tool_id):
    with pytest.raises(ResearchActionRegistryError, match="prohibited"):
        ResearchActionRegistry([_definition(tool_id)])


@pytest.mark.parametrize("tool_id", ["strategy_lab.get_code_listing", "macro.get_recorder", "research.inspect_execution_costs"])
def test_registry_accepts_ids_that_only_share_a_fragment(tool_id):
    registry = ResearchActionRegistry([_definition(tool_id)])
    assert registry.require(tool_id).tool_id == tool_id
