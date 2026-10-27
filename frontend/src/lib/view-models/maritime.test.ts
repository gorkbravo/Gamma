import { describe, expect, it } from "vitest";
import type {
  CrossTabHandoffEnvelope,
  MaritimeChokepointDefinition,
  MaritimeChokepointSummary,
  MaritimeCoverageMetadata
} from "../api/types";
import {
  buildMaritimeFocusRequest,
  chokepointFocusBounds,
  findMaritimeChokepoint,
  maritimeCoverageNote,
  maritimeFocusFromHandoff,
  resolveMaritimeFocus
} from "./maritime";

// GUA-20261021-7: el handoff "Open in Sealanes" debe encuadrar el chokepoint o explicar por qué no puede.

function chokepoint(
  id: string,
  name: string,
  box: [number, number, number, number],
  commodities: string[]
): MaritimeChokepointDefinition {
  const [minLat, maxLat, minLon, maxLon] = box;
  return {
    chokepoint_id: id,
    name,
    region: "Region",
    latitude: (minLat + maxLat) / 2,
    longitude: (minLon + maxLon) / 2,
    bounding_box: { min_latitude: minLat, max_latitude: maxLat, min_longitude: minLon, max_longitude: maxLon },
    strategic_commodities: commodities,
    description: null,
    source_provider: "gamma_static_reference",
    retrieved_at: null,
    origin: "gamma.maritime.static_reference.chokepoints",
    transformation_note: null
  };
}

const CHOKEPOINTS = [
  chokepoint("hormuz", "Strait of Hormuz", [25.0, 27.3, 55.0, 57.4], ["crude oil", "refined products", "LNG"]),
  chokepoint("suez", "Suez Canal", [29.75, 31.3, 31.85, 32.75], ["crude oil", "LNG", "containers"]),
  chokepoint("bab-el-mandeb", "Bab el-Mandeb", [11.8, 13.3, 42.7, 44.1], ["crude oil", "refined products", "containers"]),
  chokepoint("panama", "Panama Canal", [8.75, 9.45, -80.1, -79.35], ["containers", "refined products", "LNG"]),
  chokepoint("malacca", "Strait of Malacca", [1.0, 5.8, 99.0, 104.5], ["crude oil", "LNG", "containers", "dry bulk"])
];

function summary(id: string, total = 0): MaritimeChokepointSummary {
  return {
    chokepoint_id: id,
    name: id,
    region: "Region",
    coverage_status: "unavailable",
    total_vessel_count: total,
    vessel_count_by_type: {},
    baseline_vessel_count: null,
    congestion_score: null,
    congestion_label: "unavailable",
    commodity_links: [],
    methodology: null,
    caveats: [],
    source_provider: "gamma",
    retrieved_at: null,
    origin: "gamma.maritime.chokepoint_summary",
    transformation_note: null,
    position_sample_note: "No live AIS positions in last 6 s sample"
  };
}

function coverage(overrides: Partial<MaritimeCoverageMetadata> = {}): MaritimeCoverageMetadata {
  return {
    coverage_status: "unavailable",
    provider_id: "aisstream",
    provider_label: "AISstream",
    freshness_label: "live_stream_empty_sample",
    regions: [],
    as_of: null,
    source_timestamp: null,
    caveats: [],
    credential_env_vars: [],
    supports_live: true,
    supports_historical: false,
    source_provider: "aisstream",
    retrieved_at: null,
    origin: "aisstream.coverage",
    transformation_note: null,
    sample_window_seconds: 6,
    ...overrides
  };
}

const EMPTY_SAMPLE_WORKSPACE = {
  chokepoints: CHOKEPOINTS,
  chokepoint_summaries: CHOKEPOINTS.map((item) => summary(item.chokepoint_id)),
  coverage: coverage()
};

function predictionHormuzHandoff(): CrossTabHandoffEnvelope {
  return {
    source_tab: "prediction_markets",
    source_mode: "contract",
    selected_entity: {
      entity_type: "maritime_chokepoint",
      label: "Strait of Hormuz",
      normalized_id: "hormuz",
      provider_id: null,
      native_id: null,
      metadata: { matched_terms: ["strait of hormuz"] }
    },
    selected_timeframe: null,
    provider: "polymarket",
    source: null,
    warnings: [],
    normalized_ids: { market_id: "pm-1", chokepoint_id: "hormuz" },
    timestamp: "2026-10-21T10:00:00Z",
    intended_target_tab: "maritime",
    intended_target_mode: "chokepoints"
  };
}

describe("maritimeFocusFromHandoff", () => {
  it("reads the Prediction Markets chokepoint envelope", () => {
    const request = maritimeFocusFromHandoff(predictionHormuzHandoff(), 7);

    expect(request).toEqual({
      requestId: 7,
      sourceTab: "prediction_markets",
      lens: "chokepoints",
      chokepointId: "hormuz",
      entityLabel: "Strait of Hormuz",
      entityType: "maritime_chokepoint",
      commodityLinks: []
    });
  });

  it("ignores envelopes for other tabs and issues increasing request ids", () => {
    expect(maritimeFocusFromHandoff({ ...predictionHormuzHandoff(), intended_target_tab: "macro" })).toBeNull();

    const first = maritimeFocusFromHandoff(predictionHormuzHandoff());
    const second = maritimeFocusFromHandoff(predictionHormuzHandoff());
    expect(second!.requestId).toBeGreaterThan(first!.requestId);
  });

  it("falls back to the live map lens when no chokepoint is named and the mode is unknown", () => {
    const request = buildMaritimeFocusRequest({ requestId: 1, entityLabel: "Shipping disruption context", lens: "risk" });

    expect(request.lens).toBe("live_map");
    expect(request.chokepointId).toBeNull();
  });
});

describe("resolveMaritimeFocus", () => {
  it("pans to Hormuz with an honest empty-sample coverage note", () => {
    const request = maritimeFocusFromHandoff(predictionHormuzHandoff(), 3);
    const focus = resolveMaritimeFocus(request, EMPTY_SAMPLE_WORKSPACE);

    expect(focus?.status).toBe("resolved");
    if (focus?.status !== "resolved") throw new Error("expected a resolved focus");
    expect(focus.requestId).toBe(3);
    expect(focus.mode).toBe("chokepoints");
    expect(focus.title).toBe("Strait of Hormuz");
    expect(focus.sourceLabel).toBe("Prediction Markets");
    expect(focus.chokepointIds).toEqual(["hormuz"]);
    expect(focus.note).toBe("0 AIS positions in the last 6 s sample · AISstream coverage varies by region");
    const [[west, south], [east, north]] = focus.bounds;
    expect(west).toBeLessThan(55.0);
    expect(south).toBeLessThan(25.0);
    expect(east).toBeGreaterThan(57.4);
    expect(north).toBeGreaterThan(27.3);
    // El encuadre es regional (por encima del umbral de zoom AIS), no el Atlántico por defecto.
    expect(east - west).toBeLessThan(6);
  });

  it("resolves an entity named only by label", () => {
    for (const [label, expected] of [
      ["Strait of Hormuz", "hormuz"],
      ["Hormuz", "hormuz"],
      ["Bab el Mandeb", "bab-el-mandeb"],
      ["Suez", "suez"],
      ["Strait of Hormuz traffic returns to normal by December 31?", "hormuz"]
    ] as const) {
      expect(findMaritimeChokepoint(CHOKEPOINTS, null, label)?.chokepoint_id, label).toBe(expected);
    }
    expect(findMaritimeChokepoint(CHOKEPOINTS, null, "Suez and Bab el-Mandeb disruption")).toBeNull();
  });

  it("states an explicit fallback for an unknown entity instead of a silent default view", () => {
    const request = buildMaritimeFocusRequest({
      requestId: 9,
      sourceTab: "prediction_markets",
      lens: "chokepoints",
      chokepointId: "cape-of-good-hope",
      entityLabel: "Cape of Good Hope"
    });
    const focus = resolveMaritimeFocus(request, EMPTY_SAMPLE_WORKSPACE);

    expect(focus?.status).toBe("unresolved");
    if (focus?.status !== "unresolved") throw new Error("expected an unresolved focus");
    expect(focus.title).toBe("Cape of Good Hope");
    expect(focus.message).toContain('"Cape of Good Hope" is not a chokepoint Sealanes tracks; showing the default view.');
    expect(focus.message).toContain("Strait of Hormuz");
  });

  it("says when no chokepoint geography is loaded at all", () => {
    const request = maritimeFocusFromHandoff(predictionHormuzHandoff(), 4);
    const focus = resolveMaritimeFocus(request, { chokepoints: [], chokepoint_summaries: [], coverage: coverage() });

    expect(focus?.status).toBe("unresolved");
    if (focus?.status !== "unresolved") throw new Error("expected an unresolved focus");
    expect(focus.message).toContain("no chokepoint reference geography is loaded");
  });

  it("waits for the workspace before deciding", () => {
    expect(resolveMaritimeFocus(maritimeFocusFromHandoff(predictionHormuzHandoff()), null)).toBeNull();
    expect(resolveMaritimeFocus(null, EMPTY_SAMPLE_WORKSPACE)).toBeNull();
  });

  it("focuses a commodity group such as the Commodities energy chokepoints row", () => {
    const request = buildMaritimeFocusRequest({
      requestId: 5,
      sourceTab: "commodities",
      lens: "chokepoints",
      entityLabel: "Sealanes Energy Chokepoints",
      entityType: "maritime_chokepoint_group",
      commodityLinks: ["crude oil", "LNG"]
    });
    const focus = resolveMaritimeFocus(request, EMPTY_SAMPLE_WORKSPACE);

    expect(focus?.status).toBe("resolved");
    if (focus?.status !== "resolved") throw new Error("expected a resolved focus");
    expect(focus.title).toBe("Sealanes Energy Chokepoints");
    expect(focus.chokepointIds).toEqual(["hormuz", "suez", "bab-el-mandeb", "panama", "malacca"]);
    expect(focus.note).toBe("0 AIS positions across 5 boxes in the last 6 s sample · AISstream coverage varies by region");
  });
});

describe("maritimeCoverageNote", () => {
  it("labels sample data and missing samples without implying live coverage", () => {
    expect(
      maritimeCoverageNote(coverage({ coverage_status: "sample", provider_label: "Sample Maritime Dataset" }), [summary("hormuz", 3)])
    ).toBe("3 sample positions · Sample Maritime Dataset is not live AIS");
    expect(maritimeCoverageNote(coverage({ sample_window_seconds: null }), [summary("hormuz")])).toBe(
      "No live AIS sample was taken (unavailable) · static chokepoint geography only"
    );
    expect(maritimeCoverageNote(coverage({ coverage_status: "partial" }), [summary("hormuz", 1)])).toBe(
      "1 AIS position in the last 6 s sample · AISstream coverage varies by region"
    );
  });

  it("pads tiny boxes so the focus never collapses to a point", () => {
    const [[west, south], [east, north]] = chokepointFocusBounds([CHOKEPOINTS[3]]);
    expect(east - west).toBeGreaterThan(1.5);
    expect(north - south).toBeGreaterThan(1.5);
  });
});
