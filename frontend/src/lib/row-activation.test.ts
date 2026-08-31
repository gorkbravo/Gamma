import { describe, expect, it, vi } from "vitest";
import { activateRowOnKey } from "./row-activation";

function keyEvent(key: string, sameTarget = true) {
  const row = { tag: "tr" };
  return {
    key,
    target: sameTarget ? row : { tag: "button" },
    currentTarget: row,
    preventDefault: vi.fn()
  } as unknown as KeyboardEvent;
}

describe("activateRowOnKey", () => {
  it("activates on Enter and Space", () => {
    for (const key of ["Enter", " "]) {
      const activate = vi.fn();
      const event = keyEvent(key);
      activateRowOnKey(event, activate);
      expect(activate).toHaveBeenCalledTimes(1);
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    }
  });

  it("ignores other keys", () => {
    const activate = vi.fn();
    activateRowOnKey(keyEvent("a"), activate);
    expect(activate).not.toHaveBeenCalled();
  });

  it("ignores keys raised by nested controls", () => {
    const activate = vi.fn();
    const event = keyEvent("Enter", false);
    activateRowOnKey(event, activate);
    expect(activate).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});
