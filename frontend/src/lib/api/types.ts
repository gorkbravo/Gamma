export type WorkspaceMode = "portfolio" | "research";

export type TabId =
  | "portfolio"
  | "sitrep"
  | "equity_research"
  | "strategy_lab"
  | "macro"
  | "commodities"
  | "prediction_markets"
  | "crypto"
  | "fundamentals"
  | "maritime"
  | "copilot"
  | "risk"
  | "iv";

export interface WorkspaceTabDefinition {
  id: TabId;
  label: string;
  pinned: boolean;
  defaultIndex: number;
}

export type WorkspaceTabOrderState = Record<WorkspaceMode, TabId[]>;

export type ActionKeybindingId =
  | "toggle_sidebar"
  | "refresh_view"
  | "open_settings"
  | "dismiss_surface"
  | "switch_portfolio_workspace"
  | "switch_research_workspace"
  | "previous_tab"
  | "next_tab"
  | "previous_mode"
  | "next_mode";

export interface ShortcutCombo {
  id: string;
  label: string;
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
}

export interface ActionKeybindingDefinition {
  id: ActionKeybindingId;
  label: string;
  description: string;
  combos: ShortcutCombo[];
}

export type MacroMode = "snapshot" | "cross_asset" | "rates_policy" | "events_regimes" | "trade_partners" | "country_compare";
export type EquityResearchMode =
  | "overview"
  | "scope_analysis"
  | "comparables"
  | "scenario_context"
  | "saved_equity_research";
export type StrategyLabMode = "composer" | "backtest_analyze" | "regime_stress" | "imports" | "saved_runs";
export type MacroRegion = "US" | "EU" | "Global";
export type MacroTimeframe = "1M" | "3M" | "6M" | "1Y";
export type MacroTheme = "all" | "growth" | "inflation" | "policy" | "recession_risk";

export type CommodityMode =
  | "overview"
  | "energy"
  | "metals"
  | "curves_spreads"
  | "inventories_fundamentals"
  | "events_cross_domain";

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

export interface ProviderUsageCall {
  provider_id: string;
  endpoint: string;
  status: string;
  cache_status: string | null;
  duration_ms: number;
  recorded_at: string;
  message: string | null;
}

export interface ProviderUsageSummary {
  provider_id: string;
  call_count: number;
  success_count: number;
  unavailable_count: number;
  error_count: number;
  cache_hit_count: number;
  cache_miss_count: number;
  average_duration_ms: number;
  last_status: string | null;
  last_message: string | null;
  last_error: string | null;
  last_called_at: string | null;
  endpoints: string[];
}

export interface ProviderUsageHealth {
  provider_id: string;
  display_name: string;
  health_status: string;
  health_label: string;
  expected_when: string;
  reason: string;
  action_label: string | null;
  call_count: number;
  success_count: number;
  unavailable_count: number;
  error_count: number;
  last_called_at: string | null;
}

export interface ProviderUsageResponse {
  generated_at: string;
  providers: ProviderUsageSummary[];
  health: ProviderUsageHealth[];
  recent_calls: ProviderUsageCall[];
  total_calls: number;
  source_provider: string;
  origin: string;
  transformation_note: string | null;
}

export interface NewsEventEntity {
  label: string;
  entity_type: string;
  normalized_id: string | null;
  symbol: string | null;
  metadata: Record<string, unknown>;
}

export interface NewsEventItem {
  normalized_id: string;
  title: string;
  url: string;
  source_provider: string;
  source_name: string;
  published_at: string;
  retrieved_at: string;
  origin: string;
  summary: string | null;
  source_domain: string | null;
  provider_item_id: string | null;
  detected_entities: NewsEventEntity[];
  tags: string[];
  freshness_label: string;
  warnings: string[];
  transformation_note: string | null;
}

export interface NewsEventFeedResponse {
  items: NewsEventItem[];
  source_provider: string;
  retrieved_at: string;
  origin: string;
  freshness_label: string;
  warnings: string[];
  transformation_note: string | null;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
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
  source_provider?: string;
  history_source_label?: string | null;
  freshness_label?: string;
}

export type ResearchOverviewMetricId = "return" | "volatility" | "beta" | "drawdown" | "relative_return";
export type ResearchOverviewSortId =
  | "market_cap_desc"
  | "universe_weight_desc"
  | "return_desc"
  | "volatility_desc"
  | "beta_desc"
  | "drawdown_desc";

export interface ResearchOverviewUniverseInstrument {
  symbol: string;
  label: string;
  group: string;
  sector: string;
  industry: string | null;
  weight: number;
  market_cap_usd: number | null;
  index_weight: number | null;
  sort_rank: number | null;
  currency: string;
  exchange: string;
  sec_type: string;
}

export interface ResearchOverviewUniverse {
  universe_id: string;
  label: string;
  description: string;
  instruments: ResearchOverviewUniverseInstrument[];
  limitations: string[];
  metadata_source_label: string;
  coverage_label: string;
  is_complete_universe: boolean;
}

export interface ResearchOverviewMetricOption {
  metric_id: ResearchOverviewMetricId;
  label: string;
  description: string;
}

export interface ResearchOverviewSortOption {
  sort_id: ResearchOverviewSortId;
  label: string;
  description: string;
}

export interface ResearchOverviewMetrics {
  total_return: number | null;
  annual_volatility: number | null;
  beta: number | null;
  max_drawdown: number | null;
  relative_return: number | null;
  latest_price: number | null;
  observation_count: number;
}

export interface ResearchOverviewNode {
  node_id: string;
  normalized_id: string;
  label: string;
  level: "group" | "instrument" | string;
  parent_id: string | null;
  group: string | null;
  sector: string | null;
  industry: string | null;
  symbol: string | null;
  instrument_id: string | null;
  weight: number | null;
  market_cap_usd: number | null;
  index_weight: number | null;
  sort_rank: number | null;
  size: number;
  metrics: ResearchOverviewMetrics;
  source_provider: string;
  retrieved_at: string;
  origin: string;
  transformation_note: string | null;
  freshness_label: string;
  warnings: string[];
}

export interface ResearchOverviewCoverage {
  instrument_count: number;
  priced_count: number;
  missing_symbols: string[];
  benchmark_symbol: string;
  benchmark_available: boolean;
  benchmark_observation_count: number;
  coverage_ratio: number;
  missing_count: number;
  thin_history_symbols: string[];
  min_observation_count: number;
  max_observation_count: number;
  coverage_label: string;
  history_source_label: string;
  metadata_source_label: string;
}

export interface ResearchOverviewRankItem {
  node_id: string;
  label: string;
  group: string | null;
  symbol: string | null;
  value: number | null;
}

export interface ResearchOverviewRankings {
  leaders: ResearchOverviewRankItem[];
  laggards: ResearchOverviewRankItem[];
  highest_volatility: ResearchOverviewRankItem[];
  highest_beta: ResearchOverviewRankItem[];
  largest_drawdowns: ResearchOverviewRankItem[];
}

export interface ResearchOverviewSummary {
  leading_group: ResearchOverviewRankItem | null;
  lagging_group: ResearchOverviewRankItem | null;
  highest_volatility_group: ResearchOverviewRankItem | null;
  coverage_note: string | null;
}

export interface ResearchOverviewResponse {
  universe_id: string;
  universe_label: string;
  universe_description: string;
  timeframe: string;
  lookback_days: number;
  benchmark_symbol: string;
  available_universes: ResearchOverviewUniverse[];
  available_timeframes: string[];
  metric_options: ResearchOverviewMetricOption[];
  sort_options: ResearchOverviewSortOption[];
  nodes: ResearchOverviewNode[];
  coverage: ResearchOverviewCoverage;
  rankings: ResearchOverviewRankings;
  summary: ResearchOverviewSummary;
  warnings: string[];
  source_provider: string;
  retrieved_at: string;
  origin: string;
  transformation_note: string | null;
  freshness_label: string;
  history_source_label: string;
  metadata_source_label: string;
  coverage_label: string;
}

export interface ResearchReturnMetrics {
  total_return: number | null;
  annual_return: number | null;
  annual_volatility: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown: number | null;
  max_drawdown_duration: number | null;
  observation_count: number;
  frequency: string;
  periods_per_year: number;
  start_date: string | null;
  end_date: string | null;
  benchmark_beta: number | null;
  benchmark_correlation: number | null;
  upside_capture: number | null;
  downside_capture: number | null;
}

export interface ResearchRollingPoint {
  timestamp: string;
  rolling_return: number | null;
  rolling_volatility: number | null;
  rolling_beta: number | null;
  rolling_correlation: number | null;
}

export interface ResearchPeriodReturn {
  period: string;
  value: number | null;
}

export interface StrategyLabResult {
  name: string;
  value_kind: "return" | "level" | string;
  benchmark_column: string | null;
  benchmark_value_kind: "return" | "level" | string;
  metrics: ResearchReturnMetrics;
  returns_points: TimeSeriesPoint[];
  equity_curve_points: TimeSeriesPoint[];
  drawdown_points: TimeSeriesPoint[];
  benchmark_points: TimeSeriesPoint[];
  benchmark_equity_curve_points: TimeSeriesPoint[];
  rolling_points: ResearchRollingPoint[];
  monthly_returns: ResearchPeriodReturn[];
  annual_returns: ResearchPeriodReturn[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string;
  origin: string;
  transformation_note: string | null;
  freshness_label: string;
}

export type ResearchObjectResolverCapability = "return_leg" | "benchmark" | "lens" | "overlay" | "reference_only";

export interface ResearchObjectReturnPoint {
  timestamp: string;
  value: number;
}

export interface GammaResearchObject {
  object_id: string;
  object_type: string;
  display_name: string;
  source_tab: string;
  source_mode: string | null;
  resolver_capabilities: ResearchObjectResolverCapability[];
  symbols: string[];
  constituents: Record<string, unknown>[];
  weights: Record<string, unknown>[];
  available_start: string | null;
  available_end: string | null;
  provider_summary: string | null;
  provenance: Record<string, unknown>;
  warnings: string[];
  return_points: ResearchObjectReturnPoint[];
}

export interface StrategyLabCompositionLegInput {
  object: GammaResearchObject;
  weight: number;
}

export interface StrategyLabCompositionResult extends StrategyLabResult {
  leg_contributions: Record<string, number>;
  lenses: GammaResearchObject[];
  overlays: GammaResearchObject[];
}

export interface ResearchComparisonLegResult {
  label: string;
  object_type: string;
  metrics: ResearchReturnMetrics;
  returns_points: TimeSeriesPoint[];
  normalized_nav_points: TimeSeriesPoint[];
  drawdown_points: TimeSeriesPoint[];
}

export interface ResearchCompareResult {
  left: ResearchComparisonLegResult;
  right: ResearchComparisonLegResult;
  left_observation_count: number;
  right_observation_count: number;
  aligned_observation_count: number;
  overlap_start: string | null;
  overlap_end: string | null;
  relative_return: number | null;
  volatility_difference: number | null;
  max_drawdown_difference: number | null;
  correlation: number | null;
  beta: number | null;
  relative_nav_points: TimeSeriesPoint[];
  relative_drawdown_points: TimeSeriesPoint[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string;
  origin: string;
  transformation_note: string | null;
  freshness_label: string;
}

export interface SavedResearchItem {
  id: string;
  schema_version: number;
  object_type: string;
  title: string;
  notes: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface SavedResearchListResponse {
  items: SavedResearchItem[];
}

export interface SavedResearchDeleteResponse {
  success: boolean;
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

export interface RiskFrontierWeight {
  symbol: string;
  instrument_id: string | null;
  display_symbol: string | null;
  weight: number;
}

export interface RiskFrontierPoint {
  label: string;
  kind:
    | "current"
    | "candidate"
    | "frontier"
    | "asset"
    | "risk_free"
    | "universe_frontier"
    | "universe_asset"
    | "universe_candidate"
    | "cached_equity_asset"
    | "cached_equity_frontier"
    | "cached_equity_candidate"
    | "cml"
    | "portfolio_cml"
    | string;
  annual_return: number;
  annual_vol: number;
  sharpe: number | null;
  weights: RiskFrontierWeight[];
  history_rows?: number | null;
  history_start?: string | null;
  history_end?: string | null;
  source_provider?: string | null;
}

export interface RiskCorrelationAsset {
  symbol: string;
  instrument_id: string | null;
  display_symbol: string | null;
}

export interface RiskCorrelationCell {
  row: string;
  column: string;
  correlation: number | null;
}

export interface RiskCorrelationMatrix {
  assets: RiskCorrelationAsset[];
  cells: RiskCorrelationCell[];
}

export interface RiskDependencyNetworkNode {
  symbol: string;
  label: string;
  cluster_id: number;
  is_portfolio: boolean;
  portfolio_weight: number | null;
  risk_contribution: number | null;
  annual_vol: number | null;
  degree: number;
  strength: number;
  centrality: number;
  source_provider: string | null;
}

export interface RiskDependencyNetworkEdge {
  source: string;
  target: string;
  partial_correlation: number;
  strength: number;
  sign: number;
}

export interface RiskDependencyNetworkCluster {
  cluster_id: number;
  label: string;
  node_count: number;
  portfolio_node_count: number;
  portfolio_weight: number;
  average_annual_vol: number | null;
  density: number;
  top_symbols: string[];
  central_symbols: string[];
}

export interface RiskDependencyNetwork {
  nodes: RiskDependencyNetworkNode[];
  edges: RiskDependencyNetworkEdge[];
  clusters: RiskDependencyNetworkCluster[];
  methodology: string | null;
  universe_size: number;
  observation_count: number;
  edge_threshold: number | null;
  warnings: string[];
  source_provider: string;
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
  frontier_points: RiskFrontierPoint[];
  correlation_matrix: RiskCorrelationMatrix;
  dependency_network: RiskDependencyNetwork;
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

export interface CryptoBasketConstituent {
  token_id: string;
  name: string | null;
  symbol: string | null;
  image_url: string | null;
}

export interface CryptoNarrativeBasket {
  basket_id: string;
  label: string;
  description: string | null;
  market_cap: number | null;
  market_cap_change_pct_24h: number | null;
  volume_24h: number | null;
  top_tokens: CryptoBasketConstituent[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoToken {
  token_id: string;
  symbol: string;
  name: string;
  image_url: string | null;
  chain: string | null;
  asset_platform_id: string | null;
  geckoterminal_network: string | null;
  contract_address: string | null;
  market_cap_rank: number | null;
  current_price: number | null;
  market_cap: number | null;
  fully_diluted_valuation: number | null;
  total_volume: number | null;
  circulating_supply: number | null;
  total_supply: number | null;
  max_supply: number | null;
  price_change_pct_24h: number | null;
  price_change_pct_7d: number | null;
  price_change_pct_30d: number | null;
  market_cap_change_pct_24h: number | null;
  high_24h: number | null;
  low_24h: number | null;
  homepage_url: string | null;
  description: string | null;
  categories: string[];
  narrative_labels: string[];
  layer_bucket: string | null;
  turnover_ratio_24h: number | null;
  fdv_premium_ratio: number | null;
  screen_score: number | null;
  screen_rationale: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoWorkspaceResponse {
  tokens: CryptoToken[];
  narratives: CryptoNarrativeBasket[];
  warnings: string[];
}

export interface CryptoPricePoint {
  timestamp: string;
  price: number;
  market_cap: number | null;
  total_volume: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoPriceHistoryResponse {
  token_id: string;
  points: CryptoPricePoint[];
}

export interface CryptoDexPool {
  pool_id: string;
  network: string;
  dex: string;
  pair_name: string;
  address: string;
  quote_token_symbol: string | null;
  base_token_price_usd: number | null;
  fdv_usd: number | null;
  market_cap_usd: number | null;
  reserve_usd: number | null;
  volume_24h: number | null;
  price_change_pct_24h: number | null;
  buys_24h: number;
  sells_24h: number;
  buyers_24h: number;
  sellers_24h: number;
  pool_created_at: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoDexLiquiditySummary {
  token_id: string;
  lookup_strategy: string;
  matched_networks: string[];
  total_reserve_usd: number | null;
  total_volume_24h: number | null;
  total_buys_24h: number;
  total_sells_24h: number;
  total_buyers_24h: number;
  total_sellers_24h: number;
  dominant_dex: string | null;
  pools: CryptoDexPool[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoComparison {
  subject_token_id: string;
  target_kind: string;
  target_id: string;
  target_label: string;
  shared_categories: string[];
  subject_price_change_pct_24h: number | null;
  target_price_change_pct_24h: number | null;
  price_gap_pct_24h: number | null;
  subject_price_change_pct_7d: number | null;
  target_price_change_pct_7d: number | null;
  price_gap_pct_7d: number | null;
  subject_price_change_pct_30d: number | null;
  target_price_change_pct_30d: number | null;
  price_gap_pct_30d: number | null;
  subject_market_cap: number | null;
  target_market_cap: number | null;
  market_cap_ratio: number | null;
  subject_turnover_ratio_24h: number | null;
  target_turnover_ratio_24h: number | null;
  turnover_gap: number | null;
  summary: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoFlowSummary {
  token_id: string;
  pool_count: number;
  matched_networks: string[];
  total_reserve_usd: number | null;
  total_volume_24h: number | null;
  dex_volume_share_of_total_volume: number | null;
  reserve_to_market_cap_ratio: number | null;
  top_pool_reserve_share: number | null;
  top_pool_volume_share: number | null;
  buy_pressure_pct: number | null;
  active_trader_proxy_24h: number;
  buy_sell_ratio: number | null;
  participant_balance_ratio: number | null;
  reserve_volume_ratio_24h: number | null;
  slippage_proxy_label: string | null;
  liquidity_concentration_label: string;
  flow_signal_label: string;
  summary: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CryptoPortfolioConstituent {
  token_id: string;
  symbol: string;
  name: string;
  input_weight: number;
  normalized_weight: number;
  market_cap: number | null;
  turnover_ratio_24h: number | null;
  narrative_labels: string[];
  layer_bucket: string | null;
}

export interface CryptoPortfolioNarrativeExposure {
  label: string;
  normalized_weight: number;
  constituent_count: number;
}

export interface CryptoPortfolioPoint {
  timestamp: string;
  value: number;
}

export interface CryptoSyntheticPortfolio {
  lookback_days: number;
  benchmark_token_id: string;
  benchmark_label: string;
  constituents: CryptoPortfolioConstituent[];
  narrative_exposures: CryptoPortfolioNarrativeExposure[];
  portfolio_points: CryptoPortfolioPoint[];
  benchmark_points: CryptoPortfolioPoint[];
  cumulative_return_pct: number | null;
  benchmark_return_pct: number | null;
  relative_return_pct: number | null;
  annualized_volatility_pct: number | null;
  weighted_turnover_ratio_24h: number | null;
  weighted_market_cap: number | null;
  concentration_hhi: number | null;
  effective_positions: number | null;
  summary: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsSearchResult {
  ticker: string;
  name: string;
  cik: string;
  exchange: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsSearchResponse {
  results: FundamentalsSearchResult[];
}

export interface FundamentalsMetric {
  metric_id: string;
  label: string;
  value: number | null;
  display_value: string | null;
  unit: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPricePoint {
  timestamp: string;
  price: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsFiling {
  form: string;
  filing_date: string;
  report_period: string | null;
  acceptance_datetime: string | null;
  accession_number: string | null;
  primary_document: string | null;
  is_amendment: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsCompany {
  ticker: string;
  cik: string;
  name: string;
  exchange: string | null;
  sic: string | null;
  sic_description: string | null;
  filer_category: string | null;
  fiscal_year_end: string | null;
  state_of_incorporation: string | null;
  phone: string | null;
  website: string | null;
  investor_website: string | null;
  description: string | null;
  latest_report_period: string | null;
  latest_filing_date: string | null;
  classification_labels: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsCompanySummary {
  ticker: string;
  summary: string | null;
  source_form: string | null;
  accession_number: string | null;
  filing_date: string | null;
  report_period: string | null;
  primary_document: string | null;
  section: string | null;
  source_url: string | null;
  model_provider: string | null;
  model: string | null;
  generated_at: string | null;
  confidence: number | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeriod {
  period_key: string;
  label: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
  start_date: string | null;
  end_date: string | null;
  filing_date: string | null;
  form: string | null;
  accession_number: string | null;
  is_amendment: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsStatementCell {
  period_key: string;
  value: number | null;
  display_value: string | null;
  start_date: string | null;
  end_date: string | null;
  filing_date: string | null;
  form: string | null;
  accession_number: string | null;
  is_amendment: boolean;
  concept_name: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsStatementLine {
  line_key: string;
  label: string;
  statement: string;
  unit: string;
  cells: FundamentalsStatementCell[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsStatementView {
  statement: string;
  basis: string;
  periods: FundamentalsPeriod[];
  lines: FundamentalsStatementLine[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerCandidate {
  ticker: string;
  name: string;
  reason: string | null;
  exchange: string | null;
  classification_label: string | null;
  market_cap: number | null;
  revenue: number | null;
  selected: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerBasket {
  focal_ticker: string;
  basket_label: string;
  peer_tickers: string[];
  display_order: string[];
  user_edited: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerHeatmapCell {
  ticker: string;
  value: number | null;
  display_value: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerHeatmapMetricRow {
  metric_id: string;
  label: string;
  family: string;
  cells: FundamentalsPeerHeatmapCell[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerHeatmapView {
  tickers: string[];
  rows: FundamentalsPeerHeatmapMetricRow[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerComparison {
  ticker: string;
  name: string;
  selected: boolean;
  candidate_reason: string | null;
  metrics: FundamentalsMetric[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeerDiagnostics {
  ticker: string;
  missing_metric_ids: string[];
  warning: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsPeers {
  company: FundamentalsCompany;
  peer_basket: FundamentalsPeerBasket;
  peer_candidates: FundamentalsPeerCandidate[];
  peer_heatmap: FundamentalsPeerHeatmapView | null;
  comparisons: FundamentalsPeerComparison[];
  diagnostics: FundamentalsPeerDiagnostics[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfRow {
  line_key: string;
  label: string;
  unit: string;
  values: Array<number | null>;
  display_values: Array<string | null>;
  editable: boolean;
  overridden: boolean[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfValuationSummary {
  scenario_id: string;
  label: string;
  enterprise_value: number | null;
  equity_value: number | null;
  implied_value_per_share: number | null;
  implied_value_low: number | null;
  implied_value_high: number | null;
  upside_downside_pct: number | null;
  terminal_value: number | null;
  discounted_terminal_value: number | null;
  discounted_cash_flow_value: number | null;
  current_price: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfBridgeRow {
  row_id: string;
  label: string;
  value: number | null;
  display_value: string | null;
  unit: string | null;
  note: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfSensitivityCell {
  wacc_pct: number;
  terminal_growth_pct: number;
  implied_value_per_share: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfSensitivityMatrix {
  wacc_values: number[];
  terminal_growth_values: number[];
  rows: FundamentalsDcfSensitivityCell[][];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfScenario {
  scenario_id: string;
  label: string;
  assumptions: Record<string, unknown>;
  overrides: Record<string, Array<number | null>>;
  assumption_rows: FundamentalsDcfRow[];
  projection_rows: FundamentalsDcfRow[];
  cost_of_capital_rows: FundamentalsDcfBridgeRow[];
  valuation_bridge_rows: FundamentalsDcfBridgeRow[];
  summary: FundamentalsDcfValuationSummary | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfModel {
  ticker: string;
  company_name: string;
  active_scenario_id: string;
  historical_year_labels: string[];
  projection_years: number[];
  actual_rows: FundamentalsDcfRow[];
  scenarios: FundamentalsDcfScenario[];
  sensitivity_matrix: FundamentalsDcfSensitivityMatrix | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfSnapshot {
  snapshot_id: string;
  ticker: string;
  name: string;
  created_at: string;
  active_scenario_id: string;
  projection_years: number[];
  scenario_summaries: FundamentalsDcfValuationSummary[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsDcfSnapshotList {
  snapshots: FundamentalsDcfSnapshot[];
}

export interface FundamentalsSourceTrace {
  statement: string;
  basis: string;
  line_key: string;
  line_label: string;
  period_key: string;
  period_label: string | null;
  normalized_value: number | null;
  display_value: string | null;
  unit: string | null;
  concept_name: string | null;
  accession_number: string | null;
  filing_form: string | null;
  fiscal_year: number | null;
  fiscal_period: string | null;
  filing_date: string | null;
  report_period: string | null;
  is_amendment: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsCoverage {
  statement: string;
  basis: string;
  line_key: string;
  line_label: string;
  concept_names: string[];
  observed_periods: number;
  missing_periods: number;
  derived_observations: number;
  coverage_ratio: number | null;
  warning: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsRawNormalizedInspection {
  company: FundamentalsCompany;
  traces: FundamentalsSourceTrace[];
  coverage: FundamentalsCoverage[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsReference {
  company: FundamentalsCompany;
  filings: FundamentalsFiling[];
  inspection: FundamentalsRawNormalizedInspection | null;
  provider_warnings: string[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsReverseValuationDriver {
  driver_id: string;
  label: string;
  implied_value: number | null;
  display_value: string | null;
  base_value: number | null;
  base_display_value: string | null;
  gap_to_base: number | null;
  gap_display_value: string | null;
  target_enterprise_value: number | null;
  solved_enterprise_value: number | null;
  success: boolean;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsReverseValuationSensitivityCell {
  wacc_pct: number;
  terminal_growth_pct: number;
  implied_revenue_growth_pct: number | null;
  implied_ebit_margin_pct: number | null;
  implied_fcf_cagr_pct: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsReverseValuationSensitivityMatrix {
  wacc_values: number[];
  terminal_growth_values: number[];
  rows: FundamentalsReverseValuationSensitivityCell[][];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsReverseValuation {
  company: FundamentalsCompany;
  current_price: number | null;
  shares_outstanding: number | null;
  net_debt: number | null;
  target_equity_value: number | null;
  target_enterprise_value: number | null;
  base_case_summary: FundamentalsDcfValuationSummary | null;
  scenario_gap_metrics: FundamentalsMetric[];
  drivers: FundamentalsReverseValuationDriver[];
  sensitivity_matrix: FundamentalsReverseValuationSensitivityMatrix | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface FundamentalsOverview {
  company: FundamentalsCompany;
  company_summary: FundamentalsCompanySummary | null;
  headline_metrics: FundamentalsMetric[];
  price_history: FundamentalsPricePoint[];
  filings: FundamentalsFiling[];
  peer_candidates: FundamentalsPeerCandidate[];
  peer_basket: FundamentalsPeerBasket | null;
  peer_heatmap: FundamentalsPeerHeatmapView | null;
  dcf_summary: FundamentalsDcfValuationSummary[];
  warnings: string[];
}

export interface FundamentalsFinancials {
  company: FundamentalsCompany;
  annual_income_statement: FundamentalsStatementView;
  annual_balance_sheet: FundamentalsStatementView;
  annual_cash_flow_statement: FundamentalsStatementView;
  quarterly_income_statement: FundamentalsStatementView;
  quarterly_balance_sheet: FundamentalsStatementView;
  quarterly_cash_flow_statement: FundamentalsStatementView;
  annual_ratio_view: FundamentalsStatementView;
  quarterly_ratio_view: FundamentalsStatementView;
  filings: FundamentalsFiling[];
  warnings: string[];
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
  comparison_region: string | null;
  comparison_label: string | null;
  comparison_value: number | null;
  comparison_display_value: string | null;
  comparison_delta_value: number | null;
  comparison_delta_display: string | null;
  gap_value: number | null;
  gap_display: string | null;
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

export interface MacroLinkedPredictionMarket {
  market_id: string;
  venue: string;
  title: string;
  status: string;
  category: string | null;
  end_time: string | null;
  current_probability: number | null;
  probability_label: string | null;
  recent_price_change: number | null;
  change_display: string | null;
  research_score: number | null;
  macro_stance?: string | null;
  macro_alignment: string;
  macro_alignment_summary: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroEventReactionSignal {
  role: string;
  tone: string;
  signal_score: number;
  signal_score_display: string;
  move_value: number | null;
  move_display: string | null;
  before_display_value: string | null;
  after_display_value: string | null;
  observed_at?: string | null;
  observed_label?: string | null;
  lag_days?: number | null;
  lag_label?: string | null;
  interpretation: string;
  metric: MacroMetric;
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
  why_now?: string | null;
  mode_target: string;
  target_theme: string | null;
  signal_label?: string | null;
  drilldown_label?: string | null;
  metrics: MacroMetric[];
  linked_markets: MacroLinkedPredictionMarket[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroDivergenceSignal {
  role: string;
  tone: string;
  signal_score: number;
  signal_score_display: string;
  interpretation: string;
  metric: MacroMetric;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroLeadLagSignal {
  label: string;
  series_id?: string | null;
  role: string;
  tone: string;
  signal_score: number;
  signal_score_display?: string | null;
  move_value?: number | null;
  move_display?: string | null;
  observed_at?: string | null;
  observed_label?: string | null;
  lag_days?: number | null;
  lag_label?: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroCoherenceProfile {
  theme: string;
  direction_label: string;
  coherence_label: string;
  supporting_signals: number;
  opposing_signals: number;
  neutral_signals: number;
  lead_signal?: MacroLeadLagSignal | null;
  lag_signal?: MacroLeadLagSignal | null;
  lag_span_days?: number | null;
  lag_span_display?: string | null;
  summary: string;
  methodology?: string | null;
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
  primary_driver: MacroDivergenceSignal | null;
  counter_signal: MacroDivergenceSignal | null;
  coherence?: MacroCoherenceProfile | null;
  research_focus: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
  comparison_region: string | null;
  comparison_score: number | null;
  score_gap: number | null;
  score_gap_display: string | null;
}

export interface MacroThemeComparison {
  theme: string;
  headline: string;
  summary: string;
  agreement_label: string;
  metrics: MacroMetric[];
  linked_markets: MacroLinkedPredictionMarket[];
  primary_driver: MacroDivergenceSignal | null;
  counter_signal: MacroDivergenceSignal | null;
  coherence?: MacroCoherenceProfile | null;
  divergence_score: number | null;
  research_focus: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
  comparison_region: string | null;
  comparison_summary: string | null;
}

export interface MacroPolicyMeetingPathRow {
  meeting_id: string;
  title: string;
  scheduled_at: string;
  meeting_index: number;
  implied_policy_rate: number | null;
  implied_policy_rate_display: string | null;
  incremental_change_bps: number | null;
  incremental_change_display: string | null;
  cumulative_change_bps: number | null;
  cumulative_change_display: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroPolicyMeetingPathSummary {
  headline: string;
  summary: string;
  window_label: string;
  metrics: MacroMetric[];
  meetings: MacroPolicyMeetingPathRow[];
  research_focus: string | null;
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
  linked_markets: MacroLinkedPredictionMarket[];
  path_headline: string | null;
  path_summary: string | null;
  path_metrics: MacroMetric[];
  path_research_focus: string | null;
  expectation_metrics?: MacroMetric[];
  expectation_summary?: string | null;
  expectation_caveat?: string | null;
  meeting_path: MacroPolicyMeetingPathSummary | null;
  market_alignment_label: string | null;
  market_alignment_summary: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
  comparison_region: string | null;
  comparison_summary: string | null;
}

export interface MacroTradePartnerRow {
  partner_code: string;
  partner_name: string;
  rank: number;
  export_value: number | null;
  import_value: number | null;
  total_trade_value: number | null;
  trade_balance: number | null;
  share_of_total: number | null;
  export_value_display: string | null;
  import_value_display: string | null;
  total_trade_value_display: string | null;
  trade_balance_display: string | null;
  share_of_total_display: string | null;
  interpretation: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroTradePartnerSummary {
  region: string;
  headline: string;
  summary: string;
  partners: MacroTradePartnerRow[];
  caveats: string[];
  research_focus: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroCountryCompareRow {
  metric_id: string;
  label: string;
  base_region: string;
  comparison_region: string;
  base_value: number | null;
  comparison_value: number | null;
  gap_value: number | null;
  unit: string | null;
  base_value_display: string | null;
  comparison_value_display: string | null;
  gap_display: string | null;
  interpretation: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroCountryCompareSummary {
  base_region: string;
  comparison_region: string;
  headline: string;
  summary: string;
  rows: MacroCountryCompareRow[];
  caveats: string[];
  research_focus: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroEventStudy {
  study_id: string;
  theme: string;
  timing: string;
  headline: string;
  summary: string;
  window_label: string;
  window_start?: string | null;
  window_end?: string | null;
  window_start_label?: string | null;
  window_end_label?: string | null;
  event: MacroEvent;
  reactions: MacroEventReactionSignal[];
  primary_reaction: MacroEventReactionSignal | null;
  counter_reaction: MacroEventReactionSignal | null;
  coherence?: MacroCoherenceProfile | null;
  linked_markets: MacroLinkedPredictionMarket[];
  research_focus: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MacroSnapshotFocusItem {
  focus_id: string;
  title: string;
  summary: string;
  why_now: string;
  mode_target: string;
  target_theme?: string | null;
  signal_label?: string | null;
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
  focus_items?: MacroSnapshotFocusItem[];
  snapshot_cards: MacroSnapshotCard[];
  rates_policy: MacroRatesPolicySummary | null;
  cross_asset: MacroThemeComparison[];
  trade_partners?: MacroTradePartnerSummary | null;
  country_compare?: MacroCountryCompareSummary | null;
  top_divergences: MacroDivergence[];
  event_studies: MacroEventStudy[];
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
  comparison_region: string | null;
  divergences: MacroDivergence[];
}

export interface MacroEventsResponse {
  region: string;
  events: MacroEvent[];
}

export interface CommodityCoverageMetadata {
  coverage_status: "sample" | "mock" | "official_partial" | "partial" | "live" | "unavailable" | string;
  provider_id: string;
  provider_label: string;
  freshness_label: string;
  instruments: string[];
  regions: string[];
  as_of: string | null;
  source_timestamp: string | null;
  caveats: string[];
  credential_env_vars: string[];
  supports_prices: boolean;
  supports_curves: boolean;
  supports_inventories: boolean;
  supports_events: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityInstrument {
  instrument_id: string;
  symbol: string;
  name: string;
  family: string;
  subgroup: string;
  quote_unit: string;
  currency: string;
  exchange: string | null;
  front_symbol: string | null;
  provider_symbols: Record<string, string>;
  aliases: string[];
  description: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityPricePoint {
  instrument_id: string;
  timestamp: string;
  value: number;
  unit: string;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityPriceHistory {
  instrument_id: string;
  label: string;
  unit: string;
  points: CommodityPricePoint[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityFuturesContract {
  contract_id: string;
  instrument_id: string;
  symbol: string;
  contract_month: string;
  expiry_date: string | null;
  is_front_month: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityCurveNode {
  contract: CommodityFuturesContract;
  price: number | null;
  previous_price: number | null;
  change: number | null;
  days_to_expiry: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityCurveSnapshot {
  instrument_id: string;
  as_of: string;
  nodes: CommodityCurveNode[];
  shape_label: string;
  front_spread: number | null;
  front_spread_pct: number | null;
  m1_m6_spread: number | null;
  curve_slope: number | null;
  roll_yield_proxy_pct: number | null;
  summary: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommoditySpreadDefinition {
  spread_id: string;
  label: string;
  spread_type: string;
  left_leg_id: string;
  right_leg_id: string;
  unit: string;
  formula: string;
  rationale: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommoditySpreadPoint {
  spread_id: string;
  timestamp: string;
  value: number;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommoditySpreadSnapshot {
  definition: CommoditySpreadDefinition;
  value: number | null;
  previous_value: number | null;
  change: number | null;
  z_score: number | null;
  percentile: number | null;
  interpretation: string | null;
  history: CommoditySpreadPoint[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityInventorySeriesMetadata {
  series_id: string;
  instrument_id: string | null;
  label: string;
  category: string;
  unit: string;
  frequency: string;
  provider_series_id: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityInventoryPoint {
  series_id: string;
  timestamp: string;
  value: number;
  change: number | null;
  seasonal_percentile: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityInventorySeries {
  metadata: CommodityInventorySeriesMetadata;
  points: CommodityInventoryPoint[];
  latest_value: number | null;
  latest_change: number | null;
  seasonal_percentile: number | null;
  interpretation: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityMarketSummary {
  instrument: CommodityInstrument;
  latest_price: number | null;
  latest_change: number | null;
  latest_change_pct: number | null;
  curve_state: string;
  front_spread: number | null;
  inventory_signal: string | null;
  summary: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewMarketBreadth {
  total_markets: number;
  counts_by_family: Record<string, number>;
  backwardation_count: number;
  contango_count: number;
  flat_count: number;
  unavailable_curve_count: number;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewMatrixRow {
  instrument_id: string;
  family: string;
  symbol: string;
  name: string;
  quote_unit: string;
  latest_price: number | null;
  latest_change: number | null;
  latest_change_pct: number | null;
  curve_state: string;
  front_spread: number | null;
  front_basis: number | null;
  roll_yield_proxy_pct: number | null;
  inventory_signal: string | null;
  inventory_seasonal_percentile: number | null;
  price_source_provider: string | null;
  curve_source_provider: string | null;
  inventory_source_provider: string | null;
  provenance_summary: string[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewScatterPoint {
  instrument_id: string;
  symbol: string;
  name: string;
  family: string;
  x_value: number;
  y_value: number;
  display_label: string;
  x_source_provider: string | null;
  y_source_provider: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewScatter {
  points: CommodityOverviewScatterPoint[];
  x_methodology_label: string;
  y_methodology_label: string;
  caveats: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewRankingItem {
  item_id: string;
  label: string;
  value: number | null;
  instrument_id: string | null;
  family: string | null;
  display_value: string | null;
  unit: string | null;
  direction: string | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewRankings {
  strongest_backwardation: CommodityOverviewRankingItem[];
  deepest_contango: CommodityOverviewRankingItem[];
  inventory_outliers: CommodityOverviewRankingItem[];
  spread_z_score_outliers: CommodityOverviewRankingItem[];
  largest_movers: CommodityOverviewRankingItem[];
  caveats: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewTermStructure {
  selected_instrument_id: string;
  current_curve: CommodityCurveSnapshot | null;
  previous_curve_snapshots: CommodityCurveSnapshot[];
  current_curve_methodology: string | null;
  previous_curve_methodology: string | null;
  caveats: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityOverviewAnalytics {
  market_breadth: CommodityOverviewMarketBreadth;
  matrix_rows: CommodityOverviewMatrixRow[];
  scatter: CommodityOverviewScatter | null;
  rankings: CommodityOverviewRankings | null;
  term_structure: CommodityOverviewTermStructure | null;
  caveats: string[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityEventRecord {
  event_id: string;
  title: string;
  category: string;
  scheduled_at: string | null;
  relative_label: string | null;
  importance: string;
  linked_instrument_ids: string[];
  summary: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityCrossDomainLink {
  link_id: string;
  target_domain: string;
  target_label: string;
  relationship: string;
  linked_instrument_ids: string[];
  summary: string | null;
  confidence: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface CommodityWorkspaceResponse {
  mode: CommodityMode | string;
  selected_instrument_id: string;
  available_modes: string[];
  coverage: CommodityCoverageMetadata;
  instruments: CommodityInstrument[];
  market_summaries: CommodityMarketSummary[];
  price_histories: CommodityPriceHistory[];
  curves: CommodityCurveSnapshot[];
  spreads: CommoditySpreadSnapshot[];
  inventories: CommodityInventorySeries[];
  events: CommodityEventRecord[];
  cross_domain_links: CommodityCrossDomainLink[];
  overview?: CommodityOverviewAnalytics | null;
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export type MaritimeMode = "live_map" | "chokepoints" | "trade_flows" | "fleet_monitoring" | "event_replay";

export interface MaritimeCoverageMetadata {
  coverage_status: "sample" | "mock" | "historical" | "partial" | "live" | "unavailable" | string;
  provider_id: string;
  provider_label: string;
  freshness_label: string;
  regions: string[];
  as_of: string | null;
  source_timestamp: string | null;
  caveats: string[];
  credential_env_vars: string[];
  supports_live: boolean;
  supports_historical: boolean;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeVesselIdentity {
  vessel_id: string;
  mmsi: string;
  imo: string | null;
  callsign: string | null;
  normalized_id: string | null;
}

export interface MaritimeVesselStatic {
  vessel_id: string;
  name: string;
  identity: MaritimeVesselIdentity;
  vessel_type: string;
  vessel_class: string;
  flag: string | null;
  owner_operator: string | null;
  length_m: number | null;
  beam_m: number | null;
  deadweight_tons: number | null;
  cargo_inference: string | null;
  cargo_inference_confidence: number | null;
  cargo_inference_caveat: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeAisPosition {
  position_id: string;
  vessel_id: string;
  mmsi: string;
  timestamp: string;
  latitude: number;
  longitude: number;
  speed_knots: number | null;
  course_degrees: number | null;
  heading_degrees: number | null;
  navigation_status: string | null;
  destination: string | null;
  draught_m: number | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeTrackSnippet {
  track_id: string;
  vessel_id: string;
  label: string;
  start_port_id: string | null;
  end_port_id: string | null;
  chokepoint_ids: string[];
  points: MaritimeAisPosition[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimePort {
  port_id: string;
  name: string;
  country: string;
  region: string;
  latitude: number;
  longitude: number;
  unlocode: string | null;
  terminal_type: string | null;
  commodity_links: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeBoundingBox {
  min_latitude: number;
  max_latitude: number;
  min_longitude: number;
  max_longitude: number;
}

export interface MaritimeChokepointDefinition {
  chokepoint_id: string;
  name: string;
  region: string;
  latitude: number;
  longitude: number;
  bounding_box: MaritimeBoundingBox;
  strategic_commodities: string[];
  description: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeChokepointSummary {
  chokepoint_id: string;
  name: string;
  region: string;
  coverage_status: string;
  total_vessel_count: number;
  vessel_count_by_type: Record<string, number>;
  baseline_vessel_count: number | null;
  congestion_score: number | null;
  congestion_label: string;
  commodity_links: string[];
  methodology: string | null;
  caveats: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeFlowSummary {
  flow_id: string;
  label: string;
  vessel_type: string;
  route_label: string;
  coverage_status: string;
  vessel_count: number;
  affected_chokepoint_ids: string[];
  inferred_commodity: string | null;
  inference_confidence: number | null;
  inference_caveat: string | null;
  summary: string | null;
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeEventWindow {
  event_id: string;
  title: string;
  event_type: string;
  region: string;
  start_at: string;
  end_at: string;
  summary: string;
  linked_chokepoint_ids: string[];
  linked_commodity_flows: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeFleetWatchlist {
  watchlist_id: string;
  label: string;
  description: string;
  vessel_ids: string[];
  vessel_type_filters: string[];
  caveats: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeWorkspaceResponse {
  mode: MaritimeMode | string;
  available_modes: string[];
  coverage: MaritimeCoverageMetadata;
  vessels: MaritimeVesselStatic[];
  positions: MaritimeAisPosition[];
  tracks: MaritimeTrackSnippet[];
  ports: MaritimePort[];
  chokepoints: MaritimeChokepointDefinition[];
  chokepoint_summaries: MaritimeChokepointSummary[];
  flow_summaries: MaritimeFlowSummary[];
  event_windows: MaritimeEventWindow[];
  watchlists: MaritimeFleetWatchlist[];
  warnings: string[];
  source_provider: string;
  retrieved_at: string | null;
  origin: string;
  transformation_note: string | null;
}

export interface MaritimeTrackResponse {
  vessel_id: string;
  track: MaritimeTrackSnippet | null;
}

export type CopilotBaseDomain =
  | "portfolio"
  | "research"
  | "equity_research"
  | "strategy_lab"
  | "macro"
  | "commodities"
  | "prediction_markets"
  | "crypto"
  | "fundamentals"
  | "risk"
  | "iv";
export type CopilotDomain = CopilotBaseDomain | "synthesis";

export interface CopilotSourceRef {
  source_id: string;
  label: string;
  kind: string;
  provider: string;
  origin: string;
  description: string | null;
  retrieved_at: string | null;
}

export interface CopilotToolTrace {
  tool_name: string;
  summary: string;
  arguments: Record<string, unknown>;
  source_ids: string[];
}

export interface ResearchClaim {
  claim: string;
  evidence_refs: string[];
}

export interface ResearchCard {
  title: string;
  hypothesis: string;
  rationale: string;
  required_data: string[];
  proposed_test: string;
  confounders: string[];
  next_steps: string[];
  caveats: string[];
  source_backed_claims: ResearchClaim[];
  inferred_claims: string[];
}

export interface CopilotResearchCardResult {
  domain: CopilotDomain;
  current_tab: string;
  status: string;
  provider: string;
  model: string | null;
  response_id: string | null;
  message: string | null;
  card: ResearchCard | null;
  sources: CopilotSourceRef[];
  tool_traces: CopilotToolTrace[];
  warnings: string[];
}

export interface CopilotThreadEntry {
  entryId: string;
  turnIndex: number;
  prompt: string;
  continuedFromResponseId: string | null;
  result: CopilotResearchCardResult;
}

export interface CopilotThreadState {
  domain: CopilotDomain;
  contextFingerprint: string | null;
  latestResponseId: string | null;
  entries: CopilotThreadEntry[];
}

export interface CopilotSessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  active_domain: string | null;
  active_context_fingerprint: string | null;
  turn_count: number;
  memo_count: number;
  warnings: string[];
  archived_at: string | null;
}

export interface CopilotTurnRecord {
  turn_id: string;
  session_id: string;
  turn_index: number;
  domain: string;
  prompt: string;
  context_snapshot_id: string;
  result: CopilotResearchCardResult;
  created_at: string;
}

export interface CopilotMemo {
  memo_id: string;
  session_id: string;
  title: string;
  body: string;
  source_turn_ids: string[];
  source_snapshot_ids: string[];
  created_at: string;
  updated_at: string;
  warnings: string[];
  source_provider: string;
  origin: string;
  transformation_note: string | null;
}

export interface CopilotSessionDetail {
  session: CopilotSessionSummary;
  turns: CopilotTurnRecord[];
  memos: CopilotMemo[];
}

export interface CrossTabHandoffEntity {
  entity_type: string;
  label: string;
  normalized_id: string;
  provider_id: string | null;
  native_id: string | null;
  metadata: Record<string, unknown>;
}

export interface CrossTabHandoffTimeframe {
  label: string;
  start: string | null;
  end: string | null;
}

export interface CrossTabHandoffEnvelope {
  source_tab: TabId | string;
  source_mode: string | null;
  selected_entity: CrossTabHandoffEntity | null;
  selected_timeframe: CrossTabHandoffTimeframe | null;
  provider: string | null;
  source: Record<string, unknown> | null;
  warnings: string[];
  normalized_ids: Record<string, string>;
  timestamp: string;
  intended_target_tab: TabId | string;
  intended_target_mode: string | null;
}

export interface IvSurfaceCollection {
  depth_preset: string;
  market_data_mode: string;
  include_calls: boolean;
  include_puts: boolean;
  max_expiries: number;
  strike_band_pct: number;
  configured_max_contracts: number;
  configured_market_data_line_budget: number;
  reserved_market_data_lines: number;
  underlying_market_data_lines: number;
  option_market_data_line_budget: number;
  selected_expiry_count: number;
  selected_strike_count: number;
  requested_contract_count: number;
  subscribed_contract_count: number;
  estimated_total_market_data_lines: number;
  market_data_line_utilization: number | null;
  contract_selection_note: string | null;
}

export interface IvSurfaceQuality {
  expected_surface_cells: number;
  observed_surface_cells: number;
  interpolated_surface_cells: number;
  interpolation_ratio: number | null;
  contracts_with_bid_ask: number;
  contracts_with_volume: number;
  contracts_with_open_interest: number;
  contracts_with_provider_greeks: number;
  contracts_with_derived_greeks: number;
  call_contract_count: number;
  put_contract_count: number;
  pairs_with_both_sides: number;
}

export interface IvOptionPair {
  pair_id: string;
  expiry: string;
  strike: number;
  days_to_expiry: number | null;
  call_contract_id: string | null;
  put_contract_id: string | null;
  call_midpoint: number | null;
  put_midpoint: number | null;
  call_mark_price: number | null;
  put_mark_price: number | null;
  call_implied_volatility: number | null;
  put_implied_volatility: number | null;
  blended_implied_volatility: number | null;
  call_delta: number | null;
  put_delta: number | null;
  call_open_interest: number | null;
  put_open_interest: number | null;
  call_volume: number | null;
  put_volume: number | null;
  straddle_midpoint: number | null;
  synthetic_forward_price: number | null;
  implied_move_pct: number | null;
  call_put_parity_gap: number | null;
}

export interface IvSurface {
  symbol: string;
  timestamp: string;
  retrieved_at: string;
  snapshot_available: boolean;
  spot: number | null;
  expiries: string[];
  strikes: number[];
  iv_grid: number[][];
  delayed: boolean | null;
  points: number;
  warnings: string[];
  messages: string[];
  source_provider: string;
  origin: string;
  transformation_note: string | null;
  freshness_label: string;
  collection: IvSurfaceCollection | null;
  quality: IvSurfaceQuality | null;
  pairs: IvOptionPair[];
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
