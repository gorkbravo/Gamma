<script lang="ts">
  import type { MacroCoherenceProfile, MacroLeadLagSignal } from "../lib/api/types";

  export let coherence: MacroCoherenceProfile | null | undefined = null;
  /* Compact, for the cards it sits in, drops the summary (the card's own
     summary already says it) and the methodology note. */
  export let compact = false;

  function toneClass(label: string | null | undefined): string {
    if (label === "coherent") return "positive";
    if (label === "fractured") return "negative";
    if (label === "narrow") return "warning";
    return "";
  }

  function scoreTone(tone: string | null | undefined): string {
    if (tone === "reinforcing") return "positive";
    if (tone === "opposing") return "negative";
    return "";
  }

  function signalMeta(signal: MacroLeadLagSignal | null | undefined): string | null {
    if (!signal) return null;
    return [signal.observed_label, signal.lag_label, signal.move_display].filter(Boolean).join(" · ") || null;
  }

  $: leadLag = [
    { role: "Leader", signal: coherence?.lead_signal ?? null },
    { role: "Laggard", signal: coherence?.lag_signal ?? null },
  ].filter((row) => row.signal !== null);
</script>

{#if coherence}
  <div class:compact class="coherence-panel">
    <div class="coherence-tags">
      <span class="tag is-tinted {toneClass(coherence.coherence_label)}">{coherence.coherence_label}</span>
      <span class="coherence-counts">
        {coherence.supporting_signals} confirm · {coherence.opposing_signals} oppose{#if coherence.lag_span_display} · {coherence.lag_span_display} spread{/if}
      </span>
    </div>

    {#if coherence.summary && !compact}
      <p class="coherence-summary">{coherence.summary}</p>
    {/if}

    {#if leadLag.length}
      <!-- Who moved first and who has not caught up: rule-less stats inside
           the card, never a card inside a card. -->
      <div class="lead-lag-grid">
        {#each leadLag as row (row.role)}
          <div class="lead-lag">
            <span class="lead-lag-label">
              {row.role}
              {#if row.signal?.signal_score_display}
                <b class="lead-lag-score {scoreTone(row.signal.tone)}">{row.signal.signal_score_display}</b>
              {/if}
            </span>
            <strong>{row.signal?.label}</strong>
            {#if signalMeta(row.signal)}
              <small class="lead-lag-meta">{signalMeta(row.signal)}</small>
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    {#if coherence.methodology && !compact}
      <p class="methodology-note">{coherence.methodology}</p>
    {/if}
  </div>
{/if}

<style>
  /* Lives inside a Macro card (a tinted block), so it has no box of its own. */
  .coherence-panel {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }

  .coherence-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }

  /* The chip is .tag.is-tinted from primitives.css; long coherence labels wrap. */
  .tag {
    line-height: 1.2;
    white-space: normal;
  }

  .coherence-counts {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .coherence-summary,
  .methodology-note {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .coherence-summary {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .lead-lag-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .lead-lag {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .lead-lag-label {
    display: flex;
    gap: var(--space-3);
    align-items: baseline;
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .lead-lag strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
    line-height: 1.35;
  }

  .lead-lag-score {
    color: var(--text-1);
    font-family: var(--font-num);
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .lead-lag-score.positive {
    color: var(--positive);
  }

  .lead-lag-score.negative {
    color: var(--negative);
  }

  .lead-lag-meta {
    color: var(--text-2);
    font-family: var(--font-num);
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  .methodology-note {
    padding-left: var(--space-4);
    border-left: 2px solid var(--divider);
  }

  @media (max-width: 900px) {
    .lead-lag-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
