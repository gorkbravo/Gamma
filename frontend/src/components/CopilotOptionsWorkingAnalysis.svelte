<script lang="ts">
  import type { CopilotWorkingAnalysis } from "../lib/api/types";

  export let analysis: CopilotWorkingAnalysis;

  type JsonRecord = Record<string, unknown>;
  type ComparisonRow = {
    expiry: string | null;
    daysToExpiry: number | null;
    historicalVolatility: number | null;
    impliedVolatility: number | null;
    volatilityPremium: number | null;
    impliedToHistoricalRatio: number | null;
    impliedMovePct: number | null;
    status: string;
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
  const decimal = (value: unknown, digits = 2) => {
    const numeric = number(value);
    return numeric == null ? "N/A" : numeric.toFixed(digits);
  };
  const money = (value: unknown) => {
    const numeric = number(value);
    return numeric == null
      ? "N/A"
      : numeric.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  const formatExpiry = (value: string | null) => {
    if (!value) return "N/A";
    const match = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(value);
    return match ? `${match[1]}/${match[2]}/${match[3]}` : value;
  };
  const statusLabel = (value: string) => value.replace(/_/g, " ");

  $: entity = record(analysis.entity);
  $: inputs = record(analysis.inputs);
  $: outputs = record(analysis.outputs);
  $: summary = record(outputs.summary);
  $: quality = record(outputs.quality);
  $: collection = record(outputs.collection);
  $: requested = record(outputs.requested);
  $: symbol = text(entity.symbol) ?? text(entity.ticker) ?? text(outputs.symbol) ?? "Options";
  $: rows = (Array.isArray(outputs.expiry_comparisons) ? outputs.expiry_comparisons : [])
    .map((value): ComparisonRow => {
      const row = record(value);
      return {
        expiry: text(row.expiry),
        daysToExpiry: number(row.days_to_expiry),
        historicalVolatility: number(row.historical_volatility),
        impliedVolatility: number(row.atm_implied_volatility),
        volatilityPremium: number(row.volatility_premium),
        impliedToHistoricalRatio: number(row.implied_to_historical_ratio),
        impliedMovePct: number(row.implied_move_pct),
        status: text(row.comparison_status) ?? "unknown"
      };
    });
  $: warnings = Array.from(
    new Set(
      [
        ...analysis.warnings,
        ...(Array.isArray(outputs.warnings) ? outputs.warnings : [])
      ].map((value) => String(value)).filter(Boolean)
    )
  );
</script>

<article class="panel temporary-analysis" aria-label="Temporary Copilot Options working analysis">
  <header class="temporary-header">
    <div>
      <span class="temporary-label">Temporary</span>
      <strong>{analysis.title}</strong>
    </div>
    <span class="temporary-scope">Session ephemeral · unsaved</span>
  </header>

  <div class="temporary-summary">
    <div><span>Symbol</span><strong>{symbol}</strong></div>
    <div><span>Spot</span><strong class:absent={money(outputs.spot) === "N/A"}>{money(outputs.spot)}</strong></div>
    <div><span>Expiries</span><strong>{number(summary.expiry_count) ?? rows.length}</strong></div>
    <div><span>Comparable</span><strong>{number(summary.ok_count) ?? 0}</strong></div>
    <div><span>Avg IV premium</span><strong class:absent={pct(summary.average_volatility_premium) === "N/A"}>{pct(summary.average_volatility_premium)}</strong></div>
  </div>

  <div class="comparison-table" role="region" aria-label={`${symbol} temporary realized versus implied comparison`}>
    <table>
      <thead>
        <tr>
          <th>Expiry</th>
          <th>DTE</th>
          <th>Historical vol</th>
          <th>ATM IV</th>
          <th>IV premium</th>
          <th>IV / historical</th>
          <th>Implied move</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row}
          <tr>
            <td>{formatExpiry(row.expiry)}</td>
            <td class:absent={row.daysToExpiry == null}>{row.daysToExpiry ?? "N/A"}</td>
            <td class:absent={row.historicalVolatility == null}>{pct(row.historicalVolatility)}</td>
            <td class:absent={row.impliedVolatility == null}>{pct(row.impliedVolatility)}</td>
            <td
              class:absent={row.volatilityPremium == null}
              class:positive={(row.volatilityPremium ?? 0) > 0}
              class:negative={(row.volatilityPremium ?? 0) < 0}
            >{pct(row.volatilityPremium)}</td>
            <td class:absent={row.impliedToHistoricalRatio == null}>{decimal(row.impliedToHistoricalRatio)}×</td>
            <td class:absent={row.impliedMovePct == null}>{pct(row.impliedMovePct)}</td>
            <td><span class="status-tag" data-status={row.status}>{statusLabel(row.status)}</span></td>
          </tr>
        {:else}
          <tr><td colspan="8" class="empty">No comparable expiry rows were retained.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>

  <footer class="temporary-footer">
    <div class="boundary-grid">
      <div><span>Depth</span><strong>{text(requested.depth_preset) ?? text(inputs.depth_preset) ?? "N/A"}</strong></div>
      <div><span>Market data</span><strong>{text(collection.market_data_mode) ?? text(requested.market_data_mode) ?? "N/A"}</strong></div>
      <div><span>Observed cells</span><strong>{number(quality.observed_surface_cells) ?? "N/A"}</strong></div>
      <div><span>Provider</span><strong>{analysis.source_provider}</strong></div>
    </div>
    <p>
      Opened from Copilot as <code>{analysis.contract_version}</code>. This view does not save an
      option set, place an order, or create trading authority.
    </p>
    <p>{analysis.origin}</p>
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
  .temporary-summary span,
  .boundary-grid span,
  th {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .temporary-label {
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
    padding: var(--space-1) var(--space-2);
  }

  .temporary-header strong,
  .temporary-summary strong,
  .boundary-grid strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .temporary-header strong {
    font-size: var(--text-base);
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

  .comparison-table {
    overflow: auto;
    border-bottom: 1px solid var(--divider);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
  }

  td {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  td.empty {
    color: var(--text-2);
    text-align: center;
  }

  .status-tag {
    display: inline-block;
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--divider);
    border-radius: 999px;
    color: var(--text-1);
    font-family: var(--display-font);
    font-size: var(--text-2xs);
    text-transform: uppercase;
  }

  .status-tag[data-status="ok"] {
    color: var(--positive);
    border-color: color-mix(in srgb, var(--positive) 45%, transparent);
  }

  .positive { color: var(--positive) !important; }
  .negative { color: var(--negative) !important; }

  .temporary-footer {
    display: grid;
    gap: var(--space-2);
  }

  .boundary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .boundary-grid > div {
    display: grid;
    gap: var(--space-1);
  }

  .temporary-footer p,
  summary,
  li {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .temporary-footer code { color: var(--text-1); }
  summary { cursor: pointer; }
  ul { margin: var(--space-2) 0 0; padding-left: var(--space-5); }

  @media (max-width: 980px) {
    .temporary-summary,
    .boundary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--space-3);
    }

    .temporary-summary > div,
    .temporary-summary > div:not(:first-child) {
      padding: 0;
      border-right: 0;
    }
  }

  @media (max-width: 620px) {
    .temporary-header {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
