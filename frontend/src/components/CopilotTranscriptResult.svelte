<script lang="ts">
  import type {
    CopilotDraftMutation,
    CopilotOperatorPlan,
    CopilotResearchCardResult,
    CopilotResearchPlan,
    CopilotResearchReport,
    CopilotSourceRef
  } from "../lib/api/types";
  import { canNavigateCopilotSource } from "../lib/copilot-source-navigation";
  import {
    buildCopilotTranscriptBlocks,
    type CopilotTranscriptBlock
  } from "../lib/copilot-transcript";

  export let result: CopilotResearchCardResult | null = null;
  export let researchPlan: CopilotResearchPlan | null = null;
  export let operatorPlan: CopilotOperatorPlan | null = null;
  export let report: CopilotResearchReport | null = null;
  export let mutation: CopilotDraftMutation | null = null;
  export let compact = false;
  export let cardLabel: string | null = "Research Card";
  export let onOpenSource: ((source: CopilotSourceRef) => Promise<unknown> | void) | null = null;
  export let onConfirmMutation:
    | ((mutation: CopilotDraftMutation) => Promise<unknown> | unknown)
    | null = null;
  export let onRejectMutation:
    | ((mutation: CopilotDraftMutation) => Promise<unknown> | unknown)
    | null = null;

  let blocks: CopilotTranscriptBlock[] = [];
  let resolvingMutationId: string | null = null;
  let mutationResolutionError = "";

  function formatMs(value: number) {
    return value >= 1000 ? `${Math.round(value / 100) / 10}s` : `${value}ms`;
  }

  function formatValue(value: unknown) {
    if (value == null) return "—";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  function payloadEntries(payload: Record<string, unknown>) {
    return Object.entries(payload).filter(([, value]) => value != null);
  }

  function sourceIsNavigable(source: CopilotSourceRef) {
    return onOpenSource != null && canNavigateCopilotSource(source);
  }

  function rollbackLabel(mutation: CopilotDraftMutation) {
    if (mutation.rollback_snapshot_id) return `rollback ${mutation.rollback_snapshot_id}`;
    if (mutation.status === "pending") return "pre-change snapshot on apply";
    return "rollback unavailable";
  }

  async function resolveMutation(
    action: "confirm" | "reject",
    mutation: CopilotDraftMutation
  ) {
    const callback = action === "confirm" ? onConfirmMutation : onRejectMutation;
    if (!callback || resolvingMutationId) return;
    resolvingMutationId = mutation.mutation_id;
    mutationResolutionError = "";
    try {
      const resolved = await callback(mutation);
      if (resolved == null) {
        mutationResolutionError = `Could not ${action} this mutation.`;
      }
    } catch (error) {
      mutationResolutionError =
        error instanceof Error ? error.message : `Could not ${action} this mutation.`;
    } finally {
      resolvingMutationId = null;
    }
  }

  $: blocks = buildCopilotTranscriptBlocks(result, { researchPlan, operatorPlan, report, mutation });
</script>

<div class:compact class="transcript-blocks">
  {#each blocks as block}
    {#if block.kind === "message"}
      <p class="result-message {block.status}">{block.message}</p>

    {:else if block.kind === "research-card"}
      <section class="block research-card" aria-label="Copilot research card">
        <header class="block-head">
          <h4>{block.card.title}</h4>
          {#if cardLabel}<span>{cardLabel}</span>{/if}
        </header>

        <div class="field">
          <span>Hypothesis</span>
          <p class="emphasis">{block.card.hypothesis}</p>
        </div>
        <div class="field">
          <span>Rationale</span>
          <p>{block.card.rationale}</p>
        </div>
        <div class="field">
          <span>Proposed test</span>
          <p>{block.card.proposed_test}</p>
        </div>

        {#if block.card.required_data.length}
          <div class="field">
            <span>Required data</span>
            <ul>{#each block.card.required_data as item}<li>{item}</li>{/each}</ul>
          </div>
        {/if}
        {#if block.card.confounders.length}
          <div class="field">
            <span>Confounders</span>
            <ul>{#each block.card.confounders as item}<li>{item}</li>{/each}</ul>
          </div>
        {/if}
        {#if block.card.next_steps.length}
          <div class="field">
            <span>Next steps</span>
            <ul>{#each block.card.next_steps as item}<li>{item}</li>{/each}</ul>
          </div>
        {/if}
        {#if block.card.caveats.length}
          <div class="field warning-field">
            <span>Caveats</span>
            <ul>{#each block.card.caveats as item}<li>{item}</li>{/each}</ul>
          </div>
        {/if}

        {#if block.claims.length}
          <div class="field source-field">
            <span>Source-backed</span>
            {#each block.claims as claim}
              <div class="claim">
                <p>{claim.claim}</p>
                {#if claim.evidence.length}
                  <div class="source-links" aria-label="Claim sources">
                    {#each claim.evidence as source}
                      {#if sourceIsNavigable(source)}
                        <button type="button" on:click={() => onOpenSource?.(source)} title={`Open ${source.label || source.source_id}`}>
                          {source.label || source.source_id}
                        </button>
                      {:else}
                        <span>{source.label || source.source_id}</span>
                      {/if}
                    {/each}
                  </div>
                {/if}
                {#if claim.unresolvedEvidenceRefs.length}
                  <small class="unresolved">Unresolved evidence: {claim.unresolvedEvidenceRefs.join(" / ")}</small>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        {#if block.card.inferred_claims.length}
          <div class="field inferred">
            <span>Inferred</span>
            <ul>{#each block.card.inferred_claims as item}<li>{item}</li>{/each}</ul>
          </div>
        {/if}
      </section>

    {:else if block.kind === "research-plan"}
      <section class="block plan-block" aria-label="Copilot research plan">
        <header class="block-head">
          <h4>{block.plan.intent.replaceAll("_", " ")}</h4>
          <span>Research plan · {block.plan.depth_profile}</span>
        </header>
        <div class="metric-row">
          <span>{block.plan.max_tool_calls} tools</span>
          <span>{block.plan.max_provider_calls} provider calls</span>
          <span>{formatMs(block.plan.max_elapsed_ms)} guard</span>
          <span>{block.plan.expected_artifacts.length} artifacts</span>
        </div>
        {#if block.plan.target_entities.length}
          <div class="chip-row">
            {#each block.plan.target_entities as entity}
              <span>{entity.kind}: {entity.label ?? entity.id}</span>
            {/each}
          </div>
        {/if}
        {#if block.plan.entity_resolution}
          <div
            class="notice entity-resolution"
            class:resolved={block.plan.entity_resolution.status === "resolved"}
            class:warning={block.plan.entity_resolution.status !== "resolved"}
          >
            <strong>
              {block.plan.entity_resolution.status === "resolved"
                ? "Company resolved"
                : block.plan.entity_resolution.status === "ambiguous"
                  ? "Choose a ticker"
                  : "Company not resolved"}
            </strong>
            {#if block.plan.entity_resolution.resolved}
              <p>
                {block.plan.entity_resolution.query ?? "Company"} →
                {block.plan.entity_resolution.resolved.label}
                ({block.plan.entity_resolution.resolved.id})
              </p>
            {:else if block.plan.entity_resolution.query}
              <p>{block.plan.entity_resolution.query}</p>
            {/if}
            {#if block.plan.entity_resolution.candidates.length > 1}
              <div class="chip-row" aria-label="Company ticker candidates">
                {#each block.plan.entity_resolution.candidates as candidate}
                  <span>{candidate.id} · {candidate.label}{candidate.exchange ? ` · ${candidate.exchange}` : ""}</span>
                {/each}
              </div>
            {/if}
            <small>
              {block.plan.entity_resolution.method.replaceAll("_", " ")} ·
              {block.plan.entity_resolution.source_provider}
            </small>
          </div>
        {/if}
        {#if block.plan.domain_plan.length}
          <div class="table-wrap">
            <table>
              <thead><tr><th>Domain</th><th>Depth</th><th>Budget</th><th>Reason</th></tr></thead>
              <tbody>
                {#each block.plan.domain_plan as item}
                  <tr>
                    <td>{item.domain.replaceAll("_", " ")}</td>
                    <td>{item.depth}</td>
                    <td>{item.estimated_tool_calls}T / {item.estimated_provider_calls}P</td>
                    <td>{item.reason}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
        {#if block.plan.domain_decisions.length}
          <div class="decision-list">
            {#each block.plan.domain_decisions as decision}
              <div class:skip={!decision.used}>
                <strong>
                  {decision.used ? "Use" : "Skip"} {decision.domain.replaceAll("_", " ")}
                  · {(decision.classification ?? (decision.used ? "selected" : "irrelevant")).replaceAll("_", " ")}
                </strong>
                <span>{decision.reason}</span>
              </div>
            {/each}
          </div>
        {/if}
        {#if block.plan.warnings.length}
          <div class="notice warning"><strong>Plan warnings</strong><ul>{#each block.plan.warnings as warning}<li>{warning}</li>{/each}</ul></div>
        {/if}
        <footer class="provenance">{block.plan.source_provider} · {block.plan.origin}</footer>
      </section>

    {:else if block.kind === "operator-plan"}
      <section class="block plan-block" aria-label="Copilot operator plan">
        <header class="block-head">
          <h4>{block.plan.intent.replaceAll("_", " ")}</h4>
          <span>{block.plan.role.replaceAll("_", " ")}</span>
        </header>
        <div class="metric-row">
          <span>{block.plan.max_tool_calls} tools</span>
          <span>{block.plan.max_provider_calls} provider calls</span>
          <span>{formatMs(block.plan.max_elapsed_ms)} guard</span>
          <span>{block.plan.confirmation_checkpoints.length} checkpoints</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Step</th><th>Action</th><th>Policy</th><th>Artifacts</th></tr></thead>
            <tbody>
              {#each block.plan.steps as step}
                <tr class:checkpoint={step.requires_confirmation}>
                  <td>{step.order}</td>
                  <td><strong>{step.title}</strong>{#if step.rationale}<small>{step.rationale}</small>{/if}</td>
                  <td>{step.domain.replaceAll("_", " ")} / {step.action_type.replaceAll("_", " ")}</td>
                  <td>{step.permission_policy.replaceAll("_", " ")}</td>
                  <td>{step.expected_artifacts.join(" / ") || "trace"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if block.plan.warnings.length}
          <div class="notice warning"><strong>Operator warnings</strong><ul>{#each block.plan.warnings as warning}<li>{warning}</li>{/each}</ul></div>
        {/if}
        <footer class="provenance">{block.plan.source_provider} · {block.plan.origin}</footer>
      </section>

    {:else if block.kind === "operator-step"}
      <section class="event-row {block.event.event_type}" aria-label="Operator step">
        <span class="sequence">{block.event.sequence}</span>
        <div>
          <strong>{block.event.title ?? block.event.event_type.replaceAll("-", " ")}</strong>
          <p>{block.event.message ?? "Operator event recorded."}</p>
          {#if payloadEntries(block.event.payload).length}
            <details><summary>Step details</summary><pre>{formatValue(block.event.payload)}</pre></details>
          {/if}
          {#if block.references.evidence.length}
            <div class="source-links">
              {#each block.references.evidence as source}
                {#if sourceIsNavigable(source)}
                  <button type="button" on:click={() => onOpenSource?.(source)}>{source.label || source.source_id}</button>
                {:else}<span>{source.label || source.source_id}</span>{/if}
              {/each}
            </div>
          {/if}
          {#if block.references.unresolvedEvidenceRefs.length}
            <small class="unresolved">Unresolved evidence: {block.references.unresolvedEvidenceRefs.join(" / ")}</small>
          {/if}
          {#if block.event.warnings.length}
            <ul class="warnings">{#each block.event.warnings as warning}<li>{warning}</li>{/each}</ul>
          {/if}
        </div>
      </section>

    {:else if block.kind === "confirmation"}
      <section class="block confirmation" aria-label="Copilot confirmation checkpoint">
        <header class="block-head"><h4>{block.title}</h4><span>Confirmation required</span></header>
        <p>{block.message}</p>
        {#if payloadEntries(block.payload).length}
          <dl>
            {#each payloadEntries(block.payload) as [key, value]}
              <dt>{key.replaceAll("_", " ")}</dt><dd>{formatValue(value)}</dd>
            {/each}
          </dl>
        {/if}
        {#if block.references.evidence.length}
          <div class="source-links">
            {#each block.references.evidence as source}
              {#if sourceIsNavigable(source)}
                <button type="button" on:click={() => onOpenSource?.(source)}>{source.label || source.source_id}</button>
              {:else}<span>{source.label || source.source_id}</span>{/if}
            {/each}
          </div>
        {/if}
        {#if block.references.unresolvedEvidenceRefs.length}
          <small class="unresolved">Unresolved evidence: {block.references.unresolvedEvidenceRefs.join(" / ")}</small>
        {/if}
        {#if block.warnings.length}
          <ul class="warnings">{#each block.warnings as warning}<li>{warning}</li>{/each}</ul>
        {/if}
        {#if block.mutation && block.mutation.status === "pending"}
          <div class="confirmation-actions" aria-label="Mutation confirmation actions">
            <button
              type="button"
              class="confirm-action"
              disabled={resolvingMutationId != null || onConfirmMutation == null}
              on:click={() => resolveMutation("confirm", block.mutation)}
            >
              {resolvingMutationId === block.mutation.mutation_id ? "Applying…" : "Confirm and apply"}
            </button>
            <button
              type="button"
              class="reject-action"
              disabled={resolvingMutationId != null || onRejectMutation == null}
              on:click={() => resolveMutation("reject", block.mutation)}
            >
              Reject
            </button>
          </div>
          {#if mutationResolutionError}
            <p class="mutation-error" role="alert">{mutationResolutionError}</p>
          {/if}
        {/if}
      </section>

    {:else if block.kind === "mutation-diff"}
      <section class="block mutation" aria-label="Copilot mutation diff">
        <header class="block-head">
          <h4>{block.mutation.target_label}</h4>
          <span>{block.mutation.status} · {rollbackLabel(block.mutation)}</span>
        </header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Field</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
            <tbody>
              {#each block.mutation.diff as entry}
                <tr>
                  <td><strong>{entry.label}</strong><small>{entry.path}</small></td>
                  <td>{formatValue(entry.before)}{entry.unit ? ` ${entry.unit}` : ""}</td>
                  <td>{formatValue(entry.after)}{entry.unit ? ` ${entry.unit}` : ""}</td>
                  <td>{entry.change_type.replaceAll("_", " ")}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if block.mutation.expires_at}<p class="secondary">Confirmation expires {block.mutation.expires_at}.</p>{/if}
        <footer class="provenance">{block.mutation.source_provider} · {block.mutation.origin}</footer>
      </section>

    {:else if block.kind === "artifact" || block.kind === "operator-report"}
      <section class="event-row artifact" aria-label={block.kind === "artifact" ? "Operator artifact" : "Operator report"}>
        <span class="sequence">{block.event.sequence}</span>
        <div>
          <strong>{block.event.title ?? (block.kind === "artifact" ? "Operator artifact" : "Operator report")}</strong>
          <p>{block.event.message ?? "Operator artifact recorded."}</p>
          {#if payloadEntries(block.event.payload).length}
            <details open={block.kind === "operator-report"}>
              <summary>{block.kind === "operator-report" ? "Report details" : "Artifact details"}</summary>
              <dl>
                {#each payloadEntries(block.event.payload) as [key, value]}
                  <dt>{key.replaceAll("_", " ")}</dt><dd>{formatValue(value)}</dd>
                {/each}
              </dl>
            </details>
          {/if}
          {#if block.references.evidence.length}
            <div class="source-links">
              {#each block.references.evidence as source}
                {#if sourceIsNavigable(source)}
                  <button type="button" on:click={() => onOpenSource?.(source)}>{source.label || source.source_id}</button>
                {:else}<span>{source.label || source.source_id}</span>{/if}
              {/each}
            </div>
          {/if}
          {#if block.references.unresolvedEvidenceRefs.length}
            <small class="unresolved">Unresolved evidence: {block.references.unresolvedEvidenceRefs.join(" / ")}</small>
          {/if}
        </div>
      </section>

    {:else if block.kind === "report"}
      <section class="block report" aria-label="Copilot research report">
        <header class="block-head"><h4>{block.report.title}</h4><span>Research report</span></header>
        <div class="metric-row">
          <span>{block.report.source_turn_ids.length} turns</span>
          <span>{block.report.sources.length} sources</span>
          <span>{block.report.tool_trace_summary.length} tools</span>
        </div>
        {#if block.claims.length}
          <div class="field source-field">
            <span>Source-backed findings</span>
            {#each block.claims as claim}
              <div class="claim">
                <p>{claim.claim}</p>
                <div class="source-links">
                  {#each claim.evidence as source}
                    {#if sourceIsNavigable(source)}
                      <button type="button" on:click={() => onOpenSource?.(source)}>{source.label || source.source_id}</button>
                    {:else}<span>{source.label || source.source_id}</span>{/if}
                  {/each}
                </div>
                {#if claim.unresolvedEvidenceRefs.length}
                  <small class="unresolved">Unresolved evidence: {claim.unresolvedEvidenceRefs.join(" / ")}</small>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        {#if block.report.inferred_claims.length}
          <div class="field inferred"><span>Inferred</span><ul>{#each block.report.inferred_claims as item}<li>{item}</li>{/each}</ul></div>
        {/if}
        {#if block.report.assumptions.length}
          <div class="field assumption"><span>Assumptions</span><ul>{#each block.report.assumptions as item}<li>{item}</li>{/each}</ul></div>
        {/if}
        {#if block.report.missing_data.length}
          <div class="field missing"><span>Missing data</span><ul>{#each block.report.missing_data as item}<li>{item}</li>{/each}</ul></div>
        {/if}
        {#if block.report.tool_trace_summary.length}
          <details class="report-details">
            <summary>Tool trace ({block.report.tool_trace_summary.length})</summary>
            {#each block.report.tool_trace_summary as trace}
              <div class="evidence-row"><strong>{trace.tool_name}</strong><p>{trace.summary}</p><small>{trace.status}</small></div>
            {/each}
          </details>
        {/if}
        {#if block.report.warnings.length}
          <div class="notice warning"><strong>Report warnings</strong><ul>{#each block.report.warnings as warning}<li>{warning}</li>{/each}</ul></div>
        {/if}
        <footer class="provenance">{block.report.source_provider} · {block.report.origin} · {block.report.generated_at}</footer>
      </section>

    {:else if block.kind === "status"}
      <section class="block result-state {block.status}" aria-label="Copilot result state">
        <header class="block-head"><h4>{block.label}</h4><span>{block.providerLabel}</span></header>
        <p>{block.message}</p>
      </section>

    {:else if block.kind === "evidence"}
      <details class="evidence" class:warning={block.warnings.length > 0}>
        <summary>
          <span>Evidence</span>
          {#if block.sources.length}<span>Sources ({block.sources.length})</span>{/if}
          {#if block.toolTraces.length}<span>Tools ({block.toolTraces.length})</span>{/if}
          {#if block.warnings.length}<span class="warning-label">Warnings ({block.warnings.length})</span>{/if}
        </summary>
        <div class="evidence-body">
          {#if block.sources.length}
            <section>
              <h5>Sources</h5>
              {#each block.sources as source}
                <div class="evidence-row">
                  <div class="evidence-title">
                    <strong>{source.label || source.source_id}</strong>
                    {#if sourceIsNavigable(source)}
                      <button type="button" on:click={() => onOpenSource?.(source)}>Open source</button>
                    {/if}
                  </div>
                  <small>{source.source_id} / {source.kind || "source"}</small>
                  {#if source.description}<p>{source.description}</p>{/if}
                  {#if !sourceIsNavigable(source) && source.navigation_reason}
                    <small>{source.navigation_reason}</small>
                  {/if}
                </div>
              {/each}
            </section>
          {/if}
          {#if block.toolTraces.length}
            <section>
              <h5>Tools used</h5>
              {#each block.toolTraces as trace}
                <div class="evidence-row">
                  <strong>{trace.tool_name}</strong>
                  <p>{trace.summary}</p>
                  {#if trace.source_ids.length}<small>{trace.source_ids.join(" / ")}</small>{/if}
                </div>
              {/each}
            </section>
          {/if}
          {#if block.warnings.length}
            <section>
              <h5>Warnings</h5>
              <ul>{#each block.warnings as warning}<li>{warning}</li>{/each}</ul>
            </section>
          {/if}
          <footer class="provenance">{block.providerLabel}</footer>
        </div>
      </details>

    {:else if block.kind === "provider-meta"}
      <div class="provenance">{block.providerLabel}</div>
    {/if}
  {/each}
</div>

<style>
  .transcript-blocks {
    display: grid;
    gap: var(--space-3);
    min-width: 0;
  }

  .result-message,
  .block p,
  .event-row p,
  .evidence p,
  .block ul,
  .evidence ul {
    margin: 0;
  }

  .result-message {
    color: var(--text-0);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .block,
  .evidence,
  .event-row {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
  }

  .block {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4);
  }

  .research-card,
  .report {
    border-left: 2px solid var(--accent);
  }

  .block-head,
  .evidence-title {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .block-head h4,
  .evidence h5 {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-base);
  }

  .block-head > span,
  .field > span,
  .evidence h5,
  .provenance {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-size: var(--text-2xs);
  }

  .field {
    display: grid;
    gap: var(--space-1);
  }

  .field + .field {
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .field p,
  .field li,
  .block > p,
  .event-row p,
  .evidence p,
  .evidence li,
  dd {
    color: var(--text-1);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    overflow-wrap: anywhere;
  }

  .field p.emphasis {
    color: var(--text-0);
  }

  ul {
    padding-left: var(--space-5);
  }

  .claim {
    display: grid;
    gap: var(--space-2);
    padding-left: var(--space-3);
    border-left: 2px solid var(--positive);
  }

  .claim + .claim {
    margin-top: var(--space-2);
  }

  .inferred {
    border-left: 2px solid var(--warning);
    padding-left: var(--space-3);
  }

  .assumption {
    border-left: 2px solid var(--text-2);
    padding-left: var(--space-3);
  }

  .missing,
  .warning-field {
    border-left: 2px solid var(--negative);
    padding-left: var(--space-3);
  }

  .source-links,
  .chip-row,
  .metric-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .source-links button,
  .source-links span,
  .chip-row span,
  .metric-row span {
    min-height: 1.5rem;
    padding: 0 var(--space-2);
    border: 1px solid var(--panel-border);
    background: var(--surface-1);
    color: var(--text-2);
    font: inherit;
    font-size: var(--text-xs);
    line-height: 1.45rem;
  }

  .source-links button,
  .evidence-title button {
    color: var(--accent);
    cursor: pointer;
  }

  .source-links button:hover,
  .evidence-title button:hover {
    border-color: var(--accent);
    color: var(--text-0);
  }

  .unresolved,
  .warnings {
    color: var(--warning);
    font-size: var(--text-xs);
  }

  .table-wrap {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  th,
  td {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-2);
    background: var(--surface-1);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  td {
    color: var(--text-1);
  }

  td strong,
  td small {
    display: block;
  }

  td small {
    margin-top: var(--space-1);
    color: var(--text-2);
  }

  tr.checkpoint td {
    border-top-color: var(--warning);
  }

  .decision-list {
    display: grid;
    border: 1px solid var(--divider);
  }

  .decision-list > div {
    display: grid;
    grid-template-columns: minmax(9rem, 0.35fr) 1fr;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
  }

  .decision-list > div + div {
    border-top: 1px solid var(--divider);
  }

  .decision-list strong,
  .decision-list span {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .decision-list .skip strong {
    color: var(--text-2);
  }

  .notice {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-3);
    border-left: 2px solid var(--panel-border);
    background: var(--surface-1);
  }

  .notice.warning,
  .confirmation {
    border-left-color: var(--warning);
  }

  .notice.resolved {
    border-left-color: var(--positive);
  }

  .notice.resolved strong {
    color: var(--positive);
  }

  .entity-resolution small {
    color: var(--text-2);
    font-size: var(--text-xs);
    text-transform: capitalize;
  }

  .notice strong {
    color: var(--warning);
    font-size: var(--text-sm);
  }

  .event-row {
    display: grid;
    grid-template-columns: 2rem 1fr;
    gap: var(--space-3);
    padding: var(--space-3);
  }

  .event-row > div {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }

  .sequence {
    color: var(--text-2);
    font-family: var(--app-font), monospace;
    font-size: var(--text-xs);
  }

  .event-row strong {
    color: var(--text-0);
    font-size: var(--text-sm);
  }

  .event-row.warning,
  .event-row.confirmation-needed {
    border-left: 2px solid var(--warning);
  }

  .event-row.artifact {
    border-left: 2px solid var(--accent);
  }

  details summary {
    color: var(--text-2);
    cursor: pointer;
    font-size: var(--text-xs);
  }

  pre {
    max-height: 14rem;
    margin: var(--space-2) 0 0;
    padding: var(--space-2);
    overflow: auto;
    border: 1px solid var(--divider);
    background: var(--surface-0);
    color: var(--text-1);
    font: var(--text-xs)/var(--leading-normal) var(--app-font), monospace;
    white-space: pre-wrap;
  }

  dl {
    display: grid;
    grid-template-columns: minmax(8rem, 0.3fr) 1fr;
    margin: 0;
    border: 1px solid var(--divider);
  }

  dt,
  dd {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--divider);
  }

  dt {
    color: var(--text-2);
    text-transform: uppercase;
    font-size: var(--text-2xs);
  }

  dl > :nth-last-child(-n + 2) {
    border-bottom: 0;
  }

  .secondary {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .confirmation-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .confirmation-actions button {
    min-height: 28px;
    padding: 0 var(--space-4);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-1);
    color: var(--text-1);
    cursor: pointer;
    font: inherit;
    font-size: var(--text-xs);
  }

  .confirmation-actions .confirm-action {
    background: var(--active-bg);
    color: var(--text-0);
  }

  .confirmation-actions button:not(:disabled):hover {
    background: var(--hover-bg);
  }

  .confirmation-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .mutation-error {
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .result-state {
    border-left: 2px solid var(--panel-strong);
  }

  .result-state.error,
  .result-state.provider_error,
  .result-state.failed {
    border-left-color: var(--negative);
  }

  .result-state.error p,
  .result-state.provider_error p,
  .result-state.failed p {
    color: var(--negative);
  }

  .result-state.unavailable,
  .result-state.incomplete,
  .result-state.refused,
  .result-state.cancelled,
  .result-state.timeout,
  .result-state.degraded {
    border-left-color: var(--warning);
  }

  .evidence {
    padding: var(--space-3);
  }

  .evidence > summary {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  .warning-label {
    color: var(--warning);
  }

  .evidence-body,
  .evidence-body section,
  .evidence-row,
  .report-details {
    display: grid;
    gap: var(--space-2);
  }

  .evidence-body {
    gap: var(--space-4);
    padding-top: var(--space-4);
  }

  .evidence-body section + section {
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .evidence-row + .evidence-row {
    padding-top: var(--space-2);
    border-top: 1px solid var(--divider);
  }

  .evidence-row strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .evidence-row small {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .evidence-title button {
    min-height: 1.5rem;
    padding: 0 var(--space-2);
    border: 1px solid var(--panel-border);
    background: transparent;
    font: inherit;
    font-size: var(--text-xs);
  }

  .provenance {
    overflow-wrap: anywhere;
  }

  .compact {
    gap: var(--space-2);
  }

  .compact .block {
    padding: var(--space-3);
  }

  .compact .block-head {
    display: grid;
    gap: var(--space-1);
  }

  @media (max-width: 760px) {
    .block-head,
    .evidence-title {
      align-items: flex-start;
      flex-direction: column;
    }

    .decision-list > div,
    dl {
      grid-template-columns: 1fr;
    }

    dl > :nth-last-child(-n + 2) {
      border-bottom: 1px solid var(--divider);
    }
  }
</style>
