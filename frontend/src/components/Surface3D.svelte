<script lang="ts" context="module">
  type RGB = [number, number, number];
  export type SurfaceModel = "linear" | "spline" | "ssvi";

  export const SURFACE_MODEL_OPTIONS: Array<{ id: SurfaceModel; label: string }> = [
    { id: "linear", label: "Line interpolation" },
    { id: "spline", label: "Spline interpolation" },
    { id: "ssvi", label: "SSVI" },
  ];

  export const SURFACE_COLORMAPS: Record<string, RGB[]> = {
    viridis: [
      [68, 1, 84],
      [59, 82, 139],
      [33, 145, 140],
      [94, 201, 98],
      [253, 231, 37],
    ],
    magma: [
      [0, 0, 4],
      [81, 18, 124],
      [183, 55, 121],
      [252, 137, 97],
      [252, 253, 191],
    ],
    plasma: [
      [13, 8, 135],
      [126, 3, 168],
      [204, 71, 120],
      [248, 149, 64],
      [240, 249, 33],
    ],
    turbo: [
      [48, 18, 59],
      [33, 144, 215],
      [60, 232, 130],
      [225, 220, 55],
      [165, 14, 1],
    ],
  };

  function sampleStops(stops: RGB[], t: number): RGB {
    const clamped = Math.max(0, Math.min(1, t));
    const n = stops.length - 1;
    const f = clamped * n;
    const i = Math.min(n - 1, Math.floor(f));
    const u = f - i;
    const a = stops[i];
    const b = stops[i + 1];
    return [
      Math.round(a[0] + (b[0] - a[0]) * u),
      Math.round(a[1] + (b[1] - a[1]) * u),
      Math.round(a[2] + (b[2] - a[2]) * u),
    ];
  }
</script>

<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  export let strikes: number[] = [];
  export let expiries: string[] = [];
  export let grid: Array<Array<number | null>> = [];
  export let dte: number[] = [];
  export let atmStrikeIndex = -1;
  export let height = 380;
  export let surfaceModel: SurfaceModel = "linear";
  export let surfaceModelStatus: string | null = null;
  export let modelLoading = false;
  export let valueAxisLabel = "IV";
  export let emptyMessage = "Load a max-depth surface to render the volatility surface.";
  export let formatValue: (value: number) => string = (value) => `${(value * 100).toFixed(1)}%`;
  export let onSurfaceModelChange: (model: SurfaceModel) => void | Promise<void> = () => {};

  type RenderMode = "surface" | "wireframe" | "points";
  let colormap: keyof typeof SURFACE_COLORMAPS = "viridis";
  let renderMode: RenderMode = "surface";
  let showGrid = true;
  let settingsOpen = false;

  // Camera — default to a gentle isometric view, nearest expiry to the front.
  const DEFAULT_YAW = -0.72;
  const DEFAULT_PITCH = 0.6;
  const DEFAULT_ZOOM = 1.18;
  const ORBIT_SENSITIVITY = 0.005;
  const ZOOM_STEP = 1.06;
  let yaw = DEFAULT_YAW;
  let pitch = DEFAULT_PITCH;
  let zoom = DEFAULT_ZOOM;
  let hoverPick: { sx: number; sy: number; strike: number; dte: number; iv: number } | null = null;

  let canvas: HTMLCanvasElement;
  let wrap: HTMLDivElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let cssW = 0;
  let cssH = 0;
  let raf = 0;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let observer: ResizeObserver | null = null;

  let vMin = 0;
  let vMax = 1;

  const theme = {
    text: "#8a919a",
    grid: "rgba(50,56,64,0.55)",
    axis: "#2e353e",
    panel: "#0b0d10",
    accent: "#7aa6c8",
  };

  $: rows = grid.length;
  $: cols = strikes.length;
  $: hasData = rows >= 2 && cols >= 2;
  $: legendGradient = `linear-gradient(90deg, ${SURFACE_COLORMAPS[colormap]
    .map((c, i, arr) => `rgb(${c[0]},${c[1]},${c[2]}) ${(i / (arr.length - 1)) * 100}%`)
    .join(", ")})`;

  $: if (ctx && grid) {
    computeRange();
    scheduleRender();
  }

  $: if (ctx) {
    // re-render when display settings change
    colormap;
    renderMode;
    showGrid;
    scheduleRender();
  }

  function computeRange() {
    let lo = Infinity;
    let hi = -Infinity;
    for (const row of grid) {
      for (const v of row) {
        if (v != null && Number.isFinite(v) && v > 0) {
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
      }
    }
    if (lo === Infinity) {
      vMin = 0;
      vMax = 1;
    } else {
      vMin = lo;
      vMax = hi > lo ? hi : lo + 0.01;
    }
  }

  function readTheme() {
    const styles = getComputedStyle(document.documentElement);
    const get = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    theme.text = get("--text-2", theme.text);
    theme.grid = get("--divider", theme.grid);
    theme.axis = get("--panel-strong", theme.axis);
    theme.panel = get("--bg-1", theme.panel);
    theme.accent = get("--accent", theme.accent);
  }

  function gx(j: number) {
    return cols <= 1 ? 0 : (j / (cols - 1)) * 2 - 1;
  }
  function gz(i: number) {
    return rows <= 1 ? 0 : (i / (rows - 1)) * 2 - 1;
  }
  function gy(v: number | null | undefined) {
    if (v == null || !Number.isFinite(v)) return -0.45;
    const range = vMax - vMin || 1;
    return ((v - vMin) / range) * 0.9 - 0.45;
  }

  type Projected = { sx: number; sy: number; depth: number };

  function makeProjector(): (x: number, y: number, z: number) => Projected {
    const cx = cssW / 2;
    const cy = cssH / 2 + cssH * 0.04;
    const scale = Math.min(cssW, cssH) * 0.4 * zoom;
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const cosP = Math.cos(pitch);
    const sinP = Math.sin(pitch);
    return (x, y, z) => {
      const x1 = x * cosY - z * sinY;
      const z1 = x * sinY + z * cosY;
      // Conventional surface orientation: IV (y) up, near-DTE edge toward the
      // viewer at the bottom-front, far DTE receding up and back.
      const sy = cy - (y * cosP + z1 * sinP) * scale;
      const depth = z1 * cosP - y * sinP;
      return { sx: cx + x1 * scale, sy, depth };
    };
  }

  function color(t: number) {
    const c = sampleStops(SURFACE_COLORMAPS[colormap], t);
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  function drawPlaneGrid(
    project: (x: number, y: number, z: number) => Projected,
    origin: RGB,
    uEnd: RGB,
    vEnd: RGB,
    divisions = 6
  ) {
    if (!ctx) return;
    ctx.strokeStyle = theme.grid;
    ctx.lineWidth = 1;
    for (let s = 0; s <= divisions; s += 1) {
      const t = s / divisions;
      // lines along v
      let a = project(
        origin[0] + (uEnd[0] - origin[0]) * t,
        origin[1] + (uEnd[1] - origin[1]) * t,
        origin[2] + (uEnd[2] - origin[2]) * t
      );
      let b = project(
        origin[0] + (uEnd[0] - origin[0]) * t + (vEnd[0] - origin[0]),
        origin[1] + (uEnd[1] - origin[1]) * t + (vEnd[1] - origin[1]),
        origin[2] + (uEnd[2] - origin[2]) * t + (vEnd[2] - origin[2])
      );
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();
      // lines along u
      a = project(
        origin[0] + (vEnd[0] - origin[0]) * t,
        origin[1] + (vEnd[1] - origin[1]) * t,
        origin[2] + (vEnd[2] - origin[2]) * t
      );
      b = project(
        origin[0] + (vEnd[0] - origin[0]) * t + (uEnd[0] - origin[0]),
        origin[1] + (vEnd[1] - origin[1]) * t + (uEnd[1] - origin[1]),
        origin[2] + (vEnd[2] - origin[2]) * t + (uEnd[2] - origin[2])
      );
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();
    }
  }

  function drawGrids(project: (x: number, y: number, z: number) => Projected) {
    const lo = -0.45;
    const hi = 0.45;
    // Floor
    drawPlaneGrid(project, [-1, lo, -1], [1, lo, -1], [-1, lo, 1]);
    // Pick far walls by depth.
    const farX = project(1, 0, 0).depth > project(-1, 0, 0).depth ? 1 : -1;
    const farZ = project(0, 0, 1).depth > project(0, 0, -1).depth ? 1 : -1;
    // Wall at x = farX (spans z and y)
    drawPlaneGrid(project, [farX, lo, -1], [farX, lo, 1], [farX, hi, -1]);
    // Wall at z = farZ (spans x and y)
    drawPlaneGrid(project, [-1, lo, farZ], [1, lo, farZ], [-1, hi, farZ]);
  }

  function drawSurface(project: (x: number, y: number, z: number) => Projected, wireframe: boolean) {
    if (!ctx) return;
    type Quad = { pts: Projected[]; depth: number; t: number };
    const quads: Quad[] = [];
    for (let i = 0; i < rows - 1; i += 1) {
      for (let j = 0; j < cols - 1; j += 1) {
        const v00 = grid[i]?.[j];
        const v01 = grid[i]?.[j + 1];
        const v11 = grid[i + 1]?.[j + 1];
        const v10 = grid[i + 1]?.[j];
        const valid = [v00, v01, v11, v10].every((v) => v != null && Number.isFinite(v) && v > 0);
        if (!valid) continue;
        const p00 = project(gx(j), gy(v00), gz(i));
        const p01 = project(gx(j + 1), gy(v01), gz(i));
        const p11 = project(gx(j + 1), gy(v11), gz(i + 1));
        const p10 = project(gx(j), gy(v10), gz(i + 1));
        const depth = (p00.depth + p01.depth + p11.depth + p10.depth) / 4;
        const avg = ((v00 as number) + (v01 as number) + (v11 as number) + (v10 as number)) / 4;
        const t = (avg - vMin) / (vMax - vMin || 1);
        quads.push({ pts: [p00, p01, p11, p10], depth, t });
      }
    }
    quads.sort((a, b) => b.depth - a.depth);
    for (const q of quads) {
      ctx.beginPath();
      ctx.moveTo(q.pts[0].sx, q.pts[0].sy);
      for (let k = 1; k < q.pts.length; k += 1) ctx.lineTo(q.pts[k].sx, q.pts[k].sy);
      ctx.closePath();
      if (wireframe) {
        ctx.strokeStyle = color(q.t);
        ctx.lineWidth = 1;
        ctx.stroke();
      } else {
        ctx.fillStyle = color(q.t);
        ctx.fill();
        ctx.strokeStyle = "rgba(7,8,9,0.35)";
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
  }

  function drawPoints(project: (x: number, y: number, z: number) => Projected) {
    if (!ctx) return;
    type Pt = { p: Projected; t: number };
    const pts: Pt[] = [];
    for (let i = 0; i < rows; i += 1) {
      for (let j = 0; j < cols; j += 1) {
        const v = grid[i]?.[j];
        if (v == null || !Number.isFinite(v) || v <= 0) continue;
        pts.push({ p: project(gx(j), gy(v), gz(i)), t: ((v as number) - vMin) / (vMax - vMin || 1) });
      }
    }
    pts.sort((a, b) => b.p.depth - a.p.depth);
    const r = Math.max(2.2, Math.min(cssW, cssH) * 0.012);
    for (const { p, t } of pts) {
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = color(t);
      ctx.fill();
    }
  }

  function drawLabels(project: (x: number, y: number, z: number) => Projected) {
    if (!ctx || !strikes.length || !rows) return;
    ctx.fillStyle = theme.text;
    ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
    const lo = -0.45;
    const minStrike = strikes[0];
    const maxStrike = strikes[strikes.length - 1];
    // Strike axis along the front-bottom edge (nearest DTE, z = -1).
    const sxA = project(-1, lo, -1);
    const sxB = project(1, lo, -1);
    ctx.textAlign = "center";
    ctx.fillText(`${Math.round(minStrike)}`, sxA.sx, sxA.sy + 12);
    ctx.fillText(`${Math.round(maxStrike)}`, sxB.sx, sxB.sy + 12);
    const sMid = project(0, lo, -1);
    ctx.fillText("STRIKE", sMid.sx, sMid.sy + 23);
    // DTE axis up the right edge: nearest at the front-bottom, farthest at the back-top.
    const nearLabel = dte[0] != null ? `${dte[0]}D` : "near";
    const farLabel = dte[rows - 1] != null ? `${dte[rows - 1]}D` : "far";
    const ezNear = project(1, lo, -1);
    const ezFar = project(1, lo, 1);
    ctx.textAlign = "left";
    ctx.fillText(nearLabel, ezNear.sx + 8, ezNear.sy + 2);
    ctx.fillText(farLabel, ezFar.sx + 8, ezFar.sy);
    // IV axis (vertical) at the back-left corner.
    const ivTop = project(-1, 0.45, 1);
    const ivBot = project(-1, lo, 1);
    ctx.textAlign = "right";
    ctx.fillText(formatValue(vMax), ivTop.sx - 6, ivTop.sy);
    ctx.fillText(formatValue(vMin), ivBot.sx - 6, ivBot.sy);
    ctx.fillText(valueAxisLabel.toUpperCase(), ivTop.sx - 6, ivTop.sy - 12);
  }

  function render() {
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    if (!hasData) return;
    const project = makeProjector();
    if (showGrid) drawGrids(project);
    if (renderMode === "points") drawPoints(project);
    else drawSurface(project, renderMode === "wireframe");
    drawLabels(project);
    if (hoverPick) {
      ctx.beginPath();
      ctx.arc(hoverPick.sx, hoverPick.sy, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = theme.accent;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = "rgba(240,242,245,0.85)";
      ctx.stroke();
    }
  }

  function scheduleRender() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      render();
    });
  }

  function resize() {
    if (!canvas || !wrap) return;
    const rect = wrap.getBoundingClientRect();
    cssW = rect.width;
    cssH = rect.height;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.width = `${cssW}px`;
    canvas.style.height = `${cssH}px`;
    scheduleRender();
  }

  function onPointerDown(event: PointerEvent) {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch {
      // ignore (synthetic events / unsupported)
    }
  }
  function onPointerMove(event: PointerEvent) {
    if (dragging) {
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      yaw += dx * ORBIT_SENSITIVITY;
      pitch = Math.max(-0.2, Math.min(1.35, pitch + dy * ORBIT_SENSITIVITY));
      if (hoverPick) hoverPick = null;
      scheduleRender();
      return;
    }
    const rect = canvas.getBoundingClientRect();
    pickNearest(event.clientX - rect.left, event.clientY - rect.top);
  }
  function pickNearest(mx: number, my: number) {
    if (!hasData) return;
    const project = makeProjector();
    let best: typeof hoverPick = null;
    let bestDist = 15 * 15;
    for (let i = 0; i < rows; i += 1) {
      for (let j = 0; j < cols; j += 1) {
        const v = grid[i]?.[j];
        if (v == null || !Number.isFinite(v) || v <= 0) continue;
        const p = project(gx(j), gy(v), gz(i));
        const dx = p.sx - mx;
        const dy = p.sy - my;
        const d = dx * dx + dy * dy;
        if (d < bestDist) {
          bestDist = d;
          best = { sx: p.sx, sy: p.sy, strike: strikes[j], dte: dte[i] ?? 0, iv: v };
        }
      }
    }
    if (best?.strike !== hoverPick?.strike || best?.dte !== hoverPick?.dte || !!best !== !!hoverPick) {
      hoverPick = best;
      scheduleRender();
    }
  }
  function onPointerUp(event: PointerEvent) {
    dragging = false;
    try {
      canvas.releasePointerCapture(event.pointerId);
    } catch {
      // ignore
    }
  }
  function onPointerLeave(event: PointerEvent) {
    onPointerUp(event);
    if (hoverPick) {
      hoverPick = null;
      scheduleRender();
    }
  }
  function onWheel(event: WheelEvent) {
    event.preventDefault();
    zoom = Math.max(0.45, Math.min(3, zoom * (event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP)));
    scheduleRender();
  }
  function resetView() {
    yaw = DEFAULT_YAW;
    pitch = DEFAULT_PITCH;
    zoom = DEFAULT_ZOOM;
    scheduleRender();
  }

  function chooseSurfaceModel(event: Event) {
    const next = (event.currentTarget as HTMLSelectElement).value as SurfaceModel;
    if (next === surfaceModel) {
      return;
    }
    void onSurfaceModelChange(next);
  }

  onMount(() => {
    ctx = canvas.getContext("2d");
    readTheme();
    observer = new ResizeObserver(() => resize());
    observer.observe(wrap);
    resize();
  });

  onDestroy(() => {
    if (raf) cancelAnimationFrame(raf);
    observer?.disconnect();
  });
</script>

<div class="surface3d" style={`--surface-h:${height}px`}>
  <div class="surface3d-toolbar">
    <span class="surface3d-hint">
      {#if hoverPick}
        <strong class="pick">{Math.round(hoverPick.strike)} · {hoverPick.dte}D · {formatValue(hoverPick.iv)}</strong>
      {:else}
        Drag to orbit · scroll to zoom
      {/if}
    </span>
    <button
      type="button"
      class="gear"
      class:active={settingsOpen}
      aria-label="Surface settings"
      on:click={() => (settingsOpen = !settingsOpen)}
    >⚙</button>
    {#if settingsOpen}
      <div class="surface3d-settings">
        <label>
          <span>Fit</span>
          <select value={surfaceModel} on:change={chooseSurfaceModel} disabled={modelLoading}>
            {#each SURFACE_MODEL_OPTIONS as option}
              <option value={option.id}>{option.label}</option>
            {/each}
          </select>
        </label>
        {#if surfaceModelStatus && surfaceModelStatus !== "applied"}
          <div class="model-status">{surfaceModelStatus}</div>
        {/if}
        <label>
          <span>Colormap</span>
          <select bind:value={colormap}>
            <option value="viridis">Viridis</option>
            <option value="magma">Magma</option>
            <option value="plasma">Plasma</option>
            <option value="turbo">Turbo</option>
          </select>
        </label>
        <label>
          <span>Render</span>
          <select bind:value={renderMode}>
            <option value="surface">Surface</option>
            <option value="wireframe">Wireframe</option>
            <option value="points">Points</option>
          </select>
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={showGrid} />
          <span>Grid planes</span>
        </label>
        <button type="button" class="reset" on:click={resetView}>Reset view</button>
      </div>
    {/if}
  </div>

  <div class="surface3d-canvas" bind:this={wrap}>
    {#if !hasData}
      <p class="surface3d-empty">{emptyMessage}</p>
    {/if}
    <canvas
      bind:this={canvas}
      on:pointerdown={onPointerDown}
      on:pointermove={onPointerMove}
      on:pointerup={onPointerUp}
      on:pointerleave={onPointerLeave}
      on:wheel={onWheel}
    ></canvas>
  </div>

  <div class="surface3d-legend">
    <span>{formatValue(vMin)}</span>
    <div class="legend-bar" style={`background:${legendGradient}`}></div>
    <span>{formatValue(vMax)}</span>
  </div>
</div>

<style>
  .surface3d {
    position: relative;
    display: grid;
    grid-template-rows: auto var(--surface-h) auto;
  }

  .surface3d-toolbar {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-1) var(--space-3);
  }

  .surface3d-hint {
    margin-right: auto;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-2);
  }

  .surface3d-hint .pick {
    color: var(--accent);
    font-weight: 600;
  }

  .gear {
    background: transparent;
    border: 1px solid var(--panel-strong);
    color: var(--text-1);
    width: 26px;
    height: 24px;
    border-radius: 2px;
    cursor: pointer;
    font-size: var(--text-md);
    line-height: 1;
  }

  .gear.active {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  }

  .surface3d-settings {
    position: absolute;
    top: 28px;
    right: 0;
    z-index: 5;
    display: grid;
    gap: var(--space-4);
    padding: var(--space-4);
    min-width: 11rem;
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
  }

  .surface3d-settings label {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .surface3d-settings label.checkbox {
    grid-template-columns: auto 1fr;
    justify-items: start;
  }

  .surface3d-settings select {
    background: var(--bg-0);
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    font: inherit;
    font-size: var(--text-sm);
    padding: var(--space-1) var(--space-3);
    border-radius: 2px;
  }

  .surface3d-settings input[type="checkbox"] {
    accent-color: var(--accent);
  }

  .surface3d-settings .reset {
    background: var(--bg-0);
    border: 1px solid var(--panel-strong);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border-radius: 2px;
    cursor: pointer;
  }

  .surface3d-settings .model-status {
    color: var(--warning);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .surface3d-canvas {
    position: relative;
    width: 100%;
    height: var(--surface-h);
    overflow: hidden;
  }

  .surface3d-canvas canvas {
    display: block;
    touch-action: none;
    cursor: grab;
  }

  .surface3d-canvas canvas:active {
    cursor: grabbing;
  }

  .surface3d-empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-base);
  }

  .surface3d-legend {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-4) var(--space-1) var(--space-1);
    font-size: var(--text-xs);
    color: var(--text-2);
  }

  .legend-bar {
    flex: 1;
    height: 0.5rem;
    border: 1px solid var(--panel-border);
  }
</style>
