<script lang="ts">
  import MacroDivergenceCard from "./MacroDivergenceCard.svelte";
  import MacroLinkedMarketRow from "./MacroLinkedMarketRow.svelte";
  import MacroMetricRow from "./MacroMetricRow.svelte";
  import type {
    MacroCoherenceProfile,
    MacroDivergenceListResponse,
    MacroDivergenceSignal,
    MacroSnapshot,
    MacroTheme,
    MacroThemeComparison,
  } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;
  export let divergences: MacroDivergenceListResponse | null = null;
  export let theme: MacroTheme = "all";

  const themeLabels: Record<string, string> = {
    all: "All", growth: "Growth", inflation: "Inflation",
    policy: "Policy", recession_risk: "Recession Risk",
  };

  $: crossAssetCards = theme === "all"
    ? snapshot?.cross_asset ?? []
    : (snapshot?.cross_asset ?? []).filter((row) => row.theme === theme);

  function coherenceTone(label: string | null | undefined): string {
    if (label === "coherent") return "positive";
    if (label === "fractured") return "negative";
    if (label === "narrow") return "warning";
    return "";
  }

  function toneClass(tone: string | null | undefined): string {
    if (tone === "reinforcing") return "positive";
    if (tone === "opposing") return "negative";
    return "";
  }
</script>

<div class="cross-asset-layout">
  <!-- Theme comparison cards -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Cross-Asset</p>
        <h3>Do these markets agree?</h3>
      </div>
    </div>
    {#if crossAssetCards.length}
      <div class="card-grid">
        {#each crossAssetCards as card}
          <article class="theme-card">
            <div class="card-head">
              <div class="head-left">
                <small class="eyebrow">{themeLabels[card.theme] ?? card.theme}</small>
                <h3>{card.headline}</h3>
              </div>
              <div class="card-badges">
                {#if card.divergence_score !== null}
                  <span class="score-badge {card.agreement_label}">{card.divergence_score.toFixed(1)}</span>
                {/if}
                <span class="tag tone-tag">{card.agreement_label}</span>
              </div>
            </div>

            <p class="card-summary">{card.summary}</p>

            {#if card.coherence}
              <div class="coherence-inline">
                <span class="tag {coherenceTone(card.coherence.coherence_label)}">{card.coherence.coherence_label}</span>
                <span class="coherence-stat">{card.coherence.supporting_signals} confirm · {card.coherence.opposing_signals} oppose</span>
                {#if card.coherence.lag_span_display}
                  <span class="coherence-stat">· {card.coherence.lag_span_display} spread</span>
                {/if}
              </div>
            {/if}

            {#if card.primary_driver || card.counter_signal}
              <div class="signal-grid">
                {#if card.primary_driver}
                  <div class="signal-brief">
                    <div class="signal-head">
                      <span class="signal-role">Lead driver</span>
                      <span class="signal-score {toneClass(card.primary_driver.tone)}">{card.primary_driver.signal_score_display}</span>
                    </div>
                    <strong class="signal-name">{card.primary_driver.metric.label}</strong>
                    <p class="signal-interp">{card.primary_driver.interpretation}</p>
                  </div>
                {/if}
                {#if card.counter_signal}
                  <div class="signal-brief">
                    <div class="signal-head">
                      <span class="signal-role">Counter-signal</span>
                      <span class="signal-score {toneClass(card.counter_signal.tone)}">{card.counter_signal.signal_score_display}</span>
                    </div>
                    <strong class="signal-name">{card.counter_signal.metric.label}</strong>
                    <p class="signal-interp">{card.counter_signal.interpretation}</p>
                  </div>
                {/if}
              </div>
            {/if}

            {#if card.research_focus}
              <p class="research-focus">{card.research_focus}</p>
            {/if}

            {#if card.linked_markets?.length}
              <div class="linked-markets-section">
                {#each card.linked_markets as market}
                  <MacroLinkedMarketRow {market} />
                {/each}
              </div>
            {/if}

            <MacroMetricRow metrics={card.metrics} compact />
          </article>
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No cross-asset comparisons for this theme.</p>
    {/if}
  </article>

  <!-- Ranked divergences -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Ranked Divergences</p>
        <h3>Best research candidates</h3>
      </div>
    </div>
    {#if (divergences?.divergences ?? []).length}
      <div class="divergence-list">
        {#each divergences?.divergences ?? [] as row}
          <MacroDivergenceCard
            headline={row.headline}
            summary={row.summary}
            score={row.score}
            label={row.label}
            theme={row.theme}
            coherence={row.coherence}
            primaryDriver={row.primary_driver}
            counterSignal={row.counter_signal}
            researchFocus={row.research_focus}
          />
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No divergences ranked for current context.</p>
    {/if}
  </article>
</div>

<style>
  .cross-asset-layout {
    display: grid;
    gap: var(--space-4);
  }

  /* ── Panel ── */
  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
    display: grid;
    gap: var(--space-4);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-5);
    align-items: start;
  }

  .panel-header > div { min-width: 0; }

  /* ── Card grid ── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .theme-card {
    display: grid;
    gap: var(--space-3);
    border: 1px solid var(--panel-border);
    background: var(--surface-soft);
    padding: var(--space-5);
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
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Coherence inline ── */
  .coherence-inline {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }

  .coherence-stat {
    color: var(--text-2);
    font-size: var(--text-2xs);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  /* ── Signal grid ── */
  .signal-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .signal-brief {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-2) 0;
  }

  .signal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .signal-role {
    font-size: var(--text-2xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-2);
  }

  .signal-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.6rem;
    padding: var(--space-1) var(--space-2);
    border-radius: 999px;
    border: 1px solid rgba(46, 60, 74, 0.42);
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-1);
    font-size: var(--text-2xs);
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
    border-left: 2px solid rgba(46, 60, 74, 0.35);
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Linked markets ── */
  .linked-markets-section {
    display: grid;
    gap: 0;
    border-top: 1px solid rgba(46, 60, 74, 0.2);
    padding-top: var(--space-1);
  }

  /* ── Divergence list ── */
  .divergence-list {
    display: grid;
    gap: var(--space-3);
  }

  /* ── Tags ── */
  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-2xs);
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
    padding: var(--space-1) var(--space-2);
    font-size: var(--text-2xs);
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

  /* ── Empty ── */
  .empty-hint {
    color: var(--text-2);
    font-size: var(--text-sm);
    margin: 0;
    padding: var(--space-3) 0;
  }

  /* ── Typography ── */
  .eyebrow {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
    margin: 0;
  }

  h3, p, small { margin: 0; }

  .span-2 { grid-column: span 2; }

  @media (max-width: 1080px) {
    .card-grid { grid-template-columns: 1fr; }
    .signal-grid { grid-template-columns: 1fr; }
    .span-2 { grid-column: auto; }
  }
</style>
