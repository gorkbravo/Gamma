<script lang="ts">
  import MacroSnapshot from "../components/MacroSnapshot.svelte";
  import MacroCrossAsset from "../components/MacroCrossAsset.svelte";
  import MacroRatesPolicy from "../components/MacroRatesPolicy.svelte";
  import MacroEventsRegimes from "../components/MacroEventsRegimes.svelte";
  import type { ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroDivergenceListResponse,
    MacroEventsResponse,
    MacroMode,
    MacroSeriesHistory,
    MacroSnapshot as MacroSnapshotType,
    MacroTheme,
  } from "../lib/api/types";
  import { macroContext, setMacroContext } from "../lib/stores/app";

  export let snapshot: MacroSnapshotType | null = null;
  export let divergences: MacroDivergenceListResponse | null = null;
  export let events: MacroEventsResponse | null = null;
  export let histories: Record<string, MacroSeriesHistory> = {};
  export let loading = false;
  export let onLoadWorkspace: (options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onLoadSeries: (seriesId: string, options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;

  /* ── Mode definitions ── */
  const modes: Array<{ id: MacroMode; label: string }> = [
    { id: "snapshot", label: "Snapshot" },
    { id: "cross_asset", label: "Cross-Asset" },
    { id: "rates_policy", label: "Rates & Policy" },
    { id: "events_regimes", label: "Events / Regimes" },
  ];
  const themeLabels: Record<MacroTheme, string> = {
    all: "All", growth: "Growth", inflation: "Inflation",
    policy: "Policy", recession_risk: "Recession Risk",
  };

  /* ── Chart series configuration ── */
  const regionModeSeries: Record<MacroContextState["region"], Record<MacroMode, string[]>> = {
    US: {
      snapshot: [], cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
      events_regimes: [],
    },
    EU: {
      snapshot: [], cross_asset: ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "eu-industrial-production-yoy"],
      rates_policy: ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-hicp-yoy", "eu-eurusd"],
      events_regimes: [],
    },
    Global: {
      snapshot: [], cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
      events_regimes: [],
    },
  };
  const chartComparisonPairs: Record<string, string> = {
    "us-2y-yield": "eu-3m-rate", "us-10y-yield": "eu-10y-yield",
    "us-real-10y-yield": "eu-hicp-yoy", "us-5y-breakeven": "eu-eurusd",
    "eu-3m-rate": "us-2y-yield", "eu-10y-yield": "us-10y-yield",
    "eu-hicp-yoy": "us-cpi-yoy", "eu-eurusd": "us-dollar-broad",
  };
  const rateChartSeriesByRegion: Record<MacroContextState["region"], string[]> = {
    US: ["us-2y-yield", "us-10y-yield"], EU: ["eu-3m-rate", "eu-10y-yield"], Global: ["us-2y-yield", "us-10y-yield"],
  };
  const inflationChartSeriesByRegion: Record<MacroContextState["region"], string[]> = {
    US: ["us-real-10y-yield", "us-5y-breakeven"], EU: ["eu-hicp-yoy", "eu-eurusd"], Global: ["us-real-10y-yield", "us-5y-breakeven"],
  };

  /* ── FX strip ── */
  const fxPairOptions: Array<{ id: string; label: string; seriesId: string }> = [
    { id: "eurusd", label: "EUR/USD", seriesId: "fx-eurusd" },
    { id: "usdeur", label: "USD/EUR", seriesId: "fx-usdeur" },
    { id: "gbpusd", label: "GBP/USD", seriesId: "fx-gbpusd" },
    { id: "usdgbp", label: "USD/GBP", seriesId: "fx-usdgbp" },
    { id: "usdjpy", label: "USD/JPY", seriesId: "fx-usdjpy" },
    { id: "jpyusd", label: "JPY/USD", seriesId: "fx-jpyusd" },
    { id: "usdchf", label: "USD/CHF", seriesId: "fx-usdchf" },
    { id: "chfusd", label: "CHF/USD", seriesId: "fx-chfusd" },
    { id: "usdcad", label: "USD/CAD", seriesId: "fx-usdcad" },
    { id: "cadusd", label: "CAD/USD", seriesId: "fx-cadusd" },
    { id: "audusd", label: "AUD/USD", seriesId: "fx-audusd" },
    { id: "usdaud", label: "USD/AUD", seriesId: "fx-usdaud" },
  ];
  let fxPair0 = "eurusd";
  let fxPair1 = "gbpusd";
  let fxPair2 = "usdjpy";

  /* ── Utility functions ── */
  type MacroChartContext = Pick<MacroContextState, "region" | "timeframe" | "comparisonRegion">;

  function historyKey(seriesId: string, timeframe: MacroContextState["timeframe"], region: MacroContextState["region"]) {
    return `${region}:${timeframe}:${seriesId}`;
  }

  function deltaClass(display: string | null | undefined): string {
    if (!display) return "";
    const trimmed = display.trim();
    if (trimmed.startsWith("+") || trimmed.startsWith("▲")) return "positive";
    if (trimmed.startsWith("-") || trimmed.startsWith("−") || trimmed.startsWith("▼")) return "negative";
    return "";
  }

  function shortDate(value: string | null | undefined) {
    return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "N/A";
  }

  /* ── Navigation ── */
  async function refreshContext(next: Partial<MacroContextState>) {
    setMacroContext(next);
    await onLoadWorkspace(next);
  }

  async function drillTo(mode: MacroMode, theme?: string | null) {
    await refreshContext({ mode, ...(theme ? { theme: theme as MacroTheme } : {}) });
  }

  /* ── Series loading ── */
  async function ensureSeries(seriesIds: string[]) {
    const requests: Array<Promise<unknown> | void> = [];
    const requested = new Set<string>();
    for (const seriesId of seriesIds) {
      const localKey = historyKey(seriesId, $macroContext.timeframe, $macroContext.region);
      if (!histories[localKey] && !requested.has(localKey)) {
        requested.add(localKey);
        requests.push(onLoadSeries(seriesId));
      }
      const comparisonSeriesId = $macroContext.comparisonRegion && $macroContext.region !== "Global" ? chartComparisonPairs[seriesId] : null;
      const comparisonKey = comparisonSeriesId && $macroContext.comparisonRegion ? historyKey(comparisonSeriesId, $macroContext.timeframe, $macroContext.comparisonRegion) : null;
      if (comparisonSeriesId && comparisonKey && !histories[comparisonKey] && !requested.has(comparisonKey)) {
        requested.add(comparisonKey);
        requests.push(onLoadSeries(comparisonSeriesId, { region: $macroContext.comparisonRegion }));
      }
    }
    if (requests.length) await Promise.all(requests);
  }

  /* ── Chart builders ── */
  function chartFromSeries(
    seriesMap: Record<string, MacroSeriesHistory>, context: MacroChartContext,
    seriesId: string, color: string,
    options?: { region?: MacroContextState["region"]; lineStyle?: "solid" | "dashed"; labelSuffix?: string }
  ): ChartSeries[] {
    const region = options?.region ?? context.region;
    const history = seriesMap[historyKey(seriesId, context.timeframe, region)];
    if (!history?.points?.length) return [];
    return [{
      id: `${region}:${seriesId}`, label: `${history.title}${options?.labelSuffix ?? ""}`,
      color, type: "line", lineStyle: options?.lineStyle,
      data: history.points.map((point) => ({ time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: point.value }))
    }];
  }

  function buildChart(seriesMap: Record<string, MacroSeriesHistory>, context: MacroChartContext, seriesIds: string[], colors: string[]) {
    const rows: ChartSeries[] = [];
    seriesIds.forEach((seriesId, index) => {
      rows.push(...chartFromSeries(seriesMap, context, seriesId, colors[index] ?? "#7aa6c8"));
      if (context.comparisonRegion && context.region !== "Global") {
        const comparisonSeriesId = chartComparisonPairs[seriesId];
        if (comparisonSeriesId) {
          rows.push(...chartFromSeries(seriesMap, context, comparisonSeriesId, colors[index] ?? "#7aa6c8", {
            region: context.comparisonRegion, lineStyle: "dashed", labelSuffix: ` (${context.comparisonRegion})`
          }));
        }
      }
    });
    return rows;
  }

  /* ── FX helpers ── */
  function fxLastPrice(series: ChartSeries[]): string | null {
    const pts = series[0]?.data;
    if (!pts?.length) return null;
    const last = pts[pts.length - 1].value;
    return last.toFixed(last >= 100 ? 2 : 4);
  }

  /* ── Reactive series loading ── */
  $: if ($macroContext.mode === "rates_policy") { void ensureSeries(regionModeSeries[$macroContext.region].rates_policy); }
  $: if ($macroContext.mode === "cross_asset") { void ensureSeries(regionModeSeries[$macroContext.region].cross_asset); }

  /* ── Chart reactives ── */
  $: chartContext = { region: $macroContext.region, timeframe: $macroContext.timeframe, comparisonRegion: $macroContext.comparisonRegion } satisfies MacroChartContext;
  $: ratesChart = buildChart(histories, chartContext, rateChartSeriesByRegion[chartContext.region], ["#7aa6c8", "#c49a5a"]);
  $: inflationChart = buildChart(histories, chartContext, inflationChartSeriesByRegion[chartContext.region], ["#7aa6c8", "#c49a5a"]);

  /* ── FX reactives ── */
  $: fxPair0SeriesId = fxPairOptions.find((p) => p.id === fxPair0)?.seriesId ?? "fx-eurusd";
  $: fxPair1SeriesId = fxPairOptions.find((p) => p.id === fxPair1)?.seriesId ?? "fx-gbpusd";
  $: fxPair2SeriesId = fxPairOptions.find((p) => p.id === fxPair2)?.seriesId ?? "fx-usdjpy";
  $: fxSeriesIds = Array.from(new Set([fxPair0SeriesId, fxPair1SeriesId, fxPair2SeriesId]));
  $: if ($macroContext.mode === "snapshot") { void ensureSeries(fxSeriesIds); }
  $: fxChart1 = chartFromSeries(histories, chartContext, fxPair0SeriesId, "#7aa6c8");
  $: fxChart2 = chartFromSeries(histories, chartContext, fxPair1SeriesId, "#c49a5a");
  $: fxChart3 = chartFromSeries(histories, chartContext, fxPair2SeriesId, "#b65d54");
  $: fxLast0 = fxLastPrice(fxChart1);
  $: fxLast1 = fxLastPrice(fxChart2);
  $: fxLast2 = fxLastPrice(fxChart3);

  /* ── Headline KPI strip ── */
  const headlineSeriesUS = ["us-cpi-yoy", "us-fed-funds", "us-2s10s-slope", "us-dollar-broad"];
  const headlineSeriesEU = ["eu-hicp-yoy", "eu-policy-rate", "eu-3m10y-slope", "eu-eurusd"];
  type HeadlineKPI = { label: string; displayValue: string; delta: string | null; deltaClass: string };

  function pickHeadlineKPIs(snap: MacroSnapshotType | null, region: string): HeadlineKPI[] {
    if (!snap?.snapshot_cards?.length) return [];
    const target = region === "EU" ? headlineSeriesEU : headlineSeriesUS;
    const allMetrics = snap.snapshot_cards.flatMap((c) => c.metrics);
    const result: HeadlineKPI[] = [];
    for (const sid of target) {
      const m = allMetrics.find((metric) => metric.series_id === sid);
      if (m?.display_value) result.push({ label: m.label, displayValue: m.display_value, delta: m.delta_display ?? null, deltaClass: deltaClass(m.delta_display) });
    }
    return result;
  }

  $: headlineKPIs = pickHeadlineKPIs(snapshot, $macroContext.region);
  $: nextEvent = (events?.events ?? snapshot?.upcoming_events ?? [])[0] ?? null;
  $: coverageNote = $macroContext.region === "Global" ? "Global is a light V1 comparative lens. Some analytics reuse US-first coverage."
    : $macroContext.region === "EU" ? "EU is a lighter but structurally compatible region in Macro V1."
    : "US is the primary regional implementation in Macro V1.";
  $: compareOptions = $macroContext.region === "Global" ? [] : (["US", "EU"] as Array<MacroContextState["region"]>).filter((r) => r !== $macroContext.region);
  $: maxSnapshotMetrics = Math.max(...(snapshot?.snapshot_cards ?? []).map((c) => c.metrics.length), 0);
</script>

<section class="view">
  <!-- ── Header shell ── -->
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Macro</p>
        <div class="headline-title-row">
          <h2>Macro Research</h2>
          {#if loading}<span class="loading-pill">Refreshing</span>{/if}
        </div>
      </div>
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Macro modes">
        {#each modes as mode}
          <button class:selected={mode.id === $macroContext.mode} role="tab" aria-selected={mode.id === $macroContext.mode} type="button" on:click={() => refreshContext({ mode: mode.id })}>
            {mode.label}
          </button>
        {/each}
      </div>
      <div class="header-right">
        {#if headlineKPIs.length}
          <div class="headline-strip">
            {#each headlineKPIs as kpi}
              <div class="headline-kpi">
                <span class="headline-kpi-label">{kpi.label}</span>
                <strong class="headline-kpi-value">{kpi.displayValue}</strong>
                {#if kpi.delta}<small class="headline-kpi-delta {kpi.deltaClass}">{kpi.delta}</small>{/if}
              </div>
            {/each}
          </div>
          {#if nextEvent}
            <div class="next-event">
              <span class="next-event-label">Next</span>
              <span class="next-event-title">{nextEvent.title}</span>
              <span class="next-event-date">{shortDate(nextEvent.scheduled_at)}</span>
            </div>
          {/if}
        {/if}
      </div>
    </div>

    <div class="context-bar">
      <div class="context-group">
        <label><span>Region</span>
          <select value={$macroContext.region} on:change={(e) => refreshContext({ region: (e.currentTarget as HTMLSelectElement).value as MacroContextState["region"] })}>
            <option value="US">US</option><option value="EU">EU</option><option value="Global">Global</option>
          </select>
        </label>
        <label><span>Timeframe</span>
          <select value={$macroContext.timeframe} on:change={(e) => refreshContext({ timeframe: (e.currentTarget as HTMLSelectElement).value as MacroContextState["timeframe"] })}>
            <option value="1M">1M</option><option value="3M">3M</option><option value="6M">6M</option><option value="1Y">1Y</option>
          </select>
        </label>
      </div>
      <div class="context-group">
        <label><span>Theme</span>
          <select value={$macroContext.theme} on:change={(e) => refreshContext({ theme: (e.currentTarget as HTMLSelectElement).value as MacroTheme })}>
            {#each Object.entries(themeLabels) as [value, label]}<option value={value}>{label}</option>{/each}
          </select>
        </label>
        <label><span>Compare</span>
          <select value={$macroContext.comparisonRegion ?? ""} disabled={$macroContext.region === "Global"} on:change={(e) => refreshContext({ comparisonRegion: ((e.currentTarget as HTMLSelectElement).value || null) as MacroContextState["comparisonRegion"] })}>
            <option value="">None</option>
            {#each compareOptions as region}<option value={region}>{region}</option>{/each}
          </select>
        </label>
      </div>
    </div>
    <p class="coverage-note">{coverageNote}</p>
  </article>

  <!-- ── Mode content ── -->
  {#if $macroContext.mode === "snapshot"}
    <MacroSnapshot
      {snapshot} {events} {loading}
      {fxChart1} {fxChart2} {fxChart3}
      {fxLast0} {fxLast1} {fxLast2}
      {fxPairOptions}
      bind:fxPair0 bind:fxPair1 bind:fxPair2
      {maxSnapshotMetrics}
      onDrillTo={drillTo}
    />
  {:else if $macroContext.mode === "cross_asset"}
    <MacroCrossAsset {snapshot} {divergences} theme={$macroContext.theme} />
  {:else if $macroContext.mode === "rates_policy"}
    <MacroRatesPolicy {snapshot} {ratesChart} {inflationChart} region={$macroContext.region} />
  {:else if $macroContext.mode === "events_regimes"}
    <MacroEventsRegimes {snapshot} {events} />
  {/if}
</section>

<style>
  .view {
    display: grid;
    gap: 0.6rem;
  }

  /* ── Header panel ── */
  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel { gap: 0.35rem; }

  .header-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.8rem;
  }

  .headline-block {
    display: grid;
    gap: 0.1rem;
    flex-shrink: 0;
  }

  .headline-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }

  .header-right {
    position: absolute;
    right: 0;
    top: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0;
  }

  /* ── Headline KPI strip ── */
  .headline-strip { display: flex; gap: 0; }

  .headline-kpi {
    padding: 0.2rem 0.65rem;
    border-left: 1px solid rgba(46, 60, 74, 0.42);
    text-align: right;
  }

  .headline-kpi:first-child { border-left: 0; }

  .headline-kpi-label {
    display: block;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.52rem;
    white-space: nowrap;
  }

  .headline-kpi-value {
    display: block;
    font-size: 0.92rem;
    line-height: 1.2;
    margin-top: 0.06rem;
    white-space: nowrap;
  }

  .headline-kpi-delta {
    display: block;
    color: var(--text-2);
    font-size: 0.62rem;
    margin-top: 0.02rem;
    white-space: nowrap;
  }

  .headline-kpi-delta.positive { color: var(--positive); }
  .headline-kpi-delta.negative { color: var(--negative); }

  /* ── Next event ── */
  .next-event {
    display: flex;
    align-items: baseline;
    justify-content: flex-end;
    gap: 0.6rem;
    white-space: nowrap;
    margin-top: 0.1rem;
    padding-top: 0.2rem;
    border-top: 1px solid rgba(46, 60, 74, 0.25);
  }

  .next-event-label {
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
    color: var(--text-2);
    opacity: 0.7;
  }

  .next-event-title { color: var(--text-1); font-size: 0.84rem; }

  .next-event-date { color: var(--text-2); font-size: 0.8rem; }

  .next-event-date::before { content: "·"; margin-right: 0.5rem; opacity: 0.5; }

  /* ── Loading pill ── */
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

  /* ── Mode bar ── */
  .mode-kpi-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    position: relative;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(4, auto);
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.4rem 0.85rem;
    font: inherit;
    font-size: 0.78rem;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  /* ── Context bar ── */
  .context-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .context-group { display: flex; gap: 0.5rem; }
  .context-bar label { display: grid; gap: 0.2rem; }

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

  .context-bar select:hover { border-color: rgba(122, 166, 200, 0.32); }
  .context-bar select:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }

  .coverage-note {
    color: var(--text-2);
    font-size: 0.74rem;
    margin: 0;
    line-height: 1.35;
  }

  /* ── Typography ── */
  .eyebrow {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
    margin: 0;
  }

  h2, p, small { margin: 0; }

  /* ── Responsive ── */
  @media (max-width: 640px) {
    .mode-bar {
      grid-template-columns: 1fr;
      max-width: 100%;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }

    .mode-bar button:last-child { border-bottom: 0; }

    .context-group { flex-direction: column; width: 100%; }
    .context-bar select { width: 100%; }

    .header-top { flex-direction: column; gap: 0.4rem; }
    .headline-strip, .next-event { display: none; }
  }
</style>
