<script lang="ts">
  import AllocationDonut from "../components/AllocationDonut.svelte";
  import DiagnosticsPanel, { type DiagnosticsEntry } from "../components/DiagnosticsPanel.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { flashOnChange } from "../lib/flash";
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
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

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

  function formatSummaryValue(key: string, raw: string) {
    const numeric = Number(raw);
    const text = Number.isFinite(numeric)
      ? numeric.toLocaleString("en-US", { maximumFractionDigits: 2 })
      : raw;
    const suffix = key.includes(":") ? key.split(":", 2)[1] : "";
    return suffix && suffix !== "BASE" ? `${text} ${suffix}` : text;
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
        rows.push([item.label, formatSummaryValue(match[0], match[1])]);
      }
      if (rows.length >= 6) {
        return rows;
      }
    }

    return [
      ...rows,
      ...Object.entries(summary)
        .filter(([key]) => !used.has(key))
        .slice(0, Math.max(0, 6 - rows.length))
        .map(([key, value]) => [key, formatSummaryValue(key, value)] as [string, string])
    ];
  }

  function buildAllocationSlices(nextSnapshot: PortfolioSnapshot | null) {
    const positions = (nextSnapshot?.positions ?? [])
      .map((position) => ({
        label: position.display_symbol ?? position.symbol,
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
  $: dayPnl = performance?.day_pnl ?? snapshot?.day_pnl ?? null;
  $: dayPnlPct = performance?.day_pnl_pct ?? snapshot?.day_pnl_pct ?? null;
  $: dayPnlSource = performance?.day_pnl_source ?? snapshot?.day_pnl_source ?? null;
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
          color: "var(--chart-primary)",
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
          color: "var(--chart-negative)",
          type: "area",
          invertFilledArea: true,
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
        color: "var(--chart-primary)",
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
        color: "var(--chart-secondary)",
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
        <div class="panel-head">
          <h2>Portfolio Performance</h2>
          <div class="chart-controls">
            <label class="control-group benchmark-field">
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
            <strong use:flashOnChange={{ value: snapshot?.net_liquidation }}>{fmt(snapshot?.net_liquidation)} {currency}</strong>
            <small>{snapshot ? `Updated ${new Date(snapshot.timestamp).toLocaleString("en-US")}` : "Waiting for snapshot"}</small>
          </article>
          <article class="metric">
            <span>Day P&amp;L</span>
            <strong
              use:flashOnChange={{ value: dayPnl, direction: (dayPnl ?? 0) > 0 ? "up" : (dayPnl ?? 0) < 0 ? "down" : "neutral" }}
              class:positive={(dayPnl ?? 0) > 0}
              class:negative={(dayPnl ?? 0) < 0}
            >
              {fmt(dayPnl)} {currency}
            </strong>
            <small>{pct(dayPnlPct)} | {dayPnlSource ?? "no source"}</small>
          </article>
          <article class="metric">
            <span>Gross Exposure</span>
            <strong use:flashOnChange={{ value: bookDiagnostics.grossExposure }}>{fmt(bookDiagnostics.grossExposure)} {currency}</strong>
            <small>Net {fmt(bookDiagnostics.netExposure)} {currency}</small>
          </article>
          <article class="metric">
            <span>Cash Weight</span>
            <strong class:elevated={(bookDiagnostics.cashWeight ?? 0) > 0.25}>{pct(bookDiagnostics.cashWeight)}</strong>
            <small>Cash {fmt(snapshot?.total_cash)} {currency}</small>
          </article>
          <article class="metric">
            <span>Stored Return</span>
            <strong class:positive={(historyStats.totalReturn ?? 0) > 0} class:negative={(historyStats.totalReturn ?? 0) < 0}>{pct(historyStats.totalReturn)}</strong>
            <small>{history?.points.length ?? 0} local history points</small>
          </article>
        </div>

        <TimeSeriesChart
          series={chartSeries}
          height={360}
          emptyMessage={
            chartMode === "value"
              ? "Refresh the portfolio to seed local history"
              : "Set a benchmark or timeframe to load the comparison overlay"
          }
        />

        <div class="chart-foot">
          <span class:warning-text={Boolean(performance?.missing_symbols?.length)}>
            {performance?.missing_symbols?.length
              ? `Missing history: ${performance.missing_symbols.join(", ")}`
              : ""}
          </span>
          <strong>{historyStats.latestValue == null ? "" : `${fmt(historyStats.latestValue)} ${currency}`}</strong>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="table-head">
          <h3>Positions <span class="count">{sortedPositions.length}</span></h3>
          <div class="table-controls">
            <input bind:value={search} placeholder="Filter symbol, type, currency" />
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
              <span>Desc</span>
            </label>
            <label class="checkbox">
              <input type="checkbox" bind:checked={includeCash} />
              <span>Cash</span>
            </label>
          </div>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th>Ccy</th>
                <th class="num">Qty</th>
                <th class="num">Avg Cost</th>
                <th class="num">Last</th>
                <th class="num">Mkt Value</th>
                <th class="num">Base Value</th>
                <th class="num">FX</th>
                <th class="num">Weight</th>
                <th class="num">Unreal. P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {#if sortedPositions.length}
                {#each sortedPositions as position (position.instrument_id ?? position.symbol)}
                  <tr>
                    <td class="symbol">{position.display_symbol ?? position.symbol}</td>
                    <td>{position.sec_type}</td>
                    <td>{position.currency}</td>
                    <td class="num">{fmt(position.quantity, 3)}</td>
                    <td class="num">{fmt(position.avg_cost)}</td>
                    <td class="num">{fmt(position.market_price)}</td>
                    <td class="num">{fmt(position.market_value)}</td>
                    <td class="num">{fmt(position.base_market_value)}</td>
                    <td class="num">{fmt(position.fx_rate, 4)}</td>
                    <td class="num" class:elevated={(position.weight ?? 0) > 0.25}>{pct(position.weight)}</td>
                    <td class="num" class:positive={(position.unrealized_pnl ?? 0) > 0} class:negative={(position.unrealized_pnl ?? 0) < 0}>
                      {fmt(position.unrealized_pnl)}
                    </td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="11" class="empty">No matching positions.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel messages-panel">
        <div class="table-head">
          <h3>Messages <span class="count">{consoleEntries.length}</span></h3>
          <button class="ghost-button" on:click={onToggleDiagnostics}>
            {diagnosticsOpen ? "Hide Diagnostics" : "Diagnostics"}
          </button>
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
        <div class="rail-head">
          <h3>Allocation</h3>
        </div>
        <AllocationDonut slices={allocationSlices} />
      </article>

      <article class="panel rail-panel">
        <div class="rail-head">
          <h3>Book Diagnostics</h3>
        </div>
        <div class="stack">
          <div class="row"><span>Largest Position</span><strong>{bookDiagnostics.largestPosition?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Largest Weight</span><strong>{pct(bookDiagnostics.largestPosition?.weight)}</strong></div>
          <div class="row"><span>Best Unreal. P&amp;L</span><strong class="positive">{bookDiagnostics.bestPnl?.symbol ?? "N/A"}</strong></div>
          <div class="row"><span>Worst Unreal. P&amp;L</span><strong class="negative">{bookDiagnostics.worstPnl?.symbol ?? "N/A"}</strong></div>
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
        <div class="rail-head">
          <h3>Account Summary</h3>
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
  .support-column {
    display: grid;
    gap: var(--space-4);
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
    background: var(--panel-bg);
    padding: var(--space-5);
  }

  .performance-panel,
  .rail-panel {
    display: grid;
    gap: var(--space-4);
  }

  .table-panel,
  .messages-panel {
    padding: 0;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h2 {
    font-size: var(--text-md);
    font-weight: 700;
  }

  h3 {
    font-size: var(--text-base);
    font-weight: 700;
  }

  .count {
    color: var(--text-2);
    font-weight: 500;
    font-size: var(--text-sm);
  }

  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: var(--space-4);
  }

  .table-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-height: 26px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .rail-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--divider);
  }

  /* ── Controls ── */
  .chart-controls {
    display: flex;
    gap: var(--space-4);
    align-items: start;
    flex-wrap: wrap;
  }

  .control-group {
    display: grid;
    gap: var(--space-1);
  }

  .control-group > span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  input,
  select {
    height: 26px;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-1) var(--space-3);
    font: inherit;
    font-size: var(--text-sm);
  }

  select {
    cursor: pointer;
  }

  input:hover,
  select:hover {
    border-color: rgba(122, 166, 200, 0.32);
  }

  .benchmark-field {
    width: 6rem;
  }

  .benchmark-field input {
    width: 100%;
    min-width: 0;
    text-transform: uppercase;
  }

  .segmented {
    display: inline-flex;
    flex-wrap: wrap;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }

  .segmented button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-2);
    padding: var(--space-1) var(--space-4);
    font: inherit;
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: background var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease);
  }

  .segmented button:last-child { border-right: 0; }
  .segmented button:hover:not(:disabled) { background: var(--hover-bg); color: var(--text-0); }
  .segmented button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .segmented button.active { background: var(--active-bg); color: var(--accent); }

  .ghost-button {
    height: 22px;
    border: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0 var(--space-4);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease);
  }

  .ghost-button:hover {
    background: var(--hover-bg);
    color: var(--text-0);
  }

  .table-controls {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }

  .table-controls input[type="text"],
  .table-controls input:not([type="checkbox"]) {
    width: 13rem;
  }

  .checkbox {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-sm);
    cursor: pointer;
    white-space: nowrap;
  }

  .checkbox input {
    height: auto;
    width: auto;
    padding: 0;
    margin: 0;
  }

  /* ── KPI strip ── */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    border-block: 1px solid var(--divider);
  }

  .metric {
    min-width: 0;
    padding: var(--space-3) var(--space-4);
    border-right: 1px solid var(--divider);
  }

  .metric:last-child {
    border-right: 0;
  }

  .metric > span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .metric strong {
    display: block;
    margin: var(--space-1) 0;
    font-size: var(--text-md);
    line-height: var(--leading-tight);
    overflow-wrap: anywhere;
  }

  .metric small {
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
    overflow-wrap: anywhere;
  }

  .chart-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
    font-size: var(--text-xs);
    color: var(--text-2);
    min-height: 1em;
  }

  .chart-foot span {
    overflow-wrap: anywhere;
    min-width: 0;
  }

  .warning-text {
    color: var(--warning);
  }

  /* ── Positions table ── */
  .table-wrap {
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    line-height: var(--leading-tight);
  }

  th {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: var(--surface-0);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  td {
    font-size: var(--text-sm);
  }

  th.num,
  td.num {
    text-align: right;
  }

  td.symbol {
    color: var(--text-0);
    font-weight: 600;
  }

  td.empty {
    color: var(--text-2);
  }

  tbody tr:last-child td {
    border-bottom: 0;
  }

  /* ── Messages ── */
  .message-list {
    max-height: 12rem;
    overflow: auto;
  }

  .message-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr);
    gap: var(--space-4);
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .message-row:last-child {
    border-bottom: 0;
  }

  .message-row p {
    color: var(--warning);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .message-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .message-row.info p,
  .message-row.info .message-tag {
    color: var(--accent-2);
  }

  .messages-panel .muted {
    padding: var(--space-3) var(--space-5);
  }

  .muted {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  /* ── Rail panels ── */
  .stack {
    display: grid;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) 0;
    border-top: 1px solid var(--divider);
    font-size: var(--text-sm);
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .row span {
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  .row strong {
    overflow-wrap: anywhere;
    text-align: right;
  }

  .mini-groups {
    display: grid;
    gap: var(--space-3);
  }

  .group-label {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  .pill-list span {
    border: 1px solid rgba(122, 166, 200, 0.14);
    background: rgba(122, 166, 200, 0.05);
    color: var(--text-1);
    font-size: var(--text-xs);
    padding: var(--space-1) var(--space-3);
  }

  /* ── Semantic values ── */
  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .elevated {
    color: var(--data-warm);
  }

  /* ── Responsive ── */
  @media (max-width: 1080px) {
    .kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .metric {
      border-right: 0;
      border-top: 1px solid var(--divider);
    }

    .metric:first-child,
    .metric:nth-child(2) {
      border-top: 0;
    }

    .panel-head,
    .table-head,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .chart-controls,
    .table-controls {
      flex-wrap: wrap;
    }

    .segmented {
      width: 100%;
    }

    .segmented button {
      flex: 1;
    }

    .table-controls input:not([type="checkbox"]),
    .table-controls select {
      flex: 1;
      min-width: 8rem;
    }
  }

  @media (max-width: 980px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }

    .support-column {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
</style>
