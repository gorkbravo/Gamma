import type {
  PredictionHistoryRange,
  PredictionMarket,
  PredictionMarketComparison,
  PredictionOutcomeSeries,
  PredictionPairAnalytics,
  PredictionProbabilityHistoryResponse
} from "./api/types";

export const PREDICTION_WATCHLIST_STORAGE_KEY = "gamma.predictionMarkets.watchlist.v1";
export const PREDICTION_COMPARE_STORAGE_KEY = "gamma.predictionMarkets.compareBasket.v1";

export const MAX_WATCHLIST_ENTRIES = 40;
export const MAX_COMPARE_LEGS = 6;

export const HISTORY_RANGES: readonly { id: PredictionHistoryRange; label: string }[] = [
  { id: "1d", label: "1D" },
  { id: "1w", label: "1W" },
  { id: "1m", label: "1M" },
  { id: "3m", label: "3M" },
  { id: "6m", label: "6M" },
  { id: "1y", label: "1Y" },
  { id: "max", label: "MAX" }
];

/** `null` means "let the backend pick a resolution from the window span". */
export const RESOLUTION_CHOICES: readonly { id: number | null; label: string }[] = [
  { id: null, label: "AUTO" },
  { id: 5, label: "5M" },
  { id: 15, label: "15M" },
  { id: 60, label: "1H" },
  { id: 360, label: "6H" },
  { id: 1440, label: "1D" }
];

export interface PredictionWatchlistEntry {
  market_id: string;
  venue: string;
  title: string;
  probability: number | null;
  added_at: string;
}

function readStorage(key: string): unknown {
  if (typeof localStorage === "undefined") {
    return null;
  }
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: unknown) {
  if (typeof localStorage === "undefined") {
    return;
  }
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // A full or unavailable store must not break the view.
  }
}

function isWatchlistEntry(value: unknown): value is PredictionWatchlistEntry {
  if (!value || typeof value !== "object") {
    return false;
  }
  const entry = value as Record<string, unknown>;
  return typeof entry.market_id === "string" && entry.market_id.length > 0 && typeof entry.venue === "string";
}

export function normalizeWatchlist(value: unknown): PredictionWatchlistEntry[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const entries: PredictionWatchlistEntry[] = [];
  for (const candidate of value) {
    if (!isWatchlistEntry(candidate) || seen.has(candidate.market_id)) {
      continue;
    }
    seen.add(candidate.market_id);
    entries.push({
      market_id: candidate.market_id,
      venue: candidate.venue,
      title: typeof candidate.title === "string" ? candidate.title : candidate.market_id,
      probability: typeof candidate.probability === "number" ? candidate.probability : null,
      added_at: typeof candidate.added_at === "string" ? candidate.added_at : new Date().toISOString()
    });
    if (entries.length >= MAX_WATCHLIST_ENTRIES) {
      break;
    }
  }
  return entries;
}

export function loadWatchlist(): PredictionWatchlistEntry[] {
  return normalizeWatchlist(readStorage(PREDICTION_WATCHLIST_STORAGE_KEY));
}

export function saveWatchlist(entries: PredictionWatchlistEntry[]) {
  writeStorage(PREDICTION_WATCHLIST_STORAGE_KEY, entries.slice(0, MAX_WATCHLIST_ENTRIES));
}

export function toggleWatchlistEntry(
  entries: PredictionWatchlistEntry[],
  market: PredictionMarket
): PredictionWatchlistEntry[] {
  const existing = entries.some((entry) => entry.market_id === market.market_id);
  if (existing) {
    return entries.filter((entry) => entry.market_id !== market.market_id);
  }
  return [
    {
      market_id: market.market_id,
      venue: market.venue,
      title: market.title,
      probability: market.current_probability,
      added_at: new Date().toISOString()
    },
    ...entries
  ].slice(0, MAX_WATCHLIST_ENTRIES);
}

export function normalizeCompareSelection(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  for (const candidate of value) {
    if (typeof candidate === "string" && candidate.length > 0) {
      seen.add(candidate);
    }
    if (seen.size >= MAX_COMPARE_LEGS) {
      break;
    }
  }
  return [...seen];
}

export function loadCompareSelection(): string[] {
  return normalizeCompareSelection(readStorage(PREDICTION_COMPARE_STORAGE_KEY));
}

export function saveCompareSelection(marketIds: string[]) {
  writeStorage(PREDICTION_COMPARE_STORAGE_KEY, marketIds.slice(0, MAX_COMPARE_LEGS));
}

/**
 * Add or remove a contract from the comparison basket.
 * Returns the unchanged list when the cap is already reached so the caller can
 * detect the no-op and explain it.
 */
export function toggleCompareSelection(selection: string[], marketId: string): string[] {
  if (selection.includes(marketId)) {
    return selection.filter((id) => id !== marketId);
  }
  if (selection.length >= MAX_COMPARE_LEGS) {
    return selection;
  }
  return [...selection, marketId];
}

export function formatResolution(minutes: number | null | undefined): string {
  if (minutes == null) {
    return "auto";
  }
  if (minutes >= 1440) {
    return `${Math.round(minutes / 1440)}d`;
  }
  if (minutes >= 60) {
    return `${Math.round(minutes / 60)}h`;
  }
  return `${minutes}m`;
}

/**
 * One-line description of what the chart is actually showing, so a short series
 * inside a long requested window reads as coverage rather than as a bug.
 */
export function describeHistoryCoverage(history: PredictionProbabilityHistoryResponse | null): string {
  if (!history || !history.points.length) {
    return "No history";
  }
  const stats = history.stats;
  const span = stats?.span_days;
  const spanLabel =
    span == null ? "unknown span" : span < 1 ? `${Math.round(span * 24)}h` : `${span.toFixed(span < 10 ? 1 : 0)}d`;
  return `${history.points.length} pts | ${spanLabel} | ${formatResolution(history.effective_resolution_minutes)} bars`;
}

const COMPARISON_COLORS = [
  "var(--chart-primary)",
  "var(--chart-secondary)",
  "var(--positive)",
  "var(--chart-negative)",
  "var(--text-1)",
  "var(--warning)"
];

export function comparisonColor(index: number): string {
  return COMPARISON_COLORS[index % COMPARISON_COLORS.length];
}

/** Rank pairs so the widest current dislocation is inspected first. */
export function sortPairsByDislocation(pairs: PredictionPairAnalytics[]): PredictionPairAnalytics[] {
  return [...pairs].sort((left, right) => {
    const leftSpread = left.current_spread == null ? -1 : Math.abs(left.current_spread);
    const rightSpread = right.current_spread == null ? -1 : Math.abs(right.current_spread);
    return rightSpread - leftSpread;
  });
}

export interface OutcomeLadderRow {
  outcome_id: string;
  label: string;
  probability: number | null;
  change: number | null;
  points: number;
  hasHistory: boolean;
}

/**
 * Flatten per-outcome series into a table-ready ladder. Multi-outcome markets
 * are the reason this exists: charting only the first outcome hides the rest of
 * the book.
 */
export function buildOutcomeLadder(series: PredictionOutcomeSeries[]): OutcomeLadderRow[] {
  return series
    .map((item) => {
      const points = item.points;
      const change =
        points.length > 1 ? points[points.length - 1].probability - points[0].probability : null;
      return {
        outcome_id: item.outcome_id,
        label: item.label,
        probability: item.probability ?? (points.length ? points[points.length - 1].probability : null),
        change,
        points: points.length,
        hasHistory: points.length > 0
      };
    })
    .sort((left, right) => (right.probability ?? -1) - (left.probability ?? -1));
}

export function comparisonLegLabel(comparison: PredictionMarketComparison | null, marketId: string): string {
  const leg = comparison?.legs.find((item) => item.market_id === marketId);
  if (!leg) {
    return marketId;
  }
  return leg.title;
}
