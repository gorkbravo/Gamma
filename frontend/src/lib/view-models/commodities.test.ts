import { describe, expect, it } from "vitest";
import type { CommodityCrossDomainLink, CommodityPriceReconciliation, CommoditySpreadSnapshot } from "../api/types";
import {
  buildCommodityCrossDomainHandoff,
  crossDomainLinkTargetTab,
  metalsFallbackNotes,
  observationDateLabel,
  pendingCommodityInstrument,
  reconciliationReferenceRows,
  reconciliationStatusLabel,
  spreadCurrentValueView,
  spreadObservationView
} from "./commodities";
import { maritimeFocusFromHandoff, resolveMaritimeFocus } from "./maritime";

function spread(overrides: Partial<CommoditySpreadSnapshot> = {}): CommoditySpreadSnapshot {
  return {
    definition: {
      spread_id: "gasoline-crack",
      label: "Gasoline 1-1 Crack Proxy",
      spread_type: "inter_commodity",
      left_leg_id: "gasoline",
      right_leg_id: "wti",
      unit: "USD/bbl",
      formula: "product price * 42 - crude price",
      rationale: null,
      source_provider: "gamma",
      retrieved_at: "2026-10-21T10:31:00",
      origin: "gamma.commodities.spread_definition",
      transformation_note: null
    },
    value: 23.54,
    previous_value: 23.1,
    change: 0.44,
    z_score: -2.1,
    percentile: 0.8,
    interpretation: "lower historical bucket",
    history: [],
    warnings: [],
    source_provider: "gamma",
    retrieved_at: "2026-10-21T10:31:00",
    origin: "gamma.commodities.spread_snapshot",
    transformation_note: null,
    ...overrides
  };
}

describe("commodity spread observation (GUA-20261021-2)", () => {
  it("labels the latest aligned observation date, never retrieved_at, and flags staleness", () => {
    const view = spreadObservationView(
      spread({
        observed_at: "2026-10-14T00:00:00",
        observation_lag_days: 7,
        freshness: "stale",
        stale_after_days: 4,
        leg_observed_at: { gasoline: "2026-10-14T00:00:00", wti: "2026-10-14T00:00:00" }
      })
    );

    expect(view.date).toBe("2026-10-14");
    expect(view.stale).toBe(true);
    expect(view.lagLabel).toBe("7d old");
    expect(view.title).toContain("gasoline 2026-10-14");
    expect(view.title).toContain("limit 4");
  });

  it("falls back to an unknown state when the payload has no observation date", () => {
    const view = spreadObservationView(spread());

    expect(view.date).toBe("N/A");
    expect(view.freshness).toBe("unknown");
    expect(view.stale).toBe(false);
  });

  it("keeps a date-only observation on its calendar day in any time zone", () => {
    expect(observationDateLabel("2026-10-14T00:00:00Z")).toBe("2026-10-14");
    expect(observationDateLabel("2026-10-14")).toBe("2026-10-14");
    expect(observationDateLabel(null)).toBe("N/A");
  });

  it("exposes the same-snapshot current value separately from the history value", () => {
    expect(spreadCurrentValueView(spread())).toBeNull();
    const current = spreadCurrentValueView(
      spread({
        current_value: 33.51,
        current_value_as_of: "2026-10-21T10:31:00",
        current_value_source: "IBKR front futures RBX6 / CLZ6 from one snapshot"
      })
    );
    expect(current).toEqual({
      value: 33.51,
      asOf: "2026-10-21T10:31:00",
      source: "IBKR front futures RBX6 / CLZ6 from one snapshot"
    });
  });
});

describe("commodity basis reconciliation rows (GUA-20261021-4)", () => {
  const reconciliation: CommodityPriceReconciliation = {
    instrument_id: "copper",
    status: "stale_reference",
    headline: {
      basis_id: "copper:curve_front",
      instrument_id: "copper",
      role: "curve_front",
      basis_type: "front_future",
      display_label: "IBKR front future Dec 2026",
      provider: "ibkr",
      value: 6.49,
      previous_value: null,
      change: null,
      change_pct: null,
      unit: "USD/lb",
      timestamp: "2026-10-21T10:31:00",
      source_timestamp: "2026-10-21T10:31:00",
      previous_source_timestamp: null,
      contract_month: "Dec 2026",
      contract_symbol: "HGZ6",
      provider_symbol: "HGZ6",
      freshness_label: null,
      warnings: [],
      source_provider: "ibkr",
      retrieved_at: "2026-10-21T10:31:00",
      origin: "ibkr",
      transformation_note: null
    },
    observations: [],
    summary: "Copper reference quotes are stale.",
    warnings: [],
    source_provider: "gamma",
    retrieved_at: "2026-10-21T10:31:00",
    origin: "gamma.commodities.price_reconciliation",
    transformation_note: null,
    stale_after_days: 4,
    comparisons: [
      {
        basis_id: "copper:history_latest",
        display_label: "FRED spot proxy",
        kind: "stale_reference",
        provider: "fred",
        value: 13542.82,
        unit: "USD/metric ton",
        observed_at: "2026-07-01T00:00:00",
        headline_value: 6.49,
        headline_unit: "USD/lb",
        headline_observed_at: "2026-10-21T10:31:00",
        converted_value: 6.1429,
        age_days: 112,
        difference: null,
        difference_pct: null,
        note: "Stale reference: it is dated 2026-07-01, 112 days before the headline (2026-10-21)."
      }
    ]
  };

  it("lists the headline first and every reference with its date, unit and converted value", () => {
    const rows = reconciliationReferenceRows(reconciliation);

    expect(rows.map((row) => row.kind)).toEqual(["headline", "stale_reference"]);
    expect(rows[0]).toMatchObject({ label: "IBKR front future Dec 2026", unit: "USD/lb", date: "2026-10-21" });
    expect(rows[1]).toMatchObject({
      label: "FRED spot proxy",
      unit: "USD/metric ton",
      date: "2026-07-01",
      convertedValue: 6.1429,
      convertedUnit: "USD/lb",
      ageDays: 112,
      differencePct: null,
      kindLabel: "Stale",
      tone: "warning"
    });
  });

  it("names the reconciliation statuses so a basis is not read as a conflict", () => {
    expect(reconciliationStatusLabel("basis")).toBe("Futures-spot basis");
    expect(reconciliationStatusLabel("stale_reference")).toBe("Stale reference");
    expect(reconciliationStatusLabel("conflict")).toBe("Data conflict");
    expect(reconciliationReferenceRows(null)).toEqual([]);
  });
});

describe("commodity cross-domain handoffs (GUA-20261021-7)", () => {
  function link(overrides: Partial<CommodityCrossDomainLink> = {}): CommodityCrossDomainLink {
    return {
      link_id: "maritime-energy-chokepoints",
      target_domain: "maritime",
      target_label: "Sealanes Energy Chokepoints",
      relationship: "shipping_context",
      linked_instrument_ids: ["wti", "brent", "henry_hub", "heating_oil"],
      summary: null,
      confidence: 0.5,
      source_provider: "gamma",
      retrieved_at: null,
      origin: "gamma.commodities.cross_domain",
      transformation_note: null,
      target_tab: "maritime",
      target_mode: "chokepoints",
      target_ids: {},
      ...overrides
    };
  }

  it("builds a Sealanes chokepoint-group envelope with the commodity links as metadata", () => {
    const handoff = buildCommodityCrossDomainHandoff(link(), {
      instrument: { instrument_id: "brent", name: "Brent Crude Oil" },
      sourceMode: "energy",
      now: new Date("2026-10-21T10:31:00Z")
    });

    expect(handoff).toMatchObject({
      source_tab: "commodities",
      source_mode: "energy",
      intended_target_tab: "maritime",
      intended_target_mode: "chokepoints",
      timestamp: "2026-10-21T10:31:00.000Z",
      selected_entity: {
        entity_type: "maritime_chokepoint_group",
        label: "Sealanes Energy Chokepoints",
        metadata: {
          source_commodity_id: "brent",
          commodity_links: ["crude oil", "LNG", "refined products"],
          cross_domain_links: [
            {
              link_id: "maritime-energy-chokepoints",
              relationship: "shipping_context",
              linked_instrument_ids: ["wti", "brent", "henry_hub", "heating_oil"],
              selected_instrument_id: "brent"
            }
          ]
        }
      }
    });
  });

  // Integración Commodities → Sealanes: el grupo debe resolverse a chokepoints, no a "no tracked".
  it("resolves the Sealanes chokepoint group on the receiving side", () => {
    const handoff = buildCommodityCrossDomainHandoff(link(), { instrument: { instrument_id: "brent", name: "Brent Crude Oil" } });
    const request = maritimeFocusFromHandoff(handoff!);
    const chokepoint = (id: string, commodities: string[]) => ({
      chokepoint_id: id,
      name: id,
      strategic_commodities: commodities,
      bounding_box: { min_latitude: 25, max_latitude: 27.5, min_longitude: 55, max_longitude: 57.5 }
    });
    const focus = resolveMaritimeFocus(request, {
      chokepoints: [chokepoint("hormuz", ["crude oil", "LNG"]), chokepoint("panama", ["containers"])] as never,
      chokepoint_summaries: [],
      coverage: null as never
    });

    expect(focus?.status).toBe("resolved");
    expect(focus && "chokepointIds" in focus ? focus.chokepointIds : []).toEqual(["hormuz"]);
  });

  it("passes the Macro lens through normalized ids and resolves legacy links by domain", () => {
    const macro = buildCommodityCrossDomainHandoff(
      link({
        link_id: "macro-inflation-energy",
        target_domain: "macro",
        target_label: "Macro Inflation",
        target_tab: "macro",
        target_mode: "snapshot",
        target_ids: { theme: "inflation" }
      })
    );
    expect(macro?.intended_target_tab).toBe("macro");
    expect(macro?.normalized_ids).toEqual({ theme: "inflation" });
    expect(macro?.selected_entity?.entity_type).toBe("commodity_cross_domain_link");

    expect(crossDomainLinkTargetTab(link({ target_tab: null, target_domain: "prediction_markets" }))).toBe(
      "prediction_markets"
    );
    expect(buildCommodityCrossDomainHandoff(link({ target_tab: null, target_domain: "weather" }))).toBeNull();
  });
});

describe("pending commodity instrument (wrong-market header, 2026-10-21)", () => {
  it("reports the requested instrument only while it differs from the loaded one", () => {
    expect(pendingCommodityInstrument(true, "brent", "wti")).toBe("brent");
    expect(pendingCommodityInstrument(true, "brent", "brent")).toBeNull();
    expect(pendingCommodityInstrument(false, "brent", "wti")).toBeNull();
    expect(pendingCommodityInstrument(true, null, "wti")).toBeNull();
  });
});

describe("metals fallback notes (GUA-20261021-8, live check 2026-10-27)", () => {
  it("keeps only the retired FRED fallback warnings, once each", () => {
    const retired =
      "No FRED fallback is configured for Gold, Silver, Platinum: GOLDAMGBD228NLBM, SLVPRUSD, PPLTUSDM failed with HTTPError in the 2026-10-21 audit and are treated as discontinued, so these markets rely on IBKR futures only.";
    expect(
      metalsFallbackNotes([
        "Using cached IBKR curve for Gold from 2026-10-27T12:53:17; no fresh TWS request was made.",
        retired,
        retired
      ])
    ).toEqual([retired]);
    expect(metalsFallbackNotes(null)).toEqual([]);
  });
});
