import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CopilotWorkingAnalysis, FundamentalsDcfModel } from "../lib/api/types";
import FundamentalsView from "./FundamentalsView.svelte";

describe("FundamentalsView", () => {
  it("renders stale search state separately from company refresh state", () => {
    const { body } = render(FundamentalsView, {
      props: {
        search: {
          results: [
            {
              ticker: "AAPL",
              name: "Apple Inc.",
              cik: "0000320193",
              exchange: "Nasdaq",
              source_provider: "sec",
              retrieved_at: "2026-04-30T00:00:00Z",
              origin: "fixture",
              transformation_note: null
            }
          ]
        },
        selectedTicker: null,
        overview: null,
        financials: null,
        dcfModel: null,
        peers: null,
        reverseValuation: null,
        reference: null,
        dcfSnapshots: null,
        loading: false,
        searchState: {
          query: "MSFT",
          loading: true,
          refreshing: true,
          stale: true,
          error: null,
          requestedAt: "2026-06-15T10:00:00Z",
          completedAt: null
        },
        saving: false,
        onSearch: vi.fn(),
        onSelectCompany: vi.fn(),
        onSavePeerBasket: vi.fn(),
        onSaveDcfModel: vi.fn(),
        onSaveDcfSnapshot: vi.fn(),
        onLoadDcfSnapshot: vi.fn()
      }
    });

    expect(body).toContain("Search Refresh");
    expect(body).toContain("Stale results");
    expect(body).not.toContain("Refreshing</span><span");
  });

  it("renders DCF editable cells with visible affordances and descriptive labels", () => {
    const { body } = render(FundamentalsView, {
      props: {
        search: null,
        selectedTicker: "MSFT",
        overview: null,
        financials: null,
        dcfModel: makeDcfModel(),
        peers: null,
        reverseValuation: null,
        reference: null,
        dcfSnapshots: { snapshots: [] },
        loading: false,
        saving: false,
        mode: "dcf",
        onSearch: vi.fn(),
        onSelectCompany: vi.fn(),
        onSavePeerBasket: vi.fn(),
        onSaveDcfModel: vi.fn(),
        onSaveDcfSnapshot: vi.fn(),
        onLoadDcfSnapshot: vi.fn()
      }
    });

    expect(body).toMatch(/class="editable-input [^"]*"/);
    expect(body).toMatch(/class="sheet-cell sheet-cell-edit [^"]*"/);
    expect(body).toContain('aria-label="WACC (base scenario)"');
    expect(body).toContain('aria-label="Terminal growth (base scenario)"');
    expect(body).toContain('aria-label="Revenue growth 2026"');
    expect(body).toContain('aria-label="Revenue projection 2026"');
    expect(body).toContain('title="Editable DCF assumption: Revenue growth 2026"');
    expect(body).toContain('title="Editable DCF projection override: Revenue projection 2026"');
    expect(body).toMatch(/<button type="button"[^>]*disabled[^>]*>Recalculate \+ Save<\/button>/);
    expect(body).toContain("Sanity Checks");
    expect(body).toContain("Capex / Revenue");
    expect(body).toContain("Projected capex / revenue is low for a capital-intensive business.");
    expect(body).toMatch(/sens-heat-neg-strong[^"]*">\$100\.00<\/td>/);
    expect(body).toMatch(/sens-heat-neg[^"]*">\$400\.00<\/td>/);
    expect(body).not.toMatch(/sens-heat-pos[^"]*">\$400\.00<\/td>/);
    expect(body).toContain("Implied terminal EV / FCF");
    expect(body).toContain("PV terminal share of EV");
    expect(body).toContain("not a second valuation method");
  });

  it("explains when a focused instrument has no SEC company profile", () => {
    const { body } = render(FundamentalsView, {
      props: {
        focusedTicker: "XLE",
        search: { results: [{ ticker: "XEL", name: "Xcel Energy" }] },
        selectedTicker: null,
        overview: null,
        financials: null,
        dcfModel: null,
        peers: null,
        reverseValuation: null,
        reference: null,
        dcfSnapshots: null,
        searchState: {
          query: "XLE",
          loading: false,
          refreshing: false,
          stale: false,
          error: null,
          requestedAt: null,
          completedAt: "2026-07-13T00:00:00Z"
        },
        onSearch: vi.fn(),
        onSelectCompany: vi.fn(),
        onSavePeerBasket: vi.fn(),
        onSaveDcfModel: vi.fn(),
        onSaveDcfSnapshot: vi.fn(),
        onLoadDcfSnapshot: vi.fn()
      }
    });

    expect(body).toContain("XLE has no matching SEC company profile");
    expect(body).toContain("ETFs, funds, and unsupported non-US issuers");
  });

  it("labels materialized Copilot valuation state as temporary and unsaved", () => {
    const workingAnalysis: CopilotWorkingAnalysis = {
      analysis_id: "work_lmt",
      session_id: "session_lmt",
      run_id: "oprun_lmt",
      tool_id: "run_fundamentals_reverse_valuation",
      domain: "fundamentals",
      analysis_type: "reverse_valuation",
      title: "Lockheed Martin Corporation reverse valuation",
      status: "active",
      state_scope: "session_ephemeral",
      entity: { ticker: "LMT" },
      inputs: { ticker: "LMT" },
      outputs: {
        ticker: "LMT",
        current_price: 412.35,
        target_equity_value: 120_000_000_000
      },
      source_ids: [],
      warnings: [],
      context_fingerprint: "fp_lmt",
      owning_tab: "fundamentals",
      owning_mode: "reverse_valuation",
      materialization: { durable: false },
      created_at: "2026-08-25T10:00:00Z",
      updated_at: "2026-08-25T10:00:00Z",
      expires_at: "2026-09-01T10:00:00Z",
      materialized_at: "2026-08-25T10:01:00Z",
      discarded_at: null,
      read_only_safety: {},
      source_provider: "gamma",
      origin: "tests",
      transformation_note: null,
      contract_version: "copilot.working-analysis.v1"
    };
    const { body } = render(FundamentalsView, {
      props: {
        mode: "reverse_valuation",
        workingAnalysis,
        onSearch: vi.fn(),
        onSelectCompany: vi.fn(),
        onSavePeerBasket: vi.fn(),
        onSaveDcfModel: vi.fn(),
        onSaveDcfSnapshot: vi.fn(),
        onLoadDcfSnapshot: vi.fn()
      }
    });

    expect(body).toContain("Temporary working analysis");
    expect(body).toContain("Lockheed Martin Corporation reverse valuation");
    expect(body).toContain("Captured result");
    expect(body).toContain("$412.35 price");
    expect(body).toContain("$120.0B equity value");
    expect(body).toContain("opened from Copilot");
    expect(body).toContain("has not saved or changed a Fundamentals DCF model");
    expect(body).toContain("copilot.working-analysis.v1");
  });
});

function makeDcfModel(): FundamentalsDcfModel {
  return {
    ticker: "MSFT",
    company_name: "Microsoft Corp.",
    active_scenario_id: "base",
    historical_year_labels: ["FY 2024", "FY 2025"],
    projection_years: [2026, 2027],
    actual_rows: [
      {
        line_key: "revenue",
        label: "Revenue",
        unit: "currency",
        values: [245_000_000_000, 270_000_000_000],
        display_values: ["245,000,000,000", "270,000,000,000"],
        editable: false,
        overridden: [false, false],
        source_provider: "sec",
        retrieved_at: "2026-06-15T10:00:00Z",
        origin: "fundamentals.test.actuals",
        transformation_note: null
      }
    ],
    scenarios: [
      {
        scenario_id: "base",
        label: "base",
        assumptions: {
          revenue_growth_pct: [0.12, 0.1],
          wacc_pct: 0.09,
          terminal_growth_pct: 0.03
        },
        overrides: {},
        assumption_rows: [
          {
            line_key: "revenue_growth_pct",
            label: "Revenue growth",
            unit: "percent",
            values: [0.12, 0.1],
            display_values: ["12.0%", "10.0%"],
            editable: true,
            overridden: [false, false],
            source_provider: "manual",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.assumptions",
            transformation_note: null
          }
        ],
        projection_rows: [
          {
            line_key: "revenue",
            label: "Revenue",
            unit: "currency",
            values: [302_400_000_000, 332_640_000_000],
            display_values: ["302,400,000,000", "332,640,000,000"],
            editable: true,
            overridden: [false, false],
            source_provider: "manual",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.projection",
            transformation_note: null
          }
        ],
        cost_of_capital_rows: [],
        valuation_bridge_rows: [],
        sanity_checks: [
          {
            check_id: "capex_revenue",
            label: "Capex / Revenue",
            severity: "warning",
            value: 0.025,
            display_value: "2.5%",
            benchmark: "Historical capex/revenue 4.1%",
            message: "Projected capex / revenue is low for a capital-intensive business.",
            source_provider: "gamma",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.sanity",
            transformation_note: null
          }
        ],
        summary: {
          scenario_id: "base",
          label: "base",
          enterprise_value: 4_000_000_000_000,
          equity_value: 4_050_000_000_000,
          implied_value_per_share: 540,
          implied_value_low: 500,
          implied_value_high: 580,
          upside_downside_pct: 0.12,
          terminal_value: 5_000_000_000_000,
          discounted_terminal_value: 3_500_000_000_000,
          discounted_cash_flow_value: 500_000_000_000,
          current_price: 480,
          source_provider: "gamma",
          retrieved_at: "2026-06-15T10:00:00Z",
          origin: "fundamentals.test.summary",
          transformation_note: null
        },
        source_provider: "manual",
        retrieved_at: "2026-06-15T10:00:00Z",
        origin: "fundamentals.test.scenario",
        transformation_note: null
      }
    ],
    sensitivity_matrix: {
      wacc_values: [0.08, 0.09, 0.1],
      terminal_growth_values: [0.025],
      rows: [
        [
          {
            wacc_pct: 0.08,
            terminal_growth_pct: 0.025,
            implied_value_per_share: 100,
            source_provider: "gamma",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.sensitivity",
            transformation_note: null
          },
          {
            wacc_pct: 0.09,
            terminal_growth_pct: 0.025,
            implied_value_per_share: 300,
            source_provider: "gamma",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.sensitivity",
            transformation_note: null
          },
          {
            wacc_pct: 0.1,
            terminal_growth_pct: 0.025,
            implied_value_per_share: 400,
            source_provider: "gamma",
            retrieved_at: "2026-06-15T10:00:00Z",
            origin: "fundamentals.test.sensitivity",
            transformation_note: null
          }
        ]
      ],
      source_provider: "gamma",
      retrieved_at: "2026-06-15T10:00:00Z",
      origin: "fundamentals.test.sensitivity",
      transformation_note: "Test DCF sensitivity matrix."
    },
    warnings: [],
    source_provider: "gamma",
    retrieved_at: "2026-06-15T10:00:00Z",
    origin: "fundamentals.test.dcf",
    transformation_note: "Test DCF model."
  };
}
