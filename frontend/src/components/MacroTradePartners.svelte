<script lang="ts">
  import type { MacroSnapshot } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;

  $: tradePartners = snapshot?.trade_partners ?? null;
</script>

<div class="workspace-grid">
  <div class="primary-column">
    <article class="panel table-panel">
      <div class="table-panel-header">Trade Partners</div>
      {#if tradePartners?.partners?.length}
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Partner</th>
              <th>Exports</th>
              <th>Imports</th>
              <th>Total</th>
              <th>Trade Balance</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {#each tradePartners.partners as partner}
              <tr>
                <td>{partner.rank}</td>
                <td>
                  <strong>{partner.partner_name}</strong>
                  <span>{partner.partner_code}</span>
                </td>
                <td>{partner.export_value_display ?? "N/A"}</td>
                <td>{partner.import_value_display ?? "N/A"}</td>
                <td>{partner.total_trade_value_display ?? "N/A"}</td>
                <td class:positive={(partner.trade_balance ?? 0) > 0} class:negative={(partner.trade_balance ?? 0) < 0}>{partner.trade_balance_display ?? "N/A"}</td>
                <td>{partner.share_of_total_display ?? "N/A"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No trade partner context</p>
      {/if}
    </article>

    {#if tradePartners?.summary}
      <article class="panel">
        <p class="eyebrow">Trade Linkages</p>
        <h3>{tradePartners.headline}</h3>
        <p class="summary">{tradePartners.summary}</p>
      </article>
    {/if}
  </div>

  <div class="support-column">
    <article class="panel">
      <p class="eyebrow">Research Focus</p>
      <p class="summary">{tradePartners?.research_focus ?? "No research focus available."}</p>
    </article>

    <article class="panel">
      <p class="eyebrow">Coverage</p>
      {#if tradePartners?.caveats?.length}
        <ul>
          {#each tradePartners.caveats as caveat}
            <li>{caveat}</li>
          {/each}
        </ul>
      {:else}
        <p class="summary">No caveats reported.</p>
      {/if}
    </article>
  </div>
</div>

<style>
  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(18rem, 0.8fr);
    gap: 0.5rem;
  }

  .primary-column,
  .support-column {
    display: grid;
    gap: 0.5rem;
    align-content: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    display: grid;
    gap: 0.5rem;
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-panel-header {
    min-height: 26px;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    border-bottom: 1px solid var(--divider);
    padding: 0.4rem 0.55rem;
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-2);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  td {
    color: var(--text-1);
    font-size: 0.78rem;
  }

  td strong,
  h3 {
    color: var(--text-0);
  }

  td span {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: 0.68rem;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .eyebrow {
    margin: 0;
    color: var(--text-2);
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  h3,
  .summary,
  .empty,
  ul {
    margin: 0;
  }

  .summary,
  .empty,
  li {
    color: var(--text-1);
    font-size: 0.8rem;
    line-height: 1.45;
  }

  ul {
    padding-left: 1rem;
  }

  @media (max-width: 980px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
