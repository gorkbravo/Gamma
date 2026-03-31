<script lang="ts">
  import { onMount } from "svelte";
  import LandingPage from "./components/LandingPage.svelte";
  import Shell from "./components/Shell.svelte";
  import StatusRail from "./components/StatusRail.svelte";
  import TabBar, { type TabBarItem } from "./components/TabBar.svelte";
  import MacroView from "./views/MacroView.svelte";
  import PortfolioView from "./views/PortfolioView.svelte";
  import PredictionMarketsView from "./views/PredictionMarketsView.svelte";
  import ResearchView from "./views/ResearchView.svelte";
  import RiskView from "./views/RiskView.svelte";
  import IvView from "./views/IvView.svelte";
  import { matchesActionKeybinding, isEditableEventTarget } from "./lib/keybindings";
  import { openKeyBindingsWindow } from "./lib/keybindings-window";
  import {
    getOrderedWorkspaceTabs,
    getTabByShortcutIndex,
    getTabLabel,
    getWorkspaceHomeTab,
    isWorkspaceTab,
  } from "./lib/navigation";
  import { buildIvRequestFromResearch, buildRiskRequestFromResearch } from "./lib/workspace";
  import {
    activeTab,
    diagnostics,
    diagnosticsLog,
    clearPortfolioHistory,
    computeRisk,
    forceAccountSubscribe,
    ivSurface,
    ivSession,
    lastError,
    loadDiagnostics,
    loadIvSession,
    loadIvSurface,
    loadMacroSeriesHistory,
    loadMacroWorkspace,
    loadPortfolioPerformance,
    loading,
    loadPortfolioSnapshot,
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
    researchResult,
    riskResult,
    loadPredictionMarketScreener,
    runDiagnosticsAction,
    runResearch,
    selectPredictionMarket,
    setBaseCurrency,
    setMarketDataMode,
    startIvSession,
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
  import type { TabId, WorkspaceMode } from "./lib/api/types";

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
  let consoleEntries: ConsoleEntry[] = [];
  let diagnosticsOpen = false;
  let sidebarOpen = false;
  let settingsOpen = false;
  let activeViewLabel = "";
  let orderedTabs: ReturnType<typeof getOrderedWorkspaceTabs> = [];
  let tabBarTabs: TabBarItem[] = [];

  $: activeViewLabel = getTabLabel($activeTab);
  $: orderedTabs =
    workspaceMode == null
      ? []
      : getOrderedWorkspaceTabs(workspaceMode, $workspaceTabOrders);
  $: tabBarTabs = orderedTabs.map<TabBarItem>((tab) => ({
    id: tab.id,
    label: tab.label,
    pinned: tab.pinned,
  }));

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
    sidebarOpen = false;
    settingsOpen = false;
    activeTab.set(getWorkspaceHomeTab(mode));
    const tasks: Array<Promise<unknown>> = [loadDiagnostics()];
    if (mode === "portfolio" && ($systemStatus?.mock_mode || $systemStatus?.connection.connected)) {
      tasks.push(loadPortfolioSnapshot());
    }
    await Promise.allSettled(tasks);
  }

  async function switchWorkspace(mode: WorkspaceMode) {
    if (workspaceMode === mode) {
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

    if (nextTab === "macro") {
      if (!$macroSnapshot) {
        await loadMacroWorkspace();
      }
    } else if (nextTab === "prediction_markets") {
      await loadPredictionMarketScreener();
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

    if ($activeTab === "prediction_markets") {
      await loadPredictionMarketScreener({ forceRefresh: true });
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
    diagnosticsOpen = false;
    sidebarOpen = false;
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
    sidebarOpen = !sidebarOpen;
    if (sidebarOpen) {
      settingsOpen = false;
    }
  }

  function handleToggleSettings() {
    settingsOpen = !settingsOpen;
    if (settingsOpen) {
      sidebarOpen = false;
    }
  }

  function dismissSurfaces() {
    sidebarOpen = false;
    settingsOpen = false;
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

  async function handleAppKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented) {
      return;
    }

    const hasDismissibleSurface = sidebarOpen || settingsOpen;
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

    if (
      workspaceMode != null &&
      event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey &&
      !event.metaKey &&
      /^[1-9]$/.test(event.key)
    ) {
      const nextTab = getTabByShortcutIndex(workspaceMode, $workspaceTabOrders, Number(event.key));
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
  <Shell activeViewLabel={activeViewLabel} onToggleSidebar={handleToggleSidebar}>
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
            result={$researchResult}
            loading={$loading.research}
            onRun={runResearch}
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
  </Shell>
{/if}

<style>
  .workspace-shell {
    display: grid;
    gap: 0.65rem;
  }

  .workspace-main {
    min-width: 0;
  }
</style>
