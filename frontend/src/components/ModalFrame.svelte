<script lang="ts">
  // Marco común de los diálogos modales de la beta («Report a problem», «Getting started»):
  // fondo, cabecera con título y Close, cuerpo con scroll y pie. Mismo aspecto que SetupWizard,
  // con Escape para cerrar, foco atrapado dentro y retorno del foco al cerrar.
  import { onDestroy, onMount, tick } from "svelte";

  export let titleId: string;
  export let title: string;
  export let eyebrow = "";
  export let closeLabel = "Close";
  export let onClose: () => void;

  let dialogEl: HTMLDivElement | null = null;
  let headingEl: HTMLHeadingElement | null = null;
  let previouslyFocused: HTMLElement | null = null;

  onMount(() => {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    void tick().then(() => headingEl?.focus());
  });

  onDestroy(() => {
    previouslyFocused?.focus?.();
  });

  function focusableElements(): HTMLElement[] {
    if (!dialogEl) return [];
    return Array.from(
      dialogEl.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      )
    );
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusableElements();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === headingEl)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
</script>

<div class="backdrop">
  <div
    class="dialog"
    role="dialog"
    aria-modal="true"
    aria-labelledby={titleId}
    tabindex="-1"
    bind:this={dialogEl}
    on:keydown={handleKeydown}
  >
    <header class="head">
      <div class="titles">
        {#if eyebrow}<span class="eyebrow">{eyebrow}</span>{/if}
        <h2 id={titleId} tabindex="-1" bind:this={headingEl}>{title}</h2>
      </div>
      <button type="button" class="btn is-ghost close" aria-label={closeLabel} on:click={onClose}>Close</button>
    </header>
    <slot name="nav" />
    <div class="body">
      <slot />
    </div>
    {#if $$slots.footer}
      <footer class="foot">
        <slot name="footer" />
      </footer>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    /* Por encima de shelf y menús (≤ 60), por debajo de los tooltips (200), como SetupWizard. */
    z-index: 100;
    display: grid;
    place-items: center;
    padding: var(--space-6);
    background: var(--scrim);
  }

  /* Superficie de overlay: el único caso en que el modelo de planos admite sombra. */
  .dialog {
    width: min(48rem, 100%);
    max-height: calc(100vh - 2 * var(--space-6));
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    border: 1px solid var(--panel-border);
    border-radius: var(--overlay-radius);
    background: var(--surface-0);
    box-shadow: var(--overlay-shadow);
    outline: none;
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-6) var(--space-5);
    border-bottom: 1px solid var(--panel-border);
  }

  .titles {
    display: grid;
    gap: var(--space-2);
  }

  .eyebrow {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    letter-spacing: 0;
    text-transform: var(--label-case);
  }

  h2 {
    margin: 0;
    color: var(--text-0);
    font-family: var(--font-ui);
    font-size: var(--text-lg);
    line-height: var(--leading-tight);
    outline: none;
  }

  .body {
    display: grid;
    align-content: start;
    gap: var(--space-5);
    min-height: 12rem;
    padding: var(--space-6);
    overflow: auto;
    color: var(--text-1);
    font-family: var(--font-ui);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
  }

  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-5) var(--space-6);
    border-top: 1px solid var(--panel-border);
  }

  .close {
    flex-shrink: 0;
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    font-weight: 500;
  }

  @media (max-width: 640px) {
    .backdrop {
      padding: var(--space-4);
    }

    .dialog {
      max-height: calc(100vh - 2 * var(--space-4));
    }

    .head,
    .body,
    .foot {
      padding-left: var(--space-5);
      padding-right: var(--space-5);
    }
  }
</style>
