// Intraday layer of an idea's hypothetical record (Workstream 12, I3d): pure
// helpers for the strip in the tracking panel. While Trader Workstation is
// connected, the backend records one IBKR mark per leg every few minutes and
// values it against the canonical daily series; this module turns that view
// into labels, chart points and gap rows. Absence stays visible: a stretch
// without marks is a break in the line and a row in the gaps table.

import type { UTCTimestamp } from "lightweight-charts";
import type { IdeaIntradayGap, IdeaIntradayQuality, IdeaIntradayView } from "./api/types";

export const INTRADAY_QUALITY_LABELS: Record<IdeaIntradayQuality, string> = {
  live: "Live",
  delayed: "Delayed",
  frozen: "Frozen",
  delayed_frozen: "Delayed, frozen",
};

/** Tag tone of a quality: live is the accent; anything older is a caution. */
export function intradayQualityTone(quality: IdeaIntradayQuality | null | undefined): "accent" | "warning" | "" {
  if (!quality) return "";
  return quality === "live" ? "accent" : "warning";
}

export const INTRADAY_GAP_LABELS: Record<IdeaIntradayGap["kind"], string> = {
  disconnected: "TWS disconnected",
  skipped: "IBKR did not answer",
  not_running: "Gamma not running",
  not_recorded: "Not recorded",
};

/** "15:05" from a naive-UTC instant ("2026-11-10T15:05:00"); the strip states UTC once. */
export function utcClock(instant: string | null | undefined): string {
  if (!instant || instant.length < 16) return "N/A";
  return instant.slice(11, 16);
}

/** UTC seconds of a naive-UTC instant, for the chart's time axis. */
export function instantTime(instant: string): UTCTimestamp {
  const [day, clock = "00:00:00"] = instant.split("T");
  const [year, month, date] = day.split("-").map(Number);
  const [hour, minute, second] = clock.split(":").map((part) => Number.parseFloat(part) || 0);
  return (Date.UTC(year, month - 1, date, hour, minute, Math.floor(second)) / 1000) as UTCTimestamp;
}

/**
 * The reason under a gap's label, only when it adds something: IBKR's own
 * message or why nothing was recorded. "Gamma not running" and "TWS
 * disconnected" say it all.
 */
export function gapReasonDetail(gap: IdeaIntradayGap): string | null {
  return gap.kind === "skipped" || gap.kind === "not_recorded" ? gap.reason : null;
}

/** "15:05–15:25" or "since 16:30" for an open-ended gap. */
export function gapPeriodText(gap: IdeaIntradayGap): string {
  return gap.end ? `${utcClock(gap.start)}–${utcClock(gap.end)}` : `since ${utcClock(gap.start)}`;
}

/** Duration of a closed gap ("20 min", "1 h 5 min"); open-ended gaps have none. */
export function gapDurationText(gap: IdeaIntradayGap): string {
  if (!gap.end) return "Ongoing";
  const minutes = Math.max(0, Math.round((instantTime(gap.end) - instantTime(gap.start)) / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export interface IntradayChartPoint {
  time: UTCTimestamp;
  value: number;
}

/**
 * Today's return in percent at each mark. A gap point, a mark before the
 * segment's first close and every explicit gap between two marks become a
 * non-finite value, so the chart breaks the line there instead of drawing
 * continuity that was never observed.
 */
export function intradayChartData(view: IdeaIntradayView | null | undefined): IntradayChartPoint[] {
  if (!view?.points.length) return [];
  const points: IntradayChartPoint[] = view.points.map((point) => ({
    time: instantTime(point.at),
    value: point.today_return == null || point.gap ? Number.NaN : point.today_return * 100,
  }));
  const taken = new Set(points.map((point) => point.time));
  for (const gap of view.gaps) {
    if (!gap.end) continue;
    const start = instantTime(gap.start);
    const end = instantTime(gap.end);
    const inside = points.some((point) => point.time > start && point.time < end);
    const middle = Math.floor((start + end) / 2) as UTCTimestamp;
    if (!inside && end - start > 1 && !taken.has(middle)) {
      points.push({ time: middle, value: Number.NaN });
      taken.add(middle);
    }
  }
  points.sort((left, right) => left.time - right.time);
  return points.some((point) => Number.isFinite(point.value)) ? points : [];
}

/** "as of 15:25 UTC · 12 marks · 2 gaps" for the strip head. */
export function intradayMetaText(view: IdeaIntradayView): string {
  const parts: string[] = [];
  if (view.summary.as_of) parts.push(`as of ${utcClock(view.summary.as_of)} UTC`);
  parts.push(`${view.summary.marks} ${view.summary.marks === 1 ? "mark" : "marks"}`);
  if (view.summary.gaps) parts.push(`${view.summary.gaps} ${view.summary.gaps === 1 ? "gap" : "gaps"}`);
  return parts.join(" · ");
}

/** "every 5 min while a market is open, hourly while closed". */
export function cadenceText(view: IdeaIntradayView): string {
  const open = Math.round(view.cadence_seconds / 60);
  const closed = Math.round(view.closed_cadence_seconds / 60);
  return `Every ${open} min while a leg's market is open, every ${closed === 60 ? "hour" : `${closed} min`} while all are closed`;
}

/** The strip polls while it records today's session; otherwise the figures do not move. */
export function shouldPollIntraday(view: IdeaIntradayView | null | undefined, now: Date = new Date()): boolean {
  if (view?.status === "recording") return true;
  // Con TWS desconectado durante la sesión de hoy se sigue releyendo: el hueco crece y la
  // reconexión aparece sin reabrir la idea (visto en vivo el 2026-11-24).
  return Boolean(view && view.status === "idle" && !view.tws_connected && view.session === now.toISOString().slice(0, 10));
}

/** A mark's source as shown in the legs table: "Last", "Mid", "Prior close"… */
export function markFieldText(field: string | null | undefined): string {
  switch (field) {
    case "last":
      return "Last";
    case "mid":
      return "Mid";
    case "close":
      return "Prior close";
    case "delayedLast":
      return "Last";
    case "delayedMid":
      return "Mid";
    case "delayedClose":
      return "Prior close";
    default:
      return field ? field : "N/A";
  }
}

/** A price with two decimals (four below 1), or N/A. */
export function formatMark(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return Math.abs(value) >= 1
    ? value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value.toFixed(4);
}
