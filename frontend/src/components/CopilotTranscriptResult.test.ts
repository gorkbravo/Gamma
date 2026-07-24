import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { CopilotResearchCardResult } from "../lib/api/types";
import CopilotTranscriptResult from "./CopilotTranscriptResult.svelte";

function result(): CopilotResearchCardResult {
  return {
    domain: "synthesis",
    current_tab: "copilot",
    status: "ready",
    provider: "openai_responses",
    model: "gpt-5.5",
    response_id: "resp_1",
    message: "The loaded evidence supports a cautious thesis.",
    card: {
      title: "Rates and equity sensitivity",
      hypothesis: "The equity is exposed to a renewed rate shock.",
      rationale: "Duration and valuation remain elevated.",
      required_data: ["Current duration proxy"],
      proposed_test: "Run the loaded rate-shock scenario.",
      confounders: ["Earnings revisions"],
      next_steps: ["Compare implied volatility"],
      caveats: ["The macro series is delayed"],
      source_backed_claims: [
        { claim: "Rates rose in the loaded window.", evidence_refs: ["macro.rates"] }
      ],
      inferred_claims: ["Valuation sensitivity may remain asymmetric."]
    },
    sources: [
      {
        source_id: "macro.rates",
        label: "Macro rates snapshot",
        kind: "workspace",
        provider: "gamma",
        origin: "gamma.macro",
        description: "Loaded Rates & Policy context.",
        retrieved_at: null
      }
    ],
    tool_traces: [
      {
        tool_name: "get_macro_rates",
        summary: "Loaded the current rates context.",
        arguments: {},
        source_ids: ["macro.rates"]
      }
    ],
    operator_events: [],
    warnings: ["One series is delayed."]
  };
}

describe("CopilotTranscriptResult", () => {
  it("renders the complete research card and its grounding evidence", () => {
    const { body } = render(CopilotTranscriptResult, { props: { result: result() } });

    for (const text of [
      "Required data",
      "Current duration proxy",
      "Confounders",
      "Earnings revisions",
      "Next steps",
      "Compare implied volatility",
      "Caveats",
      "The macro series is delayed",
      "Source-backed",
      "Rates rose in the loaded window.",
      "macro.rates",
      "Inferred",
      "Valuation sensitivity may remain asymmetric.",
      "Macro rates snapshot",
      "get_macro_rates",
      "One series is delayed."
    ]) {
      expect(body).toContain(text);
    }
  });

  it("keeps typed cardless failures visible with their evidence", () => {
    const failed = result();
    failed.status = "incomplete";
    failed.card = null;
    failed.message = "OpenAI ended the response early: max_output_tokens.";

    const { body } = render(CopilotTranscriptResult, { props: { result: failed } });
    expect(body).toContain("incomplete");
    expect(body).toContain("OpenAI ended the response early");
    expect(body).toContain("Sources (1)");
    expect(body).toContain("Tools (1)");
    expect(body).toContain("Warnings (1)");
  });
});
