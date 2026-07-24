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

export type CopilotTranscriptBlock =
  | { kind: "message"; status: string; message: string }
  | { kind: "research-card"; card: ResearchCard; claims: ResolvedTranscriptClaim[] }
  | { kind: "research-plan"; plan: CopilotResearchPlan }
  | { kind: "operator-plan"; plan: CopilotOperatorPlan }
  | { kind: "operator-step"; event: CopilotOperatorProgressEvent }
  | { kind: "confirmation"; title: string; message: string; sourceIds: string[]; warnings: string[]; payload: Record<string, unknown> }
  | { kind: "mutation-diff"; mutation: CopilotDraftMutation }
  | { kind: "artifact"; event: CopilotOperatorProgressEvent }
  | { kind: "operator-report"; event: CopilotOperatorProgressEvent }
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

function resolveClaims(claims: ResearchClaim[], sources: CopilotSourceRef[]): ResolvedTranscriptClaim[] {
  const registry = new Map(sources.map((source) => [source.source_id, source]));
  return claims.map((claim) => ({
    claim: claim.claim,
    evidence: claim.evidence_refs
      .map((ref) => registry.get(ref))
      .filter((source): source is CopilotSourceRef => source != null),
    unresolvedEvidenceRefs: claim.evidence_refs.filter((ref) => !registry.has(ref))
  }));
}

function operatorEventBlock(event: CopilotOperatorProgressEvent): CopilotTranscriptBlock {
  if (event.event_type === "confirmation-needed") {
    return {
      kind: "confirmation",
      title: event.title ?? "Confirmation required",
      message: event.message ?? "This operator step is stopped pending exact confirmation.",
      sourceIds: event.source_ids,
      warnings: event.warnings,
      payload: event.payload
    };
  }
  if (event.event_type === "artifact-created") return { kind: "artifact", event };
  if (event.event_type === "final-report") return { kind: "operator-report", event };
  return { kind: "operator-step", event };
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
        sourceIds: [],
        warnings: [],
        payload: {
          checkpoint_id: checkpoint.checkpoint_id,
          required_for_tool_ids: checkpoint.required_for_tool_ids,
          policy: checkpoint.default_policy
        }
      });
    }
  }

  if (result) {
    const provider = providerLabel(result);
    const hasOperatorContent = result.operator_events.length > 0;
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
        claims: resolveClaims(result.card.source_backed_claims, result.sources)
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

    blocks.push(...result.operator_events.map(operatorEventBlock));

    if (result.sources.length || result.tool_traces.length || result.warnings.length) {
      blocks.push({
        kind: "evidence",
        providerLabel: provider,
        sources: result.sources,
        toolTraces: result.tool_traces,
        warnings: result.warnings
      });
    } else if (result.card || result.operator_events.length) {
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
    blocks.push({
      kind: "confirmation",
      title: `${extras.mutation.action_type.replaceAll("_", " ")} · ${extras.mutation.target_label}`,
      message: extras.mutation.rationale ?? "Review the exact before/after diff before confirming this local research-state mutation.",
      sourceIds: extras.mutation.source_ids,
      warnings: extras.mutation.warnings,
      payload: {
        mutation_id: extras.mutation.mutation_id,
        status: extras.mutation.status,
        expires_at: extras.mutation.expires_at,
        rollback_snapshot_id: extras.mutation.rollback_snapshot_id
      }
    });
    blocks.push({ kind: "mutation-diff", mutation: extras.mutation });
  }

  return blocks;
}
