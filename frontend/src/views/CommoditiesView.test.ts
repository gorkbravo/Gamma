import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CommodityWorkspaceResponse } from "../lib/api/types";
import { commoditiesRequestedInstrumentId } from "../lib/stores/app";
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

    expect(body).toContain("Commodities");
    expect(body).toContain("Overview");
    expect(body).toContain("Energy");
    expect(body).toContain("Metals");
    expect(body).toContain("Term Structure Stack");
    expect(body).toContain("Commodity Matrix");
    expect(body).toContain("Momentum / Roll Scatter");
    expect(body).toContain("Market Regime Ranks");
    expect(body).toContain("WTI Crude Oil");
    expect(body).toContain("backwardation");
    expect(body).toContain("WTI M1-M2");
    expect(body).toContain("US Commercial Crude Stocks");
    expect(body).toContain("EIA Weekly Petroleum Status Report");
    expect(body).toContain("Macro Inflation");
    expect(body).toContain("Sample Commodities Dataset");
    expect(body).toContain("Sample generated");
    expect(body).toContain("Headline");
    expect(body).toContain('aria-label="Strategy actions for CL"');
    expect(body).toContain('tabindex="0"');
  });

  it("shows reconciliation detail only when basis conflict exists", () => {
    const workspace = makeWorkspace();
    const conflictBasis = {
      ...workspace.market_summaries[0].quote_basis!,
      basis_id: "wti:curve_front",
      basis_type: "front_future",
      display_label: "IBKR front future May 2026",
      provider: "ibkr",
      value: 84,
      change: -2,
      change_pct: -0.023256,
      contract_month: "May 2026",
      contract_symbol: "CLK26",
      source_provider: "ibkr"
    };
    workspace.market_summaries[0] = {
      ...workspace.market_summaries[0],
      latest_price: 84,
      latest_change: -2,
      latest_change_pct: -0.023256,
      quote_basis: conflictBasis
    };
    workspace.price_reconciliations[0] = {
      ...workspace.price_reconciliations[0],
      status: "conflict",
      headline: conflictBasis,
      observations: [conflictBasis, workspace.price_reconciliations[0].observations[0]],
      summary: "WTI Crude Oil has a material basis mismatch across 2 loaded quote references.",
      warnings: ["Commodity basis conflict for WTI Crude Oil: headline IBKR front future May 2026 84.00 differs from FRED spot proxy 95.00 by 13.1%."]
    };

    const { body } = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "energy",
        onLoadWorkspace: vi.fn()
      }
    });

    expect(body).toContain("Basis Reconciliation");
    expect(body).toContain("IBKR front future May 2026");
    expect(body).toContain("FRED spot proxy");
  });

  it("surfaces degraded provider notices without requiring inventory data", () => {
    const workspace = makeWorkspace();
    workspace.mode = "inventories_fundamentals";
    workspace.coverage.coverage_status = "official_partial";
    workspace.coverage.freshness_label = "delayed";
    workspace.coverage.caveats = ["EIA coverage is official but partial and release-lagged."];
    workspace.warnings = ["IBKR futures curve unavailable; using fallback payload."];
    workspace.inventories = [];

    const { body } = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "inventories_fundamentals",
        onLoadWorkspace: vi.fn()
      }
    });

    expect(body).toContain("OFFICIAL PARTIAL");
    expect(body).toContain("EIA coverage is official but partial and release-lagged.");
    expect(body).toContain("No inventory series linked.");
  });

  it("renders the deep energy flow modules", () => {
    const workspace = makeWorkspace();
    workspace.mode = "energy";

    const { body } = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "energy",
        onLoadWorkspace: vi.fn()
      }
    });

    expect(body).toContain("Crack Spread Matrix");
    expect(body).toContain("Term Structure Heatmap");
    expect(body).toContain("Inventory vs Seasonality");
    expect(body).toContain("Vessel / Flow Proxy");
    expect(body).toContain("EIA Fundamental Stack");
    expect(body).toContain("Fundamental Tape");
  });

  it("renders the deep metals macro modules", () => {
    const workspace = makeWorkspace();
    workspace.mode = "metals";
    workspace.selected_instrument_id = "gold";

    const { body } = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "metals",
        onLoadWorkspace: vi.fn(),
        onLoadMacroSeries: vi.fn()
      }
    });

    expect(body).toContain("Macro Driver Correlation");
    expect(body).toContain("Precious Ratio Gauges");
    expect(body).toContain("LME / COMEX Warehouse Stocks");
    expect(body).toContain("Substitution Spreads");
  });

  it("names the retired FRED metals fallbacks under the metals snapshot (live check 2026-10-27)", () => {
    const workspace = makeWorkspace();
    workspace.mode = "metals";
    workspace.selected_instrument_id = "gold";
    workspace.warnings = [
      ...workspace.warnings,
      "No FRED fallback is configured for Gold, Silver, Platinum: GOLDAMGBD228NLBM, SLVPRUSD, PPLTUSDM failed with HTTPError in the 2026-10-21 audit and are treated as discontinued, so these markets rely on IBKR futures only."
    ];

    const metals = render(CommoditiesView, {
      props: { workspace, loading: false, mode: "metals", onLoadWorkspace: vi.fn(), onLoadMacroSeries: vi.fn() }
    });
    const energy = render(CommoditiesView, {
      props: {
        workspace: { ...workspace, mode: "energy" },
        loading: false,
        mode: "energy",
        onLoadWorkspace: vi.fn(),
        onLoadMacroSeries: vi.fn()
      }
    });

    expect(metals.body).toContain("No FRED fallback is configured for Gold, Silver, Platinum");
    expect(energy.body).not.toContain("No FRED fallback is configured");
  });

  it("keeps instruments without loaded curves selectable for on-demand curve pulls", () => {
    const workspace = makeWorkspace();
    workspace.mode = "curves_spreads";
    workspace.instruments.push({
      ...workspace.instruments[1],
      instrument_id: "nickel",
      symbol: "NI",
      name: "Nickel",
      subgroup: "industrial",
      quote_unit: "USD/metric ton",
      exchange: "LME",
      front_symbol: null
    });
    workspace.market_summaries.push({
      ...workspace.market_summaries[1],
      instrument: workspace.instruments[2],
      latest_price: 15900,
      curve_state: "unavailable",
      front_spread: null,
      summary: "Nickel curve unavailable."
    });

    const { body } = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "curves_spreads",
        onLoadWorkspace: vi.fn()
      }
    });

    expect(body).toContain('value="nickel"');
  });

  it("shows each spread's observation date, a stale tag and the same-snapshot live value (GUA-20261021-2)", () => {
    const workspace = makeWorkspace();
    workspace.mode = "energy";
    workspace.spreads.push({
      ...workspace.spreads[0],
      definition: {
        ...workspace.spreads[0].definition,
        spread_id: "gasoline-crack",
        label: "Gasoline 1-1 Crack Proxy",
        spread_type: "inter_commodity",
        left_leg_id: "gasoline",
        right_leg_id: "wti",
        unit: "USD/bbl",
        formula: "product price * 42 - crude price"
      },
      value: 23.54,
      percentile: 0.8,
      observed_at: "2026-10-14T00:00:00",
      observation_lag_days: 7,
      freshness: "stale",
      stale_after_days: 4,
      leg_observed_at: { gasoline: "2026-10-14T00:00:00", wti: "2026-10-14T00:00:00" },
      current_value: 33.51,
      current_value_as_of: "2026-10-21T10:31:00",
      current_value_source: "IBKR front futures RBX6 / CLZ6 from one snapshot"
    });
    workspace.spreads[0] = { ...workspace.spreads[0], observed_at: "2026-04-19T12:00:00", freshness: "current", observation_lag_days: 0 };

    const { body } = render(CommoditiesView, {
      props: { workspace, loading: false, mode: "energy", onLoadWorkspace: vi.fn() }
    });

    expect(body).toContain("Gasoline 1-1 Crack Proxy");
    expect(body).toContain("2026-10-14");
    expect(body).toContain("Stale 7d old");
    expect(body).toContain("Live 33.51");
    expect(body).toContain("2026-04-19");
  });

  it("lists stale basis references with their dates and units instead of a conflict (GUA-20261021-4)", () => {
    const workspace = makeWorkspace();
    const headline = {
      ...workspace.market_summaries[0].quote_basis!,
      basis_id: "wti:curve_front",
      basis_type: "front_future",
      display_label: "IBKR cached front future Dec 2026",
      provider: "ibkr_cached",
      value: 100.05,
      timestamp: "2026-10-21T10:31:00",
      source_timestamp: "2026-10-21T10:31:00",
      contract_symbol: "CLZ6"
    };
    workspace.market_summaries[0] = { ...workspace.market_summaries[0], quote_basis: headline };
    workspace.price_reconciliations[0] = {
      ...workspace.price_reconciliations[0],
      status: "stale_reference",
      headline,
      summary: "WTI Crude Oil reference quotes are stale (FRED spot proxy 2026-10-14).",
      warnings: ["Stale commodity reference for WTI Crude Oil: headline 100.05 USD/bbl (2026-10-21) vs FRED spot proxy 101.91 USD/bbl (2026-10-14)."],
      stale_after_days: 4,
      comparisons: [
        {
          basis_id: "wti:history_latest",
          display_label: "FRED spot proxy",
          kind: "stale_reference",
          provider: "fred",
          value: 101.91,
          unit: "USD/bbl",
          observed_at: "2026-10-14T00:00:00",
          headline_value: 100.05,
          headline_unit: "USD/bbl",
          headline_observed_at: "2026-10-21T10:31:00",
          converted_value: 101.91,
          age_days: 7,
          difference: null,
          difference_pct: null,
          note: "Stale reference: quotes more than 4 days apart are not compared."
        }
      ]
    };

    const { body } = render(CommoditiesView, {
      props: { workspace, loading: false, mode: "energy", onLoadWorkspace: vi.fn() }
    });

    expect(body).toContain("Basis Reconciliation");
    expect(body).toContain("Stale reference");
    expect(body).toContain("FRED spot proxy");
    expect(body).toContain("2026-10-14");
    expect(body).toContain("7d");
    expect(body).not.toContain("Basis conflict");
  });

  it("makes cross-domain rows actionable when a handoff callback is wired (GUA-20261021-7)", () => {
    const workspace = makeWorkspace();
    workspace.mode = "events_cross_domain";
    workspace.cross_domain_links.push({
      ...workspace.cross_domain_links[0],
      link_id: "maritime-energy-chokepoints",
      target_domain: "maritime",
      target_label: "Sealanes Energy Chokepoints",
      relationship: "shipping_context",
      target_tab: "maritime",
      target_mode: "chokepoints",
      target_ids: {}
    });

    const wired = render(CommoditiesView, {
      props: {
        workspace,
        loading: false,
        mode: "events_cross_domain",
        onLoadWorkspace: vi.fn(),
        onCrossDomainHandoff: vi.fn()
      }
    }).body;
    expect(wired).toContain('aria-label="Open Sealanes Energy Chokepoints in maritime"');
    expect(wired).toContain('aria-label="Open Macro Inflation in macro"');
    expect(wired).toContain("clickable-row");

    const unwired = render(CommoditiesView, {
      props: { workspace, loading: false, mode: "events_cross_domain", onLoadWorkspace: vi.fn() }
    }).body;
    expect(unwired).not.toContain("clickable-row");
  });

  it("shows the requested instrument as loading instead of the previous market's basis", () => {
    const workspace = makeWorkspace();
    commoditiesRequestedInstrumentId.set("gold");
    try {
      const { body } = render(CommoditiesView, {
        props: { workspace, loading: true, mode: "overview", onLoadWorkspace: vi.fn() }
      });
      expect(body).toContain("Loading</em> Gold");
      expect(body).not.toContain("<em>Headline</em>");
    } finally {
      commoditiesRequestedInstrumentId.set(null);
    }
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
  const wtiBasis = {
    basis_id: "wti:history_latest",
    instrument_id: "wti",
    role: "history_latest",
    basis_type: "sample_generated",
    display_label: "Sample generated",
    provider: "sample_data",
    value: 79.2,
    previous_value: 78.8,
    change: 0.4,
    change_pct: 0.005,
    unit: "USD/bbl",
    timestamp: retrievedAt,
    source_timestamp: retrievedAt,
    previous_source_timestamp: "2026-04-18T00:00:00Z",
    contract_month: null,
    contract_symbol: null,
    provider_symbol: "CL",
    freshness_label: "mocked",
    warnings: ["Headline commodity quote is sample-generated fallback data."],
    source_provider: "sample_data",
    retrieved_at: retrievedAt,
    origin: "sample_commodities.price_history",
    transformation_note: "Synthetic offline price path."
  };
  const goldBasis = {
    ...wtiBasis,
    basis_id: "gold:history_latest",
    instrument_id: "gold",
    value: 2392,
    change: -3,
    change_pct: -0.001,
    unit: "USD/oz",
    provider_symbol: "GC"
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
        quote_basis: wtiBasis,
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
        quote_basis: goldBasis,
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
    price_reconciliations: [
      {
        instrument_id: "wti",
        status: "aligned",
        headline: wtiBasis,
        observations: [wtiBasis],
        summary: "WTI Crude Oil quote bases are aligned within the materiality threshold.",
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.price_reconciliation",
        transformation_note: "Gamma compares loaded quote references."
      },
      {
        instrument_id: "gold",
        status: "aligned",
        headline: goldBasis,
        observations: [goldBasis],
        summary: "Gold quote bases are aligned within the materiality threshold.",
        warnings: [],
        source_provider: "gamma",
        retrieved_at: retrievedAt,
        origin: "gamma.commodities.price_reconciliation",
        transformation_note: "Gamma compares loaded quote references."
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
        warnings: [],
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
        previous_as_of: "2026-04-19T00:00:00Z",
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
