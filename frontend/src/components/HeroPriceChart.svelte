<script module lang="ts">
  import {
    buildHeroPriceChartSeries,
    defaultHeroPriceChartSettings,
    heroPriceChartAvailability,
    heroPriceSettingsStorageKey,
    movingAverageWindows,
    normalizeHeroPricePoints,
    normalizeHeroPriceChartSettings,
    type HeroPriceChartSettings,
    type HeroPricePoint,
    type MovingAverageWindow
  } from "../lib/view-models/hero-price-chart";

  export interface HeroPriceSettingsStorage {
    getItem(key: string): string | null;
    setItem(key: string, value: string): void;
  }

  export interface HeroPriceSettingsStorageState {
    loadedStorageKey: string | null;
    settings: HeroPriceChartSettings;
  }

  export function readHeroPriceChartSettings(
    storage: HeroPriceSettingsStorage | null,
    key: string
  ): HeroPriceChartSettings {
    if (!storage) {
      return normalizeHeroPriceChartSettings(null);
    }
    try {
      return normalizeHeroPriceChartSettings(JSON.parse(storage.getItem(key) ?? "null"));
    } catch {
      return normalizeHeroPriceChartSettings(null);
    }
  }

  export function writeHeroPriceChartSettings(
    storage: HeroPriceSettingsStorage | null,
    key: string,
    value: HeroPriceChartSettings
  ) {
    if (!storage) {
      return;
    }
    try {
      storage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage may be blocked or full. Chart settings should degrade without interrupting research.
    }
  }

  export function syncHeroPriceSettingsStorage({
    storageKey,
    loadedStorageKey,
    settings,
    readSettings,
    writeSettings
  }: {
    storageKey: string;
    loadedStorageKey: string | null;
    settings: HeroPriceChartSettings;
    readSettings: (key: string) => HeroPriceChartSettings;
    writeSettings: (key: string, value: HeroPriceChartSettings) => void;
  }): HeroPriceSettingsStorageState {
    if (loadedStorageKey !== storageKey) {
      return {
        loadedStorageKey: storageKey,
        settings: readSettings(storageKey)
      };
    }

    writeSettings(storageKey, settings);
    return { loadedStorageKey, settings };
  }

  export function canRenderHeroCandlesticks(points: Array<Partial<HeroPricePoint>> | null | undefined) {
    const normalized = normalizeHeroPricePoints(points);
    return normalized.length > 0 && normalized.every(hasCompleteOhlc);
  }

  function hasCompleteOhlc(point: Partial<HeroPricePoint>) {
    return (
      typeof point.open === "number" &&
      Number.isFinite(point.open) &&
      typeof point.high === "number" &&
      Number.isFinite(point.high) &&
      typeof point.low === "number" &&
      Number.isFinite(point.low) &&
      typeof point.close === "number" &&
      Number.isFinite(point.close)
    );
  }
</script>

<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart from "./TimeSeriesChart.svelte";

  export let chartKey: string;
  export let points: HeroPricePoint[] = [];
  export let height = 320;
  export let emptyMessage = "CHART UNAVAILABLE";
  export let showLegend = true;

  let settings: HeroPriceChartSettings = normalizeHeroPriceChartSettings(defaultHeroPriceChartSettings);
  let mounted = false;
  let loadedStorageKey: string | null = null;

  $: storageKey = heroPriceSettingsStorageKey(chartKey);
  $: availability = heroPriceChartAvailability(points);
  $: candlesAvailable = canRenderHeroCandlesticks(points);
  $: effectiveSettings = normalizeHeroPriceChartSettings({
    ...settings,
    priceStyle: settings.priceStyle === "candlestick" && !candlesAvailable ? "line" : settings.priceStyle,
    volumeOverlay: settings.volumeOverlay && availability.hasVolume,
    movingAverages: availability.hasClose ? settings.movingAverages : []
  });
  $: series = buildHeroPriceChartSeries(points, effectiveSettings);

  onMount(() => {
    mounted = true;
  });

  $: if (mounted) {
    const synced = syncHeroPriceSettingsStorage({
      storageKey,
      loadedStorageKey,
      settings,
      readSettings: (key) => readHeroPriceChartSettings(getLocalStorage(), key),
      writeSettings: (key, value) => writeHeroPriceChartSettings(getLocalStorage(), key, value)
    });
    if (loadedStorageKey !== synced.loadedStorageKey) {
      loadedStorageKey = synced.loadedStorageKey;
    }
    if (settings !== synced.settings) {
      settings = synced.settings;
    }
  }

  function getLocalStorage(): HeroPriceSettingsStorage | null {
    if (typeof window === "undefined") {
      return null;
    }
    try {
      return window.localStorage;
    } catch {
      return null;
    }
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
          disabled={!candlesAvailable}
          on:click={() => setPriceStyle("candlestick")}
        >
          {candlesAvailable ? "Candles" : "Candles unavailable"}
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
    font-size: var(--text-sm);
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
    gap: var(--space-3);
    padding: var(--space-4);
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--surface-0);
  }

  .settings-title {
    color: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 600;
    line-height: 1.2;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .settings-group {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  button {
    min-height: 25px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-1);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-xs);
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
