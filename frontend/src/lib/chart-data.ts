import type { UTCTimestamp } from "lightweight-charts";

export interface TimeValuePoint {
  time: UTCTimestamp;
  value: number;
}

const API_TIMESTAMP_WITH_ZONE = /(?:[zZ]|[+\-]\d{2}:\d{2})$/;

export function parseApiTimestampToUtcSeconds(timestamp: string): UTCTimestamp | null {
  const normalized = API_TIMESTAMP_WITH_ZONE.test(timestamp) ? timestamp : `${timestamp}Z`;
  const milliseconds = Date.parse(normalized);
  if (!Number.isFinite(milliseconds)) {
    return null;
  }
  return Math.floor(milliseconds / 1000) as UTCTimestamp;
}

export function normalizeChartData(points: readonly TimeValuePoint[]): TimeValuePoint[] {
  const sorted = [...points]
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time);

  const deduped: TimeValuePoint[] = [];
  for (const point of sorted) {
    const previous = deduped.at(-1);
    if (previous && previous.time === point.time) {
      deduped[deduped.length - 1] = point;
      continue;
    }
    deduped.push(point);
  }
  return deduped;
}

/**
 * Sorted and de-duplicated like ``normalizeChartData``, but a non-finite value
 * is kept (as NaN) so the chart can draw it as a break: a missing observation
 * must never look like continuity.
 */
export function normalizeChartDataWithGaps(points: readonly TimeValuePoint[]): TimeValuePoint[] {
  const sorted = [...points]
    .filter((point) => Number.isFinite(point.time))
    .map((point) => (Number.isFinite(point.value) ? point : { ...point, value: Number.NaN }))
    .sort((left, right) => left.time - right.time);
  const deduped: TimeValuePoint[] = [];
  for (const point of sorted) {
    const previous = deduped.at(-1);
    if (previous && previous.time === point.time) {
      deduped[deduped.length - 1] = point;
      continue;
    }
    deduped.push(point);
  }
  return deduped;
}

/**
 * Continuous runs of a series with gaps, and the gap times. A chart draws each
 * run on its own, so nothing connects the observations on either side of a gap.
 */
export function splitAtGaps(points: readonly TimeValuePoint[]): { runs: TimeValuePoint[][]; gaps: UTCTimestamp[] } {
  const runs: TimeValuePoint[][] = [];
  const gaps: UTCTimestamp[] = [];
  let current: TimeValuePoint[] = [];
  for (const point of normalizeChartDataWithGaps(points)) {
    if (Number.isFinite(point.value)) {
      current.push(point);
      continue;
    }
    gaps.push(point.time);
    if (current.length) runs.push(current);
    current = [];
  }
  if (current.length) runs.push(current);
  return { runs, gaps };
}

/**
 * Week-over-week change of a daily series as a fraction: the latest value
 * against the one `sessions` observations earlier (five trading sessions by
 * default). Null when the series is too short or the base is zero.
 */
/**
 * Axis format for a series already expressed in percent (2.468 means 2.468%).
 * lightweight-charts' own "percent" format belongs to its percentage scale
 * mode and does not print the value: it showed 2.468 as "2.1%" and 0.6 as
 * "0.1%", and only whole ticks came out right. Two decimals, one above 100%.
 */
export function percentAxisFormat(latest: number | null | undefined): {
  type: "custom";
  minMove: number;
  formatter: (value: number) => string;
} {
  const magnitude = Math.abs(Number(latest ?? 0));
  const precision = Number.isFinite(magnitude) && magnitude >= 100 ? 1 : 2;
  return {
    type: "custom",
    minMove: 10 ** -precision,
    formatter: (value: number) => formatPercentAxisValue(value, precision),
  };
}

/** "2.47%", "−4.00%" (true minus sign, like the chart's other axes), "0.00%". */
export function formatPercentAxisValue(value: number, precision = 2): string {
  if (!Number.isFinite(value)) return "";
  const rounded = Number(value.toFixed(precision));
  if (rounded === 0) return `${(0).toFixed(precision)}%`;
  return `${rounded < 0 ? "−" : ""}${Math.abs(rounded).toFixed(precision)}%`;
}

export function weekOverWeekChange(values: ReadonlyArray<number | null | undefined>, sessions = 5): number | null {
  const series = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (series.length <= sessions) return null;
  const latest = series[series.length - 1];
  const base = series[series.length - 1 - sessions];
  return base === 0 ? null : latest / base - 1;
}
