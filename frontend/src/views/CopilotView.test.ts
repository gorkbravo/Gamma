import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CopilotSessionDetail, CopilotSessionSummary, CopilotStorageStatus } from "../lib/api/types";
import CopilotView from "./CopilotView.svelte";

function surface() {
  return {
    supported: true,
    domain: "synthesis" as const,
    contextLabel: "Context | Equity Research + Macro",
    domainLabel: "Copilot Context",
    guidance: "Grounded only in selected Gamma contexts.",
    placeholder: "Ask for a grounded synthesis.",
    selectedScopeDomains: ["equity_research", "macro"] as const,
    selectionMessage: "2 Gamma contexts selected.",
    scopeOptions: [],
    thread: null
  };
}

function session(sessionId: string, overrides: Partial<CopilotSessionSummary> = {}): CopilotSessionSummary {
  return {
    session_id: sessionId,
    title: `Session ${sessionId}`,
    created_at: "2026-07-25T10:00:00Z",
    updated_at: "2026-07-25T10:00:01Z",
    active_domain: "macro",
    active_context_fingerprint: "fp-macro",
    turn_count: 2,
    memo_count: 0,
    report_count: 0,
    artifact_count: 0,
    warnings: [],
    archived_at: null,
    ...overrides
  };
}

function detail(summary: CopilotSessionSummary): CopilotSessionDetail {
  return {
    session: summary,
    turns: [],
    memos: [],
    context_snapshots: [],
    artifacts: [],
    storage_warnings: []
  };
}

const storageStatus: CopilotStorageStatus = {
  current_schema_version: 3,
  supported_legacy_versions: [1, 2],
  warnings: [
    {
      warning_id: "storage_warning_1",
      record_type: "turn",
      action: "quarantined",
      message: "Copilot preserved an unreadable turn record.",
      path: "quarantine/turn/turn_abc.json.decode_error.preserved",
      created_at: "2026-07-25T09:59:00Z"
    }
  ]
};

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    synthesisSurface: surface(),
    sessions: [],
    activeSession: null,
    actionDefinitions: [],
    researchPlan: null,
    operatorPlan: null,
    operatorResult: null,
    latestHandoff: null,
    loading: false,
    onGenerate: vi.fn(),
    onToggleScope: vi.fn(),
    ...overrides
  };
}

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
    expect(body).toContain("Sources (1)");
    expect(body).toContain("Tools (1)");
    expect(body).toContain("Macro Snapshot");
    expect(body).toContain("get_synthesis_scope_summary");
  });

  it("distinguishes selected, inactive, running, and archived sessions", () => {
    const selected = session("session-selected", { title: "Selected conversation" });
    const { body } = render(CopilotView, {
      props: baseProps({
        sessions: [
          selected,
          session("session-inactive", { title: "Inactive conversation" }),
          session("session-running", { title: "Running conversation" }),
          session("session-archived", {
            title: "Archived conversation",
            archived_at: "2026-07-25T09:00:00Z"
          })
        ],
        activeSession: detail(selected),
        runningSessionIds: ["session-running"]
      })
    });

    expect(body).toContain("Selected conversation — selected, 2 turns");
    expect(body).toContain("Inactive conversation — inactive, 2 turns");
    expect(body).toContain("Running conversation — inactive · running, 2 turns");
    expect(body).toContain("Archived conversation — archived, 2 turns");
    expect(body).toContain('aria-current="true"');
    expect(body).toContain("running-dot");
  });

  it("labels a brand-new empty session as selected and empty", () => {
    const blank = session("session-blank", {
      title: "New Copilot Session",
      turn_count: 0,
      active_domain: null
    });
    const { body } = render(CopilotView, {
      props: baseProps({ sessions: [blank], activeSession: detail(blank) })
    });

    expect(body).toContain("New Copilot Session — selected, 0 turns");
    expect(body).toContain("empty");
    expect(body).not.toContain("archived, 0 turns");
  });

  it("exposes an accessible New chat control", () => {
    const { body } = render(CopilotView, { props: baseProps() });

    expect(body).toContain('aria-label="Start a new Copilot conversation"');
    expect(body).toContain("New chat");
    // Nothing about an existing conversation may disable it.
    expect(body).not.toContain('aria-label="Start a new Copilot conversation" disabled');
  });

  it("reports an honest failure when new chat creation fails", () => {
    const { body } = render(CopilotView, {
      props: baseProps({ sessionCreateError: "Copilot persistence is not configured." })
    });

    expect(body).toContain('role="alert"');
    expect(body).toContain("New chat failed: Copilot persistence is not configured.");
  });

  it("presents storage recovery as an in-flow status region with safe details", () => {
    const { body } = render(CopilotView, { props: baseProps({ storageStatus }) });

    expect(body).toContain('id="copilot-storage-recovery"');
    expect(body).toContain('role="status"');
    expect(body).toContain('aria-live="polite"');
    expect(body).toContain('aria-label="Copilot storage recovery"');
    expect(body).toContain("1 storage record preserved");
    expect(body).toContain("Nothing was deleted");
    expect(body).toContain("Inspect records");
    expect(body).toContain("Dismiss");
    // The rediscovery affordance sits with the other header controls.
    expect(body).toContain("Storage recovery diagnostics — 1 storage record preserved");
    expect(body).toContain('aria-controls="copilot-storage-recovery"');

    // It renders above the transcript, so it can never sit over the pinned
    // composer or the artifact inspector controls.
    const stripIndex = body.indexOf("copilot-storage-recovery");
    const transcriptIndex = body.indexOf('class="transcript');
    const composerIndex = body.indexOf('class="composer');
    expect(stripIndex).toBeGreaterThan(-1);
    expect(stripIndex).toBeLessThan(transcriptIndex);
    expect(stripIndex).toBeLessThan(composerIndex);
  });

  it("omits the storage region entirely when storage is healthy", () => {
    const { body } = render(CopilotView, { props: baseProps() });

    expect(body).not.toContain("copilot-storage-recovery");
    expect(body).not.toContain("storage record");
    expect(body).not.toContain("Storage recovery diagnostics");
  });

  it("never positions the storage recovery region over workspace controls", () => {
    const source = readFileSync(fileURLToPath(new URL("./CopilotView.svelte", import.meta.url)), "utf8");
    const styles = source.slice(source.indexOf("<style>"));

    // The pre-fix regression was an absolutely positioned bottom-right banner.
    expect(styles).not.toContain(".storage-warning");
    for (const selector of [".storage-strip", ".storage-summary", ".storage-details", ".storage-trigger"]) {
      const start = styles.indexOf(`${selector} {`);
      expect(start).toBeGreaterThan(-1);
      const rule = styles.slice(start, styles.indexOf("}", start));
      expect(rule).not.toContain("position: absolute");
      expect(rule).not.toContain("position: fixed");
      expect(rule).not.toContain("z-index");
    }
    // The strip is a real grid row of the chat column at every width.
    expect(styles).toContain("grid-template-rows: auto minmax(0, 1fr) auto");
  });

  it("offers Retry from the persisted turn after the composer has cleared", () => {
    const summary = session("session-quota", { turn_count: 1 });
    const { body } = render(CopilotView, {
      props: baseProps({
        sessions: [summary],
        activeSession: {
          ...detail(summary),
          turns: [
            {
              turn_id: "turn-1",
              session_id: summary.session_id,
              turn_index: 0,
              domain: "synthesis",
              prompt: "Map the active macro setup.",
              context_snapshot_id: "ctx-1",
              created_at: "2026-07-25T10:00:02Z",
              role: "research_agent",
              reasoning_effort: "medium",
              selected_scope_domains: ["macro"],
              context_fingerprint: "fp-macro",
              requested_provider: null,
              requested_model: null,
              resolved_provider: "openai_responses",
              resolved_model: "gpt-5.5",
              run_id: "run_1",
              terminal_status: "error",
              cancellation_outcome: null,
              usage: {
                input_tokens: 0,
                output_tokens: 0,
                reasoning_tokens: 0,
                total_tokens: 0,
                cache_read_tokens: 0,
                cache_write_tokens: 0,
                provider_calls: 1,
                tool_calls: 0,
                raw: {}
              },
              research_plan: null,
              operator_plan: null,
              run_events: [],
              confirmations: [],
              artifact_refs: [],
              mutation_refs: [],
              trace_state: {
                event_count: 0,
                tool_trace_count: 0,
                operator_event_count: 0,
                source_count: 0,
                warning_count: 0
              },
              result: {
                domain: "synthesis",
                current_tab: "copilot",
                status: "error",
                provider: "openai_responses",
                model: "gpt-5.5",
                response_id: "resp_quota",
                message: "The configured OpenAI account has no remaining quota.",
                card: null,
                sources: [],
                tool_traces: [],
                operator_events: [],
                warnings: []
              }
            }
          ]
        },
        lastSubmission: {
          submissionId: 3,
          prompt: "Map the active macro setup.",
          accepted: true,
          rejectedReason: null
        }
      })
    });

    expect(body).toContain("Retry");
    expect(body).toContain('title="Resend the last prompt"');
    expect(body).toContain("Map the active macro setup.");
    expect(body).toMatch(/<textarea[^>]*>\s*<\/textarea>/);
  });

  it("echoes the accepted prompt in the transcript instead of the cleared composer", () => {
    const { body } = render(CopilotView, {
      props: baseProps({
        loading: true,
        activeRun: {
          runId: "run_1",
          accepted: true,
          phase: "streaming",
          domain: "synthesis",
          provider: "openai_responses",
          model: "gpt-5.5",
          provisionalText: "",
          functionArguments: [],
          toolNotes: [],
          warnings: [],
          usage: null,
          lastSequence: 0,
          terminalEvent: null,
          statusDetail: null,
          rawResult: null
        },
        lastSubmission: {
          submissionId: 4,
          prompt: "Map the active macro setup.",
          accepted: true,
          rejectedReason: null
        }
      })
    });

    expect(body).toContain("Map the active macro setup.");
    // The composer itself is empty once the submission was accepted.
    expect(body).toMatch(/<textarea[^>]*>\s*<\/textarea>/);
  });
});
