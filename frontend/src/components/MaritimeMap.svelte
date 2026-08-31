<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import maplibregl from "maplibre-gl";
  import "maplibre-gl/dist/maplibre-gl.css";
  import { WS_BASE } from "../lib/api/client";
  import type {
    MaritimeAisPosition,
    MaritimeChokepointDefinition,
    MaritimeChokepointSummary,
    MaritimeCoverageMetadata,
    MaritimeEventWindow,
    MaritimeFleetWatchlist,
    MaritimeFlowSummary,
    MaritimePort,
    MaritimeTrackSnippet,
    MaritimeVesselStatic,
  } from "../lib/api/types";

  export let positions: MaritimeAisPosition[] = [];
  export let vessels: MaritimeVesselStatic[] = [];
  export let ports: MaritimePort[] = [];
  export let chokepoints: MaritimeChokepointDefinition[] = [];
  export let chokepointSummaries: MaritimeChokepointSummary[] = [];
  export let flowSummaries: MaritimeFlowSummary[] = [];
  export let tracks: MaritimeTrackSnippet[] = [];
  export let watchlists: MaritimeFleetWatchlist[] = [];
  export let eventWindows: MaritimeEventWindow[] = [];
  export let coverage: MaritimeCoverageMetadata | null = null;
  export let warnings: string[] = [];
  export let loading = false;
  export let onRefresh: ((forceRefresh?: boolean) => Promise<unknown> | void) | null = null;
  export let is3D = false;
  export let connected = false;
  /** Chokepoint an inbound cross-tab handoff asked the map to open. */
  export let focusChokepointId: string | null = null;

  type OverlayKey = "chokepoints" | "tradeFlows" | "fleet" | "eventReplay";
  type DetailSelection =
    | { kind: "chokepoint"; id: string }
    | { kind: "flow"; id: string }
    | { kind: "vessel"; id: string }
    | { kind: "event"; id: string }
    | null;

  // Design token values used for map layer styling
  const BG0 = "#02060c";
  const TEXT2 = "#8a919a";
  const AIS_ZOOM_THRESHOLD = 4;
  const VIEWPORT_DEBOUNCE_MS = 1500;
  const MAX_LIVE_POSITIONS = 600;
  const AISSTREAM_COVERAGE_URL = "https://aisstream.io/coverage";
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
  let settingsOpen = false;
  let displaySettingsOpen = false;
  let selectedDetail: DetailSelection = null;
  let appliedFocusChokepointId: string | null = null;
  let activeOverlays: Record<OverlayKey, boolean> = {
    chokepoints: true,
    tradeFlows: false,
    fleet: false,
    eventReplay: false,
  };
  let displaySettings = {
    ports: true,
  };
  let vesselGroupFilters: Record<string, boolean> = Object.fromEntries(VESSEL_GROUPS.map((group) => [group, true]));
  let replayTrackId = "";
  let replayIndex = 0;

  $: displayPositions = mapZoom >= AIS_ZOOM_THRESHOLD ? (livePositions.length ? livePositions : positions) : [];
  $: displayVessels = mergeVessels(vessels, liveVessels);
  $: vesselIndex = Object.fromEntries(displayVessels.map((v) => [v.vessel_id, v]));
  $: summaryIndex = Object.fromEntries(chokepointSummaries.map((s) => [s.chokepoint_id, s]));
  $: watchlistVesselIds = new Set(watchlists.flatMap((w) => w.vessel_ids));
  $: selectedReplayTrack =
    tracks.find((track) => track.track_id === replayTrackId) ??
    tracks[0] ??
    null;
  $: replayMax = selectedReplayTrack ? Math.max(selectedReplayTrack.points.length - 1, 0) : 0;
  $: if (replayIndex > replayMax) replayIndex = replayMax;
  // An inbound handoff names a chokepoint; open its detail shelf so the entity
  // the sending tab selected is not lost on arrival.
  $: if (focusChokepointId && focusChokepointId !== appliedFocusChokepointId && summaryIndex[focusChokepointId]) {
    appliedFocusChokepointId = focusChokepointId;
    activeOverlays = { ...activeOverlays, chokepoints: true };
    selectedDetail = { kind: "chokepoint", id: focusChokepointId };
  }
  $: selectedChokepoint = selectedDetail?.kind === "chokepoint" ? summaryIndex[selectedDetail.id] : null;
  $: selectedFlow = selectedDetail?.kind === "flow" ? flowSummaries.find((f) => f.flow_id === selectedDetail?.id) ?? null : null;
  $: selectedVessel = selectedDetail?.kind === "vessel" ? displayVessels.find((v) => v.vessel_id === selectedDetail?.id) ?? null : null;
  $: selectedEvent = selectedDetail?.kind === "event" ? eventWindows.find((e) => e.event_id === selectedDetail?.id) ?? null : null;

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
            watchlisted: watchlistVesselIds.has(p.vessel_id),
            speed_knots: p.speed_knots ?? null,
            navigation_status: p.navigation_status ?? null,
            mmsi: p.mmsi,
            heading: p.heading_degrees ?? p.course_degrees ?? 0,
            moving: (p.speed_knots ?? 0) >= 0.5,
          },
        }))
        .filter((feature) => vesselGroupFilters[String(feature.properties.vessel_group)] !== false),
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

  function chokepointAreaFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: chokepoints.map((c) => {
        const s = summaryIndex[c.chokepoint_id];
        const bbox = c.bounding_box;
        const score = s?.congestion_score ?? 0;
        const tone = score >= 1.35 ? "high" : s && s.total_vessel_count > 0 ? "active" : "quiet";
        return {
          type: "Feature" as const,
          geometry: {
            type: "Polygon" as const,
            coordinates: [[
              [bbox.min_longitude, bbox.min_latitude],
              [bbox.max_longitude, bbox.min_latitude],
              [bbox.max_longitude, bbox.max_latitude],
              [bbox.min_longitude, bbox.max_latitude],
              [bbox.min_longitude, bbox.min_latitude],
            ]],
          },
          properties: {
            chokepoint_id: c.chokepoint_id,
            name: c.name,
            region: c.region,
            total_vessel_count: s?.total_vessel_count ?? 0,
            congestion_score: score,
            congestion_label: s?.congestion_label ?? "sample unavailable",
            commodities: (s?.commodity_links ?? c.strategic_commodities).join(", "),
            methodology: s?.methodology ?? "Coverage is defined by a static chokepoint bounding box.",
            caveat: s?.caveats?.[0] ?? c.description ?? "Sample or partial AIS coverage only.",
            tone,
          },
        };
      }),
    };
  }

  function flowTrackFeatureCollection() {
    return {
      type: "FeatureCollection" as const,
      features: tracks
        .filter((track) => track.points.length >= 2)
        .map((track) => {
          const vessel = vesselIndex[track.vessel_id];
          const flow = flowSummaries.find((item) => item.vessel_type === vessel?.vessel_type);
          return {
            type: "Feature" as const,
            geometry: {
              type: "LineString" as const,
              coordinates: track.points.map((p) => [p.longitude, p.latitude]),
            },
            properties: {
              track_id: track.track_id,
              vessel_id: track.vessel_id,
              label: track.label,
              vessel_group: vesselGroup(vessel?.vessel_type),
              vessel_type: vesselTypeLabel(vessel?.vessel_type),
              flow_id: flow?.flow_id ?? "",
              inferred_commodity: flow?.inferred_commodity ?? "Unknown",
              inference_caveat: flow?.inference_caveat ?? "Route is a sample track snippet, not confirmed cargo.",
            },
          };
        }),
    };
  }

  function replayLineFeatureCollection() {
    if (!selectedReplayTrack) return { type: "FeatureCollection" as const, features: [] };
    const points = selectedReplayTrack.points.slice(0, replayIndex + 1);
    if (points.length < 2) return { type: "FeatureCollection" as const, features: [] };
    return {
      type: "FeatureCollection" as const,
      features: [{
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: points.map((p) => [p.longitude, p.latitude]),
        },
        properties: {
          track_id: selectedReplayTrack.track_id,
          label: selectedReplayTrack.label,
        },
      }],
    };
  }

  function replayPointFeatureCollection() {
    if (!selectedReplayTrack || !selectedReplayTrack.points.length) return { type: "FeatureCollection" as const, features: [] };
    const point = selectedReplayTrack.points[Math.min(replayIndex, selectedReplayTrack.points.length - 1)];
    return {
      type: "FeatureCollection" as const,
      features: [{
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [point.longitude, point.latitude] },
        properties: {
          track_id: selectedReplayTrack.track_id,
          label: selectedReplayTrack.label,
          timestamp: point.timestamp,
        },
      }],
    };
  }

  function pushSources() {
    if (!map || !mapReady) return;
    (map.getSource("vessels") as maplibregl.GeoJSONSource | undefined)?.setData(vesselFeatureCollection() as never);
    (map.getSource("ports") as maplibregl.GeoJSONSource | undefined)?.setData(portFeatureCollection() as never);
    (map.getSource("chokepoints") as maplibregl.GeoJSONSource | undefined)?.setData(chokepointFeatureCollection() as never);
    (map.getSource("chokepoint-areas") as maplibregl.GeoJSONSource | undefined)?.setData(chokepointAreaFeatureCollection() as never);
    (map.getSource("flow-tracks") as maplibregl.GeoJSONSource | undefined)?.setData(flowTrackFeatureCollection() as never);
    (map.getSource("replay-line") as maplibregl.GeoJSONSource | undefined)?.setData(replayLineFeatureCollection() as never);
    (map.getSource("replay-point") as maplibregl.GeoJSONSource | undefined)?.setData(replayPointFeatureCollection() as never);
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

  function vesselTypeLabel(value: string | null | undefined) {
    const labels: Record<string, string> = {
      dry_bulk: "Dry Bulk",
      lng_carrier: "LNG",
      product_tanker: "Products",
      tanker: "Tanker",
      container: "Container",
      cargo: "Cargo",
      fishing: "Fishing",
      passenger: "Passenger",
      special: "Special",
      unknown: "Unknown",
    };
    const key = String(value ?? "unknown").toLowerCase();
    return labels[key] ?? key.replace(/_/g, " ");
  }

  function coverageLabel(value: string | null | undefined) {
    return String(value ?? "unknown").replace(/_/g, " ").toUpperCase();
  }

  function isAisstreamProvider(meta: MaritimeCoverageMetadata | null) {
    if (!meta) return false;
    const haystack = `${meta.provider_id ?? ""} ${meta.provider_label ?? ""}`.toLowerCase();
    return haystack.includes("aisstream");
  }

  $: coverageStatus = coverage?.coverage_status ?? null;

  let showCoverageChip = false;
  let coverageChipTimer: ReturnType<typeof setTimeout> | null = null;

  $: {
    const subscribed = liveStatus === "subscribed" || liveStatus === "live";
    const noVessels = displayPositions.length === 0;
    const shouldShow = isAisstreamProvider(coverage) && mapZoom >= AIS_ZOOM_THRESHOLD && subscribed && noVessels;
    if (shouldShow) {
      if (!coverageChipTimer && !showCoverageChip) {
        coverageChipTimer = setTimeout(() => {
          showCoverageChip = true;
          coverageChipTimer = null;
        }, 3000);
      }
    } else {
      if (coverageChipTimer) {
        clearTimeout(coverageChipTimer);
        coverageChipTimer = null;
      }
      showCoverageChip = false;
    }
  }

  $: coverageChipTooltip = `Subscribed but no vessels detected — ${coverage?.provider_label ?? "AISstream"} may have limited coverage here — open coverage map`;

  function shortDate(value: string | null | undefined) {
    return value
      ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
      : "N/A";
  }

  function number(value: number | null | undefined, digits = 1) {
    return value == null ? "N/A" : value.toFixed(digits);
  }

  function pct(value: number | null | undefined, digits = 0) {
    return value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  }

  function vesselMix(summary: MaritimeChokepointSummary | null) {
    if (!summary) return "No sample vessels";
    const entries = Object.entries(summary.vessel_count_by_type).filter(([, count]) => count > 0);
    return entries.length
      ? entries.map(([type, count]) => `${vesselTypeLabel(type)} ${count}`).join(" | ")
      : "No sample vessels";
  }

  function firstWarning() {
    return warnings[0] ?? coverage?.caveats?.[0] ?? "AIS coverage is partial or sample unless explicitly marked live.";
  }

  function toggleOverlay(key: OverlayKey) {
    activeOverlays = { ...activeOverlays, [key]: !activeOverlays[key] };
    if (key === "eventReplay" && !activeOverlays.eventReplay && selectedDetail?.kind === "event") {
      selectedDetail = null;
    }
  }

  function showOverlay(key: OverlayKey) {
    return activeOverlays[key] ? "visible" : "none";
  }

  function applyOverlayVisibility() {
    if (!map || !mapReady) return;
    const chokepoints = showOverlay("chokepoints");
    const tradeFlows = showOverlay("tradeFlows");
    const fleet = showOverlay("fleet");
    const eventReplay = showOverlay("eventReplay");
    for (const id of ["chokepoints-fill", "chokepoints-outline", "chokepoints-labels"]) {
      setLayout(id, "visibility", chokepoints);
    }
    for (const id of ["flow-tracks-glow", "flow-tracks-line"]) {
      setLayout(id, "visibility", tradeFlows);
    }
    setLayout("watchlist-halo", "visibility", fleet);
    for (const id of ["replay-line-glow", "replay-line-body", "replay-point"]) {
      setLayout(id, "visibility", eventReplay);
    }
  }

  function applyDisplaySettings() {
    if (!map || !mapReady) return;
    const portVisibility = displaySettings.ports ? "visible" : "none";
    for (const id of ["major-ports-halo", "major-ports-dot", "major-ports-labels", "ports-dot"]) {
      setLayout(id, "visibility", portVisibility);
    }
  }

  function togglePorts() {
    displaySettings = { ...displaySettings, ports: !displaySettings.ports };
  }

  function toggleVesselGroup(group: string) {
    vesselGroupFilters = { ...vesselGroupFilters, [group]: vesselGroupFilters[group] === false };
  }

  function setAllVesselGroups(value: boolean) {
    vesselGroupFilters = Object.fromEntries(VESSEL_GROUPS.map((group) => [group, value]));
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

  function stressColorExpression() {
    return [
      "match", ["get", "tone"],
      "high", "#c66b61",
      "active", "#c49a5a",
      "#7aa6c8",
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
      map.addSource("chokepoint-areas", { type: "geojson", data: chokepointAreaFeatureCollection() as never });
      map.addLayer({
        id: "chokepoints-fill",
        type: "fill",
        source: "chokepoint-areas",
        paint: {
          "fill-color": stressColorExpression(),
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.10, 5, 0.16, 8, 0.22],
        },
      });
      map.addLayer({
        id: "chokepoints-outline",
        type: "line",
        source: "chokepoint-areas",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": stressColorExpression(),
          "line-opacity": 0.84,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.1, 6, 1.8],
          "line-blur": 0.8,
        },
      });
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

      // ── Trade-flow and replay overlays ────────────────────────
      map.addSource("flow-tracks", { type: "geojson", data: flowTrackFeatureCollection() as never });
      map.addLayer({
        id: "flow-tracks-glow",
        type: "line",
        source: "flow-tracks",
        layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: {
          "line-color": groupColorExpression("vessel_group"),
          "line-opacity": 0.24,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 8, 7, 15],
          "line-blur": 10,
        },
      });
      map.addLayer({
        id: "flow-tracks-line",
        type: "line",
        source: "flow-tracks",
        layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: {
          "line-color": groupColorExpression("vessel_group"),
          "line-opacity": 0.78,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.5, 7, 3],
          "line-blur": 1.6,
        },
      });

      map.addSource("replay-line", { type: "geojson", data: replayLineFeatureCollection() as never });
      map.addLayer({
        id: "replay-line-glow",
        type: "line",
        source: "replay-line",
        layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: {
          "line-color": "#7aa6c8",
          "line-opacity": 0.26,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 12, 7, 20],
          "line-blur": 14,
        },
      });
      map.addLayer({
        id: "replay-line-body",
        type: "line",
        source: "replay-line",
        layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: {
          "line-color": "#7aa6c8",
          "line-opacity": 0.86,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 2, 7, 4],
          "line-blur": 1.2,
        },
      });
      map.addSource("replay-point", { type: "geojson", data: replayPointFeatureCollection() as never });
      map.addLayer({
        id: "replay-point",
        type: "circle",
        source: "replay-point",
        layout: { visibility: "none" },
        paint: {
          "circle-color": "#7aa6c8",
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 4, 7, 7],
          "circle-stroke-color": BG0,
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "watchlist-halo",
        type: "circle",
        source: "vessels",
        filter: ["==", ["get", "watchlisted"], true],
        layout: { visibility: "none" },
        paint: {
          "circle-color": "#f0f2f5",
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 10, 8, 22],
          "circle-opacity": 0.08,
          "circle-stroke-color": "#f0f2f5",
          "circle-stroke-opacity": 0.62,
          "circle-stroke-width": 1.3,
        },
      }, "vessels-chevron");

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

      map.on("click", "vessels-chevron", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        selectedDetail = { kind: "vessel", id: String(props.vessel_id ?? "") };
      });

      map.on("mouseenter", "chokepoints-fill", (e) => {
        if (!map || !popup || !e.features?.length) return;
        map.getCanvas().style.cursor = "crosshair";
        const f = e.features[0];
        const props = f.properties as Record<string, unknown>;
        const coordinates = e.lngLat;
        popup
          .setLngLat(coordinates)
          .setHTML(
            `<div class="mp-inner">
              <strong class="mp-name">${escapeHtml(String(props.name ?? ""))}</strong>
              <div class="mp-row"><span>Region</span><span>${escapeHtml(String(props.region ?? ""))}</span></div>
              <div class="mp-row"><span>Vessels</span><span>${escapeHtml(String(props.total_vessel_count ?? 0))}</span></div>
              <div class="mp-row"><span>Score</span><span>${escapeHtml(number(Number(props.congestion_score ?? 0), 2))}</span></div>
              <div class="mp-row"><span>Label</span><span>${escapeHtml(String(props.congestion_label ?? "N/A"))}</span></div>
              <div class="mp-note">${escapeHtml(String(props.caveat ?? ""))}</div>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseleave", "chokepoints-fill", () => {
        if (!map || !popup) return;
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      map.on("click", "chokepoints-fill", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        selectedDetail = { kind: "chokepoint", id: String(props.chokepoint_id ?? "") };
      });

      map.on("mouseenter", "flow-tracks-line", (e) => {
        if (!map || !popup || !e.features?.length) return;
        map.getCanvas().style.cursor = "crosshair";
        const props = e.features[0].properties as Record<string, unknown>;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="mp-inner">
              <strong class="mp-name">${escapeHtml(String(props.label ?? ""))}</strong>
              <div class="mp-row"><span>Vessel</span><span>${escapeHtml(String(props.vessel_type ?? "Unknown"))}</span></div>
              <div class="mp-row"><span>Commodity</span><span>${escapeHtml(String(props.inferred_commodity ?? "Unknown"))}</span></div>
              <div class="mp-note">${escapeHtml(String(props.inference_caveat ?? ""))}</div>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseleave", "flow-tracks-line", () => {
        if (!map || !popup) return;
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      map.on("click", "flow-tracks-line", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        const flowId = String(props.flow_id ?? "");
        if (flowId) selectedDetail = { kind: "flow", id: flowId };
      });

      mapReady = true;
      mapZoom = map.getZoom();
      pushSources();
      applyOverlayVisibility();
      applyDisplaySettings();
      scheduleViewportSubscription();
    });
  });

  onDestroy(() => {
    closeLiveSocket("component destroyed", "idle", true);
    if (coverageChipTimer) clearTimeout(coverageChipTimer);
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
  $: if (mapReady) void (displayPositions, displayVessels, ports, chokepoints, chokepointSummaries, tracks, replayIndex, replayTrackId, vesselGroupFilters, pushSources());
  $: if (mapReady) applyProjection();
  $: if (mapReady) void (activeOverlays, applyOverlayVisibility());
  $: if (mapReady) void (displaySettings, applyDisplaySettings());
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

  <div class="settings-zone">
    <div class="top-control-row">
      <button
        type="button"
        class="settings-button"
        class:active={settingsOpen}
        aria-expanded={settingsOpen}
        on:click={() => { settingsOpen = !settingsOpen; if (settingsOpen) displaySettingsOpen = false; }}
        title="Sealanes overlays"
      >Modes</button>
      <button
        type="button"
        class="settings-icon-button"
        class:active={displaySettingsOpen}
        aria-label="Map display settings"
        aria-expanded={displaySettingsOpen}
        on:click={() => { displaySettingsOpen = !displaySettingsOpen; if (displaySettingsOpen) settingsOpen = false; }}
        title="Map display settings"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8Z" />
          <path d="M19.4 13.2a7.5 7.5 0 0 0 0-2.4l2-1.5-2-3.5-2.4 1a7.7 7.7 0 0 0-2.1-1.2L14.6 3h-5.2l-.3 2.6A7.7 7.7 0 0 0 7 6.8l-2.4-1-2 3.5 2 1.5a7.5 7.5 0 0 0 0 2.4l-2 1.5 2 3.5 2.4-1a7.7 7.7 0 0 0 2.1 1.2l.3 2.6h5.2l.3-2.6a7.7 7.7 0 0 0 2.1-1.2l2.4 1 2-3.5-2-1.5Z" />
        </svg>
      </button>
    </div>

    {#if settingsOpen}
      <section class="settings-shelf" aria-label="Sealanes overlay settings">
        <div class="shelf-header">
          <div>
            <p class="shelf-label">Sealanes</p>
            <strong>Map Overlays</strong>
          </div>
          {#if onRefresh}
            <button type="button" class="shelf-action" on:click={() => onRefresh?.(true)} disabled={loading}>
              {loading ? "Loading" : "Refresh"}
            </button>
          {/if}
        </div>

        <div class="coverage-mini">
          <span>{coverageLabel(coverage?.coverage_status)}</span>
          <span>{coverage?.provider_label ?? "No provider"}</span>
        </div>
        <p class="shelf-note">{firstWarning()}</p>

        <div class="overlay-list">
          <button type="button" class:enabled={activeOverlays.chokepoints} on:click={() => toggleOverlay("chokepoints")}>
            <span>Chokepoints</span>
            <small>{chokepointSummaries.length} boxes, hover/click for stress context</small>
          </button>
          <button type="button" class:enabled={activeOverlays.tradeFlows} on:click={() => toggleOverlay("tradeFlows")}>
            <span>Trade Flows</span>
            <small>{flowSummaries.length} inferred commodity-flow summaries</small>
          </button>
          <button type="button" class:enabled={activeOverlays.fleet} on:click={() => toggleOverlay("fleet")}>
            <span>Fleet / Vessel</span>
            <small>{watchlists.length} watchlists, live chevrons stay read-only</small>
          </button>
          <button type="button" class:enabled={activeOverlays.eventReplay} on:click={() => toggleOverlay("eventReplay")}>
            <span>Event Replay</span>
            <small>{eventWindows.length} event windows, {tracks.length ? "sample track slider" : "track snippets unavailable"}</small>
          </button>
        </div>

        {#if activeOverlays.tradeFlows}
          <div class="shelf-section">
            <p class="shelf-label">Flow Focus</p>
            {#each flowSummaries.slice(0, 4) as flow}
              <button type="button" class="row-button" on:click={() => selectedDetail = { kind: "flow", id: flow.flow_id }}>
                <strong>{flow.label}</strong>
                <small>{flow.inferred_commodity ?? "Unknown"} | {pct(flow.inference_confidence)} confidence</small>
              </button>
            {/each}
          </div>
        {/if}

        {#if activeOverlays.fleet}
          <div class="shelf-section">
            <p class="shelf-label">Watchlists</p>
            {#each watchlists as watchlist}
              <div class="static-row">
                <strong>{watchlist.label}</strong>
                <small>{watchlist.vessel_ids.length} vessels | {watchlist.description}</small>
              </div>
            {/each}
          </div>
        {/if}

        {#if activeOverlays.eventReplay}
          <div class="shelf-section">
            <p class="shelf-label">Events</p>
            {#each eventWindows as event}
              <button type="button" class="row-button" on:click={() => selectedDetail = { kind: "event", id: event.event_id }}>
                <strong>{event.title}</strong>
                <small>{shortDate(event.start_at)} | {event.region}</small>
              </button>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    {#if displaySettingsOpen}
      <section class="settings-shelf display-settings" aria-label="Map display settings">
        <div class="shelf-header">
          <div>
            <p class="shelf-label">Display</p>
            <strong>Map Settings</strong>
          </div>
        </div>

        <div class="settings-toggle-row">
          <div>
            <strong>Show ports</strong>
            <small>Major terminals and workspace ports.</small>
          </div>
          <button
            type="button"
            class="compact-toggle"
            class:enabled={displaySettings.ports}
            on:click={togglePorts}
            aria-pressed={displaySettings.ports}
          >{displaySettings.ports ? "On" : "Off"}</button>
        </div>

        <div class="shelf-section">
          <div class="filter-header">
            <p class="shelf-label">Vessel Types</p>
            <div class="filter-actions">
              <button type="button" class="mini-action" on:click={() => setAllVesselGroups(true)}>All</button>
              <button type="button" class="mini-action" on:click={() => setAllVesselGroups(false)}>None</button>
            </div>
          </div>
          <div class="vessel-filter-grid">
            {#each VESSEL_GROUPS as group}
              <button
                type="button"
                class="vessel-filter"
                class:enabled={vesselGroupFilters[group] !== false}
                on:click={() => toggleVesselGroup(group)}
                aria-pressed={vesselGroupFilters[group] !== false}
              >
                <span class="filter-dot" style={`--filter-color: ${VESSEL_COLORS[group] ?? VESSEL_COLORS.unknown}`}></span>
                <span>{vesselTypeLabel(group)}</span>
              </button>
            {/each}
          </div>
        </div>
      </section>
    {/if}
  </div>

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
    {#if showCoverageChip}
      <a
        class="hud-row coverage-chip"
        href={AISSTREAM_COVERAGE_URL}
        target="_blank"
        rel="noreferrer"
        title={coverageChipTooltip}
      >
        <span class="hud-label">Coverage</span>
        <span class="hud-value coverage-chip-value">{coverageLabel(coverageStatus)} ↗</span>
      </a>
    {/if}
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

  {#if activeOverlays.eventReplay && selectedReplayTrack}
    <section class="replay-panel" aria-label="Event replay controls">
      <div class="replay-copy">
        <p class="shelf-label">Event Replay</p>
        <strong>{selectedReplayTrack.label}</strong>
        <small>
          {selectedReplayTrack.points.length} sample points |
          {shortDate(selectedReplayTrack.points[replayIndex]?.timestamp)}
        </small>
      </div>
      <select bind:value={replayTrackId} aria-label="Track snippet">
        {#each tracks as track}
          <option value={track.track_id}>{track.label}</option>
        {/each}
      </select>
      <input
        type="range"
        min="0"
        max={replayMax}
        bind:value={replayIndex}
        aria-label="Replay time"
      />
    </section>
  {:else if activeOverlays.eventReplay}
    <section class="replay-panel unavailable" aria-label="Event replay coverage">
      <div class="replay-copy">
        <p class="shelf-label">Event Replay</p>
        <strong>Track snippets unavailable</strong>
        <small>Live AIS viewport sampling does not provide historical track replay in this provider state.</small>
      </div>
      <small>{coverage?.caveats?.[0] ?? "Replay requires historical or sample track data."}</small>
    </section>
  {/if}

  {#if selectedDetail}
    <aside class="detail-drawer" aria-label="Sealanes detail">
      <div class="drawer-header">
        <div>
          <p class="shelf-label">
            {selectedDetail.kind === "chokepoint" ? "Chokepoint" : selectedDetail.kind === "flow" ? "Trade Flow" : selectedDetail.kind === "event" ? "Event" : "Vessel"}
          </p>
          <strong>
            {selectedChokepoint?.name ?? selectedFlow?.label ?? selectedVessel?.name ?? selectedEvent?.title ?? "Detail"}
          </strong>
        </div>
        <button type="button" class="shelf-action" on:click={() => selectedDetail = null}>Close</button>
      </div>

      {#if selectedChokepoint}
        <div class="drawer-grid">
          <div><span>Region</span><strong>{selectedChokepoint.region}</strong></div>
          <div><span>Vessels</span><strong>{selectedChokepoint.total_vessel_count}</strong></div>
          <div><span>Score</span><strong>{number(selectedChokepoint.congestion_score, 2)}</strong></div>
          <div><span>Label</span><strong>{selectedChokepoint.congestion_label}</strong></div>
        </div>
        <div class="drawer-section">
          <span>Commodity Links</span>
          <p>{selectedChokepoint.commodity_links.join(", ") || "No commodity link in sample"}</p>
        </div>
        <div class="drawer-section">
          <span>Vessel Mix</span>
          <p>{vesselMix(selectedChokepoint)}</p>
        </div>
        <div class="drawer-section">
          <span>Method</span>
          <p>{selectedChokepoint.methodology ?? "Static bounding box with sample AIS positions."}</p>
        </div>
        {#each selectedChokepoint.caveats as caveat}
          <div class="drawer-section">
            <span>Caveat</span>
            <p>{caveat}</p>
          </div>
        {/each}
      {:else if selectedFlow}
        <div class="drawer-grid">
          <div><span>Route</span><strong>{selectedFlow.route_label}</strong></div>
          <div><span>Vessels</span><strong>{selectedFlow.vessel_count}</strong></div>
          <div><span>Type</span><strong>{vesselTypeLabel(selectedFlow.vessel_type)}</strong></div>
          <div><span>Confidence</span><strong>{pct(selectedFlow.inference_confidence)}</strong></div>
        </div>
        <div class="drawer-section">
          <span>Commodity</span>
          <p>{selectedFlow.inferred_commodity ?? "Unknown"}</p>
        </div>
        <div class="drawer-section">
          <span>Summary</span>
          <p>{selectedFlow.summary ?? "No summary available."}</p>
        </div>
        <div class="drawer-section">
          <span>Caveat</span>
          <p>{selectedFlow.inference_caveat ?? "AIS does not confirm cargo; this is a proxy inference."}</p>
        </div>
      {:else if selectedVessel}
        <div class="drawer-grid">
          <div><span>MMSI</span><strong>{selectedVessel.identity.mmsi}</strong></div>
          <div><span>IMO</span><strong>{selectedVessel.identity.imo ?? "N/A"}</strong></div>
          <div><span>Class</span><strong>{selectedVessel.vessel_class}</strong></div>
          <div><span>Flag</span><strong>{selectedVessel.flag ?? "N/A"}</strong></div>
        </div>
        <div class="drawer-section">
          <span>Type</span>
          <p>{vesselTypeLabel(selectedVessel.vessel_type)}</p>
        </div>
        <div class="drawer-section">
          <span>Cargo Inference</span>
          <p>{selectedVessel.cargo_inference ?? "N/A"} | {pct(selectedVessel.cargo_inference_confidence)} confidence</p>
        </div>
        <div class="drawer-section">
          <span>Caveat</span>
          <p>{selectedVessel.cargo_inference_caveat ?? "AIS static and position messages do not confirm cargo."}</p>
        </div>
      {:else if selectedEvent}
        <div class="drawer-grid">
          <div><span>Region</span><strong>{selectedEvent.region}</strong></div>
          <div><span>Type</span><strong>{selectedEvent.event_type}</strong></div>
          <div><span>Start</span><strong>{shortDate(selectedEvent.start_at)}</strong></div>
          <div><span>End</span><strong>{shortDate(selectedEvent.end_at)}</strong></div>
        </div>
        <div class="drawer-section">
          <span>Summary</span>
          <p>{selectedEvent.summary}</p>
        </div>
        <div class="drawer-section">
          <span>Linked Chokepoints</span>
          <p>{selectedEvent.linked_chokepoint_ids.join(", ") || "None"}</p>
        </div>
        <div class="drawer-section">
          <span>Linked Flows</span>
          <p>{selectedEvent.linked_commodity_flows.join(", ") || "None"}</p>
        </div>
      {/if}
    </aside>
  {/if}
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
    padding: var(--space-3) var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .hud-row {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-xs);
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
    padding-left: var(--space-5);
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
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  .coverage-chip {
    color: inherit;
    text-decoration: none;
    border-top: 1px dashed color-mix(in srgb, var(--warning, #c49a5a) 35%, transparent);
    padding-top: var(--space-2);
    margin-top: 0.05rem;
    cursor: pointer;
  }

  .coverage-chip:hover .coverage-chip-value,
  .coverage-chip:focus-visible .coverage-chip-value {
    color: var(--warning, #c49a5a);
  }

  .coverage-chip-value {
    color: color-mix(in srgb, var(--warning, #c49a5a) 80%, var(--text-0, #f0f2f5));
  }

  /* ── Bottom-left: legend + 3D toggle ─────────────────────── */
  .map-bottom {
    position: absolute;
    bottom: 1.8rem; /* clear MapLibre attribution */
    left: 0.6rem;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .map-legend {
    display: flex;
    gap: var(--space-6);
    background: color-mix(in srgb, var(--bg-0, #070809) 90%, transparent);
    border: 1px solid var(--panel-border, #1e2228);
    padding: var(--space-2) var(--space-5);
  }

  .legend-item {
    font-size: var(--text-2xs);
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--text-2, #8a919a);
    display: flex;
    align-items: center;
    gap: var(--space-3);
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
    font-size: var(--text-2xs);
    padding: var(--space-2) var(--space-4);
    cursor: pointer;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }

  .map-ctrl-btn:hover,
  .map-ctrl-btn.active {
    color: var(--accent, #7aa6c8);
    border-color: color-mix(in srgb, var(--accent, #7aa6c8) 40%, var(--panel-border, #1e2228));
  }

  .settings-zone {
    position: absolute;
    top: 0.6rem;
    left: 0.6rem;
    z-index: 12;
    display: grid;
    gap: var(--space-4);
    width: min(21rem, calc(100% - 1.2rem));
    pointer-events: none;
  }

  .top-control-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: max-content;
    pointer-events: auto;
  }

  .settings-button,
  .settings-icon-button,
  .shelf-action,
  .compact-toggle,
  .mini-action,
  .row-button,
  .overlay-list button,
  .vessel-filter,
  .replay-panel select {
    font: inherit;
    border: 1px solid var(--panel-border, #1e2228);
    background: color-mix(in srgb, var(--bg-0, #070809) 93%, transparent);
    color: var(--text-1, #c2c8d0);
  }

  .settings-button {
    width: max-content;
    padding: var(--space-3) var(--space-4);
    font-size: var(--text-xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    pointer-events: auto;
  }

  .settings-icon-button {
    width: 1.78rem;
    height: 1.78rem;
    padding: 0;
    display: grid;
    place-items: center;
    cursor: pointer;
  }

  .settings-icon-button svg {
    width: 0.86rem;
    height: 0.86rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .settings-button:hover,
  .settings-button.active,
  .settings-icon-button:hover,
  .settings-icon-button.active,
  .shelf-action:hover,
  .compact-toggle:hover,
  .compact-toggle.enabled,
  .mini-action:hover,
  .row-button:hover,
  .overlay-list button:hover,
  .overlay-list button.enabled,
  .vessel-filter:hover,
  .vessel-filter.enabled {
    color: var(--accent, #7aa6c8);
    border-color: color-mix(in srgb, var(--accent, #7aa6c8) 42%, var(--panel-border, #1e2228));
  }

  .settings-shelf,
  .detail-drawer,
  .replay-panel {
    background: color-mix(in srgb, var(--bg-0, #070809) 94%, transparent);
    border: 1px solid var(--panel-border, #1e2228);
    pointer-events: auto;
  }

  .settings-shelf {
    display: grid;
    gap: var(--space-4);
    max-height: calc(100vh - 8rem);
    overflow: auto;
    padding: var(--space-5);
  }

  .display-settings {
    width: min(18rem, calc(100vw - 1.2rem));
  }

  .shelf-header,
  .coverage-mini,
  .drawer-header,
  .replay-panel {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .shelf-label {
    margin: 0;
    color: var(--text-2, #8a919a);
    font-size: var(--text-2xs);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .shelf-action {
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .compact-toggle,
  .mini-action {
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-2xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
  }

  .shelf-action:disabled {
    color: var(--text-2, #8a919a);
    cursor: not-allowed;
  }

  .coverage-mini {
    border-top: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    border-bottom: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    padding: var(--space-3) 0;
    color: var(--text-2, #8a919a);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .shelf-note {
    margin: 0;
    color: var(--warning, #c49a5a);
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  .overlay-list,
  .shelf-section {
    display: grid;
    gap: var(--space-3);
  }

  .settings-toggle-row,
  .filter-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-4);
    border-top: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    padding-top: var(--space-4);
  }

  .settings-toggle-row strong {
    display: block;
    color: var(--text-0, #f0f2f5);
    font-size: var(--text-sm);
  }

  .settings-toggle-row small {
    display: block;
    color: var(--text-2, #8a919a);
    font-size: var(--text-xs);
    line-height: 1.35;
    margin-top: var(--space-1);
  }

  .filter-actions {
    display: flex;
    gap: var(--space-2);
  }

  .vessel-filter-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .vessel-filter {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    color: var(--text-2, #8a919a);
    font-size: var(--text-xs);
    cursor: pointer;
    text-align: left;
  }

  .filter-dot {
    width: 0.42rem;
    height: 0.42rem;
    flex: 0 0 auto;
    border-radius: 50%;
    background: var(--filter-color);
    opacity: 0.55;
  }

  .vessel-filter.enabled .filter-dot {
    opacity: 1;
  }

  .overlay-list button,
  .row-button {
    display: grid;
    gap: var(--space-1);
    width: 100%;
    padding: var(--space-4) var(--space-4);
    text-align: left;
    cursor: pointer;
  }

  .overlay-list span,
  .row-button strong,
  .static-row strong,
  .drawer-header strong,
  .replay-copy strong {
    color: var(--text-0, #f0f2f5);
    font-size: var(--text-sm);
  }

  .overlay-list small,
  .row-button small,
  .static-row small,
  .drawer-section p,
  .replay-copy small {
    color: var(--text-2, #8a919a);
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  .static-row {
    display: grid;
    gap: var(--space-1);
    border-top: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    padding-top: var(--space-3);
  }

  .detail-drawer {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    z-index: 13;
    width: min(25rem, calc(100% - 1.2rem));
    max-height: calc(100% - 1.2rem);
    overflow: auto;
    padding: var(--space-5);
    display: grid;
    gap: var(--space-4);
  }

  .drawer-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
  }

  .drawer-grid div {
    padding: var(--space-4) var(--space-4);
    border-right: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    border-bottom: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    display: grid;
    gap: var(--space-1);
  }

  .drawer-grid div:nth-child(2n) {
    border-right: 0;
  }

  .drawer-grid div:nth-last-child(-n + 2) {
    border-bottom: 0;
  }

  .drawer-grid span,
  .drawer-section span {
    color: var(--text-2, #8a919a);
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .drawer-grid strong {
    color: var(--text-0, #f0f2f5);
    font-size: var(--text-sm);
  }

  .drawer-section {
    display: grid;
    gap: var(--space-1);
    border-top: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    padding-top: var(--space-4);
  }

  .drawer-section p {
    margin: 0;
    color: var(--text-1, #c2c8d0);
  }

  .replay-panel {
    position: absolute;
    left: 0.6rem;
    right: 0.6rem;
    bottom: 3.25rem;
    z-index: 11;
    align-items: center;
    padding: var(--space-4) var(--space-5);
  }

  .replay-copy {
    display: grid;
    min-width: min(24rem, 42%);
    gap: 0.08rem;
  }

  .replay-panel select {
    min-width: 15rem;
    max-width: 24rem;
    padding: var(--space-3) var(--space-4);
    font-size: var(--text-xs);
  }

  .replay-panel input[type="range"] {
    flex: 1;
    min-width: 8rem;
    accent-color: var(--accent, #7aa6c8);
  }

  /* ── MapLibre GL popup overrides ── */
  :global(.maplibregl-popup-content) {
    background: var(--bg-1, #0b0d10) !important;
    border: 1px solid var(--panel-border, #1e2228) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
    font-family: var(--app-font), monospace !important;
  }

  :global(.maplibregl-popup-tip) {
    display: none !important;
  }

  :global(.mp-inner) {
    padding: var(--space-4) var(--space-5);
    min-width: 180px;
  }

  :global(.mp-name) {
    display: block;
    color: var(--text-0, #f0f2f5);
    font-size: var(--text-base);
    margin-bottom: var(--space-3);
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
  }

  :global(.mp-row) {
    display: flex;
    justify-content: space-between;
    gap: var(--space-6);
    padding: var(--space-1) 0;
    font-size: var(--text-xs);
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

  :global(.mp-note) {
    margin-top: var(--space-3);
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider, rgba(50, 56, 64, 0.55));
    color: var(--text-2, #8a919a);
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  /* Keep MapLibre attribution minimal */
  :global(.maplibregl-ctrl-attrib) {
    background: color-mix(in srgb, #070809 88%, transparent) !important;
    font-size: var(--text-2xs) !important;
  }

  :global(.maplibregl-ctrl-attrib a) {
    color: var(--text-2, #8a919a) !important;
  }

  @media (max-width: 760px) {
    .map-bottom,
    .replay-panel,
    .shelf-header,
    .drawer-header {
      align-items: stretch;
      flex-direction: column;
    }

    .map-legend {
      flex-wrap: wrap;
      gap: var(--space-4);
    }

    .detail-drawer {
      left: 0.6rem;
      width: auto;
    }

    .replay-panel select {
      max-width: none;
      width: 100%;
    }
  }
</style>
