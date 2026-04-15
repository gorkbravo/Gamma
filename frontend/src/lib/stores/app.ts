import { get, writable } from "svelte/store";
import { deleteJson, getJson, postJson } from "../api/client";
import { normalizeCopilotResearchCardResult } from "../copilot-result";
import type {
  ActionResponse,
  BaseCurrencyResponse,
  CopilotBaseDomain,
  CopilotDomain,
  CopilotResearchCardResult,
  CopilotThreadEntry,
  CopilotThreadState,
  CryptoComparison,
  CryptoDexLiquiditySummary,
  CryptoFlowSummary,
  CryptoPriceHistoryResponse,
  CryptoSyntheticPortfolio,
  CryptoToken,
  CryptoWorkspaceResponse,
  DiagnosticsResponse,
  FundamentalsDcfModel,
  FundamentalsFinancials,
  FundamentalsOverview,
  FundamentalsPeerBasket,
  FundamentalsSearchResponse,
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
  ResearchCompareResult,
  ResearchOverviewResponse,
  ResearchResult,
  RiskResult,
  SavedResearchDeleteResponse,
  SavedResearchItem,
  SavedResearchListResponse,
  StrategyLabResult,
  SystemStatus,
  TabId,
  WorkspaceMode
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

export interface ResearchOverviewLoadOptions {
  universeId?: string;
  timeframe?: string;
  benchmarkSymbol?: string;
  forceRefresh?: boolean;
}

export interface StrategyLabAnalyzeOptions {
  name: string;
  rows: Array<Record<string, string | number | null>>;
  dateColumn: string;
  valueColumn: string;
  valueKind: "return" | "level";
  benchmarkColumn?: string | null;
  benchmarkValueKind?: "return" | "level";
  minObservations?: number;
}

export interface ResearchCompareLegInput {
  label: string;
  objectType: string;
  returnPoints?: Array<{ timestamp: string; value: number }>;
  savedResearchId?: string | null;
}

export interface ResearchCompareOptions {
  left: ResearchCompareLegInput;
  right: ResearchCompareLegInput;
}

export interface SavedResearchCreateOptions {
  objectType: string;
  title: string;
  notes?: string;
  payload: Record<string, unknown>;
  warnings?: string[];
  sourceProvider?: string;
  origin?: string;
  transformationNote?: string | null;
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

export type PredictionMarketSortBy = NonNullable<PredictionMarketScreenerOptions["sortBy"]>;

export interface CryptoWorkspaceLoadOptions {
  query?: string;
  narrative?: string;
  chain?: string;
  minMarketCap?: number;
  minVolume?: number;
  minTurnoverRatio?: number;
  sortBy?: "market_cap_desc" | "volume_desc" | "turnover_desc" | "momentum_desc" | "screen_score_desc" | "fdv_premium_asc";
  limit?: number;
  forceRefresh?: boolean;
}

export type CryptoSortBy = NonNullable<CryptoWorkspaceLoadOptions["sortBy"]>;

export interface CryptoSyntheticPositionInput {
  identifier: string;
  weight: number;
}

export interface CryptoTokenSelectOptions {
  resetThread?: boolean;
  historyDays?: number;
}

export interface CryptoSyntheticPortfolioRunOptions {
  positions: CryptoSyntheticPositionInput[];
  benchmarkTokenId?: string;
  lookbackDays?: number;
  forceRefresh?: boolean;
}

export interface MacroLoadOptions {
  region?: MacroContextState["region"];
  timeframe?: MacroContextState["timeframe"];
  theme?: MacroContextState["theme"];
  comparisonRegion?: MacroContextState["comparisonRegion"];
  mode?: MacroContextState["mode"];
  forceRefresh?: boolean;
}

export interface FundamentalsSearchOptions {
  query?: string;
  limit?: number;
  forceRefresh?: boolean;
}

export interface FundamentalsSelectOptions {
  resetThread?: boolean;
  forceRefresh?: boolean;
}

export interface FundamentalsDcfScenarioSaveInput {
  assumptions: Record<string, unknown>;
  overrides: Record<string, Array<number | null>>;
}

export interface FundamentalsDcfSavePayload {
  activeScenarioId: string;
  projectionYears: number[];
  scenarios: Record<string, FundamentalsDcfScenarioSaveInput>;
}

function createEmptyCopilotThread(domain: CopilotDomain): CopilotThreadState {
  return {
    domain,
    contextFingerprint: null,
    latestResponseId: null,
    entries: []
  };
}

function createEmptyCopilotThreads(): Record<CopilotDomain, CopilotThreadState> {
  return {
    portfolio: createEmptyCopilotThread("portfolio"),
    research: createEmptyCopilotThread("research"),
    macro: createEmptyCopilotThread("macro"),
    prediction_markets: createEmptyCopilotThread("prediction_markets"),
    crypto: createEmptyCopilotThread("crypto"),
    fundamentals: createEmptyCopilotThread("fundamentals"),
    risk: createEmptyCopilotThread("risk"),
    iv: createEmptyCopilotThread("iv"),
    synthesis: createEmptyCopilotThread("synthesis")
  };
}

export const activeTab = writable<TabId>("portfolio");
export const systemStatus = writable<SystemStatus | null>(null);
export const diagnostics = writable<DiagnosticsResponse | null>(null);
export const diagnosticsLog = writable<string[]>([]);
export const portfolioSnapshot = writable<PortfolioSnapshot | null>(null);
export const portfolioHistory = writable<PortfolioHistoryResponse | null>(null);
export const portfolioPerformance = writable<PortfolioPerformanceResponse | null>(null);
export const researchOverview = writable<ResearchOverviewResponse | null>(null);
export const researchResult = writable<ResearchResult | null>(null);
export const strategyLabResult = writable<StrategyLabResult | null>(null);
export const researchCompareResult = writable<ResearchCompareResult | null>(null);
export const savedResearchItems = writable<SavedResearchItem[]>([]);
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
export const cryptoWorkspace = writable<CryptoWorkspaceResponse | null>(null);
export const selectedCryptoTokenId = writable<string | null>(null);
export const cryptoTokenDetail = writable<CryptoToken | null>(null);
export const cryptoPriceHistory = writable<CryptoPriceHistoryResponse | null>(null);
export const cryptoLiquidity = writable<CryptoDexLiquiditySummary | null>(null);
export const cryptoFlowSummary = writable<CryptoFlowSummary | null>(null);
export const cryptoComparison = writable<CryptoComparison | null>(null);
export const cryptoSyntheticPortfolio = writable<CryptoSyntheticPortfolio | null>(null);
export const fundamentalsSearch = writable<FundamentalsSearchResponse | null>(null);
export const selectedFundamentalsTicker = writable<string | null>(null);
export const fundamentalsOverview = writable<FundamentalsOverview | null>(null);
export const fundamentalsFinancials = writable<FundamentalsFinancials | null>(null);
export const fundamentalsDcfModel = writable<FundamentalsDcfModel | null>(null);
export const copilotCards = writable<Record<CopilotDomain, CopilotResearchCardResult | null>>({
  portfolio: null,
  research: null,
  macro: null,
  prediction_markets: null,
  crypto: null,
  fundamentals: null,
  risk: null,
  iv: null,
  synthesis: null
});
export const copilotThreads = writable<Record<CopilotDomain, CopilotThreadState>>(createEmptyCopilotThreads());
export const researchDraft = writable<ResearchDraftState>({
  scopeType: "single_ticker",
  primarySymbol: "AAPL",
  benchmarkSymbol: "SPY",
  lookbackDays: 252,
  syntheticText: "SPY 0.60\nQQQ 0.40",
  selectedPreset: "index-core"
});
export const riskResult = writable<RiskResult | null>(null);
export const riskSnapshotBasis = writable<PortfolioSnapshot | null>(null);
export const riskWorkspaceBasis = writable<WorkspaceMode | null>(null);
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
  researchOverview: false,
  research: false,
  strategyLab: false,
  compareScenario: false,
  savedResearch: false,
  macro: false,
  macroHistory: false,
  prediction: false,
  predictionDetail: false,
  crypto: false,
  cryptoDetail: false,
  cryptoPortfolio: false,
  fundamentals: false,
  fundamentalsSave: false,
  copilot: false,
  risk: false,
  iv: false,
  ivSession: false
});

const macroWorkspaceInflight = new Map<string, Promise<MacroSnapshot | null>>();
const macroSeriesInflight = new Map<string, Promise<MacroSeriesHistory | null>>();
const DEFAULT_MACRO_SNAPSHOT_FX_SERIES = ["fx-eurusd", "fx-gbpusd", "fx-usdjpy"] as const;
const MACRO_CROSS_ASSET_SERIES: Record<MacroContextState["region"], readonly string[]> = {
  US: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
  EU: ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "eu-industrial-production-yoy"],
  Global: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"]
};
const MACRO_RATES_POLICY_SERIES: Record<MacroContextState["region"], readonly string[]> = {
  US: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
  EU: ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-hicp-yoy", "eu-eurusd"],
  Global: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"]
};
const MACRO_COMPARISON_SERIES: Record<string, string> = {
  "us-2y-yield": "eu-3m-rate",
  "us-10y-yield": "eu-10y-yield",
  "us-real-10y-yield": "eu-hicp-yoy",
  "us-5y-breakeven": "eu-eurusd",
  "eu-3m-rate": "us-2y-yield",
  "eu-10y-yield": "us-10y-yield",
  "eu-hicp-yoy": "us-cpi-yoy",
  "eu-eurusd": "us-dollar-broad"
};

function setLoading(key: string, value: boolean) {
  loading.update((current) => ({ ...current, [key]: value }));
}

function resetCopilotCard(domain: CopilotDomain) {
  copilotCards.update((current) => ({ ...current, [domain]: null }));
  copilotThreads.update((current) => ({ ...current, [domain]: createEmptyCopilotThread(domain) }));
}

export function setResearchDraft(nextDraft: ResearchDraftState) {
  researchDraft.set(nextDraft);
}

export function setMacroContext(nextContext: Partial<MacroContextState>) {
  macroContext.update((current) => normalizeMacroContextState({ ...current, ...nextContext }));
  resetCopilotCard("macro");
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

function resolvedIvSurface() {
  const directSurface = get(ivSurface);
  if (hasRenderableIvSurface(directSurface)) {
    return directSurface;
  }
  const sessionSurface = get(ivSession)?.surface ?? null;
  return hasRenderableIvSurface(sessionSurface) ? sessionSurface : directSurface ?? sessionSurface;
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

function lastItem<T>(items: readonly T[]) {
  return items.length ? items[items.length - 1] : undefined;
}

function serializePositionSignature(snapshot: PortfolioSnapshot | null | undefined) {
  return (snapshot?.positions ?? []).map((position) => ({
    symbol: position.symbol,
    quantity: position.quantity,
    weight: position.weight ?? null,
    baseMarketValue: position.base_market_value ?? null
  }));
}

const COPILOT_DOMAIN_LABELS: Record<CopilotBaseDomain, string> = {
  portfolio: "Portfolio",
  research: "Research",
  macro: "Macro",
  prediction_markets: "Prediction Markets",
  crypto: "Crypto",
  fundamentals: "Fundamentals",
  risk: "Risk",
  iv: "IV"
};

function buildCopilotContextFingerprint(
  domain: CopilotDomain,
  workspaceMode: WorkspaceMode | null | undefined,
  options: { synthesisDomains?: CopilotBaseDomain[]; activeTabId?: TabId } = {}
) {
  if (domain === "synthesis") {
    const includedDomains = normalizeSynthesisDomains(options.synthesisDomains);
    return JSON.stringify({
      domain,
      workspaceMode,
      activeTab: options.activeTabId ?? get(activeTab),
      includedContexts: includedDomains.map((includedDomain) => ({
        domain: includedDomain,
        fingerprint: buildCopilotContextFingerprint(includedDomain, workspaceMode)
      }))
    });
  }

  if (domain === "portfolio") {
    const snapshot = get(portfolioSnapshot);
    const performance = get(portfolioPerformance);
    return JSON.stringify({
      domain,
      workspaceMode,
      baseCurrency: snapshot?.base_currency ?? null,
      snapshotTimestamp: snapshot?.timestamp ?? null,
      netLiquidation: snapshot?.net_liquidation ?? null,
      positions: serializePositionSignature(snapshot),
      benchmarkSymbol: performance?.benchmark_symbol ?? null,
      performancePoints: performance?.performance_points.length ?? 0,
      performanceTimestamp: lastItem(performance?.performance_points ?? [])?.timestamp ?? null
    });
  }

  if (domain === "research") {
    const result = get(researchResult);
    return JSON.stringify({
      domain,
      workspaceMode,
      scopeType: result?.scope_type ?? null,
      primarySymbol: result?.primary_symbol ?? null,
      benchmarkSymbol: result?.benchmark_symbol ?? null,
      snapshotTimestamp: result?.snapshot?.timestamp ?? null,
      weights: (result?.weights ?? []).map((weight) => ({
        symbol: weight.symbol,
        weight: weight.weight
      }))
    });
  }

  if (domain === "macro") {
    const macro = get(macroContext);
    return JSON.stringify({
      domain,
      mode: macro.mode,
      region: macro.region,
      timeframe: macro.timeframe,
      theme: macro.theme,
      comparisonRegion: macro.comparisonRegion
    });
  }

  if (domain === "prediction_markets") {
    return JSON.stringify({
      domain,
      marketId: get(selectedPredictionMarketId)
    });
  }

  if (domain === "crypto") {
    const detail = get(cryptoTokenDetail);
    const history = get(cryptoPriceHistory);
    const comparison = get(cryptoComparison);
    return JSON.stringify({
      domain,
      tokenId: get(selectedCryptoTokenId),
      retrievedAt: detail?.retrieved_at ?? null,
      historyPoints: history?.points.length ?? 0,
      historyTimestamp: lastItem(history?.points ?? [])?.timestamp ?? null,
      comparisonTarget: comparison?.target_id ?? null
    });
  }

  if (domain === "fundamentals") {
    const overview = get(fundamentalsOverview);
    const dcf = get(fundamentalsDcfModel);
    return JSON.stringify({
      domain,
      workspaceMode,
      ticker: get(selectedFundamentalsTicker),
      companyTicker: overview?.company.ticker ?? null,
      companyName: overview?.company.name ?? null,
      overviewRetrievedAt: overview?.company.retrieved_at ?? null,
      dcfRetrievedAt: dcf?.retrieved_at ?? null,
      activeScenarioId: dcf?.active_scenario_id ?? null
    });
  }

  if (domain === "risk") {
    const snapshot = get(riskSnapshotBasis);
    const result = get(riskResult);
    return JSON.stringify({
      domain,
      workspaceMode: get(riskWorkspaceBasis) ?? workspaceMode ?? null,
      snapshotTimestamp: snapshot?.timestamp ?? null,
      positions: serializePositionSignature(snapshot),
      alpha: result?.metrics.alpha ?? null,
      lookbackDays: result?.metrics.lookback_days ?? null,
      horizonDays: result?.metrics.horizon_days ?? null,
      monteCarloModel: result?.metrics.monte_carlo_model ?? null
    });
  }

  const surface = resolvedIvSurface();
  const session = get(ivSession);
  return JSON.stringify({
    domain,
    workspaceMode,
    symbol: surface?.symbol ?? session?.active_symbol ?? null,
    expiries: surface?.expiries ?? [],
    strikeCount: surface?.strikes.length ?? 0,
    marketDataMode: session?.market_data_mode ?? null
  });
}

export function previewCopilotContextFingerprint(
  domain: CopilotBaseDomain,
  options: { workspaceMode?: WorkspaceMode | null } = {}
) {
  return buildCopilotContextFingerprint(domain, options.workspaceMode);
}

export function previewCopilotThreadFingerprint(
  domain: CopilotDomain,
  options: CopilotLoadOptions = {}
) {
  return buildCopilotContextFingerprint(domain, options.workspaceMode, {
    synthesisDomains: options.synthesisDomains,
    activeTabId: options.activeTabId
  });
}

function buildCopilotThreadEntry(
  domain: CopilotDomain,
  result: CopilotResearchCardResult,
  prompt: string,
  previousResponseId: string | null,
  turnIndex: number
): CopilotThreadEntry {
  const stableResponseId =
    typeof result.response_id === "string" && result.response_id.trim().length > 0
      ? result.response_id
      : null;
  return {
    entryId:
      stableResponseId ??
      `${domain}-${turnIndex}-${Date.now().toString(36)}`,
    turnIndex,
    prompt: prompt.trim(),
    continuedFromResponseId: previousResponseId,
    result
  };
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
      strategyLabResult.set(null);
      researchCompareResult.set(null);
      riskResult.set(null);
      riskSnapshotBasis.set(null);
      riskWorkspaceBasis.set(null);
      resetCopilotCard("portfolio");
      resetCopilotCard("research");
      resetCopilotCard("risk");
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
      resetCopilotCard("portfolio");
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
    resetCopilotCard("portfolio");
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("portfolio", false);
  }
}

export async function loadResearchOverview(options: ResearchOverviewLoadOptions = {}) {
  setLoading("researchOverview", true);
  try {
    const params = new URLSearchParams({
      universe_id: options.universeId ?? "broad_us_market",
      timeframe: options.timeframe ?? "3M",
      benchmark_symbol: options.benchmarkSymbol ?? "SPY"
    });
    if (options.forceRefresh) {
      params.set("force_refresh", "true");
    }
    const overview = await getJson<ResearchOverviewResponse>(`/research/overview?${params.toString()}`);
    researchOverview.set(overview);
    lastError.set("");
    return overview;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("researchOverview", false);
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
    researchCompareResult.set(null);
    // Downstream analysis must be recomputed from the latest executed research scope.
    riskResult.set(null);
    riskSnapshotBasis.set(null);
    riskWorkspaceBasis.set(null);
    resetCopilotCard("research");
    resetCopilotCard("risk");
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("research", false);
  }
}

export async function analyzeStrategyLab(options: StrategyLabAnalyzeOptions) {
  setLoading("strategyLab", true);
  try {
    const result = await postJson<StrategyLabResult>("/research/strategy-lab/analyze", {
      name: options.name,
      rows: options.rows,
      date_column: options.dateColumn,
      value_column: options.valueColumn,
      value_kind: options.valueKind,
      benchmark_column: options.benchmarkColumn || null,
      benchmark_value_kind: options.benchmarkValueKind ?? "return",
      min_observations: options.minObservations ?? 5
    });
    strategyLabResult.set(result);
    researchCompareResult.set(null);
    resetCopilotCard("research");
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("strategyLab", false);
  }
}

export async function compareResearch(options: ResearchCompareOptions) {
  setLoading("compareScenario", true);
  try {
    const payload = {
      left: serializeCompareLeg(options.left),
      right: serializeCompareLeg(options.right)
    };
    const result = await postJson<ResearchCompareResult>("/research/compare-scenario/analyze", payload);
    researchCompareResult.set(result);
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("compareScenario", false);
  }
}

function serializeCompareLeg(leg: ResearchCompareLegInput) {
  return {
    label: leg.label,
    object_type: leg.objectType,
    return_points: leg.returnPoints ?? [],
    saved_research_id: leg.savedResearchId ?? null
  };
}

export async function loadSavedResearch() {
  setLoading("savedResearch", true);
  try {
    const response = await getJson<SavedResearchListResponse>("/research/saved");
    savedResearchItems.set(response.items);
    lastError.set("");
    return response.items;
  } catch (error) {
    setError(error);
    return [];
  } finally {
    setLoading("savedResearch", false);
  }
}

export async function saveResearchItem(options: SavedResearchCreateOptions) {
  setLoading("savedResearch", true);
  try {
    const item = await postJson<SavedResearchItem>("/research/saved", {
      object_type: options.objectType,
      title: options.title,
      notes: options.notes ?? "",
      payload: options.payload,
      warnings: options.warnings ?? [],
      source_provider: options.sourceProvider ?? "gamma_saved_research",
      origin: options.origin ?? "frontend.research.saved",
      transformation_note: options.transformationNote ?? null
    });
    savedResearchItems.update((current) => [item, ...current.filter((existing) => existing.id !== item.id)]);
    lastError.set("");
    return item;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("savedResearch", false);
  }
}

export async function deleteSavedResearchItem(itemId: string) {
  setLoading("savedResearch", true);
  try {
    const response = await deleteJson<SavedResearchDeleteResponse>(`/research/saved/${encodeURIComponent(itemId)}`);
    if (response.success) {
      savedResearchItems.update((current) => current.filter((item) => item.id !== itemId));
    }
    lastError.set("");
    return response.success;
  } catch (error) {
    setError(error);
    return false;
  } finally {
    setLoading("savedResearch", false);
  }
}

function normalizeMacroContextState(context: MacroContextState): MacroContextState {
  const normalizedComparison =
    context.region === "Global" || context.comparisonRegion == null || context.comparisonRegion === context.region || context.comparisonRegion === "Global"
      ? null
      : context.comparisonRegion;
  return {
    ...context,
    comparisonRegion: normalizedComparison
  };
}

function macroPayloadFromContext(context: MacroContextState, forceRefresh = false) {
  return {
    region: context.region,
    timeframe: context.timeframe,
    theme: context.theme,
    comparison_region: context.comparisonRegion,
    force_refresh: forceRefresh
  };
}

function macroHistoryKey(seriesId: string, region: string, timeframe: string) {
  return `${region}:${timeframe}:${seriesId}`;
}

async function prefetchMacroSeries(seriesIds: readonly string[], options: MacroLoadOptions = {}) {
  const uniqueSeriesIds = Array.from(new Set(seriesIds));
  if (!uniqueSeriesIds.length) {
    return;
  }
  await Promise.all(uniqueSeriesIds.map((seriesId) => loadMacroSeriesHistory(seriesId, options)));
}

function seriesForMacroMode(context: MacroContextState) {
  if (context.mode === "snapshot") {
    return [...DEFAULT_MACRO_SNAPSHOT_FX_SERIES];
  }
  if (context.mode === "events_regimes") {
    return [];
  }
  if (context.mode === "cross_asset") {
    return [...MACRO_CROSS_ASSET_SERIES[context.region]];
  }
  return [...MACRO_RATES_POLICY_SERIES[context.region]];
}

function comparisonSeriesForContext(context: MacroContextState, seriesIds: readonly string[]) {
  if (!context.comparisonRegion || context.region === "Global") {
    return [];
  }
  return seriesIds
    .map((seriesId) => MACRO_COMPARISON_SERIES[seriesId])
    .filter((seriesId): seriesId is string => Boolean(seriesId));
}

export async function loadMacroWorkspace(options: MacroLoadOptions = {}) {
  const previousContext = get(macroContext);
  const nextContext = normalizeMacroContextState({
    ...previousContext,
    ...(options.mode ? { mode: options.mode } : {}),
    ...(options.region ? { region: options.region } : {}),
    ...(options.timeframe ? { timeframe: options.timeframe } : {}),
    ...(options.theme ? { theme: options.theme } : {}),
    ...(options.comparisonRegion !== undefined ? { comparisonRegion: options.comparisonRegion } : {})
  });
  macroContext.set(nextContext);
  if (JSON.stringify(previousContext) !== JSON.stringify(nextContext)) {
    resetCopilotCard("macro");
  }
  const payload = macroPayloadFromContext(nextContext, options.forceRefresh ?? false);
  const requestKey = JSON.stringify(payload);
  const existingRequest = macroWorkspaceInflight.get(requestKey);
  if (existingRequest) {
    return existingRequest;
  }
  const requestPromise = (async () => {
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
        const primarySeries = seriesForMacroMode(nextContext);
        if (primarySeries.length) {
          await prefetchMacroSeries(primarySeries, {
            region: nextContext.region,
            timeframe: nextContext.timeframe,
            theme: nextContext.theme,
            comparisonRegion: nextContext.comparisonRegion,
            forceRefresh: options.forceRefresh ?? false
          });
        }
        const comparisonSeries = comparisonSeriesForContext(nextContext, primarySeries);
        if (comparisonSeries.length && nextContext.comparisonRegion) {
          await prefetchMacroSeries(comparisonSeries, {
            region: nextContext.comparisonRegion,
            timeframe: nextContext.timeframe,
            theme: nextContext.theme,
            comparisonRegion: nextContext.comparisonRegion,
            forceRefresh: options.forceRefresh ?? false
          });
        }
        lastError.set("");
        return snapshot;
      } catch (error) {
      setError(error);
      return null;
    } finally {
      setLoading("macro", false);
      macroWorkspaceInflight.delete(requestKey);
    }
  })();
  macroWorkspaceInflight.set(requestKey, requestPromise);
  return requestPromise;
}

export async function loadMacroSeriesHistory(seriesId: string, options: MacroLoadOptions = {}) {
  const nextContext = normalizeMacroContextState({
    ...get(macroContext),
    ...(options.region ? { region: options.region } : {}),
    ...(options.timeframe ? { timeframe: options.timeframe } : {}),
    ...(options.theme ? { theme: options.theme } : {}),
    ...(options.comparisonRegion !== undefined ? { comparisonRegion: options.comparisonRegion } : {})
  });
  const payload = macroPayloadFromContext(nextContext, options.forceRefresh ?? false);
  const cacheKey = macroHistoryKey(seriesId, payload.region, payload.timeframe);
  const requestKey = `${cacheKey}:${payload.force_refresh ? "refresh" : "cached"}`;
  const existingRequest = macroSeriesInflight.get(requestKey);
  if (existingRequest) {
    return existingRequest;
  }
  const requestPromise = (async () => {
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
      macroSeriesInflight.delete(requestKey);
    }
  })();
  macroSeriesInflight.set(requestKey, requestPromise);
  return requestPromise;
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
      await selectPredictionMarket(nextSelection, {
        resetThread: nextSelection !== currentSelection || get(predictionMarketDetail) == null
      });
    } else {
      selectedPredictionMarketId.set(null);
      predictionMarketDetail.set(null);
      predictionMarketHistory.set(null);
      predictionMarketWallet.set(null);
      predictionMarketRelated.set(null);
      predictionMarketCalibration.set(null);
      resetCopilotCard("prediction_markets");
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

export async function selectPredictionMarket(
  marketId: string,
  options: { resetThread?: boolean } = {}
) {
  selectedPredictionMarketId.set(marketId);
  if (options.resetThread ?? true) {
    resetCopilotCard("prediction_markets");
  }
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

export async function loadCryptoWorkspace(options: CryptoWorkspaceLoadOptions = {}) {
  setLoading("crypto", true);
  try {
    const response = await postJson<CryptoWorkspaceResponse>("/crypto/workspace", {
      query: options.query ?? "",
      narrative: options.narrative ?? null,
      chain: options.chain ?? null,
      min_market_cap: options.minMarketCap ?? null,
      min_volume: options.minVolume ?? null,
      min_turnover_ratio: options.minTurnoverRatio ?? null,
      sort_by: options.sortBy ?? "market_cap_desc",
      limit: options.limit ?? 40,
      force_refresh: options.forceRefresh ?? false
    });
    cryptoWorkspace.set(response);
    const currentSelection = get(selectedCryptoTokenId);
    const selectedStillVisible = response.tokens.some((token) => token.token_id === currentSelection);
    const nextSelection = selectedStillVisible ? currentSelection : (response.tokens[0]?.token_id ?? null);
    if (nextSelection) {
      await selectCryptoToken(nextSelection, {
        resetThread: nextSelection !== currentSelection || get(cryptoTokenDetail) == null
      });
    } else {
      selectedCryptoTokenId.set(null);
      cryptoTokenDetail.set(null);
      cryptoPriceHistory.set(null);
      cryptoLiquidity.set(null);
      cryptoFlowSummary.set(null);
      cryptoComparison.set(null);
      cryptoSyntheticPortfolio.set(null);
      resetCopilotCard("crypto");
    }
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("crypto", false);
  }
}

export async function selectCryptoToken(
  tokenId: string,
  options: CryptoTokenSelectOptions = {}
) {
  selectedCryptoTokenId.set(tokenId);
  if (options.resetThread ?? true) {
    resetCopilotCard("crypto");
  }
  setLoading("cryptoDetail", true);
  try {
    const historyDays = Math.min(Math.max(options.historyDays ?? 30, 7), 365);
    const [detailResult, historyResult, liquidityResult, flowResult, comparisonResult] = await Promise.allSettled([
      getJson<CryptoToken>(`/crypto/tokens/${tokenId}`),
      getJson<CryptoPriceHistoryResponse>(`/crypto/tokens/${tokenId}/history?days=${historyDays}`),
      getJson<CryptoDexLiquiditySummary>(`/crypto/tokens/${tokenId}/liquidity`),
      getJson<CryptoFlowSummary>(`/crypto/tokens/${tokenId}/flow`),
      getJson<CryptoComparison>(`/crypto/tokens/${tokenId}/comparison`)
    ]);

    const errors: unknown[] = [];

    if (detailResult.status === "fulfilled") {
      cryptoTokenDetail.set(detailResult.value);
    } else {
      cryptoTokenDetail.set(null);
      errors.push(detailResult.reason);
    }
    if (historyResult.status === "fulfilled") {
      cryptoPriceHistory.set(historyResult.value);
    } else {
      cryptoPriceHistory.set(null);
      errors.push(historyResult.reason);
    }
    if (liquidityResult.status === "fulfilled") {
      cryptoLiquidity.set(liquidityResult.value);
    } else {
      cryptoLiquidity.set(null);
      errors.push(liquidityResult.reason);
    }
    if (flowResult.status === "fulfilled") {
      cryptoFlowSummary.set(flowResult.value);
    } else {
      cryptoFlowSummary.set(null);
      errors.push(flowResult.reason);
    }
    if (comparisonResult.status === "fulfilled") {
      cryptoComparison.set(comparisonResult.value);
    } else {
      cryptoComparison.set(null);
      errors.push(comparisonResult.reason);
    }

    if (errors.length === 0) {
      lastError.set("");
    } else {
      setError(errors[0]);
    }
  } catch (error) {
    setError(error);
  } finally {
    setLoading("cryptoDetail", false);
  }
}

export function clearCryptoSyntheticPortfolio() {
  cryptoSyntheticPortfolio.set(null);
}

export async function runCryptoSyntheticPortfolio(
  options: CryptoSyntheticPortfolioRunOptions
) {
  setLoading("cryptoPortfolio", true);
  try {
    const response = await postJson<CryptoSyntheticPortfolio>("/crypto/portfolio", {
      positions: options.positions.map((position) => ({
        identifier: position.identifier,
        weight: position.weight
      })),
      benchmark_token_id: options.benchmarkTokenId ?? null,
      lookback_days: options.lookbackDays ?? 30,
      force_refresh: options.forceRefresh ?? false
    });
    cryptoSyntheticPortfolio.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    cryptoSyntheticPortfolio.set(null);
    setError(error);
    return null;
  } finally {
    setLoading("cryptoPortfolio", false);
  }
}

export async function loadFundamentalsSearch(options: FundamentalsSearchOptions = {}) {
  setLoading("fundamentals", true);
  try {
    const params = new URLSearchParams({
      query: options.query ?? "",
      limit: String(options.limit ?? 12),
      force_refresh: options.forceRefresh ? "true" : "false"
    });
    const response = await getJson<FundamentalsSearchResponse>(`/fundamentals/search?${params.toString()}`);
    fundamentalsSearch.set(response);
    const currentSelection = get(selectedFundamentalsTicker);
    const selectedStillVisible = response.results.some((result) => result.ticker === currentSelection);
    const nextSelection =
      selectedStillVisible
        ? currentSelection
        : (response.results[0]?.ticker ?? currentSelection);
    if (nextSelection) {
      await selectFundamentalsCompany(nextSelection, {
        resetThread: nextSelection !== currentSelection || get(fundamentalsOverview) == null,
        forceRefresh: options.forceRefresh
      });
    } else {
      selectedFundamentalsTicker.set(null);
      fundamentalsOverview.set(null);
      fundamentalsFinancials.set(null);
      fundamentalsDcfModel.set(null);
      resetCopilotCard("fundamentals");
    }
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentals", false);
  }
}

export async function selectFundamentalsCompany(
  ticker: string,
  options: FundamentalsSelectOptions = {}
) {
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!normalizedTicker) {
    return null;
  }
  selectedFundamentalsTicker.set(normalizedTicker);
  if (options.resetThread ?? true) {
    resetCopilotCard("fundamentals");
  }
  setLoading("fundamentals", true);
  try {
    const querySuffix = options.forceRefresh ? "?force_refresh=true" : "";
    const [overviewResult, financialsResult, dcfResult] = await Promise.allSettled([
      getJson<FundamentalsOverview>(`/fundamentals/${normalizedTicker}/overview${querySuffix}`),
      getJson<FundamentalsFinancials>(`/fundamentals/${normalizedTicker}/financials${querySuffix}`),
      getJson<FundamentalsDcfModel>(`/fundamentals/${normalizedTicker}/dcf${querySuffix}`)
    ]);

    const errors: unknown[] = [];

    if (overviewResult.status === "fulfilled") {
      fundamentalsOverview.set(overviewResult.value);
    } else {
      fundamentalsOverview.set(null);
      errors.push(overviewResult.reason);
    }

    if (financialsResult.status === "fulfilled") {
      fundamentalsFinancials.set(financialsResult.value);
    } else {
      fundamentalsFinancials.set(null);
      errors.push(financialsResult.reason);
    }

    if (dcfResult.status === "fulfilled") {
      fundamentalsDcfModel.set(dcfResult.value);
    } else {
      fundamentalsDcfModel.set(null);
      errors.push(dcfResult.reason);
    }

    if (errors.length === 0) {
      lastError.set("");
    } else {
      setError(errors[0]);
    }
    return {
      overview: overviewResult.status === "fulfilled" ? overviewResult.value : null,
      financials: financialsResult.status === "fulfilled" ? financialsResult.value : null,
      dcf: dcfResult.status === "fulfilled" ? dcfResult.value : null
    };
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentals", false);
  }
}

export async function saveFundamentalsPeerBasket(ticker: string, peerTickers: string[]) {
  const normalizedTicker = ticker.trim().toUpperCase();
  setLoading("fundamentalsSave", true);
  try {
    const response = await postJson<FundamentalsPeerBasket>(`/fundamentals/${normalizedTicker}/peers`, {
      peer_tickers: peerTickers
    });
    await selectFundamentalsCompany(normalizedTicker, { resetThread: false });
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentalsSave", false);
  }
}

export async function saveFundamentalsDcfModel(ticker: string, payload: FundamentalsDcfSavePayload) {
  const normalizedTicker = ticker.trim().toUpperCase();
  setLoading("fundamentalsSave", true);
  try {
    const response = await postJson<FundamentalsDcfModel>(`/fundamentals/${normalizedTicker}/dcf`, {
      active_scenario_id: payload.activeScenarioId,
      projection_years: payload.projectionYears,
      scenarios: Object.fromEntries(
        Object.entries(payload.scenarios).map(([scenarioId, value]) => [
          scenarioId,
          {
            assumptions: value.assumptions,
            overrides: value.overrides
          }
        ])
      )
    });
    fundamentalsDcfModel.set(response);
    fundamentalsOverview.update((current) =>
      current == null
        ? current
        : {
            ...current,
            dcf_summary: response.scenarios
              .map((scenario) => scenario.summary)
              .filter((summary): summary is NonNullable<typeof summary> => summary != null)
          }
    );
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentalsSave", false);
  }
}

export async function computeRisk(options: RiskComputeOptions) {
  const snapshot = options.snapshot ?? get(portfolioSnapshot) ?? get(researchResult)?.snapshot ?? null;
  if (!snapshot) {
    lastError.set("Load or build a snapshot before computing risk.");
    return;
  }
  const snapshotWorkspace: WorkspaceMode =
    snapshot === get(researchResult)?.snapshot
      ? "research"
      : "portfolio";
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
    riskSnapshotBasis.set(snapshot);
    riskWorkspaceBasis.set(snapshotWorkspace);
    resetCopilotCard("risk");
    lastError.set("");
  } catch (error) {
    setError(error);
  } finally {
    setLoading("risk", false);
  }
}

function getCopilotSessionId() {
  if (typeof localStorage === "undefined") {
    return "gamma-copilot-session";
  }
  const existing = localStorage.getItem("gamma.copilot.session");
  if (existing) {
    return existing;
  }
  const nextId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `gamma-${Date.now()}`;
  localStorage.setItem("gamma.copilot.session", nextId);
  return nextId;
}

type CopilotLoadOptions = {
  workspaceMode?: WorkspaceMode | null;
  synthesisDomains?: CopilotBaseDomain[];
  activeTabId?: TabId;
};

function normalizeSynthesisDomains(domains: CopilotBaseDomain[] | undefined) {
  const seen = new Set<CopilotBaseDomain>();
  const ordered: CopilotBaseDomain[] = [];
  for (const domain of domains ?? []) {
    if (seen.has(domain)) {
      continue;
    }
    seen.add(domain);
    ordered.push(domain);
  }
  return ordered;
}

function buildCopilotContext(domain: CopilotDomain, workspaceMode: WorkspaceMode | null | undefined) {
  switch (domain) {
    case "portfolio":
      return {
        current_tab: "portfolio",
        workspace_mode: workspaceMode,
        portfolio_state: {
          snapshot: get(portfolioSnapshot),
          history: get(portfolioHistory),
          performance: get(portfolioPerformance)
        }
      };
    case "research":
      return {
        current_tab: "research",
        workspace_mode: workspaceMode,
        research_state: {
          result: get(researchResult)
        }
      };
    case "macro":
      return {
        current_tab: "macro",
        workspace_mode: workspaceMode,
        macro: {
          mode: get(macroContext).mode,
          region: get(macroContext).region,
          timeframe: get(macroContext).timeframe,
          theme: get(macroContext).theme,
          comparison_region: get(macroContext).comparisonRegion
        }
      };
    case "prediction_markets":
      return {
        current_tab: "prediction_markets",
        workspace_mode: workspaceMode,
        prediction_market_id: get(selectedPredictionMarketId)
      };
    case "crypto":
      return {
        current_tab: "crypto",
        workspace_mode: workspaceMode,
        crypto_token_id: get(selectedCryptoTokenId)
      };
    case "fundamentals":
      return {
        current_tab: "fundamentals",
        workspace_mode: workspaceMode,
        fundamentals_ticker: get(selectedFundamentalsTicker)
      };
    case "risk":
      return {
        current_tab: "risk",
        workspace_mode: get(riskWorkspaceBasis) ?? workspaceMode,
        risk_state: {
          snapshot: get(riskSnapshotBasis),
          result: get(riskResult)
        }
      };
    case "iv":
      return {
        current_tab: "iv",
        workspace_mode: workspaceMode,
        iv_state: {
          surface: resolvedIvSurface(),
          session: get(ivSession)
        }
      };
    case "synthesis":
      return {
        current_tab: "synthesis",
        workspace_mode: workspaceMode
      };
  }
}

function buildCopilotSynthesisPayload(
  domains: CopilotBaseDomain[] | undefined,
  workspaceMode: WorkspaceMode | null | undefined,
  activeTabId: TabId | undefined
) {
  const includedScopes = normalizeSynthesisDomains(domains)
    .map((domain) => {
      const context = buildCopilotContext(domain, workspaceMode);
      if (!context) {
        return null;
      }
      return {
        domain,
        label: COPILOT_DOMAIN_LABELS[domain],
        context_fingerprint: buildCopilotContextFingerprint(domain, workspaceMode),
        context
      };
    })
    .filter((item): item is NonNullable<typeof item> => item != null);

  if (!includedScopes.length) {
    return null;
  }

  return {
    active_tab: activeTabId ?? get(activeTab),
    included_scopes: includedScopes
  };
}

function validateSynthesisScopeDomain(
  domain: CopilotBaseDomain,
  workspaceMode: WorkspaceMode | null | undefined
) {
  if (domain === "portfolio" && !get(portfolioSnapshot)) {
    return "Load the Portfolio context before including it in a synthesis card.";
  }
  if (domain === "research" && !get(researchResult)) {
    return "Run a Research analysis before including it in a synthesis card.";
  }
  if (domain === "macro" && !get(macroSnapshot)) {
    return "Load the Macro workspace before including it in a synthesis card.";
  }
  if (domain === "prediction_markets" && !get(predictionMarketDetail)) {
    return "Select and load a Prediction Markets contract before including it in a synthesis card.";
  }
  if (domain === "crypto" && !get(cryptoTokenDetail)) {
    return "Select and load a crypto token before including it in a synthesis card.";
  }
  if (domain === "fundamentals") {
    return "Fundamentals Copilot grounding is not implemented yet.";
  }
  if (domain === "risk" && !get(riskResult)) {
    return "Run a Risk computation before including it in a synthesis card.";
  }
  if (domain === "iv" && !hasRenderableIvSurface(resolvedIvSurface())) {
    return "Load an IV surface before including it in a synthesis card.";
  }
  const context = buildCopilotContext(domain, workspaceMode);
  return context ? null : `The ${COPILOT_DOMAIN_LABELS[domain]} context is unavailable.`;
}

function validateCopilotContext(domain: CopilotDomain, options: CopilotLoadOptions = {}) {
  if (domain === "synthesis") {
    const synthesisDomains = normalizeSynthesisDomains(options.synthesisDomains);
    if (synthesisDomains.length < 2) {
      return "Select at least two loaded Gamma contexts before generating a synthesis card.";
    }
    for (const synthesisDomain of synthesisDomains) {
      const validationError = validateSynthesisScopeDomain(synthesisDomain, options.workspaceMode);
      if (validationError) {
        return validationError;
      }
    }
    return buildCopilotSynthesisPayload(synthesisDomains, options.workspaceMode, options.activeTabId)
      ? null
      : "The active synthesis scope is unavailable.";
  }

  if (domain === "portfolio" && !get(portfolioSnapshot)) {
    return "Load a portfolio snapshot before generating a research card.";
  }
  if (domain === "research" && !get(researchResult)) {
    return "Run a research analysis before generating a research card.";
  }
  if (domain === "prediction_markets" && !get(selectedPredictionMarketId)) {
    return "Select a prediction market before generating a research card.";
  }
  if (domain === "crypto" && !get(selectedCryptoTokenId)) {
    return "Select a crypto token before generating a research card.";
  }
  if (domain === "fundamentals") {
    return "Fundamentals Copilot grounding is not implemented yet.";
  }
  if (domain === "risk" && !get(riskResult)) {
    return "Run a risk computation before generating a research card.";
  }
  if (domain === "iv" && !hasRenderableIvSurface(resolvedIvSurface())) {
    return "Load an IV surface before generating a research card.";
  }
  if (domain === "portfolio" || domain === "research" || domain === "crypto" || domain === "risk" || domain === "iv") {
    const context = buildCopilotContext(domain, options.workspaceMode);
    return context ? null : "The active Copilot context is unavailable.";
  }
  return null;
}

export async function loadCopilotResearchCard(
  domain: CopilotDomain,
  prompt = "",
  options: CopilotLoadOptions = {}
) {
  setLoading("copilot", true);
  try {
    const validationError = validateCopilotContext(domain, options);
    if (validationError) {
      lastError.set(validationError);
      return null;
    }
    const context = buildCopilotContext(domain, options.workspaceMode);
    if (!context) {
      lastError.set("The active Copilot context is unavailable.");
      return null;
    }

    const synthesis =
      domain === "synthesis"
        ? buildCopilotSynthesisPayload(options.synthesisDomains, options.workspaceMode, options.activeTabId)
        : null;
    if (domain === "synthesis" && !synthesis) {
      lastError.set("The active synthesis scope is unavailable.");
      return null;
    }

    const contextFingerprint = buildCopilotContextFingerprint(domain, options.workspaceMode, {
      synthesisDomains: options.synthesisDomains,
      activeTabId: options.activeTabId
    });
    const activeThread = get(copilotThreads)[domain];
    const continuingThread =
      activeThread.contextFingerprint != null &&
      activeThread.contextFingerprint === contextFingerprint &&
      activeThread.latestResponseId != null;
    const previousResponseId = continuingThread ? activeThread.latestResponseId : null;

    if (!continuingThread && activeThread.entries.length) {
      resetCopilotCard(domain);
    }

    const payload = {
      domain,
      prompt,
      user_session_id: getCopilotSessionId(),
      ...(previousResponseId ? { previous_response_id: previousResponseId } : {}),
      context,
      ...(synthesis ? { synthesis } : {})
    };

    const rawResult = await postJson<CopilotResearchCardResult>("/copilot/research-card", payload);
    const result = normalizeCopilotResearchCardResult(domain, rawResult);
    copilotCards.update((current) => ({ ...current, [domain]: result }));
    const baseThread =
      continuingThread
        ? activeThread
        : createEmptyCopilotThread(domain);
    const nextEntry = buildCopilotThreadEntry(
      domain,
      result,
      prompt,
      previousResponseId,
      baseThread.entries.length + 1
    );
    const latestResponseId =
      result.status === "ready" && result.response_id
        ? result.response_id
        : baseThread.latestResponseId;
    copilotThreads.update((current) => ({
      ...current,
      [domain]: {
        domain,
        contextFingerprint,
        latestResponseId,
        entries: [...baseThread.entries, nextEntry]
      }
    }));
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("copilot", false);
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
    resetCopilotCard("iv");
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
    resetCopilotCard("iv");
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
    resetCopilotCard("iv");
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
