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

export interface SitrepFollowUp {
  id: string;
  source: string;
  tone: string;
  title: string;
  detail: string;
  meta: string;
  handoff: SitrepHandoffRequest | null;
  saved_at: string;
}

export const SITREP_FOLLOW_UP_STORAGE_KEY = "gamma.sitrep.follow_ups.v1";
export const SITREP_FOLLOW_UP_LIMIT = 24;

export function isSitrepFollowUpSaved(followUps: SitrepFollowUp[], id: string): boolean {
  return followUps.some((item) => item.id === id);
}

export function toggleSitrepFollowUp(
  followUps: SitrepFollowUp[],
  row: SitrepTapeHandoffRow,
  savedAt: string = new Date().toISOString()
): SitrepFollowUp[] {
  if (isSitrepFollowUpSaved(followUps, row.id)) {
    return removeSitrepFollowUp(followUps, row.id);
  }
  const entry: SitrepFollowUp = {
    id: row.id,
    source: row.source,
    tone: row.tone,
    title: row.title,
    detail: row.detail,
    meta: row.meta,
    handoff: row.handoff ?? null,
    saved_at: savedAt,
  };
  return [entry, ...followUps].slice(0, SITREP_FOLLOW_UP_LIMIT);
}

export function removeSitrepFollowUp(followUps: SitrepFollowUp[], id: string): SitrepFollowUp[] {
  return followUps.filter((item) => item.id !== id);
}

export function serializeSitrepFollowUps(followUps: SitrepFollowUp[]): string {
  return JSON.stringify(followUps.slice(0, SITREP_FOLLOW_UP_LIMIT));
}

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
    if (entry && !items.some((item) => item.id === entry.id)) {
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
  return {
    id: record.id,
    source: typeof record.source === "string" ? record.source : "",
    tone: typeof record.tone === "string" ? record.tone : "neutral",
    title: record.title,
    detail: typeof record.detail === "string" ? record.detail : "",
    meta: typeof record.meta === "string" ? record.meta : "",
    handoff: coerceFollowUpHandoff(record.handoff),
    saved_at: typeof record.saved_at === "string" ? record.saved_at : new Date(0).toISOString(),
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
