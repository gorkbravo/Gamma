import { describe, expect, it } from "vitest";
import type { IdeaEvidence, IdeaSummary } from "./api/types";
import {
  boardFilterStatuses,
  buildPromotePayload,
  buildReopenEnvelope,
  captureMetric,
  capturedMetricPairs,
  capturedValuesExtraCount,
  findPromotedIdea,
  formatLegs,
  groupEvidenceByStance,
  handoffPlaceLabel,
  ideaExportFilename,
  parseTagInput,
  pinBadgeData,
  pinSourceFromBadge,
  pinSourceFromProvenance,
  sitrepHandoffToEnvelope,
} from "./ideas";
import type { SitrepFollowUp } from "./view-models/sitrep";

const NOW = new Date("2026-11-14T09:30:00Z");

function evidence(overrides: Partial<IdeaEvidence>): IdeaEvidence {
  return {
    schema_version: 1,
    evidence_id: "e1",
    idea_id: "i1",
    kind: "metric",
    stance: "supports",
    title: "Pin",
    captured_values: {},
    provenance: null,
    freshness: null,
    reopen: null,
    captured_at: "2026-11-14T09:00:00",
    note: "",
    ...overrides,
  };
}

describe("ideas capture helpers", () => {
  it("builds a reopen envelope that targets the source tab, mode, entity and lens", () => {
    const envelope = buildReopenEnvelope({
      tab: "fundamentals",
      mode: "overview",
      entity: { entity_type: "equity", label: "Exxon Mobil", normalized_id: "XOM", metadata: { symbol: "XOM" } },
      timeframe: "1Y",
      normalizedIds: { symbol: "XOM", cik: "", empty: null },
      provider: "sec_edgar",
      now: NOW,
    });
    expect(envelope).toMatchObject({
      source_tab: "fundamentals",
      source_mode: "overview",
      intended_target_tab: "fundamentals",
      intended_target_mode: "overview",
      selected_timeframe: { label: "1Y", start: null, end: null },
      normalized_ids: { symbol: "XOM" },
      provider: "sec_edgar",
      timestamp: "2026-11-14T09:30:00.000Z",
    });
    expect(envelope.selected_entity).toMatchObject({ normalized_id: "XOM", label: "Exxon Mobil", metadata: { symbol: "XOM" } });
  });

  it("freezes provenance only when a provider and a retrieval time exist", () => {
    const full = pinSourceFromProvenance(
      { source_provider: "fred", retrieved_at: "2026-11-14T08:00:00", freshness_label: "live", transformation_note: "YoY", warnings: ["late"] },
      "macro_view.snapshot"
    );
    expect(full.provenance).toEqual({
      source_provider: "fred",
      retrieved_at: "2026-11-14T08:00:00",
      origin: "macro_view.snapshot",
      transformation_note: "YoY",
    });
    expect(full.freshness).toMatchObject({ label: "live", warnings: ["late"] });

    const partial = pinSourceFromProvenance({ source_provider: "mock", freshness: { status: "stale" } }, "x");
    expect(partial.provenance).toBeNull();
    expect(partial.freshness?.label).toBe("stale");
    expect(pinSourceFromProvenance(null, "x")).toEqual({ provenance: null, freshness: null });

    const fromBadge = pinSourceFromBadge(
      {
        provider: "polymarket",
        state: "live",
        rawLabel: "fresh",
        retrievedAt: "2026-11-14T09:00:00",
        sourceTimestamp: null,
        transformationNote: null,
        warnings: [],
      },
      "prediction_markets_view.contract"
    );
    expect(fromBadge.provenance?.source_provider).toBe("polymarket");
    expect(fromBadge.freshness?.label).toBe("fresh");
  });

  it("keeps a missing figure visible as N/A instead of dropping it", () => {
    expect(captureMetric("ATM IV", null, null)).toEqual({ label: "ATM IV", display: "N/A", value: null });
    expect(captureMetric("Spot", "$612.40", 612.4, "USD")).toEqual({ label: "Spot", display: "$612.40", value: 612.4, unit: "USD" });
    expect(captureMetric("Bad", "x", Number.NaN).value).toBeNull();
  });
});

describe("ideas reading helpers", () => {
  it("groups evidence by stance, newest capture first", () => {
    const groups = groupEvidenceByStance([
      evidence({ evidence_id: "a", stance: "supports", captured_at: "2026-11-14T08:00:00" }),
      evidence({ evidence_id: "b", stance: "challenges" }),
      evidence({ evidence_id: "c", stance: "supports", captured_at: "2026-11-14T10:00:00" }),
    ]);
    expect(groups.supports.map((item) => item.evidence_id)).toEqual(["c", "a"]);
    expect(groups.challenges.map((item) => item.evidence_id)).toEqual(["b"]);
    expect(groups.context).toEqual([]);
  });

  it("labels the source place and compacts frozen values", () => {
    const envelope = buildReopenEnvelope({ tab: "prediction_markets", mode: "contract", entity: null, now: NOW });
    expect(handoffPlaceLabel(envelope)).toBe("Prediction Markets / Contract");
    expect(handoffPlaceLabel(buildReopenEnvelope({ tab: "sitrep", entity: null, now: NOW }))).toBe("Sitrep");
    expect(handoffPlaceLabel(null)).toBe("");

    const values = {
      metrics: Array.from({ length: 8 }, (_, index) => ({ label: `M${index}`, display: index === 2 ? null : `${index}%`, value: index })),
    };
    expect(capturedMetricPairs(values).map((pair) => pair.display)).toEqual(["0%", "1%", "2", "3%", "4%", "5%"]);
    expect(capturedValuesExtraCount(values)).toBe(2);
    expect(capturedMetricPairs({})).toEqual([]);
  });

  it("rebuilds badge data from a frozen pin", () => {
    expect(pinBadgeData(evidence({}))).toBeNull();
    const badge = pinBadgeData(
      evidence({
        provenance: { source_provider: "sample", retrieved_at: "2026-11-14T08:59:00", origin: "o", transformation_note: null },
        freshness: { label: "mocked", retrieved_at: null, source_timestamp: null, evaluated_at: null, age_seconds: null, ttl_seconds: null, is_stale: false, warnings: ["w"] },
      })
    );
    expect(badge).toMatchObject({ source_provider: "sample", freshness_label: "mocked", warnings: ["w"] });
  });

  it("formats legs, filters, tags and filenames", () => {
    expect(formatLegs([])).toBe("—");
    expect(formatLegs([{ label: "XOM", weight: 1 }, { label: "SPY", weight: -1 }, { label: "Brent", weight: null }])).toBe("XOM +1, SPY -1, Brent");
    expect(boardFilterStatuses("open")).toEqual(["draft", "active"]);
    expect(boardFilterStatuses("all")).toEqual([]);
    expect(boardFilterStatuses("archived")).toEqual(["archived"]);
    expect(parseTagInput(" Energy, refiners ,energy,, ")).toEqual(["energy", "refiners"]);
    expect(ideaExportFilename("Energy | Refiners beat SPY", "abc12345", "md")).toBe("idea-energy-refiners-beat-spy.md");
    expect(ideaExportFilename("***", "abc12345xyz", "json")).toBe("idea-abc12345.json");
  });
});

describe("Sitrep promote", () => {
  const followUp: SitrepFollowUp = {
    id: "fu-1",
    row_id: "commodities-brent",
    source: "Commodities",
    tone: "positive",
    title: "Brent +3.2% over 1W",
    detail: "Front month 84.10",
    meta: "",
    note: "Check refiners.",
    status: "open",
    handoff: { targetTab: "commodities", targetMode: "energy", commodityId: "BRENT", label: "Brent" },
    saved_at: "2026-11-14T08:00:00",
  };

  it("carries the title, note and handoff across without touching the follow-up", () => {
    const payload = buildPromotePayload(followUp);
    expect(payload.title).toBe("Brent +3.2% over 1W");
    expect(payload.notes).toBe("Check refiners.");
    expect(payload.origin).toMatchObject({ kind: "sitrep_follow_up", source_ref: "fu-1", label: "Brent +3.2% over 1W · Front month 84.10" });
    expect(payload.origin?.handoff).toMatchObject({
      source_tab: "sitrep",
      intended_target_tab: "commodities",
      intended_target_mode: "energy",
      normalized_ids: { commodity_id: "BRENT" },
      selected_entity: { entity_type: "commodity", normalized_id: "BRENT", label: "Brent" },
    });
    expect(followUp.status).toBe("open");
  });

  it("converts an equity follow-up handoff and finds an existing promotion", () => {
    const envelope = sitrepHandoffToEnvelope({ targetTab: "equity_research", targetMode: "scope_analysis", symbol: "XOM", timeframe: "1Y" }, "XOM", NOW);
    expect(envelope.selected_entity?.entity_type).toBe("equity");
    expect(envelope.selected_timeframe?.label).toBe("1Y");
    expect(buildPromotePayload({ ...followUp, handoff: null }).origin?.handoff).toBeNull();

    const summaries = [
      { idea_id: "i1", origin_kind: "manual", origin_ref: null },
      { idea_id: "i2", origin_kind: "sitrep_follow_up", origin_ref: "fu-1" },
    ] as IdeaSummary[];
    expect(findPromotedIdea(summaries, "fu-1")?.idea_id).toBe("i2");
    expect(findPromotedIdea(summaries, "fu-2")).toBeNull();
  });
});
