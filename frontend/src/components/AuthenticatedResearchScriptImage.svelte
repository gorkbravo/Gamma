<script lang="ts">
  import { onMount } from "svelte";

  import { fetchResearchScriptOutput } from "../lib/api/research-scripts";

  export let runId: string;
  export let outputId: string;
  export let alt = "Generated research chart";

  let source = "";
  let error = "";

  onMount(() => {
    let cancelled = false;
    let objectUrl = "";
    void fetchResearchScriptOutput(runId, outputId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        source = objectUrl;
      })
      .catch((reason) => {
        if (!cancelled) error = reason instanceof Error ? reason.message : String(reason);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  });
</script>

{#if source}
  <img src={source} {alt} />
{:else if error}
  <span class="image-state" role="alert">Retained image preview unavailable.</span>
{:else}
  <span class="image-state" role="status">Loading retained image…</span>
{/if}

<style>
  img {
    display: block;
    width: 100%;
    max-width: 100%;
    max-height: 28rem;
    object-fit: contain;
    border: 1px solid var(--divider);
    background: var(--surface-0);
  }

  .image-state {
    color: var(--text-3);
    font-size: var(--text-xs);
  }
</style>
