import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type {
  CopilotDraftMutation,
  CopilotOperatorPlan,
  CopilotResearchCardResult,
  CopilotResearchPlan,
  CopilotResearchReport
} from "../lib/api/types";
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

const typedPlan: CopilotResearchPlan = {
  intent: "rates_review",
  target_entities: [{ kind: "ticker", id: "AAPL", label: "Apple", confidence: 1 }],
  depth_profile: "standard",
  domain_plan: [
    {
      domain: "macro",
      depth: "focused",
      reason: "Test rate sensitivity.",
      action_type: "read_context",
      planned_tools: ["get_macro_rates"],
      required_context: ["macro"],
      estimated_tool_calls: 1,
      estimated_provider_calls: 0,
      estimated_latency_ms: 50
    }
  ],
  domain_decisions: [{ domain: "macro", used: true, reason: "Relevant." }],
  max_tool_calls: 4,
  max_provider_calls: 1,
  max_elapsed_ms: 5000,
  requires_confirmation: false,
  expected_artifacts: ["research_card"],
  warnings: ["Delayed series."],
  generated_at: "2026-07-24T00:00:00Z",
  source_provider: "gamma",
  origin: "gamma.copilot.plan",
  transformation_note: null
};

const typedOperatorPlan: CopilotOperatorPlan = {
  intent: "operator_review",
  target_entities: [],
  depth_profile: "standard",
  role: "research_operator",
  research_plan: typedPlan,
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
      reason: "Review the exact watchlist diff.",
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

const typedReport: CopilotResearchReport = {
  report_id: "report_1",
  session_id: "session_1",
  title: "Rates report",
  source_turn_ids: ["turn_1"],
  source_memo_ids: [],
  source_backed_claims: [{ claim: "Rates rose.", evidence_refs: ["macro.rates"] }],
  inferred_claims: ["Duration may remain exposed."],
  assumptions: ["Hold earnings constant."],
  missing_data: ["Live dealer gamma."],
  warnings: ["One report series is delayed."],
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

const typedMutation: CopilotDraftMutation = {
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

describe("CopilotTranscriptResult", () => {
  it("renders inline apply and reject controls for a pending operator mutation", () => {
    const operatorResult = result();
    const pendingMutation = {
      ...typedMutation,
      status: "pending",
      rollback_snapshot_id: null
    };
    operatorResult.status = "awaiting_confirmation";
    operatorResult.operator_events = [
      {
        run_id: "run_1",
        event_id: "event_confirmation",
        sequence: 1,
        event_type: "confirmation-needed",
        timestamp: "2026-07-24T00:00:00Z",
        step_id: "step_draft",
        tool_id: "fundamentals.propose_dcf_update",
        title: "Review DCF update",
        message: "Review the exact before and after values.",
        payload: {
          mutation_id: pendingMutation.mutation_id,
          confirmation_token: pendingMutation.confirmation_token,
          mutation: pendingMutation
        },
        source_ids: [],
        warnings: []
      }
    ];

    const { body } = render(CopilotTranscriptResult, {
      props: {
        result: operatorResult,
        onConfirmMutation: () => pendingMutation,
        onRejectMutation: () => pendingMutation
      }
    });

    expect(body).toContain("Confirm and apply");
    expect(body).toContain("Reject");
    expect(body).toContain("Before");
    expect(body).toContain("After");
    expect(body).toContain("pre-change snapshot on apply");
    expect(body).not.toContain("confirm-token");
  });

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

  it("renders plans, operator events, reports, confirmations, artifacts, and mutation diffs", () => {
    const operatorResult = result();
    operatorResult.card = null;
    operatorResult.message = "Operator completed.";
    operatorResult.operator_events = [
      {
        run_id: "run_1",
        event_id: "event_1",
        sequence: 1,
        event_type: "tool-result",
        timestamp: "2026-07-24T00:00:00Z",
        step_id: "step_1",
        tool_id: "get_macro_rates",
        title: "Rates loaded",
        message: "Loaded the current rate regime.",
        payload: { status: "completed" },
        source_ids: ["macro.rates"],
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
        title: "Operator trace",
        message: "Created the trace artifact.",
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
        title: "Final operator report",
        message: "Operator report completed.",
        payload: { status: "ready" },
        source_ids: ["macro.rates"],
        warnings: []
      }
    ];

    const { body } = render(CopilotTranscriptResult, {
      props: {
        result: operatorResult,
        researchPlan: typedPlan,
        operatorPlan: typedOperatorPlan,
        report: typedReport,
        mutation: typedMutation,
        onOpenSource: () => {}
      }
    });

    for (const text of [
      "Research plan",
      "Operator review",
      "Review the exact watchlist diff.",
      "Rates loaded",
      "Operator trace",
      "Final operator report",
      "Rates report",
      "Source-backed findings",
      "Assumptions",
      "Missing data",
      "Macro watchlist",
      "Before",
      "After",
      "Open source"
    ]) {
      expect(body.toLowerCase()).toContain(text.toLowerCase());
    }
  });
});
