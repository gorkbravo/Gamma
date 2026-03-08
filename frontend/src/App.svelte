<script lang="ts">
  import { onMount } from "svelte";
  import DiagnosticsPanel from "./components/DiagnosticsPanel.svelte";
  import LandingPage from "./components/LandingPage.svelte";
  import Shell from "./components/Shell.svelte";
  import StatusRail from "./components/StatusRail.svelte";
  import TabBar from "./components/TabBar.svelte";
  import PortfolioView from "./views/PortfolioView.svelte";
  import ResearchView from "./views/ResearchView.svelte";
  import RiskView from "./views/RiskView.svelte";
  import IvView from "./views/IvView.svelte";
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
    loadPortfolioPerformance,
    loading,
    loadPortfolioSnapshot,
    portfolioHistory,
    portfolioPerformance,
    portfolioSnapshot,
    refreshSystemStatus,
    researchResult,
    riskResult,
    runDiagnosticsAction,
    runResearch,
    setMarketDataMode,
    startIvSession,
    stopIvSession,
    systemStatus,
    toggleConnection
  } from "./lib/stores/app";
  import type { TabId, WorkspaceMode } from "./lib/api/types";

  let pollHandle: ReturnType<typeof setInterval> | undefined;
  let ivPollHandle: ReturnType<typeof setInterval> | undefined;
  let diagnosticsOpen = false;
  let workspaceMode: WorkspaceMode | null = null;
  let ivRequestedSymbol = "SPY";
  let ivPollingActive = false;

  onMount(() => {
    void bootstrapApp();
    pollHandle = setInterval(() => {
      void refreshSystemStatus();
    }, 5000);
    return () => {
      if (pollHandle) {
        clearInterval(pollHandle);
      }
      stopIvPolling();
    };
  });

  async function bootstrapApp() {
    const status = await refreshSystemStatus();
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

  async function enterWorkspace(mode: WorkspaceMode) {
    workspaceMode = mode;
    activeTab.set(mode === "portfolio" ? "portfolio" : "research");
    if (mode === "portfolio" && ($systemStatus?.mock_mode || $systemStatus?.connection.connected)) {
      await loadPortfolioSnapshot();
    }
  }

  function returnToLanding() {
    workspaceMode = null;
    diagnosticsOpen = false;
    activeTab.set("portfolio");
  }

  async function selectTab(tab: TabId) {
    if (!workspaceMode) {
      return;
    }
    const primaryTab = workspaceMode === "portfolio" ? "portfolio" : "research";
    const nextTab = tab === "risk" || tab === "iv" ? tab : primaryTab;

    activeTab.set(nextTab);

    if (nextTab === "iv") {
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
    if (diagnosticsOpen) {
      await loadDiagnostics();
    }
    if (workspaceMode != null && $activeTab === "iv") {
      await loadIvSession();
    }
  }

  async function handleMarketDataModeChange(mode: string) {
    await setMarketDataMode(mode);
    if (diagnosticsOpen) {
      await loadDiagnostics();
    }
    if (workspaceMode != null && $activeTab === "iv") {
      await loadIvSession();
    }
  }

  async function toggleDiagnostics() {
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
</script>

<Shell
  subtitle={workspaceMode == null
    ? "Select a workspace mode before entering the analytics shell."
    : workspaceMode === "portfolio"
      ? "Portfolio view keeps the live account snapshot as the primary context."
      : "Research view forwards your active research context into downstream analytics."}
>
  {#if workspaceMode == null}
    <LandingPage
      status={$systemStatus}
      busy={$loading.status}
      onConnect={handleConnectionToggle}
      onEnterPortfolio={() => enterWorkspace("portfolio")}
      onEnterResearch={() => enterWorkspace("research")}
    />
  {:else}
    <StatusRail
      status={$systemStatus}
      activeTab={$activeTab}
      workspaceMode={workspaceMode}
      lastError={$lastError}
      busy={$loading.status}
      diagnosticsOpen={diagnosticsOpen}
      onToggleConnection={handleConnectionToggle}
      onMarketDataModeChange={handleMarketDataModeChange}
      onToggleDiagnostics={toggleDiagnostics}
    />
    {#if diagnosticsOpen}
      <DiagnosticsPanel
        diagnostics={$diagnostics}
        loading={$loading.diagnostics}
        actionLoading={$loading.diagnosticsAction || $loading.portfolioAction}
        log={$diagnosticsLog}
        onRefresh={loadDiagnostics}
        onRunDiagnostics={handleRunDiagnostics}
        onForceSubscribe={handleForceSubscribe}
        onClearHistory={handleClearHistory}
      />
    {/if}
    <TabBar
      activeTab={$activeTab}
      mode={workspaceMode}
      onSelect={selectTab}
      onSwitchWorkspace={returnToLanding}
    />

    {#if $activeTab === "portfolio"}
      <PortfolioView
        snapshot={$portfolioSnapshot}
        history={$portfolioHistory}
        performance={$portfolioPerformance}
        loading={$loading.portfolio}
        onRefresh={loadPortfolioSnapshot}
        onReloadPerformance={loadPortfolioPerformance}
      />
    {:else if $activeTab === "research"}
      <ResearchView
        result={$researchResult}
        loading={$loading.research}
        onRun={runResearch}
        onOpenRisk={openRiskFromResearch}
        onOpenIv={openIvFromResearch}
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
  {/if}
</Shell>
