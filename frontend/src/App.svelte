<script lang="ts">
  import { onMount } from "svelte";
  import CopilotResearchCard from "./components/CopilotResearchCard.svelte";
  import LandingPage from "./components/LandingPage.svelte";
  import Shell from "./components/Shell.svelte";
  import StatusRail from "./components/StatusRail.svelte";
  import TabBar, { type TabBarItem } from "./components/TabBar.svelte";
  import { installExternalLinkHandler } from "./lib/external-links";
  import { matchesActionKeybinding, isEditableEventTarget } from "./lib/keybindings";
  import { openKeyBindingsWindow } from "./lib/keybindings-window";
  import {
    getModeByShortcutIndex,
    getOrderedWorkspaceTabs,
    getTabModes,
    getTabByShortcutIndex,
    getWorkspaceHomeTab,
    isWorkspaceTab,
    type NavigationRouteMatch,
  } from "./lib/navigation";
  import { buildIvRequestFromResearch, buildRiskRequestFromResearch } from "./lib/workspace";
  import { createRiskHandoffController } from "./lib/risk-handoff";
  import { createAdaptivePoller, type AdaptivePoller } from "./lib/adaptive-poller";
  import { hydrateActiveWorkspace } from "./lib/shell/bootstrap";
  import { markStartupBegin, markStartupUsable } from "./lib/request-metrics";
  import {
    loadPersistedWorkspaceState,
    persistedMode,
    persistWorkspaceState
  } from "./lib/shell/workspace-state";
  import {
    activeTab,
    analyzeStrategyLab,
    acceptResolvedStrategyLabHandoff,
    composeStrategyLab,
    composeStrategyLabPortfolio,
    validateStrategyLabPortfolio,
    reviveStrategyLabHandoff,
    clearStaleStrategyLabHandoffs,
    diagnostics,
    diagnosticsLog,
    clearPortfolioHistory,
    cancelIvSessionRequest,
    commoditiesWorkspace,
    activeCopilotSession,
    copilotActionDefinitions,
    copilotOperatorPlan,
    copilotOperatorResult,
    copilotResearchPlan,
    copilotSessions,
    copilotThreads,
    archiveCopilotSession,
    cryptoComparison,
    fundamentalsDcfSnapshots,
    fundamentalsDcfModel,
    fundamentalsFinancials,
    fundamentalsOverview,
    fundamentalsPeers,
    fundamentalsReference,
    fundamentalsReverseValuation,
    fundamentalsSearch,
    fundamentalsSearchState,
    cryptoFlowSummary,
    cryptoLiquidity,
    cryptoPriceHistory,
    cryptoSyntheticPortfolio,
    cryptoTokenDetail,
    cryptoWorkspace,
    clearCryptoSyntheticPortfolio,
    computeRisk,
    forceAccountSubscribe,
    ivSurface,
    ivError,
    ivUnderlyingHistory,
    ivSession,
    lastError,
    loadDiagnostics,
    loadProviderUsage,
    loadIvSession,
    loadIvSurface,
    stopIvSession,
    loadFundamentalsSearch,
    loadResearchOverview,
    loadSitrepIndicesOverview,
    loadSitrepWorkspace,
    loadSitrepFollowUps,
    toggleSitrepFollowUpItem,
    updateSitrepFollowUpItem,
    dismissSitrepFollowUpItem,
    sitrepFollowUps,
    sitrepWorkspaceMeta,
    loadSavedResearch,
    macroContext,
    loadMacroSeriesHistory,
    loadMacroWorkspace,
    loadCommoditiesWorkspace,
    loadMaritimeWorkspace,
    loadNewsFeed,
    loadPortfolioPerformance,
    loading,
    loadPortfolioSnapshot,
    loadActiveCopilotSession,
    loadCopilotMemos,
    loadCopilotActionDefinitions,
    loadCopilotOperatorPlan,
    loadCopilotResearchCard,
    loadCopilotResearchPlan,
    loadCopilotSession,
    loadCopilotSessions,
    executeCopilotOperatorPlan,
    macroDivergences,
    macroEvents,
    macroSeriesHistories,
    macroSnapshot,
    maritimeWorkspace,
    newsFeed,
    portfolioHistory,
    portfolioPerformance,
    portfolioSnapshot,
    providerUsage,
    requestMetrics,
    predictionMarketCalibration,
    predictionMarketDetail,
    predictionMarketHistory,
    predictionMarketRelated,
    predictionMarketScreener,
    predictionMarketWallet,
    refreshSystemStatus,
    researchOverview,
    sitrepIndicesOverview,
    researchDraft,
    researchCompareResult,
    researchResult,
    strategyLabComposition,
    strategyLabResearchBook,
    riskResult,
    riskWorkspaceBasis,
    setRiskWorkspaceMode,
    loadPredictionMarketScreener,
    loadCryptoWorkspace,
    previewCopilotContextFingerprint,
    previewCopilotThreadFingerprint,
    runCryptoSyntheticPortfolio,
    runDiagnosticsAction,
    compareResearch,
    restoreStrategyLabResult,
    runResearch,
    saveResearchItem,
    deleteSavedResearchItem,
    clearStrategyLabHandoffs,
    dismissStrategyLabHandoff,
    enqueueAndOpenStrategyLab,
    enqueueStrategyLabHandoff,
    saveFundamentalsDcfModel,
    saveFundamentalsDcfSnapshot,
    saveFundamentalsPeerBasket,
    savedResearchItems,
    selectedFundamentalsTicker,
    sharedEquitySelection,
    selectCryptoToken,
    selectFundamentalsCompany,
    loadFundamentalsDcfSnapshot,
    selectPredictionMarket,
    setResearchDraft,
    setSharedEquitySelection,
    clearSharedEquitySelection,
    clearPortfolioSnapshot,
    setBaseCurrency,
    setMarketDataMode,
    resolvePendingStrategyLabHandoffs,
    strategyLabHandoffQueue,
    strategyLabResult,
    systemStatus,
    toggleConnection,
    startNewCopilotSession
  } from "./lib/stores/app";
  import {
    reorderWorkspaceTab,
    resetWorkspaceTabOrder,
    restoreWorkspaceTabOrders,
    workspaceTabOrders,
  } from "./lib/stores/navigation";
  import type {
    CopilotBaseDomain,
    CopilotDomain,
    CopilotReasoningEffort,
    CopilotThreadState,
    CrossTabHandoffEnvelope,
    CommodityMode,
    CommodityWorkspaceResponse,
    CryptoComparison,
    CryptoDexLiquiditySummary,
    CryptoFlowSummary,
    CryptoPriceHistoryResponse,
    CryptoSyntheticPortfolio,
    CryptoToken,
    CryptoWorkspaceResponse,
    FundamentalsDcfModel,
    FundamentalsDcfSnapshotList,
    FundamentalsFinancials,
    FundamentalsOverview,
    FundamentalsPeers,
    FundamentalsReference,
    FundamentalsReverseValuation,
    FundamentalsSearchResponse,
    IvSessionStatus,
    IvSurface,
    MacroContextState,
    MacroSnapshot,
    MaritimeMode,
    PortfolioPerformanceResponse,
    PortfolioSnapshot,
    PredictionMarket,
    ResearchResult,
    RiskResult,
    StrategyLabHandoffEnvelope,
    StrategyLabHandoffQueueItem,
    SystemStatus,
    TabId,
    WorkspaceMode
  } from "./lib/api/types";
  import type { CryptoMode } from "./lib/view-models/crypto";
  import type { FundamentalsMode } from "./lib/view-models/fundamentals";
  import type { SitrepHandoffRequest } from "./lib/view-models/sitrep";
  import type { OptionsMode } from "./lib/view-models/iv";
  import type { EquityResearchMode, StrategyLabMode } from "./lib/view-models/research";
  import type { RiskMode } from "./lib/risk-workspace";

  type LazyViewComponent = any;
  type LazyViewModule = { default: LazyViewComponent };
  type LazyViewLoader = () => Promise<LazyViewModule>;

  const viewLoaders: Record<TabId, LazyViewLoader> = {
    portfolio: () => import("./views/PortfolioView.svelte"),
    sitrep: () => import("./views/SitrepView.svelte"),
    equity_research: () => import("./views/EquityResearchView.svelte"),
    strategy_lab: () => import("./views/StrategyLabView.svelte"),
    macro: () => import("./views/MacroView.svelte"),
    commodities: () => import("./views/CommoditiesView.svelte"),
    prediction_markets: () => import("./views/PredictionMarketsView.svelte"),
    crypto: () => import("./views/CryptoView.svelte"),
    fundamentals: () => import("./views/FundamentalsView.svelte"),
    maritime: () => import("./views/MaritimeView.svelte"),
    copilot: () => import("./views/CopilotView.svelte"),
    risk: () => import("./views/RiskView.svelte"),
    iv: () => import("./views/IvView.svelte"),
  };

  type ConsoleEntry = {
    label: string;
    message: string;
    tone: "info" | "warning" | "error" | "action";
  };

  const restoredWorkspaceState = loadPersistedWorkspaceState();

  let systemStatusPoller: AdaptivePoller | null = null;
  let providerUsagePoller: AdaptivePoller | null = null;
  let ivSessionPoller: AdaptivePoller | null = null;
  let workspaceMode: WorkspaceMode | null = restoredWorkspaceState?.workspaceMode ?? null;
  let navigationSearchResetToken = 0;
  let ivRequestedSymbol = "";
  let ivPollingActive = false;
  let equityResearchMode: EquityResearchMode = persistedMode(restoredWorkspaceState, "equity_research", "overview");
  let strategyLabMode: StrategyLabMode = persistedMode(restoredWorkspaceState, "strategy_lab", "composer");
  let cryptoMode: CryptoMode = persistedMode(restoredWorkspaceState, "crypto", "overview");
  let fundamentalsMode: FundamentalsMode = persistedMode(restoredWorkspaceState, "fundamentals", "overview");
  let commoditiesMode: CommodityMode = persistedMode(restoredWorkspaceState, "commodities", "overview");
  let maritimeMode: MaritimeMode = persistedMode(restoredWorkspaceState, "maritime", "live_map");
  let optionsMode: OptionsMode = persistedMode(restoredWorkspaceState, "iv", "overview");
  let riskMode: RiskMode = persistedMode(restoredWorkspaceState, "risk", "overview");
  let copilotContextTab: TabId = "sitrep";
  let consoleEntries: ConsoleEntry[] = [];
  let diagnosticsOpen = false;
  let sidebarOpen = false;
  let copilotOpen = false;
  let selectedSynthesisDomains: CopilotBaseDomain[] = [];
  let lastDefaultCopilotDomain: CopilotBaseDomain | null | undefined = undefined;
  let latestCopilotHandoff: CrossTabHandoffEnvelope | null = null;
  let settingsOpen = false;
  let orderedTabs: ReturnType<typeof getOrderedWorkspaceTabs> = [];
  let tabBarTabs: TabBarItem[] = [];
  let synthesisScopeOptions: CopilotGroundingScopeOption[] = [];
  let activeTabCopilotSurface: CopilotSurfaceState;
  let synthesisCopilotSurface: CopilotSurfaceState;
  let copilotSurface: CopilotSurfaceState;
  let activeViewTab: TabId | null = null;
  let activeViewComponent: LazyViewComponent | null = null;
  let activeViewLoading: TabId | null = null;
  let activeViewLoadError: string | null = null;
  let activeViewLoadSequence = 0;
  let riskHandoffRunning = false;
  const loadedViewComponents: Partial<Record<TabId, LazyViewComponent>> = {};

  if (restoredWorkspaceState) {
    activeTab.set(restoredWorkspaceState.activeTab || getWorkspaceHomeTab(restoredWorkspaceState.workspaceMode));
  }

  function normalizeAppTabId(tabId: TabId | "research"): TabId {
    return tabId === "research" ? "equity_research" : tabId;
  }

  $: orderedTabs =
    workspaceMode == null
      ? []
      : getOrderedWorkspaceTabs(workspaceMode, $workspaceTabOrders);
  $: tabBarTabs = orderedTabs.map<TabBarItem>((tab) => ({
    id: tab.id,
    label: tab.label,
    pinned: tab.pinned,
  }));
  $: synthesisScopeOptions = buildSynthesisScopeOptions({
    activeTab: $activeTab,
    workspaceMode,
    system: $systemStatus,
    portfolio: $portfolioSnapshot,
    portfolioPerformance: $portfolioPerformance,
    overview: $researchOverview,
    research: $researchResult,
    strategy: $strategyLabResult,
    strategyComposition: $strategyLabComposition,
    compareResult: $researchCompareResult,
    strategyLabHandoffs: $strategyLabHandoffQueue,
    macro: $macroContext,
    macroSnapshot: $macroSnapshot,
    commodities: $commoditiesWorkspace,
    prediction: $predictionMarketDetail,
    crypto: $cryptoTokenDetail,
    fundamentals: $fundamentalsOverview,
    risk: $riskResult,
    riskWorkspace: $riskWorkspaceBasis,
    ivSurface: $ivSurface,
    ivSession: $ivSession,
  });
  $: {
    const availableDomains = synthesisScopeOptions
      .filter((option) => option.supported && option.domain != null)
      .map((option) => option.domain as CopilotBaseDomain);
    const activeDefaultDomain = resolveDefaultCopilotDomain(
      $activeTab === "copilot" ? copilotContextTab : $activeTab,
      synthesisScopeOptions
    );
    const filteredSelection = selectedSynthesisDomains.filter((domain) =>
      availableDomains.includes(domain)
    );
    const nextSelection =
      activeDefaultDomain !== lastDefaultCopilotDomain
        ? activeDefaultDomain
          ? [activeDefaultDomain]
          : []
        : filteredSelection;
    const changed =
      activeDefaultDomain !== lastDefaultCopilotDomain ||
      nextSelection.length !== selectedSynthesisDomains.length ||
      nextSelection.some((domain, index) => domain !== selectedSynthesisDomains[index]);
    if (changed) {
      selectedSynthesisDomains = nextSelection;
      lastDefaultCopilotDomain = activeDefaultDomain;
    }
  }
  $: activeTabCopilotSurface = buildActiveTabCopilotSurface({
    tab: $activeTab === "copilot" ? copilotContextTab : $activeTab,
    workspaceMode,
    threads: $copilotThreads,
    system: $systemStatus,
    portfolio: $portfolioSnapshot,
    portfolioPerformance: $portfolioPerformance,
    overview: $researchOverview,
    research: $researchResult,
    strategy: $strategyLabResult,
    strategyComposition: $strategyLabComposition,
    compareResult: $researchCompareResult,
    strategyLabHandoffs: $strategyLabHandoffQueue,
    risk: $riskResult,
    riskWorkspace: $riskWorkspaceBasis,
    ivSurface: $ivSurface,
    ivSession: $ivSession,
    macro: $macroContext,
    commodities: $commoditiesWorkspace,
    prediction: $predictionMarketDetail,
    crypto: $cryptoTokenDetail,
    fundamentals: $fundamentalsOverview,
    fundamentalsTicker: $selectedFundamentalsTicker,
  });
  $: setRiskWorkspaceMode(riskMode);
  $: persistWorkspaceState(
    workspaceMode == null
      ? null
      : {
          workspaceMode,
          activeTab: isWorkspaceTab(workspaceMode, $activeTab) ? $activeTab : getWorkspaceHomeTab(workspaceMode),
          modes: {
            equity_research: equityResearchMode,
            strategy_lab: strategyLabMode,
            macro: $macroContext.mode,
            crypto: cryptoMode,
            fundamentals: fundamentalsMode,
            commodities: commoditiesMode,
            maritime: maritimeMode,
            iv: optionsMode,
            risk: riskMode
          }
        }
  );
  $: synthesisCopilotSurface = buildSynthesisCopilotSurface({
    activeTab: $activeTab,
    workspaceMode,
    threads: $copilotThreads,
    scopeOptions: synthesisScopeOptions,
    selectedDomains: selectedSynthesisDomains,
  });
  $: copilotSurface = synthesisCopilotSurface;
  $: if (workspaceMode != null && activeViewTab !== $activeTab) {
    void loadActiveView($activeTab);
  }

  type CopilotGroundingScopeOption = {
    tabId: TabId;
    domain: CopilotBaseDomain | null;
    label: string;
    contextLabel: string;
    fingerprintLabel: string;
    freshnessLabel: string | null;
    warningLabel: string | null;
    supported: boolean;
    disabledReason: string | null;
  };
  type CopilotSurfaceState = {
    supported: boolean;
    domain: CopilotDomain | null;
    triggerLabel: string;
    contextLabel: string;
    domainLabel: string;
    guidance: string;
    placeholder: string;
    thread: CopilotThreadState | null;
    scopeOptions: CopilotGroundingScopeOption[];
    selectedScopeDomains: CopilotBaseDomain[];
    selectionMessage: string | null;
  };

  async function loadActiveView(tabId: TabId) {
    const sequence = ++activeViewLoadSequence;
    const cachedView = loadedViewComponents[tabId] ?? null;
    activeViewTab = tabId;
    activeViewLoadError = null;

    if (cachedView) {
      activeViewComponent = cachedView;
      activeViewLoading = null;
      return;
    }

    activeViewComponent = null;
    activeViewLoading = tabId;

    try {
      const module = await viewLoaders[tabId]();
      loadedViewComponents[tabId] = module.default;
      if (sequence === activeViewLoadSequence) {
        activeViewComponent = module.default;
        activeViewLoading = null;
      }
    } catch (error) {
      if (sequence === activeViewLoadSequence) {
        activeViewLoadError = error instanceof Error ? error.message : String(error);
        activeViewLoading = null;
      }
    }
  }

  async function loadSitrepContext(options: { forceRefresh?: boolean } = {}) {
    // The backend-owned /sitrep/workspace contract composes all six sections
    // server-side; the store fans them out into the per-domain stores.
    await Promise.allSettled([
      loadSitrepWorkspace({ forceRefresh: options.forceRefresh }),
      loadSitrepFollowUps(),
    ]);
  }

  const macroModeLabels: Record<MacroContextState["mode"], string> = {
    snapshot: "Snapshot",
    cross_asset: "Cross-Asset",
    rates_policy: "Rates & Policy",
    events_regimes: "Events / Regimes",
    trade_partners: "Trade Partners",
    country_compare: "Country Compare",
  };

  function describeMacroCopilotContext(context: MacroContextState) {
    return `Macro | ${context.region} | ${context.timeframe} | ${macroModeLabels[context.mode]}`;
  }

  function describeCommoditiesCopilotContext(workspace: CommodityWorkspaceResponse | null) {
    if (!workspace) {
      return "Commodities | Load workspace to ground the Copilot";
    }
    const selected = workspace.market_summaries.find(
      (summary) => summary.instrument.instrument_id === workspace.selected_instrument_id
    );
    const provider = workspace.coverage.provider_label || workspace.coverage.provider_id || "Provider";
    return `Commodities | ${selected?.instrument.name ?? workspace.selected_instrument_id} | ${provider}`;
  }

  function describePortfolioCopilotContext(
    snapshot: PortfolioSnapshot | null,
    performance: PortfolioPerformanceResponse | null,
    system: SystemStatus | null
  ) {
    if (!snapshot) {
      return "Portfolio | Load a portfolio snapshot to ground the Copilot";
    }
    const baseCurrency = snapshot.base_currency || system?.base_currency || "Base";
    const liquidity =
      snapshot.net_liquidation == null
        ? "No net liq"
        : `${snapshot.net_liquidation.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${baseCurrency}`;
    const benchmark = performance?.benchmark_symbol ? ` | ${performance.benchmark_symbol}` : "";
    return `Portfolio | ${liquidity}${benchmark}`;
  }

  function describeResearchCopilotContext(result: ResearchResult | null) {
    if (!result) {
      return "Research | Run analysis to ground the Copilot";
    }
    if (result.scope_type === "single_ticker") {
      return `Research | Single Ticker | ${result.primary_symbol ?? "Unknown"}`;
    }
    return `Research | Synthetic Portfolio | ${result.weights.length} symbols`;
  }

  function describePredictionCopilotContext(detail: PredictionMarket | null) {
    if (!detail) {
      return "Prediction Markets | Select a contract to ground the Copilot";
    }
    return `Prediction Markets | ${detail.venue} | ${detail.title}`;
  }

  function describeCryptoCopilotContext(detail: CryptoToken | null) {
    if (!detail) {
      return "Crypto | Select a token to ground the Copilot";
    }
    const chain = detail.chain ?? detail.asset_platform_id ?? "Unknown chain";
    return `Crypto | ${detail.name} | ${chain}`;
  }

  function describeFundamentalsCopilotContext(
    detail: FundamentalsOverview | null,
    ticker: string | null
  ) {
    if (!detail) {
      return `Fundamentals | ${ticker ?? "Load a company"} to ground the Copilot`;
    }
    const latestPeriod = detail.company.latest_report_period
      ? new Date(detail.company.latest_report_period).getFullYear()
      : "latest";
    return `Fundamentals | ${detail.company.ticker} | FY ${latestPeriod}`;
  }

  function describeRiskCopilotContext(result: RiskResult | null, mode: "portfolio" | "research" | "research_book" | null) {
    if (!result) {
      return "Risk | Run a risk pass to ground the Copilot";
    }
    const coverage = result.metrics.risk_coverage_ratio;
    const coverageLabel =
      coverage == null ? "coverage unknown" : `${(coverage * 100).toFixed(1)}% coverage`;
    const sourceLabel =
      result.source_label ?? (mode === "research_book" ? "Strategy Lab book" : mode === "research" ? "Research" : "Portfolio");
    return `Risk | ${sourceLabel} | ${coverageLabel}`;
  }

  function resolveIvCopilotSurface(
    surface: IvSurface | null,
    session: IvSessionStatus | null
  ) {
    if (surface && (surface.snapshot_available || surface.points > 0 || surface.expiries.length > 0)) {
      return surface;
    }
    const sessionSurface = session?.surface ?? null;
    if (sessionSurface && (sessionSurface.snapshot_available || sessionSurface.points > 0 || sessionSurface.expiries.length > 0)) {
      return sessionSurface;
    }
    return surface ?? sessionSurface;
  }

  function describeIvCopilotContext(
    surface: IvSurface | null,
    session: IvSessionStatus | null
  ) {
    const activeSurface = resolveIvCopilotSurface(surface, session);
    if (!activeSurface || (!activeSurface.snapshot_available && activeSurface.points === 0)) {
      return "Options | Load a surface snapshot to ground the Copilot";
    }
    return `Options | ${activeSurface.symbol} | ${activeSurface.expiries.length} expiries x ${activeSurface.strikes.length} strikes`;
  }

  function formatShortTimestamp(timestamp: string | null | undefined) {
    if (!timestamp) {
      return null;
    }
    const normalized = timestamp.replace("T", " ").replace("Z", "");
    return normalized.slice(0, 16);
  }

  function formatWarningLabel(count: number) {
    if (count <= 0) {
      return null;
    }
    return count === 1 ? "1 warning" : `${count} warnings`;
  }

  function shortFingerprint(value: string) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return `FP ${(hash >>> 0).toString(16).padStart(8, "0")}`;
  }

  const COPILOT_CONTEXT_DEFINITIONS: Array<{
    tabId: TabId;
    domain: CopilotBaseDomain | null;
    label: string;
    unavailableLabel: string;
  }> = [
    { tabId: "portfolio", domain: "portfolio", label: "Portfolio", unavailableLabel: "Load a portfolio snapshot" },
    { tabId: "sitrep", domain: null, label: "SITREP", unavailableLabel: "SITREP is not a standalone Copilot context" },
    { tabId: "equity_research", domain: "equity_research", label: "Equity Research", unavailableLabel: "Load Equity Research overview or run Scope Analysis" },
    { tabId: "strategy_lab", domain: "strategy_lab", label: "Strategy Lab", unavailableLabel: "Run a Strategy Lab import, composition, or comparison" },
    { tabId: "macro", domain: "macro", label: "Macro", unavailableLabel: "Load the Macro workspace" },
    { tabId: "prediction_markets", domain: "prediction_markets", label: "Prediction Markets", unavailableLabel: "Select and load a prediction market" },
    { tabId: "crypto", domain: "crypto", label: "Crypto", unavailableLabel: "Select and load a crypto token" },
    { tabId: "fundamentals", domain: "fundamentals", label: "Fundamentals", unavailableLabel: "Select and load a Fundamentals company" },
    { tabId: "commodities", domain: "commodities", label: "Commodities", unavailableLabel: "Load the Commodities workspace" },
    { tabId: "maritime", domain: null, label: "Sealanes", unavailableLabel: "Sealanes Copilot grounding is not implemented yet" },
    { tabId: "risk", domain: "risk", label: "Risk", unavailableLabel: "Run a Risk computation" },
    { tabId: "iv", domain: "iv", label: "Options", unavailableLabel: "Load an options surface" },
  ];

  function contextDefinitionForDomain(domain: CopilotBaseDomain) {
    return COPILOT_CONTEXT_DEFINITIONS.find((definition) => definition.domain === domain);
  }

  function resolveDefaultCopilotDomain(
    tabId: TabId,
    options: CopilotGroundingScopeOption[]
  ): CopilotBaseDomain | null {
    const match = options.find((option) => option.tabId === tabId && option.supported && option.domain != null);
    return match?.domain ?? null;
  }

  function buildSynthesisScopeOptions({
    activeTab,
    workspaceMode,
    system,
    portfolio,
    portfolioPerformance,
    overview,
    research,
    strategy,
    strategyComposition,
    compareResult,
    strategyLabHandoffs,
    macro,
    macroSnapshot,
    commodities,
    prediction,
    crypto,
    fundamentals,
    risk,
    riskWorkspace,
    ivSurface,
    ivSession,
  }: {
    activeTab: TabId;
    workspaceMode: WorkspaceMode | null;
    system: SystemStatus | null;
    portfolio: PortfolioSnapshot | null;
    portfolioPerformance: PortfolioPerformanceResponse | null;
    overview: typeof $researchOverview;
    research: ResearchResult | null;
    strategy: typeof $strategyLabResult;
    strategyComposition: typeof $strategyLabComposition;
    compareResult: typeof $researchCompareResult;
    strategyLabHandoffs: StrategyLabHandoffQueueItem[];
    macro: MacroContextState;
    macroSnapshot: MacroSnapshot | null;
    commodities: CommodityWorkspaceResponse | null;
    prediction: PredictionMarket | null;
    crypto: CryptoToken | null;
    fundamentals: FundamentalsOverview | null;
    risk: RiskResult | null;
    riskWorkspace: "portfolio" | "research" | "research_book" | null;
    ivSurface: IvSurface | null;
    ivSession: IvSessionStatus | null;
  }): CopilotGroundingScopeOption[] {
    const options: CopilotGroundingScopeOption[] = [];
    const pushedDomains = new Set<CopilotBaseDomain>();
    const pushOption = (
      domain: CopilotBaseDomain,
      contextLabel: string,
      freshnessLabel: string | null,
      warningLabel: string | null
    ) => {
      const fingerprint = previewCopilotContextFingerprint(domain, { workspaceMode });
      const definition = contextDefinitionForDomain(domain);
      pushedDomains.add(domain);
      options.push({
        tabId: definition?.tabId ?? activeTab,
        domain,
        label: definition?.label ?? domain.charAt(0).toUpperCase() + domain.slice(1),
        contextLabel,
        fingerprintLabel: shortFingerprint(fingerprint),
        freshnessLabel,
        warningLabel,
        supported: true,
        disabledReason: null
      });
    };

    if (portfolio) {
      pushOption(
        "portfolio",
        describePortfolioCopilotContext(portfolio, portfolioPerformance, system),
        formatShortTimestamp(portfolio.timestamp)
          ? `Snapshot ${formatShortTimestamp(portfolio.timestamp)}`
          : null,
        formatWarningLabel(
          portfolio.warnings.length + (portfolioPerformance?.warnings.length ?? 0)
        )
      );
    }

    if (research) {
      const researchTimestamp =
        research.snapshot?.timestamp ??
        research.performance_points[research.performance_points.length - 1]?.timestamp ??
        null;
      pushOption(
        "research",
        describeResearchCopilotContext(research),
        formatShortTimestamp(researchTimestamp)
          ? `Result ${formatShortTimestamp(researchTimestamp)}`
          : null,
        formatWarningLabel(research.warnings.length)
      );
    }

    if (overview || research) {
      const overviewTimestamp = overview?.retrieved_at ?? null;
      const researchTimestamp =
        research?.snapshot?.timestamp ??
        research?.performance_points[research.performance_points.length - 1]?.timestamp ??
        null;
      pushOption(
        "equity_research",
        research ? describeResearchCopilotContext(research) : (overview?.universe_label ?? "Equity overview"),
        formatShortTimestamp(researchTimestamp ?? overviewTimestamp)
          ? `Context ${formatShortTimestamp(researchTimestamp ?? overviewTimestamp)}`
          : null,
        formatWarningLabel((research?.warnings.length ?? 0) + (overview?.warnings.length ?? 0))
      );
    }

    const currentStrategyLabHandoffs = strategyLabHandoffs.filter((item) => !item.stale);
    if (strategy || strategyComposition || compareResult || currentStrategyLabHandoffs.length) {
      const strategyWarnings =
        (strategyComposition?.warnings.length ?? 0) +
        (strategy?.warnings.length ?? 0) +
        (compareResult?.warnings.length ?? 0) +
        currentStrategyLabHandoffs.reduce(
          (count, item) => count + item.handoff.warnings.length + (item.resolved?.warnings.length ?? 0) + (item.error ? 1 : 0),
          0
        );
      pushOption(
        "strategy_lab",
        strategyComposition?.name ??
          strategy?.name ??
          (compareResult
            ? `${compareResult.left.label} vs ${compareResult.right.label}`
            : currentStrategyLabHandoffs.length
              ? `${currentStrategyLabHandoffs.length} Strategy Lab handoff${currentStrategyLabHandoffs.length === 1 ? "" : "s"}`
              : "Strategy Lab"),
        formatShortTimestamp(strategyComposition?.retrieved_at ?? strategy?.retrieved_at ?? null)
          ? `Result ${formatShortTimestamp(strategyComposition?.retrieved_at ?? strategy?.retrieved_at ?? null)}`
          : currentStrategyLabHandoffs.length
            ? `${currentStrategyLabHandoffs.filter((item) => item.status === "resolved").length} resolved / ${currentStrategyLabHandoffs.filter((item) => item.status === "pending" || item.status === "resolving").length} pending`
          : null,
        formatWarningLabel(strategyWarnings)
      );
    }

    if (macroSnapshot) {
      pushOption(
        "macro",
        describeMacroCopilotContext(macro),
        formatShortTimestamp(macroSnapshot.retrieved_at)
          ? `Snapshot ${formatShortTimestamp(macroSnapshot.retrieved_at)}`
          : null,
        formatWarningLabel(macroSnapshot.warnings.length)
      );
    }

    if (commodities) {
      pushOption(
        "commodities",
        describeCommoditiesCopilotContext(commodities),
        formatShortTimestamp(commodities.coverage.source_timestamp ?? commodities.retrieved_at)
          ? `Data ${formatShortTimestamp(commodities.coverage.source_timestamp ?? commodities.retrieved_at)}`
          : commodities.coverage.freshness_label
            ? `Freshness ${commodities.coverage.freshness_label}`
            : null,
        formatWarningLabel(commodities.warnings.length + commodities.coverage.caveats.length)
      );
    }

    if (prediction) {
      pushOption(
        "prediction_markets",
        describePredictionCopilotContext(prediction),
        prediction.freshness?.status
          ? `Freshness ${prediction.freshness.status}`
          : formatShortTimestamp(prediction.retrieved_at)
            ? `Market ${formatShortTimestamp(prediction.retrieved_at)}`
            : null,
        prediction.freshness?.is_stale || prediction.freshness?.is_broken
          ? "Freshness warning"
          : null
      );
    }

    if (crypto) {
      pushOption(
        "crypto",
        describeCryptoCopilotContext(crypto),
        formatShortTimestamp(crypto.retrieved_at)
          ? `Token ${formatShortTimestamp(crypto.retrieved_at)}`
          : null,
        null
      );
    }

    if (fundamentals) {
      pushOption(
        "fundamentals",
        describeFundamentalsCopilotContext(fundamentals, fundamentals.company.ticker),
        formatShortTimestamp(fundamentals.company.retrieved_at)
          ? `Company ${formatShortTimestamp(fundamentals.company.retrieved_at)}`
          : null,
        formatWarningLabel(fundamentals.warnings.length)
      );
    }

    if (risk) {
      pushOption(
        "risk",
        describeRiskCopilotContext(risk, riskWorkspace ?? workspaceMode),
        null,
        formatWarningLabel(risk.warnings.length)
      );
    }

    const activeIvSurface = resolveIvCopilotSurface(ivSurface, ivSession);
    if (
      activeIvSurface &&
      (activeIvSurface.snapshot_available ||
        activeIvSurface.points > 0 ||
        activeIvSurface.expiries.length > 0)
    ) {
      pushOption(
        "iv",
        describeIvCopilotContext(ivSurface, ivSession),
        formatShortTimestamp(activeIvSurface.timestamp)
          ? `${activeIvSurface.delayed ? "Delayed" : "Surface"} ${formatShortTimestamp(activeIvSurface.timestamp)}`
          : activeIvSurface.delayed
            ? "Delayed surface"
            : null,
        formatWarningLabel(activeIvSurface.warnings.length + (ivSession?.messages.length ?? 0))
      );
    }

    for (const definition of COPILOT_CONTEXT_DEFINITIONS) {
      if (definition.domain != null && pushedDomains.has(definition.domain)) {
        continue;
      }
      options.push({
        tabId: definition.tabId,
        domain: definition.domain,
        label: definition.label,
        contextLabel: definition.unavailableLabel,
        fingerprintLabel: "UNAVAILABLE",
        freshnessLabel: null,
        warningLabel: definition.domain == null ? "Not wired" : "Context required",
        supported: false,
        disabledReason: definition.unavailableLabel
      });
    }

    return [...options].sort((left, right) => {
      if (left.tabId === activeTab) {
        return -1;
      }
      if (right.tabId === activeTab) {
        return 1;
      }
      const leftIndex = COPILOT_CONTEXT_DEFINITIONS.findIndex((definition) => definition.tabId === left.tabId);
      const rightIndex = COPILOT_CONTEXT_DEFINITIONS.findIndex((definition) => definition.tabId === right.tabId);
      return leftIndex - rightIndex;
    });
  }

  function buildActiveTabCopilotSurface({
    tab,
    workspaceMode,
    threads,
    system,
    portfolio,
    portfolioPerformance,
    overview,
    research,
    strategy,
    strategyComposition,
    compareResult,
    strategyLabHandoffs,
    risk,
    riskWorkspace,
    ivSurface,
    ivSession,
    macro,
    commodities,
    prediction,
    crypto,
    fundamentals,
    fundamentalsTicker,
  }: {
    tab: TabId;
    workspaceMode: WorkspaceMode | null;
    threads: Record<CopilotDomain, CopilotThreadState>;
    system: SystemStatus | null;
    portfolio: PortfolioSnapshot | null;
    portfolioPerformance: PortfolioPerformanceResponse | null;
    overview: typeof $researchOverview;
    research: ResearchResult | null;
    strategy: typeof $strategyLabResult;
    strategyComposition: typeof $strategyLabComposition;
    compareResult: typeof $researchCompareResult;
    strategyLabHandoffs: StrategyLabHandoffQueueItem[];
    risk: RiskResult | null;
    riskWorkspace: "portfolio" | "research" | "research_book" | null;
    ivSurface: IvSurface | null;
    ivSession: IvSessionStatus | null;
    macro: MacroContextState;
    commodities: CommodityWorkspaceResponse | null;
    prediction: PredictionMarket | null;
    crypto: CryptoToken | null;
    fundamentals: FundamentalsOverview | null;
    fundamentalsTicker: string | null;
  }): CopilotSurfaceState {
    if (tab === "portfolio") {
      return {
        supported: portfolio != null,
        domain: "portfolio",
        triggerLabel: portfolio ? "Portfolio context" : "Load portfolio",
        contextLabel: describePortfolioCopilotContext(portfolio, portfolioPerformance, system),
        domainLabel: "Portfolio",
        guidance:
          portfolio != null
            ? "Grounded in the active portfolio snapshot, local history, and performance overlay. Gamma stays read-only and the Copilot should stay attached to the live book context."
            : "Load a portfolio snapshot before generating a research card from the portfolio workspace.",
        placeholder:
          "Frame concentration risk, benchmark slippage, capital deployment, or the next diagnostic angle.",
        thread: threads.portfolio,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "equity_research") {
      return {
        supported: overview != null || research != null,
        domain: "equity_research",
        triggerLabel: research ? "Equity scope" : overview ? "Equity overview" : "Load overview",
        contextLabel: research ? describeResearchCopilotContext(research) : (overview?.universe_label ?? "No equity context"),
        domainLabel: "Equity Research",
        guidance:
          overview != null || research != null
            ? "Grounded in the active research run, including weights, coverage, benchmark overlap, and forwarded snapshot context."
            : "Load Equity Research overview or run Scope Analysis before generating a research card.",
        placeholder:
          "Stress-test the active scope, sharpen the hypothesis, or identify the cleanest next comparison.",
        thread: threads.equity_research,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "strategy_lab") {
      const currentHandoffs = strategyLabHandoffs.filter((item) => !item.stale);
      const hasStrategyContext =
        strategy != null || strategyComposition != null || compareResult != null || currentHandoffs.length > 0;
      const resolvedHandoffs = currentHandoffs.filter((item) => item.status === "resolved").length;
      const pendingHandoffs = currentHandoffs.filter((item) => item.status === "pending" || item.status === "resolving").length;
      const strategyContextLabel =
        strategyComposition?.name ??
        strategy?.name ??
        (compareResult
          ? `${compareResult.left.label} vs ${compareResult.right.label}`
          : currentHandoffs.length
            ? `${currentHandoffs.length} handoff${currentHandoffs.length === 1 ? "" : "s"} (${resolvedHandoffs} resolved / ${pendingHandoffs} pending)`
            : "No strategy context");
      return {
        supported: hasStrategyContext,
        domain: "strategy_lab",
        triggerLabel: strategyComposition
          ? "Composition"
          : strategy
            ? "Strategy run"
            : compareResult
              ? "Comparison"
              : currentHandoffs.length
                ? "Handoff context"
                : "Run strategy",
        contextLabel: strategyContextLabel,
        domainLabel: "Strategy Lab",
        guidance:
          hasStrategyContext
            ? "Grounded in imported returns, composed research objects, and comparison outputs. Gamma remains read-only and does not execute trades."
            : "Run a Strategy Lab import, composition, comparison, or queue a current handoff before generating a research card.",
        placeholder:
          "Pressure-test the active strategy, identify robustness gaps, or frame the next portfolio experiment.",
        thread: threads.strategy_lab,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "macro") {
      return {
        supported: true,
        domain: "macro",
        triggerLabel: "Macro context",
        contextLabel: describeMacroCopilotContext(macro),
        domainLabel: "Macro",
        guidance:
          "Grounded in the current Macro workspace. Gamma stays read-only and the Copilot should separate evidence-backed claims from inference.",
        placeholder:
          "Map the active regime, stress-test the leading divergence, or frame the catalyst path.",
        thread: threads.macro,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "commodities") {
      return {
        supported: commodities != null,
        domain: "commodities",
        triggerLabel: commodities ? "Commodities context" : "Load workspace",
        contextLabel: describeCommoditiesCopilotContext(commodities),
        domainLabel: "Commodities",
        guidance:
          commodities != null
            ? "Grounded in the loaded Commodities workspace: market summaries, curves, spreads, inventories, events, warnings, and provider caveats. Gamma remains read-only."
            : "Load the Commodities workspace before generating a research card.",
        placeholder:
          "Pressure-test the selected commodity setup, compare curve and inventory context, or frame the cleanest cross-domain handoff.",
        thread: threads.commodities,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "prediction_markets") {
      return {
        supported: prediction != null,
        domain: "prediction_markets",
        triggerLabel: prediction ? "Market context" : "Select a market",
        contextLabel: describePredictionCopilotContext(prediction),
        domainLabel: "Prediction Markets",
        guidance:
          "Grounded in the selected market, its history, related contracts, flow, and calibration panels. Gamma remains a read-only research environment.",
        placeholder:
          "Test the repricing thesis, compare probability against flow, or frame the cleanest consistency check.",
        thread: threads.prediction_markets,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "crypto") {
      return {
        supported: crypto != null,
        domain: "crypto",
        triggerLabel: crypto ? "Crypto context" : "Select a token",
        contextLabel: describeCryptoCopilotContext(crypto),
        domainLabel: "Crypto",
        guidance:
          "Grounded in the selected token, its price history, liquidity summary, and default relative comparison. Gamma remains a read-only research environment.",
        placeholder:
          "Pressure-test the token thesis, challenge the narrative fit, or compare liquidity quality versus the current benchmark.",
        thread: threads.crypto,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "fundamentals") {
      return {
        supported: fundamentals != null,
        domain: "fundamentals",
        triggerLabel: fundamentals ? "Fundamentals context" : "Select company",
        contextLabel: describeFundamentalsCopilotContext(fundamentals, fundamentalsTicker),
        domainLabel: "Fundamentals",
        guidance:
          fundamentals != null
            ? "Grounded in the selected company, filings, normalized statements, peer basket, DCF state, and reverse valuation. Gamma remains read-only."
            : "Select and load a Fundamentals company before generating a research card.",
        placeholder:
          "Pressure-test implied expectations, compare peers, or frame the cleanest filing-backed valuation question.",
        thread: threads.fundamentals,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "risk") {
      return {
        supported: risk != null,
        domain: "risk",
        triggerLabel: risk ? "Risk context" : "Run risk",
        contextLabel: describeRiskCopilotContext(risk, riskWorkspace ?? workspaceMode),
        domainLabel: "Risk",
        guidance:
          risk != null
            ? "Grounded in the active risk result, including coverage, benchmark overlap, contribution-to-risk, exclusions, and Monte Carlo output."
            : "Run a core or Monte Carlo risk pass before generating a research card from the risk workspace.",
        placeholder:
          "Explain the main VaR driver, isolate the cleanest hedge question, or challenge the current coverage assumptions.",
        thread: threads.risk,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    if (tab === "iv") {
      const activeIvSurface = resolveIvCopilotSurface(ivSurface, ivSession);
      const ivAvailable =
        activeIvSurface != null &&
        (activeIvSurface.snapshot_available || activeIvSurface.points > 0 || activeIvSurface.expiries.length > 0);
      return {
        supported: ivAvailable,
        domain: "iv",
        triggerLabel: ivAvailable ? "Options context" : "Load surface",
        contextLabel: describeIvCopilotContext(ivSurface, ivSession),
        domainLabel: "Options",
        guidance:
          ivAvailable
            ? "Grounded in the active options surface and session state. Gamma remains read-only, so the Copilot should focus on surface interpretation, term structure, and caveats."
            : "Load an options surface snapshot before generating a research card from the Options workspace.",
        placeholder:
          "Interpret the term structure, flag skew caveats, or frame the cleanest surface-comparison question.",
        thread: threads.iv,
        scopeOptions: [],
        selectedScopeDomains: [],
        selectionMessage: null,
      };
    }

    return {
      supported: false,
      domain: null,
      triggerLabel: "Unavailable",
      contextLabel: "Copilot context is unavailable for the active tab.",
      domainLabel: "Copilot",
      guidance: "The Copilot needs an active Gamma tab context before it can generate a research card.",
      placeholder: "Load the required Gamma context to use Copilot.",
      thread: null,
      scopeOptions: [],
      selectedScopeDomains: [],
      selectionMessage: null,
    };
  }

  function buildSynthesisCopilotSurface({
    activeTab,
    workspaceMode,
    threads,
    scopeOptions,
    selectedDomains,
  }: {
    activeTab: TabId;
    workspaceMode: WorkspaceMode | null;
    threads: Record<CopilotDomain, CopilotThreadState>;
    scopeOptions: CopilotGroundingScopeOption[];
    selectedDomains: CopilotBaseDomain[];
  }): CopilotSurfaceState {
    const selectedScopeOptions = scopeOptions.filter((option) =>
      option.domain != null && option.supported && selectedDomains.includes(option.domain)
    );
    const selectionFingerprint = previewCopilotThreadFingerprint("synthesis", {
      workspaceMode,
      synthesisDomains: selectedScopeOptions.map((option) => option.domain as CopilotBaseDomain),
      activeTabId: activeTab,
    });
    const storedThread = threads.synthesis;
    const scopeChanged =
      storedThread.entries.length > 0 &&
      storedThread.contextFingerprint != null &&
      storedThread.contextFingerprint !== selectionFingerprint;
    const visibleThread =
      storedThread.contextFingerprint == null ||
      storedThread.contextFingerprint === selectionFingerprint
        ? storedThread
        : null;
    const selectedLabels = selectedScopeOptions.map((option) => option.label);
    const supported = selectedScopeOptions.length >= 1;
    const scopeSummary =
      selectedLabels.length > 0
        ? selectedLabels.length <= 3
          ? selectedLabels.join(" + ")
          : `${selectedLabels.slice(0, 3).join(" + ")} + ${selectedLabels.length - 3} more`
        : "Select a Gamma context";
    const selectionMessage =
      scopeChanged
        ? "The context scope changed. Generating starts a new Copilot thread."
        : supported
          ? `${selectedScopeOptions.length} Gamma context${selectedScopeOptions.length === 1 ? "" : "s"} selected.`
          : "Select at least one available Gamma context.";

    return {
      supported,
      domain: "synthesis",
      triggerLabel: supported ? "Context-grounded Copilot" : "Select context",
      contextLabel: `Context | ${scopeSummary}`,
      domainLabel: "Copilot Context",
      guidance: supported
        ? "Grounded only in the selected Gamma context tabs. Gamma remains read-only, and Copilot should preserve provenance, warnings, and domain-specific caveats."
        : selectionMessage,
      placeholder:
        "Ask for a grounded thesis, contradiction, operator run, or next research test across the selected context tabs.",
      thread: visibleThread,
      scopeOptions,
      selectedScopeDomains: selectedDomains,
      selectionMessage,
    };
  }

  onMount(() => {
    restoreWorkspaceTabOrders();
    markStartupBegin();
    void bootstrapApp().finally(() => markStartupUsable(workspaceMode == null ? "landing" : $activeTab));
    systemStatusPoller = createAdaptivePoller({
      task: async () => Boolean(await refreshSystemStatus()),
      baseDelayMs: 15_000,
      maxDelayMs: 120_000,
      runImmediately: false
    });
    providerUsagePoller = createAdaptivePoller({
      task: async () => Boolean(await loadProviderUsage()),
      baseDelayMs: 30_000,
      maxDelayMs: 180_000,
      runImmediately: false
    });
    ivSessionPoller = createAdaptivePoller({
      task: async () => {
        const session = await loadIvSession();
        return { ok: Boolean(session), nextDelayMs: session?.running ? 1_500 : 10_000 };
      },
      baseDelayMs: 1_500,
      maxDelayMs: 30_000,
      runImmediately: false
    });
    systemStatusPoller.start();
    const handleGlobalKeydown = (event: KeyboardEvent) => {
      void handleAppKeydown(event);
    };
    const uninstallExternalLinkHandler = installExternalLinkHandler(document, {
      logger: console,
    });
    window.addEventListener("keydown", handleGlobalKeydown);
    return () => {
      uninstallExternalLinkHandler();
      window.removeEventListener("keydown", handleGlobalKeydown);
      systemStatusPoller?.stop();
      providerUsagePoller?.stop();
      ivSessionPoller?.stop();
      stopIvPolling();
    };
  });

  function appendEntries(
    target: ConsoleEntry[],
    label: string,
    lines: string[] | undefined | null,
    tone: ConsoleEntry["tone"]
  ) {
    for (const line of lines ?? []) {
      if (line?.trim()) {
        target.push({ label, message: line, tone });
      }
    }
  }

  async function bootstrapApp() {
    const status = await refreshSystemStatus();
    if (!restoredWorkspaceState) return;
    await hydrateTab(restoredWorkspaceState.activeTab, status);
  }

  async function hydrateTab(tab: TabId, status: SystemStatus | null = $systemStatus) {
    await hydrateActiveWorkspace(tab, status, {
      portfolio: loadPortfolioSnapshot,
      sitrep: loadSitrepContext,
      equityResearch: async () => {
        await Promise.allSettled([loadResearchOverview(), loadSavedResearch()]);
      },
      strategyLab: loadSavedResearch,
      macro: loadMacroWorkspace,
      commodities: () => loadCommoditiesWorkspace({ mode: commoditiesMode }),
      predictionMarkets: loadPredictionMarketScreener,
      crypto: loadCryptoWorkspace,
      fundamentals: () => loadFundamentalsSearch({ query: $selectedFundamentalsTicker ?? undefined }),
      maritime: () => loadMaritimeWorkspace({ mode: maritimeMode }),
      copilot: handleLoadCopilotWorkspaceState,
      risk: async () => {
        if (workspaceMode === "portfolio" && (status?.mock_mode || status?.connection.connected)) {
          await loadPortfolioSnapshot();
        } else {
          await applySharedEquityToTab("risk");
        }
      },
      iv: async () => {
        const autoLoaded = await loadResearchIvContext();
        if (!autoLoaded) await loadIvSession();
      }
    });
  }

  $: if (ivSessionPoller) {
    const shouldPollIv = workspaceMode != null && $activeTab === "iv";
    if (shouldPollIv && !ivPollingActive) {
      ivPollingActive = true;
      void loadIvSession();
      startIvPolling();
    } else if (!shouldPollIv && ivPollingActive) {
      ivPollingActive = false;
      stopIvPolling();
    }
  }

  $: if (providerUsagePoller) {
    if (settingsOpen) providerUsagePoller.start();
    else providerUsagePoller.stop();
  }

  $: consoleEntries = (() => {
    const entries: ConsoleEntry[] = [];
    const seen = new Set<string>();

    const push = (label: string, lines: string[] | undefined | null, tone: ConsoleEntry["tone"]) => {
      const scoped: ConsoleEntry[] = [];
      appendEntries(scoped, label, lines, tone);
      for (const entry of scoped) {
        const key = `${entry.label}:${entry.message}`;
        if (!seen.has(key)) {
          seen.add(key);
          entries.push(entry);
        }
      }
    };

    if ($lastError.trim()) {
      push("API", [$lastError], "error");
    }

    push("Runtime", $diagnostics?.recent_errors, "error");

    if ($activeTab === "portfolio") {
      push("Portfolio", $portfolioSnapshot?.warnings, "warning");
      push("Performance", $portfolioPerformance?.warnings, "warning");
    } else if ($activeTab === "sitrep") {
      push("News", $newsFeed?.warnings, "warning");
      push("Research Overview", $researchOverview?.warnings, "warning");
      push("Macro", $macroSnapshot?.warnings, "warning");
      push("Commodities", $commoditiesWorkspace?.warnings, "warning");
      push("Coverage", $commoditiesWorkspace?.coverage.caveats, "warning");
      push("Prediction", $predictionMarketScreener?.warnings, "warning");
    } else if ($activeTab === "equity_research") {
      push("Equity Research", $researchResult?.warnings, "warning");
      push("Equity Overview", $researchOverview?.warnings, "warning");
    } else if ($activeTab === "strategy_lab") {
      push("Strategy Lab", $strategyLabResult?.warnings, "warning");
      push("Strategy Composition", $strategyLabComposition?.warnings, "warning");
      push("Strategy Compare", $researchCompareResult?.warnings, "warning");
    } else if ($activeTab === "macro") {
      push("Macro", $macroSnapshot?.warnings, "warning");
    } else if ($activeTab === "commodities") {
      push("Commodities", $commoditiesWorkspace?.warnings, "warning");
      push("Coverage", $commoditiesWorkspace?.coverage.caveats, "warning");
    } else if ($activeTab === "prediction_markets") {
      push("Prediction", $predictionMarketDetail ? $predictionMarketWallet?.warnings : [], "warning");
      push("Calibration", $predictionMarketCalibration?.warnings, "warning");
    } else if ($activeTab === "crypto") {
      push("Crypto", $cryptoWorkspace?.warnings, "warning");
      push("Liquidity", $cryptoLiquidity?.warnings, "warning");
    } else if ($activeTab === "fundamentals") {
      push("Fundamentals", $fundamentalsOverview?.warnings, "warning");
      push("Financials", $fundamentalsFinancials?.warnings, "warning");
      push("DCF", $fundamentalsDcfModel?.warnings, "warning");
      push("Peers", $fundamentalsPeers?.warnings, "warning");
      push("Reverse", $fundamentalsReverseValuation?.warnings, "warning");
      push("Reference", $fundamentalsReference?.warnings, "warning");
      push("Provider", $fundamentalsReference?.provider_warnings, "warning");
    } else if ($activeTab === "maritime") {
      push("Sealanes", $maritimeWorkspace?.warnings, "warning");
      push("Coverage", $maritimeWorkspace?.coverage.caveats, "warning");
    } else if ($activeTab === "risk") {
      push("Risk", $riskResult?.warnings, "warning");
    } else {
      push("Options", $ivSurface?.warnings, "warning");
      push("Session", $ivSession?.messages, "info");
      push("Options", $ivSurface?.messages, "info");
    }

    return entries;
  })();

  async function enterWorkspace(mode: WorkspaceMode) {
    workspaceMode = mode;
    sidebarOpen = false;
    copilotOpen = false;
    settingsOpen = false;
    activeTab.set(getWorkspaceHomeTab(mode));
    await hydrateTab(getWorkspaceHomeTab(mode));
  }

  async function switchWorkspace(mode: WorkspaceMode) {
    if (workspaceMode === mode) {
      if (mode === "research") {
        void loadSitrepContext();
      }
      activeTab.set(getWorkspaceHomeTab(mode));
      dismissSurfaces();
      return;
    }
    await enterWorkspace(mode);
  }

  function selectSharedEquity(symbol: string, label?: string | null, sourceTab: TabId | null = $activeTab) {
    return setSharedEquitySelection(symbol, { label, sourceTab });
  }

  function sharedEquitySymbol() {
    return $sharedEquitySelection?.symbol.trim().toUpperCase() || null;
  }

  function handoffErrorMessage(error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }

  const riskHandoffController = createRiskHandoffController({
    getActiveTab: () => $activeTab,
    getStrategyLabResearchBook: () => $strategyLabResearchBook,
    getResearchResult: () => $researchResult,
    setActiveTab: (tab) => activeTab.set(tab),
    computeRisk,
    onRunningChange: (running) => {
      riskHandoffRunning = running;
    },
    onError: (error) => {
      const message = `Risk handoff failed: ${handoffErrorMessage(error)}`;
      console.error("[Risk handoff]", error);
      lastError.set(message);
    }
  });

  function researchResultMatchesSingleEquity(symbol: string) {
    const normalizedSymbol = symbol.trim().toUpperCase();
    return (
      $researchResult?.scope_type === "single_ticker" &&
      ($researchResult.primary_symbol ?? $researchResult.snapshot?.positions[0]?.symbol ?? "")
        .trim()
        .toUpperCase() === normalizedSymbol
    );
  }

  async function ensureSingleEquityResearch(symbol: string) {
    const normalizedSymbol = symbol.trim().toUpperCase();
    if (!normalizedSymbol) {
      return;
    }
    setResearchDraft({
      ...$researchDraft,
      scopeType: "single_ticker",
      primarySymbol: normalizedSymbol,
      benchmarkSymbol: $researchDraft.benchmarkSymbol.trim().toUpperCase() || "SPY"
    });
    if (researchResultMatchesSingleEquity(normalizedSymbol)) {
      return;
    }
    await runResearch({
      scopeType: "single_ticker",
      primarySymbol: normalizedSymbol,
      benchmarkSymbol: $researchDraft.benchmarkSymbol.trim().toUpperCase() || "SPY",
      lookbackDays: $researchDraft.lookbackDays
    });
  }

  async function applySharedEquityToTab(tab: TabId) {
    const symbol = sharedEquitySymbol();
    if (!symbol) {
      return false;
    }

    if (tab === "equity_research") {
      // Preserve an in-progress synthetic basket: returning to Equity Research must not
      // replace the active scope with the focal single ticker (usability audit P1).
      if (
        $researchDraft.scopeType === "synthetic_portfolio" ||
        $researchResult?.scope_type === "synthetic_portfolio"
      ) {
        return false;
      }
      equityResearchMode = "scope_analysis";
      await ensureSingleEquityResearch(symbol);
      return true;
    }

    if (tab === "fundamentals") {
      await loadFundamentalsSearch({ query: symbol });
      if ($selectedFundamentalsTicker !== symbol || !$fundamentalsOverview) {
        await selectFundamentalsCompany(symbol);
      }
      return true;
    }

    if (tab === "risk") {
      await ensureSingleEquityResearch(symbol);
      const request = buildRiskRequestFromResearch($researchResult);
      if (request) {
        await computeRisk(request);
      }
      return true;
    }

    if (tab === "iv") {
      ivRequestedSymbol = symbol;
      await loadIvSurface({
        symbol,
        marketDataMode: $systemStatus?.market_data_mode ?? "delayed",
        waitSeconds: 60,
        depthPreset: "max"
      });
      await loadIvSession();
      return true;
    }

    return false;
  }

  async function selectTab(tab: TabId | "research") {
    if (!workspaceMode) {
      return;
    }
    const nextTab = normalizeAppTabId(tab);
    if (!isWorkspaceTab(workspaceMode, nextTab)) {
      resetNavigationSearch();
      return;
    }

    resetNavigationSearch();
    dismissSurfaces();
    activeTab.set(nextTab);
    if (nextTab !== "copilot") {
      copilotContextTab = nextTab;
    }

    if (nextTab === "sitrep") {
      await loadSitrepContext();
    } else if (nextTab === "copilot") {
      await handleLoadCopilotWorkspaceState();
    } else if (nextTab === "equity_research") {
      if (await applySharedEquityToTab(nextTab)) {
        return;
      }
      if (!$researchOverview) {
        await loadResearchOverview();
      }
      if (!$savedResearchItems.length) {
        await loadSavedResearch();
      }
    } else if (nextTab === "strategy_lab") {
      if (!$savedResearchItems.length) {
        await loadSavedResearch();
      }
    } else if (nextTab === "macro") {
      // A SITREP workspace load fans out the snapshot alone, so check the
      // divergence/event stores too before skipping the full Macro bundle.
      if (!$macroSnapshot || !$macroDivergences || !$macroEvents) {
        await loadMacroWorkspace();
      }
    } else if (nextTab === "commodities") {
      await loadCommoditiesWorkspace({ mode: commoditiesMode });
    } else if (nextTab === "prediction_markets") {
      await loadPredictionMarketScreener();
    } else if (nextTab === "crypto") {
      await loadCryptoWorkspace();
    } else if (nextTab === "fundamentals") {
      if (await applySharedEquityToTab(nextTab)) {
        return;
      }
      await loadFundamentalsSearch({
        query: $selectedFundamentalsTicker ?? undefined
      });
    } else if (nextTab === "maritime") {
      await loadMaritimeWorkspace({ mode: maritimeMode });
    } else if (nextTab === "risk") {
      await applySharedEquityToTab(nextTab);
    } else if (nextTab === "iv") {
      if (await applySharedEquityToTab(nextTab)) {
        return;
      }
      const autoLoaded = await loadResearchIvContext();
      if (!autoLoaded) {
        await loadIvSession();
      }
    }
  }

  async function openRiskFromResearch() {
    await riskHandoffController.open();
  }

  async function runResearchFromView(options: Parameters<typeof runResearch>[0]) {
    if (options.scopeType === "single_ticker" && options.primarySymbol) {
      selectSharedEquity(options.primarySymbol, null, "equity_research");
    }
    await runResearch(options);
  }

  async function selectFundamentalsCompanyFromView(
    ticker: string,
    options?: Parameters<typeof selectFundamentalsCompany>[1]
  ) {
    selectSharedEquity(ticker, null, "fundamentals");
    await selectFundamentalsCompany(ticker, options);
  }

  async function openIvFromResearch() {
    activeTab.set("iv");
    const autoLoaded = await loadResearchIvContext();
    if (!autoLoaded) {
      await loadIvSession();
    }
  }

  async function handleLoadIvSurface(options: Parameters<typeof loadIvSurface>[0]) {
    if (typeof options !== "string") {
      ivRequestedSymbol = options.symbol.trim().toUpperCase();
    } else {
      ivRequestedSymbol = options.trim().toUpperCase();
    }
    await loadIvSurface(options);
  }

  async function openStrategyLabFromEquityResearch() {
    workspaceMode = "research";
    activeTab.set("strategy_lab");
    strategyLabMode = "composer";
    if (!$savedResearchItems.length) {
      await loadSavedResearch();
    }
  }

  async function handleStrategyLabHandoff(
    handoff: StrategyLabHandoffEnvelope,
    options: { open?: boolean } = {}
  ) {
    if (options.open) {
      enqueueAndOpenStrategyLab(handoff);
      workspaceMode = "research";
      strategyLabMode = "composer";
      await selectTab("strategy_lab");
      await resolvePendingStrategyLabHandoffs();
      return;
    }
    enqueueStrategyLabHandoff(handoff);
    consoleEntries = [
      {
        label: "Strategy Lab",
        message: `${handoff.selected_entity.label} queued for Strategy Lab.`,
        tone: "action"
      },
      ...consoleEntries
    ].slice(0, 12);
  }

  async function loadResearchIvContext() {
    if (workspaceMode !== "research") {
      return false;
    }
    const request = buildIvRequestFromResearch($researchResult, $systemStatus?.market_data_mode);
    if (!request) {
      return false;
    }
    ivRequestedSymbol = request.symbol;
    await loadIvSurface(request);
    await loadIvSession();
    return true;
  }

  async function handleConnectionToggle() {
    const nextStatus = await toggleConnection();
    if (nextStatus?.connection.connected) {
      await loadPortfolioSnapshot();
    }
    await loadDiagnostics();
    if (workspaceMode != null && $activeTab === "iv") {
      await loadIvSession();
    }
  }

  async function handleMarketDataModeChange(mode: string) {
    await setMarketDataMode(mode);
    await loadDiagnostics();
    if (workspaceMode != null && $activeTab === "iv") {
      await loadIvSession();
    }
  }

  async function handleBaseCurrencyChange(currency: string) {
    const response = await setBaseCurrency(currency);
    if (!response) {
      return;
    }
    await loadDiagnostics();
    if (workspaceMode === "portfolio" && ($systemStatus?.mock_mode || $systemStatus?.connection.connected)) {
      await loadPortfolioSnapshot();
    }
  }

  async function handleRefreshWorkspace() {
    await Promise.allSettled([refreshSystemStatus(), loadDiagnostics(), loadProviderUsage()]);

    if (workspaceMode === "portfolio" && ($activeTab === "portfolio" || $activeTab === "risk")) {
      await loadPortfolioSnapshot();
    }

    if ($activeTab === "equity_research" && equityResearchMode === "overview") {
      await loadResearchOverview({ forceRefresh: true });
    }

    if ($activeTab === "sitrep") {
      await loadSitrepContext({ forceRefresh: true });
    }

    if ($activeTab === "prediction_markets") {
      await loadPredictionMarketScreener({ forceRefresh: true });
    }

    if ($activeTab === "crypto") {
      await loadCryptoWorkspace({ forceRefresh: true });
    }

    if ($activeTab === "fundamentals") {
      await loadFundamentalsSearch({
        query: $selectedFundamentalsTicker ?? undefined,
        forceRefresh: true
      });
    }

    if ($activeTab === "maritime") {
      await loadMaritimeWorkspace({ mode: maritimeMode, forceRefresh: true });
    }

    if ($activeTab === "macro") {
      await loadMacroWorkspace({ forceRefresh: true });
    }

    if ($activeTab === "commodities") {
      await loadCommoditiesWorkspace({ mode: commoditiesMode, forceRefresh: true });
    }

    if ($activeTab === "iv") {
      if (workspaceMode === "research") {
        const autoLoaded = await loadResearchIvContext();
        if (!autoLoaded) {
          await loadIvSession();
        }
      } else {
        await loadIvSession();
      }
    }
  }

  async function handleChangeView() {
    workspaceMode = null;
    diagnosticsOpen = false;
    sidebarOpen = false;
    copilotOpen = false;
    settingsOpen = false;
  }

  async function handleToggleDiagnostics() {
    diagnosticsOpen = !diagnosticsOpen;
    if (diagnosticsOpen) {
      await loadDiagnostics();
    }
  }

  async function handleRunDiagnostics() {
    await runDiagnosticsAction();
    await loadDiagnostics();
  }

  async function handleForceSubscribe() {
    await forceAccountSubscribe();
    await loadDiagnostics();
  }

  async function handleClearHistory() {
    await clearPortfolioHistory();
    await loadDiagnostics();
  }

  function startIvPolling() {
    ivSessionPoller?.start();
  }

  function stopIvPolling() {
    ivSessionPoller?.stop();
    cancelIvSessionRequest();
  }

  function handleToggleSidebar() {
    if (workspaceMode == null) {
      return;
    }
    const nextOpen = !sidebarOpen;
    sidebarOpen = nextOpen;
    if (nextOpen) {
      copilotOpen = false;
      settingsOpen = false;
    }
  }

  function handleToggleSettings() {
    const nextOpen = !settingsOpen;
    settingsOpen = nextOpen;
    if (nextOpen) {
      sidebarOpen = false;
      copilotOpen = false;
      void loadProviderUsage();
    }
  }

  function handleClearSelectedPortfolio() {
    if ($researchResult?.scope_type === "synthetic_portfolio") {
      researchResult.set(null);
      return;
    }
    clearPortfolioSnapshot();
  }

  function handleToggleCopilot() {
    if (workspaceMode == null) {
      return;
    }
    const nextOpen = !copilotOpen;
    copilotOpen = nextOpen;
    if (nextOpen) {
      sidebarOpen = false;
      settingsOpen = false;
    }
  }

  function handleToggleSynthesisScope(domain: CopilotBaseDomain) {
    if (selectedSynthesisDomains.includes(domain)) {
      selectedSynthesisDomains = selectedSynthesisDomains.filter((item) => item !== domain);
      return;
    }
    selectedSynthesisDomains = [...selectedSynthesisDomains, domain];
  }

  function dismissSurfaces() {
    sidebarOpen = false;
    copilotOpen = false;
    settingsOpen = false;
  }

  function resetNavigationSearch() {
    navigationSearchResetToken += 1;
  }

  async function handleGenerateCopilot(prompt = "", reasoningEffort?: CopilotReasoningEffort) {
    if (!copilotSurface.supported || !copilotSurface.domain) {
      return null;
    }
    return loadCopilotResearchCard(copilotSurface.domain, prompt, {
      workspaceMode,
      synthesisDomains:
        copilotSurface.domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handleRunOperatorCopilot(prompt = "", reasoningEffort?: CopilotReasoningEffort) {
    if (!copilotSurface.supported || !copilotSurface.domain) {
      return null;
    }
    return executeCopilotOperatorPlan(copilotSurface.domain, prompt, {
      workspaceMode,
      synthesisDomains:
        copilotSurface.domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handleGenerateCopilotWorkspace(
    domain: CopilotDomain,
    prompt = "",
    reasoningEffort?: CopilotReasoningEffort
  ) {
    return loadCopilotResearchCard(domain, prompt, {
      workspaceMode,
      synthesisDomains: domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handlePlanCopilotWorkspace(
    domain: CopilotDomain,
    prompt = "",
    reasoningEffort?: CopilotReasoningEffort
  ) {
    return loadCopilotResearchPlan(domain, prompt, {
      workspaceMode,
      synthesisDomains: domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handleOperatorPlanCopilotWorkspace(
    domain: CopilotDomain,
    prompt = "",
    reasoningEffort?: CopilotReasoningEffort
  ) {
    return loadCopilotOperatorPlan(domain, prompt, {
      workspaceMode,
      synthesisDomains: domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handleRunOperatorCopilotWorkspace(
    domain: CopilotDomain,
    prompt = "",
    reasoningEffort?: CopilotReasoningEffort
  ) {
    return executeCopilotOperatorPlan(domain, prompt, {
      workspaceMode,
      synthesisDomains: domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
      reasoningEffort,
    });
  }

  async function handleArchiveCopilotSession(sessionId: string) {
    return archiveCopilotSession(sessionId);
  }

  async function handleNewCopilotSession() {
    startNewCopilotSession();
    return handleLoadCopilotWorkspaceState();
  }

  async function handleLoadCopilotSessionsFiltered(options: { includeArchived?: boolean; search?: string } = {}) {
    return loadCopilotSessions(options);
  }

  async function handleSelectCopilotSession(sessionId: string) {
    return loadCopilotSession(sessionId, { makeActive: true });
  }

  async function handleSendToCopilot(handoff: CrossTabHandoffEnvelope) {
    const sourceTab = normalizeAppTabId(handoff.source_tab as TabId | "research");
    latestCopilotHandoff = handoff;
    if (isWorkspaceTab("research", sourceTab) || isWorkspaceTab("portfolio", sourceTab)) {
      copilotContextTab = sourceTab;
    }
    workspaceMode = "research";
    activeTab.set("copilot");
    copilotOpen = false;
    sidebarOpen = false;
    settingsOpen = false;
    await handleLoadCopilotWorkspaceState();
  }

  async function handleLoadCopilotWorkspaceState() {
    await Promise.allSettled([loadCopilotSessions(), loadActiveCopilotSession(), loadCopilotMemos()]);
  }

  async function handleOpenKeyBindings() {
    settingsOpen = false;
    await openKeyBindingsWindow();
  }

  function handleTabReorder(draggedTabId: TabId, dropIndex: number) {
    if (!workspaceMode) {
      return;
    }
    reorderWorkspaceTab(workspaceMode, draggedTabId, dropIndex);
  }

  function handleResetTabOrder() {
    if (!workspaceMode) {
      return;
    }
    resetWorkspaceTabOrder(workspaceMode);
  }

  function getNumberShortcutIndex(event: KeyboardEvent) {
    if (/^[1-9]$/.test(event.key)) {
      return Number(event.key);
    }
    const codeMatch = /^(?:Digit|Numpad)([1-9])$/.exec(event.code);
    return codeMatch ? Number(codeMatch[1]) : null;
  }

  async function selectModeByShortcutIndex(shortcutIndex: number) {
    const nextMode = getModeByShortcutIndex($activeTab, shortcutIndex);
    if (!nextMode) {
      return false;
    }

    return selectModeById($activeTab, nextMode.id);
  }

  async function selectModeById(tabId: TabId, modeId: string) {
    if (!getTabModes(tabId).some((mode) => mode.id === modeId)) {
      return false;
    }

    if (tabId === "equity_research") {
      equityResearchMode = modeId as EquityResearchMode;
      if (equityResearchMode === "overview" && !$researchOverview) {
        await loadResearchOverview();
      }
      if (equityResearchMode === "saved_equity_research") {
        await loadSavedResearch();
      }
      return true;
    }

    if (tabId === "strategy_lab") {
      strategyLabMode = modeId as StrategyLabMode;
      if (strategyLabMode === "saved_runs") {
        await loadSavedResearch();
      }
      return true;
    }

    if (tabId === "macro") {
      await loadMacroWorkspace({ mode: modeId as MacroContextState["mode"] });
      return true;
    }

    if (tabId === "crypto") {
      cryptoMode = modeId as CryptoMode;
      return true;
    }

    if (tabId === "fundamentals") {
      fundamentalsMode = modeId as FundamentalsMode;
      return true;
    }

    if (tabId === "commodities") {
      commoditiesMode = modeId as CommodityMode;
      await loadCommoditiesWorkspace({ mode: commoditiesMode });
      return true;
    }

    if (tabId === "maritime") {
      maritimeMode = modeId as MaritimeMode;
      await loadMaritimeWorkspace({ mode: maritimeMode });
      return true;
    }

    if (tabId === "iv") {
      optionsMode = modeId as OptionsMode;
      return true;
    }

    if (tabId === "risk") {
      riskMode = modeId as RiskMode;
      return true;
    }

    return false;
  }

  function getCurrentModeId(tabId: TabId) {
    if (tabId === "equity_research") return equityResearchMode;
    if (tabId === "strategy_lab") return strategyLabMode;
    if (tabId === "macro") return $macroContext.mode;
    if (tabId === "crypto") return cryptoMode;
    if (tabId === "fundamentals") return fundamentalsMode;
    if (tabId === "commodities") return commoditiesMode;
    if (tabId === "maritime") return maritimeMode;
    if (tabId === "iv") return optionsMode;
    if (tabId === "risk") return riskMode;
    return null;
  }

  async function selectAdjacentTab(direction: -1 | 1) {
    if (!workspaceMode) {
      return false;
    }
    const tabs = getOrderedWorkspaceTabs(workspaceMode, $workspaceTabOrders);
    const currentIndex = tabs.findIndex((tab) => tab.id === $activeTab);
    if (currentIndex < 0 || tabs.length < 2) {
      return false;
    }
    const nextIndex = (currentIndex + direction + tabs.length) % tabs.length;
    await selectTab(tabs[nextIndex].id);
    return true;
  }

  async function selectAdjacentMode(direction: -1 | 1) {
    const modes = getTabModes($activeTab);
    if (modes.length < 2) {
      return false;
    }
    const currentModeId = getCurrentModeId($activeTab);
    const currentIndex = Math.max(0, modes.findIndex((mode) => mode.id === currentModeId));
    const nextIndex = (currentIndex + direction + modes.length) % modes.length;
    return selectModeById($activeTab, modes[nextIndex].id);
  }

  async function selectNavigationRoute(route: NavigationRouteMatch) {
    const routeTab = normalizeAppTabId(route.tab.id);
    if (!workspaceMode || !isWorkspaceTab(workspaceMode, routeTab)) {
      resetNavigationSearch();
      return;
    }
    await selectTab(routeTab);
    if (route.mode) {
      await selectModeById(routeTab, route.mode.id);
    }
  }

  async function openSitrepHandoff(handoff: SitrepHandoffRequest) {
    workspaceMode = "research";
    const targetTab = normalizeAppTabId(handoff.targetTab);
    if (handoff.symbol) {
      selectSharedEquity(handoff.symbol, handoff.label ?? null, "sitrep");
    }

    await selectTab(targetTab);

    if (targetTab === "equity_research" && handoff.symbol) {
      // An explicit handoff overrides any preserved basket; passive tab returns do not.
      equityResearchMode = "scope_analysis";
      await ensureSingleEquityResearch(handoff.symbol);
      if (handoff.targetMode) {
        await selectModeById(targetTab, handoff.targetMode);
      }
      return;
    }

    if (targetTab === "commodities") {
      const nextMode = (handoff.targetMode ?? "overview") as CommodityMode;
      commoditiesMode = nextMode;
      await loadCommoditiesWorkspace({
        mode: nextMode,
        selectedInstrumentId: handoff.commodityId ?? undefined
      });
      return;
    }

    if (targetTab === "prediction_markets") {
      if (handoff.marketId) {
        await selectPredictionMarket(handoff.marketId);
      }
      return;
    }

    if (handoff.targetMode) {
      await selectModeById(targetTab, handoff.targetMode);
    }
  }

  async function handleAppKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented) {
      return;
    }

    const hasDismissibleSurface = sidebarOpen || copilotOpen || settingsOpen;
    const editableTarget = isEditableEventTarget(event.target);

    if (matchesActionKeybinding(event, "dismiss_surface")) {
      if (hasDismissibleSurface) {
        event.preventDefault();
        dismissSurfaces();
      }
      return;
    }

    if (matchesActionKeybinding(event, "refresh_view")) {
      event.preventDefault();
      await handleRefreshWorkspace();
      return;
    }

    if (matchesActionKeybinding(event, "open_settings")) {
      if (!editableTarget && workspaceMode != null) {
        event.preventDefault();
        settingsOpen = true;
        sidebarOpen = false;
        copilotOpen = false;
      }
      return;
    }

    if (editableTarget) {
      return;
    }

    if (matchesActionKeybinding(event, "toggle_sidebar")) {
      if (workspaceMode != null) {
        event.preventDefault();
        handleToggleSidebar();
      }
      return;
    }

    if (matchesActionKeybinding(event, "switch_portfolio_workspace")) {
      event.preventDefault();
      await switchWorkspace("portfolio");
      return;
    }

    if (matchesActionKeybinding(event, "switch_research_workspace")) {
      event.preventDefault();
      await switchWorkspace("research");
      return;
    }

    if (matchesActionKeybinding(event, "previous_tab")) {
      if (workspaceMode != null) {
        event.preventDefault();
        await selectAdjacentTab(-1);
      }
      return;
    }

    if (matchesActionKeybinding(event, "next_tab")) {
      if (workspaceMode != null) {
        event.preventDefault();
        await selectAdjacentTab(1);
      }
      return;
    }

    if (matchesActionKeybinding(event, "previous_mode")) {
      if (workspaceMode != null) {
        event.preventDefault();
        await selectAdjacentMode(-1);
      }
      return;
    }

    if (matchesActionKeybinding(event, "next_mode")) {
      if (workspaceMode != null) {
        event.preventDefault();
        await selectAdjacentMode(1);
      }
      return;
    }

    const numberShortcutIndex = getNumberShortcutIndex(event);

    if (
      workspaceMode != null &&
      event.shiftKey &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey &&
      numberShortcutIndex != null
    ) {
      if (getModeByShortcutIndex($activeTab, numberShortcutIndex)) {
        event.preventDefault();
        await selectModeByShortcutIndex(numberShortcutIndex);
      }
      return;
    }

    if (
      workspaceMode != null &&
      event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey &&
      !event.metaKey &&
      numberShortcutIndex != null
    ) {
      const nextTab = getTabByShortcutIndex(workspaceMode, $workspaceTabOrders, numberShortcutIndex);
      if (nextTab) {
        event.preventDefault();
        await selectTab(nextTab);
      }
    }
  }
</script>

{#if workspaceMode == null}
  <LandingPage
    status={$systemStatus}
    busy={$loading.status}
    onConnect={handleConnectionToggle}
    onEnterPortfolio={() => enterWorkspace("portfolio")}
    onEnterResearch={() => enterWorkspace("research")}
  />
{:else}
  <Shell
    activeTab={$activeTab}
    workspaceMode={workspaceMode}
    workspaceTabOrders={$workspaceTabOrders}
    searchResetToken={navigationSearchResetToken}
    tabs={tabBarTabs}
    selectedEquity={$sharedEquitySelection}
    selectedPortfolio={$researchResult?.scope_type === "synthetic_portfolio"
      ? { variant: "research" }
      : $portfolioSnapshot
      ? { variant: "live" }
      : null}
    copilotOpen={copilotOpen}
    onSelectTab={selectTab}
    onSelectRoute={selectNavigationRoute}
    onClearSelectedEquity={clearSharedEquitySelection}
    onClearSelectedPortfolio={handleClearSelectedPortfolio}
    onToggleCopilot={handleToggleCopilot}
    onToggleSidebar={handleToggleSidebar}
  >
    <svelte:fragment slot="status">
      <StatusRail
        status={$systemStatus}
        providerUsage={$providerUsage}
        requestMetrics={$requestMetrics}
        pollingState={{
          system: true,
          providerUsage: settingsOpen,
          iv: ivPollingActive
        }}
        workspaceMode={workspaceMode}
        busy={$loading.status || $loading.diagnostics || $loading.portfolio || $loading.researchOverview || $loading.macro || $loading.commodities || $loading.prediction || $loading.ivSession}
        settingsOpen={settingsOpen}
        onToggleConnection={handleConnectionToggle}
        onBaseCurrencyChange={handleBaseCurrencyChange}
        onMarketDataModeChange={handleMarketDataModeChange}
        onRefresh={handleRefreshWorkspace}
        onChangeView={handleChangeView}
        onToggleSettings={handleToggleSettings}
        onOpenKeyBindings={handleOpenKeyBindings}
      />
    </svelte:fragment>

    <section class="workspace-shell">
      <TabBar
        activeTab={$activeTab}
        open={sidebarOpen}
        tabs={tabBarTabs}
        onSelect={selectTab}
        onClose={() => sidebarOpen = false}
        onReset={handleResetTabOrder}
        onReorder={handleTabReorder}
      />

      <section class="workspace-main">
        {#if activeViewLoadError}
          <div class="view-load-state" role="alert">
            <strong>Unable to load view</strong>
            <span>{activeViewLoadError}</span>
          </div>
        {:else if activeViewComponent == null || activeViewTab !== $activeTab || activeViewLoading === $activeTab}
          <div class="view-load-state" aria-live="polite">
            <strong>Loading workspace</strong>
          </div>
        {:else if $activeTab === "portfolio"}
          <svelte:component
            this={activeViewComponent}
            snapshot={$portfolioSnapshot}
            history={$portfolioHistory}
            performance={$portfolioPerformance}
            loading={$loading.portfolio}
            diagnostics={$diagnostics}
            diagnosticsLog={$diagnosticsLog}
            consoleEntries={consoleEntries}
            diagnosticsOpen={diagnosticsOpen}
            diagnosticsLoading={$loading.diagnostics}
            diagnosticsActionLoading={$loading.diagnosticsAction || $loading.portfolioAction}
            onReloadPerformance={loadPortfolioPerformance}
            onToggleDiagnostics={handleToggleDiagnostics}
            onRefreshDiagnostics={loadDiagnostics}
            onRunDiagnostics={handleRunDiagnostics}
            onForceSubscribe={handleForceSubscribe}
            onClearHistory={handleClearHistory}
          />
        {:else if $activeTab === "sitrep"}
          <svelte:component
            this={activeViewComponent}
            system={$systemStatus}
            overview={$researchOverview}
            indicesOverview={$sitrepIndicesOverview}
            news={$newsFeed}
            macro={$macroSnapshot}
            commodities={$commoditiesWorkspace}
            prediction={$predictionMarketScreener}
            loading={$loading.researchOverview || $loading.news || $loading.macro || $loading.commodities || $loading.prediction}
            onLoadNews={loadNewsFeed}
            onLoadOverview={loadResearchOverview}
            onLoadIndicesOverview={loadSitrepIndicesOverview}
            onLoadMacro={loadMacroWorkspace}
            onLoadCommodities={loadCommoditiesWorkspace}
            onLoadPrediction={loadPredictionMarketScreener}
            onLoadWorkspace={loadSitrepWorkspace}
            selectedEquitySymbol={$sharedEquitySelection?.symbol ?? null}
            onSelectEquity={(symbol, label) => selectSharedEquity(symbol, label, "sitrep")}
            onOpenHandoff={openSitrepHandoff}
            workspaceMeta={$sitrepWorkspaceMeta}
            followUps={$sitrepFollowUps}
            onLoadFollowUps={loadSitrepFollowUps}
            onToggleFollowUp={toggleSitrepFollowUpItem}
            onUpdateFollowUp={(id, patch) => updateSitrepFollowUpItem(id, patch)}
            onDismissFollowUp={dismissSitrepFollowUpItem}
          />
        {:else if $activeTab === "equity_research"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={equityResearchMode}
            overview={$researchOverview}
            result={$researchResult}
            strategyResult={$strategyLabResult}
            compareResult={$researchCompareResult}
            savedItems={$savedResearchItems}
            loading={$loading.research}
            overviewLoading={$loading.researchOverview}
            compareLoading={$loading.compareScenario}
            savedLoading={$loading.savedResearch}
            riskHandoffLoading={riskHandoffRunning}
            selectedEquitySymbol={$sharedEquitySelection?.symbol ?? null}
            onLoadOverview={loadResearchOverview}
            onRun={runResearchFromView}
            onSelectEquity={(symbol, label) => selectSharedEquity(symbol, label, $activeTab)}
            onCompare={compareResearch}
            onLoadSaved={loadSavedResearch}
            onSaveResearch={saveResearchItem}
            onDeleteSaved={deleteSavedResearchItem}
            onOpenRisk={openRiskFromResearch}
            onOpenIv={openIvFromResearch}
            onOpenStrategyLab={openStrategyLabFromEquityResearch}
            onSendToStrategyLab={handleStrategyLabHandoff}
          />
        {:else if $activeTab === "strategy_lab"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={strategyLabMode}
            result={$researchResult}
            strategyResult={$strategyLabResult}
            strategyComposition={$strategyLabComposition}
            savedItems={$savedResearchItems}
            strategyLoading={$loading.strategyLab}
            savedLoading={$loading.savedResearch}
            riskHandoffLoading={riskHandoffRunning}
            onAnalyzeStrategy={analyzeStrategyLab}
            onComposeStrategy={composeStrategyLab}
            onComposePortfolioStrategy={composeStrategyLabPortfolio}
            onValidatePortfolioStrategy={validateStrategyLabPortfolio}
            onLoadSaved={loadSavedResearch}
            onSaveResearch={saveResearchItem}
            onDeleteSaved={deleteSavedResearchItem}
            onRestoreStrategy={restoreStrategyLabResult}
            onOpenRisk={openRiskFromResearch}
            strategyLabHandoffs={$strategyLabHandoffQueue}
            handoffLoading={$loading.strategyLabHandoff}
            onResolveStrategyLabHandoffs={resolvePendingStrategyLabHandoffs}
            onDismissStrategyLabHandoff={dismissStrategyLabHandoff}
            onClearStrategyLabHandoffs={clearStrategyLabHandoffs}
            onAcceptStrategyLabHandoff={acceptResolvedStrategyLabHandoff}
            onReviveStrategyLabHandoff={reviveStrategyLabHandoff}
            onClearStaleStrategyLabHandoffs={clearStaleStrategyLabHandoffs}
          />
        {:else if $activeTab === "macro"}
          <svelte:component
            this={activeViewComponent}
            snapshot={$macroSnapshot}
            divergences={$macroDivergences}
            events={$macroEvents}
            histories={$macroSeriesHistories}
            loading={$loading.macro || $loading.macroHistory}
            onLoadWorkspace={loadMacroWorkspace}
            onLoadSeries={loadMacroSeriesHistory}
            onSendToStrategyLab={handleStrategyLabHandoff}
          />
        {:else if $activeTab === "commodities"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={commoditiesMode}
            workspace={$commoditiesWorkspace}
            loading={$loading.commodities}
            onLoadWorkspace={loadCommoditiesWorkspace}
            macroHistories={$macroSeriesHistories}
            onLoadMacroSeries={loadMacroSeriesHistory}
            onSendToStrategyLab={handleStrategyLabHandoff}
          />
        {:else if $activeTab === "prediction_markets"}
          <svelte:component
            this={activeViewComponent}
            screener={$predictionMarketScreener}
            detail={$predictionMarketDetail}
            history={$predictionMarketHistory}
            wallet={$predictionMarketWallet}
            related={$predictionMarketRelated}
            calibration={$predictionMarketCalibration}
            loading={$loading.prediction || $loading.predictionDetail}
            onLoadScreener={loadPredictionMarketScreener}
            onSelectMarket={selectPredictionMarket}
            onSendToStrategyLab={handleStrategyLabHandoff}
          />
        {:else if $activeTab === "crypto"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={cryptoMode}
            workspace={$cryptoWorkspace}
            detail={$cryptoTokenDetail}
            history={$cryptoPriceHistory}
            liquidity={$cryptoLiquidity}
            flow={$cryptoFlowSummary}
            comparison={$cryptoComparison}
            syntheticPortfolio={$cryptoSyntheticPortfolio}
            loading={$loading.crypto || $loading.cryptoDetail}
            portfolioLoading={$loading.cryptoPortfolio}
            onLoadWorkspace={loadCryptoWorkspace}
            onSelectToken={selectCryptoToken}
            onRunSyntheticPortfolio={runCryptoSyntheticPortfolio}
            onClearSyntheticPortfolio={clearCryptoSyntheticPortfolio}
          />
        {:else if $activeTab === "fundamentals"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={fundamentalsMode}
            search={$fundamentalsSearch}
            selectedTicker={$selectedFundamentalsTicker}
            overview={$fundamentalsOverview}
            financials={$fundamentalsFinancials}
            dcfModel={$fundamentalsDcfModel}
            peers={$fundamentalsPeers}
            reverseValuation={$fundamentalsReverseValuation}
            reference={$fundamentalsReference}
            dcfSnapshots={$fundamentalsDcfSnapshots}
            loading={$loading.fundamentals}
            searchState={$fundamentalsSearchState}
            saving={$loading.fundamentalsSave}
            onSearch={loadFundamentalsSearch}
            onSelectCompany={selectFundamentalsCompanyFromView}
            onSavePeerBasket={saveFundamentalsPeerBasket}
            onSaveDcfModel={saveFundamentalsDcfModel}
            onSaveDcfSnapshot={saveFundamentalsDcfSnapshot}
            onLoadDcfSnapshot={loadFundamentalsDcfSnapshot}
            onSendToCopilot={handleSendToCopilot}
          />
        {:else if $activeTab === "maritime"}
          <svelte:component
            this={activeViewComponent}
            bind:mode={maritimeMode}
            workspace={$maritimeWorkspace}
            loading={$loading.maritime}
            onLoadWorkspace={loadMaritimeWorkspace}
          />
        {:else if $activeTab === "copilot"}
          <svelte:component
            this={activeViewComponent}
            synthesisSurface={synthesisCopilotSurface}
            sessions={$copilotSessions}
            activeSession={$activeCopilotSession}
            actionDefinitions={$copilotActionDefinitions}
            researchPlan={$copilotResearchPlan}
            operatorPlan={$copilotOperatorPlan}
            operatorResult={$copilotOperatorResult}
            latestHandoff={latestCopilotHandoff}
            loading={$loading.copilot}
            onGenerate={handleGenerateCopilotWorkspace}
            onPlan={handlePlanCopilotWorkspace}
            onOperatorPlan={handleOperatorPlanCopilotWorkspace}
            onRunOperator={handleRunOperatorCopilotWorkspace}
            onArchiveSession={handleArchiveCopilotSession}
            onNewSession={handleNewCopilotSession}
            onLoadSessions={handleLoadCopilotWorkspaceState}
            onSelectSession={handleSelectCopilotSession}
            onSearchSessions={handleLoadCopilotSessionsFiltered}
            onToggleScope={handleToggleSynthesisScope}
          />
        {:else if $activeTab === "risk"}
          <svelte:component
            this={activeViewComponent}
            mode={workspaceMode}
            bind:activeMode={riskMode}
            snapshot={$portfolioSnapshot}
            researchSnapshot={$researchResult?.snapshot ?? null}
            strategyLabResearchBook={$strategyLabResearchBook}
            result={$riskResult}
            loading={$loading.risk}
            onCompute={computeRisk}
          />
        {:else}
          <svelte:component
            this={activeViewComponent}
            bind:mode={optionsMode}
            status={$systemStatus}
            requestedSymbol={ivRequestedSymbol}
            result={$ivSurface}
            session={$ivSession}
            underlyingHistory={$ivUnderlyingHistory}
            underlyingPricePoints={$researchResult?.primary_price_points ?? []}
            researchPrimarySymbol={$researchResult?.primary_symbol ?? null}
            loading={$loading.iv}
            sessionLoading={$loading.ivSession}
            errorMessage={$ivError}
            onLoad={handleLoadIvSurface}
            onStopSession={stopIvSession}
            onSendToCopilot={handleSendToCopilot}
            onSendToStrategyLab={handleStrategyLabHandoff}
          />
        {/if}
      </section>
    </section>

    <CopilotResearchCard
      open={copilotOpen}
      available={copilotSurface.supported}
      contextLabel={copilotSurface.contextLabel}
      domainLabel={copilotSurface.domainLabel}
      guidance={copilotSurface.guidance}
      thread={copilotSurface.thread}
      loading={$loading.copilot}
      placeholder={copilotSurface.placeholder}
      scopeOptions={copilotSurface.scopeOptions}
      selectedScopeDomains={copilotSurface.selectedScopeDomains}
      selectionMessage={copilotSurface.selectionMessage}
      onGenerate={handleGenerateCopilot}
      onRunOperator={handleRunOperatorCopilot}
      onToggleScope={handleToggleSynthesisScope}
      onClose={() => copilotOpen = false}
    />
  </Shell>
{/if}

<style>
  .workspace-shell {
    display: grid;
    gap: var(--space-4);
  }

  .workspace-main {
    min-width: 0;
  }

  .view-load-state {
    display: grid;
    gap: var(--space-2);
    min-height: 12rem;
    align-content: center;
    padding: var(--space-6);
    border: 1px solid var(--panel-border);
    background: var(--surface-0);
    color: var(--text-2);
  }

  .view-load-state strong {
    color: var(--text-0);
    font-size: var(--text-base);
    font-weight: 600;
  }

  .view-load-state span {
    font-size: var(--text-sm);
  }
</style>
