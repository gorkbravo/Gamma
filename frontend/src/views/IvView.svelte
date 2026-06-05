<script lang="ts">
  import type { CrossTabHandoffEnvelope, IvSessionStatus, IvSurface, SystemStatus, TimeSeriesPoint } from "../lib/api/types";
  import type { IvLoadOptions } from "../lib/stores/app";
  import {
    buildStrategyLegFromChainRow,
    daysToExpiry,
    deriveChainRows,
    deriveDistributionBuckets,
    deriveIvSmile,
    deriveOptionPayoffMatrix,
    deriveOverviewSnapshot,
    deriveRealizedVolatility,
    deriveSkewRows,
    deriveStrategyPayoff,
    deriveSurfaceStats,
    deriveTermCurve,
    deriveTermStructure,
    nearestStrikeIndex,
    optionsModes,
    selectedExpiryForSurface,
    type ChainRow,
    type IvSmile,
    type IvSmilePoint,
    type OptionPayoffMatrix,
    type OptionsMode,
    type StrategyLeg,
    type StrategyOptionType,
    type StrategySide,
    type TermCurve,
    type TermCurvePoint,
  } from "../lib/view-models/iv";
  import Surface3D from "../components/Surface3D.svelte";

  export let mode: OptionsMode = "overview";
  export let status: SystemStatus | null = null;
  export let requestedSymbol = "";
  export let result: IvSurface | null = null;
  export let session: IvSessionStatus | null = null;
  export let underlyingPricePoints: TimeSeriesPoint[] = [];
  export let loading = false;
  export let sessionLoading = false;
  export let errorMessage = "";
  export let onLoad: (options: IvLoadOptions) => void | Promise<void>;
  export let onStopSession: () => void | Promise<void>;
  export let onSendToCopilot: (handoff: CrossTabHandoffEnvelope) => Promise<unknown> | void = () => {};

  let symbol = requestedSymbol || "";
  let lastRequestedSymbol = requestedSymbol;
  let selectedExpiry: string | null = null;
  let selectedOptionType: StrategyOptionType = "call";
  let selectedSide: StrategySide = "long";
  let payoffOptionType: StrategyOptionType = "call";
  let strategyLegs: StrategyLeg[] = [];

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const money = (value: number | null | undefined) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const signedPct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
  const signedMoney = (value: number | null | undefined) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const shortTime = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";
  const formatExpiry = (expiry: string | null | undefined) => {
    if (!expiry) return "N/A";
    const match = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(expiry);
    return match ? `${match[1]}/${match[2]}/${match[3]}` : expiry;
  };
  const depthLabel = (value: string | null | undefined) =>
    value === "max"
      ? "Max"
      : value === "front_deep"
        ? "Front Deep"
        : value
          ? value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
          : "N/A";

  let activeExpiry: string | null = null;
  let chainRows: ChainRow[] = [];
  let overview = deriveOverviewSnapshot(result, selectedExpiry);
  let surfaceStats = deriveSurfaceStats(result);
  let termStructure = deriveTermStructure(result);
  let skewRows = deriveSkewRows(result);
  let realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  let distributionBuckets = deriveDistributionBuckets(result);
  let strategyPayoff = deriveStrategyPayoff(strategyLegs, result?.spot);
  let maxDistributionProbability = 0.01;
  let payoffAbsMax = 1;
  let ivSmile: IvSmile | null = null;
  let hoverSmile: IvSmilePoint | null = null;
  let termCurve: TermCurve | null = null;
  let hoverTerm: TermCurvePoint | null = null;
  let hoveredSurface: { row: number; col: number } | null = null;
  let payoffMatrix: OptionPayoffMatrix | null = null;
  let atmStrikeIndex = 0;
  let surfaceAlerts: string[] = [];
  let requestSymbol = "";
  let displayedSymbol = "No surface";

  $: if (!optionsModes.some((candidate) => candidate.id === mode)) {
    mode = "overview";
  }

  $: if (requestedSymbol && requestedSymbol !== lastRequestedSymbol) {
    lastRequestedSymbol = requestedSymbol;
    symbol = requestedSymbol.toUpperCase();
    selectedExpiry = null;
  }

  $: activeExpiry = selectedExpiryForSurface(result, selectedExpiry);
  $: chainRows = deriveChainRows(result, activeExpiry);
  $: overview = deriveOverviewSnapshot(result, activeExpiry);
  $: surfaceStats = deriveSurfaceStats(result);
  $: termStructure = deriveTermStructure(result);
  $: termCurve = deriveTermCurve(termStructure);
  $: skewRows = deriveSkewRows(result);
  $: realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  $: distributionBuckets = deriveDistributionBuckets(result);
  $: maxDistributionProbability = Math.max(...distributionBuckets.map((bucket) => bucket.probability), 0.01);
  $: strategyPayoff = deriveStrategyPayoff(strategyLegs, result?.spot);
  $: payoffAbsMax = Math.max(...strategyPayoff.points.map((point) => Math.abs(point.payoff)), 1);
  $: ivSmile = deriveIvSmile(chainRows, overview.atmPair?.strike);
  $: payoffMatrix = deriveOptionPayoffMatrix(chainRows, result?.spot, payoffOptionType);
  $: atmStrikeIndex = nearestStrikeIndex(result);
  $: requestSymbol = symbol.trim().toUpperCase() || result?.symbol?.trim().toUpperCase() || "";
  $: displayedSymbol = result?.symbol ?? (symbol.trim() ? normalizedSymbol() : "No surface");
  $: surfaceAlerts = [
    errorMessage?.trim(),
    result && !result.snapshot_available ? `No options surface snapshot is available for ${result.symbol}.` : "",
    ...(result?.warnings ?? []),
    ...(result?.messages ?? []),
    session?.status_text?.toLowerCase().startsWith("error") ? session.status_text : "",
    ...(session?.messages ?? []),
  ].filter((message): message is string => Boolean(message && message.trim()));

  function normalizedSymbol() {
    return requestSymbol;
  }

  function activeMarketDataMode() {
    return status?.market_data_mode ?? result?.collection?.market_data_mode ?? session?.market_data_mode ?? "delayed";
  }

  async function loadMaxSurface() {
    const nextSymbol = normalizedSymbol();
    if (!nextSymbol) {
      return;
    }
    await onLoad({
      symbol: nextSymbol,
      marketDataMode: activeMarketDataMode(),
      waitSeconds: 60,
      depthPreset: "max",
    });
  }

  async function stopSession() {
    await onStopSession();
  }

  function chooseMode(nextMode: OptionsMode) {
    mode = nextMode;
  }

  function sendSurfaceToCopilot() {
    const surface = result;
    if (!surface) {
      return;
    }
    const handoff: CrossTabHandoffEnvelope = {
      source_tab: "iv",
      source_mode: mode,
      selected_entity: {
        entity_type: "options_surface",
        label: `${surface.symbol} Options Workspace`,
        normalized_id: surface.symbol,
        provider_id: surface.source_provider,
        native_id: surface.symbol,
        metadata: {
          symbol: surface.symbol,
          expiries: surface.expiries.length,
          strikes: surface.strikes.length,
          points: surface.points,
          selected_expiry: activeExpiry,
          freshness_label: surface.freshness_label,
          delayed: surface.delayed,
        },
      },
      selected_timeframe: surface.timestamp
        ? { label: `Snapshot ${shortTime(surface.timestamp)}`, start: null, end: surface.timestamp }
        : null,
      provider: surface.source_provider,
      source: null,
      warnings: surface.warnings ?? [],
      normalized_ids: { symbol: surface.symbol },
      timestamp: new Date().toISOString(),
      intended_target_tab: "copilot",
      intended_target_mode: "active_tab",
    };
    void onSendToCopilot(handoff);
  }

  function addLeg(row: ChainRow, optionType = selectedOptionType, side = selectedSide) {
    const leg = buildStrategyLegFromChainRow(row, optionType, side);
    if (!leg) {
      return;
    }
    strategyLegs = [...strategyLegs, { ...leg, id: `${leg.id}-${strategyLegs.length + 1}` }];
    mode = "strategies";
  }

  function removeLeg(id: string) {
    strategyLegs = strategyLegs.filter((leg) => leg.id !== id);
  }

  function clearStrategy() {
    strategyLegs = [];
  }

  function payoffCellStyle(value: number) {
    const color = value >= 0 ? "var(--positive)" : "var(--negative)";
    const intensity = Math.min(0.26, Math.abs(value) / payoffAbsMax * 0.26);
    return `background: color-mix(in srgb, ${color} ${Math.round(intensity * 100)}%, transparent); color: ${color};`;
  }

  function payoffHeatStyle(pct: number, maxGain: number) {
    const color = pct >= 0 ? "var(--positive)" : "var(--negative)";
    const denom = pct >= 0 ? Math.max(maxGain, 0.01) : 1;
    const intensity = Math.min(0.52, (Math.abs(pct) / denom) * 0.52);
    return `background: color-mix(in srgb, ${color} ${Math.round(intensity * 100)}%, transparent);`;
  }

  const payoffPct = (value: number) => `${value >= 0 ? "+" : ""}${Math.round(Math.max(-1, value) * 100)}`;

  function heatStyle(value: number | null | undefined) {
    if (value == null || surfaceStats.minIv == null || surfaceStats.maxIv == null) {
      return "";
    }
    const range = Math.max(surfaceStats.maxIv - surfaceStats.minIv, 0.01);
    const heat = Math.max(8, Math.min(58, ((value - surfaceStats.minIv) / range) * 58));
    return `background: color-mix(in srgb, var(--chart-primary) ${heat}%, var(--bg-0));`;
  }

  function rowClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div>
        <span class="eyebrow">OPTIONS WORKSPACE</span>
        <h2>{displayedSymbol}</h2>
      </div>
      <div class="header-actions">
        <label class="symbol-control">
          <span>Symbol</span>
          <input bind:value={symbol} on:keydown={(event) => event.key === "Enter" && loadMaxSurface()} placeholder="SPY" />
        </label>
        <button class="primary-action" type="button" on:click={loadMaxSurface} disabled={loading || sessionLoading || !requestSymbol}>
          {loading ? "LOADING..." : result ? "Reload Max Surface" : "Load Max Surface"}
        </button>
        {#if session?.running}
          <button type="button" on:click={stopSession} disabled={sessionLoading}>
            {sessionLoading ? "STOPPING..." : "Stop Stream"}
          </button>
        {/if}
        <button type="button" on:click={sendSurfaceToCopilot} disabled={loading || !result}>Copilot</button>
      </div>
    </div>

    <div class="mode-row">
      <div class="mode-bar" role="tablist" aria-label="Options modes">
        {#each optionsModes as optionMode}
          <button
            class:selected={optionMode.id === mode}
            role="tab"
            aria-selected={optionMode.id === mode}
            type="button"
            on:click={() => chooseMode(optionMode.id)}
          >
            {optionMode.label}
          </button>
        {/each}
      </div>
      <div class="source-strip">
        <div><span>Spot</span><strong>{money(result?.spot)}</strong></div>
        <div><span>ATM IV</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
        <div><span>Term</span><strong class={rowClass(surfaceStats.termSlope)}>{signedPct(surfaceStats.termSlope)}</strong></div>
        <div><span>Expiry</span><strong>{formatExpiry(activeExpiry)}</strong></div>
        <div><span>Depth</span><strong>{depthLabel(result?.collection?.depth_preset)}</strong></div>
        <div><span>Source</span><strong>{result?.freshness_label ?? "unknown"}</strong></div>
      </div>
    </div>
  </article>

  {#if surfaceAlerts.length}
    <article class="panel alert-panel" role="alert">
      <h3>Options Data Issue</h3>
      <div class="warning-list">
        {#each surfaceAlerts.slice(0, 5) as message}
          <div>{message}</div>
        {/each}
      </div>
    </article>
  {/if}

  {#if mode === "overview"}
    <div class="workspace-grid overview-grid">
      <div class="primary-column">
        <article class="panel kpi-panel">
          <div class="kpi-grid">
            <div class="metric"><span>Front ATM IV</span><strong>{pct(surfaceStats.frontAtmIv)}</strong><small>{formatExpiry(surfaceStats.frontExpiry)}</small></div>
            <div class="metric"><span>Back ATM IV</span><strong>{pct(surfaceStats.backAtmIv)}</strong><small>{signedPct(surfaceStats.termSlope)} slope</small></div>
            <div class="metric"><span>ATM Strike</span><strong>{fmt(surfaceStats.atmStrike, 2)}</strong><small>Spot {money(result?.spot)}</small></div>
            <div class="metric"><span>Put / Call OI</span><strong>{fmt(overview.putCallOpenInterestRatio, 2)}</strong><small>Volume {fmt(overview.putCallVolumeRatio, 2)}</small></div>
            <div class="metric"><span>Implied Move</span><strong>{pct(overview.atmPair?.impliedMovePct)}</strong><small>Straddle {money(overview.atmPair?.straddleMidpoint)}</small></div>
            <div class="metric"><span>Max Pain</span><strong>{fmt(overview.maxPainStrike, 2)}</strong><small>{overview.frontChain.length} chain rows</small></div>
          </div>
        </article>

        <article class="panel split-panel">
          <div class="panel-head">
            <h3>Front Expiry Chain</h3>
            <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
              {#each result?.expiries ?? [] as expiry}
                <option value={expiry}>{formatExpiry(expiry)} / {daysToExpiry(expiry)}D</option>
              {/each}
            </select>
          </div>
          {#if chainRows.length}
            <table class="chain-table">
              <thead>
                <tr>
                  <th>C Δ</th><th>C IV</th><th>C Px</th><th class="strike-cell">Strike</th><th>P Px</th><th>P IV</th><th>P Δ</th><th>Move</th>
                </tr>
              </thead>
              <tbody>
                {#each chainRows as row}
                  {@const callItm = row.distancePct != null && row.distancePct < 0}
                  {@const putItm = row.distancePct != null && row.distancePct > 0}
                  <tr class:atm={row.strike === overview.atmPair?.strike}>
                    <td class:itm={callItm}>{fmt(row.callDelta, 3)}</td>
                    <td class:itm={callItm}>{pct(row.callIv)}</td>
                    <td class:itm={callItm}>{money(row.callMidpoint)}</td>
                    <td class="strike-cell">{fmt(row.strike, 2)}</td>
                    <td class:itm={putItm}>{money(row.putMidpoint)}</td>
                    <td class:itm={putItm}>{pct(row.putIv)}</td>
                    <td class:itm={putItm}>{fmt(row.putDelta, 3)}</td>
                    <td>{pct(row.impliedMovePct)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="muted">Load an options snapshot to populate the front-expiry chain.</p>
          {/if}
        </article>

        <article class="panel payoff-panel split-panel">
          <div class="panel-head">
            <h3>Payoff Glance</h3>
            <div class="payoff-controls">
              {#if payoffMatrix}
                <span class="payoff-meta">ATM {fmt(payoffMatrix.strike, 0)} {payoffOptionType} · @ {money(payoffMatrix.premium)} · IV {pct(payoffMatrix.sigma)} · % of max risk</span>
              {/if}
              <select bind:value={payoffOptionType} aria-label="Payoff option type">
                <option value="call">Call</option>
                <option value="put">Put</option>
              </select>
            </div>
          </div>
          {#if payoffMatrix}
            <div class="payoff-heatmap-wrap">
              <table class="payoff-heatmap">
                <thead>
                  <tr>
                    <th class="price-col">Price</th>
                    {#each payoffMatrix.dteColumns as dte}
                      <th>{dte === 0 ? "Exp" : `${dte}d`}</th>
                    {/each}
                    <th class="move-col">+/-%</th>
                  </tr>
                </thead>
                <tbody>
                  {#each payoffMatrix.rows as row}
                    <tr class:atm={Math.abs(row.movePct) < 1e-9}>
                      <th class="price-col">{fmt(row.price, 0)}</th>
                      {#each row.cells as cell}
                        <td style={payoffHeatStyle(cell.pct, payoffMatrix.maxGain)}>{payoffPct(cell.pct)}</td>
                      {/each}
                      <td class="move-col {rowClass(row.movePct)}">{signedPct(row.movePct, 0)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="muted pad">No ATM option pair available to model payoff.</p>
          {/if}
        </article>
      </div>

      <div class="support-column">
        <article class="panel">
          <h3>
            Front IV Smile
            {#if hoverSmile}
              <span class="smile-readout">{fmt(hoverSmile.strike, 0)} · {pct(hoverSmile.iv)}{hoverSmile.isAtm ? " · ATM" : ""}</span>
            {/if}
          </h3>
          {#if ivSmile}
            <div class="smile-chart">
              <svg
                viewBox={`0 0 ${ivSmile.width} ${ivSmile.height}`}
                role="img"
                aria-label="Front expiry implied volatility smile"
                on:mouseleave={() => (hoverSmile = null)}
              >
                <line class="smile-axis" x1="32" y1={ivSmile.height - 18} x2={ivSmile.width - 8} y2={ivSmile.height - 18} />
                {#if ivSmile.atmX != null}
                  <line class="smile-atm" x1={ivSmile.atmX} y1="10" x2={ivSmile.atmX} y2={ivSmile.height - 18} />
                {/if}
                <path class="smile-area" d={ivSmile.areaPath} />
                <path class="smile-line" d={ivSmile.linePath} />
                {#each ivSmile.points as point}
                  <circle class:atm={point.isAtm} class="smile-dot" cx={point.x} cy={point.y} r={point.isAtm ? 2.6 : 1.6} />
                {/each}
                {#if hoverSmile}
                  <line class="smile-guide" x1={hoverSmile.x} y1="10" x2={hoverSmile.x} y2={ivSmile.height - 18} />
                  <circle class="smile-dot hover" cx={hoverSmile.x} cy={hoverSmile.y} r="3.4" />
                {/if}
                {#each ivSmile.points as point}
                  <circle
                    class="smile-hit"
                    cx={point.x}
                    cy={point.y}
                    r="9"
                    role="presentation"
                    on:mouseenter={() => (hoverSmile = point)}
                  />
                {/each}
                <text class="smile-label" x="2" y="14">{pct(ivSmile.maxIv)}</text>
                <text class="smile-label" x="2" y={ivSmile.height - 20}>{pct(ivSmile.minIv)}</text>
                <text class="smile-label strike-min" x="32" y={ivSmile.height - 5}>{fmt(ivSmile.minStrike, 0)}</text>
                <text class="smile-label strike-max" x={ivSmile.width - 8} y={ivSmile.height - 5}>{fmt(ivSmile.maxStrike, 0)}</text>
              </svg>
            </div>
          {:else}
            <p class="muted">No front slice available.</p>
          {/if}
        </article>

        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "chain"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header">
          <h3>Options Chain</h3>
          <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
            {#each result?.expiries ?? [] as expiry}
              <option value={expiry}>{formatExpiry(expiry)} / {daysToExpiry(expiry)}D</option>
            {/each}
          </select>
        </div>
        {#if chainRows.length}
          <table class="chain-table">
            <thead>
              <tr>
                <th>C OI</th><th>C Δ</th><th>C IV</th><th>Call</th><th class="strike-cell">Strike</th><th>Mny</th><th>Put</th><th>P IV</th><th>P Δ</th><th>P OI</th><th>Strategy</th>
              </tr>
            </thead>
            <tbody>
              {#each chainRows as row}
                {@const callItm = row.distancePct != null && row.distancePct < 0}
                {@const putItm = row.distancePct != null && row.distancePct > 0}
                <tr class:atm={row.strike === overview.atmPair?.strike}>
                  <td class:itm={callItm}>{fmt(row.callOpenInterest, 0)}</td>
                  <td class:itm={callItm}>{fmt(row.callDelta, 3)}</td>
                  <td class:itm={callItm}>{pct(row.callIv)}</td>
                  <td class:itm={callItm}>{money(row.callMidpoint)}</td>
                  <td class="strike-cell">{fmt(row.strike, 2)}</td>
                  <td class={rowClass(row.distancePct)}>{signedPct(row.distancePct)}</td>
                  <td class:itm={putItm}>{money(row.putMidpoint)}</td>
                  <td class:itm={putItm}>{pct(row.putIv)}</td>
                  <td class:itm={putItm}>{fmt(row.putDelta, 3)}</td>
                  <td class:itm={putItm}>{fmt(row.putOpenInterest, 0)}</td>
                  <td class="action-cell">
                    <button type="button" on:click={() => addLeg(row, "call")}>+C</button>
                    <button type="button" on:click={() => addLeg(row, "put")}>+P</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted pad">Load a snapshot to inspect the chain.</p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Chain Context</h3>
          <div class="metric-list">
            <div><span>Expiry</span><strong>{formatExpiry(activeExpiry)}</strong></div>
            <div><span>DTE</span><strong>{activeExpiry ? daysToExpiry(activeExpiry) : "N/A"}</strong></div>
            <div><span>Rows</span><strong>{chainRows.length}</strong></div>
            <div><span>ATM Pair</span><strong>{fmt(overview.atmPair?.strike, 2)}</strong></div>
            <div><span>Straddle</span><strong>{money(overview.atmPair?.straddleMidpoint)}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "surface"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel surface-hero">
          <div class="panel-head">
            <h3>IV Surface</h3>
          </div>
          <Surface3D
            strikes={result?.strikes ?? []}
            expiries={result?.expiries ?? []}
            grid={result?.iv_grid ?? []}
            dte={(result?.expiries ?? []).map((expiry) => daysToExpiry(expiry))}
            {atmStrikeIndex}
          />
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <h3>Surface Grid</h3>
            {#if hoveredSurface && result}
              <span class="surface-readout">
                {formatExpiry(result.expiries[hoveredSurface.row])} · {fmt(result.strikes[hoveredSurface.col], 1)} · {pct(result.iv_grid[hoveredSurface.row]?.[hoveredSurface.col])}
              </span>
            {/if}
          </div>
          {#if result?.expiries.length && result.strikes.length}
            <div class="surface-scroll">
              <table class="surface-table" on:mouseleave={() => (hoveredSurface = null)}>
                <thead>
                  <tr>
                    <th>Expiry</th>
                    {#each result.strikes as strike, colIndex}
                      <th class:atm-strike={atmStrikeIndex === colIndex} class:col-hi={hoveredSurface?.col === colIndex}>{fmt(strike, 1)}</th>
                    {/each}
                  </tr>
                </thead>
                <tbody>
                  {#each result.expiries as expiry, rowIndex}
                    <tr class:row-hi={hoveredSurface?.row === rowIndex}>
                      <th>{formatExpiry(expiry)}<small>{daysToExpiry(expiry)}D</small></th>
                      {#each result.iv_grid[rowIndex] ?? [] as value, colIndex}
                        <td
                          style={heatStyle(value)}
                          class:cross={hoveredSurface?.row === rowIndex || hoveredSurface?.col === colIndex}
                          class:cell-hi={hoveredSurface?.row === rowIndex && hoveredSurface?.col === colIndex}
                          on:mouseenter={() => (hoveredSurface = { row: rowIndex, col: colIndex })}
                        >{pct(value)}</td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="muted pad">Load a max-depth surface snapshot to inspect expiry/strike volatility.</p>
          {/if}
        </article>
      </div>

      <div class="support-column">
        <article class="panel">
          <h3>
            Term Structure
            {#if hoverTerm}
              <span class="smile-readout">{hoverTerm.dte}D · {pct(hoverTerm.iv)}</span>
            {/if}
          </h3>
          {#if termCurve}
            <div class="smile-chart">
              <svg
                viewBox={`0 0 ${termCurve.width} ${termCurve.height}`}
                role="img"
                aria-label="ATM term structure curve"
                on:mouseleave={() => (hoverTerm = null)}
              >
                <line class="smile-axis" x1="34" y1={termCurve.height - 20} x2={termCurve.width - 10} y2={termCurve.height - 20} />
                <path class="smile-area" d={termCurve.areaPath} />
                <path class="smile-line" d={termCurve.linePath} />
                {#each termCurve.points as point}
                  <circle class="smile-dot" cx={point.x} cy={point.y} r="1.8" />
                {/each}
                {#if hoverTerm}
                  <line class="smile-guide" x1={hoverTerm.x} y1="10" x2={hoverTerm.x} y2={termCurve.height - 20} />
                  <circle class="smile-dot hover" cx={hoverTerm.x} cy={hoverTerm.y} r="3.4" />
                {/if}
                {#each termCurve.points as point}
                  <circle
                    class="smile-hit"
                    cx={point.x}
                    cy={point.y}
                    r="10"
                    role="presentation"
                    on:mouseenter={() => (hoverTerm = point)}
                  />
                {/each}
                <text class="smile-label" x="2" y="14">{pct(termCurve.maxIv)}</text>
                <text class="smile-label" x="2" y={termCurve.height - 24}>{pct(termCurve.minIv)}</text>
                <text class="smile-label" x="34" y={termCurve.height - 6}>{termCurve.points[0].dte}D</text>
                <text class="smile-label strike-max" x={termCurve.width - 10} y={termCurve.height - 6}>{termCurve.points[termCurve.points.length - 1].dte}D</text>
              </svg>
            </div>
          {:else}
            <p class="muted">No term structure available.</p>
          {/if}
        </article>

        <article class="panel">
          <h3>Skew By Expiry</h3>
          <div class="compact-table">
            <table>
              <thead><tr><th>Expiry</th><th>Put</th><th>Call</th><th>Spread</th></tr></thead>
              <tbody>
                {#each skewRows as row}
                  <tr>
                    <td>{formatExpiry(row.expiry)}</td>
                    <td class={rowClass(row.putSkew)}>{signedPct(row.putSkew)}</td>
                    <td class={rowClass(row.callSkew)}>{signedPct(row.callSkew)}</td>
                    <td class={rowClass(row.wingSpread)}>{signedPct(row.wingSpread)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>

        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "realized_implied"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header"><h3>Realized vs IV</h3></div>
        {#if realizedRows.some((row) => row.realizedVol != null)}
          <table>
            <thead><tr><th>Window</th><th>Realized Vol</th><th>Front ATM IV</th><th>IV Premium</th><th>Obs</th></tr></thead>
            <tbody>
              {#each realizedRows as row}
                <tr>
                  <td>{row.window}D</td>
                  <td>{pct(row.realizedVol)}</td>
                  <td>{pct(surfaceStats.frontAtmIv)}</td>
                  <td class={rowClass(row.spreadToFrontIv)}>{signedPct(row.spreadToFrontIv)}</td>
                  <td>{row.observationCount}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted pad">No underlying price history is loaded. Open a single-ticker Equity Research context first, then return to Options.</p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Boundary</h3>
          <div class="metric-list">
            <div><span>Implied Source</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
            <div><span>Realized Source</span><strong>{underlyingPricePoints.length ? "Research price history" : "N/A"}</strong></div>
            <div><span>Price Points</span><strong>{underlyingPricePoints.length}</strong></div>
            <div><span>Front ATM IV</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "distribution"}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Front Expiry Implied Distribution</h3>
        {#if distributionBuckets.length}
          <div class="distribution">
            {#each distributionBuckets as bucket}
              <div class="dist-row">
                <span>{bucket.label}</span>
                <div class="bar"><div class="fill" style={`width:${(bucket.probability / maxDistributionProbability) * 100}%`}></div></div>
                <strong>{pct(bucket.probability, 1)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">Load a surface with spot and front ATM IV to inspect the first-pass distribution proxy.</p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Assumptions</h3>
          <div class="metric-list">
            <div><span>Method</span><strong>Lognormal proxy</strong></div>
            <div><span>Expiry</span><strong>{formatExpiry(surfaceStats.frontExpiry)}</strong></div>
            <div><span>DTE</span><strong>{surfaceStats.frontExpiry ? daysToExpiry(surfaceStats.frontExpiry) : "N/A"}</strong></div>
            <div><span>Vol Input</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "strategies"}
    <div class="workspace-grid">
      <article class="panel">
        <div class="panel-head">
          <h3>Strategy Builder</h3>
          <div class="builder-controls">
            <select bind:value={selectedSide}>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
            <select bind:value={selectedOptionType}>
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
            <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
              {#each result?.expiries ?? [] as expiry}
                <option value={expiry}>{formatExpiry(expiry)}</option>
              {/each}
            </select>
            <button type="button" on:click={clearStrategy} disabled={!strategyLegs.length}>Clear</button>
          </div>
        </div>

        <div class="strategy-layout">
          <div class="compact-table chain-pick">
            <table>
              <thead><tr><th>Strike</th><th>Call</th><th>Put</th><th>Add</th></tr></thead>
              <tbody>
                {#each chainRows as row}
                  <tr class:atm={row.strike === overview.atmPair?.strike}>
                    <td>{fmt(row.strike, 2)}</td>
                    <td>{money(row.callMidpoint)}</td>
                    <td>{money(row.putMidpoint)}</td>
                    <td><button type="button" on:click={() => addLeg(row)}>Add</button></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>

          <div class="legs-panel">
            <h4>Legs</h4>
            {#if strategyLegs.length}
              {#each strategyLegs as leg}
                <div class="leg-row">
                  <span>{leg.side.toUpperCase()} {leg.optionType.toUpperCase()}</span>
                  <strong>{formatExpiry(leg.expiry)} {fmt(leg.strike, 2)} @ {money(leg.premium)}</strong>
                  <button type="button" on:click={() => removeLeg(leg.id)}>Remove</button>
                </div>
              {/each}
            {:else}
              <p class="muted">Add legs from the chain to calculate expiry payoff.</p>
            {/if}
          </div>
        </div>
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Payoff Matrix</h3>
          <div class="payoff-matrix">
            {#each strategyPayoff.points as point}
              <div style={payoffCellStyle(point.payoff)}>
                <span>{fmt(point.underlyingPrice, 0)}</span>
                <strong>{signedMoney(point.payoff)}</strong>
              </div>
            {/each}
          </div>
          <div class="metric-list">
            <div><span>Net Premium</span><strong>{signedMoney(strategyPayoff.netPremium)}</strong></div>
            <div><span>Max Profit</span><strong>{strategyPayoff.maxProfit == null ? "Open" : signedMoney(strategyPayoff.maxProfit)}</strong></div>
            <div><span>Max Loss</span><strong>{strategyPayoff.maxLoss == null ? "Open" : signedMoney(strategyPayoff.maxLoss)}</strong></div>
            <div><span>Breakevens</span><strong>{strategyPayoff.breakevens.length ? strategyPayoff.breakevens.map((value) => fmt(value, 2)).join(", ") : "N/A"}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {/if}
</section>

{#snippet DiagnosticsPanel(result: IvSurface | null, session: IvSessionStatus | null, status: SystemStatus | null, sessionLoading: boolean)}
  <article class="panel diagnostics-panel">
    <h3>Data & Source</h3>
    <div class="metric-list">
      <div><span>Provider</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
      <div><span>Backend Mode</span><strong>{status?.market_data_mode ?? result?.collection?.market_data_mode ?? "unknown"}</strong></div>
      <div><span>Session</span><strong>{sessionLoading ? "loading" : session?.running ? "running" : session?.status_text ?? "idle"}</strong></div>
      <div><span>Cells</span><strong>{result?.quality ? `${result.quality.observed_surface_cells}/${result.quality.expected_surface_cells}` : "N/A"}</strong></div>
      <div><span>Lines</span><strong>{result?.collection ? `${result.collection.estimated_total_market_data_lines}/${result.collection.configured_market_data_line_budget}` : "N/A"}</strong></div>
      <div><span>Updated</span><strong>{shortTime(result?.timestamp)}</strong></div>
    </div>
    {#if result?.transformation_note}
      <p class="note">{result.transformation_note}</p>
    {/if}
    {#if result?.warnings?.length || result?.messages?.length || session?.messages?.length}
      <div class="warning-list">
        {#each [...(result?.warnings ?? []), ...(result?.messages ?? []), ...(session?.messages ?? [])].slice(0, 4) as message}
          <div>{message}</div>
        {/each}
      </div>
    {/if}
  </article>
{/snippet}

<style>
  .view,
  .workspace-grid,
  .primary-column,
  .support-column,
  .metric-list,
  .warning-list,
  .slice-list,
  .distribution,
  .strategy-layout,
  .legs-panel {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.55fr) minmax(20rem, 0.72fr);
    align-items: start;
  }

  .overview-grid {
    grid-template-columns: minmax(0, 1.35fr) minmax(22rem, 0.65fr);
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    min-width: 0;
  }

  .header-panel {
    padding: 0.55rem 0.65rem;
  }

  .header-top,
  .mode-row,
  .header-actions,
  .source-strip,
  .panel-head,
  .builder-controls,
  .bar-row,
  .dist-row,
  .metric-list > div,
  .leg-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.65rem;
  }

  .header-top {
    align-items: end;
    margin-bottom: 0.5rem;
  }

  .header-actions,
  .builder-controls {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .mode-row {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .eyebrow,
  span,
  .muted,
  th,
  small {
    color: var(--text-2);
  }

  .eyebrow,
  th {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  h2,
  h3,
  h4,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.05rem;
    line-height: 1.2;
  }

  h3 {
    font-size: 0.88rem;
  }

  h4 {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong {
    color: var(--text-0);
    font-weight: 650;
  }

  button,
  input,
  select {
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    min-height: 28px;
    padding: 0.24rem 0.52rem;
    font: inherit;
    font-size: 0.82rem;
    border-radius: 2px;
  }

  button {
    cursor: pointer;
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
  }

  .primary-action {
    border-color: color-mix(in srgb, var(--accent) 34%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .symbol-control {
    display: grid;
    gap: 0.18rem;
  }

  .symbol-control span {
    font-size: 0.66rem;
    text-transform: uppercase;
  }

  .symbol-control input {
    width: 8rem;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(6, auto);
    border: 1px solid var(--panel-strong);
    width: fit-content;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    white-space: nowrap;
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button.selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .source-strip {
    flex: 1;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .source-strip > div {
    min-width: 5.8rem;
    display: grid;
    gap: 0.08rem;
    text-align: right;
  }

  .source-strip span,
  .metric span {
    font-size: 0.66rem;
    text-transform: uppercase;
  }

  .kpi-panel {
    padding: 0;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .metric {
    min-width: 0;
    padding: 0.55rem 0.7rem;
    border-right: 1px solid var(--divider);
    display: grid;
    gap: 0.16rem;
  }

  .metric:last-child {
    border-right: 0;
  }

  .metric small {
    font-size: 0.69rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-header {
    min-height: 30px;
    padding: 0.28rem 0.7rem;
    border-bottom: 1px solid var(--divider);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

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
  }

  td {
    color: var(--text-1);
  }

  tbody tr:hover td {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  tr.atm td,
  th.atm-strike {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  /* Option chain: calls left, strike center, puts right. */
  .chain-table .strike-cell {
    font-weight: 700;
    color: var(--text-0);
    text-align: center;
    background: var(--bg-1);
    border-left: 1px solid var(--panel-strong);
    border-right: 1px solid var(--panel-strong);
  }

  /* In-the-money side shaded blue (call side when strike < spot, put side when strike > spot). */
  .chain-table td.itm {
    background: color-mix(in srgb, var(--accent) 11%, transparent);
  }

  /* ATM row in accent amber, overriding ITM shading. */
  .chain-table tr.atm td {
    color: var(--warning);
    background: color-mix(in srgb, var(--warning) 18%, transparent);
  }

  th small {
    display: block;
    margin-top: 0.08rem;
    font-size: 0.62rem;
    letter-spacing: 0;
  }

  .surface-scroll {
    overflow: auto;
    max-height: 42vh;
  }

  .surface-hero {
    padding: 0.5rem 0.6rem 0.55rem;
  }

  .surface-hero .panel-head {
    margin-bottom: 0.1rem;
  }

  .surface-readout {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.02em;
  }

  .surface-table td {
    cursor: crosshair;
  }

  .surface-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--bg-1);
  }

  .surface-table tbody th {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--bg-1);
  }

  .surface-table thead th:first-child {
    z-index: 2;
  }

  .surface-table th.col-hi,
  .surface-table tr.row-hi > th {
    color: var(--accent);
  }

  .surface-table td.cross {
    box-shadow: inset 0 0 0 9999px color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .surface-table td.cell-hi {
    box-shadow: inset 0 0 0 9999px color-mix(in srgb, var(--accent) 26%, transparent);
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .compact-table {
    overflow: auto;
  }

  .compact-table th,
  .compact-table td {
    padding: 0.28rem 0.42rem;
  }

  .action-cell {
    display: flex;
    gap: 0.25rem;
  }

  .pad {
    padding: 0.6rem 0.75rem;
  }

  .bar {
    flex: 1;
    min-width: 4rem;
    height: 0.42rem;
    background: var(--panel-strong);
  }

  .fill {
    height: 100%;
    background: var(--chart-primary);
  }

  .bar-row,
  .dist-row,
  .metric-list > div,
  .warning-list > div {
    border-top: 1px solid var(--divider);
    padding-top: 0.3rem;
  }

  .split-panel {
    padding: 0;
    overflow: hidden;
  }

  .split-panel .panel-head {
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--divider);
  }

  .payoff-strip,
  .payoff-matrix {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(4.8rem, 1fr));
    border: 1px solid var(--divider);
  }

  .payoff-strip > div,
  .payoff-matrix > div {
    min-height: 3rem;
    padding: 0.38rem;
    border-right: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
    display: grid;
    gap: 0.18rem;
  }

  .payoff-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .payoff-meta {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-2);
  }

  .payoff-controls select {
    min-height: 24px;
    padding: 0.1rem 0.42rem;
    font-size: 0.74rem;
  }

  .payoff-heatmap-wrap {
    overflow: auto;
    max-height: 60vh;
  }

  .payoff-heatmap {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.66rem;
  }

  .payoff-heatmap th,
  .payoff-heatmap td {
    padding: 0.16rem 0.32rem;
    text-align: right;
    border-bottom: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .payoff-heatmap thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--bg-1);
    color: var(--text-2);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .payoff-heatmap td {
    color: var(--text-0);
  }

  .payoff-heatmap .price-col {
    position: sticky;
    left: 0;
    text-align: left;
    color: var(--text-1);
    font-weight: 650;
    background: var(--bg-1);
  }

  .payoff-heatmap thead .price-col {
    z-index: 2;
  }

  .payoff-heatmap tr.atm .price-col {
    color: var(--accent);
  }

  .payoff-heatmap .move-col {
    color: var(--text-2);
  }

  .smile-chart {
    width: 100%;
  }

  .smile-chart svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .smile-axis {
    stroke: var(--divider);
    stroke-width: 1;
  }

  .smile-atm {
    stroke: var(--accent);
    stroke-width: 1;
    stroke-dasharray: 3 3;
    opacity: 0.55;
  }

  .smile-area {
    fill: color-mix(in srgb, var(--chart-primary) 15%, transparent);
    stroke: none;
  }

  .smile-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.6;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }

  .smile-dot {
    fill: var(--chart-primary);
  }

  .smile-dot.atm {
    fill: var(--accent);
  }

  .smile-dot.hover {
    fill: var(--text-0);
    stroke: var(--chart-primary);
    stroke-width: 1.4;
    vector-effect: non-scaling-stroke;
  }

  .smile-guide {
    stroke: var(--accent);
    stroke-width: 1;
    stroke-dasharray: 2 2;
    opacity: 0.7;
  }

  .smile-hit {
    fill: transparent;
    pointer-events: all;
    cursor: crosshair;
  }

  .smile-readout {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.02em;
    margin-left: 0.4rem;
  }

  .smile-label {
    fill: var(--text-2);
    font-size: 8px;
  }

  .smile-label.strike-max {
    text-anchor: end;
  }

  .strategy-layout {
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.8fr);
    align-items: start;
  }

  .chain-pick {
    max-height: 58vh;
  }

  .legs-panel {
    border-left: 1px solid var(--divider);
    padding-left: 0.75rem;
  }

  .alert-panel {
    border-color: color-mix(in srgb, var(--warning) 44%, var(--panel-border));
    background: color-mix(in srgb, var(--warning) 8%, var(--panel-bg));
  }

  .alert-panel h3 {
    color: var(--warning);
  }

  .leg-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.35rem;
  }

  .leg-row strong {
    font-size: 0.78rem;
  }

  .diagnostics-panel .note {
    color: var(--text-1);
    line-height: 1.45;
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
  }

  .warning-list > div {
    color: var(--warning);
    line-height: 1.35;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1180px) {
    .workspace-grid,
    .overview-grid,
    .strategy-layout {
      grid-template-columns: 1fr;
    }

    .kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .mode-bar {
      grid-template-columns: repeat(3, auto);
    }

    .legs-panel {
      border-left: 0;
      padding-left: 0;
    }
  }

  @media (max-width: 760px) {
    .header-top,
    .mode-row,
    .header-actions,
    .source-strip {
      align-items: stretch;
      flex-direction: column;
    }

    .source-strip > div {
      text-align: left;
    }

    .mode-bar {
      grid-template-columns: 1fr;
      width: 100%;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }
  }
</style>
