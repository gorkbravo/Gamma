from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from src.analytics.risk_metrics import max_drawdown, realized_vol
from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.request_limits import (
    MAX_REQUEST_TEXT_CHARS,
    MAX_RISK_LOOKBACK_DAYS,
    MAX_STRATEGY_LAB_ROW_FIELDS,
    MAX_STRATEGY_LAB_ROW_TEXT_CHARS,
    MAX_STRATEGY_LAB_ROWS,
)
from src.application.research_service import ResearchAnalysisResult
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.research_lab import (
    GammaResearchObject,
    ImportedReturnStreamRequest,
    CrossTabHandoffEntity,
    CrossTabHandoffTimeframe,
    ResearchComparisonLeg,
    ResearchComparisonRequest,
    ResearchComparisonResult,
    ResearchObjectReturnPoint,
    SavedResearchCreateRequest,
    SavedResearchItem,
    StrategyLabAnalysisResult,
    StrategyLabCompositionLeg,
    StrategyLabCompositionRequest,
    StrategyLabCompositionResult,
    StrategyLabHandoffEnvelope,
    StrategyLabHandoffResolveRequest,
    StrategyLabResolvedHandoff,
    StrategyLabPortfolioCompositionRequest,
    StrategyLabPortfolioLeg,
)
from src.models.research_overview import (
    ResearchOverviewCoverage,
    ResearchOverviewMetricOption,
    ResearchOverviewMetrics,
    ResearchOverviewNode,
    ResearchOverviewRankItem,
    ResearchOverviewRankings,
    ResearchOverviewResult,
    ResearchOverviewSortOption,
    ResearchOverviewSummary,
    ResearchOverviewUniverse,
    ResearchOverviewUniverseInstrument,
)


class SyntheticPositionModel(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    weight: float
    instrument_id: str | None = Field(default=None, max_length=96)
    display_symbol: str | None = Field(default=None, max_length=32)
    sec_type: str | None = Field(default=None, max_length=16)
    currency: str | None = Field(default=None, max_length=8)
    exchange: str | None = Field(default=None, max_length=32)
    primary_exchange: str | None = Field(default=None, max_length=32)
    provider: str | None = Field(default=None, max_length=64)
    provider_id: str | None = Field(default=None, max_length=128)

    def to_domain(self) -> SyntheticPosition:
        return SyntheticPosition(
            symbol=self.symbol,
            weight=self.weight,
            instrument_id=self.instrument_id,
            display_symbol=self.display_symbol,
            sec_type=self.sec_type,
            currency=self.currency,
            exchange=self.exchange,
            primary_exchange=self.primary_exchange,
            provider=self.provider,
            provider_id=self.provider_id,
        )


class ResearchAnalyzeRequestModel(BaseModel):
    scope_type: ResearchScopeType
    primary_symbol: str = Field(default="", max_length=32)
    synthetic_positions: list[SyntheticPositionModel] = Field(default_factory=list, max_length=100)
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=32)
    lookback_days: int = Field(default=252, ge=20, le=MAX_RISK_LOOKBACK_DAYS)


class StrategyLabAnalyzeRequestModel(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_STRATEGY_LAB_ROWS)
    date_column: str = Field(default="date", min_length=1, max_length=64)
    value_column: str = Field(default="return", min_length=1, max_length=64)
    value_kind: Literal["return", "level"] = "return"
    name: str = Field(default="Imported Strategy", min_length=1, max_length=128)
    benchmark_column: str | None = Field(default=None, max_length=64)
    benchmark_value_kind: Literal["return", "level"] = "return"
    min_observations: int = Field(default=5, ge=2, le=MAX_RISK_LOOKBACK_DAYS)

    @field_validator("rows")
    @classmethod
    def _bound_row_shape(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for index, row in enumerate(rows):
            if len(row) > MAX_STRATEGY_LAB_ROW_FIELDS:
                raise ValueError(
                    f"rows[{index}] has too many fields; maximum is {MAX_STRATEGY_LAB_ROW_FIELDS}"
                )
            for key, value in row.items():
                if len(str(key)) > MAX_REQUEST_TEXT_CHARS:
                    raise ValueError(
                        f"rows[{index}] contains a field name longer than {MAX_REQUEST_TEXT_CHARS} characters"
                    )
                if isinstance(value, str) and len(value) > MAX_STRATEGY_LAB_ROW_TEXT_CHARS:
                    raise ValueError(
                        f"rows[{index}].{key} is longer than {MAX_STRATEGY_LAB_ROW_TEXT_CHARS} characters"
                    )
        return rows

    def to_domain(self) -> ImportedReturnStreamRequest:
        return ImportedReturnStreamRequest(
            rows=[dict(row) for row in self.rows],
            date_column=self.date_column,
            value_column=self.value_column,
            value_kind=self.value_kind,
            name=self.name,
            benchmark_column=self.benchmark_column,
            benchmark_value_kind=self.benchmark_value_kind,
            min_observations=max(int(self.min_observations), 2),
        )


class ResearchObjectReturnPointModel(BaseModel):
    timestamp: datetime
    value: float

    def to_domain(self) -> ResearchObjectReturnPoint:
        return ResearchObjectReturnPoint(timestamp=self.timestamp.isoformat(), value=float(self.value))

    @classmethod
    def from_domain(cls, row: ResearchObjectReturnPoint) -> "ResearchObjectReturnPointModel":
        return cls(timestamp=row.timestamp, value=float(row.value))


class GammaResearchObjectModel(BaseModel):
    object_id: str
    object_type: str
    display_name: str
    source_tab: str
    source_mode: str | None = None
    resolver_capabilities: list[Literal["return_leg", "benchmark", "lens", "overlay", "reference_only"]] = Field(
        default_factory=list
    )
    symbols: list[str] = Field(default_factory=list)
    constituents: list[dict[str, Any]] = Field(default_factory=list)
    weights: list[dict[str, Any]] = Field(default_factory=list)
    available_start: str | None = None
    available_end: str | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    return_points: list[ResearchObjectReturnPointModel] = Field(default_factory=list)

    def to_domain(self) -> GammaResearchObject:
        return GammaResearchObject(
            object_id=self.object_id,
            object_type=self.object_type,
            display_name=self.display_name,
            source_tab=self.source_tab,
            source_mode=self.source_mode,
            resolver_capabilities=list(self.resolver_capabilities),
            symbols=list(self.symbols),
            constituents=[dict(row) for row in self.constituents],
            weights=[dict(row) for row in self.weights],
            available_start=self.available_start,
            available_end=self.available_end,
            provider_summary=self.provider_summary,
            provenance=dict(self.provenance),
            warnings=list(self.warnings),
            return_points=[point.to_domain() for point in self.return_points],
        )

    @classmethod
    def from_domain(cls, row: GammaResearchObject) -> "GammaResearchObjectModel":
        return cls(
            object_id=row.object_id,
            object_type=row.object_type,
            display_name=row.display_name,
            source_tab=row.source_tab,
            source_mode=row.source_mode,
            resolver_capabilities=list(row.resolver_capabilities),
            symbols=list(row.symbols),
            constituents=[dict(item) for item in row.constituents],
            weights=[dict(item) for item in row.weights],
            available_start=row.available_start,
            available_end=row.available_end,
            provider_summary=row.provider_summary,
            provenance=dict(row.provenance),
            warnings=list(row.warnings),
            return_points=[ResearchObjectReturnPointModel.from_domain(point) for point in row.return_points],
        )


class StrategyLabCompositionLegModel(BaseModel):
    object: GammaResearchObjectModel
    weight: float

    def to_domain(self) -> StrategyLabCompositionLeg:
        return StrategyLabCompositionLeg(object=self.object.to_domain(), weight=float(self.weight))


class StrategyLabCompositionRequestModel(BaseModel):
    name: str = Field(default="Gamma Research Composition", min_length=1, max_length=128)
    legs: list[StrategyLabCompositionLegModel] = Field(default_factory=list, max_length=100)
    lenses: list[GammaResearchObjectModel] = Field(default_factory=list, max_length=100)
    overlays: list[GammaResearchObjectModel] = Field(default_factory=list, max_length=100)
    benchmark_object: GammaResearchObjectModel | None = None
    min_observations: int = Field(default=5, ge=2, le=MAX_RISK_LOOKBACK_DAYS)

    def to_domain(self) -> StrategyLabCompositionRequest:
        return StrategyLabCompositionRequest(
            name=self.name,
            legs=[leg.to_domain() for leg in self.legs],
            lenses=[item.to_domain() for item in self.lenses],
            overlays=[item.to_domain() for item in self.overlays],
            benchmark_object=self.benchmark_object.to_domain() if self.benchmark_object is not None else None,
            min_observations=max(int(self.min_observations), 2),
        )


class StrategyLabPortfolioLegModel(BaseModel):
    label: str = Field(default="", max_length=128)
    asset_class: str = Field(default="equity", min_length=1, max_length=48)
    identifier: str = Field(default="", max_length=160)
    weight: float
    value_kind: Literal["return", "level"] = "return"
    return_points: list[ResearchObjectReturnPointModel] = Field(default_factory=list, max_length=MAX_STRATEGY_LAB_ROWS)
    object: GammaResearchObjectModel | None = None

    def to_domain(self) -> StrategyLabPortfolioLeg:
        return StrategyLabPortfolioLeg(
            label=self.label,
            asset_class=self.asset_class,
            identifier=self.identifier,
            weight=float(self.weight),
            value_kind=self.value_kind,
            return_points=[point.to_domain() for point in self.return_points],
            object=self.object.to_domain() if self.object is not None else None,
        )

    @classmethod
    def from_domain(cls, row: StrategyLabPortfolioLeg) -> "StrategyLabPortfolioLegModel":
        return cls(
            label=row.label,
            asset_class=row.asset_class,
            identifier=row.identifier,
            weight=row.weight,
            value_kind=row.value_kind,
            return_points=[ResearchObjectReturnPointModel.from_domain(point) for point in row.return_points],
            object=GammaResearchObjectModel.from_domain(row.object) if row.object is not None else None,
        )


class CrossTabHandoffEntityModel(BaseModel):
    entity_type: str = Field(min_length=1, max_length=96)
    label: str = Field(min_length=1, max_length=256)
    normalized_id: str = Field(min_length=1, max_length=256)
    provider_id: str | None = Field(default=None, max_length=256)
    native_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_domain(self) -> CrossTabHandoffEntity:
        return CrossTabHandoffEntity(
            entity_type=self.entity_type,
            label=self.label,
            normalized_id=self.normalized_id,
            provider_id=self.provider_id,
            native_id=self.native_id,
            metadata=dict(self.metadata),
        )

    @classmethod
    def from_domain(cls, row: CrossTabHandoffEntity) -> "CrossTabHandoffEntityModel":
        return cls(**row.__dict__)


class CrossTabHandoffTimeframeModel(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    start: str | None = Field(default=None, max_length=96)
    end: str | None = Field(default=None, max_length=96)

    def to_domain(self) -> CrossTabHandoffTimeframe:
        return CrossTabHandoffTimeframe(label=self.label, start=self.start, end=self.end)

    @classmethod
    def from_domain(cls, row: CrossTabHandoffTimeframe) -> "CrossTabHandoffTimeframeModel":
        return cls(**row.__dict__)


class StrategyLabHandoffEnvelopeModel(BaseModel):
    source_tab: str = Field(min_length=1, max_length=96)
    source_mode: str | None = Field(default=None, max_length=96)
    intended_target_tab: str = Field(default="strategy_lab", min_length=1, max_length=96)
    intended_target_mode: str | None = Field(default="composer", max_length=96)
    selected_entity: CrossTabHandoffEntityModel
    resolver_capability: Literal["return_leg", "benchmark", "lens", "overlay", "reference_only"] = "return_leg"
    asset_class: Literal[
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
    ] = "other"
    value_kind: Literal["return", "level", "probability", "price", "spread", "context"] = "context"
    default_side: Literal["long", "short", "long_yes", "long_no", "none"] = "long"
    default_weight: float | None = None
    selected_timeframe: CrossTabHandoffTimeframeModel | None = None
    provider: str | None = Field(default=None, max_length=96)
    source: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list, max_length=64)
    normalized_ids: dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default="", max_length=96)

    def to_domain(self) -> StrategyLabHandoffEnvelope:
        return StrategyLabHandoffEnvelope(
            source_tab=self.source_tab,
            source_mode=self.source_mode,
            intended_target_tab=self.intended_target_tab,
            intended_target_mode=self.intended_target_mode,
            selected_entity=self.selected_entity.to_domain(),
            resolver_capability=self.resolver_capability,
            asset_class=self.asset_class,
            value_kind=self.value_kind,
            default_side=self.default_side,
            default_weight=self.default_weight,
            selected_timeframe=self.selected_timeframe.to_domain() if self.selected_timeframe is not None else None,
            provider=self.provider,
            source=dict(self.source) if self.source is not None else None,
            warnings=list(self.warnings),
            normalized_ids=dict(self.normalized_ids),
            timestamp=self.timestamp,
        )

    @classmethod
    def from_domain(cls, row: StrategyLabHandoffEnvelope) -> "StrategyLabHandoffEnvelopeModel":
        return cls(
            source_tab=row.source_tab,
            source_mode=row.source_mode,
            intended_target_tab=row.intended_target_tab,
            intended_target_mode=row.intended_target_mode,
            selected_entity=CrossTabHandoffEntityModel.from_domain(row.selected_entity),
            resolver_capability=row.resolver_capability,
            asset_class=row.asset_class,
            value_kind=row.value_kind,
            default_side=row.default_side,
            default_weight=row.default_weight,
            selected_timeframe=(
                CrossTabHandoffTimeframeModel.from_domain(row.selected_timeframe)
                if row.selected_timeframe is not None
                else None
            ),
            provider=row.provider,
            source=dict(row.source) if row.source is not None else None,
            warnings=list(row.warnings),
            normalized_ids=dict(row.normalized_ids),
            timestamp=row.timestamp,
        )


class StrategyLabHandoffResolveRequestModel(BaseModel):
    handoff: StrategyLabHandoffEnvelopeModel

    def to_domain(self) -> StrategyLabHandoffResolveRequest:
        return StrategyLabHandoffResolveRequest(handoff=self.handoff.to_domain())


class StrategyLabResolvedHandoffModel(BaseModel):
    handoff_id: str
    envelope: StrategyLabHandoffEnvelopeModel
    status: str
    resolved_capability: Literal["return_leg", "benchmark", "lens", "overlay", "reference_only"]
    composer_draft_leg: StrategyLabPortfolioLegModel | None = None
    benchmark_draft: GammaResearchObjectModel | None = None
    lens: GammaResearchObjectModel | None = None
    overlay: GammaResearchObjectModel | None = None
    date_coverage: CrossTabHandoffTimeframeModel | None = None
    provider_summary: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unsupported_reason: str | None = None

    @classmethod
    def from_domain(cls, row: StrategyLabResolvedHandoff) -> "StrategyLabResolvedHandoffModel":
        return cls(
            handoff_id=row.handoff_id,
            envelope=StrategyLabHandoffEnvelopeModel.from_domain(row.envelope),
            status=row.status,
            resolved_capability=row.resolved_capability,
            composer_draft_leg=(
                StrategyLabPortfolioLegModel.from_domain(row.composer_draft_leg)
                if row.composer_draft_leg is not None
                else None
            ),
            benchmark_draft=GammaResearchObjectModel.from_domain(row.benchmark_draft) if row.benchmark_draft else None,
            lens=GammaResearchObjectModel.from_domain(row.lens) if row.lens else None,
            overlay=GammaResearchObjectModel.from_domain(row.overlay) if row.overlay else None,
            date_coverage=CrossTabHandoffTimeframeModel.from_domain(row.date_coverage) if row.date_coverage else None,
            provider_summary=row.provider_summary,
            provenance=dict(row.provenance),
            warnings=list(row.warnings),
            unsupported_reason=row.unsupported_reason,
        )


class StrategyLabPortfolioCompositionRequestModel(BaseModel):
    name: str = Field(default="Strategy Lab Portfolio", min_length=1, max_length=128)
    legs: list[StrategyLabPortfolioLegModel] = Field(default_factory=list, max_length=100)
    lenses: list[GammaResearchObjectModel] = Field(default_factory=list, max_length=100)
    overlays: list[GammaResearchObjectModel] = Field(default_factory=list, max_length=100)
    benchmark_symbol: str | None = Field(default="SPY", max_length=32)
    benchmark_object: GammaResearchObjectModel | None = None
    lookback_days: int = Field(default=756, ge=20, le=MAX_RISK_LOOKBACK_DAYS)
    min_observations: int = Field(default=5, ge=2, le=MAX_RISK_LOOKBACK_DAYS)

    def to_domain(self) -> StrategyLabPortfolioCompositionRequest:
        return StrategyLabPortfolioCompositionRequest(
            name=self.name,
            legs=[leg.to_domain() for leg in self.legs],
            lenses=[item.to_domain() for item in self.lenses],
            overlays=[item.to_domain() for item in self.overlays],
            benchmark_symbol=self.benchmark_symbol,
            benchmark_object=self.benchmark_object.to_domain() if self.benchmark_object is not None else None,
            lookback_days=int(self.lookback_days),
            min_observations=max(int(self.min_observations), 2),
        )


class ResearchReturnMetricsModel(BaseModel):
    total_return: float | None = None
    annual_return: float | None = None
    annual_volatility: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: float | None = None
    max_drawdown_duration: int | None = None
    observation_count: int = 0
    frequency: str = "unknown"
    periods_per_year: float = 252.0
    start_date: datetime | None = None
    end_date: datetime | None = None
    benchmark_beta: float | None = None
    benchmark_correlation: float | None = None
    upside_capture: float | None = None
    downside_capture: float | None = None

    @classmethod
    def from_domain(cls, row) -> "ResearchReturnMetricsModel":
        return cls(**row.__dict__)


class ResearchRollingPointModel(BaseModel):
    timestamp: datetime
    rolling_return: float | None = None
    rolling_volatility: float | None = None
    rolling_beta: float | None = None
    rolling_correlation: float | None = None

    @classmethod
    def from_domain(cls, row) -> "ResearchRollingPointModel":
        return cls(**row.__dict__)


class ResearchPeriodReturnModel(BaseModel):
    period: str
    value: float | None = None

    @classmethod
    def from_domain(cls, row) -> "ResearchPeriodReturnModel":
        return cls(**row.__dict__)


class StrategyLabAnalyzeResponseModel(BaseModel):
    name: str
    value_kind: str
    benchmark_column: str | None = None
    benchmark_value_kind: str
    metrics: ResearchReturnMetricsModel
    returns_points: list[TimeSeriesPoint] = Field(default_factory=list)
    equity_curve_points: list[TimeSeriesPoint] = Field(default_factory=list)
    drawdown_points: list[TimeSeriesPoint] = Field(default_factory=list)
    benchmark_points: list[TimeSeriesPoint] = Field(default_factory=list)
    benchmark_equity_curve_points: list[TimeSeriesPoint] = Field(default_factory=list)
    rolling_points: list[ResearchRollingPointModel] = Field(default_factory=list)
    monthly_returns: list[ResearchPeriodReturnModel] = Field(default_factory=list)
    annual_returns: list[ResearchPeriodReturnModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str

    @classmethod
    def from_domain(cls, row: StrategyLabAnalysisResult) -> "StrategyLabAnalyzeResponseModel":
        return cls(
            name=row.name,
            value_kind=row.value_kind,
            benchmark_column=row.benchmark_column,
            benchmark_value_kind=row.benchmark_value_kind,
            metrics=ResearchReturnMetricsModel.from_domain(row.metrics),
            returns_points=series_to_points(row.returns),
            equity_curve_points=series_to_points(row.equity_curve),
            drawdown_points=series_to_points(row.drawdowns),
            benchmark_points=series_to_points(row.benchmark_returns),
            benchmark_equity_curve_points=series_to_points(row.benchmark_equity_curve),
            rolling_points=[ResearchRollingPointModel.from_domain(item) for item in row.rolling_points],
            monthly_returns=[ResearchPeriodReturnModel.from_domain(item) for item in row.monthly_returns],
            annual_returns=[ResearchPeriodReturnModel.from_domain(item) for item in row.annual_returns],
            warnings=list(row.warnings),
            source_provider=row.source_provider,
            retrieved_at=row.retrieved_at,
            origin=row.origin,
            transformation_note=row.transformation_note,
            freshness_label=row.freshness_label,
        )


class StrategyLabCompositionResponseModel(StrategyLabAnalyzeResponseModel):
    leg_contributions: dict[str, float] = Field(default_factory=dict)
    lenses: list[GammaResearchObjectModel] = Field(default_factory=list)
    overlays: list[GammaResearchObjectModel] = Field(default_factory=list)
    alignment_diagnostics: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, row: StrategyLabCompositionResult) -> "StrategyLabCompositionResponseModel":
        base = StrategyLabAnalyzeResponseModel.from_domain(row)
        return cls(
            **base.model_dump(),
            leg_contributions=dict(row.leg_contributions),
            lenses=[GammaResearchObjectModel.from_domain(item) for item in row.lenses],
            overlays=[GammaResearchObjectModel.from_domain(item) for item in row.overlays],
            alignment_diagnostics=dict(row.alignment_diagnostics),
        )


class StrategyLabBookValidationResponseModel(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usable_leg_count: int = 0
    requested_leg_count: int = 0
    aligned_observation_count: int = 0
    min_observations: int = 2
    alignment_diagnostics: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime
    origin: str = "research_service.strategy_lab.validate_book"

    @classmethod
    def from_domain(cls, row) -> "StrategyLabBookValidationResponseModel":
        return cls(
            valid=row.valid,
            errors=list(row.errors),
            warnings=list(row.warnings),
            usable_leg_count=row.usable_leg_count,
            requested_leg_count=row.requested_leg_count,
            aligned_observation_count=row.aligned_observation_count,
            min_observations=row.min_observations,
            alignment_diagnostics=dict(row.alignment_diagnostics),
            retrieved_at=row.retrieved_at,
            origin=row.origin,
        )


class ResearchComparisonLegRequestModel(BaseModel):
    label: str = Field(default="", max_length=128)
    object_type: str = Field(default="research_object", min_length=1, max_length=64)
    return_points: list[TimeSeriesPoint] = Field(default_factory=list, max_length=MAX_STRATEGY_LAB_ROWS)
    saved_research_id: str | None = Field(default=None, max_length=96)

    def to_domain(self) -> ResearchComparisonLeg:
        return ResearchComparisonLeg(
            label=self.label,
            object_type=self.object_type,
            returns=_points_to_series(self.return_points),
            saved_research_id=self.saved_research_id,
        )


class ResearchCompareRequestModel(BaseModel):
    left: ResearchComparisonLegRequestModel
    right: ResearchComparisonLegRequestModel

    def to_domain(self) -> ResearchComparisonRequest:
        return ResearchComparisonRequest(left=self.left.to_domain(), right=self.right.to_domain())


class ResearchComparisonLegModel(BaseModel):
    label: str
    object_type: str
    metrics: ResearchReturnMetricsModel
    returns_points: list[TimeSeriesPoint] = Field(default_factory=list)
    normalized_nav_points: list[TimeSeriesPoint] = Field(default_factory=list)
    drawdown_points: list[TimeSeriesPoint] = Field(default_factory=list)


class ResearchCompareResponseModel(BaseModel):
    left: ResearchComparisonLegModel
    right: ResearchComparisonLegModel
    left_observation_count: int
    right_observation_count: int
    aligned_observation_count: int
    overlap_start: datetime | None = None
    overlap_end: datetime | None = None
    relative_return: float | None = None
    volatility_difference: float | None = None
    max_drawdown_difference: float | None = None
    correlation: float | None = None
    beta: float | None = None
    relative_nav_points: list[TimeSeriesPoint] = Field(default_factory=list)
    relative_drawdown_points: list[TimeSeriesPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str

    @classmethod
    def from_domain(cls, row: ResearchComparisonResult) -> "ResearchCompareResponseModel":
        comparison = row.comparison
        return cls(
            left=ResearchComparisonLegModel(
                label=comparison.left.label,
                object_type=comparison.left.object_type,
                metrics=ResearchReturnMetricsModel.from_domain(comparison.left.metrics),
                returns_points=series_to_points(comparison.left.returns),
                normalized_nav_points=series_to_points(comparison.left.normalized_nav),
                drawdown_points=series_to_points(comparison.left.drawdowns),
            ),
            right=ResearchComparisonLegModel(
                label=comparison.right.label,
                object_type=comparison.right.object_type,
                metrics=ResearchReturnMetricsModel.from_domain(comparison.right.metrics),
                returns_points=series_to_points(comparison.right.returns),
                normalized_nav_points=series_to_points(comparison.right.normalized_nav),
                drawdown_points=series_to_points(comparison.right.drawdowns),
            ),
            left_observation_count=comparison.left_observation_count,
            right_observation_count=comparison.right_observation_count,
            aligned_observation_count=comparison.aligned_observation_count,
            overlap_start=comparison.overlap_start,
            overlap_end=comparison.overlap_end,
            relative_return=comparison.relative_return,
            volatility_difference=comparison.volatility_difference,
            max_drawdown_difference=comparison.max_drawdown_difference,
            correlation=comparison.correlation,
            beta=comparison.beta,
            relative_nav_points=series_to_points(comparison.relative_nav),
            relative_drawdown_points=series_to_points(comparison.relative_drawdown),
            warnings=list(row.warnings),
            source_provider=row.source_provider,
            retrieved_at=row.retrieved_at,
            origin=row.origin,
            transformation_note=row.transformation_note,
            freshness_label=row.freshness_label,
        )


class SavedResearchCreateRequestModel(BaseModel):
    object_type: str
    title: str
    notes: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str = "gamma_saved_research"
    origin: str = "research_service.saved_research.create"
    transformation_note: str | None = None

    def to_domain(self) -> SavedResearchCreateRequest:
        return SavedResearchCreateRequest(
            object_type=self.object_type,
            title=self.title,
            notes=self.notes,
            payload=dict(self.payload or {}),
            warnings=list(self.warnings or []),
            source_provider=self.source_provider,
            origin=self.origin,
            transformation_note=self.transformation_note,
        )


class SavedResearchItemModel(BaseModel):
    id: str
    schema_version: int
    object_type: str
    title: str
    notes: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: SavedResearchItem) -> "SavedResearchItemModel":
        return cls(**row.__dict__)


class SavedResearchListResponseModel(BaseModel):
    items: list[SavedResearchItemModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, rows: list[SavedResearchItem]) -> "SavedResearchListResponseModel":
        return cls(items=[SavedResearchItemModel.from_domain(row) for row in rows])


class SavedResearchDeleteResponseModel(BaseModel):
    success: bool


class ResearchOverviewUniverseInstrumentModel(BaseModel):
    symbol: str
    label: str
    group: str
    sector: str
    industry: str | None = None
    weight: float = 1.0
    market_cap_usd: float | None = None
    index_weight: float | None = None
    sort_rank: int | None = None
    currency: str = "USD"
    exchange: str = "SMART"
    sec_type: str = "STK"

    @classmethod
    def from_domain(cls, row: ResearchOverviewUniverseInstrument) -> "ResearchOverviewUniverseInstrumentModel":
        return cls(
            symbol=row.symbol,
            label=row.label,
            group=row.group,
            sector=row.sector,
            industry=row.industry,
            weight=row.weight,
            market_cap_usd=row.market_cap_usd,
            index_weight=row.index_weight,
            sort_rank=row.sort_rank,
            currency=row.currency,
            exchange=row.exchange,
            sec_type=row.sec_type,
        )


class ResearchOverviewUniverseModel(BaseModel):
    universe_id: str
    label: str
    description: str
    instruments: list[ResearchOverviewUniverseInstrumentModel] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    metadata_source_label: str = "Static Gamma reference list"
    coverage_label: str = "Partial research universe"
    is_complete_universe: bool = False

    @classmethod
    def from_domain(cls, row: ResearchOverviewUniverse) -> "ResearchOverviewUniverseModel":
        return cls(
            universe_id=row.universe_id,
            label=row.label,
            description=row.description,
            instruments=[ResearchOverviewUniverseInstrumentModel.from_domain(item) for item in row.instruments],
            limitations=list(row.limitations),
            metadata_source_label=row.metadata_source_label,
            coverage_label=row.coverage_label,
            is_complete_universe=row.is_complete_universe,
        )


class ResearchOverviewMetricOptionModel(BaseModel):
    metric_id: str
    label: str
    description: str

    @classmethod
    def from_domain(cls, row: ResearchOverviewMetricOption) -> "ResearchOverviewMetricOptionModel":
        return cls(**row.__dict__)


class ResearchOverviewSortOptionModel(BaseModel):
    sort_id: str
    label: str
    description: str

    @classmethod
    def from_domain(cls, row: ResearchOverviewSortOption) -> "ResearchOverviewSortOptionModel":
        return cls(**row.__dict__)


class ResearchOverviewMetricsModel(BaseModel):
    total_return: float | None = None
    annual_volatility: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    relative_return: float | None = None
    latest_price: float | None = None
    observation_count: int = 0

    @classmethod
    def from_domain(cls, row: ResearchOverviewMetrics) -> "ResearchOverviewMetricsModel":
        return cls(**row.__dict__)


class ResearchOverviewNodeModel(BaseModel):
    node_id: str
    normalized_id: str
    label: str
    level: str
    parent_id: str | None = None
    group: str | None = None
    sector: str | None = None
    industry: str | None = None
    symbol: str | None = None
    instrument_id: str | None = None
    weight: float | None = None
    market_cap_usd: float | None = None
    index_weight: float | None = None
    sort_rank: int | None = None
    size: float
    metrics: ResearchOverviewMetricsModel
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchOverviewNode) -> "ResearchOverviewNodeModel":
        payload = dict(row.__dict__)
        payload["metrics"] = ResearchOverviewMetricsModel.from_domain(row.metrics)
        payload["freshness_label"] = row.freshness_label.value
        return cls(**payload)


class ResearchOverviewCoverageModel(BaseModel):
    instrument_count: int
    priced_count: int
    missing_symbols: list[str] = Field(default_factory=list)
    benchmark_symbol: str
    benchmark_available: bool
    benchmark_observation_count: int
    coverage_ratio: float = 0.0
    missing_count: int = 0
    thin_history_symbols: list[str] = Field(default_factory=list)
    min_observation_count: int = 0
    max_observation_count: int = 0
    coverage_label: str = "Partial research universe"
    history_source_label: str = "Unknown history source"
    metadata_source_label: str = "Static Gamma reference list"

    @classmethod
    def from_domain(cls, row: ResearchOverviewCoverage) -> "ResearchOverviewCoverageModel":
        return cls(**row.__dict__)


class ResearchOverviewRankItemModel(BaseModel):
    node_id: str
    label: str
    group: str | None = None
    symbol: str | None = None
    value: float | None = None

    @classmethod
    def from_domain(cls, row: ResearchOverviewRankItem) -> "ResearchOverviewRankItemModel":
        return cls(**row.__dict__)


class ResearchOverviewRankingsModel(BaseModel):
    leaders: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    laggards: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    highest_volatility: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    highest_beta: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    largest_drawdowns: list[ResearchOverviewRankItemModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchOverviewRankings) -> "ResearchOverviewRankingsModel":
        return cls(
            leaders=[ResearchOverviewRankItemModel.from_domain(item) for item in row.leaders],
            laggards=[ResearchOverviewRankItemModel.from_domain(item) for item in row.laggards],
            highest_volatility=[ResearchOverviewRankItemModel.from_domain(item) for item in row.highest_volatility],
            highest_beta=[ResearchOverviewRankItemModel.from_domain(item) for item in row.highest_beta],
            largest_drawdowns=[ResearchOverviewRankItemModel.from_domain(item) for item in row.largest_drawdowns],
        )


class ResearchOverviewSummaryModel(BaseModel):
    leading_group: ResearchOverviewRankItemModel | None = None
    lagging_group: ResearchOverviewRankItemModel | None = None
    highest_volatility_group: ResearchOverviewRankItemModel | None = None
    coverage_note: str | None = None

    @classmethod
    def from_domain(cls, row: ResearchOverviewSummary) -> "ResearchOverviewSummaryModel":
        return cls(
            leading_group=ResearchOverviewRankItemModel.from_domain(row.leading_group) if row.leading_group else None,
            lagging_group=ResearchOverviewRankItemModel.from_domain(row.lagging_group) if row.lagging_group else None,
            highest_volatility_group=(
                ResearchOverviewRankItemModel.from_domain(row.highest_volatility_group)
                if row.highest_volatility_group
                else None
            ),
            coverage_note=row.coverage_note,
        )


class ResearchOverviewResponseModel(BaseModel):
    universe_id: str
    universe_label: str
    universe_description: str
    timeframe: str
    lookback_days: int
    benchmark_symbol: str
    available_universes: list[ResearchOverviewUniverseModel] = Field(default_factory=list)
    available_timeframes: list[str] = Field(default_factory=list)
    metric_options: list[ResearchOverviewMetricOptionModel] = Field(default_factory=list)
    sort_options: list[ResearchOverviewSortOptionModel] = Field(default_factory=list)
    nodes: list[ResearchOverviewNodeModel] = Field(default_factory=list)
    coverage: ResearchOverviewCoverageModel
    rankings: ResearchOverviewRankingsModel
    summary: ResearchOverviewSummaryModel
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str
    history_source_label: str = "Unknown history source"
    metadata_source_label: str = "Static Gamma reference list"
    coverage_label: str = "Partial research universe"

    @classmethod
    def from_domain(cls, row: ResearchOverviewResult) -> "ResearchOverviewResponseModel":
        return cls(
            universe_id=row.universe_id,
            universe_label=row.universe_label,
            universe_description=row.universe_description,
            timeframe=row.timeframe,
            lookback_days=row.lookback_days,
            benchmark_symbol=row.benchmark_symbol,
            available_universes=[ResearchOverviewUniverseModel.from_domain(item) for item in row.available_universes],
            available_timeframes=list(row.available_timeframes),
            metric_options=[ResearchOverviewMetricOptionModel.from_domain(item) for item in row.metric_options],
            sort_options=[ResearchOverviewSortOptionModel.from_domain(item) for item in row.sort_options],
            nodes=[ResearchOverviewNodeModel.from_domain(item) for item in row.nodes],
            coverage=ResearchOverviewCoverageModel.from_domain(row.coverage),
            rankings=ResearchOverviewRankingsModel.from_domain(row.rankings),
            summary=ResearchOverviewSummaryModel.from_domain(row.summary),
            warnings=list(row.warnings),
            source_provider=row.source_provider,
            retrieved_at=row.retrieved_at,
            origin=row.origin,
            transformation_note=row.transformation_note,
            freshness_label=row.freshness_label.value,
            history_source_label=row.history_source_label,
            metadata_source_label=row.metadata_source_label,
            coverage_label=row.coverage_label,
        )


class WeightPointModel(BaseModel):
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None


class ResearchSummaryModel(BaseModel):
    total_return: float | None = None
    annual_return: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None
    correlation: float | None = None


class ResearchStructureModel(BaseModel):
    total_weight: float | None = None
    top_weight: float | None = None
    top5_weight: float | None = None
    concentration_hhi: float | None = None
    effective_positions: float | None = None
    aligned_symbol_count: int = 0


class ResearchCoverageModel(BaseModel):
    available_symbols: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    benchmark_overlap_count: int = 0


class ResearchConstituentModel(BaseModel):
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None
    total_return: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
    weighted_return: float | None = None


class ResearchAnalyzeResponseModel(BaseModel):
    scope_type: ResearchScopeType
    benchmark_symbol: str
    primary_symbol: str | None = None
    observations_count: int
    latest_daily_return: float | None = None
    latest_daily_return_at: datetime | None = None
    latest_price: float | None = None
    latest_price_at: datetime | None = None
    snapshot: PortfolioSnapshotModel | None = None
    performance_points: list[TimeSeriesPoint]
    benchmark_points: list[TimeSeriesPoint]
    primary_price_points: list[TimeSeriesPoint]
    weights: list[WeightPointModel]
    summary: ResearchSummaryModel
    structure: ResearchStructureModel
    coverage: ResearchCoverageModel
    constituents: list[ResearchConstituentModel]
    warnings: list[str] = Field(default_factory=list)
    source_provider: str = "unknown"
    history_source_label: str = "Unknown history source"
    freshness_label: str = "unknown"

    @classmethod
    def from_service_result(cls, result: ResearchAnalysisResult) -> "ResearchAnalyzeResponseModel":
        total_return = None
        annual_return = None
        annual_vol = None
        max_dd = None
        beta = None
        correlation = None
        if not result.perf.empty:
            cumulative = (1.0 + result.perf).cumprod()
            total_return = float(cumulative.iloc[-1] - 1.0)
            annual_return = _annualized_return(result.perf)
            _daily_vol, annual_vol = realized_vol(result.perf)
            max_dd = max_drawdown(result.perf)
            beta, correlation = _beta_corr(result.perf, result.benchmark_returns)
        latest_daily_return, latest_daily_return_at = _latest_series_value(result.perf)
        latest_price, latest_price_at = _latest_series_value(result.primary_price)

        return cls(
            scope_type=result.scope_type,
            benchmark_symbol=result.benchmark_symbol,
            primary_symbol=result.primary_symbol,
            observations_count=int(len(result.perf)),
            latest_daily_return=latest_daily_return,
            latest_daily_return_at=latest_daily_return_at,
            latest_price=latest_price,
            latest_price_at=latest_price_at,
            snapshot=PortfolioSnapshotModel.from_domain(result.snapshot) if result.snapshot is not None else None,
            performance_points=series_to_points(result.perf),
            benchmark_points=series_to_points(result.benchmark_returns),
            primary_price_points=series_to_points(result.primary_price, result.primary_price_ohlcv),
            weights=[
                _weight_point_model(result.snapshot, str(instrument_id), float(weight))
                for instrument_id, weight in result.weights.items()
            ],
            summary=ResearchSummaryModel(
                total_return=total_return,
                annual_return=annual_return,
                annual_vol=annual_vol,
                max_drawdown=max_dd,
                beta=beta,
                correlation=correlation,
            ),
            structure=_structure_from_weights(result.weights),
            coverage=ResearchCoverageModel(
                available_symbols=list(result.available_symbols),
                missing_symbols=list(result.missing_symbols),
                benchmark_overlap_count=result.benchmark_overlap_count,
            ),
            constituents=_constituents_from_result(result),
            warnings=list(result.warnings),
            source_provider=result.source_provider,
            history_source_label=result.history_source_label,
            freshness_label=result.freshness_label.value,
        )


def _latest_series_value(series: pd.Series) -> tuple[float | None, datetime | None]:
    if series is None or series.empty:
        return None, None
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None, None
    timestamp = pd.Timestamp(clean.index[-1]).to_pydatetime()
    return float(clean.iloc[-1]), timestamp


def _points_to_series(points: list[TimeSeriesPoint]) -> pd.Series:
    if not points:
        return pd.Series(dtype=float)
    values = {
        pd.Timestamp(point.timestamp).to_pydatetime(): float(point.value)
        for point in points
        if point.value is not None
    }
    if not values:
        return pd.Series(dtype=float)
    return pd.Series(values).sort_index().astype(float)


def _annualized_return(perf):
    if perf.empty:
        return None
    cumulative = float((1.0 + perf).prod())
    periods = int(len(perf))
    if periods <= 0 or cumulative <= 0:
        return None
    return float(cumulative ** (252.0 / periods) - 1.0)


def _beta_corr(perf, benchmark_returns):
    if perf.empty or benchmark_returns.empty:
        return None, None
    aligned = perf.to_frame("portfolio").join(benchmark_returns.to_frame("benchmark"), how="inner").dropna()
    if len(aligned) < 2:
        return None, None
    benchmark_var = float(aligned["benchmark"].var())
    corr = float(aligned["portfolio"].corr(aligned["benchmark"])) if len(aligned) > 1 else None
    if benchmark_var <= 0:
        return None, corr
    cov = float(aligned["portfolio"].cov(aligned["benchmark"]))
    return cov / benchmark_var, corr


def _structure_from_weights(weights) -> ResearchStructureModel:
    if weights.empty:
        return ResearchStructureModel()
    absolute_weights = weights.abs().astype(float)
    total_weight = float(absolute_weights.sum())
    if total_weight <= 0:
        return ResearchStructureModel(total_weight=total_weight, aligned_symbol_count=int(len(weights)))
    normalized = absolute_weights / total_weight
    hhi = float((normalized**2).sum())
    return ResearchStructureModel(
        total_weight=total_weight,
        top_weight=float(normalized.max()),
        top5_weight=float(normalized.sort_values(ascending=False).head(5).sum()),
        concentration_hhi=hhi,
        effective_positions=float(1.0 / hhi) if hhi > 0 else None,
        aligned_symbol_count=int(len(weights)),
    )


def _constituents_from_result(result: ResearchAnalysisResult) -> list[ResearchConstituentModel]:
    if result.weights.empty:
        return []
    rows: list[ResearchConstituentModel] = []
    for instrument_id, weight in result.weights.sort_values(ascending=False).items():
        position_meta = _position_meta(result.snapshot, str(instrument_id))
        total_return = _series_value(result.constituent_total_returns, instrument_id)
        annual_vol = _series_value(result.constituent_annual_vol, instrument_id)
        max_dd = _series_value(result.constituent_max_drawdown, instrument_id)
        rows.append(
            ResearchConstituentModel(
                symbol=position_meta.get("symbol") or str(instrument_id),
                weight=float(weight),
                instrument_id=position_meta.get("instrument_id"),
                display_symbol=position_meta.get("display_symbol"),
                total_return=total_return,
                annual_vol=annual_vol,
                max_drawdown=max_dd,
                weighted_return=float(weight) * total_return if total_return is not None else None,
            )
        )
    return rows


def _series_value(series, symbol: str) -> float | None:
    if series is None or getattr(series, "empty", True):
        return None
    value = series.get(symbol)
    return None if value is None else float(value)


def _weight_point_model(snapshot, instrument_id: str, weight: float) -> WeightPointModel:
    position_meta = _position_meta(snapshot, instrument_id)
    return WeightPointModel(
        symbol=position_meta.get("symbol") or instrument_id,
        weight=weight,
        instrument_id=position_meta.get("instrument_id"),
        display_symbol=position_meta.get("display_symbol"),
    )


def _position_meta(snapshot, instrument_id: str) -> dict[str, str | None]:
    identity_map = snapshot_identity_map(snapshot)
    identity = identity_map.get(instrument_id)
    if identity is not None:
        return {
            "instrument_id": identity.instrument_id,
            "symbol": identity.symbol,
            "display_symbol": identity.display_symbol,
        }
    fallback = find_identity_by_symbol(snapshot, instrument_id)
    if fallback is not None:
        return {
            "instrument_id": fallback.instrument_id,
            "symbol": fallback.symbol,
            "display_symbol": fallback.display_symbol,
        }
    if snapshot is None:
        return {"instrument_id": None, "symbol": None, "display_symbol": None}
    return {"instrument_id": None, "symbol": None, "display_symbol": None}
