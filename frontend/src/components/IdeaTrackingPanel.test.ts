import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaTrackingResponse } from "../lib/api/types";
import IdeaTrackingPanel from "./IdeaTrackingPanel.svelte";

const IDEA: Idea = {
  schema_version: 3,
  idea_id: "i1",
  title: "AAPL over MSFT",
  thesis: "Apple holds up better.",
  notes: "",
  stance: "relative",
  legs: [
    { entity: { entity_type: "equity", label: "AAPL", normalized_id: "AAPL", provider_id: null, native_id: null, metadata: {} }, weight: 1 },
    { entity: { entity_type: "equity", label: "MSFT", normalized_id: "MSFT", provider_id: null, native_id: null, metadata: {} }, weight: -1 },
  ],
  horizon: { review_date: null, holding_window: null },
  status: "active",
  origin: { kind: "manual", source_ref: null, label: null, handoff: null },
  tags: [],
  created_at: "2026-11-06T12:00:00",
  updated_at: "2026-11-11T15:00:00",
  closed_at: null,
  evidence: [],
  criteria: [],
  journal: [],
  evidence_counts: { supports: 0, challenges: 0, context: 0 },
  criteria_counts: { pending: 0, holding: 0, triggered: 0, unavailable: 0, stale: 0 },
  tracking: {
    label: "Hypothetical, not executed",
    benchmark: "SPY",
    cost_model: { per_side_bp: { us_equity_liquid: 5 }, leg_classes: {}, updated_at: null },
    segments: [
      {
        segment_id: "seg-1",
        number: 1,
        started_at: "2026-11-09T14:00:00",
        start_reason: "activated",
        start_note: "Activated",
        stance: "relative",
        legs: [],
        ended_at: "2026-11-11T15:00:00",
        end_reason: "legs_edited",
        end_note: "",
        untracked_reason: null,
      },
      {
        segment_id: "seg-2",
        number: 2,
        started_at: "2026-11-11T15:00:00",
        start_reason: "legs_edited",
        start_note: "Legs edited",
        stance: "relative",
        legs: [],
        ended_at: null,
        end_reason: null,
        end_note: "",
        untracked_reason: null,
      },
    ],
    snapshot: null,
  },
  provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-14T12:00:00", origin: "idea_store", transformation_note: null },
};

function leg(weight: number) {
  return {
    key: weight > 0 ? "equity:AAPL" : "equity:MSFT",
    label: weight > 0 ? "AAPL" : "MSFT",
    entity_type: "equity",
    normalized_id: weight > 0 ? "AAPL" : "MSFT",
    stated_weight: weight,
    weight: weight / 2,
    weight_source: "stated" as const,
    asset_class: "us_equity_liquid" as const,
    detected_class: "us_equity_liquid" as const,
    cost_bp: 5,
    market: "us",
    entry_price: 100,
    last_price: 101,
  };
}

const TRACKING: IdeaTrackingResponse = {
  idea_id: "i1",
  label: "Hypothetical, not executed",
  status: "tracking",
  status_reason: null,
  methodology: "Hypothetical, not executed. Each segment buys fixed quantities…",
  summary: {
    net_return: 0.0123,
    gross_return: 0.0135,
    cost_drag: 0.0012,
    benchmark_return: 0.03,
    excess_return: -0.0177,
    max_drawdown: -0.004,
    sessions: 4,
    gaps: 1,
    partial: false,
    first_session: "2026-11-09",
    as_of: "2026-11-13",
  },
  benchmark: { symbol: "SPY", available: true, reason: null },
  cost_model: {
    classes: [
      {
        asset_class: "us_equity_liquid",
        label: "Liquid US equities and ETFs",
        basis: "Commission plus half a typical spread.",
        per_side_bp: 5,
        default_bp: 5,
        editable: true,
        source: "stated",
        edited: false,
      },
    ],
    leg_classes: {},
    updated_at: null,
    edited: false,
  },
  segments: [
    {
      segment_id: "seg-1",
      number: 1,
      status: "closed",
      reason: null,
      started_at: "2026-11-09T14:00:00",
      start_reason: "activated",
      start_note: "Activated",
      ended_at: "2026-11-11T15:00:00",
      end_reason: "legs_edited",
      stance: "relative",
      entry_session: "2026-11-09",
      exit_session: "2026-11-11",
      last_session: "2026-11-11",
      sessions: 3,
      gaps: 1,
      gross_return: 0.01,
      net_return: 0.009,
      entry_cost: 0.0005,
      exit_cost: 0.0005,
      cost: 0.001,
      benchmark_return: 0.02,
      excess_return: -0.011,
      max_drawdown: -0.004,
      legs: [leg(1), leg(1)],
    },
    {
      segment_id: "seg-2",
      number: 2,
      status: "tracking",
      reason: null,
      started_at: "2026-11-11T15:00:00",
      start_reason: "legs_edited",
      start_note: "Legs edited",
      ended_at: null,
      end_reason: null,
      stance: "relative",
      entry_session: "2026-11-11",
      exit_session: null,
      last_session: "2026-11-13",
      sessions: 3,
      gaps: 0,
      gross_return: 0.0035,
      net_return: 0.003,
      entry_cost: 0.0005,
      exit_cost: 0.0005,
      cost: 0.001,
      benchmark_return: 0.01,
      excess_return: -0.007,
      max_drawdown: 0,
      legs: [leg(1), leg(-1)],
    },
  ],
  points: [
    { session: "2026-11-09", segment: 1, net_return: -0.001, gross_return: 0, benchmark_return: 0, drawdown: 0, gap: false, missing: [] },
    { session: "2026-11-10", segment: 1, net_return: null, gross_return: null, benchmark_return: 0.01, drawdown: null, gap: true, missing: ["MSFT"] },
    { session: "2026-11-11", segment: 2, net_return: 0.009, gross_return: 0.01, benchmark_return: 0.02, drawdown: 0, gap: false, missing: [] },
  ],
  warnings: ["Segment 1: no close for MSFT on 2026-11-10; the session is a gap, not interpolated."],
  provenance: [
    { key: "equity:AAPL", label: "AAPL", role: "leg", source_provider: "Yahoo Finance", retrieved_at: "2026-11-14T12:00:00", origin: "research_market_data.history", transformation_note: null, available: true },
  ],
  computed_at: "2026-11-14T12:00:00",
  source_provider: "gamma_ideas",
  origin: "idea_tracking.compute",
  transformation_note: null,
};

describe("IdeaTrackingPanel", () => {
  it("labels the record hypothetical and shows costs next to returns", () => {
    const { body } = render(IdeaTrackingPanel, { props: { idea: IDEA, tracking: TRACKING } });
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("Net since activation");
    expect(body).toContain("+1.23%");
    expect(body).toContain("Gross");
    expect(body).toContain("+1.35%");
    expect(body).toContain("-0.12%");
    expect(body).toContain("5 bp per side");
    expect(body).toContain("4 sessions · 1 gap · as of 2026-11-13");
    expect(body).toContain("height:220px");
  });

  it("keeps every segment visible with its closes, legs and reason", () => {
    const { body } = render(IdeaTrackingPanel, { props: { idea: IDEA, tracking: TRACKING } });
    expect(body).toContain("S1");
    expect(body).toContain("S2");
    expect(body).toContain("2026-11-09 → 2026-11-11");
    expect(body).toContain("2026-11-11 → open");
    expect(body).toContain("AAPL +50% · MSFT -50%");
    expect(body).toContain("Legs edited");
    expect(body).toContain("1 gap");
    expect(body).toContain("the session is a gap, not interpolated");
    expect(body).toMatch(/<th class="num">SPY<\/th>/);
  });

  it("says why there is no record yet instead of an empty chart", () => {
    const draft = { ...IDEA, status: "draft" as const, tracking: null };
    const { body } = render(IdeaTrackingPanel, { props: { idea: draft, tracking: null } });
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("Tracking starts at the first close after the idea is activated with legs.");
    expect(body).not.toContain("Net since activation");
  });

  it("holds the chart geometry while the series loads or waits", () => {
    const loading = render(IdeaTrackingPanel, { props: { idea: IDEA, tracking: null, loading: true } }).body;
    expect(loading).toContain("Loading…");
    expect(loading).toContain("height:220px");
    const waiting = render(IdeaTrackingPanel, {
      props: {
        idea: IDEA,
        tracking: {
          ...TRACKING,
          status: "waiting",
          status_reason: "Waiting for the first close after 2026-11-11 15:00 UTC with a price for every leg.",
          points: [],
          summary: { ...TRACKING.summary, sessions: 0, net_return: null },
        },
      },
    }).body;
    expect(waiting).toContain("Waiting for the first close after 2026-11-11 15:00 UTC");
    expect(waiting).toContain("N/A");
  });
});
