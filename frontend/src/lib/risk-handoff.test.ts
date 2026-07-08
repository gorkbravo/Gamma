import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PortfolioSnapshot, RiskResult, TabId } from "./api/types";
import { activeTab, computeRisk, lastError, loading, riskResult, type RiskComputeOptions, type StrategyLabResearchBook } from "./stores/app";
import { createRiskHandoffController } from "./risk-handoff";

describe("risk compute idempotency", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    activeTab.set("strategy_lab");
    riskResult.set(null);
    lastError.set("");
    loading.set({
      status: false,
      diagnostics: false,
      providerUsage: false,
      diagnosticsAction: false,
      portfolio: false,
      portfolioAction: false,
      researchOverview: false,
      research: false,
      strategyLab: false,
      strategyLabHandoff: false,
      compareScenario: false,
      savedResearch: false,
      macro: false,
      macroHistory: false,
      news: false,
      commodities: false,
      maritime: false,
      prediction: false,
      predictionDetail: false,
      crypto: false,
      cryptoDetail: false,
      cryptoPortfolio: false,
      fundamentals: false,
      fundamentalsSave: false,
      copilot: false,
      risk: false,
      iv: false,
      ivSession: false
    });
  });

  it("reuses the in-flight request for repeated computeRisk calls with the same key", async () => {
    let resolveRisk!: (value: ReturnType<typeof ok>) => void;
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/risk/compute")) {
        return new Promise<ReturnType<typeof ok>>((resolve) => {
          resolveRisk = resolve;
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const options = makeRiskComputeOptions();
    const first = computeRisk(options);
    const second = computeRisk(options);

    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/risk/compute"))).toHaveLength(1);
    expect(get(loading).risk).toBe(true);

    resolveRisk(ok(makeRiskResult()));
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(firstResult).toBe(secondResult);
    expect(get(riskResult)?.metrics.historical_var).toBe(-1200);
    expect(get(loading).risk).toBe(false);
  });

  it("coalesces repeated Strategy Lab Open In Risk handoffs and does not load IV", async () => {
    let resolveRisk!: (value: ReturnType<typeof ok>) => void;
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/iv/surface")) {
        throw new Error(`Unexpected IV request: ${url}`);
      }
      if (url.includes("/risk/compute")) {
        return new Promise<ReturnType<typeof ok>>((resolve) => {
          resolveRisk = resolve;
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const openedTabs: TabId[] = [];
    const controller = createRiskHandoffController({
      getActiveTab: () => "strategy_lab",
      getStrategyLabResearchBook: () => makeStrategyLabResearchBook(),
      getResearchResult: () => null,
      setActiveTab: (tab) => {
        openedTabs.push(tab);
        activeTab.set(tab);
      },
      computeRisk
    });

    const first = controller.open();
    const second = controller.open();

    expect(first).toBe(second);
    expect(openedTabs).toEqual(["risk"]);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/risk/compute"))).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/iv/surface"))).toBe(false);

    resolveRisk(ok(makeRiskResult({ source_scope: "research_book", source_label: "Strategy Lab book: Pair Trade" })));
    await Promise.all([first, second]);

    expect(get(activeTab)).toBe("risk");
    expect(get(riskResult)?.source_scope).toBe("research_book");
    expect(controller.running).toBe(false);
  });

  it("clears risk loading after a failed compute", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValueOnce(new Error("network down"))
    );

    const result = await computeRisk(makeRiskComputeOptions());

    expect(result).toBeNull();
    expect(get(loading).risk).toBe(false);
    expect(get(lastError)).toBe("network down");
  });
});

function makeRiskComputeOptions(): RiskComputeOptions {
  return {
    snapshot: makeSnapshot(),
    sourceScope: "research_book",
    researchBookReturnPoints: [{ timestamp: "2026-07-07T00:00:00Z", value: 0.012 }],
    riskSourceLabel: "Strategy Lab book: Pair Trade",
    riskSourceObjectId: "strategy-book:test",
    riskSourceOrigin: "strategy_lab",
    alpha: 0.95,
    lookbackDays: 252,
    horizonDays: 1,
    mcHorizonDays: 10,
    mcSimulationModel: "Gaussian",
    mcNumSimulations: 2000,
    betaWindow: 126,
    benchmarkSymbol: "SPY"
  };
}

function makeStrategyLabResearchBook(): StrategyLabResearchBook {
  return {
    bookId: "strategy-book:test",
    sourceLabel: "Strategy Lab book: Pair Trade",
    object: {
      object_id: "strategy-book:test",
      return_points: [{ timestamp: "2026-07-07T00:00:00Z", value: 0.012 }],
      provenance: { origin: "strategy_lab" }
    },
    snapshot: makeSnapshot(),
    benchmarkSymbol: "SPY"
  } as unknown as StrategyLabResearchBook;
}

function makeSnapshot(): PortfolioSnapshot {
  return {
    timestamp: "2026-07-07T00:00:00Z",
    base_currency: "USD",
    account_summary: {},
    positions: [
      {
        symbol: "STRATEGY_BOOK",
        sec_type: "BOOK",
        currency: "USD",
        quantity: 1,
        avg_cost: null,
        market_price: 100000,
        market_value: 100000,
        unrealized_pnl: null,
        weight: 1,
        base_market_value: 100000,
        fx_rate: 1,
        instrument_id: "strategy-book:test",
        display_symbol: "Pair Trade",
        exchange: null,
        primary_exchange: null,
        provider: "gamma_strategy_lab",
        provider_id: "strategy-book:test"
      }
    ],
    total_market_value: 100000,
    total_cash: 0,
    net_liquidation: 100000,
    day_pnl: null,
    day_pnl_pct: null,
    day_pnl_source: "strategy_lab_validated_return_stream",
    warnings: []
  };
}

function makeRiskResult(overrides: Partial<RiskResult> = {}): RiskResult {
  return {
    source_scope: "research_book",
    source_label: "Strategy Lab book: Pair Trade",
    source_object_id: "strategy-book:test",
    source_origin: "strategy_lab",
    metrics: {
      alpha: 0.95,
      lookback_days: 252,
      horizon_days: 1,
      portfolio_value: 100000,
      historical_var: -1200,
      historical_cvar: -1600,
      parametric_var: -1100,
      daily_vol: 0.012,
      annual_vol: 0.19,
      max_drawdown: -0.08,
      beta: 0.4,
      correlation: 0.3,
      alpha_annual: 0.01,
      covered_portfolio_value: 100000,
      covered_risk_basis_value: 100000,
      risk_basis_value: 100000,
      risk_coverage_ratio: 1,
      historical_var_total_estimate: -1200,
      historical_cvar_total_estimate: -1600,
      parametric_var_total_estimate: -1100,
      monte_carlo_model: "Gaussian",
      monte_carlo_horizon_days: 10,
      monte_carlo_num_simulations: 2000,
      monte_carlo_var: -4500,
      monte_carlo_cvar: -5200,
      monte_carlo_var_total_estimate: -4500,
      monte_carlo_cvar_total_estimate: -5200,
      aligned_obs_count: 252,
      benchmark_overlap_count: 252,
      concentration_hhi: 1,
      top5_weight: 1,
      effective_bets: 1
    },
    portfolio_return_points: [{ timestamp: "2026-07-07T00:00:00Z", value: 0.012 }],
    benchmark_return_points: [{ timestamp: "2026-07-07T00:00:00Z", value: -0.004 }],
    contributions: [],
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
      source_provider: "risk_service"
    },
    excluded_assets: [],
    warnings: [],
    ...overrides
  };
}

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    async json() {
      return body;
    }
  };
}
