<script lang="ts">
  import type { CopilotWorkingAnalysis } from "../lib/api/types";
  import { strategyLabDraftFromWorkingAnalysis } from "../lib/view-models/research";

  export let analysis: CopilotWorkingAnalysis | null = null;

  const metricLabels: Array<[string, string, "percent" | "number"]> = [
    ["total_return", "Total return", "percent"],
    ["annual_return", "Annual return", "percent"],
    ["annual_volatility", "Annual vol", "percent"],
    ["sharpe_ratio", "Sharpe", "number"],
    ["max_drawdown", "Max drawdown", "percent"],
    ["observation_count", "Observations", "number"]
  ];

  function formatMetric(value: unknown, kind: "percent" | "number") {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "N/A";
    return kind === "percent" ? `${(numeric * 100).toFixed(2)}%` : numeric.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  $: draft = strategyLabDraftFromWorkingAnalysis(analysis);
</script>

{#if draft}
  <article class="working-analysis" aria-label="Temporary Copilot Strategy Lab analysis">
    <header>
      <div>
        <p class="eyebrow">Copilot Working Analysis</p>
        <h3>{draft.name}</h3>
      </div>
      <span class="temporary">Temporary</span>
    </header>

    <p class="safety">Session-ephemeral and unsaved. Opening this result does not rebalance, trade, or change a portfolio.</p>

    <div class="assumptions" aria-label="Temporary assumptions">
      <span><small>Benchmark</small><strong>{draft.benchmarkSymbol}</strong></span>
      <span><small>Lookback</small><strong>{draft.lookbackDays} days</strong></span>
      <span><small>Min overlap</small><strong>{draft.minObservations} obs</strong></span>
      <span><small>Weights</small><strong>Gross signed</strong></span>
      <span><small>Costs</small><strong>Excluded</strong></span>
      <span><small>Rebalancing</small><strong>Not simulated</strong></span>
    </div>

    <div class="metric-strip">
      {#each metricLabels as metric}
        <span><small>{metric[1]}</small><strong>{formatMetric(draft.metrics[metric[0]], metric[2])}</strong></span>
      {/each}
    </div>

    <div class="table-wrap">
      <table class="data-table is-compact is-nowrap">
        <thead><tr><th>Leg</th><th>Class</th><th>Identifier</th><th class="num">Signed weight</th></tr></thead>
        <tbody>
          {#each draft.legs as leg}
            <tr>
              <td>{leg.label}</td>
              <td>{leg.assetClass}</td>
              <td>{leg.identifier}</td>
              <td class="num" class:negative={leg.weight < 0}>{leg.weight > 0 ? "+" : ""}{leg.weight.toFixed(3)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </article>
{/if}

<style>
  .working-analysis {
    display: grid;
    gap: var(--space-4);
    background: var(--panel-bg);
    padding: var(--space-5);
    border-radius: var(--panel-radius);
  }

  header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: flex-start;
  }

  h3, p { margin: 0; }
  h3 { color: var(--text-0); font-size: var(--text-title); }
  .eyebrow, small { color: var(--text-2); font-size: var(--text-xs); text-transform: var(--label-case); letter-spacing: 0; }
  .temporary { color: var(--accent); padding: var(--space-1) var(--space-3); font-size: var(--text-xs); text-transform: var(--label-case); letter-spacing: 0;
    border-radius: var(--radius-pill);
    background: var(--accent-soft);
  }
  .safety { color: var(--text-1); font-size: var(--text-sm); }

  /* KPI strips: tinted blocks on one baseline (§8 KPI Strips), no dividers. */
  .assumptions, .metric-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .assumptions > span, .metric-strip > span {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-1) calc(var(--space-4) + var(--space-1));
    border-radius: var(--panel-radius);
    background: var(--tint);
    min-width: 0;
  }
  strong { color: var(--text-0); font-size: var(--text-sm); overflow-wrap: anywhere; }

  .table-wrap { overflow-x: auto; }
  /* Cells and header come from .data-table.is-compact.is-nowrap in primitives.css. */
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .negative { color: var(--negative); }

  @media (max-width: 980px) {
    .assumptions, .metric-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }

  @media (max-width: 640px) {
    .assumptions, .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
</style>
