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
    type RiskMode,
    type RiskKpi,
    type RiskContributionRow,
    type RiskCorrelationMatrixView,
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
    historyRows: number | null;
    historyStart: string | null;
    historyEnd: string | null;
    sourceProvider: string | null;
    x: number;
    y: number;
    clipped: boolean;
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
  let frontierW = 0;
  let frontierH = 0;
  let hoveredFrontierIdx: number | null = null;
  const FRONTIER_PAD = { l: 38, r: 14, t: 14, b: 28 };

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value) ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

  function corrColor(value: number | null | undefined) {
    if (value == null || !Number.isFinite(value)) return "transparent";
    const clamped = Math.max(-1, Math.min(1, value));
    if (clamped >= 0) {
      const a = 0.06 + clamped * clamped * 0.62;
      return `rgba(198, 107, 97, ${a.toFixed(3)})`;
    }
    const a = 0.06 + clamped * clamped * 0.45;
    return `rgba(75, 180, 116, ${a.toFixed(3)})`;
  }

  function corrTextColor(value: number | null | undefined) {
    if (value == null || !Number.isFinite(value)) return "var(--text-2)";
    return Math.abs(value) > 0.55 ? "var(--text-0)" : "var(--text-1)";
  }

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

  $: headerKpis = (() => {
    const coverage: RiskKpi = {
      label: "Coverage",
      value: workspace.context.coverageLabel,
      tone: (result?.metrics.risk_coverage_ratio ?? 1) < 0.95 ? "warning" : undefined,
    } as RiskKpi;
    let modeKpis: RiskKpi[] = [];
    if (activeMode === "overview") modeKpis = workspace.overviewKpis;
    else if (activeMode === "exposures") modeKpis = workspace.exposureKpis;
    else if (activeMode === "drawdowns") modeKpis = workspace.drawdownKpis;
    else if (activeMode === "correlation") modeKpis = workspace.correlationKpis;
    else if (activeMode === "scenarios") modeKpis = workspace.scenarioKpis;
    else modeKpis = workspace.optimizationKpis;
    return [coverage, ...modeKpis.slice(0, 4)];
  })();

  $: correlationMatrix = workspace.correlationMatrix;
  $: stressCorrelation = (() => {
    const normal = result?.metrics.correlation ?? null;
    if (normal == null || !Number.isFinite(normal)) return { normal: null, stress: null, delta: null };
    const stress = Math.min(0.99, normal + 0.15);
    return { normal, stress, delta: stress - normal };
  })();

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
    const raw = points
      .filter((point) => Number.isFinite(point.annual_vol) && Number.isFinite(point.annual_return))
      .map((point) => ({
        label: point.label,
        kind: point.kind,
        annualReturn: point.annual_return,
        annualVol: point.annual_vol,
        sharpe: point.sharpe,
        historyRows: point.history_rows ?? null,
        historyStart: point.history_start ?? null,
        historyEnd: point.history_end ?? null,
        sourceProvider: point.source_provider ?? null,
        x: 0,
        y: 0,
        clipped: false,
      }));
    const portfolioLabels = new Set(
      raw
        .filter((point) => point.kind === "asset" || point.kind === "candidate" || point.kind === "current")
        .map((point) => normalizeFrontierLabel(point.label))
        .filter(Boolean)
    );
    const seen = new Set<string>();
    const clean = raw.filter((point) => {
      if (!isVisibleFrontierKind(point.kind)) return false;
      if (point.kind === "cached_equity_asset" && portfolioLabels.has(normalizeFrontierLabel(point.label))) {
        return false;
      }
      const dedupeKey = `${point.kind}:${normalizeFrontierLabel(point.label)}`;
      if (seen.has(dedupeKey)) return false;
      seen.add(dedupeKey);
      return true;
    });
    if (!clean.length) return { points: [], frontierPath: "", xMin: 0, xMax: 0, yMin: 0, yMax: 0 };
    const domainClean = clean.filter((point) => !isHiddenReferenceAsset(point));
    const core = domainClean.filter((point) => !isCachedEquityKind(point.kind));
    const cached = domainClean.filter((point) => isCachedEquityKind(point.kind));
    const xValues = boundedDomainValues(core.map((point) => point.annualVol), cached.map((point) => point.annualVol));
    const yValues = boundedDomainValues(core.map((point) => point.annualReturn), cached.map((point) => point.annualReturn));
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
      x: clamp(((point.annualVol - xMin) / width) * 100, 0, 100),
      y: clamp(100 - ((point.annualReturn - yMin) / height) * 100, 0, 100),
      clipped: point.annualVol < xMin || point.annualVol > xMax || point.annualReturn < yMin || point.annualReturn > yMax,
    }));
    const frontierPath = plotted
      .filter((point) => point.kind === "frontier")
      .sort((left, right) => left.annualVol - right.annualVol)
      .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
      .join(" ");
    return { points: plotted, frontierPath, xMin, xMax, yMin, yMax };
  }

  function isVisibleFrontierKind(kind: string) {
    return kind === "current" || kind === "candidate" || kind === "frontier" || kind === "asset" || kind === "risk_free" || kind === "cached_equity_asset" || kind === "cached_equity_frontier";
  }

  function isCachedEquityKind(kind: string) {
    return kind === "cached_equity_asset" || kind === "cached_equity_frontier" || kind === "cached_equity_candidate";
  }

  function isHiddenReferenceAsset(point: Pick<FrontierPlotPoint, "kind" | "annualReturn">) {
    return point.kind === "cached_equity_asset" && point.annualReturn < 0;
  }

  function normalizeFrontierLabel(value: string) {
    return String(value || "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  }

  function boundedDomainValues(core: number[], cached: number[]) {
    const finiteCore = core.filter(Number.isFinite);
    const finiteCached = cached.filter(Number.isFinite);
    if (!finiteCached.length) return finiteCore.length ? finiteCore : [0];
    const boundedCached =
      finiteCached.length >= 8
        ? [
            quantile(finiteCached, 0.1),
            quantile(finiteCached, 0.9),
          ]
        : finiteCached;
    return finiteCore.length ? [...finiteCore, ...boundedCached] : boundedCached;
  }

  function quantile(values: number[], q: number) {
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return 0;
    const position = (sorted.length - 1) * q;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sorted[lower];
    const weight = position - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
  }

  function viridisColor(t: number): string {
    const v = Math.max(0, Math.min(1, t));
    const stops: [number, [number, number, number]][] = [
      [0.0,  [68,   1,  84]],
      [0.25, [59,  82, 139]],
      [0.5,  [33, 145, 140]],
      [0.75, [94, 201,  98]],
      [1.0,  [253, 231,  37]],
    ];
    for (let i = 1; i < stops.length; i++) {
      if (v <= stops[i][0]) {
        const [t0, [r0, g0, b0]] = stops[i - 1];
        const [t1, [r1, g1, b1]] = stops[i];
        const f = (v - t0) / (t1 - t0);
        return `rgb(${Math.round(r0 + f * (r1 - r0))},${Math.round(g0 + f * (g1 - g0))},${Math.round(b0 + f * (b1 - b0))})`;
      }
    }
    return "rgb(253,231,37)";
  }

  function smoothSvgPath(points: Array<{ px: number; py: number }>) {
    if (points.length < 2) return "";
    if (points.length === 2) {
      return `M ${points[0].px.toFixed(1)} ${points[0].py.toFixed(1)} L ${points[1].px.toFixed(1)} ${points[1].py.toFixed(1)}`;
    }
    const tension = 0.15;
    return points
      .map((point, index) => {
        if (index === 0) return `M ${point.px.toFixed(1)} ${point.py.toFixed(1)}`;
        const previous = points[index - 1];
        const beforePrevious = points[Math.max(0, index - 2)];
        const next = points[Math.min(points.length - 1, index + 1)];
        const cp1x = previous.px + (point.px - beforePrevious.px) * tension;
        const cp1y = previous.py + (point.py - beforePrevious.py) * tension;
        const cp2x = point.px - (next.px - previous.px) * tension;
        const cp2y = point.py - (next.py - previous.py) * tension;
        return `C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)} ${cp2x.toFixed(1)} ${cp2y.toFixed(1)} ${point.px.toFixed(1)} ${point.py.toFixed(1)}`;
      })
      .join(" ");
  }

  function frontierEnvelopePath(points: Array<{ px: number; py: number; annualVol: number; annualReturn: number }>) {
    const clean = points
      .filter((point) => Number.isFinite(point.px) && Number.isFinite(point.py))
      .sort((left, right) => left.annualVol - right.annualVol);
    if (clean.length < 2) return smoothSvgPath(clean);

    const upper: typeof clean = [];
    for (const point of clean) {
      const previous = upper.at(-1);
      if (!previous) {
        upper.push(point);
        continue;
      }
      if (point.px - previous.px < 18) {
        if (point.annualReturn >= previous.annualReturn) {
          upper[upper.length - 1] = point;
        }
        continue;
      }
      upper.push(point);
    }

    const first = clean[0];
    const last = clean[clean.length - 1];
    const displayPoints = [first, ...upper.filter((point) => point !== first && point !== last), last];
    const deduped = displayPoints.filter((point, index, rows) => index === 0 || point.px !== rows[index - 1].px || point.py !== rows[index - 1].py);
    if (deduped.length < 3) return smoothSvgPath(deduped);

    return deduped
      .map((point, index) => {
        if (index === 0) return `M ${point.px.toFixed(1)} ${point.py.toFixed(1)}`;
        const previous = deduped[index - 1];
        const dx = point.px - previous.px;
        return `C ${(previous.px + dx * 0.45).toFixed(1)} ${previous.py.toFixed(1)} ${(point.px - dx * 0.45).toFixed(1)} ${point.py.toFixed(1)} ${point.px.toFixed(1)} ${point.py.toFixed(1)}`;
      })
      .join(" ");
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
      <span class="title">Risk Workspace</span>
      <span class="subtitle">{workspace.context.sourceScope} · {workspace.context.baseCurrency}</span>
    </div>
    <div class="mode-kpi-row">
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
      <div class="header-kpis">
        {#each headerKpis as kpi}
          <div class="header-kpi">
            <span>{kpi.label}</span>
            <strong class={toneClass(kpi.tone)}>{kpi.value}</strong>
          </div>
        {/each}
      </div>
    </div>
  </article>

  <article class="panel controls-card">
    <div class="controls-bar">
      <label class="control"><span>Benchmark</span><input bind:value={benchmarkSymbol} /></label>
      <label class="control"><span>Lookback</span>
        <select bind:value={lookbackDays}>
          <option value={126}>126D</option><option value={252}>252D</option><option value={504}>504D</option>
        </select>
      </label>
      <label class="control"><span>Frequency</span>
        <select bind:value={returnFrequency}>
          <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
        </select>
      </label>
      <label class="control"><span>Confidence</span><select bind:value={confidence}><option value={0.9}>90%</option><option value={0.95}>95%</option><option value={0.99}>99%</option></select></label>
      <label class="control"><span>Horizon</span><select bind:value={horizonDays}><option value={1}>1D</option><option value={10}>10D</option><option value={21}>21D</option></select></label>
      <label class="control"><span>Beta win.</span><select bind:value={betaWindow}><option value={63}>63D</option><option value={126}>126D</option><option value={252}>252D</option></select></label>
      <label class="control"><span>MC horiz.</span><select bind:value={mcHorizonDays}><option value={5}>5D</option><option value={10}>10D</option><option value={21}>21D</option><option value={63}>63D</option></select></label>
      <label class="control"><span>MC model</span><select bind:value={mcSimulationModel}><option value="Gaussian">Gaussian</option><option value="Bootstrap">Bootstrap</option></select></label>
      <label class="control"><span>Sims</span><select bind:value={mcNumSimulations}><option value={1000}>1k</option><option value={2000}>2k</option><option value={5000}>5k</option></select></label>
      <div class="actions">
        <button class="action-btn" on:click={() => submit("core")} disabled={loading || !activeSnapshot}>
          {loading && activeComputeMethod === "core" ? "Computing" : "Compute Core"}
        </button>
        <button class="action-btn primary" on:click={() => submit("monteCarlo")} disabled={loading || !activeSnapshot}>
          {loading && activeComputeMethod === "monteCarlo" ? "Running" : "Run MC"}
        </button>
      </div>
    </div>
  </article>

  {#if activeMode === "overview"}
    <div class="mode-shell">
      <div class="workspace-grid">
        <div class="primary-column">
        {#if result?.monte_carlo?.fan_percentiles}
          <div class="two-col">
            <article class="panel chart-panel">{@render PanelTitle("Cumulative Return vs Benchmark")}<TimeSeriesChart series={cumulativeChart} height={240} emptyMessage="Run a risk pass to populate portfolio and benchmark return history" /></article>
            <article class="panel chart-panel">{@render PanelTitle("Forward Path Envelope")}<FanChart series={result.monte_carlo.fan_percentiles} history={fanHistory} samplePaths={result.monte_carlo.sample_paths} height={240} emptyMessage="Monte Carlo fan chart unavailable" /></article>
          </div>
        {:else}
          <article class="panel chart-panel">{@render PanelTitle("Cumulative Return vs Benchmark")}<TimeSeriesChart series={cumulativeChart} height={260} emptyMessage="Run a risk pass to populate portfolio and benchmark return history" /></article>
        {/if}
        <div class="two-col">
          <article class="panel chart-panel">{@render PanelTitle("Rolling Volatility")}<TimeSeriesChart series={rollingVolChart} height={220} emptyMessage="Need at least 21 observations" /></article>
          <article class="panel chart-panel">{@render PanelTitle("Rolling Beta")}<TimeSeriesChart series={rollingBetaChart} height={220} emptyMessage="Need benchmark overlap for selected beta window" /></article>
        </div>
        {#if result?.monte_carlo?.terminal_returns}
          <div class="two-col">
            <article class="panel chart-panel">{@render PanelTitle("Drawdown Strip")}<TimeSeriesChart series={drawdownChart} height={200} emptyMessage="Drawdown history unavailable" /></article>
            <article class="panel chart-panel">{@render PanelTitle("MC Terminal Distribution")}<DistributionChart values={result.monte_carlo.terminal_returns} markers={monteCarloMarkers} height={200} emptyMessage="Monte Carlo distribution unavailable" /></article>
          </div>
        {:else}
          <article class="panel chart-panel">{@render PanelTitle("Drawdown Strip")}<TimeSeriesChart series={drawdownChart} height={180} emptyMessage="Drawdown history unavailable" /></article>
        {/if}
        {@render RiskContributorsTable(workspace.riskContributors)}
        </div>
        <aside class="support-column">
        {@render RankPanel("Top Risk Contributors", riskContributionBars)}
        {@render SimpleTable("Largest Movers", ["Symbol", "P&L", "Weight", "Flag"], workspace.largestMovers)}
        {@render SimpleTable("Concentration Flags", ["Type", "Name", "Value", "Rule"], workspace.concentrationFlags)}
        {@render ListPanel("What Changed", workspace.whatChanged)}
        {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {:else if activeMode === "exposures"}
    <div class="mode-shell">
      <div class="workspace-grid">
        <div class="primary-column">
          {@render RankPanel("Position Weight", weightBars)}
          {@render RankPanel("Sector / Asset-Class Exposure", exposureBars)}
          {@render HoldingsTable(workspace.holdings)}
        </div>
        <aside class="support-column">
          {@render ExposureTable(workspace.exposureBreakdown)}
          {@render SimpleTable("Currency Exposure", ["Currency", "Weight", "Contribution", "Status"], workspace.exposureBreakdown.map((row) => ({ cells: [row.category === "Cash" ? workspace.context.baseCurrency : "Mixed", pct(row.weight), pct(row.volatilityContribution), row.label] })))}
          {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {:else if activeMode === "drawdowns"}
    <div class="mode-shell">
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
          {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {:else if activeMode === "correlation"}
    <div class="mode-shell">
      <div class="workspace-grid">
        <div class="primary-column">
        <article class="panel heatmap-panel">{@render PanelTitle("Correlation Heatmap")}{@render CorrelationHeatmap(workspace.correlationMatrix)}</article>
        <div class="two-col">
          <article class="panel chart-panel">{@render PanelTitle("Rolling Correlation To Benchmark")}<TimeSeriesChart series={rollingBetaChart} height={220} emptyMessage="Correlation series requires benchmark overlap" /></article>
          <article class="panel">{@render PanelTitle("Normal vs Stress Correlation")}{@render StressCompare(stressCorrelation)}</article>
        </div>
        {@render SimpleTable("Highest Correlated Pairs", ["Pair", "Corr", "Read"], workspace.correlatedPairs)}
        </div>
        <aside class="support-column">
          {@render SimpleTable("Diversification Warnings", ["Cluster", "Members", "Weight", "Avg corr", "Risk contribution"], workspace.diversificationWarnings)}
          {@render SimpleTable("Benchmark Sensitivity", ["Symbol", "Beta", "Corr", "R2", "Tracking contribution"], workspace.benchmarkSensitivity)}
          {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {:else if activeMode === "scenarios"}
    <div class="mode-shell">
      <div class="workspace-grid">
        <div class="primary-column">
          {@render RankPanel("Scenario Waterfall", scenarioBars, "currency")}
          {@render ScenarioTable(workspace.scenarios)}
          {@render ScenarioImpactTable(workspace.scenarioImpacts)}
        </div>
        <aside class="support-column">
          {@render RankPanel("Shock Impact by Asset Class", exposureBars.map((item) => ({ ...item, value: item.value * (workspace.scenarios[0]?.portfolioReturn ?? 0) })))}
          {@render ListPanel("Scenario Assumptions", workspace.scenarioAssumptions)}
          {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {:else}
    <div class="mode-shell">
      <div class="workspace-grid">
        <div class="primary-column">
          <article class="panel chart-panel">{@render PanelTitle("Efficient Frontier")}{@render FrontierChart(frontierPlot, workspace.frontierMessage)}</article>
          {@render RankPanel("Weight Changes Before / After", optimizationBars)}
          {@render CandidateTable(workspace.candidates)}
        </div>
        <aside class="support-column">
          {@render SimpleTable("Optimization Comparison", ["Candidate", "Vol", "Score", "Max wt", "Status"], workspace.optimizationComparison)}
          {@render SimpleTable("Constraint Panel", ["Constraint", "Setting", "Note"], workspace.constraints)}
          {@render ListPanel("Diagnostics", workspace.diagnostics)}
          {@render SharedAlerts()}
        </aside>
      </div>
    </div>
  {/if}
</section>

{#snippet PanelTitle(title: string)}
  <header class="panel-title"><span>{title}</span></header>
{/snippet}

{#snippet SharedAlerts()}
  {@render ListPanel("Risk Alerts", workspace.alerts)}
  {@render ListPanel("Provenance / Coverage", [...workspace.provenance, ...workspace.coverageWarnings.slice(0, 6)])}
{/snippet}

{#snippet RankPanel(title: string, items: RankBarItem[], format: "percent" | "currency" = "percent")}
  <article class="panel rank-panel">
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

{#snippet CorrelationHeatmap(matrix: RiskCorrelationMatrixView)}
  {@const assets = matrix.assets.slice(0, 10)}
  {@const values = new Map(matrix.cells.map((cell) => [`${cell.row}|${cell.column}`, cell.correlation]))}
  {#if assets.length >= 2}
    <div class="heatmap" style={`grid-template-columns:minmax(4.2rem,0.85fr) repeat(${assets.length}, minmax(2.8rem,1fr));`}>
      <div class="heatmap-corner"></div>
      {#each assets as asset}
        <div class="heatmap-label top" title={asset.key}>{asset.label}</div>
      {/each}
      {#each assets as row}
        <div class="heatmap-label side" title={row.key}>{row.label}</div>
        {#each assets as col}
          {@const value = row.key === col.key ? 1 : (values.get(`${row.key}|${col.key}`) ?? values.get(`${col.key}|${row.key}`) ?? null)}
          <div
            class="heatmap-cell"
            class:diag={row.key === col.key}
            style={`background:${corrColor(value)}; color:${corrTextColor(value)};`}
            title={value == null ? `${row.label} / ${col.label}: unavailable` : `${row.label} / ${col.label}: ${value.toFixed(3)}`}
          >
            {value == null ? "—" : value.toFixed(2)}
          </div>
        {/each}
      {/each}
    </div>
    <div class="heatmap-scale">
      <span class="scale-end">−1</span>
      <div class="scale-track">
        {#each Array(21) as _, i}
          <span class="scale-step" style={`background:${corrColor((i - 10) / 10)};`}></span>
        {/each}
      </div>
      <span class="scale-end">+1</span>
      <span class="scale-note">closer to +1 = redder · negative = green</span>
    </div>
  {:else}
    <div class="frontier-empty">Run a risk pass with at least two covered assets to populate the correlation heatmap.</div>
  {/if}
{/snippet}

{#snippet StressCompare(values: { normal: number | null; stress: number | null; delta: number | null })}
  <div class="stress-compare">
    <div class="sc-row">
      <span class="sc-lbl">Normal</span>
      <div class="sc-track"><div class="sc-fill" style={`width:${values.normal != null ? Math.abs(values.normal) * 100 : 0}%; background:${corrColor(values.normal)};`}></div></div>
      <strong class="sc-val">{fmt(values.normal, 2)}</strong>
    </div>
    <div class="sc-row">
      <span class="sc-lbl">Stress</span>
      <div class="sc-track"><div class="sc-fill" style={`width:${values.stress != null ? Math.abs(values.stress) * 100 : 0}%; background:${corrColor(values.stress)};`}></div></div>
      <strong class="sc-val">{fmt(values.stress, 2)}</strong>
    </div>
    <div class="sc-delta">
      <span>Δ Stress</span>
      <strong class={values.delta != null && values.delta >= 0 ? "negative" : "positive"}>{values.delta == null ? "N/A" : (values.delta >= 0 ? "+" : "") + fmt(values.delta, 2)}</strong>
    </div>
  </div>
{/snippet}

{#snippet FrontierChart(plot: FrontierPlotModel, emptyMessage: string | null)}
  <div class="frontier" bind:clientWidth={frontierW} bind:clientHeight={frontierH}>
    {#if plot.points.length && frontierW > 0 && frontierH > 0}
      {@const plotW = Math.max(frontierW - FRONTIER_PAD.l - FRONTIER_PAD.r, 1)}
      {@const plotH = Math.max(frontierH - FRONTIER_PAD.t - FRONTIER_PAD.b, 1)}
      {@const pixelPoints = plot.points.map((p, idx) => ({
        ...p,
        idx,
        px: FRONTIER_PAD.l + (p.x / 100) * plotW,
        py: FRONTIER_PAD.t + (p.y / 100) * plotH,
      }))}
      {@const cachedEquityFrontierPx = pixelPoints
        .filter((p) => p.kind === "cached_equity_frontier")
        .sort((a, b) => a.annualVol - b.annualVol)}
      {@const cachedEquityFrontierLine = smoothSvgPath(cachedEquityFrontierPx)}
      {@const portfolioFrontierPx = pixelPoints
        .filter((p) => p.kind === "frontier")
        .sort((a, b) => a.annualVol - b.annualVol)}
      {@const portfolioFrontierLine = frontierEnvelopePath(portfolioFrontierPx)}
      {@const portfolioAssetPx = pixelPoints.filter((p) => p.kind === "asset" && !p.clipped)}
      {@const cachedAssetPx = pixelPoints.filter((p) => p.kind === "cached_equity_asset" && !p.clipped && !isHiddenReferenceAsset(p))}
      {@const namedMarkerPx = pixelPoints.filter((p) => ["current", "candidate", "risk_free"].includes(p.kind))}
      {@const minVolFrontierPt = cachedEquityFrontierPx.length
        ? cachedEquityFrontierPx.reduce((a, b) => (a.annualVol <= b.annualVol ? a : b))
        : null}
      {@const maxSharpeFrontierPt = cachedEquityFrontierPx.length
        ? cachedEquityFrontierPx.reduce((a, b) => ((a.sharpe ?? -Infinity) >= (b.sharpe ?? -Infinity) ? a : b))
        : null}
      {@const specialFrontierMarkers = [
        ...(minVolFrontierPt ? [{ ...minVolFrontierPt, label: "Min Vol", markerKind: "min-vol" }] : []),
        ...(maxSharpeFrontierPt && maxSharpeFrontierPt.idx !== minVolFrontierPt?.idx
          ? [{ ...maxSharpeFrontierPt, label: "Max Sharpe", markerKind: "max-sharpe" }]
          : []),
      ]}
      {@const specialFrontierIdxs = new Set(
        [minVolFrontierPt?.idx, maxSharpeFrontierPt?.idx].filter((n): n is number => n != null)
      )}
      {@const assetSharpes = cachedAssetPx
        .map((p) => p.sharpe)
        .filter((s): s is number => Number.isFinite(s))}
      {@const sharpeMin = assetSharpes.length ? Math.min(...assetSharpes) : 0}
      {@const sharpeRange = Math.max((assetSharpes.length ? Math.max(...assetSharpes) : 1) - sharpeMin, 0.001)}
      {@const rfPt = pixelPoints.find((p) => p.kind === "risk_free") ?? null}
      {@const portfolioMaxSharpePt = namedMarkerPx.find((p) => p.kind === "candidate" && p.label === "Max Sharpe") ?? null}
      {@const cmlCoords = (() => {
        const tangencyPt = portfolioMaxSharpePt ?? maxSharpeFrontierPt;
        if (!rfPt || !tangencyPt) return null;
        const dVol = tangencyPt.annualVol - rfPt.annualVol;
        if (dVol <= 0) return null;
        const slope = (tangencyPt.annualReturn - rfPt.annualReturn) / dVol;
        const yRange = Math.max(plot.yMax - plot.yMin, 1e-9);
        const endReturn = rfPt.annualReturn + slope * (plot.xMax - rfPt.annualVol);
        return {
          x1: rfPt.px, y1: rfPt.py,
          x2: FRONTIER_PAD.l + plotW,
          y2: FRONTIER_PAD.t + (1 - (endReturn - plot.yMin) / yRange) * plotH,
        };
      })()}
      {@const zeroReturnY = plot.yMin < 0 && plot.yMax > 0
        ? FRONTIER_PAD.t + (1 - (0 - plot.yMin) / Math.max(plot.yMax - plot.yMin, 1e-9)) * plotH
        : null}
      {@const hovered = hoveredFrontierIdx != null ? pixelPoints[hoveredFrontierIdx] ?? null : null}
      <svg width={frontierW} height={frontierH} aria-label="Efficient frontier risk return chart">
        <defs>
          <clipPath id="fp-clip">
            <rect x={FRONTIER_PAD.l} y={FRONTIER_PAD.t} width={plotW} height={plotH} />
          </clipPath>
        </defs>
        {#each [0.25, 0.5, 0.75] as t}
          <line class="grid" x1={FRONTIER_PAD.l} y1={FRONTIER_PAD.t + t * plotH} x2={frontierW - FRONTIER_PAD.r} y2={FRONTIER_PAD.t + t * plotH} />
          <line class="grid" x1={FRONTIER_PAD.l + t * plotW} y1={FRONTIER_PAD.t} x2={FRONTIER_PAD.l + t * plotW} y2={frontierH - FRONTIER_PAD.b} />
        {/each}
        {#if zeroReturnY != null}
          <line class="zero-return-line"
            x1={FRONTIER_PAD.l} y1={zeroReturnY}
            x2={frontierW - FRONTIER_PAD.r} y2={zeroReturnY} />
        {/if}
        <line class="axis" x1={FRONTIER_PAD.l} y1={frontierH - FRONTIER_PAD.b} x2={frontierW - FRONTIER_PAD.r} y2={frontierH - FRONTIER_PAD.b} />
        <line class="axis" x1={FRONTIER_PAD.l} y1={FRONTIER_PAD.t} x2={FRONTIER_PAD.l} y2={frontierH - FRONTIER_PAD.b} />
        <g clip-path="url(#fp-clip)">
          {#if cmlCoords}
            <line class="cml-line"
              x1={cmlCoords.x1} y1={cmlCoords.y1}
              x2={cmlCoords.x2} y2={cmlCoords.y2} />
          {/if}
          {#if cachedEquityFrontierLine}
            <path class="cached-equity-frontier-line" d={cachedEquityFrontierLine} />
          {/if}
          {#if portfolioFrontierLine}
            <path class="frontier-line" d={portfolioFrontierLine} />
          {/if}
          {#each portfolioAssetPx as p}
            <circle
              class="frontier-marker-dot asset"
              class:hovered={hoveredFrontierIdx === p.idx}
              cx={p.px} cy={p.py}
              r={hoveredFrontierIdx === p.idx ? 4.8 : 3}
              role="button" tabindex="0"
              aria-label={`${p.label}: vol ${pct(p.annualVol)}, return ${pct(p.annualReturn)}, Sharpe ${fmt(p.sharpe, 2)}`}
              on:mouseenter={() => (hoveredFrontierIdx = p.idx)}
              on:mouseleave={() => (hoveredFrontierIdx = null)}
              on:focus={() => (hoveredFrontierIdx = p.idx)}
              on:blur={() => (hoveredFrontierIdx = null)}
            />
          {/each}
          {#each cachedAssetPx as p}
            <circle
              class="frontier-marker-dot cached_equity_asset"
              class:hovered={hoveredFrontierIdx === p.idx}
              cx={p.px} cy={p.py}
              r={hoveredFrontierIdx === p.idx ? 4.4 : 2.7}
              style="fill:{viridisColor(((p.sharpe ?? sharpeMin) - sharpeMin) / sharpeRange)};stroke:none;opacity:{hoveredFrontierIdx === p.idx ? 0.9 : 0.65};"
              role="button" tabindex="0"
              aria-label={`${p.label}: vol ${pct(p.annualVol)}, return ${pct(p.annualReturn)}, Sharpe ${fmt(p.sharpe, 2)}`}
              on:mouseenter={() => (hoveredFrontierIdx = p.idx)}
              on:mouseleave={() => (hoveredFrontierIdx = null)}
              on:focus={() => (hoveredFrontierIdx = p.idx)}
              on:blur={() => (hoveredFrontierIdx = null)}
            />
          {/each}
          {#each namedMarkerPx as p}
            <circle
              class={`frontier-marker-dot ${p.kind}`}
              class:hovered={hoveredFrontierIdx === p.idx}
              cx={p.px} cy={p.py}
              r={p.kind === "risk_free" ? (hoveredFrontierIdx === p.idx ? 6.5 : 5) : (hoveredFrontierIdx === p.idx ? 7 : 5.8)}
              role="button" tabindex="0"
              aria-label={`${p.label}: vol ${pct(p.annualVol)}, return ${pct(p.annualReturn)}, Sharpe ${fmt(p.sharpe, 2)}`}
              on:mouseenter={() => (hoveredFrontierIdx = p.idx)}
              on:mouseleave={() => (hoveredFrontierIdx = null)}
              on:focus={() => (hoveredFrontierIdx = p.idx)}
              on:blur={() => (hoveredFrontierIdx = null)}
            />
          {/each}
          {#each specialFrontierMarkers as p}
            <circle
              class={`frontier-marker-dot special-frontier ${p.markerKind}`}
              class:hovered={hoveredFrontierIdx === p.idx}
              cx={p.px} cy={p.py}
              r={hoveredFrontierIdx === p.idx ? 6.5 : 5}
              role="button" tabindex="0"
              aria-label={`${p.label}: vol ${pct(p.annualVol)}, return ${pct(p.annualReturn)}, Sharpe ${fmt(p.sharpe, 2)}`}
              on:mouseenter={() => (hoveredFrontierIdx = p.idx)}
              on:mouseleave={() => (hoveredFrontierIdx = null)}
              on:focus={() => (hoveredFrontierIdx = p.idx)}
              on:blur={() => (hoveredFrontierIdx = null)}
            />
          {/each}
        </g>
      </svg>

      <div class="frontier-label-layer">
        {#if hovered && (["current", "candidate", "risk_free"].includes(hovered.kind) || specialFrontierIdxs.has(hovered.idx))}
          <span
            class={`frontier-label ${hovered.kind}`}
            style={`left:${hovered.px}px; top:${hovered.py - 14}px;`}
          >{hovered.label}</span>
        {/if}
      </div>

      <span class="axis-label x-min">Vol {pct(plot.xMin)}</span>
      <span class="axis-label x-max">{pct(plot.xMax)}</span>
      <span class="axis-label y-min">{pct(plot.yMin)}</span>
      <span class="axis-label y-max">Ret {pct(plot.yMax)}</span>

      {#if hovered}
        <div
          class="frontier-tooltip"
          style={`left:${Math.min(hovered.px + 12, frontierW - 180)}px; top:${Math.max(hovered.py - 4, 8)}px;`}
        >
          <strong>{hovered.label}</strong>
          <span><em>Vol</em> {pct(hovered.annualVol)}</span>
          <span><em>Return</em> {pct(hovered.annualReturn)}</span>
          <span><em>Sharpe</em> {fmt(hovered.sharpe, 2)}</span>
          {#if hovered.historyRows}
            <span><em>Rows</em> {hovered.historyRows}</span>
          {/if}
          {#if hovered.historyStart && hovered.historyEnd}
            <span><em>Window</em> {hovered.historyStart} - {hovered.historyEnd}</span>
          {/if}
          {#if hovered.sourceProvider}
            <span><em>Source</em> {hovered.sourceProvider}</span>
          {/if}
        </div>
      {/if}
    {:else if plot.points.length}
      <!-- waiting for measurement -->
    {:else}
      <div class="frontier-empty">{emptyMessage ?? "Run a risk computation to populate the efficient frontier."}</div>
    {/if}
  </div>
{/snippet}

<style>
  .view,
  .mode-shell,
  .workspace-grid,
  .primary-column,
  .support-column,
  .two-col,
  .list {
    display: grid;
    gap: 0.5rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.65rem 0.75rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel {
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
  }

  .header-top {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }

  .title {
    color: var(--text-0);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .subtitle {
    color: var(--text-2);
    font-size: 10.5px;
    letter-spacing: 0.04em;
  }

  .mode-kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .header-kpis {
    display: flex;
    gap: 0;
    flex-wrap: wrap;
    border-left: 1px solid var(--divider);
  }

  .header-kpi {
    display: grid;
    gap: 0.05rem;
    padding: 0.1rem 0.7rem;
    border-right: 1px solid var(--divider);
    min-width: 5.5rem;
  }

  .header-kpi span {
    color: var(--text-2);
    font-size: 9.5px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    line-height: 1.1;
  }

  .header-kpi strong {
    color: var(--text-0);
    font-size: 12.5px;
    font-weight: 600;
    line-height: 1.15;
    white-space: nowrap;
  }

  .header-kpi strong.warning { color: var(--warning); }
  .header-kpi strong.positive { color: var(--positive); }
  .header-kpi strong.negative { color: var(--negative); }

  .controls-card { padding: 0.45rem 0.65rem; }

  .workspace-grid { grid-template-columns: minmax(0, 1.8fr) minmax(20rem, 0.85fr); align-items: start; }
  .two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .primary-column, .support-column { align-content: start; }

  /* ── Mode bar ── */
  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(6, auto);
    border: 1px solid var(--panel-strong);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.28rem 0.65rem;
    font: inherit;
    font-size: 0.79rem;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  /* ── Controls bar ── */
  .controls-bar {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    align-items: flex-end;
  }

  .actions {
    margin-left: auto;
    display: flex;
    gap: 0.35rem;
    align-items: flex-end;
    padding-left: 0.5rem;
    border-left: 1px solid var(--divider);
    align-self: stretch;
  }

  .actions .action-btn { align-self: flex-end; }

  .control {
    display: grid;
    gap: 0.15rem;
    min-width: 4.5rem;
    flex: 1 1 4.5rem;
  }

  .control:has(input) { flex: 1 1 5rem; min-width: 5rem; }

  .control > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10px;
    font-weight: 500;
  }

  .control > strong {
    height: 28px;
    display: flex;
    align-items: center;
    color: var(--text-0);
    font-size: 12px;
    font-weight: 500;
    text-transform: capitalize;
  }

  /* ── Inputs / buttons ── */
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
  .action-btn {
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
    padding: 0 0.7rem;
  }
  .action-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .action-btn.primary {
    background: rgba(122, 166, 200, 0.1);
    border-color: rgba(122, 166, 200, 0.5);
    color: var(--accent);
  }
  .action-btn.primary:hover:not(:disabled) { background: rgba(122, 166, 200, 0.18); }

  /* ── Panel headers ── */
  .panel-title,
  .table-panel-header {
    min-height: 26px;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    color: var(--text-1);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 11px;
    font-weight: 600;
  }

  .table-panel-header span { color: var(--text-2); font-weight: 400; font-size: 10px; }

  /* Chart, heatmap, table panels: edge-to-edge content under a 26px header */
  .table-panel,
  .chart-panel,
  .heatmap-panel { padding: 0; }
  .table-panel { overflow: auto; }
  .chart-panel { gap: 0; }

  /* ── Tables ── */
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 0.34rem 0.5rem; border-bottom: 1px solid var(--divider); text-align: left; white-space: nowrap; font-size: 12px; }
  th { color: var(--text-2); font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
  td.empty { color: var(--text-2); text-align: center; padding: 0.65rem; }
  tbody tr:hover { background: rgba(122, 166, 200, 0.06); }

  /* ── Lists ── */
  .list-panel { padding: 0; }
  .list-panel .list { padding: 0.5rem 0.75rem; gap: 0.4rem; }
  .list p {
    margin: 0;
    color: var(--text-1);
    font-size: 12px;
    line-height: 1.4;
  }
  .list-panel > p.muted { padding: 0.5rem 0.75rem; }

  p { margin: 0; }
  .muted { color: var(--text-2); font-size: 11px; line-height: 1.35; }
  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  .warning { color: var(--warning); }

  /* ── Heatmap ── */
  .heatmap {
    display: grid;
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
  .heatmap-label,
  .heatmap-corner {
    color: var(--text-2);
    background: var(--surface-0);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 0 0.35rem;
  }
  .heatmap-label.side {
    justify-items: start;
  }
  .heatmap-cell {
    color: var(--text-1);
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }
  .heatmap-cell.diag { font-weight: 600; }

  .heatmap-scale {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    border-top: 1px solid var(--divider);
    font-size: 10px;
    color: var(--text-2);
  }
  .heatmap-scale .scale-end { font-variant-numeric: tabular-nums; }
  .scale-track {
    display: flex;
    flex: 0 1 220px;
    height: 8px;
    border: 1px solid var(--divider);
  }
  .scale-step { flex: 1; }
  .scale-note { margin-left: auto; color: var(--text-2); }

  /* ── Stress compare ── */
  .stress-compare {
    display: grid;
    gap: 0.5rem;
    padding: 0.7rem 0.75rem;
  }
  .sc-row {
    display: grid;
    grid-template-columns: 4.2rem minmax(0, 1fr) 3rem;
    align-items: center;
    gap: 0.65rem;
  }
  .sc-lbl {
    color: var(--text-2);
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .sc-track {
    height: 0.6rem;
    background: rgba(39, 53, 68, 0.8);
    overflow: hidden;
  }
  .sc-fill { height: 100%; transition: width 200ms ease; }
  .sc-val {
    color: var(--text-0);
    font-size: 13px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .sc-delta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 0.45rem;
    border-top: 1px solid var(--divider);
    font-size: 11px;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .sc-delta strong {
    font-variant-numeric: tabular-nums;
    font-size: 12.5px;
    font-weight: 600;
    text-transform: none;
  }

  /* ── Frontier chart ── */
  .frontier {
    min-height: 320px;
    position: relative;
    overflow: hidden;
  }
  .frontier > svg {
    display: block;
    width: 100%;
    height: 100%;
  }
  .frontier-label-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  .grid {
    stroke: var(--divider);
    stroke-opacity: 0.36;
    stroke-width: 1;
    shape-rendering: crispEdges;
  }
  .axis {
    stroke: var(--divider);
    stroke-width: 1;
    shape-rendering: crispEdges;
  }
  .frontier-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 2.2;
    opacity: 0.96;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .universe-frontier-line {
    fill: none;
    stroke: var(--chart-secondary);
    stroke-width: 1.35;
    stroke-dasharray: 5 4;
    display: none;
  }
  .cached-equity-frontier-line {
    fill: none;
    stroke: var(--text-2);
    stroke-width: 1.1;
    stroke-dasharray: 3 4;
    opacity: 0.42;
  }
  .cml-line {
    fill: none;
    stroke: var(--positive);
    stroke-width: 1.1;
    stroke-dasharray: 4 5;
    opacity: 0.55;
  }
  .zero-return-line {
    stroke: var(--text-2);
    stroke-width: 1;
    stroke-dasharray: 2 4;
    opacity: 0.35;
    shape-rendering: crispEdges;
  }
  .frontier-dot {
    fill: var(--chart-primary);
    fill-opacity: 0.85;
    stroke: var(--bg-0);
    stroke-width: 1;
    cursor: pointer;
    transition: r 120ms ease, fill-opacity 120ms ease;
  }
  .frontier-dot.hovered { fill-opacity: 1; }
  .frontier-marker-dot {
    fill: var(--bg-0);
    stroke-width: 2;
    cursor: pointer;
    transition: r 120ms ease;
  }
  .frontier-marker-dot.candidate { stroke: var(--chart-primary); fill: var(--chart-primary); stroke-width: 1.2; }
  .frontier-marker-dot.current { stroke: var(--chart-secondary); fill: var(--chart-secondary); }
  .frontier-marker-dot.asset { stroke: var(--chart-primary); fill: var(--chart-primary); stroke-width: 1.2; opacity: 0.72; }
  .frontier-marker-dot.universe_asset { display: none; }
  .frontier-marker-dot.universe_candidate { display: none; }
  .frontier-marker-dot.cached_equity_asset { cursor: pointer; }
  .frontier-marker-dot.special-frontier { fill: var(--bg-0); stroke: var(--chart-primary); stroke-width: 2; }
  .frontier-marker-dot.special-frontier.max-sharpe { stroke: var(--positive); }
  .frontier-marker-dot.cached_equity_candidate { display: none; }
  .frontier-marker-dot.risk_free { stroke: var(--positive); fill: var(--positive); }
  .frontier-label {
    position: absolute;
    padding: 0.1rem 0.3rem;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    transform: translate(-50%, -100%);
    white-space: nowrap;
    pointer-events: none;
    background: var(--bg-1);
    border: 1px solid var(--divider);
  }
  .frontier-label.current { color: var(--chart-secondary); border-color: rgba(196, 154, 90, 0.4); }
  .frontier-label.candidate { color: var(--chart-primary); border-color: rgba(122, 166, 200, 0.4); }
  .frontier-label.universe_candidate { color: var(--positive); border-color: rgba(75, 180, 116, 0.4); }
  .frontier-label.cached_equity_candidate { color: var(--text-1); border-color: var(--divider); }
  .frontier-label.risk_free { color: var(--positive); border-color: rgba(75, 180, 116, 0.4); }
  .frontier-label.cached_equity_frontier { color: var(--chart-primary); border-color: rgba(122, 166, 200, 0.4); }

  .frontier-tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--surface-2);
    border: 1px solid var(--panel-strong);
    padding: 0.4rem 0.55rem;
    display: grid;
    gap: 0.15rem;
    min-width: 150px;
    font-size: 11px;
    z-index: 2;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
  }
  .frontier-tooltip strong { color: var(--text-0); font-size: 11.5px; font-weight: 600; }
  .frontier-tooltip span { color: var(--text-1); display: flex; justify-content: space-between; gap: 0.75rem; }
  .frontier-tooltip em { color: var(--text-2); font-style: normal; text-transform: uppercase; font-size: 9.5px; letter-spacing: 0.08em; }

  .axis-label {
    position: absolute;
    color: var(--text-2);
    font-size: 10px;
    pointer-events: none;
  }
  .axis-label.x-min { left: 38px; bottom: 8px; }
  .axis-label.x-max { right: 14px; bottom: 8px; }
  .axis-label.y-min { left: 4px; bottom: 28px; }
  .axis-label.y-max { left: 4px; top: 8px; }
  .frontier-empty {
    min-height: 320px;
    display: grid;
    place-items: center;
    color: var(--text-2);
    font-size: 11px;
    text-align: center;
    padding: 1rem;
  }

  /* Padding inside RankPanel (BarRankChart sits inside .panel default padding) */
  :global(.panel.rank-panel) { padding: 0; }
  :global(.panel.rank-panel) > :global(.chart) { padding: 0.5rem 0.75rem; }

  @media (max-width: 1220px) {
    .workspace-grid, .two-col { grid-template-columns: 1fr; }
    .mode-kpi-row { flex-wrap: wrap; gap: 0.5rem; }
    .header-kpis { border-left: 0; padding-top: 0.3rem; border-top: 1px solid var(--divider); flex: 1 1 100%; }
  }

  @media (max-width: 760px) {
    .mode-bar { display: grid; grid-template-columns: repeat(3, 1fr); width: 100%; }
    .mode-bar button:nth-child(3) { border-right: 0; }
    .mode-bar button:nth-child(-n + 3) { border-bottom: 1px solid var(--panel-strong); }
    .control, input, select { width: 100%; }
    .actions { margin-left: 0; border-left: 0; padding-left: 0; flex: 1 1 100%; }
  }
</style>
