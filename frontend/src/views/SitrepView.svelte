<script lang="ts">
  import { onMount } from "svelte";
  import SitrepMarketTable from "../components/SitrepMarketTable.svelte";
  import type {
    CommodityWorkspaceResponse,
    MacroMetric,
    MacroSnapshot,
    PredictionMarketListResponse,
    ResearchOverviewNode,
    ResearchOverviewResponse,
    SystemStatus
  } from "../lib/api/types";
  import type {
    CommodityWorkspaceLoadOptions,
    MacroLoadOptions,
    PredictionMarketScreenerOptions,
    ResearchOverviewLoadOptions
  } from "../lib/stores/app";

  export let system: SystemStatus | null = null;
  export let overview: ResearchOverviewResponse | null = null;
  export let macro: MacroSnapshot | null = null;
  export let commodities: CommodityWorkspaceResponse | null = null;
  export let prediction: PredictionMarketListResponse | null = null;
  export let loading = false;
  export let onLoadOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void;
  export let onLoadMacro: (options?: MacroLoadOptions) => Promise<unknown> | void;
  export let onLoadCommodities: (options?: CommodityWorkspaceLoadOptions) => Promise<unknown> | void;
  export let onLoadPrediction: (options?: PredictionMarketScreenerOptions) => Promise<unknown> | void;

  const bloombergChannelId = "UCIALMKvObZNtJ6AmdCLP7Lg";
  const bloombergEmbedUrl = `https://www.youtube.com/embed/live_stream?channel=${bloombergChannelId}&autoplay=0&mute=1`;
  const bloombergWatchUrl = "https://www.youtube.com/@markets/live";

  type TapeRow = {
    id: string;
    source: string;
    tone: "positive" | "negative" | "warning" | "neutral";
    title: string;
    detail: string;
    meta: string;
  };

  type SitrepMarketRow = {
    id: string;
    label: string;
    group: string;
    last: string;
    change: string;
    secondary: string;
    tone: string;
    source: string;
  };

  onMount(() => {
    const tasks: Array<Promise<unknown> | void> = [];
    if (!overview) {
      tasks.push(onLoadOverview({ universeId: "broad_us_market", timeframe: "3M", benchmarkSymbol: "SPY" }));
    }
    if (!macro) {
      tasks.push(onLoadMacro({ region: "US", timeframe: "3M", theme: "all", mode: "snapshot" }));
    }
    if (!commodities) {
      tasks.push(onLoadCommodities({ mode: "overview" }));
    }
    if (!prediction) {
      tasks.push(onLoadPrediction({ status: "open", sortBy: "research_rank", limit: 12 }));
    }
    if (tasks.length) {
      void Promise.allSettled(tasks);
    }
  });

  function formatNumber(value: number | null | undefined, digits = 2) {
    if (value == null || !Number.isFinite(value)) {
      return "N/A";
    }
    const abs = Math.abs(value);
    if (abs >= 1_000_000_000_000) {
      return `${(value / 1_000_000_000_000).toFixed(1)}T`;
    }
    if (abs >= 1_000_000_000) {
      return `${(value / 1_000_000_000).toFixed(1)}B`;
    }
    if (abs >= 1_000_000) {
      return `${(value / 1_000_000).toFixed(1)}M`;
    }
    if (abs >= 1_000) {
      return `${(value / 1_000).toFixed(1)}K`;
    }
    return value.toFixed(digits);
  }

  function formatPct(value: number | null | undefined, digits = 1) {
    if (value == null || !Number.isFinite(value)) {
      return "N/A";
    }
    const scaled = value * 100;
    const sign = scaled > 0 ? "+" : "";
    return `${sign}${scaled.toFixed(digits)}%`;
  }

  function formatDateTime(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value.slice(0, 16);
    }
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  function shortDate(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value.slice(0, 10);
    }
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function toneFromValue(value: number | null | undefined) {
    if (value == null || !Number.isFinite(value)) {
      return "";
    }
    return value > 0 ? "positive" : value < 0 ? "negative" : "";
  }

  function toneFromText(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (!normalized) {
      return "";
    }
    if (normalized.startsWith("+") || normalized.includes("backwardation") || normalized.includes("firm")) {
      return "positive";
    }
    if (normalized.startsWith("-") || normalized.includes("contango") || normalized.includes("stale")) {
      return "negative";
    }
    if (normalized.includes("warning") || normalized.includes("sample") || normalized.includes("proxy")) {
      return "warning";
    }
    return "";
  }

  function humanize(value: string | null | undefined) {
    return (value ?? "N/A").replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function allMacroMetrics(data: MacroSnapshot | null): MacroMetric[] {
    return data?.snapshot_cards.flatMap((card) => card.metrics) ?? [];
  }

  function metricMatches(metric: MacroMetric, terms: string[]) {
    const haystack = `${metric.series_id ?? ""} ${metric.metric_id} ${metric.label}`.toLowerCase();
    return terms.some((term) => haystack.includes(term));
  }

  function metricRow(metric: MacroMetric): SitrepMarketRow {
    return {
      id: metric.metric_id,
      label: metric.label,
      group: metric.series_id ?? "macro",
      last: metric.display_value ?? formatNumber(metric.value),
      change: metric.delta_display ?? "N/A",
      secondary: metric.gap_display ?? metric.comparison_display_value ?? metric.unit ?? "",
      tone: toneFromValue(metric.delta_value),
      source: metric.source_provider
    };
  }

  function uniqueMetrics(metrics: MacroMetric[]) {
    const seen = new Set<string>();
    return metrics.filter((metric) => {
      const key = metric.series_id ?? metric.metric_id ?? metric.label;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  function buildFxRows(data: MacroSnapshot | null): SitrepMarketRow[] {
    const directRows = uniqueMetrics(
      allMacroMetrics(data)
        .filter((metric) => metricMatches(metric, ["fx-", "eurusd", "gbpusd", "usdjpy", "dollar", "eur/usd", "usd/jpy"]))
    )
      .map(metricRow);
    return directRows.length ? directRows.slice(0, 8) : [
      {
        id: "fx-placeholder",
        label: "FX strip",
        group: "provider needed",
        last: "N/A",
        change: "N/A",
        secondary: "Load Macro Snapshot FX histories",
        tone: "warning",
        source: "macro workspace"
      }
    ];
  }

  function buildYieldRows(data: MacroSnapshot | null): SitrepMarketRow[] {
    const curveRows = (data?.rates_policy?.curve_nodes ?? []).map((node) => ({
      id: `curve-${node.tenor}`,
      label: `${node.tenor} yield`,
      group: data?.region ?? "US",
      last: node.current_value == null ? "N/A" : `${node.current_value.toFixed(2)}%`,
      change: node.change_bps == null ? "N/A" : `${node.change_bps > 0 ? "+" : ""}${node.change_bps.toFixed(1)} bps`,
      secondary: node.prior_value == null ? "" : `prior ${node.prior_value.toFixed(2)}%`,
      tone: toneFromValue(node.change_bps),
      source: node.source_provider
    }));
    const policyRows = (data?.rates_policy?.policy_metrics ?? []).slice(0, 4).map(metricRow);
    return [...curveRows, ...policyRows].slice(0, 9);
  }

  function buildEquityRows(data: ResearchOverviewResponse | null): SitrepMarketRow[] {
    const nodes = (data?.nodes ?? [])
      .filter((node): node is ResearchOverviewNode => node.level === "instrument")
      .sort((left, right) => (right.size ?? 0) - (left.size ?? 0))
      .slice(0, 12);
    return nodes.map((node) => ({
      id: node.node_id,
      label: node.symbol ?? node.label,
      group: node.group ?? node.sector ?? "Equity",
      last: node.metrics.latest_price == null ? "N/A" : formatNumber(node.metrics.latest_price, 2),
      change: formatPct(node.metrics.total_return),
      secondary: `vol ${formatPct(node.metrics.annual_volatility)}`,
      tone: toneFromValue(node.metrics.total_return),
      source: node.freshness_label
    }));
  }

  function buildCommodityRows(data: CommodityWorkspaceResponse | null): SitrepMarketRow[] {
    const overviewRows = data?.overview?.matrix_rows ?? [];
    if (overviewRows.length) {
      return overviewRows.slice(0, 12).map((row) => ({
        id: row.instrument_id,
        label: row.symbol,
        group: humanize(row.family),
        last: row.latest_price == null ? "N/A" : formatNumber(row.latest_price, 2),
        change: row.latest_change_pct == null
          ? row.latest_change == null ? "N/A" : formatNumber(row.latest_change, 2)
          : formatPct(row.latest_change_pct),
        secondary: row.curve_state,
        tone: toneFromValue(row.latest_change_pct ?? row.latest_change),
        source: row.price_source_provider ?? row.source_provider
      }));
    }
    return (data?.market_summaries ?? []).slice(0, 12).map((summary) => ({
      id: summary.instrument.instrument_id,
      label: summary.instrument.symbol,
      group: humanize(summary.instrument.family),
      last: summary.latest_price == null ? "N/A" : formatNumber(summary.latest_price, 2),
      change: summary.latest_change_pct == null ? "N/A" : formatPct(summary.latest_change_pct),
      secondary: summary.curve_state,
      tone: toneFromValue(summary.latest_change_pct),
      source: summary.source_provider
    }));
  }

  function buildTapeRows(
    macroData: MacroSnapshot | null,
    predictionData: PredictionMarketListResponse | null,
    commodityData: CommodityWorkspaceResponse | null
  ): TapeRow[] {
    const focusRows: TapeRow[] = (macroData?.focus_items ?? []).slice(0, 4).map((item) => ({
      id: item.focus_id,
      source: "Macro",
      tone: item.signal_label?.toLowerCase().includes("risk") ? "warning" : "neutral",
      title: item.title,
      detail: item.why_now || item.summary,
      meta: item.source_provider
    }));
    const eventRows: TapeRow[] = (macroData?.upcoming_events ?? []).slice(0, 4).map((event) => ({
      id: event.event_id,
      source: "Event",
      tone: event.importance === "high" ? "warning" : "neutral",
      title: event.title,
      detail: `${humanize(event.category)} / ${event.region}`,
      meta: event.relative_label ?? shortDate(event.scheduled_at)
    }));
    const marketRows: TapeRow[] = (predictionData?.markets ?? []).slice(0, 4).map((market) => ({
      id: market.market_id,
      source: market.venue,
      tone: market.recent_price_change == null
        ? "neutral"
        : market.recent_price_change > 0
          ? "positive"
          : "negative",
      title: market.title,
      detail: market.probability_label ?? (market.current_probability == null ? "No probability" : formatPct(market.current_probability)),
      meta: market.freshness?.status ?? market.status
    }));
    const commodityRows: TapeRow[] = (commodityData?.events ?? []).slice(0, 3).map((event) => ({
      id: event.event_id,
      source: "Commodity",
      tone: event.importance === "high" ? "warning" : "neutral",
      title: event.title,
      detail: event.summary ?? humanize(event.category),
      meta: event.relative_label ?? shortDate(event.scheduled_at)
    }));
    return [...focusRows, ...eventRows, ...marketRows, ...commodityRows].slice(0, 14);
  }

  function buildWhatChangedRows(
    macroData: MacroSnapshot | null,
    overviewData: ResearchOverviewResponse | null,
    commodityData: CommodityWorkspaceResponse | null
  ): TapeRow[] {
    const divergenceRows: TapeRow[] = (macroData?.top_divergences ?? []).slice(0, 4).map((item) => ({
      id: item.divergence_id,
      source: humanize(item.theme),
      tone: item.label === "high" ? "warning" : item.score > 0 ? "neutral" : "negative",
      title: item.headline,
      detail: item.research_focus ?? item.summary,
      meta: `score ${item.score.toFixed(1)} / ${item.label}`
    }));
    const movers: TapeRow[] = buildCommodityRows(commodityData)
      .filter((row) => row.change !== "N/A")
      .slice(0, 3)
      .map((row) => ({
        id: `commodity-${row.id}`,
        source: "Commodity",
        tone: row.tone === "positive" ? "positive" : row.tone === "negative" ? "negative" : "neutral",
        title: `${row.label} ${row.change}`,
        detail: `${row.group} / ${row.secondary}`,
        meta: row.source
      }));
    const equityLeader = overviewData?.rankings.leaders?.[0];
    const equityLaggard = overviewData?.rankings.laggards?.[0];
    const equityRows: TapeRow[] = [equityLeader, equityLaggard]
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .map((item) => ({
        id: `equity-${item.node_id}`,
        source: "Equity",
        tone: (item.value ?? 0) >= 0 ? "positive" : "negative",
        title: `${item.symbol ?? item.label} ${formatPct(item.value)}`,
        detail: item.group ?? "Market overview",
        meta: overviewData?.freshness_label ?? "research overview"
      }));
    return [...divergenceRows, ...equityRows, ...movers].slice(0, 10);
  }

  function warningRows(
    overviewData: ResearchOverviewResponse | null,
    macroData: MacroSnapshot | null,
    commodityData: CommodityWorkspaceResponse | null,
    predictionData: PredictionMarketListResponse | null
  ) {
    return [
      ...(overviewData?.warnings ?? []),
      ...(macroData?.warnings ?? []),
      ...(commodityData?.warnings ?? []),
      ...(commodityData?.coverage.caveats ?? []),
      ...(predictionData?.warnings ?? [])
    ].slice(0, 6);
  }

  $: equityRows = buildEquityRows(overview);
  $: fxRows = buildFxRows(macro);
  $: yieldRows = buildYieldRows(macro);
  $: commodityRows = buildCommodityRows(commodities);
  $: tapeRows = buildTapeRows(macro, prediction, commodities);
  $: changedRows = buildWhatChangedRows(macro, overview, commodities);
  $: warnings = warningRows(overview, macro, commodities, prediction);
  $: asOf = macro?.retrieved_at ?? overview?.retrieved_at ?? commodities?.retrieved_at ?? null;
  $: pricedRatio = overview?.coverage.coverage_ratio ?? null;
  $: highDivergences = (macro?.top_divergences ?? []).filter((item) => item.label === "high").length;
  $: staleMarkets = (prediction?.venues ?? []).reduce((total, venue) => total + venue.stale_markets + venue.broken_markets, 0);
  $: providerMode = system?.mock_mode ? "MOCK" : system?.connection.connected ? system.market_data_mode.toUpperCase() : "OFFLINE";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div>
        <p class="eyebrow">SITREP</p>
        <h2>Situation Report</h2>
      </div>
      <div class="status-line">
        <span class:warning={loading}>{loading ? "REFRESHING" : "LIVE SNAPSHOT"}</span>
        <span>{providerMode}</span>
        <span>{formatDateTime(asOf)}</span>
      </div>
    </div>

    <div class="kpi-strip">
      <div class="metric">
        <span>Equity Coverage</span>
        <strong>{pricedRatio == null ? "N/A" : `${(pricedRatio * 100).toFixed(0)}%`}</strong>
        <small>{overview?.coverage.coverage_label ?? "Research Overview not loaded"}</small>
      </div>
      <div class="metric">
        <span>Macro Breaks</span>
        <strong class:warning={highDivergences > 0}>{highDivergences}</strong>
        <small>{macro?.region ?? "US"} / {macro?.timeframe ?? "3M"} lens</small>
      </div>
      <div class="metric">
        <span>Commodity Source</span>
        <strong class={toneFromText(commodities?.coverage.coverage_status)}>{commodities?.coverage.provider_label ?? "N/A"}</strong>
        <small>{commodities?.coverage.freshness_label ?? "No commodity payload"}</small>
      </div>
      <div class="metric">
        <span>Prediction Health</span>
        <strong class:warning={staleMarkets > 0}>{staleMarkets}</strong>
        <small>{prediction?.markets.length ?? 0} open contracts loaded</small>
      </div>
      <div class="metric">
        <span>Warnings</span>
        <strong class:warning={warnings.length > 0}>{warnings.length}</strong>
        <small>Provider caveats and stale-data notes</small>
      </div>
    </div>
  </article>

  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel tape-panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Triage</p>
            <h3>What Changed</h3>
          </div>
          <small>Cross-domain handoff candidates</small>
        </div>
        <div class="tape-list">
          {#if changedRows.length}
            {#each changedRows as row}
              <div class="tape-row {row.tone}">
                <span>{row.source}</span>
                <strong>{row.title}</strong>
                <p>{row.detail}</p>
                <small>{row.meta}</small>
              </div>
            {/each}
          {:else}
            <p class="empty-state">LOAD MARKET CONTEXT TO POPULATE CHANGE TRIAGE.</p>
          {/if}
        </div>
      </article>

      <div class="market-grid">
        <article class="panel table-panel">
          <div class="panel-head">
            <div><p class="eyebrow">Equities</p><h3>Market Map Table</h3></div>
            <small>{overview?.universe_label ?? "Broad US Market"}</small>
          </div>
          <SitrepMarketTable rows={equityRows} emptyLabel="No equity overview loaded." />
        </article>

        <article class="panel table-panel">
          <div class="panel-head">
            <div><p class="eyebrow">FX</p><h3>Dollar / FX Readout</h3></div>
            <small>{macro?.source_provider ?? "Macro Snapshot"}</small>
          </div>
          <SitrepMarketTable rows={fxRows} emptyLabel="No FX strip loaded." />
        </article>

        <article class="panel table-panel">
          <div class="panel-head">
            <div><p class="eyebrow">Yields</p><h3>Rates Table</h3></div>
            <small>{macro?.rates_policy?.source_provider ?? "Treasury / FRED"}</small>
          </div>
          <SitrepMarketTable rows={yieldRows} emptyLabel="No rates policy payload loaded." />
        </article>

        <article class="panel table-panel">
          <div class="panel-head">
            <div><p class="eyebrow">Commodities</p><h3>Futures / Physical Proxies</h3></div>
            <small>{commodities?.coverage.coverage_status ?? "not loaded"}</small>
          </div>
          <SitrepMarketTable rows={commodityRows} emptyLabel="No commodities workspace loaded." />
        </article>
      </div>
    </div>

    <aside class="support-column">
      <article class="panel media-panel">
        <div class="panel-head">
          <div><p class="eyebrow">Live Media</p><h3>Bloomberg TV</h3></div>
          <a href={bloombergWatchUrl} target="_blank" rel="noreferrer">YouTube</a>
        </div>
        <div class="video-shell">
          <iframe
            title="Bloomberg Television live stream"
            src={bloombergEmbedUrl}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowfullscreen
          ></iframe>
        </div>
        <p class="source-note">Uses the public Bloomberg Television YouTube live-stream endpoint. Availability depends on YouTube and Bloomberg embed policy.</p>
      </article>

      <article class="panel tape-panel">
        <div class="panel-head">
          <div><p class="eyebrow">News / Events</p><h3>Event Tape</h3></div>
          <small>RSS provider pending</small>
        </div>
        <div class="tape-list compact">
          {#if tapeRows.length}
            {#each tapeRows as row}
              <div class="tape-row {row.tone}">
                <span>{row.source}</span>
                <strong>{row.title}</strong>
                <p>{row.detail}</p>
                <small>{row.meta}</small>
              </div>
            {/each}
          {:else}
            <p class="empty-state">No event or market tape loaded.</p>
          {/if}
        </div>
      </article>

      <article class="panel provider-panel">
        <div class="panel-head">
          <div><p class="eyebrow">Coverage</p><h3>Provider Needs</h3></div>
        </div>
        <div class="need-list">
          <div><strong>News</strong><span>Needs a normalized RSS/news adapter for real headline coverage.</span></div>
          <div><strong>TV</strong><span>YouTube embed is best-effort and can be blocked by remote policy.</span></div>
          <div><strong>Listed Markets</strong><span>Uses current Research Overview provider coverage; fuller live breadth needs provider-neutral market data depth.</span></div>
          <div><strong>FX / Rates</strong><span>Uses Macro/FRED/IBKR paths where present; intraday real-time coverage remains provider-dependent.</span></div>
        </div>
        {#if warnings.length}
          <ul class="warning-list">
            {#each warnings as warning}
              <li>{warning}</li>
            {/each}
          </ul>
        {/if}
      </article>
    </aside>
  </div>
</section>

<style>
  .view {
    display: grid;
    gap: 0.5rem;
  }

  .panel {
    display: grid;
    gap: 0.5rem;
    align-content: start;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
  }

  .header-panel {
    gap: 0.55rem;
  }

  .header-top,
  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
    min-width: 0;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.1rem;
  }

  h3 {
    font-size: 0.92rem;
  }

  .eyebrow {
    margin: 0 0 0.08rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.62rem;
  }

  .status-line {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0;
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .status-line span {
    padding: 0 0.55rem;
    border-left: 1px solid var(--divider);
  }

  .status-line span:first-child {
    border-left: 0;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(21rem, 0.36fr);
    gap: 0.5rem;
  }

  .primary-column,
  .support-column {
    display: grid;
    gap: 0.5rem;
    align-content: start;
    min-width: 0;
  }

  .market-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0;
    border-top: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
  }

  .metric {
    display: grid;
    gap: 0.12rem;
    min-width: 0;
    padding: 0.45rem 0.65rem;
    border-right: 1px solid var(--divider);
  }

  .metric:last-child {
    border-right: 0;
  }

  .metric span,
  .tape-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
  }

  .metric strong {
    color: var(--text-0);
    font-size: 0.95rem;
    overflow-wrap: anywhere;
  }

  .metric small,
  .panel-head small,
  .source-note,
  .tape-row small,
  .need-list span {
    color: var(--text-2);
    line-height: 1.35;
  }

  .tape-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .tape-list.compact {
    max-height: 23rem;
    overflow: auto;
  }

  .tape-row {
    display: grid;
    grid-template-columns: 5.8rem minmax(0, 0.9fr) minmax(0, 1.7fr) minmax(5.5rem, 0.45fr);
    gap: 0.5rem;
    align-items: baseline;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .tape-list.compact .tape-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.16rem;
  }

  .tape-row strong,
  .tape-row p,
  .tape-row small {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .tape-row p {
    color: var(--text-1);
    line-height: 1.35;
  }

  .video-shell {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: hidden;
  }

  .video-shell iframe {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--bg-0);
  }

  a {
    color: var(--accent);
    text-decoration: none;
    font-size: 0.76rem;
  }

  a:hover {
    color: var(--text-0);
  }

  .need-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .need-list div {
    display: grid;
    grid-template-columns: 7.5rem minmax(0, 1fr);
    gap: 0.5rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .warning-list {
    margin: 0;
    padding-left: 1rem;
    color: var(--text-2);
    line-height: 1.4;
  }

  .empty-state {
    margin: 0;
    padding: 0.75rem 0;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
  }

  .positive {
    color: var(--positive) !important;
  }

  .negative {
    color: var(--negative) !important;
  }

  .warning {
    color: var(--warning) !important;
  }

  .neutral {
    color: var(--text-1);
  }

  @media (max-width: 1250px) {
    .workspace-grid,
    .market-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .support-column {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .provider-panel {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: 820px) {
    .header-top,
    .panel-head,
    .support-column {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      justify-content: stretch;
    }

    .status-line {
      justify-content: flex-start;
    }

    .kpi-strip {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .metric {
      border-bottom: 1px solid var(--divider);
    }

    .metric:nth-child(2n) {
      border-right: 0;
    }

    .tape-row {
      grid-template-columns: minmax(0, 1fr);
      gap: 0.16rem;
    }

    .need-list div {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
