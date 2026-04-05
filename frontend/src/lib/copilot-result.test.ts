import { describe, expect, it } from "vitest";

import { normalizeCopilotResearchCardResult } from "./copilot-result";

describe("normalizeCopilotResearchCardResult", () => {
  it("fills in missing nested arrays so the drawer can render partial payloads", () => {
    const result = normalizeCopilotResearchCardResult("research", {
      current_tab: "research",
      status: "ready",
      provider: "openai_responses",
      model: "gpt-5.4",
      response_id: "",
      card: {
        title: "Test card",
        hypothesis: "Hypothesis",
        rationale: "Rationale",
        proposed_test: "Test"
      },
      tool_traces: [{ tool_name: "get_research_scope_summary", summary: "Loaded scope" }]
    });

    expect(result.response_id).toBeNull();
    expect(result.card?.required_data).toEqual([]);
    expect(result.card?.confounders).toEqual([]);
    expect(result.card?.next_steps).toEqual([]);
    expect(result.card?.caveats).toEqual([]);
    expect(result.card?.source_backed_claims).toEqual([]);
    expect(result.card?.inferred_claims).toEqual([]);
    expect(result.tool_traces[0]?.source_ids).toEqual([]);
  });

  it("adds a fallback message when the backend returns no renderable card", () => {
    const result = normalizeCopilotResearchCardResult("portfolio", {
      current_tab: "portfolio",
      status: "ready",
      provider: "openai_responses",
      model: "gpt-5.4"
    });

    expect(result.card).toBeNull();
    expect(result.message).toBe("Copilot returned no renderable card.");
  });
});
