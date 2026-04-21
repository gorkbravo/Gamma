<script lang="ts" context="module">
  export interface SitrepMarketRow {
    id: string;
    label: string;
    group: string;
    last: string;
    change: string;
    secondary: string;
    tone: string;
    source: string;
  }
</script>

<script lang="ts">
  export let rows: SitrepMarketRow[] = [];
  export let emptyLabel = "No data loaded.";
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Market</th>
        <th>Group</th>
        <th class="num-cell">Last</th>
        <th class="num-cell">Move</th>
        <th>Context</th>
      </tr>
    </thead>
    <tbody>
      {#if rows.length}
        {#each rows as row}
          <tr>
            <td>
              <strong>{row.label}</strong>
              <span>{row.source}</span>
            </td>
            <td>{row.group}</td>
            <td class="num-cell">{row.last}</td>
            <td class="num-cell {row.tone}">{row.change}</td>
            <td>{row.secondary}</td>
          </tr>
        {/each}
      {:else}
        <tr>
          <td colspan="5" class="empty-cell">{emptyLabel}</td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

<style>
  .table-wrap {
    overflow: auto;
    border: 1px solid var(--divider);
    background: var(--bg-0);
    max-height: 20rem;
  }

  table {
    width: 100%;
    min-width: 33rem;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.38rem 0.45rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
    line-height: 1.32;
  }

  th {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
  }

  td strong,
  td span {
    display: block;
  }

  td span {
    color: var(--text-2);
    font-size: 0.72rem;
  }

  .num-cell {
    text-align: right;
    white-space: nowrap;
  }

  .empty-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .warning {
    color: var(--warning);
  }
</style>
