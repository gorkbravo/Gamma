<script lang="ts">
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type { ResearchResult, TimeSeriesPoint } from "../lib/api/types";
  import type { ResearchRunOptions } from "../lib/stores/app";
  import {
    normalizeSyntheticText,
    parseSyntheticText,
    summarizeWeights
  } from "../lib/view-models/research";

  export let result: ResearchResult | null = null;
  export let loading = false;
  export let onRun: (options: ResearchRunOptions) => void;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let onOpenIv: (() => void) | undefined = undefined;

  let scopeType: "single_ticker" | "synthetic_portfolio" = "single_ticker";
  let primarySymbol = "AAPL";
  let benchmarkSymbol = "SPY";
  let lookbackDays = 252;
  let syntheticText = "SPY 0.60\nQQQ 0.40";
  let chartMode:
    | "performance"
    | "relative"
    | "price"
    | "drawdown"
    | "rolling_vol"
    | "rolling_beta"
    | "rolling_corr" = "performance";
  let timeframe: "1M" | "3M" | "6M" | "1Y" | "MAX" = "1Y";
  let inputWarning = "";

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  function submit() {
    if (scopeType === "single_ticker") {
      inputWarning = primarySymbol.trim() ? "" : "Ticker is required.";
      if (inputWarning) {
        return;
      }
      onRun({
        scopeType,
        primarySymbol: primarySymbol.trim().toUpperCase(),
        benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
        lookbackDays
      });
      return;
    }
    const syntheticPositions = parsedSynthetic.filter((item) => Number.isFinite(item.weight) && item.weight > 0);
    if (!syntheticPositions.length) {
      inputWarning = "Synthetic portfolio needs valid positive weights.";
      return;
    }
    inputWarning = "";
    onRun({
      scopeType,
      syntheticPositions,
      benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
      lookbackDays
    });
  }

  function normalizeSynthetic() {
    syntheticText = normalizeSyntheticText(syntheticText);
    inputWarning = "";
  }

  function seedSynthetic() {
    syntheticText = "SPY 0.50\nQQQ 0.30\nIWM 0.20";
    inputWarning = "";
  }

  function slicePoints(points: TimeSeriesPoint[]) {
    if (timeframe === "MAX" || !points.length) {
      return points;
    }
    const latest = new Date(points[points.length - 1].timestamp).getTime();
    const days = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 }[timeframe];
    const cutoff = latest - days * 24 * 60 * 60 * 1000;
    return points.filter((point) => new Date(point.timestamp).getTime() >= cutoff);
  }

  function toChartPoint(point: TimeSeriesPoint) {
    return {
      time: Math.floor(new Date(point.timestamp).getTime() / 1000),
      value: point.value
    };
  }

  function normalizeReturnSeries(points: TimeSeriesPoint[]) {
    let baseValue: number | null = null;
    return points.map((point) => {
      if (baseValue == null) {
        baseValue = point.value;
      }
      return {
        time: Math.floor(new Date(point.timestamp).getTime() / 1000),
        value: baseValue && baseValue !== 0 ? point.value / baseValue : point.value
      };
    });
  }

  function cumulativeFromReturns(points: TimeSeriesPoint[]) {
    let cumulative = 1;
    return points.map((point) => {
      cumulative *= 1 + point.value;
      return {
        time: Math.floor(new Date(point.timestamp).getTime() / 1000),
        value: cumulative
      };
    });
  }

  function rollingStd(points: TimeSeriesPoint[], window = 21) {
    return points
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = points.slice(index + 1 - window, index + 1).map((item) => item.value);
        const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
        const variance = slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(slice.length - 1, 1);
        return {
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: Math.sqrt(variance) * Math.sqrt(252)
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function rollingBetaLike(
    perfPoints: TimeSeriesPoint[],
    benchmarkPoints: TimeSeriesPoint[],
    mode: "beta" | "corr",
    window = 63
  ) {
    const benchmarkByTs = new Map(benchmarkPoints.map((point) => [new Date(point.timestamp).getTime(), point.value]));
    const aligned = perfPoints
      .map((point) => {
        const ts = new Date(point.timestamp).getTime();
        const benchmark = benchmarkByTs.get(ts);
        if (benchmark == null) {
          return null;
        }
        return { ts, perf: point.value, benchmark };
      })
      .filter((point): point is { ts: number; perf: number; benchmark: number } => point !== null);

    return aligned
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = aligned.slice(index + 1 - window, index + 1);
        const perfMean = slice.reduce((sum, item) => sum + item.perf, 0) / slice.length;
        const benchmarkMean = slice.reduce((sum, item) => sum + item.benchmark, 0) / slice.length;
        const covariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) * (item.benchmark - benchmarkMean), 0) /
          Math.max(slice.length - 1, 1);
        const perfVariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) ** 2, 0) / Math.max(slice.length - 1, 1);
        const benchmarkVariance =
          slice.reduce((sum, item) => sum + (item.benchmark - benchmarkMean) ** 2, 0) /
          Math.max(slice.length - 1, 1);
        if (benchmarkVariance <= 0) {
          return null;
        }
        const value =
          mode === "beta"
            ? covariance / benchmarkVariance
            : covariance / Math.sqrt(Math.max(perfVariance, 0) * benchmarkVariance || 1);
        return {
          time: Math.floor(point.ts / 1000),
          value
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  let parsedSynthetic = parseSyntheticText(syntheticText);
  let chartSeries: ChartSeries[] = [];
  let weightBars: RankBarItem[] = [];
  let structureSummary = summarizeWeights(result?.weights ?? []);

  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: structureSummary = summarizeWeights(result?.weights ?? []);
  $: weightBars = (result?.weights ?? []).map((weight) => ({
    label: weight.symbol,
    value: weight.weight,
    tone: "positive"
  }));
  $: {
    const perf = slicePoints(result?.performance_points ?? []);
    const benchmark = slicePoints(result?.benchmark_points ?? []);
    const prices = slicePoints(result?.primary_price_points ?? []);

    if (!result) {
      chartSeries = [];
    } else if (chartMode === "price") {
      chartSeries = prices.length
        ? [
            {
              id: "price",
              label: "Price",
              color: "#e8b260",
              type: "line",
              data: prices.map(toChartPoint)
            }
          ]
        : [];
    } else if (chartMode === "drawdown") {
      let cumulative = 1;
      let peak = 1;
      chartSeries = perf.length
        ? [
            {
              id: "drawdown",
              label: "Drawdown",
              color: "#ff6760",
              type: "area",
              data: perf.map((point) => {
                cumulative *= 1 + point.value;
                peak = Math.max(peak, cumulative);
                return {
                  time: Math.floor(new Date(point.timestamp).getTime() / 1000),
                  value: cumulative / peak - 1
                };
              })
            }
          ]
        : [];
    } else if (chartMode === "rolling_vol") {
      const volSeries = rollingStd(perf);
      chartSeries = volSeries.length
        ? [
            {
              id: "rolling_vol",
              label: "Rolling Vol",
              color: "#6aa8ff",
              type: "line",
              data: volSeries
            }
          ]
        : [];
    } else if (chartMode === "rolling_beta" || chartMode === "rolling_corr") {
      const betaSeries = rollingBetaLike(perf, benchmark, chartMode === "rolling_beta" ? "beta" : "corr");
      chartSeries = betaSeries.length
        ? [
            {
              id: chartMode,
              label: chartMode === "rolling_beta" ? "Rolling Beta" : "Rolling Corr",
              color: chartMode === "rolling_beta" ? "#9bd19f" : "#f3d166",
              type: "line",
              data: betaSeries
            }
          ]
        : [];
    } else if (chartMode === "relative") {
      const perfSeries = cumulativeFromReturns(perf);
      const benchmarkSeries = cumulativeFromReturns(benchmark);
      const benchmarkByTime = new Map(benchmarkSeries.map((point) => [point.time, point.value]));
      const relative = perfSeries
        .map((point) => {
          const benchmarkValue = benchmarkByTime.get(point.time);
          if (benchmarkValue == null || benchmarkValue === 0) {
            return null;
          }
          return {
            time: point.time,
            value: point.value / benchmarkValue - 1
          };
        })
        .filter((point): point is { time: number; value: number } => point !== null);
      chartSeries = relative.length
        ? [
            {
              id: "relative",
              label: "Relative Return",
              color: "#ff9f5a",
              type: "line",
              data: relative
            }
          ]
        : [];
    } else {
      const series: ChartSeries[] = [];
      if (perf.length) {
        series.push({
          id: "research",
          label: "Research",
          color: "#6aa8ff",
          type: "area",
          data: cumulativeFromReturns(perf)
        });
      }
      if (benchmark.length) {
        series.push({
          id: "benchmark",
          label: result.benchmark_symbol,
          color: "#e8b260",
          type: "line",
          lineStyle: "dashed",
          data: cumulativeFromReturns(benchmark)
        });
      }
      chartSeries = series;
    }
  }
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Research Command Deck</h2>
      <p>
        Single-name and synthetic workflows now expose richer builder, structure, and context controls without moving
        analytics out of Python.
      </p>
    </div>
    <div class="action-row">
      <button on:click={submit} disabled={loading}>{loading ? "Running..." : "Run Analysis"}</button>
      <button on:click={() => onOpenRisk?.()} disabled={!result?.snapshot}>Open In Risk</button>
      <button on:click={() => onOpenIv?.()} disabled={result?.scope_type !== "single_ticker"}>Open In IV</button>
    </div>
  </div>

  <div class="layout">
    <article class="panel control-panel">
      <div class="field-grid">
        <label>
          <span>Scope</span>
          <select bind:value={scopeType}>
            <option value="single_ticker">Single Ticker</option>
            <option value="synthetic_portfolio">Synthetic Portfolio</option>
          </select>
        </label>
        <label>
          <span>Benchmark</span>
          <input bind:value={benchmarkSymbol} placeholder="SPY" />
        </label>
        <label>
          <span>Lookback</span>
          <select bind:value={lookbackDays}>
            <option value={126}>126D</option>
            <option value={252}>252D</option>
            <option value={504}>504D</option>
          </select>
        </label>
      </div>

      {#if scopeType === "single_ticker"}
        <label class="field-block">
          <span>Ticker</span>
          <input bind:value={primarySymbol} placeholder="AAPL" />
        </label>
      {:else}
        <label class="field-block">
          <span>Synthetic Portfolio</span>
          <textarea bind:value={syntheticText} rows="6" spellcheck="false"></textarea>
          <small>One line per name, example: `SPY 0.60`</small>
        </label>
        <div class="action-row compact">
          <button on:click={normalizeSynthetic} type="button">Normalize Weights</button>
          <button on:click={seedSynthetic} type="button">Seed Basket</button>
        </div>
      {/if}

      {#if inputWarning}
        <p class="warning">{inputWarning}</p>
      {/if}

      <div class="summary-grid">
        <article><span>Total Return</span><strong>{pct(result?.summary.total_return)}</strong></article>
        <article><span>Annual Return</span><strong>{pct(result?.summary.annual_return)}</strong></article>
        <article><span>Annual Vol</span><strong>{pct(result?.summary.annual_vol)}</strong></article>
        <article><span>Max Drawdown</span><strong>{pct(result?.summary.max_drawdown)}</strong></article>
      </div>
    </article>

    <article class="panel chart-panel">
      <div class="panel-header">
        <div>
          <h3>Research Chart</h3>
          <p>{result ? `${result.observations_count} observations | ${result.benchmark_symbol} benchmark` : "Run a scope to populate chart data"}</p>
        </div>
        <div class="control-row">
          <select bind:value={timeframe}>
            <option value="1M">1M</option>
            <option value="3M">3M</option>
            <option value="6M">6M</option>
            <option value="1Y">1Y</option>
            <option value="MAX">MAX</option>
          </select>
          <select bind:value={chartMode}>
            <option value="performance">Performance</option>
            <option value="relative">Relative</option>
            <option value="price">Price</option>
            <option value="drawdown">Drawdown</option>
            <option value="rolling_vol">Rolling Vol</option>
            <option value="rolling_beta">Rolling Beta</option>
            <option value="rolling_corr">Rolling Corr</option>
          </select>
        </div>
      </div>
      <TimeSeriesChart
        series={chartSeries}
        height={330}
        emptyMessage={scopeType === "synthetic_portfolio" ? "Synthetic chart data will appear here" : "Research chart data will appear here"}
      />
    </article>
  </div>

  <div class="detail-grid">
    <article class="panel">
      <h3>Structure</h3>
      <div class="list">
        <div class="row"><span>Scope</span><strong>{result?.scope_type ?? scopeType}</strong></div>
        <div class="row"><span>Names</span><strong>{result?.weights.length ?? parsedSynthetic.length}</strong></div>
        <div class="row"><span>Top Weight</span><strong>{pct(structureSummary.normalizedTopWeight)}</strong></div>
        <div class="row"><span>Effective Positions</span><strong>{fmt(structureSummary.effectivePositions, 2)}</strong></div>
        <div class="row"><span>Beta / Corr</span><strong>{fmt(result?.summary.beta, 3)} / {fmt(result?.summary.correlation, 3)}</strong></div>
      </div>
    </article>

    <article class="panel">
      <h3>Weights</h3>
      <BarRankChart
        items={weightBars}
        emptyMessage="No research result yet."
        formatValue={(value) => pct(value)}
      />
    </article>

    <article class="panel">
      <h3>Forwarded Context</h3>
      {#if result?.snapshot}
        <div class="list">
          <div class="row"><span>Base Currency</span><strong>{result.snapshot.base_currency}</strong></div>
          <div class="row"><span>Benchmark</span><strong>{result.benchmark_symbol}</strong></div>
          <div class="row"><span>Positions</span><strong>{result.snapshot.positions.length}</strong></div>
          <div class="row"><span>Portfolio Value</span><strong>{fmt(result.snapshot.net_liquidation)}</strong></div>
        </div>
      {:else}
        <p class="muted">Snapshot data appears here once analysis completes.</p>
      {/if}
    </article>
  </div>

  <div class="detail-grid second-row">
    <article class="panel">
      <h3>Builder Preview</h3>
      {#if scopeType === "synthetic_portfolio"}
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Symbol</th><th>Weight</th></tr>
            </thead>
            <tbody>
              {#if parsedSynthetic.length}
                {#each parsedSynthetic as item}
                  <tr>
                    <td>{item.symbol}</td>
                    <td>{fmt(item.weight, 4)}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="2">No parsed symbols yet.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="muted">Single-ticker research forwards the selected symbol directly into risk and IV.</p>
      {/if}
    </article>

    <article class="panel span-2">
      <h3>Warnings</h3>
      {#if result?.warnings?.length}
        <div class="list">
          {#each result.warnings as warning}
            <p class="warning">{warning}</p>
          {/each}
        </div>
      {:else}
        <p class="muted">No warnings.</p>
      {/if}
    </article>
  </div>
</section>

<style>
  .view,
  .layout,
  .detail-grid,
  .field-grid,
  .summary-grid,
  .list {
    display: grid;
    gap: 0.9rem;
  }

  .toolbar,
  .panel-header,
  .row,
  .control-row,
  .action-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .layout {
    grid-template-columns: minmax(20rem, 0.95fr) minmax(0, 1.5fr);
    align-items: start;
  }

  .detail-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .second-row {
    grid-template-columns: minmax(18rem, 0.9fr) minmax(0, 2fr);
  }

  .field-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .summary-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .summary-grid article {
    border: 1px solid rgba(19, 32, 44, 0.7);
    background: rgba(5, 8, 11, 0.85);
    padding: 0.85rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: rgba(6, 9, 13, 0.96);
    box-shadow: 0 16px 28px var(--shadow);
    padding: 1rem;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  p,
  span,
  small,
  .muted {
    color: var(--text-2);
  }

  strong {
    color: var(--text-0);
  }

  .field-block,
  label {
    display: grid;
    gap: 0.45rem;
  }

  input,
  select,
  textarea,
  button {
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.75rem 0.85rem;
    font: inherit;
  }

  textarea {
    resize: vertical;
    min-height: 8rem;
  }

  button {
    cursor: pointer;
  }

  .compact {
    justify-content: flex-start;
  }

  .control-row {
    align-items: center;
  }

  .row {
    align-items: center;
    border-bottom: 1px solid rgba(19, 32, 44, 0.7);
    padding-bottom: 0.55rem;
  }

  .warning {
    color: var(--warning);
  }

  .table-wrap {
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.6rem 0.45rem;
    border-bottom: 1px solid rgba(19, 32, 44, 0.7);
    text-align: left;
  }

  .span-2 {
    grid-column: span 2;
  }

  @media (max-width: 1080px) {
    .layout,
    .detail-grid,
    .field-grid,
    .summary-grid,
    .toolbar,
    .second-row {
      grid-template-columns: 1fr;
    }

    .toolbar,
    .panel-header,
    .row,
    .control-row,
    .action-row {
      flex-direction: column;
      align-items: flex-start;
    }

    .control-row {
      width: 100%;
    }

    .control-row select,
    .span-2 {
      width: 100%;
      grid-column: auto;
    }
  }
</style>
