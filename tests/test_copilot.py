from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.application.copilot_agents_operator import CopilotAgentsOperatorService
from src.application.copilot_context_contracts import (
    COPILOT_SCOPE_CONTEXT_BUDGET_BYTES,
    COPILOT_TOTAL_CONTEXT_BUDGET_BYTES,
    finalize_context_bundle,
)
from src.application.research_action_registry import (
    ResearchActionPermissionError,
    ResearchActionRegistry,
    ResearchActionRegistryError,
)
from src.api.main import create_app
from src.application.copilot_service import CopilotService
from src.application.runtime import build_runtime
from src.models.copilot import (
    CopilotContextBundle,
    CopilotArtifactReference,
    CopilotConfirmationState,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotResearchActionDefinition,
    CopilotResearchPlan,
    CopilotResearchPlanDomain,
    CopilotResearchPlanDomainDecision,
    CopilotRunEvent,
    CopilotSourceRef,
    CopilotToolExecution,
    CopilotToolTrace,
    CopilotUsageRecord,
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
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.services.mock_copilot_provider import MockCopilotProvider
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
from src.services.copilot_store import (
    CURRENT_COPILOT_STORE_SCHEMA_VERSION,
    CopilotStore,
    CopilotStoreConflictError,
    CopilotStoreNotFoundError,
)


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

        if request.domain == "strategy_lab":
            handoff_execution = execute_tool("get_strategy_lab_handoff_context", {}, context)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model="stub-model",
                response_id="resp_stub_strategy_lab",
                card=ResearchCard(
                    title="Strategy Lab test card",
                    hypothesis="Strategy Lab handoff context should separate pending intent from resolved research objects.",
                    rationale="The active Gamma Strategy Lab context exposes explicit handoff queue state for Copilot.",
                    required_data=["Handoff queue state", "Resolved object provenance"],
                    proposed_test="Resolve pending objects before treating them as evidence, and cite only resolved source refs.",
                    confounders=["Pending handoffs may resolve as unsupported.", "Warnings can differ by source object."],
                    next_steps=["Inspect handoff sources", "Review resolver warnings"],
                    caveats=["This is a test fixture."],
                    source_backed_claims=[
                        ResearchClaim(
                            claim="Strategy Lab handoff context was available to the copilot.",
                            evidence_refs=handoff_execution.trace.source_ids,
                        )
                    ],
                    inferred_claims=["The next interpretation depends on resolver coverage."],
                ),
                sources=[*context.sources, *handoff_execution.sources],
                tool_traces=[handoff_execution.trace],
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
        assert report["warning_provenance"] == []
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
        assert "## Warning Provenance\n- None recorded." in markdown
        assert "- `get_macro_series_history_summary`: Loaded" in markdown
        assert "- `macro.snapshot`: Macro snapshot" in markdown
        assert "Source provider: gamma_copilot" in markdown
    finally:
        runtime.shutdown()


_MACRO_STREAM_REQUEST = {
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
}


def test_copilot_stream_endpoint_emits_run_events(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card/stream",
            json={**_MACRO_STREAM_REQUEST, "run_id": "run_client_supplied"},
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert events[0]["event"] == "run.created"
        assert events[0]["run_id"] == "run_client_supplied"
        assert events[-1]["event"] == "completed"
        assert events[-1]["result"]["card"]["title"] == "Macro test card"
        sequences = [event["sequence"] for event in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)
        terminal_events = [
            event for event in events if event["event"] in {"completed", "failed", "cancelled"}
        ]
        assert len(terminal_events) == 1
    finally:
        runtime.shutdown()


def test_copilot_stream_persists_turn_for_replay(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post("/copilot/research-card/stream", json=_MACRO_STREAM_REQUEST)
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        final_result = events[-1]["result"]

        detail = client.get("/copilot/sessions/session_test_stream").json()
        assert len(detail["turns"]) == 1
        persisted = detail["turns"][0]["result"]
        assert persisted["status"] == final_result["status"] == "ready"
        assert persisted["card"]["title"] == final_result["card"]["title"]
        assert persisted["response_id"] == final_result["response_id"]
    finally:
        runtime.shutdown()


class _StreamingStubProvider:
    """Streaming provider stub that emits semantic events before finishing."""

    provider_name = "streaming_stub"
    model = "streaming-stub-model"

    def __init__(self, *, deltas: int = 3, wait_for_cancel: bool = False):
        self.deltas = deltas
        self.wait_for_cancel = wait_for_cancel

    def generate_research_card(self, *, request, context, tool_specs, execute_tool):
        raise AssertionError("streaming provider should use stream_research_card")

    def stream_research_card(self, *, request, context, tool_specs, execute_tool, emit, should_cancel):
        from src.services.copilot_provider import CopilotRunCancelled

        for index in range(self.deltas):
            if should_cancel():
                raise CopilotRunCancelled()
            emit("text.delta", {"delta": f"chunk-{index} "})
        if self.wait_for_cancel:
            deadline = time.monotonic() + 10.0
            while not should_cancel():
                if time.monotonic() > deadline:
                    raise AssertionError("cancellation never arrived")
                time.sleep(0.02)
            raise CopilotRunCancelled()
        emit("usage", {"input_tokens": 10, "output_tokens": 4})
        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="ready",
            provider=self.provider_name,
            model=self.model,
            response_id="resp_streaming_stub",
            card=ResearchCard(
                title="Streamed macro card",
                hypothesis="Streaming should deliver deltas before the final card.",
                rationale="Provider-native events reach the Gamma run contract.",
                required_data=[],
                proposed_test="Consume the run events in order.",
                confounders=[],
                next_steps=[],
                caveats=[],
                source_backed_claims=[],
                inferred_claims=[],
            ),
            sources=list(context.sources),
            warnings=list(context.warnings),
        )


def test_copilot_streaming_provider_events_reach_run_contract(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.provider = _StreamingStubProvider(deltas=3)
    try:
        response = client.post("/copilot/research-card/stream", json=_MACRO_STREAM_REQUEST)
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        event_types = [event["event"] for event in events]
        assert event_types[0] == "run.created"
        assert event_types.count("text.delta") == 3
        assert "usage" in event_types
        assert event_types[-1] == "completed"
        deltas = [event["data"]["delta"] for event in events if event["event"] == "text.delta"]
        assert deltas == ["chunk-0 ", "chunk-1 ", "chunk-2 "]
        assert events[-1]["result"]["status"] == "ready"
        assert events[-1]["result"]["card"]["title"] == "Streamed macro card"
    finally:
        runtime.shutdown()


def test_copilot_run_cancellation_emits_cancelled_terminal_and_persists(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.provider = _StreamingStubProvider(deltas=2, wait_for_cancel=True)
    try:
        request = CopilotResearchCardRequest(
            domain="macro",
            prompt="Cancel this run.",
            user_session_id="session_cancel_test",
            context=CopilotRequestContext(current_tab="macro", workspace_mode="research"),
        )
        events = []
        cancellation_requested = False
        stream = runtime.copilot_service.stream_research_card_events(request, run_id="run_cancel_test")
        for event in stream:
            events.append(event)
            if not cancellation_requested and len([e for e in events if e.event_type == "text.delta"]) == 2:
                outcome = runtime.copilot_service.cancel_run("run_cancel_test")
                assert outcome["found"] is True
                assert outcome["cancelled"] is True
                cancellation_requested = True

        assert events[-1].event_type == "cancelled"
        assert events[-1].result is not None
        assert events[-1].result.status == "cancelled"
        terminal = [e for e in events if e.event_type in {"completed", "failed", "cancelled"}]
        assert len(terminal) == 1
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)

        # Cancelled runs persist a replayable cancelled turn.
        detail = client.get("/copilot/sessions/session_cancel_test").json()
        assert len(detail["turns"]) == 1
        assert detail["turns"][0]["result"]["status"] == "cancelled"

        # Cancelling a finished retained run is a safe no-op.
        outcome = runtime.copilot_service.cancel_run("run_cancel_test")
        assert outcome["found"] is True
        assert outcome["cancelled"] is False
    finally:
        runtime.shutdown()


def test_copilot_run_reconnect_replays_after_cursor_without_duplicate_persistence(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        request = {**_MACRO_STREAM_REQUEST, "run_id": "run_replay_test"}
        initial = client.post("/copilot/research-card/stream", json=request)
        assert initial.status_code == 200
        events = [json.loads(line) for line in initial.text.splitlines() if line.strip()]
        cursor = events[0]["sequence"]

        replay = client.get(f"/copilot/runs/run_replay_test/events?after_sequence={cursor}")
        assert replay.status_code == 200
        replayed = [json.loads(line) for line in replay.text.splitlines() if line.strip()]
        assert replayed
        assert all(event["sequence"] > cursor for event in replayed)
        assert replayed[-1]["event"] == "completed"

        duplicate = client.post(
            "/copilot/research-card/stream",
            json={**request, "last_seen_sequence": replayed[-1]["sequence"]},
        )
        assert duplicate.status_code == 200
        assert duplicate.text == ""
        detail = client.get("/copilot/sessions/session_test_stream").json()
        assert len(detail["turns"]) == 1
    finally:
        runtime.shutdown()


def test_copilot_run_rejects_duplicate_id_for_different_request(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        first = client.post(
            "/copilot/research-card/stream",
            json={**_MACRO_STREAM_REQUEST, "run_id": "run_duplicate_test"},
        )
        assert first.status_code == 200
        duplicate = client.post(
            "/copilot/research-card/stream",
            json={
                **_MACRO_STREAM_REQUEST,
                "run_id": "run_duplicate_test",
                "prompt": "A different request must not reuse this run.",
            },
        )
        assert duplicate.status_code == 409
    finally:
        runtime.shutdown()


def test_copilot_disconnect_does_not_cancel_server_owned_run(tmp_path):
    class DisconnectProvider(_StreamingStubProvider):
        def stream_research_card(self, *, request, context, tool_specs, execute_tool, emit, should_cancel):
            emit("text.delta", {"delta": "still running "})
            time.sleep(0.08)
            return super().stream_research_card(
                request=request,
                context=context,
                tool_specs=tool_specs,
                execute_tool=execute_tool,
                emit=emit,
                should_cancel=should_cancel,
            )

    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.provider = DisconnectProvider(deltas=1)
    try:
        request = CopilotResearchCardRequest(
            domain="macro",
            prompt="Survive subscriber disconnect.",
            user_session_id="session_disconnect_test",
            context=CopilotRequestContext(current_tab="macro", workspace_mode="research"),
        )
        subscription = runtime.copilot_service.stream_research_card_events(
            request,
            run_id="run_disconnect_test",
        )
        assert next(subscription).event_type == "run.created"
        subscription.close()

        replayed = list(runtime.copilot_service.stream_existing_run_events("run_disconnect_test"))
        assert replayed[-1].event_type == "completed"
        assert replayed[-1].result is not None
        assert replayed[-1].result.status == "ready"
        detail = client.get("/copilot/sessions/session_disconnect_test").json()
        assert len(detail["turns"]) == 1
    finally:
        runtime.shutdown()


def test_copilot_cancel_before_first_event_and_timeout_are_terminal_and_persisted(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    runtime.copilot_service.provider = _StreamingStubProvider(wait_for_cancel=True)
    try:
        pending = runtime.copilot_service.cancel_run("run_pre_cancelled")
        assert pending == {
            "run_id": "run_pre_cancelled",
            "found": False,
            "cancelled": True,
            "status": "pending",
        }
        cancelled_request = CopilotResearchCardRequest(
            domain="macro",
            prompt="Cancel before start.",
            user_session_id="session_pre_cancelled",
            context=CopilotRequestContext(current_tab="macro", workspace_mode="research"),
        )
        cancelled_events = list(runtime.copilot_service.stream_research_card_events(
            cancelled_request,
            run_id="run_pre_cancelled",
        ))
        assert [event.event_type for event in cancelled_events] == ["run.created", "cancelled"]
        assert cancelled_events[-1].result is not None
        assert cancelled_events[-1].result.status == "cancelled"

        timeout_request = replace(
            cancelled_request,
            prompt="Time out safely.",
            user_session_id="session_timeout_test",
        )
        timeout_events = list(runtime.copilot_service.stream_research_card_events(
            timeout_request,
            run_id="run_timeout_test",
            timeout_seconds=0.03,
        ))
        assert timeout_events[-1].event_type == "cancelled"
        assert timeout_events[-1].data["reason"] == "timeout"
        assert timeout_events[-1].result is not None
        assert timeout_events[-1].result.status == "timeout"
        assert len(client.get("/copilot/sessions/session_pre_cancelled").json()["turns"]) == 1
        assert len(client.get("/copilot/sessions/session_timeout_test").json()["turns"]) == 1
    finally:
        runtime.shutdown()


def test_copilot_refusal_incomplete_and_provider_error_are_typed_run_states(tmp_path):
    class TerminalStateProvider:
        provider_name = "terminal_state_stub"
        model = "terminal-state-model"

        def __init__(self, status: str):
            self.status = status

        def generate_research_card(self, *, request, context, tool_specs, execute_tool):
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status=self.status,
                provider=self.provider_name,
                model=self.model,
                message=f"typed {self.status}",
                sources=list(context.sources),
                warnings=list(context.warnings),
            )

    client, runtime = _build_test_client(tmp_path)
    try:
        expected = {
            "refused": ("refusal", "completed"),
            "incomplete": ("incomplete", "completed"),
            "error": ("provider.error", "failed"),
        }
        for status, (semantic, terminal) in expected.items():
            runtime.copilot_service.provider = TerminalStateProvider(status)
            request = CopilotResearchCardRequest(
                domain="macro",
                prompt=f"Return {status}.",
                user_session_id=f"session_{status}_test",
                context=CopilotRequestContext(current_tab="macro", workspace_mode="research"),
            )
            events = list(runtime.copilot_service.stream_research_card_events(
                request,
                run_id=f"run_{status}_test",
            ))
            event_types = [event.event_type for event in events]
            assert semantic in event_types
            assert event_types[-1] == terminal
            assert sum(event.is_terminal for event in events) == 1
            assert len(client.get(f"/copilot/sessions/session_{status}_test").json()["turns"]) == 1
    finally:
        runtime.shutdown()


def test_openai_provider_streams_sdk_semantic_events():
    class StreamingCaptureProvider(OpenAIResponsesCopilotProvider):
        def __init__(self, sse_lines):
            super().__init__(
                api_key="test-key",
                model="gpt-test",
                reasoning_effort="low",
                store_responses=False,
            )
            self.sse_lines = sse_lines
            self.payloads: list[dict] = []

        def _open_stream(self, payload):
            self.payloads.append(payload)
            return iter(self.sse_lines)

    card_payload = json.dumps(
        {
            "title": "SSE card",
            "hypothesis": "Streaming works.",
            "rationale": "Deltas arrived before completion.",
            "required_data": [],
            "proposed_test": "n/a",
            "confounders": [],
            "next_steps": [],
            "caveats": [],
            "source_backed_claims": [],
            "inferred_claims": [],
        }
    )
    final_response = {
        "id": "resp_sse_test",
        "model": "gpt-test",
        "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": card_payload}],
            }
        ],
    }
    sse_lines = [
        {"type": "response.created", "response": {"id": "resp_sse_test"}},
        {"type": "response.output_text.delta", "delta": '{"title": "SSE'},
        {"type": "response.output_text.delta", "delta": ' card"}'},
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_test",
            "output_index": 0,
            "arguments": '{"region":"US"}',
        },
        {"type": "response.completed", "response": final_response},
    ]

    provider = StreamingCaptureProvider(sse_lines)
    emitted: list[tuple[str, dict]] = []
    result = provider.stream_research_card(
        request=CopilotResearchCardRequest(domain="macro", prompt="stream test"),
        context=CopilotContextBundle(
            domain="macro",
            current_tab="macro",
            summary_data={},
            sources=[],
            warnings=[],
        ),
        tool_specs=[],
        execute_tool=lambda name, arguments, context: (_ for _ in ()).throw(
            AssertionError("no tools expected")
        ),
        emit=lambda etype, data: emitted.append((etype, data)),
        should_cancel=lambda: False,
    )

    assert provider.payloads[0]["stream"] is True
    delta_events = [data["delta"] for etype, data in emitted if etype == "text.delta"]
    assert delta_events == ['{"title": "SSE', ' card"}']
    usage_events = [data for etype, data in emitted if etype == "usage"]
    assert usage_events == [{"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}]
    argument_events = [data for etype, data in emitted if etype == "function.arguments"]
    assert argument_events == [
        {"item_id": "fc_test", "output_index": 0, "arguments": '{"region":"US"}'}
    ]
    assert result.status == "ready"
    assert result.card is not None
    assert result.card.title == "SSE card"
    assert result.response_id == "resp_sse_test"


def test_openai_provider_stream_incomplete_returns_typed_state():
    class IncompleteStreamProvider(OpenAIResponsesCopilotProvider):
        def _open_stream(self, payload):
            del payload
            incomplete = {
                "type": "response.incomplete",
                "response": {
                    "id": "resp_incomplete",
                    "model": "gpt-test",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [],
                },
            }
            return iter([incomplete])

    provider = IncompleteStreamProvider(
        api_key="test-key",
        model="gpt-test",
        reasoning_effort="low",
        store_responses=False,
    )
    emitted: list[tuple[str, dict]] = []
    result = provider.stream_research_card(
        request=CopilotResearchCardRequest(domain="macro", prompt="incomplete test"),
        context=CopilotContextBundle(
            domain="macro",
            current_tab="macro",
            summary_data={},
            sources=[],
            warnings=[],
        ),
        tool_specs=[],
        execute_tool=lambda name, arguments, context: (_ for _ in ()).throw(
            AssertionError("no tools expected")
        ),
        emit=lambda etype, data: emitted.append((etype, data)),
        should_cancel=lambda: False,
    )

    assert ("incomplete", {"reason": "max_output_tokens"}) in emitted
    assert result.status == "incomplete"
    assert "max_output_tokens" in (result.message or "")


def test_openai_provider_stream_error_emits_typed_provider_error():
    class ErrorStreamProvider(OpenAIResponsesCopilotProvider):
        def _open_stream(self, payload):
            del payload
            return iter([{"type": "error", "message": "provider transport failed"}])

    provider = ErrorStreamProvider(
        api_key="test-key",
        model="gpt-test",
        reasoning_effort="low",
        store_responses=False,
    )
    emitted: list[tuple[str, dict]] = []
    result = provider.stream_research_card(
        request=CopilotResearchCardRequest(domain="macro", prompt="provider error test"),
        context=CopilotContextBundle(
            domain="macro",
            current_tab="macro",
            summary_data={},
            sources=[],
            warnings=[],
        ),
        tool_specs=[],
        execute_tool=lambda *_args: None,
        emit=lambda etype, data: emitted.append((etype, data)),
        should_cancel=lambda: False,
    )

    assert result.status == "error"
    assert emitted[-1][0] == "provider.error"
    assert "provider transport failed" in emitted[-1][1]["message"]


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


def test_strategy_lab_copilot_route_uses_pending_and_resolved_handoff_context(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "strategy_lab",
                "prompt": "Explain the Strategy Lab handoff state.",
                "context": {
                    "current_tab": "strategy_lab",
                    "workspace_mode": "research",
                    "strategy_lab_state": {
                        "handoff_context": {
                            "context_state": "mixed_handoff_states",
                            "items": [
                                {
                                    "id": "prediction_markets:oil:2026-06-27T00:00:00Z",
                                    "status": "pending",
                                    "context_state": "pending_resolution",
                                    "stale": False,
                                    "enqueued_at": "2026-06-27T00:00:00Z",
                                    "updated_at": "2026-06-27T00:00:00Z",
                                    "source_tab": "prediction_markets",
                                    "source_mode": "detail",
                                    "resolver_capability": "return_leg",
                                    "asset_class": "prediction_market",
                                    "value_kind": "probability",
                                    "default_side": "long_yes",
                                    "default_weight": 0.1,
                                    "provider": "polymarket",
                                    "selected_entity": {
                                        "entity_type": "prediction_market_contract",
                                        "label": "Oil threshold market",
                                        "normalized_id": "polymarket:oil",
                                        "provider_id": "oil",
                                        "native_id": "0xabc",
                                    },
                                    "normalized_ids": {"market_id": "polymarket:oil"},
                                    "warnings": ["Pending handoff still needs resolver coverage."],
                                },
                                {
                                    "id": "equity_research:AAPL:2026-06-27T00:01:00Z",
                                    "status": "resolved",
                                    "context_state": "resolved_return_leg",
                                    "stale": False,
                                    "enqueued_at": "2026-06-27T00:01:00Z",
                                    "updated_at": "2026-06-27T00:02:00Z",
                                    "source_tab": "equity_research",
                                    "source_mode": "scope_analysis",
                                    "resolver_capability": "return_leg",
                                    "asset_class": "equity",
                                    "value_kind": "return",
                                    "default_side": "long",
                                    "default_weight": 0.5,
                                    "provider": "fixture",
                                    "selected_entity": {
                                        "entity_type": "equity_symbol",
                                        "label": "AAPL",
                                        "normalized_id": "AAPL",
                                        "provider_id": "AAPL",
                                        "native_id": "AAPL",
                                    },
                                    "normalized_ids": {"symbol": "AAPL"},
                                    "warnings": [],
                                    "resolved": {
                                        "handoff_id": "equity_research:AAPL:2026-06-27T00:01:00Z",
                                        "status": "resolved",
                                        "resolved_capability": "return_leg",
                                        "date_coverage": {
                                            "label": "Price history",
                                            "start": "2026-06-01T00:00:00Z",
                                            "end": "2026-06-26T00:00:00Z",
                                        },
                                        "provider_summary": "fixture",
                                        "provenance": {"transformation": "equity_history_to_return_leg"},
                                        "warnings": ["Fixture coverage warning."],
                                        "resolved_objects": {
                                            "composer_draft_leg": {
                                                "label": "AAPL equity return stream",
                                                "identifier": "AAPL",
                                                "asset_class": "equity",
                                                "value_kind": "return",
                                                "return_point_count": 18,
                                                "coverage_start": "2026-06-01T00:00:00Z",
                                                "coverage_end": "2026-06-26T00:00:00Z",
                                            }
                                        },
                                    },
                                },
                            ],
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["domain"] == "strategy_lab"
        assert payload["card"]["title"] == "Strategy Lab test card"
        assert {trace["tool_name"] for trace in payload["tool_traces"]} == {"get_strategy_lab_handoff_context"}
        handoff_trace = payload["tool_traces"][0]
        assert handoff_trace["summary"] == "Expanded Strategy Lab handoff context: 2 current, 0 stale."
        assert any(source["source_id"] == "strategy_lab.handoffs" for source in payload["sources"])
        assert any(source["source_id"].startswith("strategy_lab.handoff.prediction_markets_oil") for source in payload["sources"])
        assert any(source["source_id"].startswith("strategy_lab.handoff.equity_research_aapl") for source in payload["sources"])
        assert any("Pending handoff still needs resolver coverage." in warning for warning in payload["warnings"])
        assert any("Fixture coverage warning." in warning for warning in payload["warnings"])
        assert any("strategy_lab.handoffs" in claim["evidence_refs"] for claim in payload["card"]["source_backed_claims"])
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
        assert [item["domain"] for item in payload["domain_plan"][:5]] == [
            "commodities",
            "maritime",
            "macro",
            "prediction_markets",
            "external_context",
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
        risk_schema = by_id["run_risk_scenario_analysis"]["input_schema"]
        assert risk_schema["properties"]["scenario_type"]["enum"] == [
            "baseline",
            "rate_shock",
            "equity_drawdown",
            "commodity_shock",
            "custom",
            None,
        ]
        assert "rate_shift_bps" in risk_schema["required"]
        assert "Rate shock proxy uses transparent duration assumptions" in " ".join(
            by_id["run_risk_scenario_analysis"]["failure_modes"]
        )
        assert by_id["run_risk_contribution_analysis"]["permission_policy"] == "automatic"
        assert by_id["run_risk_contribution_analysis"]["action_type"] == "run_analysis"
        assert by_id["run_risk_contribution_analysis"]["read_only"] is True
        assert by_id["run_risk_contribution_analysis"]["mutates_local_state"] is False
        assert by_id["run_risk_contribution_analysis"]["input_schema"]["required"] == [
            "source_scope",
            "top_n",
            "include_monte_carlo",
        ]
        assert by_id["run_strategy_lab_backtest"]["permission_policy"] == "automatic"
        assert by_id["run_strategy_lab_backtest"]["action_type"] == "run_analysis"
        assert by_id["run_strategy_lab_backtest"]["read_only"] is True
        assert by_id["run_strategy_lab_backtest"]["mutates_local_state"] is False
        assert by_id["run_hypothetical_portfolio_comparison"]["permission_policy"] == "automatic"
        assert by_id["run_hypothetical_portfolio_comparison"]["action_type"] == "run_analysis"
        assert by_id["run_hypothetical_portfolio_comparison"]["read_only"] is True
        assert by_id["run_hypothetical_portfolio_comparison"]["mutates_local_state"] is False
        assert "include_risk_analysis" in by_id["run_hypothetical_portfolio_comparison"]["input_schema"]["required"]
        assert "Optional Risk handoff" in " ".join(
            by_id["run_hypothetical_portfolio_comparison"]["failure_modes"]
        )
        assert by_id["run_research_scope_analysis"]["permission_policy"] == "automatic"
        assert by_id["run_research_scope_analysis"]["action_type"] == "run_analysis"
        assert by_id["run_research_scope_analysis"]["read_only"] is True
        assert by_id["run_research_scope_analysis"]["mutates_local_state"] is False
        assert by_id["run_research_scope_analysis"]["input_schema"]["required"] == [
            "scope_type",
            "primary_symbol",
            "benchmark_symbol",
            "lookback_days",
            "synthetic_positions",
        ]
        assert by_id["run_options_realized_implied_comparison"]["permission_policy"] == "automatic"
        assert by_id["run_options_realized_implied_comparison"]["action_type"] == "run_analysis"
        assert by_id["run_options_realized_implied_comparison"]["read_only"] is True
        assert by_id["run_options_realized_implied_comparison"]["mutates_local_state"] is False
        iv_schema = by_id["run_options_realized_implied_comparison"]["input_schema"]
        assert iv_schema["required"] == ["symbol", "max_expiries", "depth_preset", "market_data_mode"]
        assert iv_schema["properties"]["market_data_mode"]["enum"] == ["live", "delayed", "auto", None]
        assert "historical-volatility fields" in " ".join(
            by_id["run_options_realized_implied_comparison"]["failure_modes"]
        ).lower()
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
        assert any(step["tool_id"] == "run_risk_contribution_analysis" for step in payload["steps"])
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
        contribution_trace = next(
            trace
            for trace in payload["tool_traces"]
            if trace["tool_name"] == "run_risk_contribution_analysis"
        )
        assert contribution_trace["arguments"]["top_n"] == 10
        assert contribution_trace["arguments"]["include_monte_carlo"] is True
        risk_trace = next(
            trace
            for trace in payload["tool_traces"]
            if trace["tool_name"] == "run_risk_scenario_analysis"
        )
        assert risk_trace["arguments"]["scenario_type"] == "rate_shock"
        assert risk_trace["arguments"]["rate_shift_bps"] == 100.0
        assert any(
            source["source_id"] == "risk.scenario.analysis"
            for source in payload["sources"]
        )
        assert any(
            source["source_id"] == "risk.contribution.analysis"
            for source in payload["sources"]
        )
        event_types = [event["event_type"] for event in payload["operator_events"]]
        assert event_types[0] == "plan"
        assert "step-start" in event_types
        assert "tool-result" in event_types
        assert "artifact-created" in event_types
        assert event_types[-1] == "final-report"
        final_payload = payload["operator_events"][-1]["payload"]
        assert final_payload["status"] == "ready"
        assert final_payload["failed_steps"] == []
        assert final_payload["output_retention"]["mode"] == "full"
        assert "output_summaries" in final_payload
        assert any(
            "run_risk_scenario_analysis" in step_id
            for step_id in final_payload["output_summaries"]
        )
        completed_events = [
            event
            for event in payload["operator_events"]
            if event["event_type"] == "tool-result" and event["payload"].get("status") == "completed"
        ]
        assert completed_events
        assert all("output_summary" in event["payload"] for event in completed_events)
        sessions = client.get("/copilot/sessions").json()
        assert sessions and sessions[0]["turn_count"] == 1
        detail = client.get(f"/copilot/sessions/{sessions[0]['session_id']}").json()
        persisted_events = detail["turns"][0]["result"]["operator_events"]
        assert persisted_events
        assert [event["sequence"] for event in persisted_events] == list(range(1, len(persisted_events) + 1))
    finally:
        runtime.shutdown()


def test_copilot_operator_stream_uses_shared_run_contract_and_persists_once(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        response = client.post(
            "/copilot/operator-plan/execute/stream",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "run_id": "run_operator_stream_test",
                "user_session_id": "session_operator_stream_test",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {"snapshot": snapshot},
                },
            },
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        event_types = [event["event"] for event in events]
        assert event_types[0] == "run.created"
        assert "plan" in event_types
        assert "tool.call" in event_types
        assert "tool.result" in event_types
        assert "artifact.created" in event_types
        assert "report" in event_types
        assert event_types[-1] == "completed"
        assert all(event["run_id"] == "run_operator_stream_test" for event in events)
        assert [event["sequence"] for event in events] == list(range(len(events)))
        assert sum(event["event"] in {"completed", "failed", "cancelled"} for event in events) == 1
        assert events[-1]["result"]["status"] == "ready"
        detail = client.get("/copilot/sessions/session_operator_stream_test").json()
        assert len(detail["turns"]) == 1
    finally:
        runtime.shutdown()


def test_copilot_operator_stream_cancels_at_safe_step_boundary(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        service = runtime.copilot_service
        original_append = service._append_run_event
        cancellation_sent = False

        def append_and_cancel(handle, event_type, data=None, *, result=None):
            nonlocal cancellation_sent
            event = original_append(handle, event_type, data, result=result)
            if event_type == "tool.result" and not cancellation_sent:
                cancellation_sent = True
                outcome = service.cancel_run(handle.run_id)
                assert outcome["cancelled"] is True
            return event

        service._append_run_event = append_and_cancel
        response = client.post(
            "/copilot/operator-plan/execute/stream",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "run_id": "run_operator_cancel_test",
                "user_session_id": "session_operator_cancel_test",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {"snapshot": snapshot},
                },
            },
        )
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert cancellation_sent is True
        assert events[-1]["event"] == "cancelled"
        assert events[-1]["result"]["status"] == "cancelled"
        final_report = next(
            event for event in reversed(events) if event["event"] == "report"
        )
        assert final_report["data"]["payload"]["status"] == "cancelled"
        detail = client.get("/copilot/sessions/session_operator_cancel_test").json()
        assert len(detail["turns"]) == 1
        assert detail["turns"][0]["result"]["status"] == "cancelled"
    finally:
        runtime.shutdown()


def test_copilot_operator_final_outputs_compact_when_payload_is_large():
    outputs = {
        "step_run_large_analysis": {
            "symbol": "AAPL",
            "rows": [{"note": "x" * 1000} for _ in range(8)],
            "warnings": ["Large output warning"],
        }
    }
    summaries = {
        "step_run_large_analysis": {
            "kind": "dict",
            "symbol": "AAPL",
            "warnings_count": 1,
        }
    }

    bounded, retention = CopilotService._bounded_operator_outputs(outputs, summaries, max_bytes=500)

    assert retention["mode"] == "compact"
    assert retention["reason"] == "full_output_exceeded_payload_budget"
    assert retention["estimated_full_output_bytes"] > retention["max_full_output_bytes"]
    assert bounded["step_run_large_analysis"]["truncated"] is True
    assert bounded["step_run_large_analysis"]["output_summary"]["symbol"] == "AAPL"
    assert "rows" not in bounded["step_run_large_analysis"]


def test_agents_sdk_operator_final_outputs_compact_when_payload_is_large():
    outputs = {"step_agents_large": {"rows": ["x" * 1000 for _ in range(8)]}}
    summaries = {"step_agents_large": {"kind": "dict", "rows_count": 8}}

    bounded, retention = CopilotAgentsOperatorService._bounded_outputs(outputs, summaries, max_bytes=500)

    assert retention["mode"] == "compact"
    assert bounded["step_agents_large"]["truncated"] is True
    assert bounded["step_agents_large"]["output_summary"]["rows_count"] == 8


def test_copilot_operator_plan_includes_hypothetical_portfolio_comparison_tool(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "synthesis",
                "prompt": "Compare a hypothetical 60/40 AAPL/MSFT research portfolio to SPY",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "hypothetical_portfolio_comparison"
        assert any(step["tool_id"] == "run_hypothetical_portfolio_comparison" for step in payload["steps"])
        assert all(step["permission_policy"] == "automatic" for step in payload["steps"])
        assert not any("No registered Research Operator tools" in warning for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_hypothetical_portfolio_comparison(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Compare a hypothetical 60/40 AAPL/MSFT research portfolio to SPY",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(
            trace["tool_name"] == "run_hypothetical_portfolio_comparison"
            for trace in payload["tool_traces"]
        )
        comparison_trace = next(
            trace
            for trace in payload["tool_traces"]
            if trace["tool_name"] == "run_hypothetical_portfolio_comparison"
        )
        assert comparison_trace["arguments"]["benchmark_symbol"] == "SPY"
        assert comparison_trace["arguments"]["legs"] == [
            {"symbol": "AAPL", "weight": 0.6, "sec_type": None, "currency": None, "exchange": None},
            {"symbol": "MSFT", "weight": 0.4, "sec_type": None, "currency": None, "exchange": None},
        ]
        assert comparison_trace["arguments"]["include_risk_analysis"] is False
        assert any(
            source["source_id"] == "research.hypothetical_portfolio.operator_comparison"
            for source in payload["sources"]
        )
        final_event = payload["operator_events"][-1]
        outputs = final_event["payload"]["outputs"]
        comparison_output = next(
            output
            for step_id, output in outputs.items()
            if "run_hypothetical_portfolio_comparison" in step_id
        )
        assert comparison_output["portfolio_label"] == "Hypothetical AAPL/MSFT"
        assert comparison_output["benchmark_symbol"] == "SPY"
        assert comparison_output["coverage"]["aligned_observation_count"] >= 2
        assert comparison_output["left"]["object_type"] == "hypothetical_portfolio"
        assert comparison_output["right"]["object_type"] == "benchmark"
        assert "relative_return" in comparison_output["relative"]
        assert comparison_output["risk_handoff"]["status"] == "not_requested"
        assert any("read-only research" in warning for warning in comparison_output["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_hypothetical_portfolio_can_include_risk_handoff(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Compare risk for a hypothetical 60/40 AAPL/MSFT research portfolio to SPY",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        comparison_trace = next(
            trace
            for trace in payload["tool_traces"]
            if trace["tool_name"] == "run_hypothetical_portfolio_comparison"
        )
        assert comparison_trace["arguments"]["include_risk_analysis"] is True
        assert "risk.hypothetical_portfolio.operator_handoff" in comparison_trace["source_ids"]
        assert any(
            source["source_id"] == "risk.hypothetical_portfolio.operator_handoff"
            for source in payload["sources"]
        )
        final_event = payload["operator_events"][-1]
        output = next(
            value
            for step_id, value in final_event["payload"]["outputs"].items()
            if "run_hypothetical_portfolio_comparison" in step_id
        )
        assert output["risk_handoff"]["status"] == "completed"
        assert output["risk_handoff"]["snapshot"]["notional_value"] == 1_000_000.0
        assert output["risk_handoff"]["metrics"]["portfolio_value"] == 1_000_000.0
        assert output["risk_handoff"]["top_contributions"]
        assert any("temporary fixed-notional" in warning for warning in output["risk_handoff"]["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_research_scope_analysis(tmp_path):
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

        plan = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "research",
                "prompt": "Run research scope analysis on the current scope.",
                "context": {
                    "current_tab": "research",
                    "workspace_mode": "research",
                    "research_state": {"result": research},
                },
            },
        ).json()
        assert any(step["tool_id"] == "run_research_scope_analysis" for step in plan["steps"])

        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "research",
                "prompt": "Run research scope analysis on the current scope.",
                "context": {
                    "current_tab": "research",
                    "workspace_mode": "research",
                    "research_state": {"result": research},
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        trace = next(
            trace
            for trace in payload["tool_traces"]
            if trace["tool_name"] == "run_research_scope_analysis"
        )
        assert trace["arguments"]["scope_type"] == "single_ticker"
        assert trace["arguments"]["primary_symbol"] == "AAPL"
        assert any(
            source["source_id"] == "research.scope_analysis.operator"
            for source in payload["sources"]
        )
    finally:
        runtime.shutdown()


def test_copilot_operator_plan_includes_strategy_lab_backtest_tool(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "synthesis",
                "prompt": "Run a Strategy Lab backtest on the imported strategy",
                "context": {
                    "current_tab": "strategy_lab",
                    "workspace_mode": "research",
                    "strategy_lab_state": {
                        "imported_result": {
                            "name": "Fixture strategy",
                            "source_provider": "uploaded_csv",
                            "metrics": {"observation_count": 8, "annual_return": 0.12},
                            "warnings": [],
                            "retrieved_at": "2026-05-31T00:00:00",
                        }
                    },
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "active_context_research"
        assert any(step["tool_id"] == "run_strategy_lab_backtest" for step in payload["steps"])
        assert not any("No registered Research Operator tools" in warning for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_strategy_lab_backtest_summary(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Run a Strategy Lab backtest on the imported strategy",
                "context": {
                    "current_tab": "strategy_lab",
                    "workspace_mode": "research",
                    "strategy_lab_state": {
                        "imported_result": {
                            "name": "Fixture strategy",
                            "value_kind": "return",
                            "benchmark_column": "SPY",
                            "benchmark_value_kind": "return",
                            "source_provider": "uploaded_csv",
                            "origin": "tests.strategy_lab",
                            "freshness_label": "derived",
                            "retrieved_at": "2026-05-31T00:00:00",
                            "metrics": {
                                "observation_count": 8,
                                "annual_return": 0.12,
                                "annual_volatility": 0.18,
                                "sharpe_ratio": 0.67,
                                "max_drawdown": -0.04,
                                "benchmark_correlation": 0.72,
                            },
                            "returns_points": [
                                {"timestamp": "2026-01-02T00:00:00", "value": 0.01},
                                {"timestamp": "2026-01-05T00:00:00", "value": -0.004},
                            ],
                            "benchmark_points": [
                                {"timestamp": "2026-01-02T00:00:00", "value": 0.004},
                                {"timestamp": "2026-01-05T00:00:00", "value": -0.002},
                            ],
                            "annual_returns": [{"period": "2026", "value": 0.12}],
                            "warnings": [],
                        }
                    },
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(trace["tool_name"] == "run_strategy_lab_backtest" for trace in payload["tool_traces"])
        strategy_trace = next(
            trace for trace in payload["tool_traces"] if trace["tool_name"] == "run_strategy_lab_backtest"
        )
        assert strategy_trace["arguments"] == {"result_kind": "imported_result"}
        assert any(source["source_id"] == "strategy_lab.imported_result.operator_backtest" for source in payload["sources"])
        final_event = payload["operator_events"][-1]
        outputs = final_event["payload"]["outputs"]
        strategy_output = next(
            output
            for step_id, output in outputs.items()
            if "run_strategy_lab_backtest" in step_id
        )
        assert strategy_output["metrics"]["annual_return"] == 0.12
        assert strategy_output["benchmark"]["available"] is True
        assert strategy_output["coverage"]["return_points"] == 2
        assert any("does not execute strategy code" in warning for warning in strategy_output["warnings"])
    finally:
        runtime.shutdown()


def test_copilot_operator_plan_includes_options_realized_implied_tool(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL into CPI week and compare options implied versus realized volatility",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "single_company_event_research"
        assert any(step["tool_id"] == "run_options_realized_implied_comparison" for step in payload["steps"])
        iv_step = next(step for step in payload["steps"] if step["tool_id"] == "run_options_realized_implied_comparison")
        assert iv_step["domain"] == "iv"
        assert iv_step["permission_policy"] == "automatic"
        assert iv_step["action_type"] == "run_analysis"
    finally:
        runtime.shutdown()


def test_copilot_operator_execution_runs_options_realized_implied_comparison(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Run options IV realized implied comparison for AAPL",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert any(trace["tool_name"] == "run_options_realized_implied_comparison" for trace in payload["tool_traces"])
        assert any(source["source_id"].startswith("iv.realized_implied.") for source in payload["sources"])
        final_event = payload["operator_events"][-1]
        assert final_event["event_type"] == "final-report"
        output = next(
            value
            for key, value in final_event["payload"]["outputs"].items()
            if "run_options_realized_implied_comparison" in key
        )
        assert output["symbol"] == "AAPL"
        assert output["snapshot_available"] is True
        assert output["expiry_comparisons"]
        assert output["summary"]["expiry_count"] <= 6
        assert output["summary"]["ok_count"] >= 1
        assert output["source_provider"] in {"mock", "ibkr"}
        assert output["origin"].startswith("gamma.iv.surface")
    finally:
        runtime.shutdown()


def test_copilot_risk_scenario_tool_applies_bounded_symbol_shock_proxy(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot_payload = client.get("/portfolio/snapshot").json()
        context = runtime.copilot_service._build_risk_context(
            CopilotResearchCardRequest(
                domain="risk",
                prompt="Run a custom symbol shock.",
                context=CopilotRequestContext(
                    current_tab="risk",
                    workspace_mode="portfolio",
                    portfolio_state={"snapshot": snapshot_payload},
                ),
            )
        )
        symbol = snapshot_payload["positions"][0]["symbol"]
        execution = runtime.copilot_service._execute_tool(
            "run_risk_scenario_analysis",
            {
                "scenario_label": "custom_symbol_shock",
                "source_scope": "portfolio",
                "scenario_type": "custom",
                "rate_shift_bps": None,
                "equity_shock_pct": None,
                "duration_proxy_years": None,
                "symbol_shocks": [{"symbol": symbol, "price_shock_pct": -2.0}],
            },
            context,
        )

        assert execution.output["scenario_type"] == "custom"
        assert execution.output["shock_parameters"]["symbol_shocks"] == [
            {"symbol": symbol.upper(), "price_shock_pct": -0.95}
        ]
        assert execution.output["shock_proxy"]["applied"] is True
        assert execution.output["shock_proxy"]["position_impacts"][0]["basis"] == "explicit_symbol_shock"
        assert any("symbol_shocks" in warning and "clipped" in warning for warning in execution.output["warnings"])
        assert execution.trace.arguments["symbol_shocks"][0]["price_shock_pct"] == -0.95
    finally:
        runtime.shutdown()


def test_copilot_risk_shock_proxy_uses_duration_for_rate_scenarios():
    snapshot = PortfolioSnapshot(
        timestamp=datetime(2026, 5, 31),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem(
                symbol="TLT",
                sec_type="STK",
                currency="USD",
                quantity=10.0,
                avg_cost=None,
                market_price=100.0,
                market_value=1000.0,
                unrealized_pnl=None,
                base_market_value=1000.0,
            )
        ],
        net_liquidation=1000.0,
    )
    shock_spec = {
        "scenario_type": "rate_shock",
        "rate_shift_bps": 100.0,
        "equity_shock_pct": None,
        "duration_proxy_years": None,
        "symbol_shocks": [],
    }

    impact = CopilotService._risk_shock_proxy_impact(snapshot, shock_spec)

    assert impact["applied"] is True
    assert impact["estimated_pnl"] == -160.0
    assert impact["estimated_return_pct"] == -0.16
    assert impact["position_impacts"][0]["basis"] == "duration_proxy"


def test_copilot_operator_execution_can_use_agents_sdk_orchestrator(tmp_path, monkeypatch):
    from src.application import copilot_agents_operator as agents_operator

    class _FakeAgent:
        def __init__(self, *, name, model, instructions, tools):
            self.name = name
            self.model = model
            self.instructions = instructions
            self.tools = tools

    class _FakeRunner:
        @staticmethod
        async def run(agent, prompt, max_turns):
            assert agent.name == "Gamma Research Operator"
            assert max_turns >= 1
            assert "run_risk_scenario_analysis" in prompt
            agent.tools[0]("run_risk_scenario_analysis", "{}")
            return type("_FakeRunResult", (), {"final_output": "ok"})()

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", "gpt-test-operator")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agents_operator,
        "_load_agents_sdk",
        lambda: agents_operator._AgentsSdkModule(
            Agent=_FakeAgent,
            Runner=_FakeRunner,
            function_tool=lambda func: func,
        ),
    )

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
        assert payload["provider"] == "openai_agents_sdk_operator"
        assert payload["model"] == "gpt-test-operator"
        assert any(trace["tool_name"] == "run_risk_scenario_analysis" for trace in payload["tool_traces"])
        assert payload["operator_events"][0]["payload"]["orchestrator"] == "openai_agents_sdk_operator"
        final_payload = payload["operator_events"][-1]["payload"]
        assert final_payload["orchestrator"] == "openai_agents_sdk_operator"
        assert final_payload["failed_steps"] == []
        assert "output_summaries" in final_payload
        assert any(
            "run_risk_scenario_analysis" in step_id
            for step_id in final_payload["output_summaries"]
        )
        completed_events = [
            event
            for event in payload["operator_events"]
            if event["event_type"] == "tool-result" and event["payload"].get("status") == "completed"
        ]
        assert completed_events
        assert all("output_summary" in event["payload"] for event in completed_events)

        sessions = client.get("/copilot/sessions").json()
        assert sessions and sessions[0]["turn_count"] == 1
        detail = client.get(f"/copilot/sessions/{sessions[0]['session_id']}").json()
        persisted = detail["turns"][0]["result"]
        assert persisted["provider"] == "openai_agents_sdk_operator"
        assert persisted["operator_events"][-1]["payload"]["orchestrator"] == "openai_agents_sdk_operator"
    finally:
        runtime.shutdown()


def test_agents_sdk_operator_streams_provider_and_tool_progress_live(tmp_path, monkeypatch):
    from src.application import copilot_agents_operator as agents_operator

    class _FakeAgent:
        def __init__(self, *, name, model, instructions, tools):
            del name
            del model
            del instructions
            self.tools = tools

    class _FakeSdkEvent:
        def __init__(self, event_type):
            self.type = event_type

    class _FakeStreamResult:
        def __init__(self, agent):
            self.agent = agent
            self.cancel_mode = None

        async def stream_events(self):
            yield _FakeSdkEvent("agent_updated_stream_event")
            self.agent.tools[0]("run_risk_scenario_analysis", "{}")
            yield _FakeSdkEvent("run_item_stream_event")

        def cancel(self, mode="immediate"):
            self.cancel_mode = mode

    class _FakeRunner:
        @staticmethod
        def run_streamed(agent, prompt, max_turns):
            assert max_turns >= 1
            assert "run_risk_scenario_analysis" in prompt
            return _FakeStreamResult(agent)

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agents_operator,
        "_load_agents_sdk",
        lambda: agents_operator._AgentsSdkModule(
            Agent=_FakeAgent,
            Runner=_FakeRunner,
            function_tool=lambda func: func,
        ),
    )

    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        response = client.post(
            "/copilot/operator-plan/execute/stream",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "run_id": "run_agents_sdk_stream",
                "user_session_id": "session_agents_sdk_stream",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {"snapshot": snapshot},
                },
            },
        )

        assert response.status_code == 200
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]
        event_types = [event["event"] for event in events]
        assert "provider.progress" in event_types, json.dumps(events, indent=2)
        assert "tool.call" in event_types
        assert "tool.result" in event_types
        assert event_types.index("provider.progress") < event_types.index("tool.result")
        assert events[-1]["event"] == "completed"
        assert events[-1]["result"]["provider"] == "openai_agents_sdk_operator"
        assert [event["sequence"] for event in events] == list(range(len(events)))
    finally:
        runtime.shutdown()


def test_agents_sdk_operator_cancels_after_current_safe_turn(tmp_path, monkeypatch):
    from src.application import copilot_agents_operator as agents_operator

    streams = []

    class _FakeAgent:
        def __init__(self, *, name, model, instructions, tools):
            del name
            del model
            del instructions
            self.tools = tools

    class _FakeSdkEvent:
        type = "run_item_stream_event"

    class _FakeStreamResult:
        def __init__(self, agent):
            self.agent = agent
            self.cancel_mode = None
            streams.append(self)

        async def stream_events(self):
            self.agent.tools[0]("run_risk_scenario_analysis", "{}")
            yield _FakeSdkEvent()

        def cancel(self, mode="immediate"):
            self.cancel_mode = mode

    class _FakeRunner:
        @staticmethod
        def run_streamed(agent, prompt, max_turns):
            del prompt
            del max_turns
            return _FakeStreamResult(agent)

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agents_operator,
        "_load_agents_sdk",
        lambda: agents_operator._AgentsSdkModule(
            Agent=_FakeAgent,
            Runner=_FakeRunner,
            function_tool=lambda func: func,
        ),
    )

    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        service = runtime.copilot_service
        original_append = service._append_run_event
        cancellation_sent = False

        def append_and_cancel(handle, event_type, data=None, *, result=None):
            nonlocal cancellation_sent
            event = original_append(handle, event_type, data, result=result)
            if event_type == "tool.result" and not cancellation_sent:
                cancellation_sent = True
                assert service.cancel_run(handle.run_id)["cancelled"] is True
            return event

        service._append_run_event = append_and_cancel
        response = client.post(
            "/copilot/operator-plan/execute/stream",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "run_id": "run_agents_sdk_cancel",
                "context": {
                    "current_tab": "portfolio",
                    "workspace_mode": "portfolio",
                    "portfolio_state": {"snapshot": snapshot},
                },
            },
        )
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]
        assert cancellation_sent is True
        assert streams and streams[0].cancel_mode == "after_turn"
        assert events[-1]["event"] == "cancelled"
        assert events[-1]["result"]["status"] == "cancelled"
    finally:
        runtime.shutdown()


def test_agents_sdk_operator_surfaces_provider_failure_as_typed_terminal(tmp_path, monkeypatch):
    from src.application import copilot_agents_operator as agents_operator

    class _FakeAgent:
        def __init__(self, *, name, model, instructions, tools):
            del name
            del model
            del instructions
            del tools

    class _FakeRunner:
        @staticmethod
        def run_streamed(agent, prompt, max_turns):
            del agent
            del prompt
            del max_turns
            raise RuntimeError("provider unavailable")

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agents_operator,
        "_load_agents_sdk",
        lambda: agents_operator._AgentsSdkModule(
            Agent=_FakeAgent,
            Runner=_FakeRunner,
            function_tool=lambda func: func,
        ),
    )

    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "context": {"current_tab": "portfolio", "workspace_mode": "portfolio"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert payload["provider"] == "openai_agents_sdk_operator"
        assert any(
            "Agents SDK operator run failed: RuntimeError: provider unavailable" in warning
            for warning in payload["warnings"]
        )
    finally:
        runtime.shutdown()


def test_custom_operator_records_partial_tool_failure_and_enforces_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    client, runtime = _build_test_client(tmp_path)
    try:
        service = runtime.copilot_service
        original_execute = service._execute_tool
        original_plan = service.plan_research_operator
        execution_count = 0

        def execute_with_one_failure(tool_id, arguments, context):
            nonlocal execution_count
            execution_count += 1
            if execution_count == 1:
                return CopilotToolExecution(
                    output={"error": "fixture partial failure"},
                    trace=CopilotToolTrace(
                        tool_name=tool_id,
                        summary="Fixture partial tool failure.",
                        arguments=arguments,
                        source_ids=[],
                    ),
                )
            return original_execute(tool_id, arguments, context)

        service._execute_tool = execute_with_one_failure
        service.plan_research_operator = lambda request: replace(
            original_plan(request),
            max_tool_calls=2,
        )
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Is my portfolio exposed to rate shock?",
                "context": {"current_tab": "portfolio", "workspace_mode": "portfolio"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        final_report = next(
            item
            for item in payload["operator_events"]
            if item["event_type"] == "final-report"
        )
        assert final_report["payload"]["failed_steps"], payload
        assert any(
            item["payload"].get("status") == "failed"
            for item in payload["operator_events"]
            if item["event_type"] == "tool-result"
        )
        assert len(payload["tool_traces"]) == 2
        assert any(
            "Stopped operator execution after 2 tools." in warning
            for warning in payload["warnings"]
        )
    finally:
        runtime.shutdown()


def test_agents_sdk_configuration_cannot_bypass_local_mutation_authority(tmp_path, monkeypatch):
    from src.application import copilot_agents_operator as agents_operator

    class _FakeAgent:
        def __init__(self, *, name, model, instructions, tools):
            del name
            del model
            del instructions
            self.tools = tools

    class _FakeRunner:
        @staticmethod
        async def run(agent, prompt, max_turns):
            del agent
            del prompt
            del max_turns
            raise AssertionError("Local mutation authority must not delegate to the Agents SDK.")

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agents_operator,
        "_load_agents_sdk",
        lambda: agents_operator._AgentsSdkModule(
            Agent=_FakeAgent,
            Runner=_FakeRunner,
            function_tool=lambda func: func,
        ),
    )

    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()

        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Research AAPL and adjust the DCF revenue growth assumption",
                "user_session_id": "session_operator_confirmation_report",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "gamma_operator_executor"
        assert not any(trace["tool_name"] == "fundamentals.apply_dcf_update" for trace in payload["tool_traces"])
        assert any("explicit supported percentage" in warning for warning in payload["warnings"])
        assert any(
            event["event_type"] == "confirmation-needed"
            and "fundamentals.apply_dcf_update" in event["payload"]["required_for_tool_ids"]
            for event in payload["operator_events"]
        )

        report_response = client.post(
            "/copilot/sessions/session_operator_confirmation_report/report",
            json={"title": "Operator Confirmation Report"},
        )
        assert report_response.status_code == 200
        report = report_response.json()
        assert any("confirmation checkpoints" in warning for warning in report["warnings"])
        assert any(
            row["event_type"] == "confirmation-needed"
            and row["warning"]
            == "Operator plan includes confirmation checkpoints that were not applied by automatic execution."
            for row in report["warning_provenance"]
        )
        apply_summary = next(
            row
            for row in report["tool_trace_summary"]
            if row["tool_name"] == "fundamentals.apply_dcf_update"
        )
        assert apply_summary["status"] == "confirmation_required"
        assert apply_summary["event_type"] == "confirmation-needed"
        assert "dcf update mutates" in apply_summary["summary"].lower()
        assert any("confirmation checkpoints" in warning for warning in apply_summary["warnings"])

        export_response = client.post(
            "/copilot/sessions/session_operator_confirmation_report/report/export",
            json={"title": "Operator Confirmation Report"},
        )
        assert export_response.status_code == 200
        assert "## Warning Provenance" in export_response.text
        assert "event `confirmation-needed`" in export_response.text
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


def test_research_action_registry_rejects_unsafe_or_unauthorized_actions():
    with pytest.raises(ResearchActionRegistryError, match="prohibited"):
        ResearchActionRegistry(
            [
                CopilotResearchActionDefinition(
                    tool_id="portfolio.execute_trade",
                    domains=["portfolio"],
                    action_type="apply_change",
                    description="Unsafe execution action.",
                    input_schema={},
                    read_only=False,
                    mutates_local_state=True,
                    requires_confirmation=True,
                    permission_policy="confirmation_required",
                )
            ]
        )

    with pytest.raises(ResearchActionRegistryError, match="must require confirmation"):
        ResearchActionRegistry(
            [
                CopilotResearchActionDefinition(
                    tool_id="fundamentals.apply_local_change",
                    domains=["fundamentals"],
                    action_type="apply_change",
                    description="Invalid ungated mutation.",
                    input_schema={},
                    read_only=False,
                    mutates_local_state=True,
                    requires_confirmation=False,
                    permission_policy="automatic",
                )
            ]
        )

    registry = ResearchActionRegistry(
        [
            CopilotResearchActionDefinition(
                tool_id="fundamentals.apply_local_change",
                domains=["fundamentals"],
                action_type="apply_change",
                description="Valid confirmation-gated local mutation.",
                input_schema={},
                read_only=False,
                mutates_local_state=True,
                requires_confirmation=True,
                permission_policy="confirmation_required",
            )
        ]
    )
    with pytest.raises(ResearchActionPermissionError, match="not automatic"):
        registry.authorize_automatic("fundamentals.apply_local_change")


def test_copilot_operator_drafts_exact_context_bound_dcf_mutation(tmp_path, monkeypatch):
    # Even when Agents SDK orchestration is enabled, local mutation drafting stays
    # in Gamma's deterministic confirmation authority path.
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "agents_sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "synthesis",
                "prompt": "Set AAPL base DCF WACC to 9%",
                "run_id": "run_context_bound_dcf",
                "user_session_id": "session_context_bound_dcf",
                "context_fingerprint": "context-v1",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "awaiting_confirmation", payload
        event = next(
            item
            for item in payload["operator_events"]
            if item["event_type"] == "confirmation-needed"
            and item["payload"].get("mutation_id")
        )
        mutation = event["payload"]["mutation"]
        assert mutation["session_id"] == "session_context_bound_dcf"
        assert mutation["run_id"] == "run_context_bound_dcf"
        assert mutation["context_fingerprint"] == "context-v1"
        assert mutation["proposal_hash"]
        assert mutation["expires_at"]
        assert any(
            item["path"] == "scenarios.base.assumptions.wacc_pct"
            and item["after"] == 0.09
            for item in mutation["diff"]
        )
        assert not any(
            trace["tool_name"] == "fundamentals.apply_dcf_update"
            for trace in payload["tool_traces"]
        )
        final_report = next(
            item
            for item in payload["operator_events"]
            if item["event_type"] == "final-report"
        )
        assert mutation["confirmation_token"] not in json.dumps(final_report["payload"])

        detail_response = client.get("/copilot/sessions/session_context_bound_dcf")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert [item["mutation_id"] for item in detail["mutations"]] == [
            mutation["mutation_id"]
        ]
        assert detail["turns"][-1]["confirmations"][-1]["status"] == "pending"
        assert detail["turns"][-1]["confirmations"][-1]["proposal_hash"] == mutation["proposal_hash"]

        applied_response = client.post(
            f"/copilot/mutations/{mutation['mutation_id']}/apply",
            json={
                "confirmation_token": mutation["confirmation_token"],
                "user_session_id": mutation["session_id"],
                "context_fingerprint": mutation["context_fingerprint"],
                "proposal_hash": mutation["proposal_hash"],
            },
        )
        assert applied_response.status_code == 200
        resolved_detail = client.get(
            "/copilot/sessions/session_context_bound_dcf"
        ).json()
        assert resolved_detail["turns"][-1]["result"]["status"] == "ready"
        assert resolved_detail["turns"][-1]["terminal_status"] == "ready"
        assert resolved_detail["turns"][-1]["confirmations"][-1]["status"] == "applied"
        assert resolved_detail["turns"][-1]["mutation_refs"] == [
            {
                "artifact_id": mutation["mutation_id"],
                "artifact_type": "mutation",
                "status": "applied",
                "mutation_id": mutation["mutation_id"],
                "rollback_snapshot_id": applied_response.json()["mutation"]["rollback_snapshot_id"],
            }
        ]
        resolved_confirmation = next(
            item
            for item in resolved_detail["turns"][-1]["result"]["operator_events"]
            if item["event_type"] == "confirmation-needed"
            and item["payload"].get("mutation_id") == mutation["mutation_id"]
        )
        assert resolved_confirmation["payload"]["mutation"]["status"] == "applied"
    finally:
        runtime.shutdown()


def test_context_bound_dcf_confirmation_survives_restart_and_is_single_use(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
        proposal = client.post(
            "/copilot/mutations/fundamentals/dcf/propose",
            json={
                "ticker": "AAPL",
                "scenario_id": "base",
                "assumptions": {"wacc": 0.09},
                "user_session_id": "session_restart_dcf",
                "run_id": "run_restart_dcf",
                "context_fingerprint": "context-v1",
            },
        )
        assert proposal.status_code == 200
        draft = proposal.json()
    finally:
        runtime.shutdown()

    restarted_client, restarted_runtime = _build_test_client(tmp_path)
    try:
        restarted_runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
        wrong_session = restarted_client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={
                "confirmation_token": draft["confirmation_token"],
                "user_session_id": "session-other",
                "context_fingerprint": "context-v1",
                "proposal_hash": draft["proposal_hash"],
            },
        )
        assert wrong_session.status_code == 400

        wrong_context = restarted_client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={
                "confirmation_token": draft["confirmation_token"],
                "user_session_id": "session_restart_dcf",
                "context_fingerprint": "context-v2",
                "proposal_hash": draft["proposal_hash"],
            },
        )
        assert wrong_context.status_code == 400

        wrong_hash = restarted_client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={
                "confirmation_token": draft["confirmation_token"],
                "user_session_id": "session_restart_dcf",
                "context_fingerprint": "context-v1",
                "proposal_hash": "tampered-proposal",
            },
        )
        assert wrong_hash.status_code == 400

        applied = restarted_client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={
                "confirmation_token": draft["confirmation_token"],
                "user_session_id": "session_restart_dcf",
                "context_fingerprint": "context-v1",
                "proposal_hash": draft["proposal_hash"],
            },
        )
        assert applied.status_code == 200
        assert applied.json()["mutation"]["status"] == "applied"

        replay = restarted_client.post(
            f"/copilot/mutations/{draft['mutation_id']}/apply",
            json={
                "confirmation_token": draft["confirmation_token"],
                "user_session_id": "session_restart_dcf",
                "context_fingerprint": "context-v1",
                "proposal_hash": draft["proposal_hash"],
            },
        )
        assert replay.status_code == 400
        assert "not active" in replay.json()["detail"]
    finally:
        restarted_runtime.shutdown()


def test_copilot_mutation_reject_and_expiry_are_enforced(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = _StubFundamentalsService()
        rejected_draft = client.post(
            "/copilot/mutations/fundamentals/dcf/propose",
            json={
                "ticker": "AAPL",
                "assumptions": {"wacc": 0.09},
                "user_session_id": "session_reject_dcf",
            },
        ).json()
        rejected = client.post(
            f"/copilot/mutations/{rejected_draft['mutation_id']}/reject",
            json={"user_session_id": "session_reject_dcf"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"

        apply_rejected = client.post(
            f"/copilot/mutations/{rejected_draft['mutation_id']}/apply",
            json={
                "confirmation_token": rejected_draft["confirmation_token"],
                "user_session_id": "session_reject_dcf",
                "proposal_hash": rejected_draft["proposal_hash"],
            },
        )
        assert apply_rejected.status_code == 400

        expired_draft = client.post(
            "/copilot/mutations/fundamentals/dcf/propose",
            json={"ticker": "AAPL", "assumptions": {"wacc": 0.1}},
        ).json()
        runtime.copilot_store.update_mutation(
            expired_draft["mutation_id"],
            lambda item: replace(item, expires_at=datetime.utcnow() - timedelta(seconds=1)),
        )
        expired = client.post(
            f"/copilot/mutations/{expired_draft['mutation_id']}/apply",
            json={"confirmation_token": expired_draft["confirmation_token"]},
        )
        assert expired.status_code == 400
        assert "expired" in expired.json()["detail"]
        expired_state = client.get(
            f"/copilot/mutations/{expired_draft['mutation_id']}"
        )
        assert expired_state.status_code == 200
        assert expired_state.json()["status"] == "expired"
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
            trace["tool_name"] == "get_news_items_context"
            for trace in payload["tool_traces"]
        )
        assert any(
            source["source_id"] == "external_context.news_feed"
            and source["provider"] == "sample_news"
            for source in payload["sources"]
        )
        commodity_decision = next(
            item for item in payload["research_plan"]["domain_decisions"]
            if item["domain"] == "commodities"
        )
        assert commodity_decision["used"] is False
        assert commodity_decision["classification"] == "irrelevant"
        assert "explicitly limited" in commodity_decision["reason"].lower()
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


def test_copilot_service_reclassifies_unresolved_claims_before_persistence():
    result = CopilotResearchCardResult(
        domain="macro",
        current_tab="copilot",
        status="ready",
        provider="stub",
        card=ResearchCard(
            title="Evidence resolution",
            hypothesis="H",
            rationale="R",
            proposed_test="T",
            source_backed_claims=[
                ResearchClaim(claim="Fully grounded.", evidence_refs=["macro.known"]),
                ResearchClaim(claim="Partially grounded.", evidence_refs=["macro.known", "fake.source"]),
                ResearchClaim(claim="Unsupported claim.", evidence_refs=["missing.source"]),
                ResearchClaim(claim="Uncited claim.", evidence_refs=[]),
            ],
            inferred_claims=["Existing inference."],
        ),
        sources=[
            CopilotSourceRef(
                source_id="macro.known",
                label="Known macro source",
                kind="workspace",
                provider="gamma",
                origin="gamma.macro",
            )
        ],
    )

    normalized = CopilotService._normalize_result_sources(result)

    assert normalized.card is not None
    assert [(claim.claim, claim.evidence_refs) for claim in normalized.card.source_backed_claims] == [
        ("Fully grounded.", ["macro.known"]),
        ("Partially grounded.", ["macro.known"]),
    ]
    assert normalized.card.inferred_claims == [
        "Existing inference.",
        "Unsupported claim.",
        "Uncited claim.",
    ]
    assert any("fake.source" in warning for warning in normalized.warnings)
    assert any("missing.source" in warning for warning in normalized.warnings)


def test_copilot_store_defensively_reclassifies_unresolved_claims(tmp_path):
    store = CopilotStore(tmp_path / "copilot")
    result = CopilotResearchCardResult(
        domain="macro",
        current_tab="copilot",
        status="ready",
        provider="stub",
        card=ResearchCard(
            title="Persistence boundary",
            hypothesis="H",
            rationale="R",
            proposed_test="T",
            source_backed_claims=[ResearchClaim(claim="Fake citation.", evidence_refs=["unknown.source"])],
        ),
    )

    session, _snapshot, _turn = store.record_turn(
        session_id=None,
        title=None,
        domain="macro",
        current_tab="copilot",
        workspace_mode="research",
        prompt="Check evidence.",
        context_fingerprint="fp-evidence",
        context_summary={},
        result=result,
    )

    restored = store.list_turns(session.session_id)[0].result
    assert restored.card is not None
    assert restored.card.source_backed_claims == []
    assert restored.card.inferred_claims == ["Fake citation."]
    assert any("Reclassified" in warning for warning in restored.warnings)


def test_copilot_store_revalidates_legacy_claims_when_reading_json():
    restored = CopilotStore._result_from_json(
        {
            "domain": "macro",
            "current_tab": "copilot",
            "status": "ready",
            "provider": "legacy",
            "card": {
                "title": "Legacy evidence",
                "hypothesis": "H",
                "rationale": "R",
                "proposed_test": "T",
                "source_backed_claims": [
                    {"claim": "Known claim.", "evidence_refs": ["macro.known"]},
                    {"claim": "Stale fake claim.", "evidence_refs": ["removed.source"]},
                ],
            },
            "sources": [
                {
                    "source_id": "macro.known",
                    "label": "Known macro source",
                    "kind": "workspace",
                    "provider": "gamma",
                    "origin": "gamma.macro",
                }
            ],
        }
    )

    assert restored.card is not None
    assert [(claim.claim, claim.evidence_refs) for claim in restored.card.source_backed_claims] == [
        ("Known claim.", ["macro.known"])
    ]
    assert restored.card.inferred_claims == ["Stale fake claim."]
    assert any("removed.source" in warning for warning in restored.warnings)


def test_operator_terminal_normalizes_evidence_even_without_store():
    service = object.__new__(CopilotService)
    service.store = None
    result = CopilotResearchCardResult(
        domain="synthesis",
        current_tab="copilot",
        status="cancelled",
        provider="gamma_operator_executor",
        card=ResearchCard(
            title="Cancelled operator",
            hypothesis="H",
            rationale="R",
            proposed_test="T",
            source_backed_claims=[
                ResearchClaim(claim="Unsupported terminal claim.", evidence_refs=["missing.source"])
            ],
        ),
    )

    normalized = service._persist_operator_execution_result(
        CopilotResearchCardRequest(domain="synthesis"),
        None,
        result,
    )

    assert normalized.card is not None
    assert normalized.card.source_backed_claims == []
    assert normalized.card.inferred_claims == ["Unsupported terminal claim."]
    assert any("missing.source" in warning for warning in normalized.warnings)


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


def test_openai_provider_uses_request_reasoning_effort_override():
    class CaptureOpenAIProvider(OpenAIResponsesCopilotProvider):
        def __init__(self):
            super().__init__(
                api_key="test-key",
                model="gpt-test",
                reasoning_effort="medium",
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
        request=CopilotResearchCardRequest(domain="macro", reasoning_effort="high"),
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        tool_specs=[],
        execute_tool=lambda *_args: None,
    )

    assert provider.payloads[0]["reasoning"] == {"effort": "high"}


def test_openai_provider_retries_once_when_structured_card_is_missing():
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
                    "id": "resp_missing_card",
                    "model": "gpt-test",
                    "output": [{"type": "message", "content": []}],
                }
            return {
                "id": "resp_retry_card",
                "model": "gpt-test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "title": "Retry Test",
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

    result = provider.generate_research_card(
        request=CopilotResearchCardRequest(domain="macro"),
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        tool_specs=[],
        execute_tool=lambda *_args: None,
    )

    assert result.status == "ready"
    assert result.card is not None
    assert result.card.title == "Retry Test"
    assert result.response_id == "resp_retry_card"
    assert len(provider.payloads) == 2
    assert "tools" not in provider.payloads[1]
    assert "tool_choice" not in provider.payloads[1]
    assert provider.payloads[1]["prompt_cache_key"].endswith(":structured-retry")
    retry_text = provider.payloads[1]["input"][-1]["content"][0]["text"]
    assert "OpenAI returned no structured research card." in retry_text


def test_openai_provider_preserves_reasoning_items_when_response_storage_is_disabled():
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
    reasoning = next(item for item in second_input if item.get("type") == "reasoning")
    assert reasoning["id"] == "rs_not_persisted"
    function_call = next(item for item in second_input if item.get("type") == "function_call")
    assert function_call["id"] == "fc_not_persisted"
    assert function_call["call_id"] == "call_123"


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


def test_sitrep_copilot_context_bundles_sections_warnings_and_follow_ups(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        created = client.post(
            "/sitrep/follow-ups",
            json={
                "row_id": "evt-cpi",
                "title": "CPI release",
                "source": "Event",
                "note": "Watch the front end",
            },
        )
        assert created.status_code == 200

        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "sitrep",
                "prompt": "Summarize the situation report.",
                "context": {"current_tab": "sitrep", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["domain"] == "sitrep"
        source_ids = {source["source_id"] for source in payload["sources"]}
        assert "sitrep.workspace" in source_ids
        assert "sitrep.news" in source_ids
        assert "sitrep.follow_ups" in source_ids
    finally:
        runtime.shutdown()


def test_sitrep_copilot_context_builder_summary_shape(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        bundle = runtime.copilot_service._build_context_for_domain(
            "sitrep", CopilotRequestContext(current_tab="sitrep", workspace_mode="research")
        )
        assert bundle.domain == "sitrep"
        summary = bundle.summary_data
        assert set(summary["sections_loaded"]) == {
            "equities",
            "indices",
            "macro",
            "commodities",
            "prediction_markets",
            "news",
        }
        assert summary["equities"]["universe_id"] == "broad_us_market"
        assert summary["indices"]["universe_id"] == "global_indices"
        assert summary["macro"]["region"] == "US"
        assert summary["news"]["items"]
        assert isinstance(summary["follow_ups"], list)
        assert summary["section_warnings"] == []
    finally:
        runtime.shutdown()


def _checkpoint3_persisted_result() -> CopilotResearchCardResult:
    source = CopilotSourceRef(
        source_id="macro.checkpoint3",
        label="Checkpoint 3 macro snapshot",
        kind="workspace_context",
        provider="gamma",
        origin="gamma.macro.snapshot",
        description="Persisted source used by the Checkpoint 3 restart fixture.",
        retrieved_at=datetime(2026, 7, 24, 10, 30),
    )
    return CopilotResearchCardResult(
        domain="macro",
        current_tab="macro",
        status="ready",
        provider="stub_provider",
        model="stub-model-v3",
        response_id="resp_checkpoint3",
        card=ResearchCard(
            title="Checkpoint 3 replay",
            hypothesis="A complete Copilot turn can be reconstructed after restart.",
            rationale="The record owns its plan, trace, usage, evidence, warning, and artifact links.",
            required_data=["Persisted macro snapshot"],
            proposed_test="Restart the store and compare every typed field.",
            confounders=["Legacy records contain fewer fields."],
            next_steps=["Export the linked report."],
            caveats=["Fixture data only."],
            source_backed_claims=[
                ResearchClaim(
                    claim="The macro snapshot is preserved.",
                    evidence_refs=[source.source_id],
                )
            ],
            inferred_claims=["Restart fidelity is proven by typed equality assertions."],
        ),
        sources=[source],
        tool_traces=[
            CopilotToolTrace(
                tool_name="get_macro_workspace_drilldown",
                summary="Loaded the persisted macro snapshot.",
                arguments={"theme": "inflation"},
                source_ids=[source.source_id],
            )
        ],
        operator_events=[
            CopilotOperatorProgressEvent(
                run_id="run_checkpoint3",
                event_id="evt_warning",
                sequence=2,
                event_type="warning",
                tool_id="get_macro_workspace_drilldown",
                message="One series is delayed.",
                source_ids=[source.source_id],
                warnings=["One series is delayed."],
            )
        ],
        warnings=["One series is delayed."],
    )


def test_checkpoint3_session_lifecycle_and_artifact_api_contract(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        created_turn = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Persist a lifecycle fixture.",
                "user_session_id": "session_checkpoint3_lifecycle",
                "role": "research_agent",
                "reasoning_effort": "high",
                "selected_scope_domains": ["macro"],
                "context": {
                    "current_tab": "macro",
                    "workspace_mode": "research",
                    "macro": {"mode": "snapshot", "region": "US", "timeframe": "3M", "theme": "inflation"},
                },
            },
        )
        assert created_turn.status_code == 200
        detail = client.get("/copilot/sessions/session_checkpoint3_lifecycle").json()
        original_updated_at = detail["session"]["updated_at"]
        turn_id = detail["turns"][0]["turn_id"]

        renamed = client.patch(
            "/copilot/sessions/session_checkpoint3_lifecycle",
            json={"title": "Renamed lifecycle session", "expected_updated_at": original_updated_at},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renamed lifecycle session"
        stale_rename = client.patch(
            "/copilot/sessions/session_checkpoint3_lifecycle",
            json={"title": "Stale rename", "expected_updated_at": original_updated_at},
        )
        assert stale_rename.status_code == 409

        archived = client.post("/copilot/sessions/session_checkpoint3_lifecycle/archive")
        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None
        restored = client.post("/copilot/sessions/session_checkpoint3_lifecycle/restore")
        assert restored.status_code == 200
        assert restored.json()["archived_at"] is None

        artifact = client.post(
            "/copilot/sessions/session_checkpoint3_lifecycle/artifacts",
            json={
                "artifact_type": "report",
                "template": "research_report",
                "title": "Lifecycle report",
                "source_turn_ids": [turn_id],
            },
        )
        assert artifact.status_code == 200
        artifact_payload = artifact.json()
        assert artifact_payload["source_turn_ids"] == [turn_id]
        assert artifact_payload["provider_metadata"][0]["reasoning_effort"] == "high"

        edited = client.patch(
            f"/copilot/artifacts/{artifact_payload['artifact_id']}",
            json={
                "title": "Edited lifecycle report",
                "body": "# Edited\n\nPersisted body.",
                "expected_updated_at": artifact_payload["updated_at"],
            },
        )
        assert edited.status_code == 200
        assert edited.json()["body"].endswith("Persisted body.")
        stale_edit = client.patch(
            f"/copilot/artifacts/{artifact_payload['artifact_id']}",
            json={"title": "Stale artifact edit", "expected_updated_at": artifact_payload["updated_at"]},
        )
        assert stale_edit.status_code == 409

        duplicate = client.post(
            f"/copilot/artifacts/{artifact_payload['artifact_id']}/duplicate",
            json={"title": "Lifecycle report copy"},
        )
        assert duplicate.status_code == 200
        duplicate_payload = duplicate.json()
        assert duplicate_payload["source_turn_ids"] == [turn_id]
        assert duplicate_payload["sources"] == artifact_payload["sources"]

        markdown = client.get(f"/copilot/artifacts/{artifact_payload['artifact_id']}/export")
        assert markdown.status_code == 200
        assert "## Source-Backed Claims" in markdown.text
        assert "## Provider and Model Metadata" in markdown.text
        assert f"- Source turns: {turn_id}" in markdown.text

        missing_confirmation = client.delete(f"/copilot/artifacts/{duplicate_payload['artifact_id']}")
        assert missing_confirmation.status_code == 422
        deleted_artifact = client.delete(
            f"/copilot/artifacts/{duplicate_payload['artifact_id']}",
            params={"confirm_artifact_id": duplicate_payload["artifact_id"]},
        )
        assert deleted_artifact.status_code == 200
        assert deleted_artifact.json()["recoverable"] is True

        wrong_session_confirmation = client.delete(
            "/copilot/sessions/session_checkpoint3_lifecycle",
            params={"confirm_session_id": "wrong"},
        )
        assert wrong_session_confirmation.status_code == 409
        deleted_session = client.delete(
            "/copilot/sessions/session_checkpoint3_lifecycle",
            params={"confirm_session_id": "session_checkpoint3_lifecycle"},
        )
        assert deleted_session.status_code == 200
        assert deleted_session.json()["deleted_counts"]["turns"] == 1
        assert client.get("/copilot/sessions/session_checkpoint3_lifecycle").status_code == 404
        assert client.get("/copilot/sessions/stale-session-id").status_code == 404
    finally:
        runtime.shutdown()


def test_checkpoint3_restart_replays_complete_turn_and_artifact_contract(tmp_path):
    store_dir = tmp_path / "copilot"
    store = CopilotStore(store_dir)
    result = _checkpoint3_persisted_result()
    research_plan = CopilotResearchPlan(
        intent="Replay all persisted research metadata.",
        domain_plan=[
            CopilotResearchPlanDomain(
                domain="macro",
                depth="deep",
                reason="Macro context is selected.",
                planned_tools=["get_macro_workspace_drilldown"],
                required_context=["macro"],
                estimated_tool_calls=1,
                estimated_provider_calls=1,
                estimated_latency_ms=25,
            )
        ],
        expected_artifacts=["research_report"],
    )
    operator_plan = CopilotOperatorPlan(
        intent="Persist an operator plan without broadening mutations.",
        research_plan=research_plan,
        steps=[
            CopilotOperatorPlanStep(
                step_id="step_1",
                order=1,
                title="Read macro context",
                domain="macro",
                action_type="read_context",
                tool_id="get_macro_workspace_drilldown",
                expected_artifacts=["research_report"],
            )
        ],
        max_tool_calls=1,
        max_provider_calls=1,
        max_elapsed_ms=100,
        expected_artifacts=["research_report"],
    )
    run_events = [
        CopilotRunEvent(
            run_id="run_checkpoint3",
            sequence=0,
            event_type="run.created",
            data={"role": "research_operator"},
        ),
        CopilotRunEvent(
            run_id="run_checkpoint3",
            sequence=1,
            event_type="usage",
            data={"input_tokens": 31, "output_tokens": 17, "total_tokens": 48},
        ),
        CopilotRunEvent(
            run_id="run_checkpoint3",
            sequence=2,
            event_type="completed",
            data={"status": "ready"},
            result=result,
        ),
    ]
    session, snapshot, turn = store.record_turn(
        session_id="session_checkpoint3_restart",
        title="Checkpoint 3 restart",
        domain="macro",
        current_tab="macro",
        workspace_mode="research",
        prompt="Prove restart fidelity.",
        context_fingerprint="fp_checkpoint3_macro",
        context_summary={"lens": "inflation"},
        request_context={"macro": {"theme": "inflation"}},
        selected_scope_domains=["macro", "prediction_markets"],
        role="research_operator",
        reasoning_effort="xhigh",
        requested_provider="openai",
        requested_model="requested-model",
        run_id="run_checkpoint3",
        terminal_status="ready",
        cancellation_outcome="not_cancelled",
        usage=CopilotUsageRecord(
            input_tokens=31,
            output_tokens=17,
            reasoning_tokens=5,
            total_tokens=53,
            provider_calls=1,
            tool_calls=1,
            raw={"provider_request_id": "redacted"},
        ),
        research_plan=research_plan,
        operator_plan=operator_plan,
        run_events=run_events,
        confirmations=[
            CopilotConfirmationState(
                checkpoint_id="confirm_1",
                status="pending",
                required_for_tool_ids=["local.memo.update"],
                mutation_id="mutation_1",
                confirmation_token="confirmation_local_only",
                rollback_snapshot_id="snapshot_rollback_1",
                warnings=["Local research-state confirmation only."],
            )
        ],
        artifact_refs=[
            CopilotArtifactReference(
                artifact_id="artifact_trace_1",
                artifact_type="research_report",
                status="created",
                mutation_id="mutation_1",
                rollback_snapshot_id="snapshot_rollback_1",
            )
        ],
        mutation_refs=[
            CopilotArtifactReference(
                artifact_id="mutation_1",
                artifact_type="local_research_mutation",
                status="pending",
                mutation_id="mutation_1",
                rollback_snapshot_id="snapshot_rollback_1",
            )
        ],
        result=result,
    )
    memo = store.create_artifact(
        session_id=session.session_id,
        artifact_type="memo",
        template="concise_memo",
        title="Restart memo",
        source_turn_ids=[turn.turn_id],
    )
    edited_memo = store.update_artifact(
        memo.artifact_id,
        title="Edited restart memo",
        body="# Edited restart memo\n\nThe exact edited body survives.",
        expected_updated_at=memo.updated_at,
    )
    report = store.create_artifact(
        session_id=session.session_id,
        artifact_type="report",
        template="research_report",
        title="Restart report",
        source_turn_ids=[turn.turn_id],
        source_memo_ids=[memo.artifact_id],
    )

    restarted = CopilotStore(store_dir)
    restored_turn = restarted.list_turns(session.session_id)[0]
    restored_snapshot = restarted.get_context_snapshot(snapshot.snapshot_id)
    restored_artifacts = {item.artifact_id: item for item in restarted.list_artifacts(session.session_id)}

    assert restored_turn.role == "research_operator"
    assert restored_turn.reasoning_effort == "xhigh"
    assert restored_turn.selected_scope_domains == ["macro", "prediction_markets"]
    assert restored_turn.context_fingerprint == "fp_checkpoint3_macro"
    assert restored_turn.requested_provider == "openai"
    assert restored_turn.requested_model == "requested-model"
    assert restored_turn.resolved_provider == "stub_provider"
    assert restored_turn.resolved_model == "stub-model-v3"
    assert restored_turn.run_id == "run_checkpoint3"
    assert restored_turn.terminal_status == "ready"
    assert restored_turn.cancellation_outcome == "not_cancelled"
    assert restored_turn.usage.total_tokens == 53
    assert restored_turn.research_plan == research_plan
    assert restored_turn.operator_plan == operator_plan
    assert [event.event_type for event in restored_turn.run_events] == [
        "run.created",
        "usage",
        "completed",
    ]
    assert restored_turn.run_events[-1].result == result
    assert restored_turn.confirmations[0].status == "pending"
    assert restored_turn.confirmations[0].rollback_snapshot_id == "snapshot_rollback_1"
    assert restored_turn.artifact_refs[0].artifact_id == "artifact_trace_1"
    assert restored_turn.mutation_refs[0].mutation_id == "mutation_1"
    assert restored_turn.trace_state.replay_complete is True
    assert restored_snapshot is not None
    assert restored_snapshot.request_context == {"macro": {"theme": "inflation"}}
    assert restored_snapshot.selected_scope_domains == ["macro", "prediction_markets"]
    assert restored_artifacts[memo.artifact_id].body == edited_memo.body
    assert restored_artifacts[report.artifact_id].source_memo_ids == [memo.artifact_id]
    assert restored_artifacts[report.artifact_id].source_turn_ids == [turn.turn_id]
    assert restored_artifacts[report.artifact_id].source_backed_claims[0].evidence_refs == [
        "macro.checkpoint3"
    ]
    assert restored_artifacts[report.artifact_id].warnings == ["One series is delayed."]
    assert restored_artifacts[report.artifact_id].provider_metadata[0].requested_model == "requested-model"
    markdown = restarted.export_artifact_markdown(report.artifact_id)
    assert "The macro snapshot is preserved. [macro.checkpoint3]" in markdown
    assert "One series is delayed." in markdown
    assert "requested-model" in markdown
    assert "get_macro_workspace_drilldown" in markdown
    assert turn.turn_id in markdown
    assert memo.artifact_id in markdown


def test_checkpoint3_migrates_every_legacy_version_idempotently(tmp_path):
    base_dir = tmp_path / "copilot"
    store = CopilotStore(base_dir)
    timestamp = "2026-07-24T10:00:00"
    for version in (0, 1, 2):
        session_id = f"legacy_session_v{version}"
        payload = {
            "schema_version": version,
            "session_id": session_id,
            "title": f"Legacy {version}",
            "created_at": timestamp,
            "updated_at": timestamp,
            "turn_count": 0,
            "memo_count": version,
            "warnings": [],
            "unknown_safe_field": {"preserved": version},
        }
        (store.sessions_dir / f"{session_id}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    migrated_store = CopilotStore(base_dir)
    migrated = migrated_store.list_sessions(include_archived=True)
    assert {item.session_id for item in migrated} == {
        "legacy_session_v0",
        "legacy_session_v1",
        "legacy_session_v2",
    }
    first_bytes: dict[str, str] = {}
    for version in (0, 1, 2):
        path = migrated_store.sessions_dir / f"legacy_session_v{version}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == CURRENT_COPILOT_STORE_SCHEMA_VERSION
        assert payload["report_count"] == 0
        assert payload["artifact_count"] == version
        assert payload["unknown_safe_field"] == {"preserved": version}
        first_bytes[path.name] = path.read_text(encoding="utf-8")

    repeated_store = CopilotStore(base_dir)
    repeated_store.list_sessions(include_archived=True)
    for name, content in first_bytes.items():
        assert (repeated_store.sessions_dir / name).read_text(encoding="utf-8") == content


def test_checkpoint3_migrates_nested_replay_and_artifact_records_from_every_legacy_version(tmp_path):
    base_dir = tmp_path / "copilot"
    store = CopilotStore(base_dir)
    fixtures: list[tuple[int, str, str, str]] = []
    replay_fields = {
        "role",
        "reasoning_effort",
        "selected_scope_domains",
        "context_fingerprint",
        "requested_provider",
        "requested_model",
        "resolved_provider",
        "resolved_model",
        "run_id",
        "terminal_status",
        "cancellation_outcome",
        "usage",
        "research_plan",
        "operator_plan",
        "run_events",
        "confirmations",
        "artifact_refs",
        "mutation_refs",
        "trace_state",
    }
    artifact_provenance_fields = {
        "source_memo_ids",
        "unavailable_source_turn_ids",
        "context_fingerprints",
        "source_backed_claims",
        "inferred_claims",
        "assumptions",
        "missing_data",
        "warning_provenance",
        "tool_trace_summary",
        "sources",
        "provider_metadata",
    }
    for version in (0, 1, 2):
        session, snapshot, turn = store.record_turn(
            session_id=f"nested_legacy_v{version}",
            title=f"Nested legacy {version}",
            domain="macro",
            current_tab="macro",
            workspace_mode="research",
            prompt="Migrate nested replay fields.",
            context_fingerprint=f"fp-v{version}",
            context_summary={},
            request_context={"macro": {"theme": "all"}},
            selected_scope_domains=["macro"],
            result=_checkpoint3_persisted_result(),
        )
        report = store.create_artifact(
            session_id=session.session_id,
            artifact_type="report",
            template="research_report",
            source_turn_ids=[turn.turn_id],
        )
        turn_path = store.turns_dir / session.session_id / f"{turn.turn_id}.json"
        snapshot_path = store.snapshots_dir / f"{snapshot.snapshot_id}.json"
        artifact_path = store.artifacts_dir / f"{report.artifact_id}.json"
        for path, removed_fields in (
            (turn_path, replay_fields),
            (snapshot_path, {"request_context", "selected_scope_domains"}),
            (artifact_path, artifact_provenance_fields),
        ):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["schema_version"] = version
            for field in removed_fields:
                payload.pop(field, None)
            path.write_text(json.dumps(payload), encoding="utf-8")
        fixtures.append((version, session.session_id, turn.turn_id, report.artifact_id))

    migrated = CopilotStore(base_dir)
    for version, session_id, turn_id, artifact_id in fixtures:
        restored_turn = migrated.list_turns(session_id)[0]
        restored_snapshot = migrated.get_context_snapshot(restored_turn.context_snapshot_id)
        restored_artifact = migrated.get_artifact(artifact_id)
        assert restored_turn.turn_id == turn_id
        assert restored_turn.role == "research_operator"
        assert restored_turn.usage.total_tokens == 0
        assert restored_turn.research_plan is None
        assert restored_turn.operator_plan is None
        assert restored_turn.run_events == []
        assert restored_turn.confirmations == []
        assert restored_turn.artifact_refs == []
        assert restored_turn.mutation_refs == []
        assert restored_turn.trace_state.replay_complete is True
        assert restored_snapshot is not None
        assert restored_snapshot.request_context == {}
        assert restored_snapshot.selected_scope_domains == []
        assert restored_artifact is not None
        assert restored_artifact.artifact_type == "report"
        assert restored_artifact.provider_metadata == []
        for path in (
            migrated.turns_dir / session_id / f"{turn_id}.json",
            migrated.snapshots_dir / f"{restored_turn.context_snapshot_id}.json",
            migrated.artifacts_dir / f"{artifact_id}.json",
        ):
            assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == (
                CURRENT_COPILOT_STORE_SCHEMA_VERSION
            ), version


def test_checkpoint3_recovers_mixed_corruption_future_and_interrupted_writes(tmp_path):
    base_dir = tmp_path / "copilot"
    store = CopilotStore(base_dir)
    timestamp = "2026-07-24T10:00:00"
    healthy_payload = {
        "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION,
        "session_id": "healthy_session",
        "title": "Healthy session",
        "created_at": timestamp,
        "updated_at": timestamp,
        "turn_count": 0,
        "memo_count": 0,
        "report_count": 0,
        "artifact_count": 0,
        "warnings": [],
    }
    (store.sessions_dir / "healthy_session.json").write_text(
        json.dumps(healthy_payload),
        encoding="utf-8",
    )
    malformed_path = store.sessions_dir / "malformed_session.json"
    malformed_path.write_text('{"schema_version": 1,', encoding="utf-8")
    future_path = store.sessions_dir / "future_session.json"
    future_payload = {
        **healthy_payload,
        "schema_version": CURRENT_COPILOT_STORE_SCHEMA_VERSION + 1,
        "session_id": "future_session",
        "title": "Future session",
    }
    future_text = json.dumps(future_payload)
    future_path.write_text(future_text, encoding="utf-8")
    partial_payload = {
        **healthy_payload,
        "session_id": "partial_session",
    }
    partial_payload.pop("title")
    (store.sessions_dir / "partial_session.json").write_text(
        json.dumps(partial_payload),
        encoding="utf-8",
    )
    interrupted_payload = {
        **healthy_payload,
        "session_id": "interrupted_session",
        "title": "Recovered interrupted session",
    }
    interrupted_temp = store.sessions_dir / "interrupted_session.json.tmp"
    interrupted_temp.write_text(json.dumps(interrupted_payload), encoding="utf-8")

    recovered = CopilotStore(base_dir)
    loaded_ids = {
        item.session_id for item in recovered.list_sessions(include_archived=True)
    }
    assert loaded_ids == {"healthy_session", "interrupted_session", "partial_session"}
    assert recovered.get_session("partial_session").title == "Copilot Session"
    assert not malformed_path.exists()
    quarantine_files = list((base_dir / "quarantine" / "session").glob("malformed_session.json.*.preserved"))
    assert quarantine_files
    assert quarantine_files[0].read_text(encoding="utf-8") == '{"schema_version": 1,'
    assert future_path.exists()
    assert future_path.read_text(encoding="utf-8") == future_text
    assert not interrupted_temp.exists()
    assert (store.sessions_dir / "interrupted_session.json").exists()
    actions = {warning.action for warning in recovered.storage_status().warnings}
    assert "recovered_interrupted_write" in actions
    assert "quarantined" in actions
    assert "skipped_future_version" in actions
    assert "recovered_partial_record" in actions


def test_checkpoint3_artifact_reopen_never_resurrects_invalid_evidence_and_flags_missing_turns(tmp_path):
    base_dir = tmp_path / "copilot"
    store = CopilotStore(base_dir)
    session, _snapshot, turn = store.record_turn(
        session_id="session_evidence_reopen",
        title="Evidence reopen",
        domain="macro",
        current_tab="macro",
        workspace_mode="research",
        prompt="Preserve only valid evidence.",
        context_fingerprint="fp-evidence",
        context_summary={},
        selected_scope_domains=["macro"],
        result=_checkpoint3_persisted_result(),
    )
    artifact = store.create_artifact(
        session_id=session.session_id,
        artifact_type="report",
        template="research_report",
        source_turn_ids=[turn.turn_id],
    )
    artifact_path = store.artifacts_dir / f"{artifact.artifact_id}.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["source_backed_claims"].append(
        {"claim": "This claim has a fabricated citation.", "evidence_refs": ["fake.source"]}
    )
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    reopened = CopilotStore(base_dir)
    normalized = reopened.get_artifact(artifact.artifact_id)
    assert normalized is not None
    assert all(
        "fake.source" not in claim.evidence_refs
        for claim in normalized.source_backed_claims
    )
    assert "This claim has a fabricated citation." in normalized.inferred_claims
    assert any("Reclassified artifact claim" in warning for warning in normalized.warnings)
    edited = reopened.update_artifact(
        artifact.artifact_id,
        title="Normalized evidence report",
        body="# Normalized\n\nEdited without changing provenance.",
        expected_updated_at=normalized.updated_at,
    )
    duplicated = reopened.duplicate_artifact(edited.artifact_id)
    assert all(
        "fake.source" not in claim.evidence_refs
        for claim in duplicated.source_backed_claims
    )
    assert "fake.source" not in reopened.export_artifact_markdown(duplicated.artifact_id)

    turn_path = reopened.turns_dir / session.session_id / f"{turn.turn_id}.json"
    turn_path.unlink()
    unavailable = reopened.get_artifact(artifact.artifact_id)
    assert unavailable is not None
    assert unavailable.unavailable_source_turn_ids == [turn.turn_id]
    assert artifact_path.exists()


def test_new_chat_creates_one_authoritative_empty_session(tmp_path):
    """`New chat` must produce a real, selectable, empty session record."""
    store = CopilotStore(tmp_path / "copilot")

    created = store.create_session()

    assert created.turn_count == 0
    assert created.artifact_count == 0
    assert created.archived_at is None
    assert store.get_session(created.session_id) == created
    assert [item.session_id for item in store.list_sessions()] == [created.session_id]

    # A second activation with the same id reattaches instead of duplicating.
    repeated = store.create_session(session_id=created.session_id)
    assert repeated.session_id == created.session_id
    assert repeated.created_at == created.created_at
    assert len(store.list_sessions()) == 1

    # The blank session survives a process restart.
    reopened = CopilotStore(tmp_path / "copilot")
    assert reopened.get_session(created.session_id) is not None
    assert [item.session_id for item in reopened.list_sessions()] == [created.session_id]


def test_new_chat_session_stays_selectable_alongside_existing_sessions(tmp_path):
    store = CopilotStore(tmp_path / "copilot")
    existing, _, _ = store.record_turn(
        session_id="session_existing",
        title="Existing conversation",
        domain="macro",
        current_tab="macro",
        workspace_mode="research",
        prompt="Keep this conversation available.",
        context_fingerprint="macro:US:3M",
        context_summary={},
        result=CopilotResearchCardResult(
            domain="macro",
            current_tab="macro",
            status="ready",
            provider="mock",
            model="gamma-mock",
            response_id="resp_existing",
        ),
    )
    archived_session = store.create_session(title="Archived conversation", session_id="session_archived")
    store.archive_session(archived_session.session_id)

    blank = store.create_session(title="New chat", session_id="session_blank")

    normal = [item.session_id for item in store.list_sessions()]
    assert blank.session_id in normal
    assert existing.session_id in normal
    assert archived_session.session_id not in normal
    with_archived = [item.session_id for item in store.list_sessions(include_archived=True)]
    assert archived_session.session_id in with_archived
    # The blank session accepts its first turn without losing identity.
    updated, _, turn = store.record_turn(
        session_id=blank.session_id,
        title=None,
        domain="macro",
        current_tab="macro",
        workspace_mode="research",
        prompt="First prompt in the new conversation.",
        context_fingerprint="macro:US:3M",
        context_summary={},
        result=CopilotResearchCardResult(
            domain="macro",
            current_tab="macro",
            status="ready",
            provider="mock",
            model="gamma-mock",
            response_id="resp_blank_1",
        ),
    )
    assert updated.session_id == blank.session_id
    assert updated.title == "New chat"
    assert turn.turn_index == 0


def test_create_session_route_is_authoritative_and_idempotent(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        seeded = client.post(
            "/copilot/research-card",
            json={
                "domain": "macro",
                "prompt": "Seed an existing conversation.",
                "user_session_id": "session_new_chat_existing",
                "role": "research_agent",
                "selected_scope_domains": ["macro"],
                "context": {
                    "current_tab": "macro",
                    "workspace_mode": "research",
                    "macro": {"mode": "snapshot", "region": "US", "timeframe": "3M", "theme": "inflation"},
                },
            },
        )
        assert seeded.status_code == 200

        created = client.post("/copilot/sessions", json={"session_id": "session_new_chat_blank"})
        assert created.status_code == 200
        payload = created.json()
        assert payload["session_id"] == "session_new_chat_blank"
        assert payload["turn_count"] == 0
        assert payload["archived_at"] is None

        # Selecting the brand-new session must not 404 into the existing one.
        detail = client.get("/copilot/sessions/session_new_chat_blank")
        assert detail.status_code == 200
        assert detail.json()["turns"] == []
        assert detail.json()["artifacts"] == []

        duplicate = client.post("/copilot/sessions", json={"session_id": "session_new_chat_blank"})
        assert duplicate.status_code == 200
        assert duplicate.json()["created_at"] == payload["created_at"]

        listed = [item["session_id"] for item in client.get("/copilot/sessions").json()]
        assert "session_new_chat_blank" in listed
        assert "session_new_chat_existing" in listed
        assert len([item for item in listed if item == "session_new_chat_blank"]) == 1

        rejected = client.post("/copilot/sessions", json={"session_id": "///"})
        assert rejected.status_code == 400
    finally:
        runtime.shutdown()


def _checkpoint5_context_request(
    *,
    supplied_fingerprint: str | None = None,
) -> CopilotResearchCardRequest:
    return CopilotResearchCardRequest(
        domain="portfolio",
        prompt="Inspect this read-only research book.",
        context_fingerprint=supplied_fingerprint,
        context=CopilotRequestContext(
            current_tab="portfolio",
            workspace_mode="research_book",
            portfolio_state={
                "account_scope": "research-book-alpha",
                "selected_entity": "NVDA",
            },
        ),
    )


def _checkpoint5_context_bundle(
    *,
    retrieved_at: datetime,
    summary: dict | None = None,
    warnings: list[str] | None = None,
) -> CopilotContextBundle:
    return CopilotContextBundle(
        domain="portfolio",
        current_tab="portfolio",
        summary_data=summary
        or {
            "workspace_mode": "research_book",
            "account_scope": "research-book-alpha",
            "selected_entity": "NVDA",
            "timeframe": "1Y",
            "coverage": {"status": "ready"},
        },
        sources=[
            CopilotSourceRef(
                source_id="portfolio.snapshot",
                label="Research-book snapshot",
                kind="workspace",
                provider="gamma",
                origin="gamma.portfolio.snapshot",
                retrieved_at=retrieved_at,
                navigation_supported=True,
                navigation_tab="portfolio",
                navigation_mode="research_book",
                navigation_context={
                    "account_scope": "research-book-alpha",
                    "symbol": "NVDA",
                },
            )
        ],
        warnings=list(warnings or ["Research-book boundary preserved."]),
    )


def test_checkpoint5_context_fingerprint_is_canonical_and_invalidates_on_change():
    retrieved_at = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)
    request = _checkpoint5_context_request()
    first = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=retrieved_at,
            summary={
                "selected_entity": "NVDA",
                "coverage": {"status": "ready", "provider": "gamma"},
                "timeframe": "1Y",
                "workspace_mode": "research_book",
                "account_scope": "research-book-alpha",
            },
        ),
        request,
    )
    equivalent = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=retrieved_at,
            summary={
                "account_scope": "research-book-alpha",
                "workspace_mode": "research_book",
                "timeframe": "1Y",
                "coverage": {"provider": "gamma", "status": "ready"},
                "selected_entity": "NVDA",
            },
        ),
        request,
    )

    assert first.context_contract is not None
    assert equivalent.context_contract is not None
    assert (
        first.context_contract.context_fingerprint
        == equivalent.context_contract.context_fingerprint
    )
    changed = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=retrieved_at + timedelta(minutes=5),
            summary={
                **first.summary_data,
                "timeframe": "3M",
            },
        ),
        _checkpoint5_context_request(
            supplied_fingerprint=first.context_contract.context_fingerprint,
        ),
    )
    assert changed.context_contract is not None
    assert (
        changed.context_contract.context_fingerprint
        != first.context_contract.context_fingerprint
    )
    assert changed.context_contract.freshness.status == "invalidated"
    assert (
        changed.context_contract.freshness.invalidated_fingerprint
        == first.context_contract.context_fingerprint
    )


def test_checkpoint5_context_budget_compacts_deterministically_and_discloses_omissions():
    retrieved_at = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)
    oversized = {
        "workspace_mode": "research_book",
        "account_scope": "research-book-alpha",
        "selected_entity": "NVDA",
        "timeframe": "1Y",
        "warnings_detail": {
            f"row_{index:04d}": {
                "status": "degraded" if index % 5 == 0 else "ready",
                "source_ids": [f"source.{index}"],
                "transformation_note": "normalized " + ("x" * 260),
            }
            for index in range(700)
        },
        "api_key": "must-not-survive",
    }
    request = _checkpoint5_context_request()
    first = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=retrieved_at,
            summary=oversized,
            warnings=["Sparse provider coverage.", "Freshness is delayed."],
        ),
        request,
    )
    second = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=retrieved_at,
            summary=deepcopy(oversized),
            warnings=["Sparse provider coverage.", "Freshness is delayed."],
        ),
        request,
    )

    assert first.context_contract is not None
    assert second.context_contract is not None
    contract = first.context_contract
    assert contract.compaction.applied is True
    assert contract.compaction.omitted_sections
    assert contract.budget.original_bytes > contract.budget.scope_budget_bytes
    assert contract.budget.final_bytes <= COPILOT_SCOPE_CONTEXT_BUDGET_BYTES["portfolio"]
    assert contract.budget.within_scope_budget is True
    assert first.summary_data == second.summary_data
    assert contract.context_fingerprint == second.context_contract.context_fingerprint
    assert "api_key" not in json.dumps(first.summary_data)
    assert any("compacted deterministically" in warning for warning in first.warnings)
    assert first.sources[0].source_id == "portfolio.snapshot"


def test_checkpoint5_context_plan_and_omission_contract_survive_restart(tmp_path):
    finalized = finalize_context_bundle(
        _checkpoint5_context_bundle(
            retrieved_at=datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc),
        ),
        _checkpoint5_context_request(),
    )
    assert finalized.context_contract is not None
    plan = CopilotResearchPlan(
        intent="portfolio_rate_shock",
        domain_plan=[
            CopilotResearchPlanDomain(
                domain="portfolio",
                depth="deep",
                reason="The active research-book exposure is first-order.",
                planned_tools=["get_portfolio_positions_summary"],
            )
        ],
        domain_decisions=[
            CopilotResearchPlanDomainDecision(
                domain="portfolio",
                used=True,
                reason="Selected for bounded exposure context.",
                classification="selected",
                selected_depth="deep",
                planned_tools=["get_portfolio_positions_summary"],
            ),
            CopilotResearchPlanDomainDecision(
                domain="iv",
                used=False,
                reason="Options context is irrelevant to this bounded rate-shock request.",
                classification="irrelevant",
            ),
        ],
    )
    result = CopilotResearchCardResult(
        domain="portfolio",
        current_tab="portfolio",
        status="ready",
        provider="gamma_executor",
        card=ResearchCard(
            title="Rate shock",
            hypothesis="Research-book duration exposure is material.",
            rationale="Read-only portfolio and macro context.",
            required_data=[],
            proposed_test="Run the bounded scenario.",
            confounders=[],
            next_steps=[],
            caveats=[],
        ),
        sources=list(finalized.sources),
        warnings=list(finalized.warnings),
        research_plan=plan,
        context_contracts=[finalized.context_contract],
        context_budget={
            "total_budget_bytes": COPILOT_TOTAL_CONTEXT_BUDGET_BYTES,
            "used_bytes": finalized.context_contract.budget.final_bytes,
            "within_total_budget": True,
            "omitted_domains": [],
        },
    )
    store_dir = tmp_path / "copilot-checkpoint5"
    store = CopilotStore(store_dir)
    session, snapshot, _turn = store.record_turn(
        session_id="session_checkpoint5",
        title="Checkpoint 5 replay",
        domain="portfolio",
        current_tab="portfolio",
        workspace_mode="research_book",
        prompt="Portfolio rate shock",
        context_fingerprint=finalized.context_contract.context_fingerprint,
        context_summary={
            "context_contract": finalized.context_contract.to_dict(),
            "account_scope": "research-book-alpha",
        },
        request_context={"account_scope": "research-book-alpha"},
        selected_scope_domains=["portfolio", "risk", "macro"],
        research_plan=plan,
        result=result,
    )

    restarted = CopilotStore(store_dir)
    restored = restarted.list_turns(session.session_id)[0]
    restored_snapshot = restarted.get_context_snapshot(snapshot.snapshot_id)
    assert restored.research_plan == plan
    assert restored.result.research_plan == plan
    assert (
        restored.result.context_contracts[0].context_fingerprint
        == finalized.context_contract.context_fingerprint
    )
    assert restored.result.context_budget["within_total_budget"] is True
    assert restored_snapshot is not None
    assert (
        restored_snapshot.context_contract["context_fingerprint"]
        == finalized.context_contract.context_fingerprint
    )


def test_checkpoint5_total_context_budget_omits_low_priority_domain_deterministically(
    tmp_path,
    monkeypatch,
):
    client, runtime = _build_test_client(tmp_path)
    del client
    try:
        service = runtime.copilot_service
        request = CopilotResearchCardRequest(
            domain="synthesis",
            prompt="Run a bounded four-domain context test.",
            context=CopilotRequestContext(
                current_tab="copilot",
                workspace_mode="research",
            ),
        )
        domain_tools = {
            "portfolio": "get_portfolio_positions_summary",
            "risk": "run_risk_contribution_analysis",
            "iv": "inspect_options_structure",
            "macro": "get_macro_workspace_drilldown",
        }
        payload_sizes = {
            "portfolio": 24_000,
            "risk": 30_000,
            "iv": 30_000,
            "macro": 20_000,
        }
        bundles = {
            domain: finalize_context_bundle(
                CopilotContextBundle(
                    domain=domain,
                    current_tab=domain,
                    summary_data={
                        "workspace_mode": "research",
                        "status": "ready",
                        "payload": character * payload_sizes[domain],
                    },
                    sources=[
                        CopilotSourceRef(
                            source_id=f"{domain}.budget_fixture",
                            label=f"{domain} budget fixture",
                            kind="workspace",
                            provider="fixture",
                            origin=f"tests.{domain}.budget",
                            retrieved_at=datetime(
                                2026,
                                7,
                                25,
                                10,
                                0,
                                tzinfo=timezone.utc,
                            ),
                            navigation_supported=False,
                            navigation_reason="Synthetic budget fixture.",
                        )
                    ],
                ),
                replace(request, domain=domain),
            )
            for domain, character in zip(
                domain_tools,
                ("p", "r", "i", "m"),
                strict=True,
            )
        }
        plan_domains = [
            CopilotResearchPlanDomain(
                domain=domain,
                depth="medium",
                reason=f"{domain} is relevant to the bounded fixture.",
                planned_tools=[tool_id],
            )
            for domain, tool_id in domain_tools.items()
        ]
        plan = CopilotResearchPlan(
            intent="checkpoint5_total_budget",
            domain_plan=plan_domains,
            domain_decisions=[
                CopilotResearchPlanDomainDecision(
                    domain=item.domain,
                    used=True,
                    reason=item.reason,
                    classification="selected",
                    selected_depth=item.depth,
                    planned_tools=list(item.planned_tools),
                )
                for item in plan_domains
            ],
            max_tool_calls=10,
            max_provider_calls=1,
            max_elapsed_ms=12_000,
        )
        monkeypatch.setattr(service, "plan_research", lambda _request: plan)
        monkeypatch.setattr(
            service,
            "_build_plan_execution_context",
            lambda _request, domain: bundles[domain],
        )

        def execute_fixture(tool_id, arguments, context):
            source = context.sources[0]
            return CopilotToolExecution(
                output={
                    "status": "ready",
                    "domain": context.domain,
                    "source_ids": [source.source_id],
                    "warnings": [],
                },
                trace=CopilotToolTrace(
                    tool_name=tool_id,
                    summary=f"Executed {context.domain} budget fixture.",
                    arguments=arguments,
                    source_ids=[source.source_id],
                ),
                sources=[source],
            )

        monkeypatch.setattr(service, "_execute_tool", execute_fixture)
        result = service.execute_research_plan(request)
        assert result.status == "ready"
        assert result.context_budget["within_total_budget"] is True
        assert result.context_budget["used_bytes"] <= COPILOT_TOTAL_CONTEXT_BUDGET_BYTES
        assert result.context_budget["omitted_domains"] == [
            {"domain": "macro", "reason": "budget_omission"}
        ]
        assert result.research_plan is not None
        macro = next(
            decision
            for decision in result.research_plan.domain_decisions
            if decision.domain == "macro"
        )
        assert macro.used is False
        assert macro.classification == "budget_omission"
        assert all(
            contract.budget.within_scope_budget
            for contract in result.context_contracts
        )
    finally:
        runtime.shutdown()


def test_checkpoint5_new_drilldowns_are_registry_authorized_read_only_actions(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        definitions = {
            item.tool_id: item
            for item in runtime.copilot_service.list_research_action_definitions()
        }
        tool_ids = {
            "inspect_equity_research_context",
            "inspect_commodity_curve_fundamentals",
            "get_maritime_chokepoint_context",
            "get_maritime_route_context",
            "inspect_options_structure",
            "get_news_items_context",
        }
        assert tool_ids <= definitions.keys()
        for tool_id in tool_ids:
            definition = definitions[tool_id]
            assert definition.read_only is True
            assert definition.mutates_local_state is False
            assert definition.requires_confirmation is False
            assert definition.permission_policy == "automatic"
            assert definition.input_schema["type"] == "object"
            assert definition.output_schema["type"] == "object"
            assert definition.provenance_behavior
            assert definition.failure_modes
            authorized = (
                runtime.copilot_service.action_registry.authorize_automatic(tool_id)
            )
            assert authorized.tool_id == tool_id
    finally:
        runtime.shutdown()


def test_checkpoint5_maritime_and_news_provider_absence_are_typed_unavailable(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        runtime.copilot_service.maritime_service = None
        maritime_request = CopilotResearchCardRequest(
            domain="maritime",
            prompt="Inspect Hormuz and do not infer cargo or operational risk.",
            context=CopilotRequestContext(
                current_tab="maritime",
                workspace_mode="chokepoints",
            ),
        )
        maritime_context = runtime.copilot_service._build_plan_execution_context(
            maritime_request,
            "maritime",
        )
        chokepoints = runtime.copilot_service._execute_tool(
            "get_maritime_chokepoint_context",
            {"chokepoint_id": "strait-of-hormuz", "max_rows": 4},
            maritime_context,
        )
        routes = runtime.copilot_service._execute_tool(
            "get_maritime_route_context",
            {"route_id": None, "max_rows": 4},
            maritime_context,
        )
        assert chokepoints.output["status"] == "unavailable"
        assert chokepoints.output["chokepoints"] == []
        assert routes.output["status"] == "unavailable"
        assert routes.output["routes"] == []
        assert all(source.navigation_supported is False for source in maritime_context.sources)
        assert any("not inferred" in warning.lower() for warning in maritime_context.warnings)

        runtime.copilot_service.news_service = None
        news_request = CopilotResearchCardRequest(
            domain="external_context",
            prompt="Recent oil-disruption news.",
            context=CopilotRequestContext(
                current_tab="copilot",
                workspace_mode="research",
            ),
        )
        news_context = runtime.copilot_service._build_plan_execution_context(
            news_request,
            "external_context",
        )
        news = runtime.copilot_service._execute_tool(
            "get_news_items_context",
            {"limit": 8},
            news_context,
        )
        assert news.output["status"] == "unavailable"
        assert news.output["items"] == []
        assert any(
            "missing coverage" in warning.lower()
            or "no newsservice" in warning.lower()
            for warning in news.output["warnings"]
        )
        unavailable_source = next(
            source
            for source in news.sources
            if source.source_id == "external_context.news_feed"
        )
        assert unavailable_source.provider == "unavailable"
        assert unavailable_source.navigation_supported is False
    finally:
        runtime.shutdown()


def test_checkpoint5_priority_drilldowns_preserve_provenance_and_navigation(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    del client
    try:
        retrieved_at = "2026-07-25T10:00:00+00:00"
        equity_request = CopilotResearchCardRequest(
            domain="equity_research",
            prompt="Research NVDA",
            context=CopilotRequestContext(
                current_tab="equity_research",
                workspace_mode="research",
                research_state={
                    "result": {
                        "scope_type": "single_ticker",
                        "primary_symbol": "NVDA",
                        "benchmark_symbol": "SPY",
                        "lookback_days": 252,
                        "observations_count": 252,
                        "summary": {"total_return": 0.18},
                        "structure": {"position_count": 1},
                        "coverage": {"missing_symbols": []},
                        "weights": [{"symbol": "NVDA", "weight": 1.0}],
                        "constituents": [
                            {
                                "symbol": "NVDA",
                                "weight": 1.0,
                                "total_return": 0.18,
                                "weighted_return": 0.18,
                            }
                        ],
                        "performance_points": [{"timestamp": retrieved_at, "value": 1.18}],
                        "source_provider": "mock_research",
                        "origin": "gamma.research.analyze",
                        "warnings": [],
                    }
                },
            ),
        )
        equity_context = runtime.copilot_service._build_plan_execution_context(
            equity_request,
            "equity_research",
        )
        equity = runtime.copilot_service._execute_tool(
            "inspect_equity_research_context",
            {"symbol": "NVDA", "max_rows": 6},
            equity_context,
        )
        assert equity.output["status"] == "ready"
        assert equity.output["symbol"] == "NVDA"
        assert equity.output["timeframe"] == 252
        assert equity.sources[0].provider == "mock_research"
        assert equity.sources[0].provider_native_id == "NVDA"
        assert equity.sources[0].navigation_supported is True
        assert equity.sources[0].navigation_context == {
            "symbol": "NVDA",
            "timeframe": "252",
        }

        commodities_workspace = {
            "mode": "curves_spreads",
            "selected_instrument_id": "wti",
            "source_provider": "mock_commodities",
            "origin": "gamma.commodities.workspace",
            "retrieved_at": retrieved_at,
            "coverage": {
                "provider_id": "mock_commodities",
                "provider_label": "Mock commodities",
                "coverage_status": "live",
                "freshness_label": "live",
                "source_timestamp": retrieved_at,
                "retrieved_at": retrieved_at,
                "caveats": [],
            },
            "instruments": [{"instrument_id": "wti"}],
            "market_summaries": [],
            "spreads": [],
            "curves": [
                {
                    "instrument_id": "wti",
                    "as_of": retrieved_at,
                    "shape_label": "backwardation",
                    "front_spread": 1.2,
                    "nodes": [
                        {
                            "contract": {
                                "contract_id": "CL-2026-09",
                                "symbol": "CLU6",
                                "contract_month": "2026-09",
                                "expiry_date": "2026-08-20",
                                "is_front_month": True,
                            },
                            "price": 82.5,
                            "days_to_expiry": 26,
                            "source_provider": "mock_commodities",
                            "retrieved_at": retrieved_at,
                            "origin": "mock.curve",
                            "transformation_note": "Normalized provider contract.",
                        }
                    ],
                    "source_provider": "mock_commodities",
                    "retrieved_at": retrieved_at,
                    "origin": "gamma.commodities.curve_analytics",
                    "transformation_note": "Existing Gamma curve analytics.",
                    "warnings": [],
                }
            ],
            "inventories": [
                {
                    "metadata": {
                        "series_id": "eia-crude-stocks",
                        "provider_series_id": "PET.WCESTUS1.W",
                        "instrument_id": "wti",
                        "label": "US crude stocks",
                        "unit": "thousand barrels",
                        "frequency": "weekly",
                        "source_provider": "eia",
                        "retrieved_at": retrieved_at,
                        "origin": "gamma.commodities.inventory",
                    },
                    "latest_value": 420000,
                    "points": [
                        {"timestamp": "2026-07-18T00:00:00+00:00", "value": 420000}
                    ],
                    "source_provider": "eia",
                    "retrieved_at": retrieved_at,
                    "origin": "gamma.commodities.inventory",
                    "transformation_note": "Provider-native weekly series.",
                    "warnings": [],
                }
            ],
            "events": [
                {
                    "event_id": "eia-weekly",
                    "title": "EIA weekly petroleum status",
                    "category": "inventory",
                    "scheduled_at": "2026-07-29T14:30:00+00:00",
                    "importance": "high",
                    "linked_instrument_ids": ["wti"],
                    "source_provider": "eia",
                    "retrieved_at": retrieved_at,
                    "origin": "gamma.commodities.events",
                }
            ],
            "cross_domain_links": [],
            "price_reconciliations": [
                {
                    "instrument_id": "wti",
                    "status": "aligned",
                    "warnings": [],
                }
            ],
            "warnings": [],
        }
        commodities_request = CopilotResearchCardRequest(
            domain="commodities",
            prompt="Inspect WTI curve and inventories.",
            context=CopilotRequestContext(
                current_tab="commodities",
                workspace_mode="curves_spreads",
                commodities_state={"workspace": commodities_workspace},
            ),
        )
        commodities_context = runtime.copilot_service._build_plan_execution_context(
            commodities_request,
            "commodities",
        )
        commodities = runtime.copilot_service._execute_tool(
            "inspect_commodity_curve_fundamentals",
            {
                "instrument_id": "wti",
                "max_curve_nodes": 6,
                "max_inventory_points": 4,
            },
            commodities_context,
        )
        assert commodities.output["status"] == "ready"
        assert commodities.output["curve"]["nodes"][0]["contract_id"] == "CL-2026-09"
        assert (
            commodities.output["inventories"][0]["provider_series_id"]
            == "PET.WCESTUS1.W"
        )
        assert commodities.output["assumptions"]
        assert any(
            source.provider_native_id == "PET.WCESTUS1.W"
            and source.navigation_mode == "inventories_fundamentals"
            for source in commodities.sources
        )

        iv_surface = {
            "symbol": "NVDA",
            "timestamp": retrieved_at,
            "retrieved_at": retrieved_at,
            "snapshot_available": True,
            "spot": 125.0,
            "expiries": ["2026-08-21"],
            "strikes": [120.0, 125.0, 130.0],
            "iv_grid": [[0.42, 0.40, 0.41]],
            "delayed": False,
            "warnings": [],
            "source_provider": "mock_options",
            "origin": "gamma.iv.surface",
            "freshness_label": "live",
            "surface_model": "linear",
            "surface_model_status": "applied",
            "surface_model_notes": ["No extrapolation beyond quoted strikes."],
            "pricing_assumptions": {
                "risk_free_rate": 0.04,
                "dividend_yield": 0.0,
            },
            "expiry_analytics": [
                {
                    "expiry": "2026-08-21",
                    "atm_strike": 125.0,
                    "atm_blended_implied_volatility": 0.40,
                    "historical_volatility": 0.32,
                    "implied_move": 0.08,
                    "quality": "complete",
                    "source_provider": "mock_options",
                    "retrieved_at": retrieved_at,
                    "origin": "gamma.iv.expiry_analytics",
                    "transformation_note": "Normalized listed contracts.",
                    "warnings": [],
                }
            ],
            "contracts": [
                {
                    "contract_id": "NVDA-20260821-C-125",
                    "provider_contract_id": "conid-123",
                    "expiry": "2026-08-21",
                    "strike": 125.0,
                    "right": "C",
                }
            ],
        }
        iv_request = CopilotResearchCardRequest(
            domain="iv",
            prompt="Inspect NVDA options structure.",
            context=CopilotRequestContext(
                current_tab="iv",
                workspace_mode="surface",
                iv_state={
                    "target_symbol": "NVDA",
                    "surface": iv_surface,
                    "session": {"market_data_mode": "live"},
                },
            ),
        )
        iv_context = runtime.copilot_service._build_plan_execution_context(
            iv_request,
            "iv",
        )
        iv = runtime.copilot_service._execute_tool(
            "inspect_options_structure",
            {"symbol": "NVDA", "expiry": None, "max_expiries": 4},
            iv_context,
        )
        assert iv.output["status"] == "ready"
        assert iv.output["surface_model"] == "linear"
        assert iv.output["pricing_assumptions"]["risk_free_rate"] == 0.04
        assert iv.output["expiries"][0]["provider_contract_ids"] == ["conid-123"]
        expiry_source = next(
            source for source in iv.sources if source.kind == "iv_expiry"
        )
        assert expiry_source.navigation_supported is True
        assert expiry_source.navigation_context["contract_id"] == "NVDA-20260821-C-125"
    finally:
        runtime.shutdown()


def test_checkpoint5_new_source_types_resolve_evidence_and_reject_unknown_refs():
    sources = [
        CopilotSourceRef(
            source_id="equity_research.scope.nvda",
            label="NVDA Equity Research",
            kind="equity_research",
            provider="mock_research",
            origin="gamma.research.analyze",
            navigation_supported=True,
            navigation_tab="equity_research",
            navigation_mode="single_name",
            navigation_context={"symbol": "NVDA"},
        ),
        CopilotSourceRef(
            source_id="commodities.curve.wti",
            label="WTI curve",
            kind="commodity_curve",
            provider="mock_commodities",
            origin="gamma.commodities.curve_analytics",
            navigation_supported=True,
            navigation_tab="commodities",
            navigation_mode="curves_spreads",
            navigation_context={"instrument_id": "wti"},
        ),
        CopilotSourceRef(
            source_id="maritime.chokepoint.strait_of_hormuz",
            label="Strait of Hormuz",
            kind="maritime_chokepoint",
            provider="sample_maritime",
            origin="gamma.maritime.chokepoint_summary",
            navigation_supported=True,
            navigation_tab="maritime",
            navigation_mode="chokepoints",
            navigation_context={"chokepoint_id": "strait-of-hormuz"},
        ),
        CopilotSourceRef(
            source_id="iv.expiry.nvda.2026_08_21",
            label="NVDA IV expiry",
            kind="iv_expiry",
            provider="mock_options",
            origin="gamma.iv.expiry_analytics",
            navigation_supported=True,
            navigation_tab="iv",
            navigation_mode="surface",
            navigation_context={"symbol": "NVDA", "expiry": "2026-08-21"},
        ),
        CopilotSourceRef(
            source_id="external_context.news_item.feed_1",
            label="Oil disruption headline",
            kind="news_item",
            provider="sample_news",
            origin="sample.news.item",
            url="https://news.example.com/oil-disruption",
            navigation_supported=True,
            navigation_context={"news_item_id": "feed:1"},
        ),
        CopilotSourceRef(
            source_id="maritime.coverage",
            label="Maritime coverage",
            kind="provenance",
            provider="sample_maritime",
            origin="gamma.maritime.coverage",
            navigation_supported=False,
            navigation_reason="Coverage has no standalone destination.",
        ),
    ]
    valid_ids = [source.source_id for source in sources[:5]]
    result = CopilotResearchCardResult(
        domain="synthesis",
        current_tab="copilot",
        status="ready",
        provider="gamma_executor",
        card=ResearchCard(
            title="Checkpoint 5 evidence",
            hypothesis="Each supported domain can ground a bounded claim.",
            rationale="Registry-backed source references.",
            required_data=[],
            proposed_test="Resolve all evidence references.",
            confounders=[],
            next_steps=[],
            caveats=[],
            source_backed_claims=[
                *[
                    ResearchClaim(
                        claim=f"Claim grounded by {source_id}.",
                        evidence_refs=[source_id],
                    )
                    for source_id in valid_ids
                ],
                ResearchClaim(
                    claim="Claim with a fabricated source.",
                    evidence_refs=["unknown.checkpoint5.source"],
                ),
            ],
        ),
        sources=sources,
    )

    normalized = CopilotService._normalize_result_sources(result)
    assert normalized.card is not None
    assert {
        ref
        for claim in normalized.card.source_backed_claims
        for ref in claim.evidence_refs
    } == set(valid_ids)
    assert "Claim with a fabricated source." in normalized.card.inferred_claims
    assert all(
        "unknown.checkpoint5.source" not in claim.evidence_refs
        for claim in normalized.card.source_backed_claims
    )
    coverage = next(
        source for source in normalized.sources if source.source_id == "maritime.coverage"
    )
    assert coverage.navigation_supported is False
    assert coverage.navigation_reason


@pytest.mark.parametrize(
    ("prompt", "expected_domains", "expected_omissions"),
    [
        (
            "Research NVDA using the relevant Gamma domains.",
            {"fundamentals", "equity_research", "iv", "external_context"},
            {"portfolio", "commodities", "maritime"},
        ),
        (
            "Research CPI and the next Fed decision using relevant Gamma domains.",
            {"macro", "prediction_markets", "external_context"},
            {"portfolio", "commodities", "maritime"},
        ),
        (
            "Research an oil supply disruption using relevant Gamma domains.",
            {
                "commodities",
                "maritime",
                "macro",
                "prediction_markets",
                "external_context",
            },
            {"portfolio", "iv"},
        ),
        (
            "Is my portfolio exposed to a 100 basis-point rate shock?",
            {"portfolio", "risk", "macro"},
            {"commodities", "maritime", "external_context"},
        ),
    ],
)
def test_checkpoint5_representative_plans_select_domains_and_explain_omissions(
    tmp_path,
    prompt,
    expected_domains,
    expected_omissions,
):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/copilot/research-plan",
            json={
                "domain": "synthesis",
                "prompt": prompt,
                "context": {
                    "current_tab": "copilot",
                    "workspace_mode": "research_book",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        selected = {item["domain"] for item in payload["domain_plan"]}
        assert selected == expected_domains
        decisions = {item["domain"]: item for item in payload["domain_decisions"]}
        assert all(decisions[domain]["used"] is True for domain in expected_domains)
        assert all(
            decisions[domain]["classification"] == "selected"
            for domain in expected_domains
        )
        for domain in expected_omissions:
            assert decisions[domain]["used"] is False
            assert decisions[domain]["classification"] == "irrelevant"
            assert decisions[domain]["reason"]
    finally:
        runtime.shutdown()
