<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";

  export interface CompactContextMenuItem {
    id: string;
    label: string;
    disabled?: boolean;
  }

  export let open = false;
  export let x = 0;
  export let y = 0;
  export let label = "Context menu";
  export let items: CompactContextMenuItem[] = [];
  export let onSelect: ((id: string) => void) | undefined = undefined;
  export let onClose: (() => void) | undefined = undefined;

  let menuEl: HTMLDivElement | null = null;
  $: menuStyle = `left: ${Math.max(4, x)}px; top: ${Math.max(4, y)}px;`;
  $: if (open) {
    void tick().then(() => menuEl?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus());
  }

  function selectItem(item: CompactContextMenuItem) {
    if (item.disabled) {
      return;
    }
    onSelect?.(item.id);
    onClose?.();
  }

  function handleDocumentPointerDown(event: PointerEvent) {
    if (!open || !menuEl || menuEl.contains(event.target as Node)) {
      return;
    }
    onClose?.();
  }

  function handleDocumentKeydown(event: KeyboardEvent) {
    if (!open) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      onClose?.();
    }
  }

  onMount(() => {
    document.addEventListener("pointerdown", handleDocumentPointerDown);
    document.addEventListener("keydown", handleDocumentKeydown);
  });

  onDestroy(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.removeEventListener("pointerdown", handleDocumentPointerDown);
    document.removeEventListener("keydown", handleDocumentKeydown);
  });
</script>

{#if open}
  <div bind:this={menuEl} class="compact-context-menu" style={menuStyle} role="menu" aria-label={label}>
    {#each items as item}
      <button
        type="button"
        role="menuitem"
        disabled={item.disabled}
        on:click={() => selectItem(item)}
      >
        {item.label}
      </button>
    {/each}
  </div>
{/if}

<style>
  .compact-context-menu {
    position: fixed;
    z-index: 60;
    min-width: 9.5rem;
    max-width: min(16rem, calc(100vw - 0.75rem));
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    padding: var(--space-1);
    display: grid;
    gap: var(--space-1);
  }

  .compact-context-menu button {
    width: 100%;
    min-height: 1.7rem;
    padding: var(--space-2) var(--space-4);
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-1);
    text-align: left;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .compact-context-menu button:hover,
  .compact-context-menu button:focus-visible {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    color: var(--text-0);
    outline: 1px solid color-mix(in srgb, var(--accent) 34%, transparent);
    outline-offset: -1px;
  }

  .compact-context-menu button:disabled {
    color: var(--text-2);
    cursor: default;
    opacity: 0.55;
  }
</style>
