import type { CommodityMode, MacroMode, SitrepWorkspaceResponse, TabId } from "../api/types";

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
  timeframe?: string | null;
  region?: string | null;
  theme?: string | null;
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
  timeframe?: string | null;
  region?: string | null;
  theme?: string | null;
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
          timeframe: row.timeframe ?? "1Y",
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
          timeframe: row.timeframe ?? "1Y",
        }
      : { targetTab: "equity_research", targetMode: "overview" };
  }

  if (profile === "fx") {
    return {
      targetTab: "macro",
      targetMode: "snapshot" satisfies MacroMode,
      timeframe: row.timeframe ?? "3M",
      region: row.region ?? "US",
      theme: row.theme ?? "all",
    };
  }

  if (profile === "yields") {
    return {
      targetTab: "macro",
      targetMode: "rates_policy" satisfies MacroMode,
      timeframe: row.timeframe ?? "3M",
      region: row.region ?? "US",
      theme: row.theme ?? "all",
    };
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

/**
 * Metadatos agregados de /sitrep/workspace (secciones + avisos de degradación). Desde
 * GUA-20261021-12 cada sección es una petición concurrente y esto se combina sección a
 * sección según responde cada proveedor.
 */
export interface SitrepWorkspaceMeta {
  retrieved_at: string;
  /** Secciones que ya han respondido (con datos o con una degradación del backend). */
  sections: string[];
  section_warnings: string[];
  /** Secciones aún en vuelo durante la carga progresiva (GUA-20261021-12). */
  pending_sections?: string[];
}

/** Ids de sección del contrato, en el orden de SITREP_SECTIONS (src/application/sitrep_service.py). */
export const SITREP_WORKSPACE_SECTIONS = [
  "equities",
  "indices",
  "macro",
  "commodities",
  "prediction_markets",
  "news",
] as const;

export type SitrepWorkspaceSection = (typeof SITREP_WORKSPACE_SECTIONS)[number];

const SITREP_SECTION_FIELDS: Record<SitrepWorkspaceSection, keyof SitrepWorkspaceResponse> = {
  equities: "equities_overview",
  indices: "indices_overview",
  macro: "macro_snapshot",
  commodities: "commodities",
  prediction_markets: "prediction_markets",
  news: "news",
};

/** Secciones conocidas en orden de contrato; vacío o solo desconocidas equivale a todas. */
export function normalizeSitrepWorkspaceSections(sections?: readonly string[] | null): SitrepWorkspaceSection[] {
  const requested = new Set((sections ?? []).map((section) => section.trim().toLowerCase()));
  const known = SITREP_WORKSPACE_SECTIONS.filter((section) => requested.has(section));
  return known.length ? known : [...SITREP_WORKSPACE_SECTIONS];
}

/** Mismo texto que el aviso de degradación por sección del backend. */
export function sitrepSectionFailureWarning(section: string, message: string): string {
  return `SITREP section '${section}' failed to load: ${message}`;
}

function warningBelongsToSection(warning: string, section: string): boolean {
  return warning.startsWith(`SITREP section '${section}'`);
}

/** True si la última carga de la sección falló (aviso del backend o error HTTP). */
export function sitrepSectionFailed(meta: SitrepWorkspaceMeta | null | undefined, section: string): boolean {
  return Boolean(meta?.section_warnings.some((warning) => warningBelongsToSection(warning, section)));
}

export interface SitrepSectionOutcome {
  section: SitrepWorkspaceSection;
  response?: SitrepWorkspaceResponse | null;
  /** Fallo de transporte de esta sección; las demás no se ven afectadas. */
  error?: string | null;
}

function latestTimestamp(left: string | null | undefined, right: string | null | undefined): string | null {
  const leftMillis = left ? Date.parse(left) : Number.NaN;
  const rightMillis = right ? Date.parse(right) : Number.NaN;
  if (!Number.isFinite(rightMillis)) return Number.isFinite(leftMillis) ? left ?? null : right ?? left ?? null;
  if (!Number.isFinite(leftMillis)) return right ?? null;
  return rightMillis >= leftMillis ? right ?? null : left ?? null;
}

/**
 * Incorpora la respuesta de una sección: sustituye sus avisos anteriores y conserva los de
 * las demás, así un proveedor que falla queda aislado en su fila (GUA-20261021-12).
 */
export function mergeSitrepSectionMeta(
  previous: SitrepWorkspaceMeta | null,
  outcome: SitrepSectionOutcome,
  pendingSections: readonly string[] = []
): SitrepWorkspaceMeta {
  const { section } = outcome;
  const response = outcome.response ?? null;
  const warnings = (previous?.section_warnings ?? []).filter((warning) => !warningBelongsToSection(warning, section));
  if (response) {
    warnings.push(...response.section_warnings.filter((warning) => warningBelongsToSection(warning, section)));
  }
  if (outcome.error) {
    warnings.push(sitrepSectionFailureWarning(section, outcome.error));
  }
  const answered = new Set((previous?.sections ?? []).filter((item) => item !== section));
  if (response) answered.add(section);
  return {
    retrieved_at:
      latestTimestamp(previous?.retrieved_at, response?.retrieved_at) ?? previous?.retrieved_at ?? new Date().toISOString(),
    sections: SITREP_WORKSPACE_SECTIONS.filter((item) => answered.has(item)),
    section_warnings: warnings,
    pending_sections: SITREP_WORKSPACE_SECTIONS.filter((item) => pendingSections.includes(item)),
  };
}

/** Recompone el payload agregado a partir de las respuestas por sección (null si ninguna respondió). */
export function composeSitrepWorkspace(
  responses: Partial<Record<SitrepWorkspaceSection, SitrepWorkspaceResponse>>,
  meta: SitrepWorkspaceMeta | null
): SitrepWorkspaceResponse | null {
  const answered = SITREP_WORKSPACE_SECTIONS.filter((section) => responses[section]);
  if (!answered.length) return null;
  const first = responses[answered[0]] as SitrepWorkspaceResponse;
  const composed: SitrepWorkspaceResponse = {
    equities_overview: null,
    indices_overview: null,
    macro_snapshot: null,
    commodities: null,
    prediction_markets: null,
    news: null,
    sections: [...answered],
    section_warnings: meta?.section_warnings ?? answered.flatMap((section) => responses[section]?.section_warnings ?? []),
    source_provider: first.source_provider,
    retrieved_at: meta?.retrieved_at ?? first.retrieved_at,
    origin: first.origin,
    transformation_note: first.transformation_note,
  };
  for (const section of answered) {
    const field = SITREP_SECTION_FIELDS[section];
    (composed as unknown as Record<string, unknown>)[field] = responses[section]?.[field] ?? null;
  }
  return composed;
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
    timeframe: typeof record.timeframe === "string" ? record.timeframe : null,
    region: typeof record.region === "string" ? record.region : null,
    theme: typeof record.theme === "string" ? record.theme : null,
  };
}

export interface SitrepSectionClock {
  id: string;
  label: string;
  retrievedAt: string | null | undefined;
}

export interface SitrepOldestSection {
  id: string;
  label: string;
  retrievedAt: string;
}

/** Returns the oldest valid loaded section timestamp; unloaded/invalid sections are ignored. */
export function oldestSitrepSection(sections: SitrepSectionClock[]): SitrepOldestSection | null {
  let oldest: SitrepOldestSection | null = null;
  let oldestMillis = Number.POSITIVE_INFINITY;
  for (const section of sections) {
    if (!section.retrievedAt) continue;
    const millis = Date.parse(section.retrievedAt);
    if (!Number.isFinite(millis) || millis >= oldestMillis) continue;
    oldestMillis = millis;
    oldest = { id: section.id, label: section.label, retrievedAt: section.retrievedAt };
  }
  return oldest;
}

export function formatSitrepSectionAge(
  retrievedAt: string | null | undefined,
  now: Date = new Date()
): string {
  if (!retrievedAt) return "N/A";
  const millis = Date.parse(retrievedAt);
  if (!Number.isFinite(millis)) return "N/A";
  const minutes = Math.max(0, Math.floor((now.getTime() - millis) / 60_000));
  if (minutes < 1) return "<1m old";
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h old`;
  return `${Math.floor(hours / 24)}d old`;
}

export interface SitrepNewsEntityLike {
  label: string;
  entity_type: string;
  symbol?: string | null;
}

/**
 * Routes a detected news ticker/company/index entity into Equity Research
 * scope analysis. Non-listed entity types (central banks, regulators,
 * crypto assets, chokepoints) have no equity scope and return null.
 */
export function resolveSitrepNewsEntityHandoff(entity: SitrepNewsEntityLike): SitrepHandoffRequest | null {
  const symbol = (entity.symbol ?? "").trim().toUpperCase();
  if (!symbol) {
    return null;
  }
  const entityType = (entity.entity_type ?? "").trim().toLowerCase();
  if (!["company", "ticker", "index", "etf", "equity"].includes(entityType)) {
    return null;
  }
  return {
    targetTab: "equity_research",
    targetMode: "scope_analysis",
    symbol,
    label: entity.label || symbol,
    timeframe: "1Y",
  };
}

const NEWS_RELIABILITY_LABELS: Record<string, string> = {
  official: "OFFICIAL",
  major_outlet: "OUTLET",
  aggregator: "AGGR",
  sample: "SAMPLE",
};

/** Compact per-source reliability label; unknown reliability renders nothing. */
export function formatNewsReliabilityLabel(value: string | null | undefined): string {
  return NEWS_RELIABILITY_LABELS[(value ?? "").trim().toLowerCase()] ?? "";
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
