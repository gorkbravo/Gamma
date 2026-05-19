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
    return { targetTab: "equity_research", targetMode: "overview" };
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
