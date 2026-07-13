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
            tabId: "portfolio",
            domain: "portfolio",
            label: "Portfolio",
            contextLabel: "Portfolio | 110 USD | SPY",
            fingerprintLabel: "FP a1b2c3d4",
            freshnessLabel: "Snapshot 2026-03-01 00:00",
            warningLabel: null,
            supported: true,
            disabledReason: null
          },
          {
            tabId: "macro",
            domain: "macro",
            label: "Macro",
            contextLabel: "Macro | US | 3M | Snapshot",
            fingerprintLabel: "FP d4c3b2a1",
            freshnessLabel: "Snapshot 2026-03-01 00:00",
            warningLabel: "1 warning",
            supported: true,
            disabledReason: null
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

    expect(body).toContain("Research Agent");
    expect(body).toContain("Research Operator");
    expect(body).toContain("Context");
    expect(body).toContain("Portfolio");
    expect(body).toContain("Macro");
    // Fingerprint and warning details are surfaced via the chip tooltip.
    expect(body).toContain("FP a1b2c3d4");
    expect(body).toContain("1 warning");
    expect(body).toContain("Grounded Research");
    expect(body).toContain("Ask a follow-up grounded in this context scope...");
  });

  it("renders backend error results with grounding metadata when no card is returned", () => {
    const { body } = render(CopilotResearchCard, {
      props: {
        open: true,
        available: true,
        contextLabel: "Context | Equity Research + Macro",
        domainLabel: "Copilot Context",
        guidance: "Grounded only in selected Gamma contexts.",
        placeholder: "Synthesize the setup.",
        loading: false,
        selectedScopeDomains: ["equity_research", "macro"],
        scopeOptions: [
          {
            tabId: "strategy_lab",
            domain: "strategy_lab",
            label: "Strategy Lab",
            contextLabel: "Run a Strategy Lab import, composition, comparison, or queue a current Strategy Lab handoff before including it in a synthesis card.",
            fingerprintLabel: "UNAVAILABLE",
            freshnessLabel: null,
            warningLabel: "Context required",
            supported: false,
            disabledReason:
              "Run a Strategy Lab import, composition, comparison, or queue a current Strategy Lab handoff before including it in a synthesis card."
          }
        ],
        thread: {
          domain: "synthesis",
          contextFingerprint: "synthesis:equity+macro",
          latestResponseId: null,
          entries: [
            {
              entryId: "synthesis-error-1",
              turnIndex: 1,
              prompt: "Connect the loaded context.",
              continuedFromResponseId: null,
              result: {
                domain: "synthesis",
                current_tab: "copilot",
                status: "error",
                provider: "openai_responses",
                model: "gpt-5.5",
                response_id: "resp_error",
                message: "OpenAI returned no structured research card.",
                card: null,
                sources: [
                  {
                    source_id: "macro.snapshot",
                    label: "Macro Snapshot",
                    kind: "workspace",
                    provider: "gamma",
                    origin: "gamma.macro",
                    description: null,
                    retrieved_at: null
                  }
                ],
                tool_traces: [
                  {
                    tool_name: "get_synthesis_scope_summary",
                    summary: "Loaded synthesis scope.",
                    arguments: {},
                    source_ids: ["macro.snapshot"]
                  }
                ],
                operator_events: [],
                warnings: []
              }
            }
          ]
        },
        onGenerate: vi.fn(),
        onClose: vi.fn(),
        onToggleScope: vi.fn()
      }
    });

    expect(body).toContain("OpenAI returned no structured research card.");
    expect(body).toContain("openai_responses");
    expect(body).toContain("gpt-5.5");
    expect(body).toContain("Sources (1)");
    expect(body).toContain("Tools (1)");
    expect(body).toContain("macro.snapshot");
    expect(body).toContain("Run a Strategy Lab import");
  });

  it("renders distinct domains that share one source tab without duplicate keys", () => {
    const { body } = render(CopilotResearchCard, {
      props: {
        open: true,
        available: true,
        selectedScopeDomains: ["research", "equity_research"],
        scopeOptions: [
          {
            tabId: "equity_research",
            domain: "research",
            label: "Research Result",
            contextLabel: "SPY result",
            fingerprintLabel: "FP result",
            freshnessLabel: null,
            warningLabel: null,
            supported: true,
            disabledReason: null
          },
          {
            tabId: "equity_research",
            domain: "equity_research",
            label: "Equity Research",
            contextLabel: "SPY overview",
            fingerprintLabel: "FP overview",
            freshnessLabel: null,
            warningLabel: null,
            supported: true,
            disabledReason: null
          }
        ],
        onGenerate: vi.fn(),
        onClose: vi.fn(),
        onToggleScope: vi.fn()
      }
    });

    expect(body).toContain("Research Result");
    expect(body).toContain("Equity Research");
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
