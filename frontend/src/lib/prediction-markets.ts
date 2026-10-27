import type {
  CopilotWorkingAnalysis,
  PredictionCalibrationCurve,
  PredictionCalibrationSummary,
  PredictionEventBook,
  PredictionEventBookLeg,
  PredictionHistoryRange,
  PredictionMarket,
  PredictionMarketComparison,
  PredictionOutcomeSeries,
  PredictionPairAnalytics,
  PredictionProbabilityHistoryResponse,
  RelatedPredictionMarket
} from "./api/types";
import { resolveWorkingAnalysisTarget } from "./copilot-workspace";

/** Retained evidence is independent of the tab's live basket and saved sets. */
export function predictionComparisonFromWorkingAnalysis(analysis: CopilotWorkingAnalysis | null, now = Date.now()) {
  if (!analysis || resolveWorkingAnalysisTarget(analysis)?.tab !== "prediction_markets") return null;
  if (!analysis.expires_at || !Number.isFinite(Date.parse(analysis.expires_at)) || Date.parse(analysis.expires_at) <= now) return null;
  const inputs = analysis.inputs;
  const ids = inputs.market_ids;
  const comparison = analysis.outputs.comparison as PredictionMarketComparison | undefined;
  if (
    !Array.isArray(ids) || ids.length < 2 || ids.length > MAX_COMPARE_LEGS ||
    ids.some((id) => typeof id !== "string") || new Set(ids).size !== ids.length ||
    !comparison || !Array.isArray(comparison.legs) || !Array.isArray(comparison.pairs) ||
    comparison.legs.length < 2 || comparison.legs.some((leg) => !ids.includes(leg.market_id) || !Array.isArray(leg.points)) ||
    comparison.pairs.some((pair) => !Array.isArray(pair.spread_series)) ||
    !HISTORY_RANGES.some((range) => range.id === inputs.range) || comparison.requested_range !== inputs.range
  ) return null;
  return {
    comparison, marketIds: ids as string[], range: inputs.range as PredictionHistoryRange,
    resolutionMinutes: inputs.resolution_minutes as number | null,
  };
}

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

// ── Event Book: escaleras acumulativas ─────────────────────────────────

export interface EventBookLadderSummary {
  label: "Date ladder" | "Threshold ladder";
  /** Regla de monotonicidad que comprueba el backend. */
  rule: string;
  inversions: number;
  /** Primer y último peldaño cotizados, en el orden de la escalera. */
  first: PredictionEventBookLeg | null;
  last: PredictionEventBookLeg | null;
}

/**
 * Resumen de un Event Book que es una escalera ("by Dec 31 / by Jun 30",
 * "above 72k / above 74k"). Sus peldaños están anidados, así que no hay suma,
 * overround ni favorito; `null` cuando el libro no es una escalera.
 */
export function eventBookLadderSummary(book: PredictionEventBook | null | undefined): EventBookLadderSummary | null {
  if (!book || book.exclusivity_signal !== "cumulative_ladder") return null;
  const priced = book.legs.filter((leg) => leg.probability != null);
  const isDate = book.ladder_kind === "date";
  return {
    label: isDate ? "Date ladder" : "Threshold ladder",
    rule: isDate ? "later ≥ earlier" : "nested levels",
    inversions: book.ladder_inversions ?? 0,
    first: priced[0] ?? null,
    last: priced.at(-1) ?? null
  };
}

// ── Agrupación por evento y hermanos (GUA-20261021-15) ─────────────────

export type BucketBounds = readonly [number, number];

// Misma lectura que el resolver del backend: "20-24", "fewer than 20",
// "40 or more", "70° to 71°". Gana la coincidencia más temprana del texto.
const BUCKET_NUMBER = String.raw`\$?\d[\d,]*(?:\.\d+)?`;
const BUCKET_UNIT = String.raw`\s*[%°]?`;
const BUCKET_PATTERNS: readonly { kind: "range" | "below" | "above"; pattern: RegExp }[] = [
  {
    kind: "range",
    pattern: new RegExp(String.raw`(${BUCKET_NUMBER})${BUCKET_UNIT}\s*(?:-|–|—|to|and)\s*(${BUCKET_NUMBER})`, "i")
  },
  {
    kind: "below",
    pattern: new RegExp(
      String.raw`(?:\b(?:fewer than|less than|under|below|at most|no more than|up to)|<=?|≤|↓)\s*(${BUCKET_NUMBER})`,
      "i"
    )
  },
  { kind: "below", pattern: new RegExp(String.raw`(${BUCKET_NUMBER})${BUCKET_UNIT}\s*or (?:fewer|less|below|lower)`, "i") },
  {
    // ↑/↓ son las etiquetas de Polymarket para "toca el nivel" ("↑ 95,000").
    kind: "above",
    pattern: new RegExp(String.raw`(?:\b(?:more than|greater than|over|above|at least)|>=?|≥|↑)\s*(${BUCKET_NUMBER})`, "i")
  },
  {
    kind: "above",
    pattern: new RegExp(String.raw`(${BUCKET_NUMBER})${BUCKET_UNIT}\s*(?:\+|or (?:more|above|higher|greater))`, "i")
  }
];

function bucketNumber(text: string): number | null {
  const value = Number(text.replace(/[$,]/g, ""));
  return Number.isFinite(value) ? value : null;
}

/** (inferior, superior) de una etiqueta de bucket; los extremos abiertos son ±Infinity. */
export function parseBucketBounds(text: string | null | undefined): BucketBounds | null {
  const source = String(text ?? "");
  let best: { start: number; length: number; bounds: BucketBounds } | null = null;
  for (const { kind, pattern } of BUCKET_PATTERNS) {
    const match = pattern.exec(source);
    if (!match) continue;
    let bounds: BucketBounds;
    if (kind === "range") {
      const left = bucketNumber(match[1]);
      const right = bucketNumber(match[2]);
      if (left == null || right == null) continue;
      bounds = [Math.min(left, right), Math.max(left, right)];
    } else {
      const value = bucketNumber(match[1]);
      if (value == null) continue;
      bounds = kind === "below" ? [-Infinity, value] : [value, Infinity];
    }
    const candidate = { start: match.index, length: match[0].length, bounds };
    if (!best || candidate.start < best.start || (candidate.start === best.start && candidate.length > best.length)) {
      best = candidate;
    }
  }
  return best?.bounds ?? null;
}

/** La etiqueta de grupo del venue manda; el título solo si no hay etiqueta legible. */
export function marketBucketBounds(market: Pick<PredictionMarket, "subtitle" | "title">): BucketBounds | null {
  return parseBucketBounds(market.subtitle) ?? parseBucketBounds(market.title);
}

/**
 * `buckets`: rangos numéricos sin solape, excluyentes por estructura.
 * `candidates`: una etiqueta distinta por leg y misma fecha de resolución.
 * `unverified`: escalera de fechas o umbrales; la suma es solo descriptiva.
 */
export type PredictionEventGroupKind = "buckets" | "candidates" | "unverified";

export interface PredictionEventGroupLeg {
  market: PredictionMarket;
  label: string;
  probability: number | null;
  /** Altura de la barra de distribución relativa al leg más probable (0-1). */
  share: number;
  isMode: boolean;
}

export interface PredictionEventGroup {
  key: string;
  eventId: string;
  eventTitle: string;
  venue: string;
  kind: PredictionEventGroupKind;
  /** `complete` solo cuando los buckets visibles cubren la recta sin huecos. */
  coverage: "complete" | "partial" | "unknown";
  legs: PredictionEventGroupLeg[];
  pricedLegs: number;
  probabilitySum: number | null;
  /** Σ − 100% solo cuando el libro visible es excluyente, completo y todo cotizado. */
  overround: number | null;
  mode: PredictionEventGroupLeg | null;
  volume24h: number | null;
  volume: number | null;
  liquidity: number | null;
  soonestEnd: string | null;
  worstFreshness: string | null;
}

export type PredictionScreenerEntry =
  | { type: "market"; key: string; market: PredictionMarket }
  | { type: "group"; key: string; group: PredictionEventGroup };

const CANDIDATE_RESOLUTION_DRIFT_MS = 3 * 86_400_000;
const FRESHNESS_RANK: Record<string, number> = { fresh: 0, delayed: 1, closed: 1, stale: 2, broken: 3 };

function endMs(market: PredictionMarket): number {
  const parsed = market.end_time ? Date.parse(market.end_time) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function sumOrNull(values: (number | null | undefined)[]): number | null {
  const present = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return present.length ? present.reduce((total, value) => total + value, 0) : null;
}

function legLabel(market: PredictionMarket): string {
  return market.subtitle?.trim() || market.title;
}

function classifyEventLegs(members: PredictionMarket[]): {
  kind: PredictionEventGroupKind;
  coverage: PredictionEventGroup["coverage"];
  ordered: PredictionMarket[];
} {
  const bounds = members.map((market) => marketBucketBounds(market));
  if (bounds.every((value): value is BucketBounds => value != null)) {
    const keyed = members.map((market, index) => ({ market, bounds: bounds[index] as BucketBounds }));
    keyed.sort((left, right) => left.bounds[0] - right.bounds[0] || left.bounds[1] - right.bounds[1]);
    const distinct = new Set(keyed.map((item) => item.bounds.join(":"))).size === keyed.length;
    // Rangos que se tocan (0-5 / 5-10) son excluyentes; "above 3" y "above 3.5" no.
    const exclusive = keyed.every((item, index) => index === 0 || keyed[index - 1].bounds[1] <= item.bounds[0]);
    if (distinct) {
      const ordered = keyed.map((item) => item.market);
      if (!exclusive) return { kind: "unverified", coverage: "unknown", ordered };
      // Buckets enteros (20-24 / 25-29) dejan un hueco de 1; uno mayor es un bucket que falta en la vista.
      const contiguous = keyed.every((item, index) => index === 0 || item.bounds[0] - keyed[index - 1].bounds[1] <= 1);
      const first = keyed[0].bounds[0];
      const last = keyed[keyed.length - 1].bounds[1];
      const closedEnds = (first === -Infinity || first === 0) && last === Infinity;
      return { kind: "buckets", coverage: contiguous && closedEnds ? "complete" : "partial", ordered };
    }
  }
  const labels = members.map((market) => market.subtitle?.trim().toLowerCase() ?? "");
  const ends = members.map(endMs).filter(Number.isFinite);
  const sameResolution = ends.length === members.length && Math.max(...ends) - Math.min(...ends) <= CANDIDATE_RESOLUTION_DRIFT_MS;
  if (labels.every(Boolean) && new Set(labels).size === labels.length && sameResolution) {
    const ordered = [...members].sort((left, right) => (right.current_probability ?? -1) - (left.current_probability ?? -1));
    return { kind: "candidates", coverage: "unknown", ordered };
  }
  const ordered = [...members].sort(
    (left, right) => endMs(left) - endMs(right) || (right.current_probability ?? -1) - (left.current_probability ?? -1)
  );
  return { kind: "unverified", coverage: "unknown", ordered };
}

export function buildEventGroup(members: PredictionMarket[]): PredictionEventGroup {
  const { kind, coverage, ordered } = classifyEventLegs(members);
  const priced = ordered.filter((market) => market.current_probability != null);
  const maxProbability = Math.max(0, ...priced.map((market) => market.current_probability as number));
  let modeIndex = -1;
  ordered.forEach((market, index) => {
    const probability = market.current_probability;
    if (probability != null && (modeIndex < 0 || probability > (ordered[modeIndex].current_probability ?? -1))) {
      modeIndex = index;
    }
  });
  const legs = ordered.map((market, index) => ({
    market,
    label: legLabel(market),
    probability: market.current_probability,
    share: maxProbability > 0 && market.current_probability != null ? market.current_probability / maxProbability : 0,
    isMode: index === modeIndex
  }));
  const probabilitySum = sumOrNull(ordered.map((market) => market.current_probability));
  const anchor = ordered[0];
  const worst = ordered
    .map((market) => market.freshness?.status ?? null)
    .filter((status): status is string => Boolean(status))
    .sort((left, right) => (FRESHNESS_RANK[right] ?? 1) - (FRESHNESS_RANK[left] ?? 1))[0] ?? null;
  const soonest = [...ordered].sort((left, right) => endMs(left) - endMs(right))[0];
  return {
    key: `${anchor.venue}|${anchor.event_id}`,
    eventId: anchor.event_id ?? anchor.market_id,
    eventTitle: anchor.event_title?.trim() || anchor.title,
    venue: anchor.venue,
    kind,
    coverage,
    legs,
    pricedLegs: priced.length,
    probabilitySum,
    overround:
      kind === "buckets" && coverage === "complete" && priced.length === ordered.length && probabilitySum != null
        ? probabilitySum - 1
        : null,
    mode: modeIndex >= 0 ? legs[modeIndex] : null,
    volume24h: sumOrNull(ordered.map((market) => market.volume_24h)),
    volume: sumOrNull(ordered.map((market) => market.volume)),
    liquidity: sumOrNull(ordered.map((market) => market.liquidity)),
    soonestEnd: soonest?.end_time ?? null,
    worstFreshness: worst
  };
}

/**
 * Agrupa las filas del screener que comparten evento del venue. El grupo ocupa
 * la posición de su primer miembro, así el ranking del screener se conserva;
 * los contratos sin hermanos en la vista siguen como filas sueltas.
 */
export function groupScreenerMarkets(markets: PredictionMarket[]): PredictionScreenerEntry[] {
  const eventKey = (market: PredictionMarket) => (market.event_id ? `${market.venue}|${market.event_id}` : null);
  const members = new Map<string, PredictionMarket[]>();
  for (const market of markets) {
    const key = eventKey(market);
    if (key) members.set(key, [...(members.get(key) ?? []), market]);
  }
  const entries: PredictionScreenerEntry[] = [];
  const emitted = new Set<string>();
  for (const market of markets) {
    const key = eventKey(market);
    const group = key ? members.get(key) : undefined;
    if (!key || !group || group.length < 2) {
      entries.push({ type: "market", key: market.market_id, market });
      continue;
    }
    if (emitted.has(key)) continue;
    emitted.add(key);
    entries.push({ type: "group", key, group: buildEventGroup(group) });
  }
  return entries;
}

export function flatScreenerEntries(markets: PredictionMarket[]): PredictionScreenerEntry[] {
  return markets.map((market) => ({ type: "market", key: market.market_id, market }));
}

export interface RelatedMarketSection {
  id: "analog" | "same_event" | "same_series";
  label: string;
  groupTitle: string | null;
  rows: RelatedPredictionMarket[];
}

const bySiblingOrder = (left: RelatedPredictionMarket, right: RelatedPredictionMarket) =>
  (left.sibling_order ?? Number.MAX_SAFE_INTEGER) - (right.sibling_order ?? Number.MAX_SAFE_INTEGER);

/**
 * Secciones del panel RELATED: los análogos en el orden del backend y, aparte,
 * los hermanos de evento (orden de bucket) y de serie (fecha de resolución).
 */
export function groupRelatedMarkets(rows: RelatedPredictionMarket[]): RelatedMarketSection[] {
  const analogs = rows.filter((row) => !row.sibling_scope);
  const sameEvent = rows.filter((row) => row.sibling_scope === "same_event").sort(bySiblingOrder);
  const sameSeries = rows.filter((row) => row.sibling_scope === "same_series").sort(bySiblingOrder);
  const sections: RelatedMarketSection[] = [
    { id: "analog", label: "Analogs", groupTitle: null, rows: analogs },
    { id: "same_event", label: "Same event", groupTitle: sameEvent[0]?.group_title ?? null, rows: sameEvent },
    { id: "same_series", label: "Same series", groupTitle: sameSeries[0]?.group_title ?? null, rows: sameSeries }
  ];
  return sections.filter((section) => section.rows.length > 0);
}
