<script lang="ts">
  import type { MacroDivergenceSignal, MacroCoherenceProfile, MacroTheme } from "../lib/api/types";

  export let headline: string;
  export let summary: string;
  export let score: number;
  export let label: string;
  export let theme: string;
  export let coherence: MacroCoherenceProfile | null | undefined = null;
  export let primaryDriver: MacroDivergenceSignal | null = null;
  export let counterSignal: MacroDivergenceSignal | null = null;
  export let researchFocus: string | null = null;
  /** Compact mode hides driver/counter detail and trims summary */
  export let compact = false;

  const themeLabels: Record<string, string> = {
    all: "All", growth: "Growth", inflation: "Inflation",
    policy: "Policy", recession_risk: "Recession Risk",
  };

  function toneClass(tone: string | null | undefined): string {
    if (tone === "reinforcing") return "positive";
    if (tone === "opposing") return "negative";
    return "";
  }

  function coherenceTone(label: string | null | undefined): string {
    if (label === "coherent") return "positive";
    if (label === "fractured") return "negative";
    if (label === "narrow") return "warning";
    return "";
  }
</script>

<article class="divergence-card" class:compact>
  <div class="card-head">
    <div class="head-left">
      <small class="eyebrow">{themeLabels[theme] ?? theme}</small>
      <h3>{headline}</h3>
    </div>
    <div class="card-badges">
      <span class="score-badge {label}">{score.toFixed(1)}</span>
      {#if !compact}
        <span class="tag tone-tag">{label}</span>
      {/if}
    </div>
  </div>

  <p class="card-summary" class:clamped={compact}>{summary}</p>

  {#if coherence}
    <div class="coherence-inline">
      <span class="tag {coherenceTone(coherence.coherence_label)}">{coherence.coherence_label}</span>
      <span class="coherence-stat">{coherence.supporting_signals} confirm · {coherence.opposing_signals} oppose</span>
      {#if coherence.lag_span_display}
        <span class="coherence-stat">· {coherence.lag_span_display} spread</span>
      {/if}
    </div>
  {/if}

  {#if !compact && (primaryDriver || counterSignal)}
    <div class="signal-grid">
      {#if primaryDriver}
        <div class="signal-brief">
          <div class="signal-head">
            <span class="signal-role">Lead driver</span>
            <span class="signal-score {toneClass(primaryDriver.tone)}">{primaryDriver.signal_score_display}</span>
          </div>
          <strong class="signal-name">{primaryDriver.metric.label}</strong>
          <p class="signal-interp">{primaryDriver.interpretation}</p>
        </div>
      {/if}
      {#if counterSignal}
        <div class="signal-brief">
          <div class="signal-head">
            <span class="signal-role">Counter-signal</span>
            <span class="signal-score {toneClass(counterSignal.tone)}">{counterSignal.signal_score_display}</span>
          </div>
          <strong class="signal-name">{counterSignal.metric.label}</strong>
          <p class="signal-interp">{counterSignal.interpretation}</p>
        </div>
      {/if}
    </div>
  {/if}

  {#if researchFocus && !compact}
    <p class="research-focus">{researchFocus}</p>
  {/if}
</article>

<style>
  .divergence-card {
    display: grid;
    gap: 0.4rem;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.75rem;
  }

  .divergence-card.compact {
    padding: 0.55rem 0.65rem;
    gap: 0.3rem;
  }

  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .head-left {
    display: grid;
    gap: 0.1rem;
    min-width: 0;
  }

  .eyebrow {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.6rem;
    margin: 0;
  }

  h3 { margin: 0; font-size: 0.88rem; }

  .card-badges {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }

  .card-summary {
    color: var(--text-2);
    margin: 0;
    font-size: 0.76rem;
    line-height: 1.4;
  }

  .card-summary.clamped {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Coherence inline row ── */
  .coherence-inline {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    align-items: center;
  }

  .coherence-stat {
    color: var(--text-2);
    font-size: 0.62rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  /* ── Signal grid ── */
  .signal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 0.25rem;
  }

  .signal-brief {
    display: grid;
    gap: 0.15rem;
    padding: 0.35rem 0;
  }

  .signal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
  }

  .signal-role {
    font-size: 0.6rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-2);
  }

  .signal-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.8rem;
    padding: 0.12rem 0.35rem;
    border-radius: 999px;
    border: 1px solid rgba(46, 60, 74, 0.42);
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-1);
    font-size: 0.66rem;
    font-weight: 600;
  }

  .signal-score.positive {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.08);
    color: var(--positive);
  }

  .signal-score.negative {
    border-color: rgba(198, 107, 97, 0.3);
    background: rgba(198, 107, 97, 0.1);
    color: var(--negative);
  }

  .signal-name {
    font-size: 0.76rem;
    line-height: 1.3;
  }

  .signal-interp {
    margin: 0;
    color: var(--text-2);
    font-size: 0.72rem;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .research-focus {
    margin: 0;
    padding: 0.1rem 0 0.1rem 0.5rem;
    border-left: 2px solid rgba(46, 60, 74, 0.35);
    color: var(--text-2);
    font-size: 0.72rem;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Tags ── */
  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: 0.12rem 0.38rem;
    font-size: 0.56rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
  }

  .tag.positive {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.06);
    color: var(--positive);
  }

  .tag.negative {
    border-color: rgba(198, 107, 97, 0.32);
    background: rgba(198, 107, 97, 0.08);
    color: var(--negative);
  }

  .tag.warning {
    border-color: rgba(196, 154, 90, 0.32);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  .tone-tag {
    border-color: rgba(196, 154, 90, 0.24);
    background: rgba(196, 154, 90, 0.06);
    color: var(--accent-2);
  }

  .score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    padding: 0.1rem 0.3rem;
    font-size: 0.64rem;
    font-weight: 600;
    border-radius: 2px;
    border: 1px solid rgba(122, 166, 200, 0.2);
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-1);
  }

  .score-badge.high {
    border-color: rgba(198, 107, 97, 0.35);
    background: rgba(198, 107, 97, 0.1);
    color: var(--negative);
  }

  .score-badge.moderate {
    border-color: rgba(196, 154, 90, 0.3);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  .score-badge.low {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.06);
    color: var(--positive);
  }
</style>
