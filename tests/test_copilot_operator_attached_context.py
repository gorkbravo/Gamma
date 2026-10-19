"""Identidades adjuntas visibles en el mensaje del Operator.

Regresión de la clase de fallo en vivo del 2026-10-16: el mensaje del bucle Operator solo llevaba
tarea, plan y contratos, así que el modelo no podía rellenar argumentos que solo existen en el
estado adjunto de la UI. Los proveedores falsos de otras pruebas inyectan los ids directamente y no
lo detectan; aquí un modelo falso decide cada llamada leyendo únicamente el mensaje construido.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import re

import pandas as pd
import pytest

from offline_fixtures import install_offline_market_fixtures
from test_copilot import _build_test_client, _checkpoint7_final_card, _crypto_token_fixture
from src.application.iv_service import IVSurfaceRequest
from src.application.copilot_agents_operator import CopilotAgentsOperatorService
from src.models.copilot import (
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotSynthesisRequest,
    CopilotSynthesisScope,
    MacroCopilotContext,
)
from src.models.crypto import CryptoPricePoint
from src.models.provenance import FreshnessLabel
from src.services.research_market_data import ResearchHistoryResult
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
from src.utils.time import now_utc


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    client, runtime = _build_test_client(tmp_path)
    # Suite hermética: los venues de predicción vienen de fixtures offline, no de la red.
    install_offline_market_fixtures(runtime)

    class CryptoFixture:
        def get_token_detail(self, token_id):
            return replace(_crypto_token_fixture(), token_id=token_id, source_provider="fixture", retrieved_at=now_utc())

        def get_price_history(self, token_id, *, days):
            return [CryptoPricePoint(timestamp=now_utc() - timedelta(days=offset), price=price, market_cap=1000.0,
                total_volume=100.0, source_provider="fixture", retrieved_at=now_utc(), origin="tests.crypto.history")
                for offset, price in [(days - 1, 100.0), (0, 110.0)]]

        def get_dex_liquidity(self, token_id):
            return None

        def get_comparison(self, token_id):
            return None

    runtime.copilot_service.crypto_service = CryptoFixture()
    yield client, runtime
    runtime.shutdown()


def _operator_request(prompt, *, context=None, synthesis=None, session_id=None):
    return CopilotResearchCardRequest(
        domain="synthesis" if synthesis is not None else "copilot",
        prompt=prompt,
        role="research_operator",
        user_session_id=session_id,
        context=context or CopilotRequestContext(current_tab="copilot", workspace_mode="research"),
        synthesis=synthesis,
    )


def _message(runtime, request):
    """Plan real y mensaje de usuario real que recibiría el modelo."""
    plan = runtime.copilot_service.plan_research_operator(request)
    provider = OpenAIResponsesCopilotProvider(api_key="test-key", model="gpt-test", reasoning_effort="low")
    body = json.loads(provider._build_operator_user_message(request, plan)["content"][0]["text"])
    return plan, body


def _outside_attached(body):
    return json.dumps({key: value for key, value in body.items() if key != "attached_context"})


class _MessageOnlyModel(OpenAIResponsesCopilotProvider):
    """Modelo simulado: elige la llamada solo con el mensaje de usuario, sin acceso a fixtures."""

    def __init__(self, decide):
        super().__init__(api_key="test-key", model="gpt-test-operator", reasoning_effort="low", store_responses=False)
        self.decide = decide
        self.messages: list[dict] = []
        self.observations: list[dict] = []

    def propose_equity_entity(self, *, request):
        # Sin red: equivale al fallo controlado del proveedor, que el servicio convierte en aviso.
        raise RuntimeError("Entity resolution is offline in tests.")

    def _post_json_stream(self, payload, emit, should_cancel):
        outputs = [json.loads(item["output"]) for item in payload["input"] if item.get("type") == "function_call_output"]
        if not outputs:
            message = json.loads(payload["input"][0]["content"][0]["text"])
            self.messages.append(message)
            tool_id, arguments = self.decide(message)
            wire = tool_id.replace(".", "__")
            assert wire in {tool["name"] for tool in payload["tools"]}
            return ({"id": "resp-call", "model": self.model, "output": [{
                "type": "function_call", "id": "fc-1", "call_id": "call-1",
                "name": wire, "arguments": json.dumps(arguments),
            }]}, "completed")
        self.observations = outputs
        observation = outputs[-1]
        rationale = f"Gamma returned `{observation['tool_id']}` with status {observation['status']} for the attached inputs."
        return ({"id": "resp-final", "model": self.model, "output": [{"type": "message", "content": [{
            "type": "output_text", "text": json.dumps(_checkpoint7_final_card(rationale=rationale)),
        }]}]}, "completed")


def _run_message_only(client, runtime, request, decide):
    model = _MessageOnlyModel(decide)
    runtime.copilot_service.provider = model
    if request.user_session_id:
        client.post("/copilot/sessions", json={"session_id": request.user_session_id})
    result = runtime.copilot_service.execute_research_operator_plan(request)
    assert result.status == "ready", (result.message, result.warnings)
    assert len(model.observations) == 1
    observation = model.observations[0]
    assert observation["status"] == "completed", observation
    return result, observation


def _days(task):
    return int(re.search(r"(\d+)\s*days?", task)[1])


# --- Cripto: token seleccionado dentro de un ámbito de síntesis ----------------------------------

def _crypto_synthesis_request(session_id=None):
    return _operator_request(
        "Analyze the selected crypto token over 90 days",
        context=CopilotRequestContext(current_tab="synthesis", workspace_mode="research"),
        synthesis=CopilotSynthesisRequest(active_tab="crypto", included_scopes=[
            CopilotSynthesisScope(domain="crypto", context=CopilotRequestContext(current_tab="crypto", crypto_token_id="bitcoin")),
            CopilotSynthesisScope(domain="macro", context=CopilotRequestContext(current_tab="macro", macro=MacroCopilotContext())),
        ]),
        session_id=session_id,
    )


def _decide_crypto(message):
    attached = message["attached_context"]["crypto"]
    return "run_crypto_token_analysis", {"token_id": attached["selected_token_id"], "days": _days(message["task"])}


def test_selected_crypto_token_in_synthesis_scope_reaches_the_message(app):
    _, runtime = app
    plan, body = _message(runtime, _crypto_synthesis_request())
    assert [step.tool_id for step in plan.steps] == ["run_crypto_token_analysis"]
    assert body["attached_context"]["crypto"]["selected_token_id"] == "bitcoin"
    assert "bitcoin" not in _outside_attached(body)  # solo el bloque adjunto lo aporta


def test_model_completes_crypto_call_from_message_alone(app):
    client, runtime = app
    result, observation = _run_message_only(client, runtime, _crypto_synthesis_request("attached-crypto"), _decide_crypto)
    assert observation["arguments"] == {"token_id": "bitcoin", "days": 90}
    assert observation["output"]["token_id"] == "bitcoin"


# --- Mercados de predicción: contrato seleccionado en una comparación --------------------------

def _prediction_request(client, session_id=None):
    markets = client.post("/prediction-markets/screener", json={}).json()["markets"]
    selected, other = markets[0]["market_id"], markets[1]["market_id"]
    request = _operator_request(
        f"Compare the selected prediction market with {other} over 1w using 60 minute bars",
        context=CopilotRequestContext(current_tab="prediction_markets", workspace_mode="research", prediction_market_id=selected),
        session_id=session_id,
    )
    return request, selected, other


def _decide_prediction(message):
    selected = message["attached_context"]["prediction_markets"]["selected_market_id"]
    named = [entity["id"] for entity in message["operator_plan"]["target_entities"] if entity["kind"] == "prediction_market"]
    window = re.search(r"over (\w+)", message["task"])[1]
    minutes = int(re.search(r"(\d+) minute", message["task"])[1])
    return "run_prediction_market_comparison", {"market_ids": [selected, *named], "range": window, "resolution_minutes": minutes}


def test_selected_prediction_market_reaches_the_comparison_message(app):
    client, runtime = app
    request, selected, other = _prediction_request(client)
    plan, body = _message(runtime, request)
    assert plan.intent == "prediction_market_comparison"
    assert [entity.id for entity in plan.target_entities] == [other]  # el plan no añade el seleccionado
    assert body["attached_context"]["prediction_markets"]["selected_market_id"] == selected
    assert selected not in _outside_attached(body)


def test_model_completes_prediction_comparison_from_message_alone(app):
    client, runtime = app
    request, selected, other = _prediction_request(client, "attached-prediction")
    _, observation = _run_message_only(client, runtime, request, _decide_prediction)
    assert observation["arguments"]["market_ids"] == [selected, other]
    assert observation["output"]["inputs"]["market_ids"] == [selected, other]


# --- Opciones: workbench visible ------------------------------------------------------------------

def _options_request(runtime, session_id=None, *, surface_symbol=None):
    iv_service = runtime.copilot_service.iv_service
    fixed = iv_service.get_surface(IVSurfaceRequest(symbol="AAPL", market_data_mode="auto", depth_preset="compact"))
    iv_service.get_surface = lambda request: fixed  # congela la malla de strikes del mock
    snapshot = fixed.snapshot
    expiry = snapshot.expiries[0]
    pairs = [pair for pair in snapshot.pairs if pair.expiry == expiry]
    long_pair, short_pair = pairs[len(pairs) // 2], pairs[-1]
    workbench = {
        "mode": "strategies", "symbol": "AAPL", "strategy_symbol": "AAPL", "selected_expiry": expiry,
        "selected_expiry_days": 30, "contracts": 2, "contract_multiplier": 100,
        "legs": [
            {"side": "long", "option_type": "call", "expiry": expiry, "days_to_expiry": 30,
             "strike": float(long_pair.strike), "premium": 4.25, "quantity": 1},
            {"side": "short", "option_type": "call", "expiry": expiry, "days_to_expiry": 30,
             "strike": float(short_pair.strike), "premium": 1.1, "quantity": 1},
        ],
        "strategy": {"net_premium_per_share": 3.15, "max_profit_total": 999.0, "breakevens": [123.0]},
    }
    state = {"session": {"active_symbol": "AAPL"}, "workbench": workbench}
    if surface_symbol:
        state["surface"] = {"symbol": surface_symbol, "snapshot_available": True}
    request = _operator_request(
        "Draft the call spread from my Options workbench as a temporary option strategy",
        context=CopilotRequestContext(current_tab="iv", workspace_mode="strategies", iv_state=state),
        session_id=session_id,
    )
    return request, expiry, long_pair, short_pair


def _decide_options(message):
    attached = message["attached_context"]["options"]
    legs = [{key: leg[key] for key in ("side", "option_type", "expiry", "strike", "quantity")} for leg in attached["workbench_legs"]]
    return "draft_options_strategy", {"symbol": attached["active_symbol"], "name": None, "contracts": attached["contracts"],
        "depth_preset": "compact", "market_data_mode": None, "legs": legs}


def test_options_workbench_structure_reaches_the_message_without_marks(app):
    _, runtime = app
    request, expiry, long_pair, short_pair = _options_request(runtime)
    plan, body = _message(runtime, request)
    assert [step.tool_id for step in plan.steps] == ["draft_options_strategy"]
    attached = body["attached_context"]["options"]
    assert attached["active_symbol"] == "AAPL" and attached["selected_expiry"] == expiry and attached["contracts"] == 2
    assert [leg["strike"] for leg in attached["workbench_legs"]] == [float(long_pair.strike), float(short_pair.strike)]
    assert all("premium" not in leg for leg in attached["workbench_legs"])  # marcas y payoff son salidas
    assert "strategy" not in attached and "breakevens" not in json.dumps(body)
    assert expiry not in _outside_attached(body)


def test_options_workbench_for_another_underlying_is_not_attached(app):
    _, runtime = app
    request, *_ = _options_request(runtime, surface_symbol="MSFT")
    _, body = _message(runtime, request)
    attached = body["attached_context"]["options"]
    assert attached["active_symbol"] == "MSFT"
    assert "workbench_legs" not in attached and "selected_expiry" not in attached


def test_model_completes_options_draft_from_message_alone(app):
    client, runtime = app
    request, expiry, long_pair, short_pair = _options_request(runtime, "attached-options")
    _, observation = _run_message_only(client, runtime, request, _decide_options)
    assert observation["arguments"]["symbol"] == "AAPL" and observation["arguments"]["contracts"] == 2
    assert [leg["strike"] for leg in observation["arguments"]["legs"]] == [float(long_pair.strike), float(short_pair.strike)]
    assert observation["output"]["unresolved_legs"] == []


# --- Strategy Lab: composición actual -------------------------------------------------------------

def _composition_request(runtime, session_id=None):
    def fixture_history(instrument, lookback_days):
        symbol = str(instrument.symbol).upper()
        dates = pd.date_range("2024-01-02", periods=520, freq="B")
        bias = {"QQQ": 0.0009, "IWM": 0.0004, "SPY": 0.0006}[symbol]
        returns = pd.Series([bias + (0.0007 if index % 5 == 0 else -0.0002) for index in range(520)], index=dates)
        return ResearchHistoryResult(series=100.0 * (1.0 + returns).cumprod(), source_provider="fixture",
            source_label="Fixture listed history", origin="tests.copilot.attached_composition",
            freshness_label=FreshnessLabel.HISTORICAL)

    runtime.research_provider.load_instrument_history_result = fixture_history
    points = [{"timestamp": "2026-01-02T00:00:00", "value": 0.01}] * 40
    composition = {"label": "Current QQQ/IWM", "metrics": {"annualized_return": 0.2}, "portfolio_inputs": {
        "name": "Current QQQ/IWM", "benchmark_symbol": "SPY", "lookback_days": 504, "min_observations": 100,
        "legs": [
            {"label": "Long QQQ", "asset_class": "etf", "identifier": "QQQ", "weight": 0.6, "value_kind": "return", "return_points": points},
            {"label": "Short IWM", "asset_class": "etf", "identifier": "IWM", "weight": -0.4, "value_kind": "return", "return_points": points},
        ],
        "lenses": [], "overlays": [], "benchmark_object": None,
    }}
    return _operator_request(
        "Backtest the current Strategy Lab portfolio composition as it stands",
        context=CopilotRequestContext(current_tab="strategy_lab", workspace_mode="research",
            strategy_lab_state={"composition": composition}),
        session_id=session_id,
    )


def _decide_composition(message):
    attached = message["attached_context"]["strategy_lab_composition"]
    legs = [{key: leg.get(key) for key in ("label", "asset_class", "identifier", "weight")} for leg in attached["legs"]]
    return "run_strategy_lab_portfolio_backtest", {"name": attached["name"], "benchmark_symbol": attached["benchmark_symbol"],
        "lookback_days": attached["lookback_days"], "min_observations": attached["min_observations"], "legs": legs}


def test_current_composition_inputs_reach_the_message_without_return_series(app):
    _, runtime = app
    plan, body = _message(runtime, _composition_request(runtime))
    assert plan.intent == "strategy_lab_portfolio_backtest"
    attached = body["attached_context"]["strategy_lab_composition"]
    assert [(leg["identifier"], leg["weight"]) for leg in attached["legs"]] == [("QQQ", 0.6), ("IWM", -0.4)]
    assert attached["lookback_days"] == 504 and attached["min_observations"] == 100
    assert "return_points" not in json.dumps(body) and "annualized_return" not in json.dumps(body)
    assert "IWM" not in _outside_attached(body)


def test_model_completes_composition_backtest_from_message_alone(app):
    client, runtime = app
    _, observation = _run_message_only(client, runtime, _composition_request(runtime, "attached-composition"), _decide_composition)
    assert [leg["weight"] for leg in observation["arguments"]["legs"]] == [0.6, -0.4]
    assert observation["arguments"]["lookback_days"] == 504


# --- Research: ámbito activo (vía HTTP, donde scope_type llega como Enum) --------------------------

def _research_payload(client, session_id):
    result = client.post("/research/analyze", json={
        "scope_type": "synthetic_portfolio", "benchmark_symbol": "SPY", "lookback_days": 252,
        "synthetic_positions": [{"symbol": "AAPL", "weight": 0.6}, {"symbol": "MSFT", "weight": 0.4}],
    })
    assert result.status_code == 200, result.text
    return {
        "domain": "copilot", "role": "research_operator", "user_session_id": session_id,
        "prompt": "Analyze the current Research scope basket weights against QQQ over 252 days",
        "context": {"current_tab": "research", "workspace_mode": "research", "research_state": {"result": result.json()}},
    }


def _decide_research(message):
    attached = message["attached_context"]["research_scope"]
    benchmark = re.search(r"against ([A-Z]+)", message["task"])[1]
    return "run_research_basket_analysis", {"positions": attached["positions"], "benchmark_symbol": benchmark,
        "lookback_days": _days(message["task"])}


def test_model_completes_research_basket_from_active_scope_message_alone(app):
    client, runtime = app
    model = _MessageOnlyModel(_decide_research)
    runtime.copilot_service.provider = model
    client.post("/copilot/sessions", json={"session_id": "attached-research"})
    payload = _research_payload(client, "attached-research")
    plan = client.post("/copilot/operator-plan", json=payload).json()
    assert [step["tool_id"] for step in plan["steps"]] == ["run_research_basket_analysis"]
    response = client.post("/copilot/operator-plan/execute", json=payload)
    assert response.status_code == 200 and response.json()["status"] == "ready", response.json()
    observation = model.observations[0]
    assert observation["status"] == "completed", observation
    assert observation["arguments"]["positions"] == [{"symbol": "AAPL", "weight": 0.6}, {"symbol": "MSFT", "weight": 0.4}]
    assert observation["arguments"]["benchmark_symbol"] == "QQQ"
    assert "performance_points" not in json.dumps(model.messages[0])


def test_active_research_scope_message_has_positions_not_metrics(app):
    client, runtime = app
    payload = _research_payload(client, None)
    from src.api.schemas.copilot import CopilotResearchCardRequestModel
    request = CopilotResearchCardRequestModel.model_validate(payload).to_domain()
    _, body = _message(runtime, request)
    attached = body["attached_context"]["research_scope"]
    assert attached["scope_type"] == "synthetic_portfolio" and attached["benchmark_symbol"] == "SPY"
    assert attached["positions"] == [{"symbol": "AAPL", "weight": 0.6}, {"symbol": "MSFT", "weight": 0.4}]
    text = json.dumps(body)
    assert "performance_points" not in text and "constituents" not in text and "observations_count" not in text
    assert "MSFT" not in _outside_attached(body)


# --- Macro: vista visible -------------------------------------------------------------------------

def _macro_request(session_id=None):
    return _operator_request(
        "Analyze macro series us-cpi-yoy for the current Macro view",
        context=CopilotRequestContext(current_tab="macro", workspace_mode="research",
            macro=MacroCopilotContext(region="US", timeframe="1Y")),
        session_id=session_id,
    )


def _decide_macro(message):
    view = message["attached_context"]["macro_view"]
    series = re.search(r"macro series ([a-z0-9-]+)", message["task"])[1]
    return "run_macro_series_analysis", {"series_id": series, "region": view["region"], "timeframe": view["timeframe"]}


def test_model_completes_macro_series_from_visible_view(app):
    client, runtime = app
    plan, body = _message(runtime, _macro_request())
    assert [step.tool_id for step in plan.steps] == ["run_macro_series_analysis"]
    assert body["attached_context"]["macro_view"]["region"] == "US"
    assert "1Y" not in _outside_attached(body)
    _, observation = _run_message_only(client, runtime, _macro_request("attached-macro"), _decide_macro)
    assert observation["arguments"] == {"series_id": "us-cpi-yoy", "region": "US", "timeframe": "1Y"}


# --- Síntesis: dominios seleccionados -------------------------------------------------------------

def _synthesis_request(session_id=None):
    return _operator_request(
        "Explain how the selected contexts relate to each other",
        context=CopilotRequestContext(current_tab="synthesis", workspace_mode="research"),
        synthesis=CopilotSynthesisRequest(active_tab="macro", included_scopes=[
            CopilotSynthesisScope(domain="macro", context=CopilotRequestContext(current_tab="macro", macro=MacroCopilotContext())),
            CopilotSynthesisScope(domain="crypto", context=CopilotRequestContext(current_tab="crypto", crypto_token_id="bitcoin")),
        ]),
        session_id=session_id,
    )


def test_model_reads_a_selected_synthesis_domain_without_a_discovery_call(app):
    client, runtime = app
    plan, body = _message(runtime, _synthesis_request())
    assert "get_synthesis_domain_context" in [step.tool_id for step in plan.steps]
    assert body["attached_context"]["synthesis_scope"]["included_domains"] == ["macro", "crypto"]
    _, observation = _run_message_only(client, runtime, _synthesis_request("attached-synthesis"),
        lambda message: ("get_synthesis_domain_context", {"domain": message["attached_context"]["synthesis_scope"]["included_domains"][0]}))
    assert observation["output"]["domain"] == "macro"


# --- Límites comunes -----------------------------------------------------------------------------

def test_no_attached_context_when_no_planned_tool_needs_it(app):
    _, runtime = app
    request = _operator_request(
        "Research NVDA using the relevant Gamma domains.",
        context=CopilotRequestContext(current_tab="crypto", workspace_mode="research", crypto_token_id="bitcoin",
            macro=MacroCopilotContext(region="EU")),
    )
    _, body = _message(runtime, request)
    assert "attached_context" not in body


def test_agents_sdk_prompt_carries_the_same_attached_context(app):
    _, runtime = app
    request = _crypto_synthesis_request()
    plan, body = _message(runtime, request)
    prompt = json.loads(CopilotAgentsOperatorService._operator_prompt(request, plan, ["run_crypto_token_analysis"]))
    assert prompt["attached_context"] == body["attached_context"]


def test_operator_instructions_explain_attached_context_usage(app):
    _, runtime = app
    plan = runtime.copilot_service.plan_research_operator(_crypto_synthesis_request())
    instructions = OpenAIResponsesCopilotProvider._build_operator_instructions(plan)
    assert "attached_context holds identities the user visibly attached" in instructions
    assert "explicit task values always win" in instructions


def test_attached_blocks_are_bounded_and_carry_no_outputs():
    from src.application.copilot_operator_context import (
        MAX_ATTACHED_COMPOSITION_LEGS, MAX_ATTACHED_RESEARCH_POSITIONS, operator_attached_context)
    from src.models.copilot import CopilotOperatorPlan, CopilotOperatorPlanStep

    def plan(tool_id):
        return CopilotOperatorPlan(intent="test", steps=[CopilotOperatorPlanStep(
            step_id="step_01", order=1, title="t", domain="research", action_type="run_analysis", tool_id=tool_id)])

    legs = [{"label": f"L{i}", "asset_class": "equity", "identifier": f"S{i}", "weight": 0.01,
             "return_points": [{"value": 1.0}]} for i in range(40)]
    # La composición también llega desde Research (research_state.strategy_composition).
    research = CopilotRequestContext(current_tab="research", research_state={
        "strategy_composition": {"portfolio_inputs": {"name": "Big", "legs": legs}},
        "result": {"scope_type": "synthetic_portfolio", "benchmark_symbol": "SPY", "summary": {"beta": 1.2},
                   "weights": [{"symbol": f"S{i}", "weight": 0.001, "instrument_id": "x"} for i in range(150)]},
    })
    request = CopilotResearchCardRequest(domain="research", prompt="p", context=research)
    composition = operator_attached_context(request, plan("run_strategy_lab_portfolio_backtest"))["strategy_lab_composition"]
    assert len(composition["legs"]) == MAX_ATTACHED_COMPOSITION_LEGS and composition["legs_truncated"] is True
    assert all(set(leg) == {"label", "asset_class", "identifier", "weight"} for leg in composition["legs"])
    scope = operator_attached_context(request, plan("run_research_basket_analysis"))["research_scope"]
    assert len(scope["positions"]) == MAX_ATTACHED_RESEARCH_POSITIONS and scope["positions_truncated"] is True
    assert all(set(row) == {"symbol", "weight"} for row in scope["positions"])
    assert "summary" not in scope and "beta" not in json.dumps(scope)
    # Sin estado adjunto no hay bloque, aunque la herramienta esté planificada.
    empty = CopilotResearchCardRequest(domain="research", prompt="p")
    for tool_id in ("run_strategy_lab_portfolio_backtest", "run_research_basket_analysis", "run_crypto_token_analysis",
                    "run_prediction_market_comparison", "draft_options_strategy", "run_macro_series_analysis",
                    "get_synthesis_domain_context"):
        assert operator_attached_context(empty, plan(tool_id)) is None, tool_id
