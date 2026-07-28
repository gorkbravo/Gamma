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


# Saved research sets are versioned so a stored record written by an older build
# can be recognized rather than silently reinterpreted.
PREDICTION_RESEARCH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PredictionWatchlistEntry:
    id: str
    market_id: str
    venue: str
    title: str
    probability: float | None = None
    note: str = ""
    saved_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PredictionComparisonSet:
    """A named, reopenable comparison basket."""

    id: str
    name: str
    market_ids: list[str] = field(default_factory=list)
    range_key: str = "max"
    resolution_minutes: int | None = None
    note: str = ""
    saved_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PredictionSavedResearch:
    schema_version: int = PREDICTION_RESEARCH_SCHEMA_VERSION
    watchlist: list[PredictionWatchlistEntry] = field(default_factory=list)
    comparison_sets: list[PredictionComparisonSet] = field(default_factory=list)
    watchlist_limit: int = 0
    comparison_set_limit: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionEventBookLeg:
    market_id: str
    venue: str
    title: str
    subtitle: str | None
    outcome_label: str | None
    probability: float | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    volume: float | None
    liquidity: float | None
    open_interest: float | None
    status: str
    end_time: datetime | None
    resolution_source: str | None
    is_anchor: bool = False
    divergence_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionEventBookCompleteness:
    """Whether the summed book is the venue's whole event.

    A probability sum is only an overround check if nothing is missing from the
    sum. `status` says which of those conditions failed rather than leaving the
    caller to infer it from a leg count.
    """

    status: str
    legs_returned: int
    legs_priced: int
    cap: int
    truncated: bool
    note: str = ""


@dataclass(frozen=True)
class PredictionEventBook:
    """Every sibling contract a venue groups under one event.

    Polymarket represents an N-candidate race as N separate binary markets, so
    checking whether a book sums sensibly means resolving the siblings first.
    `overround_is_meaningful` is the gate: the sum is only presented as an
    overround when the book is complete, fully priced, and the venue's own
    grouping indicates mutually exclusive candidates.
    """

    venue: str
    anchor_market_id: str
    event_id: str | None = None
    event_title: str | None = None
    provider_event_id: str | None = None
    legs: list[PredictionEventBookLeg] = field(default_factory=list)
    probability_sum: float | None = None
    implied_overround: float | None = None
    favorite_market_id: str | None = None
    exclusivity_signal: str = "unverified"
    overround_is_meaningful: bool = False
    completeness: PredictionEventBookCompleteness | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class PredictionBookLevel:
    price: float
    size: float
    notional: float
    cumulative_size: float
    cumulative_notional: float


@dataclass(frozen=True)
class PredictionOrderBookDepth:
    """Resting size behind a quote. Read-only market data; no order entry.

    A spread reading is not interpretable on its own: two contracts quoting the
    same 4-point spread are different research objects when one has $500 resting
    and the other $500k. `notional_within_band` and the slippage estimates are
    what make the spread mean something.
    """

    market_id: str
    venue: str
    outcome_id: str | None = None
    outcome_label: str | None = None
    token_id: str | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    mid: float | None = None
    spread: float | None = None
    bids: list[PredictionBookLevel] = field(default_factory=list)
    asks: list[PredictionBookLevel] = field(default_factory=list)
    depth_band: float = 0.05
    bid_notional_within_band: float | None = None
    ask_notional_within_band: float | None = None
    total_bid_notional: float | None = None
    total_ask_notional: float | None = None
    depth_imbalance: float | None = None
    # Probability points of slippage from the touch to fill a reference clip.
    reference_clip_notional: float = 1000.0
    bid_slippage_reference: float | None = None
    ask_slippage_reference: float | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
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
    """One probability band of a calibration curve.

    `lead_time_hours` is part of the bucket's identity, not decoration: the
    same band measured a day before resolution and a week before resolution are
    different measurements of different things.
    """

    label: str
    sample_size: int
    average_probability: float | None
    realized_frequency: float | None
    lead_time_hours: int = 0
    meets_minimum: bool = False
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
    lead_time_hours: int = 0
    observed_at: datetime | None = None
    observation_lag_hours: float | None = None
    # The final trade before settlement. Reported so the convergence
    # diagnostic is inspectable; it is never an input to a bucket.
    settlement_probability: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CalibrationCurve:
    """Every bucket measured at one fixed lead time before resolution.

    `is_plottable` is false when the sample is too thin to draw honestly; a
    consumer must respect it rather than rendering a shape from three markets.
    """

    lead_time_hours: int
    label: str
    sample_size: int
    buckets: list[CalibrationBucket] = field(default_factory=list)
    brier_score: float | None = None
    mean_signed_error: float | None = None
    is_plottable: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalibrationConvergence:
    """How far the settlement print had already collapsed toward the outcome.

    This exists to show *why* the settlement price cannot be a calibration
    input. It is a diagnostic and is never bucketed.
    """

    sample_size: int
    average_settlement_probability: float | None = None
    average_distance_to_outcome: float | None = None
    share_within_five_points: float | None = None
    note: str = ""


CALIBRATION_METHOD_LEAD_TIME = "lead_time_history"
CALIBRATION_METHOD_SETTLEMENT = "settlement_last_trade_deprecated"


@dataclass(frozen=True)
class CalibrationSummary:
    """Venue calibration measured at fixed pre-resolution lead times.

    `method` and `is_validated` are load-bearing. A summary built from the
    deprecated settlement-price path reports `is_validated=False` and carries
    no curves, because a price that already knows the answer cannot measure
    foresight.
    """

    venue: str
    sample_size: int
    method: str = CALIBRATION_METHOD_SETTLEMENT
    is_validated: bool = False
    lead_times_hours: list[int] = field(default_factory=list)
    curves: list[CalibrationCurve] = field(default_factory=list)
    minimum_bucket_sample: int = 0
    minimum_curve_sample: int = 0
    resolved_markets_considered: int = 0
    markets_sampled: int = 0
    markets_without_history: int = 0
    sample_period_start: datetime | None = None
    sample_period_end: datetime | None = None
    # Which research categories the sampled contracts fell into. A venue-level
    # number measured mostly on sports settlements does not describe the venue's
    # macro book, so the composition travels with the result.
    sample_categories: dict[str, int] = field(default_factory=dict)
    research_share: float | None = None
    convergence: CalibrationConvergence | None = None
    observations: list[CalibrationObservation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
