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

  it("renders coverage note and visible scope limits inline, including the compare lens", () => {
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

    expect(body).toContain("Global is a light V1 comparative lens. Some analytics reuse US-first coverage.");
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

  it("renders snapshot focus items and drilldown targets", () => {
    const { body } = render(MacroView, {
      props: {
        snapshot: makeSnapshot({
          focus_items: [
            {
              focus_id: "top-divergence",
              title: "Biggest disagreement",
              summary: "Breakevens and the dollar are still disagreeing on the inflation read.",
              why_now: "Gamma's lead-lag heuristic shows breakevens moved first and the dollar still has not cleanly confirmed.",
              mode_target: "cross_asset",
              target_theme: "inflation",
              signal_label: "coherent",
              source_provider: "fred",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.snapshot_focus",
              transformation_note: "Snapshot focus."
            }
          ],
          snapshot_cards: [
            {
              card_id: "inflation",
              title: "Inflation Context",
              subtitle: null,
              summary: "Inflation context compares CPI with breakevens.",
              why_now: "Recent catalyst: CPI Release. Breakevens moved first while the dollar lagged.",
              mode_target: "cross_asset",
              target_theme: "inflation",
              signal_label: "coherent",
              drilldown_label: "Open Cross-Asset (inflation)",
              metrics: [],
              linked_markets: [],
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

    expect(body).toContain("What Matters Now");
    expect(body).toContain("coherent");
    expect(body).toContain("Open Cross-Asset (inflation)");
  });

  it("renders linked prediction-market hints inside macro cards", () => {
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

    expect(body).toContain("1 linked market");
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
              coherence: {
                theme: "inflation",
                direction_label: "firming inflation",
                coherence_label: "coherent",
                supporting_signals: 3,
                opposing_signals: 1,
                neutral_signals: 0,
                lead_signal: {
                  label: "US 5Y Breakeven Inflation",
                  series_id: "us-5y-breakeven",
                  role: "leader",
                  tone: "reinforcing",
                  signal_score: 1.8,
                  signal_score_display: "+1.80",
                  move_value: 0.22,
                  move_display: "+0.22 pp",
                  observed_at: "2026-03-04T00:00:00Z",
                  observed_label: "2026-03-04",
                  lag_days: 0,
                  lag_label: "at window start",
                  source_provider: "fred",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.lead_lag",
                  transformation_note: "Lead-lag heuristic."
                },
                lag_signal: {
                  label: "Broad Dollar Index",
                  series_id: "us-dollar-broad",
                  role: "laggard",
                  tone: "opposing",
                  signal_score: -0.9,
                  signal_score_display: "-0.90",
                  move_value: -1.2,
                  move_display: "-1.20",
                  observed_at: "2026-03-18T00:00:00Z",
                  observed_label: "2026-03-18",
                  lag_days: 14,
                  lag_label: "14d from window start",
                  source_provider: "fred",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.lead_lag",
                  transformation_note: "Lead-lag heuristic."
                },
                lag_span_days: 14,
                lag_span_display: "14d",
                summary: "US 5Y Breakeven Inflation moved first on the current firming inflation read; Broad Dollar Index only aligned roughly 14d later.",
                methodology: "Lead-lag is a first-pass heuristic.",
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.coherence",
                transformation_note: "Lead-lag heuristic."
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
    expect(body).toContain("3 confirm");
    expect(body).toContain("1 oppose");
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
            linked_markets: [
              {
                market_id: "kalshi:fed-cut",
                venue: "kalshi",
                title: "Will the Fed cut by September?",
                status: "open",
                category: "Economy",
                end_time: "2026-09-18T00:00:00Z",
                current_probability: 0.58,
                probability_label: "58%",
                recent_price_change: 0.03,
                change_display: "+3.0 pts",
                research_score: 76.2,
                macro_stance: "policy-easier",
                macro_alignment: "mixed",
                macro_alignment_summary: "Contracts lean easier than the hold proxy but the overall linked set is mixed.",
                source_provider: "kalshi",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.linked_prediction_markets",
                transformation_note: "Linked prediction context."
              }
            ],
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
            expectation_metrics: [
              {
                ...makeMetric("policy-linked-bias", "Market bias"),
                value: -1,
                display_value: "Easier",
                unit: null,
                delta_value: null,
                delta_display: null,
                series_id: null
              }
            ],
            expectation_summary: "Linked policy contracts skew easier while the front-end path proxy is still close to hold. Use the contract set as a challenge case rather than as an implied curve.",
            expectation_caveat: "Prediction-market contracts are mapped by text and topic rather than by exact policy-meeting payoff.",
            meeting_path: {
              headline: "Next 3 meetings keep policy near 4.35% if the hold proxy persists.",
              summary: "The ladder spreads the current 2Y Treasury versus Fed Funds gap evenly across the next 3 scheduled policy meetings.",
              window_label: "Next 3 policy meetings",
              metrics: [
                {
                  ...makeMetric("meeting-count", "Meetings"),
                  value: 3,
                  display_value: "3",
                  unit: null,
                  delta_value: null,
                  delta_display: null,
                  series_id: null
                },
                {
                  ...makeMetric("avg-move", "Avg / meeting"),
                  value: -5,
                  display_value: "-5 bps",
                  unit: "bps",
                  delta_value: null,
                  delta_display: null,
                  series_id: null
                }
              ],
              meetings: [
                {
                  meeting_id: "fomc:2026-04-29",
                  title: "FOMC Meeting (April 29-30)",
                  scheduled_at: "2026-04-29T00:00:00Z",
                  meeting_index: 1,
                  implied_policy_rate: 4.45,
                  implied_policy_rate_display: "4.45%",
                  incremental_change_bps: -5,
                  incremental_change_display: "-5 bps",
                  cumulative_change_bps: -5,
                  cumulative_change_display: "-5 bps",
                  source_provider: "treasury",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.policy_meeting_path",
                  transformation_note: "Meeting ladder proxy."
                }
              ],
              research_focus: "Focus on what would break the hold ladder first: 2Y Treasury, Fed Funds, or linked policy contracts.",
              source_provider: "treasury",
              retrieved_at: "2026-03-20T11:00:00Z",
              origin: "macro_service.policy_meeting_path",
              transformation_note: "Meeting ladder proxy."
            },
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
    expect(body).toContain("Expectation Overlay");
    expect(body).toContain("Linked policy contracts skew easier");
    expect(body).toContain("Easier");
    expect(body).toContain("Meeting Ladder");
    expect(body).toContain("Next 3 policy meetings");
    expect(body).toContain("FOMC Meeting (April 29-30)");
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
              window_start: "2026-03-01T00:00:00Z",
              window_end: "2026-03-19T00:00:00Z",
              window_start_label: "2026-03-01",
              window_end_label: "2026-03-19",
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
                observed_at: "2026-03-12T00:00:00Z",
                observed_label: "2026-03-12",
                lag_days: 0,
                lag_label: "same-day follow-through",
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
                observed_at: "2026-03-14T00:00:00Z",
                observed_label: "2026-03-14",
                lag_days: 2,
                lag_label: "2d after event",
                interpretation: "After CPI Release, Broad Dollar Index moved -1.4 and points to cooling inflation pressure.",
                metric: makeMetric("us-dollar-broad", "Broad Dollar Index"),
                source_provider: "fred",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.event_reaction_signal",
                transformation_note: "Event reaction."
              },
              coherence: {
                theme: "inflation",
                direction_label: "firming inflation",
                coherence_label: "narrow",
                supporting_signals: 2,
                opposing_signals: 1,
                neutral_signals: 0,
                lead_signal: {
                  label: "US 5Y Breakeven Inflation",
                  series_id: "us-5y-breakeven",
                  role: "leader",
                  tone: "reinforcing",
                  signal_score: 1.2,
                  signal_score_display: "+1.20",
                  move_value: 0.18,
                  move_display: "+0.18 pp",
                  observed_at: "2026-03-12T00:00:00Z",
                  observed_label: "2026-03-12",
                  lag_days: 0,
                  lag_label: "same-day follow-through",
                  source_provider: "fred",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.lead_lag",
                  transformation_note: "Lead-lag heuristic."
                },
                lag_signal: {
                  label: "Broad Dollar Index",
                  series_id: "us-dollar-broad",
                  role: "laggard",
                  tone: "opposing",
                  signal_score: -0.7,
                  signal_score_display: "-0.70",
                  move_value: -1.4,
                  move_display: "-1.4",
                  observed_at: "2026-03-14T00:00:00Z",
                  observed_label: "2026-03-14",
                  lag_days: 2,
                  lag_label: "2d after event",
                  source_provider: "fred",
                  retrieved_at: "2026-03-20T11:00:00Z",
                  origin: "macro_service.lead_lag",
                  transformation_note: "Lead-lag heuristic."
                },
                lag_span_days: 2,
                lag_span_display: "2d",
                summary: "US 5Y Breakeven Inflation reacted first after CPI Release; Broad Dollar Index only confirmed roughly 2d later.",
                methodology: "Event lead-lag is a first-pass heuristic.",
                source_provider: "bls",
                retrieved_at: "2026-03-20T11:00:00Z",
                origin: "macro_service.event_coherence",
                transformation_note: "Lead-lag heuristic."
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
    expect(body).toContain("2 confirm");
    expect(body).toContain("1 oppose");
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
