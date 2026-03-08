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
  .chart,
  .row {
    display: grid;
    gap: 0.45rem;
  }

  .head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .track {
    height: 0.7rem;
    background: rgba(19, 32, 44, 0.8);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    background: rgba(106, 168, 255, 0.86);
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

  strong {
    color: var(--text-0);
  }

  .empty {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.78rem;
  }
</style>
