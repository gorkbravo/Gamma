from __future__ import annotations

import inspect

import pytest

from src.application.copilot_agents_operator import CopilotAgentsOperatorConfig


def test_agents_sdk_operator_env_defaults_are_feature_flagged_gpt55(monkeypatch):
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", raising=False)
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", raising=False)
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_AGENTS_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("GAMMA_COPILOT_MODEL", "gpt-5.5")
    monkeypatch.setenv("GAMMA_COPILOT_REASONING_EFFORT", "medium")

    config = CopilotAgentsOperatorConfig.from_env()

    assert config.enabled is False
    assert config.model == "gpt-5.5"
    assert config.reasoning_effort == "low"


def test_openai_agents_sdk_contract_smoke_without_live_api(monkeypatch):
    agents = pytest.importorskip("agents")

    def execute_registered_action(tool_id: str, arguments_json: str = "{}") -> str:
        del tool_id
        del arguments_json
        return "{}"

    wrapped = agents.function_tool(execute_registered_action)
    schema = getattr(wrapped, "params_json_schema", {})
    runner_run_params = inspect.signature(agents.Runner.run).parameters
    model_settings_params = inspect.signature(agents.ModelSettings).parameters

    assert getattr(wrapped, "name", None) == "execute_registered_action"
    assert schema["properties"]["tool_id"]["type"] == "string"
    assert schema["properties"]["arguments_json"]["type"] == "string"
    assert "max_turns" in runner_run_params
    assert "parallel_tool_calls" in model_settings_params

    settings = agents.ModelSettings(parallel_tool_calls=False)
    agent = agents.Agent(
        name="Gamma Research Operator",
        model="gpt-test",
        instructions="Use only the Gamma action registry tool.",
        tools=[wrapped],
        model_settings=settings,
    )

    assert agent.tools == [wrapped]
    assert agent.model_settings.parallel_tool_calls is False

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", "gpt-test")
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_AGENTS_MAX_TURNS", "3")
    config = CopilotAgentsOperatorConfig.from_env()

    assert config.enabled is True
    assert config.model == "gpt-test"
    assert config.max_turns == 3
