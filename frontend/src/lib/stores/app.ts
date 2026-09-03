import { get, writable } from "svelte/store";
import { deleteJson, getJson, getNdjsonStream, getText, patchJson, postJson, postNdjsonStream, postText } from "../api/client";
import { normalizeCopilotResearchCardResult } from "../copilot-result";
import {
  createCopilotRunState,
  isTerminalCopilotRunEvent,
  reduceCopilotRunEvent,
  type CopilotRunState
} from "../copilot-run";
import { isAbortError, RequestCoordinator } from "../request-coordinator";
import { queryCache, stableQueryKey } from "../query-cache";
export { requestMetrics, resetRequestMetrics } from "../request-metrics";
export { queryStates } from "../query-cache";
export function clearFrontendQueryCache() { queryCache.clear(); }
import { beginLoading, endLoading, lastError, loading, setError, setLoading } from "./runtime";
import { researchScriptWorkspace } from "./research-script";
export { lastError, loading } from "./runtime";
import {
  diagnostics, diagnosticsLog, loadDiagnostics, loadProviderUsage, providerUsage,
  refreshSystemStatus, setMarketDataMode, systemStatus, toggleConnection
} from "./system";
export {
  diagnostics, diagnosticsLog, loadDiagnostics, loadProviderUsage, providerUsage,
  refreshSystemStatus, setMarketDataMode, systemStatus, toggleConnection
} from "./system";
import {
  loadPortfolioHistoryData, loadPortfolioPerformanceData, loadPortfolioSnapshotData,
  portfolioHistory, portfolioHistoryRequestState, portfolioPerformance,
  portfolioPerformanceRequestState, portfolioPreferences, portfolioSnapshot,
  portfolioSnapshotRequestState, updatePortfolioPreferences
} from "./portfolio";
export {
  portfolioHistory,
  portfolioHistoryRequestState,
  portfolioPerformance,
  portfolioPerformanceRequestState,
  portfolioPreferences,
  portfolioSnapshot,
  portfolioSnapshotRequestState,
  updatePortfolioPreferences
} from "./portfolio";
import { buildResearchBookObjectFromStrategyComposition } from "../view-models/research";
import {
  DEFAULT_CALIBRATION_LEAD_TIMES,
  DEFAULT_CALIBRATION_SAMPLE,
  PREDICTION_WORKING_BASKET_NAME,
  markLegacyResearchMigrated,
  readLegacyResearch
} from "../prediction-markets";
import {
  SITREP_FOLLOW_UP_MIGRATED_STORAGE_KEY,
  SITREP_FOLLOW_UP_STORAGE_KEY,
  buildSitrepFollowUpCreatePayload,
  findSitrepFollowUpByRow,
  parseSitrepFollowUps,
  type SitrepFollowUp,
  type SitrepFollowUpStatus,
  type SitrepTapeHandoffRow,
  type SitrepWorkspaceMeta
} from "../view-models/sitrep";
import type {
  ActionResponse,
  BaseCurrencyResponse,
  CommodityMode,
  CommodityWorkspaceResponse,
  CopilotArtifact,
  CopilotBaseDomain,
  CopilotDeleteResult,
  CopilotDraftMutation,
  CopilotDomain,
  CopilotMemo,
  CopilotDiagnostics,
  CopilotMutationApplyResult,
  CopilotOperatorPlan,
  CopilotProfile,
  CopilotReasoningEffort,
  CopilotResearchCardResult,
  CopilotResearchActionDefinition,
  CopilotResearchPlan,
  CopilotResearchReport,
  CopilotRunEvent,
  CopilotSessionDetail,
  CopilotSessionSummary,
  CopilotShelfPromotion,
  CopilotStorageStatus,
  CopilotThreadEntry,
  CopilotThreadState,
  CopilotWorkingAnalysis,
  CryptoComparison,
  CryptoDexLiquiditySummary,
  CryptoFlowSummary,
  CryptoPriceHistoryResponse,
  CryptoSyntheticPortfolio,
  CryptoToken,
  CryptoWorkspaceResponse,
  DiagnosticsResponse,
  FundamentalsDcfModel,
  FundamentalsDcfSnapshot,
  FundamentalsDcfSnapshotList,
  FundamentalsFinancials,
  FundamentalsOverview,
  FundamentalsPeerBasket,
  FundamentalsPeers,
  FundamentalsReference,
  FundamentalsReverseValuation,
  FundamentalsSearchResponse,
  IvSessionStatus,
  IvSurface,
  IvUnderlyingHistoryResponse,
  MacroContextState,
  MacroDivergenceListResponse,
  MacroEventsResponse,
  MaritimeMode,
  MaritimeWorkspaceResponse,
  MacroSeriesHistory,
  MacroSnapshot,
  NewsEventFeedResponse,
  SitrepWorkspaceResponse,
  CrossTabHandoffEnvelope,
  PredictionCalibrationSummary,
  PredictionEventBook,
  PredictionOrderBookDepth,
  PredictionSavedResearch,
  PredictionHistoryRange,
  PredictionMarket,
  PredictionMarketComparison,
  PredictionMarketListResponse,
  PredictionOutcomeSeriesResponse,
  PredictionProbabilityHistoryResponse,
  PredictionWalletSummary,
  PortfolioHistoryClearResponse,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  ProviderUsageResponse,
  RelatedPredictionMarketListResponse,
  GammaResearchObject,
  ResearchCompareResult,
  ResearchOverviewResponse,
  ResearchResult,
  RiskResult,
  SavedResearchDeleteResponse,
  SavedResearchItem,
  SavedResearchListResponse,
  StrategyLabBookValidation,
  StrategyLabCompositionLegInput,
  StrategyLabCompositionResult,
  StrategyLabHandoffEnvelope,
  StrategyLabHandoffQueueItem,
  StrategyLabResolvedHandoff,
  StrategyLabPortfolioLegInput,
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
  surface?: "research_overview" | "sitrep";
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

export interface StrategyLabComposeOptions {
  name: string;
  legs: StrategyLabCompositionLegInput[];
  lenses: GammaResearchObject[];
  overlays: GammaResearchObject[];
  benchmarkObject?: StrategyLabCompositionLegInput["object"] | null;
  minObservations?: number;
}

export interface StrategyLabPortfolioComposeOptions {
  name: string;
  legs: StrategyLabPortfolioLegInput[];
  lenses?: GammaResearchObject[];
  overlays?: GammaResearchObject[];
  benchmarkSymbol?: string | null;
  benchmarkObject?: StrategyLabCompositionLegInput["object"] | null;
  lookbackDays?: number;
  minObservations?: number;
  validation?: StrategyLabBookValidation | null;
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

export interface SharedEquitySelection {
  symbol: string;
  label: string | null;
  sourceTab: TabId | "research" | null;
  updatedAt: string;
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
  sourceScope?: "portfolio" | "research" | "research_book";
  researchBookReturnPoints?: Array<{ timestamp: string; value: number }>;
  researchBookRiskLegs?: NonNullable<GammaResearchObject["risk_legs"]>;
  riskSourceLabel?: string | null;
  riskSourceObjectId?: string | null;
  riskSourceOrigin?: string | null;
}

export interface StrategyLabResearchBook {
  bookId: string;
  sourceLabel: string;
  object: GammaResearchObject;
  snapshot: PortfolioSnapshot;
  validation: StrategyLabBookValidation;
  composition: StrategyLabCompositionResult;
  benchmarkSymbol: string | null;
  createdAt: string;
  warnings: string[];
}

export interface IvLoadOptions {
  symbol: string;
  marketDataMode?: string;
  waitSeconds?: number;
  depthPreset?: string;
  surfaceModel?: string;
  preserveExisting?: boolean;
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

export interface PredictionHistoryOptions {
  range?: PredictionHistoryRange;
  resolutionMinutes?: number | null;
  outcomeId?: string | null;
  includeOutcomes?: boolean;
}

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

export interface MaritimeLoadOptions {
  mode?: MaritimeMode | string;
  forceRefresh?: boolean;
}

export interface CommodityWorkspaceLoadOptions {
  mode?: CommodityMode | string;
  selectedInstrumentId?: string;
  forceRefresh?: boolean;
}

export interface FundamentalsSearchOptions {
  query?: string;
  limit?: number;
  forceRefresh?: boolean;
}

export interface FundamentalsSearchState {
  query: string;
  loading: boolean;
  refreshing: boolean;
  stale: boolean;
  error: string | null;
  requestedAt: string | null;
  completedAt: string | null;
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
    sourceSessionId: null,
    contextFingerprint: null,
    latestResponseId: null,
    entries: []
  };
}

function createEmptyCopilotThreads(): Record<CopilotDomain, CopilotThreadState> {
  return {
    portfolio: createEmptyCopilotThread("portfolio"),
    sitrep: createEmptyCopilotThread("sitrep"),
    research: createEmptyCopilotThread("research"),
    equity_research: createEmptyCopilotThread("equity_research"),
    strategy_lab: createEmptyCopilotThread("strategy_lab"),
    macro: createEmptyCopilotThread("macro"),
    commodities: createEmptyCopilotThread("commodities"),
    maritime: createEmptyCopilotThread("maritime"),
    prediction_markets: createEmptyCopilotThread("prediction_markets"),
    crypto: createEmptyCopilotThread("crypto"),
    fundamentals: createEmptyCopilotThread("fundamentals"),
    risk: createEmptyCopilotThread("risk"),
    iv: createEmptyCopilotThread("iv"),
    synthesis: createEmptyCopilotThread("synthesis")
  };
}

export const activeTab = writable<TabId>("portfolio");
export const researchOverview = writable<ResearchOverviewResponse | null>(null);
export const sitrepIndicesOverview = writable<ResearchOverviewResponse | null>(null);
export const sitrepFollowUps = writable<SitrepFollowUp[]>([]);
export const sitrepWorkspaceMeta = writable<SitrepWorkspaceMeta | null>(null);
export const researchResult = writable<ResearchResult | null>(null);
export const strategyLabResult = writable<StrategyLabResult | null>(null);
export const strategyLabComposition = writable<StrategyLabCompositionResult | null>(null);
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
export const newsFeed = writable<NewsEventFeedResponse | null>(null);
export const commoditiesWorkspace = writable<CommodityWorkspaceResponse | null>(null);
export const maritimeWorkspace = writable<MaritimeWorkspaceResponse | null>(null);
export const predictionMarketScreener = writable<PredictionMarketListResponse | null>(null);
export const selectedPredictionMarketId = writable<string | null>(null);
export const predictionMarketDetail = writable<PredictionMarket | null>(null);
export const predictionMarketHistory = writable<PredictionProbabilityHistoryResponse | null>(null);
export const predictionMarketWallet = writable<PredictionWalletSummary | null>(null);
export const predictionMarketRelated = writable<RelatedPredictionMarketListResponse | null>(null);
export const predictionMarketCalibration = writable<PredictionCalibrationSummary | null>(null);
export const predictionMarketOutcomeSeries = writable<PredictionOutcomeSeriesResponse | null>(null);
export const predictionMarketComparison = writable<PredictionMarketComparison | null>(null);
export const predictionHistoryRange = writable<PredictionHistoryRange>("max");
export const predictionHistoryResolution = writable<number | null>(null);
export const predictionHistoryOutcomeId = writable<string | null>(null);
export const predictionMarketEventBook = writable<PredictionEventBook | null>(null);
export const predictionMarketDepth = writable<PredictionOrderBookDepth | null>(null);
export const predictionMarketHandoffs = writable<CrossTabHandoffEnvelope[]>([]);
export const predictionSavedResearch = writable<PredictionSavedResearch | null>(null);
export const predictionCompareSelection = writable<string[]>([]);
export const predictionCalibrationLeadTimes = writable<number[]>([...DEFAULT_CALIBRATION_LEAD_TIMES]);
export const predictionCalibrationSample = writable<number>(DEFAULT_CALIBRATION_SAMPLE);
export const cryptoWorkspace = writable<CryptoWorkspaceResponse | null>(null);
export const selectedCryptoTokenId = writable<string | null>(null);
export const cryptoTokenDetail = writable<CryptoToken | null>(null);
export const cryptoPriceHistory = writable<CryptoPriceHistoryResponse | null>(null);
export const cryptoLiquidity = writable<CryptoDexLiquiditySummary | null>(null);
export const cryptoFlowSummary = writable<CryptoFlowSummary | null>(null);
export const cryptoComparison = writable<CryptoComparison | null>(null);
export const cryptoSyntheticPortfolio = writable<CryptoSyntheticPortfolio | null>(null);
export const fundamentalsSearch = writable<FundamentalsSearchResponse | null>(null);
export const fundamentalsLoadWarnings = writable<string[]>([]);
export const fundamentalsSearchState = writable<FundamentalsSearchState>({
  query: "",
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
  requestedAt: null,
  completedAt: null
});
export const selectedFundamentalsTicker = writable<string | null>(null);
export const fundamentalsOverview = writable<FundamentalsOverview | null>(null);
export const fundamentalsFinancials = writable<FundamentalsFinancials | null>(null);
export const fundamentalsDcfModel = writable<FundamentalsDcfModel | null>(null);
export const fundamentalsPeers = writable<FundamentalsPeers | null>(null);
export const fundamentalsReference = writable<FundamentalsReference | null>(null);
export const fundamentalsReverseValuation = writable<FundamentalsReverseValuation | null>(null);
export const fundamentalsDcfSnapshots = writable<FundamentalsDcfSnapshotList | null>(null);
export const copilotCards = writable<Record<CopilotDomain, CopilotResearchCardResult | null>>({
  portfolio: null,
  sitrep: null,
  research: null,
  equity_research: null,
  strategy_lab: null,
  macro: null,
  commodities: null,
  maritime: null,
  prediction_markets: null,
  crypto: null,
  fundamentals: null,
  risk: null,
  iv: null,
  synthesis: null
});
export const copilotThreads = writable<Record<CopilotDomain, CopilotThreadState>>(createEmptyCopilotThreads());
export const copilotSessions = writable<CopilotSessionSummary[]>([]);
export const activeCopilotSession = writable<CopilotSessionDetail | null>(null);
export const copilotMemos = writable<CopilotMemo[]>([]);
export const copilotArtifacts = writable<CopilotArtifact[]>([]);
export const activeCopilotArtifact = writable<CopilotArtifact | null>(null);
export const copilotStorageStatus = writable<CopilotStorageStatus | null>(null);
export const copilotDiagnostics = writable<CopilotDiagnostics | null>(null);
export const copilotArtifactSaveState = writable<"idle" | "saving" | "saved" | "error">("idle");
/** True while an authoritative `New chat` create is in flight. */
export const copilotSessionCreating = writable(false);
/** Sessions with a non-terminal run, whether or not they are the selected one. */
export const copilotRunningSessionIds = writable<string[]>([]);
/** Set when the last `New chat` activation failed, so the UI can be honest. */
export const copilotSessionCreateError = writable<string | null>(null);
/**
 * The most recent composer submission and whether the server accepted it.
 * `accepted` flips as soon as the run is acknowledged, which is the point where
 * a turn is persisted and the composer draft stops being the only copy.
 */
export const copilotLastSubmission = writable<CopilotSubmissionRecord | null>(null);

export type CopilotSubmissionRecord = {
  submissionId: number;
  sessionId: string | null;
  role: "research_agent" | "research_operator";
  prompt: string;
  accepted: boolean;
  rejectedReason: string | null;
};
export const copilotResearchPlan = writable<CopilotResearchPlan | null>(null);
export const copilotOperatorPlan = writable<CopilotOperatorPlan | null>(null);
export const copilotOperatorResult = writable<CopilotResearchCardResult | null>(null);
export const copilotActionDefinitions = writable<CopilotResearchActionDefinition[]>([]);
// Live streamed Copilot run state for the dedicated tab; null when idle.
export const copilotActiveRun = writable<CopilotRunState | null>(null);
export const researchDraft = writable<ResearchDraftState>({
  scopeType: "single_ticker",
  primarySymbol: "AAPL",
  benchmarkSymbol: "SPY",
  lookbackDays: 252,
  syntheticText: [
    "SPY 0.20",
    "QQQ 0.14",
    "IWM 0.08",
    "EFA 0.07",
    "EEM 0.06",
    "XLV 0.08",
    "XLF 0.07",
    "XLE 0.06",
    "GLD 0.08",
    "TLT 0.08",
    "HYG 0.04",
    "DBC 0.04"
  ].join("\n"),
  selectedPreset: "index-core"
});
export const sharedEquitySelection = writable<SharedEquitySelection | null>(null);
export const riskResult = writable<RiskResult | null>(null);
export const riskSnapshotBasis = writable<PortfolioSnapshot | null>(null);
export const riskWorkspaceBasis = writable<"portfolio" | "research" | "research_book" | null>(null);
export const riskWorkspaceMode = writable<string>("overview");

/**
 * What the Options workbench is actually showing right now. Copilot runs from
 * Options were grounding on the front expiry and losing the built strategy
 * entirely (GUA-20260903-2), so the view publishes its live state here and the
 * context payload carries it verbatim.
 */
export interface IvWorkbenchState {
  mode: string;
  symbol: string | null;
  /** Symbol the legs were priced against; guards against cross-symbol carryover. */
  strategy_symbol: string | null;
  /** True once the Options view unmounted: still a valid snapshot, no longer live. */
  detached?: boolean;
  selected_expiry: string | null;
  selected_expiry_days: number | null;
  contracts: number;
  contract_multiplier: number;
  legs: {
    side: string;
    option_type: string;
    expiry: string;
    days_to_expiry: number | null;
    strike: number;
    premium: number;
    quantity: number;
  }[];
  strategy: {
    net_premium_per_share: number | null;
    net_premium_total: number | null;
    premium_direction: string | null;
    max_profit_per_share: number | null;
    max_loss_per_share: number | null;
    max_profit_total: number | null;
    max_loss_total: number | null;
    breakevens: number[];
    net_delta: number | null;
    net_gamma: number | null;
    net_vega: number | null;
    net_theta: number | null;
    shares_represented: number | null;
    live_position_shares: number | null;
    coverage_ratio: number | null;
    sizing_warnings: string[];
  } | null;
  realized_vs_implied: {
    window_days: number;
    realized_vol: number | null;
    reference_iv: number | null;
    reference_iv_expiry: string | null;
    reference_iv_days: number | null;
    spread: number | null;
  }[];
}

function createIvWorkbenchStore() {
  const inner = writable<IvWorkbenchState | null>(null);
  return {
    subscribe: inner.subscribe,
    set(value: IvWorkbenchState | null) {
      inner.set(value ? { ...value, detached: false } : null);
    },
    /**
     * The Options view unmounted. The snapshot is kept — handing off to Copilot
     * switches tabs and destroys the view before the prompt is submitted, so
     * discarding here lost the strategy the run was about (GUA-20260903-2) — but
     * it is flagged so consumers know it is no longer being refreshed.
     */
    markDetached() {
      inner.update((current) => (current ? { ...current, detached: true } : current));
    },
    reset() {
      inner.set(null);
    }
  };
}

export const ivWorkbenchState = createIvWorkbenchStore();

/**
 * The workbench snapshot, but only the parts that belong to the surface actually
 * loaded. A snapshot for another symbol never travels with the context, and legs
 * priced against a different underlying are dropped rather than reinterpreted
 * (GUA-20260903-6).
 */
function resolvedIvWorkbench(): IvWorkbenchState | null {
  const workbench = get(ivWorkbenchState);
  if (!workbench) {
    return null;
  }
  const surfaceSymbol = String(resolvedIvSurface()?.symbol ?? get(ivSession)?.active_symbol ?? "")
    .trim()
    .toUpperCase();
  const workbenchSymbol = String(workbench.symbol ?? "").trim().toUpperCase();
  if (surfaceSymbol && workbenchSymbol && surfaceSymbol !== workbenchSymbol) {
    return null;
  }
  const strategySymbol = String(workbench.strategy_symbol ?? "").trim().toUpperCase();
  if (workbenchSymbol && strategySymbol && strategySymbol !== workbenchSymbol) {
    return { ...workbench, legs: [], strategy: null };
  }
  return workbench;
}
const STRATEGY_LAB_RESEARCH_BOOK_STORAGE_KEY = "gamma.strategyLab.latestResearchBook";

function loadPersistedStrategyLabResearchBook(): StrategyLabResearchBook | null {
  if (typeof localStorage === "undefined") {
    return null;
  }
  try {
    const raw = localStorage.getItem(STRATEGY_LAB_RESEARCH_BOOK_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as StrategyLabResearchBook;
    return parsed?.object?.return_points?.length && parsed?.snapshot ? parsed : null;
  } catch {
    return null;
  }
}

function persistStrategyLabResearchBook(book: StrategyLabResearchBook | null) {
  if (typeof localStorage === "undefined") {
    return;
  }
  try {
    if (book) {
      localStorage.setItem(STRATEGY_LAB_RESEARCH_BOOK_STORAGE_KEY, JSON.stringify(book));
    } else {
      localStorage.removeItem(STRATEGY_LAB_RESEARCH_BOOK_STORAGE_KEY);
    }
  } catch {
    // Persistence is best-effort; the active Svelte store remains authoritative.
  }
}

export const strategyLabResearchBook = writable<StrategyLabResearchBook | null>(loadPersistedStrategyLabResearchBook());
strategyLabResearchBook.subscribe(persistStrategyLabResearchBook);
export const ivSurface = writable<IvSurface | null>(null);
export const ivUnderlyingHistory = writable<IvUnderlyingHistoryResponse | null>(null);
export const ivSession = writable<IvSessionStatus | null>(null);
export const ivError = writable("");

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

export type FontFamily = "Consolas" | "JetBrains Mono" | "Cascadia Mono" | "IBM Plex Mono" | "Courier New";
export const fontFamily = writable<FontFamily>("Consolas");

export function setFontFamily(family: FontFamily) {
  fontFamily.set(family);
  if (typeof document !== "undefined") {
    document.documentElement.style.setProperty("--app-font", `"${family}"`);
  }
}

const STRATEGY_LAB_HANDOFF_STORAGE_KEY = "gamma.strategyLab.handoffQueue.v1";
// Restored handoffs older than this are grouped as an earlier session instead of
// silently reappearing as current research context (usability audit P0 leftover).
const STRATEGY_LAB_HANDOFF_STALE_MS = 24 * 60 * 60 * 1000;

function isStaleStrategyLabHandoff(enqueuedAt: string): boolean {
  const enqueued = Date.parse(enqueuedAt);
  return !Number.isFinite(enqueued) || Date.now() - enqueued > STRATEGY_LAB_HANDOFF_STALE_MS;
}

function loadPersistedStrategyLabHandoffQueue(): StrategyLabHandoffQueueItem[] {
  if (typeof localStorage === "undefined") {
    return [];
  }
  try {
    const raw = localStorage.getItem(STRATEGY_LAB_HANDOFF_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter(isStrategyLabHandoffQueueItem)
      .slice(0, 20)
      .map((item) => {
        const stale = item.stale || isStaleStrategyLabHandoff(item.enqueued_at);
        if (!stale) {
          return { ...item, stale: false };
        }
        // Drop any previously resolved payload so day-old return streams cannot be
        // accepted into the composer without an explicit revive + re-resolve. The
        // carried series goes with it: a revived handoff re-reads its provider.
        return withoutCarriedSeries({ ...item, stale: true, status: "pending" as const, resolved: null });
      });
  } catch {
    return [];
  }
}

// A carried series can be thousands of points. Only an item that still has to be
// resolved needs one, so resolved and stale items persist without it rather than
// filling the storage quota with series nothing will read again.
function withoutCarriedSeries(item: StrategyLabHandoffQueueItem): StrategyLabHandoffQueueItem {
  if (!item.handoff.loaded_series) {
    return item;
  }
  return { ...item, handoff: { ...item.handoff, loaded_series: null } };
}

function persistStrategyLabHandoffQueue(items: StrategyLabHandoffQueueItem[]) {
  if (typeof localStorage === "undefined") {
    return;
  }
  try {
    const persistable = items
      .slice(0, 20)
      .map((item) =>
        !item.stale && (item.status === "pending" || item.status === "resolving" || item.status === "error")
          ? item
          : withoutCarriedSeries(item)
      );
    localStorage.setItem(STRATEGY_LAB_HANDOFF_STORAGE_KEY, JSON.stringify(persistable));
  } catch {
    // Local persistence is best-effort; the in-memory queue remains authoritative.
  }
}

function isStrategyLabHandoffQueueItem(value: unknown): value is StrategyLabHandoffQueueItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Partial<StrategyLabHandoffQueueItem>;
  return typeof item.id === "string" && Boolean(item.handoff) && typeof item.enqueued_at === "string";
}

export const strategyLabHandoffQueue = writable<StrategyLabHandoffQueueItem[]>(loadPersistedStrategyLabHandoffQueue());
strategyLabHandoffQueue.subscribe(persistStrategyLabHandoffQueue);

const requestCoordinator = new RequestCoordinator();
const DEFAULT_MACRO_SNAPSHOT_FX_SERIES = [
  "fx-eurusd", "fx-gbpusd", "fx-eurgbp", "fx-eurchf", "fx-usdjpy", "fx-usdchf", "fx-usdcnh",
  "fx-usdcad", "fx-audusd", "fx-nzdusd"
] as const;
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

function stableJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`)
    .join(",")}}`;
}

function resetCopilotCard(domain: CopilotDomain) {
  const domainsToReset: CopilotDomain[] =
    domain === "research" ? ["research", "equity_research", "strategy_lab"] : [domain];
  copilotCards.update((current) => {
    const next = { ...current };
    for (const resetDomain of domainsToReset) {
      next[resetDomain] = null;
    }
    return next;
  });
  copilotThreads.update((current) => {
    const next = { ...current };
    for (const resetDomain of domainsToReset) {
      next[resetDomain] = createEmptyCopilotThread(resetDomain);
    }
    return next;
  });
}

/**
 * Drop every in-memory Copilot thread and card.
 *
 * Threads are conversation-scoped scratch state. The workspace renders the
 * thread of whichever domain the selected scope resolves to, so switching
 * conversations must clear all of them or the previous conversation's turns
 * keep rendering under the newly selected session.
 */
function resetAllCopilotThreads() {
  copilotCards.set({
    portfolio: null,
    sitrep: null,
    research: null,
    equity_research: null,
    strategy_lab: null,
    macro: null,
    commodities: null,
    maritime: null,
    prediction_markets: null,
    crypto: null,
    fundamentals: null,
    risk: null,
    iv: null,
    synthesis: null
  });
  copilotThreads.set(createEmptyCopilotThreads());
}

export function setResearchDraft(nextDraft: ResearchDraftState) {
  researchDraft.set(nextDraft);
}

export function setSharedEquitySelection(
  symbol: string,
  options: { label?: string | null; sourceTab?: TabId | "research" | null } = {}
) {
  const normalizedSymbol = symbol.trim().toUpperCase();
  if (!normalizedSymbol) {
    return null;
  }
  const nextSelection: SharedEquitySelection = {
    symbol: normalizedSymbol,
    label: options.label?.trim() || null,
    sourceTab: options.sourceTab ?? null,
    updatedAt: new Date().toISOString()
  };
  sharedEquitySelection.set(nextSelection);
  return nextSelection;
}

export function clearSharedEquitySelection() {
  sharedEquitySelection.set(null);
}

export function clearPortfolioSnapshot() {
  portfolioSnapshot.set(null);
}

export function setMacroContext(nextContext: Partial<MacroContextState>) {
  macroContext.update((current) => normalizeMacroContextState({ ...current, ...nextContext }));
  resetCopilotCard("macro");
}

export function setRiskWorkspaceMode(mode: string) {
  riskWorkspaceMode.set(mode);
  resetCopilotCard("risk");
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
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

function summarizeStrategyLabDraftLegForCopilot(leg: StrategyLabPortfolioLegInput | null | undefined) {
  if (!leg) {
    return null;
  }
  const points = Array.isArray(leg.return_points) ? leg.return_points : [];
  return {
    label: leg.label,
    identifier: leg.identifier,
    asset_class: leg.asset_class,
    value_kind: leg.value_kind,
    weight: leg.weight,
    return_point_count: points.length,
    coverage_start: points[0]?.timestamp ?? null,
    coverage_end: points[points.length - 1]?.timestamp ?? null,
    object_id: leg.object?.object_id ?? null,
    object_type: leg.object?.object_type ?? null,
    source_tab: leg.object?.source_tab ?? null,
    provenance: leg.object?.provenance ?? null,
    warnings: leg.object?.warnings ?? []
  };
}

function summarizeStrategyLabResearchObjectForCopilot(object: GammaResearchObject | null | undefined) {
  if (!object) {
    return null;
  }
  return {
    object_id: object.object_id,
    object_type: object.object_type,
    display_name: object.display_name,
    resolver_capabilities: object.resolver_capabilities,
    source_tab: object.source_tab,
    source_mode: object.source_mode,
    symbols: object.symbols,
    available_start: object.available_start,
    available_end: object.available_end,
    provider_summary: object.provider_summary,
    provenance: object.provenance,
    warnings: object.warnings,
    return_point_count: object.return_points.length
  };
}

function summarizeStrategyLabResolvedHandoffForCopilot(resolved: StrategyLabResolvedHandoff | null | undefined) {
  if (!resolved) {
    return null;
  }
  return {
    handoff_id: resolved.handoff_id,
    status: resolved.status,
    resolved_capability: resolved.resolved_capability,
    date_coverage: resolved.date_coverage,
    provider_summary: resolved.provider_summary,
    provenance: resolved.provenance,
    warnings: resolved.warnings,
    unsupported_reason: resolved.unsupported_reason,
    resolved_objects: {
      composer_draft_leg: summarizeStrategyLabDraftLegForCopilot(resolved.composer_draft_leg),
      benchmark_draft: summarizeStrategyLabResearchObjectForCopilot(resolved.benchmark_draft),
      lens: summarizeStrategyLabResearchObjectForCopilot(resolved.lens),
      overlay: summarizeStrategyLabResearchObjectForCopilot(resolved.overlay)
    }
  };
}

function strategyLabHandoffContextState(item: StrategyLabHandoffQueueItem) {
  if (item.stale) {
    return "stale_earlier_session";
  }
  if (item.status === "resolved") {
    const capability = item.resolved?.resolved_capability ?? item.handoff.resolver_capability;
    return `resolved_${capability}`;
  }
  if (item.status === "unsupported") {
    return "unsupported_reference_only";
  }
  if (item.status === "error") {
    return "resolution_error";
  }
  if (item.status === "resolving") {
    return "resolving";
  }
  return "pending_resolution";
}

function buildStrategyLabHandoffContextForCopilot() {
  const queue = get(strategyLabHandoffQueue);
  const statusCounts = queue.reduce<Record<string, number>>((counts, item) => {
    const key = item.stale ? "stale" : item.status;
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
  const currentItems = queue.filter((item) => !item.stale);
  const resolvedItems = currentItems.filter((item) => item.status === "resolved");
  const pendingItems = currentItems.filter((item) => item.status === "pending" || item.status === "resolving");
  const unsupportedItems = currentItems.filter((item) => item.status === "unsupported");
  const errorItems = currentItems.filter((item) => item.status === "error");
  const contextState =
    currentItems.length === 0
      ? "no_current_handoffs"
      : resolvedItems.length === currentItems.length
        ? "resolved_handoffs"
        : pendingItems.length === currentItems.length
          ? "pending_handoffs"
          : "mixed_handoff_states";

  return {
    context_state: contextState,
    current_count: currentItems.length,
    stale_count: queue.length - currentItems.length,
    status_counts: statusCounts,
    has_pending: pendingItems.length > 0,
    has_resolved: resolvedItems.length > 0,
    has_unsupported: unsupportedItems.length > 0,
    has_errors: errorItems.length > 0,
    items: queue.map((item) => ({
      id: item.id,
      status: item.status,
      context_state: strategyLabHandoffContextState(item),
      stale: Boolean(item.stale),
      enqueued_at: item.enqueued_at,
      updated_at: item.updated_at,
      source_tab: item.handoff.source_tab,
      source_mode: item.handoff.source_mode,
      resolver_capability: item.handoff.resolver_capability,
      asset_class: item.handoff.asset_class,
      value_kind: item.handoff.value_kind,
      default_side: item.handoff.default_side,
      default_weight: item.handoff.default_weight,
      provider: item.handoff.provider,
      selected_timeframe: item.handoff.selected_timeframe,
      selected_entity: item.handoff.selected_entity,
      normalized_ids: item.handoff.normalized_ids,
      warnings: item.handoff.warnings,
      error: item.error,
      resolved: summarizeStrategyLabResolvedHandoffForCopilot(item.resolved)
    }))
  };
}

function hasActiveStrategyLabCopilotContext() {
  return (
    Boolean(get(strategyLabResult)) ||
    Boolean(get(strategyLabComposition)) ||
    Boolean(get(researchCompareResult)) ||
    get(strategyLabHandoffQueue).some((item) => !item.stale)
  );
}

// Operator runs execute multi-step tool plans and can legitimately take longer.
const COPILOT_OPERATOR_TIMEOUT_MS = 300_000;

const COPILOT_DOMAIN_LABELS: Record<CopilotBaseDomain, string> = {
  portfolio: "Portfolio",
  sitrep: "SITREP",
  research: "Research",
  equity_research: "Equity Research",
  strategy_lab: "Strategy Lab",
  macro: "Macro",
  commodities: "Commodities",
  maritime: "Sealanes",
  prediction_markets: "Prediction Markets",
  crypto: "Crypto",
  fundamentals: "Fundamentals",
  risk: "Risk",
  iv: "Options"
};

function buildCopilotContextFingerprint(
  domain: CopilotDomain,
  workspaceMode: WorkspaceMode | null | undefined,
  options: { synthesisDomains?: CopilotBaseDomain[]; activeTabId?: TabId | "research" } = {}
): string {
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

  if (domain === "sitrep") {
    const meta = get(sitrepWorkspaceMeta);
    const overview = get(researchOverview);
    const indices = get(sitrepIndicesOverview);
    const macro = get(macroSnapshot);
    const commodities = get(commoditiesWorkspace);
    const news = get(newsFeed);
    const followUps = get(sitrepFollowUps);
    return JSON.stringify({
      domain,
      workspaceMode,
      workspaceRetrievedAt: meta?.retrieved_at ?? null,
      sectionWarnings: meta?.section_warnings.length ?? 0,
      equitiesRetrievedAt: overview?.retrieved_at ?? null,
      indicesRetrievedAt: indices?.retrieved_at ?? null,
      macroRetrievedAt: macro?.retrieved_at ?? null,
      commoditiesRetrievedAt: commodities?.retrieved_at ?? null,
      newsRetrievedAt: news?.retrieved_at ?? null,
      followUps: followUps.map((item) => ({ id: item.id, status: item.status }))
    });
  }

  if (domain === "research") {
    const result = get(researchResult);
    const strategyResult = get(strategyLabResult);
    const composition = get(strategyLabComposition);
    const strategyLabHandoffs = buildStrategyLabHandoffContextForCopilot();
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
      })),
      strategyResult: strategyResult
        ? {
            name: strategyResult.name,
            valueKind: strategyResult.value_kind,
            returnPoints: strategyResult.returns_points
          }
        : null,
      strategyLabComposition: composition
        ? {
            name: composition.name,
            returnPoints: composition.returns_points,
            legContributions: composition.leg_contributions,
            lenses: composition.lenses,
            overlays: composition.overlays
          }
        : null,
      strategyLabHandoffs
    });
  }

  if (domain === "equity_research") {
    const overview = get(researchOverview);
    const result = get(researchResult);
    return JSON.stringify({
      domain,
      workspaceMode,
      overviewUniverse: overview?.universe_id ?? null,
      overviewRetrievedAt: overview?.retrieved_at ?? null,
      overviewWarnings: overview?.warnings.length ?? 0,
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

  if (domain === "strategy_lab") {
    const strategyResult = get(strategyLabResult);
    const composition = get(strategyLabComposition);
    const compareResult = get(researchCompareResult);
    const handoffContext = buildStrategyLabHandoffContextForCopilot();
    return JSON.stringify({
      domain,
      workspaceMode,
      importedStrategy: strategyResult
        ? {
            name: strategyResult.name,
            valueKind: strategyResult.value_kind,
            returnPoints: strategyResult.returns_points.length,
            retrievedAt: strategyResult.retrieved_at
          }
        : null,
      composition: composition
        ? {
            name: composition.name,
            returnPoints: composition.returns_points.length,
            legContributions: composition.leg_contributions,
            lenses: composition.lenses.map((lens) => lens.object_id),
            overlays: composition.overlays.map((overlay) => overlay.object_id)
          }
        : null,
      handoffContext,
      compareResult: compareResult
        ? {
            left: compareResult.left.label,
            right: compareResult.right.label,
            alignedObservationCount: compareResult.aligned_observation_count
          }
        : null
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

  if (domain === "commodities") {
    const workspace = get(commoditiesWorkspace);
    return JSON.stringify({
      domain,
      workspaceMode,
      mode: workspace?.mode ?? null,
      selectedInstrumentId: workspace?.selected_instrument_id ?? null,
      providerId: workspace?.coverage.provider_id ?? null,
      sourceTimestamp: workspace?.coverage.source_timestamp ?? null,
      retrievedAt: workspace?.retrieved_at ?? null,
      summaries: workspace?.market_summaries.length ?? 0,
      spreads: workspace?.spreads.length ?? 0,
      inventories: workspace?.inventories.length ?? 0
    });
  }

  if (domain === "maritime") {
    const workspace = get(maritimeWorkspace);
    return JSON.stringify({
      domain,
      workspaceMode,
      mode: workspace?.mode ?? null,
      providerId: workspace?.coverage.provider_id ?? null,
      coverageStatus: workspace?.coverage.coverage_status ?? "unavailable",
      freshnessLabel: workspace?.coverage.freshness_label ?? "unavailable",
      sourceTimestamp: workspace?.coverage.source_timestamp ?? null,
      retrievedAt: workspace?.retrieved_at ?? null,
      supportsHistorical: workspace?.coverage.supports_historical ?? false,
      positions: workspace?.positions.length ?? 0,
      tracks: workspace?.tracks.length ?? 0,
      chokepoints: workspace?.chokepoint_summaries.map((row) => ({
        id: row.chokepoint_id,
        retrievedAt: row.retrieved_at,
        vesselCount: row.total_vessel_count
      })) ?? [],
      routes: workspace?.flow_summaries.map((row) => ({
        id: row.flow_id,
        retrievedAt: row.retrieved_at,
        vesselCount: row.vessel_count
      })) ?? []
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
    const peers = get(fundamentalsPeers);
    const reverse = get(fundamentalsReverseValuation);
    const reference = get(fundamentalsReference);
    return JSON.stringify({
      domain,
      workspaceMode,
      ticker: get(selectedFundamentalsTicker),
      companyTicker: overview?.company.ticker ?? null,
      companyName: overview?.company.name ?? null,
      overviewRetrievedAt: overview?.company.retrieved_at ?? null,
      dcfRetrievedAt: dcf?.retrieved_at ?? null,
      peersRetrievedAt: peers?.retrieved_at ?? null,
      reverseRetrievedAt: reverse?.retrieved_at ?? null,
      referenceRetrievedAt: reference?.retrieved_at ?? null,
      activeScenarioId: dcf?.active_scenario_id ?? null,
      peerTickers: peers?.peer_basket.display_order ?? overview?.peer_basket?.display_order ?? []
    });
  }

  if (domain === "risk") {
    const snapshot = get(riskSnapshotBasis);
    const result = get(riskResult);
    return JSON.stringify({
      domain,
      workspaceMode: get(riskWorkspaceBasis) ?? workspaceMode ?? null,
      mode: get(riskWorkspaceMode),
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
  const workbench = resolvedIvWorkbench();
  return JSON.stringify({
    domain,
    workspaceMode,
    symbol: surface?.symbol ?? session?.active_symbol ?? null,
    expiries: surface?.expiries ?? [],
    strikeCount: surface?.strikes.length ?? 0,
    marketDataMode: session?.market_data_mode ?? null,
    // The visible workbench state is part of the context identity: a card built
    // against a different submode, expiry, or strategy is a different card.
    mode: workbench?.mode ?? null,
    strategySymbol: workbench?.strategy_symbol ?? null,
    selectedExpiry: workbench?.selected_expiry ?? null,
    contracts: workbench?.contracts ?? null,
    legs: (workbench?.legs ?? []).map(
      (leg) => `${leg.side}:${leg.option_type}:${leg.expiry}:${leg.strike}:${leg.quantity}`
    ),
    netPremiumPerShare: workbench?.strategy?.net_premium_per_share ?? null,
    realizedWindows: (workbench?.realized_vs_implied ?? []).map((row) => row.window_days)
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

function buildCopilotFailureResult(
  domain: CopilotDomain,
  message: string,
  status: "error" | "unavailable" = "error"
): CopilotResearchCardResult {
  return {
    domain,
    current_tab: domain,
    status,
    provider: "gamma_frontend",
    model: null,
    response_id: null,
    message,
    card: null,
    sources: [],
    tool_traces: [],
    operator_events: [],
    warnings: []
  };
}

function appendCopilotThreadResult(
  domain: CopilotDomain,
  result: CopilotResearchCardResult,
  prompt: string,
  contextFingerprint: string | null,
  previousResponseId: string | null,
  baseThread: CopilotThreadState,
  sourceSessionId: string | null = baseThread.sourceSessionId ?? null
) {
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
  copilotCards.update((current) => ({ ...current, [domain]: result }));
  copilotThreads.update((current) => ({
    ...current,
    [domain]: {
      domain,
      sourceSessionId,
      contextFingerprint,
      latestResponseId,
      entries: [...baseThread.entries, nextEntry]
    }
  }));
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
  const loaded = await loadPortfolioSnapshotData();
  if (loaded) resetCopilotCard("portfolio");
  return loaded;
}

export async function loadPortfolioPerformance(options?: {
  snapshot?: PortfolioSnapshot | null;
  benchmarkSymbol?: string;
  lookbackDays?: number;
}) {
  const loaded = await loadPortfolioPerformanceData(options);
  if (loaded) resetCopilotCard("portfolio");
  return loaded;
}

export async function loadResearchOverview(options: ResearchOverviewLoadOptions = {}) {
  const params = new URLSearchParams({
    universe_id: options.universeId ?? "broad_us_market",
    timeframe: options.timeframe ?? "3M",
    benchmark_symbol: options.benchmarkSymbol ?? "SPY",
    surface: options.surface ?? "research_overview"
  });
  if (options.forceRefresh) params.set("force_refresh", "true");
  const path = `/research/overview?${params.toString()}`;
  const key = stableQueryKey("/research/overview", {
    universe_id: options.universeId ?? "broad_us_market",
    timeframe: options.timeframe ?? "3M",
    benchmark_symbol: options.benchmarkSymbol ?? "SPY",
    surface: options.surface ?? "research_overview"
  });
  beginLoading("researchOverview");
  try {
    const overview = await queryCache.query<ResearchOverviewResponse>({
      scope: "research-overview",
      key,
      staleTimeMs: 5 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => getJson<ResearchOverviewResponse>(path, { signal }),
      onData: (data) => researchOverview.set(data)
    });
    lastError.set("");
    return overview;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally {
    endLoading("researchOverview");
  }
}

export async function loadSitrepIndicesOverview(options: ResearchOverviewLoadOptions = {}) {
  const params = new URLSearchParams({
      universe_id: options.universeId ?? "global_indices",
      timeframe: options.timeframe ?? "3M",
      benchmark_symbol: options.benchmarkSymbol ?? "SPY",
      surface: options.surface ?? "sitrep"
    });
  if (options.forceRefresh) params.set("force_refresh", "true");
  const path = `/research/overview?${params.toString()}`;
  const key = stableQueryKey("/research/overview", {
    universe_id: options.universeId ?? "global_indices",
    timeframe: options.timeframe ?? "3M",
    benchmark_symbol: options.benchmarkSymbol ?? "SPY",
    surface: options.surface ?? "sitrep"
  });
  beginLoading("researchOverview");
  try {
    const overview = await queryCache.query<ResearchOverviewResponse>({
      scope: "sitrep-indices-overview",
      key,
      staleTimeMs: 5 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => getJson<ResearchOverviewResponse>(path, { signal }),
      onData: (data) => sitrepIndicesOverview.set(data)
    });
    lastError.set("");
    return overview;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally {
    endLoading("researchOverview");
  }
}

export async function loadSitrepWorkspace(options: { forceRefresh?: boolean } = {}) {
  const params = new URLSearchParams();
  if (options.forceRefresh) params.set("force_refresh", "true");
  const query = params.toString();
  const path = query ? `/sitrep/workspace?${query}` : "/sitrep/workspace";
  beginLoading("researchOverview");
  beginLoading("macro");
  beginLoading("commodities");
  setLoading("prediction", true);
  setLoading("news", true);
  try {
    const workspace = await queryCache.query<SitrepWorkspaceResponse>({
      scope: "sitrep-workspace",
      key: stableQueryKey("/sitrep/workspace", {}),
      staleTimeMs: 5 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => getJson<SitrepWorkspaceResponse>(path, { signal }),
      onData: (data) => {
        if (data.equities_overview) researchOverview.set(data.equities_overview);
        if (data.indices_overview) sitrepIndicesOverview.set(data.indices_overview);
        if (data.macro_snapshot) macroSnapshot.set(data.macro_snapshot);
        if (data.commodities) commoditiesWorkspace.set(data.commodities);
        if (data.prediction_markets) predictionMarketScreener.set(data.prediction_markets);
        if (data.news) newsFeed.set(data.news);
        sitrepWorkspaceMeta.set({
          retrieved_at: data.retrieved_at,
          sections: data.sections,
          section_warnings: data.section_warnings
        });
        if (data.section_warnings.length) {
          console.warn("SITREP workspace sections degraded:", data.section_warnings);
        }
      }
    });
    lastError.set("");
    return workspace;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally {
    endLoading("researchOverview");
    endLoading("macro");
    endLoading("commodities");
    setLoading("prediction", false);
    setLoading("news", false);
  }
}

interface SitrepFollowUpListResponse {
  items: SitrepFollowUp[];
}

/**
 * One-time migration of pre-backend localStorage follow-ups into the backend
 * store. On failure the local copy is kept so a later load can retry.
 */
async function migrateLegacySitrepFollowUps() {
  if (typeof localStorage === "undefined") {
    return;
  }
  const raw = localStorage.getItem(SITREP_FOLLOW_UP_STORAGE_KEY);
  if (!raw) {
    return;
  }
  const legacy = parseSitrepFollowUps(raw);
  for (const item of legacy) {
    try {
      await postJson<SitrepFollowUp>("/sitrep/follow-ups", {
        row_id: item.row_id,
        title: item.title,
        source: item.source,
        tone: item.tone,
        detail: item.detail,
        meta: item.meta,
        note: item.note,
        handoff: item.handoff,
        saved_at: item.saved_at
      });
    } catch {
      return;
    }
  }
  localStorage.setItem(SITREP_FOLLOW_UP_MIGRATED_STORAGE_KEY, raw);
  localStorage.removeItem(SITREP_FOLLOW_UP_STORAGE_KEY);
}

export async function loadSitrepFollowUps() {
  try {
    await migrateLegacySitrepFollowUps();
    const response = await getJson<SitrepFollowUpListResponse>("/sitrep/follow-ups");
    sitrepFollowUps.set(response.items);
    return response.items;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  }
}

export async function toggleSitrepFollowUpItem(row: SitrepTapeHandoffRow) {
  const existing = findSitrepFollowUpByRow(get(sitrepFollowUps), row.id);
  try {
    if (existing) {
      await deleteJson<{ success: boolean }>(`/sitrep/follow-ups/${existing.id}`);
      sitrepFollowUps.update((items) => items.filter((item) => item.id !== existing.id));
      return null;
    }
    const created = await postJson<SitrepFollowUp>(
      "/sitrep/follow-ups",
      buildSitrepFollowUpCreatePayload(row)
    );
    sitrepFollowUps.update((items) => [created, ...items.filter((item) => item.row_id !== created.row_id)]);
    return created;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function updateSitrepFollowUpItem(
  id: string,
  patch: { note?: string; status?: SitrepFollowUpStatus }
) {
  try {
    const updated = await patchJson<SitrepFollowUp>(`/sitrep/follow-ups/${id}`, patch);
    sitrepFollowUps.update((items) => items.map((item) => (item.id === updated.id ? updated : item)));
    return updated;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function dismissSitrepFollowUpItem(id: string) {
  try {
    await deleteJson<{ success: boolean }>(`/sitrep/follow-ups/${id}`);
    sitrepFollowUps.update((items) => items.filter((item) => item.id !== id));
    return true;
  } catch (error) {
    setError(error);
    return false;
  }
}

export async function loadNewsFeed(options: { limit?: number; forceRefresh?: boolean } = {}) {
  setLoading("news", true);
  try {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 25)
    });
    if (options.forceRefresh) {
      params.set("force_refresh", "true");
    }
    const response = await getJson<NewsEventFeedResponse>(`/news/latest?${params.toString()}`);
    newsFeed.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("news", false);
  }
}

export async function runResearch(options: ResearchRunOptions) {
  const payload = {
      scope_type: options.scopeType,
      primary_symbol: options.primarySymbol ?? "",
      synthetic_positions: options.syntheticPositions ?? [],
      benchmark_symbol: options.benchmarkSymbol,
      lookback_days: options.lookbackDays
  };
  const key = stableJson(payload);
  return requestCoordinator.run("research-analysis", key, async (signal) => {
    setLoading("research", true);
    try {
      const nextResearchResult = await postJson<ResearchResult>("/research/analyze", payload, { signal });
      if (signal.aborted) return null;
      researchResult.set(nextResearchResult);
      strategyLabComposition.set(null);
      researchCompareResult.set(null);
      riskResult.set(null);
      riskSnapshotBasis.set(null);
      riskWorkspaceBasis.set(null);
      resetCopilotCard("research");
      resetCopilotCard("risk");
      lastError.set("");
      return nextResearchResult;
    } catch (error) {
      if (!isAbortError(error)) setError(error);
      return null;
    } finally {
      if (requestCoordinator.isCurrent("research-analysis", signal)) setLoading("research", false);
    }
  });
}

export async function analyzeStrategyLab(options: StrategyLabAnalyzeOptions) {
  const payload = {
      name: options.name,
      rows: options.rows,
      date_column: options.dateColumn,
      value_column: options.valueColumn,
      value_kind: options.valueKind,
      benchmark_column: options.benchmarkColumn || null,
      benchmark_value_kind: options.benchmarkValueKind ?? "return",
      min_observations: options.minObservations ?? 5
  };
  return requestCoordinator.run("strategy-lab-work", `analyze:${stableJson(payload)}`, async (signal) => {
    beginLoading("strategyLab");
    try {
      const result = await postJson<StrategyLabResult>("/research/strategy-lab/analyze", payload, { signal });
      if (signal.aborted) return null;
      strategyLabResult.set(result);
      strategyLabComposition.set(null);
      researchCompareResult.set(null);
      resetCopilotCard("research");
      lastError.set("");
      return result;
    } catch (error) {
      if (!isAbortError(error)) setError(error);
      return null;
    } finally {
      endLoading("strategyLab");
    }
  });
}

export async function composeStrategyLab(options: StrategyLabComposeOptions) {
  const payload = {
      name: options.name,
      legs: options.legs,
      lenses: options.lenses,
      overlays: options.overlays,
      benchmark_object: options.benchmarkObject ?? null,
      min_observations: options.minObservations ?? 5
  };
  return requestCoordinator.run("strategy-lab-work", `compose:${stableJson(payload)}`, async (signal) => {
    beginLoading("strategyLab");
    try {
      const result = await postJson<StrategyLabCompositionResult>("/research/strategy-lab/compose", payload, { signal });
      if (signal.aborted) return null;
      strategyLabComposition.set(result);
      researchCompareResult.set(null);
      resetCopilotCard("research");
      lastError.set("");
      return result;
    } catch (error) {
      if (!isAbortError(error)) {
        strategyLabComposition.set(null);
        setError(error);
      }
      return null;
    } finally {
      endLoading("strategyLab");
    }
  });
}

export async function composeStrategyLabPortfolio(options: StrategyLabPortfolioComposeOptions) {
  const payload = {
      name: options.name,
      legs: options.legs,
      lenses: options.lenses ?? [],
      overlays: options.overlays ?? [],
      benchmark_symbol: options.benchmarkSymbol ?? "SPY",
      benchmark_object: options.benchmarkObject ?? null,
      lookback_days: options.lookbackDays ?? 756,
      min_observations: options.minObservations ?? 5
  };
  return requestCoordinator.run("strategy-lab-work", `portfolio-compose:${stableJson(payload)}`, async (signal) => {
    beginLoading("strategyLab");
    try {
      const result = await postJson<StrategyLabCompositionResult>("/research/strategy-lab/portfolio-compose", payload, { signal });
      if (signal.aborted) return null;
    strategyLabComposition.set(result);
    if (options.validation?.valid) {
      const book = buildStrategyLabResearchBook(result, options.validation, options.benchmarkSymbol ?? null);
      strategyLabResearchBook.set(book);
    }
    researchCompareResult.set(null);
    resetCopilotCard("research");
    lastError.set("");
    return result;
    } catch (error) {
      if (!isAbortError(error)) {
        strategyLabComposition.set(null);
        setError(error);
      }
    return null;
    } finally {
      endLoading("strategyLab");
    }
  });
}

function buildStrategyLabResearchBook(
  composition: StrategyLabCompositionResult,
  validation: StrategyLabBookValidation,
  benchmarkSymbol: string | null
): StrategyLabResearchBook {
  const object = buildResearchBookObjectFromStrategyComposition(composition, validation);
  if (!object) {
    throw new Error("Validated Strategy Lab composition did not produce a research-book object.");
  }
  const createdAt = new Date().toISOString();
  const sourceLabel = `Strategy Lab book: ${composition.name}`;
  const snapshot: PortfolioSnapshot = {
    timestamp: createdAt,
    base_currency: "USD",
    account_summary: {
      source: "strategy_lab_research_book",
      source_label: sourceLabel,
      source_object_id: object.object_id
    },
    positions: [
      {
        symbol: "STRATEGY_BOOK",
        sec_type: "BOOK",
        currency: "USD",
        quantity: 1,
        avg_cost: null,
        market_price: 100000,
        market_value: 100000,
        unrealized_pnl: null,
        weight: 1,
        base_market_value: 100000,
        fx_rate: 1,
        instrument_id: object.object_id,
        display_symbol: composition.name || "Strategy Lab Book",
        exchange: null,
        primary_exchange: null,
        provider: "gamma_strategy_lab",
        provider_id: object.object_id
      }
    ],
    total_market_value: 100000,
    total_cash: 0,
    net_liquidation: 100000,
    day_pnl: null,
    day_pnl_pct: null,
    day_pnl_source: "strategy_lab_validated_return_stream",
    warnings: object.warnings
  };
  return {
    bookId: object.object_id,
    sourceLabel,
    object,
    snapshot,
    validation,
    composition,
    benchmarkSymbol,
    createdAt,
    warnings: object.warnings
  };
}

export async function validateStrategyLabPortfolio(options: StrategyLabPortfolioComposeOptions) {
  const payload = {
      name: options.name,
      legs: options.legs,
      lenses: options.lenses ?? [],
      overlays: options.overlays ?? [],
      benchmark_symbol: options.benchmarkSymbol ?? "SPY",
      benchmark_object: options.benchmarkObject ?? null,
      lookback_days: options.lookbackDays ?? 756,
      min_observations: options.minObservations ?? 5
  };
  return requestCoordinator.run("strategy-lab-work", `portfolio-validate:${stableJson(payload)}`, async (signal) => {
    beginLoading("strategyLab");
    try {
      const result = await postJson<StrategyLabBookValidation>("/research/strategy-lab/portfolio-validate", payload, { signal });
      if (signal.aborted) return null;
      lastError.set("");
      return result;
    } catch (error) {
      if (!isAbortError(error)) setError(error);
      return null;
    } finally {
      endLoading("strategyLab");
    }
  });
}

export function enqueueStrategyLabHandoff(handoff: StrategyLabHandoffEnvelope) {
  const now = new Date().toISOString();
  const entityId = handoff.selected_entity.normalized_id || handoff.selected_entity.native_id || handoff.selected_entity.label;
  const id = `${handoff.source_tab}:${entityId}:${handoff.timestamp || now}`;
  const item: StrategyLabHandoffQueueItem = {
    id,
    handoff: {
      ...handoff,
      timestamp: handoff.timestamp || now,
      warnings: Array.isArray(handoff.warnings) ? handoff.warnings : [],
      normalized_ids: handoff.normalized_ids ?? {}
    },
    status: "pending",
    resolved: null,
    error: null,
    enqueued_at: now,
    updated_at: now
  };
  strategyLabHandoffQueue.update((current) => {
    const withoutDuplicate = current.filter((candidate) => candidate.id !== item.id);
    return [item, ...withoutDuplicate].slice(0, 20);
  });
  lastError.set("");
  return item;
}

export function enqueueAndOpenStrategyLab(handoff: StrategyLabHandoffEnvelope) {
  return enqueueStrategyLabHandoff(handoff);
}

export function resolvePendingStrategyLabHandoffs() {
  return requestCoordinator.run("strategy-lab-handoff-resolution", "pending", resolvePendingStrategyLabHandoffsImpl);
}

async function resolvePendingStrategyLabHandoffsImpl(signal: AbortSignal) {
  // Stale earlier-session items stay out of auto-resolution; the user can dismiss
  // them or re-send the handoff from the source tab for fresh data.
  const pending = get(strategyLabHandoffQueue).filter(
    (item) => !item.stale && (item.status === "pending" || item.status === "error")
  );
  if (!pending.length) {
    return get(strategyLabHandoffQueue);
  }
  setLoading("strategyLabHandoff", true);
  try {
    for (const item of pending) {
      if (signal.aborted) break;
      strategyLabHandoffQueue.update((current) =>
        current.map((candidate) =>
          candidate.id === item.id
            ? { ...candidate, status: "resolving", error: null, updated_at: new Date().toISOString() }
            : candidate
        )
      );
      try {
        const resolved = await postJson<StrategyLabResolvedHandoff>("/research/strategy-lab/resolve-handoff", {
          handoff: item.handoff
        }, { signal });
        if (signal.aborted) break;
        strategyLabHandoffQueue.update((current) =>
          current.map((candidate) =>
            candidate.id === item.id
              ? {
                  ...candidate,
                  status: resolved.status === "resolved" ? "resolved" : "unsupported",
                  resolved,
                  error: resolved.unsupported_reason,
                  updated_at: new Date().toISOString()
                }
              : candidate
          )
        );
      } catch (error) {
        if (isAbortError(error)) break;
        const message = errorMessage(error);
        strategyLabHandoffQueue.update((current) =>
          current.map((candidate) =>
            candidate.id === item.id
              ? { ...candidate, status: "error", error: message, updated_at: new Date().toISOString() }
              : candidate
          )
        );
        lastError.set(message);
      }
    }
    return get(strategyLabHandoffQueue);
  } finally {
    if (requestCoordinator.isCurrent("strategy-lab-handoff-resolution", signal)) {
      setLoading("strategyLabHandoff", false);
    }
  }
}

export function dismissStrategyLabHandoff(id: string) {
  strategyLabHandoffQueue.update((current) => current.filter((item) => item.id !== id));
}

export function clearStrategyLabHandoffs() {
  strategyLabHandoffQueue.set([]);
}

export function clearStaleStrategyLabHandoffs() {
  strategyLabHandoffQueue.update((current) => current.filter((item) => !item.stale));
}

export function reviveStrategyLabHandoff(id: string) {
  const now = new Date().toISOString();
  strategyLabHandoffQueue.update((current) =>
    current.map((item) =>
      item.id === id
        ? { ...item, stale: false, status: "pending", resolved: null, error: null, updated_at: now }
        : item
    )
  );
}

export function acceptResolvedStrategyLabHandoff(id: string) {
  const item = get(strategyLabHandoffQueue).find((candidate) => candidate.id === id) ?? null;
  if (item?.resolved?.status !== "resolved") {
    return null;
  }
  dismissStrategyLabHandoff(id);
  return item.resolved;
}

export function restoreStrategyLabResult(result: StrategyLabResult) {
  strategyLabResult.set(result);
  strategyLabComposition.set(null);
  researchCompareResult.set(null);
  resetCopilotCard("research");
  lastError.set("");
}

export async function compareResearch(options: ResearchCompareOptions) {
  const payload = {
      left: serializeCompareLeg(options.left),
      right: serializeCompareLeg(options.right)
  };
  return requestCoordinator.run("research-compare", stableJson(payload), async (signal) => {
    setLoading("compareScenario", true);
    try {
      const result = await postJson<ResearchCompareResult>("/research/compare-scenario/analyze", payload, { signal });
      if (signal.aborted) return null;
      researchCompareResult.set(result);
      lastError.set("");
      return result;
    } catch (error) {
      if (!isAbortError(error)) setError(error);
      return null;
    } finally {
      if (requestCoordinator.isCurrent("research-compare", signal)) setLoading("compareScenario", false);
    }
  });
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
  beginLoading("savedResearch");
  try {
    const response = await queryCache.query<SavedResearchListResponse>({
      scope: "saved-research",
      key: "/research/saved",
      staleTimeMs: 60_000,
      fetcher: (signal) => getJson<SavedResearchListResponse>("/research/saved", { signal }),
      onData: (data) => savedResearchItems.set(Array.isArray(data.items) ? data.items : [])
    });
    lastError.set("");
    return Array.isArray(response.items) ? response.items : [];
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return get(savedResearchItems);
  } finally {
    endLoading("savedResearch");
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
    queryCache.invalidate("/research/saved");
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
      queryCache.invalidate("/research/saved");
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
  if (context.mode === "trade_partners" || context.mode === "country_compare") {
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
  const requestKey = stableQueryKey("/macro/workspace", payload);
  const requestPromise = (async () => {
    beginLoading("macro");
    try {
      const bundle = await queryCache.query<{
        snapshot: MacroSnapshot;
        divergences: MacroDivergenceListResponse;
        events: MacroEventsResponse;
      }>({
        scope: "macro-workspace",
        key: requestKey,
        staleTimeMs: 10 * 60_000,
        forceRefresh: options.forceRefresh,
        fetcher: async (signal) => {
          const [snapshot, divergences, events] = await Promise.all([
            postJson<MacroSnapshot>("/macro/snapshot", payload, { signal }),
            postJson<MacroDivergenceListResponse>("/macro/divergences", payload, { signal }),
            getJson<MacroEventsResponse>(
              `/macro/events?region=${encodeURIComponent(payload.region)}&force_refresh=${payload.force_refresh ? "true" : "false"}`,
              { signal }
            )
          ]);
          return { snapshot, divergences, events };
        },
        onData: ({ snapshot, divergences, events }) => {
          macroSnapshot.set(snapshot);
          macroDivergences.set(divergences);
          macroEvents.set(events);
        }
      });
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
        return bundle.snapshot;
      } catch (error) {
      setError(error);
      return null;
    } finally {
      endLoading("macro");
    }
  })();
  return requestPromise;
}

export async function loadMaritimeWorkspace(options: MaritimeLoadOptions = {}) {
  const params = new URLSearchParams({
    mode: options.mode ?? get(maritimeWorkspace)?.mode ?? "live_map",
    force_refresh: options.forceRefresh ? "true" : "false"
  });
  setLoading("maritime", true);
  try {
    const response = await getJson<MaritimeWorkspaceResponse>(`/maritime/workspace?${params.toString()}`);
    maritimeWorkspace.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("maritime", false);
  }
}

export async function loadCommoditiesWorkspace(options: CommodityWorkspaceLoadOptions = {}) {
  beginLoading("commodities");
  try {
    const current = get(commoditiesWorkspace);
    const mode = options.mode ?? current?.mode ?? "overview";
    const payload = {
      mode,
      selected_instrument_id:
        options.selectedInstrumentId ?? resolveCommodityInstrumentForMode(current, mode) ?? "wti",
      force_refresh: options.forceRefresh ?? false
    };
    const response = await queryCache.query<CommodityWorkspaceResponse>({
      scope: "commodities-workspace",
      key: stableQueryKey("/commodities/workspace", {
        mode: payload.mode,
        selected_instrument_id: payload.selected_instrument_id
      }),
      staleTimeMs: 5 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => postJson<CommodityWorkspaceResponse>("/commodities/workspace", payload, { signal }),
      onData: (data) => commoditiesWorkspace.set(data)
    });
    resetCopilotCard("commodities");
    lastError.set("");
    return response;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return null;
  } finally {
    endLoading("commodities");
  }
}

function resolveCommodityInstrumentForMode(
  current: CommodityWorkspaceResponse | null,
  mode: CommodityWorkspaceLoadOptions["mode"]
) {
  const selectedInstrumentId = current?.selected_instrument_id ?? null;
  if (!current || !selectedInstrumentId) {
    return selectedInstrumentId;
  }
  const validInstrumentIds = commodityInstrumentIdsForMode(current, mode);
  if (!validInstrumentIds.length || validInstrumentIds.includes(selectedInstrumentId)) {
    return selectedInstrumentId;
  }
  return validInstrumentIds[0] ?? selectedInstrumentId;
}

function commodityInstrumentIdsForMode(
  current: CommodityWorkspaceResponse,
  mode: CommodityWorkspaceLoadOptions["mode"]
) {
  if (mode === "energy" || mode === "metals") {
    return current.market_summaries
      .filter((summary) => summary.instrument.family === mode)
      .map((summary) => summary.instrument.instrument_id);
  }
  if (mode === "overview" || mode === "curves_spreads") {
    return current.curves.map((curve) => curve.instrument_id);
  }
  if (mode === "inventories_fundamentals") {
    return current.inventories
      .map((series) => series.metadata.instrument_id)
      .filter((instrumentId): instrumentId is string => Boolean(instrumentId));
  }
  if (mode === "events_cross_domain") {
    return Array.from(new Set([
      ...current.events.flatMap((event) => event.linked_instrument_ids),
      ...current.cross_domain_links.flatMap((link) => link.linked_instrument_ids)
    ]));
  }
  return [];
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
  const path = `/macro/series/${encodeURIComponent(seriesId)}/history?region=${encodeURIComponent(payload.region)}&timeframe=${encodeURIComponent(payload.timeframe)}&force_refresh=${payload.force_refresh ? "true" : "false"}`;
  beginLoading("macroHistory");
  try {
    const history = await queryCache.query<MacroSeriesHistory>({
      scope: `macro-series:${cacheKey}`,
      key: stableQueryKey(`/macro/series/${seriesId}/history`, { region: payload.region, timeframe: payload.timeframe }),
      staleTimeMs: 30 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => getJson<MacroSeriesHistory>(path, { signal }),
      onData: (data) => macroSeriesHistories.update((current) => ({ ...current, [cacheKey]: data }))
    });
    lastError.set("");
    return history;
  } catch (error) {
    if (!isAbortError(error)) setError(error);
    return get(macroSeriesHistories)[cacheKey] ?? null;
  } finally {
    endLoading("macroHistory");
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
      predictionMarketOutcomeSeries.set(null);
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

function predictionHistoryQuery(options: PredictionHistoryOptions = {}) {
  const params = new URLSearchParams();
  params.set("range", options.range ?? get(predictionHistoryRange));
  const resolution = options.resolutionMinutes === undefined ? get(predictionHistoryResolution) : options.resolutionMinutes;
  if (resolution != null) {
    params.set("resolution", String(resolution));
  }
  return params;
}

export async function loadPredictionMarketHistory(
  marketId: string,
  options: PredictionHistoryOptions = {}
) {
  const range = options.range ?? get(predictionHistoryRange);
  const resolution =
    options.resolutionMinutes === undefined ? get(predictionHistoryResolution) : options.resolutionMinutes;
  const outcomeId = options.outcomeId === undefined ? get(predictionHistoryOutcomeId) : options.outcomeId;

  predictionHistoryRange.set(range);
  predictionHistoryResolution.set(resolution ?? null);
  predictionHistoryOutcomeId.set(outcomeId ?? null);

  const params = predictionHistoryQuery({ range, resolutionMinutes: resolution });
  if (outcomeId) {
    params.set("outcome_id", outcomeId);
  }

  setLoading("predictionHistory", true);
  try {
    const requests: Promise<unknown>[] = [
      getJson<PredictionProbabilityHistoryResponse>(
        `/prediction-markets/markets/${marketId}/history?${params.toString()}`
      )
    ];
    if (options.includeOutcomes) {
      requests.push(
        getJson<PredictionOutcomeSeriesResponse>(
          `/prediction-markets/markets/${marketId}/outcome-history?${predictionHistoryQuery({
            range,
            resolutionMinutes: resolution
          }).toString()}`
        )
      );
    }
    const [historyResult, outcomeResult] = await Promise.allSettled(requests);

    if (historyResult.status === "fulfilled") {
      predictionMarketHistory.set(historyResult.value as PredictionProbabilityHistoryResponse);
      lastError.set("");
    } else {
      setError(historyResult.reason);
    }
    if (options.includeOutcomes) {
      if (outcomeResult?.status === "fulfilled") {
        predictionMarketOutcomeSeries.set(outcomeResult.value as PredictionOutcomeSeriesResponse);
      } else if (outcomeResult?.status === "rejected") {
        predictionMarketOutcomeSeries.set(null);
      }
    }
    return get(predictionMarketHistory);
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionHistory", false);
  }
}

export async function runPredictionMarketComparison(
  marketIds: string[],
  options: { range?: PredictionHistoryRange; resolutionMinutes?: number | null } = {}
) {
  if (marketIds.length < 1) {
    predictionMarketComparison.set(null);
    return null;
  }
  setLoading("predictionCompare", true);
  try {
    const response = await postJson<PredictionMarketComparison>("/prediction-markets/compare", {
      market_ids: marketIds,
      range_key: options.range ?? get(predictionHistoryRange),
      resolution_minutes:
        options.resolutionMinutes === undefined ? get(predictionHistoryResolution) : options.resolutionMinutes
    });
    predictionMarketComparison.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionCompare", false);
  }
}

function applySavedResearch(saved: PredictionSavedResearch | null) {
  predictionSavedResearch.set(saved);
  if (!saved) {
    return saved;
  }
  const working = saved.comparison_sets.find((row) => row.name === PREDICTION_WORKING_BASKET_NAME);
  if (working) {
    predictionCompareSelection.set([...working.market_ids]);
  }
  return saved;
}

/**
 * Load server-side saved research, migrating this browser's local records once.
 * The migration flag is set only after the server confirms the import, so a
 * failed request leaves the local records available for a later attempt.
 */
export async function loadPredictionSavedResearch() {
  setLoading("predictionSaved", true);
  try {
    const legacy = readLegacyResearch();
    if (legacy) {
      const migrated = await postJson<PredictionSavedResearch>("/prediction-markets/saved/import", {
        watchlist: legacy.watchlist.map((entry) => ({
          market_id: entry.market_id,
          venue: entry.venue,
          title: entry.title,
          probability: entry.probability
        })),
        comparison_basket: legacy.comparison_basket,
        basket_name: PREDICTION_WORKING_BASKET_NAME
      });
      markLegacyResearchMigrated();
      lastError.set("");
      return applySavedResearch(migrated);
    }
    const response = await getJson<PredictionSavedResearch>("/prediction-markets/saved");
    lastError.set("");
    return applySavedResearch(response);
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionSaved", false);
  }
}

export async function togglePredictionWatchlistEntry(market: {
  market_id: string;
  venue?: string | null;
  title?: string | null;
  current_probability?: number | null;
}) {
  const saved = get(predictionSavedResearch);
  const isWatched = Boolean(saved?.watchlist.some((entry) => entry.market_id === market.market_id));
  setLoading("predictionSaved", true);
  try {
    const response = isWatched
      ? await deleteJson<PredictionSavedResearch>(
          `/prediction-markets/saved/watchlist/${market.market_id}`
        )
      : await postJson<PredictionSavedResearch>("/prediction-markets/saved/watchlist", {
          market_id: market.market_id,
          venue: market.venue ?? "",
          title: market.title ?? "",
          probability: market.current_probability ?? null
        });
    lastError.set("");
    return applySavedResearch(response);
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionSaved", false);
  }
}

export async function savePredictionComparisonSet(options: {
  name: string;
  marketIds: string[];
  setId?: string | null;
  rangeKey?: string;
  resolutionMinutes?: number | null;
  note?: string;
}) {
  setLoading("predictionSaved", true);
  try {
    const response = await postJson<PredictionSavedResearch>("/prediction-markets/saved/comparison-sets", {
      name: options.name,
      market_ids: options.marketIds,
      set_id: options.setId ?? null,
      range_key: options.rangeKey ?? get(predictionHistoryRange),
      resolution_minutes: options.resolutionMinutes ?? get(predictionHistoryResolution),
      note: options.note ?? ""
    });
    lastError.set("");
    return applySavedResearch(response);
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionSaved", false);
  }
}

export async function deletePredictionComparisonSet(setId: string) {
  setLoading("predictionSaved", true);
  try {
    const response = await deleteJson<PredictionSavedResearch>(
      `/prediction-markets/saved/comparison-sets/${setId}`
    );
    lastError.set("");
    return applySavedResearch(response);
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionSaved", false);
  }
}

let workingBasketHandle: ReturnType<typeof setTimeout> | null = null;

/**
 * Update the working comparison basket and persist it to the server.
 * Persistence is debounced because ticking four contracts should cost one
 * write, not four.
 */
export function setPredictionCompareSelection(marketIds: string[]) {
  predictionCompareSelection.set([...marketIds]);
  if (workingBasketHandle) {
    clearTimeout(workingBasketHandle);
  }
  workingBasketHandle = setTimeout(() => {
    workingBasketHandle = null;
    void persistPredictionWorkingBasket();
  }, 600);
}

export async function persistPredictionWorkingBasket() {
  const marketIds = get(predictionCompareSelection);
  const saved = get(predictionSavedResearch);
  const existing = saved?.comparison_sets.find((row) => row.name === PREDICTION_WORKING_BASKET_NAME);
  if (!marketIds.length) {
    if (!existing) {
      return null;
    }
    return deletePredictionComparisonSet(existing.id);
  }
  return savePredictionComparisonSet({
    name: PREDICTION_WORKING_BASKET_NAME,
    marketIds,
    setId: existing?.id ?? null
  });
}

/**
 * Resolve every sibling contract the venue groups under the selected event.
 * Loaded on demand: an event with dozens of candidates is a bigger surface than
 * the contract bundle needs by default.
 */
export async function loadPredictionMarketEventBook(marketId: string) {
  setLoading("predictionEventBook", true);
  try {
    const response = await getJson<PredictionEventBook>(
      `/prediction-markets/markets/${marketId}/event-book`
    );
    predictionMarketEventBook.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionEventBook", false);
  }
}

/**
 * Lead-time calibration costs one provider history request per sampled
 * contract, so it is loaded when the Calibration mode asks for it rather than
 * bundled into every contract selection.
 */
export async function loadPredictionMarketCalibration(
  marketId: string,
  options: { leadTimes?: number[]; sampleSize?: number } = {}
) {
  const leadTimes = options.leadTimes ?? get(predictionCalibrationLeadTimes);
  const sampleSize = options.sampleSize ?? get(predictionCalibrationSample);
  predictionCalibrationLeadTimes.set(leadTimes);
  predictionCalibrationSample.set(sampleSize);

  const params = new URLSearchParams();
  params.set("sample", String(sampleSize));
  for (const lead of leadTimes) {
    params.append("lead", String(lead));
  }

  setLoading("predictionCalibration", true);
  try {
    const response = await getJson<PredictionCalibrationSummary>(
      `/prediction-markets/markets/${marketId}/calibration?${params.toString()}`
    );
    predictionMarketCalibration.set(response);
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("predictionCalibration", false);
  }
}

export async function selectPredictionMarket(
  marketId: string,
  options: { resetThread?: boolean } & PredictionHistoryOptions = {}
) {
  selectedPredictionMarketId.set(marketId);
  if (options.resetThread ?? true) {
    resetCopilotCard("prediction_markets");
  }
  // A new contract must not inherit the previous contract's outcome selection
  // or its event book.
  predictionHistoryOutcomeId.set(options.outcomeId ?? null);
  predictionMarketOutcomeSeries.set(null);
  predictionMarketEventBook.set(null);
  predictionMarketDepth.set(null);
  predictionMarketHandoffs.set([]);
  setLoading("predictionDetail", true);
  try {
    const historyParams = predictionHistoryQuery(options);
    const [detailResult, historyResult, walletResult, relatedResult, outcomeResult, depthResult, handoffResult] =
      await Promise.allSettled([
      getJson<PredictionMarket>(`/prediction-markets/markets/${marketId}`),
      getJson<PredictionProbabilityHistoryResponse>(
        `/prediction-markets/markets/${marketId}/history?${historyParams.toString()}`
      ),
      getJson<PredictionWalletSummary>(`/prediction-markets/markets/${marketId}/wallet-summary`),
      getJson<RelatedPredictionMarketListResponse>(`/prediction-markets/markets/${marketId}/related`),
      getJson<PredictionOutcomeSeriesResponse>(
        `/prediction-markets/markets/${marketId}/outcome-history?${historyParams.toString()}`
      ),
      getJson<PredictionOrderBookDepth>(`/prediction-markets/markets/${marketId}/depth`),
      getJson<{ market_id: string; handoffs: CrossTabHandoffEnvelope[] }>(
        `/prediction-markets/markets/${marketId}/handoffs`
      )
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
    if (outcomeResult.status === "fulfilled") {
      predictionMarketOutcomeSeries.set(outcomeResult.value);
    } else {
      // Per-outcome history is additive context; a venue without outcome tokens
      // must not turn the whole contract load into an error.
      predictionMarketOutcomeSeries.set(null);
    }
    if (depthResult.status === "fulfilled") {
      predictionMarketDepth.set(depthResult.value);
    } else {
      // Same rule for depth: a venue without a public book must not fail the load.
      predictionMarketDepth.set(null);
    }
    if (handoffResult.status === "fulfilled") {
      predictionMarketHandoffs.set(handoffResult.value.handoffs ?? []);
    } else {
      predictionMarketHandoffs.set([]);
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
  const query = String(options.query ?? "").trim();
  const previousResults = get(fundamentalsSearch)?.results ?? [];
  fundamentalsSearchState.set({
    query,
    loading: true,
    refreshing: previousResults.length > 0,
    stale: previousResults.length > 0,
    error: null,
    requestedAt: new Date().toISOString(),
    completedAt: null
  });
  try {
    const params = new URLSearchParams({
      query,
      limit: String(options.limit ?? 12),
      force_refresh: options.forceRefresh ? "true" : "false"
    });
    const response = await getJson<FundamentalsSearchResponse>(`/fundamentals/search?${params.toString()}`);
    fundamentalsSearch.set(response);
    fundamentalsSearchState.set({
      query,
      loading: false,
      refreshing: false,
      stale: false,
      error: null,
      requestedAt: null,
      completedAt: new Date().toISOString()
    });
    const currentSelection = get(selectedFundamentalsTicker);
    const exactTickerMatch = query
      ? response.results.find((result) => result.ticker.trim().toUpperCase() === query.toUpperCase()) ?? null
      : null;
    if (exactTickerMatch && (currentSelection !== exactTickerMatch.ticker || get(fundamentalsOverview) == null)) {
      await selectFundamentalsCompany(exactTickerMatch.ticker, {
        resetThread: currentSelection !== exactTickerMatch.ticker || get(fundamentalsOverview) == null,
        forceRefresh: options.forceRefresh
      });
    } else if (!currentSelection && !query && response.results.length === 0) {
      selectedFundamentalsTicker.set(null);
      fundamentalsOverview.set(null);
      fundamentalsFinancials.set(null);
      fundamentalsDcfModel.set(null);
      fundamentalsPeers.set(null);
      fundamentalsReference.set(null);
      fundamentalsReverseValuation.set(null);
      fundamentalsDcfSnapshots.set(null);
      resetCopilotCard("fundamentals");
    }
    lastError.set("");
    return response;
  } catch (error) {
    fundamentalsSearchState.update((current) => ({
      ...current,
      loading: false,
      refreshing: false,
      stale: false,
      error: errorMessage(error),
      completedAt: new Date().toISOString()
    }));
    setError(error);
    return null;
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
  fundamentalsLoadWarnings.set([]);
  try {
    const querySuffix = options.forceRefresh ? "?force_refresh=true" : "";
    const [overviewResult, financialsResult, dcfResult, peersResult, reverseResult, referenceResult, snapshotsResult] = await Promise.allSettled([
      getJson<FundamentalsOverview>(`/fundamentals/${normalizedTicker}/overview${querySuffix}`),
      getJson<FundamentalsFinancials>(`/fundamentals/${normalizedTicker}/financials${querySuffix}`),
      getJson<FundamentalsDcfModel>(`/fundamentals/${normalizedTicker}/dcf${querySuffix}`),
      getJson<FundamentalsPeers>(`/fundamentals/${normalizedTicker}/peers${querySuffix}`),
      getJson<FundamentalsReverseValuation>(`/fundamentals/${normalizedTicker}/reverse-valuation${querySuffix}`),
      getJson<FundamentalsReference>(`/fundamentals/${normalizedTicker}/reference${querySuffix}`),
      getJson<FundamentalsDcfSnapshotList>(`/fundamentals/${normalizedTicker}/dcf/snapshots${querySuffix}`)
    ]);

    const errors: unknown[] = [];
    const sectionWarnings: string[] = [];

    if (overviewResult.status === "fulfilled") {
      fundamentalsOverview.set(overviewResult.value);
    } else {
      fundamentalsOverview.set(null);
      errors.push(overviewResult.reason);
      sectionWarnings.push(`Overview unavailable: ${errorMessage(overviewResult.reason)}`);
    }

    if (financialsResult.status === "fulfilled") {
      fundamentalsFinancials.set(financialsResult.value);
    } else {
      fundamentalsFinancials.set(null);
      errors.push(financialsResult.reason);
      sectionWarnings.push(`Financials unavailable: ${errorMessage(financialsResult.reason)}`);
    }

    if (dcfResult.status === "fulfilled") {
      fundamentalsDcfModel.set(dcfResult.value);
    } else {
      fundamentalsDcfModel.set(null);
      errors.push(dcfResult.reason);
      sectionWarnings.push(`DCF unavailable: ${errorMessage(dcfResult.reason)}`);
    }

    if (peersResult.status === "fulfilled") {
      fundamentalsPeers.set(peersResult.value);
    } else {
      fundamentalsPeers.set(null);
      errors.push(peersResult.reason);
      sectionWarnings.push(`Peers unavailable: ${errorMessage(peersResult.reason)}`);
    }

    if (reverseResult.status === "fulfilled") {
      fundamentalsReverseValuation.set(reverseResult.value);
    } else {
      fundamentalsReverseValuation.set(null);
      errors.push(reverseResult.reason);
      sectionWarnings.push(`Reverse valuation unavailable: ${errorMessage(reverseResult.reason)}`);
    }

    if (referenceResult.status === "fulfilled") {
      fundamentalsReference.set(referenceResult.value);
    } else {
      fundamentalsReference.set(null);
      errors.push(referenceResult.reason);
      sectionWarnings.push(`Reference / filings unavailable: ${errorMessage(referenceResult.reason)}`);
    }

    if (snapshotsResult.status === "fulfilled") {
      fundamentalsDcfSnapshots.set(snapshotsResult.value);
    } else {
      fundamentalsDcfSnapshots.set(null);
      errors.push(snapshotsResult.reason);
      sectionWarnings.push(`DCF snapshots unavailable: ${errorMessage(snapshotsResult.reason)}`);
    }

    fundamentalsLoadWarnings.set(sectionWarnings);

    if (errors.length === 0) {
      lastError.set("");
    } else {
      setError(errors[0]);
    }
    return {
      overview: overviewResult.status === "fulfilled" ? overviewResult.value : null,
      financials: financialsResult.status === "fulfilled" ? financialsResult.value : null,
      dcf: dcfResult.status === "fulfilled" ? dcfResult.value : null,
      peers: peersResult.status === "fulfilled" ? peersResult.value : null,
      reverseValuation: reverseResult.status === "fulfilled" ? reverseResult.value : null,
      reference: referenceResult.status === "fulfilled" ? referenceResult.value : null,
      snapshots: snapshotsResult.status === "fulfilled" ? snapshotsResult.value : null
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
    resetCopilotCard("fundamentals");
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
    const querySuffix = "?force_refresh=false";
    const [reverseResult, snapshotsResult] = await Promise.allSettled([
      getJson<FundamentalsReverseValuation>(`/fundamentals/${normalizedTicker}/reverse-valuation${querySuffix}`),
      getJson<FundamentalsDcfSnapshotList>(`/fundamentals/${normalizedTicker}/dcf/snapshots${querySuffix}`)
    ]);
    if (reverseResult.status === "fulfilled") {
      fundamentalsReverseValuation.set(reverseResult.value);
    }
    if (snapshotsResult.status === "fulfilled") {
      fundamentalsDcfSnapshots.set(snapshotsResult.value);
    }
    resetCopilotCard("fundamentals");
    lastError.set("");
    return response;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentalsSave", false);
  }
}

export async function saveFundamentalsDcfSnapshot(ticker: string, name?: string) {
  const normalizedTicker = ticker.trim().toUpperCase();
  setLoading("fundamentalsSave", true);
  try {
    const snapshot = await postJson<FundamentalsDcfSnapshot>(`/fundamentals/${normalizedTicker}/dcf/snapshots`, {
      name: name?.trim() || null
    });
    const snapshots = await getJson<FundamentalsDcfSnapshotList>(`/fundamentals/${normalizedTicker}/dcf/snapshots`);
    fundamentalsDcfSnapshots.set(snapshots);
    resetCopilotCard("fundamentals");
    lastError.set("");
    return snapshot;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("fundamentalsSave", false);
  }
}

export async function loadFundamentalsDcfSnapshot(ticker: string, snapshotId: string) {
  const normalizedTicker = ticker.trim().toUpperCase();
  const normalizedSnapshotId = snapshotId.trim();
  if (!normalizedTicker || !normalizedSnapshotId) {
    return null;
  }
  setLoading("fundamentalsSave", true);
  try {
    const model = await getJson<FundamentalsDcfModel>(
      `/fundamentals/${normalizedTicker}/dcf/snapshots/${encodeURIComponent(normalizedSnapshotId)}`
    );
    fundamentalsDcfModel.set(model);
    resetCopilotCard("fundamentals");
    lastError.set("");
    return model;
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
    return null;
  }
  const snapshotWorkspace: "portfolio" | "research" | "research_book" =
    options.sourceScope ?? (snapshot === get(researchResult)?.snapshot ? "research" : "portfolio");
  const payload = {
    snapshot,
    source_scope: snapshotWorkspace,
    source_label: options.riskSourceLabel ?? null,
    source_object_id: options.riskSourceObjectId ?? null,
    source_origin: options.riskSourceOrigin ?? null,
    research_book_return_points: options.researchBookReturnPoints ?? [],
    research_book_legs: options.researchBookRiskLegs ?? [],
    alpha: options.alpha,
    lookback_days: options.lookbackDays,
    horizon_days: options.horizonDays,
    mc_horizon_days: options.mcHorizonDays,
    mc_simulation_model: options.mcSimulationModel,
    mc_num_simulations: options.mcNumSimulations,
    beta_window: options.betaWindow,
    benchmark_symbol: options.benchmarkSymbol,
    include_monte_carlo: options.includeMonteCarlo ?? true
  };
  const requestKey = stableJson(payload);
  return requestCoordinator.run("risk-compute", requestKey, async (signal) => {
    setLoading("risk", true);
    try {
      const result = await postJson<RiskResult>("/risk/compute", payload, { signal });
      if (signal.aborted) return null;
      riskResult.set(result);
      riskSnapshotBasis.set(snapshot);
      riskWorkspaceBasis.set(snapshotWorkspace);
      resetCopilotCard("risk");
      lastError.set("");
      return result;
    } catch (error) {
      if (!isAbortError(error)) setError(error);
      return null;
    } finally {
      if (requestCoordinator.isCurrent("risk-compute", signal)) setLoading("risk", false);
    }
  });
}

const COPILOT_SESSION_STORAGE_KEY = "gamma.copilot.session";

/**
 * The session the workspace currently displays, or `null` when nothing has been
 * selected yet. Never mints an id — an unselected workspace is a real state, not
 * a stale persisted id to reconcile away.
 */
function getSelectedCopilotSessionId(): string | null {
  if (typeof localStorage === "undefined") {
    return null;
  }
  const existing = localStorage.getItem(COPILOT_SESSION_STORAGE_KEY);
  return existing && existing.trim() ? existing : null;
}

function getCopilotSessionId() {
  if (typeof localStorage === "undefined") {
    return "gamma-copilot-session";
  }
  const existing = getSelectedCopilotSessionId();
  if (existing) {
    return existing;
  }
  const nextId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `gamma-${Date.now()}`;
  localStorage.setItem(COPILOT_SESSION_STORAGE_KEY, nextId);
  return nextId;
}

function setCopilotSessionId(sessionId: string) {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(COPILOT_SESSION_STORAGE_KEY, sessionId);
  }
}

function clearSelectedCopilotSessionId() {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(COPILOT_SESSION_STORAGE_KEY);
  }
}

function copilotArtifactStorageKey(sessionId: string) {
  return `gamma.copilot.artifact.${sessionId}`;
}

function getCopilotArtifactId(sessionId: string) {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(copilotArtifactStorageKey(sessionId));
}

function setCopilotArtifactId(sessionId: string, artifactId: string | null) {
  if (typeof localStorage === "undefined") return;
  const key = copilotArtifactStorageKey(sessionId);
  if (artifactId) {
    localStorage.setItem(key, artifactId);
  } else {
    localStorage.removeItem(key);
  }
}

function reconcileCopilotArtifacts(sessionId: string, artifacts: CopilotArtifact[]) {
  copilotArtifacts.set(artifacts);
  const preferredId = getCopilotArtifactId(sessionId);
  const selected =
    artifacts.find((artifact) => artifact.artifact_id === preferredId) ??
    artifacts[0] ??
    null;
  activeCopilotArtifact.set(selected);
  setCopilotArtifactId(sessionId, selected?.artifact_id ?? null);
  return selected;
}

type CopilotLoadOptions = {
  workspaceMode?: WorkspaceMode | null;
  synthesisDomains?: CopilotBaseDomain[];
  activeTabId?: TabId | "research";
  reasoningEffort?: CopilotReasoningEffort;
  selectedProfile?: CopilotProfile;
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

function normalizeReasoningEffort(effort: CopilotReasoningEffort | undefined) {
  return effort && ["minimal", "low", "medium", "high", "xhigh"].includes(effort)
    ? effort
    : undefined;
}

function buildCopilotContext(domain: CopilotDomain, workspaceMode: WorkspaceMode | null | undefined) {
  switch (domain) {
    case "sitrep":
      // The backend composes the SITREP bundle itself from SitrepService plus
      // the persisted follow-up store, so only tab/mode routing is sent.
      return {
        current_tab: "sitrep",
        workspace_mode: workspaceMode
      };
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
          result: get(researchResult),
          strategy_result: get(strategyLabResult),
          strategy_composition: get(strategyLabComposition),
          strategy_lab_handoffs: buildStrategyLabHandoffContextForCopilot()
        }
      };
    case "equity_research":
      return {
        current_tab: "equity_research",
        workspace_mode: workspaceMode,
        research_state: {
          overview: get(researchOverview),
          result: get(researchResult)
        }
      };
    case "strategy_lab":
      const scriptWorkspace = get(researchScriptWorkspace);
      const canonicalScriptRevision = scriptWorkspace.detail?.revisions.find(
        (item) => item.revision_id === scriptWorkspace.detail?.script.canonical_revision_id
      ) ?? null;
      return {
        current_tab: "strategy_lab",
        workspace_mode: workspaceMode,
        strategy_lab_state: {
          imported_result: get(strategyLabResult),
          composition: get(strategyLabComposition),
          compare_result: get(researchCompareResult),
          handoff_context: buildStrategyLabHandoffContextForCopilot(),
          script_state: scriptWorkspace.detail && canonicalScriptRevision
            ? {
                script_id: scriptWorkspace.detail.script.script_id,
                canonical_revision_id: canonicalScriptRevision.revision_id,
                source_sha256: canonicalScriptRevision.source_sha256,
                canonical_source: canonicalScriptRevision.source,
                selected_revision_id: scriptWorkspace.selectedRevisionId,
                selected_run_id: scriptWorkspace.selectedRun?.run_id ?? null,
                selected_run_status: scriptWorkspace.selectedRun?.status ?? null,
                input_snapshot_id: scriptWorkspace.selectedRun?.input_snapshot_id ?? null,
                manifest_sha256: scriptWorkspace.selectedRun?.input_manifest_sha256 ?? null,
                selected_run_outputs: scriptWorkspace.selectedRun?.outputs.map((item) => ({
                  output_id: item.output_id,
                  kind: item.kind,
                  media_type: item.media_type,
                  metric_name: item.metric_name,
                  metric_value: item.metric_value,
                  columns: item.columns,
                  rows: item.rows,
                  text: item.text,
                  filename: item.filename,
                  generated: item.generated
                })) ?? [],
                selected_run_warnings: scriptWorkspace.selectedRun?.warnings ?? [],
                staged_revision_ids: scriptWorkspace.detail.revisions
                  .filter((item) => item.status === "staged")
                  .map((item) => item.revision_id)
              }
            : null
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
    case "commodities":
      return {
        current_tab: "commodities",
        workspace_mode: workspaceMode,
        commodities_state: {
          workspace: get(commoditiesWorkspace)
        }
      };
    case "maritime":
      return {
        current_tab: "maritime",
        workspace_mode: workspaceMode,
        maritime_state: {
          workspace: get(maritimeWorkspace)
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
    case "fundamentals": {
      const fundamentalsTicker = get(selectedFundamentalsTicker);
      const fundamentalsOverviewState = get(fundamentalsOverview);
      const fundamentalsDcfState = get(fundamentalsDcfModel);
      const fundamentalsPeersState = get(fundamentalsPeers);
      const fundamentalsReverseState = get(fundamentalsReverseValuation);
      return {
        current_tab: "fundamentals",
        workspace_mode: workspaceMode,
        fundamentals_ticker: fundamentalsTicker,
        fundamentals_state: {
          ticker: fundamentalsTicker,
          company_name: fundamentalsOverviewState?.company.name ?? null,
          active_scenario_id: fundamentalsDcfState?.active_scenario_id ?? null,
          peer_tickers:
            fundamentalsPeersState?.peer_basket.display_order ??
            fundamentalsOverviewState?.peer_basket?.display_order ??
            [],
          reverse_drivers:
            fundamentalsReverseState?.drivers.map((driver) => ({
              driver_id: driver.driver_id,
              display_value: driver.display_value,
              base_display_value: driver.base_display_value,
              gap_display_value: driver.gap_display_value,
              success: driver.success
            })) ?? []
        }
      };
    }
    case "risk":
      return {
        current_tab: "risk",
        workspace_mode: get(riskWorkspaceBasis) ?? workspaceMode,
        risk_state: {
          mode: get(riskWorkspaceMode),
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
          session: get(ivSession),
          workbench: resolvedIvWorkbench()
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
  activeTabId: TabId | "research" | undefined
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
  if (domain === "sitrep" && !get(sitrepWorkspaceMeta)) {
    return "Load the SITREP workspace before including it in a synthesis card.";
  }
  if (domain === "research" && !get(researchResult)) {
    return "Run a Research analysis before including it in a synthesis card.";
  }
  if (domain === "equity_research" && !get(researchOverview) && !get(researchResult)) {
    return "Load Equity Research overview or run Scope Analysis before including it in a synthesis card.";
  }
  if (domain === "strategy_lab" && !hasActiveStrategyLabCopilotContext()) {
    return "Run a Strategy Lab import, composition, comparison, or queue a current Strategy Lab handoff before including it in a synthesis card.";
  }
  if (domain === "macro" && !get(macroSnapshot)) {
    return "Load the Macro workspace before including it in a synthesis card.";
  }
  if (domain === "commodities" && !get(commoditiesWorkspace)) {
    return "Load the Commodities workspace before including it in a synthesis card.";
  }
  if (domain === "maritime" && !get(maritimeWorkspace)) {
    return "Load the Sealanes workspace before including it in a synthesis card.";
  }
  if (domain === "prediction_markets" && !get(predictionMarketDetail)) {
    return "Select and load a Prediction Markets contract before including it in a synthesis card.";
  }
  if (domain === "crypto" && !get(cryptoTokenDetail)) {
    return "Select and load a crypto token before including it in a synthesis card.";
  }
  if (domain === "fundamentals" && !get(fundamentalsOverview)) {
    return "Select and load a Fundamentals company before including it in a synthesis card.";
  }
  if (domain === "risk" && !get(riskResult)) {
    return "Run a Risk computation before including it in a synthesis card.";
  }
  if (domain === "iv" && !hasRenderableIvSurface(resolvedIvSurface())) {
    return "Load an options surface before including it in a synthesis card.";
  }
  const context = buildCopilotContext(domain, workspaceMode);
  return context ? null : `The ${COPILOT_DOMAIN_LABELS[domain]} context is unavailable.`;
}

function validateCopilotContext(domain: CopilotDomain, options: CopilotLoadOptions = {}) {
  if (domain === "synthesis") {
    const synthesisDomains = normalizeSynthesisDomains(options.synthesisDomains);
    if (!synthesisDomains.length) {
      return "Select at least one loaded Gamma context before using Copilot.";
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
  if (domain === "sitrep" && !get(sitrepWorkspaceMeta)) {
    return "Load the SITREP workspace before generating a research card.";
  }
  if (domain === "research" && !get(researchResult)) {
    return "Run a research analysis before generating a research card.";
  }
  if (domain === "equity_research" && !get(researchOverview) && !get(researchResult)) {
    return "Load Equity Research overview or run Scope Analysis before generating a research card.";
  }
  if (domain === "strategy_lab" && !hasActiveStrategyLabCopilotContext()) {
    return "Run a Strategy Lab import, composition, comparison, or queue a current Strategy Lab handoff before generating a research card.";
  }
  if (domain === "commodities" && !get(commoditiesWorkspace)) {
    return "Load the Commodities workspace before generating a research card.";
  }
  if (domain === "prediction_markets" && !get(selectedPredictionMarketId)) {
    return "Select a prediction market before generating a research card.";
  }
  if (domain === "crypto" && !get(selectedCryptoTokenId)) {
    return "Select a crypto token before generating a research card.";
  }
  if (domain === "fundamentals" && !get(selectedFundamentalsTicker)) {
    return "Select a Fundamentals company before generating a research card.";
  }
  if (domain === "fundamentals" && !get(fundamentalsOverview)) {
    return "Load a Fundamentals company before generating a research card.";
  }
  if (domain === "risk" && !get(riskResult)) {
    return "Run a risk computation before generating a research card.";
  }
  if (domain === "iv" && !hasRenderableIvSurface(resolvedIvSurface())) {
    return "Load an options surface before generating a research card.";
  }
  if (
    domain === "portfolio" ||
    domain === "sitrep" ||
    domain === "research" ||
    domain === "equity_research" ||
    domain === "strategy_lab" ||
    domain === "commodities" ||
    domain === "crypto" ||
    domain === "fundamentals" ||
    domain === "risk" ||
    domain === "iv"
  ) {
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
  return streamCopilotResearchCard(domain, prompt, options);
}

const COPILOT_STREAM_TIMEOUT_MS = 330_000;

let activeCopilotRunId: string | null = null;

function newCopilotRunId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `run_${crypto.randomUUID().replaceAll("-", "")}`;
  }
  return `run_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

const COPILOT_RECONNECT_ATTEMPTS = 3;

/**
 * Track which conversation owns a non-terminal run.
 *
 * Switching sessions or starting a new chat does not cancel the run, so the
 * source conversation keeps a visible running indicator until it settles.
 */
/**
 * True when a settled run still belongs to the displayed conversation.
 *
 * If the user started a new chat or switched sessions mid-run, the result stays
 * with its own session on the server and replays there; it must not be appended
 * to the transcript now on screen.
 */
function isCopilotRunSessionStillSelected(runSessionId: string) {
  const selected = getSelectedCopilotSessionId();
  return selected == null || selected === runSessionId;
}

function markCopilotSessionRunning(sessionId: string | null, running: boolean) {
  if (!sessionId) {
    return;
  }
  copilotRunningSessionIds.update((items) => {
    const without = items.filter((item) => item !== sessionId);
    return running ? [...without, sessionId] : without;
  });
}

let copilotSubmissionSequence = 0;

/** Record a composer submission before any network work happens. */
function beginCopilotSubmission(
  role: CopilotSubmissionRecord["role"],
  prompt: string,
  sessionId: string | null
): CopilotSubmissionRecord {
  copilotSubmissionSequence += 1;
  const record: CopilotSubmissionRecord = {
    submissionId: copilotSubmissionSequence,
    sessionId,
    role,
    prompt,
    accepted: false,
    rejectedReason: null
  };
  copilotLastSubmission.set(record);
  return record;
}

function acceptCopilotSubmission(record: CopilotSubmissionRecord) {
  if (record.accepted) {
    return;
  }
  record.accepted = true;
  copilotLastSubmission.update((current) =>
    current?.submissionId === record.submissionId ? { ...current, accepted: true } : current
  );
}

/** Mark a submission the server never accepted, so the draft is preserved. */
function rejectCopilotSubmission(record: CopilotSubmissionRecord, reason: string) {
  if (record.accepted) {
    return;
  }
  record.rejectedReason = reason;
  copilotLastSubmission.update((current) =>
    current?.submissionId === record.submissionId ? { ...current, rejectedReason: reason } : current
  );
}

async function consumeCopilotRun(
  endpoint: string,
  payload: Record<string, unknown>,
  runId: string,
  domain: CopilotDomain,
  signal: AbortSignal,
  onAccepted: () => void = () => {}
): Promise<{ state: CopilotRunState; result: CopilotResearchCardResult }> {
  let runState = createCopilotRunState(runId);
  let finalResult: CopilotResearchCardResult | null = null;
  let attempt = 0;
  copilotActiveRun.set(runState);

  const onLine = (line: string) => {
    let event: CopilotRunEvent;
    try {
      event = JSON.parse(line) as CopilotRunEvent;
    } catch {
      return;
    }
    const previouslyAccepted = runState.accepted;
    runState = reduceCopilotRunEvent(runState, event);
    copilotActiveRun.set(runState);
    if (!previouslyAccepted && runState.accepted) {
      onAccepted();
    }
    if (finalResult == null && isTerminalCopilotRunEvent(event) && runState.rawResult != null) {
      finalResult = normalizeCopilotResearchCardResult(domain, runState.rawResult);
    }
  };

  while (finalResult == null && attempt < COPILOT_RECONNECT_ATTEMPTS) {
    try {
      if (attempt === 0) {
        await postNdjsonStream(endpoint, payload, onLine, { signal });
      } else {
        await getNdjsonStream(
          `/copilot/runs/${encodeURIComponent(runId)}/events?after_sequence=${runState.lastSequence}`,
          onLine,
          { signal }
        );
      }
    } catch (error) {
      if (signal.aborted) {
        throw error;
      }
      if (attempt + 1 >= COPILOT_RECONNECT_ATTEMPTS) {
        throw error;
      }
    }
    attempt += 1;
  }

  if (finalResult == null) {
    throw new Error("Copilot stream ended without a replayable terminal result.");
  }
  return { state: runState, result: finalResult };
}

export async function cancelCopilotRun() {
  const runId = activeCopilotRunId;
  if (!runId) {
    return null;
  }
  try {
    // The backend delivers the terminal `cancelled` event through the open
    // stream, so the stream reader — not this call — settles the run.
    return await postJson<{ run_id: string; found: boolean; cancelled: boolean }>(
      `/copilot/runs/${runId}/cancel`,
      {}
    );
  } catch {
    // The run may already have finished; a failed cancel is not an error state.
    return null;
  }
}

export async function streamCopilotResearchCard(
  domain: CopilotDomain,
  prompt = "",
  options: CopilotLoadOptions = {}
) {
  setLoading("copilot", true);
  const contextFingerprint = buildCopilotContextFingerprint(domain, options.workspaceMode, {
    synthesisDomains: options.synthesisDomains,
    activeTabId: options.activeTabId
  });
  let activeThread = get(copilotThreads)[domain];
  if (!activeThread) {
    activeThread = createEmptyCopilotThread(domain);
  }
  const continuingThread =
    activeThread.contextFingerprint != null &&
    activeThread.contextFingerprint === contextFingerprint &&
    activeThread.latestResponseId != null;
  const previousResponseId = continuingThread ? activeThread.latestResponseId : null;
  let baseThread =
    continuingThread || !activeThread.entries.length
      ? activeThread
      : createEmptyCopilotThread(domain);
  const submission = beginCopilotSubmission("research_agent", prompt, getSelectedCopilotSessionId());

  try {
    const validationError = validateCopilotContext(domain, options);
    if (validationError) {
      lastError.set(validationError);
      rejectCopilotSubmission(submission, validationError);
      const result = buildCopilotFailureResult(domain, validationError);
      appendCopilotThreadResult(domain, result, prompt, contextFingerprint, previousResponseId, baseThread);
      return result;
    }
    const context = buildCopilotContext(domain, options.workspaceMode);
    if (!context) {
      const message = "The active Copilot context is unavailable.";
      lastError.set(message);
      rejectCopilotSubmission(submission, message);
      const result = buildCopilotFailureResult(domain, message);
      appendCopilotThreadResult(domain, result, prompt, contextFingerprint, previousResponseId, baseThread);
      return result;
    }

    const synthesis =
      domain === "synthesis"
        ? buildCopilotSynthesisPayload(options.synthesisDomains, options.workspaceMode, options.activeTabId)
        : null;
    if (domain === "synthesis" && !synthesis) {
      const message = "The active synthesis scope is unavailable.";
      lastError.set(message);
      rejectCopilotSubmission(submission, message);
      const result = buildCopilotFailureResult(domain, message);
      appendCopilotThreadResult(domain, result, prompt, contextFingerprint, previousResponseId, baseThread);
      return result;
    }

    if (!continuingThread && activeThread.entries.length) {
      resetCopilotCard(domain);
      baseThread = createEmptyCopilotThread(domain);
    }

    const runId = newCopilotRunId();
    const selectedScopeDomains =
      domain === "synthesis" ? options.synthesisDomains ?? [] : [domain];
    const runSessionId = getCopilotSessionId();
    submission.sessionId = runSessionId;
    const payload = {
      domain,
      prompt,
      role: "research_agent",
      selected_scope_domains: selectedScopeDomains,
      user_session_id: runSessionId,
      context_fingerprint: contextFingerprint,
      run_id: runId,
      ...(normalizeReasoningEffort(options.reasoningEffort)
        ? { reasoning_effort: normalizeReasoningEffort(options.reasoningEffort) }
        : {}),
      ...(normalizeCopilotProfile(options.selectedProfile)
        ? { selected_profile: normalizeCopilotProfile(options.selectedProfile) }
        : {}),
      ...(previousResponseId ? { previous_response_id: previousResponseId } : {}),
      context,
      ...(synthesis ? { synthesis } : {})
    };

    const controller = new AbortController();
    activeCopilotRunId = runId;
    markCopilotSessionRunning(runSessionId, true);
    const timer = setTimeout(() => controller.abort(), COPILOT_STREAM_TIMEOUT_MS);
    let streamed: { state: CopilotRunState; result: CopilotResearchCardResult };
    try {
      streamed = await consumeCopilotRun(
        "/copilot/research-card/stream",
        payload,
        runId,
        domain,
        controller.signal,
        () => acceptCopilotSubmission(submission)
      );
    } finally {
      clearTimeout(timer);
      markCopilotSessionRunning(runSessionId, false);
    }
    const settled = streamed.result;
    if (isCopilotRunSessionStillSelected(runSessionId)) {
      appendCopilotThreadResult(
        domain,
        settled,
        prompt,
        contextFingerprint,
        previousResponseId,
        baseThread,
        runSessionId
      );
    }
    lastError.set(settled.status === "ready" ? "" : settled.message ?? "Copilot failed.");
    return settled;
  } catch (error) {
    const message = errorMessage(error).includes("timed out")
      ? `${errorMessage(error)}. Your prompt draft is preserved; retry or reduce the synthesis scope.`
      : errorMessage(error);
    lastError.set(message);
    rejectCopilotSubmission(submission, message);
    const result = buildCopilotFailureResult(domain, message);
    appendCopilotThreadResult(domain, result, prompt, contextFingerprint, previousResponseId, baseThread);
    return result;
  } finally {
    activeCopilotRunId = null;
    copilotActiveRun.set(null);
    setLoading("copilot", false);
  }
}

export async function loadCopilotResearchPlan(
  domain: CopilotDomain,
  prompt = "",
  options: CopilotLoadOptions = {}
) {
  setLoading("copilot", true);
  try {
    const context = buildCopilotContext(domain, options.workspaceMode);
    if (!context) {
      const message = "The active Copilot context is unavailable.";
      lastError.set(message);
      copilotResearchPlan.set(null);
      return null;
    }
    const synthesis =
      domain === "synthesis"
        ? buildCopilotSynthesisPayload(options.synthesisDomains, options.workspaceMode, options.activeTabId)
        : null;
    const payload = {
      domain,
      prompt,
      role: "research_agent",
      selected_scope_domains:
        domain === "synthesis" ? options.synthesisDomains ?? [] : [domain],
      ...(normalizeReasoningEffort(options.reasoningEffort)
        ? { reasoning_effort: normalizeReasoningEffort(options.reasoningEffort) }
        : {}),
      ...(normalizeCopilotProfile(options.selectedProfile)
        ? { selected_profile: normalizeCopilotProfile(options.selectedProfile) }
        : {}),
      context_fingerprint: buildCopilotContextFingerprint(domain, options.workspaceMode, {
        synthesisDomains: options.synthesisDomains,
        activeTabId: options.activeTabId
      }),
      context,
      ...(synthesis ? { synthesis } : {})
    };
    const plan = normalizeCopilotResearchPlan(await postJson<CopilotResearchPlan>("/copilot/research-plan", payload));
    copilotResearchPlan.set(plan);
    lastError.set("");
    return plan;
  } catch (error) {
    setError(error);
    copilotResearchPlan.set(null);
    return null;
  } finally {
    setLoading("copilot", false);
  }
}

export async function loadCopilotActionDefinitions() {
  try {
    const definitions = await getJson<CopilotResearchActionDefinition[]>("/copilot/actions");
    copilotActionDefinitions.set(normalizeCopilotActionDefinitions(definitions));
    lastError.set("");
    return definitions;
  } catch (error) {
    setError(error);
    copilotActionDefinitions.set([]);
    return [];
  }
}

export async function loadCopilotOperatorPlan(
  domain: CopilotDomain,
  prompt = "",
  options: CopilotLoadOptions = {}
) {
  setLoading("copilot", true);
  try {
    const context = buildCopilotContext(domain, options.workspaceMode);
    if (!context) {
      const message = "The active Copilot context is unavailable.";
      lastError.set(message);
      copilotOperatorPlan.set(null);
      return null;
    }
    const synthesis =
      domain === "synthesis"
        ? buildCopilotSynthesisPayload(options.synthesisDomains, options.workspaceMode, options.activeTabId)
        : null;
    const payload = {
      domain,
      prompt,
      role: "research_operator",
      selected_scope_domains:
        domain === "synthesis" ? options.synthesisDomains ?? [] : [domain],
      user_session_id: getCopilotSessionId(),
      ...(normalizeReasoningEffort(options.reasoningEffort)
        ? { reasoning_effort: normalizeReasoningEffort(options.reasoningEffort) }
        : {}),
      ...(normalizeCopilotProfile(options.selectedProfile)
        ? { selected_profile: normalizeCopilotProfile(options.selectedProfile) }
        : {}),
      context_fingerprint: buildCopilotContextFingerprint(domain, options.workspaceMode, {
        synthesisDomains: options.synthesisDomains,
        activeTabId: options.activeTabId
      }),
      context,
      ...(synthesis ? { synthesis } : {})
    };
    const plan = normalizeCopilotOperatorPlan(await postJson<CopilotOperatorPlan>("/copilot/operator-plan", payload));
    copilotOperatorPlan.set(plan);
    lastError.set("");
    return plan;
  } catch (error) {
    setError(error);
    copilotOperatorPlan.set(null);
    return null;
  } finally {
    setLoading("copilot", false);
  }
}

export async function executeCopilotOperatorPlan(
  domain: CopilotDomain,
  prompt = "",
  options: CopilotLoadOptions = {}
) {
  setLoading("copilot", true);
  const contextFingerprint = buildCopilotContextFingerprint(domain, options.workspaceMode, {
    synthesisDomains: options.synthesisDomains,
    activeTabId: options.activeTabId
  });
  const activeThread = get(copilotThreads)[domain] ?? createEmptyCopilotThread(domain);
  const baseThread =
    activeThread.contextFingerprint === contextFingerprint
      ? activeThread
      : createEmptyCopilotThread(domain);
  const submission = beginCopilotSubmission("research_operator", prompt, getSelectedCopilotSessionId());

  try {
    const context = buildCopilotContext(domain, options.workspaceMode);
    if (!context) {
      const message = "The active Copilot context is unavailable.";
      lastError.set(message);
      rejectCopilotSubmission(submission, message);
      const result = buildCopilotFailureResult(domain, message);
      copilotOperatorResult.set(result);
      appendCopilotThreadResult(
        domain,
        result,
        prompt,
        contextFingerprint,
        null,
        baseThread
      );
      return result;
    }
    const synthesis =
      domain === "synthesis"
        ? buildCopilotSynthesisPayload(options.synthesisDomains, options.workspaceMode, options.activeTabId)
        : null;
    const runId = newCopilotRunId();
    const runSessionId = getCopilotSessionId();
    submission.sessionId = runSessionId;
    const payload = {
      domain,
      prompt,
      role: "research_operator",
      selected_scope_domains:
        domain === "synthesis" ? options.synthesisDomains ?? [] : [domain],
      run_id: runId,
      user_session_id: runSessionId,
      context_fingerprint: contextFingerprint,
      ...(normalizeReasoningEffort(options.reasoningEffort)
        ? { reasoning_effort: normalizeReasoningEffort(options.reasoningEffort) }
        : {}),
      ...(normalizeCopilotProfile(options.selectedProfile)
        ? { selected_profile: normalizeCopilotProfile(options.selectedProfile) }
        : {}),
      context,
      ...(synthesis ? { synthesis } : {})
    };
    const controller = new AbortController();
    activeCopilotRunId = runId;
    markCopilotSessionRunning(runSessionId, true);
    const timer = setTimeout(() => controller.abort(), COPILOT_OPERATOR_TIMEOUT_MS);
    let streamed: { state: CopilotRunState; result: CopilotResearchCardResult };
    try {
      streamed = await consumeCopilotRun(
        "/copilot/operator-plan/execute/stream",
        payload,
        runId,
        domain,
        controller.signal,
        () => acceptCopilotSubmission(submission)
      );
    } finally {
      clearTimeout(timer);
      markCopilotSessionRunning(runSessionId, false);
    }
    const result = streamed.result;
    if (isCopilotRunSessionStillSelected(runSessionId)) {
      copilotOperatorResult.set(result);
      appendCopilotThreadResult(
        domain,
        result,
        prompt,
        contextFingerprint,
        null,
        baseThread,
        runSessionId
      );
    }
    await Promise.allSettled([loadActiveCopilotSession(), loadCopilotSessions()]);
    lastError.set(
      ["ready", "awaiting_confirmation"].includes(result.status)
        ? ""
        : result.message ?? "Research Operator failed."
    );
    return result;
  } catch (error) {
    const message = errorMessage(error);
    lastError.set(message);
    rejectCopilotSubmission(submission, message);
    const result = buildCopilotFailureResult(domain, message);
    copilotOperatorResult.set(result);
    appendCopilotThreadResult(domain, result, prompt, contextFingerprint, null, baseThread);
    return result;
  } finally {
    activeCopilotRunId = null;
    copilotActiveRun.set(null);
    setLoading("copilot", false);
  }
}

function normalizeCopilotProfile(profile: CopilotProfile | undefined) {
  return profile && ["auto", "quick", "standard", "deep"].includes(profile)
    ? profile
    : undefined;
}

function resultWithResolvedMutation(
  result: CopilotResearchCardResult,
  mutation: CopilotDraftMutation
): CopilotResearchCardResult {
  let matched = false;
  const operatorEvents = (result.operator_events ?? []).map((event) => {
    if (event.payload?.mutation_id !== mutation.mutation_id) return event;
    matched = true;
    return {
      ...event,
      payload: {
        ...event.payload,
        status: mutation.status,
        rollback_snapshot_id: mutation.rollback_snapshot_id,
        mutation
      }
    };
  });
  if (!matched) return result;
  const status =
    result.status === "awaiting_confirmation"
      ? ["failed", "expired"].includes(mutation.status)
        ? "error"
        : mutation.status === "pending"
          ? result.status
          : "ready"
      : result.status;
  const message =
    mutation.status === "applied"
      ? `Confirmed mutation applied to ${mutation.target_label}.`
      : mutation.status === "rejected"
        ? `Mutation rejected for ${mutation.target_label}; no local research state changed.`
        : mutation.status === "failed"
          ? `Confirmed mutation failed for ${mutation.target_label}.`
          : mutation.status === "expired"
            ? `Mutation confirmation expired for ${mutation.target_label}.`
          : result.message;
  return { ...result, status, message, operator_events: operatorEvents };
}

function reconcileResolvedCopilotMutation(mutation: CopilotDraftMutation) {
  copilotOperatorResult.update((result) =>
    result ? resultWithResolvedMutation(result, mutation) : result
  );
  copilotThreads.update((threads) =>
    Object.fromEntries(
      Object.entries(threads).map(([domain, thread]) => [
        domain,
        {
          ...thread,
          entries: thread.entries.map((entry) => ({
            ...entry,
            result: resultWithResolvedMutation(entry.result, mutation)
          }))
        }
      ])
    ) as Record<CopilotDomain, CopilotThreadState>
  );
  activeCopilotSession.update((detail) =>
    detail == null
      ? detail
      : {
          ...detail,
          mutations: (detail.mutations ?? []).map((item) =>
            item.mutation_id === mutation.mutation_id ? mutation : item
          ),
          turns: detail.turns.map((turn) => ({
            ...turn,
            result: resultWithResolvedMutation(turn.result, mutation),
            confirmations: turn.confirmations.map((confirmation) =>
              confirmation.mutation_id === mutation.mutation_id
                ? {
                    ...confirmation,
                    status: mutation.status,
                    rollback_snapshot_id: mutation.rollback_snapshot_id,
                    resolved_at:
                      mutation.applied_at
                      ?? mutation.rejected_at
                      ?? mutation.confirmed_at
                      ?? confirmation.resolved_at
                  }
                : confirmation
            )
          }))
        }
  );
}

export async function confirmCopilotMutation(mutation: CopilotDraftMutation) {
  try {
    const result = await postJson<CopilotMutationApplyResult>(
      `/copilot/mutations/${encodeURIComponent(mutation.mutation_id)}/apply`,
      {
        confirmation_token: mutation.confirmation_token,
        user_session_id: mutation.session_id ?? null,
        context_fingerprint: mutation.context_fingerprint ?? null,
        proposal_hash: mutation.proposal_hash ?? null
      }
    );
    reconcileResolvedCopilotMutation(result.mutation);
    await Promise.allSettled([loadActiveCopilotSession(), loadCopilotSessions()]);
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function rejectCopilotMutation(mutation: CopilotDraftMutation) {
  try {
    const rejected = await postJson<CopilotDraftMutation>(
      `/copilot/mutations/${encodeURIComponent(mutation.mutation_id)}/reject`,
      { user_session_id: mutation.session_id ?? null }
    );
    reconcileResolvedCopilotMutation(rejected);
    await Promise.allSettled([loadActiveCopilotSession(), loadCopilotSessions()]);
    lastError.set("");
    return rejected;
  } catch (error) {
    setError(error);
    return null;
  }
}

function normalizeCopilotResearchPlan(plan: CopilotResearchPlan): CopilotResearchPlan {
  const domainPlan = Array.isArray(plan.domain_plan)
    ? plan.domain_plan.map((item) => ({
        ...item,
        planned_tools: Array.isArray(item.planned_tools) ? item.planned_tools : [],
        required_context: Array.isArray(item.required_context) ? item.required_context : [],
        estimated_tool_calls: Number.isFinite(item.estimated_tool_calls)
          ? item.estimated_tool_calls
          : Array.isArray(item.planned_tools)
            ? item.planned_tools.length
            : 0,
        estimated_provider_calls: Number.isFinite(item.estimated_provider_calls) ? item.estimated_provider_calls : 0,
        estimated_latency_ms: Number.isFinite(item.estimated_latency_ms) ? item.estimated_latency_ms : 0
      }))
    : [];
  const fallbackToolLimit = domainPlan.reduce((total, item) => total + item.estimated_tool_calls, 0);
  const fallbackProviderLimit = domainPlan.reduce((total, item) => total + item.estimated_provider_calls, 0);
  const fallbackElapsedLimit = domainPlan.reduce((total, item) => total + item.estimated_latency_ms, 0);
  return {
    ...plan,
    target_entities: Array.isArray(plan.target_entities) ? plan.target_entities : [],
    entity_resolution: plan.entity_resolution
      ? {
          ...plan.entity_resolution,
          resolved: plan.entity_resolution.resolved ?? null,
          candidates: Array.isArray(plan.entity_resolution.candidates)
            ? plan.entity_resolution.candidates
            : [],
          warnings: Array.isArray(plan.entity_resolution.warnings)
            ? plan.entity_resolution.warnings
            : []
        }
      : null,
    domain_plan: domainPlan,
    domain_decisions: Array.isArray(plan.domain_decisions) ? plan.domain_decisions : [],
    expected_artifacts: Array.isArray(plan.expected_artifacts) ? plan.expected_artifacts : [],
    warnings: Array.isArray(plan.warnings) ? plan.warnings : [],
    max_tool_calls: Number.isFinite(plan.max_tool_calls) ? plan.max_tool_calls : fallbackToolLimit,
    max_provider_calls: Number.isFinite(plan.max_provider_calls) ? plan.max_provider_calls : fallbackProviderLimit,
    max_elapsed_ms: Number.isFinite(plan.max_elapsed_ms) ? plan.max_elapsed_ms : fallbackElapsedLimit
  };
}

function normalizeCopilotActionDefinitions(
  definitions: CopilotResearchActionDefinition[]
): CopilotResearchActionDefinition[] {
  return Array.isArray(definitions)
    ? definitions.map((definition) => ({
        ...definition,
        domains: Array.isArray(definition.domains) ? definition.domains : [],
        input_schema: definition.input_schema ?? {},
        output_schema: definition.output_schema ?? {},
        failure_modes: Array.isArray(definition.failure_modes) ? definition.failure_modes : [],
        read_only: definition.read_only !== false,
        mutates_local_state: definition.mutates_local_state === true,
        requires_confirmation: definition.requires_confirmation === true,
        can_call_external_providers: definition.can_call_external_providers === true,
        request_limit: Number.isFinite(definition.request_limit) ? definition.request_limit : 1,
        timeout_seconds: Number.isFinite(definition.timeout_seconds) ? definition.timeout_seconds : 30
      }))
    : [];
}

function normalizeCopilotOperatorPlan(plan: CopilotOperatorPlan): CopilotOperatorPlan {
  const steps = Array.isArray(plan.steps)
    ? plan.steps.map((step) => ({
        ...step,
        expected_artifacts: Array.isArray(step.expected_artifacts) ? step.expected_artifacts : [],
        stop_conditions: Array.isArray(step.stop_conditions) ? step.stop_conditions : [],
        warnings: Array.isArray(step.warnings) ? step.warnings : [],
        estimated_latency_ms: Number.isFinite(step.estimated_latency_ms) ? step.estimated_latency_ms : 0,
        requires_confirmation: step.requires_confirmation === true
      }))
    : [];
  const fallbackElapsedLimit = steps.reduce((total, step) => total + step.estimated_latency_ms, 0);
  return {
    ...plan,
    target_entities: Array.isArray(plan.target_entities) ? plan.target_entities : [],
    research_plan: plan.research_plan ? normalizeCopilotResearchPlan(plan.research_plan) : null,
    steps,
    confirmation_checkpoints: Array.isArray(plan.confirmation_checkpoints)
      ? plan.confirmation_checkpoints.map((checkpoint) => ({
          ...checkpoint,
          required_for_tool_ids: Array.isArray(checkpoint.required_for_tool_ids)
            ? checkpoint.required_for_tool_ids
            : []
        }))
      : [],
    expected_artifacts: Array.isArray(plan.expected_artifacts) ? plan.expected_artifacts : [],
    warnings: Array.isArray(plan.warnings) ? plan.warnings : [],
    max_tool_calls: Number.isFinite(plan.max_tool_calls) ? plan.max_tool_calls : steps.length,
    max_provider_calls: Number.isFinite(plan.max_provider_calls) ? plan.max_provider_calls : 0,
    max_elapsed_ms: Number.isFinite(plan.max_elapsed_ms) ? plan.max_elapsed_ms : fallbackElapsedLimit,
    requires_confirmation: plan.requires_confirmation === true
  };
}

export async function loadCopilotSessions(options: { includeArchived?: boolean; search?: string } = {}) {
  try {
    const params = new URLSearchParams();
    if (options.includeArchived) {
      params.set("include_archived", "true");
    }
    if (options.search?.trim()) {
      params.set("search", options.search.trim());
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const sessions = await getJson<CopilotSessionSummary[]>(`/copilot/sessions${suffix}`);
    copilotSessions.set(sessions);
    lastError.set("");
    return sessions;
  } catch (error) {
    setError(error);
    return [];
  }
}

export async function loadCopilotDiagnostics() {
  try {
    const result = await getJson<CopilotDiagnostics>("/copilot/diagnostics");
    copilotDiagnostics.set(result);
    return result;
  } catch (error) {
    setError(error);
    copilotDiagnostics.set(null);
    return null;
  }
}

export async function promoteCopilotShelfThread(
  thread: CopilotThreadState,
  options: {
    selectedScopeDomains?: CopilotBaseDomain[];
    role?: "research_agent" | "research_operator";
    selectedProfile?: CopilotProfile;
  } = {}
) {
  const sourceSessionId = thread.sourceSessionId ?? getSelectedCopilotSessionId();
  try {
    const promotion = await postJson<CopilotShelfPromotion>(
      "/copilot/shelf/promote",
      {
        source_session_id: sourceSessionId ?? "",
        source_domain: thread.domain,
        context_fingerprint: thread.contextFingerprint,
        entries: thread.entries.map((entry) => ({
          turn_index: entry.turnIndex,
          prompt: entry.prompt,
          response_id: entry.result.response_id
        })),
        selected_scope_domains:
          options.selectedScopeDomains
          ?? (thread.domain === "synthesis" ? [] : [thread.domain as CopilotBaseDomain]),
        role: options.role ?? "research_agent",
        selected_profile: options.selectedProfile ?? "auto"
      }
    );
    if (["promoted", "already_promoted"].includes(promotion.status)) {
      await loadCopilotSession(promotion.source_session_id, { makeActive: true });
      await Promise.allSettled([loadCopilotSessions(), loadCopilotDiagnostics()]);
      lastError.set("");
    } else {
      lastError.set(promotion.message);
    }
    return promotion;
  } catch (error) {
    setError(error);
    return null;
  }
}

function clearActiveCopilotSessionState() {
  activeCopilotSession.set(null);
  copilotMemos.set([]);
  copilotArtifacts.set([]);
  activeCopilotArtifact.set(null);
  copilotArtifactSaveState.set("idle");
}

export async function loadActiveCopilotSession() {
  const sessionId = getSelectedCopilotSessionId();
  if (!sessionId) {
    // Nothing is selected yet. Adopt the newest unarchived conversation when one
    // exists; otherwise stay on an honest empty workspace instead of erroring.
    const sessions = await loadCopilotSessions();
    const fallback = sessions.find((session) => session.archived_at == null) ?? null;
    if (!fallback) {
      clearActiveCopilotSessionState();
      return null;
    }
    return loadCopilotSession(fallback.session_id, { makeActive: true });
  }
  try {
    const detail = await getJson<CopilotSessionDetail>(`/copilot/sessions/${encodeURIComponent(sessionId)}`);
    activeCopilotSession.set(detail);
    copilotMemos.set(detail.memos);
    reconcileCopilotArtifacts(sessionId, detail.artifacts ?? []);
    lastError.set("");
    return detail;
  } catch (error) {
    const sessions = await loadCopilotSessions();
    const fallback = sessions.find((session) => session.archived_at == null) ?? sessions[0] ?? null;
    if (fallback && fallback.session_id !== sessionId) {
      setCopilotSessionId(fallback.session_id);
      try {
        const detail = await getJson<CopilotSessionDetail>(
          `/copilot/sessions/${encodeURIComponent(fallback.session_id)}`
        );
        activeCopilotSession.set(detail);
        copilotMemos.set(detail.memos);
        reconcileCopilotArtifacts(fallback.session_id, detail.artifacts ?? []);
        lastError.set("");
        return detail;
      } catch (fallbackError) {
        setError(fallbackError);
      }
    } else {
      clearActiveCopilotSessionState();
      setError(error);
    }
    return null;
  }
}

export async function loadCopilotSession(sessionId: string, options: { makeActive?: boolean } = {}) {
  const switchingSession = options.makeActive === true && getSelectedCopilotSessionId() !== sessionId;
  try {
    const detail = await getJson<CopilotSessionDetail>(`/copilot/sessions/${encodeURIComponent(sessionId)}`);
    if (options.makeActive) {
      setCopilotSessionId(sessionId);
    }
    if (switchingSession) {
      // The in-memory thread belongs to the conversation being left; the newly
      // selected session must render from its own persisted turns.
      resetAllCopilotThreads();
      copilotResearchPlan.set(null);
      copilotOperatorPlan.set(null);
      copilotOperatorResult.set(null);
      copilotLastSubmission.set(null);
    }
    activeCopilotSession.set(detail);
    copilotMemos.set(detail.memos);
    reconcileCopilotArtifacts(sessionId, detail.artifacts ?? []);
    lastError.set("");
    return detail;
  } catch (error) {
    setError(error);
    return null;
  }
}

function emptyCopilotSessionDetail(session: CopilotSessionSummary): CopilotSessionDetail {
  return {
    session,
    turns: [],
    memos: [],
    context_snapshots: [],
    artifacts: [],
    mutations: [],
    working_analyses: [],
    storage_warnings: []
  };
}

function reconcileWorkingAnalysis(analysis: CopilotWorkingAnalysis) {
  activeCopilotSession.update((detail) => {
    if (!detail || detail.session.session_id !== analysis.session_id) {
      return detail;
    }
    return {
      ...detail,
      working_analyses: [
        analysis,
        ...(detail.working_analyses ?? []).filter(
          (item) => item.analysis_id !== analysis.analysis_id
        )
      ]
    };
  });
}

export async function materializeCopilotWorkingAnalysis(analysisId: string) {
  try {
    const analysis = await postJson<CopilotWorkingAnalysis>(
      `/copilot/working-analyses/${encodeURIComponent(analysisId)}/materialize`,
      {}
    );
    reconcileWorkingAnalysis(analysis);
    lastError.set("");
    return analysis;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function discardCopilotWorkingAnalysis(analysisId: string) {
  try {
    const analysis = await postJson<CopilotWorkingAnalysis>(
      `/copilot/working-analyses/${encodeURIComponent(analysisId)}/discard`,
      {}
    );
    reconcileWorkingAnalysis(analysis);
    lastError.set("");
    return analysis;
  } catch (error) {
    setError(error);
    return null;
  }
}

/** Select an authoritative session and reset every per-conversation surface. */
function selectCopilotSessionLocally(session: CopilotSessionSummary, detail: CopilotSessionDetail | null = null) {
  setCopilotSessionId(session.session_id);
  activeCopilotSession.set(detail ?? emptyCopilotSessionDetail(session));
  copilotMemos.set(detail?.memos ?? []);
  reconcileCopilotArtifacts(session.session_id, detail?.artifacts ?? []);
  copilotArtifactSaveState.set("idle");
  copilotResearchPlan.set(null);
  copilotOperatorPlan.set(null);
  copilotOperatorResult.set(null);
  copilotLastSubmission.set(null);
  resetAllCopilotThreads();
}

let copilotSessionCreateInFlight: Promise<CopilotSessionSummary | null> | null = null;

async function requestNewCopilotSession(title: string | null): Promise<CopilotSessionSummary | null> {
  copilotSessionCreating.set(true);
  copilotSessionCreateError.set(null);
  try {
    const session = await postJson<CopilotSessionSummary>("/copilot/sessions", {
      title,
      session_id: null
    });
    copilotSessions.update((items) => [
      session,
      ...items.filter((item) => item.session_id !== session.session_id)
    ]);
    selectCopilotSessionLocally(session);
    lastError.set("");
    return session;
  } catch (error) {
    // An unusable New chat must say so rather than silently doing nothing.
    copilotSessionCreateError.set(errorMessage(error));
    setError(error);
    return null;
  } finally {
    copilotSessionCreating.set(false);
  }
}

/**
 * Create exactly one authoritative blank session and select it.
 *
 * Concurrent activations (double click, Enter plus click) share the in-flight
 * request so a second empty session is never created.
 */
export async function startNewCopilotSession(options: { title?: string | null } = {}) {
  if (copilotSessionCreateInFlight) {
    return copilotSessionCreateInFlight;
  }
  const request = requestNewCopilotSession(options.title ?? null);
  copilotSessionCreateInFlight = request;
  try {
    return await request;
  } finally {
    copilotSessionCreateInFlight = null;
  }
}

export async function loadCopilotMemos(sessionId?: string | null) {
  try {
    const suffix = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
    const memos = await getJson<CopilotMemo[]>(`/copilot/memos${suffix}`);
    copilotMemos.set(memos);
    lastError.set("");
    return memos;
  } catch (error) {
    setError(error);
    return [];
  }
}

export async function loadCopilotStorageStatus() {
  try {
    const status = await getJson<CopilotStorageStatus>("/copilot/storage-status");
    copilotStorageStatus.set(status);
    lastError.set("");
    return status;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function renameCopilotSession(
  sessionId: string,
  title: string,
  expectedUpdatedAt?: string | null
) {
  try {
    const session = await patchJson<CopilotSessionSummary>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}`,
      {
        title,
        expected_updated_at: expectedUpdatedAt ?? null
      }
    );
    copilotSessions.update((items) =>
      items.map((item) => (item.session_id === session.session_id ? session : item))
    );
    activeCopilotSession.update((detail) =>
      detail?.session.session_id === session.session_id ? { ...detail, session } : detail
    );
    lastError.set("");
    return session;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function restoreCopilotSession(sessionId: string) {
  try {
    const session = await postJson<CopilotSessionSummary>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/restore`,
      {}
    );
    copilotSessions.update((items) =>
      items.map((item) => (item.session_id === session.session_id ? session : item))
    );
    activeCopilotSession.update((detail) =>
      detail?.session.session_id === session.session_id ? { ...detail, session } : detail
    );
    lastError.set("");
    return session;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function deleteCopilotSession(sessionId: string) {
  try {
    const result = await deleteJson<CopilotDeleteResult>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}?confirm_session_id=${encodeURIComponent(sessionId)}`
    );
    const remaining = get(copilotSessions).filter((item) => item.session_id !== sessionId);
    copilotSessions.set(remaining);
    copilotRunningSessionIds.update((items) => items.filter((item) => item !== sessionId));
    if (getSelectedCopilotSessionId() === sessionId) {
      const fallback = remaining.find((session) => session.archived_at == null) ?? remaining[0] ?? null;
      if (fallback) {
        await loadCopilotSession(fallback.session_id, { makeActive: true });
      } else {
        // Nothing left to select. Stay on an empty workspace; `New chat` is the
        // explicit action that creates the next authoritative session.
        clearSelectedCopilotSessionId();
        clearActiveCopilotSessionState();
        resetAllCopilotThreads();
      }
    }
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function loadCopilotArtifacts(sessionId = getCopilotSessionId()) {
  try {
    const artifacts = await getJson<CopilotArtifact[]>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/artifacts`
    );
    reconcileCopilotArtifacts(sessionId, artifacts);
    lastError.set("");
    return artifacts;
  } catch (error) {
    setError(error);
    return [];
  }
}

export function selectCopilotArtifact(artifactId: string | null) {
  const selected = artifactId
    ? get(copilotArtifacts).find((artifact) => artifact.artifact_id === artifactId) ?? null
    : null;
  const sessionId = selected?.session_id ?? getSelectedCopilotSessionId();
  activeCopilotArtifact.set(selected);
  if (sessionId) {
    setCopilotArtifactId(sessionId, selected?.artifact_id ?? null);
  }
  copilotArtifactSaveState.set("idle");
  return selected;
}

export async function createCopilotArtifact(options: {
  artifactType: "memo" | "report";
  template: "concise_memo" | "research_report";
  title?: string | null;
  body?: string | null;
  sourceTurnIds?: string[];
  sourceMemoIds?: string[];
}) {
  const sessionId = getCopilotSessionId();
  try {
    const artifact = await postJson<CopilotArtifact>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/artifacts`,
      {
        artifact_type: options.artifactType,
        template: options.template,
        title: options.title ?? null,
        body: options.body ?? null,
        source_turn_ids: options.sourceTurnIds ?? [],
        source_memo_ids: options.sourceMemoIds ?? []
      }
    );
    const detail = await loadCopilotSession(sessionId);
    if (!detail) {
      const next = [...get(copilotArtifacts).filter((item) => item.artifact_id !== artifact.artifact_id), artifact];
      reconcileCopilotArtifacts(sessionId, next);
    }
    selectCopilotArtifact(artifact.artifact_id);
    lastError.set("");
    return artifact;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function updateCopilotArtifact(
  artifactId: string,
  options: { title?: string; body?: string; expectedUpdatedAt?: string | null }
) {
  copilotArtifactSaveState.set("saving");
  try {
    const artifact = await patchJson<CopilotArtifact>(
      `/copilot/artifacts/${encodeURIComponent(artifactId)}`,
      {
        title: options.title,
        body: options.body,
        expected_updated_at: options.expectedUpdatedAt ?? null
      }
    );
    copilotArtifacts.update((items) =>
      items.map((item) => (item.artifact_id === artifact.artifact_id ? artifact : item))
    );
    activeCopilotArtifact.set(artifact);
    activeCopilotSession.update((detail) =>
      detail
        ? {
            ...detail,
            artifacts: detail.artifacts.map((item) =>
              item.artifact_id === artifact.artifact_id ? artifact : item
            )
          }
        : detail
    );
    setCopilotArtifactId(artifact.session_id, artifact.artifact_id);
    copilotArtifactSaveState.set("saved");
    lastError.set("");
    return artifact;
  } catch (error) {
    const currentArtifact = get(activeCopilotArtifact);
    if (currentArtifact?.artifact_id === artifactId) {
      await loadCopilotSession(currentArtifact.session_id);
      selectCopilotArtifact(artifactId);
    }
    copilotArtifactSaveState.set("error");
    setError(error);
    return null;
  }
}

export async function duplicateCopilotArtifact(artifactId: string, title?: string | null) {
  try {
    const artifact = await postJson<CopilotArtifact>(
      `/copilot/artifacts/${encodeURIComponent(artifactId)}/duplicate`,
      { title: title ?? null }
    );
    const detail = await loadCopilotSession(artifact.session_id);
    if (!detail) {
      const next = [...get(copilotArtifacts), artifact];
      reconcileCopilotArtifacts(artifact.session_id, next);
    }
    selectCopilotArtifact(artifact.artifact_id);
    lastError.set("");
    return artifact;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function deleteCopilotArtifact(artifactId: string) {
  try {
    const artifact = get(copilotArtifacts).find((item) => item.artifact_id === artifactId) ?? null;
    const result = await deleteJson<CopilotDeleteResult>(
      `/copilot/artifacts/${encodeURIComponent(artifactId)}?confirm_artifact_id=${encodeURIComponent(artifactId)}`
    );
    const sessionId = artifact?.session_id ?? getCopilotSessionId();
    const remaining = get(copilotArtifacts).filter((item) => item.artifact_id !== artifactId);
    reconcileCopilotArtifacts(sessionId, remaining);
    activeCopilotSession.update((detail) =>
      detail ? { ...detail, artifacts: detail.artifacts.filter((item) => item.artifact_id !== artifactId) } : detail
    );
    lastError.set("");
    return result;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function exportCopilotArtifact(artifactId: string) {
  try {
    const markdown = await getText(`/copilot/artifacts/${encodeURIComponent(artifactId)}/export`);
    lastError.set("");
    return markdown;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function createCopilotMemo(options: {
  title?: string;
  notes?: string;
  sourceTurnIds?: string[];
} = {}) {
  setLoading("copilot", true);
  try {
    const memo = await postJson<CopilotMemo>("/copilot/memos", {
      session_id: getCopilotSessionId(),
      title: options.title,
      notes: options.notes,
      source_turn_ids: options.sourceTurnIds ?? []
    });
    await Promise.allSettled([loadCopilotMemos(getCopilotSessionId()), loadActiveCopilotSession(), loadCopilotSessions()]);
    lastError.set("");
    return memo;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("copilot", false);
  }
}

export async function archiveCopilotSession(sessionId: string) {
  try {
    const session = await postJson<CopilotSessionSummary>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/archive`,
      {}
    );
    copilotSessions.update((items) =>
      items.map((item) => (item.session_id === session.session_id ? session : item))
    );
    activeCopilotSession.update((detail) =>
      detail?.session.session_id === session.session_id ? { ...detail, session } : detail
    );
    lastError.set("");
    return session;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function updateCopilotMemo(memoId: string, options: { title?: string; body?: string }) {
  setLoading("copilot", true);
  try {
    const memo = await patchJson<CopilotMemo>(`/copilot/memos/${encodeURIComponent(memoId)}`, {
      title: options.title,
      body: options.body
    });
    await Promise.allSettled([loadCopilotMemos(getCopilotSessionId()), loadActiveCopilotSession(), loadCopilotSessions()]);
    lastError.set("");
    return memo;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("copilot", false);
  }
}

export async function exportCopilotMemo(memoId: string) {
  try {
    const markdown = await getText(`/copilot/memos/${encodeURIComponent(memoId)}/export`);
    lastError.set("");
    return markdown;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function generateCopilotResearchReport(options: {
  sessionId?: string | null;
  title?: string | null;
  notes?: string | null;
  sourceTurnIds?: string[];
  sourceMemoIds?: string[];
}) {
  setLoading("copilot", true);
  try {
    const sessionId = options.sessionId || getCopilotSessionId();
    const report = await postJson<CopilotResearchReport>(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/report`,
      {
        title: options.title,
        notes: options.notes,
        source_turn_ids: options.sourceTurnIds ?? [],
        source_memo_ids: options.sourceMemoIds ?? []
      }
    );
    lastError.set("");
    return report;
  } catch (error) {
    setError(error);
    return null;
  } finally {
    setLoading("copilot", false);
  }
}

export async function exportCopilotResearchReport(options: {
  sessionId?: string | null;
  title?: string | null;
  notes?: string | null;
  sourceTurnIds?: string[];
  sourceMemoIds?: string[];
}) {
  try {
    const sessionId = options.sessionId || getCopilotSessionId();
    const markdown = await postText(
      `/copilot/sessions/${encodeURIComponent(sessionId)}/report/export`,
      {
        title: options.title,
        notes: options.notes,
        source_turn_ids: options.sourceTurnIds ?? [],
        source_memo_ids: options.sourceMemoIds ?? []
      }
    );
    lastError.set("");
    return markdown;
  } catch (error) {
    setError(error);
    return null;
  }
}

export async function loadIvUnderlyingHistory(options: { symbol: string; lookbackDays?: number; forceRefresh?: boolean }) {
  const symbol = options.symbol.trim().toUpperCase();
  if (!symbol) {
    return null;
  }
  const current = get(ivUnderlyingHistory);
  if (current && current.symbol.trim().toUpperCase() !== symbol) {
    ivUnderlyingHistory.set(null);
  }
  const params = new URLSearchParams({
      symbol,
      lookback_days: String(options.lookbackDays ?? 252),
      force_refresh: options.forceRefresh ? "true" : "false"
  });
  const path = `/iv/underlying-history?${params.toString()}`;
  const key = stableQueryKey("/iv/underlying-history", {
    symbol,
    lookback_days: options.lookbackDays ?? 252
  });
  try {
    return await queryCache.query<IvUnderlyingHistoryResponse>({
      scope: "iv-underlying-history",
      key,
      staleTimeMs: 15 * 60_000,
      forceRefresh: options.forceRefresh,
      fetcher: (signal) => getJson<IvUnderlyingHistoryResponse>(path, { signal }),
      onData: (history) => ivUnderlyingHistory.set(history)
    });
  } catch (error) {
    if (isAbortError(error)) return null;
    if (!get(ivUnderlyingHistory)) ivUnderlyingHistory.set({
      symbol,
      lookback_days: options.lookbackDays ?? 252,
      points: [],
      source_provider: "unavailable",
      source_label: "Underlying history unavailable",
      origin: "gamma.iv.underlying_history",
      freshness_label: "unavailable",
      retrieved_at: new Date().toISOString(),
      warnings: [error instanceof Error ? error.message : "Underlying price history request failed."],
      transformation_note: null
    });
    return null;
  }
}

export async function loadIvSurface(options: IvLoadOptions | string = "SPY") {
  const request: IvLoadOptions =
    typeof options === "string"
      ? { symbol: options }
      : options;
  const requestedSymbol = request.symbol.trim().toUpperCase();
  setLoading("iv", true);
  try {
    const cachedHistorySymbol = String(get(ivUnderlyingHistory)?.symbol ?? "").trim().toUpperCase();
    if (requestedSymbol && cachedHistorySymbol !== requestedSymbol) {
      ivUnderlyingHistory.set(null);
    }
    const activeSession = get(ivSession);
    if (activeSession?.running) {
      const stoppedSession = await postJson<IvSessionStatus>("/iv/session/stop", {});
      ivSession.set(stoppedSession);
    }
    const params = new URLSearchParams({
      symbol: requestedSymbol || request.symbol
    });
    if (request.marketDataMode) {
      params.set("market_data_mode", request.marketDataMode);
    }
    if (request.waitSeconds != null) {
      params.set("wait_seconds", String(request.waitSeconds));
    }
    if (request.depthPreset) {
      params.set("depth_preset", request.depthPreset);
    }
    if (request.surfaceModel) {
      params.set("surface_model", request.surfaceModel);
    }
    const surface = await getJson<IvSurface>(`/iv/surface?${params.toString()}`);
    const shouldReplaceSurface = hasRenderableIvSurface(surface) || !hasRenderableIvSurface(get(ivSurface));
    if (shouldReplaceSurface || request.preserveExisting === false) {
      ivSurface.set(surface);
      ivSession.update((current) => (current == null ? current : { ...current, surface }));
      await loadIvUnderlyingHistory({ symbol: surface.symbol || requestedSymbol || request.symbol });
    } else {
      const message = surface.warnings[0] ?? surface.messages[0] ?? `No options surface snapshot available for ${request.symbol}.`;
      lastError.set(message);
    }
    resetCopilotCard("iv");
    if (hasRenderableIvSurface(surface)) {
      ivError.set("");
      lastError.set("");
    } else {
      const message = surface.warnings[0] ?? surface.messages[0] ?? `No options surface snapshot available for ${request.symbol}.`;
      ivError.set(message);
      lastError.set(message);
    }
  } catch (error) {
    ivError.set(errorMessage(error));
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
  const result = await runActionRequest<PortfolioHistoryClearResponse>(
    "/portfolio/history/clear",
    "portfolioAction",
    "[History]"
  );
  if (result?.success) {
    await loadPortfolioHistoryData();
    const snapshot = get(portfolioSnapshot);
    if (snapshot) {
      await loadPortfolioPerformanceData({ snapshot });
    }
  }
  return result;
}

export async function loadIvSession() {
  return requestCoordinator.run("iv-session", "status", async (signal) => {
    setLoading("ivSession", true);
    try {
      const session = await getJson<IvSessionStatus>("/iv/session", { signal });
      if (signal.aborted) return null;
      ivSession.set(session);
      const sessionHasSurface = hasRenderableIvSurface(session.surface);
      const sessionSymbol = String(sessionHasSurface ? session.surface?.symbol : "").trim().toUpperCase();
      let preservedExplicitSurface = false;
      ivSurface.update((current) => {
        if (!sessionHasSurface) return current;
        const currentHasSurface = hasRenderableIvSurface(current);
        const currentSymbol = String(currentHasSurface ? current?.symbol : "").trim().toUpperCase();
        preservedExplicitSurface = Boolean(
          currentSymbol && sessionSymbol && currentSymbol !== sessionSymbol
        );
        return preservedExplicitSurface ? current : session.surface;
      });
      const visibleSurface = get(ivSurface);
      const visibleSymbol = String(
        hasRenderableIvSurface(visibleSurface) ? visibleSurface?.symbol : sessionSymbol
      ).trim().toUpperCase();
      const currentHistory = get(ivUnderlyingHistory);
      const currentHistorySymbol = String(currentHistory?.symbol ?? "").trim().toUpperCase();
      if (
        sessionHasSurface &&
        !preservedExplicitSurface &&
        visibleSymbol &&
        (currentHistorySymbol !== visibleSymbol || !currentHistory?.points.length)
      ) {
        await loadIvUnderlyingHistory({ symbol: visibleSymbol });
      }
      if (signal.aborted) return null;
      if (sessionHasSurface) {
        ivError.set("");
        lastError.set("");
      }
      return session;
    } catch (error) {
      if (!isAbortError(error)) {
        ivError.set(errorMessage(error));
        setError(error);
      }
      return null;
    } finally {
      if (requestCoordinator.isCurrent("iv-session", signal)) setLoading("ivSession", false);
    }
  });
}

export function cancelIvSessionRequest() {
  requestCoordinator.cancel("iv-session");
}

export async function startIvSession(options: IvLoadOptions) {
  setLoading("ivSession", true);
  try {
    const session = await postJson<IvSessionStatus>("/iv/session/start", {
      symbol: options.symbol,
      market_data_mode: options.marketDataMode ?? null,
      depth_preset: options.depthPreset ?? null,
      surface_model: options.surfaceModel ?? null
    });
    ivSession.set(session);
    ivSurface.update((current) => (hasRenderableIvSurface(session.surface) ? session.surface : current));
    const sessionSymbol = session.surface?.symbol || session.active_symbol || options.symbol;
    if (sessionSymbol) {
      await loadIvUnderlyingHistory({ symbol: sessionSymbol });
    }
    resetCopilotCard("iv");
    ivError.set("");
    lastError.set("");
  } catch (error) {
    ivError.set(errorMessage(error));
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
    ivSurface.update((current) => (hasRenderableIvSurface(session.surface) ? session.surface : current));
    const sessionSymbol = session.surface?.symbol || session.active_symbol;
    if (sessionSymbol) {
      await loadIvUnderlyingHistory({ symbol: sessionSymbol });
    }
    resetCopilotCard("iv");
    ivError.set("");
    lastError.set("");
  } catch (error) {
    ivError.set(errorMessage(error));
    setError(error);
  } finally {
    setLoading("ivSession", false);
  }
}

async function runActionRequest<T extends ActionResponse = ActionResponse>(
  path: string,
  loadingKey: string,
  heading: string
) {
  setLoading(loadingKey, true);
  try {
    const result = await postJson<T>(path, {});
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
