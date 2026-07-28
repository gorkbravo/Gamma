import type {
  PredictionCalibrationCurve,
  PredictionCalibrationSummary,
  PredictionHistoryRange,
  PredictionMarket,
  PredictionMarketComparison,
  PredictionOutcomeSeries,
  PredictionPairAnalytics,
  PredictionProbabilityHistoryResponse
} from "./api/types";

// Retained only so the one-time migration can find what a previous build wrote.
// Saved research now lives in the backend store.
export const PREDICTION_WATCHLIST_STORAGE_KEY = "gamma.predictionMarkets.watchlist.v1";
export const PREDICTION_COMPARE_STORAGE_KEY = "gamma.predictionMarkets.compareBasket.v1";
export const PREDICTION_MIGRATION_FLAG_KEY = "gamma.predictionMarkets.serverMigration.v1";
/** Reserved set name holding the current working basket so it survives a browser change. */
export const PREDICTION_WORKING_BASKET_NAME = "Working basket";

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

/**
 * Lead times a calibration curve can be measured at, in hours. The ceiling is
 * a provider constraint mirrored from the backend: a longer lookback cannot be
 * requested as an explicit window ending at a contract's own resolution.
 */
export const CALIBRATION_LEAD_TIME_CHOICES: readonly { hours: number; label: string }[] = [
  { hours: 6, label: "T-6H" },
  { hours: 24, label: "T-1D" },
  { hours: 72, label: "T-3D" },
  { hours: 168, label: "T-7D" }
];

export const DEFAULT_CALIBRATION_LEAD_TIMES: readonly number[] = [24, 168];
export const MAX_CALIBRATION_LEAD_TIMES = 3;
/** Mirrors the backend default; smaller samples rarely clear the curve minimum. */
export const DEFAULT_CALIBRATION_SAMPLE = 80;
export const CALIBRATION_SAMPLE_CHOICES: readonly number[] = [20, 40, 80, 120];

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

export interface LegacyPredictionResearch {
  watchlist: PredictionWatchlistEntry[];
  comparison_basket: string[];
}

/**
 * Read what an older build persisted in this browser. Returns `null` once the
 * migration has already run, so a second load does not re-import records the
 * user has since deleted on the server.
 */
export function readLegacyResearch(): LegacyPredictionResearch | null {
  if (typeof localStorage === "undefined") {
    return null;
  }
  if (localStorage.getItem(PREDICTION_MIGRATION_FLAG_KEY)) {
    return null;
  }
  const watchlist = normalizeWatchlist(readStorage(PREDICTION_WATCHLIST_STORAGE_KEY));
  const comparison_basket = normalizeCompareSelection(readStorage(PREDICTION_COMPARE_STORAGE_KEY));
  if (!watchlist.length && !comparison_basket.length) {
    markLegacyResearchMigrated();
    return null;
  }
  return { watchlist, comparison_basket };
}

export function markLegacyResearchMigrated() {
  writeStorage(PREDICTION_MIGRATION_FLAG_KEY, new Date().toISOString());
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

/**
 * Add or remove a calibration lead time. At least one must stay selected and
 * the count is capped, because each lead time is a separate measurement the
 * backend has to sample.
 */
export function toggleCalibrationLeadTime(selected: number[], hours: number): number[] {
  if (selected.includes(hours)) {
    return selected.length <= 1 ? selected : selected.filter((value) => value !== hours);
  }
  if (selected.length >= MAX_CALIBRATION_LEAD_TIMES) {
    return selected;
  }
  return [...selected, hours].sort((left, right) => left - right);
}

export interface CalibrationBucketRow {
  label: string;
  sample_size: number;
  meets_minimum: boolean;
  predicted: number | null;
  realized: number | null;
  error: number | null;
}

/** Flatten a curve into table rows, carrying the per-bucket minimum forward. */
export function buildCalibrationRows(curve: PredictionCalibrationCurve | null): CalibrationBucketRow[] {
  if (!curve) {
    return [];
  }
  return curve.buckets.map((bucket) => ({
    label: bucket.label,
    sample_size: bucket.sample_size,
    meets_minimum: bucket.meets_minimum,
    predicted: bucket.average_probability,
    realized: bucket.realized_frequency,
    error:
      bucket.realized_frequency == null || bucket.average_probability == null
        ? null
        : bucket.realized_frequency - bucket.average_probability
  }));
}

/**
 * Curve to show for a lead time. With no explicit selection, prefer one that
 * cleared the minimum: opening on a withheld curve makes a measured result look
 * like a failed one.
 */
export function calibrationCurveFor(
  summary: PredictionCalibrationSummary | null,
  leadHours: number | null
): PredictionCalibrationCurve | null {
  if (!summary?.curves?.length) {
    return null;
  }
  const requested = summary.curves.find((curve) => curve.lead_time_hours === leadHours);
  if (requested) {
    return requested;
  }
  return summary.curves.find((curve) => curve.is_plottable) ?? summary.curves[0];
}

/**
 * One line stating what the number actually is. A summary built from the
 * deprecated settlement path must never read like a calibration result.
 */
export function describeCalibrationMethod(summary: PredictionCalibrationSummary | null): string {
  if (!summary) {
    return "No calibration loaded";
  }
  if (summary.method !== "lead_time_history") {
    return "UNVALIDATED - settlement print only, no curve measured";
  }
  const leads = summary.curves.map((curve) => curve.label).join(" / ") || "no lead time";
  const plottable = summary.curves.filter((curve) => curve.is_plottable).length;
  return `Lead-time history | ${leads} | n=${summary.sample_size} | ${plottable}/${summary.curves.length} above minimum`;
}

export function comparisonLegLabel(comparison: PredictionMarketComparison | null, marketId: string): string {
  const leg = comparison?.legs.find((item) => item.market_id === marketId);
  if (!leg) {
    return marketId;
  }
  return leg.title;
}
