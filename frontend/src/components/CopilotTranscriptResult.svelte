<script lang="ts">
  import type { CopilotResearchCardResult } from "../lib/api/types";
  import { buildCopilotTranscriptBlocks, type CopilotTranscriptBlock } from "../lib/copilot-transcript";

  export let result: CopilotResearchCardResult;
  let blocks: CopilotTranscriptBlock[] = [];

  $: blocks = buildCopilotTranscriptBlocks(result);
</script>

{#each blocks as block}
  {#if block.kind === "message"}
    <p class="result-message {block.status}">{block.message}</p>
  {:else if block.kind === "research-card"}
    <section class="research-card" aria-label="Copilot research card">
      <h4>{block.card.title}</h4>

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
        <div class="field">
          <span>Caveats</span>
          <ul>{#each block.card.caveats as item}<li>{item}</li>{/each}</ul>
        </div>
      {/if}

      {#if block.card.source_backed_claims.length}
        <div class="field">
          <span>Source-backed</span>
          {#each block.card.source_backed_claims as claim}
            <div class="claim">
              <p>{claim.claim}</p>
              {#if claim.evidence_refs.length}<small>{claim.evidence_refs.join(" / ")}</small>{/if}
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
  {:else if block.kind === "status"}
    <section class="result-state {block.status}" aria-label="Copilot result state">
      <div class="state-head">
        <span>{block.label}</span>
        <small>{block.providerLabel}</small>
      </div>
      <p>{block.message}</p>
    </section>
  {:else if block.kind === "evidence"}
    <details class="evidence" class:warning={block.warnings.length > 0}>
      <summary>
        <span>{block.providerLabel}</span>
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
                <strong>{source.label || source.source_id}</strong>
                <small>{source.source_id} / {source.provider}{source.kind ? ` / ${source.kind}` : ""}</small>
                {#if source.description}<p>{source.description}</p>{/if}
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
      </div>
    </details>
  {:else if block.kind === "provider-meta"}
    <div class="result-meta">{block.providerLabel}</div>
  {/if}
{/each}

<style>
  .result-message {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .result-message.error,
  .result-state.error p {
    color: var(--negative);
  }

  .research-card,
  .result-state,
  .evidence {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
  }

  .research-card {
    display: grid;
    gap: var(--space-3);
    border-left: 2px solid var(--accent);
    padding: var(--space-4) var(--space-5);
  }

  .research-card h4,
  .evidence h5,
  .research-card p,
  .result-state p,
  .evidence p,
  .research-card ul,
  .evidence ul {
    margin: 0;
  }

  .research-card h4 {
    color: var(--text-0);
    font-size: var(--text-base);
  }

  .field {
    display: grid;
    gap: var(--space-1);
  }

  .field + .field {
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .field > span,
  .state-head span,
  .state-head small,
  .evidence h5,
  .result-meta {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .field p,
  .field li,
  .result-state p,
  .evidence p,
  .evidence li {
    color: var(--text-1);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    overflow-wrap: anywhere;
  }

  .field p.emphasis {
    color: var(--text-0);
  }

  ul {
    padding-left: var(--space-6);
  }

  .claim {
    display: grid;
    gap: var(--space-1);
  }

  .claim + .claim {
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .claim small,
  .evidence-row small {
    color: var(--text-2);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }

  .inferred {
    border-left: 2px solid var(--warning);
    padding-left: var(--space-3);
  }

  .result-state {
    display: grid;
    gap: var(--space-3);
    border-left: 2px solid var(--panel-strong);
    padding: var(--space-4) var(--space-5);
  }

  .result-state.error {
    border-left-color: var(--negative);
  }

  .result-state.unavailable,
  .result-state.incomplete,
  .result-state.refused,
  .result-state.cancelled {
    border-left-color: var(--warning);
  }

  .state-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .evidence {
    padding: var(--space-3) var(--space-4);
  }

  .evidence summary {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
    cursor: pointer;
  }

  .evidence summary::marker {
    color: var(--text-2);
  }

  .evidence .warning-label,
  .evidence.warning h5:last-of-type {
    color: var(--warning);
  }

  .evidence-body {
    display: grid;
    gap: var(--space-4);
    padding-top: var(--space-4);
  }

  .evidence-body section,
  .evidence-row {
    display: grid;
    gap: var(--space-2);
  }

  .evidence-body section + section {
    padding-top: var(--space-4);
    border-top: 1px solid var(--divider);
  }

  .evidence-row + .evidence-row {
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .evidence-row strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }
</style>
