import { get, writable } from "svelte/store";
import { getJson, postJson } from "../api/client";
import type {
  ActionResponse,
  BaseCurrencyResponse,
  DiagnosticsResponse,
  IvSessionStatus,
  IvSurface,
  MacroContextState,
  MacroDivergenceListResponse,
  MacroEventsResponse,
  MacroSeriesHistory,
  MacroSnapshot,
  PredictionCalibrationSummary,
  PredictionMarket,
  PredictionMarketListResponse,
  PredictionProbabilityHistoryResponse,
  PredictionWalletSummary,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  RelatedPredictionMarketListResponse,
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

export interface ResearchDraftState {
  scopeType: "single_ticker" | "synthetic_portfolio";
  primarySymbol: string;
  benchmarkSymbol: string;
  lookbackDays: number;
  syntheticText: string;
  selectedPreset: string;
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
  includeMonteCarlo?: boolean;
  snapshot?: PortfolioSnapshot | null;
}

export interface IvLoadOptions {
  symbol: string;
  marketDataMode?: string;
  waitSeconds?: number;
}

export interface PredictionMarketScreenerOptions {
  query?: string;
  venues?: string[];
  status?: "open" | "closed" | "all";
  forceRefresh?: boolean;
  category?: string;
  minVolume?: number;
  minLiquidity?: number;
  minOpenInterest?: number;
  minProbability?: number;
  maxProbability?: number;
  maxDaysToResolution?: number;
  minRepricingAbs?: number;
  sortBy?: "research_rank" | "volume_desc" | "liquidity_desc" | "open_interest_desc" | "repricing_desc" | "resolution_soon";
  limit?: number;
}

export interface MacroLoadOptions {
  region?: MacroContextState["region"];
  timeframe?: MacroContextState["timeframe"];
  theme?: MacroContextState["theme"];
  comparisonRegion?: MacroContextState["comparisonRegion"];
  mode?: MacroContextState["mode"];
  forceRefresh?: boolean;
}

export const activeTab = writable<TabId>("portfolio");
export const systemStatus = writable<SystemStatus | null>(null);
export const diagnostics = writable<DiagnosticsResponse | null>(null);
export const diagnosticsLog = writable<string[]>([]);
export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const portfolioPerformance = writable<PortfolioPerformanceResponse | null>(null);
export const researchResult = writable<ResearchResult | null>(null);
export const macroContext = writable<MacroContextState>({
  mode: "snapshot",
  region: "US",
  timeframe: "3M",
  theme: "all",
  comparisonRegion: null
});
export const macroSnapshot = writable<MacroSnapshot | null>(null);
export const macroDivergences = writable<MacroDivergenceListResponse | null>(null);
export const macroEvents = writable<MacroEventsResponse | null>(null);
export const macroSeriesHistories = writable<Record<string, MacroSeriesHistory>>({});
export const predictionMarketScreener = writable<PredictionMarketListResponse | null>(null);
export const selectedPredictionMarketId = writable<string | null>(null);
export const predictionMarketDetail = writable<PredictionMarket | null>(null);
export const predictionMarketHistory = writable<PredictionProbabilityHistoryResponse | null>(null);
export const predictionMarketWallet = writable<PredictionWalletSummary | null>(null);
export const predictionMarketRelated = writable<RelatedPredictionMarketListResponse | null>(null);
export const predictionMarketCalibration = writable<PredictionCalibrationSummary | null>(null);
export const researchDraft = writable<ResearchDraftState>({
  scopeType: "single_ticker",
  primarySymbol: "AAPL",
  benchmarkSymbol: "SPY",
  lookbackDays: 252,
  syntheticText: "SPY 0.60\nQQQ 0.40",
  selectedPreset: "index-core"
});
export const riskResult = writable<RiskResult | null>(null);
export const ivSurface = writable<IvSurface | null>(null);
export const ivSession = writable<IvSessionStatus | null>(null);
export const lastError = writable<string>("");

export type ChartTheme = "blue" | "amber" | "green";
export const chartTheme = writable<ChartTheme>("blue");

export function setChartTheme(theme: ChartTheme) {
  chartTheme.set(theme);
  if (typeof document !== "undefined") {
    if (theme === "blue") {
      document.documentElement.removeAttribute("data-chart-theme");
    } else {
      document.documentElement.setAttribute("data-chart-theme", theme);
    }
  }
}
export const loading = writable<Record<string, boolean>>({
  status: false,
  diagnostics: false,
  diagnosticsAction: false,
  portfolio: false,
  portfolioAction: false,
  research: false,
  macro: false,
  macroHistory: false,
  prediction: false,
  predictionDetail: false,
  risk: false,
  iv: false,
  ivSession: false
});

function setLoading(key: string, value: boolean) {
  loading.update((current) => ({ ...current, [key]: value }));
}

export function setResearchDraft(nextDraft: ResearchDraftState) {
  researchDraft.set(nextDraft);
}

export function setMacroContext(nextContext: Partial<MacroContextState>) {
  macroContext.update((current) => ({ ...current, ...nextContext }));
}

function setError(error: unknown) {
  lastError.set(error instanceof Error ? error.message : String(error));
}

function hasRenderableIvSurface(surface: IvSurface | null | undefined) {
  if (!surface) {
    return false;
  }
  return Boolean(surface.snapshot_available || surface.points > 0 || surface.expiries.length > 0 || surface.strikes.length > 0);
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

export async function setBaseCurrency(currency: string) {
  setLoading("status", true);
  try {
    const previousCurrency = get(systemStatus)?.base_currency ?? null;
    const response = await postJson<BaseCurrencyResponse>("/system/base-currency", {
      base_currency: currency
    });
    systemStatus.set(response);
    const currencyChanged = previousCurrency !== response.base_currency;
    diagnostics.update((current) =>
      current == null
        ? current
        : {
            ...current,
            base_currency: response.base_currency,
            local_history_entries: currencyChanged ? 0 : current.local_history_entries
          }
    );
    if (currencyChanged) {
      portfolioSnapshot.set(null);
      portfolioHistory.set({
        source: "local_history_store",
        points: []
      });
      portfolioPerformance.set(null);
      researchResult.set(null);
      riskResult.set(null);
    }
    appendDiagnosticsLog(response.lines, "[Settings]");
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
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
    const nextResearchResult = await postJson<ResearchResult>("/research/analyze", payload);
    researchResult.set(nextResearchResult);
    // Downstream analysis must be recomputed from the latest executed research scope.
    riskResult.set(null);
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("research", false);
  }
}

function macroPayloadFromOptions(options: MacroLoadOptions = {}) {
  const current = get(macroContext);
  return {
    region: options.region ?? current.region,
    timeframe: options.timeframe ?? current.timeframe,
    theme: options.theme ?? current.theme,
    comparison_region: options.comparisonRegion ?? current.comparisonRegion,
    force_refresh: options.forceRefresh ?? false
  };
}

function macroHistoryKey(seriesId: string, region: string, timeframe: string) {
  return `${region}:${timeframe}:${seriesId}`;
}

export async function loadMacroWorkspace(options: MacroLoadOptions = {}) {
  const nextContext: MacroContextState = {
    ...get(macroContext),
    ...(options.mode ? { mode: options.mode } : {}),
    ...(options.region ? { region: options.region } : {}),
    ...(options.timeframe ? { timeframe: options.timeframe } : {}),
    ...(options.theme ? { theme: options.theme } : {}),
    ...(options.comparisonRegion !== undefined ? { comparisonRegion: options.comparisonRegion } : {})
  };
  macroContext.set(nextContext);
  const payload = macroPayloadFromOptions(options);
  setLoading("macro", true);
  try {
    const [snapshot, divergences, events] = await Promise.all([
      postJson<MacroSnapshot>("/macro/snapshot", payload),
      postJson<MacroDivergenceListResponse>("/macro/divergences", payload),
      getJson<MacroEventsResponse>(
        `/macro/events?region=${encodeURIComponent(payload.region)}&force_refresh=${payload.force_refresh ? "true" : "false"}`
      )
    ]);
    macroSnapshot.set(snapshot);
    macroDivergences.set(divergences);
    macroEvents.set(events);
    lastError.set("");
    return snapshot;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("macro", false);
  }
}

export async function loadMacroSeriesHistory(seriesId: string, options: MacroLoadOptions = {}) {
  const payload = macroPayloadFromOptions(options);
  const cacheKey = macroHistoryKey(seriesId, payload.region, payload.timeframe);
  setLoading("macroHistory", true);
  try {
    const history = await getJson<MacroSeriesHistory>(
      `/macro/series/${encodeURIComponent(seriesId)}/history?region=${encodeURIComponent(payload.region)}&timeframe=${encodeURIComponent(payload.timeframe)}&force_refresh=${payload.force_refresh ? "true" : "false"}`
    );
    macroSeriesHistories.update((current) => ({ ...current, [cacheKey]: history }));
    lastError.set("");
    return history;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("macroHistory", false);
  }
}

export async function loadPredictionMarketScreener(options: PredictionMarketScreenerOptions = {}) {
  setLoading("prediction", true);
  try {
    const response = await postJson<PredictionMarketListResponse>("/prediction-markets/screener", {
      query: options.query ?? "",
      venues: options.venues ?? [],
      status: options.status ?? "open",
      force_refresh: options.forceRefresh ?? false,
      category: options.category ?? null,
      min_volume: options.minVolume ?? null,
      min_liquidity: options.minLiquidity ?? null,
      min_open_interest: options.minOpenInterest ?? null,
      min_probability: options.minProbability ?? null,
      max_probability: options.maxProbability ?? null,
      max_days_to_resolution: options.maxDaysToResolution ?? null,
      min_repricing_abs: options.minRepricingAbs ?? null,
      sort_by: options.sortBy ?? "research_rank",
      limit: options.limit ?? 40
    });
    predictionMarketScreener.set(response);
    const currentSelection = get(selectedPredictionMarketId);
    const selectedStillVisible = response.markets.some((market) => market.market_id === currentSelection);
    const nextSelection = selectedStillVisible ? currentSelection : (response.markets[0]?.market_id ?? null);
    if (nextSelection) {
      await selectPredictionMarket(nextSelection);
    } else {
      selectedPredictionMarketId.set(null);
      predictionMarketDetail.set(null);
      predictionMarketHistory.set(null);
      predictionMarketWallet.set(null);
      predictionMarketRelated.set(null);
      predictionMarketCalibration.set(null);
    }
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("prediction", false);
  }
}

export async function selectPredictionMarket(marketId: string) {
  selectedPredictionMarketId.set(marketId);
  setLoading("predictionDetail", true);
  try {
    const [detailResult, historyResult, walletResult, relatedResult, calibrationResult] = await Promise.allSettled([
      getJson<PredictionMarket>(`/prediction-markets/markets/${marketId}`),
      getJson<PredictionProbabilityHistoryResponse>(`/prediction-markets/markets/${marketId}/history`),
      getJson<PredictionWalletSummary>(`/prediction-markets/markets/${marketId}/wallet-summary`),
      getJson<RelatedPredictionMarketListResponse>(`/prediction-markets/markets/${marketId}/related`),
      getJson<PredictionCalibrationSummary>(`/prediction-markets/markets/${marketId}/calibration`)
    ]);

    const errors: unknown[] = [];

    if (detailResult.status === "fulfilled") {
      predictionMarketDetail.set(detailResult.value);
    } else {
      errors.push(detailResult.reason);
    }
    if (historyResult.status === "fulfilled") {
      predictionMarketHistory.set(historyResult.value);
    } else {
      errors.push(historyResult.reason);
    }
    if (walletResult.status === "fulfilled") {
      predictionMarketWallet.set(walletResult.value);
    } else {
      errors.push(walletResult.reason);
    }
    if (relatedResult.status === "fulfilled") {
      predictionMarketRelated.set(relatedResult.value);
    } else {
      errors.push(relatedResult.reason);
    }
    if (calibrationResult.status === "fulfilled") {
      predictionMarketCalibration.set(calibrationResult.value);
    } else {
      errors.push(calibrationResult.reason);
    }

    if (errors.length === 0) {
      lastError.set("");
    } else {
      setError(errors[0]);
    }
  } catch (error) {
    setError(error);
  } finally {
    setLoading("predictionDetail", false);
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
        benchmark_symbol: options.benchmarkSymbol,
        include_monte_carlo: options.includeMonteCarlo ?? true
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
    ivSurface.update((current) => {
      if (session.running || hasRenderableIvSurface(session.surface)) {
        return session.surface;
      }
      return current;
    });
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
