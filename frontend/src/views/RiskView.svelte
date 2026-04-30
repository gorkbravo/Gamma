<script lang="ts">
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import DistributionChart, { type DistributionMarker } from "../components/DistributionChart.svelte";
  import FanChart from "../components/FanChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import {
    buildRiskWorkspaceModel,
    type CandidateAllocationRow,
    type DrawdownEpisode,
    type ExposureBreakdownRow,
    type HoldingRiskRow,
    type ReturnFrequency,
    type RiskKpi,
    type RiskMode,
    type RiskContributionRow,
    type RiskTableRow,
    type ScenarioImpactRow,
    type ScenarioResult,
  } from "../lib/risk-workspace";
  import type { IndexedValuePoint, PortfolioSnapshot, RiskFrontierPoint, RiskResult, TimeSeriesPoint, WorkspaceMode } from "../lib/api/types";
  import type { RiskComputeOptions } from "../lib/stores/app";

  export let mode: WorkspaceMode | null = "portfolio";
  export let activeMode: RiskMode = "overview";
  export let snapshot: PortfolioSnapshot | null = null;
  export let researchSnapshot: PortfolioSnapshot | null = null;
  export let result: RiskResult | null = null;
  export let loading = false;
  export let onCompute: (options: RiskComputeOptions) => Promise<void> | void;

  type ComputeMethod = "core" | "monteCarlo";
  type FrontierPlotPoint = {
    label: string;
    kind: string;
    annualReturn: number;
    annualVol: number;
    sharpe: number | null;
    x: number;
    y: number;
  };

  type FrontierPlotModel = {
    points: FrontierPlotPoint[];
    frontierPath: string;
    xMin: number;
    xMax: number;
    yMin: number;
    yMax: number;
  };

  const modes: Array<{ id: RiskMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "exposures", label: "Exposures" },
    { id: "drawdowns", label: "Drawdowns" },
    { id: "correlation", label: "Correlation" },
    { id: "scenarios", label: "Scenarios" },
    { id: "optimization", label: "Optimization" },
  ];

  let benchmarkSymbol = "SPY";
  let confidence = 0.95;
  let lookbackDays = 252;
  let horizonDays = 1;
  let mcHorizonDays = 10;
  let mcSimulationModel = "Gaussian";
  let mcNumSimulations = 2000;
  let betaWindow = 126;
  let returnFrequency: ReturnFrequency = "daily";
  let activeComputeMethod: ComputeMethod | null = null;

  let activeSnapshot: PortfolioSnapshot | null = snapshot;
  let workspace = buildRiskWorkspaceModel(null, null, {
    sourceScope: "portfolio",
    benchmarkSymbol,
    returnFrequency,
  });
  let cumulativeChart: ChartSeries[] = [];
  let rollingVolChart: ChartSeries[] = [];
  let rollingBetaChart: ChartSeries[] = [];
  let drawdownChart: ChartSeries[] = [];
  let scenarioBars: RankBarItem[] = [];
  let riskContributionBars: RankBarItem[] = [];
  let weightBars: RankBarItem[] = [];
  let exposureBars: RankBarItem[] = [];
  let optimizationBars: RankBarItem[] = [];
  let realizedReturns: number[] = [];
  let realizedMarkers: DistributionMarker[] = [];
  let monteCarloMarkers: DistributionMarker[] = [];
  let fanHistory: IndexedValuePoint[] = [];
  let frontierPlot: FrontierPlotModel = buildFrontierPlot([]);

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value) ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  const currency = (value: number | null | undefined, baseCurrency = workspace.context.baseCurrency) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${baseCurrency} ${Math.round(value).toLocaleString("en-US")}`;

  const toneClass = (tone: string | undefined | null) => tone ?? "";
  const cellValue = (value: string | number | null) => value == null ? "N/A" : String(value);

  $: activeSnapshot = mode === "research" ? researchSnapshot : snapshot;
  $: workspace = buildRiskWorkspaceModel(activeSnapshot, result, {
    sourceScope: mode === "research" ? "research" : "portfolio",
    benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
    returnFrequency,
  });

  async function submit(method: ComputeMethod) {
    activeComputeMethod = method;
    try {
      await onCompute({
        snapshot: activeSnapshot,
        alpha: confidence,
        lookbackDays,
        horizonDays,
        mcHorizonDays,
        mcSimulationModel,
        mcNumSimulations,
        betaWindow,
        benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
        includeMonteCarlo: method === "monteCarlo"
      });
    } finally {
      activeComputeMethod = null;
    }
  }

  function cumulativeSeries(points: TimeSeriesPoint[], id: string, label: string, color: string, lineStyle?: "solid" | "dashed"): ChartSeries | null {
    if (!points.length) return null;
    let cumulative = 1;
    return {
      id,
      label,
      color,
      type: "line",
      lineStyle,
      data: points.map((point) => {
        cumulative *= 1 + point.value;
        return { time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: cumulative };
      }),
    };
  }

  function drawdownSeries(points: TimeSeriesPoint[]): ChartSeries[] {
    if (!points.length) return [];
    let cumulative = 1;
    let peak = 1;
    return [{
      id: "drawdown",
      label: "Drawdown",
      color: "var(--chart-negative)",
      type: "area",
      invertFilledArea: true,
      data: points.map((point) => {
        cumulative *= 1 + point.value;
        peak = Math.max(peak, cumulative);
        return { time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: cumulative / peak - 1 };
      })
    }];
  }

  function rollingStd(points: TimeSeriesPoint[], window = 21) {
    return points
      .map((point, index) => {
        if (index + 1 < window) return null;
        const slice = points.slice(index + 1 - window, index + 1).map((item) => item.value);
        const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
        const variance = slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(slice.length - 1, 1);
        return { time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: Math.sqrt(variance) * Math.sqrt(252) };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function rollingBeta(points: TimeSeriesPoint[], benchmark: TimeSeriesPoint[], window: number) {
    const byDate = new Map(benchmark.map((point) => [point.timestamp, point.value]));
    const aligned = points
      .map((point) => ({ ts: point.timestamp, perf: point.value, benchmark: byDate.get(point.timestamp) }))
      .filter((point): point is { ts: string; perf: number; benchmark: number } => point.benchmark != null);
    return aligned
      .map((point, index) => {
        if (index + 1 < window) return null;
        const slice = aligned.slice(index + 1 - window, index + 1);
        const pm = slice.reduce((sum, item) => sum + item.perf, 0) / slice.length;
        const bm = slice.reduce((sum, item) => sum + item.benchmark, 0) / slice.length;
        const cov = slice.reduce((sum, item) => sum + (item.perf - pm) * (item.benchmark - bm), 0) / Math.max(slice.length - 1, 1);
        const variance = slice.reduce((sum, item) => sum + (item.benchmark - bm) ** 2, 0) / Math.max(slice.length - 1, 1);
        return variance > 0 ? { time: Math.floor(new Date(point.ts).getTime() / 1000), value: cov / variance } : null;
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function riskBaseValue() {
    return result?.metrics.covered_portfolio_value || result?.metrics.portfolio_value || null;
  }

  function buildFrontierPlot(points: RiskFrontierPoint[]): FrontierPlotModel {
    const clean = points
      .filter((point) => Number.isFinite(point.annual_vol) && Number.isFinite(point.annual_return))
      .map((point) => ({
        label: point.label,
        kind: point.kind,
        annualReturn: point.annual_return,
        annualVol: point.annual_vol,
        sharpe: point.sharpe,
        x: 0,
        y: 0,
      }));
    if (!clean.length) return { points: [], frontierPath: "", xMin: 0, xMax: 0, yMin: 0, yMax: 0 };
    const xValues = clean.map((point) => point.annualVol);
    const yValues = clean.map((point) => point.annualReturn);
    const xMinRaw = Math.min(...xValues);
    const xMaxRaw = Math.max(...xValues);
    const yMinRaw = Math.min(...yValues);
    const yMaxRaw = Math.max(...yValues);
    const xPad = Math.max((xMaxRaw - xMinRaw) * 0.08, 0.01);
    const yPad = Math.max((yMaxRaw - yMinRaw) * 0.12, 0.02);
    const xMin = Math.max(0, xMinRaw - xPad);
    const xMax = xMaxRaw + xPad;
    const yMin = yMinRaw - yPad;
    const yMax = yMaxRaw + yPad;
    const width = Math.max(xMax - xMin, 1e-9);
    const height = Math.max(yMax - yMin, 1e-9);
    const plotted = clean.map((point) => ({
      ...point,
      x: ((point.annualVol - xMin) / width) * 100,
      y: 100 - ((point.annualReturn - yMin) / height) * 100,
    }));
    const frontierPath = plotted
      .filter((point) => point.kind === "frontier")
      .sort((left, right) => left.annualVol - right.annualVol)
      .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
      .join(" ");
    return { points: plotted, frontierPath, xMin, xMax, yMin, yMax };
  }

  $: cumulativeChart = (() => {
    const rows: ChartSeries[] = [];
    const portfolio = cumulativeSeries(result?.portfolio_return_points ?? [], "portfolio", "Portfolio", "var(--chart-primary)");
    const benchmark = cumulativeSeries(result?.benchmark_return_points ?? [], "benchmark", benchmarkSymbol.trim().toUpperCase() || "SPY", "var(--chart-secondary)", "dashed");
    if (portfolio) rows.push(portfolio);
    if (benchmark) rows.push(benchmark);
    return rows;
  })();

  $: rollingVolChart = (() => {
    const data = rollingStd(result?.portfolio_return_points ?? []);
    return data.length ? [{ id: "rolling-vol", label: "Rolling Vol", color: "var(--chart-primary)", type: "line", data }] : [];
  })();

  $: rollingBetaChart = (() => {
    const data = rollingBeta(result?.portfolio_return_points ?? [], result?.benchmark_return_points ?? [], betaWindow);
    return data.length ? [{ id: "rolling-beta", label: "Rolling Beta", color: "var(--chart-secondary)", type: "line", data }] : [];
  })();

  $: drawdownChart = drawdownSeries(result?.portfolio_return_points ?? []);
  $: realizedReturns = result?.portfolio_return_points?.map((point) => point.value) ?? [];

  $: realizedMarkers = [
    { label: "Hist VaR", value: riskBaseValue() ? -(result?.metrics.historical_var ?? 0) / (riskBaseValue() ?? 1) : null, color: "var(--chart-negative)" },
    { label: "Hist ES", value: riskBaseValue() ? -(result?.metrics.historical_cvar ?? 0) / (riskBaseValue() ?? 1) : null, color: "var(--chart-secondary)" },
  ];

  $: monteCarloMarkers = [
    { label: "MC VaR", value: riskBaseValue() ? -(result?.metrics.monte_carlo_var ?? 0) / (riskBaseValue() ?? 1) : null, color: "var(--chart-primary)" },
    { label: "MC ES", value: riskBaseValue() ? -(result?.metrics.monte_carlo_cvar ?? 0) / (riskBaseValue() ?? 1) : null, color: "var(--chart-negative)" },
  ];

  $: fanHistory = (() => {
    const perf = result?.portfolio_return_points ?? [];
    if (perf.length < 2) return [];
    const recent = perf.slice(-40);
    let cumulative = 1;
    const points = recent.map((point, index) => {
      cumulative *= 1 + point.value;
      return { index: index - recent.length + 1, value: cumulative };
    });
    const terminal = points.at(-1)?.value ?? 1;
    return points.map((point) => ({ index: point.index, value: terminal !== 0 ? point.value / terminal : point.value }));
  })();

  $: frontierPlot = buildFrontierPlot(workspace.frontierPoints);

  $: riskContributionBars = workspace.riskContributors.slice(0, 8).map((item) => ({
    label: item.symbol,
    value: item.contribution ?? 0,
    tone: (item.contribution ?? 0) >= 0 ? "positive" : "negative",
    meta: `${pct(item.weight)} wt | ${currency(item.componentVar)} component VaR`,
  }));

  $: weightBars = workspace.holdings.slice(0, 10).map((item) => ({
    label: item.symbol,
    value: item.weight ?? 0,
    tone: (item.weight ?? 0) >= 0 ? "positive" : "negative",
    meta: `${currency(item.marketValue)} | ${item.qualityFlag}`,
  }));

  $: exposureBars = workspace.exposureBreakdown.map((item) => ({
    label: item.category,
    value: item.weight,
    tone: item.weight >= 0 ? "positive" : "negative",
    meta: `${pct(item.volatilityContribution)} risk contribution`,
  }));

  $: scenarioBars = workspace.scenarioImpacts.slice(0, 10).map((item) => ({
    label: item.symbol,
    value: item.pnlImpact ?? 0,
    tone: (item.pnlImpact ?? 0) >= 0 ? "positive" : "negative",
    meta: `${pct(item.estimatedReturn)} shock | ${pct(item.weight)} weight`,
  }));

  $: optimizationBars = workspace.candidates.slice(0, 10).map((item) => ({
    label: item.symbol,
    value: item.delta ?? 0,
    tone: (item.delta ?? 0) >= 0 ? "positive" : "negative",
    meta: `${pct(item.currentWeight)} to ${pct(item.proposedWeight)} | ${item.constraintFlag}`,
  }));
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div>
        <p class="eyebrow">Risk</p>
        <h2>Risk Workspace</h2>
      </div>
      <div class="header-actions">
        <button class="action-btn" on:click={() => submit("core")} disabled={loading || !activeSnapshot}>
          {loading && activeComputeMethod === "core" ? "Computing" : "Compute Core"}
        </button>
        <button class="action-btn" on:click={() => submit("monteCarlo")} disabled={loading || !activeSnapshot}>
          {loading && activeComputeMethod === "monteCarlo" ? "Running" : "Run MC"}
        </button>
      </div>
    </div>

    <div class="mode-bar" role="tablist" aria-label="Risk modes">
      {#each modes as riskMode}
        <button
          type="button"
          class:selected={activeMode === riskMode.id}
          role="tab"
          aria-selected={activeMode === riskMode.id}
          on:click={() => (activeMode = riskMode.id)}
        >
          {riskMode.label}
        </button>
      {/each}
    </div>

    <div class="context-bar">
      <div class="context-field"><span>Scope</span><strong>{workspace.context.sourceScope}</strong></div>
      <label><span>Benchmark</span><input bind:value={benchmarkSymbol} /></label>
      <div class="context-field"><span>Base</span><strong>{workspace.context.baseCurrency}</strong></div>
      <label><span>Lookback</span>
        <select bind:value={lookbackDays}>
          <option value={126}>126D</option><option value={252}>252D</option><option value={504}>504D</option>
        </select>
      </label>
      <label><span>Frequency</span>
        <select bind:value={returnFrequency}>
          <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
        </select>
      </label>
      <div class="context-field"><span>Coverage</span><strong class:warning={(result?.metrics.risk_coverage_ratio ?? 1) < 0.95}>{workspace.context.coverageLabel}</strong></div>
    </div>

    <div class="settings-row">
      <label><span>Confidence</span><select bind:value={confidence}><option value={0.9}>90%</option><option value={0.95}>95%</option><option value={0.99}>99%</option></select></label>
      <label><span>Horizon</span><select bind:value={horizonDays}><option value={1}>1D</option><option value={10}>10D</option><option value={21}>21D</option></select></label>
      <label><span>Beta window</span><select bind:value={betaWindow}><option value={63}>63D</option><option value={126}>126D</option><option value={252}>252D</option></select></label>
      <label><span>MC horizon</span><select bind:value={mcHorizonDays}><option value={5}>5D</option><option value={10}>10D</option><option value={21}>21D</option><option value={63}>63D</option></select></label>
      <label><span>MC model</span><select bind:value={mcSimulationModel}><option value="Gaussian">Gaussian</option><option value="Bootstrap">Bootstrap</option></select></label>
      <label><span>Sims</span><select bind:value={mcNumSimulations}><option value={1000}>1,000</option><option value={2000}>2,000</option><option value={5000}>5,000</option></select></label>
    </div>
  </article>

  {#if activeMode === "overview"}
    <div class="mode-shell">
      {@render KpiStrip(workspace.overviewKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
        <article class="panel chart-panel">{@render PanelTitle("Cumulative Return vs Benchmark")}<TimeSeriesChart series={cumulativeChart} height={280} emptyMessage="Run a risk pass to populate portfolio and benchmark return history" /></article>
        <div class="two-col">
          <article class="panel chart-panel">{@render PanelTitle("Rolling Volatility")}<TimeSeriesChart series={rollingVolChart} height={220} emptyMessage="Need at least 21 observations" /></article>
          <article class="panel chart-panel">{@render PanelTitle("Rolling Beta")}<TimeSeriesChart series={rollingBetaChart} height={220} emptyMessage="Need benchmark overlap for selected beta window" /></article>
        </div>
        <article class="panel chart-panel">{@render PanelTitle("Drawdown Strip")}<TimeSeriesChart series={drawdownChart} height={180} emptyMessage="Drawdown history unavailable" /></article>
        {@render RiskContributorsTable(workspace.riskContributors)}
        </div>
        <aside class="support-column">
        {@render RankPanel("Top Risk Contributors", riskContributionBars)}
        {@render SimpleTable("Largest Movers", ["Symbol", "P&L", "Weight", "Flag"], workspace.largestMovers)}
        {@render SimpleTable("Concentration Flags", ["Type", "Name", "Value", "Rule"], workspace.concentrationFlags)}
        {@render ListPanel("What Changed", workspace.whatChanged)}
        </aside>
      </div>
    </div>
  {:else if activeMode === "exposures"}
    <div class="mode-shell">
      {@render KpiStrip(workspace.exposureKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
          {@render RankPanel("Position Weight", weightBars)}
          {@render RankPanel("Sector / Asset-Class Exposure", exposureBars)}
          {@render HoldingsTable(workspace.holdings)}
        </div>
        <aside class="support-column">
          {@render ExposureTable(workspace.exposureBreakdown)}
          {@render SimpleTable("Currency Exposure", ["Currency", "Weight", "Contribution", "Status"], workspace.exposureBreakdown.map((row) => ({ cells: [row.category === "Cash" ? workspace.context.baseCurrency : "Mixed", pct(row.weight), pct(row.volatilityContribution), row.label] })))}
          {@render ListPanel("Data Limits", ["Industry, geography, and factor exposures depend on provider metadata not yet present in the Risk payload.", "Asset-class and currency views use snapshot fields and coverage warnings."])}
        </aside>
      </div>
    </div>
  {:else if activeMode === "drawdowns"}
    <div class="mode-shell">
      {@render KpiStrip(workspace.drawdownKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
        <article class="panel chart-panel">{@render PanelTitle("Portfolio Equity Curve")}<TimeSeriesChart series={cumulativeChart} height={260} emptyMessage="Run a risk pass to populate equity curve" /></article>
        <article class="panel chart-panel">{@render PanelTitle("Underwater Chart vs Benchmark")}<TimeSeriesChart series={drawdownChart} height={240} emptyMessage="Drawdown curve unavailable" /></article>
        <div class="two-col">
          <article class="panel chart-panel">{@render PanelTitle("Rolling Downside Volatility")}<TimeSeriesChart series={rollingVolChart} height={220} emptyMessage="Need enough observations" /></article>
          <article class="panel chart-panel">{@render PanelTitle("Return Distribution")}<DistributionChart values={realizedReturns} markers={realizedMarkers} height={220} emptyMessage="Return distribution unavailable" /></article>
        </div>
        {@render DrawdownTable(workspace.drawdownEpisodes)}
        </div>
        <aside class="support-column">
          {@render SimpleTable("Worst Single-Period Returns", ["Date", "Portfolio", "Benchmark", "Active", "Top losers"], workspace.worstReturns)}
          {@render SimpleTable("Position Drawdown Contribution", ["Symbol", "Return", "Start weight", "Loss contribution"], workspace.positionDrawdownContributions)}
        </aside>
      </div>
    </div>
  {:else if activeMode === "correlation"}
    <div class="mode-shell">
      {@render KpiStrip(workspace.correlationKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
        <article class="panel heatmap-panel">{@render PanelTitle("Correlation Heatmap")}{@render HeatmapPlaceholder(workspace.holdings)}</article>
        <div class="two-col">
          <article class="panel chart-panel">{@render PanelTitle("Rolling Correlation To Benchmark")}<TimeSeriesChart series={rollingBetaChart} height={220} emptyMessage="Correlation series requires benchmark overlap" /></article>
          <article class="panel chart-panel">{@render PanelTitle("Normal vs Stress Correlation")}<BarRankChart items={[{ label: "Normal", value: result?.metrics.correlation ?? 0, tone: "neutral" }, { label: "Stress proxy", value: Math.min(0.95, (result?.metrics.correlation ?? 0) + 0.15), tone: "negative" }]} formatValue={(value) => fmt(value, 2)} /></article>
        </div>
        {@render SimpleTable("Highest Correlated Pairs", ["Status"], workspace.correlatedPairs)}
        </div>
        <aside class="support-column">
          {@render SimpleTable("Diversification Warnings", ["Cluster", "Members", "Weight", "Avg corr", "Risk contribution"], workspace.diversificationWarnings)}
          {@render SimpleTable("Benchmark Sensitivity", ["Symbol", "Beta", "Corr", "R2", "Tracking contribution"], workspace.benchmarkSensitivity)}
        </aside>
      </div>
    </div>
  {:else if activeMode === "scenarios"}
    <div class="mode-shell">
      {@render KpiStrip(workspace.scenarioKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
          {@render RankPanel("Scenario Waterfall", scenarioBars, "currency")}
          {@render ScenarioTable(workspace.scenarios)}
          {@render ScenarioImpactTable(workspace.scenarioImpacts)}
        </div>
        <aside class="support-column">
          {@render RankPanel("Shock Impact by Asset Class", exposureBars.map((item) => ({ ...item, value: item.value * (workspace.scenarios[0]?.portfolioReturn ?? 0) })))}
          {@render ListPanel("Scenario Assumptions", workspace.scenarioAssumptions)}
          {@render ListPanel("Historical Replay Coverage", ["COVID crash, 2022 rates shock, and 2008-style labels are exposed as proxy regimes until historical replay windows are provider-backed.", "Custom shocks remain bounded to read-only factor assumptions."])}
        </aside>
      </div>
    </div>
  {:else}
    <div class="mode-shell">
      {@render KpiStrip(workspace.optimizationKpis)}
      <div class="workspace-grid">
        <div class="primary-column">
          <article class="panel chart-panel">{@render PanelTitle("Efficient Frontier")}{@render FrontierChart(frontierPlot)}</article>
          {@render RankPanel("Weight Changes Before / After", optimizationBars)}
          {@render CandidateTable(workspace.candidates)}
        </div>
        <aside class="support-column">
          {@render SimpleTable("Optimization Comparison", ["Candidate", "Vol", "Score", "Max wt", "Status"], workspace.optimizationComparison)}
          {@render SimpleTable("Constraint Panel", ["Constraint", "Setting", "Note"], workspace.constraints)}
          {@render ListPanel("Diagnostics", workspace.diagnostics)}
        </aside>
      </div>
    </div>
  {/if}

  <div class="shared-panels">
    {@render ListPanel("Risk Alerts", workspace.alerts)}
    {@render ListPanel("Provenance / Coverage", [...workspace.provenance, ...workspace.coverageWarnings.slice(0, 6)])}
  </div>

  {#if activeMode === "overview" && result?.monte_carlo?.fan_percentiles}
    <article class="panel mc-panel">
      {@render PanelTitle("Monte Carlo Scenario Envelope")}
      <div class="two-col">
        <FanChart series={result.monte_carlo.fan_percentiles} history={fanHistory} samplePaths={result.monte_carlo.sample_paths} height={260} emptyMessage="Monte Carlo fan chart unavailable" />
        <DistributionChart values={result.monte_carlo.terminal_returns} markers={monteCarloMarkers} height={260} emptyMessage="Monte Carlo distribution unavailable" />
      </div>
    </article>
  {/if}
</section>

{#snippet KpiStrip(kpis: RiskKpi[])}
  <div class="kpi-grid">
    {#each kpis as kpi}
      <article class="metric">
        <span>{kpi.label}</span>
        <strong class={toneClass(kpi.tone)}>{kpi.value}</strong>
        {#if kpi.sublabel}<small>{kpi.sublabel}</small>{/if}
      </article>
    {/each}
  </div>
{/snippet}

{#snippet PanelTitle(title: string)}
  <header class="panel-title"><span>{title}</span></header>
{/snippet}

{#snippet RankPanel(title: string, items: RankBarItem[], format: "percent" | "currency" = "percent")}
  <article class="panel">
    {@render PanelTitle(title)}
    <BarRankChart items={items} emptyMessage="No ranked data available" formatValue={(value) => format === "currency" ? currency(value) : pct(value)} />
  </article>
{/snippet}

{#snippet ListPanel(title: string, rows: string[])}
  <article class="panel list-panel">
    {@render PanelTitle(title)}
    {#if rows.length}
      <div class="list">
        {#each rows as row}<p>{row}</p>{/each}
      </div>
    {:else}
      <p class="muted">No active items.</p>
    {/if}
  </article>
{/snippet}

{#snippet SimpleTable(title: string, headers: string[], rows: RiskTableRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">{title}<span>{rows.length} rows</span></header>
    <table>
      <thead><tr>{#each headers as header}<th>{header}</th>{/each}</tr></thead>
      <tbody>
        {#if rows.length}
          {#each rows as row}
            <tr class={toneClass(row.tone)}>{#each row.cells as cell}<td>{cellValue(cell)}</td>{/each}</tr>
          {/each}
        {:else}
          <tr><td colspan={headers.length} class="empty">No rows available.</td></tr>
        {/if}
      </tbody>
    </table>
  </article>
{/snippet}

{#snippet HoldingsTable(rows: HoldingRiskRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Holdings<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Symbol</th><th>Name</th><th>Asset class</th><th>Weight</th><th>Market value</th><th>P&L</th><th>Vol</th><th>Beta</th><th>Risk contribution</th><th>Flag</th></tr></thead>
      <tbody>
        {#each rows as row}
          <tr><td>{row.symbol}</td><td>{row.name}</td><td>{row.assetClass}</td><td>{pct(row.weight)}</td><td>{currency(row.marketValue)}</td><td class={row.pnl == null ? "" : row.pnl >= 0 ? "positive" : "negative"}>{currency(row.pnl)}</td><td>{pct(row.volatility)}</td><td>{fmt(row.beta, 2)}</td><td>{pct(row.riskContribution)}</td><td class:warning={row.qualityFlag !== "OK"}>{row.qualityFlag}</td></tr>
        {/each}
      </tbody>
    </table>
  </article>
{/snippet}

{#snippet RiskContributorsTable(rows: RiskContributionRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Contribution Detail<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Symbol</th><th>Weight</th><th>Vol</th><th>Var %</th><th>Component VaR</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.symbol}</td><td>{pct(row.weight)}</td><td>{pct(row.volatility)}</td><td>{pct(row.contribution)}</td><td>{currency(row.componentVar)}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet ExposureTable(rows: ExposureBreakdownRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Exposure Breakdown<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Sector/category</th><th>Weight</th><th>Vol contribution</th><th>Benchmark</th><th>Active</th><th>Label</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.category}</td><td>{pct(row.weight)}</td><td>{pct(row.volatilityContribution)}</td><td>{pct(row.benchmarkWeight)}</td><td>{pct(row.activeWeight)}</td><td>{row.label}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet DrawdownTable(rows: DrawdownEpisode[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Worst Drawdown Episodes<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Start</th><th>Trough</th><th>Recovery</th><th>Depth</th><th>Duration</th><th>Benchmark DD</th><th>Main contributors</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.startDate}</td><td>{row.troughDate}</td><td>{row.recoveryDate}</td><td class="negative">{pct(row.depth)}</td><td>{row.duration}</td><td>{pct(row.benchmarkDrawdown)}</td><td>{row.contributors}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet ScenarioTable(rows: ScenarioResult[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Scenario Results<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Scenario</th><th>Portfolio</th><th>Benchmark</th><th>Active</th><th>Worst contributor</th><th>Best hedge</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.scenario}</td><td class={row.portfolioReturn == null ? "" : row.portfolioReturn >= 0 ? "positive" : "negative"}>{pct(row.portfolioReturn)}</td><td>{pct(row.benchmarkReturn)}</td><td>{pct(row.activeReturn)}</td><td>{row.worstContributor}</td><td>{row.bestHedge}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet ScenarioImpactTable(rows: ScenarioImpactRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Position-Level Impact<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Symbol</th><th>Current weight</th><th>Shock assumption</th><th>Estimated return</th><th>P&L impact</th><th>Contribution %</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.symbol}</td><td>{pct(row.weight)}</td><td>{row.shock}</td><td>{pct(row.estimatedReturn)}</td><td>{currency(row.pnlImpact)}</td><td>{pct(row.contributionPct)}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet CandidateTable(rows: CandidateAllocationRow[])}
  <article class="panel table-panel">
    <header class="table-panel-header">Candidate Allocation<span>{rows.length} rows</span></header>
    <table>
      <thead><tr><th>Symbol</th><th>Current weight</th><th>Proposed weight</th><th>Delta</th><th>Current risk</th><th>Proposed risk</th><th>Constraint</th></tr></thead>
      <tbody>{#each rows as row}<tr><td>{row.symbol}</td><td>{pct(row.currentWeight)}</td><td>{pct(row.proposedWeight)}</td><td class={row.delta == null ? "" : row.delta >= 0 ? "positive" : "negative"}>{pct(row.delta)}</td><td>{pct(row.currentRiskContribution)}</td><td>{pct(row.proposedRiskContribution)}</td><td>{row.constraintFlag}</td></tr>{/each}</tbody>
    </table>
  </article>
{/snippet}

{#snippet HeatmapPlaceholder(holdings: HoldingRiskRow[])}
  <div class="heatmap">
    {#each holdings.slice(0, 8) as row, rowIndex}
      {#each holdings.slice(0, 8) as col, colIndex}
        <div class:diag={rowIndex === colIndex} title={`${row.symbol} / ${col.symbol}`}>{rowIndex === colIndex ? "1.00" : "N/A"}</div>
      {/each}
    {/each}
  </div>
  <p class="muted">Position-level aligned return histories are not present in the current Risk API response, so cells stay unavailable instead of showing estimated precision.</p>
{/snippet}

{#snippet FrontierChart(plot: FrontierPlotModel)}
  <div class="frontier">
    {#if plot.points.length}
      <svg class="frontier-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Efficient frontier risk return chart">
        <line class="axis" x1="0" y1="100" x2="100" y2="100" />
        <line class="axis" x1="0" y1="0" x2="0" y2="100" />
        {#if plot.frontierPath}
          <path class="frontier-line" d={plot.frontierPath} />
        {/if}
        {#each plot.points.filter((point) => point.kind === "frontier") as point}
          <circle class="frontier-dot" cx={point.x} cy={point.y} r="1.05">
            <title>{point.label}: vol {pct(point.annualVol)}, return {pct(point.annualReturn)}, Sharpe {fmt(point.sharpe, 2)}</title>
          </circle>
        {/each}
        {#each plot.points.filter((point) => point.kind !== "frontier") as point}
          <circle class={`frontier-marker-dot ${point.kind}`} cx={point.x} cy={point.y} r="1.8">
            <title>{point.label}: vol {pct(point.annualVol)}, return {pct(point.annualReturn)}, Sharpe {fmt(point.sharpe, 2)}</title>
          </circle>
        {/each}
      </svg>
      <div class="frontier-label-layer">
        {#each plot.points.filter((point) => point.kind !== "frontier") as point}
          <span class={`frontier-label ${point.kind}`} style={`left:${point.x}%; top:${point.y}%;`}>{point.label}</span>
        {/each}
      </div>
      <span class="axis-label x-min">{pct(plot.xMin)}</span>
      <span class="axis-label x-max">{pct(plot.xMax)}</span>
      <span class="axis-label y-min">{pct(plot.yMin)}</span>
      <span class="axis-label y-max">{pct(plot.yMax)}</span>
    {:else}
      <div class="frontier-empty">Need at least two covered non-cash positions with overlapping return history.</div>
    {/if}
  </div>
  <p class="muted">Frontier uses the current covered risky sleeve and backend historical returns. It is a read-only research diagnostic, not an account or broker action.</p>
{/snippet}

<style>
  .view,
  .mode-shell,
  .workspace-grid,
  .primary-column,
  .support-column,
  .two-col,
  .shared-panels,
  .list {
    display: grid;
    gap: 0.5rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.75rem 0.85rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel { gap: 0.45rem; }
  .header-top, .header-actions, .context-bar, .settings-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .header-actions { justify-content: flex-end; }
  .workspace-grid { grid-template-columns: minmax(0, 1.8fr) minmax(20rem, 0.85fr); align-items: start; }
  .two-col, .shared-panels { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .primary-column, .support-column { align-content: start; }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(6, auto);
    width: fit-content;
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.38rem 0.78rem;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  .context-bar label,
  .context-field,
  .settings-row label {
    display: grid;
    gap: 0.18rem;
    min-width: 5rem;
  }

  label span,
  .context-field span,
  .eyebrow,
  .panel-title,
  .table-panel-header {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10.5px;
    font-weight: 600;
  }

  .context-bar strong,
  .context-field strong {
    min-height: 28px;
    display: flex;
    align-items: center;
    color: var(--text-0);
    text-transform: capitalize;
  }

  input,
  select,
  .action-btn {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    height: 28px;
    padding: 4px 8px;
    font: inherit;
    font-size: 12px;
    border-radius: 2px;
  }

  input:focus,
  select:focus { outline: 1px solid var(--accent); outline-offset: -1px; }
  .action-btn { cursor: pointer; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }
  .action-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
    gap: 0;
    border: 1px solid var(--divider);
    border-bottom: 0;
  }

  .metric {
    padding: 0.35rem 0.65rem;
    border-right: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .metric span { display: block; color: var(--text-2); font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
  .metric strong { display: block; margin-top: 0.12rem; color: var(--text-0); font-size: 13.5px; line-height: 1.2; }
  .metric small { color: var(--text-2); font-size: 10.5px; }

  .table-panel { padding: 0; overflow: auto; }
  .table-panel-header {
    min-height: 26px;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 0.34rem 0.5rem; border-bottom: 1px solid var(--divider); text-align: left; white-space: nowrap; font-size: 12px; }
  th { color: var(--text-2); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
  td.empty { color: var(--text-2); text-align: center; padding: 0.65rem; }

  .list p {
    margin: 0;
    color: var(--text-1);
    line-height: 1.35;
    padding-top: 0.38rem;
    border-top: 1px solid var(--divider);
  }
  .list p:first-child { padding-top: 0; border-top: 0; }

  h2, p, small { margin: 0; }
  h2 { font-size: 16px; line-height: 1.2; }
  .muted { color: var(--text-2); font-size: 12px; line-height: 1.35; }
  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  .warning { color: var(--warning); }

  .heatmap {
    display: grid;
    grid-template-columns: repeat(8, minmax(2.8rem, 1fr));
    border: 1px solid var(--divider);
  }
  .heatmap div {
    min-height: 2rem;
    display: grid;
    place-items: center;
    border-right: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    font-size: 11px;
  }
  .heatmap .diag { color: var(--accent); background: rgba(122, 166, 200, 0.08); }

  .frontier {
    min-height: 280px;
    border: 1px solid var(--divider);
    position: relative;
    background: var(--bg-0);
    overflow: hidden;
  }
  .frontier-svg {
    position: absolute;
    inset: 1.8rem 1rem 1.8rem 2.2rem;
    width: calc(100% - 3.2rem);
    height: calc(100% - 3.6rem);
  }
  .frontier-label-layer {
    position: absolute;
    inset: 1.8rem 1rem 1.8rem 2.2rem;
  }
  .frontier-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.4;
    vector-effect: non-scaling-stroke;
  }
  .frontier-dot {
    fill: var(--chart-primary);
    opacity: 0.45;
    vector-effect: non-scaling-stroke;
  }
  .frontier-marker-dot {
    fill: var(--bg-1);
    stroke: var(--chart-secondary);
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
  }
  .frontier-marker-dot.candidate { stroke: var(--chart-primary); }
  .frontier-marker-dot.current { stroke: var(--chart-secondary); fill: var(--chart-secondary); }
  .axis {
    stroke: var(--divider);
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }
  .frontier-label {
    position: absolute;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    padding: 0.22rem 0.35rem;
    font-size: 11px;
    transform: translate(-50%, -145%);
    white-space: nowrap;
  }
  .frontier-label.current { color: var(--chart-secondary); }
  .frontier-label.candidate { color: var(--chart-primary); }
  .axis-label {
    position: absolute;
    color: var(--text-2);
    font-size: 10px;
  }
  .axis-label.x-min { left: 2.2rem; bottom: 0.45rem; }
  .axis-label.x-max { right: 1rem; bottom: 0.45rem; }
  .axis-label.y-min { left: 0.45rem; bottom: 1.55rem; }
  .axis-label.y-max { left: 0.45rem; top: 1.35rem; }
  .frontier-empty {
    min-height: 280px;
    display: grid;
    place-items: center;
    color: var(--text-2);
    font-size: 12px;
    text-align: center;
    padding: 1rem;
  }

  @media (max-width: 1220px) {
    .workspace-grid, .two-col, .shared-panels { grid-template-columns: 1fr; }
    .mode-bar { grid-template-columns: repeat(3, auto); }
    .mode-bar button:nth-child(3) { border-right: 0; }
    .mode-bar button:nth-child(-n + 3) { border-bottom: 1px solid var(--panel-strong); }
  }

  @media (max-width: 760px) {
    .mode-bar { grid-template-columns: 1fr; width: 100%; }
    .mode-bar button { border-right: 0; border-bottom: 1px solid var(--panel-strong); }
    .mode-bar button:last-child { border-bottom: 0; }
    .context-bar label, .context-field, .settings-row label, input, select { width: 100%; }
  }
</style>
