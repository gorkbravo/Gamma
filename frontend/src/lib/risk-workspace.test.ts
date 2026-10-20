import { describe, expect, it } from "vitest";
import { buildRiskWorkspaceModel, describeAnalysisWindow, type RiskMode } from "./risk-workspace";
import type { PortfolioSnapshot, RiskResult } from "./api/types";

const snapshot: PortfolioSnapshot = {
  timestamp: "2026-04-29T10:00:00Z",
  base_currency: "USD",
  account_summary: {},
  total_market_value: 100000,
  total_cash: 5000,
  net_liquidation: 105000,
  day_pnl: -750,
  day_pnl_pct: -0.0071,
  day_pnl_source: "broker",
  warnings: ["FX conversion uses latest available rate."],
  positions: [
    {
      symbol: "AAPL",
      sec_type: "STK",
      currency: "USD",
      quantity: 100,
      avg_cost: 150,
      market_price: 175,
      market_value: 35000,
      unrealized_pnl: 2500,
      weight: 0.3333,
      base_market_value: 35000,
      fx_rate: 1,
      instrument_id: "portfolio:stk:aapl",
      display_symbol: "AAPL",
      exchange: "SMART",
      primary_exchange: "NASDAQ",
      provider: "ibkr",
      provider_id: "AAPL",
    },
    {
      symbol: "MSFT",
      sec_type: "STK",
      currency: "USD",
      quantity: 100,
      avg_cost: 250,
      market_price: 315,
      market_value: 30000,
      unrealized_pnl: -500,
      weight: 0.2857,
      base_market_value: 30000,
      fx_rate: 1,
      instrument_id: "portfolio:stk:msft",
      display_symbol: "MSFT",
      exchange: "SMART",
      primary_exchange: "NASDAQ",
      provider: "ibkr",
      provider_id: "MSFT",
    },
    {
      symbol: "CASH-USD",
      sec_type: "CASH",
      currency: "USD",
      quantity: 5000,
      avg_cost: null,
      market_price: 1,
      market_value: 5000,
      unrealized_pnl: null,
      weight: 0.0476,
      base_market_value: 5000,
      fx_rate: 1,
      instrument_id: "cash:usd",
      display_symbol: "USD Cash",
      exchange: null,
      primary_exchange: null,
      provider: "portfolio",
      provider_id: "USD",
    },
  ],
};

const riskResult: RiskResult = {
  source_scope: "portfolio",
  source_label: "Live account portfolio",
  source_object_id: null,
  source_origin: null,
  metrics: {
    alpha: 0.95,
    lookback_days: 252,
    horizon_days: 1,
    portfolio_value: 105000,
    historical_var: -2200,
    historical_cvar: -3100,
    parametric_var: -2000,
    daily_vol: 0.012,
    annual_vol: 0.19,
    max_drawdown: -0.16,
    beta: 1.15,
    correlation: 0.82,
    alpha_annual: 0.03,
    covered_portfolio_value: 70000,
    covered_risk_basis_value: 65000,
    risk_basis_value: 70000,
    risk_coverage_ratio: 0.928,
    historical_var_total_estimate: -2369,
    historical_cvar_total_estimate: -3338,
    parametric_var_total_estimate: -2153,
    monte_carlo_model: "Gaussian",
    monte_carlo_horizon_days: 10,
    monte_carlo_num_simulations: 2000,
    monte_carlo_var: null,
    monte_carlo_cvar: null,
    monte_carlo_var_total_estimate: null,
    monte_carlo_cvar_total_estimate: null,
    aligned_obs_count: 6,
    benchmark_overlap_count: 6,
    concentration_hhi: 0.21,
    top5_weight: 0.666,
    effective_bets: 4.76,
  },
  portfolio_return_points: [
    { timestamp: "2026-04-22T00:00:00Z", value: 0.01 },
    { timestamp: "2026-04-23T00:00:00Z", value: -0.02 },
    { timestamp: "2026-04-24T00:00:00Z", value: -0.03 },
    { timestamp: "2026-04-27T00:00:00Z", value: 0.015 },
    { timestamp: "2026-04-28T00:00:00Z", value: -0.01 },
    { timestamp: "2026-04-29T00:00:00Z", value: 0.005 },
  ],
  benchmark_return_points: [
    { timestamp: "2026-04-22T00:00:00Z", value: 0.008 },
    { timestamp: "2026-04-23T00:00:00Z", value: -0.015 },
    { timestamp: "2026-04-24T00:00:00Z", value: -0.02 },
    { timestamp: "2026-04-27T00:00:00Z", value: 0.01 },
    { timestamp: "2026-04-28T00:00:00Z", value: -0.007 },
    { timestamp: "2026-04-29T00:00:00Z", value: 0.004 },
  ],
  contributions: [
    {
      symbol: "AAPL",
      instrument_id: "portfolio:stk:aapl",
      display_symbol: "AAPL",
      weight: 0.3333,
      daily_vol: 0.015,
      variance_contribution_pct: 0.58,
      marginal_contribution_to_risk: 0.01,
      component_var: 1200,
    },
    {
      symbol: "MSFT",
      instrument_id: "portfolio:stk:msft",
      display_symbol: "MSFT",
      weight: 0.2857,
      daily_vol: 0.012,
      variance_contribution_pct: 0.36,
      marginal_contribution_to_risk: 0.009,
      component_var: 900,
    },
  ],
  monte_carlo: { terminal_returns: [], fan_percentiles: {}, sample_paths: {} },
  frontier_points: [
    {
      label: "Current",
      kind: "current",
      annual_return: 0.08,
      annual_vol: 0.19,
      sharpe: 0.42,
      weights: [
        { symbol: "AAPL", instrument_id: "portfolio:stk:aapl", display_symbol: "AAPL", weight: 0.54 },
        { symbol: "MSFT", instrument_id: "portfolio:stk:msft", display_symbol: "MSFT", weight: 0.46 },
      ],
    },
    {
      label: "Min Vol",
      kind: "candidate",
      annual_return: 0.07,
      annual_vol: 0.16,
      sharpe: 0.44,
      weights: [
        { symbol: "AAPL", instrument_id: "portfolio:stk:aapl", display_symbol: "AAPL", weight: 0.4 },
        { symbol: "MSFT", instrument_id: "portfolio:stk:msft", display_symbol: "MSFT", weight: 0.6 },
      ],
    },
  ],
  correlation_matrix: {
    assets: [
      { symbol: "AAPL", instrument_id: "portfolio:stk:aapl", display_symbol: "AAPL" },
      { symbol: "MSFT", instrument_id: "portfolio:stk:msft", display_symbol: "MSFT" },
    ],
    cells: [
      { row: "portfolio:stk:aapl", column: "portfolio:stk:aapl", correlation: 1 },
      { row: "portfolio:stk:aapl", column: "portfolio:stk:msft", correlation: 0.68 },
      { row: "portfolio:stk:msft", column: "portfolio:stk:aapl", correlation: 0.68 },
      { row: "portfolio:stk:msft", column: "portfolio:stk:msft", correlation: 1 },
    ],
  },
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
  excluded_assets: [{ symbol: "BND", instrument_id: null, display_symbol: "BND", reason: "No historical bars" }],
  warnings: ["Risk coverage below 95%; headline risk estimates may be materially incomplete."],
};

describe("risk workspace view-model", () => {
  it("builds shared context, alerts, and mode KPI strips from one risk result", () => {
    const model = buildRiskWorkspaceModel(snapshot, riskResult, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.context.baseCurrency).toBe("USD");
    expect(model.context.sourceLabel).toBe("Live account portfolio");
    expect(model.context.coverageLabel).toContain("92.8%");
    expect(model.overviewKpis.map((kpi) => kpi.label)).toContain("VaR / expected shortfall");
    expect(model.exposureKpis.map((kpi) => kpi.label)).toContain("Effective positions");
    expect(model.drawdownEpisodes[0]?.contributors).toContain("AAPL");
    expect(model.alerts.some((alert) => alert.includes("Concentration breach"))).toBe(true);
    expect(model.alerts.some((alert) => alert.includes("Missing/stale data"))).toBe(true);
  });

  it("splits the historical expected shortfall across positions", () => {
    const withEs: RiskResult = {
      ...riskResult,
      component_es_tail_days: 13,
      contributions: [
        { ...riskResult.contributions[0], component_es: 1500 },
        { ...riskResult.contributions[1], component_es: 500 },
      ],
    };
    const model = buildRiskWorkspaceModel(snapshot, withEs, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.contributionTailDays).toBe(13);
    expect(model.riskContributors.map((row) => [row.symbol, row.componentEs, row.esShare])).toEqual([
      ["AAPL", 1500, 0.75],
      ["MSFT", 500, 0.25],
    ]);

    // Sin desglose del ES (respuesta antigua) las columnas quedan vacías en vez de inventar un reparto.
    const legacy = buildRiskWorkspaceModel(snapshot, riskResult, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });
    expect(legacy.contributionTailDays).toBeNull();
    expect(legacy.riskContributors.every((row) => row.componentEs === null && row.esShare === null)).toBe(true);
  });

  it("labels Strategy Lab research-book sources distinctly", () => {
    const model = buildRiskWorkspaceModel(snapshot, {
      ...riskResult,
      source_scope: "research_book",
      source_label: "Strategy Lab book: JETS / XLE",
      source_object_id: "strategy_research_book:jets-xle",
      source_origin: "research_service.strategy_lab.portfolio_compose",
      contributions: [
        {
          symbol: "XOM",
          instrument_id: "leg:xom",
          display_symbol: "XOM",
          weight: 0.6,
          daily_vol: 0.01,
          variance_contribution_pct: 0.7,
          marginal_contribution_to_risk: 0.01,
          component_var: 700
        },
        {
          symbol: "AMD",
          instrument_id: "leg:amd",
          display_symbol: "AMD",
          weight: -0.4,
          daily_vol: 0.02,
          variance_contribution_pct: 0.3,
          marginal_contribution_to_risk: -0.01,
          component_var: 300
        }
      ]
    }, {
      sourceScope: "research_book",
      sourceLabel: "Strategy Lab book: JETS / XLE",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.context.sourceScope).toBe("research_book");
    expect(model.context.sourceLabel).toBe("Strategy Lab book: JETS / XLE");
    expect(model.provenance.join(" ")).toContain("Strategy Lab validated aggregate return stream");
    expect(model.riskContributors.map((row) => row.symbol)).toEqual(["XOM", "AMD"]);
    expect(model.holdings).toEqual([]);
    expect(model.largestMovers).toEqual([]);
    expect(model.concentrationFlags).toEqual([]);
  });

  it("keeps optimization output as diagnostics-only candidate allocations", () => {
    const model = buildRiskWorkspaceModel(snapshot, riskResult, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.candidates.length).toBeGreaterThan(0);
    expect(model.diagnostics.join(" ")).toContain("backend efficient frontier");
    expect(model.constraints.map((row) => row.cells[0])).toContain("Long-only");
    expect(model.optimizationComparison.map((row) => row.cells[0])).toContain("Min Vol");
    expect(model.frontierPoints.length).toBeGreaterThan(0);
  });

  it("passes cached equity frontier points through without using them for candidate allocations", () => {
    const model = buildRiskWorkspaceModel(
      snapshot,
      {
        ...riskResult,
        frontier_points: [
          ...riskResult.frontier_points,
          {
            label: "CACHEA",
            kind: "cached_equity_asset",
            annual_return: 0.18,
            annual_vol: 0.32,
            sharpe: 0.56,
            weights: [{ symbol: "CACHEA", instrument_id: "CACHEA", display_symbol: "CACHEA", weight: 1 }],
            history_rows: 90,
            history_start: "2026-01-02",
            history_end: "2026-05-07",
            source_provider: "market_data_cache",
          },
          {
            label: "Cached Equity Max Sharpe",
            kind: "cached_equity_candidate",
            annual_return: 0.15,
            annual_vol: 0.24,
            sharpe: 0.62,
            weights: [{ symbol: "CACHEA", instrument_id: "CACHEA", display_symbol: "CACHEA", weight: 1 }],
          },
        ],
      },
      {
        sourceScope: "portfolio",
        benchmarkSymbol: "SPY",
        returnFrequency: "daily",
      }
    );

    expect(model.frontierPoints.some((point) => point.kind === "cached_equity_asset")).toBe(true);
    expect(model.candidates.map((row) => row.symbol)).not.toContain("CACHEA");
    expect(model.optimizationKpis.find((kpi) => kpi.label === "Frontier assets")?.sublabel).toBe("covered risky sleeve");
  });

  it("populates correlation diagnostics from backend position-level returns", () => {
    const model = buildRiskWorkspaceModel(snapshot, riskResult, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.correlationKpis[0].value).toBe("0.68");
    expect(model.correlatedPairs[0].cells[0]).toContain("AAPL / MSFT");
    expect(model.correlationMatrix.assets).toHaveLength(2);
    expect(model.correlationMatrix.assets).toEqual([
      { key: "portfolio:stk:aapl", label: "AAPL" },
      { key: "portfolio:stk:msft", label: "MSFT" },
    ]);
  });

  it("builds Scenarios from the measured replay, regimes and beta, never from proxy shocks", () => {
    const replay = {
      episodes: [
        {
          episode_id: "covid_2020", label: "COVID crash", start: "2020-02-19", end: "2020-03-23",
          description: "S&P 500 close-to-close peak to trough.", status: "partial",
          book_return: -0.18, book_pnl: -18900, benchmark_return: -0.34, active_return: 0.16,
          max_drawdown: -0.2, worst_day_return: -0.07, worst_day_date: "2020-03-16",
          covered_gross_weight: 0.8, gross_weight: 1, observation_count: 23, note: "80% covered",
          legs: [
            { symbol: "AAPL", instrument_id: "a", display_symbol: "AAPL", weight: 0.5, status: "covered", episode_return: -0.3, pnl: -15750, contribution_share: 0.83, start_price_date: "2020-02-19", end_price_date: "2020-03-23", note: null },
            { symbol: "NEW", instrument_id: "n", display_symbol: "NEW", weight: 0.2, status: "missing", episode_return: null, pnl: null, contribution_share: null, start_price_date: null, end_price_date: null, note: "Price history starts 2021-01-04, after the episode began." },
            { symbol: "MSFT", instrument_id: "m", display_symbol: "MSFT", weight: 0.3, status: "covered", episode_return: -0.1, pnl: -3150, contribution_share: 0.17, start_price_date: "2020-02-19", end_price_date: "2020-03-23", note: null },
          ],
        },
        {
          episode_id: "tariffs_2025", label: "2025 tariff shock", start: "2025-02-19", end: "2025-04-08",
          description: "S&P 500 close-to-close peak to trough.", status: "full",
          book_return: -0.05, book_pnl: -5250, benchmark_return: -0.19, active_return: 0.14,
          max_drawdown: -0.08, worst_day_return: -0.04, worst_day_date: "2025-04-04",
          covered_gross_weight: 1, gross_weight: 1, observation_count: 33, note: null, legs: [],
        },
        {
          episode_id: "gfc_2007_2009", label: "Global financial crisis", start: "2007-10-09", end: "2009-03-09",
          description: "S&P 500 close-to-close peak to trough.", status: "unavailable",
          book_return: null, book_pnl: null, benchmark_return: null, active_return: null,
          max_drawdown: null, worst_day_return: null, worst_day_date: null,
          covered_gross_weight: 0, gross_weight: 1, observation_count: 0, note: "No position has price history covering this window.", legs: [],
        },
      ],
      portfolio_value: 105000, base_currency: "USD", benchmark_symbol: "SPY", lookback_days: 5040,
      method: "Current weights are held through each documented episode.", warnings: [],
    };
    const withRegimes: RiskResult = {
      ...riskResult,
      regime_analysis: {
        status: "available", window_days: 21, threshold_annual_vol: 0.16, observation_count: 200, note: null,
        method: "Days are split at the median of the benchmark's trailing 21-day realized volatility.",
        regimes: [
          { regime: "calm", observation_count: 100, annual_vol: 0.12, historical_var: 0.012, historical_cvar: 0.015, benchmark_correlation: 0.6, benchmark_annual_vol: 0.1 },
          { regime: "stressed", observation_count: 100, annual_vol: 0.24, historical_var: 0.025, historical_cvar: 0.032, benchmark_correlation: 0.85, benchmark_annual_vol: 0.22 },
        ],
      },
    };
    const model = buildRiskWorkspaceModel(snapshot, withRegimes, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
      stressReplay: replay,
    });

    expect(model.stressState).toBe("ready");
    expect(model.stressEpisodes.map((row) => row.episodeId)).toEqual(["covid_2020", "tariffs_2025", "gfc_2007_2009"]);
    // Por defecto se elige el peor episodio cubierto.
    expect(model.selectedEpisode?.episodeId).toBe("covid_2020");
    expect(model.stressLegs.map((row) => row.symbol)).toEqual(["AAPL", "MSFT", "NEW"]);
    expect(model.stressEpisodes[0].coverage).toBe(0.8);
    expect(model.scenarioKpis.find((kpi) => kpi.label === "Episodes covered")?.value).toBe("2 / 3");
    expect(model.scenarioKpis.find((kpi) => kpi.label === "Worst episode")?.sublabel).toBe("COVID crash");
    expect(model.regimeRows.map((row) => row.cells[0])).toEqual(["Calm", "High vol"]);
    expect(model.correlationKpis.find((kpi) => kpi.label === "Stressed-regime corr")?.value).toBe("0.85");
    expect(model.betaShockRows).toHaveLength(3);
    // Ninguna fila inventada: no quedan los antiguos proxies de COVID, tipos, USD o petróleo.
    const text = JSON.stringify(model);
    expect(text).not.toContain("COVID-style");
    expect(text).not.toContain("Oil +20%");
    expect(text).not.toContain("Stress corr estimate");

    const chosen = buildRiskWorkspaceModel(snapshot, withRegimes, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
      stressReplay: replay,
      selectedEpisodeId: "tariffs_2025",
    });
    expect(chosen.selectedEpisode?.episodeId).toBe("tariffs_2025");

    const loading = buildRiskWorkspaceModel(snapshot, withRegimes, {
      sourceScope: "portfolio",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
      stressReplayLoading: true,
    });
    expect(loading.stressState).toBe("loading");
    expect(loading.stressEpisodes).toEqual([]);
  });

  it("pairs research-book legs by the matrix key, not the instrument id", () => {
    const bookResult: RiskResult = {
      ...riskResult,
      source_scope: "research_book",
      correlation_matrix: {
        assets: [
          { key: "1:leg:xom", symbol: "XOM", instrument_id: "leg:xom", display_symbol: "XOM" },
          { key: "2:leg:amd", symbol: "AMD", instrument_id: "leg:amd", display_symbol: "AMD" },
        ],
        cells: [
          { row: "1:leg:xom", column: "1:leg:xom", correlation: 1 },
          { row: "1:leg:xom", column: "2:leg:amd", correlation: -0.42 },
          { row: "2:leg:amd", column: "1:leg:xom", correlation: -0.42 },
          { row: "2:leg:amd", column: "2:leg:amd", correlation: 1 },
        ],
      },
    };
    const model = buildRiskWorkspaceModel(snapshot, bookResult, {
      sourceScope: "research_book",
      benchmarkSymbol: "SPY",
      returnFrequency: "daily",
    });

    expect(model.correlationMatrix.assets).toEqual([
      { key: "1:leg:xom", label: "XOM" },
      { key: "2:leg:amd", label: "AMD" },
    ]);
    expect(model.correlatedPairs[0].cells.slice(0, 2)).toEqual(["XOM / AMD", "-0.42"]);
  });

  it("surfaces the backend frontier reason when no frontier points are returned", () => {
    const model = buildRiskWorkspaceModel(
      snapshot,
      {
        ...riskResult,
        frontier_points: [],
        warnings: [
          ...riskResult.warnings,
          "Efficient frontier unavailable: need at least two eligible non-cash long positions with usable return variance (eligible 1; positive covered risky 2; snapshot risky 2; return columns 2).",
        ],
      },
      {
        sourceScope: "portfolio",
        benchmarkSymbol: "SPY",
        returnFrequency: "daily",
      }
    );

    expect(model.frontierMessage).toContain("eligible 1");
    expect(model.diagnostics[0]).toContain("eligible 1");
  });

  it("declares the complete risk mode union", () => {
    const modes: RiskMode[] = ["overview", "exposures", "drawdowns", "correlation", "scenarios", "optimization"];
    expect(modes).toHaveLength(6);
  });
});

describe("describeAnalysisWindow", () => {
  const metrics = {
    lookback_days: 252,
    requested_lookback_days: 252,
    aligned_obs_count: 252,
    raw_observation_count: 281,
    dropped_observation_count: 29,
    effective_start_date: "2025-08-29",
    effective_end_date: "2026-09-02",
    return_calendar_basis: "trading days from the provider's daily bar calendar",
  } as any;

  it("states requested and effective windows with dates and row reconciliation", () => {
    const line = describeAnalysisWindow({ metrics } as any);

    expect(line).toContain("requested 252 observations");
    expect(line).toContain("analysed 252");
    expect(line).toContain("2025-08-29 to 2026-09-02");
    expect(line).toContain("281 rows available, 29 outside the window");
  });

  it("omits the reconciliation clause when nothing was dropped", () => {
    const line = describeAnalysisWindow({
      metrics: { ...metrics, raw_observation_count: 252, dropped_observation_count: 0 },
    } as any);

    expect(line).not.toContain("outside the window");
  });

  it("handles a run with no analysed observations", () => {
    expect(describeAnalysisWindow(null)).toContain("none were analysed yet");
  });
});
