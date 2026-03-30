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
    expect(body).toContain("Comparison is currently available only for direct US-versus-EU views. The requested comparison target was ignored.");
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

  it("renders the policy path proxy in rates and policy mode", () => {
    macroContext.set({
      mode: "rates_policy",
      region: "US",
      timeframe: "3M",
      theme: "policy",
      comparisonRegion: null
    });

    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot({
          rates_policy: {
            headline: "Front-end policy pricing remains the cleanest read on US macro conditions.",
            summary: "Rates & Policy emphasizes the current Treasury curve, front-end policy context, and the real-yield versus breakeven split.",
            policy_metrics: [],
            curve_nodes: [],
            real_yield_metrics: [],
            events: [],
            linked_markets: [],
            path_headline: "2Y Treasury is within 15 bps of Fed Funds; hold remains the cleanest path proxy.",
            path_summary: "This is a front-end path proxy rather than a full meeting curve: compare the 2Y, Fed Funds, and the active curve slope to judge whether easing or tightening is actually being priced.",
            path_metrics: [
              {
                ...makeMetric("us-fed-funds", "Fed Funds"),
                value: 4.5,
                display_value: "4.50%",
                unit: "pct",
                delta_value: -0.2,
                delta_display: "-0.20 pp"
              },
              {
                ...makeMetric("us-2y-yield", "2Y Treasury"),
                value: 4.35,
                display_value: "4.35%",
                unit: "pct",
                delta_value: -0.35,
                delta_display: "-0.35 pp"
              },
              {
                ...makeMetric("path-gap", "2Y Treasury minus Fed Funds"),
                value: -15,
                display_value: "-15 bps",
                unit: "bps",
                delta_value: -12,
                delta_display: "-12 bps",
                series_id: null
              }
            ],
            path_research_focus: "Watch whether 2Y Treasury breaks away from Fed Funds before the next policy event.",
            market_alignment_label: "mixed",
            market_alignment_summary: "Linked policy contracts are mixed relative to the rates-path proxy.",
            source_provider: "treasury",
            retrieved_at: "2026-03-20T11:00:00Z",
            origin: "macro_service.rates_policy",
            transformation_note: "Rates and policy summary.",
            comparison_region: null,
            comparison_summary: null
          }
        }),
        divergences: makeDivergences(),
        events: makeEvents(),
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Path Proxy");
    expect(body).toContain("hold remains the cleanest path proxy");
    expect(body).toContain("2Y Treasury minus Fed Funds");
    expect(body).toContain("Linked policy contracts are mixed relative to the rates-path proxy.");
  });

  it("renders event studies and regime framing in events/regimes mode", () => {
    macroContext.set({
      mode: "events_regimes",
      region: "US",
      timeframe: "3M",
      theme: "all",
      comparisonRegion: null
    });

    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot({
          top_divergences: [
            {
              divergence_id: "us:inflation:divergence",
              theme: "inflation",
              region: "US",
              headline: "Inflation divergence score 2.70",
              summary: "Breakevens are leading while the dollar is the clearest counter-signal.",
              score: 2.7,
              label: "high",
              metrics: [],
              series_ids: ["us-5y-breakeven", "us-dollar-broad"],
              primary_driver: {
                role: "driver",
                tone: "reinforcing",
                signal_score: 1.8,
                signal_score_display: "+1.80",
                interpretation: "US 5Y Breakeven Inflation is the lead driver.",
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
                interpretation: "Broad Dollar Index is the clearest counter-signal.",
                metric: makeMetric("us-dollar-broad", "Broad Dollar Index"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.divergence_signal",
                transformation_note: "Signal annotation."
              },
              research_focus: "Test whether breakevens or the dollar resets first.",
              source_provider: "fred",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.divergences",
              transformation_note: "Divergence score.",
              comparison_region: null,
              comparison_score: null,
              score_gap: null,
              score_gap_display: null
            }
          ],
          event_studies: [
            {
              study_id: "bls:cpi_release:2026-03-12:inflation",
              theme: "inflation",
              timing: "recent",
              headline: "CPI Release: how inflation proxies absorbed the release",
              summary: "After the event, breakevens absorbed the clearest inflation move while the dollar pushed the other way.",
              window_label: "Post-event window",
              event: {
                event_id: "bls:cpi_release:2026-03-12",
                title: "CPI Release",
                category: "inflation",
                region: "US",
                scheduled_at: "2026-03-12T00:00:00Z",
                relative_label: "February 2026",
                importance: "medium",
                source_provider: "bls",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro.events.bls_schedule",
                transformation_note: "Official calendar event."
              },
              reactions: [],
              primary_reaction: {
                role: "lead",
                tone: "reinforcing",
                signal_score: 1.2,
                signal_score_display: "+1.20",
                move_value: 0.18,
                move_display: "+0.18 pp",
                before_display_value: "2.22%",
                after_display_value: "2.40%",
                interpretation: "After CPI Release, US 5Y Breakeven Inflation moved +0.18 pp and points to firmer inflation pressure.",
                metric: makeMetric("us-5y-breakeven", "US 5Y Breakeven Inflation"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.event_reaction_signal",
                transformation_note: "Event reaction."
              },
              counter_reaction: {
                role: "counter",
                tone: "opposing",
                signal_score: -0.7,
                signal_score_display: "-0.70",
                move_value: -1.4,
                move_display: "-1.4",
                before_display_value: "121.5",
                after_display_value: "120.1",
                interpretation: "After CPI Release, Broad Dollar Index moved -1.4 and points to cooling inflation pressure.",
                metric: makeMetric("us-dollar-broad", "Broad Dollar Index"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.event_reaction_signal",
                transformation_note: "Event reaction."
              },
              linked_markets: [],
              research_focus: "Test whether the post-event move broadens into the rest of the inflation complex.",
              source_provider: "bls",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.event_studies",
              transformation_note: "Event study."
            }
          ]
        }),
        divergences: makeDivergences(),
        events: {
          region: "US",
          events: [
            {
              event_id: "fomc:2026-04-29",
              title: "FOMC Meeting",
              category: "policy",
              region: "US",
              scheduled_at: "2026-04-29T00:00:00Z",
              relative_label: null,
              importance: "high",
              source_provider: "federalreserve",
              retrieved_at: "2026-03-20T10:00:00Z",
              origin: "macro.events.fomc_calendar",
              transformation_note: "Official calendar event."
            }
          ]
        },
        histories: {},
        loading: false,
        onLoadWorkspace: vi.fn(),
        onLoadSeries: vi.fn()
      }
    });

    expect(body).toContain("Regime Framing");
    expect(body).toContain("Post-event absorption");
    expect(body).toContain("CPI Release");
    expect(body).toContain("Lead reaction");
    expect(body).toContain("Scheduled catalysts");
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
    event_studies: [],
    upcoming_events: [],
    warnings: [
      "Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.",
      "Comparison is currently available only for direct US-versus-EU views. The requested comparison target was ignored."
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
