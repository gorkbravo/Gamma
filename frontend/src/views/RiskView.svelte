<script lang="ts">
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import DistributionChart, { type DistributionMarker } from "../components/DistributionChart.svelte";
  import FanChart from "../components/FanChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type { PortfolioSnapshot, RiskResult, WorkspaceMode } from "../lib/api/types";
  import type { RiskComputeOptions } from "../lib/stores/app";

  export let mode: WorkspaceMode = "portfolio";
  export let snapshot: PortfolioSnapshot | null = null;
  export let researchSnapshot: PortfolioSnapshot | null = null;
  export let result: RiskResult | null = null;
  export let loading = false;
  export let onCompute: (options: RiskComputeOptions) => void;

  let benchmarkSymbol = "SPY";
  let confidence = 0.95;
  let lookbackDays = 252;
  let horizonDays = 1;
  let mcHorizonDays = 10;
  let mcSimulationModel = "Gaussian";
  let mcNumSimulations = 2000;
  let betaWindow = 126;
  let chartMode: "cumulative" | "drawdown" = "drawdown";

  let activeSnapshot: PortfolioSnapshot | null = snapshot;
  let chartSeries: ChartSeries[] = [];
  let realizedReturns: number[] = [];
  let realizedMarkers: DistributionMarker[] = [];
  let monteCarloMarkers: DistributionMarker[] = [];
  let contributionItems: RankBarItem[] = [];

  $: activeSnapshot =
    mode === "research"
      ? researchSnapshot
      : snapshot;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;

  function submit() {
    onCompute({
      snapshot: activeSnapshot,
      alpha: confidence,
      lookbackDays,
      horizonDays,
      mcHorizonDays,
      mcSimulationModel,
      mcNumSimulations,
      betaWindow,
      benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY"
    });
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

  $: chartSeries = (() => {
    if (!result?.portfolio_return_points?.length) {
      return [];
    }
    if (chartMode === "cumulative") {
      let cumulative = 1;
      return [
        {
          id: "cumulative",
          label: "Cumulative",
          color: "#6aa8ff",
          type: "line",
          data: result.portfolio_return_points.map((point) => {
            cumulative *= 1 + point.value;
            return {
              time: Math.floor(new Date(point.timestamp).getTime() / 1000),
              value: cumulative
            };
          })
        }
      ];
    }
    let cumulative = 1;
    let peak = 1;
    return [
      {
        id: "drawdown",
        label: "Drawdown",
        color: "#ff6760",
        type: "area",
        data: result.portfolio_return_points.map((point) => {
          cumulative *= 1 + point.value;
          peak = Math.max(peak, cumulative);
          return {
            time: Math.floor(new Date(point.timestamp).getTime() / 1000),
            value: cumulative / peak - 1
          };
        })
      }
    ];
  })();

  $: realizedReturns = result?.portfolio_return_points?.map((point) => point.value) ?? [];

  $: realizedMarkers = (() => {
    const base = riskBaseValue();
    if (!base) {
      return [];
    }
    return [
      {
        label: "Hist VaR",
        value: result?.metrics.historical_var == null ? null : -result.metrics.historical_var / base,
        color: "#ff8a65"
      },
      {
        label: "Hist CVaR",
        value: result?.metrics.historical_cvar == null ? null : -result.metrics.historical_cvar / base,
        color: "#ff6760"
      },
      {
        label: "Param VaR",
        value: result?.metrics.parametric_var == null ? null : -result.metrics.parametric_var / base,
        color: "#ffd166"
      }
    ];
  })();

  $: monteCarloMarkers = (() => {
    const base = riskBaseValue();
    if (!base) {
      return [];
    }
    return [
      {
        label: "MC VaR",
        value: result?.metrics.monte_carlo_var == null ? null : -result.metrics.monte_carlo_var / base,
        color: "#6aa8ff"
      },
      {
        label: "MC CVaR",
        value: result?.metrics.monte_carlo_cvar == null ? null : -result.metrics.monte_carlo_cvar / base,
        color: "#ff6760"
      }
    ];
  })();

  $: contributionItems = (result?.contributions ?? [])
    .filter((item) => item.variance_contribution_pct != null)
    .slice(0, 8)
    .map((item) => ({
      label: item.symbol,
      value: item.variance_contribution_pct ?? 0,
      tone: (item.variance_contribution_pct ?? 0) < 0 ? "negative" : "positive",
      meta: `${pct(item.weight)} wt | ${fmt(item.component_var)} Comp VaR`
    }));
</script>

<section class="view">
  <div class="toolbar">
    <div>
      <h2>Risk Command Deck</h2>
      <p>
        The browser risk workflow now mirrors the shared Python outputs more closely: covered versus total risk, benchmark diagnostics, concentration, exclusions, and Monte Carlo views all stay on the shared service payload.
      </p>
    </div>
    <button on:click={submit} disabled={loading || !activeSnapshot}>{loading ? "Computing..." : "Compute Risk"}</button>
  </div>

  <div class="layout">
    <article class="panel controls">
      <div class="field-grid">
        <article class="mode-card">
          <span>Snapshot Source</span>
          <strong>{mode === "portfolio" ? "Portfolio Snapshot" : "Research Snapshot"}</strong>
          <small>
            {mode === "portfolio"
              ? "Risk uses the live portfolio snapshot in portfolio view."
              : "Risk uses the active research snapshot in research view."}
          </small>
        </article>
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
    </article>

    <article class="panel chart-panel">
      <div class="panel-header">
        <div>
          <h3>Risk Time Series</h3>
          <p>{result ? `${result.metrics.aligned_obs_count ?? 0} aligned observations` : "Run risk to populate the browser chart deck"}</p>
        </div>
        <div class="segmented">
          <button class:active={chartMode === "drawdown"} on:click={() => (chartMode = "drawdown")}>Drawdown</button>
          <button class:active={chartMode === "cumulative"} on:click={() => (chartMode = "cumulative")}>Cumulative</button>
        </div>
      </div>
      <TimeSeriesChart series={chartSeries} height={320} emptyMessage="Risk time series will appear after compute" />
    </article>
  </div>

  <div class="summary-grid">
    <article class="panel"><span>Hist VaR</span><strong>{fmt(result?.metrics.historical_var)}</strong></article>
    <article class="panel"><span>Hist CVaR</span><strong>{fmt(result?.metrics.historical_cvar)}</strong></article>
    <article class="panel"><span>Param VaR</span><strong>{fmt(result?.metrics.parametric_var)}</strong></article>
    <article class="panel"><span>MC VaR</span><strong>{fmt(result?.metrics.monte_carlo_var)}</strong></article>
    <article class="panel"><span>MC CVaR</span><strong>{fmt(result?.metrics.monte_carlo_cvar)}</strong></article>
    <article class="panel"><span>Coverage</span><strong>{pct(result?.metrics.risk_coverage_ratio)}</strong></article>
    <article class="panel"><span>Annual Vol</span><strong>{pct(result?.metrics.annual_vol)}</strong></article>
    <article class="panel"><span>Beta / Corr</span><strong>{fmt(result?.metrics.beta, 3)} / {fmt(result?.metrics.correlation, 3)}</strong></article>
    <article class="panel"><span>Jensen Alpha</span><strong>{pct(result?.metrics.alpha_annual)}</strong></article>
    <article class="panel"><span>Obs / Overlap</span><strong>{result?.metrics.aligned_obs_count ?? 0} / {result?.metrics.benchmark_overlap_count ?? 0}</strong></article>
    <article class="panel"><span>HHI / Top-5</span><strong>{fmt(result?.metrics.concentration_hhi, 3)} / {pct(result?.metrics.top5_weight)}</strong></article>
    <article class="panel"><span>Eff Bets</span><strong>{fmt(result?.metrics.effective_bets, 2)}</strong></article>
  </div>

  <div class="detail-grid">
    <article class="panel">
      <h3>Coverage Diagnostics</h3>
      <div class="list">
        <div class="row"><span>Snapshot Source</span><strong>{mode === "portfolio" ? "portfolio" : "research"}</strong></div>
        <div class="row"><span>Snapshot Positions</span><strong>{activeSnapshot?.positions.length ?? 0}</strong></div>
        <div class="row"><span>Portfolio Value</span><strong>{fmt(result?.metrics.portfolio_value)}</strong></div>
        <div class="row"><span>Covered Value</span><strong>{fmt(result?.metrics.covered_portfolio_value)}</strong></div>
        <div class="row"><span>Total Hist VaR Est.</span><strong>{fmt(result?.metrics.historical_var_total_estimate)}</strong></div>
        <div class="row"><span>Total MC VaR Est.</span><strong>{fmt(result?.metrics.monte_carlo_var_total_estimate)}</strong></div>
      </div>
    </article>

    <article class="panel">
      <h3>Risk Regime</h3>
      <div class="list">
        <div class="row"><span>Confidence</span><strong>{pct(confidence)}</strong></div>
        <div class="row"><span>Lookback</span><strong>{lookbackDays}D</strong></div>
        <div class="row"><span>Horizon</span><strong>{horizonDays}D</strong></div>
        <div class="row"><span>MC Model</span><strong>{mcSimulationModel}</strong></div>
        <div class="row"><span>MC Sims</span><strong>{fmt(mcNumSimulations, 0)}</strong></div>
      </div>
    </article>

    <article class="panel">
      <h3>Excluded Assets</h3>
      {#if result?.excluded_assets?.length}
        <div class="list">
          {#each result.excluded_assets as asset}
            <div class="row">
              <span>{asset.symbol}</span>
              <small>{asset.reason}</small>
            </div>
          {/each}
        </div>
      {:else}
        <p class="muted">No excluded assets.</p>
      {/if}
    </article>
  </div>

  <div class="chart-grid">
    <article class="panel">
      <div class="card-head">
        <h3>Return Distribution</h3>
        <small>Historical portfolio returns with VaR/CVaR markers</small>
      </div>
      <DistributionChart
        values={realizedReturns}
        markers={realizedMarkers}
        height={230}
        emptyMessage="Historical return distribution unavailable"
      />
    </article>

    <article class="panel">
      <div class="card-head">
        <h3>Contribution Rank</h3>
        <small>Top variance contributors from the shared risk payload</small>
      </div>
      <BarRankChart
        items={contributionItems}
        emptyMessage="Contribution ranking will appear after compute"
        formatValue={(value) => pct(value)}
      />
    </article>

    <article class="panel">
      <div class="card-head">
        <h3>Monte Carlo Distribution</h3>
        <small>{result?.metrics.monte_carlo_model ?? "Monte Carlo"} terminal returns</small>
      </div>
      <DistributionChart
        values={result?.monte_carlo.terminal_returns ?? []}
        markers={monteCarloMarkers}
        height={230}
        emptyMessage="Monte Carlo distribution unavailable"
      />
    </article>

    <article class="panel span-2">
      <div class="card-head">
        <h3>Monte Carlo Fan</h3>
        <small>{result?.metrics.monte_carlo_horizon_days ?? 0}D percentile path projection</small>
      </div>
      <FanChart
        series={result?.monte_carlo.fan_percentiles ?? {}}
        height={250}
        emptyMessage="Monte Carlo fan chart unavailable"
      />
    </article>
  </div>

  <article class="panel">
    <h3>Contributions Table</h3>
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
            <tr><td colspan="6">No risk result yet.</td></tr>
          {/if}
        </tbody>
      </table>
    </div>
  </article>
</section>

<style>
  .view,
  .layout,
  .field-grid,
  .summary-grid,
  .chart-grid,
  .detail-grid,
  .list {
    display: grid;
    gap: 0.9rem;
  }

  .toolbar,
  .panel-header,
  .row,
  .card-head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .layout {
    grid-template-columns: minmax(20rem, 1fr) minmax(0, 1.35fr);
    align-items: start;
  }

  .field-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .summary-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .detail-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .chart-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: start;
  }

  .span-2 {
    grid-column: span 2;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--surface-0);
    padding: 1rem;
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

  label {
    display: grid;
    gap: 0.45rem;
  }

  .mode-card {
    display: grid;
    gap: 0.45rem;
    border: 1px solid var(--divider);
    background: rgba(8, 13, 18, 0.72);
    padding: 0.75rem 0.85rem;
    align-content: start;
  }

  input,
  select,
  button {
    background: #0b1219;
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.75rem 0.85rem;
    font: inherit;
  }

  button {
    cursor: pointer;
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
  }

  .segmented button {
    border: 0;
  }

  .segmented button.active {
    background: rgba(106, 168, 255, 0.16);
    color: var(--accent);
  }

  .card-head {
    align-items: baseline;
    margin-bottom: 0.85rem;
  }

  .table-wrap {
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    padding: 0.6rem 0.45rem;
    text-align: left;
  }

  .row {
    align-items: flex-start;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    padding-bottom: 0.55rem;
  }

  @media (max-width: 1240px) {
    .chart-grid {
      grid-template-columns: 1fr 1fr;
    }

    .span-2 {
      grid-column: span 2;
    }
  }

  @media (max-width: 1140px) {
    .layout,
    .field-grid,
    .summary-grid,
    .chart-grid,
    .detail-grid,
    .toolbar {
      grid-template-columns: 1fr;
    }

    .span-2 {
      grid-column: auto;
    }

    .toolbar,
    .panel-header,
    .row,
    .card-head {
      flex-direction: column;
      align-items: flex-start;
    }

    .segmented {
      width: 100%;
    }

    .segmented button {
      flex: 1;
    }
  }
</style>
