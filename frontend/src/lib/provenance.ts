// Shared provider/provenance badge contract.
//
// Backend payloads carry provenance as loose snake_case fields
// (source_provider / freshness_label / retrieved_at / transformation_note /
// warnings) whose freshness vocabulary varies by provider. This module is the
// single normalization point: views convert any payload-shaped object into a
// ProvenanceBadgeData and render it through components/ProvenanceBadge.svelte
// instead of per-widget warning prose.

export type ProvenanceState =
  | "live"
  | "delayed"
  | "cached"
  | "stale"
  | "historical"
  | "sample"
  | "synthetic"
  | "derived"
  | "model"
  | "unavailable"
  | "unknown";

export type ProvenanceTone = "positive" | "warning" | "negative" | "neutral";

export interface ProvenanceBadgeData {
  provider: string | null;
  state: ProvenanceState;
  rawLabel: string | null;
  qualityLabel?: string | null;
  retrievedAt: string | null;
  sourceTimestamp: string | null;
  transformationNote: string | null;
  warnings: string[];
}

/** Accepts any backend payload shape that carries provenance fields. */
export interface ProvenanceLike {
  source_provider?: string | null;
  provider?: string | null;
  freshness_label?: string | null;
  freshness?: string | { status?: string | null } | null;
  retrieved_at?: string | null;
  source_timestamp?: string | null;
  transformation_note?: string | null;
  warnings?: string[] | null;
}

const STATE_ALIASES: Record<string, ProvenanceState> = {
  live: "live",
  fresh: "live",
  current: "live",
  current_public_api: "live",
  realtime: "live",
  real_time: "live",
  delayed: "delayed",
  cached: "cached",
  cache: "cached",
  local_cache: "cached",
  stale: "stale",
  historical: "historical",
  sample: "sample",
  sample_data: "sample",
  mock: "sample",
  mocked: "sample",
  demo: "sample",
  synthetic: "synthetic",
  synthetic_derived: "synthetic",
  derived: "derived",
  model: "model",
  model_generated: "model",
  ai_generated: "model",
  unavailable: "unavailable",
  not_available: "unavailable",
  "n/a": "unavailable",
  none: "unavailable",
  broken: "unavailable",
  unknown: "unknown"
};

export function normalizeProvenanceState(label: string | null | undefined): ProvenanceState {
  const normalized = String(label ?? "")
    .trim()
    .toLowerCase()
    .replace(/[-\s]+/g, "_");
  if (!normalized) return "unknown";
  return STATE_ALIASES[normalized] ?? "unknown";
}

const STATE_TONES: Record<ProvenanceState, ProvenanceTone> = {
  live: "positive",
  delayed: "warning",
  cached: "warning",
  stale: "warning",
  historical: "neutral",
  sample: "warning",
  synthetic: "warning",
  derived: "neutral",
  model: "warning",
  unavailable: "negative",
  unknown: "neutral"
};

export function provenanceTone(state: ProvenanceState): ProvenanceTone {
  return STATE_TONES[state];
}

const STATE_LABELS: Record<ProvenanceState, string> = {
  live: "LIVE",
  delayed: "DELAYED",
  cached: "CACHED",
  stale: "STALE",
  historical: "HIST",
  sample: "SAMPLE",
  synthetic: "SYNTH",
  derived: "DERIVED",
  model: "MODEL",
  unavailable: "N/A",
  unknown: "UNKNOWN"
};

export function provenanceStateLabel(state: ProvenanceState): string {
  return STATE_LABELS[state];
}

function rawFreshnessLabel(input: ProvenanceLike): string | null {
  if (input.freshness_label != null && String(input.freshness_label).trim()) {
    return String(input.freshness_label);
  }
  const freshness = input.freshness;
  if (typeof freshness === "string" && freshness.trim()) return freshness;
  if (freshness && typeof freshness === "object" && freshness.status) {
    return String(freshness.status);
  }
  return null;
}

export interface ProvenanceOverrides {
  provider?: string | null;
  state?: ProvenanceState;
  retrievedAt?: string | null;
  sourceTimestamp?: string | null;
  transformationNote?: string | null;
  warnings?: string[];
  qualityLabel?: string | null;
}

export function toProvenanceBadge(
  input: ProvenanceLike | null | undefined,
  overrides: ProvenanceOverrides = {}
): ProvenanceBadgeData {
  const source = input ?? {};
  const rawLabel = rawFreshnessLabel(source);
  const provider =
    overrides.provider ??
    (source.source_provider != null && String(source.source_provider).trim()
      ? String(source.source_provider)
      : source.provider != null && String(source.provider).trim()
        ? String(source.provider)
        : null);
  return {
    provider,
    state: overrides.state ?? normalizeProvenanceState(rawLabel),
    rawLabel,
    qualityLabel: overrides.qualityLabel ?? null,
    retrievedAt: overrides.retrievedAt ?? source.retrieved_at ?? null,
    sourceTimestamp: overrides.sourceTimestamp ?? source.source_timestamp ?? null,
    transformationNote: overrides.transformationNote ?? source.transformation_note ?? null,
    warnings: overrides.warnings ?? (Array.isArray(source.warnings) ? [...source.warnings] : [])
  };
}

/** Compact timestamp: HH:MM when today, otherwise YYYY-MM-DD. */
export function shortProvenanceTimestamp(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  const now = new Date();
  const sameDay =
    parsed.getFullYear() === now.getFullYear() &&
    parsed.getMonth() === now.getMonth() &&
    parsed.getDate() === now.getDate();
  if (sameDay) {
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return parsed.toISOString().slice(0, 10);
}

/** Full multi-line detail used as the badge tooltip. */
export function provenanceTitle(data: ProvenanceBadgeData): string {
  const lines: string[] = [];
  lines.push(`Provider: ${data.provider ?? "unknown"}`);
  lines.push(`State: ${data.state}${data.rawLabel && normalizeProvenanceState(data.rawLabel) === "unknown" ? ` (reported: ${data.rawLabel})` : ""}`);
  if (data.qualityLabel) lines.push(`Quality: ${data.qualityLabel}`);
  if (data.retrievedAt) lines.push(`Retrieved: ${data.retrievedAt}`);
  if (data.sourceTimestamp) lines.push(`Source timestamp: ${data.sourceTimestamp}`);
  if (data.transformationNote) lines.push(`Transformation: ${data.transformationNote}`);
  for (const warning of data.warnings.slice(0, 4)) {
    lines.push(`Warning: ${warning}`);
  }
  if (data.warnings.length > 4) lines.push(`+${data.warnings.length - 4} more warnings`);
  return lines.join("\n");
}
