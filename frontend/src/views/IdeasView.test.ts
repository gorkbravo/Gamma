import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { Idea, IdeaListResponse } from "../lib/api/types";
import { buildReopenEnvelope } from "../lib/ideas";
import IdeasView from "./IdeasView.svelte";

const LIST: IdeaListResponse = {
  items: [
    {
      idea_id: "i1",
      title: "Refiners beat SPY",
      thesis: "Crack spreads stay wide into Q1.",
      stance: "relative",
      status: "active",
      tags: ["energy"],
      legs: [
        { label: "XOM", entity_type: "equity", normalized_id: "XOM", weight: 1 },
        { label: "SPY", entity_type: "etf", normalized_id: "SPY", weight: -1 },
      ],
      evidence_counts: { supports: 2, challenges: 1, context: 0 },
      evidence_total: 3,
      last_evidence_at: "2026-11-14T09:00:00",
      journal_count: 4,
      origin_kind: "manual",
      origin_ref: null,
      review_date: null,
      created_at: "2026-11-13T09:00:00",
      updated_at: "2026-11-14T09:00:00",
    },
    {
      idea_id: "i2",
      title: "Old rates idea",
      thesis: "",
      stance: "neutral",
      status: "archived",
      tags: [],
      legs: [],
      evidence_counts: { supports: 0, challenges: 0, context: 0 },
      evidence_total: 0,
      last_evidence_at: null,
      journal_count: 1,
      origin_kind: "manual",
      origin_ref: null,
      review_date: null,
      created_at: "2026-11-01T09:00:00",
      updated_at: "2026-11-01T09:00:00",
    },
  ],
  total: 2,
  status_counts: { draft: 0, active: 1, closed: 0, archived: 1 },
  tags: ["energy"],
  storage_warnings: [{ action: "quarantined", file_name: "bad.json", message: "Idea file bad.json is not valid JSON.", created_at: "2026-11-14T09:00:00" }],
  source_provider: "gamma_ideas",
  retrieved_at: "2026-11-14T09:30:00",
  origin: "idea_service.list_ideas",
  transformation_note: null,
};

const IDEA: Idea = {
  schema_version: 1,
  idea_id: "i1",
  title: "Refiners beat SPY",
  thesis: "Crack spreads stay wide into Q1.",
  notes: "Watch the January print.",
  stance: "relative",
  legs: [],
  horizon: { review_date: "2027-03-31", holding_window: "3M" },
  status: "active",
  origin: { kind: "manual", source_ref: null, label: null, handoff: null },
  tags: ["energy"],
  created_at: "2026-11-13T09:00:00",
  updated_at: "2026-11-14T09:00:00",
  closed_at: null,
  evidence: [
    {
      schema_version: 1,
      evidence_id: "e1",
      idea_id: "i1",
      kind: "metric",
      stance: "challenges",
      title: "XOM price and valuation",
      captured_values: { metrics: [{ label: "P/E", display: "12.3x", value: 12.3 }, { label: "FCF yield", display: null, value: null }] },
      provenance: { source_provider: "sample", retrieved_at: "2026-11-14T08:59:00", origin: "fundamentals_view.price_and_valuation", transformation_note: null },
      freshness: { label: "mocked", retrieved_at: null, source_timestamp: null, evaluated_at: null, age_seconds: null, ttl_seconds: null, is_stale: false, warnings: [] },
      reopen: buildReopenEnvelope({
        tab: "fundamentals",
        mode: "overview",
        entity: { entity_type: "equity", label: "Exxon Mobil", normalized_id: "XOM" },
        now: new Date("2026-11-14T09:00:00Z"),
      }),
      captured_at: "2026-11-14T09:00:00",
      note: "Cheap for a reason?",
    },
  ],
  journal: [
    { schema_version: 1, entry_id: "j1", idea_id: "i1", kind: "created", author: "system", body: "Created the idea.", created_at: "2026-11-13T09:00:00", details: {} },
    {
      schema_version: 1,
      entry_id: "j2",
      idea_id: "i1",
      kind: "edited",
      author: "system",
      body: "Edited thesis.",
      created_at: "2026-11-13T09:05:00",
      details: { changes: [{ field: "thesis", before: "", after: "Crack spreads stay wide into Q1." }] },
    },
    { schema_version: 1, entry_id: "j3", idea_id: "i1", kind: "decision", author: "user", body: "Hold until the print.", created_at: "2026-11-14T09:10:00", details: {} },
  ],
  evidence_counts: { supports: 0, challenges: 1, context: 0 },
  provenance: { source_provider: "gamma_ideas", retrieved_at: "2026-11-14T09:30:00", origin: "idea_store", transformation_note: null },
};

describe("IdeasView", () => {
  it("lists open ideas on the Board with stance, legs, status and evidence counts", () => {
    const { body } = render(IdeasView, { props: { mode: "board", list: LIST } });
    expect(body).toContain('aria-label="Ideas modes"');
    expect(body).toContain("Refiners beat SPY");
    expect(body).toContain("Crack spreads stay wide into Q1.");
    expect(body).toContain("XOM +1, SPY -1");
    expect(body).toContain("Relative");
    expect(body).toContain(">Active</span>");
    expect(body).toMatch(/<th class="num">Challenges<\/th>/);
    // The default "Open" filter hides archived ideas.
    expect(body).not.toContain("Old rates idea");
    expect(body).toContain("1 shown");
    expect(body).toContain("Idea file bad.json is not valid JSON.");
  });

  it("explains an empty board and the loading state in place", () => {
    const empty = render(IdeasView, { props: { mode: "board", list: { ...LIST, items: [], total: 0 } } }).body;
    expect(empty).toContain("No ideas yet.");
    const loading = render(IdeasView, { props: { mode: "board", list: null, loading: true } }).body;
    expect(loading).toContain("Loading…");
  });

  it("shows the idea with evidence grouped by stance, frozen values, provenance and journal", () => {
    const { body } = render(IdeasView, { props: { mode: "idea", list: LIST, idea: IDEA } });
    expect(body).toContain("Crack spreads stay wide into Q1.");
    expect(body.indexOf(">Supports</h3>")).toBeLessThan(body.indexOf(">Challenges</h3>"));
    expect(body.indexOf(">Challenges</h3>")).toBeLessThan(body.indexOf(">Context</h3>"));
    expect(body).toContain("No supporting evidence pinned yet.");
    expect(body).toContain("XOM price and valuation");
    expect(body).toContain("Fundamentals / Overview · Exxon Mobil");
    expect(body).toContain("12.3x");
    expect(body).toContain("FCF yield");
    expect(body).toContain("N/A");
    expect(body).toContain("Cheap for a reason?");
    expect(body).toContain("Sample");
    expect(body).toContain('title="Open Fundamentals / Overview on Exxon Mobil"');
    expect(body).toContain("Hold until the print.");
    expect(body).toContain("thesis: empty → Crack spreads stay wide into Q1.");
    expect(body).toContain("append-only");
    expect(body).toContain("Export Markdown");
    expect(body).toContain("Export JSON");
    expect(body).toContain("Review 2027-03-31 · 3M");
  });

  it("asks for a selection when Idea mode has no idea", () => {
    const { body } = render(IdeasView, { props: { mode: "idea", list: LIST, idea: null } });
    expect(body).toContain("No idea selected.");
  });
});
