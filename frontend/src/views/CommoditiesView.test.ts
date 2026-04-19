import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CommodityWorkspaceResponse } from "../lib/api/types";
import CommoditiesView from "./CommoditiesView.svelte";

describe("CommoditiesView", () => {
  it("renders the commodities workspace shell with curves, spreads, inventories, and cross-domain context", () => {
    const { body } = render(CommoditiesView, {
      props: {
        workspace: makeWorkspace(),
        loading: false,
        mode: "overview",
        onLoadWorkspace: vi.fn()
      }
    });

    expect(body).toContain("Commodities Research");
    expect(body).toContain("Overview");
    expect(body).toContain("Energy");
    expect(body).toContain("Metals");
    expect(body).toContain("WTI Crude Oil");
    expect(body).toContain("backwardation");
    expect(body).toContain("WTI M1-M2");
    expect(body).toContain("US Commercial Crude Stocks");
    expect(body).toContain("EIA Weekly Petroleum Status Report");
    expect(body).toContain("Macro Inflation");
    expect(body).toContain("Sample Commodities Dataset");
  });
});

function makeWorkspace(): CommodityWorkspaceResponse {
  const retrievedAt = "2026-04-19T12:00:00Z";
  const wti = {
    instrument_id: "wti",
    symbol: "CL",
    name: "WTI Crude Oil",
    family: "energy",
    subgroup: "crude",
    quote_unit: "USD/bbl",
    currency: "USD",
    exchange: "NYMEX",
    front_symbol: "CL",
    provider_symbols: { sample: "CL" },
    aliases: ["wti", "cl"],
    description: "WTI research instrument.",
    source_provider: "sample_data",
    retrieved_at: retrievedAt,
    origin: "sample_commodities.instruments",
    transformation_note: "Sample metadata."
  };
  const gold = {
    ...wti,
    instrument_id: "gold",
    symbol: "GC",
    name: "Gold",
    family: "metals",
    subgroup: "precious",
    quote_unit: "USD/oz",
    exchange: "COMEX",
    front_symbol: "GC"
  };
  const contract = {
    contract_id: "wti-2026-05",
    instrument_id: "wti",
    symbol: "CLK26",
    contract_month: "May 2026",
    expiry_date: "2026-05-20T00:00:00Z",
    is_front_month: true,
    source_provider: "sample_data",
    retrieved_at: retrievedAt,
    origin: "sample_commodities.contracts",
    transformation_note: "Sample contract."
  };
  return {
    mode: "overview",
    selected_instrument_id: "wti",
    available_modes: ["overview", "energy", "metals", "curves_spreads", "inventories_fundamentals", "events_cross_domain"],
    coverage: {
      coverage_status: "sample",
      provider_id: "sample_commodities",
      provider_label: "Sample Commodities Dataset",
      freshness_label: "mocked",
      instruments: ["wti", "gold"],
      regions: ["US", "Global"],
      as_of: retrievedAt,
      source_timestamp: retrievedAt,
      caveats: ["Sample commodities data."],
      credential_env_vars: [],
      supports_prices: true,
      supports_curves: true,
      supports_inventories: true,
      supports_events: true,
      source_provider: "sample_data",
      retrieved_at: retrievedAt,
      origin: "sample_commodities.coverage",
      transformation_note: "Sample coverage."
    },
    instruments: [wti, gold],
    market_summaries: [
      {
        instrument: wti,
        latest_price: 79.2,
        latest_change: 0.4,
        latest_change_pct: 0.005,
        curve_state: "backwardation",
        front_spread: 0.75,
        inventory_signal: "draw | low versus available history",
        summary: "WTI curve is backwardation.",
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.market_summary",
        transformation_note: "Gamma summary."
      },
      {
        instrument: gold,
        latest_price: 2392,
        latest_change: -3,
        latest_change_pct: -0.001,
        curve_state: "contango",
        front_spread: -5,
        inventory_signal: null,
        summary: "Gold curve is contango.",
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.market_summary",
        transformation_note: "Gamma summary."
      }
    ],
    price_histories: [
      {
        instrument_id: "wti",
        label: "WTI sample price",
        unit: "USD/bbl",
        points: [
          {
            instrument_id: "wti",
            timestamp: "2026-04-18T00:00:00Z",
            value: 78.8,
            unit: "USD/bbl",
            source_provider: "sample_data",
            retrieved_at: retrievedAt,
            origin: "sample_commodities.price_history",
            transformation_note: "Sample price."
          },
          {
            instrument_id: "wti",
            timestamp: "2026-04-19T00:00:00Z",
            value: 79.2,
            unit: "USD/bbl",
            source_provider: "sample_data",
            retrieved_at: retrievedAt,
            origin: "sample_commodities.price_history",
            transformation_note: "Sample price."
          }
        ],
        source_provider: "sample_data",
        retrieved_at: retrievedAt,
        origin: "sample_commodities.price_history",
        transformation_note: "Synthetic offline price path."
      }
    ],
    curves: [
      {
        instrument_id: "wti",
        as_of: retrievedAt,
        nodes: [
          {
            contract,
            price: 79.2,
            previous_price: 78.9,
            change: 0.3,
            days_to_expiry: 30,
            source_provider: "sample_data",
            retrieved_at: retrievedAt,
            origin: "sample_commodities.curve_nodes",
            transformation_note: "Sample node."
          },
          {
            contract: { ...contract, contract_id: "wti-2026-06", symbol: "CLM26", contract_month: "Jun 2026" },
            price: 78.45,
            previous_price: 78.4,
            change: 0.05,
            days_to_expiry: 60,
            source_provider: "sample_data",
            retrieved_at: retrievedAt,
            origin: "sample_commodities.curve_nodes",
            transformation_note: "Sample node."
          }
        ],
        shape_label: "backwardation",
        front_spread: 0.75,
        front_spread_pct: 0.009,
        m1_m6_spread: 2.95,
        curve_slope: -2.95,
        roll_yield_proxy_pct: 11.2,
        summary: "WTI curve is backwardation.",
        warnings: ["Roll-yield proxy is a heuristic."],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.curve_analytics",
        transformation_note: "Gamma curve analytics."
      }
    ],
    spreads: [
      {
        definition: {
          spread_id: "wti-m1-m2",
          label: "WTI M1-M2",
          spread_type: "calendar",
          left_leg_id: "wti:M1",
          right_leg_id: "wti:M2",
          unit: "price",
          formula: "front minus deferred",
          rationale: "Calendar spreads expose term-structure tightness.",
          source_provider: "gamma",
          retrieved_at: retrievedAt,
          origin: "gamma.commodities.spread_definition",
          transformation_note: "Gamma spread."
        },
        value: 0.75,
        previous_value: 0.7,
        change: 0.05,
        z_score: 1.1,
        percentile: 82,
        interpretation: "upper historical bucket",
        history: [],
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.spread_snapshot",
        transformation_note: "Gamma spread analytics."
      }
    ],
    inventories: [
      {
        metadata: {
          series_id: "us-commercial-crude-stocks",
          instrument_id: "wti",
          label: "US Commercial Crude Stocks",
          category: "inventories",
          unit: "million bbl",
          frequency: "weekly",
          provider_series_id: null,
          source_provider: "sample_data",
          retrieved_at: retrievedAt,
          origin: "sample_commodities.inventory_metadata",
          transformation_note: "Sample inventory."
        },
        points: [],
        latest_value: 432,
        latest_change: -1.5,
        seasonal_percentile: 22,
        interpretation: "draw | low versus available history",
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.inventory_context",
        transformation_note: "Gamma inventory context."
      }
    ],
    events: [
      {
        event_id: "eia-wpsr",
        title: "EIA Weekly Petroleum Status Report",
        category: "official_release",
        scheduled_at: "2026-04-22T14:30:00Z",
        relative_label: "Weekly",
        importance: "high",
        linked_instrument_ids: ["wti"],
        summary: "Official weekly US petroleum inventory context.",
        source_provider: "sample_data",
        retrieved_at: retrievedAt,
        origin: "sample_commodities.events",
        transformation_note: "Sample event."
      }
    ],
    cross_domain_links: [
      {
        link_id: "macro-inflation-energy",
        target_domain: "macro",
        target_label: "Macro Inflation",
        relationship: "inflation_input",
        linked_instrument_ids: ["wti"],
        summary: "Energy prices can frame inflation impulse research.",
        confidence: 0.55,
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.cross_domain",
        transformation_note: "Heuristic link."
      }
    ],
    warnings: ["Commodities is read-only research context."],
    source_provider: "gamma",
    retrieved_at: retrievedAt,
    origin: "gamma.commodities.workspace",
    transformation_note: "Gamma workspace."
  };
}
