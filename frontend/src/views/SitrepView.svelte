<script lang="ts">
  import { onMount } from "svelte";
  import { flashOnMount } from "../lib/flash";
  import SitrepMarketTable from "../components/SitrepMarketTable.svelte";
  import type {
    CommodityWorkspaceResponse,
    MacroMetric,
    MacroSnapshot,
    NewsEventFeedResponse,
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
  export let indicesOverview: ResearchOverviewResponse | null = null;
  export let news: NewsEventFeedResponse | null = null;
  export let macro: MacroSnapshot | null = null;
  export let commodities: CommodityWorkspaceResponse | null = null;
  export let prediction: PredictionMarketListResponse | null = null;
  export let loading = false;
  export let onLoadNews: (options?: { limit?: number; forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onLoadOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void;
  export let onLoadIndicesOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void = onLoadOverview;
  export let onLoadMacro: (options?: MacroLoadOptions) => Promise<unknown> | void;
  export let onLoadCommodities: (options?: CommodityWorkspaceLoadOptions) => Promise<unknown> | void;
  export let onLoadPrediction: (options?: PredictionMarketScreenerOptions) => Promise<unknown> | void;
  export let selectedEquitySymbol: string | null = null;
  export let onSelectEquity: ((symbol: string, label?: string | null) => void) | null = null;

  const bloombergLiveVideoId = "iEpJwprxDdk";
  const bloombergEmbedUrl = `https://www.youtube-nocookie.com/embed/${bloombergLiveVideoId}?autoplay=0&mute=1&playsinline=1&rel=0`;
  const bloombergWatchUrl = `https://www.youtube.com/watch?v=${bloombergLiveVideoId}`;

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
    symbol?: string | null;
    label: string;
    selectionLabel?: string | null;
    group: string;
    last: string;
    change: string;
    changePct?: string;
    changePctTone?: string;
    secondary: string;
    secondaryTone?: string;
    tone: string;
    source: string;
  };

  type RefreshKey = "indices" | "fx" | "rates" | "commodities" | "news";

  const REFRESH_COOLDOWN_MS = 30_000;
  let refreshing: Record<RefreshKey, boolean> = {
    indices: false,
    fx: false,
    rates: false,
    commodities: false,
    news: false
  };
  let cooldownUntil: Record<RefreshKey, number> = {
    indices: 0,
    fx: 0,
    rates: 0,
    commodities: 0,
    news: 0
  };

  function isCoolingDown(key: RefreshKey) {
    return Date.now() < cooldownUntil[key];
  }

  function refreshTitle(key: RefreshKey) {
    if (refreshing[key]) {
      return "Loading latest data";
    }
    if (isCoolingDown(key)) {
      return "Reload cooling down";
    }
    return "Reload latest data";
  }

  async function refreshPanel(key: RefreshKey, loader: () => Promise<unknown> | void) {
    if (refreshing[key] || isCoolingDown(key)) {
      return;
    }
    refreshing = { ...refreshing, [key]: true };
    cooldownUntil = { ...cooldownUntil, [key]: Date.now() + REFRESH_COOLDOWN_MS };
    window.setTimeout(() => {
      cooldownUntil = { ...cooldownUntil, [key]: 0 };
    }, REFRESH_COOLDOWN_MS);
    try {
      await loader();
    } finally {
      refreshing = { ...refreshing, [key]: false };
    }
  }

  function refreshIndices() {
    return refreshPanel("indices", () =>
      onLoadIndicesOverview({
        universeId: "global_indices",
        timeframe: "DoD",
        benchmarkSymbol: "SPY",
        surface: "sitrep",
        forceRefresh: true
      })
    );
  }

  function refreshFx() {
    return refreshPanel("fx", () =>
      onLoadMacro({ region: "US", timeframe: "3M", theme: "all", mode: "snapshot", forceRefresh: true })
    );
  }

  function refreshRates() {
    return refreshPanel("rates", () =>
      onLoadMacro({ region: "US", timeframe: "3M", theme: "all", mode: "snapshot", forceRefresh: true })
    );
  }

  function refreshCommodities() {
    return refreshPanel("commodities", () => onLoadCommodities({ mode: "overview", forceRefresh: true }));
  }

  function refreshNews() {
    return refreshPanel("news", () => onLoadNews({ limit: 25, forceRefresh: true }));
  }

  onMount(() => {
    const tasks: Array<Promise<unknown> | void> = [];
    if (!overview) {
      tasks.push(onLoadOverview({ universeId: "broad_us_market", timeframe: "DoD", benchmarkSymbol: "SPY", surface: "sitrep" }));
    }
    if (!indicesOverview) {
      tasks.push(onLoadIndicesOverview({ universeId: "global_indices", timeframe: "DoD", benchmarkSymbol: "SPY", surface: "sitrep" }));
    }
    if (!macro) {
      tasks.push(onLoadMacro({ region: "US", timeframe: "3M", theme: "all", mode: "snapshot" }));
    }
    if (!news) {
      tasks.push(onLoadNews({ limit: 25 }));
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

  function formatSignedNumber(value: number | null | undefined, digits = 2) {
    if (value == null || !Number.isFinite(value)) {
      return "N/A";
    }
    const formatted = formatNumber(value, digits);
    return value > 0 ? `+${formatted}` : formatted;
  }

  function absoluteChangeFromReturn(latest: number | null | undefined, totalReturn: number | null | undefined) {
    if (
      latest == null ||
      totalReturn == null ||
      !Number.isFinite(latest) ||
      !Number.isFinite(totalReturn) ||
      totalReturn <= -1
    ) {
      return null;
    }
    return latest - latest / (1 + totalReturn);
  }

  function pctChangeFromDelta(current: number | null | undefined, delta: number | null | undefined) {
    if (
      current == null ||
      delta == null ||
      !Number.isFinite(current) ||
      !Number.isFinite(delta)
    ) {
      return null;
    }
    const prior = current - delta;
    if (!Number.isFinite(prior) || prior === 0) {
      return null;
    }
    return delta / prior;
  }

  function formatDateTime(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value.slice(0, 16);
    }
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  function formatTime(value: string | null | undefined) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.slice(11, 16);
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  const SOURCE_ABBREV: Record<string, string> = {
    "marketwatch top stories": "MarketWatch",
    "marketwatch": "MarketWatch",
    "bloomberg markets": "Bloomberg",
    "bloomberg": "Bloomberg",
    "yahoo finance": "Yahoo",
    "reuters": "Reuters",
    "cnbc": "CNBC",
    "financial times": "FT",
    "wall street journal": "WSJ",
    "the wall street journal": "WSJ",
    "24/7 wall st.": "24/7WS",
    "motley fool": "Fool",
    "zacks": "Zacks",
    "seeking alpha": "SeekAlpha",
    "al jazeera": "AJ",
    "oilprice": "OilPrice",
    "gamma sample news": "Gamma",
    "axios": "Axios",
    "business insider": "BI",
    "investor's business daily": "IBD",
    "barron's": "Barron's",
    "thestreet": "TheStreet",
    "benzinga": "Benzinga",
    "fortune": "Fortune",
  };

  function abbreviateSource(name: string): string {
    const key = name.trim().toLowerCase();
    if (SOURCE_ABBREV[key]) return SOURCE_ABBREV[key];
    const words = name.trim().split(/\s+/);
    return words.length > 1 && name.length > 10 ? words[0] : name;
  }

  function shortDate(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value.slice(0, 10);
    }
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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
    const changePct = pctChangeFromDelta(metric.value, metric.delta_value);
    return {
      id: metric.metric_id,
      label: metric.label,
      group: metric.series_id ?? "macro",
      last: metric.display_value ?? formatNumber(metric.value),
      change: metric.delta_display ?? "N/A",
      changePct: formatPct(changePct),
      changePctTone: toneFromValue(changePct ?? metric.delta_value),
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

  const FX_SERIES_ORDER = [
    "fx-eurusd", "fx-gbpusd", "fx-eurgbp", "fx-eurchf", "fx-usdjpy", "fx-usdchf", "fx-usdcnh",
    "fx-usdcad", "fx-audusd", "fx-nzdusd"
  ];

  function buildFxRows(data: MacroSnapshot | null): SitrepMarketRow[] {
    const allFx = uniqueMetrics(
      allMacroMetrics(data).filter((m) =>
        metricMatches(m, ["fx-", "eur/usd", "gbp/usd", "eur/gbp", "eur/chf", "usd/jpy", "usd/chf", "usd/cnh", "usd/cad", "aud/usd", "nzd/usd"])
      )
    );
    const ordered = [
      ...FX_SERIES_ORDER.map((sid) => allFx.find((m) => m.series_id === sid)).filter(Boolean) as typeof allFx,
      ...allFx.filter((m) => !FX_SERIES_ORDER.includes(m.series_id ?? ""))
    ];
    return ordered.length
      ? ordered.slice(0, 12).map((m) => ({ ...metricRow(m), group: "", source: "" }))
      : [{
          id: "fx-placeholder",
          label: "FX strip",
          group: "",
          last: "N/A",
          change: "N/A",
          secondary: "Load Macro Snapshot",
          tone: "warning",
          source: ""
        }];
  }

  const SECTOR_SHORT: Record<string, string> = {
    "information technology": "Info Tech",
    "communication services": "Comm Svcs",
    "consumer discretionary": "Cons Disc",
    "consumer staples": "Cons Staples",
    "health care": "Health Care",
    "financials": "Financials",
    "industrials": "Industrials",
    "materials": "Materials",
    "energy": "Energy",
    "real estate": "Real Estate",
    "utilities": "Utilities"
  };

  function abbreviateSector(group: string): string {
    return SECTOR_SHORT[group.toLowerCase()] ?? group;
  }

  function simplifyYieldGroup(seriesId: string | null | undefined): string {
    if (!seriesId) return "";
    return seriesId
      .replace(/^us-/, "")
      .replace(/^eu-/, "")
      .replace(/-/g, " ")
      .toUpperCase();
  }

  function cleanYieldLabel(label: string): string {
    return label
      .replace(/^(US|EU)\s+/i, "")
      .replace(/\bFed\s+Funds\s+Rate\b/i, "Feds Funds")
      .replace(/\bTreasury\s*/gi, "")
      .replace(/\bYield\b/gi, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function buildYieldRows(data: MacroSnapshot | null): SitrepMarketRow[] {
    const curveRows = (data?.rates_policy?.curve_nodes ?? []).map((node) => ({
      id: `curve-${node.tenor}`,
      label: node.tenor,
      group: "",
      last: node.current_value == null ? "N/A" : `${node.current_value.toFixed(2)}%`,
      change: node.change_bps == null ? "N/A" : `${node.change_bps > 0 ? "+" : ""}${node.change_bps.toFixed(1)}bp`,
      secondary: node.prior_value == null ? "" : `${node.prior_value.toFixed(2)}%`,
      tone: toneFromValue(node.change_bps),
      source: ""
    }));
    const curveTenors = new Set(curveRows.map((r) => r.label.toLowerCase()));
    const policyRows = (data?.rates_policy?.policy_metrics ?? [])
      .filter((m) => {
        const clean = cleanYieldLabel(m.label).toLowerCase();
        return !curveTenors.has(clean);
      })
      .slice(0, 4)
      .map((m) => ({
        ...metricRow(m),
        label: cleanYieldLabel(m.label),
        group: "",
        secondary: m.display_value ?? "",
        source: ""
      }));
    return [...curveRows, ...policyRows].slice(0, 10);
  }

  function buildEquityRows(data: ResearchOverviewResponse | null): SitrepMarketRow[] {
    const nodes = (data?.nodes ?? [])
      .filter((node): node is ResearchOverviewNode => node.level === "instrument")
      .sort((left, right) => (right.size ?? 0) - (left.size ?? 0))
      .slice(0, 12);
    return nodes.map((node) => ({
      id: node.node_id,
      symbol: node.symbol,
      label: node.symbol ?? node.label,
      selectionLabel: node.label,
      group: abbreviateSector(node.group ?? node.sector ?? ""),
      last: node.metrics.latest_price == null ? "N/A" : formatNumber(node.metrics.latest_price, 2),
      change: formatPct(node.metrics.total_return),
      secondary: node.metrics.annual_volatility == null ? "" : formatPct(node.metrics.annual_volatility),
      tone: toneFromValue(node.metrics.total_return),
      source: ""
    }));
  }

  function selectEquityRow(row: SitrepMarketRow) {
    const symbol = row.symbol?.trim() || row.label.trim();
    if (!symbol) {
      return;
    }
    onSelectEquity?.(symbol, row.selectionLabel ?? row.label);
  }

  function isSelectedEquityRow(row: SitrepMarketRow) {
    const selected = selectedEquitySymbol?.trim().toUpperCase();
    const symbol = (row.symbol ?? row.label).trim().toUpperCase();
    return Boolean(selected && symbol && selected === symbol);
  }

  function buildIndexRows(data: ResearchOverviewResponse | null): SitrepMarketRow[] {
    const nodes = (data?.nodes ?? [])
      .filter((node): node is ResearchOverviewNode => node.level === "instrument")
      .sort((left, right) => (left.sort_rank ?? 999) - (right.sort_rank ?? 999))
      .slice(0, 12);
    return nodes.map((node) => ({
      id: node.node_id,
      label: node.label,
      group: node.group ?? "Global",
      last: node.metrics.latest_price == null ? "N/A" : formatNumber(node.metrics.latest_price, 2),
      change: formatSignedNumber(absoluteChangeFromReturn(node.metrics.latest_price, node.metrics.total_return), 2),
      changePct: formatPct(node.metrics.total_return),
      changePctTone: toneFromValue(node.metrics.total_return),
      secondary: node.symbol ?? "",
      tone: toneFromValue(node.metrics.total_return),
      source: node.source_provider
    }));
  }

  function buildCommodityRows(data: CommodityWorkspaceResponse | null): SitrepMarketRow[] {
    const overviewRows = data?.overview?.matrix_rows ?? [];
    if (overviewRows.length) {
      return overviewRows
        .filter((row) => row.latest_price != null || hasCommodityCurveSignal(row.curve_state))
        .slice(0, 16)
        .map((row) => ({
        id: row.instrument_id,
        label: formatCommodityLabel(row.name, row.symbol),
        group: humanize(row.family),
        last: row.latest_price == null ? "N/A" : formatNumber(row.latest_price, 2),
        change: formatSignedNumber(row.latest_change, 2),
        changePct: formatPct(row.latest_change_pct),
        changePctTone: toneFromValue(row.latest_change_pct ?? row.latest_change),
        secondary: formatCommodityContext(row.curve_state, row.price_source_provider, row.latest_price),
        secondaryTone: hasCommodityCurveSignal(row.curve_state) ? toneFromCommodityState(row.curve_state) : "",
        tone: toneFromValue(row.latest_change_pct ?? row.latest_change),
        source: row.price_source_provider ?? row.source_provider
      }));
    }
    return (data?.market_summaries ?? [])
      .filter((summary) => summary.latest_price != null || hasCommodityCurveSignal(summary.curve_state))
      .slice(0, 16)
      .map((summary) => ({
      id: summary.instrument.instrument_id,
      label: formatCommodityLabel(summary.instrument.name, summary.instrument.symbol),
      group: humanize(summary.instrument.family),
      last: summary.latest_price == null ? "N/A" : formatNumber(summary.latest_price, 2),
      change: formatSignedNumber(summary.latest_change, 2),
      changePct: formatPct(summary.latest_change_pct),
      changePctTone: toneFromValue(summary.latest_change_pct ?? summary.latest_change),
      secondary: formatCommodityContext(summary.curve_state, summary.source_provider, summary.latest_price),
      secondaryTone: hasCommodityCurveSignal(summary.curve_state) ? toneFromCommodityState(summary.curve_state) : "",
      tone: toneFromValue(summary.latest_change_pct ?? summary.latest_change),
      source: summary.source_provider
    }));
  }

  function formatCommodityLabel(name: string | null | undefined, symbol: string | null | undefined) {
    const cleanName = (name ?? "").trim();
    if (cleanName) {
      return cleanName;
    }
    return (symbol ?? "").trim() || "Commodity";
  }

  function hasCommodityCurveSignal(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    return normalized === "backwardation" || normalized === "contango" || normalized === "flat";
  }

  function formatCommodityContext(
    curveState: string | null | undefined,
    priceSource: string | null | undefined,
    latestPrice: number | null | undefined
  ) {
    if (hasCommodityCurveSignal(curveState)) {
      return formatCommodityState(curveState);
    }
    if (latestPrice != null) {
      return formatCommodityPriceSource(priceSource);
    }
    return formatCommodityState(curveState);
  }

  function formatCommodityPriceSource(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (normalized === "eia") {
      return "EIA spot";
    }
    if (normalized === "fred") {
      return "FRED proxy";
    }
    if (normalized === "ibkr" || normalized === "ibkr_cached") {
      return "IBKR front";
    }
    return "Price proxy";
  }

  function formatCommodityState(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (!normalized) {
      return "N/A";
    }
    if (normalized.includes("backwardation")) {
      return "Backwardation";
    }
    if (normalized.includes("contango")) {
      return "Contango";
    }
    if (normalized.includes("flat")) {
      return "Flat";
    }
    return humanize(normalized);
  }

  function toneFromCommodityState(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (normalized.includes("backwardation")) {
      return "positive";
    }
    if (normalized.includes("contango")) {
      return "negative";
    }
    if (normalized.includes("flat")) {
      return "neutral";
    }
    return "";
  }

  function buildTapeRows(
    newsData: NewsEventFeedResponse | null,
    macroData: MacroSnapshot | null,
    predictionData: PredictionMarketListResponse | null,
    commodityData: CommodityWorkspaceResponse | null
  ): TapeRow[] {
    const newsRows: TapeRow[] = (newsData?.items ?? []).slice(0, 6).map((item) => ({
      id: item.normalized_id,
      source: item.source_name,
      tone: "neutral",
      title: item.title,
      detail: item.summary ?? item.source_domain ?? item.url,
      meta: `${item.freshness_label} / ${formatDateTime(item.published_at)}`
    }));
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
    return [...newsRows, ...focusRows, ...eventRows, ...marketRows, ...commodityRows].slice(0, 14);
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
    newsData: NewsEventFeedResponse | null,
    overviewData: ResearchOverviewResponse | null,
    macroData: MacroSnapshot | null,
    commodityData: CommodityWorkspaceResponse | null,
    predictionData: PredictionMarketListResponse | null
  ) {
    return [
      ...(newsData?.warnings ?? []),
      ...(overviewData?.warnings ?? []),
      ...(macroData?.warnings ?? []),
      ...(commodityData?.warnings ?? []),
      ...(commodityData?.coverage.caveats ?? []),
      ...(predictionData?.warnings ?? [])
    ].slice(0, 6);
  }

  $: equityRows = buildEquityRows(overview);
  $: indexRows = buildIndexRows(indicesOverview);
  $: fxRows = buildFxRows(macro);
  $: yieldRows = buildYieldRows(macro);
  $: commodityRows = buildCommodityRows(commodities);
  $: tapeRows = buildTapeRows(news, macro, prediction, commodities);
  $: changedRows = buildWhatChangedRows(macro, overview, commodities);
  $: warnings = warningRows(news, overview, macro, commodities, prediction);
  $: asOf = news?.retrieved_at ?? macro?.retrieved_at ?? overview?.retrieved_at ?? commodities?.retrieved_at ?? null;
  $: pricedRatio = overview?.coverage.coverage_ratio ?? null;
  $: highDivergences = (macro?.top_divergences ?? []).filter((item) => item.label === "high").length;
  $: staleMarkets = (prediction?.venues ?? []).reduce((total, venue) => total + venue.stale_markets + venue.broken_markets, 0);
  $: newsStatus = news
    ? `${news.source_provider.toUpperCase()} / ${news.items.length} ITEMS / ${news.freshness_label.toUpperCase()}`
    : "NOT LOADED";
  $: providerMode = system?.mock_mode ? "MOCK" : system?.connection.connected ? system.market_data_mode.toUpperCase() : "OFFLINE";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-identity">
      <p class="eyebrow">SITREP</p>
      <h2>Situation Report</h2>
    </div>
    <div class="equity-strip" aria-label="US equity tape">
      {#if equityRows.length}
        <div class="strip-track">
          {#each [...equityRows, ...equityRows] as row}
            <button
              type="button"
              class:selected={isSelectedEquityRow(row)}
              class="strip-item"
              on:click={() => selectEquityRow(row)}
              aria-label={`Select ${row.label} as selected equity`}
              aria-pressed={isSelectedEquityRow(row)}
              title={`Select ${row.label}`}
            >
              <strong>{row.label}</strong>
              <em>{row.last}</em>
              <b class={row.tone}>{row.change}</b>
            </button>
          {/each}
        </div>
      {:else}
        <span class="strip-empty">US EQUITY TAPE UNAVAILABLE</span>
      {/if}
    </div>
    <div class="status-line">
      <span class:warning={loading}>{loading ? "REFRESHING" : "LIVE"}</span>
      <span>{providerMode}</span>
      {#if warnings.length > 0}<span class="warning">{warnings.length} WARN</span>{/if}
      <span>{formatDateTime(asOf)}</span>
    </div>
  </article>

  <div class="workspace-grid">
    <div class="primary-column">
      <div class="market-grid">
        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Worldwide Indices</span>
              <small>{indicesOverview?.universe_label ?? "Global Indices"}</small>
            </div>
            <button type="button" class="reload-button" on:click={refreshIndices} disabled={refreshing.indices || isCoolingDown("indices")} aria-label={refreshTitle("indices")} title={refreshTitle("indices")}>
              <span class:spinning={refreshing.indices} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={indexRows} profile="indices" hideSource hideContext showPctChange changeLabel="CHG" emptyLabel="No index overview loaded." />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>FX Pairs</span>
              <small>{macro?.source_provider ?? "Macro / IBKR"}</small>
            </div>
            <button type="button" class="reload-button" on:click={refreshFx} disabled={refreshing.fx || isCoolingDown("fx")} aria-label={refreshTitle("fx")} title={refreshTitle("fx")}>
              <span class:spinning={refreshing.fx} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={fxRows} profile="fx" hideGroup hideSource hideContext showPctChange changeLabel="CHG" emptyLabel="No FX strip loaded." />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Rates</span>
              <small>{macro?.rates_policy?.source_provider ?? "Treasury / FRED"}</small>
            </div>
            <button type="button" class="reload-button" on:click={refreshRates} disabled={refreshing.rates || isCoolingDown("rates")} aria-label={refreshTitle("rates")} title={refreshTitle("rates")}>
              <span class:spinning={refreshing.rates} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={yieldRows} profile="yields" hideGroup hideSource contextLabel="Prior" emptyLabel="No rates policy payload loaded." />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Commodities</span>
              <small>{commodities?.coverage.coverage_status ?? "not loaded"}</small>
            </div>
            <button type="button" class="reload-button" on:click={refreshCommodities} disabled={refreshing.commodities || isCoolingDown("commodities")} aria-label={refreshTitle("commodities")} title={refreshTitle("commodities")}>
              <span class:spinning={refreshing.commodities} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={commodityRows} profile="commodities" hideSource hideContext showPctChange changeLabel="CHG" emptyLabel="No commodities workspace loaded." />
        </article>
      </div>

      <article class="panel tape-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Triage</p><h3>What Changed</h3></div>
        </div>
        <div class="tape-list">
          {#if changedRows.length}
            {#each changedRows as row (row.id)}
              <div use:flashOnMount={row.tone === 'positive' ? 'up' : row.tone === 'negative' ? 'down' : 'neutral'} class="tape-row {row.tone}">
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

    </div>

    <aside class="support-column">
      <article class="panel media-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Live Media</p><h3>Bloomberg TV</h3></div>
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
      </article>

      <article class="panel table-panel news-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Market News</span>
            <small>{news?.freshness_label ?? "not loaded"}</small>
          </div>
          <button type="button" class="reload-button" on:click={refreshNews} disabled={refreshing.news || isCoolingDown("news")} aria-label={refreshTitle("news")} title={refreshTitle("news")}>
            <span class:spinning={refreshing.news} aria-hidden="true">↻</span>
          </button>
        </div>
        <div class="news-wrap">
          {#if news?.items?.length}
            {#each news.items as item (item.normalized_id)}
              <div use:flashOnMount={'neutral'} class="news-row">
                <span class="news-time">{formatTime(item.published_at)}</span>
                <p class="news-title">{item.title}</p>
                <a class="news-source" href={item.url} target="_blank" rel="noreferrer">{abbreviateSource(item.source_name)}</a>
              </div>
            {/each}
          {:else}
            <p class="news-empty">NO NEWS LOADED.</p>
          {/if}
        </div>
      </article>

      <article class="panel provider-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Coverage</p><h3>Provider Status</h3></div>
        </div>
        <div class="need-list">
          <div><strong>News</strong><span class:warning={!news || news.items.length === 0}>{newsStatus}</span></div>
          <div><strong>TV</strong><span class="warning">EMBED ONLY</span></div>
          <div><strong>Listed Markets</strong><span>{overview?.history_source_label ?? "Research Overview policy"}</span></div>
          <div><strong>FX / Rates</strong><span>Macro / FRED / IBKR</span></div>
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

  .table-panel {
    padding: 0;
    overflow: hidden;
    gap: 0;
  }

  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    min-height: 26px;
    flex-shrink: 0;
  }

  .table-title {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
    min-width: 0;
  }

  .table-title span {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
    white-space: nowrap;
  }

  .table-title small {
    color: var(--text-2);
    font-size: 0.64rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .reload-button {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 1px solid var(--panel-strong);
    border-radius: 0;
    background: transparent;
    color: var(--text-2);
    font-size: 0.78rem;
    line-height: 1;
    cursor: pointer;
    flex-shrink: 0;
  }

  .reload-button span {
    display: block;
    transform-origin: 50% 50%;
  }

  .reload-button .spinning {
    animation: reload-spin 0.8s linear infinite;
  }

  .reload-button:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .reload-button:disabled {
    cursor: default;
    opacity: 0.55;
  }

  @keyframes reload-spin {
    to {
      transform: rotate(360deg);
    }
  }

  .header-panel {
    display: flex;
    flex-direction: row;
    align-items: stretch;
    padding: 0;
    gap: 0;
    min-width: 0;
    overflow: hidden;
  }

  .header-identity {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.52rem 0.85rem;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .title-line {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
    min-width: 0;
  }

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

  .title-line .eyebrow {
    margin: 0;
    white-space: nowrap;
  }

  .equity-strip {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    border-left: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
    position: relative;
  }

  .strip-track {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    display: flex;
    align-items: center;
    width: max-content;
    animation: strip-scroll 42s linear infinite;
  }

  .strip-item {
    appearance: none;
    background: transparent;
    border: 0;
    display: inline-flex;
    align-items: baseline;
    gap: 0.38rem;
    padding: 0.42rem 0.72rem;
    border-right: 1px solid var(--divider);
    white-space: nowrap;
    cursor: pointer;
    font: inherit;
    color: inherit;
  }

  .strip-item:hover,
  .strip-item:focus-visible {
    background: var(--bg-1);
  }

  .strip-item:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .strip-item.selected {
    background: color-mix(in srgb, var(--accent) 16%, transparent);
  }

  .strip-item strong,
  .strip-item em,
  .strip-item b {
    font-style: normal;
    font-size: 0.72rem;
    line-height: 1;
  }

  .strip-item strong {
    color: var(--text-0);
  }

  .strip-item em {
    color: var(--text-1);
  }

  .strip-empty {
    display: block;
    padding: 0.5rem 0.65rem;
    color: var(--text-2);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
  }

  @keyframes strip-scroll {
    from {
      transform: translateX(0);
    }
    to {
      transform: translateX(-50%);
    }
  }

  .status-line {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    flex-shrink: 0;
    gap: 0;
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
  }

  .status-line span {
    padding: 0 0.6rem;
    border-left: 1px solid var(--divider);
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(29rem, 0.48fr);
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

  .tape-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
  }

  .panel-head small,
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

  .tape-row {
    display: grid;
    grid-template-columns: 5.8rem minmax(0, 0.9fr) minmax(0, 1.7fr) minmax(5.5rem, 0.45fr);
    gap: 0.5rem;
    align-items: baseline;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--divider);
    min-width: 0;
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

  .news-wrap {
    overflow: auto;
    max-height: 28rem;
  }

  .news-row {
    display: grid;
    grid-template-columns: 3rem minmax(0, 1fr) minmax(4.5rem, max-content);
    gap: 0 0.6rem;
    align-items: start;
    padding: 0.42rem 0.75rem;
    border-bottom: 1px solid var(--divider);
  }

  .news-time {
    color: var(--accent);
    font-size: 0.7rem;
    padding-top: 0.12rem;
    white-space: nowrap;
  }

  .news-title {
    color: var(--text-0);
    font-size: 0.74rem;
    line-height: 1.35;
    margin: 0;
  }

  .news-source {
    color: var(--text-2);
    font-size: 0.68rem;
    text-decoration: none;
    text-align: right;
    white-space: nowrap;
    padding-top: 0.12rem;
  }

  .news-source:hover {
    color: var(--accent);
  }

  .news-empty {
    padding: 0.75rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
    margin: 0;
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
    .panel-head,
    .support-column {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      justify-content: stretch;
    }

    .title-line {
      flex-wrap: wrap;
    }

    .status-line {
      justify-content: flex-start;
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
