<script lang="ts">
  import type { MacroSnapshot } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;

  $: countryCompare = snapshot?.country_compare ?? null;
</script>

<div class="workspace-grid">
  <div class="primary-column">
    <article class="panel table-panel">
      <div class="table-panel-header">Country Compare</div>
      {#if countryCompare?.rows?.length}
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>{countryCompare.base_region}</th>
              <th>{countryCompare.comparison_region}</th>
              <th>Gap</th>
              <th>Read</th>
            </tr>
          </thead>
          <tbody>
            {#each countryCompare.rows as row}
              <tr>
                <td><strong>{row.label}</strong></td>
                <td>{row.base_value_display ?? "N/A"}</td>
                <td>{row.comparison_value_display ?? "N/A"}</td>
                <td class:positive={(row.gap_value ?? 0) > 0} class:negative={(row.gap_value ?? 0) < 0}>{row.gap_display ?? "N/A"}</td>
                <td>{row.interpretation ?? "N/A"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No country comparison context</p>
      {/if}
    </article>

    {#if countryCompare?.summary}
      <article class="panel">
        <p class="eyebrow">Macro Gap Map</p>
        <h3>{countryCompare.headline}</h3>
        <p class="summary">{countryCompare.summary}</p>
      </article>
    {/if}
  </div>

  <div class="support-column">
    <article class="panel">
      <p class="eyebrow">Research Focus</p>
      <p class="summary">{countryCompare?.research_focus ?? "No research focus available."}</p>
    </article>

    <article class="panel">
      <p class="eyebrow">Coverage</p>
      {#if countryCompare?.caveats?.length}
        <ul>
          {#each countryCompare.caveats as caveat}
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
    grid-template-columns: minmax(0, 1.65fr) minmax(18rem, 0.8fr);
    gap: var(--space-4);
  }

  .primary-column,
  .support-column {
    display: grid;
    gap: var(--space-4);
    align-content: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
    display: grid;
    gap: var(--space-4);
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-panel-header {
    min-height: 26px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-xs);
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
    padding: var(--space-3) var(--space-4);
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  td {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  td strong,
  h3 {
    color: var(--text-0);
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
    font-size: var(--text-2xs);
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
    font-size: var(--text-base);
    line-height: 1.45;
  }

  ul {
    padding-left: var(--space-6);
  }

  @media (max-width: 980px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
