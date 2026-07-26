import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CopilotResearchCardResult,
  CryptoComparison,
  CryptoDexLiquiditySummary,
  CryptoFlowSummary,
  CryptoPriceHistoryResponse,
  CryptoToken,
  CryptoWorkspaceResponse,
  DiagnosticsResponse,
  FundamentalsSearchResponse,
  GammaResearchObject,
  IvSurface,
  IvSessionStatus,
  MacroDivergenceListResponse,
  MacroEventsResponse,
  MacroSeriesHistory,
  MacroSnapshot,
  NewsEventFeedResponse,
  PredictionCalibrationSummary,
  PredictionMarket,
  PredictionMarketListResponse,
  PredictionProbabilityHistoryResponse,
  PredictionWalletSummary,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  RelatedPredictionMarketListResponse,
  ResearchCompareResult,
  ResearchOverviewResponse,
  ResearchResult,
  RiskResult,
  SavedResearchItem,
  StrategyLabHandoffEnvelope,
  StrategyLabResult,
  SystemStatus
} from "../api/types";
import {
  clearFrontendQueryCache,
  activeCopilotSession,
  analyzeStrategyLab,
  acceptResolvedStrategyLabHandoff,
  copilotCards,
  copilotDiagnostics,
  copilotSessions,
  copilotThreads,
  composeStrategyLab,
  composeStrategyLabPortfolio,
  compareResearch,
  computeRisk,
  cryptoComparison,
  cryptoFlowSummary,
  cryptoLiquidity,
  cryptoPriceHistory,
  cryptoTokenDetail,
  cryptoWorkspace,
  diagnostics,
  fundamentalsSearch,
  fundamentalsLoadWarnings,
  fundamentalsSearchState,
  ivError,
  ivSession,
  ivSurface,
  lastError,
  loadCopilotResearchCard,
  loadCryptoWorkspace,
  loadFundamentalsSearch,
  loadIvSurface,
  loadIvSession,
  loadMacroWorkspace,
  loadNewsFeed,
  loadPortfolioSnapshot,
  loadPredictionMarketScreener,
  clearStrategyLabHandoffs,
  clearStaleStrategyLabHandoffs,
  dismissStrategyLabHandoff,
  enqueueStrategyLabHandoff,
  reviveStrategyLabHandoff,
  loadResearchOverview,
  loadSavedResearch,
  previewCopilotThreadFingerprint,
  promoteCopilotShelfThread,
  loading,
  macroContext,
  macroDivergences,
  macroEvents,
  macroSeriesHistories,
  macroSnapshot,
  newsFeed,
  portfolioHistory,
  portfolioPerformance,
  portfolioSnapshot,
  providerUsage,
  predictionMarketCalibration,
  predictionMarketDetail,
  predictionMarketHistory,
  predictionMarketRelated,
  predictionMarketScreener,
  predictionMarketWallet,
  loadSitrepWorkspace,
  loadSitrepFollowUps,
  toggleSitrepFollowUpItem,
  updateSitrepFollowUpItem,
  dismissSitrepFollowUpItem,
  sitrepFollowUps,
  sitrepWorkspaceMeta,
  sitrepIndicesOverview,
  commoditiesWorkspace,
  researchOverview,
  researchCompareResult,
  researchResult,
  strategyLabComposition,
  strategyLabHandoffQueue,
  resolvePendingStrategyLabHandoffs,
  restoreStrategyLabResult,
  riskResult,
  savedResearchItems,
  saveResearchItem,
  deleteSavedResearchItem,
  runResearch,
  clearSharedEquitySelection,
  setBaseCurrency,
  setMarketDataMode,
  setMacroContext,
  setSharedEquitySelection,
  selectedCryptoTokenId,
  selectedFundamentalsTicker,
  sharedEquitySelection,
  selectedPredictionMarketId,
  strategyLabResult,
  systemStatus
} from "./app";

describe("app store orchestration", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    clearFrontendQueryCache();
    systemStatus.set(null);
    diagnostics.set(null);
    providerUsage.set(null);
    ivError.set("");
    portfolioSnapshot.set(null);
    portfolioHistory.set(null);
    portfolioPerformance.set(null);
    researchOverview.set(null);
    researchResult.set(null);
    sharedEquitySelection.set(null);
    strategyLabResult.set(null);
    strategyLabComposition.set(null);
    strategyLabHandoffQueue.set([]);
    researchCompareResult.set(null);
    savedResearchItems.set([]);
    selectedPredictionMarketId.set(null);
    selectedCryptoTokenId.set(null);
    selectedFundamentalsTicker.set(null);
    fundamentalsSearch.set(null);
    fundamentalsLoadWarnings.set([]);
    fundamentalsSearchState.set({
      query: "",
      loading: false,
      refreshing: false,
      stale: false,
      error: null,
      requestedAt: null,
      completedAt: null
    });
    predictionMarketScreener.set(null);
    predictionMarketDetail.set(null);
    predictionMarketHistory.set(null);
    predictionMarketWallet.set(null);
    predictionMarketRelated.set(null);
    predictionMarketCalibration.set(null);
    cryptoWorkspace.set(null);
    cryptoTokenDetail.set(null);
    cryptoPriceHistory.set(null);
    cryptoLiquidity.set(null);
    cryptoComparison.set(null);
    copilotCards.set(emptyCopilotCards());
    activeCopilotSession.set(null);
    copilotDiagnostics.set(null);
    copilotSessions.set([]);
    copilotThreads.set(emptyCopilotThreads());
    riskResult.set(null);
    ivSurface.set(null);
    ivSession.set(null);
    macroContext.set({
      mode: "snapshot",
      region: "US",
      timeframe: "3M",
      theme: "all",
      comparisonRegion: null
    });
    macroSnapshot.set(null);
    macroDivergences.set(null);
    macroEvents.set(null);
    macroSeriesHistories.set({});
    newsFeed.set(null);
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

  it("does not auto-select the first fundamentals result for an empty search", async () => {
    const searchResponse: FundamentalsSearchResponse = {
      results: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          cik: "0000320193",
          exchange: "Nasdaq",
          source_provider: "sec",
          retrieved_at: "2026-04-30T00:00:00Z",
          origin: "fixture",
          transformation_note: null
        }
      ]
    };
    const fetchMock = vi.fn().mockResolvedValue(ok(searchResponse));
    vi.stubGlobal("fetch", fetchMock);

    await loadFundamentalsSearch();

    expect(get(fundamentalsSearch)?.results[0]?.ticker).toBe("AAPL");
    expect(get(selectedFundamentalsTicker)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/fundamentals/search?");
  });

  it("keeps stale fundamentals search results distinct while a refresh is pending", async () => {
    fundamentalsSearch.set({
      results: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          cik: "0000320193",
          exchange: "Nasdaq",
          source_provider: "sec",
          retrieved_at: "2026-04-30T00:00:00Z",
          origin: "fixture",
          transformation_note: null
        }
      ]
    });
    let resolveFetch!: (value: ReturnType<typeof ok>) => void;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const pending = loadFundamentalsSearch({ query: "missing-company" });

    expect(get(fundamentalsSearchState)).toMatchObject({
      query: "missing-company",
      loading: true,
      refreshing: true,
      stale: true,
      error: null
    });
    expect(get(fundamentalsSearch)?.results[0]?.ticker).toBe("AAPL");

    resolveFetch(ok({ results: [] }));
    await pending;

    expect(get(fundamentalsSearchState)).toMatchObject({
      query: "missing-company",
      loading: false,
      refreshing: false,
      stale: false,
      error: null
    });
    expect(get(fundamentalsSearch)?.results).toEqual([]);
  });

  it("selects an exact ticker fundamentals result for an explicit search", async () => {
    const searchResponse: FundamentalsSearchResponse = {
      results: [
        {
          ticker: "MSFT",
          name: "Microsoft Corporation",
          cik: "0000789019",
          exchange: "Nasdaq",
          source_provider: "sec",
          retrieved_at: "2026-04-30T00:00:00Z",
          origin: "fixture",
          transformation_note: null
        }
      ]
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(searchResponse))
      .mockResolvedValue(ok({ warnings: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await loadFundamentalsSearch({ query: "msft" });

    expect(get(selectedFundamentalsTicker)).toBe("MSFT");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/fundamentals/MSFT/overview"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/fundamentals/MSFT/financials"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/fundamentals/MSFT/dcf"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/fundamentals/MSFT/peers"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/fundamentals/MSFT/reverse-valuation"),
      expect.any(Object)
    );
  });

  it("does not auto-select a fuzzy SEC result for a non-company focus", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({
      results: [{
        ticker: "XEL",
        name: "Xcel Energy Inc.",
        cik: "0000072903",
        exchange: "Nasdaq",
        source_provider: "sec",
        retrieved_at: "2026-07-13T00:00:00Z",
        origin: "fixture",
        transformation_note: null
      }]
    }));
    vi.stubGlobal("fetch", fetchMock);

    await loadFundamentalsSearch({ query: "XLE" });

    expect(get(selectedFundamentalsTicker)).toBeNull();
    expect(get(fundamentalsSearch)?.results[0]?.ticker).toBe("XEL");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps fulfilled fundamentals sections and reports degraded section loads", async () => {
    const searchResponse: FundamentalsSearchResponse = {
      results: [{
        ticker: "MSFT",
        name: "Microsoft Corporation",
        cik: "0000789019",
        exchange: "Nasdaq",
        source_provider: "sec",
        retrieved_at: "2026-07-13T00:00:00Z",
        origin: "fixture",
        transformation_note: null
      }]
    };
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.includes("/fundamentals/search")) return ok(searchResponse);
      if (url.includes("/financials")) return notFound({ detail: "quarterly facts unavailable" });
      return ok({ warnings: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadFundamentalsSearch({ query: "MSFT" });

    expect(get(selectedFundamentalsTicker)).toBe("MSFT");
    expect(get(fundamentalsLoadWarnings)).toEqual([
      expect.stringContaining("Financials unavailable")
    ]);
  });

  it("loads snapshot, history, and shared performance together", async () => {
    const snapshot = makeSnapshot();
    const history: PortfolioHistoryResponse = {
      source: "local_history_store",
      points: [
        {
          timestamp: "2026-03-01T00:00:00Z",
          portfolio_value: 100,
          net_liquidation: 100,
          market_value: 90,
          cash: 10,
          base_currency: "USD"
        }
      ]
    };
    const performance: PortfolioPerformanceResponse = {
      benchmark_symbol: "SPY",
      benchmark_source: "history_SPY",
      performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1 }],
      benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1 }],
      portfolio_base_value: 100,
      missing_symbols: [],
      day_pnl: 1,
      day_pnl_pct: 0.01,
      day_pnl_source: "account_summary",
      message: null,
      warnings: []
    };

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(ok(snapshot))
        .mockResolvedValueOnce(ok(history))
        .mockResolvedValueOnce(ok(performance))
    );

    await loadPortfolioSnapshot();

    expect(get(portfolioSnapshot)).toEqual(snapshot);
    expect(get(portfolioHistory)).toEqual(history);
    expect(get(portfolioPerformance)).toEqual(performance);
    expect(get(lastError)).toBe("");
  });

  it("falls back to the research snapshot when computing risk", async () => {
    const snapshot = makeSnapshot();
    const research: ResearchResult = {
      scope_type: "single_ticker",
      benchmark_symbol: "SPY",
      primary_symbol: "AAPL",
      observations_count: 10,
      latest_daily_return: 0.01,
      latest_daily_return_at: "2026-03-01T00:00:00Z",
      latest_price: 100,
      latest_price_at: "2026-03-01T00:00:00Z",
      snapshot,
      performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
      benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }],
      primary_price_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 100 }],
      weights: [{ symbol: "AAPL", weight: 1, instrument_id: "portfolio:stk:aapl", display_symbol: "AAPL" }],
      summary: {
        total_return: 0.1,
        annual_return: 0.1,
        annual_vol: 0.2,
        max_drawdown: -0.05,
        beta: 1,
        correlation: 0.9
      },
      structure: {
        total_weight: 1,
        top_weight: 1,
        top5_weight: 1,
        concentration_hhi: 1,
        effective_positions: 1,
        aligned_symbol_count: 1
      },
      coverage: {
        available_symbols: ["AAPL"],
        missing_symbols: [],
        benchmark_overlap_count: 10
      },
      constituents: [
        {
          symbol: "AAPL",
          weight: 1,
          instrument_id: "portfolio:stk:aapl",
          display_symbol: "AAPL",
          total_return: 0.1,
          annual_vol: 0.2,
          max_drawdown: -0.05,
          weighted_return: 0.1
        }
      ],
      warnings: []
    };
    const risk: RiskResult = {
      source_scope: "research",
      source_label: "Research scope snapshot",
      source_object_id: null,
      source_origin: null,
      metrics: {
        alpha: 0.95,
        lookback_days: 252,
        horizon_days: 1,
        portfolio_value: 100,
        historical_var: 5,
        historical_cvar: 6,
        parametric_var: 4,
        daily_vol: 0.01,
        annual_vol: 0.2,
        max_drawdown: -0.1,
        beta: 1,
        correlation: 0.8,
        alpha_annual: 0.05,
        covered_portfolio_value: 100,
        covered_risk_basis_value: 100,
        risk_basis_value: 100,
        risk_coverage_ratio: 1,
        historical_var_total_estimate: 5,
        historical_cvar_total_estimate: 6,
        parametric_var_total_estimate: 4,
        monte_carlo_model: "Gaussian",
        monte_carlo_horizon_days: 10,
        monte_carlo_num_simulations: 1000,
        monte_carlo_var: 7,
        monte_carlo_cvar: 8,
        monte_carlo_var_total_estimate: 7,
        monte_carlo_cvar_total_estimate: 8,
        aligned_obs_count: 10,
        benchmark_overlap_count: 10,
        concentration_hhi: 1,
        top5_weight: 1,
        effective_bets: 1
      },
      portfolio_return_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
      benchmark_return_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.005 }],
      contributions: [],
      monte_carlo: {
        terminal_returns: [],
        fan_percentiles: {},
        sample_paths: {}
      },
      frontier_points: [],
      correlation_matrix: emptyRiskCorrelationMatrix(),
      dependency_network: emptyRiskDependencyNetwork(),
      excluded_assets: [],
      warnings: []
    };

    researchResult.set(research);
    const fetchMock = vi.fn().mockResolvedValue(ok(risk));
    vi.stubGlobal("fetch", fetchMock);

    await computeRisk({
      alpha: 0.95,
      lookbackDays: 252,
      horizonDays: 1,
      mcHorizonDays: 10,
      mcSimulationModel: "Gaussian",
      mcNumSimulations: 1000,
      betaWindow: 63,
      benchmarkSymbol: "SPY"
    });

    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(requestBody.snapshot.positions[0].symbol).toBe("AAPL");
    expect(requestBody.source_scope).toBe("research");
    expect(get(riskResult)?.metrics.historical_var).toBe(5);
  });

  it("replaces the active research context and clears stale risk results on rerun", async () => {
    const singleTicker = makeResearchResult("single_ticker", makeSnapshot());
    const syntheticSnapshot = {
      ...makeSnapshot(),
      positions: [
        {
          ...makeSnapshot().positions[0],
          symbol: "XLV",
          quantity: 0.35,
          weight: 0.35,
          base_market_value: 35,
          market_value: 35
        },
        {
          ...makeSnapshot().positions[0],
          symbol: "XLP",
          quantity: 0.35,
          weight: 0.35,
          base_market_value: 35,
          market_value: 35
        },
        {
          ...makeSnapshot().positions[0],
          symbol: "XLU",
          quantity: 0.3,
          weight: 0.3,
          base_market_value: 30,
          market_value: 30
        }
      ],
      total_market_value: 100,
      net_liquidation: 100
    };
    const synthetic = makeResearchResult("synthetic_portfolio", syntheticSnapshot);

    riskResult.set({
      source_scope: "research",
      source_label: "Research scope snapshot",
      source_object_id: null,
      source_origin: null,
      metrics: {
        alpha: 0.95,
        lookback_days: 252,
        horizon_days: 1,
        portfolio_value: 100,
        historical_var: 5,
        historical_cvar: 6,
        parametric_var: 4,
        daily_vol: 0.01,
        annual_vol: 0.2,
        max_drawdown: -0.1,
        beta: 1,
        correlation: 0.8,
        alpha_annual: 0.05,
        covered_portfolio_value: 100,
        covered_risk_basis_value: 100,
        risk_basis_value: 100,
        risk_coverage_ratio: 1,
        historical_var_total_estimate: 5,
        historical_cvar_total_estimate: 6,
        parametric_var_total_estimate: 4,
        monte_carlo_model: "Gaussian",
        monte_carlo_horizon_days: 10,
        monte_carlo_num_simulations: 1000,
        monte_carlo_var: 7,
        monte_carlo_cvar: 8,
        monte_carlo_var_total_estimate: 7,
        monte_carlo_cvar_total_estimate: 8,
        aligned_obs_count: 10,
        benchmark_overlap_count: 10,
        concentration_hhi: 1,
        top5_weight: 1,
        effective_bets: 1
      },
      portfolio_return_points: [],
      benchmark_return_points: [],
      contributions: [],
      monte_carlo: {
        terminal_returns: [],
        fan_percentiles: {},
        sample_paths: {}
      },
      frontier_points: [],
      correlation_matrix: emptyRiskCorrelationMatrix(),
      dependency_network: emptyRiskDependencyNetwork(),
      excluded_assets: [],
      warnings: []
    });

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(ok(singleTicker))
        .mockResolvedValueOnce(ok(synthetic))
    );

    await runResearch({
      scopeType: "single_ticker",
      primarySymbol: "AAPL",
      benchmarkSymbol: "SPY",
      lookbackDays: 252
    });

    expect(get(researchResult)?.scope_type).toBe("single_ticker");
    expect(get(researchResult)?.snapshot?.positions.map((position) => position.symbol)).toEqual(["AAPL"]);
    expect(get(riskResult)).toBeNull();

    riskResult.set({
      source_scope: "research",
      source_label: "Research scope snapshot",
      source_object_id: null,
      source_origin: null,
      metrics: {
        alpha: 0.95,
        lookback_days: 252,
        horizon_days: 1,
        portfolio_value: 100,
        historical_var: 5,
        historical_cvar: 6,
        parametric_var: 4,
        daily_vol: 0.01,
        annual_vol: 0.2,
        max_drawdown: -0.1,
        beta: 1,
        correlation: 0.8,
        alpha_annual: 0.05,
        covered_portfolio_value: 100,
        covered_risk_basis_value: 100,
        risk_basis_value: 100,
        risk_coverage_ratio: 1,
        historical_var_total_estimate: 5,
        historical_cvar_total_estimate: 6,
        parametric_var_total_estimate: 4,
        monte_carlo_model: "Gaussian",
        monte_carlo_horizon_days: 10,
        monte_carlo_num_simulations: 1000,
        monte_carlo_var: 7,
        monte_carlo_cvar: 8,
        monte_carlo_var_total_estimate: 7,
        monte_carlo_cvar_total_estimate: 8,
        aligned_obs_count: 10,
        benchmark_overlap_count: 10,
        concentration_hhi: 1,
        top5_weight: 1,
        effective_bets: 1
      },
      portfolio_return_points: [],
      benchmark_return_points: [],
      contributions: [],
      monte_carlo: {
        terminal_returns: [],
        fan_percentiles: {},
        sample_paths: {}
      },
      frontier_points: [],
      correlation_matrix: emptyRiskCorrelationMatrix(),
      dependency_network: emptyRiskDependencyNetwork(),
      excluded_assets: [],
      warnings: []
    });

    await runResearch({
      scopeType: "synthetic_portfolio",
      syntheticPositions: [
        { symbol: "XLV", weight: 0.35 },
        { symbol: "XLP", weight: 0.35 },
        { symbol: "XLU", weight: 0.3 }
      ],
      benchmarkSymbol: "SPY",
      lookbackDays: 252
    });

    expect(get(researchResult)?.scope_type).toBe("synthetic_portfolio");
    expect(get(researchResult)?.primary_symbol).toBeNull();
    expect(get(researchResult)?.snapshot?.positions.map((position) => position.symbol)).toEqual(["XLV", "XLP", "XLU"]);
    expect(get(riskResult)).toBeNull();
  });

  it("normalizes and clears the shared equity lens", () => {
    const selection = setSharedEquitySelection(" aapl ", {
      label: " Apple Inc. ",
      sourceTab: "research"
    });

    expect(selection?.symbol).toBe("AAPL");
    expect(selection?.label).toBe("Apple Inc.");
    expect(selection?.sourceTab).toBe("research");
    expect(get(sharedEquitySelection)?.symbol).toBe("AAPL");

    clearSharedEquitySelection();

    expect(get(sharedEquitySelection)).toBeNull();
  });

  it("loads the Research Overview with universe, timeframe, and benchmark filters", async () => {
    const overview = makeResearchOverview();
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(overview));
    vi.stubGlobal("fetch", fetchMock);

    await loadResearchOverview({
      universeId: "sample_equities",
      timeframe: "1M",
      benchmarkSymbol: "AAPL",
      forceRefresh: true
    });

    expect(get(researchOverview)?.universe_id).toBe("sample_equities");
    expect(get(researchOverview)?.nodes[0]?.source_provider).toBe("mock");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/research/overview?universe_id=sample_equities&timeframe=1M&benchmark_symbol=AAPL&surface=research_overview&force_refresh=true"
    );
  });

  it("loads the latest news feed for SITREP", async () => {
    const feed: NewsEventFeedResponse = {
      source_provider: "rss",
      retrieved_at: "2026-04-22T12:00:00Z",
      origin: "news_service.latest",
      freshness_label: "delayed",
      warnings: ["One RSS feed failed."],
      transformation_note: "Merged news feed.",
      items: [
        {
          normalized_id: "rss:test:1",
          title: "Fed markets update",
          url: "https://example.com/fed",
          source_provider: "rss",
          source_name: "Example Markets",
          published_at: "2026-04-22T11:45:00Z",
          retrieved_at: "2026-04-22T12:00:00Z",
          origin: "rss.feed:test",
          summary: "Policy-sensitive markets moved.",
          source_domain: "example.com",
          provider_item_id: "test:1",
          detected_entities: [],
          tags: ["macro"],
          freshness_label: "delayed",
          warnings: [],
          transformation_note: "Parsed from RSS."
        }
      ]
    };
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(feed));
    vi.stubGlobal("fetch", fetchMock);

    await loadNewsFeed({ limit: 10, forceRefresh: true });

    expect(get(newsFeed)?.items[0]?.title).toBe("Fed markets update");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/news/latest?limit=10&force_refresh=true");
    expect(get(lastError)).toBe("");
  });

  it("analyzes Strategy Lab returns and stores the latest result", async () => {
    const strategy = makeStrategyLabResult();
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(strategy));
    vi.stubGlobal("fetch", fetchMock);

    await analyzeStrategyLab({
      name: "CSV Strategy",
      rows: [{ date: "2026-03-01", return: "1%" }],
      dateColumn: "date",
      valueColumn: "return",
      valueKind: "return",
      benchmarkColumn: null
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(body.value_kind).toBe("return");
    expect(get(strategyLabResult)?.name).toBe("CSV Strategy");
    expect(get(researchCompareResult)).toBeNull();
  });

  it("clears stale Strategy Lab composition after a new research run", async () => {
    const snapshot = makeSnapshot();
    const result = makeResearchResult("single_ticker", snapshot);
    strategyLabComposition.set({
      ...makeStrategyLabResult(),
      name: "Stale Composition",
      leg_contributions: { "scope-1": 1 },
      lenses: [],
      overlays: []
    } as any);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(ok(result)));

    await runResearch({
      scopeType: "single_ticker",
      primarySymbol: "AAPL",
      benchmarkSymbol: "SPY",
      lookbackDays: 252
    });

    expect(get(researchResult)?.scope_type).toBe("single_ticker");
    expect(get(strategyLabComposition)).toBeNull();
  });

  it("composes Strategy Lab research objects and stores the composition result", async () => {
    const composition = {
      ...makeStrategyLabResult(),
      name: "Composite Strategy",
      leg_contributions: { "scope-1": 0.6, "strategy-1": 0.4 },
      lenses: [],
      overlays: []
    };
    const scopeObject: GammaResearchObject = {
      object_id: "scope-1",
      object_type: "equity_scope",
      display_name: "Scope Basket",
      source_tab: "equity_research",
      source_mode: "scope_analysis",
      resolver_capabilities: ["return_leg", "benchmark"],
      symbols: ["AAPL"],
      constituents: [],
      weights: [{ symbol: "AAPL", weight: 1 }],
      available_start: "2026-03-01T00:00:00Z",
      available_end: "2026-03-12T00:00:00Z",
      provider_summary: "Local daily history",
      provenance: { source_provider: "gamma_research" },
      warnings: [],
      return_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }]
    };
    const benchmarkObject = { ...scopeObject, object_id: "benchmark-1", display_name: "Benchmark" };
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(composition));
    vi.stubGlobal("fetch", fetchMock);

    await composeStrategyLab({
      name: "Composite Strategy",
      legs: [{ object: scopeObject, weight: 0.6 }],
      lenses: [],
      overlays: [],
      benchmarkObject,
      minObservations: 10
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/research/strategy-lab/compose");
    expect(body.name).toBe("Composite Strategy");
    expect(body.legs[0].object.object_id).toBe("scope-1");
    expect(body.legs[0].weight).toBe(0.6);
    expect(body.benchmark_object.object_id).toBe("benchmark-1");
    expect(body.min_observations).toBe(10);
    expect(get(strategyLabComposition)?.leg_contributions).toEqual({ "scope-1": 0.6, "strategy-1": 0.4 });
    expect(get(researchCompareResult)).toBeNull();
    expect(get(lastError)).toBe("");
  });

  it("sends accepted Strategy Lab lenses through portfolio composition", async () => {
    const lens: GammaResearchObject = {
      object_id: "macro:us:3m:policy:snapshot:none",
      object_type: "macro_lens",
      display_name: "US Policy lens",
      source_tab: "macro",
      source_mode: "snapshot",
      resolver_capabilities: ["lens"],
      symbols: [],
      constituents: [{ region: "US", timeframe: "3M", theme: "policy" }],
      weights: [],
      available_start: null,
      available_end: "2026-06-03T00:00:00Z",
      provider_summary: "fixture_macro",
      provenance: { transformation: "macro_context_to_strategy_lab_lens" },
      warnings: ["Macro lens is context only."],
      return_points: []
    };
    const composition = {
      ...makeStrategyLabResult(),
      name: "Portfolio With Lens",
      leg_contributions: { QQQ: 1 },
      lenses: [lens],
      overlays: []
    };
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(composition));
    vi.stubGlobal("fetch", fetchMock);

    await composeStrategyLabPortfolio({
      name: "Portfolio With Lens",
      legs: [
        {
          label: "QQQ",
          asset_class: "etf",
          identifier: "QQQ",
          weight: 1,
          value_kind: "return",
          return_points: []
        }
      ],
      lenses: [lens],
      overlays: [],
      benchmarkSymbol: null,
      lookbackDays: 252,
      minObservations: 5
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/research/strategy-lab/portfolio-compose");
    expect(body.lenses[0].object_id).toBe(lens.object_id);
    expect(body.overlays).toEqual([]);
    expect(get(strategyLabComposition)?.lenses[0]?.object_id).toBe(lens.object_id);
  });

  it("clears stale Strategy Lab composition after failed portfolio compose", async () => {
    strategyLabComposition.set({
      ...makeStrategyLabResult(),
      name: "Previous Composition",
      leg_contributions: { QQQ: 1 },
      lenses: [],
      overlays: [],
      alignment_diagnostics: {}
    } as any);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        notFound({
          detail: [
            "Strategy Lab composition needs at least 5 shared return observations; only 0 overlap after source alignment."
          ]
        })
      )
    );

    const result = await composeStrategyLabPortfolio({
      name: "Thin Book",
      legs: [
        {
          label: "QQQ",
          asset_class: "etf",
          identifier: "QQQ",
          weight: 1,
          value_kind: "return",
          return_points: []
        }
      ],
      benchmarkSymbol: null,
      lookbackDays: 252,
      minObservations: 5
    });

    expect(result).toBeNull();
    expect(get(strategyLabComposition)).toBeNull();
    expect(get(lastError)).toContain("only 0 overlap");
  });

  it("restores a normalized saved Strategy Lab result without an API call", () => {
    const strategy = makeStrategyLabResult();
    researchCompareResult.set(makeResearchCompareResult());

    restoreStrategyLabResult(strategy);

    expect(get(strategyLabResult)?.name).toBe("CSV Strategy");
    expect(get(researchCompareResult)).toBeNull();
    expect(get(lastError)).toBe("");
  });

  it("compares research return streams through the scenario endpoint", async () => {
    const comparison = makeResearchCompareResult();
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(comparison));
    vi.stubGlobal("fetch", fetchMock);

    await compareResearch({
      left: {
        label: "Scope",
        objectType: "scope_analysis",
        returnPoints: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }]
      },
      right: {
        label: "Strategy",
        objectType: "strategy_lab",
        returnPoints: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }]
      }
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(body.left.object_type).toBe("scope_analysis");
    expect(get(researchCompareResult)?.aligned_observation_count).toBe(12);
  });

  it("loads, saves, and deletes Saved Research items", async () => {
    const item = makeSavedResearchItem("saved-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok({ items: [item] }))
      .mockResolvedValueOnce(ok(item))
      .mockResolvedValueOnce(ok({ success: true }));
    vi.stubGlobal("fetch", fetchMock);

    await loadSavedResearch();
    expect(get(savedResearchItems).map((saved) => saved.id)).toEqual(["saved-1"]);

    await saveResearchItem({
      objectType: "strategy_lab",
      title: "Saved Strategy",
      payload: { returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }] }
    });
    expect(get(savedResearchItems)[0]?.title).toBe("Saved Strategy");

    await deleteSavedResearchItem("saved-1");
    expect(get(savedResearchItems).some((saved) => saved.id === "saved-1")).toBe(false);
  });

  it("preserves saved research items when the saved endpoint is temporarily unavailable", async () => {
    const staleSavedItem = makeSavedResearchItem("stale-saved");
    savedResearchItems.set([staleSavedItem]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(notFound({ detail: "Not Found" })));

    const items = await loadSavedResearch();

    expect(items).toEqual([staleSavedItem]);
    expect(get(savedResearchItems)).toEqual([staleSavedItem]);
    expect(get(lastError)).toContain("404");
  });

  it("loads the prediction screener and selected market bundle together", async () => {
    const screener: PredictionMarketListResponse = {
      markets: [makePredictionMarket("polymarket:fed-cut")],
      venues: [
        {
          venue: "polymarket",
          status: "active",
          message: "1 research contract surfaced from polymarket.",
          total_markets: 1,
          matched_markets: 1,
          visible_markets: 1,
          stale_markets: 0,
          broken_markets: 0,
          retrieved_at: "2026-03-01T00:05:00Z"
        }
      ],
      warnings: []
    };
    const detail: PredictionMarket = makePredictionMarket("polymarket:fed-cut");
    const history: PredictionProbabilityHistoryResponse = {
      market_id: "polymarket:fed-cut",
      points: [
        {
          timestamp: "2026-03-01T00:00:00Z",
          probability: 0.45,
          volume: 100,
          open_interest: 50,
          bid: 0.44,
          ask: 0.46,
          spread: 0.02,
          source_provider: "polymarket",
          retrieved_at: "2026-03-01T00:05:00Z",
          origin: "polymarket.history",
          transformation_note: null
        }
      ]
    };
    const wallet: PredictionWalletSummary = {
      market_id: "polymarket:fed-cut",
      venue: "polymarket",
      concentration_hhi: 0.4,
      top_participant_share: 0.55,
      total_trades: 4,
      total_notional: 2500,
      participants: [
        {
          participant_id: "wallet-1",
          display_name: "Desk One",
          venue: "polymarket",
          side: "buy",
          outcome_label: "Yes",
          trade_count: 4,
          total_size: 300,
          average_price: 0.48,
          first_seen: "2026-03-01T00:00:00Z",
          last_seen: "2026-03-01T04:00:00Z",
          current_edge: 0.03,
          source_provider: "polymarket",
          retrieved_at: "2026-03-01T04:00:00Z",
          origin: "polymarket.wallets",
          transformation_note: null
        }
      ],
      warnings: [],
      source_provider: "polymarket",
      retrieved_at: "2026-03-01T04:00:00Z",
      origin: "polymarket.wallets",
      transformation_note: null
    };
    const related: RelatedPredictionMarketListResponse = {
      market_id: "polymarket:fed-cut",
      related: [
        {
          market_id: "kalshi:fed-cut",
          venue: "kalshi",
          title: "Will the Fed cut rates in March?",
          probability: 0.49,
          price_gap: 0.03,
          relationship: "cross_venue_similarity",
          note: "Cross-venue lexical similarity score 0.72.",
          source_provider: "kalshi",
          retrieved_at: "2026-03-01T05:00:00Z",
          origin: "prediction_market_service.cross_venue_similarity",
          transformation_note: null
        }
      ]
    };
    const calibration: PredictionCalibrationSummary = {
      venue: "polymarket",
      sample_size: 12,
      buckets: [],
      observations: [],
      warnings: [],
      source_provider: "polymarket",
      retrieved_at: "2026-03-01T05:00:00Z",
      origin: "polymarket.calibration",
      transformation_note: "Calibration uses last traded probabilities as a proxy."
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(screener))
      .mockResolvedValueOnce(ok(detail))
      .mockResolvedValueOnce(ok(history))
      .mockResolvedValueOnce(ok(wallet))
      .mockResolvedValueOnce(ok(related))
      .mockResolvedValueOnce(ok(calibration));
    vi.stubGlobal("fetch", fetchMock);

    await loadPredictionMarketScreener({
      query: "fed",
      venues: ["polymarket"],
      status: "open",
      sortBy: "open_interest_desc",
      limit: 20
    });

    expect(get(predictionMarketScreener)?.markets).toHaveLength(1);
    expect(get(predictionMarketDetail)?.market_id).toBe("polymarket:fed-cut");
    expect(get(predictionMarketHistory)?.points[0]?.probability).toBe(0.45);
    expect(get(predictionMarketWallet)?.participants[0]?.display_name).toBe("Desk One");
    expect(get(predictionMarketRelated)?.related[0]?.venue).toBe("kalshi");
    expect(get(predictionMarketCalibration)?.sample_size).toBe(12);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}")).sort_by).toBe("open_interest_desc");
  });

  it("loads the crypto workspace and selected token bundle together", async () => {
    const workspace: CryptoWorkspaceResponse = {
      tokens: [makeCryptoToken("solana")],
      narratives: [
        {
          basket_id: "layer-1",
          label: "Layer 1",
          description: "Base-layer networks.",
          market_cap: 900000000000,
          market_cap_change_pct_24h: 2.5,
          volume_24h: 50000000000,
          top_tokens: [
            {
              token_id: "bitcoin",
              name: "Bitcoin",
              symbol: "BTC",
              image_url: null
            }
          ],
          source_provider: "coingecko",
          retrieved_at: "2026-03-01T00:05:00Z",
          origin: "coingecko.categories",
          transformation_note: "Gamma-selected narrative basket."
        }
      ],
      warnings: []
    };
    const detail: CryptoToken = {
      ...makeCryptoToken("solana"),
      description: "High-throughput smart-contract network.",
      categories: ["Layer 1", "Smart Contract Platform"],
      contract_address: "So11111111111111111111111111111111111111112",
      homepage_url: "https://solana.com"
    };
    const history: CryptoPriceHistoryResponse = {
      token_id: "solana",
      points: [
        {
          timestamp: "2026-03-01T00:00:00Z",
          price: 150,
          market_cap: 70000000000,
          total_volume: 4500000000,
          source_provider: "coingecko",
          retrieved_at: "2026-03-01T00:05:00Z",
          origin: "coingecko.market_chart",
          transformation_note: null
        }
      ]
    };
    const liquidity: CryptoDexLiquiditySummary = {
      token_id: "solana",
      lookup_strategy: "contract_lookup",
      matched_networks: ["solana"],
      total_reserve_usd: 180000000,
      total_volume_24h: 45000000,
      total_buys_24h: 9000,
      total_sells_24h: 8700,
      total_buyers_24h: 5200,
      total_sellers_24h: 5100,
      dominant_dex: "raydium",
      pools: [],
      warnings: [],
      source_provider: "geckoterminal",
      retrieved_at: "2026-03-01T00:05:00Z",
      origin: "geckoterminal.liquidity_summary",
      transformation_note: "Gamma aggregates top matched pools."
    };
    const comparison: CryptoComparison = {
      subject_token_id: "solana",
      target_kind: "basket",
      target_id: "layer-1",
      target_label: "Layer 1",
      shared_categories: ["Layer 1"],
      subject_price_change_pct_24h: 4.2,
      target_price_change_pct_24h: 2.1,
      price_gap_pct_24h: 2.1,
      subject_price_change_pct_7d: 10.5,
      target_price_change_pct_7d: 5.2,
      price_gap_pct_7d: 5.3,
      subject_price_change_pct_30d: 18.2,
      target_price_change_pct_30d: 11.4,
      price_gap_pct_30d: 6.8,
      subject_market_cap: 75000000000,
      target_market_cap: 900000000000,
      market_cap_ratio: 0.083,
      subject_turnover_ratio_24h: 0.09,
      target_turnover_ratio_24h: 0.06,
      turnover_gap: 0.03,
      summary: "Solana is outperforming the Layer 1 basket over 7D with hotter turnover.",
      source_provider: "gamma",
      retrieved_at: "2026-03-01T00:05:00Z",
      origin: "gamma.crypto.comparison.basket",
      transformation_note: "Basket comparison uses market-cap-weighted aggregates."
    };
    const flow: CryptoFlowSummary = {
      token_id: "solana",
      pool_count: 2,
      matched_networks: ["solana"],
      total_reserve_usd: 180000000,
      total_volume_24h: 45000000,
      dex_volume_share_of_total_volume: 0.34,
      reserve_to_market_cap_ratio: 0.0024,
      top_pool_reserve_share: 0.62,
      top_pool_volume_share: 0.58,
      buy_pressure_pct: 57.3,
      active_trader_proxy_24h: 10300,
      buy_sell_ratio: 1.03,
      participant_balance_ratio: 1.02,
      reserve_volume_ratio_24h: 4.0,
      slippage_proxy_label: "deep",
      liquidity_concentration_label: "moderately concentrated",
      flow_signal_label: "accumulation",
      summary: "Constructive flow with deep pool support.",
      warnings: [],
      source_provider: "gamma",
      retrieved_at: "2026-03-01T00:05:00Z",
      origin: "gamma.crypto.flow_summary",
      transformation_note: "Gamma flow summary."
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(workspace))
      .mockResolvedValueOnce(ok(detail))
      .mockResolvedValueOnce(ok(history))
      .mockResolvedValueOnce(ok(liquidity))
      .mockResolvedValueOnce(ok(flow))
      .mockResolvedValueOnce(ok(comparison));
    vi.stubGlobal("fetch", fetchMock);

    await loadCryptoWorkspace({
      query: "sol",
      narrative: "Layer 1",
      sortBy: "screen_score_desc",
      limit: 20
    });

    expect(get(cryptoWorkspace)?.tokens).toHaveLength(1);
    expect(get(cryptoTokenDetail)?.token_id).toBe("solana");
    expect(get(cryptoPriceHistory)?.points[0]?.price).toBe(150);
    expect(get(cryptoLiquidity)?.dominant_dex).toBe("raydium");
    expect(get(cryptoFlowSummary)?.flow_signal_label).toBe("accumulation");
    expect(get(cryptoComparison)?.target_label).toBe("Layer 1");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}")).sort_by).toBe("screen_score_desc");
  });

  it("synchronizes diagnostics when market data mode changes", async () => {
    const initialDiagnostics: DiagnosticsResponse = {
      generated_at: "2026-03-01T00:00:00Z",
      mock_mode: true,
      base_currency: "USD",
      market_data_mode: "delayed",
      connection: {
        connected: true,
        status_text: "Status: Mock",
        action_text: "Mock Mode",
        action_enabled: false,
        active_account: "DU123"
      },
      history_cache: { hits: 1, misses: 0, hit_rate: 1 },
      local_history_entries: 1,
      local_history_path: "data/mock.csv",
      recent_errors: [],
      cached_symbols: ["AAPL"],
      research_scope_type: "none",
      research_primary_symbol: null,
      research_synthetic_count: 0,
      iv_running: false,
      iv_status_text: "Idle",
      iv_active_symbol: null
    };
    const nextStatus: SystemStatus = {
      healthy: true,
      app_name: "Gamma API",
      backend: "fastapi",
      mock_mode: true,
      base_currency: "USD",
      market_data_mode: "live",
      connection: initialDiagnostics.connection,
      cached_symbols: ["AAPL"]
    };
    diagnostics.set(initialDiagnostics);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(nextStatus)));

    await setMarketDataMode("live");

    expect(get(systemStatus)?.market_data_mode).toBe("live");
    expect(get(diagnostics)?.market_data_mode).toBe("live");
  });

  it("resets currency-specific state when base currency changes", async () => {
    const snapshot = makeSnapshot();
    const status: SystemStatus = {
      healthy: true,
      app_name: "Gamma API",
      backend: "fastapi",
      mock_mode: true,
      base_currency: "EUR",
      market_data_mode: "delayed",
      connection: {
        connected: true,
        status_text: "Status: Mock",
        action_text: "Mock Mode",
        action_enabled: false,
        active_account: "DU123"
      },
      cached_symbols: ["AAPL"]
    };
    diagnostics.set({
      generated_at: "2026-03-01T00:00:00Z",
      mock_mode: true,
      base_currency: "USD",
      market_data_mode: "delayed",
      connection: status.connection,
      history_cache: { hits: 1, misses: 0, hit_rate: 1 },
      local_history_entries: 5,
      local_history_path: "data/mock.csv",
      recent_errors: [],
      cached_symbols: ["AAPL"],
      research_scope_type: "none",
      research_primary_symbol: null,
      research_synthetic_count: 0,
      iv_running: false,
      iv_status_text: "Idle",
      iv_active_symbol: null
    });
    portfolioSnapshot.set(snapshot);
    portfolioPerformance.set({
      benchmark_symbol: "SPY",
      benchmark_source: "history_SPY",
      performance_points: [],
      benchmark_points: [],
      portfolio_base_value: 110,
      missing_symbols: [],
      day_pnl: 1,
      day_pnl_pct: 0.01,
      day_pnl_source: "account_summary",
      message: null,
      warnings: []
    });
    researchResult.set(makeResearchResult("single_ticker", snapshot));
    riskResult.set({
      source_scope: "research",
      source_label: "Research scope snapshot",
      source_object_id: null,
      source_origin: null,
      metrics: {
        alpha: 0.95,
        lookback_days: 252,
        horizon_days: 1,
        portfolio_value: 100,
        historical_var: 5,
        historical_cvar: 6,
        parametric_var: 4,
        daily_vol: 0.01,
        annual_vol: 0.2,
        max_drawdown: -0.1,
        beta: 1,
        correlation: 0.8,
        alpha_annual: 0.05,
        covered_portfolio_value: 100,
        covered_risk_basis_value: 100,
        risk_basis_value: 100,
        risk_coverage_ratio: 1,
        historical_var_total_estimate: 5,
        historical_cvar_total_estimate: 6,
        parametric_var_total_estimate: 4,
        monte_carlo_model: "Gaussian",
        monte_carlo_horizon_days: 10,
        monte_carlo_num_simulations: 1000,
        monte_carlo_var: 7,
        monte_carlo_cvar: 8,
        monte_carlo_var_total_estimate: 7,
        monte_carlo_cvar_total_estimate: 8,
        aligned_obs_count: 10,
        benchmark_overlap_count: 10,
        concentration_hhi: 1,
        top5_weight: 1,
        effective_bets: 1
      },
      portfolio_return_points: [],
      benchmark_return_points: [],
      contributions: [],
      monte_carlo: {
        terminal_returns: [],
        fan_percentiles: {},
        sample_paths: {}
      },
      frontier_points: [],
      correlation_matrix: emptyRiskCorrelationMatrix(),
      dependency_network: emptyRiskDependencyNetwork(),
      excluded_assets: [],
      warnings: []
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        ok({
          ...status,
          lines: [
            "Base currency set to EUR.",
            "Local portfolio history was cleared because stored snapshots are base-currency specific."
          ]
        })
      )
    );

    await setBaseCurrency("EUR");

    expect(get(systemStatus)?.base_currency).toBe("EUR");
    expect(get(diagnostics)?.base_currency).toBe("EUR");
    expect(get(diagnostics)?.local_history_entries).toBe(0);
    expect(get(portfolioSnapshot)).toBeNull();
    expect(get(portfolioHistory)?.points).toEqual([]);
    expect(get(portfolioPerformance)).toBeNull();
    expect(get(researchResult)).toBeNull();
    expect(get(riskResult)).toBeNull();
    expect(get(lastError)).toBe("");
  });

  it("loads IV session state and mirrors the latest surface", async () => {
    const session: IvSessionStatus = {
      running: true,
      status_text: "Streaming",
      active_symbol: "SPY",
      market_data_mode: "delayed",
      messages: [],
      surface: {
        ...makeIvSurface(),
        symbol: "SPY",
        spot: 500,
        expiries: ["20260320"],
        strikes: [495, 500, 505],
        iv_grid: [[0.2, 0.19, 0.21]],
        points: 3
      }
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(session)));

    await loadIvSession();

    expect(get(ivSession)?.running).toBe(true);
    expect(get(ivSurface)?.symbol).toBe("SPY");
  });

  it("prefetches default FX histories when loading the macro snapshot workspace", async () => {
    const snapshot: MacroSnapshot = {
      region: "US",
      timeframe: "3M",
      theme: "all",
      comparison_region: null,
      available_regions: ["US", "EU", "Global"],
      available_timeframes: ["1M", "3M", "6M", "1Y"],
      available_themes: ["all", "growth", "inflation", "policy", "recession_risk"],
      snapshot_cards: [],
      rates_policy: null,
      cross_asset: [],
      top_divergences: [],
      event_studies: [],
      upcoming_events: [],
      warnings: [],
      source_provider: "fred",
      retrieved_at: "2026-03-20T11:00:00Z",
      origin: "macro_service.snapshot",
      transformation_note: "Snapshot combines normalized macro sources."
    };
    const divergences: MacroDivergenceListResponse = {
      region: "US",
      timeframe: "3M",
      theme: "all",
      comparison_region: null,
      divergences: []
    };
    const events: MacroEventsResponse = {
      region: "US",
      events: []
    };
    const fxHistory = (seriesId: string, title: string): MacroSeriesHistory => ({
      series_id: seriesId,
      title,
      region: "Global",
      unit: "fx",
      frequency: "daily",
      theme: "policy",
      mode_tags: ["snapshot"],
      points: [{ timestamp: "2026-03-20T00:00:00Z", value: 1.1, source_provider: "ibkr", retrieved_at: "2026-03-20T11:00:00Z", origin: `ibkr.fx_history:${title.replace("/", "")}`, transformation_note: null }],
      source_provider: "ibkr",
      retrieved_at: "2026-03-20T11:00:00Z",
      origin: `ibkr.fx_history:${title.replace("/", "")}`,
      transformation_note: null
    });

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(snapshot))
      .mockResolvedValueOnce(ok(divergences))
      .mockResolvedValueOnce(ok(events))
      .mockResolvedValueOnce(ok(fxHistory("fx-eurusd", "EUR/USD")))
      .mockResolvedValueOnce(ok(fxHistory("fx-gbpusd", "GBP/USD")))
      .mockResolvedValueOnce(ok(fxHistory("fx-eurgbp", "EUR/GBP")))
      .mockResolvedValueOnce(ok(fxHistory("fx-eurchf", "EUR/CHF")))
      .mockResolvedValueOnce(ok(fxHistory("fx-usdjpy", "USD/JPY")))
      .mockResolvedValueOnce(ok(fxHistory("fx-usdchf", "USD/CHF")))
      .mockResolvedValueOnce(ok(fxHistory("fx-usdcnh", "USD/CNH")))
      .mockResolvedValueOnce(ok(fxHistory("fx-usdcad", "USD/CAD")))
      .mockResolvedValueOnce(ok(fxHistory("fx-audusd", "AUD/USD")))
      .mockResolvedValueOnce(ok(fxHistory("fx-nzdusd", "NZD/USD")));
    vi.stubGlobal("fetch", fetchMock);

    await loadMacroWorkspace();

    expect(get(macroSnapshot)?.region).toBe("US");
    expect(Object.keys(get(macroSeriesHistories))).toEqual(
      expect.arrayContaining([
        "US:3M:fx-eurusd",
        "US:3M:fx-gbpusd",
        "US:3M:fx-eurgbp",
        "US:3M:fx-eurchf",
        "US:3M:fx-usdjpy",
        "US:3M:fx-usdcnh"
      ])
    );
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-eurusd/history?region=US&timeframe=3M")
    )).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-gbpusd/history?region=US&timeframe=3M")
    )).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-usdjpy/history?region=US&timeframe=3M")
    )).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-eurgbp/history?region=US&timeframe=3M")
    )).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-eurchf/history?region=US&timeframe=3M")
    )).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/macro/series/fx-usdcnh/history?region=US&timeframe=3M")
    )).toBe(true);
  });

  it("preserves one-shot IV data when idle session polling returns an empty surface", async () => {
    ivSurface.set(makeIvSurface({
      symbol: "AAPL",
      spot: 210,
      expiries: ["20260320"],
      strikes: [205, 210, 215],
      iv_grid: [[0.28, 0.27, 0.29]],
      points: 3
    }));
    const session: IvSessionStatus = {
      running: false,
      status_text: "Idle",
      active_symbol: null,
      market_data_mode: "delayed",
      messages: [],
      surface: {
        ...makeIvSurface({ symbol: "AAPL" }),
        snapshot_available: false,
        spot: null,
        expiries: [],
        strikes: [],
        iv_grid: [],
        points: 0
      }
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(session)));
    ivError.set("No market data entitlement for XLE.");

    await loadIvSession();

    expect(get(ivSession)?.running).toBe(false);
    expect(get(ivSurface)?.symbol).toBe("AAPL");
    expect(get(ivSurface)?.points).toBe(3);
    expect(get(ivError)).toBe("No market data entitlement for XLE.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed surface-load reason visible across an idle status poll", async () => {
    ivSurface.set(makeIvSurface({ symbol: "SPY", points: 3 }));
    const unavailable = {
      ...makeIvSurface({ symbol: "XLE" }),
      snapshot_available: false,
      spot: null,
      expiries: [],
      strikes: [],
      iv_grid: [],
      points: 0,
      warnings: ["No market data entitlement for XLE."],
    };
    const idle: IvSessionStatus = {
      running: false,
      status_text: "Idle",
      active_symbol: null,
      market_data_mode: "delayed",
      messages: [],
      surface: unavailable,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok(unavailable))
      .mockResolvedValueOnce(ok(idle));
    vi.stubGlobal("fetch", fetchMock);

    await loadIvSurface({ symbol: "XLE", depthPreset: "max" });
    await loadIvSession();

    expect(get(ivSurface)?.symbol).toBe("SPY");
    expect(get(ivError)).toBe("No market data entitlement for XLE.");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/iv/surface?symbol=XLE");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/iv/session");
  });

  it("queues, resolves, accepts, and dismisses Strategy Lab handoffs", async () => {
    const market = makePredictionMarket("polymarket:fed-cut");
    const handoff: StrategyLabHandoffEnvelope = {
      source_tab: "prediction_markets",
      source_mode: "detail",
      intended_target_tab: "strategy_lab",
      intended_target_mode: "composer",
      selected_entity: {
        entity_type: "prediction_market_contract",
        label: market.title,
        normalized_id: market.market_id,
        provider_id: market.provider_market_id,
        native_id: market.provider_condition_id,
        metadata: {}
      },
      resolver_capability: "return_leg",
      asset_class: "prediction_market",
      value_kind: "probability",
      default_side: "long_yes",
      default_weight: 0.1,
      selected_timeframe: null,
      provider: market.source_provider,
      source: null,
      warnings: [],
      normalized_ids: { market_id: market.market_id },
      timestamp: "2026-03-01T00:00:00Z"
    };
    const resolved = {
      handoff_id: "prediction_markets:polymarket:fed-cut:2026-03-01T00:00:00Z",
      envelope: handoff,
      status: "resolved",
      resolved_capability: "return_leg",
      composer_draft_leg: {
        label: "Will the Fed cut rates in March? | YES probability",
        asset_class: "prediction_contract",
        identifier: market.market_id,
        weight: 0.1,
        value_kind: "level",
        return_points: [
          { timestamp: "2026-03-01T00:00:00Z", value: 0.51 },
          { timestamp: "2026-03-02T00:00:00Z", value: 0.53 }
        ],
        object: null
      },
      benchmark_draft: null,
      lens: null,
      overlay: null,
      date_coverage: { label: "Probability history", start: "2026-03-01T00:00:00Z", end: "2026-03-02T00:00:00Z" },
      provider_summary: "polymarket",
      provenance: { transformation: "long_yes_probability_return" },
      warnings: ["Probability history is a research proxy."],
      unsupported_reason: null
    };
    const fetchMock = vi.fn().mockResolvedValue(ok(resolved));
    vi.stubGlobal("fetch", fetchMock);

    const queued = enqueueStrategyLabHandoff(handoff);
    expect(get(strategyLabHandoffQueue)[0]?.id).toBe(queued.id);

    await resolvePendingStrategyLabHandoffs();

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/research/strategy-lab/resolve-handoff"), expect.any(Object));
    expect(get(strategyLabHandoffQueue)[0]?.status).toBe("resolved");
    expect(get(strategyLabHandoffQueue)[0]?.resolved?.composer_draft_leg?.identifier).toBe(market.market_id);

    const accepted = acceptResolvedStrategyLabHandoff(queued.id);
    expect(accepted?.status).toBe("resolved");
    expect(get(strategyLabHandoffQueue)).toHaveLength(0);

    enqueueStrategyLabHandoff(handoff);
    dismissStrategyLabHandoff(queued.id);
    expect(get(strategyLabHandoffQueue)).toHaveLength(0);

    enqueueStrategyLabHandoff(handoff);
    clearStrategyLabHandoffs();
    expect(get(strategyLabHandoffQueue)).toHaveLength(0);
  });

  it("excludes stale earlier-session handoffs from auto-resolution until revived", async () => {
    const queued = enqueueStrategyLabHandoff({
      source_tab: "equity_research",
      source_mode: "scope_analysis",
      intended_target_tab: "strategy_lab",
      intended_target_mode: "composer",
      selected_entity: {
        entity_type: "equity_symbol",
        label: "SMH",
        normalized_id: "SMH",
        provider_id: "SMH",
        native_id: "SMH",
        metadata: {}
      },
      resolver_capability: "return_leg",
      asset_class: "equity",
      value_kind: "return",
      default_side: "short",
      default_weight: -0.4,
      selected_timeframe: null,
      provider: "fixture",
      source: null,
      warnings: [],
      normalized_ids: { symbol: "SMH" },
      timestamp: "2026-06-01T00:00:00Z"
    });
    strategyLabHandoffQueue.update((current) =>
      current.map((item) => (item.id === queued.id ? { ...item, stale: true } : item))
    );
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await resolvePendingStrategyLabHandoffs();
    expect(fetchMock).not.toHaveBeenCalled();

    reviveStrategyLabHandoff(queued.id);
    const revived = get(strategyLabHandoffQueue).find((item) => item.id === queued.id);
    expect(revived?.stale).toBe(false);
    expect(revived?.status).toBe("pending");
    expect(revived?.resolved).toBeNull();

    strategyLabHandoffQueue.update((current) =>
      current.map((item) => (item.id === queued.id ? { ...item, stale: true } : item))
    );
    clearStaleStrategyLabHandoffs();
    expect(get(strategyLabHandoffQueue)).toHaveLength(0);
  });

  it("stops an active IV stream before loading a one-shot surface", async () => {
    const stoppedSession: IvSessionStatus = {
      running: false,
      status_text: "Stopped",
      active_symbol: "AAPL",
      market_data_mode: "delayed",
      messages: [],
      surface: makeIvSurface({ symbol: "AAPL" })
    };
    const surface = makeIvSurface({ symbol: "AAPL" });
    ivSession.set({
      ...stoppedSession,
      running: true,
      status_text: "Running (AAPL)",
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(stoppedSession))
      .mockResolvedValueOnce(ok(surface));
    vi.stubGlobal("fetch", fetchMock);

    await loadIvSurface({ symbol: "AAPL", depthPreset: "max", waitSeconds: 8 });

    expect(fetchMock.mock.calls[0]?.[0]).toContain("/iv/session/stop");
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/iv/surface?symbol=AAPL");
    expect(get(ivSession)?.running).toBe(false);
    expect(get(ivSurface)?.symbol).toBe("AAPL");
  });

  it("threads previous_response_id through follow-up copilot generations in the same macro context", async () => {
    const firstResult = makeCopilotResult("macro", "resp_macro_1", "Macro Thread 1");
    const secondResult = makeCopilotResult("macro", "resp_macro_2", "Macro Thread 2");
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(firstResult, init)))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(secondResult, init)));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("macro", "Map the active macro setup.");
    await loadCopilotResearchCard("macro", "Pressure-test the lead divergence.");

    const firstBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));

    expect(firstBody.previous_response_id).toBeUndefined();
    expect(secondBody.previous_response_id).toBe("resp_macro_1");
    expect(get(copilotThreads).macro.entries.map((entry) => entry.result.response_id)).toEqual([
      "resp_macro_1",
      "resp_macro_2"
    ]);
    expect(get(copilotThreads).macro.latestResponseId).toBe("resp_macro_2");
  });

  it("promotes the exact persisted shelf session without synthesizing duplicate turns", async () => {
    const result = makeCopilotResult("macro", "resp_shelf_1", "Exact shelf result");
    const thread = {
      domain: "macro" as const,
      sourceSessionId: "session-shelf-1",
      contextFingerprint: "fp-shelf-1",
      latestResponseId: "resp_shelf_1",
      entries: [
        {
          entryId: "resp_shelf_1",
          turnIndex: 0,
          prompt: "Open the exact shelf result.",
          continuedFromResponseId: null,
          result
        }
      ]
    };
    const summary = {
      session_id: "session-shelf-1",
      title: "Shelf session",
      created_at: "2026-07-25T10:00:00Z",
      updated_at: "2026-07-25T10:00:01Z",
      active_domain: "macro",
      active_context_fingerprint: "fp-shelf-1",
      turn_count: 1,
      memo_count: 0,
      report_count: 0,
      artifact_count: 0,
      warnings: [],
      archived_at: null
    };
    const exactTurn = {
      turn_id: "turn-shelf-1",
      turn_index: 0,
      prompt: "Open the exact shelf result.",
      result
    };
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.includes("/copilot/shelf/promote")) {
        return ok({
          promotion_id: "promotion-shelf-1",
          contract_version: "copilot.shelf-promotion.v1",
          status: "promoted",
          source_session_id: "session-shelf-1",
          source_domain: "macro",
          source_turn_ids: ["turn-shelf-1"],
          source_snapshot_ids: ["ctx-shelf-1"],
          context_fingerprint: "fp-shelf-1",
          context_contract_versions: ["copilot.context.v2"],
          selected_scope_domains: ["macro"],
          role: "research_agent",
          selected_profile: "standard",
          message: "Opened the exact persisted shelf session.",
          already_promoted: false,
          created_at: "2026-07-25T10:00:02Z"
        });
      }
      if (url.endsWith("/copilot/sessions/session-shelf-1")) {
        return ok({
          session: summary,
          turns: [exactTurn],
          memos: [],
          context_snapshots: [],
          artifacts: [],
          storage_warnings: []
        });
      }
      if (url.includes("/copilot/diagnostics")) {
        return ok({});
      }
      if (url.includes("/copilot/sessions")) {
        return ok([summary]);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const promotion = await promoteCopilotShelfThread(thread, {
      selectedScopeDomains: ["macro"],
      role: "research_agent",
      selectedProfile: "standard"
    });

    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(requestBody).toEqual({
      source_session_id: "session-shelf-1",
      source_domain: "macro",
      context_fingerprint: "fp-shelf-1",
      entries: [
        {
          turn_index: 0,
          prompt: "Open the exact shelf result.",
          response_id: "resp_shelf_1"
        }
      ],
      selected_scope_domains: ["macro"],
      role: "research_agent",
      selected_profile: "standard"
    });
    expect(promotion?.status).toBe("promoted");
    expect(get(activeCopilotSession)?.session.session_id).toBe("session-shelf-1");
    expect(get(activeCopilotSession)?.turns).toEqual([exactTurn]);
    expect(fetchMock.mock.calls.filter(([url]) =>
      String(url).endsWith("/copilot/sessions/session-shelf-1")
    )).toHaveLength(1);
  });

  it("starts a fresh copilot thread when the macro grounding lens changes", async () => {
    const firstResult = makeCopilotResult("macro", "resp_macro_1", "Macro Thread 1");
    const secondResult = makeCopilotResult("macro", "resp_macro_2", "Macro Thread 2");
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(firstResult, init)))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(secondResult, init)));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("macro", "Map the active macro setup.");
    setMacroContext({ region: "EU" });
    await loadCopilotResearchCard("macro", "Reframe the EU setup.");

    const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));
    expect(secondBody.context.macro.region).toBe("EU");
    expect(secondBody.previous_response_id).toBeUndefined();
    expect(get(copilotThreads).macro.entries).toHaveLength(1);
    expect(get(copilotThreads).macro.entries[0]?.result.response_id).toBe("resp_macro_2");
  });

  it("includes Strategy Lab state in the legacy research copilot context and fingerprint", async () => {
    const snapshot = makeSnapshot();
    researchResult.set(makeResearchResult("single_ticker", snapshot));
    const queued = enqueueStrategyLabHandoff({
      source_tab: "prediction_markets",
      source_mode: "detail",
      intended_target_tab: "strategy_lab",
      intended_target_mode: "composer",
      selected_entity: {
        entity_type: "prediction_market_contract",
        label: "Oil threshold market",
        normalized_id: "polymarket:oil",
        provider_id: "oil",
        native_id: "0xabc",
        metadata: {}
      },
      resolver_capability: "return_leg",
      asset_class: "prediction_market",
      value_kind: "probability",
      default_side: "long_yes",
      default_weight: 0.1,
      selected_timeframe: null,
      provider: "polymarket",
      source: null,
      warnings: ["Pending handoff still needs resolver coverage."],
      normalized_ids: { market_id: "polymarket:oil" },
      timestamp: "2026-06-27T00:00:00Z"
    });
    const baseFingerprint = previewCopilotThreadFingerprint("research", { workspaceMode: "research" });
    const composition = {
      ...makeStrategyLabResult(),
      name: "Composite Strategy",
      leg_contributions: { "scope-1": 0.6, "strategy-1": 0.4 },
      lenses: [],
      overlays: []
    };
    strategyLabResult.set(makeStrategyLabResult());
    strategyLabComposition.set(composition as any);
    const enrichedFingerprint = previewCopilotThreadFingerprint("research", { workspaceMode: "research" });
    const researchCard = makeCopilotResult("research", "resp_research_1", "Research Card");
    const fetchMock = vi.fn().mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(researchCard, init)));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("research", "Assess the current Strategy Lab setup.", {
      workspaceMode: "research"
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(enrichedFingerprint).not.toBe(baseFingerprint);
    expect(body.context_fingerprint).toBe(enrichedFingerprint);
    expect(body.context.research_state.result?.scope_type).toBe("single_ticker");
    expect(body.context.research_state.strategy_result?.name).toBe("CSV Strategy");
    expect(body.context.research_state.strategy_composition?.name).toBe("Composite Strategy");
    expect(body.context.research_state.strategy_lab_handoffs.context_state).toBe("pending_handoffs");
    expect(body.context.research_state.strategy_lab_handoffs.items[0]?.id).toBe(queued.id);
  });

  it("builds explicit strategy lab copilot context for pending and resolved handoffs", async () => {
    const market = makePredictionMarket("polymarket:oil");
    const handoff: StrategyLabHandoffEnvelope = {
      source_tab: "prediction_markets",
      source_mode: "detail",
      intended_target_tab: "strategy_lab",
      intended_target_mode: "composer",
      selected_entity: {
        entity_type: "prediction_market_contract",
        label: market.title,
        normalized_id: market.market_id,
        provider_id: market.provider_market_id,
        native_id: market.provider_condition_id,
        metadata: {}
      },
      resolver_capability: "return_leg",
      asset_class: "prediction_market",
      value_kind: "probability",
      default_side: "long_yes",
      default_weight: 0.1,
      selected_timeframe: null,
      provider: market.source_provider,
      source: null,
      warnings: ["Pending handoff still needs resolver coverage."],
      normalized_ids: { market_id: market.market_id },
      timestamp: "2026-06-27T00:00:00Z"
    };
    const resolved = {
      handoff_id: "prediction_markets:polymarket:oil:2026-06-27T00:00:00Z",
      envelope: handoff,
      status: "resolved",
      resolved_capability: "return_leg",
      composer_draft_leg: {
        label: "Oil threshold market | YES probability",
        asset_class: "prediction_contract",
        identifier: market.market_id,
        weight: 0.1,
        value_kind: "level",
        return_points: [
          { timestamp: "2026-06-01T00:00:00Z", value: 0.3 },
          { timestamp: "2026-06-02T00:00:00Z", value: 0.34 }
        ],
        object: {
          object_id: "strategy_lab:prediction:oil",
          object_type: "prediction_market_probability",
          display_name: "Oil threshold market YES probability",
          source_tab: "prediction_markets",
          source_mode: "detail",
          resolver_capabilities: ["return_leg"],
          symbols: [],
          constituents: [],
          weights: [],
          available_start: "2026-06-01T00:00:00Z",
          available_end: "2026-06-02T00:00:00Z",
          provider_summary: "polymarket",
          provenance: { transformation: "long_yes_probability_return" },
          warnings: ["Probability history is a research proxy."],
          return_points: [
            { timestamp: "2026-06-01T00:00:00Z", value: 0.3 },
            { timestamp: "2026-06-02T00:00:00Z", value: 0.34 }
          ]
        }
      },
      benchmark_draft: null,
      lens: null,
      overlay: null,
      date_coverage: { label: "Probability history", start: "2026-06-01T00:00:00Z", end: "2026-06-02T00:00:00Z" },
      provider_summary: "polymarket",
      provenance: { transformation: "long_yes_probability_return" },
      warnings: ["Probability history is a research proxy."],
      unsupported_reason: null
    };
    enqueueStrategyLabHandoff(handoff);
    const pendingFingerprint = previewCopilotThreadFingerprint("strategy_lab", { workspaceMode: "research" });
    const pendingCard = makeCopilotResult("strategy_lab", "resp_strategy_pending", "Pending Strategy Card");
    const pendingFetch = vi.fn().mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(pendingCard, init)));
    vi.stubGlobal("fetch", pendingFetch);

    await loadCopilotResearchCard("strategy_lab", "Explain pending handoff state.", {
      workspaceMode: "research"
    });

    const pendingBody = JSON.parse(String(pendingFetch.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(pendingBody.context.strategy_lab_state.handoff_context.context_state).toBe("pending_handoffs");
    expect(pendingBody.context.strategy_lab_state.handoff_context.has_pending).toBe(true);
    expect(pendingBody.context.strategy_lab_state.handoff_context.items[0]?.context_state).toBe("pending_resolution");
    expect(pendingBody.context.strategy_lab_state.handoff_context.items[0]?.resolved).toBeNull();

    const resolvedFetch = vi
      .fn()
      .mockResolvedValueOnce(ok(resolved))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(
        makeCopilotResult("strategy_lab", "resp_strategy_resolved", "Resolved Strategy Card"),
        init
      )));
    vi.stubGlobal("fetch", resolvedFetch);

    await resolvePendingStrategyLabHandoffs();
    const resolvedFingerprint = previewCopilotThreadFingerprint("strategy_lab", { workspaceMode: "research" });
    await loadCopilotResearchCard("strategy_lab", "Explain resolved handoff state.", {
      workspaceMode: "research"
    });

    const resolvedBody = JSON.parse(String(resolvedFetch.mock.calls[1]?.[1]?.body ?? "{}"));
    const handoffContext = resolvedBody.context.strategy_lab_state.handoff_context;
    expect(resolvedFingerprint).not.toBe(pendingFingerprint);
    expect(handoffContext.context_state).toBe("resolved_handoffs");
    expect(handoffContext.has_resolved).toBe(true);
    expect(handoffContext.items[0]?.resolved.resolved_objects.composer_draft_leg.return_point_count).toBe(2);
    expect(handoffContext.items[0]?.resolved.resolved_objects.composer_draft_leg.object_id).toBe("strategy_lab:prediction:oil");
    expect(get(copilotCards).strategy_lab?.response_id).toBe("resp_strategy_resolved");
  });

  it("builds distinct copilot contexts for equity research and strategy lab", async () => {
    const snapshot = makeSnapshot();
    researchResult.set(makeResearchResult("single_ticker", snapshot));
    strategyLabResult.set(makeStrategyLabResult());
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(
        makeCopilotResult("equity_research", "resp_equity_1", "Equity Card"),
        init
      )))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(
        makeCopilotResult("strategy_lab", "resp_strategy_1", "Strategy Card"),
        init
      )));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("equity_research", "Assess the active equity scope.", {
      workspaceMode: "research"
    });
    await loadCopilotResearchCard("strategy_lab", "Assess the active strategy setup.", {
      workspaceMode: "research"
    });

    const equityBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    const strategyBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));
    expect(equityBody.domain).toBe("equity_research");
    expect(equityBody.context.current_tab).toBe("equity_research");
    expect(equityBody.context.research_state.result?.scope_type).toBe("single_ticker");
    expect(strategyBody.domain).toBe("strategy_lab");
    expect(strategyBody.context.current_tab).toBe("strategy_lab");
    expect(strategyBody.context.strategy_lab_state.imported_result?.name).toBe("CSV Strategy");
    expect(get(copilotCards).equity_research?.response_id).toBe("resp_equity_1");
    expect(get(copilotCards).strategy_lab?.response_id).toBe("resp_strategy_1");
  });

  it("adds a visible copilot error turn when generation fails before a response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));

    const result = await loadCopilotResearchCard("macro", "Map the active macro setup.");

    expect(result?.status).toBe("error");
    expect(result?.message).toContain("Failed to fetch");
    expect(get(lastError)).toContain("Failed to fetch");
    expect(get(copilotCards).macro?.status).toBe("error");
    expect(get(copilotThreads).macro.entries).toHaveLength(1);
    expect(get(copilotThreads).macro.entries[0]?.prompt).toBe("Map the active macro setup.");
    expect(get(copilotThreads).macro.entries[0]?.result.message).toContain("Failed to fetch");
  });

  it("resumes a disconnected copilot stream from the last accepted sequence", async () => {
    const result = makeCopilotResult("macro", "resp_reconnected", "Reconnected Card");
    let runId = "";
    const encoder = new TextEncoder();
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => {
        const payload = JSON.parse(String(init?.body ?? "{}")) as { run_id: string };
        runId = payload.run_id;
        const partial = [
          JSON.stringify({
            run_id: runId,
            sequence: 0,
            event: "run.created",
            timestamp: "2026-03-01T00:00:00Z",
            data: { domain: "macro", provider: "mock" },
            result: null
          }),
          JSON.stringify({
            run_id: runId,
            sequence: 1,
            event: "text.delta",
            timestamp: "2026-03-01T00:00:01Z",
            data: { delta: "partial" },
            result: null
          })
        ].join("\n") + "\n";
        let sent = false;
        const body = new ReadableStream<Uint8Array>({
          pull(controller) {
            if (!sent) {
              sent = true;
              controller.enqueue(encoder.encode(partial));
              return;
            }
            controller.error(new Error("connection dropped"));
          }
        });
        return Promise.resolve(new Response(body, { status: 200 }));
      })
      .mockImplementationOnce(() => Promise.resolve(new Response(
        JSON.stringify({
          run_id: runId,
          sequence: 2,
          event: "completed",
          timestamp: "2026-03-01T00:00:02Z",
          data: { status: "ready" },
          result
        }) + "\n",
        { status: 200, headers: { "content-type": "application/x-ndjson" } }
      )));
    vi.stubGlobal("fetch", fetchMock);

    const settled = await loadCopilotResearchCard("macro", "Reconnect this run.");

    expect(settled?.response_id).toBe("resp_reconnected");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(`/copilot/runs/${runId}/events?after_sequence=1`);
    expect(get(copilotThreads).macro.entries).toHaveLength(1);
  });

  it("threads previous_response_id through synthesis follow-ups when the grounding scope is unchanged", async () => {
    const snapshot = makeSnapshot();
    portfolioSnapshot.set(snapshot);
    portfolioHistory.set({
      source: "local_history_store",
      points: [
        {
          timestamp: "2026-03-01T00:00:00Z",
          portfolio_value: 110,
          net_liquidation: 110,
          market_value: 110,
          cash: 0,
          base_currency: "USD"
        }
      ]
    });
    portfolioPerformance.set({
      benchmark_symbol: "SPY",
      benchmark_source: "history_SPY",
      performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1 }],
      benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1 }],
      portfolio_base_value: 110,
      missing_symbols: [],
      day_pnl: 1,
      day_pnl_pct: 0.01,
      day_pnl_source: "account_summary",
      message: null,
      warnings: []
    });
    macroSnapshot.set(makeMacroSnapshot());

    const firstResult = makeCopilotResult("synthesis", "resp_synthesis_1", "Synthesis Thread 1");
    const secondResult = makeCopilotResult("synthesis", "resp_synthesis_2", "Synthesis Thread 2");
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(firstResult, init)))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(secondResult, init)));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("synthesis", "Connect the loaded portfolio and macro context.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "macro"],
      activeTabId: "macro",
      reasoningEffort: "high"
    });
    await loadCopilotResearchCard("synthesis", "Pressure-test the cross-context disagreement.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "macro"],
      activeTabId: "macro"
    });

    const firstBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));

    expect(firstBody.context.current_tab).toBe("synthesis");
    expect(firstBody.reasoning_effort).toBe("high");
    expect(firstBody.synthesis.active_tab).toBe("macro");
    expect(firstBody.synthesis.included_scopes.map((item: { domain: string }) => item.domain)).toEqual([
      "portfolio",
      "macro"
    ]);
    expect(firstBody.previous_response_id).toBeUndefined();
    expect(secondBody.previous_response_id).toBe("resp_synthesis_1");
    expect(get(copilotThreads).synthesis.entries.map((entry) => entry.result.response_id)).toEqual([
      "resp_synthesis_1",
      "resp_synthesis_2"
    ]);
    expect(get(copilotThreads).synthesis.latestResponseId).toBe("resp_synthesis_2");
  });

  it("starts a fresh synthesis thread when the selected grounding scope changes materially", async () => {
    const snapshot = makeSnapshot();
    portfolioSnapshot.set(snapshot);
    researchResult.set(makeResearchResult("single_ticker", snapshot));
    macroSnapshot.set(makeMacroSnapshot());

    const firstResult = makeCopilotResult("synthesis", "resp_synthesis_1", "Synthesis Thread 1");
    const secondResult = makeCopilotResult("synthesis", "resp_synthesis_2", "Synthesis Thread 2");
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(firstResult, init)))
      .mockImplementationOnce((_url, init) => Promise.resolve(copilotStreamOk(secondResult, init)));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("synthesis", "Connect the loaded portfolio and macro context.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "macro"],
      activeTabId: "macro"
    });
    await loadCopilotResearchCard("synthesis", "Reframe the scope around portfolio and research instead.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "research"],
      activeTabId: "research"
    });

    const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));
    expect(secondBody.synthesis.included_scopes.map((item: { domain: string }) => item.domain)).toEqual([
      "portfolio",
      "research"
    ]);
    expect(secondBody.previous_response_id).toBeUndefined();
    expect(get(copilotThreads).synthesis.entries).toHaveLength(1);
    expect(get(copilotThreads).synthesis.entries[0]?.result.response_id).toBe("resp_synthesis_2");
  });

  it("fans a /sitrep/workspace payload out into the per-domain stores", async () => {
    researchOverview.set(null);
    sitrepIndicesOverview.set(null);
    macroSnapshot.set(null);
    commoditiesWorkspace.set(null);
    predictionMarketScreener.set(null);
    newsFeed.set(null);
    const workspace = {
      equities_overview: null,
      indices_overview: null,
      macro_snapshot: makeMacroSnapshot(),
      commodities: null,
      prediction_markets: { markets: [], venues: [], warnings: [] },
      news: {
        items: [],
        source_provider: "sample_news",
        retrieved_at: "2026-07-12T18:00:00Z",
        origin: "test",
        freshness_label: "mocked",
        warnings: [],
        transformation_note: null
      },
      sections: ["equities", "indices", "macro", "commodities", "prediction_markets", "news"],
      section_warnings: ["SITREP section 'commodities' failed to load: boom"],
      source_provider: "gamma_sitrep",
      retrieved_at: "2026-07-12T18:00:00Z",
      origin: "sitrep_service.workspace",
      transformation_note: null
    };
    const fetchMock = vi.fn().mockResolvedValue(ok(workspace));
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadSitrepWorkspace();

    expect(result?.source_provider).toBe("gamma_sitrep");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/sitrep/workspace");
    expect(get(macroSnapshot)).not.toBeNull();
    expect(get(newsFeed)?.source_provider).toBe("sample_news");
    expect(get(predictionMarketScreener)).not.toBeNull();
    expect(get(researchOverview)).toBeNull();
    expect(get(sitrepIndicesOverview)).toBeNull();
    expect(get(commoditiesWorkspace)).toBeNull();
    expect(get(sitrepWorkspaceMeta)).toEqual({
      retrieved_at: "2026-07-12T18:00:00Z",
      sections: ["equities", "indices", "macro", "commodities", "prediction_markets", "news"],
      section_warnings: ["SITREP section 'commodities' failed to load: boom"]
    });
  });
});

describe("sitrep follow-ups store", () => {
  function makeLocalStorageStub(initial: Record<string, string> = {}) {
    const backing = new Map(Object.entries(initial));
    return {
      getItem: (key: string) => backing.get(key) ?? null,
      setItem: (key: string, value: string) => void backing.set(key, value),
      removeItem: (key: string) => void backing.delete(key),
      clear: () => backing.clear(),
      key: (index: number) => [...backing.keys()][index] ?? null,
      get length() {
        return backing.size;
      },
      _backing: backing
    };
  }

  const backendFollowUp = {
    id: "uuid-1",
    row_id: "evt-cpi",
    title: "CPI release",
    source: "Event",
    tone: "warning",
    detail: "Inflation / US",
    meta: "in 3d",
    note: "",
    status: "open",
    handoff: { targetTab: "macro", targetMode: "events_regimes" },
    saved_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
    resolved_at: null
  };

  beforeEach(() => {
    sitrepFollowUps.set([]);
  });

  it("migrates legacy localStorage follow-ups into the backend before listing", async () => {
    const storage = makeLocalStorageStub({
      "gamma.sitrep.follow_ups.v1": JSON.stringify([
        {
          id: "evt-cpi",
          source: "Event",
          tone: "warning",
          title: "CPI release",
          detail: "Inflation / US",
          meta: "in 3d",
          handoff: { targetTab: "macro", targetMode: "events_regimes" },
          saved_at: "2026-07-12T00:00:00Z"
        }
      ])
    });
    vi.stubGlobal("localStorage", storage);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(backendFollowUp))
      .mockResolvedValueOnce(ok({ items: [backendFollowUp] }));
    vi.stubGlobal("fetch", fetchMock);

    const items = await loadSitrepFollowUps();

    expect(items).toHaveLength(1);
    expect(get(sitrepFollowUps)[0]?.row_id).toBe("evt-cpi");
    const createCall = fetchMock.mock.calls[0];
    expect(String(createCall?.[0])).toContain("/sitrep/follow-ups");
    expect(createCall?.[1]?.method).toBe("POST");
    const createBody = JSON.parse(String(createCall?.[1]?.body ?? "{}"));
    expect(createBody.row_id).toBe("evt-cpi");
    expect(createBody.saved_at).toBe("2026-07-12T00:00:00Z");
    expect(storage.getItem("gamma.sitrep.follow_ups.v1")).toBeNull();
    expect(storage.getItem("gamma.sitrep.follow_ups.v1.migrated")).not.toBeNull();
  });

  it("keeps the legacy localStorage payload when migration fails", async () => {
    const legacyRaw = JSON.stringify([{ id: "evt-cpi", title: "CPI release" }]);
    const storage = makeLocalStorageStub({ "gamma.sitrep.follow_ups.v1": legacyRaw });
    vi.stubGlobal("localStorage", storage);
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("backend down"))
      .mockResolvedValueOnce(ok({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await loadSitrepFollowUps();

    expect(storage.getItem("gamma.sitrep.follow_ups.v1")).toBe(legacyRaw);
    expect(storage.getItem("gamma.sitrep.follow_ups.v1.migrated")).toBeNull();
  });

  it("toggles a follow-up on and off through the backend endpoints", async () => {
    vi.stubGlobal("localStorage", makeLocalStorageStub());
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(backendFollowUp));
    vi.stubGlobal("fetch", fetchMock);

    const created = await toggleSitrepFollowUpItem({
      id: "evt-cpi",
      source: "Event",
      tone: "warning",
      title: "CPI release",
      detail: "Inflation / US",
      meta: "in 3d",
      handoff: { targetTab: "macro", targetMode: "events_regimes" }
    });

    expect(created?.id).toBe("uuid-1");
    expect(get(sitrepFollowUps)).toHaveLength(1);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");

    fetchMock.mockResolvedValueOnce(ok({ success: true }));
    const removed = await toggleSitrepFollowUpItem({
      id: "evt-cpi",
      source: "Event",
      tone: "warning",
      title: "CPI release",
      detail: "Inflation / US",
      meta: "in 3d",
      handoff: null
    });

    expect(removed).toBeNull();
    expect(get(sitrepFollowUps)).toHaveLength(0);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("DELETE");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/sitrep/follow-ups/uuid-1");
  });

  it("updates note and resolved state in place", async () => {
    vi.stubGlobal("localStorage", makeLocalStorageStub());
    sitrepFollowUps.set([backendFollowUp as never]);
    const resolved = { ...backendFollowUp, status: "resolved", note: "watch 2s10s", resolved_at: "2026-07-13T00:00:00Z" };
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(resolved));
    vi.stubGlobal("fetch", fetchMock);

    const updated = await updateSitrepFollowUpItem("uuid-1", { note: "watch 2s10s", status: "resolved" });

    expect(updated?.status).toBe("resolved");
    expect(get(sitrepFollowUps)[0]?.note).toBe("watch 2s10s");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");

    fetchMock.mockResolvedValueOnce(ok({ success: true }));
    const dismissed = await dismissSitrepFollowUpItem("uuid-1");
    expect(dismissed).toBe(true);
    expect(get(sitrepFollowUps)).toHaveLength(0);
  });

  it("grounds a SITREP research card once the workspace is loaded", async () => {
    sitrepWorkspaceMeta.set(null);
    const blocked = await loadCopilotResearchCard("sitrep", "Summarize the situation report.", {
      workspaceMode: "research"
    });
    expect(blocked?.status).toBe("error");
    expect(blocked?.message).toContain("Load the SITREP workspace");

    sitrepWorkspaceMeta.set({
      retrieved_at: "2026-07-13T09:00:00Z",
      sections: ["equities", "indices", "macro", "commodities", "prediction_markets", "news"],
      section_warnings: []
    });
    const sitrepCard = makeCopilotResult("sitrep", "resp_sitrep_1", "SITREP card");
    const fetchMock = vi.fn().mockImplementation((_url, init) => Promise.resolve(copilotStreamOk(sitrepCard, init)));
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadCopilotResearchCard("sitrep", "Summarize the situation report.", {
      workspaceMode: "research"
    });

    expect(result?.status).toBe("ready");
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(body.domain).toBe("sitrep");
    expect(body.context.current_tab).toBe("sitrep");
    expect(get(copilotThreads).sitrep.entries).toHaveLength(1);
  });
});

function emptyCopilotCards() {
  return {
    portfolio: null,
    sitrep: null,
    research: null,
    equity_research: null,
    strategy_lab: null,
    macro: null,
    commodities: null,
    maritime: null,
    prediction_markets: null,
    crypto: null,
    fundamentals: null,
    risk: null,
    iv: null,
    synthesis: null
  };
}

function emptyCopilotThreads() {
  return {
    portfolio: { domain: "portfolio" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    sitrep: { domain: "sitrep" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    research: { domain: "research" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    equity_research: { domain: "equity_research" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    strategy_lab: { domain: "strategy_lab" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    macro: { domain: "macro" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    commodities: { domain: "commodities" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    maritime: { domain: "maritime" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    prediction_markets: { domain: "prediction_markets" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    crypto: { domain: "crypto" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    fundamentals: { domain: "fundamentals" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    risk: { domain: "risk" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    iv: { domain: "iv" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    synthesis: { domain: "synthesis" as const, contextFingerprint: null, latestResponseId: null, entries: [] }
  };
}

function emptyRiskCorrelationMatrix(): RiskResult["correlation_matrix"] {
  return {
    assets: [],
    cells: []
  };
}

function emptyRiskDependencyNetwork(): RiskResult["dependency_network"] {
  return {
    nodes: [],
    edges: [],
    clusters: [],
    methodology: null,
    universe_size: 0,
    observation_count: 0,
    edge_threshold: null,
    warnings: [],
    source_provider: "risk_service"
  };
}

function makeIvSurface(overrides: Partial<IvSurface> = {}): IvSurface {
  return {
    symbol: "SPY",
    timestamp: "2026-03-01T00:00:00Z",
    retrieved_at: "2026-03-01T00:00:00Z",
    snapshot_available: true,
    spot: 500,
    expiries: ["20260320"],
    strikes: [495, 500, 505],
    iv_grid: [[0.2, 0.19, 0.21]],
    delayed: true,
    points: 3,
    warnings: [],
    messages: [],
    source_provider: "ibkr",
    origin: "iv_surface_engine",
    transformation_note: null,
    freshness_label: "delayed",
    collection: null,
    quality: null,
    pairs: [],
    ...overrides
  };
}

function makeSnapshot(): PortfolioSnapshot {
  return {
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
        fx_rate: 1,
        instrument_id: "portfolio:stk:aapl",
        display_symbol: "AAPL",
        exchange: "SMART",
        primary_exchange: "NASDAQ",
        provider: "ibkr",
        provider_id: "AAPL"
      }
    ],
    total_market_value: 110,
    total_cash: 0,
    net_liquidation: 110,
    day_pnl: 1,
    day_pnl_pct: 0.01,
    day_pnl_source: "account_summary",
    warnings: []
  };
}

function makeResearchResult(scopeType: "single_ticker" | "synthetic_portfolio", snapshot: PortfolioSnapshot): ResearchResult {
  return {
    scope_type: scopeType,
    benchmark_symbol: "SPY",
    primary_symbol: scopeType === "single_ticker" ? snapshot.positions[0]?.symbol ?? null : null,
    observations_count: 10,
    latest_daily_return: 0.01,
    latest_daily_return_at: "2026-03-01T00:00:00Z",
    latest_price: scopeType === "single_ticker" ? 100 : null,
    latest_price_at: scopeType === "single_ticker" ? "2026-03-01T00:00:00Z" : null,
    snapshot,
    performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
    benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }],
    primary_price_points: scopeType === "single_ticker" ? [{ timestamp: "2026-03-01T00:00:00Z", value: 100 }] : [],
    weights: snapshot.positions.map((position) => ({
      symbol: position.symbol,
      weight: position.weight ?? 0,
      instrument_id: position.instrument_id,
      display_symbol: position.display_symbol
    })),
    summary: {
      total_return: 0.1,
      annual_return: 0.1,
      annual_vol: 0.2,
      max_drawdown: -0.05,
      beta: 1,
      correlation: 0.9
    },
    structure: {
      total_weight: 1,
      top_weight: scopeType === "single_ticker" ? 1 : 0.35,
      top5_weight: 1,
      concentration_hhi: scopeType === "single_ticker" ? 1 : 0.335,
      effective_positions: scopeType === "single_ticker" ? 1 : 2.99,
      aligned_symbol_count: snapshot.positions.length
    },
    coverage: {
      available_symbols: snapshot.positions.map((position) => position.symbol),
      missing_symbols: [],
      benchmark_overlap_count: 10
    },
    constituents: snapshot.positions.map((position) => ({
      symbol: position.symbol,
      weight: position.weight ?? 0,
      instrument_id: position.instrument_id,
      display_symbol: position.display_symbol,
      total_return: 0.1,
      annual_vol: 0.2,
      max_drawdown: -0.05,
      weighted_return: 0.1 * (position.weight ?? 0)
    })),
    warnings: []
  };
}

function makeResearchOverview(): ResearchOverviewResponse {
  return {
    universe_id: "sample_equities",
    universe_label: "Sample equities",
    universe_description: "Small offline-friendly listed-equity sample.",
    timeframe: "1M",
    lookback_days: 21,
    benchmark_symbol: "AAPL",
    available_universes: [
      {
        universe_id: "sample_equities",
        label: "Sample equities",
        description: "Small offline-friendly listed-equity sample.",
        instruments: [],
        limitations: ["Narrow sample universe."],
        metadata_source_label: "Local sample/watchlist metadata",
        coverage_label: "Sample watchlist, partial coverage",
        is_complete_universe: false
      }
    ],
    available_timeframes: ["1M", "3M", "6M", "1Y"],
    metric_options: [
      { metric_id: "return", label: "Return", description: "Total return." },
      { metric_id: "volatility", label: "Volatility", description: "Annualized volatility." },
      { metric_id: "beta", label: "Beta", description: "Benchmark beta." },
      { metric_id: "drawdown", label: "Drawdown", description: "Maximum drawdown." },
      { metric_id: "relative_return", label: "Relative", description: "Relative return." }
    ],
    sort_options: [
      { sort_id: "market_cap_desc", label: "Market Cap", description: "Size by market cap." },
      { sort_id: "universe_weight_desc", label: "Universe Weight", description: "Size by universe weight." }
    ],
    nodes: [
      {
        node_id: "instrument:AAPL",
        normalized_id: "research:AAPL:STK:SMART:USD",
        label: "Apple",
        level: "instrument",
        parent_id: "group:us_mega_cap_tech",
        group: "US Mega-Cap Tech",
        sector: "Information Technology",
        industry: "Consumer Electronics",
        symbol: "AAPL",
        instrument_id: "research:AAPL:STK:SMART:USD",
        weight: 1,
        market_cap_usd: 3_000_000_000_000,
        index_weight: null,
        sort_rank: 1,
        size: 1,
        metrics: {
          total_return: 0.05,
          annual_volatility: 0.2,
          beta: 1,
          max_drawdown: -0.03,
          relative_return: 0,
          latest_price: 100,
          observation_count: 21
        },
        source_provider: "mock",
        retrieved_at: "2026-03-01T00:00:00Z",
        origin: "research_service.overview.instrument",
        transformation_note: "Computed from daily close history.",
        freshness_label: "mocked",
        warnings: []
      }
    ],
    coverage: {
      instrument_count: 1,
      priced_count: 1,
      missing_symbols: [],
      benchmark_symbol: "AAPL",
      benchmark_available: true,
      benchmark_observation_count: 21,
      coverage_ratio: 1,
      missing_count: 0,
      thin_history_symbols: [],
      min_observation_count: 21,
      max_observation_count: 21,
      coverage_label: "Sample watchlist, partial coverage",
      history_source_label: "Mock sample-data daily history",
      metadata_source_label: "Local sample/watchlist metadata"
    },
    rankings: {
      leaders: [{ node_id: "instrument:AAPL", label: "Apple", group: "US Mega-Cap Tech", symbol: "AAPL", value: 0.05 }],
      laggards: [{ node_id: "instrument:AAPL", label: "Apple", group: "US Mega-Cap Tech", symbol: "AAPL", value: 0.05 }],
      highest_volatility: [{ node_id: "instrument:AAPL", label: "Apple", group: "US Mega-Cap Tech", symbol: "AAPL", value: 0.2 }],
      highest_beta: [{ node_id: "instrument:AAPL", label: "Apple", group: "US Mega-Cap Tech", symbol: "AAPL", value: 1 }],
      largest_drawdowns: [{ node_id: "instrument:AAPL", label: "Apple", group: "US Mega-Cap Tech", symbol: "AAPL", value: -0.03 }]
    },
    summary: {
      leading_group: null,
      lagging_group: null,
      highest_volatility_group: null,
      coverage_note: null
    },
    warnings: ["Narrow sample universe."],
    source_provider: "mock",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "research_service.overview",
    transformation_note: "Computed from daily close histories.",
    freshness_label: "mocked",
    history_source_label: "Mock sample-data daily history",
    metadata_source_label: "Local sample/watchlist metadata",
    coverage_label: "Sample watchlist, partial coverage"
  };
}

function makeStrategyLabResult(): StrategyLabResult {
  return {
    name: "CSV Strategy",
    value_kind: "return",
    benchmark_column: null,
    benchmark_value_kind: "return",
    metrics: makeResearchReturnMetrics(),
    returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
    equity_curve_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1.01 }],
    drawdown_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0 }],
    benchmark_points: [],
    benchmark_equity_curve_points: [],
    rolling_points: [],
    monthly_returns: [{ period: "2026-03", value: 0.01 }],
    annual_returns: [{ period: "2026", value: 0.01 }],
    warnings: ["Uploaded strategy returns are data inputs only."],
    source_provider: "uploaded_csv",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "research_service.strategy_lab.analyze",
    transformation_note: "CSV rows parsed as returns.",
    freshness_label: "derived"
  };
}

function makeResearchCompareResult(): ResearchCompareResult {
  return {
    left: {
      label: "Scope",
      object_type: "scope_analysis",
      metrics: makeResearchReturnMetrics(),
      returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
      normalized_nav_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1.01 }],
      drawdown_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0 }]
    },
    right: {
      label: "Strategy",
      object_type: "strategy_lab",
      metrics: makeResearchReturnMetrics(),
      returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }],
      normalized_nav_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1.02 }],
      drawdown_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0 }]
    },
    left_observation_count: 12,
    right_observation_count: 12,
    aligned_observation_count: 12,
    overlap_start: "2026-03-01T00:00:00Z",
    overlap_end: "2026-03-12T00:00:00Z",
    relative_return: -0.01,
    volatility_difference: 0.01,
    max_drawdown_difference: 0,
    correlation: 0.8,
    beta: 0.9,
    relative_nav_points: [{ timestamp: "2026-03-01T00:00:00Z", value: -0.01 }],
    relative_drawdown_points: [],
    warnings: ["Scenario output is read-only."],
    source_provider: "gamma_research",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "research_service.compare_scenario.analyze",
    transformation_note: "Aligned comparison.",
    freshness_label: "derived"
  };
}

function makeResearchReturnMetrics() {
  return {
    total_return: 0.01,
    annual_return: 0.1,
    annual_volatility: 0.2,
    sharpe_ratio: 0.5,
    sortino_ratio: 0.6,
    max_drawdown: -0.02,
    max_drawdown_duration: 2,
    observation_count: 12,
    frequency: "daily",
    periods_per_year: 252,
    start_date: "2026-03-01T00:00:00Z",
    end_date: "2026-03-12T00:00:00Z",
    benchmark_beta: 1,
    benchmark_correlation: 0.8,
    upside_capture: 1.1,
    downside_capture: 0.9
  };
}

function makeSavedResearchItem(id: string): SavedResearchItem {
  return {
    id,
    schema_version: 1,
    object_type: "strategy_lab",
    title: "Saved Strategy",
    notes: "",
    payload: { returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }] },
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
    warnings: [],
    source_provider: "gamma_saved_research",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "test",
    transformation_note: null
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

function copilotStreamOk(result: CopilotResearchCardResult, init: RequestInit | undefined) {
  const payload = JSON.parse(String(init?.body ?? "{}")) as { run_id?: string };
  const runId = payload.run_id ?? "run_test";
  const timestamp = "2026-03-01T00:00:00Z";
  const body = [
    JSON.stringify({
      run_id: runId,
      sequence: 0,
      event: "run.created",
      timestamp,
      data: { domain: result.domain, provider: result.provider, model: result.model },
      result: null
    }),
    JSON.stringify({
      run_id: runId,
      sequence: 1,
      event: "completed",
      timestamp,
      data: { status: result.status },
      result
    })
  ].join("\n") + "\n";
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/x-ndjson" }
  });
}

function notFound(body: unknown) {
  return {
    ok: false,
    status: 404,
    statusText: "Not Found",
    headers: new Headers({ "content-type": "application/json" }),
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    }
  };
}

function makePredictionMarket(marketId: string): PredictionMarket {
  return {
    market_id: marketId,
    venue: "polymarket",
    title: "Will the Fed cut rates in March?",
    subtitle: "50+ bps cut",
    description: "Fed decision contract",
    status: "open",
    category: "Economy",
    event_id: "polymarket:event:1",
    event_title: "Fed decision in March?",
    series_id: "polymarket:series:1",
    series_title: "FOMC",
    provider_market_id: "fed-cut",
    provider_condition_id: "0xabc",
    provider_event_id: "1",
    provider_series_id: "series-1",
    slug: "fed-cut",
    end_time: "2026-03-18T00:00:00Z",
    open_time: "2026-03-01T00:00:00Z",
    close_time: null,
    current_probability: 0.51,
    probability_label: "Yes",
    volume: 100000,
    volume_24h: 5000,
    liquidity: 25000,
    open_interest: 4000,
    best_bid: 0.5,
    best_ask: 0.52,
    spread: 0.02,
    recent_price_change: 0.03,
    resolved_probability: null,
    resolution_outcome: null,
    image_url: null,
    resolution_source: "Federal Reserve statement",
    outcomes: [
      {
        outcome_id: `${marketId}:yes`,
        label: "Yes",
        probability: 0.51,
        token_id: "yes-token",
        resolved: false,
        winner: null,
        source_provider: "polymarket",
        retrieved_at: "2026-03-01T00:05:00Z",
        origin: "polymarket.seed",
        transformation_note: null
      },
      {
        outcome_id: `${marketId}:no`,
        label: "No",
        probability: 0.49,
        token_id: "no-token",
        resolved: false,
        winner: null,
        source_provider: "polymarket",
        retrieved_at: "2026-03-01T00:05:00Z",
        origin: "polymarket.seed",
        transformation_note: "Derived as one minus the normalized Yes probability."
      }
    ],
    tags: ["Fed Rates"],
    freshness: {
      status: "fresh",
      is_stale: false,
      is_broken: false,
      reason: "Venue metadata is recent and no integrity issue was detected.",
      last_history_point_at: "2026-03-01T00:00:00Z",
      retrieval_age_seconds: 300,
      history_lag_seconds: 300
    },
    research_score: 88.5,
    research_rationale: "Research rank uses relevance 1.00, signal 0.75, recency 1.00, and resolution 0.86.",
    source_provider: "polymarket",
    retrieved_at: "2026-03-01T00:05:00Z",
    origin: "polymarket.seed",
    transformation_note: "Seed market."
  };
}

function makeCryptoToken(tokenId: string): CryptoToken {
  return {
    token_id: tokenId,
    symbol: "sol",
    name: "Solana",
    image_url: null,
    chain: "Solana",
    asset_platform_id: "solana",
    geckoterminal_network: "solana",
    contract_address: null,
    market_cap_rank: 6,
    current_price: 150,
    market_cap: 75000000000,
    fully_diluted_valuation: 90000000000,
    total_volume: 4500000000,
    circulating_supply: 500000000,
    total_supply: 600000000,
    max_supply: null,
    price_change_pct_24h: 4.2,
    price_change_pct_7d: 10.5,
    price_change_pct_30d: 18.2,
    market_cap_change_pct_24h: 4.0,
    high_24h: 155,
    low_24h: 143,
    homepage_url: null,
    description: null,
    categories: [],
    narrative_labels: [],
    layer_bucket: "layer_1",
    turnover_ratio_24h: 0.06,
    fdv_premium_ratio: 0.2,
    screen_score: 77.4,
    screen_rationale: "turnover 0.06x | 24H volume $4.5B",
    source_provider: "coingecko",
    retrieved_at: "2026-03-01T00:05:00Z",
    origin: "coingecko.markets",
    transformation_note: "Gamma screen score combines size and turnover."
  };
}

function makeCopilotResult(
  domain:
    | "portfolio"
    | "sitrep"
    | "research"
    | "equity_research"
    | "strategy_lab"
    | "macro"
    | "commodities"
    | "prediction_markets"
    | "crypto"
    | "fundamentals"
    | "risk"
    | "iv"
    | "synthesis",
  responseId: string,
  title: string
): CopilotResearchCardResult {
  return {
    domain,
    current_tab: domain,
    status: "ready",
    provider: "mock",
    model: "gamma-mock-research-card-v1",
    response_id: responseId,
    message: null,
    card: {
      title,
      hypothesis: "Follow the strongest grounded thread.",
      rationale: "This result is a test fixture.",
      required_data: ["Current Gamma context"],
      proposed_test: "Check whether continuation state is preserved.",
      confounders: ["Fixture data"],
      next_steps: ["Issue a follow-up prompt"],
      caveats: ["Test fixture only."],
      source_backed_claims: [
        {
          claim: "This card is sourced from a mocked response.",
          evidence_refs: ["fixture.source"]
        }
      ],
      inferred_claims: ["Thread handling is frontend stateful."]
    },
    sources: [
      {
        source_id: "fixture.source",
        label: "Fixture Source",
        kind: "fixture",
        provider: "mock",
        origin: "vitest",
        description: "Static fixture source",
        retrieved_at: "2026-03-01T00:00:00Z"
      }
    ],
    tool_traces: [
      {
        tool_name: "fixture_tool",
        summary: "Mock tool trace",
        arguments: {},
        source_ids: ["fixture.source"]
      }
    ],
    operator_events: [],
    warnings: []
  };
}

function makeMacroSnapshot(): MacroSnapshot {
  return {
    region: "US",
    timeframe: "3M",
    theme: "all",
    comparison_region: null,
    available_regions: ["US", "EU", "Global"],
    available_timeframes: ["1M", "3M", "6M", "1Y"],
    available_themes: ["all", "growth", "inflation", "policy", "recession_risk"],
    focus_items: [],
    snapshot_cards: [],
    rates_policy: null,
    cross_asset: [],
    top_divergences: [],
    event_studies: [],
    upcoming_events: [],
    warnings: [],
    source_provider: "mock",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "vitest",
    transformation_note: null
  };
}
