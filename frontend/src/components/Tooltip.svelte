<script lang="ts">
  // Hover/focus tooltip for detail that would otherwise be rendered as inline
  // metadata prose. Uses `position: fixed` so the bubble escapes the
  // `overflow: auto` table/news scrollers it is triggered from.
  import { onDestroy } from "svelte";

  /** Plain-text body. Ignored when the `content` slot is filled. */
  export let text: string | null = null;
  /** Optional uppercase heading rendered above the body. */
  export let heading: string | null = null;
  /** Preferred side. Flips automatically when the bubble would leave the viewport. */
  export let placement: "top" | "bottom" = "top";
  /** Set false when the trigger sits inside a button/link that already takes focus. */
  export let focusable = true;
  /** Trigger participates in a grid/flex row rather than flowing inline. */
  export let block = false;
  /** Dotted underline + help cursor marking the trigger as inspectable. */
  export let hint = false;
  export let disabled = false;
  export let maxWidth = "24rem";
  export let label: string | null = null;

  const OPEN_DELAY_MS = 90;
  const GAP = 6;
  const EDGE = 8;
  const bubbleId = `tooltip-${Math.random().toString(36).slice(2, 9)}`;

  let triggerEl: HTMLElement | null = null;
  let open = false;
  let openTimer = 0;

  $: hasBody = Boolean(text?.trim()) || Boolean($$slots.content);
  $: active = open && !disabled && hasBody;
  // A focusable trigger has to be a real control for `aria-describedby` to reach
  // a screen reader; pass focusable={false} when nesting inside a button or link.
  $: useButton = focusable && hasBody && !disabled;

  function scheduleOpen() {
    if (disabled || !hasBody) return;
    window.clearTimeout(openTimer);
    openTimer = window.setTimeout(() => (open = true), OPEN_DELAY_MS);
  }

  function close() {
    window.clearTimeout(openTimer);
    open = false;
  }

  /** Touch devices never fire mouseenter — tapping the trigger toggles instead. */
  function toggle() {
    if (disabled || !hasBody) return;
    window.clearTimeout(openTimer);
    open = !open;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && open) {
      close();
    }
  }

  // Measures after the bubble mounts, then keeps it pinned while scrolling.
  function place(node: HTMLDivElement) {
    const reposition = () => {
      if (!triggerEl) return;
      const anchor = triggerEl.getBoundingClientRect();
      const bubble = node.getBoundingClientRect();

      let side = placement;
      let top = side === "top" ? anchor.top - bubble.height - GAP : anchor.bottom + GAP;
      if (side === "top" && top < EDGE) {
        side = "bottom";
        top = anchor.bottom + GAP;
      } else if (side === "bottom" && top + bubble.height > window.innerHeight - EDGE) {
        const flipped = anchor.top - bubble.height - GAP;
        if (flipped >= EDGE) {
          side = "top";
          top = flipped;
        }
      }
      top = Math.min(Math.max(EDGE, top), Math.max(EDGE, window.innerHeight - bubble.height - EDGE));

      let left = anchor.left + anchor.width / 2 - bubble.width / 2;
      left = Math.min(Math.max(EDGE, left), Math.max(EDGE, window.innerWidth - bubble.width - EDGE));

      node.style.top = `${Math.round(top)}px`;
      node.style.left = `${Math.round(left)}px`;
      node.dataset.side = side;
      node.style.visibility = "visible";
    };

    reposition();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return {
      destroy() {
        window.removeEventListener("scroll", reposition, true);
        window.removeEventListener("resize", reposition);
      }
    };
  }

  onDestroy(() => {
    if (typeof window !== "undefined") {
      window.clearTimeout(openTimer);
    }
  });
</script>

<svelte:window on:keydown={handleKeydown} />

{#if useButton}
  <button
    bind:this={triggerEl}
    type="button"
    class="tooltip-trigger"
    class:block
    class:hint
    aria-describedby={active ? bubbleId : undefined}
    aria-label={label}
    on:mouseenter={scheduleOpen}
    on:mouseleave={close}
    on:focusin={scheduleOpen}
    on:focusout={close}
    on:click={toggle}
  ><slot /></button>
{:else}
  <!-- Passive hover region: the focusable control it decorates lives in the slot. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <span
    bind:this={triggerEl}
    class="tooltip-trigger"
    class:block
    class:hint={hint && hasBody}
    aria-describedby={active ? bubbleId : undefined}
    aria-label={label}
    on:mouseenter={scheduleOpen}
    on:mouseleave={close}
    on:focusin={scheduleOpen}
    on:focusout={close}
  ><slot /></span>
{/if}

{#if active}
  <div class="tooltip-bubble" id={bubbleId} role="tooltip" use:place style={`max-width: ${maxWidth};`}>
    {#if heading}<span class="tooltip-heading">{heading}</span>{/if}
    {#if $$slots.content}
      <slot name="content" />
    {:else}
      <span class="tooltip-text">{text}</span>
    {/if}
  </div>
{/if}

<style>
  .tooltip-trigger {
    display: inline-flex;
    align-items: center;
    min-width: 0;
    max-width: 100%;
    /* Button reset — the trigger must be invisible chrome around the slot. */
    appearance: none;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    letter-spacing: inherit;
    text-align: inherit;
    text-transform: inherit;
  }

  button.tooltip-trigger {
    cursor: default;
  }

  .tooltip-trigger.block {
    display: block;
  }

  .tooltip-trigger.hint {
    cursor: help;
    text-decoration: underline dotted var(--panel-strong);
    text-underline-offset: 3px;
  }

  .tooltip-trigger.hint:hover,
  .tooltip-trigger.hint:focus-visible {
    text-decoration-color: var(--accent);
  }

  .tooltip-trigger:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: 1px;
  }

  .tooltip-bubble {
    position: fixed;
    top: 0;
    left: 0;
    visibility: hidden;
    z-index: 200;
    display: grid;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    pointer-events: none;
    white-space: normal;
    overflow-wrap: anywhere;
    /* The bubble renders next to its trigger, so it would otherwise inherit
       uppercase status-line / table-header typography from the surface. */
    text-transform: none;
    text-align: left;
    letter-spacing: normal;
    font-weight: 400;
    font-style: normal;
  }

  .tooltip-heading {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .tooltip-text {
    color: var(--text-1);
    white-space: pre-line;
  }
</style>
