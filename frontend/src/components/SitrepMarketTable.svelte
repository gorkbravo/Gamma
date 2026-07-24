<script lang="ts" context="module">
  export interface SitrepMarketRow {
    id: string;
    symbol?: string | null;
    label: string;
    selectionLabel?: string | null;
    group: string;
    last: string;
    change: string;
    changePct?: string;
    changePctTone?: string;
    secondary: string;
    secondaryTone?: string;
    tone: string;
    source: string;
  }
</script>

<script lang="ts">
  import { flashOnChange } from "../lib/flash";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import type { ProvenanceBadgeData } from "../lib/provenance";

  export let rows: SitrepMarketRow[] = [];
  export let emptyLabel = "No data loaded.";
  export let hideGroup = false;
  export let hideSource = false;
  export let changeLabel = "Move";
  export let pctChangeLabel = "%CHG";
  export let showPctChange = false;
  export let contextLabel = "Context";
  export let hideContext = false;
  export let contextTone = false;
  export let profile: "default" | "equities" | "indices" | "fx" | "yields" | "commodities" = "default";
  export let onSelect: ((row: SitrepMarketRow) => void) | null = null;
  export let provenance: ProvenanceBadgeData | null = null;

  $: colCount = 3 + (hideGroup ? 0 : 1) + (showPctChange ? 1 : 0) + (hideContext ? 0 : 1);

  function handleRowKeydown(event: KeyboardEvent, row: SitrepMarketRow) {
    if (!onSelect || (event.key !== "Enter" && event.key !== " ")) {
      return;
    }
    event.preventDefault();
    onSelect(row);
  }
</script>

<div class="table-wrap">
  {#if provenance}
    <div class="table-provenance"><ProvenanceBadge data={provenance} /></div>
  {/if}
  <table class={`profile-${profile}`}>
    <thead>
      <tr>
        <th class="market-cell">Market</th>
        {#if !hideGroup}<th class="group-cell">Group</th>{/if}
        <th class="num-cell last-cell">Last</th>
        <th class="num-cell move-cell">{changeLabel}</th>
        {#if showPctChange}<th class="num-cell pct-cell">{pctChangeLabel}</th>{/if}
        {#if !hideContext}<th class="context-cell">{contextLabel}</th>{/if}
      </tr>
    </thead>
    <tbody>
      {#if rows.length}
        {#each rows as row (row.id)}
          <tr
            class:clickable={Boolean(onSelect)}
            tabindex={onSelect ? 0 : undefined}
            role={onSelect ? "button" : undefined}
            on:click={() => onSelect?.(row)}
            on:keydown={(event) => handleRowKeydown(event, row)}
          >
            <td class="market-cell">
              <strong>{row.label}</strong>
              {#if !hideSource && row.source}<span>{row.source}</span>{/if}
            </td>
            {#if !hideGroup}<td class="group-cell">{row.group}</td>{/if}
            <td use:flashOnChange={{ value: row.last, direction: 'neutral' }} class="num-cell last-cell">{row.last}</td>
            <td use:flashOnChange={{ value: row.change, direction: row.tone === 'positive' ? 'up' : row.tone === 'negative' ? 'down' : 'neutral' }} class="num-cell move-cell {row.tone}">{row.change}</td>
            {#if showPctChange}
              <td use:flashOnChange={{ value: row.changePct ?? 'N/A', direction: (row.changePctTone ?? row.tone) === 'positive' ? 'up' : (row.changePctTone ?? row.tone) === 'negative' ? 'down' : 'neutral' }} class="num-cell pct-cell {row.changePctTone ?? row.tone}">{row.changePct ?? 'N/A'}</td>
            {/if}
            {#if !hideContext}<td class="context-cell {contextTone ? row.secondaryTone ?? '' : ''}">{row.secondary}</td>{/if}
          </tr>
        {/each}
      {:else}
        <tr>
          <td colspan={colCount} class="empty-cell">{emptyLabel}</td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

<style>
  .table-wrap {
    overflow: auto;
    max-height: 20rem;
  }

  .table-provenance {
    display: flex;
    justify-content: flex-end;
    padding: var(--space-1) var(--space-4);
    border-bottom: 1px solid var(--divider);
    min-height: 20px;
  }

  table {
    width: 100%;
    min-width: 33rem;
    border-collapse: collapse;
    table-layout: fixed;
  }

  th,
  td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
    line-height: 1.32;
  }

  th {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  td strong,
  td span {
    display: block;
  }

  .context-cell {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  td span {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .num-cell {
    text-align: right;
    white-space: nowrap;
  }

  .profile-equities {
    min-width: 28rem;
  }

  .profile-equities .market-cell {
    width: 30%;
  }

  .profile-equities .group-cell {
    width: 24%;
    padding-right: var(--space-2);
  }

  .profile-equities .last-cell {
    width: 16%;
    padding-left: var(--space-2);
  }

  .profile-equities .move-cell,
  .profile-equities .context-cell {
    width: 15%;
  }

  .profile-indices {
    min-width: 30rem;
  }

  .profile-indices .market-cell {
    width: 34%;
  }

  .profile-indices .group-cell {
    width: 18%;
    padding-right: var(--space-2);
  }

  .profile-indices .last-cell {
    width: 17%;
    padding-left: var(--space-2);
  }

  .profile-indices .move-cell,
  .profile-indices .context-cell {
    width: 15.5%;
  }

  .profile-indices .pct-cell {
    width: 15.5%;
  }

  .profile-fx {
    min-width: 20rem;
  }

  .profile-fx th,
  .profile-fx td {
    padding-left: var(--space-2);
    padding-right: var(--space-2);
  }

  .profile-fx .market-cell {
    width: 40%;
  }

  .profile-fx .last-cell,
  .profile-fx .move-cell,
  .profile-fx .pct-cell {
    width: 20%;
  }

  .profile-yields {
    min-width: 24rem;
  }

  .profile-yields .market-cell {
    width: 24%;
    padding-right: var(--space-2);
  }

  .profile-yields .last-cell {
    width: 20%;
    padding-left: var(--space-2);
  }

  .profile-yields .move-cell {
    width: 22%;
  }

  .profile-yields .context-cell {
    width: 34%;
  }

  .profile-commodities {
    min-width: 38rem;
  }

  .profile-commodities .market-cell {
    width: 30%;
  }

  .profile-commodities .group-cell {
    width: 16%;
  }

  .profile-commodities .last-cell {
    width: 15%;
  }

  .profile-commodities .move-cell,
  .profile-commodities .pct-cell {
    width: 12%;
  }

  .profile-commodities .context-cell {
    width: 15%;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .empty-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-sm);
  }

  tr.clickable {
    cursor: pointer;
  }

  tr.clickable:hover,
  tr.clickable:focus-visible {
    background: var(--bg-1);
  }

  tr.clickable:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
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
