import { describe, expect, it } from "vitest";
import {
  adoptRiskSourceFromResult,
  resolveRiskSourceView,
  riskSourceIdForScope,
  riskSourceScopeFor,
  type RiskSourceOption,
} from "./risk-source";

const available: RiskSourceOption[] = [
  { id: "portfolio", label: "Live Account Portfolio" },
  { id: "research", label: "Research Scope Snapshot" },
  { id: "strategy_lab_book", label: "AUDIT 2026-09-03 Gold vs Duration" },
];

describe("risk source scope mapping", () => {
  it("round-trips every selector identity", () => {
    for (const source of available) {
      expect(riskSourceIdForScope(riskSourceScopeFor(source.id))).toBe(source.id);
    }
  });

  it("reports an unknown backend scope rather than guessing", () => {
    expect(riskSourceIdForScope("copilot_working_analysis")).toBeNull();
    expect(riskSourceIdForScope(null)).toBeNull();
  });
});

describe("resolveRiskSourceView", () => {
  it("renders the selected source before any result exists", () => {
    expect(resolveRiskSourceView({ selected: "portfolio", result: null })).toEqual({
      rendered: "portfolio",
      renderScope: "portfolio",
      pendingRecompute: false,
    });
  });

  it("renders the research book when the result came from it, whatever the selector says", () => {
    expect(resolveRiskSourceView({ selected: "portfolio", result: { source_scope: "research_book" } })).toEqual({
      rendered: "strategy_lab_book",
      renderScope: "research_book",
      pendingRecompute: true,
    });
  });

  it("does not render the account book when the selector is moved off a research result", () => {
    const view = resolveRiskSourceView({ selected: "portfolio", result: { source_scope: "research" } });
    expect(view.rendered).toBe("research");
    expect(view.renderScope).toBe("research");
    expect(view.pendingRecompute).toBe(true);
  });

  it("is settled once the selector and the result agree", () => {
    const view = resolveRiskSourceView({ selected: "strategy_lab_book", result: { source_scope: "research_book" } });
    expect(view.rendered).toBe("strategy_lab_book");
    expect(view.pendingRecompute).toBe(false);
  });

  it("falls back to the selector for a scope this build cannot map", () => {
    const view = resolveRiskSourceView({ selected: "research", result: { source_scope: "unknown_scope" } });
    expect(view.rendered).toBe("research");
    expect(view.pendingRecompute).toBe(false);
  });
});

describe("adoptRiskSourceFromResult", () => {
  it("adopts the handoff source so the selector matches the computation", () => {
    expect(
      adoptRiskSourceFromResult({ selected: "portfolio", available, result: { source_scope: "research_book" } })
    ).toBe("strategy_lab_book");
  });

  it("returns null when the selection already matches", () => {
    expect(
      adoptRiskSourceFromResult({ selected: "strategy_lab_book", available, result: { source_scope: "research_book" } })
    ).toBeNull();
  });

  it("returns null when there is no result to adopt", () => {
    expect(adoptRiskSourceFromResult({ selected: "portfolio", available, result: null })).toBeNull();
  });

  it("does not select a source the screen does not offer", () => {
    expect(
      adoptRiskSourceFromResult({
        selected: "portfolio",
        available: [{ id: "portfolio", label: "Live Account Portfolio" }],
        result: { source_scope: "research_book" },
      })
    ).toBeNull();
  });
});
