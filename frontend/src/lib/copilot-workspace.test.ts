import { describe, expect, it } from "vitest";
import type {
  CopilotSessionSummary,
  CopilotStorageStatus,
  CopilotWorkingAnalysis
} from "./api/types";
import {
  describeCopilotSession,
  resolveComposerDraft,
  resolveInFlightPrompt,
  resolveWorkingAnalysisTarget,
  summarizeCopilotStorageRecovery,
  type CopilotComposerSubmission
} from "./copilot-workspace";

function workingAnalysis(
  overrides: Partial<CopilotWorkingAnalysis> = {}
): CopilotWorkingAnalysis {
  return {
    analysis_id: "work-lmt",
    session_id: "session-lmt",
    run_id: "oprun-lmt",
    tool_id: "run_fundamentals_reverse_valuation",
    domain: "fundamentals",
    analysis_type: "reverse_valuation",
    title: "LMT reverse valuation",
    status: "active",
    state_scope: "session_ephemeral",
    entity: { ticker: "lmt", label: "Lockheed Martin Corporation" },
    inputs: { ticker: "LMT" },
    outputs: { ticker: "LMT" },
    source_ids: ["fundamentals.reverse_valuation.analysis"],
    warnings: [],
    context_fingerprint: "fp-lmt",
    owning_tab: "fundamentals",
    owning_mode: "reverse_valuation",
    materialization: {
      contract_version: "copilot.materialization.v1",
      payload_contract: "copilot.fundamentals-working-analysis.v1",
      target_tab: "fundamentals",
      target_mode: "reverse_valuation",
      durable: false
    },
    created_at: "2026-08-25T10:00:00Z",
    updated_at: "2026-08-25T10:00:00Z",
    expires_at: "2026-09-01T10:00:00Z",
    materialized_at: null,
    discarded_at: null,
    read_only_safety: { execution_enabled: false },
    source_provider: "gamma",
    origin: "tests",
    transformation_note: null,
    contract_version: "copilot.working-analysis.v1",
    ...overrides
  };
}

describe("Copilot working-analysis materialization", () => {
  it("resolves the typed Fundamentals target and normalizes the ticker", () => {
    expect(resolveWorkingAnalysisTarget(workingAnalysis())).toEqual({
      analysisId: "work-lmt",
      ticker: "LMT",
      tab: "fundamentals",
      mode: "reverse_valuation"
    });
  });

  it("rejects inactive or unsupported materialization contracts", () => {
    expect(
      resolveWorkingAnalysisTarget(workingAnalysis({ status: "discarded" }))
    ).toBeNull();
    expect(
      resolveWorkingAnalysisTarget(workingAnalysis({ owning_tab: "options" }))
    ).toBeNull();
    expect(
      resolveWorkingAnalysisTarget(workingAnalysis({ state_scope: "durable" }))
    ).toBeNull();
  });

  it("resolves the typed temporary Risk scenarios target without requiring a ticker", () => {
    expect(
      resolveWorkingAnalysisTarget(
        workingAnalysis({
          tool_id: "run_risk_scenario_analysis",
          domain: "risk",
          analysis_type: "hypothetical_portfolio_risk_scenario",
          entity: {
            entity_type: "hypothetical_portfolio",
            portfolio_label: "AAPL/TLT",
            legs: [
              { symbol: "AAPL", weight: 0.6 },
              { symbol: "TLT", weight: 0.4 }
            ]
          },
          owning_tab: "risk",
          owning_mode: "scenarios",
          materialization: {
            contract_version: "copilot.materialization.v1",
            payload_contract: "copilot.risk-working-analysis.v1",
            target_tab: "risk",
            target_mode: "scenarios",
            durable: false
          }
        })
      )
    ).toEqual({
      analysisId: "work-lmt",
      tab: "risk",
      mode: "scenarios"
    });
  });
});

function submission(overrides: Partial<CopilotComposerSubmission> = {}): CopilotComposerSubmission {
  return {
    submissionId: 1,
    prompt: "Map the active macro setup.",
    accepted: false,
    rejectedReason: null,
    ...overrides
  };
}

function summary(sessionId: string, overrides: Partial<CopilotSessionSummary> = {}): CopilotSessionSummary {
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

describe("copilot composer draft policy", () => {
  it("clears the composer as soon as the submission is accepted", () => {
    const resolved = resolveComposerDraft(
      { draft: "Map the active macro setup.", handledSubmissionId: 0 },
      submission({ accepted: true })
    );

    expect(resolved.draft).toBe("");
    expect(resolved.handledSubmissionId).toBe(1);
  });

  it("keeps the composer clear for every typed non-success outcome after acceptance", () => {
    // The final status is irrelevant: acceptance means a retryable turn exists.
    const outcomes = [
      "quota_exceeded",
      "provider_error",
      "refusal",
      "incomplete",
      "cancelled",
      "timeout",
      "no_tools_available"
    ];

    for (const [index, outcome] of outcomes.entries()) {
      const accepted = submission({
        submissionId: index + 1,
        prompt: `Run ${outcome}.`,
        accepted: true
      });
      const cleared = resolveComposerDraft(
        { draft: `Run ${outcome}.`, handledSubmissionId: index },
        accepted
      );
      expect(cleared.draft).toBe("");

      // A later reactive pass with the same submission must not resurrect it.
      const stable = resolveComposerDraft(
        { draft: cleared.draft, handledSubmissionId: cleared.handledSubmissionId },
        accepted
      );
      expect(stable.draft).toBe("");
    }
  });

  it("preserves the draft when the submission is rejected before acceptance", () => {
    const resolved = resolveComposerDraft(
      { draft: "Map the active macro setup.", handledSubmissionId: 0 },
      submission({ rejectedReason: "Select at least one loaded Gamma context before using Copilot." })
    );

    expect(resolved.draft).toBe("Map the active macro setup.");
    expect(resolved.handledSubmissionId).toBe(0);
  });

  it("preserves a new draft typed while the accepted run was still streaming", () => {
    const resolved = resolveComposerDraft(
      { draft: "A different follow-up.", handledSubmissionId: 0 },
      submission({ accepted: true })
    );

    expect(resolved.draft).toBe("A different follow-up.");
    expect(resolved.handledSubmissionId).toBe(1);
  });

  it("leaves the composer untouched when there is no submission yet", () => {
    const resolved = resolveComposerDraft({ draft: "Draft in progress", handledSubmissionId: 0 }, null);
    expect(resolved).toEqual({ draft: "Draft in progress", handledSubmissionId: 0 });
  });

  it("echoes the accepted prompt in flight after the composer has cleared", () => {
    expect(resolveInFlightPrompt("", submission({ accepted: true }))).toBe("Map the active macro setup.");
    expect(resolveInFlightPrompt("Still typing", submission())).toBe("Still typing");
    expect(resolveInFlightPrompt("   ", null)).toBeNull();
  });
});

describe("copilot session lifecycle presentation", () => {
  it("separates selected, inactive, running, and archived state", () => {
    const sessions = [
      summary("session-selected"),
      summary("session-inactive"),
      summary("session-running"),
      summary("session-archived", { archived_at: "2026-07-25T09:00:00Z" })
    ];

    const described = sessions.map((session) =>
      describeCopilotSession(session, {
        selectedSessionId: "session-selected",
        runningSessionIds: ["session-running"]
      })
    );

    expect(described.map((item) => item.stateLabel)).toEqual([
      "selected",
      "inactive",
      "inactive · running",
      "archived"
    ]);
    expect(described[0].selected).toBe(true);
    expect(described[0].running).toBe(false);
    expect(described[2].running).toBe(true);
    expect(described[2].selected).toBe(false);
    expect(described[3].archived).toBe(true);
  });

  it("keeps a run visible on the selected session without conflating the two", () => {
    const described = describeCopilotSession(summary("session-a"), {
      selectedSessionId: "session-a",
      runningSessionIds: ["session-a"]
    });

    expect(described.stateLabel).toBe("selected · running");
    expect(described.accessibleLabel).toBe("Session session-a — selected · running, 2 turns");
  });

  it("treats a blank new session as selected and empty, not archived", () => {
    const described = describeCopilotSession(
      summary("session-new", { turn_count: 0, active_domain: null }),
      { selectedSessionId: "session-new" }
    );

    expect(described.selected).toBe(true);
    expect(described.archived).toBe(false);
    expect(described.running).toBe(false);
    expect(described.accessibleLabel).toContain("0 turns");
  });
});

describe("copilot storage recovery summary", () => {
  const status: CopilotStorageStatus = {
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

  it("reports nothing when storage is healthy", () => {
    expect(summarizeCopilotStorageRecovery(null)).toBeNull();
    expect(
      summarizeCopilotStorageRecovery({ ...status, warnings: [] })
    ).toBeNull();
  });

  it("explains that originals were preserved and healthy sessions remain usable", () => {
    const summarized = summarizeCopilotStorageRecovery(status);

    expect(summarized?.count).toBe(1);
    expect(summarized?.headline).toBe("1 storage record preserved");
    expect(summarized?.explanation).toContain("kept the original file");
    expect(summarized?.explanation).toContain("Nothing was deleted");
    expect(summarized?.explanation).toContain("remain usable");
  });

  it("exposes safe inspection details without record payloads", () => {
    const summarized = summarizeCopilotStorageRecovery(status);
    const detail = summarized?.details[0];

    expect(detail?.warningId).toBe("storage_warning_1");
    expect(detail?.label).toBe("turn · quarantined · quarantine/turn/turn_abc.json.decode_error.preserved");
    expect(detail?.message).toBe("Copilot preserved an unreadable turn record.");
    // Paths stay relative to the Copilot store; no absolute disk path leaks.
    expect(detail?.label).not.toContain(":\\");
    expect(detail?.label).not.toContain("/Users/");
  });

  it("pluralizes multiple preserved records", () => {
    const summarized = summarizeCopilotStorageRecovery({
      ...status,
      warnings: [
        status.warnings[0],
        { ...status.warnings[0], warning_id: "storage_warning_2", record_type: "session" }
      ]
    });

    expect(summarized?.headline).toBe("2 storage records preserved");
    expect(summarized?.details).toHaveLength(2);
  });
});
