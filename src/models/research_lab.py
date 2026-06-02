from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import pandas as pd

from src.analytics.research_returns import (
    PeriodReturn,
    ReturnStreamComparison,
    ReturnStreamMetrics,
    RollingReturnPoint,
)


ReturnValueKind = Literal["return", "level"]
ResolverCapability = Literal["return_leg", "benchmark", "lens", "overlay", "reference_only"]
StrategyLabHandoffAssetClass = Literal[
    "equity",
    "etf",
    "commodity",
    "crypto",
    "prediction_market",
    "macro",
    "fundamental",
    "rates",
    "fx",
    "other",
]
StrategyLabHandoffValueKind = Literal["return", "level", "probability", "price", "spread", "context"]
StrategyLabHandoffDefaultSide = Literal["long", "short", "long_yes", "long_no", "none"]


@dataclass(frozen=True)
class ResearchObjectReturnPoint:
    timestamp: str
    value: float


@dataclass(frozen=True)
class GammaResearchObject:
    object_id: str
    object_type: str
    display_name: str
    source_tab: str
    source_mode: str | None = None
    resolver_capabilities: list[ResolverCapability] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    constituents: list[dict[str, Any]] = field(default_factory=list)
    weights: list[dict[str, Any]] = field(default_factory=list)
    available_start: str | None = None
    available_end: str | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    return_points: list[ResearchObjectReturnPoint] = field(default_factory=list)


@dataclass(frozen=True)
class ImportedReturnStreamRequest:
    rows: list[dict[str, Any]]
    date_column: str
    value_column: str
    value_kind: ReturnValueKind = "return"
    name: str = "Imported Strategy"
    benchmark_column: str | None = None
    benchmark_value_kind: ReturnValueKind = "return"
    min_observations: int = 5


@dataclass(frozen=True)
class StrategyLabAnalysisResult:
    name: str
    value_kind: ReturnValueKind
    benchmark_column: str | None
    benchmark_value_kind: ReturnValueKind
    returns: pd.Series
    equity_curve: pd.Series
    drawdowns: pd.Series
    benchmark_returns: pd.Series
    benchmark_equity_curve: pd.Series
    metrics: ReturnStreamMetrics
    rolling_points: list[RollingReturnPoint]
    monthly_returns: list[PeriodReturn]
    annual_returns: list[PeriodReturn]
    warnings: list[str]
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str = "derived"


@dataclass(frozen=True)
class StrategyLabCompositionLeg:
    object: GammaResearchObject
    weight: float


@dataclass(frozen=True)
class StrategyLabCompositionRequest:
    name: str
    legs: list[StrategyLabCompositionLeg] = field(default_factory=list)
    lenses: list[GammaResearchObject] = field(default_factory=list)
    overlays: list[GammaResearchObject] = field(default_factory=list)
    benchmark_object: GammaResearchObject | None = None
    min_observations: int = 5


@dataclass(frozen=True)
class StrategyLabCompositionResult(StrategyLabAnalysisResult):
    leg_contributions: dict[str, float] = field(default_factory=dict)
    lenses: list[GammaResearchObject] = field(default_factory=list)
    overlays: list[GammaResearchObject] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyLabPortfolioLeg:
    label: str
    asset_class: str
    identifier: str = ""
    weight: float = 0.0
    value_kind: ReturnValueKind = "return"
    return_points: list[ResearchObjectReturnPoint] = field(default_factory=list)
    object: GammaResearchObject | None = None


@dataclass(frozen=True)
class CrossTabHandoffEntity:
    entity_type: str
    label: str
    normalized_id: str
    provider_id: str | None = None
    native_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrossTabHandoffTimeframe:
    label: str
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class StrategyLabHandoffEnvelope:
    source_tab: str
    source_mode: str | None
    intended_target_tab: str
    intended_target_mode: str | None
    selected_entity: CrossTabHandoffEntity
    resolver_capability: ResolverCapability
    asset_class: StrategyLabHandoffAssetClass
    value_kind: StrategyLabHandoffValueKind
    default_side: StrategyLabHandoffDefaultSide = "long"
    default_weight: float | None = None
    selected_timeframe: CrossTabHandoffTimeframe | None = None
    provider: str | None = None
    source: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    normalized_ids: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""


@dataclass(frozen=True)
class StrategyLabHandoffResolveRequest:
    handoff: StrategyLabHandoffEnvelope


@dataclass(frozen=True)
class StrategyLabResolvedHandoff:
    handoff_id: str
    envelope: StrategyLabHandoffEnvelope
    status: str
    resolved_capability: ResolverCapability
    composer_draft_leg: StrategyLabPortfolioLeg | None = None
    benchmark_draft: GammaResearchObject | None = None
    lens: GammaResearchObject | None = None
    overlay: GammaResearchObject | None = None
    date_coverage: CrossTabHandoffTimeframe | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class StrategyLabPortfolioCompositionRequest:
    name: str
    legs: list[StrategyLabPortfolioLeg] = field(default_factory=list)
    benchmark_symbol: str | None = "SPY"
    benchmark_object: GammaResearchObject | None = None
    lookback_days: int = 756
    min_observations: int = 5


@dataclass(frozen=True)
class ResearchComparisonLeg:
    label: str
    object_type: str
    returns: pd.Series | None = None
    saved_research_id: str | None = None


@dataclass(frozen=True)
class ResearchComparisonRequest:
    left: ResearchComparisonLeg
    right: ResearchComparisonLeg


@dataclass(frozen=True)
class ResearchComparisonResult:
    comparison: ReturnStreamComparison
    warnings: list[str]
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str = "derived"


@dataclass(frozen=True)
class SavedResearchItem:
    id: str
    schema_version: int
    object_type: str
    title: str
    notes: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = field(default_factory=list)
    source_provider: str = "gamma_saved_research"
    retrieved_at: datetime | None = None
    origin: str = "saved_research_store"
    transformation_note: str | None = None


@dataclass(frozen=True)
class SavedResearchCreateRequest:
    object_type: str
    title: str
    notes: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = "gamma_saved_research"
    origin: str = "research_service.saved_research.create"
    transformation_note: str | None = None
