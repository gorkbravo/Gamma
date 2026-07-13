<script lang="ts">
  import type { ProvenanceBadgeData } from "../lib/provenance";
  import {
    provenanceStateLabel,
    provenanceTitle,
    provenanceTone,
    shortProvenanceTimestamp
  } from "../lib/provenance";

  export let data: ProvenanceBadgeData | null = null;
  export let label: string | null = null;
  export let showTime = true;

  $: tone = data ? provenanceTone(data.state) : "neutral";
  $: stateText = data ? provenanceStateLabel(data.state) : "N/A";
  $: timeText = showTime && data ? shortProvenanceTimestamp(data.retrievedAt) : null;
  $: title = data ? provenanceTitle(data) : "No provenance metadata available.";
</script>

<span class="provenance-badge" {title}>
  {#if label}<span class="context-label">{label}</span>{/if}
  <span class="state {tone}">{stateText}</span>
  {#if data?.provider}<span class="provider">{data.provider}</span>{/if}
  {#if data?.qualityLabel}<span class="quality">{data.qualityLabel}</span>{/if}
  {#if timeText}<span class="time">{timeText}</span>{/if}
  {#if data?.transformationNote}<span class="transform" aria-label="Transformed value">ƒ</span>{/if}
  {#if data?.warnings.length}<span class="warn-count">!{data.warnings.length}</span>{/if}
</span>

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
    color: var(--warning);
    font-weight: 700;
  }
</style>
