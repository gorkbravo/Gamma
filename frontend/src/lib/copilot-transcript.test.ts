import { describe, expect, it } from "vitest";
import type {
  CopilotDraftMutation,
  CopilotOperatorPlan,
  CopilotResearchCardResult,
  CopilotResearchPlan,
  CopilotResearchReport
} from "./api/types";
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

function researchPlan(): CopilotResearchPlan {
  return {
    intent: "cross_context_review",
    target_entities: [{ kind: "ticker", id: "AAPL", label: "Apple", confidence: 1 }],
    depth_profile: "standard",
    domain_plan: [
      {
        domain: "macro",
        depth: "focused",
        reason: "Test the rates exposure.",
        action_type: "read_context",
        planned_tools: ["get_macro_rates"],
        required_context: ["macro"],
        estimated_tool_calls: 1,
        estimated_provider_calls: 0,
        estimated_latency_ms: 50
      }
    ],
    domain_decisions: [
      { domain: "macro", used: true, reason: "Relevant." },
      { domain: "crypto", used: false, reason: "Out of scope." }
    ],
    max_tool_calls: 4,
    max_provider_calls: 1,
    max_elapsed_ms: 5000,
    requires_confirmation: false,
    expected_artifacts: ["research_card"],
    warnings: ["Rates series is delayed."],
    generated_at: "2026-07-24T00:00:00Z",
    source_provider: "gamma",
    origin: "gamma.copilot.plan",
    transformation_note: null
  };
}

function operatorPlan(): CopilotOperatorPlan {
  return {
    intent: "operator_review",
    target_entities: [],
    depth_profile: "standard",
    role: "research_operator",
    research_plan: null,
    steps: [
      {
        step_id: "step_1",
        order: 1,
        title: "Load rates",
        domain: "macro",
        action_type: "read_context",
        tool_id: "get_macro_rates",
        status: "planned",
        permission_policy: "automatic_read_only",
        requires_confirmation: false,
        expected_artifacts: ["trace"],
        rationale: "Ground the report.",
        stop_conditions: [],
        estimated_latency_ms: 50,
        warnings: []
      }
    ],
    confirmation_checkpoints: [
      {
        checkpoint_id: "confirm_1",
        after_step_id: "step_1",
        reason: "Review the exact mutation.",
        required_for_tool_ids: ["draft_watchlist"],
        default_policy: "deny"
      }
    ],
    max_tool_calls: 4,
    max_provider_calls: 1,
    max_elapsed_ms: 5000,
    requires_confirmation: true,
    expected_artifacts: ["operator_report"],
    warnings: [],
    generated_at: "2026-07-24T00:00:00Z",
    source_provider: "gamma",
    origin: "gamma.copilot.operator_plan",
    transformation_note: null
  };
}

function report(): CopilotResearchReport {
  return {
    report_id: "report_1",
    session_id: "session_1",
    title: "Rates review",
    source_turn_ids: ["turn_1"],
    source_memo_ids: [],
    source_backed_claims: [{ claim: "Rates rose.", evidence_refs: ["macro.rates"] }],
    inferred_claims: ["Duration may remain exposed."],
    assumptions: ["Hold earnings constant."],
    missing_data: ["Live dealer gamma."],
    warnings: ["One series is delayed."],
    warning_provenance: [],
    tool_trace_summary: [
      {
        tool_name: "get_macro_rates",
        summary: "Loaded rates.",
        source_ids: ["macro.rates"],
        status: "completed",
        step_id: "step_1",
        event_type: "tool-result",
        output_summary: {},
        warnings: []
      }
    ],
    sources: [
      {
        source_id: "macro.rates",
        label: "Rates policy",
        kind: "workspace",
        provider: "gamma",
        origin: "gamma.macro.rates_policy",
        description: null,
        retrieved_at: null
      }
    ],
    generated_at: "2026-07-24T00:00:00Z",
    source_provider: "gamma",
    origin: "gamma.copilot.report",
    transformation_note: null
  };
}

function mutation(): CopilotDraftMutation {
  return {
    mutation_id: "mutation_1",
    domain: "portfolio",
    tool_id: "draft_watchlist",
    action_type: "draft_watchlist",
    target_id: "watchlist_1",
    target_label: "Macro watchlist",
    status: "pending_confirmation",
    requires_confirmation: true,
    confirmation_token: "confirm-token",
    diff: [
      {
        path: "symbols[0]",
        label: "Symbol",
        before: null,
        after: "AAPL",
        unit: null,
        change_type: "added"
      }
    ],
    rendered_diff: ["Add AAPL"],
    proposed_payload: { symbol: "AAPL" },
    rationale: "Track the exposed equity.",
    warnings: [],
    source_ids: ["macro.rates"],
    rollback_snapshot_id: "rollback_1",
    created_at: "2026-07-24T00:00:00Z",
    expires_at: "2026-07-24T00:05:00Z",
    applied_at: null,
    source_provider: "gamma",
    origin: "gamma.copilot.mutation",
    transformation_note: null
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

  it("maps plans, operator events, reports, confirmations, artifacts, and mutation diffs", () => {
    const value = result(false);
    value.status = "ready";
    value.message = "Operator completed.";
    value.sources = report().sources;
    value.operator_events = [
      {
        run_id: "run_1",
        event_id: "event_1",
        sequence: 1,
        event_type: "tool-result",
        timestamp: "2026-07-24T00:00:00Z",
        step_id: "step_1",
        tool_id: "get_macro_rates",
        title: "Rates loaded",
        message: "Loaded rates.",
        payload: { status: "completed" },
        source_ids: ["macro.rates", "missing.source"],
        warnings: []
      },
      {
        run_id: "run_1",
        event_id: "event_2",
        sequence: 2,
        event_type: "artifact-created",
        timestamp: "2026-07-24T00:00:01Z",
        step_id: null,
        tool_id: null,
        title: "Trace",
        message: "Created trace.",
        payload: { artifact_id: "run_1" },
        source_ids: [],
        warnings: []
      },
      {
        run_id: "run_1",
        event_id: "event_3",
        sequence: 3,
        event_type: "final-report",
        timestamp: "2026-07-24T00:00:02Z",
        step_id: null,
        tool_id: null,
        title: "Final report",
        message: "Complete.",
        payload: { status: "ready" },
        source_ids: ["macro.rates"],
        warnings: []
      }
    ];

    const blocks = buildCopilotTranscriptBlocks(value, {
      researchPlan: researchPlan(),
      operatorPlan: operatorPlan(),
      report: report(),
      mutation: mutation()
    });

    expect(blocks.map((block) => block.kind)).toEqual([
      "research-plan",
      "operator-plan",
      "confirmation",
      "message",
      "operator-step",
      "artifact",
      "operator-report",
      "evidence",
      "report",
      "confirmation",
      "mutation-diff"
    ]);
    expect(blocks.find((block) => block.kind === "operator-step")).toMatchObject({
      references: {
        evidence: [{ source_id: "macro.rates" }],
        unresolvedEvidenceRefs: ["missing.source"]
      }
    });
    expect(blocks.find((block) => block.kind === "report")).toMatchObject({
      claims: [{ claim: "Rates rose.", evidence: [{ source_id: "macro.rates" }] }]
    });
  });
});
