import { describe, expect, it } from "vitest";
import type { ResearchResult } from "./api/types";
import { buildIvRequestFromResearch, buildRiskRequestFromResearch } from "./workspace";

describe("workspace context forwarding", () => {
  it("builds a risk request from a research result", () => {
    const request = buildRiskRequestFromResearch(makeResearchResult("single_ticker"));

    expect(request?.snapshot?.positions[0].symbol).toBe("AAPL");
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
    observations_count: 10,
    snapshot: {
      timestamp: "2026-03-01T00:00:00Z",
      base_currency: "USD",
      account_summary: {},
      positions: [
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
      ],
      total_market_value: 110,
      total_cash: 0,
      net_liquidation: 110,
      day_pnl: 1,
      day_pnl_pct: 0.01,
      day_pnl_source: "account_summary",
      warnings: []
    },
    performance_points: [],
    benchmark_points: [],
    primary_price_points: [],
    weights: [{ symbol: "AAPL", weight: 1 }],
    summary: {
      total_return: null,
      annual_return: null,
      annual_vol: null,
      max_drawdown: null,
      beta: null,
      correlation: null
    },
    warnings: []
  };
}
