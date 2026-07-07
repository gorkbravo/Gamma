<script lang="ts">
  import { get } from "svelte/store";
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    ResearchConstituent,
    ResearchCoverage,
    ResearchResult,
    ResearchStructure,
    TimeSeriesPoint
  } from "../lib/api/types";
  import { researchDraft, setResearchDraft, type ResearchRunOptions } from "../lib/stores/app";
  import {
    buildPreviewRows,
    deriveConstituentsFromResearchResult,
    deriveCoverageFromResearchResult,
    deriveStructureFromWeights,
    doesResearchDraftMatchResult,
    hasPopulatedCoverage,
    hasPopulatedStructure,
    normalizeSyntheticText,
    parseSyntheticText,
    type ResearchPreviewRow
  } from "../lib/view-models/research";

  export let result: ResearchResult | null = null;
  export let loading = false;
  export let onRun: (options: ResearchRunOptions) => void;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let onOpenIv: (() => void) | undefined = undefined;

  type ChartMode =
    | "performance"
    | "relative"
    | "price"
    | "drawdown"
    | "rolling_vol"
    | "rolling_beta"
    | "rolling_corr";
  type ResearchTimeframe = "1M" | "3M" | "6M" | "1Y" | "MAX";

  const chartModeLabels: Record<ChartMode, string> = {
    performance: "Performance",
    relative: "Relative",
    price: "Price",
    drawdown: "Drawdown",
    rolling_vol: "Rolling Vol",
    rolling_beta: "Rolling Beta",
    rolling_corr: "Rolling Corr"
  };
  const timeframes: ResearchTimeframe[] = ["1M", "3M", "6M", "1Y", "MAX"];
  const presetBaskets: Array<{ id: string; label: string; text: string }> = [
    { id: "index-core", label: "Index Core", text: "SPY 0.50\nQQQ 0.30\nIWM 0.20" },
    { id: "mega-cap", label: "Mega Cap", text: "AAPL 0.35\nMSFT 0.35\nNVDA 0.30" },
    { id: "defensive", label: "Defensive", text: "XLV 0.35\nXLP 0.35\nXLU 0.30" }
  ];

  const initialDraft = get(researchDraft);
  let scopeType: "single_ticker" | "synthetic_portfolio" = initialDraft.scopeType;
  let primarySymbol = initialDraft.primarySymbol;
  let benchmarkSymbol = initialDraft.benchmarkSymbol;
  let lookbackDays = initialDraft.lookbackDays;
  let syntheticText = initialDraft.syntheticText;
  let chartMode: ChartMode = "performance";
  let timeframe: ResearchTimeframe = "1Y";
  let selectedPreset = initialDraft.selectedPreset;
  let inputWarning = "";
  const emptyStructure: ResearchStructure = {
    total_weight: null,
    top_weight: null,
    top5_weight: null,
    concentration_hhi: null,
    effective_positions: null,
    aligned_symbol_count: 0
  };
  const emptyCoverage: ResearchCoverage = {
    available_symbols: [],
    missing_symbols: [],
    benchmark_overlap_count: 0
  };

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

  function submit() {
    if (scopeType === "single_ticker") {
      inputWarning = primarySymbol.trim() ? "" : "Ticker is required.";
      if (inputWarning) {
        return;
      }
      onRun({
        scopeType,
        primarySymbol: primarySymbol.trim().toUpperCase(),
        benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
        lookbackDays
      });
      return;
    }

    const syntheticPositions = parsedSynthetic.filter((item) => Number.isFinite(item.weight) && item.weight > 0);
    if (!syntheticPositions.length) {
      inputWarning = "Synthetic portfolio needs valid positive weights.";
      return;
    }

    inputWarning = "";
    onRun({
      scopeType,
      syntheticPositions,
      benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
      lookbackDays
    });
  }

  function normalizeSynthetic() {
    syntheticText = normalizeSyntheticText(syntheticText);
    inputWarning = "";
  }

  function applyPreset(presetId: string) {
    const preset = presetBaskets.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }
    syntheticText = preset.text;
    inputWarning = "";
  }

  function resetBuilder() {
    scopeType = "single_ticker";
    primarySymbol = "AAPL";
    benchmarkSymbol = "SPY";
    lookbackDays = 252;
    syntheticText = presetBaskets[0]?.text ?? "SPY 0.60\nQQQ 0.40";
    selectedPreset = presetBaskets[0]?.id ?? "index-core";
    inputWarning = "";
  }

  function slicePoints(points: TimeSeriesPoint[]) {
    if (timeframe === "MAX" || !points.length) {
      return points;
    }
    const latest = new Date(points[points.length - 1].timestamp).getTime();
    const days = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 }[timeframe];
    const cutoff = latest - days * 24 * 60 * 60 * 1000;
    return points.filter((point) => new Date(point.timestamp).getTime() >= cutoff);
  }

  function toChartPoint(point: TimeSeriesPoint) {
    return {
      time: Math.floor(new Date(point.timestamp).getTime() / 1000),
      value: point.value
    };
  }

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
    mode: "beta" | "corr",
    window = 63
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
          mode === "beta"
            ? covariance / benchmarkVariance
            : covariance / Math.sqrt(Math.max(perfVariance, 0) * benchmarkVariance || 1);
        return {
          time: Math.floor(point.ts / 1000),
          value
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function chartEmptyMessage(modeId: ChartMode, currentResult: ResearchResult | null) {
    if (modeId === "price" && currentResult?.scope_type === "synthetic_portfolio") {
      return "Price mode is only available for single-ticker research.";
    }
    if (modeId === "rolling_beta" || modeId === "rolling_corr") {
      return "Rolling beta/correlation needs benchmark overlap after a run.";
    }
    return "Run analysis to populate the research canvas.";
  }

  function buildNotes(
    currentResult: ResearchResult | null,
    structure: ResearchStructure,
    coverage: ResearchCoverage,
    draftScopeType: "single_ticker" | "synthetic_portfolio",
    previewCount: number
  ) {
    const notes: string[] = [];
    if (!currentResult) {
      if (draftScopeType === "synthetic_portfolio") {
        notes.push(previewCount ? `Draft basket has ${previewCount} parsed names before normalization.` : "Build a basket to inspect concentration and benchmark sensitivity.");
      } else {
        notes.push("Single-name research is best for isolating benchmark sensitivity before sending the name to IV or Risk.");
      }
      return notes;
    }

    if ((structure.top_weight ?? 0) >= 0.5) {
      notes.push(`Scope is concentrated: top weight is ${pct(structure.top_weight)}.`);
    } else if ((structure.effective_positions ?? 0) >= 4) {
      notes.push(`Scope is reasonably spread: effective positions are ${fmt(structure.effective_positions, 2)}.`);
    } else {
      notes.push(`Scope remains fairly tight with ${fmt(structure.effective_positions, 2)} effective positions.`);
    }

    if ((currentResult.summary.correlation ?? 0) >= 0.8) {
      notes.push(`Benchmark sensitivity is high at ${fmt(currentResult.summary.correlation, 3)} correlation to ${currentResult.benchmark_symbol}.`);
    } else if ((currentResult.summary.beta ?? 0) >= 1.2) {
      notes.push(`Beta is elevated at ${fmt(currentResult.summary.beta, 3)} versus ${currentResult.benchmark_symbol}.`);
    } else {
      notes.push(`Benchmark dependence looks moderate against ${currentResult.benchmark_symbol}.`);
    }

    if (coverage.missing_symbols.length) {
      notes.push(`Coverage is partial: missing ${coverage.missing_symbols.join(", ")}.`);
    } else {
      notes.push(`Coverage is clean across ${coverage.available_symbols.length} aligned symbols.`);
    }

    if (coverage.benchmark_overlap_count > 0) {
      notes.push(`${coverage.benchmark_overlap_count} aligned benchmark observations support the run.`);
    }

    return notes.slice(0, 4);
  }

  function formatScopeLabel(scopeType: ResearchResult["scope_type"] | "none" | null | undefined) {
    if (scopeType === "single_ticker") {
      return "Single Ticker";
    }
    if (scopeType === "synthetic_portfolio") {
      return "Synthetic Portfolio";
    }
    return "No Active Run";
  }

  function activeHeadline(currentResult: ResearchResult | null) {
    if (!currentResult) {
      return "No Active Analysis";
    }
    if (currentResult.scope_type === "single_ticker") {
      return currentResult.primary_symbol ?? "Single Ticker";
    }
    return "Synthetic Basket";
  }

  function activePrimaryScopeLabel(currentResult: ResearchResult | null) {
    if (!currentResult) {
      return "No active run";
    }
    if (currentResult.scope_type === "single_ticker") {
      return currentResult.primary_symbol ?? "N/A";
    }
    return "Basket";
  }

  let parsedSynthetic = parseSyntheticText(syntheticText);
  let previewRows: ResearchPreviewRow[] = [];
  let chartSeries: ChartSeries[] = [];
  let weightBars: RankBarItem[] = [];
  let structureMetrics: ResearchStructure = emptyStructure;
  let coverageMetrics: ResearchCoverage = emptyCoverage;
  let constituentRows: ResearchConstituent[] = [];
  let bestConstituent: ResearchConstituent | null = null;
  let worstConstituent: ResearchConstituent | null = null;
  let weightedLeader: ResearchConstituent | null = null;
  let researchNotes: string[] = [];
  let draftMatchesResult = false;

  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: setResearchDraft({
    scopeType,
    primarySymbol,
    benchmarkSymbol,
    lookbackDays,
    syntheticText,
    selectedPreset
  });
  $: previewRows = buildPreviewRows(scopeType, primarySymbol, parsedSynthetic);
  $: draftMatchesResult = doesResearchDraftMatchResult(
    result,
    {
      scopeType,
      primarySymbol,
      benchmarkSymbol
    },
    previewRows
  );
  $: structureMetrics = hasPopulatedStructure(result?.structure)
    ? (result?.structure ?? emptyStructure)
    : result?.weights?.length
      ? deriveStructureFromWeights(result.weights)
      : emptyStructure;
  $: coverageMetrics = hasPopulatedCoverage(result?.coverage)
    ? (result?.coverage ?? emptyCoverage)
    : deriveCoverageFromResearchResult(result);
  $: weightBars = (result?.weights ?? []).map((weight) => ({
    label: weight.display_symbol ?? weight.symbol,
    value: weight.weight,
    tone: "positive"
  }));
  $: constituentRows = result?.constituents?.length ? result.constituents : deriveConstituentsFromResearchResult(result);
  $: {
    const ranked = [...(result?.constituents ?? [])].filter((item) => item.total_return != null);
    bestConstituent = ranked.length ? [...ranked].sort((left, right) => (right.total_return ?? -Infinity) - (left.total_return ?? -Infinity))[0] : null;
    worstConstituent = ranked.length ? [...ranked].sort((left, right) => (left.total_return ?? Infinity) - (right.total_return ?? Infinity))[0] : null;
    weightedLeader = [...(result?.constituents ?? [])]
      .filter((item) => item.weighted_return != null)
      .sort((left, right) => (right.weighted_return ?? -Infinity) - (left.weighted_return ?? -Infinity))[0] ?? null;
  }
  $: researchNotes = buildNotes(result, structureMetrics, coverageMetrics, scopeType, previewRows.length);
  $: {
    const perf = slicePoints(result?.performance_points ?? []);
    const benchmark = slicePoints(result?.benchmark_points ?? []);
    const prices = slicePoints(result?.primary_price_points ?? []);

    if (!result) {
      chartSeries = [];
    } else if (chartMode === "price") {
      chartSeries = prices.length
        ? [
            {
              id: "price",
              label: result.primary_symbol ?? "Price",
              color: "#c49a5a",
              type: "line",
              data: prices.map(toChartPoint)
            }
          ]
        : [];
    } else if (chartMode === "drawdown") {
      let cumulative = 1;
      let peak = 1;
      chartSeries = perf.length
        ? [
            {
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
            }
          ]
        : [];
    } else if (chartMode === "rolling_vol") {
      const volSeries = rollingStd(perf);
      chartSeries = volSeries.length
        ? [
            {
              id: "rolling_vol",
              label: "Rolling Vol",
              color: "#9bd19f",
              type: "line",
              data: volSeries
            }
          ]
        : [];
    } else if (chartMode === "rolling_beta" || chartMode === "rolling_corr") {
      const betaSeries = rollingBetaLike(perf, benchmark, chartMode === "rolling_beta" ? "beta" : "corr");
      chartSeries = betaSeries.length
        ? [
            {
              id: chartMode,
              label: chartMode === "rolling_beta" ? "Rolling Beta" : "Rolling Corr",
              color: chartMode === "rolling_beta" ? "#c49a5a" : "#d8c17a",
              type: "line",
              data: betaSeries
            }
          ]
        : [];
    } else if (chartMode === "relative") {
      const perfSeries = cumulativeFromReturns(perf);
      const benchmarkSeries = cumulativeFromReturns(benchmark);
      const benchmarkByTime = new Map(benchmarkSeries.map((point) => [point.time, point.value]));
      const relative = perfSeries
        .map((point) => {
          const benchmarkValue = benchmarkByTime.get(point.time);
          if (benchmarkValue == null || benchmarkValue === 0) {
            return null;
          }
          return {
            time: point.time,
            value: point.value / benchmarkValue - 1
          };
        })
        .filter((point): point is { time: number; value: number } => point !== null);
      chartSeries = relative.length
        ? [
            {
              id: "relative",
              label: "Relative Return",
              color: "#ff9f5a",
              type: "line",
              data: relative
            }
          ]
        : [];
    } else {
      const series: ChartSeries[] = [];
      if (perf.length) {
        series.push({
          id: "research",
          label: result.primary_symbol ?? (result.scope_type === "single_ticker" ? "Research" : "Scope"),
          color: "#7aa6c8",
          type: "area",
          data: cumulativeFromReturns(perf)
        });
      }
      if (benchmark.length) {
        series.push({
          id: "benchmark",
          label: result.benchmark_symbol,
          color: "#c49a5a",
          type: "line",
          lineStyle: "dashed",
          data: cumulativeFromReturns(benchmark)
        });
      }
      chartSeries = series;
    }
  }
</script>

<section class="view">
  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel performance-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Research Workspace</p>
            <h2>{activeHeadline(result)}</h2>
            <p class="muted">
              {#if result}
                Analysis cards and handoff actions are pinned to the last completed research run.
              {:else}
                Build a scope in the builder, then run analysis to create an active research context.
              {/if}
            </p>
          </div>
          <div class="header-actions">
            <label class="inline-field timeframe-field">
              <span>Timeframe</span>
              <select bind:value={timeframe}>
                {#each timeframes as option}
                  <option value={option}>{option}</option>
                {/each}
              </select>
            </label>
            <label class="inline-field view-field">
              <span>View</span>
              <select bind:value={chartMode}>
                {#each Object.entries(chartModeLabels) as [value, label]}
                  <option value={value}>{label}</option>
                {/each}
              </select>
            </label>
          </div>
        </div>

        <div class="kpi-grid">
          <article class="metric">
            <span>Total Return</span>
            <strong class:positive={(result?.summary.total_return ?? 0) > 0} class:negative={(result?.summary.total_return ?? 0) < 0}>{pct(result?.summary.total_return)}</strong>
            <small>{result?.observations_count ?? 0} aligned observations</small>
          </article>
          <article class="metric">
            <span>Annual Return</span>
            <strong>{pct(result?.summary.annual_return)}</strong>
            <small>{result?.benchmark_symbol ?? "N/A"} benchmark</small>
          </article>
          <article class="metric">
            <span>Annual Vol</span>
            <strong>{pct(result?.summary.annual_vol)}</strong>
            <small>{fmt(structureMetrics.aligned_symbol_count, 0)} aligned names</small>
          </article>
          <article class="metric">
            <span>Max Drawdown</span>
            <strong class:negative={(result?.summary.max_drawdown ?? 0) < 0}>{pct(result?.summary.max_drawdown)}</strong>
            <small>{pct(structureMetrics.top_weight)} top weight</small>
          </article>
          <article class="metric">
            <span>Beta</span>
            <strong class:elevated={(result?.summary.beta ?? 0) > 1.2}>{fmt(result?.summary.beta, 3)}</strong>
            <small>{coverageMetrics.benchmark_overlap_count} overlap obs</small>
          </article>
          <article class="metric">
            <span>Correlation</span>
            <strong>{fmt(result?.summary.correlation, 3)}</strong>
            <small>{pct(structureMetrics.top5_weight)} top-5 weight</small>
          </article>
        </div>

        <TimeSeriesChart series={chartSeries} height={380} emptyMessage={chartEmptyMessage(chartMode, result)} />

        <div class="chart-foot">
          <span>
            {#if coverageMetrics.missing_symbols.length}
              Missing history: {coverageMetrics.missing_symbols.join(", ")}
            {:else if result}
              Shared research return stream against {result.benchmark_symbol}
            {:else}
              Run a scope to seed the chart deck.
            {/if}
          </span>
          <strong>{result?.scope_type === "synthetic_portfolio" ? `${coverageMetrics.available_symbols.length} symbols in scope` : activePrimaryScopeLabel(result)}</strong>
        </div>
      </article>

      <div class="detail-split">
        <article class="panel composition-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Composition</p>
              <h3>Weights &amp; Structure</h3>
            </div>
            <small>{structureMetrics.aligned_symbol_count} aligned names</small>
          </div>

          <BarRankChart items={weightBars} emptyMessage="Weights will appear after running analysis." formatValue={(value) => pct(value)} />

          <div class="stack">
            <div class="row"><span>Top Weight</span><strong>{pct(structureMetrics.top_weight)}</strong></div>
            <div class="row"><span>Top-5 Weight</span><strong>{pct(structureMetrics.top5_weight)}</strong></div>
            <div class="row"><span>HHI</span><strong>{fmt(structureMetrics.concentration_hhi, 3)}</strong></div>
            <div class="row"><span>Effective Positions</span><strong>{fmt(structureMetrics.effective_positions, 2)}</strong></div>
          </div>
        </article>
 
        <article class="panel insight-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Research Readout</p>
              <h3>Interpretation</h3>
            </div>
          </div>

          <div class="stack">
            <div class="row"><span>Best Constituent</span><strong>{bestConstituent ? `${bestConstituent.display_symbol ?? bestConstituent.symbol} | ${pct(bestConstituent.total_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Worst Constituent</span><strong>{worstConstituent ? `${worstConstituent.display_symbol ?? worstConstituent.symbol} | ${pct(worstConstituent.total_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Weighted Leader</span><strong>{weightedLeader ? `${weightedLeader.display_symbol ?? weightedLeader.symbol} | ${pct(weightedLeader.weighted_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Benchmark Overlap</span><strong>{coverageMetrics.benchmark_overlap_count}</strong></div>
          </div>

          <div class="notes-list">
            {#each researchNotes as note}
              <div class="note-row">
                <span class="note-tag">Note</span>
                <p>{note}</p>
              </div>
            {/each}
          </div>
        </article>
      </div>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Constituents</p>
            <h3>Constituent Detail</h3>
          </div>
          <small>{constituentRows.length} rows</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Weight</th>
                <th>Total Return</th>
                <th>Annual Vol</th>
                <th>Max DD</th>
                <th>Weighted Return</th>
              </tr>
            </thead>
            <tbody>
              {#if constituentRows.length}
                {#each constituentRows as constituent}
                  <tr>
                    <td>{constituent.display_symbol ?? constituent.symbol}</td>
                    <td>{pct(constituent.weight)}</td>
                    <td>{pct(constituent.total_return)}</td>
                    <td>{pct(constituent.annual_vol)}</td>
                    <td>{pct(constituent.max_drawdown)}</td>
                    <td>{pct(constituent.weighted_return)}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="6">No constituent rows yet.</td></tr>
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
            <p class="eyebrow">Scope Builder</p>
            <h3>Build Research Scope</h3>
          </div>
          <strong>{scopeType === "single_ticker" ? "Single Ticker" : "Synthetic Basket"}</strong>
        </div>

        <div class="field-grid">
          <label>
            <span>Scope</span>
            <select bind:value={scopeType}>
              <option value="single_ticker">Single Ticker</option>
              <option value="synthetic_portfolio">Synthetic Portfolio</option>
            </select>
          </label>
          <label>
            <span>Benchmark</span>
            <input bind:value={benchmarkSymbol} placeholder="SPY" />
          </label>
          <label>
            <span>Lookback</span>
            <select bind:value={lookbackDays}>
              <option value={126}>126D</option>
              <option value={252}>252D</option>
              <option value={504}>504D</option>
            </select>
          </label>
        </div>

        {#if scopeType === "single_ticker"}
          <label>
            <span>Ticker</span>
            <input bind:value={primarySymbol} placeholder="AAPL" />
          </label>
        {:else}
          <div class="subsection">
            <div class="section-head">
              <h4>Basket Input</h4>
              <small>One line per name, example: `SPY 0.60`</small>
            </div>

            <label>
              <span>Preset</span>
              <select bind:value={selectedPreset} on:change={() => applyPreset(selectedPreset)}>
                {#each presetBaskets as preset}
                  <option value={preset.id}>{preset.label}</option>
                {/each}
              </select>
            </label>

            <label>
              <span>Synthetic Portfolio</span>
              <textarea bind:value={syntheticText} rows="7" spellcheck="false"></textarea>
            </label>

            <div class="builder-actions compact">
              <button type="button" on:click={normalizeSynthetic}>Normalize</button>
              <button type="button" class="ghost-button" on:click={() => applyPreset(selectedPreset)}>Load Preset</button>
            </div>
          </div>
        {/if}

        {#if inputWarning}
          <p class="warning">{inputWarning}</p>
        {/if}

        <div class="builder-actions">
          <button on:click={submit} disabled={loading}>{loading ? "Running..." : "Run Analysis"}</button>
          <button type="button" class="ghost-button" on:click={resetBuilder}>Reset Builder</button>
        </div>

        {#if result && !draftMatchesResult}
          <p class="muted">Draft differs from the active analysis. Rerun to replace the current research context.</p>
        {/if}

        <div class="subsection">
          <div class="section-head">
            <h4>Scope Preview</h4>
            <small>{previewRows.length} parsed names</small>
          </div>

          <div class="table-wrap preview-table">
            <table>
              <thead>
                <tr><th>Symbol</th><th>Input</th><th>Normalized</th></tr>
              </thead>
              <tbody>
                {#if previewRows.length}
                  {#each previewRows as row}
                    <tr>
                      <td>{row.symbol}</td>
                      <td>{fmt(row.inputWeight, 4)}</td>
                      <td>{pct(row.normalizedWeight)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="3">No parsed scope yet.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </div>
      </article>
 
      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Structure</p>
            <h3>Active Scope Summary</h3>
          </div>
        </div>

        <div class="stack">
          <div class="row"><span>Scope Type</span><strong>{formatScopeLabel(result?.scope_type)}</strong></div>
          <div class="row"><span>Primary Symbol</span><strong>{activePrimaryScopeLabel(result)}</strong></div>
          <div class="row"><span>Aligned Symbols</span><strong>{structureMetrics.aligned_symbol_count}</strong></div>
          <div class="row"><span>Total Weight</span><strong>{fmt(structureMetrics.total_weight, 4)}</strong></div>
          <div class="row"><span>Effective Positions</span><strong>{fmt(structureMetrics.effective_positions, 2)}</strong></div>
          <div class="row"><span>HHI / Top-5</span><strong>{fmt(structureMetrics.concentration_hhi, 3)} / {pct(structureMetrics.top5_weight)}</strong></div>
        </div>

        <div class="mini-groups">
          <div>
            <small class="group-label">Available Symbols</small>
            <div class="pill-list">
              {#if coverageMetrics.available_symbols.length}
                {#each coverageMetrics.available_symbols as symbol}
                  <span>{symbol}</span>
                {/each}
              {:else}
                <span>Waiting for active run</span>
              {/if}
            </div>
          </div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Research Context</p>
            <h3>Data Quality &amp; Coverage</h3>
          </div>
        </div>

        <div class="stack">
          <div class="row"><span>Observations</span><strong>{result?.observations_count ?? 0}</strong></div>
          <div class="row"><span>Benchmark Overlap</span><strong>{coverageMetrics.benchmark_overlap_count}</strong></div>
          <div class="row"><span>Missing Symbols</span><strong>{coverageMetrics.missing_symbols.length}</strong></div>
          <div class="row"><span>Benchmark</span><strong>{result?.benchmark_symbol ?? "N/A"}</strong></div>
        </div>

        {#if result?.warnings?.length || coverageMetrics.missing_symbols.length}
          <div class="notes-list">
            {#each coverageMetrics.missing_symbols as symbol}
              <div class="note-row">
                <span class="note-tag">{symbol}</span>
                <p>History is missing for this symbol in the current run.</p>
              </div>
            {/each}
            {#each result?.warnings ?? [] as warning}
              <div class="note-row info">
                <span class="note-tag">Warning</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No active coverage issues or warnings.</p>
        {/if}
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Forward Actions</p>
            <h3>Handoff &amp; Snapshot</h3>
          </div>
        </div>

        <div class="builder-actions">
          <button type="button" on:click={() => onOpenRisk?.()} disabled={!result?.snapshot}>Open In Risk</button>
          <button type="button" class="ghost-button" on:click={() => onOpenIv?.()} disabled={result?.scope_type !== "single_ticker"}>Open In IV</button>
        </div>

        {#if result?.snapshot}
          <div class="stack">
            <div class="row"><span>Base Currency</span><strong>{result.snapshot.base_currency}</strong></div>
            <div class="row"><span>Positions</span><strong>{result.snapshot.positions.length}</strong></div>
            <div class="row"><span>Portfolio Value</span><strong>{fmt(result.snapshot.net_liquidation)}</strong></div>
            <div class="row"><span>Snapshot Time</span><strong>{new Date(result.snapshot.timestamp).toLocaleString()}</strong></div>
          </div>
        {:else}
          <p class="muted">Run research to create the forwarded snapshot for Risk or IV.</p>
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
  .detail-split,
  .stack,
  .field-grid,
  .builder-actions,
  .notes-list,
  .mini-groups {
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

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(12, 14, 16, 0.97), rgba(9, 10, 12, 0.95));
    padding: 1.05rem;
  }

  .performance-panel,
  .composition-panel,
  .insight-panel,
  .table-panel,
  .control-panel,
  .rail-panel,
  .subsection {
    display: grid;
    gap: 0.95rem;
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

  .title-block {
    min-width: 0;
    max-width: 40rem;
  }

  .header-actions {
    display: grid;
    grid-template-columns: auto auto;
    gap: 0.75rem;
    align-items: end;
    justify-content: end;
  }

  .header-actions select {
    min-height: 2.6rem;
    padding: 0.42rem 0.62rem;
  }

  .view-field {
    min-width: 0;
    width: 9rem;
  }

  .kpi-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
    padding-block: 0.2rem;
  }

  .metric {
    min-width: 0;
    padding: 0.2rem 1rem;
    border-left: 1px solid rgba(46, 60, 74, 0.52);
    background: none;
    text-align: center;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric strong {
    display: block;
    margin: 0.18rem 0 0.24rem;
    font-size: 1rem;
    line-height: 1.2;
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

  h2,
  h3,
  h4,
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

  .muted,
  .row span,
  .row strong,
  .note-row p {
    overflow-wrap: anywhere;
  }

  label,
  .inline-field {
    display: grid;
    gap: 0.4rem;
  }

  .inline-field {
    min-width: 10rem;
  }

  .inline-field.timeframe-field {
    min-width: 7.75rem;
    width: 7.75rem;
  }

  .field-grid {
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.72fr) minmax(0, 0.58fr);
  }

  .field-grid > label {
    min-width: 0;
  }

  input,
  select,
  textarea,
  button {
    border: 1px solid var(--panel-strong);
    background: #0d0f12;
    color: var(--text-0);
    padding: 0.56rem 0.72rem;
    font: inherit;
    display: block;
    width: 100%;
    box-sizing: border-box;
  }

  textarea {
    min-height: 7rem;
    resize: vertical;
  }

  input,
  select,
  button {
    min-height: 3rem;
    line-height: 1.15;
  }

  button {
    cursor: pointer;
  }

  .ghost-button {
    background: transparent;
  }

  .builder-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .builder-actions.compact {
    grid-template-columns: repeat(2, auto);
    justify-content: start;
  }

  .builder-actions.compact button {
    width: auto;
    min-height: 2.5rem;
    padding: 0.45rem 0.8rem;
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

  .table-wrap {
    overflow: auto;
    border-top: 1px solid rgba(46, 60, 74, 0.52);
  }

  .preview-table {
    border-top: 0;
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

  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.55rem;
  }

  .pill-list span {
    border: 1px solid rgba(122, 166, 200, 0.14);
    background: rgba(122, 166, 200, 0.05);
    color: var(--text-1);
    padding: 0.34rem 0.46rem;
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

  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  .elevated { color: var(--data-warm); }

  .warning {
    color: var(--warning);
  }

  @media (max-width: 1240px) {
    .workspace-grid,
    .detail-split {
      grid-template-columns: 1fr;
    }

    .support-column {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .kpi-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 980px) {
    .support-column,
    .field-grid,
    .builder-actions,
    .kpi-grid {
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
    .chart-foot,
    .section-head {
      flex-direction: column;
      align-items: stretch;
    }

    .header-actions {
      grid-template-columns: 1fr;
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
