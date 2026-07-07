import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { ResearchOverviewResponse } from "../lib/api/types";
import SitrepView from "./SitrepView.svelte";

describe("SitrepView", () => {
  it("labels index moves as latest-day returns and shows the proxy/as-of pivot", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: makeGlobalIndicesOverview(),
        news: null,
        macro: null,
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
      },
    });

    expect(body).toContain("Latest daily close / Jun 26");
    expect(body).toContain("Latest Day");
    expect(body).toContain("Latest Day %");
    expect(body).toContain("Proxy / As Of");
    expect(body).toContain("EWJ / Jun 26");
    expect(body).toContain("-4.2%");
  });
});

function makeGlobalIndicesOverview(): ResearchOverviewResponse {
  return {
    universe_id: "global_indices",
    universe_label: "Global Indices",
    universe_description: "Curated cash-index board.",
    timeframe: "DoD",
    lookback_days: 1,
    benchmark_symbol: "SPY",
    available_universes: [],
    available_timeframes: ["DoD", "1M"],
    metric_options: [],
    sort_options: [],
    nodes: [
      {
        node_id: "instrument:^N225",
        normalized_id: "index:^N225",
        label: "Nikkei 225",
        level: "instrument",
        parent_id: "group:japan",
        group: "Japan",
        sector: "Japan",
        industry: null,
        symbol: "^N225",
        instrument_id: "index:^N225",
        weight: 1,
        market_cap_usd: null,
        index_weight: null,
        sort_rank: 11,
        size: 1,
        metrics: {
          total_return: -0.04153,
          latest_daily_return: -0.04153,
          latest_daily_return_at: "2026-06-26T00:00:00Z",
          annual_volatility: null,
          beta: null,
          max_drawdown: null,
          relative_return: -0.0343,
          latest_price: 69360.88,
          observation_count: 1,
        },
        source_provider: "yfinance",
        retrieved_at: "2026-06-27T20:20:15Z",
        origin: "research_service.overview.instrument",
        transformation_note: "Computed from daily close history.",
        freshness_label: "historical",
        warnings: [],
      },
    ],
    coverage: {
      instrument_count: 1,
      priced_count: 1,
      missing_symbols: [],
      benchmark_symbol: "SPY",
      benchmark_available: true,
      benchmark_observation_count: 1,
      coverage_ratio: 1,
      missing_count: 0,
      thin_history_symbols: [],
      min_observation_count: 1,
      max_observation_count: 1,
      coverage_label: "Curated global cash-index board",
      history_source_label: "Yahoo Finance/yfinance daily history",
      metadata_source_label: "Curated Gamma global cash-index symbol list",
    },
    rankings: {
      leaders: [],
      laggards: [],
      highest_volatility: [],
      highest_beta: [],
      largest_drawdowns: [],
    },
    summary: {
      leading_group: null,
      lagging_group: null,
      highest_volatility_group: null,
      coverage_note: null,
    },
    warnings: [],
    source_provider: "yfinance",
    retrieved_at: "2026-06-27T20:20:15Z",
    origin: "research_service.overview",
    transformation_note: "Computed from daily close histories.",
    freshness_label: "historical",
    history_source_label: "Yahoo Finance/yfinance daily history",
    metadata_source_label: "Curated Gamma global cash-index symbol list",
    coverage_label: "Curated global cash-index board",
  };
}
