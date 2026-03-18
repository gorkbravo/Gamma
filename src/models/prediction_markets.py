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
