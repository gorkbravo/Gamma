export type TabId = "portfolio" | "research" | "risk" | "iv";

export interface ConnectionState {
  connected: boolean;
  status_text: string;
  action_text: string;
  action_enabled: boolean;
  active_account: string | null;
}

export interface SystemStatus {
  healthy: boolean;
  app_name: string;
  backend: string;
  mock_mode: boolean;
  base_currency: string;
  market_data_mode: string;
  connection: ConnectionState;
  cached_symbols: string[];
}

export interface DiagnosticsResponse {
  generated_at: string;
  mock_mode: boolean;
  base_currency: string;
  market_data_mode: string;
  connection: ConnectionState;
  history_cache: Record<string, number>;
  local_history_entries: number;
  local_history_path: string;
  recent_errors: string[];
  cached_symbols: string[];
  research_scope_type: string;
  research_primary_symbol: string | null;
  research_synthetic_count: number;
  iv_running: boolean;
  iv_status_text: string;
  iv_active_symbol: string | null;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
}

export interface Position {
  symbol: string;
  sec_type: string;
  currency: string;
  quantity: number;
  avg_cost: number | null;
  market_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  weight: number | null;
  base_market_value: number | null;
  fx_rate: number | null;
}

export interface PortfolioSnapshot {
  timestamp: string;
  base_currency: string;
  account_summary: Record<string, string>;
  positions: Position[];
  total_market_value: number | null;
  total_cash: number | null;
  net_liquidation: number | null;
  day_pnl: number | null;
  day_pnl_pct: number | null;
  day_pnl_source: string | null;
  warnings: string[];
}

export interface PortfolioHistoryPoint {
  timestamp: string;
  portfolio_value: number;
  net_liquidation: number | null;
  market_value: number | null;
  cash: number | null;
  base_currency: string | null;
}

export interface PortfolioHistoryResponse {
  source: string;
  points: PortfolioHistoryPoint[];
}

export interface PortfolioPerformanceResponse {
  benchmark_symbol: string;
  benchmark_source: string;
  performance_points: TimeSeriesPoint[];
  benchmark_points: TimeSeriesPoint[];
  portfolio_base_value: number | null;
  missing_symbols: string[];
  day_pnl: number | null;
  day_pnl_pct: number | null;
  day_pnl_source: string | null;
  message: string | null;
  warnings: string[];
}

export interface ResearchWeightPoint {
  symbol: string;
  weight: number;
}

export interface ResearchSummary {
  total_return: number | null;
  annual_return: number | null;
  annual_vol: number | null;
  max_drawdown: number | null;
  beta: number | null;
  correlation: number | null;
}

export interface ResearchResult {
  scope_type: string;
  benchmark_symbol: string;
  observations_count: number;
  snapshot: PortfolioSnapshot | null;
  performance_points: TimeSeriesPoint[];
  benchmark_points: TimeSeriesPoint[];
  primary_price_points: TimeSeriesPoint[];
  weights: ResearchWeightPoint[];
  summary: ResearchSummary;
  warnings: string[];
}

export interface RiskMetrics {
  alpha: number;
  lookback_days: number;
  horizon_days: number;
  portfolio_value: number;
  historical_var: number | null;
  historical_cvar: number | null;
  parametric_var: number | null;
  daily_vol: number | null;
  annual_vol: number | null;
  max_drawdown: number | null;
  beta: number | null;
  correlation: number | null;
  alpha_annual: number | null;
  covered_portfolio_value: number | null;
  risk_coverage_ratio: number | null;
  historical_var_total_estimate: number | null;
  historical_cvar_total_estimate: number | null;
  parametric_var_total_estimate: number | null;
  monte_carlo_model: string | null;
  monte_carlo_horizon_days: number | null;
  monte_carlo_num_simulations: number | null;
  monte_carlo_var: number | null;
  monte_carlo_cvar: number | null;
  monte_carlo_var_total_estimate: number | null;
  monte_carlo_cvar_total_estimate: number | null;
  aligned_obs_count: number | null;
  benchmark_overlap_count: number | null;
  concentration_hhi: number | null;
  top5_weight: number | null;
  effective_bets: number | null;
}

export interface RiskContribution {
  symbol: string;
  weight: number | null;
  daily_vol: number | null;
  variance_contribution_pct: number | null;
  marginal_contribution_to_risk: number | null;
  component_var: number | null;
}

export interface IndexedValuePoint {
  index: number;
  value: number;
}

export interface RiskMonteCarloCharts {
  terminal_returns: number[];
  fan_percentiles: Record<string, IndexedValuePoint[]>;
}

export interface ExcludedAsset {
  symbol: string;
  reason: string;
}

export interface RiskResult {
  metrics: RiskMetrics;
  portfolio_return_points: TimeSeriesPoint[];
  contributions: RiskContribution[];
  monte_carlo: RiskMonteCarloCharts;
  excluded_assets: ExcludedAsset[];
  warnings: string[];
}

export interface IvSurface {
  symbol: string;
  timestamp: string;
  snapshot_available: boolean;
  spot: number | null;
  expiries: string[];
  strikes: number[];
  iv_grid: number[][];
  delayed: boolean | null;
  points: number;
  warnings: string[];
  messages: string[];
}

export interface ActionResponse {
  success: boolean;
  lines: string[];
}

export interface IvSessionStatus {
  running: boolean;
  status_text: string;
  active_symbol: string | null;
  market_data_mode: string;
  surface: IvSurface;
  messages: string[];
}
