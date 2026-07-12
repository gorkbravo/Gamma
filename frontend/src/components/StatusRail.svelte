<script lang="ts">
  import type { ProviderUsageHealth, ProviderUsageResponse, ProviderUsageSummary, SystemStatus, WorkspaceMode } from "../lib/api/types";
  import { getWorkspaceLabel } from "../lib/navigation";
  import { setChartTheme, setFontFamily, type FontFamily } from "../lib/stores/app";
  import type { RequestMetricSnapshot } from "../lib/request-metrics";

  export let status: SystemStatus | null = null;
  export let providerUsage: ProviderUsageResponse | null = null;
  export let requestMetrics: RequestMetricSnapshot | null = null;
  export let pollingState: { system: boolean; providerUsage: boolean; iv: boolean } = {
    system: false,
    providerUsage: false,
    iv: false
  };
  export let workspaceMode: WorkspaceMode = "portfolio";
  export let busy = false;
  export let settingsOpen = false;
  export let onToggleConnection: () => void;
  export let onBaseCurrencyChange: (currency: string) => void;
  export let onMarketDataModeChange: (mode: string) => void;
  export let onRefresh: () => void;
  export let onChangeView: () => void;
  export let onToggleSettings: () => void = () => {};
  export let onOpenKeyBindings: () => void = () => {};

  const baseCurrencyOptions = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD"];
  let selectedBaseCurrency = status?.base_currency ?? "USD";
  let selectedMarketDataMode = status?.market_data_mode ?? "delayed";
  let workspaceLabel = getWorkspaceLabel("portfolio");
  let topProviderRows: ProviderUsageSummary[] = [];
  let providerHealthRows: ProviderUsageHealth[] = [];

  $: if (status?.base_currency) {
    selectedBaseCurrency = status.base_currency;
  }

  $: if (status?.market_data_mode) {
    selectedMarketDataMode = status.market_data_mode;
  }

  $: workspaceLabel = getWorkspaceLabel(workspaceMode);

  let selectedChartTheme: string = "blue";
  let selectedFontFamily: string = "Cascadia Mono";

  $: topProviderRows = providerUsage?.providers.slice(0, 4) ?? [];
  $: providerHealthRows = providerUsage?.health.slice(0, 4) ?? [];

  function providerCallLabel(row: ProviderUsageSummary) {
    return row.call_count === 1 ? "1 call" : `${row.call_count} calls`;
  }

  function providerStatusLabel(row: ProviderUsageSummary) {
    const parts = [`${row.success_count} ok`];
    if (row.unavailable_count) {
      parts.push(`${row.unavailable_count} unavailable`);
    }
    if (row.error_count) {
      parts.push(`${row.error_count} error`);
    }
    return parts.join(" / ");
  }

  function providerLatencyLabel(row: ProviderUsageSummary) {
    return `${row.average_duration_ms.toFixed(row.average_duration_ms >= 10 ? 0 : 1)} ms avg`;
  }

  function providerHealthTone(status: string) {
    if (status === "healthy") return "positive";
    if (status === "degraded" || status === "unavailable" || status === "needs_config") return "warning";
    return "neutral";
  }
</script>

<section class="rail">
  <div class="actions">
    <div class="conn-chip" title={status?.connection.status_text ?? "Waiting for backend status"}>
      <span class="conn-dot" class:on={status?.connection.connected}></span>
      <span class="conn-label" class:mock={status?.mock_mode}>{status?.mock_mode ? "Mock" : "Live"}</span>
    </div>
    <button class="ghost" on:click={onChangeView}>Change View</button>
    <button class="accent" on:click={onRefresh} disabled={busy}>{busy ? "Refreshing..." : "Refresh"}</button>
    <div class="settings-menu">
      <button
        type="button"
        class="ghost settings-toggle"
        class:open={settingsOpen}
        on:click={onToggleSettings}
        aria-expanded={settingsOpen}
        aria-haspopup="dialog"
      >
        Settings
      </button>
      {#if settingsOpen}
      <div class="settings-popover">
        <div class="settings-section">
          <div class="settings-head">
            <span class="label">Connection</span>
            <strong class:positive={status?.connection.connected}>{status?.connection.status_text ?? "Status: Loading"}</strong>
          </div>
          <small>{status?.connection.active_account ?? "No active account"}</small>
          <button class="ghost wide" on:click={onToggleConnection} disabled={busy || !status?.connection.action_enabled}>
            {busy ? "Working..." : status?.connection.action_text ?? "Connect"}
          </button>
        </div>

        <div class="settings-section">
          <div class="settings-head">
            <span class="label">Frontend Requests</span>
            <strong>{requestMetrics?.totals.network_request ?? 0} network</strong>
          </div>
          <div class="row"><span>Cache / stale</span><strong>{requestMetrics?.totals.cache_hit ?? 0} / {requestMetrics?.totals.stale_hit ?? 0}</strong></div>
          <div class="row"><span>Coalesced / cancelled</span><strong>{requestMetrics?.totals.coalesced ?? 0} / {requestMetrics?.totals.cancelled ?? 0}</strong></div>
          <div class="row"><span>Slow / failed</span><strong>{requestMetrics?.totals.slow_request ?? 0} / {requestMetrics?.totals.network_error ?? 0}</strong></div>
          {#if requestMetrics?.startup}
            <div class="row"><span>Startup usable</span><strong>{requestMetrics.startup.durationMs.toFixed(0)} ms / {requestMetrics.startup.networkRequests} req</strong></div>
          {/if}
          <small>Polling: system {pollingState.system ? "active" : "paused"}; provider {pollingState.providerUsage ? "active" : "paused"}; Options {pollingState.iv ? "active" : "paused"}. Hidden windows pause adaptive pollers.</small>
        </div>

        <div class="settings-section">
          <div class="row">
            <span class="label">Workspace</span>
            <strong>{workspaceLabel}</strong>
          </div>
          <div class="row">
            <span class="label">Mode</span>
            <strong>{status?.mock_mode ? "Mock" : "Live"}</strong>
          </div>
        </div>

        <div class="settings-section field">
          <span class="label">Base Currency</span>
          <select
            bind:value={selectedBaseCurrency}
            disabled={busy}
            on:change={() => onBaseCurrencyChange(selectedBaseCurrency)}
          >
            {#each baseCurrencyOptions as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
          <small>Changing base currency clears local portfolio history and recomputes analytics in the selected currency.</small>
          <small>When historical FX is unavailable, portfolio, research, and risk will show explicit spot-FX fallback warnings.</small>
        </div>

        <div class="settings-section field">
          <span class="label">Market Data</span>
          <select
            bind:value={selectedMarketDataMode}
            disabled={busy}
            on:change={() => onMarketDataModeChange(selectedMarketDataMode)}
          >
            <option value="delayed">Delayed</option>
            <option value="live">Live</option>
            <option value="auto">Auto</option>
          </select>
        </div>

        <div class="settings-section">
          <div class="settings-head">
            <span class="label">Provider Usage</span>
            <strong>{providerUsage?.total_calls ?? 0} calls</strong>
          </div>
          {#if topProviderRows.length}
            <div class="usage-list">
              {#each topProviderRows as row}
                <div class="usage-row" title={row.endpoints.join(", ")}>
                  <strong>{row.provider_id}</strong>
                  <span>{providerCallLabel(row)}</span>
                  <small>{providerStatusLabel(row)} | {providerLatencyLabel(row)}</small>
                </div>
              {/each}
            </div>
          {:else}
            <small>No provider calls recorded since backend startup.</small>
          {/if}
          {#if providerHealthRows.length}
            <div class="health-list">
              {#each providerHealthRows as row}
                <div class="health-row" title={row.expected_when}>
                  <strong>{row.display_name}</strong>
                  <span class={providerHealthTone(row.health_status)}>{row.health_label}</span>
                  <small>{row.action_label ?? row.reason}</small>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <div class="settings-section field">
          <span class="label">Chart Theme</span>
          <select
            bind:value={selectedChartTheme}
            on:change={() => setChartTheme(selectedChartTheme as "blue" | "amber" | "green")}
          >
            <option value="blue">Blue (Default)</option>
            <option value="amber">Amber Phosphor</option>
            <option value="green">Green Phosphor</option>
          </select>
          <small>Changes chart line and area colors across all views.</small>
        </div>

        <div class="settings-section field">
          <span class="label">Font Family</span>
          <select
            bind:value={selectedFontFamily}
            on:change={() => setFontFamily(selectedFontFamily as FontFamily)}
          >
            <option value="Cascadia Mono">Cascadia Mono (Default)</option>
            <option value="Consolas">Consolas</option>
            <option value="JetBrains Mono">JetBrains Mono</option>
            <option value="IBM Plex Mono">IBM Plex Mono</option>
            <option value="Courier New">Courier New</option>
          </select>
        </div>

        <div class="settings-section">
          <div class="settings-head">
            <span class="label">Navigation</span>
            <strong>Keyboard</strong>
          </div>
          <small>Open the dedicated key bindings window to review default and derived shortcuts.</small>
          <button class="ghost wide" type="button" on:click={onOpenKeyBindings}>Key Bindings</button>
        </div>
      </div>
      {/if}
    </div>
  </div>
</section>

<style>
  .rail {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    width: 100%;
  }

  .label {
    display: block;
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  strong {
    color: var(--text-0);
    font-size: var(--text-base);
    font-weight: 600;
  }

  small {
    display: block;
    margin-top: var(--space-1);
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .positive {
    color: var(--positive);
  }

  select,
  button,
  .settings-toggle {
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    color: var(--text-0);
    padding: var(--space-2) var(--space-4);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
    transition: border-color 120ms ease, background 120ms ease, color 120ms ease;
  }

  button:hover:not(:disabled) {
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-strong));
  }

  .actions {
    display: flex;
    align-items: stretch;
    gap: var(--space-4);
    min-width: 0;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .conn-chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-4);
    white-space: nowrap;
  }

  .conn-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-2);
    flex-shrink: 0;
  }

  .conn-dot.on {
    background: var(--positive);
  }

  .conn-label {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .conn-label.mock {
    color: var(--warning);
  }

  .actions button,
  .settings-toggle {
    min-width: 5.8rem;
  }

  .ghost {
    background: transparent;
  }

  .accent {
    border-color: rgba(122, 166, 200, 0.5);
    color: var(--accent);
  }

  .settings-menu {
    position: relative;
  }

  .settings-toggle.open {
    border-color: rgba(122, 166, 200, 0.5);
    color: var(--accent);
  }

  .settings-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    list-style: none;
    user-select: none;
    text-align: center;
  }

  .settings-toggle::-webkit-details-marker {
    display: none;
  }

  .settings-popover {
    position: absolute;
    top: calc(100% + 0.45rem);
    right: 0;
    z-index: 20;
    width: min(21rem, calc(100vw - 2rem));
    display: grid;
    gap: var(--space-5);
    padding: var(--space-6);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    background: rgba(8, 13, 18, 0.98);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  }

  .settings-section {
    display: grid;
    gap: var(--space-3);
  }

  .settings-section + .settings-section {
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    padding-top: var(--space-5);
  }

  .settings-head,
  .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .field {
    gap: var(--space-2);
  }

  .wide {
    width: 100%;
  }

  .usage-list {
    display: grid;
    gap: var(--space-3);
  }

  .usage-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-2) var(--space-4);
    align-items: baseline;
    padding: var(--space-3) 0;
    border-top: 1px solid rgba(46, 60, 74, 0.36);
  }

  .usage-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .usage-row strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .usage-row span {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .usage-row small {
    grid-column: 1 / -1;
    margin-top: 0;
  }

  .health-list {
    display: grid;
    gap: var(--space-3);
    padding-top: var(--space-3);
    border-top: 1px dashed rgba(46, 60, 74, 0.42);
  }

  .health-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-2) var(--space-4);
    align-items: baseline;
  }

  .health-row strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .health-row span {
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .health-row small {
    grid-column: 1 / -1;
    margin-top: 0;
  }

  .health-row .positive {
    color: var(--positive);
  }

  .health-row .warning {
    color: var(--warning);
  }

  .health-row .neutral {
    color: var(--text-2);
  }

  @media (max-width: 960px) {
    .rail,
    .actions {
      justify-content: stretch;
    }

    .actions {
      width: 100%;
    }

    .actions button,
    .settings-menu,
    .settings-toggle {
      width: 100%;
    }

    .settings-popover {
      left: 0;
      right: auto;
      width: 100%;
    }
  }
</style>
