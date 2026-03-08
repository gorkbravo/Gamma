<script lang="ts">
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    PortfolioHistoryResponse,
    PortfolioPerformanceResponse,
    PortfolioSnapshot
  } from "../lib/api/types";
  import {
    derivePortfolioDiagnostics,
    filterAndSortPositions,
    type PortfolioSortKey
  } from "../lib/view-models/portfolio";

  export let snapshot: PortfolioSnapshot | null = null;
  export let history: PortfolioHistoryResponse | null = null;
  export let performance: PortfolioPerformanceResponse | null = null;
  export let loading = false;
  export let onRefresh: () => void;
  export let onReloadPerformance: (options: { benchmarkSymbol: string; lookbackDays: number }) => void;

  let chartMode: "value" | "growth" | "drawdown" = "growth";
  let benchmarkSymbol = performance?.benchmark_symbol ?? "SPY";
  let lookbackDays = 504;
  let search = "";
  let includeCash = true;
  let sortKey: PortfolioSortKey = "base_market_value";
  let descending = true;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  function reloadPerformance() {
    onReloadPerformance({
      benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
      lookbackDays
    });
  }

  let currency = "";
  let historyPoints = history?.points ?? [];
  let chartSeries: ChartSeries[] = [];
  let historyStats: { totalReturn: number | null; maxDrawdown: number | null; latestValue: number | null } = {
    totalReturn: null,
    maxDrawdown: null,
    latestValue: null
  };
  let diagnostics = derivePortfolioDiagnostics(snapshot);
  let sortedPositions = filterAndSortPositions([], {
    search: "",
    sortKey: "base_market_value",
    descending: true,
    includeCash: true
  });
  let accountRows: Array<[string, string]> = [];

  $: if (performance?.benchmark_symbol) {
    benchmarkSymbol = performance.benchmark_symbol;
  }
  $: currency = snapshot?.base_currency ?? history?.points.at(-1)?.base_currency ?? "";
  $: historyPoints = history?.points ?? [];
  $: diagnostics = derivePortfolioDiagnostics(snapshot);
  $: sortedPositions = filterAndSortPositions(snapshot?.positions ?? [], {
    search,
    sortKey,
    descending,
    includeCash
  });
  $: accountRows = Object.entries(snapshot?.account_summary ?? {}).slice(0, 10);
  $: historyStats = (() => {
    if (historyPoints.length < 2) {
      return { totalReturn: null, maxDrawdown: null, latestValue: null };
    }
    const values = historyPoints.map((point) => point.portfolio_value).filter((value) => Number.isFinite(value));
    if (values.length < 2) {
      return { totalReturn: null, maxDrawdown: null, latestValue: null };
    }
    let peak = values[0];
    let maxDrawdown = 0;
    for (const value of values) {
      peak = Math.max(peak, value);
      if (peak > 0) {
        maxDrawdown = Math.min(maxDrawdown, value / peak - 1);
      }
    }
    return {
      totalReturn: values.at(-1)! / values[0] - 1,
      maxDrawdown,
      latestValue: values.at(-1) ?? null
    };
  })();
  $: chartSeries = (() => {
    if (chartMode === "value") {
      if (historyPoints.length < 2) {
        return [];
      }
      return [
        {
          id: "portfolio-value",
          label: "Portfolio Value",
          color: "#6aa8ff",
          type: "line",
          data: historyPoints.map((point) => ({
            time: Math.floor(new Date(point.timestamp).getTime() / 1000),
            value: point.portfolio_value
          }))
        }
      ];
    }

    const growthPoints = performance?.performance_points ?? [];
    if (growthPoints.length < 2) {
      return [];
    }
    if (chartMode === "drawdown") {
      let peak = growthPoints[0]?.value ?? 1;
      return [
        {
          id: "drawdown",
          label: "Drawdown",
          color: "#ff6760",
          type: "area",
          data: growthPoints.map((point) => {
            peak = Math.max(peak, point.value);
            return {
              time: Math.floor(new Date(point.timestamp).getTime() / 1000),
              value: peak > 0 ? point.value / peak - 1 : 0
            };
          })
        }
      ];
    }
    const series: ChartSeries[] = [
      {
        id: "portfolio-growth",
        label: "Portfolio",
        color: "#6aa8ff",
        type: "area",
        data: growthPoints.map((point) => ({
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: point.value
        }))
      }
    ];
    if (performance?.benchmark_points?.length) {
      series.push({
        id: "portfolio-benchmark",
        label:
          performance.benchmark_source === "cash_0"
            ? `${performance.benchmark_symbol} (Cash 0%)`
            : performance.benchmark_symbol,
        color: "#e8b260",
        type: "line",
        lineStyle: "dashed",
        data: performance.benchmark_points.map((point) => ({
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: point.value
        }))
      });
    }
    return series;
  })();
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Portfolio Command Deck</h2>
      <p>
        Snapshot, local history, and benchmarked performance all stay on the shared Python service path.
        The browser now exposes the richer book diagnostics and table controls the Qt view already depends on.
      </p>
    </div>
    <div class="action-row">
      <button on:click={reloadPerformance} disabled={loading}>{loading ? "Refreshing..." : "Reload Performance"}</button>
      <button on:click={onRefresh} disabled={loading}>{loading ? "Refreshing..." : "Refresh Snapshot"}</button>
    </div>
  </div>

  <div class="summary-grid">
    <article class="panel metric">
      <span>Net Liq</span>
      <strong>{fmt(snapshot?.net_liquidation)} {currency}</strong>
      <small>{snapshot ? `Updated ${new Date(snapshot.timestamp).toLocaleString()}` : "Waiting for snapshot"}</small>
    </article>
    <article class="panel metric">
      <span>Day P&amp;L</span>
      <strong class:positive={((performance?.day_pnl ?? snapshot?.day_pnl) ?? 0) > 0} class:negative={((performance?.day_pnl ?? snapshot?.day_pnl) ?? 0) < 0}>
        {fmt(performance?.day_pnl ?? snapshot?.day_pnl)} {currency}
      </strong>
      <small>{pct(performance?.day_pnl_pct ?? snapshot?.day_pnl_pct)} | {performance?.day_pnl_source ?? snapshot?.day_pnl_source ?? "no source"}</small>
    </article>
    <article class="panel metric">
      <span>Gross Exposure</span>
      <strong>{fmt(diagnostics.grossExposure)} {currency}</strong>
      <small>Net {fmt(diagnostics.netExposure)} {currency}</small>
    </article>
    <article class="panel metric">
      <span>Cash Weight</span>
      <strong>{pct(diagnostics.cashWeight)}</strong>
      <small>{sortedPositions.length} visible positions</small>
    </article>
    <article class="panel metric">
      <span>Stored Return</span>
      <strong>{pct(historyStats.totalReturn)}</strong>
      <small>{history?.points.length ?? 0} local history points</small>
    </article>
    <article class="panel metric">
      <span>Benchmark Source</span>
      <strong>{performance?.benchmark_source ?? "not loaded"}</strong>
      <small>{performance?.benchmark_symbol ?? benchmarkSymbol}</small>
    </article>
  </div>

  <div class="main-grid">
    <article class="panel chart-panel">
      <div class="panel-header">
        <div>
          <h3>Portfolio Performance</h3>
          <p>
            {chartMode === "value"
              ? history?.source ?? "No history source available yet"
              : performance?.message ?? `${performance?.benchmark_symbol ?? benchmarkSymbol} benchmark overlay`}
          </p>
        </div>
        <div class="chart-controls">
          <label>
            <span>Benchmark</span>
            <input bind:value={benchmarkSymbol} placeholder="SPY" />
          </label>
          <label>
            <span>Lookback</span>
            <select bind:value={lookbackDays}>
              <option value={252}>252D</option>
              <option value={504}>504D</option>
              <option value={756}>756D</option>
            </select>
          </label>
          <div class="segmented">
            <button class:active={chartMode === "growth"} on:click={() => (chartMode = "growth")}>Growth</button>
            <button class:active={chartMode === "value"} on:click={() => (chartMode = "value")}>Value</button>
            <button class:active={chartMode === "drawdown"} on:click={() => (chartMode = "drawdown")}>Drawdown</button>
          </div>
        </div>
      </div>
      <TimeSeriesChart
        series={chartSeries}
        height={340}
        emptyMessage={chartMode === "value" ? "Refresh the portfolio to seed local history" : "Reload performance to compare against the benchmark"}
      />
      <div class="chart-foot">
        <span>
          {performance?.missing_symbols?.length
            ? `Missing history: ${performance.missing_symbols.join(", ")}`
            : "Performance chart is using shared portfolio_service output."}
        </span>
        <strong>{historyStats.latestValue == null ? "No latest value" : `${fmt(historyStats.latestValue)} ${currency}`}</strong>
      </div>
      {#if snapshot?.warnings?.length || performance?.warnings?.length}
        <div class="warning-strip">
          {#each [...(snapshot?.warnings ?? []), ...(performance?.warnings ?? [])] as warning}
            <span>{warning}</span>
          {/each}
        </div>
      {/if}
    </article>

    <aside class="side-column">
      <article class="panel">
        <h3>Book Diagnostics</h3>
        <div class="stack">
          <div class="row"><span>Largest Position</span><strong>{diagnostics.largestPosition?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Best Unreal. P&amp;L</span><strong>{diagnostics.bestPnl?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Worst Unreal. P&amp;L</span><strong>{diagnostics.worstPnl?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>History Max DD</span><strong class:negative={(historyStats.maxDrawdown ?? 0) < 0}>{pct(historyStats.maxDrawdown)}</strong></div>
        </div>
      </article>

      <article class="panel">
        <h3>Structure</h3>
        <div class="pill-list">
          {#each diagnostics.bySecurityType.slice(0, 6) as bucket}
            <span>{bucket.key}: {bucket.count}</span>
          {/each}
        </div>
        <div class="pill-list">
          {#each diagnostics.byCurrency.slice(0, 6) as bucket}
            <span>{bucket.key}: {bucket.count}</span>
          {/each}
        </div>
      </article>

      <article class="panel">
        <h3>Account Summary</h3>
        {#if accountRows.length}
          <div class="history-list">
            {#each accountRows as [key, value]}
              <div class="history-row">
                <span>{key}</span>
                <strong>{value}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No account summary fields in the current snapshot.</p>
        {/if}
      </article>
    </aside>
  </div>

  <article class="panel">
    <div class="panel-header">
      <div>
        <h3>Positions</h3>
        <p>The browser table now carries the key cost, market value, FX, and sort/filter controls from the Qt workflow.</p>
      </div>
      <div class="table-controls">
        <input bind:value={search} placeholder="Filter symbol, type, or currency" />
        <select bind:value={sortKey}>
          <option value="base_market_value">Base Value</option>
          <option value="market_value">Market Value</option>
          <option value="unrealized_pnl">Unrealized P&amp;L</option>
          <option value="weight">Weight</option>
          <option value="market_price">Last</option>
          <option value="quantity">Quantity</option>
          <option value="symbol">Symbol</option>
          <option value="sec_type">SecType</option>
        </select>
        <label class="checkbox">
          <input type="checkbox" bind:checked={descending} />
          <span>Descending</span>
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={includeCash} />
          <span>Include Cash</span>
        </label>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Type</th>
            <th>Currency</th>
            <th>Qty</th>
            <th>Avg Cost</th>
            <th>Last</th>
            <th>Mkt Value</th>
            <th>Base Value</th>
            <th>FX</th>
            <th>Weight</th>
            <th>Unreal. P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#if sortedPositions.length}
            {#each sortedPositions as position}
              <tr>
                <td>{position.symbol}</td>
                <td>{position.sec_type}</td>
                <td>{position.currency}</td>
                <td>{fmt(position.quantity, 3)}</td>
                <td>{fmt(position.avg_cost)}</td>
                <td>{fmt(position.market_price)}</td>
                <td>{fmt(position.market_value)} {position.currency}</td>
                <td>{fmt(position.base_market_value)} {currency}</td>
                <td>{fmt(position.fx_rate, 4)}</td>
                <td>{pct(position.weight)}</td>
                <td class:positive={(position.unrealized_pnl ?? 0) > 0} class:negative={(position.unrealized_pnl ?? 0) < 0}>
                  {fmt(position.unrealized_pnl)} {currency}
                </td>
              </tr>
            {/each}
          {:else}
            <tr><td colspan="11">No matching positions.</td></tr>
          {/if}
        </tbody>
      </table>
    </div>
  </article>
</section>

<style>
  .view,
  .summary-grid,
  .main-grid {
    display: grid;
    gap: 0.9rem;
  }

  .toolbar,
  .panel-header,
  .row,
  .chart-foot,
  .history-row,
  .action-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .toolbar,
  .main-grid {
    align-items: start;
  }

  .summary-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .main-grid {
    grid-template-columns: minmax(0, 2fr) minmax(18rem, 1fr);
  }

  .side-column,
  .stack,
  .history-list,
  .chart-controls {
    display: grid;
    gap: 0.75rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background:
      linear-gradient(180deg, rgba(10, 16, 22, 0.98), rgba(6, 9, 13, 0.98)),
      radial-gradient(circle at top, rgba(106, 168, 255, 0.06), transparent 52%);
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

  .metric strong {
    display: block;
    margin: 0.35rem 0 0.4rem;
    font-size: 1.35rem;
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
    background: rgba(6, 9, 13, 0.85);
  }

  button,
  input,
  select {
    border: 1px solid var(--panel-strong);
    background: rgba(8, 12, 18, 0.95);
    color: var(--text-0);
    padding: 0.75rem 0.95rem;
    cursor: pointer;
    font: inherit;
  }

  .segmented button {
    border: 0;
    padding: 0.55rem 0.85rem;
  }

  .segmented button.active {
    background: rgba(106, 168, 255, 0.16);
    color: var(--accent);
  }

  .chart-panel {
    display: grid;
    gap: 0.85rem;
  }

  .chart-controls {
    grid-template-columns: repeat(3, minmax(0, auto));
    align-items: end;
  }

  .chart-controls label,
  .table-controls,
  .checkbox {
    display: flex;
    gap: 0.55rem;
    align-items: center;
  }

  .table-controls {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .checkbox input {
    width: auto;
    padding: 0;
  }

  .chart-foot {
    align-items: center;
    border-top: 1px solid rgba(19, 32, 44, 0.75);
    padding-top: 0.8rem;
  }

  .warning-strip,
  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .warning-strip span,
  .pill-list span {
    border: 1px solid rgba(210, 154, 82, 0.28);
    background: rgba(210, 154, 82, 0.08);
    color: var(--warning);
    padding: 0.35rem 0.5rem;
  }

  .pill-list span {
    border-color: rgba(106, 168, 255, 0.2);
    background: rgba(106, 168, 255, 0.08);
    color: var(--text-1);
  }

  .row,
  .history-row {
    align-items: center;
    border-bottom: 1px solid rgba(19, 32, 44, 0.75);
    padding-bottom: 0.55rem;
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
    padding: 0.65rem 0.45rem;
    border-bottom: 1px solid rgba(19, 32, 44, 0.75);
    text-align: left;
    white-space: nowrap;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1120px) {
    .summary-grid,
    .main-grid,
    .toolbar,
    .chart-controls {
      grid-template-columns: 1fr;
    }

    .toolbar,
    .panel-header,
    .table-controls,
    .action-row {
      flex-direction: column;
      align-items: stretch;
    }

    .segmented {
      width: 100%;
    }

    .segmented button {
      flex: 1;
    }
  }
</style>
