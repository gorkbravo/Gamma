<script lang="ts">
  import type { IvSessionStatus, IvSurface, SystemStatus } from "../lib/api/types";
  import type { IvLoadOptions } from "../lib/stores/app";
  import { deriveTermStructure, nearestStrikeIndex } from "../lib/view-models/iv";

  export let status: SystemStatus | null = null;
  export let requestedSymbol = "SPY";
  export let result: IvSurface | null = null;
  export let session: IvSessionStatus | null = null;
  export let loading = false;
  export let sessionLoading = false;
  export let onLoad: (options: IvLoadOptions) => void;
  export let onStartSession: (options: IvLoadOptions) => void;
  export let onStopSession: () => void;
  export let onRefreshSession: () => void;

  let symbol = "SPY";
  let marketDataMode = "delayed";
  let waitSeconds = 2.5;
  let selectedExpiry = 0;

  const fmt = (value: number | null | undefined, digits = 3) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  function submit() {
    onLoad({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode,
      waitSeconds
    });
  }

  function startSession() {
    onStartSession({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode
    });
  }

  $: if (result && selectedExpiry >= result.expiries.length) {
    selectedExpiry = 0;
  }

  $: if (requestedSymbol && requestedSymbol !== symbol) {
    symbol = requestedSymbol;
  }

  let expiryRows: Array<{ expiry: string; values: number[] }> = [];
  let slice: { expiry: string; values: number[] } | undefined;
  let termStructure = deriveTermStructure(result);
  let atmStrikeIndex = nearestStrikeIndex(result);

  $: expiryRows = result?.expiries.map((expiry, index) => ({
    expiry,
    values: result.iv_grid[index] ?? []
  })) ?? [];
  $: slice = expiryRows[selectedExpiry];
  $: termStructure = deriveTermStructure(result);
  $: atmStrikeIndex = nearestStrikeIndex(result);
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>IV Explorer</h2>
      <p>
        The browser path now supports both one-shot surface loads and a Python-owned session loop, with deeper term
        structure and skew inspection on top of the shared IV payload.
      </p>
    </div>
    <div class="action-row">
      <button on:click={submit} disabled={loading}>{loading ? "Loading..." : "Load Snapshot"}</button>
      <button on:click={startSession} disabled={sessionLoading}>{sessionLoading ? "Starting..." : "Start Session"}</button>
      <button on:click={onRefreshSession} disabled={sessionLoading}>Refresh Session</button>
      <button on:click={onStopSession} disabled={sessionLoading || !session?.running}>Stop Session</button>
    </div>
  </div>

  <div class="layout">
    <article class="panel controls">
      <div class="field-grid">
        <label>
          <span>Symbol</span>
          <input bind:value={symbol} placeholder="SPY" />
        </label>
        <label>
          <span>Requested Mode</span>
          <select bind:value={marketDataMode}>
            <option value="delayed">Delayed</option>
            <option value="live">Live</option>
            <option value="auto">Auto</option>
          </select>
        </label>
        <label>
          <span>Wait Seconds</span>
          <select bind:value={waitSeconds}>
            <option value={1.5}>1.5s</option>
            <option value={2.5}>2.5s</option>
            <option value={4}>4.0s</option>
          </select>
        </label>
      </div>

      <div class="status-grid">
        <article>
          <span>Backend Mode</span>
          <strong>{status?.market_data_mode ?? "unknown"}</strong>
        </article>
        <article>
          <span>Session</span>
          <strong>{session?.running ? "running" : "idle"}</strong>
        </article>
        <article>
          <span>Surface Mode</span>
          <strong>{result?.delayed == null ? "unknown" : result.delayed ? "delayed" : "live"}</strong>
        </article>
        <article>
          <span>Points</span>
          <strong>{result?.points ?? 0}</strong>
        </article>
      </div>

      <div class="meta-list">
        <div class="row"><span>Spot</span><strong>{fmt(result?.spot)}</strong></div>
        <div class="row"><span>Session Status</span><strong>{session?.status_text ?? "Idle"}</strong></div>
        <div class="row"><span>Active Symbol</span><strong>{session?.active_symbol ?? result?.symbol ?? symbol}</strong></div>
        <div class="row"><span>ATM Strike</span><strong>{fmt(result?.strikes[atmStrikeIndex], 2)}</strong></div>
        <div class="row"><span>Timestamp</span><strong>{result ? new Date(result.timestamp).toLocaleString() : "N/A"}</strong></div>
      </div>
    </article>

    <article class="panel heatmap-panel">
      <div class="panel-header">
        <div>
          <h3>Expiry / Strike Heatmap</h3>
          <p>{result?.expiries.length ?? 0} expiries x {result?.strikes.length ?? 0} strikes</p>
        </div>
      </div>
      {#if expiryRows.length}
        <div class="heatmap">
          <div class="cell header">Expiry</div>
          {#each result?.strikes ?? [] as strike, strikeIndex}
            <div class="cell header" class:spot={strikeIndex === atmStrikeIndex}>{fmt(strike, 2)}</div>
          {/each}
          {#each expiryRows as row, rowIndex}
            <button class:active={selectedExpiry === rowIndex} class="cell expiry" on:click={() => (selectedExpiry = rowIndex)}>
              {row.expiry}
            </button>
            {#each row.values as value}
              <div
                class="cell data"
                style={`background: rgba(106, 168, 255, ${Math.min(Math.max(value / 0.8, 0.12), 0.92)});`}
              >
                {fmt(value, 2)}
              </div>
            {/each}
          {/each}
        </div>
      {:else}
        <p class="muted">No IV payload loaded yet.</p>
      {/if}
    </article>
  </div>

  <div class="detail-grid">
    <article class="panel">
      <h3>Selected Expiry Slice</h3>
      {#if slice}
        <div class="slice">
          {#each slice.values as value, index}
            <div class="slice-row">
              <span>{fmt(result?.strikes[index], 2)}</span>
              <div class="bar">
                <div class="fill" style={`width:${Math.min(value / 1.1, 1) * 100}%`}></div>
              </div>
              <strong>{fmt(value, 3)}</strong>
            </div>
          {/each}
        </div>
      {:else}
        <p class="muted">Select an expiry after loading a surface.</p>
      {/if}
    </article>

    <article class="panel">
      <h3>ATM Term Structure</h3>
      {#if termStructure.length}
        <div class="slice">
          {#each termStructure as point}
            <div class="slice-row">
              <span>{point.expiry}</span>
              <div class="bar">
                <div class="fill" style={`width:${Math.min((point.iv ?? 0) / 1.1, 1) * 100}%`}></div>
              </div>
              <strong>{fmt(point.iv, 3)}</strong>
            </div>
          {/each}
        </div>
      {:else}
        <p class="muted">Load a surface to inspect ATM term structure.</p>
      {/if}
    </article>

    <article class="panel">
      <h3>Warnings</h3>
      {#if result?.warnings?.length}
        {#each result.warnings as warning}
          <p class="warning">{warning}</p>
        {/each}
      {:else}
        <p class="muted">No warnings.</p>
      {/if}
    </article>
  </div>

  <article class="panel">
    <h3>Backend Messages</h3>
    {#if session?.messages?.length || result?.messages?.length}
      <div class="message-list">
        {#each session?.messages ?? [] as message}
          <p class="message">{message}</p>
        {/each}
        {#each result.messages as message}
          <p class="message">{message}</p>
        {/each}
      </div>
    {:else}
      <p class="muted">No backend messages.</p>
    {/if}
  </article>
</section>

<style>
  .view,
  .layout,
  .field-grid,
  .status-grid,
  .detail-grid,
  .slice {
    display: grid;
    gap: 0.9rem;
  }

  .toolbar,
  .panel-header,
  .row,
  .slice-row,
  .action-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .layout {
    grid-template-columns: minmax(18rem, 0.85fr) minmax(0, 1.55fr);
    align-items: start;
  }

  .field-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .status-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .detail-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: rgba(6, 9, 13, 0.96);
    padding: 1rem;
    box-shadow: 0 16px 28px var(--shadow);
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  span,
  .muted {
    color: var(--text-2);
  }

  strong {
    color: var(--text-0);
  }

  label {
    display: grid;
    gap: 0.45rem;
  }

  input,
  select,
  button {
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.75rem 0.85rem;
    font: inherit;
  }

  button {
    cursor: pointer;
  }

  .action-row {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .heatmap {
    display: grid;
    grid-template-columns: 7rem repeat(auto-fit, minmax(3.8rem, 1fr));
    gap: 0.35rem;
    overflow: auto;
  }

  .cell {
    border: 1px solid rgba(19, 32, 44, 0.75);
    padding: 0.55rem 0.4rem;
    text-align: center;
    min-height: 2.6rem;
  }

  .header {
    background: rgba(16, 25, 35, 0.96);
    color: var(--text-2);
  }

  .spot {
    border-color: rgba(232, 178, 96, 0.65);
    color: #f6d08b;
  }

  .expiry {
    background: rgba(8, 12, 18, 0.9);
  }

  .expiry.active {
    border-color: var(--accent);
    color: var(--accent);
  }

  .data {
    color: #031017;
    font-weight: 700;
  }

  .slice-row,
  .row {
    align-items: center;
    border-bottom: 1px solid rgba(19, 32, 44, 0.75);
    padding-bottom: 0.55rem;
  }

  .bar {
    flex: 1;
    min-width: 6rem;
    height: 0.55rem;
    background: rgba(19, 32, 44, 0.8);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(106, 168, 255, 0.42), rgba(106, 168, 255, 0.92));
  }

  .warning {
    color: var(--warning);
  }

  .message,
  .message-list {
    color: var(--text-1);
  }

  .message-list {
    display: grid;
    gap: 0.5rem;
  }

  @media (max-width: 1140px) {
    .layout,
    .field-grid,
    .status-grid,
    .detail-grid,
    .toolbar {
      grid-template-columns: 1fr;
    }

    .toolbar,
    .panel-header,
    .row,
    .slice-row,
    .action-row {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
