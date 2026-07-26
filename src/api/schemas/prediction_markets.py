from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from src.application.request_limits import (
    MAX_PREDICTION_COMPARISON_LEGS,
    MAX_PREDICTION_MARKET_LIMIT,
    MAX_PREDICTION_MARKET_VENUES,
    MAX_REQUEST_TEXT_CHARS,
)
from src.application.prediction_market_service import PredictionMarketScreenerRequest
from src.models.prediction_markets import (
    CalibrationBucket,
    CalibrationObservation,
    CalibrationSummary,
    PredictionBasketSummary,
    PredictionComparisonLeg,
    PredictionHistoryStats,
    PredictionMarketComparison,
    PredictionMarketFreshness,
    PredictionMarketOutcome,
    PredictionMarketRecord,
    PredictionMarketScreenerResult,
    PredictionOutcomeSeries,
    PredictionPairAnalytics,
    PredictionProbabilityHistory,
    PredictionProbabilityPoint,
    PredictionSpreadPoint,
    PredictionVenueStatus,
    RelatedMarketRecord,
    WalletActivityRecord,
    WalletSummary,
)


class PredictionMarketScreenerRequestModel(BaseModel):
    query: str = Field(default="", max_length=MAX_REQUEST_TEXT_CHARS)
    venues: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list,
        max_length=MAX_PREDICTION_MARKET_VENUES,
    )
    status: str = Field(default="open", min_length=1, max_length=32)
    force_refresh: bool = False
    category: str | None = Field(default=None, max_length=64)
    min_volume: float | None = Field(default=None, ge=0)
    min_liquidity: float | None = Field(default=None, ge=0)
    min_open_interest: float | None = Field(default=None, ge=0)
    min_probability: float | None = Field(default=None, ge=0, le=1)
    max_probability: float | None = Field(default=None, ge=0, le=1)
    max_days_to_resolution: float | None = Field(default=None, ge=0)
    min_repricing_abs: float | None = Field(default=None, ge=0, le=1)
    sort_by: str = Field(default="research_rank", min_length=1, max_length=64)
    limit: int = Field(default=40, ge=1, le=MAX_PREDICTION_MARKET_LIMIT)

    def to_domain(self) -> PredictionMarketScreenerRequest:
        return PredictionMarketScreenerRequest(
            query=self.query,
            venues=list(self.venues),
            status=self.status,
            force_refresh=self.force_refresh,
            category=self.category,
            min_volume=self.min_volume,
            min_liquidity=self.min_liquidity,
            min_open_interest=self.min_open_interest,
            min_probability=self.min_probability,
            max_probability=self.max_probability,
            max_days_to_resolution=self.max_days_to_resolution,
            min_repricing_abs=self.min_repricing_abs,
            sort_by=self.sort_by,
            limit=self.limit,
        )


class PredictionMarketOutcomeModel(BaseModel):
    outcome_id: str
    label: str
    probability: float | None = None
    token_id: str | None = None
    resolved: bool | None = None
    winner: bool | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, outcome: PredictionMarketOutcome) -> "PredictionMarketOutcomeModel":
        return cls(**outcome.__dict__)


class PredictionMarketFreshnessModel(BaseModel):
    status: str
    is_stale: bool
    is_broken: bool
    reason: str | None = None
    last_history_point_at: datetime | None = None
    retrieval_age_seconds: float | None = None
    history_lag_seconds: float | None = None

    @classmethod
    def from_domain(cls, freshness: PredictionMarketFreshness) -> "PredictionMarketFreshnessModel":
        return cls(**freshness.__dict__)


class PredictionMarketModel(BaseModel):
    market_id: str
    venue: str
    title: str
    subtitle: str | None = None
    description: str | None = None
    status: str
    category: str | None = None
    event_id: str | None = None
    event_title: str | None = None
    series_id: str | None = None
    series_title: str | None = None
    provider_market_id: str
    provider_condition_id: str | None = None
    provider_event_id: str | None = None
    provider_series_id: str | None = None
    slug: str | None = None
    end_time: datetime | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    current_probability: float | None = None
    probability_label: str | None = None
    volume: float | None = None
    volume_24h: float | None = None
    liquidity: float | None = None
    open_interest: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    recent_price_change: float | None = None
    resolved_probability: float | None = None
    resolution_outcome: bool | None = None
    image_url: str | None = None
    resolution_source: str | None = None
    outcomes: list[PredictionMarketOutcomeModel] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    freshness: PredictionMarketFreshnessModel | None = None
    research_score: float | None = None
    research_rationale: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, market: PredictionMarketRecord) -> "PredictionMarketModel":
        payload = dict(market.__dict__)
        payload["outcomes"] = [PredictionMarketOutcomeModel.from_domain(outcome) for outcome in market.outcomes]
        payload["freshness"] = (
            PredictionMarketFreshnessModel.from_domain(market.freshness) if market.freshness is not None else None
        )
        return cls(**payload)


class PredictionVenueStatusModel(BaseModel):
    venue: str
    status: str
    message: str | None = None
    total_markets: int
    matched_markets: int
    visible_markets: int
    stale_markets: int
    broken_markets: int
    retrieved_at: datetime | None = None

    @classmethod
    def from_domain(cls, row: PredictionVenueStatus) -> "PredictionVenueStatusModel":
        return cls(**row.__dict__)


class PredictionMarketListResponseModel(BaseModel):
    markets: list[PredictionMarketModel] = Field(default_factory=list)
    venues: list[PredictionVenueStatusModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, result: PredictionMarketScreenerResult) -> "PredictionMarketListResponseModel":
        return cls(
            markets=[PredictionMarketModel.from_domain(market) for market in result.markets],
            venues=[PredictionVenueStatusModel.from_domain(venue) for venue in result.venues],
            warnings=list(result.warnings),
        )


class PredictionProbabilityPointModel(BaseModel):
    timestamp: datetime
    probability: float
    volume: float | None = None
    open_interest: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, point: PredictionProbabilityPoint) -> "PredictionProbabilityPointModel":
        return cls(**point.__dict__)


class PredictionHistoryStatsModel(BaseModel):
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

    @classmethod
    def from_domain(cls, stats: PredictionHistoryStats) -> "PredictionHistoryStatsModel":
        return cls(**stats.__dict__)


class PredictionProbabilityHistoryResponseModel(BaseModel):
    market_id: str
    points: list[PredictionProbabilityPointModel] = Field(default_factory=list)
    venue: str = ""
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
    stats: PredictionHistoryStatsModel | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, history: PredictionProbabilityHistory) -> "PredictionProbabilityHistoryResponseModel":
        payload = dict(history.__dict__)
        payload["points"] = [PredictionProbabilityPointModel.from_domain(point) for point in history.points]
        payload["stats"] = (
            PredictionHistoryStatsModel.from_domain(history.stats) if history.stats is not None else None
        )
        return cls(**payload)


class PredictionOutcomeSeriesModel(BaseModel):
    outcome_id: str
    label: str
    probability: float | None = None
    token_id: str | None = None
    points: list[PredictionProbabilityPointModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, series: PredictionOutcomeSeries) -> "PredictionOutcomeSeriesModel":
        payload = dict(series.__dict__)
        payload["points"] = [PredictionProbabilityPointModel.from_domain(point) for point in series.points]
        return cls(**payload)


class PredictionOutcomeSeriesResponseModel(BaseModel):
    market_id: str
    requested_range: str = "max"
    series: list[PredictionOutcomeSeriesModel] = Field(default_factory=list)


class PredictionComparisonRequestModel(BaseModel):
    market_ids: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        min_length=1,
        max_length=MAX_PREDICTION_COMPARISON_LEGS,
    )
    range_key: str = Field(default="max", min_length=1, max_length=8)
    resolution_minutes: int | None = Field(default=None, ge=1, le=1440)


class PredictionComparisonLegModel(BaseModel):
    market_id: str
    venue: str
    title: str
    outcome_label: str | None = None
    current_probability: float | None = None
    status: str
    end_time: datetime | None = None
    event_id: str | None = None
    event_title: str | None = None
    points: list[PredictionProbabilityPointModel] = Field(default_factory=list)
    stats: PredictionHistoryStatsModel | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str = ""
    origin: str = ""

    @classmethod
    def from_domain(cls, leg: PredictionComparisonLeg) -> "PredictionComparisonLegModel":
        payload = dict(leg.__dict__)
        payload["points"] = [PredictionProbabilityPointModel.from_domain(point) for point in leg.points]
        payload["stats"] = PredictionHistoryStatsModel.from_domain(leg.stats) if leg.stats is not None else None
        return cls(**payload)


class PredictionSpreadPointModel(BaseModel):
    timestamp: datetime
    spread: float

    @classmethod
    def from_domain(cls, point: PredictionSpreadPoint) -> "PredictionSpreadPointModel":
        return cls(**point.__dict__)


class PredictionPairAnalyticsModel(BaseModel):
    left_market_id: str
    right_market_id: str
    overlap_points: int
    overlap_start: datetime | None = None
    overlap_end: datetime | None = None
    current_spread: float | None = None
    mean_spread: float | None = None
    max_spread: float | None = None
    min_spread: float | None = None
    spread_volatility: float | None = None
    current_spread_percentile: float | None = None
    correlation: float | None = None
    spread_series: list[PredictionSpreadPointModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, pair: PredictionPairAnalytics) -> "PredictionPairAnalyticsModel":
        payload = dict(pair.__dict__)
        payload["spread_series"] = [
            PredictionSpreadPointModel.from_domain(point) for point in pair.spread_series
        ]
        return cls(**payload)


class PredictionBasketSummaryModel(BaseModel):
    leg_count: int
    probability_sum: float | None = None
    implied_overround: float | None = None
    same_event: bool = False
    same_venue: bool = False
    venues: list[str] = Field(default_factory=list)
    note: str | None = None

    @classmethod
    def from_domain(cls, basket: PredictionBasketSummary) -> "PredictionBasketSummaryModel":
        return cls(**basket.__dict__)


class PredictionMarketComparisonResponseModel(BaseModel):
    requested_range: str
    effective_resolution_minutes: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    legs: list[PredictionComparisonLegModel] = Field(default_factory=list)
    pairs: list[PredictionPairAnalyticsModel] = Field(default_factory=list)
    basket: PredictionBasketSummaryModel | None = None
    warnings: list[str] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, result: PredictionMarketComparison) -> "PredictionMarketComparisonResponseModel":
        payload = dict(result.__dict__)
        payload["legs"] = [PredictionComparisonLegModel.from_domain(leg) for leg in result.legs]
        payload["pairs"] = [PredictionPairAnalyticsModel.from_domain(pair) for pair in result.pairs]
        payload["basket"] = (
            PredictionBasketSummaryModel.from_domain(result.basket) if result.basket is not None else None
        )
        return cls(**payload)


class WalletActivityModel(BaseModel):
    participant_id: str
    display_name: str
    venue: str
    side: str
    outcome_label: str | None = None
    trade_count: int
    total_size: float
    average_price: float | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    current_edge: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: WalletActivityRecord) -> "WalletActivityModel":
        return cls(**row.__dict__)


class WalletSummaryResponseModel(BaseModel):
    market_id: str
    venue: str
    concentration_hhi: float | None = None
    top_participant_share: float | None = None
    total_trades: int
    total_notional: float
    participants: list[WalletActivityModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, summary: WalletSummary) -> "WalletSummaryResponseModel":
        payload = dict(summary.__dict__)
        payload["participants"] = [WalletActivityModel.from_domain(row) for row in summary.participants]
        return cls(**payload)


class RelatedMarketModel(BaseModel):
    market_id: str
    venue: str
    title: str
    probability: float | None = None
    price_gap: float | None = None
    relationship: str
    note: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: RelatedMarketRecord) -> "RelatedMarketModel":
        return cls(**row.__dict__)


class RelatedMarketListResponseModel(BaseModel):
    market_id: str
    related: list[RelatedMarketModel] = Field(default_factory=list)


class CalibrationBucketModel(BaseModel):
    label: str
    sample_size: int
    average_probability: float | None = None
    realized_frequency: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, bucket: CalibrationBucket) -> "CalibrationBucketModel":
        return cls(**bucket.__dict__)


class CalibrationObservationModel(BaseModel):
    market_id: str
    title: str
    probability: float
    outcome: bool
    settled_at: datetime | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, observation: CalibrationObservation) -> "CalibrationObservationModel":
        return cls(**observation.__dict__)


class CalibrationSummaryResponseModel(BaseModel):
    venue: str
    sample_size: int
    buckets: list[CalibrationBucketModel] = Field(default_factory=list)
    observations: list[CalibrationObservationModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, summary: CalibrationSummary) -> "CalibrationSummaryResponseModel":
        payload = dict(summary.__dict__)
        payload["buckets"] = [CalibrationBucketModel.from_domain(bucket) for bucket in summary.buckets]
        payload["observations"] = [
            CalibrationObservationModel.from_domain(observation) for observation in summary.observations
        ]
        return cls(**payload)
