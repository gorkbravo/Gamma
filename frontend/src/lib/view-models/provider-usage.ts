import type { ProviderUsageHealth, ProviderUsageResponse } from "../api/types";

/*
 * Settings › Provider Usage (GUA-20260903-10). Antes se pintaban solo las cuatro filas más
 * recientes: "500 calls" junto a filas que sumaban 132. Aquí se muestran todos los
 * proveedores, las llamadas sin atribuir como fila explícita y las filas suman el total.
 */

export const UNATTRIBUTED_PROVIDER_ID = "unattributed";

export interface ProviderUsageRow {
  providerId: string;
  label: string;
  calls: number;
  httpRequests: number;
  ok: number;
  failed: number;
  /** Respuestas parciales ("incomplete"): ni éxito ni fallo, con su propio contador. */
  partial: number;
  unavailable: number;
  averageMs: number;
  endpoints: string[];
  unattributed: boolean;
  tone: "warning" | "neutral";
}

export interface ProviderUsageView {
  rows: ProviderUsageRow[];
  total: number;
  rowSum: number;
  failed: number;
  headline: string;
  windowNote: string | null;
}

export interface ProviderHealthView {
  attention: ProviderUsageHealth[];
  summary: string | null;
}

const numberFormat = new Intl.NumberFormat("en-US");

function count(value: number | null | undefined): number {
  return Number.isFinite(value) ? Math.max(0, Math.trunc(Number(value))) : 0;
}

function plural(value: number, word: string): string {
  return `${numberFormat.format(value)} ${word}${value === 1 ? "" : "s"}`;
}

export function buildProviderUsageView(usage: ProviderUsageResponse | null | undefined): ProviderUsageView {
  const total = count(usage?.total_calls);
  const rows: ProviderUsageRow[] = (usage?.providers ?? []).map((row) => {
    const unattributed = row.provider_id === UNATTRIBUTED_PROVIDER_ID || row.provider_id === "unknown";
    const failed = count(row.error_count);
    return {
      providerId: row.provider_id,
      label: unattributed ? "Unattributed" : row.provider_id,
      calls: count(row.call_count),
      httpRequests: count(row.http_request_count),
      ok: count(row.success_count),
      failed,
      partial: count(row.incomplete_count),
      unavailable: count(row.unavailable_count),
      averageMs: Number.isFinite(row.average_duration_ms) ? row.average_duration_ms : 0,
      endpoints: row.endpoints ?? [],
      unattributed,
      tone: failed > 0 || unattributed ? "warning" : "neutral"
    };
  });

  // Si el backend devolviera filas que no cuadran, el resto se muestra como no atribuido:
  // ninguna llamada desaparece del panel.
  const listed = rows.reduce((sum, row) => sum + row.calls, 0);
  if (listed < total) {
    const remainder = total - listed;
    const existing = rows.find((row) => row.unattributed);
    if (existing) {
      existing.calls += remainder;
    } else {
      rows.push({
        providerId: UNATTRIBUTED_PROVIDER_ID,
        label: "Unattributed",
        calls: remainder,
        httpRequests: 0,
        ok: 0,
        failed: 0,
        partial: 0,
        unavailable: 0,
        averageMs: 0,
        endpoints: [],
        unattributed: true,
        tone: "warning"
      });
    }
  }

  rows.sort((left, right) => {
    if (left.unattributed !== right.unattributed) return left.unattributed ? 1 : -1;
    return right.calls - left.calls || left.label.localeCompare(right.label);
  });

  const rowSum = rows.reduce((sum, row) => sum + row.calls, 0);
  const lifetime = count(usage?.lifetime_calls);
  const limit = count(usage?.retained_limit);
  const windowNote =
    lifetime > total
      ? `Last ${numberFormat.format(total)} of ${numberFormat.format(lifetime)} calls since backend startup.`
      : limit && total >= limit
        ? `Window holds the last ${numberFormat.format(limit)} calls.`
        : null;

  return {
    rows,
    total,
    rowSum,
    failed: rows.reduce((sum, row) => sum + row.failed, 0),
    headline: plural(total, "call"),
    windowNote
  };
}

export function providerUsageRowDetail(row: ProviderUsageRow): string {
  const parts = [`${numberFormat.format(row.ok)} ok`];
  if (row.failed) parts.push(`${numberFormat.format(row.failed)} failed`);
  if (row.partial) parts.push(`${numberFormat.format(row.partial)} partial`);
  if (row.unavailable) parts.push(`${numberFormat.format(row.unavailable)} unavailable`);
  if (row.httpRequests) parts.push(`${numberFormat.format(row.httpRequests)} HTTP`);
  if (row.averageMs > 0) parts.push(`${row.averageMs.toFixed(row.averageMs >= 10 ? 0 : 1)} ms avg`);
  return parts.join(" · ");
}

// Estados que se listan uno a uno: incidencias, configuración pendiente y la inactividad
// deliberada (p. ej. AISstream sin llamadas hasta hacer zoom). Sanos y no pedidos se resumen.
const ATTENTION_STATUSES = new Set(["degraded", "unavailable", "needs_config", "idle_by_design"]);

/** Todas las filas que piden atención y un resumen del resto, en vez de un corte a cuatro. */
export function buildProviderHealthView(usage: ProviderUsageResponse | null | undefined): ProviderHealthView {
  const health = usage?.health ?? [];
  const attention = health.filter((row) => ATTENTION_STATUSES.has(row.health_status));
  const rest = new Map<string, number>();
  for (const row of health) {
    if (ATTENTION_STATUSES.has(row.health_status)) continue;
    const label = (row.health_label || row.health_status).toLowerCase();
    rest.set(label, (rest.get(label) ?? 0) + 1);
  }
  const summary = [...rest.entries()].map(([label, value]) => `${numberFormat.format(value)} ${label}`).join(" · ");
  return { attention, summary: summary || null };
}
