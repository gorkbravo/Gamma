from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from hashlib import sha256
import json
import logging
import math
import queue
import re
import threading
import time
from typing import Any, Callable, Iterator

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
from src.application.copilot_agents_operator import CopilotAgentsOperatorService
from src.application.copilot_report_service import CopilotReportService
from src.application.crypto_service import CryptoService
from src.application.fundamentals_service import FundamentalsService
from src.application.iv_service import IVService, IVSurfaceRequest
from src.application.macro_service import MacroSnapshotRequest, MacroService
from src.application.news_service import NewsService
from src.application.prediction_market_service import PredictionMarketService
from src.application.research_service import ResearchAnalysisRequest, ResearchService
from src.application.research_action_registry import ResearchActionRegistry
from src.application.request_limits import MAX_RISK_LOOKBACK_DAYS
from src.application.risk_service import RiskComputeRequest, RiskService
from src.application.sitrep_service import SitrepService, SitrepWorkspaceRequest
from src.models.app_mode import ResearchScopeType, SyntheticPosition
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
    CopilotOperatorConfirmationCheckpoint,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotResearchPlan,
    CopilotResearchPlanDomainDecision,
    CopilotResearchPlanDomain,
    CopilotResearchPlanEntity,
    CopilotResearchReport,
    CopilotRunEvent,
    COPILOT_RUN_EVENT_TYPES,
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
from src.services.copilot_evidence import resolve_result_evidence
from src.models.macro import MacroMetricRecord, MacroSeriesHistory
from src.models.news import NewsEventFeed, NewsEventItem
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.models.prediction_markets import PredictionProbabilityPoint
from src.models.provenance import FreshnessLabel
from src.models.research_lab import ResearchComparisonLeg, ResearchComparisonRequest
from src.services.copilot_provider import CopilotProvider, CopilotRunCancelled
from src.utils.time import now_utc

logger = logging.getLogger(__name__)

MAX_OPERATOR_FINAL_OUTPUT_BYTES = 50_000

DEFAULT_COPILOT_RUN_TIMEOUT_SECONDS = 300.0
COPILOT_RUN_REPLAY_LIMIT = 512
COPILOT_RUN_RETENTION_SECONDS = 900.0
COPILOT_RUN_REGISTRY_LIMIT = 64


@dataclass
class _CopilotRunHandle:
    run_id: str
    run_kind: str
    request_fingerprint: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    condition: threading.Condition = field(default_factory=threading.Condition)
    events: list[CopilotRunEvent] = field(default_factory=list)
    next_sequence: int = 0
    status: str = "pending"
    finalized: bool = False
    terminal: bool = False
    created_monotonic: float = field(default_factory=time.monotonic)
    updated_monotonic: float = field(default_factory=time.monotonic)


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
    permission_policy: str = "automatic"
    provenance_behavior: str = "Returns Gamma source references and warnings where available."
    retry_policy: str = "retry_safe_if_read_only"
    test_coverage_owner: str | None = "tests/test_copilot.py"

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
            permission_policy=self.permission_policy,
            provenance_behavior=self.provenance_behavior,
            retry_policy=self.retry_policy,
            can_call_external_providers=self.external_provider is not None,
            test_coverage_owner=self.test_coverage_owner,
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
        risk_service: RiskService | None = None,
        iv_service: IVService | None = None,
        portfolio_provider: Any | None = None,
        research_provider: Any | None = None,
        news_service: NewsService | None = None,
        sitrep_service: SitrepService | None = None,
        provider: CopilotProvider,
        store: CopilotStore | None = None,
    ) -> None:
        self.macro_service = macro_service
        self.prediction_market_service = prediction_market_service
        self.crypto_service = crypto_service
        self.fundamentals_service = fundamentals_service
        self.risk_service = risk_service
        self.iv_service = iv_service
        self.portfolio_provider = portfolio_provider
        self.research_provider = research_provider
        self.news_service = news_service
        self.sitrep_service = sitrep_service
        self.provider = provider
        self.store = store
        self.agents_operator_service = CopilotAgentsOperatorService()
        self._runs: dict[str, _CopilotRunHandle] = {}
        self._pending_run_cancellations: dict[str, float] = {}
        self._runs_lock = threading.Lock()
        self._context_builders = {
            "portfolio": self._build_portfolio_context,
            "research": self._build_research_context,
            "equity_research": self._build_equity_research_context,
            "strategy_lab": self._build_strategy_lab_context,
            "macro": self._build_macro_context,
            "commodities": self._build_commodities_context,
            "sitrep": self._build_sitrep_context,
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
                    name="run_research_scope_analysis",
                    description="Run a bounded read-only Research scope analysis for the active single-name or synthetic research scope.",
                    domains=("research", "equity_research"),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "scope_type": {
                                "type": ["string", "null"],
                                "enum": ["auto", "single_ticker", "synthetic_portfolio", None],
                                "description": "Research scope type. Use auto/null to infer from the active research result.",
                            },
                            "primary_symbol": {
                                "type": ["string", "null"],
                                "description": "Ticker for single-ticker scope analysis.",
                            },
                            "benchmark_symbol": {
                                "type": ["string", "null"],
                                "description": "Benchmark ticker. Defaults to SPY.",
                            },
                            "lookback_days": {
                                "type": ["integer", "null"],
                                "description": "Historical lookback in days, bounded to 20-2520.",
                            },
                            "synthetic_positions": {
                                "type": "array",
                                "description": "Optional synthetic research positions. Weights are normalized by Gamma and do not modify saved research state.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {"type": "string"},
                                        "weight": {"type": "number"},
                                        "instrument_id": {"type": ["string", "null"]},
                                        "display_symbol": {"type": ["string", "null"]},
                                        "sec_type": {"type": ["string", "null"]},
                                        "currency": {"type": ["string", "null"]},
                                        "exchange": {"type": ["string", "null"]},
                                        "primary_exchange": {"type": ["string", "null"]},
                                        "provider": {"type": ["string", "null"]},
                                        "provider_id": {"type": ["string", "null"]},
                                    },
                                    "required": [
                                        "symbol",
                                        "weight",
                                        "instrument_id",
                                        "display_symbol",
                                        "sec_type",
                                        "currency",
                                        "exchange",
                                        "primary_exchange",
                                        "provider",
                                        "provider_id",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "scope_type",
                            "primary_symbol",
                            "benchmark_symbol",
                            "lookback_days",
                            "synthetic_positions",
                        ],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_research_scope_analysis,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=30.0,
                    permission_policy="automatic",
                    provenance_behavior=(
                        "Runs Gamma's existing ResearchService.analyze path and returns scope metrics, coverage, "
                        "constituent diagnostics, warnings, and provider provenance without saving scopes or modifying state."
                    ),
                    failure_modes=(
                        "Requires an active research result or explicit scope arguments.",
                        "History may be missing for one or more scope constituents.",
                        "Synthetic scope positions are temporary and read-only; saved research objects are not loaded or updated by this action.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="get_strategy_lab_handoff_context",
                    description="Return the current read-only Strategy Lab inbound handoff queue, including pending, resolved, unsupported, and stale context state.",
                    domains=("strategy_lab",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_strategy_lab_handoff_context,
                    output_schema={"type": "object"},
                    timeout_seconds=5.0,
                    provenance_behavior=(
                        "Returns compact Strategy Lab handoff queue state, resolved object identities, coverage, provenance, and warnings "
                        "from the same frontend handoff records shown in the Strategy Lab inbound strip."
                    ),
                    failure_modes=(
                        "Pending handoffs are user intent only until resolved by the Strategy Lab resolver.",
                        "Unsupported handoffs are context/reference records and must not be treated as weighted return legs.",
                        "Stale earlier-session handoffs are reported separately and excluded from current auto-resolution.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="run_strategy_lab_backtest",
                    description="Return an operator-grade read-only Strategy Lab backtest summary from the active imported strategy, composition, or comparison result.",
                    domains=("strategy_lab",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "result_kind": {
                                "type": ["string", "null"],
                                "enum": ["auto", "imported_result", "composition", "compare_result", None],
                                "description": "Optional active Strategy Lab result kind to summarize. Use auto to prefer composition, then imported_result, then compare_result.",
                            }
                        },
                        "required": ["result_kind"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_strategy_lab_backtest,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=10.0,
                    permission_policy="automatic",
                    provenance_behavior=(
                        "Summarizes already-loaded Strategy Lab analytics, provenance, benchmark context, "
                        "period tables, and warnings without executing strategy code or modifying saved research."
                    ),
                    failure_modes=(
                        "Raw uploaded CSV rows are not persisted by default, so this action summarizes the active normalized result.",
                        "Benchmark-relative fields are unavailable when the active Strategy Lab result has no benchmark overlap.",
                        "Compare/Scenario results are summarized as comparison analytics rather than rerun as a new backtest.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="run_hypothetical_portfolio_comparison",
                    description="Build a bounded read-only hypothetical research portfolio, compare its historical return stream to a benchmark, and optionally hand it to Risk for read-only contribution analytics.",
                    domains=("research",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "portfolio_label": {
                                "type": ["string", "null"],
                                "description": "Optional label for the hypothetical portfolio.",
                            },
                            "benchmark_symbol": {
                                "type": ["string", "null"],
                                "description": "Benchmark ticker for comparison. Defaults to SPY.",
                            },
                            "lookback_days": {
                                "type": ["integer", "null"],
                                "description": "Historical lookback in days, bounded to 20-2520.",
                            },
                            "min_observations": {
                                "type": ["integer", "null"],
                                "description": "Minimum aligned observations required for the comparison, bounded to 2-2520.",
                            },
                            "include_risk_analysis": {
                                "type": ["boolean", "null"],
                                "description": "Whether to run an optional bounded read-only Risk handoff against the temporary hypothetical snapshot.",
                            },
                            "legs": {
                                "type": "array",
                                "description": "Hypothetical long-only research legs. Weights are normalized by Gamma and do not modify any portfolio.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {
                                            "type": "string",
                                            "description": "Ticker or instrument symbol.",
                                        },
                                        "weight": {
                                            "type": "number",
                                            "description": "Non-negative portfolio weight. Gamma normalizes the supplied weights.",
                                        },
                                        "sec_type": {
                                            "type": ["string", "null"],
                                            "description": "Optional security type, e.g. STK or ETF.",
                                        },
                                        "currency": {
                                            "type": ["string", "null"],
                                            "description": "Optional instrument currency.",
                                        },
                                        "exchange": {
                                            "type": ["string", "null"],
                                            "description": "Optional exchange.",
                                        },
                                    },
                                    "required": ["symbol", "weight", "sec_type", "currency", "exchange"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "portfolio_label",
                            "benchmark_symbol",
                            "lookback_days",
                            "min_observations",
                            "include_risk_analysis",
                            "legs",
                        ],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_hypothetical_portfolio_comparison,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=20.0,
                    permission_policy="automatic",
                    provenance_behavior=(
                        "Builds a temporary read-only synthetic research scope, compares normalized returns to a benchmark, "
                        "optionally computes Risk analytics from a temporary notional snapshot, and returns coverage, "
                        "relative metrics, warnings, and provider provenance without saving or trading anything."
                    ),
                    failure_modes=(
                        "History may be missing for one or more requested symbols.",
                        "The comparison can be unavailable if fewer than two aligned return observations remain.",
                        "Optional Risk handoff is skipped when RiskService is unavailable or history coverage is too thin.",
                        "Weights are bounded, long-only, and normalized; this does not modify broker or saved research state.",
                    ),
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
                    name="run_fundamentals_reverse_valuation",
                    description="Run a read-only Fundamentals reverse-valuation analysis for the selected or supplied ticker and return implied-expectation drivers.",
                    domains=("fundamentals",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": ["string", "null"],
                                "description": "Optional ticker override. Use null to keep the selected Fundamentals ticker.",
                            }
                        },
                        "required": ["ticker"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_fundamentals_reverse_valuation,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    permission_policy="automatic",
                    provenance_behavior="Returns reverse-valuation drivers, sensitivity context, source refs, and warnings without changing DCF state.",
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
                    name="run_risk_contribution_analysis",
                    description="Run a bounded read-only risk contribution computation for the active portfolio or research snapshot.",
                    domains=("risk",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "source_scope": {
                                "type": ["string", "null"],
                                "description": "portfolio or research. Use null to infer from workspace mode.",
                            },
                            "top_n": {
                                "type": ["integer", "null"],
                                "description": "Number of contribution rows to return, bounded to 1-25.",
                            },
                            "include_monte_carlo": {
                                "type": ["boolean", "null"],
                                "description": "Whether to include the existing bounded Monte Carlo diagnostics.",
                            },
                        },
                        "required": ["source_scope", "top_n", "include_monte_carlo"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_risk_contribution_analysis,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=35.0,
                    permission_policy="automatic",
                    provenance_behavior=(
                        "Computes Gamma risk contribution, coverage, concentration, VaR, beta/correlation, "
                        "and optional Monte Carlo diagnostics from the active snapshot without changing portfolio or research state."
                    ),
                    failure_modes=(
                        "Risk contribution requires an active portfolio or research snapshot.",
                        "Contribution rows can be unavailable when return history coverage is too thin.",
                        "Monte Carlo diagnostics remain bounded and use Gamma's existing configured simulation model.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="run_risk_scenario_analysis",
                    description="Run a bounded read-only risk computation for the active portfolio or research snapshot, including VaR, contribution, coverage, typed shock parameters, transparent proxy impact, and scenario warnings.",
                    domains=("risk",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "scenario_label": {
                                "type": ["string", "null"],
                                "description": "Optional label for the scenario being studied, e.g. rate_shock_baseline.",
                            },
                            "source_scope": {
                                "type": ["string", "null"],
                                "description": "portfolio or research. Use null to infer from workspace mode.",
                            },
                            "scenario_type": {
                                "type": ["string", "null"],
                                "enum": ["baseline", "rate_shock", "equity_drawdown", "commodity_shock", "custom", None],
                                "description": "Typed bounded scenario family. Use rate_shock for rate/yield shocks.",
                            },
                            "rate_shift_bps": {
                                "type": ["number", "null"],
                                "description": "Parallel rate shift in basis points, bounded to +/-300 bps. Positive means rates rise.",
                            },
                            "equity_shock_pct": {
                                "type": ["number", "null"],
                                "description": "Optional broad equity proxy shock as a decimal return, bounded to -80% to +80%.",
                            },
                            "duration_proxy_years": {
                                "type": ["number", "null"],
                                "description": "Optional duration proxy used only when a position-specific duration proxy is unavailable, bounded to 0-30 years.",
                            },
                            "symbol_shocks": {
                                "type": "array",
                                "description": "Optional explicit per-symbol price shocks. These override inferred proxies for matching positions.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {
                                            "type": "string",
                                            "description": "Portfolio symbol or display symbol to shock.",
                                        },
                                        "price_shock_pct": {
                                            "type": "number",
                                            "description": "Decimal price shock, bounded to -95% to +500%.",
                                        },
                                    },
                                    "required": ["symbol", "price_shock_pct"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "scenario_label",
                            "source_scope",
                            "scenario_type",
                            "rate_shift_bps",
                            "equity_shock_pct",
                            "duration_proxy_years",
                            "symbol_shocks",
                        ],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_risk_scenario_analysis,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=45.0,
                    permission_policy="automatic",
                    provenance_behavior="Computes read-only risk analytics from the active snapshot and returns source refs, bounded shock parameters, transparent proxy impact, warnings, and coverage diagnostics.",
                    failure_modes=(
                        "Shock parameters are bounded and may be clipped before execution.",
                        "Rate shock proxy uses transparent duration assumptions; it is not a full curve repricing model.",
                        "Positions without explicit shocks or supported proxies are left unchanged in the proxy impact block.",
                    ),
                ),
                _CopilotToolDefinition(
                    name="run_options_realized_implied_comparison",
                    description="Run a bounded read-only Options/IV realized-versus-implied volatility comparison for the active or supplied symbol.",
                    domains=("iv",),
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": ["string", "null"],
                                "description": "Optional ticker override. Use null to keep the active Options symbol.",
                            },
                            "max_expiries": {
                                "type": ["integer", "null"],
                                "description": "Maximum expiry rows to return, bounded to 1-8.",
                            },
                            "depth_preset": {
                                "type": ["string", "null"],
                                "enum": ["compact", "standard", "deep", "front_deep", "max", None],
                                "description": "IV surface collection depth. The operator defaults to compact for bounded automatic execution.",
                            },
                            "market_data_mode": {
                                "type": ["string", "null"],
                                "enum": ["live", "delayed", "auto", None],
                                "description": "Optional market-data mode override. Null keeps the active IV service mode.",
                            },
                        },
                        "required": ["symbol", "max_expiries", "depth_preset", "market_data_mode"],
                        "additionalProperties": False,
                    },
                    handler=self._tool_run_options_realized_implied_comparison,
                    action_type="run_analysis",
                    output_schema={"type": "object"},
                    timeout_seconds=20.0,
                    permission_policy="automatic",
                    provenance_behavior=(
                        "Uses Gamma's existing IVService surface path and loaded Options state to compare ATM implied volatility, "
                        "available historical-volatility fields, implied moves, surface quality, warnings, and source provenance without "
                        "calling providers directly from Copilot or modifying state."
                    ),
                    failure_modes=(
                        "Requires an active IV surface, a supplied ticker, or an IV service able to load a compact read-only surface.",
                        "Historical-volatility fields can be unavailable for some or all contracts, in which case rows are marked insufficient rather than inferred.",
                        "Sparse or delayed option chains can limit comparison confidence and surface quality is returned transparently.",
                    ),
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
                permission_policy="automatic_draft",
                provenance_behavior="Returns a before/after diff, warnings, source ids, and confirmation token without applying local state.",
                retry_policy="retry_safe_until_applied",
                test_coverage_owner="tests/test_copilot.py",
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
                permission_policy="confirmation_required",
                provenance_behavior="Applies a confirmed draft and records rollback/snapshot context through Copilot persistence.",
                retry_policy="not_retry_safe_after_success",
                test_coverage_owner="tests/test_copilot.py",
            ),
        ]
        self.action_registry = ResearchActionRegistry(self._action_definitions())

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
        return self._persist_result_turn(normalized_request, resolved_domain, context, result)

    def _persist_result_turn(
        self,
        normalized_request: CopilotResearchCardRequest,
        resolved_domain: str,
        context: CopilotContextBundle,
        result: CopilotResearchCardResult,
    ) -> CopilotResearchCardResult:
        if self.store is None:
            return result
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

    @staticmethod
    def _run_request_fingerprint(request: CopilotResearchCardRequest, run_kind: str) -> str:
        encoded = json.dumps(
            {"kind": run_kind, "request": asdict(request)},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def _prune_runs_locked(self) -> None:
        now = time.monotonic()
        self._pending_run_cancellations = {
            run_id: created
            for run_id, created in self._pending_run_cancellations.items()
            if now - created <= COPILOT_RUN_RETENTION_SECONDS
        }
        expired = [
            run_id
            for run_id, handle in self._runs.items()
            if handle.terminal and now - handle.updated_monotonic > COPILOT_RUN_RETENTION_SECONDS
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)
        if len(self._runs) <= COPILOT_RUN_REGISTRY_LIMIT:
            return
        completed = sorted(
            (handle for handle in self._runs.values() if handle.terminal),
            key=lambda handle: handle.updated_monotonic,
        )
        for handle in completed[: max(0, len(self._runs) - COPILOT_RUN_REGISTRY_LIMIT)]:
            self._runs.pop(handle.run_id, None)

    def _resolve_run_handle(
        self,
        request: CopilotResearchCardRequest,
        *,
        run_kind: str,
        run_id: str | None,
    ) -> tuple[_CopilotRunHandle, bool]:
        resolved_run_id = (run_id or "").strip() or new_copilot_id("run")
        fingerprint = self._run_request_fingerprint(request, run_kind)
        with self._runs_lock:
            self._prune_runs_locked()
            existing = self._runs.get(resolved_run_id)
            if existing is not None:
                if existing.run_kind != run_kind or existing.request_fingerprint != fingerprint:
                    raise ValueError("Copilot run id is already attached to a different request.")
                return existing, False
            handle = _CopilotRunHandle(
                run_id=resolved_run_id,
                run_kind=run_kind,
                request_fingerprint=fingerprint,
            )
            if resolved_run_id in self._pending_run_cancellations:
                handle.cancel_event.set()
                self._pending_run_cancellations.pop(resolved_run_id, None)
            self._runs[resolved_run_id] = handle
            return handle, True

    def _append_run_event(
        self,
        handle: _CopilotRunHandle,
        event_type: str,
        data: dict[str, Any] | None = None,
        *,
        result: CopilotResearchCardResult | None = None,
    ) -> CopilotRunEvent | None:
        if event_type not in COPILOT_RUN_EVENT_TYPES:
            unsupported_type = event_type
            event_type = "warning"
            data = {"message": f"Ignored unsupported provider run event type: {unsupported_type}."}
        with handle.condition:
            if handle.terminal:
                return None
            event = CopilotRunEvent(
                run_id=handle.run_id,
                sequence=handle.next_sequence,
                event_type=event_type,
                data=data or {},
                result=result,
            )
            handle.next_sequence += 1
            handle.events.append(event)
            if len(handle.events) > COPILOT_RUN_REPLAY_LIMIT:
                handle.events = handle.events[-COPILOT_RUN_REPLAY_LIMIT:]
            handle.updated_monotonic = time.monotonic()
            if event.is_terminal:
                handle.terminal = True
                handle.status = "done"
            elif event_type == "run.created":
                handle.status = "running"
            handle.condition.notify_all()
            return event

    @staticmethod
    def _subscribe_run(
        handle: _CopilotRunHandle,
        *,
        after_sequence: int = -1,
    ) -> Iterator[CopilotRunEvent]:
        cursor = max(-1, int(after_sequence))
        while True:
            with handle.condition:
                batch = [event for event in handle.events if event.sequence > cursor]
                terminal = handle.terminal
                if not batch and not terminal:
                    handle.condition.wait(timeout=1.0)
                    continue
            for event in batch:
                cursor = event.sequence
                yield event
            if terminal:
                return

    def has_run(self, run_id: str) -> bool:
        normalized = (run_id or "").strip()
        with self._runs_lock:
            self._prune_runs_locked()
            return normalized in self._runs

    def stream_existing_run_events(
        self,
        run_id: str,
        *,
        after_sequence: int = -1,
    ) -> Iterator[CopilotRunEvent]:
        normalized = (run_id or "").strip()
        with self._runs_lock:
            self._prune_runs_locked()
            handle = self._runs.get(normalized)
        if handle is None:
            raise ValueError(f"Copilot run not found: {normalized}")
        return self._subscribe_run(handle, after_sequence=after_sequence)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        """Request cancellation, including before the stream creates its run."""
        normalized = (run_id or "").strip()
        if not normalized:
            return {"run_id": normalized, "found": False, "cancelled": False, "status": "invalid"}
        with self._runs_lock:
            self._prune_runs_locked()
            handle = self._runs.get(normalized)
            if handle is None:
                self._pending_run_cancellations[normalized] = time.monotonic()
                return {"run_id": normalized, "found": False, "cancelled": True, "status": "pending"}
        with handle.condition:
            if handle.terminal:
                return {"run_id": normalized, "found": True, "cancelled": False, "status": handle.status}
            handle.cancel_event.set()
            handle.condition.notify_all()
            return {"run_id": normalized, "found": True, "cancelled": True, "status": handle.status}

    def stream_research_card_events(
        self,
        request: CopilotResearchCardRequest,
        *,
        run_id: str | None = None,
        after_sequence: int = -1,
        timeout_seconds: float | None = None,
    ) -> Iterator[CopilotRunEvent]:
        """Create or resume one server-owned Agent run and replay from a cursor."""
        resolved_domain = self._resolve_domain(request)
        normalized_request = replace(request, domain=resolved_domain)
        provider_name = getattr(self.provider, "provider_name", "unknown")
        handle, created = self._resolve_run_handle(
            normalized_request,
            run_kind="agent",
            run_id=run_id,
        )
        if created:
            self._append_run_event(
                handle,
                "run.created",
                {
                    "domain": resolved_domain,
                    "provider": provider_name,
                    "model": getattr(self.provider, "model", None),
                    "provider_streaming": hasattr(self.provider, "stream_research_card"),
                    "run_kind": "agent",
                },
            )
            worker = threading.Thread(
                target=self._execute_agent_run,
                kwargs={
                    "handle": handle,
                    "request": normalized_request,
                    "timeout_seconds": timeout_seconds,
                },
                daemon=True,
                name=f"copilot-agent-{handle.run_id}",
            )
            worker.start()
        return self._subscribe_run(handle, after_sequence=after_sequence)

    def _execute_agent_run(
        self,
        *,
        handle: _CopilotRunHandle,
        request: CopilotResearchCardRequest,
        timeout_seconds: float | None,
    ) -> None:
        resolved_domain = request.domain
        provider_name = getattr(self.provider, "provider_name", "unknown")
        deadline = time.monotonic() + (timeout_seconds or DEFAULT_COPILOT_RUN_TIMEOUT_SECONDS)

        def timed_out() -> bool:
            return time.monotonic() > deadline

        def should_cancel() -> bool:
            return handle.cancel_event.is_set() or timed_out()

        context = CopilotContextBundle(
            domain=resolved_domain,
            current_tab=request.context.current_tab,
            summary_data={},
        )

        def finalize(result: CopilotResearchCardResult) -> CopilotResearchCardResult:
            with handle.condition:
                if handle.finalized:
                    terminal = next((event.result for event in reversed(handle.events) if event.is_terminal), None)
                    return terminal or result
                handle.finalized = True
            normalized = self._normalize_result_sources(result)
            normalized = self._persist_result_turn(request, resolved_domain, context, normalized)
            return normalized

        def cancelled(reason: str) -> None:
            result = finalize(self._cancelled_result(resolved_domain, context, reason))
            self._append_run_event(handle, "cancelled", {"reason": reason}, result=result)

        if should_cancel():
            cancelled("timeout" if timed_out() and not handle.cancel_event.is_set() else "user_cancelled")
            return

        builder = self._context_builders.get(resolved_domain)
        if builder is None:
            message = f"Unsupported copilot domain: {resolved_domain}"
            result = finalize(CopilotResearchCardResult(
                domain=resolved_domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=provider_name,
                message=message,
            ))
            self._append_run_event(handle, "failed", {"message": message}, result=result)
            return

        try:
            context = builder(request)
        except ValueError as exc:
            result = finalize(CopilotResearchCardResult(
                domain=resolved_domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=provider_name,
                message=str(exc),
            ))
            self._append_run_event(handle, "failed", {"message": str(exc)}, result=result)
            return

        if should_cancel():
            cancelled("timeout" if timed_out() and not handle.cancel_event.is_set() else "user_cancelled")
            return

        tool_specs = [
            tool.to_openai_spec()
            for tool in self._tools.values()
            if resolved_domain in tool.domains
        ]
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        def provider_worker() -> None:
            try:
                if hasattr(self.provider, "stream_research_card"):
                    provider_result = self.provider.stream_research_card(
                        request=request,
                        context=context,
                        tool_specs=tool_specs,
                        execute_tool=self._execute_tool,
                        emit=lambda etype, data: event_queue.put(("event", (etype, dict(data)))),
                        should_cancel=should_cancel,
                    )
                else:
                    provider_result = self.provider.generate_research_card(
                        request=request,
                        context=context,
                        tool_specs=tool_specs,
                        execute_tool=self._execute_tool,
                    )
                event_queue.put(("final", provider_result))
            except CopilotRunCancelled as exc:
                event_queue.put(("cancelled", exc.reason))
            except Exception as exc:  # pragma: no cover - defensive transport guard
                logger.exception("Copilot streaming provider failed for domain %s", resolved_domain)
                event_queue.put(("error", f"Copilot failed: {exc}"))

        thread = threading.Thread(target=provider_worker, daemon=True, name=f"copilot-provider-{handle.run_id}")
        thread.start()

        while True:
            try:
                kind, payload = event_queue.get(timeout=0.2)
            except queue.Empty:
                if should_cancel():
                    reason = "timeout" if timed_out() and not handle.cancel_event.is_set() else "user_cancelled"
                    handle.cancel_event.set()
                    cancelled(reason)
                    return
                continue

            if kind == "event":
                etype, data = payload
                self._append_run_event(handle, etype, data)
                continue
            if kind == "final":
                if should_cancel():
                    cancelled("timeout" if timed_out() and not handle.cancel_event.is_set() else "user_cancelled")
                    return
                result = finalize(payload)
                if result.status == "refused":
                    self._append_run_event(handle, "refusal", {"message": result.message or "Request refused."})
                elif result.status == "incomplete":
                    self._append_run_event(handle, "incomplete", {"reason": result.message or "incomplete"})
                elif result.status in {"error", "unavailable"}:
                    self._append_run_event(
                        handle,
                        "provider.error",
                        {"message": result.message or "Copilot provider failed.", "provider": result.provider},
                    )
                    self._append_run_event(handle, "failed", {"message": result.message or "Copilot failed."}, result=result)
                    return
                self._append_run_event(handle, "completed", {"status": result.status}, result=result)
                return
            if kind == "cancelled":
                reason = str(payload or "cancelled")
                if timed_out() and not handle.cancel_event.is_set():
                    reason = "timeout"
                cancelled(reason)
                return
            if kind == "error":
                message = str(payload)
                self._append_run_event(handle, "provider.error", {"message": message, "provider": provider_name})
                result = finalize(CopilotResearchCardResult(
                    domain=resolved_domain,
                    current_tab=context.current_tab,
                    status="error",
                    provider=provider_name,
                    message=message,
                    sources=list(context.sources),
                    warnings=dedupe_warnings([
                        *context.warnings,
                        "Copilot generation failed before a research card could be produced.",
                    ]),
                ))
                self._append_run_event(handle, "failed", {"message": message}, result=result)
                return

    def _cancelled_result(
        self,
        domain: str,
        context: CopilotContextBundle,
        reason: str,
    ) -> CopilotResearchCardResult:
        message = (
            "Copilot run timed out before completing."
            if reason == "timeout"
            else "Copilot run was cancelled before completing."
        )
        return CopilotResearchCardResult(
            domain=domain,
            current_tab=context.current_tab,
            status="timeout" if reason == "timeout" else "cancelled",
            provider=getattr(self.provider, "provider_name", "unknown"),
            message=message,
            sources=list(context.sources),
            warnings=dedupe_warnings([*context.warnings, message]),
        )

    def stream_research_operator_events(
        self,
        request: CopilotResearchCardRequest,
        *,
        run_id: str | None = None,
        after_sequence: int = -1,
        timeout_seconds: float | None = None,
    ) -> Iterator[CopilotRunEvent]:
        """Create or resume a server-owned Research Operator run."""
        handle, created = self._resolve_run_handle(
            request,
            run_kind="operator",
            run_id=run_id,
        )
        if created:
            orchestrator = "agents_sdk" if self.agents_operator_service.config.enabled else "gamma_custom_loop"
            self._append_run_event(
                handle,
                "run.created",
                {
                    "domain": request.domain,
                    "provider": "gamma_operator_executor",
                    "model": "gamma-operator-executor-v1",
                    "orchestrator": orchestrator,
                    "run_kind": "operator",
                },
            )
            worker = threading.Thread(
                target=self._execute_operator_run,
                kwargs={
                    "handle": handle,
                    "request": request,
                    "timeout_seconds": timeout_seconds,
                },
                daemon=True,
                name=f"copilot-operator-{handle.run_id}",
            )
            worker.start()
        return self._subscribe_run(handle, after_sequence=after_sequence)

    def _execute_operator_run(
        self,
        *,
        handle: _CopilotRunHandle,
        request: CopilotResearchCardRequest,
        timeout_seconds: float | None,
    ) -> None:
        deadline = time.monotonic() + (timeout_seconds or DEFAULT_COPILOT_RUN_TIMEOUT_SECONDS)

        def timed_out() -> bool:
            return time.monotonic() > deadline

        def should_cancel() -> bool:
            return handle.cancel_event.is_set() or timed_out()

        def emit_operator_event(event: CopilotOperatorProgressEvent) -> None:
            data: dict[str, Any] = {
                "operator_event_type": event.event_type,
                "event_id": event.event_id,
                "step_id": event.step_id,
                "tool_name": event.tool_id,
                "title": event.title,
                "message": event.message,
                "payload": event.payload,
                "source_ids": list(event.source_ids),
                "warnings": list(event.warnings),
            }
            mapped_type = {
                "plan": "plan",
                "step-start": "tool.call",
                "tool-result": "tool.result",
                "warning": "warning",
                "confirmation-needed": "confirmation.needed",
                "artifact-created": "artifact.created",
                "final-report": "report",
            }.get(event.event_type, "warning")
            self._append_run_event(handle, mapped_type, data)

        if should_cancel():
            result = CopilotResearchCardResult(
                domain="synthesis",
                current_tab=request.context.current_tab or "copilot",
                status="timeout" if timed_out() and not handle.cancel_event.is_set() else "cancelled",
                provider="gamma_operator_executor",
                model="gamma-operator-executor-v1",
                message="Research Operator stopped before its first safe step.",
                warnings=["Research Operator stopped before its first safe step."],
            )
            result = self._persist_operator_execution_result(request, None, result)
            with handle.condition:
                handle.finalized = True
            self._append_run_event(
                handle,
                "cancelled",
                {"reason": "timeout" if result.status == "timeout" else "user_cancelled"},
                result=result,
            )
            return

        try:
            result = self.execute_research_operator_plan(
                request,
                run_id=handle.run_id,
                emit_event=emit_operator_event,
                should_cancel=should_cancel,
            )
        except Exception as exc:  # pragma: no cover - defensive orchestration guard
            logger.exception("Copilot Operator run failed")
            message = f"Research Operator failed: {exc}"
            self._append_run_event(
                handle,
                "provider.error",
                {"message": message, "provider": "gamma_operator_executor"},
            )
            result = CopilotResearchCardResult(
                domain="synthesis",
                current_tab=request.context.current_tab or "copilot",
                status="error",
                provider="gamma_operator_executor",
                model="gamma-operator-executor-v1",
                message=message,
                warnings=[message],
            )
            result = self._persist_operator_execution_result(request, None, result)

        with handle.condition:
            handle.finalized = True
        if result.status in {"cancelled", "timeout"}:
            self._append_run_event(
                handle,
                "cancelled",
                {"reason": "timeout" if result.status == "timeout" else "user_cancelled"},
                result=result,
            )
        elif result.status in {"error", "unavailable"}:
            self._append_run_event(handle, "failed", {"message": result.message or "Operator failed."}, result=result)
        else:
            self._append_run_event(handle, "completed", {"status": result.status}, result=result)

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

    def plan_research_operator(self, request: CopilotResearchCardRequest) -> CopilotOperatorPlan:
        research_plan = self.plan_research(request)
        steps: list[CopilotOperatorPlanStep] = []
        checkpoints: list[CopilotOperatorConfirmationCheckpoint] = []
        warnings = list(research_plan.warnings)
        prompt = str(request.prompt or "").strip().lower()

        step_index = 1
        for domain_item in research_plan.domain_plan:
            if not domain_item.planned_tools:
                warnings.append(
                    f"No registered Research Operator tools are available for {domain_item.domain} yet."
                )
                continue
            for tool_id in domain_item.planned_tools:
                definition = self.action_registry.get(tool_id)
                if definition is None:
                    warnings.append(f"Planned tool is not registered in the Research Action Registry: {tool_id}.")
                    continue
                steps.append(
                    self._operator_step_from_action(
                        definition=definition,
                        domain_item=domain_item,
                        order=step_index,
                    )
                )
                step_index += 1

        if self._prompt_requests_dcf_mutation(prompt):
            draft_definition = self.action_registry.get("fundamentals.propose_dcf_update")
            apply_definition = self.action_registry.get("fundamentals.apply_dcf_update")
            ticker = self._first_entity_id(research_plan.target_entities, "ticker")
            if ticker is None:
                warnings.append("DCF mutation planning needs a target ticker before a draft can be generated.")
            if draft_definition is not None:
                draft_step = self._operator_step_from_action(
                    definition=draft_definition,
                    domain_item=CopilotResearchPlanDomain(
                        domain="fundamentals",
                        depth="medium",
                        reason="The prompt asks the Research Operator to draft a local DCF research-state change.",
                        action_type="draft_change",
                        planned_tools=[draft_definition.tool_id],
                        required_context=["fundamentals_ticker", "dcf_model"],
                        estimated_tool_calls=1,
                        estimated_provider_calls=0,
                        estimated_latency_ms=900,
                    ),
                    order=step_index,
                    title=f"Draft DCF update{f' for {ticker}' if ticker else ''}",
                    expected_artifacts=["draft_mutation", "rendered_diff", "confirmation_token"],
                    stop_conditions=[
                        "No selected Fundamentals ticker.",
                        "No existing local DCF model for the ticker.",
                        "Draft does not change supported DCF fields.",
                    ],
                )
                steps.append(draft_step)
                step_index += 1
                if apply_definition is not None:
                    checkpoints.append(
                        CopilotOperatorConfirmationCheckpoint(
                            checkpoint_id="checkpoint_dcf_apply",
                            after_step_id=draft_step.step_id,
                            reason="Applying a DCF update mutates durable local Fundamentals research state.",
                            required_for_tool_ids=[apply_definition.tool_id],
                        )
                    )

        expected_artifacts = ["operator_trace", "operator_report", *research_plan.expected_artifacts]
        if checkpoints:
            expected_artifacts.append("confirmation_checkpoint")
        budget = self._execution_budget_for_depth(research_plan.depth_profile)
        return CopilotOperatorPlan(
            intent=research_plan.intent,
            target_entities=research_plan.target_entities,
            depth_profile=research_plan.depth_profile,
            research_plan=research_plan,
            steps=steps,
            confirmation_checkpoints=checkpoints,
            max_tool_calls=budget.max_tool_calls,
            max_provider_calls=budget.max_provider_calls,
            max_elapsed_ms=budget.max_elapsed_ms,
            requires_confirmation=bool(checkpoints),
            expected_artifacts=dedupe_warnings(expected_artifacts),
            warnings=dedupe_warnings(warnings),
        )

    def list_research_action_definitions(self) -> list[CopilotResearchActionDefinition]:
        return self.action_registry.list_definitions()

    def _action_definitions(self) -> list[CopilotResearchActionDefinition]:
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

    def execute_research_operator_plan(
        self,
        request: CopilotResearchCardRequest,
        *,
        run_id: str | None = None,
        emit_event: Callable[[CopilotOperatorProgressEvent], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> CopilotResearchCardResult:
        plan = self.plan_research_operator(request)
        if self.agents_operator_service.config.enabled:
            if should_cancel is not None and should_cancel():
                result = CopilotResearchCardResult(
                    domain="synthesis",
                    current_tab=request.context.current_tab or "copilot",
                    status="cancelled",
                    provider="openai_agents_sdk",
                    message="Research Operator was cancelled before orchestration began.",
                    warnings=["Research Operator was cancelled before orchestration began."],
                )
                return self._persist_operator_execution_result(request, plan, result)
            result = self.agents_operator_service.execute(
                request=request,
                plan=plan,
                action_registry=self.action_registry,
                build_context=lambda domain: self._build_plan_execution_context(request, domain),
                default_arguments=self._default_plan_execution_arguments,
                execute_action=self._execute_registered_operator_action,
                build_card=self._build_operator_execution_card,
            )
            result = self._normalize_result_sources(result)
            result = self._persist_agents_operator_execution_result(request, plan, result)
            if emit_event is not None:
                for event in result.operator_events:
                    emit_event(event)
            return result

        resolved_run_id = (run_id or "").strip() or new_copilot_id("oprun")
        response_id = new_copilot_id("opexec")
        sources: dict[str, CopilotSourceRef] = {}
        tool_traces: list[CopilotToolTrace] = []
        warnings = list(plan.warnings)
        events: list[CopilotOperatorProgressEvent] = []
        executed_steps: list[str] = []
        skipped_steps: list[str] = []
        failed_steps: list[str] = []
        outputs: dict[str, Any] = {}
        output_summaries: dict[str, Any] = {}
        remaining_tools = plan.max_tool_calls
        provider_calls_used = 0
        started_at = time.perf_counter()
        cancelled_at_boundary = False

        def record_event(
            event_type: str,
            *,
            step: CopilotOperatorPlanStep | None = None,
            title: str | None = None,
            message: str | None = None,
            payload: dict[str, Any] | None = None,
            source_ids: list[str] | None = None,
            event_warnings: list[str] | None = None,
        ) -> None:
            event = CopilotOperatorProgressEvent(
                    run_id=resolved_run_id,
                    event_id=new_copilot_id("opevent"),
                    sequence=len(events) + 1,
                    event_type=event_type,
                    timestamp=now_utc(),
                    step_id=step.step_id if step else None,
                    tool_id=step.tool_id if step else None,
                    title=title or (step.title if step else None),
                    message=message,
                    payload=payload or {},
                    source_ids=source_ids or [],
                    warnings=event_warnings or [],
                )
            events.append(event)
            if emit_event is not None:
                try:
                    emit_event(event)
                except Exception:
                    logger.exception("Copilot Operator event delivery failed")

        def record_warning(message: str, *, step: CopilotOperatorPlanStep | None = None) -> None:
            warnings.append(message)
            record_event("warning", step=step, title="Operator warning", message=message, event_warnings=[message])

        record_event(
            "plan",
            title="Operator plan",
            message=f"Prepared {len(plan.steps)} Research Operator step(s).",
            payload={
                "intent": plan.intent,
                "role": plan.role,
                "depth_profile": plan.depth_profile,
                "step_count": len(plan.steps),
                "checkpoint_count": len(plan.confirmation_checkpoints),
                "max_tool_calls": plan.max_tool_calls,
                "max_provider_calls": plan.max_provider_calls,
                "max_elapsed_ms": plan.max_elapsed_ms,
            },
        )
        for warning in plan.warnings:
            record_event("warning", title="Plan warning", message=warning, event_warnings=[warning])

        for step in plan.steps:
            if should_cancel is not None and should_cancel():
                cancelled_at_boundary = True
                message = "Research Operator cancellation took effect before the next safe step."
                record_warning(message, step=step)
                break
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            if elapsed_ms >= plan.max_elapsed_ms and tool_traces:
                record_warning(
                    f"Stopped operator execution after {elapsed_ms}ms, above the {plan.max_elapsed_ms}ms elapsed-time guard.",
                    step=step,
                )
                break
            if remaining_tools <= 0:
                record_warning(f"Stopped operator execution after {plan.max_tool_calls} tools.", step=step)
                break
            record_event(
                "step-start",
                step=step,
                message=f"Starting `{step.tool_id or step.step_id}`.",
                payload={
                    "order": step.order,
                    "domain": step.domain,
                    "action_type": step.action_type,
                    "permission_policy": step.permission_policy,
                },
            )
            if step.requires_confirmation or step.permission_policy == "confirmation_required":
                skipped_steps.append(step.step_id)
                message = f"Stopped before `{step.tool_id}` because confirmation is required."
                record_warning(message, step=step)
                record_event(
                    "confirmation-needed",
                    step=step,
                    message=message,
                    payload={"required_for_tool_ids": [step.tool_id] if step.tool_id else []},
                    event_warnings=[message],
                )
                break
            if step.action_type not in {"read_context", "run_analysis", "fetch_external_context"}:
                skipped_steps.append(step.step_id)
                message = f"Skipped `{step.tool_id}` because this executor only runs automatic read-only operator steps."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                continue
            if not step.tool_id:
                skipped_steps.append(step.step_id)
                message = f"Skipped {step.step_id}: no tool id was attached."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                continue
            definition = self._tools.get(step.tool_id)
            if definition is None:
                skipped_steps.append(step.step_id)
                message = f"Skipped unsupported operator tool `{step.tool_id}`."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                continue
            if definition.external_provider:
                if provider_calls_used + 1 > plan.max_provider_calls:
                    skipped_steps.append(step.step_id)
                    message = (
                        f"Skipped `{step.tool_id}` because provider calls would exceed the "
                        f"{plan.max_provider_calls} call guard."
                    )
                    record_warning(message, step=step)
                    record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                    continue
                provider_calls_used += 1

            try:
                context = self._build_plan_execution_context(request, step.domain)
            except ValueError as exc:
                skipped_steps.append(step.step_id)
                message = f"Skipped {step.step_id}: {exc}"
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                continue
            for source in context.sources:
                sources[source.source_id] = source
            for warning in context.warnings:
                record_warning(warning, step=step)

            arguments = self._default_plan_execution_arguments(step.tool_id, context)
            if arguments is None:
                skipped_steps.append(step.step_id)
                tool_traces.append(
                    CopilotToolTrace(
                        tool_name=step.tool_id,
                        summary="Skipped because operator execution could not infer required arguments.",
                        arguments={},
                        source_ids=[],
                    )
                )
                record_event(
                    "tool-result",
                    step=step,
                    message="Skipped because operator execution could not infer required arguments.",
                    payload={"status": "skipped", "arguments": {}},
                )
                continue
            execution = self._execute_tool(step.tool_id, arguments, context)
            remaining_tools -= 1
            tool_traces.append(execution.trace)
            outputs[step.step_id] = execution.output
            output_summaries[step.step_id] = self._compact_operator_output(execution.output)
            for source in execution.sources:
                sources[source.source_id] = source
            if isinstance(execution.output, dict) and execution.output.get("error"):
                skipped_steps.append(step.step_id)
                failed_steps.append(step.step_id)
                message = f"{step.tool_id} failed: {execution.output['error']}"
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "failed",
                        "trace_summary": execution.trace.summary,
                        "output_summary": output_summaries[step.step_id],
                    },
                    source_ids=list(execution.trace.source_ids),
                    event_warnings=[message],
                )
            else:
                executed_steps.append(step.step_id)
                record_event(
                    "tool-result",
                    step=step,
                    message=execution.trace.summary,
                    payload={
                        "status": "completed",
                        "arguments": execution.trace.arguments,
                        "output_kind": type(execution.output).__name__,
                        "output_summary": output_summaries[step.step_id],
                    },
                    source_ids=list(execution.trace.source_ids),
                )

        if plan.confirmation_checkpoints and not cancelled_at_boundary:
            message = "Operator plan includes confirmation checkpoints that were not applied by automatic execution."
            warnings.append(message)
            for checkpoint in plan.confirmation_checkpoints:
                record_event(
                    "confirmation-needed",
                    title="Confirmation checkpoint",
                    message=checkpoint.reason,
                    payload={
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "after_step_id": checkpoint.after_step_id,
                        "required_for_tool_ids": list(checkpoint.required_for_tool_ids),
                        "default_policy": checkpoint.default_policy,
                    },
                    event_warnings=[message],
                )

        status = "cancelled" if cancelled_at_boundary else ("ready" if executed_steps else "error")

        warnings = dedupe_warnings(warnings)
        record_event(
            "artifact-created",
            title="Operator trace",
            message="Created an operator event trace for this run.",
            payload={"artifact_type": "operator_trace", "artifact_id": resolved_run_id, "event_count": len(events) + 3},
        )
        record_event(
            "artifact-created",
            title="Operator report",
            message="Created the final Research Operator result card.",
            payload={"artifact_type": "operator_report", "artifact_id": response_id},
        )
        final_outputs, output_retention = self._bounded_operator_outputs(outputs, output_summaries)
        record_event(
            "final-report",
            title="Final operator report",
            message=(
                "Research Operator stopped at a safe step boundary."
                if cancelled_at_boundary
                else f"Executed {len(executed_steps)} automatic operator step(s)."
            ),
            payload={
                "status": status,
                "executed_steps": list(executed_steps),
                "skipped_steps": list(skipped_steps),
                "failed_steps": list(failed_steps),
                "warning_count": len(warnings),
                "source_count": len(sources),
                "tool_trace_count": len(tool_traces),
                "output_summaries": output_summaries,
                "output_retention": output_retention,
                "outputs": final_outputs,
            },
            source_ids=[source.source_id for source in list(sources.values())[:10]],
            event_warnings=warnings,
        )
        result = CopilotResearchCardResult(
            domain="synthesis",
            current_tab=request.context.current_tab or "copilot",
            status=status,
            provider="gamma_operator_executor",
            model="gamma-operator-executor-v1",
            response_id=response_id,
            message=(
                "Research Operator stopped at a safe step boundary."
                if cancelled_at_boundary
                else f"Executed {len(executed_steps)} automatic operator step(s)."
            ),
            card=self._build_operator_execution_card(
                plan,
                executed_steps,
                skipped_steps,
                list(sources.values()),
                warnings,
            ),
            sources=list(sources.values()),
            tool_traces=tool_traces,
            operator_events=events,
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
                        "operator_plan": {
                            "intent": plan.intent,
                            "role": plan.role,
                            "steps": [step.__dict__ for step in plan.steps],
                            "executed_steps": list(executed_steps),
                            "skipped_steps": list(skipped_steps),
                            "failed_steps": list(failed_steps),
                            "output_summaries": output_summaries,
                            "output_retention": output_retention,
                            "outputs": final_outputs,
                        },
                        "operator_events": [asdict(event) for event in events],
                    },
                    result=result,
                )
            except Exception:
                logger.exception("Copilot operator execution persistence failed")
                result = replace(
                    result,
                    warnings=dedupe_warnings(
                        [
                            *result.warnings,
                            "Copilot executed the operator plan, but failed to persist this turn locally.",
                        ]
                    ),
                )
        return result

    def _execute_registered_operator_action(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        definition = self.action_registry.get(tool_id)
        if definition is None:
            return CopilotToolExecution(
                output={"error": f"Unsupported Research Action Registry tool: {tool_id}"},
                trace=CopilotToolTrace(
                    tool_name=tool_id,
                    summary="Gamma rejected an action that is not registered.",
                    arguments=arguments,
                    source_ids=[],
                ),
            )
        if (
            definition.action_type not in {"read_context", "run_analysis", "fetch_external_context"}
            or not definition.read_only
            or definition.mutates_local_state
            or definition.requires_confirmation
        ):
            return CopilotToolExecution(
                output={"error": f"Action is not automatic read-only work: {tool_id}"},
                trace=CopilotToolTrace(
                    tool_name=tool_id,
                    summary="Gamma blocked a non-automatic or state-changing operator action.",
                    arguments=arguments,
                    source_ids=[],
                ),
            )
        return self._execute_tool(tool_id, arguments, context)

    def _persist_operator_execution_result(
        self,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan | None,
        result: CopilotResearchCardResult,
    ) -> CopilotResearchCardResult:
        """Persist an Operator terminal that did not enter an orchestrator path."""
        if self.store is None:
            return result
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
                    "operator_plan": asdict(plan) if plan is not None else None,
                    "operator_events": [asdict(event) for event in result.operator_events],
                    "terminal_status": result.status,
                },
                result=result,
            )
        except Exception:
            logger.exception("Copilot Operator terminal persistence failed")
            return replace(
                result,
                warnings=dedupe_warnings(
                    [*result.warnings, "Research Operator finished, but its terminal state was not persisted locally."]
                ),
            )
        return result

    def _persist_agents_operator_execution_result(
        self,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        result: CopilotResearchCardResult,
    ) -> CopilotResearchCardResult:
        final_payload: dict[str, Any] = {}
        for event in reversed(result.operator_events):
            if event.event_type == "final-report":
                final_payload = dict(event.payload)
                break
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
                        "operator_plan": {
                            "intent": plan.intent,
                            "role": plan.role,
                            "orchestrator": result.provider,
                            "steps": [step.__dict__ for step in plan.steps],
                            "executed_steps": list(final_payload.get("executed_steps") or []),
                            "skipped_steps": list(final_payload.get("skipped_steps") or []),
                            "failed_steps": list(final_payload.get("failed_steps") or []),
                            "output_summaries": dict(final_payload.get("output_summaries") or {}),
                            "output_retention": dict(final_payload.get("output_retention") or {}),
                            "outputs": dict(final_payload.get("outputs") or {}),
                        },
                        "operator_events": [asdict(event) for event in result.operator_events],
                    },
                    result=result,
                )
            except Exception:
                logger.exception("Copilot Agents SDK operator execution persistence failed")
                result = replace(
                    result,
                    warnings=dedupe_warnings(
                        [
                            *result.warnings,
                            "Copilot executed the Agents SDK operator plan, but failed to persist this turn locally.",
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
        if domain == "iv":
            ticker = self._first_plan_entity_id(request, "ticker")
            if ticker:
                state = dict(domain_context.iv_state or {})
                state.setdefault("target_symbol", ticker)
                domain_context = replace(domain_context, iv_state=state)

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
        if tool_name == "run_fundamentals_reverse_valuation":
            return {"ticker": context.summary_data.get("ticker")}
        if tool_name == "run_strategy_lab_backtest":
            return {"result_kind": "auto"}
        if tool_name == "run_research_scope_analysis":
            return self._default_research_scope_analysis_arguments(context)
        if tool_name == "run_hypothetical_portfolio_comparison":
            return self._default_hypothetical_portfolio_arguments(context)
        if tool_name == "run_options_realized_implied_comparison":
            return {
                "symbol": context.summary_data.get("target_symbol"),
                "max_expiries": 6,
                "depth_preset": "compact",
                "market_data_mode": None,
            }
        if tool_name == "run_risk_contribution_analysis":
            return {
                "source_scope": context.summary_data.get("workspace_mode"),
                "top_n": 10,
                "include_monte_carlo": True,
            }
        if tool_name == "run_risk_scenario_analysis":
            is_rate_shock = "rate" in str(context.summary_data).lower()
            return {
                "scenario_label": "rate_shock_plus_100bps" if is_rate_shock else "baseline_risk",
                "source_scope": context.summary_data.get("workspace_mode"),
                "scenario_type": "rate_shock" if is_rate_shock else "baseline",
                "rate_shift_bps": 100.0 if is_rate_shock else None,
                "equity_shock_pct": None,
                "duration_proxy_years": None,
                "symbol_shocks": [],
            }
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

    @staticmethod
    def _build_operator_execution_card(
        plan: CopilotOperatorPlan,
        executed_steps: list[str],
        skipped_steps: list[str],
        sources: list[CopilotSourceRef],
        warnings: list[str],
    ) -> ResearchCard:
        evidence_refs = [source.source_id for source in sources[:10]]
        step_lookup = {step.step_id: step for step in plan.steps}
        executed_labels = [
            step_lookup[step_id].title
            for step_id in executed_steps
            if step_id in step_lookup
        ]
        skipped_labels = [
            step_lookup[step_id].title
            for step_id in skipped_steps
            if step_id in step_lookup
        ]
        claims = []
        if evidence_refs:
            claims.append(
                ResearchClaim(
                    claim="Gamma executed automatic read-only Research Operator steps and preserved the source trace.",
                    evidence_refs=evidence_refs,
                )
            )
        return ResearchCard(
            title=f"Executed Research Operator Plan: {plan.intent.replace('_', ' ')}",
            hypothesis=(
                f"The request maps to a {plan.depth_profile} Research Operator plan with "
                f"{len(plan.steps)} planned step(s)."
            ),
            rationale=(
                f"Executed steps: {', '.join(executed_labels) or 'none'}. "
                f"Skipped steps: {', '.join(skipped_labels) or 'none'}."
            ),
            required_data=[step.domain for step in plan.steps],
            proposed_test="Review the operator trace and generated warnings before turning this into a final memo or saved research artifact.",
            confounders=warnings[:8],
            next_steps=[
                "Inspect the tool traces for exact inputs and outputs.",
                "Load missing domain state if any operator step was skipped.",
                "Confirm any durable local research-state mutation separately.",
            ],
            caveats=[
                "This executor runs automatic read-only operator steps only.",
                "Custom shock repricing and confirmed state mutations are gated for later operator slices.",
            ],
            source_backed_claims=claims,
            inferred_claims=[
                "The operator output is an analytical workup, not an investment decision or execution instruction."
            ],
        )

    @classmethod
    def _normalize_result_sources(cls, result: CopilotResearchCardResult) -> CopilotResearchCardResult:
        normalized = replace(
            result,
            sources=[
                replace(source, retrieved_at=cls._coerce_source_datetime(source.retrieved_at))
                for source in result.sources
            ],
        )
        return resolve_result_evidence(normalized)

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
            if match.lower() in {"cpi", "fed", "iv", "oil", "rate", "rates", "var"}:
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
            "research": ("scope", "scope analysis", "research scope"),
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

        if CopilotService._prompt_requests_hypothetical_portfolio(prompt):
            return "hypothetical_portfolio_comparison"
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
        elif intent == "hypothetical_portfolio_comparison":
            add(
                "research",
                "deep",
                "The request asks Gamma to compare a hypothetical research portfolio against a benchmark using read-only historical analytics.",
                action_type="run_analysis",
                planned_tools=["run_hypothetical_portfolio_comparison"],
                required_context=["symbols", "weights", "benchmark_symbol"],
            )
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
            "equity_research": ["run_research_scope_analysis", "get_research_scope_summary", "get_research_coverage_context"],
            "research": ["run_research_scope_analysis", "get_research_scope_summary", "get_research_coverage_context"],
            "strategy_lab": ["run_strategy_lab_backtest"],
            "macro": ["get_macro_workspace_drilldown", "get_macro_series_history_summary"],
            "commodities": ["get_commodities_workspace_summary"],
            "prediction_markets": ["get_prediction_market_history_summary", "get_prediction_market_flow_context"],
            "crypto": ["get_crypto_price_history_summary", "get_crypto_liquidity_context", "get_crypto_comparison_context"],
            "fundamentals": [
                "get_fundamentals_company_context",
                "get_fundamentals_statement_context",
                "get_fundamentals_peer_context",
                "get_fundamentals_dcf_context",
                "run_fundamentals_reverse_valuation",
            ],
            "risk": ["run_risk_contribution_analysis", "run_risk_scenario_analysis"],
            "iv": ["run_options_realized_implied_comparison", "get_iv_surface_context", "get_iv_session_status"],
            "external_context": ["get_external_context_summary"],
            "synthesis": ["get_synthesis_scope_summary", "get_synthesis_domain_context"],
        }.get(domain, [])

    @staticmethod
    def _operator_step_from_action(
        *,
        definition: CopilotResearchActionDefinition,
        domain_item: CopilotResearchPlanDomain,
        order: int,
        title: str | None = None,
        expected_artifacts: list[str] | None = None,
        stop_conditions: list[str] | None = None,
    ) -> CopilotOperatorPlanStep:
        inferred_artifacts = expected_artifacts
        if inferred_artifacts is None:
            inferred_artifacts = ["tool_trace", "source_refs"]
            if definition.action_type == "fetch_external_context":
                inferred_artifacts.append("freshness_labels")
            if definition.action_type == "run_analysis":
                inferred_artifacts.append("analysis_result")
            if definition.action_type == "draft_change":
                inferred_artifacts.extend(["draft_diff", "confirmation_token"])
        step_title = title or CopilotService._operator_step_title(definition)
        return CopilotOperatorPlanStep(
            step_id=f"step_{order:02d}_{CopilotService._safe_source_id(definition.tool_id).lower()}",
            order=order,
            title=step_title,
            domain=domain_item.domain,
            action_type=definition.action_type,
            tool_id=definition.tool_id,
            permission_policy=definition.permission_policy,
            requires_confirmation=definition.requires_confirmation,
            expected_artifacts=inferred_artifacts,
            rationale=domain_item.reason,
            stop_conditions=stop_conditions
            or [
                "Required Gamma context is missing.",
                "Execution budget is exhausted.",
                "Provider is unavailable or stale beyond the tool policy.",
            ],
            estimated_latency_ms=max(domain_item.estimated_latency_ms, int(definition.timeout_seconds * 1000 / 3)),
            warnings=list(definition.failure_modes),
        )

    @staticmethod
    def _operator_step_title(definition: CopilotResearchActionDefinition) -> str:
        cleaned = definition.tool_id
        for prefix in ("get_", "run_", "inspect_", "fetch_"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        cleaned = cleaned.replace(".", " ").replace("_", " ")
        return cleaned[:1].upper() + cleaned[1:]

    @staticmethod
    def _prompt_requests_dcf_mutation(prompt: str) -> bool:
        if "dcf" not in prompt:
            return False
        mutation_terms = (
            "adjust",
            "apply",
            "change",
            "edit",
            "modify",
            "raise",
            "lower",
            "update",
            "cell",
            "cells",
            "assumption",
            "assumptions",
        )
        return any(term in prompt for term in mutation_terms)

    @staticmethod
    def _prompt_requests_hypothetical_portfolio(prompt: str) -> bool:
        normalized = str(prompt or "").lower()
        if "portfolio" not in normalized:
            return False
        comparison_terms = ("compare", "comparison", "versus", " vs ", "against", "relative to", "to ")
        hypothetical_terms = ("hypothetical", "research portfolio", "synthetic", "60/40", "70/30", "50/50")
        return any(term in normalized for term in comparison_terms) and any(
            term in normalized for term in hypothetical_terms
        )

    @staticmethod
    def _first_entity_id(entities: list[CopilotResearchPlanEntity], kind: str) -> str | None:
        for entity in entities:
            if entity.kind == kind:
                return entity.id
        return None

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
            if self._prompt_requests_hypothetical_portfolio(str(request.prompt or "").lower()):
                source = CopilotSourceRef(
                    source_id="research.hypothetical_request",
                    label="Hypothetical research request",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.copilot.operator.hypothetical_portfolio",
                    description="Prompt-derived hypothetical portfolio comparison request; no saved research state is modified.",
                    retrieved_at=now_utc(),
                )
                return CopilotContextBundle(
                    domain="research",
                    current_tab=request.context.current_tab or "research",
                    summary_data={
                        "workspace_mode": request.context.workspace_mode or "research",
                        "prompt": request.prompt,
                        "research": None,
                    },
                    tool_state={},
                    sources=[source],
                    warnings=[],
                )
            raise ValueError("Research copilot requires an active research result.")
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "research",
            "prompt": request.prompt,
            "research": summarize_research_result(result),
        }
        strategy_lab_handoffs = self._summarize_strategy_lab_handoff_context(state.get("strategy_lab_handoffs"))
        if strategy_lab_handoffs.get("current_count"):
            summary_data["strategy_lab_handoffs"] = strategy_lab_handoffs
        warnings = dedupe_warnings(result.get("warnings", []), strategy_lab_handoffs.get("warnings", []))
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
        if strategy_lab_handoffs.get("current_count"):
            sources.extend(self._strategy_lab_handoff_sources(strategy_lab_handoffs))
        return CopilotContextBundle(
            domain="research",
            current_tab=request.context.current_tab or "research",
            summary_data=summary_data,
            tool_state={"result": result, "strategy_lab_handoffs": strategy_lab_handoffs},
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
        handoff_context = self._summarize_strategy_lab_handoff_context(state.get("handoff_context"))
        if not any(isinstance(item, dict) for item in (imported_result, composition, compare_result)) and not handoff_context.get("current_count"):
            raise ValueError("Strategy Lab copilot requires an active import, composition, comparison, or current handoff.")
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "research",
            "imported_result": imported_result if isinstance(imported_result, dict) else None,
            "composition": composition if isinstance(composition, dict) else None,
            "compare_result": compare_result if isinstance(compare_result, dict) else None,
            "handoff_context": handoff_context,
        }
        warnings = dedupe_warnings(
            (imported_result or {}).get("warnings", []) if isinstance(imported_result, dict) else [],
            (composition or {}).get("warnings", []) if isinstance(composition, dict) else [],
            (compare_result or {}).get("warnings", []) if isinstance(compare_result, dict) else [],
            handoff_context.get("warnings", []),
        )
        sources = []
        if any(isinstance(item, dict) for item in (imported_result, composition, compare_result)):
            sources.append(
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
            )
        if handoff_context.get("items"):
            sources.extend(self._strategy_lab_handoff_sources(handoff_context))
        return CopilotContextBundle(
            domain="strategy_lab",
            current_tab=request.context.current_tab or "strategy_lab",
            summary_data=summary_data,
            tool_state=summary_data,
            sources=sources,
            warnings=warnings,
        )

    @classmethod
    def _summarize_strategy_lab_handoff_context(cls, handoff_context: Any) -> dict[str, Any]:
        if not isinstance(handoff_context, dict):
            return {
                "context_state": "no_current_handoffs",
                "current_count": 0,
                "stale_count": 0,
                "status_counts": {},
                "has_pending": False,
                "has_resolved": False,
                "has_unsupported": False,
                "has_errors": False,
                "items": [],
                "warnings": [],
            }
        raw_items = handoff_context.get("items")
        items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        summarized_items = [cls._summarize_strategy_lab_handoff_item(item) for item in items]
        current_items = [item for item in summarized_items if not item.get("stale")]
        status_counts: dict[str, int] = {}
        for item in summarized_items:
            key = "stale" if item.get("stale") else str(item.get("status") or "unknown")
            status_counts[key] = status_counts.get(key, 0) + 1
        warnings = dedupe_warnings(
            handoff_context.get("warnings", []) if isinstance(handoff_context.get("warnings"), list) else [],
            *(item.get("warnings", []) for item in summarized_items),
            *(item.get("resolved", {}).get("warnings", []) for item in summarized_items if isinstance(item.get("resolved"), dict)),
        )
        has_pending = any(item.get("status") in {"pending", "resolving"} and not item.get("stale") for item in summarized_items)
        has_resolved = any(item.get("status") == "resolved" and not item.get("stale") for item in summarized_items)
        has_unsupported = any(item.get("status") == "unsupported" and not item.get("stale") for item in summarized_items)
        has_errors = any(item.get("status") == "error" and not item.get("stale") for item in summarized_items)
        if not current_items:
            context_state = "no_current_handoffs"
        elif has_resolved and not (has_pending or has_unsupported or has_errors):
            context_state = "resolved_handoffs"
        elif has_pending and not (has_resolved or has_unsupported or has_errors):
            context_state = "pending_handoffs"
        else:
            context_state = "mixed_handoff_states"
        return {
            "context_state": str(handoff_context.get("context_state") or context_state),
            "computed_context_state": context_state,
            "current_count": len(current_items),
            "stale_count": len(summarized_items) - len(current_items),
            "status_counts": status_counts,
            "has_pending": has_pending,
            "has_resolved": has_resolved,
            "has_unsupported": has_unsupported,
            "has_errors": has_errors,
            "items": summarized_items[:20],
            "warnings": warnings,
        }

    @classmethod
    def _summarize_strategy_lab_handoff_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        entity = item.get("selected_entity") if isinstance(item.get("selected_entity"), dict) else {}
        resolved = item.get("resolved") if isinstance(item.get("resolved"), dict) else None
        return {
            "id": str(item.get("id") or ""),
            "source_id": f"strategy_lab.handoff.{cls._safe_source_id(str(item.get('id') or entity.get('normalized_id') or entity.get('label') or 'unknown')).lower()}",
            "status": str(item.get("status") or "pending"),
            "context_state": str(item.get("context_state") or ""),
            "stale": bool(item.get("stale")),
            "enqueued_at": item.get("enqueued_at"),
            "updated_at": item.get("updated_at"),
            "source_tab": item.get("source_tab"),
            "source_mode": item.get("source_mode"),
            "resolver_capability": item.get("resolver_capability"),
            "asset_class": item.get("asset_class"),
            "value_kind": item.get("value_kind"),
            "default_side": item.get("default_side"),
            "default_weight": item.get("default_weight"),
            "provider": item.get("provider"),
            "selected_timeframe": item.get("selected_timeframe") if isinstance(item.get("selected_timeframe"), dict) else None,
            "selected_entity": {
                "entity_type": entity.get("entity_type"),
                "label": entity.get("label"),
                "normalized_id": entity.get("normalized_id"),
                "provider_id": entity.get("provider_id"),
                "native_id": entity.get("native_id"),
            },
            "normalized_ids": item.get("normalized_ids") if isinstance(item.get("normalized_ids"), dict) else {},
            "warnings": [str(warning) for warning in item.get("warnings", []) if str(warning).strip()]
            if isinstance(item.get("warnings"), list)
            else [],
            "error": item.get("error"),
            "resolved": cls._summarize_strategy_lab_resolved_handoff(resolved),
        }

    @classmethod
    def _summarize_strategy_lab_resolved_handoff(cls, resolved: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(resolved, dict):
            return None
        resolved_objects = resolved.get("resolved_objects") if isinstance(resolved.get("resolved_objects"), dict) else {}
        return {
            "handoff_id": resolved.get("handoff_id"),
            "status": resolved.get("status"),
            "resolved_capability": resolved.get("resolved_capability"),
            "date_coverage": resolved.get("date_coverage") if isinstance(resolved.get("date_coverage"), dict) else None,
            "provider_summary": resolved.get("provider_summary"),
            "provenance": resolved.get("provenance") if isinstance(resolved.get("provenance"), dict) else {},
            "warnings": [str(warning) for warning in resolved.get("warnings", []) if str(warning).strip()]
            if isinstance(resolved.get("warnings"), list)
            else [],
            "unsupported_reason": resolved.get("unsupported_reason"),
            "resolved_objects": {
                "composer_draft_leg": cls._compact_nested_mapping(resolved_objects.get("composer_draft_leg")),
                "benchmark_draft": cls._compact_nested_mapping(resolved_objects.get("benchmark_draft")),
                "lens": cls._compact_nested_mapping(resolved_objects.get("lens")),
                "overlay": cls._compact_nested_mapping(resolved_objects.get("overlay")),
            },
        }

    @staticmethod
    def _compact_nested_mapping(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        allowed = {
            "label",
            "display_name",
            "identifier",
            "object_id",
            "object_type",
            "source_tab",
            "source_mode",
            "asset_class",
            "value_kind",
            "resolver_capability",
            "resolver_capabilities",
            "return_point_count",
            "coverage_start",
            "coverage_end",
            "available_start",
            "available_end",
            "provider_summary",
            "date_coverage",
            "provenance",
            "warnings",
        }
        return {key: value.get(key) for key in sorted(allowed) if key in value}

    @staticmethod
    def _strategy_lab_handoff_sources(handoff_context: dict[str, Any]) -> list[CopilotSourceRef]:
        sources = [
            CopilotSourceRef(
                source_id="strategy_lab.handoffs",
                label="Strategy Lab handoff queue",
                kind="workspace",
                provider="gamma",
                origin="gamma.strategy_lab.handoff_queue",
                description="Current Strategy Lab inbound handoff queue state, including pending, resolved, unsupported, and stale items.",
                retrieved_at=now_utc(),
            )
        ]
        for item in handoff_context.get("items", []):
            if not isinstance(item, dict):
                continue
            entity = item.get("selected_entity") if isinstance(item.get("selected_entity"), dict) else {}
            sources.append(
                CopilotSourceRef(
                    source_id=str(item.get("source_id") or "strategy_lab.handoff.unknown"),
                    label=str(entity.get("label") or item.get("id") or "Strategy Lab handoff"),
                    kind="handoff",
                    provider=str(item.get("provider") or "gamma"),
                    origin="gamma.strategy_lab.handoff_queue",
                    description=(
                        f"Strategy Lab handoff state `{item.get('context_state') or item.get('status')}` "
                        f"from {item.get('source_tab') or 'unknown source'}; capability `{item.get('resolver_capability')}`."
                    ),
                    retrieved_at=item.get("updated_at") or item.get("enqueued_at") or now_utc(),
                )
            )
        return sources

    def _build_risk_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        state = request.context.risk_state or {}
        result = state.get("result")
        snapshot = state.get("snapshot") if isinstance(state.get("snapshot"), dict) else None
        if snapshot is None and isinstance(request.context.portfolio_state, dict):
            portfolio_snapshot = request.context.portfolio_state.get("snapshot")
            if isinstance(portfolio_snapshot, dict):
                snapshot = portfolio_snapshot
        if not isinstance(result, dict) and snapshot is None:
            raise ValueError("Risk copilot requires an active risk result or a portfolio snapshot.")
        summary_data = {
            "workspace_mode": request.context.workspace_mode or "portfolio",
            "prompt": request.prompt,
            "risk": summarize_risk_result(result) if isinstance(result, dict) else None,
            "snapshot": summarize_portfolio_snapshot(snapshot),
        }
        warnings = dedupe_warnings(
            result.get("warnings", []) if isinstance(result, dict) else [],
            (snapshot or {}).get("warnings", []),
        )
        sources = []
        if isinstance(result, dict):
            sources.append(
                CopilotSourceRef(
                    source_id="risk.result",
                    label="Risk computation result",
                    kind="analytics",
                    provider="gamma",
                    origin="gamma.risk.compute",
                    description="Active risk computation payload returned by Gamma.",
                    retrieved_at=None,
                )
            )
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
                "result": result if isinstance(result, dict) else None,
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
        target_symbol = self._iv_target_symbol_from_state(state, surface, session)
        summary = summarize_iv_state(surface, session)
        if summary is None:
            summary = {
                "symbol": target_symbol,
                "snapshot_available": False,
                "warnings": ["No active Options surface is loaded; operator tools may request a bounded service snapshot."],
            }
        warnings = dedupe_warnings(summary.get("warnings", []))
        sources = []
        if isinstance(active_surface, dict):
            sources.append(
                CopilotSourceRef(
                    source_id="iv.surface",
                    label="Options surface snapshot",
                    kind="workspace",
                    provider="gamma",
                    origin="gamma.iv.surface",
                    description="Loaded options implied-volatility surface payload from Gamma.",
                    retrieved_at=active_surface.get("timestamp"),
                )
            )
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
                "target_symbol": target_symbol,
                "iv": summary,
            },
            tool_state={
                "surface": surface,
                "session": session,
                "target_symbol": target_symbol,
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

    def _build_sitrep_context(self, request: CopilotResearchCardRequest) -> CopilotContextBundle:
        if self.sitrep_service is None:
            raise ValueError("SITREP copilot requires a configured SitrepService.")
        workspace = self.sitrep_service.get_workspace(SitrepWorkspaceRequest(force_refresh=False))
        warnings: list[str] = list(workspace.section_warnings)

        follow_ups: list[dict[str, Any]] = []
        if self.sitrep_service.follow_up_store is not None:
            follow_ups = [
                {
                    "id": item.id,
                    "title": item.title,
                    "source": item.source,
                    "detail": item.detail,
                    "note": item.note,
                    "status": item.status,
                    "saved_at": item.saved_at.isoformat(),
                }
                for item in self.sitrep_service.list_follow_ups()[:12]
            ]
        else:
            warnings.append("SITREP follow-up persistence is not configured; follow-ups are omitted.")

        summary_data: dict[str, Any] = {
            "workspace_mode": request.context.workspace_mode or "research",
            "retrieved_at": workspace.retrieved_at.isoformat(),
            "sections_loaded": [
                section
                for section, payload in (
                    ("equities", workspace.equities_overview),
                    ("indices", workspace.indices_overview),
                    ("macro", workspace.macro_snapshot),
                    ("commodities", workspace.commodities),
                    ("prediction_markets", workspace.prediction_markets),
                    ("news", workspace.news),
                )
                if payload is not None
            ],
            "section_warnings": list(workspace.section_warnings),
            "equities": self._sitrep_overview_summary(workspace.equities_overview),
            "indices": self._sitrep_overview_summary(workspace.indices_overview),
            "macro": self._sitrep_macro_summary(workspace.macro_snapshot),
            "commodities": self._sitrep_commodities_summary(workspace.commodities),
            "prediction_markets": self._sitrep_prediction_summary(workspace.prediction_markets),
            "news": self._sitrep_news_summary(workspace.news),
            "follow_ups": follow_ups,
            "warnings": warnings,
        }

        sources = [
            CopilotSourceRef(
                source_id="sitrep.workspace",
                label="SITREP situation-report workspace",
                kind="workspace",
                provider=workspace.source_provider,
                origin=workspace.origin,
                description="Backend-composed SITREP workspace: equities, indices, macro, commodities, prediction markets, and news sections with per-section degradation warnings.",
                retrieved_at=workspace.retrieved_at,
            )
        ]
        for section, payload in (
            ("equities", workspace.equities_overview),
            ("indices", workspace.indices_overview),
            ("macro", workspace.macro_snapshot),
            ("commodities", workspace.commodities),
            ("news", workspace.news),
        ):
            if payload is None:
                continue
            sources.append(
                CopilotSourceRef(
                    source_id=f"sitrep.{section}",
                    label=f"SITREP {section.replace('_', ' ')} section",
                    kind="workspace_section",
                    provider=str(getattr(payload, "source_provider", "") or "gamma"),
                    origin=str(getattr(payload, "origin", "") or f"gamma.sitrep.{section}"),
                    description=f"{section.replace('_', ' ').title()} payload embedded in the SITREP workspace.",
                    retrieved_at=getattr(payload, "retrieved_at", None),
                )
            )
        if follow_ups:
            sources.append(
                CopilotSourceRef(
                    source_id="sitrep.follow_ups",
                    label="SITREP saved follow-ups",
                    kind="saved_research",
                    provider="gamma_sitrep",
                    origin="sitrep_follow_up_store",
                    description="Locally persisted SITREP triage follow-ups with notes and resolved states.",
                    retrieved_at=workspace.retrieved_at,
                )
            )

        return CopilotContextBundle(
            domain="sitrep",
            current_tab=request.context.current_tab or "sitrep",
            summary_data=summary_data,
            tool_state={"workspace": workspace, "follow_ups": follow_ups},
            sources=sources,
            warnings=dedupe_warnings(warnings),
        )

    @staticmethod
    def _sitrep_overview_summary(overview: Any) -> dict[str, Any] | None:
        if overview is None:
            return None

        def _rank_items(items: Any) -> list[dict[str, Any]]:
            return [
                {"label": item.label, "symbol": item.symbol, "value": item.value}
                for item in list(items)[:3]
            ]

        return {
            "universe_id": overview.universe_id,
            "universe_label": overview.universe_label,
            "timeframe": overview.timeframe,
            "coverage_ratio": overview.coverage.coverage_ratio,
            "coverage_label": overview.coverage_label,
            "freshness_label": getattr(overview.freshness_label, "value", str(overview.freshness_label)),
            "leaders": _rank_items(overview.rankings.leaders),
            "laggards": _rank_items(overview.rankings.laggards),
            "warning_count": len(overview.warnings),
        }

    @staticmethod
    def _sitrep_macro_summary(snapshot: Any) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        return {
            "region": snapshot.region,
            "timeframe": snapshot.timeframe,
            "focus_items": [
                {"title": item.title, "why_now": item.why_now}
                for item in snapshot.focus_items[:3]
            ],
            "top_divergences": [
                {"headline": row.headline, "label": row.label}
                for row in snapshot.top_divergences[:3]
            ],
            "upcoming_events": [
                {"title": event.title, "scheduled_at": event.scheduled_at.isoformat()}
                for event in snapshot.upcoming_events[:3]
            ],
            "warning_count": len(snapshot.warnings),
        }

    @staticmethod
    def _sitrep_commodities_summary(workspace: Any) -> dict[str, Any] | None:
        if workspace is None:
            return None
        return {
            "mode": workspace.mode,
            "coverage_status": workspace.coverage.coverage_status,
            "provider": workspace.coverage.source_provider or workspace.coverage.provider_id,
            "freshness_label": workspace.coverage.freshness_label,
            "movers": [
                {
                    "instrument_id": summary.instrument.instrument_id,
                    "name": summary.instrument.name,
                    "family": summary.instrument.family,
                    "latest_change_pct": summary.latest_change_pct,
                    "curve_state": summary.curve_state,
                }
                for summary in workspace.market_summaries[:6]
            ],
            "event_count": len(workspace.events),
            "warning_count": len(workspace.warnings),
        }

    @staticmethod
    def _sitrep_prediction_summary(screener: Any) -> dict[str, Any] | None:
        if screener is None:
            return None
        return {
            "markets": [
                {
                    "market_id": market.market_id,
                    "title": market.title,
                    "venue": market.venue,
                    "current_probability": market.current_probability,
                }
                for market in screener.markets[:6]
            ],
            "venues": [venue.venue for venue in screener.venues],
            "warning_count": len(screener.warnings),
        }

    @staticmethod
    def _sitrep_news_summary(feed: Any) -> dict[str, Any] | None:
        if feed is None:
            return None
        return {
            "source_provider": feed.source_provider,
            "freshness_label": getattr(feed.freshness_label, "value", str(feed.freshness_label)),
            "items": [
                {
                    "title": item.title,
                    "source_name": item.source_name,
                    "published_at": item.published_at.isoformat(),
                    "tickers": [
                        entity.symbol
                        for entity in item.detected_entities
                        if getattr(entity, "symbol", None)
                    ],
                }
                for item in feed.items[:10]
            ],
            "warning_count": len(feed.warnings),
        }

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

    def _tool_run_research_scope_analysis(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        if self.research_provider is None:
            raise ValueError("Research provider is unavailable to Copilot.")
        normalized = self._normalize_research_scope_analysis_arguments(arguments, context)
        research_service = ResearchService(self.research_provider)
        analysis = research_service.analyze(
            ResearchAnalysisRequest(
                scope_type=normalized["scope_type"],
                primary_symbol=normalized["primary_symbol"],
                synthetic_positions=[
                    SyntheticPosition(
                        symbol=position["symbol"],
                        weight=position["weight"],
                        instrument_id=position.get("instrument_id"),
                        display_symbol=position.get("display_symbol"),
                        sec_type=position.get("sec_type"),
                        currency=position.get("currency"),
                        exchange=position.get("exchange"),
                        primary_exchange=position.get("primary_exchange"),
                        provider=position.get("provider"),
                        provider_id=position.get("provider_id"),
                    )
                    for position in normalized["synthetic_positions"]
                ],
                benchmark_symbol=normalized["benchmark_symbol"],
                lookback_days=normalized["lookback_days"],
            )
        )
        output = self._research_scope_analysis_operator_summary(
            analysis,
            normalized=normalized,
        )
        source = CopilotSourceRef(
            source_id="research.scope_analysis.operator",
            label="Research scope operator analysis",
            kind="analytics",
            provider=analysis.source_provider,
            origin="gamma.research.analyze",
            description="Read-only Research Operator analysis of the active or supplied Research scope.",
            retrieved_at=analysis.snapshot.timestamp if analysis.snapshot is not None else now_utc(),
        )
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_research_scope_analysis",
                summary=f"Ran read-only Research scope analysis for {normalized['scope_type'].value}.",
                arguments={
                    "scope_type": normalized["scope_type"].value,
                    "primary_symbol": normalized["primary_symbol"],
                    "benchmark_symbol": normalized["benchmark_symbol"],
                    "lookback_days": normalized["lookback_days"],
                    "synthetic_position_count": len(normalized["synthetic_positions"]),
                },
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_run_strategy_lab_backtest(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        result_kind, result = self._strategy_lab_active_result(context, arguments.get("result_kind"))
        source = CopilotSourceRef(
            source_id=f"strategy_lab.{result_kind}.operator_backtest",
            label="Strategy Lab operator backtest",
            kind="analytics",
            provider=str(result.get("source_provider") or "gamma"),
            origin=str(result.get("origin") or "gamma.strategy_lab"),
            description="Read-only Research Operator summary of the active Strategy Lab analysis result.",
            retrieved_at=result.get("retrieved_at"),
        )
        output = self._strategy_lab_operator_summary(result_kind, result)
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_strategy_lab_backtest",
                summary=f"Summarized the active Strategy Lab {result_kind.replace('_', ' ')} as a read-only backtest.",
                arguments={"result_kind": result_kind},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_get_strategy_lab_handoff_context(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        del arguments
        handoff_context = context.tool_state.get("handoff_context")
        if not isinstance(handoff_context, dict):
            handoff_context = self._summarize_strategy_lab_handoff_context(None)
        sources = self._strategy_lab_handoff_sources(handoff_context)
        source_ids = [source.source_id for source in sources]
        return CopilotToolExecution(
            output={
                "context_state": handoff_context.get("context_state"),
                "computed_context_state": handoff_context.get("computed_context_state"),
                "current_count": handoff_context.get("current_count"),
                "stale_count": handoff_context.get("stale_count"),
                "status_counts": dict(handoff_context.get("status_counts") or {}),
                "has_pending": bool(handoff_context.get("has_pending")),
                "has_resolved": bool(handoff_context.get("has_resolved")),
                "has_unsupported": bool(handoff_context.get("has_unsupported")),
                "has_errors": bool(handoff_context.get("has_errors")),
                "items": list(handoff_context.get("items", []) or []),
                "warnings": list(handoff_context.get("warnings", []) or []),
            },
            trace=CopilotToolTrace(
                tool_name="get_strategy_lab_handoff_context",
                summary=(
                    "Expanded Strategy Lab handoff context: "
                    f"{handoff_context.get('current_count', 0)} current, "
                    f"{handoff_context.get('stale_count', 0)} stale."
                ),
                arguments={},
                source_ids=source_ids,
            ),
            sources=sources,
        )

    def _tool_run_hypothetical_portfolio_comparison(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        if self.research_provider is None:
            raise ValueError("Research provider is unavailable to Copilot.")
        normalized = self._normalize_hypothetical_portfolio_arguments(arguments)
        research_service = ResearchService(self.research_provider)
        analysis = research_service.analyze(
            ResearchAnalysisRequest(
                scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
                synthetic_positions=[
                    SyntheticPosition(
                        symbol=leg["symbol"],
                        weight=leg["weight"],
                        sec_type=leg.get("sec_type") or None,
                        currency=leg.get("currency") or None,
                        exchange=leg.get("exchange") or None,
                    )
                    for leg in normalized["legs"]
                ],
                benchmark_symbol=normalized["benchmark_symbol"],
                lookback_days=normalized["lookback_days"],
            )
        )
        comparison = research_service.compare_research(
            ResearchComparisonRequest(
                left=ResearchComparisonLeg(
                    label=normalized["portfolio_label"],
                    object_type="hypothetical_portfolio",
                    returns=analysis.perf,
                ),
                right=ResearchComparisonLeg(
                    label=normalized["benchmark_symbol"],
                    object_type="benchmark",
                    returns=analysis.benchmark_returns,
                ),
            )
        )
        output = self._hypothetical_portfolio_comparison_summary(
            normalized=normalized,
            analysis=analysis,
            comparison=comparison,
        )
        comparison_source = CopilotSourceRef(
            source_id="research.hypothetical_portfolio.operator_comparison",
            label="Hypothetical portfolio comparison",
            kind="analytics",
            provider=comparison.source_provider,
            origin=comparison.origin,
            description="Read-only Research Operator comparison of a temporary hypothetical portfolio against a benchmark.",
            retrieved_at=comparison.retrieved_at,
        )
        sources = [comparison_source]
        source_ids = [comparison_source.source_id]
        if normalized["include_risk_analysis"]:
            risk_output, risk_source = self._hypothetical_portfolio_risk_handoff(normalized)
            output["risk_handoff"] = risk_output
            output["warnings"] = dedupe_warnings(output.get("warnings", []), risk_output.get("warnings", []))
            if risk_source is not None:
                sources.append(risk_source)
                source_ids.append(risk_source.source_id)
        else:
            output["risk_handoff"] = {
                "status": "not_requested",
                "summary": "Optional read-only Risk handoff was not requested for this hypothetical comparison.",
                "warnings": [],
            }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_hypothetical_portfolio_comparison",
                summary=(
                    f"Compared {normalized['portfolio_label']} against {normalized['benchmark_symbol']} "
                    "as a read-only hypothetical research portfolio."
                ),
                arguments=normalized,
                source_ids=source_ids,
            ),
            sources=sources,
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

    def _tool_run_fundamentals_reverse_valuation(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        ticker = str(arguments.get("ticker") or "").strip().upper() or self._fundamentals_ticker_from_bundle(context)
        reverse = self.fundamentals_service.get_reverse_valuation(ticker)
        if reverse is None:
            raise ValueError(f"Fundamentals reverse valuation is unavailable for: {ticker}")
        source = CopilotSourceRef(
            source_id="fundamentals.reverse_valuation.analysis",
            label="Fundamentals reverse-valuation analysis",
            kind="analytics",
            provider=reverse.source_provider,
            origin=reverse.origin,
            description="Read-only reverse valuation run for market-implied expectations.",
            retrieved_at=reverse.retrieved_at,
        )
        output = {
            "ticker": reverse.company.ticker,
            "company_name": reverse.company.name,
            "current_price": reverse.current_price,
            "target_equity_value": reverse.target_equity_value,
            "target_enterprise_value": reverse.target_enterprise_value,
            "base_case": self._fundamentals_dcf_summary(reverse.base_case_summary),
            "scenario_gap_metrics": [
                {
                    "metric_id": metric.metric_id,
                    "label": metric.label,
                    "display_value": metric.display_value,
                    "value": metric.value,
                    "source_provider": metric.source_provider,
                    "origin": metric.origin,
                    "transformation_note": metric.transformation_note,
                }
                for metric in reverse.scenario_gap_metrics
            ],
            "drivers": [
                {
                    "driver_id": driver.driver_id,
                    "label": driver.label,
                    "implied_value": driver.implied_value,
                    "display_value": driver.display_value,
                    "base_value": driver.base_value,
                    "base_display_value": driver.base_display_value,
                    "gap_to_base": driver.gap_to_base,
                    "gap_display_value": driver.gap_display_value,
                    "success": driver.success,
                    "warnings": list(driver.warnings),
                }
                for driver in reverse.drivers
            ],
            "sensitivity": {
                "wacc_values": list(reverse.sensitivity_matrix.wacc_values) if reverse.sensitivity_matrix else [],
                "terminal_growth_values": list(reverse.sensitivity_matrix.terminal_growth_values) if reverse.sensitivity_matrix else [],
                "rows": [
                    [
                        {
                            "wacc_pct": cell.wacc_pct,
                            "terminal_growth_pct": cell.terminal_growth_pct,
                            "implied_revenue_growth_pct": cell.implied_revenue_growth_pct,
                            "implied_ebit_margin_pct": cell.implied_ebit_margin_pct,
                            "implied_fcf_cagr_pct": cell.implied_fcf_cagr_pct,
                        }
                        for cell in row
                    ]
                    for row in (reverse.sensitivity_matrix.rows if reverse.sensitivity_matrix else [])
                ],
            },
            "warnings": list(reverse.warnings),
            "source_provider": reverse.source_provider,
            "origin": reverse.origin,
            "transformation_note": reverse.transformation_note,
        }
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_fundamentals_reverse_valuation",
                summary=f"Ran read-only reverse valuation for {ticker}.",
                arguments={"ticker": ticker},
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

    def _tool_run_risk_contribution_analysis(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        if self.risk_service is None:
            raise ValueError("Risk service is unavailable to Copilot.")
        snapshot_payload = context.tool_state.get("snapshot")
        if not isinstance(snapshot_payload, dict):
            raise ValueError("Risk contribution analysis requires an active portfolio or research snapshot.")
        snapshot = self._portfolio_snapshot_from_payload(snapshot_payload)
        source_scope = str(arguments.get("source_scope") or context.summary_data.get("workspace_mode") or "portfolio").strip().lower()
        if source_scope not in {"portfolio", "research"}:
            source_scope = "portfolio"
        data_provider = self.research_provider if source_scope == "research" else self.portfolio_provider
        normalization_warnings: list[str] = []
        top_n = self._bounded_int(
            arguments.get("top_n"),
            default=10,
            minimum=1,
            maximum=25,
            field_name="top_n",
            warnings=normalization_warnings,
        )
        include_monte_carlo = arguments.get("include_monte_carlo")
        if include_monte_carlo is None:
            include_monte_carlo = True
        else:
            include_monte_carlo = bool(include_monte_carlo)
        payload = self.risk_service.compute(
            RiskComputeRequest(
                snapshot=snapshot,
                alpha=0.95,
                lookback_days=252,
                horizon_days=1,
                mc_horizon_days=10,
                mc_simulation_model="Gaussian",
                mc_num_simulations=2000,
                beta_window=126,
                benchmark_symbol="SPY",
                base_currency=snapshot.base_currency,
                include_monte_carlo=include_monte_carlo,
            ),
            data_provider=data_provider,
        )
        summary = self._risk_compute_summary(payload, scenario_label="risk_contribution")
        metrics = dict(summary.get("metrics") or {})
        output = {
            "method": (
                "Gamma historical risk contribution analysis using the active snapshot. "
                "This is read-only and does not rebalance, trade, or modify saved research state."
            ),
            "source_scope": source_scope,
            "top_n": top_n,
            "include_monte_carlo": include_monte_carlo,
            "metrics": metrics,
            "top_contributions": list(summary.get("top_contributions", []) or [])[:top_n],
            "excluded_assets": dict(summary.get("excluded_assets") or {}),
            "frontier_points": list(summary.get("frontier_points", []) or []),
            "warnings": dedupe_warnings(summary.get("warnings", []), normalization_warnings),
        }
        if not include_monte_carlo:
            output["monte_carlo"] = None
        else:
            output["monte_carlo"] = {
                "var": metrics.get("monte_carlo_var"),
                "cvar": metrics.get("monte_carlo_cvar"),
            }
        source = CopilotSourceRef(
            source_id="risk.contribution.analysis",
            label="Risk contribution analysis",
            kind="analytics",
            provider="gamma",
            origin="gamma.risk.compute",
            description="Read-only risk contribution computation run by the Research Operator.",
            retrieved_at=snapshot.timestamp,
        )
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_risk_contribution_analysis",
                summary=f"Ran read-only risk contribution analysis for the active {source_scope} snapshot.",
                arguments={
                    "source_scope": source_scope,
                    "top_n": top_n,
                    "include_monte_carlo": include_monte_carlo,
                },
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

    def _tool_run_risk_scenario_analysis(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        if self.risk_service is None:
            raise ValueError("Risk service is unavailable to Copilot.")
        snapshot_payload = context.tool_state.get("snapshot")
        if not isinstance(snapshot_payload, dict):
            raise ValueError("Risk scenario analysis requires an active portfolio or research snapshot.")
        snapshot = self._portfolio_snapshot_from_payload(snapshot_payload)
        source_scope = str(arguments.get("source_scope") or context.summary_data.get("workspace_mode") or "portfolio").strip().lower()
        if source_scope not in {"portfolio", "research"}:
            source_scope = "portfolio"
        data_provider = self.research_provider if source_scope == "research" else self.portfolio_provider
        scenario_label = str(arguments.get("scenario_label") or "baseline_risk").strip() or "baseline_risk"
        shock_spec, shock_warnings = self._normalize_risk_shock_arguments(
            snapshot,
            arguments,
            scenario_label=scenario_label,
        )
        payload = self.risk_service.compute(
            RiskComputeRequest(
                snapshot=snapshot,
                alpha=0.95,
                lookback_days=252,
                horizon_days=1,
                mc_horizon_days=10,
                mc_simulation_model="Gaussian",
                mc_num_simulations=2000,
                beta_window=126,
                benchmark_symbol="SPY",
                base_currency=snapshot.base_currency,
                include_monte_carlo=True,
            ),
            data_provider=data_provider,
        )
        result_summary = self._risk_compute_summary(
            payload,
            scenario_label=scenario_label,
            shock_spec=shock_spec,
            shock_warnings=shock_warnings,
        )
        source = CopilotSourceRef(
            source_id="risk.scenario.analysis",
            label="Risk scenario analysis",
            kind="analytics",
            provider="gamma",
            origin="gamma.risk.compute",
            description="Read-only risk computation run by the Research Operator.",
            retrieved_at=snapshot.timestamp,
        )
        return CopilotToolExecution(
            output=result_summary,
            trace=CopilotToolTrace(
                tool_name="run_risk_scenario_analysis",
                summary=f"Ran read-only risk scenario analysis for {scenario_label}.",
                arguments={
                    "scenario_label": scenario_label,
                    "source_scope": source_scope,
                    "scenario_type": shock_spec["scenario_type"],
                    "rate_shift_bps": shock_spec["rate_shift_bps"],
                    "equity_shock_pct": shock_spec["equity_shock_pct"],
                    "duration_proxy_years": shock_spec["duration_proxy_years"],
                    "symbol_shocks": list(shock_spec["symbol_shocks"]),
                },
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

    def _tool_run_options_realized_implied_comparison(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> CopilotToolExecution:
        normalized = self._normalize_options_realized_implied_arguments(arguments, context)
        surface, service_warnings, service_messages = self._options_surface_for_operator(normalized, context)
        output = self._options_realized_implied_summary(
            surface=surface,
            normalized=normalized,
            service_warnings=service_warnings,
            service_messages=service_messages,
        )
        source = CopilotSourceRef(
            source_id=f"iv.realized_implied.{self._safe_source_id(output.get('symbol') or normalized['symbol'])}",
            label="Options realized versus implied comparison",
            kind="analytics",
            provider=str(output.get("source_provider") or "gamma"),
            origin=str(output.get("origin") or "gamma.iv.surface"),
            description="Read-only Research Operator comparison of available historical-volatility fields against ATM implied volatility.",
            retrieved_at=(
                self._coerce_source_datetime(output.get("retrieved_at"))
                or self._coerce_source_datetime(output.get("timestamp"))
                or now_utc()
            ),
        )
        return CopilotToolExecution(
            output=output,
            trace=CopilotToolTrace(
                tool_name="run_options_realized_implied_comparison",
                summary=(
                    f"Compared available historical volatility against ATM implied volatility for "
                    f"{output.get('symbol') or normalized['symbol']} across {len(output.get('expiry_comparisons') or [])} expiry row(s)."
                ),
                arguments=normalized,
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
            "strategy_lab": (
                "get_strategy_lab_handoff_context",
                "run_strategy_lab_backtest",
            ),
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
                "run_options_realized_implied_comparison",
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
    def _portfolio_snapshot_from_payload(payload: dict[str, Any]) -> PortfolioSnapshot:
        timestamp = CopilotService._coerce_source_datetime(payload.get("timestamp")) or now_utc()
        positions = [
            PositionItem(
                symbol=str(row.get("symbol") or ""),
                sec_type=str(row.get("sec_type") or "STK"),
                currency=str(row.get("currency") or payload.get("base_currency") or "USD"),
                quantity=float(row.get("quantity") or 0.0),
                avg_cost=CopilotService._optional_float(row.get("avg_cost")),
                market_price=CopilotService._optional_float(row.get("market_price")),
                market_value=CopilotService._optional_float(row.get("market_value")),
                unrealized_pnl=CopilotService._optional_float(row.get("unrealized_pnl")),
                weight=CopilotService._optional_float(row.get("weight")),
                base_market_value=CopilotService._optional_float(row.get("base_market_value")),
                fx_rate=CopilotService._optional_float(row.get("fx_rate")),
                instrument_id=row.get("instrument_id"),
                display_symbol=row.get("display_symbol"),
                exchange=row.get("exchange"),
                primary_exchange=row.get("primary_exchange"),
                provider=row.get("provider"),
                provider_id=row.get("provider_id"),
            )
            for row in payload.get("positions", [])
            if isinstance(row, dict)
        ]
        return PortfolioSnapshot(
            timestamp=timestamp,
            base_currency=str(payload.get("base_currency") or "USD"),
            account_summary=dict(payload.get("account_summary") or {}),
            positions=positions,
            total_market_value=CopilotService._optional_float(payload.get("total_market_value")),
            total_cash=CopilotService._optional_float(payload.get("total_cash")),
            net_liquidation=CopilotService._optional_float(payload.get("net_liquidation")),
            day_pnl=CopilotService._optional_float(payload.get("day_pnl")),
            day_pnl_pct=CopilotService._optional_float(payload.get("day_pnl_pct")),
            day_pnl_source=payload.get("day_pnl_source"),
            warnings=[str(item) for item in payload.get("warnings", [])],
        )

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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

    @classmethod
    def _default_research_scope_analysis_arguments(
        cls,
        context: CopilotContextBundle,
    ) -> dict[str, Any] | None:
        result = context.tool_state.get("result")
        if not isinstance(result, dict):
            return None
        scope_type = result.get("scope_type") or "auto"
        if isinstance(scope_type, ResearchScopeType):
            scope_type = scope_type.value
        return {
            "scope_type": scope_type,
            "primary_symbol": result.get("primary_symbol"),
            "benchmark_symbol": result.get("benchmark_symbol") or "SPY",
            "lookback_days": 252,
            "synthetic_positions": cls._synthetic_positions_from_research_payload(result),
        }

    @classmethod
    def _normalize_research_scope_analysis_arguments(
        cls,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> dict[str, Any]:
        result = context.tool_state.get("result")
        result_payload = result if isinstance(result, dict) else {}
        warnings: list[str] = []
        synthetic_positions = cls._normalize_research_synthetic_positions(
            arguments.get("synthetic_positions"),
            warnings=warnings,
        )
        if not synthetic_positions:
            synthetic_positions = cls._synthetic_positions_from_research_payload(result_payload)

        raw_scope_value = arguments.get("scope_type") or result_payload.get("scope_type") or "auto"
        raw_scope_type = raw_scope_value.value if isinstance(raw_scope_value, ResearchScopeType) else str(raw_scope_value)
        raw_scope_type = raw_scope_type.strip().lower()
        if raw_scope_type.startswith("researchscopetype."):
            raw_scope_type = raw_scope_type.split(".", 1)[1]
        if raw_scope_type in {"", "auto", "none"}:
            raw_scope_type = "synthetic_portfolio" if synthetic_positions else "single_ticker"
        try:
            scope_type = ResearchScopeType(raw_scope_type)
        except ValueError as exc:
            raise ValueError(f"Unsupported research scope_type: {raw_scope_type}") from exc
        if scope_type == ResearchScopeType.NONE:
            raise ValueError("Research scope analysis requires a configured research scope.")

        primary_symbol = str(arguments.get("primary_symbol") or result_payload.get("primary_symbol") or "").strip().upper()
        if scope_type == ResearchScopeType.SINGLE_TICKER and not primary_symbol:
            raise ValueError("Single-ticker research scope analysis requires primary_symbol.")
        if scope_type == ResearchScopeType.SYNTHETIC_PORTFOLIO and not synthetic_positions:
            raise ValueError("Synthetic research scope analysis requires at least one synthetic position.")

        benchmark_symbol = str(arguments.get("benchmark_symbol") or result_payload.get("benchmark_symbol") or "SPY").strip().upper() or "SPY"
        lookback_days = cls._bounded_int(
            arguments.get("lookback_days"),
            default=252,
            minimum=20,
            maximum=MAX_RISK_LOOKBACK_DAYS,
            field_name="lookback_days",
            warnings=warnings,
        )
        return {
            "scope_type": scope_type,
            "primary_symbol": primary_symbol if scope_type == ResearchScopeType.SINGLE_TICKER else "",
            "benchmark_symbol": benchmark_symbol[:32],
            "lookback_days": lookback_days,
            "synthetic_positions": synthetic_positions if scope_type == ResearchScopeType.SYNTHETIC_PORTFOLIO else [],
            "warnings": warnings,
        }

    @classmethod
    def _normalize_research_synthetic_positions(
        cls,
        raw_positions: Any,
        *,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_positions, list):
            return []
        positions: list[dict[str, Any]] = []
        for item in raw_positions[:100]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            weight = cls._bounded_optional_float(
                item.get("weight"),
                minimum=0.0,
                maximum=100.0,
                field_name=f"synthetic_positions.{symbol}.weight",
                warnings=warnings,
            )
            if weight is None or weight <= 0:
                continue
            positions.append(
                {
                    "symbol": symbol,
                    "weight": weight,
                    "instrument_id": cls._optional_clean_string_preserve_case(item.get("instrument_id")),
                    "display_symbol": cls._optional_clean_string(item.get("display_symbol")),
                    "sec_type": cls._optional_clean_string(item.get("sec_type")),
                    "currency": cls._optional_clean_string(item.get("currency")),
                    "exchange": cls._optional_clean_string(item.get("exchange")),
                    "primary_exchange": cls._optional_clean_string(item.get("primary_exchange")),
                    "provider": cls._optional_clean_string_preserve_case(item.get("provider")),
                    "provider_id": cls._optional_clean_string_preserve_case(item.get("provider_id")),
                }
            )
        if len(raw_positions) > 100:
            warnings.append("Research scope synthetic positions were truncated to the first 100 entries.")
        weight_sum = sum(float(position["weight"]) for position in positions)
        if weight_sum > 0:
            positions = [
                {
                    **position,
                    "weight": float(position["weight"]) / weight_sum,
                }
                for position in positions
            ]
        return positions

    @classmethod
    def _synthetic_positions_from_research_payload(cls, result: dict[str, Any]) -> list[dict[str, Any]]:
        weights = result.get("weights")
        if isinstance(weights, list) and weights:
            return cls._normalize_research_synthetic_positions(weights, warnings=[])
        snapshot = result.get("snapshot")
        if not isinstance(snapshot, dict):
            return []
        positions = snapshot.get("positions")
        if not isinstance(positions, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in positions:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "symbol": item.get("symbol") or item.get("display_symbol"),
                    "weight": item.get("weight") or item.get("base_market_value") or item.get("market_value") or 0.0,
                    "instrument_id": item.get("instrument_id"),
                    "display_symbol": item.get("display_symbol"),
                    "sec_type": item.get("sec_type"),
                    "currency": item.get("currency"),
                    "exchange": item.get("exchange"),
                    "primary_exchange": item.get("primary_exchange"),
                    "provider": item.get("provider"),
                    "provider_id": item.get("provider_id"),
                }
            )
        return cls._normalize_research_synthetic_positions(rows, warnings=[])

    @staticmethod
    def _strategy_lab_active_result(
        context: CopilotContextBundle,
        requested_kind: Any,
    ) -> tuple[str, dict[str, Any]]:
        valid_kinds = ("imported_result", "composition", "compare_result")
        normalized_kind = str(requested_kind or "auto").strip()
        if normalized_kind in valid_kinds:
            result = context.tool_state.get(normalized_kind)
            if isinstance(result, dict):
                return normalized_kind, result
            raise ValueError(f"Strategy Lab context is missing `{normalized_kind}`.")
        for result_kind in ("composition", "imported_result", "compare_result"):
            result = context.tool_state.get(result_kind)
            if isinstance(result, dict):
                return result_kind, result
        raise ValueError("Strategy Lab context is missing an active imported, composition, or comparison result.")

    @classmethod
    def _normalize_hypothetical_portfolio_arguments(cls, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_legs = arguments.get("legs")
        if not isinstance(raw_legs, list):
            raw_legs = []
        warnings: list[str] = []
        legs: list[dict[str, Any]] = []
        for item in raw_legs[:25]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            weight = cls._bounded_optional_float(
                item.get("weight"),
                minimum=0.0,
                maximum=100.0,
                field_name=f"legs.{symbol}.weight",
                warnings=warnings,
            )
            if weight is None or weight <= 0:
                continue
            legs.append(
                {
                    "symbol": symbol,
                    "weight": weight,
                    "sec_type": cls._optional_clean_string(item.get("sec_type")),
                    "currency": cls._optional_clean_string(item.get("currency")),
                    "exchange": cls._optional_clean_string(item.get("exchange")),
                }
            )
        if len(raw_legs) > 25:
            warnings.append("Hypothetical portfolio legs were truncated to the first 25 entries.")
        if not legs:
            raise ValueError("Hypothetical portfolio comparison requires at least one positive-weight leg.")
        weight_sum = sum(float(item["weight"]) for item in legs)
        if weight_sum <= 0:
            raise ValueError("Hypothetical portfolio comparison requires positive total weight.")
        normalized_legs = [
            {
                **item,
                "weight": float(item["weight"]) / weight_sum,
            }
            for item in legs
        ]
        lookback_days = cls._bounded_int(
            arguments.get("lookback_days"),
            default=252,
            minimum=20,
            maximum=MAX_RISK_LOOKBACK_DAYS,
            field_name="lookback_days",
            warnings=warnings,
        )
        min_observations = cls._bounded_int(
            arguments.get("min_observations"),
            default=5,
            minimum=2,
            maximum=MAX_RISK_LOOKBACK_DAYS,
            field_name="min_observations",
            warnings=warnings,
        )
        include_risk_analysis = arguments.get("include_risk_analysis")
        include_risk_analysis = False if include_risk_analysis is None else bool(include_risk_analysis)
        benchmark_symbol = str(arguments.get("benchmark_symbol") or "SPY").strip().upper() or "SPY"
        portfolio_label = str(arguments.get("portfolio_label") or "").strip()
        if not portfolio_label:
            portfolio_label = "Hypothetical " + "/".join(item["symbol"] for item in normalized_legs[:4])
        return {
            "portfolio_label": portfolio_label[:128],
            "benchmark_symbol": benchmark_symbol[:24],
            "lookback_days": lookback_days,
            "min_observations": min_observations,
            "include_risk_analysis": include_risk_analysis,
            "legs": normalized_legs,
            "warnings": warnings,
        }

    @classmethod
    def _default_hypothetical_portfolio_arguments(
        cls,
        context: CopilotContextBundle,
    ) -> dict[str, Any] | None:
        prompt = str(context.summary_data.get("prompt") or context.tool_state.get("prompt") or "")
        tickers = [
            match.upper()
            for match in re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b", prompt)
            if match.lower() not in {"cpi", "fed", "oil", "rate", "rates", "var"}
        ]
        if not tickers:
            return None
        benchmark_symbol = "SPY"
        benchmark_match = re.search(
            r"\b(?:to|vs\.?|versus|against|relative to)\s+([A-Z]{1,5}(?:\.[A-Z])?)\b",
            prompt,
        )
        if benchmark_match:
            benchmark_symbol = benchmark_match.group(1).upper()
        elif len(tickers) > 2:
            benchmark_symbol = tickers[-1]
        leg_symbols = [ticker for ticker in tickers if ticker != benchmark_symbol]
        if not leg_symbols:
            return None
        weights = cls._extract_ratio_weights(prompt, len(leg_symbols))
        if weights is None:
            weights = [1.0 / len(leg_symbols)] * len(leg_symbols)
        include_risk_analysis = any(
            term in prompt.lower()
            for term in (
                "risk",
                "var",
                "volatility",
                "vol ",
                "drawdown",
                "contribution",
                "stress",
            )
        )
        return {
            "portfolio_label": "Hypothetical " + "/".join(leg_symbols[:4]),
            "benchmark_symbol": benchmark_symbol,
            "lookback_days": 252,
            "min_observations": 5,
            "include_risk_analysis": include_risk_analysis,
            "legs": [
                {
                    "symbol": symbol,
                    "weight": weights[index],
                    "sec_type": None,
                    "currency": None,
                    "exchange": None,
                }
                for index, symbol in enumerate(leg_symbols)
            ],
        }

    @staticmethod
    def _extract_ratio_weights(prompt: str, expected_count: int) -> list[float] | None:
        for match in re.finditer(r"\b\d{1,3}(?:\s*/\s*\d{1,3})+\b", prompt):
            parts = [float(item) for item in re.findall(r"\d{1,3}", match.group(0))]
            if len(parts) == expected_count and sum(parts) > 0:
                return [value / sum(parts) for value in parts]
        return None

    @staticmethod
    def _bounded_int(
        value: Any,
        *,
        default: int,
        minimum: int,
        maximum: int,
        field_name: str,
        warnings: list[str],
    ) -> int:
        if value is None:
            return default
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            warnings.append(f"Ignored non-integer {field_name}; using {default}.")
            return default
        if numeric < minimum:
            warnings.append(f"{field_name} was clipped to {minimum}.")
            return minimum
        if numeric > maximum:
            warnings.append(f"{field_name} was clipped to {maximum}.")
            return maximum
        return numeric

    @staticmethod
    def _optional_clean_string(value: Any) -> str | None:
        text = str(value or "").strip()
        return text.upper() if text else None

    @staticmethod
    def _optional_clean_string_preserve_case(value: Any) -> str | None:
        text = str(value or "").strip()
        return text if text else None

    @classmethod
    def _research_scope_analysis_operator_summary(
        cls,
        analysis: Any,
        *,
        normalized: dict[str, Any],
        constituent_limit: int = 12,
    ) -> dict[str, Any]:
        perf = analysis.perf
        benchmark = analysis.benchmark_returns
        metrics = cls._return_stream_metrics(perf, benchmark)
        weights = analysis.weights
        weight_values = [float(value) for value in weights.values] if not weights.empty else []
        hhi = sum(value * value for value in weight_values) if weight_values else None
        position_by_id = {
            position.resolved_instrument_id(): position
            for position in (analysis.snapshot.positions if analysis.snapshot is not None else [])
        }

        constituents: list[dict[str, Any]] = []
        ranked_weights = weights.abs().sort_values(ascending=False) if not weights.empty else weights
        for instrument_id, _abs_weight in ranked_weights.iloc[:constituent_limit].items():
            raw_weight = cls._series_get_float(weights, instrument_id)
            position = position_by_id.get(str(instrument_id))
            symbol = position.resolved_display_symbol() if position is not None else str(instrument_id)
            total_return = cls._series_get_float(analysis.constituent_total_returns, instrument_id)
            constituents.append(
                {
                    "symbol": symbol,
                    "instrument_id": str(instrument_id),
                    "weight": raw_weight,
                    "total_return": total_return,
                    "annual_vol": cls._series_get_float(analysis.constituent_annual_vol, instrument_id),
                    "max_drawdown": cls._series_get_float(analysis.constituent_max_drawdown, instrument_id),
                    "weighted_return": (raw_weight * total_return) if raw_weight is not None and total_return is not None else None,
                }
            )

        warnings = dedupe_warnings(analysis.warnings, normalized.get("warnings", []))
        return {
            "method": (
                "Gamma ResearchService scope analysis over normalized daily return history. "
                "This operator action is read-only and does not save, overwrite, rebalance, or trade any research object."
            ),
            "scope": {
                "scope_type": analysis.scope_type.value,
                "primary_symbol": analysis.primary_symbol,
                "benchmark_symbol": analysis.benchmark_symbol,
                "lookback_days": normalized["lookback_days"],
                "synthetic_position_count": len(normalized.get("synthetic_positions", [])),
            },
            "metrics": {
                **metrics,
                "observations_count": int(len(perf)),
            },
            "structure": {
                "total_weight": sum(weight_values) if weight_values else None,
                "top_weight": max(weight_values) if weight_values else None,
                "top5_weight": sum(sorted(weight_values, reverse=True)[:5]) if weight_values else None,
                "concentration_hhi": hhi,
                "effective_positions": (1.0 / hhi) if hhi and hhi > 0 else None,
                "aligned_symbol_count": int(len(weights)),
            },
            "coverage": {
                "available_symbols": list(analysis.available_symbols),
                "missing_symbols": list(analysis.missing_symbols),
                "benchmark_overlap_count": int(analysis.benchmark_overlap_count),
                "benchmark_available": not benchmark.empty,
            },
            "top_constituents": constituents,
            "provenance": {
                "source_provider": analysis.source_provider,
                "history_source_label": analysis.history_source_label,
                "freshness_label": analysis.freshness_label.value,
                "transformation_note": "ResearchService.analyze builds a scope snapshot, normalizes histories, computes weighted returns, and derives benchmark-relative diagnostics.",
            },
            "warnings": warnings,
        }

    @staticmethod
    def _return_stream_metrics(perf: Any, benchmark: Any) -> dict[str, Any]:
        if perf is None or perf.empty:
            return {
                "total_return": None,
                "annual_return": None,
                "annual_vol": None,
                "max_drawdown": None,
                "beta": None,
                "correlation": None,
            }
        clean = perf.dropna()
        if clean.empty:
            return {
                "total_return": None,
                "annual_return": None,
                "annual_vol": None,
                "max_drawdown": None,
                "beta": None,
                "correlation": None,
            }
        total_return = float((1.0 + clean).prod() - 1.0)
        annual_return = None
        if total_return > -1.0:
            annual_return = float((1.0 + total_return) ** (252.0 / max(len(clean), 1)) - 1.0)
        annual_vol = float(clean.std(ddof=1) * math.sqrt(252.0)) if len(clean) > 1 else None
        cumulative = (1.0 + clean).cumprod()
        drawdown = cumulative / cumulative.cummax() - 1.0
        max_dd = float(drawdown.min()) if not drawdown.empty else None
        beta = None
        correlation = None
        if benchmark is not None and not benchmark.empty:
            aligned = clean.align(benchmark.dropna(), join="inner")
            if len(aligned[0]) > 1:
                variance = float(aligned[1].var())
                if variance > 0:
                    beta = float(aligned[0].cov(aligned[1]) / variance)
                correlation_value = aligned[0].corr(aligned[1])
                if correlation_value == correlation_value:
                    correlation = float(correlation_value)
        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "annual_vol": annual_vol,
            "max_drawdown": max_dd,
            "beta": beta,
            "correlation": correlation,
        }

    @classmethod
    def _hypothetical_portfolio_comparison_summary(
        cls,
        *,
        normalized: dict[str, Any],
        analysis: Any,
        comparison: Any,
    ) -> dict[str, Any]:
        row = comparison.comparison
        warnings = dedupe_warnings(
            normalized.get("warnings", []),
            analysis.warnings,
            comparison.warnings,
            [
                "Hypothetical portfolio comparison is read-only research; Gamma does not rebalance or modify broker portfolios.",
            ],
        )
        if row.aligned_observation_count < int(normalized["min_observations"]):
            warnings = dedupe_warnings(
                warnings,
                [
                    (
                        f"Aligned observations ({row.aligned_observation_count}) are below the requested "
                        f"minimum ({normalized['min_observations']}); treat comparison metrics as thin-window diagnostics."
                    )
                ],
            )
        return {
            "portfolio_label": normalized["portfolio_label"],
            "benchmark_symbol": normalized["benchmark_symbol"],
            "lookback_days": normalized["lookback_days"],
            "min_observations": normalized["min_observations"],
            "legs": list(normalized["legs"]),
            "coverage": {
                "left_observation_count": row.left_observation_count,
                "right_observation_count": row.right_observation_count,
                "aligned_observation_count": row.aligned_observation_count,
                "overlap_start": row.overlap_start,
                "overlap_end": row.overlap_end,
                "missing_symbols": list(getattr(analysis, "missing_symbols", []) or []),
                "available_symbols": list(getattr(analysis, "available_symbols", []) or []),
                "benchmark_overlap_count": getattr(analysis, "benchmark_overlap_count", None),
            },
            "left": {
                "label": row.left.label,
                "object_type": row.left.object_type,
                "metrics": cls._metrics_to_dict(row.left.metrics),
            },
            "right": {
                "label": row.right.label,
                "object_type": row.right.object_type,
                "metrics": cls._metrics_to_dict(row.right.metrics),
            },
            "relative": {
                "relative_return": row.relative_return,
                "volatility_difference": row.volatility_difference,
                "max_drawdown_difference": row.max_drawdown_difference,
                "correlation": row.correlation,
                "beta": row.beta,
            },
            "provenance": {
                "source_provider": comparison.source_provider,
                "retrieved_at": comparison.retrieved_at,
                "origin": comparison.origin,
                "transformation_note": comparison.transformation_note,
                "freshness_label": comparison.freshness_label,
                "history_source_label": getattr(analysis, "history_source_label", None),
            },
            "warnings": warnings,
        }

    def _hypothetical_portfolio_risk_handoff(
        self,
        normalized: dict[str, Any],
    ) -> tuple[dict[str, Any], CopilotSourceRef | None]:
        if self.risk_service is None:
            return (
                {
                    "status": "skipped",
                    "summary": "Optional Risk handoff was skipped because RiskService is unavailable.",
                    "warnings": ["Risk handoff unavailable: RiskService is not configured."],
                },
                None,
            )
        if self.research_provider is None:
            return (
                {
                    "status": "skipped",
                    "summary": "Optional Risk handoff was skipped because the research data provider is unavailable.",
                    "warnings": ["Risk handoff unavailable: research data provider is not configured."],
                },
                None,
            )
        snapshot = self._hypothetical_portfolio_snapshot(normalized)
        try:
            payload = self.risk_service.compute(
                RiskComputeRequest(
                    snapshot=snapshot,
                    alpha=0.95,
                    lookback_days=int(normalized["lookback_days"]),
                    horizon_days=1,
                    mc_horizon_days=10,
                    mc_simulation_model="Gaussian",
                    mc_num_simulations=1000,
                    beta_window=126,
                    benchmark_symbol=str(normalized["benchmark_symbol"]),
                    base_currency=snapshot.base_currency,
                    include_monte_carlo=False,
                    recommended_min_obs=max(20, min(60, int(normalized["min_observations"]))),
                ),
                data_provider=self.research_provider,
            )
        except Exception as exc:
            return (
                {
                    "status": "failed",
                    "summary": f"Optional Risk handoff failed: {exc.__class__.__name__}.",
                    "warnings": [f"Risk handoff failed: {exc.__class__.__name__}: {exc}"],
                },
                None,
            )

        summary = self._risk_compute_summary(payload, scenario_label="hypothetical_portfolio_risk")
        warnings = dedupe_warnings(
            summary.get("warnings", []),
            [
                "Risk handoff used a temporary fixed-notional hypothetical snapshot; no broker portfolio or saved research object was modified.",
                "Monte Carlo diagnostics are disabled for the optional hypothetical Risk handoff to keep the operator run bounded.",
            ],
        )
        source = CopilotSourceRef(
            source_id="risk.hypothetical_portfolio.operator_handoff",
            label="Hypothetical portfolio Risk handoff",
            kind="analytics",
            provider="gamma",
            origin="gamma.risk.compute",
            description="Read-only Risk analytics computed from a temporary hypothetical portfolio snapshot.",
            retrieved_at=snapshot.timestamp,
        )
        return (
            {
                "status": "completed",
                "summary": "Computed read-only Risk analytics from the temporary hypothetical portfolio snapshot.",
                "snapshot": {
                    "notional_value": snapshot.net_liquidation,
                    "base_currency": snapshot.base_currency,
                    "position_count": len(snapshot.positions),
                },
                "metrics": summary.get("metrics", {}),
                "top_contributions": list(summary.get("top_contributions", []) or [])[:10],
                "excluded_assets": dict(summary.get("excluded_assets") or {}),
                "frontier_points": list(summary.get("frontier_points", []) or []),
                "warnings": warnings,
            },
            source,
        )

    @staticmethod
    def _hypothetical_portfolio_snapshot(normalized: dict[str, Any]) -> PortfolioSnapshot:
        notional_value = 1_000_000.0
        positions: list[PositionItem] = []
        for leg in list(normalized.get("legs") or []):
            weight = float(leg.get("weight") or 0.0)
            market_value = notional_value * weight
            market_price = 100.0
            positions.append(
                PositionItem(
                    symbol=str(leg.get("symbol") or "").strip().upper(),
                    sec_type=str(leg.get("sec_type") or "STK"),
                    currency=str(leg.get("currency") or "USD"),
                    quantity=market_value / market_price,
                    avg_cost=market_price,
                    market_price=market_price,
                    market_value=market_value,
                    unrealized_pnl=0.0,
                    weight=weight,
                    base_market_value=market_value,
                    fx_rate=1.0,
                    display_symbol=str(leg.get("symbol") or "").strip().upper(),
                    exchange=leg.get("exchange") or "SMART",
                    provider="gamma_hypothetical",
                    provider_id=str(leg.get("symbol") or "").strip().upper(),
                )
            )
        return PortfolioSnapshot(
            timestamp=now_utc(),
            base_currency="USD",
            account_summary={
                "source": "temporary_hypothetical_research_snapshot",
                "mutation_behavior": "read_only_ephemeral",
            },
            positions=positions,
            total_market_value=notional_value,
            total_cash=0.0,
            net_liquidation=notional_value,
            warnings=[
                "Temporary hypothetical Risk handoff snapshot; not a broker account, saved portfolio, or rebalance instruction."
            ],
        )

    @staticmethod
    def _metrics_to_dict(metrics: Any) -> dict[str, Any]:
        if hasattr(metrics, "__dict__"):
            return {
                key: value
                for key, value in metrics.__dict__.items()
                if value is not None
            }
        return {}

    @classmethod
    def _strategy_lab_operator_summary(
        cls,
        result_kind: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        warnings = dedupe_warnings(
            result.get("warnings", []),
            [
                "Strategy Lab operator actions are read-only research summaries; Gamma does not execute strategy code.",
                "Raw uploaded CSV rows are not persisted by default, so this action uses the active normalized Strategy Lab result.",
            ],
        )
        if result_kind == "compare_result":
            return cls._strategy_lab_compare_summary(result, warnings)

        returns_points = cls._list_or_empty(result.get("returns_points") or result.get("return_points"))
        benchmark_points = cls._list_or_empty(result.get("benchmark_points"))
        rolling_points = cls._list_or_empty(result.get("rolling_points"))
        monthly_returns = cls._list_or_empty(result.get("monthly_returns"))
        annual_returns = cls._list_or_empty(result.get("annual_returns"))
        output: dict[str, Any] = {
            "result_kind": result_kind,
            "name": result.get("name") or result.get("label") or "Strategy Lab result",
            "value_kind": result.get("value_kind"),
            "benchmark": {
                "column": result.get("benchmark_column"),
                "value_kind": result.get("benchmark_value_kind"),
                "points": len(benchmark_points),
                "available": bool(benchmark_points),
            },
            "metrics": cls._select_metric_fields(
                metrics,
                (
                    "total_return",
                    "annual_return",
                    "annualized_return",
                    "annual_volatility",
                    "annualized_volatility",
                    "sharpe_ratio",
                    "sortino_ratio",
                    "max_drawdown",
                    "max_drawdown_duration",
                    "observation_count",
                    "frequency",
                    "periods_per_year",
                    "benchmark_beta",
                    "benchmark_correlation",
                    "upside_capture",
                    "downside_capture",
                ),
            ),
            "coverage": {
                "return_points": len(returns_points),
                "benchmark_points": len(benchmark_points),
                "rolling_points": len(rolling_points),
                "monthly_periods": len(monthly_returns),
                "annual_periods": len(annual_returns),
            },
            "period_returns": {
                "latest_month": cls._last_period_return(monthly_returns),
                "latest_year": cls._last_period_return(annual_returns),
                "best_year": cls._best_period_return(annual_returns, highest=True),
                "worst_year": cls._best_period_return(annual_returns, highest=False),
            },
            "provenance": cls._strategy_lab_provenance(result),
            "warnings": warnings,
        }
        if isinstance(result.get("leg_contributions"), dict):
            output["leg_contributions"] = dict(result.get("leg_contributions") or {})
        if isinstance(result.get("lenses"), list):
            output["lens_count"] = len(result.get("lenses") or [])
        if isinstance(result.get("overlays"), list):
            output["overlay_count"] = len(result.get("overlays") or [])
        return output

    @classmethod
    def _strategy_lab_compare_summary(
        cls,
        result: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        comparison = result.get("comparison") if isinstance(result.get("comparison"), dict) else result
        left = comparison.get("left") if isinstance(comparison.get("left"), dict) else {}
        right = comparison.get("right") if isinstance(comparison.get("right"), dict) else {}
        return {
            "result_kind": "compare_result",
            "name": result.get("name") or "Strategy Lab comparison",
            "left": cls._strategy_lab_comparison_leg_summary(left),
            "right": cls._strategy_lab_comparison_leg_summary(right),
            "relative": cls._select_metric_fields(
                comparison,
                (
                    "relative_return",
                    "volatility_gap",
                    "max_drawdown_gap",
                    "rolling_correlation",
                    "rolling_beta",
                    "overlap_count",
                ),
            ),
            "provenance": cls._strategy_lab_provenance(result),
            "warnings": warnings,
        }

    @classmethod
    def _strategy_lab_comparison_leg_summary(cls, leg: dict[str, Any]) -> dict[str, Any]:
        metrics = leg.get("metrics") if isinstance(leg.get("metrics"), dict) else {}
        return {
            "label": leg.get("label"),
            "object_type": leg.get("object_type"),
            "metrics": cls._select_metric_fields(
                metrics,
                (
                    "total_return",
                    "annual_return",
                    "annual_volatility",
                    "sharpe_ratio",
                    "max_drawdown",
                    "observation_count",
                    "frequency",
                ),
            ),
        }

    @staticmethod
    def _strategy_lab_provenance(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_provider": result.get("source_provider"),
            "retrieved_at": result.get("retrieved_at"),
            "origin": result.get("origin"),
            "transformation_note": result.get("transformation_note"),
            "freshness_label": result.get("freshness_label"),
        }

    @staticmethod
    def _select_metric_fields(metrics: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {
            key: metrics.get(key)
            for key in keys
            if key in metrics and metrics.get(key) is not None
        }

    @staticmethod
    def _list_or_empty(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @classmethod
    def _last_period_return(cls, periods: list[Any]) -> dict[str, Any] | None:
        rows = [item for item in periods if isinstance(item, dict)]
        return rows[-1] if rows else None

    @classmethod
    def _best_period_return(cls, periods: list[Any], *, highest: bool) -> dict[str, Any] | None:
        rows = [
            item
            for item in periods
            if isinstance(item, dict) and cls._optional_float(item.get("value")) is not None
        ]
        if not rows:
            return None
        return max(rows, key=lambda item: cls._optional_float(item.get("value")) or 0.0) if highest else min(
            rows,
            key=lambda item: cls._optional_float(item.get("value")) or 0.0,
        )

    @staticmethod
    def _risk_result_from_bundle(context: CopilotContextBundle) -> dict[str, Any]:
        risk = context.tool_state.get("result")
        if not isinstance(risk, dict):
            raise ValueError("Risk context is missing the active risk result.")
        return risk

    @staticmethod
    def _risk_compute_summary(
        payload: Any,
        *,
        scenario_label: str,
        shock_spec: dict[str, Any] | None = None,
        shock_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        results = payload.results
        shock_spec = shock_spec or CopilotService._default_risk_shock_spec()
        shock_proxy = CopilotService._risk_shock_proxy_impact(payload.snapshot, shock_spec)
        warnings = dedupe_warnings(list(results.warnings), shock_warnings or [], shock_proxy.get("warnings", []))
        top_contributions = []
        contribution_symbols = list(payload.returns_df.columns)
        if not payload.contributions.empty:
            contribution_symbols.sort(
                key=lambda symbol: abs(float(payload.contributions.get(symbol, 0.0) or 0.0)),
                reverse=True,
            )
        for symbol in contribution_symbols[:10]:
            top_contributions.append(
                {
                    "symbol": str(symbol),
                    "weight": CopilotService._series_get_float(payload.weights, symbol),
                    "variance_contribution_pct": CopilotService._series_get_float(payload.contributions, symbol),
                    "marginal_contribution_to_risk": CopilotService._series_get_float(
                        payload.marginal_contribution_to_risk,
                        symbol,
                    ),
                    "component_var": CopilotService._series_get_float(payload.component_var, symbol),
                }
            )
        return {
            "scenario_label": scenario_label,
            "scenario_type": shock_spec["scenario_type"],
            "method": (
                "Current snapshot risk baseline plus a transparent bounded shock proxy. "
                "VaR, contribution, beta, and frontier metrics come from Gamma's existing historical risk engine; "
                "shock_proxy is a read-only position-level estimate, not a full curve or factor repricing model."
            ),
            "shock_parameters": {
                "scenario_type": shock_spec["scenario_type"],
                "rate_shift_bps": shock_spec["rate_shift_bps"],
                "equity_shock_pct": shock_spec["equity_shock_pct"],
                "duration_proxy_years": shock_spec["duration_proxy_years"],
                "symbol_shocks": list(shock_spec["symbol_shocks"]),
                "bounds": {
                    "rate_shift_bps": [-300.0, 300.0],
                    "equity_shock_pct": [-0.8, 0.8],
                    "duration_proxy_years": [0.0, 30.0],
                    "symbol_price_shock_pct": [-0.95, 5.0],
                },
            },
            "shock_proxy": shock_proxy,
            "metrics": {
                "portfolio_value": results.portfolio_value,
                "historical_var": results.historical_var,
                "historical_cvar": results.historical_cvar,
                "parametric_var": results.parametric_var,
                "daily_vol": results.daily_vol,
                "annual_vol": results.annual_vol,
                "max_drawdown": results.max_drawdown,
                "beta": results.beta,
                "correlation": results.correlation,
                "risk_coverage_ratio": results.risk_coverage_ratio,
                "covered_risk_basis_value": results.covered_risk_basis_value,
                "risk_basis_value": results.risk_basis_value,
                "monte_carlo_var": results.monte_carlo_var,
                "monte_carlo_cvar": results.monte_carlo_cvar,
                "aligned_obs_count": results.aligned_obs_count,
                "benchmark_overlap_count": results.benchmark_overlap_count,
                "concentration_hhi": results.concentration_hhi,
                "top5_weight": results.top5_weight,
                "effective_bets": results.effective_bets,
            },
            "top_contributions": top_contributions,
            "excluded_assets": dict(results.excluded_assets),
            "frontier_points": [
                {
                    "label": point.label,
                    "kind": point.kind,
                    "annual_return": point.annual_return,
                    "annual_vol": point.annual_vol,
                    "sharpe": point.sharpe,
                }
                for point in payload.frontier_points[:8]
            ],
            "warnings": warnings,
        }

    @staticmethod
    def _default_risk_shock_spec() -> dict[str, Any]:
        return {
            "scenario_type": "baseline",
            "rate_shift_bps": None,
            "equity_shock_pct": None,
            "duration_proxy_years": None,
            "symbol_shocks": [],
        }

    @classmethod
    def _normalize_risk_shock_arguments(
        cls,
        snapshot: PortfolioSnapshot,
        arguments: dict[str, Any],
        *,
        scenario_label: str,
    ) -> tuple[dict[str, Any], list[str]]:
        del snapshot
        warnings: list[str] = []
        allowed = {"baseline", "rate_shock", "equity_drawdown", "commodity_shock", "custom"}
        scenario_type = str(arguments.get("scenario_type") or "").strip().lower()
        if not scenario_type:
            label = scenario_label.lower()
            if "rate" in label or "yield" in label:
                scenario_type = "rate_shock"
            elif "drawdown" in label or "equity" in label:
                scenario_type = "equity_drawdown"
            else:
                scenario_type = "baseline"
        if scenario_type not in allowed:
            warnings.append(f"Unsupported scenario_type `{scenario_type}` was treated as custom.")
            scenario_type = "custom"

        rate_shift_bps = cls._bounded_optional_float(
            arguments.get("rate_shift_bps"),
            minimum=-300.0,
            maximum=300.0,
            field_name="rate_shift_bps",
            warnings=warnings,
        )
        if scenario_type == "rate_shock" and rate_shift_bps is None:
            rate_shift_bps = 100.0

        equity_shock_pct = cls._bounded_optional_float(
            arguments.get("equity_shock_pct"),
            minimum=-0.8,
            maximum=0.8,
            field_name="equity_shock_pct",
            warnings=warnings,
        )
        if scenario_type == "equity_drawdown" and equity_shock_pct is None:
            equity_shock_pct = -0.1

        duration_proxy_years = cls._bounded_optional_float(
            arguments.get("duration_proxy_years"),
            minimum=0.0,
            maximum=30.0,
            field_name="duration_proxy_years",
            warnings=warnings,
        )

        symbol_shocks = []
        raw_symbol_shocks = arguments.get("symbol_shocks")
        if isinstance(raw_symbol_shocks, list):
            for item in raw_symbol_shocks[:25]:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                price_shock_pct = cls._bounded_optional_float(
                    item.get("price_shock_pct"),
                    minimum=-0.95,
                    maximum=5.0,
                    field_name=f"symbol_shocks.{symbol}.price_shock_pct",
                    warnings=warnings,
                )
                if price_shock_pct is None:
                    continue
                symbol_shocks.append({"symbol": symbol, "price_shock_pct": price_shock_pct})
            if len(raw_symbol_shocks) > 25:
                warnings.append("symbol_shocks was truncated to the first 25 entries.")

        return (
            {
                "scenario_type": scenario_type,
                "rate_shift_bps": rate_shift_bps,
                "equity_shock_pct": equity_shock_pct,
                "duration_proxy_years": duration_proxy_years,
                "symbol_shocks": symbol_shocks,
            },
            warnings,
        )

    @staticmethod
    def _bounded_optional_float(
        value: Any,
        *,
        minimum: float,
        maximum: float,
        field_name: str,
        warnings: list[str],
    ) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            warnings.append(f"Ignored non-numeric {field_name}.")
            return None
        if numeric < minimum:
            warnings.append(f"{field_name} was clipped to {minimum}.")
            return minimum
        if numeric > maximum:
            warnings.append(f"{field_name} was clipped to {maximum}.")
            return maximum
        return numeric

    @classmethod
    def _risk_shock_proxy_impact(
        cls,
        snapshot: PortfolioSnapshot,
        shock_spec: dict[str, Any],
    ) -> dict[str, Any]:
        scenario_type = str(shock_spec.get("scenario_type") or "baseline")
        explicit_shocks = {
            str(item.get("symbol") or "").strip().upper(): cls._optional_float(item.get("price_shock_pct"))
            for item in shock_spec.get("symbol_shocks", [])
            if isinstance(item, dict)
        }
        position_impacts: list[dict[str, Any]] = []
        warnings: list[str] = []
        total_pnl = 0.0
        shocked_count = 0
        for position in snapshot.positions:
            value = cls._position_base_value(position)
            if value is None:
                continue
            shock_pct, basis = cls._position_shock_pct(position, shock_spec, explicit_shocks)
            if shock_pct is None:
                continue
            pnl = value * shock_pct
            total_pnl += pnl
            shocked_count += 1
            position_impacts.append(
                {
                    "symbol": position.resolved_display_symbol(),
                    "instrument_id": position.resolved_instrument_id(),
                    "sec_type": position.sec_type,
                    "base_market_value": value,
                    "shock_pct": shock_pct,
                    "estimated_pnl": pnl,
                    "basis": basis,
                }
            )

        portfolio_value = (
            snapshot.net_liquidation
            or snapshot.total_market_value
            or sum(abs(cls._position_base_value(position) or 0.0) for position in snapshot.positions)
            or None
        )
        if scenario_type != "baseline" and shocked_count == 0:
            warnings.append("No positions matched the typed shock proxy; baseline risk metrics are still returned.")
        position_impacts.sort(key=lambda item: abs(float(item["estimated_pnl"])), reverse=True)
        return {
            "applied": shocked_count > 0,
            "method": cls._risk_shock_proxy_method(shock_spec),
            "portfolio_value": portfolio_value,
            "estimated_pnl": total_pnl if shocked_count else None,
            "estimated_return_pct": (total_pnl / portfolio_value) if shocked_count and portfolio_value else None,
            "shocked_position_count": shocked_count,
            "position_impacts": position_impacts[:12],
            "warnings": warnings,
        }

    @staticmethod
    def _position_base_value(position: PositionItem) -> float | None:
        value = position.base_market_value
        if value is None:
            value = position.market_value
        return CopilotService._optional_float(value)

    @classmethod
    def _position_shock_pct(
        cls,
        position: PositionItem,
        shock_spec: dict[str, Any],
        explicit_shocks: dict[str, float | None],
    ) -> tuple[float | None, str | None]:
        symbols = {
            str(position.symbol or "").strip().upper(),
            str(position.display_symbol or "").strip().upper(),
            position.resolved_symbol().upper(),
            position.resolved_display_symbol().upper(),
        }
        for symbol in symbols:
            if symbol in explicit_shocks and explicit_shocks[symbol] is not None:
                return explicit_shocks[symbol], "explicit_symbol_shock"

        scenario_type = str(shock_spec.get("scenario_type") or "baseline")
        if scenario_type == "rate_shock":
            rate_shift_bps = cls._optional_float(shock_spec.get("rate_shift_bps"))
            if rate_shift_bps is None:
                return None, None
            duration = cls._duration_proxy_for_position(position, shock_spec.get("duration_proxy_years"))
            if duration is not None:
                return -duration * (rate_shift_bps / 10000.0), "duration_proxy"
            equity_shock_pct = cls._optional_float(shock_spec.get("equity_shock_pct"))
            if equity_shock_pct is not None and cls._is_equity_like_position(position):
                return equity_shock_pct, "optional_equity_proxy"
            return None, None

        if scenario_type == "equity_drawdown":
            equity_shock_pct = cls._optional_float(shock_spec.get("equity_shock_pct"))
            if equity_shock_pct is not None and cls._is_equity_like_position(position):
                return equity_shock_pct, "equity_drawdown_proxy"
        return None, None

    @staticmethod
    def _duration_proxy_for_position(position: PositionItem, fallback: Any) -> float | None:
        symbol = position.resolved_display_symbol().upper()
        duration_by_symbol = {
            "SHY": 1.9,
            "VGSH": 1.9,
            "IEF": 7.0,
            "VGIT": 5.2,
            "TLT": 16.0,
            "VGLT": 15.0,
            "AGG": 6.0,
            "BND": 6.0,
            "LQD": 8.0,
            "HYG": 3.5,
            "JNK": 3.5,
            "TBT": -16.0,
            "TMV": -24.0,
            "UBT": 16.0,
        }
        if symbol in duration_by_symbol:
            return duration_by_symbol[symbol]
        normalized_sec_type = str(position.sec_type or "").strip().upper()
        fallback_value = CopilotService._optional_float(fallback)
        if normalized_sec_type in {"BOND", "BILL", "NOTE", "FIXED_INCOME"} and fallback_value is not None:
            return fallback_value
        return None

    @staticmethod
    def _is_equity_like_position(position: PositionItem) -> bool:
        return str(position.sec_type or "").strip().upper() in {"STK", "ETF", "FUND"}

    @staticmethod
    def _risk_shock_proxy_method(shock_spec: dict[str, Any]) -> str:
        scenario_type = str(shock_spec.get("scenario_type") or "baseline")
        if scenario_type == "rate_shock":
            return "Parallel-rate proxy: price shock ~= -duration_proxy_years * rate_shift_decimal; explicit symbol shocks override inferred duration proxies."
        if scenario_type == "equity_drawdown":
            return "Equity drawdown proxy: applies bounded equity_shock_pct to equity-like positions; explicit symbol shocks override inferred proxies."
        if scenario_type in {"commodity_shock", "custom"}:
            return "Custom proxy: applies only explicit per-symbol shocks."
        return "Baseline scenario: no proxy shock was applied."

    @staticmethod
    def _series_get_float(series: Any, key: str) -> float | None:
        try:
            value = series.get(key)
        except Exception:
            return None
        return CopilotService._optional_float(value)

    @staticmethod
    def _iv_surface_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        surface = context.tool_state.get("surface")
        return surface if isinstance(surface, dict) else None

    @staticmethod
    def _iv_session_from_bundle(context: CopilotContextBundle) -> dict[str, Any] | None:
        session = context.tool_state.get("session")
        return session if isinstance(session, dict) else None

    @staticmethod
    def _iv_target_symbol_from_state(
        state: dict[str, Any],
        surface: dict[str, Any] | None,
        session: dict[str, Any] | None,
    ) -> str:
        active_surface = resolve_iv_surface(surface, session)
        candidates = [
            state.get("target_symbol"),
            (active_surface or {}).get("symbol") if isinstance(active_surface, dict) else None,
            (session or {}).get("active_symbol"),
            (surface or {}).get("symbol"),
        ]
        for candidate in candidates:
            symbol = str(candidate or "").strip().upper()
            if symbol:
                return symbol
        return "SPY"

    def _normalize_options_realized_implied_arguments(
        self,
        arguments: dict[str, Any],
        context: CopilotContextBundle,
    ) -> dict[str, Any]:
        surface = self._iv_surface_from_bundle(context)
        session = self._iv_session_from_bundle(context)
        target_symbol = str(context.summary_data.get("target_symbol") or context.tool_state.get("target_symbol") or "")
        symbol = str(arguments.get("symbol") or target_symbol or "").strip().upper()
        if not symbol:
            symbol = self._iv_target_symbol_from_state({}, surface, session)
        max_expiries = int(self._optional_float(arguments.get("max_expiries")) or 6)
        max_expiries = max(1, min(8, max_expiries))
        depth_preset = str(arguments.get("depth_preset") or "compact").strip().lower().replace("-", "_")
        if depth_preset not in {"compact", "standard", "deep", "front_deep", "max"}:
            depth_preset = "compact"
        market_data_mode = str(arguments.get("market_data_mode") or "").strip().lower() or None
        if self.iv_service is not None:
            market_data_mode = self.iv_service.normalize_market_data_mode(market_data_mode or self.iv_service.market_data_mode)
        elif market_data_mode not in {"live", "delayed", "auto"}:
            market_data_mode = None
        return {
            "symbol": symbol or "SPY",
            "max_expiries": max_expiries,
            "depth_preset": depth_preset,
            "market_data_mode": market_data_mode,
        }

    def _options_surface_for_operator(
        self,
        normalized: dict[str, Any],
        context: CopilotContextBundle,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        requested_symbol = str(normalized.get("symbol") or "").strip().upper()
        surface = self._iv_surface_from_bundle(context)
        session = self._iv_session_from_bundle(context)
        active_surface = resolve_iv_surface(surface, session)
        if isinstance(active_surface, dict) and active_surface.get("snapshot_available", True):
            active_symbol = str(active_surface.get("symbol") or "").strip().upper()
            if not requested_symbol or active_symbol == requested_symbol:
                return active_surface, [], []

        if self.iv_service is None:
            if isinstance(active_surface, dict):
                return active_surface, [], []
            raise ValueError("Options IV service is unavailable and no active IV surface is loaded.")

        result = self.iv_service.get_surface(
            IVSurfaceRequest(
                symbol=requested_symbol or "SPY",
                market_data_mode=str(normalized.get("market_data_mode") or self.iv_service.market_data_mode),
                wait_seconds=2.5,
                depth_preset=str(normalized.get("depth_preset") or "compact"),
            )
        )
        if result.snapshot is None:
            return {
                "symbol": requested_symbol or "SPY",
                "timestamp": now_utc(),
                "retrieved_at": now_utc(),
                "snapshot_available": False,
                "warnings": list(result.warnings),
                "messages": list(result.messages),
                "source_provider": "iv_service",
                "origin": "gamma.iv.surface",
                "freshness_label": "unavailable",
            }, list(result.warnings), list(result.messages)
        snapshot = result.snapshot
        iv_grid = snapshot.iv_grid.tolist() if hasattr(snapshot.iv_grid, "tolist") else list(snapshot.iv_grid)
        return {
            "symbol": snapshot.symbol,
            "timestamp": snapshot.timestamp,
            "retrieved_at": now_utc(),
            "snapshot_available": True,
            "spot": snapshot.spot,
            "expiries": list(snapshot.expiries),
            "strikes": [float(strike) for strike in snapshot.strikes],
            "iv_grid": iv_grid,
            "delayed": snapshot.delayed,
            "points": snapshot.points,
            "warnings": list(result.warnings),
            "messages": list(result.messages),
            "source_provider": snapshot.source_provider,
            "origin": snapshot.origin,
            "transformation_note": snapshot.transformation_note,
            "freshness_label": snapshot.freshness_label,
            "contracts": [asdict(item) for item in snapshot.contracts],
            "pairs": [asdict(item) for item in snapshot.pairs],
            "collection": asdict(snapshot.collection) if snapshot.collection is not None else None,
            "quality": asdict(snapshot.quality) if snapshot.quality is not None else None,
            "expiry_analytics": [asdict(item) for item in snapshot.expiry_analytics],
            "pricing_assumptions": asdict(snapshot.pricing_assumptions) if snapshot.pricing_assumptions is not None else None,
        }, list(result.warnings), list(result.messages)

    def _options_realized_implied_summary(
        self,
        *,
        surface: dict[str, Any],
        normalized: dict[str, Any],
        service_warnings: list[str],
        service_messages: list[str],
    ) -> dict[str, Any]:
        warnings = dedupe_warnings(
            surface.get("warnings", []) if isinstance(surface.get("warnings"), list) else [],
            service_warnings,
            service_messages,
        )
        if not surface.get("snapshot_available", True):
            warnings = dedupe_warnings(warnings, ["No IV surface snapshot was available for realized-versus-implied comparison."])
            return {
                "symbol": surface.get("symbol") or normalized["symbol"],
                "timestamp": self._iso_or_value(surface.get("timestamp")),
                "retrieved_at": self._iso_or_value(surface.get("retrieved_at")),
                "snapshot_available": False,
                "requested": dict(normalized),
                "expiry_comparisons": [],
                "summary": {
                    "expiry_count": 0,
                    "ok_count": 0,
                    "missing_historical_volatility_count": 0,
                    "missing_implied_volatility_count": 0,
                },
                "quality": surface.get("quality"),
                "warnings": warnings,
                "source_provider": surface.get("source_provider"),
                "origin": surface.get("origin"),
                "transformation_note": surface.get("transformation_note"),
                "freshness_label": surface.get("freshness_label"),
            }

        expiry_rows = [row for row in surface.get("expiry_analytics", []) or [] if isinstance(row, dict)]
        contracts = [row for row in surface.get("contracts", []) or [] if isinstance(row, dict)]
        rows: list[dict[str, Any]] = []
        for row in expiry_rows[: int(normalized["max_expiries"])]:
            expiry = str(row.get("expiry") or "")
            implied_vol = self._first_optional_float(
                row.get("atm_blended_implied_volatility"),
                row.get("atm_call_implied_volatility"),
                row.get("atm_put_implied_volatility"),
            )
            historical_vol = self._expiry_historical_volatility(
                expiry=expiry,
                atm_strike=self._optional_float(row.get("atm_strike")),
                contracts=contracts,
            )
            comparison_status = "ok"
            if implied_vol is None and historical_vol is None:
                comparison_status = "insufficient_data"
            elif implied_vol is None:
                comparison_status = "missing_implied_volatility"
            elif historical_vol is None:
                comparison_status = "missing_historical_volatility"
            rows.append(
                {
                    "expiry": expiry,
                    "days_to_expiry": row.get("days_to_expiry"),
                    "atm_strike": row.get("atm_strike"),
                    "atm_implied_volatility": implied_vol,
                    "historical_volatility": historical_vol,
                    "volatility_premium": implied_vol - historical_vol if implied_vol is not None and historical_vol is not None else None,
                    "implied_to_historical_ratio": implied_vol / historical_vol if implied_vol is not None and historical_vol not in {None, 0.0} else None,
                    "implied_move_pct": row.get("implied_move_pct"),
                    "atm_straddle_midpoint": row.get("atm_straddle_midpoint"),
                    "pair_count": row.get("pair_count"),
                    "pair_count_with_both_sides": row.get("pair_count_with_both_sides"),
                    "comparison_status": comparison_status,
                }
            )

        if not rows:
            warnings = dedupe_warnings(warnings, ["IV surface contained no expiry analytics rows for comparison."])
        if any(row["comparison_status"] == "missing_historical_volatility" for row in rows):
            warnings = dedupe_warnings(
                warnings,
                ["One or more expiry rows lack provider historical-volatility fields; Gamma did not infer realized volatility from price history."],
            )
        quality = surface.get("quality") if isinstance(surface.get("quality"), dict) else {}
        collection = surface.get("collection") if isinstance(surface.get("collection"), dict) else {}
        return {
            "symbol": surface.get("symbol") or normalized["symbol"],
            "timestamp": self._iso_or_value(surface.get("timestamp")),
            "retrieved_at": self._iso_or_value(surface.get("retrieved_at")),
            "snapshot_available": True,
            "requested": dict(normalized),
            "spot": self._optional_float(surface.get("spot")),
            "delayed": surface.get("delayed"),
            "surface_points": surface.get("points"),
            "expiry_comparisons": rows,
            "summary": {
                "expiry_count": len(rows),
                "ok_count": sum(1 for row in rows if row["comparison_status"] == "ok"),
                "missing_historical_volatility_count": sum(1 for row in rows if row["comparison_status"] == "missing_historical_volatility"),
                "missing_implied_volatility_count": sum(1 for row in rows if row["comparison_status"] == "missing_implied_volatility"),
                "insufficient_data_count": sum(1 for row in rows if row["comparison_status"] == "insufficient_data"),
                "average_volatility_premium": self._average_optional(
                    row.get("volatility_premium") for row in rows if row.get("volatility_premium") is not None
                ),
            },
            "quality": {
                "expected_surface_cells": quality.get("expected_surface_cells"),
                "observed_surface_cells": quality.get("observed_surface_cells"),
                "interpolated_surface_cells": quality.get("interpolated_surface_cells"),
                "interpolation_ratio": quality.get("interpolation_ratio"),
                "pairs_with_both_sides": quality.get("pairs_with_both_sides"),
                "contracts_with_provider_greeks": quality.get("contracts_with_provider_greeks"),
                "contracts_with_derived_greeks": quality.get("contracts_with_derived_greeks"),
            },
            "collection": {
                "depth_preset": collection.get("depth_preset"),
                "market_data_mode": collection.get("market_data_mode"),
                "selected_expiry_count": collection.get("selected_expiry_count"),
                "selected_strike_count": collection.get("selected_strike_count"),
                "subscribed_contract_count": collection.get("subscribed_contract_count"),
                "market_data_line_utilization": collection.get("market_data_line_utilization"),
                "contract_selection_note": collection.get("contract_selection_note"),
            },
            "warnings": warnings,
            "source_provider": surface.get("source_provider"),
            "origin": surface.get("origin"),
            "transformation_note": surface.get("transformation_note"),
            "freshness_label": surface.get("freshness_label"),
        }

    @classmethod
    def _expiry_historical_volatility(
        cls,
        *,
        expiry: str,
        atm_strike: float | None,
        contracts: list[dict[str, Any]],
    ) -> float | None:
        expiry_contracts = [row for row in contracts if str(row.get("expiry") or "") == expiry]
        if not expiry_contracts:
            return None
        if atm_strike is not None:
            expiry_contracts = sorted(
                expiry_contracts,
                key=lambda row: abs((cls._optional_float(row.get("strike")) or atm_strike) - atm_strike),
            )
            nearest_distance = abs((cls._optional_float(expiry_contracts[0].get("strike")) or atm_strike) - atm_strike)
            expiry_contracts = [
                row
                for row in expiry_contracts
                if abs((cls._optional_float(row.get("strike")) or atm_strike) - atm_strike) <= max(nearest_distance, 0.01)
            ]
        values = [cls._optional_float(row.get("historical_volatility")) for row in expiry_contracts]
        clean_values = [value for value in values if value is not None and value > 0]
        return cls._average_optional(clean_values)

    @staticmethod
    def _first_optional_float(*values: Any) -> float | None:
        for value in values:
            normalized = CopilotService._optional_float(value)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _average_optional(values: Any) -> float | None:
        clean = [float(value) for value in values if value is not None]
        return sum(clean) / len(clean) if clean else None

    @staticmethod
    def _iso_or_value(value: Any) -> Any:
        return value.isoformat() if hasattr(value, "isoformat") else value

    @classmethod
    def _compact_operator_output(cls, output: Any) -> Any:
        if isinstance(output, list):
            return {"kind": "list", "count": len(output), "items": output[:5]}
        if not isinstance(output, dict):
            return {"kind": type(output).__name__, "value": output}
        summary: dict[str, Any] = {
            "kind": "dict",
            "keys": list(output.keys())[:12],
        }
        for key in (
            "symbol",
            "ticker",
            "scenario_label",
            "scenario_type",
            "scope_type",
            "result_kind",
            "portfolio_label",
            "benchmark_symbol",
            "snapshot_available",
            "source_provider",
            "origin",
            "freshness_label",
        ):
            if key in output:
                summary[key] = output.get(key)
        nested_summary = output.get("summary")
        if isinstance(nested_summary, dict):
            summary["summary"] = {
                key: value
                for key, value in nested_summary.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
        metrics = output.get("metrics")
        if isinstance(metrics, dict):
            summary["metrics"] = {
                key: value
                for key, value in metrics.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
        for list_key in (
            "warnings",
            "expiry_comparisons",
            "top_contributions",
            "relative_metrics",
            "coverage",
            "constituents",
        ):
            value = output.get(list_key)
            if isinstance(value, list):
                summary[f"{list_key}_count"] = len(value)
            elif isinstance(value, dict):
                summary[list_key] = {
                    key: item
                    for key, item in value.items()
                    if isinstance(item, (str, int, float, bool)) or item is None
                }
        return summary

    @classmethod
    def _bounded_operator_outputs(
        cls,
        outputs: dict[str, Any],
        output_summaries: dict[str, Any],
        *,
        max_bytes: int = MAX_OPERATOR_FINAL_OUTPUT_BYTES,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        estimated_bytes = cls._json_size_bytes(outputs)
        retention = {
            "mode": "full",
            "reason": None,
            "output_count": len(outputs),
            "estimated_full_output_bytes": estimated_bytes,
            "max_full_output_bytes": max_bytes,
        }
        if estimated_bytes <= max_bytes:
            return outputs, retention
        compact_outputs = {
            step_id: {
                "truncated": True,
                "retention_reason": "full_output_exceeded_payload_budget",
                "output_summary": output_summaries.get(step_id) or cls._compact_operator_output(output),
            }
            for step_id, output in outputs.items()
        }
        retention["mode"] = "compact"
        retention["reason"] = "full_output_exceeded_payload_budget"
        return compact_outputs, retention

    @staticmethod
    def _json_size_bytes(value: Any) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=True, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            return len(str(value).encode("utf-8"))

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
