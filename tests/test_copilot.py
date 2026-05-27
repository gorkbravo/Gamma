from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.copilot_service import CopilotService
from src.application.runtime import build_runtime
from src.models.copilot import (
    CopilotContextBundle,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolExecution,
    CopilotToolTrace,
    ResearchCard,
    ResearchClaim,
)
from src.models.crypto import (
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoPricePoint,
    CryptoTokenRecord,
)
from src.models.fundamentals import (
    FundamentalsCompanyRecord,
    FundamentalsCoverageRecord,
    FundamentalsDcfModelRecord,
    FundamentalsDcfScenarioRecord,
    FundamentalsDcfSnapshotRecord,
    FundamentalsDcfValuationSummary,
    FundamentalsFilingRecord,
    FundamentalsFinancialsResult,
    FundamentalsMetricRecord,
    FundamentalsOverviewResult,
    FundamentalsPeerBasketRecord,
    FundamentalsPeerComparisonRecord,
    FundamentalsPeerDiagnosticsRecord,
    FundamentalsPeerHeatmapCell,
    FundamentalsPeerHeatmapMetricRow,
    FundamentalsPeerHeatmapView,
    FundamentalsPeersResult,
    FundamentalsPeriodRecord,
    FundamentalsRawNormalizedInspectionResult,
    FundamentalsReferenceResult,
    FundamentalsReverseValuationDriverRecord,
    FundamentalsReverseValuationResult,
    FundamentalsReverseValuationSensitivityCell,
    FundamentalsReverseValuationSensitivityMatrix,
    FundamentalsSourceTraceRecord,
    FundamentalsStatementCell,
    FundamentalsStatementLine,
    FundamentalsStatementView,
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
from src.services.copilot_store import CopilotStore


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

        if request.domain == "fundamentals":
            company_execution = execute_tool("get_fundamentals_company_context", {}, context)
            statement_execution = execute_tool("get_fundamentals_statement_context", {}, context)
            peer_execution = execute_tool("get_fundamentals_peer_context", {}, context)
            dcf_execution = execute_tool("get_fundamentals_dcf_context", {}, context)
            reverse_execution = execute_tool("get_fundamentals_reverse_valuation_context", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_fundamentals",
                card=ResearchCard(
                    title="Fundamentals test card",
                    hypothesis="The selected company should be framed through filings, normalized statements, peers, DCF, and implied expectations together.",
                    rationale="The Gamma fundamentals context exposes company facts, traceable statements, peer diagnostics, DCF summaries, and reverse valuation.",
                    required_data=["Company filings", "Peer comparison", "Reverse valuation"],
                    proposed_test="Compare market-implied growth and margin requirements against the base DCF and peer basket.",
                    confounders=["Sparse taxonomy coverage", "Market-data freshness"],
                    next_steps=["Inspect source trace", "Review implied expectations"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Fundamentals company, statement, peer, DCF, and reverse-valuation tools were available to the copilot.",
                            evidence_refs=[
                                company_execution.sources[0].source_id,
                                statement_execution.sources[0].source_id,
                                peer_execution.sources[0].source_id,
                                dcf_execution.sources[0].source_id,
                                reverse_execution.sources[0].source_id,
                            ],
                        )
                    ],
                    inferred_claims=["Company thesis quality still requires interpretation."],
                ),
                sources=[
                    *context.sources,
                    *company_execution.sources,
                    *statement_execution.sources,
                    *peer_execution.sources,
                    *dcf_execution.sources,
                    *reverse_execution.sources,
                ],
                tool_traces=[
                    company_execution.trace,
                    statement_execution.trace,
                    peer_execution.trace,
                    dcf_execution.trace,
                    reverse_execution.trace,
                ],
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


class _StubFundamentalsService:
    retrieved_at = datetime(2026, 4, 5, 10, 0, 0)

    def __init__(self) -> None:
        self.saved_payload: dict | None = None
        self.saved_snapshots: list[FundamentalsDcfSnapshotRecord] = []
        self.company = FundamentalsCompanyRecord(
            ticker="AAPL",
            cik="0000320193",
            name="Apple Inc.",
            exchange="NASDAQ",
            sic="3571",
            sic_description="Electronic Computers",
            latest_report_period=datetime(2025, 9, 27),
            latest_filing_date=datetime(2025, 10, 31),
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.company",
            transformation_note="Fixture company record for Fundamentals Copilot grounding.",
        )
        self.filing = FundamentalsFilingRecord(
            form="10-K",
            filing_date=datetime(2025, 10, 31),
            report_period=datetime(2025, 9, 27),
            accession_number="0000320193-25-000079",
            is_amendment=False,
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.filing",
            transformation_note="Fixture filing record for source-backed Copilot tests.",
        )
        self.period = FundamentalsPeriodRecord(
            period_key="FY-2025",
            label="FY 2025",
            fiscal_year=2025,
            fiscal_period="FY",
            filing_date=self.filing.filing_date,
            form=self.filing.form,
            accession_number=self.filing.accession_number,
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.period",
            transformation_note="Fixture fiscal period from SEC filing metadata.",
        )
        self.revenue_line = FundamentalsStatementLine(
            line_key="revenue",
            label="Revenue",
            statement="income",
            unit="usd",
            cells=[
                FundamentalsStatementCell(
                    period_key="FY-2025",
                    value=391_000_000_000.0,
                    display_value="$391.0B",
                    filing_date=self.filing.filing_date,
                    form=self.filing.form,
                    accession_number=self.filing.accession_number,
                    concept_name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                    source_provider="sec",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.statement_cell",
                    transformation_note="Normalized SEC revenue concept into Gamma statement row.",
                )
            ],
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.statement_line",
            transformation_note="Fixture normalized income statement line.",
        )

    def get_overview(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        return FundamentalsOverviewResult(
            company=self.company,
            headline_metrics=[
                FundamentalsMetricRecord(
                    metric_id="ev_to_sales",
                    label="EV / Sales",
                    value=7.2,
                    display_value="7.2x",
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.metric",
                    transformation_note="Fixture valuation metric combines price context and normalized SEC revenue.",
                )
            ],
            filings=[self.filing],
            peer_basket=self._peer_basket(),
            dcf_summary=[self._dcf_summary()],
            warnings=[],
        )

    def get_financials(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        income = FundamentalsStatementView(
            statement="income",
            basis="annual",
            periods=[self.period],
            lines=[self.revenue_line],
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.income",
            transformation_note="Fixture annual income statement normalized from SEC facts.",
        )
        empty = FundamentalsStatementView(
            statement="balance",
            basis="annual",
            periods=[self.period],
            lines=[],
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.empty_statement",
            transformation_note="Fixture statement shell for Copilot tests.",
        )
        ratios = FundamentalsStatementView(
            statement="ratios",
            basis="annual",
            periods=[self.period],
            lines=[],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.ratios",
            transformation_note="Fixture ratio statement derived by Gamma.",
        )
        return FundamentalsFinancialsResult(
            company=self.company,
            annual_income_statement=income,
            annual_balance_sheet=empty,
            annual_cash_flow_statement=empty,
            quarterly_income_statement=income,
            quarterly_balance_sheet=empty,
            quarterly_cash_flow_statement=empty,
            annual_ratio_view=ratios,
            quarterly_ratio_view=ratios,
            filings=[self.filing],
            warnings=[],
        )

    def get_peers(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        heatmap = FundamentalsPeerHeatmapView(
            tickers=["AAPL", "MSFT"],
            rows=[
                FundamentalsPeerHeatmapMetricRow(
                    metric_id="ev_to_sales",
                    label="EV / Sales",
                    family="valuation",
                    cells=[
                        FundamentalsPeerHeatmapCell(
                            ticker="AAPL",
                            value=7.2,
                            display_value="7.2x",
                            source_provider="gamma",
                            retrieved_at=self.retrieved_at,
                            origin="tests.copilot.fundamentals.peer_cell",
                            transformation_note="Fixture peer metric from normalized fundamentals and price context.",
                        )
                    ],
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.peer_row",
                    transformation_note="Fixture peer heatmap row.",
                )
            ],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.peer_heatmap",
            transformation_note="Fixture peer heatmap assembled by Gamma.",
        )
        return FundamentalsPeersResult(
            company=self.company,
            peer_basket=self._peer_basket(),
            peer_heatmap=heatmap,
            comparisons=[
                FundamentalsPeerComparisonRecord(
                    ticker="AAPL",
                    name="Apple Inc.",
                    selected=True,
                    candidate_reason="focal",
                    metrics=[
                        FundamentalsMetricRecord(
                            metric_id="implied_revenue_cagr",
                            label="Implied revenue CAGR",
                            value=0.07,
                            display_value="7.0%",
                            source_provider="gamma",
                            retrieved_at=self.retrieved_at,
                            origin="tests.copilot.fundamentals.peer_implied",
                            transformation_note="Fixture implied expectation comparison from reverse valuation.",
                        )
                    ],
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.peer_comparison",
                    transformation_note="Fixture peer comparison record.",
                )
            ],
            diagnostics=[
                FundamentalsPeerDiagnosticsRecord(
                    ticker="MSFT",
                    missing_metric_ids=["net_debt_to_ebit"],
                    warning="Some leverage metrics are missing in the fixture.",
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.peer_diagnostics",
                    transformation_note="Fixture peer missing-data diagnostic.",
                )
            ],
            warnings=[],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.peers",
            transformation_note="Fixture peer payload for Fundamentals Copilot tests.",
        )

    def get_dcf_model(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        if self.saved_payload is not None:
            return self._dcf_model_from_payload(self.saved_payload)
        return self._dcf_model_from_payload(
            {
                "ticker": "AAPL",
                "active_scenario_id": "base",
                "projection_years": [2026, 2027, 2028],
                "scenarios": {
                    "base": {
                        "assumptions": {
                            "revenue_growth_pct": [0.05, 0.05, 0.04],
                            "wacc_pct": 0.10,
                        },
                        "overrides": {},
                    }
                },
            }
        )

    def preview_dcf_model(self, ticker: str, payload: dict, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        return self._dcf_model_from_payload(payload)

    def save_dcf_model(self, ticker: str, payload: dict, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        self.saved_payload = deepcopy(payload)
        return self._dcf_model_from_payload(self.saved_payload)

    def save_dcf_snapshot(self, ticker: str, *, name: str | None = None, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        snapshot = FundamentalsDcfSnapshotRecord(
            snapshot_id=f"fixture-snapshot-{len(self.saved_snapshots) + 1}",
            ticker="AAPL",
            name=name or "Fixture snapshot",
            created_at=self.retrieved_at,
            active_scenario_id="base",
            projection_years=[2026, 2027, 2028],
            scenario_summaries=[self._dcf_summary()],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.saved_snapshot",
            transformation_note="Fixture DCF snapshot saved before applying a Copilot mutation.",
        )
        self.saved_snapshots.append(snapshot)
        return snapshot

    def _dcf_model_from_payload(self, payload: dict):
        scenario_payload = dict(payload.get("scenarios", {})).get("base", {})
        assumptions = dict(scenario_payload.get("assumptions", {}))
        overrides = dict(scenario_payload.get("overrides", {}))
        growth = assumptions.get("revenue_growth_pct", [0.05, 0.05, 0.04])
        growth_level = growth[0] if isinstance(growth, list) and growth else 0.05
        wacc = float(assumptions.get("wacc_pct", 0.10) or 0.10)
        implied_value = 182.13 + ((float(growth_level) - 0.05) * 400.0) - ((wacc - 0.10) * 500.0)
        return FundamentalsDcfModelRecord(
            ticker="AAPL",
            company_name="Apple Inc.",
            active_scenario_id=str(payload.get("active_scenario_id") or "base"),
            projection_years=list(payload.get("projection_years") or [2026, 2027, 2028]),
            scenarios=[
                FundamentalsDcfScenarioRecord(
                    scenario_id="base",
                    label="Base",
                    assumptions=assumptions,
                    overrides=overrides,
                    summary=FundamentalsDcfValuationSummary(
                        scenario_id="base",
                        label="Base",
                        enterprise_value=2_860_000_000_000.0 + ((implied_value - 182.13) * 10_000_000_000.0),
                        equity_value=2_823_000_000_000.0,
                        implied_value_per_share=implied_value,
                        upside_downside_pct=(implied_value / 190.0) - 1.0,
                        current_price=190.0,
                        source_provider="gamma",
                        retrieved_at=self.retrieved_at,
                        origin="tests.copilot.fundamentals.dcf_summary",
                        transformation_note="Fixture DCF summary derived from normalized statements and price context.",
                    ),
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.dcf_scenario",
                    transformation_note="Fixture Base DCF scenario.",
                )
            ],
            warnings=[],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.dcf",
            transformation_note="Fixture DCF model derived from normalized SEC statements.",
        )

    def list_dcf_snapshots(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return []
        return [
            *self.saved_snapshots,
            FundamentalsDcfSnapshotRecord(
                snapshot_id="fixture-base",
                ticker="AAPL",
                name="Base checkpoint",
                created_at=self.retrieved_at,
                active_scenario_id="base",
                projection_years=[2026, 2027, 2028],
                scenario_summaries=[self._dcf_summary()],
                source_provider="gamma",
                retrieved_at=self.retrieved_at,
                origin="tests.copilot.fundamentals.dcf_snapshot",
                transformation_note="Fixture saved DCF snapshot for Copilot grounding.",
            )
        ]

    def get_reverse_valuation(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        return FundamentalsReverseValuationResult(
            company=self.company,
            current_price=190.0,
            shares_outstanding=15_500_000_000.0,
            net_debt=37_000_000_000.0,
            target_equity_value=2_945_000_000_000.0,
            target_enterprise_value=2_982_000_000_000.0,
            base_case_summary=self._dcf_summary(),
            scenario_gap_metrics=[
                FundamentalsMetricRecord(
                    metric_id="base_gap",
                    label="Base gap",
                    value=0.04,
                    display_value="+4.0%",
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.reverse_gap",
                    transformation_note="Fixture gap between market EV and Base DCF enterprise value.",
                )
            ],
            drivers=[
                FundamentalsReverseValuationDriverRecord(
                    driver_id="implied_revenue_cagr",
                    label="Implied revenue CAGR",
                    implied_value=0.07,
                    display_value="7.0%",
                    base_value=0.05,
                    base_display_value="5.0%",
                    gap_to_base=0.02,
                    gap_display_value="+2.0 pts",
                    target_enterprise_value=2_982_000_000_000.0,
                    solved_enterprise_value=2_982_000_000_000.0,
                    success=True,
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.reverse_driver",
                    transformation_note="Fixture reverse valuation driver solved by Gamma.",
                )
            ],
            sensitivity_matrix=FundamentalsReverseValuationSensitivityMatrix(
                wacc_values=[0.08],
                terminal_growth_values=[0.025],
                rows=[
                    [
                        FundamentalsReverseValuationSensitivityCell(
                            wacc_pct=0.08,
                            terminal_growth_pct=0.025,
                            implied_revenue_growth_pct=0.07,
                            implied_ebit_margin_pct=0.32,
                            implied_fcf_cagr_pct=0.06,
                            source_provider="gamma",
                            retrieved_at=self.retrieved_at,
                            origin="tests.copilot.fundamentals.reverse_sensitivity",
                            transformation_note="Fixture reverse-valuation sensitivity cell.",
                        )
                    ]
                ],
                source_provider="gamma",
                retrieved_at=self.retrieved_at,
                origin="tests.copilot.fundamentals.reverse_matrix",
                transformation_note="Fixture WACC and terminal-growth reverse-valuation sensitivity.",
            ),
            warnings=[],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.reverse",
            transformation_note="Fixture reverse valuation result for Copilot grounding.",
        )

    def get_reference(self, ticker: str, *, force_refresh: bool = False):
        del force_refresh
        if ticker.upper() != "AAPL":
            return None
        inspection = FundamentalsRawNormalizedInspectionResult(
            company=self.company,
            traces=[
                FundamentalsSourceTraceRecord(
                    statement="income",
                    basis="annual",
                    line_key="revenue",
                    line_label="Revenue",
                    period_key="FY-2025",
                    period_label="FY 2025",
                    normalized_value=391_000_000_000.0,
                    display_value="$391.0B",
                    unit="usd",
                    concept_name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                    accession_number=self.filing.accession_number,
                    filing_form=self.filing.form,
                    fiscal_year=2025,
                    fiscal_period="FY",
                    filing_date=self.filing.filing_date,
                    report_period=self.filing.report_period,
                    is_amendment=False,
                    source_provider="sec",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.source_trace",
                    transformation_note="Fixture raw-versus-normalized source trace.",
                )
            ],
            coverage=[
                FundamentalsCoverageRecord(
                    statement="income",
                    basis="annual",
                    line_key="revenue",
                    line_label="Revenue",
                    concept_names=["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"],
                    observed_periods=1,
                    missing_periods=0,
                    derived_observations=0,
                    coverage_ratio=1.0,
                    source_provider="gamma",
                    retrieved_at=self.retrieved_at,
                    origin="tests.copilot.fundamentals.coverage",
                    transformation_note="Fixture taxonomy coverage record.",
                )
            ],
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.inspection",
            transformation_note="Fixture inspection payload comparing normalized rows against source concepts.",
        )
        return FundamentalsReferenceResult(
            company=self.company,
            filings=[self.filing],
            inspection=inspection,
            provider_warnings=[],
            warnings=[],
            source_provider="sec",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.reference",
            transformation_note="Fixture reference payload for filings and source trace.",
        )

    def _peer_basket(self) -> FundamentalsPeerBasketRecord:
        return FundamentalsPeerBasketRecord(
            focal_ticker="AAPL",
            basket_label="Technology hardware peers",
            peer_tickers=["MSFT"],
            display_order=["AAPL", "MSFT"],
            user_edited=True,
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.peer_basket",
            transformation_note="Fixture persistent peer basket.",
        )

    def _dcf_summary(self) -> FundamentalsDcfValuationSummary:
        return FundamentalsDcfValuationSummary(
            scenario_id="base",
            label="Base",
            enterprise_value=2_860_000_000_000.0,
            equity_value=2_823_000_000_000.0,
            implied_value_per_share=182.13,
            upside_downside_pct=-0.04,
            current_price=190.0,
            source_provider="gamma",
            retrieved_at=self.retrieved_at,
            origin="tests.copilot.fundamentals.dcf_summary",
            transformation_note="Fixture DCF summary derived from normalized statements and price context.",
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


def test_copilot_persists_sessions_turns_and_memos(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Persist this macro session.",
                "user_session_id": "session_test_persist",
                "context_fingerprint": "fp_macro_persist",
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
        )
        assert response.status_code == 200

        sessions = client.get("/copilot/sessions")
        assert sessions.status_code == 200
        assert any(item["session_id"] == "session_test_persist" for item in sessions.json())

        detail = client.get("/copilot/sessions/session_test_persist")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["session"]["turn_count"] == 1
        assert payload["turns"][0]["context_snapshot_id"].startswith("ctx_")
        assert payload["turns"][0]["result"]["card"]["title"] == "Macro test card"

        memo_response = client.post(
            "/copilot/memos",
            json={"session_id": "session_test_persist", "title": "Macro Memo"},
        )
        assert memo_response.status_code == 200
        memo = memo_response.json()
        assert memo["title"] == "Macro Memo"
        assert "Hypothesis:" in memo["body"]
        assert memo["source_turn_ids"] == [payload["turns"][0]["turn_id"]]

        update_response = client.patch(
            f"/copilot/memos/{memo['memo_id']}",
            json={"title": "Edited Macro Memo", "body": "# Edited Macro Memo\n\nSourced claim retained."},
        )
        assert update_response.status_code == 200
        edited_memo = update_response.json()
        assert edited_memo["title"] == "Edited Macro Memo"
        assert "Sourced claim retained." in edited_memo["body"]

        export_response = client.get(f"/copilot/memos/{memo['memo_id']}/export")
        assert export_response.status_code == 200
        assert "Source turns:" in export_response.text
        assert payload["turns"][0]["turn_id"] in export_response.text

        filtered_sessions = client.get("/copilot/sessions", params={"search": "macro"})
        assert filtered_sessions.status_code == 200
        assert any(item["session_id"] == "session_test_persist" for item in filtered_sessions.json())

        archive_response = client.post("/copilot/sessions/session_test_persist/archive")
        assert archive_response.status_code == 200
        assert archive_response.json()["archived_at"] is not None

        active_sessions = client.get("/copilot/sessions")
        assert all(item["session_id"] != "session_test_persist" for item in active_sessions.json())

        archived_sessions = client.get("/copilot/sessions", params={"include_archived": "true", "search": "macro"})
        assert any(item["session_id"] == "session_test_persist" for item in archived_sessions.json())
    finally:
        runtime.shutdown()


def test_copilot_generates_research_report_and_markdown_snapshot(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Build a report-ready macro trace.",
                "user_session_id": "session_report_test",
                "context_fingerprint": "fp_macro_report",
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
        )
        assert response.status_code == 200
        detail = client.get("/copilot/sessions/session_report_test").json()
        turn_id = detail["turns"][0]["turn_id"]

        memo_response = client.post(
            "/copilot/memos",
            json={"session_id": "session_report_test", "title": "Macro Report Memo"},
        )
        assert memo_response.status_code == 200
        memo_id = memo_response.json()["memo_id"]

        report_request = {
            "title": "Macro Research Report",
            "notes": "Treat this as a report snapshot test.",
            "source_turn_ids": [turn_id],
            "source_memo_ids": [memo_id],
        }
        report_response = client.post("/copilot/sessions/session_report_test/report", json=report_request)
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["title"] == "Macro Research Report"
        assert report["source_turn_ids"] == [turn_id]
        assert report["source_memo_ids"] == [memo_id]
        assert report["source_backed_claims"][0]["evidence_refs"]
        assert any(item.startswith("macro: Inflation remains") for item in report["inferred_claims"])
        assert "User note: Treat this as a report snapshot test." in report["assumptions"]
        assert report["missing_data"] == [
            "No explicit missing-data warnings were recorded in the selected session trace."
        ]
        assert any(
            row["tool_name"] == "get_macro_series_history_summary"
            for row in report["tool_trace_summary"]
        )

        export_response = client.post("/copilot/sessions/session_report_test/report/export", json=report_request)
        assert export_response.status_code == 200
        markdown = re.sub(r"report_[a-f0-9]+", "report_TEST", export_response.text)
        markdown = re.sub(r"turn_[a-f0-9]+", "turn_TEST", markdown)
        markdown = re.sub(r"memo_[a-f0-9]+", "memo_TEST", markdown)
        assert "## Source-Backed Claims" in markdown
        assert "- The macro workspace context was available to the copilot." in markdown
        assert "## Inferred Claims\n- macro: Inflation remains the dominant macro swing factor." in markdown
        assert "## Missing Data\n- No explicit missing-data warnings were recorded in the selected session trace." in markdown
        assert "- `get_macro_series_history_summary`: Loaded" in markdown
        assert "- `macro.snapshot`: Macro snapshot" in markdown
        assert "Source provider: gamma_copilot" in markdown
    finally:
        runtime.shutdown()


def test_copilot_stream_endpoint_emits_ndjson_events(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card/stream",
            json={
                "domain": "macro",
                "prompt": "Stream the macro card.",
                "user_session_id": "session_test_stream",
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
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert [event["event"] for event in events] == ["status", "metadata", "result", "done"]
        assert events[2]["data"]["card"]["title"] == "Macro test card"
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


def test_copilot_route_returns_structured_error_when_provider_raises(tmp_path):
    class RaisingProvider:
        provider_name = "raising_provider"

        def generate_research_card(self, *, request, context, tool_specs, execute_tool):
            del request, context, tool_specs, execute_tool
            raise RuntimeError("provider transport failed")

    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.provider = RaisingProvider()
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
        assert payload["status"] == "error"
        assert payload["provider"] == "raising_provider"
        assert "provider transport failed" in payload["message"]
        assert payload["sources"]
        assert any("failed before a research card" in warning for warning in payload["warnings"])
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


def test_fundamentals_copilot_route_uses_fundamentals_tool_context(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "fundamentals",
                "prompt": "Frame the active company setup.",
                "context": {
                    "current_tab": "fundamentals",
                    "workspace_mode": "research",
                    "fundamentals_ticker": "AAPL",
                    "fundamentals_state": {
                        "ticker": "AAPL",
                        "active_scenario_id": "base",
                        "peer_tickers": ["MSFT"],
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["card"]["title"] == "Fundamentals test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {
            "get_fundamentals_company_context",
            "get_fundamentals_statement_context",
            "get_fundamentals_peer_context",
            "get_fundamentals_dcf_context",
            "get_fundamentals_reverse_valuation_context",
        }
        assert any(source["source_id"] == "fundamentals.company" for source in payload["sources"])
        assert any(source["source_id"] == "fundamentals.reference" for source in payload["sources"])
        assert any(source["source_id"] == "fundamentals.reverse_valuation.drilldown" for source in payload["sources"])
        assert payload["card"]["source_backed_claims"][0]["evidence_refs"]
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


def test_mock_provider_generates_offline_fundamentals_card(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "fundamentals",
                "prompt": "Frame the active company setup.",
                "context": {
                    "current_tab": "fundamentals",
                    "workspace_mode": "research",
                    "fundamentals_ticker": "AAPL",
                    "fundamentals_state": {
                        "ticker": "AAPL",
                        "active_scenario_id": "base",
                        "peer_tickers": ["MSFT"],
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "mock"
        assert payload["response_id"].startswith("mock_fundamentals_")
        assert payload["card"]["title"].startswith("Fundamentals:")
        assert "read-only fundamentals" in payload["card"]["rationale"]
        tool_names = {trace["tool_name"] for trace in payload["tool_traces"]}
        assert tool_names == {
            "get_fundamentals_company_context",
            "get_fundamentals_statement_context",
            "get_fundamentals_peer_context",
            "get_fundamentals_dcf_context",
            "get_fundamentals_reverse_valuation_context",
        }
        assert any(source["source_id"] == "fundamentals.company" for source in payload["sources"])
        assert any(source["source_id"] == "fundamentals.reverse_valuation.drilldown" for source in payload["sources"])
        assert payload["card"]["source_backed_claims"][0]["evidence_refs"]
        assert any("local mock Copilot provider" in warning for warning in payload["warnings"])
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


def test_copilot_research_plan_single_company_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Research NVDA",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "single_company_research"
        assert payload["depth_profile"] == "standard"
        assert payload["target_entities"][0]["kind"] == "ticker"
        assert payload["target_entities"][0]["id"] == "NVDA"
        assert [item["domain"] for item in payload["domain_plan"][:3]] == [
            "fundamentals",
            "equity_research",
            "iv",
        ]
        assert payload["domain_plan"][0]["depth"] == "deep"
        assert payload["requires_confirmation"] is False
        assert "research_memo" in payload["expected_artifacts"]
    finally:
        runtime.shutdown()


def test_copilot_research_plan_event_company_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Research NVDA into CPI/Fed week",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "single_company_event_research"
        domain_depths = {item["domain"]: item["depth"] for item in payload["domain_plan"]}
        assert domain_depths["macro"] == "deep"
        assert domain_depths["iv"] == "deep"
        assert domain_depths["fundamentals"] == "medium"
    finally:
        runtime.shutdown()


def test_copilot_research_plan_oil_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "What is going on in oil?",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "commodity_macro_research"
        assert payload["target_entities"][0]["kind"] == "commodity"
        assert payload["target_entities"][0]["id"] == "oil"
        assert [item["domain"] for item in payload["domain_plan"][:3]] == [
            "commodities",
            "macro",
            "prediction_markets",
        ]
    finally:
        runtime.shutdown()


def test_copilot_research_plan_portfolio_rate_shock_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "context": {"current_tab": "portfolio", "workspace_mode": "portfolio"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "portfolio_rate_shock_research"
        domain_depths = {item["domain"]: item["depth"] for item in payload["domain_plan"]}
        assert domain_depths["portfolio"] == "deep"
        assert domain_depths["risk"] == "deep"
        assert domain_depths["macro"] == "deep"
        assert "fundamentals" not in domain_depths
    finally:
        runtime.shutdown()


def test_copilot_research_plan_phase3_depth_budget_and_domain_decisions(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Quick research NVDA",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["depth_profile"] == "quick"
        assert payload["max_tool_calls"] == 3
        assert payload["max_provider_calls"] == 0
        assert len(payload["domain_plan"]) <= 3
        assert all(item["depth"] == "light" for item in payload["domain_plan"])
        assert all(item["estimated_tool_calls"] >= 0 for item in payload["domain_plan"])
        assert all(item["estimated_latency_ms"] > 0 for item in payload["domain_plan"])
        assert any(
            decision["domain"] == "fundamentals" and decision["used"]
            for decision in payload["domain_decisions"]
        )
        assert any(
            decision["domain"] == "portfolio" and not decision["used"]
            for decision in payload["domain_decisions"]
        )
    finally:
        runtime.shutdown()


def test_copilot_research_plan_user_directed_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Use only macro and risk for this question",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["depth_profile"] == "user_directed"
        assert [item["domain"] for item in payload["domain_plan"]] == ["risk", "macro"]
        assert payload["max_tool_calls"] == 10
        assert any(
            decision["domain"] == "fundamentals" and not decision["used"]
            for decision in payload["domain_decisions"]
        )
    finally:
        runtime.shutdown()


def test_copilot_action_registry_marks_existing_tools_read_only(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        del client
        definitions = runtime.copilot_service.list_research_action_definitions()
        assert definitions
        automatic_tools = [
            definition
            for definition in definitions
            if definition.action_type in {"read_context", "run_analysis", "fetch_external_context"}
        ]
        assert all(definition.read_only for definition in automatic_tools)
        assert not any(definition.mutates_local_state for definition in automatic_tools)
        portfolio_tools = {
            definition.tool_id: definition
            for definition in definitions
            if "portfolio" in definition.domains
        }
        assert portfolio_tools["get_portfolio_positions_summary"].action_type == "read_context"
        assert portfolio_tools["get_portfolio_positions_summary"].requires_confirmation is False
        mutation_tools = {definition.tool_id: definition for definition in definitions}
        assert mutation_tools["fundamentals.propose_dcf_update"].action_type == "draft_change"
        assert mutation_tools["fundamentals.propose_dcf_update"].mutates_local_state is False
        assert mutation_tools["fundamentals.apply_dcf_update"].action_type == "apply_change"
        assert mutation_tools["fundamentals.apply_dcf_update"].mutates_local_state is True
        assert mutation_tools["fundamentals.apply_dcf_update"].requires_confirmation is True
    finally:
        runtime.shutdown()


def test_copilot_actions_route_exposes_operator_contract_metadata(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.get("/copilot/actions")

        assert response.status_code == 200
        payload = response.json()
        by_id = {item["tool_id"]: item for item in payload}
        assert by_id["get_portfolio_positions_summary"]["permission_policy"] == "automatic"
        assert by_id["get_external_context_summary"]["can_call_external_providers"] is True
        assert by_id["fundamentals.propose_dcf_update"]["permission_policy"] == "automatic_draft"
        assert by_id["fundamentals.apply_dcf_update"]["permission_policy"] == "confirmation_required"
        assert by_id["fundamentals.apply_dcf_update"]["retry_policy"] == "not_retry_safe_after_success"
        assert by_id["fundamentals.apply_dcf_update"]["test_coverage_owner"] == "tests/test_copilot.py"
    finally:
        runtime.shutdown()


def test_copilot_operator_plan_returns_ordered_steps_for_rate_shock(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "context": {"current_tab": "portfolio", "workspace_mode": "portfolio"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["role"] == "research_operator"
        assert payload["intent"] == "portfolio_rate_shock_research"
        assert payload["requires_confirmation"] is False
        assert "operator_trace" in payload["expected_artifacts"]
        assert payload["steps"]
        assert [step["order"] for step in payload["steps"]] == list(range(1, len(payload["steps"]) + 1))
        assert any(step["tool_id"] == "get_portfolio_positions_summary" for step in payload["steps"])
        assert any(step["domain"] == "risk" for step in payload["steps"])
        assert all(step["permission_policy"] == "automatic" for step in payload["steps"])
        assert payload["research_plan"]["intent"] == "portfolio_rate_shock_research"
    finally:
        runtime.shutdown()


def test_copilot_operator_plan_adds_dcf_confirmation_checkpoint(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL and adjust the DCF revenue growth assumption",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "single_company_research"
        assert payload["requires_confirmation"] is True
        draft_step = next(
            step
            for step in payload["steps"]
            if step["tool_id"] == "fundamentals.propose_dcf_update"
        )
        assert draft_step["action_type"] == "draft_change"
        assert draft_step["permission_policy"] == "automatic_draft"
        assert "confirmation_token" in draft_step["expected_artifacts"]
        assert payload["confirmation_checkpoints"] == [
            {
                "checkpoint_id": "checkpoint_dcf_apply",
                "after_step_id": draft_step["step_id"],
                "reason": "Applying a DCF update mutates durable local Fundamentals research state.",
                "required_for_tool_ids": ["fundamentals.apply_dcf_update"],
                "default_policy": "confirmation_required",
            }
        ]
        assert "confirmation_checkpoint" in payload["expected_artifacts"]
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_read_only_risk_analysis(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()

        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {"snapshot": snapshot},
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "gamma_operator_executor"
        assert payload["card"]["title"].startswith("Executed Research Operator Plan")
        assert any(
            trace["tool_name"] == "run_risk_scenario_analysis"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "risk.scenario.analysis"
            for source in payload["sources"]
        )
        event_types = [event["event_type"] for event in payload["operator_events"]]
        assert event_types[0] == "plan"
        assert "step-start" in event_types
        assert "tool-result" in event_types
        assert "artifact-created" in event_types
        assert event_types[-1] == "final-report"
        assert payload["operator_events"][-1]["payload"]["status"] == "ready"
        sessions = client.get("/copilot/sessions").json()
        assert sessions and sessions[0]["turn_count"] == 1
        detail = client.get(f"/copilot/sessions/{sessions[0]['session_id']}").json()
        persisted_events = detail["turns"][0]["result"]["operator_events"]
        assert persisted_events
        assert [event["sequence"] for event in persisted_events] == list(range(1, len(persisted_events) + 1))
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_reverse_valuation_analysis(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()

        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL and run reverse valuation",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(
            trace["tool_name"] == "run_fundamentals_reverse_valuation"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "fundamentals.reverse_valuation.analysis"
            for source in payload["sources"]
        )
        assert not any("confirmation" in warning.lower() for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_stops_before_confirmed_dcf_apply(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()

        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL and adjust the DCF revenue growth assumption",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert not any(
            trace["tool_name"] == "fundamentals.apply_dcf_update"
            for trace in payload["tool_traces"]
        )
        assert any(
            "confirmation checkpoints" in warning
            for warning in payload["warnings"]
        )
        assert any(
            event["event_type"] == "confirmation-needed"
            and "fundamentals.apply_dcf_update" in event["payload"]["required_for_tool_ids"]
            for event in payload["operator_events"]
        )
    finally:
        runtime.shutdown()


def test_copilot_confirmed_dcf_mutation_propose_and_apply_flow(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        fundamentals_service = _StubFundamentalsService()
        runtime.copilot_service.fundamentals_service = fundamentals_service
        current = fundamentals_service.get_dcf_model("AAPL")
        projection_count = len(current.projection_years)

        proposal = client.post(
            "/copilot/mutations/fundamentals/dcf/propose",
            json={
                "ticker": "AAPL",
                "scenario_id": "base",
                "active_scenario_id": "base",
                "assumptions": {
                    "revenue_growth": 0.11,
                    "wacc": 0.09,
                },
                "rationale": "Test a higher growth and lower discount-rate case.",
            },
        )

        assert proposal.status_code == 200
        draft = proposal.json()
        assert draft["status"] == "pending"
        assert draft["requires_confirmation"] is True
        assert draft["confirmation_token"].startswith("confirm_")
        assert any(item["path"] == "scenarios.base.assumptions.revenue_growth_pct" for item in draft["diff"])
        assert any("Revenue Growth" in line for line in draft["rendered_diff"])
        assert draft["proposed_payload"]["scenarios"]["base"]["assumptions"]["revenue_growth_pct"] == [0.11] * projection_count

        rejected = client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={"confirmation_token": "wrong-token"},
        )
        assert rejected.status_code == 400

        applied = client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={"confirmation_token": draft["confirmation_token"]},
        )

        assert applied.status_code == 200
        payload = applied.json()
        assert payload["mutation"]["status"] == "applied"
        assert payload["mutation"]["tool_id"] == "fundamentals.apply_dcf_update"
        assert payload["mutation"]["rollback_snapshot_id"]
        assert payload["artifact"]["rollback_snapshot_id"] == payload["mutation"]["rollback_snapshot_id"]
        assert any("snapshot was saved" in warning for warning in payload["warnings"])

        saved = fundamentals_service.get_dcf_model("AAPL")
        base = next(scenario for scenario in saved.scenarios if scenario.scenario_id == "base")
        assert base.assumptions["revenue_growth_pct"] == [0.11] * projection_count
        assert base.assumptions["wacc_pct"] == 0.09
        assert any(
            snapshot.snapshot_id == payload["mutation"]["rollback_snapshot_id"]
            for snapshot in fundamentals_service.list_dcf_snapshots("AAPL")
        )
    finally:
        runtime.shutdown()


def test_copilot_plan_execution_applies_quick_profile_budget(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        history = client.get("/portfolio/history").json()
        performance = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 30,
            },
        ).json()

        response = client.post(
            "/copilot/research-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Quick: is my portfolio exposed to rate shock?",
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
        assert len(payload["tool_traces"]) <= 3
        assert any("bounded to 2 domains" in warning for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_plan_execution_runs_read_only_tools_and_persists_trace(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        history = client.get("/portfolio/history").json()
        performance = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 30,
            },
        ).json()

        response = client.post(
            "/copilot/research-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
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
        assert payload["provider"] == "gamma_executor"
        assert payload["card"]["title"].startswith("Executed Research Plan")
        assert any(
            trace["tool_name"] == "get_portfolio_positions_summary"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "portfolio.snapshot.drilldown"
            for source in payload["sources"]
        )
        assert any(
            trace["tool_name"] == "run_risk_scenario_analysis"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "risk.scenario.analysis"
            for source in payload["sources"]
        )

        sessions = client.get("/copilot/sessions").json()
        assert sessions and sessions[0]["turn_count"] == 1
        turns = client.get(f"/copilot/sessions/{sessions[0]['session_id']}").json()["turns"]
        assert any(
            trace["tool_name"] == "get_portfolio_positions_summary"
            for trace in turns[0]["result"]["tool_traces"]
        )
    finally:
        runtime.shutdown()


def test_copilot_plan_execution_uses_planned_ticker_for_fundamentals(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()

        response = client.post(
            "/copilot/research-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(
            trace["tool_name"] == "get_fundamentals_company_context"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "fundamentals.company"
            for source in payload["sources"]
        )
        assert not any("Skipped fundamentals" in warning for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_planner_does_not_treat_relevant_gamma_domains_as_user_directed(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": "Research NVDA into CPI/Fed week. Use the relevant Gamma domains.",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "single_company_event_research"
        assert payload["depth_profile"] == "standard"
        planned_domains = [item["domain"] for item in payload["domain_plan"]]
        assert planned_domains[:3] == ["fundamentals", "macro", "iv"]
        assert "external_context" in planned_domains
    finally:
        runtime.shutdown()


def test_copilot_external_context_tool_fetches_news_and_unavailable_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    client, runtime = _build_test_client(tmp_path)
    try:
        del client
        request = CopilotResearchCardRequest(
            domain="external_context",
            prompt="Use only news for oil and Fed policy context",
            context=CopilotRequestContext(current_tab="external_context", workspace_mode="research"),
        )
        context = runtime.copilot_service._build_plan_execution_context(request, "external_context")
        execution = runtime.copilot_service._execute_tool("get_external_context_summary", {}, context)

        assert execution.trace.tool_name == "get_external_context_summary"
        assert execution.output["news"]["freshness_label"] == "mocked"
        assert execution.output["news"]["items"]
        assert any(
            boundary["provider"] == "analyst_estimates" and boundary["status"] == "unavailable"
            for boundary in execution.output["provider_boundaries"]
        )
        assert any(
            boundary["provider"] == "transcripts" and boundary["freshness_label"] == "unavailable"
            for boundary in execution.output["provider_boundaries"]
        )
        assert any(source.source_id == "external_context.news_feed" for source in execution.sources)
    finally:
        runtime.shutdown()


def test_copilot_external_context_requires_specific_match_for_company_news(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    client, runtime = _build_test_client(tmp_path)
    try:
        del client
        request = CopilotResearchCardRequest(
            domain="external_context",
            prompt="Research AAPL latest news",
            context=CopilotRequestContext(current_tab="external_context", workspace_mode="research"),
        )
        context = runtime.copilot_service._build_plan_execution_context(request, "external_context")
        execution = runtime.copilot_service._execute_tool("get_external_context_summary", {}, context)

        assert execution.trace.tool_name == "get_external_context_summary"
        assert execution.output["news"]["items"] == []
        assert any(
            "No news/event items matched" in warning
            for warning in execution.output["warnings"]
        )
        assert not any(source.kind == "news_item" for source in execution.sources)
    finally:
        runtime.shutdown()


def test_copilot_plan_execution_runs_external_context_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Use only news for oil",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(
            trace["tool_name"] == "get_external_context_summary"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "external_context.news_feed"
            and source["provider"] == "sample_news"
            for source in payload["sources"]
        )
        assert any(
            "Skipped commodities" in warning
            for warning in payload["warnings"]
        )
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


def test_copilot_store_persists_sources_with_serialized_timestamps(tmp_path):
    store = CopilotStore(tmp_path / "copilot")
    result = CopilotResearchCardResult(
        domain="synthesis",
        current_tab="copilot",
        status="ready",
        provider="stub",
        model="stub-model",
        response_id="resp_test",
        card=ResearchCard(
            title="Synthesis test",
            hypothesis="H",
            rationale="R",
            required_data=[],
            proposed_test="T",
            confounders=[],
            next_steps=[],
            caveats=[],
            source_backed_claims=[],
            inferred_claims=[],
        ),
        sources=[
            CopilotSourceRef(
                source_id="synthesis.scope",
                label="Synthesis scope",
                kind="workspace",
                provider="gamma",
                origin="gamma.copilot.synthesis",
                retrieved_at="2026-04-30T08:12:22",
            )
        ],
    )

    session, _snapshot, turn = store.record_turn(
        session_id=None,
        title=None,
        domain="synthesis",
        current_tab="copilot",
        workspace_mode="research",
        prompt="Connect these contexts.",
        context_fingerprint="fp_test",
        context_summary={"scope_size": 2},
        result=result,
    )

    turns = store.list_turns(session.session_id)
    assert [item.turn_id for item in turns] == [turn.turn_id]
    assert turns[0].result.sources[0].retrieved_at == datetime(2026, 4, 30, 8, 12, 22)


def test_copilot_service_normalizes_result_source_timestamps():
    result = CopilotResearchCardResult(
        domain="synthesis",
        current_tab="copilot",
        status="ready",
        provider="stub",
        sources=[
            CopilotSourceRef(
                source_id="synthesis.scope",
                label="Synthesis scope",
                kind="workspace",
                provider="gamma",
                origin="gamma.copilot.synthesis",
                retrieved_at="2026-04-30T08:12:22Z",
            )
        ],
    )

    normalized = CopilotService._normalize_result_sources(result)

    assert normalized.sources[0].retrieved_at == datetime(2026, 4, 30, 8, 12, 22)


def test_openai_provider_omits_previous_response_id_when_response_storage_is_disabled():
    class CaptureOpenAIProvider(OpenAIResponsesCopilotProvider):
        def __init__(self):
            super().__init__(
                api_key="test-key",
                model="gpt-test",
                reasoning_effort="low",
                store_responses=False,
            )
            self.payloads: list[dict] = []

        def _post_json(self, payload):
            self.payloads.append(payload)
            return {
                "id": "resp_test",
                "model": "gpt-test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "title": "Test",
                                        "hypothesis": "H",
                                        "rationale": "R",
                                        "required_data": [],
                                        "proposed_test": "T",
                                        "confounders": [],
                                        "next_steps": [],
                                        "caveats": [],
                                        "source_backed_claims": [],
                                        "inferred_claims": [],
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }

    provider = CaptureOpenAIProvider()
    provider.generate_research_card(
        request=CopilotResearchCardRequest(domain="macro", previous_response_id="resp_previous"),
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        tool_specs=[],
        execute_tool=lambda *_args: None,
    )

    assert provider.payloads
    assert "previous_response_id" not in provider.payloads[0]


def test_openai_provider_omits_reasoning_items_when_response_storage_is_disabled():
    class CaptureOpenAIProvider(OpenAIResponsesCopilotProvider):
        def __init__(self):
            super().__init__(
                api_key="test-key",
                model="gpt-test",
                reasoning_effort="low",
                store_responses=False,
            )
            self.payloads: list[dict] = []

        def _post_json(self, payload):
            self.payloads.append(payload)
            if len(self.payloads) == 1:
                return {
                    "id": "resp_tool_round",
                    "model": "gpt-test",
                    "output": [
                        {
                            "type": "reasoning",
                            "id": "rs_not_persisted",
                            "summary": [],
                        },
                        {
                            "type": "function_call",
                            "id": "fc_not_persisted",
                            "call_id": "call_123",
                            "name": "get_macro_workspace_drilldown",
                            "arguments": "{}",
                        },
                    ],
                }
            return {
                "id": "resp_final",
                "model": "gpt-test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "title": "Test",
                                        "hypothesis": "H",
                                        "rationale": "R",
                                        "required_data": [],
                                        "proposed_test": "T",
                                        "confounders": [],
                                        "next_steps": [],
                                        "caveats": [],
                                        "source_backed_claims": [],
                                        "inferred_claims": [],
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }

    provider = CaptureOpenAIProvider()
    source = CopilotSourceRef(
        source_id="macro.drilldown",
        label="Macro drilldown",
        kind="workspace",
        provider="gamma",
        origin="gamma.macro",
    )

    def execute_tool(*_args):
        return CopilotToolExecution(
            output={"ok": True},
            trace=CopilotToolTrace(
                tool_name="get_macro_workspace_drilldown",
                summary="Expanded macro context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    result = provider.generate_research_card(
        request=CopilotResearchCardRequest(domain="macro"),
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        tool_specs=[],
        execute_tool=execute_tool,
    )

    assert result.status == "ready"
    assert len(provider.payloads) == 2
    second_input = provider.payloads[1]["input"]
    assert not any(item.get("type") == "reasoning" for item in second_input)
    function_call = next(item for item in second_input if item.get("type") == "function_call")
    assert function_call == {
        "type": "function_call",
        "call_id": "call_123",
        "name": "get_macro_workspace_drilldown",
        "arguments": "{}",
    }
    assert "id" not in function_call


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
