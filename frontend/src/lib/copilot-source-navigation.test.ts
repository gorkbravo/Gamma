import { describe, expect, it, vi } from "vitest";
import type { CopilotSourceRef, CrossTabHandoffEnvelope } from "./api/types";
import { buildCopilotSourceHandoff } from "./copilot-source-navigation";

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

  it("does not invent a destination for an unmapped provider source", () => {
    expect(buildCopilotSourceHandoff({ ...source, source_id: "external.unknown", origin: "vendor.feed" })).toBeNull();
  });
});
