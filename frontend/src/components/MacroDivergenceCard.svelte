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
        <span class="tag is-tinted context">{label}</span>
      {/if}
    </div>
  </div>

  <p class="card-summary" class:clamped={compact}>{summary}</p>

  {#if coherence}
    <div class="coherence-inline">
      <span class="tag is-tinted {coherenceTone(coherence.coherence_label)}">{coherence.coherence_label}</span>
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
  /* A tinted block on the sheet: the tonal step is the edge. */
  .divergence-card {
    display: grid;
    gap: var(--space-3);
    border-radius: var(--panel-radius);
    background: var(--tint);
    padding: var(--space-5);
  }

  .divergence-card.compact {
    padding: var(--space-4) var(--space-5);
    gap: var(--space-2);
  }

  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .head-left {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  h3 { margin: 0; font-size: var(--text-title); }

  .card-badges {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    flex-shrink: 0;
  }

  .card-summary {
    color: var(--text-2);
    margin: 0;
    font-size: var(--text-sm);
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
    gap: var(--space-2);
    align-items: center;
  }

  .coherence-stat {
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0;
    text-transform: var(--label-case);
  }

  /* ── Signal grid ── */
  .signal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: var(--space-2);
  }

  .signal-brief {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3) 0;
  }

  .signal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .signal-role {
    font-size: var(--text-xs);
    letter-spacing: 0;
    text-transform: var(--label-case);
    color: var(--text-2);
  }

  .signal-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.8rem;
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-pill);
    --pill-fill: var(--accent-soft);
    color: var(--text-1);
    font-size: var(--text-xs);
    font-weight: 600;
    background: linear-gradient(var(--pill-fill), var(--pill-fill)), var(--panel-bg);
  }

  .signal-score.positive {
    --pill-fill: var(--positive-soft);
    color: var(--positive);
  }

  .signal-score.negative {
    --pill-fill: var(--negative-soft);
    color: var(--negative);
  }

  .signal-name {
    font-size: var(--text-sm);
    line-height: 1.3;
  }

  .signal-interp {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .research-focus {
    margin: 0;
    padding: var(--space-1) 0 var(--space-1) var(--space-4);
    border-left: 2px solid color-mix(in srgb, var(--rule-navy) 35%, transparent);
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Tags ──
     The chip, gold agreement label included, is .tag.is-tinted from
     primitives.css. */
  .score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    padding: var(--space-1) var(--space-2);
    font-size: var(--text-2xs);
    font-weight: 600;
    border-radius: var(--radius-pill);
    --pill-fill: var(--accent-soft);
    color: var(--text-1);
    background: linear-gradient(var(--pill-fill), var(--pill-fill)), var(--panel-bg);
  }

  .score-badge.high {
    --pill-fill: var(--negative-soft);
    color: var(--negative);
  }

  .score-badge.moderate {
    --pill-fill: var(--warning-soft);
    color: var(--accent-2);
  }

  .score-badge.low {
    --pill-fill: var(--positive-soft);
    color: var(--positive);
  }
</style>
