<script lang="ts">
  import { get } from "svelte/store";
  import StrategyLabView from "../views/StrategyLabView.svelte";
  import RiskView from "../views/RiskView.svelte";
  import { composeStrategyLabPortfolio, validateStrategyLabPortfolio, saveResearchItem, loadSavedResearch,
    deleteSavedResearchItem, restoreStrategyLabComposition, restoreStrategyLabResult, computeRisk,
    strategyLabComposition, strategyLabCompositionStale, strategyLabResult, strategyLabResearchBook, savedResearchItems, loading, lastError,
    riskResult, strategyComposerDraft } from "../lib/stores/app";
  import { buildStrategyLabRiskRequest } from "../lib/risk-handoff";
  import type { StrategyLabMode } from "../lib/view-models/research";
  import type { GammaResearchObject } from "../lib/api/types";
  let mode: StrategyLabMode = "composer", risk = false;
  const fixture = new URLSearchParams(location.search).has("fixture");
  const points = Array.from({ length: 260 }, (_, i) => ({ timestamp: new Date(Date.UTC(2025, 0, 1 + i)).toISOString(), value: 0.002 + (i % 7 - 3) * 0.001 }));
  const benchmark: GammaResearchObject = { object_id: "fixture-spy", object_type: "history", display_name: "SPY", source_tab: "strategy_lab",
    symbols: ["SPY"], constituents: [], weights: [], resolver_capabilities: ["benchmark"], warnings: [],
    provenance: { source_provider: "fixture" }, return_points: points.map(p => ({ ...p, value: p.value * 0.6 })) };
  strategyComposerDraft.update((draft) => ({ ...draft, legs: draft.legs.slice(0, 2).map((leg, i) => ({ ...leg, weight: i ? -1 : 1 })),
    lookbackDays: 260, minObservations: 60 }));
  if (fixture) strategyComposerDraft.update(draft => ({ ...draft, benchmarkObject: benchmark,
    legs: draft.legs.map((leg, i) => ({ ...leg, historyText: ["date,value", ...points.map(p => `${p.timestamp},${p.value * (i ? 0.6 : 1)}`)].join("\n") })) }));
  async function openRisk() {
    const book = get(strategyLabResearchBook);
    if (!book) throw new Error("No composed research book");
    risk = true;
    await computeRisk(buildStrategyLabRiskRequest(book));
  }
</script>
<button on:click={() => risk = !risk} data-testid="switch-view">{risk ? "Return to Strategy Lab" : "Show Risk"}</button>
{#if risk}
  <RiskView mode="research" strategyLabResearchBook={$strategyLabResearchBook} result={$riskResult}
    loading={$loading.risk} onCompute={async (options) => { await computeRisk(options); }} />
{:else}
  <StrategyLabView bind:mode strategyComposition={$strategyLabComposition} compositionStaleMessage={$strategyLabCompositionStale ?? ""} strategyResult={$strategyLabResult}
    savedItems={$savedResearchItems} strategyLoading={$loading.strategyLab} savedLoading={$loading.savedResearch}
    errorMessage={$lastError} onComposePortfolioStrategy={composeStrategyLabPortfolio}
    onValidatePortfolioStrategy={validateStrategyLabPortfolio} onAnalyzeStrategy={async () => null}
    onSaveResearch={saveResearchItem} onLoadSaved={loadSavedResearch} onDeleteSaved={deleteSavedResearchItem}
    onRestoreComposition={restoreStrategyLabComposition} onRestoreStrategy={restoreStrategyLabResult} onOpenRisk={openRisk} />
{/if}
<style>:global(body) { margin: 0; background: var(--bg-0); color: var(--text-0); font-family: var(--font-ui); } :global(#app) { padding: 12px; }</style>
