import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import type { CopilotWorkingAnalysis } from "../lib/api/types";
import { researchBasketSnapshot } from "../lib/research-working-analysis";
import { resolveWorkingAnalysisTarget } from "../lib/copilot-workspace";
import { researchDraft } from "../lib/stores/app";
import EquityResearchView from "../views/EquityResearchView.svelte";
import ResearchScopeWorkingAnalysis from "./ResearchScopeWorkingAnalysis.svelte";

function fixture(): CopilotWorkingAnalysis {
  return {
    analysis_id: "basket", session_id: "session", run_id: "run", tool_id: "run_research_basket_analysis",
    domain: "research", analysis_type: "research_basket_analysis", title: "2-asset Research scope",
    status: "active", state_scope: "session_ephemeral", entity: {},
    inputs: { positions: [{ symbol: "AAPL", weight: 0.6 }, { symbol: "MSFT", weight: 0.4 }], benchmark_symbol: "SPY", lookback_days: 252 },
    outputs: { status: "degraded", metrics: { total_return: 0.12, observations_count: 100 },
      coverage: { benchmark_available: true, benchmark_overlap_count: 98 }, top_constituents: [],
      performance_points: [{ time: 1700000000, value: 12 }], benchmark_points: [] },
    source_ids: ["research.basket.fixture"], warnings: ["History coverage is thin."], context_fingerprint: null,
    owning_tab: "equity_research", owning_mode: "scope_analysis", materialization: {
      durable: false, target_tab: "equity_research", target_mode: "scope_analysis",
      payload_contract: "copilot.research-scope-working-analysis.v1"
    },
    created_at: "2026-09-06T00:00:00Z", updated_at: "2026-09-06T00:00:00Z", expires_at: "2099-01-01T00:00:00Z",
    materialized_at: null, discarded_at: null, read_only_safety: { execution_enabled: false },
    source_provider: "fixture", origin: "gamma.research.analyze", transformation_note: "Opening does not recompute or save a scope.",
    contract_version: "copilot.working-analysis.v1"
  };
}

describe("temporary Research scope", () => {
  it("resolves the exact non-durable target and withholds expired or unsupported state", () => {
    const analysis = fixture();
    expect(resolveWorkingAnalysisTarget(analysis)).toEqual({ analysisId: "basket", tab: "equity_research", mode: "scope_analysis" });
    expect(researchBasketSnapshot(analysis)?.positions).toEqual(analysis.inputs.positions);
    expect(researchBasketSnapshot({ ...analysis, expires_at: "2000-01-01T00:00:00Z" })).toBeNull();
    expect(resolveWorkingAnalysisTarget({ ...analysis, status: "discarded" })).toBeNull();
    expect(researchBasketSnapshot({ ...analysis, outputs: { ...analysis.outputs, status: "unavailable" } })).toBeNull();
    expect(resolveWorkingAnalysisTarget({ ...analysis, materialization: { ...analysis.materialization, durable: true } })).toBeNull();
  });
  it("renders retained evidence without loading, saving, or overwriting the live draft", () => {
    const callback = vi.fn();
    const before = get(researchDraft);
    const { body } = render(EquityResearchView, { props: {
      workingAnalysis: fixture(), mode: "scope_analysis", selectedEquitySymbol: "NVDA",
      onLoadOverview: callback, onRun: callback, onCompare: callback, onLoadSaved: callback,
      onSaveResearch: callback, onDeleteSaved: callback
    } });
    expect(body).toContain("TEMPORARY");
    expect(body).toContain("60.00%");
    expect(body).toContain("12.00%");
    expect(body).toContain("History coverage is thin.");
    expect(body).toContain("Return to live scope");
    expect(body).not.toContain("NVDA");
    expect(body).not.toContain("Run Analysis");
    expect(callback).not.toHaveBeenCalled();
    expect(get(researchDraft)).toEqual(before);
  });
  it("does not show expired analytics under a temporary heading", () => {
    const { body } = render(ResearchScopeWorkingAnalysis, { props: { analysis: { ...fixture(), status: "expired" } } });
    expect(body).toContain("expired or unavailable");
    expect(body).not.toContain("12.00%");
    expect(body).not.toContain("AAPL");
  });
});
