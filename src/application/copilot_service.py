from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import logging
import re
import time
from typing import Any, Callable

from src.application.copilot_context_helpers import (
    dedupe_warnings,
    resolve_iv_surface,
    summarize_commodities_workspace,
    summarize_iv_state,
    summarize_portfolio_history,
    summarize_portfolio_performance,
    summarize_portfolio_snapshot,
    summarize_research_result,
    summarize_risk_result,
)
from src.application.copilot_report_service import CopilotReportService
from src.application.crypto_service import CryptoService
from src.application.fundamentals_service import FundamentalsService
from src.application.macro_service import MacroSnapshotRequest, MacroService
from src.application.news_service import NewsService
from src.application.prediction_market_service import PredictionMarketService
from src.models.copilot import (
    CopilotContextBundle,
    CopilotDraftMutation,
    CopilotMemo,
    CopilotMutationApplyResult,
    CopilotMutationDiffEntry,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotResearchActionDefinition,
    CopilotResearchPlan,
    CopilotResearchPlanDomainDecision,
    CopilotResearchPlanDomain,
    CopilotResearchPlanEntity,
    CopilotResearchReport,
    CopilotSession,
    CopilotSourceRef,
    CopilotTurn,
    CopilotToolExecution,
    CopilotToolTrace,
    MacroCopilotContext,
    ResearchCard,
    ResearchClaim,
    new_copilot_id,
)
from src.services.copilot_store import CopilotStore
from src.models.macro import MacroMetricRecord, MacroSeriesHistory
from src.models.news import NewsEventFeed, NewsEventItem
from src.models.prediction_markets import PredictionProbabilityPoint
from src.models.provenance import FreshnessLabel
from src.services.copilot_provider import CopilotProvider
from src.utils.time import now_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CopilotToolDefinition:
    name: str
    description: str
    domains: tuple[str, ...]
    parameters_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], CopilotContextBundle], CopilotToolExecution]
    action_type: str = "read_context"
    output_schema: dict[str, Any] | None = None
    read_only: bool = True
    mutates_local_state: bool = False
    requires_confirmation: bool = False
    external_provider: str | None = None
    timeout_seconds: float = 30.0
    request_limit: int = 1
    failure_modes: tuple[str, ...] = ()

    def to_openai_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
            "strict": True,
        }

    def to_action_definition(self) -> CopilotResearchActionDefinition:
        return CopilotResearchActionDefinition(
            tool_id=self.name,
            domains=list(self.domains),
            action_type=self.action_type,
            description=self.description,
            input_schema=self.parameters_schema,
            output_schema=self.output_schema or {},
            read_only=self.read_only,
            mutates_local_state=self.mutates_local_state,
            requires_confirmation=self.requires_confirmation,
            external_provider=self.external_provider,
            timeout_seconds=self.timeout_seconds,
            request_limit=self.request_limit,
            failure_modes=list(self.failure_modes),
        )


@dataclass(frozen=True)
class _CopilotExecutionBudget:
    max_domains: int
    max_tool_calls: int
    max_provider_calls: int
    max_elapsed_ms: int


class CopilotService:
    def __init__(
        self,
        *,
        macro_service: MacroService,
        prediction_market_service: PredictionMarketService,
        crypto_service: CryptoService,
        fundamentals_service: FundamentalsService,
        news_service: NewsService | None = None,
        provider: CopilotProvider,
        store: CopilotStore | None = None,
    ) -> None:
        self.macro_service = macro_service
        self.prediction_market_service = prediction_market_service
        self.crypto_service = crypto_service
        self.fundamentals_service = fundamentals_service
        self.news_service = news_service
        self.provider = provider
        self.store = store
        self._context_builders = {
            "portfolio": self._build_portfolio_context,
            "research": self._build_research_context,
            "equity_research": self._build_equity_research_context,
            "strategy_lab": self._build_strategy_lab_context,
            "macro": self._build_macro_context,
            "commodities": self._build_commodities_context,
            "prediction_markets": self._build_prediction_market_context,
            "crypto": self._build_crypto_context,
            "fundamentals": self._build_fundamentals_context,
            "risk": self._build_risk_context,
            "iv": self._build_iv_context,
            "external_context": self._build_external_context,
            "synthesis": self._build_synthesis_context,
        }
        self._tools = {
            definition.name: definition
            for definition in (
                _CopilotToolDefinition(
                    name="get_portfolio_positions_summary",
                    description="Return a read-only snapshot summary of the current Gamma portfolio, including top exposures and concentration cues.",
                    domains=("portfolio",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_portfolio_positions_summary,
                ),
                _CopilotToolDefinition(
                    name="get_portfolio_performance_context",
                    description="Return a read-only performance and local-history summary for the active Gamma portfolio context.",
                    domains=("portfolio",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_portfolio_performance_context,
                ),
                _CopilotToolDefinition(
                    name="get_research_scope_summary",
                    description="Return a read-only summary of the active Gamma research scope, weights, and benchmark context.",
                    domains=("research", "equity_research"),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_research_scope_summary,
                ),
                _CopilotToolDefinition(
                    name="get_research_coverage_context",
                    description="Return a read-only research coverage and constituent summary for the active Gamma research result.",
                    domains=("research", "equity_research"),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_research_coverage_context,
                ),
                _CopilotToolDefinition(
                    name="get_macro_workspace_drilldown",
                    description="Return a fuller read-only macro workspace payload for the currently selected Gamma context.",
                    domains=("macro",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_macro_workspace_drilldown,
                ),
                _CopilotToolDefinition(
                    name="get_macro_series_history_summary",
                    description="Return a compact read-only time-series summary for a macro series in the active timeframe.",
                    domains=("macro",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "series_id": {
                                "type": "string",
                                "description": "Gamma macro series identifier, e.g. us-cpi-yoy or us-2y-yield.",
                            },
                            "region": {
                                "type": ["string", "null"],
                                "description": "Optional region override. Use null to keep the active region.",
                            },
                        },
                        "required": ["series_id", "region"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_macro_series_history_summary,
                ),
                _CopilotToolDefinition(
                    name="get_commodities_workspace_summary",
                    description="Return a read-only summary of the loaded Commodities workspace, including market, curve, spread, inventory, event, warning, and provenance context.",
                    domains=("commodities",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_commodities_workspace_summary,
                ),
                _CopilotToolDefinition(
                    name="get_prediction_market_history_summary",
                    description="Return a read-only summary of probability history for the selected prediction market.",
                    domains=("prediction_markets",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_prediction_market_history_summary,
                ),
                _CopilotToolDefinition(
                    name="get_prediction_market_flow_context",
                    description="Return read-only wallet, related-market, and calibration context for the selected prediction market.",
                    domains=("prediction_markets",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_prediction_market_flow_context,
                ),
                _CopilotToolDefinition(
                    name="get_crypto_price_history_summary",
                    description="Return a read-only price, market-cap, and volume history summary for the selected crypto token.",
                    domains=("crypto",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_crypto_price_history_summary,
                ),
                _CopilotToolDefinition(
                    name="get_crypto_liquidity_context",
                    description="Return read-only DEX liquidity, flow, and top-pool context for the selected crypto token.",
                    domains=("crypto",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_crypto_liquidity_context,
                ),
                _CopilotToolDefinition(
                    name="get_crypto_comparison_context",
                    description="Return a read-only comparison between the selected crypto token and Gamma's default comparison target.",
                    domains=("crypto",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_crypto_comparison_context,
                ),
                _CopilotToolDefinition(
                    name="get_fundamentals_company_context",
                    description="Return read-only company, filing, headline metric, and warning context for the selected Fundamentals ticker.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_fundamentals_company_context,
                ),
                _CopilotToolDefinition(
                    name="get_fundamentals_statement_context",
                    description="Return read-only normalized statement and raw-versus-normalized source trace context for the selected Fundamentals ticker.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_fundamentals_statement_context,
                ),
                _CopilotToolDefinition(
                    name="get_fundamentals_peer_context",
                    description="Return read-only peer basket, peer heatmap, comparison, and missing-data diagnostics for the selected Fundamentals ticker.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_fundamentals_peer_context,
                ),
                _CopilotToolDefinition(
                    name="get_fundamentals_dcf_context",
                    description="Return read-only DCF scenario, sensitivity, and snapshot context for the selected Fundamentals ticker.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_fundamentals_dcf_context,
                ),
                _CopilotToolDefinition(
                    name="get_fundamentals_reverse_valuation_context",
                    description="Return read-only reverse-valuation and implied-expectation context for the selected Fundamentals ticker.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_fundamentals_reverse_valuation_context,
                ),
                _CopilotToolDefinition(
                    name="get_risk_coverage_summary",
                    description="Return a read-only risk coverage, benchmark, and warning summary for the active Gamma risk result.",
                    domains=("risk",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_risk_coverage_summary,
                ),
                _CopilotToolDefinition(
                    name="get_risk_contribution_summary",
                    description="Return a read-only contribution and Monte Carlo summary for the active Gamma risk result.",
                    domains=("risk",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_risk_contribution_summary,
                ),
                _CopilotToolDefinition(
                    name="get_iv_surface_context",
                    description="Return a read-only options surface and ATM term-structure summary for the active Gamma Options context.",
                    domains=("iv",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_iv_surface_context,
                ),
                _CopilotToolDefinition(
                    name="get_iv_session_status",
                    description="Return a read-only session and market-data-mode summary for the active Gamma Options context.",
                    domains=("iv",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_iv_session_status,
                ),
                _CopilotToolDefinition(
                    name="get_external_context_summary",
                    description="Return bounded read-only company, macro, commodity, and event context from approved external provider adapters, with explicit freshness and unavailable-provider labels.",
                    domains=("external_context",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_external_context_summary,
                    action_type="fetch_external_context",
                    external_provider="news",
                    timeout_seconds=8.0,
                    failure_modes=(
                        "No news/event provider is configured.",
                        "Configured provider returned no matching items.",
                        "Estimate, transcript, or filing-delta adapters are not configured.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="get_synthesis_scope_summary",
                    description="Return the active cross-context Gamma synthesis scope, including included domains, context fingerprints, warnings, and source references.",
                    domains=("synthesis",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_synthesis_scope_summary,
                ),
                _CopilotToolDefinition(
                    name="get_synthesis_domain_context",
                    description="Return a read-only detailed context package for one included Gamma domain inside the active synthesis scope.",
                    domains=("synthesis",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Included Gamma domain id, e.g. macro, prediction_markets, research, risk, portfolio, or iv.",
                            }
                        },
                        "required": ["domain"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_synthesis_domain_context,
                ),
            )
        }
        self._mutation_action_definitions = [
            CopilotResearchActionDefinition(
                tool_id="fundamentals.propose_dcf_update",
                domains=["fundamentals"],
                action_type="draft_change",
                description="Draft a local Fundamentals DCF scenario update and return a diff plus confirmation token; does not apply the change.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "scenario_id": {"type": "string"},
                        "active_scenario_id": {"type": ["string", "null"]},
                        "assumptions": {"type": "object"},
                        "overrides": {"type": "object"},
                        "rationale": {"type": ["string", "null"]},
                    },
                    "required": ["ticker", "scenario_id", "active_scenario_id", "assumptions", "overrides", "rationale"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                read_only=False,
                mutates_local_state=False,
                requires_confirmation=False,
                request_limit=1,
                failure_modes=[
                    "Selected ticker has no Fundamentals DCF model.",
                    "No valid DCF fields are changed by the draft.",
                ],
            ),
            CopilotResearchActionDefinition(
                tool_id="fundamentals.apply_dcf_update",
                domains=["fundamentals"],
                action_type="apply_change",
                description="Apply a previously drafted Fundamentals DCF update after confirmation-token validation, saving a rollback snapshot first.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mutation_id": {"type": "string"},
                        "confirmation_token": {"type": "string"},
                    },
                    "required": ["mutation_id", "confirmation_token"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                read_only=False,
                mutates_local_state=True,
                requires_confirmation=True,
                request_limit=1,
                failure_modes=[
                    "Confirmation token is missing or does not match.",
                    "Draft mutation has already been applied.",
                    "Underlying Fundamentals DCF model cannot be saved.",
                ],
            ),
        ]

    def generate_research_card(self, request: CopilotResearchCardRequest) -> CopilotResearchCardResult:
        resolved_domain = self._resolve_domain(request)
        normalized_request = replace(request, domain=resolved_domain)
        builder = self._context_builders.get(resolved_domain)
        if builder is None:
            return CopilotResearchCardResult(
                domain=resolved_domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=getattr(self.provider, "provider_name", "unknown"),
                message=f"Unsupported copilot domain: {resolved_domain}",
            )
        try:
            context = builder(normalized_request)
        except ValueError as exc:
            return CopilotResearchCardResult(
                domain=resolved_domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=getattr(self.provider, "provider_name", "unknown"),
                message=str(exc),
            )

        tool_specs = [
            tool.to_openai_spec()
            for tool in self._tools.values()
            if resolved_domain in tool.domains
        ]
        try:
            result = self.provider.generate_research_card(
                request=normalized_request,
                context=context,
                tool_specs=tool_specs,
                execute_tool=self._execute_tool,
            )
        except Exception as exc:
            logger.exception("Copilot provider failed for domain %s", resolved_domain)
            result = CopilotResearchCardResult(
                domain=resolved_domain,
                current_tab=context.current_tab,
                status="error",
                provider=getattr(self.provider, "provider_name", "unknown"),
                message=f"Copilot failed: {exc}",
                sources=list(context.sources),
                warnings=dedupe_warnings(
                    [
                        *context.warnings,
                        "Copilot generation failed before a research card could be produced.",
                    ]
                ),
            )
        result = self._normalize_result_sources(result)
        if self.store is not None:
            try:
                self.store.record_turn(
                    session_id=normalized_request.user_session_id,
                    title=normalized_request.session_title,
                    domain=resolved_domain,
                    current_tab=context.current_tab,
                    workspace_mode=normalized_request.context.workspace_mode,
                    prompt=normalized_request.prompt,
                    context_fingerprint=normalized_request.context_fingerprint,
                    context_summary=self._context_summary_for_persistence(context),
                    result=result,
                )
            except Exception:
                logger.exception("Copilot persistence failed for domain %s", resolved_domain)
                result = replace(
                    result,
                    warnings=dedupe_warnings(
                        [
                            *result.warnings,
                            "Copilot generated a response, but failed to persist this turn locally.",
                        ]
                    ),
                )
        return result

    def plan_research(self, request: CopilotResearchCardRequest) -> CopilotResearchPlan:
        prompt = str(request.prompt or "").strip()
        normalized_prompt = prompt.lower()
        target_entities = self._extract_plan_entities(prompt, request.context)
        depth_profile = self._infer_depth_profile(normalized_prompt)
        intent = self._infer_plan_intent(normalized_prompt, target_entities, request.context)
        domain_plan = self._build_domain_plan(
            intent=intent,
            prompt=normalized_prompt,
            depth_profile=depth_profile,
            target_entities=target_entities,
            request=request,
        )
        budget = self._execution_budget_for_depth(depth_profile)
        domain_decisions = self._build_domain_decisions(
            intent=intent,
            domain_plan=domain_plan,
            request=request,
        )
        warnings = self._plan_warnings(prompt, domain_plan)
        expected_artifacts = ["session_trace"]
        if depth_profile in {"standard", "deep"} or intent != "active_context_research":
            expected_artifacts.append("research_memo")
        if depth_profile == "deep":
            expected_artifacts.append("report_outline")

        return CopilotResearchPlan(
            intent=intent,
            target_entities=target_entities,
            depth_profile=depth_profile,
            domain_plan=domain_plan,
            domain_decisions=domain_decisions,
            max_tool_calls=budget.max_tool_calls,
            max_provider_calls=budget.max_provider_calls,
            max_elapsed_ms=budget.max_elapsed_ms,
            requires_confirmation=False,
            expected_artifacts=expected_artifacts,
            warnings=warnings,
        )

    def list_research_action_definitions(self) -> list[CopilotResearchActionDefinition]:
        return [
            *[definition.to_action_definition() for definition in self._tools.values()],
            *self._mutation_action_definitions,
        ]

    def propose_fundamentals_dcf_update(
        self,
        *,
        ticker: str,
        scenario_id: str = "base",
        active_scenario_id: str | None = None,
        assumptions: dict[str, Any] | None = None,
        overrides: dict[str, list[float | None]] | None = None,
        rationale: str | None = None,
    ) -> CopilotDraftMutation:
        if self.store is None:
            raise ValueError("Copilot mutation proposals require local Copilot persistence.")
        normalized_ticker = str(ticker or "").strip().upper()
        normalized_scenario = str(scenario_id or "base").strip().lower()
        if not normalized_ticker:
            raise ValueError("ticker is required.")
        current_model = self.fundamentals_service.get_dcf_model(normalized_ticker)
        if current_model is None:
            raise ValueError(f"Fundamentals DCF model not found: {normalized_ticker}")
        current_payload = self._dcf_payload_from_model(current_model)
        proposed_payload = self._apply_dcf_mutation_payload(
            current_payload,
            scenario_id=normalized_scenario,
            active_scenario_id=active_scenario_id,
            assumptions=assumptions or {},
            overrides=overrides or {},
        )
        proposed_model = self.fundamentals_service.preview_dcf_model(normalized_ticker, proposed_payload)
        if proposed_model is None:
            raise ValueError(f"Fundamentals DCF model could not be previewed: {normalized_ticker}")

        diff = self._build_dcf_mutation_diff(
            current_model,
            proposed_model,
            current_payload,
            proposed_payload,
            normalized_scenario,
        )
        warnings = []
        if not diff:
            warnings.append("Draft DCF mutation does not change any supported DCF fields.")
        mutation = CopilotDraftMutation(
            mutation_id=new_copilot_id("mutation"),
            domain="fundamentals",
            tool_id="fundamentals.propose_dcf_update",
            action_type="draft_change",
            target_id=f"{normalized_ticker}:{normalized_scenario}",
            target_label=f"{normalized_ticker} {normalized_scenario.title()} DCF",
            status="pending",
            requires_confirmation=True,
            confirmation_token=new_copilot_id("confirm"),
            diff=diff,
            rendered_diff=self._render_mutation_diff(diff),
            proposed_payload=proposed_payload,
            rationale=str(rationale or "").strip() or None,
            warnings=dedupe_warnings([*warnings, *proposed_model.warnings]),
            source_ids=["fundamentals.dcf.model"],
            origin="copilot_service.propose_fundamentals_dcf_update",
            transformation_note=(
                "Gamma drafted a local DCF scenario update from explicit typed inputs. "
                "No DCF state is changed until the confirmation token is submitted."
            ),
        )
        self.store.save_mutation(mutation)
        return mutation

    def apply_fundamentals_dcf_update(
        self,
        *,
        mutation_id: str,
        confirmation_token: str,
    ) -> CopilotMutationApplyResult:
        if self.store is None:
            raise ValueError("Copilot mutation application requires local Copilot persistence.")
        mutation = self.store.get_mutation(mutation_id)
        if mutation is None:
            raise ValueError(f"Copilot mutation not found: {mutation_id}")
        if mutation.tool_id != "fundamentals.propose_dcf_update" or mutation.domain != "fundamentals":
            raise ValueError(f"Unsupported Copilot mutation: {mutation.tool_id}")
        if mutation.status != "pending":
            raise ValueError(f"Copilot mutation is not pending: {mutation.status}")
        if not confirmation_token or confirmation_token != mutation.confirmation_token:
            raise ValueError("Confirmation token does not match the pending Copilot mutation.")
        ticker = mutation.target_id.split(":", 1)[0].strip().upper()
        if not ticker:
            raise ValueError("Pending Copilot mutation is missing a Fundamentals ticker.")

        snapshot = self.fundamentals_service.save_dcf_snapshot(
            ticker,
            name=f"Pre-Copilot DCF update {mutation.mutation_id[-8:]}",
        )
        model = self.fundamentals_service.save_dcf_model(ticker, mutation.proposed_payload)
        if model is None:
            raise ValueError(f"Fundamentals DCF model could not be saved: {ticker}")
        applied = replace(
            mutation,
            status="applied",
            tool_id="fundamentals.apply_dcf_update",
            action_type="apply_change",
            rollback_snapshot_id=snapshot.snapshot_id if snapshot else None,
            applied_at=now_utc(),
            warnings=dedupe_warnings(
                [
                    *mutation.warnings,
                    *model.warnings,
                    "A DCF snapshot was saved before applying the confirmed Copilot update."
                    if snapshot is not None
                    else "Copilot applied the DCF update, but a rollback snapshot could not be saved.",
                ]
            ),
            origin="copilot_service.apply_fundamentals_dcf_update",
            transformation_note=(
                "Gamma applied a previously drafted DCF mutation after confirmation-token validation "
                "and saved the pre-change DCF snapshot as rollback context."
            ),
        )
        self.store.save_mutation(applied)
        return CopilotMutationApplyResult(
            mutation=applied,
            artifact={
                "ticker": model.ticker,
                "active_scenario_id": model.active_scenario_id,
                "projection_years": list(model.projection_years),
                "rollback_snapshot_id": applied.rollback_snapshot_id,
            },
            warnings=list(applied.warnings),
        )

    def execute_research_plan(self, request: CopilotResearchCardRequest) -> CopilotResearchCardResult:
        plan = self.plan_research(request)
        sources: dict[str, CopilotSourceRef] = {}
        tool_traces: list[CopilotToolTrace] = []
        warnings = [
            warning
            for warning in plan.warnings
            if not warning.startswith("Planner-only prototype")
        ]
        executed_domains: list[str] = []
        skipped_domains: list[str] = []
        tool_outputs: dict[str, dict[str, Any]] = {}
        budget = self._execution_budget_for_depth(plan.depth_profile)
        remaining_tools = budget.max_tool_calls
        provider_calls_used = 0
        started_at = time.perf_counter()

        for planned_domain in plan.domain_plan[: budget.max_domains]:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            if elapsed_ms >= budget.max_elapsed_ms:
                warnings.append(
                    f"Stopped plan execution after {elapsed_ms}ms, above the {budget.max_elapsed_ms}ms elapsed-time guard."
                )
                break
            domain = planned_domain.domain

            try:
                context = self._build_plan_execution_context(request, domain)
            except ValueError as exc:
                skipped_domains.append(domain)
                warnings.append(f"Skipped {domain}: {exc}")
                continue

            for source in context.sources:
                sources[source.source_id] = source
            warnings.extend(context.warnings)

            domain_outputs: dict[str, Any] = {}
            for tool_name in planned_domain.planned_tools:
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                if elapsed_ms >= budget.max_elapsed_ms and tool_traces:
                    warnings.append(
                        f"Stopped plan execution after {elapsed_ms}ms, above the {budget.max_elapsed_ms}ms elapsed-time guard."
                    )
                    break
                if remaining_tools <= 0:
                    warnings.append(
                        f"Stopped plan execution after {budget.max_tool_calls} read-only tools."
                    )
                    break

                definition = self._tools.get(tool_name)
                if definition is None:
                    warnings.append(f"Skipped unsupported Copilot tool `{tool_name}`.")
                    continue
                if domain not in definition.domains:
                    warnings.append(f"Skipped `{tool_name}` because it is not registered for {domain}.")
                    continue
                if (
                    not definition.read_only
                    or definition.mutates_local_state
                    or definition.requires_confirmation
                ):
                    warnings.append(f"Skipped `{tool_name}` because it is not automatic read-only work.")
                    continue
                if definition.external_provider:
                    if provider_calls_used + 1 > budget.max_provider_calls:
                        warnings.append(
                            f"Skipped `{tool_name}` because provider calls would exceed the {budget.max_provider_calls} call guard."
                        )
                        continue
                    provider_calls_used += 1

                arguments = self._default_plan_execution_arguments(tool_name, context)
                if arguments is None:
                    tool_traces.append(
                        CopilotToolTrace(
                            tool_name=tool_name,
                            summary="Skipped because bounded plan execution could not infer required arguments.",
                            arguments={},
                            source_ids=[],
                        )
                    )
                    continue

                execution = self._execute_tool(tool_name, arguments, context)
                remaining_tools -= 1
                tool_traces.append(execution.trace)
                domain_outputs[tool_name] = execution.output
                for source in execution.sources:
                    sources[source.source_id] = source
                if isinstance(execution.output, dict) and execution.output.get("error"):
                    warnings.append(f"{tool_name} failed: {execution.output['error']}")

            if domain_outputs:
                executed_domains.append(domain)
                tool_outputs[domain] = domain_outputs

        if len(plan.domain_plan) > budget.max_domains:
            warnings.append(
                f"Plan execution was bounded to {budget.max_domains} domains for the {plan.depth_profile} profile."
            )

        warnings = dedupe_warnings(warnings)
        result = CopilotResearchCardResult(
            domain="synthesis",
            current_tab=request.context.current_tab or "copilot",
            status="ready" if executed_domains else "error",
            provider="gamma_executor",
            model="gamma-plan-executor-v1",
            response_id=new_copilot_id("planexec"),
            message=(
                f"Executed {len(tool_traces)} read-only tool traces across "
                f"{len(executed_domains)} planned domains."
            ),
            card=self._build_plan_execution_card(
                plan,
                executed_domains,
                skipped_domains,
                list(sources.values()),
                warnings,
            ),
            sources=list(sources.values()),
            tool_traces=tool_traces,
            warnings=warnings,
        )
        result = self._normalize_result_sources(result)

        if self.store is not None:
            try:
                self.store.record_turn(
                    session_id=request.user_session_id,
                    title=request.session_title,
                    domain="synthesis",
                    current_tab=request.context.current_tab or "copilot",
                    workspace_mode=request.context.workspace_mode,
                    prompt=request.prompt,
                    context_fingerprint=request.context_fingerprint,
                    context_summary={
                        "plan": asdict(plan),
                        "executed_domains": executed_domains,
                        "skipped_domains": skipped_domains,
                        "tool_output_keys": {
                            domain: list(outputs)
                            for domain, outputs in tool_outputs.items()
                        },
                    },
                    result=result,
                )
            except Exception:
                logger.exception("Copilot plan execution persistence failed")
                result = replace(
                    result,
                    warnings=dedupe_warnings(
                        [
                            *result.warnings,
                            "Copilot executed the plan, but failed to persist this turn locally.",
                        ]
                    ),
                )
        return result

    def _build_plan_execution_context(
        self,
        request: CopilotResearchCardRequest,
        domain: str,
    ) -> CopilotContextBundle:
        builder = self._context_builders.get(domain)
        if builder is None:
            raise ValueError(f"unsupported Copilot domain `{domain}`.")
        domain_context = self._plan_execution_request_context(request, domain)
        return builder(replace(request, domain=domain, context=domain_context))

    def _plan_execution_request_context(
        self,
        request: CopilotResearchCardRequest,
        domain: str,
    ) -> CopilotRequestContext:
        domain_context = self._synthesis_scope_context_for_domain(request, domain) or request.context
        domain_context = replace(domain_context, current_tab=domain)

        if domain == "fundamentals" and not self._context_has_fundamentals_ticker(domain_context):
            ticker = self._first_plan_entity_id(request, "ticker")
            if ticker:
                domain_context = replace(domain_context, fundamentals_ticker=ticker)

        return domain_context

    @staticmethod
    def _synthesis_scope_context_for_domain(
        request: CopilotResearchCardRequest,
        domain: str,
    ) -> CopilotRequestContext | None:
        if request.synthesis is None:
            return None
        for scope in request.synthesis.included_scopes:
            if str(scope.domain or "").strip() == domain:
                return scope.context
        return None

    @staticmethod
    def _context_has_fundamentals_ticker(context: CopilotRequestContext) -> bool:
        if str(context.fundamentals_ticker or "").strip():
            return True
        if isinstance(context.fundamentals_state, dict):
            return bool(
                str(
                    context.fundamentals_state.get("ticker")
                    or context.fundamentals_state.get("selected_ticker")
                    or ""
                ).strip()
            )
        return False

    def _first_plan_entity_id(
        self,
        request: CopilotResearchCardRequest,
        kind: str,
    ) -> str | None:
        for entity in self._extract_plan_entities(str(request.prompt or ""), request.context):
            if entity.kind == kind and str(entity.id or "").strip():
                return str(entity.id).strip()
        return None

    def _default_plan_execution_arguments(
        self,
        tool_name: str,
        context: CopilotContextBundle,
    ) -> dict[str, Any] | None:
        if tool_name == "get_macro_series_history_summary":
            for card in context.summary_data.get("snapshot_cards", []) or []:
                for metric in card.get("metrics", []) if isinstance(card, dict) else []:
                    series_id = metric.get("series_id") if isinstance(metric, dict) else None
                    if series_id:
                        return {
                            "series_id": series_id,
                            "region": context.summary_data.get("region"),
                        }
            return None
        if tool_name == "get_synthesis_domain_context":
            included_domains = context.summary_data.get("included_domains", []) or []
            return {"domain": included_domains[0]} if included_domains else None
        return {}

    @staticmethod
    def _dcf_payload_from_model(model: Any) -> dict[str, Any]:
        return {
            "ticker": model.ticker,
            "active_scenario_id": model.active_scenario_id,
            "projection_years": list(model.projection_years),
            "scenarios": {
                scenario.scenario_id: {
                    "assumptions": dict(scenario.assumptions),
                    "overrides": {
                        key: list(values)
                        for key, values in dict(scenario.overrides).items()
                    },
                }
                for scenario in model.scenarios
            },
        }

    @staticmethod
    def _apply_dcf_mutation_payload(
        payload: dict[str, Any],
        *,
        scenario_id: str,
        active_scenario_id: str | None,
        assumptions: dict[str, Any],
        overrides: dict[str, list[float | None]],
    ) -> dict[str, Any]:
        proposed = deepcopy(payload)
        scenarios = proposed.setdefault("scenarios", {})
        if scenario_id not in scenarios:
            raise ValueError(f"Unsupported DCF scenario: {scenario_id}")
        scenario = scenarios[scenario_id]
        scenario_assumptions = scenario.setdefault("assumptions", {})
        for key, value in assumptions.items():
            normalized_key = CopilotService._normalize_dcf_assumption_key(str(key))
            if normalized_key not in scenario_assumptions:
                continue
            default_value = scenario_assumptions[normalized_key]
            if isinstance(default_value, list):
                scenario_assumptions[normalized_key] = (
                    list(value)
                    if isinstance(value, list)
                    else [value for _ in default_value]
                )
            else:
                scenario_assumptions[normalized_key] = value
        scenario_overrides = scenario.setdefault("overrides", {})
        for key, values in overrides.items():
            if isinstance(values, list):
                scenario_overrides[key] = list(values)
        if active_scenario_id:
            proposed["active_scenario_id"] = str(active_scenario_id).strip().lower()
        return proposed

    @staticmethod
    def _normalize_dcf_assumption_key(key: str) -> str:
        normalized = key.strip().lower()
        aliases = {
            "revenue_growth": "revenue_growth_pct",
            "growth": "revenue_growth_pct",
            "terminal_growth": "terminal_growth_pct",
            "wacc": "wacc_pct",
            "discount_rate": "wacc_pct",
            "tax_rate": "tax_rate_pct",
            "ebit_margin": "ebit_margin_pct",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _build_dcf_mutation_diff(
        current_model: Any,
        proposed_model: Any,
        current_payload: dict[str, Any],
        proposed_payload: dict[str, Any],
        scenario_id: str,
    ) -> list[CopilotMutationDiffEntry]:
        diff: list[CopilotMutationDiffEntry] = []
        if current_payload.get("active_scenario_id") != proposed_payload.get("active_scenario_id"):
            diff.append(
                CopilotMutationDiffEntry(
                    path="active_scenario_id",
                    label="Active Scenario",
                    before=current_payload.get("active_scenario_id"),
                    after=proposed_payload.get("active_scenario_id"),
                    change_type="update",
                )
            )
        current_scenario = dict(current_payload.get("scenarios", {})).get(scenario_id, {})
        proposed_scenario = dict(proposed_payload.get("scenarios", {})).get(scenario_id, {})
        current_assumptions = dict(current_scenario.get("assumptions", {}))
        proposed_assumptions = dict(proposed_scenario.get("assumptions", {}))
        for key, after_value in proposed_assumptions.items():
            before_value = current_assumptions.get(key)
            if before_value != after_value:
                diff.append(
                    CopilotMutationDiffEntry(
                        path=f"scenarios.{scenario_id}.assumptions.{key}",
                        label=CopilotService._dcf_field_label(key),
                        before=before_value,
                        after=after_value,
                        unit=CopilotService._dcf_field_unit(key),
                        change_type="update",
                    )
                )
        current_overrides = dict(current_scenario.get("overrides", {}))
        proposed_overrides = dict(proposed_scenario.get("overrides", {}))
        for key, after_value in proposed_overrides.items():
            before_value = current_overrides.get(key)
            if before_value != after_value:
                diff.append(
                    CopilotMutationDiffEntry(
                        path=f"scenarios.{scenario_id}.overrides.{key}",
                        label=f"{CopilotService._dcf_field_label(key)} Override",
                        before=before_value,
                        after=after_value,
                        unit=CopilotService._dcf_field_unit(key),
                        change_type="update",
                    )
                )
        current_summary = next(
            (scenario.summary for scenario in current_model.scenarios if scenario.scenario_id == scenario_id),
            None,
        )
        proposed_summary = next(
            (scenario.summary for scenario in proposed_model.scenarios if scenario.scenario_id == scenario_id),
            None,
        )
        if current_summary is not None and proposed_summary is not None:
            for key, label in (
                ("implied_value_per_share", "Implied Value / Share"),
                ("upside_downside_pct", "Upside / Downside"),
                ("enterprise_value", "Enterprise Value"),
            ):
                before_value = getattr(current_summary, key, None)
                after_value = getattr(proposed_summary, key, None)
                if before_value != after_value:
                    diff.append(
                        CopilotMutationDiffEntry(
                            path=f"scenarios.{scenario_id}.summary.{key}",
                            label=label,
                            before=before_value,
                            after=after_value,
                            unit="percent" if key.endswith("_pct") else "currency",
                            change_type="derived",
                        )
                    )
        return diff

    @staticmethod
    def _render_mutation_diff(diff: list[CopilotMutationDiffEntry]) -> list[str]:
        return [
            f"{item.label}: {CopilotService._format_diff_value(item.before, item.unit)} -> {CopilotService._format_diff_value(item.after, item.unit)}"
            for item in diff
        ]

    @staticmethod
    def _dcf_field_label(key: str) -> str:
        labels = {
            "revenue_growth_pct": "Revenue Growth",
            "ebit_margin_pct": "EBIT Margin",
            "tax_rate_pct": "Tax Rate",
            "da_pct_revenue": "D&A / Revenue",
            "capex_pct_revenue": "Capex / Revenue",
            "nwc_pct_incremental_revenue": "NWC / Incremental Revenue",
            "share_change_pct": "Share Count Change",
            "wacc_pct": "WACC",
            "terminal_growth_pct": "Terminal Growth",
            "revenue": "Revenue",
            "ebit": "EBIT",
            "taxes": "Taxes",
            "depreciation_and_amortization": "D&A",
            "capital_expenditures": "Capex",
            "change_in_nwc": "Change In NWC",
            "free_cash_flow": "Free Cash Flow",
        }
        return labels.get(key, key.replace("_", " ").title())

    @staticmethod
    def _dcf_field_unit(key: str) -> str | None:
        if key.endswith("_pct") or "_pct_" in key:
            return "percent"
        if key in {
            "revenue",
            "ebit",
            "taxes",
            "depreciation_and_amortization",
            "capital_expenditures",
            "change_in_nwc",
            "free_cash_flow",
            "enterprise_value",
        }:
            return "currency"
        return None

    @staticmethod
    def _format_diff_value(value: Any, unit: str | None) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(CopilotService._format_diff_value(item, unit) for item in value[:6]) + (", ..." if len(value) > 6 else "") + "]"
        if value is None:
            return "None"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if unit == "percent":
            return f"{numeric * 100:.1f}%"
        if unit == "currency":
            return f"{numeric:,.2f}"
        return f"{numeric:.4g}"

    @staticmethod
    def _build_plan_execution_card(
        plan: CopilotResearchPlan,
        executed_domains: list[str],
        skipped_domains: list[str],
        sources: list[CopilotSourceRef],
        warnings: list[str],
    ) -> ResearchCard:
        evidence_refs = [source.source_id for source in sources[:8]]
        intent_label = plan.intent.replace("_", " ")
        executed_label = ", ".join(domain.replace("_", " ") for domain in executed_domains) or "none"
        skipped_label = ", ".join(domain.replace("_", " ") for domain in skipped_domains) or "none"
        claims = []
        if evidence_refs:
            claims.append(
                ResearchClaim(
                    claim="Gamma executed bounded read-only tools for the selected research plan.",
                    evidence_refs=evidence_refs,
                )
            )
        return ResearchCard(
            title=f"Executed Research Plan: {intent_label}",
            hypothesis=(
                f"The request maps to a {plan.depth_profile} plan with "
                f"{len(plan.domain_plan)} planned domain steps."
            ),
            rationale=(
                f"Executed domains: {executed_label}. Skipped domains: {skipped_label}. "
                "Skipped steps indicate missing loaded Gamma context or unavailable approved providers."
            ),
            required_data=[
                item.domain
                for item in plan.domain_plan
                if item.domain not in skipped_domains
            ],
            proposed_test="Use the persisted tool trace as the source snapshot before synthesis or memo generation.",
            confounders=warnings[:6],
            next_steps=[
                "Review warnings for missing loaded contexts.",
                "Run synthesis after loading skipped domain state if the gaps matter.",
            ],
            caveats=[
                "This first-pass executor calls Gamma-owned read-only tools only.",
                "It does not fetch general web context or apply local research-state changes.",
            ],
            source_backed_claims=claims,
            inferred_claims=[
                "Tool outputs still need model synthesis before they become a final research conclusion."
            ],
        )

    @classmethod
    def _normalize_result_sources(cls, result: CopilotResearchCardResult) -> CopilotResearchCardResult:
        return replace(
            result,
            sources=[
                replace(source, retrieved_at=cls._coerce_source_datetime(source.retrieved_at))
                for source in result.sources
            ],
        )

    @staticmethod
    def _coerce_source_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def list_sessions(self, *, include_archived: bool = False, search: str | None = None) -> list[CopilotSession]:
        return self.store.list_sessions(include_archived=include_archived, search=search) if self.store is not None else []

    def list_turns(self, session_id: str) -> list[CopilotTurn]:
        return self.store.list_turns(session_id) if self.store is not None else []

    def list_memos(self, session_id: str | None = None) -> list[CopilotMemo]:
        return self.store.list_memos(session_id) if self.store is not None else []

    def create_memo(
        self,
        *,
        session_id: str,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
    ) -> CopilotMemo:
        if self.store is None:
            raise ValueError("Copilot persistence is not configured.")
        return self.store.create_memo(
            session_id=session_id,
            title=title,
            notes=notes,
            source_turn_ids=source_turn_ids,
        )

    def archive_session(self, session_id: str) -> CopilotSession:
        if self.store is None:
            raise ValueError("Copilot persistence is not configured.")
        return self.store.archive_session(session_id)

    def update_memo(self, memo_id: str, *, title: str | None = None, body: str | None = None) -> CopilotMemo:
        if self.store is None:
            raise ValueError("Copilot persistence is not configured.")
        return self.store.update_memo(memo_id, title=title, body=body)

    def export_memo_markdown(self, memo_id: str) -> str:
        if self.store is None:
            raise ValueError("Copilot persistence is not configured.")
        memo = self.store.get_memo(memo_id)
        if memo is None:
            raise ValueError(f"Copilot memo not found: {memo_id}")
        meta = [
            f"Session: {memo.session_id}",
            f"Memo: {memo.memo_id}",
            f"Updated: {memo.updated_at.isoformat()}",
            f"Source turns: {', '.join(memo.source_turn_ids) if memo.source_turn_ids else 'none'}",
        ]
        if memo.warnings:
            meta.extend(["", "Warnings:", *[f"- {warning}" for warning in memo.warnings]])
        return "\n".join([memo.body.strip(), "", "---", *meta]).strip() + "\n"

    def generate_research_report(
        self,
        *,
        session_id: str,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
        source_memo_ids: list[str] | None = None,
    ) -> CopilotResearchReport:
        if self.store is None:
            raise ValueError("Copilot persistence is not configured.")
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError(f"Copilot session not found: {session_id}")
        return CopilotReportService.generate_report(
            session=session,
            turns=self.store.list_turns(session.session_id),
            memos=self.store.list_memos(session.session_id),
            title=title,
            notes=notes,
            source_turn_ids=source_turn_ids,
            source_memo_ids=source_memo_ids,
        )

    def export_research_report_markdown(
        self,
        *,
        session_id: str,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
        source_memo_ids: list[str] | None = None,
    ) -> str:
        report = self.generate_research_report(
            session_id=session_id,
            title=title,
            notes=notes,
            source_turn_ids=source_turn_ids,
            source_memo_ids=source_memo_ids,
        )
        return CopilotReportService.export_markdown(report)

    @staticmethod
    def stream_events_for_result(result: CopilotResearchCardResult) -> list[dict[str, Any]]:
        return [
            {"event": "status", "data": {"status": "started", "domain": result.domain}},
            {
                "event": "metadata",
                "data": {
                    "provider": result.provider,
                    "model": result.model,
                    "response_id": result.response_id,
                    "source_count": len(result.sources),
                    "tool_count": len(result.tool_traces),
                    "warning_count": len(result.warnings),
                },
            },
            {"event": "result", "data": result},
            {"event": "done", "data": {"status": result.status}},
        ]

    @staticmethod
    def _extract_plan_entities(
        prompt: str,
        context: CopilotRequestContext,
    ) -> list[CopilotResearchPlanEntity]:
        entities: list[CopilotResearchPlanEntity] = []
        seen: set[tuple[str, str]] = set()

        def add_entity(kind: str, entity_id: str, label: str | None = None, confidence: float = 0.75) -> None:
            normalized_id = entity_id.strip().upper() if kind == "ticker" else entity_id.strip().lower()
            if not normalized_id:
                return
            key = (kind, normalized_id)
            if key in seen:
                return
            seen.add(key)
            entities.append(
                CopilotResearchPlanEntity(
                    kind=kind,
                    id=normalized_id,
                    label=label or normalized_id,
                    confidence=confidence,
                )
            )

        for match in re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b", prompt):
            if match.lower() in {"cpi", "fed", "oil", "rate", "rates", "var"}:
                continue
            add_entity("ticker", match, confidence=0.72)

        if context.fundamentals_ticker:
            add_entity("ticker", context.fundamentals_ticker, confidence=0.9)
        if context.crypto_token_id:
            add_entity("crypto_token", context.crypto_token_id, confidence=0.85)
        if context.prediction_market_id:
            add_entity("prediction_market", context.prediction_market_id, confidence=0.85)

        prompt_lower = prompt.lower()
        commodity_terms = {
            "oil": "oil",
            "crude": "oil",
            "brent": "brent",
            "wti": "wti",
            "gas": "natural_gas",
            "gold": "gold",
            "copper": "copper",
        }
        for term, entity_id in commodity_terms.items():
            if re.search(rf"\b{re.escape(term)}\b", prompt_lower):
                add_entity("commodity", entity_id, term.title(), confidence=0.8)

        return entities

    @staticmethod
    def _infer_depth_profile(prompt: str) -> str:
        if CopilotService._extract_user_directed_domains(prompt) or any(
            term in prompt for term in ("use only", "only use", "just use", "only run", "run only")
        ):
            return "user_directed"
        if any(term in prompt for term in ("deep", "full", "comprehensive", "report", "memo")):
            return "deep"
        if any(term in prompt for term in ("quick", "brief", "fast", "summary")):
            return "quick"
        return "standard"

    @staticmethod
    def _extract_user_directed_domains(prompt: str) -> list[str]:
        prompt = prompt.lower()
        if not prompt.strip():
            return []
        if re.search(r"\buse\s+(the\s+)?relevant\s+gamma\s+domains?\b", prompt):
            return []
        explicit_markers = (
            "use ",
            "using ",
            "run ",
            "only ",
            "just ",
            "from ",
            "with ",
        )
        if not any(marker in prompt for marker in explicit_markers):
            return []

        domain_terms: dict[str, tuple[str, ...]] = {
            "portfolio": ("portfolio", "book", "positions"),
            "risk": ("risk", "var", "cvar", "scenario"),
            "macro": ("macro", "rates", "fed", "cpi", "inflation"),
            "commodities": ("commodities", "commodity", "oil", "crude", "gold", "copper"),
            "prediction_markets": ("prediction market", "prediction markets", "polymarket", "kalshi"),
            "crypto": ("crypto", "token", "dex", "on-chain", "onchain"),
            "fundamentals": ("fundamentals", "dcf", "filings", "financials"),
            "equity_research": ("equity research", "equities", "stocks", "benchmark"),
            "strategy_lab": ("strategy lab", "strategy", "backtest"),
            "iv": ("options", "iv", "vol", "skew"),
            "external_context": ("external context", "news", "recent news", "headlines"),
        }
        domains: list[str] = []
        for domain, terms in domain_terms.items():
            if any(re.search(rf"\b{re.escape(term)}\b", prompt) for term in terms):
                domains.append(domain)
        return domains

    @staticmethod
    def _infer_plan_intent(
        prompt: str,
        entities: list[CopilotResearchPlanEntity],
        context: CopilotRequestContext,
    ) -> str:
        has_ticker = any(entity.kind == "ticker" for entity in entities)
        has_rate_context = any(term in prompt for term in ("rate", "rates", "fed", "cpi", "inflation", "yield"))
        has_portfolio_context = "portfolio" in prompt or context.current_tab == "portfolio"
        has_oil_context = any(term in prompt for term in ("oil", "crude", "brent", "wti"))

        if has_portfolio_context and has_rate_context:
            return "portfolio_rate_shock_research"
        if has_oil_context:
            return "commodity_macro_research"
        if has_ticker and has_rate_context:
            return "single_company_event_research"
        if has_ticker:
            return "single_company_research"
        if context.current_tab and context.current_tab not in {"copilot", "synthesis"}:
            return "active_context_research"
        return "cross_domain_research"

    def _build_domain_plan(
        self,
        *,
        intent: str,
        prompt: str,
        depth_profile: str,
        target_entities: list[CopilotResearchPlanEntity],
        request: CopilotResearchCardRequest,
    ) -> list[CopilotResearchPlanDomain]:
        domain_plan: list[CopilotResearchPlanDomain] = []
        seen: set[str] = set()

        def add(
            domain: str,
            depth: str,
            reason: str,
            *,
            action_type: str = "read_context",
            planned_tools: list[str] | None = None,
            required_context: list[str] | None = None,
        ) -> None:
            if domain in seen:
                return
            seen.add(domain)
            tools = planned_tools or self._default_plan_tools(domain)
            provider_calls = self._estimated_provider_calls(domain, tools)
            domain_plan.append(
                CopilotResearchPlanDomain(
                    domain=domain,
                    depth=depth,
                    reason=reason,
                    action_type=action_type,
                    planned_tools=tools,
                    required_context=required_context or [],
                    estimated_tool_calls=len(tools),
                    estimated_provider_calls=provider_calls,
                    estimated_latency_ms=self._estimated_domain_latency_ms(depth, len(tools), provider_calls),
                )
            )

        if depth_profile == "user_directed":
            directed_domains = self._extract_user_directed_domains(prompt)
            if not directed_domains:
                directed_domains = [self._resolve_domain(request)]
            for domain in directed_domains:
                add(domain, "medium", "The user explicitly named this Gamma domain or asked to use the active context.")
        elif intent == "single_company_research":
            add("fundamentals", "deep", "Single-company research needs filings, normalized statements, peers, DCF, and implied-expectation context.")
            add("equity_research", "medium", "Market and benchmark-relative context helps frame whether the company question is idiosyncratic or factor-driven.")
            add("iv", "medium", "Options context can surface event risk, term structure, and skew caveats if an options surface is available.")
            add("external_context", "light", "Recent news, filings, estimates, or transcript context can add freshness when approved providers are configured.")
        elif intent == "single_company_event_research":
            add("fundamentals", "medium", "Company-specific financial context remains relevant but should not dominate an event-week request.")
            add("macro", "deep", "CPI, Fed, inflation, and rates context are first-order drivers for the stated event lens.")
            add("iv", "deep", "Options term structure and implied move context are central to event-risk framing.")
            add("equity_research", "medium", "Benchmark and peer-relative behavior help separate company-specific movement from macro beta.")
            add("external_context", "medium", "Recent news, calendar, estimates, and filings should be fetched only through approved read-only providers.")
        elif intent == "commodity_macro_research":
            add("commodities", "deep", "Commodity workspace data should anchor the price, curve, spread, inventory, and event read.")
            add("macro", "medium", "Macro context helps separate demand, inflation, USD, and rates effects from commodity-specific supply signals.")
            add("prediction_markets", "medium", "Related event contracts can provide cross-market expectations around geopolitics, policy, or supply disruptions.")
            add("external_context", "medium", "Recent commodity and official event context can add freshness when provider-backed.")
        elif intent == "portfolio_rate_shock_research":
            add("portfolio", "deep", "Portfolio exposure, concentration, cash, and position context are required before interpreting rate sensitivity.")
            add("risk", "deep", "Risk contribution, coverage, correlation, and scenario tools should quantify the shock path.")
            add("macro", "deep", "Rates, policy path, curve, breakeven, and event context define the rate-shock scenario.")
            add("iv", "light", "Options context is optional and only useful if active surfaces exist for dominant exposures.")
        elif intent == "active_context_research":
            active_domain = self._resolve_domain(request)
            add(active_domain, "medium" if depth_profile != "quick" else "light", "The request is anchored to the active Gamma context.")
            if request.synthesis is not None:
                add("synthesis", "medium", "The supplied synthesis scope should be used to compare already-loaded Gamma contexts.")
        else:
            add("synthesis", "medium", "The request is broad and should start from the selected loaded Gamma contexts.")
            add("macro", "light", "Macro is a useful default background lens for broad cross-domain research.")

        if depth_profile == "quick":
            return [
                self._with_plan_depth(item, "light" if item.depth in {"medium", "deep"} else item.depth)
                for item in domain_plan[:3]
            ]
        if depth_profile == "deep" and target_entities:
            return [
                self._with_plan_depth(item, "deep" if item.depth == "medium" else item.depth)
                for item in domain_plan
            ]
        return domain_plan

    @staticmethod
    def _default_plan_tools(domain: str) -> list[str]:
        return {
            "portfolio": ["get_portfolio_positions_summary", "get_portfolio_performance_context"],
            "equity_research": ["get_research_scope_summary", "get_research_coverage_context"],
            "research": ["get_research_scope_summary", "get_research_coverage_context"],
            "macro": ["get_macro_workspace_drilldown", "get_macro_series_history_summary"],
            "commodities": ["get_commodities_workspace_summary"],
            "prediction_markets": ["get_prediction_market_history_summary", "get_prediction_market_flow_context"],
            "crypto": ["get_crypto_price_history_summary", "get_crypto_liquidity_context", "get_crypto_comparison_context"],
            "fundamentals": [
                "get_fundamentals_company_context",
                "get_fundamentals_statement_context",
                "get_fundamentals_peer_context",
                "get_fundamentals_dcf_context",
                "get_fundamentals_reverse_valuation_context",
            ],
            "risk": ["get_risk_coverage_summary", "get_risk_contribution_summary"],
            "iv": ["get_iv_surface_context", "get_iv_session_status"],
            "external_context": ["get_external_context_summary"],
            "synthesis": ["get_synthesis_scope_summary", "get_synthesis_domain_context"],
        }.get(domain, [])

    @staticmethod
    def _with_plan_depth(item: CopilotResearchPlanDomain, depth: str) -> CopilotResearchPlanDomain:
        return replace(
            item,
            depth=depth,
            estimated_latency_ms=CopilotService._estimated_domain_latency_ms(
                depth,
                item.estimated_tool_calls,
                item.estimated_provider_calls,
            ),
        )

    def _estimated_provider_calls(self, domain: str, tools: list[str]) -> int:
        calls = 0
        for tool_name in tools:
            definition = self._tools.get(tool_name)
            if definition is not None and definition.external_provider:
                calls += 1
        return calls

    @staticmethod
    def _estimated_domain_latency_ms(depth: str, tool_calls: int, provider_calls: int) -> int:
        depth_multiplier = {
            "light": 0.7,
            "medium": 1.0,
            "deep": 1.45,
        }.get(depth, 1.0)
        estimate = 250 + (tool_calls * 650 * depth_multiplier) + (provider_calls * 1500)
        return int(round(estimate))

    @staticmethod
    def _execution_budget_for_depth(depth_profile: str) -> _CopilotExecutionBudget:
        return {
            "quick": _CopilotExecutionBudget(
                max_domains=2,
                max_tool_calls=3,
                max_provider_calls=0,
                max_elapsed_ms=2_500,
            ),
            "standard": _CopilotExecutionBudget(
                max_domains=4,
                max_tool_calls=8,
                max_provider_calls=1,
                max_elapsed_ms=8_000,
            ),
            "deep": _CopilotExecutionBudget(
                max_domains=6,
                max_tool_calls=14,
                max_provider_calls=3,
                max_elapsed_ms=20_000,
            ),
            "user_directed": _CopilotExecutionBudget(
                max_domains=5,
                max_tool_calls=10,
                max_provider_calls=1,
                max_elapsed_ms=12_000,
            ),
        }.get(
            depth_profile,
            _CopilotExecutionBudget(
                max_domains=4,
                max_tool_calls=8,
                max_provider_calls=1,
                max_elapsed_ms=8_000,
            ),
        )

    @staticmethod
    def _build_domain_decisions(
        *,
        intent: str,
        domain_plan: list[CopilotResearchPlanDomain],
        request: CopilotResearchCardRequest,
    ) -> list[CopilotResearchPlanDomainDecision]:
        selected = {item.domain: item for item in domain_plan}
        decisions = [
            CopilotResearchPlanDomainDecision(
                domain=item.domain,
                used=True,
                reason=item.reason,
            )
            for item in domain_plan
        ]
        omitted_reasons = CopilotService._omitted_domain_reasons(intent, request)
        for domain in CopilotService._known_research_domains():
            if domain in selected:
                continue
            decisions.append(
                CopilotResearchPlanDomainDecision(
                    domain=domain,
                    used=False,
                    reason=omitted_reasons.get(domain, "Not selected because the prompt did not make this domain material to the bounded plan."),
                )
            )
        return decisions

    @staticmethod
    def _known_research_domains() -> tuple[str, ...]:
        return (
            "portfolio",
            "risk",
            "equity_research",
            "strategy_lab",
            "macro",
            "commodities",
            "prediction_markets",
            "crypto",
            "fundamentals",
            "iv",
            "external_context",
            "synthesis",
        )

    @staticmethod
    def _omitted_domain_reasons(
        intent: str,
        request: CopilotResearchCardRequest,
    ) -> dict[str, str]:
        base = {
            "portfolio": "Portfolio is omitted unless the request asks about the user's book, exposure, or active portfolio context.",
            "risk": "Risk is omitted unless the request needs portfolio/scenario quantification or an active risk result.",
            "equity_research": "Equity Research is omitted unless listed-equity market context helps answer the request.",
            "strategy_lab": "Strategy Lab is omitted unless the request asks about imported strategies, compositions, or backtests.",
            "macro": "Macro is omitted unless rates, inflation, policy, growth, FX, or regime context is material.",
            "commodities": "Commodities is omitted unless the request names a commodity, curve, inventory, spread, or supply/demand theme.",
            "prediction_markets": "Prediction Markets is omitted unless event probabilities or venue expectations add useful context.",
            "crypto": "Crypto is omitted unless the request names a token, crypto sector, DEX/liquidity, or on-chain flow.",
            "fundamentals": "Fundamentals is omitted unless a company, filing, DCF, financial statement, or valuation question is central.",
            "iv": "Options is omitted unless volatility, skew, event risk, or an active IV surface is relevant.",
            "external_context": "External context is omitted unless freshness from approved read-only providers is needed.",
            "synthesis": "Synthesis is omitted unless the request needs comparison across already-loaded Gamma contexts.",
        }
        if intent == "active_context_research":
            active_domain = request.context.current_tab or request.domain
            base["synthesis"] = f"Synthesis is omitted because the active-context request is anchored to `{active_domain}`."
        return base

    @staticmethod
    def _plan_warnings(prompt: str, domain_plan: list[CopilotResearchPlanDomain]) -> list[str]:
        warnings: list[str] = [
            "Planner-only prototype: this preview does not execute tools or fetch provider data yet."
        ]
        if not prompt.strip():
            warnings.append("No prompt was supplied; the plan falls back to active context.")
        if any(item.domain == "external_context" for item in domain_plan):
            warnings.append("External context is planned only through approved read-only provider adapters; general web browsing is not the default path.")
        return warnings

    @staticmethod
    def _context_summary_for_persistence(context: CopilotContextBundle) -> dict[str, Any]:
        return {
            "domain": context.domain,
            "current_tab": context.current_tab,
            "summary_data": context.summary_data,
            "source_ids": [source.source_id for source in context.sources],
            "warnings": list(context.warnings),
            "read_only_safety": context.read_only_safety,
        }

    def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        definition = self._tools.get(tool_name)
        if definition is None:
            return CopilotToolExecution(
                output={"error": f"Unsupported tool: {tool_name}"},
                trace=CopilotToolTrace(
                    tool_name=tool_name,
                    summary="Gamma rejected an unsupported tool call.",
                    arguments=arguments,
                    source_ids=[],
                ),
            )
        try:
            return definition.handler(arguments, context)
        except Exception as exc:
            return CopilotToolExecution(
                output={"error": str(exc)},
                trace=CopilotToolTrace(
                    tool_name=tool_name,
                    summary=f"Gamma tool execution failed: {exc}",
                    arguments=arguments,
                    source_ids=[],
                ),
            )

    def _resolve_domain(self, request: CopilotResearchCardRequest) -> str:
        current_tab = str(request.context.current_tab or "").strip()
        if current_tab in self._context_builders:
            return current_tab
        requested_domain = str(request.domain or "").strip()
        if requested_domain in self._context_builders:
            return requested_domain
        return current_tab or requested_domain

    def _build_context_for_domain(
        self,
        domain: str,
        context: CopilotRequestContext,
    ) -> CopilotContextBundle:
        if domain == "synthesis":
            raise ValueError("Nested synthesis scopes are not supported.")
        builder = self._context_builders.get(domain)
        if builder is None:
            raise ValueError(f"Unsupported synthesis domain: {domain}")
        nested_context = context
        if not str(nested_context.current_tab or "").strip():
            nested_context = replace(nested_context, current_tab=domain)
        nested_request = CopilotResearchCardRequest(
            domain=domain,
            context=nested_context,
        )
        return builder(nested_request)

    def _build_external_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        prompt = str(request.prompt or "").strip()
        target_entities = self._extract_plan_entities(prompt, request.context)
        profile = self._external_context_profile(prompt, target_entities)
        warnings: list[str] = []
        if self.news_service is None:
            warnings.append("External news/event context is unavailable because no NewsService is configured.")
        return CopilotContextBundle(
            domain="external_context",
            current_tab=request.context.current_tab or "external_context",
            summary_data={
                "workspace_mode": request.context.workspace_mode or "research",
                "prompt": prompt,
                "context_types": profile["context_types"],
                "target_entities": [asdict(entity) for entity in target_entities],
                "provider_boundaries": self._external_provider_boundaries(
                    news_configured=self.news_service is not None,
                    news_freshness=None,
                ),
                "warnings": warnings,
            },
            tool_state={
                "prompt": prompt,
                "target_entities": target_entities,
                "external_context_profile": profile,
            },
            sources=[
                CopilotSourceRef(
                    source_id="external_context.boundary",
                    label="External context provider boundary",
                    kind="provider_boundary",
                    provider="gamma",
                    origin="gamma.copilot.external_context",
                    description="Gamma-approved read-only external-context boundary for Copilot plan execution.",
                    retrieved_at=now_utc(),
                )
            ],
            warnings=warnings,
        )

    def _build_synthesis_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        synthesis = request.synthesis
        if synthesis is None:
            raise ValueError("Copilot synthesis requires an explicit synthesis scope.")

        included_contexts: list[dict[str, Any]] = []
        included_bundles: dict[str, CopilotContextBundle] = {}
        sources: dict[str, CopilotSourceRef] = {
            "synthesis.scope": CopilotSourceRef(
                source_id="synthesis.scope",
                label="Cross-context synthesis scope",
                kind="workspace",
                provider="gamma",
                origin="gamma.copilot.synthesis",
                description="Shell-level Gamma synthesis scope assembled from included loaded contexts.",
                retrieved_at=None,
            )
        }
        warnings: list[str] = []

        for scope in synthesis.included_scopes:
            domain = str(scope.domain or "").strip()
            if not domain:
                continue
            if domain in included_bundles:
                continue
            bundle = self._build_context_for_domain(domain, scope.context)
            included_bundles[domain] = bundle
            for source in bundle.sources:
                sources[source.source_id] = source
            warnings.extend(bundle.warnings)
            included_contexts.append(
                {
                    "domain": domain,
                    "label": scope.label or domain.replace("_", " ").title(),
                    "context_fingerprint": scope.context_fingerprint,
                    "current_tab": bundle.current_tab,
                    "summary": bundle.summary_data,
                    "source_ids": [source.source_id for source in bundle.sources],
                    "source_count": len(bundle.sources),
                    "warnings": list(bundle.warnings),
                    "warning_count": len(bundle.warnings),
                }
            )

        if len(included_contexts) < 2:
            raise ValueError("Copilot synthesis requires at least two distinct loaded Gamma contexts.")

        return CopilotContextBundle(
            domain="synthesis",
            current_tab=request.context.current_tab or "synthesis",
            summary_data={
                "workspace_mode": request.context.workspace_mode,
                "active_tab": synthesis.active_tab,
                "scope_size": len(included_contexts),
                "included_domains": [item["domain"] for item in included_contexts],
                "included_contexts": included_contexts,
            },
            tool_state={
                "included_bundles": included_bundles,
                "included_contexts": included_contexts,
                "active_tab": synthesis.active_tab,
            },
            sources=list(sources.values()),
            warnings=dedupe_warnings(warnings),
        )

    def _build_portfolio_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.portfolio_state or {}
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("Portfolio copilot requires a portfolio snapshot.")
        history = state.get("history") if isinstance(state.get("history"), dict) else None
        performance = state.get("performance") if isinstance(state.get("performance"), dict) else None
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "portfolio",
            "snapshot": summarize_portfolio_snapshot(snapshot),
            "history": summarize_portfolio_history(history),
            "performance": summarize_portfolio_performance(performance),
        }
        warnings = dedupe_warnings(
            snapshot.get("warnings", []),
            (performance or {}).get("warnings", []),
        )
        sources = [
            CopilotSourceRef(
                source_id="portfolio.snapshot",
                label="Portfolio snapshot",
                kind="workspace",
                provider="gamma",
                origin="gamma.portfolio.snapshot",
                description="Current portfolio snapshot returned by Gamma.",
                retrieved_at=snapshot.get("timestamp"),
            )
        ]
        if history is not None:
            latest_history_ts = history.get("points", [])[-1].get("timestamp") if history.get("points") else None
            sources.append(
                CopilotSourceRef(
                    source_id="portfolio.history",
                    label="Portfolio local history",
                    kind="timeseries",
                    provider="gamma",
                    origin="gamma.portfolio.history",
                    description="Local portfolio history already loaded in Gamma.",
                    retrieved_at=latest_history_ts,
                )
            )
        if performance is not None:
            performance_points = performance.get("performance_points", [])
            latest_performance_ts = performance_points[-1].get("timestamp") if performance_points else None
            sources.append(
                CopilotSourceRef(
                    source_id="portfolio.performance",
                    label="Portfolio performance overlay",
                    kind="analytics",
                    provider="gamma",
                    origin="gamma.portfolio.performance",
                    description="Current portfolio performance comparison returned by Gamma.",
                    retrieved_at=latest_performance_ts,
                )
            )
        return CopilotContextBundle(
            domain="portfolio",
            current_tab=request.context.current_tab or "portfolio",
            summary_data=summary_data,
            tool_state={
                "snapshot": snapshot,
                "history": history,
                "performance": performance,
            },
            sources=sources,
            warnings=warnings,
        )

    def _build_research_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.research_state or {}
        result = state.get("result")
        if not isinstance(result, dict):
            raise ValueError("Research copilot requires an active research result.")
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "research",
            "research": summarize_research_result(result),
        }
        warnings = dedupe_warnings(result.get("warnings", []))
        performance_points = result.get("performance_points", [])
        sources = [
            CopilotSourceRef(
                source_id="research.result",
                label="Research analysis result",
                kind="workspace",
                provider="gamma",
                origin="gamma.research.analyze",
                description="Active research analysis result returned by Gamma.",
                retrieved_at=performance_points[-1].get("timestamp") if performance_points else None,
            )
        ]
        if isinstance(result.get("snapshot"), dict):
            sources.append(
                CopilotSourceRef(
                    source_id="research.snapshot",
                    label="Research forwarded snapshot",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.research.snapshot",
                    description="Synthetic or single-name snapshot attached to the active research run.",
                    retrieved_at=result["snapshot"].get("timestamp"),
                )
            )
        return CopilotContextBundle(
            domain="research",
            current_tab=request.context.current_tab or "research",
            summary_data=summary_data,
            tool_state={"result": result},
            sources=sources,
            warnings=warnings,
        )

    def _build_equity_research_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.research_state or {}
        result = state.get("result")
        overview = state.get("overview")
        if not isinstance(result, dict) and not isinstance(overview, dict):
            raise ValueError("Equity Research copilot requires an active overview or research result.")
        summary_data: dict[str, Any] = {
            "workspace_mode": request.context.workspace_mode or "research",
        }
        warnings: list[str] = []
        sources: list[CopilotSourceRef] = []
        tool_state: dict[str, Any] = {}
        if isinstance(result, dict):
            summary_data["research"] = summarize_research_result(result)
            warnings.extend(dedupe_warnings(result.get("warnings", [])))
            performance_points = result.get("performance_points", [])
            sources.append(
                CopilotSourceRef(
                    source_id="research.result",
                    label="Equity research analysis result",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.research.analyze",
                    description="Active Equity Research analysis result returned by Gamma.",
                    retrieved_at=performance_points[-1].get("timestamp") if performance_points else None,
                )
            )
            tool_state["result"] = result
        if isinstance(overview, dict):
            summary_data["overview"] = {
                "universe": overview.get("universe_label") or overview.get("universe_id"),
                "benchmark": overview.get("benchmark_symbol"),
                "nodes": len(overview.get("nodes", [])) if isinstance(overview.get("nodes"), list) else 0,
                "warnings": overview.get("warnings", []),
            }
            warnings.extend(dedupe_warnings(overview.get("warnings", [])))
            sources.append(
                CopilotSourceRef(
                    source_id="equity_research.overview",
                    label="Equity Research overview",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.research.overview",
                    description="Active Equity Research market-map overview.",
                    retrieved_at=overview.get("retrieved_at"),
                )
            )
        return CopilotContextBundle(
            domain="equity_research",
            current_tab=request.context.current_tab or "equity_research",
            summary_data=summary_data,
            tool_state=tool_state,
            sources=sources,
            warnings=dedupe_warnings(warnings),
        )

    def _build_strategy_lab_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.strategy_lab_state or {}
        imported_result = state.get("imported_result")
        composition = state.get("composition")
        compare_result = state.get("compare_result")
        if not any(isinstance(item, dict) for item in (imported_result, composition, compare_result)):
            raise ValueError("Strategy Lab copilot requires an active import, composition, or comparison.")
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "research",
            "imported_result": imported_result if isinstance(imported_result, dict) else None,
            "composition": composition if isinstance(composition, dict) else None,
            "compare_result": compare_result if isinstance(compare_result, dict) else None,
        }
        warnings = dedupe_warnings(
            (imported_result or {}).get("warnings", []) if isinstance(imported_result, dict) else [],
            (composition or {}).get("warnings", []) if isinstance(composition, dict) else [],
            (compare_result or {}).get("warnings", []) if isinstance(compare_result, dict) else [],
        )
        sources = [
            CopilotSourceRef(
                source_id="strategy_lab.context",
                label="Strategy Lab context",
                kind="workspace",
                provider="gamma",
                origin="gamma.strategy_lab",
                description="Active Strategy Lab import, composition, or comparison context.",
                retrieved_at=(composition or imported_result or {}).get("retrieved_at")
                if isinstance(composition or imported_result, dict)
                else None,
            )
        ]
        return CopilotContextBundle(
            domain="strategy_lab",
            current_tab=request.context.current_tab or "strategy_lab",
            summary_data=summary_data,
            tool_state=summary_data,
            sources=sources,
            warnings=warnings,
        )

    def _build_risk_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.risk_state or {}
        result = state.get("result")
        if not isinstance(result, dict):
            raise ValueError("Risk copilot requires an active risk result.")
        snapshot = state.get("snapshot") if isinstance(state.get("snapshot"), dict) else None
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "portfolio",
            "risk": summarize_risk_result(result),
            "snapshot": summarize_portfolio_snapshot(snapshot),
        }
        warnings = dedupe_warnings(result.get("warnings", []), (snapshot or {}).get("warnings", []))
        sources = [
            CopilotSourceRef(
                source_id="risk.result",
                label="Risk computation result",
                kind="analytics",
                provider="gamma",
                origin="gamma.risk.compute",
                description="Active risk computation payload returned by Gamma.",
                retrieved_at=None,
            )
        ]
        if snapshot is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="risk.snapshot",
                    label="Risk snapshot basis",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.risk.snapshot",
                    description="Snapshot used as the basis for the active risk result.",
                    retrieved_at=snapshot.get("timestamp"),
                )
            )
        return CopilotContextBundle(
            domain="risk",
            current_tab=request.context.current_tab or "risk",
            summary_data=summary_data,
            tool_state={
                "result": result,
                "snapshot": snapshot,
            },
            sources=sources,
            warnings=warnings,
        )

    def _build_iv_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.iv_state or {}
        surface = state.get("surface") if isinstance(state.get("surface"), dict) else None
        session = state.get("session") if isinstance(state.get("session"), dict) else None
        active_surface = resolve_iv_surface(surface, session)
        if not isinstance(active_surface, dict):
            raise ValueError("Options copilot requires a loaded options surface.")
        summary = summarize_iv_state(surface, session)
        if summary is None:
            raise ValueError("Options copilot requires a loaded options surface.")
        warnings = dedupe_warnings(summary.get("warnings", []))
        sources = [
            CopilotSourceRef(
                source_id="iv.surface",
                label="Options surface snapshot",
                kind="workspace",
                provider="gamma",
                origin="gamma.iv.surface",
                description="Loaded options implied-volatility surface payload from Gamma.",
                retrieved_at=active_surface.get("timestamp"),
            )
        ]
        if session is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="iv.session",
                    label="IV session status",
                    kind="status",
                    provider="gamma",
                    origin="gamma.iv.session",
                    description="Current Options session state from Gamma.",
                    retrieved_at=active_surface.get("timestamp"),
                )
            )
        return CopilotContextBundle(
            domain="iv",
            current_tab=request.context.current_tab or "iv",
            summary_data={
                "workspace_mode": request.context.workspace_mode,
                "iv": summary,
            },
            tool_state={
                "surface": surface,
                "session": session,
            },
            sources=sources,
            warnings=warnings,
        )

    def _build_macro_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        macro = request.context.macro or MacroCopilotContext()
        snapshot_request = MacroSnapshotRequest(
            region=macro.region,
            timeframe=macro.timeframe,
            theme=macro.theme,
            comparison_region=macro.comparison_region,
            force_refresh=False,
        )
        try:
            snapshot = self.macro_service.get_snapshot(snapshot_request)
            divergences = self.macro_service.get_divergences(snapshot_request)
            events = self.macro_service.get_events(region=macro.region, force_refresh=False)
        except Exception as exc:
            warning = f"Macro context is degraded because a macro provider failed: {exc}"
            return CopilotContextBundle(
                domain="macro",
                current_tab=request.context.current_tab or "macro",
                summary_data={
                    "mode": macro.mode,
                    "region": macro.region,
                    "timeframe": macro.timeframe,
                    "theme": macro.theme,
                    "comparison_region": macro.comparison_region,
                    "focus_items": [],
                    "snapshot_cards": [],
                    "top_divergences": [],
                    "rates_policy": None,
                    "upcoming_events": [],
                    "warnings": [warning],
                },
                sources=[
                    CopilotSourceRef(
                        source_id="macro.degraded",
                        label="Macro workspace unavailable",
                        kind="warning",
                        provider="gamma",
                        origin="gamma.macro.degraded_context",
                        description="Macro context could not be fully assembled because an upstream macro provider failed.",
                    )
                ],
                warnings=[warning],
            )
        summary_data = {
            "mode": macro.mode,
            "region": macro.region,
            "timeframe": macro.timeframe,
            "theme": macro.theme,
            "comparison_region": snapshot.comparison_region,
            "focus_items": [
                {
                    "focus_id": item.focus_id,
                    "title": item.title,
                    "summary": item.summary,
                    "why_now": item.why_now,
                    "mode_target": item.mode_target,
                }
                for item in snapshot.focus_items[:4]
            ],
            "snapshot_cards": [self._macro_card_summary(card) for card in snapshot.snapshot_cards[:4]],
            "top_divergences": [
                {
                    "divergence_id": row.divergence_id,
                    "theme": row.theme,
                    "headline": row.headline,
                    "summary": row.summary,
                    "label": row.label,
                    "research_focus": row.research_focus,
                }
                for row in divergences[:4]
            ],
            "rates_policy": self._macro_rates_policy_summary(snapshot.rates_policy),
            "upcoming_events": [
                {
                    "event_id": item.event_id,
                    "title": item.title,
                    "category": item.category,
                    "scheduled_at": item.scheduled_at.isoformat(),
                    "importance": item.importance,
                }
                for item in events[:5]
            ],
            "warnings": snapshot.warnings,
        }
        sources = [
            CopilotSourceRef(
                source_id="macro.snapshot",
                label="Macro snapshot workspace",
                kind="workspace",
                provider=snapshot.source_provider,
                origin=snapshot.origin,
                description="Current macro snapshot payload assembled by Gamma.",
                retrieved_at=snapshot.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="macro.divergences",
                label="Macro divergences",
                kind="analytics",
                provider=snapshot.source_provider,
                origin="gamma.macro.divergences",
                description="Current divergence rankings for the selected macro context.",
                retrieved_at=snapshot.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="macro.events",
                label="Macro events",
                kind="calendar",
                provider=events[0].source_provider if events else snapshot.source_provider,
                origin=events[0].origin if events else "gamma.macro.events",
                description="Upcoming macro catalysts for the selected region.",
                retrieved_at=events[0].retrieved_at if events else snapshot.retrieved_at,
            ),
        ]
        return CopilotContextBundle(
            domain="macro",
            current_tab=request.context.current_tab or "macro",
            summary_data=summary_data,
            sources=sources,
            warnings=list(snapshot.warnings),
        )

    def _build_commodities_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.commodities_state or {}
        workspace = state.get("workspace")
        if not isinstance(workspace, dict):
            raise ValueError("Commodities copilot requires a loaded commodities workspace.")
        summary = summarize_commodities_workspace(workspace)
        if summary is None:
            raise ValueError("Commodities copilot requires a loaded commodities workspace.")
        coverage = workspace.get("coverage") if isinstance(workspace.get("coverage"), dict) else {}
        warnings = dedupe_warnings(workspace.get("warnings", []), coverage.get("caveats", []))
        sources = [
            CopilotSourceRef(
                source_id="commodities.workspace",
                label="Commodities workspace",
                kind="workspace",
                provider=str(workspace.get("source_provider") or coverage.get("source_provider") or "gamma"),
                origin=str(workspace.get("origin") or "gamma.commodities.workspace"),
                description="Loaded Commodities workspace payload assembled by Gamma.",
                retrieved_at=workspace.get("retrieved_at") or coverage.get("retrieved_at"),
            )
        ]
        source_timestamp = coverage.get("source_timestamp")
        if source_timestamp:
            sources.append(
                CopilotSourceRef(
                    source_id="commodities.provider_coverage",
                    label="Commodities provider coverage",
                    kind="provenance",
                    provider=str(coverage.get("source_provider") or coverage.get("provider_id") or "gamma"),
                    origin=str(coverage.get("origin") or "gamma.commodities.coverage"),
                    description="Provider coverage, freshness, and caveats for the loaded Commodities workspace.",
                    retrieved_at=coverage.get("retrieved_at") or source_timestamp,
                )
            )
        return CopilotContextBundle(
            domain="commodities",
            current_tab=request.context.current_tab or "commodities",
            summary_data={"workspace_mode": request.context.workspace_mode or "research", "commodities": summary},
            tool_state={"workspace": workspace},
            sources=sources,
            warnings=warnings,
        )

    def _build_prediction_market_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        market_id = (request.context.prediction_market_id or "").strip()
        if not market_id:
            raise ValueError("Prediction Markets copilot requires a selected market.")

        detail = self.prediction_market_service.get_market_detail(market_id)
        if detail is None:
            raise ValueError(f"Prediction market not found: {market_id}")
        history = self.prediction_market_service.get_probability_history(market_id)
        wallet = self.prediction_market_service.get_wallet_summary(market_id)
        related = self.prediction_market_service.get_related_markets(market_id)
        calibration = self.prediction_market_service.get_calibration_summary(market_id)

        summary_data = {
            "market_id": detail.market_id,
            "selected_market": {
                "title": detail.title,
                "subtitle": detail.subtitle,
                "venue": detail.venue,
                "status": detail.status,
                "category": detail.category,
                "description": detail.description,
                "current_probability": detail.current_probability,
                "probability_label": detail.probability_label,
                "recent_price_change": detail.recent_price_change,
                "end_time": detail.end_time.isoformat() if detail.end_time else None,
                "research_score": detail.research_score,
                "research_rationale": detail.research_rationale,
                "freshness": detail.freshness.__dict__ if detail.freshness is not None else None,
            },
            "history_summary": self._prediction_history_summary(history),
            "wallet_summary": {
                "total_trades": wallet.total_trades if wallet else 0,
                "total_notional": wallet.total_notional if wallet else 0.0,
                "top_participant_share": wallet.top_participant_share if wallet else None,
                "concentration_hhi": wallet.concentration_hhi if wallet else None,
                "participants": [
                    {
                        "display_name": row.display_name,
                        "side": row.side,
                        "trade_count": row.trade_count,
                        "total_size": row.total_size,
                        "current_edge": row.current_edge,
                    }
                    for row in (wallet.participants[:5] if wallet else [])
                ],
                "warnings": list(wallet.warnings if wallet else []),
            },
            "related_markets": [
                {
                    "market_id": row.market_id,
                    "title": row.title,
                    "venue": row.venue,
                    "probability": row.probability,
                    "price_gap": row.price_gap,
                    "relationship": row.relationship,
                    "note": row.note,
                }
                for row in related[:5]
            ],
            "calibration_summary": {
                "venue": calibration.venue if calibration else detail.venue,
                "sample_size": calibration.sample_size if calibration else 0,
                "buckets": [
                    {
                        "label": bucket.label,
                        "sample_size": bucket.sample_size,
                        "average_probability": bucket.average_probability,
                        "realized_frequency": bucket.realized_frequency,
                    }
                    for bucket in (calibration.buckets[:5] if calibration else [])
                ],
                "warnings": list(calibration.warnings if calibration else []),
            },
        }
        sources = [
            CopilotSourceRef(
                source_id="prediction.detail",
                label="Prediction market detail",
                kind="workspace",
                provider=detail.source_provider,
                origin=detail.origin,
                description="Selected prediction market detail payload.",
                retrieved_at=detail.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="prediction.history",
                label="Prediction market history",
                kind="timeseries",
                provider=history[-1].source_provider if history else detail.source_provider,
                origin=history[-1].origin if history else "gamma.prediction.history",
                description="Primary-outcome probability history for the selected market.",
                retrieved_at=history[-1].retrieved_at if history else detail.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="prediction.wallet",
                label="Prediction market wallet flow",
                kind="flow",
                provider=wallet.source_provider if wallet else detail.source_provider,
                origin=wallet.origin if wallet else "gamma.prediction.wallet",
                description="Participant and flow summary for the selected market.",
                retrieved_at=wallet.retrieved_at if wallet else detail.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="prediction.related",
                label="Prediction market related contracts",
                kind="consistency",
                provider=related[0].source_provider if related else detail.source_provider,
                origin=related[0].origin if related else "gamma.prediction.related",
                description="Related or analogous contracts linked to the selected market.",
                retrieved_at=related[0].retrieved_at if related else detail.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="prediction.calibration",
                label="Prediction market calibration",
                kind="analytics",
                provider=calibration.source_provider if calibration else detail.source_provider,
                origin=calibration.origin if calibration else "gamma.prediction.calibration",
                description="Historical calibration summary for the selected venue.",
                retrieved_at=calibration.retrieved_at if calibration else detail.retrieved_at,
            ),
        ]
        warnings = []
        if wallet is not None:
            warnings.extend(wallet.warnings)
        if calibration is not None:
            warnings.extend(calibration.warnings)
        return CopilotContextBundle(
            domain="prediction_markets",
            current_tab=request.context.current_tab or "prediction_markets",
            summary_data=summary_data,
            sources=sources,
            warnings=warnings,
        )

    def _build_crypto_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        token_id = (request.context.crypto_token_id or "").strip()
        if not token_id:
            raise ValueError("Crypto copilot requires a selected token.")

        detail = self.crypto_service.get_token_detail(token_id)
        if detail is None:
            raise ValueError(f"Crypto token not found: {token_id}")
        history = self.crypto_service.get_price_history(token_id, days=30)
        liquidity = self.crypto_service.get_dex_liquidity(token_id)
        comparison = self.crypto_service.get_comparison(token_id)

        summary_data = {
            "token_id": detail.token_id,
            "selected_token": {
                "name": detail.name,
                "symbol": detail.symbol.upper(),
                "chain": detail.chain,
                "asset_platform_id": detail.asset_platform_id,
                "geckoterminal_network": detail.geckoterminal_network,
                "contract_address": detail.contract_address,
                "market_cap_rank": detail.market_cap_rank,
                "current_price": detail.current_price,
                "market_cap": detail.market_cap,
                "fully_diluted_valuation": detail.fully_diluted_valuation,
                "total_volume": detail.total_volume,
                "turnover_ratio_24h": detail.turnover_ratio_24h,
                "fdv_premium_ratio": detail.fdv_premium_ratio,
                "price_change_pct_24h": detail.price_change_pct_24h,
                "price_change_pct_7d": detail.price_change_pct_7d,
                "price_change_pct_30d": detail.price_change_pct_30d,
                "screen_score": detail.screen_score,
                "screen_rationale": detail.screen_rationale,
                "categories": list(detail.categories[:8]),
            },
            "price_history_summary": self._crypto_price_history_summary(history),
            "liquidity_summary": {
                "lookup_strategy": liquidity.lookup_strategy if liquidity else None,
                "matched_networks": list(liquidity.matched_networks if liquidity else []),
                "total_reserve_usd": liquidity.total_reserve_usd if liquidity else None,
                "total_volume_24h": liquidity.total_volume_24h if liquidity else None,
                "dominant_dex": liquidity.dominant_dex if liquidity else None,
                "warnings": list(liquidity.warnings if liquidity else []),
                "top_pools": [
                    {
                        "network": row.network,
                        "dex": row.dex,
                        "pair_name": row.pair_name,
                        "reserve_usd": row.reserve_usd,
                        "volume_24h": row.volume_24h,
                        "price_change_pct_24h": row.price_change_pct_24h,
                    }
                    for row in (liquidity.pools[:5] if liquidity else [])
                ],
            },
            "comparison_summary": (
                {
                    "target_kind": comparison.target_kind,
                    "target_id": comparison.target_id,
                    "target_label": comparison.target_label,
                    "price_gap_pct_7d": comparison.price_gap_pct_7d,
                    "price_gap_pct_30d": comparison.price_gap_pct_30d,
                    "market_cap_ratio": comparison.market_cap_ratio,
                    "turnover_gap": comparison.turnover_gap,
                    "summary": comparison.summary,
                }
                if comparison is not None
                else None
            ),
        }
        sources = [
            CopilotSourceRef(
                source_id="crypto.detail",
                label="Crypto token detail",
                kind="workspace",
                provider=detail.source_provider,
                origin=detail.origin,
                description="Selected crypto token detail payload.",
                retrieved_at=detail.retrieved_at,
            ),
            CopilotSourceRef(
                source_id="crypto.history",
                label="Crypto price history",
                kind="timeseries",
                provider=history[-1].source_provider if history else detail.source_provider,
                origin=history[-1].origin if history else "gamma.crypto.history",
                description="Selected crypto token price history.",
                retrieved_at=history[-1].retrieved_at if history else detail.retrieved_at,
            ),
        ]
        if liquidity is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="crypto.liquidity",
                    label="Crypto DEX liquidity",
                    kind="flow",
                    provider=liquidity.source_provider,
                    origin=liquidity.origin,
                    description="DEX liquidity summary for the selected crypto token.",
                    retrieved_at=liquidity.retrieved_at,
                )
            )
        if comparison is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="crypto.comparison",
                    label="Crypto comparison",
                    kind="analytics",
                    provider=comparison.source_provider,
                    origin=comparison.origin,
                    description="Relative token or basket comparison for the selected crypto token.",
                    retrieved_at=comparison.retrieved_at,
                )
            )
        return CopilotContextBundle(
            domain="crypto",
            current_tab=request.context.current_tab or "crypto",
            summary_data=summary_data,
            tool_state={
                "token_id": detail.token_id,
            },
            sources=sources,
            warnings=dedupe_warnings(liquidity.warnings if liquidity is not None else []),
        )

    def _build_fundamentals_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        ticker = self._fundamentals_ticker_from_request(request)
        overview = self.fundamentals_service.get_overview(ticker)
        if overview is None:
            raise ValueError(f"Fundamentals company not found: {ticker}")
        peers = self.fundamentals_service.get_peers(ticker)
        dcf = self.fundamentals_service.get_dcf_model(ticker)
        reverse = self.fundamentals_service.get_reverse_valuation(ticker)
        reference = self.fundamentals_service.get_reference(ticker)
        headline_metrics = [
            {
                "metric_id": metric.metric_id,
                "label": metric.label,
                "display_value": metric.display_value,
                "value": metric.value,
                "source_provider": metric.source_provider,
                "origin": metric.origin,
                "transformation_note": metric.transformation_note,
            }
            for metric in overview.headline_metrics[:10]
        ]
        dcf_summaries = [
            self._fundamentals_dcf_summary(scenario.summary)
            for scenario in (dcf.scenarios if dcf else [])
            if scenario.summary is not None
        ]
        reverse_drivers = [
            {
                "driver_id": driver.driver_id,
                "label": driver.label,
                "implied_value": driver.implied_value,
                "display_value": driver.display_value,
                "base_display_value": driver.base_display_value,
                "gap_display_value": driver.gap_display_value,
                "success": driver.success,
                "warnings": list(driver.warnings),
            }
            for driver in (reverse.drivers[:5] if reverse else [])
        ]
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "research",
            "ticker": overview.company.ticker,
            "company": {
                "name": overview.company.name,
                "exchange": overview.company.exchange,
                "sic_description": overview.company.sic_description,
                "latest_report_period": overview.company.latest_report_period.isoformat() if overview.company.latest_report_period else None,
                "latest_filing_date": overview.company.latest_filing_date.isoformat() if overview.company.latest_filing_date else None,
            },
            "company_summary": {
                "summary": overview.company_summary.summary if overview.company_summary else None,
                "source_form": overview.company_summary.source_form if overview.company_summary else None,
                "accession_number": overview.company_summary.accession_number if overview.company_summary else None,
                "section": overview.company_summary.section if overview.company_summary else None,
                "model_provider": overview.company_summary.model_provider if overview.company_summary else None,
                "origin": overview.company_summary.origin if overview.company_summary else None,
                "warnings": list(overview.company_summary.warnings) if overview.company_summary else [],
            },
            "headline_metrics": headline_metrics,
            "peer_basket": {
                "label": peers.peer_basket.basket_label if peers else overview.peer_basket.basket_label if overview.peer_basket else None,
                "tickers": list(peers.peer_basket.display_order if peers else overview.peer_basket.display_order if overview.peer_basket else []),
                "user_edited": peers.peer_basket.user_edited if peers else overview.peer_basket.user_edited if overview.peer_basket else False,
            },
            "dcf": {
                "active_scenario_id": dcf.active_scenario_id if dcf else None,
                "summaries": dcf_summaries,
                "warnings": list(dcf.warnings if dcf else []),
            },
            "reverse_valuation": {
                "current_price": reverse.current_price if reverse else None,
                "target_enterprise_value": reverse.target_enterprise_value if reverse else None,
                "drivers": reverse_drivers,
                "warnings": list(reverse.warnings if reverse else []),
            },
            "reference": {
                "filings": len(reference.filings) if reference else len(overview.filings),
                "trace_rows": len(reference.inspection.traces) if reference and reference.inspection else 0,
                "coverage_warnings": len(reference.inspection.warnings) if reference and reference.inspection else 0,
            },
        }
        sources = [
            CopilotSourceRef(
                source_id="fundamentals.company",
                label="Fundamentals company context",
                kind="workspace",
                provider=overview.company.source_provider,
                origin=overview.company.origin,
                description="Selected company profile, filing metadata, headline metrics, and warnings.",
                retrieved_at=overview.company.retrieved_at,
            )
        ]
        if overview.company_summary is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="fundamentals.company_summary",
                    label="Fundamentals company business summary",
                    kind="filing",
                    provider=overview.company_summary.source_provider,
                    origin=overview.company_summary.origin,
                    description="Business summary sourced from the latest annual filing business section, with metadata fallback when extraction is unavailable.",
                    retrieved_at=overview.company_summary.retrieved_at,
                )
            )
        if dcf is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="fundamentals.dcf",
                    label="Fundamentals DCF model",
                    kind="analytics",
                    provider=dcf.source_provider,
                    origin=dcf.origin,
                    description="Bear/Base/Bull DCF model and sensitivity context.",
                    retrieved_at=dcf.retrieved_at,
                )
            )
        if reverse is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="fundamentals.reverse_valuation",
                    label="Fundamentals reverse valuation",
                    kind="analytics",
                    provider=reverse.source_provider,
                    origin=reverse.origin,
                    description="Market-implied expectation outputs derived by Gamma.",
                    retrieved_at=reverse.retrieved_at,
                )
            )
        if reference is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="fundamentals.reference",
                    label="Fundamentals reference and filings",
                    kind="filing",
                    provider=reference.source_provider,
                    origin=reference.origin,
                    description="SEC filing chronology and raw-versus-normalized source trace.",
                    retrieved_at=reference.retrieved_at,
                )
            )
        return CopilotContextBundle(
            domain="fundamentals",
            current_tab=request.context.current_tab or "fundamentals",
            summary_data=summary_data,
            tool_state={"ticker": overview.company.ticker},
            sources=sources,
            warnings=dedupe_warnings(
                overview.warnings,
                peers.warnings if peers else [],
                dcf.warnings if dcf else [],
                reverse.warnings if reverse else [],
                reference.warnings if reference else [],
            ),
        )

    def _tool_get_portfolio_positions_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        snapshot = self._portfolio_snapshot_from_bundle(context)
        source = CopilotSourceRef(
            source_id="portfolio.snapshot.drilldown",
            label="Portfolio snapshot drilldown",
            kind="workspace",
            provider="gamma",
            origin="gamma.portfolio.snapshot",
            description="Expanded position and exposure summary for the active Gamma portfolio.",
            retrieved_at=snapshot.get("timestamp"),
        )
        output = summarize_portfolio_snapshot(snapshot, position_limit=10, bucket_limit=8)
        return CopilotToolExecution(
            output=output or {},
            trace=CopilotToolTrace(
                tool_name="get_portfolio_positions_summary",
                summary="Expanded the active portfolio into top positions, exposure, and concentration context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_portfolio_performance_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        performance = self._portfolio_performance_from_bundle(context)
        history = self._portfolio_history_from_bundle(context)
        sources: list[CopilotSourceRef] = []
        source_ids: list[str] = []

        if performance is not None:
            performance_points = performance.get("performance_points", [])
            sources.append(
                CopilotSourceRef(
                    source_id="portfolio.performance.drilldown",
                    label="Portfolio performance drilldown",
                    kind="analytics",
                    provider="gamma",
                    origin="gamma.portfolio.performance",
                    description="Expanded portfolio performance and benchmark context.",
                    retrieved_at=performance_points[-1].get("timestamp") if performance_points else None,
                )
            )
            source_ids.append("portfolio.performance.drilldown")
        if history is not None:
            history_points = history.get("points", [])
            sources.append(
                CopilotSourceRef(
                    source_id="portfolio.history.drilldown",
                    label="Portfolio history drilldown",
                    kind="timeseries",
                    provider="gamma",
                    origin="gamma.portfolio.history",
                    description="Expanded local portfolio history context.",
                    retrieved_at=history_points[-1].get("timestamp") if history_points else None,
                )
            )
            source_ids.append("portfolio.history.drilldown")

        output = {
            "performance": summarize_portfolio_performance(performance),
            "history": summarize_portfolio_history(history),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_portfolio_performance_context",
                summary="Expanded the active portfolio performance overlay and local-history context.",
                arguments={},
                source_ids=source_ids,
            ),
            sources=sources,
        )

    def _tool_get_research_scope_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        result = self._research_result_from_bundle(context)
        performance_points = result.get("performance_points", [])
        sources = [
            CopilotSourceRef(
                source_id="research.result.drilldown",
                label="Research scope drilldown",
                kind="workspace",
                provider="gamma",
                origin="gamma.research.analyze",
                description="Expanded active research scope, weights, and structure context.",
                retrieved_at=performance_points[-1].get("timestamp") if performance_points else None,
            )
        ]
        if isinstance(result.get("snapshot"), dict):
            sources.append(
                CopilotSourceRef(
                    source_id="research.snapshot.drilldown",
                    label="Research snapshot drilldown",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.research.snapshot",
                    description="Expanded snapshot attached to the active research run.",
                    retrieved_at=result["snapshot"].get("timestamp"),
                )
            )
        return CopilotToolExecution(
            output=summarize_research_result(result, weight_limit=10, constituent_limit=10) or {},
            trace=CopilotToolTrace(
                tool_name="get_research_scope_summary",
                summary="Expanded the active research scope into weights, structure, and benchmark context.",
                arguments={},
                source_ids=[source.source_id for source in sources],
            ),
            sources=sources,
        )

    def _tool_get_research_coverage_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        result = self._research_result_from_bundle(context)
        performance_points = result.get("performance_points", [])
        source = CopilotSourceRef(
            source_id="research.coverage.drilldown",
            label="Research coverage drilldown",
            kind="analytics",
            provider="gamma",
            origin="gamma.research.coverage",
            description="Expanded research coverage and constituent context for the active run.",
            retrieved_at=performance_points[-1].get("timestamp") if performance_points else None,
        )
        research_summary = summarize_research_result(result, weight_limit=12, constituent_limit=12) or {}
        output = {
            "coverage": research_summary.get("coverage"),
            "top_constituents": research_summary.get("top_constituents"),
            "best_constituent": research_summary.get("best_constituent"),
            "worst_constituent": research_summary.get("worst_constituent"),
            "weighted_leader": research_summary.get("weighted_leader"),
            "warnings": research_summary.get("warnings", []),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_research_coverage_context",
                summary="Expanded the active research result into coverage and constituent-level context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_macro_workspace_drilldown(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        macro_context = self._macro_context_from_bundle(context)
        snapshot_request = MacroSnapshotRequest(
            region=macro_context.region,
            timeframe=macro_context.timeframe,
            theme=macro_context.theme,
            comparison_region=macro_context.comparison_region,
            force_refresh=False,
        )
        snapshot = self.macro_service.get_snapshot(snapshot_request)
        divergences = self.macro_service.get_divergences(snapshot_request)
        events = self.macro_service.get_events(region=macro_context.region, force_refresh=False)
        source = CopilotSourceRef(
            source_id="macro.workspace.drilldown",
            label="Macro workspace drilldown",
            kind="workspace",
            provider=snapshot.source_provider,
            origin=snapshot.origin,
            description="Expanded macro workspace sections for the current context.",
            retrieved_at=snapshot.retrieved_at,
        )
        output = {
            "snapshot_cards": [self._macro_card_summary(card) for card in snapshot.snapshot_cards],
            "cross_asset": [
                {
                    "theme": row.theme,
                    "headline": row.headline,
                    "summary": row.summary,
                    "agreement_label": row.agreement_label,
                    "research_focus": row.research_focus,
                }
                for row in snapshot.cross_asset
            ],
            "divergences": [
                {
                    "divergence_id": row.divergence_id,
                    "headline": row.headline,
                    "summary": row.summary,
                    "label": row.label,
                    "research_focus": row.research_focus,
                }
                for row in divergences
            ],
            "events": [
                {
                    "event_id": row.event_id,
                    "title": row.title,
                    "category": row.category,
                    "scheduled_at": row.scheduled_at.isoformat(),
                    "importance": row.importance,
                }
                for row in events
            ],
            "warnings": snapshot.warnings,
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_macro_workspace_drilldown",
                summary="Expanded the current macro workspace into snapshot, divergence, and catalyst sections.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_macro_series_history_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        series_id = str(arguments.get("series_id") or "").strip()
        if not series_id:
            raise ValueError("series_id is required.")
        macro_context = self._macro_context_from_bundle(context)
        region = str(arguments.get("region") or "").strip() or macro_context.region
        history = self.macro_service.get_series_history(
            series_id,
            region=region,
            timeframe=macro_context.timeframe,
            force_refresh=False,
        )
        if history is None:
            raise ValueError(f"Macro series not found: {series_id}")
        source_id = f"macro.series.{history.series_id}:{history.region}:{macro_context.timeframe}"
        source = CopilotSourceRef(
            source_id=source_id,
            label=f"{history.title} history",
            kind="timeseries",
            provider=history.source_provider,
            origin=history.origin,
            description="Compact time-series summary for a requested macro series.",
            retrieved_at=history.retrieved_at,
        )
        return CopilotToolExecution(
            output=self._macro_series_summary(history),
            trace=CopilotToolTrace(
                tool_name="get_macro_series_history_summary",
                summary=f"Loaded {history.title} history for {history.region} over {macro_context.timeframe}.",
                arguments={"series_id": series_id, "region": region},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_commodities_workspace_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        workspace = self._commodities_workspace_from_bundle(context)
        coverage = workspace.get("coverage") if isinstance(workspace.get("coverage"), dict) else {}
        source = CopilotSourceRef(
            source_id="commodities.workspace.drilldown",
            label="Commodities workspace drilldown",
            kind="workspace",
            provider=str(workspace.get("source_provider") or coverage.get("source_provider") or "gamma"),
            origin=str(workspace.get("origin") or "gamma.commodities.workspace"),
            description="Expanded read-only Commodities workspace context for the active research view.",
            retrieved_at=workspace.get("retrieved_at") or coverage.get("retrieved_at"),
        )
        return CopilotToolExecution(
            output=summarize_commodities_workspace(
                workspace,
                summary_limit=12,
                spread_limit=12,
                inventory_limit=12,
            )
            or {},
            trace=CopilotToolTrace(
                tool_name="get_commodities_workspace_summary",
                summary="Expanded the loaded Commodities workspace into market, curve, spread, inventory, event, and provenance context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_prediction_market_history_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        market_id = self._prediction_market_id_from_bundle(context)
        history = self.prediction_market_service.get_probability_history(market_id)
        source = CopilotSourceRef(
            source_id="prediction.history.drilldown",
            label="Prediction history drilldown",
            kind="timeseries",
            provider=history[-1].source_provider if history else "prediction_markets",
            origin=history[-1].origin if history else "gamma.prediction.history",
            description="Expanded history summary for the selected market.",
            retrieved_at=history[-1].retrieved_at if history else None,
        )
        return CopilotToolExecution(
            output=self._prediction_history_summary(history),
            trace=CopilotToolTrace(
                tool_name="get_prediction_market_history_summary",
                summary="Expanded the selected market's probability-history summary.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_prediction_market_flow_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        market_id = self._prediction_market_id_from_bundle(context)
        wallet = self.prediction_market_service.get_wallet_summary(market_id)
        related = self.prediction_market_service.get_related_markets(market_id)
        calibration = self.prediction_market_service.get_calibration_summary(market_id)
        sources: list[CopilotSourceRef] = []
        source_ids: list[str] = []

        if wallet is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="prediction.wallet.drilldown",
                    label="Prediction wallet drilldown",
                    kind="flow",
                    provider=wallet.source_provider,
                    origin=wallet.origin,
                    description="Expanded participant and flow context for the selected market.",
                    retrieved_at=wallet.retrieved_at,
                )
            )
            source_ids.append("prediction.wallet.drilldown")
        if related:
            sources.append(
                CopilotSourceRef(
                    source_id="prediction.related.drilldown",
                    label="Prediction related-market drilldown",
                    kind="consistency",
                    provider=related[0].source_provider,
                    origin=related[0].origin,
                    description="Expanded related-market comparisons for the selected market.",
                    retrieved_at=related[0].retrieved_at,
                )
            )
            source_ids.append("prediction.related.drilldown")
        if calibration is not None:
            sources.append(
                CopilotSourceRef(
                    source_id="prediction.calibration.drilldown",
                    label="Prediction calibration drilldown",
                    kind="analytics",
                    provider=calibration.source_provider,
                    origin=calibration.origin,
                    description="Expanded venue calibration data for the selected market.",
                    retrieved_at=calibration.retrieved_at,
                )
            )
            source_ids.append("prediction.calibration.drilldown")

        output = {
            "wallet_summary": {
                "total_trades": wallet.total_trades if wallet else 0,
                "total_notional": wallet.total_notional if wallet else 0.0,
                "top_participant_share": wallet.top_participant_share if wallet else None,
                "concentration_hhi": wallet.concentration_hhi if wallet else None,
                "participants": [
                    {
                        "display_name": row.display_name,
                        "side": row.side,
                        "trade_count": row.trade_count,
                        "total_size": row.total_size,
                        "average_price": row.average_price,
                        "current_edge": row.current_edge,
                    }
                    for row in (wallet.participants if wallet else [])
                ],
                "warnings": list(wallet.warnings if wallet else []),
            },
            "related_markets": [
                {
                    "market_id": row.market_id,
                    "title": row.title,
                    "relationship": row.relationship,
                    "probability": row.probability,
                    "price_gap": row.price_gap,
                    "note": row.note,
                }
                for row in related
            ],
            "calibration_summary": {
                "venue": calibration.venue if calibration else None,
                "sample_size": calibration.sample_size if calibration else 0,
                "buckets": [
                    {
                        "label": row.label,
                        "sample_size": row.sample_size,
                        "average_probability": row.average_probability,
                        "realized_frequency": row.realized_frequency,
                    }
                    for row in (calibration.buckets if calibration else [])
                ],
                "warnings": list(calibration.warnings if calibration else []),
            },
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_prediction_market_flow_context",
                summary="Expanded flow, related-market, and calibration context for the selected market.",
                arguments={},
                source_ids=source_ids,
            ),
            sources=sources,
        )

    def _tool_get_crypto_price_history_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        token_id = self._crypto_token_id_from_bundle(context)
        history = self.crypto_service.get_price_history(token_id, days=30)
        source = CopilotSourceRef(
            source_id="crypto.history.drilldown",
            label="Crypto history drilldown",
            kind="timeseries",
            provider=history[-1].source_provider if history else "crypto",
            origin=history[-1].origin if history else "gamma.crypto.history",
            description="Expanded price, market-cap, and volume history for the selected crypto token.",
            retrieved_at=history[-1].retrieved_at if history else None,
        )
        return CopilotToolExecution(
            output=self._crypto_price_history_summary(history),
            trace=CopilotToolTrace(
                tool_name="get_crypto_price_history_summary",
                summary="Expanded the selected crypto token into a 30D price and liquidity history summary.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_crypto_liquidity_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        token_id = self._crypto_token_id_from_bundle(context)
        liquidity = self.crypto_service.get_dex_liquidity(token_id)
        if liquidity is None:
            raise ValueError(f"Crypto liquidity context is unavailable for: {token_id}")
        source = CopilotSourceRef(
            source_id="crypto.liquidity.drilldown",
            label="Crypto liquidity drilldown",
            kind="flow",
            provider=liquidity.source_provider,
            origin=liquidity.origin,
            description="Expanded DEX liquidity and pool-flow context for the selected crypto token.",
            retrieved_at=liquidity.retrieved_at,
        )
        output = {
            "lookup_strategy": liquidity.lookup_strategy,
            "matched_networks": list(liquidity.matched_networks),
            "total_reserve_usd": liquidity.total_reserve_usd,
            "total_volume_24h": liquidity.total_volume_24h,
            "total_buys_24h": liquidity.total_buys_24h,
            "total_sells_24h": liquidity.total_sells_24h,
            "total_buyers_24h": liquidity.total_buyers_24h,
            "total_sellers_24h": liquidity.total_sellers_24h,
            "dominant_dex": liquidity.dominant_dex,
            "warnings": list(liquidity.warnings),
            "pools": [
                {
                    "network": row.network,
                    "dex": row.dex,
                    "pair_name": row.pair_name,
                    "quote_token_symbol": row.quote_token_symbol,
                    "reserve_usd": row.reserve_usd,
                    "volume_24h": row.volume_24h,
                    "price_change_pct_24h": row.price_change_pct_24h,
                    "buys_24h": row.buys_24h,
                    "sells_24h": row.sells_24h,
                }
                for row in liquidity.pools
            ],
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_crypto_liquidity_context",
                summary="Expanded the selected crypto token into DEX liquidity and pool-flow context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_crypto_comparison_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        token_id = self._crypto_token_id_from_bundle(context)
        comparison = self.crypto_service.get_comparison(token_id)
        if comparison is None:
            raise ValueError(f"Crypto comparison is unavailable for: {token_id}")
        source = CopilotSourceRef(
            source_id="crypto.comparison.drilldown",
            label="Crypto comparison drilldown",
            kind="analytics",
            provider=comparison.source_provider,
            origin=comparison.origin,
            description="Expanded comparison context for the selected crypto token.",
            retrieved_at=comparison.retrieved_at,
        )
        output = {
            "target_kind": comparison.target_kind,
            "target_id": comparison.target_id,
            "target_label": comparison.target_label,
            "shared_categories": list(comparison.shared_categories),
            "price_gap_pct_24h": comparison.price_gap_pct_24h,
            "price_gap_pct_7d": comparison.price_gap_pct_7d,
            "price_gap_pct_30d": comparison.price_gap_pct_30d,
            "market_cap_ratio": comparison.market_cap_ratio,
            "turnover_gap": comparison.turnover_gap,
            "summary": comparison.summary,
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_crypto_comparison_context",
                summary="Expanded the selected crypto token into a relative token or basket comparison.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_fundamentals_company_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        ticker = self._fundamentals_ticker_from_bundle(context)
        overview = self.fundamentals_service.get_overview(ticker)
        if overview is None:
            raise ValueError(f"Fundamentals company not found: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.company.drilldown",
            label="Fundamentals company drilldown",
            kind="workspace",
            provider=overview.company.source_provider,
            origin=overview.company.origin,
            description="Expanded company, headline metric, filing, and warning context.",
            retrieved_at=overview.company.retrieved_at,
        )
        output = {
            "company": {
                "ticker": overview.company.ticker,
                "name": overview.company.name,
                "exchange": overview.company.exchange,
                "sic": overview.company.sic,
                "sic_description": overview.company.sic_description,
                "filer_category": overview.company.filer_category,
                "latest_report_period": overview.company.latest_report_period.isoformat() if overview.company.latest_report_period else None,
                "latest_filing_date": overview.company.latest_filing_date.isoformat() if overview.company.latest_filing_date else None,
                "description": overview.company.description,
            },
            "headline_metrics": [
                {
                    "metric_id": metric.metric_id,
                    "label": metric.label,
                    "value": metric.value,
                    "display_value": metric.display_value,
                    "source_provider": metric.source_provider,
                    "origin": metric.origin,
                    "transformation_note": metric.transformation_note,
                }
                for metric in overview.headline_metrics
            ],
            "filings": [
                {
                    "form": filing.form,
                    "filing_date": filing.filing_date.isoformat(),
                    "report_period": filing.report_period.isoformat() if filing.report_period else None,
                    "accession_number": filing.accession_number,
                    "is_amendment": filing.is_amendment,
                }
                for filing in overview.filings[:8]
            ],
            "warnings": list(overview.warnings),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_fundamentals_company_context",
                summary=f"Expanded Fundamentals company context for {ticker}.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_fundamentals_statement_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        ticker = self._fundamentals_ticker_from_bundle(context)
        financials = self.fundamentals_service.get_financials(ticker)
        reference = self.fundamentals_service.get_reference(ticker)
        if financials is None or reference is None:
            raise ValueError(f"Fundamentals statements not found: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.statements.drilldown",
            label="Fundamentals statement drilldown",
            kind="filing",
            provider=financials.annual_income_statement.source_provider,
            origin=financials.annual_income_statement.origin,
            description="Expanded normalized statement rows and source trace coverage.",
            retrieved_at=financials.annual_income_statement.retrieved_at,
        )
        output = {
            "annual_income": self._statement_summary(financials.annual_income_statement),
            "annual_balance": self._statement_summary(financials.annual_balance_sheet),
            "annual_cash_flow": self._statement_summary(financials.annual_cash_flow_statement),
            "annual_ratios": self._statement_summary(financials.annual_ratio_view),
            "trace_sample": [
                {
                    "statement": row.statement,
                    "basis": row.basis,
                    "line_key": row.line_key,
                    "period_label": row.period_label,
                    "display_value": row.display_value,
                    "concept_name": row.concept_name,
                    "accession_number": row.accession_number,
                    "filing_form": row.filing_form,
                    "is_amendment": row.is_amendment,
                    "source_provider": row.source_provider,
                    "transformation_note": row.transformation_note,
                }
                for row in (reference.inspection.traces[:24] if reference.inspection else [])
            ],
            "coverage_warnings": list(reference.inspection.warnings[:10] if reference.inspection else []),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_fundamentals_statement_context",
                summary=f"Expanded normalized statements and raw-versus-normalized trace for {ticker}.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_fundamentals_peer_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        ticker = self._fundamentals_ticker_from_bundle(context)
        peers = self.fundamentals_service.get_peers(ticker)
        if peers is None:
            raise ValueError(f"Fundamentals peers not found: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.peers.drilldown",
            label="Fundamentals peer drilldown",
            kind="analytics",
            provider=peers.source_provider,
            origin=peers.origin,
            description="Expanded peer basket, heatmap, comparisons, and missing-data diagnostics.",
            retrieved_at=peers.retrieved_at,
        )
        output = {
            "peer_basket": {
                "label": peers.peer_basket.basket_label,
                "display_order": list(peers.peer_basket.display_order),
                "user_edited": peers.peer_basket.user_edited,
            },
            "metric_families": sorted({row.family for row in peers.peer_heatmap.rows}) if peers.peer_heatmap else [],
            "comparisons": [
                {
                    "ticker": row.ticker,
                    "name": row.name,
                    "selected": row.selected,
                    "metrics": [
                        {
                            "metric_id": metric.metric_id,
                            "label": metric.label,
                            "display_value": metric.display_value,
                        }
                        for metric in row.metrics[:10]
                    ],
                    "warnings": list(row.warnings),
                }
                for row in peers.comparisons
            ],
            "diagnostics": [
                {
                    "ticker": row.ticker,
                    "missing_metric_ids": list(row.missing_metric_ids),
                    "warning": row.warning,
                }
                for row in peers.diagnostics
            ],
            "warnings": list(peers.warnings),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_fundamentals_peer_context",
                summary=f"Expanded peer comparison context for {ticker}.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_fundamentals_dcf_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        ticker = self._fundamentals_ticker_from_bundle(context)
        dcf = self.fundamentals_service.get_dcf_model(ticker)
        snapshots = self.fundamentals_service.list_dcf_snapshots(ticker) or []
        if dcf is None:
            raise ValueError(f"Fundamentals DCF model not found: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.dcf.drilldown",
            label="Fundamentals DCF drilldown",
            kind="analytics",
            provider=dcf.source_provider,
            origin=dcf.origin,
            description="Expanded Bear/Base/Bull DCF scenario context and saved snapshots.",
            retrieved_at=dcf.retrieved_at,
        )
        output = {
            "active_scenario_id": dcf.active_scenario_id,
            "projection_years": list(dcf.projection_years),
            "scenario_summaries": [
                self._fundamentals_dcf_summary(scenario.summary)
                for scenario in dcf.scenarios
                if scenario.summary is not None
            ],
            "active_assumptions": next(
                (
                    scenario.assumptions
                    for scenario in dcf.scenarios
                    if scenario.scenario_id == dcf.active_scenario_id
                ),
                {},
            ),
            "snapshots": [
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "name": snapshot.name,
                    "created_at": snapshot.created_at.isoformat(),
                    "active_scenario_id": snapshot.active_scenario_id,
                }
                for snapshot in snapshots[:8]
            ],
            "warnings": list(dcf.warnings),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_fundamentals_dcf_context",
                summary=f"Expanded DCF scenario and snapshot context for {ticker}.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_fundamentals_reverse_valuation_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        ticker = self._fundamentals_ticker_from_bundle(context)
        reverse = self.fundamentals_service.get_reverse_valuation(ticker)
        if reverse is None:
            raise ValueError(f"Fundamentals reverse valuation not found: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.reverse_valuation.drilldown",
            label="Fundamentals reverse valuation drilldown",
            kind="analytics",
            provider=reverse.source_provider,
            origin=reverse.origin,
            description="Expanded market-implied expectation and reverse-valuation context.",
            retrieved_at=reverse.retrieved_at,
        )
        output = {
            "current_price": reverse.current_price,
            "target_equity_value": reverse.target_equity_value,
            "target_enterprise_value": reverse.target_enterprise_value,
            "scenario_gap_metrics": [
                {
                    "metric_id": metric.metric_id,
                    "label": metric.label,
                    "display_value": metric.display_value,
                }
                for metric in reverse.scenario_gap_metrics
            ],
            "drivers": [
                {
                    "driver_id": driver.driver_id,
                    "label": driver.label,
                    "display_value": driver.display_value,
                    "base_display_value": driver.base_display_value,
                    "gap_display_value": driver.gap_display_value,
                    "success": driver.success,
                    "warnings": list(driver.warnings),
                }
                for driver in reverse.drivers
            ],
            "warnings": list(reverse.warnings),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_fundamentals_reverse_valuation_context",
                summary=f"Expanded reverse-valuation context for {ticker}.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_risk_coverage_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        result = self._risk_result_from_bundle(context)
        source = CopilotSourceRef(
            source_id="risk.coverage.drilldown",
            label="Risk coverage drilldown",
            kind="analytics",
            provider="gamma",
            origin="gamma.risk.compute",
            description="Expanded coverage, benchmark, and warning summary for the active risk result.",
            retrieved_at=None,
        )
        risk_summary = summarize_risk_result(result, contribution_limit=12, excluded_limit=12) or {}
        output = {
            "metrics": risk_summary.get("metrics"),
            "coverage": risk_summary.get("coverage"),
            "benchmark": risk_summary.get("benchmark"),
            "warnings": risk_summary.get("warnings", []),
            "excluded_assets": risk_summary.get("excluded_assets", []),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_risk_coverage_summary",
                summary="Expanded the active risk result into coverage, benchmark, and warning context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_risk_contribution_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        result = self._risk_result_from_bundle(context)
        source = CopilotSourceRef(
            source_id="risk.contributions.drilldown",
            label="Risk contribution drilldown",
            kind="analytics",
            provider="gamma",
            origin="gamma.risk.contributions",
            description="Expanded contribution rank and Monte Carlo context for the active risk result.",
            retrieved_at=None,
        )
        risk_summary = summarize_risk_result(result, contribution_limit=14, excluded_limit=12) or {}
        output = {
            "top_contributions": risk_summary.get("top_contributions", []),
            "monte_carlo": risk_summary.get("monte_carlo"),
            "warnings": risk_summary.get("warnings", []),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_risk_contribution_summary",
                summary="Expanded the active risk result into contribution and Monte Carlo context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_iv_surface_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        surface = self._iv_surface_from_bundle(context)
        session = self._iv_session_from_bundle(context)
        active_surface = resolve_iv_surface(surface, session)
        source = CopilotSourceRef(
            source_id="iv.surface.drilldown",
            label="Options surface drilldown",
            kind="workspace",
            provider="gamma",
            origin="gamma.iv.surface",
            description="Expanded options implied-volatility surface and ATM term-structure context.",
            retrieved_at=(active_surface or {}).get("timestamp"),
        )
        return CopilotToolExecution(
            output=summarize_iv_state(surface, session) or {},
            trace=CopilotToolTrace(
                tool_name="get_iv_surface_context",
                summary="Expanded the active Options context into surface, front-slice, and term-structure summaries.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_iv_session_status(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        session = self._iv_session_from_bundle(context) or {}
        source = CopilotSourceRef(
            source_id="iv.session.drilldown",
            label="Options session drilldown",
            kind="status",
            provider="gamma",
            origin="gamma.iv.session",
            description="Expanded Options session state and market-data-mode context.",
            retrieved_at=None,
        )
        output = {
            "running": bool(session.get("running")),
            "status_text": session.get("status_text"),
            "active_symbol": session.get("active_symbol"),
            "market_data_mode": session.get("market_data_mode"),
            "messages": list(session.get("messages", []) or []),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_iv_session_status",
                summary="Expanded the active Options session state and market-data-mode context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_external_context_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        profile = context.tool_state.get("external_context_profile")
        if not isinstance(profile, dict):
            profile = self._external_context_profile(
                str(context.tool_state.get("prompt") or ""),
                [],
            )
        warnings = list(context.warnings)
        sources: dict[str, CopilotSourceRef] = {
            source.source_id: source for source in context.sources
        }
        if self.news_service is None:
            source = CopilotSourceRef(
                source_id="external_context.news_feed",
                label="External news/event feed unavailable",
                kind="news",
                provider="unavailable",
                origin="gamma.copilot.external_context.news",
                description="No approved news/event provider is configured for Copilot external context.",
                retrieved_at=now_utc(),
            )
            sources[source.source_id] = source
            warnings.append("Skipped news/event external context because no NewsService is configured.")
            output = self._external_context_output(
                profile=profile,
                feed=None,
                items=[],
                item_source_ids=[],
                provider_boundaries=self._external_provider_boundaries(
                    news_configured=False,
                    news_freshness=FreshnessLabel.UNAVAILABLE,
                ),
                warnings=warnings,
            )
            return CopilotToolExecution(
                output=output,
                trace=CopilotToolTrace(
                    tool_name="get_external_context_summary",
                    summary="External context provider boundary was unavailable; no news/event items were fetched.",
                    arguments={},
                    source_ids=list(sources),
                ),
                sources=list(sources.values()),
            )

        try:
            feed = self.news_service.latest(limit=25, force_refresh=False)
        except Exception as exc:
            source = CopilotSourceRef(
                source_id="external_context.news_feed",
                label="External news/event feed failed",
                kind="news",
                provider="unavailable",
                origin="gamma.copilot.external_context.news",
                description="The configured news/event provider failed while serving Copilot external context.",
                retrieved_at=now_utc(),
            )
            sources[source.source_id] = source
            warnings.append(f"News/event external context provider failed: {exc}")
            output = self._external_context_output(
                profile=profile,
                feed=None,
                items=[],
                item_source_ids=[],
                provider_boundaries=self._external_provider_boundaries(
                    news_configured=True,
                    news_freshness=FreshnessLabel.UNAVAILABLE,
                ),
                warnings=warnings,
            )
            return CopilotToolExecution(
                output=output,
                trace=CopilotToolTrace(
                    tool_name="get_external_context_summary",
                    summary="Configured news/event external context provider failed.",
                    arguments={},
                    source_ids=list(sources),
                ),
                sources=list(sources.values()),
            )

        warnings.extend(feed.warnings)
        selected_items = self._select_external_news_items(feed.items, profile, limit=8)
        if not selected_items:
            warnings.append("No news/event items matched the Copilot external-context profile.")
        stale_warning = self._external_news_stale_warning(feed, selected_items)
        if stale_warning:
            warnings.append(stale_warning)

        feed_source = CopilotSourceRef(
            source_id="external_context.news_feed",
            label="External news/event feed",
            kind="news",
            provider=feed.source_provider,
            origin=feed.origin,
            description=f"Approved read-only news/event feed for Copilot external context; freshness={feed.freshness_label.value}.",
            retrieved_at=feed.retrieved_at,
        )
        sources[feed_source.source_id] = feed_source
        item_source_ids: list[str] = []
        for item in selected_items:
            source_id = f"external_context.news_item.{self._safe_source_id(item.normalized_id)}"
            item_source_ids.append(source_id)
            sources[source_id] = CopilotSourceRef(
                source_id=source_id,
                label=item.title[:120],
                kind="news_item",
                provider=item.source_provider,
                origin=item.origin,
                description=f"{item.source_name}; freshness={item.freshness_label.value}.",
                retrieved_at=item.retrieved_at,
            )

        output = self._external_context_output(
            profile=profile,
            feed=feed,
            items=selected_items,
            item_source_ids=item_source_ids,
            provider_boundaries=self._external_provider_boundaries(
                news_configured=True,
                news_freshness=feed.freshness_label,
            ),
            warnings=warnings,
        )
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_external_context_summary",
                summary=(
                    f"Fetched {len(selected_items)} bounded external news/event items "
                    f"for {', '.join(profile.get('context_types', []) or ['general'])} context."
                ),
                arguments={},
                source_ids=list(sources),
            ),
            sources=list(sources.values()),
        )

    def _tool_get_synthesis_scope_summary(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        source = CopilotSourceRef(
            source_id="synthesis.scope.drilldown",
            label="Synthesis scope drilldown",
            kind="workspace",
            provider="gamma",
            origin="gamma.copilot.synthesis",
            description="Expanded included-domain scope for the active Gamma cross-context synthesis.",
            retrieved_at=None,
        )
        output = {
            "active_tab": context.summary_data.get("active_tab"),
            "scope_size": context.summary_data.get("scope_size"),
            "included_domains": list(context.summary_data.get("included_domains", []) or []),
            "included_contexts": list(context.summary_data.get("included_contexts", []) or []),
            "warnings": list(context.warnings),
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="get_synthesis_scope_summary",
                summary="Expanded the current Gamma cross-context synthesis scope into included domains, fingerprints, warnings, and source references.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_synthesis_domain_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        domain = str(arguments.get("domain") or "").strip()
        if not domain:
            raise ValueError("domain is required.")

        included_bundles = self._synthesis_bundles_from_bundle(context)
        bundle = included_bundles.get(domain)
        if bundle is None:
            raise ValueError(f"Synthesis scope does not include domain: {domain}")

        drilldown: dict[str, Any] = {}
        sources: dict[str, CopilotSourceRef] = {
            source.source_id: source
            for source in bundle.sources
        }
        source_ids = [source.source_id for source in bundle.sources]

        for tool_name in self._synthesis_drilldown_tools_for_domain(domain):
            execution = self._execute_tool(tool_name, {}, bundle)
            drilldown[tool_name] = execution.output
            for source in execution.sources:
                sources[source.source_id] = source
            for source_id in execution.trace.source_ids:
                if source_id not in source_ids:
                    source_ids.append(source_id)

        domain_source = CopilotSourceRef(
            source_id=f"synthesis.domain.{domain}.drilldown",
            label=f"{domain.replace('_', ' ').title()} synthesis drilldown",
            kind="workspace",
            provider="gamma",
            origin="gamma.copilot.synthesis",
            description="Expanded one included Gamma domain inside the active synthesis scope.",
            retrieved_at=None,
        )
        sources[domain_source.source_id] = domain_source
        source_ids.append(domain_source.source_id)

        return CopilotToolExecution(
            output={
                "domain": domain,
                "summary": bundle.summary_data,
                "drilldown": drilldown,
                "warnings": list(bundle.warnings),
                "source_ids": [source.source_id for source in sources.values()],
            },
            trace=CopilotToolTrace(
                tool_name="get_synthesis_domain_context",
                summary=f"Expanded the included `{domain}` Gamma context inside the current synthesis scope.",
                arguments={"domain": domain},
                source_ids=source_ids,
            ),
            sources=list(sources.values()),
        )

    @staticmethod
    def _synthesis_bundles_from_bundle(context: CopilotContextBundle) -> dict[str, CopilotContextBundle]:
        bundles = context.tool_state.get("included_bundles")
        return bundles if isinstance(bundles, dict) else {}

    @staticmethod
    def _synthesis_drilldown_tools_for_domain(domain: str) -> tuple[str, ...]:
        return {
            "portfolio": (
                "get_portfolio_positions_summary",
                "get_portfolio_performance_context",
            ),
            "research": (
                "get_research_scope_summary",
                "get_research_coverage_context",
            ),
            "equity_research": (
                "get_research_scope_summary",
                "get_research_coverage_context",
            ),
            "strategy_lab": (),
            "macro": ("get_macro_workspace_drilldown",),
            "commodities": ("get_commodities_workspace_summary",),
            "prediction_markets": (
                "get_prediction_market_history_summary",
                "get_prediction_market_flow_context",
            ),
            "crypto": (
                "get_crypto_price_history_summary",
                "get_crypto_liquidity_context",
                "get_crypto_comparison_context",
            ),
            "fundamentals": (
                "get_fundamentals_company_context",
                "get_fundamentals_statement_context",
                "get_fundamentals_peer_context",
                "get_fundamentals_dcf_context",
                "get_fundamentals_reverse_valuation_context",
            ),
            "risk": (
                "get_risk_coverage_summary",
                "get_risk_contribution_summary",
            ),
            "iv": (
                "get_iv_surface_context",
                "get_iv_session_status",
            ),
        }.get(domain, ())

    @staticmethod
    def _external_context_profile(
        prompt: str,
        entities: list[CopilotResearchPlanEntity],
    ) -> dict[str, Any]:
        prompt_lower = str(prompt or "").lower()
        context_types: list[str] = []

        def add_context_type(value: str) -> None:
            if value not in context_types:
                context_types.append(value)

        if any(entity.kind == "ticker" for entity in entities):
            add_context_type("company")
        if any(entity.kind == "commodity" for entity in entities):
            add_context_type("commodity")
        if any(term in prompt_lower for term in ("macro", "fed", "cpi", "inflation", "rate", "rates", "yield", "policy")):
            add_context_type("macro")
        if any(term in prompt_lower for term in ("event", "calendar", "catalyst", "week", "news", "latest", "going on")):
            add_context_type("event")
        if not context_types:
            add_context_type("event")

        query_terms = CopilotService._external_query_terms(prompt, entities)
        tags = CopilotService._external_profile_tags(context_types, query_terms)
        return {
            "context_types": context_types,
            "query_terms": query_terms,
            "tags": tags,
            "entities": [asdict(entity) for entity in entities],
        }

    @staticmethod
    def _external_query_terms(
        prompt: str,
        entities: list[CopilotResearchPlanEntity],
    ) -> list[str]:
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "into",
            "what",
            "going",
            "research",
            "quick",
            "deep",
            "full",
            "week",
            "this",
            "that",
            "from",
            "only",
            "use",
        }
        terms: list[str] = []
        for entity in entities:
            terms.append(str(entity.id or ""))
            if entity.label:
                terms.append(str(entity.label))
            if entity.kind == "commodity" and str(entity.id or "").lower() == "oil":
                terms.extend(["crude", "wti", "brent"])
        for match in re.findall(r"[a-zA-Z][a-zA-Z0-9.\-]{2,}", prompt):
            value = match.lower()
            if value not in stopwords:
                terms.append(value)
                if value == "oil":
                    terms.extend(["crude", "wti", "brent"])
                elif value == "fed":
                    terms.append("federal reserve")
        return list(dict.fromkeys(term.strip().lower() for term in terms if term.strip()))

    @staticmethod
    def _external_profile_tags(context_types: list[str], query_terms: list[str]) -> list[str]:
        tags: list[str] = []
        by_context = {
            "company": ("company", "equities", "fundamentals", "filings", "regulatory", "markets"),
            "macro": ("macro", "rates", "policy", "inflation", "growth", "official", "cross_asset"),
            "commodity": ("commodities", "commodity", "energy", "oil", "metals", "geopolitics"),
            "event": ("events", "event", "calendar", "official", "regulatory", "geopolitics", "markets"),
        }
        for context_type in context_types:
            tags.extend(by_context.get(context_type, ()))
        commodity_terms = {"oil", "crude", "wti", "brent", "gas", "gold", "copper"}
        if any(term in commodity_terms for term in query_terms):
            tags.extend(["commodities", "energy", "oil"])
        return list(dict.fromkeys(tags))

    @staticmethod
    def _select_external_news_items(
        items: list[NewsEventItem],
        profile: dict[str, Any],
        *,
        limit: int,
    ) -> list[NewsEventItem]:
        terms = [str(term).lower() for term in profile.get("query_terms", []) if str(term).strip()]
        tags = {str(tag).lower() for tag in profile.get("tags", []) if str(tag).strip()}
        entity_terms = {
            term
            for entity in profile.get("entities", []) or []
            for term in (
                str(entity.get("id") or "").lower() if isinstance(entity, dict) else "",
                str(entity.get("label") or "").lower() if isinstance(entity, dict) else "",
            )
            if term.strip()
        }
        if "oil" in entity_terms:
            entity_terms.update({"crude", "wti", "brent"})
        if "fed" in entity_terms:
            entity_terms.add("federal reserve")
        specific_terms = {
            term
            for term in terms
            if len(term) >= 3
            and term
            not in {
                "latest",
                "news",
                "event",
                "events",
                "macro",
                "market",
                "markets",
                "context",
            }
        }
        required_terms = entity_terms or specific_terms

        scored: list[tuple[int, datetime, int, NewsEventItem]] = []
        for index, item in enumerate(items):
            haystack = " ".join(
                [
                    item.title,
                    item.summary or "",
                    item.source_name,
                    " ".join(item.tags),
                    " ".join(entity.label for entity in item.detected_entities),
                    " ".join(entity.symbol or "" for entity in item.detected_entities),
                    " ".join(entity.normalized_id or "" for entity in item.detected_entities),
                ]
            ).lower()
            score = 0
            matched_specific = False
            item_tags = {tag.lower() for tag in item.tags}
            if tags.intersection(item_tags):
                score += 3
            for term in terms:
                if term and term in haystack:
                    matched_specific = matched_specific or term in required_terms
                    score += 6 if term in entity_terms else 3 if len(term) <= 5 else 2
            if required_terms and not matched_specific:
                continue
            if score > 0:
                scored.append((score, item.published_at, -index, item))

        if scored:
            scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
            return [row[3] for row in scored[:limit]]
        return []

    @staticmethod
    def _external_news_stale_warning(feed: NewsEventFeed, items: list[NewsEventItem]) -> str | None:
        if feed.freshness_label in {FreshnessLabel.UNAVAILABLE, FreshnessLabel.STALE, FreshnessLabel.UNKNOWN}:
            return f"News/event external context freshness is {feed.freshness_label.value}."
        if not items:
            return None
        latest = max(item.published_at for item in items)
        age_seconds = (now_utc() - latest).total_seconds()
        if age_seconds > 72 * 60 * 60:
            return "Matched news/event external context is older than 72 hours and should be treated as stale."
        return None

    @staticmethod
    def _external_provider_boundaries(
        *,
        news_configured: bool,
        news_freshness: FreshnessLabel | str | None,
    ) -> list[dict[str, Any]]:
        normalized_news_freshness = (
            news_freshness.value if isinstance(news_freshness, FreshnessLabel) else str(news_freshness or "unknown")
        )
        return [
            {
                "provider": "news_events",
                "status": "available" if news_configured else "unavailable",
                "action_type": "fetch_external_context",
                "read_only": True,
                "freshness_label": normalized_news_freshness,
                "source_provider": "news_service" if news_configured else "unavailable",
                "fallback": "Return an empty item list with warnings when feeds are missing, stale, or failing.",
            },
            {
                "provider": "analyst_estimates",
                "status": "unavailable",
                "action_type": "fetch_external_context",
                "read_only": True,
                "freshness_label": FreshnessLabel.UNAVAILABLE.value,
                "source_provider": "unconfigured",
                "fallback": "Use Gamma fundamentals/market context and emit a missing-provider warning; do not synthesize consensus estimates.",
            },
            {
                "provider": "transcripts",
                "status": "unavailable",
                "action_type": "fetch_external_context",
                "read_only": True,
                "freshness_label": FreshnessLabel.UNAVAILABLE.value,
                "source_provider": "unconfigured",
                "fallback": "Use loaded filing/fundamentals context when available; do not invent transcript snippets.",
            },
            {
                "provider": "filing_deltas",
                "status": "unavailable",
                "action_type": "fetch_external_context",
                "read_only": True,
                "freshness_label": FreshnessLabel.UNAVAILABLE.value,
                "source_provider": "unconfigured",
                "fallback": "Rely on Gamma's SEC-backed Fundamentals context for filing chronology until a dedicated delta adapter exists.",
            },
        ]

    @staticmethod
    def _external_context_output(
        *,
        profile: dict[str, Any],
        feed: NewsEventFeed | None,
        items: list[NewsEventItem],
        item_source_ids: list[str],
        provider_boundaries: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "context_types": list(profile.get("context_types", []) or []),
            "query_terms": list(profile.get("query_terms", []) or []),
            "target_entities": list(profile.get("entities", []) or []),
            "news": {
                "source_provider": feed.source_provider if feed is not None else "unavailable",
                "origin": feed.origin if feed is not None else "gamma.copilot.external_context.news",
                "retrieved_at": feed.retrieved_at.isoformat() if feed is not None else now_utc().isoformat(),
                "freshness_label": feed.freshness_label.value if feed is not None else FreshnessLabel.UNAVAILABLE.value,
                "items": [
                    {
                        "source_id": item_source_ids[index] if index < len(item_source_ids) else None,
                        "normalized_id": item.normalized_id,
                        "title": item.title,
                        "summary": item.summary,
                        "url": item.url,
                        "source_name": item.source_name,
                        "source_domain": item.source_domain,
                        "source_provider": item.source_provider,
                        "published_at": item.published_at.isoformat(),
                        "retrieved_at": item.retrieved_at.isoformat(),
                        "freshness_label": item.freshness_label.value,
                        "tags": list(item.tags),
                        "detected_entities": [
                            {
                                "label": entity.label,
                                "entity_type": entity.entity_type,
                                "normalized_id": entity.normalized_id,
                                "symbol": entity.symbol,
                            }
                            for entity in item.detected_entities
                        ],
                        "origin": item.origin,
                        "transformation_note": item.transformation_note,
                        "warnings": list(item.warnings),
                    }
                    for index, item in enumerate(items)
                ],
            },
            "provider_boundaries": provider_boundaries,
            "fallback_behavior": [
                "Missing providers are represented as unavailable boundaries with warnings.",
                "Stale or unavailable feeds are passed through as freshness labels instead of being converted into confident claims.",
                "General web browsing is not used by this executor path.",
            ],
            "warnings": dedupe_warnings(warnings),
        }

    @staticmethod
    def _safe_source_id(value: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip())
        return safe[:120] or "item"

    @staticmethod
    def _portfolio_snapshot_from_bundle(context: CopilotContextBundle) -> dict[str, Any]:
        snapshot = context.tool_state.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("Portfolio context is missing the active snapshot.")
        return snapshot

    @staticmethod
    def _portfolio_history_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        history = context.tool_state.get("history")
        return history if isinstance(history, dict) else None

    @staticmethod
    def _portfolio_performance_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        performance = context.tool_state.get("performance")
        return performance if isinstance(performance, dict) else None

    @staticmethod
    def _research_result_from_bundle(context: CopilotContextBundle) -> dict[str, Any]:
        research = context.tool_state.get("result")
        if not isinstance(research, dict):
            raise ValueError("Research context is missing the active research result.")
        return research

    @staticmethod
    def _risk_result_from_bundle(context: CopilotContextBundle) -> dict[str, Any]:
        risk = context.tool_state.get("result")
        if not isinstance(risk, dict):
            raise ValueError("Risk context is missing the active risk result.")
        return risk

    @staticmethod
    def _iv_surface_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        surface = context.tool_state.get("surface")
        return surface if isinstance(surface, dict) else None

    @staticmethod
    def _iv_session_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        session = context.tool_state.get("session")
        return session if isinstance(session, dict) else None

    @staticmethod
    def _macro_context_from_bundle(context: CopilotContextBundle) -> MacroCopilotContext:
        return MacroCopilotContext(
            mode=str(context.summary_data.get("mode") or "snapshot"),
            region=str(context.summary_data.get("region") or "US"),
            timeframe=str(context.summary_data.get("timeframe") or "3M"),
            theme=str(context.summary_data.get("theme") or "all"),
            comparison_region=context.summary_data.get("comparison_region"),
        )

    @staticmethod
    def _commodities_workspace_from_bundle(context: CopilotContextBundle) -> dict[str, Any]:
        workspace = context.tool_state.get("workspace")
        if not isinstance(workspace, dict):
            raise ValueError("Commodities context is missing the loaded workspace.")
        return workspace

    @staticmethod
    def _prediction_market_id_from_bundle(context: CopilotContextBundle) -> str:
        market_id = str(context.summary_data.get("market_id") or "").strip()
        if not market_id:
            raise ValueError("Prediction market context is missing the selected market id.")
        return market_id

    @staticmethod
    def _crypto_token_id_from_bundle(context: CopilotContextBundle) -> str:
        token_id = str(context.summary_data.get("token_id") or "").strip()
        if not token_id:
            raise ValueError("Crypto context is missing the selected token id.")
        return token_id

    @staticmethod
    def _fundamentals_ticker_from_request(request: CopilotResearchCardRequest) -> str:
        ticker = str(request.context.fundamentals_ticker or "").strip().upper()
        if not ticker and isinstance(request.context.fundamentals_state, dict):
            ticker = str(
                request.context.fundamentals_state.get("ticker")
                or request.context.fundamentals_state.get("selected_ticker")
                or ""
            ).strip().upper()
        if not ticker:
            raise ValueError("Fundamentals copilot requires a selected ticker.")
        return ticker

    @staticmethod
    def _fundamentals_ticker_from_bundle(context: CopilotContextBundle) -> str:
        ticker = str(context.tool_state.get("ticker") or context.summary_data.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError("Fundamentals context is missing the selected ticker.")
        return ticker

    @staticmethod
    def _fundamentals_dcf_summary(summary: Any) -> dict[str, Any]:
        if summary is None:
            return {}
        return {
            "scenario_id": summary.scenario_id,
            "label": summary.label,
            "enterprise_value": summary.enterprise_value,
            "equity_value": summary.equity_value,
            "implied_value_per_share": summary.implied_value_per_share,
            "upside_downside_pct": summary.upside_downside_pct,
            "current_price": summary.current_price,
            "source_provider": summary.source_provider,
            "origin": summary.origin,
            "retrieved_at": summary.retrieved_at.isoformat() if summary.retrieved_at else None,
            "transformation_note": summary.transformation_note,
        }

    @staticmethod
    def _statement_summary(statement: Any) -> dict[str, Any]:
        return {
            "statement": statement.statement,
            "basis": statement.basis,
            "periods": [period.label for period in statement.periods],
            "rows": [
                {
                    "line_key": line.line_key,
                    "label": line.label,
                    "latest": line.cells[-1].display_value if line.cells else None,
                    "source_provider": line.source_provider,
                    "origin": line.origin,
                    "transformation_note": line.transformation_note,
                }
                for line in statement.lines
            ],
            "source_provider": statement.source_provider,
            "origin": statement.origin,
            "transformation_note": statement.transformation_note,
        }

    @staticmethod
    def _macro_card_summary(card: Any) -> dict[str, Any]:
        return {
            "card_id": card.card_id,
            "title": card.title,
            "subtitle": card.subtitle,
            "summary": card.summary,
            "why_now": card.why_now,
            "mode_target": card.mode_target,
            "target_theme": card.target_theme,
            "metrics": [CopilotService._metric_summary(metric) for metric in card.metrics[:5]],
            "linked_markets": [
                {
                    "market_id": row.market_id,
                    "title": row.title,
                    "venue": row.venue,
                    "current_probability": row.current_probability,
                    "macro_alignment": row.macro_alignment,
                    "macro_alignment_summary": row.macro_alignment_summary,
                }
                for row in card.linked_markets[:4]
            ],
        }

    @staticmethod
    def _macro_rates_policy_summary(summary: Any) -> dict[str, Any] | None:
        if summary is None:
            return None
        return {
            "headline": summary.headline,
            "summary": summary.summary,
            "path_headline": summary.path_headline,
            "path_summary": summary.path_summary,
            "market_alignment_label": summary.market_alignment_label,
            "market_alignment_summary": summary.market_alignment_summary,
            "policy_metrics": [CopilotService._metric_summary(metric) for metric in summary.policy_metrics[:6]],
            "real_yield_metrics": [CopilotService._metric_summary(metric) for metric in summary.real_yield_metrics[:4]],
            "events": [
                {
                    "event_id": row.event_id,
                    "title": row.title,
                    "scheduled_at": row.scheduled_at.isoformat(),
                    "importance": row.importance,
                }
                for row in summary.events[:4]
            ],
        }

    @staticmethod
    def _metric_summary(metric: MacroMetricRecord) -> dict[str, Any]:
        return {
            "metric_id": metric.metric_id,
            "label": metric.label,
            "display_value": metric.display_value,
            "delta_display": metric.delta_display,
            "series_id": metric.series_id,
            "comparison_display_value": metric.comparison_display_value,
            "gap_display": metric.gap_display,
        }

    @staticmethod
    def _macro_series_summary(history: MacroSeriesHistory) -> dict[str, Any]:
        points = history.points
        latest = points[-1] if points else None
        first = points[0] if points else None
        values = [point.value for point in points]
        return {
            "series_id": history.series_id,
            "title": history.title,
            "region": history.region,
            "timeframe_points": [
                {"timestamp": point.timestamp.isoformat(), "value": point.value}
                for point in points[-12:]
            ],
            "latest": {"timestamp": latest.timestamp.isoformat(), "value": latest.value} if latest else None,
            "start": {"timestamp": first.timestamp.isoformat(), "value": first.value} if first else None,
            "change": (latest.value - first.value) if latest and first else None,
            "min_value": min(values) if values else None,
            "max_value": max(values) if values else None,
            "observations": len(points),
            "source_provider": history.source_provider,
            "origin": history.origin,
            "retrieved_at": history.retrieved_at.isoformat() if history.retrieved_at else None,
            "transformation_note": history.transformation_note,
        }

    @staticmethod
    def _prediction_history_summary(points: list[PredictionProbabilityPoint]) -> dict[str, Any]:
        if not points:
            return {
                "observations": 0,
                "latest_probability": None,
                "start_probability": None,
                "change": None,
                "high_probability": None,
                "low_probability": None,
                "points": [],
            }
        latest = points[-1]
        first = points[0]
        probabilities = [point.probability for point in points]
        return {
            "observations": len(points),
            "latest_probability": latest.probability,
            "latest_timestamp": latest.timestamp.isoformat(),
            "start_probability": first.probability,
            "start_timestamp": first.timestamp.isoformat(),
            "change": latest.probability - first.probability,
            "high_probability": max(probabilities),
            "low_probability": min(probabilities),
            "points": [
                {"timestamp": point.timestamp.isoformat(), "probability": point.probability}
                for point in points[-24:]
            ],
        }

    @staticmethod
    def _crypto_price_history_summary(points: list[Any]) -> dict[str, Any]:
        if not points:
            return {
                "observations": 0,
                "latest_price": None,
                "start_price": None,
                "change_pct": None,
                "high_price": None,
                "low_price": None,
                "latest_market_cap": None,
                "latest_total_volume": None,
                "points": [],
            }
        latest = points[-1]
        first = points[0]
        prices = [point.price for point in points]
        change_pct = None
        if first.price not in {None, 0}:
            change_pct = ((latest.price / first.price) - 1.0) * 100.0
        return {
            "observations": len(points),
            "latest_price": latest.price,
            "latest_timestamp": latest.timestamp.isoformat(),
            "start_price": first.price,
            "start_timestamp": first.timestamp.isoformat(),
            "change_pct": change_pct,
            "high_price": max(prices),
            "low_price": min(prices),
            "latest_market_cap": latest.market_cap,
            "latest_total_volume": latest.total_volume,
            "points": [
                {
                    "timestamp": point.timestamp.isoformat(),
                    "price": point.price,
                    "market_cap": point.market_cap,
                    "total_volume": point.total_volume,
                }
                for point in points[-24:]
            ],
        }
