<script lang="ts">
  import type { IvSurface } from "../lib/api/types";

  export let result: IvSurface | null = null;
  export let loading = false;
  export let onLoad: (symbol: string) => void;

  let symbol = "SPY";
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>IV Shell</h2>
      <p>Polling-friendly IV surface endpoint. The browser shell stays 2D for now.</p>
    </div>
    <form class="form" on:submit|preventDefault={() => onLoad(symbol)}>
      <input bind:value={symbol} placeholder="SPY" />
      <button disabled={loading}>{loading ? "Loading..." : "Load Surface"}</button>
    </form>
  </div>

  <div class="split">
    <article class="panel">
      <h3>Surface Meta</h3>
      <div class="row"><span>Available</span><strong>{result?.snapshot_available ? "Yes" : "No"}</strong></div>
      <div class="row"><span>Spot</span><strong>{result?.spot ?? "N/A"}</strong></div>
      <div class="row"><span>Points</span><strong>{result?.points ?? 0}</strong></div>
      <div class="row"><span>Delayed</span><strong>{result?.delayed == null ? "N/A" : result.delayed ? "Yes" : "No"}</strong></div>
    </article>

    <article class="panel">
      <h3>Expiry Grid Preview</h3>
      {#if result?.expiries?.length}
        <div class="heatmap">
          {#each result.expiries as expiry, rowIndex}
            <div class="expiry">{expiry}</div>
            {#each result.iv_grid[rowIndex].slice(0, 6) as cell}
              <div class="cell" style={`opacity:${Math.min(Math.max(cell / 0.6, 0.2), 1)}`}>{cell.toFixed(2)}</div>
            {/each}
          {/each}
        </div>
      {:else}
        <p class="muted">No IV payload loaded yet.</p>
      {/if}
    </article>
  </div>
</section>

<style>
  .toolbar,
  .split {
    display: grid;
    gap: 0.85rem;
  }

  .toolbar {
    grid-template-columns: 1fr auto;
    align-items: start;
  }

  .form {
    display: flex;
    gap: 0.55rem;
  }

  input {
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.65rem 0.75rem;
    width: 8rem;
  }

  .split {
    grid-template-columns: 0.9fr 1.6fr;
    margin-top: 1rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: rgba(6, 9, 13, 0.96);
    padding: 1rem;
  }

  .row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid #13202c;
  }

  .row span,
  .muted {
    color: var(--text-2);
  }

  .heatmap {
    display: grid;
    grid-template-columns: 8rem repeat(6, minmax(3.3rem, 1fr));
    gap: 0.35rem;
  }

  .expiry,
  .cell {
    padding: 0.55rem 0.45rem;
    border: 1px solid #13202c;
    background: var(--bg-2);
  }

  .cell {
    text-align: center;
    background: rgba(106, 168, 255, 0.28);
  }

  @media (max-width: 900px) {
    .toolbar,
    .split {
      grid-template-columns: 1fr;
    }

    .form {
      flex-direction: column;
    }
  }
</style>
