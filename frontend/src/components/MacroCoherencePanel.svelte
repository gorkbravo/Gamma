<script lang="ts">
  import type { MacroCoherenceProfile, MacroLeadLagSignal } from "../lib/api/types";

  export let coherence: MacroCoherenceProfile | null | undefined = null;
  export let compact = false;

  function toneClass(label: string | null | undefined): string {
    if (label === "coherent") return "positive";
    if (label === "fractured") return "negative";
    if (label === "narrow") return "warning";
    return "";
  }

  function signalMeta(signal: MacroLeadLagSignal | null | undefined): string | null {
    if (!signal) return null;
    return [signal.observed_label, signal.lag_label, signal.move_display].filter(Boolean).join(" | ") || null;
  }
</script>

{#if coherence}
  <div class:compact class="coherence-panel">
    <div class="coherence-head">
      <div class="coherence-tags">
        <span class="tag {toneClass(coherence.coherence_label)}">{coherence.coherence_label}</span>
        <span class="coherence-counts">{coherence.supporting_signals} confirm</span>
        <span class="coherence-counts">{coherence.opposing_signals} oppose</span>
        {#if coherence.lag_span_display}
          <span class="coherence-counts">{coherence.lag_span_display} spread</span>
        {/if}
      </div>
      <p class="coherence-summary">{coherence.summary}</p>
    </div>

    {#if coherence.lead_signal || coherence.lag_signal}
      <div class="lead-lag-grid">
        {#if coherence.lead_signal}
          <article class="lead-lag-card">
            <div class="lead-lag-top">
              <span class="lead-lag-label">Leader</span>
              {#if coherence.lead_signal.signal_score_display}
                <span class="lead-lag-score {coherence.lead_signal.tone}">{coherence.lead_signal.signal_score_display}</span>
              {/if}
            </div>
            <strong>{coherence.lead_signal.label}</strong>
            {#if signalMeta(coherence.lead_signal)}
              <p class="lead-lag-meta">{signalMeta(coherence.lead_signal)}</p>
            {/if}
          </article>
        {/if}

        {#if coherence.lag_signal}
          <article class="lead-lag-card">
            <div class="lead-lag-top">
              <span class="lead-lag-label">Laggard</span>
              {#if coherence.lag_signal.signal_score_display}
                <span class="lead-lag-score {coherence.lag_signal.tone}">{coherence.lag_signal.signal_score_display}</span>
              {/if}
            </div>
            <strong>{coherence.lag_signal.label}</strong>
            {#if signalMeta(coherence.lag_signal)}
              <p class="lead-lag-meta">{signalMeta(coherence.lag_signal)}</p>
            {/if}
          </article>
        {/if}
      </div>
    {/if}

    {#if coherence.methodology && !compact}
      <p class="methodology-note">{coherence.methodology}</p>
    {/if}
  </div>
{/if}

<style>
  .coherence-panel {
    display: grid;
    gap: 0.35rem;
    padding: 0.45rem 0.55rem;
    border: 1px solid rgba(46, 60, 74, 0.3);
    background: var(--surface-soft);
  }

  .coherence-panel.compact {
    padding: 0.4rem 0.5rem;
    gap: 0.3rem;
  }

  .coherence-head {
    display: grid;
    gap: 0.2rem;
  }

  .coherence-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
  }

  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: 0.15rem 0.42rem;
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    line-height: 1.2;
  }

  .tag.positive {
    border-color: rgba(75, 180, 116, 0.28);
    background: rgba(75, 180, 116, 0.06);
    color: var(--positive);
  }

  .tag.negative {
    border-color: rgba(198, 107, 97, 0.35);
    background: rgba(198, 107, 97, 0.08);
    color: var(--negative);
  }

  .tag.warning {
    border-color: rgba(196, 154, 90, 0.32);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  .coherence-counts {
    color: var(--text-2);
    font-size: 0.64rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .coherence-summary,
  .lead-lag-meta,
  .methodology-note {
    margin: 0;
    color: var(--text-2);
    font-size: 0.72rem;
    line-height: 1.4;
  }

  .lead-lag-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.35rem;
  }

  .lead-lag-card {
    display: grid;
    gap: 0.14rem;
    padding: 0.4rem 0.45rem;
    border: 1px solid rgba(46, 60, 74, 0.28);
    background: rgba(255, 255, 255, 0.015);
  }

  .lead-lag-top {
    display: flex;
    justify-content: space-between;
    gap: 0.4rem;
    align-items: center;
  }

  .lead-lag-label {
    color: var(--text-2);
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .lead-lag-card strong {
    font-size: 0.75rem;
    line-height: 1.35;
  }

  .lead-lag-score {
    font-size: 0.64rem;
    font-weight: 600;
    color: var(--text-1);
  }

  .lead-lag-score.reinforcing {
    color: var(--positive);
  }

  .lead-lag-score.opposing {
    color: var(--negative);
  }

  .methodology-note {
    padding-left: 0.5rem;
    border-left: 2px solid rgba(46, 60, 74, 0.35);
  }

  @media (max-width: 900px) {
    .lead-lag-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
