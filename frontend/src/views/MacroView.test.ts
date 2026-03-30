import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MacroDivergenceListResponse, MacroEventsResponse, MacroSnapshot } from "../lib/api/types";
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

  it("renders three FX selectors with distinct default presets in snapshot mode", () => {
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

    expect(body.match(/fx-select/g)?.length ?? 0).toBe(3);
    expect(body).toContain('option value="eurusd"');
    expect(body).toContain('option value="gbpusd"');
    expect(body).toContain('option value="usdjpy"');
  });

  it("renders linked prediction-market context inside macro cards", () => {
    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot({
          snapshot_cards: [
            {
              card_id: "inflation",
              title: "Inflation Context",
              subtitle: null,
              summary: "Inflation context compares CPI with breakevens.",
              mode_target: "cross_asset",
              target_theme: "inflation",
              metrics: [],
              linked_markets: [
                {
                  market_id: "polymarket:inflation",
                  venue: "polymarket",
                  title: "Will CPI print above 3% in June?",
                  status: "open",
                  category: "Economy",
                  end_time: "2026-06-10T00:00:00Z",
                  current_probability: 0.62,
                  probability_label: "62%",
                  recent_price_change: 0.04,
                  change_display: "+4.0 pts",
                  research_score: 87.5,
                  macro_alignment: "aligned",
                  macro_alignment_summary: "Gamma maps this contract as inflation-up; Macro inflation proxies are firming.",
                  source_provider: "polymarket",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.linked_prediction_markets",
                  transformation_note: "Linked prediction context.",
                }
              ],
              source_provider: "fred",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.snapshot_cards",
              transformation_note: "Snapshot cards summarize macro conditions."
            }
          ]
        }),
        divergences: null,
        events: makeEvents(),
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Will CPI print above 3% in June?");
    expect(body).toContain("aligned");
  });

  it("renders divergence drivers and research focus in cross-asset mode", () => {
    macroContext.set({
      mode: "cross_asset",
      region: "US",
      timeframe: "3M",
      theme: "inflation",
      comparisonRegion: null
    });

    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot({
          region: "US",
          timeframe: "3M",
          theme: "inflation",
          cross_asset: [
            {
              theme: "inflation",
              headline: "Inflation signals",
              summary: "Breakevens are driving the inflation read while the dollar is the clearest counter-signal.",
              agreement_label: "high",
              metrics: [],
              linked_markets: [],
              primary_driver: {
                role: "driver",
                tone: "reinforcing",
                signal_score: 1.8,
                signal_score_display: "+1.80",
                interpretation: "US 5Y Breakeven Inflation is the lead driver. Its +0.22 pp move points to firmer inflation pressure.",
                metric: makeMetric("us-5y-breakeven", "US 5Y Breakeven Inflation"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.divergence_signal",
                transformation_note: "Signal annotation."
              },
              counter_signal: {
                role: "counter",
                tone: "opposing",
                signal_score: -0.9,
                signal_score_display: "-0.90",
                interpretation: "Broad Dollar Index is the clearest counter-signal. Its -1.20 move points to cooling inflation pressure.",
                metric: makeMetric("us-dollar-broad", "Broad Dollar Index"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.divergence_signal",
                transformation_note: "Signal annotation."
              },
              divergence_score: 2.7,
              research_focus: "Test whether breakevens or the dollar is more likely to reset first.",
              source_provider: "fred",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.cross_asset",
              transformation_note: "Cross-asset comparison.",
              comparison_region: null,
              comparison_summary: null
            }
          ]
        }),
        divergences: makeDivergences(),
        events: makeEvents(),
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Lead driver");
    expect(body).toContain("Counter-signal");
    expect(body).toContain("Test whether breakevens or the dollar is more likely to reset first.");
  });
});

function makeSnapshot(overrides: Partial<MacroSnapshot> = {}): MacroSnapshot {
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
    top_divergences: [],
    upcoming_events: [],
    warnings: [
      "Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.",
      "Comparison targets are not applied analytically in Macro V1; the comparison selection was ignored."
    ],
    source_provider: "fred",
    retrieved_at: "2026-03-20T11:00:00Z",
    origin: "macro_service.snapshot",
    transformation_note: "Snapshot combines normalized macro sources.",
    ...overrides
  };
}

function makeEvents(): MacroEventsResponse {
  return {
    region: "Global",
    events: []
  };
}

function makeDivergences(): MacroDivergenceListResponse {
  return {
    region: "US",
    timeframe: "3M",
    theme: "inflation",
    comparison_region: null,
    divergences: []
  };
}

function makeMetric(seriesId: string, label: string) {
  return {
    metric_id: seriesId,
    label,
    value: null,
    display_value: null,
    unit: null,
    delta_value: null,
    delta_display: null,
    series_id: seriesId,
    source_provider: "fred",
    retrieved_at: "2026-03-20T11:00:00Z",
    origin: "macro_service.metric",
    transformation_note: null,
    comparison_region: null,
    comparison_label: null,
    comparison_value: null,
    comparison_display_value: null,
    comparison_delta_value: null,
    comparison_delta_display: null,
    gap_value: null,
    gap_display: null
  };
}
