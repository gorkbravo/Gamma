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
    CommodityPriceHistory,
    CommodityPricePoint,
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
    price_histories: list[CommodityPriceHistoryModel] = Field(default_factory=list)
    curves: list[CommodityCurveSnapshotModel] = Field(default_factory=list)
    spreads: list[CommoditySpreadSnapshotModel] = Field(default_factory=list)
    inventories: list[CommodityInventorySeriesModel] = Field(default_factory=list)
    events: list[CommodityEventRecordModel] = Field(default_factory=list)
    cross_domain_links: list[CommodityCrossDomainLinkModel] = Field(default_factory=list)
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
                "price_histories": [CommodityPriceHistoryModel.from_domain(item) for item in row.price_histories],
                "curves": [CommodityCurveSnapshotModel.from_domain(item) for item in row.curves],
                "spreads": [CommoditySpreadSnapshotModel.from_domain(item) for item in row.spreads],
                "inventories": [CommodityInventorySeriesModel.from_domain(item) for item in row.inventories],
                "events": [CommodityEventRecordModel.from_domain(item) for item in row.events],
                "cross_domain_links": [
                    CommodityCrossDomainLinkModel.from_domain(item) for item in row.cross_domain_links
                ],
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
