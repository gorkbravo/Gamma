<script lang="ts">
  import { onMount } from "svelte";
  import CryptoTreemapBoard from "../components/CryptoTreemapBoard.svelte";
  import HeroPriceChart from "../components/HeroPriceChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { parseApiTimestampToUtcSeconds } from "../lib/chart-data";
  import type {
    CryptoComparison,
    CryptoDexLiquiditySummary,
    CryptoFlowSummary,
    CryptoPriceHistoryResponse,
    CryptoSyntheticPortfolio,
    CryptoToken,
    CryptoWorkspaceResponse
  } from "../lib/api/types";
  import type {
    CryptoSortBy,
    CryptoSyntheticPortfolioRunOptions,
    CryptoTokenSelectOptions,
    CryptoWorkspaceLoadOptions
  } from "../lib/stores/app";
  import {
    buildLayerTreemap,
    buildSyntheticPreviewRows,
    cryptoSortMetricLabel,
    flowLeaderboardScore,
    medianNumbers,
    narrativePresetText,
    sumNullableNumbers,
    type BasketPreset,
    type CryptoMode,
    type FocusRow,
    type HeadlineMetric,
    type HeroCanvas
  } from "../lib/view-models/crypto";
  import type { HeroPricePoint } from "../lib/view-models/hero-price-chart";
  import { normalizeSyntheticText, parseSyntheticText } from "../lib/view-models/research";

  import { activateRowOnKey } from "../lib/row-activation";
  export let workspace: CryptoWorkspaceResponse | null = null;
  export let detail: CryptoToken | null = null;
  export let history: CryptoPriceHistoryResponse | null = null;
  export let liquidity: CryptoDexLiquiditySummary | null = null;
  export let flow: CryptoFlowSummary | null = null;
  export let comparison: CryptoComparison | null = null;
  export let syntheticPortfolio: CryptoSyntheticPortfolio | null = null;
  export let loading = false;
  export let portfolioLoading = false;
  export let onLoadWorkspace: (options?: CryptoWorkspaceLoadOptions) => Promise<unknown> | void;
  export let onSelectToken: (tokenId: string, options?: CryptoTokenSelectOptions) => Promise<unknown> | void;
  export let onRunSyntheticPortfolio: (options: CryptoSyntheticPortfolioRunOptions) => Promise<unknown> | void;
  export let onClearSyntheticPortfolio: () => void;

  const modes: Array<{ id: CryptoMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "deep_dive", label: "Deep Dive" },
    { id: "flows_liquidity", label: "Flows & Liquidity" }
  ];
  const defaultNarrativeOptions = ["", "Layer 1", "Layer 2", "Layer 3", "DeFi", "AI", "DePIN", "Gaming", "Meme"];
  const sortOptions: Array<{ value: CryptoSortBy; label: string }> = [
    { value: "market_cap_desc", label: "Market Cap" },
    { value: "screen_score_desc", label: "Screen Score" },
    { value: "volume_desc", label: "Volume" },
    { value: "turnover_desc", label: "Turnover" },
    { value: "momentum_desc", label: "Momentum" },
    { value: "fdv_premium_asc", label: "FDV Discount" }
  ];
  const heroCanvasOptions: Array<{ id: HeroCanvas; label: string }> = [
    { id: "token", label: "Selected Token" },
    { id: "basket", label: "Synthetic Basket" }
  ];
  const heroLookbackOptions = [
    { value: 7, label: "7D" },
    { value: 30, label: "30D" },
    { value: 90, label: "90D" },
    { value: 180, label: "180D" },
    { value: 365, label: "1Y" }
  ];

  export let mode: CryptoMode = "overview";
  let heroCanvas: HeroCanvas = "token";
  let heroLookbackDays = 30;
  let query = "";
  let narrative = "";
  let chain = "";
  let sortBy: CryptoSortBy = "market_cap_desc";
  let minMarketCap = "";
  let minVolume = "";
  let minTurnoverRatio = "";
  let syntheticText = "BTC 0.45\nETH 0.35\nSOL 0.20";
  let selectedBasketPreset = "custom";
  let syntheticBenchmarkTokenId = "bitcoin";
  let basketWarning = "";

  const money = (value: number | null | undefined, digits = 0) =>
    value == null
      ? "N/A"
      : new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: digits
        }).format(value);

  const compactMoney = (value: number | null | undefined) => {
    if (value == null) return "N/A";
    const absolute = Math.abs(value);
    if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
    if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
    if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (absolute >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return money(value, 0);
  };
  const pct = (value: number | null | undefined, digits = 1) => (value == null ? "N/A" : `${value.toFixed(digits)}%`);
  const ratio = (value: number | null | undefined, digits = 2) => (value == null ? "N/A" : `${value.toFixed(digits)}x`);
  const shortDate = (value: string | null | undefined) => (value ? new Date(value).toLocaleString("en-US") : "N/A");

  function toneClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function flowToneClass(label: string | null | undefined) {
    const normalized = String(label ?? "").trim().toLowerCase();
    if (normalized === "accumulation" || normalized === "deep" || normalized === "distributed") return "positive";
    if (normalized === "distribution" || normalized === "fragile" || normalized === "highly concentrated") return "negative";
    if (normalized) return "warning";
    return "";
  }

  function buildPayload(forceRefresh = false): CryptoWorkspaceLoadOptions {
    const toNumber = (value: string) => {
      const numeric = Number(value);
      return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined;
    };
    return {
      query: query.trim() || undefined,
      narrative: narrative || undefined,
      chain: chain.trim() || undefined,
      sortBy,
      minMarketCap: toNumber(minMarketCap),
      minVolume: toNumber(minVolume),
      minTurnoverRatio: toNumber(minTurnoverRatio),
      limit: 60,
      forceRefresh
    };
  }

  async function runWorkspace(forceRefresh = false) {
    await onLoadWorkspace(buildPayload(forceRefresh));
  }

  async function chooseToken(tokenId: string, nextMode?: CryptoMode, selectionOptions: CryptoTokenSelectOptions = {}) {
    if (nextMode) mode = nextMode;
    await onSelectToken(tokenId, {
      historyDays: selectionOptions.historyDays ?? heroLookbackDays,
      resetThread: selectionOptions.resetThread
    });
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void runWorkspace();
    }
  }

  function applyNarrative(label: string) {
    narrative = label;
    mode = "overview";
    void runWorkspace();
  }

  function applyBasketPreset(presetId: string) {
    selectedBasketPreset = presetId;
    const preset = basketPresets.find((item) => item.id === presetId);
    if (preset) syntheticText = preset.text;
    basketWarning = "";
  }

  function normalizeSynthetic() {
    syntheticText = normalizeSyntheticText(syntheticText);
    basketWarning = "";
  }

  async function submitSyntheticPortfolio(forceRefresh = false) {
    const parsed = parseSyntheticText(syntheticText).filter((row) => row.symbol && Number.isFinite(row.weight) && row.weight > 0);
    if (!parsed.length) {
      basketWarning = "Synthetic basket needs at least one valid token weight.";
      return;
    }
    basketWarning = "";
    const result = await onRunSyntheticPortfolio({
      positions: parsed.map((row) => ({ identifier: row.symbol, weight: row.weight })),
      benchmarkTokenId: syntheticBenchmarkTokenId || undefined,
      lookbackDays: heroLookbackDays,
      forceRefresh
    });
    if (result) {
      heroCanvas = "basket";
      mode = "deep_dive";
    }
  }

  function clearSyntheticPortfolioSurface() {
    onClearSyntheticPortfolio();
    heroCanvas = "token";
    basketWarning = "";
  }

  async function refreshHeroCanvas() {
    if (heroCanvas === "basket") {
      if (syntheticPortfolio) {
        await submitSyntheticPortfolio(false);
      }
      return;
    }
    if (detail?.token_id) {
      await chooseToken(detail.token_id, undefined, {
        historyDays: heroLookbackDays,
        resetThread: false
      });
    }
  }

  async function handleHeroLookbackChange(event: Event) {
    heroLookbackDays = Number((event.currentTarget as HTMLSelectElement).value);
    await refreshHeroCanvas();
  }

  onMount(() => {
    if (!workspace?.tokens?.length) void runWorkspace();
  });

  $: screenTokens = workspace?.tokens ?? [];
  $: screenWarnings = workspace?.warnings ?? [];
  $: totalScreenMarketCap = sumNullableNumbers(screenTokens.map((token) => token.market_cap));
  $: totalScreenVolume = sumNullableNumbers(screenTokens.map((token) => token.total_volume));
  $: advancers = screenTokens.filter((token) => (token.price_change_pct_24h ?? 0) > 0).length;
  $: decliners = screenTokens.filter((token) => (token.price_change_pct_24h ?? 0) < 0).length;
  $: weightedMove = screenTokens.length
    ? screenTokens.reduce((sum, token) => sum + ((token.price_change_pct_24h ?? 0) * (token.market_cap ?? 0)), 0) / Math.max(totalScreenMarketCap, 1)
    : null;
  $: weightedTurnover = screenTokens.length
    ? screenTokens.reduce((sum, token) => sum + ((token.turnover_ratio_24h ?? 0) * (token.market_cap ?? 0)), 0) / Math.max(totalScreenMarketCap, 1)
    : null;
  $: medianMove = medianNumbers(screenTokens.map((token) => token.price_change_pct_24h));
  $: topFlowToken = [...screenTokens].sort((left, right) => flowLeaderboardScore(right) - flowLeaderboardScore(left))[0] ?? null;
  $: strongestNarrative = [...(workspace?.narratives ?? [])].sort((left, right) => (right.market_cap_change_pct_24h ?? -999) - (left.market_cap_change_pct_24h ?? -999))[0] ?? null;
  $: btcToken = screenTokens.find((token) => token.symbol.toLowerCase() === "btc") ?? null;
  $: ethToken = screenTokens.find((token) => token.symbol.toLowerCase() === "eth") ?? null;
  $: headlineMetrics = [
    { label: "BTC", value: btcToken ? `$${Math.round(btcToken.current_price ?? 0).toLocaleString("en-US")}` : "N/A", meta: btcToken ? pct(btcToken.price_change_pct_24h) : null, metaTone: toneClass(btcToken?.price_change_pct_24h) },
    { label: "ETH", value: ethToken ? `$${Math.round(ethToken.current_price ?? 0).toLocaleString("en-US")}` : "N/A", meta: ethToken ? pct(ethToken.price_change_pct_24h) : null, metaTone: toneClass(ethToken?.price_change_pct_24h) },
    { label: "Screen Mcap", value: compactMoney(totalScreenMarketCap), meta: `${screenTokens.length} tokens` },
    { label: "24H Breadth", value: `${advancers}A / ${decliners}D`, meta: pct(weightedMove), metaTone: toneClass(weightedMove) }
  ] satisfies HeadlineMetric[];
  $: sortMetricLabel = cryptoSortMetricLabel(sortBy);
  $: layerTreemap = buildLayerTreemap(screenTokens, sortBy);
  $: flowLeaderboard = [...screenTokens].sort((left, right) => flowLeaderboardScore(right) - flowLeaderboardScore(left)).slice(0, 10);
  $: narrativeLeaderboard = [...(workspace?.narratives ?? [])].sort((left, right) => (right.volume_24h ?? 0) - (left.volume_24h ?? 0)).slice(0, 6);
  $: focusRows = [
    { label: "Weighted Move", value: pct(weightedMove), body: `${advancers} advancing, ${decliners} declining`, tone: toneClass(weightedMove) },
    { label: "Median Tape", value: pct(medianMove), body: `${screenTokens.length} tokens in screen`, tone: toneClass(medianMove) },
    { label: "Top Flow Name", value: topFlowToken ? topFlowToken.symbol.toUpperCase() : "N/A", body: topFlowToken ? `turnover ${ratio(topFlowToken.turnover_ratio_24h)} | vol ${compactMoney(topFlowToken.total_volume)} | 7D ${pct(topFlowToken.price_change_pct_7d)}` : "N/A" },
    { label: "Strongest Narrative", value: strongestNarrative?.label ?? "N/A", body: strongestNarrative ? `${pct(strongestNarrative.market_cap_change_pct_24h)} | ${compactMoney(strongestNarrative.volume_24h)} volume` : "N/A" }
  ] satisfies FocusRow[];
  $: narrativeOptions = Array.from(new Set([...defaultNarrativeOptions, ...(workspace?.narratives ?? []).map((basket) => basket.label)]));
  $: tokenChartSeries = history?.points?.length ? [{ id: "price", label: detail ? `${detail.symbol.toUpperCase()} price` : "Price", color: "var(--chart-primary)", type: "area", data: history.points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.price })).filter((point): point is { time: number; value: number } => point.time != null) }] : [];
  $: tokenHeroPricePoints = (history?.points ?? [])
    .map((point) => ({
      time: parseApiTimestampToUtcSeconds(point.timestamp),
      close: point.price,
      volume: point.total_volume ?? undefined
    }))
    .filter((point): point is HeroPricePoint => point.time != null && Number.isFinite(point.close));
  $: syntheticChartSeries = syntheticPortfolio ? [
    { id: "basket", label: "Synthetic basket", color: "var(--chart-primary)", type: "area", data: syntheticPortfolio.portfolio_points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.value })).filter((point): point is { time: number; value: number } => point.time != null) },
    { id: "benchmark", label: syntheticPortfolio.benchmark_label, color: "var(--chart-secondary)", type: "line", lineStyle: "dashed", data: syntheticPortfolio.benchmark_points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.value })).filter((point): point is { time: number; value: number } => point.time != null) }
  ] : [];
  $: activeHeroSeries = heroCanvas === "basket" && syntheticChartSeries.length ? syntheticChartSeries : tokenChartSeries;
  $: if (heroCanvas === "basket" && syntheticPortfolio?.lookback_days && syntheticPortfolio.lookback_days !== heroLookbackDays) {
    heroLookbackDays = syntheticPortfolio.lookback_days;
  }
  $: heroTitle = heroCanvas === "basket" && syntheticPortfolio ? "Synthetic Basket" : detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Select a token";
  $: heroDescription = heroCanvas === "basket" && syntheticPortfolio
    ? syntheticPortfolio.summary ?? "Synthetic basket analytics will appear once Gamma can align the selected token histories."
    : detail?.screen_rationale ?? "Selected token history, market structure, and benchmark context render together inside Deep Dive.";
  $: tokenAbout = detail?.description ?? "Profile details appear once a token is selected.";
  $: basketPresets = [{ id: "custom", label: "Custom", text: syntheticText }, ...((workspace?.narratives ?? []).filter((basket) => basket.top_tokens.length > 0).map((basket) => ({ id: basket.basket_id, label: basket.label, text: narrativePresetText(basket) })) ?? [])] satisfies BasketPreset[];
  $: benchmarkCandidates = Array.from(new Map(([detail, ...screenTokens.slice(0, 12)].filter((token): token is CryptoToken => token != null).map((token) => [token.token_id, token]))).values());
  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: previewRows = buildSyntheticPreviewRows(parsedSynthetic, screenTokens);
  $: recognizedPreviewCount = previewRows.filter((row) => row.resolvedToken != null).length;
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Crypto Research</span>
      {#if detail}
        <span class="subtitle">
          {detail.symbol ?? detail.token_id}
          {#if detail.layer_bucket} · {detail.layer_bucket}{/if}
          {#if detail.chain && !detail.chain.startsWith(detail.layer_bucket ?? "")} · {detail.chain}{/if}
          {#if strongestNarrative} · {strongestNarrative.label} leads{/if}
        </span>
      {/if}
      {#if loading}<span class="loading-pill">Refreshing</span>{/if}
      {#if portfolioLoading}<span class="loading-pill secondary-pill">Building basket</span>{/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Crypto modes">
        {#each modes as modeOption}
          <button class:selected={modeOption.id === mode} role="tab" aria-selected={modeOption.id === mode} type="button" on:click={() => (mode = modeOption.id)}>{modeOption.label}</button>
        {/each}
      </div>
      <div class="headline-strip">
        {#each headlineMetrics as metric}
          <div class="headline-kpi">
            <span class="headline-kpi-label">{metric.label}</span>
            <strong class="headline-kpi-value">{metric.value}{#if metric.meta} <small class={`headline-kpi-meta ${metric.metaTone ?? ""}`}>· {metric.meta}</small>{/if}</strong>
          </div>
        {/each}
      </div>
    </div>

    {#if screenWarnings.length}
      <div class="notes-list">
        {#each screenWarnings as warning}
          <div class="note-row">
            <span class="focus-label">Note</span>
            <p>{warning}</p>
          </div>
        {/each}
      </div>
    {/if}
  </article>

  <div class="workspace-grid" class:overview-layout={mode === "overview"}>
    <div class="primary-column">
      {#if mode === "overview"}
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Overview</p>
              <h3>Layer Treemap</h3>
            </div>
            <div class="panel-actions">
              <button type="button" on:click={() => runWorkspace(false)} disabled={loading}>{loading ? "Loading..." : "Run Screen"}</button>
              <button type="button" class="secondary" on:click={() => runWorkspace(true)} disabled={loading}>Refresh</button>
            </div>
          </div>

          <div class="screener-strip">
            <label class="search-field filter-wide"><span>Search</span><input bind:value={query} placeholder="bitcoin, solana, ai, defi..." on:keydown={handleSearchKeydown} /></label>
            <label><span>Narrative</span><select bind:value={narrative}>{#each narrativeOptions as option}<option value={option}>{option || "All narratives"}</option>{/each}</select></label>
            <label><span>Sort</span><select bind:value={sortBy}>{#each sortOptions as option}<option value={option.value}>{option.label}</option>{/each}</select></label>
            <label><span>Min Mcap</span><input bind:value={minMarketCap} placeholder="1B" /></label>
            <label><span>Min Volume</span><input bind:value={minVolume} placeholder="25M" /></label>
          </div>

          <CryptoTreemapBoard
            sections={layerTreemap}
            {sortBy}
            selectedTokenId={detail?.token_id ?? null}
            emptyMessage="No treemap tiles available for the current crypto screen."
            onSelectToken={(tokenId) => chooseToken(tokenId)}
          />
        </article>

        <div class="overview-packed">
          <div class="overview-left">
            <div class="overview-top-pair">
              <article class="panel">
                <div class="panel-header">
                  <div>
                    <p class="eyebrow">Pulse</p>
                    <h3>Market Pulse</h3>
                  </div>
                </div>

                <div class="focus-list">
                  {#each focusRows as row}
                    <div class="focus-row">
                      <span class="focus-label">{row.label}</span>
                      <strong class={`focus-value ${row.tone ?? ""}`}>{row.value}</strong>
                      <p>{row.body}</p>
                    </div>
                  {/each}
                </div>
              </article>

              <article class="panel">
                <div class="panel-header">
                  <div>
                    <p class="eyebrow">Selection</p>
                    <h3>Quick Take</h3>
                  </div>
                  <small>{detail?.symbol?.toUpperCase() ?? "None"}</small>
                </div>

                <div class="focus-list">
                  <div class="focus-row compact-focus">
                    <span class="focus-label">Name</span>
                    <strong>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Pick a token"}</strong>
                    <p>{detail?.screen_rationale ?? "Select a token from the treemap or table."}</p>
                  </div>
                  <div class="focus-row compact-focus">
                    <span class="focus-label">Narrative</span>
                    <strong>{detail?.narrative_labels?.[0] ?? detail?.layer_bucket ?? "N/A"}</strong>
                    <p>{comparison?.summary ?? "Select a token to see comparison context."}</p>
                  </div>
                  <div class="focus-row compact-focus">
                    <span class="focus-label">Flow</span>
                    <strong class={flowToneClass(flow?.flow_signal_label)}>{flow?.flow_signal_label ?? "N/A"}</strong>
                    <p>{flow?.summary ?? "Flow context appears after token selection."}</p>
                  </div>
                </div>
              </article>
            </div>

            <article class="panel table-panel">
              <div class="table-header">
                <span>Tokens</span>
                <small>{workspace?.tokens?.length ?? 0} tokens</small>
              </div>

              <div class="table-wrap overview-table-wrap">
                <table>
                  <thead>
                    <tr><th>Token</th><th>Price</th><th>24H</th><th>Mcap</th><th>Turnover</th><th>Score</th></tr>
                  </thead>
                  <tbody>
                    {#if workspace?.tokens?.length}
                      {#each workspace.tokens as token}
                        <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => chooseToken(token.token_id))}>
                          <td><div class="market-title"><strong>{token.name}</strong><small>{token.symbol.toUpperCase()} | {token.layer_bucket ?? token.chain ?? "Unknown chain"}</small></div></td>
                          <td>{money(token.current_price, token.current_price && token.current_price < 5 ? 4 : 2)}</td>
                          <td class={toneClass(token.price_change_pct_24h)}>{pct(token.price_change_pct_24h)}</td>
                          <td>{compactMoney(token.market_cap)}</td>
                          <td>{ratio(token.turnover_ratio_24h)}</td>
                          <td>{token.screen_score?.toFixed(1) ?? "N/A"}</td>
                        </tr>
                      {/each}
                    {:else}
                      <tr><td colspan="6">No tokens matched the current screen.</td></tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </article>
          </div>

          <div class="overview-right">
            <article class="panel">
              <div class="panel-header">
                <div>
                  <p class="eyebrow">Narratives</p>
                  <h3>Basket Board</h3>
                </div>
                <small>{workspace?.narratives.length ?? 0} baskets</small>
              </div>

              <div class="basket-grid">
                {#if workspace?.narratives?.length}
                  {#each workspace.narratives as basket}
                    <button type="button" class="basket-card" on:click={() => applyNarrative(basket.label)}>
                      <span>{basket.label}</span>
                      <strong>{compactMoney(basket.market_cap)}</strong>
                      <small class={toneClass(basket.market_cap_change_pct_24h)}>
                        {pct(basket.market_cap_change_pct_24h)} | {compactMoney(basket.volume_24h)} vol
                      </small>
                    </button>
                  {/each}
                {:else}
                  <p class="muted">Narrative baskets will appear with the screener universe.</p>
                {/if}
              </div>
            </article>

            <article class="panel table-panel">
              <div class="table-header">
                <span>Flow Proxy Leaders</span>
                <small>Gamma turnover + move proxy</small>
              </div>

              <div class="table-wrap overview-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Token</th>
                      <th>24H</th>
                      <th>Turnover</th>
                      <th>Volume</th>
                      <th>Signal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#if flowLeaderboard.length}
                      {#each flowLeaderboard.slice(0, 8) as token}
                        <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id, "deep_dive")} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => chooseToken(token.token_id, "deep_dive"))}>
                          <td>
                            <div class="market-title">
                              <strong>{token.name}</strong>
                              <small>{token.symbol.toUpperCase()} | {token.layer_bucket ?? "Cross-sector"}</small>
                            </div>
                          </td>
                          <td class={toneClass(token.price_change_pct_24h)}>{pct(token.price_change_pct_24h)}</td>
                          <td>{ratio(token.turnover_ratio_24h)}</td>
                          <td>{compactMoney(token.total_volume)}</td>
                          <td>{token.screen_score?.toFixed(1) ?? "N/A"}</td>
                        </tr>
                      {/each}
                    {:else}
                      <tr><td colspan="5">Run a screen to populate the opportunity board.</td></tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </article>
          </div>
        </div>
      {:else if mode === "deep_dive"}
        <article class="panel hero-panel">
          <div class="panel-header top-line">
            <div class="headline-block">
              <p class="eyebrow">Deep Dive</p>
              <h3>{heroTitle}</h3>
              {#if heroCanvas === "basket" && syntheticPortfolio}
                <p class="muted">{heroDescription}</p>
              {/if}
            </div>
            <div class="hero-controls">
              <div class="canvas-toggle" role="tablist" aria-label="Hero canvas">
                {#each heroCanvasOptions as option}
                  <button type="button" class:selected={option.id === heroCanvas} on:click={() => (heroCanvas = option.id)} disabled={option.id === "basket" && !syntheticPortfolio}>
                    {option.label}
                  </button>
                {/each}
              </div>
              <label class="hero-control-field">
                <span>Time</span>
                <select bind:value={heroLookbackDays} on:change={handleHeroLookbackChange}>
                  {#each heroLookbackOptions as option}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              </label>
            </div>
          </div>

          <div class="kpi-grid hero-stat-strip">
            {#if heroCanvas === "basket" && syntheticPortfolio}
              <div class="metric hero-stat">
                <span>Basket Return</span>
                <strong>{pct(syntheticPortfolio.cumulative_return_pct)}</strong>
                <small>{syntheticPortfolio.lookback_days}D window</small>
              </div>
              <div class="metric hero-stat">
                <span>Vs {syntheticPortfolio.benchmark_label}</span>
                <strong class={toneClass(syntheticPortfolio.relative_return_pct)}>{pct(syntheticPortfolio.relative_return_pct)}</strong>
                <small>{pct(syntheticPortfolio.benchmark_return_pct)}</small>
              </div>
              <div class="metric hero-stat">
                <span>Volatility</span>
                <strong>{pct(syntheticPortfolio.annualized_volatility_pct)}</strong>
                <small>annualized</small>
              </div>
              <div class="metric hero-stat">
                <span>Weighted Mcap</span>
                <strong>{compactMoney(syntheticPortfolio.weighted_market_cap)}</strong>
                <small>Turnover {ratio(syntheticPortfolio.weighted_turnover_ratio_24h)}</small>
              </div>
              <div class="metric hero-stat">
                <span>Positions</span>
                <strong>{syntheticPortfolio.effective_positions?.toFixed(1) ?? "N/A"}</strong>
                <small>effective</small>
              </div>
            {:else}
              <div class="metric hero-stat">
                <span>Price</span>
                <strong>{money(detail?.current_price, detail?.current_price && detail.current_price < 5 ? 4 : 2)}</strong>
                <small class={toneClass(detail?.price_change_pct_24h)}>{pct(detail?.price_change_pct_24h)} 24H</small>
              </div>
              <div class="metric hero-stat">
                <span>Market Cap</span>
                <strong>{compactMoney(detail?.market_cap)}</strong>
                <small>FDV {compactMoney(detail?.fully_diluted_valuation)}</small>
              </div>
              <div class="metric hero-stat">
                <span>24H Volume</span>
                <strong>{compactMoney(detail?.total_volume)}</strong>
                <small>Turnover {ratio(detail?.turnover_ratio_24h)}</small>
              </div>
              <div class="metric hero-stat">
                <span>7D</span>
                <strong class={toneClass(detail?.price_change_pct_7d)}>{pct(detail?.price_change_pct_7d)}</strong>
                <small>30D {pct(detail?.price_change_pct_30d)}</small>
              </div>
              <div class="metric hero-stat">
                <span>24H Range</span>
                <strong>{money(detail?.low_24h, 2)}–{money(detail?.high_24h, 2)}</strong>
                <small>Rank #{detail?.market_cap_rank ?? "N/A"}</small>
              </div>
            {/if}
          </div>

          {#if heroCanvas === "basket"}
            <TimeSeriesChart
              series={activeHeroSeries}
              height={360}
              emptyMessage="Build a synthetic basket to promote it into the hero canvas."
            />
          {:else}
            <HeroPriceChart
              chartKey="crypto:token"
              points={tokenHeroPricePoints}
              height={360}
              emptyMessage="Select a token to load price history."
            />
          {/if}

          <div class="chart-foot">
            <span>{heroCanvas === "basket" && syntheticPortfolio ? syntheticPortfolio.transformation_note ?? "" : detail?.transformation_note ?? ""}</span>
            <strong>{heroCanvas === "basket" && syntheticPortfolio ? `${syntheticPortfolio.source_provider} | ${syntheticPortfolio.origin}` : detail ? `${detail.source_provider} | ${detail.origin}` : ""}</strong>
          </div>
        </article>

        <div class="detail-split">
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Comparison</p>
                <h3>Relative Context</h3>
              </div>
              <small>{comparison?.target_label ?? "N/A"}</small>
            </div>

            <div class="focus-list">
              <div class="focus-row">
                <span class="focus-label">Target</span>
                <strong class="focus-value">{comparison?.target_kind ?? "N/A"}</strong>
                <p>{comparison?.summary ?? "Comparison context will appear once Gamma resolves a target."}</p>
              </div>
              <div class="focus-row">
                <span class="focus-label">7D Gap</span>
                <strong class={`focus-value ${toneClass(comparison?.price_gap_pct_7d)}`}>{pct(comparison?.price_gap_pct_7d)}</strong>
              </div>
              <div class="focus-row">
                <span class="focus-label">30D Gap</span>
                <strong class={`focus-value ${toneClass(comparison?.price_gap_pct_30d)}`}>{pct(comparison?.price_gap_pct_30d)}</strong>
              </div>
              <div class="focus-row">
                <span class="focus-label">Mcap Ratio</span>
                <strong class="focus-value">{ratio(comparison?.market_cap_ratio)}</strong>
              </div>
            </div>
          </article>

          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Profile</p>
                <h3>Token Detail</h3>
              </div>
              <small>{detail?.homepage_url ? "Linked" : "Read-only"}</small>
            </div>

            <div class="profile-about">
              <span class="focus-label">About</span>
              <p>{tokenAbout}</p>
            </div>

            <div class="meta-flat">
              <div class="meta-row">
                <span>Chain / Layer</span>
                <strong>{detail?.chain ?? "Unknown chain"} / {detail?.layer_bucket ?? "Unclassified"}</strong>
              </div>
              <div class="meta-row">
                <span>Rank / Contract</span>
                <strong>#{detail?.market_cap_rank ?? "N/A"} / {detail?.contract_address ?? "Native / unavailable"}</strong>
              </div>
              <div class="meta-row">
                <span>Supply</span>
                <strong>{detail?.circulating_supply?.toLocaleString("en-US") ?? "N/A"} / {detail?.total_supply?.toLocaleString("en-US") ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Max Supply</span>
                <strong>{detail?.max_supply?.toLocaleString("en-US") ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Retrieved</span>
                <strong>{shortDate(detail?.retrieved_at)}</strong>
              </div>
            </div>

            <div class="tag-list">
              {#each detail?.narrative_labels ?? [] as tag}
                <span class="tag-chip accent-chip">{tag}</span>
              {/each}
              {#each detail?.categories ?? [] as tag}
                <span class="tag-chip">{tag}</span>
              {/each}
            </div>
          </article>
        </div>

        <div class="detail-split" class:basket-empty={!syntheticPortfolio}>
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Narratives</p>
                <h3>Sector Baskets</h3>
              </div>
              <small>{workspace?.narratives.length ?? 0} baskets</small>
            </div>

            <div class="basket-grid">
              {#if workspace?.narratives?.length}
                {#each workspace.narratives as basket}
                  <button type="button" class="basket-card" on:click={() => applyNarrative(basket.label)}>
                    <span>{basket.label}</span>
                    <strong>{compactMoney(basket.market_cap)}</strong>
                    <small class={toneClass(basket.market_cap_change_pct_24h)}>{pct(basket.market_cap_change_pct_24h)} | {compactMoney(basket.volume_24h)} vol</small>
                  </button>
                {/each}
              {:else}
                <p class="muted">Narrative baskets will appear with the screener universe.</p>
              {/if}
            </div>
          </article>

          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Synthetic Basket</p>
                <h3>Exposure Read</h3>
              </div>
              <small>{syntheticPortfolio?.constituents.length ?? 0} names</small>
            </div>

            {#if syntheticPortfolio}
              <div class="meta-flat">
                <div class="meta-row"><span>Benchmark</span><strong>{syntheticPortfolio.benchmark_label}</strong></div>
                <div class="meta-row"><span>Relative Return</span><strong class={toneClass(syntheticPortfolio.relative_return_pct)}>{pct(syntheticPortfolio.relative_return_pct)}</strong></div>
                <div class="meta-row"><span>Effective Positions</span><strong>{syntheticPortfolio.effective_positions?.toFixed(1) ?? "N/A"}</strong></div>
                <div class="meta-row"><span>Warnings</span><strong>{syntheticPortfolio.warnings.length || "None"}</strong></div>
              </div>

              <div class="tag-list">
                {#each syntheticPortfolio.narrative_exposures.slice(0, 6) as exposure}
                  <span class="tag-chip accent-chip">{exposure.label} {pct(exposure.normalized_weight * 100, 0)}</span>
                {/each}
              </div>

              <div class="table-wrap compact-wrap">
                <table>
                  <thead>
                    <tr><th>Token</th><th>Weight</th><th>Turnover</th><th>Layer</th></tr>
                  </thead>
                  <tbody>
                    {#each syntheticPortfolio.constituents as constituent}
                      <tr>
                        <td><div class="market-title"><strong>{constituent.symbol}</strong><small>{constituent.name}</small></div></td>
                        <td>{pct(constituent.normalized_weight * 100, 0)}</td>
                        <td>{ratio(constituent.turnover_ratio_24h)}</td>
                        <td>{constituent.layer_bucket ?? "N/A"}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {:else}
              <p class="muted">Build a synthetic basket in the side rail to deep dive a custom coin selection.</p>
            {/if}
          </article>
        </div>
      {:else}
        <article class="panel hero-panel">
          <div class="panel-header top-line">
            <div class="headline-block">
              <p class="eyebrow">Flows &amp; Liquidity</p>
              <h3>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Select a token"}</h3>
              {#if flow?.summary}<p class="muted">{flow.summary}</p>{/if}
            </div>
            <div class="badge-stack">
              {#if flow?.slippage_proxy_label}<span class={flowToneClass(flow.slippage_proxy_label)}>{flow.slippage_proxy_label}</span>{/if}
              {#if flow?.liquidity_concentration_label}<span class={flowToneClass(flow.liquidity_concentration_label)}>{flow.liquidity_concentration_label}</span>{/if}
              {#if flow?.flow_signal_label}<span class={flowToneClass(flow.flow_signal_label)}>{flow.flow_signal_label}</span>{/if}
            </div>
          </div>

          <div class="kpi-grid">
            <article class="metric">
              <span>DEX Share</span>
              <strong>{pct(flow?.dex_volume_share_of_total_volume != null ? flow.dex_volume_share_of_total_volume * 100 : null)}</strong>
              <small>of spot volume</small>
            </article>
            <article class="metric">
              <span>Buy Pressure</span>
              <strong class={toneClass((flow?.buy_pressure_pct ?? 50) - 50)}>{pct(flow?.buy_pressure_pct)}</strong>
              <small>{flow?.active_trader_proxy_24h?.toLocaleString("en-US") ?? "N/A"} trader proxy</small>
            </article>
            <article class="metric">
              <span>Reserve / Volume</span>
              <strong>{ratio(flow?.reserve_volume_ratio_24h)}</strong>
              <small>{flow?.slippage_proxy_label ?? "N/A"} depth</small>
            </article>
            <article class="metric">
              <span>Top Pool Share</span>
              <strong>{pct(flow?.top_pool_reserve_share != null ? flow.top_pool_reserve_share * 100 : null)}</strong>
              <small>{flow?.pool_count ?? 0} matched pools</small>
            </article>
          </div>

          {#if flow?.warnings?.length}
            <div class="notes-list">
              {#each flow.warnings as warning}
                <div class="note-row">
                  <span class="focus-label">Warning</span>
                  <p>{warning}</p>
                </div>
              {/each}
            </div>
          {/if}
        </article>

        <div class="detail-split">
          <article class="panel table-panel">
            <div class="table-header">
              <span>Pool Tape</span>
              <small>{liquidity?.dominant_dex ?? "N/A"}</small>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>Pool</th><th>DEX</th><th>Reserve</th><th>Vol 24H</th><th>Buys / Sells</th></tr>
                </thead>
                <tbody>
                  {#if liquidity?.pools?.length}
                    {#each liquidity.pools.slice(0, 8) as pool}
                      <tr>
                        <td><div class="market-title"><strong>{pool.pair_name}</strong><small>{pool.network}</small></div></td>
                        <td>{pool.dex}</td>
                        <td>{compactMoney(pool.reserve_usd)}</td>
                        <td>{compactMoney(pool.volume_24h)}</td>
                        <td>{pool.buys_24h}/{pool.sells_24h}</td>
                      </tr>
                    {/each}
                  {:else}
                    <tr><td colspan="5">No matched DEX pools yet.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Structure</p>
                <h3>Concentration Read</h3>
              </div>
              <small>{detail?.symbol?.toUpperCase() ?? "N/A"}</small>
            </div>

            <div class="focus-list">
              <div class="focus-row"><span class="focus-label">Liquidity</span><strong class={flowToneClass(flow?.liquidity_concentration_label)}>{flow?.liquidity_concentration_label ?? "N/A"}</strong></div>
              <div class="focus-row"><span class="focus-label">Flow Regime</span><strong class={flowToneClass(flow?.flow_signal_label)}>{flow?.flow_signal_label ?? "N/A"}</strong></div>
              <div class="focus-row"><span class="focus-label">Reserve / Mcap</span><strong>{pct(flow?.reserve_to_market_cap_ratio != null ? flow.reserve_to_market_cap_ratio * 100 : null)}</strong></div>
              <div class="focus-row"><span class="focus-label">Buyer / Seller</span><strong>{ratio(flow?.participant_balance_ratio)}</strong></div>
            </div>
          </article>
        </div>

        <div class="detail-split">
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Narratives</p>
                <h3>Narrative Flow Board</h3>
              </div>
              <small>Basket volumes and tape</small>
            </div>

            <div class="focus-list">
              {#if narrativeLeaderboard.length}
                {#each narrativeLeaderboard as basket}
                  <div class="focus-row compact-focus">
                    <span class="focus-label">{basket.label}</span>
                    <strong class={toneClass(basket.market_cap_change_pct_24h)}>{pct(basket.market_cap_change_pct_24h)}</strong>
                    <p>{compactMoney(basket.volume_24h)} volume | {compactMoney(basket.market_cap)} market cap</p>
                  </div>
                {/each}
              {:else}
                <p class="muted">Narrative board will appear once the screener workspace loads.</p>
              {/if}
            </div>
          </article>

          <article class="panel table-panel">
            <div class="table-header">
              <span>Flow Leaderboard</span>
              <small>Turnover-led ranking</small>
            </div>

            <div class="table-wrap compact-wrap">
              <table>
                <thead>
                  <tr><th>Token</th><th>24H</th><th>Turnover</th><th>Narrative</th></tr>
                </thead>
                <tbody>
                  {#if flowLeaderboard.length}
                    {#each flowLeaderboard as token}
                      <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => chooseToken(token.token_id))}>
                        <td><div class="market-title"><strong>{token.symbol.toUpperCase()}</strong><small>{compactMoney(token.market_cap)}</small></div></td>
                        <td class={toneClass(token.price_change_pct_24h)}>{pct(token.price_change_pct_24h)}</td>
                        <td>{ratio(token.turnover_ratio_24h)}</td>
                        <td>{token.narrative_labels?.[0] ?? token.layer_bucket ?? "N/A"}</td>
                      </tr>
                    {/each}
                  {:else}
                    <tr><td colspan="4">Run a screen to populate the flow leaderboard.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      {/if}
    </div>

    {#if mode !== "overview"}
      <aside class="support-column">
        {#if mode === "deep_dive"}
          <article class="panel builder-panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Builder</p>
                <h3>Synthetic Basket</h3>
              </div>
              <small>{recognizedPreviewCount}/{previewRows.length} locally recognized</small>
            </div>

            <div class="field-grid">
              <label>
                <span>Preset</span>
                <select bind:value={selectedBasketPreset} on:change={(event) => applyBasketPreset((event.currentTarget as HTMLSelectElement).value)}>
                  {#each basketPresets as preset}<option value={preset.id}>{preset.label}</option>{/each}
                </select>
              </label>
              <label>
                <span>Benchmark</span>
                <select bind:value={syntheticBenchmarkTokenId}>
                  <option value="bitcoin">Bitcoin</option>
                  {#if detail}<option value={detail.token_id}>{detail.symbol.toUpperCase()} (selected)</option>{/if}
                  {#each benchmarkCandidates as token}
                    {#if token.token_id !== "bitcoin" && token.token_id !== detail?.token_id}
                      <option value={token.token_id}>{token.symbol.toUpperCase()}</option>
                    {/if}
                  {/each}
                </select>
              </label>
            </div>

            <label class="textarea-field">
              <span>Synthetic Portfolio</span>
              <textarea bind:value={syntheticText} rows="7" placeholder="BTC 0.50&#10;ETH 0.30&#10;SOL 0.20"></textarea>
            </label>

            {#if basketWarning}
              <div class="focus-row compact-focus">
                <span class="focus-label">Input</span>
                <strong>{basketWarning}</strong>
              </div>
            {/if}

            {#if syntheticPortfolio?.warnings?.length}
              <div class="notes-list">
                {#each syntheticPortfolio.warnings as warning}
                  <div class="focus-row compact-focus">
                    <span class="focus-label">Basket</span>
                    <strong>{warning}</strong>
                  </div>
                {/each}
              </div>
            {/if}

            <div class="builder-actions">
              <button type="button" on:click={normalizeSynthetic}>Normalize</button>
              <button type="button" class="secondary" on:click={() => submitSyntheticPortfolio(false)} disabled={portfolioLoading}>{portfolioLoading ? "Building..." : "Build Basket"}</button>
              <button type="button" class="secondary" on:click={clearSyntheticPortfolioSurface} disabled={!syntheticPortfolio}>Clear</button>
            </div>

            <div class="table-wrap compact-wrap">
              <table>
                <thead>
                  <tr><th>Token</th><th>Input</th><th>Norm</th><th>Layer</th></tr>
                </thead>
                <tbody>
                  {#if previewRows.length}
                    {#each previewRows as row}
                      <tr>
                        <td><div class="market-title"><strong>{row.symbol}</strong><small>{row.resolvedToken?.name ?? "External resolution on submit"}</small></div></td>
                        <td>{row.inputWeight.toFixed(2)}</td>
                        <td>{pct(row.normalizedWeight * 100, 0)}</td>
                        <td>{row.resolvedToken?.layer_bucket ?? "N/A"}</td>
                      </tr>
                    {/each}
                  {:else}
                    <tr><td colspan="4">Basket preview appears once valid rows are entered.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>
        {:else}
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Selection</p>
                <h3>Flow Signal</h3>
              </div>
              <small>{detail?.symbol?.toUpperCase() ?? "None"}</small>
            </div>

            <div class="focus-list">
              <div class="focus-row compact-focus">
                <span class="focus-label">Name</span>
                <strong>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Pick a token"}</strong>
                <p>{detail?.screen_rationale ?? "Select a token from the treemap or screener table to anchor the research surface."}</p>
              </div>
              <div class="focus-row compact-focus">
                <span class="focus-label">Narrative</span>
                <strong>{detail?.narrative_labels?.[0] ?? detail?.layer_bucket ?? "N/A"}</strong>
                <p>{comparison?.summary ?? "Comparison context appears once Gamma resolves a default target."}</p>
              </div>
              <div class="focus-row compact-focus">
                <span class="focus-label">Flow</span>
                <strong class={flowToneClass(flow?.flow_signal_label)}>{flow?.flow_signal_label ?? "N/A"}</strong>
                <p>{flow?.summary ?? "Flow summary will appear after a token is selected and DEX context is available."}</p>
              </div>
            </div>
          </article>
        {/if}

        <article class="panel table-panel">
          <div class="table-header">
            <span>Tokens</span>
            <small>{workspace?.tokens?.length ?? 0} tokens</small>
          </div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Token</th><th>Price</th><th>24H</th><th>Mcap</th><th>Turnover</th><th>Score</th></tr>
              </thead>
              <tbody>
                {#if workspace?.tokens?.length}
                  {#each workspace.tokens as token}
                    <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id)} tabindex="0" on:keydown={(event) => activateRowOnKey(event, () => chooseToken(token.token_id))}>
                      <td><div class="market-title"><strong>{token.name}</strong><small>{token.symbol.toUpperCase()} | {token.layer_bucket ?? token.chain ?? "Unknown chain"}</small></div></td>
                      <td>{money(token.current_price, token.current_price && token.current_price < 5 ? 4 : 2)}</td>
                      <td class={toneClass(token.price_change_pct_24h)}>{pct(token.price_change_pct_24h)}</td>
                      <td>{compactMoney(token.market_cap)}</td>
                      <td>{ratio(token.turnover_ratio_24h)}</td>
                      <td>{token.screen_score?.toFixed(1) ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="6">No tokens matched the current screen.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </aside>
    {/if}
  </div>
</section>

<style>
  .view,
  .primary-column,
  .support-column,
  .detail-split,
  .notes-list,
  .basket-grid,
  .tag-list,
  .focus-list,
  .meta-flat {
    display: grid;
    gap: var(--space-4);
  }

  .view {
    gap: var(--space-4);
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.58fr) minmax(22rem, 0.96fr);
    gap: var(--space-4);
    align-items: start;
  }

  .workspace-grid.overview-layout {
    grid-template-columns: 1fr;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-support-grid {
    grid-template-columns: minmax(18rem, 0.88fr) minmax(0, 1.12fr);
    align-items: start;
  }

  .detail-split.basket-empty {
    grid-template-columns: minmax(0, 1.6fr) minmax(0, 0.4fr);
  }

  .overview-packed {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }

  .overview-left,
  .overview-right {
    display: grid;
    gap: var(--space-4);
    align-content: start;
  }

  .overview-top-pair {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .overview-top-pair > .panel {
    align-self: stretch;
  }

  .overview-table-wrap {
    max-height: 24rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-6);
    display: grid;
    gap: var(--space-4);
  }

  .header-panel {
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
  }

  .header-panel .header-top {
    align-items: baseline;
    justify-content: flex-start;
    gap: var(--space-4);
  }

  .header-panel .title {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .header-panel .subtitle {
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
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
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    min-height: 26px;
    flex-shrink: 0;
  }

  .table-header span {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
  }

  .table-header small {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .table-panel .table-wrap {
    border: 0;
    background: transparent;
  }

  .panel-header,
  .header-top,
  .chart-foot,
  .top-line {
    display: flex;
    justify-content: space-between;
    gap: var(--space-5);
    align-items: flex-start;
  }

  .headline-block,
  .market-title {
    min-width: 0;
  }

  .headline-title-row,
  .mode-kpi-row,
  .builder-actions,
  .hero-controls,
  .header-badges,
  .badge-stack,
  .headline-strip,
  .panel-actions {
    display: flex;
    gap: var(--space-4);
  }

  .headline-title-row {
    align-items: baseline;
    flex-wrap: wrap;
  }

  .mode-kpi-row {
    justify-content: space-between;
    align-items: flex-start;
  }

  .header-badges,
  .badge-stack,
  .headline-strip,
  .builder-actions {
    flex-wrap: wrap;
  }

  .badge-stack span {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-1);
    padding: var(--space-1) var(--space-4);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  .mode-bar,
  .canvas-toggle {
    display: inline-grid;
    border: 1px solid var(--panel-strong);
  }

  .mode-bar {
    grid-template-columns: repeat(3, auto);
  }

  .canvas-toggle {
    grid-template-columns: repeat(2, auto);
  }

  .mode-bar button,
  .canvas-toggle button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-2) var(--space-5);
    font: inherit;
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child,
  .canvas-toggle button:last-child {
    border-right: 0;
  }

  .mode-bar button:focus-visible,
  .canvas-toggle button:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-0);
    padding: var(--space-3) var(--space-5);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .mode-bar button.selected,
  .canvas-toggle button.selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .mode-bar button:hover:not(:disabled),
  .canvas-toggle button:hover:not(:disabled) {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    color: var(--text-0);
    border-color: var(--panel-strong);
  }

  button:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
  }

  button.secondary {
    color: var(--text-1);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
    border-color: var(--panel-border);
  }

  .loading-pill {
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: var(--space-2) var(--space-4);
    white-space: nowrap;
  }

  .secondary-pill {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 28%, transparent);
    background: color-mix(in srgb, var(--warning) 6%, transparent);
  }

  input,
  select,
  textarea {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-3) var(--space-4);
    font: inherit;
    font-size: var(--text-base);
    min-height: 2rem;
  }

  textarea {
    resize: vertical;
    min-height: 8rem;
  }

  input:hover,
  select:hover,
  textarea:hover {
    border-color: color-mix(in srgb, var(--accent) 32%, var(--panel-strong));
  }

  label,
  .search-field,
  .textarea-field {
    display: grid;
    gap: var(--space-2);
  }

  label > span,
  .eyebrow,
  .section-label,
  .focus-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .headline-kpi-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    line-height: 1.1;
  }

  h3,
  p,
  small,
  strong {
    margin: 0;
  }

  h3 {
    font-size: var(--text-md);
  }

  .header-panel .headline-strip {
    border-left: 1px solid var(--divider);
  }

  .header-panel .headline-kpi {
    display: grid;
    gap: 0.05rem;
    padding: var(--space-1) var(--space-5);
    border-right: 1px solid var(--divider);
    border-left: 0;
    min-width: 5.5rem;
    text-align: left;
  }

  .header-panel .headline-kpi-value {
    display: block;
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
    line-height: 1.15;
  }

  .header-panel .headline-kpi-value .headline-kpi-meta {
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 400;
    margin-left: var(--space-1);
    line-height: 1.15;
  }

  .header-panel .headline-kpi-value .headline-kpi-meta.positive { color: var(--positive); }
  .header-panel .headline-kpi-value .headline-kpi-meta.negative { color: var(--negative); }
  .header-panel .headline-kpi-value .headline-kpi-meta.warning { color: var(--warning); }

  .headline-kpi {
    padding: var(--space-1) var(--space-5) var(--space-2) var(--space-5);
    border-left: 1px solid var(--divider);
    text-align: right;
  }

  .headline-kpi:first-child {
    border-left: 0;
  }

  .headline-kpi-value {
    display: block;
    font-size: var(--text-md);
    line-height: 1.2;
  }

  .headline-kpi-meta,
  .coverage-note,
  .muted,
  .chart-foot span {
    color: var(--text-2);
    line-height: 1.35;
  }

  .coverage-note {
    margin: 0;
    font-size: var(--text-sm);
  }

  .chart-foot {
    align-items: center;
    flex-wrap: wrap;
  }

  .chart-foot strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .hero-panel {
    gap: var(--space-5);
  }

  .hero-controls {
    align-items: end;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .hero-control-field {
    min-width: 5.4rem;
    gap: var(--space-1);
  }

  .hero-control-field select {
    min-width: 5.4rem;
    min-height: 1.82rem;
    padding: var(--space-2) var(--space-4);
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
    gap: 0;
    padding-block: var(--space-1);
  }

  .hero-stat-strip {
    margin-top: 0.05rem;
  }

  .metric {
    padding: var(--space-2) var(--space-6);
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    display: grid;
    gap: var(--space-1);
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-xs);
  }

  .metric strong {
    display: block;
    margin: var(--space-2) 0;
    font-size: var(--text-lg);
    color: var(--text-0);
  }

  .hero-stat small {
    line-height: 1.35;
  }

  .metric small,
  .market-title small,
  .focus-row p,
  .meta-row span {
    color: var(--text-2);
  }

  .headline-kpi-meta.positive,
  .metric small.positive,
  .hero-stat small.positive {
    color: var(--positive);
  }

  .headline-kpi-meta.negative,
  .metric small.negative,
  .hero-stat small.negative {
    color: var(--negative);
  }

  .headline-kpi-meta.warning,
  .metric small.warning,
  .hero-stat small.warning {
    color: var(--warning);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .warning {
    color: var(--warning);
  }

  .screener-strip {
    display: flex;
    gap: var(--space-4);
    flex-wrap: wrap;
    align-items: end;
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
  }

  .screener-strip label {
    flex: 1 1 7rem;
    min-width: 5rem;
  }

  .screener-strip .filter-wide {
    flex: 1.8 1 16rem;
  }

  .focus-row,
  .meta-row,
  .note-row {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
    display: grid;
    gap: var(--space-1);
  }

  .focus-row:first-child,
  .meta-row:first-child,
  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .focus-value {
    font-size: var(--text-md);
  }

  .align-right {
    text-align: right;
  }

  .compact-focus p {
    color: var(--text-2);
  }

  .profile-about {
    display: grid;
    gap: var(--space-1);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .profile-about p {
    color: var(--text-1);
    line-height: 1.45;
  }

  .meta-row strong {
    overflow-wrap: anywhere;
  }

  .basket-card {
    border: 1px solid var(--divider);
    background: transparent;
    padding: var(--space-4);
    display: grid;
    gap: var(--space-1);
    text-align: left;
  }

  .tag-list {
    grid-template-columns: repeat(auto-fit, minmax(8rem, max-content));
  }

  .tag-chip {
    border: 1px solid var(--divider);
    padding: var(--space-2) var(--space-4);
    color: var(--text-1);
    background: var(--surface-0);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  .accent-chip {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 35%, var(--divider));
  }

  .table-wrap {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: auto;
    max-height: 29rem;
  }

  .compact-wrap {
    max-height: 17rem;
  }

  .compact-overview-table {
    max-height: 21rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
    padding: var(--space-4) var(--space-4);
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
  }

  tbody td {
    padding: var(--space-4) var(--space-4);
    border-top: 1px solid var(--divider);
    vertical-align: top;
  }

  tbody tr {
    cursor: pointer;
  }

  tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  tbody tr.selected {
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .field-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .search-field input {
    min-width: 15rem;
  }

  @media (max-width: 1180px) {
    .workspace-grid,
    .detail-split,
    .overview-packed {
      grid-template-columns: 1fr;
    }

    .overview-top-pair {
      grid-template-columns: 1fr;
    }

  }

  @media (max-width: 760px) {
    .mode-kpi-row,
    .header-top,
    .hero-controls,
    .builder-actions {
      flex-direction: column;
      align-items: stretch;
    }

    .mode-bar,
    .canvas-toggle {
      width: 100%;
      grid-template-columns: 1fr;
    }

    .headline-kpi {
      border-left: 0;
      border-top: 1px solid var(--divider);
      text-align: left;
      padding-left: 0;
    }

    .headline-kpi:first-child {
      border-top: 0;
    }

    .kpi-grid,
    .field-grid {
      grid-template-columns: 1fr;
    }

    .search-field input {
      min-width: 0;
    }

    .align-right {
      text-align: left;
    }
  }
</style>
