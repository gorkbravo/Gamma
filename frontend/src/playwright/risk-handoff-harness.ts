import "../lib/theme/tokens.css";
import { mount } from "svelte";
import RiskView from "../views/RiskView.svelte";
import type { PortfolioSnapshot, Position, RiskResult } from "../lib/api/types";
import type { RiskComputeOptions, StrategyLabResearchBook } from "../lib/stores/app";

declare global {
  interface Window {
    __gammaRiskComputes: Array<{ sourceScope: string; riskSourceLabel: string; symbols: string[] }>;
  }
}

window.__gammaRiskComputes = [];

/**
 * Account and book use deliberately distinctive symbols so a mixed screen is
 * visible rather than plausible: any ACCTONLY row under a book header is the
 * GUA-20260903-7 defect.
 */
function position(symbol: string, marketValue: number, weight: number, unrealizedPnl: number): Position {
  return {
    symbol,
    sec_type: "STK",
    currency: "USD",
    quantity: 100,
    avg_cost: 100,
    market_price: marketValue / 100,
    market_value: marketValue,
    unrealized_pnl: unrealizedPnl,
    weight,
    base_market_value: marketValue,
    fx_rate: 1,
    instrument_id: `portfolio:stk:${symbol.toLowerCase()}`,
    display_symbol: symbol,
    exchange: "SMART",
    primary_exchange: "NASDAQ",
    provider: "ibkr",
    provider_id: symbol,
  };
}

const accountSnapshot: PortfolioSnapshot = {
  timestamp: "2026-09-03T15:00:00Z",
  base_currency: "USD",
  account_summary: {},
  total_market_value: 200000,
  total_cash: 0,
  net_liquidation: 200000,
  day_pnl: -1500,
  day_pnl_pct: -0.0075,
  day_pnl_source: "broker",
  warnings: [],
  positions: [position("ACCTONLY", 140000, 0.7, -4200), position("ACCTMINOR", 60000, 0.3, 900)],
};

const bookSnapshot: PortfolioSnapshot = {
  timestamp: "2026-09-03T15:00:00Z",
  base_currency: "USD",
  account_summary: {},
  total_market_value: 0,
  total_cash: 0,
  net_liquidation: 0,
  day_pnl: null,
  day_pnl_pct: null,
  day_pnl_source: "derived",
  warnings: ["Research book. Not an account."],
  positions: [],
};

const returnPoints = Array.from({ length: 40 }, (_, index) => ({
  timestamp: new Date(Date.UTC(2026, 6, 1 + index)).toISOString(),
  value: index % 5 === 0 ? -0.011 : 0.004,
}));

const researchBook = {
  bookId: "book-gold-duration",
  sourceLabel: "BOOKLEG Gold vs Duration",
  snapshot: bookSnapshot,
  benchmarkSymbol: "SPY",
  createdAt: "2026-09-03T15:00:00Z",
  warnings: [],
  object: {
    object_id: "strategy_lab:book-gold-duration",
    object_type: "composition",
    display_name: "BOOKLEG Gold vs Duration",
    source_tab: "strategy_lab",
    source_mode: "composer",
    resolver_capabilities: [],
    symbols: ["BOOKLEG-GLD", "BOOKLEG-TLT"],
    constituents: [],
    weights: [],
    available_start: "2026-07-01",
    available_end: "2026-09-03",
    provider_summary: "yfinance",
    provenance: { origin: "strategy_lab" },
    warnings: [],
    return_points: returnPoints,
    risk_legs: [],
  },
  // RiskView reads sourceLabel, snapshot and the object; validation and
  // composition are carried by the store and are not part of this regression.
  validation: {
    valid: true,
    errors: [],
    warnings: [],
    usable_leg_count: 2,
    requested_leg_count: 2,
    aligned_observation_count: returnPoints.length,
    min_observations: 30,
    alignment_diagnostics: {},
    retrieved_at: "2026-09-03T15:00:00Z",
    origin: "strategy_lab",
  },
  composition: null,
} as unknown as StrategyLabResearchBook;

const bookResult: RiskResult = {
  source_scope: "research_book",
  source_label: "BOOKLEG Gold vs Duration",
  source_object_id: "strategy_lab:book-gold-duration",
  source_origin: "strategy_lab",
  metrics: {
    alpha: 0.95,
    lookback_days: 252,
    horizon_days: 1,
    portfolio_value: 0,
    historical_var: -0.021,
    historical_cvar: -0.03,
    parametric_var: -0.02,
    daily_vol: 0.008,
    annual_vol: 0.127,
    max_drawdown: -0.1431,
    beta: 0.37,
    correlation: 0.38,
    alpha_annual: 0.04,
    covered_portfolio_value: null,
    covered_risk_basis_value: null,
    risk_basis_value: null,
    risk_coverage_ratio: 1,
    historical_var_total_estimate: null,
    historical_cvar_total_estimate: null,
    parametric_var_total_estimate: null,
    monte_carlo_model: "Gaussian",
    monte_carlo_horizon_days: 10,
    monte_carlo_num_simulations: 2000,
    monte_carlo_var: null,
    monte_carlo_cvar: null,
    monte_carlo_var_total_estimate: null,
    monte_carlo_cvar_total_estimate: null,
    aligned_obs_count: returnPoints.length,
    benchmark_overlap_count: returnPoints.length,
    concentration_hhi: null,
    top5_weight: null,
    effective_bets: 1.4,
  },
  portfolio_return_points: returnPoints,
  benchmark_return_points: returnPoints.map((point) => ({ ...point, value: point.value * 0.6 })),
  contributions: [
    {
      symbol: "BOOKLEG-GLD",
      instrument_id: "strategy_lab:leg:gld",
      display_symbol: "BOOKLEG-GLD",
      weight: 0.5,
      daily_vol: 0.009,
      variance_contribution_pct: 0.935,
      marginal_contribution_to_risk: 0.008,
      component_var: null,
    },
    {
      symbol: "BOOKLEG-TLT",
      instrument_id: "strategy_lab:leg:tlt",
      display_symbol: "BOOKLEG-TLT",
      weight: -0.5,
      daily_vol: 0.007,
      variance_contribution_pct: 0.065,
      marginal_contribution_to_risk: 0.001,
      component_var: null,
    },
  ],
  monte_carlo: { terminal_returns: [], fan_percentiles: {}, sample_paths: {} },
  frontier_points: [],
  correlation_matrix: { assets: [], cells: [] },
  dependency_network: {
    nodes: [],
    edges: [],
    clusters: [],
    methodology: null,
    universe_size: 0,
    observation_count: 0,
    edge_threshold: null,
    warnings: [],
    source_provider: "risk_service",
  },
  excluded_assets: [],
  warnings: [],
};

mount(RiskView, {
  target: document.getElementById("app")!,
  props: {
    mode: "portfolio",
    activeMode: "overview",
    snapshot: accountSnapshot,
    researchSnapshot: null,
    strategyLabResearchBook: researchBook,
    result: bookResult,
    workingAnalysis: null,
    loading: false,
    onCompute: (options: RiskComputeOptions) => {
      window.__gammaRiskComputes.push({
        sourceScope: options.sourceScope ?? "",
        riskSourceLabel: options.riskSourceLabel ?? "",
        symbols: (options.snapshot?.positions ?? []).map((entry) => entry.symbol),
      });
    },
  },
});
