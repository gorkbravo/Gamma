from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.copilot import CopilotResearchCardResult, ResearchCard, ResearchClaim


class _StubCopilotProvider:
    provider_name = "stub_provider"

    def generate_research_card(self, *, request, context, tool_specs, execute_tool):
        assert tool_specs
        if request.domain == "macro":
            series_execution = execute_tool(
                "get_macro_series_history_summary",
                {"series_id": "us-cpi-yoy", "region": None},
                context,
            )
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_macro",
                card=ResearchCard(
                    title="Macro test card",
                    hypothesis="Inflation remains the dominant macro swing factor.",
                    rationale="The active Gamma macro context shows inflation-sensitive cards and current divergences.",
                    required_data=["Updated CPI trajectory", "Rates path repricing"],
                    proposed_test="Compare inflation-linked series against rates-policy and cross-asset signals over the active window.",
                    confounders=["Event timing", "Comparison-region noise"],
                    next_steps=["Review the latest macro events", "Check linked market alignment"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="The macro workspace context was available to the copilot.",
                            evidence_refs=[context.sources[0].source_id, series_execution.sources[0].source_id],
                        )
                    ],
                    inferred_claims=["The next regime transition remains inferential."],
                ),
                sources=[*context.sources, *series_execution.sources],
                tool_traces=[series_execution.trace],
                warnings=list(context.warnings),
            )

        history_execution = execute_tool("get_prediction_market_history_summary", {}, context)
        flow_execution = execute_tool("get_prediction_market_flow_context", {}, context)
        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="ready",
            provider=self.provider_name,
            model="stub-model",
            response_id="resp_stub_prediction",
            card=ResearchCard(
                title="Prediction market test card",
                hypothesis="The selected market is still repricing and flow does not fully confirm consensus.",
                rationale="The Gamma market context exposes current pricing, history, related markets, and wallet concentration.",
                required_data=["Fresh venue history", "Related-contract consistency"],
                proposed_test="Contrast current probability versus recent range and linked-market gaps.",
                confounders=["Venue freshness", "Sparse calibration coverage"],
                next_steps=["Inspect related market gaps", "Review wallet concentration"],
                caveats=["This is a test fixture."],
                source_backed_claims=[
                    ResearchClaim(
                        claim="Prediction history and flow tools were both available to the copilot.",
                        evidence_refs=[history_execution.sources[0].source_id, *flow_execution.trace.source_ids],
                    )
                ],
                inferred_claims=["Near-term edge remains inferential until new catalysts arrive."],
            ),
            sources=[*context.sources, *history_execution.sources, *flow_execution.sources],
            tool_traces=[history_execution.trace, flow_execution.trace],
            warnings=list(context.warnings),
        )


def _build_test_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.copilot_service.provider = _StubCopilotProvider()
    return TestClient(create_app(runtime)), runtime


def test_macro_copilot_route_returns_structured_research_card(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Frame the active macro setup.",
                "context": {
                    "current_tab": "macro",
                    "macro": {
                        "mode": "rates_policy",
                        "region": "US",
                        "timeframe": "3M",
                        "theme": "policy",
                        "comparison_region": "EU",
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "stub_provider"
        assert payload["card"]["title"] == "Macro test card"
        assert payload["tool_traces"][0]["tool_name"] == "get_macro_series_history_summary"
        assert any(source["source_id"] == "macro.snapshot" for source in payload["sources"])
        assert any(source["source_id"].startswith("macro.series.us-cpi-yoy") for source in payload["sources"])
        assert payload["card"]["source_backed_claims"][0]["evidence_refs"]
    finally:
        runtime.shutdown()


def test_prediction_market_copilot_route_uses_prediction_tool_context(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        screener = client.post("/prediction-markets/screener", json={})
        assert screener.status_code == 200
        market_id = screener.json()["markets"][0]["market_id"]

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "prediction_markets",
                "prompt": "Assess the current repricing setup.",
                "context": {
                    "current_tab": "prediction_markets",
                    "prediction_market_id": market_id,
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Prediction market test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_prediction_market_history_summary",
            "get_prediction_market_flow_context",
        }
        assert any(source["source_id"] == "prediction.detail" for source in payload["sources"])
        assert any(source["source_id"] == "prediction.history.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_prediction_market_copilot_requires_selection(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "prediction_markets",
                "context": {
                    "current_tab": "prediction_markets",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "requires a selected market" in payload["message"]
    finally:
        runtime.shutdown()
