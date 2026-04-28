<script lang="ts">
  export interface AllocationSlice {
    label: string;
    value: number;
    detail?: string;
    color: string;
    unrealizedPnl?: number | null;
  }

  export let slices: AllocationSlice[] = [];
  export let size = 188;

  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const tooltipOffset = 18;
  const tooltipViewportPadding = 12;
  const fallbackTooltipWidth = 216;
  const fallbackTooltipHeight = 104;

  let normalizedSlices: Array<AllocationSlice & { percent: number; dasharray: string; dashoffset: number }> = [];
  let activeSliceLabel: string | null = null;
  let activeSlice: (AllocationSlice & { percent: number; dasharray: string; dashoffset: number }) | null = null;
  let tooltipPosition: { x: number; y: number } | null = null;
  let tooltipPlacement: "left" | "right" = "right";
  let tooltipArrowOffset = fallbackTooltipHeight / 2;
  let chartFrame: HTMLDivElement | null = null;
  let tooltipElement: HTMLDivElement | null = null;

  $: normalizedSlices = (() => {
    const clean = slices.filter((slice) => Number.isFinite(slice.value) && slice.value > 0);
    const total = clean.reduce((sum, slice) => sum + slice.value, 0);
    let offset = 0;

    return clean.map((slice) => {
      const percent = total > 0 ? slice.value / total : 0;
      const length = percent * circumference;
      const next = {
        ...slice,
        percent,
        dasharray: `${length} ${Math.max(circumference - length, 0)}`,
        dashoffset: -offset
      };
      offset += length;
      return next;
    });
  })();

  function pct(value: number) {
    return `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
  }

  function money(value: number | null | undefined) {
    return value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  function tooltipDetail(detail: string | undefined) {
    if (detail === "Cash balance") {
      return "Cash";
    }
    return detail ?? "Position";
  }

  function setActiveSlice(label: string | null) {
    activeSliceLabel = label;
  }

  function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
  }

  function updateTooltipPosition(clientX: number, clientY: number) {
    if (!chartFrame) {
      return;
    }

    const bounds = chartFrame.getBoundingClientRect();
    const tooltipWidth = tooltipElement?.offsetWidth ?? fallbackTooltipWidth;
    const tooltipHeight = tooltipElement?.offsetHeight ?? fallbackTooltipHeight;
    const placeRight = clientX + tooltipOffset + tooltipWidth + tooltipViewportPadding <= window.innerWidth;
    const rawX = placeRight
      ? clientX - bounds.left + tooltipOffset
      : clientX - bounds.left - tooltipWidth - tooltipOffset;
    const rawY = clientY - bounds.top - tooltipHeight / 2;
    const minX = tooltipViewportPadding - bounds.left;
    const maxX = window.innerWidth - tooltipViewportPadding - bounds.left - tooltipWidth;
    const minY = tooltipViewportPadding - bounds.top;
    const maxY = window.innerHeight - tooltipViewportPadding - bounds.top - tooltipHeight;
    const x = clamp(rawX, minX, Math.max(minX, maxX));
    const y = clamp(rawY, minY, Math.max(minY, maxY));

    tooltipPlacement = placeRight ? "right" : "left";
    tooltipArrowOffset = clamp(clientY - bounds.top - y, 16, Math.max(16, tooltipHeight - 16));
    tooltipPosition = { x, y };
  }

  function handleChartHover(event: MouseEvent) {
    const target = event.target;
    if (!(target instanceof SVGElement)) {
      return;
    }
    const label = target.dataset.sliceLabel;
    if (label) {
      setActiveSlice(label);
      updateTooltipPosition(event.clientX, event.clientY);
    } else {
      setActiveSlice(null);
      tooltipPosition = null;
    }
  }

  $: if (!normalizedSlices.length) {
    activeSliceLabel = null;
    tooltipPosition = null;
  } else if (activeSliceLabel != null && !normalizedSlices.some((slice) => slice.label === activeSliceLabel)) {
    activeSliceLabel = null;
    tooltipPosition = null;
  }

  $: activeSlice = activeSliceLabel == null ? null : normalizedSlices.find((slice) => slice.label === activeSliceLabel) ?? null;
</script>

<div class="donut-shell">
  <div class="chart-wrap">
    {#if normalizedSlices.length}
      <div class="chart-frame" bind:this={chartFrame} style={`width:${size}px;height:${size}px`}>
        <svg
          viewBox="0 0 120 120"
          aria-label="Portfolio allocation donut chart"
          role="img"
          on:mousemove={handleChartHover}
          on:mouseleave={() => {
            setActiveSlice(null);
            tooltipPosition = null;
          }}
        >
          <circle class="track" cx="60" cy="60" r={radius} />
          {#each normalizedSlices as slice}
            <circle
              class="segment"
              class:active={slice.label === activeSlice?.label}
              cx="60"
              cy="60"
              r={radius}
              stroke={slice.color}
              stroke-dasharray={slice.dasharray}
              stroke-dashoffset={slice.dashoffset}
              data-slice-label={slice.label}
            />
          {/each}
        </svg>
        {#if activeSlice && tooltipPosition}
          <div
            bind:this={tooltipElement}
            class="hover-tooltip"
            class:left={tooltipPlacement === "left"}
            style={`left:${tooltipPosition.x}px; top:${tooltipPosition.y}px; --tooltip-arrow-y:${tooltipArrowOffset}px;`}
          >
            <div class="hover-header">
              <div>
                <span class="hover-label">{activeSlice.label}</span>
                <strong>{tooltipDetail(activeSlice.detail)}</strong>
              </div>
              <span class="hover-share">{pct(activeSlice.percent)}</span>
            </div>
            <div class="hover-grid">
              <div>
                <span>Base Value</span>
                <strong>{money(activeSlice.value)}</strong>
              </div>
              <div>
                <span>Unreal. P&amp;L</span>
                <strong class:positive={(activeSlice.unrealizedPnl ?? 0) > 0} class:negative={(activeSlice.unrealizedPnl ?? 0) < 0}>
                  {money(activeSlice.unrealizedPnl)}
                </strong>
              </div>
            </div>
          </div>
        {/if}
      </div>
    {:else}
      <div class="chart-frame" style={`width:${size}px;height:${size}px`}>
        <div class="empty">No allocation data</div>
      </div>
    {/if}
  </div>

  <div class="legend">
    {#each normalizedSlices as slice}
      <button
        type="button"
        class="legend-row"
        class:active={slice.label === activeSlice?.label}
        on:mouseenter={() => {
          setActiveSlice(slice.label);
          tooltipPosition = null;
        }}
        on:focus={() => {
          setActiveSlice(slice.label);
          tooltipPosition = null;
        }}
      >
        <div class="legend-label">
          <span class="swatch" style={`background:${slice.color}`}></span>
          <div>
            <strong>{slice.label}</strong>
            {#if slice.detail}
              <small>{slice.detail}</small>
            {/if}
          </div>
        </div>
        <span class="legend-value">{pct(slice.percent)}</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .donut-shell {
    display: grid;
    gap: 0.9rem;
  }

  .chart-wrap {
    display: grid;
    justify-items: center;
    gap: 0.85rem;
  }

  .chart-frame {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: visible;
  }

  svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }

  .track,
  .segment {
    fill: none;
    stroke-width: 18;
  }

  .track {
    stroke: rgba(39, 53, 68, 0.8);
  }

  .segment {
    stroke-linecap: butt;
    transition: stroke-width 120ms ease;
  }

  .segment.active {
    stroke-width: 22;
  }

  .hover-tooltip {
    position: absolute;
    z-index: 2;
    width: 216px;
    display: grid;
    gap: 0.55rem;
    pointer-events: none;
    padding: 0.8rem 0.9rem;
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-0);
    box-shadow: 0 12px 26px rgba(0, 0, 0, 0.28);
  }

  .hover-tooltip::before {
    content: "";
    position: absolute;
    left: -0.45rem;
    top: var(--tooltip-arrow-y, 50%);
    width: 0.75rem;
    height: 0.75rem;
    border-left: 1px solid rgba(46, 60, 74, 0.52);
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-0);
    transform: translateY(-50%) rotate(45deg);
  }

  .hover-tooltip.left::before {
    left: auto;
    right: -0.45rem;
    border-left: 0;
    border-bottom: 0;
    border-right: 1px solid rgba(46, 60, 74, 0.52);
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  .hover-label,
  .hover-grid span,
  .legend-row small {
    color: var(--text-2);
  }

  .hover-label {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.64rem;
  }

  .hover-header,
  .hover-grid {
    display: grid;
    gap: 0.45rem;
  }

  .hover-header {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    gap: 0.8rem;
  }

  .hover-header strong,
  .hover-grid strong {
    color: var(--text-0);
  }

  .hover-grid strong {
    overflow-wrap: anywhere;
  }

  .hover-share {
    color: var(--accent);
    font-size: 0.88rem;
  }

  .hover-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hover-grid div {
    display: grid;
    gap: 0.12rem;
  }

  .hover-grid span {
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .legend {
    display: grid;
    gap: 0.55rem;
  }

  .legend-row,
  .legend-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.7rem;
  }

  .legend-row {
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    padding-top: 0.55rem;
    transition: opacity 120ms ease, background 120ms ease;
    width: 100%;
    border-left: 0;
    border-right: 0;
    border-bottom: 0;
    background: transparent;
    padding-inline: 0;
    text-align: left;
  }

  .legend-label {
    justify-content: flex-start;
    min-width: 0;
  }

  .swatch {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 999px;
    flex: 0 0 auto;
  }

  .legend-row strong {
    display: block;
    color: var(--text-0);
    overflow-wrap: anywhere;
  }

  .legend-row small {
    display: block;
    margin-top: 0.14rem;
    font-size: 0.72rem;
    overflow-wrap: anywhere;
  }

  .legend-value {
    color: var(--text-1);
  }

  .legend-row.active {
    background: rgba(122, 166, 200, 0.08);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .empty {
    display: grid;
    place-items: center;
    width: 100%;
    height: 100%;
    border: 1px solid var(--divider);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.74rem;
  }
</style>
