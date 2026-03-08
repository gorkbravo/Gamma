<script lang="ts">
  import type { IndexedValuePoint } from "../lib/api/types";

  export let series: Record<string, IndexedValuePoint[]> = {};
  export let height = 240;
  export let emptyMessage = "No fan data";

  const width = 640;
  const padding = { top: 18, right: 18, bottom: 30, left: 36 };

  type Point = { index: number; value: number };

  function pathFrom(points: Point[]) {
    return points
      .map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.index)} ${yScale(point.value)}`)
      .join(" ");
  }

  function bandPath(upper: Point[], lower: Point[]) {
    return `${pathFrom(upper)} ${lower
      .slice()
      .reverse()
      .map((point) => `L ${xScale(point.index)} ${yScale(point.value)}`)
      .join(" ")} Z`;
  }

  let p05: Point[] = [];
  let p25: Point[] = [];
  let p50: Point[] = [];
  let p75: Point[] = [];
  let p95: Point[] = [];
  let yMin = 0;
  let yMax = 1;
  let xMax = 1;

  $: {
    p05 = series.p05 ?? [];
    p25 = series.p25 ?? [];
    p50 = series.p50 ?? [];
    p75 = series.p75 ?? [];
    p95 = series.p95 ?? [];
    const all = [...p05, ...p25, ...p50, ...p75, ...p95];
    if (all.length) {
      yMin = Math.min(...all.map((point) => point.value));
      yMax = Math.max(...all.map((point) => point.value));
      xMax = Math.max(...all.map((point) => point.index), 1);
      const spread = Math.max(yMax - yMin, 0.05);
      yMin -= spread * 0.08;
      yMax += spread * 0.08;
    } else {
      yMin = 0;
      yMax = 1;
      xMax = 1;
    }
  }

  function xScale(value: number) {
    const usableWidth = width - padding.left - padding.right;
    return padding.left + (value / Math.max(xMax, 1)) * usableWidth;
  }

  function yScale(value: number) {
    const usableHeight = height - padding.top - padding.bottom;
    return padding.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1e-6)) * usableHeight;
  }

  function fmt(value: number) {
    return value.toFixed(2);
  }
</script>

<div class="shell" style={`height:${height}px`}>
  {#if p50.length}
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label="Monte Carlo fan chart">
      <line class="axis" x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
      <line class="axis" x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} />
      {#if p05.length && p95.length}
        <path d={bandPath(p95, p05)} class="band outer" />
      {/if}
      {#if p25.length && p75.length}
        <path d={bandPath(p75, p25)} class="band inner" />
      {/if}
      <path d={pathFrom(p50)} class="median" />
      <line class="baseline" x1={padding.left} y1={yScale(1)} x2={width - padding.right} y2={yScale(1)} />
      <text class="tick" x={padding.left} y={height - 10}>Day 0</text>
      <text class="tick" x={width - padding.right - 42} y={height - 10}>Day {xMax}</text>
      <text class="tick" x={padding.left - 24} y={padding.top + 4}>{fmt(yMax)}</text>
      <text class="tick" x={padding.left - 24} y={height - padding.bottom}>{fmt(yMin)}</text>
    </svg>
  {:else}
    <div class="empty">{emptyMessage}</div>
  {/if}
</div>

<style>
  .shell {
    border: 1px solid rgba(22, 32, 43, 0.85);
    background:
      linear-gradient(180deg, rgba(9, 14, 20, 0.98), rgba(5, 8, 11, 0.98)),
      radial-gradient(circle at top, rgba(106, 168, 255, 0.08), transparent 55%);
    position: relative;
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  .axis,
  .baseline {
    stroke: rgba(30, 46, 60, 0.8);
    stroke-width: 1;
  }

  .baseline {
    stroke-dasharray: 4 4;
  }

  .band.outer {
    fill: rgba(106, 168, 255, 0.14);
  }

  .band.inner {
    fill: rgba(106, 168, 255, 0.26);
  }

  .median {
    fill: none;
    stroke: #f4f7fb;
    stroke-width: 2;
  }

  .tick,
  .empty {
    font-size: 12px;
    fill: var(--text-2);
    color: var(--text-2);
  }

  .empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
</style>
