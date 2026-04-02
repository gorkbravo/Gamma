from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

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
            "macro": self._build_macro_context,
            "prediction_markets": self._build_prediction_market_context,
        }
        self._tools = {
            definition.name: definition
            for definition in (
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
            )
        }

    def generate_research_card(self, request: CopilotResearchCardRequest) -> CopilotResearchCardResult:
        builder = self._context_builders.get(request.domain)
        if builder is None:
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=getattr(self.provider, "provider_name", "unknown"),
                message=f"Unsupported copilot domain: {request.domain}",
            )
        try:
            context = builder(request)
        except ValueError as exc:
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=request.context.current_tab,
                status="error",
                provider=getattr(self.provider, "provider_name", "unknown"),
                message=str(exc),
            )

        tool_specs = [
            tool.to_openai_spec()
            for tool in self._tools.values()
            if request.domain in tool.domains
        ]
        return self.provider.generate_research_card(
            request=request,
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
