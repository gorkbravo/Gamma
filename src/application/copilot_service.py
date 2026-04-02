from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from src.application.copilot_context_helpers import (
    dedupe_warnings,
    resolve_iv_surface,
    summarize_iv_state,
    summarize_portfolio_history,
    summarize_portfolio_performance,
    summarize_portfolio_snapshot,
    summarize_research_result,
    summarize_risk_result,
)
from src.application.macro_service import MacroSnapshotRequest, MacroService
from src.application.prediction_market_service import PredictionMarketService
from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolExecution,
    CopilotToolTrace,
    MacroCopilotContext,
)
from src.models.macro import MacroMetricRecord, MacroSeriesHistory
from src.models.prediction_markets import PredictionProbabilityPoint
from src.services.copilot_provider import CopilotProvider


@dataclass(frozen=True)
class _CopilotToolDefinition:
    name: str
    description: str
    domains: tuple[str, ...]
    parameters_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], CopilotContextBundle], CopilotToolExecution]

    def to_openai_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
            "strict": True,
        }


class CopilotService:
    def __init__(
        self,
        *,
        macro_service: MacroService,
        prediction_market_service: PredictionMarketService,
        provider: CopilotProvider,
    ) -> None:
        self.macro_service = macro_service
        self.prediction_market_service = prediction_market_service
        self.provider = provider
        self._context_builders = {
            "portfolio": self._build_portfolio_context,
            "research": self._build_research_context,
            "macro": self._build_macro_context,
            "prediction_markets": self._build_prediction_market_context,
            "risk": self._build_risk_context,
            "iv": self._build_iv_context,
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
                    domains=("research",),
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
                    domains=("research",),
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
                    description="Return a read-only IV surface and ATM term-structure summary for the active Gamma IV context.",
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
                    description="Return a read-only session and market-data-mode summary for the active Gamma IV context.",
                    domains=("iv",),
                    parameters_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    handler=self._tool_get_iv_session_status,
                ),
            )
        }

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
        return self.provider.generate_research_card(
            request=normalized_request,
            context=context,
            tool_specs=tool_specs,
            execute_tool=self._execute_tool,
        )

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
            raise ValueError("IV copilot requires a loaded IV surface.")
        summary = summarize_iv_state(surface, session)
        if summary is None:
            raise ValueError("IV copilot requires a loaded IV surface.")
        warnings = dedupe_warnings(summary.get("warnings", []))
        sources = [
            CopilotSourceRef(
                source_id="iv.surface",
                label="IV surface snapshot",
                kind="workspace",
                provider="gamma",
                origin="gamma.iv.surface",
                description="Loaded IV surface payload from Gamma.",
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
                    description="Current IV session state from Gamma.",
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
        snapshot = self.macro_service.get_snapshot(snapshot_request)
        divergences = self.macro_service.get_divergences(snapshot_request)
        events = self.macro_service.get_events(region=macro.region, force_refresh=False)
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
            label="IV surface drilldown",
            kind="workspace",
            provider="gamma",
            origin="gamma.iv.surface",
            description="Expanded IV surface and ATM term-structure context.",
            retrieved_at=(active_surface or {}).get("timestamp"),
        )
        return CopilotToolExecution(
            output=summarize_iv_state(surface, session) or {},
            trace=CopilotToolTrace(
                tool_name="get_iv_surface_context",
                summary="Expanded the active IV context into surface, front-slice, and term-structure summaries.",
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
            label="IV session drilldown",
            kind="status",
            provider="gamma",
            origin="gamma.iv.session",
            description="Expanded IV session state and market-data-mode context.",
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
                summary="Expanded the active IV session state and market-data-mode context.",
                arguments={},
                source_ids=[source.source_id],
            ),
            sources=[source],
        )

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
    def _prediction_market_id_from_bundle(context: CopilotContextBundle) -> str:
        market_id = str(context.summary_data.get("market_id") or "").strip()
        if not market_id:
            raise ValueError("Prediction market context is missing the selected market id.")
        return market_id

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
