from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


COMMODITY_MODES = {
    "overview",
    "energy",
    "metals",
    "curves_spreads",
    "inventories_fundamentals",
    "events_cross_domain",
}

COMMODITY_COVERAGE_STATUSES = {
    "sample",
    "mock",
    "official_partial",
    "partial",
    "live",
    "unavailable",
}

COMMODITY_BASIS_TYPES = {
    "spot_proxy",
    "front_future",
    "selected_future",
    "continuous_proxy",
    "curve_node",
    "eia_reference",
    "fred_reference",
    "sample_generated",
    "unavailable",
}

COMMODITY_RECONCILIATION_STATUSES = {
    "aligned",
    "conflict",
    "insufficient",
}


@dataclass(frozen=True)
class CommodityCoverageMetadata:
    coverage_status: str
    provider_id: str
    provider_label: str
    freshness_label: str
    instruments: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    as_of: datetime | None = None
    source_timestamp: datetime | None = None
    caveats: list[str] = field(default_factory=list)
    credential_env_vars: list[str] = field(default_factory=list)
    supports_prices: bool = False
    supports_curves: bool = False
    supports_inventories: bool = False
    supports_events: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
    def __post_init__(self) -> None:
        if self.coverage_status not in COMMODITY_COVERAGE_STATUSES:
            raise ValueError(f"Unsupported commodities coverage status: {self.coverage_status}")


@dataclass(frozen=True)
class CommodityInstrument:
    instrument_id: str
    symbol: str
    name: str
    family: str
    subgroup: str
    quote_unit: str
    currency: str = "USD"
    exchange: str | None = None
    front_symbol: str | None = None
    provider_symbols: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityPricePoint:
    instrument_id: str
    timestamp: datetime
    value: float
    unit: str
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityPriceHistory:
    instrument_id: str
    label: str
    unit: str
    points: list[CommodityPricePoint] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityFuturesContract:
    contract_id: str
    instrument_id: str
    symbol: str
    contract_month: str
    expiry_date: datetime | None = None
    is_front_month: bool = False
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityCurveNode:
    contract: CommodityFuturesContract
    price: float | None
    previous_price: float | None = None
    change: float | None = None
    days_to_expiry: int | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityCurveSnapshot:
    instrument_id: str
    as_of: datetime
    nodes: list[CommodityCurveNode] = field(default_factory=list)
    previous_as_of: datetime | None = None
    shape_label: str = "unavailable"
    front_spread: float | None = None
    front_spread_pct: float | None = None
    m1_m6_spread: float | None = None
    curve_slope: float | None = None
    roll_yield_proxy_pct: float | None = None
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityPriceBasis:
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
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None

    def __post_init__(self) -> None:
        if self.basis_type not in COMMODITY_BASIS_TYPES:
            raise ValueError(f"Unsupported commodity basis type: {self.basis_type}")


@dataclass(frozen=True)
class CommodityPriceReconciliation:
    instrument_id: str
    status: str
    headline: CommodityPriceBasis | None = None
    observations: list[CommodityPriceBasis] = field(default_factory=list)
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None

    def __post_init__(self) -> None:
        if self.status not in COMMODITY_RECONCILIATION_STATUSES:
            raise ValueError(f"Unsupported commodity reconciliation status: {self.status}")


@dataclass(frozen=True)
class CommoditySpreadDefinition:
    spread_id: str
    label: str
    spread_type: str
    left_leg_id: str
    right_leg_id: str
    unit: str
    formula: str
    rationale: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommoditySpreadPoint:
    spread_id: str
    timestamp: datetime
    value: float
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommoditySpreadSnapshot:
    definition: CommoditySpreadDefinition
    value: float | None
    previous_value: float | None = None
    change: float | None = None
    z_score: float | None = None
    percentile: float | None = None
    interpretation: str | None = None
    history: list[CommoditySpreadPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityInventorySeriesMetadata:
    series_id: str
    instrument_id: str | None
    label: str
    category: str
    unit: str
    frequency: str
    provider_series_id: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityInventoryPoint:
    series_id: str
    timestamp: datetime
    value: float
    change: float | None = None
    seasonal_percentile: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityInventorySeries:
    metadata: CommodityInventorySeriesMetadata
    points: list[CommodityInventoryPoint] = field(default_factory=list)
    latest_value: float | None = None
    latest_change: float | None = None
    seasonal_percentile: float | None = None
    interpretation: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityMarketSummary:
    instrument: CommodityInstrument
    latest_price: float | None
    latest_change: float | None = None
    latest_change_pct: float | None = None
    quote_basis: CommodityPriceBasis | None = None
    curve_state: str = "unavailable"
    front_spread: float | None = None
    inventory_signal: str | None = None
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewMarketBreadth:
    total_markets: int
    counts_by_family: dict[str, int] = field(default_factory=dict)
    backwardation_count: int = 0
    contango_count: int = 0
    flat_count: int = 0
    unavailable_curve_count: int = 0
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewMatrixRow:
    instrument_id: str
    family: str
    symbol: str
    name: str
    quote_unit: str
    latest_price: float | None = None
    latest_change: float | None = None
    latest_change_pct: float | None = None
    quote_basis: CommodityPriceBasis | None = None
    curve_state: str = "unavailable"
    front_spread: float | None = None
    front_basis: float | None = None
    roll_yield_proxy_pct: float | None = None
    inventory_signal: str | None = None
    inventory_seasonal_percentile: float | None = None
    price_source_provider: str | None = None
    curve_source_provider: str | None = None
    inventory_source_provider: str | None = None
    provenance_summary: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewScatterPoint:
    instrument_id: str
    symbol: str
    name: str
    family: str
    x_value: float
    y_value: float
    display_label: str
    x_source_provider: str | None = None
    y_source_provider: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewScatter:
    points: list[CommodityOverviewScatterPoint] = field(default_factory=list)
    x_methodology_label: str = "Loaded-history momentum (%)"
    y_methodology_label: str = "Front-spread roll-yield proxy (%)"
    caveats: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewRankingItem:
    item_id: str
    label: str
    value: float | None
    instrument_id: str | None = None
    family: str | None = None
    display_value: str | None = None
    unit: str | None = None
    direction: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewRankings:
    strongest_backwardation: list[CommodityOverviewRankingItem] = field(default_factory=list)
    deepest_contango: list[CommodityOverviewRankingItem] = field(default_factory=list)
    inventory_outliers: list[CommodityOverviewRankingItem] = field(default_factory=list)
    spread_z_score_outliers: list[CommodityOverviewRankingItem] = field(default_factory=list)
    largest_movers: list[CommodityOverviewRankingItem] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewTermStructure:
    selected_instrument_id: str
    current_curve: CommodityCurveSnapshot | None = None
    previous_curve_snapshots: list[CommodityCurveSnapshot] = field(default_factory=list)
    current_curve_methodology: str | None = None
    previous_curve_methodology: str | None = None
    caveats: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityOverviewAnalytics:
    market_breadth: CommodityOverviewMarketBreadth
    matrix_rows: list[CommodityOverviewMatrixRow] = field(default_factory=list)
    scatter: CommodityOverviewScatter | None = None
    rankings: CommodityOverviewRankings | None = None
    term_structure: CommodityOverviewTermStructure | None = None
    caveats: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityEventRecord:
    event_id: str
    title: str
    category: str
    scheduled_at: datetime | None
    relative_label: str | None = None
    importance: str = "medium"
    linked_instrument_ids: list[str] = field(default_factory=list)
    summary: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityCrossDomainLink:
    link_id: str
    target_domain: str
    target_label: str
    relationship: str
    linked_instrument_ids: list[str] = field(default_factory=list)
    summary: str | None = None
    confidence: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityProviderSnapshot:
    coverage: CommodityCoverageMetadata
    instruments: list[CommodityInstrument] = field(default_factory=list)
    price_histories: list[CommodityPriceHistory] = field(default_factory=list)
    curve_snapshots: list[CommodityCurveSnapshot] = field(default_factory=list)
    inventory_series: list[CommodityInventorySeries] = field(default_factory=list)
    events: list[CommodityEventRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CommodityWorkspaceResult:
    mode: str
    selected_instrument_id: str
    available_modes: list[str]
    coverage: CommodityCoverageMetadata
    instruments: list[CommodityInstrument] = field(default_factory=list)
    market_summaries: list[CommodityMarketSummary] = field(default_factory=list)
    price_reconciliations: list[CommodityPriceReconciliation] = field(default_factory=list)
    price_histories: list[CommodityPriceHistory] = field(default_factory=list)
    curves: list[CommodityCurveSnapshot] = field(default_factory=list)
    spreads: list[CommoditySpreadSnapshot] = field(default_factory=list)
    inventories: list[CommodityInventorySeries] = field(default_factory=list)
    events: list[CommodityEventRecord] = field(default_factory=list)
    cross_domain_links: list[CommodityCrossDomainLink] = field(default_factory=list)
    overview: CommodityOverviewAnalytics | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None
