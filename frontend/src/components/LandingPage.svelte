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
</script>

<section class="landing">
  <div class="intro">
    <p class="eyebrow">Desktop Quant Workstation</p>
    <h2>Choose how you want to work</h2>
    <p class="copy">
      Start with the live IBKR connection or move directly into the workspace mode that matches the task. Portfolio
      mode uses the live account snapshot. Research mode uses the synthetic or single-name context you define there.
    </p>
  </div>

  <div class="grid">
    <article class="panel">
      <span class="label">Connection</span>
      <h3>Connect to IBKR</h3>
      <p>Toggle the backend session before opening either workspace.</p>
      <div class="meta">
        <strong>{connectedLabel(status)}</strong>
        <small>{status?.connection.status_text ?? "Waiting for backend status"}</small>
      </div>
      <button on:click={onConnect} disabled={busy || !status?.connection.action_enabled}>
        {busy ? "Working..." : status?.connection.action_text ?? "Connect"}
      </button>
    </article>

    <article class="panel">
      <span class="label">Workspace</span>
      <h3>Portfolio View</h3>
      <p>Open the live portfolio workspace where downstream analytics use the portfolio snapshot directly.</p>
      <ul>
        <li>First tab: portfolio monitor</li>
        <li>Risk uses the portfolio snapshot</li>
        <li>IV stays manually ticker-driven</li>
      </ul>
      <button class="primary" on:click={onEnterPortfolio}>Enter Portfolio View</button>
    </article>

    <article class="panel">
      <span class="label">Workspace</span>
      <h3>Research View</h3>
      <p>Open the research workspace where downstream analytics inherit the active synthetic or single-name context.</p>
      <ul>
        <li>First tab: research command deck</li>
        <li>Risk uses the research snapshot</li>
        <li>IV auto-loads the researched ticker when applicable</li>
      </ul>
      <button class="primary" on:click={onEnterResearch}>Enter Research View</button>
    </article>
  </div>
</section>

<style>
  .landing,
  .grid {
    display: grid;
    gap: 1rem;
  }

  .intro {
    max-width: 54rem;
    border: 1px solid var(--panel-border);
    background:
      radial-gradient(circle at top right, rgba(106, 168, 255, 0.14), transparent 42%),
      linear-gradient(180deg, rgba(8, 12, 16, 0.96), rgba(6, 9, 13, 0.94));
    padding: 1.2rem;
    box-shadow: 0 16px 28px var(--shadow);
  }

  .grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: stretch;
  }

  .eyebrow,
  .label,
  .copy,
  p,
  li,
  small {
    color: var(--text-2);
  }

  .eyebrow,
  .label {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.72rem;
  }

  .panel {
    display: grid;
    gap: 0.95rem;
    border: 1px solid var(--panel-border);
    background:
      linear-gradient(180deg, rgba(10, 15, 21, 0.98), rgba(5, 8, 11, 0.94)),
      rgba(6, 9, 13, 0.96);
    padding: 1.2rem;
    box-shadow: 0 16px 28px var(--shadow);
  }

  h2,
  h3,
  p,
  ul {
    margin: 0;
  }

  .meta {
    display: grid;
    gap: 0.3rem;
  }

  strong {
    color: var(--text-0);
  }

  ul {
    padding-left: 1rem;
    display: grid;
    gap: 0.45rem;
  }

  button {
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.85rem 0.95rem;
    font: inherit;
    cursor: pointer;
  }

  .primary {
    border-color: rgba(106, 168, 255, 0.45);
    background: rgba(106, 168, 255, 0.14);
  }

  @media (max-width: 1080px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
