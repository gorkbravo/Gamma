import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaSignal, IdeaTrackingResponse, IdeaValidationSnapshot } from "../lib/api/types";
import {
  buildImportPayload,
  buildScriptPayload,
  cashShare,
  currentSignal,
  formatShare,
  guessDateColumn,
  importColumns,
  legCost,
  parseInstrumentMap,
  sourceIdRows,
  trialsTag,
  trialsText,
  validationCostText,
  validationSplitText,
} from "../lib/idea-signals";
import { changedLegBp, legBpDraftError, legBpText } from "../lib/idea-tracking";
import IdeaSignalPanel from "./IdeaSignalPanel.svelte";

const entity = (label: string, id: string) => ({ entity_type: "equity", label, normalized_id: id, provider_id: null, native_id: null, metadata: {} });

const VALIDATION: IdeaValidationSnapshot = {
  kind: "walk_forward",
  snapshot_id: "v1",
  created_at: "2026-11-10T14:00:01",
  sweep_id: "sweep123456",
  definition_sha256: "d",
  report_sha256: "r",
  target: "weight_book",
  result_id: null,
  execution_lag: 1,
  cost_bps: 5,
  costs_included: true,
  trials: 6,
  train_observations: 60,
  test_observations: 30,
  window: "anchored",
  selection_metric: "sharpe",
  window_start: "2026-01-05",
  window_end: "2026-08-13",
  observations: 158,
  folds: [
    { fold: 1, train_start: "2026-01-05", train_end: "2026-03-30", test_start: "2026-03-31", test_end: "2026-05-11", test_observations: 30, selected_point: 2, test_return: 0.031, partial: false },
    { fold: 2, train_start: "2026-01-05", train_end: "2026-05-11", test_start: "2026-05-12", test_end: "2026-06-22", test_observations: 30, selected_point: 4, test_return: -0.012, partial: false },
  ],
  out_of_sample: { total_return: 0.0183, annual_return: 0.077, annual_volatility: 0.14, sharpe_ratio: 0.61, max_drawdown: -0.044, observations: 60 },
  oos_start: "2026-03-31",
  oos_end: "2026-06-22",
  oos_curve: [["2026-03-31", 0.004], ["2026-06-22", 0.0183]],
  in_sample_value: 1.9,
  in_sample_point: 4,
  in_sample_label: "Descriptive only; the maximum of 6 trials is biased upward and is not a validation result.",
  distinct_selections: 2,
  causality_verified: true,
  warnings: [],
  provenance: { source_provider: "gamma_script_analytics", retrieved_at: "2026-11-10T14:00:01", origin: "script_experiments.walk_forward", transformation_note: null },
};

const SIGNAL: IdeaSignal = {
  signal_id: "s1",
  idea_id: "i1",
  attached_at: "2026-11-10T14:00:01",
  source: "script",
  output_kind: "weights",
  label: "Momentum · run abcd1234",
  source_ref: { script_id: "script1", script_title: "Momentum", revision_id: "rev1", revision_number: 3, revision_status: "accepted", parameters_sha256: "f00dfacecafe1234", run_id: "abcd1234run", sweep_id: null },
  as_of: "2026-08-13",
  legs: [
    { entity: entity("Apple", "AAPL"), weight: 0.6, instrument_id: "research:aapl", units: null, price: null, price_date: null, key: "equity:AAPL" },
    { entity: entity("Microsoft", "MSFT"), weight: -0.2, instrument_id: "research:msft", units: null, price: null, price_date: null, key: "equity:MSFT" },
  ],
  supplied: null,
  validation: VALIDATION,
  trial_count: 7,
  trial_count_lower_bound: false,
  detached_at: null,
  warnings: [],
  provenance: { source_provider: "gamma_script_analytics", retrieved_at: "2026-11-09T20:00:00", origin: "idea_signals.script", transformation_note: null },
  current: true,
  drives_tracking: true,
};

const IDEA: Idea = {
  schema_version: 6,
  idea_id: "i1",
  title: "Quant book",
  thesis: "Momentum on two megacaps.",
  notes: "",
  stance: "long",
  legs: [
    { entity: entity("Apple", "AAPL"), weight: 0.6 },
    { entity: entity("Microsoft", "MSFT"), weight: -0.2 },
  ],
  horizon: { review_date: null, holding_window: null },
  status: "active",
  origin: { kind: "manual", source_ref: null, label: null, handoff: null },
  tags: [],
  created_at: "2026-11-06T12:00:00",
  updated_at: "2026-11-10T14:00:01",
  closed_at: null,
  evidence: [],
  criteria: [],
  journal: [],
  evidence_counts: { supports: 0, challenges: 0, context: 0 },
  criteria_counts: { pending: 0, holding: 0, triggered: 0, unavailable: 0, stale: 0 },
  tracking: null,
  signals: [SIGNAL],
  current_signal_id: "s1",
  trials: [],
  trial_count: 7,
  trials_lower_bound: false,
  provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-10T14:00:01", origin: "idea_store", transformation_note: null },
};

const TRACKING = {
  segments: [
    { legs: [{ key: "equity:AAPL", cost_bp: 25, cost_source: "leg", asset_class: "us_equity_liquid" }, { key: "equity:MSFT", cost_bp: 5, cost_source: "class", asset_class: "us_equity_liquid" }] },
  ],
} as unknown as IdeaTrackingResponse;

describe("idea signal helpers", () => {
  it("counts trials, formats shares and reads the current signal", () => {
    expect(trialsText(1)).toBe("1 trial");
    expect(trialsText(4, true)).toBe("at least 4 trials");
    expect(trialsText(null)).toBe("Trials not recorded");
    expect(trialsTag(7)).toBe("Trials 7");
    expect(trialsTag(4, true)).toBe("Trials ≥ 4");
    expect(trialsTag(undefined)).toBe("Trials N/A");
    expect(formatShare(0.6)).toBe("+60.0%");
    expect(formatShare(-0.2)).toBe("-20.0%");
    expect(cashShare(SIGNAL)).toBeCloseTo(0.6);
    expect(cashShare({ ...SIGNAL, output_kind: "positions" })).toBeNull();
    expect(currentSignal(IDEA)?.signal_id).toBe("s1");
    expect(currentSignal({ ...IDEA, signals: [{ ...SIGNAL, current: false }] })).toBeNull();
  });

  it("lists the ids that pin the source and the validation's split and costs", () => {
    expect(sourceIdRows(SIGNAL)).toEqual([
      ["Script", "Momentum"],
      ["Revision", "3 (accepted)"],
      ["Parameters", "f00dfacecafe"],
      ["Run", "abcd1234run"],
    ]);
    const imported = { ...SIGNAL, source: "import" as const, source_ref: { content_sha256: "0123456789abcdef", rows: 2, columns: ["AAPL", "MSFT"] } };
    expect(sourceIdRows(imported)).toEqual([["Content", "0123456789ab"], ["Rows", "2"], ["Columns", "AAPL, MSFT"]]);
    expect(validationSplitText(VALIDATION)).toBe("Walk-forward · 2 folds · anchored · train 60 / test 30");
    expect(validationCostText(VALIDATION)).toBe("Costs 5 bp per unit of turnover");
    expect(validationCostText({ ...VALIDATION, costs_included: false })).toBe("No costs");
    expect(validationCostText({ ...VALIDATION, costs_included: null })).toBe("Costs as written by the script");
    expect(legCost(TRACKING, "equity:AAPL")).toEqual({ bp: 25, source: "leg", assetClass: "us_equity_liquid" });
    expect(legCost(null, "equity:AAPL").bp).toBeNull();
  });

  it("builds an import from pasted CSV with the Strategy Lab parser", () => {
    const csv = "date,AAPL,BTC\n2026-01-09,0.6,0.2";
    const columns = importColumns({ csv, dateColumn: "date" });
    expect(columns.instrumentColumns).toEqual(["AAPL", "BTC"]);
    expect(guessDateColumn(["Symbol", "Trade date"])).toBe("Trade date");
    const built = buildImportPayload({
      outputKind: "weights", csv, dateColumn: "date", valueColumn: "", valueKind: "return", label: "",
      instruments: { BTC: { symbol: "bitcoin", entity_type: "crypto" } },
    });
    expect(built.payload).toEqual({
      source: "import", output_kind: "weights", label: null, rows: [{ date: "2026-01-09", AAPL: "0.6", BTC: "0.2" }],
      date_column: "date", columns: ["AAPL", "BTC"],
      instruments: { AAPL: { symbol: "AAPL", entity_type: "equity" }, BTC: { symbol: "bitcoin", entity_type: "crypto" } },
    });
    expect(buildImportPayload({ outputKind: "weights", csv: "", dateColumn: "", valueColumn: "", valueKind: "return", label: "", instruments: {} }).reason).toBe("Paste CSV rows with a header");
    const returns = buildImportPayload({ outputKind: "returns", csv: "date,ret\n2026-01-09,0.1%", dateColumn: "date", valueColumn: "ret", valueKind: "return", label: "", instruments: {} });
    expect(returns.payload?.value_column).toBe("ret");
  });

  it("builds a Script attach with an instrument map and an optional walk-forward", () => {
    expect(parseInstrumentMap("research:asset = SPY etf\nresearch:btc = bitcoin crypto")).toEqual({
      instruments: { "research:asset": { symbol: "SPY", entity_type: "etf" }, "research:btc": { symbol: "bitcoin", entity_type: "crypto" } },
      errors: [],
    });
    expect(parseInstrumentMap("nonsense").errors[0]).toContain("Line 1");
    const draft = { outputKind: "weights" as const, runId: "", resultId: "", label: "", instrumentMap: "", sweepId: "", trainObservations: "", testObservations: "", window: "anchored" as const };
    expect(buildScriptPayload(draft).reason).toBe("Paste the run id from Strategy Lab");
    expect(buildScriptPayload({ ...draft, runId: "r1", sweepId: "s1" }).reason).toContain("train and test");
    expect(buildScriptPayload({ ...draft, runId: "r1", sweepId: "s1", trainObservations: "60", testObservations: "30" }).payload?.validation).toEqual({
      sweep_id: "s1", train_observations: 60, test_observations: 30, window: "anchored",
    });
  });

  it("edits per-leg costs: blank is the class cost and only changes are sent", () => {
    expect(legBpText(undefined)).toBe("");
    expect(legBpText(12.5)).toBe("12.5");
    expect(legBpDraftError({ a: "", b: "20" })).toBe("");
    expect(legBpDraftError({ a: "900" })).toContain("0 to 500");
    expect(changedLegBp({ "equity:AAPL": 25 }, { "equity:AAPL": "25", "equity:MSFT": "" })).toBeNull();
    expect(changedLegBp({ "equity:AAPL": 25 }, { "equity:AAPL": "", "equity:MSFT": "0" })).toEqual({ "equity:AAPL": null, "equity:MSFT": 0 });
  });
});

describe("IdeaSignalPanel", () => {
  it("is collapsed by default and still shows the signal and its trial count in the title", () => {
    const { body } = render(IdeaSignalPanel, { props: { idea: IDEA } });
    expect(body).toContain("Signal and validation");
    expect(body).toContain('aria-expanded="false"');
    const text = body.replace(/<!--[^>]*-->/g, "");
    expect(text).toContain("Momentum · run abcd1234 · Weights · out-of-sample +1.83%");
    expect(body).toContain("Trials 7");
    expect(body).not.toContain("Out-of-sample validation");
  });

  it("shows the frozen book, its costs, the validation and the labels when expanded", () => {
    const { body } = render(IdeaSignalPanel, { props: { idea: IDEA, tracking: TRACKING, expanded: true } });
    expect(body).toContain("Drives tracking");
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("Weight of NAV");
    expect(body).toContain("+60.0%");
    expect(body).toContain("Cash at 0%");
    expect(body).toContain("25 bp · edited");
    expect(body).toContain("Out-of-sample validation");
    expect(body).toContain("Costs 5 bp per unit of turnover");
    expect(body).toContain("6 sweep trials");
    expect(body).toContain("biased upward, not validation");
    expect(body).toContain("2026-03-31 → 2026-05-11");
    expect(body).toContain("7 trials");
  });

  it("labels a returns signal as validation only and an idea without a signal as empty", () => {
    const supplied = {
      label: "Supplied series, not rebuilt by Gamma", window_start: "2026-10-01", window_end: "2026-10-30", observations: 30,
      metrics: { total_return: 0.01, annual_return: 0.08, sharpe_ratio: 0.4, max_drawdown: -0.02 }, curve: [["2026-10-01", 0.001], ["2026-10-30", 0.01]] as Array<[string, number]>,
      warnings: [], drives_tracking: false as const,
    };
    const returnsIdea = { ...IDEA, signals: [{ ...SIGNAL, output_kind: "returns" as const, legs: [], supplied, validation: null, drives_tracking: false }] };
    const { body } = render(IdeaSignalPanel, { props: { idea: returnsIdea, expanded: true } });
    expect(body).toContain("Validation only");
    expect(body).toContain("Supplied series, not rebuilt by Gamma");
    expect(body).toContain("No out-of-sample validation.");
    const empty = render(IdeaSignalPanel, { props: { idea: { ...IDEA, signals: [], trial_count: 0 }, expanded: true } }).body;
    expect(empty).toContain("No signal. Attach a Script run or CSV rows");
    expect(empty).not.toContain("Trials 0");
  });
});
