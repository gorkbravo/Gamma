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
    { id: "events_regimes", label: "Events / Regimes" },
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
      events_regimes: [],
    },
    EU: {
      snapshot: [],
      cross_asset: ["eu-hicp-yoy", "eu-eurusd", "eu-10y-yield", "eu-industrial-production-yoy"],
      rates_policy: ["eu-policy-rate", "eu-3m-rate", "eu-10y-yield", "eu-hicp-yoy", "eu-eurusd"],
      events_regimes: [],
    },
    Global: {
      snapshot: [],
      cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
      rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
      events_regimes: [],
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

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "N/A";

  type MacroChartContext = Pick<MacroContextState, "region" | "timeframe" | "comparisonRegion">;

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

  function linkedMarketTone(label: string | null | undefined): string {
    if (label === "aligned") return "positive";
    if (label === "diverging") return "negative";
    return "";
  }

  function eventStudyTone(label: string | null | undefined): string {
    if (label === "reinforcing") return "positive";
    if (label === "opposing") return "negative";
    return "";
  }

  function divergenceSignalTone(tone: string | null | undefined): string {
    if (tone === "reinforcing") return "positive";
    if (tone === "opposing") return "negative";
    return "";
  }

  function linkedMarketScore(value: number | null | undefined): string | null {
    return value == null ? null : value.toFixed(1);
  }

  function historyKey(
    seriesId: string,
    timeframe: MacroContextState["timeframe"],
    region: MacroContextState["region"]
  ) {
    return `${region}:${timeframe}:${seriesId}`;
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
    const requests: Array<Promise<unknown> | void> = [];
    const requested = new Set<string>();
    for (const seriesId of seriesIds) {
      const localKey = historyKey(seriesId, $macroContext.timeframe, $macroContext.region);
      if (!histories[localKey] && !requested.has(localKey)) {
        requested.add(localKey);
        requests.push(onLoadSeries(seriesId));
      }
      const comparisonSeriesId =
        $macroContext.comparisonRegion && $macroContext.region !== "Global" ? chartComparisonPairs[seriesId] : null;
      const comparisonKey =
        comparisonSeriesId && $macroContext.comparisonRegion
          ? historyKey(comparisonSeriesId, $macroContext.timeframe, $macroContext.comparisonRegion)
          : null;
      if (comparisonSeriesId && comparisonKey && !histories[comparisonKey] && !requested.has(comparisonKey)) {
        requested.add(comparisonKey);
        requests.push(onLoadSeries(comparisonSeriesId, { region: $macroContext.comparisonRegion }));
      }
    }
    if (requests.length) {
      await Promise.all(requests);
    }
  }

  $: if ($macroContext.mode === "rates_policy") {
    void ensureSeries(regionModeSeries[$macroContext.region].rates_policy);
  }

  $: if ($macroContext.mode === "cross_asset") {
    void ensureSeries(regionModeSeries[$macroContext.region].cross_asset);
  }

  function chartFromSeries(
    seriesMap: Record<string, MacroSeriesHistory>,
    context: MacroChartContext,
    seriesId: string,
    color: string,
    options?: { region?: MacroContextState["region"]; lineStyle?: "solid" | "dashed"; labelSuffix?: string }
  ): ChartSeries[] {
    const region = options?.region ?? context.region;
    const history = seriesMap[historyKey(seriesId, context.timeframe, region)];
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

  function buildChart(seriesMap: Record<string, MacroSeriesHistory>, context: MacroChartContext, seriesIds: string[], colors: string[]) {
    const rows: ChartSeries[] = [];
    seriesIds.forEach((seriesId, index) => {
      rows.push(...chartFromSeries(seriesMap, context, seriesId, colors[index] ?? "#7aa6c8"));
      if (context.comparisonRegion && context.region !== "Global") {
        const comparisonSeriesId = chartComparisonPairs[seriesId];
        if (comparisonSeriesId) {
          rows.push(
            ...chartFromSeries(seriesMap, context, comparisonSeriesId, colors[index] ?? "#7aa6c8", {
              region: context.comparisonRegion,
              lineStyle: "dashed",
              labelSuffix: ` (${context.comparisonRegion})`
            })
          );
        }
      }
    });
    return rows;
  }

  let ratesChart: ChartSeries[] = [];
  let inflationChart: ChartSeries[] = [];
  let fxChart1: ChartSeries[] = [];
  let fxChart2: ChartSeries[] = [];
  let fxChart3: ChartSeries[] = [];

  $: chartContext = {
    region: $macroContext.region,
    timeframe: $macroContext.timeframe,
    comparisonRegion: $macroContext.comparisonRegion
  } satisfies MacroChartContext;
  $: ratesChart = buildChart(histories, chartContext, rateChartSeriesByRegion[chartContext.region], ["#7aa6c8", "#c49a5a"]);
  $: inflationChart = buildChart(histories, chartContext, inflationChartSeriesByRegion[chartContext.region], ["#7aa6c8", "#c49a5a"]);
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
  $: fxPair0SeriesId = fxPairOptions.find((p) => p.id === fxPair0)?.seriesId ?? "fx-eurusd";
  $: fxPair1SeriesId = fxPairOptions.find((p) => p.id === fxPair1)?.seriesId ?? "fx-gbpusd";
  $: fxPair2SeriesId = fxPairOptions.find((p) => p.id === fxPair2)?.seriesId ?? "fx-usdjpy";
  $: fxSeriesIds = Array.from(new Set([fxPair0SeriesId, fxPair1SeriesId, fxPair2SeriesId]));
  $: if ($macroContext.mode === "snapshot") {
    void ensureSeries(fxSeriesIds);
  }
  $: fxChart1 = chartFromSeries(histories, chartContext, fxPair0SeriesId, "#7aa6c8");
  $: fxChart2 = chartFromSeries(histories, chartContext, fxPair1SeriesId, "#c49a5a");
  $: fxChart3 = chartFromSeries(histories, chartContext, fxPair2SeriesId, "#b65d54");

  /* ── FX last prices ── */
  function fxLastPrice(series: ChartSeries[]): string | null {
    const pts = series[0]?.data;
    if (!pts?.length) return null;
    const last = pts[pts.length - 1].value;
    return last.toFixed(last >= 100 ? 2 : 4);
  }
  $: fxLast0 = fxLastPrice(fxChart1);
  $: fxLast1 = fxLastPrice(fxChart2);
  $: fxLast2 = fxLastPrice(fxChart3);

  /* ── Grouped events ── */
  $: groupedEvents = groupEventsByMonth(eventRows);
  $: ratesPolicyGroupedEvents = groupEventsByMonth(snapshot?.rates_policy?.events ?? []);
  $: recentEventStudies = (snapshot?.event_studies ?? []).filter((study) => study.timing === "recent");
  $: upcomingEventStudies = (snapshot?.event_studies ?? []).filter((study) => study.timing === "upcoming");
  $: maxSnapshotMetrics = Math.max(...(snapshot?.snapshot_cards ?? []).map((c) => c.metrics.length), 0);

  /* ── Headline KPI strip (persistent context) ── */
  const headlineSeriesUS = ["us-cpi-yoy", "us-fed-funds", "us-2s10s-slope", "us-dollar-broad"];
  const headlineSeriesEU = ["eu-hicp-yoy", "eu-policy-rate", "eu-3m10y-slope", "eu-eurusd"];

  type HeadlineKPI = { label: string; displayValue: string; delta: string | null; deltaClass: string };

  function pickHeadlineKPIs(snap: MacroSnapshot | null, region: string): HeadlineKPI[] {
    if (!snap?.snapshot_cards?.length) return [];
    const target = region === "EU" ? headlineSeriesEU : headlineSeriesUS;
    const allMetrics = snap.snapshot_cards.flatMap((c) => c.metrics);
    const result: HeadlineKPI[] = [];
    for (const sid of target) {
      const m = allMetrics.find((metric) => metric.series_id === sid);
      if (m?.display_value) {
        result.push({ label: m.label, displayValue: m.display_value, delta: m.delta_display ?? null, deltaClass: deltaClass(m.delta_display) });
      }
    }
    return result;
  }

  $: headlineKPIs = pickHeadlineKPIs(snapshot, $macroContext.region);
  $: nextEvent = (events?.events ?? snapshot?.upcoming_events ?? [])[0] ?? null;
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Macro</p>
        <div class="headline-title-row">
          <h2>Macro Research</h2>
          {#if loading}
            <span class="loading-pill">Refreshing</span>
          {/if}
        </div>
      </div>
    </div>

    <div class="mode-kpi-row">
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
      <div class="header-right">
        {#if headlineKPIs.length}
          <div class="headline-strip">
            {#each headlineKPIs as kpi}
              <div class="headline-kpi">
                <span class="headline-kpi-label">{kpi.label}</span>
                <strong class="headline-kpi-value">{kpi.displayValue}</strong>
                {#if kpi.delta}
                  <small class="headline-kpi-delta {kpi.deltaClass}">{kpi.delta}</small>
                {/if}
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
    {#if (snapshot?.snapshot_cards ?? []).length}
      <article class="panel snapshot-table-panel">
        <div class="table-wrap">
          <table class="snapshot-table">
            <thead>
              <tr>
                <th class="col-theme">Theme</th>
                <th class="col-drill"></th>
                {#each Array.from({ length: maxSnapshotMetrics }) as _}
                  <th class="col-metric"></th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each snapshot?.snapshot_cards ?? [] as card}
                <tr class="snapshot-row" tabindex="0" role="button" on:click={() => drillTo(card.mode_target as MacroMode, card.target_theme)} on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drillTo(card.mode_target as MacroMode, card.target_theme); } }}>
                  <td class="col-theme">
                    <span class="row-theme">{card.title}</span>
                    <span class="row-summary">{card.summary}</span>
                    {#if card.linked_markets?.length}
                      <span class="linked-hint">
                        <span class="linked-dot {linkedMarketTone(card.linked_markets[0].macro_alignment)}"></span>
                        {card.linked_markets.length} linked {card.linked_markets.length === 1 ? "market" : "markets"}
                        {#if card.linked_markets[0].macro_alignment}
                          · <span class={linkedMarketTone(card.linked_markets[0].macro_alignment)}>{card.linked_markets[0].macro_alignment}</span>
                        {/if}
                      </span>
                    {/if}
                  </td>
                  <td class="col-drill">
                    <span class="tag">{card.mode_target.replace("_", " ")}</span>
                  </td>
                  {#each card.metrics as metric}
                    <td class="col-metric">
                      <span class="metric-label">{metric.label}</span>
                      <strong class="metric-value">{metric.display_value ?? "N/A"}</strong>
                      {#if metric.delta_display}
                        <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
                      {/if}
                    </td>
                  {/each}
                  {#each Array.from({ length: maxSnapshotMetrics - card.metrics.length }) as _}
                    <td class="col-metric"></td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </article>
    {:else if !loading}
      <div class="panel empty-state">
        <p>No snapshot cards available for this configuration.</p>
      </div>
    {/if}

    <div class="fx-strip">
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <select class="fx-select" bind:value={fxPair0}>
            {#each fxPairOptions as pair}
              <option value={pair.id}>{pair.label}</option>
            {/each}
          </select>
          {#if fxLast0}<strong class="fx-last-price">{fxLast0}</strong>{/if}
        </div>
        <TimeSeriesChart series={fxChart1} height={200} emptyMessage="Loading FX data" />
      </article>
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <select class="fx-select" bind:value={fxPair1}>
            {#each fxPairOptions as pair}
              <option value={pair.id}>{pair.label}</option>
            {/each}
          </select>
          {#if fxLast1}<strong class="fx-last-price">{fxLast1}</strong>{/if}
        </div>
        <TimeSeriesChart series={fxChart2} height={200} emptyMessage="Loading FX data" />
      </article>
      <article class="panel fx-panel">
        <div class="fx-header">
          <small class="eyebrow">FX</small>
          <select class="fx-select" bind:value={fxPair2}>
            {#each fxPairOptions as pair}
              <option value={pair.id}>{pair.label}</option>
            {/each}
          </select>
          {#if fxLast2}<strong class="fx-last-price">{fxLast2}</strong>{/if}
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
        {#if snapshot?.rates_policy?.linked_markets?.length}
          <div class="linked-market-list">
            {#each snapshot.rates_policy.linked_markets as market}
              <article class="linked-market-card">
                <div class="linked-market-head">
                  <strong>{market.title}</strong>
                  <span class="tag">{market.venue}</span>
                </div>
                <div class="linked-market-stats">
                  {#if market.probability_label}
                    <span>{market.probability_label}</span>
                  {/if}
                  {#if market.change_display}
                    <span class={linkedMarketTone(market.macro_alignment)}>{market.change_display}</span>
                  {/if}
                  {#if linkedMarketScore(market.research_score)}
                    <span>rank {linkedMarketScore(market.research_score)}</span>
                  {/if}
                </div>
                <p class="linked-market-summary {linkedMarketTone(market.macro_alignment)}">{market.macro_alignment_summary}</p>
              </article>
            {/each}
          </div>
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

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Path Proxy</p>
            <h3>{snapshot?.rates_policy?.path_headline ?? "Front-end path proxy loading"}</h3>
          </div>
          {#if snapshot?.rates_policy?.market_alignment_label}
            <span class="tag agreement">{snapshot.rates_policy.market_alignment_label}</span>
          {/if}
        </div>
        {#if snapshot?.rates_policy?.path_summary}
          <p class="section-summary">{snapshot.rates_policy.path_summary}</p>
        {/if}
        {#if snapshot?.rates_policy?.market_alignment_summary}
          <p class="comparison-summary">{snapshot.rates_policy.market_alignment_summary}</p>
        {/if}
        <div class="metric-row compact">
          {#each snapshot?.rates_policy?.path_metrics ?? [] as metric}
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
        {#if snapshot?.rates_policy?.path_research_focus}
          <p class="research-focus">{snapshot.rates_policy.path_research_focus}</p>
        {/if}
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
  {:else if $macroContext.mode === "events_regimes"}
    <div class="detail-grid">
      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Regime Framing</p>
            <h3>Current cross-market read</h3>
          </div>
        </div>
        {#if (snapshot?.top_divergences ?? []).length}
          <div class="workspace-grid">
            {#each snapshot?.top_divergences ?? [] as row}
              <article class="cross-card">
                <div class="card-head">
                  <div>
                    <small class="eyebrow">{themeLabels[row.theme as MacroTheme] ?? row.theme}</small>
                    <h3>{row.headline}</h3>
                  </div>
                  <div class="card-badges">
                    <span class="score-badge {row.label}">{row.score.toFixed(1)}</span>
                    <span class="tag agreement">{row.label}</span>
                  </div>
                </div>
                <p class="card-summary">{row.summary}</p>
                {#if row.primary_driver || row.counter_signal}
                  <div class="divergence-detail-grid list-embedded">
                    {#if row.primary_driver}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lead driver</span>
                          <span class="signal-score {row.primary_driver.tone}">{row.primary_driver.signal_score_display}</span>
                        </div>
                        <strong>{row.primary_driver.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(row.primary_driver.tone)}">{row.primary_driver.interpretation}</p>
                      </article>
                    {/if}
                    {#if row.counter_signal}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Counter-signal</span>
                          <span class="signal-score {row.counter_signal.tone}">{row.counter_signal.signal_score_display}</span>
                        </div>
                        <strong>{row.counter_signal.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(row.counter_signal.tone)}">{row.counter_signal.interpretation}</p>
                      </article>
                    {/if}
                  </div>
                {/if}
                {#if row.research_focus}
                  <p class="research-focus">{row.research_focus}</p>
                {/if}
              </article>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No regime framing is available for this lens yet.</p>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Recent Windows</p>
            <h3>Post-event absorption</h3>
          </div>
        </div>
        {#if recentEventStudies.length}
          <div class="list events-scroll">
            {#each recentEventStudies as study}
              <article class="list-row study-row">
                <div class="card-head-top">
                  <strong>{study.event.title}</strong>
                  <span class="tag agreement">{themeLabels[study.theme as MacroTheme] ?? study.theme}</span>
                </div>
                <span class="list-detail">
                  <span class="event-date">{shortDate(study.event.scheduled_at)}</span>
                  <span class="event-category">{study.window_label}</span>
                </span>
                <p class="card-summary">{study.summary}</p>
                {#if study.primary_reaction || study.counter_reaction}
                  <div class="divergence-detail-grid list-embedded">
                    {#if study.primary_reaction}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lead reaction</span>
                          <span class="signal-score {study.primary_reaction.tone}">{study.primary_reaction.signal_score_display}</span>
                        </div>
                        <strong>{study.primary_reaction.metric.label}</strong>
                        <p class="signal-summary {eventStudyTone(study.primary_reaction.tone)}">{study.primary_reaction.interpretation}</p>
                      </article>
                    {/if}
                    {#if study.counter_reaction}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lagging reaction</span>
                          <span class="signal-score {study.counter_reaction.tone}">{study.counter_reaction.signal_score_display}</span>
                        </div>
                        <strong>{study.counter_reaction.metric.label}</strong>
                        <p class="signal-summary {eventStudyTone(study.counter_reaction.tone)}">{study.counter_reaction.interpretation}</p>
                      </article>
                    {/if}
                  </div>
                {/if}
                {#if study.research_focus}
                  <p class="research-focus">{study.research_focus}</p>
                {/if}
              </article>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No recent event windows are available yet.</p>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Upcoming Windows</p>
            <h3>Pre-event setup</h3>
          </div>
        </div>
        {#if upcomingEventStudies.length}
          <div class="list events-scroll">
            {#each upcomingEventStudies as study}
              <article class="list-row study-row">
                <div class="card-head-top">
                  <strong>{study.event.title}</strong>
                  <span class="tag">{themeLabels[study.theme as MacroTheme] ?? study.theme}</span>
                </div>
                <span class="list-detail">
                  <span class="event-date">{shortDate(study.event.scheduled_at)}</span>
                  <span class="event-category">{study.window_label}</span>
                </span>
                <p class="card-summary">{study.summary}</p>
                {#if study.primary_reaction || study.counter_reaction}
                  <div class="divergence-detail-grid list-embedded">
                    {#if study.primary_reaction}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lead setup</span>
                          <span class="signal-score {study.primary_reaction.tone}">{study.primary_reaction.signal_score_display}</span>
                        </div>
                        <strong>{study.primary_reaction.metric.label}</strong>
                        <p class="signal-summary {eventStudyTone(study.primary_reaction.tone)}">{study.primary_reaction.interpretation}</p>
                      </article>
                    {/if}
                    {#if study.counter_reaction}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Counter-signal</span>
                          <span class="signal-score {study.counter_reaction.tone}">{study.counter_reaction.signal_score_display}</span>
                        </div>
                        <strong>{study.counter_reaction.metric.label}</strong>
                        <p class="signal-summary {eventStudyTone(study.counter_reaction.tone)}">{study.counter_reaction.interpretation}</p>
                      </article>
                    {/if}
                  </div>
                {/if}
                {#if study.linked_markets?.length}
                  <div class="linked-market-list">
                    {#each study.linked_markets as market}
                      <article class="linked-market-card compact">
                        <div class="linked-market-head">
                          <strong>{market.title}</strong>
                          <span class="tag">{market.venue}</span>
                        </div>
                        <div class="linked-market-stats">
                          {#if market.probability_label}
                            <span>{market.probability_label}</span>
                          {/if}
                          {#if market.change_display}
                            <span class={linkedMarketTone(market.macro_alignment)}>{market.change_display}</span>
                          {/if}
                          <span class={linkedMarketTone(market.macro_alignment)}>{market.macro_alignment}</span>
                        </div>
                        <p class="linked-market-summary {linkedMarketTone(market.macro_alignment)}">{market.macro_alignment_summary}</p>
                      </article>
                    {/each}
                  </div>
                {/if}
                {#if study.research_focus}
                  <p class="research-focus">{study.research_focus}</p>
                {/if}
              </article>
            {/each}
          </div>
        {:else}
          <p class="empty-hint">No upcoming event windows are available yet.</p>
        {/if}
      </article>

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Calendar</p>
            <h3>Scheduled catalysts</h3>
          </div>
        </div>
        {#if groupedEvents.length}
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
          <p class="empty-hint">No event calendar entries are available for this region.</p>
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
                  <div class="card-badges">
                    {#if card.divergence_score !== null}
                      <span class="score-badge {card.agreement_label}">{card.divergence_score.toFixed(1)}</span>
                    {/if}
                    <span class="tag agreement">{card.agreement_label}</span>
                  </div>
                </div>
                <p class="card-subtitle">{card.summary}</p>
                {#if card.comparison_summary}
                  <p class="comparison-summary">{card.comparison_summary}</p>
                {/if}
                {#if card.primary_driver || card.counter_signal}
                  <div class="divergence-detail-grid">
                    {#if card.primary_driver}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lead driver</span>
                          <span class="signal-score {card.primary_driver.tone}">{card.primary_driver.signal_score_display}</span>
                        </div>
                        <strong>{card.primary_driver.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(card.primary_driver.tone)}">{card.primary_driver.interpretation}</p>
                      </article>
                    {/if}
                    {#if card.counter_signal}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Counter-signal</span>
                          <span class="signal-score {card.counter_signal.tone}">{card.counter_signal.signal_score_display}</span>
                        </div>
                        <strong>{card.counter_signal.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(card.counter_signal.tone)}">{card.counter_signal.interpretation}</p>
                      </article>
                    {/if}
                  </div>
                {/if}
                {#if card.research_focus}
                  <p class="research-focus">{card.research_focus}</p>
                {/if}
                {#if card.linked_markets?.length}
                  <div class="linked-market-list">
                    {#each card.linked_markets as market}
                      <article class="linked-market-card compact">
                        <div class="linked-market-head">
                          <strong>{market.title}</strong>
                          <span class="tag">{market.venue}</span>
                        </div>
                        <div class="linked-market-stats">
                          {#if market.probability_label}
                            <span>{market.probability_label}</span>
                          {/if}
                          {#if market.change_display}
                            <span class={linkedMarketTone(market.macro_alignment)}>{market.change_display}</span>
                          {/if}
                          <span class={linkedMarketTone(market.macro_alignment)}>{market.macro_alignment}</span>
                        </div>
                        <p class="linked-market-summary {linkedMarketTone(market.macro_alignment)}">{market.macro_alignment_summary}</p>
                      </article>
                    {/each}
                  </div>
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
                {#if row.primary_driver || row.counter_signal}
                  <div class="divergence-detail-grid list-embedded">
                    {#if row.primary_driver}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Lead driver</span>
                          <span class="signal-score {row.primary_driver.tone}">{row.primary_driver.signal_score_display}</span>
                        </div>
                        <strong>{row.primary_driver.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(row.primary_driver.tone)}">{row.primary_driver.interpretation}</p>
                      </article>
                    {/if}
                    {#if row.counter_signal}
                      <article class="signal-brief">
                        <div class="signal-head">
                          <span class="signal-label">Counter-signal</span>
                          <span class="signal-score {row.counter_signal.tone}">{row.counter_signal.signal_score_display}</span>
                        </div>
                        <strong>{row.counter_signal.metric.label}</strong>
                        <p class="signal-summary {divergenceSignalTone(row.counter_signal.tone)}">{row.counter_signal.interpretation}</p>
                      </article>
                    {/if}
                  </div>
                {/if}
                {#if row.research_focus}
                  <p class="research-focus">{row.research_focus}</p>
                {/if}
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
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
    gap: 0.35rem;
  }

  .cross-card {
    gap: 0.45rem;
  }

  /* ── Header block ── */
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
  .headline-strip {
    display: flex;
    gap: 0;
  }

  .headline-kpi {
    padding: 0.2rem 0.65rem;
    border-left: 1px solid rgba(46, 60, 74, 0.42);
    text-align: right;
  }

  .headline-kpi:first-child {
    border-left: 0;
  }

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

  .headline-kpi-delta.positive {
    color: var(--positive);
  }

  .headline-kpi-delta.negative {
    color: var(--negative);
  }

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

  .next-event-title {
    color: var(--text-1);
    font-size: 0.84rem;
  }

  .next-event-date {
    color: var(--text-2);
    font-size: 0.8rem;
  }

  .next-event-date::before {
    content: "·";
    margin-right: 0.5rem;
    opacity: 0.5;
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

  /* ── Mode bar + KPI row ── */
  .mode-kpi-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    position: relative;
  }

  .mode-bar {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border: 1px solid var(--panel-strong);
    background: rgba(8, 13, 18, 0.82);
    max-width: 28rem;
    width: 100%;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.4rem 0.55rem;
    font: inherit;
    font-size: 0.76rem;
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

  /* ── Snapshot table ── */
  .snapshot-table-panel {
    padding: 0;
    overflow: hidden;
  }

  .snapshot-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }

  .snapshot-table thead th {
    padding: 0.4rem 0.55rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.4);
    color: var(--text-2);
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(8, 13, 18, 0.82);
    position: sticky;
    top: 0;
    z-index: 1;
    text-align: left;
    font-weight: 500;
  }

  .snapshot-table .col-theme {
    width: 22%;
  }

  .snapshot-table .col-drill {
    width: 7%;
  }

  .snapshot-table .col-metric {
    width: auto;
  }

  .snapshot-row {
    cursor: pointer;
    transition: background 120ms ease;
  }

  .snapshot-row:hover {
    background: rgba(122, 166, 200, 0.05);
  }

  .snapshot-row:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .snapshot-row td {
    padding: 0.45rem 0.55rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.25);
    vertical-align: top;
  }

  .snapshot-row:last-child td {
    border-bottom: 0;
  }

  .row-theme {
    display: block;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-0);
    line-height: 1.3;
  }

  .row-summary {
    display: block;
    color: var(--text-2);
    font-size: 0.68rem;
    line-height: 1.3;
    margin-top: 0.15rem;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .col-drill {
    vertical-align: middle !important;
  }

  .card-head {
    display: grid;
    gap: 0.15rem;
  }

  .card-head-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
  }

  .card-head h3 {
    font-size: 0.92rem;
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

  .linked-market-list {
    display: grid;
    gap: 0;
  }

  .linked-hint {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    margin-top: 0.25rem;
    color: var(--text-2);
    font-size: 0.64rem;
  }

  .linked-dot {
    display: inline-block;
    width: 0.42rem;
    height: 0.42rem;
    border-radius: 50%;
    background: var(--text-2);
    flex-shrink: 0;
  }

  .linked-dot.positive {
    background: var(--positive);
  }

  .linked-dot.negative {
    background: var(--negative);
  }

  .linked-market-list.inline {
    margin-top: 0.35rem;
  }

  .linked-market-chip {
    border: 1px solid rgba(46, 60, 74, 0.34);
    background: rgba(8, 13, 18, 0.55);
    padding: 0.45rem 0.55rem;
    display: grid;
    gap: 0.16rem;
  }

  .linked-market-card {
    padding: 0.35rem 0;
    border-top: 1px solid rgba(46, 60, 74, 0.2);
    display: grid;
    gap: 0.12rem;
  }

  .linked-market-card:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .linked-market-card.compact {
    padding: 0.3rem 0;
  }

  .linked-market-head,
  .linked-market-meta,
  .linked-market-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    align-items: center;
  }

  .linked-market-chip strong,
  .linked-market-card strong {
    font-size: 0.76rem;
    line-height: 1.35;
  }

  .linked-market-meta,
  .linked-market-stats {
    color: var(--text-2);
    font-size: 0.66rem;
  }

  .linked-market-summary {
    color: var(--text-2);
    font-size: 0.72rem;
    line-height: 1.35;
    margin: 0;
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

  .card-badges {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .divergence-detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 0.25rem;
    margin-top: 0.25rem;
  }

  .divergence-detail-grid.list-embedded {
    margin-top: 0.2rem;
  }

  .signal-brief {
    display: grid;
    gap: 0.2rem;
    padding: 0.4rem 0;
  }

  .signal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.45rem;
  }

  .signal-label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-2);
  }

  .signal-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 3rem;
    padding: 0.15rem 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(46, 60, 74, 0.42);
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-1);
    font-size: 0.68rem;
    font-weight: 600;
  }

  .signal-score.reinforcing {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.08);
    color: var(--positive);
  }

  .signal-score.opposing {
    border-color: rgba(198, 107, 97, 0.3);
    background: rgba(198, 107, 97, 0.1);
    color: var(--negative);
  }

  .signal-summary {
    margin: 0;
    color: var(--text-2);
    font-size: 0.73rem;
    line-height: 1.4;
  }

  .research-focus {
    margin: 0.35rem 0 0;
    padding: 0.15rem 0 0.15rem 0.55rem;
    border-left: 2px solid rgba(46, 60, 74, 0.35);
    color: var(--text-2);
    font-size: 0.73rem;
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
    display: flex;
    flex-wrap: wrap;
    gap: 0;
  }

  .metric-row.compact {
    gap: 0;
  }

  .metric {
    padding: 0.4rem 0.5rem;
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

  /* ── Snapshot table metric overrides ── */
  .snapshot-table .metric-label {
    display: block;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.54rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .snapshot-table .metric-value {
    display: block;
    font-size: 0.88rem;
    line-height: 1.2;
    margin-top: 0.08rem;
  }

  .snapshot-table .metric-delta {
    display: inline-block;
    font-size: 0.66rem;
    margin-top: 0.04rem;
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

  .fx-last-price {
    margin-left: auto;
    font-size: 0.92rem;
    color: var(--text-0);
    letter-spacing: 0.02em;
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

  .list-row:first-child {
    padding-top: 0;
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

  .study-row {
    gap: 0.45rem;
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

    .metric {
      padding: 0.4rem 0;
      border-left: 0;
      flex: 1 1 45%;
    }

    .header-top {
      flex-direction: column;
      gap: 0.4rem;
    }

    .headline-strip,
    .next-event {
      display: none;
    }
  }
</style>
