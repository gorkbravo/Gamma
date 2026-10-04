from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest

from test_copilot import _build_test_client, _checkpoint7_final_card, _crypto_token_fixture
from src.models.crypto import CryptoPricePoint
from src.models.copilot import CopilotContextBundle, CopilotResearchCardRequest, CopilotToolExecution, CopilotToolTrace
from src.services.copilot_store import CopilotStore
from src.utils.time import now_utc
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider


@pytest.fixture
def app(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    class CryptoFixture:
        def get_token_detail(self, token_id):
            return replace(_crypto_token_fixture(), token_id=token_id, source_provider="fixture", retrieved_at=now_utc())
        def get_price_history(self, token_id, *, days):
            return [CryptoPricePoint(timestamp=now_utc() - timedelta(days=offset), price=price,
                market_cap=1000.0, total_volume=100.0, source_provider="fixture", retrieved_at=now_utc(), origin="tests.crypto.history")
                for offset, price in [(days + 1, 10.0), (days - 1, 100.0), (0, 110.0)]]
        def get_dex_liquidity(self, token_id): return None
        def get_comparison(self, token_id): return None
    runtime.copilot_service.crypto_service = CryptoFixture()
    yield client, runtime
    runtime.shutdown()


@pytest.mark.parametrize("prompt,tool,inputs", [
    ("Analyze macro series us-cpi-yoy in US over 1Y", "run_macro_series_analysis", {"series_id": "us-cpi-yoy", "region": "US", "timeframe": "1Y"}),
    ("Analyze crypto token bitcoin over 90 days", "run_crypto_token_analysis", {"token_id": "bitcoin", "days": 90}),
])
def test_unloaded_evidence_lifecycle(app, prompt, tool, inputs):
    client, runtime = app
    session = "checkpoint8-final"
    client.post("/copilot/sessions", json={"session_id": session})
    payload = {"domain": "synthesis", "user_session_id": session, "prompt": prompt,
               "context": {"current_tab": "copilot"}}
    plan = client.post("/copilot/operator-plan", json=payload).json()
    assert [s["tool_id"] for s in plan["steps"]] == [tool], plan
    result = client.post("/copilot/operator-plan/execute", json=payload)
    assert result.status_code == 200
    assert result.json()["status"] in {"ready", "degraded"}, result.json()
    rows = client.get(f"/copilot/sessions/{session}").json()["working_analyses"]
    assert len(rows) == 1, result.json()
    row = rows[0]
    assert row["inputs"] == inputs
    assert row["outputs"]["sources"]
    restored = CopilotStore(runtime.copilot_store.base_dir).get_working_analysis(row["analysis_id"])
    assert restored.outputs == row["outputs"]
    path = f"/copilot/working-analyses/{row['analysis_id']}"
    assert client.post(path + "/materialize").status_code == 200
    assert client.post(path + "/materialize").status_code == 200
    # A follow-up reads retained values, not today's replacement provider data.
    followup = {**payload, "prompt": f"Explain the evidence in {row['analysis_id']}"}
    replay = client.post("/copilot/operator-plan/execute", json=followup).json()
    assert replay["status"] in {"ready", "degraded"}, replay
    assert replay["tool_traces"][0]["tool_name"] == "read_working_analysis"
    request = CopilotResearchCardRequest(domain="synthesis", role="research_operator", user_session_id="other")
    assert "error" in runtime.copilot_service._read_working_analysis({"analysis_id": row["analysis_id"]}, request).output
    assert client.post(path + "/discard").status_code == 200
    assert client.post(path + "/materialize").status_code == 409
    assert "error" in runtime.copilot_service._read_working_analysis({"analysis_id": row["analysis_id"]}, replace(request, user_session_id=session)).output


def test_unavailable_evidence_is_not_materializable(app):
    _, runtime = app
    service = runtime.copilot_service
    for tool in ("run_macro_series_analysis", "run_crypto_token_analysis", "inspect_commodity_curve_fundamentals"):
        execution = CopilotToolExecution(output={"status": "unavailable"}, trace=CopilotToolTrace(tool_name=tool, summary="Unavailable"))
        assert service._operator_working_analysis_spec(execution, tool_id=tool, arguments={},
            context=CopilotContextBundle(domain="synthesis", current_tab="copilot", summary_data={}),
            request=CopilotResearchCardRequest(domain="synthesis")) is None


@pytest.mark.parametrize("tool,args", [
    ("run_macro_series_analysis", {"series_id": "us-cpi-yoy", "region": "US", "timeframe": "10Y"}),
    ("run_crypto_token_analysis", {"token_id": "bitcoin", "days": 0}),
    ("run_crypto_token_analysis", {"token_id": "bitcoin", "days": 366}),
    ("run_crypto_token_analysis", {"token_id": "bitcoin", "days": "90"}),
])
def test_evidence_arguments_fail_closed(app, tool, args):
    _, runtime = app
    with pytest.raises(ValueError):
        runtime.copilot_service.action_registry.validate_arguments(tool, args)


def create_macro_analysis(client):
    client.post("/copilot/sessions", json={"session_id": "retained-cross-tool"})
    result = client.post("/copilot/operator-plan/execute", json={
        "domain": "synthesis", "user_session_id": "retained-cross-tool",
        "prompt": "Analyze macro series us-cpi-yoy in US over 1Y", "context": {"current_tab": "copilot"},
    }).json()
    assert result["status"] in {"ready", "degraded"}, result
    return client.get("/copilot/sessions/retained-cross-tool").json()["working_analyses"][0]


@pytest.mark.parametrize("runner", ["custom", "agents_sdk"])
def test_both_runners_read_retained_evidence_and_observe_new_analysis(app, monkeypatch, runner):
    import src.application.copilot_agents_operator as agents_operator
    from src.application.copilot_agents_operator import CopilotAgentsOperatorService, CopilotAgentsOperatorConfig
    client, runtime = app
    row = create_macro_analysis(client)
    calls = []
    arguments = [{"analysis_id": row["analysis_id"]}, {"token_id": "bitcoin", "days": 90}]
    names = ["read_working_analysis", "run_crypto_token_analysis"]

    def inspect_output(output, index):
        assert "error" not in output, output
        assert CopilotAgentsOperatorService._bounded_observation(output) == output
        if index == 0:
            assert output["outputs"] == row["outputs"]
            assert output["inputs"] == row["inputs"]
            assert output["original_source_ids"] == row["source_ids"]
            assert all(source.startswith(f"working_analysis.{row['analysis_id']}") for source in output["source_ids"])
        else:
            assert output["token_id"] == "bitcoin"
            assert output["days"] == 90
            assert output["working_analysis"]["owning_tab"] == "crypto"
        calls.append(names[index])

    class Provider(OpenAIResponsesCopilotProvider):
        def __init__(self):
            super().__init__(api_key="test-key", model="gpt-test-operator", reasoning_effort="low", store_responses=False)
            self.turn = 0
        def _post_json_stream(self, payload, emit, should_cancel):
            if self.turn:
                outputs = [item for item in payload["input"] if item.get("type") == "function_call_output"]
                inspect_output(json.loads(outputs[-1]["output"])["output"], self.turn - 1)
            index = self.turn
            self.turn += 1
            if index < 2:
                tool = next(tool for tool in payload["tools"] if tool["name"] == names[index])
                assert tool["strict"] is True
                content = [{"type": "function_call", "id": f"fc-{index}", "call_id": f"call-{index}", "name": names[index], "arguments": json.dumps(arguments[index])}]
            else:
                content = [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(_checkpoint7_final_card(rationale="The retained CPI snapshot and the new 90-day Bitcoin history have distinct source dates and units; their magnitudes are not directly comparable."))}]}]
            return ({"id": f"response-{index}", "model": self.model, "output": content}, "completed")

    class FakeTool:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class FakeAgent:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, max_turns):
            for index, name in enumerate(names):
                tool = next(tool for tool in agent.tools if tool.name == name)
                assert tool.strict_json_schema
                returned = json.loads(await tool.on_invoke_tool(None, json.dumps(arguments[index])))
                inspect_output(returned["output"], index)
            return SimpleNamespace(final_output=_checkpoint7_final_card(rationale="The retained CPI snapshot and fresh Bitcoin analysis preserve their different windows and provider warnings."))

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", runner)
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", "gpt-test-operator")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    runtime.copilot_service.model_policy.operator_orchestrator = runner
    if runner == "custom":
        runtime.copilot_service.provider = Provider()
    else:
        monkeypatch.setattr(agents_operator, "_load_agents_sdk", lambda: agents_operator._AgentsSdkModule(
            Agent=FakeAgent, Runner=FakeRunner, FunctionTool=FakeTool, function_tool=lambda func: func))
        runtime.copilot_service.agents_operator_service = CopilotAgentsOperatorService(CopilotAgentsOperatorConfig.from_env())
    payload = {"domain": "synthesis", "user_session_id": "retained-cross-tool",
               "prompt": f"Compare {row['analysis_id']} with crypto token bitcoin over 90 days", "context": {"current_tab": "copilot"}}
    result = client.post("/copilot/operator-plan/execute", json=payload).json()
    assert result["status"] in {"ready", "degraded"}, result
    assert calls == names
    assert len(client.get("/copilot/sessions/retained-cross-tool").json()["working_analyses"]) == 2


def test_retained_evidence_enforces_expiry_scope_role_and_deleted_session(app):
    client, runtime = app
    row = create_macro_analysis(client)
    service = runtime.copilot_service
    args = {"analysis_id": row["analysis_id"]}
    request = CopilotResearchCardRequest(domain="synthesis", role="research_operator", user_session_id=row["session_id"])
    assert "error" in service._read_working_analysis(args, replace(request, role="research_agent")).output
    assert "error" in service._read_working_analysis(args, replace(request, selected_scope_domains=["crypto"])).output
    analysis = service.store.get_working_analysis(row["analysis_id"])
    service.store.save_working_analysis(replace(analysis, expires_at=now_utc() - timedelta(seconds=1)))
    assert "error" in service._read_working_analysis(args, request).output
    with pytest.raises(Exception): service.materialize_working_analysis(row["analysis_id"])
    # Retrying the exact same output/run does not resurrect expired state.
    execution = CopilotToolExecution(output=row["outputs"]["result"], trace=CopilotToolTrace(tool_name=row["tool_id"], arguments=row["inputs"], summary="Retry"))
    context = CopilotContextBundle(domain="macro", current_tab="macro", summary_data={})
    retained = service._attach_operator_working_analysis(execution, tool_id=row["tool_id"], arguments=row["inputs"], context=context, request=request, run_id=row["run_id"])
    assert retained.output["working_analysis"]["status"] == "expired"
    assert client.delete(f"/copilot/sessions/{row['session_id']}", params={"confirm_session_id": row["session_id"]}).status_code == 200
    assert "error" in service._read_working_analysis(args, request).output


def test_crypto_degrades_independently_and_keeps_requested_window(app, monkeypatch):
    _, runtime = app
    service = runtime.copilot_service
    def failed(*args, **kwargs): raise RuntimeError("private provider payload")
    monkeypatch.setattr(service.crypto_service, "get_dex_liquidity", failed)
    context = CopilotContextBundle(domain="crypto", current_tab="copilot", summary_data={})
    execution = service._tool_run_crypto_token_analysis({"token_id": "bitcoin", "days": 30}, context)
    assert execution.output["status"] == "degraded"
    assert execution.output["history"]["observations"] > 0
    assert execution.output["liquidity"] is None
    assert "private provider payload" not in json.dumps(execution.output)
    assert execution.trace.arguments == {"token_id": "bitcoin", "days": 30}


def test_persistence_failure_is_visible_without_false_reopen_reference(app, monkeypatch):
    client, runtime = app
    row = create_macro_analysis(client)
    def failed(*args): raise OSError("Disk unavailable")
    monkeypatch.setattr(runtime.copilot_service.store, "save_working_analysis", failed)
    execution = CopilotToolExecution(output=row["outputs"]["result"], trace=CopilotToolTrace(tool_name=row["tool_id"], arguments=row["inputs"], summary="Analysis"))
    result = runtime.copilot_service._attach_operator_working_analysis(execution, tool_id=row["tool_id"], arguments=row["inputs"],
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        request=CopilotResearchCardRequest(domain="macro", role="research_operator", user_session_id=row["session_id"]), run_id="another-run")
    assert result.output["working_analysis_status"] == "persistence_failed"
    assert "working_analysis" not in result.output
    assert any("could not be retained" in warning for warning in result.output["warnings"])


@pytest.mark.parametrize("family", ["research", "strategy_lab", "commodities"])
def test_remaining_owning_surface_retains_service_output_without_mutating_inputs(app, family):
    from copy import deepcopy
    client, runtime = app
    service = runtime.copilot_service
    client.post("/copilot/sessions", json={"session_id": "remaining-surfaces"})
    if family == "research":
        tool = "run_research_scope_analysis"
        args = {"scope_type": "single_ticker", "primary_symbol": "AAPL", "benchmark_symbol": "SPY", "lookback_days": 252, "synthetic_positions": []}
        state = {}
    elif family == "strategy_lab":
        tool = "run_strategy_lab_backtest"
        args = {"result_kind": "imported_result"}
        state = {"imported_result": {"name": "Imported alpha", "source_provider": "uploaded_csv", "origin": "tests.import",
            "retrieved_at": now_utc().isoformat(), "metrics": {"observation_count": 100, "annual_return": 0.12},
            "returns_points": [{"timestamp": now_utc().isoformat(), "value": 0.01}]}}
    else:
        tool = "inspect_commodity_curve_fundamentals"
        args = {"instrument_id": "wti", "max_curve_nodes": 2, "max_inventory_points": 2}
        state = {"workspace": {"source_provider": "fixture", "retrieved_at": now_utc().isoformat(), "coverage": {"coverage_status": "partial"},
            "curves": [{"instrument_id": "wti", "source_provider": "fixture", "shape_label": "backwardation", "nodes": [
                {"contract": {"contract_id": "exact-contract", "symbol": "CL", "contract_month": "2026-12"}, "price": 70.0}]}]}}
    before = deepcopy(state)
    context = CopilotContextBundle(domain=family, current_tab="copilot", summary_data={}, tool_state=state)
    execution = service._execute_tool(tool, args, context)
    assert "error" not in execution.output, execution.output
    attached = service._attach_operator_working_analysis(execution, tool_id=tool, arguments=args, context=context,
        request=CopilotResearchCardRequest(domain=family, role="research_operator", user_session_id="remaining-surfaces"), run_id="surface-run")
    assert state == before
    analysis = service.get_working_analysis(attached.output["working_analysis"]["analysis_id"])
    assert analysis.outputs["result"] == execution.output
    assert analysis.outputs["sources"] and analysis.inputs == execution.trace.arguments
    assert service.materialize_working_analysis(analysis.analysis_id).materialization["durable"] is False


def test_macro_rejects_substitution_and_empty_window(app, monkeypatch):
    _, runtime = app
    service = runtime.copilot_service
    context = CopilotContextBundle(domain="macro", current_tab="copilot", summary_data={})
    history = service.macro_service.get_series_history("us-cpi-yoy", region="US", timeframe="1Y")
    monkeypatch.setattr(service.macro_service, "get_series_history", lambda *args, **kwargs: replace(history, series_id="different-series"))
    with pytest.raises(ValueError, match="no substitute"):
        service._tool_run_macro_series_analysis({"series_id": "us-cpi-yoy", "region": "US", "timeframe": "1Y"}, context)
    monkeypatch.setattr(service.macro_service, "get_series_history", lambda *args, **kwargs: replace(history, points=[]))
    empty = service._tool_run_macro_series_analysis({"series_id": "us-cpi-yoy", "region": "US", "timeframe": "1Y"}, context)
    assert empty.output["status"] == "unavailable" and empty.output["observations"] == 0
    assert service._operator_working_analysis_spec(empty, tool_id="run_macro_series_analysis", arguments={}, context=context,
        request=CopilotResearchCardRequest(domain="macro")) is None
