<script lang="ts">
  export let title = "Gamma";
</script>

<div class="shell">
  <header class="topbar">
    <div class="brand">
      <img class="mark" src="/gamma-mark.svg" alt="" aria-hidden="true" />
      <h1>{title}</h1>
    </div>
    <div class="status-slot">
      <slot name="status" />
    </div>
  </header>

  <main class="content">
    <slot />
  </main>
</div>

<style>
  .shell {
    width: min(1600px, calc(100vw - 1.5rem));
    margin: 0 auto;
    padding: 0.5rem 0 1.1rem;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0.75rem;
    border: 1px solid var(--panel-border);
    background: var(--surface-1);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
  }

  .mark {
    display: block;
    width: 1.15rem;
    height: auto;
    opacity: 0.85;
  }

  h1 {
    margin: 0;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .status-slot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-width: 0;
    padding-left: 0.6rem;
    border-left: 1px solid var(--divider);
  }

  .content {
    margin-top: 0.8rem;
  }

  @media (max-width: 960px) {
    .topbar,
    .brand {
      align-items: flex-start;
    }

    .topbar,
    .brand {
      flex-direction: column;
    }

    .topbar {
      display: flex;
      padding: 0.4rem 0.75rem;
    }

    .status-slot {
      width: 100%;
      justify-content: stretch;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.5rem;
    }
  }
</style>
