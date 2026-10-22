import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type {
  CopilotWorkingAnalysis,
  PredictionMarket,
  PredictionMarketComparison,
  RelatedPredictionMarket
} from "../lib/api/types";
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

// GUA-20261021-15: agrupación opcional del screener y secciones de RELATED.
function bucket(id: string, label: string, probability: number): PredictionMarket {
  return {
    market_id: `polymarket:${id}`, venue: "polymarket",
    title: `Will ${label} ships transit the Strait of Hormuz between October 19-October 25?`, subtitle: label,
    description: null, status: "open", category: "Geopolitics",
    event_id: "polymarket:event:wk-1019", event_title: "How many ships transit the Strait of Hormuz week of October 19?",
    series_id: null, series_title: null, provider_market_id: id, provider_condition_id: null,
    provider_event_id: "wk-1019", provider_series_id: null, slug: null,
    end_time: "2099-10-26T00:00:00Z", open_time: null, close_time: null,
    current_probability: probability, probability_label: "Yes", volume: null, volume_24h: null, liquidity: null,
    open_interest: null, best_bid: null, best_ask: null, spread: null, recent_price_change: null,
    resolved_probability: null, resolution_outcome: null, image_url: null, resolution_source: null,
    outcomes: [], tags: [],
    freshness: { status: "fresh", is_stale: false, is_broken: false, reason: null, last_history_point_at: null, retrieval_age_seconds: 1, history_lag_seconds: null },
    research_score: null, research_rationale: null, source_provider: "polymarket", retrieved_at: null,
    origin: "test", transformation_note: null
  };
}

// Buckets contiguos (<20 / 20-29 / 30+): el libro visible está completo.
const book = () => [bucket("b25", "20-29", 0.35), bucket("b20", "<20", 0.4), bucket("b30", "30+", 0.28)];

describe("Prediction Markets event grouping", () => {
  it("defaults to the flat screener", () => {
    const { body } = render(PredictionMarketsView, { props: {
      mode: "screener", screener: { markets: book(), venues: [], warnings: [] },
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
    } });
    expect(body).not.toContain("Event group");
    expect(body).toContain("Group 1");
    expect(body).toContain("Will 20-29 ships transit");
  });

  it("renders one event header with the distribution, the sum and the most likely bucket", () => {
    const { body } = render(PredictionMarketsView, { props: {
      mode: "screener", groupEvents: true, screener: { markets: book(), venues: [], warnings: [] },
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
    } });
    expect(body).toContain("Event group How many ships transit the Strait of Hormuz week of October 19?");
    expect(body).toContain("3 legs in view");
    expect(body).toContain("mode &lt;20");
    expect(body).toContain("Σ 103.0%");
    expect(body).toContain("+3.0% vs 100%");
    expect(body).toMatch(/Distribution: (&lt;|<)20 40\.0%, 20-29 35\.0%, 30\+ 28\.0%/);
    // Colapsado por defecto: las legs individuales no se pintan hasta expandir.
    expect(body).not.toContain("Will 20-29 ships transit");
  });

  it("labels related siblings by event and series next to the analogs", () => {
    const related: RelatedPredictionMarket[] = [
      { market_id: "kalshi:analog", venue: "kalshi", title: "Kalshi Hormuz analog", probability: 0.14, price_gap: 0.03,
        relationship: "cross_venue_analog", note: null, source_provider: "kalshi", retrieved_at: null, origin: "test",
        transformation_note: null },
      { market_id: "polymarket:oct", venue: "polymarket", title: "Hormuz normal by October 31?", probability: 0.007,
        price_gap: 0.103, relationship: "same_series", note: "Shares the venue series", source_provider: "polymarket",
        retrieved_at: null, origin: "test", transformation_note: null, sibling_scope: "same_series", sibling_order: 0,
        group_title: "Hormuz Traffic Returns to Normal", end_time: "2026-10-31T12:00:00Z" }
    ];
    const { body } = render(PredictionMarketsView, { props: {
      mode: "contract", detail: { ...bucket("dec", "December", 0.11), subtitle: null },
      related: { market_id: "polymarket:dec", related },
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
    } });
    expect(body).toContain("Analogs");
    expect(body).toContain("Same series");
    expect(body).toContain("Hormuz Traffic Returns to Normal");
    expect(body).toContain("cross_venue_analog | kalshi");
    expect(body).toMatch(/resolves Oct 31, 26/);
  });
});
