import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import CopilotView from "./CopilotView.svelte";

describe("CopilotView", () => {
  it("renders backend error results with no card as visible grounded thread output", () => {
    const { body } = render(CopilotView, {
      props: {
        synthesisSurface: {
          supported: true,
          domain: "synthesis",
          contextLabel: "Context | Equity Research + Macro",
          domainLabel: "Copilot Context",
          guidance: "Grounded only in selected Gamma contexts.",
          placeholder: "Ask for a grounded synthesis.",
          selectedScopeDomains: ["equity_research", "macro"],
          selectionMessage: "2 Gamma contexts selected.",
          scopeOptions: [
            {
              tabId: "strategy_lab",
              domain: "strategy_lab",
              label: "Strategy Lab",
              contextLabel: "Strategy Lab context unavailable",
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
          }
        },
        sessions: [],
        activeSession: null,
        actionDefinitions: [],
        researchPlan: null,
        operatorPlan: null,
        operatorResult: null,
        latestHandoff: null,
        loading: false,
        onGenerate: vi.fn(),
        onToggleScope: vi.fn()
      }
    });

    expect(body).toContain("Connect the loaded context.");
    expect(body).toContain("OpenAI returned no structured research card.");
    expect(body).toContain("openai_responses / gpt-5.5");
    expect(body).toContain("1 sources / 1 tools");
  });
});
