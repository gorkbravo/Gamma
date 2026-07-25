import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CopilotArtifact, CopilotTurnRecord } from "../lib/api/types";
import CopilotArtifactsPanel from "./CopilotArtifactsPanel.svelte";

const turn = {
  turn_id: "turn-1",
  session_id: "session-1",
  turn_index: 0,
  domain: "macro",
  prompt: "Map the inflation setup.",
  context_snapshot_id: "snapshot-1",
  created_at: "2026-07-24T10:00:00Z",
  role: "research_operator",
  reasoning_effort: "high",
  selected_scope_domains: ["macro"],
  context_fingerprint: "fp-macro",
  requested_provider: "openai",
  requested_model: "requested-model",
  resolved_provider: "stub",
  resolved_model: "stub-model",
  run_id: "run-1",
  terminal_status: "ready",
  cancellation_outcome: "not_cancelled",
  usage: {
    input_tokens: 1,
    output_tokens: 1,
    reasoning_tokens: 0,
    total_tokens: 2,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    provider_calls: 1,
    tool_calls: 1,
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
    source_count: 1,
    warning_count: 1,
    bounded: true,
    replay_complete: true
  },
  result: {
    domain: "macro",
    current_tab: "macro",
    status: "ready",
    provider: "stub",
    model: "stub-model",
    response_id: "resp-1",
    message: null,
    card: null,
    sources: [],
    tool_traces: [],
    operator_events: [],
    warnings: []
  }
} satisfies CopilotTurnRecord;

const artifact = {
  artifact_id: "report-1",
  session_id: "session-1",
  artifact_type: "report",
  template: "research_report",
  title: "Inflation report",
  body: "# Inflation report\n\nEdited body.",
  source_turn_ids: ["turn-1", "missing-turn"],
  source_memo_ids: [],
  source_snapshot_ids: ["snapshot-1"],
  unavailable_source_turn_ids: ["missing-turn"],
  context_fingerprints: ["fp-macro"],
  source_backed_claims: [
    { claim: "Inflation evidence is available.", evidence_refs: ["macro.snapshot"] }
  ],
  inferred_claims: ["The next move remains uncertain."],
  assumptions: ["The fixture is local."],
  missing_data: ["One historical series is absent."],
  warnings: ["A linked source turn is unavailable."],
  warning_provenance: [],
  tool_trace_summary: [],
  sources: [
    {
      source_id: "macro.snapshot",
      label: "Macro snapshot",
      kind: "workspace",
      provider: "gamma",
      origin: "gamma.macro",
      description: null,
      retrieved_at: "2026-07-24T09:59:00Z"
    }
  ],
  provider_metadata: [],
  created_at: "2026-07-24T10:00:01Z",
  updated_at: "2026-07-24T10:00:02Z",
  source_provider: "gamma_copilot",
  origin: "test",
  transformation_note: "Evidence snapshot retained."
} satisfies CopilotArtifact;

describe("CopilotArtifactsPanel", () => {
  it("renders session artifacts, source selection, autosave state, and unavailable-turn recovery", () => {
    const { body } = render(CopilotArtifactsPanel, {
      props: {
        sessionId: "session-1",
        turns: [turn],
        artifacts: [artifact],
        activeArtifact: artifact,
        saveState: "error",
        onSelect: vi.fn(),
        onCreate: vi.fn(),
        onUpdate: vi.fn(),
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onExport: vi.fn()
      }
    });

    expect(body).toContain("Session artifacts");
    expect(body).toContain("Concise memo");
    expect(body).toContain("Research report");
    expect(body).toContain("0 selected");
    expect(body).toContain("Map the inflation setup.");
    expect(body).toContain("Inflation report");
    expect(body).toContain("1 linked source turn");
    expect(body).toContain("save failed");
    expect(body).toContain("Retry save");
    expect(body).toContain("Duplicate");
    expect(body).toContain("Export Markdown");
    expect(body).toContain("Delete");
  });

  it("keeps explicit destructive/export confirmations, keyboard save, and narrow drawer rules in the UI contract", () => {
    const source = readFileSync(
      fileURLToPath(new URL("./CopilotArtifactsPanel.svelte", import.meta.url)),
      "utf8"
    );
    const viewSource = readFileSync(
      fileURLToPath(new URL("../views/CopilotView.svelte", import.meta.url)),
      "utf8"
    );

    expect(source).toContain('aria-label="Confirm artifact deletion"');
    expect(source).toContain("Confirm delete");
    expect(source).toContain('aria-label="Confirm Markdown export"');
    expect(source).toContain("existing file with the same name may be replaced");
    expect(source).toContain("event.ctrlKey || event.metaKey");
    expect(source).toContain('event.key === "Escape"');
    expect(viewSource).toContain("@media (max-width: 820px)");
    expect(viewSource).toContain('aria-label="Confirm session deletion"');
    expect(viewSource).toContain("Archiving is a separate, non-destructive action.");
  });
});
