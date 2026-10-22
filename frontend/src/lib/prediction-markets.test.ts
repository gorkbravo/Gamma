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
  eventBookLadderSummary,
  flatScreenerEntries,
  formatResolution,
  groupRelatedMarkets,
  groupScreenerMarkets,
  markLegacyResearchMigrated,
  parseBucketBounds,
  type PredictionScreenerEntry,
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
  PredictionEventBook,
  PredictionEventBookLeg,
  PredictionMarket,
  PredictionOutcomeSeries,
  PredictionPairAnalytics,
  PredictionProbabilityHistoryResponse,
  RelatedPredictionMarket
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

// GUA-20261021-15: agrupación de buckets por evento y secciones de RELATED.
const WEEK = "October 19-October 25";

function bucketLeg(id: string, label: string, wording: string, probability: number, overrides: Partial<PredictionMarket> = {}) {
  return {
    ...makeMarket(`polymarket:${id}`, probability),
    title: `Will ${wording} ships transit the Strait of Hormuz between ${WEEK}?`,
    subtitle: label,
    event_id: "polymarket:event:wk-1019",
    event_title: "How many ships transit the Strait of Hormuz week of October 19?",
    end_time: "2026-10-26T00:00:00Z",
    volume_24h: 1000,
    liquidity: 500,
    freshness: { status: "fresh", is_stale: false, is_broken: false, reason: null, last_history_point_at: null, retrieval_age_seconds: 1, history_lag_seconds: null },
    ...overrides
  } satisfies PredictionMarket;
}

function weeklyBook(): PredictionMarket[] {
  // Orden de ranking del screener, no de bucket.
  return [
    bucketLeg("25", "25-29", "25-29", 0.35),
    bucketLeg("40", "40+", "40 or more", 0.03),
    bucketLeg("lt20", "<20", "fewer than 20", 0.08),
    bucketLeg("30", "30-34", "30-34", 0.22),
    bucketLeg("20", "20-24", "20-24", 0.27, {
      freshness: { status: "stale", is_stale: true, is_broken: false, reason: "old", last_history_point_at: null, retrieval_age_seconds: 1, history_lag_seconds: null }
    }),
    bucketLeg("35", "35-39", "35-39", 0.08)
  ];
}

function groupOf(entries: PredictionScreenerEntry[]) {
  const entry = entries.find((item) => item.type === "group");
  if (!entry || entry.type !== "group") throw new Error("expected a group entry");
  return entry.group;
}

describe("parseBucketBounds", () => {
  it("reads ranges, open-ended buckets and units, and ignores date-only titles", () => {
    expect(parseBucketBounds("20-24")).toEqual([20, 24]);
    expect(parseBucketBounds("<20")).toEqual([-Infinity, 20]);
    expect(parseBucketBounds("40+")).toEqual([40, Infinity]);
    expect(parseBucketBounds("Will fewer than 20 ships transit the Strait of Hormuz between October 19-October 25?")).toEqual([
      -Infinity,
      20
    ]);
    expect(parseBucketBounds("between 0 and 5 average daily transits on October 31")).toEqual([0, 5]);
    expect(parseBucketBounds("70° to 71°")).toEqual([70, 71]);
    expect(parseBucketBounds("72° or above")).toEqual([72, Infinity]);
    expect(parseBucketBounds("Strait of Hormuz traffic returns to normal by October 31?")).toBeNull();
  });

  it("reads Polymarket hit-level arrows as one-sided thresholds", () => {
    expect(parseBucketBounds("↑ 95,000")).toEqual([95000, Infinity]);
    expect(parseBucketBounds("↓ 60,000")).toEqual([-Infinity, 60000]);
  });
});

describe("eventBookLadderSummary", () => {
  function bookLeg(id: string, subtitle: string, probability: number | null): PredictionEventBookLeg {
    return {
      market_id: id, venue: "polymarket", title: `Putin out as President of Russia by ${subtitle}?`, subtitle,
      outcome_label: "Yes", probability, best_bid: null, best_ask: null, spread: null, volume: null, liquidity: null,
      open_interest: null, status: "open", end_time: null, resolution_source: null, is_anchor: false,
      divergence_flags: [], ladder_flags: []
    };
  }

  function book(overrides: Partial<PredictionEventBook>): PredictionEventBook {
    return {
      venue: "polymarket", anchor_market_id: "polymarket:dec26", event_id: "polymarket:event:putin",
      event_title: "Putin out as President of Russia by...?", provider_event_id: "putin", legs: [],
      probability_sum: null, implied_overround: null, favorite_market_id: null, exclusivity_signal: "unverified",
      overround_is_meaningful: false, ladder_kind: null, ladder_inversions: 0, completeness: null, warnings: [],
      source_provider: "polymarket", retrieved_at: null, origin: "test", transformation_note: null, ...overrides
    };
  }

  it("summarises a date ladder from its first to its last priced rung", () => {
    const summary = eventBookLadderSummary(book({
      exclusivity_signal: "cumulative_ladder", ladder_kind: "date", ladder_inversions: 1,
      legs: [bookLeg("sep26", "September 30, 2026", 0), bookLeg("dec26", "December 31, 2026", 0.02),
        bookLeg("mar27", "March 31, 2027", null), bookLeg("jun27", "June 30, 2027", 0.095)]
    }));
    expect(summary?.label).toBe("Date ladder");
    expect(summary?.rule).toBe("later ≥ earlier");
    expect(summary?.inversions).toBe(1);
    expect(summary?.first?.market_id).toBe("sep26");
    // El último peldaño sin precio no cuenta como extremo del rango.
    expect(summary?.last?.market_id).toBe("jun27");
  });

  it("labels threshold ladders and leaves exclusive books to the sum check", () => {
    const threshold = eventBookLadderSummary(book({
      exclusivity_signal: "cumulative_ladder", ladder_kind: "threshold", legs: [bookLeg("a", "72,000", 0.9)]
    }));
    expect(threshold?.label).toBe("Threshold ladder");
    expect(eventBookLadderSummary(book({ exclusivity_signal: "venue_grouped_candidates", overround_is_meaningful: true }))).toBeNull();
    expect(eventBookLadderSummary(null)).toBeNull();
  });
});

describe("groupScreenerMarkets", () => {
  it("collapses one event's buckets into a distribution with sum, mode and overround", () => {
    const loose = makeMarket("kalshi:solo", 0.4);
    const entries = groupScreenerMarkets([loose, ...weeklyBook()]);

    expect(entries.map((entry) => entry.type)).toEqual(["market", "group"]);
    const group = groupOf(entries);
    expect(group.eventTitle).toBe("How many ships transit the Strait of Hormuz week of October 19?");
    expect(group.kind).toBe("buckets");
    expect(group.coverage).toBe("complete");
    expect(group.legs.map((leg) => leg.label)).toEqual(["<20", "20-24", "25-29", "30-34", "35-39", "40+"]);
    expect(group.probabilitySum).toBeCloseTo(1.03, 6);
    expect(group.overround).toBeCloseTo(0.03, 6);
    expect(group.mode?.label).toBe("25-29");
    expect(group.legs.filter((leg) => leg.isMode)).toHaveLength(1);
    expect(group.legs.find((leg) => leg.label === "25-29")?.share).toBe(1);
    expect(group.volume24h).toBe(6000);
    expect(group.liquidity).toBe(3000);
    // La freshness del grupo es la peor de sus legs, no la del primero.
    expect(group.worstFreshness).toBe("stale");
  });

  it("keeps the group at the position of its best-ranked leg", () => {
    const [first, ...rest] = weeklyBook();
    const entries = groupScreenerMarkets([makeMarket("kalshi:a"), first, makeMarket("kalshi:b"), ...rest]);
    expect(entries.map((entry) => entry.key)).toEqual(["kalshi:a", "polymarket|polymarket:event:wk-1019", "kalshi:b"]);
  });

  it("does not call the sum an overround when a bucket is missing from the view", () => {
    const partial = weeklyBook().filter((market) => market.subtitle !== "30-34");
    const group = groupOf(groupScreenerMarkets(partial));
    expect(group.kind).toBe("buckets");
    expect(group.coverage).toBe("partial");
    expect(group.overround).toBeNull();
    expect(group.probabilitySum).toBeCloseTo(0.81, 6);
  });

  it("treats a dated ladder inside one event as descriptive, ordered by resolution", () => {
    const ladder = [
      { ...makeMarket("polymarket:dec", 0.11), title: "Hormuz normal by December 31?", subtitle: "December 31", event_id: "polymarket:event:e-1", end_time: "2026-12-31T00:00:00Z" },
      { ...makeMarket("polymarket:oct", 0.007), title: "Hormuz normal by October 31?", subtitle: "October 31", event_id: "polymarket:event:e-1", end_time: "2026-10-31T00:00:00Z" },
      { ...makeMarket("polymarket:nov", 0.05), title: "Hormuz normal by November 30?", subtitle: "November 30", event_id: "polymarket:event:e-1", end_time: "2026-11-30T00:00:00Z" }
    ];
    const group = groupOf(groupScreenerMarkets(ladder));
    expect(group.kind).toBe("unverified");
    expect(group.overround).toBeNull();
    expect(group.legs.map((leg) => leg.market.market_id)).toEqual(["polymarket:oct", "polymarket:nov", "polymarket:dec"]);
  });

  it("does not treat a cumulative threshold ladder as exclusive buckets", () => {
    const thresholds = [
      { ...makeMarket("kalshi:a3", 0.6), subtitle: "Above 3%", event_id: "kalshi:event:cpi" },
      { ...makeMarket("kalshi:a35", 0.3), subtitle: "Above 3.5%", event_id: "kalshi:event:cpi" }
    ];
    const group = groupOf(groupScreenerMarkets(thresholds));
    expect(group.kind).toBe("unverified");
    expect(group.overround).toBeNull();
  });

  it("does not read hit levels with one resolution date as a candidate race", () => {
    const end = "2026-12-31T23:59:00Z";
    const levels = [
      { ...makeMarket("polymarket:hit85", 0.45), subtitle: "↑ 85,000", event_id: "polymarket:event:btc", end_time: end },
      { ...makeMarket("polymarket:hit95", 0.2), subtitle: "↑ 95,000", event_id: "polymarket:event:btc", end_time: end },
      { ...makeMarket("polymarket:dip60", 0.3), subtitle: "↓ 60,000", event_id: "polymarket:event:btc", end_time: end }
    ];
    const group = groupOf(groupScreenerMarkets(levels));
    expect(group.kind).toBe("unverified");
    expect(group.overround).toBeNull();
  });

  it("leaves the flat list untouched", () => {
    const markets = weeklyBook();
    expect(flatScreenerEntries(markets).map((entry) => entry.key)).toEqual(markets.map((market) => market.market_id));
  });
});

describe("groupRelatedMarkets", () => {
  function relatedRow(marketId: string, overrides: Partial<RelatedPredictionMarket> = {}): RelatedPredictionMarket {
    return {
      market_id: marketId,
      venue: "polymarket",
      title: marketId,
      probability: 0.1,
      price_gap: 0.01,
      relationship: "cross_venue_analog",
      note: null,
      source_provider: "polymarket",
      retrieved_at: null,
      origin: "test",
      transformation_note: null,
      ...overrides
    };
  }

  it("splits analogs from event and series siblings and orders siblings by their rank", () => {
    const sections = groupRelatedMarkets([
      relatedRow("kalshi:analog", { venue: "kalshi" }),
      relatedRow("polymarket:nov", { relationship: "same_series", sibling_scope: "same_series", sibling_order: 1, group_title: "Hormuz Traffic Returns to Normal" }),
      relatedRow("polymarket:b40", { relationship: "adjacent_threshold", sibling_scope: "same_event", sibling_order: 2, group_title: "Week of Oct 19" }),
      relatedRow("polymarket:oct", { relationship: "same_series", sibling_scope: "same_series", sibling_order: 0, group_title: "Hormuz Traffic Returns to Normal" }),
      relatedRow("polymarket:b20", { relationship: "adjacent_threshold", sibling_scope: "same_event", sibling_order: 0, group_title: "Week of Oct 19" })
    ]);

    expect(sections.map((section) => section.id)).toEqual(["analog", "same_event", "same_series"]);
    expect(sections[1].rows.map((row) => row.market_id)).toEqual(["polymarket:b20", "polymarket:b40"]);
    expect(sections[2].rows.map((row) => row.market_id)).toEqual(["polymarket:oct", "polymarket:nov"]);
    expect(sections[2].groupTitle).toBe("Hormuz Traffic Returns to Normal");
  });

  it("drops empty sections so a sibling-only contract still lists its links", () => {
    const sections = groupRelatedMarkets([
      relatedRow("polymarket:oct", { relationship: "same_series", sibling_scope: "same_series", sibling_order: 0 })
    ]);
    expect(sections.map((section) => section.id)).toEqual(["same_series"]);
    expect(groupRelatedMarkets([])).toEqual([]);
  });
});
