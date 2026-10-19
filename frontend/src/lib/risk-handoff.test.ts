import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PortfolioSnapshot, RiskResult, TabId } from "./api/types";
import { activeTab, computeRisk, lastError, loading, riskResult, type RiskComputeOptions, type StrategyLabResearchBook } from "./stores/app";
import {
  NO_RETAINED_BENCHMARK_LABEL,
  buildStrategyLabRiskRequest,
  createRiskHandoffController,
  strategyLabBenchmarkLabel,
  strategyLabBenchmarkPoints,
  strategyLabBookControls,
  strategyLabBookControlsKey,
  strategyLabControlsToSeed
} from "./risk-handoff";

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

  it("carries signed per-leg research-book history into Risk", () => {
    const book = makeStrategyLabResearchBook();
    book.object.risk_legs = [
      {
        leg_id: "1:xom",
        label: "XOM",
        symbol: "XOM",
        instrument_id: "leg:xom",
        weight: 0.6,
        return_points: [{ timestamp: "2026-07-07T00:00:00Z", value: 0.01 }],
        source_provider: "yfinance",
        warnings: []
      },
      {
        leg_id: "2:amd",
        label: "AMD",
        symbol: "AMD",
        instrument_id: "leg:amd",
        weight: -0.4,
        return_points: [{ timestamp: "2026-07-07T00:00:00Z", value: -0.02 }],
        source_provider: "yfinance",
        warnings: []
      }
    ];

    const request = buildStrategyLabRiskRequest(book);

    expect(request.researchBookRiskLegs?.map((leg) => [leg.symbol, leg.weight])).toEqual([
      ["XOM", 0.6],
      ["AMD", -0.4]
    ]);
  });

  // Regresión: un experimento sin histórico de benchmark retenido no debe mostrarse en Risk como SPY.
  it("labels an experiment without retained benchmark history honestly instead of SPY", () => {
    for (const benchmarkSymbol of [null, "spy"]) {
      const book = { ...makeStrategyLabResearchBook(), benchmarkSymbol, composition: { benchmark_points: [] } } as unknown as StrategyLabResearchBook;

      const request = buildStrategyLabRiskRequest(book);

      expect(request.benchmarkSymbol).toBe("SPY");
      expect(request.researchBookBenchmarkPoints).toEqual([]);
      expect(strategyLabBenchmarkLabel(book, request.benchmarkSymbol)).toBe(NO_RETAINED_BENCHMARK_LABEL);
    }
  });

  it("uses retained benchmark history only for the experiment's own benchmark", () => {
    const points = [{ timestamp: "2026-07-07T00:00:00Z", value: 0.004 }];
    const book = { ...makeStrategyLabResearchBook(), benchmarkSymbol: "qqq", composition: { benchmark_points: points } } as unknown as StrategyLabResearchBook;

    expect(buildStrategyLabRiskRequest(book).researchBookBenchmarkPoints).toEqual(points);
    expect(strategyLabBenchmarkPoints(book, " QQQ ")).toEqual(points);
    expect(strategyLabBenchmarkLabel(book, "QQQ")).toBe("QQQ");
    // Otro benchmark elegido en Risk usa la ruta del proveedor y conserva su símbolo.
    expect(strategyLabBenchmarkPoints(book, "IWM")).toBeNull();
    expect(strategyLabBenchmarkLabel(book, "iwm")).toBe("IWM");
  });
});

// Revisión 2026-10-15: con el libro ya seleccionado, benchmark y lookback solo se
// adoptaban al cambiar de fuente y el siguiente recálculo usaba valores anteriores.
describe("strategyLabControlsToSeed", () => {
  function book(overrides: Partial<StrategyLabResearchBook> & { lookbackDays?: number } = {}): StrategyLabResearchBook {
    const { lookbackDays = 504, ...rest } = overrides;
    return {
      ...makeStrategyLabResearchBook(),
      benchmarkSymbol: "qqq",
      createdAt: "2026-10-15T10:00:00Z",
      composition: { portfolio_inputs: { lookback_days: lookbackDays }, benchmark_points: null },
      ...rest
    } as unknown as StrategyLabResearchBook;
  }

  it("seeds the book's benchmark and lookback when the book is selected and nothing was seeded yet", () => {
    // Sin snapshot de cuenta el libro es la fuente desde el montaje, sin cambio de fuente que lo dispare.
    expect(strategyLabControlsToSeed({ selected: "strategy_lab_book", book: book(), seededKey: null })).toEqual({
      key: "strategy-book:test|2026-10-15T10:00:00Z",
      benchmarkSymbol: "QQQ",
      lookbackDays: 504
    });
  });

  it("seeds again on a second handoff even though the source stays selected", () => {
    const first = book();
    const second = book({ bookId: "strategy-book:other", benchmarkSymbol: "IWM", lookbackDays: 126 } as never);
    const seeded = strategyLabControlsToSeed({ selected: "strategy_lab_book", book: first, seededKey: null })!;

    expect(strategyLabControlsToSeed({ selected: "strategy_lab_book", book: second, seededKey: seeded.key })).toMatchObject({
      benchmarkSymbol: "IWM",
      lookbackDays: 126
    });
  });

  it("treats a recomposed experiment with the same bookId as a new book", () => {
    const first = book();
    const recomposed = book({ createdAt: "2026-10-15T11:00:00Z", lookbackDays: 252 } as never);

    expect(strategyLabControlsToSeed({
      selected: "strategy_lab_book",
      book: recomposed,
      seededKey: strategyLabBookControlsKey(first)
    })?.lookbackDays).toBe(252);
  });

  it("keeps a deliberate Risk edit for the book that already seeded the controls", () => {
    const current = book();
    expect(strategyLabControlsToSeed({
      selected: "strategy_lab_book",
      book: current,
      seededKey: strategyLabBookControlsKey(current)
    })).toBeNull();
  });

  it("never seeds while another source is selected or without a book", () => {
    expect(strategyLabControlsToSeed({ selected: "portfolio", book: book(), seededKey: null })).toBeNull();
    expect(strategyLabControlsToSeed({ selected: "strategy_lab_book", book: null, seededKey: null })).toBeNull();
  });

  it("leaves the lookback to the caller when the experiment did not record one", () => {
    const withoutLookback = { ...book(), composition: null } as unknown as StrategyLabResearchBook;
    expect(strategyLabBookControls(withoutLookback).lookbackDays).toBeNull();
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
