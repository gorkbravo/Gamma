<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import CompactContextMenu from "../components/CompactContextMenu.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { parseApiTimestampToUtcSeconds } from "../lib/chart-data";
  import { flashOnChange } from "../lib/flash";
  import {
    CALIBRATION_LEAD_TIME_CHOICES,
    CALIBRATION_SAMPLE_CHOICES,
    DEFAULT_CALIBRATION_LEAD_TIMES,
    DEFAULT_CALIBRATION_SAMPLE,
    HISTORY_RANGES,
    MAX_COMPARE_LEGS,
    RESOLUTION_CHOICES,
    PREDICTION_WORKING_BASKET_NAME,
    buildCalibrationRows,
    buildOutcomeLadder,
    calibrationCurveFor,
    comparisonColor,
    describeCalibrationMethod,
    describeHistoryCoverage,
    formatResolution,
    sortPairsByDislocation,
    toggleCalibrationLeadTime,
    toggleCompareSelection,
    type CalibrationBucketRow,
    type OutcomeLadderRow
  } from "../lib/prediction-markets";
  import type {
    CrossTabHandoffEnvelope,
    PredictionCalibrationCurve,
    PredictionCalibrationSummary,
    PredictionComparisonSet,
    PredictionEventBook,
    PredictionEventBookLeg,
    PredictionOrderBookDepth,
    PredictionSavedResearch,
    PredictionSavedWatchlistEntry,
    PredictionHistoryRange,
    PredictionMarket,
    PredictionMarketComparison,
    PredictionMarketListResponse,
    PredictionMarketsMode,
    PredictionOutcomeSeriesResponse,
    PredictionProbabilityHistoryResponse,
    PredictionVenueStatus,
    PredictionWalletSummary,
    RelatedPredictionMarketListResponse,
    StrategyLabHandoffDefaultSide,
    StrategyLabHandoffEnvelope
  } from "../lib/api/types";
  import type { PredictionMarketScreenerOptions, PredictionMarketSortBy } from "../lib/stores/app";
  import { buildPredictionMarketStrategyHandoff } from "../lib/view-models/research";

  import { activateRowOnKey } from "../lib/row-activation";
  export let mode: PredictionMarketsMode = "screener";
  export let screener: PredictionMarketListResponse | null = null;
  export let detail: PredictionMarket | null = null;
  export let history: PredictionProbabilityHistoryResponse | null = null;
  export let outcomeSeries: PredictionOutcomeSeriesResponse | null = null;
  export let comparison: PredictionMarketComparison | null = null;
  export let wallet: PredictionWalletSummary | null = null;
  export let related: RelatedPredictionMarketListResponse | null = null;
  export let eventBook: PredictionEventBook | null = null;
  export let depth: PredictionOrderBookDepth | null = null;
  export let crossDomainHandoffs: CrossTabHandoffEnvelope[] = [];
  export let onCrossDomainHandoff:
    | ((handoff: CrossTabHandoffEnvelope) => Promise<unknown> | void)
    | undefined = undefined;
  export let calibration: PredictionCalibrationSummary | null = null;
  export let historyRange: PredictionHistoryRange = "max";
  export let historyResolution: number | null = null;
  export let historyOutcomeId: string | null = null;
  export let calibrationLeadTimes: number[] = [...DEFAULT_CALIBRATION_LEAD_TIMES];
  export let calibrationSample: number = DEFAULT_CALIBRATION_SAMPLE;
  export let loading = false;
  export let historyLoading = false;
  export let compareLoading = false;
  export let calibrationLoading = false;
  export let savedResearch: PredictionSavedResearch | null = null;
  export let compareSelection: string[] = [];
  export let savedLoading = false;
  export let onToggleWatchlist: ((market: PredictionMarket) => Promise<unknown> | void) | undefined = undefined;
  export let onSetCompareSelection: ((marketIds: string[]) => void) | undefined = undefined;
  export let onSaveComparisonSet:
    | ((options: { name: string; marketIds: string[] }) => Promise<unknown> | void)
    | undefined = undefined;
  export let onDeleteComparisonSet: ((setId: string) => Promise<unknown> | void) | undefined = undefined;
  export let onLoadEventBook: ((marketId: string) => Promise<unknown> | void) | undefined = undefined;
  export let onLoadCalibration:
    | ((marketId: string, options?: { leadTimes?: number[]; sampleSize?: number }) => Promise<unknown> | void)
    | undefined = undefined;
  export let onLoadScreener: (options?: PredictionMarketScreenerOptions) => Promise<unknown> | void;
  export let onSelectMarket: (marketId: string) => Promise<unknown> | void;
  export let onLoadHistory:
    | ((
        marketId: string,
        options?: {
          range?: PredictionHistoryRange;
          resolutionMinutes?: number | null;
          outcomeId?: string | null;
          includeOutcomes?: boolean;
        }
      ) => Promise<unknown> | void)
    | undefined = undefined;
  export let onCompare:
    | ((
        marketIds: string[],
        options?: { range?: PredictionHistoryRange; resolutionMinutes?: number | null }
      ) => Promise<unknown> | void)
    | undefined = undefined;
  export let onSendToStrategyLab:
    | ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void)
    | undefined = undefined;

  const modes: { id: PredictionMarketsMode; label: string }[] = [
    { id: "screener", label: "Screener" },
    { id: "contract", label: "Contract" },
    { id: "compare", label: "Compare" },
    { id: "calibration", label: "Calibration" }
  ];

  type VenueKey = "polymarket" | "kalshi";
  const allVenues: VenueKey[] = ["polymarket", "kalshi"];
  const availableCategories = ["Politics", "Finance", "Geopolitics", "Crypto", "Economy", "Tech/AI"];

  let query = "";
  let status: "open" | "closed" | "all" = "open";
  let sortBy: PredictionMarketSortBy = "research_rank";
  let category = "";
  let venueSelection: VenueKey[] = [...allVenues];
  let minVolume: number | null = null;
  let minLiquidity: number | null = null;
  let minProbability: number | null = null;
  let maxProbability: number | null = null;
  let maxDaysToResolution: number | null = null;
  let minRepricingAbs: number | null = null;
  let screenerLimit = 40;

  let strategySide: Extract<StrategyLabHandoffDefaultSide, "long_yes" | "long_no"> = "long_yes";
  let strategyContextMenu = { open: false, x: 0, y: 0, market: null as PredictionMarket | null };

  let cachedVenueStatuses: Partial<Record<VenueKey, PredictionVenueStatus>> = {};
  let autoRunHandle: ReturnType<typeof setTimeout> | null = null;
  let autoRunReady = false;
  let lastSubmittedKey = "";
  let currentScreenerKey = "";

  let watchlist: PredictionSavedWatchlistEntry[] = [];
  let namedSets: PredictionComparisonSet[] = [];
  let newSetName = "";
  let compareNotice = "";
  let lastComparedKey = "";
  let showOutcomeOverlay = true;

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const signedPct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 0) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US") : "N/A";
  const dayStamp = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" }) : "N/A";
  const compactId = (value: string | null | undefined) => {
    const text = String(value ?? "").trim();
    if (!text) return "N/A";
    return text.length <= 24 ? text : `${text.slice(0, 12)}...${text.slice(-10)}`;
  };
  const truncName = (value: string | null | undefined, max = 18) => {
    const text = String(value ?? "").trim();
    if (!text) return "N/A";
    return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
  };
  const toneOf = (value: number | null | undefined) =>
    value == null ? "" : value > 0 ? "positive" : value < 0 ? "negative" : "";
  const directionOf = (value: number | null | undefined) =>
    value == null ? "neutral" : value > 0 ? "up" : value < 0 ? "down" : "neutral";

  function freshnessTone(statusValue: string | null | undefined) {
    if (statusValue === "broken") return "broken";
    if (statusValue === "stale") return "stale";
    if (statusValue === "delayed") return "delayed";
    if (statusValue === "fresh") return "fresh";
    return "";
  }

  const HANDOFF_TAB_LABELS: Record<string, string> = {
    macro: "Macro",
    commodities: "Commodities",
    maritime: "Sealanes"
  };
  const handoffTabLabel = (tabId: string) => HANDOFF_TAB_LABELS[tabId] ?? tabId;
  const leadTimeLabel = (hours: number) => (hours % 24 === 0 && hours >= 24 ? `T-${hours / 24}D` : `T-${hours}H`);

  function completenessTone(statusValue: string | null | undefined) {
    if (statusValue === "complete") return "fresh";
    if (statusValue === "truncated" || statusValue === "partial_pricing") return "stale";
    return "muted";
  }

  function venueTone(statusValue: string | null | undefined) {
    if (statusValue === "active") return "fresh";
    if (statusValue === "filtered") return "delayed";
    return "stale";
  }

  function marketTone(probability: number | null | undefined) {
    if (probability == null) return "";
    if (probability >= 0.7) return "hot";
    if (probability <= 0.3) return "cold";
    return "";
  }

  function daysUntil(value: string | null | undefined): number | null {
    if (!value) return null;
    return Math.max((new Date(value).getTime() - Date.now()) / 86400000, 0);
  }

  function daysLabel(value: number | null) {
    if (value == null) return "N/A";
    return `${value.toFixed(value >= 10 ? 0 : 1)}d`;
  }

  onMount(() => {
    autoRunReady = true;
    if (!screener?.markets?.length) {
      void runScreener();
      return;
    }
    lastSubmittedKey = currentScreenerKey;
  });

  onDestroy(() => {
    if (autoRunHandle) clearTimeout(autoRunHandle);
  });

  function selectMode(next: PredictionMarketsMode) {
    mode = next;
  }

  function toggleVenue(venue: VenueKey) {
    if (venueSelection.includes(venue) && venueSelection.length === 1) return;
    venueSelection = venueSelection.includes(venue)
      ? venueSelection.filter((item) => item !== venue)
      : [...venueSelection, venue];
  }

  async function runScreener(forceRefresh = false) {
    lastSubmittedKey = currentScreenerKey;
    if (autoRunHandle) {
      clearTimeout(autoRunHandle);
      autoRunHandle = null;
    }
    await onLoadScreener({
      query,
      venues: venueSelection,
      status,
      forceRefresh,
      category: category || undefined,
      sortBy,
      limit: screenerLimit,
      minVolume: minVolume ?? undefined,
      minLiquidity: minLiquidity ?? undefined,
      minProbability: minProbability == null ? undefined : minProbability / 100,
      maxProbability: maxProbability == null ? undefined : maxProbability / 100,
      maxDaysToResolution: maxDaysToResolution ?? undefined,
      minRepricingAbs: minRepricingAbs == null ? undefined : minRepricingAbs / 100
    });
  }

  function scheduleAutoRun() {
    if (!autoRunReady) return;
    if (currentScreenerKey === lastSubmittedKey) return;
    if (autoRunHandle) clearTimeout(autoRunHandle);
    autoRunHandle = setTimeout(() => void runScreener(), query.trim() ? 250 : 50);
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void runScreener();
    }
  }

  function resetFilters() {
    minVolume = null;
    minLiquidity = null;
    minProbability = null;
    maxProbability = null;
    maxDaysToResolution = null;
    minRepricingAbs = null;
    category = "";
  }

  async function openContract(marketId: string) {
    await onSelectMarket(marketId);
    mode = "contract";
  }

  function stepContract(direction: -1 | 1) {
    const rows = screener?.markets ?? [];
    if (!rows.length) return;
    const index = rows.findIndex((row) => row.market_id === detail?.market_id);
    const nextIndex = index < 0 ? 0 : (index + direction + rows.length) % rows.length;
    void onSelectMarket(rows[nextIndex].market_id);
  }

  function handleContractKeydown(event: KeyboardEvent) {
    if (mode !== "contract" || event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) {
      return;
    }
    if (event.key === "[") stepContract(-1);
    if (event.key === "]") stepContract(1);
  }

  async function applyRange(range: PredictionHistoryRange) {
    historyRange = range;
    if (detail && onLoadHistory) {
      await onLoadHistory(detail.market_id, { range, includeOutcomes: true });
    }
    if (mode === "compare" && compareSelection.length >= 2 && onCompare) {
      await onCompare(compareSelection, { range });
    }
  }

  async function applyResolution(resolutionMinutes: number | null) {
    historyResolution = resolutionMinutes;
    if (detail && onLoadHistory) {
      await onLoadHistory(detail.market_id, { resolutionMinutes, includeOutcomes: true });
    }
    if (mode === "compare" && compareSelection.length >= 2 && onCompare) {
      await onCompare(compareSelection, { resolutionMinutes });
    }
  }

  async function selectOutcome(outcomeId: string | null) {
    historyOutcomeId = outcomeId;
    if (detail && onLoadHistory) {
      await onLoadHistory(detail.market_id, { outcomeId });
    }
  }

  function toggleWatch(market: PredictionMarket) {
    void onToggleWatchlist?.(market);
  }

  function isWatched(marketId: string | null | undefined) {
    return Boolean(marketId) && watchlist.some((entry) => entry.market_id === marketId);
  }

  function toggleCompare(marketId: string) {
    const next = toggleCompareSelection(compareSelection, marketId);
    compareNotice =
      next === compareSelection && !compareSelection.includes(marketId)
        ? `Comparison holds ${MAX_COMPARE_LEGS} contracts; remove one first.`
        : "";
    if (next !== compareSelection) {
      onSetCompareSelection?.(next);
    }
  }

  function clearCompare() {
    compareNotice = "";
    onSetCompareSelection?.([]);
  }

  function saveCurrentSet() {
    const name = newSetName.trim();
    if (!name || compareSelection.length < 2 || !onSaveComparisonSet) return;
    void onSaveComparisonSet({ name, marketIds: compareSelection });
    newSetName = "";
  }

  function openSavedSet(record: PredictionComparisonSet) {
    onSetCompareSelection?.([...record.market_ids]);
  }

  async function runComparison() {
    if (!onCompare || compareSelection.length < 2) return;
    lastComparedKey = compareKey;
    await onCompare(compareSelection, { range: historyRange, resolutionMinutes: historyResolution });
  }

  async function runCalibration() {
    if (!calibrationMarketId || !onLoadCalibration) return;
    lastCalibrationKey = calibrationKey;
    await onLoadCalibration(calibrationMarketId, {
      leadTimes: calibrationLeadTimes,
      sampleSize: calibrationSample
    });
  }

  function applyCalibrationLeadTime(hours: number) {
    const next = toggleCalibrationLeadTime(calibrationLeadTimes, hours);
    if (next === calibrationLeadTimes) return;
    calibrationLeadTimes = next;
    activeLeadTime = next.includes(activeLeadTime ?? -1) ? activeLeadTime : next[0];
    void runCalibration();
  }

  function sendSelectedMarketToStrategyLab(open = false) {
    if (!detail || !onSendToStrategyLab) return;
    onSendToStrategyLab(buildPredictionMarketStrategyHandoff(detail, { defaultSide: strategySide }), { open });
  }

  function sendMarketRowToStrategyLab(market: PredictionMarket, open = false) {
    if (!onSendToStrategyLab) return;
    onSendToStrategyLab(
      buildPredictionMarketStrategyHandoff(market, { sourceMode: "screener", defaultSide: strategySide }),
      { open }
    );
  }

  function contextMenuPosition(event: MouseEvent | KeyboardEvent) {
    if (event instanceof MouseEvent && event.type === "contextmenu") {
      return { x: event.clientX, y: event.clientY };
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: rect.left + 12, y: rect.top + Math.min(rect.height, 32) };
  }

  function openMarketStrategyMenu(event: MouseEvent | KeyboardEvent, market: PredictionMarket) {
    event.preventDefault();
    void onSelectMarket(market.market_id);
    const position = contextMenuPosition(event);
    strategyContextMenu = { open: true, x: position.x, y: position.y, market };
  }

  function handleMarketRowKeydown(event: KeyboardEvent, market: PredictionMarket) {
    if (event.key === "Enter") {
      void openContract(market.market_id);
      return;
    }
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      openMarketStrategyMenu(event, market);
    }
  }

  function handleStrategyMenuSelect(action: string) {
    const market = strategyContextMenu.market;
    if (!market) return;
    if (action === "watch") {
      toggleWatch(market);
      return;
    }
    if (action === "compare") {
      toggleCompare(market.market_id);
      return;
    }
    sendMarketRowToStrategyLab(market, action === "add-open");
  }

  function closeStrategyMenu() {
    strategyContextMenu = { ...strategyContextMenu, open: false };
  }

  // ── Derived state ────────────────────────────────────────────

  let historyPoints = history?.points ?? [];
  let historyStats = history?.stats ?? null;
  let chartSeries: ChartSeries[] = [];
  let outcomeLadder: OutcomeLadderRow[] = [];
  let multiOutcome = false;
  let daysToResolution: number | null = null;
  let topWallet = wallet?.participants?.[0] ?? null;
  let biggestGap: RelatedPredictionMarketListResponse["related"][number] | null = null;
  let venueButtons: PredictionVenueStatus[] = [];
  interface CompareRow {
    market_id: string;
    venue: string;
    title: string;
    current_probability: number | null;
  }
  let compareRows: CompareRow[] = [];
  let comparisonSeries: ChartSeries[] = [];
  let spreadSeries: ChartSeries[] = [];
  let rankedPairs: PredictionMarketComparison["pairs"] = [];
  let compareKey = "";
  let hasWalletRows = false;
  interface DepthRow {
    index: number;
    bidPrice: number | null;
    bidNotional: number | null;
    askPrice: number | null;
    askNotional: number | null;
  }
  let depthLevels: DepthRow[] = [];
  let depthBackingLabel = "no depth";
  let eventBookFavorite: PredictionEventBookLeg | null = null;
  let eventBookFlagged = 0;
  let eventBookQuoted = 0;
  let lastEventBookMarketId = "";
  let calibrationMarketId: string | null = null;
  let activeLeadTime: number | null = null;
  let activeCurve: PredictionCalibrationCurve | null = null;
  let calibrationRows: CalibrationBucketRow[] = [];
  let calibrationKey = "";
  let lastCalibrationKey = "";

  const fallbackVenueStatus = (venue: VenueKey): PredictionVenueStatus => ({
    venue,
    status: "unknown",
    message: null,
    total_markets: 0,
    matched_markets: 0,
    visible_markets: 0,
    stale_markets: 0,
    broken_markets: 0,
    retrieved_at: null
  });

  $: historyPoints = history?.points ?? [];
  $: historyStats = history?.stats ?? null;
  $: outcomeLadder = buildOutcomeLadder(outcomeSeries?.series ?? []);
  $: multiOutcome = outcomeLadder.filter((row) => row.hasHistory).length > 2;

  $: chartSeries = (() => {
    const series: ChartSeries[] = [];
    if (historyPoints.length) {
      series.push({
        id: "probability",
        label: history?.outcome_label ?? detail?.probability_label ?? "Probability",
        color: "var(--chart-primary)",
        type: multiOutcome && showOutcomeOverlay ? "line" : "area",
        data: historyPoints
          .map((point) => ({
            time: parseApiTimestampToUtcSeconds(point.timestamp),
            value: point.probability
          }))
          .filter((point): point is { time: number; value: number } => point.time != null)
      });
    }
    if (multiOutcome && showOutcomeOverlay) {
      const overlays = (outcomeSeries?.series ?? []).filter(
        (item) => item.points.length && item.outcome_id !== history?.outcome_id
      );
      overlays.forEach((item, index) => {
        series.push({
          id: `outcome-${item.outcome_id}`,
          label: item.label,
          color: comparisonColor(index + 1),
          type: "line",
          data: item.points
            .map((point) => ({
              time: parseApiTimestampToUtcSeconds(point.timestamp),
              value: point.probability
            }))
            .filter((point): point is { time: number; value: number } => point.time != null)
        });
      });
    }
    return series;
  })();

  $: daysToResolution = daysUntil(detail?.end_time);
  $: topWallet = wallet?.participants?.[0] ?? null;
  $: biggestGap =
    related?.related?.slice().sort((left, right) => (right.price_gap ?? -1) - (left.price_gap ?? -1))[0] ?? null;
  $: hasWalletRows = Boolean(wallet?.participants?.length);
  $: watchlist = savedResearch?.watchlist ?? [];
  // The working basket is stored as a reserved set so it survives a browser
  // change; it is not a research set the user named and should not be listed.
  $: namedSets = (savedResearch?.comparison_sets ?? []).filter(
    (record) => record.name !== PREDICTION_WORKING_BASKET_NAME
  );

  $: depthLevels = Array.from(
    { length: Math.min(Math.max(depth?.bids.length ?? 0, depth?.asks.length ?? 0), 12) },
    (_, index) => ({
      index,
      bidPrice: depth?.bids[index]?.price ?? null,
      bidNotional: depth?.bids[index]?.notional ?? null,
      askPrice: depth?.asks[index]?.price ?? null,
      askNotional: depth?.asks[index]?.notional ?? null
    })
  );
  // The spread KPI states what backs it: the same width means different things
  // at $2k of resting size and at $200k.
  $: depthBackingLabel = (() => {
    const near = (depth?.bid_notional_within_band ?? 0) + (depth?.ask_notional_within_band ?? 0);
    if (!depth || (!depth.bids.length && !depth.asks.length)) return "no resting depth";
    return `${fmt(near, 0)} within ${pct(depth.depth_band, 0)}`;
  })();

  $: eventBookFavorite =
    eventBook?.legs.find((leg) => leg.market_id === eventBook?.favorite_market_id) ?? eventBook?.legs[0] ?? null;
  $: eventBookFlagged = eventBook?.legs.filter((leg) => leg.divergence_flags.length).length ?? 0;
  // A venue lists empty candidate slots inside a race. They belong in the sum
  // (they contribute zero) but should not read as live quotes.
  $: eventBookQuoted = eventBook?.legs.filter((leg) => (leg.liquidity ?? 0) || (leg.volume ?? 0)).length ?? 0;
  $: if (mode === "contract" && detail?.market_id && onLoadEventBook && detail.market_id !== lastEventBookMarketId) {
    lastEventBookMarketId = detail.market_id;
    void onLoadEventBook(detail.market_id);
  }

  // Calibration is venue-level but the route is addressed by contract, so fall
  // back to the first screened row when nothing is open yet.
  $: calibrationMarketId = detail?.market_id ?? screener?.markets?.[0]?.market_id ?? null;
  $: calibrationComposition =
    Object.entries(calibration?.sample_categories ?? {})
      .slice(0, 2)
      .map(([label, count]) => `${label} ${count}`)
      .join(" | ") || "—";
  // Observations follow the drawn curve, which is not always the selected one.
  $: observationLeadLabel = calibration?.observations?.length
    ? `${leadTimeLabel(calibration.observations[0].lead_time_hours)} | `
    : "";
  $: activeCurve = calibrationCurveFor(calibration, activeLeadTime);
  $: calibrationRows = buildCalibrationRows(activeCurve);
  $: calibrationKey = JSON.stringify({
    venue: calibrationMarketId?.split(":")[0] ?? "",
    leads: calibrationLeadTimes,
    sample: calibrationSample
  });
  $: if (mode === "calibration" && calibrationMarketId && onLoadCalibration && calibrationKey !== lastCalibrationKey) {
    lastCalibrationKey = calibrationKey;
    void onLoadCalibration(calibrationMarketId, {
      leadTimes: calibrationLeadTimes,
      sampleSize: calibrationSample
    });
  }

  $: if (screener?.venues?.length) {
    const next = { ...cachedVenueStatuses };
    let changed = false;
    for (const venue of screener.venues) {
      if (venue.venue === "polymarket" || venue.venue === "kalshi") {
        if (next[venue.venue] !== venue) {
          next[venue.venue] = venue;
          changed = true;
        }
      }
    }
    if (changed) cachedVenueStatuses = next;
  }
  $: venueButtons = allVenues.map((venue) => cachedVenueStatuses[venue] ?? fallbackVenueStatus(venue));

  $: currentScreenerKey = JSON.stringify({
    query: query.trim(),
    status,
    sortBy,
    category,
    venues: [...venueSelection].sort(),
    minVolume,
    minLiquidity,
    minProbability,
    maxProbability,
    maxDaysToResolution,
    minRepricingAbs,
    screenerLimit
  });
  $: if (autoRunReady && currentScreenerKey) scheduleAutoRun();

  // Contracts in the basket may come from the screener, the watchlist, or a
  // previous session, so resolve labels from whatever is currently loaded.
  $: compareRows = compareSelection.map((marketId) => {
    const known =
      screener?.markets.find((market) => market.market_id === marketId) ??
      (detail?.market_id === marketId ? detail : null);
    if (known) {
      return {
        market_id: known.market_id,
        venue: known.venue,
        title: known.title,
        current_probability: known.current_probability
      };
    }
    const watched = watchlist.find((entry) => entry.market_id === marketId);
    const leg = comparison?.legs.find((item) => item.market_id === marketId);
    return {
      market_id: marketId,
      venue: watched?.venue ?? leg?.venue ?? "",
      title: watched?.title ?? leg?.title ?? marketId,
      current_probability: watched?.probability ?? leg?.current_probability ?? null
    };
  });

  $: comparisonSeries = (comparison?.legs ?? []).map((leg, index) => ({
    id: leg.market_id,
    label: `${leg.venue === "polymarket" ? "PM" : "KL"} ${truncName(leg.title, 34)}`,
    color: comparisonColor(index),
    type: "line" as const,
    data: leg.points
      .map((point) => ({
        time: parseApiTimestampToUtcSeconds(point.timestamp),
        value: point.probability
      }))
      .filter((point): point is { time: number; value: number } => point.time != null)
  }));

  $: rankedPairs = sortPairsByDislocation(comparison?.pairs ?? []);

  $: spreadSeries = (() => {
    const pair = rankedPairs[0];
    if (!pair?.spread_series?.length) return [];
    return [
      {
        id: "spread",
        label: "Spread",
        color: "var(--chart-secondary)",
        type: "area" as const,
        data: pair.spread_series
          .map((point) => ({
            time: parseApiTimestampToUtcSeconds(point.timestamp),
            value: point.spread
          }))
          .filter((point): point is { time: number; value: number } => point.time != null)
      }
    ];
  })();

  $: compareKey = JSON.stringify({ ids: compareSelection, historyRange, historyResolution });
  $: if (mode === "compare" && compareSelection.length >= 2 && compareKey !== lastComparedKey && onCompare) {
    lastComparedKey = compareKey;
    void onCompare(compareSelection, { range: historyRange, resolutionMinutes: historyResolution });
  }
</script>

<svelte:window on:keydown={handleContractKeydown} />

<section class="view">
  <div class="mode-row">
    <div class="mode-bar" role="tablist" aria-label="Prediction Markets modes">
      {#each modes as item}
        <button
          type="button"
          role="tab"
          aria-selected={mode === item.id}
          class:selected={mode === item.id}
          on:click={() => selectMode(item.id)}
        >
          {item.label}
        </button>
      {/each}
    </div>
    <div class="mode-meta">
      <span>{screener?.markets.length ?? 0} contracts</span>
      <span>{watchlist.length} watched</span>
      <span>{compareSelection.length}/{MAX_COMPARE_LEGS} in compare</span>
      {#if loading || historyLoading || compareLoading}<span class="loading-flag">LOADING...</span>{/if}
    </div>
  </div>

  {#if mode === "screener"}
    <div class="screener-grid">
      <article class="panel filter-panel">
        <div class="filter-row">
          <label class="grow">
            <span>Search</span>
            <input bind:value={query} placeholder="Fed, election, inflation, semis..." on:keydown={handleSearchKeydown} />
          </label>
          <label>
            <span>Status</span>
            <select bind:value={status}>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select bind:value={sortBy}>
              <option value="research_rank">Research Rank</option>
              <option value="volume_desc">Volume</option>
              <option value="liquidity_desc">Liquidity</option>
              <option value="open_interest_desc">Open Interest</option>
              <option value="repricing_desc">Repricing</option>
              <option value="resolution_soon">Resolution</option>
            </select>
          </label>
          <label>
            <span>Category</span>
            <select bind:value={category}>
              <option value="">All</option>
              {#each availableCategories as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>
            <span>Rows</span>
            <select bind:value={screenerLimit}>
              <option value={20}>20</option>
              <option value={40}>40</option>
              <option value={60}>60</option>
              <option value={100}>100</option>
            </select>
          </label>
        </div>

        <div class="filter-row">
          <label>
            <span>Min Vol</span>
            <input type="number" min="0" step="1000" bind:value={minVolume} placeholder="0" />
          </label>
          <label>
            <span>Min Liq</span>
            <input type="number" min="0" step="1000" bind:value={minLiquidity} placeholder="0" />
          </label>
          <label>
            <span>Prob %</span>
            <input type="number" min="0" max="100" bind:value={minProbability} placeholder="min" />
          </label>
          <label>
            <span>To %</span>
            <input type="number" min="0" max="100" bind:value={maxProbability} placeholder="max" />
          </label>
          <label>
            <span>Max Days</span>
            <input type="number" min="0" bind:value={maxDaysToResolution} placeholder="any" />
          </label>
          <label>
            <span>Min Δ %</span>
            <input type="number" min="0" max="100" bind:value={minRepricingAbs} placeholder="0" />
          </label>
          <div class="venue-picker">
            {#each venueButtons as venue}
              <button
                type="button"
                class="{venueSelection.includes(venue.venue as VenueKey) ? 'selected' : ''} {venueSelection.includes(
                  venue.venue as VenueKey
                )
                  ? venueTone(venue.status)
                  : ''}"
                on:click={() => toggleVenue(venue.venue as VenueKey)}
              >
                <strong>{venue.venue === "polymarket" ? "PM" : "KL"}</strong>
                <small>{venue.visible_markets ?? 0}</small>
              </button>
            {/each}
          </div>
          <div class="filter-actions">
            <button type="button" class="ghost-button" on:click={resetFilters}>Reset</button>
            <button type="button" on:click={() => runScreener(true)} disabled={loading}>Refresh</button>
          </div>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="table-scroll tall">
          <table class="screener-table">
            <thead>
              <tr>
                <th class="tick-col" title="Add to comparison">CMP</th>
                <th class="tick-col" title="Watchlist">★</th>
                <th>Market</th>
                <th class="num">Prob</th>
                <th class="num">Δ24H</th>
                <th class="num">Vol 24H</th>
                <th class="num">Volume</th>
                <th class="num">Liquidity</th>
                <th class="num">OI</th>
                <th class="num">Spread</th>
                <th class="num">Res</th>
                <th>Venue</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {#if screener?.markets?.length}
                {#each screener.markets as market (market.market_id)}
                  <tr
                    tabindex="0"
                    aria-label={`Actions for ${market.title}`}
                    class:selected={market.market_id === detail?.market_id}
                    on:click={() => openContract(market.market_id)}
                    on:contextmenu={(event) => openMarketStrategyMenu(event, market)}
                    on:keydown={(event) => handleMarketRowKeydown(event, market)}
                  >
                    <td class="tick-col">
                      <button
                        type="button"
                        class="tick"
                        class:on={compareSelection.includes(market.market_id)}
                        aria-label="Toggle comparison"
                        on:click|stopPropagation={() => toggleCompare(market.market_id)}
                      >
                        {compareSelection.includes(market.market_id) ? "◼" : "◻"}
                      </button>
                    </td>
                    <td class="tick-col">
                      <button
                        type="button"
                        class="tick"
                        class:on={isWatched(market.market_id)}
                        aria-label="Toggle watchlist"
                        on:click|stopPropagation={() => toggleWatch(market)}
                      >
                        {isWatched(market.market_id) ? "★" : "☆"}
                      </button>
                    </td>
                    <td>
                      <div class="market-title">
                        <strong>{market.title}</strong>
                        <small>
                          {market.event_title ?? market.category ?? "Uncategorized"}
                          {#if market.research_score != null}| rank {market.research_score.toFixed(0)}{/if}
                        </small>
                      </div>
                    </td>
                    <td class="num"
                      ><span class={marketTone(market.current_probability)}>{pct(market.current_probability)}</span></td
                    >
                    <td class="num {toneOf(market.recent_price_change)}"
                      ><span
                        use:flashOnChange={{
                          value: market.recent_price_change,
                          direction: directionOf(market.recent_price_change)
                        }}>{signedPct(market.recent_price_change)}</span
                      ></td
                    >
                    <td class="num">{fmt(market.volume_24h)}</td>
                    <td class="num">{fmt(market.volume)}</td>
                    <td class="num">{fmt(market.liquidity)}</td>
                    <td class="num">{fmt(market.open_interest)}</td>
                    <td class="num">{pct(market.spread, 1)}</td>
                    <td class="num">{daysLabel(daysUntil(market.end_time))}</td>
                    <td><span class="venue-label">{market.venue === "polymarket" ? "PM" : "KL"}</span></td>
                    <td
                      ><span class={`tag-chip compact-chip ${freshnessTone(market.freshness?.status)}`}
                        >{market.freshness?.status ?? "N/A"}</span
                      ></td
                    >
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="13" class="empty-row">{loading ? "LOADING..." : "No markets matched."}</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <div class="screener-foot">
        <article class="panel table-panel">
          <div class="table-header">
            <span>Watchlist</span>
            <small>{watchlist.length}/{savedResearch?.watchlist_limit ?? 0} saved{savedLoading ? " | SAVING..." : ""}</small>
          </div>
          {#if watchlist.length}
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th class="num">Prob</th>
                  <th>Venue</th>
                  <th class="tick-col">CMP</th>
                </tr>
              </thead>
              <tbody>
                {#each watchlist as entry (entry.market_id)}
                  <tr class="clickable-row" on:click={() => openContract(entry.market_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => openContract(entry.market_id))}>
                    <td class="wrap-cell"><strong>{truncName(entry.title, 46)}</strong></td>
                    <td class="num">{pct(entry.probability)}</td>
                    <td><span class="venue-label">{entry.venue === "polymarket" ? "PM" : "KL"}</span></td>
                    <td class="tick-col">
                      <button
                        type="button"
                        class="tick"
                        class:on={compareSelection.includes(entry.market_id)}
                        aria-label="Toggle comparison"
                        on:click|stopPropagation={() => toggleCompare(entry.market_id)}
                      >
                        {compareSelection.includes(entry.market_id) ? "◼" : "◻"}
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">Star a contract to keep it on the server across browsers.</p>
          {/if}
          {#if savedResearch?.warnings?.length}
            <div class="panel-notes">
              {#each savedResearch.warnings as warning}
                <div class="note-row"><span class="note-tag">Saved</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <span>Venue Status</span>
            <small>{screener?.warnings?.length ?? 0} notes</small>
          </div>
          <table>
            <thead>
              <tr>
                <th>Venue</th>
                <th>State</th>
                <th class="num">Total</th>
                <th class="num">Shown</th>
                <th class="num">Stale</th>
                <th class="num">Broken</th>
              </tr>
            </thead>
            <tbody>
              {#each venueButtons as venue}
                <tr>
                  <td>{venue.venue}</td>
                  <td><span class={venueTone(venue.status)}>{venue.status}</span></td>
                  <td class="num">{venue.total_markets}</td>
                  <td class="num">{venue.visible_markets}</td>
                  <td class="num {venue.stale_markets > 0 ? 'elevated' : ''}">{venue.stale_markets}</td>
                  <td class="num {venue.broken_markets > 0 ? 'negative' : ''}">{venue.broken_markets}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if screener?.warnings?.length}
            <div class="panel-notes">
              {#each screener.warnings as warning}
                <div class="note-row"><span class="note-tag">Note</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>
      </div>
    </div>
  {:else if mode === "contract"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel chart-panel">
          <div class="panel-header top-line">
            <div class="title-block">
              <p class="eyebrow">{detail?.event_title ?? "Prediction Markets"}</p>
              <h2>{detail?.title ?? "Select a market"}</h2>
            </div>
            {#if detail}
              <div class="badge-stack">
                <span>{detail.venue}</span>
                <span>{detail.status}</span>
                <span class={freshnessTone(detail.freshness?.status)}>{detail.freshness?.status ?? "unknown"}</span>
                <span>{detail.category ?? "Research"}</span>
              </div>
            {/if}
          </div>

          <div class="control-row">
            <div class="segmented" role="group" aria-label="History range">
              {#each HISTORY_RANGES as range}
                <button
                  type="button"
                  class:selected={historyRange === range.id}
                  disabled={!detail || historyLoading}
                  on:click={() => applyRange(range.id)}
                >
                  {range.label}
                </button>
              {/each}
            </div>
            <div class="segmented" role="group" aria-label="Bar resolution">
              {#each RESOLUTION_CHOICES as choice}
                <button
                  type="button"
                  class:selected={historyResolution === choice.id}
                  disabled={!detail || historyLoading}
                  on:click={() => applyResolution(choice.id)}
                >
                  {choice.label}
                </button>
              {/each}
            </div>
            {#if multiOutcome}
              <button
                type="button"
                class="ghost-button auto"
                class:selected={showOutcomeOverlay}
                on:click={() => (showOutcomeOverlay = !showOutcomeOverlay)}
              >
                {showOutcomeOverlay ? "Outcomes on" : "Outcomes off"}
              </button>
            {/if}
            <div class="nav-actions">
              <button type="button" class="ghost-button auto" on:click={() => stepContract(-1)} title="Previous ([)"
                >←</button
              >
              <button type="button" class="ghost-button auto" on:click={() => stepContract(1)} title="Next (])">→</button>
              <button
                type="button"
                class="ghost-button auto"
                class:selected={isWatched(detail?.market_id)}
                disabled={!detail}
                on:click={() => detail && toggleWatch(detail)}>{isWatched(detail?.market_id) ? "★" : "☆"}</button
              >
              <button
                type="button"
                class="ghost-button auto"
                class:selected={detail ? compareSelection.includes(detail.market_id) : false}
                disabled={!detail}
                on:click={() => detail && toggleCompare(detail.market_id)}>Compare</button
              >
            </div>
          </div>

          <div class="kpi-grid">
            <article class="metric">
              <span>Prob</span>
              <strong
                class={marketTone(detail?.current_probability)}
                use:flashOnChange={{
                  value: detail?.current_probability,
                  direction: directionOf(detail?.recent_price_change)
                }}>{pct(detail?.current_probability)}</strong
              >
              <small>{history?.outcome_label ?? detail?.probability_label ?? "Primary outcome"}</small>
            </article>
            <article class="metric">
              <span>Window Δ</span>
              <strong class={toneOf(historyStats?.change)}>{signedPct(historyStats?.change)}</strong>
              <small>{historyRange.toUpperCase()} range {pct(historyStats?.range_width)}</small>
            </article>
            <article class="metric">
              <span>Hi / Lo</span>
              <strong>{pct(historyStats?.high)} / {pct(historyStats?.low)}</strong>
              <small>now at {pct(historyStats?.percentile_of_range)} of range</small>
            </article>
            <article class="metric">
              <span>Daily Vol</span>
              <strong class={(historyStats?.daily_volatility ?? 0) >= 0.08 ? "elevated" : ""}
                >{pct(historyStats?.daily_volatility)}</strong
              >
              <small>max move {signedPct(historyStats?.max_move)}</small>
            </article>
            <article class="metric">
              <span>24H Vol</span>
              <strong use:flashOnChange={{ value: detail?.volume_24h, direction: "neutral" }}
                >{fmt(detail?.volume_24h)}</strong
              >
              <small>total {fmt(detail?.volume)}</small>
            </article>
            <article class="metric">
              <span>Liquidity</span>
              <strong>{fmt(detail?.liquidity)}</strong>
              <small>{(detail?.open_interest ?? 0) > 0 ? `OI ${fmt(detail?.open_interest)}` : "—"}</small>
            </article>
            <article class="metric">
              <span>Resolves</span>
              <strong>{daysLabel(daysToResolution)}</strong>
              <small>{dayStamp(detail?.end_time)}</small>
            </article>
            <article class="metric">
              <span>Spread</span>
              <strong class={(depth?.spread ?? detail?.spread ?? 0) >= 0.05 ? "elevated" : ""}
                >{pct(depth?.spread ?? detail?.spread, 1)}</strong
              >
              <small>{depthBackingLabel}</small>
            </article>
          </div>

          <TimeSeriesChart
            series={chartSeries}
            height={360}
            showLegend={chartSeries.length > 1}
            emptyMessage={historyLoading ? "LOADING..." : "Select a market to load probability history."}
          />

          <div class="chart-foot">
            <strong>{describeHistoryCoverage(history)}</strong>
            <small>
              {history?.coverage_start ? `${dayStamp(history.coverage_start)} → ${dayStamp(history.coverage_end)}` : "—"}
              {#if history?.windowing && history.windowing !== "provider_window"}| {history.windowing}{/if}
              | {history?.source_provider ?? detail?.source_provider ?? "N/A"}
            </small>
          </div>

          {#if history?.warnings?.length}
            <div class="notes-list">
              {#each history.warnings as warning}
                <div class="note-row"><span class="note-tag">History</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>

        {#if outcomeLadder.length > 1}
          <article class="panel table-panel">
            <div class="table-header">
              <span>Outcome Ladder</span>
              <small>{outcomeLadder.length} outcomes</small>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Outcome</th>
                  <th class="num">Prob</th>
                  <th class="num">Window Δ</th>
                  <th class="num">Points</th>
                  <th>Charted</th>
                </tr>
              </thead>
              <tbody>
                {#each outcomeLadder as row (row.outcome_id)}
                  <tr
                    class="clickable-row"
                    class:selected={history?.outcome_id === row.outcome_id}
                    tabindex="0"
                    on:click={() => row.hasHistory && selectOutcome(row.outcome_id)}
                    on:keydown={(event) => activateRowOnKey(event, () => row.hasHistory && selectOutcome(row.outcome_id))}
                  >
                    <td class="wrap-cell"><strong>{row.label}</strong></td>
                    <td class="num">{pct(row.probability)}</td>
                    <td class="num {toneOf(row.change)}">{signedPct(row.change)}</td>
                    <td class="num">{row.points}</td>
                    <td>
                      {#if !row.hasHistory}
                        <span class="muted">no series</span>
                      {:else if history?.outcome_id === row.outcome_id}
                        <span class="fresh">primary</span>
                      {:else}
                        <span class="muted">overlay</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </article>
        {/if}

        {#if eventBook && eventBook.legs.length > 1}
          <article class="panel table-panel">
            <div class="table-header">
              <span>Event Book</span>
              <small>
                {eventBook.legs.length} legs |
                <span class={completenessTone(eventBook.completeness?.status)}
                  >{eventBook.completeness?.status ?? "unknown"}</span
                >
              </small>
            </div>
            <div class="kpi-strip">
              <article class="metric">
                <span>Book Sum</span>
                <strong class={eventBook.overround_is_meaningful ? "" : "muted"}>{pct(eventBook.probability_sum)}</strong>
                <small>{eventBookQuoted}/{eventBook.legs.length} quoted</small>
              </article>
              <article class="metric">
                <span>{eventBook.overround_is_meaningful ? "Overround" : "Vs 100%"}</span>
                <strong class={eventBook.overround_is_meaningful ? toneOf(eventBook.implied_overround) : "muted"}
                  >{signedPct(eventBook.implied_overround)}</strong
                >
                <small>{eventBook.overround_is_meaningful ? "book-complete check" : "descriptive only"}</small>
              </article>
              <article class="metric">
                <span>Favorite</span>
                <strong>{truncName(eventBookFavorite?.subtitle ?? eventBookFavorite?.title, 20)}</strong>
                <small>{pct(eventBookFavorite?.probability)}</small>
              </article>
              <article class="metric">
                <span>Flagged</span>
                <strong class={eventBookFlagged > 0 ? "elevated" : ""}>{eventBookFlagged}</strong>
                <small>{eventBook.exclusivity_signal === "venue_grouped_candidates" ? "venue candidates" : "unverified"}</small>
              </article>
            </div>
            <div class="table-scroll tall">
              <table>
                <thead>
                  <tr>
                    <th>Contract</th>
                    <th class="num">Prob</th>
                    <th class="num">Bid</th>
                    <th class="num">Ask</th>
                    <th class="num">Spread</th>
                    <th class="num">Liquidity</th>
                    <th class="num">Volume</th>
                    <th>Terms</th>
                  </tr>
                </thead>
                <tbody>
                  {#each eventBook.legs as leg (leg.market_id)}
                    {@const unquoted = !(leg.liquidity ?? 0) && !(leg.volume ?? 0)}
                    <tr
                      class="clickable-row"
                      class:selected={leg.is_anchor}
                      tabindex="0"
                      on:click={() => onSelectMarket(leg.market_id)}
                      on:keydown={(event) => activateRowOnKey(event, () => onSelectMarket(leg.market_id))}
                    >
                      <td class="wrap-cell">
                        <strong>{truncName(leg.subtitle ?? leg.title, 44)}</strong>
                        {#if leg.divergence_flags.length}<small>{leg.divergence_flags[0]}</small>{/if}
                      </td>
                      <td class="num"><span class={marketTone(leg.probability)}>{pct(leg.probability)}</span></td>
                      <td class="num">{pct(leg.best_bid)}</td>
                      <td class="num">{unquoted ? "N/A" : pct(leg.best_ask)}</td>
                      <td class="num {!unquoted && (leg.spread ?? 0) >= 0.05 ? 'elevated' : ''}"
                        >{unquoted ? "N/A" : pct(leg.spread)}</td
                      >
                      <td class="num">{fmt(leg.liquidity)}</td>
                      <td class="num">{fmt(leg.volume)}</td>
                      <td>
                        {#if leg.divergence_flags.length}
                          <span class="stale">differs</span>
                        {:else if unquoted}
                          <span class="muted">unquoted</span>
                        {:else}
                          <span class="muted">aligned</span>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            {#if eventBook.warnings.length || eventBook.completeness?.note}
              <div class="panel-notes">
                {#each eventBook.warnings as warning}
                  <div class="note-row"><span class="note-tag">Warning</span><p>{warning}</p></div>
                {/each}
                {#if eventBook.completeness?.note}
                  <div class="note-row info"><span class="note-tag">Coverage</span><p>{eventBook.completeness.note}</p></div>
                {/if}
              </div>
            {/if}
          </article>
        {/if}

        <article class="panel table-panel">
          <div class="table-header">
            <span>Participant Flow</span>
            <small>{wallet?.participants.length ?? 0} rows</small>
          </div>
          {#if hasWalletRows}
            <div class="kpi-strip">
              <article class="metric">
                <span>Trades</span>
                <strong>{wallet?.total_trades ?? 0}</strong>
              </article>
              <article class="metric">
                <span>Notional</span>
                <strong>{fmt(wallet?.total_notional, 2)}</strong>
              </article>
              <article class="metric">
                <span>Top Share</span>
                <strong class={(wallet?.top_participant_share ?? 0) >= 0.45 ? "elevated" : ""}
                  >{pct(wallet?.top_participant_share)}</strong
                >
              </article>
              <article class="metric">
                <span>HHI</span>
                <strong class={(wallet?.concentration_hhi ?? 0) >= 0.25 ? "elevated" : ""}
                  >{wallet?.concentration_hhi?.toFixed(2) ?? "N/A"}</strong
                >
              </article>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Participant</th>
                  <th>Side</th>
                  <th class="num">Trades</th>
                  <th class="num">Size</th>
                  <th class="num">Avg Price</th>
                  <th class="num">Edge</th>
                </tr>
              </thead>
              <tbody>
                {#each wallet?.participants ?? [] as participant}
                  <tr>
                    <td class="wrap-cell">
                      <strong title={participant.display_name}>{truncName(participant.display_name, 22)}</strong>
                      <small>{participant.outcome_label ?? participant.side}</small>
                    </td>
                    <td class={participant.side === "buy" ? "positive" : participant.side === "sell" ? "negative" : ""}
                      >{participant.side}</td
                    >
                    <td class="num">{participant.trade_count}</td>
                    <td class="num">{fmt(participant.total_size, 2)}</td>
                    <td class="num">{pct(participant.average_price)}</td>
                    <td class="num {toneOf(participant.current_edge)}">{signedPct(participant.current_edge)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">No flow data for this contract.</p>
          {/if}
          {#if wallet?.warnings?.length}
            <div class="panel-notes">
              {#each wallet.warnings as warning}
                <div class="note-row"><span class="note-tag">Warning</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>
      </div>

      <aside class="support-column">
        <article class="panel control-panel">
          <div class="panel-header">
            <span class="eyebrow">Strategy Handoff</span>
          </div>
          <div class="strategy-actions">
            <div class="side-toggle" aria-label="Strategy Lab contract side">
              <button type="button" class:selected={strategySide === "long_yes"} on:click={() => (strategySide = "long_yes")}
                >YES</button
              >
              <button type="button" class:selected={strategySide === "long_no"} on:click={() => (strategySide = "long_no")}
                >NO</button
              >
            </div>
            <button type="button" class="ghost-button" disabled={!detail} on:click={() => sendSelectedMarketToStrategyLab(false)}
              >+ Strategy</button
            >
            <button type="button" disabled={!detail} on:click={() => sendSelectedMarketToStrategyLab(true)}
              >Add &amp; Open</button
            >
          </div>
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <span>Send To</span>
            <small>{crossDomainHandoffs.length} resolved targets</small>
          </div>
          {#if crossDomainHandoffs.length}
            <table>
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Entity</th>
                  <th>Lens</th>
                  <th class="tick-col"></th>
                </tr>
              </thead>
              <tbody>
                {#each crossDomainHandoffs as handoff (handoff.intended_target_tab + (handoff.selected_entity?.normalized_id ?? ""))}
                  <tr class="clickable-row" on:click={() => onCrossDomainHandoff?.(handoff)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => onCrossDomainHandoff?.(handoff))}>
                    <td>
                      <strong>{handoffTabLabel(handoff.intended_target_tab)}</strong>
                    </td>
                    <td class="wrap-cell">
                      <strong>{truncName(handoff.selected_entity?.label, 26)}</strong>
                      {#if handoff.warnings.length}<small>{handoff.warnings[0]}</small>{/if}
                    </td>
                    <td>{handoff.intended_target_mode ?? "default"}</td>
                    <td class="tick-col">
                      <button
                        type="button"
                        class="tick"
                        aria-label={`Open in ${handoffTabLabel(handoff.intended_target_tab)}`}
                        disabled={!onCrossDomainHandoff}
                        on:click|stopPropagation={() => onCrossDomainHandoff?.(handoff)}>→</button
                      >
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">No cross-domain target resolves from this contract's text.</p>
          {/if}
        </article>

        <article class="panel composition-panel">
          <div class="panel-header"><span class="eyebrow">Metadata</span></div>
          <div class="meta-flat">
            <div class="meta-row"><span>Market ID</span><code>{compactId(detail?.market_id)}</code></div>
            <div class="meta-row"><span>Venue ID</span><code>{compactId(detail?.provider_market_id)}</code></div>
            <div class="meta-row">
              <span>Series</span>
              <strong>{detail?.series_title ?? "N/A"}</strong>
            </div>
            <div class="meta-row"><span>Resolution</span><strong>{shortDate(detail?.end_time)}</strong></div>
            <div class="meta-row"><span>Opened</span><strong>{dayStamp(detail?.open_time)}</strong></div>
            <div class="meta-row"><span>Retrieved</span><strong>{shortDate(detail?.retrieved_at)}</strong></div>
            <div class="meta-row"><span>Origin</span><small>{detail?.origin ?? "N/A"}</small></div>
            {#if detail?.resolution_source}
              <div class="meta-row"><span>Res. Source</span><small>{detail.resolution_source}</small></div>
            {/if}
            {#if detail?.tags?.length}
              <div class="meta-row">
                <span>Tags</span>
                <div class="tag-list">
                  {#each detail.tags as tag}<span class="tag-chip">{tag}</span>{/each}
                </div>
              </div>
            {/if}
          </div>
          {#if detail?.description}
            <div class="description-box">
              <small class="group-label">Resolution Text</small>
              <p>{detail.description}</p>
            </div>
          {/if}
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <span>Book Depth</span>
            <small>read-only | ±{pct(depth?.depth_band ?? 0.05, 0)} band</small>
          </div>
          {#if depthLevels.length}
            <div class="kpi-strip">
              <article class="metric">
                <span>Bid Depth</span>
                <strong>{fmt(depth?.bid_notional_within_band, 0)}</strong>
                <small>total {fmt(depth?.total_bid_notional, 0)}</small>
              </article>
              <article class="metric">
                <span>Ask Depth</span>
                <strong>{fmt(depth?.ask_notional_within_band, 0)}</strong>
                <small>total {fmt(depth?.total_ask_notional, 0)}</small>
              </article>
              <article class="metric">
                <span>Imbalance</span>
                <strong class={toneOf(depth?.depth_imbalance)}>{signedPct(depth?.depth_imbalance, 0)}</strong>
                <small>bid vs ask</small>
              </article>
              <article class="metric">
                <span>{fmt(depth?.reference_clip_notional, 0)} Cost</span>
                <strong class={depth?.ask_slippage_reference == null ? "stale" : "elevated"}
                  >{depth?.ask_slippage_reference == null ? "N/A" : signedPct(depth.ask_slippage_reference, 2)}</strong
                >
                <small
                  >{depth?.bid_slippage_reference == null
                    ? "sell N/A"
                    : `sell ${signedPct(depth.bid_slippage_reference, 2)}`}</small
                >
              </article>
            </div>
            <table>
              <thead>
                <tr>
                  <th class="num">Bid Size</th>
                  <th class="num">Bid</th>
                  <th class="num">Ask</th>
                  <th class="num">Ask Size</th>
                </tr>
              </thead>
              <tbody>
                {#each depthLevels as level (level.index)}
                  <tr>
                    <td class="num">{fmt(level.bidNotional, 0)}</td>
                    <td class="num positive">{pct(level.bidPrice, 1)}</td>
                    <td class="num negative">{pct(level.askPrice, 1)}</td>
                    <td class="num">{fmt(level.askNotional, 0)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">{loading ? "LOADING..." : "No resting depth returned for this contract."}</p>
          {/if}
          {#if depth?.warnings?.length}
            <div class="panel-notes">
              {#each depth.warnings as warning}
                <div class="note-row"><span class="note-tag">Depth</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <span>Related</span>
            <small>{related?.related.length ?? 0} links</small>
          </div>
          {#if related?.related?.length}
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th class="num">Prob</th>
                  <th class="num">Gap</th>
                  <th class="tick-col">CMP</th>
                </tr>
              </thead>
              <tbody>
                {#each related.related as market (market.market_id)}
                  <tr class="clickable-row" on:click={() => onSelectMarket(market.market_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => onSelectMarket(market.market_id))}>
                    <td class="wrap-cell">
                      <strong>{truncName(market.title, 40)}</strong>
                      <small>{market.relationship} | {market.venue}</small>
                    </td>
                    <td class="num">{pct(market.probability)}</td>
                    <td class="num {(market.price_gap ?? 0) >= 0.1 ? 'elevated' : ''}">{pct(market.price_gap)}</td>
                    <td class="tick-col">
                      <button
                        type="button"
                        class="tick"
                        class:on={compareSelection.includes(market.market_id)}
                        aria-label="Toggle comparison"
                        on:click|stopPropagation={() => toggleCompare(market.market_id)}
                      >
                        {compareSelection.includes(market.market_id) ? "◼" : "◻"}
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">No linked markets.</p>
          {/if}
        </article>
      </aside>
    </div>
  {:else if mode === "compare"}
    <div class="compare-grid">
      <article class="panel table-panel">
        <div class="table-header">
          <span>Comparison Basket</span>
          <div class="header-actions">
            <button type="button" class="ghost-button auto" on:click={clearCompare} disabled={!compareSelection.length}
              >Clear</button
            >
            <button
              type="button"
              class="auto"
              on:click={runComparison}
              disabled={compareSelection.length < 2 || compareLoading}>Recompute</button
            >
          </div>
        </div>
        {#if compareRows.length}
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>Venue</th>
                <th class="num">Prob</th>
                <th class="num">Window Δ</th>
                <th class="num">Points</th>
                <th class="tick-col"></th>
              </tr>
            </thead>
            <tbody>
              {#each compareRows as row, index (row.market_id)}
                {@const leg = comparison?.legs.find((item) => item.market_id === row.market_id)}
                <tr>
                  <td class="wrap-cell">
                    <span class="swatch" style={`background:${comparisonColor(index)}`}></span>
                    <strong>{truncName(leg?.title ?? row.title, 52)}</strong>
                  </td>
                  <td><span class="venue-label">{(leg?.venue ?? row.venue) === "polymarket" ? "PM" : "KL"}</span></td>
                  <td class="num">{pct(leg?.current_probability ?? row.current_probability)}</td>
                  <td class="num {toneOf(leg?.stats?.change)}">{signedPct(leg?.stats?.change)}</td>
                  <td class="num">{leg?.stats?.point_count ?? 0}</td>
                  <td class="tick-col">
                    <button type="button" class="tick" aria-label="Remove" on:click={() => toggleCompare(row.market_id)}
                      >✕</button
                    >
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty-state">
            Tick contracts in the Screener, Watchlist, or Related panels to build a comparison of up to
            {MAX_COMPARE_LEGS}.
          </p>
        {/if}
        {#if compareNotice}
          <div class="panel-notes">
            <div class="note-row"><span class="note-tag">Limit</span><p>{compareNotice}</p></div>
          </div>
        {/if}
      </article>

      <article class="panel table-panel">
        <div class="table-header">
          <span>Saved Sets</span>
          <small>{namedSets.length}/{savedResearch?.comparison_set_limit ?? 0}{savedLoading ? " | SAVING..." : ""}</small>
        </div>
        <div class="save-row">
          <input
            bind:value={newSetName}
            placeholder="Name this comparison"
            maxlength="120"
            on:keydown={(event) => event.key === "Enter" && saveCurrentSet()}
          />
          <button
            type="button"
            class="auto"
            disabled={!newSetName.trim() || compareSelection.length < 2 || savedLoading}
            on:click={saveCurrentSet}>Save</button
          >
        </div>
        {#if namedSets.length}
          <table>
            <thead>
              <tr>
                <th>Set</th>
                <th class="num">Legs</th>
                <th>Range</th>
                <th class="tick-col"></th>
              </tr>
            </thead>
            <tbody>
              {#each namedSets as record (record.id)}
                <tr class="clickable-row" on:click={() => openSavedSet(record)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => openSavedSet(record))}>
                  <td class="wrap-cell"><strong>{truncName(record.name, 40)}</strong></td>
                  <td class="num">{record.market_ids.length}</td>
                  <td>{record.range_key.toUpperCase()}</td>
                  <td class="tick-col">
                    <button
                      type="button"
                      class="tick"
                      aria-label="Delete set"
                      on:click|stopPropagation={() => onDeleteComparisonSet?.(record.id)}>✕</button
                    >
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty-state">Name a basket to reopen a recurring cross-venue comparison later.</p>
        {/if}
      </article>

      <article class="panel chart-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Aligned Probability</p>
            <h2>{comparison?.legs.length ?? 0} contracts | {historyRange.toUpperCase()}</h2>
          </div>
          <div class="segmented" role="group" aria-label="History range">
            {#each HISTORY_RANGES as range}
              <button
                type="button"
                class:selected={historyRange === range.id}
                disabled={compareLoading}
                on:click={() => applyRange(range.id)}
              >
                {range.label}
              </button>
            {/each}
          </div>
        </div>
        <TimeSeriesChart
          series={comparisonSeries}
          height={320}
          showLegend={true}
          emptyMessage={compareLoading ? "LOADING..." : "Select at least two contracts to compare."}
        />
        <div class="chart-foot">
          <strong>
            {comparison?.window_start ? `${dayStamp(comparison.window_start)} → ${dayStamp(comparison.window_end)}` : "—"}
          </strong>
          <small>{formatResolution(comparison?.effective_resolution_minutes)} bars</small>
        </div>
      </article>

      {#if comparison?.basket}
        <article class="panel basket-panel">
          <div class="kpi-grid four">
            <article class="metric">
              <span>Legs</span>
              <strong>{comparison.basket.leg_count}</strong>
              <small>{comparison.basket.venues.join(" / ") || "—"}</small>
            </article>
            <article class="metric">
              <span>Prob Sum</span>
              <strong>{pct(comparison.basket.probability_sum)}</strong>
              <small>{comparison.basket.same_event ? "same venue event" : "cross-event"}</small>
            </article>
            <article class="metric">
              <span>Vs 100%</span>
              <strong class={toneOf(comparison.basket.implied_overround)}
                >{signedPct(comparison.basket.implied_overround)}</strong
              >
              <small>descriptive only</small>
            </article>
            <article class="metric">
              <span>Widest Gap</span>
              <strong class={(rankedPairs[0]?.current_spread ?? 0) >= 0.05 ? "elevated" : ""}
                >{signedPct(rankedPairs[0]?.current_spread)}</strong
              >
              <small>{rankedPairs.length} pairs</small>
            </article>
          </div>
          {#if comparison.basket.note}
            <div class="notes-list">
              <div class="note-row"><span class="note-tag">Method</span><p>{comparison.basket.note}</p></div>
            </div>
          {/if}
        </article>
      {/if}

      <article class="panel table-panel">
        <div class="table-header">
          <span>Pair Analytics</span>
          <small>ranked by current dislocation</small>
        </div>
        {#if rankedPairs.length}
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Pair</th>
                  <th class="num">Now</th>
                  <th class="num">Mean</th>
                  <th class="num">Min</th>
                  <th class="num">Max</th>
                  <th class="num">σ</th>
                  <th class="num">Pctl</th>
                  <th class="num">Corr Δ</th>
                  <th class="num">Overlap</th>
                </tr>
              </thead>
              <tbody>
                {#each rankedPairs as pair (pair.left_market_id + pair.right_market_id)}
                  <tr>
                    <td class="wrap-cell">
                      <strong
                        >{truncName(comparison?.legs.find((leg) => leg.market_id === pair.left_market_id)?.title, 26)}
                        vs
                        {truncName(
                          comparison?.legs.find((leg) => leg.market_id === pair.right_market_id)?.title,
                          26
                        )}</strong
                      >
                      {#if pair.warnings.length}<small>{pair.warnings[0]}</small>{/if}
                    </td>
                    <td class="num {toneOf(pair.current_spread)}">{signedPct(pair.current_spread)}</td>
                    <td class="num">{signedPct(pair.mean_spread)}</td>
                    <td class="num">{signedPct(pair.min_spread)}</td>
                    <td class="num">{signedPct(pair.max_spread)}</td>
                    <td class="num">{pct(pair.spread_volatility, 2)}</td>
                    <td class="num {(pair.current_spread_percentile ?? 0) >= 0.9 ? 'elevated' : ''}"
                      >{pct(pair.current_spread_percentile, 0)}</td
                    >
                    <td class="num {toneOf(pair.correlation)}"
                      >{pair.correlation == null ? "N/A" : pair.correlation.toFixed(2)}</td
                    >
                    <td class="num">{pair.overlap_points}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="empty-state">
            {compareLoading ? "LOADING..." : "Pair analytics appear once two contracts have overlapping history."}
          </p>
        {/if}
      </article>

      {#if spreadSeries.length}
        <article class="panel chart-panel">
          <div class="panel-header">
            <span class="eyebrow">Widest Pair Spread</span>
            <small>{formatResolution(comparison?.effective_resolution_minutes)} bars</small>
          </div>
          <TimeSeriesChart series={spreadSeries} height={200} emptyMessage="No aligned spread." />
        </article>
      {/if}

      {#if comparison?.warnings?.length || comparison?.transformation_note}
        <article class="panel">
          <div class="notes-list">
            {#each comparison?.warnings ?? [] as warning}
              <div class="note-row"><span class="note-tag">Warning</span><p>{warning}</p></div>
            {/each}
            {#if comparison?.transformation_note}
              <div class="note-row info"><span class="note-tag">Method</span><p>{comparison.transformation_note}</p></div>
            {/if}
          </div>
        </article>
      {/if}
    </div>
  {:else}
    <div class="calibration-grid">
      <article class="panel control-panel wide">
        <div class="control-row">
          <div class="segmented" role="group" aria-label="Calibration lead time">
            {#each CALIBRATION_LEAD_TIME_CHOICES as choice}
              <button
                type="button"
                class:selected={calibrationLeadTimes.includes(choice.hours)}
                disabled={calibrationLoading}
                on:click={() => applyCalibrationLeadTime(choice.hours)}
              >
                {choice.label}
              </button>
            {/each}
          </div>
          <label class="inline">
            <span>Sample</span>
            <select bind:value={calibrationSample} disabled={calibrationLoading} on:change={() => runCalibration()}>
              {#each CALIBRATION_SAMPLE_CHOICES as choice}
                <option value={choice}>{choice}</option>
              {/each}
            </select>
          </label>
          <div class="method-line">
            <span class={calibration?.is_validated ? "fresh" : "stale"}>
              {calibration?.is_validated ? "MEASURED" : "UNVALIDATED"}
            </span>
            <small>{describeCalibrationMethod(calibration)}</small>
          </div>
          <div class="nav-actions">
            <button type="button" class="auto" disabled={!calibrationMarketId || calibrationLoading} on:click={() => runCalibration()}
              >Recompute</button
            >
          </div>
        </div>
        <div class="kpi-grid five">
          <article class="metric">
            <span>Venue</span>
            <strong>{calibration?.venue ?? "N/A"}</strong>
            <small>{calibration?.markets_sampled ?? 0} of {calibration?.resolved_markets_considered ?? 0} resolved</small>
          </article>
          <article class="metric">
            <span>Observations</span>
            <strong>{calibration?.sample_size ?? 0}</strong>
            <small>min {calibration?.minimum_curve_sample ?? 0} per curve</small>
          </article>
          <article class="metric">
            <span>Sample Period</span>
            <strong>{dayStamp(calibration?.sample_period_start)} → {dayStamp(calibration?.sample_period_end)}</strong>
            <small>{calibration?.markets_without_history ?? 0} without history</small>
          </article>
          <article class="metric">
            <span>Research Share</span>
            <strong class={(calibration?.research_share ?? 1) < 0.5 ? "stale" : ""}
              >{pct(calibration?.research_share, 0)}</strong
            >
            <small>{calibrationComposition}</small>
          </article>
          <article class="metric">
            <span>Settlement Drift</span>
            <strong class="elevated">{pct(calibration?.convergence?.average_distance_to_outcome)}</strong>
            <small>{pct(calibration?.convergence?.share_within_five_points, 0)} within 5pts of outcome</small>
          </article>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="table-header">
          <span>Reliability by Bucket</span>
          <small>{activeCurve?.label ?? "N/A"} | n={activeCurve?.sample_size ?? 0}</small>
        </div>
        {#if calibrationRows.length}
          <table>
            <thead>
              <tr>
                <th>Bucket</th>
                <th class="num">Priced</th>
                <th class="num">Realized</th>
                <th class="num">Error</th>
                <th class="num">n</th>
                <th class="reliability-col">Priced / Realized</th>
              </tr>
            </thead>
            <tbody>
              {#each calibrationRows as row (row.label)}
                <tr>
                  <td>{row.label}</td>
                  <td class="num">{pct(row.predicted)}</td>
                  <td class="num">{pct(row.realized)}</td>
                  <td class="num {toneOf(row.error)}">{signedPct(row.error)}</td>
                  <td class="num {row.meets_minimum ? '' : 'stale'}">{row.sample_size}</td>
                  <td class="reliability-col">
                    {#if activeCurve?.is_plottable && row.meets_minimum}
                      <div class="reliability">
                        <i class="predicted" style={`width:${Math.round((row.predicted ?? 0) * 100)}%`}></i>
                        <i class="realized" style={`width:${Math.round((row.realized ?? 0) * 100)}%`}></i>
                      </div>
                    {:else}
                      <span class="muted">below minimum</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty-state">
            {calibrationLoading
              ? "LOADING..."
              : calibrationMarketId
                ? "No lead-time observations were measured for this venue."
                : "Select a contract to choose a venue."}
          </p>
        {/if}
        {#if activeCurve?.warnings?.length}
          <div class="panel-notes">
            {#each activeCurve.warnings as warning}
              <div class="note-row"><span class="note-tag">Sample</span><p>{warning}</p></div>
            {/each}
          </div>
        {/if}
      </article>

      <article class="panel table-panel">
        <div class="table-header">
          <span>Lead Times</span>
          <small>settlement price excluded</small>
        </div>
        {#if calibration?.curves?.length}
          <table>
            <thead>
              <tr>
                <th>Lead</th>
                <th class="num">n</th>
                <th class="num">Brier</th>
                <th class="num">Mean Err</th>
                <th>Curve</th>
              </tr>
            </thead>
            <tbody>
              {#each calibration.curves as curve (curve.lead_time_hours)}
                <tr
                  class="clickable-row"
                  class:selected={activeCurve?.lead_time_hours === curve.lead_time_hours}
                  tabindex="0"
                  on:click={() => (activeLeadTime = curve.lead_time_hours)}
                  on:keydown={(event) => activateRowOnKey(event, () => (activeLeadTime = curve.lead_time_hours))}
                >
                  <td><strong>{curve.label}</strong></td>
                  <td class="num">{curve.sample_size}</td>
                  <td class="num">{curve.brier_score == null ? "N/A" : curve.brier_score.toFixed(3)}</td>
                  <td class="num {toneOf(curve.mean_signed_error)}">{signedPct(curve.mean_signed_error)}</td>
                  <td><span class={curve.is_plottable ? "fresh" : "stale"}>{curve.is_plottable ? "drawn" : "withheld"}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty-state">{calibrationLoading ? "LOADING..." : "No lead-time curve was measured."}</p>
        {/if}
      </article>

      <article class="panel table-panel">
        <div class="table-header">
          <span>Sampled Contracts</span>
          <small
            >{observationLeadLabel}{calibration?.observations?.length ?? 0} rows</small
          >
        </div>
        {#if calibration?.observations?.length}
          <div class="table-scroll tall">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th class="num">At Lead</th>
                  <th class="num">At Settle</th>
                  <th>Outcome</th>
                  <th class="num">Surprise</th>
                  <th>Settled</th>
                </tr>
              </thead>
              <tbody>
                {#each calibration.observations as observation (observation.market_id + observation.lead_time_hours)}
                  {@const surprise = (observation.outcome ? 1 : 0) - observation.probability}
                  <tr class="clickable-row" on:click={() => openContract(observation.market_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => openContract(observation.market_id))}>
                    <td class="wrap-cell"><strong>{truncName(observation.title, 48)}</strong></td>
                    <td class="num">{pct(observation.probability)}</td>
                    <td class="num muted">{pct(observation.settlement_probability)}</td>
                    <td class={observation.outcome ? "positive" : "negative"}>{observation.outcome ? "YES" : "NO"}</td>
                    <td class="num {toneOf(surprise)}">{signedPct(surprise)}</td>
                    <td>{dayStamp(observation.settled_at)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="empty-state">{calibrationLoading ? "LOADING..." : "No contract was sampled at the selected lead time."}</p>
        {/if}
      </article>

      {#if calibration?.warnings?.length || calibration?.transformation_note || calibration?.convergence?.note}
        <article class="panel wide">
          <div class="notes-list">
            {#each calibration?.warnings ?? [] as warning}
              <div class="note-row"><span class="note-tag">Warning</span><p>{warning}</p></div>
            {/each}
            {#if calibration?.convergence?.note}
              <div class="note-row"><span class="note-tag">Convergence</span><p>{calibration.convergence.note}</p></div>
            {/if}
            {#if calibration?.transformation_note}
              <div class="note-row info"><span class="note-tag">Method</span><p>{calibration.transformation_note}</p></div>
            {/if}
          </div>
        </article>
      {/if}
    </div>
  {/if}

  <CompactContextMenu
    open={strategyContextMenu.open}
    x={strategyContextMenu.x}
    y={strategyContextMenu.y}
    label="Prediction market actions"
    items={[
      { id: "compare", label: "Toggle in comparison" },
      { id: "watch", label: "Toggle watchlist" },
      { id: "add", label: "Add to Strategy", disabled: !onSendToStrategyLab },
      { id: "add-open", label: "Add and Open", disabled: !onSendToStrategyLab }
    ]}
    onSelect={handleStrategyMenuSelect}
    onClose={closeStrategyMenu}
  />
</section>

<style>
  .view,
  .screener-grid,
  .compare-grid,
  .calibration-grid,
  .workspace-grid,
  .primary-column,
  .support-column,
  .screener-foot,
  .notes-list,
  .tag-list {
    display: grid;
    gap: var(--space-4);
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.55fr) minmax(22rem, 0.95fr);
    align-items: start;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .screener-foot,
  .calibration-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .calibration-grid .wide {
    grid-column: 1 / -1;
  }

  /* ── Mode bar ────────────────────────────────────────────── */

  .mode-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-5);
    flex-wrap: wrap;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(4, auto);
    border: 1px solid var(--panel-strong);
    width: fit-content;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-2);
    padding: var(--space-2) var(--space-5);
    font: inherit;
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    width: auto;
    min-height: 1.7rem;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    color: var(--text-0);
  }

  .mode-bar button.selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--text-0);
  }

  .mode-meta {
    display: flex;
    gap: var(--space-5);
    color: var(--text-2);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .loading-flag {
    color: var(--accent);
  }

  /* ── Panels ──────────────────────────────────────────────── */

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
  }

  .chart-panel,
  .composition-panel,
  .control-panel,
  .filter-panel,
  .basket-panel {
    display: grid;
    gap: var(--space-4);
  }

  .basket-panel,
  .chart-panel {
    padding: 0;
  }

  .basket-panel .notes-list,
  .chart-panel .notes-list {
    padding: 0 var(--space-5) var(--space-5);
  }

  .chart-panel .panel-header,
  .chart-panel .control-row,
  .chart-panel .kpi-grid,
  .chart-panel .chart-foot {
    padding-inline: var(--space-5);
  }

  .chart-panel .panel-header {
    padding-top: var(--space-5);
  }

  .chart-panel .chart-foot {
    padding-bottom: var(--space-4);
  }

  .table-panel {
    display: grid;
    gap: 0;
    padding: 0;
    align-content: start;
  }

  .table-scroll {
    overflow: auto;
  }

  .table-scroll.tall {
    max-height: 34rem;
  }

  /* ── Headers ─────────────────────────────────────────────── */

  .chart-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-5);
  }

  .top-line {
    align-items: start;
  }

  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--divider);
    min-height: 1.65rem;
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
    gap: var(--space-4);
  }

  .table-header small {
    font-size: var(--text-2xs);
    color: var(--text-2);
    text-transform: none;
    letter-spacing: 0;
  }

  .header-actions {
    display: flex;
    gap: var(--space-3);
  }

  .save-row {
    display: flex;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .save-row button {
    min-width: 4rem;
  }

  /* ── KPI strips ──────────────────────────────────────────── */

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(8, minmax(0, 1fr));
    gap: 0;
    padding-block: var(--space-2);
    border-block: 1px solid var(--divider);
  }

  .kpi-grid.four {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border-top: 0;
  }

  .kpi-grid.five {
    grid-template-columns: repeat(5, minmax(0, 1fr));
    border-top: 0;
  }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    border-bottom: 1px solid var(--divider);
    padding-block: var(--space-2);
  }

  .metric {
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    padding: var(--space-2) var(--space-4);
    min-width: 0;
  }

  .metric:first-child {
    border-left: 0;
  }

  .metric strong {
    display: block;
    margin: var(--space-1) 0;
    font-size: var(--text-base);
    color: var(--text-0);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .metric small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ── Typography ──────────────────────────────────────────── */

  .group-label,
  label > span,
  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-xs);
  }

  h2,
  p,
  small {
    margin: 0;
  }

  h2 {
    font-size: var(--text-lg);
  }

  strong {
    color: var(--text-0);
  }

  small,
  .muted,
  .note-row p,
  .wrap-cell small {
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  .title-block,
  .wrap-cell {
    min-width: 0;
  }

  .title-block {
    max-width: 48rem;
  }

  /* ── Controls ────────────────────────────────────────────── */

  label {
    display: grid;
    gap: var(--space-1);
  }

  input,
  select {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-1) var(--space-3);
    font: inherit;
    width: 100%;
    min-height: 1.75rem;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-0);
    padding: var(--space-1) var(--space-4);
    font: inherit;
    width: 100%;
    cursor: pointer;
    min-height: 1.75rem;
  }

  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  button.auto,
  .strategy-actions button {
    width: auto;
  }

  .ghost-button.selected {
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .filter-row {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--space-3);
  }

  .filter-row label {
    width: 7rem;
  }

  .filter-row label.grow {
    flex: 1 1 16rem;
    width: auto;
  }

  .filter-actions {
    display: flex;
    gap: var(--space-3);
    margin-left: auto;
  }

  .filter-actions button {
    width: auto;
    min-width: 4.5rem;
  }

  .control-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: center;
  }

  .nav-actions {
    display: flex;
    gap: var(--space-2);
    margin-left: auto;
  }

  .nav-actions button {
    width: auto;
    min-width: 2.2rem;
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
  }

  .segmented button {
    width: auto;
    min-width: 2.6rem;
    min-height: 1.6rem;
    border: 0;
    border-right: 1px solid var(--divider);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.06em;
    padding: var(--space-1) var(--space-3);
  }

  .segmented button:last-child {
    border-right: 0;
  }

  .segmented button.selected {
    color: var(--text-0);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  label.inline {
    grid-auto-flow: column;
    align-items: center;
    gap: var(--space-3);
    width: auto;
  }

  label.inline select {
    width: 4.5rem;
  }

  .method-line {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    min-width: 0;
  }

  .method-line span {
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  /* Two thin bars per bucket: priced against realized. Drawn only when the
     bucket clears the stated minimum, so a shape is never implied by three
     contracts. */
  .reliability {
    display: grid;
    gap: var(--space-1);
    min-width: 8rem;
  }

  .reliability i {
    display: block;
    height: var(--space-2);
    min-width: 1px;
  }

  .reliability .predicted {
    background: var(--chart-primary);
  }

  .reliability .realized {
    background: var(--chart-secondary);
  }

  .reliability-col {
    width: 10rem;
    white-space: normal;
  }

  .venue-picker {
    display: flex;
    gap: var(--space-2);
  }

  .venue-picker button {
    width: auto;
    min-width: 3.2rem;
    display: grid;
    gap: 0;
    text-align: center;
    padding: var(--space-1) var(--space-3);
  }

  .venue-picker button strong {
    font-size: var(--text-xs);
    color: var(--text-1);
  }

  .venue-picker button small {
    font-size: var(--text-2xs);
  }

  .venue-picker button.selected {
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .venue-picker button.selected.fresh strong {
    color: var(--positive);
  }

  .venue-picker button.selected.stale strong {
    color: var(--warning);
  }

  .side-toggle {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
  }

  .side-toggle button {
    min-width: 2.5rem;
    min-height: 1.7rem;
    width: auto;
    border: 0;
    border-right: 1px solid var(--divider);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.08em;
  }

  .side-toggle button:last-child {
    border-right: 0;
  }

  .side-toggle button.selected {
    color: var(--text-0);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .strategy-actions {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    flex-wrap: wrap;
  }

  /* ── Badges ──────────────────────────────────────────────── */

  .badge-stack {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .badge-stack span,
  .tag-chip {
    border: 1px solid color-mix(in srgb, var(--accent) 14%, transparent);
    background: color-mix(in srgb, var(--accent) 5%, transparent);
    color: var(--text-1);
    padding: var(--space-1) var(--space-3);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-xs);
  }

  .tag-list {
    grid-template-columns: repeat(auto-fit, minmax(7rem, max-content));
    align-items: start;
  }

  .compact-chip {
    display: inline-flex;
    min-width: 4.5rem;
    justify-content: center;
  }

  .swatch {
    display: inline-block;
    width: 0.55rem;
    height: 0.55rem;
    margin-right: var(--space-2);
    vertical-align: middle;
  }

  /* ── Chart foot ──────────────────────────────────────────── */

  .chart-foot {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
  }

  /* ── Tables ──────────────────────────────────────────────── */

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: var(--surface-0);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  th.num,
  td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .tick-col {
    width: 2.2rem;
    text-align: center;
    padding-inline: var(--space-2);
  }

  .tick {
    width: auto;
    min-height: 1.2rem;
    border: 0;
    background: transparent;
    color: var(--text-2);
    padding: 0;
    font-size: var(--text-sm);
  }

  .tick.on {
    color: var(--accent);
  }

  td.wrap-cell {
    white-space: normal;
  }

  .wrap-cell small {
    display: block;
    margin-top: var(--space-1);
  }

  .wrap-cell strong,
  .market-title strong,
  .description-box p,
  code {
    overflow-wrap: anywhere;
    white-space: normal;
  }

  code {
    color: var(--text-1);
    font-family: var(--app-font);
    font-size: var(--text-sm);
  }

  .screener-table tbody tr,
  .clickable-row {
    cursor: pointer;
  }

  tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  tbody tr.selected {
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .market-title {
    display: grid;
    gap: var(--space-1);
    min-width: 16rem;
  }

  .empty-row,
  .empty-state {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .empty-state {
    padding: var(--space-4) var(--space-5);
  }

  /* ── Notes ───────────────────────────────────────────────── */

  .description-box {
    border: 1px solid var(--divider);
    background: var(--surface-soft);
    padding: var(--space-4);
    display: grid;
    gap: var(--space-2);
  }

  .note-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr);
    gap: var(--space-5);
    padding: var(--space-3) 0;
    border-top: 1px solid var(--divider);
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .panel-notes {
    padding: var(--space-3) var(--space-4);
    border-top: 1px solid var(--divider);
    display: grid;
    gap: 0;
  }

  .panel-notes .note-row:first-child {
    padding-top: 0;
    border-top: 0;
  }

  .note-row.info .note-tag,
  .note-row.info p {
    color: var(--accent);
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  /* ── Metadata ────────────────────────────────────────────── */

  .meta-flat {
    display: grid;
    gap: 0;
  }

  .meta-row {
    display: grid;
    grid-template-columns: 7rem minmax(0, 1fr);
    gap: var(--space-4);
    padding: var(--space-2) 0;
    border-top: 1px solid var(--divider);
    align-items: baseline;
  }

  .meta-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .meta-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .meta-row strong,
  .meta-row code,
  .meta-row small {
    overflow-wrap: anywhere;
    white-space: normal;
  }

  /* ── Semantic colors ─────────────────────────────────────── */

  .fresh,
  .positive,
  .hot {
    color: var(--positive);
  }

  .stale,
  .elevated {
    color: var(--warning);
  }

  .delayed,
  .cold {
    color: var(--accent);
  }

  .broken,
  .negative {
    color: var(--negative);
  }

  .badge-stack span.fresh,
  .tag-chip.fresh {
    border-color: color-mix(in srgb, var(--positive) 35%, transparent);
    background: color-mix(in srgb, var(--positive) 8%, transparent);
  }

  .badge-stack span.stale,
  .tag-chip.stale {
    border-color: color-mix(in srgb, var(--warning) 35%, transparent);
    background: color-mix(in srgb, var(--warning) 8%, transparent);
  }

  .badge-stack span.delayed,
  .tag-chip.delayed {
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .badge-stack span.broken,
  .tag-chip.broken {
    border-color: color-mix(in srgb, var(--negative) 35%, transparent);
    background: color-mix(in srgb, var(--negative) 12%, transparent);
  }

  .venue-label {
    color: var(--text-2);
    text-transform: uppercase;
    font-size: var(--text-xs);
    letter-spacing: 0.06em;
  }

  /* ── Responsive ──────────────────────────────────────────── */

  @media (max-width: 1400px) {
    .kpi-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  @media (max-width: 1320px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1080px) {
    .screener-foot,
    .calibration-grid,
    .kpi-strip,
    .kpi-grid.four,
    .kpi-grid.five {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 980px) {
    .mode-bar {
      grid-template-columns: repeat(2, 1fr);
      width: 100%;
    }

    .filter-row label,
    .filter-row label.grow {
      width: 100%;
      flex: 1 1 100%;
    }

    .panel-header,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .badge-stack {
      justify-content: flex-start;
    }

    .note-row {
      grid-template-columns: 1fr;
      gap: var(--space-2);
    }
  }
</style>
