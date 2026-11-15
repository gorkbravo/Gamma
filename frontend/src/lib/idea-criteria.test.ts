import { describe, expect, it } from "vitest";
import type { IdeaNotification, IdeaObservableDefinition } from "./api/types";
import {
  criteriaSummary,
  criterionStateTone,
  daysToReview,
  daysToReviewText,
  defaultObservableLabel,
  describeCriterion,
  formatObservableValue,
  groupObservables,
  notificationDetail,
  observableChangeUnit,
  observableValueUnit,
  paramsComplete,
} from "./idea-criteria";

function definition(overrides: Partial<IdeaObservableDefinition>): IdeaObservableDefinition {
  return {
    observable_id: "equity_close",
    label: "Equity or ETF close",
    group: "Markets",
    source: "Research market data",
    params: [{ name: "symbol", label: "Ticker", kind: "ticker", required: true, placeholder: "XOM", options: [] }],
    conditions: ["above", "below"],
    cadences: ["on_open", "daily_close", "intraday"],
    change_unit: "percent",
    value_unit: "price",
    needs_tws: false,
    needs_keys: [],
    intraday_capable: false,
    available: true,
    unavailable_reason: null,
    dependency_label: null,
    order: 10,
    ...overrides,
  };
}

const MACRO = definition({
  observable_id: "macro_series",
  label: "Macro series",
  group: "Macro",
  params: [
    {
      name: "series_id",
      label: "Series",
      kind: "select",
      required: true,
      placeholder: null,
      options: [
        { value: "us-10y-yield", label: "US 10Y Treasury Yield", unit: "percent" },
        { value: "fx-eurusd", label: "EUR/USD (needs TWS)", unit: "fx" },
      ],
    },
  ],
  value_unit: "number",
  change_unit: "points",
  order: 20,
});

describe("idea criteria helpers", () => {
  it("generates the same plain-language labels as the server", () => {
    expect(describeCriterion({ observableLabel: "XOM close", condition: "below", threshold: 100, window: null })).toBe("XOM close below 100");
    expect(describeCriterion({ observableLabel: "Brent", condition: "change_over_window", threshold: -10, window: "1m" })).toBe(
      "Brent falls 10% over 1 month"
    );
    expect(
      describeCriterion({ observableLabel: "Fed cut odds", condition: "change_over_window", threshold: 15, window: "5d", changeUnit: "points" })
    ).toBe("Fed cut odds rises 15 pts over 5 days");
    expect(describeCriterion({ observableLabel: "CPI release", condition: "date_reached", threshold: null, window: null })).toBe("CPI release reached");
    expect(
      describeCriterion({
        observableLabel: "XOM close",
        condition: "below",
        threshold: 100,
        window: null,
        formatThreshold: (value) => formatObservableValue("price", value),
      })
    ).toBe("XOM close below 100.00");
  });

  it("formats values with the server's unit rules", () => {
    expect(formatObservableValue("percent", 4.256)).toBe("4.26%");
    expect(formatObservableValue("probability", 64.04)).toBe("64.0%");
    expect(formatObservableValue("bp", 35.4)).toBe("35 bp");
    expect(formatObservableValue("usd", 97512.3)).toBe("$97,512.30");
    expect(formatObservableValue("price", 0.5)).toBe("0.5000");
    expect(formatObservableValue("price", null)).toBe("N/A");
  });

  it("reads per-series units for macro observables", () => {
    const ref = { params: { series_id: "us-10y-yield" } };
    expect(observableValueUnit(MACRO, ref)).toBe("percent");
    expect(observableChangeUnit(MACRO, ref)).toBe("points");
    expect(observableChangeUnit(MACRO, { params: { series_id: "fx-eurusd" } })).toBe("percent");
    expect(defaultObservableLabel(MACRO, { series_id: "fx-eurusd" })).toBe("EUR/USD");
    expect(defaultObservableLabel(definition({}), { symbol: " xom " })).toBe("XOM close");
  });

  it("colours a trigger by what it means for the thesis and never colours holding", () => {
    expect(criterionStateTone("triggered", "invalidate")).toBe("negative");
    expect(criterionStateTone("triggered", "confirm")).toBe("positive");
    expect(criterionStateTone("triggered", "review")).toBe("warning");
    expect(criterionStateTone("unavailable", "confirm")).toBe("warning");
    expect(criterionStateTone("holding", "invalidate")).toBe("");
  });

  it("orders board counts by attention and counts review days in calendar days", () => {
    expect(criteriaSummary({ pending: 1, holding: 2, triggered: 1, unavailable: 0, stale: 0 })).toEqual([
      { state: "triggered", count: 1 },
      { state: "holding", count: 2 },
      { state: "pending", count: 1 },
    ]);
    const today = new Date(Date.UTC(2026, 10, 15, 22, 0));
    expect(daysToReview("2026-11-20", today)).toBe(5);
    expect(daysToReview("2026-11-13", today)).toBe(-2);
    expect(daysToReviewText(-2)).toBe("2d overdue");
    expect(daysToReviewText(null)).toBe("N/A");
  });

  it("groups observables in registry order and checks required params", () => {
    const groups = groupObservables([MACRO, definition({})]);
    expect(groups.map((group) => group.group)).toEqual(["Markets", "Macro"]);
    expect(paramsComplete(definition({}), { symbol: "" })).toBe(false);
    expect(paramsComplete(definition({}), { symbol: "XOM" })).toBe(true);
  });

  it("describes notifications with the value that met the rule and the date first met", () => {
    const trigger: IdeaNotification = {
      notification_id: "trigger:i:c",
      kind: "criterion_triggered",
      idea_id: "i",
      idea_title: "XOM holds",
      created_at: "2026-11-15T09:00:00",
      criterion_id: "c",
      criterion_kind: "invalidate",
      label: "XOM close below 100",
      value_display: "99.00",
      first_met_at: "2026-11-12T00:00:00",
      review_date: null,
      days_overdue: null,
      provenance: null,
    };
    expect(notificationDetail(trigger)).toBe("99.00 · first met 2026-11-12");
    expect(notificationDetail({ ...trigger, kind: "review_due", review_date: "2026-11-10", days_overdue: 5 })).toBe(
      "Review due 2026-11-10 · 5d overdue"
    );
  });
});
