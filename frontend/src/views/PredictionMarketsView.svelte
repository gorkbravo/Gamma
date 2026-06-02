<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { parseApiTimestampToUtcSeconds } from "../lib/chart-data";
  import type {
    PredictionCalibrationSummary,
    PredictionMarket,
    PredictionMarketListResponse,
    PredictionProbabilityHistoryResponse,
    PredictionVenueStatus,
    PredictionWalletSummary,
    RelatedPredictionMarketListResponse,
    StrategyLabHandoffDefaultSide,
    StrategyLabHandoffEnvelope
  } from "../lib/api/types";
  import type { PredictionMarketScreenerOptions, PredictionMarketSortBy } from "../lib/stores/app";
  import { buildPredictionMarketStrategyHandoff } from "../lib/view-models/research";

  export let screener: PredictionMarketListResponse | null = null;
  export let detail: PredictionMarket | null = null;
  export let history: PredictionProbabilityHistoryResponse | null = null;
  export let wallet: PredictionWalletSummary | null = null;
  export let related: RelatedPredictionMarketListResponse | null = null;
  export let calibration: PredictionCalibrationSummary | null = null;
  export let loading = false;
  export let onLoadScreener: (options?: PredictionMarketScreenerOptions) => Promise<unknown> | void;
  export let onSelectMarket: (marketId: string) => Promise<unknown> | void;
  export let onSendToStrategyLab: ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void) | undefined = undefined;

  let query = "";
  let status: "open" | "closed" | "all" = "open";
  let sortBy: PredictionMarketSortBy = "volume_desc";
  let category = "";
  let strategySide: Extract<StrategyLabHandoffDefaultSide, "long_yes" | "long_no"> = "long_yes";
  type VenueKey = "polymarket" | "kalshi";
  const allVenues: VenueKey[] = ["polymarket", "kalshi"];
  let venueSelection: VenueKey[] = [...allVenues];
  let cachedVenueStatuses: Partial<Record<VenueKey, PredictionVenueStatus>> = {};
  let autoRunHandle: ReturnType<typeof setTimeout> | null = null;
  let autoRunReady = false;
  let lastSubmittedKey = "";
  let currentScreenerKey = "";
  const availableCategories = ["Politics", "Finance", "Geopolitics", "Crypto", "Economy"];
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

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 0) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US") : "N/A";
  const compactId = (value: string | null | undefined) => {
    const text = String(value ?? "").trim();
    if (!text) return "N/A";
    if (text.length <= 24) return text;
    return `${text.slice(0, 12)}...${text.slice(-10)}`;
  };
  const truncName = (value: string | null | undefined, max = 18) => {
    const text = String(value ?? "").trim();
    if (!text) return "N/A";
    if (text.length <= max) return text;
    return `${text.slice(0, max - 1)}…`;
  };

  function freshnessTone(statusValue: string | null | undefined) {
    if (statusValue === "broken") return "broken";
    if (statusValue === "stale") return "stale";
    if (statusValue === "delayed") return "delayed";
    if (statusValue === "fresh") return "fresh";
    return "";
  }

  function venueTone(statusValue: string | null | undefined) {
    if (statusValue === "active") return "fresh";
    if (statusValue === "filtered") return "delayed";
    return "stale";
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

  function toggleVenue(venue: "polymarket" | "kalshi") {
    if (venueSelection.includes(venue) && venueSelection.length === 1) return;
    venueSelection = venueSelection.includes(venue)
      ? venueSelection.filter((v) => v !== venue)
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
      limit: 40
    });
  }

  function scheduleAutoRun() {
    if (!autoRunReady) return;
    if (currentScreenerKey === lastSubmittedKey) return;
    if (autoRunHandle) clearTimeout(autoRunHandle);
    autoRunHandle = setTimeout(() => {
      void runScreener();
    }, query.trim() ? 250 : 50);
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void runScreener();
    }
  }

  function marketTone(probability: number | null | undefined) {
    if (probability == null) return "";
    if (probability >= 0.7) return "hot";
    if (probability <= 0.3) return "cold";
    return "";
  }

  function sendSelectedMarketToStrategyLab(open = false) {
    if (!detail || !onSendToStrategyLab) {
      return;
    }
    onSendToStrategyLab(buildPredictionMarketStrategyHandoff(detail, { defaultSide: strategySide }), { open });
  }

  let chartSeries: ChartSeries[] = [];
  let historyPoints = history?.points ?? [];
  let latestHistoryPoint = historyPoints.length ? historyPoints[historyPoints.length - 1] : null;
  let trailingDayPoint = latestHistoryPoint ? historyPoints[0] : null;
  let historyHigh: number | null = null;
  let historyLow: number | null = null;
  let historyRange: number | null = null;
  let daysToResolution: number | null = null;
  let topWallet = wallet?.participants?.[0] ?? null;
  let biggestGap =
    related?.related?.slice().sort((a, b) => (b.price_gap ?? -1) - (a.price_gap ?? -1))[0] ?? null;
  let oneDayMove: number | null = null;
  let eventDynamics: Array<{ label: string; value: string }> = [];
  let hasCalibrationData = false;
  let hasCalibrationWarnings = false;
  let hasWalletRows = false;
  let venueButtons: PredictionVenueStatus[] = allVenues.map((v) => fallbackVenueStatus(v));

  $: chartSeries = history?.points?.length
    ? [
        {
          id: "probability",
          label: detail?.probability_label ?? "Probability",
          color: "#7aa6c8",
          type: "area",
          data: history.points
            .map((p) => ({
              time: parseApiTimestampToUtcSeconds(p.timestamp),
              value: p.probability
            }))
            .filter((p): p is { time: number; value: number } => p.time != null)
        }
      ]
    : [];

  $: historyPoints = history?.points ?? [];
  $: latestHistoryPoint = historyPoints.length ? historyPoints[historyPoints.length - 1] : null;
  $: trailingDayPoint = (() => {
    if (!latestHistoryPoint) return null;
    const latestMs = new Date(latestHistoryPoint.timestamp).getTime();
    const cutoffMs = latestMs - 24 * 60 * 60 * 1000;
    for (let i = historyPoints.length - 1; i >= 0; i--) {
      if (new Date(historyPoints[i].timestamp).getTime() <= cutoffMs) return historyPoints[i];
    }
    return historyPoints[0] ?? null;
  })();
  $: historyHigh = historyPoints.length ? Math.max(...historyPoints.map((p) => p.probability)) : null;
  $: historyLow = historyPoints.length ? Math.min(...historyPoints.map((p) => p.probability)) : null;
  $: historyRange = historyHigh != null && historyLow != null ? historyHigh - historyLow : null;
  $: daysToResolution = detail?.end_time
    ? Math.max((new Date(detail.end_time).getTime() - Date.now()) / (24 * 60 * 60 * 1000), 0)
    : null;
  $: topWallet = wallet?.participants?.[0] ?? null;
  $: biggestGap =
    related?.related?.slice().sort((a, b) => (b.price_gap ?? -1) - (a.price_gap ?? -1))[0] ?? null;
  $: oneDayMove =
    latestHistoryPoint && trailingDayPoint
      ? latestHistoryPoint.probability - trailingDayPoint.probability
      : detail?.recent_price_change ?? null;
  $: hasCalibrationData = Boolean(calibration?.buckets?.length || calibration?.observations?.length);
  $: hasCalibrationWarnings = Boolean(calibration?.warnings?.length || calibration?.transformation_note);
  $: hasWalletRows = Boolean(wallet?.participants?.length);
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
  $: venueButtons = allVenues.map((v) => cachedVenueStatuses[v] ?? fallbackVenueStatus(v));
  $: currentScreenerKey = JSON.stringify({
    query: query.trim(),
    status,
    sortBy,
    category,
    venues: [...venueSelection].sort()
  });
  $: eventDynamics = [
    { label: "Probability", value: pct(detail?.current_probability) },
    { label: "24H Move", value: pct(oneDayMove) },
    { label: "Range", value: pct(historyRange) },
    {
      label: "Resolution",
      value:
        daysToResolution == null
          ? "N/A"
          : `${daysToResolution.toFixed(daysToResolution >= 10 ? 0 : 1)}d`
    },
    {
      label: "24H Volume",
      value: (detail?.volume_24h ?? 0) > 0 ? fmt(detail?.volume_24h) : "N/A"
    },
    { label: "Top Flow", value: pct(wallet?.top_participant_share) },
    { label: "Cross-Venue Gap", value: biggestGap ? pct(biggestGap.price_gap) : "N/A" }
  ];

  $: if (autoRunReady && currentScreenerKey) {
    scheduleAutoRun();
  }
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <!-- ── Main chart panel ─────────────────────────────────── -->
      <article class="panel performance-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Prediction Markets</p>
            <h2>{detail?.title ?? "Select a market"}</h2>
          </div>
          {#if detail}
            <div class="badge-stack">
              <span>{detail.venue}</span>
              <span>{detail.status}</span>
              <span class={freshnessTone(detail.freshness?.status)}
                >{detail.freshness?.status ?? "unknown"}</span
              >
              <span>{detail.category ?? "Research"}</span>
            </div>
          {/if}
        </div>
        {#if detail}
          <div class="strategy-actions">
            <div class="side-toggle" aria-label="Strategy Lab contract side">
              <button type="button" class:selected={strategySide === "long_yes"} on:click={() => strategySide = "long_yes"}>
                YES
              </button>
              <button type="button" class:selected={strategySide === "long_no"} on:click={() => strategySide = "long_no"}>
                NO
              </button>
            </div>
            <button type="button" class="ghost-button" on:click={() => sendSelectedMarketToStrategyLab(false)}>
              + Strategy
            </button>
            <button type="button" on:click={() => sendSelectedMarketToStrategyLab(true)}>
              Add &amp; Open
            </button>
          </div>
        {/if}

        <div class="kpi-grid">
          <article class="metric">
            <span>Prob.</span>
            <strong class={marketTone(detail?.current_probability)}
              >{pct(detail?.current_probability)}</strong
            >
            <small>{detail?.probability_label ?? "Primary outcome"}</small>
          </article>
          <article class="metric">
            <span>24H Vol</span>
            <strong>{fmt(detail?.volume_24h)}</strong>
            <small>Total {fmt(detail?.volume)}</small>
          </article>
          <article class="metric">
            <span>Liquidity</span>
            <strong>{fmt(detail?.liquidity)}</strong>
            <small>{(detail?.open_interest ?? 0) > 0 ? `OI ${fmt(detail?.open_interest)}` : "—"}</small>
          </article>
          <article class="metric">
            <span>Top Flow</span>
            <strong>{topWallet ? truncName(topWallet.display_name) : "N/A"}</strong>
            <small>{topWallet ? fmt(topWallet.total_size, 2) : "—"}</small>
          </article>
        </div>

        <TimeSeriesChart
          series={chartSeries}
          height={380}
          emptyMessage="Select a market to load probability history."
        />

        <div class="chart-foot">
          <strong>{detail ? `${detail.source_provider} | ${detail.origin}` : "No active market"}</strong>
        </div>
      </article>

      <!-- ── Wallet / Flow table ────────────────────────────────── -->
      <article class="panel table-panel">
        <div class="table-header">
          <span>Participant Summary</span>
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
                <th>Trades</th>
                <th>Total Size</th>
                <th>Avg Price</th>
                <th>Current Edge</th>
              </tr>
            </thead>
            <tbody>
              {#each wallet?.participants ?? [] as participant}
                <tr>
                  <td class="wrap-cell">
                    <strong title={participant.display_name}
                      >{truncName(participant.display_name, 22)}</strong
                    >
                    <small>{participant.outcome_label ?? participant.side}</small>
                  </td>
                  <td
                    class={participant.side === "buy"
                      ? "positive"
                      : participant.side === "sell"
                        ? "negative"
                        : ""}>{participant.side}</td
                  >
                  <td>{participant.trade_count}</td>
                  <td>{fmt(participant.total_size, 2)}</td>
                  <td>{pct(participant.average_price)}</td>
                  <td
                    class={(participant.current_edge ?? 0) > 0
                      ? "positive"
                      : (participant.current_edge ?? 0) < 0
                        ? "negative"
                        : ""}>{pct(participant.current_edge)}</td
                  >
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty-state">No flow data for this contract.</p>
        {/if}

        {#if wallet?.warnings?.length || wallet?.transformation_note}
          <div class="panel-notes">
            {#each wallet?.warnings ?? [] as warning}
              <div class="note-row">
                <span class="note-tag">Warning</span>
                <p>{warning}</p>
              </div>
            {/each}
            {#if wallet?.transformation_note}
              <div class="note-row info">
                <span class="note-tag">Flow</span>
                <p>{wallet.transformation_note}</p>
              </div>
            {/if}
          </div>
        {/if}
      </article>

      <!-- ── Metadata + Event Dynamics ──────────────────────────── -->
      <div class="detail-stack">
        <article class="panel composition-panel">
          <div class="panel-header">
            <span class="eyebrow">Metadata &amp; Provenance</span>
          </div>

          <div class="meta-flat">
            <div class="meta-row">
              <span>Market ID</span>
              <code>{compactId(detail?.market_id)}</code>
            </div>
            <div class="meta-row">
              <span>Venue ID</span>
              <code>{compactId(detail?.provider_market_id)}</code>
            </div>
            <div class="meta-row">
              <span>Event</span>
              <strong
                >{detail
                  ? `${detail.event_title ?? "N/A"} / ${detail.series_title ?? "N/A"}`
                  : "N/A"}</strong
              >
            </div>
            <div class="meta-row">
              <span>Resolution</span>
              <strong>{shortDate(detail?.end_time)}</strong>
            </div>
            <div class="meta-row">
              <span>Freshness</span>
              <strong class={freshnessTone(detail?.freshness?.status)}
                >{detail?.freshness?.status ?? "N/A"}</strong
              >
            </div>
            <div class="meta-row">
              <span>Retrieved</span>
              <strong>{shortDate(detail?.retrieved_at)}</strong>
            </div>
            <div class="meta-row">
              <span>Origin</span>
              <small>{detail?.source_provider ?? "N/A"} | {detail?.origin ?? "N/A"}</small>
            </div>
            {#if detail?.resolution_source}
              <div class="meta-row">
                <span>Res. Source</span>
                <small>{detail.resolution_source}</small>
              </div>
            {/if}
            {#if detail?.tags?.length}
              <div class="meta-row">
                <span>Tags</span>
                <div class="tag-list">
                  {#each detail.tags as tag}
                    <span class="tag-chip">{tag}</span>
                  {/each}
                </div>
              </div>
            {/if}
          </div>

          {#if detail?.outcomes?.length}
            <div class="outcome-grid">
              {#each detail.outcomes as outcome}
                <div class="outcome-card">
                  <span>{outcome.label}</span>
                  <strong>{pct(outcome.probability)}</strong>
                  <small>{compactId(outcome.token_id)}</small>
                </div>
              {/each}
            </div>
          {/if}

          {#if detail?.description}
            <div class="description-box">
              <small class="group-label">Resolution / Market Text</small>
              <p>{detail.description}</p>
            </div>
          {/if}
        </article>

        <article class="panel insight-panel">
          <div class="panel-header">
            <span class="eyebrow">Event Dynamics</span>
          </div>

          <div class="dynamics-flat">
            {#each eventDynamics as item}
              <div class="dynamics-row">
                <span class="dyn-label">{item.label}</span>
                <strong class="dyn-value">{item.value}</strong>
              </div>
            {/each}
          </div>
        </article>
      </div>

      <!-- ── Related Markets + Calibration ─────────────────────── -->
      <div class="detail-split">
        <article class="panel rail-panel">
          <div class="panel-header">
            <span class="eyebrow">Related Markets</span>
            <small>{related?.related.length ?? 0} links</small>
          </div>

          <div class="notes-list compact-list">
            {#if related?.related?.length}
              {#each related.related as market}
                <div
                  class="note-row clickable-row"
                  role="button"
                  tabindex="0"
                  on:click={() => onSelectMarket(market.market_id)}
                  on:keydown={(e) => e.key === "Enter" && onSelectMarket(market.market_id)}
                >
                  <span class="note-tag">{market.relationship}</span>
                  <p>
                    <strong>{market.title}</strong><br />
                    {market.venue} | {pct(market.probability)} | gap {pct(market.price_gap)}
                    {#if market.note}<br />{market.note}{/if}
                  </p>
                </div>
              {/each}
            {:else}
              <p class="muted">No linked markets.</p>
            {/if}
          </div>
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <span>Calibration</span>
            <small>{calibration?.venue ?? "N/A"}</small>
          </div>

          {#if hasCalibrationData}
            <table>
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Avg Prob</th>
                  <th>Realized</th>
                  <th>Sample</th>
                </tr>
              </thead>
              <tbody>
                {#each calibration?.buckets ?? [] as bucket}
                  <tr>
                    <td>{bucket.label}</td>
                    <td>{pct(bucket.average_probability)}</td>
                    <td>{pct(bucket.realized_frequency)}</td>
                    <td>{bucket.sample_size}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="empty-state">Calibration unavailable for this venue.</p>
          {/if}

          {#if hasCalibrationWarnings}
            <div class="panel-notes">
              {#each calibration?.warnings ?? [] as warning}
                <div class="note-row">
                  <span class="note-tag">Warning</span>
                  <p>{warning}</p>
                </div>
              {/each}
              {#if calibration?.transformation_note}
                <div class="note-row">
                  <span class="note-tag">Method</span>
                  <p>{calibration.transformation_note}</p>
                </div>
              {/if}
            </div>
          {/if}
        </article>
      </div>
    </div>

    <!-- ── Aside: screener controls + contracts table ────────── -->
    <aside class="support-column">
      <article class="panel control-panel">
        <div class="panel-header">
          <span class="eyebrow">Market Screener</span>
          <strong class="row-count">{screener?.markets.length ?? 0}</strong>
        </div>

        <label>
          <span>Search</span>
          <input
            bind:value={query}
            placeholder="Fed, election, inflation, semis..."
            on:keydown={handleSearchKeydown}
          />
        </label>

        <div class="field-grid">
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
              <option value="volume_desc">Volume</option>
              <option value="research_rank">Research Rank</option>
              <option value="liquidity_desc">Liquidity</option>
              <option value="open_interest_desc">Open Interest</option>
              <option value="repricing_desc">Repricing</option>
              <option value="resolution_soon">Resolution</option>
            </select>
          </label>
        </div>

        <label>
          <span>Category</span>
          <select bind:value={category}>
            <option value="">All categories</option>
            {#each availableCategories as opt}
              <option value={opt}>{opt}</option>
            {/each}
          </select>
        </label>

        <div class="venue-picker">
          {#each venueButtons as venue}
            <button
              type="button"
              class="{venueSelection.includes(venue.venue as VenueKey) ? 'selected' : ''} {venueSelection.includes(venue.venue as VenueKey) ? venueTone(venue.status) : ''}"
              on:click={() => toggleVenue(venue.venue as VenueKey)}
            >
              <strong>{venue.venue === "polymarket" ? "PM" : "KL"}</strong>
              <small>{venue.visible_markets ?? 0} mkts</small>
            </button>
          {/each}
        </div>

        {#if screener?.warnings?.length}
          <div class="notes-list">
            {#each screener.warnings as warning}
              <div class="note-row">
                <span class="note-tag">Note</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {/if}

        <button type="button" on:click={() => runScreener(true)} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </article>

      <article class="panel table-panel">
        <div class="table-header">
          <span>Contracts</span>
          <small class="code-text">{detail?.market_id ?? "—"}</small>
        </div>

        <div class="table-scroll">
        <table class="screener-table">
          <thead>
            <tr>
              <th>Market</th>
              <th>Prob.</th>
              <th>Δ24H</th>
              <th>Vol</th>
              <th>Venue</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {#if screener?.markets?.length}
              {#each screener.markets as market}
                <tr
                  class:selected={market.market_id === detail?.market_id}
                  on:click={() => onSelectMarket(market.market_id)}
                >
                  <td>
                    <div class="market-title">
                      <strong>{market.title}</strong>
                      <small>
                        {market.event_title ?? market.category ?? "Uncategorized"}
                        {#if market.research_score != null}
                          | rank {market.research_score.toFixed(0)}
                        {/if}
                      </small>
                    </div>
                  </td>
                  <td
                    ><span class={marketTone(market.current_probability)}
                      >{pct(market.current_probability)}</span
                    ></td
                  >
                  <td
                    class={(market.recent_price_change ?? 0) > 0
                      ? "positive"
                      : (market.recent_price_change ?? 0) < 0
                        ? "negative"
                        : ""}>{pct(market.recent_price_change)}</td
                  >
                  <td>{fmt(market.volume_24h)}</td>
                  <td
                    ><span class="venue-label"
                      >{market.venue === "polymarket" ? "PM" : "KL"}</span
                    ></td
                  >
                  <td
                    ><span class={`tag-chip compact-chip ${freshnessTone(market.freshness?.status)}`}
                      >{market.freshness?.status ?? "N/A"}</span
                    ></td
                  >
                </tr>
              {/each}
            {:else}
              <tr><td colspan="6" class="empty-row">No markets matched.</td></tr>
            {/if}
          </tbody>
        </table>
        </div>
      </article>
    </aside>
  </div>
</section>

<style>
  .view,
  .workspace-grid,
  .primary-column,
  .support-column,
  .detail-split,
  .notes-list,
  .outcome-grid,
  .tag-list {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.55fr) minmax(22rem, 0.95fr);
    align-items: start;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-stack {
    display: grid;
    gap: 0.5rem;
  }

  /* ── Panels ──────────────────────────────────────────────── */

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 1.05rem;
  }

  .performance-panel,
  .composition-panel,
  .insight-panel,
  .control-panel,
  .rail-panel {
    display: grid;
    gap: 0.5rem;
  }

  /* table-panel: padding-free, table fills edge-to-edge */
  .table-panel {
    display: grid;
    gap: 0;
    padding: 0;
  }

  .table-scroll {
    overflow: auto;
  }

  /* ── Panel headers ───────────────────────────────────────── */

  .panel-header,
  .chart-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.85rem;
  }

  .top-line {
    align-items: start;
  }

  /* compact header for table-panels (replaces eyebrow + h3 stack) */
  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.28rem 0.6rem;
    border-bottom: 1px solid var(--divider);
    min-height: 1.65rem;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
    gap: 0.5rem;
  }

  .table-header small,
  .table-header .code-text {
    font-size: 0.65rem;
    color: var(--text-2);
    text-transform: none;
    letter-spacing: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 14rem;
  }

  /* ── KPI strips ──────────────────────────────────────────── */

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    padding-block: 0.15rem;
  }

  /* kpi-strip inside a zero-padded table-panel */
  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    border-bottom: 1px solid var(--divider);
    padding-block: 0.2rem;
  }

  .metric {
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    padding: 0.2rem 1rem;
    text-align: center;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .kpi-strip .metric:first-child {
    padding-left: 0.6rem;
    border-left: 0;
  }

  .kpi-strip .metric {
    padding-inline: 0.6rem;
  }

  .metric strong,
  .outcome-card strong {
    display: block;
    margin: 0.22rem 0;
    font-size: 1rem;
    color: var(--text-0);
  }

  /* ── Typography ──────────────────────────────────────────── */

  .eyebrow,
  .group-label,
  label > span,
  .metric span,
  .outcome-card span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  h2,
  p,
  small {
    margin: 0;
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

  /* ── Form controls ───────────────────────────────────────── */

  label {
    display: grid;
    gap: 0.3rem;
  }

  input,
  select {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0.22rem 0.5rem;
    font: inherit;
    width: 100%;
    min-height: 1.875rem;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-0);
    padding: 0.22rem 0.5rem;
    font: inherit;
    width: 100%;
    cursor: pointer;
    min-height: 1.875rem;
  }

  .field-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .venue-picker {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.4rem;
  }

  .venue-picker button {
    display: grid;
    gap: 0.1rem;
    text-align: center;
    padding: 0.28rem 0.5rem;
    min-height: 2.2rem;
  }

  .venue-picker button strong {
    font-size: 0.75rem;
    color: var(--text-1);
  }

  .venue-picker button small {
    color: var(--text-2);
    font-size: 0.62rem;
  }

  .venue-picker button.selected {
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .venue-picker button.selected.fresh {
    border-color: color-mix(in srgb, var(--positive) 35%, transparent);
    background: color-mix(in srgb, var(--positive) 8%, transparent);
  }

  .venue-picker button.selected.fresh strong {
    color: var(--positive);
  }

  .venue-picker button.selected.stale {
    border-color: color-mix(in srgb, var(--warning) 35%, transparent);
    background: color-mix(in srgb, var(--warning) 8%, transparent);
  }

  .venue-picker button.selected.stale strong {
    color: var(--warning);
  }

  .venue-picker button.selected.delayed {
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  /* ── Badge stack ─────────────────────────────────────────── */

  .badge-stack {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .strategy-actions {
    display: flex;
    gap: 0.4rem;
    justify-content: flex-end;
    align-items: center;
    flex-wrap: wrap;
  }

  .strategy-actions button {
    width: auto;
    min-height: 1.75rem;
    padding: 0.24rem 0.55rem;
  }

  .side-toggle {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
  }

  .side-toggle button {
    min-width: 2.5rem;
    min-height: 1.75rem;
    border: 0;
    border-right: 1px solid var(--divider);
    background: transparent;
    color: var(--text-2);
    font-size: 0.7rem;
    letter-spacing: 0.08em;
  }

  .side-toggle button:last-child {
    border-right: 0;
  }

  .side-toggle button.selected {
    color: var(--text-0);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .badge-stack span {
    border: 1px solid color-mix(in srgb, var(--accent) 14%, transparent);
    background: color-mix(in srgb, var(--accent) 5%, transparent);
    color: var(--text-1);
    padding: 0.22rem 0.44rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.66rem;
  }

  /* ── Outcome grid ────────────────────────────────────────── */

  .outcome-grid {
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  }

  .outcome-card {
    min-width: 0;
    border: 1px solid var(--divider);
    background: var(--panel-bg);
    padding: 0.7rem 0.8rem;
  }

  /* ── Tags ────────────────────────────────────────────────── */

  .tag-list {
    grid-template-columns: repeat(auto-fit, minmax(7rem, max-content));
    align-items: start;
  }

  .tag-chip {
    border: 1px solid color-mix(in srgb, var(--accent) 14%, transparent);
    background: color-mix(in srgb, var(--accent) 5%, transparent);
    color: var(--text-1);
    padding: 0.22rem 0.44rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.66rem;
  }

  .compact-chip {
    display: inline-flex;
    min-width: 4.5rem;
    justify-content: center;
  }

  /* ── Chart foot ──────────────────────────────────────────── */

  .chart-foot {
    border-top: 1px solid var(--divider);
    padding-top: 0.5rem;
  }

  /* ── Tables ──────────────────────────────────────────────── */

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.42rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: var(--surface-0);
  }

  td.wrap-cell {
    white-space: normal;
  }

  .wrap-cell small {
    display: block;
    margin-top: 0.15rem;
  }

  .wrap-cell strong,
  .market-title strong,
  .description-box p,
  code,
  .code-text {
    overflow-wrap: anywhere;
    white-space: normal;
  }

  code,
  .code-text {
    color: var(--text-1);
    font-family: "IBM Plex Mono", "Cascadia Code", monospace;
    font-size: 0.75rem;
  }

  .screener-table tbody tr {
    cursor: pointer;
  }

  .screener-table tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .screener-table tbody tr.selected {
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .market-title {
    display: grid;
    gap: 0.15rem;
    min-width: 16rem;
  }

  .empty-row,
  .empty-state {
    color: var(--text-2);
    font-size: 0.78rem;
  }

  .empty-state {
    padding: 0.6rem 0.75rem;
  }

  /* ── Description box ─────────────────────────────────────── */

  .description-box {
    border: 1px solid var(--divider);
    background: var(--surface-soft);
    padding: 0.65rem 0.8rem;
    display: grid;
    gap: 0.4rem;
  }

  /* ── Notes ───────────────────────────────────────────────── */

  .note-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr);
    gap: 0.8rem;
    padding: 0.55rem 0;
    border-top: 1px solid var(--divider);
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  /* panel-notes: padded notes section inside a zero-padded table-panel */
  .panel-notes {
    padding: 0.5rem 0.6rem;
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
    font-size: 0.64rem;
  }

  .compact-list .note-row {
    grid-template-columns: 8rem minmax(0, 1fr);
  }

  .clickable-row {
    cursor: pointer;
  }

  /* ── Freshness tones ─────────────────────────────────────── */

  .fresh {
    color: var(--positive);
  }

  .stale {
    color: var(--warning);
  }

  .delayed {
    color: var(--accent);
  }

  .broken {
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

  /* ── Metadata rows ───────────────────────────────────────── */

  .meta-flat {
    display: grid;
    gap: 0;
  }

  .meta-row {
    display: grid;
    grid-template-columns: 7rem minmax(0, 1fr);
    gap: 0.6rem;
    padding: 0.42rem 0;
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
    font-size: 0.62rem;
    padding-top: 0.1rem;
  }

  .meta-row strong,
  .meta-row code,
  .meta-row small {
    overflow-wrap: anywhere;
    white-space: normal;
  }

  /* ── Event dynamics ──────────────────────────────────────── */

  .dynamics-flat {
    display: grid;
    gap: 0;
  }

  .dynamics-row {
    display: grid;
    grid-template-columns: 8rem minmax(0, 1fr);
    gap: 0.6rem;
    padding: 0.42rem 0;
    border-top: 1px solid var(--divider);
    align-items: baseline;
  }

  .dynamics-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .dyn-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.62rem;
  }

  .dyn-value {
    color: var(--text-0);
    font-size: 0.82rem;
  }

  /* ── Semantic colors ─────────────────────────────────────── */

  .hot {
    color: var(--positive);
  }

  .cold {
    color: var(--accent);
  }

  .elevated {
    color: var(--warning);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .venue-label {
    color: var(--text-2);
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
  }

  .row-count {
    color: var(--text-2);
    font-size: 0.75rem;
    font-weight: 400;
  }

  /* ── Responsive ──────────────────────────────────────────── */

  @media (max-width: 1320px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1080px) {
    .detail-split,
    .kpi-grid,
    .kpi-strip {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 980px) {
    .field-grid,
    .venue-picker {
      grid-template-columns: 1fr;
    }

    .panel-header,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .badge-stack {
      justify-content: flex-start;
    }

    .note-row,
    .compact-list .note-row {
      grid-template-columns: 1fr;
      gap: 0.3rem;
    }
  }
</style>
