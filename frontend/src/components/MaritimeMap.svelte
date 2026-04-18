<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import maplibregl from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import { WS_BASE } from "../lib/api/client";
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
  const BG0 = "#02060c";
  const ACCENT = "#7aa6c8";
  const SECONDARY = "#c49a5a";
  const TEXT2 = "#8a919a";
  const AIS_ZOOM_THRESHOLD = 4;
  const VIEWPORT_DEBOUNCE_MS = 1500;
  const MAX_LIVE_POSITIONS = 600;

  let container: HTMLDivElement;
  let map: maplibregl.Map | null = null;
  let popup: maplibregl.Popup | null = null;
  let mapReady = false;
  let mapZoom = 3;
  let viewportDebounce: ReturnType<typeof setTimeout> | null = null;
  let liveSocket: WebSocket | null = null;
  let liveStatus: "idle" | "connecting" | "connected" | "subscribed" | "live" | "suspended" | "unavailable" | "error" = "idle";
  let liveMessage: string | null = null;
  let livePositions: MaritimeAisPosition[] = [];
  let liveVessels: MaritimeVesselStatic[] = [];
  let pendingSubscription: { BoundingBoxes: number[][][]; FilterMessageTypes: string[]; type: string } | null = null;
  let lastSubscriptionKey = "";

  $: displayPositions = mapZoom >= AIS_ZOOM_THRESHOLD ? (livePositions.length ? livePositions : positions) : [];
  $: displayVessels = mergeVessels(vessels, liveVessels);
  $: vesselIndex = Object.fromEntries(displayVessels.map((v) => [v.vessel_id, v]));

  function vesselFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: displayPositions
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
            heading: p.heading_degrees ?? p.course_degrees ?? 0,
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
      (map as Record<string, unknown> & { setProjection?: (p: unknown) => void }).setProjection?.(
        is3D ? { type: "globe" } : { type: "mercator" }
      );
    } catch {
      /* older version — ignore */
    }
    if (is3D) {
      map.dragRotate.enable();
      map.touchZoomRotate.enableRotation();
    } else {
      map.dragRotate.disable();
      map.touchZoomRotate.disableRotation();
      map.setPitch(0);
      map.setBearing(0);
    }
  }

  function recolorBaseMap() {
    if (!map) return;
    for (const layer of map.getStyle()?.layers ?? []) {
      const id = layer.id;
      if (id === "background") {
        // background = land base — everything that isn't explicitly filled by another layer
        setPaint(id, "background-color", "#0d2540");
      } else if (id === "water") {
        // water fills ocean, seas, lakes, rivers on top of the land background
        setPaint(id, "fill-color", "#01040c");
        setPaint(id, "fill-opacity", 1);
      } else if (id === "boundary_country_outline" || id === "boundary_country_inner") {
        setPaint(id, "line-color", "#4f9deb");
        setPaint(id, "line-opacity", 0.82);
        setPaint(id, "line-width", ["interpolate", ["linear"], ["zoom"], 2, 0.85, 5, 1.15, 8, 1.55]);
      } else if (id === "boundary_state" || id === "boundary_county") {
        setPaint(id, "line-color", "#3d86d6");
        setPaint(id, "line-opacity", 0.42);
        setPaint(id, "line-width", ["interpolate", ["linear"], ["zoom"], 2, 0.35, 6, 0.7]);
      } else {
        // Hide everything else: landcover, landuse, parks, waterway, roads, buildings, etc.
        // This lets the flat navy background show cleanly for all land areas.
        setLayout(id, "visibility", "none");
      }
    }
  }

  function setLayout(layerId: string, property: string, value: unknown) {
    if (!map || !map.getLayer(layerId)) return;
    try {
      map.setLayoutProperty(layerId, property, value as never);
    } catch {
      // ignore
    }
  }

  function setPaint(layerId: string, property: string, value: unknown) {
    if (!map || !map.getLayer(layerId)) return;
    try {
      map.setPaintProperty(layerId, property, value as never);
    } catch {
      // Some properties only apply to specific layer types.
    }
  }

  function scheduleViewportSubscription() {
    if (!map) return;
    mapZoom = map.getZoom();
    if (mapZoom < AIS_ZOOM_THRESHOLD) {
      closeLiveSocket("zoom below live AIS threshold", "suspended", true);
      return;
    }
    if (viewportDebounce) clearTimeout(viewportDebounce);
    viewportDebounce = setTimeout(() => {
      sendViewportSubscription();
    }, VIEWPORT_DEBOUNCE_MS);
  }

  function sendViewportSubscription() {
    if (!map || map.getZoom() < AIS_ZOOM_THRESHOLD) {
      closeLiveSocket("zoom below live AIS threshold", "suspended", true);
      return;
    }
    const bounds = map.getBounds();
    const west = clamp(bounds.getWest(), -180, 180);
    const east = clamp(bounds.getEast(), -180, 180);
    const south = clamp(bounds.getSouth(), -90, 90);
    const north = clamp(bounds.getNorth(), -90, 90);
    const boundingBox = [
      [Math.min(south, north), Math.min(west, east)],
      [Math.max(south, north), Math.max(west, east)]
    ];
    pendingSubscription = {
      type: "subscribe",
      BoundingBoxes: [boundingBox],
      FilterMessageTypes: ["PositionReport"]
    };
    ensureLiveSocket();
    flushSubscription();
  }

  function ensureLiveSocket() {
    if (liveSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(liveSocket.readyState)) {
      return;
    }
    liveStatus = "connecting";
    liveMessage = null;
    const socket = new WebSocket(`${WS_BASE}/maritime/live/ws`);
    liveSocket = socket;
    socket.onopen = () => {
      liveStatus = "connected";
      flushSubscription();
    };
    socket.onmessage = handleLiveMessage;
    socket.onerror = () => {
      liveStatus = "error";
      liveMessage = "Live AISstream proxy error.";
    };
    socket.onclose = () => {
      if (liveSocket === socket) {
        liveSocket = null;
      }
      if (liveStatus !== "unavailable" && liveStatus !== "error" && mapZoom >= AIS_ZOOM_THRESHOLD) {
        liveStatus = "suspended";
      }
    };
  }

  function flushSubscription() {
    if (!liveSocket || liveSocket.readyState !== WebSocket.OPEN || !pendingSubscription) return;
    const key = JSON.stringify(pendingSubscription.BoundingBoxes);
    if (key === lastSubscriptionKey) return;
    liveSocket.send(JSON.stringify(pendingSubscription));
    lastSubscriptionKey = key;
    liveStatus = "subscribed";
  }

  function handleLiveMessage(event: MessageEvent<string>) {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(event.data) as Record<string, unknown>;
    } catch {
      return;
    }
    if (message.type === "status") {
      const status = String(message.status ?? "");
      if (status === "unavailable") {
        liveStatus = "unavailable";
      } else if (status === "error") {
        liveStatus = "error";
      } else if (status === "subscribed") {
        liveStatus = "subscribed";
      } else if (status === "connected") {
        liveStatus = "connected";
      }
      liveMessage = typeof message.message === "string" ? message.message : null;
      return;
    }
    if (message.type !== "position" || !message.position) {
      return;
    }
    liveStatus = "live";
    upsertPosition(message.position as MaritimeAisPosition);
    if (message.vessel) {
      upsertVessel(message.vessel as MaritimeVesselStatic);
    }
  }

  function upsertPosition(position: MaritimeAisPosition) {
    livePositions = [
      position,
      ...livePositions.filter((item) => item.vessel_id !== position.vessel_id)
    ]
      .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
      .slice(0, MAX_LIVE_POSITIONS);
  }

  function upsertVessel(vessel: MaritimeVesselStatic) {
    liveVessels = [vessel, ...liveVessels.filter((item) => item.vessel_id !== vessel.vessel_id)];
  }

  function closeLiveSocket(reason: string, status: typeof liveStatus = "suspended", clearLiveData = false) {
    if (viewportDebounce) {
      clearTimeout(viewportDebounce);
      viewportDebounce = null;
    }
    pendingSubscription = null;
    lastSubscriptionKey = "";
    if (clearLiveData) {
      livePositions = [];
      liveVessels = [];
    }
    if (liveSocket) {
      const socket = liveSocket;
      liveSocket = null;
      if ([WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) {
        socket.close(1000, reason);
      }
    }
    liveStatus = status;
  }

  function clamp(value: number, low: number, high: number) {
    return Math.max(low, Math.min(high, value));
  }

  function mergeVessels(base: MaritimeVesselStatic[], live: MaritimeVesselStatic[]) {
    const rows = new Map<string, MaritimeVesselStatic>();
    for (const vessel of base) rows.set(vessel.vessel_id, vessel);
    for (const vessel of live) rows.set(vessel.vessel_id, vessel);
    return [...rows.values()];
  }

  onMount(() => {
    map = new maplibregl.Map({
      container,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
      center: [-20, 10],
      zoom: 3,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();

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

    map.on("move", scheduleViewportSubscription);
    map.on("zoom", scheduleViewportSubscription);

    map.on("load", () => {
      if (!map) return;
      recolorBaseMap();

      // ── Shipping lanes (static, no interaction) ───────────────
      map.addSource("shipping-lanes", {
        type: "geojson",
        data: "/shipping-lanes.geojson",
        attribution: "Shipping lanes: P. Benden / CIA, CC BY-SA 4.0",
      });
      // Width scaled by lane importance: Major > Middle > Minor
      const laneWidth = (major: number, middle: number, minor: number) => [
        "match", ["get", "Type"],
        "Major", major, "Middle", middle, minor
      ];

      map.addLayer({
        id: "shipping-lanes-aura",
        type: "line",
        source: "shipping-lanes",
        paint: {
          "line-color": "#76b9ff",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, ["match", ["get", "Type"], "Major", 0.13, "Middle", 0.09, 0.06],
            5, ["match", ["get", "Type"], "Major", 0.20, "Middle", 0.14, 0.09],
            8, ["match", ["get", "Type"], "Major", 0.26, "Middle", 0.18, 0.11]],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(16, 11, 7),
            5, laneWidth(22, 15, 10),
            8, laneWidth(30, 20, 13)],
          "line-blur": 14,
        },
      });
      map.addLayer({
        id: "shipping-lanes-glow",
        type: "line",
        source: "shipping-lanes",
        paint: {
          "line-color": "#2f89d9",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, ["match", ["get", "Type"], "Major", 0.36, "Middle", 0.25, 0.16],
            5, ["match", ["get", "Type"], "Major", 0.45, "Middle", 0.31, 0.20],
            8, ["match", ["get", "Type"], "Major", 0.52, "Middle", 0.36, 0.23]],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(8, 5.5, 3.5),
            5, laneWidth(12, 8, 5),
            8, laneWidth(17, 11, 7)],
          "line-blur": 8,
        },
      });
      map.addLayer({
        id: "shipping-lanes-body",
        type: "line",
        source: "shipping-lanes",
        paint: {
          "line-color": "#1a3a5c",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, ["match", ["get", "Type"], "Major", 0.62, "Middle", 0.44, 0.28],
            5, ["match", ["get", "Type"], "Major", 0.72, "Middle", 0.50, 0.32],
            8, ["match", ["get", "Type"], "Major", 0.82, "Middle", 0.57, 0.37]],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(4.5, 3, 2),
            5, laneWidth(6.5, 4.5, 3),
            8, laneWidth(9, 6, 4)],
          "line-blur": 4.5,
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
      mapZoom = map.getZoom();
      pushSources();
      scheduleViewportSubscription();
    });
  });

  onDestroy(() => {
    closeLiveSocket("component destroyed", "idle", true);
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
  $: if (mapReady) void (displayPositions, displayVessels, ports, chokepoints, pushSources());
  $: if (mapReady) applyProjection();
  $: connDotActive = mapZoom >= AIS_ZOOM_THRESHOLD && ["subscribed", "live"].includes(liveStatus);
  $: liveStatusLabel =
    mapZoom < AIS_ZOOM_THRESHOLD
      ? "Zoom <4"
      : liveStatus === "live"
        ? "Live"
        : liveStatus === "subscribed"
          ? "Subscribed"
          : liveStatus === "connecting" || liveStatus === "connected"
            ? "Connecting"
            : liveStatus === "unavailable"
              ? "Unavailable"
              : liveStatus === "error"
                ? "Error"
                : connected
                  ? "API"
                  : "Idle";
</script>

<div class="map-wrap">
  <div bind:this={container} class="map-container"></div>

  <!-- HUD: vessel count + connection status -->
  <div class="map-hud">
    <div class="hud-row">
      <span class="hud-label">Vessels</span>
      <span class="hud-value">{displayPositions.length}</span>
    </div>
    <div class="hud-row">
      <span class="conn-dot" class:active={connDotActive}></span>
      <span class="hud-label">{liveStatusLabel}</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Zoom</span>
      <span class="hud-value">{mapZoom.toFixed(1)}</span>
    </div>
    {#if liveMessage}<div class="hud-note">{liveMessage}</div>{/if}
  </div>

  <!-- Bottom-left: legend + 3D toggle -->
  <div class="map-bottom">
    <div class="map-legend">
      <span class="legend-item vessel">Vessel</span>
      <span class="legend-item lane">Sealanes</span>
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
    background: var(--positive, #4bb474);
  }

  .hud-note {
    max-width: 14rem;
    color: var(--warning, #c49a5a);
    font-size: 0.66rem;
    line-height: 1.35;
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
  .legend-item.lane::before {
    width: 18px;
    height: 5px;
    border-radius: 999px;
    background: color-mix(in srgb, #1a3a5c 72%, transparent);
    box-shadow:
      0 0 4px color-mix(in srgb, #2f89d9 72%, transparent),
      0 0 10px color-mix(in srgb, #76b9ff 42%, transparent);
  }
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
