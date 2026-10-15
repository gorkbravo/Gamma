<script lang="ts">
  import StrategyLabView from "../views/StrategyLabView.svelte";
  import { strategyLabResult, restoreStrategyLabResult, loadSavedResearch, saveResearchItem, deleteSavedResearchItem, savedResearchItems } from "../lib/stores/app";
  import type { StrategyLabMode } from "../lib/view-models/research";
  let mode: StrategyLabMode = "script";
</script>
<StrategyLabView bind:mode strategyResult={$strategyLabResult} savedItems={$savedResearchItems}
  onAnalyzeStrategy={async () => null} onRestoreStrategy={restoreStrategyLabResult}
  onLoadSaved={loadSavedResearch} onSaveResearch={saveResearchItem} onDeleteSaved={deleteSavedResearchItem} />
<style>
  :global(body) { margin: 0; color: var(--text-0); background: var(--bg-0); }
  :global(#app) { padding: var(--space-4); }
</style>
