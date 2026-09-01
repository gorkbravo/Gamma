import type {
  CopilotSessionSummary,
  CopilotStorageStatus,
  CopilotStorageWarning,
  CopilotWorkingAnalysis
} from "./api/types";

/**
 * Pure presentation rules for the Copilot workspace shell.
 *
 * These live outside the Svelte component so composer, session-state, and
 * storage-recovery behaviour can be asserted as observable state instead of
 * being inferred from rendered markup.
 */

export type CopilotComposerSubmission = {
  submissionId: number;
  prompt: string;
  /** True once the server acknowledged the run and a turn is being persisted. */
  accepted: boolean;
  /** Set when the submission never reached the server. */
  rejectedReason: string | null;
};

export type CopilotComposerDraftState = {
  draft: string;
  handledSubmissionId: number;
};

export type CopilotFundamentalsWorkingAnalysisTarget = {
  analysisId: string;
  ticker: string;
  tab: "fundamentals";
  mode: "reverse_valuation";
};

export type CopilotRiskWorkingAnalysisTarget = {
  analysisId: string;
  tab: "risk";
  mode: "overview" | "scenarios";
};

export type CopilotOptionsWorkingAnalysisTarget = {
  analysisId: string;
  symbol: string;
  tab: "iv";
  mode: "realized_implied";
};

export type CopilotResearchScriptWorkingAnalysisTarget = {
  analysisId: string;
  tab: "strategy_lab";
  mode: "script";
  scriptId: string;
  revisionId: string;
  inputSnapshotId: string;
  selectedRunId: string | null;
};

export type CopilotWorkingAnalysisTarget =
  | CopilotFundamentalsWorkingAnalysisTarget
  | CopilotRiskWorkingAnalysisTarget
  | CopilotOptionsWorkingAnalysisTarget
  | CopilotResearchScriptWorkingAnalysisTarget;

/** Accept only explicit non-durable materialization contracts supported by Gamma. */
export function resolveWorkingAnalysisTarget(
  analysis: CopilotWorkingAnalysis
): CopilotWorkingAnalysisTarget | null {
  const materialization = analysis.materialization;
  if (
    analysis.status !== "active" ||
    analysis.state_scope !== "session_ephemeral" ||
    materialization.durable !== false ||
    materialization.target_tab !== analysis.owning_tab ||
    materialization.target_mode !== analysis.owning_mode
  ) {
    return null;
  }
  const ticker = String(
    analysis.entity.ticker ?? analysis.entity.symbol ?? analysis.entity.normalized_id ?? ""
  )
    .trim()
    .toUpperCase();
  if (
    analysis.owning_tab === "fundamentals" &&
    analysis.owning_mode === "reverse_valuation" &&
    materialization.payload_contract === "copilot.fundamentals-working-analysis.v1" &&
    ticker
  ) {
    return {
      analysisId: analysis.analysis_id,
      ticker,
      tab: "fundamentals",
      mode: "reverse_valuation"
    };
  }
  if (
    analysis.owning_tab === "risk" &&
    (analysis.owning_mode === "overview" || analysis.owning_mode === "scenarios") &&
    materialization.payload_contract === "copilot.risk-working-analysis.v1"
  ) {
    return {
      analysisId: analysis.analysis_id,
      tab: "risk",
      mode: analysis.owning_mode
    };
  }
  if (
    analysis.owning_tab === "iv" &&
    analysis.owning_mode === "realized_implied" &&
    materialization.payload_contract === "copilot.options-working-analysis.v1" &&
    ticker
  ) {
    return {
      analysisId: analysis.analysis_id,
      symbol: ticker,
      tab: "iv",
      mode: "realized_implied"
    };
  }
  const scriptId = String(analysis.entity.script_id ?? analysis.entity.normalized_id ?? "").trim();
  const revisionId = String(analysis.entity.revision_id ?? "").trim();
  const inputSnapshotId = String(analysis.entity.input_snapshot_id ?? "").trim();
  const selectedRunId = String(analysis.entity.selected_run_id ?? "").trim() || null;
  if (
    analysis.owning_tab === "strategy_lab" &&
    analysis.owning_mode === "script" &&
    materialization.payload_contract === "copilot.strategy-lab-script-working-analysis.v1" &&
    scriptId &&
    revisionId &&
    inputSnapshotId
  ) {
    return {
      analysisId: analysis.analysis_id,
      tab: "strategy_lab",
      mode: "script",
      scriptId,
      revisionId,
      inputSnapshotId,
      selectedRunId
    };
  }
  return null;
}

/**
 * Resolve the composer draft against the latest submission.
 *
 * An accepted submission clears the composer because the prompt is already
 * persisted as a turn and is reachable through Retry. A submission that was
 * rejected before acceptance leaves the draft untouched so nothing is lost, and
 * text typed after the submission is never discarded.
 */
export function resolveComposerDraft(
  current: CopilotComposerDraftState,
  submission: CopilotComposerSubmission | null
): CopilotComposerDraftState {
  if (submission == null || !submission.accepted) {
    return current;
  }
  if (submission.submissionId === current.handledSubmissionId) {
    return current;
  }
  const holdsSubmittedPrompt = current.draft.trim() === submission.prompt.trim();
  return {
    draft: holdsSubmittedPrompt ? "" : current.draft,
    handledSubmissionId: submission.submissionId
  };
}

/**
 * The prompt echoed in the transcript while a run streams.
 *
 * Once the composer clears, the in-flight bubble must come from the accepted
 * submission rather than from whatever is currently typed.
 */
export function resolveInFlightPrompt(
  draft: string,
  submission: CopilotComposerSubmission | null
): string | null {
  const accepted = submission?.accepted ? submission.prompt.trim() : "";
  if (accepted) {
    return accepted;
  }
  const pending = draft.trim();
  return pending ? pending : null;
}

export type CopilotSessionPresentation = {
  sessionId: string;
  selected: boolean;
  running: boolean;
  archived: boolean;
  /** Compact state word used in the row meta line. */
  stateLabel: string;
  /** Full accessible label for the row control. */
  accessibleLabel: string;
};

/**
 * Describe a session row's lifecycle state.
 *
 * `selected`, `running`, and `archived` are independent facts: selection is not
 * proof that a run is active, and a run keeps its indicator after the user
 * switches away.
 */
export function describeCopilotSession(
  session: CopilotSessionSummary,
  options: { selectedSessionId: string | null; runningSessionIds?: readonly string[] }
): CopilotSessionPresentation {
  const selected = session.session_id === options.selectedSessionId;
  const running = (options.runningSessionIds ?? []).includes(session.session_id);
  const archived = session.archived_at != null;
  const states: string[] = [selected ? "selected" : archived ? "archived" : "inactive"];
  if (archived && selected) {
    states.push("archived");
  }
  if (running) {
    states.push("running");
  }
  const stateLabel = states.join(" · ");
  return {
    sessionId: session.session_id,
    selected,
    running,
    archived,
    stateLabel,
    accessibleLabel: `${session.title} — ${stateLabel}, ${session.turn_count} turn${session.turn_count === 1 ? "" : "s"}`
  };
}

export type CopilotStorageWarningDetail = {
  warningId: string;
  /** Safe one-line label: record type, recovery action, and relative path. */
  label: string;
  message: string;
  recordedAt: string;
};

export type CopilotStorageRecoverySummary = {
  count: number;
  headline: string;
  explanation: string;
  details: CopilotStorageWarningDetail[];
};

function toStorageWarningDetail(warning: CopilotStorageWarning): CopilotStorageWarningDetail {
  return {
    warningId: warning.warning_id,
    // `path` is already relative to the Copilot store root and no record
    // payload is exposed, so this stays safe to show in the workspace.
    label: `${warning.record_type} · ${warning.action} · ${warning.path || "unknown location"}`,
    message: warning.message,
    recordedAt: warning.created_at
  };
}

/**
 * Summarize non-destructive storage recovery for the workspace status strip.
 *
 * Returns `null` when there is nothing to report, so the strip never occupies
 * layout space in the normal case.
 */
export function summarizeCopilotStorageRecovery(
  status: CopilotStorageStatus | null | undefined
): CopilotStorageRecoverySummary | null {
  const warnings = status?.warnings ?? [];
  if (!warnings.length) {
    return null;
  }
  const plural = warnings.length === 1 ? "" : "s";
  return {
    count: warnings.length,
    headline: `${warnings.length} storage record${plural} preserved`,
    explanation:
      `Copilot skipped or recovered ${warnings.length} local storage record${plural} and kept the original file${plural} for inspection. ` +
      "Nothing was deleted and your healthy sessions, turns, and artifacts remain usable.",
    details: warnings.map(toStorageWarningDetail)
  };
}
