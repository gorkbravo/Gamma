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
