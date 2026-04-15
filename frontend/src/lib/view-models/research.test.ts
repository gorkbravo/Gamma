import { describe, expect, it } from "vitest";
import type { ResearchResult } from "../api/types";
import {
  buildResearchCompareOptions,
  buildResearchTreemapLayout,
  buildResearchTreemapSections,
  buildPreviewRows,
  deriveConstituentsFromResearchResult,
  deriveCoverageFromResearchResult,
  deriveStructureFromWeights,
  doesResearchDraftMatchResult,
  formatResearchOverviewMetricValue,
  formatResearchOverviewSortValue,
  normalizeSyntheticText,
  parseResearchCsvText,
  parseSyntheticText
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
});

function makeResearchResult(
  scopeType: "single_ticker" | "synthetic_portfolio",
  weights: Array<{ symbol: string; weight: number }>
): ResearchResult {
  return {
    scope_type: scopeType,
    benchmark_symbol: "SPY",
    primary_symbol: scopeType === "single_ticker" ? weights[0]?.symbol ?? null : null,
    observations_count: 10,
    snapshot: null,
    performance_points: [],
    benchmark_points: [],
    primary_price_points: [],
    weights,
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
    constituents: weights.map((item) => ({
      symbol: item.symbol,
      weight: item.weight,
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
      benchmark_observation_count: 0
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
    freshness_label: "mocked"
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
