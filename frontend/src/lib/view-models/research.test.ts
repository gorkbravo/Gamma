import { describe, expect, it } from "vitest";
import type { ResearchResult } from "../api/types";
import {
  buildPreviewRows,
  deriveConstituentsFromResearchResult,
  deriveCoverageFromResearchResult,
  deriveStructureFromWeights,
  doesResearchDraftMatchResult,
  normalizeSyntheticText,
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
