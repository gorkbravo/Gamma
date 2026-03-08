<script lang="ts">
  import { onMount } from "svelte";
  import DiagnosticsPanel from "./components/DiagnosticsPanel.svelte";
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
    setMarketDataMode,
    startIvSession,
    stopIvSession,
    toggleConnection,
    runResearch,
    systemStatus
  } from "./lib/stores/app";
  import type { TabId } from "./lib/api/types";

  let pollHandle: ReturnType<typeof setInterval> | undefined;
  let ivPollHandle: ReturnType<typeof setInterval> | undefined;
  let diagnosticsOpen = false;
  let riskSnapshotPreference: "portfolio" | "research" = "portfolio";
  let ivRequestedSymbol = "SPY";
  let ivPollingActive = false;

  onMount(() => {
    void refreshSystemStatus();
    void loadPortfolioSnapshot();
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

  $: {
    const shouldPollIv = $activeTab === "iv";
    if (shouldPollIv && !ivPollingActive) {
      ivPollingActive = true;
      void loadIvSession();
      startIvPolling();
    } else if (!shouldPollIv && ivPollingActive) {
      ivPollingActive = false;
      stopIvPolling();
    }
  }

  function selectTab(tab: TabId) {
    if (tab === "risk") {
      riskSnapshotPreference = "portfolio";
    }
    if (tab === "iv") {
      void loadIvSession();
    }
    activeTab.set(tab);
  }

  async function openRiskFromResearch() {
    const request = buildRiskRequestFromResearch($researchResult);
    if (!request) {
      return;
    }
    riskSnapshotPreference = "research";
    activeTab.set("risk");
    await computeRisk(request);
  }

  async function openIvFromResearch() {
    const request = buildIvRequestFromResearch($researchResult, $systemStatus?.market_data_mode);
    if (!request) {
      return;
    }
    ivRequestedSymbol = request.symbol;
    activeTab.set("iv");
    await loadIvSurface(request);
    await loadIvSession();
  }

  async function handleConnectionToggle() {
    await toggleConnection();
    if (diagnosticsOpen) {
      await loadDiagnostics();
    }
    if ($activeTab === "iv") {
      await loadIvSession();
    }
  }

  async function handleMarketDataModeChange(mode: string) {
    await setMarketDataMode(mode);
    if (diagnosticsOpen) {
      await loadDiagnostics();
    }
    if ($activeTab === "iv") {
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

<Shell>
  <StatusRail
    status={$systemStatus}
    activeTab={$activeTab}
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
  <TabBar activeTab={$activeTab} onSelect={selectTab} />

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
      snapshot={$portfolioSnapshot}
      researchSnapshot={$researchResult?.snapshot ?? null}
      preferredSnapshotSource={riskSnapshotPreference}
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
</Shell>
