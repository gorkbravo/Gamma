from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from src.models.prediction_markets import (
    CalibrationSummary,
    PredictionBasketSummary,
    PredictionComparisonLeg,
    PredictionHistoryFetch,
    PredictionHistoryStats,
    PredictionHistoryWindow,
    PredictionMarketComparison,
    PredictionMarketFreshness,
    PredictionMarketRecord,
    PredictionMarketScreenerResult,
    PredictionOutcomeSeries,
    PredictionPairAnalytics,
    PredictionProbabilityHistory,
    PredictionSpreadPoint,
    PredictionVenueStatus,
    RelatedMarketRecord,
    WalletSummary,
)
from src.services.prediction_market_adapters import PredictionMarketAdapter
from src.utils.time import ensure_utc, now_utc

ALLOWED_RESEARCH_CATEGORIES = ("Politics", "Finance", "Geopolitics", "Crypto", "Economy", "Tech/AI")
EXACT_CATEGORY_ALIASES = {
    "politics": "Politics",
    "political": "Politics",
    "election": "Politics",
    "elections": "Politics",
    "government": "Politics",
    "policy": "Politics",
    "finance": "Finance",
    "financial": "Finance",
    "business": "Finance",
    "markets": "Finance",
    "economy": "Economy",
    "economics": "Economy",
    "economic": "Economy",
    "macro": "Economy",
    "crypto": "Crypto",
    "cryptocurrency": "Crypto",
    "blockchain": "Crypto",
    "geopolitics": "Geopolitics",
    "geopolitical": "Geopolitics",
    "world": "Geopolitics",
    "international": "Geopolitics",
    "global affairs": "Geopolitics",
    "tech": "Tech/AI",
    "technology": "Tech/AI",
    "science and technology": "Tech/AI",
    "ai": "Tech/AI",
    "artificial intelligence": "Tech/AI",
}
CATEGORY_EXCLUSION_KEYWORDS = (
    "nba",
    "wnba",
    "nfl",
    "mlb",
    "nhl",
    "fifa",
    "ufc",
    "mma",
    "boxing",
    "tennis",
    "golf",
    "soccer",
    "football",
    "basketball",
    "baseball",
    "hockey",
    "world cup",
    "stanley cup",
    "super bowl",
    "finals",
    "champion",
    "playoff",
)
CATEGORY_KEYWORD_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("Crypto", ("bitcoin", "btc", "ethereum", "eth", "solana", "dogecoin", "doge", "crypto", "cryptocurrency")),
    ("Geopolitics", ("ukraine", "russia", "china", "taiwan", "nato", "israel", "iran", "gaza", "ceasefire", "sanction", "tariff", "military", "war", "diplomacy")),
    ("Politics", ("election", "vote", "voter", "ballot", "president", "prime minister", "governor", "senate", "congress", "parliament", "coalition")),
    ("Economy", ("inflation", "cpi", "gdp", "recession", "unemployment", "fomc", "fed", "rates", "rate cut", "rate hike", "macro")),
    ("Finance", ("stock", "stocks", "equity", "equities", "earnings", "nasdaq", "s&p", "dow", "bond", "bonds", "yield", "treasury", "etf")),
    # Tech/AI is matched last so markets that already canonicalize to an
    # existing research category (e.g. "China AI chip sanctions" -> Geopolitics)
    # keep their current label; this only catches markets that previously fell
    # through to category None.
    (
        "Tech/AI",
        (
            "ai",
            "artificial intelligence",
            "agi",
            "ai model",
            "openai",
            "anthropic",
            "chatgpt",
            "gpt",
            "grok",
            "llm",
            "machine learning",
            "deepmind",
            "nvidia",
            "semiconductor",
            "semiconductors",
            "robotics",
            "self driving",
            "spacex",
            "starship",
            "tech",
            "technology",
        ),
    ),
]
QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "before",
    "by",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "will",
    "with",
}
DELAYED_RETRIEVAL_SECONDS = 6 * 60 * 60
STALE_RETRIEVAL_SECONDS = 24 * 60 * 60
RELATED_RELATIONSHIP_PRIORITY = {
    "cross_venue_analog": 0,
    "adjacent_threshold": 1,
    "conditional_consistency": 2,
    "same_event": 3,
    "topic_similarity": 4,
    "weak_venue_link": 5,
}
# Same-event siblings need at least this much lexical overlap to be presented as
# semantically related; below it they are venue-metadata artifacts (a venue can
# group unrelated markets under one event/series id).
RELATED_SAME_EVENT_MIN_SIMILARITY = 0.25
HISTORY_RANGE_DAYS: dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 182,
    "1y": 365,
}
HISTORY_RANGE_KEYS = (*HISTORY_RANGE_DAYS, "max")
RESOLUTION_CHOICES_MINUTES = (1, 5, 15, 60, 360, 1440)
# Auto resolution aims for a chart that is dense enough to read without asking a
# venue for hundreds of thousands of bars.
AUTO_RESOLUTION_TARGET_POINTS = 900
MAX_COMPARISON_LEGS = 6
MAX_OUTCOME_SERIES = 8
MIN_PAIR_OVERLAP_POINTS = 12
MAX_SPREAD_SERIES_POINTS = 600
MAX_ALIGNED_GRID_POINTS = 2000
DEFAULT_COMPARISON_STEP_MINUTES = 60


@dataclass(frozen=True)
class PredictionMarketScreenerRequest:
    query: str = ""
    venues: list[str] = field(default_factory=list)
    status: str = "open"
    force_refresh: bool = False
    category: str | None = None
    min_volume: float | None = None
    min_liquidity: float | None = None
    min_open_interest: float | None = None
    min_probability: float | None = None
    max_probability: float | None = None
    max_days_to_resolution: float | None = None
    min_repricing_abs: float | None = None
    sort_by: str = "research_rank"
    limit: int = 40


class PredictionMarketService:
    def __init__(self, adapters: dict[str, PredictionMarketAdapter]) -> None:
        self.adapters = adapters

    def screener(self, request: PredictionMarketScreenerRequest) -> PredictionMarketScreenerResult:
        venues = request.venues or sorted(self.adapters)
        fetch_limit = self._screener_fetch_limit(request.limit)
        ranked_rows: list[PredictionMarketRecord] = []
        venue_statuses: list[PredictionVenueStatus] = []
        warnings: list[str] = []

        for venue in venues:
            adapter = self.adapters.get(venue)
            if adapter is None:
                venue_statuses.append(
                    PredictionVenueStatus(
                        venue=venue,
                        status="unavailable",
                        message="No adapter is configured for this venue.",
                        total_markets=0,
                        matched_markets=0,
                        visible_markets=0,
                        stale_markets=0,
                        broken_markets=0,
                    )
                )
                warnings.append(f"{venue} is not configured in the current runtime.")
                continue

            try:
                adapter_rows = self._canonicalize_rows(
                    adapter.list_markets(
                        status=request.status,
                        limit=fetch_limit,
                        force_refresh=request.force_refresh,
                        query=request.query,
                        category=request.category,
                    )
                )
            except Exception as exc:
                venue_statuses.append(
                    PredictionVenueStatus(
                        venue=venue,
                        status="error",
                        message=f"Venue request failed: {exc}",
                        total_markets=0,
                        matched_markets=0,
                        visible_markets=0,
                        stale_markets=0,
                        broken_markets=0,
                    )
                )
                warnings.append(f"{venue} request failed: {exc}")
                continue

            annotated_rows = [self._annotate_market_freshness(row) for row in adapter_rows]
            research_rows = [row for row in annotated_rows if self._is_research_relevant_market(row)]
            matched_rows = [row for row in research_rows if self._matches_screener(row, request)]
            visible_rows = [row for row in matched_rows if self._should_show_in_screener(row, request)]

            venue_statuses.append(
                self._build_venue_status(
                    venue=venue,
                    request=request,
                    all_rows=annotated_rows,
                    research_rows=research_rows,
                    matched_rows=matched_rows,
                    visible_rows=visible_rows,
                )
            )
            ranked_rows.extend(self._annotate_research_rank(row, request) for row in visible_rows)

        ranked_rows.sort(key=lambda row: self._sort_key(row, request.sort_by))
        return PredictionMarketScreenerResult(
            markets=ranked_rows[: request.limit],
            venues=venue_statuses,
            warnings=warnings,
        )

    def get_market_detail(self, market_id: str) -> PredictionMarketRecord | None:
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return None
        provider_market_id = self._provider_market_id(market_id)
        market = adapter.get_market(provider_market_id)
        if market is None:
            return None

        detail = self._canonicalize_market(market)
        history_points = []
        history_error: str | None = None
        try:
            history_points = adapter.get_history(detail)
        except Exception as exc:
            history_error = str(exc)
        return self._annotate_market_freshness(detail, history_points=history_points, history_error=history_error)

    def get_probability_history(self, market_id: str):
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return []
        provider_market_id = self._provider_market_id(market_id)
        market = adapter.get_market(provider_market_id)
        if market is None:
            return []
        return adapter.get_history(self._canonicalize_market(market))

    def get_history_series(
        self,
        market_id: str,
        *,
        range_key: str = "max",
        resolution_minutes: int | None = None,
        outcome_id: str | None = None,
    ) -> PredictionProbabilityHistory | None:
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return None
        provider_market_id = self._provider_market_id(market_id)
        market = adapter.get_market(provider_market_id)
        if market is None:
            return None
        detail = self._canonicalize_market(market)
        return self._build_history_series(
            adapter,
            detail,
            range_key=range_key,
            resolution_minutes=resolution_minutes,
            outcome_id=outcome_id,
        )

    def get_outcome_series(
        self,
        market_id: str,
        *,
        range_key: str = "max",
        resolution_minutes: int | None = None,
        limit: int = MAX_OUTCOME_SERIES,
    ) -> list[PredictionOutcomeSeries]:
        """Probability history for each tradable outcome of a single market.

        Binary markets return one series. Multi-outcome markets return one
        series per outcome that exposes its own provider token, which is what
        makes an outcome ladder chartable instead of YES-only.
        """
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return []
        provider_market_id = self._provider_market_id(market_id)
        market = adapter.get_market(provider_market_id)
        if market is None:
            return []
        detail = self._canonicalize_market(market)

        series: list[PredictionOutcomeSeries] = []
        for outcome in detail.outcomes[: max(limit, 1)]:
            if not outcome.token_id:
                series.append(
                    PredictionOutcomeSeries(
                        outcome_id=outcome.outcome_id,
                        label=outcome.label,
                        probability=outcome.probability,
                        token_id=None,
                        warnings=[
                            f"{detail.venue} does not expose a separate history token for '{outcome.label}'.",
                        ],
                    )
                )
                continue
            history = self._build_history_series(
                adapter,
                detail,
                range_key=range_key,
                resolution_minutes=resolution_minutes,
                outcome_id=outcome.outcome_id,
            )
            series.append(
                PredictionOutcomeSeries(
                    outcome_id=outcome.outcome_id,
                    label=outcome.label,
                    probability=outcome.probability,
                    token_id=outcome.token_id,
                    points=list(history.points) if history else [],
                    warnings=list(history.warnings) if history else [],
                )
            )
        return series

    def compare_markets(
        self,
        market_ids: list[str],
        *,
        range_key: str = "max",
        resolution_minutes: int | None = None,
    ) -> PredictionMarketComparison:
        """Align several contracts on one timeline and describe their spreads.

        This is read-only research context. A spread between two venues is not
        an executable arbitrage: sizing, fees, settlement rules, and resolution
        criteria are not modeled here.
        """
        current_time = ensure_utc(now_utc())
        unique_ids: list[str] = []
        for market_id in market_ids:
            if market_id not in unique_ids:
                unique_ids.append(market_id)

        warnings: list[str] = []
        if len(unique_ids) != len(market_ids):
            warnings.append("Duplicate contracts were requested once each.")
        unique_ids = unique_ids[:MAX_COMPARISON_LEGS]
        if len(market_ids) > MAX_COMPARISON_LEGS:
            warnings.append(
                f"Comparison is capped at {MAX_COMPARISON_LEGS} contracts; extra selections were dropped.",
            )

        legs: list[PredictionComparisonLeg] = []
        window_start: datetime | None = None
        window_end: datetime | None = None
        effective_resolution: int | None = None

        for market_id in unique_ids:
            adapter = self._resolve_adapter(market_id)
            if adapter is None:
                warnings.append(f"No adapter is configured for {market_id}.")
                continue
            market = adapter.get_market(self._provider_market_id(market_id))
            if market is None:
                warnings.append(f"{market_id} could not be loaded from its venue.")
                continue
            detail = self._canonicalize_market(market)
            history = self._build_history_series(
                adapter,
                detail,
                range_key=range_key,
                resolution_minutes=resolution_minutes,
            )
            if history is None:
                warnings.append(f"{market_id} returned no probability history.")
                continue
            legs.append(
                PredictionComparisonLeg(
                    market_id=detail.market_id,
                    venue=detail.venue,
                    title=detail.title,
                    outcome_label=detail.probability_label,
                    current_probability=detail.current_probability,
                    status=detail.status,
                    end_time=detail.end_time,
                    event_id=detail.event_id,
                    event_title=detail.event_title,
                    points=list(history.points),
                    stats=history.stats,
                    coverage_start=history.coverage_start,
                    coverage_end=history.coverage_end,
                    warnings=list(history.warnings),
                    source_provider=history.source_provider,
                    origin=history.origin,
                )
            )
            window_start = _min_datetime(window_start, history.window_start)
            window_end = _max_datetime(window_end, history.window_end)
            if history.effective_resolution_minutes is not None:
                effective_resolution = max(effective_resolution or 0, history.effective_resolution_minutes)

        pairs: list[PredictionPairAnalytics] = []
        for left_index in range(len(legs)):
            for right_index in range(left_index + 1, len(legs)):
                pairs.append(
                    self._compare_pair(
                        legs[left_index],
                        legs[right_index],
                        resolution_minutes=effective_resolution or DEFAULT_COMPARISON_STEP_MINUTES,
                    )
                )

        if len(legs) < 2:
            warnings.append("At least two loadable contracts are needed for spread and correlation analytics.")

        return PredictionMarketComparison(
            requested_range=range_key,
            effective_resolution_minutes=effective_resolution,
            window_start=window_start,
            window_end=window_end,
            legs=legs,
            pairs=pairs,
            basket=self._build_basket_summary(legs),
            warnings=warnings,
            retrieved_at=current_time,
            transformation_note=(
                "Series are aligned onto a shared grid by carrying the last observed probability forward. "
                "Correlation is computed on probability changes, not levels. Spreads are research context, "
                "not executable prices."
            ),
        )

    def get_wallet_summary(self, market_id: str) -> WalletSummary | None:
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return None
        provider_market_id = self._provider_market_id(market_id)
        market = adapter.get_market(provider_market_id)
        if market is None:
            return None
        return adapter.get_wallet_summary(self._canonicalize_market(market))

    def get_related_markets(self, market_id: str, *, limit: int = 8) -> list[RelatedMarketRecord]:
        detail = self.get_market_detail(market_id)
        if detail is None:
            return []
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return []

        related_rows: list[tuple[tuple[int, float, float, str], RelatedMarketRecord]] = []
        seen: set[str] = set()

        for sibling in adapter.list_event_markets(detail, limit=max(limit * 2, 8)):
            candidate = self._annotate_market_freshness(self._canonicalize_market(sibling))
            if candidate.market_id in seen:
                continue
            # Same-event siblings inherit the opened market's research relevance:
            # venue event endpoints often omit category/tag metadata, and the viewed
            # market already passed the screener gate. Deliberately excluded topics
            # (sportsbook-style markets) are still dropped, and the similarity gate
            # below demotes semantically unrelated venue artifacts.
            if self._is_excluded_topic_market(candidate):
                continue
            relationship, note, similarity = self._describe_related_market(detail, candidate, same_event=True)
            seen.add(candidate.market_id)
            related_rows.append(
                (
                    self._related_sort_key(relationship, similarity, candidate),
                    RelatedMarketRecord(
                        market_id=candidate.market_id,
                        venue=candidate.venue,
                        title=candidate.title,
                        probability=candidate.current_probability,
                        price_gap=_price_gap(detail.current_probability, candidate.current_probability),
                        relationship=relationship,
                        note=note,
                        source_provider=candidate.source_provider,
                        retrieved_at=candidate.retrieved_at,
                        origin=f"prediction_market_service.{relationship}",
                        transformation_note="Related-market scoring combines event linkage, lexical overlap, threshold extraction, and resolution-date proximity.",
                    ),
                )
            )

        candidate_venues = [venue for venue in self.adapters if venue != detail.venue]
        for venue in candidate_venues:
            candidate_adapter = self.adapters[venue]
            candidate_rows = self._canonicalize_rows(
                candidate_adapter.list_markets(status="open" if detail.status == "open" else "all", limit=120)
            )
            for raw_candidate in candidate_rows:
                candidate = self._annotate_market_freshness(raw_candidate)
                if not self._is_research_relevant_market(candidate):
                    continue
                if candidate.market_id in seen or (candidate.freshness and candidate.freshness.is_broken):
                    continue
                relationship, note, similarity = self._describe_related_market(detail, candidate, same_event=False)
                if relationship == "topic_similarity" and similarity < 0.55:
                    continue
                if relationship == "cross_venue_analog" and similarity < 0.48:
                    continue
                seen.add(candidate.market_id)
                related_rows.append(
                    (
                        self._related_sort_key(relationship, similarity, candidate),
                        RelatedMarketRecord(
                            market_id=candidate.market_id,
                            venue=candidate.venue,
                            title=candidate.title,
                            probability=candidate.current_probability,
                            price_gap=_price_gap(detail.current_probability, candidate.current_probability),
                            relationship=relationship,
                            note=note,
                            source_provider=candidate.source_provider,
                            retrieved_at=candidate.retrieved_at,
                            origin=f"prediction_market_service.{relationship}",
                            transformation_note="Cross-venue linking combines lexical overlap, numeric threshold extraction, and resolution-date proximity.",
                        ),
                    )
                )

        related_rows.sort(key=lambda item: item[0])
        ordered = [row for _, row in related_rows]
        # Venue-metadata-only links are shown (clearly labeled) only when nothing
        # semantically related exists, so an AI-policy market no longer surfaces
        # unrelated venue-event artifacts ahead of or alongside real matches.
        strong = [row for row in ordered if row.relationship != "weak_venue_link"]
        if strong:
            return strong[:limit]
        return ordered[: min(limit, 3)]

    def get_calibration_summary(self, market_id: str, *, sample_size: int = 30) -> CalibrationSummary | None:
        adapter = self._resolve_adapter(market_id)
        if adapter is None:
            return None
        return adapter.build_calibration_summary(sample_size=sample_size)

    def _build_history_series(
        self,
        adapter: PredictionMarketAdapter,
        detail: PredictionMarketRecord,
        *,
        range_key: str,
        resolution_minutes: int | None,
        outcome_id: str | None = None,
    ) -> PredictionProbabilityHistory:
        normalized_range = range_key if range_key in HISTORY_RANGE_KEYS else "max"
        warnings: list[str] = []
        if normalized_range != range_key:
            warnings.append(
                f"Unsupported range '{range_key}'; the full available history was used instead.",
            )

        outcome = self._resolve_outcome(detail, outcome_id)
        if outcome_id and outcome is None:
            warnings.append(
                f"Outcome '{outcome_id}' is not listed on this market; its primary outcome was used instead.",
            )

        window = self._resolve_history_window(
            detail,
            range_key=normalized_range,
            resolution_minutes=resolution_minutes,
            outcome=outcome,
        )

        fetch_window = getattr(adapter, "get_history_window", None)
        if callable(fetch_window):
            try:
                fetch = fetch_window(detail, window)
            except Exception as exc:
                return self._empty_history(
                    detail,
                    window,
                    outcome,
                    warnings=[*warnings, f"{detail.venue} history request failed: {exc}"],
                )
        else:
            try:
                fetch = PredictionHistoryFetch(
                    points=list(adapter.get_history(detail)),
                    windowing="client_clipped",
                )
            except Exception as exc:
                return self._empty_history(
                    detail,
                    window,
                    outcome,
                    warnings=[*warnings, f"{detail.venue} history request failed: {exc}"],
                )

        warnings.extend(fetch.warnings)
        points = sorted(
            (point for point in fetch.points if point.probability is not None),
            key=lambda point: ensure_utc(point.timestamp),
        )
        available_start = ensure_utc(points[0].timestamp) if points else None
        available_end = ensure_utc(points[-1].timestamp) if points else None

        clipped = self._clip_points(points, window.start, window.end)
        if points and not clipped:
            warnings.append(
                "No observations fall inside the requested window; the contract's available history covers "
                f"{_format_span(available_start, available_end)}.",
            )
        elif len(clipped) < len(points) and fetch.windowing != "provider_window":
            warnings.append("The provider returned a wider series than requested; it was clipped locally.")

        effective_resolution = fetch.effective_resolution_minutes
        if window.resolution_minutes is not None and fetch.windowing == "client_clipped":
            clipped = self._downsample_points(clipped, window.resolution_minutes)
            effective_resolution = window.resolution_minutes

        stats = self._build_history_stats(clipped)
        if stats.point_count and stats.span_days is not None and normalized_range != "max":
            requested_days = HISTORY_RANGE_DAYS.get(normalized_range)
            if requested_days is not None and stats.span_days < requested_days * 0.5:
                warnings.append(
                    f"This contract only has {stats.span_days:.1f} days of history inside the requested "
                    f"{normalized_range} window.",
                )
        if effective_resolution is None and stats.median_gap_seconds:
            effective_resolution = max(int(round(stats.median_gap_seconds / 60)), 1)

        return PredictionProbabilityHistory(
            market_id=detail.market_id,
            venue=detail.venue,
            points=clipped,
            outcome_id=outcome.outcome_id if outcome else None,
            outcome_label=outcome.label if outcome else detail.probability_label,
            requested_range=normalized_range,
            effective_range=self._describe_effective_range(stats),
            requested_resolution_minutes=resolution_minutes,
            effective_resolution_minutes=effective_resolution,
            window_start=window.start,
            window_end=window.end,
            coverage_start=stats.first_timestamp,
            coverage_end=stats.last_timestamp,
            windowing=fetch.windowing,
            stats=stats,
            warnings=warnings,
            source_provider=clipped[0].source_provider if clipped else detail.source_provider,
            retrieved_at=clipped[0].retrieved_at if clipped else detail.retrieved_at,
            origin=clipped[0].origin if clipped else detail.origin,
            transformation_note=clipped[0].transformation_note if clipped else None,
        )

    def _empty_history(
        self,
        detail: PredictionMarketRecord,
        window: PredictionHistoryWindow,
        outcome,
        *,
        warnings: list[str],
    ) -> PredictionProbabilityHistory:
        return PredictionProbabilityHistory(
            market_id=detail.market_id,
            venue=detail.venue,
            outcome_id=outcome.outcome_id if outcome else None,
            outcome_label=outcome.label if outcome else detail.probability_label,
            requested_range=window.range_key,
            effective_range="none",
            requested_resolution_minutes=window.resolution_minutes,
            window_start=window.start,
            window_end=window.end,
            windowing="unavailable",
            stats=PredictionHistoryStats(point_count=0),
            warnings=warnings,
            source_provider=detail.source_provider,
            retrieved_at=detail.retrieved_at,
            origin=detail.origin,
        )

    def _resolve_outcome(self, detail: PredictionMarketRecord, outcome_id: str | None):
        if not detail.outcomes:
            return None
        if outcome_id:
            for outcome in detail.outcomes:
                if outcome.outcome_id == outcome_id:
                    return outcome
            return None
        return detail.outcomes[0]

    def _resolve_history_window(
        self,
        detail: PredictionMarketRecord,
        *,
        range_key: str,
        resolution_minutes: int | None,
        outcome,
    ) -> PredictionHistoryWindow:
        current_time = ensure_utc(now_utc())
        market_end = ensure_utc(detail.close_time or detail.end_time)
        end = min(market_end, current_time) if market_end is not None else current_time
        market_start = ensure_utc(detail.open_time)

        if range_key == "max":
            # `max` means every observation the venue will return. Clamping to the
            # recorded open time would silently drop quotes that predate it, which
            # happens whenever a venue backdates or re-lists a contract.
            start = None
            span_start = market_start or end - timedelta(days=HISTORY_RANGE_DAYS["1y"])
        else:
            start = end - timedelta(days=HISTORY_RANGE_DAYS[range_key])
            span_start = start

        resolved_resolution = resolution_minutes
        if resolved_resolution is None:
            resolved_resolution = _auto_resolution_minutes(span_start, end)
        if resolved_resolution is not None:
            resolved_resolution = _clamp_up(resolved_resolution, RESOLUTION_CHOICES_MINUTES)

        return PredictionHistoryWindow(
            range_key=range_key,
            start=start,
            end=end,
            resolution_minutes=resolved_resolution,
            resolution_is_auto=resolution_minutes is None,
            outcome_id=outcome.outcome_id if outcome else None,
            outcome_token_id=outcome.token_id if outcome else None,
        )

    @staticmethod
    def _clip_points(points, start: datetime | None, end: datetime | None):
        if start is None and end is None:
            return list(points)
        clipped = []
        for point in points:
            stamp = ensure_utc(point.timestamp)
            if start is not None and stamp < start:
                continue
            if end is not None and stamp > end:
                continue
            clipped.append(point)
        return clipped

    @staticmethod
    def _downsample_points(points, resolution_minutes: int):
        """Keep the last observation in each bucket, always preserving the ends."""
        if resolution_minutes <= 0 or len(points) < 3:
            return list(points)
        bucket_seconds = resolution_minutes * 60
        kept = []
        current_bucket: int | None = None
        for point in points:
            bucket = int(ensure_utc(point.timestamp).timestamp() // bucket_seconds)
            if current_bucket is None or bucket != current_bucket:
                kept.append(point)
                current_bucket = bucket
            else:
                kept[-1] = point
        if kept and kept[-1] is not points[-1]:
            kept.append(points[-1])
        return kept

    def _build_history_stats(self, points) -> PredictionHistoryStats:
        if not points:
            return PredictionHistoryStats(point_count=0)

        probabilities = [point.probability for point in points]
        timestamps = [ensure_utc(point.timestamp) for point in points]
        high = max(probabilities)
        low = min(probabilities)
        width = high - low
        last = probabilities[-1]
        first = probabilities[0]
        span_seconds = (timestamps[-1] - timestamps[0]).total_seconds()

        gaps = [
            (timestamps[index] - timestamps[index - 1]).total_seconds()
            for index in range(1, len(timestamps))
        ]
        moves = [probabilities[index] - probabilities[index - 1] for index in range(1, len(probabilities))]
        max_move = None
        max_move_at = None
        if moves:
            max_index = max(range(len(moves)), key=lambda index: abs(moves[index]))
            max_move = moves[max_index]
            max_move_at = timestamps[max_index + 1]

        return PredictionHistoryStats(
            point_count=len(points),
            first_timestamp=timestamps[0],
            last_timestamp=timestamps[-1],
            span_days=span_seconds / 86400 if span_seconds > 0 else 0.0,
            first_probability=first,
            last_probability=last,
            change=last - first,
            high=high,
            low=low,
            range_width=width,
            percentile_of_range=((last - low) / width) if width > 0 else None,
            max_move=max_move,
            max_move_at=max_move_at,
            daily_volatility=self._daily_volatility(probabilities, gaps),
            share_above_half=sum(1 for value in probabilities if value > 0.5) / len(probabilities),
            median_gap_seconds=_median(gaps),
            largest_gap_seconds=max(gaps) if gaps else None,
        )

    @staticmethod
    def _daily_volatility(probabilities: list[float], gaps: list[float]) -> float | None:
        """Standard deviation of probability changes, scaled to a daily step.

        Probabilities are bounded in [0, 1], so this is reported in probability
        points per day rather than as an annualized return volatility.
        """
        moves = [probabilities[index] - probabilities[index - 1] for index in range(1, len(probabilities))]
        if len(moves) < 2:
            return None
        mean = sum(moves) / len(moves)
        variance = sum((move - mean) ** 2 for move in moves) / (len(moves) - 1)
        step_seconds = _median(gaps)
        if not step_seconds or step_seconds <= 0:
            return None
        return math.sqrt(variance) * math.sqrt(86400 / step_seconds)

    @staticmethod
    def _describe_effective_range(stats: PredictionHistoryStats) -> str:
        if not stats.point_count or stats.span_days is None:
            return "none"
        if stats.span_days < 1:
            return "intraday"
        if stats.span_days < 8:
            return "1w"
        if stats.span_days < 32:
            return "1m"
        if stats.span_days < 95:
            return "3m"
        if stats.span_days < 190:
            return "6m"
        if stats.span_days < 400:
            return "1y"
        return "multi_year"

    def _compare_pair(
        self,
        left: PredictionComparisonLeg,
        right: PredictionComparisonLeg,
        *,
        resolution_minutes: int,
    ) -> PredictionPairAnalytics:
        aligned = _align_series(left.points, right.points, resolution_minutes)
        if not aligned:
            return PredictionPairAnalytics(
                left_market_id=left.market_id,
                right_market_id=right.market_id,
                overlap_points=0,
                overlap_start=None,
                overlap_end=None,
                current_spread=_optional_difference(left.current_probability, right.current_probability),
                mean_spread=None,
                max_spread=None,
                min_spread=None,
                spread_volatility=None,
                current_spread_percentile=None,
                correlation=None,
                warnings=["These contracts have no overlapping history in the selected window."],
            )

        timestamps = [stamp for stamp, _, _ in aligned]
        left_values = [value for _, value, _ in aligned]
        right_values = [value for _, _, value in aligned]
        spreads = [left_value - right_value for left_value, right_value in zip(left_values, right_values)]
        current_spread = spreads[-1]
        mean_spread = sum(spreads) / len(spreads)
        max_spread = max(spreads)
        min_spread = min(spreads)
        spread_width = max_spread - min_spread

        variance = (
            sum((value - mean_spread) ** 2 for value in spreads) / (len(spreads) - 1)
            if len(spreads) > 1
            else 0.0
        )

        warnings: list[str] = []
        if len(aligned) < MIN_PAIR_OVERLAP_POINTS:
            warnings.append(
                f"Only {len(aligned)} aligned observations overlap; pair analytics are indicative at best.",
            )

        series_cap = max(len(aligned) // MAX_SPREAD_SERIES_POINTS, 1)
        spread_series = [
            PredictionSpreadPoint(timestamp=timestamps[index], spread=spreads[index])
            for index in range(0, len(spreads), series_cap)
        ]
        if spread_series and spread_series[-1].timestamp != timestamps[-1]:
            spread_series.append(PredictionSpreadPoint(timestamp=timestamps[-1], spread=spreads[-1]))

        return PredictionPairAnalytics(
            left_market_id=left.market_id,
            right_market_id=right.market_id,
            overlap_points=len(aligned),
            overlap_start=timestamps[0],
            overlap_end=timestamps[-1],
            current_spread=current_spread,
            mean_spread=mean_spread,
            max_spread=max_spread,
            min_spread=min_spread,
            spread_volatility=math.sqrt(variance) if variance > 0 else 0.0,
            current_spread_percentile=((current_spread - min_spread) / spread_width) if spread_width > 0 else None,
            correlation=_change_correlation(left_values, right_values),
            spread_series=spread_series,
            warnings=warnings,
        )

    @staticmethod
    def _build_basket_summary(legs: list[PredictionComparisonLeg]) -> PredictionBasketSummary | None:
        if not legs:
            return None
        venues = sorted({leg.venue for leg in legs})
        probabilities = [leg.current_probability for leg in legs if leg.current_probability is not None]
        probability_sum = sum(probabilities) if len(probabilities) == len(legs) else None
        same_venue = len(venues) == 1
        event_ids = {leg.event_id for leg in legs if leg.event_id}
        same_event = len(legs) > 1 and len(event_ids) == 1 and len(event_ids) == len({leg.event_id for leg in legs})

        note = None
        if probability_sum is not None and len(legs) > 1:
            note = (
                "The probability sum is only a book overround if these contracts are mutually exclusive and "
                "cover every outcome."
                + (
                    " These contracts share one venue event, which makes that more likely but is not proof."
                    if same_event
                    else " These contracts do not share one venue event, so treat the sum as descriptive only."
                )
            )

        return PredictionBasketSummary(
            leg_count=len(legs),
            probability_sum=probability_sum,
            implied_overround=(probability_sum - 1.0) if probability_sum is not None and len(legs) > 1 else None,
            same_event=same_event,
            same_venue=same_venue,
            venues=venues,
            note=note,
        )

    def _resolve_adapter(self, market_id: str) -> PredictionMarketAdapter | None:
        venue = str(market_id.split(":", 1)[0]).strip().lower()
        return self.adapters.get(venue)

    @staticmethod
    def _screener_fetch_limit(limit: int) -> int:
        requested = max(limit, 1)
        return min(max(requested * 8, 200), 400)

    @staticmethod
    def _provider_market_id(market_id: str) -> str:
        return str(market_id.split(":", 1)[1]).strip()

    def _matches_screener(self, row: PredictionMarketRecord, request: PredictionMarketScreenerRequest) -> bool:
        if request.query and self._query_relevance_score(row, request.query) <= 0.0:
            return False
        if request.category and request.category.strip():
            category = request.category.strip().lower()
            if category != str(row.category or "").lower():
                return False
        if request.min_volume is not None and (row.volume or 0.0) < request.min_volume:
            return False
        if request.min_liquidity is not None and (row.liquidity or 0.0) < request.min_liquidity:
            return False
        if request.min_open_interest is not None and (row.open_interest or 0.0) < request.min_open_interest:
            return False
        if request.min_probability is not None and (row.current_probability is None or row.current_probability < request.min_probability):
            return False
        if request.max_probability is not None and (row.current_probability is None or row.current_probability > request.max_probability):
            return False
        if request.min_repricing_abs is not None and abs(row.recent_price_change or 0.0) < request.min_repricing_abs:
            return False
        if request.max_days_to_resolution is not None and row.end_time is not None:
            remaining = (row.end_time - self._reference_time(row)).total_seconds() / 86400.0
            if remaining > request.max_days_to_resolution:
                return False
        return True

    def _should_show_in_screener(self, row: PredictionMarketRecord, request: PredictionMarketScreenerRequest) -> bool:
        freshness = row.freshness
        if request.status != "open" or freshness is None:
            return True
        if freshness.is_broken:
            return False
        return True

    def _sort_key(self, row: PredictionMarketRecord, sort_by: str):
        if sort_by == "liquidity_desc":
            return (-(row.liquidity or 0.0), -(row.volume or 0.0), self._freshness_sort_penalty(row), row.title.lower())
        if sort_by == "open_interest_desc":
            return (-(row.open_interest or 0.0), -(row.volume or 0.0), self._freshness_sort_penalty(row), row.title.lower())
        if sort_by == "repricing_desc":
            return (-abs(row.recent_price_change or 0.0), -(row.volume_24h or 0.0), self._freshness_sort_penalty(row), row.title.lower())
        if sort_by == "resolution_soon":
            end_time = row.end_time or datetime.max
            return (end_time, self._freshness_sort_penalty(row), -(row.volume or 0.0), row.title.lower())
        return (
            -(row.research_score or 0.0),
            self._freshness_sort_penalty(row),
            -(row.volume_24h or 0.0),
            -(row.liquidity or 0.0),
            row.title.lower(),
        )

    def _freshness_sort_penalty(self, row: PredictionMarketRecord) -> int:
        freshness = row.freshness
        if freshness is None:
            return 1
        return {"fresh": 0, "delayed": 1, "stale": 2, "broken": 3, "closed": 1}.get(freshness.status, 1)

    def _describe_related_market(
        self,
        detail: PredictionMarketRecord,
        candidate: PredictionMarketRecord,
        *,
        same_event: bool,
    ) -> tuple[str, str, float]:
        similarity = self._similarity(detail, candidate)
        threshold_pair = self._threshold_pair(detail, candidate)
        close_in_time = self._close_in_time(detail, candidate, max_days=5)

        if same_event and threshold_pair is not None:
            return (
                "adjacent_threshold",
                f"Same event family with nearby numeric hurdles {threshold_pair[0]} vs {threshold_pair[1]}.",
                similarity + 0.2,
            )
        if not same_event and (similarity >= 0.48 or (threshold_pair is not None and close_in_time)):
            if threshold_pair is not None:
                note = f"Cross-venue analog with nearby thresholds {threshold_pair[0]} vs {threshold_pair[1]} and aligned resolution timing."
            else:
                note = f"Cross-venue analog with lexical similarity score {similarity:.2f} and nearby resolution timing."
            return "cross_venue_analog", note, similarity
        if same_event and similarity >= 0.6:
            return (
                "conditional_consistency",
                "Same event cluster with overlapping event tokens; compare these contracts for internal consistency.",
                similarity,
            )
        if same_event and similarity >= RELATED_SAME_EVENT_MIN_SIMILARITY:
            return (
                "same_event",
                f"Shares the venue event and overlapping topic tokens (similarity {similarity:.2f}).",
                similarity,
            )
        if same_event:
            return (
                "weak_venue_link",
                f"Shares venue event metadata only; no topical overlap detected (similarity {similarity:.2f}). Likely unrelated.",
                similarity,
            )
        return "topic_similarity", f"Cross-venue topical overlap score {similarity:.2f}.", similarity

    def _related_sort_key(self, relationship: str, similarity: float, candidate: PredictionMarketRecord) -> tuple[int, float, float, str]:
        return (
            RELATED_RELATIONSHIP_PRIORITY.get(relationship, 9),
            -similarity,
            -(candidate.research_score or 0.0),
            candidate.title.lower(),
        )

    def _close_in_time(self, left: PredictionMarketRecord, right: PredictionMarketRecord, *, max_days: float) -> bool:
        if left.end_time is None or right.end_time is None:
            return False
        return abs((left.end_time - right.end_time).total_seconds()) <= max_days * 86400.0

    def _similarity(self, left: PredictionMarketRecord, right: PredictionMarketRecord) -> float:
        left_tokens = _tokenize(" ".join(filter(None, [left.title, left.subtitle, left.event_title, left.category])))
        right_tokens = _tokenize(" ".join(filter(None, [right.title, right.subtitle, right.event_title, right.category])))
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        jaccard = overlap / union if union else 0.0
        if self._close_in_time(left, right, max_days=2):
            jaccard += 0.15
        if self._threshold_pair(left, right) is not None:
            jaccard += 0.1
        return min(jaccard, 1.0)

    def _threshold_pair(self, left: PredictionMarketRecord, right: PredictionMarketRecord) -> tuple[str, str] | None:
        left_thresholds = _extract_threshold_tokens(left.title, left.subtitle, left.event_title)
        right_thresholds = _extract_threshold_tokens(right.title, right.subtitle, right.event_title)
        if not left_thresholds or not right_thresholds:
            return None
        if left_thresholds[0] == right_thresholds[0]:
            return None
        left_context = _tokenize(" ".join(filter(None, [left.title, left.event_title])))
        right_context = _tokenize(" ".join(filter(None, [right.title, right.event_title])))
        if len(left_context & right_context) < 3:
            return None
        return left_thresholds[0], right_thresholds[0]

    def _is_research_relevant_market(self, row: PredictionMarketRecord) -> bool:
        return row.category in ALLOWED_RESEARCH_CATEGORIES

    def _is_excluded_topic_market(self, row: PredictionMarketRecord) -> bool:
        headline_text = " ".join(
            filter(None, [row.title, row.subtitle, row.event_title, row.series_title])
        ).lower()
        return self._contains_excluded_topic(_normalize_text(headline_text))

    def _canonicalize_rows(self, rows: list[PredictionMarketRecord]) -> list[PredictionMarketRecord]:
        return [self._canonicalize_market(row) for row in rows]

    def _canonicalize_market(self, row: PredictionMarketRecord) -> PredictionMarketRecord:
        category = self._canonical_category(row)
        tags = [tag for tag in row.tags if tag]
        if category and category not in tags:
            tags = [category, *tags]
        return replace(row, category=category, tags=tags)

    def _canonical_category(self, row: PredictionMarketRecord) -> str | None:
        exact_fields = [
            str(row.category or "").strip().lower(),
            *[str(tag).strip().lower() for tag in row.tags],
        ]
        exact_matches = [EXACT_CATEGORY_ALIASES[value] for value in exact_fields if value in EXACT_CATEGORY_ALIASES]

        headline_text = " ".join(
            filter(
                None,
                [
                    row.title,
                    row.subtitle,
                    row.event_title,
                    row.series_title,
                ],
            )
        ).lower()
        normalized_text = _normalize_text(headline_text)
        if self._contains_excluded_topic(normalized_text):
            return None
        for label, keywords in CATEGORY_KEYWORD_PATTERNS:
            if any(_normalized_keyword_match(normalized_text, keyword) for keyword in keywords):
                return label
        for value in exact_fields:
            if value in EXACT_CATEGORY_ALIASES:
                return EXACT_CATEGORY_ALIASES[value]
        if exact_matches:
            return exact_matches[0]
        return None

    def _contains_excluded_topic(self, normalized_text: str) -> bool:
        return any(_normalized_keyword_match(normalized_text, keyword) for keyword in CATEGORY_EXCLUSION_KEYWORDS)

    def _annotate_market_freshness(
        self,
        row: PredictionMarketRecord,
        *,
        history_points: list | None = None,
        history_error: str | None = None,
    ) -> PredictionMarketRecord:
        current_time = ensure_utc(now_utc())
        last_history_point_at = None
        if history_points:
            last_history_point_at = max(
                (ensure_utc(point.timestamp) for point in history_points if point.timestamp is not None),
                default=None,
            )
        freshness = self._build_freshness(
            row,
            current_time=current_time,
            last_history_point_at=last_history_point_at,
            history_error=history_error,
        )
        return replace(row, freshness=freshness)

    def _build_freshness(
        self,
        row: PredictionMarketRecord,
        *,
        current_time: datetime,
        last_history_point_at: datetime | None,
        history_error: str | None,
    ) -> PredictionMarketFreshness:
        current_time = ensure_utc(current_time)
        retrieved_at = ensure_utc(row.retrieved_at)
        end_time = ensure_utc(row.end_time)
        last_history_point_at = ensure_utc(last_history_point_at)

        retrieval_age_seconds = None
        if current_time is not None and retrieved_at is not None:
            retrieval_age_seconds = max((current_time - retrieved_at).total_seconds(), 0.0)

        history_lag_seconds = None
        if retrieved_at is not None and last_history_point_at is not None:
            history_lag_seconds = max((retrieved_at - last_history_point_at).total_seconds(), 0.0)

        integrity_reference_time = retrieved_at or current_time
        if row.status == "open" and end_time is not None and integrity_reference_time is not None and end_time <= integrity_reference_time:
            reason = f"Venue still marks this market open even though end_time passed at {end_time.isoformat()}."
            if last_history_point_at is not None and last_history_point_at > end_time:
                reason = (
                    f"Venue still marks this market open after end_time {end_time.isoformat()}, "
                    f"and history continued updating through {last_history_point_at.isoformat()}."
                )
            return PredictionMarketFreshness(
                status="broken",
                is_stale=True,
                is_broken=True,
                reason=reason,
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        if row.status in {"resolved", "closed"}:
            return PredictionMarketFreshness(
                status="closed",
                is_stale=False,
                is_broken=False,
                reason="Closed or resolved contracts are kept for research, not current open inventory.",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        if history_error:
            return PredictionMarketFreshness(
                status="delayed",
                is_stale=False,
                is_broken=False,
                reason=f"History endpoint failed during freshness evaluation: {history_error}",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        if retrieval_age_seconds is not None and retrieval_age_seconds >= STALE_RETRIEVAL_SECONDS:
            return PredictionMarketFreshness(
                status="stale",
                is_stale=True,
                is_broken=False,
                reason=f"Latest venue payload is more than {int(STALE_RETRIEVAL_SECONDS / 3600)} hours old.",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        history_stale_limit = self._history_lag_stale_seconds(row, current_time)
        history_delayed_limit = history_stale_limit / 2.0
        if history_lag_seconds is not None and history_lag_seconds >= history_stale_limit:
            return PredictionMarketFreshness(
                status="stale",
                is_stale=True,
                is_broken=False,
                reason=f"Probability history lags the latest fetch by roughly {int(history_lag_seconds // 3600)} hours.",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        if retrieval_age_seconds is not None and retrieval_age_seconds >= DELAYED_RETRIEVAL_SECONDS:
            return PredictionMarketFreshness(
                status="delayed",
                is_stale=False,
                is_broken=False,
                reason=f"Metadata is recent enough to use, but the last fetch is already {int(retrieval_age_seconds // 3600)} hours old.",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        if history_lag_seconds is not None and history_lag_seconds >= history_delayed_limit:
            return PredictionMarketFreshness(
                status="delayed",
                is_stale=False,
                is_broken=False,
                reason=f"History is slightly behind the latest venue snapshot by about {int(history_lag_seconds // 3600)} hours.",
                last_history_point_at=last_history_point_at,
                retrieval_age_seconds=retrieval_age_seconds,
                history_lag_seconds=history_lag_seconds,
            )

        return PredictionMarketFreshness(
            status="fresh",
            is_stale=False,
            is_broken=False,
            reason="Venue metadata is recent and no integrity issue was detected.",
            last_history_point_at=last_history_point_at,
            retrieval_age_seconds=retrieval_age_seconds,
            history_lag_seconds=history_lag_seconds,
        )

    def _history_lag_stale_seconds(self, row: PredictionMarketRecord, current_time: datetime) -> float:
        days_to_resolution = self._days_to_resolution(row, current_time)
        if days_to_resolution is None:
            return 24 * 60 * 60
        if days_to_resolution <= 3:
            return 6 * 60 * 60
        if days_to_resolution <= 14:
            return 12 * 60 * 60
        return 24 * 60 * 60

    def _annotate_research_rank(self, row: PredictionMarketRecord, request: PredictionMarketScreenerRequest) -> PredictionMarketRecord:
        query_score = self._query_relevance_score(row, request.query)
        signal_score = self._market_signal_score(row)
        recency_score = self._recency_score(row)
        resolution_score = self._resolution_window_score(row)
        repricing_score = min(abs(row.recent_price_change or 0.0) / 0.15, 1.0)

        if request.query.strip():
            combined_score = (
                (query_score * 0.58)
                + (signal_score * 0.22)
                + (recency_score * 0.10)
                + (resolution_score * 0.10)
            )
        else:
            combined_score = (
                (signal_score * 0.44)
                + (resolution_score * 0.22)
                + (recency_score * 0.18)
                + (repricing_score * 0.16)
            )

        freshness = row.freshness
        if freshness is not None:
            if freshness.status == "delayed":
                combined_score -= 0.03
            elif freshness.status == "stale":
                combined_score -= 0.12
            elif freshness.status == "broken":
                combined_score -= 0.3

        rationale = (
            f"Research rank uses relevance {query_score:.2f}, signal {signal_score:.2f}, "
            f"recency {recency_score:.2f}, and resolution {resolution_score:.2f}."
        )
        return replace(
            row,
            research_score=round(max(combined_score, 0.0) * 100.0, 1),
            research_rationale=rationale,
        )

    def _query_relevance_score(self, row: PredictionMarketRecord, query: str) -> float:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return 0.0

        query_tokens = _query_tokens(query)
        if not query_tokens:
            return 0.0

        weighted_fields = [
            (row.title, 1.0),
            (row.event_title, 0.85),
            (row.subtitle, 0.5),
            (row.series_title, 0.35),
            (row.category, 0.25),
            (" ".join(row.tags), 0.2),
        ]
        description_text = _normalize_text(row.description or "")
        priority_tokens = _query_tokens(
            " ".join(filter(None, [row.title, row.subtitle, row.event_title, row.series_title, row.category, " ".join(row.tags)]))
        )
        score = 0.0

        if _phrase_in_text(normalized_query, row.title):
            score += 0.45
        if _phrase_in_text(normalized_query, row.event_title):
            score += 0.35

        for field_text, weight in weighted_fields:
            field_tokens = _query_tokens(field_text or "")
            if not field_tokens:
                continue
            overlap = len(query_tokens & field_tokens)
            if overlap == 0:
                continue
            coverage = overlap / len(query_tokens)
            score += weight * coverage
            if coverage == 1.0:
                score += weight * 0.2

        if query_tokens <= priority_tokens:
            score += 0.2

        if len(query_tokens) > 1:
            description_tokens = _query_tokens(description_text)
            overlap = len(query_tokens & description_tokens)
            if overlap > 0 and (query_tokens & priority_tokens):
                score += 0.1 * (overlap / len(query_tokens))

        if len(query_tokens) == 1 and not (query_tokens & priority_tokens):
            return 0.0
        return min(score, 1.5)

    def _market_signal_score(self, row: PredictionMarketRecord) -> float:
        return (
            (self._scaled_log(row.volume_24h, pivot=25_000.0) * 0.38)
            + (self._scaled_log(row.liquidity, pivot=50_000.0) * 0.3)
            + (self._scaled_log(row.volume, pivot=500_000.0) * 0.2)
            + (self._scaled_log(row.open_interest, pivot=50_000.0) * 0.12)
        )

    def _recency_score(self, row: PredictionMarketRecord) -> float:
        freshness = row.freshness
        if freshness is None:
            return 0.4
        return {
            "fresh": 1.0,
            "delayed": 0.6,
            "stale": 0.2,
            "broken": 0.0,
            "closed": 0.45,
        }.get(freshness.status, 0.4)

    def _resolution_window_score(self, row: PredictionMarketRecord) -> float:
        days = self._days_to_resolution(row, self._reference_time(row))
        if days is None:
            return 0.35
        if days < 0:
            return 0.0
        if days <= 1:
            return 0.82
        if days <= 30:
            return 1.0 - ((days - 1) / 29.0) * 0.12
        if days <= 90:
            return 0.88 - ((days - 30) / 60.0) * 0.38
        if days <= 180:
            return 0.5 - ((days - 90) / 90.0) * 0.28
        return 0.18

    def _days_to_resolution(self, row: PredictionMarketRecord, current_time: datetime) -> float | None:
        end_time = ensure_utc(row.end_time)
        current_time = ensure_utc(current_time)
        if end_time is None or current_time is None:
            return None
        return (end_time - current_time).total_seconds() / 86400.0

    def _reference_time(self, row: PredictionMarketRecord) -> datetime:
        return ensure_utc(row.retrieved_at) or ensure_utc(now_utc())

    def _scaled_log(self, value: float | None, *, pivot: float) -> float:
        if value is None or value <= 0:
            return 0.0
        return min(math.log1p(value) / math.log1p(pivot), 1.0)

    def _build_venue_status(
        self,
        *,
        venue: str,
        request: PredictionMarketScreenerRequest,
        all_rows: list[PredictionMarketRecord],
        research_rows: list[PredictionMarketRecord],
        matched_rows: list[PredictionMarketRecord],
        visible_rows: list[PredictionMarketRecord],
    ) -> PredictionVenueStatus:
        stale_markets = sum(1 for row in research_rows if row.freshness and row.freshness.is_stale)
        broken_markets = sum(1 for row in research_rows if row.freshness and row.freshness.is_broken)
        retrieved_at = max((row.retrieved_at for row in all_rows if row.retrieved_at is not None), default=None)

        if visible_rows:
            message = (
                f"{len(visible_rows)} research contracts surfaced from {venue}; "
                f"{broken_markets} broken and {stale_markets} stale candidates were tracked."
            )
            status = "active"
        elif matched_rows:
            message = "Contracts matched the screen, but integrity filters hid the stale or broken rows from open inventory."
            status = "filtered"
        elif research_rows:
            if request.query.strip():
                message = f"No {venue} contracts matched the current query and filter set."
            else:
                message = f"{venue} returned research contracts, but none passed the current screen filters."
            status = "no_results"
        elif all_rows:
            message = f"{venue} returned markets, but none fit Gamma's research-focused category filters."
            status = "filtered"
        else:
            message = f"{venue} returned no markets for the current request."
            status = "no_results"

        return PredictionVenueStatus(
            venue=venue,
            status=status,
            message=message,
            total_markets=len(all_rows),
            matched_markets=len(matched_rows),
            visible_markets=len(visible_rows),
            stale_markets=stale_markets,
            broken_markets=broken_markets,
            retrieved_at=retrieved_at,
        )


def _tokenize(text: str) -> set[str]:
    stopwords = {"the", "will", "what", "during", "after", "before", "for", "and", "or", "in", "on", "vs"}
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in stopwords}


def _query_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token and token not in QUERY_STOPWORDS
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _normalized_keyword_match(normalized_text: str, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    if " " in normalized_keyword:
        return f" {normalized_keyword} " in f" {normalized_text} "
    return normalized_keyword in set(normalized_text.split())


def _phrase_in_text(normalized_phrase: str, text: str | None) -> bool:
    normalized_text = _normalize_text(text or "")
    if not normalized_phrase or not normalized_text:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "


def _extract_threshold_tokens(*texts: str | None) -> list[str]:
    thresholds: list[str] = []
    for text in texts:
        for token in re.findall(r"\b\d+(?:\.\d+)?%?|\$\d+(?:,\d{3})*(?:\.\d+)?\b", str(text or "")):
            cleaned = token.strip()
            if not cleaned:
                continue
            numeric_only = cleaned.replace("$", "").replace("%", "").replace(",", "")
            try:
                numeric_value = float(numeric_only)
            except ValueError:
                continue
            if 1900 <= numeric_value <= 2100 and not cleaned.endswith("%"):
                continue
            thresholds.append(cleaned)
    return thresholds


def _price_gap(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return abs(left - right)


def _clamp_up(value: int, choices: tuple[int, ...]) -> int:
    for choice in choices:
        if value <= choice:
            return choice
    return choices[-1]


def _auto_resolution_minutes(start: datetime, end: datetime) -> int:
    span_minutes = max((end - start).total_seconds() / 60, 1)
    return _clamp_up(
        max(int(span_minutes / AUTO_RESOLUTION_TARGET_POINTS), 1),
        RESOLUTION_CHOICES_MINUTES,
    )


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _min_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _max_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _optional_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _format_span(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "an unknown period"
    return f"{start.date().isoformat()} to {end.date().isoformat()}"


def _align_series(
    left_points,
    right_points,
    resolution_minutes: int,
) -> list[tuple[datetime, float, float]]:
    """Sample both series onto one grid over their overlapping period.

    The last observation before each grid stamp is carried forward, so a venue
    that quotes less often is not treated as having moved to a new price at the
    moment the other venue prints.
    """
    if not left_points or not right_points:
        return []

    left_sorted = sorted(left_points, key=lambda point: ensure_utc(point.timestamp))
    right_sorted = sorted(right_points, key=lambda point: ensure_utc(point.timestamp))
    start = max(ensure_utc(left_sorted[0].timestamp), ensure_utc(right_sorted[0].timestamp))
    end = min(ensure_utc(left_sorted[-1].timestamp), ensure_utc(right_sorted[-1].timestamp))
    if end <= start:
        return []

    step_seconds = max(resolution_minutes, 1) * 60
    span_seconds = (end - start).total_seconds()
    if span_seconds / step_seconds > MAX_ALIGNED_GRID_POINTS:
        step_seconds = span_seconds / MAX_ALIGNED_GRID_POINTS

    aligned: list[tuple[datetime, float, float]] = []
    left_index = 0
    right_index = 0
    left_value: float | None = None
    right_value: float | None = None
    stamp = start
    while stamp <= end:
        while left_index < len(left_sorted) and ensure_utc(left_sorted[left_index].timestamp) <= stamp:
            left_value = left_sorted[left_index].probability
            left_index += 1
        while right_index < len(right_sorted) and ensure_utc(right_sorted[right_index].timestamp) <= stamp:
            right_value = right_sorted[right_index].probability
            right_index += 1
        if left_value is not None and right_value is not None:
            aligned.append((stamp, left_value, right_value))
        stamp = stamp + timedelta(seconds=step_seconds)
    return aligned


def _change_correlation(left_values: list[float], right_values: list[float]) -> float | None:
    """Pearson correlation of first differences.

    Correlating probability levels would mostly measure shared drift toward
    resolution; correlating changes measures whether the contracts reprice
    together.
    """
    if len(left_values) < 3 or len(right_values) != len(left_values):
        return None
    left_moves = [left_values[index] - left_values[index - 1] for index in range(1, len(left_values))]
    right_moves = [right_values[index] - right_values[index - 1] for index in range(1, len(right_values))]
    count = len(left_moves)
    if count < 2:
        return None
    left_mean = sum(left_moves) / count
    right_mean = sum(right_moves) / count
    covariance = sum(
        (left_moves[index] - left_mean) * (right_moves[index] - right_mean) for index in range(count)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left_moves)
    right_variance = sum((value - right_mean) ** 2 for value in right_moves)
    if left_variance <= 0 or right_variance <= 0:
        return None
    return covariance / math.sqrt(left_variance * right_variance)
