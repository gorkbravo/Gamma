import { describe, expect, it } from "vitest";
import type { ResearchResult } from "../api/types";
import {
  buildResearchObjectFromScopeResult,
  buildResearchObjectFromStrategyResult,
  buildEquityStrategyHandoff,
  buildPredictionMarketStrategyHandoff,
  buildStrategyComposerObjects,
  buildStrategyPortfolioLegInputs,
  buildResearchCompareOptions,
  buildResearchTreemapLayout,
  buildResearchTreemapSections,
  buildPreviewRows,
  classifyResearchSurfaceMode,
  classifySavedResearchSurface,
  defaultStrategyPortfolioDraftLeg,
  deriveConstituentsFromResearchResult,
  deriveCoverageFromResearchResult,
  deriveStructureFromWeights,
  doesResearchDraftMatchResult,
  formatResearchOverviewMetricValue,
  formatResearchOverviewSortValue,
  hydrateStrategyLabResultFromSaved,
  normalizeSyntheticText,
  parseResearchCsvText,
  parseStrategyPortfolioHistoryText,
  parseSyntheticText,
  savedResearchCanReloadScope,
  savedResearchCanReloadStrategy,
  savedResearchScopeDraft,
  strategyResolvedHandoffToDraftLeg,
  summarizeStrategyPortfolioDraft
} from "./research";

describe("research view model helpers", () => {
  it("builds normalized preview rows for synthetic drafts", () => {
    const previewRows = buildPreviewRows(
      "synthetic_portfolio",
      "",
      parseSyntheticText("XLV 35\nXLP 35\nXLU 30")
    );

    expect(previewRows).toEqual([
      { symbol: "XLV", inputWeight: 35, normalizedWeight: 0.35 },
      { symbol: "XLP", inputWeight: 35, normalizedWeight: 0.35 },
      { symbol: "XLU", inputWeight: 30, normalizedWeight: 0.3 }
    ]);
  });

  it("matches a normalized synthetic draft to the executed research result", () => {
    const previewRows = buildPreviewRows(
      "synthetic_portfolio",
      "",
      parseSyntheticText(normalizeSyntheticText("XLV 35\nXLP 35\nXLU 30"))
    );

    expect(
      doesResearchDraftMatchResult(
        makeResearchResult("synthetic_portfolio", [
          { symbol: "XLV", weight: 0.35 },
          { symbol: "XLP", weight: 0.35 },
          { symbol: "XLU", weight: 0.3 }
        ]),
        {
          scopeType: "synthetic_portfolio",
          primarySymbol: "",
          benchmarkSymbol: "SPY"
        },
        previewRows
      )
    ).toBe(true);
  });

  it("detects when the builder draft diverges from the executed result", () => {
    const previewRows = buildPreviewRows("single_ticker", "MSFT", []);

    expect(
      doesResearchDraftMatchResult(
        makeResearchResult("single_ticker", [{ symbol: "AAPL", weight: 1 }]),
        {
          scopeType: "single_ticker",
          primarySymbol: "MSFT",
          benchmarkSymbol: "SPY"
        },
        previewRows
      )
    ).toBe(false);
  });

  it("derives active structure and constituents when the response omits them", () => {
    const result = makeResearchResult("synthetic_portfolio", [
      { symbol: "XLV", weight: 0.35 },
      { symbol: "XLP", weight: 0.35 },
      { symbol: "XLU", weight: 0.3 }
    ]);

    const structure = deriveStructureFromWeights(result.weights);
    const coverage = deriveCoverageFromResearchResult(result);
    const constituents = deriveConstituentsFromResearchResult(result);

    expect(structure.aligned_symbol_count).toBe(3);
    expect(structure.top_weight).toBeCloseTo(0.35);
    expect(coverage.available_symbols).toEqual(["XLV", "XLP", "XLU"]);
    expect(constituents).toHaveLength(3);
    expect(constituents[0]?.symbol).toBe("XLV");
  });

  it("builds stable treemap rectangles from Research Overview instrument nodes", () => {
    const overview = makeResearchOverview();
    const rects = buildResearchTreemapLayout(overview, "return");

    expect(rects).toHaveLength(3);
    expect(rects.map((rect) => rect.node.symbol)).toEqual(["SAP", "AAPL", "MSFT"]);
    expect(rects.every((rect) => rect.width > 0 && rect.height > 0)).toBe(true);
    expect(rects.every((rect) => rect.x >= 0 && rect.y >= 0)).toBe(true);
    expect(formatResearchOverviewMetricValue(rects[0]?.metricValue ?? null, "return")).toMatch(/%$/);
    expect(formatResearchOverviewMetricValue(1.234, "beta")).toBe("1.23");
  });

  it("builds grouped treemap sections sized by market cap", () => {
    const overview = makeResearchOverview();
    const sections = buildResearchTreemapSections(overview, "return", "market_cap_desc");

    expect(sections.map((section) => section.label)).toEqual(["US Mega-Cap Tech", "International Software"]);
    expect(sections[0]?.tiles.map((tile) => tile.node.symbol)).toEqual(["MSFT", "AAPL"]);
    expect(sections[0]?.tiles[0]?.metricValue).toBe(2_000_000_000_000);
    expect((sections[0]?.rect.width ?? 0) * (sections[0]?.rect.height ?? 0)).toBeGreaterThan(
      10 * ((sections[1]?.rect.width ?? 0) * (sections[1]?.rect.height ?? 0))
    );
    expect(formatResearchOverviewSortValue(sections[0]?.tiles[0]?.metricValue, "market_cap_desc")).toBe("$2.00T");
  });

  it("parses CSV text with quoted cells and row diagnostics", () => {
    const parsed = parseResearchCsvText('date,name,return\n2026-01-02,"Strategy, A",1%\n2026-01-03,Strategy B');

    expect(parsed.columns).toEqual(["date", "name", "return"]);
    expect(parsed.rows[0]).toEqual({ date: "2026-01-02", name: "Strategy, A", return: "1%" });
    expect(parsed.rows[1]?.return).toBe("");
    expect(parsed.warnings[0]).toContain("Row 3");
  });

  it("builds compare options from active scope, strategy, and saved streams", () => {
    const scope = makeResearchResult("single_ticker", [{ symbol: "AAPL", weight: 1 }]);
    scope.performance_points = [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }];
    const strategy = {
      name: "CSV Strategy",
      returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }]
    } as any;
    const saved = [
      {
        id: "saved-1",
        title: "Saved Strategy",
        object_type: "strategy_lab",
        payload: { returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.03 }] },
        warnings: []
      }
    ] as any;

    expect(buildResearchCompareOptions(scope, strategy, saved).map((option) => option.id)).toEqual([
      "scope:latest",
      "strategy:latest",
      "saved:saved-1"
    ]);
  });

  it("classifies saved research surfaces by object type and return streams", () => {
    expect(classifySavedResearchSurface({ object_type: "scope_analysis", payload: {} } as any)).toBe("equity");
    expect(classifySavedResearchSurface({ object_type: "equity_scope", payload: {} } as any)).toBe("equity");
    expect(classifySavedResearchSurface({ object_type: "equity_screen", payload: {} } as any)).toBe("equity");
    expect(classifySavedResearchSurface({ object_type: "strategy_composition", payload: {} } as any)).toBe("strategy");
    expect(
      classifySavedResearchSurface({
        object_type: "custom_upload",
        payload: { returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }] }
      } as any)
    ).toBe("strategy");
    expect(classifySavedResearchSurface({ object_type: "memo", payload: {} } as any)).toBe("unknown");
  });

  it("classifies split equity research and strategy lab modes distinctly", () => {
    expect(classifyResearchSurfaceMode("equity", "overview")).toBe("overview");
    expect(classifyResearchSurfaceMode("equity", "scope_analysis")).toBe("scope_analysis");
    expect(classifyResearchSurfaceMode("equity", "comparables")).toBe("equity_comparables");
    expect(classifyResearchSurfaceMode("equity", "scenario_context")).toBe("equity_scenario_context");
    expect(classifyResearchSurfaceMode("equity", "saved_equity_research")).toBe("equity_saved");

    expect(classifyResearchSurfaceMode("strategy", "composer")).toBe("strategy_composer");
    expect(classifyResearchSurfaceMode("strategy", "backtest_analyze")).toBe("strategy_backtest");
    expect(classifyResearchSurfaceMode("strategy", "regime_stress")).toBe("strategy_regime");
    expect(classifyResearchSurfaceMode("strategy", "imports")).toBe("strategy_imports");
    expect(classifyResearchSurfaceMode("strategy", "saved_runs")).toBe("strategy_saved");

    expect(classifyResearchSurfaceMode("legacy", "strategy_lab")).toBe("legacy_strategy");
    expect(classifyResearchSurfaceMode("legacy", "compare_scenario")).toBe("legacy_compare");
    expect(classifyResearchSurfaceMode("equity", "composer")).toBe("unknown");
  });

  it("builds a strategy lab research object from scope performance", () => {
    const result = makeResearchResult("synthetic_portfolio", [
      { symbol: "XLV", weight: 0.35 },
      { symbol: "XLP", weight: 0.35 },
      { symbol: "XLU", weight: 0.3 }
    ]);
    result.performance_points = [
      { timestamp: "2026-03-01T00:00:00Z", value: 0.01 },
      { timestamp: "2026-03-02T00:00:00Z", value: 0.02 }
    ];
    result.source_provider = "gamma_research";
    result.history_source_label = "Local daily history";
    result.freshness_label = "cached";

    const object = buildResearchObjectFromScopeResult(result);

    expect(object?.object_type).toBe("equity_scope");
    expect(object?.display_name).toBe("Synthetic Basket");
    expect(object?.source_tab).toBe("equity_research");
    expect(object?.source_mode).toBe("scope_analysis");
    expect(object?.resolver_capabilities).toEqual(["return_leg", "benchmark"]);
    expect(object?.symbols).toEqual(["XLV", "XLP", "XLU"]);
    expect(object?.constituents).toEqual(result.constituents);
    expect(object?.weights).toEqual(result.weights);
    expect(object?.available_start).toBe("2026-03-01T00:00:00Z");
    expect(object?.available_end).toBe("2026-03-02T00:00:00Z");
    expect(object?.provider_summary).toBe("Local daily history");
    expect(object?.provenance).toMatchObject({ source_provider: "gamma_research", freshness_label: "cached" });
    expect(object?.return_points).toEqual(result.performance_points);
    expect(buildResearchObjectFromScopeResult(null)).toBeNull();
    expect(buildResearchObjectFromScopeResult(makeResearchResult("single_ticker", [{ symbol: "AAPL", weight: 1 }]))).toBeNull();
  });

  it("builds strategy composer objects from latest scope, imported strategy, and saved return streams", () => {
    const scope = makeResearchResult("single_ticker", [{ symbol: "AAPL", weight: 1 }]);
    scope.performance_points = [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }];
    const strategy = makeStrategyLabResult();
    const options = buildStrategyComposerObjects(scope, strategy as any, [
      {
        id: "saved-1",
        object_type: "strategy_lab",
        title: "Saved Strategy",
        payload: strategy as unknown as Record<string, unknown>,
        warnings: []
      } as any
    ]);

    expect(options.map((option) => option.object.object_type)).toContain("equity_scope");
    expect(options.map((option) => option.object.object_type)).toContain("strategy_return_stream");
    expect(options.map((option) => option.id)).toContain("saved:saved-1");
  });

  it("parses inline Strategy Lab portfolio history and signed exposures", () => {
    const parsed = parseStrategyPortfolioHistoryText("date,value\n2026-01-02,51%\n2026-01-05,0.53");
    const legs = [
      { ...defaultStrategyPortfolioDraftLeg(1), label: "Long Contract", assetClass: "prediction_contract" as const, weight: 0.7, historyText: "date,value\n2026-01-02,0.51\n2026-01-05,0.53" },
      { ...defaultStrategyPortfolioDraftLeg(2), label: "Short ETF", assetClass: "etf" as const, identifier: "SPY", weight: -0.3 }
    ];
    const summary = summarizeStrategyPortfolioDraft(legs);
    const built = buildStrategyPortfolioLegInputs(legs, []);

    expect(parsed.points).toEqual([
      { timestamp: "2026-01-02", value: 0.51 },
      { timestamp: "2026-01-05", value: 0.53 }
    ]);
    expect(summary.grossExposure).toBeCloseTo(1.0);
    expect(summary.netExposure).toBeCloseTo(0.4);
    expect(summary.inlineHistoryLegs).toBe(1);
    expect(summary.listedIdentifierLegs).toBe(1);
    expect(built.legs.map((leg) => leg.weight)).toEqual([0.7, -0.3]);
    expect(built.legs[0]?.asset_class).toBe("prediction_contract");
    expect(built.legs[1]?.identifier).toBe("SPY");
  });

  it("builds prediction-market handoffs and converts resolved drafts into composer rows", () => {
    const market = {
      market_id: "polymarket:fed-cut",
      venue: "polymarket",
      title: "Will the Fed cut rates in March?",
      provider_market_id: "fed-cut",
      provider_condition_id: "0xabc",
      provider_event_id: "event-1",
      provider_series_id: "series-1",
      probability_label: "Yes",
      status: "open",
      category: "Economy",
      source_provider: "polymarket",
      origin: "polymarket.seed",
      retrieved_at: "2026-03-01T00:05:00Z",
      end_time: "2026-03-18T00:00:00Z",
      freshness: {
        status: "fresh",
        is_stale: false,
        is_broken: false,
        reason: null
      }
    };
    const handoff = buildPredictionMarketStrategyHandoff(market);

    expect(handoff.source_tab).toBe("prediction_markets");
    expect(handoff.intended_target_tab).toBe("strategy_lab");
    expect(handoff.resolver_capability).toBe("return_leg");
    expect(handoff.asset_class).toBe("prediction_market");
    expect(handoff.default_side).toBe("long_yes");
    expect(handoff.normalized_ids.market_id).toBe(market.market_id);

    const noHandoff = buildPredictionMarketStrategyHandoff(market, { defaultSide: "long_no" });
    expect(noHandoff.default_side).toBe("long_no");
    expect(noHandoff.warnings.join(" ")).toContain("long_no_probability_return");

    const draft = strategyResolvedHandoffToDraftLeg(
      {
        handoff_id: "handoff-1",
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
        date_coverage: null,
        provider_summary: "polymarket",
        provenance: {},
        warnings: [],
        unsupported_reason: null
      },
      4
    );

    expect(draft?.assetClass).toBe("prediction_contract");
    expect(draft?.identifier).toBe(market.market_id);
    expect(draft?.valueKind).toBe("level");
    expect(draft?.historyText).toContain("2026-03-01T00:00:00Z,0.51");
  });

  it("builds equity research strategy handoffs for selected tickers", () => {
    const handoff = buildEquityStrategyHandoff({
      symbol: " msft ",
      label: "Microsoft",
      sourceProvider: "fixture"
    });

    expect(handoff.source_tab).toBe("equity_research");
    expect(handoff.source_mode).toBe("scope_analysis");
    expect(handoff.intended_target_tab).toBe("strategy_lab");
    expect(handoff.intended_target_mode).toBe("composer");
    expect(handoff.selected_entity.entity_type).toBe("equity_symbol");
    expect(handoff.selected_entity.normalized_id).toBe("MSFT");
    expect(handoff.resolver_capability).toBe("return_leg");
    expect(handoff.asset_class).toBe("equity");
    expect(handoff.value_kind).toBe("return");
    expect(handoff.default_side).toBe("long");
    expect(handoff.default_weight).toBe(0.1);
    expect(handoff.provider).toBe("fixture");
    expect(handoff.normalized_ids.symbol).toBe("MSFT");
    expect(handoff.warnings.join(" ")).toContain("read-only research return streams");
  });

  it("includes normalized weights in synthetic scope research object ids", () => {
    const first = makeResearchResult("synthetic_portfolio", [
      { symbol: "XLV", weight: 0.6 },
      { symbol: "XLP", weight: 0.4 }
    ]);
    const second = makeResearchResult("synthetic_portfolio", [
      { symbol: "XLV", weight: 0.4 },
      { symbol: "XLP", weight: 0.6 }
    ]);
    first.performance_points = [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }];
    second.performance_points = [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }];

    expect(buildResearchObjectFromScopeResult(first)?.object_id).not.toBe(
      buildResearchObjectFromScopeResult(second)?.object_id
    );
  });

  it("builds a strategy lab research object from strategy returns", () => {
    const result = makeStrategyLabResult();

    const object = buildResearchObjectFromStrategyResult(result);

    expect(object?.object_type).toBe("strategy_return_stream");
    expect(object?.display_name).toBe("CSV Strategy");
    expect(object?.source_tab).toBe("strategy_lab");
    expect(object?.source_mode).toBe("imports");
    expect(object?.resolver_capabilities).toEqual(["return_leg", "benchmark"]);
    expect(object?.available_start).toBe("2026-03-01T00:00:00Z");
    expect(object?.available_end).toBe("2026-03-01T00:00:00Z");
    expect(object?.provenance).toMatchObject({
      source_provider: "uploaded_csv",
      retrieved_at: "2026-03-01T00:00:00Z",
      origin: "research_service.strategy_lab.analyze",
      freshness_label: "derived"
    });
    expect(object?.return_points).toEqual(result.returns_points);
    expect(buildResearchObjectFromStrategyResult({ ...result, returns_points: [] })).toBeNull();
  });

  it("includes return stream values in strategy research object ids", () => {
    const first = makeStrategyLabResult();
    const second = {
      ...makeStrategyLabResult(),
      returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.02 }]
    };

    expect(buildResearchObjectFromStrategyResult(first)?.object_id).not.toBe(
      buildResearchObjectFromStrategyResult(second)?.object_id
    );
  });

  it("hydrates safe saved scope and strategy objects for reload", () => {
    const savedScope = {
      id: "scope-1",
      title: "Saved Scope",
      object_type: "scope_analysis",
      payload: {
        scope_type: "synthetic_portfolio",
        benchmark_symbol: "SPY",
        weights: [
          { symbol: "XLV", weight: 0.35 },
          { symbol: "XLP", weight: 0.35 },
          { symbol: "XLU", weight: 0.3 }
        ]
      },
      warnings: []
    } as any;
    const savedStrategy = {
      id: "strategy-1",
      title: "Saved Strategy",
      object_type: "strategy_lab",
      payload: {
        name: "Saved Strategy",
        value_kind: "return",
        benchmark_value_kind: "return",
        metrics: { total_return: 0.01, observation_count: 2, frequency: "daily", periods_per_year: 252 },
        returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }]
      },
      warnings: [],
      source_provider: "uploaded_csv",
      retrieved_at: "2026-03-01T00:00:00Z",
      updated_at: "2026-03-01T00:00:00Z",
      origin: "test",
      transformation_note: null
    } as any;

    expect(savedResearchCanReloadScope(savedScope)).toBe(true);
    expect(savedResearchScopeDraft(savedScope)?.syntheticText).toContain("XLV 0.3500");
    expect(savedResearchCanReloadStrategy(savedStrategy)).toBe(true);
    expect(hydrateStrategyLabResultFromSaved(savedStrategy)?.name).toBe("Saved Strategy");
  });
});

function makeResearchResult(
  scopeType: "single_ticker" | "synthetic_portfolio",
  weights: Array<{ symbol: string; weight: number }>
): ResearchResult {
  const normalizedWeights = weights.map((item) => ({
    ...item,
    instrument_id: `portfolio:stk:${item.symbol.toLowerCase()}`,
    display_symbol: item.symbol
  }));
  return {
    scope_type: scopeType,
    benchmark_symbol: "SPY",
    primary_symbol: scopeType === "single_ticker" ? weights[0]?.symbol ?? null : null,
    observations_count: 10,
    snapshot: null,
    performance_points: [],
    benchmark_points: [],
    primary_price_points: [],
    weights: normalizedWeights,
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
      aligned_symbol_count: weights.length
    },
    coverage: {
      available_symbols: weights.map((item) => item.symbol),
      missing_symbols: [],
      benchmark_overlap_count: 10
    },
    constituents: normalizedWeights.map((item) => ({
      symbol: item.symbol,
      weight: item.weight,
      instrument_id: item.instrument_id,
      display_symbol: item.display_symbol,
      total_return: null,
      annual_vol: null,
      max_drawdown: null,
      weighted_return: null
    })),
    warnings: []
  };
}

function makeResearchOverview() {
  return {
    universe_id: "sample_equities",
    universe_label: "Sample equities",
    universe_description: "Small offline-friendly listed-equity sample.",
    timeframe: "1M",
    lookback_days: 21,
    benchmark_symbol: "SPY",
    available_universes: [],
    available_timeframes: ["1M", "3M", "6M", "1Y"],
    metric_options: [],
    sort_options: [],
    nodes: [
      makeOverviewNode("instrument:AAPL", "AAPL", "Apple", "US Mega-Cap Tech", 0.05, 0.2),
      makeOverviewNode("instrument:MSFT", "MSFT", "Microsoft", "US Mega-Cap Tech", 0.08, 0.24),
      makeOverviewNode("instrument:SAP", "SAP", "SAP", "International Software", -0.02, 0.18)
    ],
    coverage: {
      instrument_count: 3,
      priced_count: 3,
      missing_symbols: [],
      benchmark_symbol: "SPY",
      benchmark_available: false,
      benchmark_observation_count: 0,
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
      leaders: [],
      laggards: [],
      highest_volatility: [],
      highest_beta: [],
      largest_drawdowns: []
    },
    summary: {
      leading_group: null,
      lagging_group: null,
      highest_volatility_group: null,
      coverage_note: null
    },
    warnings: [],
    source_provider: "mock",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "test",
    transformation_note: null,
    freshness_label: "mocked",
    history_source_label: "Mock sample-data daily history",
    metadata_source_label: "Local sample/watchlist metadata",
    coverage_label: "Sample watchlist, partial coverage"
  };
}

function makeOverviewNode(
  nodeId: string,
  symbol: string,
  label: string,
  group: string,
  totalReturn: number,
  annualVolatility: number
) {
  return {
    node_id: nodeId,
    normalized_id: symbol,
    label,
    level: "instrument",
    parent_id: `group:${group.toLowerCase().replaceAll(" ", "_")}`,
    group,
    sector: "Information Technology",
    industry: null,
    symbol,
    instrument_id: symbol,
    weight: 1,
    market_cap_usd: symbol === "MSFT" ? 2_000_000_000_000 : symbol === "AAPL" ? 1_000_000_000_000 : 250_000_000_000,
    index_weight: null,
    sort_rank: null,
    size: 1,
    metrics: {
      total_return: totalReturn,
      annual_volatility: annualVolatility,
      beta: null,
      max_drawdown: -0.03,
      relative_return: null,
      latest_price: 100,
      observation_count: 21
    },
    source_provider: "mock",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "test",
    transformation_note: null,
    freshness_label: "mocked",
    warnings: []
  };
}

function makeStrategyLabResult() {
  return {
    name: "CSV Strategy",
    value_kind: "return",
    benchmark_column: null,
    benchmark_value_kind: "return",
    metrics: {
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
    },
    returns_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0.01 }],
    equity_curve_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 1.01 }],
    drawdown_points: [{ timestamp: "2026-03-01T00:00:00Z", value: 0 }],
    benchmark_points: [],
    benchmark_equity_curve_points: [],
    rolling_points: [],
    monthly_returns: [{ period: "2026-03", value: 0.01 }],
    annual_returns: [{ period: "2026", value: 0.01 }],
    warnings: [],
    source_provider: "uploaded_csv",
    retrieved_at: "2026-03-01T00:00:00Z",
    origin: "research_service.strategy_lab.analyze",
    transformation_note: "CSV rows parsed as returns.",
    freshness_label: "derived"
  };
}
