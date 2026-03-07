<script lang="ts">
  import type { PortfolioHistoryResponse, PortfolioSnapshot } from "../lib/api/types";

  export let snapshot: PortfolioSnapshot | null = null;
  export let history: PortfolioHistoryResponse | null = null;
  export let loading = false;
  export let onRefresh: () => void;

  const fmt = (value: number | null | undefined) => (value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: 2 }));
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Portfolio Shell</h2>
      <p>Mock/live snapshot, local history, and positions table through the FastAPI layer.</p>
    </div>
    <button on:click={onRefresh} disabled={loading}>{loading ? "Refreshing..." : "Refresh Snapshot"}</button>
  </div>

  <div class="grid">
    <article class="panel kpi"><span>Net Liq</span><strong>{fmt(snapshot?.net_liquidation)} {snapshot?.base_currency ?? ""}</strong></article>
    <article class="panel kpi"><span>Market Value</span><strong>{fmt(snapshot?.total_market_value)} {snapshot?.base_currency ?? ""}</strong></article>
    <article class="panel kpi"><span>Cash</span><strong>{fmt(snapshot?.total_cash)} {snapshot?.base_currency ?? ""}</strong></article>
    <article class="panel kpi"><span>Day P&L</span><strong>{fmt(snapshot?.day_pnl)} {snapshot?.base_currency ?? ""}</strong></article>
  </div>

  <div class="split">
    <article class="panel">
      <h3>Positions</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Symbol</th><th>Type</th><th>Qty</th><th>Weight</th><th>Value</th></tr>
          </thead>
          <tbody>
            {#if snapshot?.positions?.length}
              {#each snapshot.positions as position}
                <tr>
                  <td>{position.symbol}</td>
                  <td>{position.sec_type}</td>
                  <td>{position.quantity}</td>
                  <td>{position.weight == null ? "N/A" : `${(position.weight * 100).toFixed(2)}%`}</td>
                  <td>{fmt(position.base_market_value)}</td>
                </tr>
              {/each}
            {:else}
              <tr><td colspan="5">No snapshot loaded yet.</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </article>

    <article class="panel">
      <h3>Local History</h3>
      <p class="muted">{history?.source ?? "No history source yet"}</p>
      <div class="history-list">
        {#if history?.points?.length}
          {#each history.points.slice(-8).reverse() as point}
            <div class="history-row">
              <span>{new Date(point.timestamp).toLocaleString()}</span>
              <strong>{fmt(point.portfolio_value)}</strong>
            </div>
          {/each}
        {:else}
          <p class="muted">No stored history points yet.</p>
        {/if}
      </div>
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
    grid-template-columns: 2fr 1fr;
    margin-top: 1rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: rgba(6, 9, 13, 0.96);
    padding: 1rem;
  }

  .kpi span,
  .muted {
    color: var(--text-2);
  }

  .kpi strong {
    display: block;
    margin-top: 0.35rem;
    font-size: 1.25rem;
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

  .history-row {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    border-bottom: 1px solid #13202c;
    padding: 0.55rem 0;
  }

  @media (max-width: 900px) {
    .grid,
    .split,
    .toolbar {
      grid-template-columns: 1fr;
    }
  }
</style>
