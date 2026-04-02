export type WorkspaceMode = "portfolio" | "research";

export type TabId = "portfolio" | "research" | "macro" | "prediction_markets" | "risk" | "iv";

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
  | "switch_research_workspace";

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

export type MacroMode = "snapshot" | "cross_asset" | "rates_policy" | "events_regimes";
export type MacroRegion = "US" | "EU" | "Global";
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

export type CopilotDomain = "macro" | "prediction_markets";

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
