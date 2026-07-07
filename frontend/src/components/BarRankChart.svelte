<script lang="ts">
  export interface RankBarItem {
    label: string;
    value: number;
    tone?: "positive" | "negative" | "neutral";
    meta?: string;
  }

export let items: RankBarItem[] = [];
export let emptyMessage = "No ranked data";
export let formatValue: (value: number) => string = (value) => value.toFixed(2);
let maxAbs = 1;

function barWidth(value: number, maxAbs: number) {
  return `${(Math.abs(value) / Math.max(maxAbs, 1e-6)) * 100}%`;
}

  $: maxAbs = Math.max(...items.map((item) => Math.abs(item.value)), 1);
</script>

{#if items.length}
  <div class="chart">
    {#each items as item}
      <div class="row">
        <div class="head">
          <span>{item.label}</span>
          <strong>{formatValue(item.value)}</strong>
        </div>
        <div class="track">
          <div class={`fill ${item.tone ?? "neutral"}`} style={`width:${barWidth(item.value, maxAbs)}`}></div>
        </div>
        {#if item.meta}
          <small>{item.meta}</small>
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <div class="empty">{emptyMessage}</div>
{/if}

<style>
  .chart {
    display: grid;
    gap: var(--space-3);
  }

  .row {
    display: grid;
    gap: var(--space-2);
  }

  .head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-5);
    font-size: var(--text-sm);
  }

  .track {
    height: 0.55rem;
    background: rgba(39, 53, 68, 0.8);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    background: rgba(122, 166, 200, 0.76);
  }

  .fill.positive {
    background: var(--positive);
  }

  .fill.negative {
    background: var(--negative);
  }

  span,
  small,
  .empty {
    color: var(--text-2);
  }

  small {
    font-size: var(--text-xs);
  }

  strong {
    color: var(--text-0);
  }

  .empty {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-xs);
    padding: var(--space-4) var(--space-5);
  }
</style>
