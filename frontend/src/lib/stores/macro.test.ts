import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  MacroDivergenceListResponse,
  MacroEventsResponse,
  MacroSeriesHistory,
  MacroSnapshot
} from "../api/types";
import {
  lastError,
  loadMacroSeriesHistory,
  loadMacroWorkspace,
  loading,
  macroContext,
  macroDivergences,
  macroEvents,
  macroSeriesHistories,
  macroSnapshot
} from "./app";

describe("macro store orchestration", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    macroContext.set({
      mode: "snapshot",
      region: "US",
      timeframe: "3M",
      theme: "all",
      comparisonRegion: null
    });
    macroSnapshot.set(null);
    macroDivergences.set(null);
    macroEvents.set(null);
    macroSeriesHistories.set({});
    lastError.set("");
    loading.set({
      status: false,
      diagnostics: false,
      diagnosticsAction: false,
      portfolio: false,
      portfolioAction: false,
      research: false,
      macro: false,
      macroHistory: false,
      prediction: false,
      predictionDetail: false,
      risk: false,
      iv: false,
      ivSession: false
    });
  });

  it("preserves shared macro context when switching modes through workspace loads", async () => {
    const snapshot = makeSnapshot();
    const divergences = makeDivergences();
    const events = makeEvents();
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/macro/snapshot")) {
        return Promise.resolve(ok(snapshot));
      }
      if (url.endsWith("/macro/divergences")) {
        return Promise.resolve(ok(divergences));
      }
      if (url.includes("/macro/events")) {
        return Promise.resolve(ok(events));
      }
      if (url.includes("/macro/series/")) {
        return Promise.resolve(ok(makeHistory()));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    await loadMacroWorkspace({
      region: "Global",
      timeframe: "6M",
      theme: "all",
      comparisonRegion: "US",
      mode: "snapshot"
    });
    await loadMacroWorkspace({ mode: "cross_asset", theme: "inflation" });
    await loadMacroWorkspace({ mode: "rates_policy" });

    expect(get(macroContext)).toEqual({
      mode: "rates_policy",
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparisonRegion: null
    });
    expect(get(macroSnapshot)?.region).toBe("Global");
    expect(get(macroDivergences)?.divergences[0]?.theme).toBe("inflation");
    expect(get(macroEvents)?.events[0]?.region).toBe("Global");

    const snapshotPayloads = snapshotBodies(fetchMock);
    const firstSnapshotPayload = snapshotPayloads[0] ?? {};
    const secondSnapshotPayload = snapshotPayloads[1] ?? {};
    const thirdSnapshotPayload = snapshotPayloads[2] ?? {};
    expect(firstSnapshotPayload).toMatchObject({
      region: "Global",
      timeframe: "6M",
      theme: "all",
      comparison_region: null
    });
    expect(secondSnapshotPayload).toMatchObject({
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparison_region: null
    });
    expect(thirdSnapshotPayload).toMatchObject({
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparison_region: null
    });
  });

  it("preserves a valid US-versus-EU comparison lens across macro mode changes", async () => {
    const snapshot = {
      ...makeSnapshot(),
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparison_region: "US",
      warnings: ["Comparison lens active: EU versus US. Only concepts with curated counterparts are compared directly."]
    };
    const divergences = {
      ...makeDivergences(),
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparison_region: "US"
    };
    const events = {
      ...makeEvents(),
      region: "EU",
      events: []
    };
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/macro/snapshot")) {
        return Promise.resolve(ok(snapshot));
      }
      if (url.endsWith("/macro/divergences")) {
        return Promise.resolve(ok(divergences));
      }
      if (url.includes("/macro/events")) {
        return Promise.resolve(ok(events));
      }
      if (url.includes("/macro/series/")) {
        return Promise.resolve(ok(makeHistory()));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    await loadMacroWorkspace({
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparisonRegion: "US",
      mode: "snapshot"
    });
    await loadMacroWorkspace({ mode: "cross_asset" });

    expect(get(macroContext)).toEqual({
      mode: "cross_asset",
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparisonRegion: "US"
    });

    const snapshotPayloads = snapshotBodies(fetchMock);
    const firstSnapshotPayload = snapshotPayloads[0] ?? {};
    const secondSnapshotPayload = snapshotPayloads[1] ?? {};
    expect(firstSnapshotPayload).toMatchObject({
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparison_region: "US"
    });
    expect(secondSnapshotPayload).toMatchObject({
      region: "EU",
      timeframe: "1Y",
      theme: "policy",
      comparison_region: "US"
    });
  });

  it("stores macro histories under the active region and timeframe context", async () => {
    const history = makeHistory();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(history)));

    macroContext.set({
      mode: "rates_policy",
      region: "US",
      timeframe: "1Y",
      theme: "policy",
      comparisonRegion: null
    });

    await loadMacroSeriesHistory("us-cpi-yoy");

    expect(get(macroSeriesHistories)["US:1Y:us-cpi-yoy"]).toEqual(history);
    expect(get(lastError)).toBe("");
  });

  it("dedupes identical macro workspace loads into one request bundle", async () => {
    const snapshot = {
      ...makeSnapshot(),
      region: "US",
      timeframe: "1Y",
      theme: "policy",
      warnings: [],
    };
    const divergences = {
      ...makeDivergences(),
      region: "US",
      timeframe: "1Y",
      theme: "policy",
    };
    const events = {
      ...makeEvents(),
      region: "US",
      events: makeEvents().events.map((event) => ({ ...event, region: "US" }))
    };
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/macro/snapshot")) {
        return Promise.resolve(ok(snapshot));
      }
      if (url.endsWith("/macro/divergences")) {
        return Promise.resolve(ok(divergences));
      }
      if (url.includes("/macro/events")) {
        return Promise.resolve(ok(events));
      }
      if (url.includes("/macro/series/")) {
        return Promise.resolve(ok(makeHistory()));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([
      loadMacroWorkspace({ region: "US", timeframe: "1Y", theme: "policy" }),
      loadMacroWorkspace({ region: "US", timeframe: "1Y", theme: "policy" })
    ]);

    expect(callsFor(fetchMock, "/macro/snapshot")).toHaveLength(1);
    expect(callsFor(fetchMock, "/macro/divergences")).toHaveLength(1);
    expect(callsFor(fetchMock, "/macro/events")).toHaveLength(1);
    expect(get(macroSnapshot)?.timeframe).toBe("1Y");
  });
});

function callsFor(fetchMock: ReturnType<typeof vi.fn>, segment: string) {
  return fetchMock.mock.calls.filter(([input]) => String(input).includes(segment));
}

function snapshotBodies(fetchMock: ReturnType<typeof vi.fn>) {
  return callsFor(fetchMock, "/macro/snapshot").map(([, init]) => JSON.parse(String(init?.body ?? "{}")));
}

function makeSnapshot(): MacroSnapshot {
  return {
    region: "Global",
    timeframe: "6M",
    theme: "inflation",
    comparison_region: null,
    available_regions: ["US", "EU", "Global"],
    available_timeframes: ["1M", "3M", "6M", "1Y"],
    available_themes: ["all", "growth", "inflation", "policy", "recession_risk"],
    snapshot_cards: [
      {
        card_id: "inflation",
        title: "Inflation Context",
        subtitle: "Realized inflation versus market pricing",
        summary: "Inflation context compares CPI with breakevens.",
        mode_target: "cross_asset",
        target_theme: "inflation",
        metrics: [],
        source_provider: "fred",
        retrieved_at: "2026-03-20T11:00:00Z",
        origin: "macro_service.snapshot_cards",
        transformation_note: "Snapshot cards summarize macro conditions."
      }
    ],
    rates_policy: {
      headline: "Front-end policy pricing remains the cleanest read.",
      summary: "Rates & Policy combines curve and real-rate context.",
      policy_metrics: [],
      curve_nodes: [],
      real_yield_metrics: [],
      events: [],
      source_provider: "treasury",
      retrieved_at: "2026-03-20T11:00:00Z",
      origin: "macro_service.rates_policy",
      transformation_note: "Rates & Policy combines Treasury and FRED data.",
      comparison_region: null,
      comparison_summary: null
    },
    cross_asset: [],
    top_divergences: [],
    upcoming_events: [],
    warnings: ["Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first."],
    source_provider: "fred",
    retrieved_at: "2026-03-20T11:00:00Z",
    origin: "macro_service.snapshot",
    transformation_note: "Snapshot combines normalized macro sources."
  };
}

function makeDivergences(): MacroDivergenceListResponse {
  return {
    region: "Global",
    timeframe: "6M",
    theme: "inflation",
    comparison_region: null,
    divergences: [
      {
        divergence_id: "global:inflation:divergence",
        theme: "inflation",
        region: "Global",
        headline: "Inflation divergence score 2.60",
        summary: "CPI is reinforcing the theme while the dollar is leaning the other way.",
        score: 2.6,
        label: "high",
        metrics: [],
        series_ids: ["us-cpi-yoy", "us-dollar-broad"],
        source_provider: "fred",
        retrieved_at: "2026-03-20T10:00:00Z",
        origin: "macro_service.divergences",
        transformation_note: "Divergence scores compare directional changes across theme proxies.",
        comparison_region: null,
        comparison_score: null,
        score_gap: null,
        score_gap_display: null,
      }
    ]
  };
}

function makeEvents(): MacroEventsResponse {
  return {
    region: "Global",
    events: [
      {
        event_id: "fomc:2026-04-29",
        title: "FOMC Meeting",
        category: "policy",
        region: "Global",
        scheduled_at: "2026-04-29T00:00:00Z",
        relative_label: null,
        importance: "high",
        source_provider: "federalreserve",
        retrieved_at: "2026-03-20T10:00:00Z",
        origin: "macro.events.fomc_calendar",
        transformation_note: "Global mode reuses the US macro calendar in V1."
      }
    ]
  };
}

function makeHistory(): MacroSeriesHistory {
  return {
    series_id: "us-cpi-yoy",
    title: "Headline CPI YoY",
    region: "US",
    unit: "pct",
    frequency: "monthly",
    theme: "inflation",
    mode_tags: ["snapshot", "cross_asset"],
    points: [
      {
        timestamp: "2026-01-31T00:00:00Z",
        value: 2.9,
        source_provider: "fred",
        retrieved_at: "2026-03-20T09:00:00Z",
        origin: "macro_service.derived.yoy",
        transformation_note: "Year-over-year percent change computed from the CPI index level."
      }
    ],
    source_provider: "fred",
    retrieved_at: "2026-03-20T09:00:00Z",
    origin: "macro_service.derived.yoy",
    transformation_note: "Year-over-year percent change computed from the CPI index level."
  };
}

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    async json() {
      return body;
    }
  };
}
