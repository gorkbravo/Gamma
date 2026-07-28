import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_CALIBRATION_LEAD_TIMES,
  MAX_COMPARE_LEGS,
  MAX_WATCHLIST_ENTRIES,
  PREDICTION_COMPARE_STORAGE_KEY,
  PREDICTION_MIGRATION_FLAG_KEY,
  PREDICTION_WATCHLIST_STORAGE_KEY,
  buildCalibrationRows,
  buildOutcomeLadder,
  calibrationCurveFor,
  describeCalibrationMethod,
  describeHistoryCoverage,
  formatResolution,
  markLegacyResearchMigrated,
  normalizeCompareSelection,
  normalizeWatchlist,
  readLegacyResearch,
  sortPairsByDislocation,
  toggleCalibrationLeadTime,
  toggleCompareSelection
} from "./prediction-markets";
import type {
  PredictionCalibrationCurve,
  PredictionCalibrationSummary,
  PredictionMarket,
  PredictionOutcomeSeries,
  PredictionPairAnalytics,
  PredictionProbabilityHistoryResponse
} from "./api/types";

function makeMarket(marketId: string, probability = 0.42): PredictionMarket {
  return {
    market_id: marketId,
    venue: "polymarket",
    title: `Market ${marketId}`,
    subtitle: null,
    description: null,
    status: "open",
    category: "Economy",
    event_id: null,
    event_title: null,
    series_id: null,
    series_title: null,
    provider_market_id: marketId,
    provider_condition_id: null,
    provider_event_id: null,
    provider_series_id: null,
    slug: null,
    end_time: null,
    open_time: null,
    close_time: null,
    current_probability: probability,
    probability_label: "Yes",
    volume: null,
    volume_24h: null,
    liquidity: null,
    open_interest: null,
    best_bid: null,
    best_ask: null,
    spread: null,
    recent_price_change: null,
    resolved_probability: null,
    resolution_outcome: null,
    image_url: null,
    resolution_source: null,
    outcomes: [],
    tags: [],
    freshness: null,
    research_score: null,
    research_rationale: null,
    source_provider: "polymarket",
    retrieved_at: null,
    origin: "test",
    transformation_note: null
  };
}

function makeOutcome(outcomeId: string, label: string, values: number[]): PredictionOutcomeSeries {
  return {
    outcome_id: outcomeId,
    label,
    probability: values.length ? values[values.length - 1] : null,
    token_id: `${outcomeId}-token`,
    points: values.map((probability, index) => ({
      timestamp: new Date(Date.UTC(2026, 2, 10, index)).toISOString(),
      probability,
      volume: null,
      open_interest: null,
      bid: null,
      ask: null,
      spread: null,
      source_provider: "polymarket",
      retrieved_at: null,
      origin: "test",
      transformation_note: null
    })),
    warnings: []
  };
}

function makePair(left: string, right: string, currentSpread: number | null): PredictionPairAnalytics {
  return {
    left_market_id: left,
    right_market_id: right,
    overlap_points: 10,
    overlap_start: null,
    overlap_end: null,
    current_spread: currentSpread,
    mean_spread: null,
    max_spread: null,
    min_spread: null,
    spread_volatility: null,
    current_spread_percentile: null,
    correlation: null,
    spread_series: [],
    warnings: []
  };
}

const localValues = new Map<string, string>();

function stubLocalStorage() {
  vi.unstubAllGlobals();
  localValues.clear();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => localValues.get(key) ?? null,
    setItem: (key: string, value: string) => localValues.set(key, value),
    removeItem: (key: string) => localValues.delete(key)
  });
}

describe("legacy watchlist normalization", () => {
  beforeEach(stubLocalStorage);

  it("keeps at most the capped number of entries", () => {
    const entries = normalizeWatchlist(
      Array.from({ length: MAX_WATCHLIST_ENTRIES + 5 }, (_, index) => ({
        market_id: `polymarket:${index}`,
        venue: "polymarket",
        title: `Market ${index}`,
        probability: 0.5,
        added_at: "2026-03-01T00:00:00Z"
      }))
    );

    expect(entries).toHaveLength(MAX_WATCHLIST_ENTRIES);
  });

  it("drops malformed persisted records instead of throwing", () => {
    expect(normalizeWatchlist("not-an-array")).toEqual([]);
    expect(normalizeWatchlist([{ venue: "polymarket" }, null, 4])).toEqual([]);
  });

  it("deduplicates repeated market ids", () => {
    const entries = normalizeWatchlist([
      { market_id: "polymarket:a", venue: "polymarket", title: "A", probability: 0.5, added_at: "2026-03-01" },
      { market_id: "polymarket:a", venue: "polymarket", title: "A dup", probability: 0.6, added_at: "2026-03-02" }
    ]);

    expect(entries).toHaveLength(1);
    expect(entries[0].title).toBe("A");
  });
});

describe("comparison basket", () => {
  beforeEach(stubLocalStorage);

  it("adds and removes contracts", () => {
    let selection = toggleCompareSelection([], "polymarket:a");
    selection = toggleCompareSelection(selection, "kalshi:b");
    expect(selection).toEqual(["polymarket:a", "kalshi:b"]);

    selection = toggleCompareSelection(selection, "polymarket:a");
    expect(selection).toEqual(["kalshi:b"]);
  });

  it("refuses to exceed the leg cap and returns the same list so callers can explain it", () => {
    const full = Array.from({ length: MAX_COMPARE_LEGS }, (_, index) => `polymarket:${index}`);
    const result = toggleCompareSelection(full, "polymarket:extra");

    expect(result).toBe(full);
  });

  it("normalizes persisted junk", () => {
    expect(normalizeCompareSelection([1, "", "polymarket:a", "polymarket:a"])).toEqual(["polymarket:a"]);
    expect(normalizeCompareSelection(null)).toEqual([]);
  });
});

describe("history presentation", () => {
  it("formats bar widths in the largest sensible unit", () => {
    expect(formatResolution(null)).toBe("auto");
    expect(formatResolution(5)).toBe("5m");
    expect(formatResolution(60)).toBe("1h");
    expect(formatResolution(360)).toBe("6h");
    expect(formatResolution(1440)).toBe("1d");
  });

  it("describes coverage so a short series reads as coverage, not breakage", () => {
    const history = {
      points: [{}, {}, {}],
      effective_resolution_minutes: 60,
      stats: { span_days: 4.2 }
    } as unknown as PredictionProbabilityHistoryResponse;

    expect(describeHistoryCoverage(history)).toBe("3 pts | 4.2d | 1h bars");
  });

  it("reports intraday spans in hours", () => {
    const history = {
      points: [{}, {}],
      effective_resolution_minutes: 5,
      stats: { span_days: 0.25 }
    } as unknown as PredictionProbabilityHistoryResponse;

    expect(describeHistoryCoverage(history)).toBe("2 pts | 6h | 5m bars");
  });

  it("handles a missing history", () => {
    expect(describeHistoryCoverage(null)).toBe("No history");
  });
});

describe("outcome ladder", () => {
  it("ranks outcomes by probability and reports window change", () => {
    const ladder = buildOutcomeLadder([
      makeOutcome("no", "No", [0.6, 0.45]),
      makeOutcome("yes", "Yes", [0.4, 0.55])
    ]);

    expect(ladder.map((row) => row.label)).toEqual(["Yes", "No"]);
    expect(ladder[0].change).toBeCloseTo(0.15);
    expect(ladder[1].change).toBeCloseTo(-0.15);
    expect(ladder[0].hasHistory).toBe(true);
  });

  it("keeps outcomes that have no chartable series", () => {
    const ladder = buildOutcomeLadder([makeOutcome("yes", "Yes", [])]);

    expect(ladder[0].hasHistory).toBe(false);
    expect(ladder[0].points).toBe(0);
    expect(ladder[0].change).toBeNull();
  });
});

describe("pair ranking", () => {
  it("puts the widest absolute dislocation first and unknowns last", () => {
    const ranked = sortPairsByDislocation([
      makePair("a", "b", 0.02),
      makePair("c", "d", null),
      makePair("e", "f", -0.11)
    ]);

    expect(ranked.map((pair) => pair.left_market_id)).toEqual(["e", "a", "c"]);
  });

  it("does not mutate the input", () => {
    const pairs = [makePair("a", "b", 0.01), makePair("c", "d", 0.5)];
    sortPairsByDislocation(pairs);

    expect(pairs[0].left_market_id).toBe("a");
  });
});

function makeCurve(
  leadHours: number,
  options: { sample?: number; plottable?: boolean; buckets?: { label: string; n: number; predicted: number; realized: number; meets: boolean }[] } = {}
): PredictionCalibrationCurve {
  return {
    lead_time_hours: leadHours,
    label: leadHours % 24 === 0 ? `T-${leadHours / 24}d` : `T-${leadHours}h`,
    sample_size: options.sample ?? 24,
    buckets: (options.buckets ?? []).map((bucket) => ({
      label: bucket.label,
      sample_size: bucket.n,
      average_probability: bucket.predicted,
      realized_frequency: bucket.realized,
      lead_time_hours: leadHours,
      meets_minimum: bucket.meets,
      source_provider: "polymarket",
      retrieved_at: null,
      origin: "prediction_market_service.calibration.polymarket",
      transformation_note: null
    })),
    brier_score: 0.2,
    mean_signed_error: 0.05,
    is_plottable: options.plottable ?? true,
    warnings: []
  };
}

function makeCalibration(
  curves: PredictionCalibrationCurve[],
  overrides: Partial<PredictionCalibrationSummary> = {}
): PredictionCalibrationSummary {
  return {
    venue: "polymarket",
    sample_size: curves.reduce((total, curve) => total + curve.sample_size, 0),
    method: "lead_time_history",
    is_validated: curves.some((curve) => curve.is_plottable),
    lead_times_hours: curves.map((curve) => curve.lead_time_hours),
    curves,
    minimum_bucket_sample: 5,
    minimum_curve_sample: 20,
    resolved_markets_considered: 60,
    markets_sampled: 40,
    markets_without_history: 4,
    sample_period_start: "2026-01-01T00:00:00Z",
    sample_period_end: "2026-06-01T00:00:00Z",
    sample_categories: { Politics: 12 },
    research_share: 1,
    convergence: null,
    observations: [],
    warnings: [],
    source_provider: "polymarket",
    retrieved_at: "2026-06-01T00:00:00Z",
    origin: "prediction_market_service.calibration.polymarket",
    transformation_note: "Lead-time sampled.",
    ...overrides
  };
}

describe("calibration lead times", () => {
  it("keeps at least one lead time selected", () => {
    expect(toggleCalibrationLeadTime([24], 24)).toEqual([24]);
  });

  it("adds a lead time in ascending order and caps the count", () => {
    expect(toggleCalibrationLeadTime([168], 24)).toEqual([24, 168]);
    const full = [6, 24, 72].slice(0, MAX_CALIBRATION_LEAD_TIMES);
    expect(toggleCalibrationLeadTime(full, 168)).toBe(full);
  });

  it("removes a lead time when more than one is selected", () => {
    expect(toggleCalibrationLeadTime([24, 168], 24)).toEqual([168]);
  });
});

describe("calibration rows", () => {
  it("computes realized-minus-priced error per bucket", () => {
    const rows = buildCalibrationRows(
      makeCurve(24, {
        buckets: [{ label: "50-75%", n: 8, predicted: 0.6, realized: 0.75, meets: true }]
      })
    );

    expect(rows[0].error).toBeCloseTo(0.15);
    expect(rows[0].meets_minimum).toBe(true);
  });

  it("returns nothing when there is no curve", () => {
    expect(buildCalibrationRows(null)).toEqual([]);
  });

  it("selects the requested lead time and falls back to a drawn curve", () => {
    const summary = makeCalibration([makeCurve(24), makeCurve(168)]);

    expect(calibrationCurveFor(summary, 168)?.lead_time_hours).toBe(168);
    expect(calibrationCurveFor(summary, 999)?.lead_time_hours).toBe(24);
    expect(calibrationCurveFor(null, 24)).toBeNull();
  });

  it("prefers a curve that cleared the minimum when nothing is selected", () => {
    const summary = makeCalibration([makeCurve(24, { plottable: false }), makeCurve(168, { plottable: true })]);

    expect(calibrationCurveFor(summary, null)?.lead_time_hours).toBe(168);
  });

  it("still shows a withheld curve when no curve cleared the minimum", () => {
    const summary = makeCalibration([makeCurve(24, { plottable: false }), makeCurve(168, { plottable: false })]);

    expect(calibrationCurveFor(summary, null)?.lead_time_hours).toBe(24);
  });
});

describe("calibration method label", () => {
  it("names the measured method and how many curves cleared the minimum", () => {
    const summary = makeCalibration([makeCurve(24), makeCurve(168, { plottable: false })]);

    const label = describeCalibrationMethod(summary);
    expect(label).toContain("Lead-time history");
    expect(label).toContain("T-1d / T-7d");
    expect(label).toContain("1/2 above minimum");
  });

  it("marks the deprecated settlement path as unvalidated", () => {
    const summary = makeCalibration([], {
      method: "settlement_last_trade_deprecated",
      is_validated: false
    });

    expect(describeCalibrationMethod(summary)).toContain("UNVALIDATED");
  });
});

describe("legacy research migration", () => {
  beforeEach(stubLocalStorage);

  it("reads local records once and then reports nothing to migrate", () => {
    // Written the way a previous build wrote them, not through a helper the
    // migration itself owns.
    localStorage.setItem(
      PREDICTION_WATCHLIST_STORAGE_KEY,
      JSON.stringify([
        { market_id: "polymarket:a", venue: "polymarket", title: "A", probability: 0.4, added_at: "2026-03-01" }
      ])
    );
    localStorage.setItem(PREDICTION_COMPARE_STORAGE_KEY, JSON.stringify(["polymarket:a", "kalshi:b"]));

    const legacy = readLegacyResearch();
    expect(legacy?.watchlist.map((entry) => entry.market_id)).toEqual(["polymarket:a"]);
    expect(legacy?.comparison_basket).toEqual(["polymarket:a", "kalshi:b"]);

    markLegacyResearchMigrated();
    expect(readLegacyResearch()).toBeNull();
  });

  it("marks an empty browser as migrated so it never re-checks", () => {
    expect(readLegacyResearch()).toBeNull();
    expect(localStorage.getItem(PREDICTION_MIGRATION_FLAG_KEY)).toBeTruthy();
  });
});
