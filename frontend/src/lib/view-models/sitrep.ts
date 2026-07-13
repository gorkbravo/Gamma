import type { CommodityMode, MacroMode, TabId } from "../api/types";

export type SitrepMarketHandoffProfile =
  | "default"
  | "equities"
  | "indices"
  | "fx"
  | "yields"
  | "commodities";

export interface SitrepHandoffRequest {
  targetTab: TabId;
  targetMode?: string;
  symbol?: string | null;
  label?: string | null;
  marketId?: string | null;
  commodityId?: string | null;
}

export interface SitrepMarketHandoffRow {
  id: string;
  symbol?: string | null;
  proxySymbol?: string | null;
  proxyLabel?: string | null;
  label: string;
  selectionLabel?: string | null;
  group: string;
  last: string;
  change: string;
  secondary: string;
}

export interface SitrepTapeHandoffRow {
  id: string;
  source: string;
  tone: string;
  title: string;
  detail: string;
  meta: string;
  handoff?: SitrepHandoffRequest | null;
}

export function resolveSitrepMarketHandoff(
  profile: SitrepMarketHandoffProfile,
  row: SitrepMarketHandoffRow
): SitrepHandoffRequest | null {
  if (profile === "equities") {
    const symbol = (row.symbol ?? row.label).trim();
    return symbol
      ? {
          targetTab: "equity_research",
          targetMode: "scope_analysis",
          symbol,
          label: row.selectionLabel ?? row.label,
        }
      : null;
  }

  if (profile === "indices") {
    const symbol = (row.proxySymbol ?? "").trim().toUpperCase();
    return symbol
      ? {
          targetTab: "equity_research",
          targetMode: "scope_analysis",
          symbol,
          label: row.proxyLabel ?? `${row.label} proxy`,
        }
      : { targetTab: "equity_research", targetMode: "overview" };
  }

  if (profile === "fx") {
    return { targetTab: "macro", targetMode: "snapshot" satisfies MacroMode };
  }

  if (profile === "yields") {
    return { targetTab: "macro", targetMode: "rates_policy" satisfies MacroMode };
  }

  if (profile === "commodities") {
    return {
      targetTab: "commodities",
      targetMode: commodityModeForGroup(row.group),
      commodityId: row.id,
    };
  }

  return null;
}

export function resolveSitrepTapeHandoff(row: SitrepTapeHandoffRow): SitrepHandoffRequest | null {
  return row.handoff ?? null;
}

/** Aggregate metadata from the single /sitrep/workspace load (section list + degradation warnings). */
export interface SitrepWorkspaceMeta {
  retrieved_at: string;
  sections: string[];
  section_warnings: string[];
}

export type SitrepFollowUpStatus = "open" | "resolved";

export interface SitrepFollowUp {
  /** Backend store id (uuid). Legacy localStorage entries reuse the row id until migrated. */
  id: string;
  /** Stable triage-row id used to match the originating What Changed / Events row. */
  row_id: string;
  source: string;
  tone: string;
  title: string;
  detail: string;
  meta: string;
  note: string;
  status: SitrepFollowUpStatus;
  handoff: SitrepHandoffRequest | null;
  saved_at: string;
  resolved_at?: string | null;
}

export const SITREP_FOLLOW_UP_STORAGE_KEY = "gamma.sitrep.follow_ups.v1";
export const SITREP_FOLLOW_UP_MIGRATED_STORAGE_KEY = "gamma.sitrep.follow_ups.v1.migrated";
export const SITREP_FOLLOW_UP_LIMIT = 48;

export function isSitrepFollowUpSaved(followUps: SitrepFollowUp[], rowId: string): boolean {
  return followUps.some((item) => item.row_id === rowId);
}

export function findSitrepFollowUpByRow(
  followUps: SitrepFollowUp[],
  rowId: string
): SitrepFollowUp | null {
  return followUps.find((item) => item.row_id === rowId) ?? null;
}

export function removeSitrepFollowUp(followUps: SitrepFollowUp[], id: string): SitrepFollowUp[] {
  return followUps.filter((item) => item.id !== id);
}

export interface SitrepFollowUpCreatePayload {
  row_id: string;
  title: string;
  source: string;
  tone: string;
  detail: string;
  meta: string;
  note?: string;
  handoff: SitrepHandoffRequest | null;
  saved_at?: string;
}

export function buildSitrepFollowUpCreatePayload(row: SitrepTapeHandoffRow): SitrepFollowUpCreatePayload {
  return {
    row_id: row.id,
    title: row.title,
    source: row.source,
    tone: row.tone,
    detail: row.detail,
    meta: row.meta,
    handoff: row.handoff ?? null,
  };
}

/** Parses the legacy localStorage payload so pre-backend follow-ups can be migrated. */
export function parseSitrepFollowUps(raw: string | null | undefined): SitrepFollowUp[] {
  if (!raw) {
    return [];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) {
    return [];
  }
  const items: SitrepFollowUp[] = [];
  for (const candidate of parsed) {
    const entry = coerceFollowUp(candidate);
    if (entry && !items.some((item) => item.row_id === entry.row_id)) {
      items.push(entry);
    }
    if (items.length >= SITREP_FOLLOW_UP_LIMIT) {
      break;
    }
  }
  return items;
}

function coerceFollowUp(candidate: unknown): SitrepFollowUp | null {
  if (typeof candidate !== "object" || candidate === null) {
    return null;
  }
  const record = candidate as Record<string, unknown>;
  if (typeof record.id !== "string" || !record.id.trim() || typeof record.title !== "string" || !record.title.trim()) {
    return null;
  }
  const rowId = typeof record.row_id === "string" && record.row_id.trim() ? record.row_id : record.id;
  return {
    id: record.id,
    row_id: rowId,
    source: typeof record.source === "string" ? record.source : "",
    tone: typeof record.tone === "string" ? record.tone : "neutral",
    title: record.title,
    detail: typeof record.detail === "string" ? record.detail : "",
    meta: typeof record.meta === "string" ? record.meta : "",
    note: typeof record.note === "string" ? record.note : "",
    status: record.status === "resolved" ? "resolved" : "open",
    handoff: coerceFollowUpHandoff(record.handoff),
    saved_at: typeof record.saved_at === "string" ? record.saved_at : new Date(0).toISOString(),
    resolved_at: typeof record.resolved_at === "string" ? record.resolved_at : null,
  };
}

function coerceFollowUpHandoff(candidate: unknown): SitrepHandoffRequest | null {
  if (typeof candidate !== "object" || candidate === null) {
    return null;
  }
  const record = candidate as Record<string, unknown>;
  if (typeof record.targetTab !== "string" || !record.targetTab.trim()) {
    return null;
  }
  return {
    targetTab: record.targetTab as TabId,
    targetMode: typeof record.targetMode === "string" ? record.targetMode : undefined,
    symbol: typeof record.symbol === "string" ? record.symbol : null,
    label: typeof record.label === "string" ? record.label : null,
    marketId: typeof record.marketId === "string" ? record.marketId : null,
    commodityId: typeof record.commodityId === "string" ? record.commodityId : null,
  };
}

export function formatSitrepWindowLabel(base: string, timeframe: string | null | undefined): string {
  const window = (timeframe ?? "").trim().toUpperCase();
  return window ? `${base} (${window})` : base;
}

function commodityModeForGroup(group: string): CommodityMode {
  const normalized = group.trim().toLowerCase();
  if (normalized.includes("energy")) {
    return "energy";
  }
  if (normalized.includes("metal")) {
    return "metals";
  }
  return "overview";
}
