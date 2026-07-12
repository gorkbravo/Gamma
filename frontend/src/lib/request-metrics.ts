import { writable } from "svelte/store";

export type RequestMetricKind =
  | "cache_hit"
  | "stale_hit"
  | "coalesced"
  | "cancelled"
  | "network_request"
  | "network_success"
  | "network_error"
  | "slow_request";

export type RequestMetricSnapshot = {
  totals: Record<RequestMetricKind, number>;
  byKey: Record<string, Partial<Record<RequestMetricKind, number>>>;
  recent: Array<{ key: string; kind: RequestMetricKind; at: string; durationMs?: number }>;
  startup: null | { activeTab: string; durationMs: number; networkRequests: number; usableAt: string };
};

const KINDS: RequestMetricKind[] = [
  "cache_hit",
  "stale_hit",
  "coalesced",
  "cancelled",
  "network_request",
  "network_success",
  "network_error",
  "slow_request"
];
const MAX_KEYS = 100;
const MAX_RECENT = 100;

function emptySnapshot(): RequestMetricSnapshot {
  return {
    totals: Object.fromEntries(KINDS.map((kind) => [kind, 0])) as Record<RequestMetricKind, number>,
    byKey: {},
    recent: [],
    startup: null
  };
}

export const requestMetrics = writable<RequestMetricSnapshot>(emptySnapshot());

export function recordRequestMetric(key: string, kind: RequestMetricKind, durationMs?: number): void {
  const safeKey = String(key || "unknown").slice(0, 240);
  requestMetrics.update((current) => {
    const byKey = { ...current.byKey };
    if (!(safeKey in byKey) && Object.keys(byKey).length >= MAX_KEYS) {
      delete byKey[Object.keys(byKey)[0]];
    }
    byKey[safeKey] = {
      ...byKey[safeKey],
      [kind]: (byKey[safeKey]?.[kind] ?? 0) + 1
    };
    return {
      totals: { ...current.totals, [kind]: current.totals[kind] + 1 },
      byKey,
      startup: current.startup,
      recent: [
        ...current.recent,
        { key: safeKey, kind, at: new Date().toISOString(), ...(durationMs == null ? {} : { durationMs }) }
      ].slice(-MAX_RECENT)
    };
  });
}

let startupStartedAt = 0;
let startupNetworkBaseline = 0;

export function markStartupBegin(): void {
  startupStartedAt = performance.now();
  requestMetrics.update((current) => {
    startupNetworkBaseline = current.totals.network_request;
    return { ...current, startup: null };
  });
}

export function markStartupUsable(activeTab: string): void {
  const durationMs = Math.max(0, performance.now() - startupStartedAt);
  requestMetrics.update((current) => ({
    ...current,
    startup: {
      activeTab,
      durationMs,
      networkRequests: Math.max(0, current.totals.network_request - startupNetworkBaseline),
      usableAt: new Date().toISOString()
    }
  }));
}

export function resetRequestMetrics(): void {
  requestMetrics.set(emptySnapshot());
}
