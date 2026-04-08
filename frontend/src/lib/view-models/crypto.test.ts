import { describe, expect, it } from "vitest";
import type { CryptoToken } from "../api/types";
import { buildLayerTreemap, treemapArea } from "./crypto";

describe("buildLayerTreemap", () => {
  it("sizes tiles by market cap inside a layer", () => {
    const [section] = buildLayerTreemap(
      [
        makeToken({ token_id: "bitcoin", symbol: "btc", name: "Bitcoin", market_cap: 1_600_000_000_000, turnover_ratio_24h: 0.02 }),
        makeToken({ token_id: "ethereum", symbol: "eth", name: "Ethereum", market_cap: 320_000_000_000, turnover_ratio_24h: 0.04 }),
        makeToken({ token_id: "solana", symbol: "sol", name: "Solana", market_cap: 80_000_000_000, turnover_ratio_24h: 0.09 })
      ],
      "market_cap_desc"
    );

    const btcArea = treemapArea(section.tiles.find((tile) => tile.token.token_id === "bitcoin")!.rect);
    const ethArea = treemapArea(section.tiles.find((tile) => tile.token.token_id === "ethereum")!.rect);
    const solArea = treemapArea(section.tiles.find((tile) => tile.token.token_id === "solana")!.rect);

    expect(btcArea).toBeGreaterThan(ethArea);
    expect(ethArea).toBeGreaterThan(solArea);
  });

  it("re-sizes the same layer when the active sort metric changes", () => {
    const tokens = [
      makeToken({ token_id: "bitcoin", symbol: "btc", name: "Bitcoin", market_cap: 1_600_000_000_000, turnover_ratio_24h: 0.02 }),
      makeToken({ token_id: "ethereum", symbol: "eth", name: "Ethereum", market_cap: 320_000_000_000, turnover_ratio_24h: 0.04 }),
      makeToken({ token_id: "solana", symbol: "sol", name: "Solana", market_cap: 80_000_000_000, turnover_ratio_24h: 0.09 })
    ];
    const [marketCapSection] = buildLayerTreemap(tokens, "market_cap_desc");
    const [turnoverSection] = buildLayerTreemap(tokens, "turnover_desc");

    const btcMarketCapArea = treemapArea(marketCapSection.tiles.find((tile) => tile.token.token_id === "bitcoin")!.rect);
    const solMarketCapArea = treemapArea(marketCapSection.tiles.find((tile) => tile.token.token_id === "solana")!.rect);
    const btcTurnoverArea = treemapArea(turnoverSection.tiles.find((tile) => tile.token.token_id === "bitcoin")!.rect);
    const solTurnoverArea = treemapArea(turnoverSection.tiles.find((tile) => tile.token.token_id === "solana")!.rect);

    expect(btcMarketCapArea).toBeGreaterThan(solMarketCapArea);
    expect(solTurnoverArea).toBeGreaterThan(btcTurnoverArea);
  });

  it("keeps smaller layers explorable even when layer 1 dominates the raw metric", () => {
    const sections = buildLayerTreemap([
      makeToken({ token_id: "bitcoin", symbol: "btc", name: "Bitcoin", layer_bucket: "Layer 1", market_cap: 1_600_000_000_000 }),
      makeToken({ token_id: "ethereum", symbol: "eth", name: "Ethereum", layer_bucket: "Layer 1", market_cap: 320_000_000_000 }),
      makeToken({ token_id: "arbitrum", symbol: "arb", name: "Arbitrum", layer_bucket: "Layer 2", market_cap: 2_200_000_000 }),
      makeToken({ token_id: "optimism", symbol: "op", name: "Optimism", layer_bucket: "Layer 2", market_cap: 1_800_000_000 }),
      makeToken({ token_id: "eigenlayer", symbol: "eigen", name: "EigenLayer", layer_bucket: "Layer 3", market_cap: 1_400_000_000 })
    ]);

    const layer1Area = treemapArea(sections.find((section) => section.label === "Layer 1")!.rect);
    const layer2Area = treemapArea(sections.find((section) => section.label === "Layer 2")!.rect);
    const layer3Area = treemapArea(sections.find((section) => section.label === "Layer 3")!.rect);

    expect(layer1Area).toBeLessThan(80_00);
    expect(layer2Area).toBeGreaterThan(9_00);
    expect(layer3Area).toBeGreaterThan(8_00);
  });
});

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
    ...overrides
  };
}
