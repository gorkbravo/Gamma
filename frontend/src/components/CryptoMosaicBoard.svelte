<script lang="ts">
  import type { CryptoToken } from "../lib/api/types";
  import { mosaicStyle, type MosaicTile, type MosaicVariant } from "../lib/view-models/crypto";

  export let label = "";
  export let subtitle = "";
  export let variant: MosaicVariant = "large";
  export let tiles: MosaicTile[] = [];
  export let selectedTokenId: string | null = null;
  export let emptyMessage = "No tokens in the current slice.";
  export let onSelectToken: (tokenId: string) => Promise<unknown> | void;

  const compactMoney = (value: number | null | undefined) => {
    if (value == null) {
      return "N/A";
    }
    const absolute = Math.abs(value);
    if (absolute >= 1_000_000_000_000) {
      return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
    }
    if (absolute >= 1_000_000_000) {
      return `$${(value / 1_000_000_000).toFixed(1)}B`;
    }
    if (absolute >= 1_000_000) {
      return `$${(value / 1_000_000).toFixed(1)}M`;
    }
    if (absolute >= 1_000) {
      return `$${(value / 1_000).toFixed(1)}K`;
    }
    return `$${value.toFixed(0)}`;
  };

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${value.toFixed(digits)}%`;
</script>

<section class:layer-large={variant === "large"} class="mosaic-section">
  <div class="section-head">
    <div>
      <span class="section-label">{label}</span>
      <strong>{tiles.length} names</strong>
    </div>
    <small>{subtitle}</small>
  </div>

  <div class={`mosaic-grid ${variant}-grid`}>
    {#if tiles.length}
      {#each tiles as tile}
        <button
          type="button"
          class:selected={tile.token.token_id === selectedTokenId}
          class="mosaic-tile"
          style={mosaicStyle(tile, variant)}
          on:click={() => onSelectToken(tile.token.token_id)}
        >
          <span class="tile-symbol">{tile.token.symbol.toUpperCase()}</span>
          <strong>{pct(tile.token.price_change_pct_24h)}</strong>
          <small>{compactMoney(tile.token.market_cap)}</small>
        </button>
      {/each}
    {:else}
      <div class="empty-inline">{emptyMessage}</div>
    {/if}
  </div>
</section>

<style>
  .mosaic-section {
    display: grid;
    gap: 0.45rem;
    padding-left: 0.5rem;
    border-left: 1px solid var(--divider);
    min-width: 0;
    flex: 1 1 0;
  }

  .layer-large {
    flex: 1.85 1 0;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: baseline;
  }

  .section-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .section-head strong,
  .section-head small {
    color: var(--text-1);
    margin: 0;
  }

  .mosaic-grid {
    display: grid;
    grid-auto-flow: dense;
    gap: 0.35rem;
    min-width: 0;
  }

  .large-grid {
    grid-template-columns: repeat(12, minmax(0, 1fr));
    grid-auto-rows: minmax(2.2rem, auto);
  }

  .medium-grid {
    grid-template-columns: repeat(10, minmax(0, 1fr));
    grid-auto-rows: minmax(1.85rem, auto);
  }

  .small-grid {
    grid-template-columns: repeat(8, minmax(0, 1fr));
    grid-auto-rows: minmax(1.55rem, auto);
  }

  .mosaic-tile {
    border: 1px solid var(--divider);
    padding: 0.45rem 0.5rem;
    display: grid;
    gap: 0.15rem;
    text-align: left;
    min-width: 0;
    cursor: pointer;
  }

  .mosaic-tile.selected {
    box-shadow: inset 0 0 0 1px var(--accent);
  }

  .tile-symbol {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.62rem;
  }

  .mosaic-tile strong,
  .mosaic-tile small {
    margin: 0;
  }

  .mosaic-tile strong {
    font-size: 0.88rem;
  }

  .mosaic-tile small {
    color: var(--text-1);
    font-size: 0.68rem;
  }

  .empty-inline {
    border: 1px dashed var(--divider);
    color: var(--text-2);
    padding: 0.6rem;
    font-size: 0.78rem;
  }

  @media (max-width: 1180px) {
    .mosaic-section,
    .layer-large {
      border-left: 0;
      padding-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.5rem;
      flex: 1 1 auto;
    }
  }
</style>
