<script lang="ts">
  import { onMount } from "svelte";
  import Shell from "./components/Shell.svelte";
  import StatusRail from "./components/StatusRail.svelte";
  import TabBar from "./components/TabBar.svelte";
  import PortfolioView from "./views/PortfolioView.svelte";
  import ResearchView from "./views/ResearchView.svelte";
  import RiskView from "./views/RiskView.svelte";
  import IvView from "./views/IvView.svelte";
  import {
    activeTab,
    computeRiskFromLatestSnapshot,
    ivSurface,
    lastError,
    loadIvSurface,
    loading,
    loadPortfolioSnapshot,
    portfolioHistory,
    portfolioSnapshot,
    refreshSystemStatus,
    researchResult,
    riskResult,
    runSingleTickerResearch,
    systemStatus
  } from "./lib/stores/app";
  import type { TabId } from "./lib/api/types";

  let pollHandle: ReturnType<typeof setInterval> | undefined;

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
    };
  });

  function selectTab(tab: TabId) {
    activeTab.set(tab);
  }
</script>

<Shell>
  <StatusRail status={$systemStatus} activeTab={$activeTab} lastError={$lastError} />
  <TabBar activeTab={$activeTab} onSelect={selectTab} />

  {#if $activeTab === "portfolio"}
    <PortfolioView
      snapshot={$portfolioSnapshot}
      history={$portfolioHistory}
      loading={$loading.portfolio}
      onRefresh={loadPortfolioSnapshot}
    />
  {:else if $activeTab === "research"}
    <ResearchView result={$researchResult} loading={$loading.research} onRun={runSingleTickerResearch} />
  {:else if $activeTab === "risk"}
    <RiskView
      snapshot={$portfolioSnapshot}
      result={$riskResult}
      loading={$loading.risk}
      onCompute={computeRiskFromLatestSnapshot}
    />
  {:else}
    <IvView result={$ivSurface} loading={$loading.iv} onLoad={loadIvSurface} />
  {/if}
</Shell>
