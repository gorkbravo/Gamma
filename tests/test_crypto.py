from __future__ import annotations

from datetime import datetime, timezone

from src.application.crypto_service import CryptoService
from src.models.crypto import (
    CryptoBasketConstituent,
    CryptoDexLiquiditySummary,
    CryptoDexPoolRecord,
    CryptoNarrativeBasketRecord,
    CryptoPricePoint,
    CryptoSyntheticPortfolioRequest,
    CryptoSyntheticPositionRequest,
    CryptoScreenerRequest,
    CryptoTokenRecord,
)


def test_crypto_service_filters_workspace_and_attaches_network_context():
    service = CryptoService(
        market_adapter=_FakeMarketAdapter(),
        dex_adapter=_FakeDexAdapter(),
    )

    result = service.get_workspace(
        CryptoScreenerRequest(
            narrative="Layer 1",
            min_turnover_ratio=0.04,
            sort_by="screen_score_desc",
            limit=10,
        )
    )

    assert [row.token_id for row in result.tokens] == ["solana"]
    assert result.tokens[0].screen_score is not None
    assert result.tokens[0].geckoterminal_network == "solana"
    assert result.tokens[0].screen_rationale is not None
    assert [row.label for row in result.narratives] == ["Layer 1", "DeFi"]


def test_crypto_service_falls_back_to_internal_layer_baskets_when_narratives_fail():
    service = CryptoService(
        market_adapter=_FailingNarrativeMarketAdapter(),
        dex_adapter=_FakeDexAdapter(),
    )

    result = service.get_workspace(CryptoScreenerRequest(limit=10))

    layer_map = {row.token_id: row.layer_bucket for row in result.tokens}
    assert layer_map["bitcoin"] == "Layer 1"
    assert layer_map["solana"] == "Layer 1"
    assert layer_map["uniswap"] == "Layer 2"
    assert [row.label for row in result.narratives] == ["Layer 1", "Layer 2"]
    assert any("fell back to internal layer baskets" in warning for warning in result.warnings)


def test_crypto_service_defaults_comparison_to_matching_narrative_basket():
    service = CryptoService(
        market_adapter=_FakeMarketAdapter(),
        dex_adapter=_FakeDexAdapter(),
    )

    comparison = service.get_comparison("solana")

    assert comparison is not None
    assert comparison.target_kind == "basket"
    assert comparison.target_label == "Layer 1"
    assert comparison.target_id == "layer-1"
    assert comparison.summary is not None


def test_crypto_service_builds_flow_summary_from_dex_proxy_data():
    service = CryptoService(
        market_adapter=_FakeMarketAdapter(),
        dex_adapter=_FakeDexAdapter(),
    )

    summary = service.get_flow_summary("solana")

    assert summary is not None
    assert summary.pool_count == 2
    assert summary.flow_signal_label == "accumulation"
    assert summary.liquidity_concentration_label in {"moderately concentrated", "highly concentrated"}
    assert summary.slippage_proxy_label in {"deep", "workable", "thin", "fragile"}
    assert summary.summary is not None


def test_crypto_service_builds_synthetic_portfolio_from_symbol_inputs():
    service = CryptoService(
        market_adapter=_FakeMarketAdapter(),
        dex_adapter=_FakeDexAdapter(),
    )

    result = service.analyze_synthetic_portfolio(
        CryptoSyntheticPortfolioRequest(
            positions=[
                CryptoSyntheticPositionRequest(identifier="SOL", weight=0.6),
                CryptoSyntheticPositionRequest(identifier="UNI", weight=0.4),
            ],
            benchmark_token_id="bitcoin",
            lookback_days=30,
        )
    )

    assert result is not None
    assert result.benchmark_token_id == "bitcoin"
    assert [row.token_id for row in result.constituents] == ["solana", "uniswap"]
    assert len(result.portfolio_points) >= 2
    assert result.relative_return_pct is not None
    assert result.effective_positions is not None
    assert any(exposure.label == "Layer 1" for exposure in result.narrative_exposures)
    assert any(exposure.label == "DeFi" for exposure in result.narrative_exposures)


class _FakeMarketAdapter:
    provider = "coingecko"

    def __init__(self) -> None:
        retrieved_at = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        self._tokens = {
            "bitcoin": _token(
                token_id="bitcoin",
                symbol="btc",
                name="Bitcoin",
                chain="Bitcoin",
                asset_platform_id="bitcoin",
                market_cap_rank=1,
                market_cap=1_600_000_000_000,
                total_volume=35_000_000_000,
                price_change_pct_24h=2.0,
                price_change_pct_7d=6.0,
                price_change_pct_30d=12.0,
                turnover_ratio_24h=0.022,
                categories=["Layer 1"],
                retrieved_at=retrieved_at,
            ),
            "solana": _token(
                token_id="solana",
                symbol="sol",
                name="Solana",
                chain="Solana",
                asset_platform_id="solana",
                market_cap_rank=5,
                market_cap=78_000_000_000,
                total_volume=5_200_000_000,
                price_change_pct_24h=4.3,
                price_change_pct_7d=12.1,
                price_change_pct_30d=18.4,
                turnover_ratio_24h=0.067,
                categories=["Layer 1", "Smart Contract Platform"],
                retrieved_at=retrieved_at,
            ),
            "uniswap": _token(
                token_id="uniswap",
                symbol="uni",
                name="Uniswap",
                chain="Ethereum",
                asset_platform_id="ethereum",
                market_cap_rank=28,
                market_cap=8_000_000_000,
                total_volume=320_000_000,
                price_change_pct_24h=1.5,
                price_change_pct_7d=4.0,
                price_change_pct_30d=7.2,
                turnover_ratio_24h=0.04,
                categories=["DeFi"],
                retrieved_at=retrieved_at,
            ),
        }
        self._narratives = [
            CryptoNarrativeBasketRecord(
                basket_id="layer-1",
                label="Layer 1",
                description="Base-layer chains.",
                market_cap=1_700_000_000_000,
                market_cap_change_pct_24h=2.2,
                volume_24h=40_000_000_000,
                top_tokens=[
                    CryptoBasketConstituent(token_id="bitcoin", name="Bitcoin", symbol="BTC"),
                    CryptoBasketConstituent(token_id="solana", name="Solana", symbol="SOL"),
                ],
                source_provider="coingecko",
                retrieved_at=retrieved_at,
                origin="coingecko.categories",
            ),
            CryptoNarrativeBasketRecord(
                basket_id="defi",
                label="DeFi",
                description="DeFi protocols.",
                market_cap=60_000_000_000,
                market_cap_change_pct_24h=1.0,
                volume_24h=3_000_000_000,
                top_tokens=[
                    CryptoBasketConstituent(token_id="uniswap", name="Uniswap", symbol="UNI"),
                ],
                source_provider="coingecko",
                retrieved_at=retrieved_at,
                origin="coingecko.categories",
            ),
        ]

    def list_tokens(self, *, limit: int = 40, force_refresh: bool = False):
        del force_refresh
        return list(self._tokens.values())[:limit]

    def search_tokens(self, query: str, *, limit: int = 40, force_refresh: bool = False):
        del force_refresh
        normalized = query.lower()
        rows = [
            row
            for row in self._tokens.values()
            if normalized in row.token_id or normalized in row.name.lower() or normalized in row.symbol.lower()
        ]
        return rows[:limit]

    def get_token(self, token_id: str, *, force_refresh: bool = False):
        del force_refresh
        return self._tokens.get(token_id)

    def get_price_history(self, token_id: str, *, days: int = 30, force_refresh: bool = False):
        del days, force_refresh
        token = self._tokens[token_id]
        return [
            CryptoPricePoint(
                timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
                price=(token.current_price or 0.0) * 0.9,
                market_cap=token.market_cap,
                total_volume=token.total_volume,
                source_provider="coingecko",
                retrieved_at=token.retrieved_at,
                origin="coingecko.market_chart",
            ),
            CryptoPricePoint(
                timestamp=datetime(2026, 4, 5, tzinfo=timezone.utc),
                price=token.current_price or 0.0,
                market_cap=token.market_cap,
                total_volume=token.total_volume,
                source_provider="coingecko",
                retrieved_at=token.retrieved_at,
                origin="coingecko.market_chart",
            ),
        ]

    def get_narrative_baskets(self, *, force_refresh: bool = False, token_index=None):
        del force_refresh, token_index
        return list(self._narratives)


class _FailingNarrativeMarketAdapter(_FakeMarketAdapter):
    def get_narrative_baskets(self, *, force_refresh: bool = False, token_index=None):
        del force_refresh, token_index
        raise RuntimeError("HTTP Error 429: Too Many Requests")


class _FakeDexAdapter:
    provider = "geckoterminal"

    def get_network_map(self, *, force_refresh: bool = False):
        del force_refresh
        return {
            "bitcoin": "bitcoin",
            "solana": "solana",
            "ethereum": "eth",
        }

    def get_liquidity_summary(self, token: CryptoTokenRecord, *, force_refresh: bool = False):
        del force_refresh
        return CryptoDexLiquiditySummary(
            token_id=token.token_id,
            lookup_strategy="contract_lookup",
            matched_networks=[token.geckoterminal_network or token.asset_platform_id or "unknown"],
            total_reserve_usd=220_000_000.0 if token.token_id == "solana" else 42_000_000.0,
            total_volume_24h=52_000_000.0 if token.token_id == "solana" else 8_000_000.0,
            total_buys_24h=13_600 if token.token_id == "solana" else 2_400,
            total_sells_24h=9_200 if token.token_id == "solana" else 2_100,
            total_buyers_24h=6_300 if token.token_id == "solana" else 1_200,
            total_sellers_24h=5_200 if token.token_id == "solana" else 1_100,
            dominant_dex="raydium" if token.token_id == "solana" else "uniswap",
            pools=[
                CryptoDexPoolRecord(
                    pool_id=f"{token.token_id}-pool-a",
                    network=token.geckoterminal_network or token.asset_platform_id or "unknown",
                    dex="raydium" if token.token_id == "solana" else "uniswap",
                    pair_name=f"{token.symbol.upper()}/USDC",
                    address="pool-a",
                    quote_token_symbol="USDC",
                    base_token_price_usd=token.current_price,
                    fdv_usd=token.fully_diluted_valuation,
                    market_cap_usd=token.market_cap,
                    reserve_usd=140_000_000.0 if token.token_id == "solana" else 22_000_000.0,
                    volume_24h=31_000_000.0 if token.token_id == "solana" else 4_800_000.0,
                    price_change_pct_24h=token.price_change_pct_24h,
                    buys_24h=7_000 if token.token_id == "solana" else 1_300,
                    sells_24h=5_100 if token.token_id == "solana" else 1_000,
                    buyers_24h=3_700 if token.token_id == "solana" else 700,
                    sellers_24h=2_900 if token.token_id == "solana" else 520,
                    source_provider="geckoterminal",
                    retrieved_at=token.retrieved_at,
                    origin="geckoterminal.pools",
                ),
                CryptoDexPoolRecord(
                    pool_id=f"{token.token_id}-pool-b",
                    network=token.geckoterminal_network or token.asset_platform_id or "unknown",
                    dex="orca" if token.token_id == "solana" else "sushiswap",
                    pair_name=f"{token.symbol.upper()}/USDT",
                    address="pool-b",
                    quote_token_symbol="USDT",
                    base_token_price_usd=token.current_price,
                    fdv_usd=token.fully_diluted_valuation,
                    market_cap_usd=token.market_cap,
                    reserve_usd=80_000_000.0 if token.token_id == "solana" else 20_000_000.0,
                    volume_24h=21_000_000.0 if token.token_id == "solana" else 3_200_000.0,
                    price_change_pct_24h=token.price_change_pct_24h,
                    buys_24h=5_400 if token.token_id == "solana" else 1_100,
                    sells_24h=4_700 if token.token_id == "solana" else 1_100,
                    buyers_24h=2_600 if token.token_id == "solana" else 500,
                    sellers_24h=2_300 if token.token_id == "solana" else 580,
                    source_provider="geckoterminal",
                    retrieved_at=token.retrieved_at,
                    origin="geckoterminal.pools",
                ),
            ],
            warnings=[],
            source_provider="geckoterminal",
            retrieved_at=token.retrieved_at,
            origin="geckoterminal.liquidity_summary",
        )


def _token(
    *,
    token_id: str,
    symbol: str,
    name: str,
    chain: str,
    asset_platform_id: str,
    market_cap_rank: int,
    market_cap: float,
    total_volume: float,
    price_change_pct_24h: float,
    price_change_pct_7d: float,
    price_change_pct_30d: float,
    turnover_ratio_24h: float,
    categories: list[str],
    retrieved_at: datetime,
) -> CryptoTokenRecord:
    return CryptoTokenRecord(
        token_id=token_id,
        symbol=symbol,
        name=name,
        image_url=None,
        chain=chain,
        asset_platform_id=asset_platform_id,
        geckoterminal_network=None,
        contract_address=None,
        market_cap_rank=market_cap_rank,
        current_price=1.0,
        market_cap=market_cap,
        fully_diluted_valuation=market_cap * 1.15,
        total_volume=total_volume,
        circulating_supply=1.0,
        total_supply=1.0,
        max_supply=None,
        price_change_pct_24h=price_change_pct_24h,
        price_change_pct_7d=price_change_pct_7d,
        price_change_pct_30d=price_change_pct_30d,
        market_cap_change_pct_24h=price_change_pct_24h,
        high_24h=1.0,
        low_24h=1.0,
        homepage_url=None,
        description=None,
        categories=categories,
        turnover_ratio_24h=turnover_ratio_24h,
        fdv_premium_ratio=0.15,
        screen_score=None,
        screen_rationale=None,
        source_provider="coingecko",
        retrieved_at=retrieved_at,
        origin="coingecko.markets",
        transformation_note=None,
    )
