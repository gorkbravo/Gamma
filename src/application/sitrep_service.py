from __future__ import annotations

"""Backend-owned SITREP situation-report contract.

SITREP started as a frontend composition over six separate endpoint loads.
This service owns that composition server-side so the cross-domain payload has
one contract: section defaults live here, sections load concurrently the same
way the frontend's parallel requests did, and a failing section degrades into
an explicit warning instead of failing the whole report.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from src.application.commodities_service import CommoditiesService, CommodityWorkspaceRequest
from src.application.macro_service import MacroService, MacroSnapshotRequest
from src.application.news_service import NewsService
from src.application.prediction_market_service import (
    PredictionMarketScreenerRequest,
    PredictionMarketService,
)
from src.application.research_service import ResearchService
from src.models.commodities import CommodityWorkspaceResult
from src.models.macro import MacroSnapshotPayload
from src.models.news import NewsEventFeed
from src.models.prediction_markets import PredictionMarketScreenerResult
from src.models.research_overview import ResearchOverviewRequest, ResearchOverviewResult
from src.utils.time import now_utc

SITREP_SECTIONS = (
    "equities",
    "indices",
    "macro",
    "commodities",
    "prediction_markets",
    "news",
)

_EQUITIES_UNIVERSE_ID = "broad_us_market"
_INDICES_UNIVERSE_ID = "global_indices"
_OVERVIEW_TIMEFRAME = "DoD"
_OVERVIEW_BENCHMARK = "SPY"
_OVERVIEW_PROVIDER_POLICY = "sitrep"
_MACRO_REGION = "US"
_MACRO_TIMEFRAME = "3M"
_MACRO_THEME = "all"
_PREDICTION_STATUS = "open"
_PREDICTION_SORT_BY = "research_rank"
_PREDICTION_LIMIT = 12
_NEWS_LIMIT = 25


@dataclass
class SitrepWorkspaceRequest:
    sections: tuple[str, ...] = SITREP_SECTIONS
    force_refresh: bool = False


@dataclass
class SitrepWorkspaceResult:
    equities_overview: ResearchOverviewResult | None
    indices_overview: ResearchOverviewResult | None
    macro_snapshot: MacroSnapshotPayload | None
    commodities: CommodityWorkspaceResult | None
    prediction_markets: PredictionMarketScreenerResult | None
    news: NewsEventFeed | None
    sections: tuple[str, ...]
    section_warnings: list[str] = field(default_factory=list)
    source_provider: str = "gamma_sitrep"
    retrieved_at: datetime = field(default_factory=now_utc)
    origin: str = "sitrep_service.workspace"
    transformation_note: str | None = (
        "Composed from Research Overview, Macro Snapshot, Commodities Overview, "
        "Prediction Markets screener, and News feed payloads."
    )


class SitrepService:
    """Composes the cross-domain SITREP payload from existing domain services."""

    def __init__(
        self,
        *,
        research_service: ResearchService,
        macro_service: MacroService,
        commodities_service: CommoditiesService,
        prediction_market_service: PredictionMarketService,
        news_service: NewsService,
    ) -> None:
        self.research_service = research_service
        self.macro_service = macro_service
        self.commodities_service = commodities_service
        self.prediction_market_service = prediction_market_service
        self.news_service = news_service

    def get_workspace(self, request: SitrepWorkspaceRequest | None = None) -> SitrepWorkspaceResult:
        normalized = request or SitrepWorkspaceRequest()
        sections = _normalize_sections(normalized.sections)
        force_refresh = bool(normalized.force_refresh)

        loaders = {
            "equities": lambda: self._load_overview(_EQUITIES_UNIVERSE_ID, force_refresh),
            "indices": lambda: self._load_overview(_INDICES_UNIVERSE_ID, force_refresh),
            "macro": lambda: self._load_macro(force_refresh),
            "commodities": lambda: self._load_commodities(force_refresh),
            "prediction_markets": lambda: self._load_prediction_markets(force_refresh),
            "news": lambda: self._load_news(force_refresh),
        }

        results: dict[str, object | None] = {section: None for section in SITREP_SECTIONS}
        warnings: list[str] = []
        requested = [section for section in SITREP_SECTIONS if section in sections]

        # Sections load concurrently; before this contract existed the frontend
        # issued the same calls as parallel HTTP requests, so per-service
        # concurrency characteristics are unchanged.
        with ThreadPoolExecutor(max_workers=max(len(requested), 1)) as executor:
            futures = {section: executor.submit(loaders[section]) for section in requested}
            for section, future in futures.items():
                try:
                    results[section] = future.result()
                except Exception as exc:  # noqa: BLE001 - a failing section must degrade, not 500
                    warnings.append(f"SITREP section '{section}' failed to load: {exc}")

        return SitrepWorkspaceResult(
            equities_overview=results["equities"],  # type: ignore[arg-type]
            indices_overview=results["indices"],  # type: ignore[arg-type]
            macro_snapshot=results["macro"],  # type: ignore[arg-type]
            commodities=results["commodities"],  # type: ignore[arg-type]
            prediction_markets=results["prediction_markets"],  # type: ignore[arg-type]
            news=results["news"],  # type: ignore[arg-type]
            sections=tuple(requested),
            section_warnings=warnings,
            retrieved_at=now_utc(),
        )

    def _load_overview(self, universe_id: str, force_refresh: bool) -> ResearchOverviewResult:
        return self.research_service.overview(
            ResearchOverviewRequest(
                universe_id=universe_id,
                timeframe=_OVERVIEW_TIMEFRAME,
                benchmark_symbol=_OVERVIEW_BENCHMARK,
                provider_policy=_OVERVIEW_PROVIDER_POLICY,
                force_refresh=force_refresh,
            )
        )

    def _load_macro(self, force_refresh: bool) -> MacroSnapshotPayload:
        return self.macro_service.get_snapshot(
            MacroSnapshotRequest(
                region=_MACRO_REGION,
                timeframe=_MACRO_TIMEFRAME,
                theme=_MACRO_THEME,
                force_refresh=force_refresh,
            )
        )

    def _load_commodities(self, force_refresh: bool) -> CommodityWorkspaceResult:
        return self.commodities_service.get_workspace(
            CommodityWorkspaceRequest(mode="overview", force_refresh=force_refresh)
        )

    def _load_prediction_markets(self, force_refresh: bool) -> PredictionMarketScreenerResult:
        return self.prediction_market_service.screener(
            PredictionMarketScreenerRequest(
                status=_PREDICTION_STATUS,
                sort_by=_PREDICTION_SORT_BY,
                limit=_PREDICTION_LIMIT,
                force_refresh=force_refresh,
            )
        )

    def _load_news(self, force_refresh: bool) -> NewsEventFeed:
        return self.news_service.latest(limit=_NEWS_LIMIT, force_refresh=force_refresh)


def _normalize_sections(sections: tuple[str, ...] | list[str] | None) -> set[str]:
    if not sections:
        return set(SITREP_SECTIONS)
    normalized = {str(section).strip().lower() for section in sections if str(section).strip()}
    known = normalized & set(SITREP_SECTIONS)
    return known or set(SITREP_SECTIONS)
