from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MacroSeriesPoint:
    timestamp: datetime
    value: float
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroMetricRecord:
    metric_id: str
    label: str
    value: float | None
    display_value: str | None = None
    unit: str | None = None
    delta_value: float | None = None
    delta_display: str | None = None
    series_id: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_label: str | None = None
    comparison_value: float | None = None
    comparison_display_value: str | None = None
    comparison_delta_value: float | None = None
    comparison_delta_display: str | None = None
    gap_value: float | None = None
    gap_display: str | None = None


@dataclass(frozen=True)
class MacroSeriesHistory:
    series_id: str
    title: str
    region: str
    unit: str | None
    frequency: str
    theme: str
    mode_tags: list[str] = field(default_factory=list)
    points: list[MacroSeriesPoint] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroCurveNode:
    tenor: str
    current_value: float | None
    prior_value: float | None
    change_bps: float | None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroSnapshotCard:
    card_id: str
    title: str
    subtitle: str | None
    summary: str
    mode_target: str
    target_theme: str | None
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroEventRecord:
    event_id: str
    title: str
    category: str
    region: str
    scheduled_at: datetime
    relative_label: str | None
    importance: str
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroDivergenceRecord:
    divergence_id: str
    theme: str
    region: str
    headline: str
    summary: str
    score: float
    label: str
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    series_ids: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_score: float | None = None
    score_gap: float | None = None
    score_gap_display: str | None = None


@dataclass(frozen=True)
class MacroThemeComparison:
    theme: str
    headline: str
    summary: str
    agreement_label: str
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_summary: str | None = None


@dataclass(frozen=True)
class MacroRatesPolicySummary:
    headline: str
    summary: str
    policy_metrics: list[MacroMetricRecord] = field(default_factory=list)
    curve_nodes: list[MacroCurveNode] = field(default_factory=list)
    real_yield_metrics: list[MacroMetricRecord] = field(default_factory=list)
    events: list[MacroEventRecord] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_summary: str | None = None


@dataclass(frozen=True)
class MacroSnapshotPayload:
    region: str
    timeframe: str
    theme: str
    comparison_region: str | None = None
    available_regions: list[str] = field(default_factory=list)
    available_timeframes: list[str] = field(default_factory=list)
    available_themes: list[str] = field(default_factory=list)
    snapshot_cards: list[MacroSnapshotCard] = field(default_factory=list)
    rates_policy: MacroRatesPolicySummary | None = None
    cross_asset: list[MacroThemeComparison] = field(default_factory=list)
    top_divergences: list[MacroDivergenceRecord] = field(default_factory=list)
    upcoming_events: list[MacroEventRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
