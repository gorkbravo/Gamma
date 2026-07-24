import { describe, expect, it } from "vitest";

import { normalizeCopilotResearchCardResult } from "./copilot-result";

describe("normalizeCopilotResearchCardResult", () => {
  it("fills in missing nested arrays so the drawer can render partial payloads", () => {
    const result = normalizeCopilotResearchCardResult("research", {
      current_tab: "research",
      status: "ready",
      provider: "openai_responses",
      model: "gpt-5.5",
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
      model: "gpt-5.5"
    });

    expect(result.card).toBeNull();
    expect(result.message).toBe("Copilot returned no renderable card.");
  });

  it("preserves backend error messages when the backend returns no card", () => {
    const result = normalizeCopilotResearchCardResult("synthesis", {
      current_tab: "copilot",
      status: "error",
      provider: "openai_responses",
      model: "gpt-5.5",
      card: null,
      message: "OpenAI returned no structured research card."
    });

    expect(result.status).toBe("error");
    expect(result.card).toBeNull();
    expect(result.message).toBe("OpenAI returned no structured research card.");
    expect(result.provider).toBe("openai_responses");
    expect(result.model).toBe("gpt-5.5");
  });

  it("makes ready-without-card distinct from backend errors", () => {
    const result = normalizeCopilotResearchCardResult("synthesis", {
      current_tab: "copilot",
      status: "ready",
      provider: "openai_responses",
      model: "gpt-5.5",
      card: null
    });

    expect(result.status).toBe("ready");
    expect(result.card).toBeNull();
    expect(result.message).toBe("Copilot returned no renderable card.");
  });
});
