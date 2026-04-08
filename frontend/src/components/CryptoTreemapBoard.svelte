<script lang="ts">
  import type { CryptoSortBy } from "../lib/stores/app";
  import {
    cryptoSortMetricLabel,
    heatStyle,
    treemapDensityClass,
    treemapMetricText,
    treemapRectStyle,
    type CryptoTreemapSection
  } from "../lib/view-models/crypto";

  export let sections: CryptoTreemapSection[] = [];
  export let sortBy: CryptoSortBy = "market_cap_desc";
  export let selectedTokenId: string | null = null;
  export let emptyMessage = "No tokens in the current slice.";
  export let onSelectToken: (tokenId: string) => Promise<unknown> | void;

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;

  function densityEmphasis(density: string) {
    if (density === "hero") return 1.08;
    if (density === "major") return 1;
    if (density === "minor") return 0.92;
    return 0.82;
  }

  function tileTitle(
    sectionLabel: string,
    tokenName: string,
    symbol: string,
    move24h: number | null | undefined,
    metricValue: number | null | undefined
  ) {
    return `${sectionLabel} | ${tokenName} (${symbol.toUpperCase()}) | 24H ${pct(move24h)} | ${cryptoSortMetricLabel(sortBy)} ${treemapMetricText(metricValue, sortBy)}`;
  }

  $: metricLabel = cryptoSortMetricLabel(sortBy);
</script>

{#if sections.length}
  <div class="treemap-shell" aria-label={`Crypto treemap sized by ${metricLabel} and colored by 24H return`}>
    {#each sections as section}
      <section class="treemap-section" style={treemapRectStyle(section.rect)}>
        <div class="section-head">
          <span class="section-label">{section.label}</span>
          <small>{section.tokenCount} names</small>
        </div>

        <div class="section-body">
          {#each section.tiles as tile}
            {@const density = treemapDensityClass(tile.rect)}
            <button
              type="button"
              class={`treemap-tile ${density}`}
              class:selected={tile.token.token_id === selectedTokenId}
              style={`${treemapRectStyle(tile.rect)} ${heatStyle(tile.token.price_change_pct_24h, densityEmphasis(density))}`}
              title={tileTitle(section.label, tile.token.name, tile.token.symbol, tile.token.price_change_pct_24h, tile.metricValue)}
              aria-label={tileTitle(section.label, tile.token.name, tile.token.symbol, tile.token.price_change_pct_24h, tile.metricValue)}
              on:click={() => onSelectToken(tile.token.token_id)}
            >
              <div class="tile-copy">
                <div class="tile-topline">
                  <span class="tile-symbol">{tile.token.symbol.toUpperCase()}</span>
                  {#if density !== "micro"}
                    <strong
                      class={`tile-move ${
                        tile.token.price_change_pct_24h == null ? "" : tile.token.price_change_pct_24h >= 0 ? "positive" : "negative"
                      }`}
                    >
                      {pct(tile.token.price_change_pct_24h)}
                    </strong>
                  {/if}
                </div>

                {#if density === "hero"}
                  <div class="tile-bottomline">
                    <strong class="tile-name">{tile.token.name}</strong>
                    <small>{metricLabel}: {treemapMetricText(tile.metricValue, sortBy)}</small>
                  </div>
                {:else if density === "major"}
                  <div class="tile-bottomline">
                    <small>{metricLabel}: {treemapMetricText(tile.metricValue, sortBy)}</small>
                  </div>
                {:else if density === "minor"}
                  <div class="tile-bottomline">
                    <small>{treemapMetricText(tile.metricValue, sortBy)}</small>
                  </div>
                {/if}
              </div>
            </button>
          {/each}
        </div>
      </section>
    {/each}
  </div>
{:else}
  <div class="empty-inline">{emptyMessage}</div>
{/if}

<style>
  .treemap-shell {
    position: relative;
    min-height: 26rem;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--divider);
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--surface-0) 84%, transparent), transparent 44%),
      var(--bg-0);
    overflow: hidden;
  }

  .treemap-section {
    position: absolute;
    border: 1px solid color-mix(in srgb, var(--panel-strong) 72%, var(--divider));
    background: color-mix(in srgb, var(--surface-0) 76%, transparent);
    min-width: 0;
    overflow: hidden;
  }

  .section-head {
    position: absolute;
    inset: 0 0 auto 0;
    min-height: 1.5rem;
    padding: 0.28rem 0.5rem;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: center;
    background: color-mix(in srgb, var(--bg-1) 86%, transparent);
    border-bottom: 1px solid var(--divider);
    z-index: 1;
    pointer-events: none;
  }

  .section-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .section-head small {
    color: var(--text-2);
    margin: 0;
    white-space: nowrap;
  }

  .section-body {
    position: absolute;
    inset: 1.55rem 0.12rem 0.12rem 0.12rem;
  }

  .treemap-tile {
    position: absolute;
    border: 1px solid var(--divider);
    padding: 0.32rem 0.38rem;
    text-align: left;
    min-width: 0;
    color: var(--text-0);
    overflow: hidden;
  }

  .treemap-tile.selected {
    box-shadow: inset 0 0 0 1px var(--accent);
  }

  .tile-copy,
  .tile-bottomline {
    display: grid;
    gap: 0.12rem;
  }

  .tile-copy {
    height: 100%;
    align-content: space-between;
  }

  .tile-topline {
    display: flex;
    justify-content: space-between;
    gap: 0.25rem;
    align-items: start;
  }

  .tile-symbol {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
    line-height: 1.1;
  }

  .tile-move,
  .tile-name,
  .tile-bottomline small {
    margin: 0;
  }

  .tile-move {
    font-size: 0.72rem;
    line-height: 1.1;
  }

  .tile-name {
    font-size: 0.86rem;
    line-height: 1.1;
  }

  .tile-bottomline small {
    color: var(--text-1);
    font-size: 0.62rem;
    line-height: 1.2;
  }

  .treemap-tile.hero {
    padding: 0.45rem 0.5rem;
  }

  .treemap-tile.hero .tile-symbol {
    font-size: 0.72rem;
  }

  .treemap-tile.hero .tile-move {
    font-size: 0.84rem;
  }

  .treemap-tile.major .tile-symbol {
    font-size: 0.66rem;
  }

  .treemap-tile.minor {
    padding: 0.28rem 0.32rem;
  }

  .treemap-tile.minor .tile-symbol,
  .treemap-tile.minor .tile-move {
    font-size: 0.6rem;
  }

  .treemap-tile.minor .tile-bottomline small {
    font-size: 0.56rem;
  }

  .treemap-tile.micro {
    padding: 0.22rem 0.24rem;
  }

  .treemap-tile.micro .tile-copy {
    align-content: start;
  }

  .treemap-tile.micro .tile-symbol {
    font-size: 0.54rem;
    letter-spacing: 0.05em;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .empty-inline {
    border: 1px dashed var(--divider);
    color: var(--text-2);
    padding: 0.8rem;
    font-size: 0.78rem;
  }

  @media (max-width: 900px) {
    .treemap-shell {
      min-height: 22rem;
      aspect-ratio: 4 / 3;
    }

    .section-head {
      padding-inline: 0.36rem;
    }

    .section-head small {
      display: none;
    }
  }

  @media (max-width: 640px) {
    .treemap-shell {
      min-height: 20rem;
      aspect-ratio: 1 / 1;
    }

    .treemap-tile.hero .tile-name,
    .treemap-tile.major .tile-bottomline,
    .treemap-tile.minor .tile-bottomline {
      display: none;
    }
  }
</style>
