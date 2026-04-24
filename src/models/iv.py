from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class IVOptionGreeksRecord:
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


@dataclass(frozen=True)
class IVOptionContractRecord:
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
    bid_greeks: IVOptionGreeksRecord | None = None
    ask_greeks: IVOptionGreeksRecord | None = None
    last_greeks: IVOptionGreeksRecord | None = None
    model_greeks: IVOptionGreeksRecord | None = None
    derived_greeks: IVOptionGreeksRecord | None = None


@dataclass(frozen=True)
class IVOptionPairRecord:
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


@dataclass(frozen=True)
class IVSurfaceCollectionMetadata:
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


@dataclass(frozen=True)
class IVSurfaceQualityMetrics:
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


@dataclass(frozen=True)
class IVExpiryAnalyticsRecord:
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


@dataclass(frozen=True)
class IVPricingAssumptionsRecord:
    spot_reference: float | None = None
    risk_free_rate: float | None = None
    dividend_yield: float | None = None
    fallback_greeks_methodology: str | None = None
    notes: list[str] = field(default_factory=list)
