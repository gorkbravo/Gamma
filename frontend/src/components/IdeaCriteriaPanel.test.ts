import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaCriterion } from "../lib/api/types";
import IdeaCriteriaPanel from "./IdeaCriteriaPanel.svelte";

const PROVENANCE = { source_provider: "yfinance", retrieved_at: "2026-11-15T09:00:00", origin: "research_market_data.history", transformation_note: null };

function criterion(overrides: Partial<IdeaCriterion>): IdeaCriterion {
  return {
    schema_version: 2,
    criterion_id: "c1",
    idea_id: "i1",
    kind: "invalidate",
    label: "XOM close below 100.00",
    observable: { observable_id: "equity_close", params: { symbol: "XOM" }, label: "XOM close" },
    condition: "below",
    threshold: 100,
    window: null,
    cadence: "daily_close",
    state: "pending",
    last_evaluation: null,
    trigger_evaluation: null,
    triggered_at: null,
    acknowledged_at: null,
    armed_at: "2026-11-10T09:00:00",
    created_at: "2026-11-10T09:00:00",
    ...overrides,
  };
}

const TRIGGERED_EVALUATION = {
  state: "triggered" as const,
  evaluated_at: "2026-11-15T09:00:00",
  value: 101,
  value_display: "101.00",
  as_of: "2026-11-13T00:00:00",
  met_value: 99,
  met_display: "99.00",
  reference_value: null,
  change: null,
  first_met_at: "2026-11-11T00:00:00",
  reason: null,
  effective_cadence: "daily_close" as const,
  cadence_note: null,
  provenance: PROVENANCE,
  warnings: [],
};

function idea(status: Idea["status"], criteria: IdeaCriterion[]): Idea {
  return {
    schema_version: 2,
    idea_id: "i1",
    title: "XOM holds its dividend",
    thesis: "Cash returns hold up into Q1.",
    notes: "",
    stance: "long",
    legs: [],
    horizon: { review_date: null, holding_window: null },
    status,
    origin: { kind: "manual", source_ref: null, label: null, handoff: null },
    tags: [],
    created_at: "2026-11-10T09:00:00",
    updated_at: "2026-11-15T09:00:00",
    closed_at: null,
    evidence: [],
    criteria,
    journal: [],
    evidence_counts: { supports: 0, challenges: 0, context: 0 },
    criteria_counts: {
      pending: criteria.filter((item) => item.state === "pending").length,
      holding: criteria.filter((item) => item.state === "holding").length,
      triggered: criteria.filter((item) => item.state === "triggered").length,
      unavailable: criteria.filter((item) => item.state === "unavailable").length,
      stale: criteria.filter((item) => item.state === "stale").length,
    },
    provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-15T09:00:00", origin: "idea_store", transformation_note: null },
  };
}

describe("IdeaCriteriaPanel", () => {
  it("shows the latched trigger with the value that met the rule and offers acknowledgement", () => {
    const body = render(IdeaCriteriaPanel, {
      props: {
        idea: idea("active", [
          criterion({
            state: "triggered",
            last_evaluation: { ...TRIGGERED_EVALUATION },
            trigger_evaluation: { ...TRIGGERED_EVALUATION },
            triggered_at: "2026-11-15T09:00:00",
          }),
        ]),
      },
    }).body;
    expect(body).toContain("XOM close below 100.00");
    expect(body).toContain(">Triggered</span>");
    expect(body).toMatch(/class="tag negative[^"]*"/);
    expect(body).toContain("99.00");
    expect(body).toContain("First met 2026-11-11");
    expect(body).toContain("101.00");
    expect(body).toContain(">Acknowledge</button>");
    expect(body).toContain("1 triggered");
    expect(body).toContain("Evaluated only while Gamma runs");
  });

  it("states why a criterion is unavailable instead of showing it as holding", () => {
    const body = render(IdeaCriteriaPanel, {
      props: {
        idea: idea("active", [
          criterion({
            observable: { observable_id: "option_atm_iv", params: { symbol: "SPY" }, label: "SPY ATM IV" },
            label: "SPY ATM IV above 30.00%",
            condition: "above",
            threshold: 30,
            cadence: "intraday",
            state: "unavailable",
            last_evaluation: {
              ...TRIGGERED_EVALUATION,
              state: "unavailable",
              value: null,
              value_display: null,
              met_value: null,
              met_display: null,
              as_of: null,
              first_met_at: null,
              reason: "Needs Trader Workstation; connect it in Settings.",
              effective_cadence: "daily_close",
              cadence_note: "Intraday needs Trader Workstation; evaluated at the daily close until it connects.",
            },
          }),
        ]),
      },
    }).body;
    expect(body).toContain(">Unavailable</span>");
    expect(body).toContain("Needs Trader Workstation; connect it in Settings.");
    expect(body).toContain("Intraday needs Trader Workstation");
    expect(body).not.toContain(">Holding</span>");
    expect(body).toContain('aria-label="What is this? unavailable"');
  });

  it("explains that drafts are not evaluated and keeps Evaluate now disabled", () => {
    const body = render(IdeaCriteriaPanel, { props: { idea: idea("draft", [criterion({})]) } }).body;
    expect(body).toContain(">Pending</span>");
    expect(body).toContain("Draft ideas are not evaluated");
    expect(body).toMatch(/disabled[^>]*title="Only active ideas are evaluated"|title="Only active ideas are evaluated"[^>]*disabled/);
  });

  it("asks for a criterion when there is none", () => {
    const body = render(IdeaCriteriaPanel, { props: { idea: idea("active", []) } }).body;
    expect(body).toContain("No criteria yet. Add what would prove the thesis wrong before the outcome is known.");
  });
});
