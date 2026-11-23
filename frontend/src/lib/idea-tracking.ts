// Hypothetical forward tracking (Workstream 12, I3a): pure helpers for the
// Idea view's tracking panel and the Board column. The backend rebuilds the
// canonical daily series from provider closes; this module only formats it.
// Gaps stay gaps here too: a gap session becomes a break in the chart line.

import type { UTCTimestamp } from "lightweight-charts";
import type {
  IdeaSummary,
  IdeaTrackingCostClass,
  IdeaTrackingCostClassView,
  IdeaTrackingResponse,
  IdeaTrackingSegment,
  IdeaTrackingSegmentStatus,
  IdeaTrackingStatus,
} from "./api/types";

export const TRACKING_LABEL = "Hypothetical, not executed";

export const TRACKING_STATUS_LABELS: Record<IdeaTrackingStatus, string> = {
  not_started: "Not started",
  waiting: "Waiting for the first close",
  tracking: "Tracking",
  stopped: "Stopped",
  unavailable: "Unavailable",
};

export const SEGMENT_STATUS_LABELS: Record<IdeaTrackingSegmentStatus, string> = {
  untracked: "Not tracked",
  unavailable: "Unavailable",
  waiting: "Waiting",
  never_entered: "Never entered",
  tracking: "Open",
  exiting: "Exiting",
  closed: "Closed",
};

export const SEGMENT_START_LABELS: Record<string, string> = {
  activated: "Activated",
  legs_edited: "Legs edited",
  legs_added: "Legs added",
  restored: "Restored",
  reopened: "Reopened",
  migrated: "Tracking began",
  signal_attached: "Signal attached",
  signal_changed: "Signal changed",
  signal_detached: "Signal detached",
};

/** "Signal changed 2026-01-20 15:00 · ended … · rebalanced, turnover 79%": the segment's history line. */
export function segmentNoteText(segment: IdeaTrackingSegment, formatInstant: (value: string) => string): string {
  const parts = [`${SEGMENT_START_LABELS[segment.start_reason] ?? segment.start_reason.replace(/_/g, " ")} ${formatInstant(segment.started_at)}`];
  if (segment.ended_at) parts.push(`ended ${formatInstant(segment.ended_at)}`);
  if (segment.rebalanced && segment.turnover != null) parts.push(`rebalanced, turnover ${Math.round(segment.turnover * 100)}%`);
  if (segment.gaps) parts.push(`${segment.gaps} ${segment.gaps === 1 ? "gap" : "gaps"}`);
  return parts.join(" · ");
}

export const COST_CLASS_SHORT_LABELS: Record<IdeaTrackingCostClass, string> = {
  us_equity_liquid: "Liquid US equity",
  equity_other: "Other equity",
  futures: "Futures",
  options: "Options",
  crypto_spot: "Spot crypto",
  prediction_contract: "Prediction",
  non_tradable: "Not tradable",
};

/** Classes a tracked leg can be moved to: the ones with a stated cost. */
export const LEG_COST_CLASSES: readonly IdeaTrackingCostClass[] = ["us_equity_liquid", "equity_other", "futures", "crypto_spot"];

/** "+2.35%" with its sign, "N/A" when absent. */
export function formatTrackingReturn(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  const percent = value * 100;
  const rounded = Number(percent.toFixed(digits));
  if (rounded === 0) return `${(0).toFixed(digits)}%`;
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(digits)}%`;
}

/** A cost is a drag: shown as a negative return ("−0.10%"). */
export function formatCostDrag(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return formatTrackingReturn(-Math.abs(value));
}

export function returnTone(value: number | null | undefined): "" | "positive" | "negative" {
  if (value == null || !Number.isFinite(value)) return "";
  const rounded = Number((value * 100).toFixed(2));
  if (rounded > 0) return "positive";
  if (rounded < 0) return "negative";
  return "";
}

export function formatBp(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "From quote";
  return `${Number(value.toFixed(2))} bp`;
}

/** Signed share of gross exposure: "+50%", "−50%". */
export function formatWeightShare(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "No weight";
  const percent = Math.round(value * 100);
  return `${percent > 0 ? "+" : ""}${percent}%`;
}

export interface BoardTrackingCell {
  text: string;
  tone: "" | "positive" | "negative";
  absent: boolean;
  meta: string;
  title: string;
}

/** The Board's "since activation" cell: the last computed headline with its session date. */
export function boardTrackingCell(row: Pick<IdeaSummary, "tracking">): BoardTrackingCell {
  const headline = row.tracking;
  if (!headline) {
    return { text: "Not tracked", tone: "", absent: true, meta: "", title: "Tracking starts when an idea with legs is activated." };
  }
  const snapshot = headline.snapshot;
  if (!snapshot) {
    return {
      text: "Not computed",
      tone: "",
      absent: true,
      meta: "",
      title: `${TRACKING_LABEL}. Open the idea to rebuild its series.`,
    };
  }
  if (snapshot.net_return == null) {
    return {
      text: TRACKING_STATUS_LABELS[snapshot.status] ?? snapshot.status,
      tone: "",
      absent: true,
      meta: "",
      title: `${TRACKING_LABEL}.`,
    };
  }
  const parts = [`as of ${snapshot.as_of ?? "N/A"}`];
  if (snapshot.stale_since) parts.push("provider stopped");
  if (snapshot.gaps) parts.push(`${snapshot.gaps} ${snapshot.gaps === 1 ? "gap" : "gaps"}`);
  if (snapshot.partial) parts.push("partial");
  if (snapshot.status === "stopped") parts.push("stopped");
  return {
    text: formatTrackingReturn(snapshot.net_return),
    tone: returnTone(snapshot.net_return),
    absent: false,
    meta: parts.join(" · "),
    title:
      `${TRACKING_LABEL}. Net of costs, chained across ${headline.segments} ` +
      `${headline.segments === 1 ? "segment" : "segments"}; ${snapshot.sessions} sessions` +
      (snapshot.benchmark && snapshot.benchmark_return != null
        ? `; ${snapshot.benchmark} ${formatTrackingReturn(snapshot.benchmark_return)}.`
        : "."),
  };
}

/** A session date (YYYY-MM-DD) as the UTC midnight timestamp the chart expects. */
export function sessionTime(session: string): UTCTimestamp {
  const [year, month, day] = session.split("-").map(Number);
  return (Date.UTC(year, month - 1, day) / 1000) as UTCTimestamp;
}

export interface TrackingChartPoint {
  time: UTCTimestamp;
  value: number;
}

export interface TrackingChartMarker {
  time: UTCTimestamp;
  text: string;
}

export interface TrackingChartData {
  net: TrackingChartPoint[];
  benchmark: TrackingChartPoint[];
  markers: TrackingChartMarker[];
}

/**
 * Chart data in percent. A gap session carries NaN so the chart breaks the
 * line there instead of drawing straight across it; the benchmark keeps its
 * own breaks. Each segment's entry gets a marker when there is more than one.
 */
export function trackingChartData(response: IdeaTrackingResponse | null): TrackingChartData {
  const points = response?.points ?? [];
  const net = points.map((point) => ({
    time: sessionTime(point.session),
    value: point.gap || point.net_return == null ? Number.NaN : point.net_return * 100,
  }));
  const benchmark = points.map((point) => ({
    time: sessionTime(point.session),
    value: point.benchmark_return == null ? Number.NaN : point.benchmark_return * 100,
  }));
  const priced = (response?.segments ?? []).filter((segment) => segment.entry_session && segment.sessions > 0);
  const markers =
    priced.length > 1
      ? priced.map((segment) => ({ time: sessionTime(segment.entry_session as string), text: `S${segment.number}` }))
      : [];
  return { net, benchmark: benchmark.some((point) => Number.isFinite(point.value)) ? benchmark : [], markers };
}

/** "2026-11-09 → 2026-11-11", "2026-11-11 → open", or the reason it has no book. */
export function segmentPeriodText(segment: IdeaTrackingSegment): string {
  if (!segment.entry_session) return SEGMENT_STATUS_LABELS[segment.status];
  const end = segment.exit_session ?? (segment.status === "tracking" ? "open" : segment.status === "exiting" ? "next close" : "N/A");
  return `${segment.entry_session} → ${end}`;
}

/**
 * The legs of a segment as written in the table: "AAPL +50% · MSFT −50%" (share
 * of gross). A segment without a book shows the weights the user wrote ("+1").
 */
export function segmentLegsText(segment: IdeaTrackingSegment): string {
  return segment.legs
    .map((leg) => {
      if (leg.weight != null) return `${leg.label} ${formatWeightShare(leg.weight)}`;
      if (leg.stated_weight != null) return `${leg.label} ${leg.stated_weight > 0 ? "+" : ""}${leg.stated_weight}`;
      return `${leg.label}, no weight`;
    })
    .join(" · ");
}

/** Only the classes whose value changed, as the PATCH payload expects. */
export function changedCosts(
  classes: IdeaTrackingCostClassView[],
  draft: Record<string, string>
): Record<string, number> | null {
  const changes: Record<string, number> = {};
  for (const item of classes) {
    if (!item.editable) continue;
    const raw = draft[item.asset_class];
    if (raw == null || raw.trim() === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value)) continue;
    if (value !== item.per_side_bp) changes[item.asset_class] = value;
  }
  return Object.keys(changes).length ? changes : null;
}

/** A cost draft is valid when every edited value is a number from 0 to 500 bp. */
export function costDraftError(draft: Record<string, string>): string {
  for (const [name, raw] of Object.entries(draft)) {
    if (raw.trim() === "") return `Enter a cost for ${COST_CLASS_SHORT_LABELS[name as IdeaTrackingCostClass] ?? name}.`;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0 || value > 500) return "Costs are 0 to 500 bp per side.";
  }
  return "";
}

/** I4: a leg's own per-side cost as typed in the editor; blank when it takes its class's cost. */
export function legBpText(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "" : String(value);
}

/** Blank is the class cost; anything else must be 0 to 500 bp per side. */
export function legBpDraftError(draft: Record<string, string>): string {
  for (const raw of Object.values(draft)) {
    if (raw.trim() === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0 || value > 500) return "Leg costs are 0 to 500 bp per side, or blank for the class cost.";
  }
  return "";
}

/** The per-leg costs that changed (null drops an override), or null when nothing did. */
export function changedLegBp(current: Record<string, number>, draft: Record<string, string>): Record<string, number | null> | null {
  const changes: Record<string, number | null> = {};
  for (const [key, raw] of Object.entries(draft)) {
    const next = raw.trim() === "" ? null : Number(raw);
    const before = current[key] ?? null;
    if (next !== before) changes[key] = next;
  }
  return Object.keys(changes).length ? changes : null;
}

/** The headline line under the panel title: sessions, gaps and the last close. */
export function trackingMetaText(response: IdeaTrackingResponse | null): string {
  if (!response) return "";
  const { summary } = response;
  if (!summary.sessions) return TRACKING_STATUS_LABELS[response.status];
  const parts = [`${summary.sessions} ${summary.sessions === 1 ? "session" : "sessions"}`];
  if (summary.gaps) parts.push(`${summary.gaps} ${summary.gaps === 1 ? "gap" : "gaps"}`);
  if (summary.as_of) parts.push(`as of ${summary.as_of}`);
  if (summary.stale_since) parts.push(`no close since ${summary.stale_since}`);
  return parts.join(" · ");
}
