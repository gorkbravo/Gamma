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
  const TEXT2 = "#8a919a";
  const AIS_ZOOM_THRESHOLD = 4;
  const VIEWPORT_DEBOUNCE_MS = 1500;
  const MAX_LIVE_POSITIONS = 600;
  const VESSEL_GROUPS = ["tanker", "lng_carrier", "cargo", "container", "dry_bulk", "passenger", "fishing", "special", "unknown"];
  const VESSEL_COLORS: Record<string, string> = {
    tanker: "#e36f5a",
    lng_carrier: "#7aa6c8",
    cargo: "#4bb474",
    container: "#4bb474",
    dry_bulk: "#c49a5a",
    passenger: "#a4b0bc",
    fishing: "#63b3a6",
    special: "#b58bd8",
    unknown: "#8a919a",
  };

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
            vessel_group: vesselGroup(vesselIndex[p.vessel_id]?.vessel_type),
            speed_knots: p.speed_knots ?? null,
            navigation_status: p.navigation_status ?? null,
            mmsi: p.mmsi,
            heading: p.heading_degrees ?? p.course_degrees ?? 0,
            moving: (p.speed_knots ?? 0) >= 0.5,
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
        properties: {
          name: p.name,
          country: p.country,
          terminal_type: p.terminal_type ?? "Port",
          port_group: portGroup(p.terminal_type, p.commodity_links),
        },
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
      FilterMessageTypes: [
        "PositionReport",
        "ExtendedClassBPositionReport",
        "StandardClassBPositionReport",
        "ShipStaticData",
        "StaticDataReport",
      ],
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
    if (message.type === "vessel" && message.vessel) {
      upsertVessel(message.vessel as MaritimeVesselStatic);
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
    const previous = liveVessels.find((item) => item.vessel_id === vessel.vessel_id);
    const merged = mergeVesselStatic(previous, vessel);
    liveVessels = [merged, ...liveVessels.filter((item) => item.vessel_id !== vessel.vessel_id)];
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
    for (const vessel of live) rows.set(vessel.vessel_id, mergeVesselStatic(rows.get(vessel.vessel_id), vessel));
    return [...rows.values()];
  }

  function mergeVesselStatic(previous: MaritimeVesselStatic | undefined, incoming: MaritimeVesselStatic) {
    if (!previous) return incoming;
    const incomingIsMinimal = incoming.vessel_type === "unknown";
    return {
      ...incoming,
      name: incoming.name.startsWith("MMSI ") && !previous.name.startsWith("MMSI ") ? previous.name : incoming.name,
      vessel_type: incomingIsMinimal && previous.vessel_type !== "unknown" ? previous.vessel_type : incoming.vessel_type,
      vessel_class:
        incoming.vessel_class === "AISstream live vessel" && previous.vessel_class !== "AISstream live vessel"
          ? previous.vessel_class
          : incoming.vessel_class,
      flag: incoming.flag ?? previous.flag,
      owner_operator: incoming.owner_operator ?? previous.owner_operator,
      length_m: incoming.length_m ?? previous.length_m,
      beam_m: incoming.beam_m ?? previous.beam_m,
      deadweight_tons: incoming.deadweight_tons ?? previous.deadweight_tons,
      cargo_inference: incoming.cargo_inference ?? previous.cargo_inference,
      cargo_inference_confidence: incoming.cargo_inference_confidence ?? previous.cargo_inference_confidence,
      cargo_inference_caveat: incoming.cargo_inference_caveat ?? previous.cargo_inference_caveat,
      transformation_note: incomingIsMinimal ? previous.transformation_note ?? incoming.transformation_note : incoming.transformation_note,
    };
  }

  function vesselGroup(value: string | null | undefined) {
    const normalized = String(value ?? "unknown").toLowerCase().replace(/[\s-]+/g, "_");
    if (normalized.includes("tanker") || normalized.includes("oil")) return "tanker";
    if (normalized.includes("lng") || normalized.includes("gas")) return "lng_carrier";
    if (normalized.includes("container")) return "container";
    if (normalized.includes("bulk")) return "dry_bulk";
    if (normalized.includes("cargo")) return "cargo";
    if (normalized.includes("passenger")) return "passenger";
    if (normalized.includes("fishing")) return "fishing";
    if (normalized.includes("tug") || normalized.includes("special")) return "special";
    return "unknown";
  }

  function portGroup(terminalType: string | null | undefined, commodityLinks: string[] = []) {
    const haystack = `${terminalType ?? ""} ${commodityLinks.join(" ")}`.toLowerCase();
    if (haystack.includes("oil") || haystack.includes("crude") || haystack.includes("product")) return "tanker";
    if (haystack.includes("lng") || haystack.includes("gas")) return "lng_carrier";
    if (haystack.includes("container")) return "container";
    if (haystack.includes("bulk") || haystack.includes("coal") || haystack.includes("iron ore")) return "dry_bulk";
    return "cargo";
  }

  function groupColorExpression(propertyName: string) {
    return [
      "match", ["get", propertyName],
      "tanker", VESSEL_COLORS.tanker,
      "lng_carrier", VESSEL_COLORS.lng_carrier,
      "cargo", VESSEL_COLORS.cargo,
      "container", VESSEL_COLORS.container,
      "dry_bulk", VESSEL_COLORS.dry_bulk,
      "passenger", VESSEL_COLORS.passenger,
      "fishing", VESSEL_COLORS.fishing,
      "special", VESSEL_COLORS.special,
      VESSEL_COLORS.unknown,
    ];
  }

  function chevronImage(color: string) {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.clearRect(0, 0, 64, 64);
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.strokeStyle = color;
    ctx.lineWidth = 9;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(17, 46);
    ctx.lineTo(32, 15);
    ctx.lineTo(47, 46);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "rgba(2, 6, 12, 0.7)";
    ctx.lineWidth = 2;
    ctx.stroke();
    return ctx.getImageData(0, 0, 64, 64);
  }

  function addChevronImages() {
    if (!map) return;
    for (const group of VESSEL_GROUPS) {
      const id = `vessel-chevron-${group}`;
      if (map.hasImage(id)) continue;
      const image = chevronImage(VESSEL_COLORS[group] ?? VESSEL_COLORS.unknown);
      if (image) map.addImage(id, image);
    }
  }

  function vesselIconExpression() {
    return [
      "match", ["get", "vessel_group"],
      "tanker", "vessel-chevron-tanker",
      "lng_carrier", "vessel-chevron-lng_carrier",
      "cargo", "vessel-chevron-cargo",
      "container", "vessel-chevron-container",
      "dry_bulk", "vessel-chevron-dry_bulk",
      "passenger", "vessel-chevron-passenger",
      "fishing", "vessel-chevron-fishing",
      "special", "vessel-chevron-special",
      "vessel-chevron-unknown",
    ];
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
        filter: ["==", ["get", "Type"], "Major"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#76b9ff",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, 0.16,
            5, 0.25,
            8, 0.31],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(18, 11, 7),
            5, laneWidth(26, 15, 10),
            8, laneWidth(34, 20, 13)],
          "line-blur": 18,
        },
      });
      map.addLayer({
        id: "shipping-lanes-glow",
        type: "line",
        source: "shipping-lanes",
        filter: ["==", ["get", "Type"], "Major"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#2f89d9",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, 0.30,
            5, 0.42,
            8, 0.50],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(9, 5.5, 3.5),
            5, laneWidth(14, 8, 5),
            8, laneWidth(19, 11, 7)],
          "line-blur": 10,
        },
      });
      map.addLayer({
        id: "shipping-lanes-body",
        type: "line",
        source: "shipping-lanes",
        filter: ["==", ["get", "Type"], "Major"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#2b79bf",
          "line-opacity": ["interpolate", ["linear"], ["zoom"],
            2, 0.36,
            5, 0.50,
            8, 0.62],
          "line-width": ["interpolate", ["linear"], ["zoom"],
            2, laneWidth(4.5, 3, 2),
            5, laneWidth(6.5, 4.5, 3),
            8, laneWidth(8.5, 6, 4)],
          "line-blur": 5,
        },
      });

      // ── Vessels ──────────────────────────────────────────────
      addChevronImages();
      map.addSource("vessels", { type: "geojson", data: vesselFeatureCollection() as never });

      // Outer halo for visibility on any background
      map.addLayer({
        id: "vessels-halo",
        type: "circle",
        source: "vessels",
        paint: {
          "circle-color": groupColorExpression("vessel_group"),
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 7, 8, 18],
          "circle-opacity": 0.08,
          "circle-stroke-width": 0,
        },
      });

      map.addLayer({
        id: "vessels-chevron",
        type: "symbol",
        source: "vessels",
        layout: {
          "icon-image": vesselIconExpression(),
          "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.22, 8, 0.34, 11, 0.46],
          "icon-rotate": ["coalesce", ["get", "heading"], 0],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": ["case", ["get", "moving"], 0.96, 0.72],
        },
      });

      // ── Ports ─────────────────────────────────────────────────
      map.addSource("major-ports", {
        type: "geojson",
        data: "/major-ports.geojson",
        attribution: "Major ports: Gamma static public-reference layer",
      });
      map.addLayer({
        id: "major-ports-halo",
        type: "circle",
        source: "major-ports",
        paint: {
          "circle-color": groupColorExpression("port_group"),
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 7, 6, 12],
          "circle-blur": 1.15,
          "circle-opacity": 0.2,
        },
      });
      map.addLayer({
        id: "major-ports-dot",
        type: "circle",
        source: "major-ports",
        paint: {
          "circle-color": groupColorExpression("port_group"),
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 2.3, 6, 4.2],
          "circle-stroke-color": BG0,
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "major-ports-labels",
        type: "symbol",
        source: "major-ports",
        minzoom: 3.2,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 9,
          "text-anchor": "left",
          "text-offset": [0.75, 0],
          "text-allow-overlap": false,
          "text-optional": true,
        },
        paint: {
          "text-color": "#c2c8d0",
          "text-halo-color": BG0,
          "text-halo-width": 1.4,
        },
      });

      map.addSource("ports", { type: "geojson", data: portFeatureCollection() as never });
      map.addLayer({
        id: "ports-dot",
        type: "circle",
        source: "ports",
        paint: {
          "circle-color": groupColorExpression("port_group"),
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
      map.on("mouseenter", "vessels-chevron", (e) => {
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

      map.on("mouseleave", "vessels-chevron", () => {
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
      <span class="legend-item tanker">Tanker</span>
      <span class="legend-item lng">LNG</span>
      <span class="legend-item cargo">Cargo</span>
      <span class="legend-item bulk">Bulk</span>
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

  .legend-item.tanker::before { background: #e36f5a; }
  .legend-item.lng::before    { background: #7aa6c8; }
  .legend-item.cargo::before  { background: #4bb474; }
  .legend-item.bulk::before   { background: #c49a5a; }
  .legend-item.lane::before {
    width: 18px;
    height: 5px;
    border-radius: 999px;
    background: color-mix(in srgb, #2b79bf 72%, transparent);
    box-shadow:
      0 0 4px color-mix(in srgb, #2f89d9 72%, transparent),
      0 0 10px color-mix(in srgb, #76b9ff 42%, transparent);
  }
  .legend-item.port::before   { background: var(--text-2, #8a919a); }
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
