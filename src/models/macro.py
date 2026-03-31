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
    why_now: str | None = None
    signal_label: str | None = None
    drilldown_label: str | None = None
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    linked_markets: list["MacroLinkedPredictionMarket"] = field(default_factory=list)
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
class MacroEventReactionSignal:
    role: str
    tone: str
    signal_score: float
    signal_score_display: str
    move_value: float | None
    move_display: str | None
    before_display_value: str | None
    after_display_value: str | None
    interpretation: str
    metric: MacroMetricRecord
    observed_at: datetime | None = None
    observed_label: str | None = None
    lag_days: float | None = None
    lag_label: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroEventStudy:
    study_id: str
    theme: str
    timing: str
    headline: str
    summary: str
    window_label: str
    event: MacroEventRecord
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_start_label: str | None = None
    window_end_label: str | None = None
    reactions: list[MacroEventReactionSignal] = field(default_factory=list)
    primary_reaction: MacroEventReactionSignal | None = None
    counter_reaction: MacroEventReactionSignal | None = None
    coherence: "MacroCoherenceProfile" | None = None
    linked_markets: list["MacroLinkedPredictionMarket"] = field(default_factory=list)
    research_focus: str | None = None
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
    primary_driver: "MacroDivergenceSignal" | None = None
    counter_signal: "MacroDivergenceSignal" | None = None
    coherence: "MacroCoherenceProfile" | None = None
    research_focus: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_score: float | None = None
    score_gap: float | None = None
    score_gap_display: str | None = None


@dataclass(frozen=True)
class MacroLinkedPredictionMarket:
    market_id: str
    venue: str
    title: str
    status: str
    category: str | None
    end_time: datetime | None
    current_probability: float | None
    probability_label: str | None = None
    recent_price_change: float | None = None
    change_display: str | None = None
    research_score: float | None = None
    macro_stance: str | None = None
    macro_alignment: str = "mixed"
    macro_alignment_summary: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroDivergenceSignal:
    role: str
    tone: str
    signal_score: float
    signal_score_display: str
    interpretation: str
    metric: MacroMetricRecord
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroLeadLagSignal:
    label: str
    series_id: str | None = None
    role: str = ""
    tone: str = "mixed"
    signal_score: float = 0.0
    signal_score_display: str | None = None
    move_value: float | None = None
    move_display: str | None = None
    observed_at: datetime | None = None
    observed_label: str | None = None
    lag_days: float | None = None
    lag_label: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroCoherenceProfile:
    theme: str
    direction_label: str
    coherence_label: str
    supporting_signals: int
    opposing_signals: int
    neutral_signals: int
    lead_signal: MacroLeadLagSignal | None = None
    lag_signal: MacroLeadLagSignal | None = None
    lag_span_days: float | None = None
    lag_span_display: str | None = None
    summary: str = ""
    methodology: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroThemeComparison:
    theme: str
    headline: str
    summary: str
    agreement_label: str
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    linked_markets: list[MacroLinkedPredictionMarket] = field(default_factory=list)
    primary_driver: MacroDivergenceSignal | None = None
    counter_signal: MacroDivergenceSignal | None = None
    coherence: MacroCoherenceProfile | None = None
    divergence_score: float | None = None
    research_focus: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    comparison_region: str | None = None
    comparison_summary: str | None = None


@dataclass(frozen=True)
class MacroPolicyMeetingPathRow:
    meeting_id: str
    title: str
    scheduled_at: datetime
    meeting_index: int
    implied_policy_rate: float | None
    implied_policy_rate_display: str | None = None
    incremental_change_bps: float | None = None
    incremental_change_display: str | None = None
    cumulative_change_bps: float | None = None
    cumulative_change_display: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroPolicyMeetingPathSummary:
    headline: str
    summary: str
    window_label: str
    metrics: list[MacroMetricRecord] = field(default_factory=list)
    meetings: list[MacroPolicyMeetingPathRow] = field(default_factory=list)
    research_focus: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroRatesPolicySummary:
    headline: str
    summary: str
    policy_metrics: list[MacroMetricRecord] = field(default_factory=list)
    curve_nodes: list[MacroCurveNode] = field(default_factory=list)
    real_yield_metrics: list[MacroMetricRecord] = field(default_factory=list)
    events: list[MacroEventRecord] = field(default_factory=list)
    linked_markets: list[MacroLinkedPredictionMarket] = field(default_factory=list)
    path_headline: str | None = None
    path_summary: str | None = None
    path_metrics: list[MacroMetricRecord] = field(default_factory=list)
    path_research_focus: str | None = None
    expectation_metrics: list[MacroMetricRecord] = field(default_factory=list)
    expectation_summary: str | None = None
    expectation_caveat: str | None = None
    meeting_path: MacroPolicyMeetingPathSummary | None = None
    market_alignment_label: str | None = None
    market_alignment_summary: str | None = None
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
    focus_items: list["MacroSnapshotFocusItem"] = field(default_factory=list)
    snapshot_cards: list[MacroSnapshotCard] = field(default_factory=list)
    rates_policy: MacroRatesPolicySummary | None = None
    cross_asset: list[MacroThemeComparison] = field(default_factory=list)
    top_divergences: list[MacroDivergenceRecord] = field(default_factory=list)
    event_studies: list[MacroEventStudy] = field(default_factory=list)
    upcoming_events: list[MacroEventRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class MacroSnapshotFocusItem:
    focus_id: str
    title: str
    summary: str
    why_now: str
    mode_target: str
    target_theme: str | None = None
    signal_label: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
