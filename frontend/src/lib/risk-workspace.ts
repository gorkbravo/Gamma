import type { PortfolioSnapshot, Position, RiskContribution, RiskCorrelationMatrix, RiskDependencyNetwork, RiskFrontierPoint, RiskResult, TimeSeriesPoint } from "./api/types";

export type RiskMode = "overview" | "exposures" | "drawdowns" | "correlation" | "scenarios" | "optimization";
export type ReturnFrequency = "daily" | "weekly" | "monthly";
export type RiskSourceScope = "portfolio" | "research" | "research_book";

export interface RiskContextState {
  sourceScope: RiskSourceScope;
  sourceLabel: string;
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
  correlationMatrix: RiskCorrelationMatrixView;
  dependencyNetwork: RiskDependencyNetwork | null;
  dependencyClusterRows: RiskTableRow[];
  dependencyNeighborRows: RiskTableRow[];
  diversificationWarnings: RiskTableRow[];
  benchmarkSensitivity: RiskTableRow[];
  scenarios: ScenarioResult[];
  scenarioImpacts: ScenarioImpactRow[];
  scenarioAssumptions: string[];
  frontierPoints: RiskFrontierPoint[];
  frontierMessage: string | null;
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

export interface RiskCorrelationMatrixView {
  assets: Array<{ key: string; label: string }>;
  cells: Array<{ row: string; column: string; correlation: number | null }>;
}

const UNKNOWN = "N/A";

export function buildRiskWorkspaceModel(
  snapshot: PortfolioSnapshot | null,
  result: RiskResult | null,
  options: { sourceScope: RiskSourceScope; sourceLabel?: string | null; benchmarkSymbol: string; returnFrequency: ReturnFrequency }
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
  const frontierPoints = result?.frontier_points ?? [];
  const frontierMessage = buildFrontierMessage(result, frontierPoints);
  const candidates = buildCandidateAllocations(holdings, frontierPoints);
  const correlationMatrix = buildCorrelationMatrix(result?.correlation_matrix);
  const dependencyNetwork = result?.dependency_network ?? null;
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
  const minVolPoint = frontierPoints.find((point) => point.label === "Min Vol");
  const maxSharpePoint = frontierPoints.find((point) => point.label === "Max Sharpe");
  const optimizedVol = minVolPoint?.annual_vol ?? (result?.metrics.annual_vol == null ? null : result.metrics.annual_vol * 0.9);

  return {
    context: {
      sourceScope: options.sourceScope,
      sourceLabel: result?.source_label ?? options.sourceLabel ?? sourceScopeLabel(options.sourceScope),
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
      kpi("Average pairwise corr", formatNumber(averagePairwiseCorrelation(correlationMatrix), 2)),
      kpi("Highest pair corr", formatNumber(highestPairwiseCorrelation(correlationMatrix)?.correlation, 2)),
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
      kpi("Optimized Sharpe / score", formatNumber(maxSharpePoint?.sharpe ?? riskAdjustedScore(returns, optimizedVol), 2)),
      kpi("Turnover required", formatPercent(candidateTurnover(candidates))),
      kpi("Max weight after", formatPercent(maxNumber(candidates.map((row) => row.proposedWeight)))),
      kpi("Frontier assets", frontierPoints.length ? String(frontierPoints[0]?.weights.length ?? 0) : UNKNOWN, "covered risky sleeve"),
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
    correlatedPairs: buildCorrelatedPairs(correlationMatrix),
    correlationMatrix,
    dependencyNetwork,
    dependencyClusterRows: buildDependencyClusterRows(dependencyNetwork),
    dependencyNeighborRows: buildDependencyNeighborRows(dependencyNetwork),
    diversificationWarnings: buildDiversificationWarnings(holdings, exposureBreakdown, result),
    benchmarkSensitivity: buildBenchmarkSensitivity(holdings, result),
    scenarios,
    scenarioImpacts: scenarios[0] ? buildScenarioImpacts(holdings, scenarios[0], portfolioValue) : [],
    scenarioAssumptions: buildScenarioAssumptions(result, coverage),
    frontierPoints,
    frontierMessage,
    candidates,
    optimizationComparison: buildOptimizationComparison(result, returns, frontierPoints),
    constraints: buildConstraints(),
    diagnostics: buildDiagnostics(result, holdings),
    alerts: buildAlerts(result, holdings, coverageWarnings),
    provenance: buildProvenance(snapshot, result, options.benchmarkSymbol, options.sourceScope),
  };
}

function sourceScopeLabel(sourceScope: RiskSourceScope) {
  if (sourceScope === "research_book") return "Strategy Lab research book";
  if (sourceScope === "research") return "Research scope";
  return "Live account portfolio";
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

function buildCorrelationMatrix(matrix: RiskCorrelationMatrix | null | undefined): RiskCorrelationMatrixView {
  const assets = (matrix?.assets ?? [])
    .map((asset) => ({
      key: asset.instrument_id ?? asset.symbol,
      label: asset.display_symbol ?? asset.symbol,
    }))
    .filter((asset) => asset.key && asset.label)
    .slice(0, 12);
  const allowed = new Set(assets.map((asset) => asset.key));
  const cells = (matrix?.cells ?? [])
    .filter((cell) => allowed.has(cell.row) && allowed.has(cell.column))
    .map((cell) => ({
      row: cell.row,
      column: cell.column,
      correlation: cell.correlation,
    }));
  return { assets, cells };
}

function averagePairwiseCorrelation(matrix: RiskCorrelationMatrixView) {
  const values = pairwiseCorrelations(matrix).map((item) => item.correlation);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function highestPairwiseCorrelation(matrix: RiskCorrelationMatrixView) {
  return pairwiseCorrelations(matrix).sort((left, right) => right.correlation - left.correlation)[0] ?? null;
}

function pairwiseCorrelations(matrix: RiskCorrelationMatrixView) {
  const order = new Map(matrix.assets.map((asset, index) => [asset.key, index]));
  return matrix.cells
    .filter((cell): cell is { row: string; column: string; correlation: number } => {
      const rowIndex = order.get(cell.row);
      const columnIndex = order.get(cell.column);
      return rowIndex != null && columnIndex != null && rowIndex < columnIndex && cell.correlation != null && Number.isFinite(cell.correlation);
    });
}

function buildCorrelatedPairs(matrix: RiskCorrelationMatrixView): RiskTableRow[] {
  const labelByKey = new Map(matrix.assets.map((asset) => [asset.key, asset.label]));
  const pairs = pairwiseCorrelations(matrix)
    .sort((left, right) => Math.abs(right.correlation) - Math.abs(left.correlation))
    .slice(0, 8)
    .map((cell) => ({
      cells: [
        `${labelByKey.get(cell.row) ?? cell.row} / ${labelByKey.get(cell.column) ?? cell.column}`,
        formatNumber(cell.correlation, 2),
        Math.abs(cell.correlation) >= 0.75 ? "Cluster watch" : "Diversifying",
      ],
      tone: Math.abs(cell.correlation) >= 0.75 ? "warning" as const : "" as const,
    }));
  return pairs.length ? pairs : buildUnavailableRows(["Run a risk pass with at least two covered assets to populate pairwise correlations."]);
}

function buildDependencyClusterRows(network: RiskDependencyNetwork | null): RiskTableRow[] {
  if (!network?.clusters?.length) {
    return buildUnavailableRows(["Run risk with usable equity histories to populate dependency clusters."]);
  }
  return network.clusters.slice(0, 12).map((cluster) => ({
    cells: [
      cluster.label,
      `${cluster.portfolio_node_count}/${cluster.node_count}`,
      formatPercent(cluster.portfolio_weight),
      formatPercent(cluster.average_annual_vol),
      formatPercent(cluster.density),
      cluster.central_symbols.slice(0, 4).join(", ") || UNKNOWN,
    ],
    tone: cluster.portfolio_weight >= 0.35 ? "warning" : "",
  }));
}

function buildDependencyNeighborRows(network: RiskDependencyNetwork | null): RiskTableRow[] {
  if (!network?.nodes?.length || !network.edges.length) {
    return buildUnavailableRows(["No sparse dependency links are available yet."]);
  }
  const nodes = new Map(network.nodes.map((node) => [node.symbol, node]));
  const rows = network.edges
    .map<RiskTableRow & { strength: number } | null>((edge) => {
      const source = nodes.get(edge.source);
      const target = nodes.get(edge.target);
      const portfolioNode = source?.is_portfolio ? source : target?.is_portfolio ? target : null;
      const otherNode = portfolioNode?.symbol === source?.symbol ? target : source;
      if (!portfolioNode || !otherNode || otherNode.is_portfolio) {
        return null;
      }
      return {
        cells: [
          portfolioNode.symbol,
          otherNode.symbol,
          formatNumber(edge.partial_correlation, 2),
          `Cluster ${otherNode.cluster_id + 1}`,
          formatNumber(otherNode.centrality, 2),
        ],
        tone: edge.strength >= 0.25 ? "warning" as const : "" as const,
        strength: edge.strength,
      };
    })
    .filter((row): row is RiskTableRow & { strength: number } => row !== null)
    .sort((left, right) => right.strength - left.strength)
    .slice(0, 12)
    .map((row) => ({ cells: row.cells, tone: row.tone }));
  return rows.length ? rows : buildUnavailableRows(["No non-held neighbors link directly to current portfolio names."]);
}

function buildDiversificationWarnings(holdings: HoldingRiskRow[], breakdown: ExposureBreakdownRow[], result: RiskResult | null): RiskTableRow[] {
  const networkRows = buildNetworkConcentrationWarnings(result?.dependency_network ?? null);
  const rows = breakdown
    .filter((row) => Math.abs(row.weight) > 0.25)
    .map((row) => ({
      cells: [row.category, holdings.filter((holding) => holding.assetClass === row.category).map((holding) => holding.symbol).slice(0, 4).join(", "), formatPercent(row.weight), UNKNOWN, formatPercent(row.volatilityContribution)],
      tone: "warning" as const,
    }));
  if ((result?.metrics.correlation ?? 0) > 0.8) rows.unshift({ cells: ["Benchmark cluster", "Portfolio aggregate", UNKNOWN, formatNumber(result?.metrics.correlation, 2), "High benchmark sensitivity"], tone: "warning" });
  return [...networkRows, ...rows];
}

function buildNetworkConcentrationWarnings(network: RiskDependencyNetwork | null): RiskTableRow[] {
  if (!network?.clusters?.length) {
    return [];
  }
  return network.clusters
    .filter((cluster) => cluster.portfolio_weight >= 0.25 || cluster.portfolio_node_count >= 3)
    .slice(0, 4)
    .map((cluster) => ({
      cells: [
        cluster.label,
        cluster.top_symbols.slice(0, 5).join(", "),
        formatPercent(cluster.portfolio_weight),
        formatPercent(cluster.density),
        `${cluster.portfolio_node_count} held names`,
      ],
      tone: cluster.portfolio_weight >= 0.35 ? "warning" as const : "" as const,
    }));
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

function buildCandidateAllocations(holdings: HoldingRiskRow[], frontierPoints: RiskFrontierPoint[] = []): CandidateAllocationRow[] {
  const minVolWeights = frontierPoints.find((point) => point.label === "Min Vol")?.weights ?? [];
  const frontierWeightByKey = new Map<string, number>();
  for (const weight of minVolWeights) {
    frontierWeightByKey.set(weight.symbol, weight.weight);
    if (weight.display_symbol) frontierWeightByKey.set(weight.display_symbol, weight.weight);
    if (weight.instrument_id) frontierWeightByKey.set(weight.instrument_id, weight.weight);
  }
  if (frontierWeightByKey.size) {
    const riskyScale = holdings
      .filter((row) => row.assetClass !== "Cash" && (row.weight ?? 0) > 0)
      .reduce((sum, row) => sum + (row.weight ?? 0), 0) || 1;
    return holdings.map((row) => {
      const frontierWeight = frontierWeightByKey.get(row.symbol);
      const proposed = frontierWeight == null
        ? row.assetClass === "Cash" ? row.weight ?? 0 : 0
        : frontierWeight * riskyScale;
      return {
        symbol: row.symbol,
        currentWeight: row.weight,
        proposedWeight: proposed,
        delta: row.weight == null ? null : proposed - row.weight,
        currentRiskContribution: row.riskContribution,
        proposedRiskContribution: row.riskContribution == null ? null : row.riskContribution * (proposed / Math.max(row.weight ?? proposed, 0.0001)),
        constraintFlag: row.qualityFlag !== "OK" ? row.qualityFlag : "Min-vol candidate",
      };
    }).sort((left, right) => Math.abs(right.delta ?? 0) - Math.abs(left.delta ?? 0));
  }

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

function buildOptimizationComparison(result: RiskResult | null, returns: TimeSeriesPoint[], frontierPoints: RiskFrontierPoint[] = []): RiskTableRow[] {
  if (frontierPoints.length) {
    const preferred = ["Current", "Min Vol", "Max Sharpe", "Equal Weight", "Risk Parity"];
    const rows = preferred
      .map((label) => frontierPoints.find((point) => point.label === label))
      .filter((point): point is RiskFrontierPoint => point != null)
      .map((point) => ({
        cells: [point.label, formatPercent(point.annual_vol), formatNumber(point.sharpe, 2), formatPercent(maxNumber(point.weights.map((weight) => weight.weight))), point.kind === "current" ? "Observed risky sleeve" : "Backend candidate"],
      }));
    if (rows.length) return rows;
  }
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
  const frontierMessage = buildFrontierMessage(result, result?.frontier_points ?? []);
  return [
    result?.frontier_points?.length
      ? `Solver status: backend efficient frontier generated ${result.frontier_points.length} risk-return points.`
      : result
        ? `Solver status: ${frontierMessage ?? "frontier unavailable; candidate rows fall back to deterministic frontend diagnostics."}`
        : "Solver status: waiting for a risk computation.",
    "No order, execution, broker mutation, account mutation, or automated trading path is exposed.",
    `${holdings.filter((row) => row.qualityFlag !== "OK").length} assets have coverage or data-quality flags.`,
    "Ill-conditioned covariance checks are limited to backend VaR warnings in the current payload.",
    "Candidate allocations are research diagnostics, not instructions.",
  ];
}

function buildFrontierMessage(result: RiskResult | null, frontierPoints: RiskFrontierPoint[]) {
  if (!result || frontierPoints.length) return null;
  const responseHasFrontierField = Object.prototype.hasOwnProperty.call(result, "frontier_points");
  if (!responseHasFrontierField) {
    return "Risk API response did not include frontier data; restart the backend and run Compute Core again.";
  }
  const frontierWarning = result.warnings.find((warning) => warning.includes("Efficient frontier unavailable"));
  if (frontierWarning) return frontierWarning;
  if ((result.contributions?.length ?? 0) >= 2) {
    return "Risk has multiple modeled contributors, but the backend returned no frontier points; recompute risk and check provider warnings.";
  }
  return "Efficient frontier unavailable until at least two covered positions have usable return history.";
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

function buildProvenance(
  snapshot: PortfolioSnapshot | null,
  result: RiskResult | null,
  benchmarkSymbol: string,
  sourceScope: RiskSourceScope
) {
  const priceSource =
    sourceScope === "research_book"
      ? "Strategy Lab validated aggregate return stream"
      : snapshot?.positions.some((position) => position.provider)
        ? "portfolio position providers / market-data adapter"
        : "portfolio snapshot and configured market-data adapter";
  return [
    `Risk source: ${result?.source_label ?? sourceScopeLabel(sourceScope)}.`,
    `Price source: ${priceSource}.`,
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
