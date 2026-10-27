import type {
  CopilotDraftMutation,
  CopilotOperatorPlan,
  CopilotOperatorProgressEvent,
  CopilotResearchCardResult,
  CopilotResearchPlan,
  CopilotResearchReport,
  CopilotSourceRef,
  CopilotToolTrace,
  ResearchCard,
  ResearchClaim
} from "./api/types";

export interface ResolvedTranscriptClaim {
  claim: string;
  evidence: CopilotSourceRef[];
  unresolvedEvidenceRefs: string[];
}

export interface ResolvedTranscriptReferences {
  evidence: CopilotSourceRef[];
  unresolvedEvidenceRefs: string[];
}

export type CopilotTranscriptBlock =
  | { kind: "message"; status: string; message: string }
  | { kind: "research-card"; card: ResearchCard; claims: ResolvedTranscriptClaim[] }
  | { kind: "research-plan"; plan: CopilotResearchPlan }
  | { kind: "operator-plan"; plan: CopilotOperatorPlan }
  | { kind: "operator-step"; event: CopilotOperatorProgressEvent; references: ResolvedTranscriptReferences }
  | {
      /** Avisos seguidos del mismo tipo de paso, en un solo bloque plegado (GUA-20261021-13). */
      kind: "operator-warnings";
      title: string;
      warnings: string[];
      firstSequence: number;
      lastSequence: number;
    }
  | { kind: "operator-progress"; count: number; firstSequence: number; lastSequence: number }
  | {
      kind: "confirmation";
      title: string;
      message: string;
      warnings: string[];
      payload: Record<string, unknown>;
      mutation: CopilotDraftMutation | null;
      references: ResolvedTranscriptReferences;
    }
  | { kind: "mutation-diff"; mutation: CopilotDraftMutation; references: ResolvedTranscriptReferences }
  | { kind: "artifact"; event: CopilotOperatorProgressEvent; references: ResolvedTranscriptReferences }
  | { kind: "operator-report"; event: CopilotOperatorProgressEvent; references: ResolvedTranscriptReferences }
  | { kind: "report"; report: CopilotResearchReport; claims: ResolvedTranscriptClaim[] }
  | { kind: "status"; status: string; label: string; message: string; providerLabel: string }
  | {
      kind: "evidence";
      providerLabel: string;
      sources: CopilotSourceRef[];
      toolTraces: CopilotToolTrace[];
      warnings: string[];
    }
  | { kind: "provider-meta"; providerLabel: string };

export interface CopilotTranscriptExtras {
  researchPlan?: CopilotResearchPlan | null;
  operatorPlan?: CopilotOperatorPlan | null;
  report?: CopilotResearchReport | null;
  mutation?: CopilotDraftMutation | null;
}

function providerLabel(result: CopilotResearchCardResult) {
  return result.model ? `${result.provider} / ${result.model}` : result.provider;
}

function resolveReferences(sourceIds: string[], sources: CopilotSourceRef[]): ResolvedTranscriptReferences {
  const registry = new Map(sources.map((source) => [source.source_id, source]));
  return {
    evidence: sourceIds
      .map((ref) => registry.get(ref))
      .filter((source): source is CopilotSourceRef => source != null),
    unresolvedEvidenceRefs: sourceIds.filter((ref) => !registry.has(ref))
  };
}

function resolveClaims(claims: ResearchClaim[], sources: CopilotSourceRef[]): ResolvedTranscriptClaim[] {
  return claims.map((claim) => ({
    claim: claim.claim,
    ...resolveReferences(claim.evidence_refs, sources)
  }));
}

function operatorEventBlock(
  event: CopilotOperatorProgressEvent,
  sources: CopilotSourceRef[]
): CopilotTranscriptBlock {
  const references = resolveReferences(event.source_ids, sources);
  if (event.event_type === "confirmation-needed") {
    const mutation = mutationFromPayload(event.payload);
    const payload = Object.fromEntries(
      Object.entries(event.payload).filter(
        ([key]) => !["confirmation_token", "mutation", "proposed_payload", "proposal_hash", "context_fingerprint", "checkpoint_id", "after_step_id", "mutation_id", "required_for_tool_ids", "default_policy", "rollback_snapshot_id"].includes(key)
      )
    );
    return {
      kind: "confirmation",
      title: event.title ?? "Confirmation required",
      message: event.message ?? "This operator step is stopped pending exact confirmation.",
      warnings: event.warnings,
      payload,
      mutation,
      references
    };
  }
  if (event.event_type === "artifact-created") return { kind: "artifact", event, references };
  if (event.event_type === "final-report") return { kind: "operator-report", event, references };
  return { kind: "operator-step", event, references };
}

/** Avisos consecutivos con el mismo título (el progreso del modelo intercalado no corta el grupo). */
function warningRun(
  events: CopilotOperatorProgressEvent[],
  start: number
): { run: CopilotOperatorProgressEvent[]; nextIndex: number } {
  const title = events[start].title;
  const run: CopilotOperatorProgressEvent[] = [];
  let nextIndex = start;
  for (let index = start; index < events.length; index += 1) {
    const event = events[index];
    if (event.event_type === "provider-progress") continue;
    if (event.event_type !== "warning" || event.title !== title || event.source_ids.length) break;
    run.push(event);
    nextIndex = index + 1;
  }
  return { run, nextIndex };
}

function isText(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function mutationFromPayload(payload: Record<string, unknown>): CopilotDraftMutation | null {
  const candidate = payload.mutation;
  if (
    candidate == null
    || typeof candidate !== "object"
    || Array.isArray(candidate)
  ) {
    return null;
  }
  const mutation = candidate as Partial<CopilotDraftMutation>;
  if (
    typeof mutation.mutation_id !== "string"
    || typeof mutation.confirmation_token !== "string"
    || !Array.isArray(mutation.diff)
  ) {
    return null;
  }
  return mutation as CopilotDraftMutation;
}

export function buildCopilotTranscriptBlocks(
  result: CopilotResearchCardResult | null,
  extras: CopilotTranscriptExtras = {}
): CopilotTranscriptBlock[] {
  const blocks: CopilotTranscriptBlock[] = [];

  if (extras.researchPlan) blocks.push({ kind: "research-plan", plan: extras.researchPlan });
  if (extras.operatorPlan) {
    blocks.push({ kind: "operator-plan", plan: extras.operatorPlan });
    for (const checkpoint of extras.operatorPlan.confirmation_checkpoints) {
      blocks.push({
        kind: "confirmation",
        title: `Checkpoint after ${checkpoint.after_step_id}`,
        message: checkpoint.reason,
        warnings: [],
        payload: {
          checkpoint_id: checkpoint.checkpoint_id,
          required_for_tool_ids: checkpoint.required_for_tool_ids,
          policy: checkpoint.default_policy
        },
        mutation: null,
        references: { evidence: [], unresolvedEvidenceRefs: [] }
      });
    }
  }

  if (result) {
    const sources = result.sources ?? [];
    const toolTraces = result.tool_traces ?? [];
    const operatorEvents = result.operator_events ?? [];
    const warnings = result.warnings ?? [];
    const provider = providerLabel(result);
    const hasOperatorContent = operatorEvents.length > 0;
    if (result.status !== "ready") {
      blocks.push({
        kind: "status",
        status: result.status,
        label: result.status.replaceAll("_", " "),
        message: result.message ?? `Copilot ended with status ${result.status}.`,
        providerLabel: provider
      });
    } else if (result.message) {
      blocks.push({ kind: "message", status: result.status, message: result.message });
    }

    if (result.card) {
      blocks.push({
        kind: "research-card",
        card: result.card,
        claims: resolveClaims(result.card.source_backed_claims, sources)
      });
    } else if (result.status === "ready" && !hasOperatorContent) {
      blocks.push({
        kind: "status",
        status: "ready",
        label: "No renderable card",
        message: result.message ?? "Copilot returned no renderable card.",
        providerLabel: provider
      });
    }

    // Verificación en vivo 2026-10-27: una tarea de curva generó 41 pasos "Operator warning"
    // (uno por caveat del workspace) y 842 filas "Operator model progress". Los avisos
    // seguidos se agrupan en un bloque plegado y el progreso del modelo en una sola fila.
    const progress = operatorEvents.filter((event) => event.event_type === "provider-progress");
    if (progress.length) {
      blocks.push({
        kind: "operator-progress",
        count: progress.length,
        firstSequence: progress[0].sequence,
        lastSequence: progress[progress.length - 1].sequence
      });
    }
    let index = 0;
    while (index < operatorEvents.length) {
      const event = operatorEvents[index];
      if (event.event_type === "provider-progress") {
        index += 1;
        continue;
      }
      if (event.event_type === "warning") {
        const { run, nextIndex } = warningRun(operatorEvents, index);
        if (run.length > 1) {
          blocks.push({
            kind: "operator-warnings",
            title: event.title ?? "Operator warning",
            warnings: [...new Set(run.flatMap((item) => [item.message, ...item.warnings]).filter(isText))],
            firstSequence: run[0].sequence,
            lastSequence: run[run.length - 1].sequence
          });
          index = nextIndex;
          continue;
        }
      }
      const block = operatorEventBlock(event, sources);
      if (block.kind === "confirmation" && block.mutation) {
        blocks.push({
          kind: "mutation-diff",
          mutation: block.mutation,
          references: block.references
        });
      }
      blocks.push(block);
      index += 1;
    }

    if (sources.length || toolTraces.length || warnings.length) {
      blocks.push({
        kind: "evidence",
        providerLabel: provider,
        sources,
        toolTraces,
        warnings
      });
    } else if (result.card || operatorEvents.length) {
      blocks.push({ kind: "provider-meta", providerLabel: provider });
    }
  }

  if (extras.report) {
    blocks.push({
      kind: "report",
      report: extras.report,
      claims: resolveClaims(extras.report.source_backed_claims, extras.report.sources)
    });
  }

  if (extras.mutation) {
    const mutationReferences = resolveReferences(
      extras.mutation.source_ids,
      result?.sources ?? extras.report?.sources ?? []
    );
    blocks.push({
      kind: "confirmation",
      title: `${extras.mutation.action_type.replaceAll("_", " ")} · ${extras.mutation.target_label}`,
      message:
        extras.mutation.rationale ??
        "Review the exact before/after diff before confirming this local research-state mutation.",
      warnings: extras.mutation.warnings,
      payload: {
        mutation_id: extras.mutation.mutation_id,
        status: extras.mutation.status,
        expires_at: extras.mutation.expires_at,
        rollback_snapshot_id: extras.mutation.rollback_snapshot_id
      },
      mutation: extras.mutation,
      references: mutationReferences
    });
    blocks.push({ kind: "mutation-diff", mutation: extras.mutation, references: mutationReferences });
  }

  return blocks;
}


/** Mutation percentages are stored as decimal fractions, just like the DCF model. */
export function formatMutationValue(value: unknown, unit: string | null | undefined): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.map((item) => formatMutationValue(item, unit)).join(", ");
  if (typeof value === "number" && Number.isFinite(value)) {
    const number = unit === "percent" ? value * 100 : value;
    return `${number.toLocaleString("en-US", { maximumFractionDigits: 6 })}${unit === "percent" ? "%" : unit ? ` ${unit}` : ""}`;
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
