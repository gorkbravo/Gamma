// Close and review (Workstream 12, I3b): pure helpers for the close form, the
// review section of a closed idea and the Review mode. Statistics describe the
// user's own record only; nothing here scores an idea.

import type {
  IdeaClosePayload,
  IdeaEvidenceVerdict,
  IdeaReviewOutcome,
  IdeaReviewStatsResponse,
} from "./api/types";

export const REVIEW_OUTCOMES: readonly IdeaReviewOutcome[] = ["confirmed", "invalidated", "abandoned", "expired"];

export const REVIEW_OUTCOME_LABELS: Record<IdeaReviewOutcome, string> = {
  confirmed: "Confirmed",
  invalidated: "Invalidated",
  abandoned: "Abandoned",
  expired: "Expired",
};

export const EVIDENCE_VERDICTS: readonly IdeaEvidenceVerdict[] = ["held", "failed", "unclear"];

export const EVIDENCE_VERDICT_LABELS: Record<IdeaEvidenceVerdict, string> = {
  held: "Held up",
  failed: "Failed",
  unclear: "Unclear",
};

/** The outcome is the user's judgment of the thesis: a status, coloured like one. */
export function outcomeTone(outcome: IdeaReviewOutcome): "" | "positive" | "negative" {
  if (outcome === "confirmed") return "positive";
  if (outcome === "invalidated") return "negative";
  return "";
}

export function verdictTone(verdict: IdeaEvidenceVerdict): "" | "positive" | "negative" {
  if (verdict === "held") return "positive";
  if (verdict === "failed") return "negative";
  return "";
}

/** "12 days", "1 day", "under a day", "N/A". */
export function formatHoldingDays(days: number | null | undefined): string {
  if (days == null || !Number.isFinite(days)) return "N/A";
  if (days < 1) return "Under a day";
  const rounded = Math.round(days);
  return `${rounded} ${rounded === 1 ? "day" : "days"}`;
}

/** "1 of 2 (50%)", or "None" when there is no sample. */
export function shareText(part: number, whole: number): string {
  if (!whole) return "None";
  return `${part} of ${whole} (${Math.round((part / whole) * 100)}%)`;
}

export interface CloseDraft {
  outcome: IdeaReviewOutcome | null;
  expected: string;
  realizedNote: string;
  lesson: string;
  verdicts: Record<string, IdeaEvidenceVerdict | "">;
}

/** Why the close form cannot be submitted yet, or "" when it can. */
export function closeDraftError(draft: CloseDraft): string {
  if (!draft.outcome) return "Choose an outcome.";
  if (draft.lesson.trim().length < 3) return "Write the lesson: closing needs a review.";
  return "";
}

/** The POST body: blank verdicts are left out; a blank expectation lets the server use the thesis. */
export function closePayload(draft: CloseDraft): IdeaClosePayload | null {
  if (closeDraftError(draft) || !draft.outcome) return null;
  const verdicts = Object.fromEntries(
    Object.entries(draft.verdicts).filter((entry): entry is [string, IdeaEvidenceVerdict] => Boolean(entry[1]))
  );
  return {
    outcome: draft.outcome,
    lesson: draft.lesson.trim(),
    expected: draft.expected.trim() || null,
    realized_note: draft.realizedNote.trim(),
    evidence_verdicts: verdicts,
  };
}

/** Review mode header blocks: counts first, then the record's medians with their sample size. */
export function reviewKpis(stats: IdeaReviewStatsResponse | null) {
  const outcomes = stats?.outcomes;
  return {
    reviewed: stats?.rows.length ?? 0,
    confirmed: outcomes?.confirmed ?? 0,
    invalidated: outcomes?.invalidated ?? 0,
    abandoned: outcomes?.abandoned ?? 0,
    expired: outcomes?.expired ?? 0,
  };
}
