// Idea drafts proposed by Copilot (Workstream 12, I5): pure helpers for the
// proposal card. The backend validates and stores each proposal; the card
// only reads the payload and sends the user's decision.

import type { CopilotDraftMutation, CopilotResearchCardResult } from "./api/types";

/** Idea proposals of a result, inline ones first, then fetched ones (after a session reload). */
export function proposalsForResult(result: CopilotResearchCardResult, fetched: CopilotDraftMutation[]): CopilotDraftMutation[] {
  const rows = [...(result.proposals ?? []), ...fetched].filter((item) => item.domain === "ideas");
  const seen = new Set<string>();
  return rows.filter((item) => (seen.has(item.mutation_id) ? false : (seen.add(item.mutation_id), true)));
}

export function proposalStatusLabel(status: string): string {
  return (
    {
      pending: "Awaiting your decision",
      applied: "Draft idea created",
      rejected: "Rejected",
      expired: "Expired",
      failed: "Not created",
      confirmed: "Creating",
    } as Record<string, string>
  )[status] ?? status;
}

/** "Exxon Mobil −1 · US Oil Fund +1" from the proposal's legs. */
export function proposalLegs(payload: Record<string, unknown>): string {
  const legs = Array.isArray(payload.legs) ? (payload.legs as Array<Record<string, unknown>>) : [];
  return legs
    .map((leg) => {
      const weight = leg.weight == null ? "" : ` ${Number(leg.weight) > 0 ? "+" : ""}${Number(leg.weight)}`;
      return `${String(leg.label ?? leg.symbol ?? "")}${weight}`;
    })
    .join(" · ");
}

export function proposalCriteria(payload: Record<string, unknown>): Array<{ kind: string; label: string; rationale: string }> {
  const rows = Array.isArray(payload.criteria) ? (payload.criteria as Array<Record<string, unknown>>) : [];
  const kinds: Record<string, string> = { invalidate: "Invalidate", confirm: "Confirm", review: "Review" };
  return rows.map((row) => ({
    kind: kinds[String(row.kind)] ?? String(row.kind ?? ""),
    label: String(row.label ?? ""),
    rationale: String(row.rationale ?? ""),
  }));
}
