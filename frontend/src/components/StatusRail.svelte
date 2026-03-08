<script lang="ts">
  import type { SystemStatus, TabId, WorkspaceMode } from "../lib/api/types";

  export let status: SystemStatus | null = null;
  export let activeTab: TabId = "portfolio";
  export let workspaceMode: WorkspaceMode = "portfolio";
  export let lastError = "";
  export let busy = false;
  export let diagnosticsOpen = false;
  export let onToggleConnection: () => void;
  export let onMarketDataModeChange: (mode: string) => void;
  export let onToggleDiagnostics: () => void;

  let selectedMarketDataMode = status?.market_data_mode ?? "delayed";
  let workspaceLabel = "Portfolio View";
  let activeTabLabel = "Portfolio";

  $: if (status?.market_data_mode) {
    selectedMarketDataMode = status.market_data_mode;
  }

  $: workspaceLabel = workspaceMode === "portfolio" ? "Portfolio View" : "Research View";
  $: activeTabLabel =
    activeTab === "portfolio"
      ? "Portfolio"
      : activeTab === "research"
        ? "Research"
        : activeTab === "risk"
          ? "Risk"
          : "IV";
</script>

<section class="rail">
  <div class="card">
    <span class="label">Connection</span>
    <strong class:positive={status?.connection.connected}>{status?.connection.status_text ?? "Status: Loading"}</strong>
    <small>{status?.connection.active_account ?? "No active account"}</small>
  </div>
  <div class="card">
    <span class="label">Mode</span>
    <strong>{status?.mock_mode ? "Mock" : "Live"}</strong>
  </div>
  <div class="card">
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
  <div class="card">
    <span class="label">View</span>
    <strong>{workspaceLabel}</strong>
    <small>{activeTabLabel} tab</small>
  </div>
  <div class="card">
    <span class="label">Cache</span>
    <strong>{status?.cached_symbols.length ?? 0} symbols</strong>
  </div>
  <div class="actions">
    <button on:click={onToggleConnection} disabled={busy || !status?.connection.action_enabled}>
      {busy ? "Working..." : status?.connection.action_text ?? "Connect"}
    </button>
    <button class:active={diagnosticsOpen} on:click={onToggleDiagnostics}>
      {diagnosticsOpen ? "Hide Diagnostics" : "Show Diagnostics"}
    </button>
  </div>
  <div class="error" class:visible={Boolean(lastError)}>{lastError || "No active API errors."}</div>
</section>

<style>
  .rail {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .card,
  .actions,
  .error {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(8, 12, 16, 0.96), rgba(6, 9, 13, 0.94));
    padding: 0.85rem 0.95rem;
    box-shadow: 0 10px 24px var(--shadow);
  }

  .label {
    display: block;
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.35rem;
  }

  strong {
    color: var(--text-0);
    font-size: 0.95rem;
    font-weight: 600;
  }

  small {
    display: block;
    margin-top: 0.35rem;
    color: var(--text-2);
  }

  .positive {
    color: var(--positive);
  }

  select,
  button {
    width: 100%;
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.7rem 0.8rem;
    font: inherit;
  }

  .actions {
    display: grid;
    gap: 0.65rem;
    align-content: start;
  }

  .actions button.active {
    border-color: var(--accent);
    color: var(--accent);
  }

  .error {
    grid-column: 1 / -1;
    color: var(--warning);
    display: none;
  }

  .visible {
    display: block;
  }

  @media (max-width: 900px) {
    .rail {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
