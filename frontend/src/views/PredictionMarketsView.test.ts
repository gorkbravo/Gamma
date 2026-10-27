import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type {
  CopilotWorkingAnalysis,
  PredictionMarket,
  PredictionEventBook,
  PredictionEventBookLeg,
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

  it("says when the venue series lookup failed instead of hiding the siblings", () => {
    const warning =
      "Same-series siblings from Kalshi series 'Fed funds rate' are missing: the series lookup failed (TimeoutError).";
    const { body } = render(PredictionMarketsView, { props: {
      mode: "contract", detail: { ...bucket("dec", "December", 0.11), subtitle: null },
      related: { market_id: "polymarket:dec", related: [], warnings: [warning] },
      onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
    } });
    expect(body).toContain("No linked markets.");
    expect(body).toContain("the series lookup failed (TimeoutError)");
  });
});

// Event Book: una escalera de plazos anidados no es un libro excluyente.
function bookLeg(id: string, subtitle: string, probability: number, overrides: Partial<PredictionEventBookLeg> = {}): PredictionEventBookLeg {
  return {
    market_id: `polymarket:${id}`, venue: "polymarket", title: `Putin out as President of Russia by ${subtitle}?`, subtitle,
    outcome_label: "Yes", probability, best_bid: null, best_ask: null, spread: null, volume: 1000, liquidity: 500,
    open_interest: null, status: "open", end_time: null, resolution_source: null, is_anchor: false,
    divergence_flags: [], ladder_flags: [], ...overrides
  };
}

function eventBook(overrides: Partial<PredictionEventBook>): PredictionEventBook {
  return {
    venue: "polymarket", anchor_market_id: "polymarket:dec26", event_id: "polymarket:event:putin",
    event_title: "Putin out as President of Russia by...?", provider_event_id: "putin", legs: [],
    probability_sum: null, implied_overround: null, favorite_market_id: null, exclusivity_signal: "unverified",
    overround_is_meaningful: false, ladder_kind: null, ladder_inversions: 0,
    completeness: { status: "complete", legs_returned: 0, legs_priced: 0, cap: 160, truncated: false, note: "" },
    warnings: [], source_provider: "polymarket", retrieved_at: null, origin: "test", transformation_note: null,
    ...overrides
  };
}

const renderContract = (book: PredictionEventBook) =>
  render(PredictionMarketsView, { props: {
    mode: "contract", detail: { ...bucket("dec26", "December 31, 2026", 0.02) }, eventBook: book,
    onLoadScreener: vi.fn(), onSelectMarket: vi.fn()
  } }).body;

describe("Prediction Markets event book", () => {
  it("labels a cumulative date ladder and shows monotonicity instead of a book sum", () => {
    const body = renderContract(eventBook({
      exclusivity_signal: "cumulative_ladder", ladder_kind: "date", ladder_inversions: 1,
      legs: [
        bookLeg("dec26", "December 31, 2026", 0.05, { is_anchor: true }),
        bookLeg("mar27", "March 31, 2027", 0.03, {
          ladder_flags: ["At 2.0%-3.0%, entirely below 4.0%-6.0% for the earlier deadline December 31, 2026; a later deadline includes every earlier one."]
        }),
        bookLeg("jun27", "June 30, 2027", 0.095)
      ],
      warnings: ["These contracts are nested deadlines: each later date includes every earlier one, so their probabilities are not summed and no overround applies."]
    }));
    expect(body).toContain("3 rungs");
    expect(body).toContain("date ladder");
    expect(body).toContain("Date ladder");
    expect(body).toContain("nested | not summed");
    expect(body).toContain("1 inverted");
    expect(body).toContain("later ≥ earlier");
    expect(body).toContain("5.0% → 9.5%");
    expect(body).toContain("entirely below 4.0%-6.0% for the earlier deadline December 31, 2026");
    expect(body).toMatch(/class="elevated[^"]*">inverted/);
    // Ni suma, ni overround, ni favorito, ni "complete" como si fuera un libro.
    expect(body).not.toContain("Book Sum");
    expect(body).not.toContain("Overround");
    expect(body).not.toContain("book-complete check");
    expect(body).not.toContain("Favorite");
    expect(body).not.toMatch(/legs \|/);
  });

  it("keeps the book-complete check for mutually exclusive buckets", () => {
    const body = renderContract(eventBook({
      exclusivity_signal: "venue_grouped_candidates", overround_is_meaningful: true,
      probability_sum: 1.03, implied_overround: 0.03, favorite_market_id: "polymarket:b20",
      legs: [bookLeg("b20", "<20", 0.4), bookLeg("b25", "20-29", 0.35), bookLeg("b30", "30+", 0.28)]
    }));
    expect(body).toContain("3 legs");
    expect(body).toContain("Book Sum");
    expect(body).toContain("103.0%");
    expect(body).toContain("Overround");
    expect(body).toContain("+3.0%");
    expect(body).toContain("book-complete check");
    expect(body).toContain("Favorite");
    expect(body).not.toContain("ladder");
    expect(body).not.toContain("Monotonicity");
  });
});
