<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart from "./TimeSeriesChart.svelte";
  import {
    buildHeroPriceChartSeries,
    defaultHeroPriceChartSettings,
    heroPriceChartAvailability,
    heroPriceSettingsStorageKey,
    movingAverageWindows,
    normalizeHeroPriceChartSettings,
    type HeroPriceChartSettings,
    type HeroPricePoint,
    type MovingAverageWindow
  } from "../lib/view-models/hero-price-chart";

  export let chartKey: string;
  export let points: HeroPricePoint[] = [];
  export let height = 320;
  export let emptyMessage = "CHART UNAVAILABLE";
  export let showLegend = true;

  let settings: HeroPriceChartSettings = normalizeHeroPriceChartSettings(defaultHeroPriceChartSettings);
  let mounted = false;

  $: storageKey = heroPriceSettingsStorageKey(chartKey);
  $: availability = heroPriceChartAvailability(points);
  $: effectiveSettings = normalizeHeroPriceChartSettings({
    ...settings,
    priceStyle: settings.priceStyle === "candlestick" && !availability.hasOhlc ? "line" : settings.priceStyle,
    volumeOverlay: settings.volumeOverlay && availability.hasVolume,
    movingAverages: availability.hasClose ? settings.movingAverages : []
  });
  $: series = buildHeroPriceChartSeries(points, effectiveSettings);

  onMount(() => {
    mounted = true;
    const stored = readStoredSettings(storageKey);
    if (stored) {
      settings = stored;
    }
  });

  $: if (mounted) {
    writeStoredSettings(storageKey, settings);
  }

  function readStoredSettings(key: string): HeroPriceChartSettings | null {
    if (typeof window === "undefined" || !window.localStorage) {
      return null;
    }
    try {
      return normalizeHeroPriceChartSettings(JSON.parse(window.localStorage.getItem(key) ?? "null"));
    } catch {
      return normalizeHeroPriceChartSettings(null);
    }
  }

  function writeStoredSettings(key: string, value: HeroPriceChartSettings) {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    window.localStorage.setItem(key, JSON.stringify(value));
  }

  function setPriceStyle(priceStyle: HeroPriceChartSettings["priceStyle"]) {
    settings = { ...settings, priceStyle };
  }

  function toggleVolumeOverlay() {
    settings = { ...settings, volumeOverlay: !settings.volumeOverlay };
  }

  function toggleMovingAverage(window: MovingAverageWindow) {
    const movingAverages = settings.movingAverages.includes(window)
      ? settings.movingAverages.filter((item) => item !== window)
      : [...settings.movingAverages, window];
    settings = { ...settings, movingAverages };
  }
</script>

<div class="hero-price-chart">
  <details class="settings-menu">
    <summary class="settings-button" aria-label="Hero chart settings" title="Hero chart settings">*</summary>
    <section class="settings-popover" aria-label="Chart Settings">
      <div class="settings-title">Chart Settings</div>

      <div class="settings-group" aria-label="Price style">
        <button class:active={settings.priceStyle === "line"} type="button" on:click={() => setPriceStyle("line")}>Line</button>
        <button
          class:active={settings.priceStyle === "candlestick"}
          type="button"
          disabled={!availability.hasOhlc}
          on:click={() => setPriceStyle("candlestick")}
        >
          {availability.hasOhlc ? "Candles" : "Candles unavailable"}
        </button>
      </div>

      <div class="settings-group" aria-label="Volume">
        <button
          class:active={settings.volumeOverlay}
          type="button"
          disabled={!availability.hasVolume}
          on:click={toggleVolumeOverlay}
        >
          {availability.hasVolume ? "Volume overlay" : "Volume unavailable"}
        </button>
      </div>

      <div class="settings-group" aria-label="Moving averages">
        {#each movingAverageWindows as window}
          <button
            class:active={settings.movingAverages.includes(window)}
            type="button"
            disabled={!availability.hasClose}
            on:click={() => toggleMovingAverage(window)}
          >
            MA{window}
          </button>
        {/each}
      </div>
    </section>
  </details>

  <TimeSeriesChart {series} {height} {emptyMessage} {showLegend} />
</div>

<style>
  .hero-price-chart {
    position: relative;
  }

  .settings-menu {
    position: absolute;
    top: 4px;
    right: 4px;
    z-index: 4;
  }

  .settings-button {
    display: grid;
    width: 25px;
    height: 25px;
    place-items: center;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-1);
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
    list-style: none;
  }

  .settings-button::-webkit-details-marker {
    display: none;
  }

  .settings-menu[open] .settings-button,
  .settings-button:hover {
    border-color: var(--accent);
    color: var(--text-0);
  }

  .settings-popover {
    position: absolute;
    top: 29px;
    right: 0;
    display: grid;
    min-width: 174px;
    gap: 6px;
    padding: 8px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--surface-0);
  }

  .settings-title {
    color: var(--text-2);
    font-size: 11px;
    font-weight: 600;
    line-height: 1.2;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .settings-group {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  button {
    min-height: 25px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-1);
    padding: 3px 7px;
    font-size: 11px;
    line-height: 1.1;
    cursor: pointer;
  }

  button:hover:not(:disabled),
  button.active {
    border-color: var(--accent);
    color: var(--text-0);
  }

  button:disabled {
    color: var(--text-2);
    cursor: not-allowed;
    opacity: 0.72;
  }
</style>
