import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaRiskSnapshot, IdeaTestSnapshot } from "../lib/api/types";
import { asLoss, episodeCoverageText, formatRatio, snapshotLegsText, snapshotWindowText, worstEpisode } from "../lib/idea-analysis";
import IdeaAnalysisPanel from "./IdeaAnalysisPanel.svelte";

const LEGS = [
  {
    entity: { entity_type: "equity", label: "Apple", normalized_id: "AAPL", provider_id: null, native_id: null, metadata: {} },
    stated_weight: 1,
    weight: 0.5,
    weight_source: "stated" as const,
    asset_class: "us_equity_liquid" as const,
    market: "us",
    key: "equity:AAPL",
  },
  {
    entity: { entity_type: "equity", label: "Microsoft", normalized_id: "MSFT", provider_id: null, native_id: null, metadata: {} },
    stated_weight: -1,
    weight: -0.5,
    weight_source: "stated" as const,
    asset_class: "us_equity_liquid" as const,
    market: "us",
    key: "equity:MSFT",
  },
];

const BASE = {
  created_at: "2026-11-21T19:36:14",
  legs: LEGS,
  benchmark: "SPY",
  window_start: "2024-12-24",
  window_end: "2026-01-27",
  observations: 286,
  source: "idea_legs" as const,
  source_ids: { composition: "Idea: AAPL over MSFT" },
  provenance: { source_provider: "gamma_strategy_lab", retrieved_at: "2026-11-21T19:36:14", origin: "research_service.strategy_lab.portfolio_compose", transformation_note: null },
  warnings: [],
  stale_reason: null,
};

const TEST: IdeaTestSnapshot = {
  ...BASE,
  snapshot_id: "t1",
  lookback_days: 756,
  metrics: {
    total_return: -0.0039,
    annual_return: -0.0034,
    annual_volatility: 0.1623,
    sharpe_ratio: 0.0597,
    max_drawdown: -0.2356,
    benchmark_total_return: -0.0211,
    excess_total_return: 0.0172,
  },
  leg_contributions: { Apple: 0.0028, Microsoft: -0.0071 },
  equity_curve: [["2024-12-24", 1], ["2025-06-02", 0.95], ["2026-01-27", 0.996]],
  benchmark_curve: [["2024-12-24", 1], ["2025-06-02", 0.97], ["2026-01-27", 0.979]],
  costs_included: false,
  sample: "in_sample",
};

const RISK: IdeaRiskSnapshot = {
  ...BASE,
  snapshot_id: "r1",
  lookback_days: 252,
  window_start: "2025-02-10",
  observations: 252,
  alpha: 0.95,
  horizon_days: 1,
  metrics: { historical_var: 0.0167, historical_es: 0.0211, parametric_var: 0.0172, annual_volatility: 0.1656, beta: 0.037 },
  episodes: [
    { episode_id: "gfc_2007_2009", label: "Global financial crisis", start: "2007-10-09", end: "2009-03-09", status: "unavailable", book_return: null, benchmark_return: null, max_drawdown: null },
    { episode_id: "tariffs_2025", label: "Tariff shock 2025", start: "2025-02-19", end: "2025-04-08", status: "full", book_return: 0.0293, benchmark_return: -0.189, max_drawdown: -0.03 },
  ],
  worst_episode_id: "tariffs_2025",
};

const IDEA: Idea = {
  schema_version: 5,
  idea_id: "i1",
  title: "AAPL over MSFT",
  thesis: "Apple holds up better.",
  notes: "",
  stance: "relative",
  legs: [
    { entity: LEGS[0].entity, weight: 1 },
    { entity: LEGS[1].entity, weight: -1 },
  ],
  horizon: { review_date: null, holding_window: null },
  status: "active",
  origin: { kind: "manual", source_ref: null, label: null, handoff: null },
  tags: [],
  created_at: "2026-11-21T19:00:00",
  updated_at: "2026-11-21T19:36:14",
  closed_at: null,
  evidence: [],
  criteria: [],
  journal: [],
  evidence_counts: { supports: 0, challenges: 0, context: 0 },
  criteria_counts: { pending: 0, holding: 0, triggered: 0, unavailable: 0, stale: 0 },
  tracking: null,
  reviews: [],
  tests: [TEST],
  risks: [RISK],
  provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-21T19:36:14", origin: "idea_store", transformation_note: null },
};

describe("idea analysis helpers", () => {
  it("formats ratios, losses, legs, windows and the worst episode", () => {
    expect(formatRatio(1.104)).toBe("1.10");
    expect(formatRatio(null)).toBe("N/A");
    expect(asLoss(0.0167)).toBe(-0.0167);
    expect(asLoss(-0.0167)).toBe(-0.0167);
    expect(asLoss(undefined)).toBeNull();
    expect(snapshotLegsText(TEST)).toBe("Apple +50% · Microsoft -50%");
    expect(snapshotWindowText(TEST)).toBe("2024-12-24 → 2026-01-27 · 286 observations");
    expect(worstEpisode(RISK)?.episode_id).toBe("tariffs_2025");
    expect(worstEpisode({ ...RISK, worst_episode_id: null, episodes: [RISK.episodes[0]] })).toBeNull();
  });

  it("prefers a fully covered episode and says how much of the book a partial one covers (live check 2026-11-21)", () => {
    const partial = { episode_id: "rates_2022", label: "2022 rate shock", start: "2022-01-03", end: "2022-10-12", status: "partial" as const, book_return: -0.36, benchmark_return: -0.24, max_drawdown: -0.4, coverage: 0.5 };
    const mixed = { ...RISK, worst_episode_id: null, episodes: [...RISK.episodes, partial] };
    expect(worstEpisode(mixed)?.episode_id).toBe("tariffs_2025");
    expect(worstEpisode({ ...mixed, episodes: [partial] })?.episode_id).toBe("rates_2022");
    expect(episodeCoverageText(partial)).toBe("Partial · 50% of gross");
    expect(episodeCoverageText({ ...partial, coverage: null })).toBe("Partial");
    expect(episodeCoverageText(RISK.episodes[1])).toBe("Full");
    const body = render(IdeaAnalysisPanel, {
      props: { idea: { ...IDEA, risks: [{ ...RISK, episodes: [partial], worst_episode_id: "rates_2022" }] } },
    }).body;
    expect(body).toContain("2022 rate shock · partial · 50% of gross");
  });
});

describe("IdeaAnalysisPanel", () => {
  it("labels the backtest in-sample with no costs and shows its window and date", () => {
    const { body } = render(IdeaAnalysisPanel, { props: { idea: IDEA } });
    expect(body).toContain("No costs");
    expect(body).toContain("In-sample only");
    expect(body).toContain("2024-12-24 → 2026-01-27 · 286 observations");
    expect(body).toContain("Apple +50% · Microsoft -50%");
    expect(body).toContain("-0.39%");
    expect(body).toContain("-23.56%");
    expect(body).toContain("0.06");
    expect(body).toContain("height:160px");
    expect(body).toContain("Rerun test");
  });

  it("shows VaR and expected shortfall as losses and names the worst replayed episode", () => {
    const { body } = render(IdeaAnalysisPanel, { props: { idea: IDEA } });
    expect(body).toContain("-1.67%");
    expect(body).toContain("-2.11%");
    expect(body).toContain("95%, 1 day");
    expect(body).toContain("Tariff shock 2025");
    expect(body).toContain("+2.93%");
    // Los episodios sin datos no entran en la tabla.
    expect(body).not.toContain("Global financial crisis");
  });

  it("marks a stale snapshot and explains an empty one", () => {
    const stale = { ...IDEA, tests: [{ ...TEST, stale_reason: "The legs or weights changed after this run." }], risks: [] };
    const body = render(IdeaAnalysisPanel, { props: { idea: stale } }).body;
    expect(body).toContain('title="The legs or weights changed after this run."');
    expect(body).toContain("No risk snapshot yet.");
    const legless = render(IdeaAnalysisPanel, { props: { idea: { ...IDEA, legs: [], tests: [], risks: [] } } }).body;
    expect(legless).toContain("Add legs to backtest the idea.");
    expect(legless).toMatch(/<button type="button" class="btn is-small is-ghost"[^>]*disabled/);
  });

  it("names the tab an attached snapshot came from (I4c)", () => {
    const attached = { ...TEST, source: "strategy_lab" as const, source_ids: { attached_label: "Megacap pair" } };
    const riskAttached = { ...RISK, source: "risk_tab" as const, source_ids: { attached_label: "Book" } };
    const { body } = render(IdeaAnalysisPanel, { props: { idea: { ...IDEA, tests: [attached], risks: [riskAttached] } } });
    expect(body).toContain("From Strategy Lab");
    expect(body).toContain("From Risk");
    expect(render(IdeaAnalysisPanel, { props: { idea: IDEA } }).body).not.toContain("From Strategy Lab");
  });
});
