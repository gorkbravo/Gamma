<script lang="ts">
  // Review section of the Idea view (Workstream 12, I3b): the review written
  // at the current close, frozen as written, beside the hypothetical record as
  // it stood at close and as it stands now (the exit close can land later).
  // Earlier reviews of a reopened idea stay listed; none is ever edited.
  import WhatIsThis from "./WhatIsThis.svelte";
  import type { Idea, IdeaReview, IdeaTrackingResponse } from "../lib/api/types";
  import {
    EVIDENCE_VERDICT_LABELS,
    REVIEW_OUTCOME_LABELS,
    formatHoldingDays,
    outcomeTone,
    verdictTone,
  } from "../lib/idea-review";
  import { TRACKING_LABEL, formatTrackingReturn, returnTone } from "../lib/idea-tracking";
  import { EVIDENCE_STANCE_LABELS, formatIdeaInstant } from "../lib/ideas";

  export let idea: Idea;
  export let tracking: IdeaTrackingResponse | null = null;

  $: reviews = idea.reviews ?? [];
  $: current = idea.closed_at ? (reviews.at(-1)?.closed_at === idea.closed_at ? reviews.at(-1) ?? null : null) : null;
  $: shown = current ?? reviews.at(-1) ?? null;
  $: earlier = reviews.filter((review) => review !== shown).reverse();
  $: now = tracking && tracking.idea_id === idea.idea_id ? tracking.summary : null;
  $: fired = (shown?.criteria_at_close ?? []).filter((item) => item.triggered_at);

  function realizedText(review: IdeaReview): string {
    const realized = review.realized;
    if (!realized || realized.net_return == null) return "No tracked record";
    return `Net ${formatTrackingReturn(realized.net_return)} · gross ${formatTrackingReturn(realized.gross_return)} · ${realized.benchmark ?? "benchmark"} ${formatTrackingReturn(realized.benchmark_return)} · as of ${realized.as_of ?? "N/A"}`;
  }
</script>

{#if shown}
  <article class="panel is-flush review-panel" aria-label="Review">
    <div class="panel-title">
      <h3>
        Review
        {#if !current}<span class="header-meta">· from an earlier close; the idea was reopened</span>{/if}
      </h3>
      <div class="title-actions">
        <span class="tag {outcomeTone(shown.outcome)}">{REVIEW_OUTCOME_LABELS[shown.outcome]}</span>
        <span class="header-meta">Closed {formatIdeaInstant(shown.closed_at)} · held {formatHoldingDays(shown.holding_days).toLowerCase()}</span>
      </div>
    </div>
    <table class="data-table is-keyvalue is-compact review-facts">
      <tbody>
        <tr><th>Expected</th><td class:absent={!shown.expected}>{shown.expected || "Not written"}</td></tr>
        <tr>
          <th>Realized at close</th>
          <td>
            <span class="tag is-tinted context">{TRACKING_LABEL}</span>
            <span class={returnTone(shown.realized?.net_return)}>{realizedText(shown)}</span>
          </td>
        </tr>
        {#if current && now && now.net_return != null}
          <tr>
            <th>Realized now</th>
            <td>
              <span class={returnTone(now.net_return)}>Net {formatTrackingReturn(now.net_return)}</span>
              <span class="meta">as of {now.as_of}{now.final ? " · final, exit priced" : " · exit close pending"}</span>
            </td>
          </tr>
        {/if}
        {#if shown.realized_note}<tr><th>What happened</th><td>{shown.realized_note}</td></tr>{/if}
        <tr><th>Lesson</th><td class="lesson">{shown.lesson}</td></tr>
        <tr>
          <th>Invalidation <WhatIsThis key="stat.invalidation_before_loss" stance={idea.stance} /></th>
          <td class:absent={!fired.some((item) => item.kind === "invalidate")}>
            {#if fired.some((item) => item.kind === "invalidate")}
              Fired before the close{shown.first_invalidation_at ? ` (first met ${formatIdeaInstant(shown.first_invalidation_at)})` : ""}
            {:else if shown.criteria_at_close.some((item) => item.kind === "invalidate")}
              Did not fire
            {:else}
              No invalidation criterion
            {/if}
          </td>
        </tr>
      </tbody>
    </table>

    {#if shown.evidence_verdicts.length}
      <div class="table-scroll">
        <table class="data-table is-compact verdicts-table">
          <thead><tr><th>Evidence</th><th>Stance</th><th>Verdict</th></tr></thead>
          <tbody>
            {#each shown.evidence_verdicts as item (item.evidence_id)}
              <tr>
                <td>{item.title}</td>
                <td>{EVIDENCE_STANCE_LABELS[item.stance]}</td>
                <td><span class="tag {verdictTone(item.verdict)}">{EVIDENCE_VERDICT_LABELS[item.verdict]}</span></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    {#if fired.length}
      <ul class="fired-list" aria-label="Criteria triggered at close">
        {#each fired as item (item.criterion_id)}
          <li><span class="tag" class:warning={item.kind === "invalidate"}>{item.kind}</span> {item.label}</li>
        {/each}
      </ul>
    {/if}

    {#if earlier.length}
      <div class="table-scroll">
        <table class="data-table is-compact earlier-table">
          <thead><tr><th>Earlier close</th><th>Outcome</th><th class="num">Held</th><th>Lesson</th></tr></thead>
          <tbody>
            {#each earlier as review (review.review_id)}
              <tr>
                <td class="num">{formatIdeaInstant(review.closed_at)}</td>
                <td><span class="tag {outcomeTone(review.outcome)}">{REVIEW_OUTCOME_LABELS[review.outcome]}</span></td>
                <td class="num">{formatHoldingDays(review.holding_days)}</td>
                <td>{review.lesson}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </article>
{/if}

<style>
  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    min-width: 0;
  }

  .review-facts td {
    overflow-wrap: anywhere;
  }

  .review-facts .tag {
    margin-right: var(--space-2);
  }

  .lesson {
    color: var(--text-0);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .meta {
    margin-left: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .verdicts-table,
  .earlier-table {
    min-width: 24rem;
  }

  .fired-list {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding: var(--space-3) var(--space-5);
    list-style: none;
    font-size: var(--text-sm);
  }
</style>
