<script lang="ts">
  import AllocationDonut from "../components/AllocationDonut.svelte";
  import DiagnosticsPanel, { type DiagnosticsEntry } from "../components/DiagnosticsPanel.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { flashOnChange } from "../lib/flash";
  import type {
    DiagnosticsResponse,
    PortfolioHistoryResponse,
    PortfolioPerformanceResponse,
    PortfolioSnapshot,
    ProviderUsageResponse,
    SystemStatus
  } from "../lib/api/types";
  import {
    derivePortfolioDiagnostics,
    derivePortfolioNotices,
    derivePortfolioReadiness,
    derivePositionEmptyState,
    filterAndSortPositions,
    lookbackDaysForPortfolioTimeframe,
    normalizePortfolioBenchmark,
    positionQuoteStatus,
    type PortfolioChartMode,
    type PortfolioHistoryWithMetadata,
    type PortfolioNoticeAction,
    type PortfolioPerformanceWithMetadata,
    type PortfolioSnapshotWithMetadata,
    type PortfolioSortKey,
    type PortfolioTimeframe
  } from "../lib/view-models/portfolio";
  import {
    loadPortfolioHistoryData,
    loadPortfolioPerformanceData,
    loadPortfolioSnapshotData,
    portfolioHistoryRequestState,
    portfolioPerformanceRequestState,
    portfolioPreferences,
    portfolioSnapshotRequestState,
    updatePortfolioPreferences
  } from "../lib/stores/portfolio";

  export let snapshot: PortfolioSnapshot | null = null;
  export let history: PortfolioHistoryResponse | null = null;
  export let performance: PortfolioPerformanceResponse | null = null;
  export let loading = false;
  export let systemStatus: SystemStatus | null = null;
  export let providerUsage: ProviderUsageResponse | null = null;
  export let diagnostics: DiagnosticsResponse | null = null;
  export let diagnosticsLog: string[] = [];
  export let consoleEntries: DiagnosticsEntry[] = [];
  export let diagnosticsOpen = false;
  export let diagnosticsLoading = false;
  export let diagnosticsActionLoading = false;
  export let onRefreshSnapshot: () => unknown | Promise<unknown> = loadPortfolioSnapshotData;
  export let onRetryHistory: () => unknown | Promise<unknown> = loadPortfolioHistoryData;
  export let onReloadPerformance: (options: {
    benchmarkSymbol: string;
    lookbackDays: number;
  }) => unknown | Promise<unknown> = loadPortfolioPerformanceData;
  export let onToggleDiagnostics: () => unknown | Promise<unknown> = () => undefined;
  export let onRefreshDiagnostics: () => unknown | Promise<unknown> = () => undefined;
  export let onRunDiagnostics: () => unknown | Promise<unknown> = () => undefined;
  export let onForceSubscribe: () => unknown | Promise<unknown> = () => undefined;
  export let onClearHistory: () => unknown | Promise<unknown> = () => undefined;

  const allocationPalette = [
    "var(--chart-primary)",
    "var(--text-1)",
    "var(--chart-secondary)",
    "var(--data-cool)",
    "var(--data-warm)",
    "var(--text-2)"
  ];
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
  const performanceTimeframes: Array<{ id: PortfolioTimeframe; label: string }> = [
    { id: "1m", label: "1M" },
    { id: "2m", label: "2M" },
    { id: "1y", label: "1Y" },
    { id: "3y", label: "3Y" },
    { id: "max", label: "Max" }
  ];

  let chartMode: PortfolioChartMode = $portfolioPreferences.chartMode;
  let benchmarkSymbol = $portfolioPreferences.benchmarkSymbol;
  let selectedTimeframe: PortfolioTimeframe = $portfolioPreferences.timeframe;
  let search = "";
  let includeCash = true;
  let sortKey: PortfolioSortKey = "base_market_value";
  let descending = true;
  let clearConfirmationOpen = false;
  let actionInProgress: string | null = null;
  let actionFeedback: { tone: "info" | "success" | "error"; message: string } | null = null;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  const titleCase = (value: string | null | undefined) =>
    String(value ?? "unknown")
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());

  const timeLabel = (value: string | null | undefined) => {
    if (!value) return "Never";
    const parsed = new Date(value);
    return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString("en-US") : value;
  };

  function currentLookbackDays() {
    return lookbackDaysForPortfolioTimeframe(selectedTimeframe);
  }

  async function reloadPerformance() {
    benchmarkSymbol = normalizePortfolioBenchmark(benchmarkSymbol);
    updatePortfolioPreferences({
      benchmarkSymbol,
      timeframe: selectedTimeframe
    });
    return await onReloadPerformance({
      benchmarkSymbol,
      lookbackDays: currentLookbackDays()
    });
  }

  async function selectTimeframe(timeframe: PortfolioTimeframe) {
    selectedTimeframe = timeframe;
    updatePortfolioPreferences({ timeframe });
    await reloadPerformance();
  }

  function selectChartMode(mode: PortfolioChartMode) {
    chartMode = mode;
    updatePortfolioPreferences({ chartMode: mode });
  }

  async function commitBenchmark() {
    await reloadPerformance();
  }

  function handleBenchmarkKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void commitBenchmark();
    }
  }

  function clearPositionFilter() {
    search = "";
    includeCash = true;
  }

  async function runAction(
    label: string,
    action: () => unknown | Promise<unknown>,
    successMessage: string
  ) {
    if (actionInProgress || diagnosticsActionLoading) return;
    actionInProgress = label;
    actionFeedback = { tone: "info", message: `${label} in progress...` };
    try {
      const result = await action();
      if (
        result === false ||
        result === null ||
        (result && typeof result === "object" && "success" in result && result.success === false)
      ) {
        actionFeedback = { tone: "error", message: `${label} did not complete. Open diagnostics for details.` };
      } else {
        actionFeedback = { tone: "success", message: successMessage };
      }
    } catch {
      actionFeedback = { tone: "error", message: `${label} failed. Open diagnostics for details.` };
    } finally {
      actionInProgress = null;
    }
  }

  async function executeNoticeAction(action: PortfolioNoticeAction) {
    switch (action) {
      case "refresh_snapshot":
        await runAction("Snapshot refresh", onRefreshSnapshot, "Portfolio snapshot refresh completed.");
        break;
      case "retry_history":
        await runAction("History retry", onRetryHistory, "Local portfolio history was reloaded.");
        break;
      case "retry_performance":
        await runAction("Performance retry", reloadPerformance, "Portfolio performance was recalculated.");
        break;
      case "force_subscribe":
        await runAction(
          "Account subscription",
          onForceSubscribe,
          "Account subscription request completed; readiness was refreshed."
        );
        break;
      case "diagnostics":
        {
          const result = !diagnosticsOpen
            ? await onToggleDiagnostics()
            : await onRefreshDiagnostics();
          actionFeedback =
            result === null || result === false
              ? {
                  tone: "error",
                  message: "Diagnostics could not be loaded. Retry when the backend is available."
                }
              : { tone: "info", message: "Portfolio diagnostics are available below." };
        }
        break;
    }
  }

  function requestClearHistory() {
    clearConfirmationOpen = true;
    actionFeedback = {
      tone: "info",
      message: "Clear History requires confirmation. No local data has been changed."
    };
  }

  function cancelClearHistory() {
    clearConfirmationOpen = false;
    actionFeedback = {
      tone: "info",
      message: "History clear cancelled. The local snapshot trail was not changed."
    };
  }

  async function confirmClearHistory() {
    await runAction(
      "History clear",
      onClearHistory,
      "Local history was cleared and the prior trail was archived when present."
    );
    clearConfirmationOpen = false;
  }

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
      const match = Object.entries(summary).find(
        ([key]) =>
          item.matches.some((token) => key.toLowerCase().includes(token.toLowerCase())) &&
          !used.has(key)
      );
      if (match) {
        used.add(match[0]);
        rows.push([item.label, formatSummaryValue(match[0], match[1])]);
      }
      if (rows.length >= 6) return rows;
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
      .filter((position) => position.value > 0)
      .sort((left, right) => right.value - left.value);
    const visible = positions.slice(0, 5).map((position, index) => ({
      label: position.label,
      value: position.value,
      color: allocationPalette[index % allocationPalette.length],
      detail: isCashPosition(position.label, position.secType) ? "Cash balance" : position.secType,
      unrealizedPnl: position.unrealizedPnl
    }));
    const remaining = positions.slice(5);
    const otherValue = remaining.reduce((sum, position) => sum + position.value, 0);
    if (otherValue > 0) {
      visible.push({
        label: "Other",
        value: otherValue,
        color: allocationPalette[allocationPalette.length - 1],
        detail: `${remaining.length} grouped positions`,
        unrealizedPnl: remaining.reduce((sum, position) => sum + (position.unrealizedPnl ?? 0), 0)
      });
    }
    return visible;
  }

  let snapshotMetadata: PortfolioSnapshotWithMetadata | null = null;
  let historyMetadata: PortfolioHistoryWithMetadata | null = null;
  let performanceMetadata: PortfolioPerformanceWithMetadata | null = null;
  let currency = "";
  let historyPoints = history?.points ?? [];
  let chartSeries: ChartSeries[] = [];
  let historyStats: {
    totalReturn: number | null;
    maxDrawdown: number | null;
    latestValue: number | null;
  } = { totalReturn: null, maxDrawdown: null, latestValue: null };
  let bookDiagnostics = derivePortfolioDiagnostics(snapshot);
  let sortedPositions = filterAndSortPositions([], {
    search: "",
    sortKey: "base_market_value",
    descending: true,
    includeCash: true
  });
  let accountRows: Array<[string, string]> = [];
  let allocationSlices: ReturnType<typeof buildAllocationSlices> = [];
  let notices = derivePortfolioNotices({
    snapshot,
    history,
    performance,
    snapshotState: $portfolioSnapshotRequestState,
    historyState: $portfolioHistoryRequestState,
    performanceState: $portfolioPerformanceRequestState
  });
  let readiness = derivePortfolioReadiness({
    snapshot,
    history,
    performance,
    snapshotState: $portfolioSnapshotRequestState,
    historyState: $portfolioHistoryRequestState,
    performanceState: $portfolioPerformanceRequestState
  });
  let positionEmptyState = derivePositionEmptyState({
    snapshot,
    snapshotStatus: $portfolioSnapshotRequestState.status,
    filteredCount: 0,
    search,
    includeCash
  });
  let primaryConsoleEntries: DiagnosticsEntry[] = [];

  $: snapshotMetadata = snapshot as PortfolioSnapshotWithMetadata | null;
  $: historyMetadata = history as PortfolioHistoryWithMetadata | null;
  $: performanceMetadata = performance as PortfolioPerformanceWithMetadata | null;
  $: currency = snapshot?.base_currency ?? history?.points.at(-1)?.base_currency ?? "";
  $: historyPoints = history?.points ?? [];
  $: bookDiagnostics = derivePortfolioDiagnostics(snapshot);
  $: sortedPositions = filterAndSortPositions(snapshot?.positions ?? [], {
    search,
    sortKey,
    descending,
    includeCash
  });
  $: positionEmptyState = derivePositionEmptyState({
    snapshot,
    snapshotStatus: $portfolioSnapshotRequestState.status,
    filteredCount: sortedPositions.length,
    search,
    includeCash
  });
  $: primaryConsoleEntries = notices
    .filter((notice) => notice.tone !== "info")
    .map((notice) => ({
      label: notice.title,
      message: notice.detail,
      tone: notice.tone === "error" ? "error" as const : "warning" as const
    }));
  $: accountRows = pickAccountSummaryRows(snapshot?.account_summary ?? {});
  $: allocationSlices = buildAllocationSlices(snapshot);
  $: notices = derivePortfolioNotices({
    snapshot,
    history,
    performance,
    snapshotState: $portfolioSnapshotRequestState,
    historyState: $portfolioHistoryRequestState,
    performanceState: $portfolioPerformanceRequestState,
    systemStatus,
    diagnostics
  });
  $: readiness = derivePortfolioReadiness({
    snapshot,
    history,
    performance,
    snapshotState: $portfolioSnapshotRequestState,
    historyState: $portfolioHistoryRequestState,
    performanceState: $portfolioPerformanceRequestState,
    systemStatus,
    diagnostics,
    providerUsage
  });
  $: snapshotBusy =
    $portfolioSnapshotRequestState.initialLoading ||
    $portfolioSnapshotRequestState.refreshing ||
    (loading && $portfolioSnapshotRequestState.status === "idle");
  $: performanceBusy =
    $portfolioPerformanceRequestState.initialLoading ||
    $portfolioPerformanceRequestState.refreshing;
  $: dayPnl = performance?.day_pnl ?? snapshot?.day_pnl ?? null;
  $: dayPnlPct = performance?.day_pnl_pct ?? snapshot?.day_pnl_pct ?? null;
  $: dayPnlSource = performance?.day_pnl_source ?? snapshot?.day_pnl_source ?? null;
  $: historyStats = (() => {
    const values = historyPoints
      .map((point) => point.portfolio_value)
      .filter((value) => Number.isFinite(value));
    if (values.length < 2) {
      return { totalReturn: null, maxDrawdown: null, latestValue: values.at(-1) ?? null };
    }
    let peak = values[0];
    let maxDrawdown = 0;
    for (const value of values) {
      peak = Math.max(peak, value);
      if (peak > 0) maxDrawdown = Math.min(maxDrawdown, value / peak - 1);
    }
    return {
      totalReturn: values.at(-1)! / values[0] - 1,
      maxDrawdown,
      latestValue: values.at(-1) ?? null
    };
  })();
  $: chartSeries = (() => {
    if (chartMode === "value") {
      if (historyPoints.length < 2) return [];
      return [
        {
          id: "portfolio-value",
          label: "Local Snapshot Value",
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
    if (growthPoints.length < 2) return [];
    if (chartMode === "drawdown") {
      let peak = growthPoints[0]?.value ?? 1;
      return [
        {
          id: "drawdown",
          label: "Portfolio Drawdown",
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
  $: chartEmptyMessage =
    chartMode === "value"
      ? $portfolioHistoryRequestState.status === "failed"
        ? "LOCAL HISTORY UNAVAILABLE"
        : historyPoints.length < 2
          ? "TWO LOCAL SNAPSHOTS REQUIRED"
          : "NO LOCAL HISTORY"
      : $portfolioPerformanceRequestState.status === "failed"
        ? "PERFORMANCE CALCULATION FAILED"
        : $portfolioPerformanceRequestState.status === "unavailable"
          ? "PERFORMANCE UNAVAILABLE"
          : "NO PERFORMANCE SERIES";
</script>

<section class="view" aria-label="Portfolio monitor">
  <div class="workspace-grid">
    <div class="primary-column">
      <section class="notice-stack" aria-label="Portfolio status" aria-live="polite">
        {#if snapshotBusy && snapshot}
          <div class="refresh-strip" role="status">
            <span>REFRESHING SNAPSHOT...</span>
            <small>Last successful data remains visible.</small>
          </div>
        {/if}
        {#if performanceBusy && performance}
          <div class="refresh-strip" role="status">
            <span>RECALCULATING PERFORMANCE...</span>
            <small>The current chart remains visible.</small>
          </div>
        {/if}
        {#each notices as notice (notice.id)}
          <div
            class="notice"
            class:notice-warning={notice.tone === "warning"}
            class:notice-error={notice.tone === "error"}
            role={notice.tone === "error" ? "alert" : "status"}
          >
            <div>
              <strong>{notice.title}</strong>
              <span>{notice.detail}</span>
            </div>
            {#if notice.action}
              <button
                type="button"
                disabled={Boolean(actionInProgress) || diagnosticsActionLoading}
                on:click={() => executeNoticeAction(notice.action!)}
              >
                {actionInProgress && notice.actionLabel?.toLowerCase().includes(actionInProgress.toLowerCase())
                  ? "WORKING..."
                  : notice.actionLabel}
              </button>
            {/if}
          </div>
        {/each}
      </section>

      {#if actionFeedback}
        <div
          class="action-feedback"
          class:feedback-success={actionFeedback.tone === "success"}
          class:feedback-error={actionFeedback.tone === "error"}
          role={actionFeedback.tone === "error" ? "alert" : "status"}
          aria-live="polite"
        >
          {actionFeedback.message}
        </div>
      {/if}

      <article class="panel performance-panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Portfolio Monitor</p>
            <h2>Portfolio Performance</h2>
            <div class="source-line">
              <span>{readiness.modeLabel}</span>
              <span>{titleCase(snapshotMetadata?.freshness_label)}</span>
              <span>{snapshotMetadata?.source_provider ?? (systemStatus?.mock_mode ? "mock" : "provider unavailable")}</span>
            </div>
          </div>
          <div class="chart-controls">
            <label class="control-group benchmark-field">
              <span>Benchmark</span>
              <input
                bind:value={benchmarkSymbol}
                aria-label="Portfolio performance benchmark"
                placeholder="SPY"
                maxlength="16"
                disabled={performanceBusy}
                on:blur={commitBenchmark}
                on:keydown={handleBenchmarkKeydown}
              />
            </label>
            <label class="control-group">
              <span>Timeframe</span>
              <select
                bind:value={selectedTimeframe}
                aria-label="Portfolio performance timeframe"
                disabled={performanceBusy}
                on:change={() => selectTimeframe(selectedTimeframe)}
              >
                {#each performanceTimeframes as timeframe}
                  <option value={timeframe.id}>{timeframe.label}</option>
                {/each}
              </select>
            </label>
            <div class="control-group">
              <span>View</span>
              <div class="segmented" role="group" aria-label="Portfolio chart view">
                {#each ["growth", "value", "drawdown"] as mode}
                  <button
                    type="button"
                    class:active={chartMode === mode}
                    aria-pressed={chartMode === mode}
                    on:click={() => selectChartMode(mode as PortfolioChartMode)}
                  >
                    {mode === "growth" ? "Growth" : mode === "value" ? "Value" : "Drawdown"}
                  </button>
                {/each}
              </div>
            </div>
          </div>
        </div>

        <div class="kpi-grid">
          <div class="metric">
            <span>Net Liquidity</span>
            <strong use:flashOnChange={{ value: snapshot?.net_liquidation }}>
              {fmt(snapshot?.net_liquidation)} {snapshot?.net_liquidation == null ? "" : currency}
            </strong>
            <small>
              {snapshot
                ? `Snapshot ${timeLabel(snapshotMetadata?.retrieved_at ?? snapshot.timestamp)}`
                : $portfolioSnapshotRequestState.error ?? "No snapshot loaded"}
            </small>
          </div>
          <div class="metric">
            <span>Day P&amp;L</span>
            <strong
              use:flashOnChange={{
                value: dayPnl,
                direction: (dayPnl ?? 0) > 0 ? "up" : (dayPnl ?? 0) < 0 ? "down" : "neutral"
              }}
              class:positive={(dayPnl ?? 0) > 0}
              class:negative={(dayPnl ?? 0) < 0}
            >
              {fmt(dayPnl)} {dayPnl == null ? "" : currency}
            </strong>
            <small>
              {dayPnl == null
                ? "Unavailable from account summary and constituent history"
                : `${pct(dayPnlPct)} · ${titleCase(dayPnlSource)}`}
            </small>
          </div>
          <div class="metric">
            <span>Gross Exposure</span>
            <strong use:flashOnChange={{ value: bookDiagnostics.grossExposure }}>
              {snapshot ? `${fmt(bookDiagnostics.grossExposure)} ${currency}` : "N/A"}
            </strong>
            <small>{snapshot ? `Net ${fmt(bookDiagnostics.netExposure)} ${currency}` : "Snapshot required"}</small>
          </div>
          <div class="metric">
            <span>Cash Weight</span>
            <strong class:elevated={(bookDiagnostics.cashWeight ?? 0) > 0.25}>
              {pct(bookDiagnostics.cashWeight)}
            </strong>
            <small>
              {snapshot?.total_cash == null
                ? "Cash total unavailable in snapshot"
                : `Cash ${fmt(snapshot.total_cash)} ${currency}`}
            </small>
          </div>
          <div class="metric">
            <span>Stored Return</span>
            <strong
              class:positive={(historyStats.totalReturn ?? 0) > 0}
              class:negative={(historyStats.totalReturn ?? 0) < 0}
            >
              {pct(historyStats.totalReturn)}
            </strong>
            <small>
              {historyPoints.length < 2
                ? `${historyPoints.length} local point${historyPoints.length === 1 ? "" : "s"} · two required`
                : `${historyPoints.length} locally accumulated snapshots`}
            </small>
          </div>
        </div>

        <TimeSeriesChart series={chartSeries} height={360} emptyMessage={chartEmptyMessage} />

        <div class="chart-foot">
          <span>
            {#if chartMode === "value"}
              Local snapshots only · {historyMetadata?.health?.first_timestamp ? timeLabel(historyMetadata.health.first_timestamp) : "range unavailable"}
              to {historyMetadata?.health?.last_timestamp ? timeLabel(historyMetadata.health.last_timestamp) : "latest"}
            {:else if performanceMetadata?.history_coverage_ratio != null}
              Coverage {pct(performanceMetadata.history_coverage_ratio)} · {performanceMetadata.covered_position_count ?? 0}/{performanceMetadata.requested_position_count ?? 0} positions
            {:else}
              {performanceMetadata?.transformation_note ?? "Gamma-derived weighted return series"}
            {/if}
          </span>
          <strong>
            {performance?.benchmark_source === "cash_0"
              ? "Benchmark: Cash 0%"
              : performance
                ? `Benchmark: ${performance.benchmark_symbol}`
                : ""}
          </strong>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="table-head">
          <h3>
            Positions
            <span class="count">
              {sortedPositions.length}{snapshot?.positions.length ? ` / ${snapshot.positions.length}` : ""}
            </span>
          </h3>
          <div class="table-controls">
            <input
              bind:value={search}
              aria-label="Filter portfolio positions"
              placeholder="Filter symbol, type, currency"
            />
            <select bind:value={sortKey} aria-label="Sort portfolio positions by">
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
                <th>Quote</th>
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
                {#each sortedPositions as position (position.instrument_id ?? `${position.symbol}:${position.currency}`)}
                  {@const quoteStatus = positionQuoteStatus(snapshot, position)}
                  <tr>
                    <td class="symbol">{position.display_symbol ?? position.symbol}</td>
                    <td>{position.sec_type}</td>
                    <td>{position.currency}</td>
                    <td>
                      <span
                        class="quality-label"
                        class:quality-positive={quoteStatus.tone === "positive"}
                        class:quality-warning={quoteStatus.tone === "warning"}
                        class:quality-negative={quoteStatus.tone === "negative"}
                        title={quoteStatus.detail}
                      >
                        {quoteStatus.label}
                      </span>
                    </td>
                    <td class="num">{fmt(position.quantity, 3)}</td>
                    <td class="num">{fmt(position.avg_cost)}</td>
                    <td class="num">{fmt(position.market_price)}</td>
                    <td class="num">{fmt(position.market_value)}</td>
                    <td class="num">{fmt(position.base_market_value)}</td>
                    <td class="num">{fmt(position.fx_rate, 4)}</td>
                    <td class="num" class:elevated={(position.weight ?? 0) > 0.25}>{pct(position.weight)}</td>
                    <td
                      class="num"
                      class:positive={(position.unrealized_pnl ?? 0) > 0}
                      class:negative={(position.unrealized_pnl ?? 0) < 0}
                    >
                      {fmt(position.unrealized_pnl)}
                    </td>
                  </tr>
                {/each}
              {:else if positionEmptyState}
                <tr>
                  <td colspan="12" class="empty">
                    <div class="table-empty">
                      <strong>{positionEmptyState.title}</strong>
                      <span>{positionEmptyState.detail}</span>
                      {#if positionEmptyState.canClearFilter}
                        <button type="button" on:click={clearPositionFilter}>Clear filter</button>
                      {/if}
                    </div>
                  </td>
                </tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel messages-panel">
        <div class="table-head">
          <h3>Important Warnings <span class="count">{primaryConsoleEntries.length}</span></h3>
          <button class="ghost-button" type="button" on:click={onToggleDiagnostics}>
            {diagnosticsOpen ? "Hide Diagnostics" : "Open Diagnostics"}
          </button>
        </div>
        {#if primaryConsoleEntries.length}
          <div class="message-list" aria-live="polite">
            {#each primaryConsoleEntries.slice(0, 8) as entry}
              <div
                class="message-row"
                class:message-error={entry.tone === "error"}
                class:message-info={entry.tone === "info" || entry.tone === "action"}
                role={entry.tone === "error" ? "alert" : undefined}
              >
                <span class="message-tag">{entry.label}</span>
                <p>{entry.message}</p>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No active portfolio warnings.</p>
        {/if}
      </article>

      {#if diagnosticsOpen}
        <DiagnosticsPanel
          diagnostics={diagnostics}
          loading={diagnosticsLoading}
          actionLoading={diagnosticsActionLoading || Boolean(actionInProgress)}
          log={diagnosticsLog}
          entries={consoleEntries}
          onRefresh={() =>
            runAction("Diagnostics refresh", onRefreshDiagnostics, "Diagnostics status was refreshed.")}
          onRunDiagnostics={() =>
            runAction("Diagnostics run", onRunDiagnostics, "Diagnostics run completed.")}
          onForceSubscribe={() =>
            runAction(
              "Account subscription",
              onForceSubscribe,
              "Account subscription request completed; readiness was refreshed."
            )}
          onClearHistory={requestClearHistory}
        />
      {/if}
    </div>

    <aside class="support-column">
      <article class="panel rail-panel readiness-panel">
        <div class="rail-head">
          <div>
            <p class="eyebrow">Portfolio Readiness</p>
            <h3>{readiness.modeLabel}</h3>
          </div>
          <button
            type="button"
            class="ghost-button"
            disabled={snapshotBusy || Boolean(actionInProgress)}
            on:click={() =>
              runAction("Snapshot refresh", onRefreshSnapshot, "Portfolio snapshot refresh completed.")}
          >
            {snapshotBusy ? "REFRESHING..." : "Refresh"}
          </button>
        </div>
        <div class="readiness-list">
          {#each readiness.rows as row}
            <div class="readiness-row">
              <span>{row.label}</span>
              <strong
                class:positive={row.tone === "positive"}
                class:warning-value={row.tone === "warning"}
                class:negative={row.tone === "negative"}
              >
                {row.value}
              </strong>
              <small>{row.detail}</small>
            </div>
          {/each}
        </div>
        <div class="refresh-history">
          <span>Last success</span><strong>{timeLabel(readiness.lastSuccessfulRefresh)}</strong>
          <span>Last failure</span><strong>{timeLabel(readiness.lastFailure)}</strong>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-head"><h3>Allocation</h3></div>
        <AllocationDonut slices={allocationSlices} />
      </article>

      <article class="panel rail-panel">
        <div class="rail-head"><h3>Book Diagnostics</h3></div>
        <div class="stack">
          <div class="row">
            <span>Largest Position</span>
            <strong>{bookDiagnostics.largestPosition?.symbol ?? (snapshot ? "Empty account" : "Snapshot unavailable")}</strong>
          </div>
          <div class="row">
            <span>Largest Weight</span>
            <strong>{bookDiagnostics.largestPosition ? pct(bookDiagnostics.largestPosition.weight) : "No position weights"}</strong>
          </div>
          <div class="row">
            <span>Best Unreal. P&amp;L</span>
            <strong class:positive={Boolean(bookDiagnostics.bestPnl)}>
              {bookDiagnostics.bestPnl?.symbol ?? "No position P&L"}
            </strong>
          </div>
          <div class="row">
            <span>Worst Unreal. P&amp;L</span>
            <strong class:negative={Boolean(bookDiagnostics.worstPnl)}>
              {bookDiagnostics.worstPnl?.symbol ?? "No position P&L"}
            </strong>
          </div>
          <div class="row">
            <span>History Max DD</span>
            <strong class:negative={(historyStats.maxDrawdown ?? 0) < 0}>
              {historyStats.maxDrawdown == null ? "Two local points required" : pct(historyStats.maxDrawdown)}
            </strong>
          </div>
        </div>
        {#if bookDiagnostics.bySecurityType.length || bookDiagnostics.byCurrency.length}
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
        {/if}
      </article>

      <article class="panel rail-panel">
        <div class="rail-head"><h3>Account &amp; Data Quality</h3></div>
        {#if accountRows.length}
          <div class="stack">
            {#each accountRows as [key, value]}
              <div class="row"><span>{key}</span><strong>{value}</strong></div>
            {/each}
          </div>
        {:else}
          <p class="muted">
            {snapshotMetadata?.account_subscription_usable === false
              ? "No account summary received. Force a read-only account subscription from diagnostics."
              : snapshot
                ? "The snapshot contains no account summary fields."
                : "Load a snapshot to inspect account-summary readiness."}
          </p>
        {/if}
        <div class="provenance-list">
          <div>
            <span>Snapshot</span>
            <strong>{snapshotMetadata?.source_provider ?? "Unavailable"}</strong>
            <small>{snapshotMetadata?.transformation_note ?? "No snapshot transformation note."}</small>
          </div>
          <div>
            <span>History</span>
            <strong>{historyMetadata?.source_provider ?? history?.source ?? "Unavailable"}</strong>
            <small>Locally accumulated snapshots; never a fictional broker backfill.</small>
          </div>
          <div>
            <span>Performance</span>
            <strong>{performanceMetadata?.source_provider ?? (performance ? "Gamma derived" : "Unavailable")}</strong>
            <small>{performanceMetadata?.transformation_note ?? performance?.message ?? "Weighted from usable constituent or local history."}</small>
            <small>
              Underlying history:
              {performanceMetadata?.history_source_provider ?? performanceMetadata?.history_source ?? "unavailable"}
              · {titleCase(performanceMetadata?.history_freshness_label ?? "unavailable")}.
              {performanceMetadata?.history_transformation_note ?? ""}
            </small>
          </div>
        </div>
        <button
          type="button"
          class="destructive-button"
          aria-haspopup="dialog"
          disabled={diagnosticsActionLoading || Boolean(actionInProgress)}
          on:click={requestClearHistory}
        >
          Clear Local History
        </button>
      </article>
    </aside>
  </div>

  {#if clearConfirmationOpen}
    <div class="dialog-backdrop" role="presentation">
      <div
        class="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="clear-history-title"
        aria-describedby="clear-history-description"
      >
        <p class="eyebrow">Destructive Local Action</p>
        <h2 id="clear-history-title">Clear local portfolio history?</h2>
        <p id="clear-history-description">
          This removes the active base-currency snapshot trail used by Value view and local-history fallback.
          Gamma will archive the prior trail when one exists. Broker history and account state are not changed.
        </p>
        <div class="dialog-actions">
          <button
            type="button"
            disabled={Boolean(actionInProgress)}
            on:click={cancelClearHistory}
          >
            Cancel
          </button>
          <button
            type="button"
            class="destructive-button"
            disabled={Boolean(actionInProgress)}
            on:click={confirmClearHistory}
          >
            {actionInProgress === "History clear" ? "Clearing..." : "Confirm Clear"}
          </button>
        </div>
      </div>
    </div>
  {/if}
</section>

<style>
  .view,
  .workspace-grid,
  .primary-column,
  .support-column,
  .notice-stack {
    display: grid;
    gap: var(--space-4);
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.9fr) minmax(19rem, 0.92fr);
    align-items: start;
    min-width: 0;
    width: 100%;
  }

  .primary-column,
  .support-column {
    align-content: start;
    min-width: 0;
    width: 100%;
  }

  .primary-column {
    grid-template-columns: minmax(0, 1fr);
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

  button,
  input,
  select {
    min-height: 28px;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    padding: var(--space-1) var(--space-4);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  button:hover:not(:disabled) {
    background: var(--hover-bg);
    color: var(--text-0);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
  }

  button:focus-visible,
  input:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .eyebrow {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .count {
    color: var(--text-2);
    font-weight: 500;
    font-size: var(--text-sm);
  }

  .panel-head,
  .table-head,
  .rail-head,
  .chart-foot {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .panel-head {
    align-items: start;
  }

  .table-head {
    align-items: center;
    min-height: 30px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .rail-head {
    align-items: start;
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--divider);
  }

  .source-line {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  .source-line span,
  .quality-label {
    border: 1px solid var(--divider);
    color: var(--text-2);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .notice,
  .refresh-strip,
  .action-feedback {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-3) var(--space-5);
    color: var(--text-1);
  }

  .notice > div {
    display: grid;
    gap: var(--space-1);
  }

  .notice span,
  .refresh-strip small {
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .notice-warning {
    border-color: color-mix(in srgb, var(--warning) 45%, var(--panel-border));
  }

  .notice-warning strong {
    color: var(--warning);
  }

  .notice-error {
    border-color: color-mix(in srgb, var(--negative) 50%, var(--panel-border));
  }

  .notice-error strong,
  .feedback-error {
    color: var(--negative);
  }

  .refresh-strip {
    color: var(--accent);
  }

  .feedback-success {
    color: var(--positive);
  }

  .chart-controls,
  .table-controls {
    display: flex;
    gap: var(--space-3);
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
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-1) var(--space-3);
    font: inherit;
    font-size: var(--text-sm);
  }

  .benchmark-field {
    width: 7rem;
  }

  .benchmark-field input {
    width: 100%;
    min-width: 0;
    text-transform: uppercase;
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
  }

  .segmented button {
    min-height: 26px;
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
  }

  .segmented button:last-child {
    border-right: 0;
  }

  .segmented button.active {
    background: var(--active-bg);
    color: var(--accent);
  }

  .ghost-button {
    min-height: 24px;
    background: transparent;
  }

  .table-controls {
    align-items: center;
  }

  .table-controls input {
    width: 14rem;
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
    min-height: auto;
    width: auto;
    margin: 0;
  }

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
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
    font-size: var(--text-xs);
    color: var(--text-2);
  }

  .chart-foot span {
    min-width: 0;
    overflow-wrap: anywhere;
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
    padding: var(--space-5);
    white-space: normal;
  }

  .table-empty {
    display: grid;
    justify-items: start;
    gap: var(--space-2);
    color: var(--text-2);
  }

  .table-empty strong {
    color: var(--text-1);
  }

  .quality-positive {
    color: var(--positive);
  }

  .quality-warning,
  .warning-value {
    color: var(--warning);
  }

  .quality-negative {
    color: var(--negative);
  }

  .message-list {
    max-height: 12rem;
    overflow: auto;
  }

  .message-row {
    display: grid;
    grid-template-columns: 7rem minmax(0, 1fr);
    gap: var(--space-4);
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
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

  .message-error p,
  .message-error .message-tag {
    color: var(--negative);
  }

  .message-info p,
  .message-info .message-tag {
    color: var(--accent);
  }

  .messages-panel .muted {
    padding: var(--space-3) var(--space-5);
  }

  .muted {
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .readiness-list,
  .stack,
  .provenance-list {
    display: grid;
  }

  .readiness-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-1) var(--space-4);
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--divider);
  }

  .readiness-row > span,
  .row span,
  .provenance-list span,
  .refresh-history span {
    color: var(--text-2);
  }

  .readiness-row small {
    grid-column: 1 / -1;
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .refresh-history {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-2) var(--space-4);
    font-size: var(--text-xs);
  }

  .refresh-history strong {
    text-align: right;
    overflow-wrap: anywhere;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: var(--space-4);
    padding: var(--space-2) 0;
    border-top: 1px solid var(--divider);
    font-size: var(--text-sm);
  }

  .row:first-child {
    border-top: 0;
  }

  .row strong {
    text-align: right;
    overflow-wrap: anywhere;
  }

  .mini-groups {
    display: grid;
    gap: var(--space-3);
  }

  .group-label,
  .provenance-list span {
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
    border: 1px solid var(--divider);
    color: var(--text-1);
    font-size: var(--text-xs);
    padding: var(--space-1) var(--space-3);
  }

  .provenance-list > div {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3) 0;
    border-top: 1px solid var(--divider);
  }

  .provenance-list small {
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .destructive-button {
    border-color: color-mix(in srgb, var(--negative) 55%, var(--panel-strong));
    color: var(--negative);
    background: transparent;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .elevated {
    color: var(--data-warm);
  }

  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    padding: var(--space-6);
    background: color-mix(in srgb, var(--bg-0) 84%, transparent);
  }

  .confirm-dialog {
    width: min(32rem, 100%);
    display: grid;
    gap: var(--space-4);
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    padding: var(--space-6);
  }

  .confirm-dialog > p:not(.eyebrow) {
    color: var(--text-1);
    line-height: var(--leading-normal);
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

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

    .segmented {
      width: 100%;
    }

    .segmented button {
      flex: 1;
    }

    .table-controls input,
    .table-controls select {
      flex: 1;
      min-width: 8rem;
    }
  }

  @media (max-width: 980px) {
    .workspace-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .support-column {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 680px) {
    .support-column {
      grid-template-columns: 1fr;
    }

    .notice,
    .refresh-strip {
      align-items: stretch;
      flex-direction: column;
    }

    .chart-controls,
    .table-controls,
    .dialog-actions {
      display: grid;
      grid-template-columns: 1fr;
      width: 100%;
    }

    .benchmark-field,
    .chart-controls input,
    .chart-controls select,
    .table-controls input,
    .table-controls select,
    .notice button,
    .dialog-actions button {
      width: 100%;
    }
  }
</style>
