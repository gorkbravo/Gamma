import { describe, expect, it } from "vitest";
import type {
  FundamentalsDcfModel,
  FundamentalsFinancials,
  FundamentalsReference,
  FundamentalsReverseValuationDriver,
  FundamentalsStatementView
} from "../api/types";
import {
  buildDcfSavePayload,
  createDcfDraft,
  dcfDecisionGateFromWarnings,
  driverTone,
  findDcfScenario,
  fundamentalsModes,
  normalizePeerTickers,
  parseEditableNumber,
  setDraftActiveScenario,
  snapshotDisplayName,
  statementViewForSelection,
  sourceTracesForStatement,
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
    expect(parseEditableNumber("(1,234.50)")).toBe(-1234.5);
    expect(parseEditableNumber("(0)")).toBe(-0);
    expect(parseEditableNumber("")).toBeNull();
    expect(parseEditableNumber("abc")).toBeNull();
    expect(parseEditableNumber("(abc)")).toBeNull();
  });

  it("registers the V2 mode order", () => {
    expect(fundamentalsModes.map((mode) => mode.id)).toEqual([
      "overview",
      "financials",
      "peers",
      "dcf",
      "reverse_valuation",
      "reference"
    ]);
  });

  it("gates DCF decision outputs when required filings lines are missing", () => {
    const gate = dcfDecisionGateFromWarnings([
      "Quarterly SEC company-facts statements are unavailable or not mapped for this ticker; quarterly views may be empty while annual statements remain usable.",
      "SEC company facts did not provide a mapped annual revenue line in the retained periods.",
      "SEC company facts did not provide a mapped capital expenditures line; free-cash-flow and DCF values that depend on capex may be incomplete.",
      "SEC company facts did not provide a mapped annual revenue line in the retained periods."
    ]);

    expect(gate.blocked).toBe(true);
    expect(gate.reasons).toEqual([
      "SEC company facts did not provide a mapped annual revenue line in the retained periods.",
      "SEC company facts did not provide a mapped capital expenditures line; free-cash-flow and DCF values that depend on capex may be incomplete."
    ]);
  });

  it("filters source traces for the active financial statement", () => {
    const reference = makeReference();

    expect(sourceTracesForStatement(reference, "annual", "income")).toHaveLength(1);
    expect(sourceTracesForStatement(reference, "quarterly", "income")).toHaveLength(0);
  });

  it("labels snapshots and reverse valuation driver tone", () => {
    const driver = {
      driver_id: "implied_revenue_cagr",
      label: "Implied revenue CAGR",
      implied_value: 0.08,
      display_value: "8.0%",
      base_value: 0.05,
      base_display_value: "5.0%",
      gap_to_base: 0.03,
      gap_display_value: "+3.0 pts",
      target_enterprise_value: 100,
      solved_enterprise_value: 100,
      success: true,
      warnings: [],
      source_provider: "gamma",
      retrieved_at: "2026-04-09T10:00:00Z",
      origin: "fundamentals.reverse.test",
      transformation_note: "Gamma solved a bounded reverse valuation driver."
    } satisfies FundamentalsReverseValuationDriver;

    expect(driverTone(driver)).toBe("warning");
    expect(snapshotDisplayName("Base case", "2026-04-09T10:00:00Z")).toBe("Base case");
    expect(snapshotDisplayName("", "2026-04-09T10:00:00Z")).toContain("Snapshot");
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

function makeReference(): FundamentalsReference {
  return {
    company: makeFinancials().company,
    filings: [],
    inspection: {
      company: makeFinancials().company,
      traces: [
        {
          statement: "income",
          basis: "annual",
          line_key: "revenue",
          line_label: "Revenue",
          period_key: "FY-2025",
          period_label: "FY 2025",
          normalized_value: 391_000_000_000,
          display_value: "$391.0B",
          unit: "usd",
          concept_name: "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
          accession_number: "0000320193-25-000079",
          filing_form: "10-K",
          fiscal_year: 2025,
          fiscal_period: "FY",
          filing_date: "2025-10-31T00:00:00Z",
          report_period: "2025-09-27T00:00:00Z",
          is_amendment: false,
          source_provider: "sec",
          retrieved_at: "2026-04-09T10:00:00Z",
          origin: "fundamentals.trace.test",
          transformation_note: "Normalized source trace for test."
        }
      ],
      coverage: [],
      warnings: [],
      source_provider: "gamma",
      retrieved_at: "2026-04-09T10:00:00Z",
      origin: "fundamentals.reference.test",
      transformation_note: "Raw-versus-normalized inspection test payload."
    },
    provider_warnings: [],
    warnings: [],
    source_provider: "sec",
    retrieved_at: "2026-04-09T10:00:00Z",
    origin: "fundamentals.reference.test",
    transformation_note: "Reference test payload."
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
    cost_of_capital_rows: [],
    valuation_bridge_rows: [],
    sanity_checks: [],
    summary: null,
    source_provider: "manual",
    retrieved_at: "2026-04-09T10:00:00Z",
    origin: `fundamentals.dcf.${scenarioId}`,
    transformation_note: "Gamma stores scenario assumptions."
  };
}
