<script lang="ts">
  import type { CrossTabHandoffEnvelope, IvSessionStatus, IvSurface, SystemStatus, TimeSeriesPoint } from "../lib/api/types";
  import type { IvLoadOptions } from "../lib/stores/app";
  import {
    daysToExpiry,
    deriveDistributionBuckets,
    deriveRealizedVolatility,
    deriveSkewRows,
    deriveSurfaceStats,
    deriveTermStructure,
    nearestStrikeIndex,
    optionsModes,
    type OptionsMode,
  } from "../lib/view-models/iv";

  export let mode: OptionsMode = "surface";
  export let status: SystemStatus | null = null;
  export let requestedSymbol = "SPY";
  export let result: IvSurface | null = null;
  export let session: IvSessionStatus | null = null;
  export let underlyingPricePoints: TimeSeriesPoint[] = [];
  export let loading = false;
  export let sessionLoading = false;
  export let onLoad: (options: IvLoadOptions) => void;
  export let onStartSession: (options: IvLoadOptions) => void;
  export let onStopSession: () => void;
  export let onSendToCopilot: (handoff: CrossTabHandoffEnvelope) => Promise<unknown> | void = () => {};

  let symbol = "SPY";
  let marketDataMode = "delayed";
  let depthPreset = "standard";
  let waitSeconds = 2.5;
  let selectedExpiry = 0;
  let hoveredExpiry: number | null = null;
  let cameraDepthX = 58;
  let cameraDepthY = 72;
  let isDragging = false;
  let dragStart = { x: 0, y: 0 };
  let dragStartCamera = { x: 0, y: 0 };
  let sliceHover: SlicePoint | null = null;

  interface SurfaceQuad { pts: string; fill: string; sortKey: number; ri: number; }
  interface AxisLabel  { x: number; y: number; label: string; anchor?: string; }
  interface SlicePoint { x: number; y: number; strike: number; value: number; }
  interface GridLine   { x1: number; y1: number; x2: number; y2: number; }

  let surfaceQuads: SurfaceQuad[] = [];
  let surfaceGridLines: GridLine[] = [];
  let surfaceFrameLines: GridLine[] = [];
  let axisStrikeLabels: AxisLabel[] = [];
  let axisIvLabels: AxisLabel[] = [];
  let axisDteLabels: AxisLabel[] = [];
  let sliceLinePoints = "";
  let sliceAreaPoints = "";
  let slicePoints: SlicePoint[] = [];
  let sliceIvLabels: AxisLabel[] = [];
  let sliceStrikeLabels: AxisLabel[] = [];

  function viridisColor(t: number): string {
    const v = Math.max(0, Math.min(1, t));
    const stops: [number, number, number][] = [
      [68, 1, 84], [70, 49, 126], [54, 91, 141], [39, 127, 142],
      [31, 161, 135], [74, 193, 109], [159, 218, 58], [253, 231, 37],
    ];
    const n = stops.length - 1;
    const pos = v * n;
    const lo = Math.floor(pos);
    const hi = Math.min(n, lo + 1);
    const f = pos - lo;
    const lr = (a: number, b: number) => Math.round(a + f * (b - a));
    return `rgb(${lr(stops[lo][0],stops[hi][0])},${lr(stops[lo][1],stops[hi][1])},${lr(stops[lo][2],stops[hi][2])})`;
  }

  function formatExpiry(expiry: string | null | undefined): string {
    if (!expiry) return "N/A";
    const m = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(expiry);
    return m ? `${m[1]}/${m[2]}/${m[3]}` : expiry;
  }

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const pct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const signedPct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
  const ratioPct = (value: number | null | undefined, digits = 0) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const shortTime = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";
  const sessionStateLabel = () =>
    depthPreset === "max" ? "snapshot only" : session?.running ? "running" : "idle";
  const depthLabel = (value: string | null | undefined) =>
    value === "max"
      ? "Max"
      : value === "front_deep"
      ? "Front Deep"
      : value
        ? value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
        : "Standard";

  function submit() {
    onLoad({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode,
      waitSeconds,
      depthPreset
    });
  }

  function startSession() {
    if (depthPreset === "max") {
      return;
    }
    onStartSession({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode,
      depthPreset
    });
  }

  function sendSurfaceToCopilot() {
    const surface = result;
    if (!surface) {
      return;
    }
    const handoff: CrossTabHandoffEnvelope = {
      source_tab: "iv",
      source_mode: mode,
      selected_entity: {
        entity_type: "options_surface",
        label: `${surface.symbol} IV Surface`,
        normalized_id: surface.symbol,
        provider_id: surface.source_provider,
        native_id: surface.symbol,
        metadata: {
          symbol: surface.symbol,
          expiries: surface.expiries.length,
          strikes: surface.strikes.length,
          points: surface.points,
          freshness_label: surface.freshness_label,
          delayed: surface.delayed
        }
      },
      selected_timeframe: surface.timestamp
        ? { label: `Snapshot ${shortTime(surface.timestamp)}`, start: null, end: surface.timestamp }
        : null,
      provider: surface.source_provider,
      source: null,
      warnings: surface.warnings ?? [],
      normalized_ids: { symbol: surface.symbol },
      timestamp: new Date().toISOString(),
      intended_target_tab: "copilot",
      intended_target_mode: "active_tab"
    };
    void onSendToCopilot(handoff);
  }

  function heatIntensity(value: number | null | undefined) {
    if (value == null || surfaceStats.minIv == null || surfaceStats.maxIv == null) {
      return 0;
    }
    const range = Math.max(surfaceStats.maxIv - surfaceStats.minIv, 0.01);
    return Math.max(0.12, Math.min(0.86, (value - surfaceStats.minIv) / range));
  }

  function toneClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function chooseMode(nextMode: OptionsMode) {
    mode = nextMode;
  }

  function onSurfacePointerDown(e: PointerEvent) {
    isDragging = true;
    dragStart = { x: e.clientX, y: e.clientY };
    dragStartCamera = { x: cameraDepthX, y: cameraDepthY };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }

  function onSurfacePointerMove(e: PointerEvent) {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    cameraDepthX = Math.max(-30, Math.min(80, dragStartCamera.x + dx * 0.25));
    cameraDepthY = Math.max(20, Math.min(120, dragStartCamera.y + dy * 0.25));
  }

  function onSurfacePointerUp() {
    isDragging = false;
  }

  function onSliceMouseMove(e: MouseEvent) {
    const target = e.currentTarget as SVGElement;
    const rect = target.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * 540;
    if (!slicePoints.length) { sliceHover = null; return; }
    let nearest = slicePoints[0];
    let minDist = Math.abs(slicePoints[0].x - mouseX);
    for (const pt of slicePoints) {
      const dist = Math.abs(pt.x - mouseX);
      if (dist < minDist) { minDist = dist; nearest = pt; }
    }
    sliceHover = nearest;
  }

  function onSliceMouseLeave() {
    sliceHover = null;
  }

  $: if (result && selectedExpiry >= result.expiries.length) {
    selectedExpiry = 0;
  }

  $: if (requestedSymbol && requestedSymbol !== symbol) {
    symbol = requestedSymbol;
  }

  let expiryRows: Array<{ expiry: string; values: number[] }> = [];
  let slice: { expiry: string; values: number[] } | undefined;
  let termStructure = deriveTermStructure(result);
  let atmStrikeIndex = nearestStrikeIndex(result);
  let surfaceStats = deriveSurfaceStats(result);
  let skewRows = deriveSkewRows(result);
  let realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  let distributionBuckets = deriveDistributionBuckets(result);
  let maxDistributionProbability = 0;
  let selectedPairs = result?.pairs?.filter((pair) => pair.expiry === slice?.expiry) ?? [];

  $: expiryRows = result?.expiries.map((expiry, index) => ({
    expiry,
    values: result.iv_grid[index] ?? []
  })) ?? [];
  $: slice = expiryRows[selectedExpiry];
  $: selectedPairs = result?.pairs?.filter((pair) => pair.expiry === slice?.expiry) ?? [];
  $: termStructure = deriveTermStructure(result);
  $: atmStrikeIndex = nearestStrikeIndex(result);
  $: surfaceStats = deriveSurfaceStats(result);
  $: skewRows = deriveSkewRows(result);
  $: realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  $: distributionBuckets = deriveDistributionBuckets(result);
  $: maxDistributionProbability = Math.max(...distributionBuckets.map((bucket) => bucket.probability), 0.01);

  $: {
    const quads: SurfaceQuad[] = [];
    const gLines: GridLine[] = [];
    const fLines: GridLine[] = [];
    const sLabels: AxisLabel[] = [];
    const ivLabs: AxisLabel[] = [];
    const dteLabs: AxisLabel[] = [];

    if (result?.expiries.length && result.strikes.length) {
      const rowCount = result.expiries.length;
      const colCount = result.strikes.length;
      const minIv = surfaceStats.minIv ?? 0;
      const maxIv = surfaceStats.maxIv ?? 1;
      const ivRange = Math.max(maxIv - minIv, 0.01);
      const baseY = 268;
      const strikeWidth = 404;
      const depthX = cameraDepthX;
      const depthY = cameraDepthY;
      const zHeight = 132;

      const proj = (ri: number, ci: number, v: number | null | undefined): [number, number] => {
        const xr = colCount <= 1 ? 0.5 : ci / (colCount - 1);
        const yr = rowCount <= 1 ? 0.5 : ri / (rowCount - 1);
        const zr = v == null || !Number.isFinite(v) ? 0 : Math.max(0, Math.min(1, (v - minIv) / ivRange));
        return [34 + xr * strikeWidth + yr * depthX, baseY - yr * depthY - zr * zHeight];
      };

      for (let ri = 0; ri < rowCount - 1; ri++) {
        for (let ci = 0; ci < colCount - 1; ci++) {
          const v00 = result.iv_grid[ri]?.[ci];
          const v01 = result.iv_grid[ri]?.[ci + 1];
          const v10 = result.iv_grid[ri + 1]?.[ci];
          const v11 = result.iv_grid[ri + 1]?.[ci + 1];
          const vals = [v00, v01, v10, v11].filter((v): v is number => Number.isFinite(v));
          if (vals.length < 2) continue;
          const avg = vals.reduce((s, v) => s + v, 0) / vals.length;
          const [p00, p01, p11, p10] = [proj(ri,ci,v00), proj(ri,ci+1,v01), proj(ri+1,ci+1,v11), proj(ri+1,ci,v10)];
          quads.push({
            pts: [p00,p01,p11,p10].map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' '),
            fill: viridisColor((avg - minIv) / ivRange),
            sortKey: ri + ci * 0.001,
            ri,
          });
        }
      }
      quads.sort((a, b) => b.sortKey - a.sortKey);

      // Frame edges (front, left depth, right depth)
      const [flx, fly] = proj(0, 0, minIv);
      const [frx, fry] = proj(0, colCount - 1, minIv);
      const [blx, bly] = proj(rowCount - 1, 0, minIv);
      const [brx, bry] = proj(rowCount - 1, colCount - 1, minIv);
      fLines.push({ x1: flx, y1: fly, x2: frx, y2: fry });
      fLines.push({ x1: flx, y1: fly, x2: blx, y2: bly });
      fLines.push({ x1: frx, y1: fry, x2: brx, y2: bry });

      // Floor grid: DTE rows
      const rowSamples = Math.min(rowCount, 7);
      const rowSampleStep = rowCount <= 1 ? 1 : Math.max(1, Math.floor((rowCount - 1) / (rowSamples - 1)));
      for (let ri = 0; ri < rowCount; ri += rowSampleStep) {
        const [lx, ly] = proj(ri, 0, minIv);
        const [rx, ry] = proj(ri, colCount - 1, minIv);
        gLines.push({ x1: lx, y1: ly, x2: rx, y2: ry });
      }
      // Floor grid: strike columns
      const colSampleStep = Math.max(1, Math.floor((colCount - 1) / 4));
      for (let ci = 0; ci <= colCount - 1; ci += colSampleStep) {
        const [fx, fy] = proj(0, ci, minIv);
        const [bx, by] = proj(rowCount - 1, ci, minIv);
        gLines.push({ x1: fx, y1: fy, x2: bx, y2: by });
      }
      // Left-wall IV level lines
      for (let i = 1; i <= 4; i++) {
        const t = i / 4;
        const iv = minIv + t * ivRange;
        const [lfx, lfy] = proj(0, 0, iv);
        const [lbx, lby] = proj(rowCount - 1, 0, iv);
        gLines.push({ x1: lfx, y1: lfy, x2: lbx, y2: lby });
      }

      // X-axis: strike labels along front base
      const sStep = Math.max(1, Math.floor(colCount / 5));
      for (let ci = 0; ci < colCount; ci += sStep) {
        const xr = colCount <= 1 ? 0.5 : ci / (colCount - 1);
        sLabels.push({ x: 34 + xr * strikeWidth, y: 284, label: fmt(result.strikes[ci], 1) });
      }

      // Z-axis: IV% labels along left front edge
      for (let i = 0; i <= 4; i++) {
        const t = i / 4;
        ivLabs.push({ x: 27, y: baseY - t * zHeight, label: pct(minIv + t * ivRange, 0), anchor: "end" });
      }

      // Y-axis: DTE labels along right depth edge
      const dStep = Math.max(1, Math.floor(rowCount / 4));
      for (let ri = 0; ri < rowCount; ri += dStep) {
        const yr = rowCount <= 1 ? 0.5 : ri / (rowCount - 1);
        const dte = daysToExpiry(result.expiries[ri]);
        dteLabs.push({ x: 34 + strikeWidth + yr * depthX + 5, y: baseY - yr * depthY + 4, label: `${dte}d` });
      }
    }

    surfaceQuads = quads;
    surfaceGridLines = gLines;
    surfaceFrameLines = fLines;
    axisStrikeLabels = sLabels;
    axisIvLabels = ivLabs;
    axisDteLabels = dteLabs;
  }

  $: {
    const points: SlicePoint[] = [];
    const ivLabels: AxisLabel[] = [];
    const strikeLabels: AxisLabel[] = [];
    const values = slice?.values ?? [];
    const strikes = result?.strikes ?? [];
    const finiteValues = values.filter((value) => Number.isFinite(value));
    const minIv = finiteValues.length ? Math.min(...finiteValues) : 0;
    const maxIv = finiteValues.length ? Math.max(...finiteValues) : 1;
    const ivRange = Math.max(maxIv - minIv, 0.01);
    const left = 42;
    const right = 502;
    const top = 24;
    const bottom = 256;
    if (values.length && strikes.length) {
      values.forEach((value, index) => {
        if (!Number.isFinite(value)) return;
        const xRatio = values.length <= 1 ? 0.5 : index / (values.length - 1);
        const yRatio = (value - minIv) / ivRange;
        points.push({
          x: left + xRatio * (right - left),
          y: bottom - yRatio * (bottom - top),
          strike: strikes[index],
          value,
        });
      });
      for (let i = 0; i <= 4; i++) {
        const t = i / 4;
        ivLabels.push({ x: left - 8, y: bottom - t * (bottom - top) + 4, label: pct(minIv + t * ivRange, 0), anchor: "end" });
      }
      const step = Math.max(1, Math.floor(strikes.length / 5));
      for (let index = 0; index < strikes.length; index += step) {
        const xRatio = strikes.length <= 1 ? 0.5 : index / (strikes.length - 1);
        strikeLabels.push({ x: left + xRatio * (right - left), y: bottom + 18, label: fmt(strikes[index], 1), anchor: "middle" });
      }
    }
    slicePoints = points;
    sliceLinePoints = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    sliceAreaPoints = points.length
      ? `${left},${bottom} ${points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ")} ${right},${bottom}`
      : "";
    sliceIvLabels = ivLabels;
    sliceStrikeLabels = strikeLabels;
  }
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Options Workspace</span>
      <span class="subtitle">{result?.symbol ?? symbol}</span>
    </div>
    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Options modes">
      {#each optionsModes as optionMode}
        <button
          class:selected={optionMode.id === mode}
          role="tab"
          aria-selected={optionMode.id === mode}
          type="button"
          on:click={() => chooseMode(optionMode.id)}
        >
          {optionMode.label}
        </button>
      {/each}
      </div>
      <div class="surface-actions">
        <button class="primary-action" on:click={submit} disabled={loading}>
          {loading ? "LOADING..." : "Reload Surface"}
        </button>
        <button class="secondary-action" on:click={sendSurfaceToCopilot} disabled={loading || !result}>
          Send to Copilot
        </button>
        <div class="session-control" class:running={session?.running} class:snapshot-only={depthPreset === "max"}>
          <div>
            <span>Live Session</span>
            <strong>{sessionStateLabel()}</strong>
          </div>
          {#if session?.running}
            <button on:click={onStopSession} disabled={sessionLoading}>
              {sessionLoading ? "STOPPING..." : "Stop"}
            </button>
          {:else}
            <button
              on:click={startSession}
              disabled={sessionLoading || depthPreset === "max"}
              title={depthPreset === "max" ? "Max Reload is snapshot-only to avoid holding a large option surface open." : "Start a continuous options surface session."}
            >
              {sessionLoading ? "STARTING..." : "Start Live"}
            </button>
          {/if}
        </div>
      </div>
    </div>
  </article>

  <article class="panel controls-panel">
    <div class="field-grid">
      <label>
        <span>Symbol</span>
        <input bind:value={symbol} placeholder="SPY" />
      </label>
      <label>
        <span>Requested Mode</span>
        <select bind:value={marketDataMode}>
          <option value="delayed">Delayed</option>
          <option value="live">Live</option>
          <option value="auto">Auto</option>
        </select>
      </label>
      <label>
        <span>Depth</span>
        <select bind:value={depthPreset}>
          <option value="compact">Compact</option>
          <option value="standard">Standard</option>
          <option value="deep">Deep</option>
          <option value="front_deep">Front Deep</option>
          <option value="max">Max Reload</option>
        </select>
      </label>
      <label>
        <span>Wait</span>
        <select bind:value={waitSeconds}>
          <option value={1.5}>1.5s</option>
          <option value={2.5}>2.5s</option>
          <option value={4}>4.0s</option>
          <option value={8}>8.0s</option>
          <option value={15}>15.0s</option>
          <option value={25}>25.0s</option>
          <option value={30}>30.0s</option>
        </select>
      </label>
    </div>
    <div class="source-strip">
      <div><span>Backend</span><strong>{status?.market_data_mode ?? "unknown"}</strong></div>
      <div><span>Session</span><strong>{sessionStateLabel()}</strong></div>
      <div><span>Provider</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
      <div><span>Depth</span><strong>{depthLabel(result?.collection?.depth_preset ?? depthPreset)}</strong></div>
      <div><span>Updated</span><strong>{shortTime(result?.timestamp)}</strong></div>
    </div>
  </article>

  {#if mode === "surface"}
    <div class="surface-chart-row">
      <article class="panel surface-panel">
        <div class="panel-header">
          <h3>Surface</h3>
          <strong>{formatExpiry(surfaceStats.frontExpiry)}</strong>
        </div>
        {#if surfaceQuads.length}
          <svg
            class="surface-svg"
            class:dragging={isDragging}
            viewBox="0 0 520 300"
            role="img"
            aria-label="Volatility surface — drag to rotate"
            on:mouseleave={() => (hoveredExpiry = null)}
            on:pointerdown={onSurfacePointerDown}
            on:pointermove={onSurfacePointerMove}
            on:pointerup={onSurfacePointerUp}
            on:pointercancel={onSurfacePointerUp}
          >
            <g class="surface-gridlines">
              {#each surfaceGridLines as gl}
                <line x1={gl.x1.toFixed(1)} y1={gl.y1.toFixed(1)} x2={gl.x2.toFixed(1)} y2={gl.y2.toFixed(1)} />
              {/each}
            </g>
            {#each surfaceFrameLines as fl}
              <line class="surface-frame" x1={fl.x1.toFixed(1)} y1={fl.y1.toFixed(1)} x2={fl.x2.toFixed(1)} y2={fl.y2.toFixed(1)} />
            {/each}
            {#each surfaceQuads as quad}
              <polygon
                role="presentation"
                aria-hidden="true"
                points={quad.pts}
                style={`fill:${quad.fill};stroke:${quad.fill};`}
                class:row-hovered={hoveredExpiry === quad.ri}
                on:mouseenter={() => (hoveredExpiry = quad.ri)}
              />
            {/each}
            {#each axisStrikeLabels as lbl}
              <text class="axis-label" x={lbl.x} y={lbl.y} text-anchor="middle">{lbl.label}</text>
            {/each}
            {#each axisIvLabels as lbl}
              <text class="axis-label" x={lbl.x} y={lbl.y} text-anchor="end">{lbl.label}</text>
            {/each}
            {#each axisDteLabels as lbl}
              <text class="axis-label" x={lbl.x} y={lbl.y}>{lbl.label}</text>
            {/each}
            {#if hoveredExpiry !== null && result?.expiries[hoveredExpiry]}
              <text class="hover-label" x="10" y="16">{formatExpiry(result.expiries[hoveredExpiry])} · {pct(result.iv_grid[hoveredExpiry]?.[atmStrikeIndex], 1)} ATM</text>
            {/if}
          </svg>
        {:else}
          <p class="muted">No options surface loaded.</p>
        {/if}
      </article>

      <article class="panel slice-chart-panel">
        <div class="panel-header">
          <h3>Expiry Slice</h3>
          {#if slice}<strong>{formatExpiry(slice.expiry)}</strong>{/if}
        </div>
        {#if sliceLinePoints}
          <svg class="slice-svg" viewBox="0 0 540 300" role="img" aria-label="Selected expiry implied volatility slice"
            on:mousemove={onSliceMouseMove}
            on:mouseleave={onSliceMouseLeave}
          >
            <g class="chart-gridlines">
              <line x1="42" y1="256" x2="502" y2="256" />
              <line x1="42" y1="198" x2="502" y2="198" />
              <line x1="42" y1="140" x2="502" y2="140" />
              <line x1="42" y1="82" x2="502" y2="82" />
              <line x1="42" y1="24" x2="502" y2="24" />
              <line x1="42" y1="24" x2="42" y2="256" />
              <line x1="157" y1="24" x2="157" y2="256" />
              <line x1="272" y1="24" x2="272" y2="256" />
              <line x1="387" y1="24" x2="387" y2="256" />
              <line x1="502" y1="24" x2="502" y2="256" />
            </g>
            <polygon class="slice-area" points={sliceAreaPoints} />
            <polyline class="slice-line" points={sliceLinePoints} />
            {#each slicePoints as point}
              <circle class:spot={point.strike === surfaceStats.atmStrike} cx={point.x} cy={point.y} r="2.4" />
            {/each}
            {#each sliceIvLabels as lbl}
              <text class="axis-label" x={lbl.x} y={lbl.y} text-anchor="end">{lbl.label}</text>
            {/each}
            {#each sliceStrikeLabels as lbl}
              <text class="axis-label" x={lbl.x} y={lbl.y} text-anchor="middle">{lbl.label}</text>
            {/each}
            {#if sliceHover}
              <line class="slice-crosshair"
                x1={sliceHover.x.toFixed(1)} y1="24"
                x2={sliceHover.x.toFixed(1)} y2="256" />
              <circle class="slice-hover-dot"
                cx={sliceHover.x.toFixed(1)} cy={sliceHover.y.toFixed(1)} r="3.5" />
              <text class="slice-hover-label"
                x={sliceHover.x < 350 ? sliceHover.x + 7 : sliceHover.x - 7}
                y="16"
                text-anchor={sliceHover.x < 350 ? "start" : "end"}
              >{fmt(sliceHover.strike, 1)} · {pct(sliceHover.value, 1)}</text>
            {/if}
          </svg>
        {:else}
          <p class="muted">Select an expiry after loading a surface.</p>
        {/if}
      </article>
    </div>

    <div class="surface-data-row">
      <article class="panel heatmap-panel">
        <div class="panel-header">
          <h3>Expiry / Strike Grid</h3>
        </div>
        {#if expiryRows.length}
          <div class="heatmap" style={`--strike-count:${result?.strikes.length ?? 1};`}>
            <div class="cell header">Expiry</div>
            {#each result?.strikes ?? [] as strike, strikeIndex}
              <div class="cell header" class:spot={strikeIndex === atmStrikeIndex}>{fmt(strike, 2)}</div>
            {/each}
            {#each expiryRows as row, rowIndex}
              <button class:active={selectedExpiry === rowIndex} class="cell expiry" on:click={() => (selectedExpiry = rowIndex)}>
                {formatExpiry(row.expiry)}
              </button>
              {#each row.values as value}
                <div class="cell data" style={`--heat:${Math.round(heatIntensity(value) * 72)}%;`}>
                  {pct(value)}
                </div>
              {/each}
            {/each}
          </div>
        {:else}
          <p class="muted">No options surface loaded.</p>
        {/if}
      </article>
      <article class="panel table-panel">
        <div class="table-header">
          <h3>Greeks / Pair Context</h3>
          {#if slice}<span>{formatExpiry(slice.expiry)}</span>{/if}
        </div>
        {#if selectedPairs.length}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Strike</th>
                  <th>Call IV</th>
                  <th>Put IV</th>
                  <th>Call Delta</th>
                  <th>Put Delta</th>
                  <th>Straddle</th>
                  <th>Move</th>
                </tr>
              </thead>
              <tbody>
                {#each selectedPairs as pair}
                  <tr>
                    <td>{fmt(pair.strike, 2)}</td>
                    <td>{pct(pair.call_implied_volatility)}</td>
                    <td>{pct(pair.put_implied_volatility)}</td>
                    <td>{fmt(pair.call_delta, 3)}</td>
                    <td>{fmt(pair.put_delta, 3)}</td>
                    <td>{fmt(pair.straddle_midpoint, 2)}</td>
                    <td>{pct(pair.implied_move_pct)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">No paired call/put context available for the selected expiry.</p>
        {/if}
      </article>

    </div>

    <div class="surface-summary-row">

      <article class="panel table-panel">
        <div class="table-header"><h3>ATM Term Structure</h3></div>
        {#if termStructure.length}
          <div class="table-scroll">
            <table>
              <thead><tr><th>Expiry</th><th>DTE</th><th>ATM IV</th></tr></thead>
              <tbody>
                {#each termStructure as point}
                  <tr>
                    <td>{formatExpiry(point.expiry)}</td>
                    <td>{daysToExpiry(point.expiry)}</td>
                    <td>{pct(point.iv)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">Load a surface to inspect ATM term structure.</p>
        {/if}
      </article>

      <article class="panel table-panel">
        <div class="table-header"><h3>Surface Context</h3></div>
        <div class="table-scroll">
          <table>
            <tbody>
              <tr><th>Selected Expiry</th><td>{formatExpiry(slice?.expiry)}</td></tr>
              <tr><th>ATM Strike</th><td>{fmt(surfaceStats.atmStrike, 2)}</td></tr>
              <tr><th>IV Range</th><td>{pct(surfaceStats.minIv)} - {pct(surfaceStats.maxIv)}</td></tr>
              <tr><th>Avg IV</th><td>{pct(surfaceStats.averageIv)}</td></tr>
              <tr><th>Grid</th><td>{result?.collection ? `${result.collection.selected_expiry_count}x${result.collection.selected_strike_count}` : "N/A"}</td></tr>
              <tr><th>Interpolation</th><td>{ratioPct(result?.quality?.interpolation_ratio)}</td></tr>
              <tr><th>Line Utilization</th><td>{ratioPct(result?.collection?.market_data_line_utilization)}</td></tr>
            </tbody>
          </table>
        </div>
      </article>
    </div>
  {:else if mode === "skew_term"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header"><h3>Skew By Expiry</h3></div>
        {#if skewRows.length}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Expiry</th>
                  <th>ATM</th>
                  <th>Put Wing</th>
                  <th>Call Wing</th>
                  <th>Put Skew</th>
                  <th>Call Skew</th>
                  <th>Wing Spread</th>
                </tr>
              </thead>
              <tbody>
                {#each skewRows as row}
                  <tr>
                    <td>{formatExpiry(row.expiry)}</td>
                    <td>{pct(row.atmIv)}</td>
                    <td>{fmt(row.putWingStrike, 2)} / {pct(row.putWingIv)}</td>
                    <td>{fmt(row.callWingStrike, 2)} / {pct(row.callWingIv)}</td>
                    <td class={toneClass(row.putSkew)}>{signedPct(row.putSkew)}</td>
                    <td class={toneClass(row.callSkew)}>{signedPct(row.callSkew)}</td>
                    <td class={toneClass(row.wingSpread)}>{signedPct(row.wingSpread)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">Load a surface to inspect skew.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Term Diagnostics</h3>
        <div class="metric-list">
          <div><span>Front Expiry</span><strong>{formatExpiry(surfaceStats.frontExpiry)}</strong></div>
          <div><span>Front DTE</span><strong>{surfaceStats.frontExpiry ? daysToExpiry(surfaceStats.frontExpiry) : 0}</strong></div>
          <div><span>Front ATM IV</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
          <div><span>Back ATM IV</span><strong>{pct(surfaceStats.backAtmIv)}</strong></div>
          <div><span>Back - Front</span><strong class={toneClass(surfaceStats.termSlope)}>{signedPct(surfaceStats.termSlope)}</strong></div>
        </div>
      </article>
    </div>
  {:else if mode === "realized_implied"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header"><h3>Realized vs Implied</h3></div>
        {#if realizedRows.some((row) => row.realizedVol != null)}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Window</th>
                  <th>Realized Vol</th>
                  <th>Front ATM IV</th>
                  <th>IV - RV</th>
                  <th>Obs</th>
                </tr>
              </thead>
              <tbody>
                {#each realizedRows as row}
                  <tr>
                    <td>{row.window}D</td>
                    <td>{pct(row.realizedVol)}</td>
                    <td>{pct(surfaceStats.frontAtmIv)}</td>
                    <td class={toneClass(row.spreadToFrontIv)}>{signedPct(row.spreadToFrontIv)}</td>
                    <td>{row.observationCount}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">Run or open a single-ticker Research context to compare realized history against the loaded options surface.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Data Boundary</h3>
        <div class="metric-list">
          <div><span>Implied Source</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
          <div><span>Realized Source</span><strong>{underlyingPricePoints.length ? "Research price history" : "N/A"}</strong></div>
          <div><span>Price Points</span><strong>{underlyingPricePoints.length}</strong></div>
          <div><span>Surface Freshness</span><strong>{result?.freshness_label ?? "unknown"}</strong></div>
        </div>
      </article>
    </div>
  {:else if mode === "distribution"}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Front Expiry Distribution Proxy</h3>
        {#if distributionBuckets.length}
          <div class="distribution">
            {#each distributionBuckets as bucket}
              <div class="dist-row">
                <span>{bucket.label}</span>
                <div class="bar"><div class="fill" style={`width:${(bucket.probability / maxDistributionProbability) * 100}%`}></div></div>
                <strong>{pct(bucket.probability, 1)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">Load a surface with spot and front ATM IV to inspect the first-pass distribution proxy.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Assumptions</h3>
        <div class="metric-list">
          <div><span>Method</span><strong>Lognormal proxy</strong></div>
          <div><span>Expiry</span><strong>{formatExpiry(surfaceStats.frontExpiry)}</strong></div>
          <div><span>Vol Input</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
        </div>
      </article>
    </div>
  {:else}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Provider Path</h3>
        <div class="metric-list">
          <div><span>Provider</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
          <div><span>Origin</span><strong>{result?.origin ?? "N/A"}</strong></div>
          <div><span>Freshness</span><strong>{result?.freshness_label ?? "unknown"}</strong></div>
          <div><span>Delayed</span><strong>{result?.delayed == null ? "unknown" : result.delayed ? "yes" : "no"}</strong></div>
          <div><span>Depth</span><strong>{depthLabel(result?.collection?.depth_preset)}</strong></div>
          <div><span>Line Budget</span><strong>{result?.collection ? `${result.collection.estimated_total_market_data_lines}/${result.collection.configured_market_data_line_budget}` : "N/A"}</strong></div>
          <div><span>Observed Cells</span><strong>{result?.quality ? `${result.quality.observed_surface_cells}/${result.quality.expected_surface_cells}` : "N/A"}</strong></div>
          <div><span>Retrieved</span><strong>{shortTime(result?.retrieved_at)}</strong></div>
        </div>
      </article>

      <article class="panel">
        <h3>Transformation</h3>
        <p class="note">{result?.transformation_note ?? "No surface transformation note available."}</p>
        <div class="warning-list">
          {#each result?.warnings ?? [] as warning}
            <div>{warning}</div>
          {/each}
          {#each result?.messages ?? [] as message}
            <div>{message}</div>
          {/each}
          {#if result?.collection?.contract_selection_note}
            <div>{result.collection.contract_selection_note}</div>
          {/if}
          {#if !(result?.warnings?.length || result?.messages?.length || result?.collection?.contract_selection_note)}
            <div class="muted">—</div>
          {/if}
        </div>
      </article>
    </div>
  {/if}
</section>

<style>
  .view,
  .workspace-grid,
  .surface-chart-row,
  .surface-data-row,
  .surface-summary-row,
  .detail-grid,
  .bar-list,
  .metric-list,
  .distribution,
  .warning-list {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-header,
  .panel-header,
  .surface-actions,
  .session-control,
  .source-strip,
  .bar-row,
  .dist-row,
  .metric-list > div {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .workspace-header {
    align-items: center;
  }

  .header-panel {
    display: grid;
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
  }

  .header-panel .header-top {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }

  .header-panel .title {
    color: var(--text-0);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .header-panel .subtitle {
    color: var(--text-2);
    font-size: 10.5px;
    letter-spacing: 0.04em;
  }

  .header-panel .mode-kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .header-panel .surface-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.45fr) minmax(18rem, 0.75fr);
    align-items: start;
  }

  .surface-grid {
    grid-template-columns: minmax(22rem, 0.9fr) minmax(0, 1.1fr);
  }

  .surface-chart-row {
    grid-template-columns: minmax(22rem, 0.95fr) minmax(22rem, 1.05fr);
  }

  .surface-data-row {
    grid-template-columns: minmax(0, 1.2fr) minmax(22rem, 0.8fr);
    align-items: start;
  }

  .surface-summary-row {
    grid-template-columns: minmax(0, 1fr) minmax(22rem, 1fr);
    align-items: start;
  }

  .detail-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    min-width: 0;
  }

  .eyebrow,
  .panel p,
  span,
  .muted,
  th {
    color: var(--text-2);
  }

  .eyebrow,
  th {
    font-size: 0.68rem;
    text-transform: uppercase;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.25rem;
  }

  h3 {
    font-size: 0.875rem;
  }

  strong {
    color: var(--text-0);
    font-weight: 650;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(5, auto);
    border: 1px solid var(--panel-strong);
    width: fit-content;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.28rem 0.65rem;
    font: inherit;
    font-size: 0.79rem;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  .controls-panel {
    display: grid;
    grid-template-columns: minmax(20rem, 0.9fr) minmax(0, 1.1fr);
    gap: 0.75rem;
    align-items: end;
  }

  .field-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 0.7fr;
    gap: 0.5rem;
  }

  label {
    display: grid;
    gap: 0.28rem;
  }

  input,
  select,
  button {
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.28rem 0.58rem;
    font: inherit;
    font-size: 0.84rem;
    border-radius: 2px;
  }

  button {
    cursor: pointer;
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
  }

  .surface-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: stretch;
  }

  .primary-action {
    border-color: rgba(122, 166, 200, 0.34);
    background: rgba(122, 166, 200, 0.08);
    min-width: 8.75rem;
  }

  .secondary-action {
    min-width: 8.75rem;
  }

  .session-control {
    align-items: stretch;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
  }

  .session-control > div {
    display: grid;
    gap: 0.05rem;
    min-width: 7.75rem;
    padding: 0.2rem 0.55rem;
    border-right: 1px solid var(--divider);
  }

  .session-control span {
    font-size: 0.66rem;
    text-transform: uppercase;
  }

  .session-control strong {
    font-size: 0.78rem;
    text-transform: uppercase;
  }

  .session-control.running strong {
    color: var(--accent);
  }

  .session-control.snapshot-only strong {
    color: var(--warning);
  }

  .session-control button {
    border: 0;
    border-radius: 0;
    background: transparent;
    min-width: 5.8rem;
  }

  .source-strip {
    flex-wrap: wrap;
    align-items: center;
  }

  .source-strip > div {
    min-width: 7rem;
    display: grid;
    gap: 0.12rem;
    text-align: right;
  }

  .surface-panel,
  .slice-chart-panel,
  .heatmap-panel {
    padding: 0;
  }

  .surface-panel .panel-header,
  .slice-chart-panel .panel-header,
  .heatmap-panel .panel-header {
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    min-height: 26px;
    align-items: center;
  }

  .surface-svg,
  .slice-svg {
    width: 100%;
    min-height: 18rem;
    background: var(--bg-0);
    display: block;
  }

  .surface-svg {
    cursor: grab;
  }

  .surface-svg.dragging {
    cursor: grabbing;
  }

  .surface-frame {
    stroke: var(--divider);
    stroke-width: 1;
  }

  .surface-svg line {
    stroke: var(--divider);
    stroke-width: 1;
  }

  .surface-gridlines line,
  .chart-gridlines line {
    stroke: var(--divider);
    stroke-width: 0.6;
    opacity: 0.45;
  }

  .surface-svg polygon {
    stroke-width: 0.3;
    vector-effect: non-scaling-stroke;
    transition: opacity 80ms;
    opacity: 0.85;
  }

  .surface-svg polygon.row-hovered {
    opacity: 1;
    stroke-width: 0;
  }

  .surface-svg .axis-label,
  .slice-svg .axis-label {
    fill: var(--text-2);
    font-size: 9px;
    font-family: monospace;
    pointer-events: none;
  }

  .surface-svg .hover-label {
    fill: var(--text-1);
    font-size: 11px;
    font-family: monospace;
    pointer-events: none;
  }

  .slice-area {
    fill: color-mix(in srgb, var(--chart-primary) 14%, transparent);
    stroke: none;
  }

  .slice-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
  }

  .slice-svg circle {
    fill: var(--bg-0);
    stroke: var(--chart-primary);
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }

  .slice-svg circle.spot {
    fill: var(--warning);
    stroke: var(--warning);
  }

  .slice-crosshair {
    stroke: var(--text-2);
    stroke-width: 0.5;
    stroke-dasharray: 3 3;
    pointer-events: none;
  }

  .slice-hover-dot {
    fill: var(--warning);
    stroke: none;
    pointer-events: none;
  }

  .slice-hover-label {
    fill: var(--text-1);
    font-size: 10px;
    font-family: monospace;
    pointer-events: none;
  }

  .heatmap {
    display: grid;
    grid-template-columns: 7rem repeat(var(--strike-count, 1), minmax(3.6rem, 1fr));
    gap: 0;
    overflow: auto;
  }

  .cell {
    border-right: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
    padding: 0.28rem 0.36rem;
    min-height: 1.75rem;
    text-align: center;
    white-space: nowrap;
  }

  .header {
    background: var(--bg-1);
    color: var(--text-2);
  }

  .spot {
    color: var(--warning);
  }

  .expiry {
    color: var(--text-1);
    border-radius: 0;
  }

  .expiry.active {
    color: var(--accent);
    background: rgba(122, 166, 200, 0.08);
  }

  .data {
    background: color-mix(in srgb, var(--chart-primary) var(--heat), var(--bg-0));
    color: var(--text-0);
    font-weight: 650;
  }

  .bar-row,
  .dist-row,
  .metric-list > div,
  .warning-list > div {
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: 0.3rem;
  }

  .bar,
  .fill {
    height: 0.5rem;
  }

  .bar {
    flex: 1;
    min-width: 5rem;
    background: var(--panel-strong);
  }

  .fill {
    background: var(--chart-primary);
  }

  .table-panel {
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  .table-panel > .muted {
    padding: 0.5rem 0.75rem;
  }

  .table-header {
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    height: 26px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .table-header h3 {
    margin: 0;
  }

  .table-wrap,
  .table-scroll {
    overflow-y: auto;
    max-height: 280px;
  }

  .surface-summary-row {
    align-items: stretch;
  }

  .surface-summary-row .table-panel {
    overflow: hidden;
  }

  .surface-summary-row .table-scroll {
    flex: 1;
    max-height: none;
    min-height: 0;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    padding: 0.28rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    letter-spacing: 0.08em;
    font-size: 0.69rem;
  }

  td {
    padding: 0.3rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    color: var(--text-1);
  }

  tr:hover td {
    background: rgba(122, 166, 200, 0.06);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .note {
    color: var(--text-1);
    line-height: 1.5;
  }

  @media (max-width: 1140px) {
    .workspace-header,
    .workspace-grid,
    .surface-grid,
    .surface-chart-row,
    .surface-data-row,
    .surface-summary-row,
    .detail-grid,
    .controls-panel,
    .field-grid {
      grid-template-columns: 1fr;
    }

    .workspace-header,
    .surface-actions,
    .source-strip {
      align-items: stretch;
      flex-direction: column;
    }

    .source-strip > div {
      text-align: left;
    }

    .mode-bar {
      grid-template-columns: 1fr;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }

    .mode-bar button:last-child {
      border-bottom: 0;
    }
  }
</style>
