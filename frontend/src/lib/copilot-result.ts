import type {
  CopilotDomain,
  CopilotModelPolicyResolution,
  CopilotOperatorProgressEvent,
  CopilotResearchCardResult,
  CopilotSourceRef,
  CopilotRunObservability,
  CopilotSafeProviderError,
  CopilotToolTrace,
  CopilotUsageRecord,
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

function asStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => typeof item === "string")
      .map(([key, item]) => [key, item as string])
  );
}

function asOptionalNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeUsage(value: unknown): CopilotUsageRecord {
  const row = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    input_tokens: asOptionalNumber(row.input_tokens),
    output_tokens: asOptionalNumber(row.output_tokens),
    reasoning_tokens: asOptionalNumber(row.reasoning_tokens),
    total_tokens: asOptionalNumber(row.total_tokens),
    cache_read_tokens: asOptionalNumber(row.cache_read_tokens),
    cache_write_tokens: asOptionalNumber(row.cache_write_tokens),
    provider_calls: asOptionalNumber(row.provider_calls),
    tool_calls: asOptionalNumber(row.tool_calls),
    raw: {}
  };
}

function normalizeObservability(value: unknown): CopilotRunObservability | undefined {
  if (!value || typeof value !== "object") return undefined;
  const row = value as Record<string, unknown>;
  return {
    selected_profile: asOptionalString(row.selected_profile),
    resolved_provider: asOptionalString(row.resolved_provider),
    resolved_model: asOptionalString(row.resolved_model),
    model_policy_version: asOptionalString(row.model_policy_version),
    routing_reason: asOptionalString(row.routing_reason),
    reasoning_mode: asOptionalString(row.reasoning_mode),
    reasoning_effort: asOptionalString(row.reasoning_effort) as CopilotRunObservability["reasoning_effort"],
    orchestration_path: asOptionalString(row.orchestration_path),
    total_latency_ms: asOptionalNumber(row.total_latency_ms),
    provider_latency_ms: asOptionalNumber(row.provider_latency_ms),
    cancellation_outcome: asOptionalString(row.cancellation_outcome),
    cancellation_boundary: asOptionalString(row.cancellation_boundary),
    provider_error_category: asOptionalString(row.provider_error_category),
    diagnostic_id: asOptionalString(row.diagnostic_id)
  };
}

function normalizeSafeError(value: unknown): CopilotSafeProviderError | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const diagnosticId = asOptionalString(row.diagnostic_id);
  if (!diagnosticId) return null;
  return {
    category: asString(row.category, "provider_error"),
    diagnostic_id: diagnosticId,
    message: asString(row.message, "The provider could not complete this Copilot run."),
    guidance: asString(row.guidance, "Retry or review provider configuration."),
    retryable: row.retryable === true,
    created_at: asString(row.created_at)
  };
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
    retrieved_at: asOptionalString(row.retrieved_at),
    provider_native_id: asOptionalString(row.provider_native_id),
    url: asOptionalString(row.url),
    navigation_supported:
      typeof row.navigation_supported === "boolean" ? row.navigation_supported : null,
    navigation_reason: asOptionalString(row.navigation_reason),
    navigation_tab: asOptionalString(row.navigation_tab) as CopilotSourceRef["navigation_tab"],
    navigation_mode: asOptionalString(row.navigation_mode),
    navigation_context: asStringRecord(row.navigation_context)
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
    warnings: asStringArray(row.warnings),
    research_plan:
      row.research_plan && typeof row.research_plan === "object"
        ? (row.research_plan as CopilotResearchCardResult["research_plan"])
        : null,
    context_contracts: Array.isArray(row.context_contracts)
      ? (row.context_contracts.filter(
          (item) => item != null && typeof item === "object" && !Array.isArray(item)
        ) as Array<Record<string, unknown>>)
      : [],
    context_budget:
      row.context_budget && typeof row.context_budget === "object" && !Array.isArray(row.context_budget)
        ? (row.context_budget as Record<string, unknown>)
        : {},
    model_resolution:
      row.model_resolution && typeof row.model_resolution === "object"
        ? (row.model_resolution as CopilotModelPolicyResolution)
        : null,
    usage: normalizeUsage(row.usage),
    observability: normalizeObservability(row.observability),
    safe_provider_error: normalizeSafeError(row.safe_provider_error)
  };
}
