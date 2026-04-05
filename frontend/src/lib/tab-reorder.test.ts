import { describe, expect, it } from "vitest";
import { getDropIndexFromPointer } from "./tab-reorder";

describe("getDropIndexFromPointer", () => {
  const rows = [
    { top: 0, bottom: 40 },
    { top: 40, bottom: 80 },
    { top: 80, bottom: 120 },
    { top: 120, bottom: 160 },
  ];

  it("never returns a slot ahead of the pinned first row", () => {
    expect(getDropIndexFromPointer(rows, 5, rows.length)).toBe(1);
    expect(getDropIndexFromPointer(rows, 39, rows.length)).toBe(1);
  });

  it("maps pointer position onto the expected insertion slot", () => {
    expect(getDropIndexFromPointer(rows, 55, rows.length)).toBe(1);
    expect(getDropIndexFromPointer(rows, 75, rows.length)).toBe(2);
    expect(getDropIndexFromPointer(rows, 115, rows.length)).toBe(3);
  });

  it("returns the last slot when the pointer is below the final row", () => {
    expect(getDropIndexFromPointer(rows, 999, rows.length)).toBe(rows.length);
  });
});
