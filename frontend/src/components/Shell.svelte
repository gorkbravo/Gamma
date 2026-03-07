<script lang="ts">
  export let title = "StrataLab";
  export let subtitle = "Tauri + FastAPI + Svelte migration shell";
</script>

<div class="shell">
  <header class="hero">
    <div>
      <p class="eyebrow">Desktop Quant Workstation</p>
      <h1>{title}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>
    <div class="badge">Browser Bootstrap</div>
  </header>
  <slot />
</div>

<style>
  .shell {
    width: min(1480px, calc(100vw - 2rem));
    margin: 0 auto;
    padding: 1rem 0 2rem;
  }

  .hero {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .eyebrow {
    margin: 0 0 0.35rem;
    color: var(--accent-2);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
  }

  h1 {
    margin: 0;
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    font-weight: 600;
  }

  .subtitle {
    margin: 0.45rem 0 0;
    color: var(--text-2);
    max-width: 42rem;
  }

  .badge {
    border: 1px solid var(--panel-strong);
    background: rgba(16, 25, 35, 0.85);
    color: var(--text-1);
    padding: 0.6rem 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.72rem;
  }
</style>
