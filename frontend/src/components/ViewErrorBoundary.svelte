<script lang="ts">
  import type { Snippet } from "svelte";

  // Aísla el fallo de render de una vista: un `each_key_duplicate` en Strategy Lab dejaba
  // muertos Ctrl+1/Ctrl+3, el menú de navegación y el "Refreshing…" del topbar hasta recargar
  // (GUA-20261021-1). El fallo queda dentro de este bloque y el resto del shell sigue vivo.
  let {
    resetKey = null,
    label = "This view",
    children
  }: {
    // Al cambiar (p. ej. la pestaña activa) se descarta el fallo y se monta el contenido nuevo.
    resetKey?: unknown;
    label?: string;
    children?: Snippet;
  } = $props();

  // `reset` del fallo en curso. No es estado reactivo: el efecto solo depende de `resetKey`.
  let pendingReset: (() => void) | null = null;

  function handleError(error: unknown, reset: () => void) {
    pendingReset = reset;
    console.error("[Gamma] View render failed", error);
  }

  function retry(reset: () => void) {
    pendingReset = null;
    reset();
  }

  $effect(() => {
    void resetKey;
    const reset = pendingReset;
    pendingReset = null;
    reset?.();
  });
</script>

<svelte:boundary onerror={handleError}>
  {@render children?.()}

  {#snippet failed(error: unknown, reset: () => void)}
    <div class="view-error" role="alert" data-testid="view-error-boundary">
      <strong>{label} failed to render</strong>
      <span class="message">{error instanceof Error ? error.message || error.name : String(error ?? "Unknown error")}</span>
      <small>Navigation and the topbar keep working. Retry remounts the view; edits it had not stored may be lost.</small>
      <button type="button" class="btn is-ghost" onclick={() => retry(reset)}>Retry</button>
    </div>
  {/snippet}
</svelte:boundary>

<style>
  .view-error {
    display: grid;
    gap: var(--space-2);
    justify-items: start;
    padding: var(--space-5) var(--space-6);
    border: 1px solid color-mix(in srgb, var(--negative) 45%, var(--panel-border));
    background: var(--surface-0);
    color: var(--text-2);
  }

  .view-error strong {
    color: var(--text-0);
    font-size: var(--text-base);
    font-weight: 600;
  }

  .view-error .message {
    color: var(--negative);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .view-error small {
    font-size: var(--text-xs);
  }

  /* The retry button is .btn.is-ghost from primitives.css. */

  .view-error button {
    margin-top: var(--space-2);
    font-size: var(--text-sm);
  }
</style>
