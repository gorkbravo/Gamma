<script lang="ts">
  import MacroSnapshot from "../components/MacroSnapshot.svelte";
  import MacroCrossAsset from "../components/MacroCrossAsset.svelte";
  import MacroRatesPolicy from "../components/MacroRatesPolicy.svelte";
  import MacroEventsRegimes from "../components/MacroEventsRegimes.svelte";
  import MacroTradePartners from "../components/MacroTradePartners.svelte";
  import MacroCountryCompare from "../components/MacroCountryCompare.svelte";
  import type { ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroDivergenceListResponse,
    MacroEventsResponse,
    MacroMode,
    MacroSeriesHistory,
    MacroSnapshot as MacroSnapshotType,
    MacroTheme,
    StrategyLabHandoffEnvelope,
  } from "../lib/api/types";
  import { macroContext, setMacroContext } from "../lib/stores/app";
  import { buildMacroStrategyLensHandoff } from "../lib/view-models/research";

  export let snapshot: MacroSnapshotType | null = null;
  export let divergences: MacroDivergenceListResponse | null = null;
  export let events: MacroEventsResponse | null = null;
  export let histories: Record<string, MacroSeriesHistory> = {};
  export let loading = false;
  export let onLoadWorkspace: (options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onLoadSeries: (seriesId: string, options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onSendToStrategyLab:
    | ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void)
    | undefined = undefined;

  /* ── Mode definitions ── */
  const modes: Array<{ id: MacroMode; label: string }> = [
    { id: "snapshot", label: "Snapshot" },
    { id: "cross_asset", label: "Cross-Asset" },
    { id: "rates_policy", label: "Rates & Policy" },
    { id: "events_regimes", label: "Events / Regimes" },
    { id: "trade_partners", label: "Trade Partners" },
    { id: "country_compare", label: "Country Compare" },
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
      trade_partners: [],
      country_compare: [],
    },
    EU: {
      snapshot: [], cross_asset: ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "eu-industrial-production-yoy"],
      rates_policy: ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-hicp-yoy", "eu-eurusd"],
      events_regimes: [],
      trade_partners: [],
      country_compare: [],
    },
    Global: {
      snapshot: [], cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
      events_regimes: [],
      trade_partners: [],
      country_compare: [],
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
    { id: "eurgbp", label: "EUR/GBP", seriesId: "fx-eurgbp" },
    { id: "eurchf", label: "EUR/CHF", seriesId: "fx-eurchf" },
    { id: "usdjpy", label: "USD/JPY", seriesId: "fx-usdjpy" },
    { id: "jpyusd", label: "JPY/USD", seriesId: "fx-jpyusd" },
    { id: "usdchf", label: "USD/CHF", seriesId: "fx-usdchf" },
    { id: "chfusd", label: "CHF/USD", seriesId: "fx-chfusd" },
    { id: "usdcnh", label: "USD/CNH", seriesId: "fx-usdcnh" },
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
    return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "N/A";
  }

  /* ── Navigation ── */
  async function refreshContext(next: Partial<MacroContextState>) {
    setMacroContext(next);
    await onLoadWorkspace(next);
  }

  async function drillTo(mode: MacroMode, theme?: string | null) {
    await refreshContext({ mode, ...(theme ? { theme: theme as MacroTheme } : {}) });
  }

  function sendMacroLensToStrategyLab(open = false) {
    if (!onSendToStrategyLab) {
      return;
    }
    const handoff = buildMacroStrategyLensHandoff({
      context: $macroContext,
      snapshot,
      events
    });
    onSendToStrategyLab(handoff, { open });
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
      rows.push(...chartFromSeries(seriesMap, context, seriesId, colors[index] ?? "var(--chart-primary)"));
      if (context.comparisonRegion && context.region !== "Global") {
        const comparisonSeriesId = chartComparisonPairs[seriesId];
        if (comparisonSeriesId) {
          rows.push(...chartFromSeries(seriesMap, context, comparisonSeriesId, colors[index] ?? "var(--chart-primary)", {
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
  $: ratesChart = buildChart(histories, chartContext, rateChartSeriesByRegion[chartContext.region], ["var(--chart-primary)", "var(--chart-secondary)"]);
  $: inflationChart = buildChart(histories, chartContext, inflationChartSeriesByRegion[chartContext.region], ["var(--chart-primary)", "var(--chart-secondary)"]);

  /* ── FX reactives ── */
  $: fxPair0SeriesId = fxPairOptions.find((p) => p.id === fxPair0)?.seriesId ?? "fx-eurusd";
  $: fxPair1SeriesId = fxPairOptions.find((p) => p.id === fxPair1)?.seriesId ?? "fx-gbpusd";
  $: fxPair2SeriesId = fxPairOptions.find((p) => p.id === fxPair2)?.seriesId ?? "fx-usdjpy";
  $: fxSeriesIds = Array.from(new Set([fxPair0SeriesId, fxPair1SeriesId, fxPair2SeriesId]));
  $: if ($macroContext.mode === "snapshot") { void ensureSeries(fxSeriesIds); }
  $: fxChart1 = chartFromSeries(histories, chartContext, fxPair0SeriesId, "var(--chart-primary)");
  $: fxChart2 = chartFromSeries(histories, chartContext, fxPair1SeriesId, "var(--chart-secondary)");
  $: fxChart3 = chartFromSeries(histories, chartContext, fxPair2SeriesId, "var(--chart-negative)");
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
      <span class="title">Macro Research</span>
      <span class="subtitle">{$macroContext.region} · {$macroContext.timeframe} · {themeLabels[$macroContext.theme] ?? $macroContext.theme}</span>
      {#if loading}<span class="loading-pill">Refreshing</span>{/if}
      <div class="handoff-actions" aria-label="Strategy Lab macro lens actions">
        <button
          type="button"
          class="ghost-action"
          on:click={() => sendMacroLensToStrategyLab(false)}
          disabled={loading || !onSendToStrategyLab}
        >
          Use as Lens
        </button>
        <button
          type="button"
          on:click={() => sendMacroLensToStrategyLab(true)}
          disabled={loading || !onSendToStrategyLab}
        >
          Lens &amp; Open
        </button>
      </div>
      {#if nextEvent}
        <span class="next-event">
          <span class="next-event-label">Next</span>
          <span class="next-event-title">{nextEvent.title}</span>
          <span class="next-event-date">{shortDate(nextEvent.scheduled_at)}</span>
        </span>
      {/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Macro modes">
        {#each modes as mode}
          <button class:selected={mode.id === $macroContext.mode} role="tab" aria-selected={mode.id === $macroContext.mode} type="button" on:click={() => refreshContext({ mode: mode.id })}>
            {mode.label}
          </button>
        {/each}
      </div>
      {#if headlineKPIs.length}
        <div class="headline-strip">
          {#each headlineKPIs as kpi}
            <div class="headline-kpi">
              <span class="headline-kpi-label">{kpi.label}</span>
              <strong class="headline-kpi-value">{kpi.displayValue}{#if kpi.delta} <small class="headline-kpi-delta {kpi.deltaClass}">{kpi.delta}</small>{/if}</strong>
            </div>
          {/each}
        </div>
      {/if}
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
  {:else if $macroContext.mode === "trade_partners"}
    <MacroTradePartners {snapshot} />
  {:else if $macroContext.mode === "country_compare"}
    <MacroCountryCompare {snapshot} />
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

  .header-panel { gap: 0.35rem; padding: 0.5rem 0.65rem; }

  .header-top {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .title {
    color: var(--text-0);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .subtitle {
    color: var(--text-2);
    font-size: 10.5px;
    letter-spacing: 0.04em;
  }

  .handoff-actions {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    flex: 0 0 auto;
  }

  .handoff-actions button {
    min-height: 25px;
    padding: 4px 8px;
    font-size: 11px;
    white-space: nowrap;
  }

  .handoff-actions .ghost-action {
    background: transparent;
  }

  /* ── Headline KPI strip ── */
  .headline-strip { display: flex; gap: 0; border-left: 1px solid var(--divider); }

  .headline-kpi {
    display: grid;
    gap: 0.05rem;
    padding: 0.1rem 0.7rem;
    border-right: 1px solid var(--divider);
    min-width: 5.5rem;
    text-align: left;
  }

  .headline-kpi-label {
    display: block;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 9.5px;
    line-height: 1.1;
    white-space: nowrap;
  }

  .headline-kpi-value {
    display: block;
    color: var(--text-0);
    font-size: 12.5px;
    font-weight: 600;
    line-height: 1.15;
    white-space: nowrap;
  }

  .headline-kpi-delta {
    color: var(--text-2);
    font-size: 10px;
    font-weight: 400;
    margin-left: 0.2rem;
    white-space: nowrap;
  }

  .headline-kpi-delta.positive { color: var(--positive); }
  .headline-kpi-delta.negative { color: var(--negative); }

  /* ── Next event (inline in header-top) ── */
  .next-event {
    display: inline-flex;
    align-items: baseline;
    gap: 0.35rem;
    white-space: nowrap;
    margin-left: auto;
    padding-left: 0.6rem;
    border-left: 1px solid var(--divider);
    color: var(--text-2);
  }

  .next-event-label {
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 9.5px;
    color: var(--text-2);
  }

  .next-event-title { color: var(--text-1); font-size: 11px; }

  .next-event-date { color: var(--text-2); font-size: 10.5px; }

  .next-event-date::before { content: "·"; margin-right: 0.35rem; opacity: 0.5; }

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
    gap: 0.5rem;
    position: relative;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(6, auto);
    border: 1px solid var(--panel-strong);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.28rem 0.65rem;
    font: inherit;
    font-size: 0.79rem;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  /* ── Context bar ── */
  .context-bar { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .context-group { display: flex; gap: 0.4rem; }
  .context-bar label { display: grid; gap: 0.15rem; }

  .context-bar label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10px;
    font-weight: 500;
  }

  .context-bar select {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    height: 24px;
    padding: 2px 6px;
    font: inherit;
    font-size: 12px;
    border-radius: 2px;
    min-width: 5rem;
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

  p, small { margin: 0; }

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
