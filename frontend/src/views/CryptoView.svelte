<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { parseApiTimestampToUtcSeconds } from "../lib/chart-data";
  import type {
    CryptoComparison,
    CryptoDexLiquiditySummary,
    CryptoPriceHistoryResponse,
    CryptoToken,
    CryptoWorkspaceResponse
  } from "../lib/api/types";
  import type { CryptoSortBy, CryptoWorkspaceLoadOptions } from "../lib/stores/app";

  export let workspace: CryptoWorkspaceResponse | null = null;
  export let detail: CryptoToken | null = null;
  export let history: CryptoPriceHistoryResponse | null = null;
  export let liquidity: CryptoDexLiquiditySummary | null = null;
  export let comparison: CryptoComparison | null = null;
  export let loading = false;
  export let onLoadWorkspace: (options?: CryptoWorkspaceLoadOptions) => Promise<unknown> | void;
  export let onSelectToken: (tokenId: string) => Promise<unknown> | void;

  let query = "";
  let narrative = "";
  let chain = "";
  let sortBy: CryptoSortBy = "market_cap_desc";
  let minMarketCap = "";
  let minVolume = "";
  let minTurnoverRatio = "";
  let chartSeries: ChartSeries[] = [];

  const narrativeOptions = ["", "Layer 1", "Layer 2", "DeFi", "AI", "DePIN", "Gaming", "Meme"];
  const sortOptions: Array<{ value: CryptoSortBy; label: string }> = [
    { value: "market_cap_desc", label: "Market Cap" },
    { value: "screen_score_desc", label: "Screen Score" },
    { value: "volume_desc", label: "Volume" },
    { value: "turnover_desc", label: "Turnover" },
    { value: "momentum_desc", label: "Momentum" },
    { value: "fdv_premium_asc", label: "FDV Discount" }
  ];

  const money = (value: number | null | undefined, digits = 0) =>
    value == null
      ? "N/A"
      : new Intl.NumberFormat(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: digits
        }).format(value);

  const compactMoney = (value: number | null | undefined) => {
    if (value == null) {
      return "N/A";
    }
    const absolute = Math.abs(value);
    if (absolute >= 1_000_000_000) {
      return `$${(value / 1_000_000_000).toFixed(1)}B`;
    }
    if (absolute >= 1_000_000) {
      return `$${(value / 1_000_000).toFixed(1)}M`;
    }
    if (absolute >= 1_000) {
      return `$${(value / 1_000).toFixed(1)}K`;
    }
    return money(value, 0);
  };

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${value.toFixed(digits)}%`;

  const ratio = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${value.toFixed(digits)}x`;

  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString() : "N/A";

  function tokenTone(value: number | null | undefined) {
    if (value == null) {
      return "";
    }
    if (value >= 8) {
      return "positive";
    }
    if (value <= -8) {
      return "negative";
    }
    return "";
  }

  function screenKey() {
    return {
      query,
      narrative,
      chain,
      sortBy,
      minMarketCap,
      minVolume,
      minTurnoverRatio
    };
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
      limit: 40,
      forceRefresh
    };
  }

  async function runWorkspace(forceRefresh = false) {
    await onLoadWorkspace(buildPayload(forceRefresh));
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void runWorkspace();
    }
  }

  function applyNarrative(label: string) {
    narrative = label;
    void runWorkspace();
  }

  onMount(() => {
    if (!workspace?.tokens?.length) {
      void runWorkspace();
    }
  });

  $: chartSeries = history?.points?.length
    ? [
        {
          id: "price",
          label: "Price",
          color: "#d4a054",
          type: "line",
          data: history.points
            .map((point) => ({
              time: parseApiTimestampToUtcSeconds(point.timestamp),
              value: point.price
            }))
            .filter((point): point is { time: number; value: number } => point.time != null)
        }
      ]
    : [];
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel hero-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Crypto</p>
            <h2>{detail ? `${detail.name} (${detail.symbol.toUpperCase()})` : "Select a token"}</h2>
            <p class="muted">
              {detail?.description ?? "Screen the token universe and select an asset to load profile, history, liquidity, and comparison context."}
            </p>
          </div>
          {#if detail}
            <div class="badge-stack">
              {#if detail.chain}
                <span>{detail.chain}</span>
              {/if}
              {#if detail.market_cap_rank != null}
                <span>Rank {detail.market_cap_rank}</span>
              {/if}
              {#if detail.geckoterminal_network}
                <span>{detail.geckoterminal_network}</span>
              {/if}
            </div>
          {/if}
        </div>

        <div class="kpi-grid">
          <article class="metric">
            <span>Price</span>
            <strong>{money(detail?.current_price, detail?.current_price && detail.current_price < 5 ? 4 : 2)}</strong>
            <small class={tokenTone(detail?.price_change_pct_24h)}>{pct(detail?.price_change_pct_24h)}</small>
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
        </div>

        <TimeSeriesChart
          series={chartSeries}
          height={360}
          emptyMessage="Select a token to load price history."
        />

        <div class="chart-foot">
          <span>{detail?.transformation_note ?? "Gamma keeps this surface read-only and provenance-rich."}</span>
          <strong>{detail ? `${detail.source_provider} | ${detail.origin}` : "No active token"}</strong>
        </div>
      </article>

      <div class="detail-split">
        <article class="panel narrative-panel">
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
                  <small>{pct(basket.market_cap_change_pct_24h)} | {compactMoney(basket.volume_24h)} vol</small>
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
              <p class="eyebrow">Liquidity</p>
              <h3>DEX View</h3>
            </div>
            <small>{liquidity?.dominant_dex ?? "N/A"}</small>
          </div>

          <div class="kpi-grid compact-kpi">
            <article class="metric">
              <span>Reserve</span>
              <strong>{compactMoney(liquidity?.total_reserve_usd)}</strong>
            </article>
            <article class="metric">
              <span>24H Flow</span>
              <strong>{compactMoney(liquidity?.total_volume_24h)}</strong>
            </article>
            <article class="metric">
              <span>Buys / Sells</span>
              <strong>{liquidity ? `${liquidity.total_buys_24h}/${liquidity.total_sells_24h}` : "N/A"}</strong>
            </article>
          </div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Pool</th>
                  <th>DEX</th>
                  <th>Reserve</th>
                  <th>Vol 24H</th>
                  <th>Flow</th>
                </tr>
              </thead>
              <tbody>
                {#if liquidity?.pools?.length}
                  {#each liquidity.pools.slice(0, 6) as pool}
                    <tr>
                      <td>
                        <strong>{pool.pair_name}</strong>
                        <small>{pool.network}</small>
                      </td>
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

          {#if liquidity?.warnings?.length}
            <div class="notes-list">
              {#each liquidity.warnings as warning}
                <div class="note-row">
                  <span class="note-tag">Warning</span>
                  <p>{warning}</p>
                </div>
              {/each}
            </div>
          {/if}
        </article>
      </div>

      <div class="detail-split">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Comparison</p>
              <h3>Relative Context</h3>
            </div>
            <small>{comparison?.target_label ?? "N/A"}</small>
          </div>

          <div class="dynamics-flat">
            <div class="dynamics-row">
              <span class="dyn-label">Target</span>
              <strong class="dyn-value">{comparison?.target_kind ?? "N/A"}</strong>
              <p class="dyn-body">{comparison?.summary ?? "Comparison context will appear once Gamma resolves a target."}</p>
            </div>
            <div class="dynamics-row">
              <span class="dyn-label">7D Gap</span>
              <strong class={`dyn-value ${tokenTone(comparison?.price_gap_pct_7d)}`}>{pct(comparison?.price_gap_pct_7d)}</strong>
              <p class="dyn-body">Relative 7D performance difference versus the current target.</p>
            </div>
            <div class="dynamics-row">
              <span class="dyn-label">30D Gap</span>
              <strong class={`dyn-value ${tokenTone(comparison?.price_gap_pct_30d)}`}>{pct(comparison?.price_gap_pct_30d)}</strong>
              <p class="dyn-body">Relative 30D performance difference versus the current target.</p>
            </div>
            <div class="dynamics-row">
              <span class="dyn-label">Mcap Ratio</span>
              <strong class="dyn-value">{ratio(comparison?.market_cap_ratio)}</strong>
              <p class="dyn-body">Subject market cap divided by target market cap.</p>
            </div>
            <div class="dynamics-row">
              <span class="dyn-label">Turnover Gap</span>
              <strong class={`dyn-value ${tokenTone((comparison?.turnover_gap ?? 0) * 100)}`}>{ratio(comparison?.turnover_gap)}</strong>
              <p class="dyn-body">Difference in 24H turnover ratio versus the comparison target.</p>
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
            {#each detail?.categories ?? [] as tag}
              <span class="tag-chip">{tag}</span>
            {/each}
          </div>
        </article>
      </div>
    </div>

    <aside class="support-column">
      <article class="panel control-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Discovery</p>
            <h3>Token Screener</h3>
          </div>
          <strong>{workspace?.tokens.length ?? 0} rows</strong>
        </div>

        <label>
          <span>Search</span>
          <input bind:value={query} placeholder="bitcoin, solana, ai, defi..." on:keydown={handleSearchKeydown} />
        </label>

        <div class="field-grid">
          <label>
            <span>Narrative</span>
            <select bind:value={narrative}>
              {#each narrativeOptions as option}
                <option value={option}>{option || "All narratives"}</option>
              {/each}
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select bind:value={sortBy}>
              {#each sortOptions as option}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </label>
        </div>

        <div class="field-grid">
          <label>
            <span>Chain</span>
            <input bind:value={chain} placeholder="Ethereum, Solana, Base..." />
          </label>
          <label>
            <span>Min Turnover</span>
            <input bind:value={minTurnoverRatio} placeholder="0.05" />
          </label>
        </div>

        <div class="field-grid">
          <label>
            <span>Min Market Cap</span>
            <input bind:value={minMarketCap} placeholder="1000000000" />
          </label>
          <label>
            <span>Min Volume</span>
            <input bind:value={minVolume} placeholder="25000000" />
          </label>
        </div>

        {#if workspace?.warnings?.length}
          <div class="notes-list">
            {#each workspace.warnings as warning}
              <div class="note-row">
                <span class="note-tag">Note</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {/if}

        <div class="builder-actions">
          <button type="button" on:click={() => runWorkspace(false)} disabled={loading}>
            {loading ? "Loading..." : "Run Screen"}
          </button>
          <button type="button" class="secondary" on:click={() => runWorkspace(true)} disabled={loading}>
            Refresh Sources
          </button>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Universe</p>
            <h3>Tokens</h3>
          </div>
          <small>{JSON.stringify(screenKey())}</small>
        </div>

        <div class="table-wrap screener-table">
          <table>
            <thead>
              <tr>
                <th>Token</th>
                <th>Price</th>
                <th>24H</th>
                <th>Mcap</th>
                <th>Turnover</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {#if workspace?.tokens?.length}
                {#each workspace.tokens as token}
                  <tr class:selected={token.token_id === detail?.token_id} on:click={() => onSelectToken(token.token_id)}>
                    <td>
                      <div class="market-title">
                        <strong>{token.name}</strong>
                        <small>{token.symbol.toUpperCase()} | {token.chain ?? "Unknown chain"}</small>
                      </div>
                    </td>
                    <td>{money(token.current_price, token.current_price && token.current_price < 5 ? 4 : 2)}</td>
                    <td class={tokenTone(token.price_change_pct_24h)}>{pct(token.price_change_pct_24h)}</td>
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
  .workspace-grid,
  .primary-column,
  .support-column,
  .detail-split,
  .builder-actions,
  .notes-list,
  .tag-list,
  .basket-grid {
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
    background: linear-gradient(180deg, rgba(18, 17, 12, 0.98), rgba(10, 10, 10, 0.95));
    padding: 1.05rem;
  }

  .hero-panel,
  .control-panel,
  .table-panel,
  .narrative-panel {
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
  .market-title {
    min-width: 0;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
  }

  .compact-kpi {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric {
    border-left: 1px solid rgba(84, 72, 41, 0.35);
    padding: 0.2rem 1rem;
    text-align: center;
  }

  .metric:first-child {
    border-left: 0;
    padding-left: 0;
  }

  .metric strong {
    display: block;
    margin: 0.22rem 0;
    font-size: 1rem;
    color: var(--text-0);
  }

  .eyebrow,
  label > span,
  .metric span,
  .dyn-label,
  .meta-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  h2,
  h3,
  p,
  small,
  strong {
    margin: 0;
  }

  .muted,
  small,
  .dyn-body,
  .note-row p {
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  .badge-stack,
  .tag-list {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .badge-stack span,
  .tag-chip {
    border: 1px solid rgba(212, 160, 84, 0.24);
    background: rgba(212, 160, 84, 0.07);
    color: #f0d3a2;
    padding: 0.34rem 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
  }

  label {
    display: grid;
    gap: 0.4rem;
  }

  input,
  select,
  button {
    border: 1px solid rgba(212, 160, 84, 0.24);
    background: #12100d;
    color: var(--text-0);
    padding: 0.56rem 0.72rem;
    font: inherit;
    width: 100%;
    min-height: 3rem;
  }

  button {
    cursor: pointer;
  }

  .secondary {
    background: rgba(212, 160, 84, 0.08);
  }

  .field-grid,
  .basket-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .basket-card {
    display: grid;
    gap: 0.35rem;
    text-align: left;
    border: 1px solid rgba(212, 160, 84, 0.18);
    background: rgba(26, 23, 17, 0.8);
    padding: 0.9rem;
  }

  .basket-card span {
    color: #f0d3a2;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.66rem;
  }

  .basket-card strong {
    color: var(--text-0);
  }

  .table-wrap {
    overflow: auto;
    border-top: 1px solid rgba(84, 72, 41, 0.35);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.72rem 0.55rem;
    border-bottom: 1px solid rgba(84, 72, 41, 0.25);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(12, 11, 8, 0.88);
  }

  td small {
    display: block;
    margin-top: 0.18rem;
  }

  .screener-table tbody tr {
    cursor: pointer;
  }

  .screener-table tbody tr.selected {
    background: rgba(212, 160, 84, 0.08);
  }

  .notes-list,
  .meta-flat,
  .dynamics-flat {
    display: grid;
    gap: 0;
  }

  .note-row,
  .meta-row,
  .dynamics-row {
    display: grid;
    gap: 0.75rem;
    padding: 0.7rem 0;
    border-top: 1px solid rgba(84, 72, 41, 0.25);
  }

  .note-row:first-child,
  .meta-row:first-child,
  .dynamics-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-row {
    grid-template-columns: 5.5rem minmax(0, 1fr);
  }

  .meta-row {
    grid-template-columns: 7rem minmax(0, 1fr);
  }

  .dynamics-row {
    grid-template-columns: 7rem 5rem minmax(0, 1fr);
    align-items: baseline;
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.64rem;
  }

  .dyn-value {
    color: var(--text-0);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1320px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1080px) {
    .detail-split,
    .kpi-grid,
    .compact-kpi,
    .field-grid,
    .basket-grid {
      grid-template-columns: 1fr;
    }

    .dynamics-row,
    .note-row,
    .meta-row {
      grid-template-columns: 1fr;
      gap: 0.3rem;
    }
  }

  @media (max-width: 980px) {
    .panel-header,
    .rail-header,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .badge-stack {
      justify-content: flex-start;
    }
  }
</style>
