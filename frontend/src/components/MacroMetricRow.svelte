<script lang="ts">
  import type { MacroMetric } from "../lib/api/types";

  export let metrics: MacroMetric[] = [];
  export let compact = false;

  function deltaClass(display: string | null | undefined): string {
    if (!display) return "";
    const trimmed = display.trim();
    if (trimmed.startsWith("+") || trimmed.startsWith("▲")) return "positive";
    if (trimmed.startsWith("-") || trimmed.startsWith("−") || trimmed.startsWith("▼")) return "negative";
    return "";
  }

  function comparisonText(metric: { comparison_region: string | null; comparison_display_value: string | null; gap_display: string | null }) {
    if (!metric.comparison_region || !metric.comparison_display_value) return null;
    return `${metric.comparison_region} ${metric.comparison_display_value}${metric.gap_display ? ` | gap ${metric.gap_display}` : ""}`;
  }
</script>

<div class="metric-row" class:compact>
  {#each metrics as metric}
    <div class="metric">
      <span class="metric-label">{metric.label}</span>
      <strong class="metric-value">{metric.display_value ?? "N/A"}</strong>
      {#if metric.delta_display}
        <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
      {/if}
      {#if comparisonText(metric)}
        <small class="metric-compare">{comparisonText(metric)}</small>
      {/if}
    </div>
  {/each}
</div>

<style>
  .metric-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0;
  }

  .metric {
    padding: var(--space-3) var(--space-4);
    border-left: 1px solid rgba(46, 60, 74, 0.42);
    min-width: 0;
    flex: 1 1 4.5rem;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric-label {
    display: block;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .metric-value {
    display: block;
    margin-top: var(--space-1);
    font-size: var(--text-lg);
    line-height: 1.25;
  }

  .metric-delta {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .metric-delta.positive { color: var(--positive); }
  .metric-delta.negative { color: var(--negative); }

  .metric-compare {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.35;
  }

  @media (max-width: 640px) {
    .metric {
      padding: var(--space-3) 0;
      border-left: 0;
      flex: 1 1 45%;
    }
  }
</style>
