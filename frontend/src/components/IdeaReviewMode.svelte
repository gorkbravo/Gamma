<script lang="ts">
  // Review mode of the Ideas tab (Workstream 12, I3b): the user's closed ideas
  // and what that record shows, with each sample size beside its figure.
  // It describes the user's own record only; nothing here scores an idea.
  import WhatIsThis from "./WhatIsThis.svelte";
  import type { IdeaReviewStatsResponse } from "../lib/api/types";
  import { REVIEW_OUTCOMES, REVIEW_OUTCOME_LABELS, formatHoldingDays, outcomeTone, shareText } from "../lib/idea-review";
  import { TRACKING_LABEL, formatTrackingReturn, returnTone } from "../lib/idea-tracking";
  import { formatIdeaInstant } from "../lib/ideas";
  import { activateRowOnKey } from "../lib/row-activation";

  export let stats: IdeaReviewStatsResponse | null = null;
  export let loading = false;
  export let onOpenIdea: (ideaId: string) => void | Promise<void> = () => {};

  $: rows = stats?.rows ?? [];
  $: holding = stats?.holding_days;
  $: realized = stats?.realized;
  $: invalidation = stats?.invalidation;
</script>

<article class="panel is-flush review-mode-panel" aria-label="Closed ideas">
  <div class="panel-title">
    <h3>Closed ideas</h3>
    <div class="title-actions">
      <span class="tag is-tinted context">{TRACKING_LABEL}</span>
      <span class="header-meta">{rows.length} {rows.length === 1 ? "review" : "reviews"} · your own record, no score</span>
    </div>
  </div>

  <div class="review-stats">
    <div class="stat">
      <span>Median holding <WhatIsThis key="stat.holding_time" /></span>
      <strong class:absent={holding?.median == null}>{formatHoldingDays(holding?.median)}</strong>
      <small>{holding?.count ?? 0} closed{holding?.min != null ? ` · ${formatHoldingDays(holding.min).toLowerCase()} to ${formatHoldingDays(holding.max).toLowerCase()}` : ""}</small>
    </div>
    <div class="stat">
      <span>Median net, hypothetical</span>
      <strong class={returnTone(realized?.median_net)} class:absent={realized?.median_net == null}>{formatTrackingReturn(realized?.median_net)}</strong>
      <small>{realized?.count ?? 0} tracked{realized?.untracked ? ` · ${realized.untracked} without a record` : ""}</small>
    </div>
    <div class="stat">
      <span>Median against benchmark</span>
      <strong class={returnTone(realized?.median_excess)} class:absent={realized?.median_excess == null}>{formatTrackingReturn(realized?.median_excess)}</strong>
      <small>{realized?.excess_count ?? 0} with a benchmark</small>
    </div>
    <div class="stat">
      <span>Invalidation before a loss <WhatIsThis key="stat.invalidation_before_loss" /></span>
      <strong class:absent={!invalidation?.losses}>{shareText(invalidation?.losses_with_trigger_before_close ?? 0, invalidation?.losses ?? 0)}</strong>
      <small>{invalidation?.losses_with_invalidation_criteria ?? 0} of the losses had an invalidation rule</small>
    </div>
  </div>

  <div class="table-scroll">
    <table class="data-table is-top review-table">
      <thead>
        <tr>
          <th>Idea</th>
          <th>Outcome</th>
          <th class="num">Closed</th>
          <th class="num">Held</th>
          <th>Expected</th>
          <th class="num">Net (hyp.)</th>
          <th class="num">Vs benchmark</th>
          <th>Invalidation</th>
          <th>Lesson</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.idea_id)}
          <tr class="review-row" tabindex="0" on:click={() => onOpenIdea(row.idea_id)} on:keydown={(event) => activateRowOnKey(event, () => onOpenIdea(row.idea_id))}>
            <td class="idea-cell">
              <strong>{row.title}</strong>
              {#if row.status === "archived" || row.tags.length}
                <span class="meta">{[row.status === "archived" ? "Archived" : "", row.tags.join(", ")].filter(Boolean).join(" · ")}</span>
              {/if}
            </td>
            <td><span class="tag {outcomeTone(row.outcome)}">{REVIEW_OUTCOME_LABELS[row.outcome]}</span></td>
            <td class="num">{formatIdeaInstant(row.closed_at).slice(0, 10)}</td>
            <td class="num">{formatHoldingDays(row.holding_days)}</td>
            <td class="text-cell" class:absent={!row.expected}>{row.expected || "Not written"}</td>
            <td class="num" class:absent={row.net_return == null}>
              <span class={returnTone(row.net_return)}>{row.tracked ? formatTrackingReturn(row.net_return) : "Not tracked"}</span>
              {#if row.tracked}<span class="meta">{row.realized_final ? `final · ${row.realized_as_of}` : `exit pending · ${row.realized_as_of ?? "N/A"}`}</span>{/if}
            </td>
            <td class="num" class:absent={row.excess_return == null}>
              <span class={returnTone(row.excess_return)}>{formatTrackingReturn(row.excess_return)}</span>
              {#if row.benchmark && row.excess_return != null}<span class="meta">vs {row.benchmark}</span>{/if}
            </td>
            <td class:absent={!row.invalidation_criteria}>
              {#if row.first_invalidation_at}
                <span class="tag warning">Fired</span><span class="meta">{formatIdeaInstant(row.first_invalidation_at).slice(0, 10)}</span>
              {:else if row.invalidation_criteria}
                Did not fire
              {:else}
                No rule
              {/if}
            </td>
            <td class="text-cell">{row.lesson}</td>
          </tr>
        {:else}
          <tr class="empty-row">
            <td colspan="9">{loading && !stats ? "Loading…" : "No closed ideas yet. Close an active idea with its review to start your record."}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if rows.length}
    <div class="table-scroll">
      <table class="data-table is-compact outcome-table">
        <thead><tr><th>Outcome</th><th class="num">Ideas</th><th class="num">Median held</th><th class="num">Median net (hyp.)</th></tr></thead>
        <tbody>
          {#each REVIEW_OUTCOMES as outcome}
            <tr>
              <td><span class="tag {outcomeTone(outcome)}">{REVIEW_OUTCOME_LABELS[outcome]}</span></td>
              <td class="num" class:absent={!stats?.outcomes[outcome]}>{stats?.outcomes[outcome] ?? 0}</td>
              <td class="num" class:absent={holding?.median_by_outcome[outcome] == null}>{formatHoldingDays(holding?.median_by_outcome[outcome])}</td>
              <td class="num {returnTone(realized?.median_net_by_outcome[outcome])}" class:absent={realized?.median_net_by_outcome[outcome] == null}
                >{formatTrackingReturn(realized?.median_net_by_outcome[outcome])}</td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</article>

<style>
  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    min-width: 0;
  }

  .review-stats {
    display: flex;
    flex-wrap: wrap;
    padding: 0 var(--space-5) var(--space-3);
  }

  .review-stats .stat {
    padding-inline: 0 var(--space-6);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .review-table {
    min-width: 62rem;
  }

  .review-row {
    cursor: pointer;
  }

  .review-row:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .idea-cell {
    min-width: 12rem;
  }

  .idea-cell strong {
    font-family: var(--font-ui);
  }

  .text-cell {
    min-width: 12rem;
    max-width: 22rem;
    font-family: var(--font-ui);
    white-space: normal;
  }

  .meta {
    display: block;
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .outcome-table {
    min-width: 24rem;
    margin-top: var(--space-4);
  }
</style>
