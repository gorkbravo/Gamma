import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type {
  IvSurface,
  PortfolioHistoryResponse,
  PortfolioSnapshot,
  ResearchResult,
  RiskResult,
  SystemStatus,
  TabId
} from "../api/types";

export const activeTab = writable<TabId>("portfolio");
export const systemStatus = writable<SystemStatus | null>(null);
export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const researchResult = writable<ResearchResult | null>(null);
export const riskResult = writable<RiskResult | null>(null);
export const ivSurface = writable<IvSurface | null>(null);
export const lastError = writable<string>("");
export const loading = writable<Record<string, boolean>>({
  status: false,
  portfolio: false,
  research: false,
  risk: false,
  iv: false
});

function setLoading(key: string, value: boolean) {
  loading.update((current) => ({ ...current, [key]: value }));
}

function setError(error: unknown) {
  lastError.set(error instanceof Error ? error.message : String(error));
}

export async function refreshSystemStatus() {
  setLoading("status", true);
  try {
    systemStatus.set(await getJson<SystemStatus>("/system/status"));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("status", false);
  }
}

export async function loadPortfolioSnapshot() {
  setLoading("portfolio", true);
  try {
    portfolioSnapshot.set(await getJson<PortfolioSnapshot>("/portfolio/snapshot"));
    portfolioHistory.set(await getJson<PortfolioHistoryResponse>("/portfolio/history"));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("portfolio", false);
  }
}

export async function runSingleTickerResearch(symbol: string, benchmarkSymbol: string) {
  setLoading("research", true);
  try {
    researchResult.set(
      await postJson<ResearchResult>("/research/analyze", {
        scope_type: "single_ticker",
        primary_symbol: symbol,
        benchmark_symbol: benchmarkSymbol,
        lookback_days: 252
      })
    );
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("research", false);
  }
}

export async function computeRiskFromLatestSnapshot() {
  const snapshot = get(portfolioSnapshot);
  if (!snapshot) {
    lastError.set("Load a portfolio snapshot before computing risk.");
    return;
  }
  setLoading("risk", true);
  try {
    riskResult.set(
      await postJson<RiskResult>("/risk/compute", {
        snapshot,
        alpha: 0.95,
        lookback_days: 252,
        horizon_days: 1,
        mc_horizon_days: 10,
        mc_simulation_model: "Gaussian",
        mc_num_simulations: 500,
        beta_window: 63,
        benchmark_symbol: "AAPL"
      })
    );
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("risk", false);
  }
}

export async function loadIvSurface(symbol = "SPY") {
  setLoading("iv", true);
  try {
    ivSurface.set(await getJson<IvSurface>(`/iv/surface?symbol=${encodeURIComponent(symbol)}`));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("iv", false);
  }
}
