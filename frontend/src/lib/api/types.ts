export type WorkspaceMode = "portfolio" | "research";

export type TabId = "portfolio" | "research" | "macro" | "prediction_markets" | "risk" | "iv";

export type MacroMode = "snapshot" | "cross_asset" | "rates_policy";
export type MacroRegion = "US" | "Global";
export type MacroTimeframe = "1M" | "3M" | "6M" | "1Y";
export type MacroTheme = "all" | "growth" | "inflation" | "policy" | "recession_risk";

export interface MacroContextState {
  mode: MacroMode;
  region: MacroRegion;
  timeframe: MacroTimeframe;
  theme: MacroTheme;
  comparisonRegion: MacroRegion | null;
}

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

export interface BaseCurrencyResponse extends SystemStatus {
  lines: string[];
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
  instrument_id: string | null;
  display_symbol: string | null;
  exchange: string | null;
  primary_exchange: string | null;
  provider: string | null;
  provider_id: string | null;
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
  instrument_id: string | null;
  display_symbol: string | null;
}

export interface ResearchSummary {
  total_return: number | null;
  annual_return: number | null;
  annual_vol: number | null;
  max_drawdown: number | null;
  beta: number | null;
  correlation: number | null;
}

export interface ResearchStructure {
  total_weight: number | null;
  top_weight: number | null;
  top5_weight: number | null;
  concentration_hhi: number | null;
  effective_positions: number | null;
  aligned_symbol_count: number;
}

export interface ResearchCoverage {
  available_symbols: string[];
  missing_symbols: string[];
  benchmark_overlap_count: number;
}

export interface ResearchConstituent {
  symbol: string;
  weight: number;
  instrument_id: string | null;
  display_symbol: string | null;
  total_return: number | null;
  annual_vol: number | null;
  max_drawdown: number | null;
  weighted_return: number | null;
}

export interface ResearchResult {
  scope_type: string;
  benchmark_symbol: string;
  primary_symbol: string | null;
  observations_count: number;
  snapshot: PortfolioSnapshot | null;
  performance_points: TimeSeriesPoint[];
  benchmark_points: TimeSeriesPoint[];
  primary_price_points: TimeSeriesPoint[];
  weights: ResearchWeightPoint[];
  summary: ResearchSummary;
  structure: ResearchStructure;
  coverage: ResearchCoverage;
  constituents: ResearchConstituent[];
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
  covered_risk_basis_value: number | null;
  risk_basis_value: number | null;
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
  instrument_id: string | null;
  display_symbol: string | null;
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
  sample_paths: Record<string, IndexedValuePoint[]>;
}

export interface ExcludedAsset {
  symbol: string;
  instrument_id: string | null;
  display_symbol: string | null;
  reason: string;
}

export interface RiskResult {
  metrics: RiskMetrics;
  portfolio_return_points: TimeSeriesPoint[];
  benchmark_return_points: TimeSeriesPoint[];
  contributions: RiskContribution[];
  monte_carlo: RiskMonteCarloCharts;
  excluded_assets: ExcludedAsset[];
  warnings: string[];
}

export interface PredictionMarketOutcome {
  outcome_id: string;
  label: string;
  probability: number | null;
  token_id: string | null;
  resolved: boolean | null;
  winner: boolean | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionMarketFreshness {
  status: string;
  is_stale: boolean;
  is_broken: boolean;
  reason: string | null;
  last_history_point_at: string | null;
  retrieval_age_seconds: number | null;
  history_lag_seconds: number | null;
}

export interface PredictionMarket {
  market_id: string;
  venue: string;
  title: string;
  subtitle: string | null;
  description: string | null;
  status: string;
  category: string | null;
  event_id: string | null;
  event_title: string | null;
  series_id: string | null;
  series_title: string | null;
  provider_market_id: string;
  provider_condition_id: string | null;
  provider_event_id: string | null;
  provider_series_id: string | null;
  slug: string | null;
  end_time: string | null;
  open_time: string | null;
  close_time: string | null;
  current_probability: number | null;
  probability_label: string | null;
  volume: number | null;
  volume_24h: number | null;
  liquidity: number | null;
  open_interest: number | null;
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  recent_price_change: number | null;
  resolved_probability: number | null;
  resolution_outcome: boolean | null;
  image_url: string | null;
  resolution_source: string | null;
  outcomes: PredictionMarketOutcome[];
  tags: string[];
  freshness: PredictionMarketFreshness | null;
  research_score: number | null;
  research_rationale: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionVenueStatus {
  venue: string;
  status: string;
  message: string | null;
  total_markets: number;
  matched_markets: number;
  visible_markets: number;
  stale_markets: number;
  broken_markets: number;
  retrieved_at: string | null;
}

export interface PredictionMarketListResponse {
  markets: PredictionMarket[];
  venues: PredictionVenueStatus[];
  warnings: string[];
}

export interface PredictionProbabilityPoint {
  timestamp: string;
  probability: number;
  volume: number | null;
  open_interest: number | null;
  bid: number | null;
  ask: number | null;
  spread: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionProbabilityHistoryResponse {
  market_id: string;
  points: PredictionProbabilityPoint[];
}

export interface PredictionWalletActivity {
  participant_id: string;
  display_name: string;
  venue: string;
  side: string;
  outcome_label: string | null;
  trade_count: number;
  total_size: number;
  average_price: number | null;
  first_seen: string | null;
  last_seen: string | null;
  current_edge: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionWalletSummary {
  market_id: string;
  venue: string;
  concentration_hhi: number | null;
  top_participant_share: number | null;
  total_trades: number;
  total_notional: number;
  participants: PredictionWalletActivity[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface RelatedPredictionMarket {
  market_id: string;
  venue: string;
  title: string;
  probability: number | null;
  price_gap: number | null;
  relationship: string;
  note: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface RelatedPredictionMarketListResponse {
  market_id: string;
  related: RelatedPredictionMarket[];
}

export interface PredictionCalibrationBucket {
  label: string;
  sample_size: number;
  average_probability: number | null;
  realized_frequency: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionCalibrationObservation {
  market_id: string;
  title: string;
  probability: number;
  outcome: boolean;
  settled_at: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface PredictionCalibrationSummary {
  venue: string;
  sample_size: number;
  buckets: PredictionCalibrationBucket[];
  observations: PredictionCalibrationObservation[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroSeriesPoint {
  timestamp: string;
  value: number;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroMetric {
  metric_id: string;
  label: string;
  value: number | null;
  display_value: string | null;
  unit: string | null;
  delta_value: number | null;
  delta_display: string | null;
  series_id: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroCurveNode {
  tenor: string;
  current_value: number | null;
  prior_value: number | null;
  change_bps: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroEvent {
  event_id: string;
  title: string;
  category: string;
  region: string;
  scheduled_at: string;
  relative_label: string | null;
  importance: string;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroSeriesHistory {
  series_id: string;
  title: string;
  region: string;
  unit: string | null;
  frequency: string;
  theme: string;
  mode_tags: string[];
  points: MacroSeriesPoint[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroSnapshotCard {
  card_id: string;
  title: string;
  subtitle: string | null;
  summary: string;
  mode_target: string;
  target_theme: string | null;
  metrics: MacroMetric[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroDivergence {
  divergence_id: string;
  theme: string;
  region: string;
  headline: string;
  summary: string;
  score: number;
  label: string;
  metrics: MacroMetric[];
  series_ids: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroThemeComparison {
  theme: string;
  headline: string;
  summary: string;
  agreement_label: string;
  metrics: MacroMetric[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroRatesPolicySummary {
  headline: string;
  summary: string;
  policy_metrics: MacroMetric[];
  curve_nodes: MacroCurveNode[];
  real_yield_metrics: MacroMetric[];
  events: MacroEvent[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroSnapshot {
  region: string;
  timeframe: string;
  theme: string;
  comparison_region: string | null;
  available_regions: string[];
  available_timeframes: string[];
  available_themes: string[];
  snapshot_cards: MacroSnapshotCard[];
  rates_policy: MacroRatesPolicySummary | null;
  cross_asset: MacroThemeComparison[];
  top_divergences: MacroDivergence[];
  upcoming_events: MacroEvent[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroDivergenceListResponse {
  region: string;
  timeframe: string;
  theme: string;
  divergences: MacroDivergence[];
}

export interface MacroEventsResponse {
  region: string;
  events: MacroEvent[];
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
