import type { CopilotWorkingAnalysis } from "./api/types";
import { researchScopeTime } from "./research-working-analysis";

export const retainedEvidenceModes = {
  equity_research: "scope_analysis", strategy_lab: "backtest_analyze", macro: "snapshot",
  crypto: "deep_dive", commodities: "curves_spreads"
} as const;
export type RetainedEvidenceTab = keyof typeof retainedEvidenceModes;
export type RetainedEvidenceTarget = { analysisId: string; tab: RetainedEvidenceTab; mode: string; retainedEvidence: true };
export const retainedEvidenceTools: Record<string, RetainedEvidenceTab> = {
  run_research_scope_analysis: "equity_research", run_strategy_lab_backtest: "strategy_lab",
  run_macro_series_analysis: "macro", get_macro_series_history_summary: "macro",
  run_crypto_token_analysis: "crypto", inspect_commodity_curve_fundamentals: "commodities"
};

export function retainedEvidenceTarget(analysis: CopilotWorkingAnalysis, now = Date.now()): RetainedEvidenceTarget | null {
  const tab = analysis.owning_tab as RetainedEvidenceTab;
  const target = analysis.materialization;
  if (analysis.analysis_type !== "retained_evidence" || analysis.status !== "active" || analysis.state_scope !== "session_ephemeral"
    || !Object.hasOwn(retainedEvidenceModes, tab) || retainedEvidenceModes[tab] !== analysis.owning_mode
    || retainedEvidenceTools[analysis.tool_id] !== tab
    || target.payload_contract !== "copilot.retained-evidence.v1" || target.durable !== false
    || target.target_tab !== tab || target.target_mode !== analysis.owning_mode
    || !analysis.expires_at || !Number.isFinite(researchScopeTime(analysis.expires_at)) || researchScopeTime(analysis.expires_at) <= now
    || !analysis.outputs.result || typeof analysis.outputs.result !== "object" || Array.isArray(analysis.outputs.result)
    || !Array.isArray(analysis.outputs.sources)) return null;
  return { analysisId: analysis.analysis_id, tab, mode: analysis.owning_mode, retainedEvidence: true };
}

export const evidenceLabel = (key: string) => key.replace(/_/g, " ").replace(/\b\w/, s => s.toUpperCase());
export function evidenceValue(value: unknown, key = ""): string {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "N/A";
    const fractions = ["total_return", "annual_return", "annualized_return", "annual_vol", "annual_volatility", "annualized_volatility", "max_drawdown", "weighted_return", "weight", "top_weight", "top5_weight", "total_weight"];
    if (fractions.includes(key)) return `${(value * 100).toFixed(2)}%`;
    if (key.endsWith("_pct") || /_pct_\d+d$/.test(key)) return `${value.toFixed(2)}%`;
    return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** Primary research fields; raw adapter metadata stays under Sources and method. */
export function evidenceSections(analysis: CopilotWorkingAnalysis): Array<{ title: string; value: unknown }> {
  const result = analysis.outputs.result as Record<string, unknown>;
  const pick = (...keys: string[]) => Object.fromEntries(keys.filter(key => key in result).map(key => [key, result[key]]));
  switch (analysis.tool_id) {
    case "run_macro_series_analysis":
    case "get_macro_series_history_summary":
      return [{ title: "Series and window", value: pick("title", "region", "unit", "frequency", "requested_timeframe", "observations") },
        { title: "Window statistics", value: pick("start", "latest", "change", "min_value", "max_value") },
        { title: "Recent observations", value: result.timeframe_points }];
    case "run_crypto_token_analysis":
      return [{ title: "Token and lookback", value: pick("name", "symbol", "days", "status") },
        { title: "Price history", value: result.history }, { title: "DEX liquidity", value: result.liquidity },
        { title: "Relative comparison", value: result.comparison }];
    case "inspect_commodity_curve_fundamentals":
      return [{ title: "Curve and spreads", value: result.curve }, { title: "Inventories", value: result.inventories },
        { title: "Price basis", value: result.price_reconciliation }, { title: "Events", value: result.events }];
    case "run_research_scope_analysis":
      return [{ title: "Scope", value: result.scope }, { title: "Performance", value: result.metrics },
        { title: "Constituents", value: result.top_constituents }, { title: "Structure and coverage", value: pick("structure", "coverage") }];
    default:
      return [{ title: "Performance", value: result.metrics ?? result.relative }, { title: "Period returns", value: result.period_returns },
        { title: "Benchmark and coverage", value: pick("benchmark", "coverage", "left", "right") }];
  }
}
