from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.application.iv_service import IVSurfaceResult
from src.models.iv import (
    IVExpiryAnalyticsRecord,
    IVOptionContractRecord,
    IVOptionGreeksRecord,
    IVOptionPairRecord,
    IVPricingAssumptionsRecord,
    IVSurfaceCollectionMetadata,
    IVSurfaceQualityMetrics,
)


class IVOptionGreeksModel(BaseModel):
    source: str
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    option_price: float | None = None
    pv_dividend: float | None = None
    underlying_price: float | None = None
    risk_free_rate: float | None = None
    dividend_yield: float | None = None
    methodology: str | None = None

    @classmethod
    def from_domain(cls, row: IVOptionGreeksRecord | None) -> "IVOptionGreeksModel | None":
        if row is None:
            return None
        return cls(**row.__dict__)


class IVOptionContractModel(BaseModel):
    contract_id: str
    symbol: str
    expiry: str
    strike: float
    right: str
    con_id: int | None = None
    local_symbol: str | None = None
    exchange: str | None = None
    currency: str | None = None
    multiplier: str | None = None
    trading_class: str | None = None
    market_data_type: int | None = None
    delayed: bool | None = None
    quote_timestamp: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    close: float | None = None
    mark_price: float | None = None
    midpoint: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    last_size: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    put_call_volume: float | None = None
    put_call_open_interest: float | None = None
    historical_volatility: float | None = None
    implied_volatility_30d: float | None = None
    price_source: str | None = None
    spread: float | None = None
    spread_pct_mid: float | None = None
    intrinsic_value: float | None = None
    extrinsic_value: float | None = None
    moneyness: float | None = None
    distance_from_spot_pct: float | None = None
    days_to_expiry: int | None = None
    bid_greeks: IVOptionGreeksModel | None = None
    ask_greeks: IVOptionGreeksModel | None = None
    last_greeks: IVOptionGreeksModel | None = None
    model_greeks: IVOptionGreeksModel | None = None
    derived_greeks: IVOptionGreeksModel | None = None

    @classmethod
    def from_domain(cls, row: IVOptionContractRecord) -> "IVOptionContractModel":
        return cls(
            **{
                **row.__dict__,
                "bid_greeks": IVOptionGreeksModel.from_domain(row.bid_greeks),
                "ask_greeks": IVOptionGreeksModel.from_domain(row.ask_greeks),
                "last_greeks": IVOptionGreeksModel.from_domain(row.last_greeks),
                "model_greeks": IVOptionGreeksModel.from_domain(row.model_greeks),
                "derived_greeks": IVOptionGreeksModel.from_domain(row.derived_greeks),
            }
        )


class IVOptionPairModel(BaseModel):
    pair_id: str
    expiry: str
    strike: float
    days_to_expiry: int | None = None
    call_contract_id: str | None = None
    put_contract_id: str | None = None
    call_midpoint: float | None = None
    put_midpoint: float | None = None
    call_mark_price: float | None = None
    put_mark_price: float | None = None
    call_price: float | None = None
    put_price: float | None = None
    call_price_source: str | None = None
    put_price_source: str | None = None
    call_implied_volatility: float | None = None
    put_implied_volatility: float | None = None
    blended_implied_volatility: float | None = None
    call_delta: float | None = None
    put_delta: float | None = None
    call_open_interest: float | None = None
    put_open_interest: float | None = None
    call_volume: float | None = None
    put_volume: float | None = None
    straddle_midpoint: float | None = None
    synthetic_forward_price: float | None = None
    implied_move_pct: float | None = None
    call_put_parity_gap: float | None = None

    @classmethod
    def from_domain(cls, row: IVOptionPairRecord) -> "IVOptionPairModel":
        return cls(**row.__dict__)


class IVSurfaceCollectionMetadataModel(BaseModel):
    depth_preset: str
    market_data_mode: str
    include_calls: bool
    include_puts: bool
    max_expiries: int
    strike_band_pct: float
    configured_max_contracts: int
    configured_market_data_line_budget: int
    reserved_market_data_lines: int
    underlying_market_data_lines: int
    option_market_data_line_budget: int
    selected_expiry_count: int
    selected_strike_count: int
    requested_contract_count: int
    subscribed_contract_count: int
    estimated_total_market_data_lines: int
    market_data_line_utilization: float | None = None
    contract_selection_note: str | None = None

    @classmethod
    def from_domain(cls, row: IVSurfaceCollectionMetadata | None) -> "IVSurfaceCollectionMetadataModel | None":
        if row is None:
            return None
        return cls(**row.__dict__)


class IVSurfaceQualityMetricsModel(BaseModel):
    expected_surface_cells: int
    observed_surface_cells: int
    interpolated_surface_cells: int
    interpolation_ratio: float | None = None
    contracts_with_bid_ask: int = 0
    contracts_with_volume: int = 0
    contracts_with_open_interest: int = 0
    contracts_with_provider_greeks: int = 0
    contracts_with_derived_greeks: int = 0
    call_contract_count: int = 0
    put_contract_count: int = 0
    pairs_with_both_sides: int = 0

    @classmethod
    def from_domain(cls, row: IVSurfaceQualityMetrics | None) -> "IVSurfaceQualityMetricsModel | None":
        if row is None:
            return None
        return cls(**row.__dict__)


class IVExpiryAnalyticsModel(BaseModel):
    expiry: str
    days_to_expiry: int | None = None
    atm_strike: float | None = None
    atm_call_implied_volatility: float | None = None
    atm_put_implied_volatility: float | None = None
    atm_blended_implied_volatility: float | None = None
    atm_straddle_midpoint: float | None = None
    synthetic_forward_price: float | None = None
    implied_move_pct: float | None = None
    put_call_parity_gap: float | None = None
    pair_count: int = 0
    pair_count_with_both_sides: int = 0

    @classmethod
    def from_domain(cls, row: IVExpiryAnalyticsRecord) -> "IVExpiryAnalyticsModel":
        return cls(**row.__dict__)


class IVPricingAssumptionsModel(BaseModel):
    spot_reference: float | None = None
    risk_free_rate: float | None = None
    dividend_yield: float | None = None
    fallback_greeks_methodology: str | None = None
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: IVPricingAssumptionsRecord | None) -> "IVPricingAssumptionsModel | None":
        if row is None:
            return None
        return cls(**row.__dict__)


class IVSurfaceResponseModel(BaseModel):
    symbol: str
    timestamp: datetime
    snapshot_available: bool
    spot: float | None = None
    expiries: list[str] = Field(default_factory=list)
    strikes: list[float] = Field(default_factory=list)
    iv_grid: list[list[float]] = Field(default_factory=list)
    delayed: bool | None = None
    points: int = 0
    warnings: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    source_provider: str = "ibkr"
    retrieved_at: datetime
    origin: str = "gamma.iv.surface"
    transformation_note: str | None = None
    freshness_label: str = "unknown"
    contracts: list[IVOptionContractModel] = Field(default_factory=list)
    pairs: list[IVOptionPairModel] = Field(default_factory=list)
    collection: IVSurfaceCollectionMetadataModel | None = None
    quality: IVSurfaceQualityMetricsModel | None = None
    expiry_analytics: list[IVExpiryAnalyticsModel] = Field(default_factory=list)
    pricing_assumptions: IVPricingAssumptionsModel | None = None

    @classmethod
    def from_service_result(cls, symbol: str, result: IVSurfaceResult) -> "IVSurfaceResponseModel":
        if result.snapshot is None:
            return cls(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                retrieved_at=datetime.utcnow(),
                snapshot_available=False,
                warnings=list(result.warnings),
                messages=list(result.messages),
                freshness_label="unavailable",
            )
        snapshot = result.snapshot
        return cls(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            retrieved_at=datetime.utcnow(),
            snapshot_available=True,
            spot=float(snapshot.spot),
            expiries=list(snapshot.expiries),
            strikes=[float(strike) for strike in snapshot.strikes],
            iv_grid=[[float(value) for value in row] for row in snapshot.iv_grid.tolist()],
            delayed=bool(snapshot.delayed),
            points=int(snapshot.points),
            warnings=list(result.warnings),
            messages=list(result.messages),
            source_provider=snapshot.source_provider,
            origin=snapshot.origin,
            transformation_note=snapshot.transformation_note,
            freshness_label=snapshot.freshness_label,
            contracts=[IVOptionContractModel.from_domain(item) for item in snapshot.contracts],
            pairs=[IVOptionPairModel.from_domain(item) for item in snapshot.pairs],
            collection=IVSurfaceCollectionMetadataModel.from_domain(snapshot.collection),
            quality=IVSurfaceQualityMetricsModel.from_domain(snapshot.quality),
            expiry_analytics=[IVExpiryAnalyticsModel.from_domain(item) for item in snapshot.expiry_analytics],
            pricing_assumptions=IVPricingAssumptionsModel.from_domain(snapshot.pricing_assumptions),
        )


class IVSessionRequestModel(BaseModel):
    symbol: str = "SPY"
    market_data_mode: str | None = None
    depth_preset: str | None = None


class IVSessionStatusResponseModel(BaseModel):
    running: bool
    status_text: str
    active_symbol: str | None = None
    market_data_mode: str
    surface: IVSurfaceResponseModel
    messages: list[str] = Field(default_factory=list)
