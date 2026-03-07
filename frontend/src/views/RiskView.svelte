<script lang="ts">
  import type { PortfolioSnapshot, RiskResult } from "../lib/api/types";

  export let snapshot: PortfolioSnapshot | null = null;
  export let result: RiskResult | null = null;
  export let loading = false;
  export let onCompute: () => void;

  const fmt = (value: number | null | undefined) => (value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: 4 }));
  const pct = (value: number | null | undefined) => (value == null ? "N/A" : `${(value * 100).toFixed(2)}%`);
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Risk Shell</h2>
      <p>Computes against the latest portfolio snapshot through the extracted Python risk service.</p>
    </div>
    <button on:click={onCompute} disabled={loading || !snapshot}>{loading ? "Computing..." : "Compute Risk"}</button>
  </div>

  <div class="grid">
    <article class="panel"><span>Hist VaR</span><strong>{fmt(result?.metrics.historical_var)}</strong></article>
    <article class="panel"><span>Param VaR</span><strong>{fmt(result?.metrics.parametric_var)}</strong></article>
    <article class="panel"><span>Annual Vol</span><strong>{pct(result?.metrics.annual_vol)}</strong></article>
    <article class="panel"><span>Coverage</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></article>
  </div>

  <div class="split">
    <article class="panel">
      <h3>Contributions</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Symbol</th><th>Weight</th><th>Vol</th><th>Var %</th></tr>
          </thead>
          <tbody>
            {#if result?.contributions?.length}
              {#each result.contributions as contribution}
                <tr>
                  <td>{contribution.symbol}</td>
                  <td>{pct(contribution.weight)}</td>
                  <td>{pct(contribution.daily_vol)}</td>
                  <td>{pct(contribution.variance_contribution_pct)}</td>
                </tr>
              {/each}
            {:else}
              <tr><td colspan="4">No risk result yet.</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
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

  .grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin-top: 1rem;
  }

  .split {
    grid-template-columns: 1.5fr 1fr;
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

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    border-bottom: 1px solid #13202c;
    padding: 0.55rem 0.4rem;
    text-align: left;
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
  }
</style>
