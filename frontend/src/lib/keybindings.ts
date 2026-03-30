import type { ActionKeybindingId, ShortcutCombo } from "./api/types";
import { ACTION_KEYBINDINGS } from "./navigation";

const ACTION_KEYBINDING_LOOKUP = new Map(ACTION_KEYBINDINGS.map((binding) => [binding.id, binding]));

function normalizeEventKey(event: KeyboardEvent) {
  if (event.key === "Escape") {
    return "escape";
  }
  if (event.key === "F5") {
    return "f5";
  }
  if (event.key === "`" || event.code === "Backquote") {
    return "`";
  }
  return event.key.toLowerCase();
}

export function matchesShortcutCombo(event: KeyboardEvent, combo: ShortcutCombo) {
  return (
    normalizeEventKey(event) === combo.key &&
    Boolean(event.ctrlKey) === Boolean(combo.ctrl) &&
    Boolean(event.shiftKey) === Boolean(combo.shift) &&
    Boolean(event.altKey) === Boolean(combo.alt) &&
    Boolean(event.metaKey) === Boolean(combo.meta)
  );
}

export function matchesActionKeybinding(event: KeyboardEvent, actionId: ActionKeybindingId) {
  const binding = ACTION_KEYBINDING_LOOKUP.get(actionId);
  if (!binding) {
    return false;
  }
  return binding.combos.some((combo) => matchesShortcutCombo(event, combo));
}

export function isEditableEventTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const nearestEditable = target.closest("input, textarea, select, [contenteditable='true']");
  return nearestEditable != null;
}
