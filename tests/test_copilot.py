from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    ResearchCard,
    ResearchClaim,
)
from src.models.crypto import (
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoPricePoint,
    CryptoTokenRecord,
)
from src.models.macro import (
    MacroDivergenceRecord,
    MacroEventRecord,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotFocusItem,
    MacroSnapshotPayload,
)
from src.services.mock_copilot_provider import MockCopilotProvider
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider


class _StubCopilotProvider:
    provider_name = "stub_provider"

    def generate_research_card(self, *, request, context, tool_specs, execute_tool):
        assert tool_specs
        if request.domain == "synthesis":
            scope_execution = execute_tool("get_synthesis_scope_summary", {}, context)
            included_contexts = scope_execution.output.get("included_contexts", [])
            drilldown_executions = [
                execute_tool("get_synthesis_domain_context", {"domain": item["domain"]}, context)
                for item in included_contexts[:2]
                if isinstance(item, dict) and item.get("domain")
            ]
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_synthesis",
                card=ResearchCard(
                    title="Synthesis test card",
                    hypothesis="The loaded Gamma contexts should be read together rather than as isolated tab answers.",
                    rationale="The synthesis scope exposes multiple included Gamma domains plus synthesis drilldowns.",
                    required_data=["Included Gamma domains", "Attached source references"],
                    proposed_test="Compare the strongest agreement and disagreement across the included contexts before narrowing the scope.",
                    confounders=["Uneven freshness", "Domain-specific warnings"],
                    next_steps=["Inspect the synthesis scope", "Review the domain drilldowns"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="The synthesis scope and domain drilldowns were available to the copilot.",
                            evidence_refs=[
                                scope_execution.sources[0].source_id,
                                *[
                                    execution.sources[0].source_id
                                    for execution in drilldown_executions
                                    if execution.sources
                                ],
                            ],
                        )
                    ],
                    inferred_claims=["The best synthesis thesis remains interpretive."],
                ),
                sources=[
                    *context.sources,
                    *scope_execution.sources,
                    *[source for execution in drilldown_executions for source in execution.sources],
                ],
                tool_traces=[scope_execution.trace, *[execution.trace for execution in drilldown_executions]],
                warnings=list(context.warnings),
            )

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

        if request.domain == "crypto":
            history_execution = execute_tool("get_crypto_price_history_summary", {}, context)
            liquidity_execution = execute_tool("get_crypto_liquidity_context", {}, context)
            comparison_execution = execute_tool("get_crypto_comparison_context", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_crypto",
                card=ResearchCard(
                    title="Crypto test card",
                    hypothesis="The selected token should be framed through price path, liquidity, and relative context together.",
                    rationale="The Gamma crypto context exposes normalized token detail, price history, DEX liquidity, and comparison context.",
                    required_data=["Price history", "DEX liquidity", "Relative comparison"],
                    proposed_test="Compare recent price path against the current comparison target and DEX liquidity depth.",
                    confounders=["Category labels", "Pool-match heuristics"],
                    next_steps=["Inspect the recent path", "Review DEX depth"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Crypto history, liquidity, and comparison tools were available to the copilot.",
                            evidence_refs=[
                                history_execution.sources[0].source_id,
                                liquidity_execution.sources[0].source_id,
                                comparison_execution.sources[0].source_id,
                            ],
                        )
                    ],
                    inferred_claims=["Token thesis quality still requires interpretation."],
                ),
                sources=[*context.sources, *history_execution.sources, *liquidity_execution.sources, *comparison_execution.sources],
                tool_traces=[history_execution.trace, liquidity_execution.trace, comparison_execution.trace],
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


class _FollowupCaptureProvider:
    provider_name = "followup_capture"

    def __init__(self):
        self.previous_response_ids: list[str | None] = []

    def generate_research_card(self, *, request, context, tool_specs, execute_tool):
        self.previous_response_ids.append(request.previous_response_id)
        turn = len(self.previous_response_ids)
        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="ready",
            provider=self.provider_name,
            model="stub-model",
            response_id=f"resp_followup_{turn}",
            card=ResearchCard(
                title=f"Follow-up test card {turn}",
                hypothesis="Continuation should preserve the previous response id at the route boundary.",
                rationale="This fixture only captures the forwarded request metadata.",
                required_data=["previous_response_id"],
                proposed_test="Assert that the second request forwards the first response id.",
                confounders=["None for this fixture."],
                next_steps=["Verify the captured request metadata."],
                caveats=["This is a test fixture."],
                source_backed_claims=[
                    ResearchClaim(
                        claim="The route forwarded the request metadata into the provider boundary.",
                        evidence_refs=[],
                    )
                ],
                inferred_claims=[],
            ),
            sources=list(context.sources),
            tool_traces=[],
            warnings=list(context.warnings),
        )


class _StubMacroService:
    retrieved_at = datetime(2026, 4, 5, 10, 0, 0)

    def get_snapshot(self, request):
        metric = MacroMetricRecord(
            metric_id="policy-rate",
            label="Policy rate",
            value=5.25,
            display_value="5.25%",
            delta_display="+25 bps",
            series_id="us-policy-rate",
            source_provider="fixture",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.macro_fixture",
        )
        event = self.get_events(region=request.region, force_refresh=False)[0]
        return MacroSnapshotPayload(
            region=request.region,
            timeframe=request.timeframe,
            theme=request.theme,
            comparison_region=request.comparison_region,
            available_regions=["US", "EU", "Global"],
            available_timeframes=["3M", "1Y"],
            available_themes=["all", "policy", "inflation"],
            focus_items=[
                MacroSnapshotFocusItem(
                    focus_id="policy-focus",
                    title="Policy repricing",
                    summary="Front-end rates are the active macro swing factor.",
                    why_now="The fixture marks policy as the current focus.",
                    mode_target="rates_policy",
                    target_theme="policy",
                    source_provider="fixture",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.macro_fixture",
                )
            ],
            snapshot_cards=[
                MacroSnapshotCard(
                    card_id="rates",
                    title="Rates",
                    subtitle="Policy",
                    summary="Rates remain restrictive in the fixture context.",
                    mode_target="rates_policy",
                    target_theme="policy",
                    why_now="Policy context is loaded for Copilot tests.",
                    metrics=[metric],
                    source_provider="fixture",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.macro_fixture",
                )
            ],
            rates_policy=MacroRatesPolicySummary(
                headline="Policy remains restrictive",
                summary="Fixture policy summary for Copilot route tests.",
                policy_metrics=[metric],
                events=[event],
                path_headline="Hold path",
                path_summary="The fixture path is stable.",
                market_alignment_label="mixed",
                market_alignment_summary="Fixture markets are mixed.",
                source_provider="fixture",
                retrieved_at=self.retrieved_at,
                origin="tests.copilot.macro_fixture",
            ),
            top_divergences=self.get_divergences(request),
            upcoming_events=[event],
            warnings=[],
            source_provider="fixture",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.macro_fixture",
        )

    def get_divergences(self, request, *, histories=None, comparison_histories=None):
        del histories, comparison_histories
        return [
            MacroDivergenceRecord(
                divergence_id="policy-gap",
                theme=request.theme,
                region=request.region,
                headline="Policy gap",
                summary="Fixture divergence keeps Copilot route tests offline.",
                score=0.72,
                label="elevated",
                series_ids=["us-cpi-yoy", "us-policy-rate"],
                research_focus="Check whether inflation confirms the policy signal.",
                source_provider="fixture",
                retrieved_at=self.retrieved_at,
                origin="tests.copilot.macro_fixture",
                comparison_region=request.comparison_region,
            )
        ]

    def get_events(self, *, region="US", force_refresh=False):
        del force_refresh
        return [
            MacroEventRecord(
                event_id="fixture-cpi",
                title="CPI Release",
                category="inflation",
                region=region,
                scheduled_at=datetime(2026, 4, 15, 12, 30, 0),
                relative_label="next",
                importance="high",
                source_provider="fixture",
                retrieved_at=self.retrieved_at,
                origin="tests.copilot.macro_fixture",
            )
        ]

    def get_series_history(self, series_id, *, region="US", timeframe="3M", force_refresh=False):
        del force_refresh
        return MacroSeriesHistory(
            series_id=series_id,
            title="US CPI YoY",
            region=region,
            unit="percent",
            frequency="monthly",
            theme="inflation",
            mode_tags=["snapshot", "rates_policy"],
            points=[
                MacroSeriesPoint(
                    timestamp=datetime(2026, 1, 1, 0, 0, 0),
                    value=3.1,
                    source_provider="fixture",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.macro_fixture",
                ),
                MacroSeriesPoint(
                    timestamp=datetime(2026, 4, 1, 0, 0, 0),
                    value=3.4,
                    source_provider="fixture",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.macro_fixture",
                ),
            ],
            source_provider="fixture",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.macro_fixture",
            transformation_note=f"Fixture {timeframe} macro history keeps Copilot route tests hermetic.",
        )


def _build_test_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.copilot_service.provider = _StubCopilotProvider()
    runtime.copilot_service.macro_service = _StubMacroService()
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


def test_macro_copilot_route_degrades_when_macro_provider_fails(tmp_path):
    class FailingMacroService:
        def get_snapshot(self, request):
            del request
            raise RuntimeError("FRED returned HTTP 500")

    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.macro_service = FailingMacroService()
    runtime.copilot_service.provider = _FollowupCaptureProvider()
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Frame the active macro setup.",
                "context": {
                    "current_tab": "macro",
                    "macro": {
                        "mode": "snapshot",
                        "region": "US",
                        "timeframe": "3M",
                        "theme": "all",
                        "comparison_region": None,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any("Macro context is degraded" in warning for warning in payload["warnings"])
        assert any(source["source_id"] == "macro.degraded" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_synthesis_copilot_route_returns_cross_context_research_card(tmp_path):
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
                "domain": "synthesis",
                "context": {
                    "current_tab": "synthesis",
                    "workspace_mode": "research",
                },
                "synthesis": {
                    "active_tab": "macro",
                    "included_scopes": [
                        {
                            "domain": "portfolio",
                            "label": "Portfolio",
                            "context_fingerprint": "fp_portfolio_fixture",
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
                        {
                            "domain": "macro",
                            "label": "Macro",
                            "context_fingerprint": "fp_macro_fixture",
                            "context": {
                                "current_tab": "macro",
                                "workspace_mode": "research",
                                "macro": {
                                    "mode": "snapshot",
                                    "region": "US",
                                    "timeframe": "3M",
                                    "theme": "all",
                                    "comparison_region": None,
                                },
                            },
                        },
                    ],
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["domain"] == "synthesis"
        assert payload["card"]["title"] == "Synthesis test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_synthesis_scope_summary",
            "get_synthesis_domain_context",
        }
        assert any(source["source_id"] == "synthesis.scope" for source in payload["sources"])
        assert any(source["source_id"] == "portfolio.snapshot" for source in payload["sources"])
        assert any(source["source_id"] == "macro.snapshot" for source in payload["sources"])
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


def test_crypto_copilot_route_uses_crypto_tool_context(tmp_path):
    client, runtime = _build_test_client(tmp_path)

    class StubCryptoService:
        def get_token_detail(self, token_id: str, *, force_refresh: bool = False):
            del force_refresh
            return _crypto_token_fixture() if token_id == "solana" else None

        def get_price_history(self, token_id: str, *, days: int = 30, force_refresh: bool = False):
            del days, force_refresh
            if token_id != "solana":
                return []
            token = _crypto_token_fixture()
            return [
                CryptoPricePoint(
                    timestamp=token.retrieved_at,
                    price=150.0,
                    market_cap=token.market_cap,
                    total_volume=token.total_volume,
                    source_provider="coingecko",
                    retrieved_at=token.retrieved_at,
                    origin="coingecko.market_chart",
                )
            ]

        def get_dex_liquidity(self, token_id: str, *, force_refresh: bool = False):
            del force_refresh
            if token_id != "solana":
                return None
            token = _crypto_token_fixture()
            return CryptoDexLiquiditySummary(
                token_id="solana",
                lookup_strategy="contract_lookup",
                matched_networks=["solana"],
                total_reserve_usd=180_000_000.0,
                total_volume_24h=45_000_000.0,
                total_buys_24h=9_000,
                total_sells_24h=8_700,
                total_buyers_24h=5_200,
                total_sellers_24h=5_100,
                dominant_dex="raydium",
                warnings=[],
                source_provider="geckoterminal",
                retrieved_at=token.retrieved_at,
                origin="geckoterminal.liquidity_summary",
            )

        def get_comparison(self, token_id: str, *, target_token_id=None, basket_id=None, force_refresh: bool = False):
            del target_token_id, basket_id, force_refresh
            if token_id != "solana":
                return None
            token = _crypto_token_fixture()
            return CryptoComparisonRecord(
                subject_token_id="solana",
                target_kind="basket",
                target_id="layer-1",
                target_label="Layer 1",
                shared_categories=["Layer 1"],
                subject_price_change_pct_24h=token.price_change_pct_24h,
                target_price_change_pct_24h=2.1,
                price_gap_pct_24h=2.1,
                subject_price_change_pct_7d=token.price_change_pct_7d,
                target_price_change_pct_7d=5.2,
                price_gap_pct_7d=5.3,
                subject_price_change_pct_30d=token.price_change_pct_30d,
                target_price_change_pct_30d=11.4,
                price_gap_pct_30d=6.8,
                subject_market_cap=token.market_cap,
                target_market_cap=900_000_000_000.0,
                market_cap_ratio=0.083,
                subject_turnover_ratio_24h=token.turnover_ratio_24h,
                target_turnover_ratio_24h=0.06,
                turnover_gap=0.03,
                summary="Solana is outperforming the Layer 1 basket with hotter turnover.",
                source_provider="gamma",
                retrieved_at=token.retrieved_at,
                origin="gamma.crypto.comparison.basket",
            )

    runtime.copilot_service.crypto_service = StubCryptoService()
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "crypto",
                "prompt": "Frame the active token setup.",
                "context": {
                    "current_tab": "crypto",
                    "workspace_mode": "research",
                    "crypto_token_id": "solana",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Crypto test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_crypto_price_history_summary",
            "get_crypto_liquidity_context",
            "get_crypto_comparison_context",
        }
        assert any(source["source_id"] == "crypto.detail" for source in payload["sources"])
        assert any(source["source_id"] == "crypto.liquidity.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()


def test_crypto_copilot_requires_selection(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "crypto",
                "context": {
                    "current_tab": "crypto",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "requires a selected token" in payload["message"]
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


def test_runtime_uses_mock_copilot_provider_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        assert isinstance(runtime.copilot_service.provider, MockCopilotProvider)
        assert runtime.copilot_service.provider.provider_name == "mock"
    finally:
        runtime.shutdown()


def test_copilot_route_forwards_previous_response_id_on_follow_up(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    capture_provider = _FollowupCaptureProvider()
    runtime.copilot_service.provider = capture_provider
    try:
        first_response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Map the active macro setup.",
                "context": {
                    "current_tab": "macro",
                    "macro": {
                        "mode": "snapshot",
                        "region": "US",
                        "timeframe": "3M",
                        "theme": "all",
                        "comparison_region": None,
                    },
                },
            },
        )
        assert first_response.status_code == 200
        first_payload = first_response.json()

        second_response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Pressure-test the lead divergence.",
                "previous_response_id": first_payload["response_id"],
                "context": {
                    "current_tab": "macro",
                    "macro": {
                        "mode": "snapshot",
                        "region": "US",
                        "timeframe": "3M",
                        "theme": "all",
                        "comparison_region": None,
                    },
                },
            },
        )
        assert second_response.status_code == 200
        assert capture_provider.previous_response_ids == [None, first_payload["response_id"]]
        assert second_response.json()["response_id"] == "resp_followup_2"
    finally:
        runtime.shutdown()


def test_mock_provider_generates_offline_macro_card(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Map the active macro setup.",
                "context": {
                    "current_tab": "macro",
                    "macro": {
                        "mode": "snapshot",
                        "region": "US",
                        "timeframe": "3M",
                        "theme": "all",
                        "comparison_region": None,
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "mock"
        assert payload["model"] == "gamma-mock-research-card-v1"
        assert payload["response_id"].startswith("mock_macro_")
        assert payload["card"]["title"].startswith("Macro:")
        assert payload["card"]["source_backed_claims"][0]["evidence_refs"]
        assert any(trace["tool_name"] == "get_macro_workspace_drilldown" for trace in payload["tool_traces"])
        assert any(
            "local mock Copilot provider" in warning
            for warning in payload["warnings"]
        )
    finally:
        runtime.shutdown()


def test_mock_provider_generates_offline_synthesis_card(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
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
                "domain": "synthesis",
                "prompt": "Connect the loaded portfolio and macro context.",
                "context": {
                    "current_tab": "synthesis",
                    "workspace_mode": "research",
                },
                "synthesis": {
                    "active_tab": "macro",
                    "included_scopes": [
                        {
                            "domain": "portfolio",
                            "label": "Portfolio",
                            "context_fingerprint": "fp_portfolio_fixture",
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
                        {
                            "domain": "macro",
                            "label": "Macro",
                            "context_fingerprint": "fp_macro_fixture",
                            "context": {
                                "current_tab": "macro",
                                "workspace_mode": "research",
                                "macro": {
                                    "mode": "snapshot",
                                    "region": "US",
                                    "timeframe": "3M",
                                    "theme": "all",
                                    "comparison_region": None,
                                },
                            },
                        },
                    ],
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "mock"
        assert payload["model"] == "gamma-mock-research-card-v1"
        assert payload["response_id"].startswith("mock_synthesis_")
        assert payload["card"]["title"].startswith("Synthesis:")
        assert any(trace["tool_name"] == "get_synthesis_scope_summary" for trace in payload["tool_traces"])
        assert any(trace["tool_name"] == "get_synthesis_domain_context" for trace in payload["tool_traces"])
        assert any(source["source_id"] == "synthesis.scope" for source in payload["sources"])
    finally:
        runtime.shutdown()


def _crypto_token_fixture() -> CryptoTokenRecord:
    return CryptoTokenRecord(
        token_id="solana",
        symbol="sol",
        name="Solana",
        image_url=None,
        chain="Solana",
        asset_platform_id="solana",
        geckoterminal_network="solana",
        contract_address=None,
        market_cap_rank=6,
        current_price=150.0,
        market_cap=75_000_000_000.0,
        fully_diluted_valuation=90_000_000_000.0,
        total_volume=4_500_000_000.0,
        circulating_supply=500_000_000.0,
        total_supply=600_000_000.0,
        max_supply=None,
        price_change_pct_24h=4.2,
        price_change_pct_7d=10.5,
        price_change_pct_30d=18.2,
        market_cap_change_pct_24h=4.0,
        high_24h=155.0,
        low_24h=143.0,
        homepage_url="https://solana.com",
        description="High-throughput smart-contract network.",
        categories=["Layer 1"],
        turnover_ratio_24h=0.09,
        fdv_premium_ratio=0.2,
        screen_score=77.4,
        screen_rationale="turnover 0.09x | 24H volume $4.5B",
        source_provider="coingecko",
        retrieved_at=datetime(2026, 4, 5, 10, 0, 0),
        origin="coingecko.markets",
        transformation_note="Gamma screen score combines size, liquidity, turnover, momentum, and FDV premium heuristics.",
    )


def test_openai_provider_serializes_datetime_workspace_context():
    provider = OpenAIResponsesCopilotProvider(
        api_key="test-key",
        model="gpt-test",
        reasoning_effort="low",
    )
    request = CopilotResearchCardRequest(domain="synthesis")
    context = CopilotContextBundle(
        domain="synthesis",
        current_tab="synthesis",
        summary_data={
            "included_contexts": [
                {
                    "domain": "macro",
                    "freshness": "fresh",
                    "retrieved_at": datetime(2026, 4, 5, 10, 52, 0),
                }
            ]
        },
    )

    message = provider._build_user_message(request, context)
    payload = json.loads(message["content"][0]["text"])

    assert payload["workspace_context"]["included_contexts"][0]["retrieved_at"] == "2026-04-05T10:52:00"


def test_openai_provider_serializes_datetime_tool_outputs():
    rendered = OpenAIResponsesCopilotProvider._format_tool_output(
        {"retrieved_at": datetime(2026, 4, 5, 10, 52, 0)}
    )

    assert json.loads(rendered) == {"retrieved_at": "2026-04-05T10:52:00"}


def test_runtime_enables_openai_response_storage_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GAMMA_COPILOT_STORE_RESPONSES", "true")

    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        assert isinstance(runtime.copilot_service.provider, OpenAIResponsesCopilotProvider)
        assert runtime.copilot_service.provider.store_responses is True
    finally:
        runtime.shutdown()
