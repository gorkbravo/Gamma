<script lang="ts">
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import DistributionChart, { type DistributionMarker } from "../components/DistributionChart.svelte";
  import FanChart from "../components/FanChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type { IndexedValuePoint, PortfolioSnapshot, RiskResult, TimeSeriesPoint, WorkspaceMode } from "../lib/api/types";
  import type { RiskComputeOptions } from "../lib/stores/app";

  export let mode: WorkspaceMode = "portfolio";
  export let snapshot: PortfolioSnapshot | null = null;
  export let researchSnapshot: PortfolioSnapshot | null = null;
  export let result: RiskResult | null = null;
  export let loading = false;
  export let onCompute: (options: RiskComputeOptions) => Promise<void> | void;

  type ChartMode = "drawdown" | "cumulative" | "rolling_vol" | "rolling_beta" | "rolling_corr";
  type ComputeMethod = "core" | "monteCarlo";

  const chartModeLabels: Record<ChartMode, string> = {
    drawdown: "Drawdown",
    cumulative: "Cumulative",
    rolling_vol: "Rolling Vol",
    rolling_beta: "Rolling Beta",
    rolling_corr: "Rolling Corr"
  };

  let benchmarkSymbol = "SPY";
  let confidence = 0.95;
  let lookbackDays = 252;
  let horizonDays = 1;
  let mcHorizonDays = 10;
  let mcSimulationModel = "Gaussian";
  let mcNumSimulations = 2000;
  let betaWindow = 126;
  let chartMode: ChartMode = "drawdown";
  let activeComputeMethod: ComputeMethod | null = null;

  let activeSnapshot: PortfolioSnapshot | null = snapshot;
  let chartSeries: ChartSeries[] = [];
  let realizedReturns: number[] = [];
  let realizedMarkers: DistributionMarker[] = [];
  let monteCarloMarkers: DistributionMarker[] = [];
  let contributionItems: RankBarItem[] = [];
  let fanHistory: IndexedValuePoint[] = [];
  let benchmarkAvailable = false;
  let excludedAssets = result?.excluded_assets ?? [];
  let benchmarkWarnings: string[] = [];
  let monteCarloWarnings: string[] = [];
  let generalWarnings: string[] = [];

  $: activeSnapshot = mode === "research" ? researchSnapshot : snapshot;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  function cumulativeFromReturns(points: TimeSeriesPoint[]) {
    let cumulative = 1;
    return points.map((point) => {
      cumulative *= 1 + point.value;
      return {
        time: Math.floor(new Date(point.timestamp).getTime() / 1000),
        value: cumulative
      };
    });
  }

  function rollingStd(points: TimeSeriesPoint[], window = 21) {
    return points
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = points.slice(index + 1 - window, index + 1).map((item) => item.value);
        const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
        const variance = slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(slice.length - 1, 1);
        return {
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: Math.sqrt(variance) * Math.sqrt(252)
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function rollingBetaLike(
    perfPoints: TimeSeriesPoint[],
    benchmarkPoints: TimeSeriesPoint[],
    modeId: "beta" | "corr",
    window: number
  ) {
    const benchmarkByTs = new Map(benchmarkPoints.map((point) => [new Date(point.timestamp).getTime(), point.value]));
    const aligned = perfPoints
      .map((point) => {
        const ts = new Date(point.timestamp).getTime();
        const benchmark = benchmarkByTs.get(ts);
        if (benchmark == null) {
          return null;
        }
        return { ts, perf: point.value, benchmark };
      })
      .filter((point): point is { ts: number; perf: number; benchmark: number } => point !== null);

    return aligned
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = aligned.slice(index + 1 - window, index + 1);
        const perfMean = slice.reduce((sum, item) => sum + item.perf, 0) / slice.length;
        const benchmarkMean = slice.reduce((sum, item) => sum + item.benchmark, 0) / slice.length;
        const covariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) * (item.benchmark - benchmarkMean), 0) /
          Math.max(slice.length - 1, 1);
        const perfVariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) ** 2, 0) / Math.max(slice.length - 1, 1);
        const benchmarkVariance =
          slice.reduce((sum, item) => sum + (item.benchmark - benchmarkMean) ** 2, 0) /
          Math.max(slice.length - 1, 1);
        if (benchmarkVariance <= 0) {
          return null;
        }
        const value =
          modeId === "beta"
            ? covariance / benchmarkVariance
            : covariance / Math.sqrt(Math.max(perfVariance, 0) * benchmarkVariance || 1);
        return {
          time: Math.floor(point.ts / 1000),
          value
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

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

  function riskBaseValue() {
    const covered = result?.metrics.covered_portfolio_value ?? null;
    const total = result?.metrics.portfolio_value ?? null;
    if (covered && covered > 0) {
      return covered;
    }
    if (total && total > 0) {
      return total;
    }
    return null;
  }

  function chartEmptyMessage(modeId: ChartMode) {
    if (!result?.portfolio_return_points?.length) {
      return "Run a core risk pass to populate the interactive chart deck";
    }
    if (modeId === "rolling_beta" || modeId === "rolling_corr") {
      return benchmarkAvailable
        ? `Need at least ${betaWindow} aligned observations for the selected benchmark window`
        : "Benchmark return history is unavailable for rolling beta/correlation";
    }
    if (modeId === "rolling_vol") {
      return "Need enough aligned return history for rolling volatility";
    }
    return "No chart data available";
  }

  $: benchmarkAvailable = Boolean(result?.benchmark_return_points?.length);

  $: chartSeries = (() => {
    const perf = result?.portfolio_return_points ?? [];
    const benchmark = result?.benchmark_return_points ?? [];
    if (!perf.length) {
      return [];
    }
    if (chartMode === "cumulative") {
      return [{ id: "cumulative", label: "Cumulative", color: "#7aa6c8", type: "line", data: cumulativeFromReturns(perf) }];
    }
    if (chartMode === "rolling_vol") {
      const volSeries = rollingStd(perf);
      return volSeries.length
        ? [{ id: "rolling_vol", label: "Rolling Vol", color: "#9bd19f", type: "line", data: volSeries }]
        : [];
    }
    if (chartMode === "rolling_beta" || chartMode === "rolling_corr") {
      const derived = rollingBetaLike(perf, benchmark, chartMode === "rolling_beta" ? "beta" : "corr", betaWindow);
      return derived.length
        ? [{
            id: chartMode,
            label: chartMode === "rolling_beta" ? "Rolling Beta" : "Rolling Corr",
            color: chartMode === "rolling_beta" ? "#c49a5a" : "#d8c17a",
            type: "line",
            data: derived
          }]
        : [];
    }

    let cumulative = 1;
    let peak = 1;
    return [{
      id: "drawdown",
      label: "Drawdown",
      color: "#d1645d",
      type: "area",
      data: perf.map((point) => {
        cumulative *= 1 + point.value;
        peak = Math.max(peak, cumulative);
        return {
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: cumulative / peak - 1
        };
      })
    }];
  })();

  $: realizedReturns = result?.portfolio_return_points?.map((point) => point.value) ?? [];

  $: realizedMarkers = (() => {
    const base = riskBaseValue();
    if (!base) {
      return [];
    }
    return [
      { label: "Hist VaR", value: result?.metrics.historical_var == null ? null : -result.metrics.historical_var / base, color: "#d1645d" },
      { label: "Hist CVaR", value: result?.metrics.historical_cvar == null ? null : -result.metrics.historical_cvar / base, color: "#ff8a65" },
      { label: "Param VaR", value: result?.metrics.parametric_var == null ? null : -result.metrics.parametric_var / base, color: "#c49a5a" }
    ];
  })();

  $: monteCarloMarkers = (() => {
    const base = riskBaseValue();
    if (!base) {
      return [];
    }
    return [
      { label: "MC VaR", value: result?.metrics.monte_carlo_var == null ? null : -result.metrics.monte_carlo_var / base, color: "#6aa8ff" },
      { label: "MC CVaR", value: result?.metrics.monte_carlo_cvar == null ? null : -result.metrics.monte_carlo_cvar / base, color: "#ff6760" }
    ];
  })();

  $: contributionItems = (result?.contributions ?? [])
    .filter((item) => Math.abs(item.variance_contribution_pct ?? 0) > 1e-4)
    .slice(0, 6)
    .map((item) => ({
      label: item.symbol,
      value: item.variance_contribution_pct ?? 0,
      tone: (item.variance_contribution_pct ?? 0) < 0 ? "negative" : "positive",
      meta: `${pct(item.weight)} wt | ${fmt(item.component_var)} Comp VaR`
    }));

  $: fanHistory = (() => {
    const perf = result?.portfolio_return_points ?? [];
    if (perf.length < 2) {
      return [];
    }
    const recent = perf.slice(-40);
    let cumulative = 1;
    const points = recent.map((point, index) => {
      cumulative *= 1 + point.value;
      return {
        index: index - recent.length + 1,
        value: cumulative
      };
    });
    const terminal = points.at(-1)?.value ?? 1;
    return points.map((point) => ({
      index: point.index,
      value: terminal !== 0 ? point.value / terminal : point.value
    }));
  })();

  $: excludedAssets = result?.excluded_assets ?? [];

  $: {
    const warnings = result?.warnings ?? [];
    benchmarkWarnings = warnings.filter((warning) => warning.toLowerCase().includes("benchmark"));
    monteCarloWarnings = warnings.filter((warning) => warning.toLowerCase().includes("monte carlo"));
    generalWarnings = warnings.filter(
      (warning) => !warning.toLowerCase().includes("benchmark") && !warning.toLowerCase().includes("monte carlo")
    );
  }
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel method-panel monte-carlo-panel">
        <div class="panel-header top-line">
          <div>
            <p class="eyebrow">Monte Carlo</p>
            <h2>Scenario Envelope</h2>
          </div>
          <button on:click={() => submit("monteCarlo")} disabled={loading || !activeSnapshot}>
            {loading && activeComputeMethod === "monteCarlo" ? "Running Monte Carlo..." : "Run Monte Carlo"}
          </button>
        </div>

        <div class="kpi-grid mc-kpi-grid">
          <article class="metric">
            <span>MC VaR</span>
            <strong>{fmt(result?.metrics.monte_carlo_var)}</strong>
            <small>Total est. {fmt(result?.metrics.monte_carlo_var_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>MC CVaR</span>
            <strong>{fmt(result?.metrics.monte_carlo_cvar)}</strong>
            <small>Total est. {fmt(result?.metrics.monte_carlo_cvar_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Model</span>
            <strong>{result?.metrics.monte_carlo_model ?? mcSimulationModel}</strong>
            <small>{fmt(result?.metrics.monte_carlo_num_simulations ?? mcNumSimulations, 0)} sims</small>
          </article>
          <article class="metric">
            <span>Horizon</span>
            <strong>{result?.metrics.monte_carlo_horizon_days ?? mcHorizonDays}D</strong>
            <small>{pct(result?.metrics.risk_coverage_ratio)} covered base</small>
          </article>
        </div>

        <div class="mc-grid">
          <section class="subsection fan-subsection">
            <div class="section-head">
              <h3>Monte Carlo Fan</h3>
              <small>{result?.metrics.monte_carlo_horizon_days ?? mcHorizonDays}D percentile path projection</small>
            </div>
            <FanChart
              series={result?.monte_carlo.fan_percentiles ?? {}}
              history={fanHistory}
              samplePaths={result?.monte_carlo.sample_paths ?? {}}
              height={280}
              emptyMessage="Monte Carlo fan chart unavailable"
            />
          </section>

          <section class="subsection">
            <div class="section-head">
              <h3>Terminal Distribution</h3>
              <small>{result?.metrics.monte_carlo_model ?? mcSimulationModel} terminal returns</small>
            </div>
            <DistributionChart
              values={result?.monte_carlo.terminal_returns ?? []}
              markers={monteCarloMarkers}
              height={280}
              emptyMessage="Monte Carlo distribution unavailable"
            />
          </section>
        </div>
      </article>

      <article class="panel method-panel core-panel">
        <div class="panel-header top-line">
          <div>
            <p class="eyebrow">Historical / Parametric</p>
            <h2>Core VaR Deck</h2>
          </div>
          <div class="header-actions">
            <label class="inline-field">
              <span>Chart</span>
              <select bind:value={chartMode}>
                {#each Object.entries(chartModeLabels) as [value, label]}
                  <option value={value}>{label}</option>
                {/each}
              </select>
            </label>
            <button on:click={() => submit("core")} disabled={loading || !activeSnapshot}>
              {loading && activeComputeMethod === "core" ? "Computing Core..." : "Compute Core VaR"}
            </button>
          </div>
        </div>

        <div class="kpi-grid">
          <article class="metric">
            <span>Hist VaR</span>
            <strong>{fmt(result?.metrics.historical_var)}</strong>
            <small>{pct(result?.metrics.risk_coverage_ratio)} coverage</small>
          </article>
          <article class="metric">
            <span>Hist CVaR</span>
            <strong>{fmt(result?.metrics.historical_cvar)}</strong>
            <small>Total est. {fmt(result?.metrics.historical_cvar_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Param VaR</span>
            <strong>{fmt(result?.metrics.parametric_var)}</strong>
            <small>Total est. {fmt(result?.metrics.parametric_var_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Annual Vol</span>
            <strong>{pct(result?.metrics.annual_vol)}</strong>
            <small>Daily {pct(result?.metrics.daily_vol)}</small>
          </article>
          <article class="metric">
            <span>Beta / Corr</span>
            <strong>{fmt(result?.metrics.beta, 3)} / {fmt(result?.metrics.correlation, 3)}</strong>
            <small>{result?.metrics.benchmark_overlap_count ?? 0} overlap obs</small>
          </article>
          <article class="metric">
            <span>Jensen Alpha</span>
            <strong>{pct(result?.metrics.alpha_annual)}</strong>
            <small>{lookbackDays}D lookback | {betaWindow}D window</small>
          </article>
        </div>

        <div class="method-grid">
          <div class="chart-column">
            <TimeSeriesChart series={chartSeries} height={360} emptyMessage={chartEmptyMessage(chartMode)} />
            <div class="chart-foot">
              <span>{chartModeLabels[chartMode]} on shared risk returns</span>
              <strong>{benchmarkAvailable ? benchmarkSymbol.trim().toUpperCase() || "SPY" : "No benchmark series"}</strong>
            </div>
          </div>

          <div class="method-side">
            <section class="subsection">
              <div class="section-head">
                <h3>Coverage</h3>
                <small>{activeSnapshot?.positions.length ?? 0} snapshot lines</small>
              </div>
              <div class="stack">
                <div class="row"><span>Portfolio Value</span><strong>{fmt(result?.metrics.portfolio_value)}</strong></div>
                <div class="row"><span>Covered Value</span><strong>{fmt(result?.metrics.covered_portfolio_value)}</strong></div>
                <div class="row"><span>Coverage Ratio</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></div>
                <div class="row"><span>Aligned Obs</span><strong>{result?.metrics.aligned_obs_count ?? 0}</strong></div>
                <div class="row"><span>Max Drawdown</span><strong class:negative={(result?.metrics.max_drawdown ?? 0) < 0}>{pct(result?.metrics.max_drawdown)}</strong></div>
              </div>
            </section>

            <section class="subsection">
              <div class="section-head">
                <h3>Benchmark Context</h3>
                <small>{benchmarkSymbol.trim().toUpperCase() || "SPY"}</small>
              </div>
              <div class="stack">
                <div class="row"><span>Overlap</span><strong>{result?.metrics.benchmark_overlap_count ?? 0}</strong></div>
                <div class="row"><span>Beta Window</span><strong>{betaWindow}D</strong></div>
                <div class="row"><span>Beta</span><strong>{fmt(result?.metrics.beta, 3)}</strong></div>
                <div class="row"><span>Correlation</span><strong>{fmt(result?.metrics.correlation, 3)}</strong></div>
                <div class="row"><span>Annual Alpha</span><strong>{pct(result?.metrics.alpha_annual)}</strong></div>
              </div>
            </section>
          </div>
        </div>

        <div class="detail-split">
          <section class="subsection">
            <div class="section-head">
              <h3>Return Distribution</h3>
              <small>Historical return stack with VaR markers</small>
            </div>
            <DistributionChart
              values={realizedReturns}
              markers={realizedMarkers}
              height={240}
              emptyMessage="Historical return distribution unavailable"
            />
          </section>

          <section class="subsection">
            <div class="section-head">
              <h3>Contribution Rank</h3>
              <small>Largest variance contributors</small>
            </div>
            <BarRankChart
              items={contributionItems}
              emptyMessage="Contribution ranking will appear after core risk"
              formatValue={(value) => pct(value)}
            />
          </section>
        </div>
      </article>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Attribution</p>
            <h3>Contribution Detail</h3>
          </div>
          <small>{result?.contributions?.length ?? 0} rows from the covered universe</small>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Symbol</th><th>Weight</th><th>Vol</th><th>Var %</th><th>MCTR</th><th>Component VaR</th></tr>
            </thead>
            <tbody>
              {#if result?.contributions?.length}
                {#each result.contributions as contribution}
                  <tr>
                    <td>{contribution.symbol}</td>
                    <td>{pct(contribution.weight)}</td>
                    <td>{pct(contribution.daily_vol)}</td>
                    <td>{pct(contribution.variance_contribution_pct)}</td>
                    <td>{fmt(contribution.marginal_contribution_to_risk, 6)}</td>
                    <td>{fmt(contribution.component_var)}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="6">No contribution data yet.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>

    <aside class="support-column">
      <article class="panel control-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Run Setup</p>
            <h3>Risk Inputs</h3>
          </div>
          <strong>{mode === "portfolio" ? "Portfolio Snapshot" : "Research Snapshot"}</strong>
        </div>

        <div class="control-section">
          <small class="group-label">Monte Carlo Inputs</small>
          <div class="field-grid mc-fields">
            <label>
              <span>MC Horizon</span>
              <select bind:value={mcHorizonDays}>
                <option value={5}>5D</option>
                <option value={10}>10D</option>
                <option value={21}>21D</option>
                <option value={63}>63D</option>
              </select>
            </label>
            <label>
              <span>MC Model</span>
              <select bind:value={mcSimulationModel}>
                <option value="Gaussian">Gaussian</option>
                <option value="Bootstrap">Bootstrap</option>
              </select>
            </label>
            <label>
              <span>MC Sims</span>
              <select bind:value={mcNumSimulations}>
                <option value={1000}>1,000</option>
                <option value={2000}>2,000</option>
                <option value={5000}>5,000</option>
              </select>
            </label>
          </div>
        </div>

        <div class="control-section">
          <small class="group-label">Core Inputs</small>
          <div class="field-grid core-fields">
            <label>
              <span>Benchmark</span>
              <input bind:value={benchmarkSymbol} placeholder="SPY" />
            </label>
            <label>
              <span>Confidence</span>
              <select bind:value={confidence}>
                <option value={0.9}>90%</option>
                <option value={0.95}>95%</option>
                <option value={0.99}>99%</option>
              </select>
            </label>
            <label>
              <span>Lookback</span>
              <select bind:value={lookbackDays}>
                <option value={126}>126D</option>
                <option value={252}>252D</option>
                <option value={504}>504D</option>
              </select>
            </label>
            <label>
              <span>Horizon</span>
              <select bind:value={horizonDays}>
                <option value={1}>1D</option>
                <option value={10}>10D</option>
                <option value={21}>21D</option>
              </select>
            </label>
            <label>
              <span>Beta Window</span>
              <select bind:value={betaWindow}>
                <option value={63}>63D</option>
                <option value={126}>126D</option>
                <option value={252}>252D</option>
              </select>
            </label>
          </div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Structure</p>
            <h3>Coverage &amp; Concentration</h3>
          </div>
        </div>
        <div class="stack">
          <div class="row"><span>Snapshot Lines</span><strong>{activeSnapshot?.positions.length ?? 0}</strong></div>
          <div class="row"><span>Portfolio Value</span><strong>{fmt(result?.metrics.portfolio_value)}</strong></div>
          <div class="row"><span>Covered Value</span><strong>{fmt(result?.metrics.covered_portfolio_value)}</strong></div>
          <div class="row"><span>Coverage Ratio</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></div>
          <div class="row"><span>HHI / Top-5</span><strong>{fmt(result?.metrics.concentration_hhi, 3)} / {pct(result?.metrics.top5_weight)}</strong></div>
          <div class="row"><span>Effective Bets</span><strong>{fmt(result?.metrics.effective_bets, 2)}</strong></div>
          <div class="row"><span>Excluded Assets</span><strong>{excludedAssets.length}</strong></div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Notes</p>
            <h3>Warnings &amp; Exclusions</h3>
          </div>
        </div>

        {#if benchmarkWarnings.length || generalWarnings.length || monteCarloWarnings.length || excludedAssets.length}
          <div class="notes-list">
            {#each generalWarnings as warning}
              <div class="note-row">
                <span class="note-tag">Risk</span>
                <p>{warning}</p>
              </div>
            {/each}
            {#each benchmarkWarnings as warning}
              <div class="note-row info">
                <span class="note-tag">Benchmark</span>
                <p>{warning}</p>
              </div>
            {/each}
            {#each monteCarloWarnings as warning}
              <div class="note-row accent">
                <span class="note-tag">MC</span>
                <p>{warning}</p>
              </div>
            {/each}
            {#each excludedAssets as asset}
              <div class="note-row">
                <span class="note-tag">{asset.symbol}</span>
                <p>{asset.reason}</p>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No active warnings or exclusions.</p>
        {/if}
      </article>
    </aside>
  </div>
</section>

<style>
  .view,
  .workspace-grid,
  .primary-column,
  .support-column,
  .kpi-grid,
  .method-grid,
  .detail-split,
  .mc-grid,
  .stack,
  .field-grid,
  .notes-list {
    display: grid;
    gap: 0.95rem;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.85fr) minmax(20rem, 0.9fr);
    align-items: start;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(9, 14, 20, 0.97), rgba(6, 10, 15, 0.95));
    padding: 1.05rem;
  }

  .method-panel,
  .control-panel,
  .rail-panel,
  .table-panel {
    display: grid;
    gap: 1rem;
  }

  .panel-header,
  .rail-header,
  .row,
  .chart-foot,
  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.85rem;
  }

  .top-line {
    align-items: start;
  }

  .header-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: end;
    gap: 0.75rem;
    align-items: end;
  }

  .inline-field,
  label {
    display: grid;
    gap: 0.4rem;
  }

  .inline-field {
    min-width: 10rem;
  }

  .kpi-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
    padding-block: 0.2rem;
  }

  .mc-kpi-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .metric {
    padding: 0.2rem 1rem;
    border-left: 1px solid rgba(46, 60, 74, 0.52);
    background: none;
    min-width: 0;
  }

  .metric strong {
    display: block;
    margin: 0.18rem 0 0.24rem;
    font-size: 1rem;
    line-height: 1.2;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .method-grid {
    grid-template-columns: minmax(0, 1.45fr) minmax(18rem, 0.8fr);
    align-items: start;
  }

  .detail-split,
  .mc-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .detail-split > .subsection,
  .mc-grid > .subsection {
    border-top: 0;
    padding-top: 0;
    align-content: start;
  }

  .chart-column,
  .method-side,
  .control-section {
    display: grid;
    gap: 0.85rem;
  }

  .subsection {
    display: grid;
    gap: 0.8rem;
    padding-top: 0.15rem;
  }

  .method-side > .subsection + .subsection {
    border-top: 1px solid rgba(46, 60, 74, 0.45);
    padding-top: 0.95rem;
  }

  .section-head {
    align-items: baseline;
  }

  .chart-foot,
  .row {
    align-items: center;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    padding-top: 0.72rem;
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .control-section + .control-section {
    border-top: 1px solid rgba(46, 60, 74, 0.45);
    padding-top: 0.95rem;
  }

  .core-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mc-fields {
    grid-template-columns: 1fr;
  }

  .note-row {
    display: grid;
    grid-template-columns: 5.75rem minmax(0, 1fr);
    gap: 0.8rem;
    padding: 0.72rem 0;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.64rem;
  }

  .note-row.info .note-tag,
  .note-row.info p {
    color: var(--accent);
  }

  .note-row.accent .note-tag,
  .note-row.accent p {
    color: var(--accent-2);
  }

  .table-wrap {
    overflow: auto;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.72rem 0.55rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    text-align: left;
    white-space: nowrap;
  }

  th {
    color: var(--text-2);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: rgba(8, 13, 18, 0.82);
  }

  input,
  select,
  button {
    border: 1px solid var(--panel-strong);
    background: #0b1219;
    color: var(--text-0);
    padding: 0.68rem 0.78rem;
    font: inherit;
  }

  button {
    cursor: pointer;
  }

  h2,
  h3,
  p,
  small {
    margin: 0;
  }

  span,
  small,
  .muted {
    color: var(--text-2);
  }

  strong {
    color: var(--text-0);
  }

  .eyebrow,
  .group-label,
  .inline-field > span,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  .muted,
  .row span,
  .row strong,
  .note-row p {
    overflow-wrap: anywhere;
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1220px) {
    .workspace-grid,
    .method-grid,
    .detail-split,
    .mc-grid {
      grid-template-columns: 1fr;
    }

    .support-column {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .kpi-grid,
    .mc-kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 980px) {
    .support-column,
    .core-fields {
      grid-template-columns: 1fr;
    }

    .kpi-grid,
    .mc-kpi-grid {
      grid-template-columns: 1fr;
    }

    .metric {
      padding: 0.7rem 0;
      border-left: 0;
    }

    .metric:first-child {
      padding-top: 0;
    }

    .panel-header,
    .rail-header,
    .section-head,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .header-actions {
      justify-content: stretch;
    }

    .header-actions > * {
      width: 100%;
    }

    .note-row {
      grid-template-columns: 1fr;
      gap: 0.35rem;
    }
  }
</style>
