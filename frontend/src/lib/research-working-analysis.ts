import type { CopilotWorkingAnalysis } from "./api/types";

export type ResearchBasketSnapshot = {
  positions: Array<{ symbol: string; weight: number }>;
  benchmark: string;
  lookback: number;
  metrics: Record<string, number | null>;
  constituents: Array<{ symbol: string; weight: number; total_return: number | null; annual_vol: number | null }>;
  performance: Array<{ time: number; value: number }>;
  benchmarkPoints: Array<{ time: number; value: number }>;
  coverage: { benchmark_overlap_count: number; benchmark_available: boolean };
};

// Gamma's persisted UTC timestamps can omit the trailing timezone marker.
export function researchScopeTime(value: string): number {
  return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`);
}

export function researchBasketSnapshot(analysis: CopilotWorkingAnalysis | null, now = Date.now()): ResearchBasketSnapshot | null {
  if (!analysis || analysis.status !== "active" || analysis.state_scope !== "session_ephemeral"
    || analysis.analysis_type !== "research_basket_analysis" || analysis.owning_tab !== "equity_research"
    || analysis.owning_mode !== "scope_analysis" || analysis.materialization.durable !== false
    || analysis.materialization.payload_contract !== "copilot.research-scope-working-analysis.v1"
    || !analysis.expires_at || !Number.isFinite(researchScopeTime(analysis.expires_at)) || researchScopeTime(analysis.expires_at) <= now) return null;
  const input = analysis.inputs;
  const output = analysis.outputs;
  const positions = input.positions as ResearchBasketSnapshot["positions"];
  const points = (value: unknown): value is Array<{ time: number; value: number }> => Array.isArray(value)
    && value.length <= 400 && value.every(p => p && Number.isFinite(p.time) && Number.isFinite(p.value));
  if (!Array.isArray(positions) || positions.length < 1 || positions.length > 100
    || !positions.every(p => p && typeof p.symbol === "string" && Number.isFinite(p.weight) && p.weight > 0)
    || typeof input.benchmark_symbol !== "string" || !Number.isInteger(input.lookback_days)
    || !["ready", "degraded"].includes(String(output.status)) || !output.metrics || !output.coverage
    || !Array.isArray(output.top_constituents) || !output.top_constituents.every(row => row && typeof row.symbol === "string")
    || !points(output.performance_points) || !points(output.benchmark_points)) return null;
  return {
    positions, benchmark: input.benchmark_symbol, lookback: Number(input.lookback_days),
    metrics: output.metrics as ResearchBasketSnapshot["metrics"],
    constituents: output.top_constituents as ResearchBasketSnapshot["constituents"],
    performance: output.performance_points, benchmarkPoints: output.benchmark_points,
    coverage: output.coverage as ResearchBasketSnapshot["coverage"]
  };
}
