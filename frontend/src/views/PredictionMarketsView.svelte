<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    PredictionCalibrationSummary,
    PredictionMarket,
    PredictionMarketListResponse,
    PredictionProbabilityHistoryResponse,
    PredictionWalletSummary,
    RelatedPredictionMarketListResponse
  } from "../lib/api/types";
  import type { PredictionMarketScreenerOptions } from "../lib/stores/app";

  export let screener: PredictionMarketListResponse | null = null;
  export let detail: PredictionMarket | null = null;
  export let history: PredictionProbabilityHistoryResponse | null = null;
  export let wallet: PredictionWalletSummary | null = null;
  export let related: RelatedPredictionMarketListResponse | null = null;
  export let calibration: PredictionCalibrationSummary | null = null;
  export let loading = false;
  export let onLoadScreener: (options?: PredictionMarketScreenerOptions) => Promise<unknown> | void;
  export let onSelectMarket: (marketId: string) => Promise<unknown> | void;

  let query = "";
  let status: "open" | "closed" | "all" = "open";
  let sortBy: "research_rank" | "volume_desc" | "liquidity_desc" | "repricing_desc" | "resolution_soon" = "research_rank";
  let category = "";
  let venueSelection: Array<"polymarket" | "kalshi"> = ["polymarket", "kalshi"];
  let autoRunHandle: ReturnType<typeof setTimeout> | null = null;
  let autoRunReady = false;
  let lastSubmittedKey = "";
  let currentScreenerKey = "";
  const availableCategories = ["Politics", "Finance", "Geopolitics", "Crypto", "Economy"];

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 0) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString() : "N/A";
  const compactId = (value: string | null | undefined) => {
    const text = String(value ?? "").trim();
    if (!text) {
      return "N/A";
    }
    if (text.length <= 24) {
      return text;
    }
    return `${text.slice(0, 12)}...${text.slice(-10)}`;
  };
  const ageLabel = (seconds: number | null | undefined) => {
    if (seconds == null) {
      return "N/A";
    }
    if (seconds < 3600) {
      return `${Math.max(Math.round(seconds / 60), 1)}m`;
    }
    if (seconds < 86400) {
      return `${Math.round(seconds / 3600)}h`;
    }
    return `${(seconds / 86400).toFixed(1)}d`;
  };
  function describeProbability(probability: number | null | undefined) {
    if (probability == null) {
      return "Probability is unavailable for this contract.";
    }
    if (probability >= 0.75) {
      return "Market pricing is confident and already leaning toward a consensus outcome.";
    }
    if (probability <= 0.25) {
      return "Market pricing is confident on the downside and leaves little room for surprise.";
    }
    if (probability >= 0.45 && probability <= 0.55) {
      return "Market pricing is balanced and still highly sensitive to incremental information.";
    }
    return "Market pricing is directional, but still loose enough for material repricing.";
  }

  function describeMove(change: number | null | undefined) {
    if (change == null) {
      return "Recent repricing is not available.";
    }
    if (Math.abs(change) < 0.01) {
      return "Recent price action has been stable.";
    }
    return change > 0
      ? `Primary-outcome probability is higher by ${pct(change)} versus the recent reference point.`
      : `Primary-outcome probability is lower by ${pct(Math.abs(change))} versus the recent reference point.`;
  }

  function describeTime(daysToResolution: number | null) {
    if (daysToResolution == null) {
      return "Resolution timing is not available.";
    }
    if (daysToResolution < 1) {
      return "This contract is in its final 24 hours, so new information should transmit quickly.";
    }
    if (daysToResolution <= 7) {
      return "This contract resolves within a week, which keeps the catalyst window tight.";
    }
    return `The contract still has roughly ${daysToResolution.toFixed(1)} days to resolve, so repricing can remain gradual.`;
  }

  function describeFlow(summary: PredictionWalletSummary | null) {
    if (!summary?.participants?.length) {
      return "No meaningful recent wallet or taker-flow summary is available yet.";
    }
    if (summary.top_participant_share != null && summary.top_participant_share >= 0.45) {
      return `Flow looks concentrated, with the largest tracked participant representing about ${pct(summary.top_participant_share)} of recent activity.`;
    }
    return "Recent flow is dispersed enough that no single participant dominates the tape.";
  }

  function describeFreshness(market: PredictionMarket | null) {
    const freshness = market?.freshness;
    if (!freshness) {
      return "Freshness checks have not run yet.";
    }
    return freshness.reason ?? "No freshness warning is attached.";
  }

  function describeLiquidity(market: PredictionMarket | null) {
    if (!market) {
      return "Liquidity and spread context will appear once a market is selected.";
    }
    const parts: string[] = [];
    if ((market.volume_24h ?? 0) > 0) {
      parts.push(`${fmt(market.volume_24h)} 24H volume`);
    }
    if ((market.liquidity ?? 0) > 0) {
      parts.push(`${fmt(market.liquidity)} liquidity`);
    }
    if ((market.open_interest ?? 0) > 0) {
      parts.push(`${fmt(market.open_interest)} open interest`);
    }
    if (!parts.length) {
      return "Liquidity and open-interest data are thin or unavailable on this venue payload.";
    }
    if (market.spread != null) {
      parts.push(`${pct(market.spread)} spread`);
    }
    return `${parts.join(" | ")}.`;
  }

  function freshnessTone(statusValue: string | null | undefined) {
    if (statusValue === "broken") {
      return "broken";
    }
    if (statusValue === "stale") {
      return "stale";
    }
    if (statusValue === "delayed") {
      return "delayed";
    }
    if (statusValue === "fresh") {
      return "fresh";
    }
    return "";
  }

  function venueTone(statusValue: string | null | undefined) {
    if (statusValue === "active") {
      return "fresh";
    }
    if (statusValue === "filtered") {
      return "delayed";
    }
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
    if (autoRunHandle) {
      clearTimeout(autoRunHandle);
    }
  });

  function toggleVenue(venue: "polymarket" | "kalshi") {
    if (venueSelection.includes(venue) && venueSelection.length === 1) {
      return;
    }
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
      limit: 40
    });
  }

  function scheduleAutoRun() {
    if (!autoRunReady) {
      return;
    }
    if (currentScreenerKey === lastSubmittedKey) {
      return;
    }
    if (autoRunHandle) {
      clearTimeout(autoRunHandle);
    }
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
    if (probability == null) {
      return "";
    }
    if (probability >= 0.7) {
      return "hot";
    }
    if (probability <= 0.3) {
      return "cold";
    }
    return "";
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
  let biggestGap = related?.related?.slice().sort((left, right) => (right.price_gap ?? -1) - (left.price_gap ?? -1))[0] ?? null;
  let oneDayMove: number | null = null;
  let eventDynamics: Array<{ label: string; value: string; body: string }> = [];
  let hasCalibrationData = false;
  let hasCalibrationWarnings = false;
  let hasWalletRows = false;

  $: chartSeries = history?.points?.length
    ? [
        {
          id: "probability",
          label: detail?.probability_label ?? "Probability",
          color: "#7aa6c8",
          type: "area",
          data: history.points.map((point) => ({
            time: Math.floor(new Date(point.timestamp).getTime() / 1000),
            value: point.probability
          }))
        }
      ]
    : [];

  $: historyPoints = history?.points ?? [];
  $: latestHistoryPoint = historyPoints.length ? historyPoints[historyPoints.length - 1] : null;
  $: trailingDayPoint = (() => {
    if (!latestHistoryPoint) {
      return null;
    }
    const latestMs = new Date(latestHistoryPoint.timestamp).getTime();
    const cutoffMs = latestMs - 24 * 60 * 60 * 1000;
    for (let index = historyPoints.length - 1; index >= 0; index -= 1) {
      const point = historyPoints[index];
      if (new Date(point.timestamp).getTime() <= cutoffMs) {
        return point;
      }
    }
    return historyPoints[0] ?? null;
  })();
  $: historyHigh = historyPoints.length ? Math.max(...historyPoints.map((point) => point.probability)) : null;
  $: historyLow = historyPoints.length ? Math.min(...historyPoints.map((point) => point.probability)) : null;
  $: historyRange = historyHigh != null && historyLow != null ? historyHigh - historyLow : null;
  $: daysToResolution = detail?.end_time
    ? Math.max((new Date(detail.end_time).getTime() - Date.now()) / (24 * 60 * 60 * 1000), 0)
    : null;
  $: topWallet = wallet?.participants?.[0] ?? null;
  $: biggestGap = related?.related?.slice().sort((left, right) => (right.price_gap ?? -1) - (left.price_gap ?? -1))[0] ?? null;
  $: oneDayMove =
    latestHistoryPoint && trailingDayPoint
      ? latestHistoryPoint.probability - trailingDayPoint.probability
      : detail?.recent_price_change ?? null;
  $: hasCalibrationData = Boolean(calibration?.buckets?.length || calibration?.observations?.length);
  $: hasCalibrationWarnings = Boolean(calibration?.warnings?.length || calibration?.transformation_note);
  $: hasWalletRows = Boolean(wallet?.participants?.length);
  $: currentScreenerKey = JSON.stringify({
    query: query.trim(),
    status,
    sortBy,
    category,
    venues: [...venueSelection].sort()
  });
  $: eventDynamics = [
    {
      label: "Probability posture",
      value: pct(detail?.current_probability),
      body: describeProbability(detail?.current_probability)
    },
    {
      label: "Recent move",
      value: pct(oneDayMove),
      body: describeMove(oneDayMove)
    },
    {
      label: "Trading range",
      value: pct(historyRange),
      body:
        historyHigh != null && historyLow != null
          ? `Observed range runs from ${pct(historyLow)} to ${pct(historyHigh)} across the loaded history window.`
          : "Historical range will appear once enough probability points are available."
    },
    {
      label: "Resolution clock",
      value: daysToResolution == null ? "N/A" : `${daysToResolution.toFixed(daysToResolution >= 10 ? 0 : 1)}d`,
      body: describeTime(daysToResolution)
    },
    {
      label: "Liquidity check",
      value: detail?.research_score == null ? "N/A" : `${detail.research_score.toFixed(0)}`,
      body: describeLiquidity(detail)
    },
    {
      label: "Freshness",
      value: detail?.freshness?.status?.toUpperCase() ?? "N/A",
      body: describeFreshness(detail)
    },
    {
      label: "Participation",
      value: pct(wallet?.top_participant_share),
      body: describeFlow(wallet)
    },
    {
      label: "Related analog",
      value: biggestGap ? pct(biggestGap.price_gap) : "N/A",
      body: biggestGap
        ? `${biggestGap.venue} ${biggestGap.relationship} is currently the largest nearby price gap.`
        : "No high-signal related contract has been linked yet."
    },
  ];

  $: if (autoRunReady && currentScreenerKey) {
    scheduleAutoRun();
  }
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel performance-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Prediction Markets</p>
            <h2>{detail?.title ?? "Select a market"}</h2>
            <p class="muted">
              {#if detail}
                The left side stays focused on probability behavior and flow, while normalized ids and provenance stay attached in the research rail for reuse later.
              {:else}
                Load the screener and select a contract to inspect history, flow, consistency, and calibration.
              {/if}
            </p>
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

        <div class="kpi-grid">
          <article class="metric">
            <span>Probability</span>
            <strong>{pct(detail?.current_probability)}</strong>
            <small>{detail?.probability_label ?? "Primary outcome"}</small>
          </article>
          <article class="metric">
            <span>24H Volume</span>
            <strong>{fmt(detail?.volume_24h)}</strong>
            <small>Total {fmt(detail?.volume)}</small>
          </article>
          <article class="metric">
            <span>Liquidity</span>
            <strong>{fmt(detail?.liquidity)}</strong>
            <small>{(detail?.open_interest ?? 0) > 0 ? `Open interest ${fmt(detail?.open_interest)}` : "Open interest unavailable"}</small>
          </article>
          <article class="metric">
            <span>Freshness</span>
            <strong class={freshnessTone(detail?.freshness?.status)}>{detail?.freshness?.status ?? "N/A"}</strong>
            <small>{ageLabel(detail?.freshness?.retrieval_age_seconds)}</small>
          </article>
          <article class="metric">
            <span>Top Flow</span>
            <strong>{topWallet ? topWallet.display_name : "N/A"}</strong>
            <small>{topWallet ? fmt(topWallet.total_size, 2) : "Waiting for flow"}</small>
          </article>
          <article class="metric">
            <span>Research Score</span>
            <strong>{detail?.research_score?.toFixed(0) ?? "N/A"}</strong>
            <small>{detail?.research_rationale ?? "Ranking signal will appear in the screener."}</small>
          </article>
        </div>

        <TimeSeriesChart
          series={chartSeries}
          height={380}
          emptyMessage="Select a market to load probability history."
        />

        <div class="chart-foot">
          <span>{detail?.transformation_note ?? "Price history is normalized into a single primary-outcome probability stream."}</span>
          <strong>{detail ? `${detail.source_provider} | ${detail.origin}` : "No active market"}</strong>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Wallet / Flow</p>
            <h3>Participant Summary</h3>
          </div>
          <small>{wallet?.participants.length ?? 0} rows</small>
        </div>

        {#if hasWalletRows}
          <div class="summary-strip">
            <article class="summary-chip">
              <span>Recent trades</span>
              <strong>{wallet?.total_trades ?? 0}</strong>
            </article>
            <article class="summary-chip">
              <span>Total notional</span>
              <strong>{fmt(wallet?.total_notional, 2)}</strong>
            </article>
            <article class="summary-chip">
              <span>Top share</span>
              <strong>{pct(wallet?.top_participant_share)}</strong>
            </article>
            <article class="summary-chip">
              <span>HHI</span>
              <strong>{wallet?.concentration_hhi?.toFixed(2) ?? "N/A"}</strong>
            </article>
          </div>

          <div class="table-wrap">
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
                      <strong>{participant.display_name}</strong>
                      <small>{participant.outcome_label ?? participant.side}</small>
                    </td>
                    <td>{participant.side}</td>
                    <td>{participant.trade_count}</td>
                    <td>{fmt(participant.total_size, 2)}</td>
                    <td>{pct(participant.average_price)}</td>
                    <td>{pct(participant.current_edge)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <div class="description-box compact-box">
            <small class="group-label">Flow Coverage</small>
            <p>No meaningful wallet or taker-flow summary is available for the selected contract yet.</p>
          </div>
        {/if}

        {#if wallet?.warnings?.length}
          <div class="notes-list">
            {#each wallet.warnings as warning}
              <div class="note-row">
                <span class="note-tag">Warning</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {/if}
      </article>

      <div class="detail-split">
        <article class="panel composition-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Contract Detail</p>
              <h3>Metadata &amp; Provenance</h3>
            </div>
          </div>

          <div class="meta-grid">
            <div class="meta-card span-2">
              <span>Title</span>
              <strong>{detail?.title ?? "No market selected"}</strong>
              <small>{detail?.event_title ?? detail?.series_title ?? "Event context will appear once a contract is selected."}</small>
            </div>
            <div class="meta-card">
              <span>Normalized Market ID</span>
              <code>{compactId(detail?.market_id)}</code>
            </div>
            <div class="meta-card">
              <span>Venue Market ID</span>
              <code>{compactId(detail?.provider_market_id)}</code>
            </div>
            <div class="meta-card">
              <span>Venue Contract ID</span>
              <code>{compactId(detail?.provider_condition_id)}</code>
            </div>
            <div class="meta-card">
              <span>Event / Series</span>
              <strong>{detail ? `${detail.event_title ?? "N/A"} / ${detail.series_title ?? "N/A"}` : "N/A"}</strong>
            </div>
            <div class="meta-card">
              <span>Resolution Time</span>
              <strong>{shortDate(detail?.end_time)}</strong>
            </div>
            <div class="meta-card">
              <span>Freshness</span>
              <strong class={freshnessTone(detail?.freshness?.status)}>{detail?.freshness?.status ?? "N/A"}</strong>
              <small>{detail?.freshness?.reason ?? "No integrity note."}</small>
            </div>
            <div class="meta-card">
              <span>Retrieved</span>
              <strong>{shortDate(detail?.retrieved_at)}</strong>
            </div>
            <div class="meta-card">
              <span>Last History Point</span>
              <strong>{shortDate(detail?.freshness?.last_history_point_at ?? latestHistoryPoint?.timestamp)}</strong>
              <small>Lag {ageLabel(detail?.freshness?.history_lag_seconds)}</small>
            </div>
            <div class="meta-card">
              <span>Origin</span>
              <small>{detail?.source_provider ?? "N/A"} | {detail?.origin ?? "N/A"}</small>
            </div>
            <div class="meta-card span-2">
              <span>Tags</span>
              <div class="tag-list">
                {#if detail?.tags?.length}
                  {#each detail.tags as tag}
                    <span class="tag-chip">{tag}</span>
                  {/each}
                {:else}
                  <small>No tags attached.</small>
                {/if}
              </div>
            </div>
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
            <div>
              <p class="eyebrow">Event Dynamics</p>
              <h3>Readout</h3>
            </div>
          </div>

          <div class="dynamics-grid">
            {#each eventDynamics as item}
              <article class="dynamic-card">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <p>{item.body}</p>
              </article>
            {/each}
          </div>

          <div class="notes-list">
            {#if wallet?.transformation_note}
              <div class="note-row info">
                <span class="note-tag">Flow</span>
                <p>{wallet.transformation_note}</p>
              </div>
            {/if}
            {#if calibration?.transformation_note}
              <div class="note-row">
                <span class="note-tag">Calibration</span>
                <p>{calibration.transformation_note}</p>
              </div>
            {/if}
            {#if detail?.resolution_source}
              <div class="note-row">
                <span class="note-tag">Source</span>
                <p>{detail.resolution_source}</p>
              </div>
            {/if}
          </div>
        </article>
      </div>

      <div class="detail-split">
        <article class="panel rail-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Consistency</p>
              <h3>Related Markets</h3>
            </div>
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
                  on:keydown={(event) => event.key === "Enter" && onSelectMarket(market.market_id)}
                >
                  <span class="note-tag">{market.relationship}</span>
                  <p>
                    <strong>{market.title}</strong><br />
                    {market.venue} | {pct(market.probability)} | gap {pct(market.price_gap)}<br />
                    {market.note ?? ""}
                  </p>
                </div>
              {/each}
            {:else}
              <p class="muted">No linked markets yet.</p>
            {/if}
          </div>
        </article>

        <article class="panel rail-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Calibration</p>
              <h3>Historical Outcomes</h3>
            </div>
            <small>{calibration?.venue ?? "N/A"}</small>
          </div>

          {#if hasCalibrationData}
            <div class="table-wrap">
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
            </div>
          {:else}
            <div class="description-box compact-box">
              <small class="group-label">Calibration Coverage</small>
              <p>Historical calibration is not populated enough on this venue to deserve a full table yet.</p>
            </div>
          {/if}

          {#if hasCalibrationWarnings}
            <div class="notes-list">
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

    <aside class="support-column">
      <article class="panel control-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Discovery</p>
            <h3>Market Screener</h3>
          </div>
          <strong>{screener?.markets.length ?? 0} rows</strong>
        </div>

        {#if screener?.venues?.length}
          <div class="venue-status-grid">
            {#each screener.venues as venue}
              <article class={`summary-chip venue-chip ${venueTone(venue.status)}`}>
                <span>{venue.venue}</span>
                <strong>{venue.status}</strong>
                <small>{venue.visible_markets} visible / {venue.matched_markets} matched</small>
                <small>{venue.message ?? "No venue note."}</small>
              </article>
            {/each}
          </div>
        {/if}

        {#if screener?.warnings?.length}
          <div class="notes-list">
            {#each screener.warnings as warning}
              <div class="note-row">
                <span class="note-tag">Venue</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {/if}

        <label>
          <span>Search</span>
          <input bind:value={query} placeholder="Fed, election, inflation, semis..." on:keydown={handleSearchKeydown} />
        </label>

        <p class="muted">
          Filters auto-apply. Press Enter for an immediate rerun.
          {#if loading}
            Searching current venue data...
          {/if}
        </p>

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
              <option value="research_rank">Research Rank</option>
              <option value="volume_desc">Volume</option>
              <option value="liquidity_desc">Liquidity</option>
              <option value="repricing_desc">Repricing</option>
              <option value="resolution_soon">Resolution</option>
            </select>
          </label>
        </div>

        <label>
          <span>Category</span>
          <select bind:value={category}>
            <option value="">All research categories</option>
            {#each availableCategories as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
        </label>

        <div class="venue-picker">
          <button type="button" class:selected={venueSelection.includes("polymarket")} on:click={() => toggleVenue("polymarket")}>
            Polymarket
          </button>
          <button type="button" class:selected={venueSelection.includes("kalshi")} on:click={() => toggleVenue("kalshi")}>
            Kalshi
          </button>
        </div>

        <div class="builder-actions">
          <button type="button" on:click={() => runScreener(true)} disabled={loading}>
            {loading ? "Loading..." : "Refresh Screener"}
          </button>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Universe</p>
            <h3>Contracts</h3>
          </div>
          <small class="code-text">{detail?.market_id ?? "No market selected"}</small>
        </div>

        <div class="table-wrap screener-table">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Venue</th>
                <th>State</th>
                <th>Prob</th>
                <th>24H Vol</th>
                <th>End</th>
              </tr>
            </thead>
            <tbody>
              {#if screener?.markets?.length}
                {#each screener.markets as market}
                  <tr class:selected={market.market_id === detail?.market_id} on:click={() => onSelectMarket(market.market_id)}>
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
                    <td>{market.venue}</td>
                    <td><span class={`tag-chip compact-chip ${freshnessTone(market.freshness?.status)}`}>{market.freshness?.status ?? "N/A"}</span></td>
                    <td><span class={marketTone(market.current_probability)}>{pct(market.current_probability)}</span></td>
                    <td>{fmt(market.volume_24h)}</td>
                    <td>{shortDate(market.end_time)}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="6">No markets matched the current screen.</td></tr>
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
  .builder-actions,
  .notes-list,
  .summary-strip,
  .venue-status-grid,
  .outcome-grid,
  .tag-list,
  .dynamics-grid {
    display: grid;
    gap: 0.95rem;
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

  .panel {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(9, 14, 20, 0.97), rgba(6, 10, 15, 0.95));
    padding: 1.05rem;
  }

  .performance-panel,
  .composition-panel,
  .insight-panel,
  .table-panel,
  .control-panel,
  .rail-panel {
    display: grid;
    gap: 0.95rem;
  }

  .panel-header,
  .rail-header,
  .chart-foot {
    display: flex;
    justify-content: space-between;
    gap: 0.85rem;
  }

  .top-line {
    align-items: start;
  }

  .title-block,
  .meta-card,
  .dynamic-card,
  .wrap-cell {
    min-width: 0;
  }

  .title-block {
    max-width: 48rem;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .metric,
  .summary-chip,
  .meta-card,
  .outcome-card,
  .dynamic-card {
    min-width: 0;
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.62);
    padding: 0.9rem;
  }

  .metric strong,
  .summary-chip strong,
  .meta-card strong,
  .outcome-card strong,
  .dynamic-card strong {
    display: block;
    margin: 0.22rem 0;
    font-size: 1rem;
    color: var(--text-0);
  }

  .eyebrow,
  .group-label,
  label > span,
  .metric span,
  .summary-chip span,
  .meta-card span,
  .outcome-card span,
  .dynamic-card span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  h2,
  h3,
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
  .dynamic-card p,
  .meta-card small,
  .wrap-cell small {
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  label {
    display: grid;
    gap: 0.4rem;
  }

  input,
  select,
  button {
    border: 1px solid var(--panel-strong);
    background: #0b1219;
    color: var(--text-0);
    padding: 0.56rem 0.72rem;
    font: inherit;
    width: 100%;
  }

  input,
  select,
  button {
    min-height: 3rem;
  }

  button {
    cursor: pointer;
  }

  .field-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
  }

  .venue-picker {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.6rem;
  }

  .venue-picker button.selected {
    border-color: rgba(122, 166, 200, 0.36);
    background: rgba(122, 166, 200, 0.08);
  }

  .badge-stack {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .badge-stack span {
    border: 1px solid rgba(122, 166, 200, 0.14);
    background: rgba(122, 166, 200, 0.05);
    color: var(--text-1);
    padding: 0.34rem 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
  }

  .summary-strip {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .venue-status-grid {
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  }

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .dynamics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .outcome-grid {
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  }

  .tag-list {
    grid-template-columns: repeat(auto-fit, minmax(7rem, max-content));
    align-items: start;
  }

  .span-2 {
    grid-column: span 2;
  }

  .tag-chip {
    border: 1px solid rgba(122, 166, 200, 0.14);
    background: rgba(122, 166, 200, 0.05);
    color: var(--text-1);
    padding: 0.34rem 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
  }

  .compact-chip {
    display: inline-flex;
    min-width: 4.5rem;
    justify-content: center;
  }

  .chart-foot {
    align-items: center;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    padding-top: 0.72rem;
  }

  .table-wrap {
    overflow: auto;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.72rem 0.55rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(8, 13, 18, 0.82);
  }

  td.wrap-cell {
    white-space: normal;
  }

  .wrap-cell small {
    display: block;
    margin-top: 0.2rem;
  }

  .wrap-cell strong,
  .market-title strong,
  .meta-card strong,
  .dynamic-card strong,
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
    font-size: 0.78rem;
  }

  .screener-table tbody tr {
    cursor: pointer;
  }

  .screener-table tbody tr.selected {
    background: rgba(122, 166, 200, 0.08);
  }

  .market-title {
    display: grid;
    gap: 0.2rem;
    min-width: 16rem;
  }

  .hot {
    color: var(--positive);
  }

  .cold {
    color: var(--accent-2);
  }

  .description-box {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.6);
    padding: 0.8rem;
    display: grid;
    gap: 0.5rem;
  }

  .compact-box {
    padding: 0.7rem 0.8rem;
  }

  .note-row {
    display: grid;
    grid-template-columns: 6rem minmax(0, 1fr);
    gap: 0.8rem;
    padding: 0.72rem 0;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
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
    color: #d66868;
  }

  .badge-stack span.fresh,
  .tag-chip.fresh,
  .venue-chip.fresh {
    border-color: rgba(103, 189, 120, 0.35);
    background: rgba(103, 189, 120, 0.08);
  }

  .badge-stack span.stale,
  .tag-chip.stale,
  .venue-chip.stale {
    border-color: rgba(214, 168, 83, 0.35);
    background: rgba(214, 168, 83, 0.08);
  }

  .badge-stack span.delayed,
  .tag-chip.delayed,
  .venue-chip.delayed {
    border-color: rgba(122, 166, 200, 0.36);
    background: rgba(122, 166, 200, 0.12);
  }

  .badge-stack span.broken,
  .tag-chip.broken,
  .venue-chip.broken {
    border-color: rgba(214, 104, 104, 0.35);
    background: rgba(214, 104, 104, 0.12);
  }

  @media (max-width: 1320px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1080px) {
    .detail-split,
    .meta-grid,
    .dynamics-grid,
    .summary-strip,
    .kpi-grid {
      grid-template-columns: 1fr;
    }

    .span-2 {
      grid-column: span 1;
    }
  }

  @media (max-width: 980px) {
    .field-grid,
    .venue-picker {
      grid-template-columns: 1fr;
    }

    .panel-header,
    .rail-header,
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
      gap: 0.35rem;
    }
  }
</style>
