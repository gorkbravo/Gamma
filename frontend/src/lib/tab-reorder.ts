export interface VerticalBounds {
  top: number;
  bottom: number;
}

export function getDropIndexFromPointer(
  rows: readonly VerticalBounds[],
  clientY: number,
  itemCount: number,
): number {
  if (itemCount <= 1) {
    return Math.max(1, itemCount);
  }

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const midpoint = row.top + (row.bottom - row.top) / 2;
    if (clientY < midpoint) {
      return Math.max(1, index);
    }
  }

  return itemCount;
}
