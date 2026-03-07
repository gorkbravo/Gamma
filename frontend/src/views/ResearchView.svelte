<script lang="ts">
  import type { ResearchResult } from "../lib/api/types";

  export let result: ResearchResult | null = null;
  export let loading = false;
  export let onRun: (symbol: string, benchmarkSymbol: string) => void;

  let symbol = "AAPL";
  let benchmarkSymbol = "MSFT";

  const pct = (value: number | null | undefined) => (value == null ? "N/A" : `${(value * 100).toFixed(2)}%`);
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Research Shell</h2>
      <p>Single-name research is already wired through the extracted Python service.</p>
    </div>
    <form class="form" on:submit|preventDefault={() => onRun(symbol, benchmarkSymbol)}>
      <input bind:value={symbol} placeholder="Ticker" />
      <input bind:value={benchmarkSymbol} placeholder="Benchmark" />
      <button disabled={loading}>{loading ? "Running..." : "Run Analysis"}</button>
    </form>
  </div>

  <div class="grid">
    <article class="panel"><span>Total Return</span><strong>{pct(result?.summary.total_return)}</strong></article>
    <article class="panel"><span>Annual Return</span><strong>{pct(result?.summary.annual_return)}</strong></article>
    <article class="panel"><span>Annual Vol</span><strong>{pct(result?.summary.annual_vol)}</strong></article>
    <article class="panel"><span>Max Drawdown</span><strong>{pct(result?.summary.max_drawdown)}</strong></article>
  </div>

  <div class="split">
    <article class="panel">
      <h3>Weights</h3>
      {#if result?.weights?.length}
        {#each result.weights as weight}
          <div class="row">
            <span>{weight.symbol}</span>
            <strong>{pct(weight.weight)}</strong>
          </div>
        {/each}
      {:else}
        <p class="muted">Run a research analysis to populate the view.</p>
      {/if}
    </article>

    <article class="panel">
      <h3>Warnings</h3>
      {#if result?.warnings?.length}
        {#each result.warnings as warning}
          <p class="warning">{warning}</p>
        {/each}
      {:else}
        <p class="muted">No warnings.</p>
      {/if}
    </article>
  </div>
</section>

<style>
  .toolbar,
  .grid,
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

  .grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin-top: 1rem;
  }

  .split {
    grid-template-columns: 1fr 1fr;
    margin-top: 1rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: rgba(6, 9, 13, 0.96);
    padding: 1rem;
  }

  span,
  .muted {
    color: var(--text-2);
  }

  strong {
    display: block;
    margin-top: 0.35rem;
  }

  .row {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid #13202c;
  }

  .warning {
    color: var(--warning);
    border-bottom: 1px solid #13202c;
    padding-bottom: 0.6rem;
    margin-bottom: 0.6rem;
  }

  @media (max-width: 900px) {
    .toolbar,
    .grid,
    .split {
      grid-template-columns: 1fr;
    }

    .form {
      flex-direction: column;
    }
  }
</style>
