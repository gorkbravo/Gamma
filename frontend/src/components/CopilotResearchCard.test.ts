import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import CopilotResearchCard from "./CopilotResearchCard.svelte";

describe("CopilotResearchCard", () => {
  it("renders a multi-turn research thread with the latest follow-up visible", () => {
    const { body } = render(CopilotResearchCard, {
      props: {
        open: true,
        available: true,
        contextLabel: "Macro | US | 3M | Snapshot",
        domainLabel: "Macro",
        guidance: "Grounded in the current macro workspace.",
        placeholder: "Map the active regime.",
        loading: false,
        thread: {
          domain: "macro",
          contextFingerprint: "macro:US:3M:all",
          latestResponseId: "resp_macro_2",
          entries: [
            {
              entryId: "resp_macro_1",
              turnIndex: 1,
              prompt: "Map the active macro setup.",
              continuedFromResponseId: null,
              result: makeResult("resp_macro_1", "Macro Thread 1")
            },
            {
              entryId: "resp_macro_2",
              turnIndex: 2,
              prompt: "Pressure-test the lead divergence.",
              continuedFromResponseId: "resp_macro_1",
              result: makeResult("resp_macro_2", "Macro Thread 2")
            }
          ]
        },
        onGenerate: vi.fn(),
        onClose: vi.fn()
      }
    });

    expect(body).toContain("Active Thread");
    expect(body).toContain("2 turns in this thread.");
    expect(body).toContain("Follow-up 2");
    expect(body).toContain("Initial Brief");
    expect(body).toContain("Macro Thread 2");
    expect(body).toContain("Macro Thread 1");
    expect(body).toContain("Pressure-test the lead divergence.");
    expect(body).toContain("Map the active macro setup.");
    expect(body).toContain("Follow Up");
  });
});

function makeResult(responseId: string, title: string) {
  return {
    domain: "macro" as const,
    current_tab: "macro",
    status: "ready",
    provider: "mock",
    model: "gamma-mock-research-card-v1",
    response_id: responseId,
    message: null,
    card: {
      title,
      hypothesis: "Macro hypothesis",
      rationale: "Macro rationale",
      required_data: ["Rates", "Inflation"],
      proposed_test: "Compare the active divergence against the next catalyst.",
      confounders: ["Event timing"],
      next_steps: ["Review the linked market context"],
      caveats: ["Fixture only"],
      source_backed_claims: [
        {
          claim: "The card is backed by fixture data.",
          evidence_refs: ["macro.fixture"]
        }
      ],
      inferred_claims: ["The best next question is still interpretive."]
    },
    sources: [
      {
        source_id: "macro.fixture",
        label: "Macro Fixture",
        kind: "fixture",
        provider: "mock",
        origin: "vitest",
        description: "Fixture source",
        retrieved_at: "2026-03-01T00:00:00Z"
      }
    ],
    tool_traces: [
      {
        tool_name: "get_macro_workspace_drilldown",
        summary: "Fixture drilldown",
        arguments: {},
        source_ids: ["macro.fixture"]
      }
    ],
    warnings: []
  };
}
