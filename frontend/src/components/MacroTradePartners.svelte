<script lang="ts">
  import type { MacroSnapshot, MacroTradePartnerRow } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;

  $: tradePartners = snapshot?.trade_partners ?? null;
  $: vizPartners = (tradePartners?.partners ?? []).slice(0, 14);
  $: maxFlow = Math.max(
    1,
    ...vizPartners.flatMap((partner) => [partner.export_value ?? 0, partner.import_value ?? 0, partner.total_trade_value ?? 0])
  );
  $: vizNodes = buildVizNodes(vizPartners);
  $: centerLabel = tradePartners?.region ?? snapshot?.region ?? "US";

  const center = 320;
  const radius = 226;
  const labelRadius = 278;

  function buildVizNodes(partners: MacroTradePartnerRow[]) {
    return partners.map((partner, index) => {
      const angle = -90 + (360 / Math.max(partners.length, 1)) * index;
      const radians = (angle * Math.PI) / 180;
      const x = center + Math.cos(radians) * radius;
      const y = center + Math.sin(radians) * radius;
      const labelX = center + Math.cos(radians) * labelRadius;
      const labelY = center + Math.sin(radians) * labelRadius;
      return {
        partner,
        x,
        y,
        labelX,
        labelY,
        textAnchor: labelX < center - 20 ? "end" : labelX > center + 20 ? "start" : "middle",
        flag: flagForPartner(partner),
        shortName: shortPartnerName(partner),
        exportWidth: flowWidth(partner.export_value),
        importWidth: flowWidth(partner.import_value),
        exportPath: flowPath(x, y, -10),
        importPath: flowPath(x, y, 10),
      };
    });
  }

  function flowWidth(value: number | null | undefined) {
    const normalized = Math.max(0, Number(value ?? 0)) / maxFlow;
    return Math.max(1.2, Math.min(7.5, 1.2 + normalized * 6.3));
  }

  function flowPath(x: number, y: number, offset: number) {
    const midX = (center + x) / 2;
    const midY = (center + y) / 2;
    const dx = x - center;
    const dy = y - center;
    const length = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const controlX = midX + (-dy / length) * offset;
    const controlY = midY + (dx / length) * offset;
    return `M ${center} ${center} Q ${controlX.toFixed(1)} ${controlY.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }

  function flagForPartner(partner: MacroTradePartnerRow) {
    const code = partner.partner_code.toUpperCase();
    const name = partner.partner_name.toLowerCase();
    const flags: Record<string, string> = {
      AU: "🇦🇺",
      BR: "🇧🇷",
      CA: "🇨🇦",
      CH: "🇨🇭",
      CN: "🇨🇳",
      DE: "🇩🇪",
      ES: "🇪🇸",
      EU: "🇪🇺",
      FR: "🇫🇷",
      GB: "🇬🇧",
      IE: "🇮🇪",
      IN: "🇮🇳",
      IT: "🇮🇹",
      JP: "🇯🇵",
      KR: "🇰🇷",
      MX: "🇲🇽",
      NL: "🇳🇱",
      SG: "🇸🇬",
      TW: "🇹🇼",
      UK: "🇬🇧",
      VN: "🇻🇳",
      VIE: "🇻🇳",
    };
    if (flags[code]) return flags[code];
    if (name.includes("european union")) return "🇪🇺";
    if (name.includes("mexico")) return "🇲🇽";
    if (name.includes("canada")) return "🇨🇦";
    if (name.includes("china")) return "🇨🇳";
    if (name.includes("taiwan")) return "🇹🇼";
    if (name.includes("vietnam")) return "🇻🇳";
    if (name.includes("japan")) return "🇯🇵";
    if (name.includes("korea")) return "🇰🇷";
    if (name.includes("germany")) return "🇩🇪";
    if (name.includes("switzerland")) return "🇨🇭";
    if (name.includes("singapore")) return "🇸🇬";
    return code.slice(0, 3);
  }

  function regionFlag(region: string) {
    if (region === "US") return "🇺🇸";
    if (region === "EU") return "🇪🇺";
    return "GLB";
  }

  function shortPartnerName(partner: MacroTradePartnerRow) {
    const normalized = partner.partner_name.toLowerCase();
    const code = partner.partner_code.toUpperCase();
    const labels: Record<string, string> = {
      CA: "Can.",
      CH: "Switz.",
      CN: "China",
      EU: "EU",
      GB: "UK",
      IE: "Ire.",
      MX: "Mex.",
      NL: "Neth.",
      SG: "Sing.",
      TW: "Tai.",
      UK: "UK",
      VN: "Viet.",
      VIE: "Viet.",
    };
    if (labels[code]) return labels[code];
    if (normalized.includes("european union")) return "EU";
    if (normalized.includes("vietnam")) return "Viet.";
    if (partner.partner_name.length <= 7) return partner.partner_name;
    return `${partner.partner_name.slice(0, 5)}.`;
  }
</script>

<div class="workspace-grid">
  <div class="primary-column">
    <article class="panel viz-panel">
      <div class="viz-header">
        <div>
          <p class="eyebrow">Trade Viz</p>
          <h3>{tradePartners?.headline ?? "Trade partner exposure"}</h3>
        </div>
        <div class="legend" aria-label="Trade flow legend">
          <span><i class="export-dot"></i>Exports</span>
          <span><i class="import-dot"></i>Imports</span>
        </div>
      </div>

      {#if vizNodes.length}
        <div class="radial-shell" aria-label="Radial trade partner visualization">
          <svg viewBox="0 0 640 640" role="img" aria-label={`${centerLabel} trade partner flows`}>
            <title>{centerLabel} trade partner exports and imports by partner</title>
            <g class="rings" aria-hidden="true">
              <circle cx="320" cy="320" r="84"></circle>
              <circle cx="320" cy="320" r="150"></circle>
              <circle cx="320" cy="320" r="216"></circle>
            </g>
            <g class="spokes" aria-hidden="true">
              {#each vizNodes as node}
                <line x1="320" y1="320" x2={node.x} y2={node.y}></line>
              {/each}
            </g>
            <g class="flows">
              {#each vizNodes as node}
                <path class="flow export-flow" d={node.exportPath} stroke-width={node.exportWidth}>
                  <title>{node.partner.partner_name} exports: {node.partner.export_value_display ?? "N/A"}</title>
                </path>
                <path class="flow import-flow" d={node.importPath} stroke-width={node.importWidth}>
                  <title>{node.partner.partner_name} imports: {node.partner.import_value_display ?? "N/A"}</title>
                </path>
              {/each}
            </g>
            <g class="partner-nodes">
              {#each vizNodes as node}
                <g>
                  <rect x={node.x - 24} y={node.y - 15} width="48" height="30" rx="3"></rect>
                  <text x={node.x} y={node.y + 5} text-anchor="middle">{node.flag}</text>
                  <text class="partner-label" x={node.labelX} y={node.labelY} text-anchor={node.textAnchor}>
                    {node.shortName}
                  </text>
                  <text class="partner-share" x={node.labelX} y={node.labelY + 17} text-anchor={node.textAnchor}>
                    {node.partner.share_of_total_display ?? ""}
                  </text>
                </g>
              {/each}
            </g>
            <g class="center-node">
              <rect x="284" y="293" width="72" height="54" rx="4"></rect>
              <text x="320" y="316" text-anchor="middle">{regionFlag(centerLabel)}</text>
              <text class="center-label" x="320" y="336" text-anchor="middle">{centerLabel}</text>
            </g>
          </svg>
        </div>
      {:else}
        <p class="empty">No trade partner flow data</p>
      {/if}
    </article>

    <article class="panel table-panel">
      <div class="table-panel-header">Trade Partners</div>
      {#if tradePartners?.partners?.length}
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Partner</th>
              <th>Exports</th>
              <th>Imports</th>
              <th>Total</th>
              <th>Trade Balance</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {#each tradePartners.partners as partner}
              <tr>
                <td>{partner.rank}</td>
                <td>
                  <strong>{flagForPartner(partner)} {partner.partner_name}</strong>
                  <span>{partner.partner_code}</span>
                </td>
                <td class:absent={partner.export_value_display == null}>{partner.export_value_display ?? "N/A"}</td>
                <td class:absent={partner.import_value_display == null}>{partner.import_value_display ?? "N/A"}</td>
                <td class:absent={partner.total_trade_value_display == null}>{partner.total_trade_value_display ?? "N/A"}</td>
                <td class:positive={(partner.trade_balance ?? 0) > 0} class:negative={(partner.trade_balance ?? 0) < 0}>{partner.trade_balance_display ?? "N/A"}</td>
                <td class:absent={partner.share_of_total_display == null}>{partner.share_of_total_display ?? "N/A"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No trade partner context</p>
      {/if}
    </article>

    {#if tradePartners?.summary}
      <article class="panel">
        <p class="eyebrow">Trade Linkages</p>
        <h3>{tradePartners.headline}</h3>
        <p class="summary">{tradePartners.summary}</p>
      </article>
    {/if}
  </div>

  <div class="support-column">
    <article class="panel">
      <p class="eyebrow">Research Focus</p>
      <p class="summary">{tradePartners?.research_focus ?? "No research focus available."}</p>
    </article>

    <article class="panel">
      <p class="eyebrow">Coverage</p>
      {#if tradePartners?.caveats?.length}
        <ul>
          {#each tradePartners.caveats as caveat}
            <li>{caveat}</li>
          {/each}
        </ul>
      {:else}
        <p class="summary">No caveats reported.</p>
      {/if}
    </article>
  </div>
</div>

<style>

  .viz-panel {
    padding: var(--space-5);
  }

  .viz-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-5);
    min-height: 34px;
  }

  .legend {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    color: var(--text-2);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .legend i {
    width: 0.72rem;
    height: 0.18rem;
    display: inline-block;
  }

  .export-dot {
    background: var(--warning);
  }

  .import-dot {
    background: var(--accent);
  }

  .radial-shell {
    min-height: 420px;
    border-top: 1px solid var(--divider);
    display: grid;
    place-items: center;
    overflow: hidden;
  }

  svg {
    width: min(100%, 680px);
    aspect-ratio: 1;
    display: block;
    font-family: var(--app-font), monospace;
  }

  .rings circle {
    fill: none;
    stroke: var(--divider);
    stroke-width: 1;
    opacity: 0.74;
  }

  .spokes line {
    stroke: var(--divider);
    stroke-width: 1;
    opacity: 0.48;
  }

  .flow {
    fill: none;
    stroke-linecap: round;
    opacity: 0.74;
  }

  .export-flow {
    stroke: var(--warning);
  }

  .import-flow {
    stroke: var(--accent);
  }

  .partner-nodes rect,
  .center-node rect {
    fill: var(--surface-1);
    stroke: var(--panel-strong);
    stroke-width: 1;
  }

  .center-node rect {
    fill: var(--surface-0);
    stroke: var(--warning);
  }

  svg text {
    fill: var(--text-0);
    font-size: var(--text-lg);
    font-weight: 700;
    letter-spacing: 0;
  }

  .partner-label {
    font-size: var(--text-md);
  }

  .partner-share {
    fill: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .center-label {
    fill: var(--warning);
    font-size: var(--text-md);
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-panel-header {
    min-height: 26px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    border-bottom: 1px solid var(--divider);
    padding: var(--space-3) var(--space-4);
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  td {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  td strong,
  h3 {
    color: var(--text-0);
  }

  td span {
    display: block;
    margin-top: 0.08rem;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  h3,
  .summary,
  .empty,
  ul {
    margin: 0;
  }

  .summary,
  .empty,
  li {
    color: var(--text-1);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  ul {
    padding-left: var(--space-6);
  }

  @media (max-width: 980px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }

    .radial-shell {
      min-height: 340px;
    }
  }
</style>
