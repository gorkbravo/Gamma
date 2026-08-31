/**
 * Enter/Space activation for table rows that act as a single click target.
 *
 * Rows carry `tabindex="0"` so they are reachable, but several of them also
 * contain their own buttons. Ignoring keys that bubble up from a nested
 * control keeps those buttons behaving as themselves rather than as the row.
 */
export function activateRowOnKey(event: KeyboardEvent, activate: () => void) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  if (event.target !== event.currentTarget) {
    return;
  }
  event.preventDefault();
  activate();
}
