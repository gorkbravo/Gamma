<script lang="ts">
  import type { MacroLinkedPredictionMarket } from "../lib/api/types";

  export let market: MacroLinkedPredictionMarket;

  function toneClass(label: string | null | undefined): string {
    if (label === "aligned") return "positive";
    if (label === "diverging") return "negative";
    return "";
  }

  function stanceLabel(stance: string | null | undefined): string | null {
    if (!stance) return null;
    if (stance === "policy-easier") return "Easier";
    if (stance === "policy-tighter") return "Tighter";
    return stance.replace(/_/g, " ");
  }

  function badgeTone(label: string | null | undefined): string {
    if (label === "aligned" || label === "coherent") return "positive";
    if (label === "diverging" || label === "fractured") return "negative";
    if (label === "mixed" || label === "narrow") return "warning";
    return "";
  }
</script>

<div class="market-row">
  <div class="market-main">
    <strong class="market-title">{market.title}</strong>
    <div class="market-meta">
      <span class="tag">{market.venue}</span>
      {#if stanceLabel(market.macro_stance)}
        <span class="tag {badgeTone(market.macro_alignment)}">{stanceLabel(market.macro_stance)}</span>
      {/if}
      {#if market.probability_label}
        <span class="meta-stat">{market.probability_label}</span>
      {/if}
      {#if market.change_display}
        <span class="meta-stat {toneClass(market.macro_alignment)}">{market.change_display}</span>
      {/if}
    </div>
  </div>
</div>

<style>
  .market-row {
    padding: var(--space-2) 0;
    border-top: 1px solid rgba(46, 60, 74, 0.18);
  }

  .market-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .market-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  .market-title {
    font-size: var(--text-sm);
    line-height: 1.3;
  }

  .market-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: center;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .meta-stat {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .meta-stat.positive { color: var(--positive); }
  .meta-stat.negative { color: var(--negative); }

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
    border-color: rgba(196, 154, 90, 0.3);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }
</style>
