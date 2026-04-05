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
