<script lang="ts">
  /* A 20-session sparkline for a KPI (visual refresh V4, B′): the last
     `sessions` values as a 1.25px accent line, scaled to its own range, with
     a dot on the latest value. Decorative next to the figure it trends, so
     it stays out of the accessibility tree; the week-over-week change beside
     it carries the reading. Draws nothing with fewer than two values. */
  export let values: Array<number | null | undefined> = [];
  export let sessions = 20;
  export let width = 56;
  export let height = 16;

  $: series = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value)).slice(-sessions);
  $: min = Math.min(...series);
  $: max = Math.max(...series);
  $: span = max - min || 1;
  $: coords = series.map((value, index) => [
    1 + (index / Math.max(series.length - 1, 1)) * (width - 3),
    1.5 + (1 - (value - min) / span) * (height - 3)
  ]);
  $: path = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  $: last = coords.at(-1);
</script>

{#if series.length >= 2 && last}
  <svg class="sparkline" {width} {height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <polyline points={path} />
    <circle cx={last[0]} cy={last[1]} r="1.5" />
  </svg>
{/if}

<style>
  .sparkline {
    display: inline-block;
    flex: none;
    vertical-align: middle;
    overflow: visible;
  }

  polyline {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.25;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  circle {
    fill: var(--chart-primary);
  }
</style>
