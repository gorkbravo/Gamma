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

    expect(body).toContain("Macro Thread 2");
    expect(body).toContain("Macro Thread 1");
    expect(body).toContain("Pressure-test the lead divergence.");
    expect(body).toContain("Map the active macro setup.");
    expect(body).toContain("Follow up");
    // Research Card header is shown only on the first turn, not on follow-ups.
    expect(body.match(/Research Card/g)?.length ?? 0).toBe(1);
  });

  it("renders synthesis mode with explicit grounding scope details", () => {
    const { body } = render(CopilotResearchCard, {
      props: {
        open: true,
        available: true,
        mode: "synthesis",
        contextLabel: "Synthesis | Portfolio + Macro",
        domainLabel: "Cross-Context Synthesis",
        guidance: "Grounded only in the selected Gamma contexts.",
        placeholder: "Synthesize the strongest contradiction.",
        loading: false,
        selectionMessage: "2 loaded contexts included in this synthesis.",
        selectedScopeDomains: ["portfolio", "macro"],
        scopeOptions: [
          {
            domain: "portfolio",
            label: "Portfolio",
            contextLabel: "Portfolio | 110 USD | SPY",
            fingerprintLabel: "FP a1b2c3d4",
            freshnessLabel: "Snapshot 2026-03-01 00:00",
            warningLabel: null
          },
          {
            domain: "macro",
            label: "Macro",
            contextLabel: "Macro | US | 3M | Snapshot",
            fingerprintLabel: "FP d4c3b2a1",
            freshnessLabel: "Snapshot 2026-03-01 00:00",
            warningLabel: "1 warning"
          }
        ],
        thread: {
          domain: "synthesis",
          contextFingerprint: "synthesis:portfolio+macro",
          latestResponseId: "resp_synthesis_1",
          entries: [
            {
              entryId: "resp_synthesis_1",
              turnIndex: 1,
              prompt: "Connect the loaded portfolio and macro context.",
              continuedFromResponseId: null,
              result: makeResult("resp_synthesis_1", "Synthesis Thread 1", "synthesis")
            }
          ]
        },
        onGenerate: vi.fn(),
        onClose: vi.fn(),
        onSetMode: vi.fn(),
        onToggleScope: vi.fn()
      }
    });

    expect(body).toContain("Synthesis");
    expect(body).toContain("Scope");
    expect(body).toContain("Portfolio");
    expect(body).toContain("Macro");
    // Fingerprint and warning details are surfaced via the chip tooltip.
    expect(body).toContain("FP a1b2c3d4");
    expect(body).toContain("1 warning");
    expect(body).toContain("Research Synthesis");
    expect(body).toContain("Ask a follow-up grounded in this synthesis scope...");
  });
});

function makeResult(
  responseId: string,
  title: string,
  domain: "macro" | "synthesis" = "macro"
) {
  return {
    domain,
    current_tab: domain,
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
