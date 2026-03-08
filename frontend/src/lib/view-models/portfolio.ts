import type { PortfolioPerformanceResponse, PortfolioSnapshot, Position } from "../api/types";

export type PortfolioSortKey =
  | "symbol"
  | "sec_type"
  | "quantity"
  | "market_price"
  | "market_value"
  | "base_market_value"
  | "unrealized_pnl"
  | "weight";

export interface PortfolioTableOptions {
  search: string;
  sortKey: PortfolioSortKey;
  descending: boolean;
  includeCash: boolean;
}

export interface PortfolioDiagnostics {
  grossExposure: number;
  netExposure: number;
  cashWeight: number | null;
  largestPosition: Position | null;
  bestPnl: Position | null;
  worstPnl: Position | null;
  bySecurityType: Array<{ key: string; count: number }>;
  byCurrency: Array<{ key: string; count: number }>;
}

export function filterAndSortPositions(
  positions: Position[],
  options: PortfolioTableOptions
): Position[] {
  const query = options.search.trim().toLowerCase();
  const filtered = positions.filter((position) => {
    if (!options.includeCash && isCashPosition(position)) {
      return false;
    }
    if (!query) {
      return true;
    }
    return [
      position.symbol,
      position.sec_type,
      position.currency
    ]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(query));
  });

  const direction = options.descending ? -1 : 1;
  return [...filtered].sort((left, right) => {
    const leftValue = sortableValue(left, options.sortKey);
    const rightValue = sortableValue(right, options.sortKey);
    if (typeof leftValue === "string" || typeof rightValue === "string") {
      return String(leftValue).localeCompare(String(rightValue)) * direction;
    }
    return (leftValue - rightValue) * direction;
  });
}

export function derivePortfolioDiagnostics(snapshot: PortfolioSnapshot | null): PortfolioDiagnostics {
  const positions = snapshot?.positions ?? [];
  const grossExposure = positions.reduce((sum, position) => sum + Math.abs(position.base_market_value ?? 0), 0);
  const netExposure = positions.reduce((sum, position) => sum + (position.base_market_value ?? 0), 0);
  const total = snapshot?.net_liquidation ?? snapshot?.total_market_value ?? null;
  const cash = positions
    .filter(isCashPosition)
    .reduce((sum, position) => sum + (position.base_market_value ?? 0), 0);

  return {
    grossExposure,
    netExposure,
    cashWeight: total && total > 0 ? cash / total : null,
    largestPosition: maxBy(positions, (position) => Math.abs(position.base_market_value ?? 0)),
    bestPnl: maxBy(positions, (position) => position.unrealized_pnl ?? Number.NEGATIVE_INFINITY),
    worstPnl: minBy(positions, (position) => position.unrealized_pnl ?? Number.POSITIVE_INFINITY),
    bySecurityType: bucketCounts(positions.map((position) => position.sec_type || "Unknown")),
    byCurrency: bucketCounts(positions.map((position) => position.currency || "Unknown"))
  };
}

export function performanceLatestValue(
  performance: PortfolioPerformanceResponse | null
): number | null {
  return performance?.performance_points.at(-1)?.value ?? null;
}

function sortableValue(position: Position, sortKey: PortfolioSortKey): number | string {
  switch (sortKey) {
    case "symbol":
      return position.symbol;
    case "sec_type":
      return position.sec_type;
    case "quantity":
      return position.quantity ?? 0;
    case "market_price":
      return position.market_price ?? Number.NEGATIVE_INFINITY;
    case "market_value":
      return position.market_value ?? Number.NEGATIVE_INFINITY;
    case "unrealized_pnl":
      return position.unrealized_pnl ?? Number.NEGATIVE_INFINITY;
    case "weight":
      return position.weight ?? Number.NEGATIVE_INFINITY;
    case "base_market_value":
    default:
      return position.base_market_value ?? Number.NEGATIVE_INFINITY;
  }
}

function bucketCounts(values: string[]): Array<{ key: string; count: number }> {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((left, right) => right.count - left.count || left.key.localeCompare(right.key));
}

function maxBy<T>(items: T[], score: (item: T) => number): T | null {
  let winner: T | null = null;
  let winnerScore = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    const currentScore = score(item);
    if (currentScore > winnerScore) {
      winner = item;
      winnerScore = currentScore;
    }
  }
  return winner;
}

function minBy<T>(items: T[], score: (item: T) => number): T | null {
  let winner: T | null = null;
  let winnerScore = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const currentScore = score(item);
    if (currentScore < winnerScore) {
      winner = item;
      winnerScore = currentScore;
    }
  }
  return winner;
}

function isCashPosition(position: Position) {
  return position.sec_type === "CASH" || position.symbol.startsWith("CASH");
}
