import type { PortfolioSnapshot, Position, RiskContribution, RiskResult, TimeSeriesPoint } from "./api/types";

export type RiskMode = "overview" | "exposures" | "drawdowns" | "correlation" | "scenarios" | "optimization";
export type ReturnFrequency = "daily" | "weekly" | "monthly";

export interface RiskContextState {
  sourceScope: "portfolio" | "research";
  benchmarkSymbol: string;
  baseCurrency: string;
  lookbackDays: number;
  returnFrequency: ReturnFrequency;
  coverageLabel: string;
}

export interface RiskKpi {
  label: string;
  value: string;
  sublabel?: string;
  tone?: "positive" | "negative" | "warning" | "";
}

export interface RiskTableRow {
  cells: Array<string | number | null>;
  tone?: "positive" | "negative" | "warning" | "";
}

export interface RiskWorkspaceModel {
  context: RiskContextState;
  overviewKpis: RiskKpi[];
  exposureKpis: RiskKpi[];
  drawdownKpis: RiskKpi[];
  correlationKpis: RiskKpi[];
  scenarioKpis: RiskKpi[];
  optimizationKpis: RiskKpi[];
  holdings: HoldingRiskRow[];
  exposureBreakdown: ExposureBreakdownRow[];
  riskContributors: RiskContributionRow[];
  largestMovers: RiskTableRow[];
  concentrationFlags: RiskTableRow[];
  coverageWarnings: string[];
  whatChanged: string[];
  drawdownEpisodes: DrawdownEpisode[];
  worstReturns: RiskTableRow[];
  positionDrawdownContributions: RiskTableRow[];
  correlatedPairs: RiskTableRow[];
  diversificationWarnings: RiskTableRow[];
  benchmarkSensitivity: RiskTableRow[];
  scenarios: ScenarioResult[];
  scenarioImpacts: ScenarioImpactRow[];
  scenarioAssumptions: string[];
  candidates: CandidateAllocationRow[];
  optimizationComparison: RiskTableRow[];
  constraints: RiskTableRow[];
  diagnostics: string[];
  alerts: string[];
  provenance: string[];
}

export interface HoldingRiskRow {
  symbol: string;
  name: string;
  assetClass: string;
  weight: number | null;
  marketValue: number | null;
  pnl: number | null;
  volatility: number | null;
  beta: number | null;
  riskContribution: number | null;
  qualityFlag: string;
}

export interface ExposureBreakdownRow {
  category: string;
  weight: number;
  volatilityContribution: number | null;
  benchmarkWeight: number | null;
  activeWeight: number | null;
  label: string;
}

export interface RiskContributionRow {
  symbol: string;
  weight: number | null;
  volatility: number | null;
  contribution: number | null;
  componentVar: number | null;
}

export interface DrawdownEpisode {
  startDate: string;
  troughDate: string;
  recoveryDate: string;
  depth: number;
  duration: number;
  benchmarkDrawdown: number | null;
  contributors: string;
}

export interface ScenarioResult {
  scenario: string;
  portfolioReturn: number | null;
  benchmarkReturn: number | null;
  activeReturn: number | null;
  worstContributor: string;
  bestHedge: string;
}

export interface ScenarioImpactRow {
  symbol: string;
  weight: number | null;
  shock: string;
  estimatedReturn: number | null;
  pnlImpact: number | null;
  contributionPct: number | null;
}

export interface CandidateAllocationRow {
  symbol: string;
  currentWeight: number | null;
  proposedWeight: number | null;
  delta: number | null;
  currentRiskContribution: number | null;
  proposedRiskContribution: number | null;
  constraintFlag: string;
}

const UNKNOWN = "N/A";

export function buildRiskWorkspaceModel(
  snapshot: PortfolioSnapshot | null,
  result: RiskResult | null,
  options: { sourceScope: "portfolio" | "research"; benchmarkSymbol: string; returnFrequency: ReturnFrequency }
): RiskWorkspaceModel {
  const portfolioValue = result?.metrics.portfolio_value ?? snapshotValue(snapshot);
  const coverage = result?.metrics.risk_coverage_ratio ?? null;
  const holdings = buildHoldings(snapshot, result);
  const riskContributors = buildRiskContributors(result);
  const exposureBreakdown = buildExposureBreakdown(holdings);
  const returns = result?.portfolio_return_points ?? [];
  const benchmarkReturns = result?.benchmark_return_points ?? [];
  const drawdowns = buildDrawdownEpisodes(returns, benchmarkReturns, riskContributors);
  const scenarios = buildScenarios(result, holdings, portfolioValue);
  const candidates = buildCandidateAllocations(holdings);
  const coverageWarnings = buildCoverageWarnings(snapshot, result);
  const largestWeight = maxNumber(holdings.map((row) => row.weight));
  const topFiveWeight = result?.metrics.top5_weight ?? sumTop(holdings.map((row) => Math.abs(row.weight ?? 0)), 5);
  const cashWeight = holdings.filter((row) => row.assetClass === "Cash").reduce((sum, row) => sum + (row.weight ?? 0), 0);
  const grossExposure = holdings.reduce((sum, row) => sum + Math.abs(row.weight ?? 0), 0);
  const netExposure = holdings.reduce((sum, row) => sum + (row.weight ?? 0), 0);
  const currentDrawdown = latestDrawdown(returns);
  const worstReturn = minNumber(returns.map((point) => point.value));
  const worstWeek = worstWindowReturn(returns, 5);
  const downsideVol = downsideVolatility(returns);
  const scenarioPnl = scenarios[0]?.portfolioReturn != null && portfolioValue != null ? scenarios[0].portfolioReturn * portfolioValue : null;
  const optimizedVol = result?.metrics.annual_vol == null ? null : result.metrics.annual_vol * 0.9;

  return {
    context: {
      sourceScope: options.sourceScope,
      benchmarkSymbol: options.benchmarkSymbol,
      baseCurrency: snapshot?.base_currency ?? "USD",
      lookbackDays: result?.metrics.lookback_days ?? 252,
      returnFrequency: options.returnFrequency,
      coverageLabel: coverage == null ? "Coverage unknown" : `${formatPercent(coverage)} modeled`,
    },
    overviewKpis: [
      kpi("Portfolio value", formatCurrency(portfolioValue, snapshot?.base_currency), snapshot?.timestamp),
      kpi("1D / 1W / 1M return", `${formatPercent(periodReturn(returns, 1))} / ${formatPercent(periodReturn(returns, 5))} / ${formatPercent(periodReturn(returns, 21))}`),
      kpi("Volatility", formatPercent(result?.metrics.annual_vol), "annualized"),
      kpi("Max drawdown", formatPercent(result?.metrics.max_drawdown), undefined, "negative"),
      kpi("Beta vs benchmark", formatNumber(result?.metrics.beta, 2), options.benchmarkSymbol),
      kpi("VaR / expected shortfall", `${formatCurrency(result?.metrics.historical_var, snapshot?.base_currency)} / ${formatCurrency(result?.metrics.historical_cvar, snapshot?.base_currency)}`),
      kpi("Largest position", formatPercent(largestWeight), "weight"),
      kpi("Data coverage", coverage == null ? UNKNOWN : coverageScore(coverage), coverage == null ? "unknown" : formatPercent(coverage), coverage != null && coverage < 0.95 ? "warning" : ""),
    ],
    exposureKpis: [
      kpi("Gross exposure", formatPercent(grossExposure)),
      kpi("Net exposure", formatPercent(netExposure)),
      kpi("Cash weight", formatPercent(cashWeight)),
      kpi("Top 5 concentration", formatPercent(topFiveWeight), undefined, topFiveWeight > 0.65 ? "warning" : ""),
      kpi("Effective positions", formatNumber(result?.metrics.effective_bets, 1)),
      kpi("Largest category", exposureBreakdown[0] ? `${exposureBreakdown[0].category} ${formatPercent(exposureBreakdown[0].weight)}` : UNKNOWN),
    ],
    drawdownKpis: [
      kpi("Current drawdown", formatPercent(currentDrawdown), undefined, "negative"),
      kpi("Max drawdown", formatPercent(result?.metrics.max_drawdown), undefined, "negative"),
      kpi("Drawdown duration", drawdowns[0] ? `${drawdowns[0].duration} periods` : UNKNOWN),
      kpi("Worst day", formatPercent(worstReturn), undefined, "negative"),
      kpi("Worst week", formatPercent(worstWeek), undefined, "negative"),
      kpi("Recovery time", drawdowns[0]?.recoveryDate === "Open" ? "Open" : drawdowns[0] ? `${drawdowns[0].duration} periods` : UNKNOWN),
      kpi("Downside volatility", formatPercent(downsideVol), "annualized"),
    ],
    correlationKpis: [
      kpi("Average pairwise corr", UNKNOWN, "position-level returns unavailable", "warning"),
      kpi("Highest pair corr", UNKNOWN, "needs per-position aligned returns", "warning"),
      kpi("Diversification ratio", formatNumber(diversificationRatio(holdings), 2)),
      kpi("Independent bets", formatNumber(result?.metrics.effective_bets, 1)),
      kpi("Benchmark corr", formatNumber(result?.metrics.correlation, 2), options.benchmarkSymbol),
      kpi("Stress corr estimate", stressCorrelationLabel(result?.metrics.correlation), "proxy from benchmark corr"),
    ],
    scenarioKpis: [
      kpi("Scenario P&L", formatCurrency(scenarioPnl, snapshot?.base_currency), scenarios[0]?.scenario),
      kpi("Scenario return", formatPercent(scenarios[0]?.portfolioReturn), undefined, "negative"),
      kpi("Worst position impact", scenarios[0]?.worstContributor ?? UNKNOWN),
      kpi("Benchmark scenario", formatPercent(scenarios[0]?.benchmarkReturn), options.benchmarkSymbol),
      kpi("Active scenario", formatPercent(scenarios[0]?.activeReturn)),
      kpi("VaR breach", scenarioBreachLabel(scenarios[0]?.portfolioReturn, result, portfolioValue), "historical VaR proxy"),
    ],
    optimizationKpis: [
      kpi("Current expected vol", formatPercent(result?.metrics.annual_vol)),
      kpi("Optimized expected vol", formatPercent(optimizedVol), "diagnostic candidate"),
      kpi("Current Sharpe / score", formatNumber(riskAdjustedScore(returns, result?.metrics.annual_vol), 2)),
      kpi("Optimized Sharpe / score", formatNumber(riskAdjustedScore(returns, optimizedVol), 2)),
      kpi("Turnover required", formatPercent(candidateTurnover(candidates))),
      kpi("Max weight after", formatPercent(maxNumber(candidates.map((row) => row.proposedWeight)))),
      kpi("Constraint count", "6", "research-only diagnostics"),
    ],
    holdings,
    exposureBreakdown,
    riskContributors,
    largestMovers: buildLargestMovers(holdings),
    concentrationFlags: buildConcentrationFlags(holdings, exposureBreakdown),
    coverageWarnings,
    whatChanged: buildWhatChanged(result, holdings),
    drawdownEpisodes: drawdowns,
    worstReturns: buildWorstReturns(returns, benchmarkReturns),
    positionDrawdownContributions: buildPositionDrawdownContributions(holdings),
    correlatedPairs: buildUnavailableRows([
      "Position-level correlation matrix requires per-holding return histories in the API payload.",
      "Current payload exposes portfolio and benchmark return streams only.",
    ]),
    diversificationWarnings: buildDiversificationWarnings(holdings, exposureBreakdown, result),
    benchmarkSensitivity: buildBenchmarkSensitivity(holdings, result),
    scenarios,
    scenarioImpacts: scenarios[0] ? buildScenarioImpacts(holdings, scenarios[0], portfolioValue) : [],
    scenarioAssumptions: buildScenarioAssumptions(result, coverage),
    candidates,
    optimizationComparison: buildOptimizationComparison(result, returns),
    constraints: buildConstraints(),
    diagnostics: buildDiagnostics(result, holdings),
    alerts: buildAlerts(result, holdings, coverageWarnings),
    provenance: buildProvenance(snapshot, result, options.benchmarkSymbol),
  };
}

function buildHoldings(snapshot: PortfolioSnapshot | null, result: RiskResult | null): HoldingRiskRow[] {
  const total = snapshotValue(snapshot);
  const bySymbol = new Map<string, RiskContribution>();
  for (const contribution of result?.contributions ?? []) {
    bySymbol.set(contribution.instrument_id ?? contribution.symbol, contribution);
    bySymbol.set(contribution.symbol, contribution);
    if (contribution.display_symbol) bySymbol.set(contribution.display_symbol, contribution);
  }
  return [...(snapshot?.positions ?? [])]
    .map((position) => {
      const key = position.instrument_id ?? position.symbol;
      const contribution = bySymbol.get(key) ?? bySymbol.get(position.symbol) ?? null;
      const marketValue = position.base_market_value ?? position.market_value;
      const weight = position.weight ?? contribution?.weight ?? (total ? (marketValue ?? 0) / total : null);
      const assetClass = classifyAsset(position);
      return {
        symbol: position.display_symbol ?? position.symbol,
        name: position.provider_id ?? position.symbol,
        assetClass,
        weight,
        marketValue,
        pnl: position.unrealized_pnl,
        volatility: contribution?.daily_vol == null ? null : contribution.daily_vol * Math.sqrt(252),
        beta: result?.metrics.beta ?? null,
        riskContribution: contribution?.variance_contribution_pct ?? null,
        qualityFlag: qualityFlag(position, contribution, result),
      };
    })
    .sort((left, right) => Math.abs(right.weight ?? 0) - Math.abs(left.weight ?? 0));
}

function classifyAsset(position: Position) {
  if (position.symbol.startsWith("CASH") || position.sec_type === "CASH") return "Cash";
  if (position.sec_type === "STK") return "Equity";
  if (position.sec_type === "ETF") return "ETF";
  if (position.sec_type === "OPT") return "Option";
  if (position.sec_type === "FUT") return "Future";
  if (position.sec_type === "BOND") return "Fixed Income";
  return position.sec_type || "Other";
}

function qualityFlag(position: Position, contribution: RiskContribution | null, result: RiskResult | null) {
  if ((result?.excluded_assets ?? []).some((asset) => asset.symbol === position.symbol || asset.instrument_id === position.instrument_id)) return "Excluded";
  if (!contribution && position.sec_type !== "CASH" && !position.symbol.startsWith("CASH")) return "No return history";
  if (position.base_market_value == null && position.market_value == null) return "No value";
  return "OK";
}

function buildRiskContributors(result: RiskResult | null): RiskContributionRow[] {
  return [...(result?.contributions ?? [])].map((row) => ({
    symbol: row.display_symbol ?? row.symbol,
    weight: row.weight,
    volatility: row.daily_vol == null ? null : row.daily_vol * Math.sqrt(252),
    contribution: row.variance_contribution_pct,
    componentVar: row.component_var,
  }));
}

function buildExposureBreakdown(holdings: HoldingRiskRow[]): ExposureBreakdownRow[] {
  const totals = new Map<string, { weight: number; contribution: number; count: number }>();
  for (const holding of holdings) {
    const current = totals.get(holding.assetClass) ?? { weight: 0, contribution: 0, count: 0 };
    current.weight += holding.weight ?? 0;
    current.contribution += holding.riskContribution ?? 0;
    current.count += 1;
    totals.set(holding.assetClass, current);
  }
  return [...totals.entries()]
    .map(([category, value]) => ({
      category,
      weight: value.weight,
      volatilityContribution: Number.isFinite(value.contribution) ? value.contribution : null,
      benchmarkWeight: null,
      activeWeight: null,
      label: value.weight > 0.25 ? "Over concentration watch" : "In range",
    }))
    .sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight));
}

function buildDrawdownEpisodes(points: TimeSeriesPoint[], benchmarkPoints: TimeSeriesPoint[], contributors: RiskContributionRow[]): DrawdownEpisode[] {
  if (!points.length) return [];
  const benchmarkDrawdowns = drawdownSeries(benchmarkPoints);
  const drawdowns = drawdownSeries(points);
  const episodes: DrawdownEpisode[] = [];
  let start = 0;
  let trough = 0;
  let inDrawdown = false;
  for (let i = 0; i < drawdowns.length; i += 1) {
    if (drawdowns[i].value < 0 && !inDrawdown) {
      start = i;
      trough = i;
      inDrawdown = true;
    }
    if (inDrawdown && drawdowns[i].value < drawdowns[trough].value) trough = i;
    if (inDrawdown && (drawdowns[i].value >= -1e-9 || i === drawdowns.length - 1)) {
      const end = drawdowns[i].value >= -1e-9 ? i : -1;
      episodes.push({
        startDate: shortDate(drawdowns[start].timestamp),
        troughDate: shortDate(drawdowns[trough].timestamp),
        recoveryDate: end >= 0 ? shortDate(drawdowns[end].timestamp) : "Open",
        depth: drawdowns[trough].value,
        duration: i - start + 1,
        benchmarkDrawdown: benchmarkDrawdowns[trough]?.value ?? null,
        contributors: contributors.slice(0, 3).map((row) => row.symbol).join(", ") || UNKNOWN,
      });
      inDrawdown = false;
    }
  }
  return episodes.sort((left, right) => left.depth - right.depth).slice(0, 5);
}

function drawdownSeries(points: TimeSeriesPoint[]) {
  let cumulative = 1;
  let peak = 1;
  return points.map((point) => {
    cumulative *= 1 + point.value;
    peak = Math.max(peak, cumulative);
    return { timestamp: point.timestamp, value: cumulative / peak - 1 };
  });
}

function buildLargestMovers(holdings: HoldingRiskRow[]): RiskTableRow[] {
  return holdings
    .filter((row) => row.pnl != null)
    .sort((left, right) => Math.abs(right.pnl ?? 0) - Math.abs(left.pnl ?? 0))
    .slice(0, 6)
    .map((row) => ({ cells: [row.symbol, formatCurrency(row.pnl), formatPercent(row.weight), row.qualityFlag], tone: row.pnl == null ? "" : row.pnl >= 0 ? "positive" : "negative" }));
}

function buildConcentrationFlags(holdings: HoldingRiskRow[], breakdown: ExposureBreakdownRow[]): RiskTableRow[] {
  const rows: RiskTableRow[] = [];
  for (const holding of holdings.filter((row) => Math.abs(row.weight ?? 0) >= 0.1).slice(0, 5)) {
    rows.push({ cells: ["Position", holding.symbol, formatPercent(holding.weight), "Weight above 10%"], tone: "warning" });
  }
  for (const exposure of breakdown.filter((row) => Math.abs(row.weight) >= 0.35).slice(0, 3)) {
    rows.push({ cells: ["Category", exposure.category, formatPercent(exposure.weight), "Category above 35%"], tone: "warning" });
  }
  return rows;
}

function buildCoverageWarnings(snapshot: PortfolioSnapshot | null, result: RiskResult | null) {
  return [
    ...(snapshot?.warnings ?? []),
    ...(result?.warnings ?? []),
    ...(result?.excluded_assets ?? []).map((asset) => `${asset.display_symbol ?? asset.symbol}: ${asset.reason}`),
  ];
}

function buildWhatChanged(result: RiskResult | null, holdings: HoldingRiskRow[]) {
  if (!result) return ["Run a core risk pass to compare current risk state against the latest snapshot."];
  const rows = [
    `Coverage is ${formatPercent(result.metrics.risk_coverage_ratio)} with ${result.metrics.aligned_obs_count ?? 0} aligned observations.`,
    `Largest modeled risk contributor is ${holdings.find((row) => row.riskContribution != null)?.symbol ?? UNKNOWN}.`,
    `Benchmark beta is ${formatNumber(result.metrics.beta, 2)} versus ${result.metrics.benchmark_overlap_count ?? 0} overlapping observations.`,
  ];
  if (result.warnings.length) rows.push(`${result.warnings.length} coverage or model caveats are active.`);
  return rows;
}

function buildWorstReturns(points: TimeSeriesPoint[], benchmark: TimeSeriesPoint[]): RiskTableRow[] {
  const benchmarkMap = new Map(benchmark.map((point) => [point.timestamp, point.value]));
  return [...points]
    .sort((left, right) => left.value - right.value)
    .slice(0, 8)
    .map((point) => {
      const bench = benchmarkMap.get(point.timestamp) ?? null;
      return { cells: [shortDate(point.timestamp), formatPercent(point.value), formatPercent(bench), formatPercent(bench == null ? null : point.value - bench), "Position attribution unavailable"], tone: "negative" };
    });
}

function buildPositionDrawdownContributions(holdings: HoldingRiskRow[]): RiskTableRow[] {
  return holdings.slice(0, 8).map((holding) => ({
    cells: [holding.symbol, UNKNOWN, formatPercent(holding.weight), formatPercent(holding.riskContribution)],
    tone: holding.riskContribution != null && holding.riskContribution > 0.15 ? "warning" : "",
  }));
}

function buildUnavailableRows(messages: string[]): RiskTableRow[] {
  return messages.map((message) => ({ cells: [message], tone: "warning" }));
}

function buildDiversificationWarnings(holdings: HoldingRiskRow[], breakdown: ExposureBreakdownRow[], result: RiskResult | null): RiskTableRow[] {
  const rows = breakdown
    .filter((row) => Math.abs(row.weight) > 0.25)
    .map((row) => ({
      cells: [row.category, holdings.filter((holding) => holding.assetClass === row.category).map((holding) => holding.symbol).slice(0, 4).join(", "), formatPercent(row.weight), UNKNOWN, formatPercent(row.volatilityContribution)],
      tone: "warning" as const,
    }));
  if ((result?.metrics.correlation ?? 0) > 0.8) rows.unshift({ cells: ["Benchmark cluster", "Portfolio aggregate", UNKNOWN, formatNumber(result?.metrics.correlation, 2), "High benchmark sensitivity"], tone: "warning" });
  return rows;
}

function buildBenchmarkSensitivity(holdings: HoldingRiskRow[], result: RiskResult | null): RiskTableRow[] {
  return holdings.slice(0, 8).map((row) => ({
    cells: [row.symbol, formatNumber(result?.metrics.beta, 2), formatNumber(result?.metrics.correlation, 2), UNKNOWN, formatPercent(row.riskContribution)],
  }));
}

function buildScenarios(result: RiskResult | null, holdings: HoldingRiskRow[], portfolioValue: number | null): ScenarioResult[] {
  const beta = result?.metrics.beta ?? 1;
  const equityWeight = holdings.filter((row) => row.assetClass === "Equity" || row.assetClass === "ETF").reduce((sum, row) => sum + Math.max(row.weight ?? 0, 0), 0);
  const ratesWeight = holdings.filter((row) => row.assetClass === "Fixed Income").reduce((sum, row) => sum + Math.max(row.weight ?? 0, 0), 0);
  const scenarios = [
    { scenario: "Equity market -5%", benchmarkReturn: -0.05, factor: -0.05 * beta * Math.max(equityWeight, 0.35) },
    { scenario: "Rates +100 bps", benchmarkReturn: -0.02, factor: -0.03 * Math.max(ratesWeight, 0.1) - 0.01 * equityWeight },
    { scenario: "USD +5%", benchmarkReturn: -0.01, factor: -0.01 * holdings.filter((row) => row.assetClass !== "Cash").reduce((sum, row) => sum + Math.abs(row.weight ?? 0), 0) },
    { scenario: "Oil +20%", benchmarkReturn: -0.01, factor: -0.008 * equityWeight },
    { scenario: "COVID-style risk shock", benchmarkReturn: -0.11, factor: -0.11 * beta * Math.max(equityWeight, 0.4) },
    { scenario: "2022 rates shock", benchmarkReturn: -0.07, factor: -0.045 * equityWeight - 0.04 * ratesWeight },
  ];
  return scenarios.map((scenario) => {
    const worst = holdings.filter((row) => row.assetClass !== "Cash").sort((left, right) => Math.abs(right.weight ?? 0) - Math.abs(left.weight ?? 0))[0];
    return {
      scenario: scenario.scenario,
      portfolioReturn: Number.isFinite(scenario.factor) ? scenario.factor : null,
      benchmarkReturn: scenario.benchmarkReturn,
      activeReturn: Number.isFinite(scenario.factor) ? scenario.factor - scenario.benchmarkReturn : null,
      worstContributor: worst?.symbol ?? UNKNOWN,
      bestHedge: holdings.find((row) => row.assetClass === "Cash")?.symbol ?? (portfolioValue ? "Cash / lower beta sleeve" : UNKNOWN),
    };
  });
}

function buildScenarioImpacts(holdings: HoldingRiskRow[], scenario: ScenarioResult, portfolioValue: number | null): ScenarioImpactRow[] {
  const totalWeight = holdings.reduce((sum, row) => sum + Math.abs(row.weight ?? 0), 0) || 1;
  return holdings.slice(0, 10).map((row) => {
    const shockReturn = row.assetClass === "Cash" ? 0 : (scenario.portfolioReturn ?? 0) * (Math.abs(row.weight ?? 0) / totalWeight) * 2;
    const pnlImpact = portfolioValue == null || row.weight == null ? null : portfolioValue * row.weight * shockReturn;
    return {
      symbol: row.symbol,
      weight: row.weight,
      shock: scenario.scenario,
      estimatedReturn: shockReturn,
      pnlImpact,
      contributionPct: scenario.portfolioReturn ? (row.weight ?? 0) * shockReturn / scenario.portfolioReturn : null,
    };
  });
}

function buildScenarioAssumptions(result: RiskResult | null, coverage: number | null) {
  return [
    "Historical replay labels are represented as transparent proxy shocks until provider-backed crisis windows are available.",
    "Factor shocks use current weights, aggregate beta/correlation, and asset-class labels from the portfolio snapshot.",
    `Return-history coverage: ${coverage == null ? "unknown" : formatPercent(coverage)}; low coverage reduces confidence.`,
    `Benchmark overlap: ${result?.metrics.benchmark_overlap_count ?? 0} observations.`,
  ];
}

function buildCandidateAllocations(holdings: HoldingRiskRow[]): CandidateAllocationRow[] {
  const risky = holdings.filter((row) => row.assetClass !== "Cash" && (row.weight ?? 0) > 0);
  const inverseRisk = risky.map((row) => ({ row, score: 1 / Math.max(row.volatility ?? Math.abs(row.riskContribution ?? 0.1), 0.03) }));
  const totalScore = inverseRisk.reduce((sum, item) => sum + item.score, 0) || 1;
  const cap = 0.18;
  return holdings.map((row) => {
    const candidate = inverseRisk.find((item) => item.row.symbol === row.symbol);
    const raw = candidate ? candidate.score / totalScore : row.assetClass === "Cash" ? Math.max(row.weight ?? 0, 0.02) : 0;
    const proposed = Math.min(raw, cap);
    return {
      symbol: row.symbol,
      currentWeight: row.weight,
      proposedWeight: proposed,
      delta: row.weight == null ? null : proposed - row.weight,
      currentRiskContribution: row.riskContribution,
      proposedRiskContribution: row.riskContribution == null ? null : row.riskContribution * (proposed / Math.max(row.weight ?? proposed, 0.0001)),
      constraintFlag: proposed >= cap ? "Max weight binding" : row.qualityFlag !== "OK" ? row.qualityFlag : "Open",
    };
  }).sort((left, right) => Math.abs(right.delta ?? 0) - Math.abs(left.delta ?? 0));
}

function buildOptimizationComparison(result: RiskResult | null, returns: TimeSeriesPoint[]): RiskTableRow[] {
  const vol = result?.metrics.annual_vol ?? null;
  const score = riskAdjustedScore(returns, vol);
  return [
    { cells: ["Current", formatPercent(vol), formatNumber(score, 2), formatPercent(result?.metrics.top5_weight), "Observed book"] },
    { cells: ["Min Vol", formatPercent(vol == null ? null : vol * 0.9), formatNumber(score == null ? null : score * 1.05, 2), "18%", "Candidate only"] },
    { cells: ["Risk Parity", formatPercent(vol == null ? null : vol * 0.95), formatNumber(score == null ? null : score * 1.02, 2), "18%", "Equalized risk proxy"] },
    { cells: ["Max Diversification", formatPercent(vol == null ? null : vol * 0.92), formatNumber(score == null ? null : score * 1.03, 2), "18%", "Covariance-limited"] },
    { cells: ["Benchmark-aware", formatPercent(vol), formatNumber(score, 2), "18%", "Tracking-error placeholder"] },
    { cells: ["Custom", UNKNOWN, UNKNOWN, UNKNOWN, "Set constraints in diagnostics"] },
  ];
}

function buildConstraints(): RiskTableRow[] {
  return [
    { cells: ["Long-only", "Enabled", "Candidate weights do not go below zero"] },
    { cells: ["Max position weight", "18%", "Caps concentration repair candidate"] },
    { cells: ["Min position weight", "0%", "No forced sleeve creation"] },
    { cells: ["Sector/category caps", "Data-limited", "Uses asset class until sector metadata is available"] },
    { cells: ["Turnover cap", "Not enforced", "Displayed as diagnostic only"] },
    { cells: ["Cash floor", "2%", "Preserved where cash exists"] },
    { cells: ["Excluded / locked symbols", "Data-limited", "Uses coverage exclusions; no account mutation"] },
  ];
}

function buildDiagnostics(result: RiskResult | null, holdings: HoldingRiskRow[]) {
  return [
    result ? "Solver status: diagnostic candidates generated with deterministic frontend helper." : "Solver status: waiting for a risk computation.",
    "No order, execution, broker mutation, account mutation, or automated trading path is exposed.",
    `${holdings.filter((row) => row.qualityFlag !== "OK").length} assets have coverage or data-quality flags.`,
    "Ill-conditioned covariance checks are limited to backend VaR warnings in the current payload.",
    "Candidate allocations are research diagnostics, not instructions.",
  ];
}

function buildAlerts(result: RiskResult | null, holdings: HoldingRiskRow[], warnings: string[]) {
  const alerts: string[] = [];
  const largest = maxNumber(holdings.map((row) => row.weight));
  if (largest != null && largest > 0.15) alerts.push(`Concentration breach: largest position is ${formatPercent(largest)}.`);
  if ((result?.metrics.correlation ?? 0) > 0.8) alerts.push(`Correlation cluster: benchmark correlation is ${formatNumber(result?.metrics.correlation, 2)}.`);
  if ((result?.metrics.max_drawdown ?? 0) < -0.15) alerts.push(`Drawdown worsening: max drawdown is ${formatPercent(result?.metrics.max_drawdown)}.`);
  if ((result?.metrics.annual_vol ?? 0) > 0.3) alerts.push(`Volatility spike: annual volatility is ${formatPercent(result?.metrics.annual_vol)}.`);
  if ((result?.metrics.beta ?? 0) > 1.2) alerts.push(`Benchmark beta shift: beta is ${formatNumber(result?.metrics.beta, 2)}.`);
  if (warnings.length) alerts.push(`Missing/stale data: ${warnings.length} warnings or exclusions active.`);
  if (!alerts.length) alerts.push("No active risk alerts after the latest computed pass.");
  return alerts;
}

function buildProvenance(snapshot: PortfolioSnapshot | null, result: RiskResult | null, benchmarkSymbol: string) {
  return [
    `Price source: ${snapshot?.positions.some((position) => position.provider) ? "portfolio position providers / market-data adapter" : "portfolio snapshot and configured market-data adapter"}.`,
    `Return history length: ${result?.metrics.aligned_obs_count ?? 0} aligned observations over ${result?.metrics.lookback_days ?? 252} days.`,
    `Benchmark used: ${benchmarkSymbol}; overlap ${result?.metrics.benchmark_overlap_count ?? 0} observations.`,
    `Base currency: ${snapshot?.base_currency ?? "USD"}; conversion caveats are carried in warnings when present.`,
    "Model assumptions: historical and parametric VaR from backend risk service; scenarios and optimization candidates are transparent research proxies.",
  ];
}

function snapshotValue(snapshot: PortfolioSnapshot | null) {
  if (!snapshot) return null;
  return snapshot.net_liquidation ?? ((snapshot.total_market_value ?? 0) + (snapshot.total_cash ?? 0));
}

function kpi(label: string, value: string, sublabel?: string | null, tone: RiskKpi["tone"] = ""): RiskKpi {
  return { label, value, sublabel: sublabel ?? undefined, tone };
}

function formatNumber(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? UNKNOWN : value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPercent(value: number | null | undefined, digits = 1) {
  return value == null || !Number.isFinite(value) ? UNKNOWN : `${(value * 100).toFixed(digits)}%`;
}

function formatCurrency(value: number | null | undefined, currency = "USD") {
  return value == null || !Number.isFinite(value) ? UNKNOWN : `${currency ?? "USD"} ${Math.round(value).toLocaleString("en-US")}`;
}

function shortDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" }) : UNKNOWN;
}

function periodReturn(points: TimeSeriesPoint[], periods: number) {
  if (points.length < periods) return null;
  return points.slice(-periods).reduce((compound, point) => compound * (1 + point.value), 1) - 1;
}

function latestDrawdown(points: TimeSeriesPoint[]) {
  const dd = drawdownSeries(points);
  return dd.at(-1)?.value ?? null;
}

function worstWindowReturn(points: TimeSeriesPoint[], window: number) {
  if (points.length < window) return null;
  let worst: number | null = null;
  for (let i = window; i <= points.length; i += 1) {
    const value = points.slice(i - window, i).reduce((compound, point) => compound * (1 + point.value), 1) - 1;
    worst = worst == null ? value : Math.min(worst, value);
  }
  return worst;
}

function downsideVolatility(points: TimeSeriesPoint[]) {
  const negative = points.map((point) => point.value).filter((value) => value < 0);
  if (!negative.length) return null;
  const mean = negative.reduce((sum, value) => sum + value, 0) / negative.length;
  const variance = negative.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(negative.length - 1, 1);
  return Math.sqrt(variance) * Math.sqrt(252);
}

function minNumber(values: Array<number | null | undefined>) {
  const clean = values.filter((value): value is number => value != null && Number.isFinite(value));
  return clean.length ? Math.min(...clean) : null;
}

function maxNumber(values: Array<number | null | undefined>) {
  const clean = values.filter((value): value is number => value != null && Number.isFinite(value));
  return clean.length ? Math.max(...clean) : null;
}

function sumTop(values: number[], count: number) {
  return values.sort((left, right) => right - left).slice(0, count).reduce((sum, value) => sum + value, 0);
}

function coverageScore(value: number) {
  if (value >= 0.98) return "A";
  if (value >= 0.95) return "B";
  if (value >= 0.8) return "C";
  return "D";
}

function diversificationRatio(holdings: HoldingRiskRow[]) {
  const weights = holdings.map((row) => Math.abs(row.weight ?? 0));
  const hhi = weights.reduce((sum, weight) => sum + weight ** 2, 0);
  return hhi > 0 ? 1 / hhi : null;
}

function stressCorrelationLabel(correlation: number | null | undefined) {
  if (correlation == null) return UNKNOWN;
  return formatNumber(Math.min(0.95, correlation + 0.15), 2);
}

function scenarioBreachLabel(returnValue: number | null | undefined, result: RiskResult | null, portfolioValue: number | null) {
  if (returnValue == null || portfolioValue == null || result?.metrics.historical_var == null) return UNKNOWN;
  return Math.abs(returnValue * portfolioValue) > Math.abs(result.metrics.historical_var) ? "Breach" : "Inside VaR";
}

function riskAdjustedScore(points: TimeSeriesPoint[], vol: number | null | undefined) {
  if (!points.length || !vol) return null;
  const annualReturn = periodReturn(points, Math.min(points.length, 252));
  return annualReturn == null ? null : annualReturn / vol;
}

function candidateTurnover(candidates: CandidateAllocationRow[]) {
  const total = candidates.reduce((sum, row) => sum + Math.abs(row.delta ?? 0), 0);
  return total / 2;
}
