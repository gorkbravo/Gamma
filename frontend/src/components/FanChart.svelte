<script lang="ts">
  import type { IndexedValuePoint } from "../lib/api/types";

  export let series: Record<string, IndexedValuePoint[]> = {};
  export let history: IndexedValuePoint[] = [];
  export let samplePaths: Record<string, IndexedValuePoint[]> = {};
  export let height = 240;
  export let emptyMessage = "No fan data";

  const width = 640;
  const padding = { top: 16, right: 16, bottom: 34, left: 32 };

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
  let xMin = 0;
  let xMax = 1;
  let hoveredIndex: number | null = null;
  let visibleSamplePaths: Point[][] = [];

  $: {
    p05 = series.p05 ?? [];
    p25 = series.p25 ?? [];
    p50 = series.p50 ?? [];
    p75 = series.p75 ?? [];
    p95 = series.p95 ?? [];
    visibleSamplePaths = Object.values(samplePaths)
      .slice(0, 12)
      .map((points) => points.map((point) => ({ index: point.index, value: point.value })));
    const historyPoints = history.map((point) => ({ index: point.index, value: point.value }));
    const all = [...historyPoints, ...visibleSamplePaths.flat(), ...p05, ...p25, ...p50, ...p75, ...p95];
    if (all.length) {
      yMin = Math.min(...all.map((point) => point.value));
      yMax = Math.max(...all.map((point) => point.value));
      xMin = Math.min(...all.map((point) => point.index), 0);
      xMax = Math.max(...all.map((point) => point.index), 1);
      const spread = Math.max(yMax - yMin, 0.05);
      yMin -= spread * 0.08;
      yMax += spread * 0.08;
    } else {
      yMin = 0;
      yMax = 1;
      xMin = 0;
      xMax = 1;
    }
  }

  function xScale(value: number) {
    const usableWidth = width - padding.left - padding.right;
    return padding.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * usableWidth;
  }

  function yScale(value: number) {
    const usableHeight = height - padding.top - padding.bottom;
    return padding.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1e-6)) * usableHeight;
  }

  function fmt(value: number) {
    return value.toFixed(2);
  }

  function pointAt(points: Point[], index: number) {
    return points.find((point) => point.index === index) ?? null;
  }

  function tooltipX(index: number) {
    const x = xScale(index);
    return Math.min(Math.max(x, 88), width - 88);
  }

  function labelForIndex(index: number) {
    return index < 0 ? `T${index}` : `Day ${index}`;
  }
</script>

<div class="shell" style={`height:${height}px`}>
  {#if p50.length}
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label="Monte Carlo fan chart">
      {#each [0.2, 0.4, 0.6, 0.8] as ratio}
        <line
          class="grid-line"
          x1={padding.left}
          y1={padding.top + (height - padding.top - padding.bottom) * ratio}
          x2={width - padding.right}
          y2={padding.top + (height - padding.top - padding.bottom) * ratio}
        />
      {/each}
      {#each [0.25, 0.5, 0.75] as ratio}
        <line
          class="grid-line"
          x1={padding.left + (width - padding.left - padding.right) * ratio}
          y1={padding.top}
          x2={padding.left + (width - padding.left - padding.right) * ratio}
          y2={height - padding.bottom}
        />
      {/each}
      <line class="axis" x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
      <line class="axis" x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} />
      {#if history.length}
        <path d={pathFrom(history)} class="history" />
      {/if}
      {#each visibleSamplePaths as path}
        <path d={pathFrom(path)} class="sample-path" />
      {/each}
      {#if p05.length && p95.length}
        <path d={bandPath(p95, p05)} class="band outer" />
      {/if}
      {#if p25.length && p75.length}
        <path d={bandPath(p75, p25)} class="band inner" />
      {/if}
      <path d={pathFrom(p50)} class="median" />
      <line class="split" x1={xScale(0)} y1={padding.top} x2={xScale(0)} y2={height - padding.bottom} />
      <line class="baseline" x1={padding.left} y1={yScale(1)} x2={width - padding.right} y2={yScale(1)} />
      {#each Array.from({ length: xMax - xMin + 1 }, (_, offset) => xMin + offset) as index}
        <rect
          class="hover-zone"
          role="presentation"
          aria-hidden="true"
          x={xScale(index) - 10}
          y={padding.top}
          width="20"
          height={height - padding.top - padding.bottom}
          on:mouseenter={() => (hoveredIndex = index)}
          on:mouseleave={() => (hoveredIndex = null)}
        />
      {/each}
      {#if hoveredIndex != null && pointAt(p50, hoveredIndex)}
        <g class="tooltip">
          <rect x={tooltipX(hoveredIndex) - 78} y={padding.top + 8} width="156" height="42" rx="4" />
          <text x={tooltipX(hoveredIndex)} y={padding.top + 22} text-anchor="middle">
            {labelForIndex(hoveredIndex)} | P50 {fmt(pointAt(p50, hoveredIndex)?.value ?? 0)}
          </text>
          <text x={tooltipX(hoveredIndex)} y={padding.top + 36} text-anchor="middle">
            P05 {fmt(pointAt(p05, hoveredIndex)?.value ?? pointAt(p50, hoveredIndex)?.value ?? 0)} | P95 {fmt(pointAt(p95, hoveredIndex)?.value ?? pointAt(p50, hoveredIndex)?.value ?? 0)}
          </text>
        </g>
      {/if}
      <text class="tick" x={padding.left} y={height - 10}>{labelForIndex(xMin)}</text>
      <text class="tick" x={xScale(0) - 18} y={height - 10}>T</text>
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
    border: 1px solid var(--divider);
    background: rgba(7, 11, 16, 0.88);
    position: relative;
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  .grid-line {
    stroke: rgba(42, 56, 70, 0.26);
    stroke-width: 1;
  }

  .axis,
  .baseline {
    stroke: rgba(46, 60, 74, 0.58);
    stroke-width: 1;
  }

  .baseline {
    stroke-dasharray: 4 4;
  }

  .split {
    stroke: rgba(122, 166, 200, 0.28);
    stroke-dasharray: 3 4;
  }

  .band.outer {
    fill: rgba(122, 166, 200, 0.12);
  }

  .band.inner {
    fill: rgba(122, 166, 200, 0.22);
  }

  .hover-zone {
    fill: transparent;
  }

  .history {
    fill: none;
    stroke: rgba(244, 247, 251, 0.82);
    stroke-width: 1.35;
  }

  .sample-path {
    fill: none;
    stroke: rgba(122, 166, 200, 0.1);
    stroke-width: 0.85;
  }

  .median {
    fill: none;
    stroke: #7aa6c8;
    stroke-width: 1.8;
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

  .tooltip rect {
    fill: rgba(7, 11, 16, 0.96);
    stroke: rgba(106, 168, 255, 0.32);
  }

  .tooltip text {
    fill: #f4f7fb;
    font-size: 11px;
  }
</style>
