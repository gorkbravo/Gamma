import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type {
  ActionResponse,
  DiagnosticsResponse,
  IvSessionStatus,
  IvSurface,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  ResearchResult,
  RiskResult,
  SystemStatus,
  TabId
} from "../api/types";

export interface SyntheticPositionInput {
  symbol: string;
  weight: number;
}

export interface ResearchRunOptions {
  scopeType: "single_ticker" | "synthetic_portfolio";
  primarySymbol?: string;
  syntheticPositions?: SyntheticPositionInput[];
  benchmarkSymbol: string;
  lookbackDays: number;
}

export interface RiskComputeOptions {
  alpha: number;
  lookbackDays: number;
  horizonDays: number;
  mcHorizonDays: number;
  mcSimulationModel: string;
  mcNumSimulations: number;
  betaWindow: number;
  benchmarkSymbol: string;
  snapshot?: PortfolioSnapshot | null;
}

export interface IvLoadOptions {
  symbol: string;
  marketDataMode?: string;
  waitSeconds?: number;
}

export const activeTab = writable<TabId>("portfolio");
export const systemStatus = writable<SystemStatus | null>(null);
export const diagnostics = writable<DiagnosticsResponse | null>(null);
export const diagnosticsLog = writable<string[]>([]);
export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const portfolioPerformance = writable<PortfolioPerformanceResponse | null>(null);
export const researchResult = writable<ResearchResult | null>(null);
export const riskResult = writable<RiskResult | null>(null);
export const ivSurface = writable<IvSurface | null>(null);
export const ivSession = writable<IvSessionStatus | null>(null);
export const lastError = writable<string>("");
export const loading = writable<Record<string, boolean>>({
  status: false,
  diagnostics: false,
  diagnosticsAction: false,
  portfolio: false,
  portfolioAction: false,
  research: false,
  risk: false,
  iv: false,
  ivSession: false
});

function setLoading(key: string, value: boolean) {
  loading.update((current) => ({ ...current, [key]: value }));
}

function setError(error: unknown) {
  lastError.set(error instanceof Error ? error.message : String(error));
}

function appendDiagnosticsLog(lines: string[], heading?: string) {
  if (!lines.length && !heading) {
    return;
  }
  diagnosticsLog.update((current) => {
    const next: string[] = [];
    if (heading) {
      next.push(heading);
    }
    next.push(...lines);
    return [...next, ...current].slice(0, 120);
  });
}

export async function refreshSystemStatus() {
  setLoading("status", true);
  try {
    const nextStatus = await getJson<SystemStatus>("/system/status");
    systemStatus.set(nextStatus);
    lastError.set("");
    return nextStatus;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("status", false);
  }
}

export async function loadDiagnostics() {
  setLoading("diagnostics", true);
  try {
    diagnostics.set(await getJson<DiagnosticsResponse>("/diagnostics"));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("diagnostics", false);
  }
}

export async function toggleConnection() {
  setLoading("status", true);
  try {
    const nextStatus = await postJson<SystemStatus>("/system/connection/toggle", {});
    systemStatus.set(nextStatus);
    diagnostics.update((current) =>
      current == null
        ? current
        : {
            ...current,
            connection: nextStatus.connection
          }
    );
    lastError.set("");
    return nextStatus;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("status", false);
  }
}

export async function setMarketDataMode(mode: string) {
  setLoading("status", true);
  try {
    const nextStatus = await postJson<SystemStatus>("/system/market-data-mode", {
      market_data_mode: mode
    });
    systemStatus.set(nextStatus);
    diagnostics.update((current) =>
      current == null
        ? current
        : {
            ...current,
            market_data_mode: nextStatus.market_data_mode
          }
    );
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
    const [snapshotResult, historyResult] = await Promise.allSettled([
      getJson<PortfolioSnapshot>("/portfolio/snapshot"),
      getJson<PortfolioHistoryResponse>("/portfolio/history")
    ]);

    const errors: unknown[] = [];

    if (snapshotResult.status === "fulfilled") {
      portfolioSnapshot.set(snapshotResult.value);
      const performanceResult = await Promise.allSettled([
        postJson<PortfolioPerformanceResponse>("/portfolio/performance", {
          snapshot: snapshotResult.value,
          benchmark_symbol: "SPY",
          lookback_days: 252
        })
      ]);
      const performance = performanceResult[0];
      if (performance.status === "fulfilled") {
        portfolioPerformance.set(performance.value);
      } else {
        errors.push(performance.reason);
      }
    } else {
      errors.push(snapshotResult.reason);
    }

    if (historyResult.status === "fulfilled") {
      portfolioHistory.set(historyResult.value);
    } else {
      errors.push(historyResult.reason);
    }

    if (errors.length === 0) {
      lastError.set("");
    } else {
      setError(errors[0]);
    }
  } catch (error) {
    setError(error);
  } finally {
    setLoading("portfolio", false);
  }
}

export async function loadPortfolioPerformance(options?: {
  snapshot?: PortfolioSnapshot | null;
  benchmarkSymbol?: string;
  lookbackDays?: number;
}) {
  const snapshot = options?.snapshot ?? get(portfolioSnapshot);
  if (!snapshot) {
    lastError.set("Load a portfolio snapshot before requesting portfolio performance.");
    return;
  }
  setLoading("portfolio", true);
  try {
    portfolioPerformance.set(
      await postJson<PortfolioPerformanceResponse>("/portfolio/performance", {
        snapshot,
        benchmark_symbol: options?.benchmarkSymbol ?? "SPY",
        lookback_days: options?.lookbackDays ?? 252
      })
    );
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("portfolio", false);
  }
}

export async function runResearch(options: ResearchRunOptions) {
  setLoading("research", true);
  try {
    const payload = {
      scope_type: options.scopeType,
      primary_symbol: options.primarySymbol ?? "",
      synthetic_positions: options.syntheticPositions ?? [],
      benchmark_symbol: options.benchmarkSymbol,
      lookback_days: options.lookbackDays
    };
    researchResult.set(await postJson<ResearchResult>("/research/analyze", payload));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("research", false);
  }
}

export async function computeRisk(options: RiskComputeOptions) {
  const snapshot = options.snapshot ?? get(portfolioSnapshot) ?? get(researchResult)?.snapshot ?? null;
  if (!snapshot) {
    lastError.set("Load or build a snapshot before computing risk.");
    return;
  }
  setLoading("risk", true);
  try {
    riskResult.set(
      await postJson<RiskResult>("/risk/compute", {
        snapshot,
        alpha: options.alpha,
        lookback_days: options.lookbackDays,
        horizon_days: options.horizonDays,
        mc_horizon_days: options.mcHorizonDays,
        mc_simulation_model: options.mcSimulationModel,
        mc_num_simulations: options.mcNumSimulations,
        beta_window: options.betaWindow,
        benchmark_symbol: options.benchmarkSymbol
      })
    );
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("risk", false);
  }
}

export async function loadIvSurface(options: IvLoadOptions | string = "SPY") {
  const request: IvLoadOptions =
    typeof options === "string"
      ? { symbol: options }
      : options;
  setLoading("iv", true);
  try {
    const params = new URLSearchParams({
      symbol: request.symbol
    });
    if (request.marketDataMode) {
      params.set("market_data_mode", request.marketDataMode);
    }
    if (request.waitSeconds != null) {
      params.set("wait_seconds", String(request.waitSeconds));
    }
    const surface = await getJson<IvSurface>(`/iv/surface?${params.toString()}`);
    ivSurface.set(surface);
    ivSession.update((current) => (current == null ? current : { ...current, surface }));
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("iv", false);
  }
}

export async function runDiagnosticsAction() {
  return runActionRequest("/diagnostics/run", "diagnosticsAction", "[Diagnostics]");
}

export async function forceAccountSubscribe() {
  return runActionRequest("/system/account-subscribe", "diagnosticsAction", "[Subscribe]");
}

export async function clearPortfolioHistory() {
  const result = await runActionRequest("/portfolio/history/clear", "portfolioAction", "[History]");
  if (result?.success) {
    portfolioHistory.set({
      source: "local_history_store",
      points: []
    });
    const snapshot = get(portfolioSnapshot);
    if (snapshot) {
      await loadPortfolioPerformance({ snapshot });
    }
  }
  return result;
}

export async function loadIvSession() {
  setLoading("ivSession", true);
  try {
    const session = await getJson<IvSessionStatus>("/iv/session");
    ivSession.set(session);
    ivSurface.set(session.surface);
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("ivSession", false);
  }
}

export async function startIvSession(options: IvLoadOptions) {
  setLoading("ivSession", true);
  try {
    const session = await postJson<IvSessionStatus>("/iv/session/start", {
      symbol: options.symbol,
      market_data_mode: options.marketDataMode ?? null
    });
    ivSession.set(session);
    ivSurface.set(session.surface);
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("ivSession", false);
  }
}

export async function stopIvSession() {
  setLoading("ivSession", true);
  try {
    const session = await postJson<IvSessionStatus>("/iv/session/stop", {});
    ivSession.set(session);
    ivSurface.set(session.surface);
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("ivSession", false);
  }
}

async function runActionRequest(path: string, loadingKey: string, heading: string) {
  setLoading(loadingKey, true);
  try {
    const result = await postJson<ActionResponse>(path, {});
    appendDiagnosticsLog(result.lines, heading);
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading(loadingKey, false);
  }
}
