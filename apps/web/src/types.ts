export type Timeframe = "1m" | "15m" | "1h";
export type BacktestExitMode = "mean_revert" | "opposite_extreme";

export type DirectionHint = "LONG_SPREAD" | "SHORT_SPREAD" | "NONE";

export interface CostGate {
  status: "AVAILABLE" | "WAIT" | "UNAVAILABLE";
  expected_edge_bps: number;
  fee_bps: number;
  funding_model: "STATIC" | "DYNAMIC";
  funding_events: number;
  funding_bps_per_event: number;
  funding_bps: number;
  slippage_bps: number;
  net_edge_bps: number;
  pass: boolean;
  rationale_codes: string[];
}

export interface SetupGate {
  status: "AVAILABLE" | "WAIT" | "UNAVAILABLE";
  pass: boolean;
  rationale_codes: string[];
}

export interface TradeGate {
  status: "AVAILABLE" | "WAIT" | "UNAVAILABLE";
  pass: boolean;
  blocked_by: "NONE" | "SETUP" | "COST" | "MULTIPLE" | "WAIT" | "UNAVAILABLE";
  rationale_codes: string[];
}

export interface PortfolioHint {
  status: "AVAILABLE" | "UNAVAILABLE";
  target_weight: number;
  risk_contribution: number;
  cap_applied: boolean;
  rationale_codes: string[];
}

export interface ShadowMl {
  status: "AVAILABLE" | "UNAVAILABLE";
  model_name: string;
  training_rows: number;
  positive_rate: number;
  precision: number;
  brier_score: number;
  recommended_variant: string;
  recommended_probability: number;
  agrees_with_selected: boolean;
  rationale_codes: string[];
}

export interface CueSelectionState {
  best_variant: string;
  best_opportunity_score: number;
  best_direction_hint: DirectionHint;
  best_confidence_band: "LOW" | "MEDIUM" | "HIGH";
  stored_champion_variant: string | null;
  stored_champion_score: number | null;
  stored_champion_direction_hint: DirectionHint | null;
  stored_champion_confidence_band: "LOW" | "MEDIUM" | "HIGH" | null;
  transition_decision: "INITIALIZE" | "UNCHANGED" | "KEEP_CHAMPION" | "PROMOTE_CHALLENGER";
  score_delta_to_champion: number | null;
  drift_active: boolean;
  source: "EVALUATED_BEST" | "STORED_CHAMPION_PROJECTION";
  validation_state:
    | "NO_STORED_CHAMPION"
    | "BEST_IS_CHAMPION"
    | "CHAMPION_PROJECTED"
    | "CHAMPION_PROJECTED_BLOCKED"
    | "CHAMPION_PROJECTION_FAILED";
}

export interface Cue {
  pair_id: string;
  left_instrument: string;
  right_instrument: string;
  timeframe: Timeframe;
  regime: "CALM" | "TRENDING" | "SHOCK";
  selected_variant: string;
  direction_hint: DirectionHint;
  spread_z: number;
  opportunity_score: number;
  confidence_band: "LOW" | "MEDIUM" | "HIGH";
  entry_band: number;
  exit_band: number;
  stop_band: number;
  expected_hold_bars: number;
  cost_estimate_bps: number;
  setup_actionable?: boolean;
  actionable: boolean;
  rationale_codes: string[];
  setup_gate?: SetupGate;
  cost_gate: CostGate;
  trade_gate?: TradeGate;
  portfolio_hint: PortfolioHint;
  shadow_ml: ShadowMl;
  selection_state?: CueSelectionState;
  evaluated_at: string;
}

export interface CueVariant {
  variant: string;
  score_last: number;
  sample_count: number;
  win_rate: number;
  edge_bps: number;
  reliability: number;
  regime_fit: number;
  opportunity_score: number;
  shadow_success_probability: number | null;
  shadow_rank_score: number | null;
  rationale_codes: string[];
}

export interface CueRow {
  cue: Cue;
  variants: CueVariant[];
  half_life_bars: number;
  hedge_ratio: number;
  hedge_ratio_stability: number;
}

export interface StrategyPairsCuesResponse {
  timeframe: Timeframe;
  generated_at: string;
  cues: CueRow[];
  candidate_set: {
    total_pairs: number;
    evaluated_pairs: number;
    actionable_pairs: number;
    cost_gate_pass_pairs: number;
    shadow_disagreement_pairs: number;
  };
  portfolio_plan: {
    status: "AVAILABLE" | "UNAVAILABLE";
    weights: Array<{
      pair_id: string;
      target_weight: number;
      risk_contribution: number;
      cap_applied: boolean;
    }>;
    constraints: {
      dollar_neutral: boolean;
      gross_cap: number;
      per_pair_cap: number;
    };
    rationale_codes: string[];
  };
  skipped: Array<{ pair_id: string; reason: string }>;
}

export type TradeNowDecisionBucket = "TRADE_NOW" | "WATCHLIST" | "EXCLUDED";
export type TradeNowApprovalSource =
  | "LEARNING_SELECTION"
  | "LEARNING_ELIGIBLE_OVERRIDE"
  | "OPERATOR_PROMOTED_ACTIVE_CHAMPION"
  | "NONE";

export interface StrategyPairsTradeNowRow {
  pair_id: string;
  left_instrument: string;
  right_instrument: string;
  timeframe: Timeframe;
  selected_variant: string;
  direction_hint: DirectionHint;
  spread_z: number;
  z_score?: number;
  opportunity_score: number;
  confidence_band: "LOW" | "MEDIUM" | "HIGH";
  expected_hold_bars: number;
  net_edge_bps: number;
  setup_gate_pass: boolean;
  cost_gate_pass: boolean;
  trade_gate_pass: boolean;
  open_live_trade: boolean;
  portfolio_target_weight: number | null;
  portfolio_risk_contribution: number | null;
  approval_source: TradeNowApprovalSource;
  requires_fresh_overlay: boolean;
  learning_recommendation: string | null;
  learning_trade_eligible: boolean | null;
  learning_selection_selected: boolean | null;
  learning_reason_codes: string[];
  learning_cycle_generated_at: string | null;
  selected_config_source: string;
  legacy_fallback_active: boolean;
  decision_bucket: TradeNowDecisionBucket;
  decision_reason_code: string;
  blocked_reason_code: string | null;
  watch_reason_code: string | null;
  rationale_codes: string[];
}

export interface StrategyPairsTradeNowResponse {
  generated_at: string;
  timeframe_filter: Timeframe | null;
  learning_overlay_generated_at: string | null;
  learning_overlay_age_seconds: number | null;
  learning_overlay_fresh: boolean;
  learning_overlay_ttl_seconds: number;
  tradable_now: StrategyPairsTradeNowRow[];
  watchlist: StrategyPairsTradeNowRow[];
  excluded: StrategyPairsTradeNowRow[];
}

export interface StrategyTradeNowObservabilityResponse {
  generated_at: string;
  learning_challenger_bypass_suppressed_total: number;
  learning_challenger_bypass_suppressed: Array<{
    pair_id: string;
    timeframe: Timeframe;
    suppressed_total: number;
  }>;
  learning_eligible_override_tradable_total: number;
  learning_eligible_override_tradable: Array<{
    pair_id: string;
    timeframe: Timeframe;
    surfaced_total: number;
  }>;
  learning_selection_cost_override_applied_total: number;
  learning_selection_cost_override_applied: Array<{
    pair_id: string;
    timeframe: Timeframe;
    applied_total: number;
  }>;
}

export interface StrategyPairsOpportunityHistoryResponse {
  timeframe: Timeframe;
  generated_at: string;
  hours: number;
  only_pass: boolean;
  rows: Array<{
    pair_id: string;
    left_instrument: string;
    right_instrument: string;
    timeframe: Timeframe;
    selected_variant: string;
    regime: string;
    direction_hint: DirectionHint;
    spread_z: number;
    opportunity_score: number;
    net_edge_bps: number;
    cost_gate_pass: boolean;
    actionable: boolean;
    rationale_codes: string[];
    cost_gate_rationale_codes: string[];
    evaluated_at: string;
  }>;
}

export interface StrategyPairsOpportunityHistoryStatsResponse {
  generated_at: string;
  timeframe_filter: Timeframe | null;
  total_rows: number;
  first_evaluated_at: string | null;
  last_evaluated_at: string | null;
  days_covered: number;
  by_timeframe: Array<{
    timeframe: Timeframe;
    rows: number;
    first_evaluated_at: string | null;
    last_evaluated_at: string | null;
    days_covered: number;
  }>;
}

export interface StrategyPairsPaperTradesResponse {
  timeframe: Timeframe;
  generated_at: string;
  hours: number;
  pair_id: string | null;
  exit_mode: BacktestExitMode;
  model_bars: number;
  rows: Array<{
    pair_id: string;
    timeframe: Timeframe;
    exit_mode: BacktestExitMode;
    left_instrument: string;
    right_instrument: string;
    selected_variant: string;
    entry_ts: string;
    exit_ts: string;
    bars_held: number;
    direction: "LONG_SPREAD" | "SHORT_SPREAD";
    exit_kind: "exit" | "stop";
    entry_z: number;
    exit_z: number;
    entry_index: number;
    exit_index: number;
    left_entry: number;
    left_exit: number;
    right_entry: number;
    right_exit: number;
    left_leg_bps: number;
    right_leg_bps: number;
    gross_bps: number;
    round_trip_cost_bps: number;
    net_bps: number;
    equity_pre_entry: number;
    equity_exit: number;
    equity_trade_bps: number;
    created_at: string;
    updated_at: string;
  }>;
}

export type StrategyZMethod =
  | "COINTEGRATION_Z"
  | "ROBUST_Z"
  | "VOL_NORMALIZED"
  | "FUNDING_ADJUSTED";

export interface StrategyExpectancyConfig {
  entry_z: number;
  exit_z: number;
  stop_z: number;
  z_method: StrategyZMethod;
  hedge_method: string;
  lookback_bars: number;
  train_bars: number;
  validation_bars: number;
}

export interface StrategyPairsExpectancyMetrics {
  trades: number;
  win_rate: number;
  avg_net_bps: number;
  p25_net_bps: number;
  p50_net_bps: number;
  p75_net_bps: number;
  avg_hold_bars: number;
  avg_mae_bps: number;
  avg_mfe_bps: number;
  expected_min_lot_net_bps: number;
  expected_min_lot_net_usd: number;
}

export interface StrategyPairsExpectancyResponse {
  timeframe: Timeframe;
  pair_id: string;
  generated_at: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  decision_state: "TRADE_READY" | "CAUTION" | "BLOCKED";
  primary_reason_code: string;
  config: StrategyExpectancyConfig;
  metrics: StrategyPairsExpectancyMetrics | null;
  rationale_codes: string[];
}

export interface StrategyPairsReplayTradePath {
  mae_bps: number;
  mfe_bps: number;
  bars_underwater: number;
  bars_held: number;
}

export interface StrategyPairsReplayTradeEntry {
  trade_id: string;
  entry_ts: string;
  exit_ts: string;
  direction: "LONG_SPREAD" | "SHORT_SPREAD";
  entry_z: number;
  exit_z: number;
  net_bps: number;
  path: StrategyPairsReplayTradePath;
}

export interface StrategyPairsReplayTradesResponse {
  timeframe: Timeframe;
  pair_id: string;
  generated_at: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  model_bars: number;
  hours: number;
  limit: number;
  exit_mode: BacktestExitMode;
  config: StrategyExpectancyConfig;
  rationale_codes: string[];
  rows: StrategyPairsReplayTradeEntry[];
}

export interface StrategyPairsResearchSweepRequest {
  timeframes?: Timeframe[];
  pair_ids?: string[];
  entry_z_grid?: number[];
  exit_z_grid?: number[];
  stop_z_grid?: number[];
  z_methods?: StrategyZMethod[];
  lookback_bars_grid?: number[];
  train_bars?: number;
  validation_bars?: number;
  max_combinations?: number;
  dry_run?: boolean;
}

export interface StrategyPairsResearchSweepResponse {
  generated_at: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  request_id: string;
  dry_run: boolean;
  timeframes: Timeframe[];
  pair_ids: string[];
  estimated_combinations: number;
  executed_combinations: number;
  successful_combinations: number;
  failed_combinations: number;
  top_k: number;
  best_candidate: StrategyPairsResearchSweepCandidate | null;
  top_candidates: StrategyPairsResearchSweepCandidate[];
  max_combinations: number;
  rationale_codes: string[];
}

export interface StrategyPairsResearchSweepCandidate {
  rank: number;
  timeframe: Timeframe;
  pair_id: string;
  config: StrategyExpectancyConfig;
  status: "AVAILABLE" | "UNAVAILABLE";
  decision_state: "TRADE_READY" | "CAUTION" | "BLOCKED";
  primary_reason_code: string;
  objective_score: number;
  metrics: StrategyPairsExpectancyMetrics | null;
  walk_forward: {
    folds_requested: number;
    folds_evaluated: number;
    folds_completed: number;
    min_trades_per_fold: number;
    pass: boolean;
    avg_objective_score: number;
    fold_trade_counts: number[];
    rationale_codes: string[];
  };
  rationale_codes: string[];
}

export interface StrategyPairsCandidateInboxEntry {
  pair_id: string;
  timeframe: Timeframe;
  candidate_id: string;
  candidate_state: "CHALLENGER" | "PROMOTION_READY" | "CHAMPION" | "HOLD" | "REJECTED";
  request_id: string;
  rank: number;
  candidate_variant: StrategyZMethod;
  status: "AVAILABLE" | "UNAVAILABLE";
  decision_state: "TRADE_READY" | "CAUTION" | "BLOCKED";
  primary_reason_code: string;
  objective_score: number;
  objective_delta: number;
  config: StrategyExpectancyConfig;
  metrics: StrategyPairsExpectancyMetrics | null;
  walk_forward: {
    folds_requested: number;
    folds_evaluated: number;
    folds_completed: number;
    min_trades_per_fold: number;
    pass: boolean;
    avg_objective_score: number;
    fold_trade_counts: number[];
    rationale_codes: string[];
  };
  rationale_codes: string[];
  champion_variant: string;
  champion_score: number;
  started_at: string;
  updated_at: string;
  eligible_after: string;
  probation_samples: number;
  promotable: boolean;
  last_reason: string;
  last_candidate_score: number;
  last_champion_score: number;
  last_objective_delta: number;
}

export interface StrategyPairsCandidateInboxResponse {
  generated_at: string;
  timeframe_filter: Timeframe | null;
  limit: number;
  rows: StrategyPairsCandidateInboxEntry[];
}

export interface StrategyPairsCandidateActionRequest {
  pair_id: string;
  timeframe: Timeframe;
  candidate_id?: string | null;
  action: "PROMOTE" | "HOLD" | "REJECT";
  operator_id: string;
  note?: string | null;
  confirm: boolean;
}

export interface StrategyPairsCandidateActionResponse {
  generated_at: string;
  accepted: boolean;
  pair_id: string;
  timeframe: Timeframe;
  candidate_id: string;
  action: "PROMOTE" | "HOLD" | "REJECT";
  state_before: "CHALLENGER" | "PROMOTION_READY" | "CHAMPION" | "HOLD" | "REJECTED";
  state_after: "CHALLENGER" | "PROMOTION_READY" | "CHAMPION" | "HOLD" | "REJECTED";
  promotable: boolean;
  message: string;
}

export interface StrategyPairsBacktestResponse {
  timeframe: Timeframe;
  pair_id: string;
  generated_at: string;
  exit_mode: BacktestExitMode;
  left_instrument: string;
  right_instrument: string;
  selected_variant: string;
  hedge_ratio: number;
  entry_band: number;
  exit_band: number;
  stop_band: number;
  round_trip_cost_bps: number;
  points: Array<{
    ts: string;
    z: number;
    equity: number;
  }>;
  markers: ChartMarker[];
  rationale_codes: string[];
}

export interface StrategyPairsLiveZResponse {
  timeframe: Timeframe;
  pair_id: string;
  generated_at: string;
  exit_mode: BacktestExitMode;
  entry_band: number;
  exit_band: number;
  stop_band: number;
  selected_variant: string;
  points: Array<{
    ts: string;
    z: number;
  }>;
  markers: ChartMarker[];
  rationale_codes: string[];
}

export interface StrategyUiAuthStatusResponse {
  enabled: boolean;
}

export interface StrategyUiAuthVerifyRequest {
  password: string;
}

export interface StrategyUiAuthVerifyResponse {
  ok: boolean;
}

export interface MarketMetricsResponse {
  instrument: string;
  server_time: string;
  bid: number;
  ask: number;
  mark: number;
  index: number;
  change_24h_pct: number;
  funding_rate: number;
  open_interest: number;
  funding_interval_secs?: number;
}

export interface KillSwitchState {
  active: boolean;
  reason: string;
  updated_at: string;
}

export interface UpdateKillSwitchRequest {
  active: boolean;
  reason: string;
  actor?: string;
}

export interface ExecutionDispatchModeResponse {
  mode: "FAIL_CLOSED" | "SIMULATE_ACK" | "LIVE_KRAKEN";
  requires_live_arm: boolean;
  sizing_tolerance_notional_drift_pct: number;
  sizing_tolerance_hedge_ratio_drift_pct: number;
}

export interface ExecutionDecisionResponse {
  instrument: string;
  timeframe: Timeframe;
  decision: "ALLOWED" | "BLOCKED";
  reason: string | null;
  min_coverage_pct: number;
  evaluated_at: string;
}

export type ExecutionAction = "ENTRY" | "EXIT" | "EMERGENCY_STOP_CLOSE";
export type TradeSide = "BUY" | "SELL";
export type ExecutionMode = "LIVE" | "PAPER";

export interface OrderIntentRequest {
  idempotency_key: string;
  exchange: string;
  account_id: string;
  pair_id?: string | null;
  instrument: string;
  timeframe: Timeframe;
  action: ExecutionAction;
  spread_direction?: "LONG_SPREAD" | "SHORT_SPREAD" | null;
  spread_z?: number | null;
  side: TradeSide;
  qty: number;
  sizing?: {
    target_notional_usd: number;
    target_hedge_ratio: number;
    reference_left_instrument: string;
    reference_right_instrument: string;
    reference_left_price: number;
    reference_right_price: number;
    planned_left_qty: number;
    planned_right_qty: number;
    achieved_notional_usd: number;
    achieved_hedge_ratio: number;
    notional_drift_pct: number;
    hedge_ratio_drift_pct: number;
    tolerance_notional_drift_pct?: number;
    tolerance_hedge_ratio_drift_pct?: number;
  };
  operator_confirmed: boolean;
  operator_id: string | null;
  min_coverage_pct: number;
}

export interface OrderIntentResponse {
  idempotency_key: string;
  exchange: string;
  account_id: string;
  execution_mode: ExecutionMode;
  pair_id: string | null;
  instrument: string;
  timeframe: Timeframe;
  action: ExecutionAction;
  spread_direction: "LONG_SPREAD" | "SHORT_SPREAD" | null;
  spread_z: number | null;
  side: TradeSide;
  qty: number;
  operator_confirmed: boolean;
  operator_id: string | null;
  min_coverage_pct: number;
  decision: "ACCEPTED" | "BLOCKED";
  reason: string | null;
  evaluated_at: string;
}

export interface DispatchIntentRequest {
  idempotency_key: string;
  actor?: string;
}

export interface DispatchIntentResponse {
  idempotency_key: string;
  result: "ACKNOWLEDGED" | "REJECTED" | "NOOP";
  from_state:
    | "NEW"
    | "APPROVED"
    | "PENDING_SUBMIT"
    | "ACKNOWLEDGED"
    | "PARTIALLY_FILLED"
    | "FILLED"
    | "CANCELED"
    | "REJECTED"
    | "EXPIRED"
    | null;
  to_state:
    | "NEW"
    | "APPROVED"
    | "PENDING_SUBMIT"
    | "ACKNOWLEDGED"
    | "PARTIALLY_FILLED"
    | "FILLED"
    | "CANCELED"
    | "REJECTED"
    | "EXPIRED"
    | null;
  exchange_order_id: string | null;
  reason: string | null;
  attempted_at: string;
}

export interface PaperOrderIntentResponse {
  schema_version: string;
  intent: OrderIntentResponse;
  dispatch: DispatchIntentResponse;
  recorded_at: string;
}

export interface OrderStateEvent {
  state:
    | "NEW"
    | "APPROVED"
    | "PENDING_SUBMIT"
    | "ACKNOWLEDGED"
    | "PARTIALLY_FILLED"
    | "FILLED"
    | "CANCELED"
    | "REJECTED"
    | "EXPIRED";
  reason: string;
  actor: string;
  created_at: string;
}

export interface DispatchAttempt {
  attempt_no: number;
  result_state: "ACKNOWLEDGED" | "REJECTED";
  exchange_order_id: string | null;
  reason: string;
  actor: string;
  created_at: string;
}

export interface OrderIntentHistoryResponse {
  idempotency_key: string;
  intent: OrderIntentResponse;
  state_events: OrderStateEvent[];
  dispatch_attempts: DispatchAttempt[];
}

export interface ReconcileResponse {
  reconcile: {
    exchange: string;
    account_id: string;
    ts: string;
    status: "OK" | "STALE_SNAPSHOT" | "DRIFT_EXCEEDED";
    drift_notional: number;
    notes: string;
  } | null;
}

export interface ExecutionPortfolioPositionsResponse {
  exchange: string;
  account_id: string;
  execution_mode: ExecutionMode;
  generated_at: string;
  positions: Array<{
    pair_id: string;
    direction: DirectionHint;
    total_size: number;
    avg_entry_z: number;
    updated_at: string;
  }>;
}

export interface ExecutionOpenTradesResponse {
  exchange: string;
  account_id: string;
  execution_mode: ExecutionMode;
  generated_at: string;
  warnings: string[];
  trades: Array<{
    pair_id: string;
    direction: Exclude<DirectionHint, "NONE">;
    spread_units: number;
    entry_z: number;
    updated_at: string;
    pnl_status: "LIVE" | "STALE" | "UNAVAILABLE";
    unrealized_pnl_usd: number | null;
    legs: Array<{
      instrument: string;
      side: TradeSide;
      qty: number;
      entry_ref_price: number | null;
      live_mark: number | null;
      mark_time: string | null;
      unrealized_pnl_usd: number | null;
    }>;
  }>;
}

export interface SpreadPosition {
  direction: DirectionHint;
  totalSize: number;
  avgEntryZ: number;
  updatedAt: string;
}

export interface TimelineEvent {
  ts: string;
  text: string;
  tone: "ok" | "warn" | "bad";
}

export interface SpreadSeriesPoint {
  ts: string;
  z: number;
  spreadReturn: number;
}

export interface ChartMarker {
  index: number;
  kind: "entry" | "exit" | "stop" | "execution-entry" | "execution-exit";
}
