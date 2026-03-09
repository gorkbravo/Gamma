<script lang="ts">
  import type { SystemStatus, WorkspaceMode } from "../lib/api/types";

  export let status: SystemStatus | null = null;
  export let workspaceMode: WorkspaceMode = "portfolio";
  export let busy = false;
  export let onToggleConnection: () => void;
  export let onMarketDataModeChange: (mode: string) => void;
  export let onRefresh: () => void;
  export let onChangeView: () => void;

  let selectedMarketDataMode = status?.market_data_mode ?? "delayed";
  let workspaceLabel = "Portfolio View";

  $: if (status?.market_data_mode) {
    selectedMarketDataMode = status.market_data_mode;
  }

  $: workspaceLabel = workspaceMode === "portfolio" ? "Portfolio View" : "Research View";
</script>

<section class="rail">
  <div class="cluster connection">
    <div>
      <span class="label">Connection</span>
      <strong class:positive={status?.connection.connected}>{status?.connection.status_text ?? "Status: Loading"}</strong>
      <small>{status?.connection.active_account ?? "No active account"}</small>
    </div>
    <button class="ghost" on:click={onToggleConnection} disabled={busy || !status?.connection.action_enabled}>
      {busy ? "Working..." : status?.connection.action_text ?? "Connect"}
    </button>
  </div>

  <div class="cluster compact">
    <span class="label">Mode</span>
    <strong>{status?.mock_mode ? "Mock" : "Live"}</strong>
  </div>

  <label class="cluster compact field">
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
  </label>

  <div class="cluster compact">
    <span class="label">Workspace</span>
    <strong>{workspaceLabel}</strong>
  </div>

  <div class="actions">
    <button class="ghost" on:click={onChangeView}>Change View</button>
    <button class="accent" on:click={onRefresh} disabled={busy}>{busy ? "Refreshing..." : "Refresh"}</button>
  </div>
</section>

<style>
  .rail {
    display: flex;
    flex-wrap: nowrap;
    justify-content: flex-end;
    align-items: center;
    gap: 0.9rem;
    min-width: 0;
    width: 100%;
  }

  .cluster,
  .actions {
    display: grid;
    gap: 0.14rem;
    padding: 0;
    min-height: auto;
  }

  .cluster.compact {
    min-width: max-content;
  }

  .connection {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    min-width: max-content;
  }

  .field {
    align-items: stretch;
    gap: 0.22rem;
    min-width: 8.9rem;
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
    font-size: 0.86rem;
    font-weight: 600;
  }

  small {
    display: block;
    margin-top: 0.18rem;
    color: var(--text-2);
    font-size: 0.7rem;
  }

  .positive {
    color: var(--positive);
  }

  select,
  button {
    background: #0b1219;
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.52rem 0.68rem;
    font: inherit;
    cursor: pointer;
  }

  .actions {
    display: flex;
    align-items: stretch;
    gap: 0.45rem;
    padding-inline: 0;
    min-width: max-content;
  }

  .actions button {
    min-width: 7.75rem;
  }

  @media (max-width: 960px) {
    .rail {
      flex-wrap: wrap;
      justify-content: stretch;
    }

    .cluster,
    .actions {
      width: 100%;
    }

    .connection {
      display: grid;
      align-items: stretch;
    }
  }

  .ghost {
    background: transparent;
  }

  .accent {
    border-color: rgba(122, 166, 200, 0.5);
    color: var(--accent);
  }
</style>
