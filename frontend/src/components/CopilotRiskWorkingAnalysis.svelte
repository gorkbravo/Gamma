<script lang="ts">
  import type { CopilotWorkingAnalysis } from "../lib/api/types";

  export let analysis: CopilotWorkingAnalysis;

  type JsonRecord = Record<string, unknown>;
  type WorkingLeg = {
    symbol: string;
    weight: number | null;
    secType: string | null;
  };

  const record = (value: unknown): JsonRecord =>
    value != null && typeof value === "object" && !Array.isArray(value)
      ? (value as JsonRecord)
      : {};
  const number = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const text = (value: unknown): string | null => {
    const normalized = String(value ?? "").trim();
    return normalized || null;
  };
  const pct = (value: unknown, digits = 1) => {
    const numeric = number(value);
    return numeric == null ? "N/A" : `${(numeric * 100).toFixed(digits)}%`;
  };
  const currency = (value: unknown) => {
    const numeric = number(value);
    return numeric == null
      ? "N/A"
      : `USD ${Math.round(numeric).toLocaleString("en-US")}`;
  };
  const bps = (value: unknown) => {
    const numeric = number(value);
    return numeric == null ? "N/A" : `${numeric >= 0 ? "+" : ""}${numeric.toFixed(0)} bps`;
  };

  $: entity = record(analysis.entity);
  $: inputs = record(analysis.inputs);
  $: outputs = record(analysis.outputs);
  $: portfolioComparison = record(outputs.portfolio_comparison);
  $: scenario = Object.keys(record(outputs.risk_scenario)).length
    ? record(outputs.risk_scenario)
    : outputs.shock_parameters
      ? outputs
      : {};
  $: contribution = Object.keys(record(outputs.risk_contribution)).length
    ? record(outputs.risk_contribution)
    : !outputs.shock_parameters && outputs.metrics
      ? outputs
      : {};
  $: portfolioInput = record(inputs.portfolio);
  $: rawLegs = Array.isArray(entity.legs)
    ? entity.legs
    : Array.isArray(portfolioInput.legs)
      ? portfolioInput.legs
      : [];
  $: legs = rawLegs
    .map((value): WorkingLeg | null => {
      const leg = record(value);
      const symbol = text(leg.symbol);
      return symbol
        ? {
            symbol,
            weight: number(leg.weight),
            secType: text(leg.sec_type)
          }
        : null;
    })
    .filter((value): value is WorkingLeg => value != null);
  $: shockParameters = record(scenario.shock_parameters);
  $: shockProxy = record(scenario.shock_proxy);
  $: metrics = Object.keys(record(scenario.metrics)).length
    ? record(scenario.metrics)
    : Object.keys(record(contribution.metrics)).length
      ? record(contribution.metrics)
      : record(portfolioComparison.relative);
  $: scenarioLabel =
    text(scenario.scenario_label) ??
    text(record(inputs.risk_scenario).scenario_label) ??
    null;
  $: scenarioType = text(scenario.scenario_type) ?? text(shockParameters.scenario_type);
  $: hasScenario = Boolean(scenarioLabel || scenarioType || Object.keys(shockParameters).length);
  $: warnings = Array.from(
    new Set(
      [
        ...analysis.warnings,
        ...(Array.isArray(scenario.warnings) ? scenario.warnings : []),
        ...(Array.isArray(contribution.warnings) ? contribution.warnings : [])
      ].map((value) => String(value)).filter(Boolean)
    )
  );
</script>

<article class="panel temporary-analysis" aria-label="Temporary Copilot Risk working analysis">
  <header class="temporary-header">
    <div>
      <span class="temporary-label">Temporary</span>
      <strong>{analysis.title}</strong>
    </div>
    <span class="temporary-scope">Session ephemeral · unsaved</span>
  </header>

  <div class="temporary-summary">
    <div><span>Portfolio</span><strong>{text(entity.portfolio_label) ?? text(entity.label) ?? "Risk snapshot"}</strong></div>
    <div><span>Benchmark</span><strong>{text(entity.benchmark_symbol) ?? text(portfolioInput.benchmark_symbol) ?? "N/A"}</strong></div>
    <div><span>Legs</span><strong>{legs.length}</strong></div>
    <div><span>Coverage</span><strong class:absent={pct(metrics.risk_coverage_ratio) === "N/A"}>{pct(metrics.risk_coverage_ratio)}</strong></div>
    <div><span>Estimated return</span><strong class:negative={(number(shockProxy.estimated_return_pct) ?? 0) < 0}>{pct(shockProxy.estimated_return_pct)}</strong></div>
  </div>

  <div class="temporary-grid">
    <section class="temporary-section">
      <h3>Portfolio definition</h3>
      <table>
        <thead><tr><th>Symbol</th><th>Weight</th><th>Type</th></tr></thead>
        <tbody>
          {#each legs as leg}
            <tr><td>{leg.symbol}</td><td class:absent={pct(leg.weight) === "N/A"}>{pct(leg.weight)}</td><td class:absent={leg.secType == null}>{leg.secType ?? "N/A"}</td></tr>
          {:else}
            <tr><td colspan="3" class="empty">No temporary legs were retained.</td></tr>
          {/each}
        </tbody>
      </table>
    </section>

    <section class="temporary-section">
      <h3>{hasScenario ? "Scenario inputs" : "Risk result"}</h3>
      {#if hasScenario}
        <dl>
          <div><dt>Scenario</dt><dd>{scenarioLabel ?? scenarioType ?? "Baseline"}</dd></div>
          <div><dt>Rate shift</dt><dd>{bps(shockParameters.rate_shift_bps)}</dd></div>
          <div><dt>Equity shock</dt><dd>{pct(shockParameters.equity_shock_pct)}</dd></div>
          <div><dt>Duration proxy</dt><dd>{number(shockParameters.duration_proxy_years) == null ? "Position-specific" : `${number(shockParameters.duration_proxy_years)?.toFixed(1)} years`}</dd></div>
          <div><dt>Estimated P&amp;L</dt><dd class:negative={(number(shockProxy.estimated_pnl) ?? 0) < 0}>{currency(shockProxy.estimated_pnl)}</dd></div>
        </dl>
      {:else}
        <dl>
          <div><dt>Annual vol</dt><dd>{pct(metrics.annual_vol)}</dd></div>
          <div><dt>Historical VaR</dt><dd>{currency(metrics.historical_var)}</dd></div>
          <div><dt>Concentration</dt><dd>{number(metrics.concentration_hhi)?.toFixed(3) ?? "N/A"}</dd></div>
        </dl>
      {/if}
    </section>
  </div>

  <footer class="temporary-footer">
    <p>
      Opened from Copilot as <code>{analysis.contract_version}</code>. This view does not save,
      rebalance, trade, or alter the live account or a saved research portfolio.
    </p>
    <p>{analysis.source_provider} · {analysis.origin}</p>
    {#if warnings.length}
      <details>
        <summary>{warnings.length} warning{warnings.length === 1 ? "" : "s"}</summary>
        <ul>{#each warnings as warning}<li>{warning}</li>{/each}</ul>
      </details>
    {/if}
  </footer>
</article>

<style>
  .temporary-analysis {
    padding: 0;
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-border));
  }

  .temporary-header,
  .temporary-summary,
  .temporary-grid,
  .temporary-footer {
    padding: var(--space-4) var(--space-5);
  }

  .temporary-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .temporary-header > div {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .temporary-label,
  .temporary-scope,
  h3,
  dt,
  th {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .temporary-label {
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
    padding: var(--space-1) var(--space-2);
  }

  .temporary-header strong {
    color: var(--text-0);
    font-size: var(--text-base);
    font-weight: 600;
  }

  .temporary-summary {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    border-bottom: 1px solid var(--divider);
  }

  .temporary-summary > div {
    display: grid;
    gap: var(--space-1);
    padding-right: var(--space-4);
    border-right: 1px solid var(--divider);
  }

  .temporary-summary > div:not(:first-child) { padding-left: var(--space-4); }
  .temporary-summary > div:last-child { border-right: 0; }
  .temporary-summary span { color: var(--text-2); font-size: var(--text-2xs); }
  .temporary-summary strong { color: var(--text-0); font-size: var(--text-sm); font-weight: 600; }

  .temporary-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    gap: var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .temporary-section { min-width: 0; }
  h3 { margin: 0 0 var(--space-3); font-weight: 600; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--divider); text-align: left; }
  td { color: var(--text-1); font-size: var(--text-sm); }
  td.empty { color: var(--text-2); text-align: center; }

  dl { margin: 0; display: grid; gap: var(--space-2); }
  dl div { display: flex; justify-content: space-between; gap: var(--space-4); padding-bottom: var(--space-2); border-bottom: 1px solid var(--divider); }
  dt { font-weight: 500; }
  dd { margin: 0; color: var(--text-0); font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
  .negative { color: var(--negative) !important; }

  .temporary-footer { display: grid; gap: var(--space-2); }
  .temporary-footer p, summary, li { margin: 0; color: var(--text-2); font-size: var(--text-xs); line-height: var(--leading-snug); }
  .temporary-footer code { color: var(--text-1); }
  summary { cursor: pointer; }
  ul { margin: var(--space-2) 0 0; padding-left: var(--space-5); }

  @media (max-width: 980px) {
    .temporary-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); }
    .temporary-summary > div,
    .temporary-summary > div:not(:first-child) { padding: 0; border-right: 0; }
    .temporary-grid { grid-template-columns: 1fr; }
  }
</style>
