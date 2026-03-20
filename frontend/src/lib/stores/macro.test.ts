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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(snapshot))
      .mockResolvedValueOnce(ok(divergences))
      .mockResolvedValueOnce(ok(events))
      .mockResolvedValueOnce(ok(snapshot))
      .mockResolvedValueOnce(ok(divergences))
      .mockResolvedValueOnce(ok(events));

    vi.stubGlobal("fetch", fetchMock);

    await loadMacroWorkspace({
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparisonRegion: "US",
      mode: "snapshot"
    });
    await loadMacroWorkspace({ mode: "rates_policy" });

    expect(get(macroContext)).toEqual({
      mode: "rates_policy",
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparisonRegion: "US"
    });
    expect(get(macroSnapshot)?.region).toBe("Global");
    expect(get(macroDivergences)?.divergences[0]?.theme).toBe("inflation");
    expect(get(macroEvents)?.events[0]?.region).toBe("Global");

    const firstSnapshotPayload = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    const secondSnapshotPayload = JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body ?? "{}"));
    expect(firstSnapshotPayload).toMatchObject({
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
      comparison_region: "US"
    });
    expect(secondSnapshotPayload).toMatchObject({
      region: "Global",
      timeframe: "6M",
      theme: "inflation",
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
});

function makeSnapshot(): MacroSnapshot {
  return {
    region: "Global",
    timeframe: "6M",
    theme: "inflation",
    comparison_region: "US",
    available_regions: ["US", "Global"],
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
      transformation_note: "Rates & Policy combines Treasury and FRED data."
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
        transformation_note: "Divergence scores compare directional changes across theme proxies."
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
