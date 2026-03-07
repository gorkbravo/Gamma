<script lang="ts">
  import type { SystemStatus, TabId } from "../lib/api/types";

  export let status: SystemStatus | null = null;
  export let activeTab: TabId = "portfolio";
  export let lastError = "";
</script>

<section class="rail">
  <div class="card">
    <span class="label">Connection</span>
    <strong class:positive={status?.connection.connected}>{status?.connection.status_text ?? "Status: Loading"}</strong>
  </div>
  <div class="card">
    <span class="label">Mode</span>
    <strong>{status?.mock_mode ? "Mock" : "Live"}</strong>
  </div>
  <div class="card">
    <span class="label">Market Data</span>
    <strong>{status?.market_data_mode ?? "delayed"}</strong>
  </div>
  <div class="card">
    <span class="label">Workspace</span>
    <strong>{activeTab}</strong>
  </div>
  <div class="card">
    <span class="label">Cache</span>
    <strong>{status?.cached_symbols.length ?? 0} symbols</strong>
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

  .positive {
    color: var(--positive);
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
