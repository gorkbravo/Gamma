import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaReview, IdeaReviewStatsResponse } from "../lib/api/types";
import IdeaCloseForm from "./IdeaCloseForm.svelte";
import IdeaReviewMode from "./IdeaReviewMode.svelte";
import IdeaReviewSection from "./IdeaReviewSection.svelte";

const REVIEW: IdeaReview = {
  review_id: "r1",
  outcome: "invalidated",
  lesson: "Close when the invalidation fires.",
  expected: "Refiners beat SPY into Q1.",
  realized_note: "Cracks collapsed.",
  opened_at: "2026-11-09T14:00:00",
  closed_at: "2026-11-20T15:00:00",
  holding_days: 11.04,
  evidence_verdicts: [{ evidence_id: "e1", verdict: "failed", title: "Crack spread", stance: "supports" }],
  criteria_at_close: [
    {
      criterion_id: "c1",
      kind: "invalidate",
      label: "XOM close below 100",
      state: "triggered",
      triggered_at: "2026-11-15T21:30:00",
      first_met_at: "2026-11-14T21:00:00",
    },
  ],
  realized: {
    status: "tracking",
    computed_at: "2026-11-20T15:00:00",
    as_of: "2026-11-19",
    net_return: -0.0412,
    gross_return: -0.04,
    benchmark_return: 0.01,
    benchmark: "SPY",
    sessions: 9,
    gaps: 0,
    partial: false,
    final: false,
  },
  first_invalidation_at: "2026-11-14T21:00:00",
};

const IDEA: Idea = {
  schema_version: 4,
  idea_id: "i1",
  title: "Refiners beat SPY",
  thesis: "Refiners beat SPY into Q1.",
  notes: "",
  stance: "relative",
  legs: [],
  horizon: { review_date: null, holding_window: null },
  status: "closed",
  origin: { kind: "manual", source_ref: null, label: null, handoff: null },
  tags: [],
  created_at: "2026-11-06T12:00:00",
  updated_at: "2026-11-20T15:00:00",
  closed_at: "2026-11-20T15:00:00",
  evidence: [
    {
      schema_version: 4,
      evidence_id: "e1",
      idea_id: "i1",
      kind: "metric",
      stance: "supports",
      title: "Crack spread",
      captured_values: {},
      provenance: null,
      freshness: null,
      reopen: null,
      captured_at: "2026-11-08T10:00:00",
      note: "",
    },
  ],
  criteria: [],
  journal: [],
  evidence_counts: { supports: 1, challenges: 0, context: 0 },
  criteria_counts: { pending: 0, holding: 0, triggered: 0, unavailable: 0, stale: 0 },
  tracking: null,
  reviews: [REVIEW],
  provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-20T15:00:00", origin: "idea_store", transformation_note: null },
};

describe("IdeaReviewSection", () => {
  it("shows the review of the current close with the record as it stood", () => {
    const { body } = render(IdeaReviewSection, { props: { idea: IDEA } });
    expect(body).toContain("Invalidated");
    expect(body).toContain("held 11 days");
    expect(body).toContain("Refiners beat SPY into Q1.");
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("Net -4.12%");
    expect(body).toContain("as of 2026-11-19");
    expect(body).toContain("Close when the invalidation fires.");
    expect(body).toContain("Cracks collapsed.");
    expect(body).toContain("Fired before the close");
    expect(body).toContain("XOM close below 100");
    expect(body).toContain("Failed");
    expect(body).not.toContain("from an earlier close");
  });

  it("marks an earlier review once the idea is reopened, and renders nothing without reviews", () => {
    const reopened = { ...IDEA, status: "active" as const, closed_at: null };
    expect(render(IdeaReviewSection, { props: { idea: reopened } }).body).toContain("from an earlier close");
    expect(render(IdeaReviewSection, { props: { idea: { ...IDEA, reviews: [] } } }).body).not.toContain("Review");
  });
});

describe("IdeaCloseForm", () => {
  it("asks for the review: outcome, expectation prefilled with the thesis, verdicts and the lesson", () => {
    const active = { ...IDEA, status: "active" as const, closed_at: null, reviews: [] };
    const { body } = render(IdeaCloseForm, { props: { idea: active } });
    for (const label of ["Confirmed", "Invalidated", "Abandoned", "Expired"]) expect(body).toContain(label);
    expect(body).toContain("Refiners beat SPY into Q1.</textarea>");
    expect(body).toContain("Hypothetical, not executed");
    expect(body).toContain("No tracked record");
    expect(body).toContain("Verdict for Crack spread");
    expect(body).toContain("Lesson");
    expect(body).toMatch(/<button type="submit"[^>]*disabled/);
  });
});

describe("IdeaCloseForm realized state", () => {
  const segment = {
    segment_id: "seg-1",
    number: 1,
    started_at: "2026-11-09T14:00:00",
    start_reason: "activated",
    start_note: "Activated",
    stance: "relative" as const,
    legs: [],
    ended_at: null,
    end_reason: null,
    end_note: "",
    untracked_reason: null,
  };
  const tracked = {
    ...IDEA,
    status: "active" as const,
    closed_at: null,
    reviews: [],
    tracking: {
      label: "Hypothetical, not executed",
      benchmark: "SPY",
      cost_model: { per_side_bp: {}, leg_classes: {}, updated_at: null },
      segments: [segment],
      snapshot: null,
    },
  };

  it("says loading, unavailable or not computed instead of waiting forever", () => {
    expect(render(IdeaCloseForm, { props: { idea: tracked, trackingLoading: true } }).body).toContain("Loading…");
    const failed = render(IdeaCloseForm, { props: { idea: tracked, trackingError: "502" } }).body;
    expect(failed).toContain("Tracking unavailable");
    expect(failed).not.toContain("Loading…");
    expect(render(IdeaCloseForm, { props: { idea: tracked } }).body).toContain("Not computed yet");
  });

  it("falls back to the last stored headline with its date", () => {
    const stored = {
      ...tracked,
      tracking: {
        ...tracked.tracking,
        snapshot: {
          status: "tracking" as const,
          computed_at: "2026-11-20T12:00:00",
          as_of: "2026-11-19",
          net_return: 0.0123,
          gross_return: 0.014,
          benchmark_return: 0.002,
          benchmark: "SPY",
          sessions: 9,
          gaps: 0,
          partial: false,
        },
      },
    };
    const body = render(IdeaCloseForm, { props: { idea: stored, trackingError: "502" } }).body;
    expect(body).toContain("+1.23%");
    expect(body).toContain("as of 2026-11-19 (last stored figure)");
  });
});

const STATS: IdeaReviewStatsResponse = {
  rows: [
    {
      idea_id: "i1",
      title: "Refiners beat SPY",
      stance: "relative",
      status: "closed",
      tags: ["energy"],
      outcome: "invalidated",
      opened_at: "2026-11-09T14:00:00",
      closed_at: "2026-11-20T15:00:00",
      holding_days: 11.04,
      expected: "Refiners beat SPY into Q1.",
      lesson: "Close when the invalidation fires.",
      net_return: -0.0412,
      benchmark: "SPY",
      benchmark_return: 0.01,
      excess_return: -0.0512,
      realized_final: true,
      realized_as_of: "2026-11-20",
      tracked: true,
      invalidation_criteria: 1,
      first_invalidation_at: "2026-11-14T21:00:00",
      evidence_verdicts: { held: 0, failed: 1, unclear: 0 },
    },
  ],
  outcomes: { confirmed: 0, invalidated: 1, abandoned: 0, expired: 0 },
  holding_days: {
    count: 1,
    median: 11.04,
    mean: 11.04,
    min: 11.04,
    max: 11.04,
    median_by_outcome: { confirmed: null, invalidated: 11.04, abandoned: null, expired: null },
  },
  realized: {
    count: 1,
    untracked: 0,
    median_net: -0.0412,
    median_excess: -0.0512,
    excess_count: 1,
    positive: 0,
    negative: 1,
    median_net_by_outcome: { confirmed: null, invalidated: -0.0412, abandoned: null, expired: null },
  },
  invalidation: {
    losses: 1,
    losses_with_invalidation_criteria: 1,
    losses_with_trigger_before_close: 1,
    share_of_losses: 1,
    share_of_losses_with_criteria: 1,
  },
  label: "Hypothetical, not executed",
  source_provider: "gamma_ideas",
  retrieved_at: "2026-11-21T10:00:00",
  origin: "idea_service.review_statistics",
  transformation_note: null,
};

describe("IdeaReviewMode", () => {
  it("describes the closed record with sample sizes and no score", () => {
    const { body } = render(IdeaReviewMode, { props: { stats: STATS } });
    expect(body).toContain("your own record, no score");
    expect(body).toContain("Median holding");
    expect(body).toContain("11 days");
    expect(body).toContain("-4.12%");
    expect(body).toContain("-5.12%");
    expect(body).toContain("1 of 1 (100%)");
    expect(body).toContain("final · 2026-11-20");
    expect(body).toContain("Fired");
    expect(body).toContain("Close when the invalidation fires.");
    expect(body).not.toMatch(/score:/i);
  });

  it("explains an empty record in place", () => {
    const empty = { ...STATS, rows: [], outcomes: { confirmed: 0, invalidated: 0, abandoned: 0, expired: 0 } };
    expect(render(IdeaReviewMode, { props: { stats: empty } }).body).toContain("No closed ideas yet.");
    expect(render(IdeaReviewMode, { props: { stats: null, loading: true } }).body).toContain("Loading…");
  });
});
