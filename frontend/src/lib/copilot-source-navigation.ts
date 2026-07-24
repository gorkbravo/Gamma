import type { CopilotSourceRef, CrossTabHandoffEnvelope, TabId } from "./api/types";

type SourceTarget = { tab: TabId; mode: string | null };

const SOURCE_TARGETS: Array<{ prefixes: string[]; target: SourceTarget }> = [
  { prefixes: ["portfolio."], target: { tab: "portfolio", mode: null } },
  { prefixes: ["risk."], target: { tab: "risk", mode: "overview" } },
  { prefixes: ["iv.", "options."], target: { tab: "iv", mode: "overview" } },
  { prefixes: ["macro."], target: { tab: "macro", mode: "snapshot" } },
  { prefixes: ["prediction."], target: { tab: "prediction_markets", mode: null } },
  { prefixes: ["crypto."], target: { tab: "crypto", mode: "overview" } },
  { prefixes: ["fundamentals."], target: { tab: "fundamentals", mode: "overview" } },
  { prefixes: ["commodities.", "commodity."], target: { tab: "commodities", mode: "overview" } },
  { prefixes: ["maritime.", "sealanes."], target: { tab: "maritime", mode: "live_map" } },
  { prefixes: ["strategy_lab."], target: { tab: "strategy_lab", mode: "backtest_analyze" } },
  { prefixes: ["research.", "equity_research."], target: { tab: "equity_research", mode: "overview" } },
  { prefixes: ["sitrep."], target: { tab: "sitrep", mode: null } }
];

function sourceTarget(source: CopilotSourceRef): SourceTarget | null {
  const identity = `${source.source_id} ${source.origin}`.toLowerCase();
  const mapping = SOURCE_TARGETS.find(({ prefixes }) => prefixes.some((prefix) => identity.includes(prefix)));
  if (!mapping) return null;

  let mode = mapping.target.mode;
  if (mapping.target.tab === "macro") {
    if (identity.includes("rate") || identity.includes("policy")) mode = "rates_policy";
    else if (identity.includes("event") || identity.includes("regime")) mode = "events_regimes";
  } else if (mapping.target.tab === "iv") {
    if (identity.includes("surface")) mode = "surface";
    else if (identity.includes("chain")) mode = "chain";
  } else if (mapping.target.tab === "fundamentals") {
    if (identity.includes("filing") || identity.includes("reference")) mode = "reference";
    else if (identity.includes("dcf")) mode = "dcf";
    else if (identity.includes("financial")) mode = "financials";
  } else if (mapping.target.tab === "commodities") {
    if (identity.includes("curve") || identity.includes("spread")) mode = "curves_spreads";
    else if (identity.includes("inventor") || identity.includes("fundamental")) mode = "inventories_fundamentals";
  } else if (mapping.target.tab === "maritime") {
    if (identity.includes("chokepoint")) mode = "chokepoints";
    else if (identity.includes("flow")) mode = "trade_flows";
    else if (identity.includes("vessel") || identity.includes("fleet")) mode = "fleet_monitoring";
  }
  return { tab: mapping.target.tab, mode };
}

export function buildCopilotSourceHandoff(
  source: CopilotSourceRef,
  priorHandoff: CrossTabHandoffEnvelope | null = null,
  warnings: string[] = []
): CrossTabHandoffEnvelope | null {
  const target = sourceTarget(source);
  if (!target) return null;
  const priorMatches =
    priorHandoff != null &&
    (priorHandoff.source_tab === target.tab || priorHandoff.intended_target_tab === target.tab);

  return {
    source_tab: "copilot",
    source_mode: "evidence",
    selected_entity: priorMatches ? priorHandoff.selected_entity : null,
    selected_timeframe: priorMatches ? priorHandoff.selected_timeframe : null,
    provider: source.provider,
    source: {
      source_provider: source.provider,
      retrieved_at: source.retrieved_at,
      origin: source.origin,
      transformation_note: source.description
    },
    warnings: [...(priorMatches ? priorHandoff.warnings : []), ...warnings],
    normalized_ids: {
      ...(priorMatches ? priorHandoff.normalized_ids : {}),
      copilot_source_id: source.source_id
    },
    timestamp: new Date().toISOString(),
    intended_target_tab: target.tab,
    intended_target_mode: priorMatches ? priorHandoff.source_mode ?? target.mode : target.mode
  };
}
