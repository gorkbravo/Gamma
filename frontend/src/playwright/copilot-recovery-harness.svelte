<script lang="ts">
  import CopilotView from "../views/CopilotView.svelte";
  import CopilotResearchCard from "../components/CopilotResearchCard.svelte";
  import { activeCopilotSession, copilotThreads, copilotActiveRun, loading,
    copilotRunningSessionIds, confirmCopilotMutation, rejectCopilotMutation,
    cancelCopilotRun, retryCopilotTurn } from "../lib/stores/app";
  import type { CopilotSessionDetail, CopilotResearchCardResult, CopilotDraftMutation } from "../lib/api/types";

  let shelf = new URLSearchParams(location.search).has("shelf");
  const mutation = {
    mutation_id: "mutation9", run_id: "run9", workflow_id: "run9", session_id: "session9",
    confirmation_token: "fixture-token", context_fingerprint: "original-context", proposal_hash: "fixture-hash",
    status: "pending", domain: "fundamentals", target_label: "AAPL base DCF", target_id: "AAPL:base",
    source_provider: "fixture", origin: "gamma.dcf", source_ids: [], warnings: [], rollback_snapshot_id: null,
    diff: [{ path: "scenarios.base.assumptions.wacc_pct", change_type: "changed", label: "WACC", before: 0.08, after: 0.09, unit: "percent" }],
  } as unknown as CopilotDraftMutation;
  const result = { domain: "synthesis", current_tab: "copilot", status: "awaiting_confirmation",
    response_id: "response9", provider: "fixture", model: null, card: null,
    message: "Review the exact saved DCF change before continuing this run.", sources: [], tool_traces: [], warnings: [],
    operator_events: [{ event_id: "approval9", run_id: "run9", sequence: 1, event_type: "confirmation-needed",
      title: "DCF approval", message: "Changing the saved WACC requires approval.", source_ids: [], warnings: [], payload: { mutation } }],
  } as unknown as CopilotResearchCardResult;
  const session = { session_id: "session9", title: "DCF recovery fixture", created_at: "2026-10-04T12:00:00Z",
    updated_at: "2026-10-04T12:00:00Z", turn_count: 1, artifact_count: 0, memo_count: 0, report_count: 0,
    active_domain: "synthesis", active_context_fingerprint: "original-context", archived_at: null, warnings: [] };
  const detail = { session, turns: [{ turn_id: "turn9", session_id: "session9", run_id: "run9", role: "research_operator",
      domain: "synthesis", prompt: "Set AAPL base DCF WACC to 9%", turn_index: 1,
      selected_scope_domains: ["fundamentals"], result }], context_snapshots: [], memos: [], artifacts: [],
      working_analyses: [], storage_warnings: [] } as unknown as CopilotSessionDetail;
  localStorage.setItem("gamma.copilot.session", "session9");
  activeCopilotSession.set(detail);
  copilotThreads.update(threads => ({ ...threads, synthesis: { domain: "synthesis", sourceSessionId: "session9",
    contextFingerprint: "original-context", latestResponseId: "response9", entries: [{ entryId: "response9", turnIndex: 1,
      prompt: "Set AAPL base DCF WACC to 9%", continuedFromResponseId: null, result }] } }));
  const surface = { supported: true, domain: "synthesis" as const, contextLabel: "Fundamentals", domainLabel: "Research",
    guidance: "Review the saved DCF.", placeholder: "Research question", scopeOptions: [], selectedScopeDomains: ["fundamentals" as const],
    selectionMessage: "Fundamentals selected", thread: null };
</script>

<div class="host">
  {#if shelf}
    <CopilotResearchCard open available thread={$copilotThreads.synthesis} loading={$loading.copilot}
      activeRun={$copilotActiveRun} onCancelRun={cancelCopilotRun} onGenerate={() => {}}
      onConfirmMutation={confirmCopilotMutation} onRejectMutation={rejectCopilotMutation}
      onOpenWorkspace={() => { shelf = false; return { status: "already_promoted" }; }} />
  {:else}
    <CopilotView {surface} synthesisSurface={surface} activeSession={$activeCopilotSession}
      thread={$copilotThreads.synthesis} loading={$loading.copilot} activeRun={$copilotActiveRun}
      runningSessionIds={$copilotRunningSessionIds} onCancelRun={cancelCopilotRun}
      onConfirmMutation={confirmCopilotMutation} onRejectMutation={rejectCopilotMutation} onRetryTurn={retryCopilotTurn} />
  {/if}
</div>
<style>.host { height: 100vh; min-width: 0; } :global(body) { margin: 0; }</style>
