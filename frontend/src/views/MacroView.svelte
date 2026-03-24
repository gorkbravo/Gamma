<script lang="ts">
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroDivergenceListResponse,
    MacroEventsResponse,
    MacroMode,
    MacroSeriesHistory,
    MacroSnapshot,
    MacroTheme,
  } from "../lib/api/types";
  import { macroContext, setMacroContext } from "../lib/stores/app";

  export let snapshot: MacroSnapshot | null = null;
  export let divergences: MacroDivergenceListResponse | null = null;
  export let events: MacroEventsResponse | null = null;
  export let histories: Record<string, MacroSeriesHistory> = {};
  export let loading = false;
  export let onLoadWorkspace: (options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onLoadSeries: (seriesId: string, options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;

  const modes: Array<{ id: MacroMode; label: string }> = [
    { id: "snapshot", label: "Snapshot" },
    { id: "cross_asset", label: "Cross-Asset" },
    { id: "rates_policy", label: "Rates & Policy" },
  ];
  const themeLabels: Record<MacroTheme, string> = {
    all: "All",
    growth: "Growth",
    inflation: "Inflation",
    policy: "Policy",
    recession_risk: "Recession Risk",
  };
  const regionModeSeries: Record<MacroContextState["region"], Record<MacroMode, string[]>> = {
    US: {
      snapshot: [],
      cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
    },
    EU: {
      snapshot: [],
      cross_asset: ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "eu-industrial-production-yoy"],
      rates_policy: ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-hicp-yoy", "eu-eurusd"],
    },
    Global: {
      snapshot: [],
      cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
    },
  };
  const chartComparisonPairs: Record<string, string> = {
    "us-2y-yield": "eu-3m-rate",
    "us-10y-yield": "eu-10y-yield",
    "us-real-10y-yield": "eu-hicp-yoy",
    "us-5y-breakeven": "eu-eurusd",
    "eu-3m-rate": "us-2y-yield",
    "eu-10y-yield": "us-10y-yield",
    "eu-hicp-yoy": "us-cpi-yoy",
    "eu-eurusd": "us-dollar-broad",
  };
  const rateChartSeriesByRegion: Record<MacroContextState["region"], string[]> = {
    US: ["us-2y-yield", "us-10y-yield"],
    EU: ["eu-3m-rate", "eu-10y-yield"],
    Global: ["us-2y-yield", "us-10y-yield"],
  };
  const inflationChartSeriesByRegion: Record<MacroContextState["region"], string[]> = {
    US: ["us-real-10y-yield", "us-5y-breakeven"],
    EU: ["eu-hicp-yoy", "eu-eurusd"],
    Global: ["us-real-10y-yield", "us-5y-breakeven"],
  };

  /* ── FX strip configuration ── */
  const fxPairOptions: Array<{ id: string; label: string; seriesId: string }> = [
    { id: "eurusd", label: "EUR/USD", seriesId: "fx-eurusd" },
    { id: "gbpusd", label: "GBP/USD", seriesId: "fx-gbpusd" },
    { id: "usdjpy", label: "USD/JPY", seriesId: "fx-usdjpy" },
    { id: "usdchf", label: "USD/CHF", seriesId: "fx-usdchf" },
    { id: "usdcad", label: "USD/CAD", seriesId: "fx-usdcad" },
    { id: "audusd", label: "AUD/USD", seriesId: "fx-audusd" },
  ];
  const fxConfigurablePairs = fxPairOptions.filter((p) => p.id !== "eurusd");
  let fxPair1 = "gbpusd";
  let fxPair2 = "usdjpy";

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "N/A";

  function groupEventsByMonth<T extends { scheduled_at: string }>(evts: T[]): Array<{ label: string; events: T[] }> {
    const groups: Array<{ label: string; events: T[] }> = [];
    let current = "";
    for (const event of evts) {
      if (!event.scheduled_at) continue;
      const d = new Date(event.scheduled_at);
      const key = d.toLocaleString(undefined, { month: "long", year: "numeric" });
      if (key !== current) {
        current = key;
        groups.push({ label: key, events: [] });
      }
      groups.at(-1)!.events.push(event);
    }
    return groups;
  }

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

  function historyKey(seriesId: string, region = $macroContext.region) {
    return `${region}:${$macroContext.timeframe}:${seriesId}`;
  }

  async function refreshContext(next: Partial<MacroContextState>) {
    setMacroContext(next);
    await onLoadWorkspace(next);
  }

  async function drillTo(mode: MacroMode, theme?: string | null) {
    await refreshContext({
      mode,
      ...(theme ? { theme: theme as MacroTheme } : {})
    });
  }

  async function ensureSeries(seriesIds: string[]) {
    for (const seriesId of seriesIds) {
      if (!histories[historyKey(seriesId)]) {
        await onLoadSeries(seriesId);
      }
      const comparisonSeriesId =
        $macroContext.comparisonRegion && $macroContext.region !== "Global" ? chartComparisonPairs[seriesId] : null;
      if (comparisonSeriesId && !histories[historyKey(comparisonSeriesId, $macroContext.comparisonRegion)]) {
        await onLoadSeries(comparisonSeriesId, { region: $macroContext.comparisonRegion });
      }
    }
  }

  $: if ($macroContext.mode === "rates_policy") {
    void ensureSeries(regionModeSeries[$macroContext.region].rates_policy);
  }

  $: if ($macroContext.mode === "cross_asset") {
    void ensureSeries(regionModeSeries[$macroContext.region].cross_asset);
  }

  function chartFromSeries(seriesId: string, color: string, options?: { region?: MacroContextState["region"]; lineStyle?: "solid" | "dashed"; labelSuffix?: string }): ChartSeries[] {
    const region = options?.region ?? $macroContext.region;
    const history = histories[historyKey(seriesId, region)];
    if (!history?.points?.length) {
      return [];
    }
    return [
      {
        id: `${region}:${seriesId}`,
        label: `${history.title}${options?.labelSuffix ?? ""}`,
        color,
        type: "line",
        lineStyle: options?.lineStyle,
        data: history.points.map((point) => ({
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: point.value
        }))
      }
    ];
  }

  function buildChart(seriesIds: string[], colors: string[]) {
    const rows: ChartSeries[] = [];
    seriesIds.forEach((seriesId, index) => {
      rows.push(...chartFromSeries(seriesId, colors[index] ?? "#7aa6c8"));
      if ($macroContext.comparisonRegion && $macroContext.region !== "Global") {
        const comparisonSeriesId = chartComparisonPairs[seriesId];
        if (comparisonSeriesId) {
          rows.push(
            ...chartFromSeries(comparisonSeriesId, colors[index] ?? "#7aa6c8", {
              region: $macroContext.comparisonRegion,
              lineStyle: "dashed",
              labelSuffix: ` (${ $macroContext.comparisonRegion })`
            })
          );
        }
      }
    });
    return rows;
  }

  $: ratesChart = buildChart(rateChartSeriesByRegion[$macroContext.region], ["#7aa6c8", "#c49a5a"]);
  $: inflationChart = buildChart(inflationChartSeriesByRegion[$macroContext.region], ["#7aa6c8", "#c49a5a"]);
  $: crossAssetCards =
    $macroContext.theme === "all"
      ? snapshot?.cross_asset ?? []
      : (snapshot?.cross_asset ?? []).filter((row) => row.theme === $macroContext.theme);
  $: eventRows = events?.events ?? snapshot?.upcoming_events ?? [];
  $: coverageNote =
    $macroContext.region === "Global"
      ? "Global is a light V1 comparative lens. Some analytics reuse US-first coverage."
      : $macroContext.region === "EU"
        ? "EU is a lighter but structurally compatible region in Macro V1."
        : "US is the primary regional implementation in Macro V1.";
  $: compareOptions =
    $macroContext.region === "Global"
      ? []
      : (["US", "EU"] as Array<MacroContextState["region"]>).filter((region) => region !== $macroContext.region);
  $: ratesPolicyTag = $macroContext.region === "EU" ? "EU-light" : "US-first";
  $: inflationPanelEyebrow = $macroContext.region === "EU" ? "Inflation / FX" : "Real Rates";
  $: inflationPanelTitle = $macroContext.region === "EU" ? "Inflation and currency proxy split" : "Breakeven split";
  $: inflationChartEmptyMessage = $macroContext.region === "EU" ? "Loading inflation and FX history." : "Loading real-yield history.";
  $: statusRows = Array.from(
    new Set([
      "Macro V1 is US-first. Global mode is intentionally lighter than the US view.",
      ...(snapshot?.warnings ?? [])
    ])
  );

  /* ── FX strip reactives ── */
  $: fxPair1SeriesId = fxPairOptions.find((p) => p.id === fxPair1)?.seriesId ?? "fx-gbpusd";
  $: fxPair2SeriesId = fxPairOptions.find((p) => p.id === fxPair2)?.seriesId ?? "fx-usdjpy";
  $: fxSeriesIds = ["fx-eurusd", fxPair1SeriesId, fxPair2SeriesId];
  $: if ($macroContext.mode === "snapshot") {
    void ensureSeries(fxSeriesIds);
  }
  $: fxChart1 = chartFromSeries("fx-eurusd", "#7aa6c8");
  $: fxChart2 = chartFromSeries(fxPair1SeriesId, "#c49a5a");
  $: fxChart3 = chartFromSeries(fxPair2SeriesId, "#b65d54");

  /* ── Grouped events ── */
  $: groupedEvents = groupEventsByMonth(eventRows);
  $: ratesPolicyGroupedEvents = groupEventsByMonth(snapshot?.rates_policy?.events ?? []);
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Macro</p>
        <h2>Macro Research</h2>
      </div>
      {#if loading}
        <span class="loading-pill">Refreshing</span>
      {/if}
    </div>

    <div class="mode-bar-wrap">
      <div class="mode-bar" role="tablist" aria-label="Macro modes">
        {#each modes as mode}
          <button
            class:selected={mode.id === $macroContext.mode}
            role="tab"
            aria-selected={mode.id === $macroContext.mode}
            type="button"
            on:click={() => refreshContext({ mode: mode.id })}
          >
            {mode.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="context-bar">
      <div class="context-group">
        <label>
          <span>Region</span>
          <select value={$macroContext.region} on:change={(event) => refreshContext({ region: (event.currentTarget as HTMLSelectElement).value as MacroContextState["region"] })}>
            <option value="US">US</option>
            <option value="EU">EU</option>
            <option value="Global">Global</option>
          </select>
        </label>
        <label>
          <span>Timeframe</span>
          <select value={$macroContext.timeframe} on:change={(event) => refreshContext({ timeframe: (event.currentTarget as HTMLSelectElement).value as MacroContextState["timeframe"] })}>
            <option value="1M">1M</option>
            <option value="3M">3M</option>
            <option value="6M">6M</option>
            <option value="1Y">1Y</option>
          </select>
        </label>
      </div>
      <div class="context-group">
        <label>
          <span>Theme</span>
          <select value={$macroContext.theme} on:change={(event) => refreshContext({ theme: (event.currentTarget as HTMLSelectElement).value as MacroTheme })}>
            {#each Object.entries(themeLabels) as [value, label]}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </label>
        <label>
          <span>Compare</span>
          <select
            value={$macroContext.comparisonRegion ?? ""}
            disabled={$macroContext.region === "Global"}
            on:change={(event) => refreshContext({ comparisonRegion: ((event.currentTarget as HTMLSelectElement).value || null) as MacroContextState["comparisonRegion"] })}
          >
            <option value="">None</option>
            {#each compareOptions as region}
              <option value={region}>{region}</option>
            {/each}
          </select>
        </label>
      </div>
    </div>
    <p class="coverage-note">{coverageNote}</p>
  </article>

  {#if statusRows.length}
    <div class="status-strip">
      {#each statusRows as row}
        <p class="status-row">{row}</p>
      {/each}
    </div>
  {/if}

  {#if $macroContext.mode === "snapshot"}
    <div class="workspace-grid">
      {#each snapshot?.snapshot_cards ?? [] as card}
        <button class="panel card-panel" type="button" on:click={() => drillTo(card.mode_target as MacroMode, card.target_theme)}>
          <div class="card-head">
            <small class="eyebrow">{themeLabels[(card.target_theme as MacroTheme) ?? "all"] ?? "Macro"}</small>
            <h3>{card.title}</h3>
            <span class="tag">{card.mode_target.replace("_", " ")}</span>
          </div>
          <p class="card-summary">{card.summary}</p>
          <div class="metric-row">
            {#each card.metrics as metric}
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
        </button>
      {/each}
    </div>

    {#if !snapshot?.snapshot_cards?.length && !loading}
      <div class="panel empty-state">
        <p>No snapshot cards available for this configuration.</p>
      </div>
    {/if}

    <div class="fx-strip">
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <h3 class="fx-title">EUR/USD</h3>
        </div>
        <TimeSeriesChart series={fxChart1} height={200} emptyMessage="Loading EUR/USD" />
      </article>
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <select class="fx-select" bind:value={fxPair1}>
            {#each fxConfigurablePairs as pair}
              <option value={pair.id}>{pair.label}</option>
            {/each}
          </select>
        </div>
        <TimeSeriesChart series={fxChart2} height={200} emptyMessage="Loading FX data" />
      </article>
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <select class="fx-select" bind:value={fxPair2}>
            {#each fxConfigurablePairs as pair}
              <option value={pair.id}>{pair.label}</option>
            {/each}
          </select>
        </div>
        <TimeSeriesChart series={fxChart3} height={200} emptyMessage="Loading FX data" />
      </article>
    </div>

    <div class="detail-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Divergences</p>
            <h3>Top ranked disagreements</h3>
          </div>
        </div>
        {#if (snapshot?.top_divergences ?? []).length}
          <div class="list">
            {#each snapshot?.top_divergences ?? [] as row}
              <button class="list-row interactive" type="button" on:click={() => drillTo("cross_asset", row.theme)}>
                <div class="divergence-head">
                  <strong>{row.headline}</strong>
                  <span class="score-badge {row.label ?? ''}">{row.score?.toFixed(1) ?? '—'}</span>
                </div>
                <span class="list-detail">{row.summary}</span>
              </button>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No divergences detected for current context.</p>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Events</p>
            <h3>Upcoming macro calendar</h3>
          </div>
        </div>
        {#if eventRows.length}
          <div class="list events-scroll">
            {#each groupedEvents as group}
              <div class="date-group-header">{group.label}</div>
              {#each group.events as event}
                <div class="list-row">
                  <strong>{event.title}</strong>
                  <span class="list-detail">
                    <span class="event-date">{shortDate(event.scheduled_at)}</span>
                    <span class="event-category">{event.category}</span>
                  </span>
                </div>
              {/each}
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No upcoming events for this region.</p>
        {/if}
      </article>
    </div>
  {:else if $macroContext.mode === "rates_policy"}
    <div class="detail-grid">
      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Rates & Policy</p>
            <h3>{snapshot?.rates_policy?.headline ?? "Rates context loading"}</h3>
          </div>
          <span class="tag">{ratesPolicyTag}</span>
        </div>
        <p class="section-summary">{snapshot?.rates_policy?.summary}</p>
        {#if snapshot?.rates_policy?.comparison_summary}
          <p class="comparison-summary">{snapshot.rates_policy.comparison_summary}</p>
        {/if}
        <div class="metric-row">
          {#each snapshot?.rates_policy?.policy_metrics ?? [] as metric}
            <div class="metric">
              <span class="metric-label">{metric.label}</span>
              <strong class="metric-value">{metric.display_value}</strong>
              {#if metric.delta_display}
                <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
              {/if}
              {#if comparisonText(metric)}
                <small class="metric-compare">{comparisonText(metric)}</small>
              {/if}
            </div>
          {/each}
        </div>
        <TimeSeriesChart series={ratesChart} height={320} emptyMessage="Loading rates history." />
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Curve</p>
            <h3>Current vs prior</h3>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tenor</th>
                <th>Current</th>
                <th>Prior</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {#each snapshot?.rates_policy?.curve_nodes ?? [] as node}
                <tr>
                  <td>{node.tenor}</td>
                  <td>{fmt(node.current_value)}</td>
                  <td>{fmt(node.prior_value)}</td>
                  <td class="{node.change_bps != null && node.change_bps > 0 ? 'positive' : ''} {node.change_bps != null && node.change_bps < 0 ? 'negative' : ''}">{node.change_bps == null ? "N/A" : `${node.change_bps > 0 ? "+" : ""}${node.change_bps.toFixed(0)} bps`}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">{inflationPanelEyebrow}</p>
            <h3>{inflationPanelTitle}</h3>
          </div>
        </div>
        <div class="metric-row compact">
          {#each snapshot?.rates_policy?.real_yield_metrics ?? [] as metric}
            <div class="metric">
              <span class="metric-label">{metric.label}</span>
              <strong class="metric-value">{metric.display_value}</strong>
              {#if metric.delta_display}
                <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
              {/if}
              {#if comparisonText(metric)}
                <small class="metric-compare">{comparisonText(metric)}</small>
              {/if}
            </div>
          {/each}
        </div>
        <TimeSeriesChart series={inflationChart} height={280} emptyMessage={inflationChartEmptyMessage} />
      </article>

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Calendar</p>
            <h3>Meeting and release context</h3>
          </div>
        </div>
        {#if (snapshot?.rates_policy?.events ?? []).length}
          <div class="list events-scroll">
            {#each ratesPolicyGroupedEvents as group}
              <div class="date-group-header">{group.label}</div>
              {#each group.events as event}
                <div class="list-row">
                  <strong>{event.title}</strong>
                  <span class="list-detail">
                    <span class="event-date">{shortDate(event.scheduled_at)}</span>
                    <span class="event-category">{event.category}</span>
                  </span>
                </div>
              {/each}
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No upcoming rate events.</p>
        {/if}
      </article>
    </div>
  {:else}
    <div class="detail-grid">
      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Cross-Asset</p>
            <h3>Do these markets agree?</h3>
          </div>
        </div>
        {#if crossAssetCards.length}
          <div class="workspace-grid">
            {#each crossAssetCards as card}
              <article class="cross-card">
                <div class="card-head">
                  <div>
                    <small class="eyebrow">{themeLabels[card.theme as MacroTheme] ?? card.theme}</small>
                    <h3>{card.headline}</h3>
                  </div>
                  <span class="tag agreement">{card.agreement_label}</span>
                </div>
                <p class="card-subtitle">{card.summary}</p>
                {#if card.comparison_summary}
                  <p class="comparison-summary">{card.comparison_summary}</p>
                {/if}
                <div class="metric-row compact">
                  {#each card.metrics as metric}
                    <div class="metric">
                      <span class="metric-label">{metric.label}</span>
                      <strong class="metric-value">{metric.display_value}</strong>
                      {#if metric.delta_display}
                        <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
                      {/if}
                      {#if comparisonText(metric)}
                        <small class="metric-compare">{comparisonText(metric)}</small>
                      {/if}
                    </div>
                  {/each}
                </div>
              </article>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No cross-asset comparisons for this theme.</p>
        {/if}
      </article>

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Ranked Divergences</p>
            <h3>Best research candidates</h3>
          </div>
        </div>
        {#if (divergences?.divergences ?? []).length}
          <div class="list">
            {#each divergences?.divergences ?? [] as row}
              <div class="list-row">
                <div class="divergence-head">
                  <strong>{row.headline}</strong>
                  <span class="score-badge {row.label}">{row.score.toFixed(1)}</span>
                </div>
                <span class="list-detail">{row.summary}</span>
              </div>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No divergences ranked for current context.</p>
        {/if}
      </article>
    </div>
  {/if}
</section>

<style>
  /* ── Layout scaffolding ── */
  .view {
    display: grid;
    gap: 0.6rem;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
    gap: 0.5rem;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  /* ── Panels ── */
  .panel,
  .cross-card {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(12, 14, 16, 0.97), rgba(9, 10, 12, 0.95));
    padding: 0.85rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel {
    gap: 0.5rem;
  }

  .cross-card {
    gap: 0.45rem;
  }

  /* ── Header block ── */
  .header-top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.8rem;
  }

  .headline-block {
    display: grid;
    gap: 0.1rem;
  }

  .loading-pill {
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid rgba(122, 166, 200, 0.28);
    background: rgba(122, 166, 200, 0.06);
    padding: 0.2rem 0.5rem;
    white-space: nowrap;
    animation: pulse-opacity 1.6s ease-in-out infinite;
  }

  @keyframes pulse-opacity {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* ── Mode bar (segmented control) ── */
  .mode-bar-wrap {
    display: flex;
  }

  .mode-bar {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border: 1px solid var(--panel-strong);
    background: rgba(8, 13, 18, 0.82);
    max-width: 36rem;
    width: 100%;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.45rem 0.8rem;
    font: inherit;
    font-size: 0.78rem;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button:hover {
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-0);
  }

  .mode-bar button:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .mode-bar button.selected {
    background: rgba(122, 166, 200, 0.12);
    color: var(--accent);
  }

  /* ── Context bar ── */
  .context-bar {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .context-group {
    display: flex;
    gap: 0.5rem;
  }

  .context-bar label {
    display: grid;
    gap: 0.2rem;
  }

  .context-bar label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .context-bar select {
    border: 1px solid var(--panel-strong);
    background: #0d0f12;
    color: var(--text-0);
    padding: 0.4rem 0.6rem;
    font: inherit;
    font-size: 0.82rem;
    min-width: 6rem;
    cursor: pointer;
    transition: border-color 120ms ease;
  }

  .context-bar select:hover {
    border-color: rgba(122, 166, 200, 0.32);
  }

  .context-bar select:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .coverage-note {
    color: var(--text-2);
    font-size: 0.74rem;
    margin: 0;
    line-height: 1.35;
  }

  /* ── Status strip (compact warnings) ── */
  .status-strip {
    display: grid;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid rgba(196, 154, 90, 0.18);
    background: rgba(196, 154, 90, 0.03);
  }

  .status-row {
    color: var(--text-2);
    font-size: 0.74rem;
    line-height: 1.4;
    margin: 0;
    padding-left: 0.7rem;
    position: relative;
  }

  .status-row::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0.45em;
    width: 4px;
    height: 4px;
    background: var(--warning);
    border-radius: 50%;
    opacity: 0.6;
  }

  /* ── Panel header ── */
  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: 0.8rem;
    align-items: start;
  }

  .panel-header > div {
    min-width: 0;
  }

  /* ── Snapshot cards ── */
  .card-panel {
    cursor: pointer;
    text-align: left;
    gap: 0.35rem;
    padding: 0.7rem;
    transition: border-color 180ms ease, background 180ms ease;
  }

  .card-panel:hover {
    border-color: rgba(122, 166, 200, 0.32);
    background: linear-gradient(180deg, rgba(14, 17, 20, 0.97), rgba(11, 13, 15, 0.95));
  }

  .card-panel:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .card-head {
    display: grid;
    gap: 0.15rem;
  }

  .card-head h3 {
    font-size: 0.92rem;
  }

  .card-head .tag {
    margin-top: 0.2rem;
    justify-self: start;
  }

  .card-summary {
    color: var(--text-2);
    margin: 0;
    font-size: 0.78rem;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Section summary (rates & policy) ── */
  .section-summary {
    color: var(--text-2);
    margin: 0;
    line-height: 1.4;
  }

  .comparison-summary {
    color: var(--text-2);
    margin: 0;
    font-size: 0.78rem;
    line-height: 1.4;
  }

  /* ── Tags ── */
  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: 0.15rem 0.42rem;
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .tag.agreement {
    border-color: rgba(196, 154, 90, 0.24);
    background: rgba(196, 154, 90, 0.06);
    color: var(--accent-2);
  }

  /* ── Metric row ── */
  .metric-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
    gap: 0;
  }

  .metric-row.compact {
    grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr));
  }

  .metric {
    padding: 0.4rem 0.6rem;
    border-left: 1px solid rgba(46, 60, 74, 0.42);
    min-width: 0;
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
    font-size: 0.58rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .metric-value {
    display: block;
    margin-top: 0.12rem;
    font-size: 1rem;
    line-height: 1.25;
  }

  .metric-delta {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: 0.72rem;
  }

  .metric-delta.positive {
    color: var(--positive);
  }

  .metric-delta.negative {
    color: var(--negative);
  }

  .metric-compare {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: 0.68rem;
    line-height: 1.35;
  }

  /* ── FX strip ── */
  .fx-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .fx-panel {
    gap: 0.4rem;
    padding: 0.7rem;
  }

  .fx-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .fx-title {
    font-size: 0.88rem;
  }

  .fx-select {
    border: 1px solid var(--panel-strong);
    background: #0d0f12;
    color: var(--text-0);
    padding: 0.2rem 0.4rem;
    font: inherit;
    font-size: 0.82rem;
    cursor: pointer;
    transition: border-color 120ms ease;
  }

  .fx-select:hover {
    border-color: rgba(122, 166, 200, 0.32);
  }

  .fx-select:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  /* ── Lists ── */
  .list {
    display: grid;
    gap: 0;
  }

  .events-scroll {
    max-height: 24rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(122, 166, 200, 0.18) transparent;
  }

  .list-row {
    display: grid;
    gap: 0.1rem;
    text-align: left;
    padding: 0.55rem 0.65rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    cursor: default;
    transition: background 120ms ease;
  }

  .list-row:last-child {
    border-bottom: 0;
  }

  .list-row.interactive {
    cursor: pointer;
    border: 0;
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    background: transparent;
    color: inherit;
    font: inherit;
    width: 100%;
  }

  .list-row.interactive:hover {
    background: rgba(122, 166, 200, 0.04);
  }

  .list-row.interactive:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .list-row.interactive:last-child {
    border-bottom: 0;
  }

  .list-detail {
    color: var(--text-2);
    font-size: 0.78rem;
    line-height: 1.35;
  }

  .event-date {
    color: var(--text-1);
  }

  .event-category {
    color: var(--text-2);
    margin-left: 0.4rem;
  }

  .event-category::before {
    content: "·";
    margin-right: 0.4rem;
    opacity: 0.5;
  }

  /* ── Date group headers ── */
  .date-group-header {
    color: var(--text-2);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 0.45rem 0.65rem 0.2rem;
    background: rgba(8, 13, 18, 0.6);
    border-bottom: 1px solid rgba(46, 60, 74, 0.2);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  /* ── Divergence head + Score badges ── */
  .divergence-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }

  .score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.2rem;
    padding: 0.12rem 0.35rem;
    font-size: 0.64rem;
    font-weight: 600;
    border-radius: 2px;
    flex-shrink: 0;
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

  /* ── Empty states ── */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--text-2);
  }

  .empty-state p {
    margin: 0;
  }

  .empty-hint {
    color: var(--text-2);
    font-size: 0.78rem;
    margin: 0;
    padding: 0.4rem 0;
  }

  /* ── Table ── */
  .table-wrap {
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.55rem 0.5rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    text-align: left;
  }

  th {
    color: var(--text-2);
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(8, 13, 18, 0.82);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  tbody tr:nth-child(even) {
    background: rgba(122, 166, 200, 0.02);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  /* ── Shared typography ── */
  .eyebrow {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
    margin: 0;
  }

  h2,
  h3,
  p,
  small {
    margin: 0;
  }

  .span-2 {
    grid-column: span 2;
  }

  /* ── Responsive ── */
  @media (max-width: 1080px) {
    .detail-grid {
      grid-template-columns: 1fr;
    }

    .span-2 {
      grid-column: auto;
    }

    .context-bar {
      flex-direction: column;
    }

    .fx-strip {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 640px) {
    .mode-bar {
      grid-template-columns: 1fr;
      max-width: 100%;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }

    .mode-bar button:last-child {
      border-bottom: 0;
    }

    .context-group {
      flex-direction: column;
      width: 100%;
    }

    .context-bar select {
      width: 100%;
    }

    .metric-row,
    .metric-row.compact {
      grid-template-columns: 1fr 1fr;
    }

    .metric {
      padding: 0.4rem 0;
      border-left: 0;
    }

    .header-top {
      flex-direction: column;
      gap: 0.4rem;
    }
  }
</style>
