import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { CopilotWorkingAnalysis, PredictionMarketComparison } from "../lib/api/types";
import { predictionComparisonFromWorkingAnalysis } from "../lib/prediction-markets";
import { resolveWorkingAnalysisTarget } from "../lib/copilot-workspace";
import PredictionMarketsView from "./PredictionMarketsView.svelte";

function fixture(): CopilotWorkingAnalysis {
  const ids = ["polymarket:123", "kalshi:FED-YES", "kalshi:MISSING"];
  const comparison: PredictionMarketComparison = {
    requested_range: "1w", effective_resolution_minutes: 60,
    window_start: null, window_end: null, basket: null,
    retrieved_at: "2026-09-05T10:00:00Z", transformation_note: "Changes, not levels; descriptive spreads.",
    warnings: ["Requested contract unavailable: kalshi:MISSING."], pairs: [],
    legs: ids.slice(0, 2).map((id, index) => ({
      market_id: id, venue: index ? "kalshi" : "polymarket", title: `Retained contract ${index + 1}`,
      outcome_label: "Yes", current_probability: 0.42, status: "open", end_time: null,
      event_id: null, event_title: null, points: [], stats: null,
      coverage_start: null, coverage_end: null, warnings: [], source_provider: "fixture", origin: "test"
    }))
  };
  return {
    analysis_id: "work-prediction", session_id: "session-1", run_id: "run-1",
    tool_id: "run_prediction_market_comparison", domain: "prediction_markets",
    analysis_type: "prediction_market_comparison", title: "3-contract comparison",
    status: "active", state_scope: "session_ephemeral", entity: { market_ids: ids },
    inputs: { market_ids: ids, range: "1w", resolution_minutes: 60 }, outputs: { comparison },
    source_ids: [], warnings: comparison.warnings, context_fingerprint: null,
    owning_tab: "prediction_markets", owning_mode: "compare",
    materialization: {
      payload_contract: "copilot.prediction-comparison-working-analysis.v1",
      target_tab: "prediction_markets", target_mode: "compare", durable: false
    },
    created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z",
    expires_at: "2099-01-01T00:00:00Z", materialized_at: null, discarded_at: null,
    read_only_safety: { execution_enabled: false }, source_provider: "fixture", origin: "test",
    transformation_note: null, contract_version: "copilot.working-analysis.v1"
  };
}

describe("Prediction Markets temporary comparison", () => {
  it("resolves only the non-durable target and preserves requested missing IDs and settings", () => {
    const analysis = fixture();
    expect(resolveWorkingAnalysisTarget(analysis)).toEqual({ analysisId: "work-prediction", tab: "prediction_markets", mode: "compare" });
    const retained = predictionComparisonFromWorkingAnalysis(analysis);
    expect(retained?.marketIds).toEqual(analysis.inputs.market_ids);
    expect(retained?.resolutionMinutes).toBe(60);
    expect(retained?.comparison).toBe(analysis.outputs.comparison);
    expect(predictionComparisonFromWorkingAnalysis({ ...analysis, status: "discarded" })).toBeNull();
    expect(predictionComparisonFromWorkingAnalysis({ ...analysis, expires_at: "2000-01-01T00:00:00Z" })).toBeNull();
    expect(predictionComparisonFromWorkingAnalysis({ ...analysis, materialization: { ...analysis.materialization, durable: true } })).toBeNull();
    expect(predictionComparisonFromWorkingAnalysis({ ...analysis, inputs: { ...analysis.inputs, range: "1d" } })).toBeNull();
  });

  it("renders retained evidence over a different live basket without recomputing or saving", () => {
    const analysis = fixture();
    const onCompare = vi.fn();
    const onSetCompareSelection = vi.fn();
    const { body } = render(PredictionMarketsView, { props: {
      mode: "compare", workingAnalysis: analysis,
      comparison: { ...(analysis.outputs.comparison as PredictionMarketComparison),
        legs: [{ ...(analysis.outputs.comparison as PredictionMarketComparison).legs[0], title: "UNRELATED LIVE CONTRACT" }] },
      compareSelection: ["kalshi:UNRELATED", "kalshi:OTHER"], historyRange: "1d",
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn(), onCompare, onSetCompareSelection
    } });
    expect(body).toContain("TEMPORARY");
    expect(body).toContain("Retained contract 1");
    expect(body).toContain("kalshi:MISSING (unavailable)");
    expect(body).toContain("Requested contract unavailable");
    expect(body).toContain("Return to live comparison");
    expect(body).not.toContain("UNRELATED LIVE CONTRACT");
    expect(body).not.toContain("Saved Sets");
    expect(body).toMatch(/disabled[^>]*>Recompute/);
    expect(onCompare).not.toHaveBeenCalled();
    expect(onSetCompareSelection).not.toHaveBeenCalled();
  });

  it("withholds expired evidence without silently showing the live result under a temporary heading", () => {
    const analysis = fixture();
    const { body } = render(PredictionMarketsView, { props: {
      mode: "compare", workingAnalysis: { ...analysis, expires_at: "2000-01-01T00:00:00Z" },
      comparison: analysis.outputs.comparison as PredictionMarketComparison,
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
    } });
    expect(body).toContain("expired or is unavailable");
    expect(body).not.toContain("Retained contract 1");
  });
});
