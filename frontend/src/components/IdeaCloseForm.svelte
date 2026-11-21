<script lang="ts">
  // Close an active idea (Workstream 12, I3b). Closing needs a review: an
  // outcome and a lesson, with the expectation (the thesis by default), what
  // happened, and a verdict per pin. The hypothetical record at this moment is
  // shown read-only; the server freezes it into the review.
  import WhatIsThis from "./WhatIsThis.svelte";
  import type { Idea, IdeaClosePayload, IdeaTrackingResponse } from "../lib/api/types";
  import {
    EVIDENCE_VERDICTS,
    EVIDENCE_VERDICT_LABELS,
    REVIEW_OUTCOMES,
    REVIEW_OUTCOME_LABELS,
    closeDraftError,
    closePayload,
    type CloseDraft,
  } from "../lib/idea-review";
  import { TRACKING_LABEL, formatTrackingReturn, returnTone } from "../lib/idea-tracking";
  import { EVIDENCE_STANCE_LABELS } from "../lib/ideas";

  export let idea: Idea;
  export let tracking: IdeaTrackingResponse | null = null;
  export let onSubmit: (payload: IdeaClosePayload) => Promise<boolean> = async () => false;
  export let onCancel: () => void = () => {};

  const formId = `close-${Math.random().toString(36).slice(2, 8)}`;
  let draft: CloseDraft = { outcome: null, expected: idea.thesis, realizedNote: "", lesson: "", verdicts: {} };
  let saving = false;
  let submitError = "";

  $: current = tracking && tracking.idea_id === idea.idea_id ? tracking : null;
  $: summary = current?.summary ?? null;
  $: draftError = closeDraftError(draft);

  async function submit() {
    const payload = closePayload(draft);
    if (!payload || saving) return;
    saving = true;
    submitError = "";
    try {
      const ok = await onSubmit(payload);
      if (!ok) submitError = "The idea was not closed.";
    } finally {
      saving = false;
    }
  }
</script>

<article class="panel is-flush close-panel" aria-label="Close the idea">
  <div class="panel-title">
    <h3>Close with a review</h3>
    <span class="header-meta">Required to close</span>
  </div>
  <form class="close-form" on:submit|preventDefault={submit}>
    <div class="field wide">
      <span id={`${formId}-outcome`}>Outcome <WhatIsThis key="review.outcome" stance={idea.stance} /></span>
      <div class="segmented" role="radiogroup" aria-labelledby={`${formId}-outcome`}>
        {#each REVIEW_OUTCOMES as option}
          <button
            type="button"
            role="radio"
            aria-checked={draft.outcome === option}
            class:selected={draft.outcome === option}
            on:click={() => (draft = { ...draft, outcome: option })}>{REVIEW_OUTCOME_LABELS[option]}</button
          >
        {/each}
      </div>
    </div>

    <label class="field wide">
      <span>What you expected</span>
      <textarea class="form-control" rows="2" bind:value={draft.expected} maxlength="4000"></textarea>
    </label>

    <div class="field wide">
      <span>Realized so far</span>
      <div class="realized-row">
        <span class="tag is-tinted context">{TRACKING_LABEL}</span>
        {#if summary && summary.net_return != null}
          <span>Net <strong class={returnTone(summary.net_return)}>{formatTrackingReturn(summary.net_return)}</strong></span>
          <span>Gross <strong class={returnTone(summary.gross_return)}>{formatTrackingReturn(summary.gross_return)}</strong></span>
          <span>{current?.benchmark.symbol} <strong class={returnTone(summary.benchmark_return)}>{formatTrackingReturn(summary.benchmark_return)}</strong></span>
          <span class="meta">as of {summary.as_of}; the exit is the next close after closing</span>
        {:else}
          <span class="absent">{current ? "No priced sessions yet" : idea.tracking?.segments.length ? "Loading…" : "No tracked record"}</span>
        {/if}
      </div>
    </div>

    <label class="field wide">
      <span>What happened</span>
      <textarea class="form-control" rows="2" bind:value={draft.realizedNote} maxlength="4000" placeholder="Optional"></textarea>
    </label>

    {#if idea.evidence.length}
      <div class="field wide">
        <span>Did the evidence hold up?</span>
        <div class="table-scroll">
          <table class="data-table is-compact verdict-table">
            <thead><tr><th>Pin</th><th>Stance</th><th>Verdict</th></tr></thead>
            <tbody>
              {#each idea.evidence as pin (pin.evidence_id)}
                <tr>
                  <td>{pin.title}</td>
                  <td>{EVIDENCE_STANCE_LABELS[pin.stance]}</td>
                  <td>
                    <select
                      class="form-control is-small"
                      aria-label={`Verdict for ${pin.title}`}
                      value={draft.verdicts[pin.evidence_id] ?? ""}
                      on:change={(event) =>
                        (draft = { ...draft, verdicts: { ...draft.verdicts, [pin.evidence_id]: event.currentTarget.value as never } })}
                    >
                      <option value="">No verdict</option>
                      {#each EVIDENCE_VERDICTS as verdict}
                        <option value={verdict}>{EVIDENCE_VERDICT_LABELS[verdict]}</option>
                      {/each}
                    </select>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <label class="field wide">
      <span>Lesson</span>
      <textarea class="form-control" rows="2" bind:value={draft.lesson} maxlength="4000" placeholder="What you would do differently, or keep doing"></textarea>
    </label>

    <div class="form-actions wide">
      {#if submitError || (draftError && (draft.outcome || draft.lesson))}<span class="close-error" role="alert">{submitError || draftError}</span>{/if}
      <button type="button" class="btn is-small is-ghost" on:click={onCancel}>Cancel</button>
      <button type="submit" class="btn is-small is-primary" disabled={Boolean(draftError) || saving} title={draftError || "Close the idea with this review"}
        >{saving ? "Closing…" : "Close idea"}</button
      >
    </div>
  </form>
</article>

<style>
  .close-form {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
    padding: var(--space-2) var(--space-5) var(--space-5);
  }

  .field {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }

  .field > span {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .segmented {
    justify-self: start;
    max-width: 100%;
    overflow-x: auto;
  }

  .realized-row {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-2) var(--space-5);
    font-size: var(--text-sm);
  }

  .realized-row strong {
    font-family: var(--font-num);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .meta {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .verdict-table {
    min-width: 24rem;
  }

  .form-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .close-error {
    margin-right: auto;
    color: var(--negative);
    font-size: var(--text-xs);
  }
</style>
