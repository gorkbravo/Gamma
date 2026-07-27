import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type { PortfolioHistoryResponse, PortfolioPerformanceResponse, PortfolioSnapshot } from "../api/types";
import {
  classifyHistoryStatus,
  classifyPerformanceStatus,
  classifySnapshotStatus,
  initialHistoryRequestState,
  initialPerformanceRequestState,
  initialSnapshotRequestState,
  lookbackDaysForPortfolioTimeframe,
  normalizePortfolioBenchmark,
  type HistoryRequestState,
  type PortfolioChartMode,
  type PortfolioHistoryWithMetadata,
  type PortfolioPerformanceWithMetadata,
  type PortfolioPreferences,
  type PortfolioSnapshotWithMetadata,
  type PortfolioTimeframe,
  type PerformanceRequestState,
  type SnapshotRequestState
} from "../view-models/portfolio";
import { beginLoading, endLoading, lastError } from "./runtime";

const PORTFOLIO_PREFERENCES_KEY = "gamma.portfolio.preferences.v1";
const DEFAULT_PREFERENCES: PortfolioPreferences = {
  benchmarkSymbol: "SPY",
  timeframe: "1y",
  chartMode: "growth"
};

export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const portfolioPerformance = writable<PortfolioPerformanceResponse | null>(null);
export const portfolioSnapshotRequestState = writable<SnapshotRequestState>(initialSnapshotRequestState());
export const portfolioHistoryRequestState = writable<HistoryRequestState>(initialHistoryRequestState());
export const portfolioPerformanceRequestState = writable<PerformanceRequestState>(initialPerformanceRequestState());
export const portfolioPreferences = writable<PortfolioPreferences>(readPreferences());

let snapshotLoadPromise: Promise<boolean> | null = null;
let historyLoadPromise: Promise<boolean> | null = null;
const performanceLoadPromises = new Map<string, Promise<boolean>>();
let latestPerformanceKey: string | null = null;

if (typeof window !== "undefined") {
  portfolioPreferences.subscribe((preferences) => {
    try {
      window.localStorage.setItem(PORTFOLIO_PREFERENCES_KEY, JSON.stringify(preferences));
    } catch {
      // Local preference persistence is best-effort; request state remains in memory.
    }
  });
}

export function updatePortfolioPreferences(patch: Partial<PortfolioPreferences>) {
  portfolioPreferences.update((current) => ({
    benchmarkSymbol: normalizePortfolioBenchmark(patch.benchmarkSymbol ?? current.benchmarkSymbol),
    timeframe: isPortfolioTimeframe(patch.timeframe) ? patch.timeframe : current.timeframe,
    chartMode: isPortfolioChartMode(patch.chartMode) ? patch.chartMode : current.chartMode
  }));
}

export function loadPortfolioSnapshotData(): Promise<boolean> {
  if (snapshotLoadPromise) {
    return snapshotLoadPromise;
  }
  const request = runPortfolioSnapshotLoad();
  snapshotLoadPromise = request;
  return request.finally(() => {
    if (snapshotLoadPromise === request) {
      snapshotLoadPromise = null;
    }
  });
}

export function loadPortfolioHistoryData(): Promise<boolean> {
  if (historyLoadPromise) {
    return historyLoadPromise;
  }
  const request = runPortfolioHistoryLoad();
  historyLoadPromise = request;
  return request.finally(() => {
    if (historyLoadPromise === request) {
      historyLoadPromise = null;
    }
  });
}

export function loadPortfolioPerformanceData(options?: {
  snapshot?: PortfolioSnapshot | null;
  benchmarkSymbol?: string;
  lookbackDays?: number;
}): Promise<boolean> {
  if (options?.benchmarkSymbol) {
    updatePortfolioPreferences({ benchmarkSymbol: options.benchmarkSymbol });
  }
  const selectedTimeframe = timeframeForLookback(options?.lookbackDays);
  if (selectedTimeframe) {
    updatePortfolioPreferences({ timeframe: selectedTimeframe });
  }
  const snapshot = options?.snapshot ?? get(portfolioSnapshot);
  const preferences = get(portfolioPreferences);
  const benchmarkSymbol = normalizePortfolioBenchmark(
    options?.benchmarkSymbol ?? preferences.benchmarkSymbol
  );
  const lookbackDays =
    options?.lookbackDays ?? lookbackDaysForPortfolioTimeframe(preferences.timeframe);
  const key = `${snapshot?.timestamp ?? "none"}:${benchmarkSymbol}:${lookbackDays}`;
  latestPerformanceKey = key;
  const existing = performanceLoadPromises.get(key);
  if (existing) {
    return existing;
  }
  const request = runPortfolioPerformanceLoad({
    snapshot,
    benchmarkSymbol,
    lookbackDays,
    requestKey: key
  });
  performanceLoadPromises.set(key, request);
  return request.finally(() => {
    if (performanceLoadPromises.get(key) === request) {
      performanceLoadPromises.delete(key);
    }
  });
}

async function runPortfolioSnapshotLoad(): Promise<boolean> {
  beginLoading("portfolio");
  markSnapshotPending();
  try {
    const [snapshotResult] = await Promise.allSettled([
      getJson<PortfolioSnapshot>("/portfolio/snapshot"),
      loadPortfolioHistoryData()
    ]);
    if (snapshotResult.status === "rejected") {
      markSnapshotFailure();
      lastError.set("Portfolio snapshot request failed. Existing Portfolio data was retained.");
      return false;
    }

    const snapshot = snapshotResult.value;
    const snapshotStatus = classifySnapshotStatus(snapshot);
    if (snapshotStatus === "failed" || snapshotStatus === "unavailable") {
      if (get(portfolioSnapshot) == null) {
        portfolioSnapshot.set(snapshot);
      }
      markSnapshotTypedFailure(snapshot, snapshotStatus);
      applySnapshotHistoryHealth(snapshot);
      lastError.set("Portfolio provider is unavailable. Existing Portfolio data was retained.");
      return false;
    }
    portfolioSnapshot.set(snapshot);
    markSnapshotSuccess(snapshot);
    applySnapshotHistoryHealth(snapshot);
    const preferences = get(portfolioPreferences);
    const performanceLoaded = await loadPortfolioPerformanceData({
      snapshot,
      benchmarkSymbol: preferences.benchmarkSymbol,
      lookbackDays: lookbackDaysForPortfolioTimeframe(preferences.timeframe)
    });
    if (performanceLoaded && get(portfolioHistoryRequestState).status !== "failed") {
      lastError.set("");
    }
    return true;
  } catch {
    markSnapshotFailure();
    lastError.set("Portfolio snapshot request failed. Existing Portfolio data was retained.");
    return false;
  } finally {
    endLoading("portfolio");
  }
}

async function runPortfolioHistoryLoad(): Promise<boolean> {
  beginLoading("portfolio");
  markHistoryPending();
  try {
    const history = await getJson<PortfolioHistoryResponse>("/portfolio/history");
    const historyStatus = classifyHistoryStatus(history);
    if (historyStatus === "failed") {
      if (get(portfolioHistory) == null) {
        portfolioHistory.set(history);
      }
      markHistoryTypedFailure(history);
      lastError.set("Local portfolio history is unavailable. Existing history was retained.");
      return false;
    }
    portfolioHistory.set(history);
    markHistorySuccess(history);
    return true;
  } catch {
    markHistoryFailure();
    lastError.set("Local portfolio history could not be read. Existing history was retained.");
    return false;
  } finally {
    endLoading("portfolio");
  }
}

async function runPortfolioPerformanceLoad(options: {
  snapshot: PortfolioSnapshot | null;
  benchmarkSymbol: string;
  lookbackDays: number;
  requestKey: string;
}): Promise<boolean> {
  const snapshot = options.snapshot;
  if (!snapshot) {
    portfolioPerformanceRequestState.update((current) => ({
      ...current,
      status: "unavailable",
      initialLoading: false,
      refreshing: false,
      error: "Load a portfolio snapshot before requesting performance.",
      lastFailureAt: new Date().toISOString()
    }));
    lastError.set("Load a portfolio snapshot before requesting portfolio performance.");
    return false;
  }

  beginLoading("portfolio");
  markPerformancePending();
  try {
    const performance = await postJson<PortfolioPerformanceResponse>("/portfolio/performance", {
      snapshot,
      benchmark_symbol: options.benchmarkSymbol,
      lookback_days: options.lookbackDays
    });
    if (options.requestKey !== latestPerformanceKey) {
      return true;
    }
    const performanceStatus = classifyPerformanceStatus(performance);
    if (performanceStatus === "failed" || performanceStatus === "unavailable") {
      if (get(portfolioPerformance) == null) {
        portfolioPerformance.set(performance);
      }
      markPerformanceTypedFailure(performance, performanceStatus);
      lastError.set("Portfolio performance is unavailable. Existing results were retained.");
      return false;
    }
    portfolioPerformance.set(performance);
    markPerformanceSuccess(performance);
    lastError.set("");
    return true;
  } catch {
    if (options.requestKey !== latestPerformanceKey) {
      return false;
    }
    markPerformanceFailure();
    lastError.set("Portfolio performance could not be recalculated. Existing results were retained.");
    return false;
  } finally {
    endLoading("portfolio");
  }
}

function markSnapshotPending() {
  const hasData = get(portfolioSnapshot) != null;
  portfolioSnapshotRequestState.update((current) => ({
    ...current,
    status: hasData ? current.status === "idle" ? "ready" : current.status : "loading",
    initialLoading: !hasData,
    refreshing: hasData,
    error: null
  }));
}

function markSnapshotSuccess(snapshot: PortfolioSnapshot) {
  const metadata = snapshot as PortfolioSnapshotWithMetadata;
  portfolioSnapshotRequestState.update((current) => ({
    ...current,
    status: classifySnapshotStatus(snapshot),
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: dedupeWarnings(snapshot.warnings),
    lastSuccessAt: metadata.retrieved_at ?? snapshot.timestamp ?? new Date().toISOString()
  }));
}

function markSnapshotTypedFailure(
  snapshot: PortfolioSnapshot,
  status: "failed" | "unavailable"
) {
  const metadata = snapshot as PortfolioSnapshotWithMetadata;
  portfolioSnapshotRequestState.update((current) => ({
    ...current,
    status,
    initialLoading: false,
    refreshing: false,
    error:
      status === "unavailable"
        ? "Portfolio provider is unavailable. Check connection and account readiness."
        : "Snapshot request failed. Open diagnostics for provider detail.",
    warnings: dedupeWarnings(snapshot.warnings),
    lastFailureAt: metadata.retrieved_at ?? new Date().toISOString()
  }));
}

function markSnapshotFailure() {
  portfolioSnapshotRequestState.update((current) => ({
    ...current,
    status: "failed",
    initialLoading: false,
    refreshing: false,
    error: "Snapshot refresh failed. Open diagnostics for provider detail.",
    lastFailureAt: new Date().toISOString()
  }));
}

function markHistoryPending() {
  const hasData = get(portfolioHistory) != null;
  portfolioHistoryRequestState.update((current) => ({
    ...current,
    status: hasData ? current.status === "idle" ? "ready" : current.status : "loading",
    initialLoading: !hasData,
    refreshing: hasData,
    error: null
  }));
}

function markHistorySuccess(history: PortfolioHistoryResponse) {
  const metadata = history as PortfolioHistoryWithMetadata;
  portfolioHistoryRequestState.update((current) => ({
    ...current,
    status: classifyHistoryStatus(history),
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: dedupeWarnings([
      ...(metadata.warnings ?? []),
      ...(metadata.health?.warnings ?? [])
    ]),
    lastSuccessAt: metadata.retrieved_at ?? metadata.health?.last_write_at ?? new Date().toISOString()
  }));
}

function markHistoryFailure() {
  portfolioHistoryRequestState.update((current) => ({
    ...current,
    status: "failed",
    initialLoading: false,
    refreshing: false,
    error: "Local history read failed. Open diagnostics for persistence detail.",
    lastFailureAt: new Date().toISOString()
  }));
}

function markHistoryTypedFailure(history: PortfolioHistoryResponse) {
  const metadata = history as PortfolioHistoryWithMetadata;
  portfolioHistoryRequestState.update((current) => ({
    ...current,
    status: "failed",
    initialLoading: false,
    refreshing: false,
    error: "Local history persistence is unavailable. Open diagnostics for details.",
    warnings: dedupeWarnings([
      ...(metadata.warnings ?? []),
      ...(metadata.health?.warnings ?? [])
    ]),
    lastFailureAt: metadata.retrieved_at ?? new Date().toISOString()
  }));
}

function markPerformancePending() {
  const hasData = get(portfolioPerformance) != null;
  portfolioPerformanceRequestState.update((current) => ({
    ...current,
    status: hasData ? current.status === "idle" ? "ready" : current.status : "loading",
    initialLoading: !hasData,
    refreshing: hasData,
    error: null
  }));
}

function markPerformanceSuccess(performance: PortfolioPerformanceResponse) {
  const metadata = performance as PortfolioPerformanceWithMetadata;
  portfolioPerformanceRequestState.update((current) => ({
    ...current,
    status: classifyPerformanceStatus(performance),
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: dedupeWarnings(performance.warnings),
    lastSuccessAt: metadata.retrieved_at ?? new Date().toISOString()
  }));
}

function markPerformanceTypedFailure(
  performance: PortfolioPerformanceResponse,
  status: "failed" | "unavailable"
) {
  const metadata = performance as PortfolioPerformanceWithMetadata;
  portfolioPerformanceRequestState.update((current) => ({
    ...current,
    status,
    initialLoading: false,
    refreshing: false,
    error:
      status === "unavailable"
        ? performance.message ?? "Portfolio performance is unavailable."
        : "Performance calculation failed. Open diagnostics for provider detail.",
    warnings: dedupeWarnings(performance.warnings),
    lastFailureAt: metadata.retrieved_at ?? new Date().toISOString()
  }));
}

function applySnapshotHistoryHealth(snapshot: PortfolioSnapshot) {
  const health = (snapshot as PortfolioSnapshotWithMetadata).history_store_health;
  if (!health) return;
  const status = String(health.status ?? "").trim().toLowerCase();
  if (status !== "recovered" && status !== "degraded" && status !== "failed") return;
  portfolioHistoryRequestState.update((current) => ({
    ...current,
    status,
    error: status === "failed" ? "Local history persistence is unavailable." : current.error,
    warnings: dedupeWarnings([...(current.warnings ?? []), ...(health.warnings ?? [])]),
    lastFailureAt: status === "failed" ? new Date().toISOString() : current.lastFailureAt
  }));
}

function markPerformanceFailure() {
  portfolioPerformanceRequestState.update((current) => ({
    ...current,
    status: "failed",
    initialLoading: false,
    refreshing: false,
    error: "Performance calculation failed. Open diagnostics for provider detail.",
    lastFailureAt: new Date().toISOString()
  }));
}

function readPreferences(): PortfolioPreferences {
  if (typeof window === "undefined") {
    return { ...DEFAULT_PREFERENCES };
  }
  try {
    const raw = window.localStorage.getItem(PORTFOLIO_PREFERENCES_KEY);
    if (!raw) {
      return { ...DEFAULT_PREFERENCES };
    }
    const parsed = JSON.parse(raw) as Partial<PortfolioPreferences>;
    return {
      benchmarkSymbol: normalizePortfolioBenchmark(parsed.benchmarkSymbol ?? "SPY"),
      timeframe: isPortfolioTimeframe(parsed.timeframe) ? parsed.timeframe : "1y",
      chartMode: isPortfolioChartMode(parsed.chartMode) ? parsed.chartMode : "growth"
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

function timeframeForLookback(lookbackDays: number | undefined): PortfolioTimeframe | null {
  if (lookbackDays == null) {
    return null;
  }
  const match = (["1m", "2m", "1y", "3y", "max"] as PortfolioTimeframe[]).find(
    (timeframe) => lookbackDaysForPortfolioTimeframe(timeframe) === lookbackDays
  );
  return match ?? null;
}

function isPortfolioTimeframe(value: unknown): value is PortfolioTimeframe {
  return ["1m", "2m", "1y", "3y", "max"].includes(String(value));
}

function isPortfolioChartMode(value: unknown): value is PortfolioChartMode {
  return ["value", "growth", "drawdown"].includes(String(value));
}

function dedupeWarnings(warnings: string[]) {
  const seen = new Set<string>();
  return warnings.filter((warning) => {
    const normalized = warning.trim().replace(/\s+/g, " ");
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

export function resetPortfolioUiStateForTests() {
  snapshotLoadPromise = null;
  historyLoadPromise = null;
  performanceLoadPromises.clear();
  latestPerformanceKey = null;
  portfolioSnapshot.set(null);
  portfolioHistory.set(null);
  portfolioPerformance.set(null);
  portfolioSnapshotRequestState.set(initialSnapshotRequestState());
  portfolioHistoryRequestState.set(initialHistoryRequestState());
  portfolioPerformanceRequestState.set(initialPerformanceRequestState());
  portfolioPreferences.set({ ...DEFAULT_PREFERENCES });
}
