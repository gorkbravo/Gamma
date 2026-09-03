<script lang="ts">
  import StrategyLabView from "../views/StrategyLabView.svelte";
  import type { StrategyLabCompositionResult } from "../lib/api/types";
  import type { StrategyLabMode as ComposerMode } from "../lib/view-models/research";

  // Leaving Strategy Lab unmounts the view. The toggle reproduces that exactly:
  // the shell swaps the component out, and anything held in component state is
  // gone unless it lives somewhere the shell keeps (GUA-20260903-9).
  let mounted = true;

  const mode = (new URLSearchParams(window.location.search).get("mode") ?? "composer") as ComposerMode;
  const composition = mode === "regime_stress" ? regimeStressComposition() : null;

  function seriesPoint(index: number, value: number) {
    return {
      timestamp: new Date(Date.UTC(2024, 0, 1 + index)).toISOString(),
      value
    };
  }

  function regimeStressComposition(): StrategyLabCompositionResult {
    const returnPoints = Array.from({ length: 400 }, (_, index) =>
      seriesPoint(index, index % 3 === 0 ? -0.006 : 0.004)
    );
    return {
      name: "AUDIT Gold vs Duration",
      value_kind: "return",
      benchmark_column: "SPY",
      benchmark_value_kind: "return",
      metrics: {
        total_return: 0.68,
        annual_return: 0.1496,
        annual_volatility: 0.1125,
        sharpe_ratio: 1.3,
        sortino_ratio: 1.8,
        max_drawdown: -0.1431,
        max_drawdown_duration: 41,
        observation_count: returnPoints.length,
        frequency: "daily",
        periods_per_year: 252,
        start_date: returnPoints[0].timestamp,
        end_date: returnPoints[returnPoints.length - 1].timestamp,
        benchmark_beta: 0.37,
        benchmark_correlation: 0.38,
        upside_capture: 0.6,
        downside_capture: 0.4,
        rolling_window: 63
      },
      returns_points: returnPoints,
      equity_curve_points: returnPoints,
      drawdown_points: returnPoints.slice(0, 8).map((point, index) => ({
        timestamp: point.timestamp,
        value: -0.02 * (index + 1)
      })),
      benchmark_points: returnPoints,
      benchmark_equity_curve_points: returnPoints,
      rolling_points: returnPoints.slice(-6).map((point, index) => ({
        timestamp: point.timestamp,
        rolling_return: 0.0353 - index * 0.002,
        rolling_volatility: 0.1352,
        rolling_beta: 0.37,
        rolling_correlation: 0.38
      })),
      monthly_returns: [],
      annual_returns: [],
      warnings: [],
      source_provider: "uploaded_csv",
      retrieved_at: "2026-09-03T15:00:00Z",
      origin: "playwright.strategy_lab.regime_stress",
      transformation_note: null,
      freshness_label: "derived",
      leg_contributions: {},
      lenses: [],
      overlays: [],
      alignment_diagnostics: {}
    };
  }
</script>

<button type="button" data-testid="toggle-mount" on:click={() => (mounted = !mounted)}>
  {mounted ? "Leave Strategy Lab" : "Return to Strategy Lab"}
</button>

{#if mounted}
  <StrategyLabView
    {mode}
    strategyComposition={composition}
    onAnalyzeStrategy={async () => null}
    onLoadSaved={async () => []}
    onSaveResearch={async () => null}
    onDeleteSaved={async () => false}
  />
{:else}
  <p data-testid="away">Away from Strategy Lab</p>
{/if}
