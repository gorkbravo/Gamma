// Ideas (Workstream 12, checkpoint I1): pure helpers shared by the Ideas tab,
// the shared Pin to idea action and Sitrep's "Promote to idea".
//
// A pin stores what the user saw: the values on screen, the provenance the
// panel showed and a handoff envelope that reopens the same tab, mode, entity
// and lens. Nothing here fetches, evaluates or tracks anything.

import type {
  CrossTabHandoffEnvelope,
  IdeaCapturedMetric,
  IdeaCapturedValues,
  IdeaCreatePayload,
  IdeaEvidence,
  IdeaEvidenceStance,
  IdeaFreshnessRecord,
  IdeaJournalKind,
  IdeaLeg,
  IdeaProvenanceRecord,
  IdeaStance,
  IdeaStatus,
  IdeaSummary,
  TabId,
} from "./api/types";
import { getTabLabel, getTabModes } from "./navigation";
import type { ProvenanceBadgeData, ProvenanceLike } from "./provenance";
import { apiInstantDate } from "./time";
import type { SitrepFollowUp, SitrepHandoffRequest } from "./view-models/sitrep";

export const IDEA_EVIDENCE_STANCES: readonly IdeaEvidenceStance[] = ["supports", "challenges", "context"];
export const IDEA_STANCES: readonly IdeaStance[] = ["long", "short", "relative", "event", "neutral"];

export const EVIDENCE_STANCE_LABELS: Record<IdeaEvidenceStance, string> = {
  supports: "Supports",
  challenges: "Challenges",
  context: "Context",
};

export const IDEA_STANCE_LABELS: Record<IdeaStance, string> = {
  long: "Long",
  short: "Short",
  relative: "Relative",
  event: "Event",
  neutral: "Neutral",
};

export const IDEA_STATUS_LABELS: Record<IdeaStatus, string> = {
  draft: "Draft",
  active: "Active",
  closed: "Closed",
  archived: "Archived",
};

const JOURNAL_KIND_LABELS: Record<IdeaJournalKind, string> = {
  note: "Note",
  decision: "Decision",
  created: "Created",
  edited: "Edited",
  status_changed: "Status",
  evidence_pinned: "Pinned",
  evidence_unpinned: "Unpinned",
  criterion_added: "Criterion",
  criterion_edited: "Criterion",
  criterion_removed: "Criterion",
  criterion_triggered: "Triggered",
  criterion_acknowledged: "Acknowledged",
};

/** Board filter presets; "open" is every idea that is neither archived nor closed. */
export type IdeaBoardFilter = "open" | "draft" | "active" | "archived" | "all";
export const IDEA_BOARD_FILTERS: ReadonlyArray<{ id: IdeaBoardFilter; label: string }> = [
  { id: "open", label: "Open" },
  { id: "draft", label: "Draft" },
  { id: "active", label: "Active" },
  { id: "archived", label: "Archived" },
  { id: "all", label: "All" },
];

export function boardFilterStatuses(filter: IdeaBoardFilter): IdeaStatus[] {
  if (filter === "open") return ["draft", "active"];
  if (filter === "all") return [];
  return [filter];
}

/** Tag tone for a lifecycle status: the active idea is the one that is live. */
export function ideaStatusTone(status: IdeaStatus): "" | "accent" {
  return status === "active" ? "accent" : "";
}

export function journalKindLabel(kind: IdeaJournalKind): string {
  return JOURNAL_KIND_LABELS[kind] ?? kind;
}

/** A local "YYYY-MM-DD HH:mm" for an API instant (naive UTC on the wire); "N/A" when absent. */
export function formatIdeaInstant(value: string | null | undefined): string {
  const date = apiInstantDate(value);
  if (!date) return "N/A";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// ── Capture ──────────────────────────────────────────────────────────────

/**
 * One frozen metric row. ``display`` is the string the panel showed (with its
 * units and precision); ``value`` keeps the raw number when there is one. A
 * missing value is kept as ``null`` with "N/A" so absence stays visible.
 */
export function captureMetric(
  label: string,
  display: string | null | undefined,
  value?: number | string | boolean | null,
  unit?: string | null
): IdeaCapturedMetric {
  const shown = display == null || display === "" ? "N/A" : display;
  const raw = typeof value === "number" && !Number.isFinite(value) ? null : value ?? null;
  return { label, display: shown, value: raw, ...(unit ? { unit } : {}) };
}

/** Build the handoff that reopens a pin's source tab and mode on the same entity and lens. */
export function buildReopenEnvelope(options: {
  tab: TabId;
  mode?: string | null;
  entity: { entity_type: string; label: string; normalized_id: string; metadata?: Record<string, unknown> } | null;
  timeframe?: string | null;
  normalizedIds?: Record<string, string | null | undefined>;
  provider?: string | null;
  warnings?: string[];
  now?: Date;
}): CrossTabHandoffEnvelope {
  const normalizedIds: Record<string, string> = {};
  for (const [key, value] of Object.entries(options.normalizedIds ?? {})) {
    const text = typeof value === "string" ? value.trim() : "";
    if (text) normalizedIds[key] = text;
  }
  return {
    source_tab: options.tab,
    source_mode: options.mode ?? null,
    selected_entity: options.entity
      ? {
          entity_type: options.entity.entity_type,
          label: options.entity.label,
          normalized_id: options.entity.normalized_id,
          provider_id: null,
          native_id: null,
          metadata: { ...(options.entity.metadata ?? {}) },
        }
      : null,
    selected_timeframe: options.timeframe ? { label: options.timeframe, start: null, end: null } : null,
    provider: options.provider ?? null,
    source: null,
    warnings: [...(options.warnings ?? [])].slice(0, 10),
    normalized_ids: normalizedIds,
    timestamp: (options.now ?? new Date()).toISOString(),
    intended_target_tab: options.tab,
    intended_target_mode: options.mode ?? null,
  };
}

export interface PinSource {
  provenance: IdeaProvenanceRecord | null;
  freshness: Partial<IdeaFreshnessRecord> | null;
}

/**
 * Freeze a panel's provenance as the pin's ProvenanceRecord/FreshnessRecord.
 * A record needs a provider and a retrieval time; without them the pin keeps
 * only the freshness label and warnings rather than inventing a source.
 */
export function pinSourceFromProvenance(source: ProvenanceLike | null | undefined, origin: string): PinSource {
  if (!source) return { provenance: null, freshness: null };
  const provider = (source.source_provider ?? source.provider ?? "").trim();
  const retrievedAt = (source.retrieved_at ?? "").trim();
  const freshnessLabel =
    source.freshness_label ??
    (typeof source.freshness === "string" ? source.freshness : source.freshness?.status ?? null);
  return {
    provenance:
      provider && retrievedAt
        ? {
            source_provider: provider,
            retrieved_at: retrievedAt,
            origin,
            transformation_note: source.transformation_note ?? null,
          }
        : null,
    freshness: {
      label: freshnessLabel ?? "unknown",
      retrieved_at: retrievedAt || null,
      source_timestamp: source.source_timestamp ?? null,
      warnings: [...(source.warnings ?? [])].slice(0, 10),
    },
  };
}

/** The same, from the shared badge's normalized data. */
export function pinSourceFromBadge(badge: ProvenanceBadgeData | null | undefined, origin: string): PinSource {
  if (!badge) return { provenance: null, freshness: null };
  return pinSourceFromProvenance(
    {
      source_provider: badge.provider,
      retrieved_at: badge.retrievedAt,
      source_timestamp: badge.sourceTimestamp,
      freshness_label: badge.rawLabel ?? badge.state,
      transformation_note: badge.transformationNote,
      warnings: badge.warnings,
    },
    origin
  );
}

/** Rebuild the badge data a frozen pin carries, so it renders through the shared ProvenanceBadge. */
export function pinBadgeData(evidence: IdeaEvidence): ProvenanceLike | null {
  if (!evidence.provenance && !evidence.freshness) return null;
  return {
    source_provider: evidence.provenance?.source_provider ?? null,
    retrieved_at: evidence.provenance?.retrieved_at ?? evidence.freshness?.retrieved_at ?? null,
    source_timestamp: evidence.freshness?.source_timestamp ?? null,
    freshness_label: evidence.freshness?.label ?? null,
    transformation_note: evidence.provenance?.transformation_note ?? null,
    warnings: evidence.freshness?.warnings ?? [],
  };
}

// ── Reading pins ─────────────────────────────────────────────────────────

export function groupEvidenceByStance(evidence: IdeaEvidence[]): Record<IdeaEvidenceStance, IdeaEvidence[]> {
  const groups: Record<IdeaEvidenceStance, IdeaEvidence[]> = { supports: [], challenges: [], context: [] };
  for (const item of evidence) {
    groups[item.stance]?.push(item);
  }
  for (const stance of IDEA_EVIDENCE_STANCES) {
    groups[stance].sort((left, right) => right.captured_at.localeCompare(left.captured_at));
  }
  return groups;
}

function modeLabel(tab: string, mode: string | null | undefined): string | null {
  if (!mode) return null;
  const match = getTabModes(tab as TabId).find((candidate) => candidate.id === mode);
  return match?.label ?? mode.replace(/_/g, " ");
}

/** "Fundamentals / Overview" for the tab and mode a handoff names. */
export function handoffPlaceLabel(envelope: CrossTabHandoffEnvelope | null, side: "source" | "target" = "source"): string {
  if (!envelope) return "";
  const tab = side === "source" ? envelope.source_tab : envelope.intended_target_tab;
  const mode = side === "source" ? envelope.source_mode : envelope.intended_target_mode;
  const tabLabel = getTabLabel(tab as TabId);
  const modeText = modeLabel(tab, mode);
  return modeText ? `${tabLabel} / ${modeText}` : tabLabel;
}

/** Compact "label value" pairs for a pin's frozen metrics, in capture order. */
export function capturedMetricPairs(values: IdeaCapturedValues, limit = 6): Array<{ label: string; display: string }> {
  const metrics = Array.isArray(values?.metrics) ? values.metrics : [];
  return metrics.slice(0, limit).map((metric) => ({
    label: String(metric.label ?? "Value"),
    display:
      metric.display != null && metric.display !== ""
        ? String(metric.display)
        : metric.value == null
          ? "N/A"
          : `${metric.value}${metric.unit ? ` ${metric.unit}` : ""}`,
  }));
}

export function capturedValuesExtraCount(values: IdeaCapturedValues, limit = 6): number {
  const metrics = Array.isArray(values?.metrics) ? values.metrics.length : 0;
  return Math.max(0, metrics - limit);
}

export function formatLegs(legs: Array<{ label: string; weight: number | null }>): string {
  if (!legs.length) return "—";
  return legs
    .map((leg) => (leg.weight == null ? leg.label : `${leg.label} ${leg.weight > 0 ? "+" : ""}${leg.weight}`))
    .join(", ");
}

export function legFromEntity(
  entity: { entity_type: string; label: string; normalized_id: string },
  weight: number | null = null
): IdeaLeg {
  return {
    entity: {
      entity_type: entity.entity_type,
      label: entity.label,
      normalized_id: entity.normalized_id,
      provider_id: null,
      native_id: null,
      metadata: {},
    },
    weight,
  };
}

export function ideaExportFilename(title: string, ideaId: string, format: "md" | "json"): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
  return `idea-${slug || ideaId.slice(0, 8)}.${format}`;
}

/** Parse a comma-separated tag field the way the backend normalizes tags. */
export function parseTagInput(value: string): string[] {
  const tags: string[] = [];
  for (const raw of value.split(",")) {
    const tag = raw.trim().replace(/\s+/g, " ").toLowerCase();
    if (tag && !tags.includes(tag)) tags.push(tag);
  }
  return tags;
}

// ── Sitrep promote ───────────────────────────────────────────────────────

/** Convert a Sitrep follow-up's handoff into the shared envelope an idea keeps. */
export function sitrepHandoffToEnvelope(
  handoff: SitrepHandoffRequest,
  label: string,
  now: Date = new Date()
): CrossTabHandoffEnvelope {
  const entityId = handoff.symbol ?? handoff.marketId ?? handoff.commodityId ?? null;
  const entityType = handoff.symbol
    ? "equity"
    : handoff.marketId
      ? "prediction_market"
      : handoff.commodityId
        ? "commodity"
        : null;
  const envelope = buildReopenEnvelope({
    tab: handoff.targetTab,
    mode: handoff.targetMode ?? null,
    entity: entityId && entityType ? { entity_type: entityType, label: handoff.label ?? label, normalized_id: entityId } : null,
    timeframe: handoff.timeframe ?? null,
    normalizedIds: {
      symbol: handoff.symbol,
      market_id: handoff.marketId,
      commodity_id: handoff.commodityId,
      region: handoff.region,
      theme: handoff.theme,
      timeframe: handoff.timeframe,
    },
    now,
  });
  return { ...envelope, source_tab: "sitrep", source_mode: null };
}

/** The create payload for "Promote to idea": title, note and handoff carried across. */
export function buildPromotePayload(followUp: SitrepFollowUp): IdeaCreatePayload {
  return {
    title: followUp.title.slice(0, 200),
    notes: followUp.note ?? "",
    stance: "neutral",
    origin: {
      kind: "sitrep_follow_up",
      source_ref: followUp.id,
      label: [followUp.title, followUp.detail].filter(Boolean).join(" · ").slice(0, 300),
      handoff: followUp.handoff ? sitrepHandoffToEnvelope(followUp.handoff, followUp.title) : null,
    },
  };
}

export function findPromotedIdea(summaries: IdeaSummary[], followUpId: string): IdeaSummary | null {
  return summaries.find((item) => item.origin_kind === "sitrep_follow_up" && item.origin_ref === followUpId) ?? null;
}
