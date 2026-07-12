import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type { PortfolioHistoryResponse, PortfolioPerformanceResponse, PortfolioSnapshot } from "../api/types";
import { lastError, setError, setLoading } from "./runtime";

export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const portfolioPerformance = writable<PortfolioPerformanceResponse | null>(null);

export async function loadPortfolioSnapshotData(): Promise<boolean> {
  setLoading("portfolio", true);
  try {
    const [snapshotResult, historyResult] = await Promise.allSettled([
      getJson<PortfolioSnapshot>("/portfolio/snapshot"),
      getJson<PortfolioHistoryResponse>("/portfolio/history")
    ]);
    const errors: unknown[] = [];
    if (snapshotResult.status === "fulfilled") {
      portfolioSnapshot.set(snapshotResult.value);
      try {
        portfolioPerformance.set(await postJson<PortfolioPerformanceResponse>("/portfolio/performance", {
          snapshot: snapshotResult.value, benchmark_symbol: "SPY", lookback_days: 252
        }));
      } catch (error) { errors.push(error); }
    } else errors.push(snapshotResult.reason);
    if (historyResult.status === "fulfilled") portfolioHistory.set(historyResult.value);
    else errors.push(historyResult.reason);
    if (errors.length) { setError(errors[0]); return false; }
    lastError.set("");
    return true;
  } catch (error) { setError(error); return false; }
  finally { setLoading("portfolio", false); }
}

export async function loadPortfolioPerformanceData(options?: {
  snapshot?: PortfolioSnapshot | null;
  benchmarkSymbol?: string;
  lookbackDays?: number;
}): Promise<boolean> {
  const snapshot = options?.snapshot ?? get(portfolioSnapshot);
  if (!snapshot) {
    lastError.set("Load a portfolio snapshot before requesting portfolio performance.");
    return false;
  }
  setLoading("portfolio", true);
  try {
    portfolioPerformance.set(await postJson<PortfolioPerformanceResponse>("/portfolio/performance", {
      snapshot, benchmark_symbol: options?.benchmarkSymbol ?? "SPY", lookback_days: options?.lookbackDays ?? 252
    }));
    lastError.set("");
    return true;
  } catch (error) { setError(error); return false; }
  finally { setLoading("portfolio", false); }
}
