from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CryptoBasketConstituent:
    token_id: str
    name: str | None = None
    symbol: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class CryptoNarrativeBasketRecord:
    basket_id: str
    label: str
    description: str | None
    market_cap: float | None
    market_cap_change_pct_24h: float | None
    volume_24h: float | None
    top_tokens: list[CryptoBasketConstituent] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoTokenRecord:
    token_id: str
    symbol: str
    name: str
    image_url: str | None
    chain: str | None
    asset_platform_id: str | None
    geckoterminal_network: str | None
    contract_address: str | None
    market_cap_rank: int | None
    current_price: float | None
    market_cap: float | None
    fully_diluted_valuation: float | None
    total_volume: float | None
    circulating_supply: float | None
    total_supply: float | None
    max_supply: float | None
    price_change_pct_24h: float | None
    price_change_pct_7d: float | None
    price_change_pct_30d: float | None
    market_cap_change_pct_24h: float | None
    high_24h: float | None
    low_24h: float | None
    homepage_url: str | None
    description: str | None
    categories: list[str] = field(default_factory=list)
    narrative_labels: list[str] = field(default_factory=list)
    layer_bucket: str | None = None
    turnover_ratio_24h: float | None = None
    fdv_premium_ratio: float | None = None
    screen_score: float | None = None
    screen_rationale: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoPricePoint:
    timestamp: datetime
    price: float
    market_cap: float | None = None
    total_volume: float | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoDexPoolRecord:
    pool_id: str
    network: str
    dex: str
    pair_name: str
    address: str
    quote_token_symbol: str | None
    base_token_price_usd: float | None
    fdv_usd: float | None
    market_cap_usd: float | None
    reserve_usd: float | None
    volume_24h: float | None
    price_change_pct_24h: float | None
    buys_24h: int
    sells_24h: int
    buyers_24h: int
    sellers_24h: int
    pool_created_at: datetime | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoDexLiquiditySummary:
    token_id: str
    lookup_strategy: str
    matched_networks: list[str] = field(default_factory=list)
    total_reserve_usd: float | None = None
    total_volume_24h: float | None = None
    total_buys_24h: int = 0
    total_sells_24h: int = 0
    total_buyers_24h: int = 0
    total_sellers_24h: int = 0
    dominant_dex: str | None = None
    pools: list[CryptoDexPoolRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoComparisonRecord:
    subject_token_id: str
    target_kind: str
    target_id: str
    target_label: str
    shared_categories: list[str] = field(default_factory=list)
    subject_price_change_pct_24h: float | None = None
    target_price_change_pct_24h: float | None = None
    price_gap_pct_24h: float | None = None
    subject_price_change_pct_7d: float | None = None
    target_price_change_pct_7d: float | None = None
    price_gap_pct_7d: float | None = None
    subject_price_change_pct_30d: float | None = None
    target_price_change_pct_30d: float | None = None
    price_gap_pct_30d: float | None = None
    subject_market_cap: float | None = None
    target_market_cap: float | None = None
    market_cap_ratio: float | None = None
    subject_turnover_ratio_24h: float | None = None
    target_turnover_ratio_24h: float | None = None
    turnover_gap: float | None = None
    summary: str | None = None
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoFlowSummaryRecord:
    token_id: str
    pool_count: int
    matched_networks: list[str] = field(default_factory=list)
    total_reserve_usd: float | None = None
    total_volume_24h: float | None = None
    dex_volume_share_of_total_volume: float | None = None
    reserve_to_market_cap_ratio: float | None = None
    top_pool_reserve_share: float | None = None
    top_pool_volume_share: float | None = None
    buy_pressure_pct: float | None = None
    active_trader_proxy_24h: int = 0
    buy_sell_ratio: float | None = None
    participant_balance_ratio: float | None = None
    reserve_volume_ratio_24h: float | None = None
    slippage_proxy_label: str | None = None
    liquidity_concentration_label: str = ""
    flow_signal_label: str = ""
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoSyntheticPositionRequest:
    identifier: str
    weight: float


@dataclass(frozen=True)
class CryptoSyntheticPortfolioRequest:
    positions: list[CryptoSyntheticPositionRequest] = field(default_factory=list)
    benchmark_token_id: str | None = None
    lookback_days: int = 30
    force_refresh: bool = False


@dataclass(frozen=True)
class CryptoPortfolioConstituentRecord:
    token_id: str
    symbol: str
    name: str
    input_weight: float
    normalized_weight: float
    market_cap: float | None = None
    turnover_ratio_24h: float | None = None
    narrative_labels: list[str] = field(default_factory=list)
    layer_bucket: str | None = None


@dataclass(frozen=True)
class CryptoPortfolioNarrativeExposureRecord:
    label: str
    normalized_weight: float
    constituent_count: int


@dataclass(frozen=True)
class CryptoPortfolioPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class CryptoSyntheticPortfolioRecord:
    lookback_days: int
    benchmark_token_id: str
    benchmark_label: str
    constituents: list[CryptoPortfolioConstituentRecord] = field(default_factory=list)
    narrative_exposures: list[CryptoPortfolioNarrativeExposureRecord] = field(default_factory=list)
    portfolio_points: list[CryptoPortfolioPoint] = field(default_factory=list)
    benchmark_points: list[CryptoPortfolioPoint] = field(default_factory=list)
    cumulative_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    relative_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    weighted_turnover_ratio_24h: float | None = None
    weighted_market_cap: float | None = None
    concentration_hhi: float | None = None
    effective_positions: float | None = None
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_provider: str = ""
    retrieved_at: datetime | None = None
    origin: str = ""
    transformation_note: str | None = None


@dataclass(frozen=True)
class CryptoScreenerRequest:
    query: str = ""
    narrative: str | None = None
    chain: str | None = None
    min_market_cap: float | None = None
    min_volume: float | None = None
    min_turnover_ratio: float | None = None
    sort_by: str = "market_cap_desc"
    limit: int = 40
    force_refresh: bool = False


@dataclass(frozen=True)
class CryptoWorkspaceResult:
    tokens: list[CryptoTokenRecord] = field(default_factory=list)
    narratives: list[CryptoNarrativeBasketRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
