<script lang="ts">
  import type { ProviderUsageHealth, ProviderUsageResponse, ProviderUsageSummary, SystemStatus, WorkspaceMode } from "../lib/api/types";
  import { getWorkspaceLabel } from "../lib/navigation";
  import { setChartTheme, setFontFamily, type FontFamily } from "../lib/stores/app";

  export let status: SystemStatus | null = null;
  export let providerUsage: ProviderUsageResponse | null = null;
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
  let selectedFontFamily: string = "Consolas";

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
            <option value="Consolas">Consolas (Default)</option>
            <option value="JetBrains Mono">JetBrains Mono</option>
            <option value="Cascadia Mono">Cascadia Mono</option>
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
    gap: 0.55rem;
    min-width: 0;
    width: 100%;
  }

  .label {
    display: block;
    color: var(--text-2);
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  strong {
    color: var(--text-0);
    font-size: 0.82rem;
    font-weight: 600;
  }

  small {
    display: block;
    margin-top: 0.12rem;
    color: var(--text-2);
    font-size: 0.68rem;
  }

  .positive {
    color: var(--positive);
  }

  select,
  button,
  .settings-toggle {
    background: #0d0f12;
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.28rem 0.58rem;
    font: inherit;
    font-size: 0.74rem;
    cursor: pointer;
  }

  .actions {
    display: flex;
    align-items: stretch;
    gap: 0.45rem;
    min-width: 0;
    flex-wrap: wrap;
    justify-content: flex-end;
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
    gap: 0.8rem;
    padding: 0.9rem;
    border: 1px solid var(--panel-strong);
    background: rgba(8, 13, 18, 0.98);
    box-shadow: 0 18px 36px rgba(0, 0, 0, 0.34);
  }

  .settings-section {
    display: grid;
    gap: 0.38rem;
  }

  .settings-section + .settings-section {
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    padding-top: 0.75rem;
  }

  .settings-head,
  .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.8rem;
  }

  .field {
    gap: 0.3rem;
  }

  .wide {
    width: 100%;
  }

  .usage-list {
    display: grid;
    gap: 0.35rem;
  }

  .usage-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.2rem 0.55rem;
    align-items: baseline;
    padding: 0.42rem 0;
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
    font-size: 0.72rem;
  }

  .usage-row small {
    grid-column: 1 / -1;
    margin-top: 0;
  }

  .health-list {
    display: grid;
    gap: 0.35rem;
    padding-top: 0.35rem;
    border-top: 1px dashed rgba(46, 60, 74, 0.42);
  }

  .health-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.2rem 0.55rem;
    align-items: baseline;
  }

  .health-row strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .health-row span {
    font-size: 0.7rem;
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
