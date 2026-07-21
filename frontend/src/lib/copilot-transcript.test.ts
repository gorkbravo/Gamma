import { describe, expect, it } from "vitest";
import type { CopilotResearchCardResult } from "./api/types";
import { buildCopilotTranscriptBlocks } from "./copilot-transcript";

function result(card = true): CopilotResearchCardResult {
  return {
    domain: "macro",
    current_tab: "copilot",
    status: card ? "ready" : "incomplete",
    provider: "openai_responses",
    model: "gpt-5.5",
    response_id: null,
    message: card ? "Grounded answer." : "Response ended early.",
    card: card
      ? {
          title: "Macro card",
          hypothesis: "Hypothesis",
          rationale: "Rationale",
          required_data: [],
          proposed_test: "Test",
          confounders: [],
          next_steps: [],
          caveats: [],
          source_backed_claims: [],
          inferred_claims: []
        }
      : null,
    sources: [],
    tool_traces: [],
    operator_events: [],
    warnings: []
  };
}

describe("buildCopilotTranscriptBlocks", () => {
  it("maps a ready card into typed message, card, and provider blocks", () => {
    expect(buildCopilotTranscriptBlocks(result()).map((block) => block.kind)).toEqual([
      "message",
      "research-card",
      "provider-meta"
    ]);
  });

  it("maps a cardless result and evidence into typed status and evidence blocks", () => {
    const value = result(false);
    value.sources = [
      {
        source_id: "macro.snapshot",
        label: "Macro snapshot",
        kind: "workspace",
        provider: "gamma",
        origin: "gamma.macro",
        description: null,
        retrieved_at: null
      }
    ];
    value.warnings = ["Series is stale."];

    const blocks = buildCopilotTranscriptBlocks(value);
    expect(blocks.map((block) => block.kind)).toEqual(["status", "evidence"]);
    expect(blocks[0]).toMatchObject({ status: "incomplete", label: "incomplete" });
    expect(blocks[1]).toMatchObject({ providerLabel: "openai_responses / gpt-5.5" });
  });
});
