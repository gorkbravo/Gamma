<script lang="ts">
  import Tooltip from "./Tooltip.svelte";
  import type { ProvenanceBadgeData } from "../lib/provenance";
  import {
    provenanceDetails,
    provenanceStateLabel,
    provenanceTone,
    shortProvenanceTimestamp
  } from "../lib/provenance";

  export let data: ProvenanceBadgeData | null = null;
  export let label: string | null = null;
  export let showTime = true;
  /**
   * `full` spells the state out inline. `dot` collapses to a tone square and
   * keeps every field in the tooltip — use it in dense headers where the
   * metadata would otherwise outweigh the data it describes.
   */
  export let variant: "full" | "dot" = "full";
  /** Set false when the badge sits inside a button/link that already takes focus. */
  export let focusable = true;

  $: tone = data ? provenanceTone(data.state) : "neutral";
  $: stateText = data ? provenanceStateLabel(data.state) : "N/A";
  $: timeText = showTime && data ? shortProvenanceTimestamp(data.retrievedAt) : null;
  $: details = data ? provenanceDetails(data) : [];
  $: warnings = data?.warnings ?? [];
  $: summary = data ? `${stateText}${data.provider ? ` / ${data.provider}` : ""}` : "No provenance metadata";
</script>

<Tooltip placement="bottom" {focusable} label={`Source detail: ${summary}`} maxWidth="26rem">
  {#if variant === "dot"}
    <span class="provenance-dot {tone}" aria-hidden="true"></span>
    {#if label}<span class="dot-label">{label}</span>{/if}
    {#if warnings.length}<span class="warn-count">!{warnings.length}</span>{/if}
  {:else}
    <span class="provenance-badge">
      {#if label}<span class="context-label">{label}</span>{/if}
      <span class="state {tone}">{stateText}</span>
      {#if data?.provider}<span class="provider">{data.provider}</span>{/if}
      {#if data?.qualityLabel}<span class="quality">{data.qualityLabel}</span>{/if}
      {#if timeText}<span class="time">{timeText}</span>{/if}
      {#if data?.transformationNote}<span class="transform" aria-label="Transformed value">ƒ</span>{/if}
      {#if warnings.length}<span class="warn-count">!{warnings.length}</span>{/if}
    </span>
  {/if}

  <svelte:fragment slot="content">
    {#if data}
      <dl class="provenance-detail">
        {#each details as row (row.label)}
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        {/each}
      </dl>
      {#if warnings.length}
        <ul class="provenance-warnings">
          {#each warnings.slice(0, 5) as warning}
            <li>{warning}</li>
          {/each}
          {#if warnings.length > 5}<li>+{warnings.length - 5} more</li>{/if}
        </ul>
      {/if}
    {:else}
      <span>No provenance metadata available.</span>
    {/if}
  </svelte:fragment>
</Tooltip>

<style>
  .provenance-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    height: 18px;
    font-size: var(--text-xs);
    line-height: 1;
    white-space: nowrap;
    cursor: default;
  }

  .provenance-dot {
    width: 7px;
    height: 7px;
    flex-shrink: 0;
    border-radius: var(--radius-sm);
    background: var(--text-2);
  }

  .provenance-dot.positive {
    background: var(--positive);
  }

  .provenance-dot.warning {
    background: var(--warning);
  }

  .provenance-dot.negative {
    background: var(--negative);
  }

  .dot-label {
    margin-left: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }

  .context-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .state {
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    color: var(--text-1);
  }

  .state.positive {
    color: var(--positive);
    border-color: rgba(75, 180, 116, 0.45);
  }

  .state.warning {
    color: var(--warning);
    border-color: rgba(196, 154, 90, 0.45);
  }

  .state.negative {
    color: var(--negative);
    border-color: rgba(198, 107, 97, 0.45);
  }

  .provider {
    color: var(--text-1);
    font-weight: 600;
  }

  .time {
    color: var(--text-2);
  }

  .quality {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .transform {
    color: var(--text-2);
    font-style: italic;
    font-weight: 700;
  }

  .warn-count {
    margin-left: var(--space-2);
    color: var(--warning);
    font-size: var(--text-2xs);
    font-weight: 700;
  }

  .provenance-detail {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: var(--space-1) var(--space-4);
    margin: 0;
  }

  .provenance-detail dt {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .provenance-detail dd {
    margin: 0;
    color: var(--text-1);
  }

  .provenance-warnings {
    margin: 0;
    padding-left: var(--space-5);
    color: var(--warning);
  }
</style>
