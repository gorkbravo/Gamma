// Test and risk snapshots (Workstream 12, I3c): pure helpers for the Idea
// view's "Test and risk" section. The backend runs Strategy Lab and Risk on the
// idea's legs only when the user asks and keeps each run frozen with its date.

import type { IdeaRiskEpisode, IdeaRiskSnapshot, IdeaTestSnapshot } from "./api/types";

/** "1.10" for a ratio such as Sharpe or beta; "N/A" when absent. */
export function formatRatio(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return value.toFixed(2);
}

/** A loss figure shown as negative ("-2.10%") whatever sign the source used. */
export function asLoss(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return -Math.abs(value);
}

/** "AAPL +50% · MSFT -50%": the shares of gross exposure the snapshot was run on. */
export function snapshotLegsText(snapshot: IdeaTestSnapshot | IdeaRiskSnapshot): string {
  return snapshot.legs
    .map((leg) => {
      const share = Math.round((leg.weight ?? 0) * 100);
      return `${leg.entity.label} ${share > 0 ? "+" : ""}${share}%`;
    })
    .join(" · ");
}

/**
 * The worst episode the backend named, or as a fallback the lowest book return
 * among fully covered episodes (a partial one only when none is full: a partial
 * replay treats the legs without history as flat).
 */
export function worstEpisode(snapshot: IdeaRiskSnapshot): IdeaRiskEpisode | null {
  const priced = snapshot.episodes.filter((item) => item.status !== "unavailable" && item.book_return != null);
  const named = priced.find((item) => item.episode_id === snapshot.worst_episode_id);
  if (named) return named;
  const full = priced.filter((item) => item.status === "full");
  return (full.length ? full : priced).reduce<IdeaRiskEpisode | null>(
    (worst, item) => (worst == null || (item.book_return ?? 0) < (worst.book_return ?? 0) ? item : worst),
    null
  );
}

/** "Full", "Partial · 50% of gross" (the rest of the book is treated as flat), or "Partial". */
export function episodeCoverageText(episode: IdeaRiskEpisode): string {
  if (episode.status === "full") return "Full";
  if (episode.coverage == null || !Number.isFinite(episode.coverage)) return "Partial";
  return `Partial · ${Math.round(episode.coverage * 100)}% of gross`;
}

/** "2024-12-24 → 2026-01-27 · 286 observations". */
export function snapshotWindowText(snapshot: IdeaTestSnapshot | IdeaRiskSnapshot): string {
  const count = `${snapshot.observations} ${snapshot.observations === 1 ? "observation" : "observations"}`;
  if (!snapshot.window_start || !snapshot.window_end) return count;
  return `${snapshot.window_start} → ${snapshot.window_end} · ${count}`;
}
