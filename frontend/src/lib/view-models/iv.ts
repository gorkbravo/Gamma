import type { IvSessionStatus, IvSurface, SystemStatus, TimeSeriesPoint } from "../api/types";

export type OptionsMode =
  | "overview"
  | "chain"
  | "surface"
  | "realized_implied"
  | "distribution"
  | "strategies";

export const optionsModes: Array<{ id: OptionsMode; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "chain", label: "Chain" },
  { id: "surface", label: "Surface" },
  { id: "realized_implied", label: "Realized vs IV" },
  { id: "distribution", label: "Implied Probabilities" },
  { id: "strategies", label: "Strategies" },
];

export interface IvSurfaceAlertInput {
  result: IvSurface | null;
  session: IvSessionStatus | null;
  status: SystemStatus | null;
  requestedSymbol: string;
  errorMessage?: string | null;
  loading?: boolean;
  sessionLoading?: boolean;
}

export function deriveIvSurfaceAlerts(input: IvSurfaceAlertInput): string[] {
  const providerMessages = [
    input.errorMessage?.trim(),
    ...(input.result?.warnings ?? []),
    ...(input.result?.messages ?? []),
    input.session?.status_text?.toLowerCase().startsWith("error") ? input.session.status_text : "",
    ...(input.session?.messages ?? []),
  ].filter((message): message is string => Boolean(message?.trim()));
  const alerts = [...new Set(providerMessages)];
  const hasSurface = Boolean(
    input.result?.snapshot_available &&
      input.result.points > 0 &&
      input.result.expiries.length > 0 &&
      input.result.strikes.length > 0
  );
  if (hasSurface || input.loading || input.sessionLoading) {
    return alerts;
  }

  if (input.errorMessage?.trim() || input.session?.status_text?.toLowerCase().startsWith("error")) {
    return alerts;
  }

  const symbol = input.requestedSymbol.trim().toUpperCase() || input.session?.active_symbol || "the selected symbol";
  let availabilityMessage: string;
  if (input.status && !input.status.mock_mode && !input.status.connection.connected) {
    availabilityMessage = `IBKR/TWS is disconnected. Connect it before loading an options surface for ${symbol}.`;
  } else if (input.session?.running) {
    availabilityMessage = `The ${symbol} options session is running, but no surface snapshot has been collected yet.`;
  } else {
    availabilityMessage = `No options surface snapshot is available for ${symbol}. The provider session is idle; load the surface and check options entitlements if collection remains unavailable.`;
  }
  return [availabilityMessage, ...alerts.filter((message) => message !== availabilityMessage)];
}

export interface SurfaceStats {
  atmStrike: number | null;
  frontExpiry: string | null;
  frontAtmIv: number | null;
  backAtmIv: number | null;
  termSlope: number | null;
  minIv: number | null;
  maxIv: number | null;
  averageIv: number | null;
  populatedPoints: number;
}

export interface SkewRow {
  expiry: string;
  atmIv: number | null;
  putWingStrike: number | null;
  putWingIv: number | null;
  callWingStrike: number | null;
  callWingIv: number | null;
  putSkew: number | null;
  callSkew: number | null;
  wingSpread: number | null;
}

export interface RealizedVolatilityPoint {
  window: number;
  realizedVol: number | null;
  spreadToFrontIv: number | null;
  observationCount: number;
}

export interface DistributionBucket {
  price: number;
  probability: number;
  label: string;
}

export interface ChainRow {
  pair: NonNullable<IvSurface["pairs"]>[number];
  expiry: string;
  strike: number;
  moneyness: number | null;
  distancePct: number | null;
  callMidpoint: number | null;
  putMidpoint: number | null;
  callPriceSource: string | null;
  putPriceSource: string | null;
  callIv: number | null;
  putIv: number | null;
  blendedIv: number | null;
  callDelta: number | null;
  putDelta: number | null;
  callOpenInterest: number | null;
  putOpenInterest: number | null;
  callVolume: number | null;
  putVolume: number | null;
  straddleMidpoint: number | null;
  impliedMovePct: number | null;
}

export interface OverviewSnapshot {
  stats: SurfaceStats;
  selectedExpiry: string | null;
  selectedExpiryDte: number | null;
  atmPair: ChainRow | null;
  frontChain: ChainRow[];
  skewRows: SkewRow[];
  termStructure: Array<{ expiry: string; iv: number | null }>;
  putCallOpenInterestRatio: number | null;
  putCallVolumeRatio: number | null;
  maxPainStrike: number | null;
}

export type StrategyOptionType = "call" | "put";
export type StrategySide = "long" | "short";
// Payoff Glance defaults to a neutral straddle so the view does not imply a
// directional recommendation (usability audit P2).
export type PayoffGlanceType = StrategyOptionType | "straddle";

export type StrategyTemplateId = "call_spread" | "put_spread" | "straddle" | "collar" | "risk_reversal";

export interface StrategyTemplateDefinition {
  id: StrategyTemplateId;
  label: string;
  stance: string;
}

export const STRATEGY_TEMPLATES: StrategyTemplateDefinition[] = [
  { id: "call_spread", label: "Call Spread", stance: "bullish / defined risk" },
  { id: "put_spread", label: "Put Spread", stance: "bearish / defined risk" },
  { id: "straddle", label: "Straddle", stance: "neutral / long vol" },
  { id: "collar", label: "Collar", stance: "hedge overlay vs long stock" },
  { id: "risk_reversal", label: "Risk Reversal", stance: "bullish skew expression" },
];
export type GreekMetric = "delta" | "gamma" | "vega" | "theta" | "rho";

export interface OptionGreekSet {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  rho: number;
  sigma: number;
}

export interface ChainGreekRow {
  expiry: string;
  strike: number;
  dte: number;
  call: OptionGreekSet | null;
  put: OptionGreekSet | null;
}

export interface StrategyLeg {
  id: string;
  optionType: StrategyOptionType;
  side: StrategySide;
  expiry: string;
  strike: number;
  premium: number;
  quantity: number;
}

export interface StrategyPayoffPoint {
  underlyingPrice: number;
  payoff: number;
  returnPct: number | null;
}

export interface StrategyPayoffSummary {
  points: StrategyPayoffPoint[];
  netPremium: number;
  maxProfit: number | null;
  maxLoss: number | null;
  breakevens: number[];
}

export interface SurfacePath {
  id: string;
  points: string;
  value: number | null;
}

export interface ImpliedProbabilitySurface {
  expiries: string[];
  strikes: number[];
  densityGrid: number[][];
  maxDensity: number;
  coverageByExpiry: number[];
}

export interface ImpliedProbabilityPoint {
  strike: number;
  density: number;
  x: number;
  y: number;
}

export interface ImpliedProbabilitySlice {
  expiry: string;
  dte: number;
  width: number;
  height: number;
  points: ImpliedProbabilityPoint[];
  linePath: string;
  areaPath: string;
  minStrike: number;
  maxStrike: number;
  maxDensity: number;
  coverageMass: number;
  baseline: number;
}

export interface ImpliedProbabilitySelection {
  lowerStrike: number;
  upperStrike: number;
  probabilityMass: number;
  areaPath: string;
}

export interface IvSmilePoint {
  strike: number;
  iv: number;
  x: number;
  y: number;
  isAtm: boolean;
}

export interface IvSmile {
  width: number;
  height: number;
  points: IvSmilePoint[];
  linePath: string;
  areaPath: string;
  atmX: number | null;
  minIv: number;
  maxIv: number;
  minStrike: number;
  maxStrike: number;
  fitPoints: IvSmilePoint[];
}

export interface ObservedSurfacePoint {
  expiry: string;
  strike: number;
  dte: number;
  iv: number;
  rowIndex: number;
  colIndex: number;
}

export interface OptionPayoffCell {
  dte: number;
  /** P/L expressed as a fraction of premium (max risk). -1 == total loss. */
  pct: number;
  pl: number;
  value: number;
}

export interface OptionPayoffRow {
  price: number;
  movePct: number;
  cells: OptionPayoffCell[];
}

export interface OptionPayoffMatrix {
  optionType: PayoffGlanceType;
  strike: number;
  premium: number;
  sigma: number;
  spot: number;
  maxDte: number;
  dteColumns: number[];
  rows: OptionPayoffRow[];
  maxGain: number;
}

export interface StrategyPayoffMatrix {
  dteColumns: number[];
  rows: OptionPayoffRow[];
  maxAbsPl: number;
  riskBasis: number;
}

export interface StrategyGreekSummary {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  rho: number;
  legCount: number;
}

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

export function deriveSurfaceStats(surface: IvSurface | null): SurfaceStats {
  const empty: SurfaceStats = {
    atmStrike: null,
    frontExpiry: null,
    frontAtmIv: null,
    backAtmIv: null,
    termSlope: null,
    minIv: null,
    maxIv: null,
    averageIv: null,
    populatedPoints: 0,
  };
  if (!surface?.expiries.length || !surface.strikes.length) {
    return empty;
  }

  const atmIndex = nearestStrikeIndex(surface);
  const values = surface.iv_grid.flat().filter((value) => Number.isFinite(value) && value > 0);
  const frontAtmIv = surface.iv_grid[0]?.[atmIndex] ?? null;
  const backAtmIv = surface.iv_grid[surface.iv_grid.length - 1]?.[atmIndex] ?? null;
  return {
    atmStrike: surface.strikes[atmIndex] ?? null,
    frontExpiry: surface.expiries[0] ?? null,
    frontAtmIv,
    backAtmIv,
    termSlope: frontAtmIv != null && backAtmIv != null ? backAtmIv - frontAtmIv : null,
    minIv: values.length ? Math.min(...values) : null,
    maxIv: values.length ? Math.max(...values) : null,
    averageIv: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
    populatedPoints: surface.points || values.length,
  };
}

export function selectedExpiryForSurface(surface: IvSurface | null, requestedExpiry: string | null | undefined): string | null {
  if (!surface?.expiries.length) {
    return null;
  }
  return requestedExpiry && surface.expiries.includes(requestedExpiry) ? requestedExpiry : surface.expiries[0];
}

export function deriveChainRows(surface: IvSurface | null, expiry: string | null | undefined): ChainRow[] {
  if (!surface?.pairs?.length || !expiry) {
    return [];
  }
  return surface.pairs
    .filter((pair) => pair.expiry === expiry && Number.isFinite(pair.strike))
    .map((pair) => {
      const strike = Number(pair.strike);
      const distancePct = surface.spot && Number.isFinite(surface.spot) ? strike / surface.spot - 1 : null;
      return {
        pair,
        expiry: pair.expiry,
        strike,
        moneyness: surface.spot && Number.isFinite(surface.spot) ? strike / surface.spot : null,
        distancePct,
        callMidpoint: pair.call_price ?? pair.call_midpoint ?? pair.call_mark_price,
        putMidpoint: pair.put_price ?? pair.put_midpoint ?? pair.put_mark_price,
        callPriceSource: pair.call_price_source ?? (pair.call_midpoint != null ? "midpoint" : pair.call_mark_price != null ? "mark" : null),
        putPriceSource: pair.put_price_source ?? (pair.put_midpoint != null ? "midpoint" : pair.put_mark_price != null ? "mark" : null),
        callIv: pair.call_implied_volatility,
        putIv: pair.put_implied_volatility,
        blendedIv: pair.blended_implied_volatility,
        callDelta: pair.call_delta,
        putDelta: pair.put_delta,
        callOpenInterest: pair.call_open_interest,
        putOpenInterest: pair.put_open_interest,
        callVolume: pair.call_volume,
        putVolume: pair.put_volume,
        straddleMidpoint: pair.straddle_midpoint,
        impliedMovePct: pair.implied_move_pct,
      };
    })
    .sort((left, right) => left.strike - right.strike);
}

export function deriveOverviewSnapshot(
  surface: IvSurface | null,
  requestedExpiry: string | null | undefined
): OverviewSnapshot {
  const stats = deriveSurfaceStats(surface);
  const selectedExpiry = selectedExpiryForSurface(surface, requestedExpiry);
  const frontChain = deriveChainRows(surface, selectedExpiry);
  const atmPair = surface?.spot && frontChain.length
    ? minBy(frontChain, (row) => Math.abs(row.strike - surface.spot!))
    : frontChain[0] ?? null;
  const callOi = sumFinite(frontChain.map((row) => row.callOpenInterest));
  const putOi = sumFinite(frontChain.map((row) => row.putOpenInterest));
  const callVolume = sumFinite(frontChain.map((row) => row.callVolume));
  const putVolume = sumFinite(frontChain.map((row) => row.putVolume));
  return {
    stats,
    selectedExpiry,
    selectedExpiryDte: selectedExpiry ? daysToExpiry(selectedExpiry) : null,
    atmPair,
    frontChain,
    skewRows: deriveSkewRows(surface),
    termStructure: deriveTermStructure(surface),
    putCallOpenInterestRatio: callOi > 0 ? putOi / callOi : null,
    putCallVolumeRatio: callVolume > 0 ? putVolume / callVolume : null,
    maxPainStrike: deriveMaxPainStrike(frontChain),
  };
}

export function deriveSkewRows(surface: IvSurface | null): SkewRow[] {
  if (!surface?.expiries.length || !surface.strikes.length) {
    return [];
  }
  const atmIndex = nearestStrikeIndex(surface);
  return surface.expiries.map((expiry, rowIndex) => {
    const row = surface.iv_grid[rowIndex] ?? [];
    const atmIv = row[atmIndex] ?? null;
    const lowerIndex = findNearestWingIndex(surface.strikes, atmIndex, "lower");
    const upperIndex = findNearestWingIndex(surface.strikes, atmIndex, "upper");
    const putWingIv = lowerIndex == null ? null : row[lowerIndex] ?? null;
    const callWingIv = upperIndex == null ? null : row[upperIndex] ?? null;
    return {
      expiry,
      atmIv,
      putWingStrike: lowerIndex == null ? null : surface.strikes[lowerIndex] ?? null,
      putWingIv,
      callWingStrike: upperIndex == null ? null : surface.strikes[upperIndex] ?? null,
      callWingIv,
      putSkew: putWingIv != null && atmIv != null ? putWingIv - atmIv : null,
      callSkew: callWingIv != null && atmIv != null ? callWingIv - atmIv : null,
      wingSpread: putWingIv != null && callWingIv != null ? putWingIv - callWingIv : null,
    };
  });
}

export function buildStrategyLegFromChainRow(
  row: ChainRow,
  optionType: StrategyOptionType,
  side: StrategySide = "long",
  quantity = 1
): StrategyLeg | null {
  const premium = optionType === "call" ? row.callMidpoint : row.putMidpoint;
  if (premium == null || !Number.isFinite(premium) || premium <= 0) {
    return null;
  }
  return {
    id: `${side}-${optionType}-${row.expiry}-${row.strike}`,
    optionType,
    side,
    expiry: row.expiry,
    strike: row.strike,
    premium,
    quantity,
  };
}

function pricedTemplateRows(rows: ChainRow[] | null | undefined, optionType: StrategyOptionType): ChainRow[] {
  return (rows ?? []).filter((row) => {
    const premium = optionType === "call" ? row.callMidpoint : row.putMidpoint;
    return Number.isFinite(row.strike) && premium != null && Number.isFinite(premium) && premium > 0;
  });
}

function nearestTemplateRow(rows: ChainRow[], targetStrike: number): ChainRow | null {
  return rows.length ? minBy(rows, (row) => Math.abs(row.strike - targetStrike)) : null;
}

function templateWingRow(
  rows: ChainRow[],
  optionType: StrategyOptionType,
  direction: "upper" | "lower",
  spot: number,
  wingPct: number
): ChainRow | null {
  const priced = pricedTemplateRows(rows, optionType);
  const candidates =
    direction === "upper"
      ? priced.filter((row) => row.strike > spot)
      : priced.filter((row) => row.strike < spot);
  if (!candidates.length) {
    return null;
  }
  const target = direction === "upper" ? spot * (1 + wingPct) : spot * (1 - wingPct);
  return nearestTemplateRow(candidates, target);
}

/**
 * One-click strategy templates built from the visible chain. Strikes resolve to
 * the nearest priced contracts (ATM and ~5% wings); rows without usable mid
 * premiums are skipped with a warning instead of failing silently.
 */
export function buildStrategyTemplateLegs(
  templateId: StrategyTemplateId,
  rows: ChainRow[] | null | undefined,
  spot: number | null | undefined,
  wingPct = 0.05
): { legs: StrategyLeg[]; warnings: string[] } {
  const warnings: string[] = [];
  if (!rows?.length || !(spot != null && Number.isFinite(spot) && spot > 0)) {
    return { legs: [], warnings: ["A priced chain and spot are required to build a strategy template."] };
  }

  const pushLeg = (
    legs: StrategyLeg[],
    row: ChainRow | null,
    optionType: StrategyOptionType,
    side: StrategySide,
    role: string
  ) => {
    if (!row) {
      warnings.push(`No priced ${optionType} strike available for the ${role} leg.`);
      return;
    }
    const leg = buildStrategyLegFromChainRow(row, optionType, side);
    if (!leg) {
      warnings.push(`The ${role} ${optionType} at ${row.strike} has no usable mid premium.`);
      return;
    }
    legs.push({ ...leg, id: `${leg.id}-${role}` });
  };

  const legs: StrategyLeg[] = [];
  const atmCall = selectPricedAtmRow(rows, spot, "call");
  const atmPut = selectPricedAtmRow(rows, spot, "put");

  if (templateId === "call_spread") {
    pushLeg(legs, atmCall, "call", "long", "body");
    pushLeg(legs, templateWingRow(rows, "call", "upper", spot, wingPct), "call", "short", "wing");
  } else if (templateId === "put_spread") {
    pushLeg(legs, atmPut, "put", "long", "body");
    pushLeg(legs, templateWingRow(rows, "put", "lower", spot, wingPct), "put", "short", "wing");
  } else if (templateId === "straddle") {
    const both = (rows ?? []).filter(
      (row) =>
        row.callMidpoint != null && row.callMidpoint > 0 && row.putMidpoint != null && row.putMidpoint > 0
    );
    const atmBoth = nearestTemplateRow(both, spot) ?? atmCall ?? atmPut;
    pushLeg(legs, atmBoth, "call", "long", "straddle call");
    pushLeg(legs, atmBoth, "put", "long", "straddle put");
  } else if (templateId === "collar") {
    pushLeg(legs, templateWingRow(rows, "put", "lower", spot, wingPct), "put", "long", "protective");
    pushLeg(legs, templateWingRow(rows, "call", "upper", spot, wingPct), "call", "short", "covered");
    warnings.push("Collar legs assume an existing long underlying position; only the option legs are modeled here.");
  } else if (templateId === "risk_reversal") {
    pushLeg(legs, templateWingRow(rows, "put", "lower", spot, wingPct), "put", "short", "funding");
    pushLeg(legs, templateWingRow(rows, "call", "upper", spot, wingPct), "call", "long", "upside");
    warnings.push("Risk reversal includes a short put; downside risk below the put strike is undefined-risk.");
  }

  if (legs.length < 2) {
    warnings.push("Template is incomplete; review the chain for missing quotes before relying on the payoff.");
  }
  return { legs, warnings };
}

export function deriveStrategyPayoff(
  legs: StrategyLeg[],
  spot: number | null | undefined,
  steps = 21
): StrategyPayoffSummary {
  const cleanLegs = legs.filter(
    (leg) =>
      Number.isFinite(leg.strike) &&
      Number.isFinite(leg.premium) &&
      Number.isFinite(leg.quantity) &&
      leg.quantity > 0
  );
  const center = spot && Number.isFinite(spot) && spot > 0
    ? spot
    : cleanLegs.length
      ? cleanLegs.reduce((sum, leg) => sum + leg.strike, 0) / cleanLegs.length
      : 100;
  const strikes = cleanLegs.map((leg) => leg.strike);
  const minStrike = strikes.length ? Math.min(...strikes) : center * 0.85;
  const maxStrike = strikes.length ? Math.max(...strikes) : center * 1.15;
  const lower = Math.max(0.01, Math.min(center * 0.75, minStrike * 0.9));
  const upper = Math.max(center * 1.25, maxStrike * 1.1);
  const count = Math.max(7, steps | 1);
  const step = (upper - lower) / Math.max(1, count - 1);
  const netPremium = cleanLegs.reduce((sum, leg) => {
    const signed = leg.side === "long" ? -leg.premium : leg.premium;
    return sum + signed * leg.quantity;
  }, 0);
  const points = Array.from({ length: count }, (_, index) => {
    const underlyingPrice = lower + step * index;
    const payoff = cleanLegs.reduce((sum, leg) => {
      const intrinsic =
        leg.optionType === "call"
          ? Math.max(0, underlyingPrice - leg.strike)
          : Math.max(0, leg.strike - underlyingPrice);
      const signedIntrinsic = leg.side === "long" ? intrinsic - leg.premium : leg.premium - intrinsic;
      return sum + signedIntrinsic * leg.quantity;
    }, 0);
    return {
      underlyingPrice,
      payoff,
      returnPct: Math.abs(netPremium) > 0 ? payoff / Math.abs(netPremium) : null,
    };
  });
  const payoffs = points.map((point) => point.payoff);
  // Boundedness comes from the structure, not from any single short leg: only a
  // net-short/net-long call tail is open-ended (price has no upper bound), while
  // the downside extreme is the finite payoff at an underlying price of zero.
  // A put spread is defined-risk even though it contains a short put.
  const rightTailSlope = cleanLegs.reduce(
    (sum, leg) => sum + (leg.optionType === "call" ? (leg.side === "long" ? 1 : -1) * leg.quantity : 0),
    0
  );
  const payoffAtZero = cleanLegs.reduce((sum, leg) => {
    const intrinsic = leg.optionType === "put" ? leg.strike : 0;
    const signedIntrinsic = leg.side === "long" ? intrinsic - leg.premium : leg.premium - intrinsic;
    return sum + signedIntrinsic * leg.quantity;
  }, 0);
  return {
    points,
    netPremium,
    maxProfit: rightTailSlope > 0 ? null : Math.max(...payoffs, payoffAtZero),
    maxLoss: rightTailSlope < 0 ? null : Math.min(...payoffs, payoffAtZero),
    breakevens: cleanLegs.length ? deriveBreakevens(points) : [],
  };
}

export function deriveStrategyPayoffMatrix(
  legs: StrategyLeg[],
  rows: ChainRow[] | null | undefined,
  spot: number | null | undefined,
  priceSteps = 15,
  dteSteps = 9,
  rate = 0
): StrategyPayoffMatrix | null {
  if (!(spot != null && Number.isFinite(spot) && spot > 0)) {
    return null;
  }
  const chainByKey = new Map((rows ?? []).map((row) => [`${row.expiry}:${row.strike}`, row]));
  const pricedLegs = legs
    .map((leg) => {
      const chainRow = chainByKey.get(`${leg.expiry}:${leg.strike}`);
      const sigma = (leg.optionType === "call" ? chainRow?.callIv : chainRow?.putIv) ?? chainRow?.blendedIv ?? null;
      const dte = daysToExpiry(leg.expiry);
      return { ...leg, sigma, dte };
    })
    .filter(
      (leg): leg is StrategyLeg & { sigma: number; dte: number } =>
        Number.isFinite(leg.strike) &&
        Number.isFinite(leg.premium) &&
        leg.premium > 0 &&
        Number.isFinite(leg.quantity) &&
        leg.quantity > 0 &&
        leg.sigma != null &&
        Number.isFinite(leg.sigma) &&
        leg.sigma > 0
    );
  if (!pricedLegs.length) {
    return null;
  }

  const maxDte = Math.max(...pricedLegs.map((leg) => leg.dte), 0);
  const columnCount = Math.max(2, dteSteps);
  const dteColumns: number[] = [];
  for (let index = 0; index < columnCount; index += 1) {
    const dte = Math.round(maxDte * (1 - index / (columnCount - 1)));
    if (!dteColumns.includes(dte)) {
      dteColumns.push(dte);
    }
  }
  if (dteColumns[dteColumns.length - 1] !== 0) {
    dteColumns.push(0);
  }

  const weightedSigma =
    pricedLegs.reduce((sum, leg) => sum + leg.sigma * Math.max(Math.abs(leg.quantity), 1), 0) /
    pricedLegs.reduce((sum, leg) => sum + Math.max(Math.abs(leg.quantity), 1), 0);
  const horizonYears = Math.max(maxDte / 365, 1 / 365);
  const span = Math.min(0.65, Math.max(0.2, 2.5 * weightedSigma * Math.sqrt(horizonYears)));
  const rowCount = Math.max(7, priceSteps | 1);
  const upper = spot * (1 + span);
  const lower = Math.max(0.01, spot * (1 - span));
  const priceStep = (upper - lower) / Math.max(1, rowCount - 1);
  const riskBasis = Math.max(
    pricedLegs
      .filter((leg) => leg.side === "long")
      .reduce((sum, leg) => sum + leg.premium * leg.quantity, 0),
    Math.abs(
      pricedLegs.reduce((sum, leg) => {
        const signed = leg.side === "long" ? -leg.premium : leg.premium;
        return sum + signed * leg.quantity;
      }, 0)
    ),
    0.01
  );

  let maxAbsPl = 0.01;
  const matrixRows: OptionPayoffRow[] = [];
  for (let index = 0; index < rowCount; index += 1) {
    const price = upper - priceStep * index;
    const cells: OptionPayoffCell[] = dteColumns.map((dte) => {
      const pl = pricedLegs.reduce((sum, leg) => {
        const years = Math.min(dte, leg.dte) / 365;
        const value = blackScholesPrice(leg.optionType, price, leg.strike, years, leg.sigma, rate);
        const legPl = leg.side === "long" ? value - leg.premium : leg.premium - value;
        return sum + legPl * leg.quantity;
      }, 0);
      maxAbsPl = Math.max(maxAbsPl, Math.abs(pl));
      return { dte, pct: pl / riskBasis, pl, value: pl };
    });
    matrixRows.push({ price, movePct: price / spot - 1, cells });
  }

  return { dteColumns, rows: matrixRows, maxAbsPl, riskBasis };
}

export function deriveRealizedVolatility(
  points: TimeSeriesPoint[] | null | undefined,
  frontAtmIv: number | null | undefined,
  windows = [20, 60, 120]
): RealizedVolatilityPoint[] {
  const prices = (points ?? [])
    .map((point) => Number(point.value))
    .filter((value) => Number.isFinite(value) && value > 0);
  const returns: number[] = [];
  for (let index = 1; index < prices.length; index += 1) {
    returns.push(Math.log(prices[index] / prices[index - 1]));
  }
  return windows.map((window) => {
    const sample = returns.slice(-window);
    const realizedVol = sample.length >= Math.max(5, Math.floor(window * 0.5))
      ? standardDeviation(sample) * Math.sqrt(252)
      : null;
    return {
      window,
      realizedVol,
      spreadToFrontIv: realizedVol != null && frontAtmIv != null ? frontAtmIv - realizedVol : null,
      observationCount: sample.length,
    };
  });
}

export function deriveDistributionBuckets(surface: IvSurface | null, bucketCount = 13): DistributionBucket[] {
  const stats = deriveSurfaceStats(surface);
  if (!surface?.spot || !stats.frontAtmIv || !stats.frontExpiry) {
    return [];
  }
  const spot = surface.spot;
  const frontAtmIv = stats.frontAtmIv;
  const days = daysToExpiry(stats.frontExpiry);
  const years = Math.max(days / 365, 1 / 365);
  const sigma = frontAtmIv * Math.sqrt(years);
  if (!Number.isFinite(sigma) || sigma <= 0) {
    return [];
  }
  const count = Math.max(7, bucketCount | 1);
  const minPrice = spot * Math.exp(-2.5 * sigma);
  const maxPrice = spot * Math.exp(2.5 * sigma);
  const step = (maxPrice - minPrice) / Math.max(1, count - 1);
  const buckets = Array.from({ length: count }, (_, index) => {
    const price = minPrice + step * index;
    const lower = index === 0 ? 0 : price - step / 2;
    const upper = index === count - 1 ? Number.POSITIVE_INFINITY : price + step / 2;
    return {
      price,
      probability: logNormalCdf(upper, spot, sigma) - logNormalCdf(lower, spot, sigma),
      label: `${Math.round(price)}`,
    };
  });
  const total = buckets.reduce((sum, bucket) => sum + bucket.probability, 0);
  return total > 0
    ? buckets.map((bucket) => ({ ...bucket, probability: bucket.probability / total }))
    : buckets;
}

export function deriveImpliedProbabilitySurface(surface: IvSurface | null): ImpliedProbabilitySurface | null {
  if (!surface?.spot || !surface.expiries.length || surface.strikes.length < 2) {
    return null;
  }
  const strikes = surface.strikes.map(Number).filter((strike) => Number.isFinite(strike) && strike > 0);
  if (strikes.length !== surface.strikes.length) {
    return null;
  }

  const densityGrid = surface.expiries.map((expiry, rowIndex) => {
    const years = Math.max(daysToExpiry(expiry) / 365, 1 / 365);
    return strikes.map((strike, colIndex) => {
      const iv = surface.iv_grid[rowIndex]?.[colIndex];
      const sigma = iv != null && Number.isFinite(iv) && iv > 0 ? iv * Math.sqrt(years) : null;
      return sigma != null ? logNormalPdf(strike, surface.spot!, sigma) : 0;
    });
  });

  const coverageByExpiry = densityGrid.map((row) => integrateDensity(strikes, row));
  const normalizedDensityGrid = densityGrid.map((row, rowIndex) => {
    const coverage = coverageByExpiry[rowIndex] ?? 0;
    return coverage > 0 ? row.map((density) => density / coverage) : row;
  });
  const maxDensity = Math.max(...normalizedDensityGrid.flat().filter((value) => Number.isFinite(value)), 0);

  return {
    expiries: [...surface.expiries],
    strikes,
    densityGrid: normalizedDensityGrid,
    maxDensity,
    coverageByExpiry,
  };
}

export function deriveImpliedProbabilitySlice(
  probabilitySurface: ImpliedProbabilitySurface | null,
  expiry: string | null | undefined,
  width = 620,
  height = 220
): ImpliedProbabilitySlice | null {
  if (!probabilitySurface || !expiry) {
    return null;
  }
  const rowIndex = probabilitySurface.expiries.indexOf(expiry);
  const row = rowIndex >= 0 ? probabilitySurface.densityGrid[rowIndex] : null;
  if (!row || row.length < 2) {
    return null;
  }

  const padLeft = 44;
  const padRight = 12;
  const padTop = 10;
  const padBottom = 24;
  const strikes = probabilitySurface.strikes;
  const minStrike = Math.min(...strikes);
  const maxStrike = Math.max(...strikes);
  const maxDensity = Math.max(...row.filter((value) => Number.isFinite(value)), 0);
  if (maxDensity <= 0) {
    return null;
  }
  const strikeRange = Math.max(maxStrike - minStrike, 1e-6);
  const baseline = height - padBottom;
  const projectX = (strike: number) => padLeft + ((strike - minStrike) / strikeRange) * (width - padLeft - padRight);
  const projectY = (density: number) => baseline - (density / maxDensity) * (height - padTop - padBottom);

  const points = strikes.map((strike, index) => ({
    strike,
    density: row[index] ?? 0,
    x: projectX(strike),
    y: projectY(row[index] ?? 0),
  }));
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${baseline.toFixed(1)} L${points[0].x.toFixed(1)},${baseline.toFixed(1)} Z`;

  return {
    expiry,
    dte: daysToExpiry(expiry),
    width,
    height,
    points,
    linePath,
    areaPath,
    minStrike,
    maxStrike,
    maxDensity,
    coverageMass: probabilitySurface.coverageByExpiry[rowIndex] ?? 0,
    baseline,
  };
}

export function deriveImpliedProbabilitySelection(
  slice: ImpliedProbabilitySlice | null,
  lowerStrike: number | null | undefined,
  upperStrike: number | null | undefined
): ImpliedProbabilitySelection | null {
  if (!slice || lowerStrike == null || upperStrike == null || !Number.isFinite(lowerStrike) || !Number.isFinite(upperStrike)) {
    return null;
  }
  const lower = Math.max(slice.minStrike, Math.min(lowerStrike, upperStrike));
  const upper = Math.min(slice.maxStrike, Math.max(lowerStrike, upperStrike));
  if (upper <= lower) {
    return null;
  }
  const samples = slice.points
    .filter((point) => point.strike > lower && point.strike < upper)
    .map((point) => ({ strike: point.strike, density: point.density }));
  const selected = [
    { strike: lower, density: interpolateSliceDensity(slice, lower) },
    ...samples,
    { strike: upper, density: interpolateSliceDensity(slice, upper) },
  ];
  const probabilityMass = integrateDensity(
    selected.map((point) => point.strike),
    selected.map((point) => point.density)
  );
  const areaPoints = selected.map((point) => ({
    x: projectSliceX(slice, point.strike),
    y: projectSliceY(slice, point.density),
  }));
  const areaLine = areaPoints.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const areaPath = `${areaLine} L${areaPoints[areaPoints.length - 1].x.toFixed(1)},${slice.baseline.toFixed(1)} L${areaPoints[0].x.toFixed(1)},${slice.baseline.toFixed(1)} Z`;
  return { lowerStrike: lower, upperStrike: upper, probabilityMass, areaPath };
}

export function deriveSurfacePaths(surface: IvSurface | null, width = 520, height = 240): SurfacePath[] {
  if (!surface?.expiries.length || !surface.strikes.length) {
    return [];
  }
  const values = surface.iv_grid.flat().filter((value) => Number.isFinite(value));
  const minIv = values.length ? Math.min(...values) : 0;
  const maxIv = values.length ? Math.max(...values) : 1;
  const valueRange = Math.max(maxIv - minIv, 0.01);
  const rowCount = surface.expiries.length;
  const colCount = surface.strikes.length;

  const project = (rowIndex: number, colIndex: number, value: number | null | undefined) => {
    const xRatio = colCount <= 1 ? 0.5 : colIndex / (colCount - 1);
    const yRatio = rowCount <= 1 ? 0.5 : rowIndex / (rowCount - 1);
    const zRatio = value == null || !Number.isFinite(value) ? 0 : (value - minIv) / valueRange;
    const x = 32 + xRatio * (width - 112) + yRatio * 54;
    const y = height - 42 - yRatio * 92 - zRatio * 92;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  const paths: SurfacePath[] = [];
  surface.iv_grid.forEach((row, rowIndex) => {
    paths.push({
      id: `expiry-${rowIndex}`,
      points: row.map((value, colIndex) => project(rowIndex, colIndex, value)).join(" "),
      value: row[nearestStrikeIndex(surface)] ?? null,
    });
  });
  for (let colIndex = 0; colIndex < colCount; colIndex += Math.max(1, Math.floor(colCount / 8))) {
    paths.push({
      id: `strike-${colIndex}`,
      points: surface.iv_grid.map((row, rowIndex) => project(rowIndex, colIndex, row[colIndex])).join(" "),
      value: surface.iv_grid[0]?.[colIndex] ?? null,
    });
  }
  return paths;
}

export function deriveIvSmile(
  rows: ChainRow[],
  atmStrike: number | null | undefined,
  width = 320,
  height = 150,
  fittedSamples: Array<{ strike: number; iv: number }> = []
): IvSmile | null {
  const padLeft = 32;
  const padRight = 8;
  const padTop = 10;
  const padBottom = 18;
  const samples = rows
    .map((row) => ({
      strike: row.strike,
      iv:
        row.blendedIv ??
        (row.callIv != null && row.putIv != null
          ? (row.callIv + row.putIv) / 2
          : row.callIv ?? row.putIv ?? null),
    }))
    .filter((sample): sample is { strike: number; iv: number } => Number.isFinite(sample.strike) && sample.iv != null && Number.isFinite(sample.iv))
    .sort((left, right) => left.strike - right.strike);
  if (samples.length < 2) {
    return null;
  }

  const fitSamples = fittedSamples
    .filter((sample) => Number.isFinite(sample.strike) && Number.isFinite(sample.iv) && sample.iv > 0)
    .sort((left, right) => left.strike - right.strike);
  const scaleSamples = fitSamples.length >= 2 ? [...samples, ...fitSamples] : samples;
  const strikes = scaleSamples.map((sample) => sample.strike);
  const ivs = scaleSamples.map((sample) => sample.iv);
  const minStrike = Math.min(...strikes);
  const maxStrike = Math.max(...strikes);
  const rawMinIv = Math.min(...ivs);
  const rawMaxIv = Math.max(...ivs);
  const ivPad = Math.max((rawMaxIv - rawMinIv) * 0.12, 0.005);
  const minIv = Math.max(0, rawMinIv - ivPad);
  const maxIv = rawMaxIv + ivPad;
  const strikeRange = Math.max(maxStrike - minStrike, 1e-6);
  const ivRange = Math.max(maxIv - minIv, 1e-6);

  const projectX = (strike: number) => padLeft + ((strike - minStrike) / strikeRange) * (width - padLeft - padRight);
  const projectY = (iv: number) => height - padBottom - ((iv - minIv) / ivRange) * (height - padTop - padBottom);

  const points: IvSmilePoint[] = samples.map((sample) => ({
    strike: sample.strike,
    iv: sample.iv,
    x: projectX(sample.strike),
    y: projectY(sample.iv),
    isAtm: atmStrike != null && sample.strike === atmStrike,
  }));

  const fitPoints: IvSmilePoint[] = fitSamples.map((sample) => ({
    strike: sample.strike,
    iv: sample.iv,
    x: projectX(sample.strike),
    y: projectY(sample.iv),
    isAtm: atmStrike != null && sample.strike === atmStrike,
  }));

  const lineSeries = fitPoints.length >= 2 ? fitPoints : points;
  const linePath = lineSeries
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(" ");
  const baseline = height - padBottom;
  const areaPath = `${linePath} L${lineSeries[lineSeries.length - 1].x.toFixed(1)},${baseline.toFixed(1)} L${lineSeries[0].x.toFixed(1)},${baseline.toFixed(1)} Z`;
  const atmX = atmStrike != null && Number.isFinite(atmStrike) ? projectX(atmStrike) : null;

  return {
    width,
    height,
    points,
    linePath,
    areaPath,
    atmX,
    minIv,
    maxIv,
    minStrike,
    maxStrike,
    fitPoints,
  };
}

export interface TermCurvePoint {
  expiry: string;
  dte: number;
  iv: number;
  x: number;
  y: number;
}

export interface TermCurve {
  width: number;
  height: number;
  points: TermCurvePoint[];
  linePath: string;
  areaPath: string;
  minIv: number;
  maxIv: number;
  observedPoints: TermCurvePoint[];
}

export function deriveTermCurve(
  term: Array<{ expiry: string; iv: number | null }>,
  width = 300,
  height = 132,
  observedTerm: Array<{ expiry: string; iv: number | null }> = []
): TermCurve | null {
  const padLeft = 34;
  const padRight = 10;
  const padTop = 10;
  const padBottom = 20;
  const samples = (term ?? [])
    .map((point) => ({ expiry: point.expiry, dte: daysToExpiry(point.expiry), iv: point.iv }))
    .filter((point): point is TermCurvePoint => point.iv != null && Number.isFinite(point.iv))
    .sort((left, right) => left.dte - right.dte);
  if (samples.length < 2) {
    return null;
  }

  const observedSamples = observedTerm
    .map((point) => ({ expiry: point.expiry, dte: daysToExpiry(point.expiry), iv: point.iv }))
    .filter((point): point is TermCurvePoint => point.iv != null && Number.isFinite(point.iv))
    .sort((left, right) => left.dte - right.dte);
  const scaleSamples = [...samples, ...observedSamples];
  const dtes = scaleSamples.map((point) => point.dte);
  const ivs = scaleSamples.map((point) => point.iv);
  const minDte = Math.min(...dtes);
  const maxDte = Math.max(...dtes);
  const rawMinIv = Math.min(...ivs);
  const rawMaxIv = Math.max(...ivs);
  const ivPad = Math.max((rawMaxIv - rawMinIv) * 0.12, 0.004);
  const minIv = Math.max(0, rawMinIv - ivPad);
  const maxIv = rawMaxIv + ivPad;
  const dteRange = Math.max(maxDte - minDte, 1e-6);
  const ivRange = Math.max(maxIv - minIv, 1e-6);

  const projectX = (d: number) => padLeft + ((d - minDte) / dteRange) * (width - padLeft - padRight);
  const projectY = (iv: number) => height - padBottom - ((iv - minIv) / ivRange) * (height - padTop - padBottom);

  const points: TermCurvePoint[] = samples.map((point) => ({
    ...point,
    x: projectX(point.dte),
    y: projectY(point.iv),
  }));
  const observedPoints: TermCurvePoint[] = observedSamples.map((point) => ({
    ...point,
    x: projectX(point.dte),
    y: projectY(point.iv),
  }));
  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(" ");
  const baseline = height - padBottom;
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${baseline.toFixed(1)} L${points[0].x.toFixed(1)},${baseline.toFixed(1)} Z`;

  return { width, height, points, linePath, areaPath, minIv, maxIv, observedPoints };
}

export function hasParametricIvFit(surface: IvSurface | null | undefined): boolean {
  const model = surface?.surface_model?.trim().toLowerCase();
  const status = surface?.surface_model_status?.trim().toLowerCase();
  return Boolean(model && model !== "linear" && model !== "spline" && status !== "fallback" && status !== "unavailable");
}

export function deriveObservedSurfacePoints(surface: IvSurface | null | undefined): ObservedSurfacePoint[] {
  if (!surface) return [];
  const expiryIndex = new Map(surface.expiries.map((expiry, index) => [expiry, index]));
  const strikeIndex = new Map(surface.strikes.map((strike, index) => [strike, index]));
  return (surface.pairs ?? [])
    .map((pair) => {
      const rowIndex = expiryIndex.get(pair.expiry);
      const colIndex = strikeIndex.get(pair.strike);
      const iv = pair.blended_implied_volatility ??
        (pair.call_implied_volatility != null && pair.put_implied_volatility != null
          ? (pair.call_implied_volatility + pair.put_implied_volatility) / 2
          : pair.call_implied_volatility ?? pair.put_implied_volatility);
      if (rowIndex == null || colIndex == null || iv == null || !Number.isFinite(iv) || iv <= 0) return null;
      return { expiry: pair.expiry, strike: pair.strike, dte: pair.days_to_expiry, iv, rowIndex, colIndex };
    })
    .filter((point): point is ObservedSurfacePoint => point != null);
}

export function deriveFittedSmileSamples(
  surface: IvSurface | null | undefined,
  expiry: string | null | undefined
): Array<{ strike: number; iv: number }> {
  if (!surface || !expiry) return [];
  const rowIndex = surface.expiries.indexOf(expiry);
  if (rowIndex < 0) return [];
  return surface.strikes
    .map((strike, colIndex) => ({ strike, iv: surface.iv_grid[rowIndex]?.[colIndex] }))
    .filter((sample): sample is { strike: number; iv: number } => sample.iv != null && Number.isFinite(sample.iv) && sample.iv > 0);
}

export function deriveObservedTermStructure(surface: IvSurface | null | undefined): Array<{ expiry: string; iv: number }> {
  if (!surface) return [];
  return surface.expiries.flatMap((expiry) => {
    const rows = deriveChainRows(surface, expiry).filter((row) => row.blendedIv != null && Number.isFinite(row.blendedIv));
    if (!rows.length) return [];
    const nearest = [...rows].sort((left, right) =>
      Math.abs(left.strike - (surface.spot ?? left.strike)) - Math.abs(right.strike - (surface.spot ?? right.strike))
    )[0];
    return nearest.blendedIv == null ? [] : [{ expiry, iv: nearest.blendedIv }];
  });
}

export function blackScholesPrice(
  optionType: StrategyOptionType,
  spot: number,
  strike: number,
  years: number,
  sigma: number,
  rate = 0
): number {
  const intrinsic = optionType === "call" ? Math.max(0, spot - strike) : Math.max(0, strike - spot);
  if (!(spot > 0) || !(strike > 0)) {
    return intrinsic;
  }
  if (!(years > 0) || !(sigma > 0)) {
    return intrinsic;
  }
  const sqrtT = Math.sqrt(years);
  const d1 = (Math.log(spot / strike) + (rate + (sigma * sigma) / 2) * years) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  const discount = Math.exp(-rate * years);
  if (optionType === "call") {
    return spot * normalCdf(d1) - strike * discount * normalCdf(d2);
  }
  return strike * discount * normalCdf(-d2) - spot * normalCdf(-d1);
}

export function blackScholesGreeks(
  optionType: StrategyOptionType,
  spot: number,
  strike: number,
  years: number,
  sigma: number,
  rate = 0
): OptionGreekSet {
  if (!(spot > 0) || !(strike > 0) || !(years > 0) || !(sigma > 0)) {
    const intrinsicDelta =
      optionType === "call"
        ? spot > strike ? 1 : 0
        : spot < strike ? -1 : 0;
    return { delta: intrinsicDelta, gamma: 0, vega: 0, theta: 0, rho: 0, sigma: Math.max(sigma || 0, 0) };
  }
  const sqrtT = Math.sqrt(years);
  const d1 = (Math.log(spot / strike) + (rate + (sigma * sigma) / 2) * years) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  const discount = Math.exp(-rate * years);
  const pdf = normalPdf(d1);
  const gamma = pdf / (spot * sigma * sqrtT);
  const vega = (spot * pdf * sqrtT) / 100;
  const carryTheta = optionType === "call"
    ? -rate * strike * discount * normalCdf(d2)
    : rate * strike * discount * normalCdf(-d2);
  const theta = (-(spot * pdf * sigma) / (2 * sqrtT) + carryTheta) / 365;
  const delta = optionType === "call" ? normalCdf(d1) : normalCdf(d1) - 1;
  const rho = optionType === "call"
    ? (strike * years * discount * normalCdf(d2)) / 100
    : (-strike * years * discount * normalCdf(-d2)) / 100;
  return { delta, gamma, vega, theta, rho, sigma };
}

export function deriveChainGreekRows(surface: IvSurface | null, expiry: string | null | undefined): ChainGreekRow[] {
  if (!surface?.spot || !expiry || !surface.expiries.length || !surface.strikes.length) {
    return [];
  }
  const rowIndex = surface.expiries.indexOf(expiry);
  if (rowIndex < 0) {
    return [];
  }
  const dte = daysToExpiry(expiry);
  const years = Math.max(dte / 365, 1 / 365);
  return surface.strikes.map((strike, colIndex) => {
    const sigma = surface.iv_grid[rowIndex]?.[colIndex];
    const hasSigma = sigma != null && Number.isFinite(sigma) && sigma > 0;
    return {
      expiry,
      strike,
      dte,
      call: hasSigma ? blackScholesGreeks("call", surface.spot!, strike, years, sigma as number) : null,
      put: hasSigma ? blackScholesGreeks("put", surface.spot!, strike, years, sigma as number) : null,
    };
  });
}

export function deriveStrategyGreeks(legs: StrategyLeg[], surface: IvSurface | null): StrategyGreekSummary | null {
  if (!surface?.spot || !legs.length) {
    return null;
  }
  let summary: StrategyGreekSummary = { delta: 0, gamma: 0, vega: 0, theta: 0, rho: 0, legCount: 0 };
  for (const leg of legs) {
    const expiryIndex = surface.expiries.indexOf(leg.expiry);
    const strikeIndex = surface.strikes.findIndex((strike) => Math.abs(strike - leg.strike) < 1e-8);
    if (expiryIndex < 0 || strikeIndex < 0) {
      continue;
    }
    const sigma = surface.iv_grid[expiryIndex]?.[strikeIndex];
    if (!(sigma != null && Number.isFinite(sigma) && sigma > 0)) {
      continue;
    }
    const years = Math.max(daysToExpiry(leg.expiry) / 365, 1 / 365);
    const greeks = blackScholesGreeks(leg.optionType, surface.spot, leg.strike, years, sigma);
    const side = leg.side === "long" ? 1 : -1;
    const weight = side * leg.quantity;
    summary = {
      delta: summary.delta + greeks.delta * weight,
      gamma: summary.gamma + greeks.gamma * weight,
      vega: summary.vega + greeks.vega * weight,
      theta: summary.theta + greeks.theta * weight,
      rho: summary.rho + greeks.rho * weight,
      legCount: summary.legCount + 1,
    };
  }
  return summary.legCount ? summary : null;
}

/**
 * Pick the strike nearest spot that is actually priced for the requested option
 * type (finite premium and IV). The literal nearest-to-spot strike is often
 * unquoted on illiquid/odd strikes, so we fall back outward to the closest
 * tradable contract rather than failing.
 */
export function selectPricedAtmRow(
  rows: ChainRow[] | null | undefined,
  spot: number | null | undefined,
  optionType: StrategyOptionType
): ChainRow | null {
  if (!rows?.length || !(spot != null && Number.isFinite(spot) && spot > 0)) {
    return null;
  }
  const priced = rows.filter((row) => {
    const premium = optionType === "call" ? row.callMidpoint : row.putMidpoint;
    const sigma = (optionType === "call" ? row.callIv : row.putIv) ?? row.blendedIv ?? null;
    return (
      Number.isFinite(row.strike) &&
      premium != null &&
      Number.isFinite(premium) &&
      premium > 0 &&
      sigma != null &&
      Number.isFinite(sigma) &&
      sigma > 0
    );
  });
  if (!priced.length) {
    return null;
  }
  return minBy(priced, (row) => Math.abs(row.strike - spot));
}

export function deriveOptionPayoffMatrix(
  rows: ChainRow[] | null | undefined,
  spot: number | null | undefined,
  optionType: PayoffGlanceType,
  maxDte: number | null | undefined = null,
  priceSteps = 15,
  dteSteps = 9,
  rate = 0
): OptionPayoffMatrix | null {
  if (!(spot != null && Number.isFinite(spot) && spot > 0)) {
    return null;
  }
  if (optionType === "straddle") {
    return deriveStraddlePayoffMatrix(rows, spot, maxDte, priceSteps, dteSteps, rate);
  }
  const atmRow = selectPricedAtmRow(rows, spot, optionType);
  if (!atmRow) {
    return null;
  }
  const strike = atmRow.strike;
  const premium = (optionType === "call" ? atmRow.callMidpoint : atmRow.putMidpoint) as number;
  const sigma = ((optionType === "call" ? atmRow.callIv : atmRow.putIv) ?? atmRow.blendedIv) as number;
  const resolvedMaxDte = maxDte ?? daysToExpiry(atmRow.expiry);
  const boundedMaxDte = Math.max(0, Math.round(resolvedMaxDte));

  // DTE columns: highest remaining DTE on the left, expiry (0) on the right.
  const columnCount = Math.max(2, dteSteps);
  const dteColumns: number[] = [];
  for (let index = 0; index < columnCount; index += 1) {
    const dte = Math.round(boundedMaxDte * (1 - index / (columnCount - 1)));
    if (!dteColumns.includes(dte)) {
      dteColumns.push(dte);
    }
  }
  if (dteColumns[dteColumns.length - 1] !== 0) {
    dteColumns.push(0);
  }

  // Price levels: span ±2.5 sigma over the longest horizon, clamped to a readable band.
  const horizonYears = Math.max(boundedMaxDte / 365, 1 / 365);
  const span = Math.min(0.6, Math.max(0.2, 2.5 * sigma * Math.sqrt(horizonYears)));
  const rowCount = Math.max(7, priceSteps | 1);
  const upper = spot * (1 + span);
  const lower = spot * (1 - span);
  const priceStep = (upper - lower) / Math.max(1, rowCount - 1);

  const matrixRows: OptionPayoffRow[] = [];
  let maxGain = 0.01;
  for (let index = 0; index < rowCount; index += 1) {
    // Top row = highest price.
    const price = upper - priceStep * index;
    const cells: OptionPayoffCell[] = dteColumns.map((dte) => {
      const years = dte / 365;
      const value = blackScholesPrice(optionType, price, strike, years, sigma, rate);
      const pl = value - premium;
      const pct = pl / premium;
      if (pct > maxGain) {
        maxGain = pct;
      }
      return { dte, pct, pl, value };
    });
    matrixRows.push({ price, movePct: price / spot - 1, cells });
  }

  return {
    optionType,
    strike,
    premium,
    sigma,
    spot,
    maxDte: boundedMaxDte,
    dteColumns,
    rows: matrixRows,
    maxGain,
  };
}

/**
 * Neutral payoff glance: long ATM straddle (call + put at the strike nearest
 * spot priced on both sides), repriced with a shared sigma across price/DTE.
 */
function deriveStraddlePayoffMatrix(
  rows: ChainRow[] | null | undefined,
  spot: number,
  maxDte: number | null | undefined,
  priceSteps: number,
  dteSteps: number,
  rate: number
): OptionPayoffMatrix | null {
  const priced = (rows ?? []).filter(
    (row) =>
      Number.isFinite(row.strike) &&
      row.callMidpoint != null &&
      Number.isFinite(row.callMidpoint) &&
      row.callMidpoint > 0 &&
      row.putMidpoint != null &&
      Number.isFinite(row.putMidpoint) &&
      row.putMidpoint > 0 &&
      ((row.blendedIv ?? row.callIv ?? row.putIv) ?? 0) > 0
  );
  if (!priced.length) {
    return null;
  }
  const atmRow = minBy(priced, (row) => Math.abs(row.strike - spot));
  if (!atmRow) {
    return null;
  }
  const strike = atmRow.strike;
  const premium = (atmRow.callMidpoint as number) + (atmRow.putMidpoint as number);
  const sigma = (atmRow.blendedIv ?? atmRow.callIv ?? atmRow.putIv) as number;
  const resolvedMaxDte = maxDte ?? daysToExpiry(atmRow.expiry);
  const boundedMaxDte = Math.max(0, Math.round(resolvedMaxDte));

  const columnCount = Math.max(2, dteSteps);
  const dteColumns: number[] = [];
  for (let index = 0; index < columnCount; index += 1) {
    const dte = Math.round(boundedMaxDte * (1 - index / (columnCount - 1)));
    if (!dteColumns.includes(dte)) {
      dteColumns.push(dte);
    }
  }
  if (dteColumns[dteColumns.length - 1] !== 0) {
    dteColumns.push(0);
  }

  const horizonYears = Math.max(boundedMaxDte / 365, 1 / 365);
  const span = Math.min(0.6, Math.max(0.2, 2.5 * sigma * Math.sqrt(horizonYears)));
  const rowCount = Math.max(7, priceSteps | 1);
  const upper = spot * (1 + span);
  const lower = spot * (1 - span);
  const priceStep = (upper - lower) / Math.max(1, rowCount - 1);

  const matrixRows: OptionPayoffRow[] = [];
  let maxGain = 0.01;
  for (let index = 0; index < rowCount; index += 1) {
    const price = upper - priceStep * index;
    const cells: OptionPayoffCell[] = dteColumns.map((dte) => {
      const years = dte / 365;
      const value =
        blackScholesPrice("call", price, strike, years, sigma, rate) +
        blackScholesPrice("put", price, strike, years, sigma, rate);
      const pl = value - premium;
      const pct = pl / premium;
      if (pct > maxGain) {
        maxGain = pct;
      }
      return { dte, pct, pl, value };
    });
    matrixRows.push({ price, movePct: price / spot - 1, cells });
  }

  return {
    optionType: "straddle",
    strike,
    premium,
    sigma,
    spot,
    maxDte: boundedMaxDte,
    dteColumns,
    rows: matrixRows,
    maxGain,
  };
}

export function daysToExpiry(expiry: string | null | undefined, now = new Date()): number {
  if (!expiry) {
    return 0;
  }
  const match = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(expiry);
  if (!match) {
    return 0;
  }
  const expiryDate = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.max(0, Math.round((expiryDate.getTime() - today) / 86_400_000));
}

function findNearestWingIndex(strikes: number[], atmIndex: number, side: "lower" | "upper") {
  if (!strikes.length) {
    return null;
  }
  const targetOffset = Math.max(2, Math.round(strikes.length * 0.18));
  const index = side === "lower" ? atmIndex - targetOffset : atmIndex + targetOffset;
  const bounded = Math.max(0, Math.min(strikes.length - 1, index));
  return bounded === atmIndex ? null : bounded;
}

function deriveMaxPainStrike(rows: ChainRow[]) {
  if (!rows.length) {
    return null;
  }
  let bestStrike: number | null = null;
  let bestPain = Number.POSITIVE_INFINITY;
  for (const candidate of rows) {
    const pain = rows.reduce((sum, row) => {
      const callOi = row.callOpenInterest ?? 0;
      const putOi = row.putOpenInterest ?? 0;
      return (
        sum +
        Math.max(0, candidate.strike - row.strike) * callOi +
        Math.max(0, row.strike - candidate.strike) * putOi
      );
    }, 0);
    if (pain < bestPain) {
      bestPain = pain;
      bestStrike = candidate.strike;
    }
  }
  return bestStrike;
}

function deriveBreakevens(points: StrategyPayoffPoint[]) {
  const levels: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1];
    const right = points[index];
    if (left.payoff === 0) {
      levels.push(left.underlyingPrice);
      continue;
    }
    if ((left.payoff < 0 && right.payoff > 0) || (left.payoff > 0 && right.payoff < 0)) {
      const slope = (right.payoff - left.payoff) / (right.underlyingPrice - left.underlyingPrice);
      if (Number.isFinite(slope) && slope !== 0) {
        levels.push(left.underlyingPrice - left.payoff / slope);
      }
    }
  }
  return levels;
}

function sumFinite(values: Array<number | null | undefined>) {
  return values.reduce<number>((sum, value) => (Number.isFinite(value) ? sum + Number(value) : sum), 0);
}

function minBy<T>(items: T[], score: (item: T) => number) {
  let best: T | null = items[0] ?? null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const value = score(item);
    if (value < bestScore) {
      best = item;
      bestScore = value;
    }
  }
  return best;
}

function standardDeviation(values: number[]) {
  if (values.length < 2) {
    return 0;
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function logNormalCdf(price: number, spot: number, sigma: number) {
  if (price <= 0) {
    return 0;
  }
  if (!Number.isFinite(price)) {
    return 1;
  }
  return normalCdf(Math.log(price / spot) / sigma);
}

function logNormalPdf(price: number, spot: number, sigma: number) {
  if (price <= 0 || spot <= 0 || sigma <= 0 || !Number.isFinite(price) || !Number.isFinite(spot) || !Number.isFinite(sigma)) {
    return 0;
  }
  const z = Math.log(price / spot) / sigma;
  return Math.exp(-0.5 * z * z) / (price * sigma * Math.sqrt(2 * Math.PI));
}

function integrateDensity(strikes: number[], densities: number[]) {
  let area = 0;
  for (let index = 1; index < strikes.length; index += 1) {
    const leftStrike = strikes[index - 1];
    const rightStrike = strikes[index];
    const leftDensity = densities[index - 1] ?? 0;
    const rightDensity = densities[index] ?? 0;
    if (
      Number.isFinite(leftStrike) &&
      Number.isFinite(rightStrike) &&
      Number.isFinite(leftDensity) &&
      Number.isFinite(rightDensity) &&
      rightStrike > leftStrike
    ) {
      area += ((leftDensity + rightDensity) / 2) * (rightStrike - leftStrike);
    }
  }
  return area;
}

function interpolateSliceDensity(slice: ImpliedProbabilitySlice, strike: number) {
  const points = slice.points;
  if (!points.length) {
    return 0;
  }
  if (strike <= points[0].strike) {
    return points[0].density;
  }
  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1];
    const right = points[index];
    if (strike <= right.strike) {
      const span = Math.max(right.strike - left.strike, 1e-6);
      const t = (strike - left.strike) / span;
      return left.density + (right.density - left.density) * t;
    }
  }
  return points[points.length - 1].density;
}

function projectSliceX(slice: ImpliedProbabilitySlice, strike: number) {
  const range = Math.max(slice.maxStrike - slice.minStrike, 1e-6);
  const leftPad = slice.points[0]?.x ?? 44;
  const rightPad = slice.width - (slice.points.at(-1)?.x ?? slice.width - 12);
  return leftPad + ((strike - slice.minStrike) / range) * (slice.width - leftPad - rightPad);
}

function projectSliceY(slice: ImpliedProbabilitySlice, density: number) {
  const top = Math.min(...slice.points.map((point) => point.y));
  const drawableHeight = Math.max(slice.baseline - top, 1);
  return slice.baseline - (density / Math.max(slice.maxDensity, 1e-9)) * drawableHeight;
}

function normalCdf(value: number) {
  return 0.5 * (1 + erf(value / Math.SQRT2));
}

function normalPdf(value: number) {
  return Math.exp(-0.5 * value * value) / Math.sqrt(2 * Math.PI);
}

function erf(value: number) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * x);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return sign * y;
}
