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
  IvSessionStatus,
  MacroDivergenceListResponse,
  MacroEventsResponse,
  MacroSeriesHistory,
  MacroSnapshot,
  PredictionCalibrationSummary,
  PredictionMarket,
  PredictionMarketListResponse,
  PredictionProbabilityHistoryResponse,
  PredictionWalletSummary,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  RelatedPredictionMarketListResponse,
  ResearchOverviewResponse,
  ResearchResult,
  RiskResult,
  SystemStatus
} from "../api/types";
import {
  copilotCards,
  copilotThreads,
  computeRisk,
  cryptoComparison,
  cryptoFlowSummary,
  cryptoLiquidity,
  cryptoPriceHistory,
  cryptoTokenDetail,
  cryptoWorkspace,
  diagnostics,
  ivSession,
  ivSurface,
  lastError,
  loadCopilotResearchCard,
  loadCryptoWorkspace,
  loadIvSession,
  loadMacroWorkspace,
  loadPortfolioSnapshot,
  loadPredictionMarketScreener,
  loadResearchOverview,
  loading,
  macroContext,
  macroDivergences,
  macroEvents,
  macroSeriesHistories,
  macroSnapshot,
  portfolioHistory,
  portfolioPerformance,
  portfolioSnapshot,
  predictionMarketCalibration,
  predictionMarketDetail,
  predictionMarketHistory,
  predictionMarketRelated,
  predictionMarketScreener,
  predictionMarketWallet,
  researchOverview,
  researchResult,
  riskResult,
  runResearch,
  setBaseCurrency,
  setMarketDataMode,
  setMacroContext,
  selectedCryptoTokenId,
  selectedPredictionMarketId,
  systemStatus
} from "./app";

describe("app store orchestration", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    systemStatus.set(null);
    diagnostics.set(null);
    portfolioSnapshot.set(null);
    portfolioHistory.set(null);
    portfolioPerformance.set(null);
    researchOverview.set(null);
    researchResult.set(null);
    selectedPredictionMarketId.set(null);
    selectedCryptoTokenId.set(null);
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
    lastError.set("");
    loading.set({
      status: false,
      diagnostics: false,
      diagnosticsAction: false,
      portfolio: false,
      portfolioAction: false,
      researchOverview: false,
      research: false,
      macro: false,
      macroHistory: false,
      prediction: false,
      predictionDetail: false,
      crypto: false,
      cryptoDetail: false,
      copilot: false,
      risk: false,
      iv: false,
      ivSession: false
    });
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
      snapshot,
      performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
      benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }],
      primary_price_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 100 }],
      weights: [{ symbol: "AAPL", weight: 1 }],
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
          total_return: 0.1,
          annual_vol: 0.2,
          max_drawdown: -0.05,
          weighted_return: 0.1
        }
      ],
      warnings: []
    };
    const risk: RiskResult = {
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
      "/research/overview?universe_id=sample_equities&timeframe=1M&benchmark_symbol=AAPL&force_refresh=true"
    );
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
        symbol: "SPY",
        timestamp: "2026-03-01T00:00:00Z",
        snapshot_available: true,
        spot: 500,
        expiries: ["20260320"],
        strikes: [495, 500, 505],
        iv_grid: [[0.2, 0.19, 0.21]],
        delayed: true,
        points: 3,
        warnings: [],
        messages: []
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
      .mockResolvedValueOnce(ok(fxHistory("fx-usdjpy", "USD/JPY")));
    vi.stubGlobal("fetch", fetchMock);

    await loadMacroWorkspace();

    expect(get(macroSnapshot)?.region).toBe("US");
    expect(Object.keys(get(macroSeriesHistories))).toEqual(
      expect.arrayContaining(["US:3M:fx-eurusd", "US:3M:fx-gbpusd", "US:3M:fx-usdjpy"])
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
  });

  it("preserves one-shot IV data when idle session polling returns an empty surface", async () => {
    ivSurface.set({
      symbol: "AAPL",
      timestamp: "2026-03-01T00:00:00Z",
      snapshot_available: true,
      spot: 210,
      expiries: ["20260320"],
      strikes: [205, 210, 215],
      iv_grid: [[0.28, 0.27, 0.29]],
      delayed: true,
      points: 3,
      warnings: [],
      messages: []
    });
    const session: IvSessionStatus = {
      running: false,
      status_text: "Idle",
      active_symbol: null,
      market_data_mode: "delayed",
      messages: [],
      surface: {
        symbol: "AAPL",
        timestamp: "2026-03-01T00:00:00Z",
        snapshot_available: false,
        spot: null,
        expiries: [],
        strikes: [],
        iv_grid: [],
        delayed: true,
        points: 0,
        warnings: [],
        messages: []
      }
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(session)));

    await loadIvSession();

    expect(get(ivSession)?.running).toBe(false);
    expect(get(ivSurface)?.symbol).toBe("AAPL");
    expect(get(ivSurface)?.points).toBe(3);
  });

  it("threads previous_response_id through follow-up copilot generations in the same macro context", async () => {
    const firstResult = makeCopilotResult("macro", "resp_macro_1", "Macro Thread 1");
    const secondResult = makeCopilotResult("macro", "resp_macro_2", "Macro Thread 2");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(firstResult))
      .mockResolvedValueOnce(ok(secondResult));
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

  it("starts a fresh copilot thread when the macro grounding lens changes", async () => {
    const firstResult = makeCopilotResult("macro", "resp_macro_1", "Macro Thread 1");
    const secondResult = makeCopilotResult("macro", "resp_macro_2", "Macro Thread 2");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(firstResult))
      .mockResolvedValueOnce(ok(secondResult));
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
      .mockResolvedValueOnce(ok(firstResult))
      .mockResolvedValueOnce(ok(secondResult));
    vi.stubGlobal("fetch", fetchMock);

    await loadCopilotResearchCard("synthesis", "Connect the loaded portfolio and macro context.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "macro"],
      activeTabId: "macro"
    });
    await loadCopilotResearchCard("synthesis", "Pressure-test the cross-context disagreement.", {
      workspaceMode: "research",
      synthesisDomains: ["portfolio", "macro"],
      activeTabId: "macro"
    });

    const firstBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body ?? "{}"));

    expect(firstBody.context.current_tab).toBe("synthesis");
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
      .mockResolvedValueOnce(ok(firstResult))
      .mockResolvedValueOnce(ok(secondResult));
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
});

function emptyCopilotCards() {
  return {
    portfolio: null,
    research: null,
    macro: null,
    prediction_markets: null,
    crypto: null,
    risk: null,
    iv: null,
    synthesis: null
  };
}

function emptyCopilotThreads() {
  return {
    portfolio: { domain: "portfolio" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    research: { domain: "research" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    macro: { domain: "macro" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    prediction_markets: { domain: "prediction_markets" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    crypto: { domain: "crypto" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    risk: { domain: "risk" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    iv: { domain: "iv" as const, contextFingerprint: null, latestResponseId: null, entries: [] },
    synthesis: { domain: "synthesis" as const, contextFingerprint: null, latestResponseId: null, entries: [] }
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
  };
}

function makeResearchResult(scopeType: "single_ticker" | "synthetic_portfolio", snapshot: PortfolioSnapshot): ResearchResult {
  return {
    scope_type: scopeType,
    benchmark_symbol: "SPY",
    primary_symbol: scopeType === "single_ticker" ? snapshot.positions[0]?.symbol ?? null : null,
    observations_count: 10,
    snapshot,
    performance_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
    benchmark_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }],
    primary_price_points: scopeType === "single_ticker" ? [{ timestamp: "2026-03-01T00:00:00Z", value: 100 }] : [],
    weights: snapshot.positions.map((position) => ({
      symbol: position.symbol,
      weight: position.weight ?? 0
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
        limitations: ["Narrow sample universe."]
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
      benchmark_observation_count: 21
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
    freshness_label: "mocked"
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
    | "research"
    | "macro"
    | "prediction_markets"
    | "crypto"
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
