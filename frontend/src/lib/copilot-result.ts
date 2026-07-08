import type {
  CopilotDomain,
  CopilotOperatorProgressEvent,
  CopilotResearchCardResult,
  CopilotSourceRef,
  CopilotToolTrace,
  ResearchCard,
  ResearchClaim
} from "./api/types";

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asOptionalString(value: unknown) {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function asStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim());
}

function normalizeClaim(value: unknown): ResearchClaim | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    claim: asString(row.claim),
    evidence_refs: asStringArray(row.evidence_refs)
  };
}

function normalizeCard(value: unknown): ResearchCard | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    title: asString(row.title),
    hypothesis: asString(row.hypothesis),
    rationale: asString(row.rationale),
    required_data: asStringArray(row.required_data),
    proposed_test: asString(row.proposed_test),
    confounders: asStringArray(row.confounders),
    next_steps: asStringArray(row.next_steps),
    caveats: asStringArray(row.caveats),
    source_backed_claims: Array.isArray(row.source_backed_claims)
      ? row.source_backed_claims
          .map(normalizeClaim)
          .filter((claim): claim is ResearchClaim => claim != null)
      : [],
    inferred_claims: asStringArray(row.inferred_claims)
  };
}

function normalizeSource(value: unknown): CopilotSourceRef | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    source_id: asString(row.source_id),
    label: asString(row.label),
    kind: asString(row.kind),
    provider: asString(row.provider),
    origin: asString(row.origin),
    description: asOptionalString(row.description),
    retrieved_at: asOptionalString(row.retrieved_at)
  };
}

function normalizeToolTrace(value: unknown): CopilotToolTrace | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    tool_name: asString(row.tool_name),
    summary: asString(row.summary),
    arguments:
      row.arguments && typeof row.arguments === "object" && !Array.isArray(row.arguments)
        ? (row.arguments as Record<string, unknown>)
        : {},
    source_ids: asStringArray(row.source_ids)
  };
}

function normalizeOperatorEvent(value: unknown): CopilotOperatorProgressEvent | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  return {
    run_id: asString(row.run_id),
    event_id: asString(row.event_id),
    sequence: typeof row.sequence === "number" && Number.isFinite(row.sequence) ? row.sequence : 0,
    event_type: asString(row.event_type),
    timestamp: asString(row.timestamp),
    step_id: asOptionalString(row.step_id),
    tool_id: asOptionalString(row.tool_id),
    title: asOptionalString(row.title),
    message: asOptionalString(row.message),
    payload:
      row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
        ? (row.payload as Record<string, unknown>)
        : {},
    source_ids: asStringArray(row.source_ids),
    warnings: asStringArray(row.warnings)
  };
}

export function normalizeCopilotResearchCardResult(
  domain: CopilotDomain,
  value: unknown
): CopilotResearchCardResult {
  const row = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const status = asString(row.status, "error");
  const card = normalizeCard(row.card);
  const message =
    asOptionalString(row.message) ??
    (card == null
      ? status === "ready"
        ? "Copilot returned no renderable card."
        : "Copilot failed before returning a renderable card."
      : null);

  return {
    domain,
    current_tab: asString(row.current_tab, domain),
    status,
    provider: asString(row.provider, "unknown"),
    model: asOptionalString(row.model),
    response_id: asOptionalString(row.response_id),
    message,
    card,
    sources: Array.isArray(row.sources)
      ? row.sources
          .map(normalizeSource)
          .filter((source): source is CopilotSourceRef => source != null)
      : [],
    tool_traces: Array.isArray(row.tool_traces)
      ? row.tool_traces
          .map(normalizeToolTrace)
          .filter((trace): trace is CopilotToolTrace => trace != null)
      : [],
    operator_events: Array.isArray(row.operator_events)
      ? row.operator_events
          .map(normalizeOperatorEvent)
          .filter((event): event is CopilotOperatorProgressEvent => event != null)
      : [],
    warnings: asStringArray(row.warnings)
  };
}
