<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import type { CopilotWorkingAnalysis } from "../lib/api/types";
  import { researchBasketSnapshot, researchScopeTime } from "../lib/research-working-analysis";
  export let analysis: CopilotWorkingAnalysis;
  export let onClose: () => void = () => {};
  let now = Date.now();
  onMount(() => { const timer = setInterval(() => { now = Date.now(); }, 1000); return () => clearInterval(timer); });
  $: snapshot = researchBasketSnapshot(analysis, now);
  $: series = snapshot ? [
    { id: "basket", label: "Research basket", color: "var(--accent)", data: snapshot.performance },
    { id: "benchmark", label: snapshot.benchmark, color: "var(--text-2)", data: snapshot.benchmarkPoints }
  ] as ChartSeries[] : [];
  const percent = (n: unknown) => typeof n === "number" && Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "N/A";
  const timestamp = (value: string) => new Date(researchScopeTime(value)).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
</script>

<article class="panel retained-scope" aria-label="Temporary Research scope">
  <div class="scope-header">
    <div><p class="eyebrow">TEMPORARY · EQUITY RESEARCH / SCOPE</p><h2>{analysis.title}</h2></div>
    <button type="button" class="btn" on:click={onClose}>Return to live scope</button>
  </div>
  {#if snapshot}
    <p class="meta">{snapshot.positions.length} assets · {snapshot.benchmark} benchmark · {snapshot.lookback} days · {analysis.source_provider}</p>
    <p class="meta">Created {timestamp(analysis.created_at)} · Expires {timestamp(analysis.expires_at!)}</p>
    <div class="metrics">
      <div><span>Total return</span><strong>{percent(snapshot.metrics.total_return)}</strong></div>
      <div><span>Annual volatility</span><strong>{percent(snapshot.metrics.annual_vol)}</strong></div>
      <div><span>Max drawdown</span><strong>{percent(snapshot.metrics.max_drawdown)}</strong></div>
      <div><span>Observations</span><strong>{snapshot.metrics.observations_count ?? "N/A"}</strong></div>
    </div>
    <TimeSeriesChart {series} height={300} showLegend={true} emptyMessage="Retained chart data unavailable." />
    <p class="meta">Cumulative return (%) · Benchmark overlap: {snapshot.coverage.benchmark_overlap_count} observations{snapshot.coverage.benchmark_available ? "" : " · Benchmark unavailable"}</p>
    <div class="table-scroll"><table class="data-table is-figures">
      <thead><tr><th>Requested asset</th><th>Weight</th><th>Total return</th><th>Annual volatility</th></tr></thead>
      <tbody>{#each snapshot.positions as position}
        {@const constituent = snapshot.constituents.find(row => row.symbol === position.symbol)}
        <tr><td>{position.symbol}</td><td>{percent(position.weight)}</td><td>{percent(constituent?.total_return)}</td><td>{percent(constituent?.annual_vol)}</td></tr>
      {/each}</tbody>
    </table></div>
    {#each analysis.warnings as warning}<p class="note">{warning}</p>{/each}
    <p class="meta">{analysis.transformation_note}</p>
  {:else}
    <p class="note" role="status">This temporary Research scope is expired or unavailable. Return to the live scope or run a new analysis.</p>
  {/if}
</article>

<style>
  .retained-scope { min-width: 0; }
  .scope-header { display: flex; justify-content: space-between; gap: var(--space-4); padding: var(--space-5); align-items: center; flex-wrap: wrap; }
  h2, p { margin: 0; }
  h2 { font-size: var(--text-lg); }
  .btn { min-height: 28px; padding: var(--space-2) var(--space-4); background: var(--bg-1); color: var(--text-1); border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font: inherit; font-family: var(--font-ui); font-size: var(--text-xs); cursor: pointer; }
  .btn:hover { border-color: var(--panel-strong); }
  .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .meta, .note { padding: var(--space-3) var(--space-5); font-size: var(--text-xs); overflow-wrap: anywhere; }
  .meta { color: var(--text-2); }
  .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--divider); }
  .metrics > div { display: grid; gap: var(--space-3); padding: var(--space-5); }
  .metrics span { font-size: var(--text-xs); color: var(--text-2); }
  .metrics strong { font-size: var(--text-md); }
  .table-scroll { overflow-x: auto; }
  /* Cells come from .data-table.is-figures in primitives.css. */
  @media (max-width: 720px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
