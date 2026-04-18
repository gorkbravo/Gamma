<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import maplibregl from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import type {
    MaritimeAisPosition,
    MaritimeChokepointDefinition,
    MaritimePort,
    MaritimeVesselStatic,
  } from "../lib/api/types";

  export let positions: MaritimeAisPosition[] = [];
  export let vessels: MaritimeVesselStatic[] = [];
  export let ports: MaritimePort[] = [];
  export let chokepoints: MaritimeChokepointDefinition[] = [];
  export let is3D = false;
  export let connected = false;

  // Design token values used for map layer styling
  const BG0 = "#070809";
  const ACCENT = "#7aa6c8";
  const SECONDARY = "#c49a5a";
  const TEXT2 = "#8a919a";

  let container: HTMLDivElement;
  let map: maplibregl.Map | null = null;
  let popup: maplibregl.Popup | null = null;
  let mapReady = false;
  let mapZoom = 1.5;

  $: vesselIndex = Object.fromEntries(vessels.map((v) => [v.vessel_id, v]));

  function vesselFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: positions
        .filter((p) => p.latitude != null && p.longitude != null)
        .map((p) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [p.longitude, p.latitude] },
          properties: {
            vessel_id: p.vessel_id,
            name: vesselIndex[p.vessel_id]?.name ?? p.vessel_id,
            vessel_class: vesselIndex[p.vessel_id]?.vessel_class ?? "Unknown",
            vessel_type: vesselIndex[p.vessel_id]?.vessel_type ?? "Unknown",
            speed_knots: p.speed_knots ?? null,
            navigation_status: p.navigation_status ?? null,
            mmsi: p.mmsi,
            heading: p.heading ?? 0,
          },
        })),
    };
  }

  function portFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: ports.map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.longitude, p.latitude] },
        properties: { name: p.name, country: p.country, terminal_type: p.terminal_type ?? "Port" },
      })),
    };
  }

  function chokepointFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: chokepoints.map((c) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [c.longitude, c.latitude] },
        properties: { name: c.name, region: c.region },
      })),
    };
  }

  function pushSources() {
    if (!map || !mapReady) return;
    (map.getSource("vessels") as maplibregl.GeoJSONSource | undefined)?.setData(vesselFeatureCollection() as never);
    (map.getSource("ports") as maplibregl.GeoJSONSource | undefined)?.setData(portFeatureCollection() as never);
    (map.getSource("chokepoints") as maplibregl.GeoJSONSource | undefined)?.setData(chokepointFeatureCollection() as never);
  }

  function applyProjection() {
    if (!map) return;
    try {
      // MapLibre GL v3+ supports globe projection
      (map as Record<string, unknown> & { setProjection?: (p: unknown) => void }).setProjection?.(
        is3D ? { type: "globe" } : { type: "mercator" }
      );
    } catch {
      /* older version — ignore */
    }
  }

  // CartoDB dark-matter-nolabels is already near-black; no color overrides needed.

  onMount(() => {
    map = new maplibregl.Map({
      container,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
      center: [10, 20],
      zoom: 1.5,
      attributionControl: false,
    });

    popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: "240px",
      anchor: "bottom",
    });

    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right"
    );

    map.on("zoom", () => { mapZoom = map?.getZoom() ?? mapZoom; });

    map.on("load", () => {
      if (!map) return;

      // ── Shipping lanes (static, no interaction) ───────────────
      map.addSource("shipping-lanes", {
        type: "geojson",
        data: "/shipping-lanes.geojson",
      });
      map.addLayer({
        id: "shipping-lanes-line",
        type: "line",
        source: "shipping-lanes",
        paint: {
          "line-color": "#1a3a5c",
          "line-opacity": 0.5,
          "line-width": 1,
        },
      });

      // ── Vessels ──────────────────────────────────────────────
      map.addSource("vessels", { type: "geojson", data: vesselFeatureCollection() as never });

      // Outer halo for visibility on any background
      map.addLayer({
        id: "vessels-halo",
        type: "circle",
        source: "vessels",
        paint: {
          "circle-color": ACCENT,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 7, 8, 18],
          "circle-opacity": 0.1,
          "circle-stroke-width": 0,
        },
      });

      // Main vessel dot
      map.addLayer({
        id: "vessels-dot",
        type: "circle",
        source: "vessels",
        paint: {
          "circle-color": ACCENT,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3, 8, 6],
          "circle-stroke-color": BG0,
          "circle-stroke-width": 1,
          "circle-opacity": 0.95,
        },
      });

      // ── Ports ─────────────────────────────────────────────────
      map.addSource("ports", { type: "geojson", data: portFeatureCollection() as never });
      map.addLayer({
        id: "ports-dot",
        type: "circle",
        source: "ports",
        paint: {
          "circle-color": SECONDARY,
          "circle-radius": 3.5,
          "circle-stroke-color": BG0,
          "circle-stroke-width": 1,
          "circle-opacity": 0.8,
        },
      });

      // ── Chokepoints ───────────────────────────────────────────
      map.addSource("chokepoints", { type: "geojson", data: chokepointFeatureCollection() as never });
      map.addLayer({
        id: "chokepoints-labels",
        type: "symbol",
        source: "chokepoints",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 9,
          "text-anchor": "top",
          "text-offset": [0, 0.5],
          "text-allow-overlap": false,
        },
        paint: {
          "text-color": TEXT2,
          "text-halo-color": BG0,
          "text-halo-width": 1.5,
        },
      });

      // ── Hover interaction ─────────────────────────────────────
      map.on("mouseenter", "vessels-dot", (e) => {
        if (!map || !popup || !e.features?.length) return;
        map.getCanvas().style.cursor = "crosshair";
        const f = e.features[0];
        const props = f.properties as Record<string, unknown>;
        const coords = (f.geometry as { coordinates: [number, number] }).coordinates;
        const speed =
          props.speed_knots != null
            ? `${Number(props.speed_knots).toFixed(1)} kn`
            : "N/A";
        const typeLabel = String(props.vessel_type ?? "").replace(/_/g, " ");
        popup
          .setLngLat(coords)
          .setHTML(
            `<div class="mp-inner">
              <strong class="mp-name">${escapeHtml(String(props.name ?? ""))}</strong>
              <div class="mp-row"><span>Class</span><span>${escapeHtml(String(props.vessel_class ?? ""))}</span></div>
              <div class="mp-row"><span>Type</span><span>${escapeHtml(typeLabel)}</span></div>
              <div class="mp-row"><span>Speed</span><span>${speed}</span></div>
              <div class="mp-row"><span>Status</span><span>${escapeHtml(String(props.navigation_status ?? "N/A"))}</span></div>
              <div class="mp-row"><span>MMSI</span><span>${escapeHtml(String(props.mmsi ?? ""))}</span></div>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseleave", "vessels-dot", () => {
        if (!map || !popup) return;
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      mapReady = true;
    });
  });

  onDestroy(() => {
    popup?.remove();
    map?.remove();
  });

  function escapeHtml(s: string) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Push new data whenever props change and map is ready
  $: if (mapReady) void (positions, vessels, ports, chokepoints, pushSources());
  $: if (mapReady) applyProjection();
  $: connDotActive = connected && mapZoom >= 4;
</script>

<div class="map-wrap">
  <div bind:this={container} class="map-container"></div>

  <!-- HUD: vessel count + connection status -->
  <div class="map-hud">
    <div class="hud-row">
      <span class="hud-label">Vessels</span>
      <span class="hud-value">{positions.length}</span>
    </div>
    <div class="hud-row">
      <span class="conn-dot" class:active={connDotActive}></span>
      <span class="hud-label">{connDotActive ? "Live" : "Offline"}</span>
    </div>
  </div>

  <!-- Bottom-left: legend + 3D toggle -->
  <div class="map-bottom">
    <div class="map-legend">
      <span class="legend-item vessel">Vessel</span>
      <span class="legend-item port">Port</span>
      <span class="legend-item choke">Chokepoint</span>
    </div>
    <button
      type="button"
      class="map-ctrl-btn"
      class:active={is3D}
      on:click={() => { is3D = !is3D; applyProjection(); }}
      title={is3D ? "Switch to 2D flat" : "Switch to 3D globe"}
    >{is3D ? "2D" : "3D"}</button>
  </div>
</div>

<style>
  .map-wrap {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .map-container {
    position: absolute;
    inset: 0;
  }

  /* ── HUD (top-right) ─────────────────────────────────────── */
  .map-hud {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    z-index: 10;
    background: color-mix(in srgb, var(--bg-0, #070809) 88%, transparent);
    border: 1px solid var(--panel-border, #1e2228);
    padding: 0.38rem 0.65rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .hud-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    white-space: nowrap;
  }

  .hud-label {
    color: var(--text-2, #8a919a);
  }

  .hud-value {
    color: var(--text-0, #f0f2f5);
    font-weight: 600;
    margin-left: auto;
    padding-left: 0.8rem;
  }

  .conn-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #475569;
    flex-shrink: 0;
  }

  .conn-dot.active {
    background: #22c55e;
  }

  /* ── Bottom-left: legend + 3D toggle ─────────────────────── */
  .map-bottom {
    position: absolute;
    bottom: 1.8rem; /* clear MapLibre attribution */
    left: 0.6rem;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .map-legend {
    display: flex;
    gap: 0.9rem;
    background: color-mix(in srgb, var(--bg-0, #070809) 90%, transparent);
    border: 1px solid var(--panel-border, #1e2228);
    padding: 0.28rem 0.65rem;
  }

  .legend-item {
    font-size: 0.6rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--text-2, #8a919a);
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .legend-item::before {
    content: "";
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .legend-item.vessel::before { background: var(--accent, #7aa6c8); }
  .legend-item.port::before   { background: var(--chart-secondary, #c49a5a); }
  .legend-item.choke::before  { background: transparent; border: 1px solid var(--text-2, #8a919a); }

  .map-ctrl-btn {
    background: color-mix(in srgb, var(--bg-0, #070809) 90%, transparent);
    border: 1px solid var(--panel-border, #1e2228);
    color: var(--text-2, #8a919a);
    font: inherit;
    font-size: 0.6rem;
    padding: 0.28rem 0.55rem;
    cursor: pointer;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }

  .map-ctrl-btn:hover,
  .map-ctrl-btn.active {
    color: var(--accent, #7aa6c8);
    border-color: color-mix(in srgb, var(--accent, #7aa6c8) 40%, var(--panel-border, #1e2228));
  }

  /* ── MapLibre GL popup overrides ── */
  :global(.maplibregl-popup-content) {
    background: var(--bg-1, #0b0d10) !important;
    border: 1px solid var(--panel-border, #1e2228) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
    font-family: "JetBrains Mono", "Cascadia Mono", "IBM Plex Mono", "Consolas", monospace !important;
  }

  :global(.maplibregl-popup-tip) {
    display: none !important;
  }

  :global(.mp-inner) {
    padding: 0.55rem 0.75rem;
    min-width: 180px;
  }

  :global(.mp-name) {
    display: block;
    color: var(--text-0, #f0f2f5);
    font-size: 0.8rem;
    margin-bottom: 0.4rem;
    padding-bottom: 0.32rem;
    border-bottom: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
  }

  :global(.mp-row) {
    display: flex;
    justify-content: space-between;
    gap: 1.2rem;
    padding: 0.1rem 0;
    font-size: 0.7rem;
  }

  :global(.mp-row span:first-child) {
    color: var(--text-2, #8a919a);
    text-transform: uppercase;
    letter-spacing: 0.07em;
    flex-shrink: 0;
  }

  :global(.mp-row span:last-child) {
    color: var(--text-0, #f0f2f5);
    text-align: right;
  }

  /* Keep MapLibre attribution minimal */
  :global(.maplibregl-ctrl-attrib) {
    background: color-mix(in srgb, #070809 88%, transparent) !important;
    font-size: 0.58rem !important;
  }

  :global(.maplibregl-ctrl-attrib a) {
    color: var(--text-2, #8a919a) !important;
  }
</style>
