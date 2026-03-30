from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.application.macro_service import MacroSnapshotRequest
from src.models.macro import (
    MacroCurveNode,
    MacroDivergenceRecord,
    MacroDivergenceSignal,
    MacroEventRecord,
    MacroLinkedPredictionMarket,
    MacroMetricRecord,
    MacroRatesPolicySummary,
    MacroSeriesHistory,
    MacroSeriesPoint,
    MacroSnapshotCard,
    MacroSnapshotPayload,
    MacroThemeComparison,
)


class MacroSnapshotRequestModel(BaseModel):
    region: str = "US"
    timeframe: str = "3M"
    theme: str = "all"
    comparison_region: str | None = None
    force_refresh: bool = False

    def to_domain(self) -> MacroSnapshotRequest:
        return MacroSnapshotRequest(
            region=self.region,
            timeframe=self.timeframe,
            theme=self.theme,
            comparison_region=self.comparison_region,
            force_refresh=self.force_refresh,
        )


class MacroSeriesPointModel(BaseModel):
    timestamp: datetime
    value: float
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, point: MacroSeriesPoint) -> "MacroSeriesPointModel":
        return cls(**point.__dict__)


class MacroMetricModel(BaseModel):
    metric_id: str
    label: str
    value: float | None = None
    display_value: str | None = None
    unit: str | None = None
    delta_value: float | None = None
    delta_display: str | None = None
    series_id: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_label: str | None = None
    comparison_value: float | None = None
    comparison_display_value: str | None = None
    comparison_delta_value: float | None = None
    comparison_delta_display: str | None = None
    gap_value: float | None = None
    gap_display: str | None = None

    @classmethod
    def from_domain(cls, row: MacroMetricRecord) -> "MacroMetricModel":
        return cls(**row.__dict__)


class MacroCurveNodeModel(BaseModel):
    tenor: str
    current_value: float | None = None
    prior_value: float | None = None
    change_bps: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroCurveNode) -> "MacroCurveNodeModel":
        return cls(**row.__dict__)


class MacroEventModel(BaseModel):
    event_id: str
    title: str
    category: str
    region: str
    scheduled_at: datetime
    relative_label: str | None = None
    importance: str
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroEventRecord) -> "MacroEventModel":
        return cls(**row.__dict__)


class MacroLinkedPredictionMarketModel(BaseModel):
    market_id: str
    venue: str
    title: str
    status: str
    category: str | None = None
    end_time: datetime | None = None
    current_probability: float | None = None
    probability_label: str | None = None
    recent_price_change: float | None = None
    change_display: str | None = None
    research_score: float | None = None
    macro_alignment: str
    macro_alignment_summary: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroLinkedPredictionMarket) -> "MacroLinkedPredictionMarketModel":
        return cls(**row.__dict__)


class MacroSeriesHistoryResponseModel(BaseModel):
    series_id: str
    title: str
    region: str
    unit: str | None = None
    frequency: str
    theme: str
    mode_tags: list[str] = Field(default_factory=list)
    points: list[MacroSeriesPointModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroSeriesHistory) -> "MacroSeriesHistoryResponseModel":
        payload = dict(row.__dict__)
        payload["points"] = [MacroSeriesPointModel.from_domain(point) for point in row.points]
        return cls(**payload)


class MacroSnapshotCardModel(BaseModel):
    card_id: str
    title: str
    subtitle: str | None = None
    summary: str
    mode_target: str
    target_theme: str | None = None
    metrics: list[MacroMetricModel] = Field(default_factory=list)
    linked_markets: list[MacroLinkedPredictionMarketModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroSnapshotCard) -> "MacroSnapshotCardModel":
        payload = dict(row.__dict__)
        payload["metrics"] = [MacroMetricModel.from_domain(metric) for metric in row.metrics]
        payload["linked_markets"] = [MacroLinkedPredictionMarketModel.from_domain(item) for item in row.linked_markets]
        return cls(**payload)


class MacroDivergenceSignalModel(BaseModel):
    role: str
    tone: str
    signal_score: float
    signal_score_display: str
    interpretation: str
    metric: MacroMetricModel
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroDivergenceSignal) -> "MacroDivergenceSignalModel":
        payload = dict(row.__dict__)
        payload["metric"] = MacroMetricModel.from_domain(row.metric)
        return cls(**payload)


class MacroDivergenceModel(BaseModel):
    divergence_id: str
    theme: str
    region: str
    headline: str
    summary: str
    score: float
    label: str
    metrics: list[MacroMetricModel] = Field(default_factory=list)
    series_ids: list[str] = Field(default_factory=list)
    primary_driver: MacroDivergenceSignalModel | None = None
    counter_signal: MacroDivergenceSignalModel | None = None
    research_focus: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_score: float | None = None
    score_gap: float | None = None
    score_gap_display: str | None = None

    @classmethod
    def from_domain(cls, row: MacroDivergenceRecord) -> "MacroDivergenceModel":
        payload = dict(row.__dict__)
        payload["metrics"] = [MacroMetricModel.from_domain(metric) for metric in row.metrics]
        payload["primary_driver"] = MacroDivergenceSignalModel.from_domain(row.primary_driver) if row.primary_driver is not None else None
        payload["counter_signal"] = MacroDivergenceSignalModel.from_domain(row.counter_signal) if row.counter_signal is not None else None
        return cls(**payload)


class MacroThemeComparisonModel(BaseModel):
    theme: str
    headline: str
    summary: str
    agreement_label: str
    metrics: list[MacroMetricModel] = Field(default_factory=list)
    linked_markets: list[MacroLinkedPredictionMarketModel] = Field(default_factory=list)
    primary_driver: MacroDivergenceSignalModel | None = None
    counter_signal: MacroDivergenceSignalModel | None = None
    divergence_score: float | None = None
    research_focus: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_summary: str | None = None

    @classmethod
    def from_domain(cls, row: MacroThemeComparison) -> "MacroThemeComparisonModel":
        payload = dict(row.__dict__)
        payload["metrics"] = [MacroMetricModel.from_domain(metric) for metric in row.metrics]
        payload["linked_markets"] = [MacroLinkedPredictionMarketModel.from_domain(item) for item in row.linked_markets]
        payload["primary_driver"] = MacroDivergenceSignalModel.from_domain(row.primary_driver) if row.primary_driver is not None else None
        payload["counter_signal"] = MacroDivergenceSignalModel.from_domain(row.counter_signal) if row.counter_signal is not None else None
        return cls(**payload)


class MacroRatesPolicySummaryModel(BaseModel):
    headline: str
    summary: str
    policy_metrics: list[MacroMetricModel] = Field(default_factory=list)
    curve_nodes: list[MacroCurveNodeModel] = Field(default_factory=list)
    real_yield_metrics: list[MacroMetricModel] = Field(default_factory=list)
    events: list[MacroEventModel] = Field(default_factory=list)
    linked_markets: list[MacroLinkedPredictionMarketModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_summary: str | None = None

    @classmethod
    def from_domain(cls, row: MacroRatesPolicySummary) -> "MacroRatesPolicySummaryModel":
        payload = dict(row.__dict__)
        payload["policy_metrics"] = [MacroMetricModel.from_domain(metric) for metric in row.policy_metrics]
        payload["curve_nodes"] = [MacroCurveNodeModel.from_domain(node) for node in row.curve_nodes]
        payload["real_yield_metrics"] = [MacroMetricModel.from_domain(metric) for metric in row.real_yield_metrics]
        payload["events"] = [MacroEventModel.from_domain(event) for event in row.events]
        payload["linked_markets"] = [MacroLinkedPredictionMarketModel.from_domain(item) for item in row.linked_markets]
        return cls(**payload)


class MacroSnapshotResponseModel(BaseModel):
    region: str
    timeframe: str
    theme: str
    comparison_region: str | None = None
    available_regions: list[str] = Field(default_factory=list)
    available_timeframes: list[str] = Field(default_factory=list)
    available_themes: list[str] = Field(default_factory=list)
    snapshot_cards: list[MacroSnapshotCardModel] = Field(default_factory=list)
    rates_policy: MacroRatesPolicySummaryModel | None = None
    cross_asset: list[MacroThemeComparisonModel] = Field(default_factory=list)
    top_divergences: list[MacroDivergenceModel] = Field(default_factory=list)
    upcoming_events: list[MacroEventModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: MacroSnapshotPayload) -> "MacroSnapshotResponseModel":
        payload = dict(row.__dict__)
        payload["snapshot_cards"] = [MacroSnapshotCardModel.from_domain(card) for card in row.snapshot_cards]
        payload["rates_policy"] = (
            MacroRatesPolicySummaryModel.from_domain(row.rates_policy) if row.rates_policy is not None else None
        )
        payload["cross_asset"] = [MacroThemeComparisonModel.from_domain(item) for item in row.cross_asset]
        payload["top_divergences"] = [MacroDivergenceModel.from_domain(item) for item in row.top_divergences]
        payload["upcoming_events"] = [MacroEventModel.from_domain(item) for item in row.upcoming_events]
        return cls(**payload)


class MacroDivergenceListResponseModel(BaseModel):
    region: str
    timeframe: str
    theme: str
    comparison_region: str | None = None
    divergences: list[MacroDivergenceModel] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls,
        *,
        region: str,
        timeframe: str,
        theme: str,
        comparison_region: str | None,
        rows: list[MacroDivergenceRecord],
    ) -> "MacroDivergenceListResponseModel":
        return cls(
            region=region,
            timeframe=timeframe,
            theme=theme,
            comparison_region=comparison_region,
            divergences=[MacroDivergenceModel.from_domain(row) for row in rows],
        )


class MacroEventsResponseModel(BaseModel):
    region: str
    events: list[MacroEventModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, *, region: str, rows: list[MacroEventRecord]) -> "MacroEventsResponseModel":
        return cls(region=region, events=[MacroEventModel.from_domain(row) for row in rows])
