<script lang="ts">
  import StrategyLabView from "../views/StrategyLabView.svelte";

  // Leaving Strategy Lab unmounts the view. The toggle reproduces that exactly:
  // the shell swaps the component out, and anything held in component state is
  // gone unless it lives somewhere the shell keeps (GUA-20260903-9).
  let mounted = true;
</script>

<button type="button" data-testid="toggle-mount" on:click={() => (mounted = !mounted)}>
  {mounted ? "Leave Strategy Lab" : "Return to Strategy Lab"}
</button>

{#if mounted}
  <StrategyLabView
    mode="composer"
    onAnalyzeStrategy={async () => null}
    onLoadSaved={async () => []}
    onSaveResearch={async () => null}
    onDeleteSaved={async () => false}
  />
{:else}
  <p data-testid="away">Away from Strategy Lab</p>
{/if}
