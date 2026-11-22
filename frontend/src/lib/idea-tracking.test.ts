import { describe, expect, it } from "vitest";
import type { IdeaTrackingResponse, IdeaTrackingSegment } from "./api/types";
import {
  TRACKING_LABEL,
  boardTrackingCell,
  changedCosts,
  costDraftError,
  formatCostDrag,
  formatTrackingReturn,
  formatWeightShare,
  returnTone,
  segmentLegsText,
  segmentPeriodText,
  sessionTime,
  trackingChartData,
  trackingMetaText,
} from "./idea-tracking";

function segment(overrides: Partial<IdeaTrackingSegment> = {}): IdeaTrackingSegment {
  return {
    segment_id: "seg-1",
    number: 1,
    status: "tracking",
    reason: null,
    started_at: "2026-11-09T14:00:00",
    start_reason: "activated",
    start_note: "Activated",
    ended_at: null,
    end_reason: null,
    stance: "relative",
    entry_session: "2026-11-09",
    exit_session: null,
    last_session: "2026-11-13",
    sessions: 5,
    gaps: 0,
    gross_return: 0.02,
    net_return: 0.019,
    entry_cost: 0.0005,
    exit_cost: 0.0005,
    cost: 0.001,
    benchmark_return: 0.03,
    excess_return: -0.011,
    max_drawdown: -0.004,
    legs: [
      {
        key: "equity:AAPL",
        label: "AAPL",
        entity_type: "equity",
        normalized_id: "AAPL",
        stated_weight: 1,
        weight: 0.5,
        weight_source: "stated",
        asset_class: "us_equity_liquid",
        detected_class: "us_equity_liquid",
        cost_bp: 5,
        market: "us",
        entry_price: 200,
        last_price: 210,
      },
      {
        key: "equity:MSFT",
        label: "MSFT",
        entity_type: "equity",
        normalized_id: "MSFT",
        stated_weight: -1,
        weight: -0.5,
        weight_source: "stated",
        asset_class: "us_equity_liquid",
        detected_class: "us_equity_liquid",
        cost_bp: 5,
        market: "us",
        entry_price: 400,
        last_price: 380,
      },
    ],
    ...overrides,
  };
}

function response(overrides: Partial<IdeaTrackingResponse> = {}): IdeaTrackingResponse {
  return {
    idea_id: "i1",
    label: TRACKING_LABEL,
    status: "tracking",
    status_reason: null,
    methodology: "Hypothetical, not executed.",
    summary: {
      net_return: 0.019,
      gross_return: 0.02,
      cost_drag: 0.001,
      benchmark_return: 0.03,
      excess_return: -0.011,
      max_drawdown: -0.004,
      sessions: 4,
      gaps: 1,
      partial: false,
      first_session: "2026-11-09",
      as_of: "2026-11-13",
    },
    benchmark: { symbol: "SPY", available: true, reason: null },
    cost_model: { classes: [], leg_classes: {}, updated_at: null, edited: false },
    segments: [segment()],
    points: [
      { session: "2026-11-09", segment: 1, net_return: -0.001, gross_return: 0, benchmark_return: 0, drawdown: 0, gap: false, missing: [] },
      { session: "2026-11-10", segment: 1, net_return: null, gross_return: null, benchmark_return: 0.01, drawdown: null, gap: true, missing: ["MSFT"] },
      { session: "2026-11-11", segment: 2, net_return: 0.019, gross_return: 0.02, benchmark_return: null, drawdown: 0, gap: false, missing: [] },
    ],
    warnings: [],
    provenance: [],
    computed_at: "2026-11-14T12:00:00",
    source_provider: "gamma_ideas",
    origin: "idea_tracking.compute",
    transformation_note: null,
    ...overrides,
  };
}

describe("idea tracking formatting", () => {
  it("formats returns with their sign and keeps absence visible", () => {
    expect(formatTrackingReturn(0.0235)).toBe("+2.35%");
    expect(formatTrackingReturn(-0.0101)).toBe("-1.01%");
    expect(formatTrackingReturn(0.00001)).toBe("0.00%");
    expect(formatTrackingReturn(null)).toBe("N/A");
    expect(formatTrackingReturn(Number.NaN)).toBe("N/A");
    expect(formatCostDrag(0.001)).toBe("-0.10%");
    expect(returnTone(0.02)).toBe("positive");
    expect(returnTone(-0.02)).toBe("negative");
    expect(returnTone(0.00001)).toBe("");
    expect(formatWeightShare(-0.5)).toBe("-50%");
    expect(formatWeightShare(null)).toBe("No weight");
  });

  it("describes segments by their entry and exit closes", () => {
    expect(segmentPeriodText(segment())).toBe("2026-11-09 → open");
    expect(segmentPeriodText(segment({ status: "closed", exit_session: "2026-11-11" }))).toBe("2026-11-09 → 2026-11-11");
    expect(segmentPeriodText(segment({ status: "waiting", entry_session: null }))).toBe("Waiting");
    expect(segmentPeriodText(segment({ status: "untracked", entry_session: null }))).toBe("Not tracked");
    expect(segmentLegsText(segment())).toBe("AAPL +50% · MSFT -50%");
    const unpriced = segment({ status: "untracked", legs: segment().legs.map((leg) => ({ ...leg, weight: null })) });
    expect(segmentLegsText(unpriced)).toBe("AAPL +1 · MSFT -1");
  });

  it("summarises sessions, gaps and the last close", () => {
    expect(trackingMetaText(response())).toBe("4 sessions · 1 gap · as of 2026-11-13");
    expect(trackingMetaText(response({ status: "waiting", summary: { ...response().summary, sessions: 0 } }))).toBe(
      "Waiting for the first close"
    );
  });
});

describe("tracking chart data", () => {
  it("turns a gap into a break, never a value, and marks each segment entry", () => {
    const twoSegments = response({
      segments: [
        segment({ status: "closed", exit_session: "2026-11-11" }),
        segment({ segment_id: "seg-2", number: 2, entry_session: "2026-11-11", sessions: 3 }),
      ],
    });
    const data = trackingChartData(twoSegments);
    expect(data.net.map((point) => point.time)).toEqual(["2026-11-09", "2026-11-10", "2026-11-11"].map(sessionTime));
    expect(Number.isNaN(data.net[1].value)).toBe(true);
    expect(data.net[2].value).toBeCloseTo(1.9);
    expect(Number.isNaN(data.benchmark[2].value)).toBe(true);
    expect(data.markers.map((marker) => marker.text)).toEqual(["S1", "S2"]);
    // Un solo segmento no necesita marcador.
    expect(trackingChartData(response()).markers).toEqual([]);
    expect(sessionTime("2026-11-09")).toBe(Date.UTC(2026, 10, 9) / 1000);
  });

  it("drops a benchmark with no values at all", () => {
    const noBenchmark = response({
      points: response().points.map((point) => ({ ...point, benchmark_return: null })),
    });
    expect(trackingChartData(noBenchmark).benchmark).toEqual([]);
    expect(trackingChartData(null)).toEqual({ net: [], benchmark: [], markers: [] });
  });
});

const responseFor = () => response();

describe("board tracking cell", () => {
  const headline = {
    label: TRACKING_LABEL,
    segments: 2,
    open: true,
    started_at: "2026-11-09T14:00:00",
    snapshot: {
      status: "tracking" as const,
      computed_at: "2026-11-14T12:00:00",
      as_of: "2026-11-13",
      net_return: 0.0123,
      gross_return: 0.014,
      benchmark_return: 0.03,
      benchmark: "SPY",
      sessions: 5,
      gaps: 1,
      partial: false,
    },
  };

  it("shows the hypothetical net return with its session and gaps", () => {
    const cell = boardTrackingCell({ tracking: headline });
    expect(cell.text).toBe("+1.23%");
    expect(cell.tone).toBe("positive");
    expect(cell.meta).toBe("as of 2026-11-13 · 1 gap");
    expect(cell.title).toContain(TRACKING_LABEL);
    expect(cell.title).toContain("SPY +3.00%");
  });

  it("says when the provider stopped instead of showing the figure as current", () => {
    const stale = { ...headline, snapshot: { ...headline.snapshot, stale_since: "2026-11-11" } };
    expect(boardTrackingCell({ tracking: stale }).meta).toBe("as of 2026-11-13 · provider stopped · 1 gap");
    const response = {
      ...responseFor(),
      summary: { ...responseFor().summary, stale_since: "2026-11-11" },
    };
    expect(trackingMetaText(response)).toBe("4 sessions · 1 gap · as of 2026-11-13 · no close since 2026-11-11");
  });

  it("keeps not tracked, not computed and waiting apart", () => {
    expect(boardTrackingCell({ tracking: null })).toMatchObject({ text: "Not tracked", absent: true });
    expect(boardTrackingCell({ tracking: { ...headline, snapshot: null } })).toMatchObject({ text: "Not computed", absent: true });
    const waiting = { ...headline, snapshot: { ...headline.snapshot, status: "waiting" as const, net_return: null, as_of: null } };
    expect(boardTrackingCell({ tracking: waiting })).toMatchObject({ text: "Waiting for the first close", absent: true });
    const stopped = { ...headline, open: false, snapshot: { ...headline.snapshot, status: "stopped" as const, net_return: -0.02 } };
    expect(boardTrackingCell({ tracking: stopped })).toMatchObject({ text: "-2.00%", tone: "negative" });
    expect(boardTrackingCell({ tracking: stopped }).meta).toContain("stopped");
  });
});

describe("cost assumptions", () => {
  const classes = [
    { asset_class: "us_equity_liquid" as const, label: "Liquid", basis: "", per_side_bp: 5, default_bp: 5, editable: true, source: "stated" as const, edited: false },
    { asset_class: "crypto_spot" as const, label: "Crypto", basis: "", per_side_bp: 50, default_bp: 50, editable: true, source: "stated" as const, edited: false },
    { asset_class: "options" as const, label: "Options", basis: "", per_side_bp: null, default_bp: null, editable: false, source: "quote" as const, edited: false },
  ];

  it("sends only the classes that changed", () => {
    expect(changedCosts(classes, { us_equity_liquid: "5", crypto_spot: "40" })).toEqual({ crypto_spot: 40 });
    expect(changedCosts(classes, { us_equity_liquid: "5", crypto_spot: "50" })).toBeNull();
  });

  it("refuses empty, negative or out-of-range values", () => {
    expect(costDraftError({ us_equity_liquid: "5" })).toBe("");
    expect(costDraftError({ us_equity_liquid: "" })).toContain("Enter a cost");
    expect(costDraftError({ us_equity_liquid: "-1" })).toBe("Costs are 0 to 500 bp per side.");
    expect(costDraftError({ us_equity_liquid: "abc" })).toBe("Costs are 0 to 500 bp per side.");
    expect(costDraftError({ us_equity_liquid: "501" })).toBe("Costs are 0 to 500 bp per side.");
  });
});
