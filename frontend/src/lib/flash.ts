export type FlashDirection = 'up' | 'down' | 'neutral';

interface FlashParams {
  value: unknown;
  direction?: FlashDirection;
}

export function flashOnChange(node: HTMLElement, params: FlashParams) {
  return {
    update({ value: _value, direction = 'neutral' }: FlashParams) {
      const cls = direction === 'up' ? 'flash-up'
                : direction === 'down' ? 'flash-down'
                : 'flash-neutral';
      node.classList.remove('flash-up', 'flash-down', 'flash-neutral');
      void node.offsetWidth; // force reflow so re-adding the same class restarts the animation
      node.classList.add(cls);
    }
  };
}

// For new items entering the DOM (keyed {#each} lists).
// The key ensures Svelte creates a fresh node rather than reusing one.
export function flashOnMount(node: HTMLElement, direction: FlashDirection = 'neutral') {
  const cls = direction === 'up' ? 'flash-up'
            : direction === 'down' ? 'flash-down'
            : 'flash-neutral';
  node.classList.add(cls);
}
