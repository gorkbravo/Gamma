<script lang="ts">
  import { onMount } from "svelte";
  import type Hls from "hls.js";
  import { flashOnMount } from "../lib/flash";
  import SitrepMarketTable from "../components/SitrepMarketTable.svelte";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import Tooltip from "../components/Tooltip.svelte";
  import { toProvenanceBadge } from "../lib/provenance";
  import type {
    CommodityPriceBasis,
    CommodityWorkspaceResponse,
    MacroMetric,
    MacroSnapshot,
    NewsEventEntity,
    NewsEventFeedResponse,
    NewsEventItem,
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
  import {
    formatNewsReliabilityLabel,
    formatSitrepSectionAge,
    formatSitrepWindowLabel,
    isSitrepFollowUpSaved,
    oldestSitrepSection,
    resolveSitrepMarketHandoff,
    resolveSitrepNewsEntityHandoff,
    resolveSitrepTapeHandoff,
    type SitrepFollowUp,
    type SitrepFollowUpStatus,
    type SitrepHandoffRequest,
    type SitrepMarketHandoffProfile,
    type SitrepTapeHandoffRow,
    type SitrepWorkspaceMeta,
  } from "../lib/view-models/sitrep";

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
  export let onLoadWorkspace: (() => Promise<unknown> | void) | null = null;
  export let selectedEquitySymbol: string | null = null;
  export let onSelectEquity: ((symbol: string, label?: string | null) => void) | null = null;
  export let onOpenHandoff: ((handoff: SitrepHandoffRequest) => Promise<unknown> | void) | null = null;
  export let workspaceMeta: SitrepWorkspaceMeta | null = null;
  export let followUps: SitrepFollowUp[] = [];
  export let onLoadFollowUps: (() => Promise<unknown> | void) | null = null;
  export let onToggleFollowUp: ((row: SitrepTapeHandoffRow) => Promise<unknown> | void) | null = null;
  export let onUpdateFollowUp:
    | ((id: string, patch: { note?: string; status?: SitrepFollowUpStatus }) => Promise<unknown> | void)
    | null = null;
  export let onDismissFollowUp: ((id: string) => Promise<unknown> | void) | null = null;

  const bloombergStreamUrl = "https://www.bloomberg.com/media-manifest/streams/phoenix-us.m3u8";
  const bloombergWatchUrl = "https://www.bloomberg.com/live";
  const bloombergYouTubeUrl = "https://www.youtube.com/channel/UCIALMKvObZNtJ6AmdCLP7Lg/live";

  type BloombergPlaybackStatus = "loading" | "ready" | "unsupported" | "error";
  let bloombergVideo: HTMLVideoElement | null = null;
  let bloombergPlaybackStatus: BloombergPlaybackStatus = "loading";
  let bloombergPlaybackMessage = "HLS stream initializing";

  type TapeRow = {
    id: string;
    source: string;
    tone: "positive" | "negative" | "warning" | "neutral";
    title: string;
    detail: string;
    meta: string;
    handoff?: SitrepHandoffRequest | null;
  };

  type SitrepMarketRow = {
    id: string;
    symbol?: string | null;
    proxySymbol?: string | null;
    proxyLabel?: string | null;
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
    timeframe?: string | null;
    region?: string | null;
    theme?: string | null;
  };

  type RefreshKey = "indices" | "fx" | "rates" | "commodities" | "news";

  /** Detail longer than this is clamped to two lines and moved into a tooltip. */
  const TAPE_DETAIL_CLAMP = 110;

  /** Provider Status source names past this width ellipsize; the tooltip carries the rest. */
  const STATUS_SOURCE_CLAMP = 14;

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
    const missingSection =
      !overview || !indicesOverview || !macro || !news || !commodities || !prediction;
    if (onLoadWorkspace && missingSection) {
      void onLoadWorkspace();
      return;
    }
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

  onMount(() => {
    let cancelled = false;
    let hlsPlayer: Hls | null = null;
    const video = bloombergVideo;

    if (!video) {
      bloombergPlaybackStatus = "unsupported";
      bloombergPlaybackMessage = "Video element unavailable";
      return;
    }

    const markReady = () => {
      bloombergPlaybackStatus = "ready";
      bloombergPlaybackMessage = "Bloomberg TV live";
    };
    const markError = () => {
      bloombergPlaybackStatus = "error";
      bloombergPlaybackMessage = "Open Bloomberg Live externally";
    };

    video.addEventListener("loadedmetadata", markReady);
    video.addEventListener("canplay", markReady);
    video.addEventListener("error", markError);

    void (async () => {
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = bloombergStreamUrl;
        video.load();
        return;
      }

      try {
        const { default: Hls } = await import("hls.js");
        if (cancelled) {
          return;
        }
        if (!Hls.isSupported()) {
          bloombergPlaybackStatus = "unsupported";
          bloombergPlaybackMessage = "HLS is not supported in this webview";
          return;
        }

        hlsPlayer = new Hls({
          enableWorker: true,
          lowLatencyMode: true
        });
        hlsPlayer.loadSource(bloombergStreamUrl);
        hlsPlayer.attachMedia(video);
        hlsPlayer.on(Hls.Events.MANIFEST_PARSED, markReady);
        hlsPlayer.on(Hls.Events.ERROR, (_event, data) => {
          if (data.fatal) {
            markError();
            hlsPlayer?.destroy();
            hlsPlayer = null;
          }
        });
      } catch {
        bloombergPlaybackStatus = "unsupported";
        bloombergPlaybackMessage = "HLS player unavailable";
      }
    })();

    return () => {
      cancelled = true;
      video.removeEventListener("loadedmetadata", markReady);
      video.removeEventListener("canplay", markReady);
      video.removeEventListener("error", markError);
      hlsPlayer?.destroy();
    };
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

  function formatDateTimeWithZone(value: string | null | undefined) {
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
      minute: "2-digit",
      timeZoneName: "short"
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

  type NewsEntityChip = { entity: NewsEventEntity; handoff: SitrepHandoffRequest };

  function newsEntityChips(item: NewsEventItem): NewsEntityChip[] {
    const seen = new Set<string>();
    const chips: NewsEntityChip[] = [];
    for (const entity of item.detected_entities ?? []) {
      const handoff = resolveSitrepNewsEntityHandoff(entity);
      const symbol = (entity.symbol ?? "").trim().toUpperCase();
      if (!handoff || !symbol || seen.has(symbol)) {
        continue;
      }
      seen.add(symbol);
      chips.push({ entity, handoff });
      if (chips.length >= 4) {
        break;
      }
    }
    return chips;
  }

  function openNewsEntity(chip: NewsEntityChip) {
    const symbol = chip.handoff.symbol ?? chip.entity.symbol ?? "";
    if (symbol) {
      onSelectEquity?.(symbol, chip.entity.label);
    }
    void onOpenHandoff?.(chip.handoff);
  }

  const NEWS_RELIABILITY_DETAIL: Record<string, string> = {
    OFFICIAL: "Official source",
    OUTLET: "Major outlet",
    AGGR: "Aggregator",
    SAMPLE: "Sample feed"
  };

  /**
   * Per-item provenance used to be rendered inline on every headline, where the
   * RSS feed stamps every row identically ("DELAYED / rss / OUTLET") and the
   * column carried no signal at all. It lives on the source link instead.
   */
  function newsSourceDetail(item: NewsEventItem): string {
    const reliability = formatNewsReliabilityLabel(item.source_reliability);
    const lines = [
      NEWS_RELIABILITY_DETAIL[reliability] ?? "Reliability unrated",
      `Published ${formatDateTimeWithZone(item.published_at)}`,
      `Retrieved ${formatDateTimeWithZone(item.retrieved_at)}`
    ];
    if (item.warnings?.length) {
      lines.push(...item.warnings.slice(0, 3));
    }
    return lines.join("\n");
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

  function pluralize(count: number, noun: string) {
    return `${count} ${noun}${count === 1 ? "" : "s"}`;
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

  const INDEX_PROXY_BY_SYMBOL: Record<string, { symbol: string; label: string }> = {
    "^GSPC": { symbol: "SPY", label: "S&P 500 ETF proxy" },
    "^DJI": { symbol: "DIA", label: "DJIA ETF proxy" },
    "^IXIC": { symbol: "QQQ", label: "Nasdaq 100 ETF proxy" },
    "^RUT": { symbol: "IWM", label: "Russell 2000 ETF proxy" },
    "^GSPTSE": { symbol: "EWC", label: "Canada ETF proxy" },
    "^STOXX50E": { symbol: "FEZ", label: "Euro Stoxx 50 ETF proxy" },
    "^FTSE": { symbol: "EWU", label: "UK ETF proxy" },
    "^GDAXI": { symbol: "EWG", label: "Germany ETF proxy" },
    "^FCHI": { symbol: "EWQ", label: "France ETF proxy" },
    "^IBEX": { symbol: "EWP", label: "Spain ETF proxy" },
    "^N225": { symbol: "EWJ", label: "Japan ETF proxy" },
    "^HSI": { symbol: "EWH", label: "Hong Kong ETF proxy" }
  };

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
      ? ordered.slice(0, 12).map((m) => ({
          ...metricRow(m),
          group: "",
          source: m.source_provider,
          timeframe: data?.timeframe ?? "3M",
          region: data?.region ?? "US",
          theme: data?.theme ?? "all"
        }))
      : [{
          id: "fx-placeholder",
          label: "FX unavailable",
          group: "",
          last: "N/A",
          change: "N/A",
          secondary: data ? "Macro loaded / no FX rows" : "Macro not loaded",
          tone: "warning",
          source: data?.source_provider ?? "macro"
        }];
  }

  function formatFxSourceMix(rows: SitrepMarketRow[], data: MacroSnapshot | null) {
    if (!data) {
      return "Macro not loaded";
    }
    const providers = [...new Set(rows.map((row) => row.source).filter(Boolean))];
    if (!providers.length || rows.every((row) => row.id === "fx-placeholder")) {
      return `${data.source_provider || "Macro"} / FX unavailable`;
    }
    return providers.length === 1 ? providers[0].toUpperCase() : `Mixed: ${providers.map((row) => row.toUpperCase()).join(" + ")}`;
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
    return [...curveRows, ...policyRows].slice(0, 10).map((row) => ({
      ...row,
      timeframe: data?.timeframe ?? "3M",
      region: data?.region ?? "US",
      theme: data?.theme ?? "all"
    }));
  }

  function buildEquityRows(data: ResearchOverviewResponse | null): SitrepMarketRow[] {
    const nodes = (data?.nodes ?? [])
      .filter((node): node is ResearchOverviewNode => node.level === "instrument")
      .sort((left, right) => (right.size ?? 0) - (left.size ?? 0))
      .slice(0, 12);
    return nodes.map((node) => {
      const latestDailyReturn = node.metrics.latest_daily_return ?? node.metrics.total_return;
      return {
        id: node.node_id,
        symbol: node.symbol,
        label: node.symbol ?? node.label,
        selectionLabel: node.label,
        group: abbreviateSector(node.group ?? node.sector ?? ""),
        last: node.metrics.latest_price == null ? "N/A" : formatNumber(node.metrics.latest_price, 2),
        change: formatPct(latestDailyReturn),
        secondary: node.metrics.annual_volatility == null ? "" : formatPct(node.metrics.annual_volatility),
        tone: toneFromValue(latestDailyReturn),
        source: "",
        timeframe: "1Y"
      };
    });
  }

  function selectEquityRow(row: SitrepMarketRow) {
    const symbol = row.symbol?.trim() || row.label.trim();
    if (!symbol) {
      return;
    }
    onSelectEquity?.(symbol, row.selectionLabel ?? row.label);
  }

  function openEquityRow(row: SitrepMarketRow) {
    selectEquityRow(row);
    openMarketRow("equities", row);
  }

  function openMarketRow(profile: SitrepMarketHandoffProfile, row: SitrepMarketRow) {
    const handoff = resolveSitrepMarketHandoff(profile, row);
    if (handoff) {
      void onOpenHandoff?.(handoff);
    }
  }

  function openTapeRow(row: TapeRow) {
    const handoff = resolveSitrepTapeHandoff(row);
    if (handoff) {
      void onOpenHandoff?.(handoff);
    }
  }

  function hasTapeHandoff(row: TapeRow) {
    return Boolean(resolveSitrepTapeHandoff(row));
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
    return nodes.map((node) => {
      const latestDailyReturn = node.metrics.latest_daily_return;
      const proxy = indexProxyForNode(node);
      return {
        id: node.node_id,
        symbol: node.symbol,
        proxySymbol: proxy?.symbol ?? null,
        proxyLabel: proxy?.label ?? null,
        label: node.label,
        group: node.group ?? "Global",
        last: node.metrics.latest_price == null ? "N/A" : formatNumber(node.metrics.latest_price, 2),
        change: formatSignedNumber(absoluteChangeFromReturn(node.metrics.latest_price, latestDailyReturn), 2),
        changePct: formatPct(latestDailyReturn),
        changePctTone: toneFromValue(latestDailyReturn),
        secondary: proxy ? `${proxy.symbol} / ${shortDate(node.metrics.latest_daily_return_at)}` : shortDate(node.metrics.latest_daily_return_at),
        tone: toneFromValue(latestDailyReturn),
        source: node.source_provider,
        timeframe: "1Y"
      };
    });
  }

  function indexProxyForNode(node: ResearchOverviewNode) {
    const symbol = (node.symbol ?? "").trim().toUpperCase();
    return INDEX_PROXY_BY_SYMBOL[symbol] ?? null;
  }

  /** Newest close represented on the board — the "as of" behind every index row. */
  function latestIndexCloseAt(data: ResearchOverviewResponse | null) {
    return (
      (data?.nodes ?? [])
        .filter((node) => node.level === "instrument")
        .map((node) => node.metrics.latest_daily_return_at)
        .filter((value): value is string => Boolean(value))
        .sort()
        .at(-1) ?? null
    );
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
        secondary: formatCommodityBasis(row.quote_basis, row.curve_state, row.price_source_provider, row.latest_price),
        secondaryTone: hasCommodityCurveSignal(row.curve_state) ? toneFromCommodityState(row.curve_state) : "",
        tone: toneFromValue(row.latest_change_pct ?? row.latest_change),
        source: row.quote_basis?.provider ?? row.price_source_provider ?? row.source_provider
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
      secondary: formatCommodityBasis(summary.quote_basis, summary.curve_state, summary.source_provider, summary.latest_price),
      secondaryTone: hasCommodityCurveSignal(summary.curve_state) ? toneFromCommodityState(summary.curve_state) : "",
      tone: toneFromValue(summary.latest_change_pct ?? summary.latest_change),
      source: summary.quote_basis?.provider ?? summary.source_provider
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

  function formatCommodityBasis(
    basis: CommodityPriceBasis | null | undefined,
    curveState: string | null | undefined,
    priceSource: string | null | undefined,
    latestPrice: number | null | undefined
  ) {
    if (basis) {
      const provider = formatCommodityProvider(basis.provider);
      const reference = compactCommodityReference(basis);
      return `${provider} ${reference}`.trim();
    }
    return formatCommodityContext(curveState, priceSource, latestPrice);
  }

  function compactCommodityReference(basis: CommodityPriceBasis) {
    const contractSymbol = normalizeCommoditySymbol(basis.contract_symbol);
    if (contractSymbol) return contractSymbol;

    const providerSymbol = normalizeCommoditySymbol(basis.provider_symbol);
    if (providerSymbol) return providerSymbol;

    const basisType = (basis.basis_type ?? "").trim().toLowerCase();
    if (basisType.includes("future")) return "Fut";
    if (basisType.includes("spot")) return "Spot";
    if (basisType.includes("fred")) return "FRED";
    if (basisType.includes("eia")) return "EIA";
    if (basisType.includes("sample")) return "Sample";
    if (basisType.includes("continuous")) return "Cont";
    if (basisType.includes("curve")) return "Curve";
    return "Ref";
  }

  function normalizeCommoditySymbol(value: string | null | undefined) {
    return (value ?? "").trim().replace(/\s+/g, "").toUpperCase();
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

  function formatCommodityProviderMix(data: CommodityWorkspaceResponse | null) {
    if (!data) return "not loaded";
    const providers = new Set<string>();
    for (const row of data.price_reconciliations ?? []) {
      if (row.headline?.provider) providers.add(formatCommodityProvider(row.headline.provider));
      for (const observation of row.observations ?? []) {
        if (observation.provider) providers.add(formatCommodityProvider(observation.provider));
      }
    }
    if (!providers.size) {
      providers.add(formatCommodityProvider(data.coverage.source_provider || data.coverage.provider_id));
    }
    const ordered = [...providers].filter(Boolean).sort();
    return ordered.length <= 1 ? ordered[0] ?? "not loaded" : `Mixed: ${ordered.join(" + ")}`;
  }

  function formatCommodityProvider(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (normalized === "ibkr" || normalized === "ibkr_cached") return "IBKR";
    if (normalized === "fred") return "FRED";
    if (normalized === "eia") return "EIA";
    if (normalized === "sample_data") return "Sample";
    if (normalized === "gamma") return "Gamma";
    return (value ?? "").trim().toUpperCase() || "Provider N/A";
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

  function buildEventRows(
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
      meta: item.source_provider,
      handoff: {
        targetTab: "macro",
        targetMode: item.mode_target ?? "snapshot",
        timeframe: macroData?.timeframe ?? "3M",
        region: macroData?.region ?? "US",
        theme: item.target_theme ?? macroData?.theme ?? "all"
      }
    }));
    const eventRows: TapeRow[] = (macroData?.upcoming_events ?? []).slice(0, 4).map((event) => ({
      id: event.event_id,
      source: "Event",
      tone: event.importance === "high" ? "warning" : "neutral",
      title: event.title,
      detail: `${humanize(event.category)} / ${event.region}`,
      meta: event.relative_label ?? shortDate(event.scheduled_at),
      handoff: {
        targetTab: "macro",
        targetMode: "events_regimes",
        timeframe: macroData?.timeframe ?? "3M",
        region: event.region || macroData?.region || "US",
        theme: macroData?.theme ?? "all"
      }
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
      meta: market.freshness?.status ?? market.status,
      handoff: {
        targetTab: "prediction_markets",
        marketId: market.market_id
      }
    }));
    const commodityRows: TapeRow[] = (commodityData?.events ?? []).slice(0, 3).map((event) => ({
      id: event.event_id,
      source: "Commodity",
      tone: event.importance === "high" ? "warning" : "neutral",
      title: event.title,
      detail: event.summary ?? humanize(event.category),
      meta: event.relative_label ?? shortDate(event.scheduled_at),
      handoff: {
        targetTab: "commodities",
        targetMode: "events_cross_domain",
        commodityId: event.linked_instrument_ids?.[0] ?? null
      }
    }));
    return [...focusRows, ...eventRows, ...marketRows, ...commodityRows].slice(0, 12);
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
      meta: `score ${item.score.toFixed(1)} / ${item.label}`,
      handoff: {
        targetTab: "macro",
        targetMode: "cross_asset",
        timeframe: macroData?.timeframe ?? "3M",
        region: macroData?.region ?? "US",
        theme: item.theme ?? macroData?.theme ?? "all"
      }
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
        meta: row.source,
        handoff: resolveSitrepMarketHandoff("commodities", row)
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
        meta: overviewData?.freshness_label ?? "research overview",
        handoff: {
          targetTab: "equity_research",
          targetMode: "scope_analysis",
          symbol: item.symbol ?? null,
          label: item.label,
          timeframe: "1Y"
        }
      }));
    return [...divergenceRows, ...equityRows, ...movers].slice(0, 10);
  }

  /**
   * Groups actionable warnings by the Provider Status domain that produced
   * them, so each row can own its own incidents instead of the panel carrying
   * one undifferentiated bullet list.
   */
  function sitrepWarningsByDomain(
    indicesData: ResearchOverviewResponse | null,
    overviewData: ResearchOverviewResponse | null,
    macroData: MacroSnapshot | null,
    commodityData: CommodityWorkspaceResponse | null,
    predictionData: PredictionMarketListResponse | null,
    newsData: NewsEventFeedResponse | null,
    meta: SitrepWorkspaceMeta | null
  ): Record<string, string[]> {
    const commodityBasisWarnings = (commodityData?.price_reconciliations ?? []).flatMap((row) => row.warnings ?? []);
    const byDomain: Record<string, string[]> = {
      workspace: meta?.section_warnings ?? [],
      indices: indicesData?.warnings ?? [],
      equities: overviewData?.warnings ?? [],
      macro: macroData?.warnings ?? [],
      commodities: [
        ...commodityBasisWarnings,
        ...(commodityData?.warnings ?? []),
        ...(commodityData?.coverage.caveats ?? [])
      ],
      prediction: predictionData?.warnings ?? [],
      news: newsData?.warnings ?? []
    };
    const grouped: Record<string, string[]> = {};
    for (const [domain, values] of Object.entries(byDomain)) {
      const actionable = collapseSitrepWarnings(values.filter(isActionableSitrepWarning));
      if (actionable.length) {
        grouped[domain] = actionable;
      }
    }
    return grouped;
  }

  const SERIES_FAILURE_PATTERN = /^(.+?) series (\S+) failed: (.+?)\.?$/i;

  /** Folds repeated per-series fetch failures into one line and drops duplicates. */
  function collapseSitrepWarnings(values: string[]): string[] {
    const seen = new Set<string>();
    const order: string[] = [];
    const groups = new Map<string, { provider: string; reason: string; ids: string[] }>();

    for (const raw of values) {
      const value = raw.trim();
      if (!value) continue;
      const match = SERIES_FAILURE_PATTERN.exec(value);
      if (!match) {
        if (seen.has(value)) continue;
        seen.add(value);
        order.push(value);
        continue;
      }
      const [, provider, seriesId, reason] = match;
      const key = ` series:${provider.toLowerCase()}:${reason.toLowerCase()}`;
      const group = groups.get(key);
      if (group) {
        if (!group.ids.includes(seriesId)) group.ids.push(seriesId);
        continue;
      }
      groups.set(key, { provider, reason, ids: [seriesId] });
      order.push(key);
    }

    return order.map((entry) => {
      const group = groups.get(entry);
      if (!group) return entry;
      return group.ids.length === 1
        ? `${group.provider} series ${group.ids[0]} failed: ${group.reason}.`
        : `${group.provider}: ${group.ids.length} series failed (${group.ids.join(", ")}) — ${group.reason}.`;
    });
  }

  onMount(() => {
    void onLoadFollowUps?.();
  });

  function toggleFollowUp(row: TapeRow) {
    void onToggleFollowUp?.(row);
  }

  function dismissFollowUp(id: string) {
    if (followUpNoteDraftId === id) {
      cancelFollowUpNote();
    }
    void onDismissFollowUp?.(id);
  }

  function openFollowUp(item: SitrepFollowUp) {
    if (item.handoff) {
      void onOpenHandoff?.(item.handoff);
    }
  }

  let followUpNoteDraftId: string | null = null;
  let followUpNoteDraft = "";

  function beginFollowUpNote(item: SitrepFollowUp) {
    followUpNoteDraftId = item.id;
    followUpNoteDraft = item.note;
  }

  function cancelFollowUpNote() {
    followUpNoteDraftId = null;
    followUpNoteDraft = "";
  }

  async function saveFollowUpNote(item: SitrepFollowUp) {
    await onUpdateFollowUp?.(item.id, { note: followUpNoteDraft.trim() });
    cancelFollowUpNote();
  }

  function toggleFollowUpResolved(item: SitrepFollowUp) {
    void onUpdateFollowUp?.(item.id, {
      status: item.status === "resolved" ? "open" : "resolved",
    });
  }

  $: openFollowUpCount = followUps.filter((item) => item.status !== "resolved").length;
  $: resolvedFollowUpCount = followUps.length - openFollowUpCount;

  type ProviderStatusRow = {
    id: string;
    domain: string;
    source: string;
    freshness: string;
    asOf: string;
    age: string;
    warn: boolean;
    warnings: string[];
  };

  function providerStatusRow(
    id: string,
    domain: string,
    source: string | null | undefined,
    freshness: string | null | undefined,
    asOf: string | null | undefined,
    warn = false,
    warnings: string[] = []
  ): ProviderStatusRow {
    return {
      id,
      domain,
      source: (source ?? "").trim() || "N/A",
      freshness: compactFreshnessLabel(freshness),
      asOf: asOf ? formatDateTimeWithZone(asOf) : "N/A",
      age: formatSitrepSectionAge(asOf),
      warn: warn || warnings.length > 0,
      warnings
    };
  }

  function buildProviderStatusRows(
    indicesData: ResearchOverviewResponse | null,
    overviewData: ResearchOverviewResponse | null,
    macroData: MacroSnapshot | null,
    commodityData: CommodityWorkspaceResponse | null,
    predictionData: PredictionMarketListResponse | null,
    newsData: NewsEventFeedResponse | null,
    windowLabel: string,
    warningsByDomain: Record<string, string[]>
  ): ProviderStatusRow[] {
    const incidents = (domain: string) => warningsByDomain[domain] ?? [];
    const rows: ProviderStatusRow[] = [];
    rows.push(
      indicesData
        ? providerStatusRow("indices", "Indices", indicesData.source_provider, indicesData.freshness_label, indicesData.retrieved_at, false, incidents("indices"))
        : providerStatusRow("indices", "Indices", null, "not loaded", null, true)
    );
    rows.push(
      overviewData
        ? providerStatusRow("equities", "Equities", overviewData.source_provider, overviewData.freshness_label, overviewData.retrieved_at, false, incidents("equities"))
        : providerStatusRow("equities", "Equities", null, "not loaded", null, true)
    );
    rows.push(
      macroData
        ? providerStatusRow("macro", "FX / Rates", macroData.source_provider, `${windowLabel} window`, macroData.retrieved_at, false, incidents("macro"))
        : providerStatusRow("macro", "FX / Rates", null, "not loaded", null, true)
    );
    if (commodityData) {
      const coverage = commodityData.coverage;
      rows.push(
        providerStatusRow(
          "commodities",
          "Commodities",
          shortProviderLabel(coverage.provider_label || coverage.source_provider),
          coverage.freshness_label,
          coverage.as_of ?? commodityData.retrieved_at,
          coverage.coverage_status === "unavailable",
          incidents("commodities")
        )
      );
    } else {
      rows.push(providerStatusRow("commodities", "Commodities", null, "not loaded", null, true));
    }
    if (predictionData) {
      const venues = predictionData.venues ?? [];
      const stale = venues.reduce((total, venue) => total + venue.stale_markets + venue.broken_markets, 0);
      const latest = venues
        .map((venue) => venue.retrieved_at)
        .filter((value): value is string => Boolean(value))
        .sort()
        .at(-1);
      rows.push(
        providerStatusRow(
          "prediction",
          "Predictions",
          venues.map((venue) => venue.venue).join(" + ") || "prediction markets",
          stale > 0 ? `${stale} stale` : "open",
          latest ?? null,
          stale > 0,
          incidents("prediction")
        )
      );
    } else {
      rows.push(providerStatusRow("prediction", "Predictions", null, "not loaded", null, true));
    }
    rows.push(
      newsData
        ? providerStatusRow(
            "news",
            "News",
            newsData.source_provider,
            newsData.freshness_label,
            newsData.retrieved_at,
            newsData.items.length === 0,
            incidents("news")
          )
        : providerStatusRow("news", "News", null, "not loaded", null, true)
    );
    return rows;
  }

  /** Freshness vocabulary varies per provider; the status column has one line to spend. */
  function compactFreshnessLabel(value: string | null | undefined) {
    const normalized = (value ?? "").trim();
    if (!normalized) return "N/A";
    return normalized
      .replace(/^official[_\s-]+/i, "")
      .replace(/[_-]+/g, " ")
      .toUpperCase();
  }

  /** Provider labels are written for prose; the status table needs the identity only. */
  function shortProviderLabel(value: string | null | undefined) {
    return (value ?? "")
      .trim()
      .replace(/\s+(commodities|markets|data|feed)$/i, "");
  }

  /**
   * Provider payloads mix two kinds of "warning": incidents (a fetch failed, a
   * provider fell back, a market went stale) and permanent capability
   * disclaimers ("coverage depends on entitlements", "futures curves are
   * unavailable unless a provider is added"). Disclaimers fire on every single
   * load regardless of connection health, so surfacing them next to real
   * incidents trains the user to ignore the warning surface entirely. Only
   * incidents belong on the Sitrep; the full payload text stays reachable
   * through each panel's provenance tooltip.
   */
  const WARNING_DISCLAIMER_PATTERNS = [
    /\bdepends on\b/,
    /\bmay require\b/,
    /\bcan be delayed\b/,
    /\bis entitlement\b/,
    /\bunless a\b/,
    /\bprovider is added\b/,
    /\bcoverage for live\b/,
    /\bin this provider slice\b/,
    /\bwhere available\b/,
    /\bwhere configured\b/,
    /\bshould be treated as\b/,
    /\bmust not be read as\b/,
    /\bread-only\b/,
    /\bheuristic/,
    /\bsample news\b/,
    /\bnews provider\b/,
    /\busing sample data\b/,
    /\bsample prices\b/,
    /\bnot an execution\b/,
    /\bdoes not place orders\b/
  ];

  const WARNING_INCIDENT_KEYWORDS = [
    "basis conflict",
    "unavailable",
    "failed",
    "missing",
    "stale",
    "cached",
    "entitlement",
    "fallback",
    "not configured",
    "delayed",
    "broken",
    "timeout"
  ];

  function isActionableSitrepWarning(value: string | null | undefined) {
    const text = (value ?? "").trim();
    if (!text) return false;
    const normalized = text.toLowerCase();
    if (WARNING_DISCLAIMER_PATTERNS.some((pattern) => pattern.test(normalized))) {
      return false;
    }
    return WARNING_INCIDENT_KEYWORDS.some((keyword) => normalized.includes(keyword));
  }

  $: equityRows = buildEquityRows(overview);
  $: indexRows = buildIndexRows(indicesOverview);
  $: fxRows = buildFxRows(macro);
  $: yieldRows = buildYieldRows(macro);
  $: commodityRows = buildCommodityRows(commodities);
  $: eventRows = buildEventRows(macro, prediction, commodities);
  $: changedRows = buildWhatChangedRows(macro, overview, commodities);
  $: warningsByDomain = sitrepWarningsByDomain(
    indicesOverview,
    overview,
    macro,
    commodities,
    prediction,
    news,
    workspaceMeta
  );
  $: warnings = Object.values(warningsByDomain).flat();
  $: macroWindowLabel = ((macro?.timeframe ?? "3M").trim() || "3M").toUpperCase();
  $: providerStatusRows = buildProviderStatusRows(
    indicesOverview,
    overview,
    macro,
    commodities,
    prediction,
    news,
    macroWindowLabel,
    warningsByDomain
  );
  $: predictionRetrievedAt = (prediction?.venues ?? [])
    .map((venue) => venue.retrieved_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;
  $: oldestSection = oldestSitrepSection([
    { id: "equities", label: "Equities", retrievedAt: overview?.retrieved_at },
    { id: "indices", label: "Indices", retrievedAt: indicesOverview?.retrieved_at },
    { id: "macro", label: "Macro", retrievedAt: macro?.retrieved_at },
    { id: "commodities", label: "Commodities", retrievedAt: commodities?.retrieved_at },
    { id: "prediction", label: "Prediction", retrievedAt: predictionRetrievedAt },
    { id: "news", label: "News", retrievedAt: news?.retrieved_at }
  ]);
  // Panel badges carry the same filtered incident list as the header WARN chip,
  // so a panel never flags a count the status line does not corroborate.
  $: indicesProvenance = indicesOverview
    ? toProvenanceBadge(indicesOverview, {
        qualityLabel: indicesOverview.coverage_label,
        sourceTimestamp: latestIndexCloseAt(indicesOverview),
        warnings: warningsByDomain.indices ?? []
      })
    : null;
  $: fxProvenance = macro
    ? toProvenanceBadge(macro, {
        provider: formatFxSourceMix(fxRows, macro),
        qualityLabel: `${macroWindowLabel} window`,
        warnings: warningsByDomain.macro ?? []
      })
    : null;
  $: ratesProvenance = macro
    ? toProvenanceBadge(macro, {
        provider: macro.rates_policy?.source_provider ?? macro.source_provider,
        retrievedAt: macro.rates_policy?.retrieved_at ?? macro.retrieved_at,
        qualityLabel: `${macroWindowLabel} window`,
        warnings: warningsByDomain.macro ?? []
      })
    : null;
  $: commoditiesProvenance = commodities
    ? toProvenanceBadge(commodities.coverage, {
        provider: formatCommodityProviderMix(commodities),
        qualityLabel: humanize(commodities.coverage.coverage_status),
        warnings: warningsByDomain.commodities ?? []
      })
    : null;
  $: newsProvenance = news
    ? toProvenanceBadge(news, {
        qualityLabel: pluralize(news.items.length, "headline"),
        warnings: warningsByDomain.news ?? []
      })
    : null;
  $: tvStatus =
    bloombergPlaybackStatus === "ready"
      ? "LIVE"
      : bloombergPlaybackStatus === "loading"
        ? "LOADING"
        : "EXTERNAL";
  $: providerMode = system?.mock_mode ? "MOCK" : system?.connection.connected ? system.market_data_mode.toUpperCase() : "OFFLINE";
  $: providerModeDetail = system?.mock_mode
    ? "Mock data mode — every price on this page is generated, not traded."
    : system?.connection.connected
      ? `IBKR connected. Market data mode: ${system.market_data_mode}.`
      : "IBKR is not connected. Boards fall back to their public providers (yfinance, FRED, EIA, RSS).";
  $: hasLoadedSitrepData = Boolean(overview || indicesOverview || macro || commodities || news || prediction);
  $: sitrepState = loading && !hasLoadedSitrepData ? "LOADING" : warnings.length ? "DEGRADED" : equityRows.length ? "LIVE" : "PARTIAL";
  $: sitrepStateDetail =
    sitrepState === "LOADING"
      ? "Fetching the Sitrep workspace."
      : sitrepState === "DEGRADED"
        ? `${warnings.length} open provider incident${warnings.length === 1 ? "" : "s"}. Data is still shown, but at least one board is running on fallback or partial coverage.`
        : sitrepState === "PARTIAL"
          ? "Some boards returned no rows. Reload the affected panel or check Provider Status."
          : "Every board loaded with no open provider incidents.";
  $: oldestSectionLabel = oldestSection
    ? `OLDEST ${oldestSection.label.toUpperCase()} ${formatSitrepSectionAge(oldestSection.retrievedAt).toUpperCase()}`
    : "OLDEST N/A";
  $: oldestSectionDetail = oldestSection
    ? `${oldestSection.label} is the least recently refreshed board on this page, retrieved ${formatDateTimeWithZone(oldestSection.retrievedAt)}.`
    : "No board has reported a retrieval timestamp yet.";
  $: equityTapeState = equityRows.length
    ? ""
    : overview
      ? `US EQUITY TAPE N/A / ${overview.freshness_label.toUpperCase()}`
      : loading
        ? "US EQUITY TAPE LOADING"
        : "US EQUITY TAPE NOT LOADED";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-identity">
      <span class="title">SITREP</span>
    </div>
    <div class="equity-strip" aria-label="US equity tape">
      {#if equityRows.length}
        <div class="strip-track">
          {#each [...equityRows, ...equityRows] as row}
            <button
              type="button"
              class:selected={isSelectedEquityRow(row)}
              class="strip-item"
              on:click={() => openEquityRow(row)}
              aria-label={`Open ${row.label} in Research`}
              aria-pressed={isSelectedEquityRow(row)}
              title={`Open ${row.label} in Research`}
            >
              <strong>{row.label}</strong>
              <em>{row.last}</em>
              <b class={row.tone}>{row.change}</b>
            </button>
          {/each}
        </div>
      {:else}
        <span class="strip-empty">{equityTapeState}</span>
      {/if}
    </div>
    <div class="status-line">
      <span class="status-cell">
        <Tooltip heading="Sitrep state" text={sitrepStateDetail} placement="bottom" hint>
          <b class:warning={sitrepState !== "LIVE"}>{sitrepState}</b>
        </Tooltip>
      </span>
      <span class="status-cell">
        <Tooltip heading="Market data" text={providerModeDetail} placement="bottom" hint>
          <b>{providerMode}</b>
        </Tooltip>
      </span>
      {#if warnings.length > 0}
        <span class="status-cell">
          <Tooltip heading="Open provider incidents" placement="bottom" hint maxWidth="30rem">
            <b class="warning">{warnings.length} WARN</b>
            <svelte:fragment slot="content">
              <ul class="tooltip-list warning-items">
                {#each warnings as warning}
                  <li>{warning}</li>
                {/each}
              </ul>
            </svelte:fragment>
          </Tooltip>
        </span>
      {/if}
      <span class="status-cell">
        <Tooltip heading="Oldest board" text={oldestSectionDetail} placement="bottom" hint>
          <b>{oldestSectionLabel}</b>
        </Tooltip>
      </span>
    </div>
  </article>

  <div class="workspace-grid">
    <div class="primary-column">
      <div class="market-grid">
        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Worldwide Indices</span>
              <ProvenanceBadge variant="dot" data={indicesProvenance} label={indicesOverview?.source_provider ?? "not loaded"} />
            </div>
            <button type="button" class="reload-button" on:click={refreshIndices} disabled={refreshing.indices || isCoolingDown("indices")} aria-label={refreshTitle("indices")} title={refreshTitle("indices")}>
              <span class:spinning={refreshing.indices} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={indexRows} profile="indices" hideSource showPctChange changeLabel="Latest Day" pctChangeLabel="Latest Day %" contextLabel="Proxy / As Of" emptyLabel="No index overview loaded." onSelect={(row) => openMarketRow("indices", row)} />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>FX Pairs</span>
              <ProvenanceBadge variant="dot" data={fxProvenance} label={formatFxSourceMix(fxRows, macro)} />
            </div>
            <button type="button" class="reload-button" on:click={refreshFx} disabled={refreshing.fx || isCoolingDown("fx")} aria-label={refreshTitle("fx")} title={refreshTitle("fx")}>
              <span class:spinning={refreshing.fx} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={fxRows} profile="fx" hideGroup hideSource hideContext showPctChange changeLabel={formatSitrepWindowLabel("CHG", macroWindowLabel)} pctChangeLabel={formatSitrepWindowLabel("%CHG", macroWindowLabel)} emptyLabel="No FX strip loaded." onSelect={(row) => openMarketRow("fx", row)} />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Rates</span>
              <ProvenanceBadge variant="dot" data={ratesProvenance} label={macro?.rates_policy?.source_provider ?? "not loaded"} />
            </div>
            <button type="button" class="reload-button" on:click={refreshRates} disabled={refreshing.rates || isCoolingDown("rates")} aria-label={refreshTitle("rates")} title={refreshTitle("rates")}>
              <span class:spinning={refreshing.rates} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={yieldRows} profile="yields" hideGroup hideSource changeLabel={formatSitrepWindowLabel("Move", macroWindowLabel)} contextLabel="Prior" emptyLabel="No rates policy payload loaded." onSelect={(row) => openMarketRow("yields", row)} />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <div class="table-title">
              <span>Commodities</span>
              <ProvenanceBadge variant="dot" data={commoditiesProvenance} label={formatCommodityProviderMix(commodities)} />
            </div>
            <button type="button" class="reload-button" on:click={refreshCommodities} disabled={refreshing.commodities || isCoolingDown("commodities")} aria-label={refreshTitle("commodities")} title={refreshTitle("commodities")}>
              <span class:spinning={refreshing.commodities} aria-hidden="true">↻</span>
            </button>
          </div>
          <SitrepMarketTable rows={commodityRows} profile="commodities" hideSource showPctChange contextLabel="Basis" changeLabel="CHG (1D)" pctChangeLabel="%CHG (1D)" emptyLabel="No commodities workspace loaded." onSelect={(row) => openMarketRow("commodities", row)} />
        </article>
      </div>

      <article class="panel tape-panel">
        <div class="table-header">
          <div class="table-title">
            <span>What Changed</span>
          </div>
        </div>
        <div class="tape-list">
          {#if changedRows.length}
            {#each changedRows as row (row.id)}
              <div class="tape-row-wrap">
                <button
                  type="button"
                  use:flashOnMount={row.tone === 'positive' ? 'up' : row.tone === 'negative' ? 'down' : 'neutral'}
                  class="tape-row {row.tone}"
                  class:clickable={hasTapeHandoff(row)}
                  disabled={!hasTapeHandoff(row)}
                  on:click={() => openTapeRow(row)}
                >
                  <span>{row.source}</span>
                  <strong>{row.title}</strong>
                  <Tooltip block focusable={false} text={row.detail} disabled={row.detail.length <= TAPE_DETAIL_CLAMP}>
                    <span class="tape-detail">{row.detail}</span>
                  </Tooltip>
                  <small>{row.meta}</small>
                </button>
                <button
                  type="button"
                  class="tape-pin"
                  class:active={isSitrepFollowUpSaved(followUps, row.id)}
                  on:click={() => toggleFollowUp(row)}
                  aria-pressed={isSitrepFollowUpSaved(followUps, row.id)}
                  aria-label={isSitrepFollowUpSaved(followUps, row.id) ? "Remove follow-up" : "Save as follow-up"}
                  title={isSitrepFollowUpSaved(followUps, row.id) ? "Remove follow-up" : "Save as follow-up"}
                >{isSitrepFollowUpSaved(followUps, row.id) ? "★" : "☆"}</button>
              </div>
            {/each}
          {:else}
            <p class="empty-state">LOAD MARKET CONTEXT TO POPULATE CHANGE TRIAGE.</p>
          {/if}
        </div>
      </article>

      <article class="panel tape-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Events &amp; Markets</span>
          </div>
        </div>
        <div class="tape-list">
          {#if eventRows.length}
            {#each eventRows as row (row.id)}
              <div class="tape-row-wrap">
                <button
                  type="button"
                  use:flashOnMount={row.tone === 'positive' ? 'up' : row.tone === 'negative' ? 'down' : 'neutral'}
                  class="tape-row {row.tone}"
                  class:clickable={hasTapeHandoff(row)}
                  disabled={!hasTapeHandoff(row)}
                  on:click={() => openTapeRow(row)}
                >
                  <span>{row.source}</span>
                  <strong>{row.title}</strong>
                  <Tooltip block focusable={false} text={row.detail} disabled={row.detail.length <= TAPE_DETAIL_CLAMP}>
                    <span class="tape-detail">{row.detail}</span>
                  </Tooltip>
                  <small>{row.meta}</small>
                </button>
                <button
                  type="button"
                  class="tape-pin"
                  class:active={isSitrepFollowUpSaved(followUps, row.id)}
                  on:click={() => toggleFollowUp(row)}
                  aria-pressed={isSitrepFollowUpSaved(followUps, row.id)}
                  aria-label={isSitrepFollowUpSaved(followUps, row.id) ? "Remove follow-up" : "Save as follow-up"}
                  title={isSitrepFollowUpSaved(followUps, row.id) ? "Remove follow-up" : "Save as follow-up"}
                >{isSitrepFollowUpSaved(followUps, row.id) ? "★" : "☆"}</button>
              </div>
            {/each}
          {:else}
            <p class="empty-state">LOAD MACRO / PREDICTION / COMMODITY CONTEXT TO POPULATE EVENTS.</p>
          {/if}
        </div>
      </article>

    </div>

    <aside class="support-column">
      <article class="panel media-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Bloomberg TV</span>
            {#if bloombergPlaybackStatus !== "ready"}<small class="warning">{bloombergPlaybackMessage}</small>{/if}
          </div>
          <div class="media-links">
            <a href={bloombergWatchUrl} target="_blank" rel="noreferrer">Bloomberg</a>
            <a href={bloombergYouTubeUrl} target="_blank" rel="noreferrer">YouTube</a>
          </div>
        </div>
        <div class="video-shell">
          <video bind:this={bloombergVideo} title="Bloomberg Television live stream" controls muted playsinline preload="metadata"></video>
          {#if bloombergPlaybackStatus !== "ready"}
            <div class="video-state">
              <strong>{bloombergPlaybackStatus === "loading" ? "LOADING BLOOMBERG TV" : "BLOOMBERG TV PLAYER UNAVAILABLE"}</strong>
              <span>{bloombergPlaybackMessage}</span>
              {#if bloombergPlaybackStatus !== "loading"}
                <a href={bloombergWatchUrl} target="_blank" rel="noreferrer">Open Bloomberg Live</a>
              {/if}
            </div>
          {/if}
        </div>
      </article>

      <article class="panel table-panel news-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Market News</span>
            <ProvenanceBadge variant="dot" data={newsProvenance} label={news ? pluralize(news.items.length, "headline") : "not loaded"} />
          </div>
          <button type="button" class="reload-button" on:click={refreshNews} disabled={refreshing.news || isCoolingDown("news")} aria-label={refreshTitle("news")} title={refreshTitle("news")}>
            <span class:spinning={refreshing.news} aria-hidden="true">↻</span>
          </button>
        </div>
        <div class="news-wrap">
          {#if news?.items?.length}
            {#each news.items as item (item.normalized_id)}
              {@const chips = newsEntityChips(item)}
              <div use:flashOnMount={'neutral'} class="news-row">
                <span class="news-time">{formatTime(item.published_at)}</span>
                <div class="news-body">
                  <p class="news-title">{item.title}</p>
                  {#if chips.length}
                    <span class="news-chips">
                      {#each chips as chip (chip.handoff.symbol)}
                        <button
                          type="button"
                          class="news-chip"
                          on:click={() => openNewsEntity(chip)}
                          title={`Open ${chip.entity.label} in Equity Research`}
                        >{chip.handoff.symbol}</button>
                      {/each}
                    </span>
                  {/if}
                </div>
                <Tooltip heading={item.source_name} text={newsSourceDetail(item)} focusable={false} maxWidth="22rem">
                  <a class="news-source" href={item.url} target="_blank" rel="noreferrer">{abbreviateSource(item.source_name)}</a>
                </Tooltip>
              </div>
            {/each}
          {:else}
            <p class="news-empty">NO NEWS LOADED.</p>
          {/if}
        </div>
      </article>

      <article class="panel tape-panel follow-up-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Follow-Ups</span>
            {#if followUps.length}
              <small>{openFollowUpCount} open / {resolvedFollowUpCount} resolved</small>
            {/if}
          </div>
        </div>
        <div class="tape-list">
          {#if followUps.length}
            {#each followUps as item (item.id)}
              <div class="tape-row-wrap" class:resolved={item.status === "resolved"}>
                <button
                  type="button"
                  class="tape-row follow-up-row {item.tone}"
                  class:clickable={Boolean(item.handoff)}
                  disabled={!item.handoff}
                  on:click={() => openFollowUp(item)}
                  title={item.handoff ? "Open in target tab" : "No handoff target"}
                >
                  <span>{item.status === "resolved" ? "RESOLVED" : item.source}</span>
                  <strong>{item.title}</strong>
                  <Tooltip block focusable={false} text={item.detail} disabled={item.detail.length <= TAPE_DETAIL_CLAMP}>
                    <span class="tape-detail">{item.detail}</span>
                    {#if item.note}<em class="follow-up-note">✎ {item.note}</em>{/if}
                  </Tooltip>
                  <small>{shortDate(item.saved_at)}</small>
                </button>
                <button
                  type="button"
                  class="tape-pin"
                  class:active={followUpNoteDraftId === item.id}
                  on:click={() => (followUpNoteDraftId === item.id ? cancelFollowUpNote() : beginFollowUpNote(item))}
                  aria-label={item.note ? "Edit follow-up note" : "Add follow-up note"}
                  title={item.note ? "Edit follow-up note" : "Add follow-up note"}
                >✎</button>
                <button
                  type="button"
                  class="tape-pin"
                  class:active={item.status === "resolved"}
                  on:click={() => toggleFollowUpResolved(item)}
                  aria-pressed={item.status === "resolved"}
                  aria-label={item.status === "resolved" ? "Reopen follow-up" : "Mark follow-up resolved"}
                  title={item.status === "resolved" ? "Reopen follow-up" : "Mark follow-up resolved"}
                >✓</button>
                <button
                  type="button"
                  class="tape-pin"
                  on:click={() => dismissFollowUp(item.id)}
                  aria-label="Dismiss follow-up"
                  title="Dismiss follow-up"
                >✕</button>
              </div>
              {#if followUpNoteDraftId === item.id}
                <form class="follow-up-note-editor" on:submit|preventDefault={() => saveFollowUpNote(item)}>
                  <input
                    type="text"
                    bind:value={followUpNoteDraft}
                    placeholder="Add a triage note"
                    aria-label={`Note for ${item.title}`}
                    maxlength="240"
                  />
                  <button type="submit">Save</button>
                  <button type="button" on:click={cancelFollowUpNote}>Cancel</button>
                </form>
              {/if}
            {/each}
          {:else}
            <p class="empty-state">NO SAVED FOLLOW-UPS — STAR A TRIAGE ROW TO TRACK IT.</p>
          {/if}
        </div>
      </article>

      <article class="panel provider-panel">
        <div class="table-header">
          <div class="table-title">
            <span>Provider Status</span>
          </div>
        </div>
        <table class="status-table">
          <thead>
            <tr>
              <th scope="col">Domain</th>
              <th scope="col">Source</th>
              <th scope="col">State</th>
              <th scope="col" class="right">Age</th>
            </tr>
          </thead>
          <tbody>
            {#each providerStatusRows as row (row.id)}
              <tr class:warn={row.warn}>
                <th scope="row">{row.domain}</th>
                <td class="status-source">
                  {#if row.source.length > STATUS_SOURCE_CLAMP}
                    <Tooltip text={row.source} focusable={false}><span>{row.source}</span></Tooltip>
                  {:else}
                    {row.source}
                  {/if}
                </td>
                <td class="status-state" class:warning={row.warn}>
                  {#if row.warnings.length}
                    <Tooltip heading={`${row.domain} incidents`} maxWidth="28rem">
                      <span class="state-text">{row.freshness}</span>
                      <span class="warn-flag">!{row.warnings.length}</span>
                      <svelte:fragment slot="content">
                        <ul class="tooltip-list warning-items">
                          {#each row.warnings as warning}
                            <li>{warning}</li>
                          {/each}
                        </ul>
                      </svelte:fragment>
                    </Tooltip>
                  {:else}
                    <span class="state-text">{row.freshness}</span>
                  {/if}
                </td>
                <td class="right" class:warning={row.warn}>
                  <Tooltip text={`Retrieved ${row.asOf}`} focusable={false}>
                    <span>{row.age}</span>
                  </Tooltip>
                </td>
              </tr>
            {/each}
            <tr class:warn={bloombergPlaybackStatus === "error" || bloombergPlaybackStatus === "unsupported"}>
              <th scope="row">TV</th>
              <td class="status-source">Bloomberg HLS</td>
              <td
                class="status-state"
                class:warning={bloombergPlaybackStatus === "error" || bloombergPlaybackStatus === "unsupported"}
              >
                <span class="state-text">{tvStatus}</span>
              </td>
              <td class="right">external</td>
            </tr>
          </tbody>
        </table>
      </article>
    </aside>
  </div>
</section>

<style>
  .view {
    display: grid;
    gap: var(--space-4);
  }

  .panel {
    display: grid;
    gap: var(--space-4);
    align-content: start;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
  }

  .table-panel,
  .tape-panel,
  .media-panel,
  .provider-panel {
    padding: 0;
    overflow: hidden;
    gap: 0;
  }

  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    min-height: 26px;
    flex-shrink: 0;
  }

  .table-title {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
    min-width: 0;
  }

  .table-title span {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
    white-space: nowrap;
  }

  .table-title small {
    color: var(--text-2);
    font-size: var(--text-2xs);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .media-links {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-shrink: 0;
  }

  .media-links a,
  .video-state a {
    color: var(--accent);
    font-size: var(--text-xs);
    text-decoration: none;
    white-space: nowrap;
  }

  .media-links a:hover,
  .video-state a:hover {
    text-decoration: underline;
  }

  .reload-button {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-sm);
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
    align-items: baseline;
    gap: var(--space-4);
    padding: var(--space-4) var(--space-5);
    flex-shrink: 0;
    white-space: nowrap;
  }

  .header-identity .title {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  p {
    margin: 0;
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

  /* Rows are click targets — stop the scroll while the pointer is over them */
  .equity-strip:hover .strip-track,
  .equity-strip:focus-within .strip-track {
    animation-play-state: paused;
  }

  .strip-item {
    appearance: none;
    background: transparent;
    border: 0;
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-5);
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
    font-size: var(--text-sm);
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
    padding: var(--space-4) var(--space-5);
    color: var(--text-2);
    font-size: var(--text-sm);
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
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
  }

  .status-line .status-cell {
    display: inline-flex;
    align-items: center;
    padding: 0 var(--space-4);
    border-left: 1px solid var(--divider);
  }

  .status-line b {
    font-weight: inherit;
  }

  .tooltip-list {
    margin: 0;
    padding-left: var(--space-5);
    display: grid;
    gap: var(--space-2);
  }

  .tooltip-list.warning-items {
    color: var(--warning);
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(29rem, 0.48fr);
    gap: var(--space-4);
  }

  .primary-column,
  .support-column {
    display: grid;
    gap: var(--space-4);
    align-content: start;
    min-width: 0;
  }

  .market-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .tape-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .tape-row small {
    color: var(--text-2);
    line-height: 1.35;
  }

  .tape-list {
    display: grid;
    gap: 0;
  }

  .tape-row-wrap {
    display: flex;
    align-items: stretch;
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .tape-row-wrap:last-child {
    border-bottom: 0;
  }

  .tape-row-wrap .tape-row {
    flex: 1;
    min-width: 0;
    border-bottom: 0;
  }

  .tape-pin {
    appearance: none;
    background: transparent;
    border: 0;
    border-left: 1px solid var(--divider);
    color: var(--text-2);
    font: inherit;
    font-size: var(--text-sm);
    width: 2rem;
    flex-shrink: 0;
    cursor: pointer;
    display: grid;
    place-items: center;
  }

  .tape-pin:hover,
  .tape-pin:focus-visible {
    background: var(--bg-1);
    color: var(--accent);
  }

  .tape-pin:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .tape-pin.active {
    color: var(--accent);
  }

  .follow-up-panel .tape-list {
    overflow: auto;
    max-height: 18rem;
  }

  .tape-row-wrap.resolved .tape-row {
    opacity: 0.55;
  }

  .tape-row-wrap.resolved .tape-row strong {
    text-decoration: line-through;
  }

  .follow-up-note {
    display: block;
    color: var(--text-2);
    font-style: normal;
    font-size: var(--text-xs);
  }

  .follow-up-note-editor {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
    background: var(--bg-1);
  }

  .follow-up-note-editor input {
    flex: 1;
    min-width: 0;
    background: var(--bg-0);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    color: var(--text-0);
    font: inherit;
    font-size: var(--text-sm);
    padding: var(--space-1) var(--space-3);
  }

  .follow-up-note-editor button {
    appearance: none;
    background: transparent;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    color: var(--text-2);
    font: inherit;
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: var(--space-1) var(--space-3);
    cursor: pointer;
  }

  .follow-up-note-editor button:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .tape-row {
    appearance: none;
    width: 100%;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    display: grid;
    grid-template-columns: 5.8rem minmax(0, 0.9fr) minmax(0, 1.7fr) minmax(5.5rem, 0.45fr);
    gap: var(--space-4);
    align-items: baseline;
    padding: var(--space-3) var(--space-5);
    border: 0;
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .tape-row:last-child {
    border-bottom: 0;
  }

  .tape-row.clickable {
    cursor: pointer;
  }

  .tape-row.clickable:hover,
  .tape-row.clickable:focus-visible {
    background: var(--bg-1);
  }

  .tape-row:disabled {
    cursor: default;
  }

  .tape-row:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .tape-row strong,
  .tape-row .tape-detail,
  .tape-row small {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  /* Divergence and focus rows carry multi-sentence research prose. Two lines is
     the triage read; the rest lives in the row's tooltip. */
  .tape-row .tape-detail {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: var(--text-1);
    line-height: 1.35;
  }

  .video-shell {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: var(--bg-0);
    overflow: hidden;
  }

  .video-shell video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--bg-0);
  }

  .video-state {
    position: absolute;
    inset: 0;
    display: grid;
    place-content: center;
    justify-items: center;
    gap: var(--space-2);
    padding: var(--space-5);
    background: var(--bg-0);
    color: var(--text-2);
    text-align: center;
    pointer-events: none;
  }

  .video-state strong {
    color: var(--text-0);
    font-size: var(--text-xs);
    letter-spacing: 0.08em;
  }

  .video-state span {
    font-size: var(--text-xs);
  }

  .video-state a {
    pointer-events: auto;
  }

  .news-wrap {
    overflow: auto;
    max-height: 28rem;
  }

  .news-row {
    display: grid;
    grid-template-columns: 3rem minmax(0, 1fr) max-content;
    gap: 0 var(--space-4);
    align-items: start;
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .news-row:last-child {
    border-bottom: 0;
  }

  .news-time {
    color: var(--accent);
    font-size: var(--text-xs);
    padding-top: var(--space-1);
    white-space: nowrap;
  }

  .news-title {
    color: var(--text-0);
    font-size: var(--text-sm);
    line-height: 1.35;
    margin: 0;
  }

  .news-body {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }

  .news-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .news-chip {
    height: 20px;
    padding: 0 var(--space-2);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--accent);
    font: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
  }

  .news-chip:hover,
  .news-chip:focus-visible {
    border-color: var(--accent);
  }

  .news-source {
    color: var(--text-2);
    font-size: var(--text-xs);
    text-decoration: none;
    text-align: right;
    white-space: nowrap;
    padding-top: var(--space-1);
  }

  .news-source:hover {
    color: var(--accent);
  }

  .news-empty {
    padding: var(--space-5);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-sm);
    margin: 0;
  }

  a {
    color: var(--accent);
    text-decoration: none;
    font-size: var(--text-sm);
  }

  a:hover {
    color: var(--text-0);
  }

  .status-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }

  .status-table th,
  .status-table td {
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: baseline;
    font-size: var(--text-sm);
    color: var(--text-2);
    min-width: 0;
  }

  .status-table thead th {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .status-table tbody tr:last-child th,
  .status-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .status-table tbody th {
    color: var(--text-1);
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-table th:nth-child(1) {
    width: 24%;
  }

  .status-table th:nth-child(2) {
    width: 29%;
  }

  .status-table th:nth-child(3) {
    width: 29%;
  }

  .status-table th:nth-child(4) {
    width: 18%;
  }

  .status-table .right {
    text-align: right;
  }

  .status-table .status-source {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-table .state-text {
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .status-table .warn-flag {
    margin-left: var(--space-2);
    color: var(--warning);
    font-size: var(--text-2xs);
    font-weight: 700;
  }

  .empty-state {
    margin: 0;
    padding: var(--space-4) var(--space-5);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-sm);
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
    .support-column {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      justify-content: stretch;
    }

    .status-line {
      justify-content: flex-start;
    }

    .tape-row {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-1);
    }
  }
</style>
