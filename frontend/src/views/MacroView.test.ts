import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MacroEventsResponse, MacroSnapshot } from "../lib/api/types";
import { macroContext } from "../lib/stores/app";
import MacroView from "./MacroView.svelte";

describe("MacroView", () => {
  beforeEach(() => {
    macroContext.set({
      mode: "snapshot",
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparisonRegion: null
    });
  });

  it("renders macro warnings and visible scope limits inline, including the compare lens", () => {
    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot(),
        divergences: null,
        events: makeEvents(),
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Macro V1 is US-first. Global mode is intentionally lighter than the US view.");
    expect(body).toContain("Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.");
    expect(body).toContain("Comparison targets are not applied analytically in Macro V1; the comparison selection was ignored.");
    expect(body).toContain(">Compare<");
    expect(body).toContain("disabled");
  });

  it("renders linked expectations in the cross-asset mode", () => {
    macroContext.set({
      mode: "cross_asset",
      region: "US",
      timeframe: "3M",
      theme: "policy",
      comparisonRegion: null
    });

    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot(),
        divergences: null,
        events: makeEvents(),
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Prediction markets versus traditional markets");
    expect(body).toContain("Rates proxies versus policy-cut pricing");
    expect(body).toContain("Will the Fed cut rates by June?");
    expect(body).toContain("aligned");
  });
});

function makeSnapshot(): MacroSnapshot {
  return {
    region: "Global",
    timeframe: "6M",
    theme: "inflation",
    comparison_region: null,
    available_regions: ["US", "EU", "Global"],
    available_timeframes: ["1M", "3M", "6M", "1Y"],
    available_themes: ["all", "growth", "inflation", "policy", "recession_risk"],
    snapshot_cards: [],
    rates_policy: null,
    cross_asset: [],
    linked_expectations: [
      {
        expectation_id: "us:policy:linked-expectation",
        theme: "policy",
        region: "US",
        headline: "Rates proxies versus policy-cut pricing",
        summary: "Macro proxies lean tighter policy while linked prediction markets lean easier policy.",
        agreement_label: "aligned",
        macro_signal_score: 0.72,
        macro_signal_display: "+0.72",
        market_signal_score: 0.51,
        market_signal_display: "+0.51",
        market_probability: 0.68,
        market_probability_display: "68%",
        score_gap: 0.21,
        score_gap_display: "+0.21",
        lead_label: "Prediction markets leading",
        lead_summary: "Prediction-market repricing is moving faster than the macro proxy set.",
        linked_markets: [
          {
            market_id: "polymarket:fed-cut-june",
            venue: "polymarket",
            title: "Will the Fed cut rates by June?",
            event_title: "Fed policy outlook",
            probability: 0.68,
            probability_display: "68%",
            recent_price_change: 0.05,
            recent_price_change_display: "+5.0 pp",
            research_score: 92,
            resolution_date: "2026-06-30T00:00:00Z",
            note: "Rate-cut odds are inverted so higher cut probabilities read as easier policy.",
            source_provider: "polymarket",
            retrieved_at: "2026-03-20T10:00:00Z",
            origin: "polymarket.seed",
            transformation_note: "Seed linked market."
          }
        ],
        source_provider: "macro+prediction_markets",
        retrieved_at: "2026-03-20T10:00:00Z",
        origin: "macro_service.linked_expectations",
        transformation_note: "Linked expectations combine macro and prediction-market signals."
      }
    ],
    top_divergences: [],
    upcoming_events: [],
    warnings: [
      "Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.",
      "Comparison targets are not applied analytically in Macro V1; the comparison selection was ignored."
    ],
    source_provider: "macro+prediction_markets",
    retrieved_at: "2026-03-20T11:00:00Z",
    origin: "macro_service.snapshot",
    transformation_note: "Snapshot combines normalized macro sources and linked prediction-market expectations."
  };
}

function makeEvents(): MacroEventsResponse {
  return {
    region: "Global",
    events: []
  };
}
