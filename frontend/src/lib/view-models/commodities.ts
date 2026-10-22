import type {
  CommodityBasisComparison,
  CommodityCrossDomainLink,
  CommodityInstrument,
  CommodityPriceReconciliation,
  CommoditySpreadSnapshot,
  CrossTabHandoffEnvelope
} from "../api/types";

/**
 * Fecha de observación (AAAA-MM-DD) tomada del ISO tal cual, sin pasar por la zona local:
 * un dato diario del 14 de octubre debe leerse "2026-10-14" en cualquier huso (GUA-20261021-2).
 */
export function observationDateLabel(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(text);
  return match ? match[1] : "N/A";
}

export interface SpreadObservationView {
  /** Fecha de la última observación alineada, nunca retrieved_at. */
  date: string;
  stale: boolean;
  freshness: "current" | "stale" | "unknown";
  lagLabel: string;
  title: string;
}

export function spreadObservationView(spread: CommoditySpreadSnapshot): SpreadObservationView {
  const date = observationDateLabel(spread.observed_at ?? null);
  const freshness = spread.freshness === "current" || spread.freshness === "stale" ? spread.freshness : "unknown";
  const lag = spread.observation_lag_days;
  const lagLabel = lag == null ? "" : lag === 0 ? "today" : `${lag}d old`;
  const legs = Object.entries(spread.leg_observed_at ?? {})
    .map(([leg, stamp]) => `${leg} ${observationDateLabel(stamp)}`)
    .join(", ");
  const threshold = spread.stale_after_days ?? 4;
  const title =
    freshness === "stale"
      ? `Stale: latest aligned observation ${date}${lag != null ? ` (${lag} days old, limit ${threshold})` : ""}. Legs: ${legs || "N/A"}.`
      : freshness === "current"
        ? `Latest aligned observation ${date}. Legs: ${legs || "N/A"}.`
        : "No dated observation; freshness unknown.";
  return { date, stale: freshness === "stale", freshness, lagLabel, title };
}

export interface SpreadCurrentValueView {
  value: number;
  asOf: string | null;
  source: string;
}

/** Valor con cotizaciones front de la misma instantánea, mostrado aparte del valor histórico. */
export function spreadCurrentValueView(spread: CommoditySpreadSnapshot): SpreadCurrentValueView | null {
  const value = spread.current_value;
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  return {
    value,
    asOf: spread.current_value_as_of ?? null,
    source: spread.current_value_source ?? "Same-snapshot front futures"
  };
}

export const RECONCILIATION_PANEL_STATUSES = new Set(["conflict", "stale_reference", "basis"]);

export function reconciliationStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "conflict":
      return "Data conflict";
    case "stale_reference":
      return "Stale reference";
    case "basis":
      return "Futures-spot basis";
    case "aligned":
      return "Aligned";
    case "insufficient":
      return "Insufficient";
    default:
      return (status ?? "N/A").replace(/_/g, " ");
  }
}

export function comparisonKindLabel(kind: string | null | undefined): string {
  switch (kind) {
    case "conflict":
      return "Data conflict";
    case "stale_reference":
      return "Stale";
    case "basis":
      return "Basis";
    case "units_differ":
      return "Units differ";
    case "aligned":
      return "Aligned";
    case "same_series":
      return "Same series";
    default:
      return (kind ?? "N/A").replace(/_/g, " ");
  }
}

export function comparisonTone(kind: string | null | undefined): "negative" | "warning" | "" {
  if (kind === "conflict") return "negative";
  if (kind === "stale_reference" || kind === "units_differ") return "warning";
  return "";
}

export interface ReconciliationReferenceRow {
  id: string;
  label: string;
  kind: string;
  kindLabel: string;
  tone: "negative" | "warning" | "";
  value: number | null;
  unit: string;
  date: string;
  convertedValue: number | null;
  convertedUnit: string;
  ageDays: number | null;
  difference: number | null;
  differencePct: number | null;
  note: string;
}

/** Filas de referencia (titular primero) con fecha y unidad de cada una (GUA-20261021-4). */
export function reconciliationReferenceRows(
  reconciliation: CommodityPriceReconciliation | null | undefined
): ReconciliationReferenceRow[] {
  if (!reconciliation) return [];
  const rows: ReconciliationReferenceRow[] = [];
  const headline = reconciliation.headline;
  if (headline) {
    rows.push({
      id: headline.basis_id,
      label: headline.display_label,
      kind: "headline",
      kindLabel: "Headline",
      tone: "",
      value: headline.value,
      unit: headline.unit ?? "",
      date: observationDateLabel(headline.source_timestamp ?? headline.timestamp),
      convertedValue: null,
      convertedUnit: "",
      ageDays: null,
      difference: null,
      differencePct: null,
      note: ""
    });
  }
  for (const comparison of reconciliation.comparisons ?? []) {
    rows.push(comparisonRow(comparison));
  }
  return rows;
}

function comparisonRow(comparison: CommodityBasisComparison): ReconciliationReferenceRow {
  const converted =
    comparison.converted_value != null && comparison.unit !== comparison.headline_unit ? comparison.converted_value : null;
  return {
    id: comparison.basis_id,
    label: comparison.display_label,
    kind: comparison.kind,
    kindLabel: comparisonKindLabel(comparison.kind),
    tone: comparisonTone(comparison.kind),
    value: comparison.value,
    unit: comparison.unit ?? "",
    date: observationDateLabel(comparison.observed_at),
    convertedValue: converted,
    convertedUnit: converted != null ? comparison.headline_unit ?? "" : "",
    ageDays: comparison.age_days,
    difference: comparison.difference,
    differencePct: comparison.difference_pct,
    note: comparison.note
  };
}

const DOMAIN_TABS: Record<string, string> = {
  macro: "macro",
  maritime: "maritime",
  sealanes: "maritime",
  prediction_markets: "prediction_markets",
  commodities: "commodities"
};

/** Pestaña destino de un enlace cruzado; null si no hay pestaña conocida. */
export function crossDomainLinkTargetTab(link: CommodityCrossDomainLink): string | null {
  const explicit = (link.target_tab ?? "").trim();
  if (explicit) return explicit;
  return DOMAIN_TABS[(link.target_domain ?? "").trim().toLowerCase()] ?? null;
}

/**
 * Sobre de traspaso entre pestañas para una fila "cross-domain" (GUA-20261021-7). Reutiliza el
 * contrato CrossTabHandoffEnvelope que ya consumen los traspasos de Prediction Markets; Sealanes
 * recibe un grupo de chokepoints con los enlaces de commodities como metadatos.
 */
export function buildCommodityCrossDomainHandoff(
  link: CommodityCrossDomainLink,
  options: {
    instrument?: Pick<CommodityInstrument, "instrument_id" | "name"> | null;
    sourceMode?: string | null;
    now?: Date;
  } = {}
): CrossTabHandoffEnvelope | null {
  const targetTab = crossDomainLinkTargetTab(link);
  if (!targetTab) return null;
  const instrument = options.instrument ?? null;
  const commodityLinks = [
    {
      link_id: link.link_id,
      relationship: link.relationship,
      linked_instrument_ids: [...link.linked_instrument_ids],
      selected_instrument_id: instrument?.instrument_id ?? null
    }
  ];
  const isMaritime = targetTab === "maritime";
  return {
    source_tab: "commodities",
    source_mode: options.sourceMode ?? null,
    selected_entity: {
      entity_type: isMaritime ? "maritime_chokepoint_group" : "commodity_cross_domain_link",
      label: link.target_label,
      normalized_id: link.link_id,
      provider_id: "gamma",
      native_id: link.link_id,
      metadata: {
        commodity_links: commodityLinks,
        relationship: link.relationship,
        source_commodity_id: instrument?.instrument_id ?? null,
        source_commodity_label: instrument?.name ?? null
      }
    },
    selected_timeframe: null,
    loaded_series: null,
    provider: "gamma",
    source: { link_id: link.link_id, origin: link.origin },
    warnings: [],
    normalized_ids: { ...(link.target_ids ?? {}) },
    timestamp: (options.now ?? new Date()).toISOString(),
    intended_target_tab: targetTab,
    intended_target_mode: link.target_mode ?? (isMaritime ? "chokepoints" : null)
  };
}

/**
 * Instrumento que se está cargando y aún no es el del workspace visible; null si no hay
 * discrepancia. Evita mostrar la cabecera y la base del instrumento anterior (P2, 2026-10-21).
 */
export function pendingCommodityInstrument(
  loading: boolean,
  requestedInstrumentId: string | null | undefined,
  loadedInstrumentId: string | null | undefined
): string | null {
  const requested = (requestedInstrumentId ?? "").trim().toLowerCase();
  if (!loading || !requested) return null;
  return requested === (loadedInstrumentId ?? "").trim().toLowerCase() ? null : requested;
}
