<script lang="ts">
  import type { ResearchCompareResult, SavedResearchItem, StrategyLabCompositionResult } from "../lib/api/types";
  import { postJson } from "../lib/api/client";
  import { savedStrategyExperiment } from "../lib/strategy-experiments";
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  export let items: SavedResearchItem[] = [];
  export let current: StrategyLabCompositionResult | null = null;
  let baselineId = "", comparisonId = "current";
  let result: ResearchCompareResult | null = null;
  let error = "", loading = false;
  let generation = 0;
  $: experiments = items.filter((item) => savedStrategyExperiment(item));
  $: baseline = savedStrategyExperiment(experiments.find((item) => item.id === baselineId) ?? { object_type: "", payload: {} } as SavedResearchItem);
  $: comparison = comparisonId === "current" ? current : savedStrategyExperiment(experiments.find((item) => item.id === comparisonId) ?? { object_type: "", payload: {} } as SavedResearchItem);
  $: resetForSelection(baseline, comparison);
  function resetForSelection(_baseline: unknown, _comparison: unknown) { generation += 1; result = null; loading = false; error = ""; }
  async function compare() {
    if (!baseline || !comparison) return;
    const version = ++generation;
    loading = true; error = "";
    try {
      const response = await postJson<ResearchCompareResult>("/research/compare-scenario/analyze", {
        left: { label: baseline.name, object_type: "strategy_composition", return_points: baseline.returns_points },
        right: { label: comparison.name, object_type: "strategy_composition", return_points: comparison.returns_points }
      });
      if (version === generation) result = response;
    } catch (e) { if (version === generation) error = e instanceof Error ? e.message : "Could not compare the retained runs."; }
    finally { if (version === generation) loading = false; }
  }
  const pct = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? "N/A" : `${(v * 100).toFixed(2)}%`;
  const delta = (a: number | null | undefined, b: number | null | undefined) => a == null || b == null ? "N/A" : `${b - a >= 0 ? "+" : ""}${((b - a) * 100).toFixed(2)} pp`;
  const weights = (run: StrategyLabCompositionResult | null) => run?.portfolio_inputs?.legs.map((leg) => `${leg.label}: ${leg.weight >= 0 ? "+" : ""}${leg.weight}`).join(" · ") ?? "N/A";
  const benchmarkHistory = (run: StrategyLabCompositionResult) => JSON.stringify(run.benchmark_points.map((point) => [point.timestamp, point.value]));
  $: series = result ? [
    { id: "baseline", label: "Baseline", color: "var(--chart-primary)", data: result.left.normalized_nav_points.map((p) => ({ time: Math.floor(new Date(p.timestamp).getTime() / 1000), value: p.value })) },
    { id: "comparison", label: "Comparison", color: "var(--chart-secondary)", data: result.right.normalized_nav_points.map((p) => ({ time: Math.floor(new Date(p.timestamp).getTime() / 1000), value: p.value })) }
  ] satisfies ChartSeries[] : [];
</script>

<article class="comparison-panel" aria-label="Saved experiment comparison">
  <div class="header"><h3>Compare experiments</h3><button class="btn" on:click={compare} disabled={loading || !baseline || !comparison}>{loading ? "Comparing…" : "Compare Runs"}</button></div>
  <div class="selectors">
    <label>Baseline<select class="form-control" bind:value={baselineId}><option value="">Select saved experiment</option>{#each experiments as item}<option value={item.id}>{item.title}</option>{/each}</select></label>
    <label>Comparison<select class="form-control" bind:value={comparisonId}><option value="current">Current composition</option>{#each experiments as item}<option value={item.id}>{item.title}</option>{/each}</select></label>
  </div>
  {#if baseline && comparison}
    <p>Baseline weights: {weights(baseline)}</p><p>Comparison weights: {weights(comparison)}</p>
    <p>Benchmarks: {baseline.portfolio_inputs?.benchmark_symbol ?? "None"} → {comparison.portfolio_inputs?.benchmark_symbol ?? "None"}. Metrics below use the shared observation window.</p>
    {#if benchmarkHistory(baseline) !== benchmarkHistory(comparison)}<p>Benchmark histories differ between these runs.</p>{/if}
  {:else}<p>Save an experiment, revise an assumption in Composer, then select the baseline and current composition.</p>{/if}
  {#if error}<p role="alert">{error} Retry Compare Runs.</p>{/if}
  {#if result}
    <p>{result.aligned_observation_count} shared observations · {result.overlap_start?.slice(0, 10)} – {result.overlap_end?.slice(0, 10)}</p>
    <table class="data-table is-figures"><thead><tr><th>Metric</th><th>Baseline</th><th>Comparison</th><th>Change</th></tr></thead><tbody>
      {#each [{ label: "Total return", key: "total_return" }, { label: "Annual volatility", key: "annual_volatility" }, { label: "Max drawdown", key: "max_drawdown" }] as metric}
        {@const a = result.left.metrics[metric.key as "total_return" | "annual_volatility" | "max_drawdown"]}
        {@const b = result.right.metrics[metric.key as "total_return" | "annual_volatility" | "max_drawdown"]}
        <tr><td>{metric.label}</td><td>{pct(a)}</td><td>{pct(b)}</td><td>{delta(a, b)}</td></tr>
      {/each}
    </tbody></table>
    <TimeSeriesChart {series} height={220} showLegend emptyMessage="Shared return history unavailable." />
    {#each result.warnings as warning}<p>{warning}</p>{/each}
  {/if}
</article>

<style>
  .comparison-panel { min-width: 0; background: var(--panel-bg); border: 1px solid var(--panel-border); border-radius: var(--radius-md); }
  .header, .selectors { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4); padding: var(--space-5); }
  h3 { margin: 0; margin-right: auto; font-size: var(--text-md); }
  label { display: grid; gap: var(--space-2); flex: 1 1 220px; min-width: 0; font-family: var(--font-label); }
  /* Controls are .btn and .form-control from primitives.css. */
  select { width: 100%; min-width: 0; }
  p { margin: 0; padding: var(--space-3) var(--space-5); font-size: var(--text-sm); color: var(--text-1); overflow-wrap: anywhere; }
  /* Cells come from .data-table.is-figures in primitives.css. */
</style>
