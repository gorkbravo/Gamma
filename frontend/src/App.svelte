<script lang="ts">
  import { onMount } from "svelte";
  import CopilotResearchCard from "./components/CopilotResearchCard.svelte";
  import LandingPage from "./components/LandingPage.svelte";
  import Shell from "./components/Shell.svelte";
  import StatusRail from "./components/StatusRail.svelte";
  import TabBar, { type TabBarItem } from "./components/TabBar.svelte";
  import MacroView from "./views/MacroView.svelte";
  import PortfolioView from "./views/PortfolioView.svelte";
  import CryptoView from "./views/CryptoView.svelte";
  import FundamentalsView from "./views/FundamentalsView.svelte";
  import PredictionMarketsView from "./views/PredictionMarketsView.svelte";
  import ResearchView from "./views/ResearchView.svelte";
  import RiskView from "./views/RiskView.svelte";
  import IvView from "./views/IvView.svelte";
  import { matchesActionKeybinding, isEditableEventTarget } from "./lib/keybindings";
  import { openKeyBindingsWindow } from "./lib/keybindings-window";
  import {
    getModeByShortcutIndex,
    getOrderedWorkspaceTabs,
    getTabByShortcutIndex,
    getWorkspaceHomeTab,
    isWorkspaceTab,
  } from "./lib/navigation";
  import { buildIvRequestFromResearch, buildRiskRequestFromResearch } from "./lib/workspace";
  import {
    activeTab,
    analyzeStrategyLab,
    diagnostics,
    diagnosticsLog,
    clearPortfolioHistory,
    copilotThreads,
    cryptoComparison,
    fundamentalsDcfModel,
    fundamentalsFinancials,
    fundamentalsOverview,
    fundamentalsSearch,
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
    ivSession,
    lastError,
    loadDiagnostics,
    loadIvSession,
    loadIvSurface,
    loadFundamentalsSearch,
    loadResearchOverview,
    loadSavedResearch,
    macroContext,
    loadMacroSeriesHistory,
    loadMacroWorkspace,
    loadPortfolioPerformance,
    loading,
    loadPortfolioSnapshot,
    loadCopilotResearchCard,
    macroDivergences,
    macroEvents,
    macroSeriesHistories,
    macroSnapshot,
    portfolioHistory,
    portfolioPerformance,
    portfolioSnapshot,
    predictionMarketCalibration,
    predictionMarketDetail,
    predictionMarketHistory,
    predictionMarketRelated,
    predictionMarketScreener,
    predictionMarketWallet,
    refreshSystemStatus,
    researchOverview,
    researchCompareResult,
    researchResult,
    riskResult,
    riskWorkspaceBasis,
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
    saveFundamentalsDcfModel,
    saveFundamentalsPeerBasket,
    savedResearchItems,
    selectedFundamentalsTicker,
    selectCryptoToken,
    selectFundamentalsCompany,
    selectPredictionMarket,
    setBaseCurrency,
    setMarketDataMode,
    startIvSession,
    strategyLabResult,
    stopIvSession,
    systemStatus,
    toggleConnection
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
    CopilotThreadState,
    CryptoComparison,
    CryptoDexLiquiditySummary,
    CryptoFlowSummary,
    CryptoPriceHistoryResponse,
    CryptoSyntheticPortfolio,
    CryptoToken,
    CryptoWorkspaceResponse,
    FundamentalsDcfModel,
    FundamentalsFinancials,
    FundamentalsOverview,
    FundamentalsSearchResponse,
    IvSessionStatus,
    IvSurface,
    MacroContextState,
    MacroSnapshot,
    PortfolioPerformanceResponse,
    PortfolioSnapshot,
    PredictionMarket,
    ResearchResult,
    RiskResult,
    SystemStatus,
    TabId,
    WorkspaceMode
  } from "./lib/api/types";
  import type { CryptoMode } from "./lib/view-models/crypto";
  import type { FundamentalsMode } from "./lib/view-models/fundamentals";
  import type { ResearchMode } from "./lib/view-models/research";

  type ConsoleEntry = {
    label: string;
    message: string;
    tone: "info" | "warning" | "error" | "action";
  };

  let pollHandle: ReturnType<typeof setInterval> | undefined;
  let ivPollHandle: ReturnType<typeof setInterval> | undefined;
  let workspaceMode: WorkspaceMode | null = null;
  let ivRequestedSymbol = "SPY";
  let ivPollingActive = false;
  let researchMode: ResearchMode = "overview";
  let cryptoMode: CryptoMode = "overview";
  let fundamentalsMode: FundamentalsMode = "overview";
  let consoleEntries: ConsoleEntry[] = [];
  let diagnosticsOpen = false;
  let sidebarOpen = false;
  let copilotOpen = false;
  let copilotMode: CopilotDrawerMode = "active_tab";
  let selectedSynthesisDomains: CopilotBaseDomain[] = [];
  let settingsOpen = false;
  let orderedTabs: ReturnType<typeof getOrderedWorkspaceTabs> = [];
  let tabBarTabs: TabBarItem[] = [];
  let synthesisScopeOptions: CopilotGroundingScopeOption[] = [];
  let activeTabCopilotSurface: CopilotSurfaceState;
  let synthesisCopilotSurface: CopilotSurfaceState;
  let copilotSurface: CopilotSurfaceState;

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
    research: $researchResult,
    macro: $macroContext,
    macroSnapshot: $macroSnapshot,
    prediction: $predictionMarketDetail,
    crypto: $cryptoTokenDetail,
    risk: $riskResult,
    riskWorkspace: $riskWorkspaceBasis,
    ivSurface: $ivSurface,
    ivSession: $ivSession,
  });
  $: {
    const availableDomains = synthesisScopeOptions.map((option) => option.domain);
    const filteredSelection = selectedSynthesisDomains.filter((domain) =>
      availableDomains.includes(domain)
    );
    const nextSelection = filteredSelection.length ? filteredSelection : availableDomains;
    const changed =
      nextSelection.length !== selectedSynthesisDomains.length ||
      nextSelection.some((domain, index) => domain !== selectedSynthesisDomains[index]);
    if (changed) {
      selectedSynthesisDomains = nextSelection;
    }
  }
  $: activeTabCopilotSurface = buildActiveTabCopilotSurface({
    tab: $activeTab,
    workspaceMode,
    threads: $copilotThreads,
    system: $systemStatus,
    portfolio: $portfolioSnapshot,
    portfolioPerformance: $portfolioPerformance,
    research: $researchResult,
    risk: $riskResult,
    riskWorkspace: $riskWorkspaceBasis,
    ivSurface: $ivSurface,
    ivSession: $ivSession,
    macro: $macroContext,
    prediction: $predictionMarketDetail,
    crypto: $cryptoTokenDetail,
    fundamentals: $fundamentalsOverview,
    fundamentalsTicker: $selectedFundamentalsTicker,
  });
  $: synthesisCopilotSurface = buildSynthesisCopilotSurface({
    activeTab: $activeTab,
    workspaceMode,
    threads: $copilotThreads,
    scopeOptions: synthesisScopeOptions,
    selectedDomains: selectedSynthesisDomains,
  });
  $: copilotSurface = copilotMode === "synthesis" ? synthesisCopilotSurface : activeTabCopilotSurface;

  type CopilotDrawerMode = "active_tab" | "synthesis";
  type CopilotGroundingScopeOption = {
    domain: CopilotBaseDomain;
    label: string;
    contextLabel: string;
    fingerprintLabel: string;
    freshnessLabel: string | null;
    warningLabel: string | null;
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

  const macroModeLabels: Record<MacroContextState["mode"], string> = {
    snapshot: "Snapshot",
    cross_asset: "Cross-Asset",
    rates_policy: "Rates & Policy",
    events_regimes: "Events / Regimes",
  };

  function describeMacroCopilotContext(context: MacroContextState) {
    return `Macro | ${context.region} | ${context.timeframe} | ${macroModeLabels[context.mode]}`;
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
        : `${snapshot.net_liquidation.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${baseCurrency}`;
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

  function describeRiskCopilotContext(result: RiskResult | null, mode: WorkspaceMode | null) {
    if (!result) {
      return "Risk | Run a risk pass to ground the Copilot";
    }
    const coverage = result.metrics.risk_coverage_ratio;
    const coverageLabel =
      coverage == null ? "coverage unknown" : `${(coverage * 100).toFixed(1)}% coverage`;
    return `Risk | ${mode === "research" ? "Research" : "Portfolio"} | ${coverageLabel}`;
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
      return "IV | Load a surface snapshot to ground the Copilot";
    }
    return `IV | ${activeSurface.symbol} | ${activeSurface.expiries.length} expiries x ${activeSurface.strikes.length} strikes`;
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

  function buildSynthesisScopeOptions({
    activeTab,
    workspaceMode,
    system,
    portfolio,
    portfolioPerformance,
    research,
    macro,
    macroSnapshot,
    prediction,
    crypto,
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
    research: ResearchResult | null;
    macro: MacroContextState;
    macroSnapshot: MacroSnapshot | null;
    prediction: PredictionMarket | null;
    crypto: CryptoToken | null;
    risk: RiskResult | null;
    riskWorkspace: WorkspaceMode | null;
    ivSurface: IvSurface | null;
    ivSession: IvSessionStatus | null;
  }): CopilotGroundingScopeOption[] {
    const options: CopilotGroundingScopeOption[] = [];
    const pushOption = (
      domain: CopilotBaseDomain,
      contextLabel: string,
      freshnessLabel: string | null,
      warningLabel: string | null
    ) => {
      const fingerprint = previewCopilotContextFingerprint(domain, { workspaceMode });
      options.push({
        domain,
        label:
          domain === "prediction_markets"
            ? "Prediction Markets"
            : domain === "macro"
              ? "Macro"
              : domain === "iv"
                ? "IV"
                : domain.charAt(0).toUpperCase() + domain.slice(1),
        contextLabel,
        fingerprintLabel: shortFingerprint(fingerprint),
        freshnessLabel,
        warningLabel
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

    return [...options].sort((left, right) => {
      if (left.domain === activeTab) {
        return -1;
      }
      if (right.domain === activeTab) {
        return 1;
      }
      return left.label.localeCompare(right.label);
    });
  }

  function buildActiveTabCopilotSurface({
    tab,
    workspaceMode,
    threads,
    system,
    portfolio,
    portfolioPerformance,
    research,
    risk,
    riskWorkspace,
    ivSurface,
    ivSession,
    macro,
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
    research: ResearchResult | null;
    risk: RiskResult | null;
    riskWorkspace: WorkspaceMode | null;
    ivSurface: IvSurface | null;
    ivSession: IvSessionStatus | null;
    macro: MacroContextState;
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

    if (tab === "research") {
      return {
        supported: research != null,
        domain: "research",
        triggerLabel: research ? "Research scope" : "Run analysis",
        contextLabel: describeResearchCopilotContext(research),
        domainLabel: "Research",
        guidance:
          research != null
            ? "Grounded in the active research run, including weights, coverage, benchmark overlap, and forwarded snapshot context."
            : "Run a research analysis before generating a research card from the research workspace.",
        placeholder:
          "Stress-test the active scope, sharpen the hypothesis, or identify the cleanest next comparison.",
        thread: threads.research,
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
        supported: false,
        domain: null,
        triggerLabel: "Coming later",
        contextLabel: describeFundamentalsCopilotContext(fundamentals, fundamentalsTicker),
        domainLabel: "Fundamentals",
        guidance:
          "The Fundamentals workspace is live, but Copilot grounding for filing-native fundamentals, peer baskets, and DCF state has not been wired yet.",
        placeholder:
          "Fundamentals Copilot grounding is intentionally disabled until the tab has a dedicated backend context.",
        thread: null,
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
        triggerLabel: ivAvailable ? "IV context" : "Load surface",
        contextLabel: describeIvCopilotContext(ivSurface, ivSession),
        domainLabel: "IV",
        guidance:
          ivAvailable
            ? "Grounded in the active IV surface and session state. Gamma remains read-only, so the Copilot should focus on surface interpretation, term structure, and caveats."
            : "Load an IV surface snapshot before generating a research card from the IV workspace.",
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
      selectedDomains.includes(option.domain)
    );
    const selectionFingerprint = previewCopilotThreadFingerprint("synthesis", {
      workspaceMode,
      synthesisDomains: selectedScopeOptions.map((option) => option.domain),
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
    const supported = selectedScopeOptions.length >= 2;
    const scopeSummary =
      selectedLabels.length > 0
        ? selectedLabels.length <= 3
          ? selectedLabels.join(" + ")
          : `${selectedLabels.slice(0, 3).join(" + ")} + ${selectedLabels.length - 3} more`
        : "Select loaded Gamma contexts";
    const selectionMessage =
      scopeChanged
        ? "The synthesis scope changed. Generating starts a new synthesis thread."
        : supported
          ? `${selectedScopeOptions.length} loaded contexts included in this synthesis.`
          : scopeOptions.length < 2
            ? "Load at least two Gamma contexts before generating a cross-context synthesis."
            : "Select at least two loaded Gamma contexts for synthesis.";

    return {
      supported,
      domain: "synthesis",
      triggerLabel: supported ? "Cross-context synthesis" : "Select scope",
      contextLabel: `Synthesis | ${scopeSummary}`,
      domainLabel: "Cross-Context Synthesis",
      guidance: supported
        ? "Grounded only in the selected Gamma contexts. Gamma remains read-only, and synthesis should preserve provenance, warnings, and domain-specific caveats."
        : selectionMessage,
      placeholder:
        "Synthesize the strongest agreement, contradiction, or next research test across the selected Gamma contexts.",
      thread: visibleThread,
      scopeOptions,
      selectedScopeDomains: selectedDomains,
      selectionMessage,
    };
  }

  onMount(() => {
    restoreWorkspaceTabOrders();
    void bootstrapApp();
    const handleGlobalKeydown = (event: KeyboardEvent) => {
      void handleAppKeydown(event);
    };
    window.addEventListener("keydown", handleGlobalKeydown);
    pollHandle = setInterval(() => {
      void refreshSystemStatus();
    }, 5000);
    return () => {
      window.removeEventListener("keydown", handleGlobalKeydown);
      if (pollHandle) {
        clearInterval(pollHandle);
      }
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
    const [status] = await Promise.all([refreshSystemStatus(), loadDiagnostics()]);
    if (status?.mock_mode || status?.connection.connected) {
      await loadPortfolioSnapshot();
    }
  }

  $: {
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
    } else if ($activeTab === "research") {
      push("Research", $researchResult?.warnings, "warning");
    } else if ($activeTab === "macro") {
      push("Macro", $macroSnapshot?.warnings, "warning");
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
    } else if ($activeTab === "risk") {
      push("Risk", $riskResult?.warnings, "warning");
    } else {
      push("IV", $ivSurface?.warnings, "warning");
      push("Session", $ivSession?.messages, "info");
      push("IV", $ivSurface?.messages, "info");
    }

    return entries;
  })();

  async function enterWorkspace(mode: WorkspaceMode) {
    workspaceMode = mode;
    copilotMode = "active_tab";
    sidebarOpen = false;
    copilotOpen = false;
    settingsOpen = false;
    activeTab.set(getWorkspaceHomeTab(mode));
    const tasks: Array<Promise<unknown>> = [loadDiagnostics()];
    if (mode === "portfolio" && ($systemStatus?.mock_mode || $systemStatus?.connection.connected)) {
      tasks.push(loadPortfolioSnapshot());
    }
    if (mode === "research") {
      researchMode = "overview";
      tasks.push(loadResearchOverview());
      tasks.push(loadSavedResearch());
    }
    await Promise.allSettled(tasks);
  }

  async function switchWorkspace(mode: WorkspaceMode) {
    if (workspaceMode === mode) {
      if (mode === "research") {
        researchMode = "overview";
      }
      activeTab.set(getWorkspaceHomeTab(mode));
      dismissSurfaces();
      return;
    }
    await enterWorkspace(mode);
  }

  async function selectTab(tab: TabId) {
    if (!workspaceMode) {
      return;
    }
    const primaryTab = getWorkspaceHomeTab(workspaceMode);
    const nextTab = isWorkspaceTab(workspaceMode, tab) ? tab : primaryTab;

    activeTab.set(nextTab);

    if (nextTab === "research") {
      researchMode = "overview";
      if (!$researchOverview) {
        await loadResearchOverview();
      }
      if (!$savedResearchItems.length) {
        await loadSavedResearch();
      }
    } else if (nextTab === "macro") {
      if (!$macroSnapshot) {
        await loadMacroWorkspace();
      }
    } else if (nextTab === "prediction_markets") {
      await loadPredictionMarketScreener();
    } else if (nextTab === "crypto") {
      await loadCryptoWorkspace();
    } else if (nextTab === "fundamentals") {
      await loadFundamentalsSearch({
        query: $selectedFundamentalsTicker ?? undefined
      });
    } else if (nextTab === "iv") {
      const autoLoaded = await loadResearchIvContext();
      if (!autoLoaded) {
        await loadIvSession();
      }
    }
  }

  async function openRiskFromResearch() {
    const request = buildRiskRequestFromResearch($researchResult);
    if (!request) {
      return;
    }
    activeTab.set("risk");
    await computeRisk(request);
  }

  async function openIvFromResearch() {
    activeTab.set("iv");
    const autoLoaded = await loadResearchIvContext();
    if (!autoLoaded) {
      await loadIvSession();
    }
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
    await Promise.allSettled([refreshSystemStatus(), loadDiagnostics()]);

    if (workspaceMode === "portfolio" && ($activeTab === "portfolio" || $activeTab === "risk")) {
      await loadPortfolioSnapshot();
    }

    if ($activeTab === "research" && researchMode === "overview") {
      await loadResearchOverview({ forceRefresh: true });
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

    if ($activeTab === "macro") {
      await loadMacroWorkspace({ forceRefresh: true });
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
    copilotMode = "active_tab";
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
    if (ivPollHandle) {
      return;
    }
    ivPollHandle = setInterval(() => {
      void loadIvSession();
    }, 1500);
  }

  function stopIvPolling() {
    if (ivPollHandle) {
      clearInterval(ivPollHandle);
      ivPollHandle = undefined;
    }
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
    }
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

  function handleSetCopilotMode(nextMode: CopilotDrawerMode) {
    copilotMode = nextMode;
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

  async function handleGenerateCopilot(prompt = "") {
    if (!copilotSurface.supported || !copilotSurface.domain) {
      return null;
    }
    return loadCopilotResearchCard(copilotSurface.domain, prompt, {
      workspaceMode,
      synthesisDomains:
        copilotSurface.domain === "synthesis" ? selectedSynthesisDomains : undefined,
      activeTabId: $activeTab,
    });
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

    if ($activeTab === "research") {
      researchMode = nextMode.id as ResearchMode;
      if (researchMode === "overview" && !$researchOverview) {
        await loadResearchOverview();
      }
      if (researchMode === "saved_research") {
        await loadSavedResearch();
      }
      return true;
    }

    if ($activeTab === "macro") {
      await loadMacroWorkspace({ mode: nextMode.id as MacroContextState["mode"] });
      return true;
    }

    if ($activeTab === "crypto") {
      cryptoMode = nextMode.id as CryptoMode;
      return true;
    }

    if ($activeTab === "fundamentals") {
      fundamentalsMode = nextMode.id as FundamentalsMode;
      return true;
    }

    return false;
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
    tabs={tabBarTabs}
    copilotOpen={copilotOpen}
    onSelectTab={selectTab}
    onToggleCopilot={handleToggleCopilot}
    onToggleSidebar={handleToggleSidebar}
  >
    <svelte:fragment slot="status">
      <StatusRail
        status={$systemStatus}
        workspaceMode={workspaceMode}
        busy={$loading.status || $loading.diagnostics || $loading.portfolio || $loading.ivSession}
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
        {#if $activeTab === "portfolio"}
          <PortfolioView
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
        {:else if $activeTab === "research"}
          <ResearchView
            bind:mode={researchMode}
            overview={$researchOverview}
            result={$researchResult}
            strategyResult={$strategyLabResult}
            compareResult={$researchCompareResult}
            savedItems={$savedResearchItems}
            loading={$loading.research}
            overviewLoading={$loading.researchOverview}
            strategyLoading={$loading.strategyLab}
            compareLoading={$loading.compareScenario}
            savedLoading={$loading.savedResearch}
            onLoadOverview={loadResearchOverview}
            onRun={runResearch}
            onAnalyzeStrategy={analyzeStrategyLab}
            onCompare={compareResearch}
            onLoadSaved={loadSavedResearch}
            onSaveResearch={saveResearchItem}
            onDeleteSaved={deleteSavedResearchItem}
            onRestoreStrategy={restoreStrategyLabResult}
            onOpenRisk={openRiskFromResearch}
            onOpenIv={openIvFromResearch}
          />
        {:else if $activeTab === "macro"}
          <MacroView
            snapshot={$macroSnapshot}
            divergences={$macroDivergences}
            events={$macroEvents}
            histories={$macroSeriesHistories}
            loading={$loading.macro || $loading.macroHistory}
            onLoadWorkspace={loadMacroWorkspace}
            onLoadSeries={loadMacroSeriesHistory}
          />
        {:else if $activeTab === "prediction_markets"}
          <PredictionMarketsView
            screener={$predictionMarketScreener}
            detail={$predictionMarketDetail}
            history={$predictionMarketHistory}
            wallet={$predictionMarketWallet}
            related={$predictionMarketRelated}
            calibration={$predictionMarketCalibration}
            loading={$loading.prediction || $loading.predictionDetail}
            onLoadScreener={loadPredictionMarketScreener}
            onSelectMarket={selectPredictionMarket}
          />
        {:else if $activeTab === "crypto"}
          <CryptoView
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
          <FundamentalsView
            bind:mode={fundamentalsMode}
            search={$fundamentalsSearch}
            selectedTicker={$selectedFundamentalsTicker}
            overview={$fundamentalsOverview}
            financials={$fundamentalsFinancials}
            dcfModel={$fundamentalsDcfModel}
            loading={$loading.fundamentals}
            saving={$loading.fundamentalsSave}
            onSearch={loadFundamentalsSearch}
            onSelectCompany={selectFundamentalsCompany}
            onSavePeerBasket={saveFundamentalsPeerBasket}
            onSaveDcfModel={saveFundamentalsDcfModel}
          />
        {:else if $activeTab === "risk"}
          <RiskView
            mode={workspaceMode}
            snapshot={$portfolioSnapshot}
            researchSnapshot={$researchResult?.snapshot ?? null}
            result={$riskResult}
            loading={$loading.risk}
            onCompute={computeRisk}
          />
        {:else}
          <IvView
            status={$systemStatus}
            requestedSymbol={ivRequestedSymbol}
            result={$ivSurface}
            session={$ivSession}
            loading={$loading.iv}
            sessionLoading={$loading.ivSession}
            onLoad={loadIvSurface}
            onStartSession={startIvSession}
            onStopSession={stopIvSession}
            onRefreshSession={loadIvSession}
          />
        {/if}
      </section>
    </section>

    <CopilotResearchCard
      open={copilotOpen}
      available={copilotSurface.supported}
      mode={copilotMode}
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
      onSetMode={handleSetCopilotMode}
      onToggleScope={handleToggleSynthesisScope}
      onClose={() => copilotOpen = false}
    />
  </Shell>
{/if}

<style>
  .workspace-shell {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-main {
    min-width: 0;
  }
</style>
