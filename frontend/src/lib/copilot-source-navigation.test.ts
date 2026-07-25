import { describe, expect, it, vi } from "vitest";
import type { CopilotSourceRef, CrossTabHandoffEnvelope } from "./api/types";
import {
  buildCopilotSourceHandoff,
  canNavigateCopilotSource,
  getCopilotSourceTarget,
  validatedExternalSourceUrl
} from "./copilot-source-navigation";

const source: CopilotSourceRef = {
  source_id: "macro.rates_policy",
  label: "Rates policy",
  kind: "workspace",
  provider: "gamma",
  origin: "gamma.macro.rates_policy",
  description: "Loaded rates lens.",
  retrieved_at: "2026-07-17T00:00:00Z"
};

describe("buildCopilotSourceHandoff", () => {
  it("maps a supported source to the correct Gamma tab and mode", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-17T01:00:00Z"));
    const handoff = buildCopilotSourceHandoff(source);
    expect(handoff).toMatchObject({
      source_tab: "copilot",
      intended_target_tab: "macro",
      intended_target_mode: "rates_policy",
      normalized_ids: { copilot_source_id: "macro.rates_policy" }
    });
    vi.useRealTimers();
  });

  it("preserves matching entity, timeframe, mode, lens ids, and warnings", () => {
    const prior = {
      source_tab: "macro",
      source_mode: "events_regimes",
      selected_entity: {
        entity_type: "macro_lens",
        label: "US policy",
        normalized_id: "macro:us:policy",
        provider_id: null,
        native_id: null,
        metadata: { lens: "policy" }
      },
      selected_timeframe: { label: "3M", start: null, end: null },
      provider: "gamma",
      source: null,
      warnings: ["Delayed series."],
      normalized_ids: { macro_lens_id: "macro:us:policy" },
      timestamp: "2026-07-17T00:00:00Z",
      intended_target_tab: "copilot",
      intended_target_mode: null
    } satisfies CrossTabHandoffEnvelope;
    const handoff = buildCopilotSourceHandoff(source, prior, ["Result warning."]);
    expect(handoff?.intended_target_mode).toBe("events_regimes");
    expect(handoff?.selected_entity?.metadata.lens).toBe("policy");
    expect(handoff?.selected_timeframe?.label).toBe("3M");
    expect(handoff?.normalized_ids.macro_lens_id).toBe("macro:us:policy");
    expect(handoff?.warnings).toEqual(["Delayed series.", "Result warning."]);
  });

  it("preserves an existing intended target mode without borrowing an unrelated source mode", () => {
    const prior = {
      source_tab: "sitrep",
      source_mode: "overview",
      selected_entity: null,
      selected_timeframe: { label: "1Y", start: null, end: null },
      provider: "gamma",
      source: null,
      warnings: [],
      normalized_ids: {},
      timestamp: "2026-07-17T00:00:00Z",
      intended_target_tab: "macro",
      intended_target_mode: "events_regimes"
    } satisfies CrossTabHandoffEnvelope;

    expect(buildCopilotSourceHandoff(source, prior)?.intended_target_mode).toBe("events_regimes");
  });

  it("does not invent a destination for an unmapped provider source", () => {
    expect(buildCopilotSourceHandoff({ ...source, source_id: "external.unknown", origin: "vendor.feed" })).toBeNull();
  });

  it("exposes only supported source targets as navigable", () => {
    expect(canNavigateCopilotSource(source)).toBe(true);
    expect(getCopilotSourceTarget({ ...source, source_id: "iv.surface", origin: "gamma.iv.surface" })).toEqual({
      tab: "iv",
      mode: "surface"
    });
    expect(
      canNavigateCopilotSource({ ...source, source_id: "external.unknown", origin: "vendor.feed" })
    ).toBe(false);
  });

  it.each([
    [
      {
        ...source,
        source_id: "equity_research.scope.nvda",
        navigation_tab: "equity_research",
        navigation_mode: "single_name",
        navigation_context: { symbol: "NVDA", timeframe: "252" }
      },
      "equity_research",
      "single_name",
      "NVDA"
    ],
    [
      {
        ...source,
        source_id: "commodities.inventory.eia_crude",
        navigation_tab: "commodities",
        navigation_mode: "inventories_fundamentals",
        navigation_context: { instrument_id: "wti", series_id: "eia-crude" }
      },
      "commodities",
      "inventories_fundamentals",
      "wti"
    ],
    [
      {
        ...source,
        source_id: "maritime.chokepoint.strait_of_hormuz",
        navigation_tab: "maritime",
        navigation_mode: "chokepoints",
        navigation_context: { chokepoint_id: "strait-of-hormuz" }
      },
      "maritime",
      "chokepoints",
      "strait-of-hormuz"
    ],
    [
      {
        ...source,
        source_id: "iv.expiry.nvda.2026_08_21",
        navigation_tab: "iv",
        navigation_mode: "surface",
        navigation_context: {
          symbol: "NVDA",
          expiry: "2026-08-21",
          contract_id: "NVDA-20260821-C-125"
        }
      },
      "iv",
      "surface",
      "NVDA"
    ]
  ])(
    "uses authoritative navigation metadata for %s sources",
    (mappedSource, expectedTab, expectedMode, expectedEntityId) => {
      const handoff = buildCopilotSourceHandoff(mappedSource as CopilotSourceRef);
      expect(handoff?.intended_target_tab).toBe(expectedTab);
      expect(handoff?.intended_target_mode).toBe(expectedMode);
      expect(handoff?.selected_entity?.normalized_id).toBe(expectedEntityId);
      expect(handoff?.normalized_ids).toMatchObject(mappedSource.navigation_context ?? {});
    }
  );

  it("treats inspectable non-navigable sources honestly", () => {
    const coverage = {
      ...source,
      source_id: "maritime.coverage",
      navigation_supported: false,
      navigation_reason: "Coverage metadata has no standalone destination."
    } satisfies CopilotSourceRef;
    expect(canNavigateCopilotSource(coverage)).toBe(false);
    expect(getCopilotSourceTarget(coverage)).toBeNull();
    expect(buildCopilotSourceHandoff(coverage)).toBeNull();
  });

  it("accepts only credential-free HTTP(S) news targets", () => {
    const news = {
      ...source,
      source_id: "external_context.news_item.feed_1",
      kind: "news_item",
      url: "https://news.example.com/events/oil-disruption",
      navigation_supported: true,
      navigation_context: { news_item_id: "feed:1" }
    } satisfies CopilotSourceRef;
    expect(canNavigateCopilotSource(news)).toBe(true);
    expect(validatedExternalSourceUrl(news.url)).toBe(
      "https://news.example.com/events/oil-disruption"
    );
    expect(validatedExternalSourceUrl("javascript:alert(1)")).toBeNull();
    expect(validatedExternalSourceUrl("https://user:secret@example.com/news")).toBeNull();
  });
});
