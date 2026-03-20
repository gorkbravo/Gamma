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

  it("renders macro warnings and visible V1 scope limits inline", () => {
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

    expect(body).toContain("Visible V1 limits");
    expect(body).toContain("Macro V1 is US-first. Global mode is intentionally lighter than the US view.");
    expect(body).toContain("Global mode is a light comparative lens in V1; the deepest normalized coverage remains US-first and some analytics reuse US proxies.");
    expect(body).toContain("Comparison targets are not applied analytically in Macro V1; the comparison selection was ignored.");
    expect(body).not.toContain(">Compare<");
  });
});

function makeSnapshot(): MacroSnapshot {
  return {
    region: "Global",
    timeframe: "6M",
    theme: "inflation",
    comparison_region: null,
    available_regions: ["US", "Global"],
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
    transformation_note: "Snapshot combines normalized macro sources."
  };
}

function makeEvents(): MacroEventsResponse {
  return {
    region: "Global",
    events: []
  };
}
