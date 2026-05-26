import { describe, expect, it } from "vitest";
import { derivePortfolioDiagnostics, filterAndSortPositions } from "./portfolio";

const positions = [
  {
    symbol: "CASHUSD",
    sec_type: "CASH",
    currency: "USD",
    quantity: 1000,
    avg_cost: null,
    market_price: 1,
    market_value: 1000,
    unrealized_pnl: 0,
    weight: 0.25,
    base_market_value: 1000,
    fx_rate: 1,
    instrument_id: "cash:usd",
    display_symbol: "USD Cash",
    exchange: null,
    primary_exchange: null,
    provider: "portfolio",
    provider_id: "USD"
  },
  {
    symbol: "MSFT",
    sec_type: "STK",
    currency: "USD",
    quantity: 5,
    avg_cost: 300,
    market_price: 320,
    market_value: 1600,
    unrealized_pnl: 100,
    weight: 0.4,
    base_market_value: 1600,
    fx_rate: 1,
    instrument_id: "portfolio:stk:msft",
    display_symbol: "MSFT",
    exchange: "SMART",
    primary_exchange: "NASDAQ",
    provider: "ibkr",
    provider_id: "MSFT"
  },
  {
    symbol: "SAP",
    sec_type: "STK",
    currency: "EUR",
    quantity: 10,
    avg_cost: 120,
    market_price: 110,
    market_value: 1100,
    unrealized_pnl: -100,
    weight: 0.35,
    base_market_value: 1100,
    fx_rate: 1.08,
    instrument_id: "portfolio:stk:sap",
    display_symbol: "SAP",
    exchange: "SMART",
    primary_exchange: "XETRA",
    provider: "ibkr",
    provider_id: "SAP"
  }
];

describe("portfolio view model helpers", () => {
  it("filters and sorts positions for the browser table", () => {
    const filtered = filterAndSortPositions(positions, {
      search: "st",
      sortKey: "base_market_value",
      descending: true,
      includeCash: false
    });

    expect(filtered.map((position) => position.symbol)).toEqual(["MSFT", "SAP"]);
  });

  it("derives portfolio diagnostics from the snapshot", () => {
    const diagnostics = derivePortfolioDiagnostics({
      timestamp: "2026-03-01T00:00:00Z",
      base_currency: "USD",
      account_summary: {},
      positions,
      total_market_value: 2700,
      total_cash: 1000,
      net_liquidation: 3700,
      day_pnl: 0,
      day_pnl_pct: 0,
      day_pnl_source: "account_summary",
      warnings: []
    });

    expect(diagnostics.largestPosition?.symbol).toBe("MSFT");
    expect(diagnostics.bestPnl?.symbol).toBe("MSFT");
    expect(diagnostics.worstPnl?.symbol).toBe("SAP");
    expect(diagnostics.cashWeight).toBeCloseTo(1000 / 3700);
  });
});
