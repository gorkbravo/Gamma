import { describe, expect, it } from "vitest";
import type { ResearchResult } from "./api/types";
import { buildIvRequestFromResearch, buildRiskRequestFromResearch } from "./workspace";

describe("workspace context forwarding", () => {
  it("builds a risk request from a research result", () => {
    const request = buildRiskRequestFromResearch(makeResearchResult("single_ticker"));

    expect(request?.snapshot?.positions[0].symbol).toBe("AAPL");
    expect(request?.benchmarkSymbol).toBe("SPY");
  });

  it("forwards the latest synthetic research snapshot to risk", () => {
    const request = buildRiskRequestFromResearch(makeResearchResult("synthetic_portfolio"));

    expect(request?.snapshot?.positions.map((position) => position.symbol)).toEqual(["XLV", "XLP", "XLU"]);
    expect(request?.benchmarkSymbol).toBe("SPY");
  });

  it("only forwards IV context for single-ticker research", () => {
    expect(buildIvRequestFromResearch(makeResearchResult("synthetic_portfolio"), "live")).toBeNull();
    expect(buildIvRequestFromResearch(makeResearchResult("single_ticker"), "live")).toEqual({
      symbol: "AAPL",
      marketDataMode: "live"
    });
  });
});

function makeResearchResult(scope: string): ResearchResult {
  return {
    scope_type: scope,
    benchmark_symbol: "SPY",
    primary_symbol: scope === "single_ticker" ? "AAPL" : null,
    observations_count: 10,
    snapshot: {
      timestamp: "2026-03-01T00:00:00Z",
      base_currency: "USD",
      account_summary: {},
      positions: scope === "single_ticker"
        ? [
            {
              symbol: "AAPL",
              sec_type: "STK",
              currency: "USD",
              quantity: 1,
              avg_cost: 100,
              market_price: 110,
              market_value: 110,
              unrealized_pnl: 10,
              weight: 1,
              base_market_value: 110,
              fx_rate: 1
            }
          ]
        : [
            {
              symbol: "XLV",
              sec_type: "STK",
              currency: "USD",
              quantity: 0.35,
              avg_cost: 100,
              market_price: 110,
              market_value: 35,
              unrealized_pnl: 10,
              weight: 0.35,
              base_market_value: 35,
              fx_rate: 1
            },
            {
              symbol: "XLP",
              sec_type: "STK",
              currency: "USD",
              quantity: 0.35,
              avg_cost: 100,
              market_price: 110,
              market_value: 35,
              unrealized_pnl: 10,
              weight: 0.35,
              base_market_value: 35,
              fx_rate: 1
            },
            {
              symbol: "XLU",
              sec_type: "STK",
              currency: "USD",
              quantity: 0.3,
              avg_cost: 100,
              market_price: 110,
              market_value: 30,
              unrealized_pnl: 10,
              weight: 0.3,
              base_market_value: 30,
              fx_rate: 1
            }
          ],
      total_market_value: 100,
      total_cash: 0,
      net_liquidation: 100,
      day_pnl: 1,
      day_pnl_pct: 0.01,
      day_pnl_source: "account_summary",
      warnings: []
    },
    performance_points: [],
    benchmark_points: [],
    primary_price_points: scope === "single_ticker" ? [] : [],
    weights: scope === "single_ticker"
      ? [{ symbol: "AAPL", weight: 1 }]
      : [
          { symbol: "XLV", weight: 0.35 },
          { symbol: "XLP", weight: 0.35 },
          { symbol: "XLU", weight: 0.3 }
        ],
    summary: {
      total_return: null,
      annual_return: null,
      annual_vol: null,
      max_drawdown: null,
      beta: null,
      correlation: null
    },
    structure: {
      total_weight: 1,
      top_weight: 1,
      top5_weight: 1,
      concentration_hhi: 1,
      effective_positions: 1,
      aligned_symbol_count: scope === "single_ticker" ? 1 : 3
    },
    coverage: {
      available_symbols: scope === "single_ticker" ? ["AAPL"] : ["XLV", "XLP", "XLU"],
      missing_symbols: [],
      benchmark_overlap_count: 10
    },
    constituents: scope === "single_ticker"
      ? [
          {
            symbol: "AAPL",
            weight: 1,
            total_return: 0.1,
            annual_vol: 0.2,
            max_drawdown: -0.05,
            weighted_return: 0.1
          }
        ]
      : [
          {
            symbol: "XLV",
            weight: 0.35,
            total_return: 0.1,
            annual_vol: 0.2,
            max_drawdown: -0.05,
            weighted_return: 0.035
          },
          {
            symbol: "XLP",
            weight: 0.35,
            total_return: 0.1,
            annual_vol: 0.2,
            max_drawdown: -0.05,
            weighted_return: 0.035
          },
          {
            symbol: "XLU",
            weight: 0.3,
            total_return: 0.1,
            annual_vol: 0.2,
            max_drawdown: -0.05,
            weighted_return: 0.03
          }
        ],
    warnings: []
  };
}
