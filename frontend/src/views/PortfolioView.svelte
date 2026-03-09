<script lang="ts">
  import AllocationDonut from "../components/AllocationDonut.svelte";
  import DiagnosticsPanel, { type DiagnosticsEntry } from "../components/DiagnosticsPanel.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    DiagnosticsResponse,
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
  export let diagnostics: DiagnosticsResponse | null = null;
  export let diagnosticsLog: string[] = [];
  export let consoleEntries: DiagnosticsEntry[] = [];
  export let diagnosticsOpen = false;
  export let diagnosticsLoading = false;
  export let diagnosticsActionLoading = false;
  export let onReloadPerformance: (options: { benchmarkSymbol: string; lookbackDays: number }) => void;
  export let onToggleDiagnostics: () => void;
  export let onRefreshDiagnostics: () => void;
  export let onRunDiagnostics: () => void;
  export let onForceSubscribe: () => void;
  export let onClearHistory: () => void;

  type PortfolioTimeframe = "1m" | "2m" | "1y" | "3y" | "max";

  const allocationPalette = ["#7aa6c8", "#b6c7d8", "#c49a5a", "#4f7f95", "#8f6c4a", "#4a5663"];
  const accountSummaryPriority = [
    { label: "Buying Power", matches: ["BuyingPower"] },
    { label: "Available Funds", matches: ["AvailableFunds"] },
    { label: "Excess Liquidity", matches: ["ExcessLiquidity"] },
    { label: "Initial Margin", matches: ["InitMarginReq"] },
    { label: "Maintenance Margin", matches: ["MaintMarginReq"] },
    { label: "Cushion", matches: ["Cushion"] },
    { label: "Settled Cash", matches: ["SettledCash"] },
    { label: "Total Cash", matches: ["TotalCashValue"] }
  ];
  const performanceTimeframes: Array<{ id: PortfolioTimeframe; label: string; lookbackDays: number }> = [
    { id: "1m", label: "1M", lookbackDays: 21 },
    { id: "2m", label: "2M", lookbackDays: 42 },
    { id: "1y", label: "1Y", lookbackDays: 252 },
    { id: "3y", label: "3Y", lookbackDays: 756 },
    { id: "max", label: "Max", lookbackDays: 5000 }
  ];

  let chartMode: "value" | "growth" | "drawdown" = "growth";
  let benchmarkSymbol = performance?.benchmark_symbol ?? "SPY";
  let selectedTimeframe: PortfolioTimeframe = "1y";
  let search = "";
  let includeCash = true;
  let sortKey: PortfolioSortKey = "base_market_value";
  let descending = true;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  function normalizeBenchmarkSymbol(value: string) {
    return value.trim().toUpperCase() || "SPY";
  }

  function currentLookbackDays() {
    return performanceTimeframes.find((timeframe) => timeframe.id === selectedTimeframe)?.lookbackDays ?? 252;
  }

  function reloadPerformance() {
    benchmarkSymbol = normalizeBenchmarkSymbol(benchmarkSymbol);
    onReloadPerformance({
      benchmarkSymbol,
      lookbackDays: currentLookbackDays()
    });
  }

  function selectTimeframe(timeframe: PortfolioTimeframe) {
    selectedTimeframe = timeframe;
    reloadPerformance();
  }

  function commitBenchmark() {
    reloadPerformance();
  }

  function handleBenchmarkKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      commitBenchmark();
    }
  }

  let currency = "";
  let historyPoints = history?.points ?? [];
  let chartSeries: ChartSeries[] = [];
  let historyStats: { totalReturn: number | null; maxDrawdown: number | null; latestValue: number | null } = {
    totalReturn: null,
    maxDrawdown: null,
    latestValue: null
  };
  let bookDiagnostics = derivePortfolioDiagnostics(snapshot);
  let sortedPositions = filterAndSortPositions([], {
    search: "",
    sortKey: "base_market_value",
    descending: true,
    includeCash: true
  });
  let accountRows: Array<[string, string]> = [];
  let allocationSlices: Array<{
    label: string;
    value: number;
    color: string;
    detail: string;
    unrealizedPnl: number | null;
  }> = [];

  function isCashPosition(symbol: string, secType: string) {
    return secType === "CASH" || symbol.startsWith("CASH");
  }

  function pickAccountSummaryRows(summary: Record<string, string>) {
    const used = new Set<string>();
    const rows: Array<[string, string]> = [];

    for (const item of accountSummaryPriority) {
      const match = Object.entries(summary).find(([key]) =>
        item.matches.some((token) => key.toLowerCase().includes(token.toLowerCase())) && !used.has(key)
      );
      if (match) {
        used.add(match[0]);
        rows.push([item.label, match[1]]);
      }
      if (rows.length >= 6) {
        return rows;
      }
    }

    return [...rows, ...Object.entries(summary).filter(([key]) => !used.has(key)).slice(0, Math.max(0, 6 - rows.length))];
  }

  function buildAllocationSlices(nextSnapshot: PortfolioSnapshot | null) {
    const positions = (nextSnapshot?.positions ?? [])
      .map((position) => ({
        label: position.symbol,
        secType: position.sec_type,
        value: Math.abs(position.base_market_value ?? 0),
        unrealizedPnl: position.unrealized_pnl
      }))
      .filter((position) => position.value > 0);

    const ordered = positions.sort((left, right) => right.value - left.value);
    const total = ordered.reduce((sum, position) => sum + position.value, 0);
    const visible = ordered.slice(0, 5).map((position, index) => ({
      label: position.label,
      value: position.value,
      color: allocationPalette[index % allocationPalette.length],
      detail: isCashPosition(position.label, position.secType) ? "Cash balance" : position.secType,
      unrealizedPnl: position.unrealizedPnl
    }));
    const remaining = ordered.slice(5);
    const otherValue = remaining.reduce((sum, position) => sum + position.value, 0);
    const otherPnl = remaining.reduce(
      (sum, position) => sum + (position.unrealizedPnl ?? 0),
      0
    );
    if (otherValue > 0) {
      visible.push({
        label: "Other",
        value: otherValue,
        color: allocationPalette[allocationPalette.length - 1],
        detail: total > 0 ? `${ordered.length - 5} grouped positions` : "Remaining lines",
        unrealizedPnl: otherPnl
      });
    }
    return visible;
  }

  $: if (performance?.benchmark_symbol) {
    benchmarkSymbol = performance.benchmark_symbol;
  }

  $: currency = snapshot?.base_currency ?? history?.points.at(-1)?.base_currency ?? "";
  $: historyPoints = history?.points ?? [];
  $: bookDiagnostics = derivePortfolioDiagnostics(snapshot);
  $: sortedPositions = filterAndSortPositions(snapshot?.positions ?? [], {
    search,
    sortKey,
    descending,
    includeCash
  });
  $: accountRows = pickAccountSummaryRows(snapshot?.account_summary ?? {});
  $: allocationSlices = buildAllocationSlices(snapshot);
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
          color: "#7aa6c8",
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
          color: "#b65d54",
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
        color: "#7aa6c8",
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
        color: "#c49a5a",
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
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel performance-panel">
        <div class="panel-header top-line">
          <div>
            <p class="eyebrow">Portfolio Monitor</p>
            <h2>Portfolio Performance</h2>
          </div>
          <div class="chart-controls">
            <label class="benchmark-field">
              <span>Benchmark</span>
              <input
                bind:value={benchmarkSymbol}
                placeholder="SPY"
                maxlength="10"
                disabled={loading}
                on:blur={commitBenchmark}
                on:keydown={handleBenchmarkKeydown}
              />
            </label>
            <label class="control-group">
              <span>Timeframe</span>
              <select bind:value={selectedTimeframe} disabled={loading} on:change={() => selectTimeframe(selectedTimeframe)}>
                {#each performanceTimeframes as timeframe}
                  <option value={timeframe.id}>{timeframe.label}</option>
                {/each}
              </select>
            </label>
            <div class="control-group">
              <span>View</span>
              <div class="segmented">
                <button type="button" class:active={chartMode === "growth"} disabled={loading} on:click={() => (chartMode = "growth")}>Growth</button>
                <button type="button" class:active={chartMode === "value"} disabled={loading} on:click={() => (chartMode = "value")}>Value</button>
                <button type="button" class:active={chartMode === "drawdown"} disabled={loading} on:click={() => (chartMode = "drawdown")}>Drawdown</button>
              </div>
            </div>
          </div>
        </div>

        <div class="kpi-grid">
          <article class="metric">
            <span>Net Liquidity</span>
            <strong>{fmt(snapshot?.net_liquidation)} {currency}</strong>
            <small>{snapshot ? `Updated ${new Date(snapshot.timestamp).toLocaleString()}` : "Waiting for snapshot"}</small>
          </article>
          <article class="metric">
            <span>Day P&amp;L</span>
            <strong class:positive={((performance?.day_pnl ?? snapshot?.day_pnl) ?? 0) > 0} class:negative={((performance?.day_pnl ?? snapshot?.day_pnl) ?? 0) < 0}>
              {fmt(performance?.day_pnl ?? snapshot?.day_pnl)} {currency}
            </strong>
            <small>{pct(performance?.day_pnl_pct ?? snapshot?.day_pnl_pct)} | {performance?.day_pnl_source ?? snapshot?.day_pnl_source ?? "no source"}</small>
          </article>
          <article class="metric">
            <span>Gross Exposure</span>
            <strong>{fmt(bookDiagnostics.grossExposure)} {currency}</strong>
            <small>Net {fmt(bookDiagnostics.netExposure)} {currency}</small>
          </article>
          <article class="metric">
            <span>Cash Weight</span>
            <strong>{pct(bookDiagnostics.cashWeight)}</strong>
            <small>{sortedPositions.length} visible lines</small>
          </article>
          <article class="metric">
            <span>Stored Return</span>
            <strong>{pct(historyStats.totalReturn)}</strong>
            <small>{history?.points.length ?? 0} local history points</small>
          </article>
        </div>

        <TimeSeriesChart
          series={chartSeries}
          height={380}
          emptyMessage={
            chartMode === "value"
              ? "Refresh the portfolio to seed local history"
              : "Set a benchmark or timeframe to load the comparison overlay"
          }
        />

        <div class="chart-foot">
          <span>
            {performance?.missing_symbols?.length
              ? `Missing history: ${performance.missing_symbols.join(", ")}`
              : "Chart uses the shared portfolio_service output."}
          </span>
          <strong>{historyStats.latestValue == null ? "No latest value" : `${fmt(historyStats.latestValue)} ${currency}`}</strong>
        </div>
      </article>

      <article class="panel positions-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Execution Book</p>
            <h3>Positions</h3>
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

      <article class="panel messages-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Messages</p>
            <h3>Broker &amp; Runtime Messages</h3>
          </div>
        </div>

        {#if consoleEntries.length}
          <div class="message-list">
            {#each consoleEntries as entry}
              <div class:warning={entry.tone === "warning"} class:error={entry.tone === "error"} class:info={entry.tone === "info"} class="message-row">
                <span class="message-tag">{entry.label}</span>
                <p>{entry.message}</p>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No active broker or runtime messages.</p>
        {/if}
      </article>

      <article class="panel diagnostics-toggle-panel">
        <div>
          <p class="eyebrow">Diagnostics</p>
          <h3>System Visibility</h3>
        </div>
        <button class="ghost-button" on:click={onToggleDiagnostics}>
          {diagnosticsOpen ? "Hide Diagnostics" : "Show Diagnostics"}
        </button>
      </article>

      {#if diagnosticsOpen}
        <DiagnosticsPanel
          diagnostics={diagnostics}
          loading={diagnosticsLoading}
          actionLoading={diagnosticsActionLoading}
          log={diagnosticsLog}
          entries={consoleEntries}
          onRefresh={onRefreshDiagnostics}
          onRunDiagnostics={onRunDiagnostics}
          onForceSubscribe={onForceSubscribe}
          onClearHistory={onClearHistory}
        />
      {/if}
    </div>

    <aside class="support-column">
      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Allocation</p>
            <h3>Position Distribution</h3>
          </div>
        </div>
        <AllocationDonut slices={allocationSlices} />
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Diagnostics</p>
            <h3>Book Diagnostics</h3>
          </div>
        </div>
        <div class="stack">
          <div class="row"><span>Largest Position</span><strong>{bookDiagnostics.largestPosition?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Largest Position Weight</span><strong>{pct(bookDiagnostics.largestPosition?.weight)}</strong></div>
          <div class="row"><span>Best Unreal. P&amp;L</span><strong>{bookDiagnostics.bestPnl?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Worst Unreal. P&amp;L</span><strong>{bookDiagnostics.worstPnl?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>History Max DD</span><strong class:negative={(historyStats.maxDrawdown ?? 0) < 0}>{pct(historyStats.maxDrawdown)}</strong></div>
        </div>

        <div class="mini-groups">
          <div>
            <small class="group-label">By Security Type</small>
            <div class="pill-list">
              {#each bookDiagnostics.bySecurityType.slice(0, 5) as bucket}
                <span>{bucket.key}: {bucket.count}</span>
              {/each}
            </div>
          </div>
          <div>
            <small class="group-label">By Currency</small>
            <div class="pill-list">
              {#each bookDiagnostics.byCurrency.slice(0, 5) as bucket}
                <span>{bucket.key}: {bucket.count}</span>
              {/each}
            </div>
          </div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Account</p>
            <h3>Account Summary</h3>
          </div>
        </div>
        {#if accountRows.length}
          <div class="stack">
            {#each accountRows as [key, value]}
              <div class="row">
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
</section>

<style>
  .view,
  .workspace-grid,
  .primary-column,
  .support-column,
  .kpi-grid,
  .stack,
  .table-controls,
  .chart-controls,
  .mini-groups,
  .message-list {
    display: grid;
    gap: 0.95rem;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.9fr) minmax(19rem, 0.92fr);
    align-items: start;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--surface-0);
    padding: 1rem;
  }

  .performance-panel,
  .positions-panel,
  .rail-panel,
  .messages-panel {
    display: grid;
    gap: 0.95rem;
  }

  .panel-header,
  .row,
  .chart-foot,
  .rail-header,
  .diagnostics-toggle-panel {
    display: flex;
    justify-content: space-between;
    gap: 0.85rem;
  }

  .top-line {
    align-items: start;
  }

  .kpi-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .metric {
    border: 1px solid var(--divider);
    background: rgba(8, 13, 18, 0.68);
    padding: 0.72rem 0.78rem;
  }

  .metric strong {
    display: block;
    margin: 0.22rem 0 0.26rem;
    font-size: 1.02rem;
    line-height: 1.2;
  }

  .eyebrow,
  span,
  small,
  .muted {
    color: var(--text-2);
  }

  .eyebrow,
  .group-label {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  .muted,
  .chart-foot span,
  .row strong,
  .row span {
    overflow-wrap: anywhere;
  }

  .chart-controls {
    grid-template-columns: minmax(6rem, 7rem) minmax(8.25rem, 9rem) minmax(0, auto);
    align-items: start;
    justify-items: start;
  }

  .chart-controls label,
  .control-group,
  .checkbox {
    display: grid;
    gap: 0.38rem;
  }

  .benchmark-field input {
    width: 100%;
    min-width: 0;
    text-transform: uppercase;
  }

  .control-group > span,
  .chart-controls label > span {
    color: var(--text-2);
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .table-controls {
    grid-template-columns: minmax(14rem, 1.3fr) repeat(3, auto);
    align-items: center;
    justify-content: end;
  }

  .checkbox {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid var(--divider);
    background: rgba(8, 13, 18, 0.6);
    padding: 0.6rem 0.72rem;
  }

  .checkbox input {
    width: auto;
    padding: 0;
  }

  input,
  select,
  button {
    border: 1px solid var(--panel-strong);
    background: #0b1219;
    color: var(--text-0);
    padding: 0.68rem 0.78rem;
    font: inherit;
  }

  button {
    cursor: pointer;
  }

  .ghost-button {
    background: transparent;
  }

  .segmented {
    display: inline-flex;
    flex-wrap: wrap;
    border: 1px solid var(--panel-strong);
    background: rgba(8, 13, 18, 0.82);
  }

  .segmented button {
    border: 0;
    background: transparent;
    padding-inline: 0.8rem;
  }

  .segmented button.active {
    background: rgba(122, 166, 200, 0.14);
    color: var(--accent);
  }

  .chart-foot,
  .row {
    align-items: center;
    border-top: 1px solid rgba(46, 60, 74, 0.56);
    padding-top: 0.72rem;
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .rail-header {
    align-items: baseline;
  }

  .panel-header > div,
  .chart-foot > span,
  .rail-header > div {
    min-width: 0;
  }

  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.55rem;
  }

  .pill-list span {
    border: 1px solid rgba(122, 166, 200, 0.18);
    background: rgba(122, 166, 200, 0.08);
    color: var(--text-1);
    padding: 0.34rem 0.46rem;
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid var(--divider);
  }

  .message-list {
    max-height: 14rem;
    overflow: auto;
    border: 1px solid var(--divider);
    background: rgba(8, 13, 18, 0.6);
  }

  .message-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr);
    gap: 0.8rem;
    padding: 0.72rem 0.85rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
  }

  .message-row p {
    color: var(--warning);
    line-height: 1.45;
  }

  .message-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.64rem;
  }

  .message-row.error p,
  .message-row.error .message-tag {
    color: var(--warning);
  }

  .message-row.info p,
  .message-row.info .message-tag {
    color: var(--accent-2);
  }

  .diagnostics-toggle-panel {
    align-items: center;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.72rem 0.55rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(8, 13, 18, 0.82);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 980px) {
    .workspace-grid,
    .kpi-grid {
      grid-template-columns: 1fr;
    }

    .support-column {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 1080px) {
    .chart-controls,
    .table-controls,
    .support-column {
      grid-template-columns: 1fr;
    }

    .panel-header,
    .chart-foot,
    .rail-header,
    .diagnostics-toggle-panel,
    .message-row {
      flex-direction: column;
      align-items: stretch;
    }

    .segmented {
      width: 100%;
    }

    .segmented button {
      flex: 1;
    }

    .checkbox,
    .chart-controls label,
    .control-group,
    .table-controls > * {
      width: 100%;
    }

    .message-row {
      display: grid;
      grid-template-columns: 1fr;
    }
  }
</style>
