import type {
  CrossTabHandoffEnvelope,
  MaritimeChokepointDefinition,
  MaritimeChokepointSummary,
  MaritimeCoverageMetadata,
  MaritimeMode,
  MaritimeWorkspaceResponse
} from "../api/types";

/*
 * Recepción de handoffs en Sealanes (GUA-20261021-7).
 *
 * Cualquier pestaña que quiera "abrir Sealanes enfocado en X" construye un
 * MaritimeFocusRequest (directamente o desde un CrossTabHandoffEnvelope con
 * intended_target_tab "maritime"). La vista lo resuelve contra la geografía
 * estática que devuelve /maritime/workspace; un destino desconocido produce un
 * mensaje explícito en lugar de la vista por defecto en silencio.
 */

export const MARITIME_MODE_IDS: readonly MaritimeMode[] = [
  "live_map",
  "chokepoints",
  "trade_flows",
  "fleet_monitoring",
  "event_replay"
];

export interface MaritimeFocusRequest {
  /** Token creciente: el mismo destino vuelve a enfocarse en un handoff repetido. */
  requestId: number;
  sourceTab: string | null;
  /** Modo de Sealanes que pide el emisor ("chokepoints" cuando nombra un chokepoint). */
  lens: MaritimeMode;
  /** Id normalizado del chokepoint (p. ej. "hormuz") si el emisor lo resolvió. */
  chokepointId: string | null;
  /** Entidad tal y como la nombra el emisor (p. ej. "Strait of Hormuz"). */
  entityLabel: string | null;
  entityType: string | null;
  /** Opcional: enfoca el grupo de chokepoints que transportan estas materias primas. */
  commodityLinks: string[];
}

export interface MaritimeFocusRequestInput {
  requestId?: number;
  sourceTab?: string | null;
  lens?: string | null;
  chokepointId?: string | null;
  entityLabel?: string | null;
  entityType?: string | null;
  commodityLinks?: string[] | null;
}

/** [[oeste, sur], [este, norte]] en el orden que espera MapLibre fitBounds. */
export type MaritimeLngLatBounds = [[number, number], [number, number]];

interface MaritimeFocusBase {
  requestId: number;
  mode: MaritimeMode;
  title: string;
  sourceLabel: string | null;
}

export interface MaritimeFocusResolved extends MaritimeFocusBase {
  status: "resolved";
  chokepointIds: string[];
  bounds: MaritimeLngLatBounds;
  /** Nota corta de cobertura AIS, p. ej. "0 AIS positions in the last 6 s sample · AISstream coverage varies by region". */
  note: string;
}

export interface MaritimeFocusUnresolved extends MaritimeFocusBase {
  status: "unresolved";
  message: string;
}

export type MaritimeFocusResolution = MaritimeFocusResolved | MaritimeFocusUnresolved;

const SOURCE_LABELS: Record<string, string> = {
  prediction_markets: "Prediction Markets",
  commodities: "Commodities",
  copilot: "Copilot",
  macro: "Macro",
  sitrep: "SITREP"
};

const NON_LIVE_STATUSES = new Set(["sample", "mock", "historical"]);

let focusSequence = 0;

export function nextMaritimeFocusRequestId() {
  focusSequence += 1;
  return focusSequence;
}

function cleanText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeLens(value: unknown, fallback: MaritimeMode): MaritimeMode {
  const text = cleanText(value)?.toLowerCase().replace(/[\s-]+/g, "_");
  return text && (MARITIME_MODE_IDS as readonly string[]).includes(text) ? (text as MaritimeMode) : fallback;
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(cleanText).filter((item): item is string => item !== null);
  }
  const text = cleanText(value);
  return text ? text.split(",").map((item) => item.trim()).filter(Boolean) : [];
}

export function buildMaritimeFocusRequest(input: MaritimeFocusRequestInput): MaritimeFocusRequest {
  const chokepointId = cleanText(input.chokepointId);
  return {
    requestId: input.requestId ?? nextMaritimeFocusRequestId(),
    sourceTab: cleanText(input.sourceTab),
    lens: normalizeLens(input.lens, chokepointId ? "chokepoints" : "live_map"),
    chokepointId,
    entityLabel: cleanText(input.entityLabel),
    entityType: cleanText(input.entityType),
    commodityLinks: stringList(input.commodityLinks)
  };
}

/** Traduce un CrossTabHandoffEnvelope dirigido a Sealanes; null si el destino es otra pestaña. */
export function maritimeFocusFromHandoff(
  handoff: CrossTabHandoffEnvelope,
  requestId?: number
): MaritimeFocusRequest | null {
  if (String(handoff.intended_target_tab ?? "") !== "maritime") return null;
  const entity = handoff.selected_entity;
  const ids = handoff.normalized_ids ?? {};
  const metadata = entity?.metadata ?? {};
  const chokepointId =
    cleanText(ids.chokepoint_id) ??
    (entity?.entity_type === "maritime_chokepoint" ? cleanText(entity.normalized_id) : null);
  return buildMaritimeFocusRequest({
    requestId,
    sourceTab: cleanText(handoff.source_tab),
    lens: handoff.intended_target_mode ?? cleanText(metadata.lens),
    chokepointId,
    entityLabel: cleanText(entity?.label),
    entityType: cleanText(entity?.entity_type),
    commodityLinks: stringList(metadata.commodity_links ?? ids.commodity_links)
  });
}

function normalizeKey(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

/** "Strait of Hormuz" → "hormuz", "Suez Canal" → "suez": el nombre propio sin el tipo de paso. */
function coreKey(value: string) {
  return normalizeKey(value)
    .replace(/^(the )?(strait|straits|canal|gulf) of /, "")
    .replace(/ (strait|straits|canal)$/, "")
    .trim();
}

function chokepointKeys(chokepoint: MaritimeChokepointDefinition) {
  return new Set(
    [chokepoint.chokepoint_id, chokepoint.name].flatMap((value) => [normalizeKey(value), coreKey(value)]).filter(Boolean)
  );
}

/** Busca por id y luego por nombre; una coincidencia ambigua no se resuelve. */
export function findMaritimeChokepoint(
  chokepoints: MaritimeChokepointDefinition[],
  chokepointId: string | null,
  entityLabel: string | null
): MaritimeChokepointDefinition | null {
  if (chokepointId) {
    const idKey = normalizeKey(chokepointId);
    const byId = chokepoints.find((item) => normalizeKey(item.chokepoint_id) === idKey);
    if (byId) return byId;
  }
  for (const candidate of [chokepointId, entityLabel]) {
    if (!candidate) continue;
    const keys = [normalizeKey(candidate), coreKey(candidate)];
    const exact = chokepoints.find((item) => keys.some((key) => key && chokepointKeys(item).has(key)));
    if (exact) return exact;
  }
  if (!entityLabel) return null;
  // Frase contenida ("Strait of Hormuz traffic…"), solo si señala un único chokepoint.
  const haystack = ` ${normalizeKey(entityLabel)} `;
  const contained = chokepoints.filter((item) => {
    const core = coreKey(item.name);
    return core.length >= 4 && haystack.includes(` ${core} `);
  });
  return contained.length === 1 ? contained[0] : null;
}

function clamp(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}

/** Caja de enfoque con margen para que el chokepoint no quede pegado al borde. */
export function chokepointFocusBounds(chokepoints: MaritimeChokepointDefinition[]): MaritimeLngLatBounds {
  const south = Math.min(...chokepoints.map((item) => item.bounding_box.min_latitude));
  const north = Math.max(...chokepoints.map((item) => item.bounding_box.max_latitude));
  const west = Math.min(...chokepoints.map((item) => item.bounding_box.min_longitude));
  const east = Math.max(...chokepoints.map((item) => item.bounding_box.max_longitude));
  const pad = Math.max(0.75, 0.35 * Math.max(north - south, east - west));
  return [
    [clamp(west - pad, -180, 180), clamp(south - pad, -85, 85)],
    [clamp(east + pad, -180, 180), clamp(north + pad, -85, 85)]
  ];
}

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** Nota de cobertura honesta: cuenta de la última muestra y límite del proveedor. */
export function maritimeCoverageNote(
  coverage: MaritimeCoverageMetadata | null | undefined,
  summaries: MaritimeChokepointSummary[],
  boxCount = summaries.length
): string {
  const total = summaries.reduce((sum, row) => sum + (row.total_vessel_count ?? 0), 0);
  const status = coverage?.coverage_status ?? "unavailable";
  const provider = coverage?.provider_label ?? "AIS provider";
  const scope = boxCount > 1 ? ` across ${boxCount} boxes` : "";
  if (NON_LIVE_STATUSES.has(status)) {
    return `${plural(total, `${status} position`)}${scope} · ${provider} is not live AIS`;
  }
  const window = coverage?.sample_window_seconds;
  if (window != null && window > 0) {
    return `${plural(total, "AIS position")}${scope} in the last ${window} s sample · ${provider} coverage varies by region`;
  }
  return `No live AIS sample was taken (${status}) · static chokepoint geography only`;
}

function sourceLabel(sourceTab: string | null) {
  return sourceTab ? SOURCE_LABELS[sourceTab] ?? sourceTab.replace(/_/g, " ") : null;
}

/**
 * Resuelve la petición contra el workspace cargado. Devuelve null mientras no
 * haya workspace (aún no se puede decidir si el destino existe).
 */
export function resolveMaritimeFocus(
  request: MaritimeFocusRequest | null | undefined,
  workspace: Pick<MaritimeWorkspaceResponse, "chokepoints" | "chokepoint_summaries" | "coverage"> | null | undefined
): MaritimeFocusResolution | null {
  if (!request || !workspace) return null;
  const chokepoints = workspace.chokepoints ?? [];
  const summaries = workspace.chokepoint_summaries ?? [];
  const base = { requestId: request.requestId, sourceLabel: sourceLabel(request.sourceTab) };

  const match = findMaritimeChokepoint(chokepoints, request.chokepointId, request.entityLabel);
  const commodities = new Set(request.commodityLinks.map((item) => item.toLowerCase()));
  const targets = match
    ? [match]
    : commodities.size
      ? chokepoints.filter((item) => item.strategic_commodities.some((commodity) => commodities.has(commodity.toLowerCase())))
      : [];

  if (targets.length) {
    const ids = targets.map((item) => item.chokepoint_id);
    const targetSummaries = summaries.filter((row) => ids.includes(row.chokepoint_id));
    return {
      ...base,
      status: "resolved",
      mode: request.lens === "live_map" ? "chokepoints" : request.lens,
      title: match ? match.name : request.entityLabel ?? `${targets.length} chokepoints`,
      chokepointIds: ids,
      bounds: chokepointFocusBounds(targets),
      note: maritimeCoverageNote(workspace.coverage, targetSummaries, targets.length)
    };
  }

  const named = request.entityLabel ?? request.chokepointId;
  const subject = named ? `"${named}"` : "The handoff";
  const message = !chokepoints.length
    ? `${subject} cannot be located: no chokepoint reference geography is loaded. Showing the default view.`
    : `${subject} ${named ? "is not a chokepoint Sealanes tracks" : "named no chokepoint"}; showing the default view. Tracked: ${chokepoints
        .map((item) => item.name)
        .join(", ")}.`;
  return {
    ...base,
    status: "unresolved",
    mode: request.lens,
    title: named ?? "No chokepoint named",
    message
  };
}
