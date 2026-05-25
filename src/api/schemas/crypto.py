from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.application.request_limits import (
    MAX_CRYPTO_PORTFOLIO_POSITIONS,
    MAX_CRYPTO_WORKSPACE_LIMIT,
    MAX_REQUEST_TEXT_CHARS,
)
from src.models.crypto import (
    CryptoBasketConstituent,
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoDexPoolRecord,
    CryptoFlowSummaryRecord,
    CryptoNarrativeBasketRecord,
    CryptoPortfolioConstituentRecord,
    CryptoPortfolioNarrativeExposureRecord,
    CryptoPortfolioPoint,
    CryptoPricePoint,
    CryptoSyntheticPortfolioRecord,
    CryptoSyntheticPortfolioRequest,
    CryptoSyntheticPositionRequest,
    CryptoScreenerRequest,
    CryptoTokenRecord,
    CryptoWorkspaceResult,
)


class CryptoWorkspaceRequestModel(BaseModel):
    query: str = Field(default="", max_length=128)
    narrative: str | None = Field(default=None, max_length=64)
    chain: str | None = Field(default=None, max_length=64)
    min_market_cap: float | None = Field(default=None, ge=0)
    min_volume: float | None = Field(default=None, ge=0)
    min_turnover_ratio: float | None = Field(default=None, ge=0)
    sort_by: str = Field(default="market_cap_desc", min_length=1, max_length=64)
    limit: int = Field(default=40, ge=1, le=MAX_CRYPTO_WORKSPACE_LIMIT)
    force_refresh: bool = False

    def to_domain(self) -> CryptoScreenerRequest:
        return CryptoScreenerRequest(
            query=self.query,
            narrative=self.narrative,
            chain=self.chain,
            min_market_cap=self.min_market_cap,
            min_volume=self.min_volume,
            min_turnover_ratio=self.min_turnover_ratio,
            sort_by=self.sort_by,
            limit=self.limit,
            force_refresh=self.force_refresh,
        )


class CryptoBasketConstituentModel(BaseModel):
    token_id: str
    name: str | None = None
    symbol: str | None = None
    image_url: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoBasketConstituent) -> "CryptoBasketConstituentModel":
        return cls(**row.__dict__)


class CryptoNarrativeBasketModel(BaseModel):
    basket_id: str
    label: str
    description: str | None = None
    market_cap: float | None = None
    market_cap_change_pct_24h: float | None = None
    volume_24h: float | None = None
    top_tokens: list[CryptoBasketConstituentModel] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoNarrativeBasketRecord) -> "CryptoNarrativeBasketModel":
        return cls(
            **{
                **row.__dict__,
                "top_tokens": [CryptoBasketConstituentModel.from_domain(item) for item in row.top_tokens],
            }
        )


class CryptoTokenModel(BaseModel):
    token_id: str
    symbol: str
    name: str
    image_url: str | None = None
    chain: str | None = None
    asset_platform_id: str | None = None
    geckoterminal_network: str | None = None
    contract_address: str | None = None
    market_cap_rank: int | None = None
    current_price: float | None = None
    market_cap: float | None = None
    fully_diluted_valuation: float | None = None
    total_volume: float | None = None
    circulating_supply: float | None = None
    total_supply: float | None = None
    max_supply: float | None = None
    price_change_pct_24h: float | None = None
    price_change_pct_7d: float | None = None
    price_change_pct_30d: float | None = None
    market_cap_change_pct_24h: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    homepage_url: str | None = None
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    narrative_labels: list[str] = Field(default_factory=list)
    layer_bucket: str | None = None
    turnover_ratio_24h: float | None = None
    fdv_premium_ratio: float | None = None
    screen_score: float | None = None
    screen_rationale: str | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoTokenRecord) -> "CryptoTokenModel":
        return cls(**row.__dict__)


class CryptoPricePointModel(BaseModel):
    timestamp: datetime
    price: float
    market_cap: float | None = None
    total_volume: float | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoPricePoint) -> "CryptoPricePointModel":
        return cls(**row.__dict__)


class CryptoDexPoolModel(BaseModel):
    pool_id: str
    network: str
    dex: str
    pair_name: str
    address: str
    quote_token_symbol: str | None = None
    base_token_price_usd: float | None = None
    fdv_usd: float | None = None
    market_cap_usd: float | None = None
    reserve_usd: float | None = None
    volume_24h: float | None = None
    price_change_pct_24h: float | None = None
    buys_24h: int
    sells_24h: int
    buyers_24h: int
    sellers_24h: int
    pool_created_at: datetime | None = None
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoDexPoolRecord) -> "CryptoDexPoolModel":
        return cls(**row.__dict__)


class CryptoDexLiquiditySummaryModel(BaseModel):
    token_id: str
    lookup_strategy: str
    matched_networks: list[str] = Field(default_factory=list)
    total_reserve_usd: float | None = None
    total_volume_24h: float | None = None
    total_buys_24h: int = 0
    total_sells_24h: int = 0
    total_buyers_24h: int = 0
    total_sellers_24h: int = 0
    dominant_dex: str | None = None
    pools: list[CryptoDexPoolModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoDexLiquiditySummary) -> "CryptoDexLiquiditySummaryModel":
        return cls(
            **{
                **row.__dict__,
                "pools": [CryptoDexPoolModel.from_domain(item) for item in row.pools],
            }
        )


class CryptoComparisonModel(BaseModel):
    subject_token_id: str
    target_kind: str
    target_id: str
    target_label: str
    shared_categories: list[str] = Field(default_factory=list)
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
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoComparisonRecord) -> "CryptoComparisonModel":
        return cls(**row.__dict__)


class CryptoFlowSummaryModel(BaseModel):
    token_id: str
    pool_count: int
    matched_networks: list[str] = Field(default_factory=list)
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
    liquidity_concentration_label: str
    flow_signal_label: str
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoFlowSummaryRecord) -> "CryptoFlowSummaryModel":
        return cls(**row.__dict__)


class CryptoWorkspaceResponseModel(BaseModel):
    tokens: list[CryptoTokenModel] = Field(default_factory=list)
    narratives: list[CryptoNarrativeBasketModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: CryptoWorkspaceResult) -> "CryptoWorkspaceResponseModel":
        return cls(
            tokens=[CryptoTokenModel.from_domain(item) for item in row.tokens],
            narratives=[CryptoNarrativeBasketModel.from_domain(item) for item in row.narratives],
            warnings=list(row.warnings),
        )


class CryptoPriceHistoryResponseModel(BaseModel):
    token_id: str
    points: list[CryptoPricePointModel] = Field(default_factory=list)


class CryptoSyntheticPositionRequestModel(BaseModel):
    identifier: str = Field(min_length=1, max_length=MAX_REQUEST_TEXT_CHARS)
    weight: float

    def to_domain(self) -> CryptoSyntheticPositionRequest:
        return CryptoSyntheticPositionRequest(
            identifier=self.identifier,
            weight=self.weight,
        )


class CryptoSyntheticPortfolioRequestModel(BaseModel):
    positions: list[CryptoSyntheticPositionRequestModel] = Field(
        default_factory=list,
        max_length=MAX_CRYPTO_PORTFOLIO_POSITIONS,
    )
    benchmark_token_id: str | None = Field(default=None, max_length=MAX_REQUEST_TEXT_CHARS)
    lookback_days: int = Field(default=30, ge=7, le=365)
    force_refresh: bool = False

    def to_domain(self) -> CryptoSyntheticPortfolioRequest:
        return CryptoSyntheticPortfolioRequest(
            positions=[item.to_domain() for item in self.positions],
            benchmark_token_id=self.benchmark_token_id,
            lookback_days=self.lookback_days,
            force_refresh=self.force_refresh,
        )


class CryptoPortfolioConstituentModel(BaseModel):
    token_id: str
    symbol: str
    name: str
    input_weight: float
    normalized_weight: float
    market_cap: float | None = None
    turnover_ratio_24h: float | None = None
    narrative_labels: list[str] = Field(default_factory=list)
    layer_bucket: str | None = None

    @classmethod
    def from_domain(cls, row: CryptoPortfolioConstituentRecord) -> "CryptoPortfolioConstituentModel":
        return cls(**row.__dict__)


class CryptoPortfolioNarrativeExposureModel(BaseModel):
    label: str
    normalized_weight: float
    constituent_count: int

    @classmethod
    def from_domain(
        cls,
        row: CryptoPortfolioNarrativeExposureRecord,
    ) -> "CryptoPortfolioNarrativeExposureModel":
        return cls(**row.__dict__)


class CryptoPortfolioPointModel(BaseModel):
    timestamp: datetime
    value: float

    @classmethod
    def from_domain(cls, row: CryptoPortfolioPoint) -> "CryptoPortfolioPointModel":
        return cls(**row.__dict__)


class CryptoSyntheticPortfolioResponseModel(BaseModel):
    lookback_days: int
    benchmark_token_id: str
    benchmark_label: str
    constituents: list[CryptoPortfolioConstituentModel] = Field(default_factory=list)
    narrative_exposures: list[CryptoPortfolioNarrativeExposureModel] = Field(default_factory=list)
    portfolio_points: list[CryptoPortfolioPointModel] = Field(default_factory=list)
    benchmark_points: list[CryptoPortfolioPointModel] = Field(default_factory=list)
    cumulative_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    relative_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    weighted_turnover_ratio_24h: float | None = None
    weighted_market_cap: float | None = None
    concentration_hhi: float | None = None
    effective_positions: float | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(
        cls,
        row: CryptoSyntheticPortfolioRecord,
    ) -> "CryptoSyntheticPortfolioResponseModel":
        return cls(
            **{
                **row.__dict__,
                "constituents": [CryptoPortfolioConstituentModel.from_domain(item) for item in row.constituents],
                "narrative_exposures": [
                    CryptoPortfolioNarrativeExposureModel.from_domain(item) for item in row.narrative_exposures
                ],
                "portfolio_points": [CryptoPortfolioPointModel.from_domain(item) for item in row.portfolio_points],
                "benchmark_points": [CryptoPortfolioPointModel.from_domain(item) for item in row.benchmark_points],
            }
        )
