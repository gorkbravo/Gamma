import type { IvSurface } from "../api/types";

export function nearestStrikeIndex(surface: IvSurface | null): number {
  if (!surface?.strikes.length || surface.spot == null) {
    return 0;
  }
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  surface.strikes.forEach((strike, index) => {
    const distance = Math.abs(strike - surface.spot!);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

export function deriveTermStructure(surface: IvSurface | null): Array<{ expiry: string; iv: number | null }> {
  if (!surface) {
    return [];
  }
  const strikeIndex = nearestStrikeIndex(surface);
  return surface.expiries.map((expiry, rowIndex) => ({
    expiry,
    iv: surface.iv_grid[rowIndex]?.[strikeIndex] ?? null
  }));
}
