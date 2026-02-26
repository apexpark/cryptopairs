export type Timeframe = "1m" | "15m" | "1h";
export type BacktestExitMode = "mean_revert" | "opposite_extreme";

export type DirectionHint = "LONG_SPREAD" | "SHORT_SPREAD" | "NONE";

export interface CostGate {
  status: "AVAILABLE" | "UNAVAILABLE";
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
  status: "AVAILABLE" | "UNAVAILABLE";
  pass: boolean;
  rationale_codes: string[];
}

export interface TradeGate {
  status: "AVAILABLE" | "UNAVAILABLE";
  pass: boolean;
  blocked_by: "NONE" | "SETUP" | "COST" | "MULTIPLE" | "UNAVAILABLE";
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

export interface StrategyPairsCostGateResponse {
  timeframe: Timeframe;
  generated_at: string;
  gates: Array<{
    pair_id: string;
    left_instrument: string;
    right_instrument: string;
    timeframe: Timeframe;
    expected_edge_bps: number;
    fee_bps: number;
    funding_model: "STATIC" | "DYNAMIC";
    funding_events: number;
    funding_bps_per_event: number;
    funding_bps: number;
    slippage_bps: number;
    net_edge_bps: number;
    pass: boolean;
    setup_pass?: boolean;
    trade_ready?: boolean;
    trade_blocked_by?: "NONE" | "SETUP" | "COST" | "MULTIPLE" | "UNAVAILABLE";
    rationale_codes: string[];
  }>;
  skipped: Array<{ pair_id: string; reason: string }>;
}

export interface StrategyPairsPortfolioPlanResponse {
  timeframe: Timeframe;
  generated_at: string;
  plan: {
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

export interface OpportunityHistoryStatsEntry {
  timeframe: Timeframe;
  rows: number;
  first_evaluated_at: string | null;
  last_evaluated_at: string | null;
  days_covered: number;
}

export interface StrategyPairsOpportunityHistoryStatsResponse {
  generated_at: string;
  timeframe_filter: Timeframe | null;
  total_rows: number;
  first_evaluated_at: string | null;
  last_evaluated_at: string | null;
  days_covered: number;
  by_timeframe: OpportunityHistoryStatsEntry[];
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

export interface StrategyMaintenanceDownload {
  label: string;
  path: string;
}

export interface StrategyMaintenanceStepResult {
  pass: boolean;
  skipped?: boolean;
  reason?: string;
  [key: string]: unknown;
}

export interface StrategyMaintenanceCycleReport {
  generated_at: string;
  run_id: string;
  status: "PASS" | "FAIL";
  decision: "PROMOTE" | "HOLD" | "REVERT" | "UNKNOWN";
  decision_reasons: string[];
  policy_path: string;
  env_file: string;
  original_values: Record<string, number>;
  baseline_values: Record<string, number>;
  candidate_values: Record<string, number>;
  steps: Record<string, StrategyMaintenanceStepResult>;
  artifacts: Record<string, string>;
  downloads: StrategyMaintenanceDownload[];
}

export interface StrategyMaintenanceLatestResponse {
  available: boolean;
  generated_at: string;
  report: StrategyMaintenanceCycleReport | null;
  reason: string | null;
  artifact_download_route: string;
}

export interface StrategyMaintenanceActionRequest {
  action: "PROMOTE" | "REVERT";
  operator_id: string;
  confirm: boolean;
}

export interface StrategyMaintenanceActionResponse {
  accepted: boolean;
  action: "PROMOTE" | "REVERT";
  operator_id: string;
  pass: boolean;
  generated_at: string;
  report_download_path: string;
  report: Record<string, unknown> | null;
  error: string | null;
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

export interface IntegrityHistoryResponse {
  instrument: string;
  timeframe: Timeframe;
  rows: Array<{
    start_ts: string;
    end_ts: string;
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    reason: string;
    checked_at: string;
  }>;
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

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface DataQueryResponse {
  instrument: string;
  timeframe: Timeframe;
  start_ts: string;
  end_ts: string;
  candles: Candle[];
  integrity: {
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    missing_ranges: Array<{ start_ts: string; end_ts: string; reason: string }>;
    last_verified_at: string;
    warnings: string[];
  };
}

export interface KillSwitchState {
  active: boolean;
  reason: string;
  updated_at: string;
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
  operator_confirmed: boolean;
  operator_id: string | null;
  min_coverage_pct: number;
}

export interface OrderIntentResponse {
  idempotency_key: string;
  exchange: string;
  account_id: string;
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
  generated_at: string;
  positions: Array<{
    pair_id: string;
    direction: DirectionHint;
    total_size: number;
    avg_entry_z: number;
    updated_at: string;
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
