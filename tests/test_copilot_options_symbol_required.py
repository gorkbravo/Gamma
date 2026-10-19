"""Las herramientas de Opciones del Operator no sustituyen un subyacente por defecto.

Antes de 2026-10-19, sin símbolo pedido ni contexto de Opciones adjunto, Gamma usaba SPY en
silencio: `symbol=null` producía un borrador, una comparación o una estructura de SPY que nadie había
pedido. Ahora fallan cerrado con un mensaje tipado; con símbolo explícito o activo nada cambia.
"""
from __future__ import annotations

import json

import pytest

from test_copilot import _build_test_client, _checkpoint7_final_card
from src.application.copilot_service import OPTIONS_SYMBOL_REQUIRED_MESSAGE, CopilotService
from src.models.copilot import CopilotRequestContext, CopilotResearchCardRequest
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider

LEGS = [{"side": "long", "option_type": "call", "expiry": "2026-11-20", "strike": 500.0, "quantity": 1}]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    client, runtime = _build_test_client(tmp_path)
    requested: list[str] = []
    original = runtime.copilot_service.iv_service.get_surface

    def recording_surface(request):
        requested.append(request.symbol)
        return original(request)

    runtime.copilot_service.iv_service.get_surface = recording_surface
    yield client, runtime, requested
    runtime.shutdown()


def _iv_context(runtime, prompt="Inspect the options", iv_state=None):
    request = CopilotResearchCardRequest(
        domain="iv", prompt=prompt,
        context=CopilotRequestContext(current_tab="iv", workspace_mode="strategies", iv_state=iv_state),
    )
    return runtime.copilot_service._build_plan_execution_context(request, "iv")


def test_resolver_returns_no_symbol_instead_of_spy():
    assert CopilotService._iv_target_symbol_from_state({}, None, None) is None
    assert CopilotService._iv_target_symbol_from_state({}, None, {"active_symbol": "msft"}) == "MSFT"


def test_iv_context_without_symbol_says_so(app):
    _, runtime, requested = app
    context = _iv_context(runtime)
    assert context.summary_data["target_symbol"] is None
    assert context.summary_data["iv"]["symbol"] is None
    assert OPTIONS_SYMBOL_REQUIRED_MESSAGE in context.warnings
    assert requested == []


@pytest.mark.parametrize("tool_id,arguments", [
    ("draft_options_strategy", {"symbol": None, "name": None, "contracts": 1, "depth_preset": "compact",
                                "market_data_mode": None, "legs": LEGS}),
    ("run_options_realized_implied_comparison", {"symbol": None, "max_expiries": 4, "depth_preset": "compact",
                                                 "market_data_mode": None}),
])
def test_analysis_tools_fail_closed_without_any_underlying(app, tool_id, arguments):
    _, runtime, requested = app
    execution = runtime.copilot_service._execute_tool(tool_id, arguments, _iv_context(runtime))
    assert execution.output["error"] == OPTIONS_SYMBOL_REQUIRED_MESSAGE
    assert execution.output["retryable"] is False
    assert requested == []  # ninguna superficie se pidió, tampoco de SPY


def test_structure_inspection_is_typed_unavailable_without_any_underlying(app):
    _, runtime, requested = app
    execution = runtime.copilot_service._execute_tool(
        "inspect_options_structure", {"symbol": None, "expiry": None, "max_expiries": 4}, _iv_context(runtime))
    assert execution.output["status"] == "unavailable"
    assert execution.output["symbol"] is None
    assert any(OPTIONS_SYMBOL_REQUIRED_MESSAGE in warning for warning in execution.output["warnings"])
    assert requested == []


def test_active_or_explicit_symbols_are_unchanged(app):
    _, runtime, _ = app
    service = runtime.copilot_service
    active = _iv_context(runtime, iv_state={"session": {"active_symbol": "aapl"}})
    assert service._normalize_options_strategy_arguments({"symbol": None, "legs": LEGS}, active)["symbol"] == "AAPL"
    assert service._normalize_options_realized_implied_arguments({"symbol": None}, active)["symbol"] == "AAPL"
    explicit = service._normalize_options_strategy_arguments({"symbol": "nvda", "legs": LEGS}, _iv_context(runtime))
    assert explicit["symbol"] == "NVDA" and explicit["name"] == "NVDA option set"
    # Un ticker explícito del prompt llega como target_symbol desde las entidades del plan.
    named = _iv_context(runtime, prompt="Draft an AAPL call spread: long 2026-11-20 500 call")
    assert named.summary_data["target_symbol"] == "AAPL"


def test_deterministic_fallback_stops_instead_of_guessing_an_underlying(app):
    _, runtime, _ = app
    prompt = "Draft a call spread: long 2026-11-20 500 call and short 2026-11-20 510 call"
    assert CopilotService._default_options_strategy_arguments(_iv_context(runtime, prompt=prompt)) is None
    named = CopilotService._default_options_strategy_arguments(_iv_context(runtime, prompt=f"For AAPL. {prompt}"))
    assert named["symbol"] == "AAPL" and len(named["legs"]) == 2


def test_operator_loop_reports_missing_underlying_without_retaining_a_spy_draft(app):
    client, runtime, requested = app

    class NullSymbolModel(OpenAIResponsesCopilotProvider):
        def __init__(self):
            super().__init__(api_key="test-key", model="gpt-test-operator", reasoning_effort="low", store_responses=False)
            self.observations: list[dict] = []

        def _post_json_stream(self, payload, emit, should_cancel):
            outputs = [json.loads(item["output"]) for item in payload["input"] if item.get("type") == "function_call_output"]
            if not outputs:
                arguments = {"symbol": None, "name": None, "contracts": 1, "depth_preset": "compact",
                             "market_data_mode": None, "legs": LEGS}
                return ({"id": "resp-call", "model": self.model, "output": [{
                    "type": "function_call", "id": "fc-1", "call_id": "call-1",
                    "name": "draft_options_strategy", "arguments": json.dumps(arguments),
                }]}, "completed")
            self.observations = outputs
            card = _checkpoint7_final_card(rationale="Gamma needs the underlying before drafting this option set.")
            return ({"id": "resp-final", "model": self.model, "output": [{"type": "message", "content": [{
                "type": "output_text", "text": json.dumps(card)}]}]}, "completed")

    model = NullSymbolModel()
    runtime.copilot_service.provider = model
    client.post("/copilot/sessions", json={"session_id": "options-no-symbol"})
    result = runtime.copilot_service.execute_research_operator_plan(CopilotResearchCardRequest(
        domain="copilot", role="research_operator", user_session_id="options-no-symbol",
        prompt="Draft a call spread: long 2026-11-20 500 call and short 2026-11-20 510 call",
        context=CopilotRequestContext(current_tab="copilot", workspace_mode="research"),
    ))
    assert model.observations[0]["status"] == "failed"
    assert model.observations[0]["output"]["error"] == OPTIONS_SYMBOL_REQUIRED_MESSAGE
    assert result.status == "incomplete"
    assert requested == []
    assert client.get("/copilot/sessions/options-no-symbol").json()["working_analyses"] == []
