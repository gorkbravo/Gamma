import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { MacroMetric, MacroSnapshot, ResearchOverviewResponse } from "../lib/api/types";
import SitrepView from "./SitrepView.svelte";

describe("SitrepView", () => {
  it("labels index moves as latest-day returns and shows the proxy/as-of pivot", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: makeGlobalIndicesOverview(),
        news: null,
        macro: null,
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
      },
    });

    expect(body).toContain("Latest Day");
    expect(body).toContain("Latest Day %");
    expect(body).toContain("Proxy / As Of");
    expect(body).toContain("EWJ / Jun 26");
    expect(body).toContain("-4.2%");
  });

  it("labels FX and rates change columns with the macro window", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: null,
        news: null,
        macro: makeMacroSnapshot(),
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
      },
    });

    expect(body).toContain("CHG (3M)");
    expect(body).toContain("%CHG (3M)");
    expect(body).toContain("Move (3M)");
    expect(body).toContain("CHG (1D)");
    expect(body).toContain("%CHG (1D)");
  });

  it("renders macro events in the Events & Markets panel with a follow-up affordance", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: null,
        news: null,
        macro: makeMacroSnapshot(),
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
      },
    });

    expect(body).toContain("Events &amp; Markets");
    expect(body).toContain("CPI release");
    expect(body).toContain("Save as follow-up");
    expect(body).toContain("Follow-Ups");
    expect(body).toContain("NO SAVED FOLLOW-UPS — STAR A TRIAGE ROW TO TRACK IT.");
    // Panel captions restating the column/source structure were cut.
    expect(body).not.toContain("macro focus / calendar / prediction markets / commodities");
    expect(body).not.toContain("star triage rows to save them");
  });

  it("groups per-domain source, freshness, and as-of in Provider Status", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: makeGlobalIndicesOverview(),
        news: null,
        macro: makeMacroSnapshot(),
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
      },
    });

    expect(body).toContain("Domain");
    expect(body).toContain("Indices");
    expect(body).toContain("HISTORICAL");
    expect(body).toContain("FX / Rates");
    expect(body).toContain("3M WINDOW");
    expect(body).toContain("Predictions");
    expect(body).toContain("NOT LOADED");
    expect(body).toContain("OLDEST INDICES");
    // The column headers carry the structure the caption used to spell out.
    expect(body).not.toContain("source / freshness / as of / age");
  });

  it("renders backend follow-ups with notes, resolved state, and triage actions", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: null,
        news: null,
        macro: null,
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
        followUps: [
          {
            id: "uuid-open",
            row_id: "evt-cpi",
            source: "Event",
            tone: "warning",
            title: "CPI release",
            detail: "Inflation / US",
            meta: "in 3d",
            note: "Watch the 2s10s reaction",
            status: "open" as const,
            handoff: { targetTab: "macro" as const, targetMode: "events_regimes" },
            saved_at: "2026-07-12T00:00:00Z",
          },
          {
            id: "uuid-resolved",
            row_id: "divergence-1",
            source: "Macro",
            tone: "neutral",
            title: "Rates vs equities divergence",
            detail: "score 2.4",
            meta: "high",
            note: "",
            status: "resolved" as const,
            handoff: null,
            saved_at: "2026-07-10T00:00:00Z",
            resolved_at: "2026-07-13T00:00:00Z",
          },
        ],
      },
    });

    expect(body).toContain("1 open / 1 resolved");
    expect(body).toContain("Watch the 2s10s reaction");
    expect(body).toContain("RESOLVED");
    expect(body).toContain("Mark follow-up resolved");
    expect(body).toContain("Reopen follow-up");
    expect(body).toContain("Add follow-up note");
    expect(body).toContain("Edit follow-up note");
    expect(body).toContain("Dismiss follow-up");
  });

  it("renders clickable news ticker chips and keeps per-item provenance off the row", () => {
    const { body } = render(SitrepView, {
      props: {
        overview: null,
        indicesOverview: null,
        macro: null,
        commodities: null,
        prediction: null,
        loading: false,
        onLoadNews: vi.fn(),
        onLoadOverview: vi.fn(),
        onLoadIndicesOverview: vi.fn(),
        onLoadMacro: vi.fn(),
        onLoadCommodities: vi.fn(),
        onLoadPrediction: vi.fn(),
        onOpenHandoff: vi.fn(),
        news: {
          items: [{
            normalized_id: "rss:test:1",
            provider_item_id: "1",
            title: "Apple expands AI investment",
            summary: null,
            url: "https://example.com/apple",
            source_provider: "rss",
            source_name: "Test Outlet",
            source_domain: "example.com",
            published_at: "2026-07-13T11:30:00Z",
            retrieved_at: "2026-07-13T11:35:00Z",
            origin: "rss.feed:test",
            detected_entities: [{ label: "Apple", entity_type: "company", symbol: "AAPL", normalized_id: null, metadata: {} }],
            tags: ["equities"],
            freshness_label: "delayed",
            source_reliability: "major_outlet",
            warnings: [],
            transformation_note: null,
          }],
          source_provider: "rss",
          retrieved_at: "2026-07-13T11:35:00Z",
          origin: "news_service.latest",
          freshness_label: "delayed",
          warnings: [],
          transformation_note: null,
        }
      },
    });

    expect(body).toContain("Open Apple in Equity Research");
    expect(body).toContain("AAPL");
    expect(body).toContain('class="news-source');
    // RSS stamps every headline identically, so the per-row freshness/reliability
    // badge carried no signal; it moved into the source link's tooltip and the
    // feed-level state is stated once, in Provider Status.
    expect(body).not.toContain("provenance-badge");
    expect(body).not.toContain("OUTLET");
    expect(body.match(/>DELAYED</g) ?? []).toHaveLength(1);
  });
});

function makeMacroMetric(overrides: Partial<MacroMetric>): MacroMetric {
  return {
    metric_id: "metric",
    label: "Metric",
    value: null,
    display_value: null,
    unit: null,
    delta_value: null,
    delta_display: null,
    series_id: null,
    source_provider: "fred",
    retrieved_at: "2026-07-12T18:00:00Z",
    origin: "test",
    transformation_note: null,
    comparison_region: null,
    comparison_label: null,
    comparison_value: null,
    comparison_display_value: null,
    comparison_delta_value: null,
    comparison_delta_display: null,
    gap_value: null,
    gap_display: null,
    ...overrides,
  };
}

function makeMacroSnapshot(): MacroSnapshot {
  return {
    region: "US",
    timeframe: "3M",
    theme: "all",
    comparison_region: null,
    available_regions: ["US"],
    available_timeframes: ["3M"],
    available_themes: ["all"],
    focus_items: [],
    snapshot_cards: [
      {
        card_id: "fx-card",
        title: "FX",
        subtitle: null,
        summary: "FX context",
        mode_target: "snapshot",
        target_theme: null,
        metrics: [
          makeMacroMetric({
            metric_id: "fx-eurusd",
            label: "EUR/USD",
            series_id: "fx-eurusd",
            value: 1.141,
            display_value: "1.141",
            delta_value: 0.012,
            delta_display: "+0.012",
            source_provider: "ibkr",
          }),
        ],
        linked_markets: [],
        source_provider: "fred",
        retrieved_at: "2026-07-12T18:00:00Z",
        origin: "test",
        transformation_note: null,
      },
    ],
    rates_policy: {
      headline: "Rates",
      summary: "Curve context",
      policy_metrics: [],
      curve_nodes: [
        {
          tenor: "2Y",
          current_value: 4.13,
          prior_value: 3.78,
          change_bps: 35,
          source_provider: "treasury",
          retrieved_at: "2026-07-12T18:00:00Z",
          origin: "test",
          transformation_note: null,
        },
      ],
      real_yield_metrics: [],
      events: [],
      linked_markets: [],
      path_headline: null,
      path_summary: null,
      path_metrics: [],
      path_research_focus: null,
      meeting_path: null,
      market_alignment_label: null,
      market_alignment_summary: null,
      source_provider: "treasury",
      retrieved_at: "2026-07-12T18:00:00Z",
      origin: "test",
      transformation_note: null,
      comparison_region: null,
      comparison_summary: null,
    },
    cross_asset: [],
    top_divergences: [],
    event_studies: [],
    upcoming_events: [
      {
        event_id: "evt-cpi",
        title: "CPI release",
        category: "inflation",
        region: "US",
        scheduled_at: "2026-07-15T12:30:00Z",
        relative_label: "in 3d",
        importance: "high",
        source_provider: "sample",
        retrieved_at: "2026-07-12T18:00:00Z",
        origin: "test",
        transformation_note: null,
      },
    ],
    warnings: [],
    source_provider: "fred",
    retrieved_at: "2026-07-12T18:00:00Z",
    origin: "test",
    transformation_note: null,
  };
}

function makeGlobalIndicesOverview(): ResearchOverviewResponse {
  return {
    universe_id: "global_indices",
    universe_label: "Global Indices",
    universe_description: "Curated cash-index board.",
    timeframe: "DoD",
    lookback_days: 1,
    benchmark_symbol: "SPY",
    available_universes: [],
    available_timeframes: ["DoD", "1M"],
    metric_options: [],
    sort_options: [],
    nodes: [
      {
        node_id: "instrument:^N225",
        normalized_id: "index:^N225",
        label: "Nikkei 225",
        level: "instrument",
        parent_id: "group:japan",
        group: "Japan",
        sector: "Japan",
        industry: null,
        symbol: "^N225",
        instrument_id: "index:^N225",
        weight: 1,
        market_cap_usd: null,
        index_weight: null,
        sort_rank: 11,
        size: 1,
        metrics: {
          total_return: -0.04153,
          latest_daily_return: -0.04153,
          latest_daily_return_at: "2026-06-26T00:00:00Z",
          annual_volatility: null,
          beta: null,
          max_drawdown: null,
          relative_return: -0.0343,
          latest_price: 69360.88,
          observation_count: 1,
        },
        source_provider: "yfinance",
        retrieved_at: "2026-06-27T20:20:15Z",
        origin: "research_service.overview.instrument",
        transformation_note: "Computed from daily close history.",
        freshness_label: "historical",
        warnings: [],
      },
    ],
    coverage: {
      instrument_count: 1,
      priced_count: 1,
      missing_symbols: [],
      benchmark_symbol: "SPY",
      benchmark_available: true,
      benchmark_observation_count: 1,
      coverage_ratio: 1,
      missing_count: 0,
      thin_history_symbols: [],
      min_observation_count: 1,
      max_observation_count: 1,
      coverage_label: "Curated global cash-index board",
      history_source_label: "Yahoo Finance/yfinance daily history",
      metadata_source_label: "Curated Gamma global cash-index symbol list",
    },
    rankings: {
      leaders: [],
      laggards: [],
      highest_volatility: [],
      highest_beta: [],
      largest_drawdowns: [],
    },
    summary: {
      leading_group: null,
      lagging_group: null,
      highest_volatility_group: null,
      coverage_note: null,
    },
    warnings: [],
    source_provider: "yfinance",
    retrieved_at: "2026-06-27T20:20:15Z",
    origin: "research_service.overview",
    transformation_note: "Computed from daily close histories.",
    freshness_label: "historical",
    history_source_label: "Yahoo Finance/yfinance daily history",
    metadata_source_label: "Curated Gamma global cash-index symbol list",
    coverage_label: "Curated global cash-index board",
  };
}
