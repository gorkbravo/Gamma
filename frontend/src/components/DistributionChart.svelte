<script lang="ts">
  export interface DistributionMarker {
    label: string;
    value: number | null | undefined;
    color: string;
  }

  export let values: number[] = [];
  export let markers: DistributionMarker[] = [];
  export let height = 220;
  export let emptyMessage = "No distribution data";
  export let xLabel = "Return";

  const width = 640;
  const padding = { top: 16, right: 16, bottom: 34, left: 28 };

  function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
  }

  let bins: Array<{ x0: number; x1: number; count: number }> = [];
  let maxCount = 0;
  let domainMin = -1;
  let domainMax = 1;
  let visibleMarkers: Array<Required<DistributionMarker>> = [];
  let hoveredBin: { x0: number; x1: number; count: number } | null = null;
  let hoveredMarker: Required<DistributionMarker> | null = null;

  $: {
    const clean = values.filter((value) => Number.isFinite(value));
    if (!clean.length) {
      bins = [];
      maxCount = 0;
      domainMin = -1;
      domainMax = 1;
      visibleMarkers = [];
    } else {
      const min = Math.min(...clean);
      const max = Math.max(...clean);
      const spread = Math.max(max - min, 1e-6);
      domainMin = min - spread * 0.05;
      domainMax = max + spread * 0.05;
      const bucketCount = clamp(Math.round(Math.sqrt(clean.length) * 1.8), 10, 28);
      const step = (domainMax - domainMin) / bucketCount;
      bins = Array.from({ length: bucketCount }, (_, index) => ({
        x0: domainMin + index * step,
        x1: domainMin + (index + 1) * step,
        count: 0
      }));
      for (const value of clean) {
        const index = clamp(Math.floor((value - domainMin) / step), 0, bucketCount - 1);
        bins[index].count += 1;
      }
      maxCount = Math.max(...bins.map((bin) => bin.count), 1);
      visibleMarkers = markers
        .filter((marker): marker is Required<DistributionMarker> => Number.isFinite(marker.value ?? NaN))
        .map((marker) => ({ ...marker, value: Number(marker.value) }));
    }
  }

  function xScale(value: number) {
    const usableWidth = width - padding.left - padding.right;
    return padding.left + ((value - domainMin) / Math.max(domainMax - domainMin, 1e-6)) * usableWidth;
  }

  function yScale(value: number) {
    const usableHeight = height - padding.top - padding.bottom;
    return height - padding.bottom - (value / Math.max(maxCount, 1)) * usableHeight;
  }

  function fmt(value: number) {
    return `${(value * 100).toFixed(1)}%`;
  }

  function tooltipX(value: number) {
    return clamp(xScale(value), 96, width - 96);
  }

  function tooltipY(value: number) {
    return clamp(yScale(value) - 12, 30, height - 52);
  }
</script>

<div class="shell" style={`height:${height}px`}>
  {#if bins.length}
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label="Distribution chart">
      <line class="axis" x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
      {#each bins as bin}
        <rect
          class="bar"
          role="presentation"
          aria-hidden="true"
          x={xScale(bin.x0)}
          y={yScale(bin.count)}
          width={Math.max(xScale(bin.x1) - xScale(bin.x0) - 2, 1)}
          height={Math.max(height - padding.bottom - yScale(bin.count), 1)}
          rx="2"
          on:mouseenter={() => {
            hoveredBin = bin;
            hoveredMarker = null;
          }}
          on:mouseleave={() => (hoveredBin = null)}
        />
      {/each}
      {#each visibleMarkers as marker}
        <line
          class="marker"
          role="presentation"
          aria-hidden="true"
          x1={xScale(marker.value)}
          y1={padding.top}
          x2={xScale(marker.value)}
          y2={height - padding.bottom}
          stroke={marker.color}
          on:mouseenter={() => {
            hoveredMarker = marker;
            hoveredBin = null;
          }}
          on:mouseleave={() => (hoveredMarker = null)}
        />
        <text class="marker-label" x={xScale(marker.value) + 4} y={padding.top + 12} fill={marker.color}>
          {marker.label}
        </text>
      {/each}
      {#if hoveredBin}
        <g class="tooltip">
          <rect x={tooltipX((hoveredBin.x0 + hoveredBin.x1) / 2) - 74} y={tooltipY(hoveredBin.count) - 18} width="148" height="34" rx="4" />
          <text x={tooltipX((hoveredBin.x0 + hoveredBin.x1) / 2)} y={tooltipY(hoveredBin.count) - 5} text-anchor="middle">
            {fmt(hoveredBin.x0)} to {fmt(hoveredBin.x1)} | {hoveredBin.count}
          </text>
        </g>
      {/if}
      {#if hoveredMarker}
        <g class="tooltip">
          <rect x={tooltipX(hoveredMarker.value) - 64} y={padding.top + 18} width="128" height="34" rx="4" />
          <text x={tooltipX(hoveredMarker.value)} y={padding.top + 31} text-anchor="middle">
            {hoveredMarker.label}: {fmt(hoveredMarker.value)}
          </text>
        </g>
      {/if}
      <text class="tick" x={padding.left} y={height - 10}>{fmt(domainMin)}</text>
      <text class="tick" x={(width - padding.left - padding.right) / 2 + padding.left - 20} y={height - 10}>{xLabel}</text>
      <text class="tick" x={width - padding.right - 36} y={height - 10}>{fmt(domainMax)}</text>
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

  .axis {
    stroke: rgba(46, 60, 74, 0.6);
    stroke-width: 1;
  }

  .bar {
    fill: rgba(122, 166, 200, 0.76);
  }

  .marker {
    stroke-width: 1.5;
    stroke-dasharray: 4 4;
  }

  .marker-label,
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
    stroke: rgba(122, 166, 200, 0.28);
  }

  .tooltip text {
    fill: #f4f7fb;
    font-size: 11px;
  }
</style>
