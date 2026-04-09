import { describe, expect, it } from "vitest";
import type {
  FundamentalsDcfModel,
  FundamentalsFinancials,
  FundamentalsStatementView
} from "../api/types";
import {
  buildDcfSavePayload,
  createDcfDraft,
  findDcfScenario,
  normalizePeerTickers,
  parseEditableNumber,
  setDraftActiveScenario,
  statementViewForSelection,
  updateDraftOverride,
  updateDraftScalarAssumption,
  updateDraftAssumptionSeriesValue
} from "./fundamentals";

describe("fundamentals view-model helpers", () => {
  it("selects the requested statement view", () => {
    const financials = makeFinancials();

    expect(statementViewForSelection(financials, "annual", "income")?.statement).toBe("income");
    expect(statementViewForSelection(financials, "annual", "ratios")?.statement).toBe("ratios");
    expect(statementViewForSelection(financials, "quarterly", "cashflow")?.basis).toBe("quarterly");
  });

  it("creates and updates a DCF draft without mutating the source model", () => {
    const model = makeDcfModel();
    const draft = createDcfDraft(model);
    const withScenario = setDraftActiveScenario(draft, "bull");
    const withSeries = updateDraftAssumptionSeriesValue(withScenario, "bull", "revenue_growth_pct", 1, 0.08);
    const withScalar = updateDraftScalarAssumption(withSeries, "bull", "wacc_pct", 0.095);
    const withOverride = updateDraftOverride(withScalar, "bull", "revenue", 2, 155_000_000_000);
    const payload = buildDcfSavePayload(withOverride);

    expect(findDcfScenario(model, "bull")?.scenario_id).toBe("bull");
    expect(payload.activeScenarioId).toBe("bull");
    expect(payload.scenarios.bull.assumptions.wacc_pct).toBe(0.095);
    expect((payload.scenarios.bull.assumptions.revenue_growth_pct as number[])[1]).toBe(0.08);
    expect(payload.scenarios.bull.overrides.revenue[2]).toBe(155_000_000_000);
    expect((model.scenarios[2].assumptions.revenue_growth_pct as number[])[1]).toBe(0.06);
  });

  it("drops empty override rows and normalizes peer tickers", () => {
    const draft = updateDraftOverride(createDcfDraft(makeDcfModel()), "base", "ebit", 0, 12_000_000_000);
    const cleared = updateDraftOverride(draft, "base", "ebit", 0, null);

    expect(buildDcfSavePayload(cleared).scenarios.base.overrides.ebit).toBeUndefined();
    expect(normalizePeerTickers("aapl", [" msft ", "GOOGL", "AAPL", "MSFT"])).toEqual(["MSFT", "GOOGL"]);
  });

  it("parses editable numeric input conservatively", () => {
    expect(parseEditableNumber(" 1,250.5 ")).toBe(1250.5);
    expect(parseEditableNumber("")).toBeNull();
    expect(parseEditableNumber("abc")).toBeNull();
  });
});

function makeStatementView(statement: string, basis: "annual" | "quarterly"): FundamentalsStatementView {
  return {
    statement,
    basis,
    periods: [],
    lines: [],
    source_provider: "sec",
    retrieved_at: "2026-04-09T10:00:00Z",
    origin: `fundamentals.test.${statement}.${basis}`,
    transformation_note: null
  };
}

function makeFinancials(): FundamentalsFinancials {
  return {
    company: {
      ticker: "AAPL",
      cik: "0000320193",
      name: "Apple Inc.",
      exchange: "Nasdaq",
      sic: null,
      sic_description: "Electronic Computers",
      filer_category: "Large accelerated filer",
      fiscal_year_end: "0928",
      state_of_incorporation: "CA",
      phone: null,
      website: null,
      investor_website: null,
      description: "Apple description.",
      latest_report_period: "2025-09-28T00:00:00Z",
      latest_filing_date: "2025-11-01T00:00:00Z",
      classification_labels: ["Electronic Computers"],
      source_provider: "sec",
      retrieved_at: "2026-04-09T10:00:00Z",
      origin: "fundamentals.sec.submissions",
      transformation_note: null
    },
    annual_income_statement: makeStatementView("income", "annual"),
    annual_balance_sheet: makeStatementView("balance", "annual"),
    annual_cash_flow_statement: makeStatementView("cashflow", "annual"),
    quarterly_income_statement: makeStatementView("income", "quarterly"),
    quarterly_balance_sheet: makeStatementView("balance", "quarterly"),
    quarterly_cash_flow_statement: makeStatementView("cashflow", "quarterly"),
    annual_ratio_view: makeStatementView("ratios", "annual"),
    quarterly_ratio_view: makeStatementView("ratios", "quarterly"),
    filings: [],
    warnings: []
  };
}

function makeDcfModel(): FundamentalsDcfModel {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    active_scenario_id: "base",
    historical_year_labels: ["FY 2022", "FY 2023", "FY 2024"],
    projection_years: [2026, 2027, 2028],
    actual_rows: [],
    scenarios: [
      makeScenario("bear", 0.02, 0.11),
      makeScenario("base", 0.04, 0.1),
      makeScenario("bull", 0.06, 0.09)
    ],
    sensitivity_matrix: null,
    warnings: [],
    source_provider: "manual",
    retrieved_at: "2026-04-09T10:00:00Z",
    origin: "fundamentals.dcf.compute",
    transformation_note: "Gamma derived DCF model."
  };
}

function makeScenario(scenarioId: string, growth: number, wacc: number) {
  return {
    scenario_id: scenarioId,
    label: scenarioId,
    assumptions: {
      revenue_growth_pct: [growth, growth, growth],
      ebit_margin_pct: [0.3, 0.3, 0.3],
      tax_rate_pct: [0.21, 0.21, 0.21],
      da_pct_revenue: [0.03, 0.03, 0.03],
      capex_pct_revenue: [0.03, 0.03, 0.03],
      nwc_pct_incremental_revenue: [0.01, 0.01, 0.01],
      shares_outstanding: [15_500_000_000, 15_450_000_000, 15_400_000_000],
      wacc_pct: wacc,
      terminal_growth_pct: 0.025
    },
    overrides: {},
    assumption_rows: [],
    projection_rows: [],
    summary: null,
    source_provider: "manual",
    retrieved_at: "2026-04-09T10:00:00Z",
    origin: `fundamentals.dcf.${scenarioId}`,
    transformation_note: "Gamma stores scenario assumptions."
  };
}
