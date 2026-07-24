import "../lib/theme/tokens.css";
import { mount } from "svelte";
import FundamentalsView from "../views/FundamentalsView.svelte";
import type { FundamentalsDcfModel, FundamentalsDcfSnapshotList } from "../lib/api/types";
import type { FundamentalsDcfSavePayload } from "../lib/stores/app";

declare global {
  interface Window {
    __gammaDcfSaves: Array<{ ticker: string; payload: FundamentalsDcfSavePayload }>;
    __gammaDcfSnapshotLoads: Array<{ ticker: string; snapshotId: string }>;
    __gammaFundamentalsSelections: string[];
  }
}

window.__gammaDcfSaves = [];
window.__gammaDcfSnapshotLoads = [];
window.__gammaFundamentalsSelections = [];

mount(FundamentalsView, {
  target: document.getElementById("app")!,
  props: {
    search: {
      results: [
        {
          ticker: "MSFT",
          name: "MICROSOFT CORP",
          cik: "0000789019",
          exchange: "Nasdaq",
          source_provider: "sec",
          retrieved_at: "2026-06-15T10:00:00Z",
          origin: "playwright.fundamentals.dcf",
          transformation_note: "MSFT-style DCF edit-flow fixture."
        },
        {
          ticker: "AAPL",
          name: "APPLE INC",
          cik: "0000320193",
          exchange: "Nasdaq",
          source_provider: "sec",
          retrieved_at: "2026-06-15T10:00:00Z",
          origin: "playwright.fundamentals.search",
          transformation_note: "Search interaction fixture."
        }
      ]
    },
    selectedTicker: "MSFT",
    overview: null,
    financials: null,
    dcfModel: makeMsftDcfModel(),
    peers: null,
    reverseValuation: null,
    reference: null,
    dcfSnapshots: makeDcfSnapshots(),
    loading: false,
    saving: false,
    mode: "dcf",
    onSearch: () => {},
    onSelectCompany: async (ticker: string) => {
      window.__gammaFundamentalsSelections.push(ticker);
    },
    onSavePeerBasket: () => {},
    onSaveDcfModel: async (ticker: string, payload: FundamentalsDcfSavePayload) => {
      window.__gammaDcfSaves.push({ ticker, payload });
    },
    onSaveDcfSnapshot: () => {},
    onLoadDcfSnapshot: async (ticker: string, snapshotId: string) => {
      window.__gammaDcfSnapshotLoads.push({ ticker, snapshotId });
    }
  }
});

function makeMsftDcfModel(): FundamentalsDcfModel {
  const retrievedAt = "2026-06-15T10:00:00Z";
  return {
    ticker: "MSFT",
    company_name: "MICROSOFT CORP",
    active_scenario_id: "base",
    historical_year_labels: ["FY 2024", "FY 2025"],
    projection_years: [2026, 2027, 2028],
    actual_rows: [
      {
        line_key: "revenue",
        label: "Revenue",
        unit: "currency",
        values: [245_122_000_000, 270_011_000_000],
        display_values: ["245,122,000,000", "270,011,000,000"],
        editable: false,
        overridden: [false, false],
        source_provider: "sec",
        retrieved_at: retrievedAt,
        origin: "playwright.fundamentals.dcf.actuals",
        transformation_note: null
      }
    ],
    scenarios: ["bear", "base", "bull"].map((id, scenarioIndex) => {
      const growth = id === "bear" ? [0.08, 0.07, 0.06] : id === "bull" ? [0.15, 0.13, 0.11] : [0.12, 0.1, 0.09];
      const wacc = id === "bear" ? 0.095 : id === "bull" ? 0.083 : 0.09;
      const terminalGrowth = id === "bear" ? 0.025 : id === "bull" ? 0.035 : 0.03;
      return {
        scenario_id: id,
        label: id,
        assumptions: {
          revenue_growth_pct: growth,
          ebit_margin_pct: [0.43, 0.44, 0.45],
          wacc_pct: wacc,
          terminal_growth_pct: terminalGrowth
        },
        overrides: {},
        assumption_rows: [
          {
            line_key: "revenue_growth_pct",
            label: "Revenue growth",
            unit: "percent",
            values: growth,
            display_values: growth.map((value) => `${(value * 100).toFixed(1)}%`),
            editable: true,
            overridden: [false, false, false],
            source_provider: "manual",
            retrieved_at: retrievedAt,
            origin: "playwright.fundamentals.dcf.assumptions",
            transformation_note: null
          },
          {
            line_key: "ebit_margin_pct",
            label: "EBIT margin",
            unit: "percent",
            values: [0.43, 0.44, 0.45],
            display_values: ["43.0%", "44.0%", "45.0%"],
            editable: true,
            overridden: [false, false, false],
            source_provider: "manual",
            retrieved_at: retrievedAt,
            origin: "playwright.fundamentals.dcf.assumptions",
            transformation_note: null
          }
        ],
        projection_rows: [
          {
            line_key: "revenue",
            label: "Revenue",
            unit: "currency",
            values: [302_412_320_000, 332_653_552_000, 362_592_371_680],
            display_values: ["302,412,320,000", "332,653,552,000", "362,592,371,680"],
            editable: true,
            overridden: [false, false, false],
            source_provider: "manual",
            retrieved_at: retrievedAt,
            origin: "playwright.fundamentals.dcf.projection",
            transformation_note: null
          }
        ],
        cost_of_capital_rows: [],
        valuation_bridge_rows: [],
        sanity_checks: [],
        summary: {
          scenario_id: id,
          label: id,
          enterprise_value: 3_800_000_000_000 + scenarioIndex * 150_000_000_000,
          equity_value: 3_900_000_000_000 + scenarioIndex * 160_000_000_000,
          implied_value_per_share: 520 + scenarioIndex * 25,
          implied_value_low: 480 + scenarioIndex * 20,
          implied_value_high: 560 + scenarioIndex * 30,
          upside_downside_pct: 0.08 + scenarioIndex * 0.04,
          terminal_value: 5_000_000_000_000,
          discounted_terminal_value: 3_400_000_000_000,
          discounted_cash_flow_value: 500_000_000_000,
          current_price: 480,
          source_provider: "gamma",
          retrieved_at: retrievedAt,
          origin: "playwright.fundamentals.dcf.summary",
          transformation_note: null
        },
        source_provider: "manual",
        retrieved_at: retrievedAt,
        origin: "playwright.fundamentals.dcf.scenario",
        transformation_note: null
      };
    }),
    sensitivity_matrix: null,
    warnings: [],
    source_provider: "gamma",
    retrieved_at: retrievedAt,
    origin: "playwright.fundamentals.dcf",
    transformation_note: "Browser-level MSFT-style DCF edit-flow fixture."
  };
}

function makeDcfSnapshots(): FundamentalsDcfSnapshotList {
  return {
    snapshots: [
      {
        snapshot_id: "msft-base-before-edit",
        ticker: "MSFT",
        name: "MSFT base before edit",
        created_at: "2026-06-15T10:05:00Z",
        active_scenario_id: "base",
        projection_years: [2026, 2027, 2028],
        scenario_summaries: [
          {
            scenario_id: "base",
            label: "base",
            enterprise_value: 3_950_000_000_000,
            equity_value: 4_060_000_000_000,
            implied_value_per_share: 545,
            implied_value_low: 505,
            implied_value_high: 585,
            upside_downside_pct: 0.12,
            terminal_value: 5_000_000_000_000,
            discounted_terminal_value: 3_500_000_000_000,
            discounted_cash_flow_value: 560_000_000_000,
            current_price: 480,
            source_provider: "gamma",
            retrieved_at: "2026-06-15T10:05:00Z",
            origin: "playwright.fundamentals.dcf.snapshot",
            transformation_note: null
          }
        ],
        source_provider: "local",
        retrieved_at: "2026-06-15T10:05:00Z",
        origin: "playwright.fundamentals.dcf.snapshot",
        transformation_note: null
      }
    ]
  };
}
