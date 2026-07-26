from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ProvenanceRecord:
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionMarketOutcome:
    outcome_id: str
    label: str
    probability: float | None
    token_id: str | None = None
    resolved: bool | None = None
    winner: bool | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionMarketFreshness:
    status: str
    is_stale: bool
    is_broken: bool
    reason: str | None = None
    last_history_point_at: datetime | None = None
    retrieval_age_seconds: float | None = None
    history_lag_seconds: float | None = None


@dataclass(frozen=True)
class PredictionMarketRecord:
    market_id: str
    venue: str
    title: str
    subtitle: str | None
    description: str | None
    status: str
    category: str | None
    event_id: str | None
    event_title: str | None
    series_id: str | None
    series_title: str | None
    provider_market_id: str
    provider_condition_id: str | None
    provider_event_id: str | None
    provider_series_id: str | None
    slug: str | None
    end_time: datetime | None
    open_time: datetime | None
    close_time: datetime | None
    current_probability: float | None
    probability_label: str | None
    volume: float | None
    volume_24h: float | None
    liquidity: float | None
    open_interest: float | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    recent_price_change: float | None
    resolved_probability: float | None
    resolution_outcome: bool | None
    image_url: str | None
    resolution_source: str | None
    outcomes: list[PredictionMarketOutcome] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    freshness: PredictionMarketFreshness | None = None
    research_score: float | None = None
    research_rationale: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionProbabilityPoint:
    timestamp: datetime
    probability: float
    volume: float | None = None
    open_interest: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionHistoryWindow:
    """Requested probability-history window.

    `range_key` is the user-facing lookback selector. `start`/`end` are the
    resolved absolute bounds, and `resolution_minutes` is the requested bar
    width. A provider may not honor either exactly; the resulting
    `PredictionProbabilityHistory` reports what was actually delivered.
    """

    range_key: str = "max"
    start: datetime | None = None
    end: datetime | None = None
    resolution_minutes: int | None = None
    # True when `resolution_minutes` was derived from the window rather than
    # chosen by the user. An adapter may override an automatic value to work
    # around a provider limit; it must honor an explicit one.
    resolution_is_auto: bool = True
    outcome_id: str | None = None
    outcome_token_id: str | None = None


@dataclass(frozen=True)
class PredictionHistoryFetch:
    """Adapter-level result of a windowed history request.

    `windowing` records how the bounds were honored: `provider_window` when the
    provider was asked for the window directly, `provider_full` when the
    adapter had to request the full series and the caller must clip, and
    `client_clipped` when the adapter has no windowing capability at all.
    """

    points: list[PredictionProbabilityPoint] = field(default_factory=list)
    effective_resolution_minutes: int | None = None
    windowing: str = "provider_window"
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionHistoryStats:
    point_count: int
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    span_days: float | None = None
    first_probability: float | None = None
    last_probability: float | None = None
    change: float | None = None
    high: float | None = None
    low: float | None = None
    range_width: float | None = None
    percentile_of_range: float | None = None
    max_move: float | None = None
    max_move_at: datetime | None = None
    daily_volatility: float | None = None
    share_above_half: float | None = None
    median_gap_seconds: float | None = None
    largest_gap_seconds: float | None = None


@dataclass(frozen=True)
class PredictionProbabilityHistory:
    market_id: str
    venue: str
    points: list[PredictionProbabilityPoint] = field(default_factory=list)
    outcome_id: str | None = None
    outcome_label: str | None = None
    requested_range: str = "max"
    effective_range: str = "max"
    requested_resolution_minutes: int | None = None
    effective_resolution_minutes: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    windowing: str = "provider_window"
    stats: PredictionHistoryStats | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionOutcomeSeries:
    outcome_id: str
    label: str
    probability: float | None
    token_id: str | None
    points: list[PredictionProbabilityPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionComparisonLeg:
    market_id: str
    venue: str
    title: str
    outcome_label: str | None
    current_probability: float | None
    status: str
    end_time: datetime | None
    event_id: str | None = None
    event_title: str | None = None
    points: list[PredictionProbabilityPoint] = field(default_factory=list)
    stats: PredictionHistoryStats | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    origin: str = ""


@dataclass(frozen=True)
class PredictionSpreadPoint:
    timestamp: datetime
    spread: float


@dataclass(frozen=True)
class PredictionPairAnalytics:
    left_market_id: str
    right_market_id: str
    overlap_points: int
    overlap_start: datetime | None
    overlap_end: datetime | None
    current_spread: float | None
    mean_spread: float | None
    max_spread: float | None
    min_spread: float | None
    spread_volatility: float | None
    current_spread_percentile: float | None
    correlation: float | None
    spread_series: list[PredictionSpreadPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionBasketSummary:
    """Aggregate view of the selected contract set.

    `probability_sum` is only an implied book overround when the selected
    contracts are mutually exclusive and collectively exhaustive; the service
    never asserts that on the user's behalf.
    """

    leg_count: int
    probability_sum: float | None
    implied_overround: float | None
    same_event: bool
    same_venue: bool
    venues: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass(frozen=True)
class PredictionMarketComparison:
    requested_range: str
    effective_resolution_minutes: int | None
    window_start: datetime | None
    window_end: datetime | None
    legs: list[PredictionComparisonLeg] = field(default_factory=list)
    pairs: list[PredictionPairAnalytics] = field(default_factory=list)
    basket: PredictionBasketSummary | None = None
    warnings: list[str] = field(default_factory=list)
    retrieved_at: datetime | None = None
    transformation_note: str | None = None


@dataclass(frozen=True)
class WalletActivityRecord:
    participant_id: str
    display_name: str
    venue: str
    side: str
    outcome_label: str | None
    trade_count: int
    total_size: float
    average_price: float | None
    first_seen: datetime | None
    last_seen: datetime | None
    current_edge: float | None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class WalletSummary:
    market_id: str
    venue: str
    concentration_hhi: float | None
    top_participant_share: float | None
    total_trades: int
    total_notional: float
    participants: list[WalletActivityRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class RelatedMarketRecord:
    market_id: str
    venue: str
    title: str
    probability: float | None
    price_gap: float | None
    relationship: str
    note: str | None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionVenueStatus:
    venue: str
    status: str
    message: str | None
    total_markets: int
    matched_markets: int
    visible_markets: int
    stale_markets: int
    broken_markets: int
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class PredictionMarketScreenerResult:
    markets: list[PredictionMarketRecord] = field(default_factory=list)
    venues: list[PredictionVenueStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    sample_size: int
    average_probability: float | None
    realized_frequency: float | None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CalibrationObservation:
    market_id: str
    title: str
    probability: float
    outcome: bool
    settled_at: datetime | None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CalibrationSummary:
    venue: str
    sample_size: int
    buckets: list[CalibrationBucket] = field(default_factory=list)
    observations: list[CalibrationObservation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
