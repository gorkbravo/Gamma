import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DiagnosticsResponse,
  IvSessionStatus,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  ResearchResult,
  RiskResult,
  SystemStatus
} from "../api/types";
import {
  computeRisk,
  diagnostics,
  ivSession,
  ivSurface,
  lastError,
  loadIvSession,
  loadPortfolioSnapshot,
  loading,
  portfolioHistory,
  portfolioPerformance,
  portfolioSnapshot,
  researchResult,
  riskResult,
  runResearch,
  setMarketDataMode,
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
    researchResult.set(null);
    riskResult.set(null);
    ivSurface.set(null);
    ivSession.set(null);
    lastError.set("");
    loading.set({
      status: false,
      diagnostics: false,
      diagnosticsAction: false,
      portfolio: false,
      portfolioAction: false,
      research: false,
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
});

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
