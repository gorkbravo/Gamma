import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type {
  CryptoComparison,
  CryptoDexLiquiditySummary,
  CryptoFlowSummary,
  CryptoPriceHistoryResponse,
  CryptoToken,
  CryptoWorkspaceResponse
} from "../lib/api/types";
import CryptoView from "./CryptoView.svelte";

describe("CryptoView", () => {
  it("renders the overview shell with the layer treemap and flow board", () => {
    const { body } = render(CryptoView, {
      props: {
        workspace: makeWorkspace(),
        detail: makeToken({
          token_id: "solana",
          symbol: "sol",
          name: "Solana",
          layer_bucket: "Layer 1",
          narrative_labels: ["Layer 1"],
        }),
        history: makeHistory(),
        liquidity: makeLiquidity(),
        flow: makeFlow(),
        comparison: makeComparison(),
        syntheticPortfolio: null,
        loading: false,
        portfolioLoading: false,
        onLoadWorkspace: vi.fn(),
        onSelectToken: vi.fn(),
        onRunSyntheticPortfolio: vi.fn(),
        onClearSyntheticPortfolio: vi.fn(),
      }
    });

    expect(body).toContain("Overview");
    expect(body).toContain("Deep Dive");
    expect(body).toContain("Flows &amp; Liquidity");
    expect(body).toContain("Layer Treemap");
    expect(body).toContain("Layer 1");
    expect(body).toContain("Layer 2");
    expect(body).toContain("Layer 3");
    expect(body).toContain("Flow Proxy Leaders");
    expect(body).toContain("Quick Take");
  });
});

function makeWorkspace(): CryptoWorkspaceResponse {
  return {
    tokens: [
      makeToken({
        token_id: "bitcoin",
        symbol: "btc",
        name: "Bitcoin",
        market_cap: 1_600_000_000_000,
        total_volume: 34_000_000_000,
        price_change_pct_24h: 2.1,
        turnover_ratio_24h: 0.021,
        layer_bucket: "Layer 1",
        narrative_labels: ["Layer 1"],
      }),
      makeToken({
        token_id: "solana",
        symbol: "sol",
        name: "Solana",
        market_cap: 80_000_000_000,
        total_volume: 5_000_000_000,
        price_change_pct_24h: 4.4,
        turnover_ratio_24h: 0.062,
        layer_bucket: "Layer 1",
        narrative_labels: ["Layer 1"],
      }),
      makeToken({
        token_id: "arbitrum",
        symbol: "arb",
        name: "Arbitrum",
        market_cap: 2_200_000_000,
        total_volume: 380_000_000,
        price_change_pct_24h: 5.2,
        turnover_ratio_24h: 0.17,
        layer_bucket: "Layer 2",
        narrative_labels: ["Layer 2"],
      }),
      makeToken({
        token_id: "eigenlayer",
        symbol: "eigen",
        name: "EigenLayer",
        market_cap: 1_400_000_000,
        total_volume: 210_000_000,
        price_change_pct_24h: -3.1,
        turnover_ratio_24h: 0.15,
        layer_bucket: "Layer 3",
        narrative_labels: ["Layer 3", "Infrastructure"],
      }),
    ],
    narratives: [
      {
        basket_id: "layer-1",
        label: "Layer 1",
        description: "Base-layer chains.",
        market_cap: 1_800_000_000_000,
        market_cap_change_pct_24h: 2.4,
        volume_24h: 40_000_000_000,
        top_tokens: [],
        source_provider: "coingecko",
        retrieved_at: "2026-04-08T17:00:00Z",
        origin: "coingecko.categories",
        transformation_note: null
      },
      {
        basket_id: "layer-2",
        label: "Layer 2",
        description: "Scaling assets.",
        market_cap: 35_000_000_000,
        market_cap_change_pct_24h: 4.8,
        volume_24h: 1_900_000_000,
        top_tokens: [],
        source_provider: "coingecko",
        retrieved_at: "2026-04-08T17:00:00Z",
        origin: "coingecko.categories",
        transformation_note: null
      }
    ],
    warnings: []
  };
}

function makeToken(overrides: Partial<CryptoToken>): CryptoToken {
  return {
    token_id: "token",
    symbol: "tok",
    name: "Token",
    image_url: null,
    chain: "Ethereum",
    asset_platform_id: "ethereum",
    geckoterminal_network: "eth",
    contract_address: null,
    market_cap_rank: 10,
    current_price: 10,
    market_cap: 10_000_000_000,
    fully_diluted_valuation: 12_000_000_000,
    total_volume: 1_000_000_000,
    circulating_supply: 1_000_000,
    total_supply: 1_200_000,
    max_supply: null,
    price_change_pct_24h: 1.5,
    price_change_pct_7d: 6,
    price_change_pct_30d: 15,
    market_cap_change_pct_24h: 1.2,
    high_24h: 11,
    low_24h: 9,
    homepage_url: null,
    description: "Token description.",
    categories: ["Layer 1"],
    narrative_labels: ["Layer 1"],
    layer_bucket: "Layer 1",
    turnover_ratio_24h: 0.1,
    fdv_premium_ratio: 0.2,
    screen_score: 80,
    screen_rationale: "turnover 0.10x | 24H volume $1.0B",
    source_provider: "coingecko",
    retrieved_at: "2026-04-08T17:00:00Z",
    origin: "coingecko.markets",
    transformation_note: "Gamma heuristic.",
    ...overrides,
  };
}

function makeHistory(): CryptoPriceHistoryResponse {
  return {
    token_id: "solana",
    points: [
      {
        timestamp: "2026-03-09T00:00:00Z",
        price: 120,
        market_cap: 60_000_000_000,
        total_volume: 4_000_000_000,
        source_provider: "coingecko",
        retrieved_at: "2026-04-08T17:00:00Z",
        origin: "coingecko.market_chart",
        transformation_note: null
      },
      {
        timestamp: "2026-04-08T00:00:00Z",
        price: 150,
        market_cap: 80_000_000_000,
        total_volume: 5_000_000_000,
        source_provider: "coingecko",
        retrieved_at: "2026-04-08T17:00:00Z",
        origin: "coingecko.market_chart",
        transformation_note: null
      }
    ]
  };
}

function makeLiquidity(): CryptoDexLiquiditySummary {
  return {
    token_id: "solana",
    lookup_strategy: "contract_lookup",
    matched_networks: ["solana"],
    total_reserve_usd: 220_000_000,
    total_volume_24h: 52_000_000,
    total_buys_24h: 12_400,
    total_sells_24h: 9_800,
    total_buyers_24h: 6_300,
    total_sellers_24h: 5_200,
    dominant_dex: "raydium",
    pools: [],
    warnings: [],
    source_provider: "geckoterminal",
    retrieved_at: "2026-04-08T17:00:00Z",
    origin: "geckoterminal.liquidity_summary",
    transformation_note: null,
  };
}

function makeFlow(): CryptoFlowSummary {
  return {
    token_id: "solana",
    pool_count: 2,
    matched_networks: ["solana"],
    total_reserve_usd: 220_000_000,
    total_volume_24h: 52_000_000,
    dex_volume_share_of_total_volume: 0.33,
    reserve_to_market_cap_ratio: 0.0027,
    top_pool_reserve_share: 0.62,
    top_pool_volume_share: 0.58,
    buy_pressure_pct: 56.8,
    active_trader_proxy_24h: 10_200,
    buy_sell_ratio: 1.03,
    participant_balance_ratio: 1.02,
    reserve_volume_ratio_24h: 4.23,
    slippage_proxy_label: "deep",
    liquidity_concentration_label: "moderately concentrated",
    flow_signal_label: "accumulation",
    summary: "Flow is constructive with deep pool support.",
    warnings: [],
    source_provider: "gamma",
    retrieved_at: "2026-04-08T17:00:00Z",
    origin: "gamma.crypto.flow_summary",
    transformation_note: null,
  };
}

function makeComparison(): CryptoComparison {
  return {
    subject_token_id: "solana",
    target_kind: "basket",
    target_id: "layer-1",
    target_label: "Layer 1",
    shared_categories: ["Layer 1"],
    subject_price_change_pct_24h: 4.4,
    target_price_change_pct_24h: 2.4,
    price_gap_pct_24h: 2,
    subject_price_change_pct_7d: 10,
    target_price_change_pct_7d: 5,
    price_gap_pct_7d: 5,
    subject_price_change_pct_30d: 18,
    target_price_change_pct_30d: 11,
    price_gap_pct_30d: 7,
    subject_market_cap: 80_000_000_000,
    target_market_cap: 1_800_000_000_000,
    market_cap_ratio: 0.044,
    subject_turnover_ratio_24h: 0.062,
    target_turnover_ratio_24h: 0.03,
    turnover_gap: 0.032,
    summary: "Solana is outrunning the Layer 1 basket.",
    source_provider: "gamma",
    retrieved_at: "2026-04-08T17:00:00Z",
    origin: "gamma.crypto.comparison.basket",
    transformation_note: null,
  };
}
