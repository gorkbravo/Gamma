from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.application.commodities_service import CommodityWorkspaceRequest
from src.models.commodities import (
    CommodityCoverageMetadata,
    CommodityCrossDomainLink,
    CommodityCurveNode,
    CommodityCurveSnapshot,
    CommodityEventRecord,
    CommodityFuturesContract,
    CommodityInstrument,
    CommodityInventoryPoint,
    CommodityInventorySeries,
    CommodityInventorySeriesMetadata,
    CommodityMarketSummary,
    CommodityOverviewAnalytics,
    CommodityOverviewMarketBreadth,
    CommodityOverviewMatrixRow,
    CommodityOverviewRankingItem,
    CommodityOverviewRankings,
    CommodityOverviewScatter,
    CommodityOverviewScatterPoint,
    CommodityOverviewTermStructure,
    CommodityPriceBasis,
    CommodityPriceHistory,
    CommodityPricePoint,
    CommodityPriceReconciliation,
    CommoditySpreadDefinition,
    CommoditySpreadPoint,
    CommoditySpreadSnapshot,
    CommodityWorkspaceResult,
)


class CommodityWorkspaceRequestModel(BaseModel):
    mode: str = "overview"
    selected_instrument_id: str = "wti"
    force_refresh: bool = False

    def to_domain(self) -> CommodityWorkspaceRequest:
        return CommodityWorkspaceRequest(
            mode=self.mode,
            selected_instrument_id=self.selected_instrument_id,
            force_refresh=self.force_refresh,
        )


class CommodityCoverageMetadataModel(BaseModel):
    coverage_status: str
    provider_id: str
    provider_label: str
    freshness_label: str
    instruments: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    as_of: datetime | None = None
    source_timestamp: datetime | None = None
    caveats: list[str] = Field(default_factory=list)
    credential_env_vars: list[str] = Field(default_factory=list)
    supports_prices: bool = False
    supports_curves: bool = False
    supports_inventories: bool = False
    supports_events: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityCoverageMetadata) -> "CommodityCoverageMetadataModel":
        return cls(**row.__dict__)


class CommodityInstrumentModel(BaseModel):
    instrument_id: str
    symbol: str
    name: str
    family: str
    subgroup: str
    quote_unit: str
    currency: str
    exchange: str | None = None
    front_symbol: str | None = None
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityInstrument) -> "CommodityInstrumentModel":
        return cls(**row.__dict__)


class CommodityPricePointModel(BaseModel):
    instrument_id: str
    timestamp: datetime
    value: float
    unit: str
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityPricePoint) -> "CommodityPricePointModel":
        return cls(**row.__dict__)


class CommodityPriceHistoryModel(BaseModel):
    instrument_id: str
    label: str
    unit: str
    points: list[CommodityPricePointModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityPriceHistory) -> "CommodityPriceHistoryModel":
        return cls(
            **{
                **row.__dict__,
                "points": [CommodityPricePointModel.from_domain(point) for point in row.points],
            }
        )


class CommodityFuturesContractModel(BaseModel):
    contract_id: str
    instrument_id: str
    symbol: str
    contract_month: str
    expiry_date: datetime | None = None
    is_front_month: bool = False
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityFuturesContract) -> "CommodityFuturesContractModel":
        return cls(**row.__dict__)


class CommodityCurveNodeModel(BaseModel):
    contract: CommodityFuturesContractModel
    price: float | None = None
    previous_price: float | None = None
    change: float | None = None
    days_to_expiry: int | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityCurveNode) -> "CommodityCurveNodeModel":
        return cls(
            **{
                **row.__dict__,
                "contract": CommodityFuturesContractModel.from_domain(row.contract),
            }
        )


class CommodityCurveSnapshotModel(BaseModel):
    instrument_id: str
    as_of: datetime
    nodes: list[CommodityCurveNodeModel] = Field(default_factory=list)
    previous_as_of: datetime | None = None
    shape_label: str
    front_spread: float | None = None
    front_spread_pct: float | None = None
    m1_m6_spread: float | None = None
    curve_slope: float | None = None
    roll_yield_proxy_pct: float | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityCurveSnapshot) -> "CommodityCurveSnapshotModel":
        return cls(
            **{
                **row.__dict__,
                "nodes": [CommodityCurveNodeModel.from_domain(node) for node in row.nodes],
            }
    )


class CommodityPriceBasisModel(BaseModel):
    basis_id: str
    instrument_id: str
    role: str
    basis_type: str
    display_label: str
    provider: str
    value: float | None = None
    previous_value: float | None = None
    change: float | None = None
    change_pct: float | None = None
    unit: str | None = None
    timestamp: datetime | None = None
    source_timestamp: datetime | None = None
    previous_source_timestamp: datetime | None = None
    contract_month: str | None = None
    contract_symbol: str | None = None
    provider_symbol: str | None = None
    freshness_label: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityPriceBasis) -> "CommodityPriceBasisModel":
        return cls(**row.__dict__)


class CommodityPriceReconciliationModel(BaseModel):
    instrument_id: str
    status: str
    headline: CommodityPriceBasisModel | None = None
    observations: list[CommodityPriceBasisModel] = Field(default_factory=list)
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityPriceReconciliation) -> "CommodityPriceReconciliationModel":
        return cls(
            **{
                **row.__dict__,
                "headline": CommodityPriceBasisModel.from_domain(row.headline) if row.headline is not None else None,
                "observations": [CommodityPriceBasisModel.from_domain(item) for item in row.observations],
            }
        )


class CommoditySpreadDefinitionModel(BaseModel):
    spread_id: str
    label: str
    spread_type: str
    left_leg_id: str
    right_leg_id: str
    unit: str
    formula: str
    rationale: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommoditySpreadDefinition) -> "CommoditySpreadDefinitionModel":
        return cls(**row.__dict__)


class CommoditySpreadPointModel(BaseModel):
    spread_id: str
    timestamp: datetime
    value: float
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommoditySpreadPoint) -> "CommoditySpreadPointModel":
        return cls(**row.__dict__)


class CommoditySpreadSnapshotModel(BaseModel):
    definition: CommoditySpreadDefinitionModel
    value: float | None = None
    previous_value: float | None = None
    change: float | None = None
    z_score: float | None = None
    percentile: float | None = None
    interpretation: str | None = None
    history: list[CommoditySpreadPointModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommoditySpreadSnapshot) -> "CommoditySpreadSnapshotModel":
        return cls(
            **{
                **row.__dict__,
                "definition": CommoditySpreadDefinitionModel.from_domain(row.definition),
                "history": [CommoditySpreadPointModel.from_domain(point) for point in row.history],
            }
        )


class CommodityInventorySeriesMetadataModel(BaseModel):
    series_id: str
    instrument_id: str | None = None
    label: str
    category: str
    unit: str
    frequency: str
    provider_series_id: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityInventorySeriesMetadata) -> "CommodityInventorySeriesMetadataModel":
        return cls(**row.__dict__)


class CommodityInventoryPointModel(BaseModel):
    series_id: str
    timestamp: datetime
    value: float
    change: float | None = None
    seasonal_percentile: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityInventoryPoint) -> "CommodityInventoryPointModel":
        return cls(**row.__dict__)


class CommodityInventorySeriesModel(BaseModel):
    metadata: CommodityInventorySeriesMetadataModel
    points: list[CommodityInventoryPointModel] = Field(default_factory=list)
    latest_value: float | None = None
    latest_change: float | None = None
    seasonal_percentile: float | None = None
    interpretation: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityInventorySeries) -> "CommodityInventorySeriesModel":
        return cls(
            **{
                **row.__dict__,
                "metadata": CommodityInventorySeriesMetadataModel.from_domain(row.metadata),
                "points": [CommodityInventoryPointModel.from_domain(point) for point in row.points],
            }
        )


class CommodityMarketSummaryModel(BaseModel):
    instrument: CommodityInstrumentModel
    latest_price: float | None = None
    latest_change: float | None = None
    latest_change_pct: float | None = None
    quote_basis: CommodityPriceBasisModel | None = None
    curve_state: str
    front_spread: float | None = None
    inventory_signal: str | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityMarketSummary) -> "CommodityMarketSummaryModel":
        return cls(
            **{
                **row.__dict__,
                "warnings": [warning for warning in row.warnings if warning],
                "instrument": CommodityInstrumentModel.from_domain(row.instrument),
                "quote_basis": CommodityPriceBasisModel.from_domain(row.quote_basis)
                if row.quote_basis is not None
                else None,
            }
        )


class CommodityOverviewMarketBreadthModel(BaseModel):
    total_markets: int
    counts_by_family: dict[str, int] = Field(default_factory=dict)
    backwardation_count: int = 0
    contango_count: int = 0
    flat_count: int = 0
    unavailable_curve_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewMarketBreadth) -> "CommodityOverviewMarketBreadthModel":
        return cls(**row.__dict__)


class CommodityOverviewMatrixRowModel(BaseModel):
    instrument_id: str
    family: str
    symbol: str
    name: str
    quote_unit: str
    latest_price: float | None = None
    latest_change: float | None = None
    latest_change_pct: float | None = None
    quote_basis: CommodityPriceBasisModel | None = None
    curve_state: str = "unavailable"
    front_spread: float | None = None
    front_basis: float | None = None
    roll_yield_proxy_pct: float | None = None
    inventory_signal: str | None = None
    inventory_seasonal_percentile: float | None = None
    price_source_provider: str | None = None
    curve_source_provider: str | None = None
    inventory_source_provider: str | None = None
    provenance_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewMatrixRow) -> "CommodityOverviewMatrixRowModel":
        return cls(
            **{
                **row.__dict__,
                "quote_basis": CommodityPriceBasisModel.from_domain(row.quote_basis)
                if row.quote_basis is not None
                else None,
            }
        )


class CommodityOverviewScatterPointModel(BaseModel):
    instrument_id: str
    symbol: str
    name: str
    family: str
    x_value: float
    y_value: float
    display_label: str
    x_source_provider: str | None = None
    y_source_provider: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewScatterPoint) -> "CommodityOverviewScatterPointModel":
        return cls(**row.__dict__)


class CommodityOverviewScatterModel(BaseModel):
    points: list[CommodityOverviewScatterPointModel] = Field(default_factory=list)
    x_methodology_label: str
    y_methodology_label: str
    caveats: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewScatter) -> "CommodityOverviewScatterModel":
        return cls(
            **{
                **row.__dict__,
                "points": [CommodityOverviewScatterPointModel.from_domain(point) for point in row.points],
            }
        )


class CommodityOverviewRankingItemModel(BaseModel):
    item_id: str
    label: str
    value: float | None = None
    instrument_id: str | None = None
    family: str | None = None
    display_value: str | None = None
    unit: str | None = None
    direction: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewRankingItem) -> "CommodityOverviewRankingItemModel":
        return cls(**row.__dict__)


class CommodityOverviewRankingsModel(BaseModel):
    strongest_backwardation: list[CommodityOverviewRankingItemModel] = Field(default_factory=list)
    deepest_contango: list[CommodityOverviewRankingItemModel] = Field(default_factory=list)
    inventory_outliers: list[CommodityOverviewRankingItemModel] = Field(default_factory=list)
    spread_z_score_outliers: list[CommodityOverviewRankingItemModel] = Field(default_factory=list)
    largest_movers: list[CommodityOverviewRankingItemModel] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewRankings) -> "CommodityOverviewRankingsModel":
        return cls(
            **{
                **row.__dict__,
                "strongest_backwardation": [
                    CommodityOverviewRankingItemModel.from_domain(item) for item in row.strongest_backwardation
                ],
                "deepest_contango": [
                    CommodityOverviewRankingItemModel.from_domain(item) for item in row.deepest_contango
                ],
                "inventory_outliers": [
                    CommodityOverviewRankingItemModel.from_domain(item) for item in row.inventory_outliers
                ],
                "spread_z_score_outliers": [
                    CommodityOverviewRankingItemModel.from_domain(item) for item in row.spread_z_score_outliers
                ],
                "largest_movers": [
                    CommodityOverviewRankingItemModel.from_domain(item) for item in row.largest_movers
                ],
            }
        )


class CommodityOverviewTermStructureModel(BaseModel):
    selected_instrument_id: str
    current_curve: CommodityCurveSnapshotModel | None = None
    previous_curve_snapshots: list[CommodityCurveSnapshotModel] = Field(default_factory=list)
    current_curve_methodology: str | None = None
    previous_curve_methodology: str | None = None
    caveats: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewTermStructure) -> "CommodityOverviewTermStructureModel":
        return cls(
            **{
                **row.__dict__,
                "current_curve": (
                    CommodityCurveSnapshotModel.from_domain(row.current_curve) if row.current_curve is not None else None
                ),
                "previous_curve_snapshots": [
                    CommodityCurveSnapshotModel.from_domain(curve) for curve in row.previous_curve_snapshots
                ],
            }
        )


class CommodityOverviewAnalyticsModel(BaseModel):
    market_breadth: CommodityOverviewMarketBreadthModel
    matrix_rows: list[CommodityOverviewMatrixRowModel] = Field(default_factory=list)
    scatter: CommodityOverviewScatterModel | None = None
    rankings: CommodityOverviewRankingsModel | None = None
    term_structure: CommodityOverviewTermStructureModel | None = None
    caveats: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityOverviewAnalytics) -> "CommodityOverviewAnalyticsModel":
        return cls(
            **{
                **row.__dict__,
                "market_breadth": CommodityOverviewMarketBreadthModel.from_domain(row.market_breadth),
                "matrix_rows": [CommodityOverviewMatrixRowModel.from_domain(item) for item in row.matrix_rows],
                "scatter": CommodityOverviewScatterModel.from_domain(row.scatter) if row.scatter is not None else None,
                "rankings": (
                    CommodityOverviewRankingsModel.from_domain(row.rankings) if row.rankings is not None else None
                ),
                "term_structure": (
                    CommodityOverviewTermStructureModel.from_domain(row.term_structure)
                    if row.term_structure is not None
                    else None
                ),
            }
        )


class CommodityEventRecordModel(BaseModel):
    event_id: str
    title: str
    category: str
    scheduled_at: datetime | None = None
    relative_label: str | None = None
    importance: str
    linked_instrument_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityEventRecord) -> "CommodityEventRecordModel":
        return cls(**row.__dict__)


class CommodityCrossDomainLinkModel(BaseModel):
    link_id: str
    target_domain: str
    target_label: str
    relationship: str
    linked_instrument_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    confidence: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityCrossDomainLink) -> "CommodityCrossDomainLinkModel":
        return cls(**row.__dict__)


class CommodityWorkspaceResponseModel(BaseModel):
    mode: str
    selected_instrument_id: str
    available_modes: list[str]
    coverage: CommodityCoverageMetadataModel
    instruments: list[CommodityInstrumentModel] = Field(default_factory=list)
    market_summaries: list[CommodityMarketSummaryModel] = Field(default_factory=list)
    price_reconciliations: list[CommodityPriceReconciliationModel] = Field(default_factory=list)
    price_histories: list[CommodityPriceHistoryModel] = Field(default_factory=list)
    curves: list[CommodityCurveSnapshotModel] = Field(default_factory=list)
    spreads: list[CommoditySpreadSnapshotModel] = Field(default_factory=list)
    inventories: list[CommodityInventorySeriesModel] = Field(default_factory=list)
    events: list[CommodityEventRecordModel] = Field(default_factory=list)
    cross_domain_links: list[CommodityCrossDomainLinkModel] = Field(default_factory=list)
    overview: CommodityOverviewAnalyticsModel | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CommodityWorkspaceResult) -> "CommodityWorkspaceResponseModel":
        return cls(
            **{
                **row.__dict__,
                "coverage": CommodityCoverageMetadataModel.from_domain(row.coverage),
                "instruments": [CommodityInstrumentModel.from_domain(item) for item in row.instruments],
                "market_summaries": [CommodityMarketSummaryModel.from_domain(item) for item in row.market_summaries],
                "price_reconciliations": [
                    CommodityPriceReconciliationModel.from_domain(item) for item in row.price_reconciliations
                ],
                "price_histories": [CommodityPriceHistoryModel.from_domain(item) for item in row.price_histories],
                "curves": [CommodityCurveSnapshotModel.from_domain(item) for item in row.curves],
                "spreads": [CommoditySpreadSnapshotModel.from_domain(item) for item in row.spreads],
                "inventories": [CommodityInventorySeriesModel.from_domain(item) for item in row.inventories],
                "events": [CommodityEventRecordModel.from_domain(item) for item in row.events],
                "cross_domain_links": [
                    CommodityCrossDomainLinkModel.from_domain(item) for item in row.cross_domain_links
                ],
                "overview": CommodityOverviewAnalyticsModel.from_domain(row.overview)
                if row.overview is not None
                else None,
            }
        )


class CommodityPriceHistoryResponseModel(BaseModel):
    instrument_id: str
    history: CommodityPriceHistoryModel | None = None


class CommodityCurveResponseModel(BaseModel):
    instrument_id: str
    curve: CommodityCurveSnapshotModel | None = None


class CommoditySpreadListResponseModel(BaseModel):
    spreads: list[CommoditySpreadSnapshotModel] = Field(default_factory=list)
