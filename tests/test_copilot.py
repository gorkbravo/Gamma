from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.copilot import CopilotResearchCardResult, ResearchCard, ResearchClaim


class _StubCopilotProvider:
    provider_name = "stub_provider"

    def generate_research_card(self, *, request, context, tool_specs, execute_tool):
        assert tool_specs
        if request.domain == "portfolio":
            positions_execution = execute_tool("get_portfolio_positions_summary", {}, context)
            performance_execution = execute_tool("get_portfolio_performance_context", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_portfolio",
                card=ResearchCard(
                    title="Portfolio test card",
                    hypothesis="The portfolio is concentrated enough that benchmark-relative framing matters.",
                    rationale="The active Gamma portfolio context exposes the current book, performance overlay, and local history.",
                    required_data=["Latest position snapshot", "Benchmark-relative performance"],
                    proposed_test="Compare top holdings and cash weight against the current benchmark-relative return path.",
                    confounders=["History gaps", "Benchmark choice"],
                    next_steps=["Inspect top positions", "Review local-history drawdown"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Portfolio snapshot and performance tools were available to the copilot.",
                            evidence_refs=[positions_execution.sources[0].source_id, *performance_execution.trace.source_ids],
                        )
                    ],
                    inferred_claims=["Allocation quality still requires judgment."],
                ),
                sources=[*context.sources, *positions_execution.sources, *performance_execution.sources],
                tool_traces=[positions_execution.trace, performance_execution.trace],
                warnings=list(context.warnings),
            )

        if request.domain == "research":
            scope_execution = execute_tool("get_research_scope_summary", {}, context)
            coverage_execution = execute_tool("get_research_coverage_context", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_research",
                card=ResearchCard(
                    title="Research test card",
                    hypothesis="The active research scope is coherent enough to refine into a sharper benchmark-relative question.",
                    rationale="The current Gamma research context exposes weights, structure, constituent results, and coverage.",
                    required_data=["Current scope weights", "Coverage diagnostics"],
                    proposed_test="Contrast the top weighted names against the weakest constituent and benchmark overlap.",
                    confounders=["Synthetic scope concentration", "Missing history"],
                    next_steps=["Inspect top weights", "Review missing-symbol warnings"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Research scope and coverage tools were both available to the copilot.",
                            evidence_refs=[scope_execution.sources[0].source_id, coverage_execution.sources[0].source_id],
                        )
                    ],
                    inferred_claims=["The cleanest next test remains inferential."],
                ),
                sources=[*context.sources, *scope_execution.sources, *coverage_execution.sources],
                tool_traces=[scope_execution.trace, coverage_execution.trace],
                warnings=list(context.warnings),
            )

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

        if request.domain == "risk":
            coverage_execution = execute_tool("get_risk_coverage_summary", {}, context)
            contribution_execution = execute_tool("get_risk_contribution_summary", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_risk",
                card=ResearchCard(
                    title="Risk test card",
                    hypothesis="The active risk result is only as strong as its coverage and top contribution concentration.",
                    rationale="The Gamma risk context exposes coverage ratios, exclusions, contribution rank, and Monte Carlo context.",
                    required_data=["Coverage ratio", "Top contribution rank"],
                    proposed_test="Compare top contribution share against excluded assets and benchmark overlap before drawing conclusions.",
                    confounders=["Incomplete coverage", "Benchmark window sensitivity"],
                    next_steps=["Review coverage summary", "Inspect top contributors"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Risk coverage and contribution tools were both available to the copilot.",
                            evidence_refs=[coverage_execution.sources[0].source_id, contribution_execution.sources[0].source_id],
                        )
                    ],
                    inferred_claims=["The hedge implication remains inferential."],
                ),
                sources=[*context.sources, *coverage_execution.sources, *contribution_execution.sources],
                tool_traces=[coverage_execution.trace, contribution_execution.trace],
                warnings=list(context.warnings),
            )

        if request.domain == "iv":
            surface_execution = execute_tool("get_iv_surface_context", {}, context)
            session_execution = execute_tool("get_iv_session_status", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_iv",
                card=ResearchCard(
                    title="IV test card",
                    hypothesis="The active IV surface is usable for framing term-structure and skew questions, not valuation certainty.",
                    rationale="The Gamma IV context exposes the loaded surface plus session and market-data-mode state.",
                    required_data=["ATM term structure", "Session status"],
                    proposed_test="Compare front-expiry ATM IV against the broader term structure before interpreting skew.",
                    confounders=["Delayed data", "Sparse surface points"],
                    next_steps=["Inspect the active surface", "Check session status"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="IV surface and session tools were both available to the copilot.",
                            evidence_refs=[surface_execution.sources[0].source_id, session_execution.sources[0].source_id],
                        )
                    ],
                    inferred_claims=["The options implication remains inferential."],
                ),
                sources=[*context.sources, *surface_execution.sources, *session_execution.sources],
                tool_traces=[surface_execution.trace, session_execution.trace],
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


def test_portfolio_copilot_route_uses_portfolio_context_tools(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        history = client.get("/portfolio/history").json()
        performance = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        ).json()

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "portfolio",
                "prompt": "Frame the active portfolio setup.",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {
                        "snapshot": snapshot,
                        "history": history,
                        "performance": performance,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Portfolio test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_portfolio_positions_summary",
            "get_portfolio_performance_context",
        }
        assert any(source["source_id"] == "portfolio.snapshot" for source in payload["sources"])
        assert any(source["source_id"] == "portfolio.performance.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_research_copilot_route_uses_research_context_tools(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        research = client.post(
            "/research/analyze",
            json={
                "scope_type": "single_ticker",
                "primary_symbol": "AAPL",
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        ).json()

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "research",
                "prompt": "Stress-test the current scope.",
                "context": {
                    "current_tab": "research",
                    "workspace_mode": "research",
                    "research_state": {
                        "result": research,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Research test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_research_scope_summary",
            "get_research_coverage_context",
        }
        assert any(source["source_id"] == "research.result" for source in payload["sources"])
        assert any(source["source_id"] == "research.coverage.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_risk_copilot_route_uses_risk_context_tools(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        research = client.post(
            "/research/analyze",
            json={
                "scope_type": "single_ticker",
                "primary_symbol": "AAPL",
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        ).json()
        risk = client.post(
            "/risk/compute",
            json={
                "snapshot": research["snapshot"],
                "alpha": 0.95,
                "lookback_days": 252,
                "horizon_days": 1,
                "mc_horizon_days": 10,
                "mc_simulation_model": "Gaussian",
                "mc_num_simulations": 500,
                "beta_window": 63,
                "benchmark_symbol": "SPY",
            },
        ).json()

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "risk",
                "prompt": "Explain the active risk picture.",
                "context": {
                    "current_tab": "risk",
                    "workspace_mode": "research",
                    "risk_state": {
                        "snapshot": research["snapshot"],
                        "result": risk,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Risk test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_risk_coverage_summary",
            "get_risk_contribution_summary",
        }
        assert any(source["source_id"] == "risk.result" for source in payload["sources"])
        assert any(source["source_id"] == "risk.coverage.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_iv_copilot_route_uses_iv_context_tools(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        surface = client.get("/iv/surface", params={"symbol": "SPY"}).json()
        session = client.post("/iv/session/start", json={"symbol": "SPY", "market_data_mode": "delayed"}).json()

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "iv",
                "prompt": "Interpret the active surface.",
                "context": {
                    "current_tab": "iv",
                    "workspace_mode": "portfolio",
                    "iv_state": {
                        "surface": surface,
                        "session": session,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "IV test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_iv_surface_context",
            "get_iv_session_status",
        }
        assert any(source["source_id"] == "iv.surface" for source in payload["sources"])
        assert any(source["source_id"] == "iv.session.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_current_tab_is_primary_copilot_routing_key(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        history = client.get("/portfolio/history").json()
        performance = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        ).json()

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Use the active tab.",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {
                        "snapshot": snapshot,
                        "history": history,
                        "performance": performance,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["domain"] == "portfolio"
        assert payload["card"]["title"] == "Portfolio test card"
    finally:
        runtime.shutdown()
