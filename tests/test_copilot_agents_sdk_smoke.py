from __future__ import annotations

import inspect

import pytest

from src.application.copilot_agents_operator import CopilotAgentsOperatorConfig


def test_agents_sdk_operator_env_defaults_are_feature_flagged_luna(monkeypatch):
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", raising=False)
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", raising=False)
    monkeypatch.delenv("GAMMA_COPILOT_OPERATOR_AGENTS_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("GAMMA_COPILOT_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("GAMMA_COPILOT_REASONING_EFFORT", "medium")

    config = CopilotAgentsOperatorConfig.from_env()

    assert config.enabled is False
    assert config.model == "gpt-5.6-luna"
    assert config.reasoning_effort == "low"


def test_openai_agents_sdk_contract_smoke_without_live_api(monkeypatch):
    agents = pytest.importorskip("agents")

    async def execute_risk_scenario(_context, arguments_json: str) -> str:
        del _context
        del arguments_json
        return "{}"

    schema = {
        "type": "object",
        "properties": {
            "rate_shift_bps": {"type": "number"},
            "duration_proxy_years": {"type": "number"},
        },
        "required": ["rate_shift_bps", "duration_proxy_years"],
        "additionalProperties": False,
    }
    wrapped = agents.FunctionTool(
        name="run_risk_scenario_analysis",
        description="Run one bounded read-only risk scenario.",
        params_json_schema=schema,
        on_invoke_tool=execute_risk_scenario,
        strict_json_schema=True,
        timeout_seconds=45.0,
    )
    runner_run_params = inspect.signature(agents.Runner.run).parameters
    runner_streamed_params = inspect.signature(agents.Runner.run_streamed).parameters
    model_settings_params = inspect.signature(agents.ModelSettings).parameters

    assert getattr(wrapped, "name", None) == "run_risk_scenario_analysis"
    assert wrapped.params_json_schema == schema
    assert wrapped.strict_json_schema is True
    assert "max_turns" in runner_run_params
    assert "max_turns" in runner_streamed_params
    assert "parallel_tool_calls" in model_settings_params

    settings = agents.ModelSettings(parallel_tool_calls=False)
    agent = agents.Agent(
        name="Gamma Research Operator",
        model="gpt-test",
        instructions="Use only the strict Gamma action tools.",
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
