<script lang="ts">
  import { onMount } from "svelte";
  import type { CopilotWorkingAnalysis } from "../lib/api/types";
  import { retainedEvidenceTarget, evidenceLabel, evidenceSections } from "../lib/retained-evidence";
  import RetainedEvidenceTable from "./RetainedEvidenceTable.svelte";
  export let analysis: CopilotWorkingAnalysis;
  export let onClose: () => void = () => {};
  let now = Date.now();
  onMount(() => { const timer = setInterval(() => { now = Date.now(); }, 1000); return () => clearInterval(timer); });
  $: available = retainedEvidenceTarget(analysis, now) !== null;
</script>
<article class="panel" aria-label="Temporary research evidence">
  <header><div><p class="eyebrow">TEMPORARY · {evidenceLabel(analysis.owning_tab)}</p><h2>{analysis.title}</h2></div>
    <button type="button" class="btn" on:click={onClose}>Return to workspace</button></header>
  {#if available}
    <p class="meta">Retained result · {analysis.source_provider} · Expires {analysis.expires_at}</p>
    {#each analysis.warnings as warning}<p class="note">{warning}</p>{/each}
    {#each evidenceSections(analysis) as section}<section><h3>{section.title}</h3><RetainedEvidenceTable value={section.value} /></section>{/each}
    <details><summary>Inputs and assumptions</summary><RetainedEvidenceTable value={analysis.inputs} /></details>
    <details><summary>Sources and method</summary><p class="meta">{analysis.transformation_note}</p><RetainedEvidenceTable value={analysis.outputs.sources} />
      <details><summary>Complete retained evidence</summary><RetainedEvidenceTable value={analysis.outputs.result} /></details>
    </details>
  {:else}
    <p class="note" role="status">This temporary result is expired or unavailable. Return to the workspace or run a new analysis.</p>
  {/if}
</article>
<style>
  article { min-width: 0; overflow: auto; }
  header { display: flex; gap: var(--space-4); justify-content: space-between; align-items: center; flex-wrap: wrap; padding: var(--space-5); }
  h2, p { margin: 0; } h2 { font: 600 var(--text-lg) var(--font-ui); }
  h3 { margin: 0; padding: var(--space-4) var(--space-5); border-top: 1px solid var(--divider); font: 600 var(--text-sm) var(--font-ui); }
  .meta, .note { padding: var(--space-3) var(--space-5); font-size: var(--text-xs); overflow-wrap: anywhere; }
  .meta { color: var(--text-2); }
  summary { padding: var(--space-4) var(--space-5); font: var(--text-sm) var(--font-ui); cursor: pointer; border-top: 1px solid var(--divider); }
  summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
</style>
