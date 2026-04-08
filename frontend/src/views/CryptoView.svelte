<script lang="ts">
  import { onMount } from "svelte";
  import CryptoMosaicBoard from "../components/CryptoMosaicBoard.svelte";
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
    CryptoWorkspaceLoadOptions
  } from "../lib/stores/app";
  import {
    buildMosaicTiles,
    buildSyntheticPreviewRows,
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
  import { normalizeSyntheticText, parseSyntheticText } from "../lib/view-models/research";

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
  export let onSelectToken: (tokenId: string) => Promise<unknown> | void;
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

  let mode: CryptoMode = "overview";
  let heroCanvas: HeroCanvas = "token";
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
      : new Intl.NumberFormat(undefined, {
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
  const shortDate = (value: string | null | undefined) => (value ? new Date(value).toLocaleString() : "N/A");

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

  async function chooseToken(tokenId: string, nextMode?: CryptoMode) {
    if (nextMode) mode = nextMode;
    await onSelectToken(tokenId);
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
      lookbackDays: 30,
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
  $: headlineMetrics = [
    { label: "Universe", value: String(screenTokens.length), meta: screenWarnings.length ? `${screenWarnings.length} notes` : null },
    { label: "Breadth", value: `${advancers}/${screenTokens.length || 0}`, meta: decliners ? `${decliners} down` : "No decliners" },
    { label: "Screen Mcap", value: compactMoney(totalScreenMarketCap), meta: `Vol ${compactMoney(totalScreenVolume)}` },
    { label: "Weighted 24H", value: pct(weightedMove), meta: `Turnover ${ratio(weightedTurnover)}` }
  ] satisfies HeadlineMetric[];
  $: coverageNote = mode === "overview"
    ? "Overview tracks the current screener universe and sizes the layer mosaics by market cap."
    : mode === "flows_liquidity"
      ? "Flows & Liquidity is a transparent first-pass proxy built from GeckoTerminal pool activity and normalized token metadata."
      : "Deep Dive centers the selected token, while synthetic baskets let Gamma treat a custom coin selection as a research object inside the same crypto domain.";
  $: layer1Tiles = buildMosaicTiles([...screenTokens].filter((token) => token.layer_bucket === "Layer 1").sort((left, right) => (right.market_cap ?? 0) - (left.market_cap ?? 0)), "large");
  $: layer2Tiles = buildMosaicTiles([...screenTokens].filter((token) => token.layer_bucket === "Layer 2").sort((left, right) => (right.market_cap ?? 0) - (left.market_cap ?? 0)), "medium");
  $: layer3Tiles = buildMosaicTiles([...screenTokens].filter((token) => token.layer_bucket === "Layer 3").sort((left, right) => (right.market_cap ?? 0) - (left.market_cap ?? 0)), "small");
  $: flowLeaderboard = [...screenTokens].sort((left, right) => flowLeaderboardScore(right) - flowLeaderboardScore(left)).slice(0, 10);
  $: narrativeLeaderboard = [...(workspace?.narratives ?? [])].sort((left, right) => (right.volume_24h ?? 0) - (left.volume_24h ?? 0)).slice(0, 6);
  $: focusRows = [
    { label: "Weighted Move", value: pct(weightedMove), body: "Market-cap weighted day return across the current crypto screen.", tone: toneClass(weightedMove) },
    { label: "Median Tape", value: pct(medianMove), body: "Median 24H move to keep the read from being dominated by the largest names.", tone: toneClass(medianMove) },
    { label: "Top Flow Name", value: topFlowToken ? topFlowToken.symbol.toUpperCase() : "N/A", body: topFlowToken?.screen_rationale ?? "Gamma flow board combines turnover, volume, and day move proxies." },
    { label: "Strongest Narrative", value: strongestNarrative?.label ?? "N/A", body: strongestNarrative ? `${pct(strongestNarrative.market_cap_change_pct_24h)} | ${compactMoney(strongestNarrative.volume_24h)} volume` : "Narrative baskets will appear once the workspace loads." }
  ] satisfies FocusRow[];
  $: narrativeOptions = Array.from(new Set([...defaultNarrativeOptions, ...(workspace?.narratives ?? []).map((basket) => basket.label)]));
  $: tokenChartSeries = history?.points?.length ? [{ id: "price", label: detail ? `${detail.symbol.toUpperCase()} price` : "Price", color: "var(--chart-primary)", type: "area", data: history.points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.price })).filter((point): point is { time: number; value: number } => point.time != null) }] : [];
  $: syntheticChartSeries = syntheticPortfolio ? [
    { id: "basket", label: "Synthetic basket", color: "var(--chart-primary)", type: "area", data: syntheticPortfolio.portfolio_points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.value })).filter((point): point is { time: number; value: number } => point.time != null) },
    { id: "benchmark", label: syntheticPortfolio.benchmark_label, color: "var(--chart-secondary)", type: "line", lineStyle: "dashed", data: syntheticPortfolio.benchmark_points.map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.value })).filter((point): point is { time: number; value: number } => point.time != null) }
  ] : [];
  $: activeHeroSeries = heroCanvas === "basket" && syntheticChartSeries.length ? syntheticChartSeries : tokenChartSeries;
  $: heroTitle = heroCanvas === "basket" && syntheticPortfolio ? "Synthetic Basket" : detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Select a token";
  $: heroDescription = heroCanvas === "basket" && syntheticPortfolio ? syntheticPortfolio.summary ?? "Synthetic basket analytics will appear once Gamma can align the selected token histories." : detail?.description ?? "Use Overview to find a name, then Deep Dive to anchor a single token or promote a custom basket into the hero canvas.";
  $: basketPresets = [{ id: "custom", label: "Custom", text: syntheticText }, ...((workspace?.narratives ?? []).filter((basket) => basket.top_tokens.length > 0).map((basket) => ({ id: basket.basket_id, label: basket.label, text: narrativePresetText(basket) })) ?? [])] satisfies BasketPreset[];
  $: benchmarkCandidates = Array.from(new Map(([detail, ...screenTokens.slice(0, 12)].filter((token): token is CryptoToken => token != null).map((token) => [token.token_id, token]))).values());
  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: previewRows = buildSyntheticPreviewRows(parsedSynthetic, screenTokens);
  $: recognizedPreviewCount = previewRows.filter((row) => row.resolvedToken != null).length;
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Crypto</p>
        <div class="headline-title-row">
          <h2>Crypto Research</h2>
          {#if loading}<span class="loading-pill">Refreshing</span>{/if}
          {#if portfolioLoading}<span class="loading-pill secondary-pill">Building basket</span>{/if}
        </div>
      </div>
      <div class="header-badges">
        {#if detail?.layer_bucket}<span>{detail.layer_bucket}</span>{/if}
        {#if detail?.chain}<span>{detail.chain}</span>{/if}
        {#if strongestNarrative}<span>{strongestNarrative.label} leads</span>{/if}
      </div>
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
            <strong class="headline-kpi-value">{metric.value}</strong>
            {#if metric.meta}<small class="headline-kpi-meta">{metric.meta}</small>{/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="context-bar">
      <div class="context-group wide-group">
        <label class="search-field"><span>Search</span><input bind:value={query} placeholder="bitcoin, solana, ai, defi..." on:keydown={handleSearchKeydown} /></label>
        <label><span>Narrative</span><select bind:value={narrative}>{#each narrativeOptions as option}<option value={option}>{option || "All narratives"}</option>{/each}</select></label>
      </div>
      <div class="context-group">
        <label><span>Chain</span><input bind:value={chain} placeholder="Ethereum, Solana, Base..." /></label>
        <label><span>Sort</span><select bind:value={sortBy}>{#each sortOptions as option}<option value={option.value}>{option.label}</option>{/each}</select></label>
      </div>
      <div class="context-group">
        <label><span>Min Mcap</span><input bind:value={minMarketCap} placeholder="1000000000" /></label>
        <label><span>Min Volume</span><input bind:value={minVolume} placeholder="25000000" /></label>
        <label><span>Min Turnover</span><input bind:value={minTurnoverRatio} placeholder="0.05" /></label>
      </div>
      <div class="context-actions">
        <button type="button" on:click={() => runWorkspace(false)} disabled={loading}>{loading ? "Loading..." : "Run Screen"}</button>
        <button type="button" class="secondary" on:click={() => runWorkspace(true)} disabled={loading}>Refresh Sources</button>
      </div>
    </div>

    <p class="coverage-note">{coverageNote}</p>

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

  <div class="workspace-grid">
    <div class="primary-column">
      {#if mode === "overview"}
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Overview</p>
              <h3>Layer Return Mosaic</h3>
            </div>
            <small>Tiles size by market cap, color by 24H return</small>
          </div>

          <div class="mosaic-strip">
            <CryptoMosaicBoard
              label="Layer 1"
              subtitle="Largest surface"
              variant="large"
              tiles={layer1Tiles}
              selectedTokenId={detail?.token_id ?? null}
              emptyMessage="No Layer 1 names in the current screen."
              onSelectToken={(tokenId) => chooseToken(tokenId)}
            />
            <CryptoMosaicBoard
              label="Layer 2"
              subtitle="Secondary mosaic"
              variant="medium"
              tiles={layer2Tiles}
              selectedTokenId={detail?.token_id ?? null}
              emptyMessage="No Layer 2 names in the current screen."
              onSelectToken={(tokenId) => chooseToken(tokenId)}
            />
            <CryptoMosaicBoard
              label="Layer 3"
              subtitle="Exploratory surface"
              variant="small"
              tiles={layer3Tiles}
              selectedTokenId={detail?.token_id ?? null}
              emptyMessage="Layer 3 coverage is still sparse in the current screen."
              onSelectToken={(tokenId) => chooseToken(tokenId)}
            />
          </div>
        </article>

        <div class="detail-split">
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Pulse</p>
                <h3>Market Pulse</h3>
              </div>
              <small>What matters now</small>
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
                    <p>{basket.description ?? "Gamma-selected basket mapped from CoinGecko category coverage."}</p>
                  </button>
                {/each}
              {:else}
                <p class="muted">Narrative baskets will appear with the screener universe.</p>
              {/if}
            </div>
          </article>
        </div>

        <div class="detail-split">
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Opportunity Board</p>
                <h3>Flow Proxy Leaders</h3>
              </div>
              <small>Gamma turnover + move proxy</small>
            </div>

            <div class="table-wrap">
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
                      <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id, "deep_dive")}>
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

          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Selection</p>
                <h3>Active Token Context</h3>
              </div>
              <small>{detail?.symbol?.toUpperCase() ?? "None"}</small>
            </div>

            <div class="meta-flat">
              <div class="meta-row">
                <span>Name</span>
                <strong>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Pick a token"}</strong>
              </div>
              <div class="meta-row">
                <span>Narrative</span>
                <strong>{detail?.narrative_labels?.[0] ?? detail?.layer_bucket ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Comparison</span>
                <strong>{comparison?.target_label ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Flow</span>
                <strong class={flowToneClass(flow?.flow_signal_label)}>{flow?.flow_signal_label ?? "N/A"}</strong>
              </div>
            </div>

            <div class="builder-actions">
              <button type="button" on:click={() => detail && chooseToken(detail.token_id, "deep_dive")} disabled={!detail}>Open Deep Dive</button>
              <button type="button" class="secondary" on:click={() => detail && chooseToken(detail.token_id, "flows_liquidity")} disabled={!detail}>Open Flows</button>
            </div>
          </article>
        </div>
      {:else if mode === "deep_dive"}
        <article class="panel hero-panel">
          <div class="panel-header top-line">
            <div class="headline-block">
              <p class="eyebrow">Deep Dive</p>
              <h3>{heroTitle}</h3>
              <p class="muted">{heroDescription}</p>
            </div>
            <div class="hero-controls">
              <div class="canvas-toggle" role="tablist" aria-label="Hero canvas">
                {#each heroCanvasOptions as option}
                  <button type="button" class:selected={option.id === heroCanvas} on:click={() => (heroCanvas = option.id)} disabled={option.id === "basket" && !syntheticPortfolio}>
                    {option.label}
                  </button>
                {/each}
              </div>
              <div class="badge-stack">
                {#if detail?.chain}<span>{detail.chain}</span>{/if}
                {#if detail?.market_cap_rank != null}<span>Rank {detail.market_cap_rank}</span>{/if}
                {#if detail?.layer_bucket}<span>{detail.layer_bucket}</span>{/if}
              </div>
            </div>
          </div>

          <div class="kpi-grid">
            {#if heroCanvas === "basket" && syntheticPortfolio}
              <article class="metric">
                <span>Basket Return</span>
                <strong>{pct(syntheticPortfolio.cumulative_return_pct)}</strong>
                <small>{syntheticPortfolio.lookback_days}D window</small>
              </article>
              <article class="metric">
                <span>Vs {syntheticPortfolio.benchmark_label}</span>
                <strong class={toneClass(syntheticPortfolio.relative_return_pct)}>{pct(syntheticPortfolio.relative_return_pct)}</strong>
                <small>{pct(syntheticPortfolio.benchmark_return_pct)}</small>
              </article>
              <article class="metric">
                <span>Weighted Turnover</span>
                <strong>{ratio(syntheticPortfolio.weighted_turnover_ratio_24h)}</strong>
                <small>Mcap {compactMoney(syntheticPortfolio.weighted_market_cap)}</small>
              </article>
              <article class="metric">
                <span>Effective Positions</span>
                <strong>{syntheticPortfolio.effective_positions?.toFixed(1) ?? "N/A"}</strong>
                <small>Vol {pct(syntheticPortfolio.annualized_volatility_pct)}</small>
              </article>
            {:else}
              <article class="metric">
                <span>Price</span>
                <strong>{money(detail?.current_price, detail?.current_price && detail.current_price < 5 ? 4 : 2)}</strong>
                <small class={toneClass(detail?.price_change_pct_24h)}>{pct(detail?.price_change_pct_24h)}</small>
              </article>
              <article class="metric">
                <span>Market Cap</span>
                <strong>{compactMoney(detail?.market_cap)}</strong>
                <small>FDV {compactMoney(detail?.fully_diluted_valuation)}</small>
              </article>
              <article class="metric">
                <span>24H Volume</span>
                <strong>{compactMoney(detail?.total_volume)}</strong>
                <small>Turnover {ratio(detail?.turnover_ratio_24h)}</small>
              </article>
              <article class="metric">
                <span>Screen Score</span>
                <strong>{detail?.screen_score?.toFixed(1) ?? "N/A"}</strong>
                <small>{detail?.screen_rationale ?? "Gamma heuristic"}</small>
              </article>
            {/if}
          </div>

          <TimeSeriesChart
            series={activeHeroSeries}
            height={360}
            emptyMessage={heroCanvas === "basket" ? "Build a synthetic basket to promote it into the hero canvas." : "Select a token to load price history."}
          />

          <div class="chart-foot">
            <span>{heroCanvas === "basket" && syntheticPortfolio ? syntheticPortfolio.transformation_note ?? "Synthetic basket history is read-only and derived from CoinGecko daily closes." : detail?.transformation_note ?? "Gamma keeps this surface read-only and provenance-rich."}</span>
            <strong>{heroCanvas === "basket" && syntheticPortfolio ? `${syntheticPortfolio.source_provider} | ${syntheticPortfolio.origin}` : detail ? `${detail.source_provider} | ${detail.origin}` : "No active token"}</strong>
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
                <p>Relative 7D performance difference versus the current comparison target.</p>
              </div>
              <div class="focus-row">
                <span class="focus-label">30D Gap</span>
                <strong class={`focus-value ${toneClass(comparison?.price_gap_pct_30d)}`}>{pct(comparison?.price_gap_pct_30d)}</strong>
                <p>Relative 30D performance difference versus the current comparison target.</p>
              </div>
              <div class="focus-row">
                <span class="focus-label">Mcap Ratio</span>
                <strong class="focus-value">{ratio(comparison?.market_cap_ratio)}</strong>
                <p>Subject market cap divided by the target market cap.</p>
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

            <div class="meta-flat">
              <div class="meta-row">
                <span>Supply</span>
                <strong>{detail?.circulating_supply?.toLocaleString() ?? "N/A"} / {detail?.total_supply?.toLocaleString() ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Max Supply</span>
                <strong>{detail?.max_supply?.toLocaleString() ?? "N/A"}</strong>
              </div>
              <div class="meta-row">
                <span>Contract</span>
                <strong>{detail?.contract_address ?? "Native / unavailable"}</strong>
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

        <div class="detail-split">
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
                    <p>{basket.description ?? "Gamma-selected basket mapped from CoinGecko category coverage."}</p>
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
              <p class="muted">{flow?.summary ?? "Flow mode interprets the selected token through DEX participation, concentration, and slippage proxies."}</p>
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
              <small>Share of reported spot volume</small>
            </article>
            <article class="metric">
              <span>Buy Pressure</span>
              <strong class={toneClass((flow?.buy_pressure_pct ?? 50) - 50)}>{pct(flow?.buy_pressure_pct)}</strong>
              <small>{flow?.active_trader_proxy_24h?.toLocaleString() ?? "N/A"} trader proxy</small>
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
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Liquidity</p>
                <h3>Pool Tape</h3>
              </div>
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
              <div class="focus-row"><span class="focus-label">Liquidity</span><strong class={flowToneClass(flow?.liquidity_concentration_label)}>{flow?.liquidity_concentration_label ?? "N/A"}</strong><p>How dependent the token looks on one or two pools for available depth.</p></div>
              <div class="focus-row"><span class="focus-label">Flow Regime</span><strong class={flowToneClass(flow?.flow_signal_label)}>{flow?.flow_signal_label ?? "N/A"}</strong><p>Gamma first-pass interpretation of buy-side versus sell-side pool activity.</p></div>
              <div class="focus-row"><span class="focus-label">Reserve / Mcap</span><strong>{pct(flow?.reserve_to_market_cap_ratio != null ? flow.reserve_to_market_cap_ratio * 100 : null)}</strong><p>Total matched reserve as a share of market cap.</p></div>
              <div class="focus-row"><span class="focus-label">Buyer / Seller</span><strong>{ratio(flow?.participant_balance_ratio)}</strong><p>Buyer versus seller count proxy from tracked pools.</p></div>
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

          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Cross-Section</p>
                <h3>Flow Leaderboard</h3>
              </div>
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
                      <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id)}>
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
              <h3>{mode === "overview" ? "Quick Take" : "Flow Signal"}</h3>
            </div>
            <small>{detail?.symbol?.toUpperCase() ?? "None"}</small>
          </div>

          <div class="focus-list">
            <div class="focus-row compact-focus">
              <span class="focus-label">Name</span>
              <strong>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Pick a token"}</strong>
              <p>{detail?.screen_rationale ?? "Select a token from the mosaic or screener table to anchor the research surface."}</p>
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

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Universe</p>
            <h3>Tokens</h3>
          </div>
          <small>{JSON.stringify({ query, narrative, chain, sortBy })}</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Token</th><th>Price</th><th>24H</th><th>Mcap</th><th>Turnover</th><th>Score</th></tr>
            </thead>
            <tbody>
              {#if workspace?.tokens?.length}
                {#each workspace.tokens as token}
                  <tr class:selected={token.token_id === detail?.token_id} on:click={() => chooseToken(token.token_id)}>
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
    gap: 0.5rem;
  }

  .view {
    gap: 0.6rem;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.58fr) minmax(22rem, 0.96fr);
    gap: 0.5rem;
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
    background: var(--panel-bg);
    padding: 0.9rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel {
    gap: 0.35rem;
  }

  .panel-header,
  .header-top,
  .chart-foot,
  .top-line {
    display: flex;
    justify-content: space-between;
    gap: 0.8rem;
    align-items: flex-start;
  }

  .headline-block,
  .market-title {
    min-width: 0;
  }

  .headline-title-row,
  .context-bar,
  .context-group,
  .context-actions,
  .mode-kpi-row,
  .mosaic-strip,
  .builder-actions,
  .hero-controls,
  .header-badges,
  .badge-stack,
  .headline-strip {
    display: flex;
    gap: 0.5rem;
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
  .context-group,
  .builder-actions {
    flex-wrap: wrap;
  }

  .header-badges span,
  .badge-stack span {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-1);
    padding: 0.18rem 0.45rem;
    font-size: 0.72rem;
    white-space: nowrap;
  }

  .context-bar {
    flex-wrap: wrap;
    align-items: end;
  }

  .wide-group {
    flex: 1 1 24rem;
  }

  .context-actions {
    margin-left: auto;
  }

  .mode-bar,
  .canvas-toggle {
    display: inline-grid;
    background: var(--surface-0);
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
  }

  .mode-bar button:last-child,
  .canvas-toggle button:last-child {
    border-right: 0;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-0);
    padding: 0.42rem 0.72rem;
    font: inherit;
    font-size: 0.78rem;
    cursor: pointer;
  }

  .mode-bar button.selected,
  .canvas-toggle button.selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .mode-bar button:hover,
  .canvas-toggle button:hover,
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
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: 0.2rem 0.5rem;
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
    padding: 0.42rem 0.62rem;
    font: inherit;
    font-size: 0.82rem;
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
    gap: 0.22rem;
  }

  label > span,
  .eyebrow,
  .headline-kpi-label,
  .section-label,
  .focus-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  h2,
  h3,
  p,
  small,
  strong {
    margin: 0;
  }

  h2 {
    font-size: 1rem;
  }

  h3 {
    font-size: 0.94rem;
  }

  .headline-kpi {
    padding: 0.12rem 0.65rem 0.2rem 0.65rem;
    border-left: 1px solid var(--divider);
    text-align: right;
  }

  .headline-kpi:first-child {
    border-left: 0;
  }

  .headline-kpi-value {
    display: block;
    font-size: 0.9rem;
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
    font-size: 0.74rem;
  }

  .chart-foot {
    align-items: center;
    flex-wrap: wrap;
  }

  .chart-foot strong {
    color: var(--text-1);
    font-size: 0.72rem;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    border: 1px solid var(--divider);
    background: var(--bg-0);
  }

  .metric {
    padding: 0.55rem 0.7rem;
    border-right: 1px solid var(--divider);
    display: grid;
    gap: 0.12rem;
  }

  .metric:last-child {
    border-right: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
  }

  .metric strong {
    font-size: 0.95rem;
  }

  .metric small,
  .market-title small,
  .basket-card p,
  .focus-row p,
  .meta-row span {
    color: var(--text-2);
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

  .mosaic-strip {
    align-items: stretch;
  }

  .focus-row,
  .meta-row,
  .note-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
    display: grid;
    gap: 0.12rem;
  }

  .focus-row:first-child,
  .meta-row:first-child,
  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .focus-value {
    font-size: 0.9rem;
  }

  .compact-focus p {
    color: var(--text-2);
  }

  .basket-card {
    border: 1px solid var(--divider);
    background: transparent;
    padding: 0.55rem;
    display: grid;
    gap: 0.15rem;
    text-align: left;
  }

  .tag-list {
    grid-template-columns: repeat(auto-fit, minmax(8rem, max-content));
  }

  .tag-chip {
    border: 1px solid var(--divider);
    padding: 0.22rem 0.45rem;
    color: var(--text-1);
    background: var(--surface-0);
    font-size: 0.72rem;
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

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
    padding: 0.45rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
  }

  tbody td {
    padding: 0.5rem 0.55rem;
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
    gap: 0.5rem;
  }

  .search-field input {
    min-width: 15rem;
  }

  @media (max-width: 1180px) {
    .workspace-grid,
    .detail-split {
      grid-template-columns: 1fr;
    }

    .mosaic-strip {
      display: grid;
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .mode-kpi-row,
    .context-bar,
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
  }
</style>
