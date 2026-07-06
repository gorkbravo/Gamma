<script lang="ts">
  import type { SystemStatus } from "../lib/api/types";

  export let status: SystemStatus | null = null;
  export let busy = false;
  export let onConnect: () => void;
  export let onEnterPortfolio: () => void;
  export let onEnterResearch: () => void;

  const connectedLabel = (status: SystemStatus | null) => {
    if (!status) {
      return "Checking connection";
    }
    if (status.connection.connected) {
      return status.connection.active_account
        ? `Connected: ${status.connection.active_account}`
        : "Connected";
    }
    return "Disconnected";
  };

  const connectionActionLabel = (status: SystemStatus | null) => {
    if (status?.connection.connected) {
      return "Disconnect from IBKR";
    }
    return "Connect to IBKR";
  };
</script>

<section class="landing">
  <article class="card">
    <div class="identity">
      <span class="mark" aria-hidden="true">Γ</span>
      <div class="wordmark">
        <h2>Gamma</h2>
        <p class="descriptor">Research Terminal</p>
      </div>
    </div>
    <p class="copy">Connect to IBKR or open a workspace.</p>

    <div class="meta">
      <span class="status-dot" class:connected={status?.connection.connected} aria-hidden="true"></span>
      <strong>{connectedLabel(status)}</strong>
      {#if status?.connection.status_text && status.connection.status_text !== `Status: ${connectedLabel(status)}`}
        <small>{status.connection.status_text}</small>
      {/if}
    </div>

    <div class="actions">
      <button
        class="primary apex"
        on:click={onConnect}
        disabled={busy || !status?.connection.action_enabled}
      >
        {busy ? "Working..." : connectionActionLabel(status)}
      </button>
      <button class="secondary" on:click={onEnterPortfolio}>Portfolio View</button>
      <button class="secondary" on:click={onEnterResearch}>Research View</button>
    </div>
  </article>
</section>

<style>
  .landing {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 1rem;
  }

  .card {
    width: min(28rem, calc(100vw - 2rem));
    display: grid;
    gap: 1rem;
    padding: 1.6rem;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    box-shadow: 0 24px 56px rgba(0, 0, 0, 0.45);
  }

  .identity {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.4rem;
    height: 2.4rem;
    flex-shrink: 0;
    border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--panel-border));
    border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--accent) 12%, var(--surface-0));
    color: var(--accent);
    font-family: var(--display-font);
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1;
  }

  .wordmark {
    display: grid;
    gap: 0.1rem;
  }

  .descriptor {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
  }

  .copy,
  small {
    color: var(--text-2);
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.3rem;
    line-height: 1.1;
    letter-spacing: 0.02em;
  }

  .meta {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: baseline;
    column-gap: 0.45rem;
    row-gap: 0.3rem;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-2);
    align-self: center;
  }

  .status-dot.connected {
    background: var(--positive);
  }

  strong {
    color: var(--text-0);
    font-size: 0.95rem;
  }

  small {
    grid-column: 2;
    line-height: 1.45;
  }

  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
    justify-items: center;
  }

  button {
    width: 100%;
    min-height: 2.5rem;
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    color: var(--text-0);
    padding: 0.6rem 0.95rem;
    font: inherit;
    font-family: var(--display-font);
    font-weight: 500;
    cursor: pointer;
    transition: border-color 0.12s ease, background 0.12s ease;
  }

  button:hover:enabled {
    border-color: color-mix(in srgb, var(--accent) 55%, var(--panel-strong));
    background: var(--hover-bg);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .apex {
    grid-column: 1 / -1;
    max-width: 15rem;
  }

  .primary {
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .secondary {
    max-width: 12.5rem;
  }

  @media (max-width: 640px) {
    .landing {
      place-items: center;
    }

    .card {
      width: min(28rem, 100%);
      padding: 1.2rem;
    }

    .actions {
      grid-template-columns: 1fr;
    }

    .apex,
    .secondary {
      max-width: none;
    }
  }
</style>
