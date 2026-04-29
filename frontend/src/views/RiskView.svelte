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
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

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
      invertFilledArea: true,
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
      label: item.display_symbol ?? item.symbol,
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

  const signTone = (value: number | null | undefined): string =>
    value == null || value === 0 ? "" : value > 0 ? "positive" : "negative";
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel method-panel monte-carlo-panel">
        <header class="panel-bar">
          <h2>Monte Carlo · Scenario Envelope</h2>
          <button class="action-btn" on:click={() => submit("monteCarlo")} disabled={loading || !activeSnapshot}>
            {loading && activeComputeMethod === "monteCarlo" ? "Running…" : "Run Monte Carlo"}
          </button>
        </header>

        <div class="kpi-grid mc-kpi-grid">
          <article class="metric">
            <span>MC VaR</span>
            <strong>{fmt(result?.metrics.monte_carlo_var)}</strong>
            <small>Total {fmt(result?.metrics.monte_carlo_var_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>MC CVaR</span>
            <strong>{fmt(result?.metrics.monte_carlo_cvar)}</strong>
            <small>Total {fmt(result?.metrics.monte_carlo_cvar_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Model</span>
            <strong>{result?.metrics.monte_carlo_model ?? mcSimulationModel}</strong>
            <small>{fmt(result?.metrics.monte_carlo_num_simulations ?? mcNumSimulations, 0)} sims</small>
          </article>
          <article class="metric">
            <span>Horizon</span>
            <strong>{result?.metrics.monte_carlo_horizon_days ?? mcHorizonDays}D</strong>
            <small>{pct(result?.metrics.risk_coverage_ratio)} coverage</small>
          </article>
        </div>

        <div class="mc-grid">
          <section class="subsection fan-subsection">
            <header class="section-bar">Monte Carlo Fan · {result?.metrics.monte_carlo_horizon_days ?? mcHorizonDays}D</header>
            <FanChart
              series={result?.monte_carlo.fan_percentiles ?? {}}
              history={fanHistory}
              samplePaths={result?.monte_carlo.sample_paths ?? {}}
              height={280}
              emptyMessage="Monte Carlo fan chart unavailable"
            />
          </section>

          <section class="subsection">
            <header class="section-bar">Terminal Distribution · {result?.metrics.monte_carlo_model ?? mcSimulationModel}</header>
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
        <header class="panel-bar">
          <h2>Core VaR Deck</h2>
          <div class="header-actions">
            <label class="inline-field">
              <span>Chart</span>
              <select bind:value={chartMode}>
                {#each Object.entries(chartModeLabels) as [value, label]}
                  <option value={value}>{label}</option>
                {/each}
              </select>
            </label>
            <button class="action-btn" on:click={() => submit("core")} disabled={loading || !activeSnapshot}>
              {loading && activeComputeMethod === "core" ? "Computing…" : "Compute Core VaR"}
            </button>
          </div>
        </header>

        <div class="kpi-grid">
          <article class="metric">
            <span>Hist VaR</span>
            <strong>{fmt(result?.metrics.historical_var)}</strong>
            <small>{pct(result?.metrics.risk_coverage_ratio)} coverage</small>
          </article>
          <article class="metric">
            <span>Hist CVaR</span>
            <strong>{fmt(result?.metrics.historical_cvar)}</strong>
            <small>Total {fmt(result?.metrics.historical_cvar_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Param VaR</span>
            <strong>{fmt(result?.metrics.parametric_var)}</strong>
            <small>Total {fmt(result?.metrics.parametric_var_total_estimate)}</small>
          </article>
          <article class="metric">
            <span>Annual Vol</span>
            <strong>{pct(result?.metrics.annual_vol)}</strong>
            <small>Daily {pct(result?.metrics.daily_vol)}</small>
          </article>
          <article class="metric">
            <span>Beta / Corr</span>
            <strong class:elevated={(result?.metrics.beta ?? 0) > 1.2}>{fmt(result?.metrics.beta, 3)} / {fmt(result?.metrics.correlation, 3)}</strong>
            <small>{result?.metrics.benchmark_overlap_count ?? 0} overlap</small>
          </article>
          <article class="metric">
            <span>Jensen Alpha</span>
            <strong class={signTone(result?.metrics.alpha_annual)}>{pct(result?.metrics.alpha_annual)}</strong>
            <small>{lookbackDays}D / {betaWindow}D</small>
          </article>
        </div>

        <div class="method-grid">
          <div class="chart-column">
            <TimeSeriesChart series={chartSeries} height={360} emptyMessage={chartEmptyMessage(chartMode)} />
            <div class="chart-foot">
              <span>{chartModeLabels[chartMode]}</span>
              <strong>{benchmarkAvailable ? benchmarkSymbol.trim().toUpperCase() || "SPY" : "No benchmark"}</strong>
            </div>
          </div>

          <div class="method-side">
            <section class="subsection">
              <header class="section-bar">Coverage</header>
              <div class="stack">
                <div class="row"><span>Portfolio Value</span><strong>{fmt(result?.metrics.portfolio_value)}</strong></div>
                <div class="row"><span>Modeled Value</span><strong>{fmt(result?.metrics.covered_portfolio_value)}</strong></div>
                <div class="row"><span>Risk Basis</span><strong>{fmt(result?.metrics.risk_basis_value)}</strong></div>
                <div class="row"><span>Coverage Ratio</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></div>
                <div class="row"><span>Aligned Obs</span><strong>{result?.metrics.aligned_obs_count ?? 0}</strong></div>
                <div class="row"><span>Max Drawdown</span><strong class:negative={(result?.metrics.max_drawdown ?? 0) < 0}>{pct(result?.metrics.max_drawdown)}</strong></div>
              </div>
            </section>

            <section class="subsection">
              <header class="section-bar">Benchmark · {benchmarkSymbol.trim().toUpperCase() || "SPY"}</header>
              <div class="stack">
                <div class="row"><span>Overlap</span><strong>{result?.metrics.benchmark_overlap_count ?? 0}</strong></div>
                <div class="row"><span>Beta Window</span><strong>{betaWindow}D</strong></div>
                <div class="row"><span>Beta</span><strong class:elevated={(result?.metrics.beta ?? 0) > 1.2}>{fmt(result?.metrics.beta, 3)}</strong></div>
                <div class="row"><span>Correlation</span><strong>{fmt(result?.metrics.correlation, 3)}</strong></div>
                <div class="row"><span>Annual Alpha</span><strong class={signTone(result?.metrics.alpha_annual)}>{pct(result?.metrics.alpha_annual)}</strong></div>
              </div>
            </section>
          </div>
        </div>

        <div class="detail-split">
          <section class="subsection">
            <header class="section-bar">Return Distribution</header>
            <DistributionChart
              values={realizedReturns}
              markers={realizedMarkers}
              height={240}
              emptyMessage="Historical return distribution unavailable"
            />
          </section>

          <section class="subsection">
            <header class="section-bar">Contribution Rank</header>
            <BarRankChart
              items={contributionItems}
              emptyMessage="Contribution ranking will appear after core risk"
              formatValue={(value) => pct(value)}
            />
          </section>
        </div>
      </article>

      <article class="panel table-panel">
        <header class="table-panel-header">
          <span>Contribution Detail</span>
          <span class="row-count">{result?.contributions?.length ?? 0} rows</span>
        </header>
        <table>
          <thead>
            <tr><th>Symbol</th><th class="num">Weight</th><th class="num">Vol</th><th class="num">Var %</th><th class="num">MCTR</th><th class="num">Component VaR</th></tr>
          </thead>
          <tbody>
            {#if result?.contributions?.length}
              {#each result.contributions as contribution}
                <tr>
                  <td>{contribution.display_symbol ?? contribution.symbol}</td>
                  <td class="num">{pct(contribution.weight)}</td>
                  <td class="num">{pct(contribution.daily_vol)}</td>
                  <td class="num {signTone(contribution.variance_contribution_pct)}">{pct(contribution.variance_contribution_pct)}</td>
                  <td class="num">{fmt(contribution.marginal_contribution_to_risk, 6)}</td>
                  <td class="num">{fmt(contribution.component_var)}</td>
                </tr>
              {/each}
            {:else}
              <tr><td colspan="6" class="empty">No contribution data yet.</td></tr>
            {/if}
          </tbody>
        </table>
      </article>
    </div>

    <aside class="support-column">
      <article class="panel control-panel">
        <header class="rail-bar">
          <h3>Risk Inputs</h3>
          <span class="rail-context">{mode === "portfolio" ? "Portfolio" : "Research"}</span>
        </header>

        <div class="control-section">
          <small class="group-label">Monte Carlo</small>
          <div class="field-grid mc-fields">
            <label>
              <span>Horizon</span>
              <select bind:value={mcHorizonDays}>
                <option value={5}>5D</option>
                <option value={10}>10D</option>
                <option value={21}>21D</option>
                <option value={63}>63D</option>
              </select>
            </label>
            <label>
              <span>Model</span>
              <select bind:value={mcSimulationModel}>
                <option value="Gaussian">Gaussian</option>
                <option value="Bootstrap">Bootstrap</option>
              </select>
            </label>
            <label>
              <span>Sims</span>
              <select bind:value={mcNumSimulations}>
                <option value={1000}>1,000</option>
                <option value={2000}>2,000</option>
                <option value={5000}>5,000</option>
              </select>
            </label>
          </div>
        </div>

        <div class="control-section">
          <small class="group-label">Core</small>
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
        <header class="rail-bar">
          <h3>Coverage &amp; Concentration</h3>
        </header>
        <div class="stack">
          <div class="row"><span>Snapshot Lines</span><strong>{activeSnapshot?.positions.length ?? 0}</strong></div>
          <div class="row"><span>Portfolio Value</span><strong>{fmt(result?.metrics.portfolio_value)}</strong></div>
          <div class="row"><span>Modeled Value</span><strong>{fmt(result?.metrics.covered_portfolio_value)}</strong></div>
          <div class="row"><span>Risk Basis</span><strong>{fmt(result?.metrics.risk_basis_value)}</strong></div>
          <div class="row"><span>Coverage Ratio</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></div>
          <div class="row"><span>HHI / Top-5</span><strong>{fmt(result?.metrics.concentration_hhi, 3)} / {pct(result?.metrics.top5_weight)}</strong></div>
          <div class="row"><span>Effective Bets</span><strong>{fmt(result?.metrics.effective_bets, 2)}</strong></div>
          <div class="row"><span>Excluded Assets</span><strong class:warning={excludedAssets.length > 0}>{excludedAssets.length}</strong></div>
        </div>
      </article>

      <article class="panel rail-panel">
        <header class="rail-bar">
          <h3>Warnings &amp; Exclusions</h3>
        </header>

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
                <span class="note-tag">{asset.display_symbol ?? asset.symbol}</span>
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
    gap: 0.5rem;
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
    background: var(--panel-bg);
    padding: 0.65rem 0.85rem;
  }

  .method-panel,
  .control-panel,
  .rail-panel {
    display: grid;
    gap: 0.55rem;
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
    display: grid;
    gap: 0;
  }

  /* ── Single-line panel + section headers ── */
  .panel-bar,
  .rail-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    min-height: 26px;
  }

  .panel-bar h2 {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-0);
    letter-spacing: 0.02em;
  }

  .rail-bar h3 {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-0);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .rail-context {
    color: var(--text-2);
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .section-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    color: var(--text-2);
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--divider);
    min-height: 22px;
  }

  .table-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3rem 0.75rem;
    min-height: 26px;
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .table-panel-header .row-count {
    color: var(--text-2);
    text-transform: none;
    letter-spacing: 0;
    font-weight: 400;
  }

  .row,
  .chart-foot {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: center;
  }

  .header-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: end;
    gap: 0.5rem;
    align-items: center;
  }

  .inline-field {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
  }

  .inline-field > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10.5px;
  }

  label {
    display: grid;
    gap: 0.3rem;
  }

  /* ── KPI strip ── */
  .kpi-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
  }

  .mc-kpi-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .metric {
    padding: 0.2rem 0.85rem;
    border-left: 1px solid var(--divider);
    background: none;
    min-width: 0;
    text-align: center;
  }

  .metric span {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-2);
  }

  .metric strong {
    display: block;
    margin: 0.12rem 0 0.14rem;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--text-0);
  }

  .metric small {
    font-size: 10.5px;
    color: var(--text-2);
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

  .chart-column,
  .method-side,
  .control-section {
    display: grid;
    gap: 0.55rem;
  }

  .subsection {
    display: grid;
    gap: 0.45rem;
  }

  .method-side > .subsection + .subsection {
    margin-top: 0.25rem;
  }

  .row {
    border-top: 1px solid var(--divider);
    padding-top: 0.4rem;
    font-size: 12.5px;
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .row span {
    color: var(--text-2);
  }

  .row strong {
    color: var(--text-0);
  }

  .chart-foot {
    border-top: 1px solid var(--divider);
    padding-top: 0.4rem;
    font-size: 11px;
  }

  .chart-foot span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .chart-foot strong {
    color: var(--text-0);
  }

  .control-section + .control-section {
    border-top: 1px solid var(--divider);
    padding-top: 0.5rem;
  }

  .core-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mc-fields {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .note-row {
    display: grid;
    grid-template-columns: 5.5rem minmax(0, 1fr);
    gap: 0.6rem;
    padding: 0.4rem 0;
    border-top: 1px solid var(--divider);
    font-size: 11.5px;
    line-height: 1.35;
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10px;
    font-weight: 600;
  }

  .note-row.info .note-tag,
  .note-row.info p {
    color: var(--accent);
  }

  .note-row.accent .note-tag,
  .note-row.accent p {
    color: var(--accent-2);
  }

  /* ── Table ── */
  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.32rem 0.5rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    font-size: 12px;
  }

  th {
    color: var(--text-2);
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: transparent;
    font-weight: 600;
  }

  td.num,
  th.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  td.empty {
    color: var(--text-2);
    text-align: center;
    padding: 0.6rem;
  }

  tbody tr:hover {
    background: rgba(122, 166, 200, 0.06);
  }

  /* ── Inputs / buttons ── */
  input,
  select {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 4px 8px;
    height: 28px;
    font: inherit;
    font-size: 12.5px;
  }

  input:focus,
  select:focus {
    outline: none;
    border-color: var(--accent);
  }

  .action-btn {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 4px 12px;
    height: 28px;
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    border-radius: 2px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .action-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  h2,
  h3,
  p,
  small {
    margin: 0;
  }

  .muted {
    color: var(--text-2);
    font-size: 12px;
    padding: 0.25rem 0;
  }

  .group-label,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 10.5px;
    font-weight: 600;
  }

  .note-row p {
    overflow-wrap: anywhere;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .warning {
    color: var(--warning);
  }

  .elevated {
    color: var(--warning);
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
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 980px) {
    .support-column,
    .core-fields,
    .mc-fields {
      grid-template-columns: 1fr;
    }

    .kpi-grid,
    .mc-kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .metric {
      padding: 0.4rem 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      text-align: left;
    }

    .metric:first-child {
      border-top: 0;
    }

    .panel-bar,
    .rail-bar,
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
      gap: 0.4rem;
    }

    .header-actions {
      justify-content: stretch;
    }

    .header-actions > * {
      width: 100%;
    }

    .note-row {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
  }
</style>
